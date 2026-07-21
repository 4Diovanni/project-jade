"""Testes do diário de conversas — puro I/O de arquivo, sem Ollama (CI-safe)."""

from datetime import datetime

from core.journal import ConversationJournal


def test_journal_cria_nota_com_frontmatter_e_transcricao(tmp_path):
    journal = ConversationJournal(vault=tmp_path, when=datetime(2026, 7, 21, 15, 30, 0))
    path = journal.record("Como você se chama?", "Eu sou o Jade.")

    # Nota criada na subpasta de conversas.
    assert path.exists()
    assert path.parent.name == "Conversas"
    assert path.name.startswith("2026-07-21_153000")

    conteudo = path.read_text(encoding="utf-8")
    assert 'title: "Como você se chama?"' in conteudo
    assert "data: 2026-07-21" in conteudo
    assert "tags: [conversa, jade]" in conteudo
    assert "#conversa/2026-07-21" in conteudo
    assert "**Você:** Como você se chama?" in conteudo
    assert "**Jade:** Eu sou o Jade." in conteudo

    # Hub (MOC) criado para o grafo do Obsidian.
    assert (tmp_path / "Jade — Memória.md").exists()


def test_journal_acumula_turnos_no_mesmo_arquivo(tmp_path):
    journal = ConversationJournal(vault=tmp_path)
    p1 = journal.record("primeira", "resposta 1")
    p2 = journal.record("segunda", "resposta 2")

    assert p1 == p2  # mesma sessão, mesmo arquivo
    conteudo = p2.read_text(encoding="utf-8")
    assert "turnos: 2" in conteudo
    assert "resposta 1" in conteudo
    assert "resposta 2" in conteudo


def test_journal_nome_de_arquivo_sem_ponto_final(tmp_path):
    # Título terminando em ponto não deve gerar "..md" (inválido no Windows).
    journal = ConversationJournal(vault=tmp_path)
    path = journal.record("Uma dica rápida.", "claro")
    assert not path.name.endswith("..md")
    assert path.name.endswith(".md")
