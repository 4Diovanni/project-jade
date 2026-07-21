---
name: add-jade-tool
description: Cria uma nova habilidade (tool) do Project Jade em tools/ seguindo o contrato JadeTool e a registra no roteador. Use ao adicionar qualquer capacidade nova ao assistente (Spotify, controle do SO, e-mail, calendário, etc.).
---

# Adicionar uma nova tool ao Jade

O ponto de extensão principal do projeto: cada nova capacidade do assistente é
uma subclasse de `JadeTool`. Adicionar uma habilidade = criar um arquivo em
`tools/` + registrá-la. Nada mais precisa mudar.

## Quando usar
Sempre que o usuário pedir uma capacidade nova ("faça o Jade tocar Spotify",
"que ele leia meus e-mails", "controlar o volume do Windows").

## Passo a passo

1. **Escolha um nome** curto em `snake_case` (ex.: `spotify_play`, `system_volume`).

2. **Crie `tools/<nome>_tool.py`** com uma subclasse de `JadeTool`:

   ```python
   from tools.base import JadeTool

   class SpotifyPlayTool(JadeTool):
       name = "spotify_play"
       description = (
           "Toca música no Spotify. Use quando o usuário pedir para tocar, "
           "pausar ou pular uma música. Recebe o que tocar como texto."
       )

       def run(self, query: str) -> str:
           # Implementação real da habilidade (ex.: chamada ao Spotipy).
           ...
           return "Tocando: <resultado>"
   ```

   - `name`: identificador único, `snake_case`.
   - `description`: escrita para o **LLM** ler e decidir acionar a tool — deixe
     claro *quando* usá-la e *o que* recebe. É a parte mais importante.
   - `run(self, query: str) -> str`: sempre retorna **texto** para o agente.

3. **Registre em `tools/registry.py`**: importe a classe e adicione uma
   instância na lista `_TOOLS`.

   ```python
   from tools.spotify_tool import SpotifyPlayTool
   _TOOLS = [ObsidianSearchTool(), SpotifyPlayTool()]
   ```

4. **Configuração/segredos**: se a tool precisar de chaves (ex.: token do
   Spotify), adicione a variável no `.env.example` e leia via
   `core.config.settings` — nunca `os.getenv` solto nem chave hardcoded.

5. **Dependências**: se usar lib nova (ex.: `spotipy`), acrescente ao
   `requirements.txt`.

6. **Valide**: `python -c "from tools.registry import get_registered_tools; print([t.name for t in get_registered_tools()])"`
   deve listar a nova tool sem erro de import.

## Convenções
- Um arquivo por tool: `tools/<nome>_tool.py`.
- Identificadores em inglês; comentários/descrições em PT-BR.
- Não faça a tool imprimir na tela — ela **retorna** texto; quem fala com o
  usuário é a interface.
