# Frontend da Jade #1 (Shell + Voz) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar a primeira UI local da Jade — layout de 3 zonas (threads + chat + orb JARVIS), conversa por texto e voz push-to-talk com TTS automático, orb Canvas reativo à amplitude real, e trava de um-turno-por-vez.

**Architecture:** SPA estática em JS puro (ES modules, sem build) servida pela própria FastAPI em `/app` (mesmo origin, sem CORS). A lógica pura (reducer de estado, mapeamento de áudio→visual, formatação) fica em módulos importáveis por Node para teste; os módulos que tocam DOM/Web Audio importam essa lógica. Dois endpoints só-leitura listam/abrem as conversas `.md` existentes.

**Tech Stack:** Python 3.11+ · FastAPI · `StaticFiles` · HTML/CSS/Canvas 2D · Web Audio API · MediaRecorder · pytest · `node --test`.

## Global Constraints

- *Privacy-first:* nenhum serviço de nuvem para STT/TTS além dos endpoints que o backend já expõe. UI servida same-origin pela FastAPI.
- Sem toolchain de build: ES modules puros no browser. Node é usado **apenas** para rodar os testes de função pura, nunca para servir/compilar a app.
- Identificadores em inglês; comentários e textos de UI em PT-BR.
- Configuração sempre via `core.config.settings` (nunca `os.getenv` solto).
- Testes automatizados não dependem de Ollama/LLM (CI-safe).
- Paleta do orb (tema escuro): verdeJade `#00BB77`, verdePrimavera `#00FF7F`, verdeEsmeralda `#00674F`.
- Trava de um-turno-por-vez: enviar (texto ou voz) trava a entrada; libera quando `/chat` (ou `/voice/chat`) responde. O estado `speaking` (TTS tocando) **não** trava.
- Abrir conversa antiga é **leitura** (retomar é o #2). Wake-word é o #3; o `orb.js` só expõe o gancho de estado.
- Workflow git: branch `feat/…` → commits frequentes → PR → CI verde → merge. Nunca commit direto na `main`.

---

## File Structure

**Backend (modificado/criado):**
- `core/journal.py` — adiciona `parse_conversation_note(text) -> list[dict]` (função pura de parsing).
- `interfaces/api.py` — adiciona: helper de frontmatter, endpoints `GET /conversations` e `GET /conversations/{conv_id}`, redirect `GET /` → `/app/`, e mount estático de `interfaces/frontend/`.
- `tests/test_conversations_api.py` — testes do parsing e dos endpoints.

**Frontend (criado em `interfaces/frontend/`):**
- `index.html` — casca das 3 zonas.
- `styles.css` — grid, tema escuro, paleta verde.
- `lib/state.js` — store pub/sub + flag `busy`/`muted` (pura, testável em Node).
- `lib/orb-visual.js` — `amplitudeToVisual(bytes)` (pura, testável).
- `lib/format.js` — `modelBadge(model)` (pura, testável).
- `api.js` — wrappers `fetch`.
- `orb.js` — visualizador Canvas + máquina de estados + Web Audio.
- `chat.js` — render de balões, envio de texto, TTS da resposta.
- `threads.js` — lista/abre conversas (leitura).
- `voice.js` — push-to-talk (MediaRecorder) + atalho + playback.
- `app.js` — bootstrap que conecta tudo.
- `__tests__/{state,orb-visual,format}.test.js` — testes Node das funções puras.

---

## Task 1: Parsing de conversa (função pura)

**Files:**
- Modify: `core/journal.py` (adicionar `parse_conversation_note`)
- Test: `tests/test_conversations_api.py`

**Interfaces:**
- Consumes: `core.notes.strip_frontmatter(text) -> str` (já existe).
- Produces: `parse_conversation_note(text: str) -> list[dict[str, str]]` — cada item `{"user": str, "jade": str}`, na ordem dos turnos.

- [ ] **Step 1: Escrever o teste que falha**

Criar `tests/test_conversations_api.py`:

```python
"""Testes do parsing de conversas e dos endpoints de leitura (CI-safe)."""

from core.journal import parse_conversation_note

_NOTE = """---
title: "abra a calculadora"
data: 2026-07-21
tags: [conversa, jade]
---

# abra a calculadora

Conversa com a Jade · [[Jade — Memória]] · #conversa/2026-07-21

**Você:** oi jade

**Jade:** Oi! Tudo bem?

**Você:** abra a calculadora

**Jade:** Abri calculadora.
"""


def test_parse_extrai_turnos_em_ordem():
    turns = parse_conversation_note(_NOTE)
    assert turns == [
        {"user": "oi jade", "jade": "Oi! Tudo bem?"},
        {"user": "abra a calculadora", "jade": "Abri calculadora."},
    ]


def test_parse_nota_sem_turnos_retorna_vazio():
    assert parse_conversation_note("---\ntags: []\n---\n\n# vazia\n") == []


def test_parse_resposta_multilinha():
    note = "**Você:** liste\n\n**Jade:** linha1\nlinha2\n"
    assert parse_conversation_note(note) == [{"user": "liste", "jade": "linha1\nlinha2"}]
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_conversations_api.py -v`
Expected: FAIL com `ImportError` / `cannot import name 'parse_conversation_note'`.

- [ ] **Step 3: Implementar a função**

Adicionar em `core/journal.py` (após os imports; `re` já está importado; adicionar o import de `strip_frontmatter`):

```python
from core.notes import strip_frontmatter

_TURN_RE = re.compile(
    r"\*\*(Você|Jade):\*\*\s*(.*?)(?=\n\*\*(?:Você|Jade):\*\*|\Z)",
    re.DOTALL,
)


def parse_conversation_note(text: str) -> list[dict[str, str]]:
    """Extrai os turnos (pergunta/resposta) do corpo de uma nota de conversa.

    Lê o formato gerado por `ConversationJournal._render` (blocos
    `**Você:** …` / `**Jade:** …`). Ignora frontmatter e cabeçalho. Um turno é
    um par Você→Jade; um 'Você' sem 'Jade' seguinte é descartado."""
    body = strip_frontmatter(text)
    turns: list[dict[str, str]] = []
    pending_user: str | None = None
    for role, content in _TURN_RE.findall(body):
        content = content.strip()
        if role == "Você":
            pending_user = content
        elif pending_user is not None:
            turns.append({"user": pending_user, "jade": content})
            pending_user = None
    return turns
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_conversations_api.py -v`
Expected: PASS (3 testes).

- [ ] **Step 5: Lint + commit**

```bash
ruff check core/journal.py tests/test_conversations_api.py && ruff format core/journal.py tests/test_conversations_api.py
git add core/journal.py tests/test_conversations_api.py
git commit -m "feat(journal): parse_conversation_note extrai turnos de uma nota"
```

---

## Task 2: Endpoints só-leitura + mount do frontend

**Files:**
- Modify: `interfaces/api.py`
- Test: `tests/test_conversations_api.py`

**Interfaces:**
- Consumes: `core.journal.parse_conversation_note` (Task 1); `core.config.settings.OBSIDIAN_VAULT_PATH`, `settings.CONVERSATIONS_SUBDIR`.
- Produces (HTTP):
  - `GET /conversations` → `list[{"id": str, "title": str, "date": str}]` (ordem: mais recente primeiro).
  - `GET /conversations/{conv_id}` → `{"title": str, "date": str, "turns": [{"user","jade"}]}`; `404` se não existir.
  - `GET /` → redirect 307 para `/app/`.
  - `/app/...` → estáticos de `interfaces/frontend/`.

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar em `tests/test_conversations_api.py`:

```python
from fastapi.testclient import TestClient

from core.config import settings
from interfaces.api import app


def _write_note(tmp_path, name, title, date, body):
    folder = tmp_path / settings.CONVERSATIONS_SUBDIR
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(
        f'---\ntitle: "{title}"\ndata: {date}\ntags: [conversa, jade]\n---\n\n'
        f"# {title}\n\n{body}\n",
        encoding="utf-8",
    )


def test_list_and_get_conversations(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_PATH", tmp_path)
    _write_note(tmp_path, "2026-07-20_100000 — antiga.md", "antiga", "2026-07-20", "**Você:** a\n\n**Jade:** b")
    _write_note(tmp_path, "2026-07-21_100000 — nova.md", "nova", "2026-07-21", "**Você:** c\n\n**Jade:** d")
    client = TestClient(app)

    lst = client.get("/conversations").json()
    assert [c["title"] for c in lst] == ["nova", "antiga"]  # mais recente primeiro
    conv_id = lst[0]["id"]

    got = client.get(f"/conversations/{conv_id}").json()
    assert got["title"] == "nova"
    assert got["turns"] == [{"user": "c", "jade": "d"}]


def test_get_conversation_inexistente_404(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_PATH", tmp_path)
    (tmp_path / settings.CONVERSATIONS_SUBDIR).mkdir(parents=True, exist_ok=True)
    assert TestClient(app).get("/conversations/nao_existe").status_code == 404


def test_get_conversation_bloqueia_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_PATH", tmp_path)
    (tmp_path / settings.CONVERSATIONS_SUBDIR).mkdir(parents=True, exist_ok=True)
    # '../../secret' deve ser sanitizado para o basename e resultar em 404.
    assert TestClient(app).get("/conversations/..%2f..%2fsecret").status_code in (404, 400)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_conversations_api.py -k "conversations or traversal or inexistente" -v`
Expected: FAIL (endpoints ainda não existem → 404 nas rotas ou AttributeError).

- [ ] **Step 3: Implementar no `interfaces/api.py`**

Adicionar aos imports do topo:

```python
from pathlib import Path
import re

from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from core.journal import parse_conversation_note
```

Adicionar os helpers e endpoints (antes do bloco de voz; o mount fica no fim do arquivo):

```python
FRONTEND_DIR = Path(__file__).parent / "frontend"

_FM_FIELD = {
    key: re.compile(rf'(?m)^{key}:\s*"?(.*?)"?\s*$') for key in ("title", "data")
}


def _frontmatter_field(text: str, key: str) -> str:
    m = _FM_FIELD[key].search(text)
    return m.group(1).strip() if m else ""


def _conversations_dir() -> Path:
    return settings.OBSIDIAN_VAULT_PATH / settings.CONVERSATIONS_SUBDIR


@app.get("/conversations")
def list_conversations() -> list[dict]:
    """Lista as conversas salvas (notas .md), mais recente primeiro."""
    folder = _conversations_dir()
    if not folder.is_dir():
        return []
    items: list[dict] = []
    for md in sorted(folder.glob("*.md"), key=lambda p: p.name, reverse=True):
        text = md.read_text(encoding="utf-8", errors="ignore")
        items.append(
            {
                "id": md.stem,
                "title": _frontmatter_field(text, "title") or md.stem,
                "date": _frontmatter_field(text, "data"),
            }
        )
    return items


@app.get("/conversations/{conv_id}")
def get_conversation(conv_id: str) -> dict:
    """Retorna uma conversa parseada (só leitura)."""
    safe = Path(conv_id).name  # anti path-traversal
    path = _conversations_dir() / f"{safe}.md"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    text = path.read_text(encoding="utf-8", errors="ignore")
    return {
        "title": _frontmatter_field(text, "title") or safe,
        "date": _frontmatter_field(text, "data"),
        "turns": parse_conversation_note(text),
    }


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/app/")
```

No **fim** do arquivo (o mount precisa vir depois das rotas; garante a pasta para o `StaticFiles` não quebrar no import):

```python
FRONTEND_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_conversations_api.py -v`
Expected: PASS (todos). Depois `python -m pytest -q` para garantir que nada quebrou.

- [ ] **Step 5: Lint + commit**

```bash
ruff check interfaces/api.py tests/test_conversations_api.py && ruff format interfaces/api.py tests/test_conversations_api.py
git add interfaces/api.py tests/test_conversations_api.py
git commit -m "feat(api): endpoints de leitura de conversas + mount do frontend em /app"
```

---

## Task 3: Casca HTML/CSS (layout de 3 zonas)

**Files:**
- Create: `interfaces/frontend/index.html`
- Create: `interfaces/frontend/styles.css`

**Interfaces:**
- Produces (IDs de DOM consumidos pelos módulos JS): `#threads-list`, `#new-chat`, `#messages`, `#composer`, `#composer-input`, `#send-btn`, `#mic-btn`, `#mute-btn`, `#orb-canvas`, `#orb-status`.

- [ ] **Step 1: Criar `index.html`**

```html
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Jade</title>
  <link rel="stylesheet" href="styles.css" />
</head>
<body>
  <main class="layout">
    <aside class="threads" aria-label="Conversas">
      <button id="new-chat" class="new-chat">+ Novo</button>
      <ul id="threads-list" class="threads-list"></ul>
    </aside>

    <section class="chat">
      <div id="messages" class="messages" aria-live="polite"></div>
      <form id="composer" class="composer" autocomplete="off">
        <input id="composer-input" class="composer-input" type="text"
               placeholder="Fale com a Jade…" />
        <button id="mic-btn" class="mic-btn" type="button" title="Segure para falar">🎤</button>
        <button id="send-btn" class="send-btn" type="submit">Enviar</button>
      </form>
    </section>

    <aside class="jade" aria-label="Jade">
      <canvas id="orb-canvas" class="orb-canvas" width="360" height="360"></canvas>
      <div id="orb-status" class="orb-status">ociosa</div>
      <button id="mute-btn" class="mute-btn" type="button" aria-pressed="false">🔊</button>
    </aside>
  </main>

  <script type="module" src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Criar `styles.css`**

```css
:root {
  --jade: #00bb77;
  --jade-spring: #00ff7f;
  --jade-emerald: #00674f;
  --bg: #0a0f0d;
  --panel: #0f1512;
  --text: #d8f5e6;
  --muted: #6f8a7e;
}
* { box-sizing: border-box; }
body { margin: 0; height: 100vh; background: var(--bg); color: var(--text);
  font-family: system-ui, sans-serif; }
.layout { display: grid; grid-template-columns: 18% 52% 30%; height: 100vh; }
.threads, .jade { background: var(--panel); border-left: 1px solid #16211c;
  border-right: 1px solid #16211c; padding: 12px; overflow-y: auto; }
.new-chat { width: 100%; padding: 8px; background: transparent; color: var(--jade-spring);
  border: 1px solid var(--jade-emerald); border-radius: 8px; cursor: pointer; }
.threads-list { list-style: none; padding: 0; margin: 12px 0 0; }
.threads-list li { padding: 8px; border-radius: 6px; cursor: pointer; color: var(--muted);
  font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.threads-list li:hover, .threads-list li.active { background: #14201b; color: var(--text); }
.chat { display: flex; flex-direction: column; min-width: 0; }
.messages { flex: 1; overflow-y: auto; padding: 20px; display: flex;
  flex-direction: column; gap: 12px; }
.bubble { max-width: 80%; padding: 10px 14px; border-radius: 12px; line-height: 1.4;
  white-space: pre-wrap; word-wrap: break-word; }
.bubble.user { align-self: flex-end; background: var(--jade-emerald); color: #eafff5; }
.bubble.jade { align-self: flex-start; background: #14201b; }
.bubble.error { align-self: flex-start; background: #3a1414; color: #ffd9d9; }
.badge { font-size: 11px; color: var(--muted); margin-top: 4px; align-self: flex-start; }
.composer { display: flex; gap: 8px; padding: 12px; border-top: 1px solid #16211c; }
.composer-input { flex: 1; padding: 10px; border-radius: 8px; border: 1px solid #22332b;
  background: #0c1210; color: var(--text); }
.composer-input:disabled { opacity: 0.5; }
.mic-btn, .send-btn, .mute-btn { padding: 10px 14px; border-radius: 8px; cursor: pointer;
  border: 1px solid var(--jade-emerald); background: transparent; color: var(--text); }
.mic-btn.recording { background: var(--jade); color: #04120c; }
button:disabled { opacity: 0.4; cursor: not-allowed; }
.jade { display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 16px; }
.orb-canvas { width: 100%; max-width: 320px; aspect-ratio: 1; }
.orb-status { color: var(--jade-spring); letter-spacing: 1px; text-transform: lowercase; }
```

- [ ] **Step 3: Verificar que é servido**

```bash
python -c "import uvicorn; uvicorn.run('interfaces.api:app', port=8000)" &
sleep 3
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/app/   # espera 200
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/       # espera 307
kill %1
```

Expected: `/app/` → `200`; `/` → `307`. (No Windows/PowerShell, abrir `http://127.0.0.1:8000/` no navegador e confirmar o layout de 3 zonas.)

- [ ] **Step 4: Commit**

```bash
git add interfaces/frontend/index.html interfaces/frontend/styles.css
git commit -m "feat(frontend): casca HTML/CSS do layout de 3 zonas (tema verde)"
```

---

## Task 4: Módulos de lógica pura + testes Node

**Files:**
- Create: `interfaces/frontend/lib/state.js`
- Create: `interfaces/frontend/lib/orb-visual.js`
- Create: `interfaces/frontend/lib/format.js`
- Test: `interfaces/frontend/__tests__/state.test.js`, `orb-visual.test.js`, `format.test.js`

**Interfaces:**
- Produces:
  - `createStore(initial?) -> { get(), set(patch), subscribe(fn) -> unsubscribe }` (state.js). Estado inicial default: `{ busy: false, muted: false, currentThread: null }`.
  - `amplitudeToVisual(bytes: Uint8Array|number[]) -> { energy: number, radius: number, glow: number }` (orb-visual.js). `energy` ∈ [0,1]; `radius`/`glow` crescem com a energia.
  - `modelBadge(model: string) -> string` (format.js): `"claude"→"☁️ Claude"`, `"llama3"→"local"`, `"tool"→"ação"`, outro→`""`.

- [ ] **Step 1: Escrever os testes que falham**

`interfaces/frontend/__tests__/state.test.js`:

```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { createStore } from "../lib/state.js";

test("estado inicial default", () => {
  const s = createStore();
  assert.deepEqual(s.get(), { busy: false, muted: false, currentThread: null });
});

test("set faz merge e notifica assinantes", () => {
  const s = createStore();
  let seen = null;
  s.subscribe((st) => { seen = st; });
  s.set({ busy: true });
  assert.equal(s.get().busy, true);
  assert.equal(s.get().muted, false);
  assert.equal(seen.busy, true);
});

test("unsubscribe para de notificar", () => {
  const s = createStore();
  let count = 0;
  const off = s.subscribe(() => { count++; });
  s.set({ busy: true });
  off();
  s.set({ busy: false });
  assert.equal(count, 1);
});
```

`interfaces/frontend/__tests__/orb-visual.test.js`:

```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { amplitudeToVisual } from "../lib/orb-visual.js";

test("silêncio → energia 0 e raio base", () => {
  const v = amplitudeToVisual(new Uint8Array([0, 0, 0, 0]));
  assert.equal(v.energy, 0);
  assert.ok(v.radius > 0);
});

test("mais amplitude → mais raio e brilho (monotônico)", () => {
  const baixo = amplitudeToVisual(new Uint8Array([40, 40, 40, 40]));
  const alto = amplitudeToVisual(new Uint8Array([220, 220, 220, 220]));
  assert.ok(alto.energy > baixo.energy);
  assert.ok(alto.radius > baixo.radius);
  assert.ok(alto.glow > baixo.glow);
});

test("array vazio não quebra", () => {
  const v = amplitudeToVisual(new Uint8Array([]));
  assert.equal(v.energy, 0);
});
```

`interfaces/frontend/__tests__/format.test.js`:

```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { modelBadge } from "../lib/format.js";

test("mapeia os modelos conhecidos", () => {
  assert.equal(modelBadge("claude"), "☁️ Claude");
  assert.equal(modelBadge("llama3"), "local");
  assert.equal(modelBadge("tool"), "ação");
});

test("modelo desconhecido → vazio", () => {
  assert.equal(modelBadge("gpt"), "");
  assert.equal(modelBadge(null), "");
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `node --test interfaces/frontend/__tests__/`
Expected: FAIL (`Cannot find module ../lib/state.js`).

- [ ] **Step 3: Implementar os módulos**

`interfaces/frontend/lib/state.js`:

```javascript
// Store pub/sub mínimo (sem dependências, testável em Node).
export function createStore(initial = {}) {
  let state = { busy: false, muted: false, currentThread: null, ...initial };
  const subs = new Set();
  return {
    get: () => state,
    set(patch) {
      state = { ...state, ...patch };
      for (const fn of subs) fn(state);
    },
    subscribe(fn) {
      subs.add(fn);
      return () => subs.delete(fn);
    },
  };
}
```

`interfaces/frontend/lib/orb-visual.js`:

```javascript
// Mapeia dados de frequência (0..255) para parâmetros visuais do orb. Puro.
const BASE_RADIUS = 0.35; // fração do menor lado do canvas
const MAX_GROWTH = 0.45;

export function amplitudeToVisual(bytes) {
  const n = bytes.length;
  let sum = 0;
  for (let i = 0; i < n; i++) sum += bytes[i];
  const energy = n ? sum / n / 255 : 0; // 0..1
  return {
    energy,
    radius: BASE_RADIUS + MAX_GROWTH * energy,
    glow: 8 + 40 * energy,
  };
}
```

`interfaces/frontend/lib/format.js`:

```javascript
// Rótulo curto de qual "cérebro" respondeu o turno. Puro.
const LABELS = { claude: "☁️ Claude", llama3: "local", tool: "ação" };

export function modelBadge(model) {
  return LABELS[model] || "";
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `node --test interfaces/frontend/__tests__/`
Expected: PASS (todos os testes).

- [ ] **Step 5: Commit**

```bash
git add interfaces/frontend/lib interfaces/frontend/__tests__
git commit -m "feat(frontend): módulos puros (store, orb-visual, format) + testes node"
```

---

## Task 5: Cliente da API (`api.js`)

**Files:**
- Create: `interfaces/frontend/api.js`

**Interfaces:**
- Consumes (HTTP): endpoints da Task 2 + `/chat`, `/reset`, `/voice/tts`, `/voice/chat`.
- Produces:
  - `sendMessage(message) -> Promise<{reply, model}>`
  - `reset() -> Promise<void>`
  - `listConversations() -> Promise<Array<{id,title,date}>>`
  - `getConversation(id) -> Promise<{title,date,turns}>`
  - `ttsUrl(text) -> Promise<string>` (object URL de um mp3)
  - `voiceChat(blob) -> Promise<{transcription, reply, audio_url}>`

- [ ] **Step 1: Implementar `api.js`**

```javascript
// Wrappers de fetch para a API da Jade (mesmo origin).
async function jsonPost(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json();
}

export const sendMessage = (message) => jsonPost("/chat", { message });
export const reset = () => fetch("/reset", { method: "POST" }).then(() => undefined);
export const listConversations = () => fetch("/conversations").then((r) => r.json());
export const getConversation = (id) =>
  fetch(`/conversations/${encodeURIComponent(id)}`).then((r) => {
    if (!r.ok) throw new Error(`/conversations/${id} → ${r.status}`);
    return r.json();
  });

export async function ttsUrl(text) {
  const res = await fetch("/voice/tts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error(`/voice/tts → ${res.status}`);
  return URL.createObjectURL(await res.blob());
}

export async function voiceChat(blob) {
  const form = new FormData();
  form.append("file", blob, "fala.webm");
  const res = await fetch("/voice/chat", { method: "POST", body: form });
  if (!res.ok) throw new Error(`/voice/chat → ${res.status}`);
  return res.json();
}
```

- [ ] **Step 2: Verificação de sintaxe**

Run: `node --check interfaces/frontend/api.js`
Expected: sem saída (sintaxe OK).

- [ ] **Step 3: Commit**

```bash
git add interfaces/frontend/api.js
git commit -m "feat(frontend): cliente de API (chat, voz, conversas)"
```

---

## Task 6: Orb visualizador (`orb.js`)

**Files:**
- Create: `interfaces/frontend/orb.js`

**Interfaces:**
- Consumes: `amplitudeToVisual` (Task 4); Web Audio API.
- Produces:
  - `createOrb(canvas) -> { setState(name), connectMic(stream), connectAudio(audioEl), onWakeword(fn) }`
  - Estados válidos de `setState`: `"idle" | "listening" | "thinking" | "speaking"`.
  - `onWakeword(fn)` apenas registra um callback (gancho para o #3); não faz nada no #1.

- [ ] **Step 1: Implementar `orb.js`**

```javascript
import { amplitudeToVisual } from "./lib/orb-visual.js";

const COLORS = { jade: "#00bb77", spring: "#00ff7f", emerald: "#00674f" };

export function createOrb(canvas) {
  const ctx = canvas.getContext("2d");
  let state = "idle";
  let audioCtx = null;
  let analyser = null;
  let micSource = null;
  let mediaSource = null;
  const bins = 64;
  let bytes = new Uint8Array(bins);
  let wakewordCb = null;
  let t = 0;

  function ensureAudio() {
    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = bins * 2;
      bytes = new Uint8Array(analyser.frequencyBinCount);
    }
    if (audioCtx.state === "suspended") audioCtx.resume();
    return audioCtx;
  }

  function draw() {
    t += 0.03;
    const w = canvas.width, h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    let energy = 0;
    if (analyser && (state === "listening" || state === "speaking")) {
      analyser.getByteFrequencyData(bytes);
      energy = amplitudeToVisual(bytes).energy;
    } else if (state === "thinking") {
      energy = 0.15 + 0.1 * Math.abs(Math.sin(t * 2));
    } else {
      energy = 0.05 + 0.03 * Math.abs(Math.sin(t)); // respiração idle
    }
    const min = Math.min(w, h);
    const base = amplitudeToVisual(bytes.length ? bytes : new Uint8Array(bins));
    const radius = (state === "idle" ? 0.32 : base.radius) * min * 0.5 * (0.9 + energy);
    const cx = w / 2, cy = h / 2;

    const grad = ctx.createRadialGradient(cx, cy, radius * 0.2, cx, cy, radius);
    grad.addColorStop(0, COLORS.spring);
    grad.addColorStop(0.6, COLORS.jade);
    grad.addColorStop(1, COLORS.emerald);
    ctx.globalAlpha = 0.9;
    ctx.shadowBlur = 8 + 40 * energy;
    ctx.shadowColor = COLORS.jade;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.fillStyle = grad;
    ctx.fill();

    // anel giratório no estado "thinking"
    if (state === "thinking") {
      ctx.globalAlpha = 0.7;
      ctx.strokeStyle = COLORS.spring;
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.arc(cx, cy, radius * 1.25, t, t + Math.PI);
      ctx.stroke();
    }
    ctx.shadowBlur = 0;
    ctx.globalAlpha = 1;
    requestAnimationFrame(draw);
  }
  requestAnimationFrame(draw);

  return {
    setState(name) { state = name; },
    connectMic(stream) {
      ensureAudio();
      if (micSource) micSource.disconnect();
      micSource = audioCtx.createMediaStreamSource(stream);
      micSource.connect(analyser); // não conecta ao destino (evita microfonia)
    },
    connectAudio(audioEl) {
      ensureAudio();
      if (!mediaSource) mediaSource = audioCtx.createMediaElementSource(audioEl);
      mediaSource.connect(analyser);
      mediaSource.connect(audioCtx.destination);
    },
    onWakeword(fn) { wakewordCb = fn; }, // gancho para o #3 (não usado no #1)
  };
}
```

- [ ] **Step 2: Verificação de sintaxe**

Run: `node --check interfaces/frontend/orb.js`
Expected: sem saída.

- [ ] **Step 3: Commit**

```bash
git add interfaces/frontend/orb.js
git commit -m "feat(frontend): orb Canvas reativo à amplitude, 4 estados + gancho wake-word"
```

---

## Task 7: Chat de texto (`chat.js`)

**Files:**
- Create: `interfaces/frontend/chat.js`

**Interfaces:**
- Consumes: `api.sendMessage`, `api.ttsUrl` (Task 5); `modelBadge` (Task 4); store (Task 4); orb (Task 6); `#messages`, `#composer`, `#composer-input`, `#send-btn`.
- Produces:
  - `createChat({ store, orb, audioEl }) -> { send(text), addBubble(role, text, model?), clear() }`
  - `send` respeita e alterna o `busy` do store; toca TTS da resposta se `!muted`.

- [ ] **Step 1: Implementar `chat.js`**

```javascript
import { sendMessage, ttsUrl } from "./api.js";
import { modelBadge } from "./lib/format.js";

export function createChat({ store, orb, audioEl }) {
  const list = document.getElementById("messages");

  function addBubble(role, text, model) {
    const div = document.createElement("div");
    div.className = `bubble ${role}`;
    div.textContent = text;
    list.appendChild(div);
    if (role === "jade" && modelBadge(model)) {
      const b = document.createElement("div");
      b.className = "badge";
      b.textContent = modelBadge(model);
      list.appendChild(b);
    }
    list.scrollTop = list.scrollHeight;
    return div;
  }

  async function speak(text) {
    if (store.get().muted) return;
    try {
      const url = await ttsUrl(text);
      audioEl.src = url;
      orb.connectAudio(audioEl);
      orb.setState("speaking");
      audioEl.onended = () => orb.setState("idle");
      await audioEl.play();
    } catch {
      orb.setState("idle"); // falha de TTS não trava a UI
    }
  }

  async function send(text) {
    if (!text || store.get().busy) return;
    addBubble("user", text);
    store.set({ busy: true });
    orb.setState("thinking");
    try {
      const { reply, model } = await sendMessage(text);
      addBubble("jade", reply, model);
      store.set({ busy: false });
      await speak(reply);
    } catch (e) {
      addBubble("error", "Jade indisponível no momento.");
      store.set({ busy: false });
      orb.setState("idle");
    }
  }

  return { send, addBubble, clear: () => { list.innerHTML = ""; } };
}
```

- [ ] **Step 2: Verificação de sintaxe**

Run: `node --check interfaces/frontend/chat.js`
Expected: sem saída.

- [ ] **Step 3: Commit**

```bash
git add interfaces/frontend/chat.js
git commit -m "feat(frontend): chat de texto com badge do modelo, trava busy e TTS"
```

---

## Task 8: Lista de conversas (`threads.js`)

**Files:**
- Create: `interfaces/frontend/threads.js`

**Interfaces:**
- Consumes: `api.listConversations`, `api.getConversation` (Task 5); chat (Task 7); `#threads-list`.
- Produces:
  - `createThreads({ chat }) -> { refresh(), openThread(id) }`
  - `openThread` renderiza os turnos em **leitura** (limpa e re-pinta os balões).

- [ ] **Step 1: Implementar `threads.js`**

```javascript
import { listConversations, getConversation } from "./api.js";

export function createThreads({ chat }) {
  const ul = document.getElementById("threads-list");

  async function refresh() {
    ul.innerHTML = "";
    let convs = [];
    try {
      convs = await listConversations();
    } catch {
      return;
    }
    for (const c of convs) {
      const li = document.createElement("li");
      li.textContent = c.title || c.id;
      li.title = c.date || "";
      li.dataset.id = c.id;
      li.addEventListener("click", () => openThread(c.id, li));
      ul.appendChild(li);
    }
  }

  async function openThread(id, li) {
    for (const el of ul.children) el.classList.toggle("active", el === li);
    let data;
    try {
      data = await getConversation(id);
    } catch {
      return;
    }
    chat.clear();
    for (const t of data.turns) {
      chat.addBubble("user", t.user);
      chat.addBubble("jade", t.jade);
    }
  }

  return { refresh, openThread };
}
```

- [ ] **Step 2: Verificação de sintaxe**

Run: `node --check interfaces/frontend/threads.js`
Expected: sem saída.

- [ ] **Step 3: Commit**

```bash
git add interfaces/frontend/threads.js
git commit -m "feat(frontend): lista de conversas com abertura em leitura"
```

---

## Task 9: Voz push-to-talk (`voice.js`)

**Files:**
- Create: `interfaces/frontend/voice.js`

**Interfaces:**
- Consumes: `api.voiceChat` (Task 5); chat (Task 7); store (Task 4); orb (Task 6); `#mic-btn`, `audioEl`.
- Produces:
  - `createVoice({ store, orb, chat, audioEl }) -> { bind() }`
  - `bind()` liga o push-to-talk ao `#mic-btn` (mousedown/up + touch) e o atalho **espaço** (segurar). Bloqueia quando `busy`.

- [ ] **Step 1: Implementar `voice.js`**

```javascript
import { voiceChat } from "./api.js";

export function createVoice({ store, orb, chat, audioEl }) {
  const btn = document.getElementById("mic-btn");
  let recorder = null;
  let chunks = [];
  let stream = null;
  let recording = false;

  async function start() {
    if (recording || store.get().busy) return;
    recording = true;
    btn.classList.add("recording");
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    orb.connectMic(stream);
    orb.setState("listening");
    chunks = [];
    recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (e) => chunks.push(e.data);
    recorder.start();
  }

  async function stop() {
    if (!recording) return;
    recording = false;
    btn.classList.remove("recording");
    await new Promise((resolve) => {
      recorder.onstop = resolve;
      recorder.stop();
    });
    for (const track of stream.getTracks()) track.stop();
    const blob = new Blob(chunks, { type: "audio/webm" });
    store.set({ busy: true });
    orb.setState("thinking");
    try {
      const { transcription, reply, audio_url } = await voiceChat(blob);
      chat.addBubble("user", transcription);
      chat.addBubble("jade", reply);
      store.set({ busy: false });
      if (!store.get().muted && audio_url) {
        audioEl.src = audio_url;
        orb.connectAudio(audioEl);
        orb.setState("speaking");
        audioEl.onended = () => orb.setState("idle");
        await audioEl.play();
      } else {
        orb.setState("idle");
      }
    } catch {
      chat.addBubble("error", "Não consegui te ouvir agora.");
      store.set({ busy: false });
      orb.setState("idle");
    }
  }

  function bind() {
    btn.addEventListener("mousedown", start);
    btn.addEventListener("mouseup", stop);
    btn.addEventListener("mouseleave", () => recording && stop());
    btn.addEventListener("touchstart", (e) => { e.preventDefault(); start(); });
    btn.addEventListener("touchend", (e) => { e.preventDefault(); stop(); });
    // Atalho: segurar espaço (fora do campo de texto).
    window.addEventListener("keydown", (e) => {
      if (e.code === "Space" && e.target.tagName !== "INPUT" && !recording) {
        e.preventDefault();
        start();
      }
    });
    window.addEventListener("keyup", (e) => {
      if (e.code === "Space" && recording) stop();
    });
  }

  return { bind };
}
```

- [ ] **Step 2: Verificação de sintaxe**

Run: `node --check interfaces/frontend/voice.js`
Expected: sem saída.

- [ ] **Step 3: Commit**

```bash
git add interfaces/frontend/voice.js
git commit -m "feat(frontend): voz push-to-talk (mic → /voice/chat) com trava e orb"
```

---

## Task 10: Bootstrap + integração da trava (`app.js`) + smoke manual

**Files:**
- Create: `interfaces/frontend/app.js`

**Interfaces:**
- Consumes: todos os módulos anteriores; `#composer`, `#composer-input`, `#send-btn`, `#mic-btn`, `#mute-btn`, `#new-chat`, `#orb-status`, `#orb-canvas`.
- Produces: a aplicação montada (nenhum export).

- [ ] **Step 1: Implementar `app.js`**

```javascript
import { createStore } from "./lib/state.js";
import { createOrb } from "./orb.js";
import { createChat } from "./chat.js";
import { createThreads } from "./threads.js";
import { createVoice } from "./voice.js";
import { reset } from "./api.js";

const store = createStore();
const audioEl = new Audio();
const orb = createOrb(document.getElementById("orb-canvas"));
const chat = createChat({ store, orb, audioEl });
const threads = createThreads({ chat });
const voice = createVoice({ store, orb, chat, audioEl });

const input = document.getElementById("composer-input");
const sendBtn = document.getElementById("send-btn");
const micBtn = document.getElementById("mic-btn");
const muteBtn = document.getElementById("mute-btn");
const status = document.getElementById("orb-status");

const STATUS = { idle: "ociosa", listening: "ouvindo…", thinking: "pensando…", speaking: "falando…" };
const _setState = orb.setState;
orb.setState = (name) => { status.textContent = STATUS[name] || name; _setState(name); };

// Trava de entrada: quando busy, desabilita composer e mic.
store.subscribe((st) => {
  input.disabled = st.busy;
  sendBtn.disabled = st.busy;
  micBtn.disabled = st.busy;
  input.placeholder = st.busy ? "Jade está pensando…" : "Fale com a Jade…";
});

document.getElementById("composer").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value.trim();
  input.value = "";
  chat.send(text);
});

document.getElementById("new-chat").addEventListener("click", async () => {
  await reset();
  chat.clear();
  for (const el of document.getElementById("threads-list").children) el.classList.remove("active");
});

muteBtn.addEventListener("click", () => {
  const muted = !store.get().muted;
  store.set({ muted });
  muteBtn.textContent = muted ? "🔇" : "🔊";
  muteBtn.setAttribute("aria-pressed", String(muted));
});

voice.bind();
threads.refresh();
orb.setState("idle");
```

- [ ] **Step 2: Verificação de sintaxe**

Run: `node --check interfaces/frontend/app.js`
Expected: sem saída.

- [ ] **Step 3: Smoke manual (com Ollama rodando)**

```bash
python main.py
```
Abrir `http://127.0.0.1:8000/` e verificar:
1. Layout de 3 zonas com o orb "respirando" (idle).
2. Enviar texto → balão do usuário, orb "pensando", resposta com badge, orb "falando" + áudio; enquanto pensa, o campo fica desabilitado ("Jade está pensando…").
3. Segurar 🎤 (ou espaço) → orb "ouvindo" reage ao mic; soltar → transcrição + resposta.
4. Botão de mudo silencia o TTS.
5. Lista à esquerda mostra conversas; clicar abre em leitura; "+ Novo" limpa.

- [ ] **Step 4: Rodar toda a bateria automatizada**

Run: `python -m pytest -q && node --test interfaces/frontend/__tests__/ && ruff check . && ruff format --check .`
Expected: tudo verde.

- [ ] **Step 5: Commit**

```bash
git add interfaces/frontend/app.js
git commit -m "feat(frontend): bootstrap, trava de entrada e rótulo de estado do orb"
```

---

## Self-Review

**1. Spec coverage:**
- Layout 3 zonas → Task 3. ✓
- Texto + voz push-to-talk → Tasks 7, 9. ✓
- TTS automático + mudo → Task 7 (`speak`), Task 10 (botão mudo). ✓
- Orb Canvas 4 estados + amplitude real + gancho #3 → Tasks 4, 6. ✓
- Trava um-turno-por-vez (libera na resposta, `speaking` não trava) → Tasks 7, 9, 10. ✓
- Lista/abrir conversas em leitura → Tasks 1, 2, 8. ✓
- Endpoints só-leitura + anti path-traversal → Task 2. ✓
- Same-origin/sem build → Tasks 2, 3 (mount, ES modules). ✓
- Paleta verde → Tasks 3, 6. ✓

**2. Placeholder scan:** nenhum "TBD/TODO/etc." — todos os steps têm código real.

**3. Type consistency:** `createStore`, `amplitudeToVisual`, `modelBadge`, `createOrb`/`setState`/`connectMic`/`connectAudio`, `createChat`/`send`/`addBubble`/`clear`, `createThreads`/`refresh`/`openThread`, `createVoice`/`bind` — usados de forma consistente entre as tasks. Endpoints (`/conversations`, `/conversations/{id}`) coerentes entre Task 2 e Task 5/8.
