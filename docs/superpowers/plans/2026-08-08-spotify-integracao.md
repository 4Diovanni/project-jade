# Spotify — Link de Conta, Cache Local e Tocar/Pesquisar — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar à Jade acesso à biblioteca musical do usuário no Spotify — login OAuth, cache local (SQLite) de faixas para tocar por nome sem round-trip de rede, busca explícita na Web API, reprodução via Spotify Connect, e uma aba própria no frontend para navegar a biblioteca.

**Architecture:** Camada `core/spotify_db.py` (SQLite puro, sem rede) por baixo de `core/spotify.py` (OAuth + Web API via `spotipy` + sync em thread de background, no mesmo padrão de `ChatSession._ensure_synced`). `tools/spotify_tool.py` expõe os três comandos determinísticos (`toca` / `pesquisa ... no spotify` / `sincroniza`) seguindo o contrato `JadeTool` já usado por `tools/system_tool.py`. `interfaces/api.py` ganha as rotas HTTP (login/callback/status/library/sync) e um hook de startup que dispara o sync em background. `interfaces/frontend/` ganha uma aba "Spotify" que troca a view inteira do "Chat".

**Tech Stack:** Python 3.11+ · FastAPI · `spotipy` (OAuth Authorization Code + Web API) · SQLite (`sqlite3` da stdlib) · pytest (Python) · `node --test` (frontend, sem build).

## Global Constraints

- **Spec-fonte:** `docs/superpowers/specs/2026-08-08-spotify-design.md` — toda tarefa abaixo implementa uma seção dela; não inventar comportamento fora do que está lá.
- **Config sempre via `core.config.settings`** — nunca `os.getenv` espalhado (regra do `CLAUDE.md`).
- **Segredos só no `.env`** (gitignorado). `database/spotify_token.json` (token OAuth) também nunca vai pro git.
- **Sem dependência nova além de `spotipy`** — já reservada e comentada em `requirements.txt` ("Fase 3+/4: Mãos"). Nenhum pacote de frontend/build novo (o projeto já roda `node --test` sem npm/bundler).
- **Tipos do `_parse`** (`tools/spotify_tool.py`): `tuple[str | None, str | None]`, com o primeiro elemento em `{"play", "search", "sync", None}` — mesma convenção de `tools/system_tool.py::_parse`.
- **Nenhum teste bate na API real do Spotify nem exige credenciais.** `spotipy.Spotify`/`SpotifyOAuth` são sempre mockados nos testes automatizados (Python) — mesma postura do `python main.py bench` (Ollama) ficar fora do CI. A validação com a conta real do usuário (login, sync, tocar, pesquisar) é manual, registrada no PR.
- **Colisão de rota com `tools/system_tool.py`:** `SpotifyTool` precisa ser registrada **antes** de `SystemControlTool` em `tools/registry.py::_TOOLS`, e `SpotifyTool.accepts()` só aceita busca/sync se a mensagem citar explicitamente "spotify" ou "música(s)" — sem isso, "pesquisa gatos no google" pararia de funcionar.
- **Antes de cada commit:** `ruff check . && ruff format .`, `pytest`, e — nas tasks que tocam `interfaces/frontend/` (Task 6) — também `node --test interfaces/frontend/__tests__/`.
- **Pré-requisito de infraestrutura, verificado ANTES da Task 1:** confirmar que a versão instalada de `spotipy` (`pip install spotipy>=2.24` num venv de teste) expõe `spotipy.oauth2.SpotifyOAuth`, `spotipy.oauth2.CacheFileHandler`, e os métodos `Spotify.current_user_saved_tracks`, `current_user_playlists`, `playlist_items`, `next`, `search`, `devices`, `start_playback` com as assinaturas assumidas neste plano (checar `spotipy.readthedocs.io` ou `python -c "import spotipy, inspect; print(inspect.signature(spotipy.Spotify.start_playback))"`). Se a API pública divergir, ajustar as chamadas da Task 3 antes de prosseguir — não travar a Task 1 nisso, mas não pular a checagem.

---

## File Structure

- **`core/config.py`** (modificado) — novo bloco de settings `SPOTIFY_*`.
- **`requirements.txt`** (modificado) — descomenta `spotipy`.
- **`.env.example`** (modificado) — entradas comentadas das novas variáveis.
- **`.gitignore`** (modificado) — ignora `database/spotify_token.json`.
- **`core/spotify_db.py`** (novo) — camada SQLite pura: schema, upsert, busca por nome, metadados de sync. Sem rede, sem `spotipy`.
- **`core/spotify.py`** (novo) — OAuth (`spotipy`), sync da biblioteca em thread de background, `find_track`/`search_track`/`play`. Único módulo que importa `spotipy`.
- **`tools/spotify_tool.py`** (novo) — `_parse()` puro + `SpotifyTool(JadeTool)`, delega pra `core.spotify`.
- **`tools/registry.py`** (modificado) — registra `SpotifyTool()` antes de `SystemControlTool()`.
- **`interfaces/api.py`** (modificado) — rotas `/spotify/login`, `/spotify/callback`, `/spotify/status`, `/spotify/library`, `/spotify/sync` + hook de startup.
- **`interfaces/frontend/lib/spotify-filter.js`** (novo) — filtro puro de faixas por nome/artista (testável em Node, sem DOM).
- **`interfaces/frontend/spotify.js`** (novo) — `createSpotify({ store })`: busca status/library, renderiza lista + card de embed, faz polling de `/spotify/status` até a 1ª sync terminar após o OAuth, trata o retorno do callback (`?spotify=conectado`/`?spotify=erro`), wiring de DOM (não testado por unidade — mesmo padrão de `chat.js`/`threads.js`; verificado manualmente no browser); exporta a função pura `spotifyCallbackParam(search)`, essa sim testada.
- **`interfaces/frontend/api.js`** (modificado) — 3 wrappers de fetch novos (`getSpotifyStatus`, `getSpotifyLibrary`, `syncSpotifyNow`).
- **`interfaces/frontend/app.js`** (modificado) — alternância de aba Chat/Spotify.
- **`interfaces/frontend/index.html`** (modificado) — tablist + `<section>` da view Spotify.
- **`interfaces/frontend/styles.css`** (modificado) — classes da tablist e da view Spotify.
- **`tests/test_config.py`** (novo) — sanidade das settings de Spotify.
- **`tests/test_spotify_db.py`** (novo) — testes de `core/spotify_db.py`.
- **`tests/test_spotify.py`** (novo) — testes de `core/spotify.py` (`spotipy` mockado).
- **`tests/test_spotify_tool.py`** (novo) — testes de `tools/spotify_tool.py` + roteamento.
- **`tests/test_spotify_api.py`** (novo) — testes das rotas `/spotify/*`.
- **`interfaces/frontend/__tests__/spotify-filter.test.js`** (novo) — testes do filtro puro.
- **`interfaces/frontend/__tests__/spotify.test.js`** (novo) — testes de `spotifyCallbackParam()`.

---

## Task 1: Config, dependência e arquivos de ambiente

**Files:**
- Modify: `core/config.py:132-135` (bloco `── API ──`)
- Modify: `requirements.txt:24-26` (bloco "Fase 3+/4: Mãos")
- Modify: `.env.example` (fim do arquivo, após `── API (FastAPI) ──`)
- Modify: `.gitignore` (bloco "Bancos de dados locais")
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `settings.SPOTIFY_CLIENT_ID: str`, `settings.SPOTIFY_CLIENT_SECRET: str`, `settings.SPOTIFY_REDIRECT_URI: str`, `settings.SPOTIFY_TOKEN_CACHE_PATH: str`, `settings.SPOTIFY_LIBRARY_STALE_HOURS: int`, `settings.SPOTIFY_TOOL_ENABLED: bool`; pacote `spotipy` instalável via `requirements.txt`.

- [ ] **Step 1: Escrever o teste (falhando) de sanidade das settings**

```python
# tests/test_config.py
"""Sanidade das settings de Spotify (Fase 4) — defaults quando o .env não
define nada, e formato dos valores derivados (redirect URI, caminho do
cache de token)."""

from core.config import settings


def test_spotify_settings_existem_com_defaults():
    assert hasattr(settings, "SPOTIFY_CLIENT_ID")
    assert hasattr(settings, "SPOTIFY_CLIENT_SECRET")
    assert settings.SPOTIFY_REDIRECT_URI.endswith("/spotify/callback")
    assert settings.SPOTIFY_TOKEN_CACHE_PATH.endswith("spotify_token.json")
    assert settings.SPOTIFY_LIBRARY_STALE_HOURS == 24
    assert settings.SPOTIFY_TOOL_ENABLED is True
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `AttributeError`/`AssertionError` (`settings` ainda não tem os atributos `SPOTIFY_*`).

- [ ] **Step 3: Adicionar o bloco de settings em `core/config.py`**

De:
```python
    # ── API ──
    API_HOST: str = os.getenv("JADE_API_HOST", "127.0.0.1")
    API_PORT: int = int(os.getenv("JADE_API_PORT", "8000"))

    # Pastas/arquivos do vault que NUNCA devem ser indexados no RAG.
```

Por:
```python
    # ── API ──
    API_HOST: str = os.getenv("JADE_API_HOST", "127.0.0.1")
    API_PORT: int = int(os.getenv("JADE_API_PORT", "8000"))

    # ── Spotify (Fase 4) ──
    # Credenciais do app registrado no Spotify Developer Dashboard.
    SPOTIFY_CLIENT_ID: str = os.getenv("SPOTIFY_CLIENT_ID", "")
    SPOTIFY_CLIENT_SECRET: str = os.getenv("SPOTIFY_CLIENT_SECRET", "")
    # Precisa bater EXATAMENTE com o Redirect URI cadastrado no Dashboard.
    SPOTIFY_REDIRECT_URI: str = os.getenv(
        "SPOTIFY_REDIRECT_URI", f"http://{API_HOST}:{API_PORT}/spotify/callback"
    )
    # Token OAuth persistido localmente — nunca vai pro git (ver .gitignore).
    SPOTIFY_TOKEN_CACHE_PATH: str = os.getenv(
        "SPOTIFY_TOKEN_CACHE_PATH", str(BASE_DIR / "database" / "spotify_token.json")
    )
    # Acima disso (em horas), o cache local de faixas é considerado velho e
    # sync_library() refaz a busca completa na próxima chamada.
    SPOTIFY_LIBRARY_STALE_HOURS: int = int(os.getenv("SPOTIFY_LIBRARY_STALE_HOURS", "24"))
    SPOTIFY_TOOL_ENABLED: bool = (
        os.getenv("JADE_SPOTIFY_TOOL_ENABLED", "true").strip().lower() != "false"
    )

    # Pastas/arquivos do vault que NUNCA devem ser indexados no RAG.
```

- [ ] **Step 4: Descomentar `spotipy` em `requirements.txt`**

De:
```
# ── Fase 3+/4: Mãos (descomente ao chegar na fase) ───────────
# spotipy                       # módulo Spotify
# pyautogui                     # controle do SO
# google-api-python-client      # Gmail / Calendar
```

Por:
```
# ── Fase 3+/4: Mãos (descomente ao chegar na fase) ───────────
spotipy>=2.24                   # módulo Spotify (OAuth + Web API)
# pyautogui                     # controle do SO
# google-api-python-client      # Gmail / Calendar
```

- [ ] **Step 5: Instalar a dependência no venv de desenvolvimento**

Run: `pip install -r requirements.txt`
Expected: `spotipy` (e suas dependências transitivas, `redis`/`urllib3`/etc.) instalados sem erro.

- [ ] **Step 6: Adicionar as variáveis em `.env.example`**

De (fim do arquivo):
```
# ── API (FastAPI) ────────────────────────────────────────────
JADE_API_HOST=127.0.0.1
JADE_API_PORT=8000
```

Por:
```
# ── API (FastAPI) ────────────────────────────────────────────
JADE_API_HOST=127.0.0.1
JADE_API_PORT=8000

# ── Spotify (Fase 4) ─────────────────────────────────────────
# Client ID/Secret do app registrado em developer.spotify.com/dashboard.
# Sem isso, a integração fica desligada (a tool avisa e não tenta rede).
# SPOTIFY_CLIENT_ID=
# SPOTIFY_CLIENT_SECRET=
# Precisa bater EXATAMENTE com o Redirect URI cadastrado no Dashboard.
# SPOTIFY_REDIRECT_URI=http://127.0.0.1:8000/spotify/callback
# SPOTIFY_TOKEN_CACHE_PATH=./database/spotify_token.json
# SPOTIFY_LIBRARY_STALE_HOURS=24
# JADE_SPOTIFY_TOOL_ENABLED=true
```

- [ ] **Step 7: Ignorar o token do Spotify no `.gitignore`**

De:
```
# Bancos de dados locais (gerados em runtime)
database/chroma_db/
database/*.db
database/*.sqlite3
database/index_state.json
```

Por:
```
# Bancos de dados locais (gerados em runtime)
database/chroma_db/
database/*.db
database/*.sqlite3
database/index_state.json
database/spotify_token.json
```

- [ ] **Step 8: Rodar o teste e confirmar que passa**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 9: Lint + commit**

Run: `ruff check . && ruff format .`

```bash
git add core/config.py requirements.txt .env.example .gitignore tests/test_config.py
git commit -m "feat(spotify): settings, dependência e variáveis de ambiente"
```

---

## Task 2: `core/spotify_db.py` — cache SQLite de faixas

**Files:**
- Create: `core/spotify_db.py`
- Test: `tests/test_spotify_db.py`

**Interfaces:**
- Consumes: `settings.SQLITE_PATH` (já existe desde a Fase 1, ativado pela primeira vez aqui).
- Produces: `upsert_tracks(tracks: list[dict]) -> int`, `search_by_name(name: str) -> dict | None`, `list_tracks() -> list[dict]`, `last_synced_at() -> str | None`, `set_last_synced_at(ts: str) -> None`, `track_count() -> int`. Cada `track` é um dict com chaves `id`, `name`, `artists`, `url`, `playlist_id`, `playlist_name`.

- [ ] **Step 1: Escrever os testes (falhando)**

```python
# tests/test_spotify_db.py
"""Testes de core/spotify_db.py — SQLite puro, banco temporário, sem rede."""

import pytest

import core.spotify_db as db


@pytest.fixture(autouse=True)
def _banco_temporario(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "SQLITE_PATH", str(tmp_path / "spotify_test.db"))
    yield


def test_upsert_tracks_e_idempotente():
    tracks = [
        {
            "id": "1",
            "name": "Bohemian Rhapsody",
            "artists": "Queen",
            "url": "https://open.spotify.com/track/1",
            "playlist_id": None,
            "playlist_name": "Curtidas",
        }
    ]
    assert db.upsert_tracks(tracks) == 1
    assert db.upsert_tracks(tracks) == 1  # resync não duplica
    assert db.track_count() == 1


def test_search_by_name_ignora_caixa_e_acento():
    db.upsert_tracks(
        [
            {
                "id": "2",
                "name": "Águas de Março",
                "artists": "Elis Regina",
                "url": "https://open.spotify.com/track/2",
                "playlist_id": None,
                "playlist_name": None,
            }
        ]
    )
    encontrada = db.search_by_name("aguas de marco")
    assert encontrada is not None
    assert encontrada["id"] == "2"


def test_search_by_name_por_artista():
    db.upsert_tracks(
        [
            {
                "id": "3",
                "name": "Imagine",
                "artists": "John Lennon",
                "url": "https://open.spotify.com/track/3",
                "playlist_id": None,
                "playlist_name": None,
            }
        ]
    )
    encontrada = db.search_by_name("lennon")
    assert encontrada is not None
    assert encontrada["id"] == "3"


def test_search_by_name_nao_encontrado():
    assert db.search_by_name("musica que nao existe em lugar nenhum") is None


def test_last_synced_at_antes_e_depois_do_set():
    assert db.last_synced_at() is None
    db.set_last_synced_at("2026-08-08T12:00:00")
    assert db.last_synced_at() == "2026-08-08T12:00:00"


def test_list_tracks_devolve_playlist_de_origem():
    db.upsert_tracks(
        [
            {
                "id": "4",
                "name": "A",
                "artists": "X",
                "url": "u1",
                "playlist_id": "p1",
                "playlist_name": "Rock",
            },
            {
                "id": "5",
                "name": "B",
                "artists": "Y",
                "url": "u2",
                "playlist_id": None,
                "playlist_name": "Curtidas",
            },
        ]
    )
    nomes_playlist = {t["playlist_name"] for t in db.list_tracks()}
    assert nomes_playlist == {"Rock", "Curtidas"}
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `pytest tests/test_spotify_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.spotify_db'`

- [ ] **Step 3: Implementar `core/spotify_db.py`**

```python
# core/spotify_db.py
"""Cache local (SQLite) das faixas do Spotify do usuário — Curtidas +
playlists salvas. Módulo síncrono, sem rede e sem `spotipy`: só sabe ler e
escrever no banco em `settings.SQLITE_PATH` (ativado pela primeira vez por
este subprojeto, Fase 4 — ver core/config.py)."""

from __future__ import annotations

import sqlite3
import unicodedata
from pathlib import Path

from core.config import settings


def _normalize(text: str) -> str:
    """lower + remove acentos simples, para busca tolerante a maiúsculas e
    diacríticos ('Águas' == 'aguas')."""
    decomposed = unicodedata.normalize("NFKD", text)
    sem_acento = "".join(c for c in decomposed if not unicodedata.combining(c))
    return sem_acento.lower().strip()


def _connect() -> sqlite3.Connection:
    path = Path(settings.SQLITE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS spotify_tracks ("
        "id TEXT PRIMARY KEY, name TEXT NOT NULL, artists TEXT NOT NULL, "
        "url TEXT NOT NULL, playlist_id TEXT, playlist_name TEXT)"
    )
    conn.execute("CREATE TABLE IF NOT EXISTS spotify_meta (key TEXT PRIMARY KEY, value TEXT)")
    return conn


def upsert_tracks(tracks: list[dict]) -> int:
    """INSERT OR REPLACE de cada faixa — um resync inteiro não duplica linha."""
    conn = _connect()
    try:
        conn.executemany(
            "INSERT OR REPLACE INTO spotify_tracks "
            "(id, name, artists, url, playlist_id, playlist_name) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    t["id"],
                    t["name"],
                    t["artists"],
                    t["url"],
                    t.get("playlist_id"),
                    t.get("playlist_name"),
                )
                for t in tracks
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return len(tracks)


def search_by_name(name: str) -> dict | None:
    """Primeiro resultado (nome ou artista) contendo `name`, normalizado.
    LIKE simples, não fuzzy matching — ver "Riscos" no spec."""
    alvo = _normalize(name)
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, name, artists, url, playlist_id, playlist_name FROM spotify_tracks"
        ).fetchall()
    finally:
        conn.close()
    for row in rows:
        if alvo in _normalize(row["name"]) or alvo in _normalize(row["artists"]):
            return dict(row)
    return None


def list_tracks() -> list[dict]:
    """Todas as faixas do cache, ordenadas por playlist e nome."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, name, artists, url, playlist_id, playlist_name "
            "FROM spotify_tracks ORDER BY playlist_name, name"
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def track_count() -> int:
    conn = _connect()
    try:
        row = conn.execute("SELECT COUNT(*) AS n FROM spotify_tracks").fetchone()
    finally:
        conn.close()
    return row["n"]


def last_synced_at() -> str | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT value FROM spotify_meta WHERE key = 'last_synced_at'"
        ).fetchone()
    finally:
        conn.close()
    return row["value"] if row else None


def set_last_synced_at(ts: str) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO spotify_meta (key, value) VALUES ('last_synced_at', ?)",
            (ts,),
        )
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `pytest tests/test_spotify_db.py -v`
Expected: PASS (6 testes)

- [ ] **Step 5: Lint + commit**

Run: `ruff check . && ruff format .`

```bash
git add core/spotify_db.py tests/test_spotify_db.py
git commit -m "feat(spotify): cache SQLite local de faixas (core/spotify_db.py)"
```

---

## Task 3: `core/spotify.py` — OAuth, sync em background, tocar/pesquisar

**Files:**
- Create: `core/spotify.py`
- Test: `tests/test_spotify.py`

**Interfaces:**
- Consumes: `settings.SPOTIFY_*` (Task 1); `core.spotify_db.upsert_tracks/search_by_name/list_tracks/last_synced_at/set_last_synced_at/track_count` (Task 2).
- Produces: `is_linked() -> bool`, `authorize_url() -> str`, `handle_callback(code: str) -> None`, `sync_library(force: bool = False) -> int`, `find_track(name: str) -> dict | None`, `search_track(query: str) -> list[dict]`, `play(track_id: str) -> str`, `start_background_sync_if_stale() -> None`, `NoActiveDeviceError` (exceção), `get_auth_manager()`, `get_client()` (pontos de mock nos testes).

- [ ] **Step 1: Escrever os testes (falhando)**

```python
# tests/test_spotify.py
"""Testes de core/spotify.py — spotipy mockado via monkeypatch em
get_auth_manager()/get_client(). Nenhum teste bate na API real nem usa
credenciais de verdade."""

from __future__ import annotations

import threading

import pytest

import core.spotify as spotify_mod


class FakeCacheHandler:
    def __init__(self, token=None):
        self._token = token

    def get_cached_token(self):
        return self._token


class FakeAuthManager:
    def __init__(self, *, token=None, valid=True, url="https://accounts.spotify.com/authorize?x"):
        self.cache_handler = FakeCacheHandler(token)
        self._valid = valid
        self._url = url
        self.exchanged_code = None

    def validate_token(self, token):
        if not self._valid:
            raise RuntimeError("refresh falhou")
        return token

    def get_authorize_url(self):
        return self._url

    def get_access_token(self, code, as_dict=False):
        self.exchanged_code = code
        self.cache_handler._token = {"access_token": "fake"}


class FakeSpotifyClient:
    def __init__(self, *, saved_tracks=None, playlists=None, devices=None, search_result=None):
        self._saved_tracks = saved_tracks or {"items": [], "next": None}
        self._playlists = playlists or {"items": [], "next": None}
        self._devices = devices if devices is not None else []
        self._search_result = search_result or {"tracks": {"items": []}}
        self.started_playback = None

    def current_user_saved_tracks(self, limit=50):
        return self._saved_tracks

    def current_user_playlists(self, limit=50):
        return self._playlists

    def playlist_items(self, playlist_id, limit=100):
        return {"items": [], "next": None}

    def next(self, page):
        return None

    def search(self, q, type, limit):
        return self._search_result

    def devices(self):
        return {"devices": self._devices}

    def start_playback(self, device_id, uris):
        self.started_playback = (device_id, uris)


@pytest.fixture(autouse=True)
def _isola_spotify(monkeypatch, tmp_path):
    monkeypatch.setattr(spotify_mod.settings, "SQLITE_PATH", str(tmp_path / "t.db"))
    spotify_mod._sync_thread = None
    yield
    spotify_mod._sync_thread = None


def test_is_linked_false_sem_credenciais(monkeypatch):
    monkeypatch.setattr(spotify_mod.settings, "SPOTIFY_CLIENT_ID", "")
    monkeypatch.setattr(spotify_mod.settings, "SPOTIFY_CLIENT_SECRET", "")
    assert spotify_mod.is_linked() is False


def test_is_linked_false_sem_token(monkeypatch):
    monkeypatch.setattr(spotify_mod.settings, "SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setattr(spotify_mod.settings, "SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.setattr(spotify_mod, "get_auth_manager", lambda: FakeAuthManager(token=None))
    assert spotify_mod.is_linked() is False


def test_is_linked_false_quando_refresh_falha(monkeypatch):
    monkeypatch.setattr(spotify_mod.settings, "SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setattr(spotify_mod.settings, "SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.setattr(
        spotify_mod,
        "get_auth_manager",
        lambda: FakeAuthManager(token={"access_token": "x"}, valid=False),
    )
    assert spotify_mod.is_linked() is False


def test_is_linked_true_com_token_valido(monkeypatch):
    monkeypatch.setattr(spotify_mod.settings, "SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setattr(spotify_mod.settings, "SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.setattr(
        spotify_mod,
        "get_auth_manager",
        lambda: FakeAuthManager(token={"access_token": "x"}, valid=True),
    )
    assert spotify_mod.is_linked() is True


def test_authorize_url_delega_pro_auth_manager(monkeypatch):
    monkeypatch.setattr(
        spotify_mod, "get_auth_manager", lambda: FakeAuthManager(url="https://x/authorize")
    )
    assert spotify_mod.authorize_url() == "https://x/authorize"


def test_handle_callback_troca_code_por_token(monkeypatch):
    fake = FakeAuthManager()
    monkeypatch.setattr(spotify_mod, "get_auth_manager", lambda: fake)
    spotify_mod.handle_callback("code123")
    assert fake.exchanged_code == "code123"


def test_sync_library_popula_o_cache(monkeypatch):
    monkeypatch.setattr(spotify_mod.settings, "SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setattr(spotify_mod.settings, "SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.setattr(
        spotify_mod,
        "get_auth_manager",
        lambda: FakeAuthManager(token={"access_token": "x"}, valid=True),
    )
    fake_client = FakeSpotifyClient(
        saved_tracks={
            "items": [
                {
                    "track": {
                        "id": "1",
                        "name": "Bohemian Rhapsody",
                        "artists": [{"name": "Queen"}],
                        "external_urls": {"spotify": "https://open.spotify.com/track/1"},
                    }
                }
            ],
            "next": None,
        }
    )
    monkeypatch.setattr(spotify_mod, "get_client", lambda: fake_client)

    n = spotify_mod.sync_library(force=True)

    assert n == 1
    from core.spotify_db import search_by_name

    encontrada = search_by_name("bohemian rhapsody")
    assert encontrada is not None
    assert encontrada["artists"] == "Queen"


def test_sync_library_nao_forcado_e_recente_e_no_op(monkeypatch):
    from datetime import datetime

    from core.spotify_db import set_last_synced_at

    monkeypatch.setattr(spotify_mod.settings, "SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setattr(spotify_mod.settings, "SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.setattr(
        spotify_mod,
        "get_auth_manager",
        lambda: FakeAuthManager(token={"access_token": "x"}, valid=True),
    )
    set_last_synced_at(datetime.now().isoformat())
    chamou = {"vezes": 0}

    def _client_que_nao_deveria_ser_chamado():
        chamou["vezes"] += 1
        return FakeSpotifyClient()

    monkeypatch.setattr(spotify_mod, "get_client", _client_que_nao_deveria_ser_chamado)

    n = spotify_mod.sync_library(force=False)

    assert n == 0
    assert chamou["vezes"] == 0


def test_find_track_encontrado(monkeypatch):
    monkeypatch.setattr(spotify_mod, "_ensure_synced", lambda: None)
    monkeypatch.setattr(spotify_mod, "search_by_name", lambda name: {"id": "1", "name": name})
    assert spotify_mod.find_track("bohemian rhapsody") == {"id": "1", "name": "bohemian rhapsody"}


def test_find_track_nao_encontrado(monkeypatch):
    monkeypatch.setattr(spotify_mod, "_ensure_synced", lambda: None)
    monkeypatch.setattr(spotify_mod, "search_by_name", lambda name: None)
    assert spotify_mod.find_track("musica inexistente") is None


def test_search_track_bate_na_api(monkeypatch):
    monkeypatch.setattr(spotify_mod.settings, "SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setattr(spotify_mod.settings, "SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.setattr(
        spotify_mod,
        "get_auth_manager",
        lambda: FakeAuthManager(token={"access_token": "x"}, valid=True),
    )
    fake_client = FakeSpotifyClient(
        search_result={
            "tracks": {
                "items": [
                    {
                        "id": "9",
                        "name": "Imagine",
                        "artists": [{"name": "John Lennon"}],
                        "external_urls": {"spotify": "https://open.spotify.com/track/9"},
                    }
                ]
            }
        }
    )
    monkeypatch.setattr(spotify_mod, "get_client", lambda: fake_client)

    resultados = spotify_mod.search_track("imagine")

    assert len(resultados) == 1
    assert resultados[0]["name"] == "Imagine"
    assert resultados[0]["artists"] == "John Lennon"


def test_play_sem_dispositivo_ativo_levanta_erro(monkeypatch):
    monkeypatch.setattr(spotify_mod, "get_client", lambda: FakeSpotifyClient(devices=[]))
    with pytest.raises(spotify_mod.NoActiveDeviceError):
        spotify_mod.play("track123")


def test_play_com_dispositivo_ativo(monkeypatch):
    client = FakeSpotifyClient(devices=[{"id": "dev1", "name": "Celular", "is_active": True}])
    monkeypatch.setattr(spotify_mod, "get_client", lambda: client)

    nome_dispositivo = spotify_mod.play("track123")

    assert nome_dispositivo == "Celular"
    assert client.started_playback == ("dev1", ["spotify:track:track123"])


def test_ensure_synced_junta_thread_em_andamento():
    liberar = threading.Event()

    def _sync_lento():
        liberar.wait(timeout=2)

    spotify_mod._sync_thread = threading.Thread(target=_sync_lento, daemon=True)
    spotify_mod._sync_thread.start()
    liberar.set()

    spotify_mod._ensure_synced()

    assert spotify_mod._sync_thread is None


def test_start_background_sync_if_stale_nao_dispara_sem_link(monkeypatch):
    monkeypatch.setattr(spotify_mod, "is_linked", lambda: False)
    spotify_mod.start_background_sync_if_stale()
    assert spotify_mod._sync_thread is None


def test_start_background_sync_if_stale_dispara_quando_linkado(monkeypatch):
    monkeypatch.setattr(spotify_mod, "is_linked", lambda: True)
    monkeypatch.setattr(spotify_mod, "sync_library", lambda force=False: 0)

    spotify_mod.start_background_sync_if_stale()

    assert spotify_mod._sync_thread is not None
    spotify_mod._sync_thread.join(timeout=2)
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `pytest tests/test_spotify.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.spotify'`

- [ ] **Step 3: Implementar `core/spotify.py`**

```python
# core/spotify.py
"""Integração com Spotify — OAuth, sincronização da biblioteca (Curtidas +
playlists) no cache local (core.spotify_db) e reprodução via Spotify
Connect (Fase 4).

Fica inteiramente síncrono, como core/chat.py — a ponte com o mundo
assíncrono do FastAPI vive só nas rotas de interfaces/api.py. O sync em
background segue o mesmo padrão de core/chat.py::ChatSession._ensure_synced
(RAG), mas na escala do processo: como a Jade só tem uma conta Spotify
linkada por vez (não uma por sessão de chat), o "início de sessão" que
dispara o sync vira o startup da API (ver start_background_sync_if_stale)."""

from __future__ import annotations

import contextlib
import threading
from datetime import datetime, timedelta

from core.config import settings
from core.spotify_db import (
    last_synced_at as _last_synced_at,
)
from core.spotify_db import (
    search_by_name,
    set_last_synced_at,
    upsert_tracks,
)

_SCOPE = (
    "user-library-read playlist-read-private "
    "user-modify-playback-state user-read-playback-state"
)

_sync_thread: threading.Thread | None = None
_sync_lock = threading.Lock()


class NoActiveDeviceError(Exception):
    """Nenhum dispositivo Spotify (app aberto em algum lugar) disponível."""


def get_auth_manager():
    import spotipy
    from spotipy.oauth2 import CacheFileHandler

    return spotipy.oauth2.SpotifyOAuth(
        client_id=settings.SPOTIFY_CLIENT_ID,
        client_secret=settings.SPOTIFY_CLIENT_SECRET,
        redirect_uri=settings.SPOTIFY_REDIRECT_URI,
        scope=_SCOPE,
        cache_handler=CacheFileHandler(cache_path=settings.SPOTIFY_TOKEN_CACHE_PATH),
    )


def get_client():
    import spotipy

    return spotipy.Spotify(auth_manager=get_auth_manager())


def is_linked() -> bool:
    if not settings.SPOTIFY_CLIENT_ID or not settings.SPOTIFY_CLIENT_SECRET:
        return False
    auth = get_auth_manager()
    try:
        token = auth.cache_handler.get_cached_token()
        if not token:
            return False
        return bool(auth.validate_token(token))
    except Exception:
        return False


def authorize_url() -> str:
    return get_auth_manager().get_authorize_url()


def handle_callback(code: str) -> None:
    get_auth_manager().get_access_token(code, as_dict=False)


def _to_track_row(track: dict, *, playlist_id: str | None, playlist_name: str | None) -> dict:
    return {
        "id": track["id"],
        "name": track["name"],
        "artists": ", ".join(a["name"] for a in track["artists"]),
        "url": track["external_urls"]["spotify"],
        "playlist_id": playlist_id,
        "playlist_name": playlist_name,
    }


def sync_library(force: bool = False) -> int:
    """Busca Curtidas + todas as playlists salvas e grava no cache local.
    Sem `force`, é no-op se o cache tiver menos de
    SPOTIFY_LIBRARY_STALE_HOURS. Devolve quantas faixas foram gravadas."""
    if not is_linked():
        return 0
    if not force:
        last = _last_synced_at()
        if last is not None:
            try:
                last_dt = datetime.fromisoformat(last)
            except ValueError:
                last_dt = None
            if last_dt is not None and datetime.now() - last_dt < timedelta(
                hours=settings.SPOTIFY_LIBRARY_STALE_HOURS
            ):
                return 0

    sp = get_client()
    tracks: list[dict] = []

    saved = sp.current_user_saved_tracks(limit=50)
    while saved:
        for item in saved["items"]:
            tracks.append(_to_track_row(item["track"], playlist_id=None, playlist_name="Curtidas"))
        saved = sp.next(saved) if saved.get("next") else None

    playlists = sp.current_user_playlists(limit=50)
    while playlists:
        for playlist in playlists["items"]:
            items = sp.playlist_items(playlist["id"], limit=100)
            while items:
                for item in items["items"]:
                    track = item.get("track")
                    if track is None:
                        continue
                    tracks.append(
                        _to_track_row(
                            track, playlist_id=playlist["id"], playlist_name=playlist["name"]
                        )
                    )
                items = sp.next(items) if items.get("next") else None
        playlists = sp.next(playlists) if playlists.get("next") else None

    n = upsert_tracks(tracks)
    set_last_synced_at(datetime.now().isoformat())
    return n


def _sync_safe() -> None:
    """Alvo da thread de background — blindado (exceções numa thread não
    propagam pro join(), então a proteção fica aqui, não em _ensure_synced)."""
    with contextlib.suppress(Exception):
        sync_library()


def start_background_sync_if_stale() -> None:
    """Dispara sync_library() numa thread se a conta estiver linkada e não
    houver uma sync já em andamento. Chamado uma vez no startup da API
    (interfaces/api.py) — equivalente ao disparo em ChatSession.__init__
    para o RAG, mas na escala do processo."""
    global _sync_thread
    with _sync_lock:
        if _sync_thread is not None and _sync_thread.is_alive():
            return
        if not is_linked():
            return
        _sync_thread = threading.Thread(target=_sync_safe, daemon=True)
        _sync_thread.start()


def _ensure_synced() -> None:
    """Espera a sincronização em background terminar, se houver uma
    rodando — custo zero se já tiver terminado. NÃO dispara uma nova (quem
    decide iniciar é start_background_sync_if_stale)."""
    global _sync_thread
    with _sync_lock:
        thread = _sync_thread
    if thread is not None:
        thread.join()
        with _sync_lock:
            if _sync_thread is thread:
                _sync_thread = None


def find_track(name: str) -> dict | None:
    """Busca só no cache local — nunca toca a API."""
    _ensure_synced()
    return search_by_name(name)


def search_track(query: str) -> list[dict]:
    """Busca só na Web API — nunca toca o cache."""
    if not is_linked():
        return []
    sp = get_client()
    results = sp.search(q=query, type="track", limit=5)
    items = results.get("tracks", {}).get("items", [])
    return [_to_track_row(t, playlist_id=None, playlist_name=None) for t in items]


def play(track_id: str) -> str:
    """Manda tocar via Spotify Connect no dispositivo ativo (ou no
    primeiro disponível). Devolve o nome do dispositivo."""
    sp = get_client()
    devices = sp.devices().get("devices", [])
    if not devices:
        raise NoActiveDeviceError("Nenhum dispositivo Spotify ativo.")
    device = next((d for d in devices if d.get("is_active")), devices[0])
    sp.start_playback(device_id=device["id"], uris=[f"spotify:track:{track_id}"])
    return device["name"]
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `pytest tests/test_spotify.py -v`
Expected: PASS (18 testes)

- [ ] **Step 5: Lint + commit**

Run: `ruff check . && ruff format .`

```bash
git add core/spotify.py tests/test_spotify.py
git commit -m "feat(spotify): OAuth, sync em background e tocar/pesquisar (core/spotify.py)"
```

---

## Task 4: `tools/spotify_tool.py` — comandos determinísticos + registro

**Files:**
- Create: `tools/spotify_tool.py`
- Modify: `tools/registry.py`
- Test: `tests/test_spotify_tool.py`

**Interfaces:**
- Consumes: `core.spotify.is_linked/find_track/play/search_track/sync_library/NoActiveDeviceError` (Task 3); `settings.SPOTIFY_TOOL_ENABLED` (Task 1); `tools.base.JadeTool` (contrato já existente).
- Produces: `SpotifyTool` (subclasse de `JadeTool`, `name = "spotify"`), `_parse(query: str) -> tuple[str | None, str | None]`. `tools/registry.py::_TOOLS` passa a conter `SpotifyTool()` antes de `SystemControlTool()`.

- [ ] **Step 1: Escrever os testes (falhando)**

```python
# tests/test_spotify_tool.py
"""Testes da tool de Spotify e do roteador — core.spotify sempre mockado."""

from core.agent_router import route
from tools.spotify_tool import SpotifyTool, _parse

tool = SpotifyTool()


def test_parse_toca():
    assert _parse("toca bohemian rhapsody") == ("play", "bohemian rhapsody")
    assert _parse("coloca imagine dragons") == ("play", "imagine dragons")


def test_parse_pesquisa_no_spotify():
    assert _parse("pesquisa bohemian rhapsody no spotify") == ("search", "bohemian rhapsody")


def test_parse_pesquisa_sem_spotify_nao_e_capturada():
    # Sem "spotify"/"música" na frase, o SystemControlTool cuida da busca web.
    assert _parse("pesquisa gatos fofos no google") == (None, None)


def test_parse_sincroniza():
    assert _parse("sincroniza minhas músicas") == ("sync", None)


def test_parse_nao_e_comando_de_spotify():
    assert _parse("como você está hoje?") == (None, None)


def test_accepts_evita_falso_positivo():
    assert tool.accepts("toca bohemian rhapsody") is True
    assert tool.accepts("me conte uma piada") is False


def test_route_seleciona_spotify_tool_para_tocar():
    r = route("toca bohemian rhapsody")
    assert r is not None
    assert r.name == "spotify"


def test_route_pesquisa_com_spotify_vai_pra_spotify_tool():
    r = route("pesquisa bohemian rhapsody no spotify")
    assert r.name == "spotify"


def test_route_pesquisa_sem_spotify_vai_pro_system_control():
    r = route("pesquisa gatos fofos no google")
    assert r.name == "system_control"


def test_run_play_sem_conta_linkada(monkeypatch):
    monkeypatch.setattr("core.spotify.is_linked", lambda: False)
    resposta = tool.run("toca bohemian rhapsody")
    assert "não está conectada" in resposta


def test_run_play_track_encontrada_e_tocada(monkeypatch):
    monkeypatch.setattr("core.spotify.is_linked", lambda: True)
    monkeypatch.setattr(
        "core.spotify.find_track", lambda name: {"id": "1", "name": "Bohemian Rhapsody"}
    )
    monkeypatch.setattr("core.spotify.play", lambda track_id: "Celular")
    assert tool.run("toca bohemian rhapsody") == "Tocando Bohemian Rhapsody no Celular."


def test_run_play_track_nao_encontrada(monkeypatch):
    monkeypatch.setattr("core.spotify.is_linked", lambda: True)
    monkeypatch.setattr("core.spotify.find_track", lambda name: None)
    resposta = tool.run("toca uma musica que nao existe")
    assert "Não achei" in resposta


def test_run_play_sem_dispositivo_ativo(monkeypatch):
    import core.spotify as spotify_mod

    monkeypatch.setattr("core.spotify.is_linked", lambda: True)
    monkeypatch.setattr(
        "core.spotify.find_track", lambda name: {"id": "1", "name": "Bohemian Rhapsody"}
    )

    def _sem_dispositivo(track_id):
        raise spotify_mod.NoActiveDeviceError("sem dispositivo")

    monkeypatch.setattr("core.spotify.play", _sem_dispositivo)
    resposta = tool.run("toca bohemian rhapsody")
    assert "Não achei nenhum Spotify aberto" in resposta


def test_run_search(monkeypatch):
    monkeypatch.setattr("core.spotify.is_linked", lambda: True)
    monkeypatch.setattr(
        "core.spotify.search_track",
        lambda term: [{"name": "Bohemian Rhapsody", "artists": "Queen"}],
    )
    resposta = tool.run("pesquisa bohemian rhapsody no spotify")
    assert "Bohemian Rhapsody — Queen" in resposta


def test_run_sync(monkeypatch):
    monkeypatch.setattr("core.spotify.is_linked", lambda: True)
    monkeypatch.setattr("core.spotify.sync_library", lambda force=False: 42)
    resposta = tool.run("sincroniza minhas músicas")
    assert resposta == "Atualizei sua biblioteca: 42 faixa(s) no cache."


def test_run_tool_desativada(monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "SPOTIFY_TOOL_ENABLED", False)
    resposta = tool.run("toca bohemian rhapsody")
    assert "desativada" in resposta
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `pytest tests/test_spotify_tool.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.spotify_tool'`

- [ ] **Step 3: Implementar `tools/spotify_tool.py`**

```python
# tools/spotify_tool.py
"""Tool de Spotify — as "mãos" da Jade para tocar/pesquisar música
(Fase 4). Três comandos determinísticos:

- "toca/coloca <nome>": busca só no cache local (sem rede).
- "pesquisa/procura <termo> no spotify": busca só na Web API.
- "sincroniza minhas músicas": força um resync do cache.

Colisão real com tools/system_tool.py: "pesquisa"/"procura"/"busca" também
disparam a busca web do SystemControlTool. Resolvida em duas partes: esta
tool é registrada ANTES de SystemControlTool em tools/registry.py, e
accepts() só aceita busca/sync se a mensagem citar "spotify" ou
"música(s)" — ver docs/superpowers/specs/2026-08-08-spotify-design.md.

O parsing (`_parse`) é uma função pura e testável; a execução (`_run_*`)
fica separada e delega pra core.spotify."""

from __future__ import annotations

from core.config import settings
from tools.base import JadeTool

_PLAY = ("toca", "toque", "coloca", "coloque", "põe", "poe")
_SEARCH = ("pesquisa", "pesquise", "procura", "procure", "busca", "busque")
_SYNC = ("sincroniza", "sincronize", "atualiza minha música", "atualiza minhas músicas")
_SPOTIFY_HINT = ("spotify", "música", "musica", "músicas", "musicas")


def _strip_prefix(text: str, prefixes: tuple[str, ...]) -> str:
    low = text.lower()
    for prefix in prefixes:
        if low.startswith(prefix):
            return text[len(prefix) :].strip(" :")
    return text.strip()


def _parse(query: str) -> tuple[str | None, str | None]:
    """Interpreta o comando. Retorna (tipo, valor) sem efeitos colaterais.

    tipos: 'play' (nome da faixa) · 'search' (termo) · 'sync' (None) ·
    None (não é comando de Spotify)."""
    low = query.lower().strip()

    if any(w in low for w in _SYNC) and any(h in low for h in _SPOTIFY_HINT):
        return "sync", None

    if any(w in low for w in _SEARCH):
        if not any(h in low for h in _SPOTIFY_HINT):
            return None, None
        term = _strip_prefix(query, _SEARCH)
        term = term.replace("no spotify", "").replace("spotify", "").strip(" .!?")
        return ("search", term) if term else (None, None)

    if any(w in low for w in _PLAY):
        term = _strip_prefix(query, _PLAY).strip(" .!?")
        return ("play", term) if term else (None, None)

    return None, None


class SpotifyTool(JadeTool):
    name = "spotify"
    description = (
        "Toca música por nome a partir do cache local, pesquisa faixas na API do "
        "Spotify e sincroniza a biblioteca. Use para 'toca <música>', "
        "'pesquisa <termo> no spotify', 'sincroniza minhas músicas'."
    )
    trigger_hints = _PLAY + _SEARCH + _SYNC + _SPOTIFY_HINT

    def accepts(self, message: str) -> bool:
        return _parse(message)[0] is not None

    def run(self, query: str) -> str:
        if not settings.SPOTIFY_TOOL_ENABLED:
            return "A integração com Spotify está desativada (JADE_SPOTIFY_TOOL_ENABLED=false)."

        kind, value = _parse(query)
        if kind == "play":
            return _run_play(str(value))
        if kind == "search":
            return _run_search(str(value))
        if kind == "sync":
            return _run_sync()
        return (
            "Não identifiquei o comando de Spotify. Tente 'toca <música>' ou "
            "'pesquisa <termo> no spotify'."
        )


_NAO_CONECTADO = (
    "Sua conta Spotify não está conectada. Se já configurou as credenciais no "
    ".env, acesse /spotify/login para conectar."
)


def _run_play(name: str) -> str:
    import core.spotify as spotify

    if not spotify.is_linked():
        return _NAO_CONECTADO
    track = spotify.find_track(name)
    if track is None:
        return f"Não achei '{name}' na sua biblioteca. Quer que eu pesquise no Spotify?"
    try:
        device = spotify.play(track["id"])
    except spotify.NoActiveDeviceError:
        return (
            "Não achei nenhum Spotify aberto pra tocar. Abre o app no computador "
            "ou celular e tenta de novo."
        )
    return f"Tocando {track['name']} no {device}."


def _run_search(term: str) -> str:
    import core.spotify as spotify

    if not spotify.is_linked():
        return _NAO_CONECTADO
    results = spotify.search_track(term)
    if not results:
        return f"Não encontrei nada pra '{term}' no Spotify."
    linhas = [f"{t['name']} — {t['artists']}" for t in results]
    return "Encontrei:\n" + "\n".join(linhas)


def _run_sync() -> str:
    import core.spotify as spotify

    if not spotify.is_linked():
        return _NAO_CONECTADO
    n = spotify.sync_library(force=True)
    return f"Atualizei sua biblioteca: {n} faixa(s) no cache."
```

- [ ] **Step 4: Registrar a tool em `tools/registry.py`**

De:
```python
from tools.base import JadeTool
from tools.system_tool import SystemControlTool

_TOOLS: list[JadeTool] = [
    SystemControlTool(),
    # Registre novas tools aqui (Spotify, e-mail, calendário...).
    # Obs.: a busca no vault (RAG) NÃO é uma tool — acontece direto no chat
    # (core.chat.ChatSession._retrieve_context), que injeta os trechos e deixa
    # o LLM responder. Uma tool de busca devolveria trechos crus (pior UX).
]
```

Por:
```python
from tools.base import JadeTool
from tools.spotify_tool import SpotifyTool
from tools.system_tool import SystemControlTool

_TOOLS: list[JadeTool] = [
    # SpotifyTool ANTES de SystemControlTool: "pesquisa <música> no spotify"
    # colide com o gatilho de busca web do SystemControlTool, e o roteador
    # (core/agent_router.py) usa a primeira tool cujo accepts() aceitar.
    SpotifyTool(),
    SystemControlTool(),
    # Registre novas tools aqui (e-mail, calendário...).
    # Obs.: a busca no vault (RAG) NÃO é uma tool — acontece direto no chat
    # (core.chat.ChatSession._retrieve_context), que injeta os trechos e deixa
    # o LLM responder. Uma tool de busca devolveria trechos crus (pior UX).
]
```

- [ ] **Step 5: Rodar e confirmar que passa**

Run: `pytest tests/test_spotify_tool.py tests/test_system_tool.py tests/test_agent_router.py -v`
Expected: PASS (todos — inclusive os testes já existentes de `system_tool`/`agent_router`, confirmando que a nova tool não quebrou o roteamento anterior)

- [ ] **Step 6: Lint + commit**

Run: `ruff check . && ruff format .`

```bash
git add tools/spotify_tool.py tools/registry.py tests/test_spotify_tool.py
git commit -m "feat(spotify): tool de comandos (toca/pesquisa/sincroniza) e registro"
```

---

## Task 5: Rotas `/spotify/*` em `interfaces/api.py`

**Files:**
- Modify: `interfaces/api.py`
- Test: `tests/test_spotify_api.py`

**Interfaces:**
- Consumes: `core.spotify.is_linked/authorize_url/handle_callback/sync_library/start_background_sync_if_stale` (Task 3); `core.spotify_db.list_tracks/last_synced_at/track_count` (Task 2).
- Produces: `GET /spotify/login`, `GET /spotify/callback`, `GET /spotify/status`, `GET /spotify/library`, `POST /spotify/sync`; hook `@app.on_event("startup")` que dispara `start_background_sync_if_stale()`.

- [ ] **Step 1: Escrever os testes (falhando)**

```python
# tests/test_spotify_api.py
"""Testes das rotas /spotify/* — core.spotify e core.spotify_db mockados,
sem credenciais reais nem rede."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import interfaces.api as api_mod


@pytest.fixture(autouse=True)
def _isola_spotify_api(monkeypatch):
    monkeypatch.setattr("core.spotify.start_background_sync_if_stale", lambda: None)
    yield


def test_spotify_login_redireciona_para_authorize_url(monkeypatch):
    monkeypatch.setattr(
        "core.spotify.authorize_url", lambda: "https://accounts.spotify.com/authorize?x=1"
    )
    client = TestClient(api_mod.app)

    resp = client.get("/spotify/login", follow_redirects=False)

    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "https://accounts.spotify.com/authorize?x=1"


def test_spotify_callback_sucesso(monkeypatch):
    chamado = {}
    monkeypatch.setattr(
        "core.spotify.handle_callback", lambda code: chamado.setdefault("code", code)
    )
    monkeypatch.setattr(
        "core.spotify.start_background_sync_if_stale",
        lambda: chamado.setdefault("sync", True),
    )
    client = TestClient(api_mod.app)

    resp = client.get("/spotify/callback?code=abc123", follow_redirects=False)

    assert resp.headers["location"] == "/app/?spotify=conectado"
    assert chamado == {"code": "abc123", "sync": True}


def test_spotify_callback_sem_code_redireciona_erro():
    client = TestClient(api_mod.app)

    resp = client.get("/spotify/callback", follow_redirects=False)

    assert resp.headers["location"] == "/app/?spotify=erro"


def test_spotify_callback_com_erro_da_spotify_redireciona_erro():
    client = TestClient(api_mod.app)

    resp = client.get("/spotify/callback?error=access_denied", follow_redirects=False)

    assert resp.headers["location"] == "/app/?spotify=erro"


def test_spotify_callback_handle_callback_falha(monkeypatch):
    def _explode(code):
        raise RuntimeError("code inválido")

    monkeypatch.setattr("core.spotify.handle_callback", _explode)
    client = TestClient(api_mod.app)

    resp = client.get("/spotify/callback?code=ruim", follow_redirects=False)

    assert resp.headers["location"] == "/app/?spotify=erro"


def test_spotify_status(monkeypatch):
    monkeypatch.setattr("core.spotify.is_linked", lambda: True)
    monkeypatch.setattr("core.spotify_db.track_count", lambda: 123)
    monkeypatch.setattr("core.spotify_db.last_synced_at", lambda: "2026-08-08T10:00:00")
    client = TestClient(api_mod.app)

    resp = client.get("/spotify/status")

    assert resp.status_code == 200
    assert resp.json() == {
        "linked": True,
        "track_count": 123,
        "last_synced_at": "2026-08-08T10:00:00",
    }


def test_spotify_library_agrupa_por_playlist(monkeypatch):
    monkeypatch.setattr(
        "core.spotify_db.list_tracks",
        lambda: [
            {
                "id": "1",
                "name": "A",
                "artists": "X",
                "url": "u1",
                "playlist_id": "p1",
                "playlist_name": "Rock",
            },
            {
                "id": "2",
                "name": "B",
                "artists": "Y",
                "url": "u2",
                "playlist_id": None,
                "playlist_name": None,
            },
        ],
    )
    client = TestClient(api_mod.app)

    resp = client.get("/spotify/library")

    body = resp.json()
    assert set(body["playlists"].keys()) == {"Rock", "Curtidas"}


def test_spotify_sync_sem_conta_linkada(monkeypatch):
    monkeypatch.setattr("core.spotify.is_linked", lambda: False)
    client = TestClient(api_mod.app)

    resp = client.post("/spotify/sync")

    assert resp.status_code == 400


def test_spotify_sync_forca_resync(monkeypatch):
    monkeypatch.setattr("core.spotify.is_linked", lambda: True)
    monkeypatch.setattr("core.spotify.sync_library", lambda force=False: 7)
    client = TestClient(api_mod.app)

    resp = client.post("/spotify/sync")

    assert resp.status_code == 200
    assert resp.json() == {"synced_tracks": 7}
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `pytest tests/test_spotify_api.py -v`
Expected: FAIL — 404 (rotas ainda não existem) nos primeiros asserts de status code.

- [ ] **Step 3: Adicionar o hook de startup**

De:
```python
def _get_session() -> ChatSession:
    global _session
    if _session is None:
        _session = ChatSession()
    return _session


# WebSocket handshakes não passam pela same-origin policy do browser — o
```

Por:
```python
def _get_session() -> ChatSession:
    global _session
    if _session is None:
        _session = ChatSession()
    return _session


@app.on_event("startup")
def _startup_spotify_sync() -> None:
    """Dispara um resync do cache do Spotify em segundo plano, se a conta já
    estiver conectada e o cache estiver velho — mesmo papel do disparo de
    sync_vault em ChatSession.__init__, mas na escala do processo da API (o
    Spotify não tem um "início de sessão" por conversa)."""
    from core.spotify import start_background_sync_if_stale

    start_background_sync_if_stale()


# WebSocket handshakes não passam pela same-origin policy do browser — o
```

- [ ] **Step 4: Adicionar as rotas de Spotify**

De:
```python
@app.post("/search")
def search(req: SearchRequest) -> dict:
    """Busca semântica direta nas anotações indexadas."""
    from core.memory import query_memory

    try:
        results = query_memory(req.query, k=req.k)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Falha na busca: {e}") from e
    return {"results": results}


FRONTEND_DIR = Path(__file__).parent / "frontend"
```

Por:
```python
@app.post("/search")
def search(req: SearchRequest) -> dict:
    """Busca semântica direta nas anotações indexadas."""
    from core.memory import query_memory

    try:
        results = query_memory(req.query, k=req.k)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Falha na busca: {e}") from e
    return {"results": results}


# ── Spotify (Fase 4) ─────────────────────────────────────────
@app.get("/spotify/login")
def spotify_login() -> RedirectResponse:
    """Redireciona para a tela de autorização do Spotify."""
    from core.spotify import authorize_url

    return RedirectResponse(url=authorize_url())


@app.get("/spotify/callback")
def spotify_callback(code: str | None = None, error: str | None = None) -> RedirectResponse:
    """Troca o code por um token, dispara a 1ª sincronização em segundo
    plano e manda o usuário de volta pro frontend, aba Spotify."""
    if error or not code:
        return RedirectResponse(url="/app/?spotify=erro")

    from core.spotify import handle_callback, start_background_sync_if_stale

    try:
        handle_callback(code)
    except Exception:
        return RedirectResponse(url="/app/?spotify=erro")
    start_background_sync_if_stale()
    return RedirectResponse(url="/app/?spotify=conectado")


@app.get("/spotify/status")
def spotify_status() -> dict:
    from core.spotify import is_linked
    from core.spotify_db import last_synced_at, track_count

    return {
        "linked": is_linked(),
        "track_count": track_count(),
        "last_synced_at": last_synced_at(),
    }


@app.get("/spotify/library")
def spotify_library() -> dict:
    """Cache completo de faixas, agrupado por playlist ('Curtidas' quando
    não vem de nenhuma playlist nomeada)."""
    from core.spotify_db import list_tracks

    grouped: dict[str, list[dict]] = {}
    for track in list_tracks():
        key = track["playlist_name"] or "Curtidas"
        grouped.setdefault(key, []).append(track)
    return {"playlists": grouped}


@app.post("/spotify/sync")
def spotify_sync() -> dict:
    """Força um resync completo da biblioteca (síncrono — a resposta só
    volta quando a sincronização termina)."""
    from core.spotify import is_linked, sync_library

    if not is_linked():
        raise HTTPException(status_code=400, detail="Conta Spotify não conectada.")
    try:
        n = sync_library(force=True)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Falha ao sincronizar: {e}") from e
    return {"synced_tracks": n}


FRONTEND_DIR = Path(__file__).parent / "frontend"
```

- [ ] **Step 5: Rodar e confirmar que passa**

Run: `pytest tests/test_spotify_api.py tests/test_chat_api.py tests/test_conversations_api.py -v`
Expected: PASS (todos — inclusive os testes já existentes de outras rotas, confirmando que nada quebrou)

- [ ] **Step 6: Lint + commit**

Run: `ruff check . && ruff format .`

```bash
git add interfaces/api.py tests/test_spotify_api.py
git commit -m "feat(spotify): rotas /spotify/login, /callback, /status, /library, /sync"
```

---

## Task 6: Frontend — aba "Spotify"

**Files:**
- Create: `interfaces/frontend/lib/spotify-filter.js`
- Create: `interfaces/frontend/spotify.js`
- Modify: `interfaces/frontend/api.js`
- Modify: `interfaces/frontend/app.js`
- Modify: `interfaces/frontend/index.html`
- Modify: `interfaces/frontend/styles.css`
- Test: `interfaces/frontend/__tests__/spotify-filter.test.js`

**Interfaces:**
- Consumes: `GET /spotify/status`, `GET /spotify/library`, `POST /spotify/sync` (Task 5); `createStore` de `interfaces/frontend/lib/state.js` (já existente).
- Produces: `filterTracks(tracks: Array<{name, artists, ...}>, term: string) -> Array` (puro); `spotifyCallbackParam(search: string) -> "conectado" | "erro" | null` (puro); `createSpotify({ store }) -> { activate: () => void }` (wiring de DOM, chamado quando a aba Spotify é aberta).

- [ ] **Step 1: Escrever os testes puros (falhando) — filtro e detecção de callback**

```js
// interfaces/frontend/__tests__/spotify-filter.test.js
import { test } from "node:test";
import assert from "node:assert/strict";
import { filterTracks } from "../lib/spotify-filter.js";

const tracks = [
  { id: "1", name: "Bohemian Rhapsody", artists: "Queen" },
  { id: "2", name: "Imagine", artists: "John Lennon" },
];

test("termo vazio devolve a lista inteira", () => {
  assert.deepEqual(filterTracks(tracks, ""), tracks);
});

test("filtra por nome (case-insensitive)", () => {
  const r = filterTracks(tracks, "bohemian");
  assert.equal(r.length, 1);
  assert.equal(r[0].id, "1");
});

test("filtra por artista", () => {
  const r = filterTracks(tracks, "lennon");
  assert.equal(r.length, 1);
  assert.equal(r[0].id, "2");
});

test("sem correspondência devolve lista vazia", () => {
  assert.deepEqual(filterTracks(tracks, "nada a ver com isso"), []);
});
```

```js
// interfaces/frontend/__tests__/spotify.test.js
import { test } from "node:test";
import assert from "node:assert/strict";
import { spotifyCallbackParam } from "../spotify.js";

test("reconhece o retorno de sucesso do callback OAuth", () => {
  assert.equal(spotifyCallbackParam("?spotify=conectado"), "conectado");
});

test("reconhece o retorno de erro do callback OAuth", () => {
  assert.equal(spotifyCallbackParam("?spotify=erro"), "erro");
});

test("devolve null sem o parametro", () => {
  assert.equal(spotifyCallbackParam(""), null);
});
```

- [ ] **Step 2: Rodar e confirmar que falham**

Run: `node --test interfaces/frontend/__tests__/spotify-filter.test.js interfaces/frontend/__tests__/spotify.test.js`
Expected: FAIL — `Cannot find module '../lib/spotify-filter.js'` e `Cannot find module '../spotify.js'`

- [ ] **Step 3: Implementar o filtro puro**

```js
// interfaces/frontend/lib/spotify-filter.js
// Filtro puro da lista de faixas do Spotify (sem DOM) — testável em Node.
export function filterTracks(tracks, term) {
  const needle = (term || "").trim().toLowerCase();
  if (!needle) return tracks;
  return tracks.filter(
    (t) => t.name.toLowerCase().includes(needle) || t.artists.toLowerCase().includes(needle),
  );
}
```

- [ ] **Step 4: Rodar e confirmar que o filtro passa (o outro segue falhando por enquanto)**

Run: `node --test interfaces/frontend/__tests__/spotify-filter.test.js`
Expected: PASS (4 testes) — `spotify.test.js` continua falhando até o Step 6 criar `spotify.js`, o que é esperado nesta altura.

- [ ] **Step 5: Adicionar os wrappers de fetch em `api.js`**

De (fim do arquivo):
```js
export async function voiceChat(blob) {
  const form = new FormData();
  form.append("file", blob, "fala.webm");
  const res = await fetch("/voice/chat", { method: "POST", body: form });
  if (!res.ok) throw new Error(`/voice/chat → ${res.status}`);
  return res.json();
}
```

Por:
```js
export async function voiceChat(blob) {
  const form = new FormData();
  form.append("file", blob, "fala.webm");
  const res = await fetch("/voice/chat", { method: "POST", body: form });
  if (!res.ok) throw new Error(`/voice/chat → ${res.status}`);
  return res.json();
}

export const getSpotifyStatus = () =>
  fetch("/spotify/status").then((r) => {
    if (!r.ok) throw new Error(`/spotify/status → ${r.status}`);
    return r.json();
  });

export const getSpotifyLibrary = () =>
  fetch("/spotify/library").then((r) => {
    if (!r.ok) throw new Error(`/spotify/library → ${r.status}`);
    return r.json();
  });

export const syncSpotifyNow = () =>
  fetch("/spotify/sync", { method: "POST" }).then((r) => {
    if (!r.ok) throw new Error(`/spotify/sync → ${r.status}`);
    return r.json();
  });
```

- [ ] **Step 6: Criar `interfaces/frontend/spotify.js`**

```js
// interfaces/frontend/spotify.js
// Aba "Spotify": lista de faixas cacheadas (filtro local) + card oficial de
// embed ao selecionar uma faixa. DOM-wiring — não testado por unidade
// (mesmo padrão de chat.js/threads.js); verificado manualmente no browser.
// spotifyCallbackParam() é a única parte pura daqui, por isso é a única
// exportada para teste (interfaces/frontend/__tests__/spotify.test.js).
import { getSpotifyLibrary, getSpotifyStatus, syncSpotifyNow } from "./api.js";
import { filterTracks } from "./lib/spotify-filter.js";

const POLL_INTERVAL_MS = 1500;
const POLL_MAX_ATTEMPTS = 20; // ~30s — depois disso desiste e deixa o botão manual

// Pura — testável sem DOM. `search` é window.location.search. /spotify/callback
// (interfaces/api.py) redireciona pra "/app/?spotify=conectado" ou "=erro".
export function spotifyCallbackParam(search) {
  return new URLSearchParams(search).get("spotify");
}

export function createSpotify({ store } = {}) {
  const filterInput = document.getElementById("spotify-filter");
  const syncBtn = document.getElementById("spotify-sync-btn");
  const statusEl = document.getElementById("spotify-status");
  const listEl = document.getElementById("spotify-list");
  const cardEl = document.getElementById("spotify-card");

  let allTracks = [];
  let loaded = false;

  function renderList(tracks) {
    listEl.innerHTML = "";
    for (const t of tracks) {
      const li = document.createElement("li");
      li.className = "spotify-track";
      li.textContent = `${t.name} — ${t.artists}`;
      li.addEventListener("click", () => selectTrack(t));
      listEl.appendChild(li);
    }
  }

  function selectTrack(track) {
    cardEl.innerHTML = "";
    const iframe = document.createElement("iframe");
    iframe.src = `https://open.spotify.com/embed/track/${track.id}`;
    iframe.width = "100%";
    iframe.height = "152";
    iframe.style.border = "0";
    iframe.allow = "encrypted-media";
    cardEl.appendChild(iframe);
  }

  function applyFilter() {
    renderList(filterTracks(allTracks, filterInput.value));
  }

  function renderDesconectado() {
    statusEl.innerHTML = "";
    statusEl.append("Não conectado. ");
    const link = document.createElement("a");
    link.href = "/spotify/login";
    link.textContent = "Conectar ao Spotify";
    statusEl.appendChild(link);
    listEl.innerHTML = "";
    cardEl.innerHTML = "";
  }

  function renderErro() {
    statusEl.innerHTML = "";
    statusEl.append("Não consegui conectar ao Spotify. ");
    const link = document.createElement("a");
    link.href = "/spotify/login";
    link.textContent = "Tentar novamente";
    statusEl.appendChild(link);
    listEl.innerHTML = "";
    cardEl.innerHTML = "";
  }

  async function loadLibrary(trackCount) {
    statusEl.textContent = `${trackCount} faixa(s) no cache.`;
    const library = await getSpotifyLibrary();
    allTracks = Object.values(library.playlists).flat();
    applyFilter();
  }

  // Logo após o OAuth, o /spotify/callback já redirecionou de volta antes de
  // a sincronização inicial (em thread de background) terminar — sem isso, a
  // aba mostraria "0 faixas" mesmo com a conta recém-conectada.
  function pollUntilSynced(attempt = 0) {
    statusEl.textContent = "Sincronizando sua biblioteca…";
    if (attempt >= POLL_MAX_ATTEMPTS) return;
    setTimeout(async () => {
      try {
        const status = await getSpotifyStatus();
        if (status.track_count > 0) {
          await loadLibrary(status.track_count);
        } else {
          pollUntilSynced(attempt + 1);
        }
      } catch (e) {
        console.error(e);
      }
    }, POLL_INTERVAL_MS);
  }

  async function load() {
    const callbackParam = spotifyCallbackParam(window.location.search);
    if (callbackParam === "erro") {
      renderErro();
      return;
    }
    const status = await getSpotifyStatus();
    if (!status.linked) {
      renderDesconectado();
      return;
    }
    if (status.track_count === 0 && callbackParam === "conectado") {
      pollUntilSynced();
      return;
    }
    await loadLibrary(status.track_count);
  }

  filterInput.addEventListener("input", applyFilter);
  syncBtn.addEventListener("click", async () => {
    statusEl.textContent = "Sincronizando…";
    try {
      await syncSpotifyNow();
    } catch (e) {
      console.error(e);
    }
    await load().catch((e) => console.error(e));
  });

  function activate() {
    if (loaded) return;
    loaded = true;
    load().catch((e) => console.error(e));
  }

  return { activate };
}
```

- [ ] **Step 7: Rodar e confirmar que os dois testes puros passam**

Run: `node --test interfaces/frontend/__tests__/spotify-filter.test.js interfaces/frontend/__tests__/spotify.test.js`
Expected: PASS (7 testes — 4 do filtro + 3 do `spotifyCallbackParam`)

- [ ] **Step 8: Adicionar a tablist e a view Spotify em `index.html`**

De:
```html
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
```

Por:
```html
<body>
  <div class="tabbar" role="tablist" aria-label="Views">
    <button id="tab-chat" class="tab active" role="tab" aria-selected="true">Chat</button>
    <button id="tab-spotify" class="tab" role="tab" aria-selected="false">Spotify</button>
  </div>

  <main id="view-chat" class="layout">
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

  <main id="view-spotify" class="view-spotify" hidden>
    <div class="spotify-toolbar">
      <input id="spotify-filter" class="spotify-filter" type="text"
             placeholder="Filtrar por nome ou artista…" />
      <button id="spotify-sync-btn" class="spotify-sync-btn" type="button">Sincronizar agora</button>
      <span id="spotify-status" class="spotify-status"></span>
    </div>
    <div class="spotify-body">
      <ul id="spotify-list" class="spotify-list"></ul>
      <div id="spotify-card" class="spotify-card"></div>
    </div>
  </main>

  <script type="module" src="app.js"></script>
</body>
```

- [ ] **Step 9: Ligar a alternância de aba em `app.js`**

De:
```js
import { createStore } from "./lib/state.js";
import { createOrb } from "./orb.js";
import { createChat } from "./chat.js";
import { createThreads } from "./threads.js";
import { createVoice } from "./voice.js";
import { reset } from "./api.js";

const store = createStore();
```

Por:
```js
import { createStore } from "./lib/state.js";
import { createOrb } from "./orb.js";
import { createChat } from "./chat.js";
import { createThreads } from "./threads.js";
import { createVoice } from "./voice.js";
import { createSpotify, spotifyCallbackParam } from "./spotify.js";
import { reset } from "./api.js";

const store = createStore();
```

De (fim do arquivo):
```js
voice.bind();
threads.refresh();
orb.setState("idle");
```

Por:
```js
const spotify = createSpotify({ store });

const tabChat = document.getElementById("tab-chat");
const tabSpotify = document.getElementById("tab-spotify");
const viewChat = document.getElementById("view-chat");
const viewSpotify = document.getElementById("view-spotify");

function activateTab(name) {
  const isChat = name === "chat";
  viewChat.hidden = !isChat;
  viewSpotify.hidden = isChat;
  tabChat.classList.toggle("active", isChat);
  tabSpotify.classList.toggle("active", !isChat);
  tabChat.setAttribute("aria-selected", String(isChat));
  tabSpotify.setAttribute("aria-selected", String(!isChat));
  if (!isChat) spotify.activate();
}

tabChat.addEventListener("click", () => activateTab("chat"));
tabSpotify.addEventListener("click", () => activateTab("spotify"));

// Depois do OAuth, /spotify/callback (interfaces/api.py) redireciona pra cá
// com ?spotify=conectado|erro — a aba Spotify precisa abrir sozinha, senão
// o usuário volta pro Chat sem ver o resultado do login.
const veioDoCallback = spotifyCallbackParam(window.location.search) !== null;
activateTab(veioDoCallback ? "spotify" : "chat");

voice.bind();
threads.refresh();
orb.setState("idle");
```

- [ ] **Step 10: Adicionar os estilos em `styles.css`**

De (fim do arquivo):
```css
.jade { display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 16px; }
.orb-canvas { width: 100%; max-width: 320px; aspect-ratio: 1; }
.orb-status { color: var(--jade-spring); letter-spacing: 1px; text-transform: lowercase; }
```

Por:
```css
.jade { display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 16px; }
.orb-canvas { width: 100%; max-width: 320px; aspect-ratio: 1; }
.orb-status { color: var(--jade-spring); letter-spacing: 1px; text-transform: lowercase; }

/* Tablist Chat/Spotify — troca a view inteira abaixo dela. */
.tabbar { display: flex; gap: 4px; padding: 8px 12px; background: var(--panel);
  border-bottom: 1px solid #16211c; }
.tab { padding: 8px 16px; background: transparent; color: var(--muted); border: none;
  border-radius: 8px 8px 0 0; cursor: pointer; font-size: 14px; }
.tab.active { color: var(--jade-spring); background: #14201b; }
.layout, .view-spotify { height: calc(100vh - 41px); }

/* View Spotify: ocupa a área central inteira (sem as colunas de threads/orb). */
.view-spotify { display: flex; flex-direction: column; min-height: 0; background: var(--bg); }
.spotify-toolbar { display: flex; align-items: center; gap: 8px; padding: 12px;
  border-bottom: 1px solid #16211c; }
.spotify-filter { flex: 1; padding: 10px; border-radius: 8px; border: 1px solid #22332b;
  background: #0c1210; color: var(--text); }
.spotify-sync-btn { padding: 10px 14px; border-radius: 8px; cursor: pointer;
  border: 1px solid var(--jade-emerald); background: transparent; color: var(--text); }
.spotify-status { color: var(--muted); font-size: 13px; white-space: nowrap; }
.spotify-status a { color: var(--jade-spring); }
.spotify-body { flex: 1; min-height: 0; display: grid; grid-template-columns: 1fr 1fr;
  gap: 12px; padding: 12px; overflow: hidden; }
.spotify-list { list-style: none; margin: 0; padding: 0; overflow-y: auto; }
.spotify-track { padding: 8px 10px; border-radius: 6px; cursor: pointer; color: var(--text);
  font-size: 14px; }
.spotify-track:hover { background: #14201b; }
.spotify-card { display: flex; align-items: flex-start; justify-content: center; padding-top: 8px; }
```

- [ ] **Step 11: Rodar os testes de frontend e confirmar que passam**

Run: `node --test interfaces/frontend/__tests__/`
Expected: PASS (todos, inclusive os já existentes de `chat.js`/`state.js`/`orb.js`/`markdown.js`/`api.js` — confirmando que nada quebrou)

- [ ] **Step 12: Verificação manual no browser**

Run: `python main.py serve` (ou `uvicorn interfaces.api:app --reload`), abrir `http://127.0.0.1:8000/app/`.

Checklist:
- A tablist aparece no topo; "Chat" começa ativa e a view de 3 colunas de sempre funciona sem regressão.
- Clicar em "Spotify" troca pra a view nova; sem `SPOTIFY_CLIENT_ID`/`SECRET` no `.env`, aparece "Não conectado." com o link pra `/spotify/login`.
- Nenhum erro no console do browser ao alternar as duas abas repetidamente.
- (Se o usuário já tiver preenchido as credenciais reais no `.env` neste ponto) `/spotify/login` completa o fluxo OAuth, a página volta já na aba Spotify mostrando "Sincronizando sua biblioteca…" (polling de `/spotify/status`) até a lista de faixas aparecer sozinha, o filtro por nome/artista funciona em memória, e clicar numa faixa mostra o card de embed oficial do Spotify.
- Abrir `/app/?spotify=erro` diretamente na URL: a aba Spotify abre sozinha mostrando "Não consegui conectar ao Spotify." com o link "Tentar novamente".

- [ ] **Step 13: Lint + commit**

Run: `ruff check . && ruff format . && node --test interfaces/frontend/__tests__/`

```bash
git add interfaces/frontend/lib/spotify-filter.js interfaces/frontend/spotify.js \
  interfaces/frontend/api.js interfaces/frontend/app.js interfaces/frontend/index.html \
  interfaces/frontend/styles.css interfaces/frontend/__tests__/spotify-filter.test.js \
  interfaces/frontend/__tests__/spotify.test.js
git commit -m "feat(spotify): aba Spotify no frontend (lista + card de embed)"
```

---

## Validação manual final (antes de abrir o PR)

Com uma conta Spotify Premium real e credenciais preenchidas no `.env` (per Global Constraints, fora do escopo de CI):

1. `POST`/`GET /spotify/login` → autorizar → callback completa e a aba Spotify mostra "sincronizando…" até a 1ª sync terminar.
2. Observar quanto tempo o 1º sync leva com a biblioteca real do usuário (ver "Riscos" no spec — não medido neste plano).
3. "toca `<nome de uma música da biblioteca>`" — confere resposta e tocando de fato no dispositivo Spotify aberto.
4. "toca `<nome que não existe>`" — confere a resposta de "não achei".
5. "pesquisa `<termo>` no spotify" — confere que bate na API (não no cache) e lista até 5 resultados.
6. "sincroniza minhas músicas" — confere resync forçado e contagem atualizada.
7. Fechar todo app/dispositivo Spotify e tentar "toca `<nome>`" de novo — confere a mensagem de "nenhum dispositivo ativo".

Registrar o resultado dessa validação na descrição do PR antes do merge (mesma exigência do spec, seção "Entregável").
