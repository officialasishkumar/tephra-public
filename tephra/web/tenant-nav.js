// The airline header on every page of a hosted airline's space /a/<ICAO>/ (SPEC-FINAL 5.2,
// RATIONALE 1 and 3): TEPHRA · [RFB Ring of Fire Charter ▾] · Map · Desk · Feeds · Settings ·
// (the page's own chips) · state chip · [Ana Ops ▾]. It is mounted into the page's existing header
// bar (the map, the Desk, the document page) or into hosted.html's, replacing the shared nav and the
// account button, so no page shell is forked. The state chip (SHADOW dashed, LIVE solid green,
// SUSPENDED red, Not started dotted) replaces the demo's clock; a red line under the header says
// a real alarm (a pause, a runtime problem, a suspension, the connection lost). Everything comes
// from GET /a/<ICAO>/api/tenant/header (TenantHeader), read again every minute; every string goes
// in through textContent.

import { el, icon } from "./wall/util.js";
import { infoButton, setInfo } from "./wall/info.js";
import { TENANT, PAGE_BASE, api, SHADOW_WORDS } from "./base.js";
import { call } from "./workspace/api.js";
import { themeControl } from "./theme.js";

export const SECTIONS = [
  { key: "map", name: "Map", path: "/" },
  { key: "desk", name: "Desk", path: "/desk" },
  { key: "feeds", name: "Feeds", path: "/feeds" },
  { key: "settings", name: "Settings", path: "/settings" },
];
export const ROLE_WORDS = { ops_manager: "Ops manager", dispatcher: "Dispatcher", viewer: "Viewer" };
export const STATE_WORDS = { setup: "Not started", shadow: "SHADOW", live: "LIVE", suspended: "SUSPENDED" };
// the state chip's (i) says what a draft becomes; the decision-support sentence is not page
// chrome (owner, 17 Oct 2026: "don't put this everywhere"): it lives in About and the sign-up tick
export const NOTHING_SENT = "Nothing is sent to aircraft.";
export const STATE_TOPIC = "the airline's state";
const REFRESH_MS = 60e3;
const RETRY_MS = 10e3;

const pad = (n) => String(n).padStart(2, "0");
const ms = (iso) => (iso ? Date.parse(iso) : NaN);
export function hhmmZ(t) {
  if (!Number.isFinite(t)) return "--:--Z";
  const d = new Date(t);
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}Z`;
}
const hhmmssZ = (t) => {
  const d = new Date(t);
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}Z`;
};
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export function dayMonth(t) {
  if (!Number.isFinite(t)) return "";
  const d = new Date(t);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
}
// "17 Oct, 13:40 UTC"
export const whenWords = (t) => (Number.isFinite(t) ? `${dayMonth(t)}, ${hhmmZ(t).replace("Z", " UTC")}` : "");
// An actor or stamp name is shown up to its "#" (S20: "Ana Ops#MB-1a2b3c4d5e" reads "Ana Ops").
export const personName = (by) => String(by || "").replace(/^(desk|visitor|operator):/, "").split("#")[0];
export const initials = (name) => String(name || "").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("") || "?";

// The state chip's words and shape for a TenantHeader at `nowMs` (the server's wall clock).
export function stateChip(h, nowMs) {
  const state = h.state;
  const running = state === "shadow" || state === "live";
  const stale = running && h.runtime && h.runtime.updating === false;
  const word = STATE_WORDS[state] || state.toUpperCase();
  let clock = "";
  let sub = "";
  if (state === "suspended") {
    sub = "since";
    clock = hhmmZ(ms(h.suspended?.at || h.state_since));
  } else if (running && !stale) {
    clock = hhmmZ(nowMs);
  }
  const lastTick = ms(h.runtime?.last_tick_wall_at);
  const staleWords = stale ? (Number.isFinite(lastTick) ? `not updating since ${hhmmZ(lastTick)}` : "not updating") : "";
  // the (i) beside the chip: what a running airline's drafts are, said once. Not started and
  // suspended say nothing more than the chip and the red line under the header already say.
  let info = null;
  if (state === "shadow") info = `TEPHRA runs on your real flights; every draft says ${SHADOW_WORDS}. ${NOTHING_SENT}`;
  if (state === "live") info = h.live ? `Switched to LIVE on ${whenWords(ms(h.live.at))} by ${personName(h.live.by)}. ${NOTHING_SENT}` : NOTHING_SENT;
  return {
    cls: `ah-state ah-state--${state === "setup" ? "setup" : state}${stale ? " ah-state--stale" : ""}`,
    word, sub, clock, stale: staleWords, info,
  };
}

// The red line under the header: real alarms only, in the server's facts.
export function alarmLines(h) {
  const out = [];
  if (h.suspended) {
    const del = ms(h.suspended.delete_after);
    out.push({
      kind: "suspended",
      lead: `TEPHRA's operators suspended ${h.name} on ${whenWords(ms(h.suspended.at))}.`,
      text: `Reason: “${h.suspended.reason}”. Runs are stopped and pushes are refused. Your settings, people, keys and record are kept${Number.isFinite(del) ? `. TEPHRA's operators can delete your data from ${dayMonth(del)} ${new Date(del).getUTCFullYear()}; nothing deletes it on its own` : ""}.`,
    });
  }
  if (h.paused) {
    const at = ms(h.paused.resumes_at);
    const resumes = `Resumes 00:00 Pacific${Number.isFinite(at) ? ` (${hhmmZ(at).replace("Z", " UTC")})` : ""}.`;
    out.push({
      kind: "paused",
      lead: h.paused.scope === "site"
        ? "Paused: the shared site's free daily database allowance is used."
        : `Paused: ${h.name}'s share of the site's free daily database allowance is used.`,
      text: resumes,
    });
  }
  if (h.runtime && h.runtime.problem && !h.suspended) out.push({ kind: "problem", lead: h.runtime.problem, text: "" });
  return out;
}

export function titleFor(h, sectionName) {
  const code = h?.icao || TENANT || "";
  return `${h?.state === "shadow" ? "SHADOW · " : ""}${sectionName} · ${code} · TEPHRA`;
}

// The same section of another airline's space ("/a/RFC/settings/people" for /a/RFB/settings/people).
export function sameSection(icao, pathname, section) {
  if (section === "doc") return `/a/${icao}/desk`;
  const rest = String(pathname).replace(/^\/a\/[A-Z]{3}/, "") || "/";
  return `/a/${icao}${rest}`;
}

// ------------------------------------------------------------------ the parts

function switcher(h, section) {
  const many = (h.memberships || []).length > 1;
  const code = el("span", { class: "ah-air__code", text: h.icao });
  const name = el("span", { class: "ah-air__name", text: h.name });
  if (!many) {
    return el("div", { class: "ah-airwrap" }, el("span", { class: "ah-air ah-air--one", title: `${h.name} (${h.icao})` }, code, name));
  }
  const button = el("button", { type: "button", id: "ah-air", class: "ah-air", "aria-haspopup": "menu", "aria-expanded": "false", "aria-controls": "ah-air-menu", "aria-label": `${h.name}, ${h.icao}. Switch airline` },
    code, name, icon("i-chevron-down"));
  const items = h.memberships.map((m) => {
    const here = m.icao === h.icao;
    return el("a", {
      class: "tn-menu__item ah-menu__air", role: "menuitemradio", "aria-checked": here ? "true" : "false",
      href: sameSection(m.icao, location.pathname, section),
    },
    el("span", { class: "ah-air__code", "aria-hidden": "true", text: m.icao }),
    el("span", {}, el("span", { text: m.name }), el("small", { text: ROLE_WORDS[m.role] || m.role })),
    el("span", { class: `ah-word ah-word--${m.state}`, text: STATE_WORDS[m.state] || m.state }),
    icon("i-check", "icon tick"));
  });
  const menu = el("div", { id: "ah-air-menu", class: "tn-menu ah-menu", role: "menu", "aria-label": "Your airlines", hidden: true },
    el("p", { class: "ah-menu__h", "aria-hidden": "true", text: "Your airlines" }), ...items);
  return menuWrap("ah-airwrap", button, menu);
}

function account(h, { theme }) {
  const you = h.you || {};
  const button = el("button", { type: "button", id: "ah-account", class: "tn-account", "aria-haspopup": "menu", "aria-expanded": "false", "aria-controls": "ah-account-menu", "aria-label": `${you.name}, ${ROLE_WORDS[you.role] || ""}. Account menu` },
    el("span", { class: "tn-account__code", "aria-hidden": "true", text: initials(you.name) }),
    el("span", { class: "tn-account__name", text: you.name || "" }),
    icon("i-chevron-down"));
  const menu = el("div", { id: "ah-account-menu", class: "tn-menu", role: "menu", "aria-label": "Your account", hidden: true },
    el("div", { class: "ah-who" }, el("b", { text: you.name || "" }), el("span", { text: `${ROLE_WORDS[you.role] || ""} · ${h.name}` })),
    el("a", { class: "tn-menu__item", role: "menuitem", href: "/workspace" }, icon("i-list"), "Your workspace"),
    theme ? el("div", { class: "tn-menu__theme", role: "group", "aria-label": "Theme" }, themeControl()) : null,
    el("button", { type: "button", class: "tn-menu__item", role: "menuitem", dataset: { act: "sign-out-all" } }, icon("i-log-out"), "Sign out on every device"));
  menu.addEventListener("click", (e) => { if (e.target.closest('[data-act="sign-out-all"]')) signOutEverywhere(); });
  return menuWrap("tn-account-wrap", button, menu);
}

// A button and its menu: arrows move, Esc closes and gives focus back, a click or focus outside closes.
function menuWrap(cls, button, menu) {
  const entries = () => [...menu.querySelectorAll('[role="menuitem"], [role="menuitemradio"]')];
  const setOpen = (open, { focus = false } = {}) => {
    menu.hidden = !open;
    button.setAttribute("aria-expanded", String(open));
    if (open && focus) (menu.querySelector('[aria-checked="true"]') || entries()[0])?.focus();
  };
  // Enter or Space opens with focus on the first entry (a keyboard click has detail 0), as the
  // arrows do; a pointer click opens and leaves focus on the button
  button.addEventListener("click", (e) => setOpen(menu.hidden, { focus: e.detail === 0 }));
  button.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true, { focus: true }); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setOpen(true); entries().at(-1)?.focus(); }
    else if (e.key === "Escape" && !menu.hidden) { e.preventDefault(); setOpen(false); }
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
  const wrap = el("div", { class: cls }, button, menu);
  wrap.addEventListener("focusout", (e) => { if (!wrap.contains(e.relatedTarget)) setOpen(false); });
  document.addEventListener("click", (e) => { if (!wrap.isConnected) return; if (!wrap.contains(e.target)) setOpen(false); }, { signal: outside.signal });
  return wrap;
}

async function signOutEverywhere() {
  await call("/api/airline/sign-out", { method: "POST", body: {} });
  location.assign("/signin");
}

function chipNode(c) {
  return el("span", { id: "ah-state", class: c.cls },
    el("i", { "aria-hidden": "true" }),
    el("b", { text: c.word }),
    c.stale ? el("span", { class: "ah-state__stale", text: ` · ${c.stale}` }) : null,
    c.sub ? el("span", { class: "ah-state__sub", text: c.sub }) : null,
    c.clock ? el("span", { class: "ah-state__clock", text: c.clock }) : null);
}

function nav(h, section) {
  const label = h ? `${h.name} on TEPHRA` : "This airline on TEPHRA";
  return el("nav", { class: "topnav ah-nav", "aria-label": label },
    ...SECTIONS.map((s) => el("a", { href: PAGE_BASE + s.path, "aria-current": s.key === section ? "page" : null, text: s.name })));
}

export function alarmNode(lines) {
  return lines.map((l) => el("div", { class: `banner ah-alarm__line ah-alarm__line--${l.kind}` },
    icon(l.kind === "paused" ? "st-caution" : "i-alert-serious"),
    el("p", {}, el("b", { text: l.lead }), l.text ? [" ", el("span", { text: l.text })] : null)));
}

// ------------------------------------------------------------------ the mount

const S = { h: null, offset: 0, lostAt: null, error: null, subs: new Set(), parts: null, opts: null, started: false };

export const tenantHeader = () => S.h;
// fn(header, { error }) on every read; called at once when a header is already in.
export function onTenantHeader(fn) {
  S.subs.add(fn);
  if (S.h || S.error) fn(S.h, { error: S.error });
}
export const serverNow = () => Date.now() + S.offset;

// `bar`: the header element to take over (a .tn-bar or the document page's .docbar). `section`:
// map | desk | feeds | settings | doc. `chips`: page nodes kept between the nav and the state chip
// (the Desk's assistant chip, Ask and connection pill). `hide`: nodes the space does not use
// (the demo's mode badge, area picker, How it works and clock). `theme`: offer the theme control.
export function mountTenantNav({ bar, section, chips = [], hide = [], theme = true }) {
  if (!TENANT || S.parts) return;
  // the space's stylesheets (and the (i)'s, which the document page lacks), added here so the
  // demo's page shells stay as they are
  for (const css of ["/static/info.css", "/static/tenant.css"]) {
    if (!document.querySelector(`link[href="${css}"]`)) document.head.append(el("link", { rel: "stylesheet", href: css }));
  }
  document.body.classList.add("is-tenant");
  // the shells' descriptions speak of the demo (replay, fictional airline): not of this space
  const about = `TEPHRA for ${TENANT}: a private airline space, behind sign-in.`;
  for (const m of document.querySelectorAll('meta[name="description"], meta[property="og:description"]')) m.setAttribute("content", about);
  bar.classList.add("ah");
  for (const n of hide) if (n) n.hidden = true;
  for (const n of bar.querySelectorAll(":scope > .topnav, :scope > .account, :scope > .tn-right")) n.remove();
  const home = bar.querySelector(":scope > .tn-home");
  const air = el("div", { class: "ah-airwrap" }, el("span", { class: "ah-air ah-air--one" }, el("span", { class: "ah-air__code", text: TENANT })));
  const links = nav(null, section);
  const spacer = el("span", { class: "tn-spacer ah-spacer" });
  const chip = el("span", { id: "ah-state", class: "ah-state ah-state--loading", text: "…" });
  const stateInfo = infoButton({ topic: STATE_TOPIC, text: NOTHING_SENT });
  stateInfo.hidden = true;
  const who = el("div", { class: "tn-account-wrap" });
  if (home) home.after(air, links, spacer); else bar.prepend(air, links, spacer);
  bar.append(...chips.filter(Boolean), el("span", { class: "ah-statewrap" }, chip, stateInfo), who);
  const alarm = el("div", { id: "ah-alarm", class: "ah-alarm", role: "alert", hidden: true });
  bar.after(alarm);
  S.parts = { bar, air, links, chip, stateInfo, who, alarm, section };
  S.opts = { theme };
  load();
  setInterval(() => { if (S.h) drawChip(); }, 15e3);
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible" && S.h) load(); });
}

let timer = 0;
async function load() {
  window.clearTimeout(timer);
  const res = await call(api("/tenant/header"));
  if (res.ok && res.data && res.data.icao) {
    S.h = res.data;
    S.offset = ms(res.data.wall_now) - Date.now();
    S.lostAt = null;
    S.error = null;
    draw();
    timer = window.setTimeout(load, REFRESH_MS);
  } else if (res.status === 401) {
    location.assign(`/signin?next=${encodeURIComponent(location.pathname)}`);
    return;
  } else if (res.status === 0) {
    S.lostAt = S.lostAt || Date.now() + S.offset;
    S.error = "offline";
    drawAlarm();
    timer = window.setTimeout(load, RETRY_MS);
  } else {
    S.error = res.status === 404 ? "no_such_airline" : `http_${res.status}`;
    drawGone();
  }
  for (const fn of S.subs) fn(S.h, { error: S.error });
}

// Read the header again now (after a change the page made, such as a stop or a policy save).
export const reloadTenantHeader = () => load();

// The switcher, the nav and the account menu are drawn again only when what they show changed.
let outside = new AbortController();
let drawnKey = "";
function draw() {
  const { air, links, who, section } = S.parts;
  const h = S.h;
  const key = JSON.stringify([h.icao, h.name, h.you, h.memberships]);
  if (key !== drawnKey) {
    drawnKey = key;
    outside.abort();
    outside = new AbortController();
    air.replaceWith(S.parts.air = switcher(h, section));
    links.replaceWith(S.parts.links = nav(h, section));
    who.replaceWith(S.parts.who = account(h, S.opts));
  }
  drawChip();
  drawAlarm();
}

// The chip is drawn again every 15 s; its (i) stays (an open one keeps its place) and only its
// words change.
function drawChip() {
  const c = stateChip(S.h, serverNow());
  const node = chipNode(c);
  S.parts.chip.replaceWith(node);
  S.parts.chip = node;
  if (c.info) setInfo(S.parts.stateInfo, c.info);
  else S.parts.stateInfo.close?.();
  S.parts.stateInfo.hidden = !c.info;
}

function drawAlarm() {
  const lines = S.h ? alarmLines(S.h) : [];
  if (S.lostAt) lines.unshift({ kind: "lost", lead: `Not connected to TEPHRA since ${hhmmssZ(S.lostAt)}.`, text: "What you see is as of then. Trying again every 10 s." });
  S.parts.alarm.replaceChildren(...alarmNode(lines));
  S.parts.alarm.hidden = !lines.length;
  document.body.classList.toggle("has-alarm", lines.length > 0);
}

function drawGone() {
  const node = el("span", { id: "ah-state", class: "ah-state ah-state--setup" }, el("i", { "aria-hidden": "true" }), el("b", { text: "No access" }));
  S.parts.chip.replaceWith(node);
  S.parts.chip = node;
  S.parts.stateInfo.hidden = true;
  S.parts.alarm.replaceChildren(el("div", { class: "banner ah-alarm__line" }, icon("i-alert-serious"),
    el("p", {}, el("b", { text: S.error === "no_such_airline" ? `There is no airline ${TENANT} here, or you are not one of its people.` : "TEPHRA could not open this airline's space." }),
      " ", el("a", { href: "/workspace", text: "Your workspace ›" }))));
  S.parts.alarm.hidden = false;
}

// The product pages' footer inside the space: who sees it (the decision-support sentence left the
// footer: owner, 17 Oct 2026, "don't put this everywhere").
export function footerWords(h) {
  return `Private to ${h ? h.name : "this airline"} and TEPHRA's operators.`;
}
