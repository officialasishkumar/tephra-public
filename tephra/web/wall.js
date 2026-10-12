// TEPHRA Wall entry point (docs/UI-REDESIGN.md, "The Story"; docs/UI-DESIGN.md). Loads GET /api/wall,
// follows GET /api/events, keeps the store and the view state, and renders the story column
// (wall/story.js), the map (wall/map.js), the time bar and the Details drawer (wall/details.js).
// Feed and model text only ever reaches the page through textContent.

import { $, el, ms, prefs, reducedMotion, inlineSprite, icon } from "./wall/util.js";
import { derive, actionWords, deciderName, LEVEL_MAX, levelFromFrac, regionOfVent, sortSituations } from "./wall/derive.js";
import { WallMap, readTokens, SAT } from "./wall/map.js";
import {
  renderChrome, renderClock, mapPills, renderTimeline, sourcesDialog, policyDialog, timelineTarget, setFailureCounter,
} from "./wall/panels.js";
import { helpContent, aboutContent } from "./wall/controls.js";
import { ext, loadExt, ingest, noteTrace, satScale, failureCount } from "./wall/ext.js";
import { renderStory, coverageNote } from "./wall/story.js";
import { renderDetails, sectionOf, PANELS } from "./wall/details.js";

const STREAM_TIMEOUT_MS = 45e3;
// A Wall hidden this long gives its stream (a Cloud Run request slot) back until it is shown.
const HIDDEN_PAUSE_MS = 5 * 60e3;
const TRACE_KEEP = 200;
const SAT_CYCLE = ["off", "ir", "vis", "airmass"];
const DEFAULT_LAYERS = { tephra: true, rose: true, aircraft: true, paths: true, routes: true, acLabels: true, context: false, navaids: false, terrain: false, reroutes: false, satboxes: true };
const DETAILS_KEY = "tephra.wall.details";

// ------------------------------------------------------------------ state

// routeLines: "WIII-WSSS" -> the route line fetched for a picked flight that is not in or heading
// into an area (null while it loads or when the server has no line for it).
const store = { state: null, snapshot: null, advisories: [], trace: [], feeds: [], routeLines: new Map() };
// Human decisions composed on the Wall from advisory events: the backend's trace has no
// DESK step yet, and the trace must show the human deciding (7.9).
const localTrace = [];
const params = new URLSearchParams(location.search);
// Recording (?present=1) and automated screenshots (?shots=1) keep Details closed (R8.1).
const PRESENT = params.get("present") === "1";
const SHOTS = params.get("shots") === "1";
const savedLayers = prefs.get("layers", {});
const ui = {
  selected: null,
  autoSelect: true,
  region: null,
  regionChosen: false,
  // layersV2: the redesign's defaults (FIR lines and all reroutes off) replace older saved choices once
  layers: { ...DEFAULT_LAYERS, ...(prefs.get("layersV2", false) ? savedLayers : { ...savedLayers, context: false, reroutes: false }) },
  sat: SAT_CYCLE.includes(prefs.get("sat", "off")) ? prefs.get("sat", "off") : "off",
  so2: !!prefs.get("so2", false),
  btd: !!prefs.get("btd", false),
  steps: prefs.get("steps", "now"),
  level: { min: 0, max: LEVEL_MAX },
  d3: false,
  compare: false,
  traceScope: "volcano",
  readOpen: false,
  historyOpen: false,
  // the map key pinned under the Details drawer (601-1599 px) starts folded to one bar
  keyOpen: (() => { try { return sessionStorage.getItem("tephra.wall.key") === "open"; } catch { return false; } })(),
  traceFilter: "all",
  vlistOpen: false,
  layersMore: false,
  rail: "brief",
  details: { open: false, sec: null, vid: null, from: null, opener: null },
  shortcuts: prefs.get("shortcuts", true),
  freshTrace: new Set(),
  freshDis: new Set(),
  freshDecisions: new Set(),
  present: PRESENT,
  selFlight: null, // { hex, proxy } of the aircraft picked on the map or in the flights list
  tlCurrent: null, // title of the timeline event last chosen (R7)
};
const conn = { lostAt: null, source: null, watchdog: null, lastEventAt: 0, loaded: false, everLost: false, hiddenTimer: null, paused: false, lastTick: null };
const extra = { error: null, basemap: null, mapError: null };
const clock = { base: NaN, at: 0 };
const seenDis = new Set();
let D = null;
let map = null;
let dialogKind = null;
let dialogOpener = null;
let lastSel = null;
setFailureCounter(failureCount);

const now = () => (Number.isFinite(clock.base) ? clock.base + (performance.now() - clock.at) : NaN);
function setClock(iso) {
  const t = ms(iso);
  if (Number.isFinite(t)) { clock.base = t; clock.at = performance.now(); }
}

function announce(text) {
  const box = $("announce");
  box.textContent = "";
  setTimeout(() => { box.textContent = text; }, 50);
}

const phone = () => window.innerWidth <= 600;
const wide = () => window.innerWidth >= 1600;

// ------------------------------------------------------------------ loading and the stream

let extTimer = 0;
function reloadExtSoon() {
  // The Wall's draft and recovery numbers follow the same data as the Desk's (R2.7): reload on a
  // new tick, debounced; the 60 s poll stays as a backstop.
  clearTimeout(extTimer);
  extTimer = setTimeout(() => loadExt(scheduleRender), 2000);
}

async function load() {
  try {
    const res = await fetch("/api/wall", { headers: { Accept: "application/json" }, cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    store.state = data.state;
    store.snapshot = data.snapshot;
    store.advisories = data.advisories || [];
    store.trace = mergeTrace(data.trace || []);
    store.feeds = data.state.feeds || [];
    conn.lastTick = data.state.last_tick || null;
    setClock(data.state.now);
    extra.error = null;
    for (const s of store.snapshot.situations || []) for (const d of s.discrepancies) seenDis.add(d.id);
    if (!conn.loaded) firstRegion();
    conn.loaded = true;
    renderNow();
    if (!conn.source) openStream();
    if (!ext.started) { ext.started = true; loadExt(scheduleRender); setInterval(() => loadExt(scheduleRender), 60e3); }
  } catch (err) {
    loadRetry(err?.message || "no answer");
  }
}

let retryIn = 0;
function loadRetry(status) {
  retryIn = 5;
  const tick = () => {
    if (conn.loaded && !extra.error) return;
    extra.error = `Could not load the Wall data: ${status}. Trying again in ${retryIn} s.`;
    renderNow();
    if (retryIn-- <= 0) { load(); return; }
    setTimeout(tick, 1000);
  };
  tick();
}

// First load only (R2.1 step 5, R2.2): the server's region, unless it is empty while ash exists
// elsewhere; then the region of the top-priority volcano. In REPLAY, the case's own volcano.
function firstRegion() {
  const tmp = derive(store, { ...ui, region: null, selected: null }, now());
  const replayIds = store.state.mode === "REPLAY" ? store.state.replay?.volcano_ids || [] : [];
  const caseSit = replayIds.map((id) => tmp.sits.find((s) => s.volcano_id === id)).find(Boolean);
  const pick = caseSit || sortSituations(tmp.sits)[0] || null;
  const serverRegion = store.state.region?.key || null;
  const inServer = serverRegion ? tmp.regionCounts[serverRegion] > 0 : false;
  if (caseSit) {
    ui.selected = caseSit.volcano_id;
    ui.region = regionOfVent(store.state, tmp.vents.get(caseSit.volcano_id));
  } else if (serverRegion && !inServer && pick) {
    ui.region = regionOfVent(store.state, tmp.vents.get(pick.volcano_id));
  } else {
    ui.region = serverRegion;
  }
}

function openStream() {
  const es = new EventSource("/api/events");
  conn.source = es;
  const on = (name, fn) => es.addEventListener(name, (ev) => {
    touch();
    let data;
    try { data = JSON.parse(ev.data); } catch { return; }
    fn(data);
    scheduleRender();
  });
  es.onopen = () => {
    touch();
    if (conn.lostAt) {
      conn.lostAt = null;
      announce("Live updates restored.");
      load();
    }
  };
  es.onerror = () => { if (es.readyState !== EventSource.OPEN) streamLost(); };
  on("state", (s) => {
    store.state = s;
    if (s.feeds) store.feeds = s.feeds;
    setClock(s.now);
    if (store.snapshot && Array.isArray(s.active_volcano_ids)) {
      const active = new Set(s.active_volcano_ids);
      store.snapshot.situations = store.snapshot.situations.filter((x) => active.has(x.volcano_id));
    }
    if (s.last_tick && s.last_tick !== conn.lastTick) { conn.lastTick = s.last_tick; reloadExtSoon(); }
  });
  on("heartbeat", (h) => { if (h.now) setClock(h.now); });
  for (const name of ["volcanoes", "official", "cones", "exposures", "aircraft", "reroutes", "routes"]) on(name, (fc) => { if (store.snapshot) store.snapshot[name] = fc; });
  for (const name of ["notice", "recovery", "budget"]) on(name, (d) => ingest(name, d));
  on("satellite", (r) => {
    if (!store.snapshot) return;
    const list = store.snapshot.satellite || (store.snapshot.satellite = []);
    const i = list.findIndex((x) => x.volcano_id === r.volcano_id);
    if (i >= 0) list[i] = r; else list.push(r);
  });
  on("duty", (run) => {
    if (!store.snapshot) return;
    store.snapshot.duty = run;
  });
  on("overlays", (o) => { if (store.snapshot) store.snapshot.overlays = o; });
  // crew reports of ash: the whole picture each time (MODULES.md 8.4)
  on("crew", (pic) => { if (store.snapshot) store.snapshot.crew = pic; });
  on("situation", (card) => {
    if (!store.snapshot) return;
    const list = store.snapshot.situations;
    const i = list.findIndex((s) => s.volcano_id === card.volcano_id);
    if (i >= 0) list[i] = card; else list.push(card);
    for (const d of card.discrepancies) {
      if (seenDis.has(d.id)) continue;
      seenDis.add(d.id);
      if (d.severity === "INFO") continue;
      ui.freshDis.add(d.id);
      setTimeout(() => { ui.freshDis.delete(d.id); scheduleRender(); }, 1200);
    }
  });
  on("trace", (t) => {
    store.trace.push(t);
    noteTrace(t);
    setTimeout(scheduleRender, 6200);
    if (store.trace.length > TRACE_KEEP) store.trace.splice(0, store.trace.length - TRACE_KEEP);
    ui.freshTrace.add(t.id);
    setTimeout(() => ui.freshTrace.delete(t.id), 800);
  });
  on("advisory", (a) => {
    const i = store.advisories.findIndex((x) => x.id === a.id);
    const prev = i >= 0 ? store.advisories[i] : null;
    if (i >= 0) store.advisories[i] = a; else store.advisories.unshift(a);
    const decided = ["APPROVED", "EDITED", "REJECTED"].includes(a.status);
    if (decided && prev?.status !== a.status) {
      ui.freshDecisions.add(a.id);
      setTimeout(() => { ui.freshDecisions.delete(a.id); scheduleRender(); }, 1600);
      const who = deciderName(a) || "A dispatcher";
      humanTrace(a);
      announce(a.status === "REJECTED" ? `${who} rejected the advisory for ${a.proxy_flight}` : `${who} approved ${actionWords(a)} for ${a.proxy_flight}`);
    }
  });
}

function mergeTrace(server) {
  const ids = new Set(server.map((t) => t.id));
  return server.concat(localTrace.filter((t) => !ids.has(t.id))).sort((a, b) => ms(a.at) - ms(b.at)).slice(-TRACE_KEEP);
}

function humanTrace(a) {
  const who = deciderName(a) || "A dispatcher";
  const verb = a.status === "REJECTED" ? "rejected" : a.status === "EDITED" ? "approved with edits" : "approved";
  const t = {
    id: `desk-${a.id}-${a.status}`, at: a.decided_at || a.updated_at, stage: "DESK", actor: "human", level: "info",
    volcano_id: a.volcano_id, flight_id: a.flight_id, message: `${who} ${verb} ${a.proxy_flight}: ${actionWords(a)}`,
  };
  localTrace.push(t);
  store.trace = mergeTrace(store.trace);
  ui.freshTrace.add(t.id);
  setTimeout(() => ui.freshTrace.delete(t.id), 800);
}

function touch() {
  conn.lastEventAt = performance.now();
  clearTimeout(conn.watchdog);
  conn.watchdog = setTimeout(streamLost, STREAM_TIMEOUT_MS);
}

function streamLost() {
  if (conn.lostAt) return;
  conn.lostAt = Number.isFinite(now()) ? now() : Date.now();
  // EventSource retries by itself after an error; a silent stall needs a fresh connection.
  if (conn.source && conn.source.readyState === EventSource.OPEN) {
    conn.source.close();
    conn.source = null;
    setTimeout(() => { if (!conn.source && !conn.paused) openStream(); }, 3000);
  }
  renderNow();
}

// Hidden for HIDDEN_PAUSE_MS: close the stream quietly (no lost banner). Shown again: resync
// from /api/wall, which opens a new stream, as the reconnect path does. A visible Wall never
// pauses: it is an unattended display.
function pauseHiddenStream() {
  conn.hiddenTimer = null;
  if (!document.hidden || !conn.source) return;
  conn.paused = true;
  clearTimeout(conn.watchdog);
  conn.source.close();
  conn.source = null;
}

document.addEventListener("visibilitychange", () => {
  clearTimeout(conn.hiddenTimer);
  conn.hiddenTimer = null;
  if (document.hidden) {
    conn.hiddenTimer = setTimeout(pauseHiddenStream, HIDDEN_PAUSE_MS);
    return;
  }
  if (!conn.paused) return;
  conn.paused = false;
  load();
});

// ------------------------------------------------------------------ rendering

let pending = 0;
// The picked flight's usual route, when the server's route layer does not already draw it. The
// line depends only on the two airports, so it is fetched once per pair (and cached by HTTP).
function fetchRouteLine(d) {
  const key = d.selRoute;
  if (!key || store.routeLines.has(key) || d.routes.some((f) => f.id === key)) return;
  store.routeLines.set(key, null);
  const [origin, dest] = key.split("-");
  fetch(`/api/routes/${encodeURIComponent(origin)}/${encodeURIComponent(dest)}`)
    .then((r) => (r.ok ? r.json() : null))
    .then((fc) => { if (fc?.features) { store.routeLines.set(key, fc); scheduleRender(); } })
    .catch(() => {});
}

function scheduleRender() {
  if (pending) return;
  pending = setTimeout(() => { pending = 0; renderNow(); }, 40);
}

// Re-render without losing the viewer's place: focus (by data-focus), the story column's and the
// drawer's scroll.
function withFocusKept(fn) {
  const active = document.activeElement;
  const key = active?.dataset?.focus;
  const body = $("details-body");
  const story = $("story");
  const top = body.scrollTop, stop = story.scrollTop;
  fn();
  body.scrollTop = top;
  story.scrollTop = stop;
  if (key && (!document.activeElement || document.activeElement === document.body || !document.contains(active))) {
    const next = document.querySelector(`[data-focus="${CSS.escape(key)}"]`);
    next?.focus({ preventScroll: true });
  }
}

function storyNotes() {
  const notes = [];
  if (extra.basemap) notes.push({ text: extra.basemap });
  // The coverage note when the story's flight line has not already said it (R5.7).
  const cov = D ? coverageNote(D, store) : null;
  if (cov && ui.layers.aircraft && (D.sit?.exposed_count || 0) > 0) notes.push({ text: cov });
  return notes;
}

function renderNow() {
  if (!store.state) {
    renderShell();
    return;
  }
  D = derive(store, ui, now());
  fetchRouteLine(D);
  let reframe = false;
  if (D.selected !== lastSel) {
    reframe = lastSel !== null || !map?.framedOnce;
    lastSel = D.selected;
    ui.selected = D.selected ?? ui.selected;
  }
  withFocusKept(() => {
    renderChrome(D, store, ui);
    renderClock(D, conn);
    renderStory(D, store, ui, { conn, extra, announce, notes: storyNotes() });
    renderPills();
    renderTimeline(D, store, ui, conn);
    renderTools();
    renderCtx();
    renderDetails(D, store, ui, conn, { reroutes: () => store.snapshot?.reroutes?.features || [] });
    if (dialogKind === "about") { /* static; nothing to refresh */ }
  });
  document.body.classList.toggle("is-stale", !!conn.lostAt);
  document.body.classList.toggle("is-3d", ui.d3);
  document.body.classList.toggle("history-open", ui.historyOpen);
  // The map's credit and controls sit above an open History panel, whatever its height.
  if (ui.historyOpen) requestAnimationFrame(() => {
    const h = document.querySelector(".tl__history")?.offsetHeight;
    if (h) document.body.style.setProperty("--history-h", `${h}px`);
  });
  document.body.classList.toggle("present", ui.present);
  $("stale-chip").hidden = !conn.lostAt;
  if (map) {
    // Reroutes only for the picked flight, unless Map layers turns them all on (R6.1).
    const rr = store.snapshot?.reroutes;
    const pickedKey = ui.selFlight ? D.aircraft.find((f) => f.properties.hex === ui.selFlight.hex) : null;
    const reroutes = ui.layers.reroutes || !rr ? rr : { ...rr, features: (rr.features || []).filter((f) => pickedKey && (f.properties.flight_id === `${pickedKey.properties.hex}:${pickedKey.properties.volcano_id}` || f.properties.proxy_flight === pickedKey.properties.proxy_flight)) };
    map.setExt({ reroutes, satellite: store.snapshot?.satellite, frames: [...(store.snapshot?.overlays?.frames || []), ...(store.snapshot?.situations || []).flatMap((x) => x.frames || [])] });
    map.update(D);
    if (reframe && D.sit) map.frame({ animate: !reducedMotion() && map.framedOnce });
    else if (reframe && !D.sit && D.area) map.flyRegion(D.area);
  }
}

// Before the first /api/wall answer: the Connecting story, no numbers (R5.4).
function renderShell() {
  renderStory(null, store, ui, { conn, extra, announce });
  renderTimeline(null, store, ui, conn);
  renderTools();
}

function renderPills() {
  const pills = mapPills(D, ui, extra);
  const box = $("map-notes");
  // The satellite caption is its own pill (#ctx-label) and is never folded (R6.4, G13).
  const ctx = map ? map.satLabel().length : 0;
  const room = Math.max(1, 3 - ctx);
  let shown = pills;
  if (pills.length > room) shown = [...pills.slice(0, room - 1), { tone: "info", text: `+${pills.length - room + 1} more map settings`, action: "details-open", sec: "layers", actionText: "Show" }];
  const key = shown.map((p) => `${p.tone}|${p.text}`).join("§");
  if (box.dataset.key === key) return;
  box.dataset.key = key;
  box.replaceChildren(...shown.map((n) => el("p", { class: `map-pill map-pill--${n.tone || "info"}` },
    n.tone === "caution" ? icon("st-caution", "st", "var(--c-caution)") : icon("st-info", "st", "var(--c-info)"),
    el("span", { text: n.text }),
    n.action ? el("button", { type: "button", class: "link-btn", dataset: { act: n.action, sec: n.sec || null, focus: `pill-${n.action}` }, text: n.actionText }) : null)));
}

function renderTools() {
  const lb = document.querySelector('#tools [data-tool="layers"]');
  if (lb) lb.setAttribute("aria-expanded", ui.details.open && ui.details.sec === "layers" ? "true" : "false");
  $("compare-labels").hidden = !ui.compare;
}

// "CONTEXT ONLY" pills for satellite, SO2 and BTD layers (5.6, R6.4), always on screen while shown,
// each with a ✕ that turns the layer off and its scale where NASA GIBS publishes one.
function renderCtx() {
  const box = $("ctx-label");
  const lines = map ? map.satLabel() : [];
  box.hidden = !lines.length;
  const scaleOf = (t) => (t.includes("SO2 (TROPOMI") ? "so2" : ui.sat === "ir" && t.includes(SAT.ir.title) ? "ir" : null);
  const offOf = (t) => (t.includes("SO2 (TROPOMI") ? "so2" : t.includes("BTD") ? "btd" : "sat");
  // One pill per layer (review 1, item 12): "CONTEXT ONLY", the caption and the scale wrap together
  // in one box, with the ✕ beside the caption, never on a row of its own.
  box.replaceChildren(...lines.map((t) => {
    const off = offOf(t);
    const caption = t.replace(/^CONTEXT ONLY\s*/, "").replace(/^[\s·:-]+/, "");
    const key = scaleOf(t);
    return el("div", { class: "ctx-label__line ctx-pill map-pill" },
      el("p", { class: "ctx-pill__text" }, el("strong", { text: "CONTEXT ONLY" }), el("span", { text: ` ${caption}` })),
      el("button", { type: "button", class: "icon-btn ctx-label__off", "aria-label": `Turn off: ${off === "sat" ? "satellite picture" : off.toUpperCase()}`, dataset: { act: "ctx-off", layer: off, focus: `ctx-off-${off}` } }, icon("i-x")),
      key ? satScale(key, renderCtx) : null);
  }));
}

// ------------------------------------------------------------------ actions

function select(vid, { frame = true } = {}) {
  ui.autoSelect = false;
  ui.selected = vid;
  // The area follows the volcano (R2.1 step 3, G9).
  ui.region = regionOfVent(store.state, D?.vents.get(vid));
  lastSel = vid;
  renderNow();
  if (frame) map?.frame({ animate: true });
}

function stepVolcano(dir) {
  if (!D?.sits.length) return;
  const i = Math.max(0, D.sits.findIndex((s) => s.volcano_id === D.selected));
  const next = D.sits[(i + dir + D.sits.length) % D.sits.length];
  select(next.volcano_id);
}

// Choosing an area only sets it (R2.1 step 4): the first volcano in it is picked by derive() on
// every render, also when volcanoes arrive later.
function chooseRegion(key) {
  const k = key === "all" ? null : key;
  if (k && !(store.state?.regions || []).some((x) => x.key === k)) return;
  ui.region = k;
  ui.autoSelect = false;
  closeAreaMenu(false);
  renderNow();
  if (D?.regionEmpty && D.area) map?.flyRegion(D.area);
}

function setLayer(key, on) {
  if (key === "so2") ui.so2 = on;
  else if (key === "btd") ui.btd = on;
  else if (key in ui.layers) ui.layers[key] = on;
  prefs.set("layers", ui.layers);
  prefs.set("layersV2", true);
  prefs.set("so2", ui.so2);
  prefs.set("btd", ui.btd);
  map?.applyLayers();
  renderNow();
}

function setSat(kind) {
  ui.sat = kind;
  prefs.set("sat", kind);
  renderNow();
}

function setSteps(k) {
  ui.steps = k;
  prefs.set("steps", k);
  renderNow();
}

function toggle3d(force) {
  const on = force ?? !ui.d3;
  if (on === ui.d3 || !map) return;
  if (on && ui.compare) toggleCompare(false);
  if (on) ui.historyOpen = false;
  ui.d3 = on;
  map.set3d(on);
  renderNow();
}

async function toggleCompare(force) {
  const on = force ?? !ui.compare;
  if (on === ui.compare || !map) return;
  if (on && phone()) return; // not offered under 600 px (R4.4)
  if (on && ui.d3) toggle3d(false);
  ui.compare = on;
  renderNow();
  const ok = await map.setCompare(on, $("map-wrap"));
  if (on && !ok) { ui.compare = false; renderNow(); return; }
  if (on) wireCompareHandle();
}

function wireCompareHandle() {
  const handle = $("map-wrap").querySelector(".compare-swiper-vertical");
  if (!handle || handle.dataset.wired) return;
  handle.dataset.wired = "1";
  handle.tabIndex = 0;
  handle.setAttribute("role", "slider");
  handle.setAttribute("aria-label", "Compare: drag or use arrow keys. Left side A, official reports only; right side B, with TEPHRA's estimate.");
  handle.setAttribute("aria-valuemin", "0");
  handle.setAttribute("aria-valuemax", "100");
  handle.setAttribute("aria-keyshortcuts", "S");
  handle.append(el("span", { class: "compare-handle" }, icon("i-swipe")));
  let pct = 50;
  const set = (p) => {
    pct = Math.max(0, Math.min(100, p));
    map.compareSlide(pct);
    handle.setAttribute("aria-valuenow", String(Math.round(pct)));
  };
  set(50);
  map.compare.on("slideend", (e) => {
    const w = $("map-wrap").getBoundingClientRect().width;
    if (w) { pct = (e.currentPosition / w) * 100; handle.setAttribute("aria-valuenow", String(Math.round(pct))); }
  });
  handle.addEventListener("keydown", (e) => {
    const k = { ArrowLeft: -5, ArrowRight: 5, ArrowDown: -5, ArrowUp: 5 }[e.key];
    if (k) { e.preventDefault(); set(pct + k); }
    else if (e.key === "Home") { e.preventDefault(); set(0); }
    else if (e.key === "End") { e.preventDefault(); set(100); }
  });
}

// Presentation layout for recording (key P or ?present=1): Details stays closed, so the story
// and the map get the frame (14).
function setPresent(on) {
  ui.present = on;
  if (on) closeDetails(false);
  renderNow();
  requestAnimationFrame(() => map?.frame({ animate: true }));
}

function levelPreset(k) {
  if (k === "all") ui.level = { min: 0, max: LEVEL_MAX };
  else if (k === "low") ui.level = { min: 0, max: 18000 };
  else if (k === "high") ui.level = { min: 18000, max: LEVEL_MAX };
  else if (k === "hazard") {
    const cone = D?.sit ? D.coneOf(D.sit.volcano_id)?.properties : null;
    if (cone) ui.level = { min: Math.max(0, cone.base_ft), max: Math.min(LEVEL_MAX, cone.top_ft) };
  }
  renderNow();
}

// ------------------------------------------------------------------ the Details drawer (R8)

function saveDetails() {
  try { sessionStorage.setItem(DETAILS_KEY, ui.details.open ? ui.details.sec || "index" : "closed"); } catch { /* storage blocked */ }
}

function placeDetails() {
  const box = $("details");
  const sheet = $("details-sheet");
  const open = ui.details.open;
  document.body.classList.toggle("details-open", open);
  // phone: a full-screen sheet below the sticky header (R8.1)
  if (phone()) {
    document.documentElement.style.setProperty("--sheet-top", `${Math.max(0, document.querySelector(".cmdbar").getBoundingClientRect().bottom)}px`);
    if (open && box.parentElement !== sheet) sheet.append(box);
    if (open && !sheet.open) sheet.showModal();
    if (!open && sheet.open) sheet.close();
  } else {
    if (box.parentElement !== $("main")) $("main").append(box);
    if (sheet.open) sheet.close();
  }
  if (!open && box.parentElement === sheet) $("main").append(box);
  // 601-1599: the key block is pinned at the bottom of the drawer; the node is moved, not copied
  const legend = $("legend");
  const mid = !phone() && !wide();
  if (open && mid) { if (legend.parentElement !== box) box.append(legend); }
  else if (legend.parentElement !== $("story")) $("trust").before(legend);
  legend.classList.toggle("key--pinned", open && mid);
}

function openDetails(sec = null, { vid = null, opener = null, from = null } = {}) {
  if (ui.present) return;
  const was = ui.details.open;
  ui.details = { open: true, sec, vid, from: from || ui.details.from, opener: was ? ui.details.opener : (opener || document.activeElement) };
  if (sec && sectionOf(sec)?.xtab) ui.rail = sectionOf(sec).xtab;
  placeDetails();
  saveDetails();
  renderNow();
  requestAnimationFrame(() => { $("details-body").scrollTop = 0; $("details-title").focus({ preventScroll: true }); });
  if (!was && wide()) setTimeout(() => map?.map.resize(), 400);
}

function detailsIndex() {
  const from = ui.details.sec;
  ui.details = { ...ui.details, sec: null };
  saveDetails();
  renderNow();
  requestAnimationFrame(() => (document.querySelector(`[data-focus="drow-${CSS.escape(from || "")}"]`) || $("details-title")).focus({ preventScroll: true }));
}

function closeDetails(restore = true) {
  if (!ui.details.open) return;
  const back = ui.details.opener;
  ui.details = { open: false, sec: null, vid: null, from: null, opener: null };
  placeDetails();
  saveDetails();
  renderNow();
  if (wide()) setTimeout(() => map?.map.resize(), 400);
  if (restore) (back && document.contains(back) && back.offsetParent !== null ? back : $("details-btn")).focus({ preventScroll: true });
}

// The old rail panel ids still work (R8.2): they open their section.
function setRail(id) {
  const p = PANELS.find((x) => x.id === id);
  if (p) openDetails(p.sec);
}

function toggleSection(sec, opener) {
  if (ui.details.open && ui.details.sec === sec) closeDetails();
  else openDetails(sec, { opener });
}

// ------------------------------------------------------------------ area menu (R3.1)

function openAreaMenu() {
  const menu = $("regions");
  menu.hidden = false;
  $("area-btn").setAttribute("aria-expanded", "true");
  (menu.querySelector('[aria-checked="true"]') || menu.querySelector("button"))?.focus();
}

function closeAreaMenu(focusBtn = true) {
  const menu = $("regions");
  if (menu.hidden) return;
  menu.hidden = true;
  $("area-btn").setAttribute("aria-expanded", "false");
  if (focusBtn) $("area-btn").focus();
}

// ------------------------------------------------------------------ dialogs

function openDialog(kind, title, body, opener) {
  const dlg = $("dlg");
  dialogKind = kind;
  dialogOpener = opener || document.activeElement;
  dlg.dataset.kind = kind;
  $("dlg-title").textContent = title;
  $("dlg-body").replaceChildren(body);
  if (!dlg.open) dlg.showModal();
  return dlg;
}

function openHelp(opener, at = null) {
  const dlg = openDialog("help", "Help", helpContent(ui.shortcuts), opener);
  if (at) requestAnimationFrame(() => { const h = $(at); h?.scrollIntoView({ block: "start" }); h?.focus({ preventScroll: true }); });
  return dlg;
}

function openAbout(opener, at = null) {
  openDialog("about", "About TEPHRA", aboutContent(store.state, $("drawer-attrib").textContent || undefined), opener);
  if (at) requestAnimationFrame(() => { const h = $(at); h?.scrollIntoView({ block: "start" }); h?.focus({ preventScroll: true }); });
}

async function openPolicy(opener) {
  let data = null;
  try {
    const res = await fetch("/api/policy", { headers: { Accept: "application/json" }, cache: "no-store", signal: AbortSignal.timeout(8000) });
    if (res.ok) data = await res.json();
  } catch { /* the dialog says it could not load */ }
  openDialog("policy", "Operator policy", policyDialog(data), opener);
}

function openSources(kind, opener) {
  const dlg = openDialog("sources", "Sources side by side", sourcesDialog(D, kind), opener);
  if (kind) {
    const col = dlg.querySelector(`.raw[data-kind="${CSS.escape(kind)}"] .raw__text`);
    col?.focus();
    col?.scrollIntoView({ block: "nearest" });
  }
}

$("dlg").addEventListener("close", () => {
  dialogKind = null;
  const back = dialogOpener;
  dialogOpener = null;
  if (back && document.contains(back)) back.focus();
});
$("details-sheet").addEventListener("cancel", (e) => { e.preventDefault(); escapeDetails(); });

// ------------------------------------------------------------------ map wiring

function onFeature(hit) {
  if (!D) return;
  const id = hit.layer.id;
  const p = hit.properties || {};
  const canvas = $("map-canvas");
  if (id === "aircraft-icon" || id === "exposure-entry") {
    const f = D.aircraft.find((a) => a.properties.hex === p.hex);
    if (!f) return;
    pickFlight(f);
    openDetails("flight", { opener: canvas });
  } else if (id === "reroute-line" || id === "reroute-wp") {
    const f = D.aircraft.find((a) => `${a.properties.hex}:${a.properties.volcano_id}` === p.flight_id || a.properties.proxy_flight === p.proxy_flight);
    if (f) { pickFlight(f); openDetails("flight", { opener: canvas }); }
  } else if (id.startsWith("volcano")) {
    if (D.sits.some((s) => s.volcano_id === p.id)) select(p.id);
  } else if (id.startsWith("crew")) {
    openDetails("crew", { vid: p.report_id || null, opener: canvas });
  } else if (id.startsWith("official") || id.startsWith("tephra")) {
    openDetails("area", { vid: p.volcano_id || D.selected, opener: canvas });
  }
}

// The picked aircraft stays marked on the map and in the flights list until cleared (7.8).
function pickFlight(f) {
  ui.selFlight = { hex: f.properties.hex, proxy: f.properties.proxy_flight };
  renderNow();
}

function clearFlight() {
  ui.selFlight = null;
  if (ui.details.sec === "flight") ui.details.sec = "flights";
  renderNow();
}

function flyToFlight(key) {
  const f = D?.aircraft.find((a) => String(a.id ?? a.properties.hex) === key || a.properties.hex === key);
  if (!f || !map) return;
  pickFlight(f);
  openDetails("flight", { from: "flights" });
  map.flyToFlight(f);
}

function startMap() {
  if (!window.maplibregl) {
    extra.mapError = "the map library did not load";
    scheduleRender();
    return;
  }
  map = new WallMap({
    container: $("map"),
    C: readTokens(),
    ui,
    onFeature,
    onReady: () => {},
    onNote: (kind, text) => {
      if (kind === "basemap") extra.basemap = text;
      if (kind === "context") { renderCtx(); renderPills(); return; }
      scheduleRender();
    },
  });
  const canvas = map.map.getCanvas();
  canvas.setAttribute("aria-label", "Map. Arrow keys pan, plus and minus zoom. Click an area or a plane for its details.");
  canvas.id = "map-canvas";
  if (D) map.update(D);
}

// ------------------------------------------------------------------ events

document.addEventListener("click", (e) => {
  const skip = e.target.closest('a.skip-link[href="#map"]');
  if (skip) { e.preventDefault(); $("map-canvas")?.focus(); return; }
  if (!e.target.closest(".areapick")) closeAreaMenu(false);
  const t = e.target.closest("button, [data-act]");
  if (!t) return;
  const act = t.dataset.act;
  const tool = t.dataset.tool;
  if (tool === "frame") map?.frame({ animate: true });
  else if (tool === "3d") toggle3d();
  else if (tool === "compare") toggleCompare();
  else if (tool === "sat") setSat(SAT_CYCLE[(SAT_CYCLE.indexOf(ui.sat) + 1) % SAT_CYCLE.length]);
  else if (tool === "layers") toggleSection("layers", t);
  else if (tool === "levels") openDetails("levels", { opener: t });
  else if (t.id === "area-btn") { if ($("regions").hidden) openAreaMenu(); else closeAreaMenu(); }
  else if (t.id === "ai-chip") openDetails("ai", { opener: t });
  else if (t.id === "feeds-chip") openDetails("feeds", { opener: t });
  else if (t.id === "details-btn") { if (ui.details.open) closeDetails(); else openDetails(null, { opener: t }); }
  else if (t.id === "time-pill") { document.body.classList.toggle("tl-sheet"); renderNow(); if (document.body.classList.contains("tl-sheet")) $("timeline").querySelector("button")?.focus(); }
  else if (t.id === "about-btn") openAbout(t);
  else if (t.id === "attribution") openAbout(t, "about-credits");
  else if (t.id === "help-btn") openHelp(t);
  else if (t.id === "policy-btn") openPolicy(t);
  else if (t.dataset.region) { const fromMenu = !!t.closest("#regions"); chooseRegion(t.dataset.region); if (fromMenu) $("area-btn").focus(); }
  else if (t.dataset.flight) flyToFlight(t.dataset.flight);
  else if (act === "select" && t.dataset.vid) select(t.dataset.vid);
  else if (act === "details-open") { if ($("dlg").open) $("dlg").close(); openDetails(t.dataset.sec || null, { opener: t }); }
  else if (act === "details-sec") openDetails(t.dataset.sec, { opener: ui.details.opener, from: t.dataset.sec });
  else if (act === "details-index") detailsIndex();
  else if (act === "details-close") closeDetails();
  else if (act === "key-toggle") {
    ui.keyOpen = !ui.keyOpen;
    try { sessionStorage.setItem("tephra.wall.key", ui.keyOpen ? "open" : "closed"); } catch { /* storage blocked */ }
    renderNow();
  }
  else if (act === "trace-filter") { ui.traceFilter = t.dataset.filter; renderNow(); }
  else if (act === "dk-jump") {
    const to = $(t.dataset.target);
    if (to) { to.scrollIntoView({ block: "start", behavior: reducedMotion() ? "auto" : "smooth" }); to.focus({ preventScroll: true }); }
  }
  else if (act === "vlist-more") { ui.vlistOpen = true; renderNow(); }
  else if (act === "trace-scope") { ui.traceScope = t.dataset.scope; renderNow(); }
  else if (act === "frame") map?.frame({ animate: true });
  else if (act === "raw") openSources(t.dataset.kind, t);
  else if (act === "retry") { extra.error = null; load(); }
  else if (act === "level-preset") levelPreset(t.dataset.preset);
  else if (act === "level-reset") levelPreset("all");
  else if (act === "steps") setSteps(t.dataset.steps);
  else if (act === "steps-now") setSteps("now");
  else if (act === "history") { ui.historyOpen = !ui.historyOpen; if (ui.historyOpen && ui.d3) toggle3d(false); renderNow(); }
  else if (act === "tl-mark") { ui.tlCurrent = t.title; renderNow(); onTimelineMark(t); }
  else if (act === "tl-step") { if (t.getAttribute("aria-disabled") !== "true") stepTimeline(Number(t.dataset.dir)); }
  else if (act === "flight-clear") clearFlight();
  else if (act === "crew-show") {
    // On a phone the Details sheet covers the map: close it and bring the map into view first.
    if (phone()) { closeDetails(false); $("map-pane").scrollIntoView({ block: "center" }); } else ui.details.vid = t.dataset.report;
    map?.flyToCrew(t.dataset.report);
    renderNow();
  }
  else if (act === "ctx-off") { if (t.dataset.layer === "sat") setSat("off"); else setLayer(t.dataset.layer, false); }
  else if (act === "view-2d") toggle3d(false);
  else if (act === "dlg-close") $("dlg").close();
  else if (act === "help") openHelp(t.closest("#dlg") ? dialogOpener : t);
  else if (act === "help-map") openHelp(t, "help-key");
  else if (act === "policy") openPolicy(t.closest("#dlg") ? dialogOpener : t); // About's button: focus goes back to About
});

// Previous / next event (R7): choose the neighbouring marker and act as if it was clicked.
function stepTimeline(dir) {
  const m = timelineTarget(dir, ui.tlCurrent);
  if (!m) return;
  ui.tlCurrent = m.title;
  renderNow();
  announce(m.title);
  onTimelineMark(m);
}

function onTimelineMark(t) {
  const kind = t.dataset.kind;
  if (kind === "SIGMET" || kind === "VAA" || kind === "VONA") openDetails("sources", { opener: t });
  else if (kind === "decision") openDetails("decisions", { opener: t });
  else if (kind === "dis") openDetails("disagree", { opener: t });
  else if (kind === "flight") openDetails("flights", { opener: t });
  map?.frame({ animate: true });
}

document.addEventListener("change", (e) => {
  const t = e.target;
  if (t.dataset.layer) setLayer(t.dataset.layer, t.checked);
  else if (t.dataset.radio === "sat") setSat(t.value);
  else if (t.dataset.radio === "steps") setSteps(t.value);
  else if (t.dataset.act === "shortcuts-toggle") { ui.shortcuts = t.checked; prefs.set("shortcuts", ui.shortcuts); }
  else if (t.id === "region-select") chooseRegion(t.value);
  else if (t.id === "details-volcano") select(t.value);
});

document.addEventListener("toggle", (e) => {
  if (e.target.matches?.(".area__read")) ui.readOpen = e.target.open;
  if (e.target.matches?.('[data-k="layers-more"]')) ui.layersMore = e.target.open;
}, true);

// ---- keyboard: menus, timeline markers, level thumbs, shortcuts

document.addEventListener("keydown", (e) => {
  const t = e.target;
  if (t.closest?.("#regions")) {
    const items = [...$("regions").querySelectorAll("button")];
    const i = items.indexOf(t);
    const j = { ArrowDown: i + 1, ArrowUp: i - 1, Home: 0, End: items.length - 1 }[e.key];
    if (j != null) { items[(j + items.length) % items.length].focus(); e.preventDefault(); return; }
    if (e.key === "Escape" || e.key === "Tab") { closeAreaMenu(e.key === "Escape"); if (e.key === "Escape") e.preventDefault(); return; }
  }
  if (t.id === "area-btn" && (e.key === "ArrowDown" || e.key === "ArrowUp")) { openAreaMenu(); e.preventDefault(); return; }
  if (t.matches?.(".tl__mark") && (e.key === "ArrowRight" || e.key === "ArrowLeft")) {
    const marks = [...document.querySelectorAll(".tl__mark")].sort((a, b) => parseFloat(a.style.left) - parseFloat(b.style.left));
    const i = marks.indexOf(t);
    const n = marks[Math.max(0, Math.min(marks.length - 1, i + (e.key === "ArrowRight" ? 1 : -1)))];
    marks.forEach((m) => { m.tabIndex = m === n ? 0 : -1; });
    n.focus();
    e.preventDefault();
    return;
  }
  if (t.dataset?.thumb && thumbKey(e, t.dataset.thumb)) return;
  shortcut(e);
});

function thumbKey(e, which) {
  const step = { ArrowUp: 1000, ArrowDown: -1000, PageUp: 5000, PageDown: -5000 }[e.key];
  let v = ui.level[which];
  if (step) v += step;
  else if (e.key === "Home") v = 0;
  else if (e.key === "End") v = LEVEL_MAX;
  else return false;
  e.preventDefault();
  setThumb(which, v);
  return true;
}

function setThumb(which, ft) {
  const v = Math.round(Math.max(0, Math.min(LEVEL_MAX, ft)) / 1000) * 1000;
  if (which === "max") ui.level = { min: ui.level.min, max: Math.max(v, ui.level.min + 1000) };
  else ui.level = { min: Math.min(v, ui.level.max - 1000), max: ui.level.max };
  renderNow();
}

// pointer drag on the level track (8.4)
let drag = null;
document.addEventListener("pointerdown", (e) => {
  const track = e.target.closest?.("#levels .levels__track");
  if (!track) return;
  const H = Number($("levels").dataset.h) || track.getBoundingClientRect().height;
  const r = track.getBoundingClientRect();
  const ftAt = (y) => levelFromFrac(1 - (y - r.top) / H);
  const ft = ftAt(e.clientY);
  const which = e.target.dataset.thumb || (Math.abs(ft - ui.level.max) < Math.abs(ft - ui.level.min) ? "max" : "min");
  drag = { which, ftAt };
  track.setPointerCapture?.(e.pointerId);
  if (!e.target.dataset.thumb) setThumb(which, ft);
  e.preventDefault();
});
window.addEventListener("pointermove", (e) => { if (drag) setThumb(drag.which, drag.ftAt(e.clientY)); });
window.addEventListener("pointerup", () => {
  if (!drag) return;
  const which = drag.which;
  drag = null;
  $("levels").querySelector(`[data-thumb="${which}"]`)?.focus({ preventScroll: true });
});

function shortcut(e) {
  if (e.key === "Escape") { escape(e); return; }
  if (!ui.shortcuts || e.ctrlKey || e.metaKey || e.altKey) return;
  const t = e.target;
  if (t.matches?.("input, textarea, select, [contenteditable='true']")) return;
  if ($("dlg").open) return;
  const k = e.key;
  const regions = store.state?.regions || [];
  let handled = true;
  if (/^[1-9]$/.test(k) && regions[Number(k) - 1]) chooseRegion(regions[Number(k) - 1].key);
  else if (k === "[") stepVolcano(-1);
  else if (k === "]") stepVolcano(1);
  else if (k === "f" || k === "F") map?.frame({ animate: true });
  else if (k === "d" || k === "D") toggle3d();
  else if (k === "s" || k === "S") toggleCompare();
  else if (k === "c" || k === "C") { if (D?.sit) openSources(null, document.activeElement); }
  else if (k === "i" || k === "I") setSat(SAT_CYCLE[(SAT_CYCLE.indexOf(ui.sat) + 1) % SAT_CYCLE.length]);
  else if (k === "o" || k === "O") setLayer("so2", !ui.so2);
  else if (k === "b" || k === "B") setLayer("btd", !ui.btd);
  else if (k === "l" || k === "L") toggleSection("layers", document.activeElement);
  else if (k === "t" || k === "T") openDetails("trace", { opener: document.activeElement });
  else if (k === "h" || k === "H") { openDetails("levels", { opener: document.activeElement }); requestAnimationFrame(() => $("levels").querySelector('[data-thumb="max"]')?.focus()); }
  else if (k === "p" || k === "P") setPresent(!ui.present);
  else if (k === "?") openHelp(document.activeElement);
  else handled = false;
  if (handled) e.preventDefault();
}

function escapeDetails() {
  if (ui.details.sec) detailsIndex(); else closeDetails();
}

// Esc (R16): dialog or menu → section → Details index → close Details → History → the picked
// flight → compare → 3D.
function escape(e) {
  if ($("dlg").open) return; // the dialog closes itself
  if (!$("regions").hidden) { closeAreaMenu(); e.preventDefault(); return; }
  if (document.body.classList.contains("tl-sheet")) { document.body.classList.remove("tl-sheet"); renderNow(); $("time-pill").focus(); e.preventDefault(); return; }
  if (ui.details.open) { escapeDetails(); e.preventDefault(); return; }
  if (ui.historyOpen) { ui.historyOpen = false; renderNow(); e.preventDefault(); return; }
  if (ui.selFlight) { clearFlight(); e.preventDefault(); return; }
  if (ui.compare) { toggleCompare(false); e.preventDefault(); return; }
  if (ui.d3) { toggle3d(false); e.preventDefault(); }
}

// ------------------------------------------------------------------ phone: header, sheet, CTA (R4.4)

// The disclaimer lives in the sticky header on a phone, in the footer elsewhere; the node moves.
const phoneMq = window.matchMedia("(max-width: 600px)");
function placeHonesty() {
  const line = document.querySelector(".honesty__line");
  if (!line) return;
  if (phoneMq.matches) { if (line.parentElement !== $("phone-honesty")) $("phone-honesty").append(line); }
  else if (line.parentElement !== document.querySelector(".honesty")) document.querySelector(".honesty").prepend(line);
  // On a phone the sticky header keeps the brand, mode, clock, Desk and the disclaimer; the area,
  // AI and data chips sit in a bar under it that scrolls away (review 1, item 13).
  const area = document.querySelector(".areapick"), ai = $("ai-chip"), feeds = $("feeds-chip"), bar = $("phone-bar");
  if (phoneMq.matches) { if (area.parentElement !== bar) bar.append(area, ai, feeds); }
  else if (area.parentElement === bar) {
    const spacer = document.querySelector(".cmdbar__spacer");
    spacer.before(area);
    spacer.after(ai, feeds);
  }
  placeDetails();
}
phoneMq.addEventListener?.("change", placeHonesty);
placeHonesty();
// On a phone the header sticks below the REPLAY band, whose height wraps with its words.
new ResizeObserver(() => {
  const band = $("replay-banner");
  document.documentElement.style.setProperty("--band-px", `${band.hidden ? 0 : band.offsetHeight}px`);
}).observe($("replay-banner"));

// The sticky call to action shows only while the story's own button is out of view.
const io = "IntersectionObserver" in window ? new IntersectionObserver((entries) => {
  for (const en of entries) $("cta-sticky").hidden = !phoneMq.matches || en.isIntersecting || ui.details.open;
}) : null;
new MutationObserver(() => { const c = $("cta"); if (c && io && c.dataset.watched !== "1") { c.dataset.watched = "1"; io.observe(c); } }).observe($("story-actions"), { childList: true });

// ------------------------------------------------------------------ clocks and start

setInterval(() => { if (D) { D.now = now(); renderClock(D, conn); } }, 1000);
setInterval(() => { if (store.state) renderNow(); }, 15000);
window.addEventListener("resize", () => { placeDetails(); scheduleRender(); });
window.matchMedia("(prefers-reduced-motion: reduce)").addEventListener?.("change", () => scheduleRender());

// The drawer state survives a reload in this tab, never into presentation or screenshot runs.
try {
  const saved = sessionStorage.getItem(DETAILS_KEY);
  if (saved && saved !== "closed" && !PRESENT && !SHOTS) {
    ui.details = { open: true, sec: saved === "index" ? null : sectionOf(saved) ? saved : null, vid: null, from: null, opener: null };
  }
} catch { /* storage blocked: Details starts closed */ }
placeDetails();
renderShell();
inlineSprite().then(() => { if (store.state) renderNow(); else renderShell(); });
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", startMap, { once: true });
else startMap();
load();

// The old rail panel ids still open their Details section (R8.2), for a debugging console.
export { setRail };
