// The Desk map (1280 px and up): the night basemap between Decide and the review, so the flight
// being decided is seen where it is. It draws the snapshot the Desk already reads from /api/wall:
// the ash areas (the official area filled, TEPHRA's wider area dashed), every RFA flight in or
// heading in with its path into the ash, the volcanoes, and for the flight under review its ring,
// its card and the reroute its draft proposes. Selecting a plane that has an open draft opens that
// review; any other plane shows its path and card. The airports the airport plan closes are drawn
// as the Wall draws them: a white bar on a dark disc (--c-closed), never red.
// Read-only: the map never changes a draft. MapLibre is loaded only when the map is shown, so a
// phone never downloads it.

import { STYLE_URL, nightBasemap, nightColours, symbolColours } from '../wall/basemap.js';
import { addImages } from '../wall/images.js';
import { PATHS, api } from './api.js';
import { byId, el, icon, reducedMotion } from './dom.js';
import { latestPlan } from './network.js';
import { app, draftList } from './state.js';

const MAPLIBRE = 'https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl';
const WIDE = window.matchMedia('(min-width: 1280px)');
const fc = (features) => ({ type: 'FeatureCollection', features });

let map = null;
let ready = false;
let loading = null;
let snap = null;
let onOpen = null;
let card = null;
let shownFor = null;
let C = null;
let airports = null; // the catalogue (GET /api/airports), for the airports the plan closes
const feats = (k) => (snap && snap[k] && Array.isArray(snap[k].features) ? snap[k].features : []);

function loadLib() {
  if (window.maplibregl) return Promise.resolve();
  if (loading) return loading;
  loading = new Promise((resolve, reject) => {
    const css = el('link', { rel: 'stylesheet', href: `${MAPLIBRE}.css` });
    const js = el('script', { src: `${MAPLIBRE}.js` });
    js.addEventListener('load', () => resolve());
    js.addEventListener('error', () => reject(new Error('map library')));
    document.head.append(css, js);
  });
  return loading;
}

// The hex of every RFA flight with an open draft of the mode playing, to its newest draft id.
function draftByHex() {
  const out = new Map();
  for (const a of draftList()) {
    const prev = out.get(a.hex);
    if (!prev || String(a.created_at) > String(prev.created_at)) out.set(a.hex, a);
  }
  return out;
}

function addLayers(C) {
  for (const id of ['d-cones', 'd-paths', 'd-reroute', 'd-closures', 'd-airports', 'd-volcanoes', 'd-aircraft']) map.addSource(id, { type: 'geojson', data: fc([]) });
  const official = ['==', ['get', 'mode'], 'OFFICIAL'];
  map.addLayer({ id: 'd-cone-fill', type: 'fill', source: 'd-cones', filter: official, paint: { 'fill-color': C.official, 'fill-opacity': 0.09 } });
  map.addLayer({ id: 'd-cone-line', type: 'line', source: 'd-cones', filter: official, layout: { 'line-join': 'round' }, paint: { 'line-color': C.official, 'line-opacity': 0.7, 'line-width': 1.6 } });
  map.addLayer({ id: 'd-tephra-line', type: 'line', source: 'd-cones', filter: ['!', official], layout: { 'line-join': 'round' }, paint: { 'line-color': C.tephra, 'line-opacity': 0.8, 'line-width': 1.4, 'line-dasharray': [4, 3] } });
  map.addLayer({ id: 'd-paths', type: 'line', source: 'd-paths', layout: { 'line-cap': 'round' }, paint: { 'line-color': C.tephra, 'line-opacity': ['case', ['get', 'sel'], 0.95, 0.22], 'line-width': ['case', ['get', 'sel'], 2.4, 1], 'line-dasharray': [1, 2] } });
  map.addLayer({ id: 'd-reroute-casing', type: 'line', source: 'd-reroute', layout: { 'line-join': 'round', 'line-cap': 'round' }, paint: { 'line-color': C.halo, 'line-width': 6, 'line-opacity': 0.8 } });
  map.addLayer({ id: 'd-reroute', type: 'line', source: 'd-reroute', layout: { 'line-join': 'round', 'line-cap': 'round' }, paint: { 'line-color': C.reroute, 'line-width': 3 } });
  map.addLayer({ id: 'd-reroute-chev', type: 'symbol', source: 'd-reroute', layout: { 'symbol-placement': 'line', 'symbol-spacing': 90, 'icon-image': 'chevron', 'icon-size': 0.9, 'icon-rotation-alignment': 'map', 'icon-allow-overlap': true, 'icon-ignore-placement': true }, paint: { 'icon-color': C.reroute, 'icon-halo-color': C.halo, 'icon-halo-width': 1 } });
  // the airports the current airport plan closes: the closed-airport symbol, the radius dashed
  map.addLayer({ id: 'd-closure-ring', type: 'line', source: 'd-closures', paint: { 'line-color': C.closed, 'line-opacity': 0.55, 'line-width': 1.3, 'line-dasharray': [3, 3] } });
  map.addLayer({ id: 'd-airports', type: 'symbol', source: 'd-airports', layout: { 'icon-image': 'closed-airport', 'icon-size': 0.85, 'icon-allow-overlap': true, 'icon-ignore-placement': true } });
  map.addLayer({ id: 'd-airport-label', type: 'symbol', source: 'd-airports', layout: { 'text-field': ['step', ['zoom'], ['get', 'icao'], 6.5, ['concat', ['get', 'icao'], ' closed']], 'text-font': ['Noto Sans Bold'], 'text-size': 12, 'text-variable-anchor': ['bottom', 'top', 'left', 'right'], 'text-radial-offset': 1, 'text-optional': true }, paint: { 'text-color': C.closed, 'text-halo-color': C.halo, 'text-halo-width': 2 } });
  map.addLayer({ id: 'd-volcanoes', type: 'symbol', source: 'd-volcanoes', layout: { 'icon-image': ['concat', 'volcano-', ['get', 'code']], 'icon-size': 0.7, 'icon-allow-overlap': true, 'icon-ignore-placement': true, 'text-field': ['get', 'name'], 'text-font': ['Noto Sans Regular'], 'text-size': 12, 'text-offset': [0, 1.4], 'text-anchor': 'top', 'text-optional': true }, paint: { 'text-color': C.label, 'text-halo-color': C.halo, 'text-halo-width': 1.5 } });
  // the flight under review: its ring in the plan's white (the Wall's picked ring); the plane is
  // amber only when TEPHRA flags it (a draft, or a picked plane that is exposed)
  map.addLayer({ id: 'd-sel-ring', type: 'circle', source: 'd-aircraft', filter: ['get', 'sel'], paint: { 'circle-radius': 16, 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': C.reroute, 'circle-stroke-width': 2 } });
  map.addLayer({
    id: 'd-aircraft', type: 'symbol', source: 'd-aircraft',
    layout: { 'icon-image': 'ac-sdf', 'icon-size': ['case', ['get', 'sel'], 0.8, ['get', 'draft'], 0.6, 0.42], 'icon-rotate': ['get', 'trk'], 'icon-rotation-alignment': 'map', 'icon-allow-overlap': true, 'icon-ignore-placement': true, 'symbol-sort-key': ['case', ['get', 'sel'], 2, ['get', 'draft'], 1, 0] },
    paint: { 'icon-color': ['case', ['get', 'flag'], C.tephra, ['get', 'draft'], C.reroute, C.aircraft], 'icon-opacity': ['case', ['any', ['get', 'draft'], ['get', 'sel']], 1, 0.5], 'icon-halo-color': C.halo, 'icon-halo-width': 1.5 },
  });
}

// The flight the map is about: the draft under review, else a plane selected on the map (its path
// and card, said as having no open draft).
let pickHex = null;
function focusOf() {
  const adv = app.selectedId ? app.drafts.get(app.selectedId) || app.closed.get(app.selectedId) : null;
  if (adv) return adv;
  const f = pickHex && feats('aircraft').find((x) => x.properties && x.properties.hex === pickHex);
  if (!f) return null;
  const p = f.properties;
  return {
    id: `pick:${pickHex}`, hex: pickHex, flight_id: `${pickHex}:${p.volcano_id}`, volcano_id: p.volcano_id, picked: true,
    proxy_flight: p.proxy_flight || p.callsign, exposed: Boolean(p.exposed), inside_now: Boolean(p.exposed) && p.minutes_to_entry === 0,
    minutes_to_entry: p.exposed ? p.minutes_to_entry : null, reroute: null,
  };
}

function draw() {
  if (!ready || !snap) return;
  const sel = focusOf();
  const drafts = draftByHex();
  const cones = feats('cones').filter((f) => f.properties && f.properties.part === 'cone');
  map.getSource('d-cones').setData(fc(cones));
  const tephraKey = byId('desk-map').querySelector('[data-key="tephra"]');
  if (tephraKey) tephraKey.hidden = !cones.some((f) => f.properties.mode !== 'OFFICIAL');
  map.getSource('d-paths').setData(fc(feats('exposures').filter((f) => f.properties && f.properties.kind === 'path')
    .map((f) => ({ ...f, properties: { ...f.properties, sel: Boolean(sel && f.properties.flight_id === sel.flight_id) } }))));
  map.getSource('d-reroute').setData(fc(rerouteOf(sel)));
  const shut = new Map(((latestPlan() && latestPlan().closures) || []).map((c) => [c.icao, c]));
  const ports = airports ? airports.features.filter((f) => shut.has(f.properties.icao)) : [];
  map.getSource('d-airports').setData(fc(ports));
  map.getSource('d-closures').setData(fc(ports.filter((f) => shut.get(f.properties.icao).radius_nm > 0).map((f) => {
    const [lon, lat] = f.geometry.coordinates;
    const r = shut.get(f.properties.icao).radius_nm / 60;
    const k = Math.cos((lat * Math.PI) / 180) || 1;
    return { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [Array.from({ length: 65 }, (_, i) => { const t = (i / 64) * 2 * Math.PI; return [lon + (r * Math.cos(t)) / k, lat + r * Math.sin(t)]; })] } };
  })));
  map.getSource('d-volcanoes').setData(fc(feats('volcanoes').filter((f) => f.properties && f.properties.active)
    .map((f) => ({ ...f, properties: { name: f.properties.name, code: f.properties.color_code in C.codes ? f.properties.color_code : 'UNKNOWN' } }))));
  map.getSource('d-aircraft').setData(fc(feats('aircraft').filter((f) => f.properties && f.geometry)
    .map((f) => ({ type: 'Feature', geometry: f.geometry, properties: { hex: f.properties.hex, trk: f.properties.track_deg || 0, draft: drafts.has(f.properties.hex), sel: Boolean(sel && sel.hex === f.properties.hex), flag: Boolean(sel && sel.hex === f.properties.hex && (!sel.picked || sel.exposed)) } }))));
  placeCard(sel);
}

// The reroute the draft under review proposes (code computed every point). Only the draft's own:
// a reroute the snapshot computed for a flight whose draft holds or changes level is not what
// the dispatcher is approving, so it is not drawn.
function rerouteOf(sel) {
  const path = sel && sel.reroute && Array.isArray(sel.reroute.path) ? sel.reroute.path.filter((p) => Array.isArray(p) && Number.isFinite(p[0]) && Number.isFinite(p[1])) : [];
  return path.length > 1 ? [{ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: path } }] : [];
}

// The card on the flight under review: who, where, what is proposed; it follows the plane.
function placeCard(sel) {
  const plane = sel && feats('aircraft').find((f) => f.properties && f.properties.hex === sel.hex && f.geometry);
  const note = byId('desk-map').querySelector('.dmap__note');
  // a draft whose aircraft the newest picture no longer holds: said, never guessed
  if (note) {
    note.hidden = !sel || Boolean(plane);
    if (sel && !plane) note.textContent = `${sel.proxy_flight || sel.hex}: no current position in the newest picture`;
  }
  if (!plane) {
    if (card) card.remove();
    // back from a review to Decide: the whole picture again
    if (!sel && shownFor !== null && ready) fitAll();
    shownFor = null;
    return;
  }
  const p = plane.properties;
  const level = Number.isFinite(p.alt_baro_ft) ? `FL${String(Math.round(p.alt_baro_ft / 100)).padStart(3, '0')}` : null;
  const when = sel.inside_now ? 'inside the ash' : Number.isFinite(sel.minutes_to_entry) ? `enters in ${sel.minutes_to_entry} min` : null;
  const node = el('div', { class: 'dmap-card' },
    el('b', { text: sel.proxy_flight || sel.callsign || sel.hex }),
    el('span', { text: [level, sel.picked && !sel.exposed ? 'not heading into the ash' : when].filter(Boolean).join(' · ') }),
    sel.picked ? el('span', { text: 'No open draft' }) : null);
  if (!card) card = new window.maplibregl.Marker({ element: el('div', { class: 'dmap-card-anchor' }), anchor: 'left', offset: [22, 0] });
  card.getElement().replaceChildren(node);
  card.setLngLat(plane.geometry.coordinates).addTo(map);
  if (shownFor !== sel.id) {
    shownFor = sel.id;
    // the plane, its volcano, its path into the ash and its reroute, all in view (the card to the
    // plane's right gets its room)
    const pts = [plane.geometry.coordinates];
    const vent = feats('volcanoes').find((f) => f.properties && String(f.properties.id) === String(sel.volcano_id) && f.geometry);
    if (vent) pts.push(vent.geometry.coordinates);
    for (const f of [...feats('exposures').filter((x) => x.properties && x.properties.flight_id === sel.flight_id), ...rerouteOf(sel)]) if (f.geometry && f.geometry.type === 'LineString') pts.push(...f.geometry.coordinates);
    const lons = pts.map((q) => q[0]), lats = pts.map((q) => q[1]);
    const w = map.getContainer().clientWidth;
    // framed wide: the region around the flight reads at once, not only the plane
    const pad = { top: 90, bottom: 90, left: Math.round(w * 0.15), right: Math.round(Math.min(240, w * 0.4)) };
    map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: pad, maxZoom: 5.4, duration: reducedMotion() ? 0 : 900 });
  }
}
// Back to the whole picture: every ash area and every flight in or heading in.
function fitAll() {
  const pts = [];
  for (const f of feats('cones')) if (f.properties && f.properties.part === 'cone') for (const ring of (f.geometry.type === 'Polygon' ? [f.geometry.coordinates[0]] : f.geometry.coordinates.map((x) => x[0]))) pts.push(...ring);
  for (const f of feats('aircraft')) if (f.properties && f.properties.exposed && f.geometry) pts.push(f.geometry.coordinates);
  if (!pts.length) return;
  const lons = pts.map((p) => p[0]), lats = pts.map((p) => p[1]);
  map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: 64, duration: reducedMotion() ? 0 : 600, maxZoom: 5.2 });
}

function build(node) {
  C = symbolColours();
  map = new window.maplibregl.Map({
    container: node.querySelector('.dmap__gl'), style: STYLE_URL, center: [108, -6], zoom: 4.5, minZoom: 2, maxZoom: 10,
    attributionControl: false, dragRotate: false, pitchWithRotate: false, touchPitch: false, renderWorldCopies: false, fadeDuration: 0,
  });
  map.touchZoomRotate.disableRotation();
  map.addControl(new window.maplibregl.AttributionControl({ compact: true }), 'bottom-right');
  map.on('styleimagemissing', (e) => { if (!map.hasImage(e.id)) map.addImage(e.id, { width: 1, height: 1, data: new Uint8Array(4) }); });
  map.on('style.load', () => {
    nightBasemap(map, nightColours(), { places: false });
    addImages(map, C);
    addLayers(C);
    ready = true;
    draw();
    if (!app.selectedId) fitAll();
  });
  map.on('load', () => node.querySelector('.maplibregl-ctrl-attrib')?.classList.remove('maplibregl-compact-show'));
  map.on('mouseenter', 'd-aircraft', () => { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', 'd-aircraft', () => { map.getCanvas().style.cursor = ''; });
  // a plane with an open draft opens its review; any other shows its path and card
  map.on('click', (e) => {
    const hits = map.queryRenderedFeatures([[e.point.x - 6, e.point.y - 6], [e.point.x + 6, e.point.y + 6]], { layers: ['d-aircraft'] });
    const withDraft = hits.find((f) => f.properties.draft);
    const adv = withDraft && draftByHex().get(withDraft.properties.hex);
    if (adv && onOpen) {
      pickHex = null;
      onOpen(adv.id);
      return;
    }
    pickHex = hits[0] ? hits[0].properties.hex : null;
    draw();
  });
  node.addEventListener('click', (e) => {
    const b = e.target.closest('[data-dmap]');
    if (!b) return;
    const a = b.dataset.dmap;
    if (a === 'in' || a === 'out') map.easeTo({ zoom: map.getZoom() + (a === 'in' ? 1 : -1), duration: reducedMotion() ? 0 : 250 });
    else if (a === 'fit') { shownFor = null; fitAll(); }
  });
  new ResizeObserver(() => map.resize()).observe(node);
}

// Mount once the Desk is shown (1280 px and up); call again on a resize.
export function initDeskMap(open) {
  onOpen = open;
  const node = byId('desk-map');
  if (!node || map || !WIDE.matches) return;
  const tool = (label, ic, act) => el('button', { type: 'button', class: 'tool', dataset: { dmap: act } }, icon(ic), el('span', { class: 'tool__tip', text: label }));
  node.replaceChildren(
    el('div', { class: 'dmap__gl' }),
    el('div', { class: 'dmap__ctl', role: 'toolbar', 'aria-label': 'Map view', 'aria-orientation': 'vertical' },
      el('div', { class: 'tool-grp' }, tool('Zoom in', 'i-plus', 'in'), tool('Zoom out', 'i-minus', 'out')),
      tool('Every flight in or heading in', 'i-frame', 'fit')),
    el('p', { class: 'dmap__note', role: 'status', hidden: true }),
    el('p', { class: 'dmap__key', 'aria-hidden': 'true' },
      el('span', { class: 'dmap__sw dmap__sw--official' }), 'Official ash',
      // said only while the map draws TEPHRA's own area (when it is the official area, only that is drawn)
      el('span', { class: 'dmap__ki', dataset: { key: 'tephra' }, hidden: true }, el('span', { class: 'dmap__sw dmap__sw--tephra' }), "TEPHRA's area"),
      el('span', { class: 'dmap__sw dmap__sw--sel' }), 'This flight',
      el('span', { class: 'dmap__sw dmap__sw--route' }), 'Reroute',
      el('span', { class: 'dmap__sw dmap__sw--closed' }), 'Closed airport'));
  api(PATHS.airports).then((res) => { if (res.ok && res.data && Array.isArray(res.data.features)) { airports = res.data; draw(); } });
  loadLib().then(() => build(node)).catch(() => {
    node.replaceChildren(el('p', { class: 'dmap__off', text: 'Map offline: the review has every fact.' }));
  });
}
WIDE.addEventListener?.('change', () => { if (WIDE.matches && onOpen) initDeskMap(onOpen); });

export function setDeskSnapshot(s) {
  snap = s;
  draw();
}

// A layer the stream sent (`cones`, `aircraft`) replaces that part of the snapshot.
export function patchDeskSnapshot(key, layer) {
  if (!snap || !layer || !Array.isArray(layer.features)) return;
  snap = { ...snap, [key]: layer };
  draw();
}

// The paths into the ash do not stream: while the map shows, the snapshot is read again every
// minute.
window.setInterval(async () => {
  if (!map || document.hidden || !WIDE.matches) return;
  const res = await api(PATHS.wall);
  if (res.ok && res.data && res.data.snapshot) setDeskSnapshot(res.data.snapshot);
}, 60000);

// The selection or the drafts changed.
export function drawDeskMap() {
  draw();
}
