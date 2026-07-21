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


def run_index() -> None:
    """(Re)indexa o vault do Obsidian no ChromaDB (RAG)."""
    from core.memory import reindex_vault

    print(f"📚 Indexando o vault do Obsidian ({settings.OBSIDIAN_VAULT_PATH})...")
    try:
        n = reindex_vault()
    except Exception as e:
        print(
            f"❌ Falha ao indexar: {e}\n"
            "Verifique se o Ollama está rodando e se o modelo de embeddings existe:\n"
            f"  ollama pull {settings.OLLAMA_EMBED_MODEL}"
        )
        return
    print(f"✓ {n} nota(s) indexada(s) no ChromaDB (coleção '{settings.CHROMA_COLLECTION}').")


def run_cli() -> None:
    from core.chat import ChatSession

    print("🟢 Jade despertou. Digite sua mensagem ('/sair' para encerrar, '/reset' para limpar).")
    if settings.JOURNAL_ENABLED:
        print(
            f"🧠 Memória: as conversas são salvas em {settings.OBSIDIAN_VAULT_PATH / settings.CONVERSATIONS_SUBDIR}"
        )
    print()
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


def run_transcribe() -> None:
    """STT: transcreve um arquivo de áudio (python main.py transcribe <audio>)."""
    from interfaces.voice_service import transcribe

    if len(sys.argv) < 3:
        print("Uso: python main.py transcribe <arquivo_de_audio>")
        return
    audio = sys.argv[2]
    print(f"🎧 Transcrevendo {audio} (modelo whisper '{settings.WHISPER_MODEL}')...")
    try:
        text = transcribe(audio)
    except Exception as e:
        print(f"❌ Falha no STT: {e}")
        return
    print(f"📝 {text}")


def run_say() -> None:
    """TTS: fala um texto ou salva em arquivo (python main.py say "texto" [saida])."""
    from interfaces.voice_service import speak, synthesize

    if len(sys.argv) < 3:
        print('Uso: python main.py say "texto" [arquivo_de_saida]')
        return
    text = sys.argv[2]
    try:
        if len(sys.argv) >= 4:
            path = synthesize(text, sys.argv[3])
            print(f"🔊 Áudio salvo em {path}")
        else:
            speak(text)
            print("🔊 (falado)")
    except Exception as e:
        print(f"❌ Falha no TTS: {e}")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "chat":
        run_cli()
    elif command == "index":
        run_index()
    elif command == "transcribe":
        run_transcribe()
    elif command == "say":
        run_say()
    else:
        run_api()
