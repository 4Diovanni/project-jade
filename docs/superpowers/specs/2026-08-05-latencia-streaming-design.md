# Latência — streaming, sync_vault assíncrono, poda de histórico e lock de sessão — Design

**Data:** 2026-08-05
**Status:** aprovado no brainstorming; pronto para o plano de implementação
**Escopo:** Subprojeto #2 de 4 (ver `docs/superpowers/specs/2026-08-03-regua-performance-jade-design.md`, seção "Decomposição")

## Contexto

O subprojeto #1 (A Régua) mediu; o subprojeto #3 (Qualidade) corrigiu a
correção das decisões (RAG e roteador dual-model). Este spec ataca a segunda
metade das seis hipóteses do spec original — as que são sobre **tempo**, não
sobre **decisão certa**.

Quatro defeitos confirmados na leitura do código atual (todos ainda presentes
depois do subprojeto #3):

1. **`/chat` não faz streaming** (`interfaces/api.py:45-63`). A resposta
   inteira é montada antes de voltar ao frontend — a tela fica parada durante
   toda a geração do LLM.
2. **`_session` é global e sem lock** (`interfaces/api.py:26`). Duas
   requisições concorrentes (`/chat`, `/voice/chat`, e agora `/ws/chat`)
   compartilham o mesmo histórico sem nenhuma exclusão mútua — corrompem o
   estado da conversa.
3. **`core/chat.py::ChatSession._history` cresce sem limite** (linha 68).
   Nenhuma poda existe; uma conversa longa o bastante estoura
   `OLLAMA_NUM_CTX=10240` e o Ollama corta o começo do prompt em silêncio.
4. **`sync_vault()` roda dentro do fluxo do 1º turno**
   (`core/chat.py::_ensure_synced()`), bloqueando a primeira busca do RAG. O
   bench do subprojeto #1 mediu esse custo como baixo (0,16-0,18s) com o
   índice já quente, mas nunca exercitou o cenário caro (índice frio, muitos
   arquivos novos) — o risco de um custo maior num cenário não medido
   continua real.

Um quinto achado, medido pelo bench do subprojeto #3
(`bench/reports/2026-08-05-225111-qualidade-rag-roteador.md`): o passo
`rag_embed` (embedding da pergunta do usuário via `nomic-embed-text`) custa
consistentemente **~2,1s por turno de conversa**, em três execuções
separadas do bench. Não é um dos quatro itens listados na decomposição
original e este spec não tenta reduzir esse custo (é uma pergunta de
desempenho do embedder/Ollama, não de arquitetura) — mas ele é relevante
para o desenho do streaming: mesmo com token a token, o usuário ainda espera
esses ~2,1s (mais o passo de humor) em silêncio antes do primeiro token
aparecer. Isso é aceito explicitamente (ver "Não-objetivos").

Um sexto achado (Hipótese 5 do spec original — `core/journal.py::record()`
reescreve a nota inteira do Obsidian a cada turno) foi identificado durante a
exploração deste spec e está **deliberadamente fora de escopo** — não fazia
parte da decomposição original do subprojeto #2, e corrigi-lo exige medir
primeiro o custo real (o bench atual não exercita conversas multi-turno com
o journal ligado). Fica registrado para um ciclo futuro.

## Objetivos

1. `/ws/chat` (WebSocket novo) entrega a resposta token a token, sem esperar
   a geração inteira terminar. `/chat` (REST) continua existindo, sem mudar
   de contrato, para `/voice/chat` e outros consumidores que só querem a
   resposta pronta.
2. Um `asyncio.Lock` único serializa qualquer combinação de chamadas
   concorrentes a `ChatSession.send()`/`stream()` entre `/chat`, `/ws/chat` e
   `/voice/chat` — sem corromper o histórico compartilhado.
3. `ChatSession._history` fica limitado a `HISTORY_MAX_TURNS` trocas — sem
   crescimento sem limite, sem estourar `OLLAMA_NUM_CTX` em conversas longas.
4. `sync_vault()` passa a rodar em background a partir da **criação** da
   sessão (não da primeira busca) — na prática, quando a sessão nasce bem
   antes da primeira mensagem chegar (o caso natural do WebSocket, que
   conecta ao abrir a tela), o custo desaparece da percepção do usuário.

## Não-objetivos

- **Reduzir o custo de `rag_embed` (~2,1s/turno).** É uma pergunta de
  desempenho do modelo de embedding/Ollama, ortogonal à arquitetura deste
  subprojeto. Streaming não elimina essa espera — só evita esperar o resto
  da geração inteira depois dela.
- **Eventos de status durante a fase pré-LLM** (ex.: "buscando na
  memória..."). Decisão explícita: o protocolo do WebSocket manda só tokens
  de resposta + um evento de fim (ou erro) — sem instrumentar estágios
  internos (humor/RAG/tool) para o usuário.
- **Reconexão automática com retomada** se o WebSocket cair no meio de uma
  resposta. O frontend mostra erro e o usuário reenvia — YAGNI para um
  assistente pessoal de um usuário só.
- **`core/journal.py::record()` reescrever a nota inteira a cada turno**
  (Hipótese 5 do spec original). Fora de escopo, registrado para um ciclo
  futuro (ver "Contexto").
- **Sumarização de histórico via LLM.** A poda é um corte simples pelos
  últimos N turnos — sem chamada extra ao LLM para resumir os turnos
  removidos.
- **Migrar `/voice/chat` ou qualquer outro consumidor para streaming.** Só
  o chat de texto do frontend usa `/ws/chat`; TTS precisa do texto completo
  de qualquer forma, então `/voice/chat` continua síncrono.

## Arquitetura

Quatro mudanças, uma delas central (o núcleo único de streaming em
`core/chat.py`) da qual as outras dependem indiretamente por compartilharem
a mesma sessão e o mesmo lock.

```
interfaces/api.py
  ├─ /ws/chat (NOVO, async def)   ─┐
  ├─ /chat (async def, era sync)  ─┼─ asyncio.Lock (_session_lock) único
  └─ /voice/chat (já era async)   ─┘

core/chat.py::ChatSession
  ├─ __init__(use_rag=True): spawna thread de sync_vault — roda desde a
  │  criação da sessão, não só antes da 1ª busca RAG.
  ├─ _stream_impl(message) -> Iterator[str]  (privado; NOVO)
  │     mesma orquestração de send() hoje: humor → tool → RAG → llm.stream()
  ├─ send(message) -> str  =  "".join(self._stream_impl(message))
  ├─ stream(message) -> Iterator[str]  =  self._stream_impl(message)  (NOVO)
  ├─ _record(): poda _history para as últimas HISTORY_MAX_TURNS trocas
  └─ _ensure_synced(): join() na thread de sync, em vez de rodar sync_vault
     direto
```

`core/chat.py` continua inteiramente síncrono — nenhuma função nele vira
`async`. A ponte para o mundo assíncrono do FastAPI vive só em
`interfaces/api.py`.

## Componentes

### `core/config.py`

```python
# Quantas trocas (pergunta+resposta) ficam no histórico ativo do prompt.
# Turnos mais antigos saem do prompt mas continuam na nota do Obsidian
# (journal) e no RAG — nada se perde de memória de longo prazo.
HISTORY_MAX_TURNS: int = int(os.getenv("HISTORY_MAX_TURNS", "20"))
```

### `core/chat.py`

- `ChatSession.__init__`: quando `use_rag=True`, cria
  `threading.Thread(target=self._sync_vault_safe, daemon=True)`, inicia e
  guarda em `self._sync_thread`. Quando `use_rag=False`,
  `self._sync_thread = None` (comportamento atual preservado — bench e
  testes que já usam `use_rag=False` não ganham uma thread à toa).
- `_sync_vault_safe()`: chama `sync_vault()` dentro de
  `contextlib.suppress(Exception)` — a mesma garantia de segurança que
  `_ensure_synced()` já tem hoje, só que agora dentro da thread (exceções
  levantadas numa thread não propagam para quem dá `join()`, então a
  proteção precisa estar dentro do alvo da thread).
- `_ensure_synced()`: corpo vira
  ```python
  if self._sync_thread is not None:
      self._sync_thread.join()
      self._sync_thread = None
  ```
  Substitui o flag `self._synced` — a própria thread virar `None` já marca
  "sincronizado, não repetir".
- `_stream_impl(message) -> Iterator[str]`: o corpo atual de `send()`
  (mood → tool → RAG → `_pick_llm`), com duas mudanças:
  - Ramo de tool: `yield text` uma vez (a resposta da tool já é instantânea,
    nada para fatiar), depois grava no journal e retorna — igual à ordem de
    hoje, só trocando `return text` por `yield text` seguido de `return`.
  - Ramo de conversa: troca
    ```python
    with timed("llm"):
        response = llm.invoke(messages)
    _note_llm_usage(response)
    text = response.content if hasattr(response, "content") else str(response)
    ```
    por
    ```python
    full = None
    with timed("llm"):
        for chunk in llm.stream(messages):
            full = chunk if full is None else full + chunk
            if chunk.content:
                yield chunk.content
    _note_llm_usage(full)
    text = full.content if full is not None else ""
    ```
    `timed("llm")` continua envolvendo o intervalo inteiro (do primeiro ao
    último chunk) — mesma semântica de hoje, números do bench continuam
    comparáveis. `_note_llm_usage` já sabe ler `response_metadata`/
    `usage_metadata` de um `AIMessage`/`AIMessageChunk` acumulado — sem
    mudança nele.
- `send(message: str) -> str`: `return "".join(self._stream_impl(message))`.
  Mesma assinatura, mesmo retorno, mesmos efeitos colaterais (grava no
  histórico e no journal do mesmo jeito, porque a gravação acontece dentro
  de `_stream_impl` depois do laço/yield, não em `send()`).
- `stream(message: str) -> Iterator[str]`: `return self._stream_impl(message)`.
  Novo, público.
- `_record()`: depois de appendar o turno,
  `self._history = self._history[-2 * settings.HISTORY_MAX_TURNS:]` (cada
  turno é 2 mensagens — Human + AI).

### `interfaces/api.py`

- Novo `_session_lock: asyncio.Lock = asyncio.Lock()` no nível do módulo,
  ao lado de `_session`.
- `/chat` deixa de ser `def` e vira `async def`. Corpo:
  ```python
  async with _session_lock:
      reply = await asyncio.to_thread(session.send, req.message)
  ```
  Contrato HTTP inalterado (mesmo request/response, mesmos códigos de erro).
- `/voice/chat` (já `async def`) ganha o mesmo
  `async with _session_lock: ... await asyncio.to_thread(session.send, ...)`
  em volta da chamada a `session.send(transcription)`.
- **`/ws/chat` (novo)**:
  ```python
  @app.websocket("/ws/chat")
  async def ws_chat(websocket: WebSocket) -> None:
      await websocket.accept()
      session = _get_session()
      try:
          while True:
              data = await websocket.receive_json()
              async with _session_lock:
                  await _stream_to_ws(websocket, session, data["message"])
              await websocket.send_json(
                  {
                      "type": "done",
                      "model": session.last_model,
                      "conversation_id": session.conversation_id,
                  }
              )
      except WebSocketDisconnect:
          pass
  ```
  Onde `_stream_to_ws` é a ponte thread-produtora → fila assíncrona:
  ```python
  async def _stream_to_ws(websocket: WebSocket, session: ChatSession, message: str) -> None:
      loop = asyncio.get_running_loop()
      queue: asyncio.Queue = asyncio.Queue()
      SENTINEL = object()

      def _produce() -> None:
          try:
              for chunk in session.stream(message):
                  loop.call_soon_threadsafe(queue.put_nowait, chunk)
          except Exception as e:
              loop.call_soon_threadsafe(queue.put_nowait, e)
          finally:
              loop.call_soon_threadsafe(queue.put_nowait, SENTINEL)

      threading.Thread(target=_produce, daemon=True).start()
      while (item := await queue.get()) is not SENTINEL:
          if isinstance(item, Exception):
              await websocket.send_json({"type": "error", "detail": str(item)})
              return
          await websocket.send_json({"type": "token", "text": item})
  ```
  `core/chat.py` continua síncrono; só esta função sabe que existe um
  event loop.

### Protocolo do WebSocket (JSON)

- Cliente → servidor: `{"message": "..."}`.
- Servidor → cliente, por chunk: `{"type": "token", "text": "..."}`.
- Servidor → cliente, ao final de um turno sem erro:
  `{"type": "done", "model": "...", "conversation_id": "..."}`.
- Servidor → cliente, se o turno falhar no meio: `{"type": "error", "detail": "..."}`
  (a conexão **continua aberta** para a próxima mensagem — um erro de turno
  não derruba o WebSocket).

### `interfaces/frontend/`

`chat.js`/`api.js` trocam o `fetch("/chat")` único (`sendMessage` em
`api.js:12`) por uma conexão WebSocket aberta quando a tela de chat carrega
(não quando o usuário manda a primeira mensagem — é esse timing que dá à
thread de `sync_vault` uma vantagem real de tempo). Tokens recebidos vão
sendo anexados à bolha de resposta em construção. Em erro ou desconexão: a
UI mostra um estado de erro; o usuário reenvia (o `fetch` de reset e outros
endpoints REST não mudam).

## Fluxo de dados

```
frontend abre WebSocket ao carregar a tela
  → interfaces/api.py: _get_session() cria ChatSession
      (spawna thread de sync_vault, se ainda não existir sessão)
  → usuário digita e manda {"message": "..."}
  → async with _session_lock:
      thread produtora drena session.stream(message):
        humor → tool_route → (RAG: join na thread de sync + busca) → llm.stream()
      cada chunk → {"type": "token", "text": "..."}
    (lock libera ao sair do "with", inclusive se algo lançar exceção)
  → {"type": "done", ...} ou {"type": "error", ...}
```

## Tratamento de erros

- Erro de tool ou de LLM dentro de `_stream_impl`: a tool já captura sua
  própria exceção hoje e devolve texto de erro como resposta (vira um único
  chunk `token`, igual ao comportamento atual de `send()`). Um erro do LLM
  que escape até `_stream_to_ws` vira `{"type": "error", ...}` — a conexão
  WebSocket **não** é derrubada por um erro de turno.
- `/chat` e `/voice/chat`: tratamento inalterado — a exceção que escapa de
  `await asyncio.to_thread(session.send, ...)` continua caindo no mesmo
  `try/except Exception → HTTPException(503)` que já existe.
- `async with _session_lock` sempre libera o lock ao sair do bloco, mesmo
  por exceção — um turno que falha não bloqueia os turnos seguintes.
- A thread de `sync_vault` está blindada por `contextlib.suppress(Exception)`
  dentro de `_sync_vault_safe()` — nunca propaga para `join()`.

## Testes

Em `tests/test_chat.py` (a `FakeLLM` existente ganha um método `.stream()`
que devolve alguns pedaços simulados, no mesmo espírito de `AIMessageChunk`):

- `stream()` gera múltiplos chunks cuja concatenação bate exatamente com o
  que `send()` devolveria para o mesmo `FakeLLM` — prova que os dois
  caminhos produzem o mesmo texto a partir da mesma orquestração.
- Todos os testes já existentes de `send()` continuam passando **sem
  alteração de asserção** — é a evidência de que o refactor para
  `"".join(self._stream_impl(...))` não mudou nada observável do lado de
  fora.
- Poda de histórico: depois de `HISTORY_MAX_TURNS + 1` turnos,
  `len(session._history) == 2 * settings.HISTORY_MAX_TURNS`.
- Thread de `sync_vault`: mocka `core.memory.sync_vault` com uma função que
  usa um `threading.Event` para simular demora; confirma que
  `_retrieve_context()` só prossegue depois que a thread termina (o
  `Event` foi setado), e que uma segunda mensagem na mesma sessão não
  dispara `sync_vault` de novo.

Em `tests/test_ws_chat.py` (novo) ou acrescentado a
`tests/test_conversations_api.py`:

- `/ws/chat` fim-a-fim via `TestClient(app).websocket_connect("/ws/chat")`:
  manda uma mensagem, espera a sequência `{"type": "token", ...}` (uma ou
  mais vezes) seguida de `{"type": "done", ...}`, com o LLM mockado (mesmo
  padrão de patch de `get_llm` que `tests/test_chat.py` já usa).
- Lock serializa: um teste `def test_lock_serializa(): asyncio.run(_cenario())`
  que dispara duas chamadas concorrentes (`asyncio.gather`) contra um LLM
  falso e lento (ex.: com um pequeno `await asyncio.sleep(...)` dentro de um
  `asyncio.to_thread`), e confirma pela ordem de entrada/saída registrada
  numa lista compartilhada que as duas execuções não se intercalam. Sem
  dependência nova — `asyncio.run` dentro de uma função de teste síncrona
  comum, sem precisar de `pytest-asyncio`.

Validação de sistema, não parte da suíte automatizada: depois da
implementação, rodar `python main.py bench` e comparar o novo relatório
contra `bench/reports/2026-08-05-225111-qualidade-rag-roteador.md` — o
`llm` p50/p95 deve ficar estatisticamente igual (o refactor para gerador não
muda o tempo total de geração, só como ele é consumido), confirmando que o
streaming não introduziu regressão de desempenho na via síncrona
(`send()`/bench).

## Entregável

- `core/config.py`: setting `HISTORY_MAX_TURNS`.
- `core/chat.py`: `_stream_impl()`, `send()` e `stream()` reescritos; thread
  de `sync_vault` no `__init__`; poda de histórico em `_record()`.
- `interfaces/api.py`: `/chat` vira `async def` com lock; `/voice/chat` ganha
  o lock; `/ws/chat` novo, com a ponte thread→fila.
- `interfaces/frontend/`: `chat.js`/`api.js` migram para WebSocket.
- Testes novos cobrindo os pontos acima, em `tests/test_chat.py` e um
  arquivo novo/estendido para `/ws/chat`.
- Rerun do bench pós-implementação, comparado ao relatório mais recente.
- Este spec e o plano de implementação, commitados em
  `docs/superpowers/`.

## Riscos

- **`HISTORY_MAX_TURNS=20` é um palpite, não um número calibrado.** Ao
  contrário de `RAG_MAX_DISTANCE` (subprojeto #3), não há neste ciclo uma
  medição de quantos tokens cada turno típico consome para validar que 20
  turnos cabem com folga em `OLLAMA_NUM_CTX=10240`. Se se mostrar generoso
  ou apertado demais em uso real, é um ajuste de configuração, não uma
  mudança de arquitetura.
- **`_transcript()` (usada para aprender fatos sobre o usuário ao encerrar a
  conversa) passa a enxergar só os últimos `HISTORY_MAX_TURNS` turnos** numa
  conversa muito longa, porque ela itera `self._history`. É uma consequência
  aceita da poda, não um bug — mas reduz a qualidade do aprendizado de
  perfil em conversas muito longas, e vale registrar caso alguém note a
  Jade "esquecendo" algo dito no início de uma conversa extensa.
- **A vantagem de tempo do `sync_vault` antecipado depende do timing real de
  uso.** Se o usuário manda a primeira mensagem imediatamente ao abrir a
  tela (sem tempo de digitação perceptível), a thread não teve vantagem
  nenhuma sobre o comportamento de hoje — o `join()` ainda bloqueia pelo
  tempo que faltar. O ganho é estatístico (médio), não uma garantia por
  turno.
- **A ponte thread-produtora + fila assíncrona (`_stream_to_ws`) é o código
  novo mais arriscado deste subprojeto** — é o único lugar onde threading e
  asyncio se encontram diretamente. Um erro aqui (esquecer `call_soon_threadsafe`,
  por exemplo, e mexer na fila direto de outra thread) causa corrupção de
  estado sutil, não uma falha óbvia. Merece atenção extra na implementação e
  na revisão.
