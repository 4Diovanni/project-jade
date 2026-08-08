"""API FastAPI — servidor principal que o Frontend e o WhatsApp consomem."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import tempfile
import threading
from pathlib import Path

from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.chat import ChatSession
from core.config import settings
from core.journal import parse_conversation_note

app = FastAPI(title="Project Jade", version="0.1.0")
logger = logging.getLogger(__name__)

# Fase 1: uma única sessão de conversa (assistente pessoal = 1 usuário local).
# A sessão é criada de forma preguiçosa para a API subir mesmo sem o LLM pronto.
_session: ChatSession | None = None
# Serializa qualquer combinação de /chat, /ws/chat e /voice/chat — sem isto,
# duas requisições concorrentes corrompem o _history compartilhado.
_session_lock = asyncio.Lock()


def _get_session() -> ChatSession:
    global _session
    if _session is None:
        _session = ChatSession()
    return _session


@app.on_event("startup")
def _startup_spotify_sync() -> None:
    """Dispara um resync do cache do Spotify em segundo plano, se a conta já
    estiver conectada e o cache estiver velho — mesmo papel do disparo de
    sync_vault em ChatSession.__init__, mas na escala do processo da API (o
    Spotify não tem um "início de sessão" por conversa)."""
    from core.spotify import start_background_sync_if_stale

    start_background_sync_if_stale()


# WebSocket handshakes não passam pela same-origin policy do browser — o
# servidor precisa validar o Origin ele mesmo. Sem isso, qualquer página
# http:// aberta no mesmo browser do usuário poderia abrir um WebSocket para
# cá e ler as respostas da Jade (geradas com RAG sobre o vault pessoal).
_ALLOWED_WS_ORIGINS = {
    f"http://{settings.API_HOST}:{settings.API_PORT}",
    f"http://localhost:{settings.API_PORT}",
}


async def _stream_to_ws(websocket: WebSocket, session: ChatSession, message: str) -> bool:
    """Drena session.stream() (síncrono) numa thread e repassa cada pedaço
    pro WebSocket assim que chega — a ponte entre o mundo síncrono do
    ChatSession e o event loop assíncrono do FastAPI. Devolve True se o
    turno terminou sem erro (o chamador manda "done" só nesse caso).

    Continua consumindo a fila até a sentinela mesmo se o envio pro
    WebSocket falhar (cliente desconectou no meio) — só assim garante que a
    thread produtora já terminou de mutar `session` antes de devolver o
    controle, o que importa porque quem chama libera o _session_lock
    assim que esta função retorna."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    sentinel = object()

    def _produce() -> None:
        try:
            for chunk in session.stream(message):
                loop.call_soon_threadsafe(queue.put_nowait, chunk)
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, e)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, sentinel)

    threading.Thread(target=_produce, daemon=True).start()

    ok = True
    disconnected = False
    while (item := await queue.get()) is not sentinel:
        payload = (
            {"type": "error", "detail": str(item)}
            if isinstance(item, Exception)
            else {"type": "token", "text": item}
        )
        if isinstance(item, Exception):
            ok = False
        if not disconnected:
            try:
                await websocket.send_json(payload)
            except Exception:
                disconnected = True
                ok = False
    return ok and not disconnected


@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket) -> None:
    origin = websocket.headers.get("origin")
    if origin is not None and origin not in _ALLOWED_WS_ORIGINS:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    session = _get_session()
    try:
        while True:
            data = await websocket.receive_json()
            async with _session_lock:
                ok = await _stream_to_ws(websocket, session, data["message"])
            if ok:
                await websocket.send_json(
                    {
                        "type": "done",
                        "model": session.last_model,
                        "conversation_id": session.conversation_id,
                    }
                )
                # Resume o assunto num título — em segundo plano, sem bloquear
                # o loop do WebSocket (não há BackgroundTasks num handler de WS).
                task = session.title_task()
                if task is not None:
                    asyncio.create_task(asyncio.to_thread(task))
    except WebSocketDisconnect:
        pass


class ChatRequest(BaseModel):
    message: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "provider": settings.LLM_PROVIDER}


@app.post("/chat")
async def chat(req: ChatRequest, background: BackgroundTasks) -> dict:
    session = _get_session()
    try:
        async with _session_lock:
            reply = await asyncio.to_thread(session.send, req.message)
    except Exception as e:  # provider fora do ar, chave faltando, etc.
        # O detalhe do erro vai para o log do servidor, não para o cliente
        # (evita expor stack trace/implementação na resposta HTTP).
        logger.exception("Falha ao responder no /chat")
        raise HTTPException(status_code=503, detail="Jade indisponível no momento.") from e
    # Resume o assunto num título — depois de responder, para não atrasar o chat.
    task = session.title_task()
    if task is not None:
        background.add_task(task)
    return {
        "reply": reply,
        "model": session.last_model,
        "conversation_id": session.conversation_id,
    }


@app.post("/reset")
async def reset(background: BackgroundTasks) -> dict:
    """Começa uma conversa nova. Responde na hora: indexar no RAG, resumir o
    título e aprender sobre o usuário rodam em segundo plano.

    Adquire o mesmo _session_lock de /chat e /ws/chat antes de mutar a sessão
    (detach() limpa _history/last_model de forma síncrona) — sem o lock, um
    /reset correria com um turno em andamento."""
    async with _session_lock:
        task = _get_session().detach()
    background.add_task(task)
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


# ── Spotify (Fase 4) ─────────────────────────────────────────
@app.get("/spotify/login")
def spotify_login() -> RedirectResponse:
    """Redireciona para a tela de autorização do Spotify."""
    from core.spotify import authorize_url

    return RedirectResponse(url=authorize_url())


@app.get("/spotify/callback")
def spotify_callback(code: str | None = None, error: str | None = None) -> RedirectResponse:
    """Troca o code por um token, dispara a 1ª sincronização em segundo
    plano e manda o usuário de volta pro frontend, aba Spotify."""
    if error or not code:
        return RedirectResponse(url="/app/?spotify=erro")

    from core.spotify import handle_callback, start_background_sync_if_stale

    try:
        handle_callback(code)
    except Exception:
        return RedirectResponse(url="/app/?spotify=erro")
    start_background_sync_if_stale()
    return RedirectResponse(url="/app/?spotify=conectado")


@app.get("/spotify/status")
def spotify_status() -> dict:
    from core.spotify import is_linked
    from core.spotify_db import last_synced_at, track_count

    return {
        "linked": is_linked(),
        "track_count": track_count(),
        "last_synced_at": last_synced_at(),
    }


@app.get("/spotify/library")
def spotify_library() -> dict:
    """Cache completo de faixas, agrupado por playlist ('Curtidas' quando
    não vem de nenhuma playlist nomeada)."""
    from core.spotify_db import list_tracks

    grouped: dict[str, list[dict]] = {}
    for track in list_tracks():
        key = track["playlist_name"] or "Curtidas"
        grouped.setdefault(key, []).append(track)
    return {"playlists": grouped}


@app.post("/spotify/sync")
def spotify_sync() -> dict:
    """Força um resync completo da biblioteca (síncrono — a resposta só
    volta quando a sincronização termina)."""
    from core.spotify import is_linked, sync_library

    if not is_linked():
        raise HTTPException(status_code=400, detail="Conta Spotify não conectada.")
    try:
        n = sync_library(force=True)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Falha ao sincronizar: {e}") from e
    return {"synced_tracks": n}


FRONTEND_DIR = Path(__file__).parent / "frontend"

_FM_FIELD = {key: re.compile(rf'(?m)^{key}:\s*"?(.*?)"?\s*$') for key in ("title", "data")}


def _frontmatter_field(text: str, key: str) -> str:
    m = _FM_FIELD[key].search(text)
    return m.group(1).strip() if m else ""


def _conversations_dir() -> Path:
    return settings.NOTES_DIR / settings.CONVERSATIONS_SUBDIR


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


class RenameRequest(BaseModel):
    title: str


@app.patch("/conversations/{conv_id}")
def rename_conversation(conv_id: str, req: RenameRequest) -> dict:
    """Renomeia o título de uma conversa (o arquivo/id não muda)."""
    from core.journal import set_note_title

    safe = Path(conv_id).name  # anti path-traversal
    path = _conversations_dir() / f"{safe}.md"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    title = set_note_title(path, req.title, custom=True)
    # Se for a conversa em andamento, mantém o título em memória em sincronia
    # (senão o próximo turno reescreveria a nota com o título antigo).
    if _session is not None and _session.conversation_id == safe:
        _session.rename(title)
    return {"id": safe, "title": title}


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
        async with _session_lock:
            reply = await asyncio.to_thread(session.send, transcription)
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
        "conversation_id": session.conversation_id,
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
