"""Factory do LLM — devolve o modelo conforme JADE_LLM_PROVIDER.

Fase 1: implementar o provider Ollama (local). Os demais ficam prontos para
serem ligados apenas preenchendo a chave no .env.
"""
from __future__ import annotations

from core.config import settings


def get_llm():
    """Retorna uma instância de chat LLM (LangChain) conforme o provider ativo."""
    provider = settings.LLM_PROVIDER.lower()

    if provider == "ollama":
        # TODO (Fase 1): from langchain_ollama import ChatOllama
        #   return ChatOllama(model=settings.OLLAMA_MODEL, base_url=settings.OLLAMA_BASE_URL)
        raise NotImplementedError("Fase 1: ligar ChatOllama aqui.")

    if provider == "openai":
        # TODO: from langchain_openai import ChatOpenAI
        raise NotImplementedError("Preencher OPENAI_API_KEY e ligar ChatOpenAI.")

    if provider == "anthropic":
        # TODO: from langchain_anthropic import ChatAnthropic
        raise NotImplementedError("Preencher ANTHROPIC_API_KEY e ligar ChatAnthropic.")

    raise ValueError(f"Provider de LLM desconhecido: {settings.LLM_PROVIDER!r}")
