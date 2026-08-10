# Voz #2 — Wake-word "Ok Jade" + Precisão do STT — Design

**Data:** 2026-08-09
**Status:** aprovado no brainstorming; pronto para implementação
**Escopo:** Realiza o Subprojeto #3 ("Daemon de wake-word") previsto em
`docs/superpowers/specs/2026-07-24-frontend-jade-shell-voz-design.md` §Decomposição,
mais uma melhoria de acurácia do STT que vale independente do wake-word.

## Contexto

Hoje a voz da Jade é **push-to-talk**: segurar o botão/espaço no frontend
(`interfaces/frontend/voice.js`) grava com `MediaRecorder`, envia pro backend
(`POST /voice/chat`), que transcreve com `faster-whisper` (`interfaces/voice_service.py`)
e roteia pro `ChatSession`. Não existe escuta contínua nem ativação por voz.

Dois problemas relatados pelo usuário:
1. **Sem mãos livres.** Precisa clicar/segurar toda vez — quer dizer "ok jade"
   e a Jade "acordar" sozinha, como o Google Assistant, com um som de
   ativação e outro de desativação.
2. **Baixa precisão do STT.** Frases viraram texto errado — "toca Sweet
   Dreams" saiu como "toque", "Jade" saiu como "ja de". A causa provável:
   `WHISPER_MODEL=base` (modelo pequeno) sem VAD nem viés de vocabulário —
   ruído/silêncio nas bordas do clipe do `MediaRecorder` e nomes próprios sem
   contexto confundem um modelo desse tamanho.

## Objetivos

- **Escuta contínua por "ok jade"**, 100% local, via um processo dedicado
  (`python main.py listen`) — não depende do frontend/navegador estar aberto.
- **Sinalização sonora**: um tom curto ao detectar o wake-word (ativado) e
  outro ao terminar de ouvir o comando (desativado) — mesmo padrão do Google
  Assistant/Alexa.
- **Fim de fala automático** (endpointing por silêncio) depois da ativação,
  sem precisar apertar nada.
- **Reaproveitar o pipeline existente**: o áudio capturado vira texto
  (`transcribe`) → vira resposta (`ChatSession.send`) → é falado (`speak`) —
  os mesmos três já usados no push-to-talk.
- **Melhorar a acurácia do STT** (`interfaces/voice_service.transcribe`) para
  todos os caminhos de voz (push-to-talk **e** wake-word), não só o novo daemon.

## Não-objetivos (por agora)

- **Focar/ativar a janela do navegador.** O spec original de 07-24 citava isso;
  não foi pedido agora e exige automação Win32 (janela em foco) que é frágil e
  não crítica — a Jade responde **falando**, sem precisar da janela em foco.
- **Integração visual com o orb do frontend** (empurrar `listening`/`speaking`
  via WebSocket para a UI reagir ao wake-word). Fica pra uma próxima iteração;
  o daemon funciona como um "alto-falante inteligente" independente da UI.
- **Rodar como serviço do Windows / autostart no boot.** O usuário roda
  `python main.py listen` manualmente por enquanto.
- **Barge-in** (interromper a Jade no meio da fala dizendo "ok jade" de novo).
- **Wake-word multilíngue ou mais de uma palavra de ativação.**

## Decisão de motor: openWakeWord

Avaliadas três opções com o usuário (Picovoice Porcupine, openWakeWord, Whisper
em janela deslizante). Escolhido **openWakeWord** por ser 100% open-source e
sem conta/chave externa — alinhado ao *privacy-first* do projeto.

**Trade-off aceito:** não existe modelo pronto pra "ok jade" (só inglês tipo
"hey jarvis", "alexa"). É preciso **treinar um modelo custom**, e o pipeline
oficial (dados sintéticos via TTS + augmentation com ruído/RIR) é pesado demais
pra rodar neste ambiente de desenvolvimento (roda em Colab com GPU gratuita,
baixa alguns GB de datasets de negativos). Por isso:
- O caminho do modelo é configurável (`JADE_WAKEWORD_MODEL_PATH`), o arquivo
  **não é gerado por esta implementação**.
- `python main.py listen` falha rápido com uma mensagem clara se o arquivo não
  existir, sem quebrar o resto do projeto (mesmo padrão de erro do `run_cli`
  quando o Ollama está fora do ar).
- Um guia (`docs/wakeword_treino.md`) documenta o passo a passo pra gerar
  `ok_jade.onnx` no notebook oficial do openWakeWord.
- Enquanto o modelo não existe, `JADE_WAKEWORD_ENABLED=false` (default) mantém
  o resto do projeto (API, chat, push-to-talk) **inalterado**.

openWakeWord também baixa, na primeira execução, dois modelos-base fixos
(melspectrogram + embedding — extração de features, não o wake-word em si) via
`openwakeword.utils.download_models()`. Isso é um download pequeno e único,
não um treino.

## Arquitetura

### Captura e detecção (`interfaces/wakeword_service.py`, novo)

```
sounddevice (mic, 16kHz mono int16, frames de 1280 amostras/80ms)
    → openwakeword.Model.predict(frame) → score de "ok_jade"
    → score > limiar (JADE_WAKEWORD_THRESHOLD) → ATIVA
        → toca tom de ativação (voice_service._play)
        → grava frames seguintes até silêncio (webrtcvad) ou teto de duração
        → toca tom de desativação
        → transcribe(wav) → ChatSession.send(texto) → speak(resposta)
    → volta a ouvir o wake-word
```

- **Endpointing:** limiar de energia (RMS) por frame — não `webrtcvad` como
  cogitado inicialmente: a lib exige compilar uma extensão C, e falhou neste
  ambiente por falta do Visual C++ Build Tools no Windows (`pip install
  webrtcvad` — sem wheel pronta pro Python usado aqui). Um limiar por
  amplitude é mais simples/menos preciso, mas não depende de compilador e usa
  só `numpy` (já é dependência transitiva do projeto). Configurável via
  `JADE_WAKEWORD_VAD_RMS_THRESHOLD`. Janela de silêncio
  (`JADE_WAKEWORD_SILENCE_MS`, default 900ms) e duração máxima do comando
  (`JADE_WAKEWORD_MAX_SECONDS`, default 12s) — nunca escuta pra sempre.
- **Sons de ativação/desativação:** sintetizados em código (seno, sem asset
  externo) — dois tons curtos (subida = ativado, descida = desativado),
  gerados uma vez e cacheados; tocados pelo mecanismo `_play` que já existe em
  `voice_service.py`.
- **Sessão:** o daemon cria sua **própria** `ChatSession`, igual ao
  `python main.py chat` — não compartilha estado com uma sessão da API aberta
  no navegador (mesma assimetria que já existe hoje entre CLI e API). O
  journal (`core/journal.py`) grava a conversa no vault de qualquer forma —
  nada de memória se perde.
- **Desligado por padrão:** `JADE_WAKEWORD_ENABLED=false` até o usuário ter o
  modelo custom.

### `main.py`

Novo comando `python main.py listen`, no mesmo padrão dos existentes
(`chat`, `transcribe`, `say`): cria a sessão, chama
`wakeword_service.listen_forever(session)`, `Ctrl+C` para sair.

### Melhoria do STT (`interfaces/voice_service.transcribe`)

Vale para **todos** os caminhos de voz, não só o wake-word:

| Mudança | Efeito |
|---|---|
| `WHISPER_MODEL`: `base` → `small` (default) | Ganho de acurácia relevante; ainda roda em CPU/int8 numa boa. Configurável via `.env` pra quem tiver máquina mais fraca. |
| `vad_filter=True` | O faster-whisper já embute um VAD (Silero); remove silêncio/ruído nas bordas do clipe — provável causa direta de "toque" em vez de "toca". |
| `beam_size=5` | Busca melhor em vez de greedy; latência um pouco maior, aceitável pro caso de uso (não é streaming). |
| `initial_prompt` configurável (`JADE_WHISPER_PROMPT`) | Viés de vocabulário: um prompt com "Jade" e pontuação em PT-BR ajuda o Whisper a acertar o nome dela e nomes próprios em geral (técnica oficial do Whisper). |

Essas mudanças por si só já deveriam corrigir os dois exemplos citados
("toque"/"toca", "ja de"/"Jade"), **antes mesmo do wake-word existir**.

## Configuração nova (`core/config.py` + `.env.example`)

```
JADE_WAKEWORD_ENABLED=false
JADE_WAKEWORD_MODEL_PATH=              # caminho pro ok_jade.onnx custom
JADE_WAKEWORD_THRESHOLD=0.5
JADE_WAKEWORD_SILENCE_MS=900
JADE_WAKEWORD_MAX_SECONDS=12
JADE_WAKEWORD_VAD_RMS_THRESHOLD=500    # limiar de energia do endpointing

JADE_WHISPER_MODEL=small               # era "base"
JADE_WHISPER_PROMPT=Jade, tocar, Spotify, playlist, música.
```

## Erros e degradação

| Situação | Comportamento |
|---|---|
| `JADE_WAKEWORD_ENABLED=false` (default) | `python main.py listen` avisa que está desligado e como habilitar. |
| Modelo custom ausente/inválido | Mensagem clara apontando `docs/wakeword_treino.md`; não derruba a API nem os outros comandos. |
| Sem microfone / `sounddevice` falha ao abrir stream | Mensagem amigável, mesmo padrão de erro do resto do `main.py`. |
| Falha na transcrição/LLM durante um comando | Fala um aviso curto ("não consegui entender") e volta a ouvir o wake-word — não derruba o daemon. |

## Testes

CI-safe (sem microfone, sem modelo real, sem baixar nada — mesmo espírito de
`tests/test_voice.py`):
- Geração dos tons de ativação/desativação: forma de onda válida, duração,
  determinística (função pura).
- Decisão de fim-de-fala (silêncio acumulado × teto de duração): função pura
  testada com sequências sintéticas de frames "fala"/"silêncio".
- `transcribe()` chama `model.transcribe` com `vad_filter=True`, `beam_size=5`
  e o `initial_prompt` configurado (fake model via monkeypatch, como já é
  feito hoje para `edge_tts`).
- Defaults das novas settings (`JADE_WAKEWORD_*`, `JADE_WHISPER_MODEL=small`).
- Validação do path do modelo custom (arquivo ausente → erro claro, função
  pura, sem tocar hardware).

Testes que dependem de microfone/modelo real de verdade ficam fora do CI
(mesmo padrão do round-trip TTS→STT já documentado em `test_voice.py`).

## Arquivos afetados

- **Novos:** `interfaces/wakeword_service.py`; `tests/test_wakeword.py`;
  `docs/wakeword_treino.md` (passo a passo pra gerar o modelo custom).
- **Alterados:** `interfaces/voice_service.py` (`transcribe`: vad_filter,
  beam_size, initial_prompt); `core/config.py` + `.env.example` (settings
  novas + `WHISPER_MODEL` default); `main.py` (comando `listen`);
  `requirements.txt` (`openwakeword`, `sounddevice`); `CLAUDE.md`
  (Estado atual); `docs/superpowers/specs/2026-07-24-frontend-jade-shell-voz-design.md`
  (marcar #3 como implementado, com a ressalva do foco de janela fora de escopo).

## Decisões resolvidas

- Motor de wake-word: **openWakeWord** (escolha do usuário), aceitando que o
  modelo custom "ok jade" é um passo manual/externo, documentado.
- O daemon roda como **processo próprio** (`python main.py listen`),
  desacoplado da API — sessão de chat independente, igual ao CLI hoje.
- Sons de ativação/desativação são **sintetizados em código**, sem asset
  externo nem nova dependência de áudio.
- Melhoria de acurácia do STT (`small` + VAD + beam_size + initial_prompt)
  entra **já nesta entrega**, beneficiando o push-to-talk mesmo sem o
  wake-word habilitado.
- Foco de janela e integração com o orb do frontend ficam fora de escopo por
  agora.
