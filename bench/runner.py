"""Runner do benchmark: orquestra health check, isolamento e execução.

Isolamento: durante toda a execução, `settings.NOTES_DIR` aponta para um
diretório temporário. Isso protege de uma vez só o humor, o perfil do usuário e
qualquer escrita de conversa — sem precisar restaurar valor a valor. As notas de
estado reais são **copiadas** para lá, para o system prompt medido continuar
realista. O índice do RAG **não** é isolado: ele lê o vault versionado do
repositório, e é justamente isso que torna o recall@k reprodutível.
"""

from __future__ import annotations

import argparse
import contextlib
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from urllib.request import urlopen

from bench.aggregate import Result, evaluate, summarize
from bench.cases import Case, CaseError, load_cases
from bench.report import write
from core.chat import ChatSession
from core.config import settings
from core.metrics import capture
from core.model_router import cloud_available

_REPORTS_DIR = Path(__file__).parent / "reports"
_CASES_DIR = Path(__file__).parent / "cases"


def health_check() -> None:
    """Confere que o Ollama responde. Falha rápido, com instrução acionável."""
    try:
        # URL vem de settings.OLLAMA_BASE_URL (configuração local), não de
        # entrada do usuário — nosec B310.
        urlopen(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=2).close()  # nosec B310
    except Exception as e:
        raise RuntimeError(
            f"Ollama não respondeu em {settings.OLLAMA_BASE_URL}.\n"
            "  1. Garanta que o serviço do Ollama está rodando.\n"
            f"  2. Baixe os modelos: ollama pull {settings.OLLAMA_MODEL} "
            f"&& ollama pull {settings.OLLAMA_EMBED_MODEL}"
        ) from e


@contextlib.contextmanager
def isolated_notes() -> Iterator[None]:
    """Aponta `settings.NOTES_DIR` para um diretório temporário durante o bloco."""
    original = settings.NOTES_DIR
    temporario = Path(tempfile.mkdtemp(prefix="jade_bench_"))
    for nota in (settings.PERSONALITY_NOTE, settings.MOOD_NOTE, settings.PROFILE_NOTE):
        origem = original / nota
        if origem.is_file():
            with contextlib.suppress(OSError):
                shutil.copy2(origem, temporario / nota)
    settings.NOTES_DIR = temporario
    try:
        yield
    finally:
        settings.NOTES_DIR = original
        shutil.rmtree(temporario, ignore_errors=True)


def _mood_level() -> int:
    from core.mood import load_level

    return load_level()


def run_case(case: Case, *, cloud_ok: bool) -> Result:
    """Executa um caso numa sessão nova e avalia o turno medido."""
    if case.expect.get("route") == "cloud" and not cloud_ok:
        return Result(
            case_id=case.id,
            category=case.category,
            status="pulado",
            detail="rota 'cloud' exige ANTHROPIC_API_KEY configurada",
            meta={"_expect": dict(case.expect)},
        )

    antes = _mood_level()
    session = ChatSession(use_journal=False)
    try:
        with capture() as turn:
            session.send(case.message)
    except Exception as e:
        return Result(
            case_id=case.id,
            category=case.category,
            status="erro",
            detail=f"{type(e).__name__}: {e}",
            meta={"_expect": dict(case.expect)},
        )

    status, falhas = evaluate(case, turn, mood_before=antes)
    meta = dict(turn.meta)
    meta["_expect"] = dict(case.expect)
    return Result(
        case_id=case.id,
        category=case.category,
        status=status,
        failures=falhas,
        steps=dict(turn.steps),
        meta=meta,
    )


def run(cases: list[Case], *, repeat: int = 1) -> list[Result]:
    """Executa todos os casos `repeat` vezes. Um caso quebrado não derruba a suíte."""
    cloud_ok = cloud_available()
    resultados: list[Result] = []
    total = len(cases) * repeat
    feito = 0
    for _ in range(repeat):
        for case in cases:
            feito += 1
            print(f"[{feito}/{total}] {case.id} … ", end="", flush=True)
            resultado = run_case(case, cloud_ok=cloud_ok)
            resultados.append(resultado)
            print(resultado.status)
    return resultados


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python main.py bench",
        description="Mede desempenho e qualidade das decisões da Jade.",
    )
    parser.add_argument("--repeat", type=int, default=1, help="repetições por caso (default: 1)")
    parser.add_argument("--cases", default=str(_CASES_DIR), help="arquivo .yaml ou pasta de casos")
    parser.add_argument("--tag", default="", help="rótulo no nome do relatório")
    args = parser.parse_args(argv)

    try:
        health_check()
    except RuntimeError as e:
        print(f"❌ {e}")
        return 1

    try:
        cases = load_cases(args.cases)
    except CaseError as e:
        print(f"❌ Caso inválido: {e}")
        return 1

    if not cloud_available():
        print("ℹ️  Sem ANTHROPIC_API_KEY: os casos de rota 'cloud' serão pulados.\n")

    with isolated_notes():
        resultados = run(cases, repeat=args.repeat)

    resumo = summarize(resultados)
    caminho = write(_REPORTS_DIR, resumo, resultados, tag=args.tag)

    print(
        f"\n✓ {resumo['ok']}/{resumo['evaluated']} caso(s) ok "
        f"({resumo['route_accuracy'] * 100:.1f}% de acerto de rota)"
    )
    print(f"📄 Relatório: {caminho}")
    return 0
