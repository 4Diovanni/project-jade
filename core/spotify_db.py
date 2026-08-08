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
        row = conn.execute("SELECT value FROM spotify_meta WHERE key = 'last_synced_at'").fetchone()
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
