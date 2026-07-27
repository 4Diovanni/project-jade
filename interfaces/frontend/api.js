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
