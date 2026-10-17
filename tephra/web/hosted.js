// A hosted airline's Feeds and Settings pages (SPEC-FINAL 5.5-5.6), one shell (hosted.html) for
// /a/<ICAO>/feeds and /a/<ICAO>/settings[/policy|assistant|people|record]. The path names the
// section; tenant-nav.js draws the header from TenantHeader, and the section module draws the page
// from its own GET /a/<ICAO>/api/tenant/... answer. Ops managers change settings; dispatchers and
// viewers read them, and a suspended airline's pages are read-only (writes answer 403). This file
// also holds the small parts the section modules share (roles, error words, dialogs, the copy box).
// Every string goes in through textContent.

import { el, icon } from "./wall/util.js";
import { TENANT, PAGE_BASE } from "./base.js";
import { call, errorCode, retryMinutes, minutesWords, waitWords } from "./workspace/api.js";
import { mountTenantNav, onTenantHeader, titleFor, footerWords, ROLE_WORDS } from "./tenant-nav.js";

export const RANK = { viewer: 0, dispatcher: 1, ops_manager: 2 };
export const SETTINGS_TABS = [
  { key: "policy", name: "Policy", icon: "i-gauge", title: "Ash policy" },
  { key: "assistant", name: "Assistant", icon: "ta-16", title: "TEPHRA Assistant" },
  { key: "people", name: "People", icon: "i-user", title: "People" },
  { key: "record", name: "Record", icon: "i-list", title: "Record" },
];
export const SETTINGS_LEAD = "Ops managers change settings. Dispatchers and viewers read them.";

// What the person may do here: `need` is a role; nothing is written while the airline is suspended.
export function can(h, need) {
  const role = h?.you?.role;
  return role != null && RANK[role] >= RANK[need] && h.state !== "suspended";
}
export const roleWords = (role) => ROLE_WORDS[role] || role || "";

// A section path: "feeds", or "settings/<tab>" (an unknown tab reads as no page).
export function sectionOf(pathname) {
  const rest = String(pathname).replace(/^\/a\/[A-Z]{3}/, "").replace(/\/+$/, "");
  if (rest === "/feeds") return { section: "feeds", tab: null };
  if (rest === "/settings") return { section: "settings", tab: "policy" };
  const m = /^\/settings\/([a-z]+)$/.exec(rest);
  if (m && SETTINGS_TABS.some((t) => t.key === m[1])) return { section: "settings", tab: m[1] };
  return { section: null, tab: null };
}

// The words for an answer a view does not handle itself (the server's codes, never its input).
export function errorWords(res, h = null) {
  const code = errorCode(res);
  const name = h?.name || "this airline";
  if (!res || res.status === 0) return "You're offline. Try again when you are back online.";
  if (res.status === 401) return "Your sign-in has ended. Sign in again.";
  if (code === "tenant_suspended") return `${name} is suspended: its pages are read-only.`;
  if (code === "role") return h?.you?.role === "viewer" ? `Your role in ${name} is Viewer. Ops managers and dispatchers decide.` : "Only an ops manager can do this.";
  if (code === "not_started") return `TEPHRA has not started for ${name} yet.`;
  if (code === "version_conflict" || (res.status === 409 && !code)) return "Someone changed this in another tab. Reload to see it.";
  if (code === "airline_paused") return `Not done: it would use more than ${name}'s free daily database allowance left.`;
  if (code === "site_paused") return "Not done: the shared site's free daily database allowance is used.";
  if (res.status === 429) return `Not done: the limit for this is reached. Try again in about ${waitWords(res)}.`;
  if (res.status === 413) return "This is larger than the server takes.";
  return `Not done (HTTP ${res.status}).`;
}
export { call, errorCode, retryMinutes, minutesWords };

// ------------------------------------------------------------------ shared parts

export const announce = (text) => {
  const a = document.getElementById("announcer");
  if (a) { a.textContent = ""; window.setTimeout(() => { a.textContent = text; }, 30); }
};

export function pageHead(title, lead, ...right) {
  return el("header", { class: "hhead" }, el("div", {}, el("h1", { class: "h1", id: "page-h", tabindex: "-1", text: title }), lead ? el("p", { class: "body2", text: lead }) : null), ...right);
}

// Loading (states.html): skeleton lines and the word, no numbers until real ones arrive.
export function loadingCard(title) {
  return el("section", { class: "card wcard", "aria-busy": "true" },
    el("div", { class: "wcard__h" }, el("h2", { text: title }), el("span", { class: "tdim", text: "Loading…" })),
    el("span", { class: "skel skel--w60" }), el("span", { class: "skel skel--w40" }));
}

export function failCard(res, h, { title = "Not loaded" } = {}) {
  return el("section", { class: "card wcard", role: "alert" },
    el("div", { class: "wcard__h" }, el("span", { class: "wcard__ic wcard__ic--bad" }, icon("i-alert")), el("h2", { text: title })),
    el("p", { text: errorWords(res, h) }));
}

// A line under a form or a button that says what happened, in words with a shape.
export function inlineStatus(id) {
  const node = el("p", { id, class: "hstatus", role: "status", hidden: true });
  node.say = (text, tone = "bad") => {
    node.hidden = !text;
    node.dataset.tone = tone;
    node.replaceChildren(...(text ? [icon(tone === "ok" ? "i-check" : "i-alert"), el("span", { text })] : []));
  };
  return node;
}

// The secret shown once (a push key, an invite link): select-all, a Copy button, its words.
export function onceBox(lead, secret, ...words) {
  const code = el("code", { text: secret });
  const copy = el("button", { type: "button", class: "btn btn--secondary btn--sm once__copy" }, el("span", { text: "Copy" }));
  copy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(secret);
      copy.firstChild.textContent = "Copied";
      announce("Copied.");
    } catch {
      const range = document.createRange();
      range.selectNodeContents(code);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      copy.firstChild.textContent = "Selected: press Ctrl+C";
    }
  });
  return el("div", { class: "once", role: "status" }, el("p", {}, lead), el("div", { class: "once__row" }, code, copy), ...words.map((w) => el("p", {}, w)));
}

// After an action draws a part of the page again, focus never drops to <body>: it goes to the Copy
// button of a secret shown once, else to `prefer` (the part's heading), else the page heading.
// Drawn while the dialog is still open, the target is focused when the dialog closes (its opener
// is gone by then).
let pendingFocus = null;
export function refocus(host, prefer = null) {
  if (document.getElementById("h-dlg")?.open) { pendingFocus = { host, prefer }; return; }
  const now = document.activeElement;
  if (now && now !== document.body && now.isConnected) return;
  const target = host.querySelector(".once__copy") || (prefer ? host.querySelector(prefer) : null) || document.getElementById("page-h");
  if (!target) return;
  const own = ["BUTTON", "A", "INPUT", "SELECT", "TEXTAREA"].includes(String(target.tagName).toUpperCase());
  if (!own && target.getAttribute("tabindex") == null) target.setAttribute("tabindex", "-1");
  target.focus();
}

// The one dialog of the page (hosted.html #h-dlg): a heading, the body, and named buttons. `go`
// runs on submit and returns true to close; it keeps the dialog open with its own words otherwise.
export function openDialog({ id, title, body = [], goText, tone = "primary", go }) {
  const dlg = document.getElementById("h-dlg");
  const cancel = el("button", { type: "button", class: "btn btn--secondary", text: "Cancel" });
  const ok = el("button", { type: "submit", class: `btn btn--${tone}` }, el("span", { text: goText }));
  const status = inlineStatus(`${id}-status`);
  const form = el("form", { class: "pdlg__form", novalidate: true },
    el("h2", { id: `${id}-h`, class: "h2", text: title }), ...body, status, el("div", { class: "pdlg__acts" }, cancel, ok));
  dlg.className = "pdlg";
  dlg.replaceChildren(form);
  dlg.setAttribute("aria-labelledby", `${id}-h`);
  const opener = document.activeElement;
  cancel.addEventListener("click", () => dlg.close());
  pendingFocus = null;
  dlg.addEventListener("close", () => {
    const after = pendingFocus;
    pendingFocus = null;
    if (opener && opener.isConnected) opener.focus();
    else if (after) refocus(after.host, after.prefer);
  }, { once: true });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    ok.disabled = true;
    try {
      if (await go(status)) dlg.close();
    } finally {
      ok.disabled = false;
    }
  });
  dlg.showModal();
  (form.querySelector("input, select, textarea") || ok).focus();
  return { dlg, status };
}

// A reason field (3-300 characters) for the dialogs that ask why.
export function reasonField(id, label, { min = 3, max = 300, hint = null } = {}) {
  const area = el("textarea", { id, class: "input textarea", rows: "3", maxlength: String(max), "aria-describedby": `${id}-err${hint ? ` ${id}-hint` : ""}` });
  const err = el("p", { id: `${id}-err`, class: "err", hidden: true });
  const node = el("div", { class: "field" }, el("label", { for: id, text: label }), area, hint ? el("p", { id: `${id}-hint`, class: "hint", text: hint }) : null, err);
  node.value = () => area.value.trim();
  node.check = () => {
    const v = area.value.trim();
    const bad = v.length < min ? `Give a reason of at least ${min} characters.` : v.length > max ? `At most ${max} characters.` : null;
    area.setAttribute("aria-invalid", bad ? "true" : "false");
    err.hidden = !bad;
    err.replaceChildren(...(bad ? [icon("i-alert"), el("span", { text: bad })] : []));
    if (bad) area.focus();
    return !bad;
  };
  return node;
}

export const notBuiltNote = (text) => el("div", { class: "note note--notbuilt" }, icon("i-info"), el("p", {}, el("b", { text: "Not built. " }), text));
export const readOnlyNote = (h) => el("p", { class: "ah-viewer", text: h.state === "suspended" ? `${h.name} is suspended: these pages are read-only.` : SETTINGS_LEAD });

// ------------------------------------------------------------------ the page

const MODULES = {
  feeds: () => import("./hosted/feeds.js"),
  policy: () => import("./hosted/policy.js"),
  assistant: () => import("./hosted/assistant.js"),
  people: () => import("./hosted/people.js"),
  record: () => import("./hosted/record.js"),
};

function settingsShell(tab) {
  const nav = el("nav", { class: "ws__nav", "aria-label": "Settings" },
    ...SETTINGS_TABS.map((t) => el("a", { href: `${PAGE_BASE}/settings/${t.key}`, "aria-current": t.key === tab ? "page" : null }, icon(t.icon), el("span", { text: t.name }))),
    el("hr"),
    el("p", { class: "ws__who", text: SETTINGS_LEAD }));
  const main = el("div", { class: "hset__main" });
  return { node: el("div", { class: "hset" }, nav, main), main };
}

let drawnFor = "";
async function draw(h, where) {
  const key = `${h.state}|${h.you?.role}`;
  if (key === drawnFor) return;
  const first = !drawnFor;
  drawnFor = key;
  const main = document.getElementById("main");
  const tab = where.section === "settings" ? SETTINGS_TABS.find((t) => t.key === where.tab) : null;
  document.title = titleFor(h, tab ? `${tab.name} · Settings` : "Feeds");
  document.getElementById("foot-words").textContent = footerWords(h);
  let host;
  if (tab) {
    const shell = settingsShell(tab.key);
    main.replaceChildren(shell.node);
    host = shell.main;
  } else {
    host = el("div", { class: "hpage" });
    main.replaceChildren(host);
  }
  const mod = await MODULES[where.tab || where.section]();
  await mod.mount(host, h);
  if (first && location.hash === "") document.getElementById("page-h")?.focus({ preventScroll: true });
  else if (first) {
    // a link to a part of the page (the checklist's #versions): drawn only now, so go there now
    const part = document.getElementById(decodeURIComponent(location.hash.slice(1)));
    if (part) { part.scrollIntoView({ block: "start" }); (part.querySelector("h2[tabindex]") || part).focus({ preventScroll: true }); }
  }
}

function noPage() {
  document.getElementById("main").replaceChildren(el("div", { class: "hpage" },
    pageHead("No such page", null),
    el("p", { class: "body2" }, "This airline's pages are ", el("a", { class: "link", href: `${PAGE_BASE}/`, text: "Map" }), ", ", el("a", { class: "link", href: `${PAGE_BASE}/desk`, text: "Desk" }), ", ", el("a", { class: "link", href: `${PAGE_BASE}/feeds`, text: "Feeds" }), " and ", el("a", { class: "link", href: `${PAGE_BASE}/settings`, text: "Settings" }), ".")));
}

function boot() {
  const where = sectionOf(location.pathname);
  mountTenantNav({ bar: document.getElementById("ah-bar"), section: where.section || "settings" });
  if (!where.section) { noPage(); return; }
  const main = document.getElementById("main");
  main.replaceChildren(el("div", { class: "hpage" }, loadingCard(where.section === "feeds" ? "Feeds" : "Settings")));
  onTenantHeader((h, { error }) => {
    if (h) draw(h, where);
    else if (error && error !== "offline") main.replaceChildren();
  });
}

if (TENANT && globalThis.document?.body?.classList.contains("hosted")) boot();
