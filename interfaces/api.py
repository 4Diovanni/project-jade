"""API FastAPI — servidor principal que o Frontend e o WhatsApp consomem."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from core.chat import ChatSession
from core.config import settings

app = FastAPI(title="Project Jade", version="0.1.0")

# Fase 1: uma única sessão de conversa (assistente pessoal = 1 usuário local).
# A sessão é criada de forma preguiçosa para a API subir mesmo sem o LLM pronto.
_session: ChatSession | None = None


def _get_session() -> ChatSession:
    global _session
    if _session is None:
        _session = ChatSession()
    return _session


class ChatRequest(BaseModel):
    message: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "provider": settings.LLM_PROVIDER}


@app.post("/chat")
def chat(req: ChatRequest) -> dict:
    try:
        reply = _get_session().send(req.message)
    except Exception as e:  # provider fora do ar, chave faltando, etc.
        raise HTTPException(status_code=503, detail=f"Jade indisponível: {e}") from e
    return {"reply": reply}


@app.post("/reset")
def reset() -> dict:
    _get_session().reset()
    return {"status": "histórico limpo"}


@app.post("/index")
def index() -> dict:
    """(Re)indexa o vault do Obsidian no ChromaDB."""
    from core.memory import reindex_vault

    try:
        n = reindex_vault()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Falha ao indexar: {e}") from e
    return {"indexed_notes": n}


class SearchRequest(BaseModel):
    query: str
    k: int | None = None


@app.post("/search")
def search(req: SearchRequest) -> dict:
    """Busca semântica direta nas anotações indexadas."""
    from core.memory import query_memory

    try:
        results = query_memory(req.query, k=req.k)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Falha na busca: {e}") from e
    return {"results": results}
