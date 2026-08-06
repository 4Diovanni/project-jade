# Qualidade — limiar do RAG, roteador dual-model e dedup de contexto — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer `core/memory.py::query_memory()` filtrar contexto por distância e fundir chunks adjacentes que se sobrepõem, para que `has_context` volte a ser um sinal real — o que destrava, sem tocar em código de roteamento, a rota `cloud` do roteador dual-model.

**Architecture:** Mudança cirúrgica em um arquivo (`core/memory.py`) mais uma setting nova (`core/config.py`). `query_memory()` passa a ler as distâncias que o Chroma já devolve, descartar trechos acima de `RAG_MAX_DISTANCE`, e fundir chunks consecutivos (`chunk: i`, `chunk: i+1`) da mesma nota por string matching real (sem assumir tamanho fixo de overlap). `core/model_router.py` e `core/chat.py` não mudam — a lógica deles já está correta; só nunca recebiam um `has_context` que pudesse ser `False`.

**Tech Stack:** Python 3.11+, ChromaDB (distâncias via `collection.query`), pytest com mocks (sem Ollama nos testes automatizados).

**Spec:** `docs/superpowers/specs/2026-08-05-qualidade-rag-roteador-design.md`

## Global Constraints

- **Identificadores de código em inglês; comentários e docstrings em PT-BR.** Convenção do projeto (`CLAUDE.md`).
- **Configuração sempre via `core.config.settings`** — nunca `os.getenv` espalhado.
- **Swallow de exceção usa `contextlib.suppress`** — o Bandit rejeita `try/except/pass`.
- **Zero mudança de código em `core/model_router.py` e `core/chat.py`.** O roteador já decide certo; se alguma task deste plano achar necessário editar esses arquivos, o desenho está errado — pare e reavalie contra o spec.
- **Contexto do RAG acima do limiar sempre trava a rota em `local`**, mesmo que a mensagem pareça informativa. Decisão explícita do spec — privacidade prevalece, sem segundo corte de "contexto fraco vs forte".
- **Dedup é só overlap literal entre chunks adjacentes da MESMA fonte.** Sem dedup semântica entre notas diferentes.
- **Sem ferramenta de calibração permanente em `bench/`.** A calibração (Task 5) é uma investigação pontual, com script descartável que nunca é commitado.
- **O contrato de `query_memory()` não muda:** mesma assinatura (`question: str, k: int | None = None`), mesmo tipo de retorno (`list[str]`). As asserções dos testes já existentes em `tests/test_memory.py` e `tests/test_chat.py` não podem mudar — só acréscimo de testes novos.
- **`python main.py bench` não roda no CI** (exige Ollama). É a validação manual da Task 6, não faz parte da suíte `pytest`.
- **Antes de cada commit:** `ruff check . && ruff format .` e `pytest`. Antes de finalizar a branch (Task 6): também `bandit -c pyproject.toml -r core tools interfaces bench main.py` e `pip-audit -r requirements.txt --ignore-vuln PYSEC-2026-311`.
- **Workflow de git:** todo o trabalho acontece na branch `feat/qualidade-rag-roteador` (já criada a partir de `origin/main`). Nunca commitar na `main`.

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `core/config.py` | **Modificar.** Nova setting `RAG_MAX_DISTANCE` (valor provisório na Task 3, calibrado na Task 5). |
| `core/memory.py` | **Modificar.** `_filter_by_distance()`, `_merge_overlap()`, `_merge_adjacent_chunks()` novos; `query_memory()` reescrito para usá-los. |
| `.env.example` | **Modificar.** Entrada documentada para `RAG_MAX_DISTANCE`, ao lado de `RAG_TOP_K`. |
| `tests/test_memory.py` | **Modificar.** Testes novos para os três helpers e para `query_memory()` filtrando/fundindo. |
| `tests/test_chat.py` | **Modificar.** Testes fim-a-fim provando que `has_context=False` alcança `cloud` e que contexto sempre trava `local` — sem mudar `core/model_router.py`. |
| `core/model_router.py` | **Não modificado.** Validado pelos testes de `tests/test_chat.py` da Task 4. |

---

### Task 1: Fundir chunks adjacentes — helpers puros

**Files:**
- Modify: `core/memory.py` (inserir após `chunk_text()`, linha 56)
- Test: `tests/test_memory.py` (acrescentar ao final)

**Interfaces:**
- Produces: `core.memory._merge_overlap(a: str, b: str) -> str` — funde dois textos cortando o maior sufixo de `a` que é prefixo de `b`.
- Produces: `core.memory._merge_adjacent_chunks(entries: list[tuple[str, dict]]) -> list[str]` — recebe pares `(doc, meta)` na ordem de relevância do Chroma; devolve blocos `"[fonte]\ntexto"` com chunks consecutivos (`chunk: i`, `chunk: i+1`) da mesma fonte fundidos.

- [ ] **Step 1: Escrever os testes que falham**

Primeiro, trocar o import já existente no topo de `tests/test_memory.py`
(linha 8) — de:

```python
from core.memory import chunk_text, iter_vault_notes
```

Para:

```python
from core.memory import _merge_adjacent_chunks, _merge_overlap, chunk_text, iter_vault_notes
```

Depois, acrescentar ao final de `tests/test_memory.py`:

```python
def test_merge_overlap_corta_sufixo_repetido():
    a = "isto é um chunk que termina em ABC"
    b = "ABC continua no próximo chunk"
    assert _merge_overlap(a, b) == "isto é um chunk que termina em ABC continua no próximo chunk"


def test_merge_overlap_sem_sobreposicao_concatena():
    assert _merge_overlap("frase um", "frase dois") == "frase umfrase dois"


def test_merge_adjacent_chunks_funde_pares_consecutivos():
    entries = [
        ("isto é um chunk que termina em ABC", {"source": "nota.md", "chunk": 0}),
        ("ABC continua no próximo chunk", {"source": "nota.md", "chunk": 1}),
    ]
    out = _merge_adjacent_chunks(entries)
    assert out == ["[nota.md]\nisto é um chunk que termina em ABC continua no próximo chunk"]


def test_merge_adjacent_chunks_nao_funde_indices_nao_consecutivos():
    entries = [
        ("trecho A", {"source": "nota.md", "chunk": 0}),
        ("trecho B", {"source": "nota.md", "chunk": 5}),
    ]
    out = _merge_adjacent_chunks(entries)
    assert out == ["[nota.md]\ntrecho A", "[nota.md]\ntrecho B"]


def test_merge_adjacent_chunks_nao_funde_fontes_diferentes():
    entries = [
        ("trecho A", {"source": "nota1.md", "chunk": 0}),
        ("trecho A", {"source": "nota2.md", "chunk": 1}),
    ]
    out = _merge_adjacent_chunks(entries)
    assert out == ["[nota1.md]\ntrecho A", "[nota2.md]\ntrecho A"]


def test_merge_adjacent_chunks_sem_indice_passa_intocado():
    entries = [("trecho único", {"source": "nota.md"})]
    assert _merge_adjacent_chunks(entries) == ["[nota.md]\ntrecho único"]
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `pytest tests/test_memory.py -v -k merge`
Expected: FAIL com `ImportError: cannot import name '_merge_adjacent_chunks'` (as funções ainda não existem em `core/memory.py`).

- [ ] **Step 3: Implementar os helpers**

Em `core/memory.py`, inserir depois de `chunk_text()` (depois da linha 56, antes de `def _get_embedder():`):

```python
def _merge_overlap(a: str, b: str) -> str:
    """Funde dois textos cortando o maior sufixo de `a` que é também prefixo de
    `b`. Não assume tamanho fixo de overlap: o `RecursiveCharacterTextSplitter`
    usado em `chunk_text()` respeita separadores e não garante
    `RAG_CHUNK_OVERLAP` caracteres exatos entre chunks vizinhos."""
    limit = min(len(a), len(b))
    for size in range(limit, 0, -1):
        if a[-size:] == b[:size]:
            return a + b[size:]
    return a + b


def _merge_adjacent_chunks(entries: list[tuple[str, dict]]) -> list[str]:
    """Funde chunks consecutivos (`chunk: i`, `chunk: i+1`) da MESMA fonte num
    só bloco `[fonte]\\ntexto`, cortando o overlap. `entries` são pares
    (doc, meta) já filtrados por distância, na ordem de relevância devolvida
    pelo Chroma. Chunks não-adjacentes, de fontes diferentes, ou sem índice de
    chunk nos metadados não se fundem."""
    sources: list[str] = []
    texts: list[str] = []
    last_chunk: dict[str, tuple[int, int]] = {}  # fonte -> (índice do chunk, posição em texts)

    for doc, meta in entries:
        source = (meta or {}).get("source", "?")
        raw_idx = (meta or {}).get("chunk")
        chunk_idx = raw_idx if isinstance(raw_idx, int) else None

        prev = last_chunk.get(source)
        if chunk_idx is not None and prev is not None and prev[0] == chunk_idx - 1:
            pos = prev[1]
            texts[pos] = _merge_overlap(texts[pos], doc)
            last_chunk[source] = (chunk_idx, pos)
            continue

        sources.append(source)
        texts.append(doc)
        if chunk_idx is not None:
            last_chunk[source] = (chunk_idx, len(texts) - 1)

    return [f"[{s}]\n{t}" for s, t in zip(sources, texts, strict=False)]
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `pytest tests/test_memory.py -v`
Expected: PASS em todos os testes, incluindo os pré-existentes (as funções novas ainda não são usadas por `query_memory()`, então nada muda no comportamento de produção).

- [ ] **Step 5: Lint e formatação**

Run: `ruff check core/memory.py tests/test_memory.py && ruff format core/memory.py tests/test_memory.py`

- [ ] **Step 6: Commit**

```bash
git add core/memory.py tests/test_memory.py
git commit -m "feat(rag): funde chunks adjacentes que se sobrepõem por overlap literal"
```

---

### Task 2: Ligar a fusão em `query_memory()`

**Files:**
- Modify: `core/memory.py:159-172` (miolo de `query_memory()`)
- Test: `tests/test_memory.py`

**Interfaces:**
- Consumes: `core.memory._merge_adjacent_chunks(entries: list[tuple[str, dict]]) -> list[str]` (Task 1).
- Produces: `query_memory()` continua com a mesma assinatura pública; o corpo interno passa a fundir chunks adjacentes automaticamente.

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar ao final de `tests/test_memory.py` (depois dos testes de merge que a
Task 1 acrescentou):

```python
def test_query_memory_funde_chunks_adjacentes_da_mesma_fonte(monkeypatch):
    """Chunks vizinhos (chunk 0 e 1) da mesma nota, com overlap, viram um bloco só."""

    class FakeCollection:
        def count(self):
            return 2

        def query(self, **kwargs):
            return {
                "documents": [
                    [
                        "isto é um chunk que termina em ABC",
                        "ABC continua no próximo chunk",
                    ]
                ],
                "metadatas": [
                    [
                        {"source": "nota.md", "chunk": 0},
                        {"source": "nota.md", "chunk": 1},
                    ]
                ],
            }

    monkeypatch.setattr(memory, "_get_collection", lambda: FakeCollection())
    monkeypatch.setattr(
        memory, "_get_embedder", lambda: type("E", (), {"embed_query": lambda self, q: [0.1]})()
    )

    out = memory.query_memory("pergunta qualquer")

    assert out == ["[nota.md]\nisto é um chunk que termina em ABC continua no próximo chunk"]
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `pytest tests/test_memory.py -v -k funde_chunks_adjacentes`
Expected: FAIL — `assert ['[nota.md]\n...ABC', '[nota.md]\nABC...'] == ['[nota.md]\n...ABC continua...']` (dois blocos separados, ainda sem fusão).

- [ ] **Step 3: Ligar a fusão em `query_memory()`**

Em `core/memory.py`, substituir o miolo de `query_memory()` (as linhas depois de `res = collection.query(...)`):

De:
```python
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

Para:
```python
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]

    entries = list(zip(docs, metas, strict=False))
    out = _merge_adjacent_chunks(entries)
    sources = list(dict.fromkeys((meta or {}).get("source", "?") for _doc, meta in entries))
    # As fontes vão para as métricas aqui, onde ainda são estruturadas — o bench
    # nunca deve reparsear as strings "[source]\n…" devolvidas.
    note(chunks=len(out), sources=sources)
    return out
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `pytest tests/test_memory.py -v`
Expected: PASS em todos os testes — incluindo `test_query_memory_registra_etapas_e_fontes` (pré-existente, sem `chunk` nos metadados, continua devolvendo 2 entradas separadas porque `_merge_adjacent_chunks` não funde chunks sem índice).

- [ ] **Step 5: Lint e formatação**

Run: `ruff check core/memory.py tests/test_memory.py && ruff format core/memory.py tests/test_memory.py`

- [ ] **Step 6: Commit**

```bash
git add core/memory.py tests/test_memory.py
git commit -m "feat(rag): query_memory funde chunks adjacentes antes de devolver o contexto"
```

---

### Task 3: Filtro por distância

**Files:**
- Modify: `core/config.py` (nova setting, perto de `RAG_TOP_K`, linha 80)
- Modify: `.env.example` (linha 71, ao lado de `RAG_TOP_K`)
- Modify: `core/memory.py` (novo helper + wiring em `query_memory()`)
- Test: `tests/test_memory.py`

**Interfaces:**
- Consumes: `core.memory._merge_adjacent_chunks` (Task 1/2).
- Produces: `settings.RAG_MAX_DISTANCE: float` (valor provisório `1.0` — recalibrado na Task 5).
- Produces: `core.memory._filter_by_distance(docs: list[str], metas: list[dict], distances: list[float]) -> list[tuple[str, dict]]`.
- Produces: `query_memory()` agora pode devolver `[]` quando todo o top-k está acima do limiar — é o que a Task 4 explora.

- [ ] **Step 1: Adicionar a setting em `core/config.py`**

Depois da linha 80 (`RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "6"))`):

```python
    # Distância máxima (Chroma, espaço cosine — ver `_get_collection()`) para um
    # trecho contar como contexto relevante. Acima disso, é descartado. Valor
    # PROVISÓRIO: calibrado com dados reais na Task 5 deste plano (ver
    # docs/superpowers/specs/2026-08-05-qualidade-rag-roteador-design.md).
    RAG_MAX_DISTANCE: float = float(os.getenv("RAG_MAX_DISTANCE", "1.0"))
```

- [ ] **Step 2: Adicionar a entrada em `.env.example`**

Na seção `# ── RAG (opcional — têm padrão no código) ────────────────────`, depois de `# RAG_TOP_K=6`:

```
# RAG_MAX_DISTANCE=1.0
```

- [ ] **Step 3: Escrever os testes que falham**

Acrescentar ao final de `tests/test_memory.py`:

```python
def test_filter_by_distance_descarta_acima_do_limiar(monkeypatch):
    monkeypatch.setattr(settings, "RAG_MAX_DISTANCE", 0.5)
    docs = ["perto", "longe"]
    metas = [{"source": "a.md"}, {"source": "b.md"}]
    distances = [0.3, 0.9]
    out = memory._filter_by_distance(docs, metas, distances)
    assert out == [("perto", {"source": "a.md"})]


def test_filter_by_distance_mantem_no_limite_exato(monkeypatch):
    monkeypatch.setattr(settings, "RAG_MAX_DISTANCE", 0.5)
    out = memory._filter_by_distance(["x"], [{"source": "a.md"}], [0.5])
    assert out == [("x", {"source": "a.md"})]


def test_filter_by_distance_sem_distancias_mantem_tudo():
    out = memory._filter_by_distance(["a", "b"], [{"source": "x"}, {"source": "y"}], [])
    assert out == [("a", {"source": "x"}), ("b", {"source": "y"})]


def test_query_memory_filtra_por_distancia_e_pode_ficar_vazio(monkeypatch):
    """Com todos os trechos acima do limiar, query_memory devolve [] — has_context
    vira False a jusante em core.chat, o que hoje é estruturalmente impossível."""
    monkeypatch.setattr(settings, "RAG_MAX_DISTANCE", 0.2)

    class FakeCollection:
        def count(self):
            return 1

        def query(self, **kwargs):
            return {
                "documents": [["trecho irrelevante"]],
                "metadatas": [[{"source": "nota.md", "chunk": 0}]],
                "distances": [[0.9]],
            }

    monkeypatch.setattr(memory, "_get_collection", lambda: FakeCollection())
    monkeypatch.setattr(
        memory, "_get_embedder", lambda: type("E", (), {"embed_query": lambda self, q: [0.1]})()
    )

    assert memory.query_memory("pergunta qualquer") == []
```

- [ ] **Step 4: Rodar e confirmar que falha**

Run: `pytest tests/test_memory.py -v -k "filter_by_distance or filtra_por_distancia"`
Expected: FAIL com `AttributeError: module 'core.memory' has no attribute '_filter_by_distance'`.

- [ ] **Step 5: Implementar o filtro e ligá-lo em `query_memory()`**

Em `core/memory.py`, inserir `_filter_by_distance` logo antes de `_merge_overlap` (que a Task 1 criou):

```python
def _filter_by_distance(
    docs: list[str], metas: list[dict], distances: list[float]
) -> list[tuple[str, dict]]:
    """Descarta trechos com distância maior que RAG_MAX_DISTANCE. Se o Chroma não
    devolver distâncias (resposta sem a chave, ou lista vazia), mantém tudo —
    nunca descarta contexto por um bug silencioso de parsing."""
    if not distances:
        return list(zip(docs, metas, strict=False))
    return [
        (doc, meta)
        for doc, meta, dist in zip(docs, metas, distances, strict=False)
        if dist <= settings.RAG_MAX_DISTANCE
    ]
```

E trocar o início do miolo de `query_memory()` (o que a Task 2 deixou):

De:
```python
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]

    entries = list(zip(docs, metas, strict=False))
    out = _merge_adjacent_chunks(entries)
```

Para:
```python
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    distances = (res.get("distances") or [[]])[0]

    entries = _filter_by_distance(docs, metas, distances)
    out = _merge_adjacent_chunks(entries)
```

(A linha `sources = list(dict.fromkeys(...))` logo abaixo não muda — já itera sobre `entries`.)

- [ ] **Step 6: Rodar e confirmar que passa**

Run: `pytest tests/test_memory.py -v`
Expected: PASS em todos, incluindo `test_query_memory_registra_etapas_e_fontes` (sem `distances` na resposta fake → `_filter_by_distance` mantém tudo, comportamento inalterado).

- [ ] **Step 7: Lint e formatação**

Run: `ruff check core/config.py core/memory.py tests/test_memory.py && ruff format core/config.py core/memory.py tests/test_memory.py`

- [ ] **Step 8: Commit**

```bash
git add core/config.py core/memory.py .env.example tests/test_memory.py
git commit -m "feat(rag): filtra contexto por distância (RAG_MAX_DISTANCE, valor provisório)"
```

---

### Task 4: Provar, fim-a-fim, que a rota `cloud` fica alcançável

**Files:**
- Modify: `tests/test_chat.py` (nova seção, depois de `test_send_pergunta_informativa_escala_para_a_nuvem`, linha 113)

**Interfaces:**
- Consumes: a capacidade de `core.memory.query_memory()` devolver `[]` (Task 3) — mas os testes desta task **mockam** `core.memory.query_memory` diretamente, sem depender da implementação real. O que eles provam é a *fiação* entre `core/chat.py` e `core/model_router.py`, que não muda de código nesta task.
- Produces: nenhuma interface nova — são testes de regressão/cobertura.

- [ ] **Step 1: Escrever os testes**

Acrescentar a `tests/test_chat.py`, depois de `test_send_pergunta_informativa_escala_para_a_nuvem` (linha 113) e antes do comentário `# ── Memória / histórico ──`:

```python
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
    monkeypatch.setattr(
        "core.memory.query_memory", lambda message: ["[nota.md]\ntrecho relevante"]
    )
    sess = _session(use_rag=True, use_tools=True)

    out = sess.send("como foi a reunião que você anotou pra mim?")

    assert out == "resposta do modelo"
    assert sess.last_model == "local"
```

- [ ] **Step 2: Rodar e confirmar que passa**

Run: `pytest tests/test_chat.py -v -k "sem_contexto_do_rag or com_contexto_do_rag"`
Expected: **PASS imediato**, sem nenhuma mudança em `core/chat.py` ou `core/model_router.py` — isso confirma o que o spec previu (Objetivo 2: o roteador já estava correto, só nunca recebia `has_context=False`). Se esses testes falharem, **pare**: significa que a fiação entre `chat.py` e `model_router.py` não é o que o spec descreve, e o desenho precisa ser reavaliado antes de continuar.

- [ ] **Step 3: Rodar a suíte inteira de `test_chat.py`**

Run: `pytest tests/test_chat.py -v`
Expected: PASS em todos — os testes novos não interferem nos existentes (usam `use_rag=True` explícito; os demais continuam com `use_rag=False` via `_session()`).

- [ ] **Step 4: Lint e formatação**

Run: `ruff check tests/test_chat.py && ruff format tests/test_chat.py`

- [ ] **Step 5: Commit**

```bash
git add tests/test_chat.py
git commit -m "test(chat): prova fim-a-fim que has_context=False alcança a rota cloud"
```

---

### Task 5: Calibrar `RAG_MAX_DISTANCE` com dados reais

**Pré-requisito:** Ollama rodando localmente, com `qwen3:8b` e `nomic-embed-text` puxados (`ollama pull nomic-embed-text`), e o vault indexado (`python main.py index`). Esta task **não roda em CI** — é investigação manual, na mesma classe de `python main.py bench`.

**Files:**
- Create (temporário, **nunca commitado**): script de calibração no scratchpad.
- Modify: `core/config.py:80` (troca o valor provisório `1.0` pelo calibrado)
- Modify: `.env.example` (troca `1.0` pelo calibrado)

**Interfaces:**
- Consumes: `core.memory._get_collection()`, `core.memory._get_embedder()` (já existentes).
- Produces: valor final de `settings.RAG_MAX_DISTANCE`, documentado no commit desta task com as distâncias observadas.

- [ ] **Step 1: Escrever o script de calibração (não commitar)**

Salvar como `scratch_calibrar_rag.py` na raiz do repo (ou no diretório de scratchpad do agente, se houver um configurado):

```python
# scratch: calibrar RAG_MAX_DISTANCE com distâncias reais do Chroma. NÃO COMMITAR.
from core.memory import _get_collection, _get_embedder

MENSAGENS = {
    # papo-*: context: none — não deveriam ter trecho relevante.
    "papo-saudacao": "oi, tudo bem?",
    "papo-agradecimento": "valeu, obrigado",
    "papo-bom-dia": "bom dia",
    "papo-tchau": "até mais tarde",
    # memoria: sources_include — deveriam vir com a fonte certa no topo.
    "mem-modelo-local": "qual modelo local o projeto usa?",
    "mem-stack": "qual é a stack do Project Jade?",
    "mem-arquitetura-memoria": "onde ficam guardadas as conversas da Jade?",
    "mem-como-usar": "como eu inicio a Jade?",
    "mem-seguranca": "qual é a política de segurança do projeto?",
}

collection = _get_collection()
embedder = _get_embedder()
for case_id, message in MENSAGENS.items():
    q_emb = embedder.embed_query(message)
    res = collection.query(query_embeddings=[q_emb], n_results=6)
    distances = res["distances"][0]
    sources = [m.get("source") for m in res["metadatas"][0]]
    pares = list(zip(sources, [round(d, 4) for d in distances], strict=False))
    print(f"{case_id:30s} {pares}")
```

- [ ] **Step 2: Rodar o script e capturar a saída**

Run: `python scratch_calibrar_rag.py`

Anotar, para cada caso `papo-*`, a **menor** distância observada (o "melhor" resultado que ainda deveria ser rejeitado). Anotar, para cada caso `mem-*`, a distância da fonte esperada (`sources_include` do respectivo caso em `bench/cases/memoria.yaml`) — o "pior" resultado que ainda deveria ser aceito.

- [ ] **Step 3: Escolher o corte**

Se o maior valor do grupo `mem-*` (deveria manter) for menor que o menor valor do grupo `papo-*` (deveria descartar), os grupos separam limpo — escolher `RAG_MAX_DISTANCE` no meio dos dois. Se houver sobreposição, escolher o valor que minimiza classificações erradas nos dois grupos, e registrar explicitamente essa sobreposição no commit desta task (não escondê-la) — é o Risco já previsto no spec.

- [ ] **Step 4: Atualizar o valor calibrado**

Em `core/config.py`, trocar o `"1.0"` provisório pelo número escolhido e remover a palavra "PROVISÓRIO" do comentário:

```python
    # Distância máxima (Chroma, espaço cosine — ver `_get_collection()`) para um
    # trecho contar como contexto relevante. Acima disso, é descartado.
    # Calibrado em bench/cases/papo.yaml (context: none) vs bench/cases/memoria.yaml
    # (sources_include) — ver docs/superpowers/specs/2026-08-05-qualidade-rag-roteador-design.md.
    RAG_MAX_DISTANCE: float = float(os.getenv("RAG_MAX_DISTANCE", "<VALOR_CALIBRADO>"))
```

Em `.env.example`, trocar `# RAG_MAX_DISTANCE=1.0` por `# RAG_MAX_DISTANCE=<VALOR_CALIBRADO>`.

- [ ] **Step 5: Apagar o script de calibração**

Run: `rm scratch_calibrar_rag.py` (ou equivalente do shell em uso) — ele não é código de produção nem teste; não pode ser commitado.

- [ ] **Step 6: Rodar a suíte para confirmar que nada quebrou**

Run: `pytest tests/test_memory.py tests/test_chat.py tests/test_model_router.py -v`
Expected: PASS — os testes das Tasks 1-4 fixam `RAG_MAX_DISTANCE` via `monkeypatch` ou não dependem de distância real, então trocar o default não os afeta.

- [ ] **Step 7: Commit**

```bash
git add core/config.py .env.example
git commit -m "$(cat <<'EOF'
fix(rag): calibra RAG_MAX_DISTANCE com distâncias reais do Chroma

Distâncias observadas (nomic-embed-text, cosine): grupo papo-* (deveria
descartar) vs grupo memoria (deveria manter) — ver detalhes no corpo do commit
ou no relatório da task de implementação.
EOF
)"
```

---

### Task 6: Validação final — quality gate e rerun do bench

**Files:**
- Nenhum arquivo de produção. Esta task só valida e gera um relatório novo em `bench/reports/`.

**Interfaces:**
- Consumes: tudo das Tasks 1-5.
- Produces: `bench/reports/<timestamp>[-tag].json` e `.md` — o rerun pós-implementação, comparado ao baseline via a coluna de Delta que `bench/report.py::load_previous()` já calcula automaticamente (pega o `.json` mais recente na pasta).

- [ ] **Step 1: Suíte de testes completa**

Run: `pytest`
Expected: PASS em tudo (nenhum teste pré-existente quebrou).

- [ ] **Step 2: Lint e formatação em tudo**

Run: `ruff check . && ruff format .`
Expected: sem erros; se `ruff format` reescrever algum arquivo, revisar o diff antes de seguir.

- [ ] **Step 3: SAST**

Run: `bandit -c pyproject.toml -r core tools interfaces bench main.py`
Expected: sem findings novos.

- [ ] **Step 4: Vulnerabilidades de dependências**

Run: `pip-audit -r requirements.txt --ignore-vuln PYSEC-2026-311`
Expected: sem vulnerabilidades novas (a exceção já é a mesma do baseline do projeto — ver `SECURITY.md`).

- [ ] **Step 5: Rerun do bench**

Pré-requisito: Ollama rodando, vault indexado (`python main.py index` se necessário).

Run: `python main.py bench --tag qualidade-rag-roteador`
Expected: escreve um novo par `.json`/`.md` em `bench/reports/`, com Delta calculado contra `bench/reports/2026-08-04-001654-baseline.json` (o mais recente antes deste run).

- [ ] **Step 6: Ler o relatório novo e confirmar a correção**

Abrir o `.md` gerado no Step 5. Confirmar:
- `context_precision` (Precisão de contexto, casos `context: none`) subiu de **0,0%** — os 4 casos `papo-*` agora devem vir sem trechos, ou pelo menos deixar de vir sempre com 6.
- A distribuição real de rotas: se `ANTHROPIC_API_KEY` estiver configurada nesta máquina, `cloud` deve deixar de ser **0**; se não estiver, documentar isso explicitamente no relatório (mesma transparência que o baseline já pratica), já que sem chave a rota `cloud` continua inatingível por decisão do próprio `cloud_available()` — não é uma regressão desta task.
- Nenhuma métrica de qualidade que já estava correta (ex.: `recall@k`) regrediu sem explicação.

Se algo regrediu sem explicação plausível, **pare** e investigue antes de prosseguir — não commitar um relatório que esconde uma regressão.

- [ ] **Step 7: Commit do relatório**

```bash
git add bench/reports/
git commit -m "$(cat <<'EOF'
chore(bench): relatório pós-correção do RAG e do roteador dual-model

Rerun após o subprojeto #3 (limiar de distância + dedup de contexto).
Comparar com bench/reports/2026-08-04-001654-baseline.md para o Delta.
EOF
)"
```

- [ ] **Step 8: Push da branch**

Run: `git push -u origin feat/qualidade-rag-roteador`

(Abrir o PR e mergear fica para a skill `finishing-a-development-branch` — decisão do humano, não desta task.)

## Notas para quem executa

**A ordem das tasks é obrigatória até a Task 4.** Task 2 consome Task 1; Task 3 consome Task 2. A Task 4 pode, em teoria, ser escrita a qualquer momento depois da Task 1 (ela mocka `query_memory` diretamente), mas fica depois da Task 3 porque é isso que ela valida: que a implementação real, uma vez capaz de devolver `[]`, não exige nenhuma mudança em `core/chat.py` ou `core/model_router.py`.

**A Task 5 precisa de Ollama e do vault indexado.** Se não houver Ollama disponível no ambiente de execução, pare na Task 4 e sinalize isso — não invente um valor de calibração sem medir; o valor provisório `1.0` fixado na Task 3 não é a entrega final.

**Se um teste pré-existente quebrar em qualquer task**, pare. O contrato de `query_memory()` não muda — é uma restrição global deste plano (ver Global Constraints). Reverta a alteração e reavalie o passo que causou a quebra.

**Se o rerun do bench (Task 6) sair "bonito demais"** (100% em tudo), desconfie antes de comemorar: confirme que o vault está de fato indexado e que `RAG_MAX_DISTANCE` está mesmo sendo lido de `core.config.settings` (não um valor hardcoded esquecido de um teste).
