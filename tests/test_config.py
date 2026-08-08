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
