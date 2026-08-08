import { test } from "node:test";
import assert from "node:assert/strict";
import { spotifyCallbackParam } from "../spotify.js";

test("reconhece o retorno de sucesso do callback OAuth", () => {
  assert.equal(spotifyCallbackParam("?spotify=conectado"), "conectado");
});

test("reconhece o retorno de erro do callback OAuth", () => {
  assert.equal(spotifyCallbackParam("?spotify=erro"), "erro");
});

test("devolve null sem o parametro", () => {
  assert.equal(spotifyCallbackParam(""), null);
});
