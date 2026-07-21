"""Contrato base de toda habilidade (tool) do Jade.

Toda nova capacidade do assistente é uma subclasse de `JadeTool`. O roteador
(`core/agent_router.py`) descobre as tools por `trigger_hints`/`accepts` e as
executa via `run()`. Ver a skill `add-jade-tool` para o passo a passo.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class JadeTool(ABC):
    #: identificador curto, snake_case (ex.: "system_control")
    name: str = ""
    #: descrição em linguagem natural — o que o LLM/roteador lê para entender a tool
    description: str = ""
    #: palavras-chave que sinalizam que a mensagem PODE ser para esta tool
    trigger_hints: tuple[str, ...] = ()

    def matches(self, message: str) -> bool:
        """True se algum gatilho aparece na mensagem (pré-filtro barato)."""
        low = message.lower()
        return any(hint in low for hint in self.trigger_hints)

    def accepts(self, message: str) -> bool:
        """True se a tool realmente sabe executar esta mensagem.

        Por padrão é igual a `matches`; tools que precisam de mais precisão
        (para evitar falsos positivos) devem sobrescrever este método.
        """
        return self.matches(message)

    @abstractmethod
    def run(self, query: str) -> str:
        """Executa a habilidade e retorna um resultado em texto para o usuário."""
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover
        return f"<JadeTool {self.name!r}>"
