---
name: sync-obsidian-rag
description: (Re)indexa as notas do vault do Obsidian no ChromaDB para o RAG do Jade, respeitando os caminhos ignorados. Use ao implementar/rodar a indexação da memória, depois de adicionar notas, ou ao depurar por que o Jade não "lembra" de algo do vault.
---

# Sincronizar o Obsidian com o RAG (ChromaDB)

A memória de longo prazo do Jade vem das notas do Obsidian, convertidas em
vetores e guardadas no ChromaDB. Esta skill cobre indexar e consultar.

## Contexto importante
- O **vault é a raiz do repositório** (`OBSIDIAN_VAULT_PATH=.` no `.env`).
- Por isso, **nunca indexe tudo**: pule `settings.VAULT_IGNORE`
  (`.obsidian`, `.claude`, `database`, código-fonte, `__pycache__`...).
  A função `core.memory.iter_vault_notes()` já aplica esse filtro — sempre
  itere as notas por ela.
- Caminhos e chaves vêm de `core.config.settings`, não de `os.getenv`.

## Implementar a indexação (`core.memory.reindex_vault`)
1. Para cada nota de `iter_vault_notes()`: ler o `.md`, dividir em *chunks*
   (ex.: `RecursiveCharacterTextSplitter`, ~500–1000 chars com overlap).
2. Gerar **embeddings** — local com `sentence-transformers`
   (`all-MiniLM-L6-v2`) para manter *privacy-first*, ou os embeddings do
   provider ativo.
3. *Upsert* dos chunks numa coleção Chroma persistente em
   `settings.CHROMA_DB_PATH`. Use o caminho relativo da nota como metadado
   (`source`) e um id estável por chunk para reindexações idempotentes.
4. Retorne o número de notas indexadas.

## Implementar a consulta (`core.memory.query_memory`)
- Embedar a pergunta, buscar os `k` chunks mais próximos na coleção e
  devolver os textos (com o `source`) para o agente.

## Rodar / validar
```bash
python -c "from core.memory import reindex_vault; print(reindex_vault(), 'notas indexadas')"
python -c "from core.memory import query_memory; print(query_memory('o que anotei sobre X'))"
```

## Ao depurar "o Jade não lembra"
1. `iter_vault_notes()` está retornando as notas esperadas? (cheque o filtro
   `VAULT_IGNORE` e `OBSIDIAN_VAULT_PATH`).
2. A coleção Chroma foi persistida no `CHROMA_DB_PATH` e reaberta na consulta?
3. As notas novas foram reindexadas depois de criadas? A indexação não é
   automática — rode `reindex_vault()` (ou agende-o).
