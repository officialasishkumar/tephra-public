// "TEPHRA Assistant at work" (docs/UI-DESIGN.md 7.21): the model behind the flow board that shows the
// Coordinator (the code's Duty Officer) handing work to the assistant's other skills and a
// dispatcher deciding at the end. Pure functions over data the Wall already holds: the newest
// Coordinator run (snapshot.duty), the assistant's work queue (/api/budget), the trace, the
// airport plans, the paperwork list, the advisories and the satellite readings. Nothing here is
// scripted: a skill with no data says so. No DOM, so the board's logic is tested on its own
// (tests/test_wall_board.py). flowModel() drives the board; boardModel() gives the Coordinator's and
// each skill's details sheet. The board says "paused" and what waits, never why: the free quota,
// budgets, per-model counts and slot times are said once, at Details › TEPHRA Assistant
// (docs/UI-AI-QUIET.md 8.6 "Say the cause once").

import { ms } from "./util.js";
import { plainLine, planFailure, actionPlain, aiStateOf, aiErrorsOf, newestPlan, aiWords, aiSymbol, causeShort, reasonClass, WHY, ASSISTANT } from "./x-parts.js";
import { collapseRuns, plural } from "./dk.js";

// Every skill of TEPHRA Assistant on the Wall, in board order. `tool` is the Coordinator's tool that reaches it,
// `kinds` the work-list kinds it does (MODULES.md 5.18), `tier` the model tier it calls,
// `to` where its work goes ("desk": a draft a dispatcher decides on; "area": TEPHRA's estimate).
// The Desk skills run only when a dispatcher asks.
export const HELPERS = [
  { id: "duty", role: "lead", name: "Coordinator", does: "Orders the day's assistant work and hands it out", stage: "DUTY", tier: "lite" },
  { id: "plume", role: "team", name: "Plume reader", does: "Proposes TEPHRA's cautious area", stage: "PLUME", tool: "assess_volcanoes", kinds: ["ASSESS"], tier: "main", to: "area", when: "It runs when a volcano's reports change and the call matters" },
  { id: "sat", role: "team", name: "Satellite reader", does: "Reads the satellite picture", stage: "SATELLITE", tool: "assess_volcanoes", kinds: ["ASSESS"], tier: "lite", to: "area", when: "It runs inside a plume read, when a new picture has come in" },
  { id: "planner", role: "team", name: "Flight planner", does: "Chooses an action for each flight", stage: "PLANNER", tool: "plan_flights", kinds: ["PLAN"], tier: "lite", when: "It runs for each RFA flight in or heading into an area" },
  { id: "drafter", role: "team", name: "Drafter", does: "Writes each flight's advisory", stage: "DRAFTER", tool: "plan_flights", kinds: ["PLAN"], tier: "lite", to: "desk", when: "It runs after the flight planner, for each flight" },
  { id: "recovery", role: "team", name: "Recovery planner", does: "Re-plans flights around closed airports", stage: "RECOVERY", tool: "run_recovery", kinds: ["RECOVER"], tier: "lite", to: "desk", when: "It runs when the set of airports closed by ash changes" },
  { id: "sra", role: "team", name: "Paperwork drafter", does: "Drafts the safety risk assessment", stage: "DOCS", tool: "draft_sra", kinds: ["SRA"], tier: "lite", to: "desk", when: "It runs when a region newly carries exposed flights" },
  { id: "notice", role: "desk", name: "Notice reader", does: "Reads pasted notices", stage: "NOTICE", tier: "lite" },
  { id: "ask", role: "desk", name: "Ask", does: "Answers questions from the data", stage: "ASK", tier: "lite" },
  { id: "messages", role: "desk", name: "Message drafter", does: "Drafts crew and passenger messages", stage: "MESSAGES", skip: /HANDOVER/i, tier: "lite" },
  { id: "handover", role: "desk", name: "Handover drafter", does: "Writes the shift handover", stage: "MESSAGES", only: /HANDOVER/i, tier: "lite" },
];

// What one hand-out covers, per tool: "24 flights", "1 volcano".
export const TOOL_UNIT = { assess_volcanoes: "volcano", plan_flights: "flight", run_recovery: "network re-plan", draft_sra: "region" };

// A step this recent counts as the helper working on it now.
export const LIVE_MS = 6000;
// Steps shown when a card opens (Aegis's lesson in research/16: short bullets, not a wall of reasoning).
export const STEPS_SHOWN = 5;

// The card states' words. An assistant step that gave nothing is a caution, never the picture's red
// (docs/UI-AI-QUIET.md Q4): "No result" when a model was called and gave nothing usable, "Not run"
// when no model was called.
export const STATE_WORD = {
  working: "Working", waiting: "Waiting in line", queued: "Queued", failed: "No result",
  notrun: "Not run", done: "Done", quiet: "Quiet",
};

const SOURCE = {
  trace: "How TEPHRA decided", queue: "Assistant work queue", run: "Coordinator run", plan: "Airport plan",
  reading: "Satellite reading", doc: "Paperwork", advisory: "Advisories", estimate: "TEPHRA's estimate",
};

// A step's tone: "failed" (a model was called and gave nothing usable) and "caution" (no model
// was called, or code found nothing) both draw in caution; the card state tells them apart.
const LEVEL_TONE = { warn: "caution" };
// A Coordinator line that is about one skill's work: it is that helper's step too.
const NOT_HANDED = /^Plume read: .+: not dispatched/;

const matches = (h, t) => t.stage === h.stage && (!h.skip || !h.skip.test(t.message || "")) && (!h.only || h.only.test(t.message || ""));

function ownLines(h, trace) {
  return trace.filter((t) => matches(h, t) || (h.id === "plume" && t.stage === "DUTY" && NOT_HANDED.test(t.message || "")));
}

// The tone of one trace line, as a step: a plume read the Coordinator did not hand out is "not run"
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

// The jobs a skill has in the queue, now. A waiting job says that it waits, not when: its slot is
// said at the assistant's home (8.6).
function queueSteps(items) {
  const out = [];
  for (const status of ["RUNNING", "WAITING", "QUEUED"]) {
    const list = items.filter((w) => w.status === status);
    if (!list.length) continue;
    const first = list[0].label;
    const more = list.length > 1 ? ` and ${plural(list.length - 1, "more job")}` : "";
    const what = status === "RUNNING" ? "Running now" : status === "WAITING" ? "Waiting in line" : "Queued for the assistant";
    out.push({
      tone: status === "WAITING" ? "waiting" : status === "RUNNING" ? "working" : "queued",
      text: `${what}: ${first}${more}`, count: 1, at: NaN, atText: status === "WAITING" ? "in line" : null, source: SOURCE.queue, now: true,
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
  return { tone: ho.failed ? "failed" : "ok", text: `Given ${what} by the Coordinator in its latest run${failed}`, count: 1, at: ho.at, source: SOURCE.run };
}

// The skills' own results beside the trace: the newest airport plan, satellite reading,
// safety risk assessment draft and advisory.
// The Plume reader's outcome per volcano, as code recorded it on each assessment; volcanoes with the
// same outcome share one step ("Semeru, Ibu and 2 more: ...").
const PLUME_OUTCOME = {
  ACCEPTED: ["ok", "its estimate passed the code's checks"],
  REPAIRED: ["ok", "its estimate passed the checks after one repair"],
  STUB: ["ok", "estimate by code (code only), the official area"],
  MODEL_FAILED: ["failed", "no estimate passed the checks, so the area stays at the official reports"],
  PENDING: ["caution", "plume read waits for the Coordinator, the area stays at the official reports until it runs"],
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
    const g = by.get(a.outcome) || { names: [], at: -Infinity };
    g.names.push(sit.volcano_name);
    g.at = Math.max(g.at, ms(a.created_at));
    by.set(a.outcome, g);
  }
  return [...by].map(([outcome, g]) => {
    const [tone, words] = PLUME_OUTCOME[outcome];
    return { tone, text: `${names(g.names)}: ${words}`, count: 1, at: g.at, source: SOURCE.estimate };
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
      // the solver finding no plan is code's answer, not an assistant failure: "No plan", in caution
      out.push({ tone: fail ? (fail.ai ? "failed" : "caution") : "ok", word: fail && !fail.ai ? "No plan" : null, text, count: 1, at: ms(plan.created_at), source: SOURCE.plan });
    }
  }
  if (h.id === "sat") {
    for (const r of ctx.satellite || []) {
      const name = ctx.volcanoName(r.volcano_id);
      const ash = { yes: "ash seen", no: "no ash seen", uncertain: "can't tell" }[r.ash_visible] || "can't tell";
      // a quota refusal called no model: "did not run", never "gave no result" (Q4)
      const text = r.status === "ai_unavailable" ? `${name}: not read (Satellite reader ${reasonClass(r.reason) === "budget" ? "did not run" : "gave no result"}). Nothing was put in its place`
        : r.status === "no_frames" ? `${name}: no picture to read` : `${name}: ${ash}`;
      out.push({ tone: r.status === "ai_unavailable" ? "failed" : r.status === "no_frames" ? "caution" : "ok", text, count: 1, at: ms(r.created_at || r.observed_at), source: SOURCE.reading });
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
      out.push({ tone: "ok", text, count: 1, at: ms(adv.drafted_at || adv.created_at), source: SOURCE.advisory });
    }
  }
  return out;
}

// The model a card's skill calls, as its sheet's footer says it: the id only. Its calls today and
// whether Google has closed it are said at Details › TEPHRA Assistant (8.6).
export function modelLine(tier, ctx) {
  if (ctx.stub) return { id: null, text: "No model (offline stub): no calls", tone: "off" };
  const b = ctx.budget;
  if (!b) return { id: null, text: ctx.budgetError ? "Model: unknown, the assistant's status did not load" : "Model: loading", tone: ctx.budgetError ? "caution" : "off" };
  const t = (b.tiers || []).find((x) => x.tier === tier);
  if (!t) return { id: null, text: "Model: unknown", tone: "caution" };
  return { id: t.model_id, text: `Model: ${t.model_id}`, tone: null };
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

// A step that just arrived shows its skill working only when it is work a skill did: never a
// failure or a quota refusal (no model was called), and never the work list code writes before
// any model is called ("Duty Officer: 3 item(s) to dispatch").
const CODE_LINE = /^Duty Officer: \d+ item\(s\) to dispatch\b|AI UNAVAILABLE|left \d+ mandatory item\(s\) undone/;
export const isWorkLine = (t) => Boolean(t) && t.level !== "error" && !CODE_LINE.test(String(t.message || ""));

function helperCard(h, ctx) {
  const lines = ownLines(h, ctx.trace);
  const newest = lines[lines.length - 1];
  const work = workOf(h, ctx.work);
  const now = queueSteps(work);
  const past = [...traceSteps(h, lines), handoffStep(h, ctx.duty), ...resultSteps(h, ctx)].filter(Boolean).sort((a, b) => (b.at || 0) - (a.at || 0));
  // The card's line is the helper's own newest result; the hand-out has its own chip.
  const last = past.find((x) => x.source !== SOURCE.run) || past[0] || null;
  const arrived = isWorkLine(newest) ? ctx.arrivedAgo(newest.id) : Infinity;
  const working = work.some((w) => w.status === "RUNNING") || arrived < LIVE_MS;
  const waiting = work.filter((w) => w.status === "WAITING");
  const queued = work.filter((w) => w.status === "QUEUED");
  const state = stateOf({ working, waiting: waiting.length, queued: queued.length, last });
  return {
    id: h.id, role: h.role, name: h.name, does: h.does, to: h.to || null, state, word: (state === "failed" || state === "notrun") && last.word ? last.word : STATE_WORD[state],
    last: last || { tone: "quiet", text: `Nothing in the newest ${plural(ctx.trace.length, "step")}. ${h.when}.`, at: NaN, source: SOURCE.trace },
    waiting: waiting.length ? { n: waiting.length } : null,
    queued: queued.length,
    handoff: handoff(ctx.duty, h.tool),
    model: modelLine(h.tier, ctx),
    steps: [...now, ...past].slice(0, STEPS_SHOWN),
    more: Math.max(0, now.length + past.length - STEPS_SHOWN),
  };
}

// The Coordinator's latest run in one sentence (code-written from the run's fields), in the words
// of Details › TEPHRA Assistant (wall/duty.js OUTCOME): a quota refusal called no model and is "Not
// run" (the assistant paused; why is said at that home, 8.6); a run whose brief failed the checks
// called one and is "No brief".
export function dutyLine(run) {
  const n = (run.dispatches || []).length;
  const handed = new Set((run.dispatches || []).flatMap((d) => d.item_ids)).size;
  const undone = (run.undispatched || []).length;
  const later = (run.deferred || []).length;
  const tail = [later ? `Left ${plural(later, "optional job")} for later.` : null, undone ? `Passed ${plural(undone, "must-do job")} to the Desk.` : null].filter(Boolean).join(" ");
  const first = n ? ` It handed out ${plural(handed, "job")} first.` : "";
  if (run.outcome === "MODEL_FAILED") {
    const cls = reasonClass((run.validation_errors || [])[0]);
    if (cls === "budget") return { tone: "caution", word: "Not run", text: `Not run: ${ASSISTANT} is paused. No brief was made.${first}${tail ? ` ${tail}` : ""}` };
    return { tone: "failed", word: "No brief", text: `No brief: the Coordinator gave no result (${WHY[cls] || WHY.other}). Nothing was made up in its place.${first}${tail ? ` ${tail}` : ""}` };
  }
  if (run.outcome === "STUB") return { tone: "ok", text: `Handed out ${plural(handed, "job")} in urgency order (code only).${tail ? ` ${tail}` : ""}` };
  const checks = run.outcome === "REPAIRED" ? "Its brief passed after one repair." : "Its brief passed the code's checks.";
  return { tone: "ok", text: `${handed ? `Handed out ${plural(handed, "job")}.` : "Handed out no job."} ${checks}${tail ? ` ${tail}` : ""}` };
}

function dutyCard(ctx) {
  const h = HELPERS[0];
  const run = ctx.duty;
  const lines = ownLines(h, ctx.trace);
  const newest = lines[lines.length - 1];
  const items = (ctx.work || []).filter((w) => w.kind === "duty_item");
  // a refused run (the quota or a model that gave nothing) is never "Working", however recent its
  // lines: no model call is in progress for it
  const refusedRun = run?.outcome === "MODEL_FAILED";
  const working = items.some((w) => w.status === "RUNNING") || (!refusedRun && isWorkLine(newest) && ctx.arrivedAgo(newest.id) < LIVE_MS);
  const waiting = items.filter((w) => w.status === "WAITING");
  const model = ctx.stub || run?.llm_backend === "stub" ? { id: null, text: "No model (offline stub): no calls", tone: "off" } : modelLine("lite", ctx);
  if (!run) {
    return {
      id: h.id, role: h.role, name: h.name, does: h.does, state: working ? "working" : "quiet", word: STATE_WORD[working ? "working" : "quiet"],
      last: { tone: "quiet", text: "No run yet. It runs when code finds assistant work due: a plume to read, a flight to plan, a network to re-plan.", at: NaN, source: SOURCE.run },
      run: null, waiting: waiting.length ? { n: waiting.length } : null, model, steps: traceSteps(h, lines).slice(0, STEPS_SHOWN), more: 0, brief: null,
    };
  }
  const line = dutyLine(run);
  const at = ms(run.decided_at || run.finished_at); // when its decisions and brief were made
  const mandatory = run.worklist.filter((i) => i.mandatory).length;
  const label = (id) => run.worklist.find((i) => i.id === id)?.label || id;
  const runSteps = [
    { tone: "info", text: `Code gave it ${plural(run.worklist.length, "job")}${mandatory ? `, ${mandatory} of them must do` : ""}`, count: 1, at: ms(run.started_at), source: SOURCE.run },
    { tone: line.tone, text: line.text, count: 1, at, source: SOURCE.run },
    run.undispatched?.length ? { tone: "caution", text: `To the Desk, for a dispatcher: ${label(run.undispatched[0])}${run.undispatched.length > 1 ? ` and ${run.undispatched.length - 1} more` : ""}`, count: 1, at, source: SOURCE.run } : null,
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
    model, brief,
    steps: runSteps.slice(0, STEPS_SHOWN), more: Math.max(0, runSteps.length - STEPS_SHOWN),
  };
}

// The details behind the board: the Coordinator's card and each skill's. `input` holds what the Wall
// already loaded; `arrivedAgo(traceId)` gives milliseconds since a trace line reached this page.
export function boardModel(input) {
  const s = input.state;
  if (!s) return { ready: false };
  const replay = s.mode === "REPLAY";
  const stub = s.llm?.backend === "stub" || input.budget?.backend === "stub";
  const ctx = {
    replay, stub, trace: input.trace || [], duty: input.duty || null,
    budget: input.budget || null, budgetError: input.budgetError || null, work: Array.isArray(input.budget?.waiting) ? input.budget.waiting : [],
    recovery: input.recovery || [], docs: input.docs || [], satellite: input.satellite || [],
    advisories: input.advisories || [], situations: input.situations || [],
    volcanoName: (id) => (input.situations || []).find((x) => x.volcano_id === id)?.volcano_name || id,
    arrivedAgo: input.arrivedAgo || (() => Infinity),
  };
  return { ready: true, replay, stub, duty: dutyCard(ctx), team: HELPERS.filter((h) => h.role === "team").map((h) => helperCard(h, ctx)) };
}

// ------------------------------------------------------------------ the flow board (UI-DESIGN 7.21)
// "TEPHRA Assistant at work" as a stage: real feeds on a map flow into code's checks, the
// Coordinator, the model gate, the skills and a person who decides. flowModel() is pure: every
// event it returns is one real record (a trace step, or a feed read whose last_success_at moved),
// and the view animates nothing else. A message no pattern knows is a log line with no motion.

// The skills each Coordinator tool reaches, the first one first (a plume read runs the Satellite
// reader inside it; a flight's plan goes on to the Drafter), and which skill a trace stage belongs to.
export const TOOL_SKILLS = { assess_volcanoes: ["plume", "sat"], plan_flights: ["planner", "drafter"], run_recovery: ["recovery"], draft_sra: ["sra"] };
const TOOL_SKILL = Object.fromEntries(Object.entries(TOOL_SKILLS).map(([tool, ids]) => [tool, ids[0]]));
const STAGE_SKILL = Object.fromEntries(HELPERS.filter((h) => h.role === "team").map((h) => [h.stage, h.id]));
const ON_REQUEST = new Set(["NOTICE", "ASK", "MESSAGES"]);
const MODEL_ACTORS = new Set(["gemini", "adk", "stub"]);
// The kind of each feed, which sets its colour: official products, the observatory, weather,
// aircraft, satellite pictures (the Wall's data colours).
export const FEED_KIND = {
  sigmet: "official", vaac_darwin: "official", vaac_tokyo: "official", vona: "observer", jma_volcano: "observer",
  metar: "weather", taf: "weather", winds: "weather", adsb: "aircraft", frames: "satellite", hsd: "satellite",
};
const FEED_WORDS = {
  sigmet: ["VA SIGMETs read", "current", "current"], vaac_darwin: ["Darwin VAAs read", "advisory", "advisories"], vaac_tokyo: ["Tokyo VAAs read", "advisory", "advisories"],
  vona: ["VONAs from MAGMA read", "notice", "notices"], jma_volcano: ["JMA volcano notices read", "notice", "notices"],
  metar: ["Airport weather (METAR) read", "report", "reports"], taf: ["Airport forecasts (TAF) read", "forecast", "forecasts"],
  winds: ["Winds aloft read", "point", "points"], frames: ["Satellite pictures read", "picture", "pictures"], hsd: ["Himawari split window read", "scene", "scenes"],
};
// A read that moved last_success_at within this of a POLL step (or a run started by new aircraft)
// is the same read: one event, never two.
const SAME_READ_MS = 3000;
// Same-second steps are told apart on screen, 160 ms each (spec 4).
export const STAGGER_MS = 160;

const POLL = /^(.+?): (\d+) new or changed record\(s\)$/;
const DUTY_START = /^Duty Officer: (\d+) item\(s\) to dispatch \((\w+)\)/;
const DUTY_REFUSED = /^Duty Officer AI UNAVAILABLE \((.+)\); (\d+) delegation\(s\) made, (\d+) mandatory item\(s\) to the Desk$/;
const DUTY_HANDOFF = /^Duty Officer -> (\w+):/;
const DUTY_BRIEF = /^Duty Officer brief: (\d+) delegation\(s\)/;
const DUTY_UNDONE = /^Duty Officer left (\d+) mandatory item\(s\) undone: to the Desk$/;
const EXPOSURE = /^(RFA\d+) \(([^)]*)\) (is inside|enters) the (.+?) cone(?: in (\d+) min)? at (FL\d{3})/;
const DESK_DRAFT = /^(RFA\d+): DRAFT (\w+(?: LEVEL)?) (?:waiting for|for) a dispatcher$/;
const PLUME_READ = /^Plume Reader (accepted|repaired): /;

const plural2 = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

function feedRead(feed, n, at, id, src, raw) {
  const kind = FEED_KIND[feed] || "weather";
  if (feed === "adsb") return { id, at, type: "adsb", raw, src, text: "Aircraft positions read (adsb.lol)" };
  const w = FEED_WORDS[feed];
  const text = w ? `${w[0]}${Number.isFinite(n) ? `: ${plural2(n, w[1], w[2])}` : ""}` : `${feed} read`;
  return { id, at, type: "feed", feed, kind, n: Number.isFinite(n) ? n : null, src, raw, text };
}

// A feed read the `state` stream reported (its last_success_at moved), as a board event; the same
// id flowEvents gives it, so it is never shown twice.
export const readEvent = (feed, n, at) => feedRead(feed, n, at, `read:${feed}:${at}`, "state", `feeds.${feed}.last_success_at ${new Date(at).toISOString()}`);

// One trace step as zero or more board events (spec 3). Pure; `t` is a trace line.
export function stepEvents(t) {
  const at = ms(t.at);
  if (!Number.isFinite(at)) return [];
  const msg = String(t.message || "");
  const id = t.id || `${t.stage}-${t.at}-${msg.slice(0, 24)}`;
  const base = { id, at, raw: msg, stage: t.stage, actor: t.actor, level: t.level };
  let m;
  if (t.stage === "POLL" && (m = POLL.exec(msg))) {
    const feed = t.detail?.feed || null;
    if (!feed) return [{ ...base, type: "note", text: plainLine(msg) }];
    const n = Number(m[2]);
    return [{ ...feedRead(feed, n, at, id, "poll", msg), stage: t.stage }];
  }
  if (t.stage === "DUTY") {
    if ((m = DUTY_START.exec(msg))) {
      const n = Number(m[1]), trig = m[2];
      const out = [];
      if (trig === "adsb") out.push({ ...base, id: `${id}:adsb`, at: at - 1, type: "adsb", src: "duty", quiet: true, text: "Aircraft positions read (adsb.lol)" });
      out.push({ ...base, type: "duty", n, trig, text: `Coordinator got ${plural2(n, "job")} ${trig === "adsb" ? "after new aircraft positions" : "on the scheduled check"}` });
      return out;
    }
    if ((m = DUTY_REFUSED.exec(msg))) {
      const cls = reasonClass(m[1]);
      return [{ ...base, type: "refused", cls, reason: m[1], d: Number(m[2]), n: Number(m[3]),
        // a refusal on record says what happened, not "paused": it may have been one skill's
        // share, and the state now is the headline's (8.6)
        text: cls === "budget" ? "Coordinator did not run" : `Coordinator gave no result (${WHY[cls] || WHY.other})` }];
    }
    if ((m = DUTY_HANDOFF.exec(msg))) {
      const skill = TOOL_SKILL[m[1]] || null;
      return [{ ...base, type: skill ? "handoff" : "note", tool: m[1], skill, text: plainLine(msg) }];
    }
    if ((m = DUTY_BRIEF.exec(msg))) return [{ ...base, type: "brief", d: Number(m[1]), text: plainLine(msg) }];
    if ((m = DUTY_UNDONE.exec(msg))) return [{ ...base, type: "undone", n: Number(m[1]), text: plainLine(msg) }];
    return [{ ...base, type: "note", text: plainLine(msg) }];
  }
  if (t.stage === "EXPOSURE" && (m = EXPOSURE.exec(msg))) {
    const inside = m[3] === "is inside";
    return [{ ...base, type: "flight", flight: m[1], cs: m[2], inside, mins: m[5] ? Number(m[5]) : 0, vol: m[4], fl: m[6],
      text: inside ? `${m[1]} is inside the ${m[4]} ash area at ${m[6]}` : `${m[1]} reaches the ${m[4]} ash area in ${m[5]} min at ${m[6]}` }];
  }
  if (t.stage === "DESK" && t.actor === "human") return [{ ...base, type: "decided", text: msg }];
  if (t.stage === "DESK" && (m = DESK_DRAFT.exec(msg))) return [{ ...base, type: "desk", skill: "drafter", flight: m[1], text: plainLine(msg) }];
  const skill = STAGE_SKILL[t.stage];
  if (skill && MODEL_ACTORS.has(t.actor)) {
    if (t.level === "error") return [{ ...base, type: "skill-failed", skill, text: plainLine(msg) }];
    const h = HELPERS.find((x) => x.id === skill);
    // the Drafter's output reaches the Desk with the DESK step; the other desk skills' with their own
    const toDesk = h.to === "desk" && skill !== "drafter";
    // amber only for a real model reading of the plume, never for code's stub estimate
    const plume = skill === "plume" && t.actor !== "stub" && PLUME_READ.test(msg);
    return [{ ...base, type: "skill", skill, toDesk, plume, volcano: t.volcano_id || null, text: plainLine(msg) }];
  }
  if (ON_REQUEST.has(t.stage) && MODEL_ACTORS.has(t.actor)) return [{ ...base, type: t.level === "error" ? "note" : "onreq", text: plainLine(msg) }];
  return [{ ...base, type: "note", text: plainLine(msg) }];
}

// Feed reads that are not trace steps: a feed's last_success_at that moved on the `state` stream
// (`reads`, kept by the Wall), and each feed's newest read when it falls in the window. A POLL step
// (or a run started by new aircraft) for the same feed within SAME_READ_MS is the same read.
function feedEvents(feeds, reads, from, to, traceEvents) {
  const seen = traceEvents.filter((e) => e.type === "feed" || e.type === "adsb");
  const same = (feed, at) => seen.some((e) => (feed === "adsb" ? e.type === "adsb" : e.feed === feed) && Math.abs(e.at - at) < SAME_READ_MS);
  const out = [];
  const add = (feed, at, n, src) => {
    if (!Number.isFinite(at) || at < from || at > to || same(feed, at)) return;
    const e = feedRead(feed, n, at, `read:${feed}:${at}`, src, `feeds.${feed}.last_success_at ${new Date(at).toISOString()}`);
    out.push(e);
    seen.push(e);
  };
  for (const r of reads || []) add(r.feed, ms(r.at), r.n, "state");
  for (const f of feeds || []) if (f.status === "OK" || f.status === "STALE") add(f.feed, ms(f.last_success_at), f.record_count, "feeds");
  return out;
}

// The Coordinator writes its "Duty Officer -> <tool>: ..." line when the tool returns, after the
// skill's own steps for that hand-out. On the board the hand-out goes first: it moves to just before
// the first step of that skill since the run started (or since the previous hand-out to the same
// tool), at most HANDOFF_BACK_MS earlier. `rec` keeps the record's own time, which the log shows.
const HANDOFF_BACK_MS = 5000;
function handoffsFirst(events) {
  let runAt = -Infinity;
  const lastTo = {};
  for (const e of events) {
    if (e.type === "duty") { runAt = e.at; continue; }
    if (e.type !== "handoff") continue;
    const skills = TOOL_SKILLS[e.tool] || [];
    const from = Math.max(runAt, lastTo[e.tool] ?? -Infinity, e.at - HANDOFF_BACK_MS);
    lastTo[e.tool] = e.at;
    const first = events.find((x) => x !== e && x.at > from && x.at <= e.at && (x.type === "skill" || x.type === "skill-failed" || x.type === "desk") && skills.includes(x.skill));
    if (first) { e.rec = e.at; e.at = first.at - 1; }
  }
  return events.sort((a, b) => a.at - b.at);
}

// Every board event in the window, oldest first, with same-second steps staggered for the eye.
export function flowEvents({ trace = [], feeds = [], feedReads = [], now = NaN }) {
  const fromTrace = trace.flatMap(stepEvents).sort((a, b) => a.at - b.at);
  const first = fromTrace.length ? fromTrace[0].at : Number.isFinite(now) ? now - 600000 : NaN;
  const t0 = Number.isFinite(first) ? first - 6000 : NaN;
  const last = fromTrace.length ? fromTrace[fromTrace.length - 1].at : -Infinity;
  const t1 = Math.max(Number.isFinite(now) ? now : -Infinity, last);
  const events = handoffsFirst([...fromTrace, ...feedEvents(feeds, feedReads, t0, t1, fromTrace)].sort((a, b) => a.at - b.at));
  let prev = -Infinity, k = 0;
  for (const e of events) {
    k = e.at - prev < 1000 && !e.quiet ? k + 1 : 0;
    if (!e.quiet) prev = e.at;
    e.lag = Math.min(k, 12) * STAGGER_MS; // screen time only
  }
  events.forEach((e, i) => { e.i = i; });
  return { events, t0, t1: Number.isFinite(t1) ? t1 : t0 };
}

// The board's counters, hero and run bars at a playhead: a pure function of the events at or
// before `t`, so scrubbing is exact (spec 6). `hero` is M of the newest refused (or must-do left
// undone) run at or before t; null before the first such run.
export function flowAt(events, t, { example = false } = {}) {
  const S = { feeds: 0, flights: 0, coordAt: null, coordRefused: false, must: null, mustAt: null, runs: 0, drafts: 0, exRun: null, lit: {}, failed: {} };
  for (const e of events) {
    if (e.at > t) break;
    if (e.type === "feed" || e.type === "adsb") S.feeds += 1;
    else if (e.type === "flight") S.flights += 1;
    else if (e.type === "duty") { S.coordAt = e.at; S.coordRefused = false; if (example) { S.exRun = e.at; S.drafts = e.n; } }
    else if ((e.type === "refused" || e.type === "undone") && !example) { S.must = e.n; S.mustAt = e.at; S.runs += e.type === "refused" ? 1 : 0; S.coordRefused = e.type === "refused"; }
    else if (e.type === "skill" || e.type === "handoff") { S.lit[e.skill] = e.at; delete S.failed[e.skill]; }
    else if (e.type === "skill-failed") S.failed[e.skill] = e.at;
  }
  return S;
}

// The log, folded so what belongs together is one row (spec 1): flights flagged together, a run's
// "N jobs" and its outcome, hand-outs to one skill, drafts reaching the Desk. Repeated refusals
// say how often ("23× since 11:28:26").
export function foldRows(events, { example = false } = {}) {
  const rows = [];
  let refusals = 0, firstRefusal = null;
  for (const e of events) {
    if (e.quiet) continue;
    const last = rows[rows.length - 1];
    const near = (ms2) => last && e.at - last.at < ms2;
    if (e.type === "flight") {
      if (near(1500) && last.kind === "flight" && last.vol === e.vol) { last.items.push(e); continue; }
      rows.push({ kind: "flight", key: `f:${e.id}`, at: e.at, vol: e.vol, items: [e] });
      continue;
    }
    if (e.type === "refused" || e.type === "undone") {
      refusals += 1;
      firstRefusal = firstRefusal ?? e.at;
      const row = near(2000) && last.kind === "duty" && !last.out ? last : null;
      const out = { e, k: refusals, since: firstRefusal };
      if (row) { row.out = out; row.items.push(e); } else rows.push({ kind: "duty", key: `r:${e.id}`, at: e.at, duty: null, out, items: [e] });
      continue;
    }
    if (e.type === "duty") { rows.push({ kind: "duty", key: `d:${e.id}`, at: e.at, duty: e, out: null, items: [e] }); continue; }
    if (e.type === "handoff" || e.type === "skill" || e.type === "desk") {
      const k = `${e.type}:${e.skill}`;
      if (near(2500) && last.kind === k) { last.items.push(e); continue; }
      rows.push({ kind: k, key: `${k}:${e.id}`, at: e.at, items: [e] });
      continue;
    }
    rows.push({ kind: e.type, key: `${e.type}:${e.id}`, at: e.at, items: [e] });
  }
  return rows.map((r) => ({ ...r, tm: r.items[0].rec ?? r.at, ...rowWords(r, example) })).filter((r) => r.text);
}

const flightNames = (a) => (a.length <= 2 ? a.map((e) => e.flight).join(" and ") : `${a[0].flight}, ${a[1].flight} +${a.length - 2}`);
const SKILL_NAME = Object.fromEntries(HELPERS.map((h) => [h.id, h.name]));

// A row's words and its colour key (official, observer, weather, aircraft, job, must, tephra,
// muted). `toYou` marks the words that say work went to a person.
function rowWords(r, example) {
  const e = r.items[0];
  const raw = r.items.map((x) => x.raw).join("\n");
  if (r.kind === "flight") {
    const a = r.items, ins = a.filter((x) => x.inside), near = a.filter((x) => !x.inside);
    const text = a.length === 1 ? e.text
      : !near.length ? `${flightNames(a)} are inside the ${r.vol} ash area`
        : !ins.length ? `${flightNames(a)} will reach the ${r.vol} ash area`
          : `${flightNames(a)}: ${ins.length} inside the ${r.vol} ash area, ${near.length} on the way`;
    return { tone: "aircraft", text: `Code: ${text}`, raw };
  }
  if (r.kind === "duty") {
    const got = r.duty ? r.duty.text : "Coordinator run";
    if (example) return r.duty ? { tone: "job", text: `Coordinator hands ${plural2(r.duty.n, "job")} to the skills (example)`, raw } : { text: "" };
    if (!r.out) return { tone: "job", text: got, raw };
    const o = r.out.e;
    const head = o.type === "undone" ? `${got} · it left must-do work` : o.cls === "budget" ? `${got} · did not run` : `${got} · ${o.text.replace(/^Coordinator /, "")}`;
    return { tone: "must", text: head, toYou: `${o.n} must-do to you`, repeat: r.out.k > 1 ? `${r.out.k}× since ${hmsOf(r.out.since)}` : null, raw };
  }
  if (r.kind.startsWith("handoff:")) return { tone: "job", text: `Coordinator handed ${r.items.length === 1 ? "a job" : `${r.items.length} jobs`} to ${SKILL_NAME[e.skill] || e.skill}`, raw };
  if (r.kind.startsWith("skill:")) return { tone: e.plume ? "tephra" : "job", text: r.items.length === 1 ? e.text : `${SKILL_NAME[e.skill] || e.skill}: ${r.items.length} steps · ${r.items[r.items.length - 1].text}`, raw };
  if (r.kind.startsWith("desk:")) return { tone: "job", text: r.items.length === 1 ? `Advisory draft for ${e.flight} reached the Desk` : `${r.items.length} advisory drafts reached the Desk`, raw };
  if (e.type === "feed") return { tone: e.kind, text: e.text, raw };
  if (e.type === "adsb") return { tone: "aircraft", text: e.text, raw };
  if (e.type === "skill-failed") return { tone: "muted", text: e.text, raw };
  if (e.type === "brief" || e.type === "onreq" || e.type === "decided") return { tone: "job", text: e.text, raw };
  return { tone: "muted", text: e.text, raw };
}

// The board's one time form, the replay clock's: "11:28:26"
export const hmsOf = (t) => (Number.isFinite(t) ? new Date(t).toISOString().slice(11, 19) : "--:--:--");
// What the map draws: the region and the snapshot's real ash areas, volcanoes, airports and
// aircraft, reduced to plain numbers (no DOM).
function geoOf(region, snapshot, activeIds) {
  const rings = (g) => (g?.type === "Polygon" ? [g.coordinates[0]] : g?.type === "MultiPolygon" ? g.coordinates.map((p) => p[0]) : []);
  const feats = (k) => snapshot?.[k]?.features || [];
  const active = new Set(activeIds || []);
  const airports = {};
  for (const f of feats("routes")) {
    const ends = f.properties?.ends || [];
    const co = f.geometry?.coordinates || [];
    if (ends.length === 2 && co.length > 1) {
      airports[ends[0]] = airports[ends[0]] || co[0];
      airports[ends[1]] = airports[ends[1]] || co[co.length - 1];
    }
  }
  return {
    bbox: region?.bbox || null, name: region?.name || "", adsbPoints: region?.adsb_points || [],
    cones: feats("cones").filter((f) => f.properties?.part === "cone").map((f) => ({ volcano: f.properties.volcano_id, mode: f.properties.mode || "OFFICIAL", top: f.properties.top_ft, base: f.properties.base_ft, rings: rings(f.geometry) })),
    official: feats("official").map((f) => ({ kind: f.properties?.kind, label: f.properties?.label || "", top: f.properties?.top_ft, base: f.properties?.base_ft, rings: rings(f.geometry) })),
    volcanoes: feats("volcanoes").filter((f) => active.has(f.id ?? f.properties?.id) || f.properties?.active).map((f) => ({ id: f.id ?? f.properties?.id, name: f.properties?.name, code: f.properties?.color_code, at: f.geometry?.coordinates })),
    aircraft: feats("aircraft").map((f) => ({ hex: f.properties.hex, flight: f.properties.proxy_flight, cs: f.properties.callsign, at: f.geometry?.coordinates, trk: f.properties.track_deg, exposed: !!f.properties.exposed,
      alt: f.properties.alt_baro_ft ?? null, gs: f.properties.gs_kt ?? null, mins: f.properties.minutes_to_entry ?? 0, from: f.properties.origin_icao || null, to: f.properties.dest_icao || null })),
    airports,
  };
}

// The whole flow board. input: { state, trace, feeds, feedReads, budget, duty, snapshot, region,
// handPlan, docs, recovery, realNow }.
export function flowModel(input) {
  const s = input.state;
  if (!s) return { ready: false };
  const replay = s.mode === "REPLAY";
  const realNow = input.realNow ?? Date.now();
  // a budget that failed to load says nothing about now: no gate state, no queue from an old copy
  const budgetError = input.budgetError || null;
  const budget = budgetError ? null : input.budget || null;
  const stub = s.llm?.backend === "stub" || budget?.backend === "stub";
  const ai = aiStateOf({ stub, budget, errors: aiErrorsOf(input.trace), duty: input.duty || null, plan: newestPlan(input.recovery), replay, now: realNow });
  const { events, t0, t1 } = flowEvents({ trace: input.trace || [], feeds: input.feeds || [], feedReads: input.feedReads || [], now: ms(s.now) });
  const waiting = (Array.isArray(budget?.waiting) ? budget.waiting : []).filter((w) => w.status === "WAITING");
  const kindOf = (w) => w.item?.kind || (w.kind === "recover" ? "RECOVER" : null);
  // a waiting job sits in front of the first skill that does its kind (a PLAN job is the Flight
  // planner's before the Drafter's; an ASSESS job the Plume reader's)
  const team = HELPERS.filter((h) => h.role === "team");
  const ownerOf = (w) => team.find((h) => h.kinds?.includes(kindOf(w)))?.id || null;
  const skills = team.map((h) => {
    const jobs = waiting.filter((w) => ownerOf(w) === h.id);
    const own = (input.trace || []).filter((t) => t.stage === h.stage && MODEL_ACTORS.has(t.actor));
    const newest = own[own.length - 1] || null;
    return { id: h.id, name: h.name, does: h.does, to: h.to || null, inLine: jobs.length, jobs: jobs.map((w) => w.label),
      last: newest ? { text: plainLine(newest.message), at: ms(newest.at), failed: newest.level === "error" } : null };
  });
  // the assistant's state in the board's words (spec 5); the chip's words for trouble and off. A
  // pause is said as "paused", what still holds and what waits; why it is paused and until when
  // are said once, at Details › TEPHRA Assistant (docs/UI-AI-QUIET.md 8.6), one tap away behind the
  // "Why ›" after the board's lede, the gate's tooltip and the "Details › TEPHRA Assistant ›" link
  const words = aiWords(ai, { home: `Details › ${ASSISTANT}`, opens: "nothing" });
  const jobs = plural2(waiting.length, "job");
  const inLine = budgetError ? "Jobs in line: unknown, the work queue did not load" : waiting.length ? `${jobs} in line` : "Nothing waits in line";
  let status, sub, gate;
  if (ai.kind === "paused") {
    status = "paused";
    // with no work queue loaded, nothing is said about jobs in line (the gate says it is unknown)
    sub = budgetError
      ? "Code still reads every feed and checks every flight, and must-do flights come straight to you."
      : "Code still reads every feed and checks every flight; jobs wait in line and must-do flights come straight to you.";
    gate = { open: false, kind: "closed", name: "Paused", meta: inLine, title: `Why: Details › ${ASSISTANT}` };
  } else if (ai.kind === "off") {
    status = "off (code only)";
    sub = "No model is connected. Code reads every feed, checks every flight and orders the work, and code templates write the drafts. Every draft still waits for you.";
    // no model to close: the skills run as code templates, so work goes past the gate
    gate = { open: true, kind: "nomodel", name: "No model · code templates", meta: "Skills run as code, no model is called", title: "NO MODEL: the offline stub" };
  } else if (ai.kind === "trouble") {
    status = words.suffix;
    sub = `${ai.trouble.map((c) => causeShort(c)).join(". ")}. Nothing was put in ${ai.trouble.length === 1 ? "its" : "their"} place: code still checks every flight, and that work comes to you.`;
    gate = { open: false, kind: "trouble", name: "AI model · gave no result", meta: inLine, title: "" };
  } else {
    status = "working";
    sub = "The Coordinator hands each job to a skill, and every draft waits for you. Code checks every number before you see it.";
    gate = { open: true, kind: "open", name: "AI model · open", meta: inLine, title: "" };
  }
  const run = input.duty || null;
  const coord = { meta: ai.kind === "paused" ? "Paused: must-do jobs come to you" : ai.kind === "off" ? "Code orders the jobs (no model)" : "Orders the jobs and hands them to skills",
    refused: run?.outcome === "MODEL_FAILED", lastAt: run ? ms(run.decided_at || run.finished_at) : NaN };
  // You decide: the Wall's own counts, this mode's work only
  const plan = newestPlan(input.recovery);
  const sra = [...new Set((input.docs || []).filter((d) => d.kind === "SRA" && d.status === "DRAFT" && d.replay === replay).map((d) => d.region_name || d.title || d.region))];
  const desk = {
    drafts: s.draft_count ?? null,
    handPlan: input.handPlan || null,
    sra: { n: sra.length, names: sra.map((x) => String(x).replace(/^SRA draft: /, "")) },
    plan: plan?.status === "DRAFT" ? "waits for approval" : plan?.status === "AI_UNAVAILABLE" ? "by hand" : null,
    planNote: plan?.status === "AI_UNAVAILABLE" ? (planFailure(plan)?.title || "") : "",
    must: (run?.undispatched || []).length,
  };
  const runs = events.filter((e) => e.type === "refused" || e.type === "undone");
  const region = input.region || s.region || null;
  return {
    ready: true, replay, stub, mode: s.mode,
    ai: { kind: ai.kind, symbol: aiSymbol(ai.kind), title: words.title, label: words.label, suffix: words.suffix, tone: words.tone }, status, sub, gate, budgetError,
    queue: waiting.map((w) => ({ label: w.label, kind: kindOf(w), skill: ownerOf(w) })),
    skills, coord, desk, runs, events, t0, t1, spanMin: Number.isFinite(t0) ? Math.max(1, Math.round((t1 - t0) / 60000)) : 0,
    feeds: (input.feeds || []).map((f) => ({ feed: f.feed, status: f.status, records: f.record_count, error: f.last_error || null, kind: FEED_KIND[f.feed] || "weather" })),
    geo: geoOf(region, input.snapshot, s.active_volcano_ids),
  };
}

