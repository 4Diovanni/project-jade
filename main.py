"""Ponto de entrada do Project Jade.

Uso:
    python main.py            # sobe a API FastAPI (uvicorn)
    python main.py chat       # (Fase 1) chat via terminal
"""
from __future__ import annotations

import sys

import uvicorn

from core.config import settings


def run_api() -> None:
    uvicorn.run(
        "interfaces.api:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True,
    )


def run_cli() -> None:
    # TODO (Fase 1): loop de chat via terminal usando core.agent_router.
    print("CLI do Jade chega na Fase 1. Por enquanto: python main.py (API).")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "chat":
        run_cli()
    else:
        run_api()
