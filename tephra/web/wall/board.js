// "AI at work" (docs/UI-DESIGN.md 7.21): the model behind the board that shows the Duty Officer
// handing work to the specialist helpers and a dispatcher deciding at the end. Pure functions over
// data the Wall already holds: the newest Duty Officer run (snapshot.duty), the AI budget and its
// work queue (/api/budget), the trace, the airport plans, the paperwork list, the advisories and
// the satellite readings. Nothing here is scripted: a card with no data says so. No DOM, so the
// board's logic is tested on its own (tests/test_wall_board.py).

import { ms } from "./util.js";
import { plainLine, planFailure, actionPlain, aiStateOf, aiErrorsOf, newestPlan, aiWords, aiLead, reasonClass, realWhen, WHY } from "./x-parts.js";
import { collapseRuns, plural } from "./dk.js";

// Every AI helper on the Wall, in board order. `tool` is the Duty Officer tool that reaches it,
// `kinds` the work-list kinds it does (MODULES.md 5.18), `tier` the model tier it calls,
// `to` where its work goes ("desk": a draft a dispatcher decides on; "area": TEPHRA's estimate).
// The Desk helpers run only when a dispatcher asks.
export const HELPERS = [
  { id: "duty", role: "lead", name: "Duty Officer", does: "Orders the day's AI work and hands it out", stage: "DUTY", tier: "lite" },
  { id: "plume", role: "team", name: "Plume Reader", does: "Proposes TEPHRA's cautious area", stage: "PLUME", tool: "assess_volcanoes", kinds: ["ASSESS"], tier: "main", to: "area", when: "It runs when a volcano's reports change and the call matters" },
  { id: "sat", role: "team", name: "Satellite reader", does: "Reads the satellite picture", stage: "SATELLITE", tool: "assess_volcanoes", kinds: ["ASSESS"], tier: "lite", to: "area", when: "It runs inside a plume read, when a new picture has come in" },
  { id: "planner", role: "team", name: "Flight planner", does: "Chooses an action for each flight", stage: "PLANNER", tool: "plan_flights", kinds: ["PLAN"], tier: "lite", when: "It runs for each RFA flight in or heading into an area" },
  { id: "drafter", role: "team", name: "Drafter", does: "Writes each flight's advisory", stage: "DRAFTER", tool: "plan_flights", kinds: ["PLAN"], tier: "lite", to: "desk", when: "It runs after the flight planner, for each flight" },
  { id: "recovery", role: "team", name: "Recovery planner", does: "Re-plans flights around closed airports", stage: "RECOVERY", tool: "run_recovery", kinds: ["RECOVER"], tier: "lite", to: "desk", when: "It runs when the set of airports closed by ash changes" },
  { id: "sra", role: "team", name: "Paperwork drafter", does: "Drafts the safety risk assessment", stage: "DOCS", tool: "draft_sra", kinds: ["SRA"], tier: "lite", to: "desk", when: "It runs when a region newly carries exposed flights" },
  { id: "notice", role: "desk", name: "Notice reader", does: "Reads pasted notices", stage: "NOTICE", tier: "lite" },
  { id: "ask", role: "desk", name: "Ask", does: "Answers questions from the data", stage: "ASK", tier: "lite" },
  { id: "messages", role: "desk", name: "Messages", does: "Drafts crew and passenger messages", stage: "MESSAGES", skip: /HANDOVER/i, tier: "lite" },
  { id: "handover", role: "desk", name: "Handover", does: "Writes the shift handover", stage: "MESSAGES", only: /HANDOVER/i, tier: "lite" },
];

// What one hand-out covers, per tool: "24 flights", "1 volcano".
export const TOOL_UNIT = { assess_volcanoes: "volcano", plan_flights: "flight", run_recovery: "network re-plan", draft_sra: "region" };

// A step this recent counts as the helper working on it now; a hand-out this recent lights its edge.
export const LIVE_MS = 6000;
// Steps shown when a card opens (Aegis's lesson in research/16: short bullets, not a wall of reasoning).
export const STEPS_SHOWN = 5;

// The card states, in the order one wins over another. Shape, colour and word for each are the
// view's (board-view.js); every state has all three. An AI step that gave nothing is a caution,
// never the picture's red (docs/UI-AI-QUIET.md Q4): "No result" when a model was called and gave
// nothing usable, "Not run" when no model was called.
export const STATES = ["working", "waiting", "queued", "failed", "notrun", "done", "quiet"];
export const STATE_WORD = {
  working: "Working", waiting: "Waiting for AI budget", queued: "Queued", failed: "No result",
  notrun: "Not run", done: "Done", quiet: "Quiet",
};

const SOURCE = {
  trace: "How TEPHRA decided", queue: "AI work queue", run: "Duty Officer run", plan: "Airport plan",
  reading: "Satellite reading", doc: "Paperwork", advisory: "Advisories", estimate: "TEPHRA's estimate",
};

// A step's tone: "failed" (a model was called and gave nothing usable) and "caution" (no model
// was called, or code found nothing) both draw in caution; the card state tells them apart.
const LEVEL_TONE = { warn: "caution" };
// A Duty Officer line that is about one helper's work: it is that helper's step too.
const NOT_HANDED = /^Plume read: .+: not dispatched/;

const matches = (h, t) => t.stage === h.stage && (!h.skip || !h.skip.test(t.message || "")) && (!h.only || h.only.test(t.message || ""));

function ownLines(h, trace) {
  return trace.filter((t) => matches(h, t) || (h.id === "plume" && t.stage === "DUTY" && NOT_HANDED.test(t.message || "")));
}

// The tone of one trace line, as a step: a plume read the Duty Officer did not hand out is "not run"
// (caution), not a Plume Reader failure.
function lineTone(h, t) {
  if (h.id === "plume" && t.stage === "DUTY") return "caution";
  if (t.level === "error") return reasonClass(t.message) === "budget" ? "caution" : "failed";
  return LEVEL_TONE[t.level] || "ok";
}

// Trace lines as steps: repeats collapse into one step with a count (Langfuse's aggregated view).
function traceSteps(h, lines) {
  const runs = collapseRuns(lines.map((t) => ({ ...t, _t: ms(t.at) })), {
    textOf: (t) => plainLine(t.message), timeOf: (t) => t._t, groupOf: (t) => `${t.stage}|${t.level}`,
  });
  return runs.map((r) => ({ tone: lineTone(h, r.items[0]), text: r.label, count: r.count, at: r.last, source: SOURCE.trace, ids: r.items.map((t) => t.id) }));
}

const workOf = (h, work) => (work || []).filter((w) => (w.kind === "recover" && h.kinds?.includes("RECOVER")) || (w.item && h.kinds?.includes(w.item.kind)));

// "next slot 0700Z", or in REPLAY "next slot in 2 h 45 min": budget times are on the real clock
// (realWhen, the AI state's rule).
let clock = { now: Date.now(), replay: false };
const slotText = (at) => { const w = realWhen(at, clock.now, clock.replay); return w ? `next slot ${w.at}` : null; };

function queueSteps(items) {
  const out = [];
  for (const status of ["RUNNING", "WAITING", "QUEUED"]) {
    const list = items.filter((w) => w.status === status);
    if (!list.length) continue;
    const slot = Math.min(...list.map((w) => ms(w.next_slot_at)).filter(Number.isFinite));
    const first = list[0].label;
    const more = list.length > 1 ? ` and ${plural(list.length - 1, "more job")}` : "";
    const what = status === "RUNNING" ? "Running now" : status === "WAITING" ? "Waiting for AI budget" : "Queued for the AI worker";
    out.push({
      tone: status === "WAITING" ? "waiting" : status === "RUNNING" ? "working" : "queued",
      text: `${what}: ${first}${more}`, count: 1, at: status === "WAITING" ? slot : NaN,
      atText: status === "WAITING" ? slotText(slot) : null, source: SOURCE.queue, now: true,
    });
  }
  return out;
}

// The latest run's hand-outs to one tool: how many items, how many failed, when.
export function handoff(run, tool) {
  if (!run || !tool) return null;
  const mine = (run.dispatches || []).filter((d) => d.tool === tool);
  if (!mine.length) return null;
  const items = new Set(mine.flatMap((d) => d.item_ids));
  return { count: items.size, failed: mine.filter((d) => !d.ok).length, calls: mine.length, at: ms(run.finished_at), unit: TOOL_UNIT[tool] || "job" };
}

function handoffStep(h, run) {
  const ho = handoff(run, h.tool);
  if (!ho) return null;
  const what = plural(ho.count, ho.unit);
  const failed = ho.failed ? `, ${ho.failed} of ${ho.calls} failed` : "";
  return { tone: ho.failed ? "failed" : "ok", text: `Given ${what} by the Duty Officer in its latest run${failed}`, count: 1, at: ho.at, source: SOURCE.run };
}

// The helpers' own results beside the trace: the newest airport plan, satellite reading,
// safety risk assessment draft and advisory.
// The Plume Reader's outcome per volcano, as code recorded it on each assessment; volcanoes with the
// same outcome share one step ("Semeru, Ibu and 2 more: ...").
const PLUME_OUTCOME = {
  ACCEPTED: ["ok", "its estimate passed the code's checks"],
  REPAIRED: ["ok", "its estimate passed the checks after one repair"],
  STUB: ["ok", "estimate by code (AI off), the official area"],
  MODEL_FAILED: ["failed", "no estimate passed the checks, so the area stays at the official reports"],
  PENDING: ["caution", "plume read waits for the Duty Officer, the area stays at the official reports until it runs"],
  OFFICIAL_ONLY: ["info", "no read needed, the official reports alone set the area"],
};

function names(list) {
  return list.length <= 3 ? list.join(", ").replace(/, ([^,]*)$/, " and $1") : `${list.slice(0, 2).join(", ")} and ${list.length - 2} more`;
}

function plumeSteps(ctx) {
  const by = new Map();
  for (const sit of ctx.situations) {
    const a = sit.assessment;
    if (!a || !PLUME_OUTCOME[a.outcome]) continue;
    const g = by.get(a.outcome) || { names: [], at: -Infinity, recorded: null };
    g.names.push(sit.volcano_name);
    g.at = Math.max(g.at, ms(a.created_at));
    g.recorded = g.recorded || a.recorded_answer || null;
    by.set(a.outcome, g);
  }
  return [...by].map(([outcome, g]) => {
    const [tone, words] = PLUME_OUTCOME[outcome];
    return { tone, text: `${names(g.names)}: ${words}`, count: 1, at: g.at, source: SOURCE.estimate, recorded: g.recorded };
  });
}

function resultSteps(h, ctx) {
  const out = [];
  if (h.id === "plume") out.push(...plumeSteps(ctx));
  if (h.id === "recovery") {
    const plan = newestPlan(ctx.recovery);
    if (plan) {
      const fail = planFailure(plan);
      const t = plan.chosen?.totals;
      const text = fail ? `${fail.title}. ${fail.sub}`
        : `Airport plan ${plan.status === "DRAFT" ? "waiting on the Desk" : plan.status === "APPROVED" ? "approved" : plan.status === "REJECTED" ? "rejected" : "made"}${t ? `: cancel ${t.cancelled_flights}, delay ${t.delayed_flights}` : ""}`;
      // the solver finding no plan is code's answer, not an AI failure: "No plan", in caution
      out.push({ tone: fail ? (fail.ai ? "failed" : "caution") : "ok", word: fail && !fail.ai ? "No plan" : null, text, count: 1, at: ms(plan.created_at), source: SOURCE.plan });
    }
  }
  if (h.id === "sat") {
    for (const r of ctx.satellite || []) {
      const name = ctx.volcanoName(r.volcano_id);
      const ash = { yes: "ash seen", no: "no ash seen", uncertain: "can't tell" }[r.ash_visible] || "can't tell";
      const text = r.status === "ai_unavailable" ? `${name}: not read (AI unavailable). Nothing was put in its place`
        : r.status === "no_frames" ? `${name}: no picture to read` : `${name}: ${ash}`;
      out.push({ tone: r.status === "ai_unavailable" ? "failed" : r.status === "no_frames" ? "caution" : "ok", text, count: 1, at: ms(r.created_at || r.observed_at), source: SOURCE.reading, recorded: r.recorded_answer || null });
    }
  }
  if (h.id === "sra") {
    const mine = (ctx.docs || []).filter((d) => d.kind === "SRA" && d.replay === ctx.replay).sort((a, b) => ms(b.created_at) - ms(a.created_at));
    if (mine[0]) out.push({ tone: "ok", text: `${mine[0].title}${mine[0].status === "DRAFT" ? ", waiting for sign-off" : ""}`, count: 1, at: ms(mine[0].created_at), source: SOURCE.doc });
  }
  if (h.id === "drafter" || h.id === "planner") {
    const adv = (ctx.advisories || []).filter((a) => a.replay === ctx.replay).sort((a, b) => ms(b.created_at) - ms(a.created_at))[0];
    if (adv) {
      const text = h.id === "drafter" ? `Newest advisory: ${adv.proxy_flight}${adv.status === "DRAFT" ? ", waiting for a dispatcher" : ""}` : `Newest plan: ${adv.proxy_flight}, ${actionPlain(adv.action) || String(adv.action || "").toLowerCase().replace(/_/g, " ")}`;
      out.push({ tone: "ok", text, count: 1, at: ms(adv.created_at), source: SOURCE.advisory, recorded: adv.recorded_answer || null });
    }
  }
  return out;
}

// One model's day, as a card's footer says it.
export function modelLine(tier, ctx) {
  if (ctx.stub) return { id: null, text: "No model (offline stub): no calls", tone: "off" };
  const b = ctx.budget;
  if (!b) return { id: null, text: ctx.budgetError ? "Calls today: unknown, the AI budget did not load" : "Calls today: loading", tone: ctx.budgetError ? "caution" : "off" };
  const t = (b.tiers || []).find((x) => x.tier === tier);
  if (!t) return { id: null, text: "Calls today: unknown", tone: "caution" };
  const m = (b.models || []).find((x) => x.model_id === t.model_id);
  const shared = (b.tiers || []).filter((x) => x.model_id === t.model_id).length > 1 || (m && /every other/i.test(m.jobs || ""));
  const reset = realWhen(ms(b.resets_at), clock.now, clock.replay);
  const out = Boolean(m?.closed) || t.remaining <= 0;
  // A closed day's limit means nothing to the reader ("1 of 450" while no call can go), so the
  // count stands alone and the closing says why and until when.
  const count = out ? plural(t.used, "call") : `${t.used.toLocaleString("en")} of ${t.limit.toLocaleString("en")} calls`;
  return {
    id: t.model_id, text: `${count} today${shared ? ", shared" : ""}`,
    closed: out ? { until: reset?.until || null, by: m?.closed ? "Google" : "budget" } : null, tone: null,
  };
}

function recordedOf(steps) {
  return steps.find((s) => s.recorded)?.recorded || null;
}

function stateOf({ working, waiting, queued, last }) {
  if (working) return "working";
  if (waiting) return "waiting";
  if (queued) return "queued";
  if (!last || last.tone === "info") return "quiet";
  if (last.tone === "failed") return "failed";
  if (last.tone === "caution") return "notrun";
  return "done";
}

function helperCard(h, ctx) {
  const lines = ownLines(h, ctx.trace);
  const newest = lines[lines.length - 1];
  const work = workOf(h, ctx.work);
  const now = queueSteps(work);
  const past = [...traceSteps(h, lines), handoffStep(h, ctx.duty), ...resultSteps(h, ctx)].filter(Boolean).sort((a, b) => (b.at || 0) - (a.at || 0));
  // The card's line is the helper's own newest result; the hand-out has its own chip.
  const last = past.find((x) => x.source !== SOURCE.run) || past[0] || null;
  const arrived = newest ? ctx.arrivedAgo(newest.id) : Infinity;
  const working = work.some((w) => w.status === "RUNNING") || arrived < LIVE_MS;
  const waiting = work.filter((w) => w.status === "WAITING");
  const queued = work.filter((w) => w.status === "QUEUED");
  const state = stateOf({ working, waiting: waiting.length, queued: queued.length, last });
  const slot = Math.min(...waiting.map((w) => ms(w.next_slot_at)).filter(Number.isFinite));
  return {
    id: h.id, role: h.role, name: h.name, does: h.does, to: h.to || null, state, word: (state === "failed" || state === "notrun") && last.word ? last.word : STATE_WORD[state],
    last: last || { tone: "quiet", text: `Nothing in the newest ${plural(ctx.trace.length, "step")}. ${h.when}.`, at: NaN, source: SOURCE.trace },
    waiting: waiting.length ? { n: waiting.length, slot: slotText(slot), until: realWhen(slot, clock.now, clock.replay)?.until || null } : null,
    queued: queued.length,
    handoff: handoff(ctx.duty, h.tool),
    model: modelLine(h.tier, ctx),
    recorded: recordedOf(past),
    steps: [...now, ...past].slice(0, STEPS_SHOWN),
    more: Math.max(0, now.length + past.length - STEPS_SHOWN),
  };
}

// The Duty Officer's latest run in one sentence (code-written from the run's fields), in the words
// of Details › AI helpers (wall/duty.js OUTCOME): a quota refusal called no model and is "Not
// run"; a run whose brief failed the checks called one and is "No brief".
export function dutyLine(run, ctx) {
  const n = (run.dispatches || []).length;
  const handed = new Set((run.dispatches || []).flatMap((d) => d.item_ids)).size;
  const undone = (run.undispatched || []).length;
  const later = (run.deferred || []).length;
  const tail = [later ? `Left ${plural(later, "optional job")} for later.` : null, undone ? `Passed ${plural(undone, "must-do job")} to the Desk.` : null].filter(Boolean).join(" ");
  const first = n ? ` It handed out ${plural(handed, "job")} first.` : "";
  if (run.outcome === "MODEL_FAILED") {
    const cls = reasonClass((run.validation_errors || [])[0]);
    if (cls === "budget") return { tone: "caution", word: "Not run", text: `Not run: today's free AI quota is used up${ctx.until ? ` (AI paused ${ctx.until})` : ""}. No brief was made.${first}${tail ? ` ${tail}` : ""}` };
    return { tone: "failed", word: "No brief", text: `No brief: AI unavailable (${WHY[cls] || WHY.other}). Nothing was made up in its place.${first}${tail ? ` ${tail}` : ""}` };
  }
  if (run.outcome === "STUB") return { tone: "ok", text: `Handed out ${plural(handed, "job")} in urgency order (AI off).${tail ? ` ${tail}` : ""}` };
  const checks = run.outcome === "REPAIRED" ? "Its brief passed after one repair." : "Its brief passed the code's checks.";
  return { tone: "ok", text: `${handed ? `Handed out ${plural(handed, "job")}.` : "Handed out no job."} ${checks}${tail ? ` ${tail}` : ""}` };
}

function dutyCard(ctx) {
  const h = HELPERS[0];
  const run = ctx.duty;
  const lines = ownLines(h, ctx.trace);
  const newest = lines[lines.length - 1];
  const items = (ctx.work || []).filter((w) => w.kind === "duty_item");
  const working = items.some((w) => w.status === "RUNNING") || (newest ? ctx.arrivedAgo(newest.id) < LIVE_MS : false);
  const waiting = items.filter((w) => w.status === "WAITING");
  const model = ctx.stub || run?.llm_backend === "stub" ? { id: null, text: "No model (offline stub): no calls", tone: "off" } : modelLine("lite", ctx);
  if (!run) {
    return {
      id: h.id, role: h.role, name: h.name, does: h.does, state: working ? "working" : "quiet", word: STATE_WORD[working ? "working" : "quiet"],
      last: { tone: "quiet", text: "No run yet. It runs when code finds AI work due: a plume to read, a flight to plan, a network to re-plan.", at: NaN, source: SOURCE.run },
      run: null, waiting: waiting.length ? { n: waiting.length } : null, model, recorded: null, steps: traceSteps(h, lines).slice(0, STEPS_SHOWN), more: 0, brief: null,
    };
  }
  const line = dutyLine(run, ctx);
  const at = ms(run.finished_at);
  const mandatory = run.worklist.filter((i) => i.mandatory).length;
  const label = (id) => run.worklist.find((i) => i.id === id)?.label || id;
  const runSteps = [
    { tone: "info", text: `Code gave it ${plural(run.worklist.length, "job")}${mandatory ? `, ${mandatory} of them must do` : ""}`, count: 1, at: ms(run.started_at), source: SOURCE.run },
    { tone: line.tone, text: line.text, count: 1, at, source: SOURCE.run },
    run.undispatched?.length ? { tone: "caution", text: `To the Desk, for a dispatcher: ${label(run.undispatched[0])}${run.undispatched.length > 1 ? ` and ${run.undispatched.length - 1} more` : ""}`, count: 1, at, source: SOURCE.run } : null,
    run.recorded_answer ? { tone: "info", text: `Same answer as the replay's first pass: ${run.recorded_answer}`, count: 1, at, source: SOURCE.run } : null,
  ].filter(Boolean);
  const state = working ? "working" : line.tone === "failed" ? "failed" : line.tone === "caution" ? "notrun" : "done";
  const brief = run.brief && run.outcome !== "MODEL_FAILED" ? { text: run.brief.summary, model: run.outcome === "STUB" || run.llm_backend === "stub" ? null : run.model_id } : null;
  return {
    id: h.id, role: h.role, name: h.name, does: h.does, state, word: !working && line.word ? line.word : STATE_WORD[state],
    last: { tone: line.tone, text: line.text, at, source: SOURCE.run },
    run: {
      given: run.worklist.length, mandatory, handed: new Set((run.dispatches || []).flatMap((d) => d.item_ids)).size,
      undone: (run.undispatched || []).length, later: (run.deferred || []).length, turns: run.turns, at,
    },
    waiting: waiting.length ? { n: waiting.length } : null,
    model, recorded: run.recorded_answer || null, brief,
    steps: runSteps.slice(0, STEPS_SHOWN), more: Math.max(0, runSteps.length - STEPS_SHOWN),
  };
}

const FEED_ORDER = ["sigmet", "vaac_darwin", "vaac_tokyo", "vona", "jma_volcano", "adsb", "winds", "frames", "taf", "metar", "hsd"];

function feedsNode(feeds, names) {
  const sorted = (feeds || []).slice().sort((a, b) => FEED_ORDER.indexOf(a.feed) - FEED_ORDER.indexOf(b.feed));
  const tone = { OK: "ok", STALE: "stale", ERROR: "serious", DISABLED: "off", NEVER: "never" };
  const on = sorted.filter((f) => f.status === "OK" || f.status === "STALE" || f.status === "ERROR");
  const off = sorted.length - on.length;
  return {
    working: sorted.filter((f) => f.status === "OK").length, stale: sorted.filter((f) => f.status === "STALE").length,
    failing: sorted.filter((f) => f.status === "ERROR").length, off,
    shown: on.map((f) => ({ id: f.feed, name: names[f.feed] || f.feed, tone: tone[f.status] || "never" })),
  };
}

function gateNode(ctx) {
  const plan = newestPlan(ctx.recovery);
  // one per region: older unsigned copies of a region's SRA (drafted again by earlier replay
  // runs) are the same work, not more of it
  const sra = [...new Set((ctx.docs || []).filter((d) => d.kind === "SRA" && d.status === "DRAFT" && d.replay === ctx.replay).map((d) => d.region))];
  const others = [];
  if (plan?.status === "DRAFT") others.push({ tone: "caution", text: "1 airport plan waits for approval" });
  else if (plan?.status === "AI_UNAVAILABLE") others.push({ tone: "caution", text: "No airport plan was made: a dispatcher plans the network by hand" });
  if (sra.length) others.push({ tone: "caution", text: `${plural(sra.length, "safety risk assessment draft")} ${sra.length === 1 ? "waits" : "wait"} for sign-off` });
  // the flights the AI made no plan for, said once with the must-do ones in it; without that
  // count (the board alone), the Duty Officer's must-do flights
  const undone = (ctx.duty?.undispatched || []).length;
  if (ctx.handPlan?.n) others.push({ tone: "caution", text: `${plural(ctx.handPlan.n, "flight")} to plan by hand${ctx.handPlan.must ? `, ${ctx.handPlan.must} of them must do` : ""}: the AI made no plan for them` });
  else if (undone) others.push({ tone: "caution", text: `${plural(undone, "must-do flight")} passed to a dispatcher by the latest Duty Officer run, to plan by hand` });
  return { drafts: ctx.drafts, others, docsLoaded: ctx.docsLoaded, planWaits: plan?.status === "DRAFT", sraWaits: sra.length };
}

// Hand-out edges from the Duty Officer to each specialist, and from the helpers whose work goes
// to the Desk into the gate. live: a hand-out arrived in the last LIVE_MS; used: the latest run
// handed it work (failed when a hand-out failed); idle: not in the latest run. Into the gate a
// line is solid while that helper has work waiting there for a dispatcher.
function edges(team, ctx, gate) {
  const out = [{ from: "feeds", to: "duty", state: "used" }];
  for (const c of team) {
    const h = HELPERS.find((x) => x.id === c.id);
    const live = ctx.liveAgo(h.tool) < LIVE_MS;
    const ho = c.handoff;
    out.push({ from: "duty", to: c.id, state: live ? "live" : ho ? (ho.failed ? "failed" : "used") : "idle" });
  }
  const waits = { drafter: (gate.drafts || 0) > 0, recovery: gate.planWaits, sra: gate.sraWaits > 0 };
  for (const c of team) if (c.to === "desk") out.push({ from: c.id, to: "gate", state: waits[c.id] ? "used" : "idle" });
  return out;
}

// The whole board. `input` holds what the Wall already loaded; `arrivedAgo(traceId)` and
// `liveAgo(tool)` give milliseconds since a trace line or a hand-out reached this page.
export function boardModel(input) {
  const s = input.state;
  if (!s) return { ready: false };
  const replay = s.mode === "REPLAY";
  const stub = s.llm?.backend === "stub" || input.budget?.backend === "stub";
  // the Wall's one AI state (docs/UI-AI-QUIET.md 1.2), from the same inputs as its AI chip
  clock = { now: input.realNow ?? Date.now(), replay };
  const ai = aiStateOf({ stub, budget: input.budget || null, errors: aiErrorsOf(input.trace), duty: input.duty || null, plan: newestPlan(input.recovery), replay, now: clock.now });
  const ctx = {
    replay, stub, until: ai.until, trace: input.trace || [], duty: input.duty || null,
    budget: input.budget || null, budgetError: input.budgetError || null, work: Array.isArray(input.budget?.waiting) ? input.budget.waiting : [],
    recovery: input.recovery || [], docs: input.docs || [], docsLoaded: !!input.docsLoaded, satellite: input.satellite || [],
    advisories: input.advisories || [], drafts: s.draft_count, handPlan: input.handPlan || null, situations: input.situations || [],
    volcanoName: (id) => (input.situations || []).find((x) => x.volcano_id === id)?.volcano_name || id,
    arrivedAgo: input.arrivedAgo || (() => Infinity), liveAgo: input.liveAgo || (() => Infinity),
  };
  const duty = dutyCard(ctx);
  const team = HELPERS.filter((h) => h.role === "team").map((h) => helperCard(h, ctx));
  const desk = HELPERS.filter((h) => h.role === "desk").map((h) => {
    const lines = ownLines(h, ctx.trace);
    const newest = lines[lines.length - 1];
    const state = newest ? (newest.level === "error" ? "failed" : ctx.arrivedAgo(newest.id) < LIVE_MS ? "working" : "done") : "quiet";
    return { id: h.id, name: h.name, does: h.does, state, word: STATE_WORD[state], at: newest ? ms(newest.at) : NaN };
  });
  const cards = [duty, ...team];
  const gate = gateNode(ctx);
  const counts = Object.fromEntries(STATES.map((k) => [k, cards.filter((c) => c.state === k).length]));
  return {
    ready: true, replay, stub, mode: s.mode, replayInfo: s.replay || null, disclaimer: s.disclaimer || "",
    ai: { kind: ai.kind, words: aiWords(ai, { home: "Details › AI helpers", opens: "nothing" }), lead: aiLead(ai) },
    budgetLoaded: !!input.budget || !!input.budgetError, budgetError: input.budgetError || null,
    window: ctx.trace.length,
    feeds: feedsNode(input.feeds, input.feedNames || {}),
    duty, team, desk, gate, edges: edges(team, ctx, gate), counts,
  };
}
