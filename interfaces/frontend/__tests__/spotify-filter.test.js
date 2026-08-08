import { test } from "node:test";
import assert from "node:assert/strict";
import { filterTracks } from "../lib/spotify-filter.js";

const tracks = [
  { id: "1", name: "Bohemian Rhapsody", artists: "Queen" },
  { id: "2", name: "Imagine", artists: "John Lennon" },
];

test("termo vazio devolve a lista inteira", () => {
  assert.deepEqual(filterTracks(tracks, ""), tracks);
});

test("filtra por nome (case-insensitive)", () => {
  const r = filterTracks(tracks, "bohemian");
  assert.equal(r.length, 1);
  assert.equal(r[0].id, "1");
});

test("filtra por artista", () => {
  const r = filterTracks(tracks, "lennon");
  assert.equal(r.length, 1);
  assert.equal(r[0].id, "2");
});

test("sem correspondência devolve lista vazia", () => {
  assert.deepEqual(filterTracks(tracks, "nada a ver com isso"), []);
});
