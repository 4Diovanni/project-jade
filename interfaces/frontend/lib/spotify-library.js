// Agrupamento puro do cache de faixas por playlist (sem DOM) — testável em
// Node. O backend (/spotify/library, interfaces/api.py::spotify_library) já
// devolve { playlists: { nomeDaPlaylist: [faixas] } }; esta função aplica o
// filtro de busca por grupo e descarta grupos que ficam vazios depois do
// filtro, mantendo o agrupamento visível na hora de renderizar (spec:
// docs/superpowers/specs/2026-08-08-spotify-design.md, Objetivos, item 5).
import { filterTracks } from "./spotify-filter.js";

export function groupLibrary(library, term) {
  const playlists = (library && library.playlists) || {};
  const grouped = {};
  for (const [playlistName, tracks] of Object.entries(playlists)) {
    const filtered = filterTracks(tracks, term);
    if (filtered.length > 0) {
      grouped[playlistName] = filtered;
    }
  }
  return grouped;
}
