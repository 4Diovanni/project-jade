"""Roteador de agente: decide qual tool (se alguma) executa a mensagem.

Abordagem **determinística e confiável**: em vez de depender do tool-calling
nativo do LLM (instável no llama3), cada tool declara `trigger_hints` e valida
via `accepts()` se sabe executar o comando. Se nenhuma aceitar, a mensagem
segue para o chat normal (com RAG).

É a base sobre a qual o futuro **roteador dual-model** (Claude p/ complexo,
llama3 p/ simples) vai ser construído.
"""

from __future__ import annotations

from tools.base import JadeTool
from tools.registry import get_registered_tools


def route(message: str) -> JadeTool | None:
    """Retorna a primeira tool que aceita a mensagem, ou None (→ conversa)."""
    for tool in get_registered_tools():
        if tool.accepts(message):
            return tool
    return None
