// "TEPHRA Assistant at work" (docs/UI-DESIGN.md 7.21, 7.27): the flow board, the page /assistant
// (the Wall's page with <dialog id="board"> shown in place of the Wall, never modal), reached from
// the demo side panel's pop-out icon, the Guide or /#ai-at-work. A live map of the region (MapLibre on
// the night basemap: drag, zoom, click a plane, a volcano, an ash area or a feed for what it is) with the snapshot's real ash areas, volcanoes,
// airports and aircraft, a beacon where each feed comes from, and one glass panel, "Inside TEPHRA": Code checks,
// the Coordinator, the model gate with its waiting jobs, the six skills and "You decide". Work moves
// only for real records (flowModel in board.js): a trace step that arrives on the stream animates at
// once (push), and the player plays back the latest steps the Wall holds, scrubbable. Every string
// goes in through el() (textContent); dynamic colours and positions are set through the CSSOM.
// Two canvases over the map: the rails (the panel's spine, the gate and its waiting jobs), redrawn on
// a resize, a scroll or a change of state; and the effects, cleared and drawn per frame while
// something moves. Effects read map positions every frame, so they follow the map as it pans. The
// loop stops when nothing moves.

import { $, el, icon, fl, airline } from "./util.js";
import { flowAt, foldRows, readEvent, stepEvents, hmsOf as hms, STAGGER_MS, TOOL_SKILLS, HELPERS, FEED_KIND, FEED_NAMES, RESULT, resultKind } from "./board.js";
import { STYLE_URL, nightBasemap, nightColours, symbolColours } from "./basemap.js";
import { addImages } from "./images.js";
import { infoButton } from "./info.js";
import { codeMark, templateText, stateLine } from "./x-parts.js";

// You decide's rule, behind its (i) on the demo's tab, the /assistant board and the Details foot
export const YOU_DECIDE = "Drafts wait at the Desk for a dispatcher. Nothing leaves TEPHRA until a dispatcher approves.";

// ---------------------------------------------------------------- the Code checks sheet
// What "N feed reads · M flight alerts" are: one card per source, one row per flagged flight.
const KIND_NAME = { official: "Official", observer: "Observatory", aircraft: "Aircraft", weather: "Weather", satellite: "Satellite" };
const KIND_ORDER = ["official", "observer", "aircraft", "weather", "satellite"];

function checksSheet(evs, colOf) {
  const reads = new Map();
  const flights = new Map();
  for (const e of evs) {
    if (e.type === "feed" || e.type === "adsb") {
      const feed = e.feed || "adsb";
      const r = reads.get(feed) || { feed, kind: FEED_KIND[feed] || "weather", n: 0, at: 0 };
      r.n += 1;
      r.at = Math.max(r.at, e.at);
      reads.set(feed, r);
    } else if (e.type === "flight") {
      const f = flights.get(e.flight) || { n: 0 };
      flights.set(e.flight, { ...e, n: f.n + 1 });
    }
  }
  const nReads = [...reads.values()].reduce((n, r) => n + r.n, 0);
  const nAlerts = [...flights.values()].reduce((n, f) => n + f.n, 0);
  const kids = [
    el("div", { class: "ss-head" }, el("span", { class: "ss-pill" }, el("i"), "Code only"), el("span", { class: "ss-does", text: "Reads every source and flags flights near the ash." })),
    el("div", { class: "ss-stats ss-stats--2" },
      el("div", { class: "ss-stat" }, el("b", { text: String(nReads) }), el("span", { text: nReads === 1 ? "feed read" : "feed reads" })),
      el("div", { class: "ss-stat" }, el("b", { text: String(nAlerts) }), el("span", { text: `flight alerts · ${flights.size} ${flights.size === 1 ? "flight" : "flights"}` }))),
  ];
  const cards = [...reads.values()].sort((a, b) => KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind) || b.n - a.n);
  if (cards.length) {
    kids.push(el("h3", { text: "Sources read" }), el("ul", { class: "ck-grid" }, ...cards.map((r) => {
      const dot = el("i", { class: "ck-dot" });
      dot.style.background = colOf(r.kind);
      return el("li", { class: "ck-card" },
        el("span", { class: "ck-card__top" }, dot, el("span", { class: "ck-card__kind", text: KIND_NAME[r.kind] || r.kind })),
        el("span", { class: "ck-card__name", text: FEED_NAMES[r.feed] || r.feed }),
        el("span", { class: "ck-card__foot" }, el("b", { text: String(r.n) }), el("span", { text: r.n === 1 ? "read" : "reads" }), el("span", { class: "ck-card__at", title: "Last read", text: hms(r.at) })));
    })));
  }
  const rows = [...flights.values()].sort((a, b) => (a.inside ? -1 : a.mins) - (b.inside ? -1 : b.mins));
  if (rows.length) {
    kids.push(el("h3", { text: "Flights flagged, most urgent first" }), el("ul", { class: "ss-jobs" }, ...rows.map((f) => {
      const soon = f.inside || f.mins <= 15;
      return el("li", { class: "ss-job ck-flight" },
        el("span", { class: "ss-job__flight", text: f.flight }),
        el("span", { class: "ss-job__what", text: [f.vol, f.fl].filter(Boolean).join(" · ") }),
        f.n > 1 ? el("span", { class: "ss-count", text: `×${f.n}` }) : el("span"),
        el("span", { class: `ss-mins${soon ? " is-soon" : ""}`, text: f.inside ? "inside now" : `${f.mins} min` }));
    })));
  }
  if (!cards.length && !rows.length) kids.push(el("p", { text: "Nothing read yet in this window." }));
  return kids;
}

// A code template's line: the "{ }" mark and the line without its "(code only)" words (the AI
// status says the state once; owner, 17 Oct: "don't say no model everywhere").
function markedText(text) {
  const t = templateText(text);
  return t.code ? [codeMark(), " ", t.text] : [t.text];
}
const stepText = (cls, text) => el("span", { class: cls }, ...markedText(text));

// ---------------------------------------------------------------- one skill's sheet
// Glance first: its state, three counts, the job it is on, then the queue by urgency and the
// newest results, each with a word and a shape for how it went (never colour alone).
const SHEET_TONE = { working: "info", waiting: "caution", queued: "muted", failed: "caution", notrun: "caution", done: "ok", quiet: "muted" };
const JOB = /^Plan (\S+) \(([^)]+)\): (.+)$/;
const plainCase = (text) => (/[a-z]/.test(text) ? text : text.charAt(0) + text.slice(1).toLowerCase());
const jobMinutes = (where) => (/inside/i.test(where) ? 0 : Number((where.match(/in (\d+) min/) || [])[1] ?? Infinity));

function jobRow(label) {
  const m = label.match(JOB);
  if (!m) return el("li", { class: "ss-job" }, el("span", { class: "ss-job__what", text: label }));
  const [, flight, volcano, where] = m;
  const min = jobMinutes(where);
  const soon = min <= 15;
  return el("li", { class: "ss-job" },
    el("span", { class: "ss-job__flight", text: flight }),
    el("span", { class: "ss-job__what", text: volcano }),
    el("span", { class: `ss-mins${soon ? " is-soon" : ""}`, text: min === 0 ? "inside now" : Number.isFinite(min) ? `${min} min` : where }));
}

function skillSheet(card, s, skillId, paused) {
  const kids = [];
  const state = card?.state || (s?.jobs.length ? "waiting" : "quiet");
  kids.push(el("div", { class: "ss-head" },
    el("span", { class: `ss-pill ss-pill--${SHEET_TONE[state] || "muted"}` }, el("i"), card?.word || (s?.jobs.length ? "Waiting in line" : "Quiet")),
    el("span", { class: "ss-does", text: s?.does || "" })));

  const steps = card?.steps || [];
  const nowStep = steps.find((x) => x.now && x.tone === "working");
  const past = steps.filter((x) => !x.now);
  const sum = (...kinds) => past.filter((x) => kinds.includes(resultKind(x))).reduce((n, x) => n + (x.count || 1), 0);
  const inLine = s?.jobs.length || 0;
  kids.push(el("div", { class: "ss-stats" },
    el("div", { class: "ss-stat" }, el("b", { text: String(inLine) }), el("span", { text: "in line" })),
    el("div", { class: "ss-stat ss-stat--ok" }, el("b", { text: String(sum("ok")) }), el("span", { text: "done" })),
    el("div", { class: `ss-stat${sum("failed", "caution", "rejected") ? " ss-stat--caution" : ""}` }, el("b", { text: String(sum("failed", "caution", "rejected")) }), el("span", { text: "not accepted" }))));

  if (nowStep) {
    const label = nowStep.text.replace(/^Running now: /, "").replace(/ and \d+ more jobs?$/, "");
    kids.push(el("div", { class: "ss-now" }, el("span", { class: "ss-now__k" }, el("i"), "Working on"), el("ul", { class: "ss-jobs" }, jobRow(label))));
  }
  if (card?.brief) kids.push(el("blockquote", { class: "ss-brief", text: card.brief.text }));

  if (inLine) {
    const jobs = [...s.jobs].sort((a, b) => jobMinutes((a.match(JOB) || [])[3] || "") - jobMinutes((b.match(JOB) || [])[3] || ""));
    kids.push(el("h3", { text: "In line, most urgent first" }), el("ul", { class: "ss-jobs" }, ...jobs.map(jobRow)));
  }

  if (past.length) {
    kids.push(el("h3", { text: "Newest results" }), el("ol", { class: "ss-results" }, ...past.map((x) => {
      const [tone, ic, word] = RESULT[resultKind(x)] || RESULT.info;
      return el("li", { class: "ss-result", title: x.source },
        el("span", { class: "flow-sheet__tm", text: x.atText || (Number.isFinite(x.at) ? hms(x.at) : "") }),
        el("span", { class: `ss-badge ss-badge--${tone}` }, icon(ic), word),
        stepText("ss-result__text", plainCase(x.text)),
        x.count > 1 ? el("span", { class: "ss-count", text: `×${x.count}` }) : null);
    })));
  } else if (s?.last) kids.push(el("p", {}, ...markedText(s.last.text), ` · ${hms(s.last.at)}`));

  const links = [];
  const stalled = card && (card.state === "notrun" || card.state === "failed" || card.state === "waiting");
  if (stalled || (paused && inLine)) links.push(el("button", { type: "button", class: "flow-link", dataset: { act: "board-details", sec: "ai", focus: `board-why-${skillId}` }, text: "Why ›" }));
  links.push(el("button", { type: "button", class: "flow-link", dataset: { act: "board-details", sec: "trace", focus: `board-trace-${skillId}` }, text: "Every step ›" }));
  kids.push(el("div", { class: "ss-foot" }, el("span", { class: "ss-links" }, ...links), card?.model?.text ? el("span", { class: "ss-model", text: card.model.text }) : null));
  return kids;
}

const ARROWS = ["→", "↘", "↓", "↙", "←", "↖", "↑", "↗"];
// Where each feed comes from: the office or source that issues it (lon, lat). The SIGMET beacon sits
// on the SIGMETs in force when there are any; METAR at the airports; winds on the grid; ADS-B at
// every aircraft. The demo's catch-up starts its pulses at the same places (assist-panel.js).
export const SRC = {
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
// the optional feature each skill's card is shown under (board.js HELPERS)
const FEATURE_OF = Object.fromEntries(HELPERS.map((h) => [h.id, h.feature || null]));
const TOKEN_SPEED = 190; // px per second down the spine
const MAX_P = 160, MAX_TR = 90, MAX_TK = 40;
const SPEEDS = [8, 30, 60, 120]; // the speed button steps through these
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

// a circle of radius nm around [lon, lat] as a ring (the aircraft feed's query circles)
function circleRing(lon, lat, nm) {
  const r = nm / 60, k = Math.cos((lat * Math.PI) / 180) || 1;
  return Array.from({ length: 49 }, (_, i) => { const t = (i / 48) * 2 * Math.PI; return [lon + (r * Math.cos(t)) / k, lat + r * Math.sin(t)]; });
}
const fc = (features) => ({ type: "FeatureCollection", features });
const poly = (rings, properties = {}) => ({ type: "Feature", properties, geometry: { type: "Polygon", coordinates: rings } });
const pt = (at, properties = {}) => ({ type: "Feature", properties, geometry: { type: "Point", coordinates: at } });
const CODE_WORD = { RED: "Red", ORANGE: "Orange", YELLOW: "Yellow", GREEN: "Green", UNKNOWN: "Unknown" };
// the board's map layers a viewer can switch off (the Layers menu)
const MAP_LAYERS = [
  ["ash", "Ash areas", ["b-official-fill", "b-official-line", "b-tephra"]],
  ["aircraft", "Aircraft", ["b-aircraft"]],
  ["airports", "Airports", ["b-airports"]],
  ["feeds", "Where feeds come from", []],
  ["coverage", "Aircraft feed coverage", ["b-adsb"]],
];

// ------------------------------------------------------------------ Inside TEPHRA (one renderer)
// The pipeline as a drawn spine, the one diagram the /assistant board's glass panel and the demo's
// Assistant tab both draw (wall/assist-panel.js): Code checks (no AI, its feed reads and flight
// alerts), the Coordinator, the model gate with the jobs waiting in line, each skill with its state,
// "When you ask" and You decide (the count, its reason, the run bars). mountInside builds it once;
// its caller hands it the model, the events up to its playhead and whether Example is on. The spine
// and the gate are drawn by drawInside on the caller's rails canvas, from the anchors measure()
// reads. `side`: the demo's tab, where a row opens its Details section (the board opens its own
// sheets), the Desk's button is the panel's pinned foot (the demo's one filled button), and the
// Desk's other counts stay on the Desk.

// the colours the canvases draw with, read from the page's tokens (tokens.css holds every value).
// `scope`: the element whose tokens to read; mapColours() reads the night map's, for marks that
// start on the map (it stays dark in both themes).
export function insideColours(scope = document.documentElement) {
  const css = getComputedStyle(scope);
  const tok = (name) => (css.getPropertyValue(name) || "").trim();
  return {
    official: tok("--c-official"), officialText: tok("--c-official-text"), observer: tok("--c-observer"),
    weather: tok("--c-info"), aircraft: tok("--c-aircraft"), satellite: tok("--c-info"),
    job: tok("--c-text-1"), must: tok("--c-caution"), tephra: tok("--c-tephra"), info: tok("--c-info"),
    text2: tok("--c-text-2"), text3: tok("--c-text-3"), line2: tok("--c-line-2"), muted: tok("--c-text-3"),
    bg: tok("--c-bg"), s1: tok("--c-surface-1"), s2: tok("--c-surface-2"),
  };
}

export const mapColours = () => insideColours(document.querySelector(".map-pane.night") || document.documentElement);

function setMark(useHost, sym) {
  const u = useHost.querySelector("use");
  const href = `${u.getAttribute("href").split("#")[0]}#${sym}`;
  setAttr(u, "href", href);
}

// Rows a page leaves out of Inside TEPHRA: a hosted airline's map has no recovery row (D15).
let SKIPPED = [];
export function skipInsideRows(ids) { SKIPPED = [...ids]; }

export function mountInside({ has, side = false }) {
  const shown = (id) => !FEATURE_OF[id] || has(FEATURE_OF[id]);
  const listed = (id) => !SKIPPED.includes(id) && shown(id);
  // a row's action: the board opens its sheet; the demo's tab opens the Details section
  const rowAct = (sheet) => (side ? { act: "board-details", sec: sheet === "checks" ? "feeds" : "ai" } : sheet === "checks" ? { flowsheet: "checks" } : { flowskill: sheet });
  const node = (cls, a, kid = null) => el("span", { class: `flow-node ${cls}`, dataset: { a } }, kid);
  const cFeeds = el("b", { text: "0" }), cFlights = el("b", { text: "0" });
  const wFeeds = el("span", { text: " feed reads · " }), wFlights = el("span", { text: " flight alerts" });
  const coordMark = icon("ta-waiting", "flow-node__mark");
  const coordMeta = el("span", { class: "flow-row__meta" });
  const coordRight = el("span", { class: "flow-row__right" });
  const coordBtn = el("button", { type: "button", class: "flow-row__btn", dataset: rowAct("duty") }, el("span", { class: "flow-row__name", text: "Coordinator" }), coordMeta);
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
    const btn = el("button", { type: "button", class: "flow-skill__btn", dataset: rowAct(id) }, name, state);
    const li = el("li", { class: "flow-skill" }, el("span"), dot, btn);
    skillEls[id] = { li, dot, name, state, btn };
    skillList.append(li);
  }
  const onreqDot = el("span", { class: "flow-dot flow-dot--small", dataset: { a: "sk-onreq" } });
  const onreqName = el("span", { class: "flow-skill__name" });
  skillList.append(el("li", { class: "flow-skill flow-skill--onreq" }, el("span"), onreqDot, onreqName));
  const heroN = el("span", { class: "flow-hero__n", text: "–" });
  const heroW = el("span", { class: "flow-hero__w" });
  const who = el("p", { class: "flow-who" });
  const runsCap = el("span");
  const runsBars = el("div", { class: "flow-runs__bars", "aria-hidden": "true" });
  // the caption is the bars' hover and screen-reader text: the hero says the must-do count once
  const runsBox = el("div", { class: "flow-runs" }, el("p", { class: "flow-runs__cap sr-only" }, el("span", { text: "Must-do passed to you, each run" }), runsCap), runsBars);
  const facts = el("ul", { class: "flow-facts" });
  const factsCap = el("p", { class: "flow-facts__cap", text: "At the Desk now" });
  const youId = side ? "assist-you" : "flow-you";
  const youHead = el("h3", { id: youId, class: "flow-you__eyebrow", text: "You decide" });
  // the count and its words on one line; the rule (never removed) one tap away behind the (i)
  // (owner, 17 Oct: "you can hide this in a info icon or something")
  const decide = el("section", { class: "flow-you", "aria-labelledby": youId },
    el("div", { class: "flow-you__head" }, node("flow-node--you", "you"), youHead,
      infoButton({ topic: "you-decide", label: "About You decide", text: YOU_DECIDE, above: true })),
    el("p", { class: "flow-hero" }, heroN, heroW), who,
    runsBox,
    ...(side ? [] : [factsCap, facts,
      el("a", { class: "flow-cta", href: "/desk", dataset: { focus: "board-desk" } }, el("span", { text: "Open the Desk" }), el("span", { "aria-hidden": "true", text: "→" })),
      el("button", { type: "button", class: "flow-link", dataset: { act: "board-details", sec: "ai", focus: "board-ai-home" }, text: "Details › TEPHRA Assistant ›" })]));
  const codeRow = el("div", { class: "flow-row flow-row--code" }, node("flow-node--code", "code"),
    el("button", { type: "button", class: "flow-row__btn flow-row__txt", dataset: rowAct("checks"), "aria-label": side ? "Code checks: what was read and which flights were flagged. Details › Data feeds" : "Code checks: what was read and which flights were flagged" },
      el("span", { class: "flow-row__name", text: "Code checks" }),
      el("span", { class: "flow-row__meta flow-ctr" }, cFeeds, wFeeds, cFlights, wFlights)));
  const panel = el(side ? "section" : "aside", { class: `flow-panel${side ? " flow-panel--side" : ""}`, "aria-label": "Inside TEPHRA" },
    el("p", { class: "flow-eyebrow", text: "Inside TEPHRA" }),
    codeRow, el("div", { class: "flow-gap1" }),
    coordRow, gap2, gateRow, skillList, decide);
  // the rows a step lights: each node's row (the catch-up's highlight, wall/assist-panel.js)
  const rowOf = { code: codeRow, coord: coordRow, gate: gateRow, you: decide, "sk-onreq": onreqDot.parentElement };
  for (const id of SKILL_ROWS) rowOf[`sk-${id}`] = skillEls[id].li;

  // the words: the state now (the model's), the same in Real and Example except where Example says so.
  // `cu`: the demo's catch-up (assist.js catchupSkills), each skill's row as of the beat playing
  function renderStatic(M, ex, cu = null) {
    for (const [id, r] of Object.entries(skillEls)) if (r.li.hidden === listed(id)) r.li.hidden = !listed(id);
    const onreq = HELPERS.filter((h) => h.role === "desk" && listed(h.id)).map((h) => h.name).join(" · ");
    setText(onreqName, `When you ask: ${onreq}`);
    // the demo's tab leaves the on-request skills to Details › TEPHRA Assistant (one line less)
    if (side && !onreqName.parentElement.hidden) onreqName.parentElement.hidden = true;
    setMark(coordMark, ex ? "ta-working" : M.ai.symbol);
    setText(gateName, ex ? "AI model · open" : M.gate.name);
    setText(gateMeta, ex ? "jobs go straight through" : M.gate.meta);
    // with no model the gate says nothing: the one AI status says it
    const bare = !gateName.textContent && !gateMeta.textContent;
    gateRow.classList.toggle("is-bare", bare);
    // no words and no gate to show: the band between Coordinator and the skills closes up, so no
    // lone dash is left there (UX verify, 17 Oct)
    panel.classList.toggle("is-gate-bare", bare && M.gate.kind === "nomodel" && !ex);
    // what waits and where the cause is; why the assistant is paused is said at its home (8.6)
    setAttr(gateRow, "title", ex || (!M.queue.length && !M.gate.title) ? null : [M.queue.length ? `Waiting in line:\n${M.queue.map((w) => `• ${w.label}`).join("\n")}` : null, M.gate.title || null].filter(Boolean).join("\n"));
    setText(coordMeta, ex ? "Orders the jobs and hands them to skills" : M.coord.meta);
    coordMeta.hidden = !coordMeta.textContent;
    const more = side ? "Details › TEPHRA Assistant" : "Details";
    setAttr(coordBtn, "aria-label", `Coordinator${ex ? ": orders the jobs and hands them to skills" : M.coord.meta ? `: ${M.coord.meta}` : ""}. ${more}`);
    for (const s of M.skills) {
      const r = skillEls[s.id];
      if (!r) continue;
      setText(r.name, s.name);
      if (cu && !ex) { catchupRow(r, s, cu[s.id], more); continue; }
      r.li.classList.remove("is-running");
      const inLine = !ex && s.inLine;
      const failed = !ex && s.last?.failed;
      const stateKey = inLine ? `in:${s.inLine}` : failed ? "failed" : ex ? "ex" : s.last ? `last:${s.last.at}` : "idle";
      if (r.state.dataset.k !== stateKey) {
        r.state.dataset.k = stateKey;
        r.state.replaceChildren(...(inLine ? [el("i", { class: "flow-ring" }), `${s.inLine} in line`] : failed ? ["no result"] : ex ? [] : [s.last ? hms(s.last.at) : "idle"]));
      }
      r.li.classList.toggle("is-idle", !inLine && !failed && !ex && !s.last);
      r.dot.classList.toggle("is-wait", Boolean(inLine));
      setAttr(r.btn, "aria-label", `${s.name}: ${inLine ? `${s.inLine} ${s.inLine === 1 ? "job waits" : "jobs wait"} in line` : failed ? "its newest step gave no result" : s.last ? `newest step ${hms(s.last.at)}` : "nothing in the newest steps"}. ${more}`);
      setAttr(r.btn, "title", [s.does, s.last ? `${templateText(s.last.text).text} · ${hms(s.last.at)}` : null, inLine ? `In line: ${s.jobs.join("; ")}` : null].filter(Boolean).join("\n"));
    }
  }

  // one skill's row in the catch-up: the state the recorded steps give it at the beat playing
  function catchupRow(r, s, c, more) {
    const st = c?.state || "idle";
    const stateKey = `cu:${st}:${c?.at ?? ""}:${c?.n ?? ""}`;
    if (r.state.dataset.k !== stateKey) {
      r.state.dataset.k = stateKey;
      // a time alone says when it last ran (the row's label says done or newest step)
      const words = { inline: `${c?.n} in line`, running: "running", done: hms(c?.at), noresult: "no result", last: hms(c?.at), idle: "idle" }[st];
      r.state.replaceChildren(...(st === "inline" || st === "running" ? [el("i", { class: "flow-ring" }), words] : [words]));
    }
    r.li.classList.toggle("is-idle", st === "idle");
    r.li.classList.toggle("is-running", st === "running");
    r.dot.classList.toggle("is-wait", st === "inline");
    const said = { inline: `${c?.n} ${c?.n === 1 ? "job waits" : "jobs wait"} in line`, running: "running", done: `done at ${hms(c?.at)}`, noresult: "its step gave no result", last: `newest step ${hms(c?.at)}`, idle: "nothing in the steps before" }[st];
    setAttr(r.btn, "aria-label", `${s.name}, replay catching up: ${said}. ${more}`);
  }

  // the counters at a playhead: every event at or before `t`
  function renderCounters(events, t) {
    const S = flowAt(events, t);
    setText(cFeeds, S.feeds); setText(wFeeds, S.feeds === 1 ? " feed read · " : " feed reads · ");
    setText(cFlights, S.flights); setText(wFlights, S.flights === 1 ? " flight alert" : " flight alerts");
    // a run the model refused called no model: it is "not run", never "last run" (Q4)
    setText(coordRight, S.coordAt ? `${S.coordRefused ? "not run" : "last run"} ${hms(S.coordAt)}` : "");
  }

  // the hero: M of the newest refused run at the playhead (tokens still on their way do not count
  // until they land), or, while the assistant works, the drafts that wait at the Desk now. Returns
  // what it said, for the board's chip.
  function renderDecide(M, { ex = false, events, t, pending = new Set(), exState = null, bump = false, rm = false, note = null }) {
    const D = M.desk;
    const done = events.filter((e) => e.at <= t && !pending.has(e.id));
    const S = flowAt(done, t);
    const mustMode = !ex && (S.must != null || M.ai.kind === "paused");
    let n, words;
    if (ex) { n = exState?.run ? exState.drafts : null; words = n === 1 ? "advisory draft to approve" : "advisory drafts to approve"; }
    else if (mustMode) { n = S.must; words = n === 1 ? "must-do flight to plan by hand" : "must-do flights to plan by hand"; }
    else { n = D.drafts; words = n === 1 ? "advisory waits for you" : "advisories wait for you"; }
    const before = heroN.textContent;
    setText(heroN, n == null ? "–" : String(n));
    heroN.classList.toggle("is-none", n == null);
    setText(heroW, words);
    if (bump && (before !== heroN.textContent || note) && !rm) { heroN.classList.add("is-bump"); window.setTimeout(() => heroN.classList.remove("is-bump"), 320); }
    decide.classList.toggle("is-must", mustMode);
    // the catch-up's note is the player's beat line on the demo's tab: said there, not twice
    const whoText = (side ? null : note) || (ex ? (exState?.run ? "" : "No run in this window yet.")
      : n == null && !mustMode ? "Advisory count unknown (database error)." : "");
    setAttr(heroN, "title", mustMode && S.mustAt == null ? "Waiting for the first run in this window" : mustMode ? `Run ${hms(S.mustAt)}` : null);
    setText(who, whoText);
    if (who.hidden !== !whoText) who.hidden = !whoText;
    // run bars: one per refused run in the window, lit up to the playhead
    const runs = M.runs.filter((e) => e.type === "refused");
    runsBox.hidden = ex || !runs.length;
    const max = Math.max(1, ...runs.map((r) => r.n));
    const doneIds = new Set(done.map((e) => e.id));
    const lit = runs.filter((r) => doneIds.has(r.id)).length;
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
    setAttr(runsBars, "title", `Must-do passed to you, each run · ${runsCap.textContent}`);
    // the other work at the Desk, now (the Wall's own counts, not the playhead). The hero already
    // says the must-do count, so the facts do not say a second one. The demo's tab leaves them to
    // the Desk.
    const rows = [];
    if (!ex && !side) {
      const hp = D.handPlan;
      if (hp && hp.n) rows.push(["Flights with no draft", mustMode ? String(hp.n) : `${hp.n}${hp.must ? ` · ${hp.must} must do` : ""}`]);
      if (D.sra.n) rows.push(["SRA to sign", `${D.sra.n}${D.sra.names[0] ? ` · ${D.sra.names[0]}` : ""}`]);
      if (D.plan) rows.push(["Airport plan", D.plan === "by hand" ? "By hand" : "Waits for approval", D.planNote]);
      if (mustMode) rows.push(["Advisories to approve", D.drafts == null ? "unknown" : D.drafts ? String(D.drafts) : "None"]);
    }
    const factsKey = JSON.stringify(rows);
    if (facts.dataset.k !== factsKey) {
      facts.dataset.k = factsKey;
      facts.replaceChildren(...rows.map(([k, v, tt]) => el("li", { title: tt || null }, el("span", { text: k }), el("b", { text: v }))));
    }
    factsCap.hidden = facts.hidden = !rows.length;
    return { n, mustMode };
  }

  // Every node's centre relative to `origin` (a DOMRect), and the spine's and gate's points.
  function measure(origin, M) {
    const A = {};
    for (const n of panel.querySelectorAll("[data-a]")) {
      if (n.closest("[hidden]")) continue; // a hidden feature's card has no place on the rails
      const r = n.getBoundingClientRect();
      A[n.dataset.a] = { x: r.left - origin.left + r.width / 2, y: r.top - origin.top + r.height / 2 };
    }
    if (!A.code || !A.you || !A.gate) return A;
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
    return A;
  }

  // The jobs waiting at a closed gate stack upward from it; the gap above the gate grows so the stack
  // (and a token knocking on top of it) never reaches the Coordinator's words. `remeasure` measures
  // again (the caller's anchors), `origin` is the caller's frame.
  let gapFor = -1;
  function fitGate(M, remeasure, origin) {
    const k = M && !M.gate.open ? Math.min(6, M.queue.length) : 0;
    if (k !== gapFor) { gapFor = k; gap2.style.height = ""; }
    let A = remeasure();
    if (!A.gate || !k) return A;
    const coordBottom = coordRow.getBoundingClientRect().bottom - origin().top;
    const top = A.gate.y - 13 - k * 11 - 8;
    if (top < coordBottom + 4) {
      gap2.style.height = `${gap2.getBoundingClientRect().height + (coordBottom + 4 - top)}px`;
      A = remeasure();
    }
    return A;
  }

  function lightSkill(id) {
    const d = skillEls[id]?.dot;
    if (!d) return;
    d.classList.add("is-lit");
    window.setTimeout(() => d.classList.remove("is-lit"), 700);
  }

  return { panel, decide, youHead, skillEls, onreqDot, rowOf, renderStatic, renderCounters, renderDecide, measure, fitGate, lightSkill };
}

function railCurve(c, p, q, noMove) {
  const dy = q[1] - p[1];
  if (!noMove) c.moveTo(p[0], p[1]);
  c.bezierCurveTo(p[0], p[1] + dy * 0.55, q[0], q[1] - dy * 0.55, q[0], q[1]);
}

// The spine and the gate on a rails canvas: code -> Coordinator -> the code lane down to you
// (caution toward you while must-do work goes that way); the AI lane through the gate and the
// skills (dashed with no model: the skills are code templates); the jobs waiting in line parked in
// front of a closed gate. `open` is the gate as drawn now.
export function drawInside(c, A, M, { C, ex = false, open, VW, VH, DPR }) {
  c.setTransform(DPR, 0, 0, DPR, 0, 0);
  c.clearRect(0, 0, VW, VH);
  if (!A.code || !A.you || !A.gate || !M) return;
  const sp = A.spine, code = A.code, coord = A.coord, you = A.you;
  c.lineCap = "round";
  const toYou = !ex && (M.ai.kind === "paused" || M.desk.must > 0);
  const grd = c.createLinearGradient(0, code.y, 0, you.y);
  grd.addColorStop(0, rgba(C.info, 0.45)); grd.addColorStop(0.4, rgba(C.info, 0.32));
  grd.addColorStop(1, toYou ? rgba(C.must, 0.45) : rgba(C.info, 0.3));
  c.strokeStyle = grd; c.lineWidth = 1.5;
  c.beginPath(); c.moveTo(sp, code.y + 13); c.lineTo(sp, coord.y - 13); c.moveTo(sp, coord.y + 13); c.lineTo(sp, you.y - 13); c.stroke();
  const nomodel = !ex && M.gate.kind === "nomodel";
  c.strokeStyle = open && !nomodel ? rgba(C.job, 0.36) : rgba(C.info, 0.26); c.lineWidth = 1.5;
  if (nomodel) c.setLineDash([4, 4]);
  c.beginPath();
  railCurve(c, [sp, coord.y + 8], [A.rail, A.gateIn.y]); c.lineTo(A.rail, A.gate.y);
  c.moveTo(A.rail, A.gateOut.y); c.lineTo(A.rail, A.railEnd.y);
  railCurve(c, [A.rail, A.railEnd.y], [sp, A.merge.y], true);
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
  } else if (!nomodel) {
    // open: the bar split in two. No model: no gate is drawn at all (the dashed rail and the one AI
    // status say it; a lone "- -" read as a stray glyph, UX verify 17 Oct)
    c.strokeStyle = rgba(C.job, 0.5); c.lineWidth = 2;
    c.beginPath(); c.moveTo(g.x - 11, g.y); c.lineTo(g.x - 5, g.y); c.moveTo(g.x + 5, g.y); c.lineTo(g.x + 11, g.y); c.stroke();
  }
}

// ------------------------------------------------------------------ the board

// `has` is the Wall's feature predicate (wall/features.js), handed in so the view imports nothing
// that holds the Wall's state (tests/test_wall_board.py).
export function mountFlow(dialog, { has }) {
  const body = $("board-body");
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  const RM = () => reduced.matches;
  const C = insideColours();
  const colOf = (tone) => C[tone] || C.text3;

  // ---------------------------------------------------------------- DOM, built once
  const glDiv = el("div", { class: "flow-map__gl" });
  const labels = el("div", { class: "flow-labels", "aria-hidden": "true" });
  const pick = el("div", { class: "flow-pick", role: "status", hidden: true });
  // the map's own controls, over its free part: zoom, back to the whole area, and the layers
  // the Wall map's control look (.tool): an icon that names itself on hover and focus
  const ctlBtn = (label, ic, act) => el("button", { type: "button", class: "tool", dataset: { flowmap: act } }, icon(ic), el("span", { class: "tool__tip", text: label }));
  const layerMenu = el("div", { class: "flow-layers", id: "flow-layers", role: "group", "aria-label": "Map layers", hidden: true },
    ...MAP_LAYERS.map(([id, label]) => el("label", { class: "flow-layers__row" }, el("input", { type: "checkbox", checked: true, dataset: { flowlayer: id } }), el("span", { text: label }))));
  const layersBtn = el("button", { type: "button", class: "tool", "aria-expanded": "false", "aria-controls": "flow-layers", dataset: { flowmap: "layers" } }, icon("i-layers"), el("span", { class: "tool__tip", text: "Map layers" }));
  const ctl = el("div", { class: "flow-ctl", role: "toolbar", "aria-label": "Map view", "aria-orientation": "vertical" },
    el("div", { class: "tool-grp" }, ctlBtn("Zoom in", "i-plus", "in"), ctlBtn("Zoom out", "i-minus", "out")),
    ctlBtn("Back to the whole area", "i-frame", "fit"), layersBtn, layerMenu);
  const mapWrap = el("div", { class: "flow-map", role: "region", "aria-label": "Map of the area: drag to move, scroll or pinch to zoom, select a plane, volcano, ash area or feed" }, glDiv, labels, pick, ctl);

  const markUse = icon("ta-waiting", "flow-head__mark");
  // the assistant's one status, as on the demo's tab (wall/x-parts.js stateLine): nothing while it
  // works, else a shape and two words ("AI off", "AI paused") with the explanation behind its (i)
  // and "Why ›" to the cause, said once at Details › TEPHRA Assistant (docs/UI-AI-QUIET.md 8.6)
  const status = el("span", { id: "board-status", class: "flow-head__status", text: "· connecting" });
  // the lede: the board's description for a screen reader (the dialog's aria-describedby); on
  // screen only in Example, where it says what the example is
  const ledeText = el("span", { text: "Connecting to TEPHRA…" });
  const lede = el("p", { id: "board-lede", class: "flow-head__sub" }, ledeText);
  const btnReal = el("button", { type: "button", class: "flow-seg__btn", "aria-pressed": "true", dataset: { flowmode: "real" }, text: "Real now" });
  const btnEx = el("button", { type: "button", class: "flow-seg__btn", "aria-pressed": "false", dataset: { flowmode: "example" }, text: "Example: working normally" });
  const exFlag = el("p", { class: "flow-exflag", hidden: true },
    "Example · illustrative, did not happen",
    infoButton({ topic: "example", label: "About the example", text: "Example · illustrative, not recorded. The assistant steps it shows did not happen." }));
  const helpBtn = el("button", { type: "button", class: "flow-iconbtn", "aria-label": "How this moves", title: "How this moves", dataset: { flowsheet: "help" }, text: "?" });
  const modeSeg = el("div", { class: "flow-seg", role: "group", "aria-label": "What to show" }, btnReal, btnEx);
  const head = el("header", { class: "flow-head" },
    el("div", { class: "flow-head__brand" }, markUse,
      el("div", { class: "flow-head__titles" },
        el("h2", { id: "board-title", class: "flow-head__title", tabindex: "-1" }, el("span", { text: "TEPHRA Assistant " }), status),
        lede)),
    el("div", { class: "flow-head__right" },
      el("div", { class: "flow-head__col" }, modeSeg, exFlag),
      helpBtn));

  // the panel: Inside TEPHRA, the one renderer the demo's Assistant tab draws too
  const I = mountInside({ has });
  const { panel, decide, youHead, skillEls, onreqDot } = I;

  // the dock: the log, the legend, the player
  const log = el("ol", { class: "flow-log", "aria-label": "Newest steps" });
  const legend = el("p", { class: "flow-legend" });
  const allSteps = el("button", { type: "button", class: "flow-link", "aria-label": "Every step in plain words", dataset: { flowsheet: "steps" }, text: "All steps" });
  const playWord = el("span", { class: "flow-play__word" });
  const play = el("button", { type: "button", class: "flow-play", "aria-label": "Play back the latest steps" }, icon("i-play"), playWord);
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
  // a lost connection is said on screen once, by the header's stale chip; a screen reader hears this
  const STALE_SAID = "Reconnecting. Showing the last steps.";

  const stage = el("div", { class: "flow-stage" }, mapWrap, head, panel, dock);
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
  let speed = SPEEDS[0];
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
  const fx = fxC.getContext("2d");
  const rctx = railC.getContext("2d");
  const tctx = trackC.getContext("2d");
  let VW = 0, VH = 0, phone = false;
  let proj = null; // lon,lat -> map px (the live map's projection)
  let mapOff = [0, 0]; // the map's origin in fx coordinates
  let A = {}; // anchors in fx coordinates
  let BE = {}; // beacon positions in map px: { id: { x, y, on, kind } }
  let mapKey = "";

  function dialogRect() { return dialog.getBoundingClientRect(); }

  function layout() {
    const d = dialogRect();
    VW = d.width; VH = d.height; phone = VW <= 760;
    fxC.width = railC.width = Math.round(VW * DPR); fxC.height = railC.height = Math.round(VH * DPR);
    if (gl) { gl.resize(); if (!userMoved) fitArea(false); }
    mapKey = ""; labelKey = "";
    drawMap();
    fitGate();
    drawTrack();
  }

  // the jobs waiting at a closed gate push the skills down (mountInside's fitGate)
  function fitGate() {
    I.fitGate(M, () => { measure(); return A; }, dialogRect);
    drawRails();
  }

  // the part of the map that the head, the panel and the dock leave free
  function freeView(r) {
    if (phone) return { x: 8, y: 8, w: r.width - 16, h: r.height - 16 };
    const p = panel.getBoundingClientRect(), dk = dock.getBoundingClientRect(), h = head.getBoundingClientRect();
    // the map's control column (40 px and its gap) stands beside the panel
    return { x: 24, y: h.bottom - r.top + 10, w: Math.max(200, p.left - r.left - 48 - 52), h: Math.max(160, dk.top - h.bottom - 20) };
  }

  function measure() {
    const d = dialogRect();
    const mr = mapWrap.getBoundingClientRect();
    mapOff = [mr.left - d.left, mr.top - d.top];
    A = I.measure(d, M);
  }

  function ptOf(ref) {
    if (typeof ref === "string") { const a = A[ref]; return a ? [a.x, a.y] : null; }
    if (ref.geo) { if (!proj) return null; const p = proj(ref.geo[0], ref.geo[1]); return [p[0] + mapOff[0], p[1] + mapOff[1]]; }
    if (ref.beacon) { const b = BE[ref.beacon]; return b ? [b.x + mapOff[0], b.y + mapOff[1]] : null; }
    return [ref.x, ref.y];
  }

  // ---------------------------------------------------------------- the map (live)
  // MapLibre on the night basemap, made the first time the board opens. The areas, airports,
  // volcanoes and aircraft are map layers; the beacons and names are DOM labels placed over it,
  // re-placed as the map moves (a beacon whose source is off the map waits at its edge with an arrow).
  let gl = null, glReady = false, userMoved = false, moveRaf = 0;
  const hidden = new Set(); // map layers switched off in Layers
  function ensureMap() {
    if (gl || !window.maplibregl) return;
    gl = new window.maplibregl.Map({
      container: glDiv, style: STYLE_URL, center: [110, -6], zoom: 4.6, minZoom: 2, maxZoom: 10,
      attributionControl: false, dragRotate: false, pitchWithRotate: false, touchPitch: false, fadeDuration: 0,
      renderWorldCopies: false, cooperativeGestures: phone,
    });
    gl.touchZoomRotate.disableRotation();
    gl.addControl(new window.maplibregl.AttributionControl({ compact: true }), "bottom-right");
    // the credit starts folded to its (i): open, it ran over the beacons
    gl.once("load", () => glDiv.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show"));
    gl.on("styleimagemissing", (e) => { if (!gl.hasImage(e.id)) gl.addImage(e.id, { width: 1, height: 1, data: new Uint8Array(4) }); });
    gl.on("style.load", () => {
      nightBasemap(gl, nightColours(), { places: false });
      addImages(gl, symbolColours());
      addLayers();
      glReady = true;
      mapKey = ""; labelKey = "";
      if (M) { fitArea(false); drawMap(); }
    });
    // a pan or zoom by hand keeps its view through resizes until Fit
    gl.on("movestart", (e) => { if (e.originalEvent) { userMoved = true; hidePick(); } });
    gl.on("move", onMove);
    gl.on("click", onMapClick);
    for (const id of ["b-aircraft", "b-volcanoes", "b-official-fill"]) {
      gl.on("mouseenter", id, () => { gl.getCanvas().style.cursor = "pointer"; });
      gl.on("mouseleave", id, () => { gl.getCanvas().style.cursor = ""; });
    }
  }
  function addLayers() {
    for (const id of ["b-official", "b-tephra", "b-adsb", "b-airports", "b-volcanoes", "b-aircraft"]) gl.addSource(id, { type: "geojson", data: fc([]) });
    const vis = (key) => ({ visibility: hidden.has(key) ? "none" : "visible" });
    gl.addLayer({ id: "b-adsb", type: "line", source: "b-adsb", layout: vis("coverage"), paint: { "line-color": C.aircraft, "line-opacity": 0.16, "line-dasharray": [1, 3] } });
    // the official area: the official cone holds every valid product, so it alone is filled and
    // edged; each product inside it is a faint line (select one for what it is)
    const isCone = ["==", ["get", "cone"], true];
    gl.addLayer({ id: "b-official-fill", type: "fill", source: "b-official", layout: vis("ash"), paint: { "fill-color": C.official, "fill-opacity": ["case", isCone, 0.08, 0] } });
    gl.addLayer({ id: "b-official-line", type: "line", source: "b-official", layout: { ...vis("ash"), "line-join": "round" }, paint: { "line-color": C.official, "line-opacity": ["case", isCone, 0.6, 0.14], "line-width": ["case", isCone, 1.8, 1] } });
    // TEPHRA's area where it is wider than the official one
    gl.addLayer({ id: "b-tephra", type: "line", source: "b-tephra", layout: { ...vis("ash"), "line-join": "round" }, paint: { "line-color": C.tephra, "line-opacity": 0.75, "line-width": 1.4, "line-dasharray": [4, 3] } });
    gl.addLayer({ id: "b-airports", type: "circle", source: "b-airports", layout: vis("airports"), paint: { "circle-radius": 2.4, "circle-color": C.text2, "circle-opacity": 0.6 } });
    gl.addLayer({ id: "b-volcanoes", type: "symbol", source: "b-volcanoes", layout: { "icon-image": ["concat", "volcano-", ["get", "code"]], "icon-size": 0.62, "icon-allow-overlap": true, "icon-ignore-placement": true } });
    gl.addLayer({ id: "b-aircraft", type: "symbol", source: "b-aircraft", layout: { ...vis("aircraft"), "icon-image": "ac-sdf", "icon-size": ["case", ["get", "exposed"], 0.5, 0.36], "icon-rotate": ["get", "trk"], "icon-rotation-alignment": "map", "icon-allow-overlap": true, "icon-ignore-placement": true, "symbol-sort-key": ["case", ["get", "exposed"], 1, 0] }, paint: { "icon-color": ["case", ["get", "exposed"], C.job, C.aircraft], "icon-opacity": ["case", ["get", "exposed"], 0.95, 0.55] } });
  }
  // the region framed in the part of the map that the head, the panel and the dock leave free
  function fitArea(animate) {
    if (!gl || !M?.geo.bbox) return;
    const r = mapWrap.getBoundingClientRect();
    if (r.width < 40 || r.height < 40) return;
    const V = freeView(r), b = M.geo.bbox;
    const pad = { left: V.x, top: V.y, right: Math.max(0, r.width - V.x - V.w), bottom: Math.max(0, r.height - V.y - V.h) };
    gl.fitBounds([[b.west - 0.2, b.south - 0.2], [b.east + 0.2, b.north + 0.2]], { padding: pad, duration: animate && !RM() ? 700 : 0 });
  }
  function onMove() {
    if (moveRaf) return;
    moveRaf = requestAnimationFrame(() => {
      moveRaf = 0;
      if (!M || !proj) return;
      const r = mapWrap.getBoundingClientRect();
      placeLabels(proj.V, r.width, r.height);
      placePick();
      if (moving()) kick();
    });
  }
  function drawMap() {
    if (!M || !M.geo.bbox || !glReady) return;
    const r = mapWrap.getBoundingClientRect();
    proj = (lon, lat) => { const p = gl.project([lon, lat]); return [p.x, p.y]; };
    proj.V = freeView(r);
    proj.centre = [(M.geo.bbox.west + M.geo.bbox.east) / 2, (M.geo.bbox.north + M.geo.bbox.south) / 2];
    const where = M.geo.aircraft.reduce((a, x) => a + (x.at ? x.at[0] * 7 + x.at[1] : 0), 0).toFixed(3);
    const key = [M.geo.cones.map((c) => `${c.mode}${c.top}${c.rings[0]?.length}`).join(","), M.geo.official.length, M.geo.bbox.west, M.geo.bbox.north, M.geo.aircraft.length, where, M.geo.volcanoes.map((v) => v.code).join(""), Object.keys(M.geo.airports).length].join("|");
    if (key !== mapKey) {
      mapKey = key;
      const src = (id, f) => gl.getSource(id)?.setData(fc(f));
      const cones = M.geo.cones.filter((cn) => cn.mode === "OFFICIAL").map((cn) => ({ cone: true, label: "Official ash area", top: cn.top, base: cn.base, rings: cn.rings }));
      src("b-official", [...M.geo.official, ...cones].flatMap((o) => o.rings.map((ring) => poly([ring], { cone: Boolean(o.cone), label: o.label || o.kind || "", top: o.top ?? null, base: o.base ?? null }))));
      src("b-tephra", M.geo.cones.filter((cn) => cn.mode !== "OFFICIAL").flatMap((cn) => cn.rings.map((ring) => poly([ring], { top: cn.top ?? null, base: cn.base ?? null }))));
      src("b-adsb", M.geo.adsbPoints.map((a) => poly([circleRing(a.lon, a.lat, a.radius_nm)])));
      src("b-airports", Object.entries(M.geo.airports).map(([code, at]) => pt(at, { code })));
      src("b-volcanoes", M.geo.volcanoes.filter((v) => v.at).map((v) => pt(v.at, { id: v.id, name: v.name, code: v.code in CODE_WORD ? v.code : "UNKNOWN" })));
      src("b-aircraft", M.geo.aircraft.filter((a) => a.at).map((a) => pt(a.at, { hex: a.hex, trk: a.trk ?? 0, exposed: a.exposed })));
    }
    // the labels are DOM: rebuilt only when what they say or where they sit can change
    const lKey = [r.width, r.height, phone, M.geo.volcanoes.map((v) => v.id).join(","), (M.feeds || []).map((f) => `${f.status}${f.records}`).join(""), M.geo.official.filter((o) => o.kind === "SIGMET").length, [...hidden].join()].join("|");
    if (lKey !== labelKey) { labelKey = lKey; placeLabels(proj.V, r.width, r.height); }
    placePick();
  }
  let labelKey = "";

  // ---------------------------------------------------------------- what you select on the map
  // One small card, anchored where you selected and following the map, written with textContent.
  let picked = null; // { at, title, lines }
  function showPick(at, title, lines) {
    picked = { at, title, lines };
    pick.replaceChildren(el("button", { type: "button", class: "flow-pick__x", "aria-label": "Close", dataset: { flowmap: "unpick" } }, icon("i-x")),
      el("b", { class: "flow-pick__title", text: title }), ...lines.filter(Boolean).map((t) => el("span", { class: "flow-pick__line", text: t })));
    pick.hidden = false;
    placePick();
  }
  function hidePick() { picked = null; pick.hidden = true; }
  function placePick() {
    if (!picked || !proj) return;
    const r = mapWrap.getBoundingClientRect();
    const [x, y] = proj(picked.at[0], picked.at[1]);
    if (x < 0 || y < 0 || x > r.width || y > r.height) { pick.hidden = true; return; }
    pick.hidden = false;
    const w = pick.offsetWidth, h = pick.offsetHeight;
    pick.style.left = `${clamp(x - w / 2, 8, r.width - w - 8)}px`;
    pick.style.top = `${y - h - 14 < 8 ? y + 14 : y - h - 14}px`;
  }
  function onMapClick(e) {
    if (!M) return;
    const hit = gl.queryRenderedFeatures(e.point, { layers: ["b-aircraft", "b-volcanoes", "b-official-fill"].filter((id) => gl.getLayer(id) && gl.getLayoutProperty(id, "visibility") !== "none") });
    // a plane or volcano first, then the product under the pointer, then the whole official area
    const f = hit.find((x) => x.layer.id !== "b-official-fill") || hit.find((x) => !x.properties.cone) || hit[0];
    if (!f) { hidePick(); return; }
    const at = [e.lngLat.lng, e.lngLat.lat];
    if (f.layer.id === "b-aircraft") {
      const a = M.geo.aircraft.find((x) => x.hex === f.properties.hex);
      if (!a) return;
      const where = a.exposed ? (a.mins > 0 ? `Enters TEPHRA's area in ${a.mins} min` : "Inside TEPHRA's area") : "Outside the ash";
      showPick(a.at, a.flight ? `${a.flight} · ${airline().fictional ? "RFA (fictional)" : airline().code}` : a.cs || a.hex,
        [a.flight && a.cs ? `${M.demo ? "Demo" : "Real"} aircraft ${a.cs}` : null, [a.alt != null ? fl(a.alt) : null, a.gs != null ? `${Math.round(a.gs)} kt` : null].filter(Boolean).join(" · ") || null,
          a.from && a.to ? `${a.from} → ${a.to}` : null, where]);
    } else if (f.layer.id === "b-volcanoes") {
      const v = M.geo.volcanoes.find((x) => String(x.id) === String(f.properties.id));
      if (v) showPick(v.at, v.name, [`Aviation colour code: ${CODE_WORD[v.code] || "Unknown"}`]);
    } else {
      const p = f.properties;
      const band = p.top != null ? `${Number(p.base) > 0 ? fl(Number(p.base)) : "Surface"} to ${fl(Number(p.top))}` : null;
      showPick(at, p.label || "Official ash area", [band, "Official products are binding: TEPHRA may only widen them"]);
    }
  }
  function onBeaconClick(id) {
    const f = (M.feeds || []).find((x) => x.feed === id), b = BE[id];
    if (!f || !b || !gl) return;
    const ll = gl.unproject([b.x, b.y]);
    const on = f.status === "OK" || f.status === "STALE";
    showPick([ll.lng, ll.lat], FEED_TITLE[id], [on ? `${f.status === "STALE" ? "Late" : "Working"} · ${plural(f.records ?? 0, "record")}` : null, !on ? (f.error || "Off") : null]);
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
      // an off feed is its name alone, dimmed; why it is off is one click away
      const sub = !on ? null : edge && km ? `${s.sub} · ${km.toLocaleString("en")} km`
        : id === "sigmet" ? (at ? `${plural(sig.length, "area")} in force` : "none in force here") : s.sub;
      if (hidden.has("feeds")) continue;
      // the name alone on the map (one short line); the office, distance or count in its tooltip
      const labEl = el("span", { class: `flow-beacon__lab flow-beacon__lab--${lab}` }, el("b", { text: `${arrow ? `${arrow} ` : ""}${s.name}` }));
      const b = el("div", { class: `flow-beacon flow-beacon--${BE[id].kind}${on ? "" : " is-off"}`, title: [on ? `${FEED_TITLE[id]}: ${f.records ?? 0} records` : `${FEED_TITLE[id]}: ${f.error || "off"}`, sub].filter(Boolean).join(" · "), dataset: { flowbeacon: id } },
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
    if (official && !phone && !hidden.has("ash")) {
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
  const litSkill = (id) => I.lightSkill(id);

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
    drawInside(rctx, A, M, { C, ex: mode === "example", open: M ? gateOpen() : false, VW, VH, DPR });
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
    setText(chipText, following ? "" : playing ? `playing back ${span}` : `paused in ${span}`);
    const label = following ? `Play back ${span}` : playing ? "Pause the playback" : "Play the playback";
    const ic = playing ? "i-pause" : following ? "i-replay" : "i-play";
    if (play.dataset.icon !== ic) { play.dataset.icon = ic; play.replaceChildren(icon(ic), playWord); }
    setText(playWord, playing ? "Pause" : "Play");
    setAttr(play, "aria-label", label);
    setAttr(play, "title", label);
    speedBtn.hidden = RM();
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
  function renderStatic() {
    // the Example segment is the `example` feature: hidden with it, and never left in Example mode
    modeSeg.hidden = !has("example");
    if (mode === "example" && !has("example")) mode = "real";
    const ex = mode === "example";
    I.renderStatic(M, ex);
    dialog.classList.toggle("is-example", ex);
    setAttr(btnReal, "aria-pressed", String(!ex));
    setAttr(btnEx, "aria-pressed", String(ex));
    exFlag.hidden = !ex;
    const sym = ex ? "ta-working" : M.ai.symbol;
    setMark(markUse, sym);
    if (dialog.dataset.ai !== (ex ? "on" : M.ai.kind)) dialog.dataset.ai = ex ? "on" : M.ai.kind;
    if (dialog.dataset.mode !== M.mode) dialog.dataset.mode = M.mode;
    const line = stateLine({ suffix: M.ai.suffix }, { stub: M.stub, kind: M.ai.kind, reason: M.ai.reason });
    const skey = ex ? "ex" : `${line.word}|${line.info}`;
    if (status.dataset.k !== skey) {
      status.dataset.k = skey;
      status.dataset.tone = ex ? "ok" : line.tone;
      const why = line.why ? el("button", { type: "button", class: "link-btn", "aria-label": "Why: open Details › TEPHRA Assistant", dataset: { act: "board-details", sec: "ai", focus: "board-why" }, text: "Why ›" }) : null;
      status.replaceChildren(...(ex ? ["· working"]
        : line.word ? [el("span", { class: "flow-head__word" }, icon(line.icon, "st"), line.word), infoButton({ topic: "assistant", label: "About the AI state", text: line.info, actions: [why] })]
          : [el("span", { class: "sr-only", text: line.said })]));
    }
    setText(ledeText, ex ? "An example of a normal run on the same recorded inputs: the Coordinator hands each job to a skill, and every draft waits for you." : M.sub);
    lede.classList.toggle("sr-only", !ex);
    // "waiting in line" and "must-do, to you" only while something can wait or be passed on
    const queueing = M.ai.kind === "paused" || M.desk.must > 0 || M.queue.length > 0;
    if (legendFor !== `${mode}|${queueing}`) {
      legendFor = `${mode}|${queueing}`;
      const sw = (tone, word, hollow = false) => el("span", {}, (() => { const i = el("i", { class: hollow ? "is-hollow" : null }); if (hollow) i.style.color = colOf(tone); else i.style.background = colOf(tone); return i; })(), word);
      legend.replaceChildren(...(ex
        ? [sw("official", "official reports"), sw("observer", "observatory"), sw("aircraft", "aircraft"), sw("weather", "weather"), sw("job", "jobs"), sw("tephra", "TEPHRA's estimate")]
        : [sw("official", "official reports"), sw("observer", "observatory"), sw("aircraft", "aircraft"), sw("weather", "weather"), sw("job", "jobs"), queueing ? sw("info", "waiting in line", true) : null, queueing ? sw("must", "must-do") : null].filter(Boolean)));
    }
    renderDecide(false);
    renderPlayer();
  }

  function renderCounters() {
    I.renderCounters(events, simT);
  }

  // the hero, its reason and the run bars (mountInside), and the bar's chip that says the same
  function renderDecide(bump) {
    if (!M) return;
    const ex = mode === "example";
    const { n, mustMode } = I.renderDecide(M, { ex, events, t: simT, pending: pendingLand, exState, bump, rm: RM() });
    mchip.classList.toggle("is-must", mustMode);
    const shown = n == null ? "–" : String(n);
    setText(mchip, ex ? `${shown} drafts` : mustMode ? `${shown} must-do` : `${shown} to approve`);
    // the button says what the hero says, a number only when there is one
    setAttr(mchip, "aria-label", `${ex ? (n == null ? "No example run yet" : `${n} example ${n === 1 ? "draft" : "drafts"}`)
      : mustMode ? (n == null ? "No must-do count yet, waiting for the first run in this window" : `${n} must-do ${n === 1 ? "flight" : "flights"} to plan by hand`)
        : n == null ? "Advisory count unknown" : `${n} ${n === 1 ? "advisory waits" : "advisories wait"} for you`}. Go to You decide`);
  }

  function rowsAt() {
    return foldRows(events.filter((e) => e.at <= simT), { example: mode === "example" });
  }
  // A row's words; the must-do count is the hero's alone, so a run's row never says a second number.
  function rowParts(r) {
    // a code template's line: the "{ }" mark, not "(code only)" words (the AI status says it once)
    const t = templateText(r.text);
    return [t.code ? codeMark() : null, t.text, r.repeat ? el("span", { class: "flow-log__x", text: ` · ${r.repeat}` }) : null].filter(Boolean);
  }
  const rowSig = (r) => `${r.text}|${r.repeat || ""}|${r.tone}`;
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
      live.textContent = `${hms(r.tm)}. ${r.text}.`;
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
      sheetBody.replaceChildren(...skillSheet(card, s, skillId, M.ai.kind === "paused"));
    } else if (kind === "checks") {
      sheetH.textContent = "Code checks";
      sheetBody.replaceChildren(...checksSheet(events.filter((e) => e.at <= simT), colOf));
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
      ol.replaceChildren(...rows.map((r) => el("li", { dataset: { at: String(r.at) } }, el("span", { class: "flow-sheet__tm", text: hms(r.tm) }), el("span", {}, ...markedText(r.text), r.repeat ? ` · ${r.repeat}` : ""))));
    }
    for (const li of ol.children) li.classList.toggle("is-now", Number(li.dataset.at) <= simT);
  }
  sheet.addEventListener("close", () => { const back = sheetOpener; sheetOpener = null; if (back && document.contains(back)) back.focus({ preventScroll: true }); });
  sheet.addEventListener("click", (e) => { if (e.target === sheet) sheet.close(); });

  // ---------------------------------------------------------------- input
  dialog.addEventListener("click", (e) => {
    const bc = e.target.closest("[data-flowbeacon]");
    if (bc) { onBeaconClick(bc.dataset.flowbeacon); return; }
    const t = e.target.closest("button");
    if (!t || !dialog.contains(t)) return;
    if (t.dataset.flowmap) {
      const a = t.dataset.flowmap;
      if (a === "in" || a === "out") { userMoved = true; gl?.easeTo({ zoom: gl.getZoom() + (a === "in" ? 1 : -1), duration: RM() ? 0 : 300 }); }
      else if (a === "fit") { userMoved = false; hidePick(); fitArea(true); }
      else if (a === "unpick") hidePick();
      else if (a === "layers") { const open = layerMenu.hidden; layerMenu.hidden = !open; layersBtn.setAttribute("aria-expanded", String(open)); }
      return;
    }
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
  layerMenu.addEventListener("change", (e) => {
    const id = e.target.dataset.flowlayer;
    if (!id) return;
    if (e.target.checked) hidden.delete(id); else hidden.add(id);
    const ids = MAP_LAYERS.find((l) => l[0] === id)?.[2] || [];
    if (glReady) for (const lid of ids) if (gl.getLayer(lid)) gl.setLayoutProperty(lid, "visibility", e.target.checked ? "visible" : "none");
    hidePick();
    drawMap();
  });
  dialog.addEventListener("keydown", (e) => { if (e.key === "Escape" && !layerMenu.hidden) { e.preventDefault(); layerMenu.hidden = true; layersBtn.setAttribute("aria-expanded", "false"); layersBtn.focus(); } });
  play.addEventListener("click", () => {
    if (following) startPlayback(T0);
    else if (!playing && simT >= T1) startPlayback(T0);
    else setPlaying(!playing);
  });
  speedBtn.addEventListener("click", () => { speed = SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.length]; renderPlayer(); });
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
      requestAnimationFrame(() => { layout(); ensureMap(); if (M) seek(following ? T1 : simT); kick(); });
    },
  };

  function setStale(lost) {
    if (lost === stale) return;
    stale = lost;
    dialog.classList.toggle("is-stale", stale);
    if (isOpen) live.textContent = stale ? STALE_SAID : "Live updates are back.";
    if (stale) { if (raf) cancelAnimationFrame(raf); raf = 0; }
    else kick();
  }
}
