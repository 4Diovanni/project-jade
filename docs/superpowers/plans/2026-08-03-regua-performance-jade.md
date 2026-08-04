# A Régua — Instrumentação e Benchmark da Jade — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir instrumentação de desempenho por etapa e um benchmark determinístico que produza um relatório versionado respondendo, com número, "onde está a Jade hoje".

**Architecture:** Um módulo `core/metrics.py` de custo zero quando desligado (context managers ancorados num `ContextVar`) instrumenta oito etapas de `ChatSession.send()`. Uma pasta `bench/` independente carrega casos declarativos em YAML, executa cada um numa sessão isolada, avalia as decisões da Jade contra o esperado e escreve um relatório Markdown com delta contra a execução anterior. A dependência aponta numa direção só: `bench/` importa `core/`, nunca o contrário.

**Tech Stack:** Python 3.11+, `contextvars`, `dataclasses`, PyYAML (nova dependência de dev), pytest.

**Spec:** `docs/superpowers/specs/2026-08-03-regua-performance-jade-design.md`

## Global Constraints

- **Identificadores de código em inglês; comentários e docstrings em PT-BR.** Convenção do projeto (`CLAUDE.md`).
- **Configuração sempre via `core.config.settings`** — nunca `os.getenv` espalhado.
- **Swallow de exceção usa `contextlib.suppress`** — o Bandit rejeita `try/except/pass`.
- **O contrato de `ChatSession.send()` não muda:** mesma assinatura, mesmo retorno, mesmo comportamento. Se algum teste existente em `tests/test_chat.py` ou `tests/test_memory.py` precisar mudar, o desenho está errado — pare e reavalie.
- **A instrumentação é no-op fora de `capture()`.** Nenhum `perf_counter()` deve ser chamado quando não há turno ativo.
- **Nomes de rota:** as métricas usam `route` com valores `tool` | `local` | `cloud`. O atributo `ChatSession.last_model` continua usando `tool` | `local` | `claude` (o frontend depende dele). O runner do bench lê **sempre** `turn.meta["route"]`, nunca `last_model`.
- **Nome da tool de sistema:** `system_control` (de `tools/system_tool.py:112`).
- **O bench não roda no CI.** Exige Ollama e GPU. Os testes de `core/metrics.py` e de `bench/` rodam no CI **sem LLM**.
- **Antes de cada commit:** `ruff check . && ruff format .` e `pytest`.
- **Workflow de git:** todo o trabalho acontece numa branch `feat/regua-performance`. Nunca commitar na `main`.

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `core/metrics.py` | **Criar.** Único lugar que conhece medição: `Turn`, `capture()`, `timed()`, `note()`. |
| `core/chat.py` | **Modificar.** Seis pontos de marcação + metadados de rota, tool, humor e uso de tokens. |
| `core/memory.py` | **Modificar.** Dois pontos de marcação (`rag_embed`, `rag_search`) + metadados de chunks e fontes. |
| `bench/cases.py` | **Criar.** Carrega e valida os casos YAML. Não executa nada. |
| `bench/aggregate.py` | **Criar.** Avalia um caso contra um turno e agrega os resultados em métricas. Função pura. |
| `bench/report.py` | **Criar.** Renderiza o Markdown e calcula o delta contra a execução anterior. |
| `bench/runner.py` | **Criar.** Orquestra: health check, isolamento, laço de execução, CLI. |
| `bench/cases/*.yaml` | **Criar.** Os ~25 casos, um arquivo por categoria. |
| `main.py` | **Modificar.** Comando `bench`. |
| `requirements-dev.txt` | **Modificar.** `pyyaml>=6.0`. |
| `tests/test_metrics.py` | **Criar.** |
| `tests/test_bench_cases.py` | **Criar.** |
| `tests/test_bench_aggregate.py` | **Criar.** |

---

### Task 1: Módulo de métricas

**Files:**
- Create: `core/metrics.py`
- Test: `tests/test_metrics.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `Turn` — dataclass com `steps: dict[str, float]` e `meta: dict[str, object]`.
  - `capture() -> ContextManager[Turn]` — abre um turno; grava `steps["total"]` ao fechar.
  - `timed(step: str) -> ContextManager[None]` — acumula tempo na etapa; no-op sem turno ativo.
  - `note(**fields) -> None` — anexa metadados ao turno; no-op sem turno ativo.

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/test_metrics.py`:

```python
"""Testes da instrumentação de desempenho (core.metrics).

Cobrem as três garantias que fazem o módulo ser seguro em produção:
acumulação correta, isolamento entre contextos e custo zero fora de `capture()`.
"""

import contextvars

import pytest

from core import metrics


def test_capture_grava_o_total():
    with metrics.capture() as turn:
        pass
    assert "total" in turn.steps
    assert turn.steps["total"] >= 0.0


def test_timed_registra_a_etapa():
    with metrics.capture() as turn:
        with metrics.timed("llm"):
            pass
    assert "llm" in turn.steps


def test_timed_acumula_chamadas_repetidas():
    with metrics.capture() as turn:
        with metrics.timed("rag_embed"):
            pass
        primeiro = turn.steps["rag_embed"]
        with metrics.timed("rag_embed"):
            pass
    assert turn.steps["rag_embed"] >= primeiro


def test_timed_contabiliza_mesmo_com_excecao():
    with metrics.capture() as turn:
        with pytest.raises(RuntimeError):
            with metrics.timed("tool_run"):
                raise RuntimeError("boom")
    assert "tool_run" in turn.steps


def test_etapas_aninhadas_sao_independentes():
    with metrics.capture() as turn:
        with metrics.timed("rag_query"):
            with metrics.timed("rag_embed"):
                pass
    assert {"rag_query", "rag_embed", "total"} <= set(turn.steps)


def test_note_anexa_metadados():
    with metrics.capture() as turn:
        metrics.note(route="local", chunks=6)
        metrics.note(sources=["CLAUDE.md"])
    assert turn.meta == {"route": "local", "chunks": 6, "sources": ["CLAUDE.md"]}


def test_timed_e_noop_fora_de_capture():
    """Em produção não há turno ativo: nada pode ser gravado nem explodir."""
    with metrics.timed("llm"):
        pass
    metrics.note(route="local")  # não levanta


def test_turnos_nao_vazam_entre_contextos():
    """Duas requisições concorrentes não podem compartilhar o mesmo turno."""
    coletadas: list[set[str]] = []

    def trabalho(etapa: str) -> None:
        with metrics.capture() as turn:
            with metrics.timed(etapa):
                pass
            coletadas.append(set(turn.steps))

    contextvars.copy_context().run(trabalho, "a")
    contextvars.copy_context().run(trabalho, "b")

    assert coletadas == [{"a", "total"}, {"b", "total"}]


def test_capture_restaura_o_estado_anterior():
    with metrics.capture():
        pass
    # Fora do bloco, timed volta a ser no-op (nenhum turno pendurado).
    with metrics.timed("llm"):
        pass
```

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `pytest tests/test_metrics.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'core.metrics'`

- [ ] **Step 3: Implementar o módulo**

Criar `core/metrics.py`:

```python
"""Instrumentação de desempenho da Jade — medição por etapa, custo zero quando desligada.

A medição só acontece dentro de um `capture()`. Fora dele, `timed()` e `note()`
são **no-op**: o custo em produção é um `ContextVar.get()` que devolve `None` —
nada é cronometrado, nada é alocado, nada é gravado.

O turno ativo vive num `ContextVar`, não numa global: é o que impede um turno de
vazar para outro quando a API serve requisições concorrentes em threads distintas.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from contextvars import ContextVar
from dataclasses import dataclass, field
from time import perf_counter


@dataclass
class Turn:
    """Medições de um turno: tempo por etapa e metadados da decisão tomada."""

    #: segundos acumulados por etapa (inclui "total", gravado por `capture`)
    steps: dict[str, float] = field(default_factory=dict)
    #: rota, tool, chunks, fontes, contadores de token...
    meta: dict[str, object] = field(default_factory=dict)


_current: ContextVar[Turn | None] = ContextVar("jade_metrics_turn", default=None)


@contextlib.contextmanager
def capture() -> Iterator[Turn]:
    """Abre um turno de medição e o devolve. Grava `steps['total']` ao fechar."""
    turn = Turn()
    token = _current.set(turn)
    started = perf_counter()
    try:
        yield turn
    finally:
        turn.steps["total"] = perf_counter() - started
        _current.reset(token)


@contextlib.contextmanager
def timed(step: str) -> Iterator[None]:
    """Acumula o tempo do bloco na etapa `step`. No-op se não há turno ativo.

    Etapas aninhadas somam de forma independente — o relatório trata as etapas
    como categorias, não como uma árvore.
    """
    turn = _current.get()
    if turn is None:
        yield
        return
    started = perf_counter()
    try:
        yield
    finally:
        turn.steps[step] = turn.steps.get(step, 0.0) + (perf_counter() - started)


def note(**fields: object) -> None:
    """Anexa metadados ao turno ativo. No-op se não há turno ativo."""
    turn = _current.get()
    if turn is not None:
        turn.meta.update(fields)
```

- [ ] **Step 4: Rodar os testes para confirmar que passam**

Run: `pytest tests/test_metrics.py -v`
Expected: PASS — 9 testes.

- [ ] **Step 5: Rodar lint e a suíte inteira**

Run: `ruff check . && ruff format . && pytest`
Expected: sem erros de lint; toda a suíte verde.

- [ ] **Step 6: Commit**

```bash
git add core/metrics.py tests/test_metrics.py
git commit -m "feat(metrics): instrumentacao por etapa com custo zero fora do bench"
```

---

### Task 2: Instrumentar o caminho quente

**Files:**
- Modify: `core/chat.py` (imports, `send()`, `_pick_llm()`, `_retrieve_context()`)
- Modify: `core/memory.py` (`query_memory()`)
- Test: `tests/test_chat.py` (adicionar testes; **não alterar os existentes**)

**Interfaces:**
- Consumes: `core.metrics.capture`, `core.metrics.timed`, `core.metrics.note` (Task 1).
- Produces: um turno capturado ao redor de `ChatSession.send()` contém —
  - `steps`: `mood`, `tool_route`, `tool_run`, `rag_sync`, `rag_embed`, `rag_search`, `llm`, `journal`, `total` (só as etapas que de fato rodaram).
  - `meta["route"]`: `"tool"` | `"local"` | `"cloud"`.
  - `meta["tool"]`: `str` — nome da tool, só na rota `tool`.
  - `meta["mood_level"]`: `int`.
  - `meta["chunks"]`: `int` — trechos recuperados do RAG.
  - `meta["sources"]`: `list[str]` — arquivos de origem, sem repetição, na ordem de relevância.
  - `meta["eval_count"]`, `meta["eval_duration"]`, `meta["prompt_eval_count"]`: `int` — só quando o provider devolve (Ollama).

- [ ] **Step 1: Escrever os testes que falham**

Primeiro, acrescentar `from core import metrics` ao **bloco de imports do topo** de
`tests/test_chat.py` (o ruff roda com a regra `I` do isort — import no meio do
arquivo seria rejeitado).

Depois, acrescentar ao final de `tests/test_chat.py`:

```python
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
```

Criar em `tests/test_memory.py` (acrescentar ao final):

```python
def test_query_memory_registra_etapas_e_fontes(monkeypatch):
    """query_memory mede embed e busca separadamente e anota as fontes."""
    from core import metrics

    class FakeCollection:
        def count(self):
            return 3

        def query(self, **kwargs):
            return {
                "documents": [["trecho A", "trecho B"]],
                "metadatas": [[{"source": "CLAUDE.md"}, {"source": "CLAUDE.md"}]],
            }

    monkeypatch.setattr(memory, "_get_collection", lambda: FakeCollection())
    monkeypatch.setattr(
        memory, "_get_embedder", lambda: type("E", (), {"embed_query": lambda self, q: [0.1]})()
    )

    with metrics.capture() as turn:
        out = memory.query_memory("qual o modelo local?")

    assert len(out) == 2
    assert {"rag_embed", "rag_search"} <= set(turn.steps)
    assert turn.meta["chunks"] == 2
    assert turn.meta["sources"] == ["CLAUDE.md"]  # sem repetição
```

`tests/test_memory.py` já importa `from core import memory` no topo — nenhum import novo é necessário.

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `pytest tests/test_chat.py tests/test_memory.py -v`
Expected: FAIL — `KeyError: 'route'` nos testes novos; os testes antigos continuam passando.

- [ ] **Step 3: Instrumentar `core/memory.py`**

Em `core/memory.py`, acrescentar ao bloco de imports do topo:

```python
from core.metrics import note, timed
```

Substituir o corpo de `query_memory` (`core/memory.py:144-162`) por:

```python
def query_memory(question: str, k: int | None = None) -> list[str]:
    """Busca semântica no ChromaDB. Retorna os trechos mais relevantes
    (formatados com a nota de origem). Lista vazia se nada foi indexado."""
    k = k or settings.RAG_TOP_K
    collection = _get_collection()
    if collection.count() == 0:
        note(chunks=0, sources=[])
        return []

    with timed("rag_embed"):
        q_emb = _get_embedder().embed_query(question)
    with timed("rag_search"):
        res = collection.query(query_embeddings=[q_emb], n_results=k)

    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]

    out: list[str] = []
    sources: list[str] = []
    for doc, meta in zip(docs, metas, strict=False):
        source = (meta or {}).get("source", "?")
        if source not in sources:
            sources.append(source)
        out.append(f"[{source}]\n{doc}")
    # As fontes vão para as métricas aqui, onde ainda são estruturadas — o bench
    # nunca deve reparsear as strings "[source]\n…" devolvidas.
    note(chunks=len(out), sources=sources)
    return out
```

- [ ] **Step 4: Instrumentar `core/chat.py`**

Em `core/chat.py`, acrescentar ao bloco de imports:

```python
from core.metrics import note, timed
```

Acrescentar esta função auxiliar logo abaixo de `_CONTEXT_TEMPLATE` (`core/chat.py:30`):

```python
def _note_llm_usage(response) -> None:
    """Anota os contadores de token do provider, quando existirem.

    O Ollama devolve `eval_count`/`eval_duration` (tok/s real) e
    `prompt_eval_count` (tamanho do prompt em tokens de verdade). Providers que
    não devolvem esses campos simplesmente não são anotados.
    """
    meta = getattr(response, "response_metadata", None) or {}
    usage = {
        key: meta[key]
        for key in ("eval_count", "eval_duration", "prompt_eval_count")
        if key in meta
    }
    if usage:
        note(**usage)
```

Em `_pick_llm` (`core/chat.py:81-91`), anotar a rota. Substituir por:

```python
    def _pick_llm(self, message: str, has_context: bool):
        can_cloud = self._use_router and cloud_available()
        r = choose_route(message, has_context=has_context, cloud_available=can_cloud)
        if r == "cloud":
            llm = self._try_cloud_llm()
            if llm is not None:
                self.last_model = "claude"
                note(route="cloud")  # métricas usam "cloud"; last_model, "claude"
                return llm
        self.last_model = "local"
        note(route="local")
        # Com contexto do vault no prompt, vale mais fidelidade que criatividade.
        return self._get_grounded_llm() if has_context else self._local_llm
```

Em `_retrieve_context` (`core/chat.py:118-128`), medir o sync:

```python
    def _retrieve_context(self, message: str) -> str:
        if not self._use_rag:
            return ""
        with timed("rag_sync"):
            self._ensure_synced()
        try:
            from core.memory import query_memory

            chunks = query_memory(message)
        except Exception:
            return ""
        return "\n\n".join(chunks)
```

Em `send()` (`core/chat.py:130-164`), substituir o corpo inteiro por:

```python
    def send(self, message: str) -> str:
        """Processa uma mensagem: humor → tool → senão conversa (modelo + RAG)."""
        # 1) O tom do usuário ajusta o humor da Jade (persistido).
        mood_level = 0
        with timed("mood"), contextlib.suppress(Exception):
            from core.mood import register

            mood_level, _label = register(message)
        note(mood_level=mood_level)

        # 2) Roteamento para tools (as "mãos" da Jade).
        if self._use_tools:
            with timed("tool_route"):
                tool = route(message)
            if tool is not None:
                note(route="tool", tool=getattr(tool, "name", "?"))
                try:
                    with timed("tool_run"):
                        text = tool.run(message)
                except Exception as e:
                    text = f"Não consegui executar a ação: {e}"
                self.last_model = "tool"
                with timed("journal"):
                    self._record(message, text)
                return text

        # 3) Conversa. Contexto do RAG é injetado só na chamada ao LLM.
        context = self._retrieve_context(message)
        llm = self._pick_llm(message, has_context=bool(context))

        user_turn = HumanMessage(content=message)
        if context:
            augmented = _CONTEXT_TEMPLATE.format(context=context, question=message)
            user_turn = HumanMessage(content=augmented)

        messages = [self._system_message(mood_level), *self._history, user_turn]
        with timed("llm"):
            response = llm.invoke(messages)
        _note_llm_usage(response)
        text = response.content if hasattr(response, "content") else str(response)
        with timed("journal"):
            self._record(message, text)
        return text
```

- [ ] **Step 5: Rodar os testes para confirmar que passam**

Run: `pytest tests/test_chat.py tests/test_memory.py -v`
Expected: PASS — inclusive todos os testes que já existiam, **sem nenhuma alteração neles**.

- [ ] **Step 6: Rodar lint e a suíte inteira**

Run: `ruff check . && ruff format . && pytest`
Expected: tudo verde. Se algum teste pré-existente falhar, o contrato de `send()` foi quebrado — reverta e reavalie antes de seguir.

- [ ] **Step 7: Commit**

```bash
git add core/chat.py core/memory.py tests/test_chat.py tests/test_memory.py
git commit -m "feat(metrics): mede as oito etapas do turno e anota rota, fontes e tokens"
```

---

### Task 3: Casos declarativos e carregador

**Files:**
- Create: `bench/__init__.py`, `bench/cases.py`
- Create: `bench/cases/tools.yaml`, `bench/cases/conhecimento.yaml`, `bench/cases/memoria.yaml`, `bench/cases/papo.yaml`, `bench/cases/humor.yaml`
- Modify: `requirements-dev.txt`
- Test: `tests/test_bench_cases.py`

**Interfaces:**
- Consumes: nada de tasks anteriores.
- Produces:
  - `Case` — dataclass congelada com `id: str`, `message: str`, `category: str`, `expect: dict`.
  - `CaseError(Exception)` — erro de validação, com mensagem legível.
  - `load_cases(path: str | Path) -> list[Case]` — aceita um arquivo `.yaml` ou um diretório; a `category` vem do nome do arquivo (sem extensão).

- [ ] **Step 1: Adicionar a dependência**

Acrescentar ao final de `requirements-dev.txt`:

```
pyyaml>=6.0          # casos declarativos do benchmark (bench/cases/*.yaml)
```

Instalar: `pip install "pyyaml>=6.0"`

- [ ] **Step 2: Escrever os testes que falham**

Criar `tests/test_bench_cases.py`:

```python
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
```

- [ ] **Step 3: Rodar os testes para confirmar que falham**

Run: `pytest tests/test_bench_cases.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'bench'`

- [ ] **Step 4: Implementar o carregador**

Criar `bench/__init__.py` vazio (arquivo em branco).

Criar `bench/cases.py`:

```python
"""Casos declarativos do benchmark: carga e validação.

Um caso descreve uma mensagem e o que se espera das **decisões** da Jade — a
rota, a tool acionada, as fontes recuperadas. Nunca o texto da resposta: isso
depende da geração do LLM e não seria reprodutível.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


class CaseError(Exception):
    """Caso mal formado — mensagem legível para quem escreveu o YAML."""


@dataclass(frozen=True)
class Case:
    id: str
    message: str
    category: str
    expect: dict


_VALID_KEYS = {"route", "tool", "sources_include", "context", "mood_delta"}
_VALID_ROUTE = {"tool", "local", "cloud"}
_VALID_CONTEXT = {"none", "any"}
_VALID_MOOD = {"negative", "positive", "neutral"}


def _validate_expect(case_id: str, expect: dict) -> None:
    desconhecidas = set(expect) - _VALID_KEYS
    if desconhecidas:
        raise CaseError(
            f"caso {case_id!r}: chave(s) de expect desconhecida(s): "
            f"{', '.join(sorted(desconhecidas))}. Válidas: {', '.join(sorted(_VALID_KEYS))}"
        )
    if "route" in expect and expect["route"] not in _VALID_ROUTE:
        raise CaseError(
            f"caso {case_id!r}: route {expect['route']!r} inválida "
            f"(use {', '.join(sorted(_VALID_ROUTE))})"
        )
    if "context" in expect and expect["context"] not in _VALID_CONTEXT:
        raise CaseError(
            f"caso {case_id!r}: context {expect['context']!r} inválido "
            f"(use {', '.join(sorted(_VALID_CONTEXT))})"
        )
    if "mood_delta" in expect and expect["mood_delta"] not in _VALID_MOOD:
        raise CaseError(
            f"caso {case_id!r}: mood_delta {expect['mood_delta']!r} inválido "
            f"(use {', '.join(sorted(_VALID_MOOD))})"
        )
    if "sources_include" in expect and not isinstance(expect["sources_include"], list):
        raise CaseError(f"caso {case_id!r}: sources_include precisa ser uma lista")


def _load_file(path: Path) -> list[Case]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(raw, list):
        raise CaseError(f"{path.name}: o arquivo precisa conter uma lista de casos")
    casos: list[Case] = []
    for item in raw:
        if not isinstance(item, dict):
            raise CaseError(f"{path.name}: cada caso precisa ser um mapeamento")
        case_id = item.get("id")
        if not case_id:
            raise CaseError(f"{path.name}: caso sem 'id'")
        message = item.get("message")
        if not message:
            raise CaseError(f"caso {case_id!r}: falta 'message'")
        expect = item.get("expect") or {}
        if not isinstance(expect, dict):
            raise CaseError(f"caso {case_id!r}: 'expect' precisa ser um mapeamento")
        _validate_expect(case_id, expect)
        casos.append(
            Case(id=case_id, message=message, category=path.stem, expect=expect)
        )
    return casos


def load_cases(path: str | Path) -> list[Case]:
    """Carrega os casos de um arquivo .yaml ou de um diretório inteiro.

    A categoria de cada caso é o nome do arquivo (sem extensão). Ids precisam
    ser únicos em toda a carga.
    """
    p = Path(path)
    arquivos = sorted(p.glob("*.yaml")) if p.is_dir() else [p]
    if not arquivos:
        raise CaseError(f"nenhum arquivo de casos encontrado em {p}")

    casos: list[Case] = []
    vistos: set[str] = set()
    for arquivo in arquivos:
        for caso in _load_file(arquivo):
            if caso.id in vistos:
                raise CaseError(f"id de caso duplicado: {caso.id!r}")
            vistos.add(caso.id)
            casos.append(caso)
    return casos
```

- [ ] **Step 5: Escrever os casos reais**

Criar `bench/cases/tools.yaml`:

```yaml
# Tools — as "mãos" da Jade. Inclui NEGATIVOS: frases que parecem comando mas
# não são, e que não podem acionar o controle do sistema.
- id: tool-calculadora
  message: "abra a calculadora"
  expect: { route: tool, tool: system_control }

- id: tool-bloco-de-notas
  message: "abre o bloco de notas pra mim"
  expect: { route: tool, tool: system_control }

- id: tool-volume
  message: "aumenta o volume"
  expect: { route: tool, tool: system_control }

- id: tool-negativo-coracao
  message: "quero abrir meu coração e conversar com você"
  expect: { route: local }

- id: tool-negativo-abrir-empresa
  message: "vale a pena abrir uma empresa no Brasil hoje?"
  expect: { route: cloud }
```

Criar `bench/cases/conhecimento.yaml`:

```yaml
# Conhecimento geral: perguntas informativas que deveriam escalar para a nuvem.
- id: info-receita
  message: "como se faz pão de queijo?"
  expect: { route: cloud }

- id: info-explique
  message: "explique o que é fotossíntese"
  expect: { route: cloud }

- id: info-diferenca
  message: "qual a diferença entre TCP e UDP?"
  expect: { route: cloud }

- id: info-por-que
  message: "por que o céu é azul?"
  expect: { route: cloud }

- id: info-compare
  message: "compare energia solar e energia eólica em custo de instalação"
  expect: { route: cloud }
```

Criar `bench/cases/memoria.yaml`:

```yaml
# Memória do vault. As fontes esperadas são arquivos VERSIONADOS no repositório
# (o vault de leitura é a raiz do repo), então o recall@k é reprodutível.
- id: mem-modelo-local
  message: "qual modelo local o projeto usa?"
  expect: { route: local, sources_include: ["CLAUDE.md"] }

- id: mem-stack
  message: "qual é a stack do Project Jade?"
  expect: { route: local, sources_include: ["CLAUDE.md"] }

- id: mem-arquitetura-memoria
  message: "onde ficam guardadas as conversas da Jade?"
  expect: { route: local, sources_include: ["projeto_jade_arquitetura.md"] }

- id: mem-como-usar
  message: "como eu inicio a Jade?"
  expect: { route: local, sources_include: ["COMO_USAR.md"] }

- id: mem-seguranca
  message: "qual é a política de segurança do projeto?"
  expect: { route: local, sources_include: ["SECURITY.md"] }

- id: mem-fases
  message: "quais fases do projeto já foram concluídas?"
  expect: { route: local, context: any }
```

Criar `bench/cases/papo.yaml`:

```yaml
# Papo curto: deve ficar local e NÃO deveria puxar contexto do vault.
# É aqui que a hipótese 1 do spec (RAG dispara sempre) fica visível.
- id: papo-saudacao
  message: "oi, tudo bem?"
  expect: { route: local, context: none }

- id: papo-agradecimento
  message: "valeu, obrigado"
  expect: { route: local, context: none }

- id: papo-bom-dia
  message: "bom dia"
  expect: { route: local, context: none }

- id: papo-tchau
  message: "até mais tarde"
  expect: { route: local, context: none }
```

Criar `bench/cases/humor.yaml`:

```yaml
# Humor: o nível persistido precisa se mover na direção esperada.
- id: humor-rudeza
  message: "você é inútil, não serve pra nada"
  expect: { route: local, mood_delta: negative }

- id: humor-gentileza
  message: "você me ajudou demais hoje, obrigado mesmo"
  expect: { route: local, mood_delta: positive }

- id: humor-neutro
  message: "que horas são"
  expect: { mood_delta: neutral }
```

- [ ] **Step 6: Rodar os testes para confirmar que passam**

Run: `pytest tests/test_bench_cases.py -v`
Expected: PASS — 9 testes, inclusive `test_os_casos_reais_do_projeto_sao_validos`.

- [ ] **Step 7: Rodar lint e a suíte inteira**

Run: `ruff check . && ruff format . && pytest`
Expected: tudo verde.

- [ ] **Step 8: Commit**

```bash
git add bench/__init__.py bench/cases.py bench/cases/ tests/test_bench_cases.py requirements-dev.txt
git commit -m "feat(bench): casos declarativos em YAML com carregador validado"
```

---

### Task 4: Avaliação e agregação

**Files:**
- Create: `bench/aggregate.py`
- Test: `tests/test_bench_aggregate.py`

**Interfaces:**
- Consumes: `bench.cases.Case` (Task 3); `core.metrics.Turn` (Task 1).
- Produces:
  - `Result` — dataclass com `case_id: str`, `category: str`, `status: str`, `failures: list[str]`, `steps: dict[str, float]`, `meta: dict`.
  - Valores de `status`: `"ok"` | `"falhou"` | `"erro"` | `"pulado"`.
  - `evaluate(case: Case, turn: Turn, *, mood_before: int) -> tuple[str, list[str]]` — devolve `(status, failures)`.
  - `summarize(results: list[Result]) -> dict` — métricas agregadas (formato descrito abaixo).
  - `percentile(values: list[float], p: float) -> float`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/test_bench_aggregate.py`:

```python
"""Testes da avaliação e agregação do benchmark (bench.aggregate).

Funções puras: recebem casos e turnos sintéticos. Nada de LLM, nada de I/O.
"""

from bench.aggregate import Result, evaluate, percentile, summarize
from bench.cases import Case
from core.metrics import Turn


def _caso(expect, cid="c1", categoria="tools"):
    return Case(id=cid, message="msg", category=categoria, expect=expect)


def _turno(meta=None, steps=None):
    return Turn(steps=steps or {"total": 1.0}, meta=meta or {})


# ── evaluate ──
def test_rota_correta_passa():
    status, falhas = evaluate(
        _caso({"route": "local"}), _turno({"route": "local"}), mood_before=0
    )
    assert status == "ok"
    assert falhas == []


def test_rota_errada_falha_com_motivo():
    status, falhas = evaluate(
        _caso({"route": "cloud"}), _turno({"route": "local"}), mood_before=0
    )
    assert status == "falhou"
    assert "route" in falhas[0]


def test_nome_da_tool_e_conferido():
    status, falhas = evaluate(
        _caso({"route": "tool", "tool": "system_control"}),
        _turno({"route": "tool", "tool": "outra"}),
        mood_before=0,
    )
    assert status == "falhou"
    assert any("tool" in f for f in falhas)


def test_sources_include_exige_todas_as_fontes():
    caso = _caso({"sources_include": ["CLAUDE.md", "README.md"]})
    status, falhas = evaluate(caso, _turno({"sources": ["CLAUDE.md"]}), mood_before=0)
    assert status == "falhou"
    assert "README.md" in falhas[0]


def test_sources_include_passa_quando_todas_presentes():
    caso = _caso({"sources_include": ["CLAUDE.md"]})
    status, _ = evaluate(
        caso, _turno({"sources": ["outra.md", "CLAUDE.md"]}), mood_before=0
    )
    assert status == "ok"


def test_context_none_falha_quando_veio_contexto():
    status, falhas = evaluate(
        _caso({"context": "none"}), _turno({"chunks": 6}), mood_before=0
    )
    assert status == "falhou"
    assert "context" in falhas[0]


def test_context_none_passa_sem_chunks():
    status, _ = evaluate(_caso({"context": "none"}), _turno({"chunks": 0}), mood_before=0)
    assert status == "ok"


def test_context_any_exige_pelo_menos_um_chunk():
    status, _ = evaluate(_caso({"context": "any"}), _turno({"chunks": 3}), mood_before=0)
    assert status == "ok"


def test_mood_delta_negative():
    caso = _caso({"mood_delta": "negative"})
    status, _ = evaluate(caso, _turno({"mood_level": -2}), mood_before=0)
    assert status == "ok"


def test_mood_delta_neutral_falha_se_mudou():
    caso = _caso({"mood_delta": "neutral"})
    status, falhas = evaluate(caso, _turno({"mood_level": 3}), mood_before=0)
    assert status == "falhou"
    assert "mood" in falhas[0]


def test_varias_falhas_sao_acumuladas():
    caso = _caso({"route": "cloud", "context": "none"})
    status, falhas = evaluate(
        caso, _turno({"route": "local", "chunks": 6}), mood_before=0
    )
    assert status == "falhou"
    assert len(falhas) == 2


# ── percentile ──
def test_percentile_mediana():
    assert percentile([1.0, 2.0, 3.0], 50) == 2.0


def test_percentile_lista_vazia():
    assert percentile([], 50) == 0.0


def test_percentile_p95_pega_o_topo():
    assert percentile([1.0, 2.0, 3.0, 100.0], 95) == 100.0


# ── summarize ──
def _res(cid, categoria, status, steps=None, meta=None):
    return Result(
        case_id=cid,
        category=categoria,
        status=status,
        failures=[],
        steps=steps or {"total": 1.0},
        meta=meta or {},
    )


def test_summarize_acerto_de_rota():
    resultados = [
        _res("a", "tools", "ok"),
        _res("b", "tools", "falhou"),
        _res("c", "papo", "ok"),
    ]
    resumo = summarize(resultados)
    assert resumo["route_accuracy"] == 2 / 3
    assert resumo["by_category"]["tools"]["accuracy"] == 0.5
    assert resumo["by_category"]["papo"]["accuracy"] == 1.0


def test_summarize_ignora_pulados_na_acuracia():
    resultados = [_res("a", "tools", "ok"), _res("b", "conhecimento", "pulado")]
    resumo = summarize(resultados)
    assert resumo["route_accuracy"] == 1.0
    assert resumo["skipped"] == 1


def test_summarize_distribuicao_de_rotas():
    resultados = [
        _res("a", "tools", "ok", meta={"route": "tool"}),
        _res("b", "papo", "ok", meta={"route": "local"}),
        _res("c", "papo", "ok", meta={"route": "local"}),
    ]
    resumo = summarize(resultados)
    assert resumo["route_distribution"] == {"tool": 1, "local": 2}


def test_summarize_latencia_por_etapa():
    resultados = [
        _res("a", "papo", "ok", steps={"llm": 2.0, "total": 3.0}),
        _res("b", "papo", "ok", steps={"llm": 4.0, "total": 5.0}),
    ]
    resumo = summarize(resultados)
    # Percentil por nearest-rank: com n=2, o p50 é o menor dos dois.
    assert resumo["latency"]["llm"]["p50"] == 2.0
    assert resumo["latency"]["llm"]["p95"] == 4.0
    assert resumo["latency"]["total"]["p50"] == 3.0


def test_summarize_tokens_por_segundo():
    resultados = [
        _res(
            "a",
            "papo",
            "ok",
            meta={"eval_count": 100, "eval_duration": 2_000_000_000},  # 2s em ns
        )
    ]
    resumo = summarize(resultados)
    assert resumo["tokens_per_second"] == 50.0


def test_summarize_sem_dados_de_token():
    resumo = summarize([_res("a", "papo", "ok")])
    assert resumo["tokens_per_second"] is None
```

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `pytest tests/test_bench_aggregate.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'bench.aggregate'`

- [ ] **Step 3: Implementar a agregação**

Criar `bench/aggregate.py`:

```python
"""Avaliação de um caso contra o turno medido, e agregação em métricas.

Tudo aqui é função pura: recebe dados, devolve dados. Não executa a Jade, não
lê arquivo, não fala com o LLM — por isso roda no CI.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from bench.cases import Case
from core.metrics import Turn


@dataclass
class Result:
    """Desfecho de um caso: o que se pediu, o que aconteceu, e quanto custou."""

    case_id: str
    category: str
    #: "ok" | "falhou" | "erro" | "pulado"
    status: str
    failures: list[str] = field(default_factory=list)
    steps: dict[str, float] = field(default_factory=dict)
    meta: dict = field(default_factory=dict)
    #: preenchido quando status == "erro" ou "pulado"
    detail: str = ""


def evaluate(case: Case, turn: Turn, *, mood_before: int) -> tuple[str, list[str]]:
    """Confere o que se esperava do caso contra o que o turno registrou.

    Devolve ("ok", []) ou ("falhou", [motivos]). Acumula todos os motivos — um
    caso pode errar a rota E trazer contexto indevido, e as duas coisas importam.
    """
    falhas: list[str] = []
    expect = case.expect

    if "route" in expect:
        obtida = turn.meta.get("route")
        if obtida != expect["route"]:
            falhas.append(f"route: esperava {expect['route']!r}, veio {obtida!r}")

    if "tool" in expect:
        obtida = turn.meta.get("tool")
        if obtida != expect["tool"]:
            falhas.append(f"tool: esperava {expect['tool']!r}, veio {obtida!r}")

    if "sources_include" in expect:
        obtidas = set(turn.meta.get("sources") or [])
        faltando = [s for s in expect["sources_include"] if s not in obtidas]
        if faltando:
            falhas.append(
                f"sources_include: faltou {', '.join(faltando)} "
                f"(veio: {', '.join(sorted(obtidas)) or 'nada'})"
            )

    if "context" in expect:
        chunks = int(turn.meta.get("chunks") or 0)
        if expect["context"] == "none" and chunks > 0:
            falhas.append(f"context: esperava nenhum trecho, vieram {chunks}")
        if expect["context"] == "any" and chunks == 0:
            falhas.append("context: esperava algum trecho, não veio nenhum")

    if "mood_delta" in expect:
        depois = int(turn.meta.get("mood_level") or 0)
        delta = depois - mood_before
        direcao = "positive" if delta > 0 else "negative" if delta < 0 else "neutral"
        if direcao != expect["mood_delta"]:
            falhas.append(
                f"mood_delta: esperava {expect['mood_delta']!r}, "
                f"veio {direcao!r} ({mood_before:+d} → {depois:+d})"
            )

    return ("falhou", falhas) if falhas else ("ok", [])


def percentile(values: list[float], p: float) -> float:
    """Percentil por índice (nearest-rank). 0.0 para lista vazia."""
    if not values:
        return 0.0
    ordenados = sorted(values)
    indice = max(0, min(len(ordenados) - 1, round(p / 100 * len(ordenados)) - 1))
    return ordenados[indice]


def _quality(results: list[Result], expect_key: str) -> float | None:
    """Fração de acerto entre os casos que declaram `expect_key`.

    Devolve None quando nenhum caso exercita a métrica — melhor um traço no
    relatório do que um 0% que parece defeito.
    """
    relevantes = [r for r in results if expect_key in r.meta.get("_expect", {})]
    if not relevantes:
        return None
    acertos = sum(1 for r in relevantes if r.status == "ok")
    return acertos / len(relevantes)


def summarize(results: list[Result]) -> dict:
    """Agrega os resultados nas métricas do relatório."""
    avaliados = [r for r in results if r.status in {"ok", "falhou"}]
    acertos = sum(1 for r in avaliados if r.status == "ok")

    por_categoria: dict[str, dict] = {}
    for r in avaliados:
        bucket = por_categoria.setdefault(r.category, {"total": 0, "ok": 0})
        bucket["total"] += 1
        bucket["ok"] += 1 if r.status == "ok" else 0
    for bucket in por_categoria.values():
        bucket["accuracy"] = bucket["ok"] / bucket["total"] if bucket["total"] else 0.0

    etapas: dict[str, list[float]] = {}
    for r in avaliados:
        for etapa, segundos in r.steps.items():
            etapas.setdefault(etapa, []).append(segundos)
    latencia = {
        etapa: {"p50": percentile(v, 50), "p95": percentile(v, 95), "n": len(v)}
        for etapa, v in sorted(etapas.items())
    }

    prompt_tokens = [
        float(r.meta["prompt_eval_count"]) for r in avaliados if "prompt_eval_count" in r.meta
    ]

    tokens = sum(int(r.meta["eval_count"]) for r in avaliados if "eval_count" in r.meta)
    duracao_ns = sum(
        int(r.meta["eval_duration"]) for r in avaliados if "eval_duration" in r.meta
    )
    tps = (tokens / (duracao_ns / 1e9)) if tokens and duracao_ns else None

    return {
        "total": len(results),
        "evaluated": len(avaliados),
        "ok": acertos,
        "failed": len(avaliados) - acertos,
        "skipped": sum(1 for r in results if r.status == "pulado"),
        "errored": sum(1 for r in results if r.status == "erro"),
        "route_accuracy": acertos / len(avaliados) if avaliados else 0.0,
        "by_category": por_categoria,
        "recall_at_k": _quality(avaliados, "sources_include"),
        "context_precision": _quality(avaliados, "context"),
        "route_distribution": dict(
            Counter(r.meta.get("route") for r in avaliados if r.meta.get("route"))
        ),
        "latency": latencia,
        "tokens_per_second": tps,
        "prompt_tokens": {
            "p50": percentile(prompt_tokens, 50),
            "p95": percentile(prompt_tokens, 95),
        }
        if prompt_tokens
        else None,
    }
```

**Nota de implementação:** `_quality` lê `r.meta["_expect"]`. O runner (Task 5)
injeta o `expect` do caso dentro de `Result.meta` sob a chave `_expect` para que
`summarize` continue sendo uma função pura sobre `Result`, sem precisar receber
os `Case` de novo. Os testes de `summarize` acima que não exercitam `recall_at_k`
e `context_precision` recebem `None` nessas chaves, o que é o comportamento
correto.

- [ ] **Step 4: Rodar os testes para confirmar que passam**

Run: `pytest tests/test_bench_aggregate.py -v`
Expected: PASS — 21 testes.

- [ ] **Step 5: Rodar lint e a suíte inteira**

Run: `ruff check . && ruff format . && pytest`
Expected: tudo verde.

- [ ] **Step 6: Commit**

```bash
git add bench/aggregate.py tests/test_bench_aggregate.py
git commit -m "feat(bench): avaliacao das decisoes da Jade e agregacao em metricas"
```

---

### Task 5: Relatório com delta

**Files:**
- Create: `bench/report.py`
- Test: `tests/test_bench_report.py`

**Interfaces:**
- Consumes: `bench.aggregate.Result` e o dicionário de `summarize()` (Task 4).
- Produces:
  - `render(summary: dict, results: list[Result], *, tag: str = "", previous: dict | None = None) -> str` — Markdown do relatório.
  - `load_previous(reports_dir: str | Path) -> dict | None` — lê o `.json` mais recente, ou `None`.
  - `write(reports_dir: str | Path, summary: dict, results: list[Result], *, tag: str = "") -> Path` — grava o par `.md` + `.json` e devolve o caminho do `.md`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/test_bench_report.py`:

```python
"""Testes do relatório do benchmark (bench.report)."""

import json

from bench.aggregate import Result
from bench.report import load_previous, render, write


def _resumo(**over):
    base = {
        "total": 2,
        "evaluated": 2,
        "ok": 1,
        "failed": 1,
        "skipped": 0,
        "errored": 0,
        "route_accuracy": 0.5,
        "by_category": {"tools": {"total": 2, "ok": 1, "accuracy": 0.5}},
        "recall_at_k": 1.0,
        "context_precision": 0.0,
        "route_distribution": {"local": 2},
        "latency": {"llm": {"p50": 2.0, "p95": 3.0, "n": 2}},
        "tokens_per_second": 37.5,
        "prompt_tokens": {"p50": 1200.0, "p95": 1800.0},
    }
    base.update(over)
    return base


def _resultados():
    return [
        Result(case_id="a", category="tools", status="ok"),
        Result(
            case_id="b",
            category="tools",
            status="falhou",
            failures=["route: esperava 'cloud', veio 'local'"],
        ),
    ]


def test_render_traz_as_metricas_principais():
    md = render(_resumo(), _resultados())
    assert "Acerto de rota" in md
    assert "50" in md  # 50%
    assert "37.5" in md or "37,5" in md


def test_render_lista_as_falhas_com_motivo():
    md = render(_resumo(), _resultados())
    assert "esperava 'cloud', veio 'local'" in md


def test_render_sem_anterior_nao_mostra_delta():
    md = render(_resumo(), _resultados())
    assert "Delta" not in md


def test_render_com_anterior_mostra_delta_com_sinal():
    anterior = _resumo(route_accuracy=0.25)
    md = render(_resumo(), _resultados(), previous=anterior)
    assert "Delta" in md
    assert "+25" in md


def test_render_marca_metrica_ausente_com_traco():
    md = render(_resumo(tokens_per_second=None, prompt_tokens=None), _resultados())
    assert "—" in md


def test_write_grava_md_e_json(tmp_path):
    caminho = write(tmp_path, _resumo(), _resultados(), tag="baseline")
    assert caminho.suffix == ".md"
    assert caminho.exists()
    gemeo = caminho.with_suffix(".json")
    assert gemeo.exists()
    assert json.loads(gemeo.read_text(encoding="utf-8"))["route_accuracy"] == 0.5
    assert "baseline" in caminho.name


def test_load_previous_devolve_none_em_pasta_vazia(tmp_path):
    assert load_previous(tmp_path) is None


def test_load_previous_le_o_mais_recente(tmp_path):
    write(tmp_path, _resumo(route_accuracy=0.1), _resultados(), tag="antigo")
    (tmp_path / "2099-01-01-0000-novo.json").write_text(
        json.dumps(_resumo(route_accuracy=0.9)), encoding="utf-8"
    )
    assert load_previous(tmp_path)["route_accuracy"] == 0.9
```

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `pytest tests/test_bench_report.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'bench.report'`

- [ ] **Step 3: Implementar o relatório**

Criar `bench/report.py`:

```python
"""Relatório do benchmark: Markdown para humano, JSON para a comparação.

O `.md` é o que você lê; o `.json` gêmeo é o que a execução seguinte carrega
para calcular o delta. Os dois são versionados no git — a série histórica é o
que torna regressão visível sem ninguém ir procurar.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from bench.aggregate import Result

_TRACO = "—"


def _pct(value: float | None) -> str:
    return f"{value * 100:.1f}%" if value is not None else _TRACO


def _num(value: float | None, casas: int = 1) -> str:
    return f"{value:.{casas}f}" if value is not None else _TRACO


def _delta_pct(atual: float | None, anterior: float | None) -> str:
    """Variação em pontos percentuais, com sinal explícito."""
    if atual is None or anterior is None:
        return _TRACO
    diff = (atual - anterior) * 100
    return f"{diff:+.1f} p.p." if abs(diff) >= 0.05 else "="


def _delta_num(atual: float | None, anterior: float | None) -> str:
    if atual is None or anterior is None:
        return _TRACO
    diff = atual - anterior
    return f"{diff:+.2f}" if abs(diff) >= 0.005 else "="


def render(
    summary: dict,
    results: list[Result],
    *,
    tag: str = "",
    previous: dict | None = None,
) -> str:
    """Monta o relatório em Markdown."""
    quando = datetime.now().strftime("%Y-%m-%d %H:%M")
    linhas: list[str] = [
        f"# Benchmark da Jade — {quando}" + (f" · `{tag}`" if tag else ""),
        "",
        f"{summary['evaluated']} caso(s) avaliado(s) · "
        f"{summary['ok']} ok · {summary['failed']} falhou · "
        f"{summary['skipped']} pulado · {summary['errored']} erro",
        "",
        "## Qualidade das decisões",
        "",
    ]

    cabecalho = "| Métrica | Valor |"
    separador = "|---|---|"
    if previous:
        cabecalho = "| Métrica | Valor | Delta |"
        separador = "|---|---|---|"
    linhas += [cabecalho, separador]

    qualidade = [
        ("Acerto de rota", summary["route_accuracy"], previous and previous.get("route_accuracy")),
        ("Recall@k do RAG", summary["recall_at_k"], previous and previous.get("recall_at_k")),
        (
            "Precisão de contexto",
            summary["context_precision"],
            previous and previous.get("context_precision"),
        ),
    ]
    for nome, atual, anterior in qualidade:
        linha = f"| {nome} | {_pct(atual)} |"
        if previous:
            linha += f" {_delta_pct(atual, anterior)} |"
        linhas.append(linha)

    linhas += ["", "### Por categoria", "", "| Categoria | Acerto | Casos |", "|---|---|---|"]
    for categoria, dados in sorted(summary["by_category"].items()):
        linhas.append(f"| {categoria} | {_pct(dados['accuracy'])} | {dados['total']} |")

    dist = summary["route_distribution"]
    linhas += [
        "",
        "### Distribuição real de rotas",
        "",
        ("| " + " | ".join(dist) + " |") if dist else "(nenhuma rota registrada)",
    ]
    if dist:
        linhas.append("|" + "---|" * len(dist))
        linhas.append("| " + " | ".join(str(v) for v in dist.values()) + " |")

    linhas += ["", "## Desempenho", "", "| Etapa | p50 (s) | p95 (s) | n |", "|---|---|---|---|"]
    for etapa, dados in summary["latency"].items():
        linhas.append(
            f"| `{etapa}` | {_num(dados['p50'], 3)} | {_num(dados['p95'], 3)} | {dados['n']} |"
        )

    tps = summary["tokens_per_second"]
    tokens = summary["prompt_tokens"]
    linhas += ["", "| Métrica | Valor |" + (" Delta |" if previous else ""), "|---|---|" + ("---|" if previous else "")]
    linha_tps = f"| Tokens/s (local) | {_num(tps)} |"
    if previous:
        linha_tps += f" {_delta_num(tps, previous.get('tokens_per_second'))} |"
    linhas.append(linha_tps)
    linhas.append(
        f"| Tokens de prompt p50 | {_num(tokens['p50'], 0) if tokens else _TRACO} |"
        + (" |" if previous else "")
    )
    linhas.append(
        f"| Tokens de prompt p95 | {_num(tokens['p95'], 0) if tokens else _TRACO} |"
        + (" |" if previous else "")
    )

    falhas = [r for r in results if r.status in {"falhou", "erro", "pulado"}]
    if falhas:
        linhas += ["", "## Casos que não passaram", ""]
        for r in falhas:
            motivo = "; ".join(r.failures) or r.detail or r.status
            linhas.append(f"- **`{r.case_id}`** ({r.category}) — {r.status}: {motivo}")

    return "\n".join(linhas) + "\n"


def _stamp(tag: str) -> str:
    base = datetime.now().strftime("%Y-%m-%d-%H%M")
    return f"{base}-{tag}" if tag else base


def load_previous(reports_dir: str | Path) -> dict | None:
    """Carrega o resumo da execução anterior (o .json de nome mais recente)."""
    pasta = Path(reports_dir)
    if not pasta.is_dir():
        return None
    arquivos = sorted(pasta.glob("*.json"))
    if not arquivos:
        return None
    try:
        return json.loads(arquivos[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write(
    reports_dir: str | Path,
    summary: dict,
    results: list[Result],
    *,
    tag: str = "",
) -> Path:
    """Grava o par .md + .json e devolve o caminho do .md."""
    pasta = Path(reports_dir)
    pasta.mkdir(parents=True, exist_ok=True)
    anterior = load_previous(pasta)

    nome = _stamp(tag)
    md = pasta / f"{nome}.md"
    md.write_text(render(summary, results, tag=tag, previous=anterior), encoding="utf-8")
    (pasta / f"{nome}.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return md
```

- [ ] **Step 4: Rodar os testes para confirmar que passam**

Run: `pytest tests/test_bench_report.py -v`
Expected: PASS — 8 testes.

- [ ] **Step 5: Rodar lint e a suíte inteira**

Run: `ruff check . && ruff format . && pytest`
Expected: tudo verde.

- [ ] **Step 6: Commit**

```bash
git add bench/report.py tests/test_bench_report.py
git commit -m "feat(bench): relatorio em markdown com delta contra a execucao anterior"
```

---

### Task 6: Runner e comando CLI

**Files:**
- Create: `bench/runner.py`
- Modify: `main.py` (docstring de uso + dispatch de comando)
- Test: `tests/test_bench_runner.py`

**Interfaces:**
- Consumes: `bench.cases.load_cases`, `bench.aggregate.evaluate/summarize/Result`, `bench.report.write`, `core.metrics.capture`, `core.chat.ChatSession`.
- Produces:
  - `health_check() -> None` — levanta `RuntimeError` com mensagem acionável se o Ollama não responder.
  - `isolated_notes() -> ContextManager[None]` — troca `settings.NOTES_DIR` por um diretório temporário durante o bloco, copiando as notas de estado reais para dentro.
  - `run_case(case, *, cloud_ok: bool) -> Result`
  - `main(argv: list[str]) -> int` — código de saída 0 em sucesso.

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/test_bench_runner.py`:

```python
"""Testes do runner do benchmark (bench.runner).

O laço e o isolamento são testados com a ChatSession mockada — sem Ollama.
"""

import pytest

import bench.runner as runner_mod
from bench.cases import Case
from core.config import settings


class FakeSession:
    """Sessão falsa: anota rota e chunks como se tivesse respondido."""

    def __init__(self, route="local", chunks=0, tool=None, boom=False, **kwargs):
        self._route = route
        self._chunks = chunks
        self._tool = tool
        self._boom = boom

    def send(self, message):
        from core.metrics import note

        if self._boom:
            raise RuntimeError("ollama caiu")
        note(route=self._route, chunks=self._chunks, mood_level=0)
        if self._tool:
            note(tool=self._tool)
        return "resposta"


def _caso(expect, cid="c1"):
    return Case(id=cid, message="oi", category="papo", expect=expect)


def test_run_case_ok(monkeypatch):
    monkeypatch.setattr(runner_mod, "ChatSession", lambda **k: FakeSession())
    r = runner_mod.run_case(_caso({"route": "local"}), cloud_ok=True)
    assert r.status == "ok"
    assert r.meta["route"] == "local"


def test_run_case_falhou(monkeypatch):
    monkeypatch.setattr(runner_mod, "ChatSession", lambda **k: FakeSession())
    r = runner_mod.run_case(_caso({"route": "cloud"}), cloud_ok=True)
    assert r.status == "falhou"
    assert r.failures


def test_run_case_pula_nuvem_sem_chave(monkeypatch):
    monkeypatch.setattr(runner_mod, "ChatSession", lambda **k: FakeSession())
    r = runner_mod.run_case(_caso({"route": "cloud"}), cloud_ok=False)
    assert r.status == "pulado"
    assert "ANTHROPIC_API_KEY" in r.detail


def test_run_case_captura_excecao(monkeypatch):
    monkeypatch.setattr(runner_mod, "ChatSession", lambda **k: FakeSession(boom=True))
    r = runner_mod.run_case(_caso({"route": "local"}), cloud_ok=True)
    assert r.status == "erro"
    assert "ollama caiu" in r.detail


def test_run_case_guarda_o_expect_para_a_agregacao(monkeypatch):
    monkeypatch.setattr(runner_mod, "ChatSession", lambda **k: FakeSession())
    r = runner_mod.run_case(_caso({"route": "local", "context": "none"}), cloud_ok=True)
    assert r.meta["_expect"] == {"route": "local", "context": "none"}


def test_isolated_notes_troca_e_restaura(tmp_path):
    original = settings.NOTES_DIR
    with runner_mod.isolated_notes():
        assert settings.NOTES_DIR != original
        assert settings.NOTES_DIR.is_dir()
    assert settings.NOTES_DIR == original


def test_isolated_notes_restaura_mesmo_com_excecao():
    original = settings.NOTES_DIR
    with pytest.raises(RuntimeError):
        with runner_mod.isolated_notes():
            raise RuntimeError("boom")
    assert settings.NOTES_DIR == original


def test_health_check_falha_com_mensagem_util(monkeypatch):
    def explode(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr(runner_mod, "urlopen", explode)
    with pytest.raises(RuntimeError, match="Ollama"):
        runner_mod.health_check()
```

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `pytest tests/test_bench_runner.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'bench.runner'`

- [ ] **Step 3: Implementar o runner**

Criar `bench/runner.py`:

```python
"""Runner do benchmark: orquestra health check, isolamento e execução.

Isolamento: durante toda a execução, `settings.NOTES_DIR` aponta para um
diretório temporário. Isso protege de uma vez só o humor, o perfil do usuário e
qualquer escrita de conversa — sem precisar restaurar valor a valor. As notas de
estado reais são **copiadas** para lá, para o system prompt medido continuar
realista. O índice do RAG **não** é isolado: ele lê o vault versionado do
repositório, e é justamente isso que torna o recall@k reprodutível.
"""

from __future__ import annotations

import argparse
import contextlib
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from urllib.request import urlopen

from bench.aggregate import Result, evaluate, summarize
from bench.cases import Case, CaseError, load_cases
from bench.report import write
from core.chat import ChatSession
from core.config import settings
from core.metrics import capture
from core.model_router import cloud_available

_REPORTS_DIR = Path(__file__).parent / "reports"
_CASES_DIR = Path(__file__).parent / "cases"


def health_check() -> None:
    """Confere que o Ollama responde. Falha rápido, com instrução acionável."""
    try:
        urlopen(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=2).close()
    except Exception as e:
        raise RuntimeError(
            f"Ollama não respondeu em {settings.OLLAMA_BASE_URL}.\n"
            "  1. Garanta que o serviço do Ollama está rodando.\n"
            f"  2. Baixe os modelos: ollama pull {settings.OLLAMA_MODEL} "
            f"&& ollama pull {settings.OLLAMA_EMBED_MODEL}"
        ) from e


@contextlib.contextmanager
def isolated_notes() -> Iterator[None]:
    """Aponta `settings.NOTES_DIR` para um diretório temporário durante o bloco."""
    original = settings.NOTES_DIR
    temporario = Path(tempfile.mkdtemp(prefix="jade_bench_"))
    for nota in (settings.PERSONALITY_NOTE, settings.MOOD_NOTE, settings.PROFILE_NOTE):
        origem = original / nota
        if origem.is_file():
            with contextlib.suppress(OSError):
                shutil.copy2(origem, temporario / nota)
    settings.NOTES_DIR = temporario
    try:
        yield
    finally:
        settings.NOTES_DIR = original
        shutil.rmtree(temporario, ignore_errors=True)


def _mood_level() -> int:
    from core.mood import load_level

    return load_level()


def run_case(case: Case, *, cloud_ok: bool) -> Result:
    """Executa um caso numa sessão nova e avalia o turno medido."""
    if case.expect.get("route") == "cloud" and not cloud_ok:
        return Result(
            case_id=case.id,
            category=case.category,
            status="pulado",
            detail="rota 'cloud' exige ANTHROPIC_API_KEY configurada",
            meta={"_expect": dict(case.expect)},
        )

    antes = _mood_level()
    session = ChatSession(use_journal=False)
    try:
        with capture() as turn:
            session.send(case.message)
    except Exception as e:
        return Result(
            case_id=case.id,
            category=case.category,
            status="erro",
            detail=f"{type(e).__name__}: {e}",
            meta={"_expect": dict(case.expect)},
        )

    status, falhas = evaluate(case, turn, mood_before=antes)
    meta = dict(turn.meta)
    meta["_expect"] = dict(case.expect)
    return Result(
        case_id=case.id,
        category=case.category,
        status=status,
        failures=falhas,
        steps=dict(turn.steps),
        meta=meta,
    )


def run(cases: list[Case], *, repeat: int = 1) -> list[Result]:
    """Executa todos os casos `repeat` vezes. Um caso quebrado não derruba a suíte."""
    cloud_ok = cloud_available()
    resultados: list[Result] = []
    total = len(cases) * repeat
    feito = 0
    for _ in range(repeat):
        for case in cases:
            feito += 1
            print(f"[{feito}/{total}] {case.id} … ", end="", flush=True)
            resultado = run_case(case, cloud_ok=cloud_ok)
            resultados.append(resultado)
            print(resultado.status)
    return resultados


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python main.py bench",
        description="Mede desempenho e qualidade das decisões da Jade.",
    )
    parser.add_argument("--repeat", type=int, default=1, help="repetições por caso (default: 1)")
    parser.add_argument("--cases", default=str(_CASES_DIR), help="arquivo .yaml ou pasta de casos")
    parser.add_argument("--tag", default="", help="rótulo no nome do relatório")
    args = parser.parse_args(argv)

    try:
        health_check()
    except RuntimeError as e:
        print(f"❌ {e}")
        return 1

    try:
        cases = load_cases(args.cases)
    except CaseError as e:
        print(f"❌ Caso inválido: {e}")
        return 1

    if not cloud_available():
        print("ℹ️  Sem ANTHROPIC_API_KEY: os casos de rota 'cloud' serão pulados.\n")

    with isolated_notes():
        resultados = run(cases, repeat=args.repeat)

    resumo = summarize(resultados)
    caminho = write(_REPORTS_DIR, resumo, resultados, tag=args.tag)

    print(
        f"\n✓ {resumo['ok']}/{resumo['evaluated']} caso(s) ok "
        f"({resumo['route_accuracy'] * 100:.1f}% de acerto de rota)"
    )
    print(f"📄 Relatório: {caminho}")
    return 0
```

- [ ] **Step 4: Ligar o comando na CLI**

Em `main.py`, atualizar a docstring do topo (linhas 3-6) para:

```python
"""Ponto de entrada do Project Jade.

Uso:
    python main.py            # sobe a API FastAPI (uvicorn)
    python main.py chat       # chat via terminal (Fase 1)
    python main.py index      # (re)indexa o vault no RAG
    python main.py bench      # mede desempenho e qualidade (ver bench/)
"""
```

Acrescentar a função, logo depois de `run_index` (`main.py:61`):

```python
def run_bench() -> int:
    """Roda o benchmark da Jade e escreve o relatório em bench/reports/."""
    from bench.runner import main as bench_main

    return bench_main(sys.argv[2:])
```

Substituir o bloco `if __name__ == "__main__":` (`main.py:143-154`) por:

```python
if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "chat":
        run_cli()
    elif command == "index":
        run_index()
    elif command == "transcribe":
        run_transcribe()
    elif command == "say":
        run_say()
    elif command == "bench":
        sys.exit(run_bench())
    else:
        run_api()
```

- [ ] **Step 5: Rodar os testes para confirmar que passam**

Run: `pytest tests/test_bench_runner.py -v`
Expected: PASS — 8 testes.

- [ ] **Step 6: Rodar lint e a suíte inteira**

Run: `ruff check . && ruff format . && pytest`
Expected: tudo verde.

- [ ] **Step 7: Verificar o pipeline de segurança**

Run: `bandit -c pyproject.toml -r core tools interfaces bench main.py`
Expected: sem findings. `urlopen` sobre uma URL vinda de `settings` pode disparar `B310` — se disparar, adicione `# nosec B310` na linha com um comentário PT-BR explicando que a URL vem da configuração local, não de entrada do usuário.

- [ ] **Step 8: Commit**

```bash
git add bench/runner.py main.py tests/test_bench_runner.py
git commit -m "feat(bench): runner isolado, health check e comando 'python main.py bench'"
```

---

### Task 7: Rodar e commitar o baseline

**Files:**
- Create: `bench/reports/*.md` e `bench/reports/*.json` (gerados)
- Modify: `CLAUDE.md`, `.gitignore` (se necessário)

**Interfaces:**
- Consumes: tudo das Tasks 1–6.
- Produces: o relatório baseline versionado — o "onde estamos" que motivou o projeto.

- [ ] **Step 1: Garantir que os relatórios não estão ignorados**

Verificar: `git check-ignore -v bench/reports/teste.md`
Expected: sem saída (não ignorado). Se estiver ignorado, adicionar `!bench/reports/` ao `.gitignore`.

- [ ] **Step 2: Garantir que o Ollama está pronto**

```bash
ollama pull qwen3:8b
ollama pull nomic-embed-text
python main.py index
```

- [ ] **Step 3: Rodar o baseline**

Run: `python main.py bench --repeat 3 --tag baseline`
Expected: os ~25 casos rodam, cada um imprime seu status, e o relatório é escrito em `bench/reports/`.

Se muitos casos derem `erro`, **não maquie o relatório** — investigue a causa antes de commitar. Um baseline com erros mascarados não serve de linha de base para nada.

- [ ] **Step 4: Ler o relatório e registrar as conclusões**

Abrir o `.md` gerado e conferir, especificamente, as três hipóteses que o spec quis testar:

- **Hipótese 1 (roteador morto):** o que diz "Precisão de contexto" e a "Distribuição real de rotas"? Se `cloud` for 0 e a precisão de contexto for baixa, está confirmada.
- **Hipótese 4 (`sync_vault` no 1º turno):** o p95 de `rag_sync` está muito acima do p50?
- **Hipótese 5 (journal quadrático):** `journal` aparece com tempo relevante?

Acrescentar ao final do relatório uma seção `## Leitura` com 3 a 6 linhas em PT-BR resumindo o que os números dizem sobre cada hipótese. Este é o entregável que o usuário pediu.

- [ ] **Step 5: Atualizar o CLAUDE.md**

Na seção "Qualidade & Segurança", acrescentar depois da linha do `pytest`:

```markdown
- `python main.py bench` — benchmark de desempenho e qualidade das decisões
  (exige Ollama; **não** roda no CI). Escreve `bench/reports/`, com delta contra
  a execução anterior. Ver `docs/superpowers/specs/2026-08-03-regua-performance-jade-design.md`.
```

Na seção "Estado atual", acrescentar ao final, antes de "**Próximo:**":

```markdown
- **Régua de performance** (`core/metrics.py` + `bench/`): instrumentação por
  etapa com custo zero fora do benchmark, e casos declarativos que medem as
  **decisões** da Jade (rota, tool, recall@k do RAG) de forma determinística.
  O baseline vive em `bench/reports/`.
```

- [ ] **Step 6: Rodar a verificação final completa**

Run: `ruff check . && ruff format . && pytest && bandit -c pyproject.toml -r core tools interfaces bench main.py`
Expected: tudo verde.

- [ ] **Step 7: Commit e abrir o PR**

```bash
git add bench/reports/ CLAUDE.md .gitignore
git commit -m "feat(bench): baseline de desempenho e qualidade da Jade"
git push -u origin feat/regua-performance
gh pr create --title "feat(bench): a régua — instrumentação e benchmark da Jade" --body "Implementa o subprojeto #1 do spec docs/superpowers/specs/2026-08-03-regua-performance-jade-design.md.

Instrumentação por etapa com custo zero fora do benchmark, casos declarativos em YAML, avaliação determinística das decisões da Jade e relatório versionado com delta.

O baseline commitado é o retrato de onde a Jade está hoje — defeitos incluídos. Ele é a linha de base contra a qual os subprojetos #2 (latência) e #3 (qualidade) vão se provar.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

---

## Notas para quem executa

**Se um teste pré-existente quebrar na Task 2**, pare. O contrato de `send()` não pode mudar — é uma restrição global deste plano. Reverta a alteração e reavalie o ponto de marcação que causou a quebra.

**Se o baseline sair "bonito demais"** (100% de acerto de rota, precisão de contexto alta), desconfie do isolamento antes de comemorar: verifique se `settings.NOTES_DIR` foi realmente trocado e se o índice do ChromaDB existe. Um bench que não exercita nada passa em tudo.

**A ordem das tasks é obrigatória.** Task 2 consome Task 1; Tasks 4 e 5 consomem Task 3; Task 6 consome tudo. Task 7 só faz sentido no fim.
