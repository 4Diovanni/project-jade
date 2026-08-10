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

## Passo a passo

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
