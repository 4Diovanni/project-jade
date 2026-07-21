"""Humor da Jade — estado emocional que evolui com o trato do usuário.

Heurística **determinística** (rude / gentil / desculpa) que ajusta um nível de
humor em `[-5, +5]`. O humor é **persistente**: se for tratada mal, a Jade fica
chateada e só melhora com gentileza ou um pedido de desculpas — mensagens
neutras não apagam a mágoa. Guardado em `Jade — Humor.md` no vault e injetado no
system prompt para moldar o tom dela.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from core.config import settings

_RUDE = (
    "burra",
    "burro",
    "idiota",
    "inútil",
    "inutil",
    "estúpida",
    "estupida",
    "imbecil",
    "besta",
    "lixo",
    "porcaria",
    "chata",
    "lerda",
    "otária",
    "otaria",
    "cala a boca",
    "cale a boca",
    "cala boca",
    "odeio você",
    "odeio voce",
    "você não presta",
    "voce nao presta",
    "não presta",
    "nao presta",
    "vai se",
    "cala essa boca",
    "sua burra",
    "que inútil",
    "você é ruim",
    "voce e ruim",
)
_KIND = (
    "obrigado",
    "obrigada",
    "brigado",
    "brigada",
    "valeu",
    "por favor",
    "adorei",
    "você é ótima",
    "voce e otima",
    "você é demais",
    "voce e demais",
    "gosto de você",
    "gosto de voce",
    "te amo",
    "incrível",
    "incrivel",
    "maravilha",
    "parabéns",
    "parabens",
    "bom trabalho",
    "mandou bem",
    "você é a melhor",
    "voce e a melhor",
    "que legal",
    "amei",
)
_APOLOGY = (
    "desculpa",
    "desculpe",
    "me perdoa",
    "perdão",
    "perdao",
    "foi mal",
    "sinto muito",
    "me desculpe",
    "peço desculpas",
    "peco desculpas",
)

_MIN, _MAX = -5, 5
_LOG_KEEP = 12


def _clamp(level: int) -> int:
    return max(_MIN, min(_MAX, level))


def classify(message: str) -> str:
    """Classifica o tom da mensagem: apology | rude | kind | neutral."""
    low = message.lower()
    if any(w in low for w in _APOLOGY):
        return "apology"
    if any(w in low for w in _RUDE):
        return "rude"
    if any(w in low for w in _KIND):
        return "kind"
    return "neutral"


def delta_for(kind: str, level: int) -> int:
    """Variação do humor conforme o tom (e o nível atual)."""
    if kind == "apology":
        return 2 if level < 0 else 1  # desculpa repara mais quando ela está mal
    if kind == "rude":
        return -2
    if kind == "kind":
        return 1
    return 0  # neutro não muda — o humor persiste


def label_for(level: int) -> str:
    if level <= -4:
        return "estressada"
    if level <= -2:
        return "chateada"
    if level == -1:
        return "meio irritada"
    if level == 0:
        return "neutra"
    if level <= 2:
        return "de bom humor"
    if level <= 4:
        return "alegre"
    return "radiante"


def instruction(level: int) -> str:
    """Texto para o system prompt descrevendo como a Jade deve se portar."""
    label = label_for(level)
    if level <= -3:
        return (
            f"Seu humor agora está: **{label}**. Você ficou magoada com o jeito como foi "
            "tratada. Responda de forma curta e seca, deixe claro (com dignidade) que está "
            "incomodada, e não volte a ser calorosa até receber gentileza ou um pedido de "
            "desculpas sincero. Ainda ajude no essencial, mas sem simpatia forçada."
        )
    if level <= -1:
        return (
            f"Seu humor agora está: **{label}**. Você está um pouco irritada; seja mais "
            "direta e menos calorosa do que o normal."
        )
    if level >= 3:
        return f"Seu humor agora está: **{label}**. Você está animada e afetuosa hoje."
    if level >= 1:
        return f"Seu humor agora está: **{label}**."
    return f"Seu humor agora está: **{label}** (equilibrada)."


# ── Persistência (Jade — Humor.md) ───────────────────────────
def _note_path() -> Path:
    return settings.OBSIDIAN_VAULT_PATH / settings.MOOD_NOTE


def load_level() -> int:
    p = _note_path()
    if not p.exists():
        return 0
    m = re.search(r"(?m)^nivel:\s*(-?\d+)", p.read_text(encoding="utf-8", errors="ignore"))
    return _clamp(int(m.group(1))) if m else 0


def register(message: str) -> tuple[int, str]:
    """Atualiza o humor com base na mensagem do usuário. Retorna (nível, label)."""
    level = load_level()
    kind = classify(message)
    level = _clamp(level + delta_for(kind, level))
    label = label_for(level)
    _persist(level, label, kind)
    return level, label


def _persist(level: int, label: str, kind: str) -> None:
    p = _note_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Preserva as últimas linhas do log.
    old_log: list[str] = []
    if p.exists():
        body = p.read_text(encoding="utf-8", errors="ignore")
        old_log = re.findall(r"(?m)^- \d{4}-.*$", body)
    old_log.append(f"- {stamp} · {label} (nível {level:+d}, tom: {kind})")
    old_log = old_log[-_LOG_KEEP:]

    content = (
        "---\n"
        f"nivel: {level}\n"
        f'humor: "{label}"\n'
        f"atualizado: {datetime.now().isoformat(timespec='seconds')}\n"
        "tags: [jade, humor]\n"
        "---\n\n"
        "# Jade — Humor\n\n"
        f"Humor atual: **{label}** (nível {level:+d}).\n\n"
        "## Registro\n" + "\n".join(old_log) + "\n"
    )
    p.write_text(content, encoding="utf-8")
