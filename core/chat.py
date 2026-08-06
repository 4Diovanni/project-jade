"""Motor de conversa do Jade — persona viva, tools, roteador dual-model, RAG e memória.

Fluxo de cada mensagem:
1. **Humor**: o tom da mensagem ajusta o humor da Jade (`core.mood`).
2. **Tools**: se alguma tool aceita (ex.: "abra a calculadora"), ela age.
3. **Modelo**: RAG do Obsidian + escolha Qwen3 (local) vs Claude (nuvem).

O system prompt é montado a cada turno a partir da **persona**, do **humor** e do
**perfil do usuário** (`core.persona`). Ao encerrar/limpar a conversa, a Jade
extrai fatos duráveis sobre o usuário (`core.profile`).
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Iterator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from core.agent_router import route
from core.config import settings
from core.journal import ConversationJournal
from core.llm_engine import get_llm
from core.metrics import note, timed
from core.model_router import choose_route, cloud_available
from core.persona import build_system_prompt

_CONTEXT_TEMPLATE = (
    "Algumas anotações que talvez ajudem (use apenas se responderem à pergunta; "
    "NÃO as liste nem repita conversas passadas):\n\n{context}\n\n---\n"
    "Responda de forma objetiva SÓ a esta mensagem: {question}"
)


def _note_llm_usage(response) -> None:
    """Anota os contadores de token do provider, quando existirem.

    O Ollama devolve `eval_count`/`eval_duration` (tok/s real) e
    `prompt_eval_count` (tamanho do prompt em tokens de verdade). Providers que
    não devolvem esses campos simplesmente não são anotados.
    """
    meta = getattr(response, "response_metadata", None) or {}
    usage = {
        key: meta[key]
        for key in ("eval_count", "eval_duration", "prompt_eval_count")
        if key in meta
    }
    if usage:
        note(**usage)


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
        self._local_llm = get_llm()  # provider padrão (Ollama / Qwen3)
        self._grounded_llm = None  # mesmo modelo, temperatura baixa — criado sob demanda
        self._cloud_llm = None  # Claude — criado sob demanda
        self._use_rag = use_rag
        self._use_tools = use_tools
        self._use_router = use_router
        self._history: list = []  # só turnos; o system prompt é montado a cada envio
        enabled = settings.JOURNAL_ENABLED if use_journal is None else use_journal
        self._journal: ConversationJournal | None = ConversationJournal() if enabled else None
        #: qual cérebro respondeu o último turno: "tool" | "local" | "claude"
        self.last_model: str | None = None
        # Sincroniza o vault (arquivos novos/alterados) em background, desde a
        # criação da sessão — não só antes da 1ª busca do RAG. Quando a sessão
        # nasce bem antes da 1ª mensagem chegar (ex.: ao abrir a tela do chat,
        # que conecta o WebSocket na hora), o custo desaparece na prática.
        self._sync_thread: threading.Thread | None = None
        if use_rag:
            self._sync_thread = threading.Thread(target=self._sync_vault_safe, daemon=True)
            self._sync_thread.start()

    @property
    def journal_path(self):
        return self._journal.path if self._journal else None

    # ── LLMs ──
    def _get_grounded_llm(self):
        """Mesmo modelo local, mas com temperatura baixa — para quando há trechos
        do vault no prompt e a Jade deve citá-los, não improvisar em cima deles.
        Não custa VRAM extra: o Ollama serve o mesmo modelo já carregado."""
        if self._grounded_llm is None:
            self._grounded_llm = get_llm(temperature=settings.OLLAMA_GROUNDED_TEMPERATURE)
        return self._grounded_llm

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
                note(route="cloud")  # métricas usam "cloud"; last_model, "claude"
                return llm
        self.last_model = "local"
        note(route="local")
        # Com contexto do vault no prompt, vale mais fidelidade que criatividade.
        return self._get_grounded_llm() if has_context else self._local_llm

    # ── system prompt vivo ──
    def _system_message(self, mood_level: int) -> SystemMessage:
        from core.profile import load_profile

        prompt = build_system_prompt(mood_level=mood_level, profile_text=load_profile())
        return SystemMessage(content=prompt)

    # ── memória ──
    def _record(self, message: str, text: str) -> None:
        self._history.append(HumanMessage(content=message))
        self._history.append(AIMessage(content=text))
        self._history = self._history[-2 * settings.HISTORY_MAX_TURNS :]
        if self._journal is not None:
            with contextlib.suppress(Exception):
                self._journal.record(message, text)

    def _sync_vault_safe(self) -> None:
        """Alvo da thread de sincronização — roda em background, blindado.
        Exceções levantadas numa thread não propagam para quem dá join() nela,
        então a proteção precisa estar aqui dentro, não em _ensure_synced()."""
        with contextlib.suppress(Exception):
            from core.memory import sync_vault

            sync_vault()

    def _ensure_synced(self) -> None:
        """Espera a sincronização em background terminar — custo zero se ela
        já tiver terminado, espera o resto se ainda estiver rodando."""
        if self._sync_thread is not None:
            self._sync_thread.join()
            self._sync_thread = None

    def _retrieve_context(self, message: str) -> str:
        if not self._use_rag:
            return ""
        with timed("rag_sync"):
            self._ensure_synced()
        try:
            from core.memory import query_memory

            chunks = query_memory(message)
        except Exception:
            return ""
        return "\n\n".join(chunks)

    def _stream_impl(self, message: str) -> Iterator[str]:
        """Gerador que produz a resposta token a token: humor → tool → senão
        conversa (modelo + RAG). send() e stream() são os dois jeitos de
        consumir este gerador — inteiro de uma vez, ou aos pedaços."""
        # 1) O tom do usuário ajusta o humor da Jade (persistido).
        # `note` fica DENTRO do bloco: se `register()` falhar, `mood_level`
        # continua 0 e anotá-lo mesmo assim inventaria um delta de humor contra o
        # nível real de antes da mensagem. Sem anotação, quem lê sabe que não
        # houve medida. `timed("mood")` segue por fora, para cronometrar a
        # tentativa mesmo quando ela falha.
        mood_level = 0
        with timed("mood"), contextlib.suppress(Exception):
            from core.mood import register

            mood_level, _label = register(message)
            note(mood_level=mood_level)

        # 2) Roteamento para tools (as "mãos" da Jade).
        if self._use_tools:
            with timed("tool_route"):
                tool = route(message)
            if tool is not None:
                note(route="tool", tool=getattr(tool, "name", "?"))
                try:
                    with timed("tool_run"):
                        text = tool.run(message)
                except Exception as e:
                    text = f"Não consegui executar a ação: {e}"
                self.last_model = "tool"
                yield text
                with timed("rag_sync"):
                    self._ensure_synced()
                with timed("journal"):
                    self._record(message, text)
                return

        # 3) Conversa. Contexto do RAG é injetado só na chamada ao LLM.
        context = self._retrieve_context(message)
        llm = self._pick_llm(message, has_context=bool(context))

        user_turn = HumanMessage(content=message)
        if context:
            augmented = _CONTEXT_TEMPLATE.format(context=context, question=message)
            user_turn = HumanMessage(content=augmented)

        messages = [self._system_message(mood_level), *self._history, user_turn]
        full = None
        with timed("llm"):
            for chunk in llm.stream(messages):
                full = chunk if full is None else full + chunk
                if chunk.content:
                    yield chunk.content
        _note_llm_usage(full)
        text = full.content if full is not None else ""
        with timed("journal"):
            self._record(message, text)

    def send(self, message: str) -> str:
        """Processa uma mensagem e devolve a resposta inteira de uma vez.
        Use stream() para consumi-la aos pedaços."""
        return "".join(self._stream_impl(message))

    def stream(self, message: str) -> Iterator[str]:
        """Como send(), mas devolve a resposta aos pedaços conforme o LLM
        gera (ou um único pedaço, no caso de uma tool)."""
        return self._stream_impl(message)

    def _transcript(self) -> str:
        lines = []
        for m in self._history:
            role = "Você" if isinstance(m, HumanMessage) else "Jade"
            lines.append(f"{role}: {m.content}")
        return "\n".join(lines)

    @property
    def conversation_id(self) -> str | None:
        """Identificador da conversa atual (nome do arquivo, sem extensão)."""
        p = self.journal_path
        return p.stem if p is not None else None

    def rename(self, title: str) -> str | None:
        """Renomeia a conversa atual (título definido pelo usuário)."""
        if self._journal is None:
            return None
        return self._journal.set_title(title, custom=True)

    def title_task(self, min_turns: int = 2):
        """Devolve a tarefa que resume o assunto da conversa num título (ou None).

        Roda em segundo plano: envolve uma chamada ao LLM, que não pode bloquear
        a resposta ao usuário."""
        journal = self._journal
        if journal is None or not journal.needs_title(min_turns):
            return None
        transcript = self._transcript()
        llm = self._local_llm

        def _run() -> None:
            with contextlib.suppress(Exception):
                from core.journal import generate_title

                journal.apply_generated_title(generate_title(transcript, llm))

        return _run

    def detach(self):
        """Encerra a conversa: limpa a sessão **na hora** e devolve o trabalho
        pesado (título, RAG, perfil) para rodar em segundo plano.

        O `/reset` da API usa isto para responder instantaneamente — antes, o
        botão "novo chat" esperava chamadas ao LLM e à indexação."""
        journal = self._journal
        history_len = len(self._history)
        transcript = self._transcript()
        llm = self._local_llm

        self._history = []
        self.last_model = None
        if journal is not None:
            self._journal = ConversationJournal()

        def _finish() -> None:
            if journal is not None:
                if journal.needs_title():
                    with contextlib.suppress(Exception):
                        from core.journal import generate_title

                        journal.apply_generated_title(generate_title(transcript, llm))
                with contextlib.suppress(Exception):
                    journal.finalize()
            if settings.PROFILE_UPDATE_ENABLED and history_len >= 4:
                with contextlib.suppress(Exception):
                    from core.profile import update_from_conversation

                    update_from_conversation(transcript, llm)

        return _finish

    def learn_from_conversation(self) -> None:
        """Encerra a conversa: indexa no RAG (memória entre chats) e aprende sobre
        o usuário. Indexar só aqui evita o loop de a conversa se recuperar a si mesma."""
        if self._journal is not None:
            with contextlib.suppress(Exception):
                self._journal.finalize()
        if settings.PROFILE_UPDATE_ENABLED and len(self._history) >= 4:
            with contextlib.suppress(Exception):
                from core.profile import update_from_conversation

                update_from_conversation(self._transcript(), self._local_llm)

    def reset(self) -> None:
        """Encerra a conversa e limpa o histórico, de forma **síncrona**.

        Usado pela CLI. A API usa `detach()` para não travar a interface."""
        self.detach()()
