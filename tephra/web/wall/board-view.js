// "TEPHRA Assistant at work" (docs/UI-DESIGN.md 7.21): the flow board, a full overlay (the modal
// <dialog id="board">) opened from the assistant chip, the story, Details › TEPHRA Assistant, A or
// /#ai-at-work. A dark map of the region with the snapshot's real ash areas, volcanoes, airports and
// aircraft, a beacon where each feed comes from, and one glass panel, "Inside TEPHRA": Code checks,
// the Coordinator, the model gate with its waiting jobs, the six skills and "You decide". Work moves
// only for real records (flowModel in board.js): a trace step that arrives on the stream animates at
// once (push), and the player plays back the latest steps the Wall holds, scrubbable. Every string
// goes in through el() (textContent); dynamic colours and positions are set through the CSSOM.
// Three canvases: the map, redrawn only on resize or a new snapshot; the rails (the panel's spine, the
// gate and its waiting jobs), redrawn on a resize, a scroll or a change of state; and the effects,
// cleared and drawn per frame while something moves. The loop stops when nothing does.

import { $, el, icon, fl } from "./util.js";
import { flowAt, foldRows, readEvent, stepEvents, hmsOf as hms, STAGGER_MS, TOOL_SKILLS } from "./board.js";

const ARROWS = ["→", "↘", "↓", "↙", "←", "↖", "↑", "↗"];
// Where each feed comes from: the office or source that issues it (lon, lat). The SIGMET beacon sits
// on the SIGMETs in force when there are any; METAR at the airports; winds on the grid; ADS-B at
// every aircraft.
const SRC = {
  sigmet: { name: "VA SIGMET", sub: "areas in force", at: null },
  vona: { name: "VONA", sub: "MAGMA, Bandung", at: [107.63, -6.92] },
  jma_volcano: { name: "JMA notices", sub: "Tokyo", at: [139.76, 35.69] },
  vaac_darwin: { name: "Darwin VAAC", sub: "VAA", at: [130.84, -12.46] },
  vaac_tokyo: { name: "Tokyo VAAC", sub: "VAA", at: [139.69, 35.69] },
  frames: { name: "Himawari", sub: "satellite pictures", at: [140.7, 0] },
  winds: { name: "Winds aloft", sub: "Open-Meteo grid", at: null },
};
const FEED_TITLE = { sigmet: "VA SIGMET (AWC)", vona: "VONA (MAGMA)", jma_volcano: "JMA volcano notices", vaac_darwin: "VAA Darwin", vaac_tokyo: "VAA Tokyo", frames: "Satellite pictures", winds: "Winds (Open-Meteo)" };
const SKILL_ROWS = ["plume", "sat", "planner", "drafter", "recovery", "sra"];
const TOKEN_SPEED = 190; // px per second down the spine
const MAX_P = 160, MAX_TR = 90, MAX_TK = 40;
const SAY_EVERY_MS = 10000;

const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
const easeIO = (u) => (u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2);
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
// a token's hex colour at an alpha, for the canvases (tokens.css holds the colours)
function rgba(hex, a) {
  const h = String(hex).trim().replace("#", "");
  const v = h.length === 3 ? h.split("").map((c) => c + c).join("") : h.slice(0, 6);
  const n = parseInt(v, 16);
  if (!Number.isFinite(n)) return hex;
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}
// write only what changed: the board updates every 15 s and on each state event
function setText(n, v) { const t = String(v ?? ""); if (n.textContent !== t) n.textContent = t; }
function setAttr(n, k, v) { if (v == null) { if (n.hasAttribute(k)) n.removeAttribute(k); } else if (n.getAttribute(k) !== String(v)) n.setAttribute(k, String(v)); }

function kmBetween(a, b) {
  const r = Math.PI / 180;
  const h = Math.sin(((b[1] - a[1]) * r) / 2) ** 2 + Math.cos(a[1] * r) * Math.cos(b[1] * r) * Math.sin(((b[0] - a[0]) * r) / 2) ** 2;
  return 12742 * Math.asin(Math.sqrt(h));
}

// Douglas–Peucker on a ring of [lon, lat] (the land file is detailed; the board needs its shape).
function simplify(pts, tol) {
  if (pts.length < 3) return pts;
  const a = pts[0], b = pts[pts.length - 1];
  const dx = b[0] - a[0], dy = b[1] - a[1], n = Math.hypot(dx, dy);
  let imax = 0, dmax = 0;
  for (let i = 1; i < pts.length - 1; i++) {
    const p = pts[i];
    // a closed ring starts and ends on one point: measure from it
    const d = n > 1e-9 ? Math.abs(dy * p[0] - dx * p[1] + b[0] * a[1] - b[1] * a[0]) / n : Math.hypot(p[0] - a[0], p[1] - a[1]);
    if (d > dmax) { imax = i; dmax = d; }
  }
  if (dmax <= tol) return [a, b];
  return [...simplify(pts.slice(0, imax + 1), tol).slice(0, -1), ...simplify(pts.slice(imax), tol)];
}

let landRings = null;
let landLoading = null;
function loadLand() {
  if (landRings || landLoading) return landLoading;
  landLoading = fetch("/static/data/land_apac.geojson").then((r) => (r.ok ? r.json() : null)).then((g) => {
    const out = [];
    for (const f of g?.features || []) {
      const geom = f.geometry;
      const polys = geom?.type === "MultiPolygon" ? geom.coordinates : geom?.type === "Polygon" ? [geom.coordinates] : [];
      for (const poly of polys) {
        const ring = poly[0];
        if (!ring || ring.length < 4) continue;
        const s = simplify(ring, 0.025);
        if (s.length >= 4) out.push(s);
      }
    }
    landRings = out;
    return out;
  }).catch(() => { landRings = []; return landRings; });
  return landLoading;
}

// ------------------------------------------------------------------ the board

export function mountFlow(dialog) {
  const body = $("board-body");
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  const RM = () => reduced.matches;
  const css = getComputedStyle(document.documentElement);
  const tok = (name, fb) => (css.getPropertyValue(name) || "").trim() || fb;
  const C = {
    official: tok("--c-official", "#ff3d8b"), officialText: tok("--c-official-text", "#ff9cc4"), observer: tok("--c-observer", "#38bdf8"),
    weather: tok("--c-info", "#9db4cc"), aircraft: tok("--c-aircraft", "#aab4be"), satellite: tok("--c-info", "#9db4cc"),
    job: tok("--c-text-1", "#eaf1f7"), must: tok("--c-caution", "#ffe566"), tephra: tok("--c-tephra", "#ffb000"), info: tok("--c-info", "#9db4cc"),
    text2: tok("--c-text-2", "#b6c3d0"), text3: tok("--c-text-3", "#93a3b5"), line2: tok("--c-line-2", "#2b3a4a"), muted: tok("--c-text-3", "#93a3b5"),
    bg: tok("--c-bg", "#05080c"), s1: tok("--c-surface-1", "#0a1017"), s2: tok("--c-surface-2", "#0f1720"),
  };
  const colOf = (tone) => C[tone] || C.text3;

  // ---------------------------------------------------------------- DOM, built once
  const mapC = el("canvas", { class: "flow-map__c", "aria-hidden": "true" });
  const labels = el("div", { class: "flow-labels", "aria-hidden": "true" });
  const mapWrap = el("div", { class: "flow-map", "aria-hidden": "true" }, mapC, labels);

  const markUse = icon("ta-waiting", "flow-head__mark");
  const status = el("span", { id: "board-status", class: "flow-head__status", text: "· connecting" });
  // the lede, then "Why ›" while the assistant is paused or has trouble: the cause is said once, at
  // Details › TEPHRA Assistant, one tap from here (docs/UI-AI-QUIET.md 8.6)
  const ledeText = el("span", { text: "Connecting to TEPHRA…" });
  const whyBtn = el("button", { type: "button", class: "flow-link flow-why", hidden: true, "aria-label": "Why: open Details › TEPHRA Assistant", dataset: { act: "board-details", sec: "ai", focus: "board-why" }, text: "Why ›" });
  const lede = el("p", { id: "board-lede", class: "flow-head__sub" }, ledeText, " ", whyBtn);
  const btnReal = el("button", { type: "button", class: "flow-seg__btn", "aria-pressed": "true", dataset: { flowmode: "real" }, text: "Real now" });
  const btnEx = el("button", { type: "button", class: "flow-seg__btn", "aria-pressed": "false", dataset: { flowmode: "example" }, text: "Example: working normally" });
  const exFlag = el("p", { class: "flow-exflag", hidden: true, text: "Example · illustrative, not recorded. The assistant steps it shows did not happen." });
  const helpBtn = el("button", { type: "button", class: "flow-iconbtn", "aria-label": "How this moves", title: "How this moves", dataset: { flowsheet: "help" }, text: "?" });
  const closeBtn = el("button", { type: "button", class: "flow-iconbtn flow-close", "aria-label": "Close TEPHRA Assistant at work", dataset: { act: "board-close" } }, icon("i-x"));
  const head = el("header", { class: "flow-head" },
    el("div", { class: "flow-head__brand" }, markUse,
      el("div", { class: "flow-head__titles" },
        el("h2", { id: "board-title", class: "flow-head__title", tabindex: "-1" }, el("span", { text: "TEPHRA Assistant " }), status),
        lede)),
    el("div", { class: "flow-head__right" },
      el("div", { class: "flow-head__col" }, el("div", { class: "flow-seg", role: "group", "aria-label": "What to show" }, btnReal, btnEx), exFlag),
      helpBtn, closeBtn));

  // the panel: the pipeline as a drawn spine
  const node = (cls, a, kid = null) => el("span", { class: `flow-node ${cls}`, dataset: { a } }, kid);
  const cFeeds = el("b", { text: "0" }), cFlights = el("b", { text: "0" });
  const wFeeds = el("span", { text: " feed reads · " }), wFlights = el("span", { text: " flight alerts" });
  const coordMark = icon("ta-waiting", "flow-node__mark");
  const coordMeta = el("span", { class: "flow-row__meta" });
  const coordRight = el("span", { class: "flow-row__right" });
  const coordBtn = el("button", { type: "button", class: "flow-row__btn", dataset: { flowskill: "duty" } }, el("span", { class: "flow-row__name", text: "Coordinator" }), coordMeta);
  const coordRow = el("div", { class: "flow-row flow-row--coord" }, node("flow-node--coord", "coord", coordMark), coordBtn, coordRight);
  const gap2 = el("div", { class: "flow-gap2" });
  const gateBar = el("span", { class: "flow-gatebar", dataset: { a: "gate" } });
  const gateName = el("span", { class: "flow-row__name" });
  const gateMeta = el("span", { class: "flow-row__meta" });
  const gateRow = el("div", { class: "flow-row flow-row--gate" }, el("span"), gateBar, el("span", { class: "flow-row__txt" }, gateName, gateMeta));
  const skillList = el("ul", { class: "flow-skills", "aria-label": "Skills" });
  const skillEls = {};
  for (const id of SKILL_ROWS) {
    const dot = el("span", { class: "flow-dot", dataset: { a: `sk-${id}` } });
    const name = el("span", { class: "flow-skill__name" });
    const state = el("span", { class: "flow-skill__state" });
    const btn = el("button", { type: "button", class: "flow-skill__btn", dataset: { flowskill: id } }, name, state);
    const li = el("li", { class: "flow-skill" }, el("span"), dot, btn);
    skillEls[id] = { li, dot, name, state, btn };
    skillList.append(li);
  }
  const onreqDot = el("span", { class: "flow-dot flow-dot--small", dataset: { a: "sk-onreq" } });
  skillList.append(el("li", { class: "flow-skill flow-skill--onreq" }, el("span"), onreqDot,
    el("span", { class: "flow-skill__name", text: "When you ask: Notice reader · Ask · Message drafter · Handover drafter" })));
  const heroN = el("span", { class: "flow-hero__n", text: "–" });
  const heroW = el("span", { class: "flow-hero__w" });
  const who = el("p", { class: "flow-who" });
  const runsCap = el("span");
  const runsBars = el("div", { class: "flow-runs__bars", "aria-hidden": "true" });
  const runsBox = el("div", { class: "flow-runs" }, el("p", { class: "flow-runs__cap" }, el("span", { text: "Must-do passed to you, each run" }), runsCap), runsBars);
  const facts = el("ul", { class: "flow-facts" });
  const factsCap = el("p", { class: "flow-facts__cap", text: "At the Desk now" });
  const youHead = el("h3", { id: "flow-you", class: "flow-you__eyebrow", text: "You decide" });
  const decide = el("section", { class: "flow-you", "aria-labelledby": "flow-you" },
    el("div", { class: "flow-you__head" }, node("flow-node--you", "you"), youHead),
    el("p", { class: "flow-hero" }, heroN, heroW), who, runsBox, factsCap, facts,
    el("a", { class: "flow-cta", href: "/desk", target: "_blank", rel: "noopener", dataset: { focus: "board-desk" } }, el("span", { text: "Open the Desk" }), el("span", { "aria-hidden": "true", text: "→" })),
    el("button", { type: "button", class: "flow-link", dataset: { act: "board-details", sec: "ai", focus: "board-ai-home" }, text: "Details › TEPHRA Assistant ›" }));
  const panel = el("aside", { class: "flow-panel", "aria-label": "Inside TEPHRA" },
    el("p", { class: "flow-eyebrow", text: "Inside TEPHRA" }),
    el("div", { class: "flow-row flow-row--code" }, node("flow-node--code", "code"),
      el("span", { class: "flow-row__txt" }, el("span", { class: "flow-row__name" }, "Code checks ", el("span", { class: "flow-tag", text: "no AI" })),
        el("span", { class: "flow-row__meta flow-ctr" }, cFeeds, wFeeds, cFlights, wFlights))),
    el("div", { class: "flow-gap1" }),
    coordRow, gap2, gateRow, skillList, decide);

  // the dock: the log, the legend, the player
  const log = el("ol", { class: "flow-log", "aria-label": "Newest steps" });
  const legend = el("p", { class: "flow-legend" });
  const allSteps = el("button", { type: "button", class: "flow-link", dataset: { flowsheet: "steps" }, text: "Every step in plain words" });
  const play = el("button", { type: "button", class: "flow-play", "aria-label": "Play back the latest steps" }, icon("i-play"));
  const chipWord = el("span", { class: "flow-chip__word" });
  const chipText = el("span", { class: "flow-chip__text" });
  // the labelled fast-forward over a stretch with no step: said in the player itself, never over
  // other text (aria-hidden: the track's value says where the playhead is)
  const skip = el("span", { class: "flow-skip", "aria-hidden": "true" },
    el("span", { class: "flow-skip__long", text: "Quiet stretch: nothing happened here, skipping ahead" }),
    el("span", { class: "flow-skip__short", text: "Quiet stretch, skipping ahead" }));
  const speedBtn = el("button", { type: "button", class: "flow-speed", "aria-label": "Playback speed 8 times", text: "8×" });
  const trackC = el("canvas", { "aria-hidden": "true" });
  const track = el("div", { class: "flow-track", role: "slider", tabindex: "0", "aria-label": "Playback position", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": "100" }, trackC);
  const tnow = el("span", { class: "flow-tnow", text: "--:--:--" });
  const mchip = el("button", { type: "button", class: "flow-mchip" });
  const player = el("div", { class: "flow-player" }, play, el("p", { class: "flow-chip" }, chipWord, chipText, skip, speedBtn), track, tnow, mchip);
  const dock = el("div", { class: "flow-dock" }, log, el("div", { class: "flow-logrow" }, legend, allSteps), player);
  // not a live region of its own: the board's one live region says it (spec 8)
  const staleNote = el("p", { class: "flow-stale", hidden: true, text: "Live updates paused, reconnecting. The board shows the last steps it had." });

  const stage = el("div", { class: "flow-stage" }, mapWrap, head, staleNote, panel, dock);
  body.replaceChildren(stage);
  const railC = el("canvas", { class: "flow-rails", "aria-hidden": "true" });
  const fxC = el("canvas", { class: "flow-fx", "aria-hidden": "true" });
  dialog.append(railC, fxC);
  const live = $("board-live");

  // the text equivalent: what each motion stands for, and every step in words
  const sheetH = el("h2", { id: "flow-sheet-h", class: "flow-sheet__h", tabindex: "-1" });
  const sheetBody = el("div", { class: "flow-sheet__body" });
  const sheet = el("dialog", { class: "flow-sheet", "aria-labelledby": "flow-sheet-h" },
    el("div", { class: "flow-sheet__in" },
      el("button", { type: "button", class: "flow-iconbtn flow-sheet__x", "aria-label": "Close", dataset: { flowsheet: "close" } }, icon("i-x")),
      sheetH, sheetBody));
  dialog.append(sheet);

  // ---------------------------------------------------------------- state
  let M = null; // the newest flowModel
  let details = null; // the newest boardModel (a skill's details)
  let mode = "real"; // real | example
  let events = [];
  let T0 = NaN, T1 = NaN;
  let simT = NaN;
  let following = true; // at the live edge: new steps animate as they arrive
  let playing = false;
  let speed = 8;
  let nextIdx = 0;
  let gen = 0;
  let stale = false;
  let isOpen = false;
  const fired = new Set(); // event ids shown (animated or applied) at the live edge
  let pendingLand = new Set(); // refused events whose tokens are still on their way
  let liveKey = null;
  let gateOpenUntil = 0; // a recorded hand-out through a gate that is closed now: open while it passes
  // Example only: the drafts of the newest example run that have reached You decide
  const exState = { run: null, runAt: -Infinity, drafts: 0 };

  // ---------------------------------------------------------------- geometry
  const DPR = Math.min(2, window.devicePixelRatio || 1);
  const mctx = mapC.getContext("2d");
  const fx = fxC.getContext("2d");
  const rctx = railC.getContext("2d");
  const tctx = trackC.getContext("2d");
  let VW = 0, VH = 0, phone = false;
  let proj = null; // lon,lat -> map canvas px
  let mapOff = [0, 0]; // map canvas origin in fx coordinates
  let A = {}; // anchors in fx coordinates
  let BE = {}; // beacon positions in map px: { id: { x, y, on, kind } }
  let mapKey = "";

  function dialogRect() { return dialog.getBoundingClientRect(); }

  function layout() {
    const d = dialogRect();
    VW = d.width; VH = d.height; phone = VW <= 760;
    fxC.width = railC.width = Math.round(VW * DPR); fxC.height = railC.height = Math.round(VH * DPR);
    const r = mapWrap.getBoundingClientRect();
    mapC.width = Math.round(r.width * DPR); mapC.height = Math.round(r.height * DPR);
    mapKey = ""; labelKey = "";
    drawMap();
    fitGate();
    drawTrack();
  }

  // The jobs waiting at a closed gate stack upward from it; the gap above the gate grows so the stack
  // (and a token knocking on top of it) never reaches the Coordinator's words.
  let gapFor = -1;
  function fitGate() {
    const k = M && !M.gate.open ? Math.min(6, M.queue.length) : 0;
    if (k !== gapFor) { gapFor = k; gap2.style.height = ""; }
    measure();
    if (!A.gate || !k) { drawRails(); return; }
    const d = dialogRect();
    const coordBottom = coordRow.getBoundingClientRect().bottom - d.top;
    const top = A.gate.y - 13 - k * 11 - 8;
    if (top < coordBottom + 4) {
      gap2.style.height = `${gap2.getBoundingClientRect().height + (coordBottom + 4 - top)}px`;
      measure();
    }
    drawRails();
  }

  // the part of the map that the head, the panel and the dock leave free
  function freeView(r) {
    if (phone) return { x: 8, y: 8, w: r.width - 16, h: r.height - 16 };
    const p = panel.getBoundingClientRect(), dk = dock.getBoundingClientRect(), h = head.getBoundingClientRect();
    return { x: 24, y: h.bottom - r.top + 10, w: Math.max(200, p.left - r.left - 48), h: Math.max(160, dk.top - h.bottom - 20) };
  }

  function measure() {
    const d = dialogRect();
    const mr = mapWrap.getBoundingClientRect();
    mapOff = [mr.left - d.left, mr.top - d.top];
    A = {};
    for (const n of stage.querySelectorAll("[data-a]")) {
      const r = n.getBoundingClientRect();
      A[n.dataset.a] = { x: r.left - d.left + r.width / 2, y: r.top - d.top + r.height / 2 };
    }
    if (!A.code || !A.you || !A.gate) return;
    const sp = A.code.x, rail = A.gate.x;
    A.spine = sp; A.rail = rail;
    A.railTop = { x: rail, y: A.coord.y + 26 };
    const lastSkill = A["sk-sra"] || A.gate;
    A.railEnd = { x: rail, y: lastSkill.y + 8 };
    A.merge = { x: sp, y: A.you.y - 30 };
    const n = M && !M.gate.open ? Math.min(6, M.queue.length) : 0;
    A.gateIn = { x: rail, y: A.gate.y - 13 - n * 11 };
    A.gateOut = { x: rail, y: A.gate.y + 12 };
    A.spineGate = { x: sp, y: A.gate.y + 6 };
  }

  function ptOf(ref) {
    if (typeof ref === "string") { const a = A[ref]; return a ? [a.x, a.y] : null; }
    if (ref.geo) { if (!proj) return null; const p = proj(ref.geo[0], ref.geo[1]); return [p[0] + mapOff[0], p[1] + mapOff[1]]; }
    if (ref.beacon) { const b = BE[ref.beacon]; return b ? [b.x + mapOff[0], b.y + mapOff[1]] : null; }
    return [ref.x, ref.y];
  }

  // ---------------------------------------------------------------- the map (static layer)
  function ringPath(c, ring) {
    ring.forEach((p, i) => { const [x, y] = proj(p[0], p[1]); if (i) c.lineTo(x, y); else c.moveTo(x, y); });
    c.closePath();
  }

  // The map in two parts: the base (land, areas, vignette; its dot matrix is the costly part) is
  // drawn once per size, region and area set into its own canvas; airports, volcanoes and aircraft
  // are drawn over a copy of it whenever the snapshot moves them.
  const baseC = document.createElement("canvas");
  const bctx = baseC.getContext("2d");
  let baseKey = "";
  function drawMap() {
    if (!M || !M.geo.bbox) return;
    const r = mapWrap.getBoundingClientRect();
    const where = M.geo.aircraft.reduce((a, x) => a + (x.at ? x.at[0] * 7 + x.at[1] : 0), 0).toFixed(3);
    const bKey = [r.width, r.height, phone, landRings ? landRings.length : 0, M.geo.cones.map((c) => `${c.mode}${c.top}${c.rings[0]?.length}`).join(","), M.geo.official.length, M.geo.bbox.west, M.geo.bbox.north].join("|");
    const key = [bKey, M.geo.aircraft.length, where, M.geo.volcanoes.map((v) => v.code).join(""), (M.feeds || []).map((f) => f.status).join(""), M.replay].join("|");
    if (key === mapKey) return;
    mapKey = key;
    const W = r.width, H = r.height;
    if (bKey !== baseKey) {
      baseKey = bKey;
      baseC.width = mapC.width; baseC.height = mapC.height;
      drawBase(r, W, H);
    }
    const c = mctx;
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.clearRect(0, 0, mapC.width, mapC.height);
    c.drawImage(baseC, 0, 0);
    c.setTransform(DPR, 0, 0, DPR, 0, 0);
    drawMovers(c);
    // the labels are DOM: rebuilt only when what they say or where they sit can change
    const lKey = [bKey, M.geo.volcanoes.map((v) => v.id).join(","), (M.feeds || []).map((f) => `${f.status}${f.records}`).join(""), M.geo.official.filter((o) => o.kind === "SIGMET").length].join("|");
    if (lKey !== labelKey) { labelKey = lKey; placeLabels(proj.V, W, H); }
  }
  let labelKey = "";

  function drawBase(r, W, H) {
    const b = M.geo.bbox;
    const V = freeView(r);
    const pad = 0.2;
    const focus = { w: b.west - pad, e: b.east + pad, n: b.north + pad, s: b.south - pad };
    const k = Math.min(V.w / (focus.e - focus.w), V.h / (focus.n - focus.s));
    const cx = V.x + V.w / 2, cy = V.y + V.h / 2, lc = (focus.w + focus.e) / 2, pc = (focus.n + focus.s) / 2;
    proj = (lon, lat) => [cx + (lon - lc) * k, cy - (lat - pc) * k];
    proj.k = k; proj.V = V; proj.centre = [lc, pc];
    const c = bctx;
    c.setTransform(DPR, 0, 0, DPR, 0, 0);
    c.clearRect(0, 0, W, H);
    const [kx, ky] = proj(lc, pc);
    const g = c.createRadialGradient(kx, ky, 20, kx, ky, Math.max(W, H) * 0.75);
    g.addColorStop(0, C.s2); g.addColorStop(0.55, C.s1); g.addColorStop(1, C.bg);
    c.fillStyle = g; c.fillRect(0, 0, W, H);
    // graticule, 2°
    c.strokeStyle = rgba(C.info, 0.045); c.lineWidth = 1;
    for (let lon = Math.floor(lc - 60); lon <= lc + 60; lon += 2) { const [x] = proj(lon, 0); if (x < -2 || x > W + 2) continue; c.beginPath(); c.moveTo(Math.round(x) + 0.5, 0); c.lineTo(Math.round(x) + 0.5, H); c.stroke(); }
    for (let lat = Math.floor(pc - 40); lat <= pc + 40; lat += 2) { const [, y] = proj(lc, lat); if (y < -2 || y > H + 2) continue; c.beginPath(); c.moveTo(0, Math.round(y) + 0.5); c.lineTo(W, Math.round(y) + 0.5); c.stroke(); }
    // land: a quiet fill and a dot matrix sampled from it
    if (landRings) {
      const vis = landRings.filter((ring) => ring.some((p) => { const [x, y] = proj(p[0], p[1]); return x > -200 && x < W + 200 && y > -200 && y < H + 200; }));
      const off = document.createElement("canvas");
      off.width = Math.max(1, Math.ceil(W)); off.height = Math.max(1, Math.ceil(H));
      const o = off.getContext("2d", { willReadFrequently: true });
      o.fillStyle = "#fff";
      for (const ring of vis) { o.beginPath(); ringPath(o, ring); o.fill(); }
      c.fillStyle = C.s1;
      for (const ring of vis) { c.beginPath(); ringPath(c, ring); c.fill(); }
      const img = o.getImageData(0, 0, off.width, off.height).data;
      const step = phone ? 4 : 5;
      for (let y = step / 2; y < off.height; y += step) for (let x = step / 2; x < off.width; x += step) {
        if (img[((y | 0) * off.width + (x | 0)) * 4 + 3] > 128) {
          const dd = Math.hypot(x - kx, y - ky) / Math.max(W, H);
          c.fillStyle = rgba(C.info, Math.max(0.16, 0.5 - dd * 0.6).toFixed(3));
          c.fillRect(x - 0.8, y - 0.8, 1.6, 1.6);
        }
      }
      c.strokeStyle = rgba(C.info, 0.26); c.lineWidth = 0.9;
      for (const ring of vis) { c.beginPath(); ringPath(c, ring); c.stroke(); }
    }
    // where the aircraft feed looks (the region's adsb.lol query circles)
    c.setLineDash([2, 5]); c.strokeStyle = rgba(C.aircraft, 0.12); c.lineWidth = 1;
    for (const a of M.geo.adsbPoints) { const [x, y] = proj(a.lon, a.lat); c.beginPath(); c.arc(x, y, (a.radius_nm / 60) * k, 0, 7); c.stroke(); }
    c.setLineDash([]);
    // the official areas (every SIGMET and VAA polygon, and the official cone that holds them) as one
    // area: filled once and outlined along its outer edge, however many products overlap
    const official = [...M.geo.official.flatMap((o) => o.rings), ...M.geo.cones.filter((cn) => cn.mode === "OFFICIAL").flatMap((cn) => cn.rings)];
    if (official.length) {
      const layer = () => { const x = document.createElement("canvas"); x.width = baseC.width; x.height = baseC.height; const xc = x.getContext("2d"); xc.setTransform(DPR, 0, 0, DPR, 0, 0); return [x, xc]; };
      const [fillC, fc] = layer();
      fc.fillStyle = C.official;
      for (const ring of official) { fc.beginPath(); ringPath(fc, ring); fc.fill(); }
      const [edgeC, ec] = layer();
      ec.strokeStyle = C.official; ec.lineWidth = 2.4; ec.lineJoin = "round";
      for (const ring of official) { ec.beginPath(); ringPath(ec, ring); ec.stroke(); }
      ec.globalCompositeOperation = "destination-out";
      for (const ring of official) { ec.beginPath(); ringPath(ec, ring); ec.fill(); }
      c.save(); c.setTransform(1, 0, 0, 1, 0, 0);
      c.globalAlpha = 0.07; c.drawImage(fillC, 0, 0);
      c.globalAlpha = 0.55; c.drawImage(edgeC, 0, 0);
      c.restore();
    }
    // TEPHRA's area where it is wider than the official one
    for (const cn of M.geo.cones) for (const ring of cn.rings) {
      if (cn.mode === "OFFICIAL") continue;
      c.beginPath(); ringPath(c, ring);
      c.setLineDash([6, 4]); c.strokeStyle = C.tephra; c.globalAlpha = 0.7; c.lineWidth = 1.4; c.stroke(); c.globalAlpha = 1; c.setLineDash([]);
    }
    // vignette
    const vg = c.createRadialGradient(W * 0.42, H * 0.5, Math.min(W, H) * 0.35, W * 0.42, H * 0.5, Math.max(W, H) * 0.8);
    vg.addColorStop(0, rgba(C.bg, 0)); vg.addColorStop(1, rgba(C.bg, 0.7));
    c.fillStyle = vg; c.fillRect(0, 0, W, H);
  }

  function drawMovers(c) {
    c.fillStyle = rgba(C.text2, 0.55);
    for (const p of Object.values(M.geo.airports)) { const [x, y] = proj(p[0], p[1]); c.fillRect(x - 2, y - 2, 4, 4); }
    for (const v of M.geo.volcanoes) {
      if (!v.at) continue;
      const [x, y] = proj(v.at[0], v.at[1]);
      // a volcano's real aviation colour code is the board's only red
      c.beginPath(); c.moveTo(x, y - 7); c.lineTo(x + 6.5, y + 5); c.lineTo(x - 6.5, y + 5); c.closePath();
      c.fillStyle = { RED: tok("--c-code-red", "#e8273b"), ORANGE: tok("--c-code-orange", "#f2711c"), YELLOW: tok("--c-code-yellow", "#fff176"), GREEN: tok("--c-code-green", "#2ec4a0") }[v.code] || tok("--c-code-unknown", "#8a96a3");
      c.fill(); c.strokeStyle = C.bg; c.lineWidth = 1.5; c.stroke();
    }
    for (const a of M.geo.aircraft) {
      if (!a.at) continue;
      const [x, y] = proj(a.at[0], a.at[1]);
      c.save(); c.translate(x, y); c.rotate(((a.trk ?? 0) * Math.PI) / 180);
      c.fillStyle = a.exposed ? rgba(C.job, 0.92) : rgba(C.aircraft, 0.55);
      c.beginPath(); c.moveTo(0, -5.5); c.lineTo(3.6, 4); c.lineTo(0, 2.2); c.lineTo(-3.6, 4); c.closePath(); c.fill();
      c.restore();
    }
  }

  function placeLabels(V, W, H) {
    BE = {};
    const kids = [];
    const centre = [proj.centre[0], proj.centre[1]];
    const [cx, cy] = [V.x + V.w / 2, V.y + V.h / 2];
    const feeds = Object.fromEntries((M.feeds || []).map((f) => [f.feed, f]));
    const sig = M.geo.official.filter((o) => o.kind === "SIGMET" && o.rings[0]);
    const insideView = (x, y) => x > V.x - 4 && x < V.x + V.w + 4 && y > V.y - 4 && y < V.y + V.h + 4;
    const beacons = [];
    for (const [id, s] of Object.entries(SRC)) {
      const f = feeds[id];
      if (!f) continue;
      const on = f.status === "OK" || f.status === "STALE";
      let at = s.at;
      if (id === "sigmet") {
        const pts = sig.flatMap((o) => o.rings[0]).filter((p) => { const [x, y] = proj(p[0], p[1]); return insideView(x, y); });
        at = pts.length ? [pts.reduce((a, p) => a + p[0], 0) / pts.length, pts.reduce((a, p) => a + p[1], 0) / pts.length] : null;
      }
      if (id === "winds") { const b = M.geo.bbox; at = [(b.west + b.east) / 2, b.south + 0.3]; }
      let x, y, edge = false, lab = "r", arrow = "";
      if (at) [x, y] = proj(at[0], at[1]); else { x = V.x + 30; y = V.y + 14; }
      if (!insideView(x, y)) {
        edge = true;
        const dx = x - cx, dy = y - cy;
        const t = Math.min((V.w / 2 - 14) / Math.abs(dx || 1e-6), (V.h / 2 - 12) / Math.abs(dy || 1e-6), 1);
        const rx = x, ry = y;
        x = cx + dx * t; y = cy + dy * t; lab = x > cx ? "l" : "r";
        arrow = ARROWS[Math.round((((Math.atan2(ry - y, rx - x) * 180) / Math.PI) + 360) % 360 / 45) % 8];
      }
      // two sources at one place (Tokyo's VAAC and JMA's notices) stack, never overlap
      while (Object.values(BE).some((o) => Math.abs(o.x - x) < 90 && Math.abs(o.y - y) < 26)) y += 34;
      BE[id] = { x, y, on, kind: (id === "vona" || id === "jma_volcano") ? "observer" : id === "winds" || id === "frames" ? "weather" : "official" };
      const km = edge && at ? Math.round(kmBetween(at, centre) / 100) * 100 : null;
      const recorded = /not in this replay case/i.test(f.error || "");
      const sub = !on ? (recorded ? "not in this recording" : "off") : edge && km ? `${s.sub} · ${km.toLocaleString("en")} km`
        : id === "sigmet" ? (at ? `${plural(sig.length, "area")} in force` : "none in force here") : s.sub;
      const labEl = el("span", { class: `flow-beacon__lab flow-beacon__lab--${lab}` }, el("b", { text: `${arrow ? `${arrow} ` : ""}${s.name}` }), phone ? null : el("span", { text: sub }));
      const b = el("div", { class: `flow-beacon flow-beacon--${BE[id].kind}${on ? "" : " is-off"}`, title: on ? `${FEED_TITLE[id]}: ${f.records ?? 0} records` : `${FEED_TITLE[id]}: ${f.error || "off"}` },
        el("i", { class: `flow-beacon__pin${edge ? " is-edge" : ""}` }), labEl);
      b.style.left = `${x}px`; b.style.top = `${y}px`;
      kids.push(b);
      beacons.push({ b, labEl, lab });
    }
    // volcano names, and the biggest official area's band
    const names = [];
    for (const v of M.geo.volcanoes) {
      if (!v.at) continue;
      const [x, y] = proj(v.at[0], v.at[1]);
      if (!insideView(x, y)) continue;
      const l = el("span", { class: "flow-maplabel flow-maplabel--vol", text: v.name });
      kids.push(l);
      names.push({ l, x, y });
    }
    let ash = null;
    const official = M.geo.cones.filter((c) => c.mode === "OFFICIAL" && c.rings[0]).sort((a, b) => (b.top || 0) - (a.top || 0))[0];
    if (official && !phone) {
      const pts = official.rings[0].map((p) => proj(p[0], p[1])).filter(([x, y]) => insideView(x, y));
      if (pts.length) {
        const low = pts.reduce((a, p) => (p[1] > a[1] ? p : a));
        const l = el("span", { class: "flow-maplabel flow-maplabel--ash", text: `Official ash area · ${official.base > 0 ? fl(official.base) : "surface"} to ${fl(official.top)}` });
        kids.push(l);
        ash = { l, x: clamp(low[0], V.x + 120, V.x + V.w - 120), y: Math.min(low[1] - 14, V.y + V.h - 10) };
      }
    }
    labels.replaceChildren(...kids);
    // Labels give way to each other and stay on the map: each takes the first place that overlaps no
    // label placed before it (a beacon's words switch side, then step up or down; a name moves
    // around its volcano), and a name with no free place is left out.
    const box = labels.getBoundingClientRect();
    const placed = [];
    const rectOf = (n) => { const r = n.getBoundingClientRect(); return { l: r.left - box.left, t: r.top - box.top, r: r.right - box.left, b: r.bottom - box.top }; };
    const clear = (q) => q.l >= 2 && q.r <= W - 2 && q.t >= 2 && q.b <= H - 2 && !placed.some((p) => q.l < p.r + 4 && q.r > p.l - 4 && q.t < p.b + 2 && q.b > p.t - 2);
    for (const { b, labEl, lab } of beacons) {
      const tries = [];
      for (const side of [lab, lab === "r" ? "l" : "r"]) for (const dy of [0, -16, 16, -32, 32]) tries.push([side, dy]);
      let ok = false;
      for (const [side, dy] of tries) {
        labEl.className = `flow-beacon__lab flow-beacon__lab--${side}`;
        labEl.style.top = dy ? `${-9 + dy}px` : "";
        const q = rectOf(labEl);
        if (clear(q)) { placed.push(q, rectOf(b.firstChild)); ok = true; break; }
      }
      if (!ok) { labEl.className = `flow-beacon__lab flow-beacon__lab--${lab}`; labEl.style.top = ""; placed.push(rectOf(labEl), rectOf(b.firstChild)); }
    }
    const placeAt = (l, spots) => {
      for (const [x, y] of spots) {
        l.style.left = `${x}px`; l.style.top = `${y}px`;
        const q = rectOf(l);
        const dx = q.l < 2 ? 2 - q.l : q.r > W - 2 ? W - 2 - q.r : 0;
        if (dx) { l.style.left = `${x + dx}px`; q.l += dx; q.r += dx; }
        if (clear(q)) { placed.push(q); return true; }
      }
      l.remove();
      return false;
    };
    for (const { l, x, y } of names) placeAt(l, [[x, y + 18], [x, y - 18], [x + 12 + l.offsetWidth / 2, y], [x - 12 - l.offsetWidth / 2, y]]);
    if (ash) placeAt(ash.l, [[ash.x, ash.y], [ash.x, ash.y - 22], [ash.x, ash.y + 18]]);
  }

  // ---------------------------------------------------------------- motion
  let P = [], TK = [], RP = [], HL = [], TR = [];
  let now = 0, raf = 0, lastFrame = 0;
  const SPR = {};
  function sprite(col) {
    if (SPR[col]) return SPR[col];
    const s = document.createElement("canvas"); s.width = s.height = 64;
    const c = s.getContext("2d");
    const g = c.createRadialGradient(32, 32, 0, 32, 32, 32);
    g.addColorStop(0, "rgba(255,255,255,1)"); g.addColorStop(0.12, col);
    c.globalAlpha = 1; c.fillStyle = g; c.fillRect(0, 0, 64, 64);
    const g2 = c.createRadialGradient(32, 32, 6, 32, 32, 32);
    g2.addColorStop(0, "rgba(0,0,0,0)"); g2.addColorStop(1, "rgba(0,0,0,1)");
    c.globalCompositeOperation = "destination-out"; c.fillStyle = g2; c.fillRect(0, 0, 64, 64);
    return (SPR[col] = s);
  }
  function glow(x, y, col, r, a = 1) { fx.globalAlpha = a; fx.drawImage(sprite(col), x - r, y - r, r * 2, r * 2); fx.globalAlpha = 1; }
  const arcTop = () => (phone ? 0 : (A.code ? Math.min(A.code.y, 90) : 90));
  function arc(sx, sy, tx, ty, u) {
    const mx = (sx + tx) / 2, my = (sy + ty) / 2, d = Math.hypot(tx - sx, ty - sy);
    const cx = mx - d * 0.05, cy = Math.max(arcTop(), my - d * 0.3);
    const a = 1 - u;
    return [a * a * sx + 2 * a * u * cx + u * u * tx, a * a * sy + 2 * a * u * cy + u * u * ty];
  }
  function later(fn, delayS) { const g = gen; window.setTimeout(() => { if (g === gen) fn(); }, delayS * 1000); }
  // one particle from the map into a panel node; under reduced motion a still line instead
  function emit(from, to, col, { delay = 0, dur = 1.5, size = 1, onArrive = null, quiet = false } = {}) {
    if (RM()) { HL.push({ line: true, from, to, col, t0: now + delay, dur: 1.8, a: quiet ? 0.4 : 0.85 }); if (onArrive) later(onArrive, delay); return; }
    if (P.length >= MAX_P) { if (onArrive) later(onArrive, delay + dur); return; }
    P.push({ from, to, col, t0: now + delay, dur, size, onArrive, done: false, a: quiet ? 0.45 : 1 });
    if (TR.length < MAX_TR && !quiet) TR.push({ from, to, col, t0: now + delay, dur, fade: 3.2, a: Math.min(0.16, 0.07 * size + 0.04) });
  }
  function ripple(at, col, { delay = 0, r1 = 26, dur = 1.1, w = 1.5 } = {}) { if (!RM()) RP.push({ at, col, t0: now + delay, dur, r1, w }); }
  // a node's pulse stays inside its own column: a thin ring and a small glow, never over its words
  function pulse(id, col) { ripple(id, col, { r1: 9, dur: 0.8, w: 1.2 }); HL.push({ node: id, col, t0: now, dur: 0.6 }); }
  function token(route, col, opts = {}) {
    if (RM()) {
      HL.push({ line: true, inPanel: true, from: route[0], to: route[route.length - 1], col: opts.col2 || col, t0: now + (opts.delay || 0), dur: 1.8 });
      if (opts.onArrive) later(opts.onArrive, 0.4 + (opts.delay || 0));
      return null;
    }
    if (TK.length >= MAX_TK) { if (opts.onArrive) later(opts.onArrive, 1 + (opts.delay || 0)); return null; }
    const t = { route: route.slice(), seg: 0, u: 0, col, col2: opts.col2 || null, t0: now + (opts.delay || 0), onArrive: opts.onArrive || null, pauseAt: opts.pauseAt || {}, lit: opts.lit || {}, wait: 0, hist: [], fired: false, group: opts.group };
    TK.push(t);
    return t;
  }
  function litSkill(id) {
    const d = skillEls[id]?.dot;
    if (!d) return;
    d.classList.add("is-lit");
    window.setTimeout(() => d.classList.remove("is-lit"), 700);
  }

  function visibleAircraft() {
    if (!proj) return [];
    const V = proj.V;
    return M.geo.aircraft.filter((a) => a.at && (() => { const [x, y] = proj(a.at[0], a.at[1]); return x > V.x - 10 && x < V.x + V.w + 10 && y > V.y - 10 && y < V.y + V.h + 10; })());
  }

  // a skill of this hand-out's tool moved in the last few seconds (the live stream's order)
  function workMovedFor(h) {
    const skills = TOOL_SKILLS[h.tool] || [];
    return events.some((x) => x !== h && (x.type === "skill" || x.type === "skill-failed" || x.type === "desk") && skills.includes(x.skill) && x.at <= h.at && h.at - x.at < 5000);
  }

  // What one real event does (spec 4).
  function fire(e) {
    const ex = mode === "example";
    const lag = (e.lag || 0) / 1000;
    if (e.type === "feed") {
      const col = colOf(e.kind);
      if (e.feed === "metar" || e.feed === "taf") {
        const aps = Object.values(M.geo.airports);
        const n = Math.min(Math.max(1, e.n || 1), 12, aps.length || 1);
        for (let i = 0; i < n && aps.length; i++) {
          const ap = aps[i % aps.length];
          emit({ geo: ap }, "code", col, { delay: lag + i * 0.1, dur: 2.0, size: 0.75, onArrive: i === n - 1 ? () => pulse("code", col) : null });
          ripple({ geo: ap }, col, { delay: lag + i * 0.07, r1: 14, dur: 0.9, w: 1 });
        }
      } else if (e.feed === "winds") {
        const b = M.geo.bbox; const n = 18;
        for (let i = 0; i < n; i++) {
          const lon = b.west + ((((i * 7) % n) + 0.5) / n) * (b.east - b.west);
          const lat = b.south + 0.15 + (((i * 5) % 6) / 6) * (b.north - b.south) * 0.35;
          emit({ geo: [lon, lat] }, "code", col, { delay: lag + i * 0.07, dur: 2.2, size: 0.6, onArrive: i === n - 1 ? () => pulse("code", col) : null });
        }
        ripple({ beacon: "winds" }, col, { delay: lag, r1: 30 });
      } else if (BE[e.feed]) {
        const n = clamp(e.n || 3, 3, 9);
        for (let i = 0; i < n; i++) emit({ beacon: e.feed }, "code", col, { delay: lag + i * 0.14, dur: 2.1, size: i === 0 ? 1.25 : 0.85, onArrive: i === n - 1 ? () => pulse("code", col) : null });
        ripple({ beacon: e.feed }, col, { delay: lag, r1: 34, dur: 1.4, w: 2 });
        ripple({ beacon: e.feed }, col, { delay: lag + 0.25, r1: 22, dur: 1.2 });
        if (ex && (e.feed === "vona" || e.feed === "vaac_darwin")) exampleAssess(lag);
      } else pulse("code", col);
    } else if (e.type === "adsb") {
      // the most frequent read and the least telling: a glint on each aircraft where it is, and one
      // faint particle from the middle of them into Code checks
      const vis = visibleAircraft();
      if (!vis.length) { pulse("code", C.aircraft); return; }
      if (!RM()) vis.forEach((a, i) => HL.push({ glint: a.at, t0: now + lag + (i % 8) * 0.03, dur: 0.9 }));
      const mid = [vis.reduce((x, a) => x + a.at[0], 0) / vis.length, vis.reduce((x, a) => x + a.at[1], 0) / vis.length];
      emit({ geo: mid }, "code", C.aircraft, { delay: lag + 0.1, dur: 1.8, size: 0.5, quiet: true, onArrive: () => pulse("code", C.aircraft) });
    } else if (e.type === "flight") {
      const a = M.geo.aircraft.find((x) => x.flight === e.flight);
      if (a?.at) {
        HL.push({ flight: a, e, t0: now + lag, dur: 3.2 });
        ripple({ geo: a.at }, e.inside ? C.official : C.aircraft, { delay: lag, r1: 20, dur: 1.2 });
        emit({ geo: a.at }, "code", C.aircraft, { delay: lag, dur: 1.9, size: 1.05, onArrive: () => pulse("code", C.aircraft) });
      } else pulse("code", C.aircraft);
    } else if (e.type === "duty") {
      const n = clamp(e.n, 1, 12);
      for (let i = 0; i < n; i++) token(["code", "coord"], C.job, { delay: lag + i * 0.22, group: e.id, onArrive: i === 0 ? () => pulse("coord", C.job) : null });
      if (ex) later(() => exampleDispatch(e), lag + 0.7);
    } else if (e.type === "refused" || e.type === "undone") {
      if (ex) return;
      // refused: the run's jobs knock at the closed gate, turn caution and drop down the code lane to
      // you; undone (the model answered and left must-do work): straight down the code lane
      const land = () => { pendingLand.delete(e.id); renderDecide(true); renderLog(false); pulse("you", C.must); };
      pendingLand.add(e.id);
      const n = clamp(e.n, 1, 8);
      const route = e.type === "refused" ? ["coord", "gateIn", "spineGate", "merge", "you"] : ["coord", "spineGate", "merge", "you"];
      for (let i = 0; i < n; i++) {
        token(route, C.job, { delay: lag + i * 0.14, col2: C.must, pauseAt: e.type === "refused" ? { gateIn: 0.55 + i * 0.18 } : {}, onArrive: i === n - 1 ? land : null });
      }
      if (e.type === "refused") HL.push({ gate: true, t0: now + lag + 0.4, dur: 0.9 });
      if (!e.n) later(land, lag + 0.6);
    } else if (e.type === "handoff") {
      if (!e.skill || !A[`sk-${e.skill}`]) return;
      // through the gate to the skill. A model hand-out is a record that the model was open at that
      // moment, so a gate that is closed now opens while the token passes; with no model the skills
      // are code templates and the gate is drawn as a bypass.
      if (M.gate.kind !== "nomodel" && !gateOpen()) {
        gateOpenUntil = Math.max(gateOpenUntil, performance.now() + (lag + 1.6) * 1000);
        drawRails();
        later(drawRails, lag + 1.7);
      }
      token(["coord", "railTop", "gateOut", `sk-${e.skill}`], C.job, { delay: lag, onArrive: () => litSkill(e.skill) });
    } else if (e.type === "skill") {
      later(() => litSkill(e.skill), lag);
      if (e.toDesk) token([`sk-${e.skill}`, "railEnd", "merge", "you"], C.job, { delay: lag + 0.2, onArrive: () => pulse("you", C.job) });
      if (e.plume) {
        const v = M.geo.volcanoes.find((x) => x.id === e.volcano) || M.geo.volcanoes[0];
        if (v?.at) later(() => emit(`sk-${e.skill}`, { geo: v.at }, C.tephra, { dur: 1.6, size: 1.2, onArrive: () => ripple({ geo: v.at }, C.tephra, { r1: 44, dur: 1.6, w: 2 }) }), lag + 0.3);
      }
    } else if (e.type === "skill-failed") {
      later(() => { const d = skillEls[e.skill]?.dot; if (d) { d.classList.add("is-failed"); } }, lag);
    } else if (e.type === "desk") {
      token(["sk-drafter", "railEnd", "merge", "you"], C.job, { delay: lag, onArrive: () => pulse("you", C.job) });
    } else if (e.type === "onreq") {
      later(() => { onreqDot.classList.add("is-lit"); window.setTimeout(() => onreqDot.classList.remove("is-lit"), 700); }, lag);
      token(["sk-onreq", "merge", "you"], C.job, { delay: lag + 0.1 });
    } else if (e.type === "decided") {
      pulse("you", C.job);
    } else if (e.type === "brief") {
      pulse("coord", C.job);
    }
  }

  // EXAMPLE ONLY (illustrative): what the same recorded inputs would do with the model open. It
  // draws and counts in the view; nothing here reaches the Wall's data or any record.
  function exampleDispatch(e) {
    const n = clamp(e.n, 1, 8);
    for (let i = 0; i < n; i++) {
      token(["coord", "railTop", "gateOut", "sk-planner", "sk-drafter", "railEnd", "merge", "you"], C.job, {
        delay: 0.25 + i * 0.16, lit: { "sk-planner": 0.35, "sk-drafter": 0.3 },
        onArrive: () => { exampleLanded(e); pulse("you", C.job); },
      });
    }
  }
  function exampleAssess(lag) {
    const v = M.geo.volcanoes[0];
    token(["code", "coord", "railTop", "gateOut", "sk-plume"], C.job, { delay: lag + 1.4, onArrive: () => {
      litSkill("plume");
      if (v?.at) emit("sk-plume", { geo: v.at }, C.tephra, { dur: 1.6, size: 1.2, onArrive: () => ripple({ geo: v.at }, C.tephra, { r1: 44, dur: 1.6, w: 2 }) });
    } });
  }
  // a draft of an example run reached You decide: the hero counts the newest run's drafts as they land
  function exampleLanded(e) {
    if (mode !== "example" || e.at < exState.runAt) return;
    if (exState.run !== e.id) { exState.run = e.id; exState.runAt = e.at; exState.drafts = 0; }
    exState.drafts += 1;
    renderDecide(true);
  }

  function stepToken(t, dt) {
    if (now < t.t0) return true;
    if (t.wait > 0) { t.wait -= dt; return true; }
    if (t.seg >= t.route.length - 1) {
      if (!t.fired) { t.fired = true; if (t.onArrive) t.onArrive(); }
      return false;
    }
    const p = ptOf(t.route[t.seg]), q = ptOf(t.route[t.seg + 1]);
    if (!p || !q) { t.seg = t.route.length - 1; return true; }
    const L = Math.hypot(q[0] - p[0], q[1] - p[1]) + 1;
    t.u += (TOKEN_SPEED * dt) / L;
    if (t.u >= 1) {
      t.u = 0; t.seg += 1;
      const name = t.route[t.seg];
      if (t.pauseAt[name]) { t.wait = t.pauseAt[name]; if (name === "gateIn") t.bounce = now; }
      if (t.lit[name]) { t.wait = t.lit[name]; litSkill(name.slice(3)); }
      if (t.col2 && name === "gateIn") t.col = t.col2;
      if (t.col2 && name === "spineGate") t.col = t.col2;
    }
    return true;
  }
  function along(p, q, u) {
    if (Math.abs(p[0] - q[0]) < 1) return [p[0], p[1] + (q[1] - p[1]) * u];
    const dy = q[1] - p[1];
    const c1 = [p[0], p[1] + dy * 0.55], c2 = [q[0], q[1] - dy * 0.55];
    const a = 1 - u;
    return [a * a * a * p[0] + 3 * a * a * u * c1[0] + 3 * a * u * u * c2[0] + u * u * u * q[0], a * a * a * p[1] + 3 * a * a * u * c1[1] + 3 * a * u * u * c2[1] + u * u * u * q[1]];
  }
  function drawToken(t) {
    if (now < t.t0) return;
    let pos;
    if (t.seg >= t.route.length - 1) pos = ptOf(t.route[t.route.length - 1]);
    else { const p = ptOf(t.route[t.seg]), q = ptOf(t.route[t.seg + 1]); pos = p && q ? along(p, q, easeIO(Math.min(1, t.u))) : null; }
    if (!pos) return;
    let [x, y] = pos;
    if (t.bounce && now - t.bounce < 0.35) y -= Math.sin(((now - t.bounce) / 0.35) * Math.PI) * 3;
    t.hist.push([x, y]); if (t.hist.length > 12) t.hist.shift();
    fx.globalCompositeOperation = "lighter"; fx.lineCap = "round";
    for (let i = 1; i < t.hist.length; i++) { const k = i / t.hist.length; fx.strokeStyle = t.col; fx.globalAlpha = k * 0.5; fx.lineWidth = k * 3; fx.beginPath(); fx.moveTo(t.hist[i - 1][0], t.hist[i - 1][1]); fx.lineTo(t.hist[i][0], t.hist[i][1]); fx.stroke(); }
    fx.globalAlpha = 1;
    glow(x, y, t.col, 11, 0.8);
    fx.globalCompositeOperation = "source-over";
    fx.fillStyle = t.col; fx.beginPath(); fx.arc(x, y, 3.6, 0, 7); fx.fill();
  }

  // the gate as drawn now: the current state, open while a recorded model hand-out passes, and always
  // open in Example (illustrative)
  const gateOpen = () => mode === "example" || M.gate.open || performance.now() < gateOpenUntil;
  function drawRails() {
    const c = rctx;
    c.setTransform(DPR, 0, 0, DPR, 0, 0);
    c.clearRect(0, 0, VW, VH);
    if (!A.code || !A.you || !A.gate || !M) return;
    const ex = mode === "example";
    const sp = A.spine, code = A.code, coord = A.coord, you = A.you;
    c.lineCap = "round";
    // the spine: code -> Coordinator -> the code lane down to you (caution toward you while must-do
    // work goes that way)
    const toYou = !ex && (M.ai.kind === "paused" || M.desk.must > 0);
    const grd = c.createLinearGradient(0, code.y, 0, you.y);
    grd.addColorStop(0, rgba(C.info, 0.45)); grd.addColorStop(0.4, rgba(C.info, 0.32));
    grd.addColorStop(1, toYou ? rgba(C.must, 0.45) : rgba(C.info, 0.3));
    c.strokeStyle = grd; c.lineWidth = 1.5;
    c.beginPath(); c.moveTo(sp, code.y + 13); c.lineTo(sp, coord.y - 13); c.moveTo(sp, coord.y + 13); c.lineTo(sp, you.y - 13); c.stroke();
    // the AI lane: Coordinator -> gate -> skills -> merge; with no model, the code templates' lane (dashed)
    const nomodel = !ex && M.gate.kind === "nomodel";
    const open = gateOpen();
    c.strokeStyle = open && !nomodel ? rgba(C.job, 0.36) : rgba(C.info, 0.26); c.lineWidth = 1.5;
    if (nomodel) c.setLineDash([4, 4]);
    c.beginPath();
    curve(c, [sp, coord.y + 8], [A.rail, A.gateIn.y]); c.lineTo(A.rail, A.gate.y);
    c.moveTo(A.rail, A.gateOut.y); c.lineTo(A.rail, A.railEnd.y);
    curve(c, [A.rail, A.railEnd.y], [sp, A.merge.y], true);
    c.stroke();
    c.setLineDash([]);
    const g = A.gate;
    if (!ex && !M.gate.open) {
      // the jobs waiting in line, parked in front of the gate (budget.waiting, now)
      M.queue.slice(0, 6).forEach((w, i) => {
        const y = g.y - 11 - i * 11;
        c.fillStyle = C.s1; c.beginPath(); c.arc(g.x, y, 4.6, 0, 7); c.fill();
        c.strokeStyle = C.info; c.lineWidth = 1.5; c.beginPath(); c.arc(g.x, y, 4.2, 0, 7); c.stroke();
      });
    }
    if (!open) {
      c.strokeStyle = C.info; c.lineWidth = 3;
      c.beginPath(); c.moveTo(g.x - 11, g.y); c.lineTo(g.x + 11, g.y); c.stroke();
    } else {
      // open: the bar split in two (dashed: no model, the skills are code templates)
      c.strokeStyle = nomodel ? rgba(C.info, 0.6) : rgba(C.job, 0.5); c.lineWidth = 2;
      if (nomodel) c.setLineDash([2, 2]);
      c.beginPath(); c.moveTo(g.x - 11, g.y); c.lineTo(g.x - 5, g.y); c.moveTo(g.x + 5, g.y); c.lineTo(g.x + 11, g.y); c.stroke();
      c.setLineDash([]);
    }
  }
  function curve(c, p, q, noMove) {
    const dy = q[1] - p[1];
    if (!noMove) c.moveTo(p[0], p[1]);
    c.bezierCurveTo(p[0], p[1] + dy * 0.55, q[0], q[1] - dy * 0.55, q[0], q[1]);
  }

  function drawHL(h) {
    const u = (now - h.t0) / h.dur;
    if (u < 0) return true;
    if (u >= 1) return false;
    const a = u < 0.15 ? u / 0.15 : 1 - (u - 0.15) / 0.85;
    const c = fx;
    if (h.glint) { const p = ptOf({ geo: h.glint }); if (p) { c.globalCompositeOperation = "lighter"; glow(p[0], p[1], C.aircraft, 10, a * 0.6); c.globalCompositeOperation = "source-over"; } return true; }
    if (h.flight) {
      const p = ptOf({ geo: h.flight.at });
      if (!p) return true;
      const [x, y] = p;
      c.globalAlpha = Math.min(1, a * 1.6);
      c.strokeStyle = h.e.inside ? C.officialText : C.job; c.lineWidth = 1.25; c.beginPath(); c.arc(x, y, 9, 0, 7); c.stroke();
      c.font = "500 12px 'IBM Plex Mono', monospace"; c.textBaseline = "middle";
      const txt = phone ? h.e.flight : `${h.e.flight} ${h.e.fl}${h.e.inside ? " · inside" : ` · in ${h.e.mins} min`}`;
      const w = c.measureText(txt).width;
      // an opaque plate: the aircraft around it must not show through the flight's name
      c.globalAlpha = Math.min(1, a * 3);
      c.fillStyle = C.s1; roundRect(c, x + 13, y - 10, w + 12, 20, 5); c.fill();
      c.strokeStyle = rgba(h.e.inside ? C.official : C.job, 0.35); c.lineWidth = 1; c.stroke();
      c.globalAlpha = Math.min(1, a * 1.6);
      c.fillStyle = h.e.inside ? C.officialText : C.job; c.fillText(txt, x + 19, y + 0.5);
      c.globalAlpha = 1;
      return true;
    }
    if (h.node) { const n = A[h.node]; if (n) { c.globalCompositeOperation = "lighter"; glow(n.x, n.y, h.col, 17, a * 0.6); c.globalCompositeOperation = "source-over"; } return true; }
    if (h.gate) { const g = A.gate; if (g) { c.globalAlpha = a; c.strokeStyle = C.info; c.lineWidth = 1.2; c.beginPath(); c.arc(g.x, g.y, RM() ? 14 : 10 + u * 8, 0, 7); c.stroke(); c.globalAlpha = 1; } return true; }
    if (h.line) {
      // reduced motion: a still line from source to target with dots at both ends
      const p = ptOf(h.from), q = ptOf(h.to);
      if (!p || !q) return true;
      c.globalAlpha = a * (h.a ?? 0.85); c.strokeStyle = h.col; c.lineWidth = 1.5; c.beginPath(); c.moveTo(p[0], p[1]);
      if (h.inPanel) c.lineTo(q[0], q[1]);
      else { const mx = (p[0] + q[0]) / 2, my = (p[1] + q[1]) / 2, d = Math.hypot(q[0] - p[0], q[1] - p[1]); c.quadraticCurveTo(mx - d * 0.05, Math.max(arcTop(), my - d * 0.3), q[0], q[1]); }
      c.stroke(); c.fillStyle = h.col; c.beginPath(); c.arc(p[0], p[1], 4, 0, 7); c.arc(q[0], q[1], 4, 0, 7); c.fill(); c.globalAlpha = 1;
      return true;
    }
    return false;
  }
  function roundRect(c, x, y, w, h, r) { c.beginPath(); c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r); c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath(); }

  const moving = () => P.length || TK.length || RP.length || HL.length || TR.length;
  function frame(t) {
    raf = 0;
    if (!isOpen || document.hidden || stale) return;
    const dt = Math.min(0.05, (t - (lastFrame || t)) / 1000);
    lastFrame = t; now += dt;
    tickPlayer(dt);
    const c = fx;
    c.setTransform(DPR, 0, 0, DPR, 0, 0);
    c.clearRect(0, 0, VW, VH);
    c.globalCompositeOperation = "lighter";
    RP = RP.filter((r) => {
      const u = (now - r.t0) / r.dur;
      if (u < 0) return true;
      if (u >= 1) return false;
      const p = ptOf(r.at); if (!p) return false;
      const e = 1 - Math.pow(1 - u, 3);
      c.strokeStyle = r.col; c.globalAlpha = (1 - u) * 0.7; c.lineWidth = r.w;
      c.beginPath(); c.arc(p[0], p[1], 4 + e * r.r1, 0, 7); c.stroke(); c.globalAlpha = 1;
      return true;
    });
    TR = TR.filter((tr) => {
      const u0 = (now - tr.t0) / tr.dur;
      if (u0 < 0) return true;
      const headU = easeIO(Math.min(1, u0)), fade = u0 <= 1 ? 1 : 1 - (now - tr.t0 - tr.dur) / tr.fade;
      if (fade <= 0) return false;
      const p = ptOf(tr.from), q = ptOf(tr.to); if (!p || !q) return false;
      c.strokeStyle = tr.col; c.globalAlpha = tr.a * fade * fade; c.lineWidth = 1.2;
      c.beginPath(); c.moveTo(p[0], p[1]);
      for (let k = 1; k <= 18; k++) { const [x, y] = arc(p[0], p[1], q[0], q[1], (headU * k) / 18); c.lineTo(x, y); }
      c.stroke(); c.globalAlpha = 1;
      return true;
    });
    P = P.filter((p) => {
      const u0 = (now - p.t0) / p.dur;
      if (u0 < 0) return true;
      const s = ptOf(p.from), q = ptOf(p.to);
      if (!s || !q) return false;
      if (u0 >= 1) { if (!p.done) { p.done = true; if (p.onArrive) p.onArrive(); } return false; }
      const u = easeIO(u0);
      const N = 12, tail = 0.16 * Math.min(1, u0 * 3);
      let px = s[0], py = s[1];
      for (let k = N; k >= 0; k--) {
        const [x, y] = arc(s[0], s[1], q[0], q[1], Math.max(0, u - (k / N) * tail));
        if (k < N) { c.strokeStyle = p.col; c.globalAlpha = (1 - k / N) * 0.55 * p.a; c.lineWidth = (1 - k / N) * 2.4 * p.size + 0.3; c.beginPath(); c.moveTo(px, py); c.lineTo(x, y); c.stroke(); }
        px = x; py = y;
      }
      c.globalAlpha = 1;
      glow(px, py, p.col, 10 * p.size, Math.min(1, u0 * 5) * p.a);
      return true;
    });
    TK = TK.filter((tk) => stepToken(tk, dt));
    c.globalCompositeOperation = "source-over";
    for (const tk of TK) drawToken(tk);
    HL = HL.filter(drawHL);
    if (playing || moving()) raf = requestAnimationFrame(frame);
    else { lastFrame = 0; }
  }
  function kick() {
    if (!raf && isOpen && !document.hidden && !stale) { lastFrame = 0; raf = requestAnimationFrame(frame); }
  }
  function drawStill() {
    fx.setTransform(DPR, 0, 0, DPR, 0, 0);
    fx.clearRect(0, 0, VW, VH);
    drawRails();
  }

  // ---------------------------------------------------------------- the player
  // `simT` is the only source of state: seek() rebuilds counters, log, hero and run bars from every
  // event at or before it, with no motion; playing fires each later event as the playhead passes it.
  function seek(t) {
    simT = clamp(t, T0, T1);
    P = []; TK = []; RP = []; HL = []; TR = [];
    pendingLand = new Set();
    gen += 1;
    nextIdx = events.findIndex((e) => e.at > simT);
    if (nextIdx < 0) nextIdx = events.length;
    for (const d of Object.values(skillEls)) d.dot.classList.remove("is-lit", "is-failed");
    gateOpenUntil = 0;
    exState.run = null; exState.runAt = -Infinity; exState.drafts = 0;
    if (mode === "example") {
      // at a seek the newest example run's drafts have all landed (one per job, spec 5)
      const S = flowAt(events, simT, { example: true });
      const run = events.filter((e) => e.type === "duty" && e.at <= simT).pop();
      if (run) { exState.run = run.id; exState.runAt = run.at; exState.drafts = S.drafts; }
    }
    renderCounters(); renderLog(false); renderDecide(false); drawTrack(); renderSheetSteps();
    setSkipping(false);
    drawStill();
  }

  let rmTimer = 0, endHold = 0, skipping = false, skipShownAt = -9, skipOn = false;
  function setSkipping(on) {
    if (on === skipOn) return;
    skipOn = on;
    player.classList.toggle("is-skipping", on);
  }
  const busy = () => P.length > 0 || TK.some((t) => !t.fired && now >= t.t0);
  function tickPlayer(dt) {
    if (!playing) return;
    if (RM()) {
      rmTimer -= dt;
      if (rmTimer <= 0) { rmTimer = 2.2; stepOne(); }
      return;
    }
    if (simT >= T1) { endHold += dt; if (endHold > 1.2) { endHold = 0; toLiveEdge(); } return; }
    let k = 1;
    const nxt = events[nextIdx];
    if (nxt && !busy()) { const gap = (nxt.at - simT) / (speed * 1000); if (gap > 1.1) k = Math.min(14, gap / 0.6); }
    const was = skipping;
    skipping = k > 1.5;
    if (skipping && !was) skipShownAt = now;
    setSkipping(skipping || now - skipShownAt < 1.2);
    simT = Math.min(T1, simT + dt * 1000 * speed * k);
    let any = false;
    while (nextIdx < events.length && events[nextIdx].at <= simT) { playEvent(events[nextIdx++]); any = true; }
    if (any) { renderCounters(); renderLog(true); renderDecide(false); renderSheetSteps(); }
    drawTrack();
  }
  function stepOne() {
    if (nextIdx >= events.length) { toLiveEdge(); return; }
    const first = events[nextIdx];
    while (nextIdx < events.length && events[nextIdx].at - first.at < 1500) { const e = events[nextIdx++]; simT = e.at; playEvent(e); }
    renderCounters(); renderLog(true); renderDecide(false); drawTrack(); renderSheetSteps();
    kick();
  }
  function playEvent(e) {
    fired.add(e.id);
    if (!e.quiet || e.type === "adsb") fire(e);
  }
  // the end of the window: new steps animate as they arrive (spec 6, live)
  function toLiveEdge() {
    following = true;
    setPlaying(false);
    simT = T1;
    for (const e of events) fired.add(e.id);
    nextIdx = events.length;
    renderCounters(); renderLog(false); renderDecide(false); drawTrack(); renderPlayer(); renderSheetSteps();
    setSkipping(false);
  }
  function startPlayback(from = T0) {
    following = false;
    seek(from);
    setPlaying(true);
    renderPlayer();
  }
  function setPlaying(p) {
    playing = p;
    renderPlayer();
    if (p) kick();
  }

  // The player says "Replay" once, small, while the Wall plays a recording; the recording itself is
  // named by the Wall's frame, not here.
  function renderPlayer() {
    if (!M) return;
    const replay = M.replay;
    setText(chipWord, replay ? "Replay" : "Live");
    chipWord.classList.toggle("is-replay", replay);
    const span = M.spanMin ? `the last ${M.spanMin} min of real steps` : "no steps yet";
    setText(chipText, following ? "new steps play as they come" : playing ? `playing back ${span}` : `paused in ${span}`);
    const label = following ? `Play back ${span}` : playing ? "Pause the playback" : "Play the playback";
    const ic = playing ? "i-pause" : following ? "i-replay" : "i-play";
    if (play.dataset.icon !== ic) { play.dataset.icon = ic; play.replaceChildren(icon(ic)); }
    setAttr(play, "aria-label", label);
    setAttr(play, "title", label);
    speedBtn.hidden = RM() || following;
    setText(speedBtn, `${speed}×`);
    setAttr(speedBtn, "aria-label", `Playback speed ${speed} times`);
  }

  function drawTrack() {
    const r = track.getBoundingClientRect();
    if (!r.width || !M) return;
    if (trackC.width !== Math.round(r.width * DPR)) { trackC.width = Math.round(r.width * DPR); trackC.height = Math.round(r.height * DPR); }
    const c = tctx;
    c.setTransform(DPR, 0, 0, DPR, 0, 0);
    c.clearRect(0, 0, r.width, r.height);
    const span = Math.max(1, T1 - T0);
    const X = (t) => 4 + ((t - T0) / span) * (r.width - 8);
    const mid = r.height / 2;
    c.fillStyle = rgba(C.info, 0.16); c.fillRect(4, mid - 1, r.width - 8, 2);
    c.fillStyle = rgba(C.info, 0.55); c.fillRect(4, mid - 1, Math.max(0, X(simT) - 4), 2);
    for (const e of events) {
      if (e.quiet || e.type === "note") continue;
      const col = e.type === "refused" || e.type === "undone" ? (mode === "example" ? null : C.must) : e.type === "duty" || e.type === "handoff" || e.type === "skill" || e.type === "desk" ? C.job : e.type === "flight" || e.type === "adsb" ? C.aircraft : e.type === "feed" ? colOf(e.kind) : null;
      if (!col) continue;
      const h = e.type === "refused" || e.type === "duty" ? 6 : e.type === "feed" ? 9 : 4;
      c.globalAlpha = e.at <= simT ? 0.95 : 0.35; c.fillStyle = col;
      c.fillRect(Math.round(X(e.at)), e.type === "feed" ? mid - h - 2 : mid + 3, 1.5, h);
    }
    c.globalAlpha = 1;
    const x = X(simT);
    c.fillStyle = C.job; c.beginPath(); c.arc(x, mid, 5, 0, 7); c.fill();
    setText(tnow, hms(simT));
    setAttr(track, "aria-valuenow", String(Math.round(((simT - T0) / span) * 100)));
    setAttr(track, "aria-valuetext", `${M.replay ? "replay clock" : "clock"} ${hms(simT)}${following ? ", the newest step" : ""}`);
  }

  // ---------------------------------------------------------------- words
  let legendFor = "";
  function setMark(useHost, sym) {
    const u = useHost.querySelector("use");
    const href = `${u.getAttribute("href").split("#")[0]}#${sym}`;
    setAttr(u, "href", href);
  }
  function renderStatic() {
    const ex = mode === "example";
    dialog.classList.toggle("is-example", ex);
    setAttr(btnReal, "aria-pressed", String(!ex));
    setAttr(btnEx, "aria-pressed", String(ex));
    exFlag.hidden = !ex;
    const sym = ex ? "ta-working" : M.ai.symbol;
    setMark(markUse, sym);
    setMark(coordMark, sym);
    if (dialog.dataset.ai !== (ex ? "on" : M.ai.kind)) dialog.dataset.ai = ex ? "on" : M.ai.kind;
    if (dialog.dataset.mode !== M.mode) dialog.dataset.mode = M.mode;
    setText(status, `· ${ex ? "working (example)" : M.status}`);
    setAttr(status, "title", M.ai.title || null);
    setText(ledeText, ex ? "An example of a normal run on the same recorded inputs: the Coordinator hands each job to a skill, and every draft waits for you." : M.sub);
    const why = !ex && (M.ai.kind === "paused" || M.ai.kind === "trouble");
    if (whyBtn.hidden === why) whyBtn.hidden = !why;
    setText(gateName, ex ? "AI model · open" : M.gate.name);
    setText(gateMeta, ex ? "Example: open, jobs go straight through" : M.gate.meta);
    // what waits and where the cause is; why the assistant is paused is said at its home (8.6)
    setAttr(gateRow, "title", ex || (!M.queue.length && !M.gate.title) ? null : [M.queue.length ? `Waiting in line:\n${M.queue.map((w) => `• ${w.label}`).join("\n")}` : null, M.gate.title || null].filter(Boolean).join("\n"));
    setText(coordMeta, ex ? "Orders the jobs and hands them to skills" : M.coord.meta);
    setAttr(coordBtn, "aria-label", `Coordinator: ${ex ? "orders the jobs and hands them to skills (example)" : M.coord.meta}. Details`);
    for (const s of M.skills) {
      const r = skillEls[s.id];
      if (!r) continue;
      setText(r.name, s.name);
      const inLine = !ex && s.inLine;
      const failed = !ex && s.last?.failed;
      const stateKey = inLine ? `in:${s.inLine}` : failed ? "failed" : ex ? "ex" : s.last ? `last:${s.last.at}` : "idle";
      if (r.state.dataset.k !== stateKey) {
        r.state.dataset.k = stateKey;
        r.state.replaceChildren(...(inLine ? [el("i", { class: "flow-ring" }), `${s.inLine} in line`] : failed ? ["no result"] : ex ? [] : [s.last ? `last ${hms(s.last.at)}` : "idle"]));
      }
      r.li.classList.toggle("is-idle", !inLine && !failed && !ex && !s.last);
      r.dot.classList.toggle("is-wait", Boolean(inLine));
      setAttr(r.btn, "aria-label", `${s.name}: ${inLine ? `${s.inLine} ${s.inLine === 1 ? "job waits" : "jobs wait"} in line` : failed ? "its newest step gave no result" : s.last ? `newest step ${hms(s.last.at)}` : "nothing in the newest steps"}. Details`);
      setAttr(r.btn, "title", [s.does, s.last ? `${s.last.text} · ${hms(s.last.at)}` : null, inLine ? `In line: ${s.jobs.join("; ")}` : null].filter(Boolean).join("\n"));
    }
    if (legendFor !== mode) {
      legendFor = mode;
      const sw = (tone, word, hollow = false) => el("span", {}, (() => { const i = el("i", { class: hollow ? "is-hollow" : null }); if (hollow) i.style.color = colOf(tone); else i.style.background = colOf(tone); return i; })(), word);
      legend.replaceChildren(...(ex
        ? [sw("official", "official reports"), sw("observer", "observatory"), sw("aircraft", "aircraft"), sw("weather", "weather"), sw("job", "jobs (example)"), sw("tephra", "TEPHRA's estimate (example)")]
        : [sw("official", "official reports"), sw("observer", "observatory"), sw("aircraft", "aircraft"), sw("weather", "weather"), sw("job", "jobs"), sw("info", "waiting in line", true), sw("must", "must-do, to you")]));
    }
    renderDecide(false);
    renderPlayer();
  }

  function renderCounters() {
    const S = flowAt(events, simT);
    setText(cFeeds, S.feeds); setText(wFeeds, S.feeds === 1 ? " feed read · " : " feed reads · ");
    setText(cFlights, S.flights); setText(wFlights, S.flights === 1 ? " flight alert" : " flight alerts");
    // a run the model refused called no model: it is "not run", never "last run" (Q4)
    setText(coordRight, S.coordAt ? `${S.coordRefused ? "not run" : "last run"} ${hms(S.coordAt)}` : "");
  }

  // the hero: M of the newest refused run at the playhead (tokens still on their way do not count
  // until they land), or, while the assistant works, the drafts that wait at the Desk now
  function renderDecide(bump) {
    if (!M) return;
    const ex = mode === "example";
    const D = M.desk;
    const done = events.filter((e) => e.at <= simT && !pendingLand.has(e.id));
    const S = flowAt(done, simT);
    const mustMode = !ex && (S.must != null || M.ai.kind === "paused");
    let n, words;
    if (ex) { n = exState.run ? exState.drafts : null; words = n === 1 ? "advisory draft to approve (example)" : "advisory drafts to approve (example)"; }
    else if (mustMode) { n = S.must; words = n === 1 ? "must-do flight to plan by hand" : "must-do flights to plan by hand"; }
    else { n = D.drafts; words = n === 1 ? "advisory waits for you" : "advisories wait for you"; }
    const before = heroN.textContent;
    setText(heroN, n == null ? "–" : String(n));
    heroN.classList.toggle("is-none", n == null);
    setText(heroW, words);
    if (bump && before !== heroN.textContent && !RM()) { heroN.classList.add("is-bump"); window.setTimeout(() => heroN.classList.remove("is-bump"), 320); }
    decide.classList.toggle("is-must", mustMode);
    setText(who, ex ? (exState.run ? `Illustrative: one draft per flight of the example run at ${hms(exState.runAt)}.` : "Illustrative: no run in this window yet.")
      : mustMode ? (S.mustAt == null ? "Waiting for the first run in this window." : `Passed straight to you by code · run ${hms(S.mustAt)}`)
        : n == null ? "Advisory count unknown (database error)." : "Drafts wait at the Desk for a dispatcher.");
    // run bars: one per refused run in the window, lit up to the playhead
    const runs = M.runs.filter((e) => e.type === "refused");
    runsBox.hidden = ex || !runs.length;
    const max = Math.max(1, ...runs.map((r) => r.n));
    const lit = runs.filter((r) => r.at <= simT && !pendingLand.has(r.id)).length;
    if (runsBars.childElementCount !== runs.length) runsBars.replaceChildren(...runs.map(() => el("i")));
    runs.forEach((r, i) => {
      const b = runsBars.children[i];
      const on = i < lit;
      const cls = on ? (bump && i === lit - 1 ? "is-new" : "is-on") : "is-ghost";
      if (b.className !== cls) b.className = cls;
      const h = on ? `${Math.max(3, (r.n / max) * 26)}px` : "2px";
      if (b.style.height !== h) b.style.height = h;
      setAttr(b, "title", `${hms(r.at)}: ${plural(r.n, "must-do flight")} passed to you`);
    });
    setText(runsCap, lit ? `${lit} of ${runs.length} runs` : `${runs.length} runs in this window`);
    // the other work at the Desk, now (the Wall's own counts, not the playhead). The hero already
    // says the must-do count, so the facts do not say a second one.
    const rows = [];
    if (!ex) {
      const hp = D.handPlan;
      if (hp && hp.n) rows.push(["Flights to plan by hand", mustMode ? String(hp.n) : `${hp.n}${hp.must ? ` · ${hp.must} must do` : ""}`]);
      if (D.sra.n) rows.push(["SRA to sign", `${D.sra.n}${D.sra.names[0] ? ` · ${D.sra.names[0]}` : ""}`]);
      if (D.plan) rows.push(["Airport plan", D.plan === "by hand" ? "By hand" : "Waits for approval", D.planNote]);
      if (mustMode) rows.push(["Advisories to approve", D.drafts == null ? "unknown" : D.drafts ? String(D.drafts) : "None"]);
    }
    const factsKey = JSON.stringify(rows);
    if (facts.dataset.k !== factsKey) {
      facts.dataset.k = factsKey;
      facts.replaceChildren(...rows.map(([k, v, t]) => el("li", { title: t || null }, el("span", { text: k }), el("b", { text: v }))));
    }
    factsCap.hidden = facts.hidden = !rows.length;
    mchip.classList.toggle("is-must", mustMode);
    const shown = n == null ? "–" : String(n);
    setText(mchip, ex ? `${shown} drafts (example)` : mustMode ? `${shown} must-do` : `${shown} to approve`);
    // the button says what the hero says, a number only when there is one
    setAttr(mchip, "aria-label", `${ex ? (n == null ? "No example run yet" : `${n} example ${n === 1 ? "draft" : "drafts"}`)
      : mustMode ? (n == null ? "No must-do count yet, waiting for the first run in this window" : `${n} must-do ${n === 1 ? "flight" : "flights"} to plan by hand`)
        : n == null ? "Advisory count unknown" : `${n} ${n === 1 ? "advisory waits" : "advisories wait"} for you`}. Go to You decide`);
  }

  function rowsAt() {
    return foldRows(events.filter((e) => e.at <= simT), { example: mode === "example" });
  }
  // A row's words. A run's "N must-do to you" waits until its tokens land, as the hero does, so the
  // log and the hero never say two numbers for one run.
  const landed = (r) => !r.out || !pendingLand.has(r.out.e.id);
  function rowParts(r) {
    return [r.text, r.toYou && landed(r) ? el("span", { class: "flow-log__you", text: `, ${r.toYou}` }) : null, r.repeat ? el("span", { class: "flow-log__x", text: ` · ${r.repeat}` }) : null].filter(Boolean);
  }
  const rowSig = (r) => `${r.text}|${r.toYou && landed(r) ? r.toYou : ""}|${r.repeat || ""}|${r.tone}`;
  function rowNode(r) {
    const dot = el("i", { class: "flow-log__dot" });
    dot.style.background = colOf(r.tone);
    dot.style.color = colOf(r.tone);
    const text = el("span", { class: "flow-log__text" }, ...rowParts(r));
    const li = el("li", { title: `From the record:\n${r.raw}`, dataset: { k: r.key, s: rowSig(r) } }, el("span", { class: "flow-log__tm", text: hms(r.tm) }), dot, text);
    li.addEventListener("animationend", () => li.classList.add("is-still"), { once: true });
    return li;
  }
  // Keyed rows: a row already shown stays (its words updated in place when its run gains an outcome),
  // and only a new row slides in.
  let logMode = "";
  let liveTimer = 0;
  function renderLog(animate) {
    const rows = rowsAt().slice(-4).reverse();
    if (logMode !== mode) { logMode = mode; log.replaceChildren(); }
    const have = new Map([...log.children].map((n) => [n.dataset.k, n]));
    const nodes = rows.map((r) => {
      let n = have.get(r.key);
      if (n) {
        n.classList.add("is-still");
        const sig = rowSig(r);
        if (n.dataset.s !== sig) {
          n.dataset.s = sig;
          n.lastChild.replaceChildren(...rowParts(r));
          dotOf(n).style.background = dotOf(n).style.color = colOf(r.tone);
          n.title = `From the record:\n${r.raw}`;
        }
      } else {
        n = rowNode(r);
        if (!animate) n.classList.add("is-still");
      }
      return n;
    });
    const same = nodes.length === log.children.length && nodes.every((n, i) => log.children[i] === n);
    if (!same) log.replaceChildren(...nodes);
    const newest = rows[0];
    if (animate && newest && liveKey !== newest.key) {
      liveKey = newest.key;
      for (const n of log.children) n.classList.toggle("is-live", n === nodes[0]);
      window.clearTimeout(liveTimer);
      liveTimer = window.setTimeout(() => log.querySelector(".is-live")?.classList.remove("is-live"), 2600);
      say();
    }
  }
  const dotOf = (n) => n.querySelector(".flow-log__dot");
  // screen readers: one line at most every 10 s, the newest folded row as it stands when spoken
  let lastSaid = -1e9, sayTimer = 0;
  function say() {
    window.clearTimeout(sayTimer);
    const wait = Math.max(1200, SAY_EVERY_MS - (performance.now() - lastSaid));
    sayTimer = window.setTimeout(() => {
      const r = rowsAt().pop();
      if (!r || !isOpen) return;
      live.textContent = `${hms(r.tm)}. ${r.text}${r.toYou ? `, ${r.toYou}` : ""}.`;
      lastSaid = performance.now();
    }, wait);
  }

  // ---------------------------------------------------------------- the text equivalent
  const MAPROWS = [
    ["official", "Pink burst from an office on the map", "A read of an official product (VA SIGMET, VAA): a POLL step, or the feed's last successful read moving on. Only reads TEPHRA recorded."],
    ["observer", "Blue burst from the observatory", "A read of the observatory's notices (VONA from MAGMA, JMA), the same way."],
    ["weather", "Grey-blue particles from airports or the winds grid", "A POLL step with new records (METAR, winds). The count follows the records, capped."],
    ["aircraft", "A swarm from every aircraft into Code checks", "Aircraft positions read: the aircraft feed's last read, or a Coordinator run started by new positions."],
    ["aircraft", "A ring and a label on one flight", "An EXPOSURE step: code found the flight inside, or on its way into, an ash area."],
    ["job", "White tokens from Code checks to the Coordinator", "A Coordinator run: N items to dispatch. One token per item."],
    ["must", "Tokens stop at the closed gate, turn yellow and drop to You decide", "The Coordinator did not run (TEPHRA Assistant paused, or no result) and code passed M must-do items to the Desk. The number becomes M when they land."],
    ["info", "Hollow rings parked at the gate", "The jobs waiting in line for TEPHRA Assistant. They do not move while it is paused."],
    ["job", "A token through the gate to a skill, then on to You decide", "A hand-out from the Coordinator to that skill, then its draft reaching the Desk."],
    ["muted", "A faint afterglow on a route", "The path a real read or step just took, fading over about 3 s. Nothing glows that did not happen."],
    ["muted", "Quiet stretch, skipping ahead", "No step in the record and nothing in flight: the clock runs faster to the next real step, and says so."],
  ];
  let sheetOpener = null;
  let sheetKind = null;
  function openSheet(kind, opener, skillId = null) {
    sheetOpener = opener || document.activeElement;
    sheetKind = kind;
    if (kind === "skill") {
      const card = details && details.ready ? [details.duty, ...details.team].find((x) => x.id === skillId) : null;
      const s = skillId === "duty" ? (card ? { name: card.name, does: card.does, jobs: [], last: null } : null) : M.skills.find((x) => x.id === skillId);
      sheetH.textContent = s ? s.name : "Skill";
      const kids = [el("p", { text: s?.does || "" })];
      if (card) {
        kids.push(el("p", { class: "flow-sheet__state", text: card.word }),
          el("p", { text: `Newest: ${card.last.text}${Number.isFinite(card.last.at) ? ` · ${hms(card.last.at)}` : ""}` }));
        if (card.brief) kids.push(el("p", { text: `Brief: ${card.brief.text}` }));
        if (card.model) kids.push(el("p", { class: "flow-sheet__fine", text: card.model.text }));
        if (card.steps.length) kids.push(el("h3", { text: "Newest steps" }), el("ol", { class: "flow-sheet__steps" }, ...card.steps.map((x) => el("li", {}, el("span", { class: "flow-sheet__tm", text: x.atText || (Number.isFinite(x.at) ? hms(x.at) : "") }), el("span", { text: `${x.text}${x.count > 1 ? ` (${x.count}×)` : ""} · ${x.source}` })))));
      } else if (s?.last) kids.push(el("p", { text: `${s.last.text} · ${hms(s.last.at)}` }));
      if (s?.jobs.length) kids.push(el("h3", { text: "Waiting in line" }), el("ul", {}, ...s.jobs.map((j) => el("li", { text: j }))));
      // a skill that did not run, gave no result or waits while the assistant is paused: why is
      // one tap away, at Details › TEPHRA Assistant (8.6)
      const stalled = card && (card.state === "notrun" || card.state === "failed" || card.state === "waiting");
      if (stalled || (M.ai.kind === "paused" && s?.jobs.length)) kids.push(el("button", { type: "button", class: "flow-link", dataset: { act: "board-details", sec: "ai", focus: `board-why-${skillId}` }, text: "Why: Details › TEPHRA Assistant ›" }));
      kids.push(el("button", { type: "button", class: "flow-link", dataset: { act: "board-details", sec: "trace", focus: `board-trace-${skillId}` }, text: "Every step in How TEPHRA decided ›" }));
      sheetBody.replaceChildren(...kids);
    } else {
      sheetH.textContent = "How this moves";
      const tb = el("tbody", {}, ...MAPROWS.map(([tone, a, b]) => { const i = el("i"); i.style.background = colOf(tone); return el("tr", {}, el("td", {}, i, a), el("td", { text: b })); }));
      sheetBody.replaceChildren(
        el("p", { text: `Everything that moves stands for one real record: a step in TEPHRA's trace, a feed's last read, or the assistant's work queue. If nothing happened, nothing moves. The playback runs the ${M?.spanMin ? `last ${M.spanMin} minutes` : "latest"} of real steps the Wall holds${M?.replay ? ", on the replay clock" : ""}.` }),
        el("table", {}, el("thead", {}, el("tr", {}, el("th", { scope: "col", text: "What moves" }), el("th", { scope: "col", text: "The real record behind it" }))), tb),
        el("h3", { id: "flow-steps-h", tabindex: "-1", text: "Every step, in plain words" }),
        el("p", { text: "The same steps the board animates, as text. The steps up to the playhead are bright." }),
        el("ol", { id: "flow-steps", class: "flow-sheet__steps" }));
      renderSheetSteps();
    }
    sheet.showModal();
    renderSheetSteps();
    if (kind === "steps") { const h = $("flow-steps-h"); h?.scrollIntoView({ block: "start" }); h?.focus({ preventScroll: true }); }
    else sheetH.focus({ preventScroll: true });
  }
  // the full list is built when its rows change; during play only the bright rows move on
  function renderSheetSteps() {
    const ol = $("flow-steps");
    if (!ol || !sheet.open || sheetKind === "skill") return;
    const rows = foldRows(events, { example: mode === "example" });
    const key = `${mode}|${rows.length}|${rows.map((r) => `${r.key}:${r.items.length}`).join(",")}`;
    if (ol.dataset.k !== key) {
      ol.dataset.k = key;
      ol.replaceChildren(...rows.map((r) => el("li", { dataset: { at: String(r.at) } }, el("span", { class: "flow-sheet__tm", text: hms(r.tm) }), el("span", { text: `${r.text}${r.toYou ? `, ${r.toYou}` : ""}${r.repeat ? ` · ${r.repeat}` : ""}` }))));
    }
    for (const li of ol.children) li.classList.toggle("is-now", Number(li.dataset.at) <= simT);
  }
  sheet.addEventListener("close", () => { const back = sheetOpener; sheetOpener = null; if (back && document.contains(back)) back.focus({ preventScroll: true }); });
  sheet.addEventListener("click", (e) => { if (e.target === sheet) sheet.close(); });

  // ---------------------------------------------------------------- input
  dialog.addEventListener("click", (e) => {
    const t = e.target.closest("button");
    if (!t || !dialog.contains(t)) return;
    if (t.dataset.flowmode) {
      if (mode === t.dataset.flowmode) return;
      mode = t.dataset.flowmode;
      renderStatic();
      // Example plays the window's recorded inputs from the start, as the model would have handled
      // them; Real now goes back to the newest step
      if (mode === "example") startPlayback(T0);
      else { seek(T1); toLiveEdge(); }
      drawRails();
    } else if (t.dataset.flowsheet === "close") sheet.close();
    else if (t.dataset.flowsheet) openSheet(t.dataset.flowsheet, t);
    else if (t.dataset.flowskill) openSheet("skill", t, t.dataset.flowskill);
  });
  play.addEventListener("click", () => {
    if (following) startPlayback(T0);
    else if (!playing && simT >= T1) startPlayback(T0);
    else setPlaying(!playing);
  });
  speedBtn.addEventListener("click", () => { speed = speed === 8 ? 30 : 8; renderPlayer(); });
  mchip.addEventListener("click", () => { decide.scrollIntoView({ behavior: RM() ? "auto" : "smooth", block: "center" }); youHead.setAttribute("tabindex", "-1"); youHead.focus({ preventScroll: true }); });
  {
    let drag = false, was = false;
    const at = (ev) => { const r = track.getBoundingClientRect(); return T0 + clamp((ev.clientX - r.left - 4) / Math.max(1, r.width - 8), 0, 1) * (T1 - T0); };
    track.addEventListener("pointerdown", (ev) => { drag = true; was = playing || following; following = false; playing = false; track.setPointerCapture(ev.pointerId); seek(at(ev)); renderPlayer(); });
    track.addEventListener("pointermove", (ev) => { if (drag) seek(at(ev)); });
    track.addEventListener("pointerup", () => { if (!drag) return; drag = false; if (was && simT < T1) setPlaying(true); else if (simT >= T1) toLiveEdge(); });
    // keys step from one real step to the next: Right / Left, Home / End
    track.addEventListener("keydown", (ev) => {
      const steps = events.filter((x) => !x.quiet && x.type !== "note");
      let t = null;
      if (ev.key === "ArrowRight") t = steps.find((x) => x.at > simT + 1500)?.at ?? null;
      else if (ev.key === "ArrowLeft") { const cur = [...steps].reverse().find((x) => x.at <= simT); const prev = cur && [...steps].reverse().find((x) => x.at < cur.at - 1500); t = prev ? steps.find((x) => x.at > prev.at - 1500).at : null; }
      else if (ev.key === "Home") { ev.preventDefault(); following = false; setPlaying(false); seek(T0); renderPlayer(); return; }
      else if (ev.key === "End") { ev.preventDefault(); toLiveEdge(); return; }
      if (t == null) return;
      ev.preventDefault();
      following = false; setPlaying(false);
      seek(t - 1); stepOne(); renderPlayer();
    });
  }
  // the panel scrolls on a phone: the rails follow it at once, moving or not
  let scrollRaf = 0;
  body.addEventListener("scroll", () => {
    if (!phone || scrollRaf) return;
    scrollRaf = requestAnimationFrame(() => { scrollRaf = 0; measure(); drawRails(); });
  }, { passive: true });
  let roTimer = 0;
  new ResizeObserver(() => { window.clearTimeout(roTimer); roTimer = window.setTimeout(() => { if (isOpen) { layout(); drawStill(); kick(); } }, 60); }).observe(dialog);
  document.addEventListener("visibilitychange", () => { if (!document.hidden && isOpen) kick(); });
  reduced.addEventListener?.("change", () => { if (M) { renderPlayer(); seek(simT); } });

  // ---------------------------------------------------------------- API
  function setModel(m, d) {
    details = d || details;
    if (!m.ready) return;
    const first = !M;
    M = m;
    events = m.events;
    const wasEnd = simT >= T1 - 1;
    T0 = m.t0; T1 = m.t1;
    if (first) {
      simT = T1;
      for (const e of events) fired.add(e.id);
      // REPLAY: the board opens playing back the latest steps; live, it follows new steps
      if (m.replay && events.length) { following = false; simT = T0; nextIdx = 0; playing = true; }
    }
    if (following) {
      // steps the stream did not deliver (a reload after a lost stream) are applied with no motion
      for (const e of events) fired.add(e.id);
      simT = T1; nextIdx = events.length;
    } else {
      nextIdx = events.findIndex((e) => e.at > simT);
      if (nextIdx < 0) nextIdx = events.length;
      if (wasEnd && !playing) simT = T1;
    }
    renderStatic();
    drawMap();
    const railKey = `${m.gate.open}|${m.gate.kind}|${m.queue.length}|${m.ai.kind}|${m.desk.must > 0}`;
    if (first) { railFor = railKey; layout(); seek(simT); if (playing) setPlaying(true); }
    else {
      renderCounters(); renderLog(false); renderDecide(false); drawTrack(); renderSheetSteps();
      if (railKey !== railFor) { railFor = railKey; fitGate(); }
    }
  }
  let railFor = "";

  return {
    update(m, d, conn) {
      if (!m.ready) return;
      setModel(m, d);
      setStale(Boolean(conn?.lostAt));
    },
    // a trace step that just arrived on the stream: at the live edge it animates at once
    push(step) {
      if (!M || !isOpen || stale || !following) return;
      // a POLL step whose read the `state` stream already showed is the same read
      const near = (e) => (e.type === "feed" || e.type === "adsb") && events.some((x) => x.type === e.type && (e.type === "adsb" || x.feed === e.feed) && Math.abs(x.at - e.at) < 3000);
      const evs = stepEvents(step).filter((e) => !fired.has(e.id) && !near(e));
      if (!evs.length) return;
      let lagK = 0;
      for (const e of evs) {
        fired.add(e.id);
        events = [...events, e].sort((a, b) => a.at - b.at);
        e.lag = lagK++ * STAGGER_MS;
        if (e.at > T1) T1 = e.at;
        simT = T1;
        // the Coordinator writes a hand-out's line after the skill's own steps (board.js
        // handoffsFirst): when that work has already moved, the hand-out is a log row only, never a
        // token that would reach the skill after its work
        if (e.type === "handoff" && workMovedFor(e)) { pulse("coord", C.job); continue; }
        if (!e.quiet || e.type === "adsb") fire(e);
      }
      renderCounters(); renderLog(true); renderDecide(false); drawTrack();
      kick();
    },
    // a feed's last successful read moved on the `state` stream
    pushRead(read) {
      if (!M || !isOpen || stale || !following) return;
      const at = Date.parse(read.at);
      const e = readEvent(read.feed, read.n, at);
      if (fired.has(e.id) || !Number.isFinite(at)) return;
      // a POLL step (or a run started by new aircraft) for the same read is already on the board
      if (events.some((x) => (read.feed === "adsb" ? x.type === "adsb" : x.feed === read.feed) && Math.abs(x.at - at) < 3000)) return;
      fired.add(e.id);
      events = [...events, e].sort((a, b) => a.at - b.at);
      if (at > T1) T1 = at;
      simT = T1;
      fire(e);
      renderCounters(); renderLog(true); drawTrack();
      kick();
    },
    open() {
      isOpen = true;
      loadLand().then(() => { mapKey = ""; if (isOpen) { drawMap(); drawStill(); } });
      requestAnimationFrame(() => { layout(); if (M) seek(following ? T1 : simT); kick(); });
    },
    close() {
      isOpen = false;
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
      if (sheet.open) sheet.close();
      // next time it opens on real data, at the live edge or (REPLAY) from the start of the window
      M = null; fired.clear(); following = true; playing = false; mode = "real"; legendFor = ""; logMode = "";
    },
  };

  function setStale(lost) {
    if (lost === stale) return;
    stale = lost;
    dialog.classList.toggle("is-stale", stale);
    staleNote.hidden = !stale;
    if (isOpen) live.textContent = stale ? staleNote.textContent : "Live updates are back.";
    if (stale) { if (raf) cancelAnimationFrame(raf); raf = 0; }
    else kick();
  }
}
