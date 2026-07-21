"""Motor de conversa do Jade — persona viva, tools, roteador dual-model, RAG e memória.

Fluxo de cada mensagem:
1. **Humor**: o tom da mensagem ajusta o humor da Jade (`core.mood`).
2. **Tools**: se alguma tool aceita (ex.: "abra a calculadora"), ela age.
3. **Modelo**: RAG do Obsidian + escolha llama3 (local) vs Claude (nuvem).

O system prompt é montado a cada turno a partir da **persona**, do **humor** e do
**perfil do usuário** (`core.persona`). Ao encerrar/limpar a conversa, a Jade
extrai fatos duráveis sobre o usuário (`core.profile`).
"""

from __future__ import annotations

import contextlib

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from core.agent_router import route
from core.config import settings
from core.journal import ConversationJournal
from core.llm_engine import get_llm
from core.model_router import choose_route, cloud_available
from core.persona import build_system_prompt

_CONTEXT_TEMPLATE = (
    "Contexto recuperado das minhas anotações do Obsidian "
    "(use se for relevante):\n\n{context}\n\n---\nPergunta: {question}"
)


class ChatSession:
    """Persona viva: humor, tools, roteador de modelos, RAG e memória em Obsidian."""

    def __init__(
        self,
        *,
        use_rag: bool = True,
        use_tools: bool = True,
        use_router: bool = True,
        use_journal: bool | None = None,
    ) -> None:
        self._local_llm = get_llm()  # provider padrão (Ollama / llama3)
        self._cloud_llm = None  # Claude — criado sob demanda
        self._use_rag = use_rag
        self._use_tools = use_tools
        self._use_router = use_router
        self._history: list = []  # só turnos; o system prompt é montado a cada envio
        enabled = settings.JOURNAL_ENABLED if use_journal is None else use_journal
        self._journal: ConversationJournal | None = ConversationJournal() if enabled else None
        #: qual cérebro respondeu o último turno: "tool" | "llama3" | "claude"
        self.last_model: str | None = None

    @property
    def journal_path(self):
        return self._journal.path if self._journal else None

    # ── LLMs ──
    def _get_cloud_llm(self):
        if self._cloud_llm is None:
            self._cloud_llm = get_llm(settings.CLOUD_PROVIDER)
        return self._cloud_llm

    def _try_cloud_llm(self):
        try:
            return self._get_cloud_llm()
        except Exception:
            return None

    def _pick_llm(self, message: str, has_context: bool):
        can_cloud = self._use_router and cloud_available()
        r = choose_route(message, has_context=has_context, cloud_available=can_cloud)
        if r == "cloud":
            llm = self._try_cloud_llm()
            if llm is not None:
                self.last_model = "claude"
                return llm
        self.last_model = "llama3"
        return self._local_llm

    # ── system prompt vivo ──
    def _system_message(self, mood_level: int) -> SystemMessage:
        from core.profile import load_profile

        prompt = build_system_prompt(mood_level=mood_level, profile_text=load_profile())
        return SystemMessage(content=prompt)

    # ── memória ──
    def _record(self, message: str, text: str) -> None:
        self._history.append(HumanMessage(content=message))
        self._history.append(AIMessage(content=text))
        if self._journal is not None:
            with contextlib.suppress(Exception):
                self._journal.record(message, text)

    def _retrieve_context(self, message: str) -> str:
        if not self._use_rag:
            return ""
        try:
            from core.memory import query_memory

            chunks = query_memory(message)
        except Exception:
            return ""
        return "\n\n".join(chunks)

    def send(self, message: str) -> str:
        """Processa uma mensagem: humor → tool → senão conversa (modelo + RAG)."""
        # 1) O tom do usuário ajusta o humor da Jade (persistido).
        mood_level = 0
        with contextlib.suppress(Exception):
            from core.mood import register

            mood_level, _label = register(message)

        # 2) Roteamento para tools (as "mãos" da Jade).
        if self._use_tools:
            tool = route(message)
            if tool is not None:
                try:
                    text = tool.run(message)
                except Exception as e:
                    text = f"Não consegui executar a ação: {e}"
                self.last_model = "tool"
                self._record(message, text)
                return text

        # 3) Conversa. Contexto do RAG é injetado só na chamada ao LLM.
        context = self._retrieve_context(message)
        llm = self._pick_llm(message, has_context=bool(context))

        user_turn = HumanMessage(content=message)
        if context:
            augmented = _CONTEXT_TEMPLATE.format(context=context, question=message)
            user_turn = HumanMessage(content=augmented)

        messages = [self._system_message(mood_level), *self._history, user_turn]
        response = llm.invoke(messages)
        text = response.content if hasattr(response, "content") else str(response)
        self._record(message, text)
        return text

    def _transcript(self) -> str:
        lines = []
        for m in self._history:
            role = "Você" if isinstance(m, HumanMessage) else "Jade"
            lines.append(f"{role}: {m.content}")
        return "\n".join(lines)

    def learn_from_conversation(self) -> None:
        """Extrai fatos duráveis sobre o usuário desta conversa (best-effort)."""
        if not settings.PROFILE_UPDATE_ENABLED or len(self._history) < 4:
            return
        with contextlib.suppress(Exception):
            from core.profile import update_from_conversation

            update_from_conversation(self._transcript(), self._local_llm)

    def reset(self) -> None:
        """Aprende com a conversa, limpa o histórico e inicia uma nova nota."""
        self.learn_from_conversation()
        self._history = []
        self.last_model = None
        if self._journal is not None:
            self._journal = ConversationJournal()
