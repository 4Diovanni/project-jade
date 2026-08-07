import { test } from "node:test";
import assert from "node:assert/strict";
import { _handleChatEvent, connectChat } from "../api.js";

test("token chama onToken com o texto", () => {
  let recebido = null;
  _handleChatEvent({ type: "token", text: "oi" }, { onToken: (t) => { recebido = t; } });
  assert.equal(recebido, "oi");
});

test("done chama onDone com o payload inteiro", () => {
  let recebido = null;
  _handleChatEvent(
    { type: "done", model: "local", conversation_id: "x" },
    { onDone: (d) => { recebido = d; } },
  );
  assert.deepEqual(recebido, { type: "done", model: "local", conversation_id: "x" });
});

test("error chama onError com o detail", () => {
  let recebido = null;
  _handleChatEvent({ type: "error", detail: "boom" }, { onError: (d) => { recebido = d; } });
  assert.equal(recebido, "boom");
});

test("tipo desconhecido não chama nenhum handler", () => {
  let chamou = false;
  const marcar = () => { chamou = true; };
  _handleChatEvent({ type: "?" }, { onToken: marcar, onDone: marcar, onError: marcar });
  assert.equal(chamou, false);
});

test("handler ausente não quebra", () => {
  assert.doesNotThrow(() => _handleChatEvent({ type: "token", text: "oi" }, {}));
});

test("connectChat().isOpen() retorna true quando readyState === OPEN", () => {
  const FakeWebSocket = class {
    static OPEN = 1;
    readyState = FakeWebSocket.OPEN;
    onmessage = null;
    onclose = null;
    send() {}
    close() {}
  };
  const socket = connectChat({}, FakeWebSocket, "ws://fake/ws/chat");
  assert.equal(socket.isOpen(), true);
});

test("connectChat().isOpen() retorna false quando readyState !== OPEN", () => {
  const FakeWebSocket = class {
    static OPEN = 1;
    readyState = 0; // CONNECTING
    onmessage = null;
    onclose = null;
    send() {}
    close() {}
  };
  const socket = connectChat({}, FakeWebSocket, "ws://fake/ws/chat");
  assert.equal(socket.isOpen(), false);
});
