// Rótulo curto de qual "cérebro" respondeu o turno. Puro.
const LABELS = { claude: "☁️ Claude", local: "local", tool: "ação" };

export function modelBadge(model) {
  return LABELS[model] || "";
}
