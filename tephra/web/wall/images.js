// Map images drawn on a canvas and added with map.addImage. Under TEPHRA's CSP MapLibre
// cannot load data: or SVG images (docs/UI-DESIGN.md 15), so every symbol is drawn here:
// the SDF plane, the flight-group marker, the SDF arrowhead, the eruption symbols, the
// stretchable label boxes, the hatch pattern and the crew report pin.

const MATERIAL_FLIGHT =
  "M409-421 137-311q-20 8-38.5-4T80-350v-18q0-11 5-19.5T98-402l311-219v-188q0-29 21-50t50-21q29 0 50 21t21 50v188l311 219q8 6 13 14.5t5 19.5v18q0 23-18.5 35t-38.5 4L551-421v172l109 76q7 5 11 12.5t4 15.5v19q0 17-13.5 27.5T631-93l-151-46-151 46q-17 5-30.5-5.5T285-126v-19q0-8 4-15.5t11-12.5l109-76v-172Z";

export const CODE_LETTER = { GREEN: "G", YELLOW: "Y", ORANGE: "O", RED: "R", UNKNOWN: "U" };

function canvas(w, h) {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  return c.getContext("2d", { willReadFrequently: true });
}

function alphaOf(ctx, w, h) {
  const rgba = ctx.getImageData(0, 0, w, h).data;
  const alpha = new Uint8ClampedArray(w * h);
  for (let i = 0; i < alpha.length; i++) alpha[i] = rgba[i * 4 + 3];
  return alpha;
}

// Signed distance field from an alpha mask (brute force; images are small and drawn once).
function alphaToSdf(alpha, w, h, radius, cutoff = 0.25) {
  const inside = new Uint8Array(w * h);
  for (let i = 0; i < inside.length; i++) inside[i] = alpha[i] >= 128 ? 1 : 0;
  const out = new Uint8ClampedArray(w * h * 4);
  const reach = Math.ceil(radius);
  const scale = 255 / radius;
  const base = 255 * (1 - cutoff);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const me = inside[y * w + x];
      let best = radius;
      for (let dy = -reach; dy <= reach; dy++) {
        const yy = y + dy;
        if (yy < 0 || yy >= h) continue;
        for (let dx = -reach; dx <= reach; dx++) {
          const xx = x + dx;
          if (xx < 0 || xx >= w || inside[yy * w + xx] === me) continue;
          const d = Math.hypot(dx, dy);
          if (d < best) best = d;
        }
      }
      const o = (y * w + x) * 4;
      out[o] = out[o + 1] = out[o + 2] = 255;
      out[o + 3] = Math.round(base + scale * (me ? best - 0.5 : 0.5 - best));
    }
  }
  return out;
}

function aircraftSdf(size = 96, padding = 16) {
  const ctx = canvas(size, size);
  const s = (size - 2 * padding) / 960;
  ctx.translate(padding, padding);
  ctx.scale(s, s);
  ctx.translate(0, 960);
  ctx.fillStyle = "#fff";
  ctx.fill(new Path2D(MATERIAL_FLIGHT));
  return { width: size, height: size, data: alphaToSdf(alphaOf(ctx, size, size), size, size, 16) };
}

function arrowheadSdf(size = 64, padding = 14) {
  const ctx = canvas(size, size);
  ctx.fillStyle = "#fff";
  ctx.beginPath();
  ctx.moveTo(size / 2, padding);
  ctx.lineTo(size - padding, size - padding);
  ctx.lineTo(size / 2, size - padding - 10);
  ctx.lineTo(padding, size - padding);
  ctx.closePath();
  ctx.fill();
  return { width: size, height: size, data: alphaToSdf(alphaOf(ctx, size, size), size, size, 12) };
}

// ICAO/WMO eruption symbol: trapezoid, three rays, the colour-code letter (section 5.3).
export function eruptionIcon(fill, letter, active, size = 64) {
  const ctx = canvas(size, size);
  const s = size / 64;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  ctx.beginPath();
  ctx.moveTo(26 * s, 22 * s);
  ctx.lineTo(38 * s, 22 * s);
  ctx.lineTo(55 * s, 57 * s);
  ctx.lineTo(9 * s, 57 * s);
  ctx.closePath();
  ctx.strokeStyle = "#05070a";
  ctx.lineWidth = 5 * s;
  ctx.stroke();
  if (active) {
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.beginPath();
    for (const [x1, y1, x2, y2] of [[32, 18, 32, 5], [27, 19, 19.5, 8], [37, 19, 44.5, 8]]) {
      ctx.moveTo(x1 * s, y1 * s);
      ctx.lineTo(x2 * s, y2 * s);
    }
    ctx.lineWidth = 6 * s;
    ctx.strokeStyle = "#05070a";
    ctx.stroke();
    ctx.strokeStyle = fill;
    ctx.lineWidth = 3 * s;
    ctx.stroke();
    ctx.fillStyle = "#05070a";
    ctx.font = `700 ${19 * s}px "IBM Plex Sans", system-ui, sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "alphabetic";
    ctx.fillText(letter, 32 * s, 52 * s);
  } else {
    ctx.strokeStyle = fill;
    ctx.lineWidth = 3 * s;
    ctx.stroke();
  }
  return ctx.getImageData(0, 0, size, size);
}

// Stretchable VAG-style label box for icon-text-fit (section 5.1).
function labelBox(border, size = 36, r = 6, bw = 3) {
  const ctx = canvas(size, size);
  ctx.beginPath();
  ctx.roundRect(bw / 2, bw / 2, size - bw, size - bw, r);
  ctx.fillStyle = "rgba(8,12,18,0.92)";
  ctx.fill();
  ctx.strokeStyle = border;
  ctx.lineWidth = bw;
  ctx.stroke();
  const a = r + bw;
  const b = size - r - bw;
  return [ctx.getImageData(0, 0, size, size), { pixelRatio: 2, stretchX: [[a, b]], stretchY: [[a, b]], content: [a, a, b, b] }];
}

// An airport code's tag on a route's end: a thin border in the route colour, so the code reads
// as an airport and not as a basemap town name.
function routeBox(hex, alpha) {
  const n = parseInt(hex.replace("#", ""), 16);
  return labelBox(`rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`, 24, 5, 2);
}

function hatch(color, size = 24) {
  const ctx = canvas(size, size);
  ctx.strokeStyle = color;
  ctx.globalAlpha = 0.55;
  ctx.lineWidth = 3;
  ctx.lineCap = "square";
  for (const o of [-size, 0, size]) {
    ctx.beginPath();
    ctx.moveTo(o, size);
    ctx.lineTo(o + size, 0);
    ctx.stroke();
  }
  return ctx.getImageData(0, 0, size, size);
}

// The crew report pin (UI-DESIGN 5.7): a map pin in the crew colour with a dark outline and a
// dark centre, drawn on top of its dashed caution area so the report position is never lost.
function crewPin(fill, size = 48) {
  const ctx = canvas(size, size);
  const s = size / 48;
  const pin = new Path2D();
  pin.moveTo(24 * s, 44 * s);
  pin.bezierCurveTo(24 * s, 44 * s, 9 * s, 29 * s, 9 * s, 19 * s);
  pin.arc(24 * s, 19 * s, 15 * s, Math.PI, 0);
  pin.bezierCurveTo(39 * s, 29 * s, 24 * s, 44 * s, 24 * s, 44 * s);
  pin.closePath();
  ctx.lineJoin = "round";
  ctx.strokeStyle = "#05070a";
  ctx.lineWidth = 5 * s;
  ctx.stroke(pin);
  ctx.fillStyle = fill;
  ctx.fill(pin);
  ctx.beginPath();
  ctx.arc(24 * s, 19 * s, 5.5 * s, 0, 2 * Math.PI);
  ctx.fillStyle = "#05070a";
  ctx.fill();
  return ctx.getImageData(0, 0, size, size);
}

// A group of RFA flights close together on the map (the exposed-cluster layer): an upright plane
// in the TEPHRA colour, a darker one behind it, and the count in a badge at the top right. One
// image per count, drawn when the map first asks for it (styleimagemissing in map.js).
export function flightGroupImage(n, fill, back) {
  const r = 2, P = 30, gap = 8, pad = 3, bh = 18, behind = [-7, 6];
  const text = String(n);
  const font = `700 ${12 * r}px "IBM Plex Sans", system-ui, sans-serif`;
  const probe = canvas(1, 1);
  probe.font = font;
  const bw = Math.max(bh, Math.ceil(probe.measureText(text).width / r) + 11);
  const cx = pad - behind[0] + P / 2, cy = pad + bh / 2 + P / 2 - 2;
  const w = Math.ceil(cx + P / 2 - gap + bw + pad) * r, h = Math.ceil(cy + P / 2 + behind[1] + pad) * r;
  const ctx = canvas(w, h);
  const path = new Path2D(MATERIAL_FLIGHT);
  const plane = (x, y, color) => {
    ctx.save();
    ctx.translate(x * r, y * r);
    const s = (P * r) / 960;
    ctx.scale(s, s);
    ctx.translate(-480, 480);
    ctx.lineJoin = "round";
    ctx.lineWidth = (3 * r) / s;
    ctx.strokeStyle = "#05070a";
    ctx.stroke(path);
    ctx.fillStyle = color;
    ctx.fill(path);
    ctx.restore();
  };
  plane(cx + behind[0], cy + behind[1], back);
  plane(cx, cy, fill);
  const bx = (cx + P / 2 - gap) * r;
  ctx.beginPath();
  ctx.roundRect(bx, pad * r, bw * r, bh * r, (bh / 2) * r);
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.lineWidth = 2 * r;
  ctx.strokeStyle = "#05070a";
  ctx.stroke();
  ctx.fillStyle = "#05070a";
  ctx.font = font;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, bx + (bw * r) / 2, (pad + bh / 2 + 0.5) * r);
  return ctx.getImageData(0, 0, w, h);
}

let cache = null;

// Build once (the SDFs take a few ms), add to any map (the compare map reuses them).
export function addImages(map, C) {
  if (!cache) {
    cache = {
      plane: aircraftSdf(),
      arrow: arrowheadSdf(),
      codes: Object.fromEntries(Object.entries(C.codes).map(([code, hex]) => [code, eruptionIcon(hex, CODE_LETTER[code], true)])),
      inactive: eruptionIcon("#6d7b8a", "", false),
      boxOfficial: labelBox(C.official),
      boxTephra: labelBox(C.tephra),
      boxClosed: labelBox(C.serious || C.official),
      boxAngle: labelBox(C.text1),
      boxObserver: labelBox(C.observer),
      boxRoute: routeBox(C.route, 0.5),
      boxRouteSel: routeBox(C.route, 1),
      hatch: hatch(C.tephra),
      pin: crewPin(C.crew),
    };
  }
  const add = (id, img, opts) => { if (!map.hasImage(id)) map.addImage(id, img, opts); };
  add("ac-sdf", cache.plane, { sdf: true, pixelRatio: 2 });
  add("arrowhead", cache.arrow, { sdf: true, pixelRatio: 2 });
  for (const [code, img] of Object.entries(cache.codes)) add(`volcano-${code}`, img, { pixelRatio: 2 });
  add("volcano-inactive", cache.inactive, { pixelRatio: 2 });
  add("box-official", ...cache.boxOfficial);
  add("box-tephra", ...cache.boxTephra);
  add("box-closed", ...cache.boxClosed);
  add("box-angle", ...cache.boxAngle);
  add("box-observer", ...cache.boxObserver);
  add("box-route", ...cache.boxRoute);
  add("box-route-sel", ...cache.boxRouteSel);
  // invisible: the route-avoid-* layers only reserve room that an airport code must not take
  add("route-avoid", { width: 16, height: 16, data: new Uint8Array(16 * 16 * 4) });
  add("hatch-tephra", cache.hatch, { pixelRatio: 2 });
  add("crew-pin", cache.pin, { pixelRatio: 2 });
}
