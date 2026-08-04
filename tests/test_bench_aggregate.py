"""Testes da avaliação e agregação do benchmark (bench.aggregate).

Funções puras: recebem casos e turnos sintéticos. Nada de LLM, nada de I/O.
"""

from bench.aggregate import Failure, Result, evaluate, percentile, summarize
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
    assert falhas[0].dimension == "route"
    assert "esperava 'cloud', veio 'local'" in falhas[0].message


def test_falha_se_formata_com_a_dimensao_na_frente():
    """O texto do relatório continua sendo `dimensão: motivo`."""
    _status, falhas = evaluate(_caso({"route": "cloud"}), _turno({"route": "local"}), mood_before=0)
    assert str(falhas[0]).startswith("route: ")


def test_nome_da_tool_e_conferido():
    status, falhas = evaluate(
        _caso({"route": "tool", "tool": "system_control"}),
        _turno({"route": "tool", "tool": "outra"}),
        mood_before=0,
    )
    assert status == "falhou"
    assert [f.dimension for f in falhas] == ["tool"]


def test_sources_include_exige_todas_as_fontes():
    caso = _caso({"sources_include": ["CLAUDE.md", "README.md"]})
    status, falhas = evaluate(caso, _turno({"sources": ["CLAUDE.md"]}), mood_before=0)
    assert status == "falhou"
    assert falhas[0].dimension == "sources_include"
    assert "README.md" in falhas[0].message


def test_sources_include_passa_quando_todas_presentes():
    caso = _caso({"sources_include": ["CLAUDE.md"]})
    status, _ = evaluate(caso, _turno({"sources": ["outra.md", "CLAUDE.md"]}), mood_before=0)
    assert status == "ok"


def test_context_none_falha_quando_veio_contexto():
    status, falhas = evaluate(_caso({"context": "none"}), _turno({"chunks": 6}), mood_before=0)
    assert status == "falhou"
    assert falhas[0].dimension == "context"


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
    assert falhas[0].dimension == "mood_delta"


def test_varias_falhas_sao_acumuladas():
    caso = _caso({"route": "cloud", "context": "none"})
    status, falhas = evaluate(caso, _turno({"route": "local", "chunks": 6}), mood_before=0)
    assert status == "falhou"
    assert {f.dimension for f in falhas} == {"route", "context"}


# ── percentile ──
def test_percentile_mediana():
    assert percentile([1.0, 2.0, 3.0], 50) == 2.0


def test_percentile_lista_vazia():
    assert percentile([], 50) == 0.0


def test_percentile_p95_pega_o_topo():
    assert percentile([1.0, 2.0, 3.0, 100.0], 95) == 100.0


# ── summarize ──
def _res(cid, categoria, status, steps=None, meta=None, expect=None, falhas=()):
    """Result sintético. `expect` é o que o caso declarou; `falhas`, as dimensões
    em que ele errou — é essa combinação que as métricas por dimensão leem."""
    meta = dict(meta or {})
    meta["_expect"] = dict(expect or {})
    return Result(
        case_id=cid,
        category=categoria,
        status=status,
        failures=[Failure(d, "motivo") for d in falhas],
        steps=steps or {"total": 1.0},
        meta=meta,
    )


def test_summarize_acerto_de_rota():
    resultados = [
        _res("a", "tools", "ok", expect={"route": "tool"}),
        _res("b", "tools", "falhou", expect={"route": "tool"}, falhas=["route"]),
        _res("c", "papo", "ok", expect={"route": "local"}),
    ]
    resumo = summarize(resultados)
    assert resumo["route_accuracy"] == 2 / 3
    assert resumo["by_category"]["tools"]["pass_rate"] == 0.5
    assert resumo["by_category"]["papo"]["pass_rate"] == 1.0


def test_summarize_ignora_pulados_na_acuracia():
    resultados = [
        _res("a", "tools", "ok", expect={"route": "tool"}),
        _res("b", "conhecimento", "pulado", expect={"route": "cloud"}),
    ]
    resumo = summarize(resultados)
    assert resumo["route_accuracy"] == 1.0
    assert resumo["skipped"] == 1


# ── métricas por dimensão: cada uma conta SÓ a sua própria falha ──
def test_route_accuracy_ignora_falha_de_outra_dimensao():
    """A regressão que motivou esta correção: um caso de `papo` que roteia certo
    mas puxa contexto indevido é **acerto de rota** e **erro de contexto**.

    Antes, `route_accuracy` era a taxa de aprovação integral, e esses casos
    apareciam como 0% de roteamento — o relatório acusava um defeito que não
    existia."""
    resultados = [
        _res(
            "papo",
            "papo",
            "falhou",
            expect={"route": "local", "context": "none"},
            falhas=["context"],
        )
    ]
    resumo = summarize(resultados)
    assert resumo["route_accuracy"] == 1.0
    assert resumo["context_precision"] == 0.0
    assert resumo["pass_rate"] == 0.0


def test_recall_at_k_ignora_falha_de_rota_no_mesmo_caso():
    resultados = [
        _res(
            "mem",
            "memoria",
            "falhou",
            expect={"route": "local", "sources_include": ["CLAUDE.md"]},
            falhas=["route"],
        )
    ]
    resumo = summarize(resultados)
    assert resumo["recall_at_k"] == 1.0
    assert resumo["route_accuracy"] == 0.0


def test_context_precision_cobre_so_os_casos_none():
    """`context: any` mede cobertura, não precisão — não pode entrar no
    denominador da precisão de contexto."""
    resultados = [
        _res("p1", "papo", "falhou", expect={"context": "none"}, falhas=["context"]),
        _res("p2", "papo", "falhou", expect={"context": "none"}, falhas=["context"]),
        _res("m1", "memoria", "ok", expect={"context": "any"}),
        _res("m2", "memoria", "ok", expect={"context": "any"}),
    ]
    resumo = summarize(resultados)
    # Só os dois `none`, ambos falhos → 0%. Misturando os `any` daria 50%.
    assert resumo["context_precision"] == 0.0


def test_metricas_sao_none_quando_ninguem_declara_a_dimensao():
    resultados = [_res("a", "humor", "ok", expect={"mood_delta": "neutral"})]
    resumo = summarize(resultados)
    assert resumo["route_accuracy"] is None
    assert resumo["recall_at_k"] is None
    assert resumo["context_precision"] is None


def test_pass_rate_continua_sendo_aprovacao_integral():
    resultados = [
        _res("a", "tools", "ok", expect={"route": "tool"}),
        _res(
            "b", "tools", "falhou", expect={"route": "tool", "context": "none"}, falhas=["context"]
        ),
    ]
    resumo = summarize(resultados)
    assert resumo["pass_rate"] == 0.5
    assert resumo["route_accuracy"] == 1.0


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


def test_summarize_sem_dados_de_prompt_tokens():
    resumo = summarize([_res("a", "papo", "ok")])
    assert resumo["prompt_tokens"] is None


def test_summarize_prompt_tokens_p50_p95():
    resultados = [
        _res("a", "papo", "ok", meta={"prompt_eval_count": 10}),
        _res("b", "papo", "ok", meta={"prompt_eval_count": 50}),
    ]
    resumo = summarize(resultados)
    # Percentil por nearest-rank: com n=2, o p50 é o menor e o p95 é o maior.
    assert resumo["prompt_tokens"]["p50"] == 10.0
    assert resumo["prompt_tokens"]["p95"] == 50.0
