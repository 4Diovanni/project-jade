// Aba "Spotify": lista de faixas cacheadas (filtro local) + card oficial de
// embed ao selecionar uma faixa. DOM-wiring — não testado por unidade
// (mesmo padrão de chat.js/threads.js); verificado manualmente no browser.
// spotifyCallbackParam() é a única parte pura daqui, por isso é a única
// exportada para teste (interfaces/frontend/__tests__/spotify.test.js).
import { getSpotifyLibrary, getSpotifyStatus, syncSpotifyNow } from "./api.js";
import { groupLibrary } from "./lib/spotify-library.js";

const POLL_INTERVAL_MS = 1500;
const POLL_MAX_ATTEMPTS = 20; // ~30s — depois disso desiste e deixa o botão manual

// Pura — testável sem DOM. `search` é window.location.search. /spotify/callback
// (interfaces/api.py) redireciona pra "/app/?spotify=conectado" ou "=erro".
export function spotifyCallbackParam(search) {
  return new URLSearchParams(search).get("spotify");
}

export function createSpotify({ store } = {}) {
  const filterInput = document.getElementById("spotify-filter");
  const syncBtn = document.getElementById("spotify-sync-btn");
  const statusEl = document.getElementById("spotify-status");
  const listEl = document.getElementById("spotify-list");
  const cardEl = document.getElementById("spotify-card");

  // Estado como vem da API: { playlists: { nomeDaPlaylist: [faixas] } } — o
  // agrupamento é preservado (não achata em lista única) para renderizar
  // por playlist (spec: seção Objetivos, item 5).
  let library = { playlists: {} };
  let loaded = false;

  function renderList(grouped) {
    listEl.innerHTML = "";
    for (const [playlistName, tracks] of Object.entries(grouped)) {
      const header = document.createElement("li");
      header.className = "spotify-playlist-header";
      header.textContent = playlistName;
      listEl.appendChild(header);
      for (const t of tracks) {
        const li = document.createElement("li");
        li.className = "spotify-track";
        li.textContent = `${t.name} — ${t.artists}`;
        li.addEventListener("click", () => selectTrack(t));
        listEl.appendChild(li);
      }
    }
  }

  function selectTrack(track) {
    cardEl.innerHTML = "";
    const iframe = document.createElement("iframe");
    iframe.src = `https://open.spotify.com/embed/track/${track.id}`;
    iframe.width = "100%";
    iframe.height = "152";
    iframe.style.border = "0";
    iframe.allow = "encrypted-media";
    cardEl.appendChild(iframe);
  }

  function applyFilter() {
    renderList(groupLibrary(library, filterInput.value));
  }

  function renderDesconectado() {
    statusEl.innerHTML = "";
    statusEl.append("Não conectado. ");
    const link = document.createElement("a");
    link.href = "/spotify/login";
    link.textContent = "Conectar ao Spotify";
    statusEl.appendChild(link);
    listEl.innerHTML = "";
    cardEl.innerHTML = "";
  }

  function renderErro() {
    statusEl.innerHTML = "";
    statusEl.append("Não consegui conectar ao Spotify. ");
    const link = document.createElement("a");
    link.href = "/spotify/login";
    link.textContent = "Tentar novamente";
    statusEl.appendChild(link);
    listEl.innerHTML = "";
    cardEl.innerHTML = "";
  }

  async function loadLibrary(trackCount) {
    statusEl.textContent = `${trackCount} faixa(s) no cache.`;
    library = await getSpotifyLibrary();
    applyFilter();
  }

  // Logo após o OAuth, o /spotify/callback já redirecionou de volta antes de
  // a sincronização inicial (em thread de background) terminar — sem isso, a
  // aba mostraria "0 faixas" mesmo com a conta recém-conectada.
  function pollUntilSynced(attempt = 0) {
    statusEl.textContent = "Sincronizando sua biblioteca…";
    if (attempt >= POLL_MAX_ATTEMPTS) {
      statusEl.textContent =
        'Não consegui confirmar a sincronização. Clique em "Sincronizar agora" pra tentar de novo.';
      return;
    }
    setTimeout(async () => {
      try {
        const status = await getSpotifyStatus();
        if (status.track_count > 0) {
          await loadLibrary(status.track_count);
        } else {
          pollUntilSynced(attempt + 1);
        }
      } catch (e) {
        console.error(e);
        statusEl.textContent =
          'Não consegui confirmar a sincronização. Clique em "Sincronizar agora" pra tentar de novo.';
      }
    }, POLL_INTERVAL_MS);
  }

  async function load() {
    const callbackParam = spotifyCallbackParam(window.location.search);
    if (callbackParam === "erro") {
      renderErro();
      return;
    }
    const status = await getSpotifyStatus();
    if (!status.linked) {
      renderDesconectado();
      return;
    }
    if (status.track_count === 0 && callbackParam === "conectado") {
      pollUntilSynced();
      return;
    }
    await loadLibrary(status.track_count);
  }

  filterInput.addEventListener("input", applyFilter);
  syncBtn.addEventListener("click", async () => {
    statusEl.textContent = "Sincronizando…";
    try {
      await syncSpotifyNow();
    } catch (e) {
      console.error(e);
    }
    await load().catch((e) => console.error(e));
  });

  function activate() {
    if (loaded) return;
    loaded = true;
    load().catch((e) => console.error(e));
  }

  return { activate };
}
