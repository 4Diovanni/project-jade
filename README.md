# 🟢 Project Jade

[![CI](https://github.com/4Diovanni/project-jade/actions/workflows/ci.yml/badge.svg)](https://github.com/4Diovanni/project-jade/actions/workflows/ci.yml)
[![Security](https://github.com/4Diovanni/project-jade/actions/workflows/security.yml/badge.svg)](https://github.com/4Diovanni/project-jade/actions/workflows/security.yml)
[![CodeQL](https://github.com/4Diovanni/project-jade/actions/workflows/codeql.yml/badge.svg)](https://github.com/4Diovanni/project-jade/actions/workflows/codeql.yml)

> Uma assistente pessoal **agentic**, *privacy-first*, que roda localmente e unifica suas ferramentas, notas e rotinas sob um único comando.

O nome remete ao **Selo Imperial de Jade** de Qin Shi Huang, o imperador que unificou a China. Assim como o Selo unificou os 7 reinos, a **Jade** unifica Obsidian, voz, o sistema operacional e (no futuro) Spotify, e-mail e WhatsApp em um só cérebro.

---

## ✨ Visão

A Jade não é um chatbot — é uma **agente** com personalidade própria. A cada comando ela decide *qual habilidade (tool)* usar, conversa com memória de longo prazo alimentada pelas suas anotações do **Obsidian** (via RAG), e tem **humor e caráter** que evoluem com o jeito que você a trata. Tudo roda **localmente** por padrão; nada das suas notas vai para a nuvem sem você mandar.

## 🖥️ Interface web (JARVIS-style)

Além do terminal, a Jade tem uma **UI local** servida pela própria API — layout de 3 zonas com voz em primeiro lugar:

- **Esquerda:** lista das suas conversas + o chat atual (texto ou voz).
- **Direita (~30%):** o **orb da Jade** — um visualizador em Canvas que reage à **amplitude real** do áudio (pulsa quando ela ouve e quando fala), com 4 estados: *ociosa / ouvindo / pensando / falando*.
- **Voz em primeiro lugar:** segure o 🎤 (ou a barra de espaço) para falar; toda resposta é **falada automaticamente** (TTS), com botão de mudo. Uma mensagem por vez — a entrada trava até a resposta chegar.

Suba a API e abra no navegador:

```bash
python main.py            # sobe a API (FastAPI/uvicorn)
# abra http://127.0.0.1:8000/  (redireciona para /app)
```

## 🏗️ Arquitetura

| Camada | Stack |
|---|---|
| **Core / Backend** | Python 3.11+ · FastAPI · LangChain |
| **LLM** | Ollama (local, padrão) *ou* OpenAI / Anthropic / Gemini (nuvem) |
| **Roteador dual-model** | llama3 (local) para o comum/pessoal · Claude (nuvem) para o complexo/informativo |
| **Memória** | ChromaDB (vetores do Obsidian) + as próprias conversas em `.md` |
| **Sentidos** | Voz (STT `faster-whisper` + TTS `edge-tts`) · UI web (Canvas/Web Audio) |

```text
project-jade/
├── core/                # Cérebro: LLM, memória (RAG), roteadores, persona, humor
├── tools/               # Habilidades (controle do SO; ponto de extensão principal)
├── interfaces/
│   ├── api.py           # API FastAPI
│   ├── voice_service.py # STT + TTS
│   └── frontend/        # UI web (JS puro, servida em /app)
├── database/            # ChromaDB (gerado em runtime; nunca versionado)
└── main.py              # Ponto de entrada (API, chat, index, voz)
```

## 🗺️ Roadmap

- [x] **Fase 1 — O Despertar:** API FastAPI + LLM + chat via terminal.
- [x] **Fase 2 — Conexão com o Passado:** ChromaDB + leitura do Obsidian (RAG), com auto-sync do vault.
- [x] **Fase 3 — Os Sentidos (voz):** STT local (`faster-whisper`) + TTS (`edge-tts`).
- [x] **Roteador dual-model:** Claude (nuvem) para o complexo/informativo · llama3 (local) para o comum/pessoal.
- [x] **Personalidade & memória viva:** IA feminina com humor persistente, perfil do usuário e conversas linkadas no grafo.
- [x] **Frontend #1 — Shell + voz:** UI web de 3 zonas, orb reativo, push-to-talk. *(#2 multi-thread e #3 wake-word são os próximos.)*
- [ ] **Fase 4 — As Mãos:** controle do SO (abrir apps, volume, busca web) ✅ · Spotify e e-mail (próximos) · WhatsApp (futuro).

Detalhes completos em [`projeto_jade_arquitetura.md`](./projeto_jade_arquitetura.md). Specs e planos em [`docs/superpowers/`](./docs/superpowers/).

## 📖 Como usar

Guia prático de uso (setup, comandos, voz, controle do PC, API): [`COMO_USAR.md`](./COMO_USAR.md).

## 🚀 Setup (desenvolvimento)

```bash
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env      # e preencha suas chaves / caminho do vault

# Provider padrão = Ollama (local). Instale-o e baixe os modelos:
#   https://ollama.com/download
#   ollama pull llama3               # LLM de conversa
#   ollama pull nomic-embed-text     # embeddings do RAG
# (ou troque JADE_LLM_PROVIDER=openai/anthropic e ponha a chave no .env)

python main.py index        # indexa suas notas do Obsidian no ChromaDB (RAG)
python main.py chat         # chat no terminal, com RAG das suas anotações

# Voz — TTS/STT pela linha de comando
python main.py say "Olá, eu sou a Jade"    # fala o texto (gera/toca .mp3)
python main.py transcribe audio.mp3         # transcreve um áudio (voz → texto)

python main.py              # sobe a API + a UI web:
#   http://127.0.0.1:8000/         → interface da Jade (orb + chat + voz)
#   http://127.0.0.1:8000/docs     → Swagger (testar os endpoints)
```

### Endpoints principais

| Rota | O que faz |
|---|---|
| `GET /` → `/app` | UI web da Jade |
| `POST /chat` | conversar — `{"message": "..."}` → `{reply, model}` |
| `POST /reset` | limpa o histórico da conversa |
| `POST /index` · `POST /search` | (re)indexar / buscar no vault |
| `GET /conversations` · `GET /conversations/{id}` | listar / abrir conversas salvas (leitura) |
| `POST /voice/transcribe` · `POST /voice/tts` · `POST /voice/chat` | voz (STT / TTS / conversa falada) |

## 🎭 Persona viva

A Jade é uma **IA feminina** com caráter — não uma assistente servil. Seu **humor** muda com o trato (rudeza a deixa mais seca; gentileza e desculpas melhoram) e persiste entre conversas; ela aprende seus gostos (`Sobre o Usuário.md`) e liga conversas do mesmo tema no grafo do Obsidian. Toda conversa vira uma nota `.md` no vault — a memória de longo prazo dela **é** o seu Obsidian.

## 🔒 Privacidade & Segurança

Este repositório vive **dentro** de um vault do Obsidian. Suas notas pessoais **não** são versionadas — o `.gitignore` protege `.env`, os bancos de dados e as notas `.md` da raiz. A Jade lê o vault localmente pelo caminho em `OBSIDIAN_VAULT_PATH`, e a UI é servida *same-origin* pela própria API (sem serviços de nuvem para voz além do TTS/STT já configurados).

Toda alteração passa por uma **pipeline de segurança automatizada**:

| Camada | Ferramenta |
|---|---|
| Segredos (código + histórico) | **Gitleaks** (CI + pre-commit) |
| Análise estática (SAST) | **Bandit** · **CodeQL** |
| Vulnerabilidades em dependências | **pip-audit** · **Dependabot** |
| Lint / formatação | **Ruff** |
| Testes (CI-safe, sem Ollama) | **pytest** · **node --test** (frontend) |

Detalhes e como reportar falhas: [`SECURITY.md`](./SECURITY.md). Para ativar os hooks locais:

```bash
pip install -r requirements-dev.txt
pre-commit install
```

---

*Construído com auxílio de skills do Claude Code (ver `.claude/skills/`).*
