import { listConversations, getConversation, renameConversation } from "./api.js";

export function createThreads({ chat }) {
  const ul = document.getElementById("threads-list");
  let activeId = null;

  function highlight() {
    for (const el of ul.children) el.classList.toggle("active", el.dataset.id === activeId);
  }

  async function refresh() {
    let convs = [];
    try {
      convs = await listConversations();
    } catch (e) {
      console.error(e);
      return;
    }
    ul.innerHTML = "";
    for (const c of convs) {
      const li = document.createElement("li");
      li.dataset.id = c.id;

      const span = document.createElement("span");
      span.className = "thread-title";
      span.textContent = c.title || c.id;
      span.title = c.date || "";
      span.addEventListener("click", () => openThread(c.id));

      const btn = document.createElement("button");
      btn.className = "thread-rename";
      btn.type = "button";
      btn.textContent = "✏️";
      btn.title = "Renomear conversa";
      btn.addEventListener("click", (e) => {
        e.stopPropagation(); // renomear não abre a conversa
        rename(c.id, span.textContent);
      });

      li.append(span, btn);
      ul.appendChild(li);
    }
    highlight();
  }

  async function rename(id, current) {
    const escolhido = window.prompt("Nome da conversa:", current);
    if (escolhido === null) return; // cancelou
    const title = escolhido.trim();
    if (!title || title === current) return;
    try {
      await renameConversation(id, title);
    } catch (e) {
      console.error(e);
      return;
    }
    await refresh();
  }

  async function openThread(id) {
    let data;
    try {
      data = await getConversation(id);
    } catch (e) {
      console.error(e);
      return;
    }
    activeId = id;
    highlight();
    chat.clear();
    for (const t of data.turns) {
      chat.addBubble("user", t.user);
      chat.addBubble("jade", t.jade);
    }
  }

  /** Marca qual conversa está ativa (a da sessão em andamento). */
  function setActive(id) {
    activeId = id;
    highlight();
  }

  return { refresh, openThread, setActive };
}
