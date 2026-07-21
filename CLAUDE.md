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

- Fase 3 (voz): `interfaces/voice_service.py` — STT local `faster-whisper`
  (sem PyTorch) + TTS `edge-tts` (padrão) ou `pyttsx3` (offline). CLI
  `python main.py say "..."` e `transcribe <audio>`; endpoints `/voice/transcribe`
  `/voice/tts` `/voice/chat`. **WhatsApp adiado** (cliente não-oficial, risco de
  ban; será serviço Node em `interfaces/whatsapp_bot/`).

- Fase 4 (As Mãos — em progresso): `core/agent_router.py` faz **roteamento
  determinístico** (cada tool declara `trigger_hints` e valida em `accepts()`;
  sem depender de tool-calling do llama3). `tools/system_tool.py` = controle do
  SO (abrir apps de **whitelist**, volume via teclas de mídia, busca web);
  `ChatSession` roteia p/ tool antes do RAG. Falta: Spotify e e-mail.

- **Roteador dual-model** (`core/model_router.py`): `ChatSession` decide entre
  **llama3 (local)** e **Claude (nuvem)** por turno. Heurística determinística:
  dados pessoais/RAG e conversa comum → local (privacidade); perguntas
  informativas/complexas → Claude. Só escala se houver `ANTHROPIC_API_KEY`
  (senão fica 100% local). Model default `claude-opus-4-8` (via `langchain-anthropic`;
  **não** passar `temperature` — Opus 4.8 dá 400). `ANTHROPIC_API_KEY` vem do
  console.anthropic.com, ≠ assinatura Claude Pro.

- **Personalidade & memória viva:** a Jade é uma **IA feminina** com caráter e
  emoções (`core/persona.py`). `core/mood.py` = humor persistente por heurística
  (rude/gentil/desculpa → nível em `[-5,+5]`, nota `Jade — Humor.md`), injetado no
  system prompt. `core/profile.py` = perfil do usuário (`USER_NAME`, default
  "Giovanni") em `Sobre o Usuário.md`, aprendido via LLM ao encerrar conversa.
  `core/journal.py` liga conversas por tema (`[[Relacionadas]]`) e indexa cada
  conversa no RAG (memória entre chats). System prompt montado por turno.
- **Auto-sync do vault** (`core/memory.py sync_vault`): `ChatSession` indexa
  incrementalmente (`.md`/`.txt`, por mtime, estado em `database/index_state.json`)
  arquivos novos/alterados na 1ª busca de cada sessão — largar arquivo no vault
  "só funciona". Notas internas da Jade (humor/perfil/personalidade) ficam fora do RAG.

**Próximo:** Spotify e e-mail (Fase 4) · WhatsApp.

## Workflow de git (OBRIGATÓRIO)
Nunca commitar direto na `main` (branch protection ativa). Toda mudança: criar
branch (`feat/…`) → commit → `git push -u origin <branch>` → `gh pr create` →
CI/Security/CodeQL verdes → `gh pr merge`.
