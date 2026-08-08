"""Testes do orquestrador de conversa (core.chat.ChatSession).

O `send()` costura humor → tool → RAG → escolha de modelo. Estes testes cobrem
os três ramos de resposta (tool, modelo local, Claude nuvem) com LLM e tools
**mockados** — sem Ollama, sem rede e sem escrever no vault (CI-safe).
"""

import threading
import time

import pytest

import core.chat as chat_mod
from core import metrics
from core.chat import ChatSession


class FakeLLM:
    """LLM falso: registra as mensagens recebidas. invoke() devolve um
    .content fixo; stream() fatia a mesma resposta em pedaços, simulando
    geração incremental (com AIMessageChunk de verdade, para exercitar o
    merge por + que _stream_impl usa)."""

    def __init__(self, reply: str = "resposta do modelo") -> None:
        self.reply = reply
        self.calls: list = []

    def invoke(self, messages):
        self.calls.append(messages)
        return type("Msg", (), {"content": self.reply})()

    def stream(self, messages):
        self.calls.append(messages)
        from langchain_core.messages import AIMessageChunk

        meio = len(self.reply) // 2 or 1
        yield AIMessageChunk(content=self.reply[:meio])
        yield AIMessageChunk(content=self.reply[meio:], response_metadata={"eval_count": 7})


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


# ── Ramo 2: modelo local (Qwen3) ──
def test_send_conversa_usa_modelo_local(monkeypatch):
    monkeypatch.setattr(chat_mod, "route", lambda message: None)
    # Sem chave/nuvem disponível → fica local.
    monkeypatch.setattr(chat_mod, "cloud_available", lambda: False)
    sess = _session(use_tools=True)

    out = sess.send("oi jade, tudo bem?")

    assert out == "resposta do modelo"
    assert sess.last_model == "local"


def test_send_sem_tools_vai_direto_ao_modelo(monkeypatch):
    monkeypatch.setattr(chat_mod, "cloud_available", lambda: False)
    sess = _session(use_tools=False)

    out = sess.send("qualquer coisa")

    assert out == "resposta do modelo"
    assert sess.last_model == "local"


# ── Ramo 3: modelo nuvem (Claude) ──
def test_send_pergunta_informativa_escala_para_a_nuvem(monkeypatch):
    monkeypatch.setattr(chat_mod, "route", lambda message: None)
    monkeypatch.setattr(chat_mod, "cloud_available", lambda: True)
    monkeypatch.setattr(chat_mod, "choose_route", lambda *a, **k: "cloud")
    sess = _session(use_tools=True)

    out = sess.send("me explique o que é fotossíntese")

    assert out == "resposta do modelo"
    assert sess.last_model == "claude"


# ── RAG decide has_context (fim-a-fim, sem mockar choose_route) ──
def test_send_sem_contexto_do_rag_alcanca_a_nuvem(monkeypatch):
    """Com o RAG filtrando tudo (has_context=False), choose_route() DE VERDADE
    (não mockado) escala para a nuvem numa pergunta informativa. Antes deste
    subprojeto, query_memory() nunca devolvia [], então has_context nunca era
    False e este caminho era impossível de exercitar — nenhuma mudança em
    core/chat.py ou core/model_router.py foi necessária para isto passar."""
    monkeypatch.setattr(chat_mod, "route", lambda message: None)
    monkeypatch.setattr(chat_mod, "cloud_available", lambda: True)
    monkeypatch.setattr("core.memory.sync_vault", lambda: 0)
    monkeypatch.setattr("core.memory.query_memory", lambda message: [])
    sess = _session(use_rag=True, use_tools=True)

    out = sess.send("me explique o que é fotossíntese")

    assert out == "resposta do modelo"
    assert sess.last_model == "claude"


def test_send_com_contexto_do_rag_fica_local_mesmo_informativa(monkeypatch):
    """Regra de privacidade: contexto do RAG sempre trava a rota em local, mesmo
    quando a pergunta parece informativa e a nuvem está disponível."""
    monkeypatch.setattr(chat_mod, "route", lambda message: None)
    monkeypatch.setattr(chat_mod, "cloud_available", lambda: True)
    monkeypatch.setattr("core.memory.sync_vault", lambda: 0)
    monkeypatch.setattr("core.memory.query_memory", lambda message: ["[nota.md]\ntrecho relevante"])
    sess = _session(use_rag=True, use_tools=True)

    out = sess.send("como foi a reunião que você anotou pra mim?")

    assert out == "resposta do modelo"
    assert sess.last_model == "local"


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


def test_detach_limpa_na_hora_e_adia_o_trabalho_pesado(monkeypatch):
    """O botão 'novo chat' não pode esperar LLM/indexação: detach() limpa a
    sessão imediatamente e devolve o trabalho pesado para rodar depois."""
    monkeypatch.setattr(chat_mod, "cloud_available", lambda: False)
    chamou = {"perfil": False}

    def _fake_update(transcript, llm):
        chamou["perfil"] = True

    monkeypatch.setattr("core.profile.update_from_conversation", _fake_update)
    sess = _session(use_tools=False)
    for _ in range(2):
        sess.send("oi")
    assert sess._history

    finish = sess.detach()

    # Limpou já; nada de LLM/perfil ainda.
    assert sess._history == []
    assert sess.last_model is None
    assert chamou["perfil"] is False

    finish()  # só agora (em background, na API) roda o trabalho pesado
    assert chamou["perfil"] is True


# ── Instrumentação (core.metrics) ────────────────────────────
def test_turno_local_registra_etapas_e_rota():
    """A rota do modelo local mede humor, RAG e LLM, e anota route='local'."""
    session = ChatSession(use_tools=False, use_rag=False, use_router=False, use_journal=False)
    with metrics.capture() as turn:
        session.send("oi")
    assert turn.meta["route"] == "local"
    assert {"mood", "llm", "journal", "total"} <= set(turn.steps)


def test_turno_de_tool_registra_rota_e_nome(monkeypatch):
    """Quando uma tool responde, route='tool' e o nome da tool é anotado."""
    tool = FakeTool()
    monkeypatch.setattr(chat_mod, "route", lambda _m: tool)
    session = ChatSession(use_rag=False, use_router=False, use_journal=False)
    with metrics.capture() as turn:
        session.send("abra a calculadora")
    assert turn.meta["route"] == "tool"
    assert turn.meta["tool"] == "fake_tool"
    assert {"tool_route", "tool_run"} <= set(turn.steps)


def test_send_funciona_sem_capture():
    """Fora de um capture(), send() se comporta exatamente como antes."""
    session = ChatSession(use_tools=False, use_rag=False, use_router=False, use_journal=False)
    assert session.send("oi") == "resposta do modelo"


def test_send_poda_historico_alem_do_limite(monkeypatch):
    from core.config import settings

    monkeypatch.setattr(chat_mod, "route", lambda message: None)
    monkeypatch.setattr(chat_mod, "cloud_available", lambda: False)
    monkeypatch.setattr(settings, "HISTORY_MAX_TURNS", 2)
    sess = _session(use_tools=False)

    for i in range(5):
        sess.send(f"mensagem {i}")

    # 5 turnos enviados, só os últimos 2 (4 mensagens) ficam no histórico.
    assert len(sess._history) == 4
    # Confirma que sobreviveram os turnos mais RECENTES, não os mais antigos
    # (um teste só de tamanho passaria igual com a poda invertida). _record()
    # empilha HumanMessage seguido de AIMessage por turno, então a mensagem
    # humana mais antiga que sobrou é _history[0].
    assert sess._history[0].content == "mensagem 3"
    assert sess._history[2].content == "mensagem 4"


def test_sync_vault_roda_em_background_e_e_esperado_na_1a_busca(monkeypatch):
    """A thread nasce no __init__ (não bloqueia a criação da sessão) e
    _retrieve_context() só prossegue depois que ela termina."""
    sync_terminou = threading.Event()
    chamadas = []

    def _fake_sync_vault():
        chamadas.append("chamou")
        time.sleep(0.05)
        sync_terminou.set()
        return 0

    monkeypatch.setattr("core.memory.sync_vault", _fake_sync_vault)
    monkeypatch.setattr("core.memory.query_memory", lambda message: [])

    sess = _session(use_rag=True, use_tools=False)
    # __init__ não bloqueou esperando o sync (senão sync_terminou já estaria setado).
    assert not sync_terminou.is_set()

    context = sess._retrieve_context("oi")

    assert sync_terminou.is_set()
    assert context == ""
    assert len(chamadas) == 1

    # 2ª busca não dispara sync_vault de novo.
    sess._retrieve_context("de novo")
    assert len(chamadas) == 1


def test_sync_vault_e_esperado_tambem_no_ramo_de_tool(monkeypatch):
    """O ramo de TOOL também espera a thread de sync terminar antes de retornar,
    fechando a corrida de escrita no database/index_state.json quando múltiplas
    sessões rodam em sequence (ex.: bench/runner.py com casos roteados a tool)."""
    sync_terminou = threading.Event()
    chamadas = []

    def _fake_sync_vault():
        chamadas.append("chamou")
        time.sleep(0.05)
        sync_terminou.set()
        return 0

    tool = FakeTool()
    monkeypatch.setattr(chat_mod, "route", lambda message: tool)
    monkeypatch.setattr("core.memory.sync_vault", _fake_sync_vault)

    sess = _session(use_rag=True, use_tools=True)
    # __init__ não bloqueou esperando o sync.
    assert not sync_terminou.is_set()

    out = sess.send("execute tool")

    # send() retornou, e sync_terminou está setado (tool esperou a sync terminar).
    assert sync_terminou.is_set()
    assert out == "tool executou"
    assert len(chamadas) == 1
    assert tool.ran_with == "execute tool"


def test_stream_gera_multiplos_chunks_que_concatenam_igual_ao_send(monkeypatch):
    """stream() devolve a mesma resposta que send(), só que em pedaços."""
    monkeypatch.setattr(chat_mod, "route", lambda message: None)
    monkeypatch.setattr(chat_mod, "cloud_available", lambda: False)
    sess = _session(use_tools=False)

    chunks = list(sess.stream("oi jade"))

    assert len(chunks) > 1
    assert "".join(chunks) == "resposta do modelo"
    assert sess.last_model == "local"


def test_stream_tool_devolve_um_unico_pedaco(monkeypatch):
    tool = FakeTool()
    monkeypatch.setattr(chat_mod, "route", lambda message: tool)
    sess = _session()

    chunks = list(sess.stream("abra a calculadora"))

    assert chunks == ["tool executou"]
    assert sess.last_model == "tool"


def test_stream_grava_no_historico_como_send(monkeypatch):
    """stream() tem os mesmos efeitos colaterais de send() (grava o turno)."""
    monkeypatch.setattr(chat_mod, "route", lambda message: None)
    monkeypatch.setattr(chat_mod, "cloud_available", lambda: False)
    sess = _session(use_tools=False)

    list(sess.stream("oi"))

    assert len(sess._history) == 2
