"""Tool do Obsidian — busca semântica nas notas do vault (RAG).

Habilidade central do Jade: responde perguntas sobre o que o usuário anotou.
"""

from __future__ import annotations

from core.memory import query_memory
from tools.base import JadeTool


class ObsidianSearchTool(JadeTool):
    name = "obsidian_search"
    description = (
        "Busca nas anotações do Obsidian do usuário para responder perguntas "
        "sobre o que ele registrou (reuniões, ideias, tarefas). "
        "Use quando a pergunta se referir a conhecimento pessoal do usuário."
    )

    def run(self, query: str) -> str:
        # TODO (Fase 2): formatar melhor os trechos recuperados para o LLM.
        trechos = query_memory(query)
        return "\n\n".join(trechos) if trechos else "Nada encontrado no vault."
