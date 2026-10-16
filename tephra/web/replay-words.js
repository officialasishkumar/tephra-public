// The replay's words for Home and the welcome dialog: the volcano and the day that plays. Pure.
// The day is the window's start when the server loops a window (the part that plays: the shipped
// case records 5-7 Sep and plays 5 Sep), else the recording's first day, in UTC.

const MON3 = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// "Anak Krakatau: ash to FL500 closes Jakarta, 5-7 Sep 2026 (reconstructed)" -> "Anak Krakatau".
// A label that does not start with a name ("Java and Bali, live public feeds from 10 Oct 2026
// 06:00Z ...": its first colon is a time) has no volcano: null, and the words leave it out.
export function volcanoOf(replay) {
  const label = String(replay?.label || "");
  const at = label.indexOf(":");
  const name = at > 0 ? label.slice(0, at).trim() : "";
  return name && !/\d/.test(name) ? name : null;
}

// "5 Sep 2026", or null without a date
export function replayDay(replay) {
  const t = Date.parse(replay?.window_from || replay?.recorded_from || "");
  if (!Number.isFinite(t)) return null;
  const d = new Date(t);
  return `${d.getUTCDate()} ${MON3[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

// The manifest's label says when a case was rebuilt from archives rather than recorded live.
export const isReconstructed = (replay) => /\(reconstructed\)/.test(String(replay?.label || ""));

// What the replay is, for the words around it: "recorded", "reconstructed", "synthetic", or
// "live" when no replay plays (and null when the state is unknown).
export function replayKind(state) {
  if (!state) return null;
  if (state.mode !== "REPLAY") return "live";
  if (state.replay?.synthetic) return "synthetic";
  return isReconstructed(state.replay) ? "reconstructed" : "recorded";
}
