"""Diário de conversas do Jade — persiste cada conversa como nota .md no vault
do Obsidian.

Cada sessão vira uma nota com frontmatter (título, data, tags) e uma tag
aninhada `#conversa/AAAA-MM-DD`, além de um link para o hub `[[Jade — Memória]]`.
Assim o grafo do Obsidian conecta as conversas por grupo, data e título — e,
ao reindexar o vault, o próprio histórico entra no RAG (a memória do Jade é,
literalmente, o Obsidian do usuário).
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from core.config import settings

_MOC_NOTE = "Jade — Memória.md"
_INVALID_FS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _first_line(text: str) -> str:
    for line in text.strip().splitlines():
        if line.strip():
            return line.strip()
    return "conversa"


def _title_from(message: str, max_len: int = 60) -> str:
    title = re.sub(r"\s+", " ", _first_line(message))
    return (title[:max_len]).strip() or "conversa"


def _safe_filename(text: str) -> str:
    # Windows não permite ponto/espaço no fim do nome de arquivo.
    cleaned = _INVALID_FS.sub("", text).strip().rstrip(". ")
    return cleaned or "conversa"


class ConversationJournal:
    """Registra uma sessão de conversa numa nota Markdown do vault do Obsidian."""

    def __init__(self, vault: Path | None = None, when: datetime | None = None) -> None:
        self._vault = vault or settings.OBSIDIAN_VAULT_PATH
        self._started = when or datetime.now()
        self._title: str | None = None
        self._turns: list[tuple[str, str]] = []
        self._path: Path | None = None

    @property
    def path(self) -> Path | None:
        return self._path

    def record(self, user_message: str, jade_reply: str) -> Path:
        """Adiciona um turno (pergunta + resposta) e (re)escreve a nota."""
        if self._title is None:
            self._title = _title_from(user_message)
            self._path = self._build_path()
        self._turns.append((user_message, jade_reply))
        self._path.write_text(self._render(), encoding="utf-8")
        return self._path

    # ── internos ──
    def _build_path(self) -> Path:
        folder = self._vault / settings.CONVERSATIONS_SUBDIR
        folder.mkdir(parents=True, exist_ok=True)
        self._ensure_moc()
        stamp = self._started.strftime("%Y-%m-%d_%H%M%S")
        name = f"{stamp} — {_safe_filename(self._title or 'conversa')}.md"
        return folder / name

    def _ensure_moc(self) -> None:
        moc = self._vault / _MOC_NOTE
        if moc.exists():
            return
        moc.write_text(
            "---\ntags: [jade, moc]\n---\n\n"
            "# Jade — Memória\n\n"
            "Hub das conversas com o Jade. Elas ficam na pasta "
            f"`{settings.CONVERSATIONS_SUBDIR}/` e usam a tag `#conversa`.\n",
            encoding="utf-8",
        )

    def _render(self) -> str:
        title = (self._title or "conversa").replace('"', "'")
        date = self._started.strftime("%Y-%m-%d")
        frontmatter = (
            "---\n"
            f'title: "{title}"\n'
            f"data: {date}\n"
            f"created: {self._started.isoformat(timespec='seconds')}\n"
            f"updated: {datetime.now().isoformat(timespec='seconds')}\n"
            f"turnos: {len(self._turns)}\n"
            "tags: [conversa, jade]\n"
            "---\n\n"
        )
        header = f"# {title}\n\nConversa com o Jade · [[Jade — Memória]] · #conversa/{date}\n\n"
        body = "\n".join(f"**Você:** {user}\n\n**Jade:** {reply}\n" for user, reply in self._turns)
        return frontmatter + header + body
