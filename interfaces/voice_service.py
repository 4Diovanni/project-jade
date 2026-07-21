"""Voz do Jade — STT (Whisper) e TTS (Edge-TTS/ElevenLabs). Fase 3."""

from __future__ import annotations


def transcribe(audio_path: str) -> str:
    """Áudio -> texto via Whisper. TODO (Fase 3)."""
    raise NotImplementedError("Fase 3: integrar OpenAI Whisper.")


def speak(text: str) -> bytes:
    """Texto -> áudio via TTS. TODO (Fase 3)."""
    raise NotImplementedError("Fase 3: integrar Edge-TTS/ElevenLabs.")
