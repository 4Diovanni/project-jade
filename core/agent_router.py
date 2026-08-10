"""Roteador de agente: decide qual tool (se alguma) executa a mensagem.

Abordagem **determinística e confiável**: em vez de depender do tool-calling
nativo do LLM (instável no llama3), cada tool declara `trigger_hints` e valida
via `accepts()` se sabe executar o comando. Se nenhuma aceitar, a mensagem
segue para o chat normal (com RAG).

É a base sobre a qual o futuro **roteador dual-model** (Claude p/ complexo,
llama3 p/ simples) vai ser construído.

**Guarda de composição (Issue #43).** `accepts()` casa substring/regex na
frase inteira, sem entender posição ou subordinação — "antes de abrir a
calculadora, faça um texto sobre matemática" batia em "abrir" e a tool de
sistema executava, descartando o pedido principal sem o LLM nunca ver a
frase. Das opções levantadas na Issue (guarda de composição / árbitro via
LLM / score de confiança por tool), a guarda foi a escolhida: é a mais barata,
não muda a arquitetura determinística atual nem exige chamada extra de LLM
pro caso comum. Mensagens com sinais de subordinação ("antes de", "depois
de", "e também"...) pulam o roteamento por tool e caem direto no chat — lá o
LLM vê a frase inteira. Isso não tenta compor múltiplas ações automaticamente
(fica pro roteador dual-model futuro); só evita o descarte silencioso.
"""

from __future__ import annotations

from tools.base import JadeTool
from tools.registry import get_registered_tools

# Sinais de que a mensagem tem mais de uma instrução/oração (principal +
# secundária/condicional). Substring simples e barata, sem NLP: um comando
# direto como "abre a calculadora" não tem nenhum desses trechos.
_COMPOSITION_SIGNALS = (
    "antes de",
    "antes disso",
    "depois de",
    "depois disso",
    "e também",
    "e tambem",
    "mas primeiro",
    "mas antes",
    "mas depois",
    "e depois",
    "e por fim",
    "assim que",
    "logo depois",
    "logo em seguida",
)


def _has_composition_signal(message: str) -> bool:
    """True se a mensagem parece ter mais de uma instrução (ver Issue #43)."""
    low = message.lower()
    return any(signal in low for signal in _COMPOSITION_SIGNALS)


def route(message: str) -> JadeTool | None:
    """Retorna a primeira tool que aceita a mensagem, ou None (→ conversa).

    Mensagens compostas (ver `_has_composition_signal`) pulam o roteamento
    determinístico por tool e vão direto pro chat, onde o LLM vê a frase
    inteira em vez de ter o pedido principal descartado por um match de
    substring numa instrução secundária.
    """
    if _has_composition_signal(message):
        return None
    for tool in get_registered_tools():
        if tool.accepts(message):
            return tool
    return None
