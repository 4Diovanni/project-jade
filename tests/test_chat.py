"""Testes do orquestrador de conversa (core.chat.ChatSession).

O `send()` costura humor → tool → RAG → escolha de modelo. Estes testes cobrem
os três ramos de resposta (tool, llama3 local, Claude nuvem) com LLM e tools
**mockados** — sem Ollama, sem rede e sem escrever no vault (CI-safe).
"""

import pytest

import core.chat as chat_mod
from core.chat import ChatSession


class FakeLLM:
    """LLM falso: registra as mensagens recebidas e devolve um .content fixo."""

    def __init__(self, reply: str = "resposta do modelo") -> None:
        self.reply = reply
        self.calls: list = []

    def invoke(self, messages):
        self.calls.append(messages)
        return type("Msg", (), {"content": self.reply})()


class FakeTool:
    name = "fake_tool"

    def __init__(self, raise_exc: bool = False) -> None:
        self.raise_exc = raise_exc
        self.ran_with: str | None = None

    def run(self, message: str) -> str:
        self.ran_with = message
        if self.raise_exc:
            raise RuntimeError("boom")
        return "tool executou"


@pytest.fixture(autouse=True)
def _isola_efeitos(monkeypatch):
    """Neutraliza efeitos colaterais de send() que tocariam o vault/Ollama."""
    # __init__ e _get_cloud_llm chamam get_llm() → não queremos Ollama/Claude reais.
    monkeypatch.setattr(chat_mod, "get_llm", lambda *a, **k: FakeLLM())
    # mood.register e build_system_prompt escrevem notas no vault — neutraliza.
    monkeypatch.setattr("core.mood.register", lambda message: (0, "neutra"))
    monkeypatch.setattr(chat_mod, "build_system_prompt", lambda **k: "system prompt de teste")


def _session(**kwargs) -> ChatSession:
    kwargs.setdefault("use_rag", False)
    kwargs.setdefault("use_journal", False)
    return ChatSession(**kwargs)


# ── Ramo 1: tool ──
def test_send_roteia_para_tool(monkeypatch):
    tool = FakeTool()
    monkeypatch.setattr(chat_mod, "route", lambda message: tool)
    sess = _session()

    out = sess.send("abra a calculadora")

    assert out == "tool executou"
    assert sess.last_model == "tool"
    assert tool.ran_with == "abra a calculadora"


def test_send_tool_que_falha_nao_derruba_a_sessao(monkeypatch):
    monkeypatch.setattr(chat_mod, "route", lambda message: FakeTool(raise_exc=True))
    sess = _session()

    out = sess.send("abra a calculadora")

    assert "Não consegui executar a ação" in out
    assert sess.last_model == "tool"


# ── Ramo 2: modelo local (llama3) ──
def test_send_conversa_usa_modelo_local(monkeypatch):
    monkeypatch.setattr(chat_mod, "route", lambda message: None)
    # Sem chave/nuvem disponível → fica local.
    monkeypatch.setattr(chat_mod, "cloud_available", lambda: False)
    sess = _session(use_tools=True)

    out = sess.send("oi jade, tudo bem?")

    assert out == "resposta do modelo"
    assert sess.last_model == "llama3"


def test_send_sem_tools_vai_direto_ao_modelo(monkeypatch):
    monkeypatch.setattr(chat_mod, "cloud_available", lambda: False)
    sess = _session(use_tools=False)

    out = sess.send("qualquer coisa")

    assert out == "resposta do modelo"
    assert sess.last_model == "llama3"


# ── Ramo 3: modelo nuvem (Claude) ──
def test_send_pergunta_informativa_escala_para_a_nuvem(monkeypatch):
    monkeypatch.setattr(chat_mod, "route", lambda message: None)
    monkeypatch.setattr(chat_mod, "cloud_available", lambda: True)
    monkeypatch.setattr(chat_mod, "choose_route", lambda *a, **k: "cloud")
    sess = _session(use_tools=True)

    out = sess.send("me explique o que é fotossíntese")

    assert out == "resposta do modelo"
    assert sess.last_model == "claude"


# ── Memória / histórico ──
def test_send_registra_o_turno_no_historico(monkeypatch):
    monkeypatch.setattr(chat_mod, "route", lambda message: None)
    monkeypatch.setattr(chat_mod, "cloud_available", lambda: False)
    sess = _session(use_tools=False)

    sess.send("primeira")
    sess.send("segunda")

    # 2 turnos → 2 HumanMessage + 2 AIMessage.
    assert len(sess._history) == 4


def test_reset_limpa_o_historico(monkeypatch):
    monkeypatch.setattr(chat_mod, "cloud_available", lambda: False)
    sess = _session(use_tools=False)
    sess.send("oi")
    assert sess._history

    sess.reset()

    assert sess._history == []
    assert sess.last_model is None
