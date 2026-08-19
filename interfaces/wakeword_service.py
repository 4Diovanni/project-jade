"""Wake-word "Ok Jade" — escuta contínua local (voz #2, Fase 3+).

Detecta a frase de ativação com openWakeWord, sinaliza com um tom curto,
grava o comando até o silêncio (endpointing por energia do áudio) e entrega
pro mesmo pipeline do push-to-talk: `transcribe()` -> `ChatSession.send()` ->
`speak()`.

O modelo custom "ok jade" NÃO vem pronto — não existe wake-word em português
pré-treinado, precisa ser gerado à parte (ver `docs/wakeword_treino.md`) e
apontado por `JADE_WAKEWORD_MODEL_PATH`. Enquanto isso, `JADE_WAKEWORD_ENABLED`
fica `false` por padrão e este módulo nem tenta abrir o microfone.

Endpointing usa um limiar de energia (RMS) simples em vez de `webrtcvad`: a
lib exige compilar uma extensão C, o que falha sem o Visual C++ Build Tools
no Windows (testado neste projeto) — um limiar por amplitude é menos
sofisticado, mas não depende de compilador e roda em qualquer máquina com
`numpy` (já é dependência transitiva do projeto).

Todos os imports pesados (sounddevice, openwakeword) são preguiçosos:
importar este módulo não abre o microfone nem baixa modelos.
"""

from __future__ import annotations

import contextlib
import tempfile
import wave
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from core.config import settings
from interfaces import voice_service

if TYPE_CHECKING:
    import numpy as np

    from core.chat import ChatSession

SAMPLE_RATE = 16000
# 80ms @ 16kHz — o tamanho de frame recomendado pelo openWakeWord.
FRAME_SAMPLES = 1280
FRAME_MS = int(FRAME_SAMPLES / SAMPLE_RATE * 1000)


class WakewordError(RuntimeError):
    """Erro de configuração/hardware do wake-word — mensagem já pronta pro usuário."""


# ── Tons de ativação/desativação (sintetizados, sem asset externo) ──
def tone_samples(freq_start: float, freq_end: float, duration: float = 0.15) -> np.ndarray:
    """Gera um tom curto (sweep senoidal) como PCM16 mono. Função pura,
    testável sem hardware de áudio."""
    import numpy as np

    n = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    freq = np.linspace(freq_start, freq_end, n)
    wave_ = np.sin(2 * np.pi * freq * t)
    # fade-out nos últimos 30% pra não estalar no fim do tom.
    fade = max(1, int(n * 0.3))
    envelope = np.ones(n)
    envelope[-fade:] = np.linspace(1, 0, fade)
    return (wave_ * envelope * 0.3 * 32767).astype(np.int16)


def _play_tone(freq_start: float, freq_end: float) -> None:
    import sounddevice as sd

    sd.play(tone_samples(freq_start, freq_end), SAMPLE_RATE)
    sd.wait()


def play_activation_tone() -> None:
    """Tom de ativação: sobe (grave -> agudo), como o Google Assistant."""
    _play_tone(440, 880)


def play_deactivation_tone() -> None:
    """Tom de desativação: desce (agudo -> grave)."""
    _play_tone(880, 440)


# ── Endpointing (fim de fala por silêncio) ──
def frame_rms(frame: np.ndarray) -> float:
    """Energia (RMS) de um frame PCM16 mono. Função pura."""
    import numpy as np

    if frame.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(frame.astype(np.float64) ** 2)))


def is_speech_frame(frame: np.ndarray, *, rms_threshold: float | None = None) -> bool:
    """Classifica um frame como fala vs. silêncio por limiar de energia."""
    threshold = settings.WAKEWORD_VAD_RMS_THRESHOLD if rms_threshold is None else rms_threshold
    return frame_rms(frame) >= threshold


def endpoint_reached(
    speech_flags: list[bool], *, silence_ms: int, frame_ms: int = FRAME_MS
) -> bool:
    """Decide se o comando terminou: silêncio contínuo >= silence_ms logo
    depois de já ter havido fala. Nunca corta antes do usuário começar a
    falar (evita parar por causa do ruído de fundo antes da frase)."""
    if not any(speech_flags):
        return False
    frames_needed = max(1, silence_ms // frame_ms)
    trailing_silence = 0
    for speaking in reversed(speech_flags):
        if speaking:
            break
        trailing_silence += 1
    return trailing_silence >= frames_needed


def max_frames_for(seconds: int, *, frame_ms: int = FRAME_MS) -> int:
    """Quantos frames cabem no teto de duração do comando."""
    return max(1, (seconds * 1000) // frame_ms)


# ── Modelo de wake-word ──
def _load_model():
    if not settings.WAKEWORD_ENABLED:
        raise WakewordError(
            "Wake-word desligado (JADE_WAKEWORD_ENABLED=false). Habilite no "
            ".env depois de gerar o modelo custom."
        )
    model_path = settings.WAKEWORD_MODEL_PATH
    if not model_path or not Path(model_path).exists():
        raise WakewordError(
            f"Modelo custom de wake-word não encontrado ({model_path or '(vazio)'}). "
            "Gere 'ok_jade.onnx' seguindo docs/wakeword_treino.md e aponte "
            "JADE_WAKEWORD_MODEL_PATH no .env."
        )
    from openwakeword import utils as oww_utils
    from openwakeword.model import Model

    # Modelos-base fixos (extração de features) + VAD interno do openWakeWord;
    # baixados uma única vez, não é o modelo custom "ok jade".
    oww_utils.download_models()
    return Model(wakeword_models=[model_path], inference_framework="onnx")


# ── Gravação do comando após a ativação ──
def _write_wav(path: str, pcm: bytes) -> None:
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm)


def _record_command(stream) -> bytes:
    """Grava frames do stream até o fim de fala (silêncio) ou o teto de
    duração. Devolve PCM16 mono bruto."""
    flags: list[bool] = []
    frames: list[bytes] = []
    ceiling = max_frames_for(settings.WAKEWORD_MAX_SECONDS)
    while len(frames) < ceiling:
        frame, _overflowed = stream.read(FRAME_SAMPLES)
        raw = frame.reshape(-1)
        frames.append(raw.tobytes())
        flags.append(is_speech_frame(raw))
        if endpoint_reached(flags, silence_ms=settings.WAKEWORD_SILENCE_MS):
            break
    return b"".join(frames)


# ── Loop principal ──
def listen_forever(
    session: ChatSession | None = None,
    *,
    speak: Callable[[str], None] | None = None,
    respond: Callable[[str], None] | None = None,  # pyright: ignore[reportRedeclaration]
    on_wake: Callable[[], None] | None = None,
    on_thinking: Callable[[], None] | None = None,
) -> None:
    """Ouve o wake-word continuamente; a cada ativação, grava o comando,
    transcreve e repassa o texto pra `respond`. Bloqueia até `KeyboardInterrupt`.

    Por padrão (`respond=None`), cada comando é processado com
    `session.send()` + fala local (`voice_service.speak`) — o caminho do
    `python main.py listen` standalone, que por isso precisa de `session`.

    Quando integrado à API (`interfaces/api.py`), `respond` substitui esse
    processamento inteiro (sessão/lock compartilhados com `/chat` e
    `/voice/chat`, turno distribuído pro frontend via WebSocket em vez de
    falado localmente) — `session` deixa de ser necessário.

    `on_wake`/`on_thinking` são ganchos opcionais de UI (chamados na
    ativação e ao começar a processar, sem esperar resposta); não fazem
    nada por padrão."""
    if respond is None:
        if session is None:
            raise ValueError("listen_forever precisa de 'session' ou 'respond'.")
        speak_fn = speak or voice_service.speak

        def respond(text: str) -> None:
            speak_fn(session.send(text))

    model = _load_model()

    import numpy as np
    import sounddevice as sd

    print(f"👂 Ouvindo 'ok jade'... (Ctrl+C para sair, limiar={settings.WAKEWORD_THRESHOLD})")
    with sd.InputStream(
        samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=FRAME_SAMPLES
    ) as stream:
        while True:
            frame, _overflowed = stream.read(FRAME_SAMPLES)
            prediction = model.predict(frame.reshape(-1).astype(np.int16))
            # predict() só devolve tupla (dict, dict) quando chamado com
            # timing=True (não é o caso aqui) — o stub inferido do openWakeWord
            # não expressa essa distinção por overload.
            score = max(prediction.values(), default=0.0)  # pyright: ignore[reportAttributeAccessIssue]
            if score < settings.WAKEWORD_THRESHOLD:
                continue

            if on_wake:
                on_wake()
            play_activation_tone()
            pcm = _record_command(stream)
            play_deactivation_tone()
            model.reset()

            if on_thinking:
                on_thinking()

            audio_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    audio_path = tmp.name
                _write_wav(audio_path, pcm)
                text = voice_service.transcribe(audio_path)
                if not text.strip():
                    continue
                respond(text)
            except Exception as e:
                print(f"⚠️ Falha ao processar o comando: {e}")
            finally:
                if audio_path:
                    with contextlib.suppress(Exception):
                        Path(audio_path).unlink()
