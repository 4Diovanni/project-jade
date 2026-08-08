// Filtro puro da lista de faixas do Spotify (sem DOM) — testável em Node.
export function filterTracks(tracks, term) {
  const needle = (term || "").trim().toLowerCase();
  if (!needle) return tracks;
  return tracks.filter(
    (t) => t.name.toLowerCase().includes(needle) || t.artists.toLowerCase().includes(needle),
  );
}
