"""Roteador dual-model — escolhe entre llama3 (local) e Claude (nuvem).

Filosofia (visão do usuário, arquitetura §8):
- **llama3 (local, privado, barato):** conversa comum, tarefas simples e tudo
  que toca dados pessoais/memória (privacidade — não vai para a nuvem).
- **Claude (nuvem, mais capaz):** perguntas informativas/complexas de
  conhecimento geral (ex.: "como preparar tal receita").

A decisão é **determinística e testável** (heurística), na mesma linha do
roteador de tools; pode evoluir para um classificador por LLM no futuro.
"""

from __future__ import annotations

from core.config import settings

# Sinais de que a mensagem é informativa/complexa → vale escalar para o Claude.
_INFORMATIONAL = (
    "como ",
    "por que",
    "porque",
    "por quê",
    "o que é",
    "o que são",
    "o que e ",
    "explique",
    "explica",
    "me ensina",
    "ensina a",
    "receita",
    "passo a passo",
    "diferença",
    "diferenca",
    "qual a melhor",
    "quais as",
    "defina",
    "significa",
    "significado",
    "história",
    "historia",
    "resuma",
    "compare",
    "vantagens",
    "desvantagens",
    "como funciona",
    "me ajude a entender",
)

# A partir de quantas palavras a mensagem já é considerada "complexa".
_LONG_MESSAGE_WORDS = 18


def cloud_available() -> bool:
    """True se o roteamento para a nuvem está ligado E há chave configurada."""
    return settings.ROUTER_ENABLED and bool(settings.ANTHROPIC_API_KEY)


def looks_informational(message: str) -> bool:
    """Heurística: a mensagem parece uma pergunta de conhecimento/complexa?"""
    low = message.lower()
    if any(sig in low for sig in _INFORMATIONAL):
        return True
    return len(low.split()) >= _LONG_MESSAGE_WORDS


def choose_route(message: str, *, has_context: bool, cloud_available: bool) -> str:
    """Retorna 'local' (llama3) ou 'cloud' (Claude)."""
    if not cloud_available:
        return "local"
    if has_context:
        # Perguntas sobre dados pessoais (RAG) ficam locais — privacidade.
        return "local"
    return "cloud" if looks_informational(message) else "local"
