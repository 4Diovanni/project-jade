import { test } from "node:test";
import assert from "node:assert/strict";
import { createStore } from "../lib/state.js";

test("estado inicial default", () => {
  const s = createStore();
  assert.deepEqual(s.get(), { busy: false, muted: false, currentThread: null });
});

test("set faz merge e notifica assinantes", () => {
  const s = createStore();
  let seen = null;
  s.subscribe((st) => { seen = st; });
  s.set({ busy: true });
  assert.equal(s.get().busy, true);
  assert.equal(s.get().muted, false);
  assert.equal(seen.busy, true);
});

test("unsubscribe para de notificar", () => {
  const s = createStore();
  let count = 0;
  const off = s.subscribe(() => { count++; });
  s.set({ busy: true });
  off();
  s.set({ busy: false });
  assert.equal(count, 1);
});
