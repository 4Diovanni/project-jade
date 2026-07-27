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
