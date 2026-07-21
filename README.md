# 🟢 Project Jade

[![CI](https://github.com/4Diovanni/project-jade/actions/workflows/ci.yml/badge.svg)](https://github.com/4Diovanni/project-jade/actions/workflows/ci.yml)
[![Security](https://github.com/4Diovanni/project-jade/actions/workflows/security.yml/badge.svg)](https://github.com/4Diovanni/project-jade/actions/workflows/security.yml)
[![CodeQL](https://github.com/4Diovanni/project-jade/actions/workflows/codeql.yml/badge.svg)](https://github.com/4Diovanni/project-jade/actions/workflows/codeql.yml)

> Um assistente pessoal **agentic**, *privacy-first*, que roda localmente e unifica suas ferramentas, notas e rotinas sob um único comando.

O nome remete ao **Selo Imperial de Jade** de Qin Shi Huang, o imperador que unificou a China. Assim como o Selo unificou os 7 reinos, o **Jade** unifica Obsidian, WhatsApp, voz, Spotify, e-mail e o próprio sistema operacional em um só cérebro.

---

## ✨ Visão

Jade não é um chatbot — é um **agente de automação**. Um LLM decide *qual ferramenta* usar a cada comando (*function calling*), com memória de longo prazo alimentada pelas suas anotações do Obsidian via **RAG**.

## 🏗️ Arquitetura

| Camada | Stack |
|---|---|
| **Core / Backend** | Python · FastAPI · LangChain |
| **LLM** | Ollama (local) *ou* OpenAI / Anthropic / Gemini (nuvem) |
| **Memória** | SQLite (histórico) · ChromaDB (vetores do Obsidian) |
| **Sentidos** | WhatsApp · Voz (Whisper + TTS) · Dashboard |

```text
project-jade/
├── core/          # Cérebro: LLM, memória (RAG) e roteador de agente
├── tools/         # Habilidades (Obsidian, Spotify, sistema, e-mail...)
├── interfaces/    # API, voz e bot de WhatsApp
├── database/      # ChromaDB + SQLite (gerados em runtime)
└── main.py        # Ponto de entrada
```

## 🗺️ Roadmap

- [x] **Fase 1 — O Despertar:** API FastAPI + LLM + chat via terminal.
- [x] **Fase 2 — Conexão com o Passado:** ChromaDB + leitura do Obsidian (RAG).
- [x] **Fase 3 (voz) — Os Sentidos:** STT local (faster-whisper) + TTS (edge-tts). *WhatsApp adiado p/ fase futura.*
- [ ] **Fase 4 — As Mãos:** controle do SO (abrir apps, volume, busca web) ✅ · Spotify e e-mail (próximos).

Detalhes completos em [`projeto_jade_arquitetura.md`](./projeto_jade_arquitetura.md).

## 🚀 Setup (desenvolvimento)

```bash
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env      # e preencha suas chaves / caminho do vault

# Provider padrão = Ollama (local). Instale-o e baixe os modelos:
#   https://ollama.com/download
#   ollama pull llama3               # LLM de conversa
#   ollama pull nomic-embed-text     # embeddings do RAG (Fase 2)
# (ou troque JADE_LLM_PROVIDER=openai/anthropic e ponha a chave no .env)

python main.py index        # indexa suas notas do Obsidian no ChromaDB (RAG)
python main.py chat         # chat no terminal, com RAG das suas anotações

# Voz (Fase 3) — precisa de: pip install faster-whisper edge-tts
python main.py say "Olá, eu sou o Jade"    # TTS: fala o texto
python main.py transcribe audio.mp3         # STT: transcreve um áudio

python main.py              # ou sobe a API:
#   /chat /search /index /reset /health
#   /voice/transcribe  /voice/tts  /voice/chat
```

## 🔒 Privacidade & Segurança

Este repositório vive **dentro** de um vault do Obsidian. Suas notas pessoais **não** são versionadas — o `.gitignore` protege `.env`, os bancos de dados e as notas `.md` da raiz. Jade lê o vault localmente pelo caminho em `OBSIDIAN_VAULT_PATH`.

Toda alteração passa por uma **pipeline de segurança automatizada**:

| Camada | Ferramenta |
|---|---|
| Segredos (código + histórico) | **Gitleaks** (CI + pre-commit) |
| Análise estática (SAST) | **Bandit** · **CodeQL** |
| Vulnerabilidades em dependências | **pip-audit** · **Dependabot** |
| Lint / formatação | **Ruff** |

Detalhes e como reportar falhas: [`SECURITY.md`](./SECURITY.md). Para ativar os hooks locais:

```bash
pip install -r requirements-dev.txt
pre-commit install
```

---

*Construído com auxílio de skills do Claude Code (ver `.claude/skills/`).*
