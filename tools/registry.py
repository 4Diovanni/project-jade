"""Registro central de tools disponíveis para o agente.

Para expor uma nova habilidade ao Jade, importe-a e adicione uma instância
em `_TOOLS`. (Passo automatizado pela skill `add-jade-tool`.)
"""
from __future__ import annotations

from tools.base import JadeTool
from tools.obsidian_tool import ObsidianSearchTool

_TOOLS: list[JadeTool] = [
    ObsidianSearchTool(),
    # Registre novas tools aqui (Spotify, sistema, e-mail, calendário...).
]


def get_registered_tools() -> list[JadeTool]:
    """Retorna as tools ativas que o agente pode acionar."""
    return _TOOLS
