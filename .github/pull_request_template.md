<!--
  Todo PR precisa estar ligado a uma Issue (ver CLAUDE.md → Workflow de trabalho).
  Substitua o número abaixo. PR sem Issue vinculada não é mergeado.
-->
Closes #

## O que muda


## Por quê


## Como testar


## Checklist
- [ ] Issue vinculada acima com `Closes #<n>` (ou `Fixes #<n>`)
- [ ] `ruff check . && ruff format .`
- [ ] `bandit -c pyproject.toml -r core tools interfaces bench main.py`
- [ ] `pip-audit -r requirements.txt --ignore-vuln PYSEC-2026-311`
- [ ] `pytest`
- [ ] Sem segredos no diff (config via `core.config.settings`, valores no `.env`)
- [ ] Docs atualizadas (`CLAUDE.md` / `README.md` / `docs/`) quando o
      comportamento ou o setup mudam
