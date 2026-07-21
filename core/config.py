"""Configuração central do Jade — lida a partir do .env.

Toda a aplicação deve importar `settings` daqui, nunca chamar os.getenv solto.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


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
    OBSIDIAN_VAULT_PATH: Path = Path(os.getenv("OBSIDIAN_VAULT_PATH", str(BASE_DIR))).resolve()

    # ── Bancos de dados ──
    CHROMA_DB_PATH: str = os.getenv("CHROMA_DB_PATH", str(BASE_DIR / "database" / "chroma_db"))
    CHROMA_COLLECTION: str = os.getenv("CHROMA_COLLECTION", "obsidian_notes")
    SQLITE_PATH: str = os.getenv("SQLITE_PATH", str(BASE_DIR / "database" / "jade.db"))

    # ── RAG (Obsidian) ──
    RAG_CHUNK_SIZE: int = int(os.getenv("RAG_CHUNK_SIZE", "800"))
    RAG_CHUNK_OVERLAP: int = int(os.getenv("RAG_CHUNK_OVERLAP", "120"))
    RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "4"))

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
