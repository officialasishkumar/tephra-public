// The Guide's annotated screenshots (docs/UI-DESIGN.md 7.29). Not part of CI.
//
// Run against a local TEPHRA in the stub replay with onboarding shown, left running for a minute so
// drafts exist (local servers on ports 8093-8096 only):
//   TEPHRA_PORT=8093 TEPHRA_LLM=stub TEPHRA_MODE=REPLAY TEPHRA_REPLAY_CASE=anak-krakatau-20260905 \
//   TEPHRA_LOCAL_SCHEDULER=1 TEPHRA_DESK_PIN=1234 TEPHRA_FEATURES=connect,onboard \
//   TEPHRA_SESSION_SECRET=<43 random characters> uv run tephra
//   PLAYWRIGHT_NODE_MODULES=... node scripts/capture_guide_shots.mjs --base http://127.0.0.1:8093 --pin 1234
//
// For each shot it opens the page, reads the boxes of the marks (CSS selectors; on the Wall, a
// clear patch of each ash area found with the map's own hit test), takes the screenshot at device
// scale 2 and stores it as WebP under tephra/web/guide/shots/ (each under MAX_BYTES), then writes
// tephra/web/data/guide-shots.json: {name: {w, h, marks: [{n, x, y, w, h}]}}, the image size in
// pixels and each mark in percent of it (an area mark also has "pin": true; the guide draws it as
// a badge on the area). A mark it cannot find stops the run (exit 1): the shot is
// retaken at another moment, never written with a mark missing. The guide's legend numbers follow
// the order of MARKS below.
//
// Playwright comes from a scratch node_modules outside this repository (npm i playwright there):
// PLAYWRIGHT_NODE_MODULES names that folder. It drives the system Chrome (channel "chrome").

import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const args = Object.fromEntries(process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith("--") ? [...acc, [a.slice(2), all[i + 1]]] : acc), []));
const BASE = (args.base || "http://127.0.0.1:8093").replace(/\/$/, "");
const PIN = args.pin || "1234";
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SHOT_DIR = path.join(ROOT, "tephra", "web", "guide", "shots");
const JSON_PATH = path.join(ROOT, "tephra", "web", "data", "guide-shots.json");
const MAX_BYTES = 250_000;
const PAD = 4; // css px of air around each mark
if (!process.env.PLAYWRIGHT_NODE_MODULES) {
  console.error("set PLAYWRIGHT_NODE_MODULES to the folder holding a scratch node_modules with playwright");
  process.exit(2);
}
const require = createRequire(path.join(process.env.PLAYWRIGHT_NODE_MODULES, "x.js"));
const { chromium } = require("playwright");

// Ports are shared between agents: check what is running before trusting a shot.
const state = await (await fetch(`${BASE}/api/state`)).json();
if (state.mode !== "REPLAY") { console.error(`expected a REPLAY, the server runs ${state.mode}`); process.exit(2); }
if (!(state.features || []).includes("onboard")) { console.error("start the server with TEPHRA_FEATURES=connect,onboard"); process.exit(2); }

// A mark: a CSS selector (its first visible match, optionally the one whose text has `text`; with
// `deep`, the box takes in its children, for a map label whose text overflows its dot),
// or `area`: a patch of the Wall map inside that area ("official", or "tephra": TEPHRA's estimate
// outside the official area), clear of every panel over the map.
const MARKS = {
  wall: [
    { sel: "#rail-btn" },
    { sel: "#rail-exposed" },
    { area: "tephra" },
    { area: "official" },
    { sel: "#assist" },
    { sel: "#clock-sub" },
    { sel: "#details-btn" },
    { sel: "#side-desk" },
  ],
  assistant: [
    { sel: ".flow-head__brand" },
    { sel: ".flow-labels > *", text: "SIGMET", deep: true },
    { sel: ".flow-panel" },
    { sel: ".flow-skill" },
    { sel: ".flow-you" },
    { sel: ".flow-log" },
    { sel: ".flow-player" },
  ],
  desk: [
    { sel: "#tabbar" },
    { sel: "section.next" },
    { sel: "section.next .ai-mark" },
    { sel: "section.grp" },
    { sel: "#desk-map" },
    { sel: "#ask-btn" },
  ],
  "desk-phone": [
    { sel: ".rv2__action" },
    { sel: "dl.facts" },
    { sel: ".textbox" },
    { sel: ".recordbtn" },
    { sel: ".approve" },
    { sel: ".actions__inner .secondary" },
  ],
  onboard: [
    { sel: "section:has(#provide-h)" },
    { sel: "#ob-start" },
    { sel: "#ob-after" },
    { sel: "#ob-private" },
    { sel: "#ob-notbuilt" },
  ],
};

// In the page: the box (css px) of each mark, or a string naming the one not found.
function boxesIn(marks) {
  const visible = (n) => { const r = n.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(n).visibility !== "hidden"; };
  // The map labels are placed only when they do not collide, so the mark goes on the area itself:
  // on a grid over the map, every 64 x 44 px patch whose corners and centre are inside the area and
  // not under a panel; the patch nearest the middle of those wins.
  const areaBox = (kind) => {
    const map = window.__tephra?.map;
    if (!map) return null;
    const canvas = map.getCanvas();
    const cr = canvas.getBoundingClientRect();
    const official = map.getStyle().layers.map((l) => l.id).filter((id) => id.startsWith("official-fill-"));
    const tephra = map.getLayer("tephra-fill") ? ["tephra-fill"] : [];
    const hit = (x, y, ids) => ids.length > 0 && map.queryRenderedFeatures([x, y], { layers: ids }).length > 0;
    const inArea = (x, y) => (kind === "official" ? hit(x, y, official) : hit(x, y, tephra) && !hit(x, y, official));
    const clear = (x, y) => document.elementFromPoint(cr.left + x, cr.top + y) === canvas;
    const BW = 64, BH = 44, STEP = 16;
    const fits = [];
    for (let y = 0; y + BH <= cr.height; y += STEP) for (let x = 0; x + BW <= cr.width; x += STEP) {
      const pts = [[x, y], [x + BW, y], [x, y + BH], [x + BW, y + BH], [x + BW / 2, y + BH / 2]];
      if (pts.every(([px, py]) => clear(px, py) && inArea(px, py))) fits.push([x, y]);
    }
    if (!fits.length) return null;
    const mx = fits.reduce((a, [x]) => a + x, 0) / fits.length;
    const my = fits.reduce((a, [, y]) => a + y, 0) / fits.length;
    const [bx, by] = fits.reduce((best, p) => (Math.hypot(p[0] - mx, p[1] - my) < Math.hypot(best[0] - mx, best[1] - my) ? p : best));
    return { x: cr.left + bx, y: cr.top + by, w: BW, h: BH };
  };
  return marks.map((m) => {
    if (m.area) return areaBox(m.area) || `map area ${m.area}`;
    const n = [...document.querySelectorAll(m.sel)].find((x) => visible(x) && (!m.text || x.textContent.includes(m.text)));
    if (!n) return `${m.sel}${m.text ? ` with "${m.text}"` : ""}`;
    const rects = [n, ...(m.deep ? n.querySelectorAll("*") : [])].map((x) => x.getBoundingClientRect()).filter((r) => r.width > 0 && r.height > 0);
    const x0 = Math.min(...rects.map((r) => r.left)), y0 = Math.min(...rects.map((r) => r.top));
    return { x: x0, y: y0, w: Math.max(...rects.map((r) => r.right)) - x0, h: Math.max(...rects.map((r) => r.bottom)) - y0 };
  });
}

const round2 = (v) => Math.round(v * 100) / 100;

function percentMarks(name, boxes, vw, vh) {
  const missing = boxes.filter((b) => typeof b === "string");
  if (missing.length) throw new Error(`${name}: mark not found: ${missing.join(", ")}`);
  return boxes.map((b, i) => {
    const x0 = Math.max(0, b.x - PAD), y0 = Math.max(0, b.y - PAD);
    const x1 = Math.min(vw, b.x + b.w + PAD), y1 = Math.min(vh, b.y + b.h + PAD);
    if (x1 - x0 < 4 || y1 - y0 < 4) throw new Error(`${name}: mark ${i + 1} is off the screen`);
    const mark = { n: i + 1, x: round2((x0 / vw) * 100), y: round2((y0 / vh) * 100), w: round2(((x1 - x0) / vw) * 100), h: round2(((y1 - y0) / vh) * 100) };
    return MARKS[name][i].area ? { ...mark, pin: true } : mark;
  });
}

// PNG at device scale 2 -> WebP at `outW` px, the quality stepped down until the file fits.
async function toWebp(encoder, png, outW, outH) {
  const res = await encoder.evaluate(async ({ b64, w, h, max }) => {
    const img = new Image();
    img.src = `data:image/png;base64,${b64}`;
    await img.decode();
    const c = Object.assign(document.createElement("canvas"), { width: w, height: h });
    const g = c.getContext("2d");
    g.imageSmoothingQuality = "high";
    g.drawImage(img, 0, 0, w, h);
    let out = null;
    for (const q of [0.86, 0.8, 0.74, 0.68, 0.62, 0.56, 0.5]) {
      const url = c.toDataURL("image/webp", q);
      out = { b64: url.slice(url.indexOf(",") + 1), q };
      if (out.b64.length * 0.75 <= max) break;
    }
    return out;
  }, { b64: png.toString("base64"), w: outW, h: outH, max: MAX_BYTES });
  const buf = Buffer.from(res.b64, "base64");
  if (buf.length > MAX_BYTES) throw new Error(`a shot stays over ${MAX_BYTES} bytes at quality ${res.q}`);
  return { buf, q: res.q };
}

const settle = (page, ms) => page.waitForTimeout(ms);
const mapReady = (page) => page.waitForFunction(() => window.__tephra?.map?.loaded() && !window.__tephra.map.isMoving(), null, { timeout: 30_000 });

async function signIn(page) {
  await page.goto(`${BASE}/desk`);
  // with visitor access on, the sign-in opens on the Visitor tab (3a46863): pick Dispatcher
  const tab = page.locator("#tab-dispatcher");
  // the tabs appear once the Desk has read /api/state; until then neither pane is final
  await page.waitForSelector("#login-name:visible, #tab-dispatcher:visible", { timeout: 15_000 });
  if (await tab.isVisible()) await tab.click();
  await page.waitForSelector("#login-name", { state: "visible" });
  await page.fill("#login-name", "Dispatcher");
  await page.fill("#login-pin", PIN);
  await page.click("#login-submit");
  await page.waitForSelector("section.next", { state: "visible", timeout: 30_000 });
}

// Each shot: where it goes, its viewport, how to bring the page to the moment, the stored width.
const SHOTS = [
  { name: "wall", vw: 1440, vh: 900, outW: 1800, go: async (page) => {
    await page.goto(`${BASE}/demo?intro=0&shots=1`);
    await page.waitForSelector("#rail-btn", { state: "visible" });
    await mapReady(page);
    await settle(page, 3000);
  } },
  { name: "assistant", vw: 1440, vh: 900, outW: 1800, go: async (page) => {
    await page.goto(`${BASE}/assistant?shots=1`);
    await page.waitForSelector(".flow-skill", { state: "visible" });
    await settle(page, 5000);
  } },
  { name: "desk", vw: 1440, vh: 900, outW: 1800, go: async (page) => {
    await page.goto(`${BASE}/desk`);
    await page.waitForSelector("section.next", { state: "visible" });
    await settle(page, 4000);
  } },
  // the review sheet on a phone, the viewport as tall as the sheet so it shows whole
  { name: "desk-phone", vw: 390, vh: 844, outW: 780, go: async (page) => {
    await page.goto(`${BASE}/desk`);
    await page.getByRole("button", { name: /^Review RFA/ }).first().click();
    await page.waitForSelector(".approve", { state: "visible" });
    await settle(page, 1500);
    const tall = await page.evaluate(() => Math.min(1100, document.documentElement.scrollHeight));
    await page.setViewportSize({ width: 390, height: tall });
    await settle(page, 1500);
  } },
  // the onboarding landing as a first visitor sees it (no draft in this browser), the viewport as
  // tall as the landing so its After you submit, Private and Not built cards show
  { name: "onboard", vw: 1440, vh: 900, outW: 1800, go: async (page) => {
    await page.goto(`${BASE}/onboard`);
    await page.waitForSelector("#provide-h", { state: "visible" });
    await settle(page, 1500);
    const tall = await page.evaluate(() => Math.min(1400, document.documentElement.scrollHeight));
    await page.setViewportSize({ width: 1440, height: tall });
    await settle(page, 1500);
  } },
];

fs.mkdirSync(SHOT_DIR, { recursive: true });
const browser = await chromium.launch({ channel: "chrome" });
const out = {};
let failed = false;
try {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, colorScheme: "dark", reducedMotion: "reduce" });
  const encoder = await ctx.newPage();
  const login = await ctx.newPage();
  await signIn(login);
  await login.close();
  for (const shot of SHOTS) {
    const page = await ctx.newPage();
    page.on("console", (m) => { if (m.type() === "error" && !/status of 401/.test(m.text())) console.log(`${shot.name} console: ${m.text()}`); });
    try {
      await page.setViewportSize({ width: shot.vw, height: shot.vh });
      await shot.go(page);
      const { width: vw, height: vh } = page.viewportSize();
      await page.evaluate(() => document.fonts.ready);
      const marks = percentMarks(shot.name, await page.evaluate(boxesIn, MARKS[shot.name]), vw, vh);
      const png = await page.screenshot({ type: "png" });
      const outH = Math.round((shot.outW * vh) / vw);
      const { buf, q } = await toWebp(encoder, png, shot.outW, outH);
      fs.writeFileSync(path.join(SHOT_DIR, `${shot.name}.webp`), buf);
      out[shot.name] = { w: shot.outW, h: outH, marks };
      console.log(`ok ${shot.name}: ${shot.outW}x${outH}, ${Math.round(buf.length / 1000)} kB (q ${q}), ${marks.length} marks`);
    } catch (err) {
      failed = true;
      console.log(`FAIL ${err.message}`);
    } finally {
      await page.close();
    }
  }
} finally {
  await browser.close();
}
if (failed) process.exit(1);
const sorted = Object.fromEntries(Object.keys(out).sort().map((k) => [k, out[k]]));
fs.writeFileSync(JSON_PATH, `${JSON.stringify(sorted, null, 2)}\n`);
console.log(`wrote ${path.relative(ROOT, JSON_PATH)} and ${Object.keys(out).length} shots`);
