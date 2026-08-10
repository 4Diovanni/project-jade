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


def test_upsert_tracks_com_mesma_faixa_em_curtidas_e_playlist_conta_uma_vez():
    """Achado #3 da whole-branch review: uma faixa em Curtidas E numa
    playlist gera duas entradas com o mesmo id na lista que sync_library()
    monta; upsert_tracks() devolvia len(tracks) (2), inflado em relação a
    track_count() (1) — /spotify/sync e /spotify/status divergiam."""
    tracks = [
        {
            "id": "1",
            "name": "Bohemian Rhapsody",
            "artists": "Queen",
            "url": "https://open.spotify.com/track/1",
            "playlist_id": None,
            "playlist_name": "Curtidas",
        },
        {
            "id": "1",
            "name": "Bohemian Rhapsody",
            "artists": "Queen",
            "url": "https://open.spotify.com/track/1",
            "playlist_id": "p1",
            "playlist_name": "Rock",
        },
    ]
    assert db.upsert_tracks(tracks) == 1
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


def test_search_similar_corrige_nome_com_typo():
    db.upsert_tracks(
        [
            {
                "id": "6",
                "name": "Bohemian Rhapsody",
                "artists": "Queen",
                "url": "u6",
                "playlist_id": None,
                "playlist_name": None,
            }
        ]
    )
    resultado = db.search_similar("bohemian rapsody")  # typo em "rhapsody"
    assert resultado
    assert resultado[0]["id"] == "6"
    assert 0.6 <= resultado[0]["score"] <= 1.0


def test_search_similar_lista_varios_candidatos_proximos_ordenados():
    db.upsert_tracks(
        [
            {
                "id": "7",
                "name": "13 Bala",
                "artists": "Nebrugg",
                "url": "u7",
                "playlist_id": None,
                "playlist_name": None,
            },
            {
                "id": "8",
                "name": "6Balas",
                "artists": "kamaitachi",
                "url": "u8",
                "playlist_id": None,
                "playlist_name": None,
            },
        ]
    )
    resultado = db.search_similar("bala", limit=3)
    ids = [t["id"] for t in resultado]
    assert "7" in ids
    # ordenado por score decrescente
    assert all(
        resultado[i]["score"] >= resultado[i + 1]["score"] for i in range(len(resultado) - 1)
    )


def test_search_similar_nada_parecido_devolve_vazio():
    db.upsert_tracks(
        [
            {
                "id": "9",
                "name": "Bohemian Rhapsody",
                "artists": "Queen",
                "url": "u9",
                "playlist_id": None,
                "playlist_name": None,
            }
        ]
    )
    assert db.search_similar("um nome completamente diferente de qualquer coisa") == []


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
