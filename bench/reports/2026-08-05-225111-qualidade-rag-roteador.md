# Benchmark da Jade — 2026-08-05 22:51 · `qualidade-rag-roteador`

17 caso(s) avaliado(s) · 14 ok · 3 falhou · 6 pulado · 0 erro

## Qualidade das decisões

| Métrica | Valor | Delta |
|---|---|---|
| Acerto de rota | 93.8% | = |
| Recall@k do RAG | 60.0% | -20.0 p.p. |
| Precisão de contexto (casos `context: none`) | 100.0% | +100.0 p.p. |
| Aprovação integral dos casos | 82.4% | +17.6 p.p. |

> **Como ler:** cada métrica de qualidade cobre **apenas** os casos que declaram a expectativa correspondente, e conta só as falhas **daquela** dimensão. Um caso que roteia certo mas puxa contexto indevido conta como acerto de rota e erro de contexto. *Acerto de rota* = casos com `route`. *Recall@k* = casos com `sources_include`. *Precisão de contexto* = casos com `context: none` (os `context: any` medem cobertura, não precisão). *Aprovação integral* = casos que passaram em **todas** as suas expectativas.

### Por categoria (aprovação integral do caso)

| Categoria | Aprovação | Casos |
|---|---|---|
| humor | 100.0% | 3 |
| memoria | 66.7% | 6 |
| papo | 100.0% | 4 |
| tools | 75.0% | 4 |

### Distribuição real de rotas

| local | tool |
|---|---|
| 13 | 4 |

## Desempenho

| Etapa | p50 (s) | p95 (s) | n |
|---|---|---|---|
| `journal` | 0.000 | 0.000 | 17 |
| `llm` | 6.586 | 16.246 | 13 |
| `mood` | 0.001 | 0.002 | 17 |
| `rag_embed` | 2.094 | 2.122 | 13 |
| `rag_search` | 0.002 | 0.003 | 13 |
| `rag_sync` | 0.161 | 0.268 | 13 |
| `tool_route` | 0.000 | 0.000 | 17 |
| `tool_run` | 0.003 | 0.207 | 4 |
| `total` | 5.218 | 18.792 | 17 |

| Métrica | Valor | Delta |
|---|---|---|
| Tokens/s (local) | 32.4 | +11.27 |
| Tokens de prompt p50 | 1562 | |
| Tokens de prompt p95 | 2862 | |

## Casos que não passaram

- **`info-receita`** (conhecimento) — pulado: rota 'cloud' exige ANTHROPIC_API_KEY configurada
- **`info-explique`** (conhecimento) — pulado: rota 'cloud' exige ANTHROPIC_API_KEY configurada
- **`info-diferenca`** (conhecimento) — pulado: rota 'cloud' exige ANTHROPIC_API_KEY configurada
- **`info-por-que`** (conhecimento) — pulado: rota 'cloud' exige ANTHROPIC_API_KEY configurada
- **`info-compare`** (conhecimento) — pulado: rota 'cloud' exige ANTHROPIC_API_KEY configurada
- **`mem-modelo-local`** (memoria) — falhou: sources_include: faltou CLAUDE.md (veio: nada)
- **`mem-arquitetura-memoria`** (memoria) — falhou: sources_include: faltou projeto_jade_arquitetura.md (veio: COMO_USAR.md, obsidian_notes\Conversas\2026-07-27_202749 — Qual o meu nome e em que ano eu nasci.md, obsidian_notes\Conversas\2026-07-28_001929 — quem é o meu melhor amigo😊.md)
- **`tool-negativo-coracao`** (tools) — falhou: route: esperava 'local', veio 'tool'
- **`tool-negativo-abrir-empresa`** (tools) — pulado: rota 'cloud' exige ANTHROPIC_API_KEY configurada
