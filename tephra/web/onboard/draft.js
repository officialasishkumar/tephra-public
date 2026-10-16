// The one onboarding file that touches localStorage (every access in try/catch; the pages work
// without it). Two keys: the draft (the answers, written 400 ms after each change) and the local
// part that never goes to the server (the Ollama address and the schedule files' text, which
// the workspace's setup kit reads in this browser). Never stored: a password, a recovery code
// or a Gemini key.

export const DRAFT_KEY = "tephra.onboard.draft.v2";
export const LOCAL_KEY = "tephra.onboard.local.v2";
const SAVE_DELAY_MS = 400;

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

export function loadDraft() {
  const d = read(DRAFT_KEY);
  return d && d.v === 2 && d.values && typeof d.values === "object" ? { ...d, seen: Array.isArray(d.seen) ? d.seen : [] } : null;
}

export function loadLocal() {
  const l = read(LOCAL_KEY);
  return l && typeof l === "object" ? { ollama_url: typeof l.ollama_url === "string" ? l.ollama_url : null, files: l.files && typeof l.files === "object" ? l.files : {} } : { ollama_url: null, files: {} };
}

export const saveDraft = (draft) => write(DRAFT_KEY, { ...draft, v: 2, saved_at: new Date().toISOString() });

// The local part; when the schedule files do not fit, the address is kept without them and the
// answer says "quota" (the page then says the files are in memory only).
export function saveLocal(local) {
  const state = write(LOCAL_KEY, local);
  if (state !== "quota") return state;
  return write(LOCAL_KEY, { ...local, files: {} }) === "ok" ? "quota" : "blocked";
}

// One save 400 ms after the last change; `onState` hears "ok", "quota" or "blocked".
export function draftSaver(onState) {
  let timer = 0;
  let pending = null;
  const flush = () => {
    window.clearTimeout(timer);
    timer = 0;
    if (!pending) return;
    const { draft, local } = pending;
    pending = null;
    const d = saveDraft(draft);
    const l = local ? saveLocal(local) : "ok";
    onState(d !== "ok" ? "blocked" : l);
  };
  return {
    schedule(draft, local) {
      pending = { draft, local };
      window.clearTimeout(timer);
      timer = window.setTimeout(flush, SAVE_DELAY_MS);
    },
    flush,
  };
}

// After the account is created: the answers now live on the server; the local part stays for
// the setup kit in this browser.
export const clearDraft = () => remove(DRAFT_KEY);

// "Clear my answers", "Start over", Sign out and Delete account: nothing of the airline's stays
// in this browser (a shared computer must not keep its schedule files).
export function clearOnboardStorage() {
  remove(DRAFT_KEY);
  remove(LOCAL_KEY);
}
