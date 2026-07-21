"""Testes de persona, humor e perfil — heurística pura + persistência em tmp vault."""

from core import mood, persona, profile
from core.config import settings


def test_mood_classify():
    assert mood.classify("sua burra, faz logo isso") == "rude"
    assert mood.classify("obrigada, adorei!") == "kind"
    assert mood.classify("me desculpa pelo que falei") == "apology"
    assert mood.classify("que horas são?") == "neutral"


def test_mood_delta_e_label():
    assert mood.delta_for("rude", 0) == -2
    assert mood.delta_for("apology", -3) == 2  # desculpa repara mais quando está mal
    assert mood.delta_for("neutral", -3) == 0  # neutro não apaga a mágoa
    assert mood.label_for(-4) == "estressada"
    assert mood.label_for(0) == "neutra"
    assert mood.label_for(5) == "radiante"


def test_mood_instruction_chateada_pede_secura():
    ins = mood.instruction(-4).lower()
    assert "seca" in ins or "curta" in ins


def test_mood_register_persiste_e_recupera(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_PATH", tmp_path)
    baixo, _ = mood.register("você é inútil")
    assert baixo < 0
    recuperado, _ = mood.register("desculpa, foi mal")
    assert recuperado > baixo
    assert (tmp_path / settings.MOOD_NOTE).exists()


def test_persona_inclui_usuario_humor_e_perfil(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_PATH", tmp_path)
    p = persona.build_system_prompt(mood_level=-4, profile_text="- Gosta de café")
    assert settings.USER_NAME in p
    assert "café" in p
    assert "estressada" in p.lower() or "seca" in p.lower()


def test_profile_add_facts_dedup(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_PATH", tmp_path)
    assert profile.add_facts(["Gosta de café", "Programa em Python"]) == 2
    assert profile.add_facts(["gosta de café"]) == 0  # duplicado (case-insensitive)
    assert "Python" in profile.load_profile()


def test_profile_parse_facts():
    assert profile._parse_facts("NADA") == []
    assert profile._parse_facts("- Gosta de X\n- Curte Y\nlinha solta") == ["Gosta de X", "Curte Y"]
