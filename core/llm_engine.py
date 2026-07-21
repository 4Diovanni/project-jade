"""Factory do LLM — devolve o modelo de chat conforme JADE_LLM_PROVIDER.

Os imports de cada provider são feitos de forma preguiçosa (dentro da função),
para que faltar a lib de um provider que você não usa não quebre o import.
"""

from __future__ import annotations

import os

from core.config import settings


def get_llm():
    """Retorna uma instância de chat LLM (LangChain) conforme o provider ativo.

    Levanta um erro claro se a lib do provider não estiver instalada ou se
    faltar a chave de API necessária.
    """
    provider = settings.LLM_PROVIDER.lower()

    if provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("Falta a lib do Ollama. Rode: pip install langchain-ollama") from e
        return ChatOllama(
            model=settings.OLLAMA_MODEL,
            base_url=settings.OLLAMA_BASE_URL,
            temperature=0.7,
        )

    if provider == "openai":
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("Defina OPENAI_API_KEY no .env para usar o provider openai.")
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("Rode: pip install langchain-openai") from e
        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            api_key=settings.OPENAI_API_KEY,
            temperature=0.7,
        )

    if provider == "anthropic":
        if not settings.ANTHROPIC_API_KEY:
            raise RuntimeError("Defina ANTHROPIC_API_KEY no .env para usar o provider anthropic.")
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("Rode: pip install langchain-anthropic") from e
        return ChatAnthropic(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5"),
            api_key=settings.ANTHROPIC_API_KEY,
            temperature=0.7,
        )

    raise ValueError(f"Provider de LLM desconhecido: {settings.LLM_PROVIDER!r}")
