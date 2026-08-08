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

    def get_authorize_url(self, state=None):
        self.received_state = state
        return self._url

    def get_access_token(self, code, as_dict=False):
        self.exchanged_code = code
        self.cache_handler._token = {"access_token": "fake"}


class FakeSpotifyClient:
    def __init__(
        self,
        *,
        saved_tracks=None,
        playlists=None,
        playlist_items=None,
        playlist_items_por_id=None,
        devices=None,
        search_result=None,
    ):
        self._saved_tracks = saved_tracks or {"items": [], "next": None}
        self._playlists = playlists or {"items": [], "next": None}
        self._playlist_items = playlist_items or {"items": [], "next": None}
        self._playlist_items_por_id = playlist_items_por_id
        self._devices = devices if devices is not None else []
        self._search_result = search_result or {"tracks": {"items": []}}
        self.started_playback = None
        self.playlist_items_calls: list[dict] = []

    def current_user_saved_tracks(self, limit=50):
        return self._saved_tracks

    def current_user_playlists(self, limit=50):
        return self._playlists

    def playlist_items(self, playlist_id, limit=100, additional_types=None):
        self.playlist_items_calls.append(
            {"playlist_id": playlist_id, "limit": limit, "additional_types": additional_types}
        )
        if self._playlist_items_por_id is not None:
            resultado = self._playlist_items_por_id.get(playlist_id)
            if isinstance(resultado, Exception):
                raise resultado
            return resultado
        return self._playlist_items

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
    spotify_mod._pending_state = None
    yield
    spotify_mod._sync_thread = None
    spotify_mod._pending_state = None


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


def test_authorize_url_gera_state_e_e_aceito_por_validate_state(monkeypatch):
    fake = FakeAuthManager(url="https://x/authorize")
    monkeypatch.setattr(spotify_mod, "get_auth_manager", lambda: fake)

    url = spotify_mod.authorize_url()

    assert url == "https://x/authorize"
    assert fake.received_state  # gerou e passou um state não-vazio
    assert spotify_mod.validate_state(fake.received_state) is True


def test_validate_state_rejeita_state_errado(monkeypatch):
    fake = FakeAuthManager(url="https://x/authorize")
    monkeypatch.setattr(spotify_mod, "get_auth_manager", lambda: fake)
    spotify_mod.authorize_url()

    assert spotify_mod.validate_state("um-state-que-nao-foi-gerado") is False


def test_validate_state_sem_pending_state_rejeita():
    # Nenhum login foi iniciado (_pending_state é None) — qualquer state
    # recebido é rejeitado, inclusive None.
    assert spotify_mod.validate_state(None) is False
    assert spotify_mod.validate_state("qualquer-coisa") is False


def test_validate_state_nao_e_reutilizavel(monkeypatch):
    fake = FakeAuthManager(url="https://x/authorize")
    monkeypatch.setattr(spotify_mod, "get_auth_manager", lambda: fake)
    spotify_mod.authorize_url()

    assert spotify_mod.validate_state(fake.received_state) is True
    # segunda checagem com o MESMO state falha — já foi consumido.
    assert spotify_mod.validate_state(fake.received_state) is False


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


def test_sync_library_pula_episodio_de_podcast_e_faixa_local(monkeypatch):
    """Achado #2 da whole-branch review: playlist_items pode devolver
    episódios de podcast (sem "artists") e faixas locais (sem
    external_urls.spotify) misturados com faixas normais. Sem o guard, o
    primeiro item desses estoura KeyError em _to_track_row e aborta o
    sync inteiro antes do upsert — nenhuma faixa é salva."""
    monkeypatch.setattr(spotify_mod.settings, "SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setattr(spotify_mod.settings, "SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.setattr(
        spotify_mod,
        "get_auth_manager",
        lambda: FakeAuthManager(token={"access_token": "x"}, valid=True),
    )
    episodio = {
        "type": "episode",
        "id": "ep1",
        "name": "Episódio de Podcast",
    }
    faixa_local = {
        "type": "track",
        "id": "local1",
        "name": "Faixa Local",
        "artists": [{"name": "Alguém"}],
        "is_local": True,
        "external_urls": {},
    }
    faixa_valida = {
        "type": "track",
        "id": "2",
        "name": "Imagine",
        "artists": [{"name": "John Lennon"}],
        "external_urls": {"spotify": "https://open.spotify.com/track/2"},
    }
    fake_client = FakeSpotifyClient(
        playlists={
            "items": [{"id": "p1", "name": "Minha Playlist"}],
            "next": None,
        },
        playlist_items={
            "items": [
                {"track": episodio},
                {"track": faixa_local},
                {"track": faixa_valida},
            ],
            "next": None,
        },
    )
    monkeypatch.setattr(spotify_mod, "get_client", lambda: fake_client)

    n = spotify_mod.sync_library(force=True)

    assert n == 1
    from core.spotify_db import search_by_name

    assert search_by_name("imagine") is not None
    assert search_by_name("episodio de podcast") is None
    assert search_by_name("faixa local") is None
    # additional_types=("track",) já filtra a maioria no nível da API.
    assert fake_client.playlist_items_calls[0]["additional_types"] == ("track",)


def test_sync_library_pula_playlist_que_da_erro_mas_preserva_curtidas(monkeypatch, caplog):
    """Playlists geradas pelo Spotify (Feita Pra Você, Daily Mix...) podem
    devolver 403 em playlist_items mesmo aparecendo em
    current_user_playlists. Sem isolar por playlist, essa exceção abortava
    sync_library() inteiro antes do upsert — as Curtidas, já coletadas em
    memória, eram perdidas junto."""
    monkeypatch.setattr(spotify_mod.settings, "SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setattr(spotify_mod.settings, "SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.setattr(
        spotify_mod,
        "get_auth_manager",
        lambda: FakeAuthManager(token={"access_token": "x"}, valid=True),
    )
    faixa_valida = {
        "type": "track",
        "id": "2",
        "name": "Imagine",
        "artists": [{"name": "John Lennon"}],
        "external_urls": {"spotify": "https://open.spotify.com/track/2"},
    }
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
        },
        playlists={
            "items": [
                {"id": "proibida", "name": "Feita Pra Você"},
                {"id": "ok", "name": "Minha Playlist"},
            ],
            "next": None,
        },
        playlist_items_por_id={
            "proibida": Exception("403 Forbidden"),
            "ok": {"items": [{"track": faixa_valida}], "next": None},
        },
    )
    monkeypatch.setattr(spotify_mod, "get_client", lambda: fake_client)

    with caplog.at_level("WARNING"):
        n = spotify_mod.sync_library(force=True)

    assert n == 2
    from core.spotify_db import search_by_name

    assert search_by_name("bohemian rhapsody") is not None
    assert search_by_name("imagine") is not None
    assert "Feita Pra Você" in caplog.text


def test_sync_safe_loga_excecao_em_vez_de_engolir_silenciosamente(monkeypatch, caplog):
    def _explode(force=False):
        raise RuntimeError("falha simulada de sync")

    monkeypatch.setattr(spotify_mod, "sync_library", _explode)

    with caplog.at_level("ERROR"):
        spotify_mod._sync_safe()

    assert "Falha ao sincronizar" in caplog.text


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


def test_start_background_sync_if_stale_nao_dispara_segunda_sync_enquanto_viva(monkeypatch):
    """Guarda contra sync duplicada: se já há uma thread viva, chamar
    start_background_sync_if_stale() de novo é no-op (retorna sem criar
    segunda thread)."""
    monkeypatch.setattr(spotify_mod, "is_linked", lambda: True)
    liberar = threading.Event()

    def _sync_lento():
        liberar.wait(timeout=2)

    # Inicia thread falsa que dura enquanto liberar não é setado
    thread_original = threading.Thread(target=_sync_lento, daemon=True)
    thread_original.start()
    spotify_mod._sync_thread = thread_original

    # Chama start_background_sync_if_stale enquanto thread ainda está viva
    spotify_mod.start_background_sync_if_stale()

    # Confirma que É O MESMO objeto de thread (identidade, não só "não é None")
    assert spotify_mod._sync_thread is thread_original

    # Libera e aguarda terminação
    liberar.set()
    thread_original.join(timeout=2)
