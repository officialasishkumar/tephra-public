// "AI at work" (docs/UI-DESIGN.md 7.21): the board as a full overlay, a native modal <dialog>
// (#board) opened from the AI chip, the story's trust line, Details › AI helpers or the A key.
// Feeds → Duty Officer → the six specialists → a dispatcher at the Desk, with the hand-out edges
// drawn in SVG between the cards from their measured places. The model is board.js. Every string
// goes in through el() (textContent); model-written text (the Duty Officer's brief) carries the
// AI-written mark. The board is rebuilt only when what it shows changes, so live updates never
// flicker, restart an animation or move the reader's scroll; focus survives by data-focus.

import { $, el, icon, hhmmz } from "./util.js";
import { dkDot, dkChip, dkAbout } from "./dk.js";
import { aiMark } from "./x-parts.js";
import { STATE_WORD } from "./board.js";

const ICON = {
  duty: "i-agent", plume: "i-eruption", sat: "i-satellite", planner: "i-route", drafter: "i-pen-line", recovery: "i-recovery",
  sra: "i-file", notice: "i-clipboard", ask: "i-chat", messages: "i-send", handover: "i-dispatcher",
};
// Shape, colour and word for each state (UI-DESIGN 3.2: never colour alone). AI steps that gave
// nothing are caution, never red (docs/UI-AI-QUIET.md Q4): "No result" has the warning shape,
// "Not run" the caution dot.
const STATE_LOOK = {
  working: { pill: "running", spin: true }, waiting: { pill: "caution", icon: "i-clock" }, queued: { pill: "off", icon: "i-clock" },
  failed: { pill: "caution", icon: "st-caution" }, notrun: { pill: "caution" }, done: { pill: "ok" }, quiet: { pill: "never" },
};
const STEP_TONE = { ok: "ok", info: "info", caution: "caution", quiet: "never", waiting: "caution", queued: "off", working: "running" };
const COUNT_ORDER = ["working", "waiting", "queued", "failed", "notrun", "done", "quiet"];
const COUNT_WORD = { working: "working", waiting: "waiting for AI budget", queued: "queued", failed: "no result", notrun: "not run", done: "done", quiet: "quiet" };

function statePill(state, word = STATE_WORD[state], full = null) {
  const look = STATE_LOOK[state] || STATE_LOOK.quiet;
  const mark = look.spin ? el("span", { class: "spinner board__spin", "aria-hidden": "true" }) : look.icon ? icon(look.icon, `st board__clock board__clock--${state}`) : dkDot(look.pill, "st");
  return el("span", { class: `dk-pill dk-pill--${look.pill} bpill`, title: full }, mark, el("span", { text: word, "aria-hidden": full ? "true" : null }), full ? el("span", { class: "sr-only", text: full }) : null);
}

const stepDot = (tone) => (tone === "waiting" || tone === "queued" ? icon("i-clock", `st board__clock board__clock--${tone}`)
  : tone === "failed" ? icon("st-caution", "st board__clock board__clock--failed")
    : tone === "working" ? el("span", { class: "spinner board__spin", "aria-hidden": "true" }) : dkDot(STEP_TONE[tone] || "info", "st"));
const timeOf = (s) => s.atText || (Number.isFinite(s.at) ? hhmmz(s.at) : "");

// The card's newest result, in one line, with its own shape and its time.
function lastLine(c) {
  const t = timeOf(c.last);
  return el("span", { class: `bcard__last bcard__last--${c.last.tone}` },
    stepDot(c.last.tone),
    el("span", { class: "bcard__lasttext" }, el("span", { text: c.last.text }), t ? el("span", { class: "bcard__time mono", text: ` ${t}` }) : null));
}

function modelFoot(c) {
  const m = c.model;
  return el("span", { class: `bcard__model${m.tone ? ` bcard__model--${m.tone}` : ""}` },
    m.id ? dkChip(m.id, { mono: true, title: "The model this helper calls" }) : null, el("span", { text: m.text }),
    m.closed ? el("span", { class: "bcard__closed", title: m.closed.by === "Google" ? "Google answered that today's free-tier calls for this model are spent. The time is real time." : "TEPHRA's daily budget for this model is used up. The time is real time." },
      icon("i-clock", "st"), el("span", { text: `${m.closed.by === "Google" ? "closed by Google" : "used up"}${m.closed.until ? ` until ${m.closed.until}` : " for today"}` })) : null);
}

function steps(c) {
  const list = el("ol", { class: "bsteps", "aria-label": `${c.name}: newest steps, newest first` },
    ...c.steps.map((s) => el("li", { class: `bstep bstep--${s.tone}` },
      stepDot(s.tone),
      el("span", { class: "bstep__body" },
        el("span", { class: "bstep__text", text: s.text }),
        el("span", { class: "bstep__meta" }, timeOf(s) ? el("span", { class: "mono", text: timeOf(s) }) : null, timeOf(s) ? " · " : null, s.source)),
      s.count > 1 ? el("span", { class: "dk-badge", text: `${s.count}×`, title: `${s.count} times` }) : null)));
  return c.steps.length ? list : el("p", { class: "bsteps__none", text: "Nothing to show yet: no step, no queued work and no result." });
}

function cardSteps(c, open) {
  const links = el("p", { class: "bsteps__links" },
    el("button", { type: "button", class: "link-btn", dataset: { act: "board-details", sec: "trace", focus: `board-trace-${c.id}` }, text: "Every step in How TEPHRA decided ›" }),
    c.id === "duty" ? el("button", { type: "button", class: "link-btn", dataset: { act: "board-details", sec: "ai", focus: "board-ai-duty" }, text: "The full run in Details ›" }) : null);
  const brief = c.brief ? el("div", { class: "bbrief" }, el("p", { class: "bbrief__title", text: "Its brief for the dispatchers" }), el("p", { class: "dk-quote", text: c.brief.text }), aiMark(c.brief.model, c.brief.model ? null : "NO MODEL")) : null;
  return el("div", { id: `bsteps-${c.id}`, class: "bcard__steps", role: "region", "aria-label": `${c.name}: newest steps`, hidden: !open },
    steps(c), c.more ? el("p", { class: "bsteps__more", text: `${c.more} older ${c.more === 1 ? "step is" : "steps are"} in How TEPHRA decided.` }) : null, brief, links);
}

function handoffWords(c) {
  const h = c.handoff;
  if (!h) return null;
  const n = `${h.count} ${h.unit}${h.count === 1 ? "" : "s"}`;
  return h.failed ? `Given ${n} · ${h.failed} failed` : `Given ${n}`;
}

function card(c, ui, edgeState) {
  const open = ui.board.card === c.id;
  const handed = handoffWords(c);
  const btn = el("button", {
    type: "button", class: "bcard__btn", "aria-expanded": open ? "true" : "false", "aria-controls": `bsteps-${c.id}`,
    dataset: { act: "board-card", id: c.id, focus: `board-card-${c.id}`, anchor: "" },
  },
  el("span", { class: "bcard__top" },
    el("span", { class: "bcard__icon" }, icon(ICON[c.id] || "i-agent")),
    el("span", { class: "bcard__names" }, el("span", { class: "bcard__name", text: c.name }), el("span", { class: "bcard__does", text: c.does })),
    statePill(c.state, c.state === "waiting" && c.waiting?.until ? `Waiting until ${c.waiting.until}` : c.word, c.state === "waiting" && c.waiting?.slot ? `Waiting for AI budget, ${c.waiting.slot}` : null)),
  lastLine(c),
  el("span", { class: "bcard__foot" }, modelFoot(c),
    handed ? el("span", { class: `bcard__handed${c.handoff.failed ? " bcard__handed--failed" : ""}`, text: handed }) : null,
    c.recorded ? el("span", { class: "tag tag--replay", title: c.recorded, text: "first-pass answer" }) : null,
    el("span", { class: "sr-only", text: edgeState === "idle" ? " No job from the Duty Officer's latest run." : "" })),
  icon("i-chevron-down", "icon bcard__chev"));
  return el("article", { class: `bcard bcard--${c.state}${edgeState === "live" ? " is-live" : ""}${open ? " is-open" : ""}`, dataset: { node: c.id } }, btn, cardSteps(c, open));
}

function dutyCard(c, ui) {
  const open = ui.board.card === "duty";
  const r = c.run;
  const stat = (n, label, tone = null) => el("span", { class: `bstat${tone ? ` bstat--${tone}` : ""}` }, el("span", { class: "bstat__n", text: String(n) }), el("span", { class: "bstat__l", text: label }));
  const btn = el("button", {
    type: "button", class: "bcard__btn", "aria-expanded": open ? "true" : "false", "aria-controls": "bsteps-duty",
    dataset: { act: "board-card", id: "duty", focus: "board-card-duty", anchor: "" },
  },
  el("span", { class: "bcard__top" },
    el("span", { class: "bcard__icon bcard__icon--lead" }, icon(ICON.duty)),
    el("span", { class: "bcard__names" }, el("span", { class: "bcard__name", text: c.name }), el("span", { class: "bcard__does", text: "Coordinator", title: c.does })),
    statePill(c.state)),
  r ? el("span", { class: "bstats", "aria-label": "Its latest run" },
    stat(r.given, r.given === 1 ? "job given" : "jobs given"),
    stat(r.mandatory, "must do", r.mandatory ? null : "muted"),
    stat(r.handed, "handed out", r.handed ? null : "muted"),
    stat(r.undone, "to the Desk", r.undone ? "caution" : "muted"),
    r.later ? stat(r.later, "left for later") : null,
    c.waiting ? stat(c.waiting.n, "wait for AI budget", "caution") : null) : null,
  lastLine(c),
  el("span", { class: "bcard__foot" }, modelFoot(c), c.recorded ? el("span", { class: "tag tag--replay", title: c.recorded, text: "first-pass answer" }) : null),
  icon("i-chevron-down", "icon bcard__chev"));
  return el("article", { class: `bcard bcard--lead bcard--${c.state}${open ? " is-open" : ""}`, dataset: { node: "duty" } }, btn, cardSteps(c, open));
}

function feedsNode(f, replay) {
  const words = [`${f.working} working`, f.stale ? `${f.stale} stale` : null, f.failing ? `${f.failing} failing` : null, f.off ? `${f.off} off` : null].filter(Boolean).join(" · ");
  return el("section", { class: "bnode bnode--feeds", dataset: { node: "feeds" }, "aria-labelledby": "bfeeds-title" },
    el("p", { class: "bnode__kicker" }, icon(replay ? "i-replay" : "i-live"), el("span", { id: "bfeeds-title", text: replay ? "Public feeds, recorded" : "Public feeds" })),
    el("p", { class: "bnode__title", text: words || "No feed read yet" }),
    f.shown.length ? el("ul", { class: "bfeeds", "aria-label": "Feeds that are on" }, ...f.shown.map((x) => el("li", { class: "bfeeds__item" }, dkDot(x.tone, "st"), el("span", { text: x.name })))) : null,
    el("p", { class: "bnode__note", text: "Code reads them every minute and finds the AI work that is due." }));
}

function gateNode(g, desk) {
  const drafts = g.drafts;
  const big = drafts == null
    ? el("p", { class: "bgate__big" }, el("span", { class: "bgate__words", text: "Advisory count unknown (database error)" }))
    : el("p", { class: "bgate__big" }, el("span", { class: "bgate__n", text: String(drafts) }), el("span", { class: "bgate__words", text: drafts === 1 ? "advisory waits for a dispatcher" : "advisories wait for a dispatcher" }));
  return el("section", { class: "bnode bnode--gate", dataset: { node: "gate" }, "aria-labelledby": "bgate-title" },
    el("p", { class: "bnode__kicker bnode__kicker--human" }, icon("i-hand"), el("span", { id: "bgate-title", text: "A dispatcher decides" })),
    big,
    g.others.length ? el("ul", { class: "bgate__list" }, ...g.others.map((o) => el("li", {}, dkDot(o.tone, "st"), el("span", { text: o.text })))) : null,
    el("a", { class: "cta bgate__cta", href: "/desk", target: "_blank", rel: "noopener", dataset: { focus: "board-desk" } }, "Open the Desk ", el("span", { "aria-hidden": "true", text: "→" })),
    el("p", { class: "bnode__note", text: "Nothing leaves TEPHRA until a dispatcher approves it, and then only to its own outbound queue." }),
    el("div", { class: "bgate__oncall" },
      el("p", { class: "bgate__oncall-title", text: "On call at the Desk, when a dispatcher asks" }),
      el("ul", { class: "bgate__chips" }, ...desk.map((d) => el("li", { class: `bchip bchip--${d.state}`, title: `${d.name}: ${d.does}. ${d.word}${Number.isFinite(d.at) ? ` ${hhmmz(d.at)}` : ""}.` },
        d.state === "working" ? el("span", { class: "spinner board__spin", "aria-hidden": "true" }) : dkDot(STATE_LOOK[d.state]?.pill || "never", "st"),
        el("span", { text: d.name }), el("span", { class: "sr-only", text: `: ${d.word.toLowerCase()}` }))))));
}

// The REPLAY band stays in the board's fixed head, so it is on screen however far the board scrolls.
function replayBand(m) {
  if (!m.replay || !m.replayInfo) return [];
  const r = m.replayInfo;
  return [el("div", { class: "replay-banner board__replay", role: "note" },
    icon("i-replay"), el("span", { class: "replay-banner__text", text: r.banner }), el("span", { class: "replay-banner__short", text: r.banner.replace(/recorded real feeds from/i, "recorded") }),
    el("span", { class: "replay-banner__live", text: " · not live" }), el("span", { class: "replay-banner__case", text: ` · ${r.label}` }))];
}

// The AI's one state in the AI chip's words (wall/x-parts.js aiWords); the full sentence is its title.
function aiPill(ai) {
  const w = ai.words;
  const tone = { off: "off", caution: "caution", on: "ok" }[w.tone] || "off";
  const mark = ai.kind === "on" ? dkDot("ok", "st") : icon(ai.kind === "off" ? "i-code" : ai.kind === "paused" ? "i-pause" : "st-caution", "st");
  return el("span", { class: `dk-pill dk-pill--${tone}`, title: w.title }, mark, el("span", { text: w.suffix ? `${w.label} · ${w.suffix}` : w.label }));
}

function header(m, conn) {
  const parts = [];
  const counts = COUNT_ORDER.filter((k) => m.counts[k]).map((k) => el("li", { class: `bcount bcount--${k}` },
    k === "working" ? el("span", { class: "spinner board__spin", "aria-hidden": "true" }) : STATE_LOOK[k].icon ? icon(STATE_LOOK[k].icon, `st board__clock board__clock--${k}`) : dkDot(STATE_LOOK[k].pill, "st"),
    el("span", { class: "bcount__n", text: String(m.counts[k]) }), el("span", { text: COUNT_WORD[k] })));
  const total = COUNT_ORDER.reduce((n, k) => n + m.counts[k], 0);
  parts.push(el("div", { class: "board__bar" },
    el("div", { class: "board__pills" },
      aiPill(m.ai),
      conn.lostAt ? el("span", { class: "dk-pill dk-pill--caution" }, dkDot("stale", "st"), el("span", { text: `Not updating since ${hhmmz(conn.lostAt)}` })) : null,
      m.replay ? el("span", { class: "board__clocknote", text: "Times are on the replay clock. AI budget times (waiting until, closed until) are real time." }) : null),
    el("ul", { class: "board__counts", "aria-label": `${total} helpers by state` }, ...counts),));
  // the calm lead, the same words as Details › AI helpers and the Desk's AI today sheet
  parts.push(el("div", { class: "board__lead" }, ...m.ai.lead.map((p) => el("p", {}, el("strong", { text: p.strong }), ` ${p.text}`)),
    el("button", { type: "button", class: "link-btn", dataset: { act: "board-details", sec: "ai", focus: "board-ai-home" }, text: "Models, today's calls and causes in Details › AI helpers ›" })));
  parts.push(el("p", { class: "sr-only", role: "status", text: `${total} helpers: ${COUNT_ORDER.filter((k) => m.counts[k]).map((k) => `${m.counts[k]} ${COUNT_WORD[k]}`).join(", ")}.` }));
  return parts;
}

function flow(m, ui) {
  const edgeTo = Object.fromEntries(m.edges.filter((e) => e.from === "duty").map((e) => [e.to, e.state]));
  const latest = m.duty.run ? ` · latest run ${hhmmz(m.duty.run.at)}` : "";
  return el("div", { class: "flow" },
    el("div", { class: "flow__lead" }, feedsNode(m.feeds, m.replay), dutyCard(m.duty, ui)),
    el("section", { class: "flow__team", "aria-labelledby": "bteam-title" },
      el("div", { class: "flow__teamhead" }, el("h3", { id: "bteam-title", class: "flow__h", text: "Specialists" }), el("span", { class: "flow__aside", text: `handed work by the Duty Officer${latest}` })),
      el("ul", { class: "flow__cards", dataset: { node: "team" } }, ...m.team.map((c) => el("li", {}, card(c, ui, edgeTo[c.id]))))),
    gateNode(m.gate, m.desk));
}

function foot(m) {
  return el("div", { class: "board__foot" },
    dkAbout("How to read this board", "board",
      "Lines run from the Duty Officer to each specialist. A solid line means its latest run handed that helper work, a dashed line means it did not. A line lights up for a few seconds as a hand-out happens.",
      "Each card shows what the helper is doing now, its newest result and when, and the model it calls. Open a card for its newest steps, each with its time and where it came from.",
      `Calls today are counted per model, the way Google's free tier counts them, not per helper: the lite model's count is shared by every helper on it. Waiting work keeps its place and runs on the same model when its slot comes.`,
      `Nothing here is scripted. Every line comes from TEPHRA's own records: the Duty Officer's run, the AI work queue and the newest ${m.window} steps in How TEPHRA decided. A card with nothing to show says so.`),
    m.disclaimer ? el("p", { class: "board__disclaimer" }, icon("i-info"), el("strong", { text: m.disclaimer })) : null);
}

function loading() {
  return [el("div", { class: "board__loading", role: "status" }, el("span", { class: "spinner", "aria-hidden": "true" }), el("span", { text: "Connecting to TEPHRA…" })),
    el("div", { class: "skeleton" }), el("div", { class: "skeleton" }), el("div", { class: "skeleton" })];
}

// Build the board into #board-status and #board-body; rebuilt only when `key` changes.
export function renderBoard(m, ui, conn) {
  const status = $("board-status");
  const body = $("board-body");
  const key = JSON.stringify([m, ui.board.card, conn.lostAt || 0]);
  if (body.dataset.key === key) return false;
  body.dataset.key = key;
  const top = body.scrollTop;
  if (!m.ready) {
    status.replaceChildren();
    body.replaceChildren(...loading());
    return true;
  }
  status.replaceChildren(...replayBand(m));
  body.classList.toggle("is-stale", !!conn.lostAt);
  const f = flow(m, ui);
  body.replaceChildren(...header(m, conn), f, foot(m));
  body.scrollTop = top;
  drawEdges(f, m.edges);
  return true;
}

// ------------------------------------------------------------------ edges (SVG, measured)

const NS = "http://www.w3.org/2000/svg";
const svgEl = (tag, attrs = {}) => {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v));
  return n;
};
const EDGE_STATES = ["idle", "used", "live", "failed"];

function boxOf(node, origin) {
  const a = node.querySelector("[data-anchor]") || node;
  const r = node.getBoundingClientRect();
  const h = a.getBoundingClientRect();
  return { left: r.left - origin.left, right: r.right - origin.left, top: r.top - origin.top, bottom: r.bottom - origin.top, cx: (r.left + r.right) / 2 - origin.left, cy: (h.top + h.bottom) / 2 - origin.top };
}

// An elbow from a to b. Right of a: out of its right side, a vertical at the midpoint, into b's
// left side (a bracket when several share a source or a target). Below a: down a trunk just left
// of b, then into b's left side; or straight down when b is not indented.
function route(a, b) {
  const r = 8;
  if (b.left >= a.right - 1) {
    const x1 = a.right, x2 = b.left - 3, y1 = a.cy, y2 = b.cy, mx = x1 + (x2 - x1) / 2;
    const dy = y2 - y1;
    if (Math.abs(dy) < 1) return `M${x1},${y1} H${x2}`;
    const s = Math.sign(dy), q = Math.min(r, Math.abs(dy) / 2, (x2 - x1) / 4);
    return `M${x1},${y1} H${mx - q} Q${mx},${y1} ${mx},${y1 + s * q} V${y2 - s * q} Q${mx},${y2} ${mx + q},${y2} H${x2}`;
  }
  if (b.left - a.left > 16) {
    const x = b.left - 16, q = Math.min(r, (b.cy - a.bottom) / 2);
    return `M${x},${a.bottom} V${b.cy - q} Q${x},${b.cy} ${x + q},${b.cy} H${b.left - 3}`;
  }
  return `M${a.cx},${a.bottom} V${b.top - 3}`;
}

export function drawEdges(flowEl, edges) {
  if (!flowEl?.isConnected) return;
  // The old drawing goes first: measured with it, the flow would keep the width it had before a
  // resize (the lines' own box counts in scrollWidth), and a phone would scroll sideways.
  flowEl.querySelector(".flow__edges")?.remove();
  const origin = flowEl.getBoundingClientRect();
  const node = (id) => flowEl.querySelector(`[data-node="${CSS.escape(id)}"]`);
  const svg = svgEl("svg", { class: "flow__edges", width: flowEl.scrollWidth, height: flowEl.scrollHeight, "aria-hidden": "true", focusable: "false" });
  const defs = svgEl("defs");
  for (const s of EDGE_STATES) {
    const mk = svgEl("marker", { id: `bm-${s}`, viewBox: "0 0 8 8", refX: 6, refY: 4, markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse", markerUnits: "userSpaceOnUse" });
    mk.append(svgEl("path", { d: "M0,0 L8,4 L0,8 z", class: `edge-head edge-head--${s}` }));
    defs.append(mk);
  }
  svg.append(defs);
  const team = node("team");
  const gate = node("gate");
  // Stacked (narrow): the gate sits under the list, so one edge runs from the list into it.
  const gateBelow = team && gate && gate.getBoundingClientRect().top >= team.getBoundingClientRect().bottom - 1;
  const toGate = edges.filter((e) => e.to === "gate");
  const drawn = gateBelow
    ? [...edges.filter((e) => e.to !== "gate"), { from: "team", to: "gate", state: toGate.some((e) => e.state === "used") ? "used" : "idle" }]
    : edges;
  for (const e of drawn) {
    const from = node(e.from), to = node(e.to);
    if (!from || !to) continue;
    const d = route(boxOf(from, origin), boxOf(to, origin));
    svg.append(svgEl("path", { d, class: `edge edge--${e.state}`, "marker-end": `url(#bm-${e.state})` }));
  }
  flowEl.prepend(svg);
  if (observer && last?.flowEl !== flowEl) {
    if (last) observer.unobserve(last.flowEl);
    observer.observe(flowEl);
  }
  last = { flowEl, edges };
}

// Redraw the edges when the board or its flow changes size (a resize, a font that loaded late).
let last = null;
let observer = null;
export function watchEdges(body) {
  if (observer || !("ResizeObserver" in window)) return;
  observer = new ResizeObserver(() => { if (last?.flowEl.isConnected) drawEdges(last.flowEl, last.edges); });
  observer.observe(body);
}
