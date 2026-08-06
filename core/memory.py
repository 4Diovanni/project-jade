"""Memória do Jade: RAG do Obsidian (ChromaDB + embeddings via Ollama).

Os imports pesados (chromadb, langchain) são preguiçosos: importar este módulo
não exige as libs nem sobe o banco — só quando o RAG é de fato usado.
Usado pela skill `sync-obsidian-rag`.
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

from core.config import settings
from core.metrics import note, timed


def _meta_notes() -> set[str]:
    """Notas internas da Jade (humor/perfil/personalidade/hub) — fora do RAG."""
    return {
        settings.PERSONALITY_NOTE,
        settings.MOOD_NOTE,
        settings.PROFILE_NOTE,
        "Jade — Memória.md",
    }


# Caches de módulo (inicialização preguiçosa).
_embedder = None
_collection = None


def iter_vault_notes(vault: Path | None = None):
    """Percorre o vault retornando os arquivos de texto (.md/.txt) a indexar,
    pulando `settings.VAULT_IGNORE` e as notas internas da Jade."""
    vault = (vault or settings.OBSIDIAN_VAULT_PATH).resolve()
    meta = _meta_notes()
    for pattern in ("*.md", "*.txt"):
        for f in vault.rglob(pattern):
            parts = set(f.relative_to(vault).parts)
            if parts & settings.VAULT_IGNORE:
                continue
            if f.name in meta:
                continue
            yield f


def chunk_text(text: str) -> list[str]:
    """Divide um texto em chunks para indexação."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.RAG_CHUNK_SIZE,
        chunk_overlap=settings.RAG_CHUNK_OVERLAP,
    )
    return [c for c in splitter.split_text(text) if c.strip()]


def _filter_by_distance(
    docs: list[str], metas: list[dict], distances: list[float]
) -> list[tuple[str, dict]]:
    """Descarta trechos com distância maior que RAG_MAX_DISTANCE. Se o Chroma não
    devolver distâncias (resposta sem a chave, ou lista vazia), mantém tudo —
    nunca descarta contexto por um bug silencioso de parsing."""
    if not distances:
        return list(zip(docs, metas, strict=False))
    return [
        (doc, meta)
        for doc, meta, dist in zip(docs, metas, distances, strict=False)
        if dist <= settings.RAG_MAX_DISTANCE
    ]


def _merge_overlap(a: str, b: str) -> str:
    """Funde dois textos cortando o maior sufixo de `a` que é também prefixo de
    `b`. Não assume tamanho fixo de overlap: o `RecursiveCharacterTextSplitter`
    usado em `chunk_text()` respeita separadores e não garante
    `RAG_CHUNK_OVERLAP` caracteres exatos entre chunks vizinhos."""
    limit = min(len(a), len(b))
    for size in range(limit, 0, -1):
        if a[-size:] == b[:size]:
            return a + b[size:]
    return a + b


def _flush_run(
    run: list[tuple[int, str, int]], source: str, blocks: list[tuple[int, str, str]]
) -> None:
    """Funde um run de chunks consecutivos (já ordenados por índice) num único
    bloco, e o acrescenta a `blocks` na melhor (menor) posição de relevância
    do run — para não bagunçar a ordenação original do Chroma."""
    if not run:
        return
    best_pos = min(pos for pos, _doc, _idx in run)
    text = run[0][1]
    for _pos, doc, _idx in run[1:]:
        text = _merge_overlap(text, doc)
    blocks.append((best_pos, source, text))


def _merge_adjacent_chunks(entries: list[tuple[str, dict]]) -> list[str]:
    """Funde chunks consecutivos (`chunk: i`, `chunk: i+1`) da MESMA fonte num
    só bloco `[fonte]\\ntexto`, cortando o overlap. `entries` são pares
    (doc, meta) na ordem de relevância devolvida pelo Chroma — uma ordem que
    NÃO segue o índice do chunk (o chunk `i+1` pode aparecer antes do chunk
    `i`, ou uma cadeia de 3+ chunks pode chegar embaralhada). Por isso
    agrupamos por fonte e ordenamos por `chunk` ANTES de fundir runs
    consecutivos, em vez de só comparar com o item anterior da lista bruta.
    Cada bloco fundido herda a melhor posição de relevância entre os chunks
    que o compõem, para preservar a ordem de relevância geral na saída.
    Chunks não-adjacentes, de fontes diferentes, ou sem índice de chunk nos
    metadados não se fundem."""
    groups: dict[str, list[tuple[int, str, int | None]]] = {}
    for pos, (doc, meta) in enumerate(entries):
        source = (meta or {}).get("source", "?")
        raw_idx = (meta or {}).get("chunk")
        chunk_idx = raw_idx if isinstance(raw_idx, int) else None
        groups.setdefault(source, []).append((pos, doc, chunk_idx))

    blocks: list[tuple[int, str, str]] = []  # (melhor posição de relevância, fonte, texto)

    for source, items in groups.items():
        com_indice = sorted((it for it in items if it[2] is not None), key=lambda it: it[2])
        sem_indice = [it for it in items if it[2] is None]

        run: list[tuple[int, str, int]] = []
        for it in com_indice:
            if run and it[2] == run[-1][2] + 1:
                run.append(it)
            else:
                _flush_run(run, source, blocks)
                run = [it]
        _flush_run(run, source, blocks)

        for pos, doc, _idx in sem_indice:
            blocks.append((pos, source, doc))

    blocks.sort(key=lambda b: b[0])
    return [f"[{s}]\n{t}" for _pos, s, t in blocks]


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
    state: dict = {}
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
        with contextlib.suppress(OSError):
            state[rel] = md.stat().st_mtime
        for i, chunk in enumerate(chunks):
            ids.append(f"{rel}::{i}")
            docs.append(chunk)
            metas.append({"source": rel, "chunk": i})

    if not docs:
        _save_state({})
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
    _save_state(state)  # mantém o cache incremental consistente com o reindex
    return n_notes


def query_memory(question: str, k: int | None = None) -> list[str]:
    """Busca semântica no ChromaDB. Retorna os trechos mais relevantes
    (formatados com a nota de origem). Lista vazia se nada foi indexado."""
    k = k or settings.RAG_TOP_K
    collection = _get_collection()
    if collection.count() == 0:
        note(chunks=0, sources=[])
        return []

    with timed("rag_embed"):
        q_emb = _get_embedder().embed_query(question)
    with timed("rag_search"):
        # `include` é explícito (não o default do Chroma): o contrato de que
        # "distances" sempre volta fica fixado no código, não dependente de
        # um default externo que pode mudar num upgrade de dependência e
        # transformar `_filter_by_distance` num no-op silencioso.
        res = collection.query(
            query_embeddings=[q_emb], n_results=k, include=["documents", "metadatas", "distances"]
        )

    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    distances = (res.get("distances") or [[]])[0]

    if docs and not distances:
        # Defensivo: `include` pediu "distances" explicitamente, então chegar
        # aqui sem elas é uma resposta fora do contrato esperado (ex.: um
        # mock de teste incompleto, ou uma API do Chroma que mudou). Fica
        # observável no bench em vez de silenciosamente desativar o filtro.
        note(rag_distances_missing=True)

    entries = _filter_by_distance(docs, metas, distances)
    out = _merge_adjacent_chunks(entries)
    sources = list(dict.fromkeys((meta or {}).get("source", "?") for _doc, meta in entries))
    # As fontes vão para as métricas aqui, onde ainda são estruturadas — o bench
    # nunca deve reparsear as strings "[source]\n…" devolvidas.
    note(chunks=len(out), sources=sources)
    return out


def _rel(path: Path) -> str:
    return str(Path(path).resolve().relative_to(settings.OBSIDIAN_VAULT_PATH))


def index_note(path: str | Path) -> None:
    """(Re)indexa UMA nota no ChromaDB (upsert por `source`). Usado para indexar
    conversas de forma incremental, para que virem memória entre chats."""
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="ignore")
    if not text.strip():
        return
    chunks = chunk_text(text)
    if not chunks:
        return
    rel = _rel(path)
    collection = _get_collection()
    with contextlib.suppress(Exception):  # remove chunks antigos desta nota
        collection.delete(where={"source": rel})
    embeddings = _get_embedder().embed_documents(chunks)
    collection.add(
        ids=[f"{rel}::{i}" for i in range(len(chunks))],
        documents=chunks,
        embeddings=embeddings,
        metadatas=[{"source": rel, "chunk": i} for i in range(len(chunks))],
    )


def related_sources(text: str, k: int = 3, exclude: str | None = None) -> list[str]:
    """Notas mais semelhantes a `text` (para linkar conversas por tema)."""
    collection = _get_collection()
    if collection.count() == 0:
        return []
    q = _get_embedder().embed_query(text)
    res = collection.query(query_embeddings=[q], n_results=k + 6)
    metas = (res.get("metadatas") or [[]])[0]
    out: list[str] = []
    for meta in metas:
        src = (meta or {}).get("source")
        if src and src != exclude and src not in out:
            out.append(src)
        if len(out) >= k:
            break
    return out


# ── Sincronização incremental (arquivos novos/alterados) ─────
def _state_path() -> Path:
    return Path(settings.CHROMA_DB_PATH).parent / "index_state.json"


def _load_state() -> dict:
    p = _state_path()
    if not p.exists():
        return {}
    with contextlib.suppress(Exception):
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _save_state(state: dict) -> None:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(Exception):
        p.write_text(json.dumps(state), encoding="utf-8")


def _delete_source(rel: str) -> None:
    with contextlib.suppress(Exception):
        _get_collection().delete(where={"source": rel})


def sync_vault() -> int:
    """Indexa apenas os arquivos novos/alterados do vault (usa mtime como cache).

    Assim, arquivos largados no vault para a Jade analisar são incorporados
    automaticamente, sem `python main.py index`. Retorna nº de arquivos indexados."""
    state = _load_state()
    seen: set[str] = set()
    changed = 0
    for f in iter_vault_notes():
        rel = _rel(f)
        seen.add(rel)
        try:
            mtime = f.stat().st_mtime
        except OSError:
            continue
        if state.get(rel) != mtime:
            index_note(f)
            state[rel] = mtime
            changed += 1
    for gone in [s for s in state if s not in seen]:  # notas removidas do vault
        _delete_source(gone)
        state.pop(gone, None)
    _save_state(state)
    return changed
