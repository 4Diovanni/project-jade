"""Testes da tool de Spotify e do roteador — core.spotify sempre mockado."""

from core.agent_router import route
from tools.spotify_tool import SpotifyTool, _parse

tool = SpotifyTool()


def test_parse_toca():
    assert _parse("toca bohemian rhapsody") == ("play", "bohemian rhapsody")
    assert _parse("coloca imagine dragons") == ("play", "imagine dragons")


def test_parse_pesquisa_no_spotify():
    assert _parse("pesquisa bohemian rhapsody no spotify") == ("search", "bohemian rhapsody")


def test_parse_pesquisa_preserva_case_do_termo_mesmo_com_spotify_maiusculo():
    assert _parse("pesquisa Bohemian Rhapsody no Spotify") == ("search", "Bohemian Rhapsody")


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
