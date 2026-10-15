// TEPHRA Connect (UI-DESIGN 7.24): feed your airline's aircraft positions in and watch TEPHRA
// check them against the ash. The page starts complete from GET /api/connect/live (every pushed
// flight on the map now, each source's flow, the newest pushes), then follows the `push` event,
// refreshing the flows every 10 s. The feed card has three ways in: upload or paste a file, push
// from your own system with a key, or the sample feed of real flights. Every string goes in
// through el() (textContent).

import { el, icon } from "./wall/util.js";
import { STYLE_URL, nightBasemap, nightColours, symbolColours } from "./wall/basemap.js";
import { addImages } from "./wall/images.js";
import { shouldReopen, STREAM_RETRY_MS } from "./wall/stream.js";
import { setFeatures, applyFeatureNav } from "./wall/features.js";

const $ = (id) => document.getElementById(id);
const FEED_NAME = { sigmet: "VA SIGMETs", vaac_darwin: "Darwin VAAC", vaac_tokyo: "Tokyo VAAC", vona: "VONA", jma_volcano: "JMA notices", adsb: "ADS-B", winds: "Winds", frames: "Satellite", hsd: "Himawari raw", taf: "TAF", metar: "METAR" };
const FEED_ICON = { sigmet: "i-alert", vaac_darwin: "i-file", vaac_tokyo: "i-file", vona: "i-eruption", jma_volcano: "i-eruption", adsb: "i-aircraft", winds: "i-wind", frames: "i-satellite", hsd: "i-satellite", taf: "i-airport", metar: "i-airport" };
const TONE = { OK: "ok", STALE: "stale", ERROR: "error" };
const GLIDE_MS = 5000;
const KEEP_MS = 30_000; // a flight with no update this long leaves the page's map
const reduced = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const app = {
  me: null, state: null, format: null, example: null, live: null, connections: [],
  tab: "upload", key: null, lang: "curl", retime: true, paste: false, result: null, sending: false,
  dots: new Map(), // hex -> { from, to, t0, inAsh, cs, trk, seen, trail }
  framed: false,
};

async function call(path, { method = "GET", body } = {}) {
  try {
    const res = await fetch(path, {
      method, credentials: "same-origin", cache: "no-store",
      headers: { Accept: "application/json", "X-Tephra-Desk": "1", ...(body ? { "Content-Type": "application/json" } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => null);
    return { ok: res.ok, status: res.status, data };
  } catch {
    return { ok: false, status: 0, data: null };
  }
}

// --- the map --------------------------------------------------------------------------------------
let map = null, ready = false, raf = 0;
const fc = (features) => ({ type: "FeatureCollection", features });

function buildMap() {
  if (map || !window.maplibregl) return;
  const r = app.state?.region;
  map = new window.maplibregl.Map({
    container: "cx-map", style: STYLE_URL, center: r ? [r.center_lon, r.center_lat] : [110, -6.5], zoom: 4.6,
    attributionControl: false, dragRotate: false, pitchWithRotate: false, renderWorldCopies: false, fadeDuration: 0, minZoom: 2, maxZoom: 10,
  });
  map.touchZoomRotate.disableRotation();
  map.addControl(new window.maplibregl.AttributionControl({ compact: true }), "bottom-right");
  map.on("styleimagemissing", (e) => { if (!map.hasImage(e.id)) map.addImage(e.id, { width: 1, height: 1, data: new Uint8Array(4) }); });
  map.on("style.load", () => {
    const C = symbolColours();
    nightBasemap(map, nightColours(), { places: false });
    addImages(map, C);
    for (const id of ["cones", "volcanoes", "trails", "dots", "plans", "reports"]) map.addSource(id, { type: "geojson", data: fc([]) });
    const official = ["==", ["get", "mode"], "OFFICIAL"];
    const cyan = "#5eead4";
    map.addLayer({ id: "cone-fill", type: "fill", source: "cones", filter: official, paint: { "fill-color": C.official, "fill-opacity": 0.1 } });
    map.addLayer({ id: "cone-line", type: "line", source: "cones", filter: official, paint: { "line-color": C.official, "line-opacity": 0.75, "line-width": 1.5 } });
    map.addLayer({ id: "tephra-line", type: "line", source: "cones", filter: ["!", official], paint: { "line-color": C.tephra, "line-opacity": 0.8, "line-width": 1.4, "line-dasharray": [4, 3] } });
    // the airline's flight plans: origin to destination, red where an airport on it is closed
    map.addLayer({ id: "plan-line", type: "line", source: "plans", layout: { "line-cap": "round" }, paint: { "line-color": ["case", ["get", "closed"], C.serious || "#ff7a6e", "#8b9bff"], "line-opacity": ["case", ["get", "closed"], 0.85, 0.45], "line-width": ["case", ["get", "closed"], 2, 1.2], "line-dasharray": [2, 2] } });
    map.addLayer({ id: "plan-end", type: "circle", source: "plans", filter: ["==", ["geometry-type"], "Point"], paint: { "circle-radius": 3.5, "circle-color": ["case", ["get", "closed"], C.serious || "#ff7a6e", "#8b9bff"], "circle-stroke-color": "#04121a", "circle-stroke-width": 1 } });
    // pilot reports: their caution areas and pins
    map.addLayer({ id: "report-area", type: "fill", source: "reports", filter: ["==", ["get", "feature"], "area"], paint: { "fill-color": C.crew || "#e8dcc6", "fill-opacity": 0.12 } });
    map.addLayer({ id: "report-edge", type: "line", source: "reports", filter: ["==", ["get", "feature"], "area"], paint: { "line-color": C.crew || "#e8dcc6", "line-width": 1.6, "line-dasharray": [5, 3] } });
    map.addLayer({ id: "report-pin", type: "symbol", source: "reports", filter: ["==", ["get", "feature"], "pin"], layout: { "icon-image": "crew-pin", "icon-anchor": "bottom", "icon-size": 0.9, "icon-allow-overlap": true } });
    map.addLayer({ id: "volcanoes", type: "symbol", source: "volcanoes", layout: { "icon-image": ["concat", "volcano-", ["get", "code"]], "icon-size": 0.7, "icon-allow-overlap": true } });
    map.addLayer({ id: "trails", type: "line", source: "trails", layout: { "line-cap": "round" }, paint: { "line-color": ["case", ["get", "inAsh"], C.tephra, cyan], "line-opacity": 0.35, "line-width": 1.5 } });
    map.addLayer({ id: "dot-glow", type: "circle", source: "dots", paint: { "circle-radius": 13, "circle-blur": 0.9, "circle-color": ["case", ["get", "inAsh"], C.tephra, cyan], "circle-opacity": 0.4 } });
    map.addLayer({ id: "dot-plane", type: "symbol", source: "dots", layout: { "icon-image": "ac-sdf", "icon-size": ["case", ["get", "inAsh"], 0.62, 0.5], "icon-rotate": ["get", "trk"], "icon-rotation-alignment": "map", "icon-allow-overlap": true, "icon-ignore-placement": true }, paint: { "icon-color": ["case", ["get", "inAsh"], C.tephra, "#e6fffb"], "icon-halo-color": "#04121a", "icon-halo-width": 1 } });
    map.addLayer({ id: "dot-label", type: "symbol", source: "dots", minzoom: 5.5, layout: { "text-field": ["get", "cs"], "text-font": ["Noto Sans Regular"], "text-size": 12, "text-offset": [0, 1.2], "text-anchor": "top", "text-optional": true }, paint: { "text-color": ["case", ["get", "inAsh"], C.tephra, "#bdf5ee"], "text-halo-color": "#05070a", "text-halo-width": 1.5 } });
    ready = true;
    drawPlansAndReports();
    loadWall();
    frameTraffic();
    paint();
  });
}

async function loadWall() {
  const res = await call("/api/wall");
  const snap = res.ok ? res.data?.snapshot : null;
  if (!snap || !ready) return;
  setCones(snap.cones);
  const codes = new Set(["RED", "ORANGE", "YELLOW", "GREEN"]);
  map.getSource("volcanoes").setData(fc((snap.volcanoes?.features || []).filter((f) => f.properties?.active)
    .map((f) => ({ ...f, properties: { code: codes.has(f.properties.color_code) ? f.properties.color_code : "UNKNOWN" } }))));
}

function setCones(layer) {
  if (!ready || !layer?.features) return;
  map.getSource("cones").setData(fc(layer.features.filter((f) => f.properties?.part === "cone")));
}

function drawPlansAndReports() {
  if (!ready || !app.live) return;
  const plans = (app.live.plans || []).flatMap((p) => [
    { type: "Feature", properties: { flight: p.flight, closed: p.closed }, geometry: { type: "LineString", coordinates: p.coordinates } },
    ...[p.coordinates[0], p.coordinates[p.coordinates.length - 1]].map((c) => ({ type: "Feature", properties: { closed: p.closed }, geometry: { type: "Point", coordinates: c } })),
  ]);
  map.getSource("plans").setData(fc(plans));
  map.getSource("reports").setData(app.live.reports?.features ? app.live.reports : fc([]));
}

function frameTraffic() {
  if (app.framed || !ready || !app.dots.size) return;
  app.framed = true;
  const pts = [...app.dots.values()].map((d) => d.to);
  const lons = pts.map((x) => x[0]), lats = pts.map((x) => x[1]);
  map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: { top: 120, bottom: 40, left: 40, right: 40 }, maxZoom: 6.5, duration: reduced() ? 0 : 1200 });
}

function paint() {
  raf = 0;
  if (!ready) return;
  const now = performance.now();
  let moving = false;
  const dots = [], trails = [];
  for (const [hex, d] of app.dots) {
    const u = reduced() ? 1 : Math.min(1, (now - d.t0) / GLIDE_MS);
    if (u < 1) moving = true;
    const at = [d.from[0] + (d.to[0] - d.from[0]) * u, d.from[1] + (d.to[1] - d.from[1]) * u];
    d.now = at;
    dots.push({ type: "Feature", properties: { hex, cs: d.cs || hex, inAsh: d.inAsh, trk: d.trk ?? 0 }, geometry: { type: "Point", coordinates: at } });
    if (d.trail.length) trails.push({ type: "Feature", properties: { inAsh: d.inAsh }, geometry: { type: "LineString", coordinates: [...d.trail, at] } });
  }
  map.getSource("dots").setData(fc(dots));
  map.getSource("trails").setData(fc(trails));
  if (moving) raf = requestAnimationFrame(paint);
}
const kick = () => { if (ready && !raf) raf = requestAnimationFrame(paint); };

function takeDots(list, { glide }) {
  const real = Date.now();
  for (const dot of list || []) {
    const to = [dot.lon, dot.lat];
    const held = app.dots.get(dot.hex);
    const from = glide && held ? held.now || held.to : to;
    const trail = held ? [...held.trail, held.to].slice(-6) : [];
    app.dots.set(dot.hex, { from, to, t0: performance.now(), inAsh: dot.in_ash, cs: dot.callsign, trk: dot.track_deg, seen: real, trail });
  }
  for (const [hex, d] of app.dots) if (real - d.seen > KEEP_MS) app.dots.delete(hex);
}

// --- numbers, sources, ticker ---------------------------------------------------------------------
function bump(node, value) {
  const text = String(value);
  if (node.textContent === text) return;
  node.textContent = text;
  node.classList.remove("is-bump");
  void node.offsetWidth;
  node.classList.add("is-bump");
}

function renderKpis() {
  const rate = (app.live?.flows || []).reduce((a, f) => a + f.per_min, 0);
  bump($("k-rate"), rate.toLocaleString("en"));
  bump($("k-live"), app.dots.size);
  bump($("k-ash"), [...app.dots.values()].filter((d) => d.inAsh).length);
  $("cx-empty").hidden = app.dots.size > 0;
}

function spark(values) {
  const top = Math.max(1, ...values);
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * 90},${26 - (v / top) * 22}`);
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("class", "cx-spark");
  svg.setAttribute("viewBox", "0 0 90 28");
  svg.setAttribute("aria-hidden", "true");
  const area = document.createElementNS(ns, "polygon");
  area.setAttribute("points", `0,28 ${pts.join(" ")} 90,28`);
  const line = document.createElementNS(ns, "polyline");
  line.setAttribute("points", pts.join(" "));
  svg.append(area, line);
  return svg;
}

function renderFlows() {
  const flows = app.live?.flows || [];
  const list = $("cx-flows");
  if (!flows.length) {
    list.replaceChildren(el("li", { class: "cx-chip" }, icon("i-network"), el("span", { text: "No airline data yet" })));
    return;
  }
  list.replaceChildren(...flows.map((f) => el("li", { class: "cx-flow", dataset: { on: f.per_min ? "1" : "0" } },
    el("span", { class: "cx-flow__ic" }, icon(f.sample ? "i-play" : "i-network")),
    el("span", { class: "cx-flow__t" }, el("b", { text: f.name }), el("span", { text: f.per_min ? "flowing" : "quiet" })),
    spark(f.spark),
    el("span", { class: "cx-flow__n" }, String(f.per_min), el("small", { text: "/ min" })))));
}

function renderPublic() {
  const feeds = (app.state?.feeds || []).filter((f) => FEED_NAME[f.feed]);
  $("cx-public").replaceChildren(...feeds.map((f) => el("li", { class: "cx-chip", dataset: { tone: TONE[f.status] || "off" }, title: f.last_error || `${f.record_count || 0} records` },
    el("i"), icon(FEED_ICON[f.feed] || "i-live"), el("span", { text: FEED_NAME[f.feed] }), f.record_count ? el("b", { text: f.record_count.toLocaleString("en") }) : null)));
  const replay = app.state?.mode === "REPLAY";
  $("cx-mode").hidden = !replay;
  $("cx-mode").textContent = replay ? "REPLAY clock" : "";
}

function tick(p) {
  return el("li", { class: `cx-tick${p.accepted ? "" : " cx-tick--bad"}`, title: p.reasons?.join(" · ") || null },
    el("b", { text: p.name }),
    el("span", {}, el("span", { class: "ok", text: `+${p.accepted}` }), " positions"),
    p.in_ash ? el("span", {}, el("span", { class: "ash", text: String(p.in_ash) }), " in the ash") : el("span"),
    p.plans ? el("span", {}, el("span", { class: "plan", text: String(p.plans) }), " plans") : null,
    p.reports ? el("span", {}, el("span", { class: "rep", text: String(p.reports) }), " pilot reports") : null,
    p.rejected ? el("span", {}, el("span", { class: "bad", text: String(p.rejected) }), " refused") : null);
}

function renderMe() {
  const box = $("cx-me");
  // the empty map's call to action: the sample feed is a dispatcher's to start
  $("cx-empty-try").hidden = !app.me;
  $("cx-empty-lock").hidden = Boolean(app.me);
  if (!app.me) { box.replaceChildren(); return; }
  const initials = app.me.name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
  box.replaceChildren(el("span", { class: "cx-me__dot", "aria-hidden": "true", text: initials }), el("span", { text: app.me.name }));
}

// --- the feed card --------------------------------------------------------------------------------
function signInForm(why) {
  const name = el("input", { class: "cx-in", autocomplete: "username", required: true, minlength: "2", maxlength: "32" });
  const pin = el("input", { class: "cx-in", type: "password", inputmode: "numeric", autocomplete: "current-password", required: true });
  const err = el("p", { class: "cx-err", hidden: true });
  const go = el("button", { type: "submit", class: "cx-btn cx-btn--glow cx-btn--block", text: "Sign in" });
  const form = el("form", { class: "cx-form" },
    el("p", { class: "cx-lock" }, icon("i-lock"), el("span", { text: why })),
    el("label", {}, "Name or initials", name), el("label", {}, "Desk PIN", pin), err, go);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    go.disabled = true;
    const res = await call("/api/desk/login", { method: "POST", body: { name: name.value.trim(), pin: pin.value } });
    go.disabled = false;
    if (!res.ok) { err.hidden = false; err.textContent = res.status === 401 ? "That PIN is not right." : res.status === 429 ? "Too many tries. Wait a minute." : "Sign-in failed."; return; }
    app.me = res.data;
    renderMe();
    await loadConnections();
    renderPanel();
  });
  return form;
}

function renderPanel() {
  for (const b of document.querySelectorAll(".cx-seg__b")) b.setAttribute("aria-selected", String(b.dataset.tab === app.tab));
  const panel = $("cx-panel");
  const kids = app.tab === "upload" ? uploadPanel() : app.tab === "api" ? apiPanel() : samplePanel();
  panel.replaceChildren(...kids.filter(Boolean));
}

function resultBlock() {
  const r = app.result;
  if (!r) return null;
  if (r.error) return el("p", { class: "cx-err", text: r.error });
  const reasons = [...new Set(r.rejected.map((x) => `${x.section.replace("_", " ")} ${x.index + 1}: ${x.reason}`))].slice(0, 4);
  const row = (ic, n, what, goes, tone) => el("li", { class: `cx-went__r cx-went__r--${tone}` }, icon(ic), el("b", { text: String(n) }), el("span", { text: what }), el("span", { class: "cx-went__go", text: goes }));
  return el("div", { class: "cx-form" },
    el("p", { class: "cx-cap", text: "Where it went" }),
    el("ul", { class: "cx-went" },
      row("i-aircraft", r.accepted, "positions", r.in_ash.length ? `${r.in_ash.length} in the ash` : "checked", r.in_ash.length ? "ash" : "ok"),
      row("i-route", r.plans_taken, "flight plans", r.closed_hits.length ? `${r.closed_hits.length} via a closed airport` : "routes on the maps", r.closed_hits.length ? "bad" : "ok"),
      row("i-pin", r.reports_taken, "pilot reports", r.reports_taken ? "caution areas" : "–", "rep"),
      r.rejected.length ? row("i-x", r.rejected.length, "refused", "see below", "bad") : null),
    reasons.length ? el("ul", { class: "cx-reasons" }, ...reasons.map((t) => el("li", { text: t }))) : null);
}

function uploadPanel() {
  if (!app.me) return [signInForm("Sign in to send a file")];
  const file = el("input", { type: "file", accept: ".json,application/json", hidden: true });
  const drop = el("div", { class: "cx-drop", tabindex: "0", role: "button", "aria-label": "Choose or drop a JSON file of positions" },
    el("span", { class: "cx-drop__ic" }, icon("i-file")), el("b", { text: app.sending ? "Sending…" : "Drop a positions file" }), el("span", { text: "positions · flight plans · pilot reports" }), file);
  drop.addEventListener("click", () => file.click());
  drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); file.click(); } });
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("is-over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("is-over"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("is-over"); const f = e.dataTransfer?.files?.[0]; if (f) f.text().then(send); });
  file.addEventListener("change", () => { const f = file.files?.[0]; if (f) f.text().then(send); });
  const sw = el("button", { type: "button", role: "switch", class: "cx-switch", "aria-checked": String(app.retime), "aria-label": "Use TEPHRA's clock for the times" }, el("i"));
  sw.addEventListener("click", () => { app.retime = !app.retime; sw.setAttribute("aria-checked", String(app.retime)); });
  const kids = [
    drop,
    el("div", { class: "cx-toggle", title: "Stamp every position with TEPHRA's clock now: for a file whose times are old, such as the sample" }, el("span", { text: "Use TEPHRA's clock for the times" }), sw),
    el("div", { class: "cx-row2" },
      el("a", { class: "cx-btn cx-btn--soft", href: "/api/connect/sample.json", download: "" }, icon("i-file"), el("span", { text: "Sample file" })),
      el("button", { type: "button", class: "cx-btn cx-btn--soft", dataset: { act: "paste" } }, icon("i-clipboard"), el("span", { text: app.paste ? "Hide paste" : "Paste JSON" }))),
  ];
  if (app.paste) {
    const area = el("textarea", { class: "cx-paste", spellcheck: "false", placeholder: '{"format": "tephra.airline/1", "positions": […], "flight_plans": […], "pilot_reports": […]}' });
    const go = el("button", { type: "button", class: "cx-btn cx-btn--glow cx-btn--block", text: "Send" });
    go.addEventListener("click", () => send(area.value));
    kids.push(area, go);
  }
  kids.push(resultBlock());
  return kids;
}

async function send(text) {
  let body;
  try {
    const parsed = JSON.parse(text);
    body = Array.isArray(parsed) ? { format: "tephra.positions/1", positions: parsed } : parsed;
  } catch {
    app.result = { error: "That is not JSON." };
    renderPanel();
    return;
  }
  app.sending = true;
  renderPanel();
  const res = await call("/api/desk/upload", { method: "POST", body: { ...body, retime: app.retime } });
  app.sending = false;
  app.result = res.ok ? res.data : { error: res.status === 422 ? "The file is not a TEPHRA push (tephra.airline/1 with positions, flight_plans or pilot_reports)." : res.status === 401 ? "Your session has ended. Sign in again." : `Not sent (HTTP ${res.status}).` };
  renderPanel();
}

function apiPanel() {
  const S = app.format?.schema?.properties || {};
  const section = (key, title, ex) => {
    const item = S[key]?.items || {};
    const props = item.properties || {};
    const required = new Set(item.required || []);
    return [el("p", { class: "cx-cap", text: title }), el("div", { class: "cx-record" }, ...Object.keys(props).map((k) => el("span", { class: `cx-field${required.has(k) ? "" : " cx-field--opt"}`, title: props[k].description || null },
      el("b", { text: k }), el("span", { text: ex?.[k] == null ? "…" : Array.isArray(ex[k]) ? ex[k].join(", ") : String(ex[k]).replace(/\.\d{3}Z$/, "Z") }))))];
  };
  const kids = [...section("positions", "positions[ ]", app.example?.positions?.[0]), ...section("flight_plans", "flight_plans[ ]", app.example?.flight_plans?.[0]), ...section("pilot_reports", "pilot_reports[ ]", app.example?.pilot_reports?.[0]),
    el("div", { class: "cx-row2" }, el("a", { class: "cx-btn cx-btn--soft", href: "/api/connect/schema.json", download: "" }, icon("i-code"), el("span", { text: "JSON Schema" })))];
  if (!app.me) return [...kids, signInForm("Sign in to get a key")];
  if (app.key) {
    const copy = el("button", { type: "button", class: "cx-copy" }, icon("i-clipboard"), el("span", { text: "Copy" }));
    copy.addEventListener("click", () => navigator.clipboard?.writeText(app.key).then(() => { copy.lastChild.textContent = "Copied"; }));
    kids.push(el("p", { class: "cx-cap", text: "Your key" }), el("div", { class: "cx-key" }, el("code", { text: app.key }), copy), el("p", { class: "cx-note", text: "Shown once. TEPHRA keeps only its fingerprint." }));
  } else {
    const name = el("input", { class: "cx-in", placeholder: "Name, e.g. RFA operations", minlength: "2", maxlength: "48", required: true });
    const go = el("button", { type: "submit", class: "cx-btn cx-btn--glow", text: "Get a key" });
    const form = el("form", { class: "cx-row2" }, name, go);
    name.style.flex = "1";
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      go.disabled = true;
      const res = await call("/api/desk/connections", { method: "POST", body: { name: name.value.trim() } });
      go.disabled = false;
      if (!res.ok) return;
      app.key = res.data.key;
      await loadConnections();
      renderPanel();
    });
    kids.push(el("p", { class: "cx-cap", text: "Get a key" }), form);
  }
  const url = `${location.origin}/api/push/positions`;
  const key = app.key || "tph_your_key";
  const f = "positions.json";
  const code = {
    curl: `curl -X POST ${url} \\\n  -H "Authorization: Bearer ${key}" \\\n  -H "Content-Type: application/json" \\\n  -d @${f}`,
    python: `import json, urllib.request\nreq = urllib.request.Request(\n    "${url}",\n    data=open("${f}", "rb").read(),\n    headers={"Authorization": "Bearer ${key}",\n             "Content-Type": "application/json"})\nprint(urllib.request.urlopen(req).read())`,
    js: `await fetch("${url}", {\n  method: "POST",\n  headers: { Authorization: "Bearer ${key}",\n             "Content-Type": "application/json" },\n  body: JSON.stringify(batch),\n});`,
  }[app.lang];
  const pre = el("pre", { class: "cx-pre", text: code });
  const copy = el("button", { type: "button", class: "cx-copy" }, icon("i-clipboard"), el("span", { text: "Copy" }));
  copy.addEventListener("click", () => navigator.clipboard?.writeText(code).then(() => { copy.lastChild.textContent = "Copied"; }));
  kids.push(el("p", { class: "cx-cap", text: "Push" }), el("div", { class: "cx-code" },
    el("div", { class: "cx-tabs", role: "tablist", "aria-label": "Language" },
      ...[["curl", "curl"], ["python", "Python"], ["js", "JavaScript"]].map(([k, t]) => el("button", { type: "button", role: "tab", class: "cx-tab", "aria-selected": String(app.lang === k), dataset: { lang: k }, text: t })), copy),
    pre));
  const mine = app.connections.filter((c) => !c.sample && !c.revoked_at);
  if (mine.length) {
    kids.push(el("p", { class: "cx-cap", text: "Your connections" }), el("div", { class: "cx-chips" }, ...mine.map((c) => el("span", { class: "cx-chip", dataset: { tone: c.last_push_at ? "ok" : "off" } },
      el("i"), el("span", { text: c.name }), el("b", { text: c.accepted.toLocaleString("en") }),
      el("button", { type: "button", class: "cx-link", dataset: { act: "revoke", id: c.id }, "aria-label": `Revoke ${c.name}`, text: "Revoke" })))));
  }
  return kids;
}

function samplePanel() {
  const on = Boolean(app.live?.sample_running);
  const flow = (app.live?.flows || []).find((f) => f.sample);
  const kids = [el("div", { class: "cx-sample" },
    el("button", { type: "button", class: `cx-sample__big${on ? " is-on" : ""}`, dataset: { act: "sample" }, "aria-pressed": String(on), "aria-label": on ? "Stop the sample feed" : "Start the sample feed", disabled: app.me ? null : true }, icon(on ? "i-pause" : "i-play")),
    el("b", { text: on ? "Sample feed running" : "Sample airline feed" }),
    el("p", { text: "Real flights fly their own tracks, with their flight plans, and crews report the ash they meet." }),
    el("div", { class: "cx-facts" },
      el("div", {}, el("b", { text: on ? String(flow?.per_min ?? 0) : "–" }), el("span", { text: "per min" }))))];
  if (!app.me) kids.push(signInForm("Sign in to start it"));
  return kids;
}

async function toggleSample() {
  if (!app.me) return;
  const on = !app.live?.sample_running;
  const res = await call("/api/desk/sample-feed", { method: "POST", body: { on } });
  if (res.ok) app.connections = res.data.connections;
  await loadLive();
}

function revoke(id) {
  const c = app.connections.find((x) => x.id === id);
  if (!c) return;
  const d = $("cx-dlg");
  const go = el("button", { type: "button", class: "cx-btn cx-btn--danger", text: "Revoke" });
  go.addEventListener("click", async () => {
    go.disabled = true;
    await call(`/api/desk/connections/${encodeURIComponent(id)}/revoke`, { method: "POST", body: {} });
    d.close();
    await loadConnections();
    renderPanel();
  });
  d.replaceChildren(el("div", { class: "cx-dlg__in" }, el("h2", { id: "cx-dlg-t", class: "cx-dlg__t", text: `Revoke ${c.name}?` }),
    el("p", { class: "cx-note", text: "Its key stops working at once." }),
    el("div", { class: "cx-dlg__acts" }, el("button", { type: "button", class: "cx-btn cx-btn--soft", dataset: { act: "close" }, text: "Cancel" }), go)));
  d.showModal();
}

// --- loading --------------------------------------------------------------------------------------
async function loadConnections() {
  if (!app.me) return;
  const res = await call("/api/desk/connections");
  if (res.ok) app.connections = res.data.connections;
}

async function loadLive({ first = false } = {}) {
  const res = await call("/api/connect/live");
  if (!res.ok) return;
  app.live = res.data;
  if (first) {
    takeDots(res.data.dots, { glide: false });
    $("cx-ticker").replaceChildren(...res.data.recent.map(tick));
    frameTraffic();
    kick();
  }
  renderKpis();
  renderFlows();
  renderWhere();
  drawPlansAndReports();
  if (app.tab === "sample") renderPanel();
}

// Where your data goes: each section, what it became, counted live.
function renderWhere() {
  const live = app.live || {};
  const dots = [...app.dots.values()];
  const plans = live.plans || [];
  const areas = (live.reports?.features || []).filter((f) => f.properties?.feature === "area");
  const flagged = (live.reports?.features || []).filter((f) => f.properties?.feature === "path").length;
  const card = (ic, n, what, goes, hot) => el("li", { class: `cx-where__c${hot ? " is-hot" : ""}` },
    el("span", { class: "cx-where__ic" }, icon(ic)),
    el("span", { class: "cx-where__n" }, el("b", { text: String(n) }), el("span", { text: what })),
    el("span", { class: "cx-where__arrow", "aria-hidden": "true", text: "→" }),
    el("span", { class: "cx-where__go", text: goes }));
  const inAsh = dots.filter((d) => d.inAsh).length;
  const closed = plans.filter((p) => p.closed).length;
  $("cx-where").replaceChildren(
    card("i-aircraft", dots.length, "positions", inAsh ? `${inAsh} in the ash · drafts on the Desk` : "checked against the ash", inAsh > 0),
    card("i-route", plans.length, "flight plans", closed ? `${closed} to or from a closed airport` : "routes on the maps", closed > 0),
    card("i-pin", areas.length, "pilot reports", flagged ? `${flagged} flights flagged · caution areas` : "caution areas on the maps", areas.length > 0));
}

function onPush(p) {
  takeDots(p.dots, { glide: true });
  if (p.plans || p.reports) loadLive();
  const list = $("cx-ticker");
  list.prepend(tick(p));
  while (list.children.length > 14) list.lastElementChild.remove();
  frameTraffic();
  renderKpis();
  renderWhere();
  kick();
}

document.addEventListener("click", (e) => {
  const t = e.target.closest("button, [data-act]");
  if (!t) return;
  const act = t.dataset.act;
  if (t.dataset.tab) { app.tab = t.dataset.tab; app.result = null; renderPanel(); }
  else if (t.dataset.lang) { app.lang = t.dataset.lang; renderPanel(); }
  else if (act === "paste") { app.paste = !app.paste; renderPanel(); }
  else if (act === "sample") toggleSample();
  else if (act === "revoke") revoke(t.dataset.id);
  else if (act === "close") $("cx-dlg").close();
});

function openStream() {
  const source = new EventSource("/api/events");
  source.addEventListener("push", (e) => { try { onPush(JSON.parse(e.data)); } catch { /* a bad frame is skipped */ } });
  source.addEventListener("cones", (e) => { try { setCones(JSON.parse(e.data)); } catch { /* skipped */ } });
  source.addEventListener("state", (e) => { try { app.state = JSON.parse(e.data); setFeatures(app.state.features); applyFeatureNav(); renderPublic(); } catch { /* skipped */ } });
  // a source the browser gave up on (an HTTP error, EventSource.CLOSED) is replaced after a wait
  source.onerror = () => { if (shouldReopen(source.readyState)) { source.close(); setTimeout(openStream, STREAM_RETRY_MS); } };
}

async function boot() {
  $("cx-flows").replaceChildren(el("li", { class: "cx-skel" }), el("li", { class: "cx-skel" }));
  const [state, me, format, sample] = await Promise.all([call("/api/state"), call("/api/desk/me"), call("/api/connect/format"), call("/api/connect/sample.json")]);
  app.state = state.ok ? state.data : null;
  setFeatures(app.state?.features);
  applyFeatureNav();
  app.me = me.ok ? me.data : null;
  app.format = format.ok ? format.data : null;
  app.example = sample.ok ? sample.data : null;
  await Promise.all([loadConnections(), loadLive({ first: true })]);
  document.body.classList.remove("is-loading");
  renderPublic();
  renderMe();
  renderPanel();
  renderKpis();
  if (window.maplibregl) buildMap();
  else window.addEventListener("load", buildMap, { once: true });
  openStream();
  setInterval(() => loadLive(), 10_000);
}

boot();
