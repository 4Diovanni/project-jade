"""Testes do RAG que NÃO dependem do Ollama/embeddings (rodam no CI).

Cobrem o filtro de notas do vault (privacidade) e o chunking.
"""

from core import memory
from core.config import settings
from core.memory import chunk_text, iter_vault_notes


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
