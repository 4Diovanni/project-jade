import { listConversations, getConversation } from "./api.js";

export function createThreads({ chat }) {
  const ul = document.getElementById("threads-list");

  async function refresh() {
    ul.innerHTML = "";
    let convs = [];
    try {
      convs = await listConversations();
    } catch {
      return;
    }
    for (const c of convs) {
      const li = document.createElement("li");
      li.textContent = c.title || c.id;
      li.title = c.date || "";
      li.dataset.id = c.id;
      li.addEventListener("click", () => openThread(c.id, li));
      ul.appendChild(li);
    }
  }

  async function openThread(id, li) {
    for (const el of ul.children) el.classList.toggle("active", el === li);
    let data;
    try {
      data = await getConversation(id);
    } catch {
      return;
    }
    chat.clear();
    for (const t of data.turns) {
      chat.addBubble("user", t.user);
      chat.addBubble("jade", t.jade);
    }
  }

  return { refresh, openThread };
}
