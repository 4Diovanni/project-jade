"""Testes da avaliação e agregação do benchmark (bench.aggregate).

Funções puras: recebem casos e turnos sintéticos. Nada de LLM, nada de I/O.
"""

from bench.aggregate import Result, evaluate, percentile, summarize
from bench.cases import Case
from core.metrics import Turn


def _caso(expect, cid="c1", categoria="tools"):
    return Case(id=cid, message="msg", category=categoria, expect=expect)


def _turno(meta=None, steps=None):
    return Turn(steps=steps or {"total": 1.0}, meta=meta or {})


# ── evaluate ──
def test_rota_correta_passa():
    status, falhas = evaluate(_caso({"route": "local"}), _turno({"route": "local"}), mood_before=0)
    assert status == "ok"
    assert falhas == []


def test_rota_errada_falha_com_motivo():
    status, falhas = evaluate(_caso({"route": "cloud"}), _turno({"route": "local"}), mood_before=0)
    assert status == "falhou"
    assert "route" in falhas[0]


def test_nome_da_tool_e_conferido():
    status, falhas = evaluate(
        _caso({"route": "tool", "tool": "system_control"}),
        _turno({"route": "tool", "tool": "outra"}),
        mood_before=0,
    )
    assert status == "falhou"
    assert any("tool" in f for f in falhas)


def test_sources_include_exige_todas_as_fontes():
    caso = _caso({"sources_include": ["CLAUDE.md", "README.md"]})
    status, falhas = evaluate(caso, _turno({"sources": ["CLAUDE.md"]}), mood_before=0)
    assert status == "falhou"
    assert "README.md" in falhas[0]


def test_sources_include_passa_quando_todas_presentes():
    caso = _caso({"sources_include": ["CLAUDE.md"]})
    status, _ = evaluate(caso, _turno({"sources": ["outra.md", "CLAUDE.md"]}), mood_before=0)
    assert status == "ok"


def test_context_none_falha_quando_veio_contexto():
    status, falhas = evaluate(_caso({"context": "none"}), _turno({"chunks": 6}), mood_before=0)
    assert status == "falhou"
    assert "context" in falhas[0]


def test_context_none_passa_sem_chunks():
    status, _ = evaluate(_caso({"context": "none"}), _turno({"chunks": 0}), mood_before=0)
    assert status == "ok"


def test_context_any_exige_pelo_menos_um_chunk():
    status, _ = evaluate(_caso({"context": "any"}), _turno({"chunks": 3}), mood_before=0)
    assert status == "ok"


def test_mood_delta_negative():
    caso = _caso({"mood_delta": "negative"})
    status, _ = evaluate(caso, _turno({"mood_level": -2}), mood_before=0)
    assert status == "ok"


def test_mood_delta_neutral_falha_se_mudou():
    caso = _caso({"mood_delta": "neutral"})
    status, falhas = evaluate(caso, _turno({"mood_level": 3}), mood_before=0)
    assert status == "falhou"
    assert "mood" in falhas[0]


def test_varias_falhas_sao_acumuladas():
    caso = _caso({"route": "cloud", "context": "none"})
    status, falhas = evaluate(caso, _turno({"route": "local", "chunks": 6}), mood_before=0)
    assert status == "falhou"
    assert len(falhas) == 2


# ── percentile ──
def test_percentile_mediana():
    assert percentile([1.0, 2.0, 3.0], 50) == 2.0


def test_percentile_lista_vazia():
    assert percentile([], 50) == 0.0


def test_percentile_p95_pega_o_topo():
    assert percentile([1.0, 2.0, 3.0, 100.0], 95) == 100.0


# ── summarize ──
def _res(cid, categoria, status, steps=None, meta=None):
    return Result(
        case_id=cid,
        category=categoria,
        status=status,
        failures=[],
        steps=steps or {"total": 1.0},
        meta=meta or {},
    )


def test_summarize_acerto_de_rota():
    resultados = [
        _res("a", "tools", "ok"),
        _res("b", "tools", "falhou"),
        _res("c", "papo", "ok"),
    ]
    resumo = summarize(resultados)
    assert resumo["route_accuracy"] == 2 / 3
    assert resumo["by_category"]["tools"]["accuracy"] == 0.5
    assert resumo["by_category"]["papo"]["accuracy"] == 1.0


def test_summarize_ignora_pulados_na_acuracia():
    resultados = [_res("a", "tools", "ok"), _res("b", "conhecimento", "pulado")]
    resumo = summarize(resultados)
    assert resumo["route_accuracy"] == 1.0
    assert resumo["skipped"] == 1


def test_summarize_distribuicao_de_rotas():
    resultados = [
        _res("a", "tools", "ok", meta={"route": "tool"}),
        _res("b", "papo", "ok", meta={"route": "local"}),
        _res("c", "papo", "ok", meta={"route": "local"}),
    ]
    resumo = summarize(resultados)
    assert resumo["route_distribution"] == {"tool": 1, "local": 2}


def test_summarize_latencia_por_etapa():
    resultados = [
        _res("a", "papo", "ok", steps={"llm": 2.0, "total": 3.0}),
        _res("b", "papo", "ok", steps={"llm": 4.0, "total": 5.0}),
    ]
    resumo = summarize(resultados)
    # Percentil por nearest-rank: com n=2, o p50 é o menor dos dois.
    assert resumo["latency"]["llm"]["p50"] == 2.0
    assert resumo["latency"]["llm"]["p95"] == 4.0
    assert resumo["latency"]["total"]["p50"] == 3.0


def test_summarize_tokens_por_segundo():
    resultados = [
        _res(
            "a",
            "papo",
            "ok",
            meta={"eval_count": 100, "eval_duration": 2_000_000_000},  # 2s em ns
        )
    ]
    resumo = summarize(resultados)
    assert resumo["tokens_per_second"] == 50.0


def test_summarize_sem_dados_de_token():
    resumo = summarize([_res("a", "papo", "ok")])
    assert resumo["tokens_per_second"] is None
