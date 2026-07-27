"""Diário de conversas do Jade — persiste cada conversa como nota .md no vault
do Obsidian.

Cada sessão vira uma nota com frontmatter (título, data, tags) e uma tag
aninhada `#conversa/AAAA-MM-DD`, além de um link para o hub `[[Jade — Memória]]`.
Assim o grafo do Obsidian conecta as conversas por grupo, data e título — e,
ao reindexar o vault, o próprio histórico entra no RAG (a memória do Jade é,
literalmente, o Obsidian do usuário).
"""

from __future__ import annotations

import contextlib
import re
from datetime import datetime
from pathlib import Path

from core.config import settings
from core.notes import strip_frontmatter

_MOC_NOTE = "Jade — Memória.md"
_INVALID_FS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_TURN_RE = re.compile(
    r"\*\*(Você|Jade):\*\*\s*(.*?)(?=\n\*\*(?:Você|Jade):\*\*|\Z)",
    re.DOTALL,
)


def parse_conversation_note(text: str) -> list[dict[str, str]]:
    """Extrai os turnos (pergunta/resposta) do corpo de uma nota de conversa.

    Lê o formato gerado por `ConversationJournal._render` (blocos
    `**Você:** …` / `**Jade:** …`). Ignora frontmatter e cabeçalho. Um turno é
    um par Você→Jade; um 'Você' sem 'Jade' seguinte é descartado."""
    body = strip_frontmatter(text)
    turns: list[dict[str, str]] = []
    pending_user: str | None = None
    for role, content in _TURN_RE.findall(body):
        content = content.strip()
        if role == "Você":
            pending_user = content
        elif pending_user is not None:
            turns.append({"user": pending_user, "jade": content})
            pending_user = None
    return turns


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
        # Notas são ESCRITAS em NOTES_DIR (gitignorado), não na raiz do vault
        # de leitura — que pode ser a raiz do repositório.
        self._vault = vault or settings.NOTES_DIR
        self._started = when or datetime.now()
        self._title: str | None = None
        self._turns: list[tuple[str, str]] = []
        self._path: Path | None = None
        self._related: list[str] = []

    @property
    def path(self) -> Path | None:
        return self._path

    def record(self, user_message: str, jade_reply: str) -> Path:
        """Adiciona um turno (pergunta + resposta) e (re)escreve a nota."""
        if self._title is None:
            self._title = _title_from(user_message)
            self._path = self._build_path()
            self._related = self._find_related(user_message)
        self._turns.append((user_message, jade_reply))
        self._path.write_text(self._render(), encoding="utf-8")
        return self._path

    def finalize(self) -> None:
        """Indexa a conversa no RAG — chamado ao ENCERRAR a conversa.

        Indexar só no fim evita o loop em que a conversa em andamento é
        recuperada e re-injetada no contexto (respostas se repetindo)."""
        self._index_self()

    # ── internos ──
    def _find_related(self, seed: str) -> list[str]:
        """Conversas passadas mais parecidas (por tema) — best-effort."""
        if self._vault != settings.NOTES_DIR:
            return []  # vault de teste: não toca no RAG real
        with contextlib.suppress(Exception):
            from core.memory import related_sources

            # `exclude` é casado contra o `source` do RAG, que é relativo ao
            # vault de LEITURA — não ao diretório de notas.
            exclude = (
                str(self._path.resolve().relative_to(settings.OBSIDIAN_VAULT_PATH))
                if self._path
                else None
            )
            return related_sources(seed, k=3, exclude=exclude)
        return []

    def _index_self(self) -> None:
        """Indexa esta conversa no RAG para virar memória entre chats — best-effort."""
        if self._vault != settings.NOTES_DIR:
            return
        with contextlib.suppress(Exception):
            from core.memory import index_note

            if self._path is not None:
                index_note(self._path)

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
        header = f"# {title}\n\nConversa com o Jade · [[Jade — Memória]] · #conversa/{date}\n"
        if self._related:
            links = " · ".join(f"[[{Path(s).stem}]]" for s in self._related)
            header += f"Relacionadas: {links}\n"
        header += "\n"
        body = "\n".join(f"**Você:** {user}\n\n**Jade:** {reply}\n" for user, reply in self._turns)
        return frontmatter + header + body
