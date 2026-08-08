# Spotify — link de conta, cache local de faixas e tocar/pesquisar — Design

**Data:** 2026-08-08
**Status:** aprovado no brainstorming; pronto para o plano de implementação
**Escopo:** Fase 4 ("As Mãos") — primeira das duas frentes pedidas nesta rodada
(a segunda, ativação por voz "ok jade"/wake word, fica para um subprojeto
separado e posterior, com spec próprio)

## Contexto

A Fase 4 já deu à Jade controle do sistema operacional
(`tools/system_tool.py`: abrir apps, volume, busca web). O próximo item da
lista ("Falta: Spotify e e-mail", ver `CLAUDE.md`) é dar a ela acesso à
biblioteca musical do usuário — puxar as músicas curtidas e as playlists,
deixar o usuário navegar isso numa aba própria do frontend, e permitir pedir
"toca `<nome>`" por voz/texto.

O requisito central de desempenho, declarado explicitamente pelo usuário: tocar
uma música por nome não pode depender de uma chamada à Web API do Spotify a
cada pedido — precisa vir de um cache local. A API só é consultada quando o
usuário pede uma busca explicitamente ("pesquisa `<termo>` no spotify").

Duas decisões de infraestrutura já confirmadas antes deste spec:

1. O usuário já tem Spotify **Premium** e um app registrado no **Spotify
   Developer Dashboard** (client_id/secret/redirect URI) — pré-requisito para
   controlar reprodução via Web API (Spotify Connect).
2. `requirements.txt` já reserva `spotipy` como dependência comentada
   ("Fase 3+/4: Mãos") — este spec a ativa. `spotipy` cuida de OAuth (fluxo
   Authorization Code), refresh de token e das chamadas à Web API, evitando
   reimplementar isso na mão.

`settings.SQLITE_PATH` existe em `core/config.py` desde a Fase 1 mas nenhum
código o usa hoje (confirmado por busca no repositório) — este subprojeto é
o primeiro a de fato abrir um banco ali.

## Objetivos

1. Login único (OAuth) com a conta Spotify do usuário, com o token
   persistido localmente (sobrevive a reinícios da Jade, nunca vai pro git).
2. Um cache local (SQLite, `settings.SQLITE_PATH`) com todas as faixas das
   Curtidas (Liked Songs) e de todas as playlists salvas do usuário —
   nome, artista, id, url, playlist de origem.
3. `tools/spotify_tool.py` (nova tool, contrato `JadeTool`) reconhece três
   comandos determinísticos:
   - **"toca/coloca `<nome>`"** → busca só no cache local, sem tocar a API.
   - **"pesquisa/procura `<termo>` no spotify"** → busca só na Web API,
     nunca no cache.
   - **"sincroniza minhas músicas"** → força um resync do cache.
4. Reprodução via **Spotify Connect** — a Jade manda tocar no dispositivo
   Spotify que o usuário já tem aberto (app desktop/celular), sem precisar de
   um player embutido no navegador.
5. Uma aba "Spotify" no frontend (troca a view inteira, ao lado da aba
   "Chat"), com a lista das faixas cacheadas (busca/filtro, agrupada por
   playlist) e, ao selecionar uma faixa, o card oficial de embed do Spotify
   (iframe `open.spotify.com/embed/track/<id>`).
6. O cache se atualiza sozinho em background (mesmo padrão do `sync_vault`
   do RAG) se estiver com mais de `SPOTIFY_LIBRARY_STALE_HOURS` (padrão 24h),
   além de poder ser forçado a qualquer momento (comando de voz ou botão na
   aba).

## Não-objetivos

- **Web Playback SDK / navegador como dispositivo Spotify.** Fora de escopo
  — decisão explícita do usuário. A reprodução depende de haver algum
  dispositivo Spotify já ativo em algum lugar (Connect).
- **Ativação por voz "ok jade" (wake word, sempre ouvindo).** Pedida na
  mesma mensagem original, mas confirmada pelo usuário como subprojeto
  separado, com spec próprio, depois deste.
- **Playlists de estudo/produtividade/humor geradas pela Jade,
  personalização por histórico de audição.** Ideias soltas levantadas pelo
  usuário na mesma mensagem — tratadas como escopo exploratório futuro, não
  requisito deste MVP. Nada no design abaixo impede construir isso depois em
  cima do cache já existente.
- **Sincronização incremental "inteligente" (delta via `snapshot_id` de
  playlist).** O resync (manual ou por staleness) sempre busca a biblioteca
  inteira de novo e faz upsert — mais simples, e o volume de dados (faixas de
  um usuário) não justifica a complexidade de um diff incremental agora.
- **Múltiplos usuários / múltiplas contas Spotify.** A Jade é um assistente
  de uma pessoa só (mesma premissa do resto do projeto) — um único token, uma
  única conta linkada por vez.
- **E-mail.** É o outro item pendente da Fase 4 no `CLAUDE.md`, mas não faz
  parte desta rodada.

## Arquitetura

```
tools/spotify_tool.py (NOVO)
  SpotifyTool(JadeTool)
    trigger_hints: "toca", "coloca", "pesquisa"/"procura" + "spotify",
                    "sincroniza"/"atualiza" + "música"/"spotify"
    accepts(): reconhece qual dos 3 comandos (play | search | sync)
    run(): delega pra core.spotify, formata a resposta em texto

core/spotify.py (NOVO)
  - auth: SpotifyOAuth (spotipy) + CacheFileHandler em
    database/spotify_token.json
  - is_linked() / authorize_url() / handle_callback(code)
  - sync_library(force=False): busca Curtidas + playlists via spotipy,
    grava no cache (core/spotify_db.py)
  - find_track(name) -> cache local (sem rede)
  - search_track(query) -> Web API (com rede)
  - play(track_id) -> Spotify Connect (GET /me/player/devices + PUT /me/player/play)
  - _ensure_synced(): dispara/junta thread de sync em background (mesmo
    padrão de core/chat.py::ChatSession._ensure_synced do RAG)

core/spotify_db.py (NOVO)
  - schema SQLite (tabelas tracks, playlists) em settings.SQLITE_PATH
  - upsert_tracks() / search_by_name() / last_synced_at()

interfaces/api.py (rotas novas)
  GET  /spotify/login     → redirect pra authorize_url()
  GET  /spotify/callback  → troca code por token, dispara sync inicial,
                             redireciona pro frontend
  GET  /spotify/status    → linked?, nº de faixas no cache, última sync
  GET  /spotify/library   → cache completo, agrupado por playlist (JSON)
  POST /spotify/sync      → força resync

interfaces/frontend/spotify.js (NOVO)
  - busca /spotify/library, renderiza lista com filtro por nome
  - ao clicar numa faixa: embute o iframe oficial do Spotify
  - botão "sincronizar agora" (POST /spotify/sync)
  - estado "não conectado": link pra /spotify/login
```

Assim como `core/chat.py`, `core/spotify.py` fica inteiramente síncrono — a
ponte com o mundo assíncrono do FastAPI (quando necessária) vive só nas
rotas de `interfaces/api.py`, seguindo o mesmo princípio já validado no
subprojeto de streaming.

## Componentes

### `core/config.py` (novo bloco `── Spotify (Fase 4) ──`)

```python
SPOTIFY_CLIENT_ID: str = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET: str = os.getenv("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI: str = os.getenv(
    "SPOTIFY_REDIRECT_URI", f"http://{API_HOST}:{API_PORT}/spotify/callback"
)
SPOTIFY_TOKEN_CACHE_PATH: str = os.getenv(
    "SPOTIFY_TOKEN_CACHE_PATH", str(BASE_DIR / "database" / "spotify_token.json")
)
SPOTIFY_LIBRARY_STALE_HOURS: int = int(os.getenv("SPOTIFY_LIBRARY_STALE_HOURS", "24"))
SPOTIFY_TOOL_ENABLED: bool = (
    os.getenv("JADE_SPOTIFY_TOOL_ENABLED", "true").strip().lower() != "false"
)
```

Sem `SPOTIFY_CLIENT_ID`/`SPOTIFY_CLIENT_SECRET`, `core/spotify.py` reporta
`is_linked() == False` e a tool informa que a integração não está
configurada — mesma filosofia de degradação do `system_tool`.

### `.env.example` / `.gitignore`

- Entradas comentadas para as 4 variáveis novas de Spotify.
- `.gitignore` ganha `database/spotify_token.json` — o padrão atual
  (`database/*.db`, `database/*.sqlite3`, `database/index_state.json`) é por
  arquivo/extensão, não a pasta inteira, então o token precisa de uma linha
  própria.

### `core/spotify_db.py`

- `_connect()` abre `settings.SQLITE_PATH` (cria o arquivo/tabelas na
  primeira chamada, `CREATE TABLE IF NOT EXISTS`).
- Tabelas: `spotify_tracks(id TEXT PRIMARY KEY, name TEXT, artists TEXT,
  url TEXT, playlist_id TEXT, playlist_name TEXT)` e
  `spotify_meta(key TEXT PRIMARY KEY, value TEXT)` (guarda
  `last_synced_at`).
- `upsert_tracks(tracks: list[dict])`: `INSERT OR REPLACE`, idempotente —
  um resync não duplica.
- `search_by_name(name: str) -> dict | None`: normaliza (lower + strip de
  acentos simples) e faz `LIKE` sobre `name`/`artists`; primeiro resultado
  ganha (sem lib de fuzzy match nova — `difflib` da stdlib se precisar de
  tolerância a erro de digitação).

### `core/spotify.py`

- `get_auth_manager()`: `spotipy.oauth2.SpotifyOAuth(client_id=..., client_secret=..., redirect_uri=..., scope="user-library-read playlist-read-private user-modify-playback-state user-read-playback-state", cache_handler=CacheFileHandler(cache_path=settings.SPOTIFY_TOKEN_CACHE_PATH))`.
- `is_linked() -> bool`: tenta obter um token válido do cache handler
  (`get_cached_token()` + `validate_token()`); `False` se não houver token
  ou o refresh falhar.
- `authorize_url() -> str` / `handle_callback(code: str) -> None`: finos
  wrappers sobre o `auth_manager`.
- `sync_library(force: bool = False) -> int`: se `not force` e
  `last_synced_at()` mais novo que `SPOTIFY_LIBRARY_STALE_HOURS`, no-op;
  senão pagina `sp.current_user_saved_tracks()` e
  `sp.current_user_playlists()` + `sp.playlist_items()` de cada uma,
  monta a lista de faixas e chama `upsert_tracks()`. Retorna quantas
  faixas foram gravadas.
- `_ensure_synced()`: mesmo padrão de `ChatSession._ensure_synced` —
  dispara uma thread de `sync_library()` na criação/uso e só dá `join()`
  quando alguém realmente precisa do resultado (aqui: antes de
  `find_track`/`search_track`, não numa sessão de chat).
- `find_track(name: str) -> dict | None`: `_ensure_synced()` (só espera
  uma sync já em andamento — não dispara uma nova) → `search_by_name()`.
- `search_track(query: str) -> list[dict]`: `sp.search(q=query, type="track", limit=5)`
  — bate direto na API, nunca toca o cache.
- `play(track_id: str) -> str`: `sp.devices()` → sem dispositivo ativo,
  levanta `NoActiveDeviceError`; com dispositivo, `sp.start_playback(device_id=..., uris=[f"spotify:track:{track_id}"])`.

### `tools/spotify_tool.py`

Mesmo formato de `tools/system_tool.py`: uma função `_parse(query) ->
tuple[str | None, str | None]` pura e testável (tipos: `"play"`,
`"search"`, `"sync"`, `None`), e a classe delega pra `core.spotify`.

```python
_PLAY = ("toca", "toque", "coloca", "coloque", "põe", "poe")
_SEARCH = ("pesquisa", "pesquise", "procura", "procure", "busca", "busque")
_SYNC = ("sincroniza", "sincronize", "atualiza minha música", "atualiza minhas músicas")
```

**Colisão real com `tools/system_tool.py`:** `_SEARCH` do `system_tool`
já reconhece "pesquis"/"busca"/"procura" para busca no Google, e
`core/agent_router.py::route()` retorna a **primeira** tool cujo
`accepts()` aceitar, na ordem de `tools/registry.py::_TOOLS`. Sem cuidado,
"pesquisa `<música>` no spotify" seria capturado pelo `SystemControlTool`
antes de a `SpotifyTool` ver a mensagem. Duas medidas juntas resolvem:

1. `tools/registry.py`: `SpotifyTool()` é registrada **antes** de
   `SystemControlTool()` na lista `_TOOLS`.
2. `SpotifyTool.accepts()` só retorna `True` para busca/sync se a mensagem
   contiver explicitamente "spotify" ou "música(s)" além do verbo — uma
   busca genérica ("pesquisa gatos no google") é rejeitada por
   `SpotifyTool` e cai, sem mudança de comportamento, para o
   `SystemControlTool` de sempre.

### `interfaces/frontend/`

- `index.html`: alterna dois `<section>` (chat / spotify) via um par de
  botões no topo (`role="tablist"`), reaproveitando o layout de 3 colunas
  só para a view de chat — a view Spotify ocupa a área central inteira.
- `spotify.js`: `createSpotify({ store })` — busca `/spotify/status` e
  `/spotify/library` ao ativar a aba; renderiza lista + campo de busca
  local (filtra em memória, sem round-trip); iframe do card só é montado
  quando uma faixa é selecionada (evita carregar dezenas de iframes de
  uma vez).

## Fluxo de dados

**Login (uma vez, manual):**
```
usuário abre /spotify/login
  → redirect pra accounts.spotify.com/authorize
  → usuário autoriza
  → GET /spotify/callback?code=...
      → core.spotify.handle_callback(code)  (spotipy grava o token)
      → dispara sync_library(force=True) em thread de background
      → redirect pro frontend, aba Spotify, estado "sincronizando…"
  → frontend faz polling leve de /spotify/status até sync terminar
```

**"Toca `<nome>`":**
```
tool.accepts() → kind="play"
  → core.spotify.find_track(nome)
      → _ensure_synced() (só espera se já houver sync rodando)
      → search_by_name(nome) no SQLite
  → achou:  play(track_id) → "Tocando <nome> no <dispositivo>."
  → não achou: "Não achei '<nome>' na sua biblioteca. Quer que eu
                pesquise no Spotify?"
```

**"Pesquisa `<termo>` no spotify":**
```
tool.accepts() → kind="search"
  → core.spotify.search_track(termo)  (Web API, sem tocar o cache)
  → devolve até 5 resultados em texto (nome — artista)
```

**"Sincroniza minhas músicas":**
```
tool.accepts() → kind="sync"
  → core.spotify.sync_library(force=True)
  → "Atualizei sua biblioteca: N faixa(s) no cache."
```

## Tratamento de erros

- **Sem `SPOTIFY_CLIENT_ID`/`SECRET` configurados:** `is_linked()` sempre
  `False`; a tool responde "Integração com Spotify não configurada" sem
  tentar rede nenhuma.
- **Token expirado, refresh falha (usuário revogou acesso no Spotify):**
  `spotipy` levanta `SpotifyOauthError` no refresh; `core.spotify` captura,
  marca como não-linkado, e qualquer comando responde pedindo pra relogar
  em `/spotify/login`.
- **Nenhum dispositivo Spotify ativo (`play()`):** resposta explícita
  "Não achei nenhum Spotify aberto pra tocar. Abre o app no computador ou
  celular e tenta de novo." — não tenta abrir o app sozinho (fora de
  escopo, diferente do `system_tool`).
- **Sync falha no meio (rede caiu, rate limit da API):** exceção contida
  dentro da thread (`contextlib.suppress(Exception)`, mesmo padrão do
  `sync_vault`); o cache fica no estado da última sync bem-sucedida (nunca
  parcialmente corrompido — cada faixa é um upsert independente); a próxima
  sessão tenta de novo por o cache continuar "stale".
- **`SPOTIFY_TOOL_ENABLED=false`:** a tool não registra `trigger_hints` /
  informa que está desativada — resto da Jade funciona normalmente.
- **Callback OAuth com `code` inválido/expirado:** `/spotify/callback`
  responde com uma página de erro simples e um link pra tentar
  `/spotify/login` de novo.

## Testes

- `core/spotify_db.py`: testes puros de SQLite em banco temporário — upsert
  idempotente, `search_by_name` com variações de caixa/acento,
  `last_synced_at` antes/depois de um upsert. Sem rede.
- `core/spotify.py`: `spotipy.Spotify` e `SpotifyOAuth` **mockados** — nenhum
  teste bate na API real nem exige credenciais. Casos: `sync_library` popula
  o cache a partir de um retorno fake da API; `find_track` achando e não
  achando; `play` sem dispositivo ativo levanta o erro esperado; refresh de
  token falhando → `is_linked() is False`.
- `tools/spotify_tool.py`: mesmo padrão de `tests/test_chat.py`/`FakeTool` —
  `_parse()` reconhece os três comandos e devolve `None` pra frases
  ambíguas; `run()` roteia pra cada um corretamente (com `core.spotify`
  mockado).
- `tests/test_spotify_api.py` (novo): isola `core.spotify` (autouse fixture,
  mesmo padrão do `_isola_chat_api` do subprojeto de streaming) e testa
  `/spotify/status`, `/spotify/library`, `/spotify/sync`, e
  `/spotify/callback` com um `code` fake e `handle_callback` mockado.
- **Sem teste de integração real contra a API do Spotify** — exigiria
  credenciais de verdade rodando em CI, o que não é seguro nem desejável.
  Mesma postura do `python main.py bench` (Ollama): fica fora do CI; o
  usuário valida manualmente com a própria conta antes de abrir o PR
  (login real, sync real, "toca" e "pesquisa" reais).

## Entregável

- `requirements.txt`: descomenta `spotipy`.
- `core/config.py`: bloco de settings de Spotify.
- `.env.example`: entradas comentadas correspondentes.
- `.gitignore`: `database/spotify_token.json`.
- `core/spotify_db.py`, `core/spotify.py`: novos.
- `tools/spotify_tool.py`: novo, registrado em `tools/registry.py`
  **antes** de `SystemControlTool()` (ver "Colisão real" em Componentes).
- `interfaces/api.py`: rotas `/spotify/login`, `/spotify/callback`,
  `/spotify/status`, `/spotify/library`, `/spotify/sync`.
- `interfaces/frontend/`: `spotify.js` novo; `index.html`/`app.js`/
  `styles.css` ganham a alternância de aba Chat/Spotify.
- Testes novos cobrindo os pontos acima.
- Validação manual com conta real (login, sync, tocar, pesquisar) registrada
  no PR antes do merge.
- Este spec e o plano de implementação, commitados em
  `docs/superpowers/`.

## Riscos

- **`search_by_name` é `LIKE` simples, não fuzzy matching de verdade.** Um
  pedido "toca bohemian rapsody" (erro de digitação/fala) pode não bater com
  "Bohemian Rhapsody" no cache. Aceito para o MVP — se se mostrar um
  problema recorrente no uso real (a Jade recebe comandos por voz via STT,
  que já introduz variação), é um upgrade localizado em
  `search_by_name()` (ex.: `difflib.get_close_matches`), não uma mudança de
  arquitetura.
- **Spotify Connect exige um dispositivo já aberto em algum lugar.** Sem o
  app desktop/celular rodando, "toca X" sempre falha com o erro de "nenhum
  dispositivo ativo" — é uma limitação aceita da escolha de não usar o Web
  Playback SDK (ver "Não-objetivos"), não um bug.
- **Sincronizar Curtidas + todas as playlists pode ser uma chamada
  relativamente pesada** para bibliotecas muito grandes (milhares de
  faixas, muitas playlists) — a paginação da Web API do Spotify cobre isso
  corretamente, mas o primeiro sync (login) pode levar alguns segundos a
  minutos dependendo do tamanho da biblioteca real do usuário. Não medido
  neste spec (não há como medir sem a conta real); vale observar o tempo do
  primeiro sync na validação manual antes do PR.
- **Escopo de OAuth pedido (`user-modify-playback-state`) dá à Jade
  permissão de controlar reprodução, não só ler dados.** É exatamente o que
  o objetivo 4 pede (tocar música), mas vale que o usuário tenha isso claro
  ao autorizar o app no navegador — a tela de consentimento do próprio
  Spotify já deixa isso explícito.
