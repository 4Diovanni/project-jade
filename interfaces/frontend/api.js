// Wrappers de fetch para a API da Jade (mesmo origin).
async function jsonPost(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json();
}

export function _handleChatEvent(data, { onToken, onDone, onError } = {}) {
  if (data.type === "token") onToken?.(data.text);
  else if (data.type === "done") onDone?.(data);
  else if (data.type === "error") onError?.(data.detail);
}

export function connectChat({ onToken, onDone, onError, onClose } = {}, WebSocketImpl = typeof WebSocket !== "undefined" ? WebSocket : null, url = null) {
  if (!url && typeof location !== "undefined") {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    url = `${scheme}://${location.host}/ws/chat`;
  }
  const ws = new WebSocketImpl(url);
  ws.onmessage = (ev) => _handleChatEvent(JSON.parse(ev.data), { onToken, onDone, onError });
  ws.onclose = () => onClose?.();
  return {
    send: (message) => ws.send(JSON.stringify({ message })),
    close: () => ws.close(),
    isOpen: () => ws.readyState === WebSocketImpl.OPEN,
  };
}

export const sendMessage = (message) => jsonPost("/chat", { message });
export const reset = () =>
  fetch("/reset", { method: "POST" }).then((r) => {
    if (!r.ok) throw new Error(`/reset → ${r.status}`);
    return undefined;
  });
export const listConversations = () =>
  fetch("/conversations").then((r) => {
    if (!r.ok) throw new Error(`/conversations → ${r.status}`);
    return r.json();
  });
export const getConversation = (id) =>
  fetch(`/conversations/${encodeURIComponent(id)}`).then((r) => {
    if (!r.ok) throw new Error(`/conversations/${id} → ${r.status}`);
    return r.json();
  });

export async function renameConversation(id, title) {
  const res = await fetch(`/conversations/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error(`PATCH /conversations/${id} → ${res.status}`);
  return res.json();
}

export async function ttsUrl(text) {
  const res = await fetch("/voice/tts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error(`/voice/tts → ${res.status}`);
  return URL.createObjectURL(await res.blob());
}

export async function voiceChat(blob) {
  const form = new FormData();
  form.append("file", blob, "fala.webm");
  const res = await fetch("/voice/chat", { method: "POST", body: form });
  if (!res.ok) throw new Error(`/voice/chat → ${res.status}`);
  return res.json();
}

export const getSpotifyStatus = () =>
  fetch("/spotify/status").then((r) => {
    if (!r.ok) throw new Error(`/spotify/status → ${r.status}`);
    return r.json();
  });

export const getSpotifyLibrary = () =>
  fetch("/spotify/library").then((r) => {
    if (!r.ok) throw new Error(`/spotify/library → ${r.status}`);
    return r.json();
  });

export const syncSpotifyNow = () =>
  fetch("/spotify/sync", { method: "POST" }).then((r) => {
    if (!r.ok) throw new Error(`/spotify/sync → ${r.status}`);
    return r.json();
  });
