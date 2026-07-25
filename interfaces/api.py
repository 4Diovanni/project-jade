"""API FastAPI — servidor principal que o Frontend e o WhatsApp consomem."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.chat import ChatSession
from core.config import settings
from core.journal import parse_conversation_note

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
    session = _get_session()
    try:
        reply = session.send(req.message)
    except Exception as e:  # provider fora do ar, chave faltando, etc.
        raise HTTPException(status_code=503, detail=f"Jade indisponível: {e}") from e
    return {"reply": reply, "model": session.last_model}


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


FRONTEND_DIR = Path(__file__).parent / "frontend"

_FM_FIELD = {key: re.compile(rf'(?m)^{key}:\s*"?(.*?)"?\s*$') for key in ("title", "data")}


def _frontmatter_field(text: str, key: str) -> str:
    m = _FM_FIELD[key].search(text)
    return m.group(1).strip() if m else ""


def _conversations_dir() -> Path:
    return settings.OBSIDIAN_VAULT_PATH / settings.CONVERSATIONS_SUBDIR


@app.get("/conversations")
def list_conversations() -> list[dict]:
    """Lista as conversas salvas (notas .md), mais recente primeiro."""
    folder = _conversations_dir()
    if not folder.is_dir():
        return []
    items: list[dict] = []
    for md in sorted(folder.glob("*.md"), key=lambda p: p.name, reverse=True):
        text = md.read_text(encoding="utf-8", errors="ignore")
        items.append(
            {
                "id": md.stem,
                "title": _frontmatter_field(text, "title") or md.stem,
                "date": _frontmatter_field(text, "data"),
            }
        )
    return items


@app.get("/conversations/{conv_id}")
def get_conversation(conv_id: str) -> dict:
    """Retorna uma conversa parseada (só leitura)."""
    safe = Path(conv_id).name  # anti path-traversal
    path = _conversations_dir() / f"{safe}.md"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    text = path.read_text(encoding="utf-8", errors="ignore")
    return {
        "title": _frontmatter_field(text, "title") or safe,
        "date": _frontmatter_field(text, "data"),
        "turns": parse_conversation_note(text),
    }


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/app/")


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
    """Áudio (upload) -> transcrição -> Jade (RAG + memória) -> resposta em texto
    E em áudio: a fala do Jade é salva como .mp3 (consumível por ele e por você)."""
    from interfaces.voice_service import synthesize_reply, transcribe

    tmp = _save_upload(file)
    try:
        transcription = transcribe(tmp)
        session = _get_session()
        reply = session.send(transcription)
        audio_path = synthesize_reply(reply)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Falha no voice chat: {e}") from e
    finally:
        tmp.unlink(missing_ok=True)
    return {
        "transcription": transcription,
        "reply": reply,
        "audio_file": str(audio_path),
        "audio_url": f"/voice/audio/{audio_path.name}",
        "model": session.last_model,
    }


@app.get("/voice/audio/{name}")
def voice_audio(name: str) -> FileResponse:
    """Baixa um áudio gerado pelo Jade (salvo em AUDIO_OUTPUT_DIR)."""
    safe = Path(name).name  # evita path traversal
    path = settings.AUDIO_OUTPUT_DIR / safe
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Áudio não encontrado.")
    return FileResponse(path, media_type="audio/mpeg", filename=safe)


FRONTEND_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
