"""Configuração central do Jade — lida a partir do .env.

Toda a aplicação deve importar `settings` daqui, nunca chamar os.getenv solto.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _resolve_path(value: str, default: Path) -> Path:
    """Resolve um caminho vindo do .env: remove espaços e ancora caminhos
    relativos no diretório do projeto (BASE_DIR), não no CWD de execução."""
    raw = (value or "").strip()
    if not raw:
        return default
    path = Path(raw)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path.resolve()


def _default_desktop_dir() -> Path:
    """Resolve a Área de Trabalho real do usuário no Windows.

    Não usa `Path.home() / "Desktop"` direto porque a pasta pode estar
    redirecionada (ex.: para dentro do OneDrive, como neste próprio ambiente)
    — o valor correto vem do registro (User Shell Folders), que já resolve
    esse redirecionamento e variáveis de ambiente no caminho."""
    if sys.platform == "win32":
        import contextlib
        import winreg

        with contextlib.suppress(OSError):
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
            )
            raw, _ = winreg.QueryValueEx(key, "Desktop")
            return Path(os.path.expandvars(raw))
    return Path.home() / "Desktop"


class Settings:
    # ── LLM ──
    LLM_PROVIDER: str = os.getenv("JADE_LLM_PROVIDER", "ollama")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen3:8b")
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_EMBED_MODEL: str = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    # Janela de contexto. O default do Ollama (2k–4k) trunca em silêncio o
    # system prompt + histórico + trechos do RAG — a Jade "esquecia" o vault.
    # 10240 foi calibrado numa RX 6600 (8 GB): é o maior valor em que o qwen3:8b
    # ainda carrega 100% na VRAM (~6,0 GB). Acima disso o Ollama joga camadas na
    # CPU e a geração cai pela metade (16384 → 18 tok/s vs 37 tok/s aqui).
    # Numa GPU com mais VRAM, aumente à vontade.
    OLLAMA_NUM_CTX: int = int(os.getenv("OLLAMA_NUM_CTX", "10240"))
    # Temperatura do papo solto (persona, criatividade).
    OLLAMA_TEMPERATURE: float = float(os.getenv("OLLAMA_TEMPERATURE", "0.7"))
    # Temperatura quando a resposta deve se ancorar em fatos (RAG/tools):
    # baixa = cita o vault em vez de inventar.
    OLLAMA_GROUNDED_TEMPERATURE: float = float(os.getenv("OLLAMA_GROUNDED_TEMPERATURE", "0.2"))
    # Modo "thinking" do Qwen3: desligado por padrão. Ligado, ele gera um bloco
    # de raciocínio antes de responder — mata a latência do chat e polui a fala
    # da Jade. Modelos sem thinking (llama3) ignoram o parâmetro sem erro.
    OLLAMA_THINKING: bool = os.getenv("OLLAMA_THINKING", "false").strip().lower() == "true"
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    # ── Sessão / histórico ──
    # Quantas trocas (pergunta+resposta) ficam no histórico ativo do prompt.
    # Turnos mais antigos saem do prompt mas continuam na nota do Obsidian
    # (journal) e no RAG — nada se perde de memória de longo prazo, só sai do
    # contexto ativo enviado ao LLM a cada turno.
    HISTORY_MAX_TURNS: int = int(os.getenv("HISTORY_MAX_TURNS", "20"))

    # ── Obsidian ──
    # Raiz do que a Jade LÊ (RAG). Apontar para a raiz do repo faz ela enxergar
    # os documentos do próprio projeto (arquitetura, README) além das notas.
    OBSIDIAN_VAULT_PATH: Path = _resolve_path(os.getenv("OBSIDIAN_VAULT_PATH", ""), BASE_DIR)
    # Onde a Jade ESCREVE (conversas, notas internas, áudios). Fica separado do
    # vault de leitura de propósito: com o vault na raiz do repo, escrever ali
    # jogaria conversas pessoais dentro do git. `obsidian_notes/` é gitignorado.
    # Default = o próprio vault, para não mudar o comportamento de quem não seta.
    NOTES_DIR: Path = _resolve_path(os.getenv("JADE_NOTES_DIR", ""), OBSIDIAN_VAULT_PATH)
    # Subpasta de NOTES_DIR onde as conversas com o Jade viram notas .md.
    CONVERSATIONS_SUBDIR: str = os.getenv("JADE_CONVERSATIONS_SUBDIR", "Conversas")
    # Persistir cada conversa em Markdown no vault (memória de longo prazo).
    JOURNAL_ENABLED: bool = os.getenv("JADE_JOURNAL_ENABLED", "true").strip().lower() != "false"

    # ── Bancos de dados ──
    CHROMA_DB_PATH: str = os.getenv("CHROMA_DB_PATH", str(BASE_DIR / "database" / "chroma_db"))
    CHROMA_COLLECTION: str = os.getenv("CHROMA_COLLECTION", "obsidian_notes")
    SQLITE_PATH: str = os.getenv("SQLITE_PATH", str(BASE_DIR / "database" / "jade.db"))

    # ── RAG (Obsidian) ──
    RAG_CHUNK_SIZE: int = int(os.getenv("RAG_CHUNK_SIZE", "800"))
    RAG_CHUNK_OVERLAP: int = int(os.getenv("RAG_CHUNK_OVERLAP", "120"))
    # 6 trechos cabem com folga em OLLAMA_NUM_CTX; com 4 a Jade perdia notas
    # relevantes que ficavam logo abaixo do corte.
    RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "6"))

    # Distância máxima (Chroma, espaço cosine — ver `_get_collection()`) para um
    # trecho contar como contexto relevante. Acima disso, é descartado.
    # Calibrado em bench/cases/papo.yaml (context: none) vs bench/cases/memoria.yaml
    # (sources_include) — ver docs/superpowers/specs/2026-08-05-qualidade-rag-roteador-design.md.
    RAG_MAX_DISTANCE: float = float(os.getenv("RAG_MAX_DISTANCE", "0.32"))

    # ── Voz (Fase 3) ──
    # STT local (faster-whisper): tiny|base|small|medium|large-v3
    # "small" troca um pouco de velocidade por acurácia bem maior que "base" —
    # calibrado depois de erros como "toque" no lugar de "toca" e "ja de" no
    # lugar de "Jade" (ver docs/superpowers/specs/2026-08-09-wakeword-precisao-voz-design.md).
    WHISPER_MODEL: str = os.getenv("JADE_WHISPER_MODEL", "small")
    WHISPER_LANGUAGE: str = os.getenv("JADE_WHISPER_LANGUAGE", "pt")
    # Viés de vocabulário do Whisper: nomes próprios/termos que ele tende a
    # errar sem contexto (técnica oficial do initial_prompt).
    WHISPER_PROMPT: str = os.getenv(
        "JADE_WHISPER_PROMPT", "Jade, tocar, Spotify, playlist, música."
    )
    # TTS: "edge" (online, alta qualidade) ou "pyttsx3" (100% offline)
    TTS_BACKEND: str = os.getenv("JADE_TTS_BACKEND", "edge")
    TTS_VOICE: str = os.getenv("JADE_TTS_VOICE", "pt-BR-ThalitaMultilingualNeural")
    # Prosódia do backend "edge" (formato do próprio edge-tts): rate em %
    # relativo à velocidade natural da voz ("+0%", "-10%", "+15%") e pitch em
    # Hz relativo ao tom natural ("+0Hz", "-20Hz"). Ajuda a tirar o tom "robô"
    # de vozes muito neutras/planas.
    TTS_RATE: str = os.getenv("JADE_TTS_RATE", "+0%")
    TTS_PITCH: str = os.getenv("JADE_TTS_PITCH", "+0Hz")
    # Onde os áudios gerados pelo Jade são salvos (padrão: subpasta do vault,
    # visível no Obsidian). São .mp3 (backend edge) consumíveis por ele e por você.
    AUDIO_OUTPUT_DIR: Path = _resolve_path(os.getenv("JADE_AUDIO_DIR", ""), NOTES_DIR / "Áudios")

    # ── Wake-word "Ok Jade" (python main.py listen) ──
    # Desligado por padrão: exige um modelo openWakeWord custom treinado à
    # parte (não existe "ok jade" pronto) — ver docs/wakeword_treino.md.
    WAKEWORD_ENABLED: bool = os.getenv("JADE_WAKEWORD_ENABLED", "true").strip().lower() == "true"
    WAKEWORD_MODEL_PATH: str = os.getenv("JADE_WAKEWORD_MODEL_PATH", "")
    # Score mínimo (0-1) do openWakeWord para considerar "ok jade" detectado.
    WAKEWORD_THRESHOLD: float = float(os.getenv("JADE_WAKEWORD_THRESHOLD", "0.01"))
    # Silêncio contínuo (ms) após a ativação que marca o fim do comando.
    WAKEWORD_SILENCE_MS: int = int(os.getenv("JADE_WAKEWORD_SILENCE_MS", "1200"))
    # Teto de duração (s) do comando gravado após a ativação — nunca escuta pra sempre.
    WAKEWORD_MAX_SECONDS: int = int(os.getenv("JADE_WAKEWORD_MAX_SECONDS", "12"))
    # Limiar de energia (RMS, escala int16) que marca um frame como "fala" no
    # endpointing do comando. Suba se o microfone captar ruído de fundo como
    # fala; desça se estiver cortando o final de frases baixinhas.
    WAKEWORD_VAD_RMS_THRESHOLD: float = float(os.getenv("JADE_WAKEWORD_VAD_RMS_THRESHOLD", "500"))

    # ── Tools / Mãos (Fase 4) ──
    # Liga/desliga o controle do sistema operacional (abrir apps, volume...).
    SYSTEM_TOOL_ENABLED: bool = (
        os.getenv("JADE_SYSTEM_TOOL_ENABLED", "true").strip().lower() != "false"
    )
    # Criação/escrita de arquivos por contexto (Issue #63).
    FILES_TOOL_ENABLED: bool = (
        os.getenv("JADE_FILES_TOOL_ENABLED", "true").strip().lower() != "false"
    )
    # Onde os arquivos criados pela Jade são salvos. Default = Área de
    # Trabalho real do usuário (ver `_default_desktop_dir`); configurável
    # para restringir a outra pasta.
    FILES_TOOL_BASE_DIR: Path = _resolve_path(
        os.getenv("JADE_FILES_BASE_DIR", ""), _default_desktop_dir()
    )

    # ── Roteador dual-model (Qwen3 local + Claude na nuvem) ──
    # Provider "nuvem" para perguntas complexas/informativas.
    CLOUD_PROVIDER: str = os.getenv("JADE_CLOUD_PROVIDER", "anthropic")
    # Modelo do Claude. Precisa de ANTHROPIC_API_KEY (≠ assinatura Claude Pro).
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-8")
    # Liga o roteamento; só escala para a nuvem se houver chave (senão fica local).
    ROUTER_ENABLED: bool = os.getenv("JADE_ROUTER_ENABLED", "true").strip().lower() != "false"

    # ── Personalidade & memória viva ──
    # Dono da Jade — o comportamento dela é voltado a esta pessoa.
    USER_NAME: str = os.getenv("JADE_USER_NAME", "Giovanni")
    # Notas de estado (no vault, visíveis no Obsidian, privadas/gitignoradas).
    PERSONALITY_NOTE: str = os.getenv("JADE_PERSONALITY_NOTE", "Jade — Personalidade.md")
    MOOD_NOTE: str = os.getenv("JADE_MOOD_NOTE", "Jade — Humor.md")
    PROFILE_NOTE: str = os.getenv("JADE_PROFILE_NOTE", "Sobre o Usuário.md")
    # Extrair fatos do usuário (via LLM) ao encerrar/limpar uma conversa.
    PROFILE_UPDATE_ENABLED: bool = (
        os.getenv("JADE_PROFILE_UPDATE", "true").strip().lower() != "false"
    )

    # ── API ──
    API_HOST: str = os.getenv("JADE_API_HOST", "127.0.0.1")
    API_PORT: int = int(os.getenv("JADE_API_PORT", "8000"))

    # ── Spotify (Fase 4) ──
    # Credenciais do app registrado no Spotify Developer Dashboard.
    SPOTIFY_CLIENT_ID: str = os.getenv("SPOTIFY_CLIENT_ID", "")
    SPOTIFY_CLIENT_SECRET: str = os.getenv("SPOTIFY_CLIENT_SECRET", "")
    # Precisa bater EXATAMENTE com o Redirect URI cadastrado no Dashboard.
    SPOTIFY_REDIRECT_URI: str = os.getenv(
        "SPOTIFY_REDIRECT_URI", f"http://{API_HOST}:{API_PORT}/spotify/callback"
    )
    # Token OAuth persistido localmente — nunca vai pro git (ver .gitignore).
    SPOTIFY_TOKEN_CACHE_PATH: str = os.getenv(
        "SPOTIFY_TOKEN_CACHE_PATH", str(BASE_DIR / "database" / "spotify_token.json")
    )
    # Acima disso (em horas), o cache local de faixas é considerado velho e
    # sync_library() refaz a busca completa na próxima chamada.
    SPOTIFY_LIBRARY_STALE_HOURS: int = int(os.getenv("SPOTIFY_LIBRARY_STALE_HOURS", "24"))
    SPOTIFY_TOOL_ENABLED: bool = (
        os.getenv("JADE_SPOTIFY_TOOL_ENABLED", "true").strip().lower() != "false"
    )

    # Pastas/arquivos do vault que NUNCA devem ser indexados no RAG.
    # Comparado contra CADA parte do caminho relativo, então serve tanto para
    # pastas quanto para nomes de arquivo soltos.
    VAULT_IGNORE: set[str] = {
        # Infra do Obsidian / do agente
        ".obsidian",
        ".claude",
        ".github",
        # Controle de versão e ambientes
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        # Caches de ferramentas (geram .md/.txt de relatório que viram ruído)
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "htmlcov",
        "dist",
        "build",
        # Dados gerados em runtime
        "database",
        # Pastas de código: os .md que vivem nelas são doc técnica de módulo,
        # não conhecimento que a Jade precise ter na ponta da língua.
        "core",
        "tools",
        "interfaces",
        "tests",
        "scripts",
        # Saída do benchmark (bench/reports/): indexar os relatórios contaminaria
        # a própria métrica que o benchmark mede (recall@k infla ao "achar" as
        # respostas esperadas de execuções passadas).
        "bench",
        # Planos e specs de implementação (artefatos de processo). São longos e
        # sozinhos chegaram a 31% do índice, competindo com o resto. A Jade
        # conhece o projeto por README/CLAUDE/arquitetura, que ficam na raiz.
        # Tire daqui se quiser que ela leia o histórico de implementação.
        "docs",
        # Manifestos de dependência: texto sem valor semântico para a Jade
        "requirements.txt",
        "requirements-dev.txt",
    }


settings = Settings()
