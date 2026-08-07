"""Testes dos endpoints de chat da API (/chat, /voice/chat, /ws/chat) — LLM,
tools, RAG e journal mockados (sem Ollama, sem rede, sem escrever no vault)."""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest
from fastapi.testclient import TestClient

import core.chat as chat_mod
import interfaces.api as api_mod
from core.config import settings


class FakeLLM:
    """Mesmo espírito do FakeLLM de tests/test_chat.py, local a este arquivo
    para não acoplar os dois módulos de teste."""

    def __init__(self, reply: str = "resposta da api") -> None:
        self.reply = reply

    def invoke(self, messages):
        return type("Msg", (), {"content": self.reply})()

    def stream(self, messages):
        from langchain_core.messages import AIMessageChunk

        meio = len(self.reply) // 2 or 1
        yield AIMessageChunk(content=self.reply[:meio])
        yield AIMessageChunk(content=self.reply[meio:])


@pytest.fixture(autouse=True)
def _isola_chat_api(monkeypatch, tmp_path):
    monkeypatch.setattr(chat_mod, "get_llm", lambda *a, **k: FakeLLM())
    monkeypatch.setattr(chat_mod, "build_system_prompt", lambda **k: "system prompt de teste")
    monkeypatch.setattr("core.mood.register", lambda message: (0, "neutra"))
    monkeypatch.setattr("core.memory.sync_vault", lambda: 0)
    monkeypatch.setattr("core.memory.query_memory", lambda message, k=None: [])
    monkeypatch.setattr(settings, "NOTES_DIR", tmp_path)
    monkeypatch.setattr(settings, "JOURNAL_ENABLED", False)
    api_mod._session = None
    yield
    api_mod._session = None


def test_chat_endpoint_devolve_resposta(monkeypatch):
    client = TestClient(api_mod.app)

    resp = client.post("/chat", json={"message": "oi, tudo bem?"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "resposta da api"
    assert body["model"] == "local"


def test_lock_serializa_chamadas_concorrentes(monkeypatch):
    """Duas chamadas concorrentes a /chat não podem se intercalar — uma
    espera a outra terminar antes de começar a processar."""
    ordem: list[str] = []

    def _fake_send(self, message):
        ordem.append(f"inicio:{message}")
        time.sleep(0.05)
        ordem.append(f"fim:{message}")
        return "resposta"

    monkeypatch.setattr(chat_mod.ChatSession, "send", _fake_send)

    async def _cenario():
        transport = httpx.ASGITransport(app=api_mod.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await asyncio.gather(
                client.post("/chat", json={"message": "A"}),
                client.post("/chat", json={"message": "B"}),
            )

    asyncio.run(_cenario())

    # Serializado: a 2ª só começa depois que a 1ª termina (em qualquer ordem).
    assert ordem in (
        ["inicio:A", "fim:A", "inicio:B", "fim:B"],
        ["inicio:B", "fim:B", "inicio:A", "fim:A"],
    )


def test_ws_chat_envia_tokens_e_termina_com_done():
    client = TestClient(api_mod.app)

    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"message": "oi, tudo bem?"})

        eventos = []
        while True:
            evento = ws.receive_json()
            eventos.append(evento)
            if evento["type"] == "done":
                break

    tipos = [e["type"] for e in eventos]
    assert tipos[-1] == "done"
    assert tipos.count("token") >= 1
    texto = "".join(e["text"] for e in eventos if e["type"] == "token")
    assert texto == "resposta da api"
    assert eventos[-1]["model"] == "local"


def test_ws_chat_erro_no_meio_nao_derruba_a_conexao(monkeypatch):
    """Um erro num turno vira {"type": "error"} (sem "done" depois) — a
    conexão continua aberta para a próxima mensagem."""

    def _stream_com_erro(self, message):
        if message == "explode":
            raise RuntimeError("boom")
        yield "ok"

    monkeypatch.setattr(chat_mod.ChatSession, "stream", _stream_com_erro)
    client = TestClient(api_mod.app)

    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"message": "explode"})
        erro = ws.receive_json()
        assert erro == {"type": "error", "detail": "boom"}

        # a conexão sobrevive: a próxima mensagem funciona normalmente.
        ws.send_json({"message": "oi"})
        tok = ws.receive_json()
        assert tok == {"type": "token", "text": "ok"}
        fim = ws.receive_json()
        assert fim["type"] == "done"
