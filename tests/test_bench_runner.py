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
    monkeypatch.setattr(runner_mod, "ChatSession", lambda **k: FakeSession())

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
