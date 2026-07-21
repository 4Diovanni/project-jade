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
