"""Testes de fumaça — não dependem do LLM/Ollama (rodam no CI).

Verificam que a aplicação importa, a API responde e as tools estão registradas.
"""

from fastapi.testclient import TestClient

from core.config import settings
from interfaces.api import app
from tools.registry import get_registered_tools

client = TestClient(app)


def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["provider"] == settings.LLM_PROVIDER


def test_obsidian_tool_registrada():
    names = [tool.name for tool in get_registered_tools()]
    assert "obsidian_search" in names


def test_config_tem_defaults():
    assert settings.LLM_PROVIDER
    assert settings.API_PORT > 0
    # Pastas sensíveis que jamais devem ser indexadas no RAG.
    assert ".obsidian" in settings.VAULT_IGNORE
    assert ".claude" in settings.VAULT_IGNORE
