# Frontend da Jade — #1: Shell + Voz — Design

**Data:** 2026-07-24
**Status:** aprovado no brainstorming; pronto para o plano de implementação
**Escopo:** Subprojeto #1 de 3 (ver "Decomposição" abaixo)

## Contexto

Hoje a Jade só é acessível por CLI (`python main.py chat`) ou por chamadas cruas
na API FastAPI (`interfaces/api.py`). Não existe interface gráfica. O objetivo é
uma UI local, *privacy-first*, que dê uma interação melhor com a Jade — no estilo
de um assistente com "presença" visual (referência: J.A.R.V.I.S. do Homem de
Ferro), com voz em primeiro lugar.

A API atual já expõe o suficiente para o chat e a voz:
- `POST /chat {message}` → `{reply, model}` (model = `llama3` | `claude` | `tool`).
- `POST /reset`, `POST /index`, `POST /search`.
- `POST /voice/transcribe`, `POST /voice/tts`, `POST /voice/chat`, `GET /voice/audio/{name}`.

A Jade é single-user, local, com persona viva (humor, memória no Obsidian,
roteamento dual-model). Cada conversa já é salva como nota `.md` na pasta
`Conversas/` do vault.

## Decomposição (visão geral — só o #1 é detalhado aqui)

O pedido completo ("frontend com multi-thread + orb JARVIS + wake-word") são três
subsistemas independentes. Cada um terá seu próprio spec → plano → implementação.

| # | Subprojeto | Entrega | Estado |
|---|---|---|---|
| **1** | **Shell do frontend + voz** | Layout JARVIS (chat + orb reativo), push-to-talk com TTS automático, lista de conversas em leitura. | **Este spec** |
| 2 | Backend multi-thread | Criar/listar/abrir/**retomar** conversas com replay real dos turnos. | Futuro |
| 3 | Daemon de wake-word | Serviço Python local ouvindo o mic; ao ouvir "Jade", foca/ativa a janela. | **Implementado** (`python main.py listen`, ver `docs/superpowers/specs/2026-08-09-wakeword-precisao-voz-design.md`) — sem o foco de janela e sem integração com o orb, que ficaram fora de escopo dessa entrega. |

Ordem de construção: 1 → 2 → 3. O #1 coloca a experiência na tela cedo e
de-risca voz + visualizador. O `orb.js` já nasce com um gancho de estado externo
para o #3 encaixar sem retrabalho; abrir uma conversa antiga é **leitura** no #1
e vira "retomar de verdade" no #2.

## Objetivos (#1)

- Layout de 3 zonas: threads (esquerda estreita) + chat (centro) + orb da Jade
  (direita ~30%).
- Conversar por **texto** e por **voz (push-to-talk)** contra a sessão atual.
- **Voz em primeiro lugar:** toda resposta da Jade é falada automaticamente
  (TTS), com botão de mudo.
- **Orb** estilo JARVIS em Canvas 2D, reagindo à **amplitude real** do áudio
  (mic ao ouvir, TTS ao falar), com 4 estados: `idle`/`listening`/`thinking`/`speaking`.
- **Um turno por vez:** ao enviar (texto ou voz), a entrada trava até a resposta
  chegar.
- Lista de conversas existentes (as notas `.md`), abrindo em **leitura**.
- Tudo *privacy-first*: servido pela própria FastAPI (mesmo origin), sem serviços
  de nuvem para STT/TTS além dos que o backend já usa.

## Não-objetivos (#1)

- Retomar/continuar conversas antigas numa sessão viva (é o #2).
- Wake-word "Jade" / escuta contínua em background (é o #3).
- Multiusuário, autenticação, deploy remoto.
- STT/TTS por streaming em tempo real (usa os endpoints atuais, request/response).
- Toolchain de build (Node/npm), framework SPA — ver "Abordagem".

## Abordagem escolhida

**SPA estática em JS puro (sem build), servida pela FastAPI.** Uma pasta
`interfaces/frontend/` (HTML/CSS/JS por módulos) montada via `StaticFiles`.
Mesmo origin ⇒ sem CORS. Roda com o que já existe (`python main.py` sobe a API);
a UI fica em `/app`.

Alternativas consideradas e por que não (agora): **Vite + React** — traz
toolchain Node/npm e build a um repo Python, exagero para o #1; fica como pivô se
o estado do multi-thread (#2) ficar difícil em JS puro. **Tauri/Electron** —
salto de complexidade; melhor reconsiderar no #3 (daemon/janela nativa). O orb em
Canvas encapsulado (`orb.js`) sobrevive a qualquer pivô.

## Arquitetura

### Como roda
- A FastAPI serve `interfaces/frontend/` via `StaticFiles(directory=..., html=True)`
  montado em `/app`; `GET /` redireciona para `/app`.
- As rotas de API atuais permanecem inalteradas.
- `python main.py` (já existente) sobe a API. Melhoria opcional: imprimir a URL
  `http://127.0.0.1:8000/app` no startup para facilitar.

### Backend novo (pequeno, só-leitura — cabe no #1)
Dois endpoints para alimentar a lista de conversas a partir das notas `.md`:

- `GET /conversations` → `[{ "id": str, "title": str, "date": str }]`
  - `id` = nome do arquivo sem extensão (opaco; usado no path do próximo endpoint).
  - Varre `OBSIDIAN_VAULT_PATH / CONVERSATIONS_SUBDIR`, ordena por data desc.
- `GET /conversations/{id}` → `{ "title": str, "date": str, "turns": [{"user": str, "jade": str}] }`
  - Faz parse do corpo da nota (formato do `core/journal.py`: blocos
    `**Você:** …` / `**Jade:** …`).
  - **Proteção contra path traversal** (mesma técnica do `/voice/audio/{name}`:
    `Path(id).name`, resolver dentro da pasta e validar).
- Parsing isolado numa função pura `parse_conversation_note(text) -> list[Turn]`
  em `interfaces/` (ou `core/journal.py`), para ser testável sem HTTP.

Estes endpoints são só-leitura e não alteram o `ChatSession`. "Retomar" (carregar
os turnos numa sessão viva) fica para o #2.

### Frontend — módulos (cada um com um propósito único)

| Módulo | Responsabilidade | Depende de |
|---|---|---|
| `api.js` | Wrappers `fetch`: `sendMessage`, `reset`, `listConversations`, `getConversation`, `tts`, `voiceChat`. | endpoints |
| `state.js` | Estado da UI (thread atual, mensagens, flag `busy`, flag `muted`) + emissor de eventos simples (pub/sub). | — |
| `chat.js` | Renderiza balões, badge do modelo, envia texto, dispara TTS da resposta. | `api`, `state`, `orb` |
| `threads.js` | Lista conversas e abre uma em leitura. | `api`, `state` |
| `voice.js` | Push-to-talk (MediaRecorder), atalho de tecla, toca o áudio da resposta, alimenta o orb. | `api`, `state`, `orb` |
| `orb.js` | Visualizador Canvas + máquina de estados; recebe um `AnalyserNode` para reagir à amplitude. Expõe `setState(state)` e um gancho externo `onWakeword` (usado só no #3). | Web Audio |
| `app.js` | Bootstrap: instancia e conecta tudo. | todos |

## Layout

Grid CSS de 3 zonas (proporções ajustáveis):

```
┌───────────┬────────────────────────────┬─────────────────┐
│  THREADS  │           CHAT             │   JADE (orb)    │
│  (~18%)   │          (~52%)            │     (~30%)      │
│ + Novo    │  balões (você / Jade)      │      ( ● )      │
│ • hoje    │  [badge: claude/llama/tool]│   status:       │
│ • RPG…    │  ──────────────────────    │   "ouvindo…"    │
│ • ontem   │  [ campo ]   [🎤]  [enviar] │   [🔊/mudo]     │
└───────────┴────────────────────────────┴─────────────────┘
       └──────── esquerda ~70% ────────┘   └── direita 30% ─┘
```

Esquerda (~70%) reúne a lista de threads + a conversa atual. Direita (~30%) é a
presença da Jade (orb + rótulo de estado + botão de mudo). Tema escuro, brilho
verdeJade(#00BB77), verdePrimavera(#00FF7F), verdeEsmeralda(#00674F). A lista de threads pode ser recolhível para dar mais espaço ao chat.

## Fluxos de dados

### Texto (resposta sempre falada — voz em 1º lugar)
```
digita → state.busy=true (trava) → orb.setState("thinking")
       → api.sendMessage() → POST /chat {message} → {reply, model}
       → chat.js pinta os balões + badge do modelo
       → state.busy=false (libera a entrada)
       → se !muted: api.tts(reply) → POST /voice/tts → <audio> toca
              → orb.setState("speaking"), reage à amplitude do TTS
       → ao fim do áudio: orb.setState("idle")
```

### Voz (push-to-talk)
```
segura 🎤 (e não busy) → getUserMedia → orb.setState("listening") (reage ao MIC)
solta → MediaRecorder.stop() → blob → state.busy=true → orb "thinking"
      → POST /voice/chat → {transcription, reply, audio_url}
      → transcription vira balão "você"; reply vira balão "Jade"
      → state.busy=false
      → toca audio_url → orb "speaking" → ao fim → "idle"
```

### Abrir thread antiga (leitura)
```
load → GET /conversations → threads.js pinta a lista
click → GET /conversations/{id} → renderiza o transcript (só leitura)
"+ Novo" → POST /reset → limpa a área de chat, nova conversa
```

## Orb (visualizador)

- **Tecnologia:** Canvas 2D + `requestAnimationFrame`. Sem WebGL nem dependência
  externa. Encapsulado em `orb.js` para poder virar WebGL depois sem afetar o resto.
- **Áudio:** um `AudioContext` com um `AnalyserNode`. A fonte troca por estado:
  - `listening` → `MediaStreamSource` do microfone.
  - `speaking` → `MediaElementSource` do `<audio>` do TTS.
  - A cada frame lê `getByteFrequencyData()` e mapeia a energia para raio/brilho/
    agitação das partículas (função pura `amplitudeToVisual(bytes) -> params`).
- **Estados:**

| Estado | Quando | Visual |
|---|---|---|
| `idle` | parada | respiração lenta, brilho baixo |
| `listening` | gravando (segurando 🎤) | pulsa na amplitude do **mic** |
| `thinking` | aguardando o backend | anéis girando, sem áudio |
| `speaking` | TTS tocando | pulsa na amplitude do **TTS**, brilho alto |

- **Gancho para o #3:** `orb.js` expõe uma API de estado externa; o daemon de
  wake-word (futuro) apenas empurrará o estado para `listening` via evento
  (provavelmente WebSocket). Nenhum retrabalho no orb.

## Trava de entrada (concorrência) — um turno por vez

- `state.js` mantém `busy: bool`. Enviar (texto **ou** voz) faz `busy=true`;
  a resposta do backend faz `busy=false`.
- Enquanto `busy`: campo de texto desabilitado, botão enviar desabilitado,
  push-to-talk ignora o "segurar", orb em `thinking`, sinal visual
  ("Jade está pensando…", campo esmaecido).
- Garante um turno por vez e protege a sessão única do backend de chamadas
  sobrepostas.
- **Ponto de liberação:** quando `/chat` (ou `/voice/chat`) responde. Enquanto a
  Jade **fala** (`speaking`), a entrada **já está liberada** — dá para digitar a
  próxima mensagem enquanto o áudio toca.
- O redutor do `busy` (transições de estado) é uma função pura, testável.

## Tratamento de erros

| Situação | Comportamento |
|---|---|
| `503` (LLM fora / sem chave) | Balão de erro "Jade indisponível"; `busy` liberado; orb → `idle`. |
| Permissão de mic negada | Cai para texto-only; aviso discreto; 🎤 desabilitado. |
| Falha no TTS | Mostra o texto normalmente; pula o áudio; não trava a UI. |
| Rede/timeout | Balão de erro; libera a trava. |
| Sem conversas | Estado vazio na lista de threads. |
| Nota corrompida/sem turnos | `GET /conversations/{id}` retorna `turns: []`; UI mostra estado vazio. |

## Testes

- **Backend (pytest, CI-safe, só filesystem — sem Ollama):**
  - `GET /conversations` lista as notas de uma pasta de teste (tmp).
  - `GET /conversations/{id}` parseia os turnos corretamente.
  - `parse_conversation_note()` (função pura): turnos, nota vazia, formato inesperado.
  - Proteção contra path traversal (`id` com `../` é rejeitado/sanitizado).
- **Frontend (leve, honrando o "sem build"):** funções puras via `node --test`:
  - `parse`/render de transcript, `amplitudeToVisual`, redutor do `busy`.
  - O fluxo visual (orb, mic, TTS) valida-se manualmente / via skill `run`.
- Nenhum teste automatizado depende do LLM/Ollama.

## Arquivos afetados

- **Novos:** `interfaces/frontend/{index.html,styles.css,app.js,api.js,state.js,chat.js,threads.js,voice.js,orb.js}`;
  `tests/test_conversations_api.py`; testes JS em `interfaces/frontend/__tests__/` (ou similar).
- **Alterados:** `interfaces/api.py` (mount estático + 2 endpoints só-leitura +
  função de parsing); opcionalmente `main.py` (imprimir a URL no startup).

## Decisões resolvidas

- Stack: JS puro estático servido pela FastAPI (sem build).
- Toda resposta é falada automaticamente (TTS), com botão de mudo.
- Orb em Canvas 2D reagindo à amplitude real, 4 estados.
- Trava de entrada libera quando a resposta chega (o `speaking` não trava).
- Abrir conversa antiga é leitura no #1; retomar é #2.
- Wake-word é #3; o orb já provê o gancho de estado.
