"""Registro central de tools disponíveis para o agente.

Para expor uma nova habilidade ao Jade, importe-a e adicione uma instância
em `_TOOLS`. (Passo automatizado pela skill `add-jade-tool`.)
"""

from __future__ import annotations

from tools.base import JadeTool
from tools.obsidian_tool import ObsidianSearchTool
from tools.system_tool import SystemControlTool

_TOOLS: list[JadeTool] = [
    SystemControlTool(),
    ObsidianSearchTool(),
    # Registre novas tools aqui (Spotify, e-mail, calendário...).
]


def get_registered_tools() -> list[JadeTool]:
    """Retorna as tools ativas que o agente pode acionar."""
    return _TOOLS
