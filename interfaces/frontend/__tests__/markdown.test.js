import { test } from "node:test";
import assert from "node:assert/strict";
import { renderMarkdown } from "../lib/markdown.js";

test("escapa HTML bruto (anti-XSS)", () => {
  const h = renderMarkdown("<script>alert(1)</script>");
  assert.match(h, /&lt;script&gt;/);
  assert.doesNotMatch(h, /<script>/);
});

test("negrito e código inline", () => {
  assert.match(renderMarkdown("isso é **forte**"), /<strong>forte<\/strong>/);
  assert.match(renderMarkdown("use `code`"), /<code>code<\/code>/);
});

test("itálico", () => {
  assert.match(renderMarkdown("um *destaque* aqui"), /<em>destaque<\/em>/);
});

test("lista não ordenada vira <ul><li>", () => {
  const h = renderMarkdown("- a\n- b");
  assert.match(h, /<ul>/);
  assert.match(h, /<li>a<\/li>/);
  assert.match(h, /<li>b<\/li>/);
  assert.match(h, /<\/ul>/);
});

test("lista ordenada vira <ol><li>", () => {
  const h = renderMarkdown("1. um\n2. dois");
  assert.match(h, /<ol>/);
  assert.match(h, /<li>um<\/li>/);
});

test("bloco de código cercado escapa o conteúdo", () => {
  const h = renderMarkdown("```\ncode<here>\n```");
  assert.match(h, /<pre><code>/);
  assert.match(h, /code&lt;here&gt;/);
});

test("cabeçalho vira <h1..3>", () => {
  assert.match(renderMarkdown("# Título"), /<h1>Título<\/h1>/);
  assert.match(renderMarkdown("### Sub"), /<h3>Sub<\/h3>/);
});

test("link sanitiza esquema perigoso", () => {
  const h = renderMarkdown("[x](javascript:alert(1))");
  assert.doesNotMatch(h, /javascript:/);
  assert.match(h, /href="#"/);
});

test("link http é preservado", () => {
  assert.match(renderMarkdown("[site](https://a.com)"), /href="https:\/\/a\.com"/);
});

test("string vazia ou nula", () => {
  assert.equal(renderMarkdown(""), "");
  assert.equal(renderMarkdown(null), "");
});
