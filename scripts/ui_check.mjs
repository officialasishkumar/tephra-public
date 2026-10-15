// UI screenshot and DOM pass for the redesign (docs/UI-REDESIGN.md R17.2). Not part of CI.
//
// Run against a local TEPHRA (stub model) in each mode, for example:
//   TEPHRA_PORT=8121 TEPHRA_LLM=stub TEPHRA_LOCAL_SCHEDULER=1 TEPHRA_DESK_PIN=1234 \
//   TEPHRA_MODE=REPLAY TEPHRA_REPLAY_CASE=anak-krakatau-20260905 \
//   TEPHRA_REPLAY_START=2026-09-05T10:30:00Z TEPHRA_REPLAY_END=2026-09-05T19:30:00Z uv run tephra
//   node scripts/ui_check.mjs --base http://127.0.0.1:8121 --mode REPLAY --case anak-krakatau-20260905 --out /tmp/ui-shots
//
// Options: --features hero|all asserts what the server's feature set shows (the Connect link is
// hidden under hero); --tour also walks /?tour=1 (six shots) when the tour is shipped.
//
// Playwright comes from a scratch node_modules outside this repository (npm i playwright@1.64.0
// there): PLAYWRIGHT_NODE_MODULES names that folder and is required. It drives the system Chrome
// (channel "chrome"). Exit code 1 when any check fails, 2 when the server is not what was asked.

import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

const args = Object.fromEntries(process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith("--") ? [...acc, [a.slice(2), all[i + 1]]] : acc), []));
const BASE = (args.base || "http://127.0.0.1:8121").replace(/\/$/, "");
const MODE = args.mode || "REPLAY";
const CASE = args.case || null;
const OUT = args.out || "/tmp/tephra-ui-check";
const PIN = args.pin || "1234";
const FEATURES = args.features || null;
const TOUR = process.argv.includes("--tour");
if (!process.env.PLAYWRIGHT_NODE_MODULES) {
  console.error("set PLAYWRIGHT_NODE_MODULES to the folder holding a scratch node_modules with playwright");
  process.exit(2);
}
const require = createRequire(path.join(process.env.PLAYWRIGHT_NODE_MODULES, "x.js"));
const { chromium } = require("playwright");

fs.mkdirSync(OUT, { recursive: true });
const failures = [];
const fail = (where, what) => { failures.push(`${where}: ${what}`); console.log(`FAIL ${where}: ${what}`); };
const pass = (where, what) => console.log(`ok ${where}: ${what}`);

// G21: ports are shared between agents, so check what is actually running before trusting a shot.
const state = await (await fetch(`${BASE}/api/state`)).json();
if (state.mode !== MODE) { console.error(`expected mode ${MODE}, the server runs ${state.mode}`); process.exit(2); }
if (CASE && state.replay?.case_id !== CASE) { console.error(`expected case ${CASE}, the server plays ${state.replay?.case_id}`); process.exit(2); }

// The DOM asserts of R17.2, run in the page.
function domChecks() {
  const out = [];
  const vis = (n) => n && !n.hidden && n.offsetParent !== null && n.getBoundingClientRect().width > 0;
  if (document.documentElement.scrollWidth > innerWidth) out.push(`page scrolls sideways: ${document.documentElement.scrollWidth} > ${innerWidth}`);
  const bar = document.querySelector(".cmdbar");
  if (bar && bar.scrollWidth > bar.clientWidth) out.push(`top bar clipped: ${bar.scrollWidth} > ${bar.clientWidth}`);
  if (innerWidth > 600) {
    const boxes = ["#story", "#details", ".map-pills", "#tools", "#timeline", "footer.honesty"].map((s) => [s, document.querySelector(s)]).filter(([, n]) => vis(n));
    for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i][1].getBoundingClientRect(), b = boxes[j][1].getBoundingClientRect();
      if (a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1) out.push(`${boxes[i][0]} overlaps ${boxes[j][0]}`);
    }
  }
  for (const n of document.querySelectorAll("body *")) {
    if (!vis(n)) continue;
    const cs = getComputedStyle(n);
    if (cs.textOverflow === "ellipsis" && n.scrollWidth > n.clientWidth + 1 && !n.closest(".raw__text, .tech")) out.push(`ellipsis truncates ${n.className || n.tagName}`);
    const hasText = [...n.childNodes].some((c) => c.nodeType === 3 && c.textContent.trim());
    if (hasText && parseFloat(cs.fontSize) < 12) out.push(`text under 12 px in ${n.className || n.tagName} (${cs.fontSize})`);
  }
  const d = document.getElementById("disclaimer");
  if (d) { const r = d.getBoundingClientRect(); if (!(r.bottom > 0 && r.top < innerHeight && vis(d))) out.push("the disclaimer is not in the viewport"); }
  // Desk: the assistant chip; at phone width fitHead's is-tight keeps the icon and state word
  // (#budget-chip) and hides the label span (#model-chip).
  const mc = document.getElementById("model-chip");
  const bc = document.getElementById("budget-chip");
  const tight = !!(mc && mc.closest(".budget")?.classList.contains("is-tight"));
  if (mc && !vis(mc) && !(tight && bc && vis(bc))) out.push("the model chip is not visible");
  // REPLAY is said by the page: its title and the "Replay clock" label (the strip is gone).
  if (document.body.dataset.mode === "REPLAY") {
    if (!document.title.startsWith("REPLAY")) out.push(`the title does not start with REPLAY: ${document.title}`);
    if (!document.body.textContent.includes("Replay clock")) out.push("no \"Replay clock\" label on the page");
  }
  const legend = document.getElementById("legend");
  if (legend && legend.querySelector("li") && !vis(legend) && !document.querySelector("#details-sheet[open]")) out.push("the key is not visible");
  return out.slice(0, 12);
}

// The map canvas paints: more than 5 % of a sample of its pixels differ from the background.
// Read inside MapLibre's render callback (the buffer is not preserved between frames).
function canvasPainted() {
  const map = window.__tephra?.map;
  if (!map) return Promise.resolve({ ok: false, why: "no map handle (window.__tephra.map)" });
  return new Promise((resolve) => {
    const sample = () => {
      const canvas = map.getCanvas();
      const gl = canvas.getContext("webgl2") || canvas.getContext("webgl");
      if (!gl) return { ok: false, why: "no WebGL context" };
      const w = canvas.width, h = canvas.height;
      const px = new Uint8Array(w * h * 4);
      gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, px);
      // Every 7th pixel over the whole canvas, against the first pixel's colour (the background).
      let differ = 0, seen = 0;
      for (let i = 0; i < w * h; i += 7) {
        seen++;
        if (Math.abs(px[i * 4] - px[0]) + Math.abs(px[i * 4 + 1] - px[1]) + Math.abs(px[i * 4 + 2] - px[2]) > 24) differ++;
      }
      const share = differ / seen;
      return { ok: share > 0.05, why: `${(share * 100).toFixed(1)} % of sampled pixels differ from the background` };
    };
    const timer = setTimeout(() => resolve({ ok: false, why: "no render frame within 5 s" }), 5000);
    map.once("render", () => { clearTimeout(timer); resolve(sample()); });
    map.triggerRepaint();
  });
}

const browser = await chromium.launch({ channel: "chrome" });

async function wallPage(w, h, query = "") {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  const page = await ctx.newPage();
  const errs = [];
  page.on("pageerror", (e) => errs.push(e.message));
  page.on("console", (m) => { if (m.type() === "error") errs.push(m.text()); });
  await page.goto(`${BASE}/${query}`, { waitUntil: "domcontentloaded" });
  try { await page.waitForSelector('body[data-map-ready="true"]', { timeout: 20000 }); } catch { fail(`wall ${w}x${h}`, "the map never reported ready"); }
  await page.waitForTimeout(1500);
  return { ctx, page, errs };
}

async function shot(page, name, where) {
  const file = path.join(OUT, `${name}.png`);
  await page.screenshot({ path: file });
  for (const p of await page.evaluate(domChecks)) fail(where || name, p);
  return file;
}

const tag = MODE.toLowerCase();
const shots = [];
for (const [w, h] of [[1920, 1080], [1440, 900], [1280, 720], [390, 844]]) {
  const { ctx, page, errs } = await wallPage(w, h);
  shots.push(await shot(page, `wall-${tag}-${w}`));
  for (const e of errs) fail(`wall ${w}`, `page error ${e}`);
  await ctx.close();
}

// The three map-crash repro steps (SPEC 8.3): (i) resize after load, (ii) a volcano row then
// Details within 300 ms, (iii) History then a timeline mark. No console error from MapLibre's
// easing, the map still loaded, the canvas still painted.
{
  const { ctx, page, errs } = await wallPage(1440, 900);
  const mapErrors = () => errs.filter((e) => /_onEaseFrame|already running/.test(e));
  await page.waitForTimeout(1000);
  await page.setViewportSize({ width: 1300, height: 900 });
  await page.waitForTimeout(3000);
  if (mapErrors().length) fail("map resize", `console error ${mapErrors()[0]}`);
  // Offline, the basemap tiles never arrive and map.loaded() stays false; the style loading and
  // a frame drawn are what a crash takes away.
  const mapState = await page.evaluate(() => ({ loaded: window.__tephra?.map?.loaded() === true, style: window.__tephra?.map?.isStyleLoaded() === true }));
  if (!mapState.style) fail("map resize", "map.isStyleLoaded() is not true after the resize"); else pass("map resize", `style loaded; map.loaded() ${mapState.loaded}`);
  const paint = await page.evaluate(canvasPainted);
  if (!paint.ok) fail("map resize", `canvas blank: ${paint.why}`); else pass("map resize", paint.why);
  shots.push(await shot(page, `repro-${tag}-resize`, "map resize"));

  // (ii) the row, then Details 150 ms later (dispatched, not waited for: the point is the speed).
  try {
    let row = page.locator("#volcano-tabs button.vrow", { hasText: "Semeru" }).first();
    if (!(await row.count())) {
      // the case strip folds the volcano list to one row ("+ 3 more"): unfold it first
      const more = page.locator("#volcano-tabs button", { hasText: /\bmore\b/i }).first();
      if (await more.count()) { await more.click(); await page.waitForTimeout(300); row = page.locator("#volcano-tabs button.vrow", { hasText: "Semeru" }).first(); }
    }
    if (await row.count()) {
      await row.click();
      await page.waitForTimeout(150);
      await page.locator("#details-btn").dispatchEvent("click");
      await page.waitForTimeout(1500);
      if (mapErrors().length) fail("row then details", `console error ${mapErrors()[0]}`); else pass("row then details", "no map error");
      shots.push(await shot(page, `repro-${tag}-row-details`, "row then details"));
      await page.keyboard.press("Escape");
      await page.waitForTimeout(300);
    } else {
      fail("row then details", "no Semeru row in the volcano list");
    }
  } catch (e) {
    fail("row then details", e.message.split("\n")[0]);
  }

  // (iii) History, then a timeline mark.
  try {
    if (await page.locator("#details").isHidden()) { await page.click("#details-btn"); await page.waitForTimeout(400); }
    await page.click('#xtabs [data-sec="history"]');
    await page.waitForTimeout(800);
    const mark = page.locator("#timeline .tl__mark").first();
    if (await mark.count()) {
      await mark.dispatchEvent("click");
      await page.waitForTimeout(1500);
      if (mapErrors().length) fail("history mark", `console error ${mapErrors()[0]}`); else pass("history mark", "no map error");
      const paintAfter = await page.evaluate(canvasPainted);
      if (!paintAfter.ok) fail("history mark", `canvas blank: ${paintAfter.why}`);
      shots.push(await shot(page, `repro-${tag}-history-mark`, "history mark"));
    } else {
      fail("history mark", "no timeline mark to click after History opened");
    }
  } catch (e) {
    fail("history mark", e.message.split("\n")[0]);
  }
  await ctx.close();
}

// The stream check (SPEC 8.3): /api/events answers 503 once; the Wall shows the lost banner,
// then reopens the stream and says "Live updates restored." within 10 s.
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  let broken = 0;
  await page.route("**/api/events", async (route) => {
    if (broken === 0) { broken++; await route.fulfill({ status: 503, body: "" }); return; }
    await route.continue();
  });
  await page.goto(`${BASE}/`, { waitUntil: "domcontentloaded" });
  try {
    await page.waitForFunction(() => { const b = document.getElementById("lost-banner"); return b && !b.hidden && b.textContent.trim(); }, null, { timeout: 10000 });
    pass("stream 503", `lost banner: ${await page.locator("#lost-banner").textContent()}`);
  } catch {
    fail("stream 503", "the lost banner never showed after the 503");
  }
  try {
    await page.waitForFunction(() => (document.getElementById("announce")?.textContent || "").includes("Live updates restored."), null, { timeout: 10000 });
    pass("stream 503", "Live updates restored.");
  } catch {
    fail("stream 503", "\"Live updates restored.\" never announced within 10 s");
  }
  await ctx.close();
}

// Details on every section at 1440; Flights and Sources at 1280.
const SECTIONS = ["sources", "disagree", "estimate", "sat", "notices", "flights", "decisions", "recovery", "history", "levels", "trace", "ai", "proof", "runs", "feeds", "layers"];
for (const [w, h, list] of [[1440, 900, SECTIONS], [1280, 720, ["flights", "sources"]]]) {
  const { ctx, page } = await wallPage(w, h);
  await page.click("#details-btn");
  await page.waitForTimeout(500);
  shots.push(await shot(page, `details-${tag}-${w}-index`));
  for (const sec of list) {
    const tab = page.locator(`#xtabs [data-sec="${sec}"]`);
    if (!(await tab.count())) continue; // a hidden feature or a section not shipped yet
    await tab.click();
    await page.waitForTimeout(500);
    shots.push(await shot(page, `details-${tag}-${w}-${sec}`));
    if (sec === "decisions" && w === 1440) {
      // "Why ›" on a draft opens the reasoning chain: four steps (SPEC T22).
      try {
        let why = page.locator("#details .dk-dec__why").first();
        if (!(await why.count())) {
          const summary = page.locator("#decisions details:not([open]) > summary").first();
          if (await summary.count()) { await summary.dispatchEvent("click"); await page.waitForTimeout(400); why = page.locator("#details .dk-dec__why").first(); }
        }
        if (await why.count()) {
          // dispatched, not clicked: the row sits under the drawer's sticky header after the scroll
          await why.dispatchEvent("click");
          await page.waitForTimeout(1200);
          const steps = await page.locator("#details .chain__step").count();
          if (steps === 4) pass("why chain", "four steps"); else fail("why chain", `${steps} .chain__step after Why ›`);
          shots.push(await shot(page, `details-${tag}-${w}-why`));
        } else {
          pass("why chain", "no draft row with Why › in this view");
        }
      } catch (e) {
        fail("why chain", e.message.split("\n")[0]);
      }
    }
    await page.click("#details-back");
    await page.waitForTimeout(300);
  }
  await ctx.close();
}

// Help, About and Policy.
{
  const { ctx, page } = await wallPage(1440, 900);
  for (const [btn, name] of [["#help-btn", "help"], ["#about-btn", "about"], ["#policy-btn", "policy"]]) {
    if (!(await page.isVisible(btn))) continue;
    // the Guide and Policy are pages now (an <a target=_blank>), screenshotted by their own checks
    if (await page.evaluate((sel) => document.querySelector(sel)?.tagName === "A", btn)) continue;
    await page.click(btn);
    await page.waitForTimeout(800);
    shots.push(await shot(page, `dialog-${tag}-${name}`));
    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);
  }
  await ctx.close();
}

// Features (CP-01): under hero the nav has no Connect link; under all it has one.
if (FEATURES) {
  const { ctx, page } = await wallPage(1440, 900);
  const connect = await page.evaluate(() => { const a = document.querySelector('.topnav a[href="/connect"]'); return a ? !a.hidden && a.offsetParent !== null : false; });
  const served = Array.isArray(state.features) ? state.features : [];
  if (FEATURES === "hero" && connect) fail("features hero", "the Connect link is shown");
  if (FEATURES === "all" && !connect) fail("features all", "the Connect link is hidden");
  if (FEATURES === "hero" && served.includes("connect")) fail("features hero", `the server serves ${served.join(",")}`);
  pass(`features ${FEATURES}`, `Connect link ${connect ? "shown" : "hidden"}; server features ${served.join(",") || "(none reported)"}`);
  await ctx.close();
}

// The tour (T23): six beats on /?tour=1, #tour never overlapping #timeline.
if (TOUR) {
  for (const [w, h] of [[1440, 900], [1280, 720], [390, 844]]) {
    const { ctx, page } = await wallPage(w, h, "?tour=1");
    for (let beat = 1; beat <= 6; beat++) {
      await page.waitForTimeout(600);
      const overlap = await page.evaluate(() => {
        const t = document.getElementById("tour"), tl = document.getElementById("timeline");
        if (!t || t.hidden || !tl || tl.hidden) return false;
        const a = t.getBoundingClientRect(), b = tl.getBoundingClientRect();
        return a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1;
      });
      if (overlap) fail(`tour ${w}`, `#tour overlaps #timeline on beat ${beat}`);
      if (w === 1440) shots.push(await shot(page, `tour-${tag}-${beat}`, `tour beat ${beat}`));
      await page.keyboard.press("ArrowRight");
    }
    await ctx.close();
  }
}

// The Desk, signed in, at 390 and 1440 (R10): each tab, and the deep link signed out and in.
for (const [w, h] of [[390, 844], [1440, 900]]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/desk#review/adv_000000000000`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2500);
  shots.push(await shot(page, `desk-${tag}-${w}-deeplink-signed-out`));
  try {
    await page.fill('input[type="password"], input[name="pin"]', PIN);
    const name = await page.$('#login-name, input[autocomplete="username"]');
    if (name) await name.fill("UI check");
    await page.keyboard.press("Enter");
    await page.waitForTimeout(3000);
    shots.push(await shot(page, `desk-${tag}-${w}-deeplink-signed-in`));
    for (const tab of ["queue", "ask", "network", "docs"]) {
      const b = await page.$(`#tabbar [data-tab="${tab}"]`);
      if (!b || !(await b.isVisible())) continue;
      await b.click();
      await page.waitForTimeout(1200);
      shots.push(await shot(page, `desk-${tag}-${w}-${tab}`));
    }
  } catch (e) {
    fail(`desk ${w}`, `could not sign in: ${e.message}`);
  }
  await ctx.close();
}

// Cold visitor (R0.3, R17.2): a fresh profile at 1440x900 sees the story with flights, the areas
// and the key, with no drawer open.
{
  const { ctx, page } = await wallPage(1440, 900);
  shots.push(await shot(page, `cold-visitor-${tag}`));
  const c = await page.evaluate(() => ({
    flights: Number(document.querySelector("#kpi-exposed")?.textContent) || 0,
    story: document.getElementById("headline")?.textContent || "",
    drawer: !document.getElementById("details").hidden,
    key: document.querySelectorAll("#legend li").length,
  }));
  if (MODE === "REPLAY" && c.flights <= 0) fail("cold visitor", "no flight count above 0");
  if (MODE === "REPLAY" && !/flights? (of RFA|in or heading)/.test(c.story)) fail("cold visitor", "the story does not name the RFA flights");
  if (c.drawer) fail("cold visitor", "Details is open on a cold start");
  if (!c.key) fail("cold visitor", "the key is empty");
  await ctx.close();
}

await browser.close();
console.log(JSON.stringify({ base: BASE, mode: MODE, case: state.replay?.case_id || null, shots: shots.length, out: OUT, failures }, null, 2));
process.exit(failures.length ? 1 : 0);
