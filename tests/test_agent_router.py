"""Testes do roteador de agente (core.agent_router) — puros, sem LLM/efeitos.

Além de cobrir a seleção de tools, este módulo tem o **guard de regressão** que
teria pego a `ObsidianSearchTool` morta: uma tool sem `trigger_hints` e sem
`accepts()` sobrescrito nunca é acionada pelo roteador (código morto).
"""

from core.agent_router import route
from tools.base import JadeTool
from tools.registry import get_registered_tools


def test_route_seleciona_tool_de_sistema():
    r = route("abra a calculadora")
    assert r is not None
    assert r.name == "system_control"


def test_route_none_para_conversa_comum():
    assert route("oi jade, tudo bem?") is None


def test_route_pergunta_pessoal_vai_para_o_chat_nao_para_tool():
    # A busca no vault (RAG) é feita no chat, não por uma tool. Perguntas sobre
    # anotações pessoais devem cair no chat (route → None), não ser interceptadas.
    assert route("o que eu anotei sobre o meu RPG?") is None


def test_route_nao_sequestra_comando_antes_de_composto():
    # Issue #43: "antes de" é condicional/secundário — o pedido principal
    # (o texto sobre matemática) não pode ser descartado silenciosamente por
    # um match cego em "abrir".
    msg = "antes de abrir a calculadora, faça um texto pra mim sobre matemática básica"
    assert route(msg) is None


def test_route_nao_sequestra_comando_e_depois_composto():
    msg = "faça um texto sobre matemática básica e depois abre a calculadora"
    assert route(msg) is None


def test_nenhuma_tool_registrada_e_inerte():
    """Regressão do #1: toda tool registrada precisa ser de fato acionável.

    Uma tool com `trigger_hints` vazio E sem `accepts()` próprio herda o
    `accepts` da base, que retorna sempre False → nunca é selecionada. Isso é
    exatamente o bug da antiga ObsidianSearchTool. Este teste falha se alguém
    registrar outra tool inerte."""
    for tool in get_registered_tools():
        tem_gatilhos = bool(tool.trigger_hints)
        accepts_proprio = type(tool).accepts is not JadeTool.accepts
        assert tem_gatilhos or accepts_proprio, (
            f"Tool {type(tool).__name__!r} é inerte: sem trigger_hints e sem "
            "accepts() sobrescrito, o roteador nunca a seleciona."
        )
