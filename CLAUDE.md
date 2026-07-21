# CLAUDE.md — Guia do projeto para o Claude Code

Contexto que todo agente deve carregar ao trabalhar no **Project Jade**.

## O que é
Assistente pessoal **agentic**, *privacy-first*, rodando localmente. Um LLM
orquestra **tools** (habilidades) para agir sobre Obsidian, WhatsApp, voz,
Spotify, e-mail e o SO. Memória de longo prazo via **RAG** sobre o vault do
Obsidian. Documento-fonte da arquitetura: `projeto_jade_arquitetura.md`.

## Escopo & Visão (ler `projeto_jade_arquitetura.md` §8)
- **Memória = o Obsidian do usuário.** Toda conversa vira nota `.md` no vault
  (`core/journal.py`), com frontmatter (título/data/tags) + `#conversa/AAAA-MM-DD`
  e link `[[Jade — Memória]]` — o grafo conecta por grupo/data/título. Notas são
  reindexadas no RAG (histórico = memória de longo prazo).
- **Meta futura:** "pensamento próprio" — emular tom/ideias do usuário a partir
  das conversas acumuladas.
- **Roteamento dual-model (futuro):** llama3 (local) p/ ações comuns/rastreáveis
  (ex.: renomear pasta); Claude (nuvem) p/ complexo/informativo (ex.: receita).

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
- `pip-audit -r requirements.txt --ignore-vuln PYSEC-2026-311` — vulnerabilidades de deps (a exceção é o CVE do servidor HTTP do ChromaDB, que não usamos; ver SECURITY.md).
- `pytest` — testes de fumaça (não dependem do LLM/Ollama).

Para swallow de exceção use `contextlib.suppress` (Bandit rejeita try/except/pass).
Segredos só no `.env`. CI: `ci.yml` (lint+test), `security.yml` (bandit/pip-audit/gitleaks), `codeql.yml`.

## Estado atual
**Fases 1 e 2 concluídas.**
- Fase 1: LLM (`core/llm_engine.py`), chat com persona+histórico (`core/chat.py`),
  CLI e endpoints `/chat` `/reset` `/health`.
- Fase 2 (RAG do Obsidian): `core/memory.py` indexa o vault no **ChromaDB** com
  **embeddings via Ollama** (`nomic-embed-text`, sem PyTorch); `ChatSession`
  injeta os trechos recuperados (RAG-augmented chat, com fallback p/ chat puro).
  Comandos: `python main.py index` e endpoints `/index` `/search`.
- Requer Ollama + `ollama pull llama3` + `ollama pull nomic-embed-text`.
- **Decisão de design:** agente multi-tool (`core/agent_router.py`) fica para a
  Fase 4 (llama3 não faz tool-calling confiável); Fase 2 usa RAG direto no chat.

**Próximo:** Fase 3 (WhatsApp + voz).

## Workflow de git (OBRIGATÓRIO)
Nunca commitar direto na `main` (branch protection ativa). Toda mudança: criar
branch (`feat/…`) → commit → `git push -u origin <branch>` → `gh pr create` →
CI/Security/CodeQL verdes → `gh pr merge`.
