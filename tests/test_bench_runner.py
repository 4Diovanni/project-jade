"""Testes do runner do benchmark (bench.runner).

O laço e o isolamento são testados com a ChatSession mockada — sem Ollama.
"""

import pytest

import bench.runner as runner_mod
from bench.cases import Case
from core.config import settings


class FakeSession:
    """Sessão falsa: anota rota e chunks como se tivesse respondido."""

    def __init__(self, route="local", chunks=0, tool=None, boom=False, **kwargs):
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


def _caso(expect, cid="c1"):
    return Case(id=cid, message="oi", category="papo", expect=expect)


def test_run_case_ok(monkeypatch):
    monkeypatch.setattr(runner_mod, "ChatSession", lambda **k: FakeSession())
    r = runner_mod.run_case(_caso({"route": "local"}), cloud_ok=True)
    assert r.status == "ok"
    assert r.meta["route"] == "local"


def test_run_case_falhou(monkeypatch):
    monkeypatch.setattr(runner_mod, "ChatSession", lambda **k: FakeSession())
    r = runner_mod.run_case(_caso({"route": "cloud"}), cloud_ok=True)
    assert r.status == "falhou"
    assert r.failures


def test_run_case_pula_nuvem_sem_chave(monkeypatch):
    monkeypatch.setattr(runner_mod, "ChatSession", lambda **k: FakeSession())
    r = runner_mod.run_case(_caso({"route": "cloud"}), cloud_ok=False)
    assert r.status == "pulado"
    assert "ANTHROPIC_API_KEY" in r.detail


def test_run_case_captura_excecao(monkeypatch):
    monkeypatch.setattr(runner_mod, "ChatSession", lambda **k: FakeSession(boom=True))
    r = runner_mod.run_case(_caso({"route": "local"}), cloud_ok=True)
    assert r.status == "erro"
    assert "ollama caiu" in r.detail


def test_run_case_guarda_o_expect_para_a_agregacao(monkeypatch):
    monkeypatch.setattr(runner_mod, "ChatSession", lambda **k: FakeSession())
    r = runner_mod.run_case(_caso({"route": "local", "context": "none"}), cloud_ok=True)
    assert r.meta["_expect"] == {"route": "local", "context": "none"}


def test_isolated_notes_troca_e_restaura(tmp_path):
    original = settings.NOTES_DIR
    with runner_mod.isolated_notes():
        assert settings.NOTES_DIR != original
        assert settings.NOTES_DIR.is_dir()
    assert settings.NOTES_DIR == original


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
