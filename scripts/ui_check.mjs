// UI screenshot and DOM pass for the redesign (docs/UI-REDESIGN.md R17.2). Not part of CI.
//
// Run against a local TEPHRA (stub model) in each mode, for example:
//   TEPHRA_PORT=8121 TEPHRA_LLM=stub TEPHRA_LOCAL_SCHEDULER=1 TEPHRA_DESK_PIN=1234 \
//   TEPHRA_MODE=REPLAY TEPHRA_REPLAY_CASE=anak-krakatau-20260905 \
//   TEPHRA_REPLAY_START=2026-09-05T10:30:00Z TEPHRA_REPLAY_END=2026-09-05T19:30:00Z uv run tephra
//   node scripts/ui_check.mjs --base http://127.0.0.1:8121 --mode REPLAY --case anak-krakatau-20260905 --out /tmp/ui-shots
//
// Playwright comes from a scratch node_modules (npm i playwright@1.64.0 there), never from this
// repository: set PLAYWRIGHT_NODE_MODULES to its folder (default <a scratch node_modules>).
// It drives the system Chrome (channel "chrome"). Exit code 1 when any check fails.

import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

const args = Object.fromEntries(process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith("--") ? [...acc, [a.slice(2), all[i + 1]]] : acc), []));
const BASE = (args.base || "http://127.0.0.1:8121").replace(/\/$/, "");
const MODE = args.mode || "REPLAY";
const CASE = args.case || null;
const OUT = args.out || "/tmp/tephra-ui-check";
const PIN = args.pin || "1234";
const require = createRequire(path.join(process.env.PLAYWRIGHT_NODE_MODULES || "<a scratch node_modules>", "x.js"));
const { chromium } = require("playwright");

fs.mkdirSync(OUT, { recursive: true });
const failures = [];
const fail = (where, what) => { failures.push(`${where}: ${what}`); console.log(`FAIL ${where}: ${what}`); };

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
  const mc = document.getElementById("model-chip");
  if (mc && !vis(mc)) out.push("the model chip is not visible");
  if (document.body.dataset.mode === "REPLAY" && !vis(document.getElementById("replay-banner"))) out.push("REPLAY band not visible");
  const legend = document.getElementById("legend");
  if (legend && legend.querySelector("li") && !vis(legend) && !document.querySelector("#details-sheet[open]")) out.push("the key is not visible");
  return out.slice(0, 12);
}

const browser = await chromium.launch({ channel: "chrome" });

async function wallPage(w, h, query = "") {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  const page = await ctx.newPage();
  const errs = [];
  page.on("pageerror", (e) => errs.push(e.message));
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

// Details on every section at 1440; Flights and Sources at 1280.
const SECTIONS = ["sources", "disagree", "estimate", "sat", "notices", "flights", "decisions", "recovery", "history", "levels", "trace", "ai", "proof", "feeds", "layers"];
for (const [w, h, list] of [[1440, 900, SECTIONS], [1280, 720, ["flights", "sources"]]]) {
  const { ctx, page } = await wallPage(w, h);
  await page.click("#details-btn");
  await page.waitForTimeout(500);
  shots.push(await shot(page, `details-${tag}-${w}-index`));
  for (const sec of list) {
    await page.click(`#xtabs [data-sec="${sec}"]`);
    await page.waitForTimeout(500);
    shots.push(await shot(page, `details-${tag}-${w}-${sec}`));
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
    await page.click(btn);
    await page.waitForTimeout(800);
    shots.push(await shot(page, `dialog-${tag}-${name}`));
    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);
  }
  await ctx.close();
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
    const name = await page.$('input[name="name"], input[autocomplete="name"]');
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

// Cold judge (R0.3, R17.2): a fresh profile at 1440x900 sees the story with flights, the areas
// and the key, with no drawer open.
{
  const { ctx, page } = await wallPage(1440, 900);
  shots.push(await shot(page, `cold-judge-${tag}`));
  const c = await page.evaluate(() => ({
    flights: Number(document.querySelector("#kpi-exposed")?.textContent) || 0,
    story: document.getElementById("headline")?.textContent || "",
    drawer: !document.getElementById("details").hidden,
    key: document.querySelectorAll("#legend li").length,
  }));
  if (MODE === "REPLAY" && c.flights <= 0) fail("cold judge", "no flight count above 0");
  if (MODE === "REPLAY" && !/flights? of RFA/.test(c.story)) fail("cold judge", "the story does not name the RFA flights");
  if (c.drawer) fail("cold judge", "Details is open on a cold start");
  if (!c.key) fail("cold judge", "the key is empty");
  await ctx.close();
}

await browser.close();
console.log(JSON.stringify({ base: BASE, mode: MODE, case: state.replay?.case_id || null, shots: shots.length, out: OUT, failures }, null, 2));
process.exit(failures.length ? 1 : 0);
