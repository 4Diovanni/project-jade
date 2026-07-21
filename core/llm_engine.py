"""Factory do LLM — devolve o modelo de chat conforme o provider.

`get_llm()` usa o provider padrão (`JADE_LLM_PROVIDER`, normalmente Ollama);
`get_llm("anthropic")` devolve o Claude para o roteador dual-model.
Os imports de cada provider são preguiçosos, para que faltar a lib de um
provider que você não usa não quebre o import.
"""

from __future__ import annotations

import os

from core.config import settings


def get_llm(provider: str | None = None):
    """Retorna uma instância de chat LLM (LangChain) para o provider dado.

    Levanta um erro claro se a lib do provider não estiver instalada ou se
    faltar a chave de API necessária.
    """
    provider = (provider or settings.LLM_PROVIDER).lower()

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
        # NÃO passar temperature: modelos Opus 4.8 / Sonnet 5 rejeitam o parâmetro.
        return ChatAnthropic(
            model=settings.ANTHROPIC_MODEL,
            api_key=settings.ANTHROPIC_API_KEY,
            max_tokens=4096,
            timeout=60,
        )

    raise ValueError(f"Provider de LLM desconhecido: {provider!r}")
