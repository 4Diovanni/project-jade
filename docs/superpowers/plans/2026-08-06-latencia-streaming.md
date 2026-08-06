# Latência — streaming, sync_vault assíncrono, poda de histórico e lock de sessão — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer `core/chat.py::ChatSession` expor um gerador de streaming (`stream()`), consumido por um WebSocket novo (`/ws/chat`); tornar `sync_vault()` assíncrono desde a criação da sessão; podar `_history` por número de turnos; e serializar `/chat`, `/ws/chat` e `/voice/chat` com um lock único, sem corromper o histórico compartilhado.

**Architecture:** `core/chat.py` ganha um núcleo único (`_stream_impl()`) do qual `send()` (contrato antigo, inalterado) e `stream()` (novo, público) são as duas formas de consumo — inteiro de uma vez ou aos pedaços. `core/chat.py` continua 100% síncrono. `interfaces/api.py` é a única camada que fala `asyncio`: um `asyncio.Lock` compartilhado, e uma ponte thread-produtora → fila assíncrona (`_stream_to_ws`) para o WebSocket consumir o gerador síncrono sem travar o event loop. O frontend migra de um `fetch("/chat")` único para uma conexão WebSocket persistente.

**Tech Stack:** Python 3.11+, FastAPI/Starlette (WebSocket nativo, sem dependência nova — `uvicorn[standard]` já traz `websockets`), `threading`/`asyncio` da stdlib, `httpx.AsyncClient`/`ASGITransport` para testar concorrência real (já é dependência de dev), JavaScript puro (`node:test` para os testes de frontend, sem npm/bundler).

**Spec:** `docs/superpowers/specs/2026-08-05-latencia-streaming-design.md`

## Global Constraints

- **Identificadores de código em inglês; comentários e docstrings em PT-BR.** Convenção do projeto (`CLAUDE.md`).
- **Configuração sempre via `core.config.settings`** — nunca `os.getenv` espalhado.
- **Swallow de exceção usa `contextlib.suppress`** — o Bandit rejeita `try/except/pass`.
- **O contrato de `ChatSession.send()` não muda:** mesma assinatura (`message: str) -> str`), mesmo retorno, mesmos efeitos colaterais. As asserções dos testes já existentes em `tests/test_chat.py` não podem mudar — só acréscimo de testes novos.
- **`core/chat.py` continua inteiramente síncrono.** Nenhuma função nele vira `async`. Toda ponte com `asyncio` fica em `interfaces/api.py`.
- **Sem eventos de status pré-LLM no protocolo do WebSocket.** Só `{"type": "token"|"done"|"error", ...}` — nada de estágios internos (humor/RAG/tool) expostos ao cliente.
- **Sem reconexão automática com retomada no frontend.** Erro/desconexão mostra estado de erro; o usuário reenvia.
- **`core/journal.py::record()` reescrever a nota inteira a cada turno fica fora de escopo** — não tocar nesse método.
- **Poda de histórico é corte simples pelos últimos N turnos** — sem sumarização via LLM.
- **`/voice/chat` continua síncrono, sem streaming** — só ganha o lock de sessão.
- **Sem dependência nova.** `websockets` (via `uvicorn[standard]`) e `httpx` (dev) já cobrem tudo — não adicionar `pytest-asyncio`, `wsproto`, nem pacotes de frontend (`node --test` já roda sem npm/bundler).
- **Antes de cada commit:** `ruff check . && ruff format .`, `pytest`, e — nas tasks que tocam `interfaces/frontend/`, também `node --test interfaces/frontend/__tests__/`.
- **Workflow de git:** todo o trabalho acontece na branch `feat/latencia-streaming` (já criada a partir de `origin/main`). Nunca commitar na `main`.

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `core/config.py` | **Modificar.** Nova setting `HISTORY_MAX_TURNS`. |
| `.env.example` | **Modificar.** Entrada documentada para `HISTORY_MAX_TURNS`. |
| `core/chat.py` | **Modificar.** Thread de `sync_vault` no `__init__`; poda de histórico em `_record()`; `_stream_impl()`/`send()`/`stream()`. |
| `interfaces/api.py` | **Modificar.** `_session_lock`; `/chat` vira `async def` com lock; `/voice/chat` ganha o lock; `/ws/chat` novo + `_stream_to_ws()`. |
| `interfaces/frontend/api.js` | **Modificar.** `connectChat()` + `_handleChatEvent()` (WebSocket). |
| `interfaces/frontend/chat.js` | **Modificar.** `send()` passa a consumir o stream, bolha de resposta incremental. |
| `tests/test_chat.py` | **Modificar.** `FakeLLM` ganha `.stream()`; testes novos de poda, thread de sync, streaming. |
| `tests/test_chat_api.py` | **Criar.** Testes de `/chat` (lock), `/voice/chat`, `/ws/chat`. |
| `interfaces/frontend/__tests__/api.test.js` | **Criar.** Testes de `_handleChatEvent()`. |

---

### Task 1: Poda de histórico

**Files:**
- Modify: `core/config.py` (depois da linha 54, `GEMINI_API_KEY: str = ...`)
- Modify: `.env.example` (antes de `# ── Obsidian (RAG) ──`)
- Modify: `core/chat.py:121-126` (`_record()`)
- Test: `tests/test_chat.py`

**Interfaces:**
- Produces: `settings.HISTORY_MAX_TURNS: int` (default `20`).
- Produces: `_record()` mantém `ChatSession._history` com no máximo `2 * settings.HISTORY_MAX_TURNS` mensagens.

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar ao final de `tests/test_chat.py`:

```python
def test_send_poda_historico_alem_do_limite(monkeypatch):
    from core.config import settings

    monkeypatch.setattr(chat_mod, "route", lambda message: None)
    monkeypatch.setattr(chat_mod, "cloud_available", lambda: False)
    monkeypatch.setattr(settings, "HISTORY_MAX_TURNS", 2)
    sess = _session(use_tools=False)

    for i in range(5):
        sess.send(f"mensagem {i}")

    # 5 turnos enviados, só os últimos 2 (4 mensagens) ficam no histórico.
    assert len(sess._history) == 4
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `pytest tests/test_chat.py -v -k poda_historico`
Expected: FAIL — `AttributeError: <class 'core.config.Settings'> has no attribute 'HISTORY_MAX_TURNS'` (o `monkeypatch.setattr` exige que o atributo já exista).

- [ ] **Step 3: Adicionar a setting em `core/config.py`**

Depois de `GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")` (linha 54), antes de `# ── Obsidian ──`:

```python

    # ── Sessão / histórico ──
    # Quantas trocas (pergunta+resposta) ficam no histórico ativo do prompt.
    # Turnos mais antigos saem do prompt mas continuam na nota do Obsidian
    # (journal) e no RAG — nada se perde de memória de longo prazo, só sai do
    # contexto ativo enviado ao LLM a cada turno.
    HISTORY_MAX_TURNS: int = int(os.getenv("HISTORY_MAX_TURNS", "20"))
```

- [ ] **Step 4: Adicionar a entrada em `.env.example`**

Antes de `# ── Obsidian (RAG) ──`:

```
# ── Sessão / histórico ────────────────────────────────────────
# Quantas trocas (pergunta+resposta) ficam no histórico ativo do prompt.
# HISTORY_MAX_TURNS=20
```

- [ ] **Step 5: Implementar a poda em `_record()`**

Em `core/chat.py`, trocar:

```python
    def _record(self, message: str, text: str) -> None:
        self._history.append(HumanMessage(content=message))
        self._history.append(AIMessage(content=text))
        if self._journal is not None:
            with contextlib.suppress(Exception):
                self._journal.record(message, text)
```

Por:

```python
    def _record(self, message: str, text: str) -> None:
        self._history.append(HumanMessage(content=message))
        self._history.append(AIMessage(content=text))
        self._history = self._history[-2 * settings.HISTORY_MAX_TURNS :]
        if self._journal is not None:
            with contextlib.suppress(Exception):
                self._journal.record(message, text)
```

- [ ] **Step 6: Rodar e confirmar que passa**

Run: `pytest tests/test_chat.py -v`
Expected: PASS em todos — os testes pré-existentes mandam poucas mensagens (bem abaixo do default 20), então não são afetados.

- [ ] **Step 7: Lint e formatação**

Run: `ruff check core/config.py core/chat.py tests/test_chat.py && ruff format core/config.py core/chat.py tests/test_chat.py`

- [ ] **Step 8: Commit**

```bash
git add core/config.py .env.example core/chat.py tests/test_chat.py
git commit -m "feat(chat): poda o histórico para os últimos HISTORY_MAX_TURNS turnos"
```

---

### Task 2: `sync_vault` assíncrono desde a criação da sessão

**Files:**
- Modify: `core/chat.py` (`__init__`, novo `_sync_vault_safe`, `_ensure_synced`)
- Test: `tests/test_chat.py`

**Interfaces:**
- Consumes: nada de tasks anteriores.
- Produces: `ChatSession._sync_thread: threading.Thread | None` — não é usado fora de `core/chat.py`, mas `_ensure_synced()` (chamada por `_retrieve_context()`, já existente) passa a depender dele.

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar ao topo de `tests/test_chat.py`, junto aos imports já existentes:

```python
import threading
import time
```

Acrescentar ao final do arquivo:

```python
def test_sync_vault_roda_em_background_e_e_esperado_na_1a_busca(monkeypatch):
    """A thread nasce no __init__ (não bloqueia a criação da sessão) e
    _retrieve_context() só prossegue depois que ela termina."""
    sync_terminou = threading.Event()
    chamadas = []

    def _fake_sync_vault():
        chamadas.append("chamou")
        time.sleep(0.05)
        sync_terminou.set()
        return 0

    monkeypatch.setattr("core.memory.sync_vault", _fake_sync_vault)
    monkeypatch.setattr("core.memory.query_memory", lambda message: [])

    sess = _session(use_rag=True, use_tools=False)
    # __init__ não bloqueou esperando o sync (senão sync_terminou já estaria setado).
    assert not sync_terminou.is_set()

    context = sess._retrieve_context("oi")

    assert sync_terminou.is_set()
    assert context == ""
    assert len(chamadas) == 1

    # 2ª busca não dispara sync_vault de novo.
    sess._retrieve_context("de novo")
    assert len(chamadas) == 1
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `pytest tests/test_chat.py -v -k sync_vault_roda_em_background`
Expected: FAIL — `assert not sync_terminou.is_set()` já falha (hoje `_ensure_synced()` roda `sync_vault()` de forma síncrona dentro de `_retrieve_context()`, então nada dispara em background no `__init__`; dependendo da ordem, o teste pode falhar num ponto diferente, mas não passa).

- [ ] **Step 3: Adicionar `import threading` em `core/chat.py`**

Depois de `import contextlib` (linha 15):

```python
import contextlib
import threading
```

- [ ] **Step 4: Spawnar a thread no `__init__`**

Trocar:

```python
        #: qual cérebro respondeu o último turno: "tool" | "local" | "claude"
        self.last_model: str | None = None
        self._synced = False  # sincroniza o vault (arquivos novos) na 1ª busca
```

Por:

```python
        #: qual cérebro respondeu o último turno: "tool" | "local" | "claude"
        self.last_model: str | None = None
        # Sincroniza o vault (arquivos novos/alterados) em background, desde a
        # criação da sessão — não só antes da 1ª busca do RAG. Quando a sessão
        # nasce bem antes da 1ª mensagem chegar (ex.: ao abrir a tela do chat,
        # que conecta o WebSocket na hora), o custo desaparece na prática.
        self._sync_thread: threading.Thread | None = None
        if use_rag:
            self._sync_thread = threading.Thread(target=self._sync_vault_safe, daemon=True)
            self._sync_thread.start()
```

- [ ] **Step 5: Novo método `_sync_vault_safe` e reescrever `_ensure_synced`**

Trocar:

```python
    def _ensure_synced(self) -> None:
        """Indexa arquivos novos/alterados do vault — uma vez por sessão."""
        if self._synced:
            return
        self._synced = True
        with contextlib.suppress(Exception):
            from core.memory import sync_vault

            sync_vault()
```

Por:

```python
    def _sync_vault_safe(self) -> None:
        """Alvo da thread de sincronização — roda em background, blindado.
        Exceções levantadas numa thread não propagam para quem dá join() nela,
        então a proteção precisa estar aqui dentro, não em _ensure_synced()."""
        with contextlib.suppress(Exception):
            from core.memory import sync_vault

            sync_vault()

    def _ensure_synced(self) -> None:
        """Espera a sincronização em background terminar — custo zero se ela
        já tiver terminado, espera o resto se ainda estiver rodando."""
        if self._sync_thread is not None:
            self._sync_thread.join()
            self._sync_thread = None
```

- [ ] **Step 6: Rodar e confirmar que passa**

Run: `pytest tests/test_chat.py -v`
Expected: PASS em todos — inclusive `test_send_sem_contexto_do_rag_alcanca_a_nuvem` e `test_send_com_contexto_do_rag_fica_local_mesmo_informativa` (já usam `use_rag=True` com `core.memory.sync_vault` mockado; a thread só muda *quando* o mock roda, não o resultado).

- [ ] **Step 7: Lint e formatação**

Run: `ruff check core/chat.py tests/test_chat.py && ruff format core/chat.py tests/test_chat.py`

- [ ] **Step 8: Commit**

```bash
git add core/chat.py tests/test_chat.py
git commit -m "feat(chat): sync_vault roda em background desde a criação da sessão"
```

---

### Task 3: Núcleo único de streaming (`_stream_impl`, `send`, `stream`)

**Files:**
- Modify: `core/chat.py` (import `Iterator`; `send()` vira `_stream_impl()` + wrapper; novo `stream()`)
- Modify: `tests/test_chat.py` (`FakeLLM` ganha `.stream()`; testes novos)

**Interfaces:**
- Consumes: nada de tasks anteriores diretamente (independente de Task 1/2, mas todas tocam `core/chat.py`, então rodar em sequência evita conflito de merge).
- Produces: `ChatSession.stream(message: str) -> Iterator[str]` — usado pela Task 5 (`/ws/chat`). `ChatSession.send(message: str) -> str` mantém a assinatura de sempre.

- [ ] **Step 1: Dar ao `FakeLLM` um `.stream()`**

Em `tests/test_chat.py`, trocar a classe `FakeLLM`:

```python
class FakeLLM:
    """LLM falso: registra as mensagens recebidas e devolve um .content fixo."""

    def __init__(self, reply: str = "resposta do modelo") -> None:
        self.reply = reply
        self.calls: list = []

    def invoke(self, messages):
        self.calls.append(messages)
        return type("Msg", (), {"content": self.reply})()
```

Por:

```python
class FakeLLM:
    """LLM falso: registra as mensagens recebidas. invoke() devolve um
    .content fixo; stream() fatia a mesma resposta em pedaços, simulando
    geração incremental (com AIMessageChunk de verdade, para exercitar o
    merge por + que _stream_impl usa)."""

    def __init__(self, reply: str = "resposta do modelo") -> None:
        self.reply = reply
        self.calls: list = []

    def invoke(self, messages):
        self.calls.append(messages)
        return type("Msg", (), {"content": self.reply})()

    def stream(self, messages):
        self.calls.append(messages)
        from langchain_core.messages import AIMessageChunk

        meio = len(self.reply) // 2 or 1
        yield AIMessageChunk(content=self.reply[:meio])
        yield AIMessageChunk(content=self.reply[meio:], response_metadata={"eval_count": 7})
```

- [ ] **Step 2: Escrever os testes que falham**

Acrescentar ao final de `tests/test_chat.py`:

```python
def test_stream_gera_multiplos_chunks_que_concatenam_igual_ao_send(monkeypatch):
    """stream() devolve a mesma resposta que send(), só que em pedaços."""
    monkeypatch.setattr(chat_mod, "route", lambda message: None)
    monkeypatch.setattr(chat_mod, "cloud_available", lambda: False)
    sess = _session(use_tools=False)

    chunks = list(sess.stream("oi jade"))

    assert len(chunks) > 1
    assert "".join(chunks) == "resposta do modelo"
    assert sess.last_model == "local"


def test_stream_tool_devolve_um_unico_pedaco(monkeypatch):
    tool = FakeTool()
    monkeypatch.setattr(chat_mod, "route", lambda message: tool)
    sess = _session()

    chunks = list(sess.stream("abra a calculadora"))

    assert chunks == ["tool executou"]
    assert sess.last_model == "tool"


def test_stream_grava_no_historico_como_send(monkeypatch):
    """stream() tem os mesmos efeitos colaterais de send() (grava o turno)."""
    monkeypatch.setattr(chat_mod, "route", lambda message: None)
    monkeypatch.setattr(chat_mod, "cloud_available", lambda: False)
    sess = _session(use_tools=False)

    list(sess.stream("oi"))

    assert len(sess._history) == 2
```

- [ ] **Step 3: Rodar e confirmar que falha**

Run: `pytest tests/test_chat.py -v -k "test_stream_"`
Expected: FAIL — `AttributeError: 'ChatSession' object has no attribute 'stream'`.

- [ ] **Step 4: Adicionar o import de `Iterator`**

Depois de `import threading` (que a Task 2 acrescentou):

```python
import contextlib
import threading
from collections.abc import Iterator
```

- [ ] **Step 5: Reescrever `send()` como `_stream_impl()` + dois consumidores**

Trocar (o método `send` inteiro, do `def send` até o `return text` final):

```python
    def send(self, message: str) -> str:
        """Processa uma mensagem: humor → tool → senão conversa (modelo + RAG)."""
        # 1) O tom do usuário ajusta o humor da Jade (persistido).
        # `note` fica DENTRO do bloco: se `register()` falhar, `mood_level`
        # continua 0 e anotá-lo mesmo assim inventaria um delta de humor contra o
        # nível real de antes da mensagem. Sem anotação, quem lê sabe que não
        # houve medida. `timed("mood")` segue por fora, para cronometrar a
        # tentativa mesmo quando ela falha.
        mood_level = 0
        with timed("mood"), contextlib.suppress(Exception):
            from core.mood import register

            mood_level, _label = register(message)
            note(mood_level=mood_level)

        # 2) Roteamento para tools (as "mãos" da Jade).
        if self._use_tools:
            with timed("tool_route"):
                tool = route(message)
            if tool is not None:
                note(route="tool", tool=getattr(tool, "name", "?"))
                try:
                    with timed("tool_run"):
                        text = tool.run(message)
                except Exception as e:
                    text = f"Não consegui executar a ação: {e}"
                self.last_model = "tool"
                with timed("rag_sync"):
                    self._ensure_synced()
                with timed("journal"):
                    self._record(message, text)
                return text

        # 3) Conversa. Contexto do RAG é injetado só na chamada ao LLM.
        context = self._retrieve_context(message)
        llm = self._pick_llm(message, has_context=bool(context))

        user_turn = HumanMessage(content=message)
        if context:
            augmented = _CONTEXT_TEMPLATE.format(context=context, question=message)
            user_turn = HumanMessage(content=augmented)

        messages = [self._system_message(mood_level), *self._history, user_turn]
        with timed("llm"):
            response = llm.invoke(messages)
        _note_llm_usage(response)
        text = response.content if hasattr(response, "content") else str(response)
        with timed("journal"):
            self._record(message, text)
        return text
```

**Nota (fix da Task 2):** o `with timed("rag_sync"): self._ensure_synced()`
no ramo de tool acima não estava no desenho original — foi acrescentado
depois de uma revisão encontrar uma corrida real (thread de `sync_vault`
órfã quando o turno é roteado para tool, especialmente visível em
`bench/runner.py`, que cria uma `ChatSession` por caso sobre o mesmo índice
real). Ver o ledger da Task 2. Este "De:" já reflete o estado real do
arquivo depois do fix — copie-o como está.

Por:

```python
    def _stream_impl(self, message: str) -> Iterator[str]:
        """Gerador que produz a resposta token a token: humor → tool → senão
        conversa (modelo + RAG). send() e stream() são os dois jeitos de
        consumir este gerador — inteiro de uma vez, ou aos pedaços."""
        # 1) O tom do usuário ajusta o humor da Jade (persistido).
        # `note` fica DENTRO do bloco: se `register()` falhar, `mood_level`
        # continua 0 e anotá-lo mesmo assim inventaria um delta de humor contra o
        # nível real de antes da mensagem. Sem anotação, quem lê sabe que não
        # houve medida. `timed("mood")` segue por fora, para cronometrar a
        # tentativa mesmo quando ela falha.
        mood_level = 0
        with timed("mood"), contextlib.suppress(Exception):
            from core.mood import register

            mood_level, _label = register(message)
            note(mood_level=mood_level)

        # 2) Roteamento para tools (as "mãos" da Jade).
        if self._use_tools:
            with timed("tool_route"):
                tool = route(message)
            if tool is not None:
                note(route="tool", tool=getattr(tool, "name", "?"))
                try:
                    with timed("tool_run"):
                        text = tool.run(message)
                except Exception as e:
                    text = f"Não consegui executar a ação: {e}"
                self.last_model = "tool"
                yield text
                with timed("rag_sync"):
                    self._ensure_synced()
                with timed("journal"):
                    self._record(message, text)
                return

        # 3) Conversa. Contexto do RAG é injetado só na chamada ao LLM.
        context = self._retrieve_context(message)
        llm = self._pick_llm(message, has_context=bool(context))

        user_turn = HumanMessage(content=message)
        if context:
            augmented = _CONTEXT_TEMPLATE.format(context=context, question=message)
            user_turn = HumanMessage(content=augmented)

        messages = [self._system_message(mood_level), *self._history, user_turn]
        full = None
        with timed("llm"):
            for chunk in llm.stream(messages):
                full = chunk if full is None else full + chunk
                if chunk.content:
                    yield chunk.content
        _note_llm_usage(full)
        text = full.content if full is not None else ""
        with timed("journal"):
            self._record(message, text)

    def send(self, message: str) -> str:
        """Processa uma mensagem e devolve a resposta inteira de uma vez.
        Use stream() para consumi-la aos pedaços."""
        return "".join(self._stream_impl(message))

    def stream(self, message: str) -> Iterator[str]:
        """Como send(), mas devolve a resposta aos pedaços conforme o LLM
        gera (ou um único pedaço, no caso de uma tool)."""
        return self._stream_impl(message)
```

- [ ] **Step 6: Rodar e confirmar que passa**

Run: `pytest tests/test_chat.py -v`
Expected: PASS em **todos** os testes do arquivo — os pré-existentes (agora roteados por baixo do panos por `.stream()` em vez de `.invoke()`) e os três novos.

- [ ] **Step 7: Lint e formatação**

Run: `ruff check core/chat.py tests/test_chat.py && ruff format core/chat.py tests/test_chat.py`

- [ ] **Step 8: Commit**

```bash
git add core/chat.py tests/test_chat.py
git commit -m "feat(chat): núcleo único de streaming — send() e stream() sobre o mesmo gerador"
```

---

### Task 4: Lock de sessão — `/chat` vira `async def`, `/voice/chat` ganha o lock

**Files:**
- Modify: `interfaces/api.py`
- Create: `tests/test_chat_api.py`

**Interfaces:**
- Consumes: `ChatSession.send()` (contrato inalterado desde antes deste plano).
- Produces: `interfaces.api._session_lock: asyncio.Lock` — usado pela Task 5 (`/ws/chat`).

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/test_chat_api.py`:

```python
"""Testes dos endpoints de chat da API (/chat, /voice/chat, /ws/chat) — LLM,
tools, RAG e journal mockados (sem Ollama, sem rede, sem escrever no vault)."""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest
from fastapi.testclient import TestClient

import core.chat as chat_mod
import interfaces.api as api_mod
from core.config import settings


class FakeLLM:
    """Mesmo espírito do FakeLLM de tests/test_chat.py, local a este arquivo
    para não acoplar os dois módulos de teste."""

    def __init__(self, reply: str = "resposta da api") -> None:
        self.reply = reply

    def invoke(self, messages):
        return type("Msg", (), {"content": self.reply})()

    def stream(self, messages):
        from langchain_core.messages import AIMessageChunk

        meio = len(self.reply) // 2 or 1
        yield AIMessageChunk(content=self.reply[:meio])
        yield AIMessageChunk(content=self.reply[meio:])


@pytest.fixture(autouse=True)
def _isola_chat_api(monkeypatch, tmp_path):
    monkeypatch.setattr(chat_mod, "get_llm", lambda *a, **k: FakeLLM())
    monkeypatch.setattr(chat_mod, "build_system_prompt", lambda **k: "system prompt de teste")
    monkeypatch.setattr("core.mood.register", lambda message: (0, "neutra"))
    monkeypatch.setattr("core.memory.sync_vault", lambda: 0)
    monkeypatch.setattr("core.memory.query_memory", lambda message, k=None: [])
    monkeypatch.setattr(settings, "NOTES_DIR", tmp_path)
    monkeypatch.setattr(settings, "JOURNAL_ENABLED", False)
    api_mod._session = None
    yield
    api_mod._session = None


def test_chat_endpoint_devolve_resposta(monkeypatch):
    client = TestClient(api_mod.app)

    resp = client.post("/chat", json={"message": "oi, tudo bem?"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "resposta da api"
    assert body["model"] == "local"


def test_lock_serializa_chamadas_concorrentes(monkeypatch):
    """Duas chamadas concorrentes a /chat não podem se intercalar — uma
    espera a outra terminar antes de começar a processar."""
    ordem: list[str] = []

    def _fake_send(self, message):
        ordem.append(f"inicio:{message}")
        time.sleep(0.05)
        ordem.append(f"fim:{message}")
        return "resposta"

    monkeypatch.setattr(chat_mod.ChatSession, "send", _fake_send)

    async def _cenario():
        transport = httpx.ASGITransport(app=api_mod.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await asyncio.gather(
                client.post("/chat", json={"message": "A"}),
                client.post("/chat", json={"message": "B"}),
            )

    asyncio.run(_cenario())

    # Serializado: a 2ª só começa depois que a 1ª termina (em qualquer ordem).
    assert ordem in (
        ["inicio:A", "fim:A", "inicio:B", "fim:B"],
        ["inicio:B", "fim:B", "inicio:A", "fim:A"],
    )
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `pytest tests/test_chat_api.py -v`
Expected: `test_chat_endpoint_devolve_resposta` deve passar (é só um smoke test de algo que já funciona). `test_lock_serializa_chamadas_concorrentes` deve FALHAR — sem lock, o FastAPI roda handlers síncronos numa threadpool, então as duas chamadas concorrentes a `/chat` podem se intercalar (`ordem` sai fora dos dois padrões esperados).

- [ ] **Step 3: Adicionar o lock e converter `/chat` e `/voice/chat`**

Em `interfaces/api.py`, o projeto usa `ruff` com a regra `I` (isort) — a ordem
alfabética dos imports importa de verdade (`ruff check` falha se estiver
errada). Trocar o bloco de imports da stdlib (topo do arquivo, logo depois de
`from __future__ import annotations`):

```python
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
```

Por (`asyncio` entra antes de `logging`, ordem alfabética):

```python
import asyncio
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
```

Trocar:

```python
# Fase 1: uma única sessão de conversa (assistente pessoal = 1 usuário local).
# A sessão é criada de forma preguiçosa para a API subir mesmo sem o LLM pronto.
_session: ChatSession | None = None
```

Por:

```python
# Fase 1: uma única sessão de conversa (assistente pessoal = 1 usuário local).
# A sessão é criada de forma preguiçosa para a API subir mesmo sem o LLM pronto.
_session: ChatSession | None = None
# Serializa qualquer combinação de /chat, /ws/chat e /voice/chat — sem isto,
# duas requisições concorrentes corrompem o _history compartilhado.
_session_lock = asyncio.Lock()
```

Trocar:

```python
@app.post("/chat")
def chat(req: ChatRequest, background: BackgroundTasks) -> dict:
    session = _get_session()
    try:
        reply = session.send(req.message)
    except Exception as e:  # provider fora do ar, chave faltando, etc.
        # O detalhe do erro vai para o log do servidor, não para o cliente
        # (evita expor stack trace/implementação na resposta HTTP).
        logger.exception("Falha ao responder no /chat")
        raise HTTPException(status_code=503, detail="Jade indisponível no momento.") from e
```

Por:

```python
@app.post("/chat")
async def chat(req: ChatRequest, background: BackgroundTasks) -> dict:
    session = _get_session()
    try:
        async with _session_lock:
            reply = await asyncio.to_thread(session.send, req.message)
    except Exception as e:  # provider fora do ar, chave faltando, etc.
        # O detalhe do erro vai para o log do servidor, não para o cliente
        # (evita expor stack trace/implementação na resposta HTTP).
        logger.exception("Falha ao responder no /chat")
        raise HTTPException(status_code=503, detail="Jade indisponível no momento.") from e
```

Trocar (dentro de `voice_chat`):

```python
    tmp = _save_upload(file)
    try:
        transcription = transcribe(tmp)
        session = _get_session()
        reply = session.send(transcription)
        audio_path = synthesize_reply(reply)
```

Por:

```python
    tmp = _save_upload(file)
    try:
        transcription = transcribe(tmp)
        session = _get_session()
        async with _session_lock:
            reply = await asyncio.to_thread(session.send, transcription)
        audio_path = synthesize_reply(reply)
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `pytest tests/test_chat_api.py -v`
Expected: PASS nos dois testes.

Run: `pytest -q`
Expected: PASS em toda a suíte — nenhum teste pré-existente de `/voice/chat` ou `/reset` quebrou (nenhum deles mocka `session.send` de um jeito incompatível com `await asyncio.to_thread(...)`, porque `asyncio.to_thread` chama a função normalmente, só que numa thread).

- [ ] **Step 5: Lint e formatação**

Run: `ruff check interfaces/api.py tests/test_chat_api.py && ruff format interfaces/api.py tests/test_chat_api.py`

- [ ] **Step 6: Commit**

```bash
git add interfaces/api.py tests/test_chat_api.py
git commit -m "feat(api): lock de sessão serializa /chat e /voice/chat"
```

---

### Task 5: `/ws/chat` — WebSocket com streaming

**Files:**
- Modify: `interfaces/api.py`
- Modify: `tests/test_chat_api.py`

**Interfaces:**
- Consumes: `ChatSession.stream(message: str) -> Iterator[str]` (Task 3), `interfaces.api._session_lock` (Task 4).
- Produces: rota `/ws/chat`. Protocolo JSON: cliente manda `{"message": "..."}`; servidor manda `{"type": "token", "text": "..."}` por pedaço, depois `{"type": "done", "model": ..., "conversation_id": ...}` (se não houve erro) ou `{"type": "error", "detail": "..."}` (se houve — sem `"done"` depois de um `"error"` do mesmo turno).

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar ao final de `tests/test_chat_api.py`:

```python
def test_ws_chat_envia_tokens_e_termina_com_done():
    client = TestClient(api_mod.app)

    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"message": "oi, tudo bem?"})

        eventos = []
        while True:
            evento = ws.receive_json()
            eventos.append(evento)
            if evento["type"] == "done":
                break

    tipos = [e["type"] for e in eventos]
    assert tipos[-1] == "done"
    assert tipos.count("token") >= 1
    texto = "".join(e["text"] for e in eventos if e["type"] == "token")
    assert texto == "resposta da api"
    assert eventos[-1]["model"] == "local"


def test_ws_chat_erro_no_meio_nao_derruba_a_conexao(monkeypatch):
    """Um erro num turno vira {"type": "error"} (sem "done" depois) — a
    conexão continua aberta para a próxima mensagem."""

    def _stream_com_erro(self, message):
        if message == "explode":
            raise RuntimeError("boom")
        yield "ok"

    monkeypatch.setattr(chat_mod.ChatSession, "stream", _stream_com_erro)
    client = TestClient(api_mod.app)

    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"message": "explode"})
        erro = ws.receive_json()
        assert erro == {"type": "error", "detail": "boom"}

        # a conexão sobrevive: a próxima mensagem funciona normalmente.
        ws.send_json({"message": "oi"})
        tok = ws.receive_json()
        assert tok == {"type": "token", "text": "ok"}
        fim = ws.receive_json()
        assert fim["type"] == "done"
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `pytest tests/test_chat_api.py -v -k ws_chat`
Expected: FAIL — a rota `/ws/chat` ainda não existe (a conexão WebSocket falha).

- [ ] **Step 3: Implementar `_stream_to_ws` e `/ws/chat`**

Em `interfaces/api.py`, dois ajustes de import (ordem alfabética — `ruff
check` usa a regra `I`/isort). Primeiro, o bloco da stdlib que a Task 4
deixou:

```python
import asyncio
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
```

Por (`threading` entra depois de `tempfile`, ordem alfabética):

```python
import asyncio
import logging
import os
import re
import shutil
import tempfile
import threading
from pathlib import Path
```

Segundo, o import do FastAPI:

```python
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
```

Por:

```python
from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
```

Acrescentar, depois da definição de `_get_session()` e antes de `class ChatRequest(BaseModel):`:

```python
async def _stream_to_ws(websocket: WebSocket, session: ChatSession, message: str) -> bool:
    """Drena session.stream() (síncrono) numa thread e repassa cada pedaço
    pro WebSocket assim que chega — a ponte entre o mundo síncrono do
    ChatSession e o event loop assíncrono do FastAPI. Devolve True se o
    turno terminou sem erro (o chamador manda "done" só nesse caso)."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    sentinel = object()

    def _produce() -> None:
        try:
            for chunk in session.stream(message):
                loop.call_soon_threadsafe(queue.put_nowait, chunk)
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, e)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, sentinel)

    threading.Thread(target=_produce, daemon=True).start()
    while (item := await queue.get()) is not sentinel:
        if isinstance(item, Exception):
            await websocket.send_json({"type": "error", "detail": str(item)})
            return False
        await websocket.send_json({"type": "token", "text": item})
    return True


@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket) -> None:
    await websocket.accept()
    session = _get_session()
    try:
        while True:
            data = await websocket.receive_json()
            async with _session_lock:
                ok = await _stream_to_ws(websocket, session, data["message"])
            if ok:
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

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `pytest tests/test_chat_api.py -v`
Expected: PASS em todos os testes do arquivo.

Run: `pytest -q`
Expected: PASS em toda a suíte.

- [ ] **Step 5: Lint e formatação**

Run: `ruff check interfaces/api.py tests/test_chat_api.py && ruff format interfaces/api.py tests/test_chat_api.py`

- [ ] **Step 6: Commit**

```bash
git add interfaces/api.py tests/test_chat_api.py
git commit -m "feat(api): /ws/chat entrega a resposta token a token"
```

---

### Task 6: Frontend — chat de texto migra para o WebSocket

**Files:**
- Modify: `interfaces/frontend/api.js`
- Modify: `interfaces/frontend/chat.js`
- Create: `interfaces/frontend/__tests__/api.test.js`

**Interfaces:**
- Consumes: `/ws/chat` (Task 5), protocolo `{"type": "token"|"done"|"error", ...}`.
- Produces: `connectChat({ onToken, onDone, onError, onClose }) -> { send, close }` — usado por `chat.js`.

- [ ] **Step 1: Escrever o teste que falha**

Criar `interfaces/frontend/__tests__/api.test.js`:

```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { _handleChatEvent } from "../api.js";

test("token chama onToken com o texto", () => {
  let recebido = null;
  _handleChatEvent({ type: "token", text: "oi" }, { onToken: (t) => { recebido = t; } });
  assert.equal(recebido, "oi");
});

test("done chama onDone com o payload inteiro", () => {
  let recebido = null;
  _handleChatEvent(
    { type: "done", model: "local", conversation_id: "x" },
    { onDone: (d) => { recebido = d; } },
  );
  assert.deepEqual(recebido, { type: "done", model: "local", conversation_id: "x" });
});

test("error chama onError com o detail", () => {
  let recebido = null;
  _handleChatEvent({ type: "error", detail: "boom" }, { onError: (d) => { recebido = d; } });
  assert.equal(recebido, "boom");
});

test("tipo desconhecido não chama nenhum handler", () => {
  let chamou = false;
  const marcar = () => { chamou = true; };
  _handleChatEvent({ type: "?" }, { onToken: marcar, onDone: marcar, onError: marcar });
  assert.equal(chamou, false);
});

test("handler ausente não quebra", () => {
  assert.doesNotThrow(() => _handleChatEvent({ type: "token", text: "oi" }, {}));
});
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `node --test interfaces/frontend/__tests__/api.test.js`
Expected: FAIL — `_handleChatEvent` não existe em `api.js` ainda.

- [ ] **Step 3: Implementar `_handleChatEvent` e `connectChat` em `api.js`**

Em `interfaces/frontend/api.js`, acrescentar (pode ficar logo depois de `jsonPost`, antes de `sendMessage`):

```javascript
export function _handleChatEvent(data, { onToken, onDone, onError } = {}) {
  if (data.type === "token") onToken?.(data.text);
  else if (data.type === "done") onDone?.(data);
  else if (data.type === "error") onError?.(data.detail);
}

export function connectChat({ onToken, onDone, onError, onClose } = {}) {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${scheme}://${location.host}/ws/chat`);
  ws.onmessage = (ev) => _handleChatEvent(JSON.parse(ev.data), { onToken, onDone, onError });
  ws.onclose = () => onClose?.();
  return {
    send: (message) => ws.send(JSON.stringify({ message })),
    close: () => ws.close(),
  };
}
```

`sendMessage` (o `fetch("/chat")` antigo) **não é removido** — fica disponível para quem ainda precisar de uma chamada síncrona pontual (não é usado por `chat.js` depois deste task, mas remover é escopo além do pedido).

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `node --test interfaces/frontend/__tests__/api.test.js`
Expected: PASS em todos os 5 testes.

- [ ] **Step 5: Migrar `chat.js` para consumir o stream**

Em `interfaces/frontend/chat.js`, trocar a linha de import:

```javascript
import { sendMessage, ttsUrl } from "./api.js";
```

Por:

```javascript
import { connectChat, ttsUrl } from "./api.js";
```

Trocar a função `send` inteira (e o que vem antes dela para guardar o estado da bolha em construção). De:

```javascript
export function createChat({ store, orb, audioEl, onConversation }) {
  const list = document.getElementById("messages");
  let lastTtsUrl = null;
```

Para:

```javascript
export function createChat({ store, orb, audioEl, onConversation }) {
  const list = document.getElementById("messages");
  let lastTtsUrl = null;
  let currentBubble = null;
  let currentText = "";
```

E trocar a função `send` (do `async function send(text) {` até o fechamento `}` correspondente):

```javascript
  async function send(text) {
    if (!text || store.get().busy) return;
    addBubble("user", text);
    store.set({ busy: true });
    orb.setState("thinking");
    try {
      const { reply, model, conversation_id } = await sendMessage(text);
      addBubble("jade", reply, model);
      notifyConversation(conversation_id);
      store.set({ busy: false });
      await speak(reply);
    } catch (e) {
      console.error(e);
      addBubble("error", "Jade indisponível no momento.");
      store.set({ busy: false });
      orb.setState("idle");
    }
  }
```

Por (a conexão WebSocket abre uma vez, na criação do chat — os handlers ficam fechados sobre `currentBubble`/`currentText`):

```javascript
  const chatSocket = connectChat({
    onToken: (text) => {
      currentText += text;
      if (currentBubble) {
        currentBubble.innerHTML = renderMarkdown(currentText);
        list.scrollTop = list.scrollHeight; // segue a rolagem conforme o texto chega
      }
    },
    onDone: ({ model, conversation_id }) => {
      if (currentBubble && modelBadge(model)) {
        const b = document.createElement("div");
        b.className = "badge";
        b.textContent = modelBadge(model);
        list.appendChild(b);
      }
      notifyConversation(conversation_id);
      const textoFinal = currentText;
      currentBubble = null;
      currentText = "";
      store.set({ busy: false });
      speak(textoFinal);
    },
    onError: (detail) => {
      console.error(detail);
      if (currentBubble) currentBubble.remove();
      currentBubble = null;
      currentText = "";
      addBubble("error", "Jade indisponível no momento.");
      store.set({ busy: false });
      orb.setState("idle");
    },
    onClose: () => {
      // conexão caiu: se havia um turno em andamento, avisa — sem
      // reconexão automática (o usuário reenvia).
      if (store.get().busy) {
        addBubble("error", "Conexão perdida. Tente enviar de novo.");
        store.set({ busy: false });
        orb.setState("idle");
      }
    },
  });

  function send(text) {
    if (!text || store.get().busy) return;
    addBubble("user", text);
    currentBubble = addBubble("jade", "", null);
    currentText = "";
    store.set({ busy: true });
    orb.setState("thinking");
    chatSocket.send(text);
  }
```

- [ ] **Step 6: Verificar sintaxe**

Run: `node --check interfaces/frontend/api.js && node --check interfaces/frontend/chat.js`
Expected: sem saída (sintaxe válida).

- [ ] **Step 7: Rodar a suíte de frontend inteira**

Run: `node --test interfaces/frontend/__tests__/`
Expected: PASS em todos os arquivos (os já existentes + `api.test.js` novo).

- [ ] **Step 8: Commit**

```bash
git add interfaces/frontend/api.js interfaces/frontend/chat.js interfaces/frontend/__tests__/api.test.js
git commit -m "feat(frontend): chat de texto passa a consumir /ws/chat com streaming"
```

---

### Task 7: Validação final — quality gate, smoke test real e rerun do bench

**Files:**
- Nenhum arquivo de produção. Só validação + relatório novo em `bench/reports/`.

**Interfaces:**
- Consumes: tudo das Tasks 1-6.
- Produces: `bench/reports/<timestamp>-latencia-streaming.json`/`.md`; confirmação manual de que `/ws/chat` funciona de ponta a ponta contra Ollama de verdade (não só `FakeLLM`).

- [ ] **Step 1: Suíte de testes Python completa**

Run: `pytest`
Expected: PASS em tudo.

- [ ] **Step 2: Suíte de testes de frontend**

Run: `node --test interfaces/frontend/__tests__/`
Expected: PASS em tudo.

- [ ] **Step 3: Lint e formatação em tudo**

Run: `ruff check . && ruff format .`
Expected: sem erros; revisar qualquer arquivo que `ruff format` reescrever.

- [ ] **Step 4: SAST**

Run: `bandit -c pyproject.toml -r core tools interfaces bench main.py`
Expected: sem findings novos.

- [ ] **Step 5: Vulnerabilidades de dependências**

Run: `pip-audit -r requirements.txt --ignore-vuln PYSEC-2026-311`
Expected: sem vulnerabilidades novas.

- [ ] **Step 6: Smoke test real de `/ws/chat` (Ollama de verdade)**

Pré-requisito: Ollama rodando localmente (`qwen3:8b` disponível).

Subir o servidor em segundo plano (sem `reload=True`, para evitar o subprocesso do reloader):

```bash
python -c "import uvicorn; uvicorn.run('interfaces.api:app', host='127.0.0.1', port=8000)" &
```

Aguardar o servidor responder (`curl -s http://127.0.0.1:8000/health`), depois rodar este script descartável (**não commitar**), salvo como `scratch_smoke_ws.py` na raiz do repo:

```python
# scratch: smoke test manual de /ws/chat contra Ollama de verdade. NÃO COMMITAR.
import asyncio
import json
import time

import websockets


async def main():
    async with websockets.connect("ws://127.0.0.1:8000/ws/chat") as ws:
        inicio = time.perf_counter()
        await ws.send(json.dumps({"message": "oi, tudo bem?"}))
        primeiro_token = None
        n_tokens = 0
        while True:
            evento = json.loads(await ws.recv())
            if evento["type"] == "token":
                if primeiro_token is None:
                    primeiro_token = time.perf_counter() - inicio
                n_tokens += 1
                print(evento["text"], end="", flush=True)
            elif evento["type"] == "done":
                total = time.perf_counter() - inicio
                print()
                print(f"--- done: {n_tokens} tokens, 1º token em {primeiro_token:.2f}s, total {total:.2f}s ---")
                break
            elif evento["type"] == "error":
                print("ERRO:", evento["detail"])
                break


asyncio.run(main())
```

Run: `python scratch_smoke_ws.py`
Expected: o texto vai aparecendo aos poucos (não tudo de uma vez); `n_tokens > 1`; o tempo até o 1º token é bem menor que o tempo total (prova de que o streaming está entregando incrementalmente, não só no fim). Apagar o script depois (`rm scratch_smoke_ws.py`) e parar o servidor em segundo plano.

Se o Ollama não estiver disponível neste ambiente, pare aqui e sinalize isso — não pule esta verificação silenciosamente, já que é a única prova real (não mockada) de que a ponte thread→fila funciona.

- [ ] **Step 7: Rerun do bench**

Run: `python main.py bench --tag latencia-streaming`
Expected: escreve um novo par `.json`/`.md` em `bench/reports/`, com Delta contra `bench/reports/2026-08-05-225111-qualidade-rag-roteador.md` (o mais recente antes deste run).

- [ ] **Step 8: Ler o relatório novo e confirmar ausência de regressão**

Abrir o `.md` gerado no Step 7. Confirmar:
- `llm` p50/p95 fica estatisticamente parecido com o relatório anterior (o refactor do núcleo de streaming não muda o tempo total de geração de `send()`, só como ele é consumido por dentro — `bench/runner.py` continua chamando `send()`, síncrono, igual a sempre).
- Nenhuma métrica de qualidade (acerto de rota, recall@k, precisão de contexto) regrediu — nada nesta branch toca RAG/roteador.

Se algo regrediu sem explicação plausível, **pare** e investigue antes de prosseguir.

- [ ] **Step 9: Commit do relatório**

```bash
git add bench/reports/
git commit -m "$(cat <<'EOF'
chore(bench): relatório pós-streaming/lock/poda/sync_vault assíncrono

Rerun após o subprojeto #2 (streaming, lock de sessão, poda de histórico,
sync_vault em background). Comparar com o relatório anterior para o Delta —
esperado: métricas de qualidade inalteradas, llm p50/p95 sem regressão.
EOF
)"
```

- [ ] **Step 10: Push da branch**

Run: `git push -u origin feat/latencia-streaming`

(Abrir o PR e mergear fica para a skill `finishing-a-development-branch` — decisão do humano, não desta task.)

## Notas para quem executa

**A ordem das tasks é obrigatória até a Task 5.** Task 3 (núcleo de streaming) é independente de Task 1 (poda) e Task 2 (sync_vault) no sentido de que nenhuma consome a outra diretamente, mas todas editam `core/chat.py` — rodar fora de ordem multiplica o risco de conflito de merge para nada. Task 4 e Task 5 dependem de Task 3 (`stream()` precisa existir) e uma da outra (`_session_lock` da Task 4 é usado pela Task 5). Task 6 depende da Task 5 (`/ws/chat` precisa existir). Task 7 depende de tudo.

**Se um teste pré-existente quebrar em qualquer task**, pare. O contrato de `ChatSession.send()` não muda — é uma restrição global deste plano. Reverta a alteração e reavalie o passo que causou a quebra.

**Se o smoke test da Task 7 (Step 6) mostrar tokens chegando todos de uma vez** (sem intervalo perceptível entre o 1º e o último), desconfie antes de prosseguir: pode ser sinal de que `llm.stream()` do provider em uso não está de fato streamando (alguns providers/versões bufferizam internamente), ou que a ponte thread→fila está bloqueando até o fim antes de repassar qualquer chunk. Investigue antes de considerar a task concluída.
