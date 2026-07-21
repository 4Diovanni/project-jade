"""Motor de conversa do Jade — tools, LLM, persona, histórico, RAG e memória.

Fluxo de cada mensagem:
1. **Roteamento**: se alguma tool aceita a mensagem (ex.: "abra a calculadora"),
   ela é executada e sua resposta é retornada (as "mãos" do Jade).
2. Caso contrário, **chat com RAG**: recupera trechos do Obsidian e conversa.

Toda troca é registrada como nota .md no vault (`core.journal`).
"""

from __future__ import annotations

import contextlib

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from core.agent_router import route
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
    """Roteia para tools, consulta o RAG, fala com o LLM e registra a conversa."""

    def __init__(
        self, *, use_rag: bool = True, use_tools: bool = True, use_journal: bool | None = None
    ) -> None:
        self._llm = get_llm()
        self._use_rag = use_rag
        self._use_tools = use_tools
        self._history: list = [SystemMessage(content=SYSTEM_PROMPT)]
        enabled = settings.JOURNAL_ENABLED if use_journal is None else use_journal
        self._journal: ConversationJournal | None = ConversationJournal() if enabled else None

    @property
    def journal_path(self):
        """Caminho da nota .md desta conversa (None até o primeiro turno)."""
        return self._journal.path if self._journal else None

    def _record(self, message: str, text: str) -> None:
        """Persiste o turno no diário (nunca derruba o chat)."""
        self._history.append(HumanMessage(content=message))
        self._history.append(AIMessage(content=text))
        if self._journal is not None:
            with contextlib.suppress(Exception):
                self._journal.record(message, text)

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
        """Processa uma mensagem: primeiro tenta uma tool, senão conversa (RAG)."""
        # 1) Roteamento para tools (as "mãos" do Jade).
        if self._use_tools:
            tool = route(message)
            if tool is not None:
                try:
                    text = tool.run(message)
                except Exception as e:
                    text = f"Não consegui executar a ação: {e}"
                self._record(message, text)
                return text

        # 2) Chat com RAG. O contexto é injetado só na chamada ao LLM.
        context = self._retrieve_context(message)
        history_for_llm = [*self._history, HumanMessage(content=message)]
        if context:
            augmented = _CONTEXT_TEMPLATE.format(context=context, question=message)
            history_for_llm = [*self._history, HumanMessage(content=augmented)]

        response = self._llm.invoke(history_for_llm)
        text = response.content if hasattr(response, "content") else str(response)
        self._record(message, text)
        return text

    def reset(self) -> None:
        """Limpa o histórico e inicia uma nova nota de conversa."""
        self._history = [SystemMessage(content=SYSTEM_PROMPT)]
        if self._journal is not None:
            self._journal = ConversationJournal()
