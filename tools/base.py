"""Contrato base de toda habilidade (tool) do Jade.

Toda nova capacidade do assistente é uma subclasse de `JadeTool`. O agente
descobre as tools pelo `name`/`description` e as executa via `run()`.
Ver a skill `add-jade-tool` para o passo a passo de criação.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class JadeTool(ABC):
    #: identificador curto, snake_case (ex.: "obsidian_search")
    name: str = ""
    #: descrição em linguagem natural — é o que o LLM lê para decidir usar a tool
    description: str = ""

    @abstractmethod
    def run(self, query: str) -> str:
        """Executa a habilidade e retorna um resultado em texto para o LLM."""
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover
        return f"<JadeTool {self.name!r}>"
