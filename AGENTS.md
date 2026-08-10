# AGENTS.md — Regras para agentes de IA no Project Jade

Este arquivo existe para que **qualquer agente, de qualquer modelo** (Claude,
GPT, Gemini, Copilot, Cursor, Codex…) siga o mesmo padrão de trabalho.

> **Leia `CLAUDE.md` por completo antes de qualquer alteração.** Ele é o guia
> canônico do projeto: arquitetura, stack, mapa do repositório, convenções de
> código e pipeline de qualidade. Este arquivo apenas destaca o que é
> inegociável.

## Regra de ouro
**Nenhum trabalho sem Issue. Nenhum PR sem `Closes #<n>`. Nenhum commit direto
na `main`.**

## O fluxo, em uma passada

1. **Abra uma Issue** para a tarefa — seja *Correção*, *Melhoria* ou *Nova
   função* — antes de escrever código:
   `gh issue create --title "fix: …" --label bug --body "…"`
   Corpo com **Contexto/Problema**, **Proposta**, **Critérios de aceite**.
   Labels: `bug` · `enhancement` · `documentation`.
2. **Crie a branch** a partir da `main` atualizada: `fix/<slug>`, `feat/<slug>`,
   `docs/<slug>`.
3. **Commits** em PT-BR, Conventional Commits (`feat:`, `fix:`, `docs:`,
   `refactor:`, `chore:`).
4. **Rode o pipeline local** (ver *Qualidade & Segurança* no `CLAUDE.md`):
   `ruff check . && ruff format .` · `bandit -c pyproject.toml -r core tools interfaces bench main.py` ·
   `pip-audit -r requirements.txt --ignore-vuln PYSEC-2026-311` · `pytest`.
5. **Abra o PR** com `Closes #<n>` na primeira linha do corpo, seguindo
   `.github/pull_request_template.md`.
6. **Espere o CI verde** (`ci.yml`, `security.yml`, `codeql.yml`) e faça o merge
   com `gh pr merge`. O merge é o deploy.

## Não faça
- Commitar segredos: tudo em `.env` (gitignored); configuração sempre via
  `core.config.settings`, nunca `os.getenv` espalhado.
- Versionar `database/` ou `obsidian_notes/` (gerados em runtime / pessoais).
- `try/except/pass` — o Bandit rejeita; use `contextlib.suppress`.
- Abrir PR que resolve algo sem Issue correspondente.
