"""Testes do RAG que NÃO dependem do Ollama/embeddings (rodam no CI).

Cobrem o filtro de notas do vault (privacidade) e o chunking.
"""

from core import memory
from core.config import settings
from core.memory import _merge_adjacent_chunks, _merge_overlap, chunk_text, iter_vault_notes


def test_iter_vault_notes_pula_pastas_ignoradas(tmp_path):
    # Notas legítimas.
    (tmp_path / "nota1.md").write_text("conteúdo 1", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "nota2.md").write_text("conteúdo 2", encoding="utf-8")

    # Coisas que JAMAIS devem ser indexadas.
    obs = tmp_path / ".obsidian"
    obs.mkdir()
    (obs / "workspace.md").write_text("segredo do editor", encoding="utf-8")
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "config.md").write_text("interno", encoding="utf-8")

    encontrados = {p.name for p in iter_vault_notes(tmp_path)}
    assert encontrados == {"nota1.md", "nota2.md"}


def test_chunk_text():
    assert chunk_text("") == []
    assert chunk_text("frase curta") == ["frase curta"]
    # Texto longo deve gerar mais de um chunk.
    longo = "palavra " * 500
    assert len(chunk_text(longo)) > 1


def test_iter_vault_notes_pula_relatorios_do_benchmark(tmp_path):
    """bench/reports/*.md nunca pode ser indexado: contaminaria o recall@k que o
    próprio benchmark mede (ver core.config.settings.VAULT_IGNORE)."""
    (tmp_path / "nota.md").write_text("conteúdo legítimo", encoding="utf-8")
    reports = tmp_path / "bench" / "reports"
    reports.mkdir(parents=True)
    (reports / "2026-08-03-120000.md").write_text(
        "relatório com sources_include e mensagens dos casos", encoding="utf-8"
    )

    encontrados = {p.name for p in iter_vault_notes(tmp_path)}
    assert encontrados == {"nota.md"}


def test_iter_inclui_txt_e_pula_notas_internas(tmp_path):
    (tmp_path / "doc.md").write_text("x", encoding="utf-8")
    (tmp_path / "notas.txt").write_text("y", encoding="utf-8")
    (tmp_path / settings.MOOD_NOTE).write_text("humor interno", encoding="utf-8")
    nomes = {p.name for p in iter_vault_notes(tmp_path)}
    assert "doc.md" in nomes
    assert "notas.txt" in nomes  # .txt também é indexado
    assert settings.MOOD_NOTE not in nomes  # nota interna da Jade fica fora do RAG


def test_index_state_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "CHROMA_DB_PATH", str(tmp_path / "chroma"))
    memory._save_state({"a.md": 1.5, "b.txt": 2.0})
    assert memory._load_state() == {"a.md": 1.5, "b.txt": 2.0}


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


def test_merge_adjacent_chunks_funde_quando_chunk_seguinte_vem_antes():
    """O Chroma devolve por relevância, não por índice de chunk: o chunk 1 pode
    aparecer ANTES do chunk 0 na lista `entries`. A fusão tem que funcionar nos
    dois sentidos, senão o overlap fica duplicado no prompt sem gerar erro."""
    entries = [
        ("ABC continua no próximo chunk", {"source": "nota.md", "chunk": 1}),
        ("isto é um chunk que termina em ABC", {"source": "nota.md", "chunk": 0}),
    ]
    out = _merge_adjacent_chunks(entries)
    assert out == ["[nota.md]\nisto é um chunk que termina em ABC continua no próximo chunk"]


def test_merge_adjacent_chunks_funde_cadeia_de_tres_em_ordem_embaralhada():
    """Cadeia de 3 chunks consecutivos (0, 1, 2) da mesma fonte, chegando na
    ordem 2, 0, 1 — nem ascendente nem descendente. Prova que a fusão não
    depende de nenhuma ordem de chegada específica, só do índice do chunk."""
    entries = [
        ("cinco seis sete", {"source": "nota.md", "chunk": 2}),
        ("um dois tres", {"source": "nota.md", "chunk": 0}),
        ("tres quatro cinco", {"source": "nota.md", "chunk": 1}),
    ]
    out = _merge_adjacent_chunks(entries)
    assert out == ["[nota.md]\num dois tres quatro cinco seis sete"]


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


def test_query_memory_passa_include_explicito_para_o_chroma(monkeypatch):
    """`include` não pode depender do default do Chroma: se um upgrade de
    dependência mudar esse default, o filtro por distância vira um no-op
    silencioso. Fixamos o contrato explicitamente na chamada."""
    from core import metrics

    captured_kwargs: dict = {}

    class FakeCollection:
        def count(self):
            return 1

        def query(self, **kwargs):
            captured_kwargs.update(kwargs)
            return {
                "documents": [["trecho"]],
                "metadatas": [[{"source": "nota.md", "chunk": 0}]],
                "distances": [[0.1]],
            }

    monkeypatch.setattr(memory, "_get_collection", lambda: FakeCollection())
    monkeypatch.setattr(
        memory, "_get_embedder", lambda: type("E", (), {"embed_query": lambda self, q: [0.1]})()
    )

    with metrics.capture():
        memory.query_memory("pergunta qualquer")

    assert captured_kwargs.get("include") == ["documents", "metadatas", "distances"]


def test_query_memory_observa_quando_distances_ausente(monkeypatch):
    """Se `documents` vier mas `distances` não, isso é uma degradação do
    contrato esperado (ver _filter_by_distance) — precisa ficar observável no
    bench, não silenciosamente mascarada."""
    from core import metrics

    class FakeCollection:
        def count(self):
            return 1

        def query(self, **kwargs):
            return {
                "documents": [["trecho"]],
                "metadatas": [[{"source": "nota.md", "chunk": 0}]],
                # sem "distances" de propósito
            }

    monkeypatch.setattr(memory, "_get_collection", lambda: FakeCollection())
    monkeypatch.setattr(
        memory, "_get_embedder", lambda: type("E", (), {"embed_query": lambda self, q: [0.1]})()
    )

    with metrics.capture() as turn:
        out = memory.query_memory("pergunta qualquer")

    assert out == ["[nota.md]\ntrecho"]  # sem distances, mantém tudo (defensivo)
    assert turn.meta["rag_distances_missing"] is True


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
