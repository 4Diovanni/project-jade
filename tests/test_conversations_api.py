"""Testes do parsing de conversas e dos endpoints de leitura (CI-safe)."""

from fastapi.testclient import TestClient

from core.config import settings
from core.journal import parse_conversation_note
from interfaces.api import app

_NOTE = """---
title: "abra a calculadora"
data: 2026-07-21
tags: [conversa, jade]
---

# abra a calculadora

Conversa com a Jade · [[Jade — Memória]] · #conversa/2026-07-21

**Você:** oi jade

**Jade:** Oi! Tudo bem?

**Você:** abra a calculadora

**Jade:** Abri calculadora.
"""


def test_parse_extrai_turnos_em_ordem():
    turns = parse_conversation_note(_NOTE)
    assert turns == [
        {"user": "oi jade", "jade": "Oi! Tudo bem?"},
        {"user": "abra a calculadora", "jade": "Abri calculadora."},
    ]


def test_parse_nota_sem_turnos_retorna_vazio():
    assert parse_conversation_note("---\ntags: []\n---\n\n# vazia\n") == []


def test_parse_resposta_multilinha():
    note = "**Você:** liste\n\n**Jade:** linha1\nlinha2\n"
    assert parse_conversation_note(note) == [{"user": "liste", "jade": "linha1\nlinha2"}]


def _write_note(tmp_path, name, title, date, body):
    folder = tmp_path / settings.CONVERSATIONS_SUBDIR
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(
        f'---\ntitle: "{title}"\ndata: {date}\ntags: [conversa, jade]\n---\n\n'
        f"# {title}\n\n{body}\n",
        encoding="utf-8",
    )


def test_list_and_get_conversations(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_PATH", tmp_path)
    monkeypatch.setattr(settings, "NOTES_DIR", tmp_path)  # onde as notas são escritas
    _write_note(
        tmp_path,
        "2026-07-20_100000 — antiga.md",
        "antiga",
        "2026-07-20",
        "**Você:** a\n\n**Jade:** b",
    )
    _write_note(
        tmp_path, "2026-07-21_100000 — nova.md", "nova", "2026-07-21", "**Você:** c\n\n**Jade:** d"
    )
    client = TestClient(app)

    lst = client.get("/conversations").json()
    assert [c["title"] for c in lst] == ["nova", "antiga"]  # mais recente primeiro
    conv_id = lst[0]["id"]

    got = client.get(f"/conversations/{conv_id}").json()
    assert got["title"] == "nova"
    assert got["turns"] == [{"user": "c", "jade": "d"}]


def test_get_conversation_inexistente_404(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_PATH", tmp_path)
    monkeypatch.setattr(settings, "NOTES_DIR", tmp_path)  # onde as notas são escritas
    (tmp_path / settings.CONVERSATIONS_SUBDIR).mkdir(parents=True, exist_ok=True)
    assert TestClient(app).get("/conversations/nao_existe").status_code == 404


def test_get_conversation_bloqueia_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_PATH", tmp_path)
    monkeypatch.setattr(settings, "NOTES_DIR", tmp_path)  # onde as notas são escritas
    (tmp_path / settings.CONVERSATIONS_SUBDIR).mkdir(parents=True, exist_ok=True)
    # '../../secret' deve ser sanitizado para o basename e resultar em 404.
    assert TestClient(app).get("/conversations/..%2f..%2fsecret").status_code in (404, 400)


# ── Título por contexto + renomeação ─────────────────────────
def test_clean_title_remove_ruido_e_bloco_think():
    from core.journal import clean_title

    assert clean_title('"Planejamento de RPG"') == "Planejamento de RPG"
    assert clean_title("<think>hmm...</think>\nSistema de poderes") == "Sistema de poderes"
    assert clean_title("- Dicas de foco.") == "Dicas de foco"
    assert clean_title("") == "conversa"


def test_generate_title_usa_o_llm():
    from core.journal import generate_title

    class _LLM:
        def invoke(self, prompt):
            self.prompt = prompt
            return type("M", (), {"content": "  Rotina de estudos  "})()

    llm = _LLM()
    assert generate_title("Você: oi\nJade: olá", llm) == "Rotina de estudos"
    assert "título curto" in llm.prompt


def test_apply_title_troca_frontmatter_e_cabecalho():
    from core.journal import apply_title, title_is_custom

    nota = '---\ntitle: "oi tudo bem"\ndata: 2026-07-25\n---\n\n# oi tudo bem\n\ncorpo\n'
    out = apply_title(nota, "Planejamento da semana")

    assert 'title: "Planejamento da semana"' in out
    assert "# Planejamento da semana" in out
    assert "oi tudo bem" not in out
    assert title_is_custom(out) is True
    assert "corpo" in out  # não destrói o conteúdo


def test_rename_conversation_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "NOTES_DIR", tmp_path)
    _write_note(
        tmp_path, "2026-07-25_100000 — oi.md", "oi", "2026-07-25", "**Você:** a\n\n**Jade:** b"
    )
    client = TestClient(app)
    conv_id = "2026-07-25_100000 — oi"

    resp = client.patch(f"/conversations/{conv_id}", json={"title": "Assunto novo"})

    assert resp.status_code == 200
    assert resp.json()["title"] == "Assunto novo"
    assert client.get(f"/conversations/{conv_id}").json()["title"] == "Assunto novo"


def test_rename_conversation_inexistente_404(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "NOTES_DIR", tmp_path)
    (tmp_path / settings.CONVERSATIONS_SUBDIR).mkdir(parents=True, exist_ok=True)
    resp = TestClient(app).patch("/conversations/nao_existe", json={"title": "x"})
    assert resp.status_code == 404


def test_clean_title_lida_com_think_repetido_sem_travar():
    """Regressão (CodeQL/ReDoS): a limpeza roda sobre saída do LLM, então não
    pode ter backtracking polinomial em entradas adversárias."""
    import time

    from core.journal import clean_title

    inicio = time.perf_counter()
    # Blocos abertos sem fechar: o conteúdo é descartado (cai no fallback).
    assert clean_title("<think>" * 3000 + "Título") == "conversa"
    # Blocos fechados repetidos: o título real sobrevive.
    assert clean_title("<think>a</think>" * 3000 + "Título") == "Título"
    assert time.perf_counter() - inicio < 1.0  # linear, não polinomial


def test_clean_title_think_variantes():
    from core.journal import clean_title

    assert clean_title("<think>a</think><think>b</think>Real") == "Real"
    assert clean_title("<THINK>x</THINK>Ok") == "Ok"
    assert clean_title("Antes<think>sem fechar") == "Antes"


def test_apply_title_reaplicado_nao_duplica_marcador():
    from core.journal import apply_title, title_is_custom

    nota = '---\ntitle: "a"\ndata: 2026-07-25\n---\n\n# a\n\ncorpo\n'
    duas_vezes = apply_title(apply_title(nota, "b"), "c")

    assert duas_vezes.count("title_custom") == 1
    assert title_is_custom(duas_vezes) is True
    assert 'title: "c"' in duas_vezes
