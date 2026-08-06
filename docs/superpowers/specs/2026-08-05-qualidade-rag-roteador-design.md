# Qualidade — limiar do RAG, roteador dual-model e dedup de contexto — Design

**Data:** 2026-08-05
**Status:** aprovado no brainstorming; pronto para o plano de implementação
**Escopo:** Subprojeto #3 de 4 (ver `docs/superpowers/specs/2026-08-03-regua-performance-jade-design.md`, seção "Decomposição")

## Contexto

O subprojeto #1 ("A Régua") mediu, não corrigiu. O baseline commitado em
`bench/reports/2026-08-04-001654-baseline.md` confirmou, com número, a
Hipótese 1 do spec da régua: **a rota `cloud` do roteador dual-model é
inalcançável por mecanismo**, mesmo com `ANTHROPIC_API_KEY` configurada.

A cadeia causal, medida:

1. `core/memory.py::query_memory()` pede ao ChromaDB os `k` trechos mais
   próximos (`RAG_TOP_K`, padrão 6) e **nunca lê a distância** que o Chroma
   devolve junto. Não há limiar — todo resultado do top-k é aceito.
2. Como não há limiar, o contexto recuperado **nunca vem vazio**: mesmo para
   "bom dia" e "valeu, obrigado", os 4 casos de `papo` do bench trouxeram 6
   trechos cada, nas 3 repetições, sem exceção.
3. `core/chat.py::send()` calcula `has_context=bool(context)` — sempre
   `True`.
4. `core/model_router.py::choose_route()` tem `if has_context: return
   "local"` **antes** de olhar se a mensagem é informativa. Resultado: a
   rota `cloud` nunca é escolhida em conversa. A "precisão de contexto"
   (casos `context: none`) do baseline é **0,0%**.

Um segundo defeito, menor e adjacente, também apareceu na leitura do código:
`query_memory()` monta uma entrada de prompt por chunk devolvido, mesmo
quando dois chunks vizinhos da mesma nota se sobrepõem por causa de
`RAG_CHUNK_OVERLAP=120` — texto repetido no contexto injetado no LLM.

Este spec corrige os três pontos. Ele **não** toca no problema, adjacente
mas fora de escopo, de `recall@k` não ser reprodutível entre máquinas porque
o RAG mistura documentos versionados com notas privadas de conversa — isso
fica para um subprojeto futuro (mudança de arquitetura: coleção Chroma
separada), conforme a ressalva do baseline.

## Objetivos

1. `query_memory()` filtra por distância: contexto de baixa relevância deixa
   de ser injetado no prompt, e passa a devolver `[]` quando nada relevante
   é encontrado.
2. Com `has_context` voltando a ser um sinal real, `choose_route()` passa a
   escalar para a nuvem quando de fato não há contexto pessoal envolvido —
   **sem nenhuma mudança de código no roteador**, que já está correto.
3. Chunks adjacentes da mesma nota, quando ambos sobrevivem ao filtro, não
   repetem o texto do overlap no contexto injetado.
4. `python main.py bench` comprova a correção: `context_precision` sai de
   0,0%, e a distribuição real de rotas deixa de ter `cloud: 0`.

## Não-objetivos

- **Corrigir `recall@k` não-reprodutível** (mistura de vault versionado com
  notas privadas). Mudança de arquitetura maior; subprojeto futuro.
- **Segundo corte de "contexto fraco vs forte"** para deixar perguntas
  informativas escaparem da regra de privacidade quando o contexto
  recuperado é ruim. Decisão explícita: contexto acima do limiar **sempre**
  trava a rota em `local`, mesmo que a heurística de intenção
  (`looks_informational()`) aponte para `cloud`. Privacidade prevalece.
- **Dedup semântica entre notas diferentes** (quase-duplicados que não são
  chunks vizinhos da mesma fonte). Escopo é só o overlap literal introduzido
  por `RAG_CHUNK_OVERLAP`.
- **Ferramenta de calibração permanente** do limiar em `bench/`. A
  calibração é uma investigação pontual, feita uma vez durante a
  implementação, com o número resultante documentado e fixado em config —
  não um comando reutilizável.

## Arquitetura

Mudança cirúrgica, concentrada em um arquivo e uma setting nova. Nenhuma
mudança em `core/model_router.py` ou `core/chat.py` — o roteador dual-model
já decide certo; ele só nunca recebeu um `has_context` que pudesse ser
`False`.

```
core/chat.py::_retrieve_context()
       │
       └──> core/memory.py::query_memory()  ← única função que muda
                   │
                   ├─ Chroma devolve top-k COM distâncias (já disponíveis,
                   │  hoje não lidas)
                   ├─ filtro: descarta distance > settings.RAG_MAX_DISTANCE
                   ├─ merge: funde chunks adjacentes da mesma fonte que se
                   │  sobrepõem (string matching, não tamanho fixo)
                   └─ devolve list[str] — [] quando nada sobrevive

core/model_router.py::choose_route()  ← ZERO mudança de código
       (já decide "local" se has_context, "cloud" se informativa e livre)
```

## Componentes

### `core/config.py`

Nova setting, no padrão das demais entradas de RAG:

```python
# Distância máxima (Chroma) para um trecho contar como contexto relevante.
# Acima disso, o trecho é descartado — ver docs/superpowers/specs/2026-08-05-qualidade-rag-roteador-design.md.
RAG_MAX_DISTANCE: float = float(os.getenv("RAG_MAX_DISTANCE", "0.0"))  # placeholder — ver "Calibração"
```

`"0.0"` acima é um placeholder ilustrativo, não o valor final: o número real
só existe depois da medição descrita em "Calibração" abaixo, porque exige
rodar o filtro contra distâncias reais do Chroma. A task de implementação
substitui esse placeholder pelo valor calibrado antes de considerar o
trabalho concluído — não é um TODO deixado em aberto no código entregue.

### `core/memory.py::query_memory()`

Reescrita do miolo da função, mantendo a assinatura e o contrato de retorno
(`list[str]`, vazio quando não há nada indexado ou nada relevante):

1. `collection.query(query_embeddings=[q_emb], n_results=k)` passa a também
   ler `res.get("distances")` (o Chroma já devolve; hoje é ignorado).
2. Para cada `(doc, meta, distance)`: descarta se `distance >
   settings.RAG_MAX_DISTANCE`. Se `distances` vier ausente da resposta
   (defensivo — não deveria acontecer), o chunk é mantido sem filtro, para
   nunca descartar contexto por um bug silencioso de parsing.
3. Agrupa os sobreviventes por `meta["source"]`; dentro de cada fonte,
   ordena por `meta["chunk"]`.
4. Para pares consecutivos `(chunk: i, chunk: i+1)` da mesma fonte: calcula
   o maior sufixo do texto de `i` que é também prefixo do texto de `i+1`
   (comparação de string real — o `RecursiveCharacterTextSplitter` usado em
   `chunk_text()` não garante overlap de tamanho exato, porque respeita
   separadores). Funde os dois em um bloco só, sob uma entrada `[fonte]\n…`,
   sem repetir o trecho sobreposto. Chunks não-adjacentes ou de fontes
   diferentes não se fundem.
5. `note(chunks=len(out), sources=sources)` continua exatamente como hoje —
   mas `chunks` agora pode ser `0`, o que antes era estruturalmente
   impossível.

### `core/model_router.py`, `core/chat.py`

Nenhuma edição. `has_context=bool(context)` em `chat.py` passa a carregar
sinal real assim que `query_memory()` pode devolver `[]`; `choose_route()`
já trata isso corretamente.

### `.env.example`

Entrada nova, documentada, ao lado de `RAG_TOP_K`.

## Fluxo de dados

```
mensagem do usuário
  → chat.py::_retrieve_context()
    → memory.py::query_memory(mensagem)
      → Chroma: top-k + distâncias
      → filtro por RAG_MAX_DISTANCE
      → merge de chunks adjacentes
      → [] ou list[str]
  → chat.py: has_context = bool(context)
  → model_router.py::choose_route(mensagem, has_context, cloud_available)
      has_context=True  → sempre "local" (privacidade)
      has_context=False → "cloud" se looks_informational(), senão "local"
```

A fronteira entre as duas peças não muda: o roteador nunca vê distância, só
o booleano `has_context`. Isso preserva a separação de responsabilidades já
existente (RAG decide relevância; roteador decide modelo).

## Calibração do limiar

Não é código de produção — é uma investigação feita uma vez durante a
implementação, com o resultado documentado no relatório da task e fixado em
config:

1. Rodar os 51 casos do bench (`bench/cases/`) com o filtro de distância
   **desligado** (ou um limiar permissivo o bastante para não descartar
   nada), capturando a distância real de cada trecho retornado.
2. Separar as distâncias em dois grupos: os 4 casos `papo-*`
   (`context: none` — deveriam vir vazios) contra os casos `memoria`
   (`sources_include` — deveriam vir com o trecho certo).
3. Escolher o corte que separa os dois grupos. Se os grupos não separarem
   limpo (overlap de distâncias entre "deveria ter contexto" e "não
   deveria"), isso é um achado a reportar, não a esconder — documentar no
   relatório da task com as distâncias observadas.
4. Fixar o número escolhido em `RAG_MAX_DISTANCE` (`.env.example` e o
   default em `core/config.py`).

## Tratamento de erros

`query_memory()` já é chamada dentro de `try/except Exception: return ""`
em `chat.py::_retrieve_context()` — nenhuma mudança de tratamento de erro é
necessária. O filtro por distância e o merge de chunks adjacentes são
código puro (sem I/O novo, sem chamada de rede nova), então não introduzem
uma nova classe de falha observável em produção.

## Testes

Unitários em `tests/test_memory.py`, com Chroma mockado (sem depender de
Ollama/embeddings reais):

- Chunk com `distance <= RAG_MAX_DISTANCE` sobrevive ao filtro; chunk com
  `distance > RAG_MAX_DISTANCE` é descartado; todos acima do limiar → lista
  vazia (`has_context` ficaria `False` a jusante).
- Merge: dois chunks da mesma fonte, `chunk: i` e `chunk: i+1`, com
  sufixo/prefixo sobrepostos, viram um único bloco sem o texto repetido.
- Não-fusão: chunks não-adjacentes (`chunk: 0` e `chunk: 5`) da mesma fonte
  não se fundem; chunks de fontes diferentes não se fundem, mesmo se o texto
  coincidir.
- Chunk sem par adjacente sobrevivente passa intocado, sem tentativa de
  merge.
- A função de merge é testável isoladamente com strings sintéticas, sem
  precisar do `RecursiveCharacterTextSplitter` real.
- Ramo defensivo: resposta do Chroma sem a chave `distances` (ou vazia) não
  filtra nada — todos os chunks do top-k sobrevivem, como hoje.

Fim-a-fim, em `tests/test_chat.py` e/ou `tests/test_model_router.py`:

- Com `query_memory` mockado para devolver `[]`, `cloud_available=True` e
  uma mensagem informativa (`looks_informational() == True`): a rota
  escolhida é `cloud`. **Hoje esse teste não é escrevível** — `has_context`
  nunca é `False` no caminho real.
- Com contexto não-vazio, mesmo com mensagem informativa: a rota continua
  `local` — a regra de privacidade (contexto trava local, sempre) permanece
  coberta.

Validação de sistema, não parte da suíte automatizada: depois da
implementação, rodar `python main.py bench` e comparar o novo relatório
contra o baseline commitado
(`bench/reports/2026-08-04-001654-baseline.md`) via a coluna de Delta que o
formato de relatório já suporta. A evidência esperada: `context_precision`
sobe de 0,0%, e a distribuição real de rotas deixa de ter `cloud` zerado
quando `ANTHROPIC_API_KEY` está configurada.

## Entregável

- `core/config.py`: setting `RAG_MAX_DISTANCE`, com o valor calibrado.
- `core/memory.py`: `query_memory()` com filtro por distância e merge de
  chunks adjacentes.
- `.env.example`: entrada documentada para `RAG_MAX_DISTANCE`.
- Testes novos em `tests/test_memory.py` e `tests/test_chat.py` /
  `tests/test_model_router.py` cobrindo os pontos acima.
- Novo relatório de bench pós-implementação, com Delta contra o baseline
  commitado.
- Este spec e o plano de implementação, commitados em
  `docs/superpowers/`.

## Riscos

- **O corte pode não separar os grupos com limpeza.** Se distâncias de
  "deveria ter contexto" e "não deveria" se sobrepuserem, qualquer limiar
  fixo vai errar alguns casos dos dois lados. Mitigação: reportar o overlap
  observado explicitamente no relatório da task, em vez de escolher um
  número que pareça bom sem declarar a imprecisão.
- **O limiar é específico do embedder atual (`nomic-embed-text`).** Trocar
  de modelo de embedding invalida o número calibrado sem aviso — não há
  teste que capture isso, porque é uma propriedade estatística do espaço
  vetorial, não do código. Fica registrado aqui para quando essa troca
  acontecer.
- **Filtrar contexto pode reduzir recall@k** em casos legítimos que hoje
  passam por sorte (a nota certa está no top-k, mas com distância alta).
  Esperado e aceitável — é a mesma tensão que motivou este subprojeto: hoje
  o recall alto é parcialmente um artefato de nunca filtrar nada.
