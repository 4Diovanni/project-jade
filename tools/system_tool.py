"""Tool de controle do sistema — as "mãos" do Jade no computador (Fase 4).

Capacidades (Windows): abrir aplicativos (de uma **whitelist**), ajustar o
volume e pesquisar na web. Salvaguardas:
- **Só abre apps da whitelist** — nada de comando arbitrário vindo do LLM.
- Volume via teclas de mídia (`ctypes`, sem shell).
- Pode ser desligada por completo com `JADE_SYSTEM_TOOL_ENABLED=false`.

O parsing (`_parse`) é uma função pura e testável; a execução fica separada.
"""

from __future__ import annotations

import sys
import webbrowser
from urllib.parse import quote_plus

from core.config import settings
from tools.base import JadeTool

# Whitelist de apps: (rótulos reconhecidos) -> comando a abrir.
# "__browser__" usa o navegador padrão via webbrowser.
_APP_TABLE: list[tuple[tuple[str, ...], str]] = [
    (("bloco de notas", "notepad", "bloco"), "notepad.exe"),
    (("calculadora", "calculator", "calc"), "calc.exe"),
    (("explorador de arquivos", "explorador", "explorer"), "explorer.exe"),
    (("paint", "desenho"), "mspaint.exe"),
    (("configurações", "configuracoes", "settings"), "ms-settings:"),
    (("navegador", "browser", "chrome", "internet"), "__browser__"),
]
_APP_LABELS = [labels[0] for labels, _ in _APP_TABLE]

_VOLUME_UP = ("aument", "sobe", "subir", "mais alto", "alto")
_VOLUME_DOWN = ("diminu", "abaix", "baix", "menos", "reduz")
_MUTE = ("mudo", "mute", "sem som", "tira o som", "tirar o som")
_OPEN = ("abrir", "abre", "abra", "inicia", "inicie", "executa", "executar")
_SEARCH = ("pesquis", "google", "buscar na web", "busca na web", "procura na web")

# Teclas virtuais de mídia (Windows).
_VK = {"up": (0xAF, 5), "down": (0xAE, 5), "mute": (0xAD, 1)}


def _find_app(low: str) -> tuple[str, str] | None:
    for labels, command in _APP_TABLE:
        if any(label in low for label in labels):
            return labels[0], command
    return None


_SEARCH_PREFIXES = (
    "pesquisar por",
    "pesquise por",
    "pesquisar",
    "pesquise",
    "buscar por",
    "buscar",
    "busca por",
    "busca",
    "procurar por",
    "procurar",
    "procure",
)
_SEARCH_SUFFIXES = ("no google", "na web", "no navegador", "pra mim", "por favor")


def _extract_search_term(query: str) -> str:
    """Extrai o termo de busca, tirando prefixos de comando e sufixos como
    'no google'. Ex.: 'pesquise gatos no google' -> 'gatos'."""
    term = query.strip()
    low = term.lower()
    for pre in _SEARCH_PREFIXES:
        if low.startswith(pre):
            term = term[len(pre) :]
            break
    low = term.lower().strip()
    for suf in _SEARCH_SUFFIXES:
        if low.endswith(suf):
            term = term[: len(term) - len(suf)]
            low = term.lower().strip()
    return term.strip(" ?.!\"'")


def _parse(query: str) -> tuple[str | None, object]:
    """Interpreta o comando. Retorna (tipo, valor) sem efeitos colaterais.

    tipos: 'volume' (up/down/mute) · 'search' (termo) · 'open' ((rótulo, cmd)) ·
    'open_unknown' (None) · None (não é comando de sistema).
    """
    low = query.lower().strip()

    if any(w in low for w in _MUTE):
        return "volume", "mute"
    if "volume" in low or "som" in low:
        if any(w in low for w in _VOLUME_UP):
            return "volume", "up"
        if any(w in low for w in _VOLUME_DOWN):
            return "volume", "down"

    if any(w in low for w in _SEARCH):
        term = _extract_search_term(query)
        if term:
            return "search", term

    if any(w in low for w in _OPEN):
        app = _find_app(low)
        return ("open", app) if app else ("open_unknown", None)

    return None, None


class SystemControlTool(JadeTool):
    name = "system_control"
    description = (
        "Controla o computador: abrir aplicativos (bloco de notas, calculadora, "
        "explorador, navegador, configurações), ajustar o volume e pesquisar na web. "
        "Use para pedidos como 'abra a calculadora', 'aumente o volume', 'mudo', "
        "'pesquise <algo> no google'."
    )
    trigger_hints = _OPEN + _SEARCH + _MUTE + ("volume", "som")

    def accepts(self, message: str) -> bool:
        # Só assume o comando se realmente souber executá-lo (evita falso positivo).
        return _parse(message)[0] is not None

    def run(self, query: str) -> str:
        if not settings.SYSTEM_TOOL_ENABLED:
            return "O controle do sistema está desativado (JADE_SYSTEM_TOOL_ENABLED=false)."

        kind, value = _parse(query)
        if kind == "volume":
            return _set_volume(str(value))
        if kind == "search":
            return _web_search(str(value))
        if kind == "open":
            label, command = value  # type: ignore[misc]
            return _open_app(label, command)
        if kind == "open_unknown":
            return "Não reconheci esse aplicativo. Posso abrir: " + ", ".join(_APP_LABELS) + "."
        return (
            "Não identifiquei a ação de sistema. Tente 'abrir <app>', "
            "'aumentar/diminuir volume', 'mudo' ou 'pesquisar <termo>'."
        )


# ── Executores (efeitos colaterais) ──────────────────────────
def _open_app(label: str, command: str) -> str:
    if command == "__browser__":
        webbrowser.open("https://www.google.com")
        return "Abri o navegador."
    if sys.platform != "win32":
        return "Abrir aplicativos está disponível apenas no Windows."
    import os

    # command vem SEMPRE da whitelist (_APP_TABLE), nunca do texto do LLM.
    os.startfile(command)  # nosec B606
    return f"Abri {label}."


def _web_search(term: str) -> str:
    webbrowser.open(f"https://www.google.com/search?q={quote_plus(term)}")
    return f"Pesquisei por “{term}” no navegador."


def _set_volume(action: str) -> str:
    if sys.platform != "win32":
        return "Controle de volume disponível apenas no Windows."
    import ctypes

    vk, times = _VK[action]
    for _ in range(times):
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
    return {
        "up": "Volume aumentado. 🔊",
        "down": "Volume diminuído. 🔉",
        "mute": "Som mutado/desmutado. 🔇",
    }[action]
