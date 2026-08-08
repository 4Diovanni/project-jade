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

import logging
import secrets
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

logger = logging.getLogger(__name__)

_SCOPE = (
    "user-library-read playlist-read-private user-modify-playback-state user-read-playback-state"
)

_sync_thread: threading.Thread | None = None
_sync_lock = threading.Lock()

# Proteção CSRF do fluxo OAuth (parâmetro `state` padrão do OAuth2): guarda
# só o último state gerado — a Jade é single-user/local, não precisa de um
# store mais elaborado. Sem isso, /spotify/callback aceitava qualquer
# `?code=` recebido, o que (a API roda sem autenticação em 127.0.0.1) abria
# risco teórico de uma página maliciosa induzir a navegação pro callback com
# o code de outra conta (achado #4 da whole-branch review).
_pending_state: str | None = None


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
    global _pending_state
    _pending_state = secrets.token_urlsafe(16)
    return get_auth_manager().get_authorize_url(state=_pending_state)


def validate_state(received_state: str | None) -> bool:
    """Compara o `state` recebido em /spotify/callback com o gerado pela
    última chamada a `authorize_url()`. Limpa `_pending_state` depois de
    checar (sempre, válido ou não) para não ser reutilizável — cada
    tentativa de login usa um state novo."""
    global _pending_state
    expected = _pending_state
    _pending_state = None
    return expected is not None and received_state == expected


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
            try:
                # additional_types=("track",) filtra episódios de podcast no
                # nível da API — sem isso, playlist_items devolve episódios
                # misturados com faixas (achado #2 da whole-branch review).
                items = sp.playlist_items(playlist["id"], limit=100, additional_types=("track",))
                while items:
                    for item in items["items"]:
                        track = item.get("track")
                        # Defesa extra: episódios de podcast (não filtrados pela
                        # API por algum motivo), faixas locais e faixas
                        # indisponíveis não têm os campos que _to_track_row
                        # precisa (artists, external_urls.spotify, id) — pula,
                        # não deixa estourar KeyError e abortar o sync inteiro.
                        if (
                            not track
                            or track.get("type") not in (None, "track")
                            or not track.get("id")
                            or not track.get("artists")
                            or not track.get("external_urls", {}).get("spotify")
                        ):
                            continue
                        tracks.append(
                            _to_track_row(
                                track, playlist_id=playlist["id"], playlist_name=playlist["name"]
                            )
                        )
                    items = sp.next(items) if items.get("next") else None
            except Exception:
                # Playlists geradas pelo Spotify (Feita Pra Você, Daily Mix,
                # Discover Weekly...) aparecem em current_user_playlists mas
                # a leitura de itens pode devolver 403 — não é um erro do
                # usuário nem da Jade, é uma restrição da própria API. Sem
                # isolar por playlist, essa exceção abortava sync_library()
                # inteiro ANTES do upsert_tracks, perdendo até as Curtidas
                # já coletadas em memória.
                logger.warning(
                    "Não consegui ler a playlist %r (%s) — pulando.",
                    playlist.get("name"),
                    playlist.get("id"),
                    exc_info=True,
                )
                continue
        playlists = sp.next(playlists) if playlists.get("next") else None

    n = upsert_tracks(tracks)
    set_last_synced_at(datetime.now().isoformat())
    return n


def _sync_safe() -> None:
    """Alvo da thread de background — blindado (exceções numa thread não
    propagam pro join(), então a proteção fica aqui, não em _ensure_synced).
    Loga antes de suprimir: uma falha de sync silenciosa deixava o cache
    vazio pra sempre sem nenhuma pista do motivo (achado #2 da whole-branch
    review)."""
    try:
        sync_library()
    except Exception:
        logger.exception("Falha ao sincronizar biblioteca do Spotify")


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
