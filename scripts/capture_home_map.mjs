// Home's map pictures (SPEC-v2 5.1): a real frame of the replay's map, never drawn by hand. Not part
// of CI.
//
// Run against a local TEPHRA in the stub replay (ports 8093-8096 only):
//   TEPHRA_PORT=8093 TEPHRA_LLM=stub TEPHRA_MODE=REPLAY TEPHRA_REPLAY_CASE=anak-krakatau-20260905 \
//   TEPHRA_REPLAY_START=2026-09-05T10:30:00Z TEPHRA_REPLAY_END=2026-09-05T13:30:00Z \
//   TEPHRA_LOCAL_SCHEDULER=1 uv run tephra
//   PLAYWRIGHT_NODE_MODULES=... node scripts/capture_home_map.mjs --base http://127.0.0.1:8093 --at 10:33
//
// It waits until the replay clock reads --at (HH:MM, UTC), opens /demo?intro=0&shots=1, keeps only
// the map column (body.shot-map, wall.css) without the map's own key, filter and tools, waits for the
// map to settle and screenshots the map at device scale 2. It writes tephra/web/home/replay-map.webp (1600 x 1000) and replay-map-phone.webp
// (780 x 400), each centre-cropped from the same frame and under MAX_BYTES, then writes the frame's
// clock and case into MAP_FRAME in tephra/web/home.js, which Home's caption reads. A frame it cannot
// take stops the run (exit 1) and nothing is written: Home then ships without the map.
//
// Playwright comes from a scratch node_modules outside this repository (npm i playwright there):
// PLAYWRIGHT_NODE_MODULES names that folder. It drives the system Chrome (channel "chrome").

import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const args = Object.fromEntries(process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith("--") ? [...acc, [a.slice(2), all[i + 1]]] : acc), []));
const BASE = (args.base || "http://127.0.0.1:8093").replace(/\/$/, "");
const AT = args.at || "10:33";
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT_DIR = path.join(ROOT, "tephra", "web", "home");
const HOME_JS = path.join(ROOT, "tephra", "web", "home.js");
const MAX_BYTES = 150_000;
const OUTPUTS = [
  { file: "replay-map.webp", w: 1600, h: 1000 },
  { file: "replay-map-phone.webp", w: 780, h: 400 },
];
const MON3 = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
if (!/^\d{2}:\d{2}$/.test(AT)) { console.error("--at is HH:MM (UTC)"); process.exit(2); }
if (!process.env.PLAYWRIGHT_NODE_MODULES) {
  console.error("set PLAYWRIGHT_NODE_MODULES to the folder holding a scratch node_modules with playwright");
  process.exit(2);
}
const require = createRequire(path.join(process.env.PLAYWRIGHT_NODE_MODULES, "x.js"));
const { chromium } = require("playwright");

const getState = async () => (await fetch(`${BASE}/api/state`)).json();
const clockOf = (state) => state.now.slice(11, 16);

// The case words Home's caption shows, as replay-words.js words them: "Anak Krakatau, 5 Sep 2026".
function caseWords(replay) {
  const at = replay.label.indexOf(":");
  const name = at > 0 ? replay.label.slice(0, at).trim() : "";
  const d = new Date(replay.window_from || replay.recorded_from);
  const day = `${d.getUTCDate()} ${MON3[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
  return name && !/\d/.test(name) ? `${name}, ${day}` : day;
}

// Ports are shared between agents: check what is running before trusting a frame.
let state = await getState();
if (state.mode !== "REPLAY" || !state.replay || state.replay.synthetic) {
  console.error("expected a replay of a real case; the server runs " + (state.replay?.label || state.mode));
  process.exit(2);
}
const deadline = Date.now() + 15 * 60_000;
while (clockOf(state) !== AT) {
  if (Date.now() > deadline) { console.error(`the replay clock never read ${AT} (it reads ${clockOf(state)})`); process.exit(1); }
  await new Promise((r) => setTimeout(r, 5000));
  state = await getState();
}

// PNG -> WebP of w x h, centre-cropped to that shape, the quality stepped down until it fits.
async function toWebp(page, png, w, h) {
  const res = await page.evaluate(async ({ b64, w, h, max }) => {
    const img = new Image();
    img.src = `data:image/png;base64,${b64}`;
    await img.decode();
    const scale = Math.max(w / img.width, h / img.height);
    const sw = w / scale, sh = h / scale;
    const c = Object.assign(document.createElement("canvas"), { width: w, height: h });
    const g = c.getContext("2d");
    g.imageSmoothingQuality = "high";
    g.drawImage(img, (img.width - sw) / 2, (img.height - sh) / 2, sw, sh, 0, 0, w, h);
    let out = null;
    for (const q of [0.82, 0.76, 0.7, 0.64, 0.58, 0.52, 0.46]) {
      const url = c.toDataURL("image/webp", q);
      out = { b64: url.slice(url.indexOf(",") + 1), q };
      if (out.b64.length * 0.75 <= max) break;
    }
    return out;
  }, { b64: png.toString("base64"), w, h, max: MAX_BYTES });
  const buf = Buffer.from(res.b64, "base64");
  if (buf.length > MAX_BYTES) throw new Error(`a frame stays over ${MAX_BYTES} bytes at quality ${res.q}`);
  return { buf, q: res.q };
}

const browser = await chromium.launch({ channel: "chrome" });
const written = [];
try {
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1056 }, deviceScaleFactor: 2, colorScheme: "dark", reducedMotion: "reduce" });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/demo?intro=0&shots=1`);
  await page.waitForSelector("#map-pane", { state: "visible" });
  // Home draws its own key, count and attribution: the map's key, flight filter, tools and notes go
  // (through the CSSOM: the page's CSP refuses an inline style sheet).
  await page.evaluate(() => {
    document.body.classList.add("shot-map");
    for (const n of document.querySelectorAll("#legend, #flight-filter, #tools, .map-pills, #map-notes, .maplibregl-control-container")) n.style.setProperty("display", "none", "important");
  });
  await page.waitForFunction(() => window.__tephra?.map?.loaded() && !window.__tephra.map.isMoving(), null, { timeout: 30_000 });
  await page.evaluate(() => { window.__tephra.map.resize(); return new Promise((r) => window.__tephra.map.once("idle", r)); });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(2000);
  const png = await page.locator("#map-pane").screenshot({ type: "png" });
  const shown = clockOf(await getState());
  const encoder = await ctx.newPage();
  const files = [];
  for (const out of OUTPUTS) files.push({ ...out, ...(await toWebp(encoder, png, out.w, out.h)) });
  const js = fs.readFileSync(HOME_JS, "utf8");
  const line = /^const MAP_FRAME = \{ at: "[^"]*", case: "[^"]*" \};$/m;
  if (!line.test(js)) throw new Error("home.js has no MAP_FRAME line to write");
  fs.mkdirSync(OUT_DIR, { recursive: true });
  for (const f of files) {
    fs.writeFileSync(path.join(OUT_DIR, f.file), f.buf);
    written.push(`${f.file} ${f.w}x${f.h} ${Math.round(f.buf.length / 1000)} kB (q ${f.q})`);
  }
  fs.writeFileSync(HOME_JS, js.replace(line, `const MAP_FRAME = { at: ${JSON.stringify(shown)}, case: ${JSON.stringify(caseWords(state.replay))} };`));
} catch (err) {
  console.log(`FAIL ${err.message}`);
  process.exitCode = 1;
} finally {
  await browser.close();
}
for (const w of written) console.log(`ok ${w}`);
