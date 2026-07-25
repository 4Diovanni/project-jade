// Mapeia dados de frequência (0..255) para parâmetros visuais do orb. Puro.
const BASE_RADIUS = 0.35; // fração do menor lado do canvas
const MAX_GROWTH = 0.45;

export function amplitudeToVisual(bytes) {
  const n = bytes.length;
  let sum = 0;
  for (let i = 0; i < n; i++) sum += bytes[i];
  const energy = n ? sum / n / 255 : 0; // 0..1
  return {
    energy,
    radius: BASE_RADIUS + MAX_GROWTH * energy,
    glow: 8 + 40 * energy,
  };
}
