"""Memória do Jade: histórico (SQLite) + RAG do Obsidian (ChromaDB).

Usado pela skill `sync-obsidian-rag` para (re)indexar o vault.
"""
from __future__ import annotations

from pathlib import Path

from core.config import settings


def iter_vault_notes():
    """Percorre o vault do Obsidian retornando os caminhos de notas .md,
    pulando as pastas de `settings.VAULT_IGNORE` (código, .obsidian, etc.)."""
    vault = settings.OBSIDIAN_VAULT_PATH
    for md in vault.rglob("*.md"):
        parts = set(md.relative_to(vault).parts)
        if parts & settings.VAULT_IGNORE:
            continue
        yield md


def reindex_vault() -> int:
    """(Re)indexa as notas do Obsidian no ChromaDB. Retorna nº de notas indexadas.

    TODO (Fase 2):
      1. carregar/chunkar cada nota de `iter_vault_notes()`;
      2. gerar embeddings (sentence-transformers ou embeddings do provider);
      3. upsert na coleção Chroma em `settings.CHROMA_DB_PATH`.
    """
    notes = list(iter_vault_notes())
    raise NotImplementedError(
        f"Fase 2: indexar {len(notes)} notas do vault no ChromaDB."
    )


def query_memory(question: str, k: int = 4) -> list[str]:
    """Busca semântica no ChromaDB. Retorna os trechos mais relevantes."""
    raise NotImplementedError("Fase 2: consulta RAG no ChromaDB.")
