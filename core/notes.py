"""Utilitários de notas Markdown do vault (frontmatter, corpo)."""

from __future__ import annotations

import re
from pathlib import Path

_FRONTMATTER = re.compile(r"^---\n.*?\n---\n", re.DOTALL)


def strip_frontmatter(text: str) -> str:
    """Remove o bloco de frontmatter YAML do início do texto, se houver."""
    return _FRONTMATTER.sub("", text, count=1)


def read_body(path: str | Path) -> str:
    """Lê o corpo de uma nota (sem frontmatter). '' se o arquivo não existe."""
    p = Path(path)
    if not p.exists():
        return ""
    return strip_frontmatter(p.read_text(encoding="utf-8", errors="ignore")).strip()
