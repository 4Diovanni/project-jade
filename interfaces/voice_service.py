"""Voz do Jade (Fase 3) — STT e TTS.

- **STT**: `faster-whisper`, 100% local (privacy-first, sem PyTorch). O modelo é
  baixado na primeira execução e cacheado.
- **TTS**: `edge-tts` (online, vozes pt-BR de alta qualidade → **.mp3**) ou
  `pyttsx3` (100% offline → .wav). Escolhido por `settings.TTS_BACKEND`.

Ao salvar, o arquivo recebe a extensão/formato corretos automaticamente, para
ser consumível tanto pelo Jade quanto pelo usuário.

Todos os imports pesados são preguiçosos: importar este módulo não puxa as libs
de voz nem baixa modelos.
"""

from __future__ import annotations

import contextlib
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from core.config import settings

_whisper_model = None

# Formato de arquivo produzido por cada backend de TTS.
_EXT_BY_BACKEND = {"edge": ".mp3", "pyttsx3": ".wav"}


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
def _output_path(out_path: str | Path, backend: str) -> Path:
    """Ajusta a extensão do arquivo ao formato real do backend (.mp3/.wav)."""
    out = Path(out_path)
    ext = _EXT_BY_BACKEND.get(backend)
    return out.with_suffix(ext) if ext else out


def synthesize(
    text: str,
    out_path: str | Path,
    *,
    backend: str | None = None,
    voice: str | None = None,
) -> Path:
    """Gera um arquivo de áudio a partir do texto. Retorna o caminho REAL gerado
    (com a extensão correta: .mp3 no backend edge, .wav no pyttsx3)."""
    backend = (backend or settings.TTS_BACKEND).lower()
    if backend not in _EXT_BY_BACKEND:
        raise ValueError(f"Backend de TTS desconhecido: {backend!r} (use 'edge' ou 'pyttsx3').")

    out = _output_path(out_path, backend)
    out.parent.mkdir(parents=True, exist_ok=True)

    if backend == "edge":
        _synthesize_edge(text, out, voice or settings.TTS_VOICE)
    else:  # pyttsx3
        _synthesize_pyttsx3(text, out)
    return out


def synthesize_reply(text: str, *, backend: str | None = None, voice: str | None = None) -> Path:
    """Salva uma fala do Jade como arquivo de áudio (mp3, por padrão) em
    `settings.AUDIO_OUTPUT_DIR`, com nome carimbado por data/hora. Retorna o caminho."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = settings.AUDIO_OUTPUT_DIR / f"jade_{stamp}"
    return synthesize(text, destino, backend=backend, voice=voice)


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
