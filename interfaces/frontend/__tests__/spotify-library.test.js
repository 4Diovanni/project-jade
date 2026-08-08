import { test } from "node:test";
import assert from "node:assert/strict";
import { groupLibrary } from "../lib/spotify-library.js";

const library = {
  playlists: {
    Rock: [
      { id: "1", name: "Bohemian Rhapsody", artists: "Queen" },
      { id: "2", name: "Livin' on a Prayer", artists: "Bon Jovi" },
    ],
    Curtidas: [{ id: "3", name: "Imagine", artists: "John Lennon" }],
  },
};

test("sem termo, devolve todos os grupos intactos", () => {
  assert.deepEqual(groupLibrary(library, ""), library.playlists);
});

test("filtra as faixas de cada grupo mantendo o agrupamento", () => {
  const r = groupLibrary(library, "queen");
  assert.deepEqual(Object.keys(r), ["Rock"]);
  assert.equal(r.Rock.length, 1);
  assert.equal(r.Rock[0].id, "1");
});

test("descarta grupos que ficam vazios apos o filtro", () => {
  const r = groupLibrary(library, "imagine");
  assert.deepEqual(Object.keys(r), ["Curtidas"]);
});

test("sem correspondencia nenhuma, devolve objeto vazio", () => {
  assert.deepEqual(groupLibrary(library, "nada a ver com isso"), {});
});

test("library sem playlists devolve objeto vazio", () => {
  assert.deepEqual(groupLibrary({}, ""), {});
  assert.deepEqual(groupLibrary(undefined, ""), {});
});
