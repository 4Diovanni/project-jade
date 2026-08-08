import { createStore } from "./lib/state.js";
import { createOrb } from "./orb.js";
import { createChat } from "./chat.js";
import { createThreads } from "./threads.js";
import { createVoice } from "./voice.js";
import { createSpotify, spotifyCallbackParam } from "./spotify.js";
import { reset } from "./api.js";

const store = createStore();
const audioEl = new Audio();
const orb = createOrb(document.getElementById("orb-canvas"));

// A conversa vira nota .md no primeiro turno: quando o id muda, a lista da
// esquerda é recarregada para a conversa nova aparecer sem recarregar a página.
// O título é resumido em segundo plano, então relemos a lista pouco depois.
let currentConversation = null;
function onConversation(id) {
  if (id === currentConversation) return;
  currentConversation = id;
  threads.refresh().then(() => threads.setActive(id));
  setTimeout(() => threads.refresh().then(() => threads.setActive(id)), 6000);
}

const chat = createChat({ store, orb, audioEl, onConversation });
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
  // Limpa a tela na hora — o /reset responde sem esperar RAG/LLM. A conversa
  // nova só vira nota (e entra na lista) no primeiro turno.
  chat.clear();
  currentConversation = null;
  threads.setActive(null);
  input.focus();
  try {
    await reset();
  } catch (e) {
    console.error(e);
  }
  // O título da conversa anterior é resumido em segundo plano.
  setTimeout(() => threads.refresh(), 6000);
});

muteBtn.addEventListener("click", () => {
  const muted = !store.get().muted;
  store.set({ muted });
  if (muted) audioEl.pause();
  muteBtn.textContent = muted ? "🔇" : "🔊";
  muteBtn.setAttribute("aria-pressed", String(muted));
});

const spotify = createSpotify({ store });

const tabChat = document.getElementById("tab-chat");
const tabSpotify = document.getElementById("tab-spotify");
const viewChat = document.getElementById("view-chat");
const viewSpotify = document.getElementById("view-spotify");

function activateTab(name) {
  const isChat = name === "chat";
  viewChat.hidden = !isChat;
  viewSpotify.hidden = isChat;
  tabChat.classList.toggle("active", isChat);
  tabSpotify.classList.toggle("active", !isChat);
  tabChat.setAttribute("aria-selected", String(isChat));
  tabSpotify.setAttribute("aria-selected", String(!isChat));
  if (!isChat) spotify.activate();
}

tabChat.addEventListener("click", () => activateTab("chat"));
tabSpotify.addEventListener("click", () => activateTab("spotify"));

// Depois do OAuth, /spotify/callback (interfaces/api.py) redireciona pra cá
// com ?spotify=conectado|erro — a aba Spotify precisa abrir sozinha, senão
// o usuário volta pro Chat sem ver o resultado do login.
const veioDoCallback = spotifyCallbackParam(window.location.search) !== null;
activateTab(veioDoCallback ? "spotify" : "chat");

voice.bind();
threads.refresh();
orb.setState("idle");
