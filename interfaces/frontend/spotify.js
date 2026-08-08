// Aba "Spotify": lista de faixas cacheadas (filtro local) + card oficial de
// embed ao selecionar uma faixa. DOM-wiring — não testado por unidade
// (mesmo padrão de chat.js/threads.js); verificado manualmente no browser.
// spotifyCallbackParam() é a única parte pura daqui, por isso é a única
// exportada para teste (interfaces/frontend/__tests__/spotify.test.js).
import { getSpotifyLibrary, getSpotifyStatus, syncSpotifyNow } from "./api.js";
import { filterTracks } from "./lib/spotify-filter.js";

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

  let allTracks = [];
  let loaded = false;

  function renderList(tracks) {
    listEl.innerHTML = "";
    for (const t of tracks) {
      const li = document.createElement("li");
      li.className = "spotify-track";
      li.textContent = `${t.name} — ${t.artists}`;
      li.addEventListener("click", () => selectTrack(t));
      listEl.appendChild(li);
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
    renderList(filterTracks(allTracks, filterInput.value));
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
    const library = await getSpotifyLibrary();
    allTracks = Object.values(library.playlists).flat();
    applyFilter();
  }

  // Logo após o OAuth, o /spotify/callback já redirecionou de volta antes de
  // a sincronização inicial (em thread de background) terminar — sem isso, a
  // aba mostraria "0 faixas" mesmo com a conta recém-conectada.
  function pollUntilSynced(attempt = 0) {
    statusEl.textContent = "Sincronizando sua biblioteca…";
    if (attempt >= POLL_MAX_ATTEMPTS) return;
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
