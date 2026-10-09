// TEPHRA Wall: the read-only operations view.
// Loads GET /api/wall once, then follows GET /api/events (Server-Sent Events) and replaces
// one section at a time (MODULES.md section 8.4). Feed and model text is only ever inserted
// with textContent; the page runs under a CSP with no inline script or style.

const API_WALL = "/api/wall";
const API_EVENTS = "/api/events";
const BASEMAP_STYLE = "https://tiles.openfreemap.org/styles/dark";
const FONT_REGULAR = ["Noto Sans Regular"];
const FONT_BOLD = ["Noto Sans Bold"];

const TRACE_LIMIT = 200;
const ADVISORY_LIMIT = 50;
const OFFICIAL_RELABEL_MS = 15_000;
const WALL_RETRY_MS = 5_000;
const STREAM_REOPEN_MS = 5_000;
const PENDING_LIMIT = 500;

const COLOR = {
  accent: "#ffb000",
  accentText: "#ffc845",
  official: "#ff3d8b",
  officialText: "#ffc2da",
  aircraft: "#b9cde2",
  text: "#e8eef5",
  muted: "#9aa8b6",
  halo: "#05070a",
  panel: "#0b0e13",
};

const AVIATION_COLOR = {
  GREEN: "#35c46a",
  YELLOW: "#f2d22e",
  ORANGE: "#ff8a1f",
  RED: "#ff3b3b",
  UNKNOWN: "#8a96a3",
};

const FEED_LABEL = {
  sigmet: "SIGMET",
  vona: "VONA",
  vaac_tokyo: "VAAC TYO",
  vaac_darwin: "VAAC DRW",
  taf: "TAF",
  metar: "METAR",
  adsb: "ADS-B",
  winds: "WINDS",
  frames: "FRAMES",
  hsd: "HSD",
};

const EVIDENCE_LABEL = {
  OBSERVED_SAT: "Observed (satellite)",
  OBSERVED_GROUND: "Observed (ground)",
  ESTIMATED: "Estimated",
  NOT_IDENTIFIABLE: "Not identifiable",
  NOT_OBSERVED: "Not observed",
  NIGHT_BLIND: "Night: no visual",
  NO_VA_EXPECTED: "No VA expected",
  FORECAST_NOT_AVAILABLE: "Forecast not available",
  STALE: "Stale",
  UNKNOWN: "Unknown",
};

// Non-observations never shrink the hazard (docs/ARCHITECTURE.md); the card says so.
const NON_OBSERVATIONS = new Set(["NOT_IDENTIFIABLE", "NOT_OBSERVED", "NIGHT_BLIND"]);

const OUTCOME_LABEL = {
  ACCEPTED: "Model reading accepted by the validators",
  REPAIRED: "Accepted after one repair call",
  FALLBACK_OFFICIAL: "Model output rejected: official products only",
  OFFICIAL_ONLY: "No model call needed: official products only",
  STUB: "NO MODEL: deterministic stub",
};

const LAYER_GROUPS = {
  official: ["official-fill", "official-line", "official-line-pending", "official-label"],
  cone: ["cone-fill", "cone-line", "sector-line", "cone-label"],
  exposures: ["exposure-path", "exposure-entry"],
  aircraft: ["aircraft-icon", "aircraft-label", "aircraft-label-exposed"],
  volcanoes: ["volcano-ring", "volcano-icon"],
};

const FEATURE_SECTIONS = ["volcanoes", "official", "cones", "exposures", "aircraft"];
const INTERACTIVE_LAYERS = [
  "aircraft-icon",
  "exposure-entry",
  "volcano-icon",
  "official-fill",
  "cone-fill",
];

// --- state ------------------------------------------------------------------------------

const data = {
  state: null,
  feeds: [],
  feedsReceivedAt: 0,
  volcanoes: emptyCollection(),
  official: emptyCollection(),
  cones: emptyCollection(),
  exposures: emptyCollection(),
  aircraft: emptyCollection(),
  situations: new Map(),
  overlays: { btd: [], frames: [] },
  advisories: new Map(),
  trace: [],
  traceIds: new Set(),
};

const ui = {
  loaded: false,
  selected: null,
  regionKey: null,
  viewInitialised: false,
  regionSignature: "",
  layers: { official: true, cone: true, exposures: true, aircraft: true, volcanoes: true, btd: true },
  openDetails: new Set(),
  rendered: { head: "", cards: "", disc: "", plume: "", flights: "", btd: "", frames: "" },
  pendingEvents: [],
  wallRetry: null,
  streamReopen: null,
};

const clock = { activeMs: null, perfAt: 0 };

let map = null;
let mapReady = false;
let popup = null;
const btdLayers = new Map();

const reducedMotionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
const prefersReducedMotion = () => reducedMotionQuery.matches;

const $ = (id) => document.getElementById(id);

// --- small helpers ----------------------------------------------------------------------

function emptyCollection() {
  return { type: "FeatureCollection", features: [] };
}

function asCollection(value) {
  if (value && value.type === "FeatureCollection" && Array.isArray(value.features)) return value;
  return emptyCollection();
}

/** Build an element. Strings become text nodes; never parsed as HTML. */
function h(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = String(value);
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2), value);
    } else node.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : String(child));
  }
  return node;
}

/** A <details> whose open state survives re-renders. */
function keptDetails(key, summary, ...children) {
  const node = h("details", { class: "kept", open: ui.openDetails.has(key) }, h("summary", {}, summary), ...children);
  node.addEventListener("toggle", () => {
    if (node.open) ui.openDetails.add(key);
    else ui.openDetails.delete(key);
  });
  return node;
}

/** Re-render a container and put focus back on the control that had it. */
function renderInto(container, nodes) {
  const active = document.activeElement;
  const focusKey = active && container.contains(active) ? active.dataset?.focusKey : undefined;
  container.replaceChildren(...nodes);
  if (focusKey) {
    const again = container.querySelector(`[data-focus-key="${CSS.escape(focusKey)}"]`);
    if (again) again.focus();
  }
}

function announce(text) {
  const node = $("announcer");
  node.textContent = "";
  window.setTimeout(() => {
    node.textContent = text;
  }, 50);
}

// --- time and units ---------------------------------------------------------------------

function syncClock(iso) {
  const ms = parseTime(iso);
  if (ms === null) return;
  clock.activeMs = ms;
  clock.perfAt = performance.now();
}

/** The active clock: recorded time in REPLAY, advanced locally between server updates. */
function activeNow() {
  if (clock.activeMs === null) return Date.now();
  return clock.activeMs + (performance.now() - clock.perfAt);
}

function parseTime(iso) {
  if (!iso) return null;
  const ms = Date.parse(iso);
  return Number.isNaN(ms) ? null : ms;
}

const pad2 = (n) => String(n).padStart(2, "0");

function clockText(ms) {
  const d = new Date(ms);
  return `${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}:${pad2(d.getUTCSeconds())}Z`;
}

function hhmmz(ms) {
  if (ms === null) return "----Z";
  const d = new Date(ms);
  return `${pad2(d.getUTCHours())}${pad2(d.getUTCMinutes())}Z`;
}

function ddhhmmz(ms) {
  if (ms === null) return "------Z";
  const d = new Date(ms);
  return `${pad2(d.getUTCDate())}${pad2(d.getUTCHours())}${pad2(d.getUTCMinutes())}Z`;
}

function durationText(totalSeconds) {
  const s = Math.max(0, Math.floor(totalSeconds));
  if (s < 60) return `${s} s`;
  const minutes = Math.floor(s / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ${pad2(minutes % 60)} min`;
  return `${Math.floor(hours / 24)} d ${hours % 24} h`;
}

function untilText(targetMs, prefix) {
  const diff = targetMs - activeNow();
  if (diff <= 0) return prefix === "starts in" ? "started" : "expired";
  return `${prefix} ${durationText(diff / 1000)}`;
}

function agoText(sinceMs) {
  return `${durationText((activeNow() - sinceMs) / 1000)} ago`;
}

function countdownNode(targetMs, prefix) {
  if (targetMs === null) return null;
  return h("span", { class: "countdown", dataset: { until: String(targetMs), prefix } }, untilText(targetMs, prefix));
}

function agoNode(sinceMs) {
  if (sinceMs === null) return null;
  return h("span", { class: "ago", dataset: { since: String(sinceMs) } }, agoText(sinceMs));
}

const fl3 = (fl) => String(Math.round(fl)).padStart(3, "0");

function flText(ft) {
  if (ft === null || ft === undefined) return "?";
  if (ft <= 0) return "SFC";
  return `FL${fl3(ft / 100)}`;
}

function bandText(baseFt, topFt) {
  return `${flText(baseFt)}/${flText(topFt)}`;
}

function bearingText(deg) {
  return `${String(Math.round(deg) % 360).padStart(3, "0")}°`;
}

function percent(fraction) {
  return `${Math.round((Number(fraction) || 0) * 100)}%`;
}

function actionText(advisory) {
  switch (advisory.action) {
    case "CHANGE_LEVEL":
      if (advisory.change_level_fl_min != null && advisory.change_level_fl_max != null) {
        return `CHANGE LEVEL FL${fl3(advisory.change_level_fl_min)}-FL${fl3(advisory.change_level_fl_max)}`;
      }
      return "CHANGE LEVEL";
    case "HOLD":
      return advisory.hold_fl != null ? `HOLD FL${fl3(advisory.hold_fl)}` : "HOLD";
    case "DIVERT":
      return advisory.alternate_icao ? `DIVERT ${advisory.alternate_icao}` : "DIVERT";
    default:
      return advisory.action;
  }
}

function safeExternalUrl(url) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : null;
  } catch {
    return null;
  }
}

/** Blob images are served by TEPHRA itself; anything else is ignored. */
function sameOriginUrl(path) {
  try {
    const parsed = new URL(path, window.location.origin);
    return parsed.origin === window.location.origin ? parsed.href : null;
  } catch {
    return null;
  }
}

// --- top bar ----------------------------------------------------------------------------

function renderTopBar() {
  const state = data.state;
  if (!state) return;
  const replay = state.mode === "REPLAY";

  const badge = $("mode-badge");
  badge.textContent = state.mode;
  badge.className = `mode-badge mode-badge--${replay ? "replay" : "live"}`;

  const banner = $("replay-banner");
  banner.hidden = !replay;
  if (replay) {
    const base = state.replay?.banner ?? "REPLAY: recorded real feeds";
    const auto = state.replay?.auto ? " (switched automatically: no live activity)" : "";
    $("replay-banner-text").textContent = `${base}${auto}`;
  }
  document.title = replay ? "REPLAY - TEPHRA Wall" : "TEPHRA Wall";

  const llm = $("llm-label");
  const stub = state.llm?.backend === "stub";
  llm.textContent = stub ? "NO MODEL (stub)" : `AI: ${state.llm?.label ?? "Gemini"}`;
  llm.className = `llm-label${stub ? " llm-label--stub" : " llm-label--ai"}`;

  $("disclaimer").textContent = state.disclaimer;
  const airline = state.airline;
  $("airline").textContent = airline ? `${airline.name} (${airline.code}) is fictional` : "";

  $("count-active").textContent = String(state.active_volcano_ids?.length ?? 0);
  $("count-exposed").textContent = String(state.exposed_count ?? 0);
  $("count-drafts").textContent = String(state.draft_count ?? 0);

  renderRegions();
}

function renderRegions() {
  const regions = data.state?.regions ?? [];
  const signature = `${regions.map((r) => r.key).join("|")}#${ui.regionKey}`;
  if (signature === ui.regionSignature) return;
  ui.regionSignature = signature;
  const buttons = regions.map((region, index) =>
    h(
      "button",
      {
        type: "button",
        class: "btn btn--region",
        "aria-pressed": String(region.key === ui.regionKey),
        "aria-keyshortcuts": index < 9 ? String(index + 1) : null,
        dataset: { focusKey: `region:${region.key}` },
        onclick: () => fitRegion(region, true),
      },
      h("span", { class: "btn__key", "aria-hidden": "true" }, String(index + 1)),
      region.name,
    ),
  );
  renderInto($("regions"), buttons);
}

function feedAgeSeconds(feed) {
  if (feed.age_s === null || feed.age_s === undefined) return null;
  return feed.age_s + (performance.now() - data.feedsReceivedAt) / 1000;
}

function feedClass(feed, age) {
  if (feed.status !== "OK") return feed.status.toLowerCase();
  if (age !== null && feed.cadence_s > 0 && age > feed.cadence_s * 3) return "late";
  return "ok";
}

function renderFeeds() {
  const chips = data.feeds.map((feed) => {
    const age = feedAgeSeconds(feed);
    const label = FEED_LABEL[feed.feed] ?? feed.feed.toUpperCase();
    const status = feedClass(feed, age);
    const ageText = age === null ? "never" : durationText(age);
    const statusWord = feed.status === "OK" ? (status === "late" ? "LATE" : "") : feed.status;
    return h(
      "span",
      { class: `feed-chip feed-chip--${status}` },
      h("span", { class: "feed-chip__dot", "aria-hidden": "true" }),
      h("span", { class: "feed-chip__name" }, label),
      h("span", { class: "feed-chip__age" }, statusWord ? `${statusWord} ${ageText}` : ageText),
      feed.replay ? h("span", { class: "feed-chip__replay" }, "R") : null,
    );
  });
  $("feed-chips").replaceChildren(...chips);

  if (!$("feeds").open) return;
  const rows = data.feeds.map((feed) => {
    const age = feedAgeSeconds(feed);
    return h(
      "tr",
      { class: `feed-row feed-row--${feedClass(feed, age)}` },
      h("th", { scope: "row" }, FEED_LABEL[feed.feed] ?? feed.feed),
      h("td", {}, feed.replay ? `${feed.status} (replay)` : feed.status),
      h("td", {}, age === null ? "never" : durationText(age)),
      h("td", {}, ddhhmmz(parseTime(feed.last_success_at))),
      h("td", {}, String(feed.record_count ?? 0)),
      h("td", { class: "feed-row__error" }, feed.last_error ?? ""),
    );
  });
  $("feed-table-body").replaceChildren(...rows);
}

function setStreamStatus(kind, text) {
  const node = $("stream-status");
  node.className = `stream-status stream-status--${kind}`;
  node.textContent = text;
}

// --- map --------------------------------------------------------------------------------

function showMapMessage(text) {
  const node = $("map-message");
  node.textContent = text;
  node.hidden = !text;
}

function initMap() {
  const lib = window.maplibregl;
  if (!lib) {
    showMapMessage("Map library could not load from unpkg.com. Panels keep updating.");
    return;
  }
  map = new lib.Map({
    container: "map",
    style: BASEMAP_STYLE,
    center: [111.0, -7.6],
    zoom: 6.2,
    attributionControl: false,
    dragRotate: false,
    pitchWithRotate: false,
    touchPitch: false,
    fadeDuration: prefersReducedMotion() ? 0 : 300,
  });
  map.touchZoomRotate.disableRotation();
  map.addControl(new lib.NavigationControl({ showCompass: false }), "top-right");
  map.addControl(new lib.ScaleControl({ unit: "nautical" }), "bottom-right");
  map.addControl(
    new lib.AttributionControl({
      compact: false,
      // The OpenFreeMap style carries its own OpenFreeMap / OpenMapTiles / OSM credit.
      customAttribution: [
        "Aircraft: adsb.lol (ODbL 1.0)",
        "Himawari-9 data: JMA via NOAA",
      ],
    }),
    "bottom-right",
  );
  map.on("load", onMapLoad);
  map.on("error", (event) => {
    if (!mapReady && event?.error) {
      showMapMessage("Basemap unavailable. TEPHRA layers will draw once the map loads.");
    }
  });
}

function onMapLoad() {
  showMapMessage("");
  addIcons();
  addSourcesAndLayers();
  mapReady = true;
  for (const key of FEATURE_SECTIONS) pushSection(key);
  syncBtdOverlays();
  applyLayerVisibility();
  bindMapInteractions();
}

function drawIcon(size, draw) {
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  draw(ctx, size);
  return ctx.getImageData(0, 0, size, size);
}

function arrowIcon(fill) {
  return drawIcon(48, (ctx, s) => {
    ctx.beginPath();
    ctx.moveTo(s / 2, 4);
    ctx.lineTo(s - 9, s - 6);
    ctx.lineTo(s / 2, s - 15);
    ctx.lineTo(9, s - 6);
    ctx.closePath();
    ctx.lineJoin = "round";
    ctx.lineWidth = 4;
    ctx.strokeStyle = COLOR.halo;
    ctx.stroke();
    ctx.fillStyle = fill;
    ctx.fill();
  });
}

function dotIcon(fill) {
  return drawIcon(32, (ctx, s) => {
    ctx.beginPath();
    ctx.arc(s / 2, s / 2, s / 2 - 6, 0, Math.PI * 2);
    ctx.lineWidth = 4;
    ctx.strokeStyle = COLOR.halo;
    ctx.stroke();
    ctx.fillStyle = fill;
    ctx.fill();
  });
}

function triangleIcon(fill) {
  return drawIcon(40, (ctx, s) => {
    ctx.beginPath();
    ctx.moveTo(s / 2, 5);
    ctx.lineTo(s - 5, s - 7);
    ctx.lineTo(5, s - 7);
    ctx.closePath();
    ctx.lineJoin = "round";
    ctx.lineWidth = 5;
    ctx.strokeStyle = COLOR.halo;
    ctx.stroke();
    ctx.fillStyle = fill;
    ctx.fill();
  });
}

function addIcons() {
  const add = (name, image) => {
    if (!map.hasImage(name)) map.addImage(name, image, { pixelRatio: 2 });
  };
  add("ac", arrowIcon(COLOR.aircraft));
  add("ac-exposed", arrowIcon(COLOR.accent));
  add("ac-dot", dotIcon(COLOR.aircraft));
  add("ac-exposed-dot", dotIcon(COLOR.accent));
  for (const [code, color] of Object.entries(AVIATION_COLOR)) add(`volcano-${code}`, triangleIcon(color));
}

function aviationColorExpression() {
  return ["match", ["get", "color_code"], ...Object.entries(AVIATION_COLOR).flat(), AVIATION_COLOR.UNKNOWN];
}

const isExposed = ["==", ["get", "exposed"], true];
const textHalo = { "text-halo-color": COLOR.halo, "text-halo-width": 1.6 };

function addSourcesAndLayers() {
  for (const key of FEATURE_SECTIONS) map.addSource(key, { type: "geojson", data: emptyCollection() });

  map.addLayer({
    id: "official-fill",
    type: "fill",
    source: "official",
    paint: {
      "fill-color": COLOR.official,
      "fill-opacity": ["match", ["get", "phase"], "current", 0.18, "future", 0.06, 0.03],
    },
  });
  map.addLayer({
    id: "official-line",
    type: "line",
    source: "official",
    filter: ["==", ["get", "phase"], "current"],
    paint: { "line-color": COLOR.official, "line-width": 2.4 },
  });
  map.addLayer({
    id: "official-line-pending",
    type: "line",
    source: "official",
    filter: ["!=", ["get", "phase"], "current"],
    paint: { "line-color": COLOR.official, "line-width": 1.4, "line-opacity": 0.75, "line-dasharray": [1, 1.5] },
  });

  map.addLayer({
    id: "cone-fill",
    type: "fill",
    source: "cones",
    filter: ["==", ["get", "part"], "cone"],
    paint: { "fill-color": COLOR.accent, "fill-opacity": 0.07 },
  });
  map.addLayer({
    id: "cone-line",
    type: "line",
    source: "cones",
    filter: ["==", ["get", "part"], "cone"],
    paint: { "line-color": COLOR.accent, "line-width": 2.6, "line-dasharray": [2.4, 1.6] },
  });
  map.addLayer({
    id: "sector-line",
    type: "line",
    source: "cones",
    filter: ["==", ["get", "part"], "sector"],
    paint: { "line-color": COLOR.accent, "line-width": 1.2, "line-opacity": 0.8, "line-dasharray": [0.5, 1.5] },
  });

  map.addLayer({
    id: "exposure-path",
    type: "line",
    source: "exposures",
    filter: ["==", ["get", "kind"], "path"],
    layout: { "line-cap": "round" },
    paint: { "line-color": COLOR.accent, "line-width": 2, "line-dasharray": [1, 1.2] },
  });
  map.addLayer({
    id: "exposure-entry",
    type: "circle",
    source: "exposures",
    filter: ["==", ["get", "kind"], "entry"],
    paint: {
      "circle-radius": 5,
      "circle-color": COLOR.panel,
      "circle-stroke-color": COLOR.accent,
      "circle-stroke-width": 2.5,
    },
  });

  map.addLayer({
    id: "volcano-ring",
    type: "circle",
    source: "volcanoes",
    filter: ["==", ["get", "active"], true],
    paint: {
      "circle-radius": 16,
      "circle-color": "rgba(0,0,0,0)",
      "circle-stroke-color": aviationColorExpression(),
      "circle-stroke-width": 2,
      "circle-stroke-opacity": 0.85,
    },
  });
  map.addLayer({
    id: "volcano-icon",
    type: "symbol",
    source: "volcanoes",
    layout: {
      "icon-image": ["concat", "volcano-", ["get", "color_code"]],
      "icon-allow-overlap": true,
      "icon-ignore-placement": true,
      "text-field": ["get", "name"],
      "text-font": FONT_BOLD,
      "text-size": ["case", ["==", ["get", "active"], true], 13, 11],
      "text-offset": [0, 1.2],
      "text-anchor": "top",
      "text-optional": true,
    },
    paint: { "text-color": COLOR.text, ...textHalo },
  });

  map.addLayer({
    id: "aircraft-icon",
    type: "symbol",
    source: "aircraft",
    layout: {
      "icon-image": [
        "case",
        ["!=", ["typeof", ["get", "track_deg"]], "number"],
        ["case", isExposed, "ac-exposed-dot", "ac-dot"],
        ["case", isExposed, "ac-exposed", "ac"],
      ],
      "icon-rotate": ["coalesce", ["get", "track_deg"], 0],
      "icon-rotation-alignment": "map",
      "icon-allow-overlap": true,
      "icon-ignore-placement": true,
      "symbol-sort-key": ["case", isExposed, 1, 0],
    },
  });
  map.addLayer({
    id: "aircraft-label",
    type: "symbol",
    source: "aircraft",
    minzoom: 7,
    filter: ["!", isExposed],
    layout: {
      "text-field": ["get", "label"],
      "text-font": FONT_REGULAR,
      "text-size": 11,
      "text-offset": [0, 1.3],
      "text-anchor": "top",
    },
    paint: { "text-color": COLOR.muted, ...textHalo },
  });
  map.addLayer({
    id: "aircraft-label-exposed",
    type: "symbol",
    source: "aircraft",
    filter: isExposed,
    layout: {
      "text-field": ["get", "label"],
      "text-font": FONT_BOLD,
      "text-size": 13,
      "text-offset": [0, 1.3],
      "text-anchor": "top",
      "text-allow-overlap": true,
    },
    paint: { "text-color": COLOR.accentText, ...textHalo },
  });

  map.addLayer({
    id: "official-label",
    type: "symbol",
    source: "official",
    layout: {
      "text-field": ["get", "map_label"],
      "text-font": FONT_BOLD,
      "text-size": 12,
      "text-max-width": 18,
      "text-line-height": 1.25,
    },
    paint: { "text-color": COLOR.officialText, ...textHalo },
  });
  map.addLayer({
    id: "cone-label",
    type: "symbol",
    source: "cones",
    filter: ["==", ["get", "part"], "cone"],
    layout: {
      "symbol-placement": "line",
      "symbol-spacing": 360,
      "text-field": ["get", "map_label"],
      "text-font": FONT_BOLD,
      "text-size": 12,
      "text-letter-spacing": 0.04,
    },
    paint: { "text-color": COLOR.accentText, ...textHalo },
  });
}

/** Official features get their phase and a countdown label on the active clock. */
function decorateOfficial(collection) {
  const now = activeNow();
  const features = collection.features.map((featureItem) => {
    const props = featureItem.properties ?? {};
    const from = parseTime(props.valid_from);
    const to = parseTime(props.valid_to);
    let phase = "current";
    let timing = to === null ? "" : untilText(to, "expires in");
    if (to !== null && to < now) {
      phase = "expired";
      timing = "expired";
    } else if (from !== null && from > now) {
      phase = "future";
      timing = untilText(from, "starts in");
    }
    const mapLabel = `${props.label ?? props.source_id ?? "OFFICIAL"}\n${bandText(props.base_ft, props.top_ft)} ${timing}`;
    return { ...featureItem, properties: { ...props, phase, map_label: mapLabel } };
  });
  return { type: "FeatureCollection", features };
}

function decorateCones(collection) {
  const features = collection.features.map((featureItem) => {
    const props = featureItem.properties ?? {};
    const mapLabel = `TEPHRA ${props.label ?? props.mode ?? ""}  ${bandText(props.base_ft, props.top_ft)}`;
    return { ...featureItem, properties: { ...props, map_label: mapLabel } };
  });
  return { type: "FeatureCollection", features };
}

function pushSection(key) {
  if (!mapReady) return;
  const source = map.getSource(key);
  if (!source) return;
  if (key === "official") source.setData(decorateOfficial(data.official));
  else if (key === "cones") source.setData(decorateCones(data.cones));
  else source.setData(data[key]);
}

function validCorners(corners) {
  return (
    Array.isArray(corners) &&
    corners.length === 4 &&
    corners.every((c) => Array.isArray(c) && c.length === 2 && c.every(Number.isFinite))
  );
}

const safeLayerId = (text) => String(text).replace(/[^A-Za-z0-9_-]/g, "_");

function syncBtdOverlays() {
  if (!mapReady) return;
  const wanted = new Map();
  for (const overlay of data.overlays?.btd ?? []) {
    const url = sameOriginUrl(overlay.image_url);
    if (url && validCorners(overlay.corners)) wanted.set(overlay.volcano_id, { url, coordinates: overlay.corners });
  }
  for (const [volcanoId, entry] of btdLayers) {
    if (wanted.has(volcanoId)) continue;
    if (map.getLayer(entry.layerId)) map.removeLayer(entry.layerId);
    if (map.getSource(entry.sourceId)) map.removeSource(entry.sourceId);
    btdLayers.delete(volcanoId);
  }
  for (const [volcanoId, { url, coordinates }] of wanted) {
    const key = `${url}|${JSON.stringify(coordinates)}`;
    const existing = btdLayers.get(volcanoId);
    if (existing) {
      if (existing.key !== key) {
        map.getSource(existing.sourceId)?.updateImage({ url, coordinates });
        existing.key = key;
      }
      continue;
    }
    const sourceId = `btd-src-${safeLayerId(volcanoId)}`;
    const layerId = `btd-${safeLayerId(volcanoId)}`;
    map.addSource(sourceId, { type: "image", url, coordinates });
    map.addLayer(
      {
        id: layerId,
        type: "raster",
        source: sourceId,
        layout: { visibility: ui.layers.btd ? "visible" : "none" },
        paint: { "raster-opacity": 0.62, "raster-fade-duration": 0 },
      },
      "official-fill",
    );
    btdLayers.set(volcanoId, { sourceId, layerId, key });
  }
}

function applyLayerVisibility() {
  if (!mapReady) return;
  for (const [group, layerIds] of Object.entries(LAYER_GROUPS)) {
    for (const id of layerIds) {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", ui.layers[group] ? "visible" : "none");
    }
  }
  for (const entry of btdLayers.values()) {
    if (map.getLayer(entry.layerId)) {
      map.setLayoutProperty(entry.layerId, "visibility", ui.layers.btd ? "visible" : "none");
    }
  }
}

function setLayer(group, visible) {
  ui.layers[group] = visible;
  const box = document.querySelector(`input[data-layer="${group}"]`);
  if (box) box.checked = visible;
  applyLayerVisibility();
}

function moveCamera(center, zoom) {
  if (!map) return;
  const target = { center, zoom: Math.max(map.getZoom(), zoom) };
  if (prefersReducedMotion()) map.jumpTo(target);
  else map.flyTo({ ...target, duration: 1100 });
}

function fitRegion(region, animate) {
  ui.regionKey = region.key;
  renderRegions();
  if (!map) return;
  const { west, south, east, north } = region.bbox;
  map.fitBounds(
    [
      [west, south],
      [east, north],
    ],
    { padding: 28, animate: animate && !prefersReducedMotion(), duration: 1000 },
  );
}

function focusFlight(hex, flightId) {
  const aircraft = data.aircraft.features.find((f) => f.properties?.hex === hex);
  if (aircraft) {
    moveCamera(aircraft.geometry.coordinates, 7.5);
    return;
  }
  const entry = data.exposures.features.find(
    (f) => f.properties?.flight_id === flightId && f.properties?.kind === "entry",
  );
  if (entry) moveCamera(entry.geometry.coordinates, 7.5);
}

function focusVolcano(volcanoId) {
  const volcano = data.volcanoes.features.find((f) => f.properties?.id === volcanoId);
  if (volcano) moveCamera(volcano.geometry.coordinates, 7);
}

// --- map popups -------------------------------------------------------------------------

function bindMapInteractions() {
  const layers = () => INTERACTIVE_LAYERS.filter((id) => map.getLayer(id));
  map.on("mousemove", (event) => {
    const hit = map.queryRenderedFeatures(event.point, { layers: layers() }).length > 0;
    map.getCanvas().style.cursor = hit ? "pointer" : "";
  });
  map.on("click", (event) => {
    const hits = map.queryRenderedFeatures(event.point, { layers: layers() });
    if (hits.length === 0) return;
    const rank = (f) => INTERACTIVE_LAYERS.indexOf(f.layer.id);
    const top = hits.reduce((best, f) => (rank(f) < rank(best) ? f : best));
    const content = popupContent(top);
    if (!content) return;
    popup?.remove();
    popup = new window.maplibregl.Popup({ maxWidth: "320px", focusAfterOpen: true, className: "wall-popup" })
      .setLngLat(event.lngLat)
      .setDOMContent(content)
      .addTo(map);
    if (top.layer.id === "volcano-icon" && data.situations.has(top.properties.id)) {
      selectVolcano(top.properties.id);
    }
  });
}

function popupRows(rows) {
  return h(
    "dl",
    { class: "popup__rows" },
    rows.filter(([, value]) => value !== null && value !== undefined && value !== "").map(([label, value]) => [
      h("dt", {}, label),
      h("dd", {}, value),
    ]),
  );
}

function popupContent(featureItem) {
  const p = featureItem.properties ?? {};
  switch (featureItem.layer.id) {
    case "aircraft-icon": {
      const levels = p.nav_altitude_mcp_ft != null ? `${flText(p.alt_baro_ft)} (MCP ${flText(p.nav_altitude_mcp_ft)})` : flText(p.alt_baro_ft);
      return h(
        "div",
        { class: "popup" },
        h("h3", { class: "popup__title" }, p.proxy_flight ?? p.hex),
        p.exposed === true
          ? h("p", { class: "popup__alert" }, Number(p.minutes_to_entry) === 0 ? "Inside the cone now" : `Enters the cone in ${p.minutes_to_entry} min if track and level are held`)
          : null,
        popupRows([
          ["ADS-B", `${p.callsign ?? "no callsign"} / ${p.hex}`],
          ["Type", p.type_icao ?? "unknown"],
          ["Level", levels],
          ["Ground speed", p.gs_kt != null ? `${Math.round(p.gs_kt)} kt` : "n/a"],
          ["Track", p.track_deg != null ? bearingText(p.track_deg) : "n/a"],
          ["Position", p.observed_at ? `${hhmmz(parseTime(p.observed_at))}` : null],
        ]),
        h("p", { class: "popup__note" }, "Proxy flight number of the fictional airline; ADS-B callsign for reference only."),
      );
    }
    case "exposure-entry":
      return h(
        "div",
        { class: "popup" },
        h("h3", { class: "popup__title" }, `${p.proxy_flight} cone entry`),
        popupRows([["Minutes to entry", String(p.minutes_to_entry)]]),
        h("p", { class: "popup__note" }, "Extrapolated along current track and ground speed."),
      );
    case "volcano-icon":
      return h(
        "div",
        { class: "popup" },
        h("h3", { class: "popup__title" }, p.name),
        popupRows([
          ["Colour code", p.color_code],
          ["Summit", p.summit_elev_ft != null ? `${Number(p.summit_elev_ft).toLocaleString("en-US")} ft` : null],
          ["VAAC", p.vaac],
          ["Status", p.active === true ? "Active in TEPHRA" : "Not active"],
        ]),
      );
    case "official-fill": {
      const to = parseTime(p.valid_to);
      return h(
        "div",
        { class: "popup popup--official" },
        h("h3", { class: "popup__title" }, p.label),
        popupRows([
          ["Band", bandText(p.base_ft, p.top_ft)],
          ["Layer", p.layer],
          ["Valid", `${ddhhmmz(parseTime(p.valid_from))} to ${ddhhmmz(to)}`],
          ["Source", p.source_id],
        ]),
        to !== null ? h("p", { class: "popup__note" }, countdownNode(to, "expires in")) : null,
        h("p", { class: "popup__note" }, "Official product: binding. TEPHRA never shrinks it."),
      );
    }
    case "cone-fill":
      return h(
        "div",
        { class: "popup popup--cone" },
        h("h3", { class: "popup__title" }, `TEPHRA cone ${p.label ?? ""}`),
        popupRows([
          ["Band", bandText(p.base_ft, p.top_ft)],
          ["Mode", p.mode],
          ["Confidence", percent(p.confidence)],
          ["Valid to", ddhhmmz(parseTime(p.valid_to))],
        ]),
        h("p", { class: "popup__note" }, "Union of every valid official polygon and, when widened, the model sector."),
      );
    default:
      return null;
  }
}

// --- situation rail ---------------------------------------------------------------------

function visibleSituations() {
  return [...data.situations.values()].sort((a, b) => {
    const exposed = (b.exposed_count ?? 0) - (a.exposed_count ?? 0);
    return exposed !== 0 ? exposed : a.volcano_name.localeCompare(b.volcano_name);
  });
}

function ensureSelection() {
  if (ui.selected && data.situations.has(ui.selected)) return;
  ui.selected = visibleSituations()[0]?.volcano_id ?? null;
}

function selectVolcano(volcanoId) {
  if (!data.situations.has(volcanoId)) return;
  ui.selected = volcanoId;
  renderVolcanoTabs();
  renderSituation();
}

function renderVolcanoTabs() {
  const situations = visibleSituations();
  const tabs = situations.map((sit) =>
    h(
      "button",
      {
        type: "button",
        role: "tab",
        class: "volcano-tab",
        id: `tab-${safeLayerId(sit.volcano_id)}`,
        "aria-selected": String(sit.volcano_id === ui.selected),
        "aria-controls": "situation-body",
        tabindex: sit.volcano_id === ui.selected ? "0" : "-1",
        dataset: { focusKey: `tab:${sit.volcano_id}`, volcano: sit.volcano_id },
        onclick: () => {
          selectVolcano(sit.volcano_id);
          focusVolcano(sit.volcano_id);
        },
        onkeydown: onTabKey,
      },
      h("span", { class: `code-dot code-dot--${sit.color_code}`, "aria-hidden": "true" }),
      sit.volcano_name,
      sit.exposed_count > 0 ? h("span", { class: "tab-count", "aria-label": `${sit.exposed_count} exposed` }, String(sit.exposed_count)) : null,
    ),
  );
  renderInto($("volcano-tabs"), tabs);
  $("compare-open").disabled = situations.length === 0;
  const panel = $("situation-body");
  if (ui.selected) panel.setAttribute("aria-labelledby", `tab-${safeLayerId(ui.selected)}`);
  else panel.setAttribute("aria-labelledby", "situation-heading");
}

function onTabKey(event) {
  const keys = ["ArrowLeft", "ArrowRight", "Home", "End"];
  if (!keys.includes(event.key)) return;
  const tabs = [...$("volcano-tabs").querySelectorAll('[role="tab"]')];
  const index = tabs.indexOf(event.currentTarget);
  let next = index;
  if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
  if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
  if (event.key === "Home") next = 0;
  if (event.key === "End") next = tabs.length - 1;
  event.preventDefault();
  const volcanoId = tabs[next]?.dataset.volcano;
  if (!volcanoId) return;
  selectVolcano(volcanoId);
  $("volcano-tabs").querySelector(`[data-volcano="${CSS.escape(volcanoId)}"]`)?.focus();
}

/** Render a sub-section only when its input changed, so open details and scroll stay put. */
function renderSection(name, inputs, build) {
  const signature = JSON.stringify(inputs);
  if (ui.rendered[name] === signature) return;
  ui.rendered[name] = signature;
  renderInto($(`sit-${name}`), build());
}

function renderSituation() {
  ensureSelection();
  const sit = ui.selected ? data.situations.get(ui.selected) : null;
  const empty = $("sit-empty");
  if (!sit) {
    empty.hidden = false;
    empty.textContent = ui.loaded
      ? "No active volcano. TEPHRA is watching the feeds; a volcano becomes active with a VONA in the last 24 h, a current VAA or a valid VA SIGMET nearby."
      : "Waiting for the first snapshot.";
    for (const name of Object.keys(ui.rendered)) renderSection(name, null, () => []);
    return;
  }
  empty.hidden = true;
  const discIndex = new Map(sit.discrepancies.map((d, i) => [d.id, i + 1]));

  renderSection("head", [sit.volcano_id, sit.volcano_name, sit.color_code, sit.active_reasons, sit.as_of], () => situationHead(sit));
  renderSection("cards", [sit.volcano_id, sit.cards, sit.discrepancies], () => [
    h("div", { class: "cards" }, sit.cards.map((card) => sourceCard(card, sit, discIndex, "rail"))),
  ]);
  renderSection("disc", [sit.volcano_id, sit.discrepancies], () => discrepancyList(sit, discIndex, "rail"));
  renderSection("plume", [sit.volcano_id, sit.assessment, discIndex.size], () => plumeBlock(sit, discIndex));
  renderFlights();
  renderSection("btd", [sit.volcano_id, sit.btd, btdOverlayFor(sit.volcano_id)], () => btdBlock(sit));
  renderSection("frames", [sit.volcano_id, sit.frames], () => framesBlock(sit));
}

function situationHead(sit) {
  return [
    h(
      "div",
      { class: "sit-head" },
      h("h3", { class: "sit-head__name" }, sit.volcano_name),
      h("span", { class: `code-chip code-chip--${sit.color_code}` }, sit.color_code),
      h("span", { class: "sit-head__asof" }, "as of ", hhmmz(parseTime(sit.as_of))),
    ),
    sit.active_reasons.length
      ? h("ul", { class: "reasons" }, sit.active_reasons.map((reason) => h("li", {}, reason)))
      : null,
  ];
}

function sourceCard(card, sit, discIndex, context) {
  const issued = parseTime(card.issued_at);
  const validFrom = parseTime(card.valid_from);
  const validTo = parseTime(card.valid_to);
  const classes = ["src-card", `src-card--${card.kind}`];
  if (card.missing) classes.push("src-card--missing");
  if (card.stale) classes.push("src-card--stale");

  const header = h(
    "header",
    { class: "src-card__head" },
    h("span", { class: "src-card__kind" }, card.kind),
    card.missing
      ? h("span", { class: "evidence evidence--missing" }, "MISSING")
      : h(
          "span",
          { class: `evidence evidence--${NON_OBSERVATIONS.has(card.evidence) ? "nonobs" : card.evidence}` },
          EVIDENCE_LABEL[card.evidence] ?? card.evidence,
        ),
  );

  if (card.missing) {
    return h(
      "article",
      { class: classes.join(" "), "aria-label": `${card.kind}: missing` },
      header,
      h("p", { class: "src-card__missing" }, card.missing_note ?? `No ${card.kind}`),
      h("p", { class: "src-card__hint" }, "Absence is not evidence that there is no ash."),
      badges(card, sit, discIndex),
    );
  }

  const times = [];
  if (issued !== null) times.push(h("span", {}, `ISSUED ${ddhhmmz(issued)}`));
  if (validFrom !== null && validTo !== null) {
    times.push(h("span", {}, `VALID ${hhmmz(validFrom)}-${hhmmz(validTo)}`));
    times.push(countdownNode(validTo, "expires in"));
  }

  const fields = Object.entries(card.display_fields ?? {});
  const url = card.url ? safeExternalUrl(card.url) : null;
  const rawLabel = `${card.kind} raw text${context === "dialog" ? " (side by side)" : ""}`;

  return h(
    "article",
    { class: classes.join(" "), "aria-label": `${card.kind}: ${card.title}` },
    header,
    h("h4", { class: "src-card__title" }, card.title),
    NON_OBSERVATIONS.has(card.evidence)
      ? h("p", { class: "src-card__hint" }, "Non-observation: never narrows the hazard.")
      : null,
    times.length ? h("p", { class: "src-card__times" }, times) : null,
    fields.length
      ? h("dl", { class: "src-card__fields" }, fields.map(([label, value]) => h("div", {}, h("dt", {}, label), h("dd", {}, value))))
      : null,
    badges(card, sit, discIndex),
    h("pre", { class: "src-card__raw", tabindex: "0", "aria-label": rawLabel }, card.raw_text || "(no raw text)"),
    h(
      "footer",
      { class: "src-card__foot" },
      h("span", { class: "src-card__id" }, card.source_id ?? ""),
      card.sha256_short ? h("span", { class: "hash" }, `#${card.sha256_short}`) : null,
      card.fetched_at ? h("span", {}, `fetched ${hhmmz(parseTime(card.fetched_at))}`) : null,
      card.stale
        ? h("span", { class: "stale-tag" }, `STALE${card.stale_age_s != null ? ` ${durationText(card.stale_age_s)}` : ""}`)
        : null,
      card.extra_source_ids?.length ? h("span", {}, `+${card.extra_source_ids.length} more`) : null,
      url ? h("a", { href: url, target: "_blank", rel: "noopener noreferrer" }, "feed") : null,
    ),
  );
}

function badges(card, sit, discIndex) {
  const byId = new Map(sit.discrepancies.map((d) => [d.id, d]));
  const items = (card.discrepancy_ids ?? [])
    .map((id) => byId.get(id))
    .filter(Boolean)
    .map((d) =>
      h(
        "li",
        { class: `badge badge--${d.severity}`, "aria-label": `Discrepancy ${discIndex.get(d.id)}: ${d.kind}, ${d.severity}` },
        h("span", { class: "badge__num" }, String(discIndex.get(d.id))),
        d.kind.replace("_", " "),
      ),
    );
  return items.length ? h("ul", { class: "badges" }, items) : null;
}

function discrepancyList(sit, discIndex, context) {
  const heading = h("h4", { class: "sub-head" }, `Where the sources differ (${sit.discrepancies.length})`);
  if (sit.discrepancies.length === 0) {
    return [heading, h("p", { class: "empty empty--inline" }, "No differences found by code between these products.")];
  }
  const rows = sit.discrepancies.map((d) =>
    h(
      "li",
      { class: `disc disc--${d.severity}`, id: context === "rail" ? `disc-${safeLayerId(d.id)}` : null },
      h("span", { class: "disc__num" }, String(discIndex.get(d.id))),
      h("span", { class: "disc__kind" }, d.kind.replace("_", " ")),
      h("span", { class: "disc__sev" }, d.severity),
      h("span", { class: "disc__summary" }, d.summary),
    ),
  );
  return [heading, h("ol", { class: "disc-list" }, rows), h("p", { class: "fine" }, "Classified by code, not by the model.")];
}

function plumeBlock(sit, discIndex) {
  const a = sit.assessment;
  const heading = h("h4", { class: "sub-head" }, "Plume reading");
  if (!a) return [heading, h("p", { class: "empty empty--inline" }, "No assessment yet for this volcano.")];
  const e = a.estimate;
  const ai = a.llm_backend === "gemini" && a.outcome !== "OFFICIAL_ONLY";
  const mark = ai
    ? h("span", { class: "ai-mark" }, `AI reading: ${a.model_id}`)
    : h("span", { class: "ai-mark ai-mark--none" }, a.llm_backend === "stub" ? "NO MODEL" : "No model call");
  const sector =
    e.mode === "OFFICIAL"
      ? "Sector not used (official polygons only)"
      : `Sector ${bearingText(e.bearing_from_deg)}-${bearingText(e.bearing_to_deg)} to ${Math.round(e.extent_km)} km`;
  const outcomeClass = a.outcome === "FALLBACK_OFFICIAL" ? " plume__outcome--warn" : "";

  const readings = (e.disagreements_explained ?? []).map((r) =>
    h(
      "li",
      {},
      h("span", { class: "disc__num" }, String(discIndex.get(r.discrepancy_id) ?? "?")),
      h("span", {}, r.reading),
      h("span", { class: "fine" }, ` Leans on ${r.which_source_we_lean_on}: ${r.why}`),
    ),
  );

  return [
    heading,
    h(
      "div",
      { class: `plume plume--${e.mode}` },
      h(
        "p",
        { class: "plume__line" },
        h("span", { class: `mode-chip mode-chip--${e.mode}` }, e.mode),
        h("span", { class: "plume__conf" }, `${percent(e.confidence)} confidence`),
        mark,
      ),
      h("p", { class: "plume__line" }, `Band ${bandText(e.base_fl * 100, e.top_fl * 100)} · ${sector} · ${e.horizon_h} h ahead`),
      h("p", { class: `plume__outcome${outcomeClass}` }, OUTCOME_LABEL[a.outcome] ?? a.outcome, a.attempts ? ` (${a.attempts} call${a.attempts > 1 ? "s" : ""})` : ""),
      e.rationale ? h("p", { class: "plume__rationale" }, e.rationale) : null,
      keptDetails(
        `plume:${a.id}`,
        "Uncertainty and readings of each difference",
        e.uncertainty_notes ? h("p", {}, e.uncertainty_notes) : null,
        readings.length ? h("ol", { class: "readings" }, readings) : h("p", { class: "fine" }, "No differences explained."),
        a.validation_errors?.length
          ? h("div", {}, h("p", { class: "fine" }, "Validator rejected the last attempt:"), h("ul", { class: "fine" }, a.validation_errors.map((err) => h("li", {}, err))))
          : null,
        h("p", { class: "fine" }, `Sources cited: ${(e.sources_used ?? []).join(", ") || "none"}`),
      ),
    ),
  ];
}

function exposedForVolcano(volcanoId) {
  return data.aircraft.features
    .map((f) => f.properties ?? {})
    .filter((props) => props.exposed === true && props.volcano_id === volcanoId)
    .sort((a, b) => (a.minutes_to_entry ?? 0) - (b.minutes_to_entry ?? 0));
}

function renderFlights() {
  const volcanoId = ui.selected;
  const flights = volcanoId ? exposedForVolcano(volcanoId) : [];
  renderSection("flights", [volcanoId, flights.map((f) => [f.hex, f.label, f.minutes_to_entry])], () => {
    if (!volcanoId) return [];
    const heading = h("h4", { class: "sub-head" }, `Flights entering the cone (${flights.length})`);
    if (flights.length === 0) {
      return [heading, h("p", { class: "empty empty--inline" }, "No airline aircraft enter the cone on their current track and level.")];
    }
    const items = flights.map((f) =>
      h(
        "li",
        {},
        h(
          "button",
          {
            type: "button",
            class: "flight-btn",
            dataset: { focusKey: `flight:${f.hex}` },
            onclick: () => focusFlight(f.hex, `${f.hex}:${volcanoId}`),
          },
          h("span", { class: "flight-btn__id" }, f.proxy_flight),
          h("span", { class: "flight-btn__cs" }, f.callsign ?? f.hex),
          h("span", { class: "flight-btn__fl" }, flText(f.alt_baro_ft)),
          h("span", { class: "flight-btn__eta" }, Number(f.minutes_to_entry) === 0 ? "INSIDE NOW" : `+${f.minutes_to_entry} MIN`),
        ),
      ),
    );
    return [heading, h("ul", { class: "flights" }, items)];
  });
}

function btdOverlayFor(volcanoId) {
  return (data.overlays?.btd ?? []).find((o) => o.volcano_id === volcanoId) ?? null;
}

function btdBlock(sit) {
  const btd = sit.btd;
  if (!btd) return [];
  const overlay = btdOverlayFor(sit.volcano_id);
  return [
    h("h4", { class: "sub-head" }, "Split-window BTD (Himawari-9)"),
    h(
      "div",
      { class: "btd" },
      h(
        "p",
        { class: "plume__line" },
        h("span", { class: `btd-chip btd-chip--${btd.indicator}` }, btd.indicator.replaceAll("_", " ")),
        h("span", {}, `${btd.band_pair} · scan ${hhmmz(parseTime(btd.scan_start))}`),
      ),
      h(
        "p",
        { class: "plume__line" },
        `${percent(btd.negative_fraction)} of ${Number(btd.pixel_count).toLocaleString("en-US")} pixels below ${btd.threshold_k} K · min ${Number(btd.min_btd_k).toFixed(1)} K`,
      ),
      btd.indicator === "SILENT" ? h("p", { class: "src-card__hint" }, "SILENT never means no ash.") : null,
      overlay ? h("p", { class: "fine" }, overlay.caption) : null,
      keptDetails(`btd:${btd.provenance?.source_id ?? sit.volcano_id}`, "Known blind spots", h("ul", { class: "fine" }, (btd.caveats ?? []).map((c) => h("li", {}, c)))),
      h("p", { class: "fine" }, "Himawari-9 data: JMA, distributed by NOAA (NODD / AWS Open Data); processed by TEPHRA."),
    ),
  ];
}

function framesBlock(sit) {
  const frames = sit.frames ?? [];
  if (frames.length === 0) return [];
  const figures = frames
    .map((frame) => ({ frame, url: sameOriginUrl(frame.image_url) }))
    .filter(({ url }) => url)
    .map(({ frame, url }) =>
      h(
        "figure",
        { class: "frame" },
        h("img", { src: url, alt: frame.caption, loading: "lazy", decoding: "async", width: "160", height: "120" }),
        h("figcaption", {}, `${frame.product.replaceAll("_", " ")} ${hhmmz(parseTime(frame.observed_at))} · ${frame.caption}`),
      ),
    );
  return [h("h4", { class: "sub-head" }, "Satellite frames (context only)"), h("div", { class: "frames" }, figures)];
}

/** Drop cards for volcanoes the server no longer lists as active. */
function pruneSituations() {
  const active = new Set(data.state?.active_volcano_ids ?? []);
  for (const id of [...data.situations.keys()]) {
    if (!active.has(id)) data.situations.delete(id);
  }
}

// --- compare dialog ---------------------------------------------------------------------

function openCompare() {
  const sit = ui.selected ? data.situations.get(ui.selected) : null;
  if (!sit) return;
  const dialog = $("compare-dialog");
  const discIndex = new Map(sit.discrepancies.map((d, i) => [d.id, i + 1]));
  $("compare-title").textContent = `${sit.volcano_name}: SIGMET, VONA and VAA side by side`;
  $("compare-body").replaceChildren(
    h("div", { class: "cards cards--wide" }, sit.cards.map((card) => sourceCard(card, sit, discIndex, "dialog"))),
    h("div", { class: "compare__disc" }, discrepancyList(sit, discIndex, "dialog")),
  );
  if (!dialog.open) dialog.showModal();
}

function closeCompare() {
  const dialog = $("compare-dialog");
  if (dialog.open) dialog.close();
}

// --- trace and advisories ---------------------------------------------------------------

function traceItem(event) {
  const at = parseTime(event.at);
  const tags = [event.volcano_id ? data.situations.get(event.volcano_id)?.volcano_name ?? event.volcano_id : null, event.flight_id]
    .filter(Boolean)
    .join(" · ");
  return h(
    "li",
    { class: `trace trace--${event.level ?? "info"}` },
    h("time", { class: "trace__time", datetime: event.at }, at === null ? "--:--:--Z" : clockText(at)),
    h("span", { class: "trace__stage" }, event.stage),
    h("span", { class: `trace__actor trace__actor--${event.actor}` }, event.actor),
    h("span", { class: "trace__msg" }, event.message),
    tags ? h("span", { class: "trace__tags" }, tags) : null,
  );
}

function nearBottom(node) {
  return node.scrollHeight - node.scrollTop - node.clientHeight < 40;
}

function renderTrace() {
  const list = $("trace-list");
  if (data.trace.length === 0) {
    list.replaceChildren(h("li", { class: "empty" }, "No reasoning steps yet. Each tick writes its steps here."));
  } else {
    list.replaceChildren(...data.trace.map(traceItem));
  }
  list.scrollTop = list.scrollHeight;
  $("trace-count").textContent = `${data.trace.length} steps`;
}

function appendTrace(event) {
  if (!event?.id || data.traceIds.has(event.id)) return;
  const list = $("trace-list");
  const stick = nearBottom(list);
  if (data.trace.length === 0) list.replaceChildren();
  data.trace.push(event);
  data.traceIds.add(event.id);
  list.append(traceItem(event));
  while (data.trace.length > TRACE_LIMIT) {
    const dropped = data.trace.shift();
    data.traceIds.delete(dropped.id);
    list.firstElementChild?.remove();
  }
  if (stick) list.scrollTop = list.scrollHeight;
  $("trace-count").textContent = `${data.trace.length} steps`;
}

function sortedAdvisories() {
  const time = (a) => parseTime(a.updated_at) ?? parseTime(a.created_at) ?? 0;
  return [...data.advisories.values()].sort((a, b) => {
    const draft = Number(b.status === "DRAFT") - Number(a.status === "DRAFT");
    return draft !== 0 ? draft : time(b) - time(a);
  });
}

function draftedBy(advisory) {
  if (advisory.llm_backend === "stub") return { text: "NO MODEL template", ai: false };
  if (advisory.validation_notes?.length) return { text: "Template (model draft rejected)", ai: false };
  return { text: `AI-drafted: ${advisory.model_id}`, ai: true };
}

function advisoryItem(advisory) {
  const created = parseTime(advisory.created_at);
  const drafted = draftedBy(advisory);
  const entry = advisory.inside_now ? "INSIDE NOW" : `ENTRY ${advisory.minutes_to_entry} MIN`;
  const decided = advisory.decided_by
    ? `${advisory.status === "EDITED" ? "Edited and approved" : advisory.status === "REJECTED" ? "Rejected" : "Approved"} by ${advisory.decided_by} ${hhmmz(parseTime(advisory.decided_at))}`
    : null;

  return h(
    "li",
    { class: `adv adv--${advisory.status}` },
    h(
      "div",
      { class: "adv__top" },
      h(
        "button",
        {
          type: "button",
          class: "adv__flight",
          dataset: { focusKey: `adv:${advisory.id}` },
          "aria-label": `Show ${advisory.proxy_flight} on the map`,
          onclick: () => focusFlight(advisory.hex, advisory.flight_id),
        },
        advisory.proxy_flight,
      ),
      h("span", { class: "adv__cs" }, advisory.callsign ?? advisory.hex),
      h("span", { class: "adv__action" }, actionText(advisory)),
      h("span", { class: `status status--${advisory.status}` }, advisory.status),
    ),
    h(
      "p",
      { class: "adv__meta" },
      h("span", { class: advisory.inside_now ? "adv__entry adv__entry--now" : "adv__entry" }, entry),
      h("span", {}, `${advisory.volcano_name} · ${advisory.plume_mode} ${percent(advisory.confidence)}`),
      h("span", { class: drafted.ai ? "ai-mark" : "ai-mark ai-mark--none" }, drafted.text),
      advisory.replay ? h("span", { class: "replay-tag" }, "REPLAY") : null,
      created !== null ? agoNode(created) : null,
    ),
    h("p", { class: "adv__body" }, advisory.final_body ?? advisory.body),
    advisory.fuel_line ? h("p", { class: "adv__fuel" }, advisory.fuel_line) : null,
    decided ? h("p", { class: "adv__decided" }, decided) : null,
    advisory.reject_reason ? h("p", { class: "adv__decided" }, `Reason: ${advisory.reject_reason}`) : null,
    keptDetails(
      `adv:${advisory.id}`,
      "Full advisory, sources and hashes",
      h("pre", { class: "adv__text", tabindex: "0" }, [advisory.header, advisory.final_body ?? advisory.body, advisory.cost_note].filter(Boolean).join("\n")),
      advisory.edited_body != null
        ? h("div", {}, h("p", { class: "fine" }, "As drafted before the dispatcher's edit:"), h("pre", { class: "adv__text adv__text--orig", tabindex: "0" }, advisory.body))
        : null,
      h(
        "ul",
        { class: "sources" },
        (advisory.sources ?? []).map((s) =>
          h("li", {}, `${FEED_LABEL[s.feed] ?? s.feed} ${s.source_id} · issued ${ddhhmmz(parseTime(s.issued_at))} · fetched ${ddhhmmz(parseTime(s.fetched_at))} · #${s.sha256_short}${s.stale ? " · STALE" : ""}`),
        ),
      ),
      advisory.validation_notes?.length ? h("ul", { class: "fine" }, advisory.validation_notes.map((n) => h("li", {}, n))) : null,
    ),
  );
}

function renderAdvisories() {
  const list = $("advisory-list");
  const advisories = sortedAdvisories().slice(0, ADVISORY_LIMIT);
  if (advisories.length === 0) {
    renderInto(list, [h("li", { class: "empty" }, "No advisories yet. Drafts appear here when a flight's track enters a cone.")]);
    return;
  }
  renderInto(list, advisories.map(advisoryItem));
}

function upsertAdvisory(advisory) {
  if (!advisory?.id) return;
  const previous = data.advisories.get(advisory.id);
  const known = previous !== undefined;
  if (known && Number(previous.version) > Number(advisory.version)) return;
  data.advisories.set(advisory.id, advisory);
  if (data.advisories.size > ADVISORY_LIMIT * 2) {
    const keep = new Set(sortedAdvisories().slice(0, ADVISORY_LIMIT * 2).map((a) => a.id));
    for (const id of [...data.advisories.keys()]) if (!keep.has(id)) data.advisories.delete(id);
  }
  renderAdvisories();
  if (!known && advisory.status === "DRAFT") {
    announce(`New draft advisory for ${advisory.proxy_flight}: ${actionText(advisory)}.`);
  } else if (known && previous.status !== advisory.status) {
    announce(`${advisory.proxy_flight} advisory ${advisory.status.toLowerCase()}.`);
  }
}

// --- data flow --------------------------------------------------------------------------

function applyState(state) {
  if (!state) return;
  data.state = state;
  syncClock(state.now);
  if (Array.isArray(state.feeds)) {
    data.feeds = state.feeds;
    data.feedsReceivedAt = performance.now();
  }
  if (!ui.viewInitialised && state.region) {
    ui.viewInitialised = true;
    fitRegion(state.region, false);
  }
}

function applySnapshot(snapshot) {
  if (!snapshot) return;
  for (const key of FEATURE_SECTIONS) data[key] = asCollection(snapshot[key]);
  data.situations = new Map((snapshot.situations ?? []).map((s) => [s.volcano_id, s]));
  data.overlays = snapshot.overlays ?? { btd: [], frames: [] };
}

function applyWall(wall) {
  applyState(wall.state);
  applySnapshot(wall.snapshot);
  data.advisories = new Map((wall.advisories ?? []).map((a) => [a.id, a]));
  data.trace = (wall.trace ?? []).slice(-TRACE_LIMIT);
  data.traceIds = new Set(data.trace.map((t) => t.id));
  ui.loaded = true;
  for (const name of Object.keys(ui.rendered)) ui.rendered[name] = "";

  renderTopBar();
  renderFeeds();
  for (const key of FEATURE_SECTIONS) pushSection(key);
  syncBtdOverlays();
  renderVolcanoTabs();
  renderSituation();
  renderTrace();
  renderAdvisories();
}

async function loadWall() {
  window.clearTimeout(ui.wallRetry);
  try {
    const response = await fetch(API_WALL, { headers: { Accept: "application/json" }, cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    applyWall(await response.json());
    const queued = ui.pendingEvents.splice(0);
    for (const [name, payload] of queued) handleEvent(name, payload);
    if (!mapReady && window.maplibregl) showMapMessage("");
  } catch (error) {
    $("sit-empty").hidden = false;
    $("sit-empty").textContent = `Could not load the Wall (${error.message}). Retrying in ${WALL_RETRY_MS / 1000} s.`;
    ui.wallRetry = window.setTimeout(loadWall, WALL_RETRY_MS);
  }
}

const SECTION_EVENTS = new Set(FEATURE_SECTIONS);

function handleEvent(name, payload) {
  if (!ui.loaded) {
    ui.pendingEvents.push([name, payload]);
    if (ui.pendingEvents.length > PENDING_LIMIT) ui.pendingEvents.shift();
    return;
  }
  if (SECTION_EVENTS.has(name)) {
    data[name] = asCollection(payload);
    pushSection(name);
    if (name === "aircraft") renderFlights();
    return;
  }
  switch (name) {
    case "state":
      applyState(payload);
      renderTopBar();
      renderFeeds();
      pruneSituations();
      renderVolcanoTabs();
      renderSituation();
      break;
    case "feeds":
      data.feeds = payload?.feeds ?? [];
      data.feedsReceivedAt = performance.now();
      renderFeeds();
      break;
    case "overlays":
      data.overlays = payload ?? { btd: [], frames: [] };
      syncBtdOverlays();
      renderSituation();
      break;
    case "situation":
      if (!payload?.volcano_id) return;
      data.situations.set(payload.volcano_id, payload);
      renderVolcanoTabs();
      renderSituation();
      break;
    case "trace":
      appendTrace(payload);
      break;
    case "advisory":
      upsertAdvisory(payload);
      break;
    case "heartbeat":
      syncClock(payload?.now);
      if (payload?.mode && data.state && payload.mode !== data.state.mode) loadWall();
      break;
    default:
      break;
  }
}

const STREAM_EVENTS = [...FEATURE_SECTIONS, "state", "feeds", "overlays", "situation", "trace", "advisory", "heartbeat"];

function connectStream() {
  window.clearTimeout(ui.streamReopen);
  setStreamStatus("connecting", "STREAM CONNECTING");
  const source = new EventSource(API_EVENTS);
  let hadError = false;

  for (const name of STREAM_EVENTS) {
    source.addEventListener(name, (message) => {
      let payload;
      try {
        payload = JSON.parse(message.data);
      } catch {
        return;
      }
      handleEvent(name, payload);
    });
  }
  source.addEventListener("open", () => {
    setStreamStatus("live", "STREAM LIVE");
    // After a drop, the server replays only what its history still holds; resync fully.
    if (hadError) loadWall();
    hadError = false;
  });
  source.addEventListener("error", () => {
    hadError = true;
    if (source.readyState === EventSource.CLOSED) {
      setStreamStatus("offline", "STREAM OFFLINE");
      ui.streamReopen = window.setTimeout(connectStream, STREAM_REOPEN_MS);
    } else {
      setStreamStatus("connecting", "STREAM RECONNECTING");
    }
  });
}

// --- timers, controls, keyboard ---------------------------------------------------------

function tickSecond() {
  $("clock").textContent = clockText(activeNow());
  for (const node of document.querySelectorAll("[data-until]")) {
    node.textContent = untilText(Number(node.dataset.until), node.dataset.prefix);
  }
  for (const node of document.querySelectorAll("[data-since]")) {
    node.textContent = agoText(Number(node.dataset.since));
  }
  renderFeeds();
}

function bindControls() {
  for (const box of document.querySelectorAll("input[data-layer]")) {
    box.addEventListener("change", () => setLayer(box.dataset.layer, box.checked));
  }
  const toggle = $("legend-toggle");
  toggle.addEventListener("click", () => toggleLegend());
  $("compare-open").addEventListener("click", openCompare);
  $("compare-close").addEventListener("click", closeCompare);
  $("compare-dialog").addEventListener("close", () => $("compare-open").focus());
  $("feeds").addEventListener("toggle", renderFeeds);
  document.addEventListener("keydown", onShortcut);
}

function toggleLegend(force) {
  const toggle = $("legend-toggle");
  const open = force ?? toggle.getAttribute("aria-expanded") !== "true";
  toggle.setAttribute("aria-expanded", String(open));
  $("legend-body").hidden = !open;
}

function onShortcut(event) {
  if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
  const target = event.target;
  if (target instanceof HTMLElement && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))) return;
  if ($("compare-dialog").open) return;
  const key = event.key.toLowerCase();
  const regions = data.state?.regions ?? [];
  if (/^[1-9]$/.test(key) && regions[Number(key) - 1]) {
    fitRegion(regions[Number(key) - 1], true);
  } else if (key === "b") {
    setLayer("btd", !ui.layers.btd);
  } else if (key === "c") {
    openCompare();
  } else if (key === "l") {
    toggleLegend();
  } else {
    return;
  }
  event.preventDefault();
}

function boot() {
  bindControls();
  initMap();
  renderTrace();
  renderAdvisories();
  connectStream();
  loadWall();
  window.setInterval(tickSecond, 1000);
  window.setInterval(() => pushSection("official"), OFFICIAL_RELABEL_MS);
}

boot();
