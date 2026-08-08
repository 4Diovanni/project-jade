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
