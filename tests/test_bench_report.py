"""Testes do relatório do benchmark (bench.report)."""

import json
from datetime import datetime

import bench.report as report_mod
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
    """O traço tem que aparecer na linha da métrica nula, não em qualquer lugar do texto.

    O `—` também aparece incondicionalmente no título e nos motivos de falha, então
    checar só `"—" in md` não prova nada sobre `_pct`/`_num`. Aqui isolamos a linha de
    cada métrica nula e exigimos o traço nela — e, no negativo, que o valor "quebrado"
    (0.0% / 0.0) que `_pct`/`_num` dariam se parassem de tratar `None` não apareça.
    """
    md = render(
        _resumo(
            recall_at_k=None,
            context_precision=None,
            tokens_per_second=None,
            prompt_tokens=None,
        ),
        _resultados(),
    )
    linhas = md.splitlines()

    def _linha_de(rotulo: str) -> str:
        encontradas = [linha for linha in linhas if linha.startswith(f"| {rotulo} |")]
        assert encontradas, f"linha da métrica {rotulo!r} não encontrada no relatório"
        return encontradas[0]

    recall = _linha_de("Recall@k do RAG")
    precisao = _linha_de("Precisão de contexto")
    tps = _linha_de("Tokens/s (local)")
    p50 = _linha_de("Tokens de prompt p50")
    p95 = _linha_de("Tokens de prompt p95")

    for linha in (recall, precisao, tps, p50, p95):
        assert "—" in linha

    assert "0.0%" not in recall
    assert "0.0%" not in precisao
    assert "0.0" not in tps
    assert "0.0" not in p50
    assert "0.0" not in p95


def test_write_grava_md_e_json(tmp_path):
    caminho = write(tmp_path, _resumo(), _resultados(), tag="baseline")
    assert caminho.suffix == ".md"
    assert caminho.exists()
    gemeo = caminho.with_suffix(".json")
    assert gemeo.exists()
    assert json.loads(gemeo.read_text(encoding="utf-8"))["route_accuracy"] == 0.5
    assert "baseline" in caminho.name


def test_write_duas_vezes_no_mesmo_minuto_nao_colide(tmp_path, monkeypatch):
    """Duas gravações no mesmo minuto (segundos diferentes) não podem se sobrescrever.

    Com `_stamp()` truncado em minutos, duas execuções dentro do mesmo minuto geravam
    o mesmo nome de arquivo e a segunda `write()` apagava silenciosamente a primeira —
    exatamente o cenário que a série histórica existe para evitar. Fixamos o relógio
    para simular chamadas dentro do mesmo minuto, em segundos distintos, e conferimos
    que cada `write()` produz seu próprio par `.md`/`.json`.
    """
    momentos = iter(datetime(2026, 1, 1, 12, 0, segundo) for segundo in range(4))

    class _RelogioFixo(datetime):
        @classmethod
        def now(cls, tz=None):
            return next(momentos)

    monkeypatch.setattr(report_mod, "datetime", _RelogioFixo)

    primeiro = write(tmp_path, _resumo(), _resultados())
    segundo = write(tmp_path, _resumo(), _resultados())

    assert primeiro != segundo
    assert len(list(tmp_path.glob("*.md"))) == 2
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_load_previous_devolve_none_em_pasta_vazia(tmp_path):
    assert load_previous(tmp_path) is None


def test_load_previous_le_o_mais_recente(tmp_path):
    write(tmp_path, _resumo(route_accuracy=0.1), _resultados(), tag="antigo")
    (tmp_path / "2099-01-01-0000-novo.json").write_text(
        json.dumps(_resumo(route_accuracy=0.9)), encoding="utf-8"
    )
    assert load_previous(tmp_path)["route_accuracy"] == 0.9
