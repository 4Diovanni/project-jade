"""Testes do runner do benchmark (bench.runner).

O laço e o isolamento são testados com a ChatSession mockada — sem Ollama.
"""

import json

import pytest

import bench.runner as runner_mod
from bench.aggregate import Result
from bench.cases import Case
from core.config import settings


class FakeSession:
    """Sessão falsa: anota rota e chunks como se tivesse respondido."""

    def __init__(self, route="local", chunks=0, tool=None, boom=False):
        self._route = route
        self._chunks = chunks
        self._tool = tool
        self._boom = boom

    def send(self, message):
        from core.metrics import note

        if self._boom:
            raise RuntimeError("ollama caiu")
        note(route=self._route, chunks=self._chunks, mood_level=0)
        if self._tool:
            note(tool=self._tool)
        return "resposta"


def _fake_chat_session(**fake_kwargs):
    """Fábrica que substitui `ChatSession` no runner **conferindo os kwargs**.

    `use_journal=False` é o que garante que o bench não escreve notas de conversa
    no vault do usuário. Um dublê que engolisse os kwargs (`lambda **k: ...`)
    deixaria essa propriedade passar em todo teste mesmo se o runner parasse de
    passá-la — então aqui ela é conferida, não descartada.
    """

    def _build(**kwargs):
        assert kwargs.get("use_journal") is False, (
            "o bench precisa construir a ChatSession com use_journal=False "
            f"(veio {kwargs!r}) — sem isso ele escreve notas de conversa no vault real"
        )
        return FakeSession(**fake_kwargs)

    return _build


def _caso(expect, cid="c1"):
    return Case(id=cid, message="oi", category="papo", expect=expect)


def test_run_case_ok(monkeypatch):
    monkeypatch.setattr(runner_mod, "ChatSession", _fake_chat_session())
    r = runner_mod.run_case(_caso({"route": "local"}), cloud_ok=True)
    assert r.status == "ok"
    assert r.meta["route"] == "local"


def test_run_case_falhou(monkeypatch):
    monkeypatch.setattr(runner_mod, "ChatSession", _fake_chat_session())
    r = runner_mod.run_case(_caso({"route": "cloud"}), cloud_ok=True)
    assert r.status == "falhou"
    assert r.failures


def test_run_case_pula_nuvem_sem_chave(monkeypatch):
    monkeypatch.setattr(runner_mod, "ChatSession", _fake_chat_session())
    r = runner_mod.run_case(_caso({"route": "cloud"}), cloud_ok=False)
    assert r.status == "pulado"
    assert "ANTHROPIC_API_KEY" in r.detail


def test_run_case_captura_excecao(monkeypatch):
    monkeypatch.setattr(runner_mod, "ChatSession", _fake_chat_session(boom=True))
    r = runner_mod.run_case(_caso({"route": "local"}), cloud_ok=True)
    assert r.status == "erro"
    assert "ollama caiu" in r.detail


def test_run_case_guarda_o_expect_para_a_agregacao(monkeypatch):
    monkeypatch.setattr(runner_mod, "ChatSession", _fake_chat_session())
    r = runner_mod.run_case(_caso({"route": "local", "context": "none"}), cloud_ok=True)
    assert r.meta["_expect"] == {"route": "local", "context": "none"}


def test_run_case_captura_falha_na_construcao_da_sessao(monkeypatch):
    """Uma ChatSession que não sobe (ex.: Ollama caiu) não pode derrubar a suíte
    inteira — antes desta correção, essa falha acontecia fora do `try` e
    propagava para fora de `run_case`."""

    def explode(**kwargs):
        raise RuntimeError("modelo indisponível")

    monkeypatch.setattr(runner_mod, "ChatSession", explode)
    r = runner_mod.run_case(_caso({"route": "local"}), cloud_ok=True)
    assert r.status == "erro"
    assert "modelo indisponível" in r.detail
    assert r.meta["_expect"] == {"route": "local"}


def test_run_case_captura_falha_na_leitura_do_humor(monkeypatch):
    """Idem para uma falha ao carregar o humor persistido (ex.: disco cheio)."""
    monkeypatch.setattr(runner_mod, "ChatSession", _fake_chat_session())

    def explode():
        raise OSError("disco cheio")

    monkeypatch.setattr(runner_mod, "_mood_level", explode)
    r = runner_mod.run_case(_caso({"route": "local"}), cloud_ok=True)
    assert r.status == "erro"
    assert "disco cheio" in r.detail
    assert r.meta["_expect"] == {"route": "local"}


def test_main_salva_relatorio_parcial_e_repropaga_interrupcao(monkeypatch, tmp_path):
    """Ctrl-C no meio de uma execução longa não pode jogar fora os casos já
    concluídos: o relatório parcial precisa ser gravado, marcado como parcial,
    e a interrupção precisa continuar se propagando (nunca ser engolida)."""

    class _FakeResponse:
        def close(self):
            pass

    monkeypatch.setattr(runner_mod, "urlopen", lambda *a, **k: _FakeResponse())
    monkeypatch.setattr(runner_mod, "_REPORTS_DIR", tmp_path / "reports")

    caso_yaml = tmp_path / "papo.yaml"
    caso_yaml.write_text(
        "- id: c1\n  message: oi\n  expect:\n    route: local\n"
        "- id: c2\n  message: oi de novo\n  expect:\n    route: local\n",
        encoding="utf-8",
    )

    def fake_run(cases, *, repeat=1, results=None):
        # Simula 1 caso concluído antes da interrupção — o segundo nunca roda.
        results.append(Result(case_id="c1", category="papo", status="ok", meta={"_expect": {}}))
        raise KeyboardInterrupt

    monkeypatch.setattr(runner_mod, "run", fake_run)

    original_notes = settings.NOTES_DIR
    with pytest.raises(KeyboardInterrupt):
        runner_mod.main(["--cases", str(caso_yaml)])

    # O isolamento de notas precisa ter sido restaurado mesmo com a interrupção.
    assert settings.NOTES_DIR == original_notes

    relatorios = list((tmp_path / "reports").glob("*.json"))
    assert len(relatorios) == 1
    dados = json.loads(relatorios[0].read_text(encoding="utf-8"))
    assert dados["partial"] is True
    assert dados["evaluated"] == 1


def test_isolated_notes_troca_e_restaura(tmp_path):
    original = settings.NOTES_DIR
    with runner_mod.isolated_notes():
        assert settings.NOTES_DIR != original
        assert settings.NOTES_DIR.is_dir()
    assert settings.NOTES_DIR == original


def test_isolated_notes_semeia_o_humor_em_zero(monkeypatch, tmp_path):
    """O humor isolado começa em 0 **qualquer que seja** o nível real do usuário.

    `core.mood` limita o nível a [-5, +5]. Se o bench copiasse a nota real e ela
    estivesse saturada em -5, `humor-rudeza` produziria delta 0 ("neutral") e o
    caso falharia por saturação do clamp, não por defeito no código."""
    from core.config import settings as cfg
    from core.mood import load_level

    vault_real = tmp_path / "notas"
    vault_real.mkdir()
    (vault_real / cfg.MOOD_NOTE).write_text(
        '---\nnivel: -5\nhumor: "estressada"\n---\n\n# Jade — Humor\n', encoding="utf-8"
    )
    monkeypatch.setattr(cfg, "NOTES_DIR", vault_real)
    assert load_level() == -5  # a nota "real" está saturada no fundo da escala

    with runner_mod.isolated_notes():
        assert load_level() == 0

    assert load_level() == -5  # e a nota real segue intacta


def test_isolated_notes_copia_personalidade_e_perfil(monkeypatch, tmp_path):
    """Personalidade e perfil continuam sendo copiados — só o humor é semeado."""
    from core.config import settings as cfg

    vault_real = tmp_path / "notas"
    vault_real.mkdir()
    (vault_real / cfg.PERSONALITY_NOTE).write_text("personalidade real", encoding="utf-8")
    (vault_real / cfg.PROFILE_NOTE).write_text("perfil real", encoding="utf-8")
    monkeypatch.setattr(cfg, "NOTES_DIR", vault_real)

    with runner_mod.isolated_notes():
        isolado = cfg.NOTES_DIR
        assert (isolado / cfg.PERSONALITY_NOTE).read_text(encoding="utf-8") == "personalidade real"
        assert (isolado / cfg.PROFILE_NOTE).read_text(encoding="utf-8") == "perfil real"


def test_isolated_notes_restaura_mesmo_com_excecao():
    original = settings.NOTES_DIR
    with pytest.raises(RuntimeError):
        with runner_mod.isolated_notes():
            raise RuntimeError("boom")
    assert settings.NOTES_DIR == original


def test_health_check_falha_com_mensagem_util(monkeypatch):
    def explode(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr(runner_mod, "urlopen", explode)
    with pytest.raises(RuntimeError, match="Ollama"):
        runner_mod.health_check()
