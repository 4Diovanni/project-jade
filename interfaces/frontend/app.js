import { createStore } from "./lib/state.js";
import { createOrb } from "./orb.js";
import { createChat } from "./chat.js";
import { createThreads } from "./threads.js";
import { createVoice } from "./voice.js";
import { reset } from "./api.js";

const store = createStore();
const audioEl = new Audio();
const orb = createOrb(document.getElementById("orb-canvas"));
const chat = createChat({ store, orb, audioEl });
const threads = createThreads({ chat });
const voice = createVoice({ store, orb, chat, audioEl });

const input = document.getElementById("composer-input");
const sendBtn = document.getElementById("send-btn");
const micBtn = document.getElementById("mic-btn");
const muteBtn = document.getElementById("mute-btn");
const status = document.getElementById("orb-status");

const STATUS = { idle: "ociosa", listening: "ouvindo…", thinking: "pensando…", speaking: "falando…" };
const _setState = orb.setState;
orb.setState = (name) => { status.textContent = STATUS[name] || name; _setState(name); };

// Trava de entrada: quando busy, desabilita composer e mic.
store.subscribe((st) => {
  input.disabled = st.busy;
  sendBtn.disabled = st.busy;
  micBtn.disabled = st.busy;
  input.placeholder = st.busy ? "Jade está pensando…" : "Fale com a Jade…";
});

document.getElementById("composer").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value.trim();
  input.value = "";
  chat.send(text);
});

document.getElementById("new-chat").addEventListener("click", async () => {
  await reset();
  chat.clear();
  for (const el of document.getElementById("threads-list").children) el.classList.remove("active");
});

muteBtn.addEventListener("click", () => {
  const muted = !store.get().muted;
  store.set({ muted });
  if (muted) audioEl.pause();
  muteBtn.textContent = muted ? "🔇" : "🔊";
  muteBtn.setAttribute("aria-pressed", String(muted));
});

voice.bind();
threads.refresh();
orb.setState("idle");
