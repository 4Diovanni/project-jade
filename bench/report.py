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
    ]
    if summary.get("partial"):
        linhas += [
            "> ⚠️ **Execução parcial** — interrompida antes de terminar todos os "
            "casos planejados. Números abaixo cobrem só o que rodou; não use "
            "este relatório como baseline nem confie no delta contra ele.",
            "",
        ]
    linhas += [
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

    # Cada métrica é medida SÓ sobre a sua dimensão, e só nos casos que a
    # declaram. O rótulo diz o denominador porque a confusão entre "acerto de
    # rota" e "caso aprovado" já produziu um relatório que mentia.
    qualidade = [
        ("Acerto de rota", "route_accuracy"),
        ("Recall@k do RAG", "recall_at_k"),
        ("Precisão de contexto (casos `context: none`)", "context_precision"),
        ("Aprovação integral dos casos", "pass_rate"),
    ]
    for nome, chave in qualidade:
        atual = summary.get(chave)
        linha = f"| {nome} | {_pct(atual)} |"
        if previous:
            linha += f" {_delta_pct(atual, previous.get(chave))} |"
        linhas.append(linha)

    linhas += [
        "",
        "> **Como ler:** cada métrica de qualidade cobre **apenas** os casos que declaram a "
        "expectativa correspondente, e conta só as falhas **daquela** dimensão. Um caso que "
        "roteia certo mas puxa contexto indevido conta como acerto de rota e erro de contexto. "
        "*Acerto de rota* = casos com `route`. *Recall@k* = casos com `sources_include`. "
        "*Precisão de contexto* = casos com `context: none` (os `context: any` medem cobertura, "
        "não precisão). *Aprovação integral* = casos que passaram em **todas** as suas "
        "expectativas.",
    ]

    linhas += [
        "",
        "### Por categoria (aprovação integral do caso)",
        "",
        "| Categoria | Aprovação | Casos |",
        "|---|---|---|",
    ]
    for categoria, dados in sorted(summary["by_category"].items()):
        linhas.append(f"| {categoria} | {_pct(dados['pass_rate'])} | {dados['total']} |")

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
            motivo = "; ".join(str(f) for f in r.failures) or r.detail or r.status
            linhas.append(f"- **`{r.case_id}`** ({r.category}) — {r.status}: {motivo}")

    return "\n".join(linhas) + "\n"


def _stamp(tag: str) -> str:
    base = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    return f"{base}-{tag}" if tag else base


def load_previous(reports_dir: str | Path) -> dict | None:
    """Carrega o resumo da execução completa mais recente.

    Relatórios marcados `partial` são **pulados**: eles cobrem uma população
    truncada (a execução foi interrompida no meio), e comparar contra eles
    produziria um delta sem sentido — e sem aviso, já que o alerta de parcial só
    é impresso para o relatório atual. Um relatório ilegível também é pulado, em
    vez de zerar a comparação inteira.
    """
    pasta = Path(reports_dir)
    if not pasta.is_dir():
        return None
    for arquivo in sorted(pasta.glob("*.json"), reverse=True):
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(dados, dict) and not dados.get("partial"):
            return dados
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
