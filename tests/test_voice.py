"""Testes de voz que NÃO baixam modelos nem acessam rede (CI-safe).

O round-trip real (TTS -> STT) é validado localmente, fora do CI.
"""

import pytest

from core.config import settings
from interfaces import voice_service


def test_config_voz_defaults():
    assert settings.WHISPER_MODEL
    assert settings.TTS_BACKEND in {"edge", "pyttsx3"}
    assert settings.TTS_VOICE
    assert settings.WHISPER_LANGUAGE


def test_transcribe_usa_vad_beam_e_prompt(monkeypatch):
    """Regressão: erros como 'toque' em vez de 'toca' vinham de transcrever
    sem VAD/beam search/viés de vocabulário. Trava os três parâmetros."""
    captured: dict = {}

    class _FakeSegment:
        text = "toca sweet dreams"

    class _FakeModel:
        def transcribe(self, path, **kwargs):
            captured.update(kwargs)
            return [_FakeSegment()], None

    monkeypatch.setattr(voice_service, "_get_whisper", lambda: _FakeModel())
    text = voice_service.transcribe("audio.wav")

    assert text == "toca sweet dreams"
    assert captured["vad_filter"] is True
    assert captured["beam_size"] == 5
    assert captured["initial_prompt"] == settings.WHISPER_PROMPT


def test_synthesize_backend_desconhecido(tmp_path):
    # Deve validar o backend ANTES de importar libs pesadas.
    with pytest.raises(ValueError):
        voice_service.synthesize("olá", tmp_path / "saida.mp3", backend="inexistente")


def test_output_path_forca_extensao_correta():
    # edge -> sempre .mp3 (mesmo sem extensão ou com extensão errada)
    assert voice_service._output_path("fala", "edge").suffix == ".mp3"
    assert voice_service._output_path("fala.wav", "edge").suffix == ".mp3"
    # pyttsx3 -> .wav (formato real do SAPI)
    assert voice_service._output_path("fala.mp3", "pyttsx3").suffix == ".wav"


def test_audio_output_dir_configurado():
    assert settings.AUDIO_OUTPUT_DIR
    assert settings.AUDIO_OUTPUT_DIR.name  # tem um nome de pasta


def test_synthesize_edge_dentro_de_event_loop(monkeypatch, tmp_path):
    """Regressão: /voice/chat é um endpoint async, então _synthesize_edge roda
    DENTRO de um event loop. asyncio.run() ali levantava RuntimeError e devolvia
    503. O TTS precisa funcionar mesmo com um loop já em execução."""
    import asyncio
    import sys
    import types
    from pathlib import Path

    saved: dict = {}

    class _FakeCommunicate:
        def __init__(self, text, voice):
            saved["text"] = text

        async def save(self, path):
            Path(path).write_bytes(b"fake-mp3")
            saved["path"] = path

    monkeypatch.setitem(
        sys.modules, "edge_tts", types.SimpleNamespace(Communicate=_FakeCommunicate)
    )
    out = tmp_path / "fala.mp3"

    async def _dentro_do_loop():
        # Simula o /voice/chat: chamada síncrona de dentro de um loop rodando.
        voice_service._synthesize_edge("olá", out, "pt-BR-FranciscaNeural")

    asyncio.run(_dentro_do_loop())

    assert out.exists()
    assert saved.get("text") == "olá"
    assert saved.get("path") == str(out)
