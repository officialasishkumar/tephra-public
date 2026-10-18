// The demo's Assistant tab (SPEC v2 5.2.5): TEPHRA Assistant's steps in the side panel, from the
// same model as the /assistant board (board.js flowModel). Under the state line (panels.js
// renderChrome writes it): the Inside TEPHRA diagram, the same renderer as the board's glass panel
// (board-view.js mountInside), then "What happened": in REPLAY a player over the replay's steps and
// the step log folded to its newest rows, with "Show all".
//
// On arrival the panel catches up (assist.js lastChain): it plays TEPHRA's last chain of kept steps
// (the feed reads, the code checks, the Coordinator, each skill, You decide) in about 16 s, a pulse
// running from each feed's place on the map into Code checks and down the diagram, then follows the
// replay clock. Every beat is recorded steps; nothing is fetched, asked of a model or written.
// Labelled "Replay · catching up" (the step playing in words under it,
// and said to a screen reader as the replay's), then "Replay · following the clock", with
// "Replay again". Each skill's row shows its state at the beat playing (in line, running, done, no
// result). The catch-up waits, and holds between beats, while the tab is hidden, a dialog covers it
// or the phone sheet only peeks; the tab scrolls the step playing into view. Under reduced motion
// nothing travels: the diagram's rows light in turn, one every RM_STEP_MS. Every string goes in through el() (textContent); positions go through
// the CSSOM and SVG attributes.

import { el, icon, reducedMotion } from "./util.js";
import { codeMark } from "./x-parts.js";
import { hmsOf, RESULT } from "./board.js";
import { mountInside, drawInside, insideColours, mapColours, SRC } from "./board-view.js";
import { FIVE_STEPS } from "../five-steps.js";
import { TENANT } from "../base.js";
import { visibleRows, minuteGroups, playerWords, trackTicks, newestAt, sayRow, sayBeat, PLAY_SPEED, RM_STEP_MS, lastChain, beatMs, chainNote, eventsShown, rowsOf, catchupSkills } from "./assist.js";

// the log shows this many newest rows until "Show all"
const FOLDED_ROWS = 3;
const SAY_EVERY_MS = 10000;
// a gap in the replay longer than this much screen time is skipped down to SKIP_TO_S
const SKIP_OVER_S = 1.2;
const SKIP_TO_S = 0.6;
// the catch-up waits this long at most for the map before it plays without the map's part
const MAP_WAIT_MS = 4000;
// the map's control column on its right edge (zoom, layers, 3D): a pulse's start stays clear of it
const MAP_CONTROLS_PX = 76;
const STAGE_ICON = Object.fromEntries(FIVE_STEPS.map((s) => [s.key, s.icon]));
const RESULT_OF = { done: RESULT.ok, tool: ["ok", "i-check", "Tool"], noresult: RESULT.failed };
const SVG = "http://www.w3.org/2000/svg";

const setText = (node, text) => { if (node.textContent !== text) node.textContent = text; };
const setAttr = (node, k, v) => { if (node.getAttribute(k) !== v) node.setAttribute(k, v); };
const rowIcon = (r) => (r.actor === "Aircraft positions" || r.actor === "Airline positions" ? "i-aircraft" : STAGE_ICON[r.stage]);
const svg = (tag, attrs = {}) => { const n = document.createElementNS(SVG, tag); for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v)); return n; };

function resultWord(r) {
  const [tone, ic, word] = RESULT_OF[r.result] || [];
  return word ? el("span", { class: `ev__res ev__res--${tone}` }, icon(ic), word) : null;
}

function logRow(r) {
  return el("li", { class: `ev t-${r.stage}` },
    el("time", { class: "ev__t", datetime: new Date(r.tm).toISOString(), text: hmsOf(r.tm) }),
    el("span", { class: "ev__ic" }, icon(rowIcon(r))),
    el("span", { class: "ev__who" }, r.actor, resultWord(r)),
    el("span", { class: "ev__what" }, r.code ? codeMark() : null, r.text));
}

// Where a feed's read comes from on the map (lon, lat), as the /assistant board places its beacons
// (board-view.js SRC): the issuing office, the SIGMETs in force, the winds grid, the aircraft, the
// airports. null when the snapshot holds no place for it.
const mid = (pts) => (pts.length ? [pts.reduce((a, p) => a + p[0], 0) / pts.length, pts.reduce((a, p) => a + p[1], 0) / pts.length] : null);
function feedPlace(feed, M) {
  const g = M.geo;
  if (SRC[feed]?.at) return SRC[feed].at;
  if (feed === "sigmet") return mid(g.official.filter((o) => o.kind === "SIGMET" && o.rings[0]).flatMap((o) => o.rings[0]));
  if (feed === "winds" && g.bbox) return [(g.bbox.west + g.bbox.east) / 2, g.bbox.south + 0.3];
  if (feed === "adsb" || feed === "airline") {
    const near = g.aircraft.filter((a) => a.at && a.exposed);
    return mid((near.length ? near : g.aircraft.filter((a) => a.at)).map((a) => a.at));
  }
  if (feed === "metar" || feed === "taf") return mid(Object.values(g.airports));
  return null;
}
const FEED_LABEL = { sigmet: "VA SIGMET", adsb: "Aircraft", airline: "Airline positions", metar: "METAR", taf: "TAF", winds: "Winds aloft" };

// `view`: the Wall's map and panel state the pulses need, handed in by wall.js: mapView() is
// { rect, project([lon, lat]) -> [x, y] in the map's own pixels } or null before the map is ready;
// sheet() is "" on a wide screen, else the phone sheet's state ("peek", "half", "full"); blocked()
// is true while a dialog (the welcome) is open; noCatchup is true for automated screenshots.
export function mountAssist(host, { has = () => true, mapView = () => null, sheet = () => "", blocked = () => false, noCatchup = false } = {}) {
  const player = host.querySelector("#assist-player");
  const note = host.querySelector("#assist-note");
  const log = host.querySelector("#assist-log");
  const live = host.querySelector("#assist-live");

  // ---- the diagram, its rails canvas over it
  const I = mountInside({ has, side: true });
  const railC = el("canvas", { class: "flow-rails flow-rails--side", "aria-hidden": "true" });
  I.panel.append(railC);
  host.querySelector("#assist-inside").replaceWith(I.panel);
  I.panel.id = "assist-inside";
  const rctx = railC.getContext("2d");

  // ---- the player
  const playBtn = el("button", { type: "button", class: "player__btn" });
  const lead = el("b");
  const sep = el("span", { class: "player__sep", text: " · " });
  const words = el("span", { class: "player__text" });
  const time = el("span", { class: "mono player__time" });
  const again = el("button", { type: "button", class: "link-btn player__again", title: "Play TEPHRA's last chain of steps again, fast", text: "Replay again" });
  const beatLine = el("p", { class: "player__beat", hidden: true });
  const ticks = el("span", { class: "player__ticks", "aria-hidden": "true" });
  const knob = el("i", { class: "player__knob", "aria-hidden": "true" });
  const track = el("div", { class: "player__track", role: "slider", tabindex: "0", "aria-label": "Position in TEPHRA's steps", "aria-valuemin": "0", "aria-valuemax": "100" }, ticks, knob);
  player.replaceChildren(playBtn, el("p", { class: "player__words" }, lead, sep, words, time), track, beatLine, again);

  // ---- the pulses: one overlay over the whole page, never taking a click
  const flowSvg = svg("svg", { class: "as-flow__svg" });
  const flow = el("div", { class: "as-flow", "aria-hidden": "true" });
  flow.append(flowSvg);
  document.body.append(flow);

  let M = null;
  const P = { mode: "follow", t: NaN, from: NaN, rm: reducedMotion() };
  let showAll = false;
  let logKey = "", tickKey = "", seenN = -1, newestKey = "";
  let lastSaid = -1e9, sayTimer = 0, said = "";
  let raf = 0, lastFrame = 0, rmLeft = 0;
  // the catch-up: its chain, the beat playing, the ids played, its timer
  // a hosted airline's map has no catch-up: its panel follows its own live steps (SPEC-FINAL 5.3)
  const CU = { state: noCatchup || TENANT ? "done" : "waiting", chain: null, i: -1, played: new Set(), timer: 0, waitSince: 0, held: false, bumped: -1 };
  let C = insideColours();
  // a pulse that starts on the map takes the night map's colours (the map is dark in both themes)
  let CM = mapColours();
  let railKey = "", gateOpenUntil = 0;

  const steps = () => (M?.events || []).filter((e) => !e.quiet && e.type !== "note");
  const eventsAt = (t) => (M?.events || []).reduce((n, e) => n + (e.at <= t ? 1 : 0), 0);
  const playhead = () => (P.mode === "follow" ? newestAt(M) : P.t);
  const shown = () => !host.hidden && host.offsetParent !== null;
  // the catch-up plays only where it is seen: the tab shown, no dialog over it, the sheet open
  const unseen = () => !shown() || blocked() || sheet() === "peek";
  const beatNow = () => (P.mode === "catchup" && CU.chain ? CU.chain.beats[CU.i] || null : null);

  // ---- the diagram's rails, drawn in the panel's own frame
  function drawRails(force = false) {
    if (!M) return;
    const r = I.panel.getBoundingClientRect();
    if (!r.width || !r.height) return;
    const DPR = Math.min(2, window.devicePixelRatio || 1);
    const open = M.gate.open || performance.now() < gateOpenUntil;
    const key = [Math.round(r.width), Math.round(r.height), M.gate.open, M.gate.kind, M.queue.length, M.ai.kind, M.desk.must > 0, open, document.documentElement.dataset.theme || ""].join("|");
    if (!force && key === railKey) return;
    railKey = key;
    C = insideColours();
    CM = mapColours();
    railC.width = Math.round(r.width * DPR); railC.height = Math.round(r.height * DPR);
    const origin = () => I.panel.getBoundingClientRect();
    const A = I.fitGate(M, () => I.measure(origin(), M), origin);
    drawInside(rctx, A, M, { C, open, VW: r.width, VH: r.height, DPR });
  }

  function renderPlayer() {
    player.hidden = !M;
    if (!M) return;
    const w = playerWords(M, CU.state === "waiting" && M.replay ? { ...P, mode: "waiting" } : P);
    // an airline's space says SHADOW or LIVE in its header chip: "Live" here would read as that
    setText(lead, TENANT && w.live ? "Now" : w.lead);
    sep.hidden = !lead.textContent;
    setText(words, w.text);
    setText(time, w.time || "");
    // LIVE: no player, one line
    player.classList.toggle("player--live", w.live);
    player.classList.toggle("is-catchup", P.mode === "catchup");
    playBtn.hidden = w.live;
    track.hidden = w.live;
    again.hidden = w.live || P.mode === "catchup" || CU.state === "waiting" || !CU.chain?.beats.length;
    const b = beatNow();
    beatLine.hidden = !b;
    setText(beatLine, b ? b.text : "");
    if (w.live) return;
    const ic = w.action === "play" ? "i-play" : "i-pause";
    if (playBtn.dataset.icon !== ic) { playBtn.dataset.icon = ic; playBtn.replaceChildren(icon(ic)); }
    setAttr(playBtn, "aria-label", w.button);
    playBtn.title = w.button;
    setAttr(track, "aria-valuetext", w.valuetext);
    const s = steps();
    const t0 = s.length ? s[0].at : NaN, t1 = s.length ? s[s.length - 1].at : NaN;
    const frac = Number.isFinite(t0) && t1 > t0 ? Math.min(1, Math.max(0, (playhead() - t0) / (t1 - t0))) : 1;
    setAttr(track, "aria-valuenow", String(Math.round(frac * 100)));
    knob.style.setProperty("left", `${(frac * 100).toFixed(2)}%`);
    const tk = `${s.length}|${t0}|${t1}`;
    if (tk !== tickKey) {
      tickKey = tk;
      ticks.replaceChildren(...trackTicks(M).map((x) => {
        const i = el("i", { class: x.ai ? "is-ai" : "" });
        i.style.setProperty("left", `${(x.frac * 100).toFixed(2)}%`);
        return i;
      }));
    }
  }

  function say(r) {
    window.clearTimeout(sayTimer);
    const wait = Math.max(0, SAY_EVERY_MS - (performance.now() - lastSaid));
    sayTimer = window.setTimeout(() => {
      const text = sayRow(r);
      if (text === said) return;
      live.textContent = text;
      said = text;
      lastSaid = performance.now();
    }, wait);
  }

  // "What happened": the newest FOLDED_ROWS rows, or every row under its minute after "Show all"
  function renderLog(rows) {
    const list = showAll ? rows : rows.slice(0, FOLDED_ROWS);
    const key = `${rows.length}|${showAll}|${list.map((r) => `${r.key}:${r.text}`).join("§")}`;
    if (key === logKey) return;
    logKey = key;
    if (!rows.length) {
      log.replaceChildren(el("p", { class: "log__empty", text: "No steps yet in this window." }));
      return;
    }
    const kids = minuteGroups(list).flatMap((g) => [el("h3", { class: "log__min", text: g.minute }), el("ol", {}, ...g.rows.map((r) => logRow(r)))]);
    if (rows.length > FOLDED_ROWS) {
      kids.push(el("button", { type: "button", class: "link-btn log__more", "aria-expanded": String(showAll), dataset: { focus: "assist-all" }, text: showAll ? "Show fewer" : `Show all (${rows.length})` }));
    }
    log.replaceChildren(...kids);
  }

  function render() {
    renderPlayer();
    if (!M) return;
    host.dataset.ai = M.ai.kind;
    let evs, t;
    if (P.mode === "catchup") { evs = eventsShown(M, CU.chain, CU.played); t = Infinity; }
    else { t = playhead(); evs = Number.isFinite(t) ? M.events.filter((e) => e.at <= t) : []; }
    const rows = P.mode === "catchup" ? rowsOf(evs) : Number.isFinite(t) ? visibleRows(M, t) : [];
    seenN = eventsAt(t);
    const b = beatNow();
    I.renderStatic(M, false, P.mode === "catchup" ? catchupSkills(M, CU.chain, CU.i) : null);
    I.renderCounters(evs, t);
    // the beat that reaches You decide says what reached a person, and the count bumps
    const toYou = b?.kind === "you";
    I.renderDecide(M, { events: evs, t, rm: P.rm, note: toYou ? `${b.text} · run ${hmsOf(b.at)}` : null, bump: toYou && CU.bumped !== CU.i });
    if (toYou) CU.bumped = CU.i;
    renderLog(rows);
    const n = chainNote(CU.chain || { beats: [], full: true });
    const say1 = P.mode === "catchup" && CU.chain && !CU.chain.full ? n : "";
    note.hidden = !say1;
    setText(note, say1);
    const top = rows[0];
    const k = top ? `${top.key}|${top.text}` : "";
    // the catch-up says its beats (nextBeat); a row is said as new only while following the clock
    if (k && k !== newestKey) { if (newestKey && P.mode === "follow") say(top); newestKey = k; }
    drawRails();
  }

  // ---- the catch-up
  function startCatchup() {
    stopCatchup();
    CU.chain = lastChain(M);
    CU.played = new Set();
    CU.i = -1;
    CU.held = false;
    CU.bumped = -1;
    if (!CU.chain.beats.length) { CU.state = "done"; P.mode = "follow"; render(); return; }
    CU.state = "playing";
    P.mode = "catchup";
    P.t = CU.chain.beats[0].from;
    newestKey = "";
    render();
    nextBeat();
  }
  function nextBeat() {
    CU.timer = 0;
    // out of sight: hold here; poke() goes on from the next beat once the tab shows again
    if (unseen()) { CU.held = true; return; }
    CU.held = false;
    CU.i += 1;
    const b = CU.chain.beats[CU.i];
    if (!b) { finishCatchup(); return; }
    for (const id of b.ids) CU.played.add(id);
    P.t = b.at;
    render();
    bringIntoView(b.kind === "feeds" || b.kind === "code" ? "code" : b.node);
    light(b);
    if (!P.rm) pulseBeat(b);
    sayNow(sayBeat(b));
    CU.timer = window.setTimeout(nextBeat, beatMs(CU.chain.beats.length, P.rm));
  }
  // a beat is said at once (beats come at most every few seconds; a polite region queues them)
  function sayNow(text) {
    window.clearTimeout(sayTimer);
    live.textContent = text;
    said = text;
    lastSaid = performance.now();
  }
  // the tab scrolls so the beat's row shows under the player (held at the top while catching up)
  let selfScroll = false;
  function bringIntoView(a) {
    const n = a === "you" ? I.decide.querySelector(".flow-hero") || I.decide : I.rowOf[a];
    if (!n || n.closest("[hidden]")) return;
    const box = host.getBoundingClientRect();
    const top = Math.max(box.top, player.hidden ? box.top : player.getBoundingClientRect().bottom);
    const r = n.getBoundingClientRect();
    let dy = 0;
    if (r.top < top + 4) dy = r.top - top - 8;
    else if (r.bottom > box.bottom - 4) dy = r.bottom - box.bottom + 12;
    if (!dy) return;
    const before = host.scrollTop;
    host.scrollTop = before + dy;
    if (host.scrollTop !== before) selfScroll = true;
  }
  function finishCatchup() {
    stopCatchup();
    CU.state = "done";
    P.mode = "follow";
    unlight();
    render();
  }
  function stopCatchup() {
    window.clearTimeout(CU.timer);
    CU.timer = 0;
    CU.held = false;
    if (CU.state === "playing") CU.state = "done";
    clearPulses();
  }
  // the beat's row in the diagram is ringed while it plays (the only highlight under reduced motion)
  function unlight() { for (const n of I.panel.querySelectorAll(".is-step")) n.classList.remove("is-step"); }
  function light(b) {
    unlight();
    I.rowOf[b.node]?.classList.add("is-step");
    if (b.kind === "skill" && M.gate.kind !== "nomodel" && !M.gate.open && !(CU.chain.beats.find((x) => x.kind === "coord")?.refused)) {
      // a recorded hand-out through a gate that is closed now: open while it passes, as the board draws it
      gateOpenUntil = performance.now() + beatMs(CU.chain.beats.length, P.rm);
      drawRails(true);
      window.setTimeout(() => drawRails(true), beatMs(CU.chain.beats.length, P.rm) + 50);
    }
  }
  // the catch-up starts once there is a model, the tab shows and no dialog covers it; it gives the
  // map up to MAP_WAIT_MS to draw first. The check runs a moment after the call, so a welcome
  // dialog the same load opens is seen as open.
  let startTimer = 0;
  function maybeStart() {
    if (CU.state !== "waiting" || !M || startTimer) return;
    startTimer = window.setTimeout(() => {
      startTimer = 0;
      if (CU.state !== "waiting" || !M) return;
      // LIVE has no player and nothing to catch up on: new steps come as they happen
      if (!M.replay) { CU.state = "done"; render(); return; }
      if (unseen()) return;
      if (!mapView()) {
        if (!CU.waitSince) CU.waitSince = performance.now();
        if (performance.now() - CU.waitSince < MAP_WAIT_MS) { window.setTimeout(maybeStart, 300); return; }
      }
      startCatchup();
    }, 120);
  }

  // ---- the pulses (SVG over the page): each from where its step's data came from to its node
  let pulses = [];
  function clearPulses() { for (const p of pulses) { p.g.remove(); p.lab?.remove(); } pulses = []; }
  const nodeAt = (a) => {
    const n = I.panel.querySelector(`[data-a="${a}"]`);
    if (!n || n.closest("[hidden]")) return null;
    const r = n.getBoundingClientRect();
    return r.width ? [r.left + r.width / 2, r.top + r.height / 2] : null;
  };
  // a node takes a pulse only when it is on screen inside the panel's scroll, below the player
  function nodeVisible(a) {
    const p = nodeAt(a);
    if (!p) return null;
    const box = host.getBoundingClientRect();
    const top = player.hidden ? box.top : Math.max(box.top, player.getBoundingClientRect().bottom);
    return p[1] >= top + 4 && p[1] <= box.bottom - 4 && p[0] >= box.left && p[0] <= box.right ? p : null;
  }
  // a feed's place on the Wall's map, held to the map's edge when it lies off the map; on the
  // right it stays clear of the map's control column (MAP_CONTROLS_PX wide)
  function mapPoint(ll) {
    const v = mapView();
    if (!v || !ll) return null;
    const [x, y] = v.project(ll);
    const r = v.rect;
    const pad = 18;
    const right = Math.max(r.left + pad, r.right - MAP_CONTROLS_PX);
    return [Math.min(right, Math.max(r.left + pad, r.left + x)), Math.min(r.bottom - pad, Math.max(r.top + pad, r.top + y))];
  }
  function curvePath(pts) {
    let d = `M${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)}`;
    for (let i = 1; i < pts.length; i++) {
      const [p, q] = [pts[i - 1], pts[i]];
      const dy = q[1] - p[1];
      d += Math.abs(p[0] - q[0]) < 1 ? ` L${q[0].toFixed(1)},${q[1].toFixed(1)}`
        : ` C${p[0].toFixed(1)},${(p[1] + dy * 0.55).toFixed(1)} ${q[0].toFixed(1)},${(q[1] - dy * 0.55).toFixed(1)} ${q[0].toFixed(1)},${q[1].toFixed(1)}`;
    }
    return d;
  }
  function arcPath(p, q) {
    const mx = (p[0] + q[0]) / 2, my = (p[1] + q[1]) / 2, d = Math.hypot(q[0] - p[0], q[1] - p[1]);
    return `M${p[0].toFixed(1)},${p[1].toFixed(1)} Q${(mx - d * 0.05).toFixed(1)},${Math.max(72, my - d * 0.2).toFixed(1)} ${q[0].toFixed(1)},${q[1].toFixed(1)}`;
  }
  // one pulse: a trail drawn along the path, a dot running on it, a ring at the start (with the
  // source's name when it comes from the map) and the target's row lit on arrival
  function pulse(d, col, { delay = 0, dur = 900, label = null, from = null, to = null } = {}) {
    const g = svg("g", { class: "as-flow__p" });
    g.style.setProperty("--c", col);
    const path = svg("path", { d, class: "as-flow__trail" });
    const dot = svg("circle", { r: 4, class: "as-flow__dot" });
    g.append(path, dot);
    if (from) {
      const ring = svg("circle", { cx: from[0], cy: from[1], r: 5, class: "as-flow__ring" });
      g.append(ring);
    }
    let lab = null;
    if (label && from) {
      // the label sits on the map: a night chip in both themes, like every other map label
      lab = el("span", { class: "as-flow__lab night", text: label });
      lab.style.setProperty("--c", col);
      lab.style.left = `${from[0]}px`; lab.style.top = `${from[1]}px`;
      flow.append(lab);
    }
    flowSvg.append(g);
    const L = path.getTotalLength();
    path.style.strokeDasharray = `${L} ${L}`;
    path.style.strokeDashoffset = `${L}`;
    const p = { g, lab, path, dot, L, t0: performance.now() + delay, dur, to, done: false };
    pulses.push(p);
    if (!raf) raf = requestAnimationFrame(frame);
  }
  function stepPulses(now) {
    pulses = pulses.filter((p) => {
      const u = (now - p.t0) / p.dur;
      if (u < 0) { p.g.style.opacity = "0"; if (p.lab) p.lab.style.opacity = "0"; return true; }
      p.g.style.opacity = "";
      if (p.lab) p.lab.style.opacity = u < 1.6 ? "1" : "0";
      const e = u >= 1 ? 1 : 1 - Math.pow(1 - u, 3);
      const pt = p.path.getPointAtLength(p.L * Math.min(1, e));
      p.dot.setAttribute("cx", pt.x.toFixed(1)); p.dot.setAttribute("cy", pt.y.toFixed(1));
      p.path.style.strokeDashoffset = `${(p.L * (1 - Math.min(1, e))).toFixed(1)}`;
      if (u >= 1 && !p.done) {
        p.done = true;
        p.dot.classList.add("is-in");
        if (p.to) { const row = I.rowOf[p.to]; row?.classList.remove("is-hit"); void row?.offsetWidth; row?.classList.add("is-hit"); }
      }
      // the trail fades over the next 0.9 s
      p.g.style.opacity = u > 1 ? String(Math.max(0, 1 - (u - 1) / 1)) : "";
      if (u > 2) { p.g.remove(); p.lab?.remove(); return false; }
      return true;
    });
  }
  function pulseBeat(b) {
    if (unseen()) return;
    const toMap = sheet() !== "full";
    const at = (a) => nodeVisible(a);
    const code = at("code");
    if (b.kind === "feeds") {
      if (!code || !toMap) return;
      b.feeds.forEach((feed, i) => {
        const from = mapPoint(feedPlace(feed, M));
        if (!from) return;
        const kind = M.feeds.find((f) => f.feed === feed)?.kind || (feed === "adsb" || feed === "airline" ? "aircraft" : "weather");
        pulse(arcPath(from, code), CM[kind] || CM.info, { delay: i * 180, dur: 1100, label: FEED_LABEL[feed] || SRC[feed]?.name || feed, from, to: "code" });
      });
    } else if (b.kind === "code") {
      if (!code || !toMap) return;
      const planes = b.flights.map((f) => M.geo.aircraft.find((a) => a.flight === f)).filter((a) => a?.at).slice(0, 6);
      planes.forEach((a, i) => {
        const from = mapPoint(a.at);
        if (from) pulse(arcPath(from, code), CM.aircraft, { delay: i * 120, dur: 1000, from, to: "code" });
      });
    } else if (b.kind === "coord") {
      const p = at("code"), q = at("coord");
      if (p && q) pulse(curvePath([p, q]), C.job, { dur: 700, to: "coord" });
    } else if (b.kind === "skill") {
      const p = at("coord"), g = at("gate"), q = at(b.node);
      if (p && g && q) pulse(curvePath([p, [g[0], g[1] - 12], g, q]), C.job, { dur: 1000, to: b.node });
    } else if (b.kind === "you") {
      const refused = CU.chain.beats.find((x) => x.kind === "coord")?.refused;
      const lastSkill = [...CU.chain.beats].reverse().find((x) => x.kind === "skill");
      const p = at(refused || !lastSkill ? "coord" : lastSkill.node), q = at("you");
      if (!p || !q) return;
      const sp = at("code");
      const pts = refused && sp ? [p, [sp[0], (p[1] + q[1]) / 2], q] : [p, q];
      pulse(curvePath(pts), refused ? C.must : C.job, { dur: 1000, to: "you" });
    }
  }

  // ---- the player: follow (every step up to the newest), paused at the playhead, playing forward
  function setMode(mode, t = P.t) {
    if (P.mode === "catchup" || CU.state === "playing") { stopCatchup(); unlight(); }
    // the visitor took the player before the catch-up began: it does not start over their choice
    if (CU.state === "waiting") CU.state = "done";
    P.mode = mode;
    P.t = t;
    if (mode === "playing") { P.from = t; lastFrame = 0; rmLeft = RM_STEP_MS; if (!raf) raf = requestAnimationFrame(frame); }
    render();
  }
  function frame(ts) {
    raf = 0;
    if (pulses.length) stepPulses(ts);
    if (P.mode === "playing" && M) {
      const dt = lastFrame ? Math.min(0.25, (ts - lastFrame) / 1000) : 0;
      lastFrame = ts;
      const s = steps();
      const end = newestAt(M);
      if (P.rm) {
        rmLeft -= dt * 1000;
        if (rmLeft <= 0) { rmLeft = RM_STEP_MS; P.t = s.find((e) => e.at > P.t)?.at ?? end; }
      } else {
        const next = s.find((e) => e.at > P.t);
        const gap = next ? (next.at - P.t) / (PLAY_SPEED * 1000) : 0;
        if (next && gap > SKIP_OVER_S) P.t = next.at - SKIP_TO_S * PLAY_SPEED * 1000;
        P.t += dt * 1000 * PLAY_SPEED;
      }
      if (!Number.isFinite(end) || P.t >= end) { P.mode = "follow"; P.t = NaN; render(); }
      else if (eventsAt(P.t) !== seenN) render();
      else renderPlayer();
    }
    if (pulses.length || P.mode === "playing") raf = requestAnimationFrame(frame);
  }

  playBtn.addEventListener("click", () => {
    if (P.mode === "playing" || P.mode === "catchup") setMode("paused", P.t);
    else if (P.mode === "follow") setMode("paused", newestAt(M));
    else {
      const s = steps();
      setMode("playing", P.t >= newestAt(M) && s.length ? s[0].at : P.t);
    }
  });
  again.addEventListener("click", () => { if (M) startCatchup(); });
  track.addEventListener("pointerdown", (ev) => {
    const s = steps();
    if (s.length < 2) return;
    const r = track.getBoundingClientRect();
    const frac = Math.min(1, Math.max(0, (ev.clientX - r.left) / Math.max(1, r.width)));
    setMode("playing", s[0].at + frac * (s[s.length - 1].at - s[0].at));
  });
  track.addEventListener("keydown", (ev) => {
    const s = steps();
    if (!s.length) return;
    const t = playhead();
    let to = null;
    if (ev.key === "ArrowRight") to = s.find((e) => e.at > t)?.at ?? null;
    else if (ev.key === "ArrowLeft") to = [...s].reverse().find((e) => e.at < t)?.at ?? null;
    else if (ev.key === "Home") to = s[0].at;
    else if (ev.key === "End") { ev.preventDefault(); setMode("follow", NaN); return; }
    else if (ev.key === " ") { ev.preventDefault(); playBtn.click(); return; }
    else return;
    ev.preventDefault();
    if (to != null) setMode("paused", to);
  });
  log.addEventListener("click", (ev) => {
    if (!ev.target.closest(".log__more")) return;
    showAll = !showAll;
    render();
    log.querySelector(".log__more")?.focus({ preventScroll: true });
  });
  window.matchMedia("(prefers-reduced-motion: reduce)").addEventListener?.("change", () => { P.rm = reducedMotion(); if (P.rm) clearPulses(); render(); });
  // the rails follow the panel's size and the theme
  new ResizeObserver(() => drawRails()).observe(I.panel);
  new MutationObserver(() => drawRails(true)).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", () => drawRails(true));
  // the page scrolls or resizes: a pulse in flight would point at an old place
  host.addEventListener("scroll", () => { if (selfScroll) { selfScroll = false; return; } clearPulses(); }, { passive: true });
  window.addEventListener("resize", clearPulses);

  return {
    update(model, { conn = null } = {}) {
      M = model?.ready ? model : null;
      log.classList.toggle("is-stale", !!conn?.lostAt);
      // the chain is read again with each model, never while it plays (its beats are fixed)
      if (M && CU.state !== "playing") CU.chain = lastChain(M);
      render();
      maybeStart();
    },
    // the tab was shown, a dialog closed or the sheet opened: the catch-up may start, or go on
    poke() {
      maybeStart();
      if (CU.state === "playing" && CU.held && !CU.timer && !unseen()) nextBeat();
      drawRails(true);
    },
  };
}
