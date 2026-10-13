// TEPHRA Connect (UI-DESIGN 7.24): an airline plugs its own aircraft positions into TEPHRA.
// The live map shows what arrives (each pushed flight glides to its new position; amber when it is
// in or heading into the ash), the sources glow while data flows, a ticker shows each push, and
// three steps show how to connect. Every string goes in through el() (textContent).

import { el, icon } from "./wall/util.js";
import { STYLE_URL, nightBasemap, nightColours, symbolColours } from "./wall/basemap.js";
import { addImages } from "./wall/images.js";

const $ = (id) => document.getElementById(id);
const FEED_NAME = { sigmet: "VA SIGMETs", vaac_darwin: "Darwin VAAC", vaac_tokyo: "Tokyo VAAC", vona: "Observatory (VONA)", jma_volcano: "JMA volcano notices", adsb: "ADS-B aircraft", winds: "Winds aloft", frames: "Satellite pictures", hsd: "Himawari raw data", taf: "Airport forecasts", metar: "Airport weather" };
const FEED_ICON = { sigmet: "i-alert", vaac_darwin: "i-file", vaac_tokyo: "i-file", vona: "i-eruption", jma_volcano: "i-eruption", adsb: "i-aircraft", winds: "i-wind", frames: "i-satellite", hsd: "i-satellite", taf: "i-airport", metar: "i-airport" };
const TONE = { OK: "ok", STALE: "stale", ERROR: "error" };
const GLIDE_MS = 5000;
const KEEP_MS = 90_000;
const reduced = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const app = {
  me: null, state: null, format: null, example: null, connections: [], sampleRunning: false, sampleId: null,
  key: null, lang: "curl",
  dots: new Map(), // hex -> { from, to, t0, inAsh, cs, conn, seen }
  pushes: [], // { at, conn, accepted }
};

// --- desk calls (session cookie) ----------------------------------------------------------------
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
  if (!window.maplibregl) return;
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
    for (const id of ["cones", "volcanoes", "trails", "dots"]) map.addSource(id, { type: "geojson", data: fc([]) });
    const official = ["==", ["get", "mode"], "OFFICIAL"];
    map.addLayer({ id: "cone-fill", type: "fill", source: "cones", filter: official, paint: { "fill-color": C.official, "fill-opacity": 0.1 } });
    map.addLayer({ id: "cone-line", type: "line", source: "cones", filter: official, paint: { "line-color": C.official, "line-opacity": 0.75, "line-width": 1.5 } });
    map.addLayer({ id: "tephra-line", type: "line", source: "cones", filter: ["!", official], paint: { "line-color": C.tephra, "line-opacity": 0.8, "line-width": 1.4, "line-dasharray": [4, 3] } });
    map.addLayer({ id: "volcanoes", type: "symbol", source: "volcanoes", layout: { "icon-image": ["concat", "volcano-", ["get", "code"]], "icon-size": 0.7, "icon-allow-overlap": true } });
    const cyan = "#5eead4";
    map.addLayer({ id: "trails", type: "line", source: "trails", layout: { "line-cap": "round" }, paint: { "line-color": ["case", ["get", "inAsh"], C.tephra, cyan], "line-opacity": 0.35, "line-width": 1.5 } });
    map.addLayer({ id: "dot-glow", type: "circle", source: "dots", paint: { "circle-radius": 13, "circle-blur": 0.9, "circle-color": ["case", ["get", "inAsh"], C.tephra, cyan], "circle-opacity": 0.45 } });
    map.addLayer({ id: "dot-core", type: "symbol", source: "dots", layout: { "icon-image": "ac-sdf", "icon-size": ["case", ["get", "inAsh"], 0.62, 0.5], "icon-rotate": ["get", "trk"], "icon-rotation-alignment": "map", "icon-allow-overlap": true, "icon-ignore-placement": true }, paint: { "icon-color": ["case", ["get", "inAsh"], C.tephra, "#e6fffb"], "icon-halo-color": "#04121a", "icon-halo-width": 1 } });
    map.addLayer({ id: "dot-label", type: "symbol", source: "dots", minzoom: 5.5, layout: { "text-field": ["get", "cs"], "text-font": ["Noto Sans Regular"], "text-size": 12, "text-offset": [0, 1.1], "text-anchor": "top", "text-optional": true }, paint: { "text-color": ["case", ["get", "inAsh"], C.tephra, "#bdf5ee"], "text-halo-color": "#05070a", "text-halo-width": 1.5 } });
    ready = true;
    loadWall();
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
const kick = () => { if (!raf) raf = requestAnimationFrame(paint); };

// --- a push arrives -------------------------------------------------------------------------------
function onPush(p) {
  const real = Date.now();
  app.pushes.push({ at: real, conn: p.connection_id, accepted: p.accepted });
  for (const dot of p.dots || []) {
    const to = [dot.lon, dot.lat];
    const held = app.dots.get(dot.hex);
    const from = held ? held.now || held.to : to;
    const trail = held ? [...held.trail, held.to].slice(-6) : [];
    app.dots.set(dot.hex, { from, to, t0: performance.now(), inAsh: dot.in_ash, cs: dot.callsign, trk: dot.track_deg, conn: p.connection_id, seen: real, trail });
  }
  if (!app.framed && ready && app.dots.size) {
    // frame the traffic the first time it arrives
    app.framed = true;
    const pts = [...app.dots.values()].map((d) => d.to);
    const lons = pts.map((x) => x[0]), lats = pts.map((x) => x[1]);
    map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: { top: 130, bottom: 50, left: 50, right: 50 }, maxZoom: 6.5, duration: reduced() ? 0 : 1200 });
  }
  for (const [hex, d] of app.dots) if (real - d.seen > KEEP_MS) app.dots.delete(hex);
  app.pushes = app.pushes.filter((x) => real - x.at < 10 * 60_000);
  addTick(p);
  renderKpis();
  renderAirline();
  $("cx-empty").hidden = app.dots.size > 0;
  kick();
}

function bump(node, value) {
  const text = String(value);
  if (node.textContent === text) return;
  node.textContent = text;
  node.classList.remove("is-bump");
  void node.offsetWidth;
  node.classList.add("is-bump");
}

function renderKpis() {
  const real = Date.now();
  const rate = app.pushes.filter((x) => real - x.at < 60_000).reduce((a, x) => a + x.accepted, 0);
  bump($("k-rate"), rate.toLocaleString("en"));
  bump($("k-live"), app.dots.size);
  bump($("k-ash"), [...app.dots.values()].filter((d) => d.inAsh).length);
}

function addTick(p) {
  const inAsh = (p.dots || []).filter((d) => d.in_ash).length;
  const li = el("li", { class: `cx-tick${p.accepted ? "" : " cx-tick--bad"}`, title: p.reasons?.join(" · ") || null },
    el("b", { text: p.name }),
    el("span", {}, el("span", { class: "ok", text: `+${p.accepted}` }), " positions"),
    inAsh ? el("span", {}, el("span", { class: "ash", text: String(inAsh) }), " in the ash") : null,
    p.rejected ? el("span", {}, el("span", { class: "bad", text: String(p.rejected) }), " refused") : null);
  const list = $("cx-ticker");
  list.prepend(li);
  while (list.children.length > 14) list.lastElementChild.remove();
}

// --- sources --------------------------------------------------------------------------------------
function spark(connId) {
  const real = Date.now();
  const buckets = new Array(20).fill(0); // 20 x 15 s = the last 5 min
  for (const x of app.pushes) {
    if (x.conn !== connId) continue;
    const i = 19 - Math.floor((real - x.at) / 15_000);
    if (i >= 0 && i < 20) buckets[i] += x.accepted;
  }
  const top = Math.max(1, ...buckets);
  const pts = buckets.map((v, i) => `${(i / 19) * 72},${24 - (v / top) * 20}`);
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("class", "cx-spark");
  svg.setAttribute("viewBox", "0 0 72 26");
  svg.setAttribute("aria-hidden", "true");
  const area = document.createElementNS(ns, "polygon");
  area.setAttribute("points", `0,26 ${pts.join(" ")} 72,26`);
  const line = document.createElementNS(ns, "polyline");
  line.setAttribute("points", pts.join(" "));
  svg.append(area, line);
  return svg;
}

function perMin(connId) {
  const real = Date.now();
  return app.pushes.filter((x) => x.conn === connId && real - x.at < 60_000).reduce((a, x) => a + x.accepted, 0);
}

function renderAirline() {
  const box = $("cx-airline");
  if (!app.me) {
    box.replaceChildren(el("li", {}, el("button", { type: "button", class: "cx-btn cx-btn--ghost", dataset: { act: "signin" } }, icon("i-lock"), el("span", { text: "Sign in to connect your airline" }))));
    return;
  }
  const live = app.connections.filter((c) => !c.revoked_at && !c.sample);
  if (!live.length) {
    box.replaceChildren(el("li", { class: "cx-none", text: "No airline source yet" }));
    return;
  }
  const real = Date.now();
  box.replaceChildren(...live.map((c) => {
    const flowing = app.pushes.some((x) => x.conn === c.id && real - x.at < 20_000);
    const n = perMin(c.id);
    return el("li", { class: "cx-src", dataset: { tone: flowing ? "flow" : c.last_push_at ? "ok" : "off" } },
      el("span", { class: "cx-src__ic" }, icon("i-network")),
      el("span", { class: "cx-src__t", title: `Key ends ${c.key_hint}` }, el("b", { text: c.name }), el("span", { text: `${c.accepted.toLocaleString("en")} positions` })),
      spark(c.id),
      el("span", { class: "cx-src__n", title: "positions in the last minute", text: n ? `${n}/min` : "" }),
      el("button", { type: "button", class: "cx-src__x", "aria-label": `Revoke ${c.name}`, title: "Revoke the key", dataset: { act: "revoke", id: c.id } }, icon("i-x")));
  }));
}

function renderSample() {
  const b = $("cx-sample");
  b.setAttribute("aria-pressed", String(app.sampleRunning));
  b.querySelector(".cx-sample__icon").replaceChildren(icon(app.sampleRunning ? "i-pause" : "i-play"));
  const n = app.sampleId ? perMin(app.sampleId) : 0;
  $("cx-sample-sub").textContent = app.sampleRunning ? (n ? `${n} positions / min · real flights` : "Starting…") : "Real recorded flights, moving live";
  $("cx-sample-hero").hidden = app.sampleRunning;
}

function renderPublic() {
  const feeds = (app.state?.feeds || []).filter((f) => FEED_NAME[f.feed]);
  $("cx-public").replaceChildren(...feeds.map((f) => {
    const tone = TONE[f.status] || "off";
    const age = f.age_s == null ? "not read yet" : f.age_s < 90 ? `${f.age_s} s ago` : f.age_s < 5400 ? `${Math.round(f.age_s / 60)} min ago` : `${Math.round(f.age_s / 3600)} h ago`;
    return el("li", { class: "cx-src", dataset: { tone }, title: f.last_error || null },
      el("span", { class: "cx-src__ic" }, icon(FEED_ICON[f.feed] || "i-live")),
      el("span", { class: "cx-src__t" }, el("b", { text: FEED_NAME[f.feed] }), el("span", { text: f.status === "DISABLED" ? "off" : age })),
      el("span"),
      el("span", { class: "cx-src__n", text: f.record_count ? f.record_count.toLocaleString("en") : "" }),
      el("span"));
  }));
  const replay = app.state?.mode === "REPLAY";
  $("cx-mode").hidden = !replay;
  $("cx-mode").textContent = replay ? "REPLAY clock" : "";
}

function renderMe() {
  const box = $("cx-me");
  box.replaceChildren(app.me ? el("span", { text: app.me.name }) : el("button", { type: "button", class: "cx-btn cx-btn--soft", dataset: { act: "signin" }, text: "Sign in" }));
}

async function loadConnections() {
  if (!app.me) { renderAirline(); return; }
  const res = await call("/api/desk/connections");
  if (!res.ok) return;
  app.connections = res.data.connections;
  app.sampleRunning = res.data.sample_running;
  app.sampleId = res.data.sample_connection_id || app.connections.find((c) => c.sample && !c.revoked_at)?.id || null;
  renderAirline();
  renderSample();
}

// --- steps: the format and the code ---------------------------------------------------------------
function renderRecord() {
  const props = app.format?.schema?.properties?.positions?.items?.properties || {};
  const required = new Set(app.format?.schema?.properties?.positions?.items?.required || []);
  const ex = app.example || {};
  $("cx-record").replaceChildren(...Object.keys(props).map((k) => el("span", { class: `cx-field${required.has(k) ? "" : " cx-field--opt"}`, title: props[k].description || null },
    el("b", { text: k }), el("span", { text: ex[k] == null ? "…" : String(ex[k]).replace(/\.000Z$/, "Z") }))));
}

function renderSnippet() {
  const url = `${location.origin}/api/push/positions`;
  const key = app.key || "tph_your_key";
  const file = "tephra-positions.sample.json";
  const text = {
    curl: `curl -X POST ${url} \\\n  -H "Authorization: Bearer ${key}" \\\n  -H "Content-Type: application/json" \\\n  -d @${file}`,
    python: `import json, urllib.request\n\nbatch = json.load(open("${file}"))\nreq = urllib.request.Request(\n    "${url}",\n    data=json.dumps(batch).encode(),\n    headers={"Authorization": "Bearer ${key}", "Content-Type": "application/json"},\n)\nprint(urllib.request.urlopen(req).read().decode())`,
    js: `const batch = await (await fetch("${file}")).json();\nconst res = await fetch("${url}", {\n  method: "POST",\n  headers: { Authorization: "Bearer ${key}", "Content-Type": "application/json" },\n  body: JSON.stringify(batch),\n});\nconsole.log(await res.json());`,
  }[app.lang];
  $("cx-snippet").textContent = text;
  for (const t of document.querySelectorAll(".cx-tab")) t.setAttribute("aria-selected", String(t.dataset.lang === app.lang));
}

// --- dialogs --------------------------------------------------------------------------------------
function dialog(title, ...kids) {
  const d = $("cx-dlg");
  d.replaceChildren(el("div", { class: "cx-dlg__in" }, el("h2", { id: "cx-dlg-t", class: "cx-dlg__t", text: title }), ...kids));
  if (!d.open) d.showModal();
  return d;
}

function signIn() {
  const name = el("input", { class: "cx-in", autocomplete: "username", required: true, minlength: "2", maxlength: "32" });
  const pin = el("input", { class: "cx-in", type: "password", inputmode: "numeric", autocomplete: "current-password", required: true });
  const err = el("p", { class: "cx-err", hidden: true });
  const go = el("button", { type: "submit", class: "cx-btn cx-btn--glow", text: "Sign in" });
  const form = el("form", { class: "cx-dlg__in" },
    el("label", {}, "Your name or initials", name), el("label", {}, "Desk PIN", pin), err,
    el("div", { class: "cx-dlg__acts" }, el("button", { type: "button", class: "cx-btn cx-btn--soft", dataset: { act: "close" }, text: "Cancel" }), go));
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    go.disabled = true;
    const res = await call("/api/desk/login", { method: "POST", body: { name: name.value.trim(), pin: pin.value } });
    go.disabled = false;
    if (!res.ok) { err.hidden = false; err.textContent = res.status === 401 ? "That PIN is not right." : res.status === 429 ? "Too many tries. Wait a minute." : "Sign-in failed."; return; }
    app.me = res.data;
    $("cx-dlg").close();
    renderMe();
    loadConnections();
  });
  const d = dialog("Sign in");
  d.firstElementChild.append(form);
  name.focus();
}

function newConnection() {
  if (!app.me) { signIn(); return; }
  const name = el("input", { class: "cx-in", placeholder: "e.g. RFA operations", minlength: "2", maxlength: "48", required: true });
  const err = el("p", { class: "cx-err", hidden: true });
  const go = el("button", { type: "submit", class: "cx-btn cx-btn--glow", text: "Create" });
  const form = el("form", { class: "cx-dlg__in" }, el("label", {}, "Name", name), err,
    el("div", { class: "cx-dlg__acts" }, el("button", { type: "button", class: "cx-btn cx-btn--soft", dataset: { act: "close" }, text: "Cancel" }), go));
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    go.disabled = true;
    const res = await call("/api/desk/connections", { method: "POST", body: { name: name.value.trim() } });
    go.disabled = false;
    if (!res.ok) { err.hidden = false; err.textContent = "Not created. Use 2 to 48 characters."; return; }
    app.key = res.data.key;
    renderSnippet();
    loadConnections();
    const copy = el("button", { type: "button", class: "cx-btn cx-btn--soft" }, icon("i-clipboard"), el("span", { text: "Copy" }));
    copy.addEventListener("click", () => navigator.clipboard?.writeText(app.key).then(() => { copy.lastChild.textContent = "Copied"; }));
    dialog(`${res.data.name} is connected`,
      el("div", { class: "cx-key" }, el("code", { text: app.key }), copy),
      el("p", { class: "cx-note", text: "Shown once. TEPHRA keeps only a fingerprint of it." }),
      el("div", { class: "cx-dlg__acts" }, el("button", { type: "button", class: "cx-btn cx-btn--glow", dataset: { act: "close" }, text: "Done" })));
  });
  const d = dialog("New connection");
  d.firstElementChild.append(form);
  name.focus();
}

async function toggleSample() {
  if (!app.me) { signIn(); return; }
  const on = !app.sampleRunning;
  app.sampleRunning = on;
  renderSample();
  const res = await call("/api/desk/sample-feed", { method: "POST", body: { on } });
  if (res.ok) {
    app.sampleRunning = res.data.sample_running;
    app.sampleId = res.data.sample_connection_id || app.sampleId;
    app.connections = res.data.connections;
  } else app.sampleRunning = !on;
  renderSample();
}

function revoke(id) {
  const c = app.connections.find((x) => x.id === id);
  if (!c) return;
  const go = el("button", { type: "button", class: "cx-btn cx-btn--danger", text: "Revoke" });
  go.addEventListener("click", async () => {
    go.disabled = true;
    await call(`/api/desk/connections/${encodeURIComponent(id)}/revoke`, { method: "POST", body: {} });
    $("cx-dlg").close();
    loadConnections();
  });
  dialog(`Revoke ${c.name}?`,
    el("p", { class: "cx-note", text: "Its key stops working at once." }),
    el("div", { class: "cx-dlg__acts" }, el("button", { type: "button", class: "cx-btn cx-btn--soft", dataset: { act: "close" }, text: "Cancel" }), go));
}

// --- wiring ---------------------------------------------------------------------------------------
document.addEventListener("click", (e) => {
  const t = e.target.closest("button, [data-act]");
  if (!t) return;
  const act = t.dataset.act;
  if (act === "signin") signIn();
  else if (act === "close") $("cx-dlg").close();
  else if (act === "revoke") revoke(t.dataset.id);
  else if (t.id === "cx-new" || t.id === "cx-new-2") newConnection();
  else if (t.id === "cx-sample" || t.id === "cx-sample-hero") toggleSample();
  else if (t.dataset.lang) { app.lang = t.dataset.lang; renderSnippet(); }
  else if (t.id === "cx-copy") navigator.clipboard?.writeText($("cx-snippet").textContent).then(() => { t.lastChild.textContent = "Copied"; setTimeout(() => { t.lastChild.textContent = "Copy"; }, 1500); });
});

function openStream() {
  const source = new EventSource("/api/events");
  source.addEventListener("push", (e) => { try { onPush(JSON.parse(e.data)); } catch { /* a bad frame is skipped */ } });
  source.addEventListener("cones", (e) => { try { setCones(JSON.parse(e.data)); } catch { /* skipped */ } });
  source.addEventListener("state", (e) => { try { app.state = JSON.parse(e.data); renderPublic(); } catch { /* skipped */ } });
}

async function boot() {
  const [state, me, format, sample] = await Promise.all([call("/api/state"), call("/api/desk/me"), call("/api/connect/format"), call("/api/connect/sample.json")]);
  app.state = state.ok ? state.data : null;
  app.me = me.ok ? me.data : null;
  app.format = format.ok ? format.data : null;
  app.example = sample.ok ? sample.data?.positions?.[0] : null;
  renderPublic();
  renderMe();
  renderRecord();
  renderSnippet();
  renderSample();
  await loadConnections();
  if (document.readyState === "complete" || window.maplibregl) buildMap();
  else window.addEventListener("load", buildMap, { once: true });
  openStream();
  setInterval(() => { renderKpis(); renderAirline(); renderSample(); }, 5000);
}

boot();
