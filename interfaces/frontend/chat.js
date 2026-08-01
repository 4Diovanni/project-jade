import { sendMessage, ttsUrl } from "./api.js";
import { modelBadge } from "./lib/format.js";
import { renderMarkdown } from "./lib/markdown.js";

export function createChat({ store, orb, audioEl, onConversation }) {
  const list = document.getElementById("messages");
  let lastTtsUrl = null;

  /** Avisa quem cuida da lista de conversas qual é a conversa atual. */
  function notifyConversation(id) {
    if (id && onConversation) onConversation(id);
  }

  function addBubble(role, text, model) {
    const div = document.createElement("div");
    div.className = `bubble ${role}`;
    // Respostas da Jade vêm em Markdown (renderizado, com HTML escapado);
    // mensagens do usuário e erros ficam como texto plano.
    if (role === "jade") {
      div.innerHTML = renderMarkdown(text);
    } else {
      div.textContent = text;
    }
    list.appendChild(div);
    if (role === "jade" && modelBadge(model)) {
      const b = document.createElement("div");
      b.className = "badge";
      b.textContent = modelBadge(model);
      list.appendChild(b);
    }
    list.scrollTop = list.scrollHeight;
    return div;
  }

  async function speak(text) {
    if (store.get().muted) { orb.setState("idle"); return; }
    try {
      const url = await ttsUrl(text);
      if (lastTtsUrl) URL.revokeObjectURL(lastTtsUrl);
      lastTtsUrl = url;
      audioEl.src = url;
      orb.connectAudio(audioEl);
      orb.setState("speaking");
      audioEl.onended = () => orb.setState("idle");
      await audioEl.play();
    } catch {
      orb.setState("idle"); // falha de TTS não trava a UI
    }
  }

  async function send(text) {
    if (!text || store.get().busy) return;
    addBubble("user", text);
    store.set({ busy: true });
    orb.setState("thinking");
    try {
      const { reply, model, conversation_id } = await sendMessage(text);
      addBubble("jade", reply, model);
      notifyConversation(conversation_id);
      store.set({ busy: false });
      await speak(reply);
    } catch (e) {
      console.error(e);
      addBubble("error", "Jade indisponível no momento.");
      store.set({ busy: false });
      orb.setState("idle");
    }
  }

  return { send, addBubble, notifyConversation, clear: () => { list.innerHTML = ""; } };
}
