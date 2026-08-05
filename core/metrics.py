"""Instrumentação de desempenho da Jade — medição por etapa, custo zero quando desligada.

A medição só acontece dentro de um `capture()`. Fora dele, `timed()` e `note()`
são **no-op**: o custo em produção é um `ContextVar.get()` que devolve `None` —
nada é cronometrado, nada é alocado, nada é gravado.

O turno ativo vive num `ContextVar`, não numa global: é o que impede um turno de
vazar para outro quando a API serve requisições concorrentes em threads distintas.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from contextvars import ContextVar
from dataclasses import dataclass, field
from time import perf_counter


@dataclass
class Turn:
    """Medições de um turno: tempo por etapa e metadados da decisão tomada."""

    #: segundos acumulados por etapa (inclui "total", gravado por `capture`)
    steps: dict[str, float] = field(default_factory=dict)
    #: rota, tool, chunks, fontes, contadores de token...
    meta: dict[str, object] = field(default_factory=dict)


_current: ContextVar[Turn | None] = ContextVar("jade_metrics_turn", default=None)


@contextlib.contextmanager
def capture() -> Iterator[Turn]:
    """Abre um turno de medição e o devolve. Grava `steps['total']` ao fechar."""
    turn = Turn()
    token = _current.set(turn)
    started = perf_counter()
    try:
        yield turn
    finally:
        turn.steps["total"] = perf_counter() - started
        _current.reset(token)


@contextlib.contextmanager
def timed(step: str) -> Iterator[None]:
    """Acumula o tempo do bloco na etapa `step`. No-op se não há turno ativo.

    Etapas aninhadas somam de forma independente — o relatório trata as etapas
    como categorias, não como uma árvore.
    """
    turn = _current.get()
    if turn is None:
        yield
        return
    started = perf_counter()
    try:
        yield
    finally:
        turn.steps[step] = turn.steps.get(step, 0.0) + (perf_counter() - started)


def note(**fields: object) -> None:
    """Anexa metadados ao turno ativo. No-op se não há turno ativo."""
    turn = _current.get()
    if turn is not None:
        turn.meta.update(fields)
