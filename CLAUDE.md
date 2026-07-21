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

## Qualidade & Segurança (obrigatório antes de commitar)
Pipeline em `.github/workflows/` + `.pre-commit-config.yaml`. Rode localmente:
- `ruff check . && ruff format .` — lint + formatação (config em `pyproject.toml`).
- `bandit -c pyproject.toml -r core tools interfaces main.py` — SAST.
- `pip-audit -r requirements.txt` — vulnerabilidades de deps.
- `pytest` — testes de fumaça (não dependem do LLM/Ollama).

Para swallow de exceção use `contextlib.suppress` (Bandit rejeita try/except/pass).
Segredos só no `.env`. CI: `ci.yml` (lint+test), `security.yml` (bandit/pip-audit/gitleaks), `codeql.yml`.

## Estado atual
**Fase 1 concluída:** LLM real conectado (`core/llm_engine.py`), motor de
conversa com persona e histórico (`core/chat.py`), CLI (`python main.py chat`)
e endpoints `/chat` `/reset` `/health`. Sem tools ainda — chat puro.
Para rodar de verdade: Ollama instalado + `ollama pull llama3` (ou provider de
nuvem com chave no `.env`). **Próximo:** Fase 2 (ChromaDB + RAG do Obsidian +
roteamento agentic em `core/agent_router.py`).
