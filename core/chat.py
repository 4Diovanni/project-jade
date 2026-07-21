"""Motor de conversa da Fase 1 — chat direto com o LLM, com persona e histórico.

Ainda SEM tools: a decisão de qual ferramenta usar (roteamento agentic) chega
na Fase 2, em `core/agent_router.py`. Aqui o Jade apenas conversa.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from core.llm_engine import get_llm

SYSTEM_PROMPT = (
    "Você é o Jade, um assistente pessoal que roda localmente na máquina do usuário. "
    "Seu propósito é unificar as ferramentas e rotinas dele sob um só comando. "
    "Responda sempre em português do Brasil, de forma direta, prática e cordial. "
    "Seja conciso: nada de enrolação. Se não souber algo ou ainda não tiver a "
    "ferramenta para fazer, diga isso com honestidade. "
    "Estamos na Fase 1 (só conversa); acesso ao Obsidian, WhatsApp, voz e sistema "
    "chega nas próximas fases."
)


class ChatSession:
    """Mantém o histórico de uma conversa e fala com o LLM."""

    def __init__(self) -> None:
        self._llm = get_llm()
        self._history: list = [SystemMessage(content=SYSTEM_PROMPT)]

    def send(self, message: str) -> str:
        """Envia uma mensagem do usuário e retorna a resposta do Jade."""
        self._history.append(HumanMessage(content=message))
        response = self._llm.invoke(self._history)
        text = response.content if hasattr(response, "content") else str(response)
        self._history.append(AIMessage(content=text))
        return text

    def reset(self) -> None:
        """Limpa o histórico, mantendo apenas a persona."""
        self._history = [SystemMessage(content=SYSTEM_PROMPT)]
