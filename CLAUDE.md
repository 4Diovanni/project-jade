# CLAUDE.md — Guia do projeto para o Claude Code

Contexto que todo agente deve carregar ao trabalhar no **Project Jade**.

## O que é
Assistente pessoal **agentic**, *privacy-first*, rodando localmente. Um LLM
orquestra **tools** (habilidades) para agir sobre Obsidian, WhatsApp, voz,
Spotify, e-mail e o SO. Memória de longo prazo via **RAG** sobre o vault do
Obsidian. Documento-fonte da arquitetura: `projeto_jade_arquitetura.md`.

## Stack
- **Backend:** Python 3.11+ · FastAPI · LangChain
- **LLM:** Ollama (local, padrão) ou OpenAI/Anthropic/Gemini — escolhido por `JADE_LLM_PROVIDER`
- **Memória:** SQLite (histórico) + ChromaDB (vetores do Obsidian)
- **Config:** tudo via `.env` (ver `.env.example`), lido por `core/config.py`

## Mapa do repositório
- `core/` — cérebro. `config.py` (settings), `llm_engine.py` (factory de LLM),
  `memory.py` (RAG/ChromaDB + histórico), `agent_router.py` (monta o agente e
  decide a tool).
- `tools/` — habilidades. `base.py` define o contrato `JadeTool`; `registry.py`
  registra as tools disponíveis. **Ponto de extensão principal do projeto.**
- `interfaces/` — `api.py` (FastAPI), `voice_service.py`, `whatsapp_bot/`.
- `database/` — gerado em runtime; **nunca** versionado.

## Convenções
- Identificadores de código em inglês; comentários e docs em PT-BR.
- Configuração **sempre** via `core.config.settings` — nunca `os.getenv` espalhado.
- Segredos só no `.env` (gitignored). Nunca commitar chaves.
- Nova capacidade = nova tool em `tools/` implementando `JadeTool` e registrada
  em `tools/registry.py`. Ver a skill **add-jade-tool**.
- O vault do Obsidian é a raiz do repo (`OBSIDIAN_VAULT_PATH=.`). Ao indexar,
  ignore `settings.VAULT_IGNORE` (.obsidian, .claude, database, código...).

## Skills disponíveis (`.claude/skills/`)
- **add-jade-tool** — scaffold de uma nova tool + registro no roteador.
- **sync-obsidian-rag** — (re)indexar o vault no ChromaDB para o RAG.

## Estado atual
Ambiente preparado (esqueleto + skills + git/GitHub). Implementação das fases
ainda por fazer — os módulos são stubs com `TODO`. Começar pela **Fase 1**.
