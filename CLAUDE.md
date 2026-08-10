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
- **Roteamento dual-model (futuro):** modelo local p/ ações comuns/rastreáveis
  (ex.: renomear pasta); Claude (nuvem) p/ complexo/informativo (ex.: receita).

## Stack
- **Backend:** Python 3.11+ · FastAPI · LangChain
- **LLM:** Ollama (local, padrão) ou OpenAI/Anthropic/Gemini — escolhido por `JADE_LLM_PROVIDER`
- **Modelo local:** `qwen3:8b` (tool-calling nativo, 32K de contexto, PT-BR sólido).
  `OLLAMA_NUM_CTX=10240` é o teto para ele caber 100% na VRAM de uma GPU de 8 GB;
  acima disso o Ollama joga camadas na CPU e a geração cai pela metade. O modo
  *thinking* fica **desligado** (`OLLAMA_THINKING=false`) — ligado, ele raciocina
  antes de responder e as tags `<think>` poluem a fala da Jade.
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
- **Leitura ≠ escrita.** `OBSIDIAN_VAULT_PATH=.` é o que a Jade **lê** (a raiz do
  repo, para ela conhecer os próprios docs); `JADE_NOTES_DIR=obsidian_notes` é
  onde ela **escreve** (conversas, humor, perfil, áudios). São separados porque
  `obsidian_notes/` é gitignorado — escrever na raiz jogaria conversas pessoais
  dentro do git. Ao indexar, ignore `settings.VAULT_IGNORE` (.obsidian, .claude,
  database, pastas de código, `docs/`, caches...).

## Skills disponíveis (`.claude/skills/`)
- **add-jade-tool** — scaffold de uma nova tool + registro no roteador.
- **sync-obsidian-rag** — (re)indexar o vault no ChromaDB para o RAG.

## Qualidade & Segurança (obrigatório antes de commitar)
Pipeline em `.github/workflows/` + `.pre-commit-config.yaml`. Rode localmente:
- `ruff check . && ruff format .` — lint + formatação (config em `pyproject.toml`).
- `bandit -c pyproject.toml -r core tools interfaces bench main.py` — SAST.
- `pip-audit -r requirements.txt --ignore-vuln PYSEC-2026-311` — vulnerabilidades de deps (a exceção é o CVE do servidor HTTP do ChromaDB, que não usamos; ver SECURITY.md).
- `pytest` — testes de fumaça (não dependem do LLM/Ollama).
- `python main.py bench` — benchmark de desempenho e qualidade das decisões
  (exige Ollama; **não** roda no CI). Escreve `bench/reports/`, com delta contra
  a execução anterior. Ver `docs/superpowers/specs/2026-08-03-regua-performance-jade-design.md`.

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
- Requer Ollama + `ollama pull qwen3:8b` + `ollama pull nomic-embed-text`.
- **Decisão de design:** agente multi-tool (`core/agent_router.py`) fica para a
  Fase 4 (o llama3 de então não fazia tool-calling confiável); Fase 2 usa RAG
  direto no chat.

- Fase 3 (voz): `interfaces/voice_service.py` — STT local `faster-whisper`
  (`WHISPER_MODEL=small` + `vad_filter`/`beam_size`/`initial_prompt` para
  acurácia — calibrado depois de erros como "toque" no lugar de "toca") + TTS
  `edge-tts` (padrão) ou `pyttsx3` (offline). CLI `python main.py say "..."` e
  `transcribe <audio>`; endpoints `/voice/transcribe` `/voice/tts`
  `/voice/chat`. **WhatsApp adiado** (cliente não-oficial, risco de ban; será
  serviço Node em `interfaces/whatsapp_bot/`).
- **Wake-word "Ok Jade"** (`interfaces/wakeword_service.py`,
  `python main.py listen`): escuta contínua local via **openWakeWord**,
  desligada por padrão (`JADE_WAKEWORD_ENABLED=false`) porque exige um modelo
  custom treinado à parte — não existe "ok jade" pronto (openWakeWord só tem
  modelos em inglês). Ver `docs/wakeword_treino.md` (passo a passo + aviso
  sobre o gerador de dados sintéticos ser só em inglês) e
  `docs/superpowers/specs/2026-08-09-wakeword-precisao-voz-design.md`.
  Endpointing por energia (RMS) em vez de `webrtcvad`: a lib exige compilar
  extensão C e falha sem Visual C++ Build Tools no Windows. Dois modos: como
  processo próprio (`python main.py listen`, sessão de chat independente,
  como o CLI) ou **integrado à API** — com `JADE_WAKEWORD_ENABLED=true` e o
  servidor rodando, `_startup_wakeword` (`interfaces/api.py`) sobe a escuta
  numa thread de fundo usando a mesma sessão/lock de `/chat`; cada turno é
  distribuído pra toda aba de `/ws/chat` conectada (`_broadcast`), o orb
  reage (`listening`/`thinking`/`speaking`) e a fala sai pelo `<audio>` do
  navegador. Foco de janela do navegador segue fora de escopo. **Dependências
  em `requirements-wakeword.txt`, fora do `requirements.txt` padrão** —
  `openwakeword` puxa `tflite-runtime` no Linux sem wheel pra Python 3.12+,
  quebraria o CI; instale com `pip install -r requirements-wakeword.txt` só
  se for usar o recurso.

- Fase 4 (As Mãos — em progresso): `core/agent_router.py` faz **roteamento
  determinístico** (cada tool declara `trigger_hints` e valida em `accepts()`;
  sem depender de tool-calling do LLM). `tools/system_tool.py` = controle do
  SO (abrir apps de **whitelist**, volume via teclas de mídia, busca web);
  `ChatSession` roteia p/ tool antes do RAG. Falta: e-mail.
- **Spotify:** `SPOTIFY_CLIENT_ID`/`SPOTIFY_CLIENT_SECRET` em `core/config.py`
  (settings); `core/spotify.py` = OAuth (com `state` anti-CSRF), sync da
  biblioteca (Curtidas + playlists) e reprodução via Spotify Connect;
  `core/spotify_db.py` = cache local em SQLite; `tools/spotify_tool.py` =
  roteamento determinístico ("toca/pesquisa/sincroniza"); rotas
  `/spotify/login` `/callback` `/status` `/library` `/sync` em
  `interfaces/api.py`; aba própria no frontend (`interfaces/frontend/spotify.js`).

- **Roteador dual-model** (`core/model_router.py`): `ChatSession` decide entre
  **Qwen3 (local)** e **Claude (nuvem)** por turno. Heurística determinística:
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
- **Régua de performance** (`core/metrics.py` + `bench/`): instrumentação por
  etapa com custo zero fora do benchmark, e casos declarativos que medem as
  **decisões** da Jade (rota, tool, recall@k do RAG) de forma determinística.
  O baseline vive em `bench/reports/`.

**Próximo:** e-mail (Fase 4) · WhatsApp.

## Workflow de trabalho (OBRIGATÓRIO — Issue → branch → PR)
Vale para **qualquer agente, de qualquer modelo**, e para humanos. Nada entra na
`main` sem Issue e sem PR. Regra de ouro: **nenhum trabalho sem Issue, nenhum PR
sem `Closes #<n>`.**

1. **Issue primeiro.** Toda tarefa — *Correção*, *Melhoria* ou *Nova função* —
   nasce como Issue no GitHub, criada **antes** de escrever código:
   `gh issue create --title "<tipo>: <resumo>" --label <label> --body "..."`
   - Título no mesmo padrão do commit (`fix:`, `feat:`, `docs:`, `refactor:`,
     `chore:`), em PT-BR.
   - Corpo com **Contexto/Problema**, **Proposta** e **Critérios de aceite**.
   - Labels: `bug` (correção) · `enhancement` (melhoria/nova função) ·
     `documentation` (docs).
   - Entrega grande = uma Issue guarda-chuva + Issues filhas. Nunca uma Issue
     genérica cobrindo várias entregas independentes.
   - Se o usuário pedir algo direto no chat, **abra a Issue mesmo assim** — ela é
     o registro rastreável do pedido.
   - **Prioridade obrigatória.** Toda Issue nova recebe, na criação, uma label
     de prioridade e é adicionada ao Project
     [Project Jade — Backlog](https://github.com/users/4Diovanni/projects/3)
     (campo "Prioridade" espelha a label):
     - `P0-critico` — bug ativo ou bloqueio que afeta o uso diário; ataca primeiro.
     - `P1-alta` — próximo da visão do projeto (`projeto_jade_arquitetura.md` §8)
       ou melhora experiência central de uso.
     - `P2-media` — importante, mas não bloqueia nada nem quebra experiência atual.
     - `P3-baixa` — polimento; vale fazer, sem urgência.
     `gh issue list --label P0-critico` (trocando a label) dá a fila de trabalho
     sem precisar abrir o board.
2. **Branch a partir da `main` atualizada**, nomeada pela Issue: `fix/<slug>`,
   `feat/<slug>`, `docs/<slug>`. Nunca commitar direto na `main` (branch
   protection ativa).
3. **Commits** pequenos, em PT-BR, no formato Conventional Commits.
4. **PR citando a Issue** — obrigatório. A primeira linha do corpo traz a
   palavra-chave de fechamento, para o GitHub linkar e fechar a Issue no merge:
   `Closes #<n>` (ou `Fixes #<n>` em correções). PR sem essa menção não merge.
   O corpo segue `.github/pull_request_template.md`: **o que muda**, **por quê**,
   **como testar**, checklist de qualidade.
   `git push -u origin <branch> && gh pr create`
5. **CI verde** — `ci.yml`, `security.yml`, `codeql.yml` — mais os comandos
   locais da seção *Qualidade & Segurança* antes de pedir review.
6. **Merge = deploy.** Só via `gh pr merge`. Depois, confira que a Issue fechou
   sozinha; se não fechou, feche manualmente citando o PR.
