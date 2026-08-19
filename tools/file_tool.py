"""Tool de criação/escrita de arquivos por contexto (Issue #63, Fase 4).

Interpreta pedidos em linguagem natural do tipo "crie um arquivo txt onde
vai estar escrito X" e separa três informações da frase: **formato**
(extensão), **nome** (opcional) e **conteúdo**. Se o formato não é
reconhecido, não cria nada — responde com os formatos suportados.

Como em `tools/system_tool.py`, o parsing (`_parse`) é puro/testável e a
escrita em disco fica isolada em `_create_file`. Segurança: o nome do
arquivo é sempre saneado (sem separador de caminho nem `..`) antes de virar
caminho, e a escrita fica restrita a `settings.FILES_TOOL_BASE_DIR` — nunca
um caminho vindo cru do texto do usuário.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from core.config import settings
from tools.base import JadeTool

# Extensões suportadas nesta entrega (ver Issue #63 — mais formatos depois).
_EXTENSION_ALIASES: dict[str, str] = {
    "txt": "txt",
    "texto": "txt",
    ".txt": "txt",
    "md": "md",
    "markdown": "md",
    ".md": "md",
}
_SUPPORTED_FORMATS_MSG = (
    "`.txt` (texto simples, ex.: 'crie um arquivo txt com bolo de cenoura escrito nele') "
    "e `.md` (Markdown, ex.: 'crie um arquivo md com a receita escrita nele')"
)

_CREATE_VERBS = (
    "crie",
    "cria",
    "criar",
    "faça",
    "faca",
    "fazer",
    "gera",
    "gerar",
    "escreva",
    "escrever",
)

_CONTENT_MARKERS = (
    "com o seguinte texto",
    "com o conteúdo",
    "com o conteudo",
    "com a frase",
    "com o texto",
    "que diz",
    "dizendo",
    "escrito",
    "escrita",
    "contendo",
)

_NAME_MARKERS = (
    "com o nome",
    "chamado",
    "chamada",
    "chame de",
    "nomeado",
    "nomeada",
    "nome de",
)

_INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]')
_QUOTED = re.compile(r"[\"“]([^\"”]+)[\"”]|'([^']+)'")


@dataclass
class FileCreateRequest:
    extension: str
    filename: str
    content: str


def _is_create_request(low: str) -> bool:
    return "arquivo" in low and any(v in low for v in _CREATE_VERBS)


def _extract_extension(low: str) -> str | None:
    for word in re.findall(r"[\wà-ú.]+", low):
        if word in _EXTENSION_ALIASES:
            return _EXTENSION_ALIASES[word]
    return None


def _extract_content(query: str) -> str:
    quoted = _QUOTED.search(query)
    if quoted:
        return (quoted.group(1) or quoted.group(2)).strip()

    low = query.lower()
    for marker in _CONTENT_MARKERS:
        idx = low.find(marker)
        if idx == -1:
            continue
        rest = query[idx + len(marker) :].strip(" :")
        rest = re.sub(r"^(que\s+)", "", rest, flags=re.IGNORECASE)
        rest = rest.strip(" .!\"'“”")
        if rest:
            return rest
    return ""


def _slugify(name: str) -> str:
    """Sanina um nome de arquivo: sem separador de caminho nem caracteres
    inválidos no Windows. Nunca produz `..` nem componente de diretório —
    é sempre um nome de arquivo solto, escrito dentro de FILES_TOOL_BASE_DIR."""
    name = _INVALID_FILENAME_CHARS.sub("", name)
    name = name.replace("..", "")
    name = re.sub(r"\s+", "_", name.strip())
    name = name.strip("._") or "arquivo"
    return name[:80]


def _extract_filename(query: str) -> str | None:
    low = query.lower()
    for marker in _NAME_MARKERS:
        idx = low.find(marker)
        if idx == -1:
            continue
        rest = query[idx + len(marker) :].strip(" :")
        # Corta assim que começar a parte de conteúdo (ex.: "... com o nome
        # bolo onde vai estar escrito a receita").
        rest = re.split(
            r"\s+(?:onde|com|contendo|escrito|escrita|dizendo)\b",
            rest,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        name = rest.strip(" .!\"'“”")
        if name:
            return _slugify(name)
    return None


def _default_filename(content: str) -> str:
    if content:
        base = _slugify(" ".join(content.split()[:4]))
        if base and base != "arquivo":
            return base
    return f"arquivo_{datetime.now():%Y%m%d_%H%M%S}"


def _parse(query: str) -> tuple[str, FileCreateRequest | None]:
    """Interpreta o pedido. Retorna (kind, dado) sem efeitos colaterais.

    kinds: 'create' (FileCreateRequest pronto) · 'unknown_format' (é pedido
    de criação de arquivo, mas o formato não foi reconhecido) · 'none'
    (não é pedido de criação de arquivo)."""
    low = query.lower().strip()
    if not _is_create_request(low):
        return "none", None

    extension = _extract_extension(low)
    if extension is None:
        return "unknown_format", None

    content = _extract_content(query)
    filename = _extract_filename(query) or _default_filename(content)
    return "create", FileCreateRequest(extension=extension, filename=filename, content=content)


def _avoid_overwrite(path: Path) -> Path:
    """Nunca sobrescreve um arquivo existente — acrescenta um sufixo numérico."""
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{n}{path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def _create_file(req: FileCreateRequest) -> str:
    base_dir = settings.FILES_TOOL_BASE_DIR
    base_dir.mkdir(parents=True, exist_ok=True)

    path = _avoid_overwrite(base_dir / f"{req.filename}.{req.extension}")
    path.write_text(req.content, encoding="utf-8")

    if req.content:
        return f"Criei o arquivo {path.name} em {base_dir} com o conteúdo pedido."
    return f"Criei o arquivo {path.name} em {base_dir} (vazio, nenhum conteúdo foi especificado)."


class FileCreateTool(JadeTool):
    name = "file_create"
    description = (
        "Cria e escreve arquivos (.txt, .md) na área de trabalho a partir de um "
        "pedido em linguagem natural, extraindo formato, nome (opcional) e "
        "conteúdo do texto. Use para pedidos como 'crie um arquivo txt com "
        "\"...\" escrito nele' ou 'faça um arquivo md chamado receita com a "
        "receita de bolo'."
    )
    trigger_hints = ("arquivo",) + _CREATE_VERBS

    def accepts(self, message: str) -> bool:
        return _is_create_request(message.lower())

    def run(self, query: str) -> str:
        if not settings.FILES_TOOL_ENABLED:
            return "A criação de arquivos está desativada (JADE_FILES_TOOL_ENABLED=false)."

        kind, req = _parse(query)
        if kind == "unknown_format":
            return (
                "Não reconheci o formato do arquivo. Hoje eu sei criar "
                f"{_SUPPORTED_FORMATS_MSG}. Me diga qual desses você quer."
            )
        if kind != "create" or req is None:
            return (
                "Não identifiquei um pedido de criação de arquivo. Tente algo como "
                "'crie um arquivo txt com ... escrito nele'."
            )
        return _create_file(req)
