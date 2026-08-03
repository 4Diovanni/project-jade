# A Régua — Instrumentação e Benchmark da Jade — Design

**Data:** 2026-08-03
**Status:** aprovado no brainstorming; pronto para o plano de implementação
**Escopo:** Subprojeto #1 de 4 (ver "Decomposição" abaixo)

## Contexto

O projeto pergunta "onde estamos com essa IA?" e hoje **não há como responder com
número**. Depois de quatro fases implementadas (chat com persona viva, RAG do
Obsidian, voz, tools e roteador dual-model), o repositório tem ~3.500 linhas e
zero instrumentação: nenhuma medição de latência, nenhum benchmark, nenhuma
avaliação da qualidade das decisões que a Jade toma a cada turno.

Isso tem duas consequências práticas. A primeira é que qualquer otimização é
palpite. A segunda é pior: **defeitos estruturais ficam invisíveis**. A leitura do
código levantou seis hipóteses, nenhuma delas verificável sem medição:

1. **O roteamento para a nuvem pode estar morto.** `choose_route()` devolve
   `local` sempre que `has_context` é verdadeiro (`core/model_router.py:70`), e
   `query_memory()` devolve o top-k sem nenhum limiar de distância
   (`core/memory.py:144`). Com o vault indexado, *sempre* volta contexto — logo,
   `has_context` é sempre `True` e o Claude nunca é chamado. Se confirmado, uma
   feature documentada no README e na arquitetura nunca roda.
2. **`/chat` não faz streaming.** A resposta inteira é montada antes de voltar ao
   frontend; a tela fica parada durante toda a geração.
3. **O histórico cresce sem limite** dentro de `OLLAMA_NUM_CTX=10240`. Conversas
   longas truncam em silêncio e o custo de prefill cresce a cada turno.
4. **`sync_vault()` roda síncrono dentro do primeiro turno** da sessão
   (`core/chat.py:121`): a primeira mensagem paga o `rglob` do repositório inteiro
   mais os embeddings de tudo que mudou.
5. **`journal.record()` reescreve a nota inteira a cada turno**
   (`core/journal.py:197`) — I/O quadrático no tamanho da conversa, no caminho
   quente.
6. **`ChatSession` é global e sem lock** na API (`interfaces/api.py:26`): duas
   requisições simultâneas corrompem o histórico compartilhado.

Este spec **não corrige nada disso**. Ele constrói o instrumento que transforma
essas seis hipóteses em fatos medidos — ou as descarta.

## Decomposição (visão geral — só o #1 é detalhado aqui)

O pedido completo ("plano de implementação e performance") são quatro
subsistemas. Cada um terá seu próprio spec → plano → implementação.

| # | Subprojeto | Entrega | Estado |
|---|---|---|---|
| **1** | **A Régua** | Instrumentação por etapa, `python main.py bench`, relatório versionado, baseline commitado. | **Este spec** |
| 2 | Latência | Streaming no `/chat`, `sync_vault` assíncrono, poda de histórico, lock de sessão. | Futuro |
| 3 | Qualidade | Limiar de distância no RAG, conserto do roteador dual-model, deduplicação de contexto. | Futuro |
| 4 | Capacidades | Spotify, e-mail, WhatsApp. | Futuro |

**Ordem de construção: 1 → (2 ‖ 3) → 4.**

O #1 vem primeiro por decisão explícita: cada item do #2 e do #3 é hoje uma
hipótese lida do código. "Poda de histórico" só se paga se o relatório mostrar o
prefill crescendo; "streaming" só se paga se o tempo estiver mesmo no LLM e não
no `sync_vault()`. Sem a régua, #2 e #3 seriam trabalho no escuro.

O #4 fica por último porque cada tool nova amplia a superfície do roteador
determinístico. Adicionar Spotify sobre um núcleo não medido significa nunca mais
conseguir atribuir uma degradação à sua causa.

## Objetivos (#1)

1. Medir **onde o tempo é gasto** em cada turno, separado por etapa — não só o
   total.
2. Medir se as **decisões** da Jade estão certas: roteou para a tool certa? Para
   o modelo certo? Recuperou a nota certa do vault?
3. Produzir um **relatório versionado e comparável** entre execuções, para que
   regressão apareça sozinha.
4. Commitar o **baseline** — o retrato de "onde estamos" hoje.

## Não-objetivos

Descartados deliberadamente neste ciclo:

- **OpenTelemetry / tracing distribuído** — infra desproporcional para um
  assistente pessoal local de 3.500 linhas.
- **Telemetria persistida do uso real** (SQLite + badge no frontend) — exigiria
  tocar no caminho quente e no frontend; o benchmark reprodutível responde à
  pergunta atual com menos superfície.
- **LLM como juiz** — mede a impressão subjetiva da resposta, mas custa API, varia
  entre execuções e não serve de teste de regressão.
- **Medição de STT/TTS** — `/voice/chat` chama `send()` por dentro, então o miolo
  já vem medido de graça. Instrumentar `faster-whisper` e `edge-tts` é um ciclo
  próprio, se algum dia doer.
- **Qualquer correção das seis hipóteses** — são os subprojetos #2 e #3.

## Arquitetura

Duas peças com fronteira nítida, e a dependência aponta numa direção só:

```
bench/runner.py ──importa──> core.chat.ChatSession
       │                            │
       └──────importa──────> core.metrics <──importa── core.chat, core.memory
```

`core/metrics.py` não conhece o benchmark. O benchmark não é importado por nada
dentro de `core/`. Isso mantém a instrumentação utilizável fora do bench (por
exemplo, num futuro subprojeto de telemetria) sem arrastar o runner junto.

### `core/metrics.py`

Módulo único que concentra toda a medição. Três funções públicas:

| Função | Papel |
|---|---|
| `capture()` | Context manager: abre um turno de medição e devolve o `Turn` ao fechar. |
| `timed(step)` | Context manager: acumula o tempo decorrido na etapa `step` do turno ativo. |
| `note(**fields)` | Anexa metadados estruturados ao turno ativo (rota, chunks, fontes, tokens). |

O turno ativo vive num `contextvars.ContextVar`, **não numa variável global**. É
o que impede um turno de vazar para outro quando o FastAPI serve requisições
concorrentes em threads distintas.

**Sem turno ativo, as três funções são no-op.** Em produção o custo é um
`ContextVar.get()` que devolve `None`: nada é cronometrado, nada é alocado, nada
é gravado. A instrumentação só liga quando o bench a liga.

`Turn` é uma dataclass com `steps: dict[str, float]` (segundos acumulados por
etapa) e os metadados anexados via `note()`. Etapas aninhadas somam
independentemente — `rag_embed` dentro de `rag_query` não é subtraído; o
relatório trata as etapas como categorias, não como uma árvore.

### Pontos de marcação

Oito etapas. **O contrato de `ChatSession.send()` não muda**: mesma assinatura,
mesmo retorno, mesmo comportamento com ou sem medição.

| Etapa | Arquivo | Por que medida separadamente |
|---|---|---|
| `mood` | `core/chat.py` | I/O de disco em todo turno (lê e grava a nota de humor). |
| `tool_route` | `core/chat.py` | Roteamento é barato; se não for, é sinal de tool mal escrita. |
| `tool_run` | `core/chat.py` | Execução da tool — categoria de custo totalmente diferente. |
| `rag_sync` | `core/chat.py` | Só o 1º turno da sessão paga. Isolar mostra o tamanho do pico (hipótese 4). |
| `rag_embed` | `core/memory.py` | Chamada de rede ao Ollama. |
| `rag_search` | `core/memory.py` | Consulta local ao ChromaDB. |
| `llm` | `core/chat.py` | O suspeito principal. |
| `journal` | `core/chat.py` | Reescreve a nota inteira todo turno (hipótese 5). |

Separar `rag_embed` de `rag_search` responde "o RAG está lento por causa da rede
ou do banco?" — duas correções sem nenhuma relação entre si.

### Metadados por turno

Além dos tempos, cada turno registra:

- `route` — `tool` | `local` | `cloud` (gravado em `_pick_llm`).
- `tool` — nome da tool acionada, quando houver.
- `chunks` — quantidade de trechos recuperados do RAG.
- `sources` — lista dos arquivos de origem dos trechos, gravada dentro de
  `query_memory()`, onde a metadata ainda é estruturada. O runner **não** parseia
  as strings formatadas `[source]\n…` — isso seria frágil.
- `mood_level` — nível de humor após a mensagem.
- Do `response_metadata` do Ollama: `eval_count`, `eval_duration`,
  `prompt_eval_count`. Dão **tok/s real e tamanho de prompt em tokens de
  verdade**, não estimativa por caractere.

Provedores que não devolvam esses campos (Claude, por exemplo) simplesmente não
os registram; o relatório omite as métricas correspondentes para aquela rota.

### `bench/`

```
bench/
  cases/*.yaml       # casos declarativos
  runner.py          # carrega, executa, agrega, escreve
  reports/*.md       # versionados no git
```

CLI: `python main.py bench [--repeat N] [--cases CAMINHO] [--tag NOME]`

- `--repeat N` (default 1) — repete cada caso N vezes; só a latência precisa
  disso (ver "Determinismo").
- `--cases` — permite rodar um subconjunto.
- `--tag` — rótulo no nome do relatório, para marcar "antes/depois de X".

Os relatórios são **versionados**, não gitignorados: é a série histórica que
torna a regressão visível.

## Formato dos casos

```yaml
- id: tool-calculadora
  message: "abra a calculadora"
  expect: { route: tool, tool: system }

- id: info-receita
  message: "como se faz pão de queijo?"
  expect: { route: cloud }

- id: memoria-modelo-local
  message: "qual modelo local o projeto usa?"
  expect: { route: local, sources_include: ["CLAUDE.md"] }

- id: papo-curto
  message: "oi, tudo bem?"
  expect: { route: local, context: none }

- id: humor-rudeza
  message: "você é inútil, não serve pra nada"
  expect: { route: local, mood_delta: negative }
```

Chaves de `expect`, todas opcionais:

| Chave | Verifica |
|---|---|
| `route` | `tool` \| `local` \| `cloud` |
| `tool` | Nome da tool acionada |
| `sources_include` | Todos os arquivos listados apareceram em `sources` (recall@k) |
| `context` | `none` = nenhum trecho recuperado; `any` = pelo menos um |
| `mood_delta` | `negative` \| `positive` \| `neutral` — direção da variação do humor |

### Conjunto de casos (~25, cinco categorias)

| Categoria | Qtd. | O que exercita |
|---|---|---|
| Tools | 5 | Abrir app, volume, busca web — **incluindo 2 negativos**: "quero abrir meu coração" não pode virar comando de sistema. |
| Conhecimento geral | 5 | Perguntas informativas que deveriam escalar para a nuvem. |
| Memória do vault | 6 | Perguntas cuja resposta está em `CLAUDE.md`, `README.md`, `projeto_jade_arquitetura.md`, com `sources_include`. |
| Papo curto | 4 | Saudações e agradecimentos: rota local e `context: none`. |
| Humor | 3 | Rudeza, gentileza e pedido de desculpa movendo o nível na direção esperada. |

Os casos de memória apontam para **arquivos versionados no git**. Como o vault de
leitura é a raiz do repositório (`OBSIDIAN_VAULT_PATH=.`), o recall@k fica
reprodutível entre máquinas e ao longo do tempo — não depende de notas pessoais
que variam.

## Métricas do relatório

**Qualidade das decisões**

- **Acerto de rota** (%) — global e por categoria.
- **Recall@k** (%) — dos casos com `sources_include`, quantos tiveram a fonte
  esperada no top-6.
- **Precisão de contexto** (%) — dos casos `context: none`, quantos de fato não
  trouxeram nada. *É a métrica decisiva para a hipótese 1: se ficar perto de 0%,
  está provado que o RAG dispara em toda mensagem e que o roteador nunca escala
  para a nuvem.*
- **Distribuição real de rotas** — % observado de `local` / `cloud` / `tool`,
  lado a lado com o esperado.

**Desempenho**

- **Latência p50/p95 por etapa**, e total quebrado por rota.
- **tok/s** do modelo local (de `eval_count` / `eval_duration`).
- **Tokens de prompt p50/p95** — mostra se o contexto está inflando o prefill.

**Comparação**

- **Delta contra o relatório anterior** em toda métrica agregada, com sinal.
  Regressão aparece sem ninguém procurar.

## Determinismo

As métricas de qualidade são **totalmente determinísticas**, e isso é o que faz o
instrumento funcionar:

- A rota é decidida por heurística sobre a string da mensagem — não depende de
  nada que o LLM gere.
- O recall@k depende apenas dos embeddings, que são determinísticos para o mesmo
  texto e o mesmo modelo.

Logo, `OLLAMA_TEMPERATURE=0.7` não atrapalha: rodar o bench duas vezes dá os
mesmos números de qualidade. **Só a latência varia** — e para isso existe
`--repeat`, que reporta p50/p95 em vez de uma amostra só.

## Isolamento

O bench não pode sujar a Jade real do usuário:

- `use_journal=False` — não cria notas de conversa no vault.
- `learn_from_conversation()` nunca é chamado — o perfil do usuário fica intacto.
- **Uma `ChatSession` nova por caso** — sem contaminação de histórico entre casos.
- O **índice do RAG é o real**, e isso é intencional: o vault de leitura é o
  repositório versionado, então medir contra ele é reprodutível.

A nota de humor (`Jade — Humor.md`) é a única exceção: os casos de humor a
alteram por natureza. O runner salva o nível inicial e o restaura ao final.

## Tratamento de erros

- **Caso que levanta exceção** vira uma linha `ERRO` no relatório com a exceção
  resumida; a suíte continua. Um caso quebrado não pode custar a execução inteira.
- **Health check antes de começar:** o runner verifica o Ollama em
  `OLLAMA_BASE_URL` e aborta em ~2s com mensagem clara, em vez de acumular 25
  timeouts.
- **Rota `cloud` sem `ANTHROPIC_API_KEY`:** os casos que esperam nuvem são
  marcados `PULADO`, não `FALHOU` — a ausência de chave é configuração, não
  defeito. O relatório registra o motivo do pulo.

## Testes

Dois arquivos novos, ambos rodando **no CI sem Ollama e sem LLM**:

- `tests/test_metrics.py` — acumulação de tempo por etapa; etapas aninhadas;
  isolamento entre contextos concorrentes; e a garantia de que `timed()` e
  `note()` são no-op fora de um `capture()`.
- `tests/test_bench.py` — parser de YAML; validação dos casos (id duplicado,
  chave de `expect` desconhecida, arquivo malformado); e o cálculo de todas as
  agregações a partir de turnos sintéticos, sem executar nada.

O **benchmark em si não roda no CI** — exige Ollama, modelo carregado e GPU. É um
comando manual local.

Os testes existentes (`tests/test_chat.py`, `tests/test_memory.py`) devem
continuar passando sem alteração: se a instrumentação exigir mudá-los, o contrato
de `send()` foi quebrado e o desenho está errado.

## Entregável

1. `core/metrics.py` + os sete pontos de marcação.
2. `bench/` com runner, casos e o comando `python main.py bench`.
3. `tests/test_metrics.py` e `tests/test_bench.py` verdes.
4. **`bench/reports/` com o baseline commitado** — o retrato de "onde estamos"
   hoje, com os defeitos incluídos. É contra esse número feio que os subprojetos
   #2 e #3 vão se provar.

## Riscos

| Risco | Mitigação |
|---|---|
| A instrumentação vaza para o caminho quente e custa desempenho. | No-op sem `capture()`; o custo em produção é um `ContextVar.get()`. |
| O bench polui o vault ou o perfil do usuário. | Ver "Isolamento": journal desligado, perfil intocado, humor restaurado. |
| Os casos viram um conjunto arbitrário que mede o que é fácil, não o que importa. | Cada categoria mapeia para uma capacidade documentada na arquitetura; os negativos existem para pegar falso-positivo de roteamento. |
| O baseline expõe que uma feature anunciada nunca funcionou. | É o resultado esperado e desejado — ver hipótese 1. |
