"""Motor de conversa do Jade — chat com o LLM, persona, histórico, RAG e memória.

- RAG: a cada mensagem, recupera trechos das anotações do Obsidian e injeta
  como contexto (fallback silencioso para conversa normal).
- Memória: cada conversa é persistida como nota .md no vault (`core.journal`),
  virando memória de longo prazo do Jade.
"""

from __future__ import annotations

import contextlib

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from core.config import settings
from core.journal import ConversationJournal
from core.llm_engine import get_llm

SYSTEM_PROMPT = (
    "Você é o Jade, um assistente pessoal que roda localmente na máquina do usuário. "
    "Seu propósito é unificar as ferramentas e rotinas dele sob um só comando. "
    "Responda sempre em português do Brasil, de forma direta, prática e cordial. "
    "Seja conciso: nada de enrolação. "
    "Quando eu fornecer trechos das anotações do Obsidian do usuário como contexto, "
    "baseie sua resposta neles e cite a nota de origem quando útil. Se o contexto não "
    "contiver a resposta, diga isso com honestidade e responda com seu conhecimento "
    "geral, deixando claro que não veio das anotações."
)

_CONTEXT_TEMPLATE = (
    "Contexto recuperado das minhas anotações do Obsidian "
    "(use se for relevante):\n\n{context}\n\n---\nPergunta: {question}"
)


class ChatSession:
    """Mantém o histórico de uma conversa, consulta o RAG, fala com o LLM e
    registra a conversa no vault do Obsidian."""

    def __init__(self, *, use_rag: bool = True, use_journal: bool | None = None) -> None:
        self._llm = get_llm()
        self._use_rag = use_rag
        self._history: list = [SystemMessage(content=SYSTEM_PROMPT)]
        enabled = settings.JOURNAL_ENABLED if use_journal is None else use_journal
        self._journal: ConversationJournal | None = ConversationJournal() if enabled else None

    @property
    def journal_path(self):
        """Caminho da nota .md desta conversa (None até o primeiro turno)."""
        return self._journal.path if self._journal else None

    def _retrieve_context(self, message: str) -> str:
        """Busca trechos relevantes no RAG. Silencioso se indisponível."""
        if not self._use_rag:
            return ""
        try:
            from core.memory import query_memory

            chunks = query_memory(message)
        except Exception:
            # Sem índice, sem embeddings ou chromadb ausente → chat normal.
            return ""
        return "\n\n".join(chunks)

    def send(self, message: str) -> str:
        """Envia uma mensagem do usuário e retorna a resposta do Jade."""
        context = self._retrieve_context(message)

        # O histórico guarda a mensagem original (limpa); o contexto do RAG é
        # injetado apenas na chamada ao LLM, para não poluir a conversa.
        self._history.append(HumanMessage(content=message))
        if context:
            augmented = _CONTEXT_TEMPLATE.format(context=context, question=message)
            prompt_messages = [*self._history[:-1], HumanMessage(content=augmented)]
        else:
            prompt_messages = self._history

        response = self._llm.invoke(prompt_messages)
        text = response.content if hasattr(response, "content") else str(response)
        self._history.append(AIMessage(content=text))

        # Persistir a conversa nunca deve derrubar o chat.
        if self._journal is not None:
            with contextlib.suppress(Exception):
                self._journal.record(message, text)
        return text

    def reset(self) -> None:
        """Limpa o histórico e inicia uma nova nota de conversa."""
        self._history = [SystemMessage(content=SYSTEM_PROMPT)]
        if self._journal is not None:
            self._journal = ConversationJournal()
