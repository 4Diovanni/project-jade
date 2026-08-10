"""Testes da tool de Spotify e do roteador — core.spotify sempre mockado."""

from core.agent_router import route
from tools.spotify_tool import SpotifyTool, _parse

tool = SpotifyTool()


def test_parse_toca():
    assert _parse("toca bohemian rhapsody") == ("play", "bohemian rhapsody")
    assert _parse("coloca imagine dragons") == ("play", "imagine dragons")


def test_parse_remove_filler_word_antes_do_nome():
    # Log real (Issue #42): "toque a música 13 bala" falhava porque o termo
    # extraído carregava "a música" grudado no nome.
    assert _parse("toque a música 13 bala") == ("play", "13 bala")
    assert _parse("toca a canção Imagine") == ("play", "Imagine")
    assert _parse("pesquisa a música bohemian rhapsody no spotify") == (
        "search",
        "bohemian rhapsody",
    )


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


def test_parse_nao_captura_conversa_normal_com_substrings_parecidas():
    # Substring matching antigo sequestrava essas frases (achado #1 da
    # whole-branch review): "põe"/"poe" aparecem dentro de "propõe",
    # "compõe", "poesia"; "coloca" dentro de "colocar".
    assert _parse("me escreve um poema sobre o mar") == (None, None)
    assert _parse("o que voce propõe pra melhorar isso?") == (None, None)
    assert _parse("como se compõe uma sinfonia?") == (None, None)
    assert _parse("qual o estoque do almoxarifado?") == (None, None)
    assert _parse("voce pode colocar meus compromissos em ordem?") == (None, None)
    assert _parse("poesia e importante pra voce?") == (None, None)


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


def test_run_play_track_nao_encontrada_sem_similar(monkeypatch):
    monkeypatch.setattr("core.spotify.is_linked", lambda: True)
    monkeypatch.setattr("core.spotify.find_track", lambda name: None)
    monkeypatch.setattr("core.spotify.find_similar", lambda name, limit=3: [])
    resposta = tool.run("toca uma musica que nao existe")
    assert "Não achei" in resposta
    assert "Quer que eu pesquise" in resposta


def test_run_play_com_filler_word_encontra_faixa_exata(monkeypatch):
    # Issue #42/log real: "toca a música 13 bala" não pode falhar só porque
    # o termo extraído tinha "a música" na frente do nome exato da faixa.
    monkeypatch.setattr("core.spotify.is_linked", lambda: True)
    chamadas = []

    def _find_track(name):
        chamadas.append(name)
        return {"id": "1", "name": "13 Bala"} if name == "13 bala" else None

    monkeypatch.setattr("core.spotify.find_track", _find_track)
    monkeypatch.setattr("core.spotify.play", lambda track_id: "Celular")
    resposta = tool.run("toca a música 13 bala")
    assert chamadas == ["13 bala"]
    assert resposta == "Tocando 13 Bala no Celular."


def test_run_play_sem_match_exato_toca_candidato_confiante(monkeypatch):
    monkeypatch.setattr("core.spotify.is_linked", lambda: True)
    monkeypatch.setattr("core.spotify.find_track", lambda name: None)
    monkeypatch.setattr(
        "core.spotify.find_similar",
        lambda name, limit=3: [
            {"id": "1", "name": "Bohemian Rhapsody", "artists": "Queen", "score": 0.95},
            {"id": "2", "name": "Outra faixa", "artists": "Alguém", "score": 0.4},
        ],
    )
    monkeypatch.setattr("core.spotify.play", lambda track_id: "Celular")
    resposta = tool.run("toca bohemian rapsody")
    assert "toquei 'Bohemian Rhapsody'" in resposta
    assert "Celular" in resposta


def test_run_play_candidatos_ambiguos_lista_opcoes_sem_tocar(monkeypatch):
    monkeypatch.setattr("core.spotify.is_linked", lambda: True)
    monkeypatch.setattr("core.spotify.find_track", lambda name: None)
    monkeypatch.setattr(
        "core.spotify.find_similar",
        lambda name, limit=3: [
            {"id": "1", "name": "13 Bala", "artists": "Nebrugg", "score": 0.8},
            {"id": "2", "name": "6Balas", "artists": "kamaitachi", "score": 0.75},
        ],
    )

    def _play_nao_deveria_rodar(track_id):
        raise AssertionError("não deveria tocar automaticamente quando é ambíguo")

    monkeypatch.setattr("core.spotify.play", _play_nao_deveria_rodar)
    resposta = tool.run("toca bala")
    assert "Você quis dizer" in resposta
    assert "13 Bala — Nebrugg" in resposta
    assert "6Balas — kamaitachi" in resposta


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
