"""Testes do roteador dual-model — heurística pura, sem chamar nenhum LLM."""

from core.model_router import choose_route, looks_informational


def test_looks_informational_verdadeiro():
    assert looks_informational("como preparar um bolo de cenoura?")
    assert looks_informational("qual a diferença entre TCP e UDP")
    assert looks_informational("me explica o que é fotossíntese")


def test_looks_informational_falso():
    assert not looks_informational("oi, tudo bem?")
    assert not looks_informational("valeu!")
    assert not looks_informational("bom dia")


def test_choose_route_sem_nuvem_sempre_local():
    assert (
        choose_route("como funciona um motor?", has_context=False, cloud_available=False) == "local"
    )


def test_choose_route_contexto_pessoal_fica_local():
    # Mesmo sendo "informativa", se veio das notas pessoais → local (privacidade).
    assert choose_route("como foi a reunião?", has_context=True, cloud_available=True) == "local"


def test_choose_route_informativa_vai_para_nuvem():
    assert (
        choose_route("como preparar um risoto de camarão?", has_context=False, cloud_available=True)
        == "cloud"
    )


def test_choose_route_conversa_simples_fica_local():
    assert choose_route("oi jade", has_context=False, cloud_available=True) == "local"
