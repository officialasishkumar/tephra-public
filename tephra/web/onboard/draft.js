// The one onboarding file that touches localStorage (every access in try/catch; the pages work
// without it). The answers live in the airline's account from sign-up on; this browser keeps only
// what never goes to the server: the schedule files' text, so the Schedule page can check them
// again after a reload (only their counts go with the answers). Never stored: a password, a
// recovery code or a Gemini key.
// One older key is read once: answers an earlier version of these pages kept in the browser,
// moved into the new account at sign-up and then removed.

export const LOCAL_KEY = "tephra.onboard.local.v2";
const LEGACY_DRAFT_KEY = "tephra.onboard.draft.v2";

function read(key) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

// "ok", "quota" (the browser's storage is full) or "blocked" (storage refused or absent).
function write(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    return "ok";
  } catch (e) {
    return e && (e.name === "QuotaExceededError" || e.code === 22) ? "quota" : "blocked";
  }
}

function remove(key) {
  try {
    localStorage.removeItem(key);
  } catch {
    // Nothing was kept, or the browser refuses storage: either way nothing is left.
  }
}

export function loadLocal() {
  const l = read(LOCAL_KEY);
  return { files: l && typeof l === "object" && l.files && typeof l.files === "object" ? l.files : {} };
}

// The local part: "ok", "quota" (the schedule files do not fit; none is kept) or "blocked".
export function saveLocal(local) {
  const state = write(LOCAL_KEY, local);
  if (state !== "quota") return state;
  remove(LOCAL_KEY);
  return "quota";
}

// Answers an earlier version of the pages kept in this browser ({ seen, at, values }), or null.
export function loadLegacyDraft() {
  const d = read(LEGACY_DRAFT_KEY);
  return d && d.v === 2 && d.values && typeof d.values === "object" ? { seen: Array.isArray(d.seen) ? d.seen : [], at: d.at || null, values: d.values } : null;
}

export const dropLegacyDraft = () => remove(LEGACY_DRAFT_KEY);

// Sign out and Delete account: nothing of the airline's stays in this browser (a shared computer
// must not keep its schedule files).
export function clearOnboardStorage() {
  remove(LEGACY_DRAFT_KEY);
  remove(LOCAL_KEY);
}
