"""Testes da tool de criação de arquivos por contexto — puros para o parsing,
com efeitos colaterais isolados num diretório temporário (CI-safe)."""

from pathlib import Path

from core.agent_router import route
from tools.file_tool import FileCreateTool, _extract_content, _extract_filename, _parse, _slugify

tool = FileCreateTool()


def test_parse_txt_com_conteudo_apos_marcador():
    kind, req = _parse("crie um arquivo txt onde nele vai estar escrito eu amo minha namorada")
    assert kind == "create"
    assert req.extension == "txt"
    assert req.content == "eu amo minha namorada"


def test_parse_md_com_nome_explicito():
    kind, req = _parse(
        "faça um arquivo md chamado receita com o texto bolo de cenoura escrito nele"
    )
    assert kind == "create"
    assert req.extension == "md"
    assert req.filename == "receita"
    assert req.content.startswith("bolo de cenoura")


def test_parse_conteudo_entre_aspas_tem_prioridade():
    kind, req = _parse('crie um arquivo txt com "feliz aniversário" escrito nele')
    assert kind == "create"
    assert req.content == "feliz aniversário"


def test_parse_formato_desconhecido():
    assert _parse("crie um arquivo techiste com isso escrito nele")[0] == "unknown_format"


def test_parse_sem_formato_algum():
    assert _parse("crie um arquivo com isso escrito nele")[0] == "unknown_format"


def test_parse_nao_e_pedido_de_arquivo():
    assert _parse("qual é a capital da França?")[0] == "none"
    assert _parse("abra o arquivo de configurações")[0] == "none"  # sem verbo de criação


def test_extract_content_sem_marcador_fica_vazio():
    assert _extract_content("crie um arquivo txt") == ""


def test_extract_filename_none_quando_sem_marcador():
    assert _extract_filename("crie um arquivo txt com bolo escrito nele") is None


def test_slugify_remove_separador_de_caminho():
    # Nunca deve virar componente de diretório nem sair da pasta base.
    assert "/" not in _slugify("../../etc/passwd")
    assert "\\" not in _slugify("..\\..\\windows\\system32")
    assert ".." not in _slugify("nome com ../ dentro")


def test_accepts_evita_falso_positivo():
    assert tool.accepts("crie um arquivo txt com bolo escrito nele") is True
    assert tool.accepts("abra o bloco de notas") is False
    assert tool.accepts("me conte uma piada") is False


def test_route_seleciona_file_tool():
    r = route("crie um arquivo txt com bolo escrito nele")
    assert r is not None
    assert r.name == "file_create"


def test_run_cria_arquivo_no_diretorio_configurado(tmp_path: Path, monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "FILES_TOOL_BASE_DIR", tmp_path)

    resultado = tool.run("crie um arquivo txt onde vai estar escrito eu amo minha namorada")

    arquivos = list(tmp_path.glob("*.txt"))
    assert len(arquivos) == 1
    assert arquivos[0].read_text(encoding="utf-8") == "eu amo minha namorada"
    assert arquivos[0].name in resultado


def test_run_nao_sobrescreve_arquivo_existente(tmp_path: Path, monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "FILES_TOOL_BASE_DIR", tmp_path)
    (tmp_path / "bolo.txt").write_text("original", encoding="utf-8")

    tool.run("crie um arquivo txt chamado bolo com receita nova escrita nele")

    assert (tmp_path / "bolo.txt").read_text(encoding="utf-8") == "original"
    assert (tmp_path / "bolo_2.txt").exists()


def test_run_formato_desconhecido_nao_cria_arquivo(tmp_path: Path, monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "FILES_TOOL_BASE_DIR", tmp_path)

    resultado = tool.run("crie um arquivo techiste com isso escrito nele")

    assert list(tmp_path.iterdir()) == []
    assert ".txt" in resultado and ".md" in resultado
