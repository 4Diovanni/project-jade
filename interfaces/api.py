"""API FastAPI — servidor principal que o Frontend e o WhatsApp consomem."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
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


# ── Voz (Fase 3) ─────────────────────────────────────────────
def _save_upload(file: UploadFile) -> Path:
    """Salva o áudio recebido num arquivo temporário e retorna o caminho."""
    suffix = Path(file.filename or "audio").suffix or ".wav"
    fd, name = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as out:
        shutil.copyfileobj(file.file, out)
    return Path(name)


class TTSRequest(BaseModel):
    text: str
    backend: str | None = None
    voice: str | None = None


@app.post("/voice/transcribe")
async def voice_transcribe(file: UploadFile = File(...)) -> dict:
    """Áudio (upload) -> texto (STT local)."""
    from interfaces.voice_service import transcribe

    tmp = _save_upload(file)
    try:
        text = transcribe(tmp)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Falha no STT: {e}") from e
    finally:
        tmp.unlink(missing_ok=True)
    return {"text": text}


@app.post("/voice/tts")
def voice_tts(req: TTSRequest) -> FileResponse:
    """Texto -> áudio (TTS). Retorna o arquivo de áudio (mp3, padrão edge)."""
    from interfaces.voice_service import synthesize

    out = Path(tempfile.mkdtemp()) / "jade_tts.mp3"
    try:
        synthesize(req.text, out, backend=req.backend, voice=req.voice)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Falha no TTS: {e}") from e
    return FileResponse(out, media_type="audio/mpeg", filename="jade.mp3")


@app.post("/voice/chat")
async def voice_chat(file: UploadFile = File(...)) -> dict:
    """Áudio (upload) -> transcrição -> Jade (RAG + memória) -> resposta em texto."""
    from interfaces.voice_service import transcribe

    tmp = _save_upload(file)
    try:
        transcription = transcribe(tmp)
        reply = _get_session().send(transcription)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Falha no voice chat: {e}") from e
    finally:
        tmp.unlink(missing_ok=True)
    return {"transcription": transcription, "reply": reply}
