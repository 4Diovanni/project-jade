"""Voz do Jade (Fase 3) — STT e TTS.

- **STT**: `faster-whisper`, 100% local (privacy-first, sem PyTorch). O modelo é
  baixado na primeira execução e cacheado.
- **TTS**: `edge-tts` (online, vozes pt-BR de alta qualidade) ou `pyttsx3`
  (100% offline). Escolhido por `settings.TTS_BACKEND`.

Todos os imports pesados são preguiçosos: importar este módulo não puxa as libs
de voz nem baixa modelos.
"""

from __future__ import annotations

import contextlib
import sys
import tempfile
from pathlib import Path

from core.config import settings

_whisper_model = None


# ── STT (voz -> texto) ───────────────────────────────────────
def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel

        _whisper_model = WhisperModel(settings.WHISPER_MODEL, device="cpu", compute_type="int8")
    return _whisper_model


def transcribe(audio_path: str | Path, language: str | None = None) -> str:
    """Transcreve um arquivo de áudio para texto (pt por padrão)."""
    model = _get_whisper()
    segments, _info = model.transcribe(
        str(audio_path), language=language or settings.WHISPER_LANGUAGE
    )
    return " ".join(seg.text.strip() for seg in segments).strip()


# ── TTS (texto -> voz) ───────────────────────────────────────
def synthesize(
    text: str,
    out_path: str | Path,
    *,
    backend: str | None = None,
    voice: str | None = None,
) -> Path:
    """Gera um arquivo de áudio a partir do texto. Retorna o caminho gerado."""
    backend = (backend or settings.TTS_BACKEND).lower()
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if backend == "edge":
        _synthesize_edge(text, out, voice or settings.TTS_VOICE)
    elif backend == "pyttsx3":
        _synthesize_pyttsx3(text, out)
    else:
        raise ValueError(f"Backend de TTS desconhecido: {backend!r} (use 'edge' ou 'pyttsx3').")
    return out


def _synthesize_edge(text: str, out: Path, voice: str) -> None:
    import asyncio

    import edge_tts

    async def _run() -> None:
        await edge_tts.Communicate(text, voice).save(str(out))

    asyncio.run(_run())


def _synthesize_pyttsx3(text: str, out: Path) -> None:
    import pyttsx3

    engine = pyttsx3.init()
    engine.save_to_file(text, str(out))
    engine.runAndWait()


def speak(text: str, *, backend: str | None = None) -> None:
    """Fala o texto pelos alto-falantes (best-effort)."""
    backend = (backend or settings.TTS_BACKEND).lower()
    if backend == "pyttsx3":
        import pyttsx3

        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()
        return

    tmp = Path(tempfile.gettempdir()) / "jade_tts.mp3"
    synthesize(text, tmp, backend="edge")
    _play(tmp)


def _play(path: Path) -> None:
    """Toca o áudio no player padrão (foco em Windows; best-effort)."""
    import os

    if sys.platform == "win32" and hasattr(os, "startfile"):
        with contextlib.suppress(Exception):
            # Abre o áudio que nós geramos no player padrão (Windows, caminho confiável).
            os.startfile(str(path))  # nosec B606
