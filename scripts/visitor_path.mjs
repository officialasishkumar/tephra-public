// The visitor's path end to end (SPEC 8.4), against the stub replay. Not part of CI.
//
//   TEPHRA_PORT=8121 TEPHRA_LLM=stub TEPHRA_LOCAL_SCHEDULER=1 TEPHRA_DESK_PIN=1234 \
//   TEPHRA_MODE=REPLAY TEPHRA_REPLAY_CASE=anak-krakatau-20260905 \
//   TEPHRA_REPLAY_START=2026-09-05T10:25:00Z TEPHRA_REPLAY_END=2026-09-05T19:30:00Z \
//   TEPHRA_FEATURES=all TEPHRA_VISITOR_ACCESS=replay uv run tephra
//   PLAYWRIGHT_NODE_MODULES=... node scripts/visitor_path.mjs --base http://127.0.0.1:8121 --out /tmp/visitor-shots
//
// Steps: "/demo?intro=0" (the demo, its welcome dialog skipped) has no console error in 5 s, a
// title starting with REPLAY, the "Replay clock" label,
// a painted map canvas and survives a 1440 -> 1300 resize; Details > Runs on, Track record and
// How TEPHRA decided render without "undefined" or "NaN"; "/desk" -> "Enter as a visitor" -> the
// review sheet with the hold button -> approve (hold) or reject (--decision reject, or when the
// draft cannot be approved) -> the receipt; GET /api/audit?limit=1 shows seq and a visitor actor;
// POST /api/mode as the visitor answers 403; screenshots of "/demo" and "/desk" at 1440x900, 1280x720
// and 390x844 into --out. --cap also makes decisions until the visitor cap answers 429.
// Exit 1 on any failure, 2 when the server is not a REPLAY with visitor access.

import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

const args = Object.fromEntries(process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith("--") && !["--cap"].includes(a) ? [...acc, [a.slice(2), all[i + 1]]] : acc), []));
const BASE = (args.base || "http://127.0.0.1:8121").replace(/\/$/, "");
const OUT = args.out || "/tmp/tephra-visitor-path";
const DECISION = args.decision || "approve";
const NAME = args.name || "Mira";
const CAP = process.argv.includes("--cap");
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

const state = await (await fetch(`${BASE}/api/state`)).json();
if (state.mode !== "REPLAY") { console.error(`the server runs ${state.mode}, not REPLAY`); process.exit(2); }
if (state.visitor_access !== true) { console.error("the server has no visitor access (TEPHRA_VISITOR_ACCESS=replay)"); process.exit(2); }

// The map canvas paints (read inside MapLibre's render callback: the buffer is not preserved).
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
const SIZES = [[1440, 900], [1280, 720], [390, 844]];

// --- the Wall -------------------------------------------------------------------------------
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const errs = [];
  page.on("pageerror", (e) => errs.push(e.message));
  page.on("console", (m) => { if (m.type() === "error") errs.push(m.text()); });
  await page.goto(`${BASE}/demo?intro=0`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(5000);
  if (errs.length) fail("wall", `console error in the first 5 s: ${errs[0]}`); else pass("wall", "no console error in 5 s");
  const title = await page.title();
  if (!title.startsWith("REPLAY")) fail("wall", `title does not start with REPLAY: ${title}`); else pass("wall", `title ${title}`);
  const clock = await page.evaluate(() => document.body.textContent.includes("Replay clock"));
  if (!clock) fail("wall", "no \"Replay clock\" label"); else pass("wall", "Replay clock label present");
  const paint = await page.evaluate(canvasPainted);
  if (!paint.ok) fail("wall", `canvas blank: ${paint.why}`); else pass("wall", `canvas paints (${paint.why})`);
  await page.setViewportSize({ width: 1300, height: 900 });
  await page.waitForTimeout(3000);
  const mapErr = errs.find((e) => /_onEaseFrame|already running/.test(e));
  if (mapErr) fail("wall resize", `console error ${mapErr}`); else pass("wall resize", "no map error after 1440 -> 1300");
  const paintAfter = await page.evaluate(canvasPainted);
  if (!paintAfter.ok) fail("wall resize", `canvas blank: ${paintAfter.why}`);

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.click("#details-btn");
  await page.waitForTimeout(500);
  for (const [sec, label] of [["runs", "Runs on"], ["proof", "Track record"], ["trace", "How TEPHRA decided"]]) {
    const tab = page.locator(`#xtabs [data-sec="${sec}"]`);
    if (!(await tab.count())) { fail(`details ${label}`, "no index row"); continue; }
    await tab.click();
    await page.waitForTimeout(800);
    const text = await page.locator("#details").innerText();
    if (/\bundefined\b|\bNaN\b/.test(text)) fail(`details ${label}`, "renders undefined or NaN"); else pass(`details ${label}`, `${text.length} chars, clean`);
    await page.screenshot({ path: path.join(OUT, `details-${sec}-1440.png`) });
    await page.click("#details-back");
    await page.waitForTimeout(300);
  }
  await page.click("#assist-tab");
  for (const [w, h] of SIZES) {
    await page.setViewportSize({ width: w, height: h });
    await page.waitForTimeout(1200);
    await page.screenshot({ path: path.join(OUT, `wall-${w}x${h}.png`) });
  }
  await ctx.close();
}

// --- the Desk -------------------------------------------------------------------------------
async function hold(page, locator) {
  const box = await locator.boundingBox();
  if (!box) throw new Error("the hold button has no box");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.waitForTimeout(1500);
  await page.mouse.up();
}

async function decide(page, which) {
  if (which === "reject") {
    await page.locator("#sheet button", { hasText: "Reject" }).first().click();
    await page.waitForTimeout(400);
    const reason = page.locator("#sheet textarea, #sheet input[type=\"text\"]").first();
    if (await reason.count()) await reason.fill("Visitor path check: rejected on purpose.");
    await page.locator("#sheet button[data-decide=\"reject\"]").click();
  } else {
    await hold(page, page.locator("#sheet button.approve").first());
  }
  await page.waitForTimeout(1500);
}

async function visitorContext(w, h) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/desk`, { waitUntil: "domcontentloaded" });
  const enter = page.getByRole("button", { name: /Enter as a visitor/ });
  await enter.waitFor({ state: "visible", timeout: 10000 });
  const name = page.getByLabel(/Your name/).first();
  if (await name.count()) await name.fill(NAME);
  await enter.click();
  return { ctx, page };
}

{
  let ctx, page;
  try {
    ({ ctx, page } = await visitorContext(390, 844));
    pass("desk", "Enter as a visitor");
  } catch (e) {
    fail("desk", `no visitor card: ${e.message}`);
  }
  if (page) {
    await page.screenshot({ path: path.join(OUT, "desk-entered-390x844.png") });
    let decided = DECISION;
    try {
      await page.waitForSelector("#sheet:not([hidden])", { timeout: 10000 });
      await page.waitForTimeout(1000); // the sheet settles before the hold
      const holdBtn = page.locator("#sheet button.approve").first();
      const blocked = await page.locator("#sheet .hint-early", { hasText: /HYPOTHESIS|cannot be approved|Reject it/ }).count();
      if (!(await holdBtn.count()) && decided === "approve") {
        fail("desk review", "the review sheet has no hold button");
      } else {
        pass("desk review", `review sheet open${blocked ? ", draft cannot be approved: rejecting" : ""}`);
        if (blocked) decided = "reject";
        await page.screenshot({ path: path.join(OUT, "desk-review-390x844.png") });
        await decide(page, decided);
        const readReceipt = () => {
          for (const id of ["sheet-receipts", "q-receipt"]) { const t = document.getElementById(id)?.textContent?.trim(); if (t) return t; }
          return [...document.querySelectorAll("[class*=receipt]")].map((n) => n.textContent.trim()).find(Boolean) || "";
        };
        await page.waitForFunction(readReceipt, null, { timeout: 8000 }).catch(() => {});
        const receipt = await page.evaluate(readReceipt);
        if (!receipt.trim()) fail("desk receipt", "no receipt line after the decision"); else pass("desk receipt", receipt.trim().split("\n")[0]);
        await page.screenshot({ path: path.join(OUT, "desk-receipt-390x844.png") });
      }
    } catch (e) {
      fail("desk review", `the review sheet did not open: ${e.message}`);
    }

    const audit = await page.evaluate(async () => {
      const r = await fetch("/api/audit?limit=1", { headers: { Accept: "application/json" } });
      return { status: r.status, body: await r.json().catch(() => null) };
    });
    const entry = audit.body?.entries?.[0];
    if (!entry || typeof entry.seq !== "number") fail("audit", `no seq in ${JSON.stringify(audit.body).slice(0, 200)}`);
    else if (!String(entry.actor || "").startsWith("visitor:")) fail("audit", `newest actor is ${entry.actor}, not visitor:`);
    else pass("audit", `seq ${entry.seq} by ${entry.actor}`);

    const mode = await page.evaluate(async () => {
      const r = await fetch("/api/mode", { method: "POST", headers: { "Content-Type": "application/json", "X-Tephra-Desk": "1" }, body: JSON.stringify({ mode: "LIVE" }) });
      return r.status;
    });
    if (mode !== 403) fail("visitor mode", `POST /api/mode answered ${mode}, not 403`); else pass("visitor mode", "POST /api/mode -> 403");

    if (CAP) {
      let status = 0, n = 0;
      while (n < 60 && status !== 429) {
        const next = page.locator("#sheet button.approve").first();
        if (!(await next.count())) break;
        await hold(page, next);
        await page.waitForTimeout(800);
        n++;
        status = await page.evaluate(() => window.__tephraLastStatus || 0);
      }
      const capped = await page.locator("#sheet", { hasText: /429|limit|cap/i }).count();
      if (!capped && status !== 429) fail("visitor cap", `no 429 after ${n} further decisions`); else pass("visitor cap", `cap reached after ${n} further decisions`);
    }
    await ctx.close();
  }
}

for (const [w, h] of SIZES) {
  if (w === 390) continue; // already shot above
  try {
    const { ctx, page } = await visitorContext(w, h);
    await page.waitForTimeout(2500);
    await page.screenshot({ path: path.join(OUT, `desk-${w}x${h}.png`) });
    await ctx.close();
  } catch (e) {
    fail(`desk ${w}`, e.message);
  }
}

await browser.close();
console.log(JSON.stringify({ base: BASE, out: OUT, failures }, null, 2));
process.exit(failures.length ? 1 : 0);
