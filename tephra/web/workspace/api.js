// HTTP for the onboarding and workspace pages: JSON in and out, the X-Tephra-Desk: 1 header the
// server's CSRF check asks for, and the error words every view shares. A network failure
// resolves to { status: 0 } so a caller never sees an exception.

// `keepalive` lets a save finish while the page closes (the browser caps such a body at 64 KB).
export async function call(path, { method = "GET", body, raw = null, signal, keepalive = false } = {}) {
  const headers = { Accept: "application/json", "X-Tephra-Desk": "1" };
  const init = { method, headers, credentials: "same-origin", cache: "no-store", signal, keepalive };
  if (raw !== null) {
    headers["Content-Type"] = "application/json";
    init.body = raw;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, init);
  } catch {
    return { ok: false, status: 0, data: null, headers: null };
  }
  let data = null;
  if ((res.headers.get("content-type") || "").includes("application/json")) {
    try {
      data = await res.json();
    } catch {
      data = null;
    }
  }
  return { ok: res.ok, status: res.status, data, headers: res.headers };
}

export async function text(path) {
  try {
    const res = await fetch(path, { credentials: "same-origin", cache: "no-store" });
    return res.ok ? await res.text() : null;
  } catch {
    return null;
  }
}

export const errorCode = (res) => (res && res.data && typeof res.data.error === "string" ? res.data.error : "");
export const problemsOf = (res) => (res && res.data && Array.isArray(res.data.problems) ? res.data.problems.filter((p) => typeof p === "string") : []);

// Retry-After in whole minutes, at least one.
export function retryMinutes(res) {
  const s = Number(res && res.headers && res.headers.get("retry-after"));
  return Number.isFinite(s) && s > 0 ? Math.max(1, Math.ceil(s / 60)) : 1;
}
export const minutesWords = (n) => `${n} ${n === 1 ? "minute" : "minutes"}`;
// A daily limit's wait reads in hours once it is past an hour and a half.
export function waitWords(res) {
  const m = retryMinutes(res);
  if (m <= 90) return minutesWords(m);
  const h = Math.round(m / 60);
  return `${h} ${h === 1 ? "hour" : "hours"}`;
}

export const ACCOUNTS_OFF = "Airline accounts are off on this server: TEPHRA_SESSION_SECRET is not set.";
export const ONBOARD_OFF = "Onboarding is off on this server.";

// The words for an answer no view handles itself.
export function failWords(res) {
  if (!res || res.status === 0) return "You're offline. Try again when you are back online.";
  const code = errorCode(res);
  if (code === "feature_off") return ONBOARD_OFF;
  if (code === "accounts_off") return ACCOUNTS_OFF;
  if (res.status === 401) return "Your sign-in has ended. Sign in again.";
  if (res.status === 409) return "Someone changed this in another tab. Reload to see it.";
  if (res.status === 429) return `Too many tries. Try again in about ${minutesWords(retryMinutes(res))}.`;
  return `Not done (HTTP ${res.status}).`;
}

export const PATHS = {
  state: "/api/state",
  policy: "/api/policy",
  airports: "/api/airports",
  session: "/api/airline/session",
  accounts: "/api/airline/accounts",
  signIn: "/api/airline/sign-in",
  recover: "/api/airline/recover",
  signOut: "/api/airline/sign-out",
  me: "/api/airline/me",
  answers: "/api/airline/answers",
  draft: "/api/airline/draft",
  submit: "/api/airline/submit",
  assistant: "/api/airline/assistant",
  remove: "/api/airline/delete",
  dryRun: "/api/airline/feeds/dry-run",
  schema: "/api/connect/schema.json",
  pushTool: "/static/kit/push.py",
};

// Hosting on this site (SPEC hosted §4.2): the root routes, and an airline's own routes under
// /a/<ICAO>/api/tenant. A code that is not three capitals never becomes a path.
export const HOSTED = {
  me: "/api/hosted/me",
  setup: "/api/hosted/setup",
  inviteLookup: "/api/hosted/invites/lookup",
  inviteAccept: "/api/hosted/invites/accept",
  inviteJoin: "/api/hosted/invites/join",
};
export const isIcao = (icao) => typeof icao === "string" && /^[A-Z]{3}$/.test(icao);
export function tenantApi(icao, path) {
  if (!isIcao(icao)) throw new Error("not an airline code");
  return `/a/${icao}/api/tenant${path}`;
}
export function spacePath(icao, path = "/") {
  if (!isIcao(icao)) throw new Error("not an airline code");
  return `/a/${icao}${path}`;
}
