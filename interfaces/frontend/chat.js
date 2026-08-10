import { connectChat, ttsUrl } from "./api.js";
import { modelBadge } from "./lib/format.js";
import { renderMarkdown } from "./lib/markdown.js";

export function createChat({ store, orb, audioEl, onConversation }) {
  const list = document.getElementById("messages");
  let lastTtsUrl = null;
  let currentBubble = null;
  let currentText = "";

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

  const chatSocket = connectChat({
    onToken: (text) => {
      currentText += text;
      if (currentBubble) {
        currentBubble.innerHTML = renderMarkdown(currentText);
        list.scrollTop = list.scrollHeight; // segue a rolagem conforme o texto chega
      }
    },
    onDone: ({ model, conversation_id }) => {
      if (currentBubble && modelBadge(model)) {
        const b = document.createElement("div");
        b.className = "badge";
        b.textContent = modelBadge(model);
        list.appendChild(b);
      }
      notifyConversation(conversation_id);
      const textoFinal = currentText;
      currentBubble = null;
      currentText = "";
      store.set({ busy: false });
      speak(textoFinal);
    },
    onError: (detail) => {
      console.error(detail);
      if (currentBubble) currentBubble.remove();
      currentBubble = null;
      currentText = "";
      addBubble("error", "Jade indisponível no momento.");
      store.set({ busy: false });
      orb.setState("idle");
    },
    onClose: () => {
      // conexão caiu: se havia um turno em andamento, avisa — sem
      // reconexão automática (o usuário reenvia).
      if (store.get().busy) {
        addBubble("error", "Conexão perdida. Tente enviar de novo.");
        store.set({ busy: false });
        orb.setState("idle");
      }
    },
    // wake_* vêm do "ok jade" (python main.py listen, integrado à API) —
    // o servidor empurra sozinho, não é resposta de nada que o composer
    // tenha enviado. Mesmo fluxo do push-to-talk (voice.js), só que o
    // gatilho foi o microfone do servidor em vez do botão do mic.
    onWakeListening: () => {
      if (!store.get().busy) store.set({ busy: true });
      orb.setState("listening");
    },
    onWakeThinking: () => orb.setState("thinking"),
    onWakeTurn: ({ transcription, reply, model, audio_url, conversation_id }) => {
      addBubble("user", transcription);
      addBubble("jade", reply, model);
      notifyConversation(conversation_id);
      store.set({ busy: false });
      if (!store.get().muted && audio_url) {
        audioEl.src = audio_url;
        orb.connectAudio(audioEl);
        orb.setState("speaking");
        audioEl.onended = () => orb.setState("idle");
        audioEl.play().catch(() => orb.setState("idle"));
      } else {
        orb.setState("idle");
      }
    },
    onWakeError: (detail) => {
      console.error("wake-word:", detail);
      addBubble("error", "Não consegui processar o comando de voz.");
      store.set({ busy: false });
      orb.setState("idle");
    },
  });

  function send(text) {
    if (!text || store.get().busy) return;
    if (!chatSocket.isOpen()) {
      addBubble("error", "Conexão perdida. Recarregue a página para continuar.");
      return;
    }
    addBubble("user", text);
    currentBubble = addBubble("jade", "", null);
    currentText = "";
    store.set({ busy: true });
    orb.setState("thinking");
    chatSocket.send(text);
  }

  return { send, addBubble, notifyConversation, clear: () => { list.innerHTML = ""; } };
}
