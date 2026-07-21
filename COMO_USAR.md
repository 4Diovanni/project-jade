# 🟢 Como usar o Jade

Guia prático do seu assistente pessoal. O Jade roda **localmente** (privacy-first):
conversa, lembra das suas anotações do Obsidian, fala e ouve, e já controla o
seu computador.

---

## 1. Pré-requisitos (uma vez)

1. **Ollama** (o cérebro local) — instale em <https://ollama.com/download> e baixe os modelos:
   ```powershell
   ollama pull llama3            # conversa
   ollama pull nomic-embed-text  # memória (RAG do Obsidian)
   ```
   Deixe o Ollama rodando (ele fica na bandeja do Windows).

2. **Dependências Python** (na pasta do projeto):
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. **Configuração** — copie o exemplo e ajuste se quiser:
   ```powershell
   copy .env.example .env
   ```
   Os padrões já funcionam. As opções mais úteis estão na [seção 7](#7-configuração-env).

---

## 2. Começando a usar

### Conversar no terminal (jeito mais rápido)
```powershell
python main.py chat
```
Digite e converse. Comandos especiais:
- `/reset` — começa uma conversa nova
- `/sair` — encerra

### Subir a API (para o navegador, apps e futuramente WhatsApp)
```powershell
python main.py
```
Abra <http://127.0.0.1:8000/docs> — uma interface web (Swagger) onde você testa
**tudo clicando**, inclusive enviando áudios.

---

## 3. O que o Jade sabe fazer

### 💬 Conversar
É só falar naturalmente. Ele responde em português, de forma direta.

### 🧠 Lembrar das suas anotações (memória / RAG do Obsidian)
O Jade lê as notas do seu **vault do Obsidian** e responde com base nelas.

1. Coloque suas notas na pasta do vault (padrão: `obsidian_notes/`).
2. Indexe:
   ```powershell
   python main.py index
   ```
3. Pergunte no chat: *"O que eu anotei sobre a reunião de ontem?"* — ele busca
   nas suas notas e **cita a nota de origem**.

> **Toda conversa vira uma nota `.md`** em `obsidian_notes/Conversas/`, com
> data, título e tags. Abra a pasta `obsidian_notes` no Obsidian para ver as
> conexões no grafo. Rode `index` de novo para o Jade "lembrar" das conversas.

### 🔊 Voz — falar e ouvir
```powershell
# O Jade FALA um texto (gera e toca um .mp3)
python main.py say "Olá, eu sou o Jade"

# Salvar a fala num arquivo
python main.py say "Bom dia" saudacao.mp3

# O Jade OUVE um áudio e transcreve (voz -> texto)
python main.py transcribe audio.mp3
```
Pela API, dá para mandar um áudio e receber a resposta falada (ver seção 5).
Os áudios que o Jade gera ficam em `obsidian_notes/Áudios/`.

### 🖐️ Controlar o computador (as "Mãos")
No chat, peça naturalmente:

| Você diz… | O Jade faz |
|---|---|
| "abra a calculadora" | abre a Calculadora |
| "abre o bloco de notas" | abre o Notepad |
| "abra o explorador" | abre o Explorador de Arquivos |
| "abra o navegador" | abre o navegador padrão |
| "abra as configurações" | abre as Configurações do Windows |
| "aumente o volume" / "diminua o volume" | ajusta o volume |
| "mudo" / "tira o som" | muta/desmuta |
| "pesquise receita de bolo no google" | busca no navegador |

> 🔒 **Segurança**: o Jade só abre aplicativos de uma **lista aprovada** — ele
> nunca executa comandos arbitrários. Para desligar o controle do sistema,
> coloque `JADE_SYSTEM_TOOL_ENABLED=false` no `.env`.

---

## 4. Como ele decide o que fazer

A cada mensagem, o Jade primeiro verifica se é um **comando** (abrir app, volume,
busca). Se for, ele age. Se não, **conversa** — buscando nas suas anotações
quando fizer sentido.

**Dois cérebros (roteador dual-model):** se você configurar uma `ANTHROPIC_API_KEY`,
o Jade manda perguntas **informativas/complexas** (ex.: "como preparar tal receita")
para o **Claude** (nuvem, mais capaz), e mantém no **llama3** (local) a conversa
comum e tudo que toca suas **notas pessoais** — privacidade. Sem chave, fica 100%
no llama3. No chat, um selo `☁️claude` indica quando a resposta veio da nuvem.

> A chave vem do <https://console.anthropic.com> (uso pago por token) — é
> **diferente** da assinatura Claude Pro do site/app, que não dá acesso à API.

---

## 5. API — referência rápida

Com `python main.py` rodando (`http://127.0.0.1:8000`):

| Método | Rota | O que faz |
|---|---|---|
| GET | `/health` | status do serviço |
| POST | `/chat` | conversar — corpo `{"message": "..."}` |
| POST | `/reset` | limpa o histórico da conversa |
| POST | `/index` | (re)indexa o vault do Obsidian |
| POST | `/search` | busca nas notas — `{"query": "...", "k": 4}` |
| POST | `/voice/transcribe` | áudio (upload) → texto |
| POST | `/voice/tts` | texto → áudio mp3 — `{"text": "..."}` |
| POST | `/voice/chat` | áudio → Jade responde (texto + `audio_url`) |
| GET | `/voice/audio/{nome}` | baixa um áudio gerado |

O jeito mais fácil de experimentar é pelo **Swagger** em `/docs`.

---

## 6. Exemplos prontos

```powershell
# Conversa rápida via API (PowerShell)
Invoke-RestMethod -Uri http://127.0.0.1:8000/chat -Method Post `
  -ContentType "application/json" -Body '{"message":"me dê uma dica de foco"}'

# Indexar as notas e perguntar sobre elas (no chat)
python main.py index
python main.py chat
#   você › o que eu tenho anotado sobre o Project Jade?
```

---

## 7. Configuração (`.env`)

As opções que você provavelmente vai querer mexer:

| Variável | Padrão | Para quê |
|---|---|---|
| `JADE_LLM_PROVIDER` | `ollama` | `ollama` (local), `openai`, `anthropic`, `gemini` |
| `OLLAMA_MODEL` | `llama3` | modelo de conversa |
| `OBSIDIAN_VAULT_PATH` | `./obsidian_notes` | onde ficam as notas/memória |
| `JADE_WHISPER_MODEL` | `base` | precisão da transcrição: `tiny` < `base` < `small` |
| `JADE_TTS_VOICE` | `pt-BR-FranciscaNeural` | voz (ex.: `pt-BR-AntonioNeural`) |
| `JADE_TTS_BACKEND` | `edge` | `edge` (online, melhor) ou `pyttsx3` (offline) |
| `JADE_SYSTEM_TOOL_ENABLED` | `true` | liga/desliga o controle do PC |

> **Segredos** (chaves de API) ficam **só** no `.env`, que nunca vai para o
> GitHub. Suas notas e conversas também são privadas.

---

## 8. Problemas comuns

- **"Jade indisponível" / erro de conexão** → o Ollama não está rodando.
  Abra o Ollama e confirme `ollama list`.
- **Ele não "lembra" de uma nota** → rode `python main.py index` depois de
  criar/editar notas (a indexação não é automática).
- **Transcrição imprecisa** → aumente o modelo: `JADE_WHISPER_MODEL=small`.
- **Acentos quebrados no terminal** → use o terminal normalmente; a CLI já força
  UTF-8.

---

## 9. O que vem por aí

- 🎵 **Spotify** e 📧 **e-mail** (Fase 4 — as Mãos).
- 📱 **WhatsApp** (falar com o Jade pelo celular).
- 🪞 **Memória evolutiva**: o Jade aprender seu jeito a partir das conversas.

Detalhes técnicos no `README.md` e no `projeto_jade_arquitetura.md`.
