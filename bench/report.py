"""Relatório do benchmark: Markdown para humano, JSON para a comparação.

O `.md` é o que você lê; o `.json` gêmeo é o que a execução seguinte carrega
para calcular o delta. Os dois são versionados no git — a série histórica é o
que torna regressão visível sem ninguém ir procurar.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from bench.aggregate import Result

_TRACO = "—"


def _pct(value: float | None) -> str:
    return f"{value * 100:.1f}%" if value is not None else _TRACO


def _num(value: float | None, casas: int = 1) -> str:
    return f"{value:.{casas}f}" if value is not None else _TRACO


def _delta_pct(atual: float | None, anterior: float | None) -> str:
    """Variação em pontos percentuais, com sinal explícito."""
    if atual is None or anterior is None:
        return _TRACO
    diff = (atual - anterior) * 100
    return f"{diff:+.1f} p.p." if abs(diff) >= 0.05 else "="


def _delta_num(atual: float | None, anterior: float | None) -> str:
    if atual is None or anterior is None:
        return _TRACO
    diff = atual - anterior
    return f"{diff:+.2f}" if abs(diff) >= 0.005 else "="


def render(
    summary: dict,
    results: list[Result],
    *,
    tag: str = "",
    previous: dict | None = None,
) -> str:
    """Monta o relatório em Markdown."""
    quando = datetime.now().strftime("%Y-%m-%d %H:%M")
    linhas: list[str] = [
        f"# Benchmark da Jade — {quando}" + (f" · `{tag}`" if tag else ""),
        "",
        f"{summary['evaluated']} caso(s) avaliado(s) · "
        f"{summary['ok']} ok · {summary['failed']} falhou · "
        f"{summary['skipped']} pulado · {summary['errored']} erro",
        "",
        "## Qualidade das decisões",
        "",
    ]

    cabecalho = "| Métrica | Valor |"
    separador = "|---|---|"
    if previous:
        cabecalho = "| Métrica | Valor | Delta |"
        separador = "|---|---|---|"
    linhas += [cabecalho, separador]

    qualidade = [
        ("Acerto de rota", summary["route_accuracy"], previous and previous.get("route_accuracy")),
        ("Recall@k do RAG", summary["recall_at_k"], previous and previous.get("recall_at_k")),
        (
            "Precisão de contexto",
            summary["context_precision"],
            previous and previous.get("context_precision"),
        ),
    ]
    for nome, atual, anterior in qualidade:
        linha = f"| {nome} | {_pct(atual)} |"
        if previous:
            linha += f" {_delta_pct(atual, anterior)} |"
        linhas.append(linha)

    linhas += ["", "### Por categoria", "", "| Categoria | Acerto | Casos |", "|---|---|---|"]
    for categoria, dados in sorted(summary["by_category"].items()):
        linhas.append(f"| {categoria} | {_pct(dados['accuracy'])} | {dados['total']} |")

    dist = summary["route_distribution"]
    linhas += [
        "",
        "### Distribuição real de rotas",
        "",
        ("| " + " | ".join(dist) + " |") if dist else "(nenhuma rota registrada)",
    ]
    if dist:
        linhas.append("|" + "---|" * len(dist))
        linhas.append("| " + " | ".join(str(v) for v in dist.values()) + " |")

    linhas += ["", "## Desempenho", "", "| Etapa | p50 (s) | p95 (s) | n |", "|---|---|---|---|"]
    for etapa, dados in summary["latency"].items():
        linhas.append(
            f"| `{etapa}` | {_num(dados['p50'], 3)} | {_num(dados['p95'], 3)} | {dados['n']} |"
        )

    tps = summary["tokens_per_second"]
    tokens = summary["prompt_tokens"]
    linhas += [
        "",
        "| Métrica | Valor |" + (" Delta |" if previous else ""),
        "|---|---|" + ("---|" if previous else ""),
    ]
    linha_tps = f"| Tokens/s (local) | {_num(tps)} |"
    if previous:
        linha_tps += f" {_delta_num(tps, previous.get('tokens_per_second'))} |"
    linhas.append(linha_tps)
    linhas.append(
        f"| Tokens de prompt p50 | {_num(tokens['p50'], 0) if tokens else _TRACO} |"
        + (" |" if previous else "")
    )
    linhas.append(
        f"| Tokens de prompt p95 | {_num(tokens['p95'], 0) if tokens else _TRACO} |"
        + (" |" if previous else "")
    )

    falhas = [r for r in results if r.status in {"falhou", "erro", "pulado"}]
    if falhas:
        linhas += ["", "## Casos que não passaram", ""]
        for r in falhas:
            motivo = "; ".join(r.failures) or r.detail or r.status
            linhas.append(f"- **`{r.case_id}`** ({r.category}) — {r.status}: {motivo}")

    return "\n".join(linhas) + "\n"


def _stamp(tag: str) -> str:
    base = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    return f"{base}-{tag}" if tag else base


def load_previous(reports_dir: str | Path) -> dict | None:
    """Carrega o resumo da execução anterior (o .json de nome mais recente)."""
    pasta = Path(reports_dir)
    if not pasta.is_dir():
        return None
    arquivos = sorted(pasta.glob("*.json"))
    if not arquivos:
        return None
    try:
        return json.loads(arquivos[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write(
    reports_dir: str | Path,
    summary: dict,
    results: list[Result],
    *,
    tag: str = "",
) -> Path:
    """Grava o par .md + .json e devolve o caminho do .md."""
    pasta = Path(reports_dir)
    pasta.mkdir(parents=True, exist_ok=True)
    anterior = load_previous(pasta)

    nome = _stamp(tag)
    md = pasta / f"{nome}.md"
    md.write_text(render(summary, results, tag=tag, previous=anterior), encoding="utf-8")
    (pasta / f"{nome}.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return md
