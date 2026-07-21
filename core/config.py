"""Configuração central do Jade — lida a partir do .env.

Toda a aplicação deve importar `settings` daqui, nunca chamar os.getenv solto.
"""

from __future__ import annotations

import os
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


class Settings:
    # ── LLM ──
    LLM_PROVIDER: str = os.getenv("JADE_LLM_PROVIDER", "ollama")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3")
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_EMBED_MODEL: str = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    # ── Obsidian ──
    OBSIDIAN_VAULT_PATH: Path = _resolve_path(os.getenv("OBSIDIAN_VAULT_PATH", ""), BASE_DIR)
    # Subpasta do vault onde as conversas com o Jade viram notas .md.
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
    RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "4"))

    # ── Voz (Fase 3) ──
    # STT local (faster-whisper): tiny|base|small|medium|large-v3
    WHISPER_MODEL: str = os.getenv("JADE_WHISPER_MODEL", "base")
    WHISPER_LANGUAGE: str = os.getenv("JADE_WHISPER_LANGUAGE", "pt")
    # TTS: "edge" (online, alta qualidade) ou "pyttsx3" (100% offline)
    TTS_BACKEND: str = os.getenv("JADE_TTS_BACKEND", "edge")
    TTS_VOICE: str = os.getenv("JADE_TTS_VOICE", "pt-BR-FranciscaNeural")
    # Onde os áudios gerados pelo Jade são salvos (padrão: subpasta do vault,
    # visível no Obsidian). São .mp3 (backend edge) consumíveis por ele e por você.
    AUDIO_OUTPUT_DIR: Path = _resolve_path(
        os.getenv("JADE_AUDIO_DIR", ""), OBSIDIAN_VAULT_PATH / "Áudios"
    )

    # ── Tools / Mãos (Fase 4) ──
    # Liga/desliga o controle do sistema operacional (abrir apps, volume...).
    SYSTEM_TOOL_ENABLED: bool = (
        os.getenv("JADE_SYSTEM_TOOL_ENABLED", "true").strip().lower() != "false"
    )

    # ── Roteador dual-model (llama3 local + Claude na nuvem) ──
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

    # Pastas/arquivos do vault que NUNCA devem ser indexados no RAG.
    VAULT_IGNORE: set[str] = {
        ".obsidian",
        ".claude",
        ".git",
        "database",
        "__pycache__",
        ".venv",
        "venv",
        "node_modules",
    }


settings = Settings()
