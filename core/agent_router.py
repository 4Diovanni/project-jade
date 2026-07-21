"""Roteador de agente: dado um comando, o LLM decide qual tool acionar.

É o coração *agentic* do Jade (Fase 2). Monta o agente LangChain a partir das
tools registradas em `tools/registry.py`.

Na Fase 1, o Jade apenas conversa — sem tools — via `core.chat.ChatSession`.
Este módulo passa a ser usado quando as tools estiverem prontas (Fase 2+).
"""

from __future__ import annotations

from core.llm_engine import get_llm
from tools.registry import get_registered_tools


def build_agent():
    """Constrói o agente com function-calling sobre as tools registradas.

    TODO (Fase 1/2): usar create_tool_calling_agent / AgentExecutor do LangChain
    envolvendo `get_registered_tools()` e `get_llm()`.
    """
    llm = get_llm()  # noqa: F841 (usado quando o agente for implementado)
    tools = get_registered_tools()  # noqa: F841
    raise NotImplementedError("Fase 1: montar o AgentExecutor do LangChain.")


def handle_message(message: str) -> str:
    """Ponto único de entrada de uma mensagem do usuário → resposta do Jade."""
    agent = build_agent()
    return agent.invoke({"input": message})["output"]
