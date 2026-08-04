"""Testes do relatório do benchmark (bench.report)."""

import json

from bench.aggregate import Result
from bench.report import load_previous, render, write


def _resumo(**over):
    base = {
        "total": 2,
        "evaluated": 2,
        "ok": 1,
        "failed": 1,
        "skipped": 0,
        "errored": 0,
        "route_accuracy": 0.5,
        "by_category": {"tools": {"total": 2, "ok": 1, "accuracy": 0.5}},
        "recall_at_k": 1.0,
        "context_precision": 0.0,
        "route_distribution": {"local": 2},
        "latency": {"llm": {"p50": 2.0, "p95": 3.0, "n": 2}},
        "tokens_per_second": 37.5,
        "prompt_tokens": {"p50": 1200.0, "p95": 1800.0},
    }
    base.update(over)
    return base


def _resultados():
    return [
        Result(case_id="a", category="tools", status="ok"),
        Result(
            case_id="b",
            category="tools",
            status="falhou",
            failures=["route: esperava 'cloud', veio 'local'"],
        ),
    ]


def test_render_traz_as_metricas_principais():
    md = render(_resumo(), _resultados())
    assert "Acerto de rota" in md
    assert "50" in md  # 50%
    assert "37.5" in md or "37,5" in md


def test_render_lista_as_falhas_com_motivo():
    md = render(_resumo(), _resultados())
    assert "esperava 'cloud', veio 'local'" in md


def test_render_sem_anterior_nao_mostra_delta():
    md = render(_resumo(), _resultados())
    assert "Delta" not in md


def test_render_com_anterior_mostra_delta_com_sinal():
    anterior = _resumo(route_accuracy=0.25)
    md = render(_resumo(), _resultados(), previous=anterior)
    assert "Delta" in md
    assert "+25" in md


def test_render_marca_metrica_ausente_com_traco():
    md = render(_resumo(tokens_per_second=None, prompt_tokens=None), _resultados())
    assert "—" in md


def test_write_grava_md_e_json(tmp_path):
    caminho = write(tmp_path, _resumo(), _resultados(), tag="baseline")
    assert caminho.suffix == ".md"
    assert caminho.exists()
    gemeo = caminho.with_suffix(".json")
    assert gemeo.exists()
    assert json.loads(gemeo.read_text(encoding="utf-8"))["route_accuracy"] == 0.5
    assert "baseline" in caminho.name


def test_load_previous_devolve_none_em_pasta_vazia(tmp_path):
    assert load_previous(tmp_path) is None


def test_load_previous_le_o_mais_recente(tmp_path):
    write(tmp_path, _resumo(route_accuracy=0.1), _resultados(), tag="antigo")
    (tmp_path / "2099-01-01-0000-novo.json").write_text(
        json.dumps(_resumo(route_accuracy=0.9)), encoding="utf-8"
    )
    assert load_previous(tmp_path)["route_accuracy"] == 0.9
