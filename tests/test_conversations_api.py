"""Testes do parsing de conversas e dos endpoints de leitura (CI-safe)."""

from core.journal import parse_conversation_note

_NOTE = """---
title: "abra a calculadora"
data: 2026-07-21
tags: [conversa, jade]
---

# abra a calculadora

Conversa com a Jade · [[Jade — Memória]] · #conversa/2026-07-21

**Você:** oi jade

**Jade:** Oi! Tudo bem?

**Você:** abra a calculadora

**Jade:** Abri calculadora.
"""


def test_parse_extrai_turnos_em_ordem():
    turns = parse_conversation_note(_NOTE)
    assert turns == [
        {"user": "oi jade", "jade": "Oi! Tudo bem?"},
        {"user": "abra a calculadora", "jade": "Abri calculadora."},
    ]


def test_parse_nota_sem_turnos_retorna_vazio():
    assert parse_conversation_note("---\ntags: []\n---\n\n# vazia\n") == []


def test_parse_resposta_multilinha():
    note = "**Você:** liste\n\n**Jade:** linha1\nlinha2\n"
    assert parse_conversation_note(note) == [{"user": "liste", "jade": "linha1\nlinha2"}]
