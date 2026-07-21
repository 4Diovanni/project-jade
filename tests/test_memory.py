"""Testes do RAG que NÃO dependem do Ollama/embeddings (rodam no CI).

Cobrem o filtro de notas do vault (privacidade) e o chunking.
"""

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
