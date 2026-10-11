// TEPHRA Wall entry point (docs/UI-DESIGN.md). Loads GET /api/wall, follows GET /api/events,
// keeps the store and the view state, and renders the map (wall/map.js) and the panels
// (wall/panels.js). Feed and model text only ever reaches the page through textContent.

import { $, el, ms, hhmmssz, inBbox, prefs, reducedMotion, inlineSprite, icon } from "./wall/util.js";
import { derive, actionWords, deciderName, LEVEL_MAX, levelFromFrac } from "./wall/derive.js";
import { WallMap, readTokens, SAT } from "./wall/map.js";
import {
  renderChrome, renderClock, renderLegend, renderHeadline, mapNotes, renderFlights, renderTrace, renderTabs,
  renderBrief, renderLevels, renderTimeline, feedsDialog, sourcesDialog, policyDialog, popupContent,
} from "./wall/panels.js";
import { renderLayers, helpContent, aboutContent } from "./wall/controls.js";
import { ext, loadExt, ingest, noteTrace, renderXTabs, renderXPanel, renderAiChip, reroutePopup, PANELS } from "./wall/ext.js";

const STREAM_TIMEOUT_MS = 45e3;
const TRACE_KEEP = 200;
const SAT_CYCLE = ["off", "ir", "vis", "airmass"];
const DEFAULT_LAYERS = { tephra: true, rose: true, aircraft: true, paths: true, acLabels: true, context: true, navaids: false, terrain: false, reroutes: true, satboxes: true };

// ------------------------------------------------------------------ state

const store = { state: null, snapshot: null, advisories: [], trace: [], feeds: [] };
// Human decisions composed on the Wall from advisory events: the backend's trace has no
// DESK step yet, and the trace must show the human deciding (7.9).
const localTrace = [];
const ui = {
  selected: null,
  autoSelect: true,
  region: null,
  emptyRegion: false,
  layers: { ...DEFAULT_LAYERS, ...prefs.get("layers", {}) },
  sat: SAT_CYCLE.includes(prefs.get("sat", "off")) ? prefs.get("sat", "off") : "off",
  so2: !!prefs.get("so2", false),
  btd: !!prefs.get("btd", false),
  steps: prefs.get("steps", "now"),
  level: { min: 0, max: LEVEL_MAX },
  d3: false,
  compare: false,
  legendOpen: new URLSearchParams(location.search).get("present") === "1" ? false : prefs.get("legendOpen", window.innerWidth >= 1600),
  layersOpen: false,
  levelsOpen: false,
  traceExpanded: false,
  traceScope: "volcano",
  harmlessOpen: false,
  readOpen: false,
  ptab: "brief",
  rail: "brief",
  shortcuts: prefs.get("shortcuts", true),
  freshTrace: new Set(),
  freshDis: new Set(),
  freshDecisions: new Set(),
  present: new URLSearchParams(location.search).get("present") === "1",
};
const conn = { lostAt: null, source: null, watchdog: null, lastEventAt: 0, loaded: false, everLost: false };
const extra = { error: null, basemap: null };
const clock = { base: NaN, at: 0 };
const seenDis = new Set();
let D = null;
let map = null;
let dialogKind = null;
let dialogOpener = null;

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

// ------------------------------------------------------------------ loading and the stream

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
    setClock(data.state.now);
    extra.error = null;
    for (const s of store.snapshot.situations || []) for (const d of s.discrepancies) seenDis.add(d.id);
    conn.loaded = true;
    renderNow();
    if (!conn.source) openStream();
    if (!ext.started) { ext.started = true; loadExt(scheduleRender); setInterval(() => loadExt(scheduleRender), 60e3); }
  } catch {
    extra.error = "Can't reach TEPHRA. Retrying in 5 s…";
    renderNow();
    setTimeout(load, 5000);
  }
}

// First view: the top-priority active volcano inside the server's region, else overall.
function initialSelection() {
  const tmp = derive(store, { ...ui, emptyRegion: false, selected: null }, now());
  const region = store.state.region;
  ui.region = ui.region || region?.key || null;
  const inRegion = region ? tmp.sits.filter((s) => tmp.vents.get(s.volcano_id) && inBbox(tmp.vents.get(s.volcano_id), region.bbox)) : [];
  const pick = (inRegion[0] || tmp.sits[0])?.volcano_id || null;
  const changed = !!ui.selected && pick !== ui.selected;
  ui.selected = pick;
  // keep choosing automatically until a volcano of the server's region is active
  if (inRegion.length) ui.autoSelect = false;
  return changed;
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
  });
  on("heartbeat", (h) => { if (h.now) setClock(h.now); });
  on("feeds", (f) => { store.feeds = f.feeds || []; if (store.state) store.state.feeds = store.feeds; });
  for (const name of ["volcanoes", "official", "cones", "exposures", "aircraft", "reroutes"]) on(name, (fc) => { if (store.snapshot) store.snapshot[name] = fc; });
  for (const name of ["notice", "recovery", "budget"]) on(name, (d) => ingest(name, d));
  on("satellite", (r) => {
    if (!store.snapshot) return;
    const list = store.snapshot.satellite || (store.snapshot.satellite = []);
    const i = list.findIndex((x) => x.volcano_id === r.volcano_id);
    if (i >= 0) list[i] = r; else list.push(r);
    announce(r.status === "ai_unavailable" ? `Satellite check unavailable for ${r.volcano_id}` : `New satellite check for ${r.volcano_id}`);
  });
  on("overlays", (o) => { if (store.snapshot) store.snapshot.overlays = o; });
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
      announce(`New disagreement at ${card.volcano_name}: ${d.summary}`);
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
      showDecision(a.id);
      announce(a.status === "REJECTED" ? `${who} rejected the advisory for ${a.proxy_flight}` : `${who} approved ${actionWords(a)} for ${a.proxy_flight}`);
    } else if (!prev && a.status === "DRAFT") {
      announce(`New draft: ${a.proxy_flight}, ${actionWords(a)}${a.inside_now ? ", inside now" : `, enters in ${a.minutes_to_entry} min`}`);
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

// Bring the stamped decision into view in the rail after the render that stamps it (7.14).
function showDecision(id) {
  if (phone()) return;
  setTimeout(() => {
    const brief = $("brief");
    const row = document.querySelector(`#decisions [data-adv="${CSS.escape(id)}"]`) || $("decisions");
    if (!brief || !row) return;
    const br = brief.getBoundingClientRect(), rr = row.getBoundingClientRect();
    if (rr.top >= br.top + 8 && rr.bottom <= br.bottom - 8) return;
    const top = brief.scrollTop + (rr.top - br.top) - Math.max(16, br.height - rr.height - 80);
    brief.scrollTo({ top: Math.max(0, top), behavior: reducedMotion() ? "auto" : "smooth" });
  }, 120);
}

function touch() {
  conn.lastEventAt = performance.now();
  clearTimeout(conn.watchdog);
  conn.watchdog = setTimeout(streamLost, STREAM_TIMEOUT_MS);
}

function streamLost() {
  if (conn.lostAt) return;
  conn.lostAt = Number.isFinite(now()) ? now() : Date.now();
  announce("Live updates lost. Showing the last data received.");
  // EventSource retries by itself after an error; a silent stall needs a fresh connection.
  if (conn.source && conn.source.readyState === EventSource.OPEN) {
    conn.source.close();
    conn.source = null;
    setTimeout(() => { if (!conn.source) openStream(); }, 3000);
  }
  renderNow();
}

// ------------------------------------------------------------------ rendering

let pending = 0;
function scheduleRender() {
  if (pending) return;
  pending = setTimeout(() => { pending = 0; renderNow(); }, 40);
}

const phone = () => window.innerWidth <= 600;

function withFocusKept(fn) {
  const active = document.activeElement;
  const key = active?.dataset?.focus;
  const brief = $("brief");
  const top = brief.scrollTop;
  const traceList = $("trace").querySelector(".trace__list");
  const traceAtEnd = !traceList || traceList.scrollTop + traceList.clientHeight >= traceList.scrollHeight - 8;
  const traceTop = traceList?.scrollTop;
  fn();
  brief.scrollTop = top;
  if (!traceAtEnd) {
    const l = $("trace").querySelector(".trace__list");
    if (l) l.scrollTop = traceTop;
  }
  if (key && (!document.activeElement || document.activeElement === document.body)) {
    const next = document.querySelector(`[data-focus="${CSS.escape(key)}"]`);
    next?.focus({ preventScroll: true });
  }
}

function renderNow() {
  if (!store.state) {
    renderShell();
    return;
  }
  // First view (7.4): pick once there are situations; until then nothing is chosen.
  let reframe = false;
  if (ui.autoSelect && !ui.emptyRegion && store.snapshot?.situations?.length) reframe = initialSelection();
  D = derive(store, ui, now());
  withFocusKept(() => {
    renderChrome(D, store, ui);
    renderClock(D, conn);
    renderLegend(D, ui);
    renderHeadline(D, ui, mapNotes(D, ui, store, extra), store);
    renderTabs(D, conn);
    renderBrief(D, store, ui);
    renderXTabs(D, store, ui);
    renderXPanel(D, store, ui);
    renderAiChip(store);
    renderFlights(D, store, ui);
    renderTrace(D, store, ui, conn);
    if (phone()) {
      const rf = $("rail-flights"), rt = $("rail-trace");
      if (rf) renderFlights(D, store, ui, rf, { all: true });
      if (rt) renderTrace(D, store, ui, conn, rt, { full: true });
    }
    renderLevels(D, ui);
    renderTimeline(D, store, ui, conn);
    renderTools();
    renderCtx();
    if (ui.layersOpen) renderLayers(ui);
    if (dialogKind === "feeds") $("dlg-body").replaceChildren(feedsDialog(D, store));
  });
  document.body.classList.toggle("is-stale", !!conn.lostAt);
  document.body.classList.toggle("is-3d", ui.d3);
  document.body.classList.toggle("present", ui.present);
  const hz = D?.sit ? D.coneOf(D.sit.volcano_id)?.properties : null;
  document.body.classList.toggle("hazard-on", !!hz && ui.level.min === Math.max(0, hz.base_ft) && ui.level.max === Math.min(LEVEL_MAX, hz.top_ft));
  $("stale-chip").hidden = !conn.lostAt;
  const lost = $("lost-banner");
  lost.hidden = !conn.lostAt;
  if (conn.lostAt) lost.textContent = `Live updates lost at ${hhmmssz(conn.lostAt)}. Showing the last data received; reconnecting…`;
  document.body.dataset.ptab = ui.ptab;
  if (map) {
    map.setExt({ reroutes: store.snapshot?.reroutes, satellite: store.snapshot?.satellite, frames: [...(store.snapshot?.overlays?.frames || []), ...(store.snapshot?.situations || []).flatMap((x) => x.frames || [])] });
    map.update(D);
    if (reframe) map.frame({ animate: false });
  }
}

// Before the first /api/wall answer: skeletons and the CONNECTING state (7.17).
function renderShell() {
  renderHeadline({ sit: null }, ui, mapNotes(null, ui, store, extra), store);
  renderTabs(null, conn);
  renderBrief(null, store, ui);
  renderFlights(null, store, ui);
  renderTrace(null, store, ui, conn);
  renderTimeline(null, store, ui, conn);
  renderLevels(null, ui);
  renderLegend({ official: [], cones: [], exposed: [], aircraft: [], rose: null }, ui);
  renderTools();
}

function renderTools() {
  const set = (tool, pressed) => {
    const b = document.querySelector(`[data-tool="${tool}"]`);
    if (b) b.setAttribute("aria-pressed", pressed ? "true" : "false");
  };
  set("3d", ui.d3);
  set("compare", ui.compare);
  set("sat", ui.sat !== "off");
  $("sat-state").textContent = ui.sat === "off" ? "Satellite" : SAT[ui.sat].short;
  document.querySelector('[data-tool="layers"]').setAttribute("aria-expanded", ui.layersOpen ? "true" : "false");
  document.querySelector('[data-tool="levels"]').setAttribute("aria-expanded", ui.levelsOpen ? "true" : "false");
  $("layers-pop").hidden = !ui.layersOpen;
  $("levels").classList.toggle("levels--open", ui.levelsOpen);
  $("compare-labels").hidden = !ui.compare;
}

// "CONTEXT ONLY" labels for satellite, SO2 and BTD layers (5.6), always on screen while shown.
function renderCtx() {
  const box = $("ctx-label");
  const lines = map ? map.satLabel() : [];
  box.hidden = !lines.length;
  box.replaceChildren(...lines.map((t) => el("p", { class: "ctx-label__line glass" }, el("strong", { text: "CONTEXT ONLY" }), el("span", { text: t.replace(/^CONTEXT ONLY · /, " · ") }))));
}

// ------------------------------------------------------------------ actions

function select(vid, { frame = true } = {}) {
  ui.autoSelect = false;
  ui.selected = vid;
  ui.emptyRegion = false;
  renderNow();
  if (frame) map?.frame({ animate: true });
  const head = $("volcano-name");
  if (head && document.activeElement?.closest?.("#volcano-tabs") == null && frame === "focus") head.focus();
}

function stepVolcano(dir) {
  if (!D?.sits.length) return;
  const i = Math.max(0, D.sits.findIndex((s) => s.volcano_id === D.selected));
  const next = D.sits[(i + dir + D.sits.length) % D.sits.length];
  select(next.volcano_id);
}

function chooseRegion(key) {
  const r = (store.state?.regions || []).find((x) => x.key === key);
  if (!r || !D) return;
  ui.region = key;
  ui.autoSelect = false;
  const inRegion = D.sits.filter((s) => D.vents.get(s.volcano_id) && inBbox(D.vents.get(s.volcano_id), r.bbox));
  if (inRegion.length) {
    select(inRegion[0].volcano_id);
  } else {
    ui.emptyRegion = true;
    renderNow();
    // no volcano is selected now: a focused tab would read as a selection, so focus moves
    // to the region that was chosen
    if (document.activeElement?.closest?.("#volcano-tabs")) document.querySelector(`[data-focus="region-${CSS.escape(key)}"]`)?.focus({ preventScroll: true });
    map?.flyRegion(r);
  }
}

function setLayer(key, on) {
  if (key === "so2") ui.so2 = on;
  else if (key === "btd") ui.btd = on;
  else if (key in ui.layers) ui.layers[key] = on;
  prefs.set("layers", ui.layers);
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

function setRail(id, focusPanel) {
  if (!PANELS.some((p) => p.id === id)) return;
  ui.rail = id;
  renderNow();
  if (focusPanel) (id === "brief" ? $("brief") : $("xpanel"))?.focus({ preventScroll: true });
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
  ui.d3 = on;
  map.set3d(on);
  renderNow();
}

async function toggleCompare(force) {
  const on = force ?? !ui.compare;
  if (on === ui.compare || !map) return;
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
  handle.setAttribute("aria-label", "Compare: drag or use arrow keys. Left side A, official products only; right side B, with TEPHRA's cautious area.");
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


function toggleLayers(force) {
  ui.layersOpen = force ?? !ui.layersOpen;
  if (ui.layersOpen && !ui.legendOpen) { ui.legendOpen = true; prefs.set("legendOpen", true); }
  if (ui.layersOpen) ui.levelsOpen = false;
  renderNow();
  if (ui.layersOpen) $("layers-pop").querySelector("input:not([disabled])")?.focus();
}

// Presentation layout for recording (key P or ?present=1): the legend folds to its button,
// the level column only shows while Hazard is on, the trace keeps two lines and the
// flights dock widens, so the story gets the map (14).
function setPresent(on) {
  ui.present = on;
  if (on) ui.legendOpen = false;
  else ui.legendOpen = prefs.get("legendOpen", window.innerWidth >= 1600);
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

function focusLevels() {
  if (window.innerWidth < 1360 && window.innerWidth > 600) { ui.levelsOpen = true; ui.layersOpen = false; renderNow(); }
  $("levels").querySelector('[data-thumb="max"]')?.focus();
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

async function openPolicy(opener) {
  let data = null;
  try {
    const res = await fetch("/api/policy", { headers: { Accept: "application/json" }, cache: "no-store" });
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

// ------------------------------------------------------------------ map wiring

function onFeature(hit, lngLat) {
  if (!D) return;
  const id = hit.layer.id;
  const p = hit.properties || {};
  if (id === "aircraft-icon" || id === "exposure-entry") {
    const f = D.aircraft.find((a) => a.properties.hex === p.hex);
    if (!f) return;
    map.popup(f.geometry.coordinates, popupContent("aircraft", f.properties, D, store));
  } else if (id === "reroute-line" || id === "reroute-wp") {
    map.popup(lngLat, reroutePopup(p, D));
  } else if (id.startsWith("volcano")) {
    map.popup(lngLat, popupContent("volcano", p, D, store));
  } else if (id.startsWith("official")) {
    map.popup(lngLat, popupContent("official", p, D, store));
  } else if (id.startsWith("tephra")) {
    map.popup(lngLat, popupContent("area", p, D, store));
  }
}

function flyToFlight(key) {
  const f = D?.aircraft.find((a) => String(a.id ?? a.properties.hex) === key || a.properties.hex === key);
  if (!f || !map) return;
  map.map.once("moveend", () => map.popup(f.geometry.coordinates, popupContent("aircraft", f.properties, D, store)));
  map.flyToFlight(f);
}

function startMap() {
  if (!window.maplibregl) {
    extra.basemap = "Map library did not load: the panels still work.";
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
      if (kind === "context") { renderCtx(); return; }
      scheduleRender();
    },
  });
  const canvas = map.map.getCanvas();
  canvas.setAttribute("aria-label", "Map. Arrow keys pan, plus and minus zoom.");
  canvas.id = "map-canvas";
  if (D) map.update(D);
}

// ------------------------------------------------------------------ events

document.addEventListener("click", (e) => {
  const skip = e.target.closest('a.skip-link[href="#map"]');
  if (skip) { e.preventDefault(); $("map-canvas")?.focus(); return; }
  const t = e.target.closest("button, [data-act], [data-ptab]");
  if (!t) return;
  const act = t.dataset.act;
  const tool = t.dataset.tool;
  if (tool === "frame") map?.frame({ animate: true });
  else if (tool === "3d") toggle3d();
  else if (tool === "compare") toggleCompare();
  else if (tool === "sat") setSat(SAT_CYCLE[(SAT_CYCLE.indexOf(ui.sat) + 1) % SAT_CYCLE.length]);
  else if (tool === "layers") toggleLayers();
  else if (tool === "levels") { ui.levelsOpen = !ui.levelsOpen; if (ui.levelsOpen) ui.layersOpen = false; renderNow(); }
  else if (t.id === "ai-chip") setRail("ai", true);
  else if (t.dataset.xtab) setRail(t.dataset.xtab, false);
  else if (t.id === "feeds-chip") openDialog("feeds", "Feed health", feedsDialog(D, store), t);
  else if (t.id === "about-btn") openDialog("about", "About TEPHRA and credits", aboutContent(), t);
  else if (t.id === "policy-btn") openPolicy(t);
  else if (t.dataset.ptab && t.closest("#ptabs")) {
    ui.ptab = t.dataset.ptab;
    for (const b of document.querySelectorAll("#ptabs button")) b.setAttribute("aria-pressed", b === t ? "true" : "false");
    renderNow();
  } else if (t.dataset.region) chooseRegion(t.dataset.region);
  else if (t.dataset.flight) flyToFlight(t.dataset.flight);
  else if (t.getAttribute("role") === "tab" && t.dataset.vid) select(t.dataset.vid);
  else if (act === "select" && t.dataset.vid) { map?.closePopup(); select(t.dataset.vid); }
  else if (act === "legend") { ui.legendOpen = !ui.legendOpen; prefs.set("legendOpen", ui.legendOpen); renderNow(); }
  else if (act === "layers-close") { toggleLayers(false); document.querySelector('[data-tool="layers"]').focus(); }
  else if (act === "trace-expand") { ui.traceExpanded = !ui.traceExpanded; renderNow(); }
  else if (act === "trace-scope") { ui.traceScope = t.dataset.scope; renderNow(); }
  else if (act === "harmless") { ui.harmlessOpen = !ui.harmlessOpen; renderNow(); }
  else if (act === "frame") map?.frame({ animate: true });
  else if (act === "raw") openSources(t.dataset.kind, t);
  else if (act === "retry") { extra.error = "Retrying…"; renderNow(); load(); }
  else if (act === "level-preset") levelPreset(t.dataset.preset);
  else if (act === "steps") setSteps(t.dataset.steps);
  else if (act === "tl-mark") onTimelineMark(t);
  else if (act === "dlg-close") $("dlg").close();
});

function onTimelineMark(t) {
  const kind = t.dataset.kind;
  if (kind === "SIGMET" || kind === "VAA" || kind === "VONA") {
    const btn = document.querySelector(`[data-act="raw"][data-kind="${kind}"]`);
    btn?.closest(".sec")?.scrollIntoView({ block: "start", behavior: reducedMotion() ? "auto" : "smooth" });
    const col = [...document.querySelectorAll(".cmp__colhead")].find((h) => h.querySelector(".cmp__kind")?.textContent.startsWith(kind));
    if (col) { col.classList.remove("is-flash"); void col.offsetWidth; col.classList.add("is-flash"); }
  } else if (kind === "decision") {
    $("decisions")?.scrollIntoView({ block: "start", behavior: reducedMotion() ? "auto" : "smooth" });
  } else if (kind === "dis") {
    document.querySelector(".dis")?.scrollIntoView({ block: "start", behavior: reducedMotion() ? "auto" : "smooth" });
  }
  map?.frame({ animate: true });
}

document.addEventListener("change", (e) => {
  const t = e.target;
  if (t.dataset.layer) setLayer(t.dataset.layer, t.checked);
  else if (t.dataset.radio === "sat") setSat(t.value);
  else if (t.dataset.radio === "steps") setSteps(t.value);
  else if (t.dataset.act === "shortcuts-toggle") { ui.shortcuts = t.checked; prefs.set("shortcuts", ui.shortcuts); }
  else if (t.id === "region-select") chooseRegion(t.value);
});

document.addEventListener("toggle", (e) => {
  if (e.target.matches?.(".area__read")) ui.readOpen = e.target.open;
}, true);

// ---- keyboard: tabs, timeline markers, level thumbs, shortcuts

document.addEventListener("keydown", (e) => {
  const t = e.target;
  if (t.matches?.(".vtab") && (e.key === "ArrowRight" || e.key === "ArrowLeft" || e.key === "Home" || e.key === "End")) {
    const tabs = [...document.querySelectorAll(".vtab")];
    const i = tabs.indexOf(t);
    const j = e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1 : (i + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    tabs.forEach((x, k) => { x.tabIndex = k === j ? 0 : -1; });
    tabs[j].focus();
    e.preventDefault();
    return;
  }
  if (t.matches?.(".xtab") && (e.key === "ArrowRight" || e.key === "ArrowLeft" || e.key === "Home" || e.key === "End")) {
    const tabs = [...document.querySelectorAll(".xtab")];
    const i = tabs.indexOf(t);
    const j = e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1 : (i + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    e.preventDefault();
    setRail(tabs[j].dataset.xtab, false);
    document.getElementById(`xtab-${tabs[j].dataset.xtab}`)?.focus();
    return;
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
  if (t.dataset?.thumb) { thumbKey(e, t.dataset.thumb); return; }
  shortcut(e);
});

function thumbKey(e, which) {
  const step = { ArrowUp: 1000, ArrowDown: -1000, PageUp: 5000, PageDown: -5000 }[e.key];
  let v = ui.level[which];
  if (step) v += step;
  else if (e.key === "Home") v = 0;
  else if (e.key === "End") v = LEVEL_MAX;
  else return;
  e.preventDefault();
  setThumb(which, v);
}

function setThumb(which, ft) {
  const v = Math.round(Math.max(0, Math.min(LEVEL_MAX, ft)) / 1000) * 1000;
  if (which === "max") ui.level = { min: ui.level.min, max: Math.max(v, ui.level.min + 1000) };
  else ui.level = { min: Math.min(v, ui.level.max - 1000), max: ui.level.max };
  renderNow();
}

// pointer drag on the level track (8.4)
let drag = null;
$("levels").addEventListener("pointerdown", (e) => {
  const track = e.target.closest(".levels__track");
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
  else if (k === "l" || k === "L") toggleLayers();
  else if (k === "t" || k === "T") { ui.traceExpanded = !ui.traceExpanded; renderNow(); }
  else if (k === "h" || k === "H") focusLevels();
  else if (k === "p" || k === "P") setPresent(!ui.present);
  else if (k === "?") openDialog("help", "Keyboard shortcuts", helpContent(ui.shortcuts), document.activeElement);
  else handled = false;
  if (handled) e.preventDefault();
}

function escape(e) {
  if ($("dlg").open) return; // the dialog closes itself
  if (map?.closePopup()) { e.preventDefault(); return; }
  if (ui.layersOpen) { toggleLayers(false); document.querySelector('[data-tool="layers"]').focus(); e.preventDefault(); return; }
  if (ui.levelsOpen) { ui.levelsOpen = false; renderNow(); e.preventDefault(); return; }
  if (ui.traceExpanded) { ui.traceExpanded = false; renderNow(); e.preventDefault(); return; }
  if (ui.compare) { toggleCompare(false); e.preventDefault(); return; }
  if (ui.d3) { toggle3d(false); e.preventDefault(); }
}

// ------------------------------------------------------------------ clocks and start

setInterval(() => { if (D) { D.now = now(); renderClock(D, conn); } }, 1000);
setInterval(() => { if (store.state) renderNow(); }, 15000);
window.addEventListener("resize", () => scheduleRender());
window.matchMedia("(prefers-reduced-motion: reduce)").addEventListener?.("change", () => scheduleRender());

renderShell();
inlineSprite().then(() => { if (store.state) renderNow(); else renderShell(); });
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", startMap, { once: true });
else startMap();
load();
