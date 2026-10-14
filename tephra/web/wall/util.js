// Small shared helpers for the Wall: DOM building (textContent only), the sprite, time and
// level formatting, and the spherical geometry the map needs. No feed text is ever parsed
// as HTML here.

export let SPRITE = "/static/icons.svg";

// Put the icon sprite into the document once, so icons drawn later (also while the server
// is unreachable) reference a local fragment instead of re-requesting the file.
export async function inlineSprite() {
  try {
    const res = await fetch(SPRITE);
    if (!res.ok) return;
    const doc = new DOMParser().parseFromString(await res.text(), "image/svg+xml");
    const svg = doc.documentElement;
    if (svg.nodeName !== "svg" || doc.querySelector("parsererror, script, foreignObject")) return;
    const node = document.importNode(svg, true);
    node.setAttribute("aria-hidden", "true");
    node.setAttribute("width", "0");
    node.setAttribute("height", "0");
    node.classList.add("sprite");
    document.body.prepend(node);
    SPRITE = "";
    for (const use of document.querySelectorAll('use[href^="/static/icons.svg#"]')) use.setAttribute("href", use.getAttribute("href").replace("/static/icons.svg", ""));
  } catch {
    /* keep the external sprite */
  }
}

export const $ = (id) => document.getElementById(id);

// el("div", { class: "x", text: "y", "aria-label": "z" }, child, "text", [more])
export function el(tag, attrs = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = String(v);
    else if (k === "dataset") Object.assign(node.dataset, v);
    else node.setAttribute(k, v === true ? "" : String(v));
  }
  append(node, kids);
  return node;
}

function append(node, kids) {
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    node.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
}

export function icon(id, cls = "icon", color = null) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", cls);
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `${SPRITE}#${id}`);
  svg.append(use);
  if (color) svg.style.color = color;
  return svg;
}

export const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// ------------------------------------------------------------------ time

export const ms = (iso) => (iso ? Date.parse(iso) : NaN);
export const pad = (n) => String(n).padStart(2, "0");
export function hhmmz(t) {
  if (!Number.isFinite(t)) return "—";
  const d = new Date(t);
  return `${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}Z`;
}
// The same time for a reader who does not know the Z: "10:32 UTC".
export function utcTime(t) {
  if (!Number.isFinite(t)) return "—";
  const d = new Date(t);
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`;
}
export function hhmmssz(t) {
  if (!Number.isFinite(t)) return "--:--:--Z";
  const d = new Date(t);
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}Z`;
}
const MON = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];
export function dayMon(t) {
  if (!Number.isFinite(t)) return "—";
  const d = new Date(t);
  return `${d.getUTCDate()} ${MON[d.getUTCMonth()]}`;
}
export function dateLong(t) {
  const d = new Date(t);
  const m = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][d.getUTCMonth()];
  return `${d.getUTCDate()} ${m} ${d.getUTCFullYear()}`;
}

// "27 s", "14 min", "2 h 5 min" (section 13: ages and countdowns)
export function age(seconds) {
  if (!Number.isFinite(seconds)) return "—";
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h} h ${m % 60} min`;
  return `${Math.round(h / 24)} days`;
}
export const durMin = (minutes) => age(Math.abs(minutes) * 60);

// The time in a source id suffix: VONA:SEMERU:20260925T1554Z
export function idTime(sourceId) {
  const m = /(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})Z$/.exec(sourceId || "");
  return m ? Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]) : NaN;
}

// "OBS 1100Z" -> the most recent such time at or before now (+5 min slack)
export function hhmmBefore(text, now) {
  const m = /(\d{2})(\d{2})Z/.exec(text || "");
  if (!m) return NaN;
  const d = new Date(now);
  let t = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), +m[1], +m[2]);
  if (t > now + 5 * 60e3) t -= 86400e3;
  return t;
}

// Local solar hour at a longitude (section 13: night at the vent)
export function solarHour(t, lon) {
  const d = new Date(t);
  return (((d.getUTCHours() + d.getUTCMinutes() / 60 + lon / 15) % 24) + 24) % 24;
}
export const isNight = (t, lon) => {
  const h = solarHour(t, lon);
  return h < 6 || h >= 18;
};

// ------------------------------------------------------------------ levels

export const fl = (ft) => (ft == null ? "—" : ft <= 0 ? "SFC" : `FL${String(Math.round(ft / 100)).padStart(3, "0")}`);
export const band = (a, b) => `${fl(a)}–${fl(b)}`;

// ------------------------------------------------------------------ compass

export const COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
const COMPASS_RE = /\b(NNE|ENE|ESE|SSE|SSW|WSW|WNW|NNW|NE|SE|SW|NW|N|E|S|W)\b/;
export function compassDeg(text) {
  const m = COMPASS_RE.exec(text || "");
  return m ? COMPASS.indexOf(m[1]) * 22.5 : null;
}
export const compassWord = (deg) => COMPASS[Math.round(deg / 22.5) % 16];

// ------------------------------------------------------------------ geometry (lon, lat)

const R_KM = 6371.0088;
const RAD = Math.PI / 180;
export function dest([lon, lat], bearingDeg, km) {
  const b = bearingDeg * RAD;
  const d = km / R_KM;
  const p1 = lat * RAD;
  const l1 = lon * RAD;
  const p2 = Math.asin(Math.sin(p1) * Math.cos(d) + Math.cos(p1) * Math.sin(d) * Math.cos(b));
  const l2 = l1 + Math.atan2(Math.sin(b) * Math.sin(d) * Math.cos(p1), Math.cos(d) - Math.sin(p1) * Math.sin(p2));
  return [l2 / RAD, p2 / RAD];
}
export function kmBetween(a, b) {
  const dLat = (b[1] - a[1]) * RAD;
  const dLon = (b[0] - a[0]) * RAD;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[1] * RAD) * Math.cos(b[1] * RAD) * Math.sin(dLon / 2) ** 2;
  return 2 * R_KM * Math.asin(Math.min(1, Math.sqrt(h)));
}
export const ringsOf = (g) => {
  if (!g) return [];
  if (g.type === "Polygon") return g.coordinates;
  if (g.type === "MultiPolygon") return g.coordinates.flat();
  if (g.type === "LineString") return [g.coordinates];
  if (g.type === "Point") return [[g.coordinates]];
  return [];
};
export function bboxOf(geoms) {
  let w = 180, s = 90, e = -180, n = -90;
  for (const g of geoms) for (const ring of ringsOf(g)) for (const [x, y] of ring) {
    w = Math.min(w, x); e = Math.max(e, x); s = Math.min(s, y); n = Math.max(n, y);
  }
  return w <= e && s <= n ? [[w, s], [e, n]] : null;
}
export function ringCentre(geom) {
  const ring = ringsOf(geom)[0] || [];
  const pts = ring.length > 1 && ring[0][0] === ring.at(-1)[0] && ring[0][1] === ring.at(-1)[1] ? ring.slice(0, -1) : ring;
  let x = 0, y = 0;
  for (const q of pts) { x += q[0]; y += q[1]; }
  return pts.length ? [x / pts.length, y / pts.length] : null;
}
export const inBbox = ([x, y], b) => x >= b.west && x <= b.east && y >= b.south && y <= b.north;

// Is a point inside a polygon ring set (even-odd)? Used for "the sector covers the drift".
export function pointInGeom(pt, geom) {
  let inside = false;
  for (const ring of ringsOf(geom)) {
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i], [xj, yj] = ring[j];
      if ((yi > pt[1]) !== (yj > pt[1]) && pt[0] < ((xj - xi) * (pt[1] - yi)) / (yj - yi) + xi) inside = !inside;
    }
  }
  return inside;
}

export const fc = (features) => ({ type: "FeatureCollection", features });

// Safe external link: only http(s) URLs are ever put in an href.
export function safeExternalUrl(url) {
  try {
    const u = new URL(url);
    return u.protocol === "https:" || u.protocol === "http:" ? u.href : null;
  } catch {
    return null;
  }
}

// Preferences kept per viewer (layer choices, shortcuts on/off). Never required to render.
export const prefs = {
  get(key, fallback) {
    try {
      const v = localStorage.getItem(`tephra.wall.${key}`);
      return v == null ? fallback : JSON.parse(v);
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try { localStorage.setItem(`tephra.wall.${key}`, JSON.stringify(value)); } catch { /* storage blocked */ }
  },
};
