"""Testes dos endpoints de chat da API (/chat, /voice/chat, /ws/chat) — LLM,
tools, RAG e journal mockados (sem Ollama, sem rede, sem escrever no vault)."""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

import httpx
import pytest
from fastapi import WebSocketDisconnect
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


def test_ws_chat_rejeita_origin_nao_permitida():
    """Handshakes de WebSocket não são cobertos pela same-origin policy do
    browser — o servidor precisa validar o Origin ele mesmo, senão uma
    página http:// maliciosa aberta no mesmo browser poderia abrir este
    WebSocket e ler as respostas da Jade."""
    client = TestClient(api_mod.app)

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/chat", headers={"origin": "http://evil.example"}) as ws:
            ws.receive_json()


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


def test_ws_chat_agenda_title_task_apos_turno_com_sucesso(monkeypatch):
    """A Task 6 migrou o chat de texto inteiro pro WebSocket — sem agendar
    title_task() aqui, o título da conversa só seria refinado no /reset
    ("novo chat"), nunca durante a conversa em si."""
    concluiu = threading.Event()

    def _fake_title_task(self, min_turns: int = 2):
        def _run() -> None:
            concluiu.set()

        return _run

    monkeypatch.setattr(chat_mod.ChatSession, "title_task", _fake_title_task)
    client = TestClient(api_mod.app)

    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"message": "oi, tudo bem?"})
        while True:
            evento = ws.receive_json()
            if evento["type"] == "done":
                break

    assert concluiu.wait(timeout=2)


def test_stream_to_ws_drena_fila_ate_o_fim_mesmo_com_falha_no_envio():
    """Se o envio pro WebSocket falha no meio (cliente desconectou),
    _stream_to_ws precisa continuar drenando a fila até a sentinela chegar —
    só assim garante que a thread produtora já terminou de mutar `session`
    antes de devolver o controle pro chamador soltar o _session_lock."""
    produtor_terminou = threading.Event()

    class FakeSession:
        def stream(self, message):
            try:
                yield "a"
                yield "b"
                yield "c"
            finally:
                produtor_terminou.set()

    class FakeWebSocket:
        def __init__(self):
            self.chamadas = 0

        async def send_json(self, payload):
            self.chamadas += 1
            if self.chamadas == 1:
                raise RuntimeError("cliente desconectou")

    async def _cenario():
        return await api_mod._stream_to_ws(FakeWebSocket(), FakeSession(), "oi")

    ok = asyncio.run(_cenario())

    # No instante em que _stream_to_ws retorna, a thread produtora já deve
    # ter terminado — senão o lock seria liberado com ela ainda mutando
    # `session` em segundo plano (a corrida que este teste existe pra evitar).
    assert produtor_terminou.is_set()
    assert ok is False


# ── Integração do wake-word com o frontend (broadcast em /ws/chat) ──
def test_ws_chat_registra_e_remove_cliente_de_ws_clients():
    """_ws_clients é a lista que _broadcast usa pra empurrar os turnos do
    wake-word pra toda aba aberta — precisa ganhar o cliente ao conectar e
    perdê-lo ao desconectar, senão vaza memória ou envia pra socket morto."""
    client = TestClient(api_mod.app)

    assert len(api_mod._ws_clients) == 0
    with client.websocket_connect("/ws/chat"):
        assert len(api_mod._ws_clients) == 1
    assert len(api_mod._ws_clients) == 0


def test_broadcast_manda_para_todo_cliente_conectado():
    class FakeWebSocket:
        def __init__(self, falha=False):
            self.falha = falha
            self.recebidos = []

        async def send_json(self, payload):
            if self.falha:
                raise RuntimeError("cliente desconectou")
            self.recebidos.append(payload)

    ok = FakeWebSocket()
    quebrado = FakeWebSocket(falha=True)
    api_mod._ws_clients.add(ok)
    api_mod._ws_clients.add(quebrado)
    try:
        asyncio.run(api_mod._broadcast({"type": "wake_listening"}))
    finally:
        api_mod._ws_clients.discard(ok)
        api_mod._ws_clients.discard(quebrado)

    assert ok.recebidos == [{"type": "wake_listening"}]


def test_wakeword_handle_command_emite_wake_turn_com_a_resposta(monkeypatch):
    recebidos = []

    class FakeWebSocket:
        async def send_json(self, payload):
            recebidos.append(payload)

    monkeypatch.setattr("interfaces.voice_service.synthesize_reply", lambda text: Path("x.mp3"))
    ws = FakeWebSocket()
    api_mod._ws_clients.add(ws)
    try:
        # Mensagem neutra de propósito: algo como "toca X" seria capturado
        # pelo roteamento determinístico de tools (spotify_tool) antes de
        # chegar no FakeLLM mockado pela fixture, e o teste é sobre o
        # encaminhamento do wake-word, não sobre roteamento de tool.
        asyncio.run(api_mod._wakeword_handle_command("oi, tudo bem?"))
    finally:
        api_mod._ws_clients.discard(ws)

    assert len(recebidos) == 1
    evento = recebidos[0]
    assert evento["type"] == "wake_turn"
    assert evento["transcription"] == "oi, tudo bem?"
    assert evento["reply"] == "resposta da api"
    assert evento["audio_url"] == "/voice/audio/x.mp3"
    assert evento["model"] == "local"


def test_wakeword_handle_command_emite_wake_error_quando_send_falha(monkeypatch):
    recebidos = []

    class FakeWebSocket:
        async def send_json(self, payload):
            recebidos.append(payload)

    def _explode(self, message):
        raise RuntimeError("boom")

    monkeypatch.setattr(chat_mod.ChatSession, "send", _explode)
    ws = FakeWebSocket()
    api_mod._ws_clients.add(ws)
    try:
        asyncio.run(api_mod._wakeword_handle_command("toca sweet dreams"))
    finally:
        api_mod._ws_clients.discard(ws)

    assert recebidos == [{"type": "wake_error", "detail": "boom"}]


def test_startup_wakeword_nao_sobe_thread_quando_desligado(monkeypatch):
    monkeypatch.setattr(settings, "WAKEWORD_ENABLED", False)
    threads_antes = threading.active_count()

    asyncio.run(api_mod._startup_wakeword())

    assert threading.active_count() == threads_antes


def test_startup_wakeword_sobe_thread_daemon_quando_ligado(monkeypatch):
    monkeypatch.setattr(settings, "WAKEWORD_ENABLED", True)
    threads_criadas = []
    thread_original = threading.Thread

    def _thread_fake(*args, **kwargs):
        t = thread_original(*args, **kwargs)
        threads_criadas.append(t)
        return t

    # Substitui o alvo por um no-op: o teste garante que a thread é
    # agendada certinha (daemon, com o loop atual), não que o listener de
    # verdade (que abriria microfone) rode até o fim.
    monkeypatch.setattr(threading, "Thread", _thread_fake)
    monkeypatch.setattr(api_mod, "_run_wakeword_listener", lambda loop: None)

    asyncio.run(api_mod._startup_wakeword())

    assert len(threads_criadas) == 1
    assert threads_criadas[0].daemon is True
