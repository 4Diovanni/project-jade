"""Ponto de entrada do Project Jade.

Uso:
    python main.py            # sobe a API FastAPI (uvicorn)
    python main.py chat       # chat via terminal (Fase 1)
"""

from __future__ import annotations

import contextlib
import sys

# Console do Windows costuma usar cp1252 e quebra com acentos/emoji.
# Forçamos UTF-8 na saída para a CLI em PT-BR funcionar (best-effort).
for _stream in (sys.stdout, sys.stderr):
    with contextlib.suppress(Exception):
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

from core.config import settings


def run_api() -> None:
    import uvicorn

    uvicorn.run(
        "interfaces.api:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True,
    )


def _provider_hint(error: Exception) -> str:
    """Dica de solução conforme o provider ativo, quando o LLM falha."""
    if settings.LLM_PROVIDER.lower() == "ollama":
        return (
            "Parece que o Ollama não está acessível em "
            f"{settings.OLLAMA_BASE_URL}.\n"
            "  1. Instale: https://ollama.com/download\n"
            f"  2. Baixe o modelo: ollama pull {settings.OLLAMA_MODEL}\n"
            "  3. Garanta que o serviço do Ollama está rodando.\n"
            "Ou troque JADE_LLM_PROVIDER no .env para um provider de nuvem."
        )
    return f"Falha ao falar com o provider '{settings.LLM_PROVIDER}': {error}"


def run_cli() -> None:
    from core.chat import ChatSession

    print("🟢 Jade despertou. Digite sua mensagem ('/sair' para encerrar, '/reset' para limpar).\n")
    try:
        session = ChatSession()
    except Exception as e:
        print(f"❌ Não consegui iniciar o modelo.\n{_provider_hint(e)}")
        return

    while True:
        try:
            user = input("você › ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAté logo. 👋")
            break

        if not user:
            continue
        if user.lower() in {"/sair", "/exit", "/quit"}:
            print("Até logo. 👋")
            break
        if user.lower() == "/reset":
            session.reset()
            print("(histórico limpo)\n")
            continue

        try:
            reply = session.send(user)
        except Exception as e:
            print(f"❌ Erro ao responder.\n{_provider_hint(e)}\n")
            continue
        print(f"jade › {reply}\n")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "chat":
        run_cli()
    else:
        run_api()
