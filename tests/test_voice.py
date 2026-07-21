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


def test_synthesize_backend_desconhecido(tmp_path):
    # Deve validar o backend ANTES de importar libs pesadas.
    with pytest.raises(ValueError):
        voice_service.synthesize("olá", tmp_path / "saida.mp3", backend="inexistente")
