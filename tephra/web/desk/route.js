// The reroute sketch: an inline SVG of the computed route, the hazard it goes around and the
// straight line it replaces. Every point is a coordinate TEPHRA's code computed (RerouteOption);
// nothing here invents a waypoint. Equirectangular, scaled by cos(latitude), fitted to the route.

const NS = 'http://www.w3.org/2000/svg';
const W = 320;
const H = 200;
const PAD = 26;

function svg(tag, attrs = {}, text = null) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  if (text !== null) node.textContent = text;
  return node;
}

const finite = (p) => Array.isArray(p) && p.length >= 2 && Number.isFinite(p[0]) && Number.isFinite(p[1]);

function rings(geometry) {
  if (!geometry) return [];
  if (geometry.type === 'Polygon') return geometry.coordinates.slice(0, 1);
  if (geometry.type === 'MultiPolygon') return geometry.coordinates.map((poly) => poly[0]);
  return [];
}

export function routeMap(option, geometry, { mode = 'OFFICIAL' } = {}) {
  const path = (option.path || []).filter(finite);
  if (path.length < 2) return null;
  const pts = [...path, ...(option.waypoints || []).filter(finite)];
  let [minLon, maxLon, minLat, maxLat] = [Infinity, -Infinity, Infinity, -Infinity];
  for (const [lon, lat] of pts) {
    minLon = Math.min(minLon, lon);
    maxLon = Math.max(maxLon, lon);
    minLat = Math.min(minLat, lat);
    maxLat = Math.max(maxLat, lat);
  }
  const midLat = (minLat + maxLat) / 2;
  const kx = Math.cos((midLat * Math.PI) / 180);
  const spanX = Math.max((maxLon - minLon) * kx, 0.4);
  const spanY = Math.max(maxLat - minLat, 0.4);
  const scale = Math.min((W - 2 * PAD) / spanX, (H - 2 * PAD) / spanY);
  const offX = (W - spanX * scale) / 2;
  const offY = (H - spanY * scale) / 2;
  const px = ([lon, lat]) => [offX + (lon - minLon) * kx * scale, H - offY - (lat - minLat) * scale];
  const d = (list) => list.map((p, i) => `${i ? 'L' : 'M'}${px(p).map((n) => n.toFixed(1)).join(' ')}`).join('');

  const root = svg('svg', {
    class: 'rmap',
    viewBox: `0 0 ${W} ${H}`,
    role: 'img',
    'aria-label': `Route sketch: ${option.route_string || 'reroute'}`,
    preserveAspectRatio: 'xMidYMid meet',
  });
  const defs = svg('defs');
  const hatch = svg('pattern', { id: 'rmap-hatch', width: 7, height: 7, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)' });
  hatch.append(svg('line', { x1: 0, y1: 0, x2: 0, y2: 7, class: 'rmap__hatch' }));
  defs.append(hatch);
  root.append(defs, svg('rect', { class: 'rmap__bg', x: 0, y: 0, width: W, height: H }));

  const zone = mode === 'OFFICIAL' ? 'official' : 'tephra';
  for (const ring of rings(geometry)) {
    const clean = ring.filter(finite);
    if (clean.length < 3) continue;
    root.append(svg('path', { class: `rmap__zone rmap__zone--${zone}`, d: `${d(clean)}Z` }));
    root.append(svg('path', { class: 'rmap__hatchfill', d: `${d(clean)}Z`, fill: 'url(#rmap-hatch)' }));
  }

  // The present track the route replaces: start to end in a straight line.
  const first = path[0];
  const last = path[path.length - 1];
  root.append(svg('path', { class: 'rmap__direct', d: d([first, last]) }));
  root.append(svg('path', { class: 'rmap__route', d: d(path) }));

  (option.waypoints || []).filter(finite).forEach((wp, i) => {
    const [x, y] = px(wp);
    root.append(svg('circle', { class: 'rmap__wp', cx: x.toFixed(1), cy: y.toFixed(1), r: 8 }));
    root.append(svg('text', { class: 'rmap__wpn', x: x.toFixed(1), y: (y + 3.6).toFixed(1), 'text-anchor': 'middle' }, String(i + 1)));
  });

  const [sx, sy] = px(first);
  root.append(svg('circle', { class: 'rmap__start', cx: sx.toFixed(1), cy: sy.toFixed(1), r: 5 }));
  const flipNow = sx > W - 50;
  root.append(svg('text', { class: 'rmap__lab', x: (flipNow ? sx - 9 : sx + 9).toFixed(1), y: (sy - 7).toFixed(1), 'text-anchor': flipNow ? 'end' : 'start' }, 'Now'));
  const [ex, ey] = px(last);
  root.append(svg('rect', { class: 'rmap__end', x: (ex - 5).toFixed(1), y: (ey - 5).toFixed(1), width: 10, height: 10, transform: `rotate(45 ${ex.toFixed(1)} ${ey.toFixed(1)})` }));
  const endWord = option.end_icao || (option.kind === 'REJOIN_TRACK' ? 'Rejoin' : 'End');
  const anchorEnd = ex > W - 60;
  root.append(svg('text', { class: 'rmap__lab', x: (anchorEnd ? ex - 9 : ex + 9).toFixed(1), y: (ey - 7).toFixed(1), 'text-anchor': anchorEnd ? 'end' : 'start' }, endWord));
  return root;
}
