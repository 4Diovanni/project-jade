import { amplitudeToVisual } from "./lib/orb-visual.js";

const COLORS = { jade: "#00bb77", spring: "#00ff7f", emerald: "#00674f" };

export function createOrb(canvas) {
  const ctx = canvas.getContext("2d");
  let state = "idle";
  let audioCtx = null;
  let analyser = null;
  let micSource = null;
  let mediaSource = null;
  const bins = 64;
  let bytes = new Uint8Array(bins);
  let t = 0;

  function ensureAudio() {
    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = bins * 2;
      bytes = new Uint8Array(analyser.frequencyBinCount);
    }
    if (audioCtx.state === "suspended") audioCtx.resume();
    return audioCtx;
  }

  function draw() {
    t += 0.03;
    const w = canvas.width, h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    let energy = 0;
    if (analyser && (state === "listening" || state === "speaking")) {
      analyser.getByteFrequencyData(bytes);
      energy = amplitudeToVisual(bytes).energy;
    } else if (state === "thinking") {
      energy = 0.15 + 0.1 * Math.abs(Math.sin(t * 2));
    } else {
      energy = 0.05 + 0.03 * Math.abs(Math.sin(t)); // respiração idle
    }
    const min = Math.min(w, h);
    const base = amplitudeToVisual(bytes.length ? bytes : new Uint8Array(bins));
    const radius = (state === "idle" ? 0.32 : base.radius) * min * 0.5 * (0.9 + energy);
    const cx = w / 2, cy = h / 2;

    const grad = ctx.createRadialGradient(cx, cy, radius * 0.2, cx, cy, radius);
    grad.addColorStop(0, COLORS.spring);
    grad.addColorStop(0.6, COLORS.jade);
    grad.addColorStop(1, COLORS.emerald);
    ctx.globalAlpha = 0.9;
    ctx.shadowBlur = 8 + 40 * energy;
    ctx.shadowColor = COLORS.jade;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.fillStyle = grad;
    ctx.fill();

    // anel giratório no estado "thinking"
    if (state === "thinking") {
      ctx.globalAlpha = 0.7;
      ctx.strokeStyle = COLORS.spring;
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.arc(cx, cy, radius * 1.25, t, t + Math.PI);
      ctx.stroke();
    }
    ctx.shadowBlur = 0;
    ctx.globalAlpha = 1;
    requestAnimationFrame(draw);
  }
  requestAnimationFrame(draw);

  return {
    setState(name) { state = name; },
    connectMic(stream) {
      ensureAudio();
      if (micSource) micSource.disconnect();
      micSource = audioCtx.createMediaStreamSource(stream);
      micSource.connect(analyser); // não conecta ao destino (evita microfonia)
    },
    connectAudio(audioEl) {
      ensureAudio();
      if (!mediaSource) mediaSource = audioCtx.createMediaElementSource(audioEl);
      mediaSource.connect(analyser);
      mediaSource.connect(audioCtx.destination);
    },
  };
}
