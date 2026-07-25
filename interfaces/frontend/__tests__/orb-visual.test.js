import { test } from "node:test";
import assert from "node:assert/strict";
import { amplitudeToVisual } from "../lib/orb-visual.js";

test("silêncio → energia 0 e raio base", () => {
  const v = amplitudeToVisual(new Uint8Array([0, 0, 0, 0]));
  assert.equal(v.energy, 0);
  assert.ok(v.radius > 0);
});

test("mais amplitude → mais raio e brilho (monotônico)", () => {
  const baixo = amplitudeToVisual(new Uint8Array([40, 40, 40, 40]));
  const alto = amplitudeToVisual(new Uint8Array([220, 220, 220, 220]));
  assert.ok(alto.energy > baixo.energy);
  assert.ok(alto.radius > baixo.radius);
  assert.ok(alto.glow > baixo.glow);
});

test("array vazio não quebra", () => {
  const v = amplitudeToVisual(new Uint8Array([]));
  assert.equal(v.energy, 0);
});
