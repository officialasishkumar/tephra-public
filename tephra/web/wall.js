// TEPHRA demo entry point (/demo, the Wall; docs/UI-DESIGN.md, SPEC v2 5.2). Loads GET /api/wall,
// follows GET /api/events, keeps the store and the view state, and renders the slim story strip
// and the story column (wall/story.js), the map (wall/map.js), the time bar and the side panel:
// TEPHRA Assistant (wall/assist-panel.js) and Details (wall/details.js) as two tabs, a bottom sheet
// at 900 px and below. The welcome dialog (wall/welcome.js) opens over it on the first load.
// Feed and model text only ever reaches the page through textContent.

import { $, el, ms, prefs, reducedMotion, inlineSprite, icon, setAirline } from "./wall/util.js";
import { derive, actionWords, deciderName, LEVEL_MAX, levelFromFrac, regionOfVent, sortSituations } from "./wall/derive.js";
import { WallMap, readTokens, SAT } from "./wall/map.js";
import {
  renderChrome, renderFrame, replayLine, renderClock, mapPills, renderTimeline, sourcesDialog, timelineTarget, setAiState,
} from "./wall/panels.js";
import { ext, loadExt, ingest, noteTrace, satScale, aiState, handPlan } from "./wall/ext.js";
import { renderStory, coverageNote, currentPlan, officialBand } from "./wall/story.js";
import { planeCard, volcanoCard, airportCard } from "./wall/pick.js";
import { photoFor, photoFigure } from "./wall/photo.js";
import { renderDetails, sectionOf, PANELS } from "./wall/details.js";
import { boardModel, flowModel } from "./wall/board.js";
import { mountFlow } from "./wall/board-view.js";
import { describeReplay, setModelBackend } from "./wall/x-parts.js";
import { nextRetryMs, shouldReopen } from "./wall/stream.js";
import { setFeatures, has, applyFeatureNav } from "./wall/features.js";
import { mountAssist } from "./wall/assist-panel.js";
import { shouldOpenWelcome, openWelcome } from "./wall/welcome.js";
import { initAccountNav } from "./account-nav.js";

const STREAM_TIMEOUT_MS = 45e3;
// A Wall hidden this long gives its stream (a Cloud Run request slot) back until it is shown.
const HIDDEN_PAUSE_MS = 5 * 60e3;
const TRACE_KEEP = 200;
const SAT_CYCLE = ["off", "ir", "vis", "airmass"];
const DEFAULT_LAYERS = { airports: true, tephra: true, rose: true, aircraft: true, paths: true, routes: true, acLabels: true, context: false, navaids: false, terrain: false, reroutes: false, satboxes: true };
// the story strip's fold and the side panel's tab, kept for the tab (sessionStorage)
const STORY_KEY = "tephra.demo.story";
const SIDE_KEY = "tephra.demo.side";
// the sheet's three heights at 900 px and below (SPEC v2 5.2.4), in the handle's cycle order
const SHEETS = ["peek", "half", "full"];
const SHEET_WORDS = { peek: "peeking, tap to open half way", half: "half open, tap to open fully", full: "open, tap to fold" };
// /assistant: the same page shows the TEPHRA Assistant board (page-mode.js, UI-DESIGN 7.27)
const ASSISTANT_PAGE = document.documentElement.dataset.page === "assistant";
// an airline push shows on the board at most this often (the sample feed pushes every few seconds)
const PUSH_SHOW_MS = 15e3;

// ------------------------------------------------------------------ state

// routeLines: "WIII-WSSS" -> the route line fetched for a picked flight that is not in or heading
// into an area (null while it loads or when the server has no line for it).
// feedReads: each feed's last successful read as the `state` stream moved it ({ feed, at, n }), so
// the board can play back reads that are not trace steps (UI-DESIGN 7.21).
const store = { state: null, snapshot: null, advisories: [], trace: [], feeds: [], feedReads: [], routeLines: new Map() };
// Human decisions composed on the Wall from advisory events: the backend's trace has no
// DESK step yet, and the trace must show the human deciding (7.9).
const localTrace = [];
const params = new URLSearchParams(location.search);
// read before the hash handling below replaces it: a deep link skips the welcome dialog (V20)
const START_HASH = location.hash;
// Recording (?present=1) and automated screenshots (?shots=1) keep the story folded, the panel on
// TEPHRA Assistant and the welcome dialog closed (R8.1, SPEC v2 5.5).
const PRESENT = params.get("present") === "1";
const SHOTS = params.get("shots") === "1";
const savedLayers = prefs.get("layers", {});
const session = (key) => { try { return sessionStorage.getItem(key); } catch { return null; } };
const keep = (key, value) => { try { sessionStorage.setItem(key, value); } catch { /* storage blocked */ } };
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
  // the map key starts open on a map 1360 px wide or more and folded to its bar on smaller ones;
  // a choice made with its button is kept for the session
  keyOpen: (() => { try { const k = sessionStorage.getItem("tephra.wall.key"); if (k) return k === "open"; } catch { /* storage blocked */ } return window.innerWidth >= 1360; })(),
  // which flights the map shows: all, inside the ash, heading in (kept for the session)
  flightFilter: (() => { try { return sessionStorage.getItem("tephra.wall.flights") || "all"; } catch { return "all"; } })(),
  // the story: folded to the slim strip by default, kept for the tab
  storyOpen: !PRESENT && !SHOTS && session(STORY_KEY) === "open",
  // the side panel as a bottom sheet (900 px and below): peek, half or full
  sheet: "peek",
  trustOpen: false, // the hero's note on what TEPHRA's ash area is
  // the case strip's fold (what went wrong): closed until opened, kept for the session
  caseOpen: (() => { try { return sessionStorage.getItem("tephra.wall.case") === "open"; } catch { return false; } })(),
  traceFilter: "all",
  historyLane: "all",
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
  board: { open: false }, // TEPHRA Assistant at work: shown (the /assistant page)
};
// backoff: the wait before the next stream reopen (wall/stream.js), 0 after a good open.
const conn = { lostAt: null, source: null, watchdog: null, lastEventAt: 0, loaded: false, everLost: false, hiddenTimer: null, paused: false, lastTick: null, backoff: 0, reopenTimer: null };
const extra = { error: null, basemap: null, mapError: null, mapNote: null };
const clock = { base: NaN, at: 0 };
const seenDis = new Set();
let D = null;
let lastPushShown = -Infinity;
let map = null;
let dialogKind = null;
let dialogOpener = null;
let lastSel = null;
setAiState(aiState);

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
// 900 px and below: the story strip is a bar over the map and the side panel a bottom sheet
const sheetMode = () => window.innerWidth <= 900;

// ------------------------------------------------------------------ loading and the stream

let extTimer = 0;
function reloadExtSoon() {
  // The Wall's draft and recovery numbers follow the same data as the Desk's (R2.7): reload on a
  // new tick, debounced; the 60 s poll stays as a backstop.
  clearTimeout(extTimer);
  extTimer = setTimeout(() => loadExt(scheduleRender), 2000);
}

// An airline's own TEPHRA names its own airline; the demo's static words say Ring of Fire Air is
// fictional (index.html).
function airlineWords(a) {
  setAirline(a);
  if (!a || a.fictional !== false) return;
  const line = document.querySelector(".honesty__airline");
  if (line) line.title = `TEPHRA checks only ${a.name}'s own flights (${a.code}). Decision support only.`;
}

async function load() {
  try {
    const res = await fetch("/api/wall", { headers: { Accept: "application/json" }, cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    store.state = data.state;
    setFeatures(data.state.features);
    setModelBackend(data.state.llm?.backend);
    airlineWords(data.state.airline);
    applyFeatureNav();
    store.snapshot = data.snapshot;
    store.advisories = data.advisories || [];
    store.trace = mergeTrace(data.trace || []);
    store.feeds = data.state.feeds || [];
    conn.lastTick = data.state.last_tick || null;
    setClock(data.state.now);
    extra.error = null;
    for (const s of store.snapshot.situations || []) for (const d of s.discrepancies) seenDis.add(d.id);
    const first = !conn.loaded;
    if (first) firstRegion();
    conn.loaded = true;
    renderNow();
    if (first) openWelcomeOnLoad();
    if (!conn.source || shouldReopen(conn.source.readyState)) openStream();
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
    conn.backoff = 0;
    if (conn.lostAt) {
      conn.lostAt = null;
      announce("Live updates restored.");
      load();
    }
  };
  // CLOSED (an HTTP error, a 503 while the service restarts): the browser will not retry, so the
  // page drops the source and opens a new one after a wait. CONNECTING: the browser is retrying a
  // network error; the page takes over with its own wait so the retries are bounded.
  es.onerror = () => {
    if (shouldReopen(es.readyState)) { dropStream(es); scheduleReopen(); return; }
    if (es.readyState !== EventSource.OPEN) streamLost();
  };
  on("state", (s) => {
    store.state = s;
    setFeatures(s.features);
    setModelBackend(s.llm?.backend);
    airlineWords(s.airline);
    applyFeatureNav();
    if (s.feeds) { noteReads(s.feeds); store.feeds = s.feeds; }
    setClock(s.now);
    if (store.snapshot && Array.isArray(s.active_volcano_ids)) {
      const active = new Set(s.active_volcano_ids);
      store.snapshot.situations = store.snapshot.situations.filter((x) => active.has(x.volcano_id));
    }
    if (s.last_tick && s.last_tick !== conn.lastTick) { conn.lastTick = s.last_tick; reloadExtSoon(); }
  });
  on("heartbeat", (h) => { if (h.now) setClock(h.now); });
  for (const name of ["volcanoes", "official", "cones", "exposures", "aircraft", "reroutes", "routes"]) on(name, (fc) => { if (store.snapshot) store.snapshot[name] = fc; });
  for (const name of ["notice", "recovery", "budget", "doc"]) on(name, (d) => ingest(name, d));
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
    // the board animates a step the moment it arrives, before the debounced render
    if (ui.board.open) flow?.push(t);
    else updateAssist();
    setTimeout(scheduleRender, 6200);
    if (store.trace.length > TRACE_KEEP) store.trace.splice(0, store.trace.length - TRACE_KEEP);
    ui.freshTrace.add(t.id);
    setTimeout(() => ui.freshTrace.delete(t.id), 800);
  });
  // an airline's positions arriving through the push API (the Desk's Data connections): a read on
  // the board and the Assistant tab, like the public feeds
  on("push", (p) => {
    const at = ms(p.at);
    if (!p.accepted || !Number.isFinite(at) || at - lastPushShown < PUSH_SHOW_MS) return;
    lastPushShown = at;
    const read = { feed: "airline", at: p.at, n: p.accepted };
    store.feedReads.push(read);
    if (ui.board.open) flow?.pushRead(read);
    else updateAssist();
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

// A feed whose last successful read moved is a real read: kept for the board's playback and, while
// the board is open, shown at once.
const READS_KEEP = 300;
function noteReads(feeds) {
  const before = new Map(store.feeds.map((f) => [f.feed, f.last_success_at]));
  for (const f of feeds) {
    const was = before.get(f.feed);
    if (!f.last_success_at || !was || f.last_success_at === was || ms(f.last_success_at) <= ms(was)) continue;
    const read = { feed: f.feed, at: f.last_success_at, n: f.record_count };
    store.feedReads.push(read);
    if (ui.board.open) flow?.pushRead(read);
    else updateAssist();
  }
  if (store.feedReads.length > READS_KEEP) store.feedReads.splice(0, store.feedReads.length - READS_KEEP);
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

// The source is closed and forgotten; the lost banner's time is set once per outage.
function dropStream(es) {
  es.close();
  if (conn.source === es) conn.source = null;
  clearTimeout(conn.watchdog);
  if (!conn.lostAt) {
    conn.lostAt = Number.isFinite(now()) ? now() : Date.now();
    renderNow();
  }
}

// A new stream after the wait, which doubles per failed try (wall/stream.js) and resets on a
// good open; nothing opens while a hidden Wall has given its stream back.
function scheduleReopen() {
  clearTimeout(conn.reopenTimer);
  conn.backoff = nextRetryMs(conn.backoff);
  conn.reopenTimer = setTimeout(() => { conn.reopenTimer = null; if (!conn.source && !conn.paused) openStream(); }, conn.backoff);
}

// A silent stall (no event for STREAM_TIMEOUT_MS) or a browser-side retry loop: whatever the
// source's state, it is replaced.
function streamLost() {
  if (conn.source) dropStream(conn.source);
  else if (!conn.lostAt) { conn.lostAt = Number.isFinite(now()) ? now() : Date.now(); renderNow(); }
  scheduleReopen();
}

// Hidden for HIDDEN_PAUSE_MS: close the stream quietly (no lost banner). Shown again: resync
// from /api/wall, which opens a new stream, as the reconnect path does. A visible Wall never
// pauses: it is an unattended display.
function pauseHiddenStream() {
  conn.hiddenTimer = null;
  if (!document.hidden || !conn.source) return;
  conn.paused = true;
  clearTimeout(conn.watchdog);
  clearTimeout(conn.reopenTimer);
  conn.reopenTimer = null;
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
  if (extra.mapNote) notes.push({ text: extra.mapNote });
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
  // The Assistant page draws the shared header and the board, never the Wall's stage.
  if (ui.board.open) {
    withFocusKept(() => { renderChrome(D, store, ui); renderClock(D, conn); });
    renderFlow();
    return;
  }
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
    renderSide();
    updateAssist();
    updateFold();
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
    map.setClosures(currentPlan()?.closures || []);
    map.setExt({ reroutes, satellite: store.snapshot?.satellite, frames: [...(store.snapshot?.overlays?.frames || []), ...(store.snapshot?.situations || []).flatMap((x) => x.frames || [])] });
    map.update(D);
    if (reframe && D.sit) map.frame({ animate: !reducedMotion() && map.framedOnce });
    else if (reframe && !D.sit && D.area) map.flyRegion(D.area);
  }
}

// Before the first /api/wall answer: the Connecting story, no numbers (R5.4).
function renderShell() {
  if (ui.board.open) renderFlow();
  renderStory(null, store, ui, { conn, extra, announce });
  renderTimeline(null, store, ui, conn);
  renderTools();
  renderSide();
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

function renderFlightFilter() {
  if (!D) return;
  // the one count set (derive.js D.counts) when the story supplies it, so the hero, the radios
  // and Details agree; today's counting otherwise
  const inside = (p) => p.inside === true || p.minutes_to_entry === 0;
  const hexes = (pred) => new Set(D.exposed.filter((f) => pred(f.properties)).map((f) => f.properties.hex)).size;
  const n = D.counts ? { all: D.counts.aircraft, inside: D.counts.inside, heading: D.counts.heading } : { all: D.aircraft.length, inside: hexes(inside), heading: hexes((p) => !inside(p)) };
  for (const b of document.querySelectorAll("#flight-filter [data-ff]")) {
    b.setAttribute("aria-checked", String(b.dataset.ff === ui.flightFilter));
    b.querySelector("b").textContent = String(n[b.dataset.ff]);
  }
}

function setFlightFilter(f) {
  ui.flightFilter = f;
  try { sessionStorage.setItem("tephra.wall.flights", f); } catch { /* storage blocked */ }
  renderNow();
}

function renderTools() {
  renderFlightFilter();
  const lb = document.querySelector('#tools [data-tool="layers"]');
  if (lb) lb.setAttribute("aria-expanded", ui.details.open && ui.details.sec === "layers" ? "true" : "false");
  const pressed = { "sat-toggle": ui.sat !== "off", compare: ui.compare, "3d": ui.d3 };
  for (const [tool, on] of Object.entries(pressed)) document.querySelector(`#tools [data-tool="${tool}"]`)?.setAttribute("aria-pressed", on ? "true" : "false");
  $("compare-labels").hidden = !ui.compare;
  document.body.classList.toggle("is-compare", ui.compare);
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
  handle.setAttribute("aria-label", "Compare: drag or use arrow keys. Left side A, official reports only. Right side B, with TEPHRA's estimate.");
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

// Presentation layout for recording (key P or ?present=1): the story folded and the panel on
// TEPHRA Assistant, so the map gets the frame (14).
function setPresent(on) {
  ui.present = on;
  if (on) { closeDetails(false); if (ui.storyOpen) setStory(false, { focus: false }); }
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

// ------------------------------------------------------------------ the side panel: TEPHRA Assistant and Details (SPEC v2 5.2.3)

// Details is the side panel's second tab; `ui.details.open` says it is the selected one.
function saveSide() {
  keep(SIDE_KEY, ui.details.open ? "details" : "assist");
}

// The tabs (roving tabindex), the two tabpanels and, at 900 px and below, the sheet's height.
function renderSide() {
  const det = ui.details.open;
  for (const [tab, on] of [[$("assist-tab"), !det], [$("details-btn"), det]]) {
    tab.setAttribute("aria-selected", on ? "true" : "false");
    tab.tabIndex = on ? 0 : -1;
  }
  $("assist").hidden = det;
  const side = $("side");
  // under the Assistant tab the diagram's You decide says the foot's words (its rule line included):
  // the foot keeps its button
  side.classList.toggle("is-assist", !det);
  const sheet = sheetMode() ? ui.sheet : "";
  if (side.dataset.sheet !== sheet) side.dataset.sheet = sheet;
  const handle = $("side-handle");
  handle.setAttribute("aria-expanded", sheet && sheet !== "peek" ? "true" : "false");
  handle.setAttribute("aria-label", `Side panel: ${SHEET_WORDS[ui.sheet]}`);
}

// The sheet's height changed: the Assistant tab's catch-up waits while the sheet only peeks, and
// starts (or goes on) once it opens.
function setSheet(state) {
  ui.sheet = state;
  renderSide();
  requestAnimationFrame(() => assist?.poke());
}

// A tab chosen while the sheet only peeks opens it half way, so the tab's content shows.
function openSheet() {
  if (sheetMode() && ui.sheet === "peek") setSheet("half");
}

// The Assistant tab (A, its tab, "See TEPHRA Assistant at work"); `focus` moves focus to its tab.
function showAssist({ focus = false } = {}) {
  if (ASSISTANT_PAGE) return;
  if (ui.details.open) closeDetails(false);
  openSheet();
  if (focus) $("assist-tab").focus({ preventScroll: true });
  requestAnimationFrame(() => assist?.poke());
}

// `focus`: the section's heading takes focus (a row, a key, a map click); a tab keeps it (ARIA tabs).
function openDetails(sec = null, { vid = null, opener = null, from = null, focus = true } = {}) {
  // Details live on the demo: from the Assistant page, a Details link opens the demo at that section
  if (ASSISTANT_PAGE) { location.assign(`/demo#details-${sec || "index"}`); return; }
  if (ui.present) return;
  const was = ui.details.open;
  ui.details = { open: true, sec, vid, from: from || ui.details.from, opener: was ? ui.details.opener : (opener || document.activeElement) };
  if (sec && sectionOf(sec)?.xtab) ui.rail = sectionOf(sec).xtab;
  openSheet();
  saveSide();
  renderNow();
  requestAnimationFrame(() => { $("details-body").scrollTop = 0; if (focus) $("details-title").focus({ preventScroll: true }); });
}

// "Collapse all" in the drawer head shows once two or more disclosures are open in a section.
const openDisclosures = () => [...$("details-body").querySelectorAll(".dsec:not([hidden]) details[open]")];
function updateFold() {
  const n = ui.details.open && ui.details.sec ? openDisclosures().length : 0;
  $("details-fold").hidden = n < 2;
}

function detailsIndex() {
  const from = ui.details.sec;
  ui.details = { ...ui.details, sec: null };
  renderNow();
  requestAnimationFrame(() => (document.querySelector(`[data-focus="drow-${CSS.escape(from || "")}"]`) || $("details-title")).focus({ preventScroll: true }));
}

// Back to the Assistant tab; focus returns to what opened Details, or to the Details tab.
function closeDetails(restore = true) {
  if (!ui.details.open) return;
  const back = ui.details.opener;
  ui.details = { open: false, sec: null, vid: null, from: null, opener: null };
  saveSide();
  renderNow();
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

// ------------------------------------------------------------------ the story: slim strip or full column (SPEC v2 5.2.2)

// Folded (the default), the strip keeps the volcano and the three numbers; expanded, the full
// story column takes its place and the map narrows. Focus goes to the story's heading, and back
// to the strip's button on folding.
function setStory(open, { focus = true } = {}) {
  ui.storyOpen = open;
  keep(STORY_KEY, open ? "open" : "folded");
  // at 900 px and below the story opens above the map: the sheet folds to its peek under it
  if (open && sheetMode()) ui.sheet = "peek";
  placeStory();
  scheduleRender();
  if (focus) (open ? $("volcano-name") : $("rail-btn")).focus({ preventScroll: true });
  // the map's column changes width with the stage's transition; on a map narrower than 900 px the
  // open key would cover a third of it, so it folds there, unless the viewer chose (R5.5)
  setTimeout(() => {
    map?.map.resize();
    if (session("tephra.wall.key") !== null) return;
    const want = window.innerWidth >= 1360 && $("map-pane").offsetWidth >= 900;
    if (ui.keyOpen !== want) { ui.keyOpen = want; renderNow(); map?.frame({ animate: false }); }
  }, reducedMotion() ? 0 : 400);
}

function placeStory() {
  const open = ui.storyOpen;
  $("story").hidden = !open;
  $("rail").hidden = open;
  $("rail-btn").setAttribute("aria-expanded", open ? "true" : "false");
  $("story-fold").setAttribute("aria-expanded", open ? "true" : "false");
  document.body.classList.toggle("story-open", open);
}

// ------------------------------------------------------------------ the welcome dialog (SPEC v2 5.2.1)

const welcome = () => $("welcome");
function showWelcome(opener) {
  if (ASSISTANT_PAGE || !store.state) return;
  openWelcome(welcome(), store.state, { opener });
}

// After the first load, unless ?intro=0, ?shots=1, ?present=1, a deep link or "Don't show this
// again" says not to (wall/welcome.js).
function openWelcomeOnLoad() {
  if (!ASSISTANT_PAGE && shouldOpenWelcome(params, START_HASH)) showWelcome(null);
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

// ------------------------------------------------------------------ TEPHRA Assistant at work (UI-DESIGN 7.21)

// What the board's details read: the data the Wall already holds, and when each trace line reached
// this page (a step that just arrived is "working").
function boardInput() {
  const since = (t) => performance.now() - (t ?? -1e12);
  return {
    state: store.state, duty: store.snapshot?.duty || null, budget: ext.budget, budgetError: ext.errors.budget || null,
    trace: store.trace, recovery: ext.recovery, docs: ext.docs, satellite: store.snapshot?.satellite || [],
    advisories: store.advisories, situations: store.snapshot?.situations || [],
    arrivedAgo: (id) => since(ext.arrivals.get(id)),
  };
}

// The flow board's input: the same data, plus the feed reads, the snapshot's map layers and the
// region the Wall shows.
function flowInput() {
  const s = store.state;
  const region = s ? (s.regions || []).find((r) => r.key === ui.region) || s.region : null;
  const hp = D ? handPlan(D, store) : null;
  return {
    state: s, trace: store.trace, feeds: store.feeds, feedReads: store.feedReads, budget: ext.budget, budgetError: ext.errors.budget || null, duty: store.snapshot?.duty || null,
    snapshot: store.snapshot, region, recovery: ext.recovery, docs: ext.docs, realNow: Date.now(),
    handPlan: hp ? { n: hp.flights.length, must: hp.must } : null,
  };
}

// The side panel's Assistant tab: the board's model, kept current whether or not it is shown. Its
// catch-up's pulses start on the Wall's map (mapView) and wait for the welcome dialog; automated
// screenshots (?shots=1) skip the catch-up and show the steps at the replay clock.
let assist = null;
function updateAssist() {
  if (ASSISTANT_PAGE || !store.state) return;
  assist = assist || mountAssist($("assist"), {
    has,
    mapView: () => {
      const m = map?.map;
      if (!m || !m.getCanvas().width) return null;
      return { rect: $("map").getBoundingClientRect(), project: (ll) => { const p = m.project(ll); return [p.x, p.y]; } };
    },
    sheet: () => (sheetMode() ? ui.sheet : ""),
    blocked: () => welcome().open || $("dlg").open,
    noCatchup: SHOTS,
  });
  assist.update(flowModel(flowInput()), { conn });
}

let flow = null;
function renderFlow() {
  if (!flow || !store.state) return;
  flow.update(flowModel(flowInput()), boardModel(boardInput()), conn);
}

// The board is a page of its own (/assistant, UI-DESIGN 7.27), shown in place of the demo, never as
// a dialog. On the demo the same steps are the side panel's Assistant tab, and its "Open as a
// page" link goes to the board.
function openBoard() {
  if (!ASSISTANT_PAGE) { showAssist({ focus: true }); return; }
  const dlg = $("board");
  ui.board.open = true;
  describeModal(dlg);
  if (!dlg.open) dlg.show();
  flow = flow || mountFlow(dlg, { has });
  flow.open();
  renderNow();
  $("board-title").focus({ preventScroll: true });
}


// ------------------------------------------------------------------ dialogs

// Each modal carries the REPLAY words as sr-only text in its description (wall/x-parts.js
// describeReplay); live, none.
function describeModal(dlg) {
  describeReplay(dlg, replayLine(store.state));
}

function openDialog(kind, title, body, opener) {
  const dlg = $("dlg");
  dialogKind = kind;
  dialogOpener = opener || document.activeElement;
  dlg.dataset.kind = kind;
  $("dlg-title").textContent = title;
  $("dlg-body").replaceChildren(body);
  // One dialog shows each kind in turn: a new kind starts at its top, not where the last was read.
  $("dlg-body").scrollTop = 0;
  describeModal(dlg);
  if (!dlg.open) dlg.showModal();
  return dlg;
}

// Help, About and the operator policy live on the guide page (UI-DESIGN 7.22), in a tab of its own
// so the Wall keeps its place.
function openGuide(section) {
  window.open(`/guide#${section}`, "_blank", "noopener");
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
// the Assistant tab's catch-up waits for the welcome dialog to close
welcome().addEventListener("close", () => requestAnimationFrame(() => assist?.poke()));

// ------------------------------------------------------------------ map wiring

// A plane, a volcano or an airport opens the map's card (UI-DESIGN 7.23): only what is needed, and
// one link to its Details section. Areas, reroutes and crew reports open their Details section.
function onFeature(hit, lngLat) {
  if (!D) return;
  const id = hit.layer.id;
  const p = hit.properties || {};
  const canvas = $("map-canvas");
  if (id === "aircraft-icon" || id === "exposed-icon" || id === "exposure-entry" || id === "exposure-entry-sel") {
    // an entry point carries its flight's id ("<hex>:<volcano>"), a plane its hex
    const hex = p.hex || String(p.flight_id || "").split(":")[0];
    const f = D.aircraft.find((a) => a.properties.hex === hex);
    if (!f) return;
    pickFlight(f);
    const adv = store.advisories.filter((a) => a.hex === hex && a.status !== "SUPERSEDED").sort((a, b) => ms(b.updated_at) - ms(a.updated_at))[0] || null;
    const closed = new Set((currentPlan()?.closures || []).map((c) => c.icao));
    map.showCard(f.geometry.coordinates, planeCard(f.properties, adv, closed));
  } else if (id.startsWith("volcano")) {
    if (D.sits.some((s) => s.volcano_id === p.id)) select(p.id);
    const sit = D.sits.find((s) => s.volcano_id === p.id);
    const node = volcanoCard(p, officialBand(D, p.id), sit?.exposed_count || 0);
    map.showCard(hit.geometry?.type === "Point" ? hit.geometry.coordinates : [lngLat.lng, lngLat.lat], node);
    withPhoto(node, "volcano", p.id, p.name);
  } else if (id.startsWith("airport")) {
    const closure = (currentPlan()?.closures || []).find((c) => c.icao === p.icao) || null;
    const node = airportCard(p, closure);
    map.showCard(hit.geometry.coordinates, node);
    withPhoto(node, "airport", p.icao, p.name || p.icao);
  } else if (id === "reroute-line" || id === "reroute-wp") {
    const f = D.aircraft.find((a) => `${a.properties.hex}:${a.properties.volcano_id}` === p.flight_id || a.properties.proxy_flight === p.proxy_flight);
    if (f) { pickFlight(f); openDetails("flight", { opener: canvas }); }
  } else if (id.startsWith("crew")) {
    openDetails("crew", { vid: p.report_id || null, opener: canvas });
  } else if (id.startsWith("official") || id.startsWith("tephra")) {
    openDetails("area", { vid: p.volcano_id || D.selected, opener: canvas });
  } else if (id.startsWith("closure")) {
    openDetails("recovery", { opener: canvas });
  }
}

// A volcano's or an airport's photo joins its card when one with a free licence is found (photo.js).
function withPhoto(node, kind, code, name) {
  photoFor(kind, code).then((ph) => { if (ph && node.isConnected) node.prepend(photoFigure(ph, name)); });
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
      if (kind === "map") {
        // the map was rebuilt (map.js recover): a swipe compare did not survive it; the note shows
        // for a few seconds, not for the session
        if (ui.compare) ui.compare = false;
        extra.mapNote = text;
        setTimeout(() => { extra.mapNote = null; scheduleRender(); }, 8000);
      }
      scheduleRender();
    },
  });
  const canvas = map.map.getCanvas();
  canvas.setAttribute("aria-label", "Map. Arrow keys pan, plus and minus zoom. Click an area or a plane for its details.");
  canvas.id = "map-canvas";
  // where each airport is, for the airports the plan closes (the catalogue changes only on deploy)
  fetch("/api/airports")
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
    .then((fc) => map.setAirports(fc))
    .catch(() => { extra.airportsMissing = true; scheduleRender(); });
  if (D) map.update(D);
}

// ------------------------------------------------------------------ events

// toggle does not bubble; a capture listener on the drawer body still hears every disclosure.
$("details-body").addEventListener("toggle", updateFold, true);

document.addEventListener("click", (e) => {
  const skip = e.target.closest('a.skip-link[href="#map"]');
  if (skip) { e.preventDefault(); $("map-canvas")?.focus(); return; }
  // the story and side panel skip links land on a control: the strip's button (or the story's
  // heading when expanded) and the selected tab
  const skipTo = e.target.closest("a.skip-link[data-skip]");
  if (skipTo) {
    e.preventDefault();
    if (skipTo.dataset.skip === "story") (ui.storyOpen ? $("volcano-name") : $("rail-btn")).focus();
    else (ui.details.open ? $("details-btn") : $("assist-tab")).focus();
    return;
  }
  if (!e.target.closest(".areapick")) closeAreaMenu(false);
  const t = e.target.closest("button, [data-act]");
  if (!t) return;
  const act = t.dataset.act;
  const tool = t.dataset.tool;
  if (tool === "frame") map?.frame({ animate: true });
  else if (tool === "3d") toggle3d();
  else if (tool === "compare") toggleCompare();
  else if (tool === "sat") setSat(SAT_CYCLE[(SAT_CYCLE.indexOf(ui.sat) + 1) % SAT_CYCLE.length]);
  else if (tool === "sat-toggle") setSat(ui.sat === "off" ? "ir" : "off");
  else if (tool === "layers") toggleSection("layers", t);
  else if (tool === "levels") openDetails("levels", { opener: t });
  else if (t.id === "rail-btn") setStory(true);
  else if (t.id === "story-fold") setStory(false);
  else if (t.id === "how-btn") showWelcome(t);
  else if (t.id === "assist-tab") showAssist();
  else if (t.id === "side-handle") { if (!handleDragged) setSheet(SHEETS[(SHEETS.indexOf(ui.sheet) + 1) % SHEETS.length]); }
  else if (t.dataset.ff) setFlightFilter(t.dataset.ff);
  else if (t.id === "area-btn") { if ($("regions").hidden) openAreaMenu(); else closeAreaMenu(); }
  else if (act === "board-open") openBoard();
  else if (act === "board-details") openDetails(t.dataset.sec);
  else if (t.id === "feeds-chip") openDetails("feeds", { opener: t });
  else if (t.id === "details-btn") { if (ui.details.open) openSheet(); else openDetails(null, { opener: t, focus: false }); }
  else if (t.id === "time-pill") { document.body.classList.toggle("tl-sheet"); renderNow(); if (document.body.classList.contains("tl-sheet")) $("timeline").querySelector("button")?.focus(); }
  else if (t.dataset.region) { const fromMenu = !!t.closest("#regions"); chooseRegion(t.dataset.region); if (fromMenu) $("area-btn").focus(); }
  else if (t.dataset.flight) flyToFlight(t.dataset.flight);
  else if (act === "select" && t.dataset.vid) select(t.dataset.vid);
  else if (act === "details-open") { if ($("dlg").open) $("dlg").close(); openDetails(t.dataset.sec || null, { opener: t }); }
  else if (act === "details-sec") openDetails(t.dataset.sec, { opener: ui.details.opener, from: t.dataset.sec });
  else if (act === "chain") openDetails("chain", { vid: t.dataset.vid || null, opener: t, from: ui.details.sec });
  else if (act === "details-index") detailsIndex();
  else if (act === "details-close") closeDetails();
  else if (act === "details-fold") {
    for (const d of openDisclosures()) d.open = false;
    $("details-fold").hidden = true;
    $("details-title").focus({ preventScroll: true });
  }
  else if (act === "key-toggle") {
    ui.keyOpen = !ui.keyOpen;
    try { sessionStorage.setItem("tephra.wall.key", ui.keyOpen ? "open" : "closed"); } catch { /* storage blocked */ }
    renderNow();
  }
  else if (act === "trust-toggle") { ui.trustOpen = !ui.trustOpen; renderNow(); }
  else if (act === "case-toggle") {
    ui.caseOpen = !ui.caseOpen;
    try { sessionStorage.setItem("tephra.wall.case", ui.caseOpen ? "open" : "closed"); } catch { /* storage blocked */ }
    renderNow();
  }
  else if (act === "history-lane") { ui.historyLane = t.dataset.lane; renderNow(); }
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
    // At 900 px and below the sheet covers the map: it folds to its peek so the report shows.
    if (sheetMode()) setSheet("peek");
    ui.details.vid = t.dataset.report;
    map?.flyToCrew(t.dataset.report);
    renderNow();
  }
  else if (act === "ctx-off") { if (t.dataset.layer === "sat") setSat("off"); else setLayer(t.dataset.layer, false); }
  else if (act === "view-2d") toggle3d(false);
  else if (act === "dlg-close") $("dlg").close();
  else if (act === "help") openGuide("read");
  else if (act === "help-map") openGuide("help-key");
  else if (act === "policy") openGuide("policy");
  else if (act === "key") { if (t.dataset.key === "Escape") escape({ preventDefault() {} }); else runKey(t.dataset.key); }
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
  // the side panel's tabs (ARIA tabs, roving tabindex): arrows move and select, Home and End jump
  if (t.closest?.("#side-tabs") && t.getAttribute("role") === "tab") {
    const tabs = [$("assist-tab"), $("details-btn")];
    const i = tabs.indexOf(t);
    const j = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[e.key];
    if (j != null) {
      e.preventDefault();
      const to = tabs[(j + tabs.length) % tabs.length];
      if (to === tabs[0]) showAssist(); else if (!ui.details.open) openDetails(null, { opener: to, focus: false });
      to.focus();
      return;
    }
  }
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
  if ($("dlg").open || $("board").open || welcome().open) return;
  if (runKey(e.key)) e.preventDefault();
}

// One shortcut, from the keyboard or from its key in the status line; true when it was one.
function runKey(k) {
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
  else if (k === "b" || k === "B") { if (!has("btd")) return false; setLayer("btd", !ui.btd); }
  else if (k === "l" || k === "L") toggleSection("layers", document.activeElement);
  else if (k === "t" || k === "T") openDetails("trace", { opener: document.activeElement });
  else if (k === "h" || k === "H") { openDetails("levels", { opener: document.activeElement }); requestAnimationFrame(() => $("levels").querySelector('[data-thumb="max"]')?.focus()); }
  else if (k === "p" || k === "P") { if (!has("present")) return false; setPresent(!ui.present); }
  else if (k === "a" || k === "A") openBoard();
  else if (k === "w" || k === "W") { if (ASSISTANT_PAGE) return false; showWelcome(document.activeElement); }
  else if (k === "e" || k === "E") { if (ASSISTANT_PAGE) return false; setStory(!ui.storyOpen); }
  else if (k === "?") openGuide("read");
  else handled = false;
  return handled;
}

// Esc (R16): dialog or menu → the map's card → a Details section → its index (Details stays the
// tab) → the open sheet → History → the picked flight → compare → 3D.
function escape(e) {
  if ($("dlg").open || $("board").open || welcome().open) return; // a dialog closes itself
  if (!$("regions").hidden) { closeAreaMenu(); e.preventDefault(); return; }
  if (document.body.classList.contains("tl-sheet")) { document.body.classList.remove("tl-sheet"); renderNow(); $("time-pill").focus(); e.preventDefault(); return; }
  if (map?.hideCard()) { e.preventDefault(); return; }
  if (ui.details.open && ui.details.sec) { detailsIndex(); e.preventDefault(); return; }
  if (sheetMode() && ui.sheet !== "peek") { setSheet("peek"); $("side-handle").focus({ preventScroll: true }); e.preventDefault(); return; }
  if (ui.historyOpen) { ui.historyOpen = false; renderNow(); e.preventDefault(); return; }
  if (ui.selFlight) { clearFlight(); e.preventDefault(); return; }
  if (ui.compare) { toggleCompare(false); e.preventDefault(); return; }
  if (ui.d3) { toggle3d(false); e.preventDefault(); }
}

// ------------------------------------------------------------------ the sheet's handle (900 px and below)

// A tap cycles peek, half and full; a drag on the handle moves the sheet and lets go at the
// nearest of the three heights. The handle is a button, so the keyboard cycles it too.
let handleDragged = false;
{
  const handle = $("side-handle");
  let drag = null;
  handle.addEventListener("pointerdown", (e) => {
    if (!sheetMode()) return;
    handleDragged = false;
    drag = { y: e.clientY, h: $("side").getBoundingClientRect().height };
    handle.setPointerCapture?.(e.pointerId);
  });
  handle.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const h = drag.h + (drag.y - e.clientY);
    if (Math.abs(drag.y - e.clientY) > 6) handleDragged = true;
    if (handleDragged) { $("side").classList.add("is-dragging"); $("side").style.setProperty("height", `${Math.max(120, h)}px`); }
  });
  const done = () => {
    if (!drag) return;
    drag = null;
    const side = $("side");
    if (handleDragged) {
      const h = side.getBoundingClientRect().height;
      const heights = SHEETS.map((k) => [k, Math.abs(h - sheetHeight(k))]);
      heights.sort((a, b) => a[1] - b[1]);
      side.style.removeProperty("height");
      side.classList.remove("is-dragging");
      setSheet(heights[0][0]);
    }
    // the click that follows a drag must not cycle the sheet once more
    setTimeout(() => { handleDragged = false; }, 0);
  };
  handle.addEventListener("pointerup", done);
  handle.addEventListener("pointercancel", done);
}
// The three heights, as wall.css draws them: a share of the viewport, full under the header.
function sheetHeight(k) {
  const vh = window.innerHeight;
  if (k === "peek") return 0.3 * vh;
  if (k === "half") return 0.58 * vh;
  return vh - document.querySelector(".cmdbar").getBoundingClientRect().bottom;
}

// ------------------------------------------------------------------ clocks and start

setInterval(() => { if (D) { D.now = now(); renderClock(D, conn); } }, 1000);
setInterval(() => { if (store.state) renderNow(); }, 15000);
window.addEventListener("resize", () => { renderSide(); scheduleRender(); });
window.matchMedia("(prefers-reduced-motion: reduce)").addEventListener?.("change", () => scheduleRender());

// The side panel's tab survives a reload in this tab, never into presentation or screenshot runs,
// and never onto the Assistant page (the board is the page there).
if (!PRESENT && !SHOTS && !ASSISTANT_PAGE && session(SIDE_KEY) === "details") ui.details = { open: true, sec: null, vid: null, from: null, opener: null };
placeStory();
renderShell();
// Old "See TEPHRA Assistant at work" links (#ai-at-work) go to its page; the guide's "Track
// record ›" (#track-record) and the board's "Details ›" (#details-<section>) open that Details
// section. The hash is not kept, so a reload shows the demo.
const hashSec = START_HASH === "#track-record" ? "proof" : START_HASH.match(/^#details-([a-z]+)$/)?.[1];
if (START_HASH === "#ai-at-work") location.replace("/assistant");
else if (hashSec && !ASSISTANT_PAGE) {
  history.replaceState(history.state, "", location.pathname + location.search);
  openDetails(hashSec === "index" ? null : hashSec, { opener: $("details-btn") });
}
if (ASSISTANT_PAGE) {
  // the nav names no page here: /assistant is reached from the side panel's icon and the Guide
  document.querySelector('.topnav a[href="/demo"]')?.removeAttribute("aria-current");
  openBoard();
}
// signed in as an airline, the nav's Onboard link reads Workspace (account-nav.js)
initAccountNav();
inlineSprite().then(() => { if (store.state) renderNow(); else renderShell(); });
// the Assistant page draws the board's own map, not the Wall's
if (ASSISTANT_PAGE) { /* no Wall map */ }
else if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", startMap, { once: true });
else startMap();
load();

// The old rail panel ids still open their Details section (R8.2), for a debugging console.
export { setRail };
