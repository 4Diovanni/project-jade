"""Memória do Jade: RAG do Obsidian (ChromaDB + embeddings via Ollama).

Os imports pesados (chromadb, langchain) são preguiçosos: importar este módulo
não exige as libs nem sobe o banco — só quando o RAG é de fato usado.
Usado pela skill `sync-obsidian-rag`.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from core.config import settings

# Caches de módulo (inicialização preguiçosa).
_embedder = None
_collection = None


def iter_vault_notes(vault: Path | None = None):
    """Percorre o vault do Obsidian retornando os caminhos de notas .md,
    pulando as pastas de `settings.VAULT_IGNORE` (código, .obsidian, etc.)."""
    vault = (vault or settings.OBSIDIAN_VAULT_PATH).resolve()
    for md in vault.rglob("*.md"):
        parts = set(md.relative_to(vault).parts)
        if parts & settings.VAULT_IGNORE:
            continue
        yield md


def chunk_text(text: str) -> list[str]:
    """Divide um texto em chunks para indexação."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.RAG_CHUNK_SIZE,
        chunk_overlap=settings.RAG_CHUNK_OVERLAP,
    )
    return [c for c in splitter.split_text(text) if c.strip()]


def _get_embedder():
    global _embedder
    if _embedder is None:
        from langchain_ollama import OllamaEmbeddings

        _embedder = OllamaEmbeddings(
            model=settings.OLLAMA_EMBED_MODEL,
            base_url=settings.OLLAMA_BASE_URL,
        )
    return _embedder


def _get_collection():
    global _collection
    if _collection is None:
        import chromadb

        client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
        _collection = client.get_or_create_collection(
            name=settings.CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def _reset_collection() -> None:
    """Apaga a coleção para uma reindexação limpa (idempotente)."""
    global _collection
    import chromadb

    client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
    with contextlib.suppress(Exception):  # coleção pode ainda não existir
        client.delete_collection(settings.CHROMA_COLLECTION)
    _collection = None


def reindex_vault() -> int:
    """(Re)indexa as notas do Obsidian no ChromaDB. Retorna nº de notas indexadas.

    Full reindex: a coleção é recriada do zero para não deixar chunks órfãos.
    """
    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict] = []
    n_notes = 0

    for md in iter_vault_notes():
        text = md.read_text(encoding="utf-8", errors="ignore")
        if not text.strip():
            continue
        chunks = chunk_text(text)
        if not chunks:
            continue
        n_notes += 1
        rel = str(md.relative_to(settings.OBSIDIAN_VAULT_PATH))
        for i, chunk in enumerate(chunks):
            ids.append(f"{rel}::{i}")
            docs.append(chunk)
            metas.append({"source": rel, "chunk": i})

    if not docs:
        return 0

    embedder = _get_embedder()
    embeddings = embedder.embed_documents(docs)

    _reset_collection()
    collection = _get_collection()

    batch = 128  # add em lotes para não estourar a requisição
    for start in range(0, len(docs), batch):
        end = start + batch
        collection.add(
            ids=ids[start:end],
            documents=docs[start:end],
            embeddings=embeddings[start:end],
            metadatas=metas[start:end],
        )
    return n_notes


def query_memory(question: str, k: int | None = None) -> list[str]:
    """Busca semântica no ChromaDB. Retorna os trechos mais relevantes
    (formatados com a nota de origem). Lista vazia se nada foi indexado."""
    k = k or settings.RAG_TOP_K
    collection = _get_collection()
    if collection.count() == 0:
        return []

    q_emb = _get_embedder().embed_query(question)
    res = collection.query(query_embeddings=[q_emb], n_results=k)

    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]

    out: list[str] = []
    for doc, meta in zip(docs, metas, strict=False):
        source = (meta or {}).get("source", "?")
        out.append(f"[{source}]\n{doc}")
    return out
