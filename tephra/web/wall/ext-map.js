// Map layers for the AI extensions: reroute polylines with ICAO turn-point labels, and the
// Satellite check boxes drawn over the frame bounds. Everything drawn here arrives as
// code-made GeoJSON (reroutes from the wall snapshot) or is placed by code from the reading's
// 0-1000 pixel boxes and the frame corners; nothing is invented here.

import { fc } from "./util.js";

const FONT_BOLD = ["Noto Sans Bold"];
const FONT_REG = ["Noto Sans Regular"];

export const EXT_LAYERS = ["reroute-casing", "reroute-line", "reroute-wp", "reroute-wp-label", "reroute-name", "sat-frame", "sat-box-fill", "sat-box-line", "sat-box-label"];

export function extTokens() {
  const css = getComputedStyle(document.documentElement);
  const tok = (n) => css.getPropertyValue(n).trim();
  return { reroute: tok("--c-reroute"), rerouteText: tok("--c-reroute-text"), sat: tok("--c-sat"), satText: tok("--c-sat-text"), halo: tok("--map-halo") };
}

export function addExtLayers(map, noText, visible) {
  const C = extTokens();
  const vis = visible ? "visible" : "none";
  for (const id of ["reroutes", "satboxes"]) if (!map.getSource(id)) map.addSource(id, { type: "geojson", data: fc([]) });
  const path = ["==", ["get", "feature"], "path"];
  const wp = ["==", ["get", "feature"], "waypoint"];
  const fade = ["case", ["==", ["get", "sel"], true], 1, 0.55];
  map.addLayer({ id: "sat-frame", type: "line", source: "satboxes", filter: ["==", ["get", "part"], "frame"], paint: { "line-color": C.sat, "line-width": 1.2, "line-dasharray": [2, 3], "line-opacity": 0.8 } });
  map.addLayer({ id: "sat-box-fill", type: "fill", source: "satboxes", filter: ["==", ["get", "part"], "box"], paint: { "fill-color": C.sat, "fill-opacity": 0.12 } });
  map.addLayer({ id: "sat-box-line", type: "line", source: "satboxes", filter: ["==", ["get", "part"], "box"], paint: { "line-color": C.sat, "line-width": 2.2 } });
  map.addLayer({ id: "reroute-casing", type: "line", source: "reroutes", filter: path, layout: { visibility: vis, "line-join": "round", "line-cap": "round" }, paint: { "line-color": C.halo, "line-width": 6.5, "line-opacity": ["case", ["==", ["get", "sel"], true], 0.9, 0.5] } });
  map.addLayer({ id: "reroute-line", type: "line", source: "reroutes", filter: path, layout: { visibility: vis, "line-join": "round", "line-cap": "round" }, paint: { "line-color": C.reroute, "line-width": 3, "line-opacity": fade } });
  map.addLayer({ id: "reroute-wp", type: "circle", source: "reroutes", filter: wp, layout: { visibility: vis }, paint: { "circle-radius": 5, "circle-color": C.halo, "circle-stroke-color": C.reroute, "circle-stroke-width": 2.2, "circle-opacity": fade, "circle-stroke-opacity": fade } });
  if (noText) return;
  map.addLayer({ id: "reroute-wp-label", type: "symbol", source: "reroutes", filter: wp, minzoom: 5.2, layout: { visibility: vis, "text-field": ["get", "label"], "text-font": FONT_BOLD, "text-size": 12, "text-variable-anchor": ["top", "bottom", "left", "right"], "text-radial-offset": 0.9, "text-optional": true }, paint: { "text-color": C.rerouteText, "text-halo-color": C.halo, "text-halo-width": 2, "text-opacity": fade } });
  map.addLayer({ id: "reroute-name", type: "symbol", source: "reroutes", filter: path, layout: { visibility: vis, "symbol-placement": "line", "symbol-spacing": 420, "text-field": ["get", "label"], "text-font": FONT_REG, "text-size": 12, "text-offset": [0, -1.1], "text-optional": true, "text-keep-upright": true }, paint: { "text-color": C.rerouteText, "text-halo-color": C.halo, "text-halo-width": 2, "text-opacity": fade } });
  map.addLayer({ id: "sat-box-label", type: "symbol", source: "satboxes", filter: ["==", ["get", "part"], "box"], layout: { "text-field": ["get", "label"], "text-font": FONT_BOLD, "text-size": 12, "text-anchor": "bottom-left", "text-offset": [0.2, -0.2], "text-allow-overlap": false, "symbol-sort-key": 2 }, paint: { "text-color": C.satText, "text-halo-color": C.halo, "text-halo-width": 2 } });
}

// Corners come as BBox.corners_lonlat(): the first is north-west, the third south-east.
export function boundsOf(corners) {
  if (!Array.isArray(corners) || corners.length < 3) return null;
  const lons = corners.map((c) => c[0]), lats = corners.map((c) => c[1]);
  return { west: Math.min(...lons), east: Math.max(...lons), south: Math.min(...lats), north: Math.max(...lats) };
}

// A 0-1000 [ymin, xmin, ymax, xmax] pixel box in the frame, as a lon/lat ring.
export function boxRing(box, b) {
  const [y0, x0, y1, x1] = box;
  const lon = (x) => b.west + (x / 1000) * (b.east - b.west);
  const lat = (y) => b.north - (y / 1000) * (b.north - b.south);
  return [[lon(x0), lat(y0)], [lon(x1), lat(y0)], [lon(x1), lat(y1)], [lon(x0), lat(y1)], [lon(x0), lat(y0)]];
}

export function frameFor(reading, frames) {
  const ids = new Set(reading.frame_ids || []);
  const mine = (frames || []).filter((f) => ids.has(f.source_id));
  return mine.find((f) => f.product === "DUST_RGB") || mine[0] || null;
}

export function satFeatures(readings, frames, selectedVid) {
  const out = [];
  for (const r of readings || []) {
    if (r.status !== "read" || !r.boxes?.length) continue;
    const frame = frameFor(r, frames);
    const b = boundsOf(frame?.corners);
    const sel = r.volcano_id === selectedVid;
    if (b) out.push({ type: "Feature", geometry: { type: "Polygon", coordinates: [boxRing([0, 0, 1000, 1000], b)] }, properties: { part: "frame", sel } });
    r.boxes.forEach((box, i) => {
      const geometry = box.polygon || (b ? { type: "Polygon", coordinates: [boxRing(box.box_2d, b)] } : null);
      if (geometry) out.push({ type: "Feature", geometry, properties: { part: "box", sel, label: `AI box ${i + 1}: possible ash` } });
    });
  }
  return out;
}

export function updateExtLayers(map, { reroutes, satellite, frames, selectedVid }) {
  if (!map.getSource("reroutes")) return;
  const feats = (reroutes?.features || []).map((f) => ({ ...f, properties: { ...f.properties, sel: f.properties.volcano_id === selectedVid } }));
  map.getSource("reroutes").setData(fc(feats));
  map.getSource("satboxes").setData(fc(satFeatures(satellite, frames, selectedVid)));
}

export function setExtVisible(map, on, satOn = true) {
  for (const id of EXT_LAYERS) {
    if (!map.getLayer(id)) continue;
    const isSat = id.startsWith("sat-");
    map.setLayoutProperty(id, "visibility", (isSat ? satOn : on) ? "visible" : "none");
  }
}
