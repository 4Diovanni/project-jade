# 🟢 Project Jade

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

- [ ] **Fase 1 — O Despertar:** API FastAPI + LLM + chat via terminal.
- [ ] **Fase 2 — Conexão com o Passado:** ChromaDB + leitura do Obsidian (RAG).
- [ ] **Fase 3 — Os Sentidos:** WhatsApp + voz (Whisper/TTS).
- [ ] **Fase 4 — As Mãos:** Spotify, controle do SO e e-mail.

Detalhes completos em [`projeto_jade_arquitetura.md`](./projeto_jade_arquitetura.md).

## 🚀 Setup (desenvolvimento)

```bash
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env      # e preencha suas chaves / caminho do vault

python main.py              # ou: uvicorn interfaces.api:app --reload
```

## 🔒 Privacidade

Este repositório vive **dentro** de um vault do Obsidian. Suas notas pessoais **não** são versionadas — o `.gitignore` protege `.env`, os bancos de dados e as notas `.md` da raiz. Jade lê o vault localmente pelo caminho em `OBSIDIAN_VAULT_PATH`.

---

*Construído com auxílio de skills do Claude Code (ver `.claude/skills/`).*
