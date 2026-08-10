"""Testes do wake-word "Ok Jade" (interfaces.wakeword_service).

Só as partes puras: geração dos tons, endpointing por energia e validação
de configuração. Nada aqui abre microfone, carrega o modelo openWakeWord de
verdade ou baixa arquivo — CI-safe, como o resto dos testes de voz
(ver tests/test_voice.py)."""

import numpy as np
import pytest

from core.config import settings
from interfaces import wakeword_service as ww


# ── Tons de ativação/desativação ──
def test_tone_samples_tem_a_duracao_certa():
    samples = ww.tone_samples(440, 880, duration=0.1)
    assert len(samples) == int(ww.SAMPLE_RATE * 0.1)


def test_tone_samples_e_pcm16_dentro_da_faixa():
    samples = ww.tone_samples(440, 880)
    assert samples.dtype == np.int16
    assert np.max(np.abs(samples)) <= 32767


def test_tone_samples_nao_e_silencio():
    samples = ww.tone_samples(440, 880)
    assert np.abs(samples).mean() > 0


def test_tons_de_ativacao_e_desativacao_sao_diferentes():
    # Ativação sobe (grave->agudo), desativação desce (agudo->grave) —
    # os arrays devem divergir mesmo tendo a mesma duração/amplitude.
    subida = ww.tone_samples(440, 880)
    descida = ww.tone_samples(880, 440)
    assert not np.array_equal(subida, descida)


# ── Endpointing (fim de fala por energia) ──
def _frame(amplitude: int) -> np.ndarray:
    return np.full(ww.FRAME_SAMPLES, amplitude, dtype=np.int16)


def test_frame_rms_de_silencio_e_zero():
    assert ww.frame_rms(_frame(0)) == 0.0


def test_frame_rms_cresce_com_amplitude():
    assert ww.frame_rms(_frame(1000)) > ww.frame_rms(_frame(100))


def test_is_speech_frame_respeita_o_limiar():
    assert ww.is_speech_frame(_frame(1000), rms_threshold=500) is True
    assert ww.is_speech_frame(_frame(100), rms_threshold=500) is False


def test_endpoint_nao_reachado_sem_fala_alguma():
    # Só silêncio: nunca deveria parar (ainda não começou a falar).
    flags = [False] * 20
    assert ww.endpoint_reached(flags, silence_ms=100, frame_ms=10) is False


def test_endpoint_reachado_apos_silencio_suficiente_depois_da_fala():
    flags = [False, True, True, False, False, False]
    assert ww.endpoint_reached(flags, silence_ms=30, frame_ms=10) is True


def test_endpoint_nao_reachado_com_silencio_insuficiente():
    flags = [True, False]
    assert ww.endpoint_reached(flags, silence_ms=30, frame_ms=10) is False


def test_endpoint_reachado_ignora_silencio_antes_da_fala():
    flags = [False, False, False, True, False, False, False]
    assert ww.endpoint_reached(flags, silence_ms=30, frame_ms=10) is True


def test_max_frames_for_arredonda_por_baixo_e_nunca_zero():
    assert ww.max_frames_for(1, frame_ms=80) == 12
    assert ww.max_frames_for(0, frame_ms=80) == 1


# ── Configuração / validação do modelo ──
def test_settings_wakeword_tem_defaults_sensatos():
    # WAKEWORD_ENABLED é uma escolha de quem roda o projeto (liga depois de
    # treinar o modelo custom) — não uma invariante para travar em teste.
    assert isinstance(settings.WAKEWORD_ENABLED, bool)
    assert 0.0 < settings.WAKEWORD_THRESHOLD <= 1.0
    assert settings.WAKEWORD_SILENCE_MS > 0
    assert settings.WAKEWORD_MAX_SECONDS > 0
    assert settings.WAKEWORD_VAD_RMS_THRESHOLD > 0


def test_load_model_recusa_quando_desligado(monkeypatch):
    monkeypatch.setattr(settings, "WAKEWORD_ENABLED", False)
    with pytest.raises(ww.WakewordError, match="desligado"):
        ww._load_model()


def test_load_model_recusa_sem_arquivo_do_modelo(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "WAKEWORD_ENABLED", True)
    monkeypatch.setattr(settings, "WAKEWORD_MODEL_PATH", str(tmp_path / "nao_existe.onnx"))
    with pytest.raises(ww.WakewordError, match="não encontrado"):
        ww._load_model()
