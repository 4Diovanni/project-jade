"""Avaliação de um caso contra o turno medido, e agregação em métricas.

Tudo aqui é função pura: recebe dados, devolve dados. Não executa a Jade, não
lê arquivo, não fala com o LLM — por isso roda no CI.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from bench.cases import Case
from core.metrics import Turn


@dataclass
class Result:
    """Desfecho de um caso: o que se pediu, o que aconteceu, e quanto custou."""

    case_id: str
    category: str
    #: "ok" | "falhou" | "erro" | "pulado"
    status: str
    failures: list[str] = field(default_factory=list)
    steps: dict[str, float] = field(default_factory=dict)
    meta: dict = field(default_factory=dict)
    #: preenchido quando status == "erro" ou "pulado"
    detail: str = ""


def evaluate(case: Case, turn: Turn, *, mood_before: int) -> tuple[str, list[str]]:
    """Confere o que se esperava do caso contra o que o turno registrou.

    Devolve ("ok", []) ou ("falhou", [motivos]). Acumula todos os motivos — um
    caso pode errar a rota E trazer contexto indevido, e as duas coisas importam.
    """
    falhas: list[str] = []
    expect = case.expect

    if "route" in expect:
        obtida = turn.meta.get("route")
        if obtida != expect["route"]:
            falhas.append(f"route: esperava {expect['route']!r}, veio {obtida!r}")

    if "tool" in expect:
        obtida = turn.meta.get("tool")
        if obtida != expect["tool"]:
            falhas.append(f"tool: esperava {expect['tool']!r}, veio {obtida!r}")

    if "sources_include" in expect:
        obtidas = set(turn.meta.get("sources") or [])
        faltando = [s for s in expect["sources_include"] if s not in obtidas]
        if faltando:
            falhas.append(
                f"sources_include: faltou {', '.join(faltando)} "
                f"(veio: {', '.join(sorted(obtidas)) or 'nada'})"
            )

    if "context" in expect:
        chunks = int(turn.meta.get("chunks") or 0)
        if expect["context"] == "none" and chunks > 0:
            falhas.append(f"context: esperava nenhum trecho, vieram {chunks}")
        if expect["context"] == "any" and chunks == 0:
            falhas.append("context: esperava algum trecho, não veio nenhum")

    if "mood_delta" in expect:
        depois = int(turn.meta.get("mood_level") or 0)
        delta = depois - mood_before
        direcao = "positive" if delta > 0 else "negative" if delta < 0 else "neutral"
        if direcao != expect["mood_delta"]:
            falhas.append(
                f"mood_delta: esperava {expect['mood_delta']!r}, "
                f"veio {direcao!r} ({mood_before:+d} → {depois:+d})"
            )

    return ("falhou", falhas) if falhas else ("ok", [])


def percentile(values: list[float], p: float) -> float:
    """Percentil por índice (nearest-rank). 0.0 para lista vazia."""
    if not values:
        return 0.0
    ordenados = sorted(values)
    indice = max(0, min(len(ordenados) - 1, round(p / 100 * len(ordenados)) - 1))
    return ordenados[indice]


def _quality(results: list[Result], expect_key: str) -> float | None:
    """Fração de acerto entre os casos que declaram `expect_key`.

    Devolve None quando nenhum caso exercita a métrica — melhor um traço no
    relatório do que um 0% que parece defeito.
    """
    relevantes = [r for r in results if expect_key in r.meta.get("_expect", {})]
    if not relevantes:
        return None
    acertos = sum(1 for r in relevantes if r.status == "ok")
    return acertos / len(relevantes)


def summarize(results: list[Result]) -> dict:
    """Agrega os resultados nas métricas do relatório."""
    avaliados = [r for r in results if r.status in {"ok", "falhou"}]
    acertos = sum(1 for r in avaliados if r.status == "ok")

    por_categoria: dict[str, dict] = {}
    for r in avaliados:
        bucket = por_categoria.setdefault(r.category, {"total": 0, "ok": 0})
        bucket["total"] += 1
        bucket["ok"] += 1 if r.status == "ok" else 0
    for bucket in por_categoria.values():
        bucket["accuracy"] = bucket["ok"] / bucket["total"] if bucket["total"] else 0.0

    etapas: dict[str, list[float]] = {}
    for r in avaliados:
        for etapa, segundos in r.steps.items():
            etapas.setdefault(etapa, []).append(segundos)
    latencia = {
        etapa: {"p50": percentile(v, 50), "p95": percentile(v, 95), "n": len(v)}
        for etapa, v in sorted(etapas.items())
    }

    prompt_tokens = [
        float(r.meta["prompt_eval_count"]) for r in avaliados if "prompt_eval_count" in r.meta
    ]

    tokens = sum(int(r.meta["eval_count"]) for r in avaliados if "eval_count" in r.meta)
    duracao_ns = sum(int(r.meta["eval_duration"]) for r in avaliados if "eval_duration" in r.meta)
    tps = (tokens / (duracao_ns / 1e9)) if tokens and duracao_ns else None

    return {
        "total": len(results),
        "evaluated": len(avaliados),
        "ok": acertos,
        "failed": len(avaliados) - acertos,
        "skipped": sum(1 for r in results if r.status == "pulado"),
        "errored": sum(1 for r in results if r.status == "erro"),
        "route_accuracy": acertos / len(avaliados) if avaliados else 0.0,
        "by_category": por_categoria,
        "recall_at_k": _quality(avaliados, "sources_include"),
        "context_precision": _quality(avaliados, "context"),
        "route_distribution": dict(
            Counter(r.meta.get("route") for r in avaliados if r.meta.get("route"))
        ),
        "latency": latencia,
        "tokens_per_second": tps,
        "prompt_tokens": {
            "p50": percentile(prompt_tokens, 50),
            "p95": percentile(prompt_tokens, 95),
        }
        if prompt_tokens
        else None,
    }
