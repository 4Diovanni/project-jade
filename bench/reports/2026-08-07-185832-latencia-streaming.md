# Benchmark da Jade — 2026-08-07 18:58 · `latencia-streaming`

17 caso(s) avaliado(s) · 13 ok · 4 falhou · 6 pulado · 0 erro

## Qualidade das decisões

| Métrica | Valor | Delta |
|---|---|---|
| Acerto de rota | 93.8% | = |
| Recall@k do RAG | 60.0% | = |
| Precisão de contexto (casos `context: none`) | 75.0% | -25.0 p.p. |
| Aprovação integral dos casos | 76.5% | -5.9 p.p. |

> **Como ler:** cada métrica de qualidade cobre **apenas** os casos que declaram a expectativa correspondente, e conta só as falhas **daquela** dimensão. Um caso que roteia certo mas puxa contexto indevido conta como acerto de rota e erro de contexto. *Acerto de rota* = casos com `route`. *Recall@k* = casos com `sources_include`. *Precisão de contexto* = casos com `context: none` (os `context: any` medem cobertura, não precisão). *Aprovação integral* = casos que passaram em **todas** as suas expectativas.

### Por categoria (aprovação integral do caso)

| Categoria | Aprovação | Casos |
|---|---|---|
| humor | 100.0% | 3 |
| memoria | 66.7% | 6 |
| papo | 75.0% | 4 |
| tools | 75.0% | 4 |

### Distribuição real de rotas

| local | tool |
|---|---|
| 13 | 4 |

## Desempenho

| Etapa | p50 (s) | p95 (s) | n |
|---|---|---|---|
| `journal` | 0.000 | 0.000 | 17 |
| `llm` | 6.197 | 13.540 | 13 |
| `mood` | 0.001 | 0.001 | 17 |
| `rag_embed` | 2.061 | 2.088 | 13 |
| `rag_search` | 0.002 | 0.003 | 13 |
| `rag_sync` | 0.170 | 0.218 | 17 |
| `tool_route` | 0.000 | 0.000 | 17 |
| `tool_run` | 0.001 | 0.128 | 4 |
| `total` | 5.043 | 16.260 | 17 |

| Métrica | Valor | Delta |
|---|---|---|
| Tokens/s (local) | 35.3 | +2.88 |
| Tokens de prompt p50 | 1565 | |
| Tokens de prompt p95 | 2862 | |

## Casos que não passaram

- **`info-receita`** (conhecimento) — pulado: rota 'cloud' exige ANTHROPIC_API_KEY configurada
- **`info-explique`** (conhecimento) — pulado: rota 'cloud' exige ANTHROPIC_API_KEY configurada
- **`info-diferenca`** (conhecimento) — pulado: rota 'cloud' exige ANTHROPIC_API_KEY configurada
- **`info-por-que`** (conhecimento) — pulado: rota 'cloud' exige ANTHROPIC_API_KEY configurada
- **`info-compare`** (conhecimento) — pulado: rota 'cloud' exige ANTHROPIC_API_KEY configurada
- **`mem-modelo-local`** (memoria) — falhou: sources_include: faltou CLAUDE.md (veio: nada)
- **`mem-arquitetura-memoria`** (memoria) — falhou: sources_include: faltou projeto_jade_arquitetura.md (veio: COMO_USAR.md, obsidian_notes\Conversas\2026-07-27_202749 — Qual o meu nome e em que ano eu nasci.md, obsidian_notes\Conversas\2026-07-28_001929 — quem é o meu melhor amigo😊.md)
- **`papo-saudacao`** (papo) — falhou: context: esperava nenhum trecho, vieram 1
- **`tool-negativo-coracao`** (tools) — falhou: route: esperava 'local', veio 'tool'
- **`tool-negativo-abrir-empresa`** (tools) — pulado: rota 'cloud' exige ANTHROPIC_API_KEY configurada

## Ressalvas

- **A queda de `precisão de contexto` (100,0% → 75,0%, -25,0 p.p.) é autocontaminação do
  processo de validação, não uma regressão de código.** O único caso novo a falhar é
  `papo-saudacao` (`context: esperava nenhum trecho, vieram 1`); os outros 3 casos
  `papo-*` (`papo-agradecimento`, `papo-bom-dia`, `papo-tchau`) continuam 100%
  corretos — o defeito é específico a este caso, não à precisão de contexto em geral.
  Causa: o smoke test manual do Step 6 desta mesma task (`scratch_smoke_ws.py`) mandou a
  mensagem `"oi, tudo bem?"` — **exatamente** a string de `bench/cases/papo.yaml` para
  `papo-saudacao` — contra `/ws/chat` de produção, que por padrão roda com
  `use_journal=True`. Isso escreveu uma nota de conversa real em
  `obsidian_notes/Conversas/2026-08-07_185343 — oi, tudo bem.md` (confirmada por
  inspeção direta: frontmatter com `created: 2026-08-07T18:53:43`, primeiro turno
  `**Você:** oi, tudo bem?` / `**Jade:** tudo bem, sim. e você?`). O `sync_vault()` em
  background (Task 2 deste subprojeto) indexou essa nota na sessão seguinte, e o bench
  — que por desenho consulta o índice Chroma real, não um corpus isolado (ver ressalva
  equivalente em `bench/reports/2026-08-04-001654-baseline.md`) — recuperou essa nota
  minutos depois (18:58:32) para o mesmo texto de entrada. Não é uma mudança de
  comportamento do roteador/RAG desta branch; é a mesma classe de instabilidade que o
  baseline já documentou ("recall@k não é reprodutível entre máquinas... varia conforme
  o usuário conversa"), desta vez disparada pelo próprio processo de validação da Task 7.
  **Nota para runs futuros:** o script de smoke test do Step 6 deveria usar uma
  mensagem que não colida com nenhuma `message:` de `bench/cases/*.yaml` (por exemplo,
  algo como "isso é só um teste de conexão do websocket", que não aparece em nenhum
  caso), evitando que o próprio smoke test polua o corpus do RAG antes do bench rodar.
- **As demais métricas de qualidade não regrediram.** `acerto de rota` (93,8%) e
  `recall@k` (60,0%) ficaram idênticos ao relatório anterior (delta `=`), e as duas
  falhas de `memoria` (`mem-modelo-local`, `mem-arquitetura-memoria`) e a falha de
  `tools` (`tool-negativo-coracao`) são as mesmas já conhecidas do relatório anterior
  — nenhuma nova, nenhuma corrigida. Nada nesta branch (streaming, lock de sessão,
  poda de histórico, `sync_vault` assíncrono) toca `core/memory.py` (RAG) ou
  `core/model_router.py`/`core/agent_router.py` (roteador), então este resultado é o
  esperado.
- **`llm` p50/p95 ficaram estatisticamente parecidos com a execução anterior**,
  confirmando que o refactor do núcleo de streaming (Task 3: `send()`/`stream()` sobre
  o mesmo gerador) não mudou o tempo total de geração — só como ele é consumido:
  p50 caiu de 6,586 s → 6,197 s e p95 de 16,246 s → 13,540 s (ambos levemente menores,
  dentro da variação normal de máquina para n=13; nenhuma piora). `bench/runner.py`
  continua chamando `ChatSession.send()` de forma síncrona, como sempre.
