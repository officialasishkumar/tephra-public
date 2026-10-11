// The Wall map: MapLibre 4.7.1 layers in the order of docs/UI-DESIGN.md section 5, the
// direction rose (section 6), camera framing (7.4), satellite context (5.6), 3D and swipe
// compare (8.1, 8.2). Feed text reaches the map only as symbol text, never as HTML.

import { addExtLayers, updateExtLayers, setExtVisible } from "./ext-map.js";
import { addImages } from "./images.js";
import { officialLabelText, tephraLabelText, LEVEL_MAX } from "./derive.js";
import { GASES_SCOPE_SHORT } from "./glossary.js";
import {
  $, el, band, bboxOf, compassWord, dest, fc, hhmmz, kmBetween, ms, reducedMotion, ringCentre, ringsOf, dayMon,
} from "./util.js";

const STYLE_URL = "https://tiles.openfreemap.org/styles/dark";
const FONT_BOLD = ["Noto Sans Bold"];
const FONT_REG = ["Noto Sans Regular"];
const CODE_SIZE = { RED: 1.0, ORANGE: 0.92, YELLOW: 0.84, GREEN: 0.76, UNKNOWN: 0.76 };
const ANT_STEPS = [
  [0, 4, 3], [0.5, 4, 2.5], [1, 4, 2], [1.5, 4, 1.5], [2, 4, 1], [2.5, 4, 0.5], [3, 4, 0],
  [0, 0.5, 3, 3.5], [0, 1, 3, 3], [0, 1.5, 3, 2.5], [0, 2, 3, 2], [0, 2.5, 3, 1.5], [0, 3, 3, 1], [0, 3.5, 3, 0.5],
];
// The WebGL buffer is kept only for automated screenshots (?shots=1, 7.4); it costs memory and
// a copy per frame otherwise.
const SHOTS = new URLSearchParams(window.location.search).get("shots") === "1";
const STEP_STYLE = {
  now: { fill: 0.14, w: 2.6, dash: null, op: 1 },
  f6: { fill: 0.05, w: 2, dash: [4, 2], op: 0.9 },
  f12: { fill: 0.035, w: 1.8, dash: [2, 2], op: 0.75 },
  f18: { fill: 0.025, w: 1.8, dash: [0.1, 2], op: 0.6 },
};
export const SAT = {
  ir: { layer: "Himawari_AHI_Band13_Clean_Infrared", matrix: "GoogleMapsCompatible_Level6", maxzoom: 6, title: "Himawari-9 infrared (band 13)", short: "Infrared" },
  vis: { layer: "Himawari_AHI_Band3_Red_Visible_1km", matrix: "GoogleMapsCompatible_Level7", maxzoom: 7, title: "Himawari-9 visible (band 3), daylight only", short: "Visible" },
  airmass: { layer: "Himawari_AHI_Air_Mass", matrix: "GoogleMapsCompatible_Level6", maxzoom: 6, title: "Himawari-9 Air Mass RGB", short: "Air mass" },
};
// Aircraft icon size (5.3): exposed aircraft stay 0.7 at every zoom; background traffic is
// thinned when zoomed out, so a busy region does not bury the flights that matter.
const AC_SIZE = ["interpolate", ["linear"], ["zoom"], 3, ["case", ["get", "exposed"], 0.7, 0.3], 6, ["case", ["get", "exposed"], 0.7, 0.42], 8, ["case", ["get", "exposed"], 0.7, 0.5]];
const GIBS = (layer, time, matrix) => `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${layer}/default/${time}/${matrix}/{z}/{y}/{x}.png`;

// GIBS TIME follows TEPHRA's active clock, never the browser's (section 5.6).
export function gibsTime(nowMs, mode, back = 0) {
  let t = Math.floor((nowMs - (mode === "LIVE" ? 3600e3 : 0)) / 600e3) * 600e3 - back * 600e3;
  const d = new Date(t);
  if (d.getUTCMinutes() === 40 && (d.getUTCHours() === 2 || d.getUTCHours() === 14)) t -= 600e3;
  return new Date(t).toISOString().slice(0, 19) + "Z";
}
export const so2Date = (nowMs, mode) => new Date(nowMs - (mode === "LIVE" ? 86400e3 : 7 * 3600e3)).toISOString().slice(0, 10);

export function readTokens() {
  const css = getComputedStyle(document.documentElement);
  const tok = (name) => css.getPropertyValue(name).trim();
  return {
    official: tok("--c-official"), officialText: tok("--c-official-text"),
    tephra: tok("--c-tephra"), tephraText: tok("--c-tephra-text"),
    observer: tok("--c-observer"), observerText: tok("--c-observer-text"),
    aircraft: tok("--c-aircraft"), stale: tok("--c-aircraft-stale"),
    land: tok("--map-land"), water: tok("--map-water"), halo: tok("--map-halo"), label: tok("--map-label"),
    fir: tok("--map-fir"), firActive: tok("--map-fir-active"), vaac: tok("--map-vaac"), navaid: tok("--map-navaid"),
    labelMinor: tok("--map-label-minor"), labelFir: tok("--map-label-fir"), labelVaac: tok("--map-label-vaac"),
    text1: tok("--c-text-1"), text2: tok("--c-text-2"), text3: tok("--c-text-3"),
    ok: tok("--c-ok"), serious: tok("--c-serious"),
    codes: {
      GREEN: tok("--c-code-green"), YELLOW: tok("--c-code-yellow"), ORANGE: tok("--c-code-orange"),
      RED: tok("--c-code-red"), UNKNOWN: tok("--c-code-unknown"),
    },
  };
}

const empty = () => fc([]);
const before = (map, id) => (map.getLayer(id) ? id : undefined);

// ------------------------------------------------------------------ layer builders

function tuneBasemap(map, C, ui) {
  if (map.getLayer("water")) map.setPaintProperty("water", "fill-color", C.water);
  if (map.getLayer("landuse_park")) map.setPaintProperty("landuse_park", "fill-opacity", 0.35);
  for (const id of ["place_city", "place_city_large", "place_town"]) if (map.getLayer(id)) map.setPaintProperty(id, "text-color", C.labelMinor);
  const vis = ui.layers.terrain ? "visible" : "none";
  if (map.getSource("ne2_shaded") && !map.getLayer("ne2-relief")) {
    map.addLayer({ id: "ne2-relief", type: "raster", source: "ne2_shaded", maxzoom: 8, paint: { "raster-saturation": -1, "raster-contrast": 0.15, "raster-brightness-max": 0.45, "raster-opacity": 0.5 } }, before(map, "water"));
  }
  if (!map.getSource("dem")) {
    map.addSource("dem", { type: "raster-dem", tiles: ["https://tiles.mapterhorn.com/{z}/{x}/{y}.webp"], encoding: "terrarium", tileSize: 512, maxzoom: 12, attribution: "© Mapterhorn" });
  }
  if (!map.getLayer("hillshade")) {
    map.addLayer({ id: "hillshade", type: "hillshade", source: "dem", minzoom: 5, layout: { visibility: vis }, paint: { "hillshade-exaggeration": 0.45, "hillshade-shadow-color": "#000000", "hillshade-highlight-color": "#2a3442", "hillshade-accent-color": "#05070a" } }, before(map, "waterway"));
  }
}

function addContext(map, C, ui, noText) {
  map.addSource("firs", { type: "geojson", data: "/static/data/firs.geojson" });
  map.addSource("vaac", { type: "geojson", data: "/static/data/vaac_aor.geojson" });
  map.addSource("navaids", { type: "geojson", data: "/static/data/navaids.geojson" });
  const ctxVis = ui.layers.context ? "visible" : "none";
  map.addLayer({ id: "fir-line", type: "line", source: "firs", layout: { visibility: ctxVis }, paint: { "line-color": C.fir, "line-width": 1 } });
  map.addLayer({ id: "fir-active", type: "line", source: "firs", filter: ["in", ["get", "icao"], ["literal", []]], layout: { visibility: ctxVis }, paint: { "line-color": C.firActive, "line-width": 1.6 } });
  map.addLayer({ id: "vaac-line", type: "line", source: "vaac", layout: { visibility: ctxVis }, paint: { "line-color": C.vaac, "line-width": 1.2, "line-dasharray": [6, 3, 1, 3] } });
  if (!noText) {
    const lab = { "symbol-placement": "line", "symbol-spacing": 700, "text-field": ["get", "label"], "text-font": FONT_REG, "text-size": 12, "text-letter-spacing": 0.08, "text-offset": [0, 0.8], visibility: ctxVis };
    map.addLayer({ id: "fir-label", type: "symbol", source: "firs", minzoom: 5, layout: lab, paint: { "text-color": C.labelFir, "text-halo-color": C.halo, "text-halo-width": 1.5 } });
    map.addLayer({ id: "vaac-label", type: "symbol", source: "vaac", minzoom: 3, layout: { ...lab, "symbol-spacing": 900 }, paint: { "text-color": C.labelVaac, "text-halo-color": C.halo, "text-halo-width": 1.5 } });
  }
  const navVis = ui.layers.navaids ? "visible" : "none";
  map.addLayer({ id: "navaid", type: "circle", source: "navaids", minzoom: 8, layout: { visibility: navVis }, paint: { "circle-radius": 3, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": C.navaid, "circle-stroke-width": 1.2 } });
  if (!noText) map.addLayer({ id: "navaid-label", type: "symbol", source: "navaids", minzoom: 8, layout: { visibility: navVis, "text-field": ["get", "ident"], "text-font": FONT_REG, "text-size": 12, "text-offset": [0, 0.9], "text-anchor": "top", "text-optional": true }, paint: { "text-color": C.navaid, "text-halo-color": C.halo, "text-halo-width": 1.5 } });
}

// The hazard and traffic layers. `withTephra` false builds the compare map's "official only" side.
function addHazard(map, C, ui, { withTephra = true, noText = false } = {}) {
  for (const id of ["official", "cones", "exposures", "aircraft", "volcanoes", "official-labels", "area-labels", "rose", "ac3d"]) map.addSource(id, { type: "geojson", data: empty() });
  // Exposed flights again, clustered for their labels only (R6.3): every plane is still drawn by
  // aircraft-icon; more than five labels within 60 px merge into one "8 RFA flights" bubble.
  if (withTephra) map.addSource("exposed-pts", { type: "geojson", data: empty(), cluster: true, clusterRadius: 60, clusterMinPoints: 6, clusterMaxZoom: 11 });
  const fade = (base) => ["*", base, ["coalesce", ["get", "fade"], 1]];
  const tVis = ui.layers.tephra ? "visible" : "none";
  if (withTephra) {
    map.addLayer({ id: "tephra-fill", type: "fill", source: "cones", filter: ["==", ["get", "part"], "cone"], layout: { visibility: tVis }, paint: { "fill-color": C.tephra, "fill-opacity": fade(0.07) } });
    map.addLayer({ id: "tephra-hatch", type: "fill", source: "cones", filter: ["==", ["get", "part"], "sector"], layout: { visibility: tVis }, paint: { "fill-pattern": "hatch-tephra", "fill-opacity": fade(1) } });
  }
  for (const [step, s] of Object.entries(STEP_STYLE)) {
    const filter = ["all", ["==", ["get", "step"], step], ["==", ["get", "show"], true]];
    const fillFilter = step === "now" ? ["all", filter, ["==", ["get", "fill"], true]] : filter;
    map.addLayer({ id: `official-fill-${step}`, type: "fill", source: "official", filter: fillFilter, paint: { "fill-color": C.official, "fill-opacity": fade(s.fill) } });
  }
  for (const [step, s] of Object.entries(STEP_STYLE)) {
    const filter = ["all", ["==", ["get", "step"], step], ["==", ["get", "show"], true]];
    const paint = { "line-color": C.official, "line-width": ["interpolate", ["linear"], ["zoom"], 4, s.w * 0.6, 8, s.w], "line-opacity": ["*", s.op, ["coalesce", ["get", "lfade"], ["get", "fade"], 1]] };
    if (s.dash) paint["line-dasharray"] = s.dash;
    map.addLayer({ id: `official-line-${step}`, type: "line", source: "official", filter, layout: { "line-join": "round", "line-cap": step === "f18" ? "round" : "butt" }, paint });
  }
  if (withTephra) {
    map.addLayer({ id: "tephra-line", type: "line", source: "cones", filter: ["==", ["get", "part"], "cone"], layout: { "line-join": "round", visibility: tVis }, paint: { "line-color": C.tephra, "line-width": ["interpolate", ["linear"], ["zoom"], 4, ["case", ["get", "sel"], 1.6, 1.4], 8, ["case", ["get", "sel"], 2.6, 1.4]], "line-dasharray": [3, 2], "line-offset": -5, "line-opacity": fade(1) } });
    const pVis = ui.layers.paths ? "visible" : "none";
    map.addLayer({ id: "exposure-path", type: "line", source: "exposures", filter: ["==", ["get", "kind"], "path"], layout: { visibility: pVis, "line-cap": "butt" }, paint: { "line-color": C.tephra, "line-width": 2.4, "line-dasharray": [1.5, 1.5] } });
    const entry = ["all", ["==", ["get", "kind"], "entry"], [">", ["coalesce", ["get", "minutes_to_entry"], 0], 0]];
    map.addLayer({ id: "exposure-entry", type: "circle", source: "exposures", filter: entry, layout: { visibility: pVis }, paint: { "circle-radius": 6, "circle-color": C.halo, "circle-stroke-color": C.tephra, "circle-stroke-width": 2.5 } });
    if (!noText) map.addLayer({ id: "exposure-entry-label", type: "symbol", source: "exposures", filter: entry, layout: { visibility: pVis, "text-field": ["concat", ["to-string", ["get", "minutes_to_entry"]], " MIN"], "text-font": FONT_BOLD, "text-size": 13, "text-variable-anchor": ["bottom", "top", "left", "right"], "text-radial-offset": 0.9, "symbol-sort-key": ["coalesce", ["get", "minutes_to_entry"], 999] }, paint: { "text-color": C.tephraText, "text-halo-color": C.halo, "text-halo-width": 2 } });
  }
  // volcanoes
  map.addLayer({ id: "volcano-inactive", type: "symbol", source: "volcanoes", filter: ["!", ["get", "active"]], layout: { "icon-image": "volcano-inactive", "icon-size": 0.5, "icon-allow-overlap": true, ...(noText ? {} : { "text-field": ["step", ["zoom"], "", 7.5, ["case", ["get", "near_sel"], "", ["get", "name"]]], "text-font": FONT_REG, "text-size": 12, "text-offset": [0, 1.1], "text-anchor": "top", "text-optional": true }) }, paint: { "icon-opacity": 0.8, "text-color": C.labelMinor, "text-halo-color": C.halo, "text-halo-width": 1.5 } });
  map.addLayer({ id: "volcano-active", type: "symbol", source: "volcanoes", filter: ["get", "active"], layout: { "icon-image": ["concat", "volcano-", ["get", "color_code"]], "icon-size": ["match", ["get", "color_code"], "RED", CODE_SIZE.RED, "ORANGE", CODE_SIZE.ORANGE, "YELLOW", CODE_SIZE.YELLOW, CODE_SIZE.GREEN], "icon-allow-overlap": true, "icon-ignore-placement": true, ...(noText ? {} : { "text-field": ["case", ["get", "named_by_area"], "", ["get", "name"]], "text-font": FONT_BOLD, "text-size": ["case", ["get", "sel"], 16, 14], "text-anchor": ["coalesce", ["get", "anchor"], "top"], "text-radial-offset": ["case", ["get", "sel"], 2.6, 1.35], "text-optional": true }) }, paint: { "text-color": C.label, "text-halo-color": C.halo, "text-halo-width": 2.5 } });
  // aircraft
  const acVis = ui.layers.aircraft ? "visible" : "none";
  map.addLayer({ id: "aircraft-icon", type: "symbol", source: "aircraft", layout: { visibility: acVis, "icon-image": "ac-sdf", "icon-size": AC_SIZE, "icon-rotate": ["coalesce", ["get", "track_deg"], 0], "icon-rotation-alignment": "map", "icon-allow-overlap": true, "icon-ignore-placement": true, "symbol-sort-key": ["case", ["get", "exposed"], 1, 0] }, paint: { "icon-color": withTephra ? ["case", ["get", "exposed"], C.tephra, ["get", "stale"], C.stale, C.aircraft] : ["case", ["get", "stale"], C.stale, C.aircraft], "icon-halo-color": C.halo, "icon-halo-width": 1.5, "icon-opacity": withTephra ? ["case", ["all", ["get", "exposed"], ["get", "stale"]], 0.8, ["get", "stale"], 0.55, 1] : ["case", ["get", "stale"], 0.55, 1] } });
  if (!noText) map.addLayer({ id: "aircraft-label", type: "symbol", source: "aircraft", minzoom: 7.5, filter: withTephra ? ["!=", ["get", "exposed"], true] : ["literal", true], layout: { visibility: ui.layers.acLabels && ui.layers.aircraft ? "visible" : "none", "text-field": ["get", "short"], "text-font": FONT_REG, "text-size": 12, "text-offset": [0, 1.2], "text-anchor": "top", "text-optional": true }, paint: { "text-color": C.text3, "text-halo-color": C.halo, "text-halo-width": 1.5 } });
  if (withTephra) {
    // the inside-now ring from zoom 6: zoomed out, the flight cluster speaks for the group
    map.addLayer({ id: "aircraft-inside", type: "circle", source: "aircraft", minzoom: 6, filter: ["==", ["get", "inside"], true], layout: { visibility: acVis }, paint: { "circle-radius": 18, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": C.tephra, "circle-stroke-width": 2 } });
    // The aircraft picked by the viewer (7.8): a white ring outside the inside-now ring.
    map.addLayer({ id: "aircraft-picked", type: "circle", source: "aircraft", filter: ["==", ["get", "picked"], true], layout: { visibility: acVis }, paint: { "circle-radius": 23, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": C.text1, "circle-stroke-width": 2.5 } });
    // One line per entering flight, right of the plane, from zoom 6 (R6.3). Labels collide;
    // a cluster of six or more becomes an amber bubble with its count.
    if (!noText) {
      // a cluster is one amber box with its count; its padding gives a 44 px hit area (R14.4)
      map.addLayer({ id: "exposed-cluster", type: "symbol", source: "exposed-pts", filter: ["has", "point_count"], layout: { visibility: acVis, "icon-image": "box-tephra", "icon-text-fit": "both", "icon-text-fit-padding": [15, 12, 15, 12], "text-field": ["concat", ["to-string", ["get", "point_count"]], " RFA flights"], "text-font": FONT_BOLD, "text-size": 13, "text-allow-overlap": false, "icon-allow-overlap": false, "symbol-sort-key": 0 }, paint: { "text-color": C.tephraText } });
      map.addLayer({ id: "aircraft-label-exposed", type: "symbol", source: "exposed-pts", minzoom: 6, filter: ["!", ["has", "point_count"]], layout: { visibility: acVis, "text-field": ["get", "elabel"], "text-font": FONT_BOLD, "text-size": 13, "text-anchor": "left", "text-offset": [1.4, 0], "text-padding": 4, "text-allow-overlap": false, "symbol-sort-key": ["+", ["case", ["get", "is_sel_vid"], 0, 1000], ["case", ["get", "inside"], 0, ["coalesce", ["get", "minutes_to_entry"], 999]]] }, paint: { "text-color": C.tephraText, "text-halo-color": C.halo, "text-halo-width": 2 } });
    }
  }
  // labels last (R6.3). The selected volcano's official label is never hidden by collision; every
  // other label (other volcanoes' names, TEPHRA's tag, forecast steps) collides and may drop out.
  if (!noText) {
    map.addLayer({ id: "official-step-label", type: "symbol", source: "official-labels", filter: ["==", ["get", "kind"], "step"], layout: { "text-field": ["get", "text"], "text-font": FONT_BOLD, "text-size": 13, "text-variable-anchor": ["center", "bottom", "top", "left", "right"], "text-radial-offset": 0.8, "text-allow-overlap": false, "symbol-sort-key": 8 }, paint: { "text-color": C.officialText, "text-halo-color": C.halo, "text-halo-width": 2 } });
    map.addLayer({ id: "official-label", type: "symbol", source: "official-labels", filter: ["==", ["get", "kind"], "name"], layout: { "text-field": ["get", "line1"], "text-font": FONT_BOLD, "text-size": 12, "text-anchor": "bottom", "text-offset": [0, -0.4], "text-allow-overlap": false, "symbol-sort-key": 10 }, paint: { "text-color": C.officialText, "text-halo-color": C.halo, "text-halo-width": 2 } });
    if (withTephra) map.addLayer({ id: "tephra-label", type: "symbol", source: "area-labels", layout: { visibility: tVis, "icon-image": "box-tephra", "icon-text-fit": "both", "icon-text-fit-padding": [5, 9, 5, 9], "text-field": ["get", "line1"], "text-font": FONT_BOLD, "text-size": ["get", "size"], "text-max-width": 40, "text-anchor": ["get", "anchor"], "text-offset": ["get", "offset"], "icon-allow-overlap": false, "text-allow-overlap": false, "symbol-sort-key": 5 }, paint: { "text-color": C.tephraText } });
    map.addLayer({ id: "official-label-selected", type: "symbol", source: "official-labels", filter: ["==", ["get", "kind"], "box"], layout: { "icon-image": "box-official", "icon-text-fit": "both", "icon-text-fit-padding": [5, 9, 5, 9], "text-field": ["case", ["==", ["get", "line2"], ""], ["format", ["get", "line1"], { "text-color": C.officialText }], ["format", ["get", "line1"], { "text-color": C.officialText }, "\n", {}, ["get", "line2"], { "text-color": C.text1, "font-scale": 0.9 }]], "text-font": FONT_BOLD, "text-size": ["get", "size"], "text-max-width": 40, "text-justify": "left", "text-anchor": ["get", "anchor"], "text-offset": ["get", "offset"], "icon-allow-overlap": true, "text-allow-overlap": true, "symbol-sort-key": 0 } });
  }
  if (withTephra) addRoseLayers(map, C, ui, noText);
}

function addRoseLayers(map, C, ui, noText) {
  const role = (r) => ["==", ["get", "role"], r];
  const vis = ui.layers.rose ? "visible" : "none";
  map.addLayer({ id: "rose-casing", type: "line", source: "rose", filter: ["in", ["get", "role"], ["literal", ["off", "obs", "arc"]]], layout: { "line-cap": "round", visibility: vis }, paint: { "line-color": ["match", ["get", "role"], "off", "#05070a", C.halo], "line-width": ["match", ["get", "role"], "arc", 5, "off", 9, 8], "line-opacity": 1 } });
  map.addLayer({ id: "rose-arc", type: "line", source: "rose", filter: role("arc"), layout: { visibility: vis }, paint: { "line-color": C.text1, "line-width": 1.6 } });
  map.addLayer({ id: "rose-off", type: "line", source: "rose", filter: role("off"), layout: { visibility: vis }, paint: { "line-color": C.officialText, "line-width": 3.6 } });
  map.addLayer({ id: "rose-obs", type: "line", source: "rose", filter: role("obs"), layout: { visibility: vis }, paint: { "line-color": C.observer, "line-width": 3.4, "line-dasharray": [2, 1.6] } });
  map.addLayer({ id: "rose-probe", type: "circle", source: "rose", filter: role("probe"), layout: { visibility: vis }, paint: { "circle-radius": 5, "circle-color": C.halo, "circle-stroke-color": C.observer, "circle-stroke-width": 2.5 } });
  map.addLayer({ id: "rose-heads", type: "symbol", source: "rose", filter: ["in", ["get", "role"], ["literal", ["off-head", "obs-head"]]], layout: { visibility: vis, "icon-image": "arrowhead", "icon-size": ["match", ["get", "role"], "off-head", 1.25, 0.62], "icon-rotate": ["get", "bearing"], "icon-rotation-alignment": "map", "icon-allow-overlap": true, "icon-ignore-placement": true }, paint: { "icon-color": ["match", ["get", "role"], "off-head", C.officialText, C.observer], "icon-halo-color": ["match", ["get", "role"], "off-head", "#05070a", C.halo], "icon-halo-width": ["match", ["get", "role"], "off-head", 2, 1.5] } });
  if (noText) return;
  map.addLayer({ id: "rose-labels", type: "symbol", source: "rose", filter: role("obs-head"), layout: { visibility: vis, "text-field": ["format", ["get", "line1"], { "text-color": C.observerText }, "\n", {}, ["get", "line2"], { "text-color": C.text2, "font-scale": 0.85 }], "text-font": FONT_BOLD, "text-size": ["get", "size"], "text-variable-anchor": ["left", "right", "top", "bottom"], "text-radial-offset": 1.1, "text-justify": "auto", "text-max-width": 30 }, paint: { "text-halo-color": C.halo, "text-halo-width": 2 } });
  map.addLayer({ id: "rose-angle", type: "symbol", source: "rose", filter: role("angle"), layout: { visibility: vis, "icon-image": "box-angle", "icon-text-fit": "both", "icon-text-fit-padding": [3, 7, 3, 7], "text-field": ["get", "text"], "text-font": FONT_BOLD, "text-size": ["get", "size"], "icon-allow-overlap": false, "text-allow-overlap": false, "symbol-sort-key": 1 }, paint: { "text-color": C.text1 } });
}

// ------------------------------------------------------------------ the Wall map

export class WallMap {
  constructor({ container, C, ui, onFeature, onReady, onNote }) {
    this.C = C;
    this.ui = ui;
    this.onFeature = onFeature;
    this.onReady = onReady;
    this.onNote = onNote;
    this.D = null;
    this.loaded = false;
    this.noText = false;
    this.framedOnce = false;
    this.flownFlights = null;
    this.gibs = { key: null, back: 0, errors: 0 };
    this.btdIds = [];
    this.pulseKey = null;
    this.compare = null;
    this.compareMap = null;
    this.sent = new Map();
    this.compareSent = new Map();
    this.container = container;
    this.map = new window.maplibregl.Map({
      container, style: STYLE_URL, center: [111, -7.6], zoom: 5.5, maxPitch: 70,
      attributionControl: false, dragRotate: false, pitchWithRotate: false, fadeDuration: 150,
      preserveDrawingBuffer: SHOTS, keyboard: true,
    });
    this.map.touchZoomRotate.disableRotation();
    window.__tephra = Object.freeze({ map: this.map });
    // Bottom-right, stacked by MapLibre: the OpenStreetMap credit (always, never compact; R6.6),
    // zoom and compass, then Fit and Layers (#tools, a custom control) on top.
    this.map.addControl(new window.maplibregl.AttributionControl({ compact: false }), "bottom-right");
    this.nav = new window.maplibregl.NavigationControl({ showCompass: true, visualizePitch: true });
    this.map.addControl(this.nav, "bottom-right");
    const tools = $("tools");
    if (tools) this.map.addControl({ onAdd: () => tools, onRemove: () => {} }, "bottom-right");
    this.map.on("styleimagemissing", (e) => {
      if (!this.map.hasImage(e.id)) this.map.addImage(e.id, { width: 1, height: 1, data: new Uint8Array(4) });
    });
    this.map.on("error", (e) => this.onError(e));
    this.map.on("style.load", () => this.onStyle());
    this.map.on("zoomend", () => { if (this.D) { this.updateRose(); this.updateLabels(); } });
    this.map.on("click", (e) => this.onClick(e));
    this.styleTimer = setTimeout(() => { if (!this.loaded) this.fallbackStyle(); }, 8000);
    const pulseNode = el("div", { class: "pulse", "aria-hidden": "true" });
    pulseNode.addEventListener("animationend", (e) => { if (e.pseudoElement === "::after" && pulseNode.classList.contains("pulse--rose")) pulseNode.classList.add("pulse--done"); });
    this.pulse = new window.maplibregl.Marker({ element: pulseNode, anchor: "center" });
    this.startAnts();
    new ResizeObserver(() => { if (this.framedOnce) this.frame({ animate: false }); }).observe(container);
  }

  onError(e) {
    const msg = e?.error?.message || "";
    if (e?.sourceId === "gibs" || /gibs\.earthdata/.test(msg)) { this.gibsMiss(); return; }
    if (e?.sourceId === "so2" || e?.sourceId === "dem" || e?.sourceId === "ne2_shaded") return;
    if (!this.loaded && !this.fallbackUsed) {
      // the basemap style itself failed
      clearTimeout(this.styleTimer);
      this.fallbackStyle();
    }
  }

  fallbackStyle() {
    if (this.fallbackUsed) return;
    this.fallbackUsed = true;
    this.noText = true;
    this.loaded = false;
    this.map.setStyle({
      version: 8,
      sources: { land: { type: "geojson", data: "/static/data/land_apac.geojson" } },
      layers: [
        { id: "background", type: "background", paint: { "background-color": this.C.water } },
        { id: "land", type: "fill", source: "land", paint: { "fill-color": "#15181c" } },
        { id: "coast", type: "line", source: "land", paint: { "line-color": "#2a3442", "line-width": 1 } },
      ],
    });
    this.onNote?.("basemap", "Basemap offline: simplified coastline (Natural Earth)");
  }

  onStyle() {
    const map = this.map;
    clearTimeout(this.styleTimer);
    try {
      if (!this.noText) tuneBasemap(map, this.C, this.ui);
      addImages(map, this.C);
      addContext(map, this.C, this.ui, this.noText);
      addHazard(map, this.C, this.ui, { noText: this.noText });
      addExtLayers(map, this.noText, this.ui.layers.reroutes);
      setExtVisible(map, true, this.ui.layers.satboxes);
      this.loaded = true;
      if (!this.hoverBound) {
        this.hoverBound = true;
        for (const id of ["aircraft-icon", "exposed-cluster", "volcano-active", "official-fill-now", "tephra-fill", "reroute-line", "reroute-wp"]) {
          map.on("mouseenter", id, () => { map.getCanvas().style.cursor = "pointer"; });
          map.on("mouseleave", id, () => { map.getCanvas().style.cursor = ""; });
        }
      }
      this.gibs.key = null;
      this.btdIds = [];
      this.sent.clear();
      if (this.D) this.update(this.D);
    } catch (err) {
      console.error("TEPHRA map setup failed", err);
    }
  }

  // ---------------------------------------------------------------- data

  update(D) {
    this.D = D;
    if (!this.loaded) return;
    const map = this.map;
    this.send("official", fc(D.official));
    this.send("cones", fc(D.cones));
    this.send("exposures", D.exposures);
    this.send("aircraft", fc(D.aircraft));
    if (map.getSource("exposed-pts")) this.send("exposed-pts", fc(D.exposed.map((f) => ({ type: "Feature", geometry: f.geometry, properties: { hex: f.properties.hex, volcano_id: f.properties.volcano_id, elabel: f.properties.elabel, inside: f.properties.inside, minutes_to_entry: f.properties.minutes_to_entry, is_sel_vid: f.properties.volcano_id === D.selected } }))));
    map.setFilter("fir-active", ["in", ["get", "icao"], ["literal", D.firsWithSigmet]]);
    this.updateExt();
    this.updateVolcanoes();
    this.updateRose();
    this.updateLabels();
    this.updatePulse();
    this.updateSat();
    this.updateBtd();
    if (this.ui.d3) this.update3d();
    if (this.compareMap) this.updateCompare();
    if (!this.framedOnce && D.sit) {
      this.framedOnce = true;
      this.frame({ animate: false });
      this.waitReady();
    } else if (!this.framedOnce && !D.sit && D.state.region) {
      this.framedOnce = true;
      this.flyRegion(D.state.region, false);
      this.waitReady();
    }
    this.followNewFlights();
  }

  // setData only when the derived data changed. derive() rebuilds every feature on each render
  // (time-dependent valid, show and age values), so the serialised result is compared, never the
  // store object; a timer render with nothing changed then sends nothing.
  send(id, data, map = this.map, sent = this.sent) {
    const json = JSON.stringify(data);
    if (sent.get(id) === json) return;
    map.getSource(id).setData(data);
    sent.set(id, json);
  }

  // reroutes and Satellite check boxes: data comes from the store, set by wall.js
  setExt(data) {
    this.extData = data;
    if (this.loaded) this.updateExt();
  }

  updateExt() {
    if (this.extData) updateExtLayers(this.map, { ...this.extData, selectedVid: this.D?.selected });
  }

  waitReady() {
    const check = () => {
      if (this.map.isStyleLoaded() && this.map.areTilesLoaded()) {
        document.body.dataset.mapReady = "true";
        this.onReady?.();
        return;
      }
      setTimeout(check, 250);
    };
    setTimeout(check, 300);
  }

  updateVolcanoes() {
    const D = this.D;
    // the selected volcano's name goes opposite the rose arrows' mean bearing
    let selAnchor = "top", selOffset = [0, 1.5];
    const side = (away) => (away >= 45 && away < 135 ? ["left", [1.7, 0]] : away >= 135 && away < 225 ? ["top", [0, 1.5]] : away >= 225 && away < 315 ? ["right", [-1.7, 0]] : ["bottom", [0, -1.6]]);
    const vent = D.sit && D.vents.get(D.sit.volcano_id);
    if (D.rose) {
      const diff = ((D.rose.obsDeg - D.rose.offDeg + 540) % 360) - 180;
      [selAnchor, selOffset] = side((D.rose.offDeg + diff / 2 + 180 + 360) % 360);
    } else if (vent) {
      // no rose: keep the name off the flights' entry points near the vent (5.3, 5.4)
      const near = (D.exposures.features || []).filter((f) => f.properties.kind === "entry" && f.properties.volcano_id === D.sit.volcano_id && kmBetween(f.geometry.coordinates, vent) < 60);
      if (near.length) {
        let x = 0, y = 0;
        for (const f of near) {
          const [lon, lat] = f.geometry.coordinates;
          x += (lon - vent[0]) * Math.cos((vent[1] * Math.PI) / 180);
          y += lat - vent[1];
        }
        const towards = ((Math.atan2(x, y) * 180) / Math.PI + 360) % 360;
        [selAnchor, selOffset] = side((towards + 180) % 360);
      }
    }
    // A non-selected volcano with an official area is named by that area's label (R6.3), so its
    // vent name is left out rather than drawn twice.
    const named = new Set(D.official.filter((f) => f.properties.show && f.properties.step === "now" && f.properties.valid && !f.properties.sel).map((f) => f.properties.volcano_id));
    const feats = D.volcanoes.map((f) => (f.properties.sel
      ? { ...f, properties: { ...f.properties, anchor: selAnchor, offset: selOffset, named_by_area: false } }
      : { ...f, properties: { ...f.properties, named_by_area: named.has(f.properties.id) && window.innerWidth > 600 } }));
    this.send("volcanoes", fc(feats));
  }

  updatePulse() {
    const D = this.D;
    const v = D.sit && D.vents.get(D.sit.volcano_id);
    if (!v) { this.pulse.remove(); return; }
    this.pulse.setLngLat(v);
    if (!this.pulse._map) this.pulse.addTo(this.map);
    const key = `${D.sit.volcano_id}|${D.sit.discrepancies.length}`;
    if (key !== this.pulseKey) {
      this.pulseKey = key;
      const node = this.pulse.getElement();
      node.classList.remove("pulse--ring", "pulse--done");
      void node.offsetWidth;
      node.classList.add("pulse--ring");
      // with the rose drawn, the static ring would make the vent a bullseye: drop it after
      // the three pulses (or at once when motion is reduced)
      if (D.rose && reducedMotion()) node.classList.add("pulse--done");
    }
    this.pulse.getElement().classList.toggle("pulse--rose", !!D.rose);
  }

  // ---------------------------------------------------------------- rose (section 6)

  roseSizes() {
    const phone = window.innerWidth <= 600;
    return { arrow: phone ? 78 : 120, arc: phone ? 40 : 64, label: phone ? 12 : 14, angle: phone ? 14 : 17, box: phone ? 12 : 14 };
  }

  updateRose() {
    const D = this.D, map = this.map;
    const src = map.getSource("rose");
    if (!src) return;
    const r = D.rose;
    if (!r || !this.ui.layers.rose) { this.send("rose", empty()); this.offTip = null; return; }
    const v = r.vent;
    const S = this.roseSizes();
    const mpp = (78271.517 * Math.cos((v[1] * Math.PI) / 180)) / 2 ** map.getZoom();
    const km = (px) => (px * mpp) / 1000;
    const L = km(S.arrow), r0 = km(16), ra = km(S.arc);
    let a1 = r.offDeg, sweep = (r.obsDeg - r.offDeg + 360) % 360;
    if (sweep > 180) { a1 = r.obsDeg; sweep = 360 - sweep; }
    const arc = [];
    for (let i = 0; i <= 32; i++) arc.push(dest(v, a1 + (sweep * i) / 32, ra));
    const obsWord = compassWord(r.obsDeg);
    const feats = [
      { type: "Feature", properties: { role: "off" }, geometry: { type: "LineString", coordinates: [dest(v, r.offDeg, r0), dest(v, r.offDeg, L)] } },
      { type: "Feature", properties: { role: "obs" }, geometry: { type: "LineString", coordinates: [dest(v, r.obsDeg, r0), dest(v, r.obsDeg, L)] } },
      { type: "Feature", properties: { role: "arc" }, geometry: { type: "LineString", coordinates: arc } },
      { type: "Feature", properties: { role: "off-head", bearing: r.offDeg }, geometry: { type: "Point", coordinates: dest(v, r.offDeg, L) } },
      { type: "Feature", properties: { role: "obs-head", bearing: r.obsDeg, size: S.label, line1: `OBSERVATORY · ${obsWord}`, line2: `VONA ${hhmmz(r.obsTime)} · ground observer${r.night ? " · night" : ""}` }, geometry: { type: "Point", coordinates: dest(v, r.obsDeg, L) } },
      { type: "Feature", properties: { role: "angle", size: S.angle, text: `${r.magnitude}° apart` }, geometry: { type: "Point", coordinates: dest(v, a1 + sweep / 2, ra + km(30)) } },
    ];
    if (r.probe) feats.push({ type: "Feature", properties: { role: "probe" }, geometry: { type: "Point", coordinates: dest(v, r.obsDeg, 15) } });
    this.offTip = dest(v, r.offDeg, L + km(10));
    this.send("rose", fc(feats));
  }

  // ---------------------------------------------------------------- label stack (5.1, 5.2)

  labelPoints() {
    const D = this.D;
    const S = this.roseSizes();
    const boxes = [];
    const vids = new Set(D.official.filter((f) => f.properties.show && f.properties.step === "now" && f.properties.valid).map((f) => f.properties.volcano_id));
    let selBox = null;
    const northOf = (g) => { const r = ringsOf(g)[0] || []; return r.length ? r.reduce((m, q) => (q[1] > m[1] ? q : m), r[0]) : ringCentre(g); };
    for (const vid of vids) {
      const t = officialLabelText(D, vid);
      if (!t || (!t.sel && window.innerWidth <= 600)) continue;
      if (!t.sel) {
        // other volcanoes: the name only, above the area's northern vertex (R6.3)
        boxes.push({ type: "Feature", geometry: { type: "Point", coordinates: northOf(t.geometry) }, properties: { kind: "name", sel: false, line1: t.line1, line2: "" } });
        continue;
      }
      // Hang the box below the area's southernmost vertex so it never covers the polygon or
      // the vent; a circle centred on the vent gets the box above its northern edge instead.
      const ring0 = ringsOf(t.geometry)[0] || [];
      let at = ring0.length ? ring0.reduce((m, q) => (q[1] < m[1] ? q : m), ring0[0]) : ringCentre(t.geometry);
      let anchor = "top", offset = [0, 0.5];
      const vent = D.vents.get(vid);
      const centre = ringCentre(t.geometry);
      if (vent && centre && kmBetween(centre, vent) < 25) {
        at = northOf(t.geometry);
        anchor = "bottom";
        offset = [0, -0.6];
      }
      if (this.offTip && D.rose && window.innerWidth > 600) {
        at = this.offTip;
        const b = D.rose.offDeg;
        anchor = b < 22.5 || b >= 337.5 ? "bottom" : b < 90 ? "bottom-left" : b < 157.5 ? "top-left" : b < 202.5 ? "top" : b < 270 ? "top-right" : "bottom-right";
        offset = [0.4, anchor.startsWith("top") ? 0.4 : -0.4];
      }
      selBox = { type: "Feature", geometry: { type: "Point", coordinates: at }, properties: { kind: "box", sel: true, size: S.box, line1: t.line1, line2: t.line2, anchor, offset } };
      boxes.push(selBox);
    }
    // Forecast-step labels only while a forecast step is chosen on the time bar (R6.3).
    if (this.ui.steps !== "now") {
      for (const f of D.official) {
        const p = f.properties;
        if (!p.show || p.step === "now" || !p.sel) continue;
        if (!(this.ui.steps === "all" || p.step === this.ui.steps)) continue;
        const c = ringCentre(f.geometry);
        const word = p.layer.replace("FCST+", "+").replace("H", " h");
        if (c) boxes.push({ type: "Feature", geometry: { type: "Point", coordinates: c }, properties: { kind: "step", text: `Forecast for ${hhmmz(ms(p.valid_from) + 3 * 3600e3)} (${word})` } });
      }
    }
    // TEPHRA's tag on the edge opposite the official label: the cone vertex farthest from it.
    const areas = [];
    const cone = D.sit ? D.coneOf(D.sit.volcano_id) : null;
    if (cone) {
      const p = cone.properties;
      const ring = ringsOf(cone.geometry)[0] || [];
      if (ring.length) {
        const ref = selBox ? selBox.geometry.coordinates : null;
        const at = ref ? ring.reduce((m, q) => (kmBetween(q, ref) > kmBetween(m, ref) ? q : m), ring[0]) : ring.reduce((m, q) => (q[1] < m[1] ? q : m), ring[0]);
        // the tag reads inward from that vertex, so it stays over the map and off the edge
        const c = ringCentre(cone.geometry) || at;
        const dx = (at[0] - c[0]) * Math.cos((c[1] * Math.PI) / 180), dy = at[1] - c[1];
        const side = Math.abs(dx) > Math.abs(dy) ? (dx < 0 ? ["left", [0.6, 0]] : ["right", [-0.6, 0]]) : dy < 0 ? ["bottom", [0, -0.6]] : ["top", [0, 0.6]];
        const stub = D.state?.llm?.backend === "stub";
        areas.push({ type: "Feature", geometry: { type: "Point", coordinates: at }, properties: { size: S.box, line1: tephraLabelText(p, stub), anchor: side[0], offset: side[1] } });
      }
    }
    return { boxes, areas, selBox };
  }

  updateLabels() {
    const map = this.map;
    if (!map.getSource("official-labels")) return;
    const { boxes, areas } = this.labelPoints();
    this.send("official-labels", fc(boxes));
    this.send("area-labels", fc(areas));
    this.lastLabels = { boxes, areas };
  }

  // ---------------------------------------------------------------- camera (7.4)

  // Nothing floats over the map but its pills and controls (R3), so framing pads 48 px on every
  // side, plus room for the controls column on the right.
  safeInsets() {
    const phone = window.innerWidth <= 600;
    if (phone) return { top: 40, bottom: 56, left: 24, right: 24 };
    const ctrls = this.container.querySelector(".maplibregl-ctrl-bottom-right");
    const w = ctrls ? ctrls.getBoundingClientRect().width : 0;
    return { top: 48, bottom: 56, left: 48, right: Math.max(48, w + 24) };
  }

  frame({ animate = true, includeFlights = true } = {}) {
    const D = this.D;
    if (!D?.sit) return;
    const vid = D.sit.volcano_id;
    const geoms = D.official.filter((f) => f.properties.volcano_id === vid && f.properties.show).map((f) => f.geometry)
      .concat(D.cones.filter((f) => f.properties.volcano_id === vid).map((f) => f.geometry));
    const v = D.vents.get(vid);
    if (v) geoms.push({ type: "Polygon", coordinates: [[dest(v, 0, 45), dest(v, 90, 45), dest(v, 180, 45), dest(v, 270, 45)]] });
    // each entering flight with room around it for its label
    if (includeFlights) for (const f of D.exposed) if (f.properties.volcano_id === vid) {
      const c = f.geometry.coordinates;
      geoms.push({ type: "Polygon", coordinates: [[dest(c, 0, 14), dest(c, 90, 42), dest(c, 180, 26), dest(c, 270, 42)]] });
    }
    const b = bboxOf(geoms);
    if (!b) return;
    const padding = this.safeInsets();
    const phone = window.innerWidth <= 600;
    const maxZoom = phone ? 7.4 : 8.6;
    const still = !animate || reducedMotion();
    if (this.ui.d3) {
      // Fit flat, then tilt about the same centre: fitting with pitch over-pads (8.1).
      let cam = null;
      try { cam = this.map.cameraForBounds(b, { padding, bearing: 0 }); } catch { /* not laid out yet */ }
      if (!cam) return;
      this.map.once("moveend", () => { this.updateRose(); this.updateLabels(); });
      this.map.easeTo({ center: cam.center, zoom: Math.min(cam.zoom, maxZoom) - 0.3, pitch: 60, bearing: -20, duration: still ? 0 : 2200 });
      return;
    }
    const opts = { padding, maxZoom, duration: still ? 0 : 1600, pitch: 0, bearing: 0 };
    const refit = { b, opts };
    // register before moving: an instant fitBounds fires moveend synchronously
    this.map.once("moveend", () => { this.updateRose(); this.updateLabels(); this.keepLabelsInView({ refit }); });
    try { this.map.fitBounds(b, opts); } catch { /* container not laid out yet */ }
  }

  // The selected volcano's official label box in map-host pixels (an estimate from its text).
  stackRect() {
    const L = this.lastLabels;
    const at = L?.boxes.find((f) => f.properties.kind === "box" && f.properties.sel);
    if (!at) return null;
    const px = at.properties.size || 14;
    const w = Math.max(at.properties.line1.length * px * 0.6, (at.properties.line2 || "").length * px * 0.9 * 0.58) + 22;
    const h = (at.properties.line2 ? 2.4 : 1.2) * px + 12;
    const p = this.map.project(at.geometry.coordinates);
    const a = at.properties.anchor || "top";
    const [ox, oy] = at.properties.offset || [0, 0];
    const x0 = (a.endsWith("left") ? p.x : a.endsWith("right") ? p.x - w : p.x - w / 2) + ox * px;
    const y0 = a.startsWith("top") ? p.y + oy * px - 6 : p.y + oy * px - h + 6;
    return { x0, y0, w, h };
  }

  // What sits on the map canvas (pills and controls), as rectangles relative to the map host.
  obstacles() {
    const host = this.container.getBoundingClientRect();
    const out = [];
    const nodes = [$("map-notes"), $("ctx-label"), $("compare-labels"), this.container.querySelector(".maplibregl-ctrl-bottom-right"), $("time-pill")];
    for (const n of nodes) {
      if (!n || n.hidden || n.offsetParent === null) continue;
      const r = n.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      out.push({ left: r.left - host.left, right: r.right - host.left, top: r.top - host.top, bottom: r.bottom - host.top });
    }
    return { host, out };
  }

  // After every camera move, pan by the smallest vector that clears the label stack of every
  // panel (12 px margin) while keeping the vent and `keep` points in the open map (5.1).
  keepLabelsInView({ keep = [], refit = null } = {}) {
    if (this.ui.d3) return;
    const r = this.stackRect();
    if (!r) return;
    const { host, out } = this.obstacles();
    const m = 12;
    const W = host.width, H = host.height;
    if (r.w > W - 2 * m || r.h > H - 2 * m) return;
    const hits = (dx, dy) => out.filter((o) => r.x0 + dx < o.right + m && r.x0 + dx + r.w > o.left - m && r.y0 + dy < o.bottom + m && r.y0 + dy + r.h > o.top - m);
    const inHost = (dx, dy) => r.x0 + dx >= m && r.x0 + dx + r.w <= W - m && r.y0 + dy >= m && r.y0 + dy + r.h <= H - m;
    const vent = this.D?.sit && this.D.vents.get(this.D.sit.volcano_id);
    const pts = [vent, ...keep].filter(Boolean).map((c) => this.map.project(c));
    const ptsOk = (dx, dy) => pts.every((q) => q.x + dx > 40 && q.x + dx < W - 40 && q.y + dy > 40 && q.y + dy < H - 40);
    let frontier = [[0, 0]];
    let best = null;
    const seen = new Set();
    for (let depth = 0; depth < 4 && frontier.length; depth++) {
      const next = [];
      for (const [dx, dy] of frontier) {
        const key = `${Math.round(dx)}|${Math.round(dy)}`;
        if (seen.has(key)) continue;
        seen.add(key);
        const hs = hits(dx, dy);
        if (!hs.length && inHost(dx, dy)) {
          if (ptsOk(dx, dy) && (!best || Math.hypot(dx, dy) < Math.hypot(...best))) best = [dx, dy];
          continue;
        }
        for (const o of hs) {
          next.push([o.left - m - (r.x0 + r.w), dy], [o.right + m - r.x0, dy], [dx, o.top - m - (r.y0 + r.h)], [dx, o.bottom + m - r.y0]);
        }
        if (!inHost(dx, dy)) {
          const fx = Math.min(Math.max(dx, m - r.x0), W - m - r.x0 - r.w);
          const fy = Math.min(Math.max(dy, m - r.y0), H - m - r.y0 - r.h);
          next.push([fx, fy]);
        }
      }
      frontier = next;
    }
    if (!best || Math.hypot(...best) < 3) return;
    // After a framing, first re-fit with room for the stack on the side it must move away
    // from, so the framed area (and its flights) stays clear of the panels; pan otherwise.
    if (refit) {
      const p2 = { ...refit.opts.padding };
      const [dx, dy] = best;
      if (dy > 0) p2.top += dy + 8; else if (dy < 0) p2.bottom += -dy + 8;
      if (dx > 0) p2.left += dx + 8; else if (dx < 0) p2.right += -dx + 8;
      if (p2.left + p2.right < W * 0.8 && p2.top + p2.bottom < H * 0.8) {
        this.map.once("moveend", () => { this.updateRose(); this.updateLabels(); this.keepLabelsInView({ keep }); });
        try { this.map.fitBounds(refit.b, { ...refit.opts, padding: p2, duration: refit.opts.duration ? 500 : 0 }); return; } catch { /* fall back to a pan */ }
      }
    }
    // the labels move with the map: moving them by +v means panning the camera by -v
    this.map.panBy([-best[0], -best[1]], { duration: reducedMotion() ? 0 : 450 });
  }

  flyRegion(region, animate = true) {
    const b = region.bbox;
    this.map.fitBounds([[b.west, b.south], [b.east, b.north]], { padding: this.safeInsets(), duration: animate && !reducedMotion() ? 1600 : 0, maxZoom: 8 });
  }

  flyToFlight(feature) {
    const c = feature.geometry.coordinates;
    const p = this.safeInsets();
    const opts = { center: c, zoom: Math.max(this.map.getZoom(), 7.5), offset: [(p.left - p.right) / 2, (p.top - p.bottom) / 2] };
    this.map.once("moveend", () => { this.updateRose(); this.updateLabels(); this.keepLabelsInView({ keep: [c] }); });
    if (reducedMotion()) this.map.easeTo({ ...opts, duration: 0 }); else this.map.flyTo({ ...opts, duration: 1600 });
  }

  // fly to fit once per flight that newly enters the selected volcano's area
  followNewFlights() {
    const D = this.D;
    const ids = new Set(D.exposed.map((f) => `${f.properties.hex}:${f.properties.volcano_id}`));
    if (this.flownFlights == null) { this.flownFlights = ids; return; }
    const fresh = D.exposed.filter((f) => !this.flownFlights.has(`${f.properties.hex}:${f.properties.volcano_id}`) && f.properties.volcano_id === D.selected);
    for (const id of ids) this.flownFlights.add(id);
    if (fresh.length) this.frame({ animate: true });
  }

  // ---------------------------------------------------------------- clicks (R6.5)
  // No popups: a click opens the matching Details section (wall.js), and a flight cluster zooms in.

  onClick(e) {
    const order = ["exposed-cluster", "aircraft-icon", "exposure-entry", "reroute-wp", "reroute-line", "volcano-active", "volcano-inactive", "official-fill-now", "official-line-now", "official-line-f6", "official-line-f12", "official-line-f18", "tephra-line", "tephra-fill", "tephra-hatch"];
    const layers = order.filter((id) => this.map.getLayer(id));
    const hits = this.map.queryRenderedFeatures([[e.point.x - 6, e.point.y - 6], [e.point.x + 6, e.point.y + 6]], { layers });
    if (!hits.length) return;
    hits.sort((a, b) => order.indexOf(a.layer.id) - order.indexOf(b.layer.id));
    if (hits[0].layer.id === "exposed-cluster") { this.zoomCluster(hits[0]); return; }
    this.onFeature?.(hits[0], e.lngLat);
  }

  async zoomCluster(hit) {
    const src = this.map.getSource("exposed-pts");
    let zoom;
    try { zoom = await src.getClusterExpansionZoom(hit.properties.cluster_id); } catch { return; }
    const center = hit.geometry.coordinates;
    if (reducedMotion()) this.map.jumpTo({ center, zoom }); else this.map.easeTo({ center, zoom, duration: 600 });
  }

  // ---------------------------------------------------------------- marching paths (5.4)

  startAnts() {
    let last = -1;
    const tick = (t) => {
      requestAnimationFrame(tick);
      if (document.hidden || reducedMotion() || !this.loaded || !this.map.getLayer("exposure-path")) return;
      if (!this.D?.exposed.length) return;
      const i = Math.floor(t / 60) % ANT_STEPS.length;
      if (i === last) return;
      last = i;
      this.map.setPaintProperty("exposure-path", "line-dasharray", ANT_STEPS[i]);
    };
    requestAnimationFrame(tick);
  }

  // ---------------------------------------------------------------- visibility

  setVisible(ids, on) {
    for (const id of ids) if (this.map.getLayer(id)) this.map.setLayoutProperty(id, "visibility", on ? "visible" : "none");
  }

  applyLayers() {
    const L = this.ui.layers;
    this.setVisible(["hillshade"], L.terrain);
    this.setVisible(["fir-line", "fir-active", "fir-label", "vaac-line", "vaac-label"], L.context);
    this.setVisible(["navaid", "navaid-label"], L.navaids);
    this.setVisible(["tephra-fill", "tephra-hatch", "tephra-line", "tephra-label"], L.tephra);
    this.setVisible(["exposure-path", "exposure-entry", "exposure-entry-label"], L.paths);
    this.setVisible(["aircraft-icon", "aircraft-inside", "aircraft-picked", "aircraft-label-exposed", "exposed-cluster"], L.aircraft);
    this.setVisible(["aircraft-label"], L.aircraft && L.acLabels);
    setExtVisible(this.map, true, L.satboxes);
    this.setVisible(["rose-casing", "rose-arc", "rose-off", "rose-obs", "rose-probe", "rose-heads", "rose-labels", "rose-angle"], L.rose);
    if (this.D) { this.updateRose(); this.updateLabels(); }
  }

  // ---------------------------------------------------------------- satellite context (5.6)

  satLabel() {
    const D = this.D;
    if (!D) return [];
    const out = [];
    if (this.ui.sat !== "off" && this.gibs.key) {
      const s = SAT[this.ui.sat];
      const t = Date.parse(this.gibs.time);
      out.push(this.gibs.failed
        ? `CONTEXT ONLY · No Himawari frame near ${hhmmz(Date.parse(gibsTime(D.now, D.mode)))} · Imagery: NASA GIBS · Himawari-9 data: JMA via NOAA`
        : `CONTEXT ONLY · ${s.title} ${hhmmz(t)} · not ash detection · Imagery: NASA GIBS · Himawari-9 data: JMA via NOAA`);
    }
    if (this.ui.so2) {
      const d = so2Date(D.now, D.mode);
      out.push(`CONTEXT ONLY · SO2 (TROPOMI, daily) ${dayMon(Date.parse(d))} ${d.slice(0, 4)} · ${GASES_SCOPE_SHORT} · Imagery: NASA GIBS · Contains modified Copernicus Sentinel data ${d.slice(0, 4)}`);
    }
    if (this.ui.btd && D.overlays.btd.length) out.push("Split-window BTD (computed by TEPHRA) · an indicator, not ash detection · Himawari-9 data: JMA via NOAA");
    return out;
  }

  updateSat() {
    const D = this.D, map = this.map;
    const kind = this.ui.sat;
    if (kind === "off") {
      if (map.getLayer("gibs")) map.removeLayer("gibs");
      if (map.getSource("gibs")) map.removeSource("gibs");
      this.gibs = { key: null, back: 0, errors: 0 };
    } else {
      const s = SAT[kind];
      const time = gibsTime(D.now, D.mode, this.gibs.kind === kind ? this.gibs.back : 0);
      const key = `${kind}|${time}`;
      if (key !== this.gibs.key) {
        const keepBack = this.gibs.kind === kind && this.gibs.slot === gibsTime(D.now, D.mode);
        this.gibs = { ...this.gibs, key, kind, time, slot: gibsTime(D.now, D.mode), back: keepBack ? this.gibs.back : 0, errors: 0, failed: keepBack ? this.gibs.failed : false };
        const tiles = [GIBS(s.layer, time, s.matrix)];
        const src = map.getSource("gibs");
        if (src && src.maxzoom === s.maxzoom && typeof src.setTiles === "function") src.setTiles(tiles);
        else {
          if (map.getLayer("gibs")) map.removeLayer("gibs");
          if (src) map.removeSource("gibs");
          map.addSource("gibs", { type: "raster", tiles, tileSize: 256, maxzoom: s.maxzoom });
          map.addLayer({ id: "gibs", type: "raster", source: "gibs", paint: { "raster-opacity": kind === "airmass" ? 0.55 : 0.6, "raster-saturation": kind === "ir" ? -1 : 0, "raster-contrast": kind === "ir" ? 0.2 : 0 } }, before(map, "water_name") || before(map, "fir-line"));
        }
        if (map.getLayer("gibs")) {
          map.setPaintProperty("gibs", "raster-opacity", kind === "airmass" ? 0.55 : 0.6);
          map.setPaintProperty("gibs", "raster-saturation", kind === "ir" ? -1 : 0);
          map.setPaintProperty("gibs", "raster-contrast", kind === "ir" ? 0.2 : 0);
        }
      }
    }
    if (this.ui.so2) {
      const d = so2Date(D.now, D.mode);
      const tiles = [GIBS("TROPOMI_L2_Sulfur_Dioxide_Total_Vertical_Column", d, "GoogleMapsCompatible_Level6")];
      if (this.so2Key !== d) {
        this.so2Key = d;
        const src = map.getSource("so2");
        if (src && typeof src.setTiles === "function") src.setTiles(tiles);
        else {
          if (map.getLayer("so2")) map.removeLayer("so2");
          if (src) map.removeSource("so2");
          map.addSource("so2", { type: "raster", tiles, tileSize: 256, maxzoom: 6 });
          map.addLayer({ id: "so2", type: "raster", source: "so2", paint: { "raster-opacity": 0.7 } }, before(map, "water_name") || before(map, "fir-line"));
        }
      }
    } else if (map.getSource("so2")) {
      if (map.getLayer("so2")) map.removeLayer("so2");
      map.removeSource("so2");
      this.so2Key = null;
    }
    this.onNote?.("context", null);
  }

  // A missing GIBS tile: step back one 10-min slot at a time, at most six (section 5.6).
  gibsMiss() {
    if (this.ui.sat === "off") return;
    this.gibs.errors = (this.gibs.errors || 0) + 1;
    if (this.gibs.errors < 2 || this.gibsStepPending) return;
    this.gibsStepPending = true;
    setTimeout(() => {
      this.gibsStepPending = false;
      if (this.gibs.back >= 6) { this.gibs.failed = true; this.onNote?.("context", null); return; }
      this.gibs.back += 1;
      const back = this.gibs.back;
      this.gibs.key = null;
      this.gibs.kind = this.ui.sat;
      const slot = gibsTime(this.D.now, this.D.mode);
      this.gibs.slot = slot;
      this.updateSatAt(back);
    }, 400);
  }

  updateSatAt(back) {
    const s = SAT[this.ui.sat];
    const time = gibsTime(this.D.now, this.D.mode, back);
    this.gibs.time = time;
    this.gibs.key = `${this.ui.sat}|${time}`;
    this.gibs.errors = 0;
    const src = this.map.getSource("gibs");
    if (src && typeof src.setTiles === "function") src.setTiles([GIBS(s.layer, time, s.matrix)]);
    this.onNote?.("context", null);
  }

  updateBtd() {
    const map = this.map;
    const want = this.ui.btd ? this.D.overlays.btd || [] : [];
    const ids = want.map((o, i) => `btd-${i}`);
    for (const id of this.btdIds) if (!ids.includes(id)) { if (map.getLayer(id)) map.removeLayer(id); if (map.getSource(id)) map.removeSource(id); }
    want.forEach((o, i) => {
      const id = `btd-${i}`;
      const url = o.image_url.startsWith("/") ? o.image_url : null;
      if (!url || !Array.isArray(o.corners) || o.corners.length !== 4) return;
      const src = map.getSource(id);
      if (src) src.updateImage({ url, coordinates: o.corners });
      else {
        map.addSource(id, { type: "image", url, coordinates: o.corners });
        map.addLayer({ id, type: "raster", source: id, paint: { "raster-opacity": 0.75 } }, before(map, "water_name") || before(map, "fir-line"));
      }
    });
    this.btdIds = ids;
  }

  // ---------------------------------------------------------------- 3D (8.1)

  set3d(on) {
    const map = this.map;
    const dur = reducedMotion() ? 0 : 2600;
    if (on) {
      map.dragRotate.enable();
      map.touchZoomRotate.enableRotation();
      const exag = 6, h = (p) => ["*", ["coalesce", ["get", p], 0], 0.3048 * exag];
      if (!map.getLayer("official-volume")) {
        const beforeId = before(map, "volcano-inactive");
        map.addLayer({ id: "official-volume", type: "fill-extrusion", source: "official", filter: ["all", ["==", ["get", "step"], "now"], ["==", ["get", "fill"], true], ["==", ["get", "valid"], true]], paint: { "fill-extrusion-color": this.C.official, "fill-extrusion-opacity": 0.45, "fill-extrusion-base": h("base_ft"), "fill-extrusion-height": h("top_ft"), "fill-extrusion-vertical-gradient": false } }, beforeId);
        if (this.ui.layers.tephra) map.addLayer({ id: "tephra-volume", type: "fill-extrusion", source: "cones", filter: ["all", ["==", ["get", "part"], "cone"], ["!=", ["get", "mode"], "OFFICIAL"]], paint: { "fill-extrusion-color": this.C.tephra, "fill-extrusion-opacity": 0.14, "fill-extrusion-base": h("base_ft"), "fill-extrusion-height": h("top_ft"), "fill-extrusion-vertical-gradient": false } }, beforeId);
        map.addLayer({ id: "ac3d-stem", type: "fill-extrusion", source: "ac3d", filter: ["==", ["get", "part"], "stem"], paint: { "fill-extrusion-color": ["case", ["get", "exposed"], this.C.tephra, this.C.aircraft], "fill-extrusion-opacity": 0.55, "fill-extrusion-base": 0, "fill-extrusion-height": ["get", "h"] } }, beforeId);
        map.addLayer({ id: "ac3d-box", type: "fill-extrusion", source: "ac3d", filter: ["==", ["get", "part"], "box"], paint: { "fill-extrusion-color": ["case", ["get", "exposed"], this.C.tephra, this.C.aircraft], "fill-extrusion-opacity": 0.95, "fill-extrusion-base": ["get", "b"], "fill-extrusion-height": ["get", "h"] } }, beforeId);
      }
      if (this.ui.layers.terrain && map.getLayer("hillshade")) map.setLayoutProperty("hillshade", "visibility", "visible");
      map.setSky({ "sky-color": "#0b1220", "horizon-color": "#1b2430", "fog-color": "#07090d", "sky-horizon-blend": 0.6, "horizon-fog-blend": 0.6, "fog-ground-blend": 0.8 });
      this.update3d();
      // 3D always targets the selected volcano (8.1)
      if (this.D?.sit) this.frame({ animate: true }); else map.easeTo({ pitch: 60, bearing: -20, duration: dur });
    } else {
      for (const id of ["official-volume", "tephra-volume", "ac3d-stem", "ac3d-box"]) if (map.getLayer(id)) map.removeLayer(id);
      map.dragRotate.disable();
      map.touchZoomRotate.disableRotation();
      if (this.D?.sit) this.frame({ animate: true }); else map.easeTo({ pitch: 0, bearing: 0, duration: reducedMotion() ? 0 : 1600 });
    }
  }

  update3d() {
    const src = this.map.getSource("ac3d");
    if (!src) return;
    const exag = 6 * 0.3048;
    const feats = [];
    for (const f of this.D.aircraft) {
      const p = f.properties;
      if (p.alt_baro_ft == null) continue;
      const c = f.geometry.coordinates;
      const sq = (km) => ({ type: "Polygon", coordinates: [[dest(c, 315, km), dest(c, 45, km), dest(c, 135, km), dest(c, 225, km), dest(c, 315, km)]] });
      const lo = Math.max(0, p.alt_baro_ft - 300) * exag, hi = (p.alt_baro_ft + 300) * exag;
      feats.push({ type: "Feature", geometry: sq(0.25), properties: { part: "stem", exposed: !!p.exposed, h: lo } });
      feats.push({ type: "Feature", geometry: sq(1.77), properties: { part: "box", exposed: !!p.exposed, b: lo, h: hi } });
    }
    this.send("ac3d", fc(feats));
  }

  // ---------------------------------------------------------------- swipe compare (8.2)

  async setCompare(on, wrap) {
    if (!on) {
      this.compare?.remove();
      this.compare = null;
      this.compareMap?.remove();
      this.compareMap = null;
      this.compareSent.clear();
      $("map-a")?.remove();
      this.container.style.clip = "";
      this.container.style.clipPath = "";
      return true;
    }
    await loadCompare();
    if (!window.maplibregl.Compare) return false;
    // start both sides from a settled, flat camera (a 3D exit may still be animating)
    this.map.stop();
    if (this.map.getPitch() || this.map.getBearing()) this.map.jumpTo({ pitch: 0, bearing: 0 });
    const node = el("div", { id: "map-a", class: "map map--a", "aria-label": "Official products only" });
    wrap.prepend(node);
    const a = new window.maplibregl.Map({
      container: node, style: this.fallbackUsed ? this.map.getStyle() : STYLE_URL, center: this.map.getCenter(), zoom: this.map.getZoom(),
      pitch: this.map.getPitch(), bearing: this.map.getBearing(), attributionControl: false, interactive: true, preserveDrawingBuffer: SHOTS, fadeDuration: 150,
    });
    a.on("styleimagemissing", (e) => { if (!a.hasImage(e.id)) a.addImage(e.id, { width: 1, height: 1, data: new Uint8Array(4) }); });
    this.compareMap = a;
    a.on("style.load", () => {
      this.compareSent.clear();
      if (!this.noText) tuneBasemap(a, this.C, this.ui);
      addImages(a, this.C);
      addContext(a, this.C, this.ui, this.noText);
      addHazard(a, this.C, this.ui, { withTephra: false, noText: this.noText });
      this.updateCompare();
    });
    this.compare = new window.maplibregl.Compare(a, this.map, wrap, { mousemove: false, orientation: "vertical" });
    return true;
  }

  updateCompare() {
    const a = this.compareMap;
    if (!a || !a.getSource("official")) return;
    const D = this.D;
    const sent = this.compareSent;
    this.send("official", fc(D.official), a, sent);
    this.send("aircraft", fc(D.aircraft), a, sent);
    this.send("volcanoes", fc(D.volcanoes), a, sent);
    this.send("official-labels", fc(this.lastLabels?.boxes || []), a, sent);
    a.setFilter("fir-active", ["in", ["get", "icao"], ["literal", D.firsWithSigmet]]);
  }

  compareSlide(pct) {
    if (!this.compare) return;
    const w = this.container.getBoundingClientRect().width;
    this.compare.setSlider(Math.round((w * pct) / 100));
  }
}

let comparePromise = null;
function loadCompare() {
  if (window.maplibregl.Compare) return Promise.resolve();
  if (!comparePromise) {
    comparePromise = new Promise((resolve) => {
      const s = document.createElement("script");
      s.src = "https://unpkg.com/@maplibre/maplibre-gl-compare@0.5.0/dist/maplibre-gl-compare.js";
      s.onload = () => resolve();
      s.onerror = () => resolve();
      document.head.append(s);
    });
  }
  return comparePromise;
}

export { LEVEL_MAX };
