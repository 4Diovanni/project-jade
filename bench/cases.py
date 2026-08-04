"""Casos declarativos do benchmark: carga e validação.

Um caso descreve uma mensagem e o que se espera das **decisões** da Jade — a
rota, a tool acionada, as fontes recuperadas. Nunca o texto da resposta: isso
depende da geração do LLM e não seria reprodutível.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


class CaseError(Exception):
    """Caso mal formado — mensagem legível para quem escreveu o YAML."""


@dataclass(frozen=True)
class Case:
    id: str
    message: str
    category: str
    expect: dict


_VALID_KEYS = {"route", "tool", "sources_include", "context", "mood_delta"}
_VALID_ROUTE = {"tool", "local", "cloud"}
_VALID_CONTEXT = {"none", "any"}
_VALID_MOOD = {"negative", "positive", "neutral"}


def _validate_expect(case_id: str, expect: dict) -> None:
    desconhecidas = set(expect) - _VALID_KEYS
    if desconhecidas:
        raise CaseError(
            f"caso {case_id!r}: chave(s) de expect desconhecida(s): "
            f"{', '.join(sorted(desconhecidas))}. Válidas: {', '.join(sorted(_VALID_KEYS))}"
        )
    if "route" in expect and expect["route"] not in _VALID_ROUTE:
        raise CaseError(
            f"caso {case_id!r}: route {expect['route']!r} inválida "
            f"(use {', '.join(sorted(_VALID_ROUTE))})"
        )
    if "context" in expect and expect["context"] not in _VALID_CONTEXT:
        raise CaseError(
            f"caso {case_id!r}: context {expect['context']!r} inválido "
            f"(use {', '.join(sorted(_VALID_CONTEXT))})"
        )
    if "mood_delta" in expect and expect["mood_delta"] not in _VALID_MOOD:
        raise CaseError(
            f"caso {case_id!r}: mood_delta {expect['mood_delta']!r} inválido "
            f"(use {', '.join(sorted(_VALID_MOOD))})"
        )
    if "sources_include" in expect and not isinstance(expect["sources_include"], list):
        raise CaseError(f"caso {case_id!r}: sources_include precisa ser uma lista")


def _load_file(path: Path) -> list[Case]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(raw, list):
        raise CaseError(f"{path.name}: o arquivo precisa conter uma lista de casos")
    casos: list[Case] = []
    for item in raw:
        if not isinstance(item, dict):
            raise CaseError(f"{path.name}: cada caso precisa ser um mapeamento")
        case_id = item.get("id")
        if not case_id:
            raise CaseError(f"{path.name}: caso sem 'id'")
        message = item.get("message")
        if not message:
            raise CaseError(f"caso {case_id!r}: falta 'message'")
        expect = item.get("expect") or {}
        if not isinstance(expect, dict):
            raise CaseError(f"caso {case_id!r}: 'expect' precisa ser um mapeamento")
        _validate_expect(case_id, expect)
        casos.append(Case(id=case_id, message=message, category=path.stem, expect=expect))
    return casos


def load_cases(path: str | Path) -> list[Case]:
    """Carrega os casos de um arquivo .yaml ou de um diretório inteiro.

    A categoria de cada caso é o nome do arquivo (sem extensão). Ids precisam
    ser únicos em toda a carga.
    """
    p = Path(path)
    arquivos = sorted(p.glob("*.yaml")) if p.is_dir() else [p]
    if not arquivos:
        raise CaseError(f"nenhum arquivo de casos encontrado em {p}")

    casos: list[Case] = []
    vistos: set[str] = set()
    for arquivo in arquivos:
        for caso in _load_file(arquivo):
            if caso.id in vistos:
                raise CaseError(f"id de caso duplicado: {caso.id!r}")
            vistos.add(caso.id)
            casos.append(caso)
    return casos
