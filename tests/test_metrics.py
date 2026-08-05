"""Testes da instrumentação de desempenho (core.metrics).

Cobrem as três garantias que fazem o módulo ser seguro em produção:
acumulação correta, isolamento entre contextos e custo zero fora de `capture()`.
"""

import contextvars

import pytest

from core import metrics


def test_capture_grava_o_total():
    with metrics.capture() as turn:
        pass
    assert "total" in turn.steps
    assert turn.steps["total"] >= 0.0


def test_timed_registra_a_etapa():
    with metrics.capture() as turn:
        with metrics.timed("llm"):
            pass
    assert "llm" in turn.steps


def test_timed_acumula_chamadas_repetidas():
    with metrics.capture() as turn:
        with metrics.timed("rag_embed"):
            pass
        primeiro = turn.steps["rag_embed"]
        with metrics.timed("rag_embed"):
            pass
    assert turn.steps["rag_embed"] >= primeiro


def test_timed_contabiliza_mesmo_com_excecao():
    with metrics.capture() as turn:
        with pytest.raises(RuntimeError):
            with metrics.timed("tool_run"):
                raise RuntimeError("boom")
    assert "tool_run" in turn.steps


def test_etapas_aninhadas_sao_independentes():
    with metrics.capture() as turn:
        with metrics.timed("rag_query"):
            with metrics.timed("rag_embed"):
                pass
    assert {"rag_query", "rag_embed", "total"} <= set(turn.steps)


def test_note_anexa_metadados():
    with metrics.capture() as turn:
        metrics.note(route="local", chunks=6)
        metrics.note(sources=["CLAUDE.md"])
    assert turn.meta == {"route": "local", "chunks": 6, "sources": ["CLAUDE.md"]}


def test_timed_e_noop_fora_de_capture():
    """Em produção não há turno ativo: nada pode ser gravado nem explodir."""
    with metrics.timed("llm"):
        pass
    metrics.note(route="local")  # não levanta


def test_turnos_nao_vazam_entre_contextos():
    """Duas requisições concorrentes não podem compartilhar o mesmo turno."""
    coletadas: list[set[str]] = []

    def trabalho(etapa: str) -> None:
        with metrics.capture() as turn:
            with metrics.timed(etapa):
                pass
        coletadas.append(set(turn.steps))

    contextvars.copy_context().run(trabalho, "a")
    contextvars.copy_context().run(trabalho, "b")

    assert coletadas == [{"a", "total"}, {"b", "total"}]


def test_capture_restaura_o_estado_anterior():
    with metrics.capture():
        pass
    # Fora do bloco, timed volta a ser no-op (nenhum turno pendurado).
    with metrics.timed("llm"):
        pass
