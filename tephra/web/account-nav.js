// The airline account in the shared header (SPEC-v2 3.1). Signed in, the nav's Onboard link becomes
// Workspace; on pages that pass `right` (Home, onboarding, workspace), the header's right side holds
// Sign in, or the account button with its menu (Workspace, Theme, Sign out). The session read costs
// the server no store read. Nothing here runs on the Desk: dispatchers sign in there.

import { el, icon } from "./wall/util.js";
import { themeControl } from "./theme.js";
import { clearOnboardStorage } from "./onboard/draft.js";

async function readSession() {
  try {
    const res = await fetch("/api/airline/session", { headers: { Accept: "application/json" }, cache: "no-store", signal: AbortSignal.timeout(8000) });
    return res.ok ? await res.json() : null;
  } catch {
    return null;
  }
}

export async function signOut() {
  try {
    await fetch("/api/airline/sign-out", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}", cache: "no-store" });
  } catch {
    /* the cookie expires on its own; this browser's copies go anyway */
  }
  clearOnboardStorage();
  location.assign("/");
}

function swapNav() {
  for (const a of document.querySelectorAll('.topnav a[data-feature="onboard"]')) {
    a.textContent = "Workspace";
    a.setAttribute("href", "/workspace");
  }
}

const signInLink = () => el("a", { id: "tn-signin", class: "tn-signin", href: "/signin" }, icon("i-user"), "Sign in");

// The menu: arrow keys move between its items, Esc closes it and gives focus back to the button,
// and focus or a click leaving it closes it. `items` are extra menu items a page adds before Sign out.
// Pages call initAccountNav again when they move between views; the menu it replaces takes its
// document listener with it.
let dropOutsideClick = null;
function accountMenu(session, items) {
  const button = el("button", { type: "button", id: "tn-account", class: "tn-account", "aria-haspopup": "menu", "aria-expanded": "false", "aria-controls": "tn-account-menu" },
    el("span", { class: "tn-account__code", "aria-hidden": "true", text: session.icao || "" }),
    el("span", { class: "tn-account__name", text: session.name || session.icao || "Your airline" }));
  const menu = el("div", { id: "tn-account-menu", class: "tn-menu", role: "menu", "aria-label": "Your airline account", hidden: true },
    el("a", { class: "tn-menu__item", role: "menuitem", href: "/workspace" }, icon("i-list"), "Workspace"),
    el("div", { class: "tn-menu__theme", role: "group", "aria-label": "Theme" }, themeControl()),
    items,
    el("button", { type: "button", class: "tn-menu__item", role: "menuitem", dataset: { act: "sign-out" } }, icon("i-log-out"), "Sign out"));
  const entries = () => [...menu.querySelectorAll('[role="menuitem"]')];
  const setOpen = (open, { focus = false } = {}) => {
    menu.hidden = !open;
    button.setAttribute("aria-expanded", String(open));
    if (open && focus) entries()[0]?.focus();
  };
  button.addEventListener("click", () => setOpen(menu.hidden));
  button.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true, { focus: true }); }
  });
  menu.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.preventDefault(); setOpen(false); button.focus(); return; }
    const list = entries();
    const at = list.indexOf(document.activeElement);
    if (at < 0 || !["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) return;
    e.preventDefault();
    const next = e.key === "Home" ? 0 : e.key === "End" ? list.length - 1 : (at + (e.key === "ArrowDown" ? 1 : -1) + list.length) % list.length;
    list[next].focus();
  });
  menu.addEventListener("click", (e) => { if (e.target.closest('[data-act="sign-out"]')) signOut(); });
  const wrap = el("div", { class: "tn-account-wrap" }, button, menu);
  wrap.addEventListener("focusout", (e) => { if (!wrap.contains(e.relatedTarget)) setOpen(false); });
  dropOutsideClick?.abort();
  dropOutsideClick = new AbortController();
  document.addEventListener("click", (e) => { if (!wrap.contains(e.target)) setOpen(false); }, { signal: dropOutsideClick.signal });
  return wrap;
}

export async function initAccountNav({ right = null, signin = true, items = [] } = {}) {
  const session = await readSession();
  if (!session) return { signedIn: false, icao: null, name: null };
  const signedIn = session.signed_in === true;
  if (signedIn) swapNav();
  if (right) {
    if (signedIn) right.replaceChildren(accountMenu(session, items));
    else right.replaceChildren(...(signin && session.accounts ? [signInLink()] : []));
  }
  return { signedIn, icao: signedIn ? session.icao : null, name: signedIn ? session.name : null };
}
