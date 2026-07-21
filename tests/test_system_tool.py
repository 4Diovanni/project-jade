"""Testes da tool de controle do sistema e do roteador — puros, sem efeitos
colaterais no SO (CI-safe: não abrem apps nem mexem no volume)."""

from core.agent_router import route
from tools.system_tool import SystemControlTool, _extract_search_term, _parse

tool = SystemControlTool()


def test_parse_volume():
    assert _parse("aumenta o volume") == ("volume", "up")
    assert _parse("abaixa o volume") == ("volume", "down")
    assert _parse("coloca no mudo") == ("volume", "mute")


def test_parse_abrir_app_da_whitelist():
    kind, value = _parse("abra a calculadora")
    assert kind == "open"
    assert isinstance(value, tuple)
    assert value[1] == "calc.exe"


def test_parse_abrir_app_desconhecido():
    assert _parse("abra o photoshop")[0] == "open_unknown"


def test_parse_pesquisa():
    kind, term = _parse("pesquise gatos fofos no google")
    assert kind == "search"
    assert term == "gatos fofos"


def test_extract_search_term():
    assert _extract_search_term("pesquise receita de bolo no google") == "receita de bolo"
    assert _extract_search_term("buscar clima em são paulo") == "clima em são paulo"


def test_parse_nao_e_comando_de_sistema():
    assert _parse("como você está hoje?")[0] is None


def test_accepts_evita_falso_positivo():
    assert tool.accepts("abra o bloco de notas") is True
    assert tool.accepts("me conte uma piada") is False


def test_route_seleciona_system_tool():
    r = route("aumente o volume")
    assert r is not None
    assert r.name == "system_control"


def test_route_none_para_conversa():
    assert route("qual é a capital da França?") is None
