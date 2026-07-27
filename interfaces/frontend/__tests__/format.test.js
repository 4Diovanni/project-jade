import { test } from "node:test";
import assert from "node:assert/strict";
import { modelBadge } from "../lib/format.js";

test("mapeia os modelos conhecidos", () => {
  assert.equal(modelBadge("claude"), "☁️ Claude");
  assert.equal(modelBadge("local"), "local");
  assert.equal(modelBadge("tool"), "ação");
});

test("modelo desconhecido → vazio", () => {
  assert.equal(modelBadge("gpt"), "");
  assert.equal(modelBadge(null), "");
});
