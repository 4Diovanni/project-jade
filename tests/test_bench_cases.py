"""Testes do carregador de casos do benchmark (bench.cases).

Puro parsing e validação — não executa a Jade nem toca no LLM.
"""

import pytest

from bench.cases import Case, CaseError, load_cases

_VALIDO = """
- id: tool-calculadora
  message: "abra a calculadora"
  expect: { route: tool, tool: system_control }

- id: papo-curto
  message: "oi, tudo bem?"
  expect: { route: local, context: none }
"""


def _escreve(tmp_path, nome, conteudo):
    arquivo = tmp_path / nome
    arquivo.write_text(conteudo, encoding="utf-8")
    return arquivo


def test_carrega_casos_de_um_arquivo(tmp_path):
    arquivo = _escreve(tmp_path, "tools.yaml", _VALIDO)
    casos = load_cases(arquivo)
    assert [c.id for c in casos] == ["tool-calculadora", "papo-curto"]
    assert isinstance(casos[0], Case)
    assert casos[0].expect["route"] == "tool"


def test_categoria_vem_do_nome_do_arquivo(tmp_path):
    arquivo = _escreve(tmp_path, "tools.yaml", _VALIDO)
    assert {c.category for c in load_cases(arquivo)} == {"tools"}


def test_carrega_um_diretorio_inteiro(tmp_path):
    _escreve(tmp_path, "tools.yaml", _VALIDO)
    _escreve(
        tmp_path,
        "memoria.yaml",
        '- id: mem-1\n  message: "qual o modelo?"\n  expect: { route: local }\n',
    )
    casos = load_cases(tmp_path)
    assert len(casos) == 3
    assert {c.category for c in casos} == {"tools", "memoria"}


def test_rejeita_id_duplicado(tmp_path):
    conteudo = (
        '- id: repetido\n  message: "a"\n  expect: { route: local }\n'
        '- id: repetido\n  message: "b"\n  expect: { route: local }\n'
    )
    arquivo = _escreve(tmp_path, "tools.yaml", conteudo)
    with pytest.raises(CaseError, match="repetido"):
        load_cases(arquivo)


def test_rejeita_chave_de_expect_desconhecida(tmp_path):
    arquivo = _escreve(
        tmp_path, "tools.yaml", '- id: x\n  message: "a"\n  expect: { rota: local }\n'
    )
    with pytest.raises(CaseError, match="rota"):
        load_cases(arquivo)


def test_rejeita_valor_de_rota_invalido(tmp_path):
    arquivo = _escreve(
        tmp_path, "tools.yaml", '- id: x\n  message: "a"\n  expect: { route: nuvem }\n'
    )
    with pytest.raises(CaseError, match="nuvem"):
        load_cases(arquivo)


def test_rejeita_caso_sem_message(tmp_path):
    arquivo = _escreve(tmp_path, "tools.yaml", "- id: x\n  expect: { route: local }\n")
    with pytest.raises(CaseError, match="message"):
        load_cases(arquivo)


def test_rejeita_yaml_que_nao_e_lista(tmp_path):
    arquivo = _escreve(tmp_path, "tools.yaml", "id: x\nmessage: a\n")
    with pytest.raises(CaseError, match="lista"):
        load_cases(arquivo)


def test_os_casos_reais_do_projeto_sao_validos():
    """Os casos versionados em bench/cases/ precisam passar na validação."""
    casos = load_cases("bench/cases")
    assert len(casos) >= 20
