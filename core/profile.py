"""Perfil do usuário — o que a Jade sabe sobre o dono dela.

Guardado em `Sobre o Usuário.md` no vault. A Jade lê este perfil sempre (para
personalizar) e o atualiza com o tempo, extraindo fatos duráveis das conversas
via LLM (chamado nos limites de conversa, não a cada turno).
"""

from __future__ import annotations

from pathlib import Path

from core.config import settings
from core.notes import read_body


def _path() -> Path:
    return settings.OBSIDIAN_VAULT_PATH / settings.PROFILE_NOTE


def ensure_profile() -> None:
    p = _path()
    if p.exists():
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "---\ntags: [jade, perfil]\n---\n\n"
        f"# Sobre {settings.USER_NAME}\n\n"
        f"- Nome: {settings.USER_NAME} (é sempre quem conversa com a Jade)\n",
        encoding="utf-8",
    )


def load_profile() -> str:
    return read_body(_path())


def _existing_facts() -> set[str]:
    out = set()
    for line in load_profile().splitlines():
        s = line.strip()
        if s.startswith(("-", "•")):
            out.add(s.lstrip("-• ").strip().lower())
    return out


def add_facts(facts: list[str]) -> int:
    """Anexa fatos novos (sem duplicar). Retorna quantos foram adicionados."""
    ensure_profile()
    have = _existing_facts()
    new = []
    for f in facts:
        clean = f.strip().lstrip("-• ").strip()
        if clean and clean.lower() not in have:
            new.append(clean)
            have.add(clean.lower())
    if not new:
        return 0
    with _path().open("a", encoding="utf-8") as fh:
        for f in new:
            fh.write(f"- {f}\n")
    return len(new)


def _parse_facts(text: str) -> list[str]:
    if text.strip().lower().startswith("nada"):
        return []
    return [
        ln.lstrip("-• ").strip() for ln in text.splitlines() if ln.strip().startswith(("-", "•"))
    ]


def update_from_conversation(conversation: str, llm) -> int:
    """Extrai fatos duráveis sobre o usuário da conversa (via LLM) e mescla."""
    user = settings.USER_NAME
    prompt = (
        f"Analise a conversa abaixo e liste, em bullets curtos e concretos, APENAS "
        f"fatos DURÁVEIS sobre {user} (gostos, interesses, personalidade, preferências, "
        f"jeito de perguntar). Um fato por linha começando com '- '. Ignore o que for "
        f"passageiro. Se não houver nada novo e relevante, responda só 'NADA'.\n\n"
        f"Conversa:\n{conversation}"
    )
    resp = llm.invoke(prompt)
    text = resp.content if hasattr(resp, "content") else str(resp)
    return add_facts(_parse_facts(text))
