"""API FastAPI — servidor principal que o Frontend e o WhatsApp consomem."""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from core.config import settings

app = FastAPI(title="Project Jade", version="0.1.0")


class ChatRequest(BaseModel):
    message: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "provider": settings.LLM_PROVIDER}


@app.post("/chat")
def chat(req: ChatRequest) -> dict:
    # TODO (Fase 1): from core.agent_router import handle_message
    #   return {"reply": handle_message(req.message)}
    return {"reply": "Jade ainda está despertando (Fase 1 pendente).",
            "echo": req.message}
