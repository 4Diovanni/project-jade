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
