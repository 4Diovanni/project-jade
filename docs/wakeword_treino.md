# Treinando o modelo custom "Ok Jade" (openWakeWord)

O wake-word da Jade (`python main.py listen`, ver `interfaces/wakeword_service.py`)
usa [openWakeWord](https://github.com/dscripka/openWakeWord). A biblioteca só
vem com modelos prontos em **inglês** ("alexa", "hey jarvis"...) — não existe
"ok jade" pronto. Este passo a passo é **manual e externo** ao repositório:
roda num notebook Google Colab (GPU grátis), gera o arquivo `.onnx` do modelo
e você só precisa apontar o `.env` pra ele. Não é algo que o Claude Code
consiga fazer sozinho dentro deste projeto (precisa de GPU e baixa alguns GB
de datasets de treino).

## ⚠️ Aviso importante: o gerador de dados é só em inglês

A documentação oficial é explícita: *"Currently, openWakeWord only supports
English, primarily because the pre-trained text-to-speech models used to
generate training data are all based on english datasets."* Ou seja: o
notebook gera milhares de variações de "ok jade" faladas por **vozes
sintéticas em inglês**, não em PT-BR. "Ok" e "Jade" existem nos dois idiomas
com sons parecidos, então tende a funcionar razoavelmente — mas a robustez
pra sua pronúncia real (ou de quem mais usar) não é garantida de fábrica.

**Mitigação recomendada:** o próprio pipeline de treino permite misturar
**gravações reais** no dataset de exemplos positivos, além das sintéticas.
Grave você mesmo (e outras pessoas que vão usar a Jade) dizendo "ok jade"
umas 20-30 vezes, em tons/velocidades diferentes, e inclua esses `.wav` no
notebook como amostras positivas reais — isso compensa boa parte do viés de
sotaque das vozes sintéticas em inglês. Se mesmo assim o índice de "falsos
negativos" (você fala e a Jade não acorda) ficar alto, vale tentar variações
da frase (ex.: "oi jade", "okay jade") e comparar qual funciona melhor pra
você.

## Caminho avançado: treinando com suas próprias gravações reais

O notebook padrão (`automatic_model_training.ipynb`, o do passo a passo abaixo)
**não tem nenhum ponto de entrada pra áudio real** — confirmado direto no
código-fonte do notebook: ele só gera positivos via TTS sintético (vozes em
inglês) e, quando você precisa de controle total sobre os dados de entrada,
ele mesmo aponta pro notebook irmão
[`training_models.ipynb`](https://github.com/dscripka/openWakeWord/blob/main/notebooks/training_models.ipynb)
([abrir direto no Colab](https://colab.research.google.com/github/dscripka/openWakeWord/blob/main/notebooks/training_models.ipynb)).
É esse notebook — não o "completo" padrão — que aceita uma pasta qualquer de
`.wav` (inclusive suas gravações reais) como exemplos positivos.

**Aviso:** o README oficial do openWakeWord chama esse notebook de
"tutorial/educacional" e recomenda o pipeline automático pra modelos de
produção — a técnica por baixo é a mesma (extração de embeddings + classificador),
mas os defaults do notebook (poucos dados de exemplo, "turn on the office
lights") são pensados pra ensinar o processo, não pra sair pronto pra uso real.
Pra chegar num modelo utilizável você provavelmente vai precisar escalar o
volume de dados negativos/background e validar o resultado com mais cuidado
do que o notebook faz por padrão.

Passo a passo (os nomes exatos de variáveis podem variar levemente entre
versões do notebook — confira as células reais antes de editar):

1. **Grave seu áudio real.** 20-30 gravações suas dizendo "ok jade", em tons/
   velocidades/distâncias do microfone diferentes (ver aviso sobre sotaque no
   topo deste documento). Corte cada clipe pra ~1-2s em torno só da frase,
   16kHz, mono, PCM16 — é o formato que a etapa de filtragem dos positivos
   (`filter_audio_paths(..., min_length_secs=1.0, max_length_secs=2.0)`)
   espera. Junte tudo numa pasta, ex. `ok_jade_real/`.

2. **Suba a pasta pro Colab** (arrasta pro painel de arquivos da sessão, ou
   monte o Google Drive com `from google.colab import drive;
   drive.mount('/content/drive')` se quiser que sobreviva a reinícios da
   sessão).

3. **Ache a célula que prepara os positivos** — algo como:
   ```python
   positive_clips, durations = openwakeword.data.filter_audio_paths(
       ["turn_on_the_office_lights"],   # <- troque pelo caminho da sua pasta
       min_length_secs=1.0,
       max_length_secs=2.0,
       duration_method="header",
   )
   ```
   Troque `"turn_on_the_office_lights"` pelo caminho da sua pasta
   (`ok_jade_real/` ou o caminho no Drive). 20-30 clipes reais sozinhos são
   um dataset fino — se quiser mais volume, gere também variações sintéticas
   (reaproveitando as células de TTS do `automatic_model_training.ipynb`) e
   concatene as duas listas antes de seguir: `positive_clips = real_clips +
   synthetic_clips`.

4. **Rode o resto do notebook normalmente.** As células seguintes misturam
   cada positivo com ruído de fundo (`mix_clips_batch`, augmentação de SNR) e
   extraem os embeddings (`F.embed_clips`) pra um `.npy` — seus clipes reais
   passam pelo mesmo pipeline dos sintéticos, sem tratamento especial. As
   células de dados negativos não precisam de mudança (não usam sua voz).

5. **Depois de treinado o classificador**, exporte pra `.onnx` (célula de
   exportação perto do fim do notebook) e siga os passos 6-9 abaixo (baixar o
   arquivo, salvar em `database/ok_jade.onnx`, apontar o `.env`) — o restante
   do fluxo é idêntico ao caminho padrão.

## Passo a passo (caminho padrão — só dados sintéticos)

0. **Instale as dependências opcionais do wake-word** (não vêm no
   `requirements.txt` padrão — ver o motivo em `requirements-wakeword.txt`):
   ```
   pip install -r requirements-wakeword.txt
   ```

1. **Abra o notebook oficial de treino.**
   - Rápido e simples (< 1h, sem precisar mexer em código):
     [Colab — treino automático](https://colab.research.google.com/drive/1q1oe2zOyZp7UsB3jJiQ1IFn8z5YfjwEb?usp=sharing)
   - Mais controle (dataset maior, mais parâmetros): `notebooks/automatic_model_training.ipynb`
     no [repositório do openWakeWord](https://github.com/dscripka/openWakeWord).
   - Confira sempre o README do projeto — o link/nome do notebook pode mudar
     em versões futuras da lib.

2. **Configure o runtime do Colab pra usar GPU** (Ambiente de
   execução → Alterar tipo de ambiente de execução → GPU). O treino sem GPU é
   inviável em tempo razoável.

3. **Defina a frase-alvo como `ok jade`** (ou a variação que você escolher,
   ver aviso acima).

4. **(Recomendado) Inclua gravações reais suas** dizendo "ok jade" como
   exemplos positivos adicionais, junto com os sintéticos gerados
   automaticamente — ver aviso acima.

5. **Rode todas as células.** O notebook baixa os datasets de negativos
   (ruído/música/fala de fundo) automaticamente, gera as variações
   sintéticas, treina um classificador pequeno sobre o extrator de features
   congelado do openWakeWord, e exporta o modelo treinado.

6. **Baixe o arquivo `.onnx`** resultante (não o `.tflite` — no Windows só o
   `onnxruntime` é suportado; `interfaces/wakeword_service.py` já carrega o
   modelo com `inference_framework="onnx"`).

7. **Salve o arquivo no seu computador**, por exemplo em
   `database/ok_jade.onnx` (a pasta `database/` já é gitignorada — o modelo
   não deve ir pro git, é um artefato local/pessoal).

8. **Aponte o `.env`:**
   ```
   JADE_WAKEWORD_MODEL_PATH=./database/ok_jade.onnx
   JADE_WAKEWORD_ENABLED=true
   ```

9. **Teste:** `python main.py listen`. Diga "ok jade" perto do microfone —
   deve tocar o tom de ativação, gravar seu comando, tocar o tom de
   desativação e responder falando.

## Ajustando a sensibilidade

- `JADE_WAKEWORD_THRESHOLD` (default `0.5`): score mínimo (0-1) pra
  considerar detectado. Baixe se a Jade estiver "surda" (você fala e nada
  acontece); suba se ela estiver disparando à toa.
- `JADE_WAKEWORD_VAD_RMS_THRESHOLD` (default `500`): limiar de energia usado
  pra decidir quando você **parou** de falar o comando (depois da ativação).
  Suba se o microfone estiver captando ruído de fundo como se fosse fala;
  desça se estiver cortando o final de frases mais baixinhas.
- `JADE_WAKEWORD_SILENCE_MS` / `JADE_WAKEWORD_MAX_SECONDS`: quanto tempo de
  silêncio marca o fim do comando, e o teto de duração da gravação.

Como referência, os modelos oficiais do openWakeWord miram uma taxa de
falso-aceite < 0,5/hora e falso-rejeite < 5% com o threshold padrão — um
modelo custom "ok jade" provavelmente vai precisar de mais calibração manual
até chegar perto disso.
