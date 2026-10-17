// The night basemap shared by the Wall map and the flow board (docs/UI-DESIGN.md 5): OpenFreeMap's
// dark style turned into the board's look. Land is a dot matrix (the style's background drawn with
// a dot tile, the sea filled over it) with a thin coastline; roads, rail, buildings and land use are
// hidden, because none of them helps a dispatcher read ash; place names are quiet and in Latin
// script. Every colour comes from tokens.css through the caller's token object.

export const STYLE_URL = "https://tiles.openfreemap.org/styles/dark";

// basemap layers that say nothing about ash or flights
const HIDE = /^(highway|road|railway|building|landuse_residential|landcover_wood|waterway|water_name|tunnel|bridge)/;
const QUIET_PLACES = ["place_other", "place_suburb", "place_village"];
const DOT = { step: 10, r: 1.5 }; // device px at pixelRatio 2: a dot every 5 css px

function rgbOf(hex) {
  const h = String(hex).trim().replace("#", "");
  const v = h.length === 3 ? h.split("").map((c) => c + c).join("") : h.slice(0, 6);
  const n = parseInt(v, 16);
  return Number.isFinite(n) ? [(n >> 16) & 255, (n >> 8) & 255, n & 255] : [10, 16, 23];
}

// One opaque tile: the land colour with a soft dot in its middle. Opaque, because a background
// pattern replaces the background colour.
function dotTile(landHex, dotHex, alpha) {
  const s = DOT.step, land = rgbOf(landHex), dot = rgbOf(dotHex);
  const data = new Uint8Array(s * s * 4);
  const c = (s - 1) / 2;
  for (let y = 0; y < s; y++) for (let x = 0; x < s; x++) {
    const d = Math.hypot(x - c, y - c);
    const a = alpha * Math.max(0, Math.min(1, DOT.r + 0.5 - d));
    const i = (y * s + x) * 4;
    for (let k = 0; k < 3; k++) data[i + k] = Math.round(land[k] * (1 - a) + dot[k] * a);
    data[i + 3] = 255;
  }
  return { width: s, height: s, data };
}

// 2° lines over the region the map opens on, very faint, over the sea and under the coast
function graticule(step = 2) {
  const lines = [];
  for (let lon = 60; lon <= 180; lon += step) lines.push({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: [[lon, -50], [lon, 50]] } });
  for (let lat = -50; lat <= 50; lat += step) lines.push({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: [[60, lat], [180, lat]] } });
  return { type: "FeatureCollection", features: lines };
}

const has = (map, id) => Boolean(map.getLayer(id));

// Apply after the style loads. `places` false (the board) keeps only country names.
export function nightBasemap(map, C, { places = true, dotAlpha = 0.3 } = {}) {
  if (!map.hasImage("land-dots")) map.addImage("land-dots", dotTile(C.land, C.dot, dotAlpha), { pixelRatio: 2 });
  if (has(map, "background")) map.setPaintProperty("background", "background-pattern", "land-dots");
  if (has(map, "water")) map.setPaintProperty("water", "fill-color", C.water);
  for (const layer of map.getStyle().layers) {
    const id = layer.id;
    if (HIDE.test(id) || (id.startsWith("aeroway") && !places)) map.setLayoutProperty(id, "visibility", "none");
    else if (id === "landuse_park" || id.startsWith("landcover")) map.setPaintProperty(id, "fill-opacity", 0.12);
  }
  for (const id of QUIET_PLACES) if (has(map, id)) map.setLayoutProperty(id, "visibility", "none");
  if (!places) {
    for (const id of ["place_town", "place_city", "place_city_large", "place_state", "boundary_state"]) if (has(map, id)) map.setLayoutProperty(id, "visibility", "none");
  }
  for (const id of ["place_city", "place_city_large", "place_town"]) if (has(map, id)) map.setPaintProperty(id, "text-color", C.labelMinor);
  for (const id of ["place_country_major", "place_country_minor", "place_country_other"]) {
    if (!has(map, id)) continue;
    map.setPaintProperty(id, "text-color", C.labelMinor);
    map.setLayoutProperty(id, "text-transform", "uppercase");
    map.setLayoutProperty(id, "text-letter-spacing", 0.18);
  }
  for (const id of ["boundary_country_z0-4", "boundary_country_z5-"]) if (has(map, id)) map.setPaintProperty(id, "line-color", C.border);
  // Place names once, in Latin script: the basemap's second line in the local script doubled
  // every country and city name on the map.
  for (const layer of map.getStyle().layers) {
    if (layer.type !== "symbol" || !JSON.stringify(layer.layout?.["text-field"] ?? "").includes("name:nonlatin")) continue;
    map.setLayoutProperty(layer.id, "text-field", ["coalesce", ["get", "name:latin"], ["get", "name:en"], ["get", "name"]]);
  }
  const below = has(map, "water_name") ? "water_name" : undefined;
  if (map.getSource("openmaptiles") && !has(map, "coast")) {
    map.addLayer({ id: "coast", type: "line", source: "openmaptiles", "source-layer": "water", filter: ["!=", ["get", "class"], "river"], paint: { "line-color": C.coast, "line-width": ["interpolate", ["linear"], ["zoom"], 3, 0.5, 8, 1.1] } }, below);
  }
  if (!map.getSource("graticule")) map.addSource("graticule", { type: "geojson", data: graticule() });
  if (!has(map, "graticule")) map.addLayer({ id: "graticule", type: "line", source: "graticule", maxzoom: 9, paint: { "line-color": C.grid, "line-width": 1 } }, has(map, "coast") ? "coast" : below);
}

// The tokens a map reads: from its night subtree when the page has one (the demo's map keeps the
// night palette in the light theme, tokens.css .night), else from the page.
export const mapTokens = () => getComputedStyle(document.querySelector(".night") || document.documentElement);

// The colours nightBasemap needs, from the tokens (tokens.css).
export function nightColours() {
  const css = mapTokens();
  const tok = (name) => css.getPropertyValue(name).trim();
  return {
    land: tok("--map-land"), water: tok("--map-water"), dot: tok("--map-dot"), coast: tok("--map-coast"),
    grid: tok("--map-grid"), border: tok("--map-border"), labelMinor: tok("--map-label-minor"),
  };
}

// The colours a map's symbols need (images.js draws the volcano, plane and label images from them).
export function symbolColours() {
  const css = mapTokens();
  const tok = (name) => css.getPropertyValue(name).trim();
  return {
    official: tok("--c-official"), tephra: tok("--c-tephra"), observer: tok("--c-observer"), crew: tok("--c-crew"),
    route: tok("--c-route"), reroute: tok("--c-reroute"), closed: tok("--c-closed"), aircraft: tok("--c-aircraft"), muted: tok("--c-map-muted"),
    text1: tok("--c-text-1"), label: tok("--map-label"), halo: tok("--map-halo"),
    codes: { GREEN: tok("--c-code-green"), YELLOW: tok("--c-code-yellow"), ORANGE: tok("--c-code-orange"), RED: tok("--c-code-red"), UNKNOWN: tok("--c-code-unknown") },
  };
}
