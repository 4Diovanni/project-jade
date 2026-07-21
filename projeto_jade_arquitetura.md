# Assistente Pessoal: Projeto Jade (Unificador)

## 1. O Conceito e o Nome

Para um nome que combine uma pedra preciosa com a ideia de "unificação" e faça referência ao Imperador Qin Shi Huang, a melhor escolha é **Jade** (ou **He Shi Bi** / **Selo Imperial**). 

**Por que Jade?**
Qin Shi Huang, após unificar a China, ordenou a criação do **Selo Imperial da China** (o símbolo supremo do poder e da unificação), que foi esculpido em uma das pedras preciosas mais famosas da história: um disco de jade chamado *He Shi Bi*.
Assim como o Imperador unificou os 7 reinos da China e o Obsidian guarda seus pensamentos como uma rocha afiada, o **Jade** (ou **Selo de Jade**) unificará todas as suas ferramentas, aplicativos e rotinas em um único local, sob o seu comando.

**Ideias de Nomes Oficiais:**
- **Project Jade** (Simples e elegante)
- **Cinnabar** (Cinábrio - a pedra vermelha de onde se extrai o mercúrio, a "poção da imortalidade" de Qin)
- **Kaiser** ou **Zheng** (Referência direta ao nome do rei, Ying Zheng, atrelado a um codinome de pedra)

---

## 2. Visão Geral do Produto

O **Project Jade** será um assistente virtual rodando primariamente de forma **local** (Privacy-First), servindo como o cérebro central das suas operações diárias. 

Ele não é apenas um chatbot; é um **agente de automação**. Ele terá permissões para ler seus arquivos locais (Obsidian), controlar seu mouse/teclado se necessário, ler seus emails, controlar mídia e interagir com você por múltiplas interfaces (Voz, WhatsApp, Terminal).

---

## 3. Arquitetura e Stack Tecnológica

Para criar isso para o seu portfólio no GitHub (demonstrando habilidades sólidas de Engenharia de Software e IA), utilizaremos uma arquitetura modular baseada em **Agentes (Agentic AI)**.

### A. Core / Backend (O Cérebro)
- **Linguagem:** `Python` (A melhor linguagem para IA e automação de SO).
- **Framework Web:** `FastAPI` (Leve, assíncrono, perfeito para criar as rotas que o WhatsApp e o Frontend vão consumir).
- **Orquestração de IA:** `LangChain` ou `LlamaIndex` (Para criar o agente que decide *qual* ferramenta usar dependendo do seu comando).
- **Modelo de Linguagem (LLM):** 
  - *Opção 1 (100% Local & Privado):* `Ollama` rodando modelos como Llama 3 ou Mistral na sua máquina.
  - *Opção 2 (Nuvem rápida):* API da OpenAI, Gemini ou Anthropic.

### B. Memória e Banco de Dados
- **Banco de Dados Relacional:** `SQLite` (Ideal para uso local) ou `PostgreSQL` para armazenar histórico de conversas, lista de tarefas, alarmes e configurações.
- **Banco de Dados Vetorial (Vector DB):** `ChromaDB` ou `FAISS`. Isso será usado para o RAG (Retrieval-Augmented Generation). O Jade vai ler suas anotações do Obsidian, converter em vetores, e salvar aqui para consultar quando você fizer uma pergunta.

### C. Interfaces de Comunicação (Os Sentidos)
- **WhatsApp:** Integração usando a biblioteca `whatsapp-web.js` (Node.js) ou `Baileys`, que funciona como um client do WhatsApp Web, enviando as mensagens via HTTP para o seu backend Python.
- **Voz:** 
  - *Ouvir (STT):* `OpenAI Whisper` (Pode rodar localmente de forma muito eficiente).
  - *Falar (TTS):* `ElevenLabs API` (Voz ultra-realista) ou bibliotecas locais como `pyttsx3` ou `Edge-TTS`.
- **Dashboard Web / Desktop:** Um frontend simples em `React` (Next.js ou Vite) ou app desktop com `Electron`/`Tauri` para ver status, logs e configurações.

---

## 4. Módulos de Atuação (As "Mãos" do Jade)

O assistente terá acesso a ferramentas (Tools). Quando você pedir algo, o LLM decide qual ferramenta ativar:

1. **Módulo Obsidian (Gestão do Conhecimento):**
   - Lê a pasta local do seu vault do Obsidian.
   - Indexa os arquivos `.md` no ChromaDB.
   - Consegue criar novas notas, fazer resumos ou responder a perguntas como *"O que eu anotei sobre X na reunião da semana passada?"*
2. **Módulo Spotify & Mídia:**
   - Integração com `Spotipy` (Spotify Web API).
   - Comandos: *"Toque um lo-fi"*, *"Pule a música"*, *"Aumente o volume"*.
3. **Módulo de Controle do Sistema Operacional:**
   - Uso das bibliotecas `os`, `subprocess`, e `pyautogui`.
   - Pode abrir programas, fechar abas, gerenciar o volume do Windows, ou até clicar em áreas da tela.
4. **Módulo de Comunicação (Emails e Mensagens):**
   - Leitura via `IMAP` e envio via `SMTP` ou integração direta com a API do Gmail.
   - Pode resumir sua caixa de entrada de manhã: *"Você tem 3 emails importantes de clientes e 1 fatura para pagar"*.
5. **Módulo de Produtividade (Tarefas e Calendário):**
   - Integração com `Google Calendar API`.
   - Adiciona lembretes e tarefas no seu banco de dados local ou no Notion/Todoist.

---

## 5. Estrutura de Diretórios para o GitHub

Esta é a estrutura recomendada para o seu repositório:

```text
project-jade/
│
├── core/                   # Cérebro do Assistente (Agentes e LLM)
│   ├── llm_engine.py
│   ├── memory.py           # Gestão de histórico e VectorDB
│   └── agent_router.py     # Decide qual ferramenta usar
│
├── tools/                  # Habilidades específicas (Integrações)
│   ├── obsidian_tool.py
│   ├── spotify_tool.py
│   ├── system_tool.py
│   ├── email_tool.py
│   └── calendar_tool.py
│
├── interfaces/             # Como você fala com ele
│   ├── whatsapp_bot/       # Serviço (NodeJS ou Python) para WhatsApp
│   ├── voice_service.py    # Whisper + TTS
│   └── api.py              # FastAPI (Servidor principal)
│
├── database/               # Bancos de dados
│   ├── chroma_db/          # Vetores do Obsidian
│   └── jade.db             # SQLite
│
├── requirements.txt
├── .env                    # Chaves de API (NUNCA commitar no Github)
└── main.py                 # Ponto de entrada (Liga tudo)
```

---

## 6. Plano de Ação (Roadmap de Implementação)

Para não se sobrecarregar, sugiro construir em fases:

**Fase 1: O Despertar (CLI e LLM)**
- Crie o servidor FastAPI.
- Conecte o modelo (OpenAI ou Ollama).
- Crie uma interface via terminal (linha de comando) para bater papo.

**Fase 2: Conexão com o Passado (Obsidian & Memória)**
- Implemente o ChromaDB e LangChain.
- Faça-o ler a pasta do Obsidian.
- Teste fazer perguntas sobre suas próprias anotações.

**Fase 3: Os Sentidos (WhatsApp e Voz)**
- Suba o serviço de conexão com o WhatsApp.
- Integre o Whisper para mandar áudios e ele responder com texto ou áudio.

**Fase 4: As Mãos (Sistema, Spotify e Email)**
- Crie a tool do Spotify.
- Crie a tool de controle do computador.
- Crie a tool de leitura de emails.

---

## 7. Como isso brilha no Portfólio

Para os recrutadores ou outros devs, esse projeto demonstra:
- **Integração de Sistemas:** Fazer WhatsApp, Python, e Spotify conversarem.
- **Engenharia de IA:** Uso avançado de LLMs como Agentes com acesso a ferramentas (*Function Calling*), não apenas geradores de texto.
- **RAG (Retrieval-Augmented Generation):** Busca semântica e embeddings no Obsidian.
- **Arquitetura Escalável:** Módulos separados onde adicionar uma nova habilidade é tão fácil quanto criar um novo arquivo em `tools/`.

---

## 8. Escopo Estendido / Evolução

Direções que guiam o projeto além do roadmap base:

### A. Memória = o próprio Obsidian do usuário
O banco de memória do Jade **é** o vault do Obsidian, no PC do usuário
(*privacy-first* levado ao limite):
- **Toda conversa** com o Jade é persistida como nota `.md` no vault
  (`core/journal.py`), com frontmatter (**título, data, tags**) e tag aninhada
  `#conversa/AAAA-MM-DD` + link para o hub `[[Jade — Memória]]`. Assim o **grafo
  do Obsidian** conecta as conversas por grupo, data e título.
- Essas notas são reindexadas no RAG: o histórico vira memória de longo prazo.
- O vault fica numa pasta local dedicada (`OBSIDIAN_VAULT_PATH`, ex.:
  `./obsidian_notes`) que o usuário abre no Obsidian.

### B. "Pensamento próprio" (emulação de persona)
Meta de longo prazo: a partir do acúmulo de conversas e do **modo como o usuário
fala**, o Jade passa a **imitar ideias, tom e preferências** do usuário —
aproximando-se de "sentimentos e ideias" baseados nele. Fundação: a memória em
Obsidian (item A) como corpus pessoal.

### C. Roteamento dual-model (Claude + llama3)
Dois "modos de IA" com um **roteador** que escolhe o modelo por tipo de tarefa:
- **llama3 (local):** ações comuns, rápidas e rastreáveis pela memória/PC —
  ex.: renomear uma pasta, comandos simples, coisas já presentes no vault.
- **Claude (nuvem):** raciocínio mais complexo e informativo — ex.: "como
  preparar tal receita", análises que exigem conhecimento amplo.
- Objetivo: privacidade e custo baixos por padrão (local), recorrendo à nuvem só
  quando agrega. *(Nota técnica: assinatura Claude Pro ≠ API da Anthropic; a
  forma de acesso será definida na implementação desta fase.)*
