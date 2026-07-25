import { sendMessage, ttsUrl } from "./api.js";
import { modelBadge } from "./lib/format.js";

export function createChat({ store, orb, audioEl }) {
  const list = document.getElementById("messages");

  function addBubble(role, text, model) {
    const div = document.createElement("div");
    div.className = `bubble ${role}`;
    div.textContent = text;
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
      const { reply, model } = await sendMessage(text);
      addBubble("jade", reply, model);
      store.set({ busy: false });
      await speak(reply);
    } catch (e) {
      console.error(e);
      addBubble("error", "Jade indisponível no momento.");
      store.set({ busy: false });
      orb.setState("idle");
    }
  }

  return { send, addBubble, clear: () => { list.innerHTML = ""; } };
}
