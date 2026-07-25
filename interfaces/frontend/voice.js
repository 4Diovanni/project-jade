import { voiceChat } from "./api.js";

export function createVoice({ store, orb, chat, audioEl }) {
  const btn = document.getElementById("mic-btn");
  let recorder = null;
  let chunks = [];
  let stream = null;
  let recording = false;
  let starting = false;
  let cancelRequested = false;

  async function start() {
    if (recording || starting || store.get().busy) return;
    starting = true;
    cancelRequested = false;
    let s;
    try {
      s = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      starting = false;
      orb.setState("idle");
      chat.addBubble("error", "Preciso de permissão do microfone para te ouvir.");
      return;
    }
    starting = false;
    if (cancelRequested) {
      // soltou o botão antes do mic liberar: não grava e fecha o stream.
      for (const track of s.getTracks()) track.stop();
      return;
    }
    stream = s;
    recording = true;
    btn.classList.add("recording");
    orb.connectMic(stream);
    orb.setState("listening");
    chunks = [];
    recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (e) => chunks.push(e.data);
    recorder.start();
  }

  async function stop() {
    if (starting) { cancelRequested = true; return; }
    if (!recording) return;
    recording = false;
    btn.classList.remove("recording");
    await new Promise((resolve) => {
      recorder.onstop = resolve;
      recorder.stop();
    });
    for (const track of stream.getTracks()) track.stop();
    const blob = new Blob(chunks, { type: "audio/webm" });
    store.set({ busy: true });
    orb.setState("thinking");
    try {
      const { transcription, reply, audio_url, model } = await voiceChat(blob);
      chat.addBubble("user", transcription);
      chat.addBubble("jade", reply, model);
      store.set({ busy: false });
      if (!store.get().muted && audio_url) {
        audioEl.src = audio_url;
        orb.connectAudio(audioEl);
        orb.setState("speaking");
        audioEl.onended = () => orb.setState("idle");
        await audioEl.play();
      } else {
        orb.setState("idle");
      }
    } catch (e) {
      console.error(e);
      chat.addBubble("error", "Não consegui te ouvir agora.");
      store.set({ busy: false });
      orb.setState("idle");
    }
  }

  function bind() {
    btn.addEventListener("mousedown", start);
    btn.addEventListener("mouseup", stop);
    btn.addEventListener("mouseleave", () => recording && stop());
    btn.addEventListener("touchstart", (e) => { e.preventDefault(); start(); });
    btn.addEventListener("touchend", (e) => { e.preventDefault(); stop(); });
    // Atalho: segurar espaço (fora do campo de texto).
    window.addEventListener("keydown", (e) => {
      if (e.code === "Space" && !/^(INPUT|TEXTAREA)$/.test(e.target.tagName) && !e.target.isContentEditable && !recording && !starting) {
        e.preventDefault();
        start();
      }
    });
    window.addEventListener("keyup", (e) => {
      if (e.code === "Space" && recording) stop();
    });
  }

  return { bind };
}
