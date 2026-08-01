// Renderizador de Markdown mínimo e seguro (sem dependências, sem build).
// Escapa TODO o HTML de entrada antes de aplicar a formatação, para nunca
// injetar tags cruas vindas do texto (proteção contra XSS). Cobre o que o LLM
// costuma produzir: cabeçalhos, negrito/itálico, código (inline e em bloco),
// listas, links e parágrafos. Puro e testável em Node.

function escapeHtml(s) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function safeUrl(url) {
  // Só permite esquemas seguros; qualquer outro (ex.: javascript:) vira "#".
  return /^(https?:|mailto:)/i.test(url.trim()) ? url.trim() : "#";
}

function inline(text) {
  // Formatações inline aplicadas sobre texto JÁ escapado.
  return text
    .replace(/`([^`]+)`/g, (_, c) => `<code>${c}</code>`)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+)__/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/(^|[^_])_([^_]+)_/g, "$1<em>$2</em>")
    .replace(
      /\[([^\]]+)\]\(([^)]+)\)/g,
      (_, t, u) => `<a href="${safeUrl(u)}" target="_blank" rel="noopener noreferrer">${t}</a>`,
    );
}

export function renderMarkdown(md) {
  if (!md) return "";
  const lines = escapeHtml(String(md)).split("\n");
  const out = [];
  let listType = null; // "ul" | "ol" | null

  const closeList = () => {
    if (listType) {
      out.push(`</${listType}>`);
      listType = null;
    }
  };

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];

    // Bloco de código cercado ```
    if (/^```/.test(line)) {
      closeList();
      const code = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) {
        code.push(lines[i]);
        i++;
      }
      i++; // pula a cerca final
      out.push(`<pre><code>${code.join("\n")}</code></pre>`);
      continue;
    }

    // Cabeçalhos # ## ###
    const h = line.match(/^(#{1,3})\s+(.*)$/);
    if (h) {
      closeList();
      const level = h[1].length;
      out.push(`<h${level}>${inline(h[2])}</h${level}>`);
      i++;
      continue;
    }

    // Lista não ordenada
    const ul = line.match(/^\s*[-*]\s+(.*)$/);
    if (ul) {
      if (listType !== "ul") {
        closeList();
        out.push("<ul>");
        listType = "ul";
      }
      out.push(`<li>${inline(ul[1])}</li>`);
      i++;
      continue;
    }

    // Lista ordenada
    const ol = line.match(/^\s*\d+\.\s+(.*)$/);
    if (ol) {
      if (listType !== "ol") {
        closeList();
        out.push("<ol>");
        listType = "ol";
      }
      out.push(`<li>${inline(ol[1])}</li>`);
      i++;
      continue;
    }

    // Linha em branco separa blocos
    if (line.trim() === "") {
      closeList();
      i++;
      continue;
    }

    // Parágrafo (agrupa linhas consecutivas de texto)
    closeList();
    const para = [line];
    i++;
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !/^(#{1,3}\s|```|\s*[-*]\s|\s*\d+\.\s)/.test(lines[i])
    ) {
      para.push(lines[i]);
      i++;
    }
    out.push(`<p>${inline(para.join("<br>"))}</p>`);
  }
  closeList();
  return out.join("\n");
}
