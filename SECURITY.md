# Política de Segurança — Project Jade

O Jade é um assistente *privacy-first*: ele lê arquivos pessoais (Obsidian),
credenciais e pode agir sobre o sistema. Segurança é requisito, não opcional.

## Reportar uma vulnerabilidade

Encontrou uma falha? **Não abra uma issue pública.** Use os
[Security Advisories](https://github.com/4Diovanni/project-jade/security/advisories/new)
do GitHub (relato privado). Retorno esperado em até 5 dias úteis.

## Pipeline de segurança automatizada

Toda alteração passa por checagens automáticas (GitHub Actions):

| Camada | Ferramenta | Onde |
|---|---|---|
| Segredos no código/histórico | **Gitleaks** | CI + pre-commit |
| Análise estática (SAST) | **Bandit**, **CodeQL** | CI (`security.yml`, `codeql.yml`) |
| Vulnerabilidades em dependências | **pip-audit** | CI (`security.yml`) |
| Atualização de dependências | **Dependabot** | `dependabot.yml` (semanal) |
| Lint / formatação | **Ruff** | CI (`ci.yml`) + pre-commit |

## Regras de ouro

1. **Segredos só no `.env`** (gitignored). Nunca commite chaves. O `.env.example`
   documenta as variáveis com valores vazios.
2. **Notas pessoais do Obsidian nunca vão pro git** (ver `.gitignore`).
3. **Configuração sempre via `core.config.settings`** — nada de `os.getenv` solto
   nem valores hardcoded.
4. Dependências novas passam por `pip-audit` antes de entrar.

## Exceções conhecidas (accepted risk)

| Advisory | Pacote | Status | Justificativa |
|---|---|---|---|
| **PYSEC-2026-311** | `chromadb` ≤ 1.5.9 | Ignorada no `pip-audit` | Injeção de código **pré-auth no servidor HTTP** do ChromaDB (endpoint `/api/v2/.../collections` com `trust_remote_code`). **Não explorável aqui:** usamos o cliente **embarcado** (`PersistentClient`, sem servidor/rede) e nunca habilitamos `trust_remote_code`. Sem versão corrigida publicada (1.5.9 é a última). **Reavaliar** quando houver release > 1.5.9. |

Regra: só se ignora um advisory com justificativa escrita aqui e reavaliação
prevista. Nada de silenciar findings sem análise.

## Setup local dos hooks (recomendado)

```bash
pip install -r requirements-dev.txt
pre-commit install          # ativa os hooks no seu git
pre-commit run --all-files  # roda todas as checagens agora
```

A partir daí, cada `git commit` roda Ruff, Bandit, Gitleaks e detecção de
chaves privadas automaticamente.
