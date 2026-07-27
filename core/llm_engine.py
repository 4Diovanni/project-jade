"""Factory do LLM — devolve o modelo de chat conforme o provider.

`get_llm()` usa o provider padrão (`JADE_LLM_PROVIDER`, normalmente Ollama);
`get_llm("anthropic")` devolve o Claude para o roteador dual-model.
Os imports de cada provider são preguiçosos, para que faltar a lib de um
provider que você não usa não quebre o import.
"""

from __future__ import annotations

import os

from core.config import settings


def get_llm(provider: str | None = None, *, temperature: float | None = None):
    """Retorna uma instância de chat LLM (LangChain) para o provider dado.

    `temperature` sobrescreve o padrão do provider — use uma temperatura baixa
    (`settings.OLLAMA_GROUNDED_TEMPERATURE`) quando a resposta precisa se ancorar
    em fatos do vault em vez de improvisar.

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
            temperature=settings.OLLAMA_TEMPERATURE if temperature is None else temperature,
            # Sem num_ctx explícito o Ollama usa o default dele (2k–4k) e corta
            # o começo do prompt em silêncio — some a persona e/ou o RAG.
            num_ctx=settings.OLLAMA_NUM_CTX,
            # `reasoning=False` vira `think: false` na API do Ollama e desliga o
            # modo thinking do Qwen3. Precisa ser False explícito: com None o
            # Qwen3 pensa por padrão e vaza as tags <think> na resposta.
            # Modelos sem thinking (llama3) ignoram o parâmetro sem erro.
            reasoning=settings.OLLAMA_THINKING,
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
