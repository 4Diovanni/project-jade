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

import re

from core.config import settings
from tools.base import JadeTool

_PLAY = ("toca", "toque", "coloca", "coloque", "põe", "poe")
_SEARCH = ("pesquisa", "pesquise", "procura", "procure", "busca", "busque")
_SYNC = ("sincroniza", "sincronize", "atualiza minha música", "atualiza minhas músicas")
_SPOTIFY_HINT = ("spotify", "música", "musica", "músicas", "musicas")

# "toca"/"coloca"/etc. são comandos imperativos — só contam se abrirem a
# mensagem, âncorados com `^` e delimitados por `\b` (palavra inteira). Sem
# isso, substring matching sequestra conversa normal: "compõe", "propõe",
# "estoque" contêm "põe"/"poe" mas não são comandos de tocar música (ver
# achado #1 da whole-branch review, docs/superpowers/plans/2026-08-08-spotify-integracao.md).
_PLAY_RE = re.compile(
    r"^\s*(?:" + "|".join(_PLAY) + r")\b\s*(.*)$",
    re.IGNORECASE,
)
# search/sync não precisam estar no início (podem vir depois de "e agora "),
# mas ainda assim usam \b — palavra inteira, não substring — para a mesma
# robustez. O hint obrigatório de "spotify"/"música" já reduz bastante o
# risco prático aqui, mas a classe de bug é a mesma do ramo `play`.
_SEARCH_RE = re.compile(r"\b(?:" + "|".join(_SEARCH) + r")\b", re.IGNORECASE)
_SYNC_RE = re.compile(
    r"\b(?:sincroniza|sincronize|atualiza\s+minhas?\s+m[uú]sicas?)\b", re.IGNORECASE
)
_SPOTIFY_HINT_RE = re.compile(r"\b(?:spotify|m[uú]sicas?)\b", re.IGNORECASE)


def _strip_prefix(text: str, prefixes: tuple[str, ...]) -> str:
    low = text.lower()
    for prefix in prefixes:
        if low.startswith(prefix):
            return text[len(prefix) :].strip(" :")
    return text.strip()


# "toca a música 13 bala" teria "a música 13 bala" como termo (tudo depois do
# verbo) — mais longo que o nome real da faixa, então nunca bate no match
# exato de `search_by_name` (que exige o termo INTEIRO como substring do
# nome). Sem isso, qualquer "toca a música/canção/faixa X" falhava mesmo com
# X exato no cache (bug real reportado — ver Issue #42).
_FILLER_PREFIXES = ("a música", "a musica", "a canção", "a cancao", "a faixa", "o som")


def _strip_filler(term: str) -> str:
    low = term.lower().strip()
    for prefix in _FILLER_PREFIXES:
        if low == prefix:
            return ""
        if low.startswith(prefix + " "):
            return term[len(prefix) + 1 :].strip()
    return term


def _parse(query: str) -> tuple[str | None, str | None]:
    """Interpreta o comando. Retorna (tipo, valor) sem efeitos colaterais.

    tipos: 'play' (nome da faixa) · 'search' (termo) · 'sync' (None) ·
    None (não é comando de Spotify)."""
    low = query.lower().strip()

    if _SYNC_RE.search(low) and _SPOTIFY_HINT_RE.search(low):
        return "sync", None

    if _SEARCH_RE.search(low):
        if not _SPOTIFY_HINT_RE.search(low):
            return None, None
        term = _strip_prefix(query, _SEARCH)
        term = re.sub(r"(?i)\s*no\s+spotify\s*", " ", term)
        term = re.sub(r"(?i)\bspotify\b", "", term)
        term = _strip_filler(term.strip(" .!?"))
        return ("search", term) if term else (None, None)

    m = _PLAY_RE.match(query)
    if m:
        term = _strip_filler(m.group(1).strip(" :.!?"))
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


#: quanto o 1º candidato precisa liderar o 2º (em score) pra tocar direto
#: sem perguntar — abaixo disso, a diferença é pequena demais pra escolher
#: sozinha (arriscaria tocar a faixa errada).
_SIMILAR_CONFIDENT_MARGIN = 0.15

_SEM_DISPOSITIVO = (
    "Não achei nenhum Spotify aberto pra tocar. Abre o app no computador "
    "ou celular e tenta de novo."
)


def _run_play(name: str) -> str:
    import core.spotify as spotify

    if not spotify.is_linked():
        return _NAO_CONECTADO
    track = spotify.find_track(name)
    if track is None:
        return _run_play_fuzzy(name, spotify)
    try:
        device = spotify.play(track["id"])
    except spotify.NoActiveDeviceError:
        return _SEM_DISPOSITIVO
    return f"Tocando {track['name']} no {device}."


def _run_play_fuzzy(name: str, spotify) -> str:
    """Fallback quando não há match exato: sugere/corrige com base no
    cache local (difflib), em vez de só devolver "não achei" (Issue #42)."""
    candidatos = spotify.find_similar(name)
    if not candidatos:
        return f"Não achei '{name}' na sua biblioteca. Quer que eu pesquise no Spotify?"

    melhor = candidatos[0]
    confiante = len(candidatos) == 1 or (
        melhor["score"] - candidatos[1]["score"] >= _SIMILAR_CONFIDENT_MARGIN
    )
    if confiante:
        try:
            device = spotify.play(melhor["id"])
        except spotify.NoActiveDeviceError:
            return _SEM_DISPOSITIVO
        return (
            f"Não achei '{name}' exato, toquei '{melhor['name']}' "
            f"(mais parecido da sua biblioteca) no {device}."
        )

    linhas = [f"{i}. {t['name']} — {t['artists']}" for i, t in enumerate(candidatos, start=1)]
    return f"Não achei '{name}' exato. Você quis dizer:\n" + "\n".join(linhas) + "\nMe diga qual."


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
