// Small building blocks shared by the Wall's Details sections (ext.js, duty.js, panels.js), and the
// one derived AI state both the Wall and the Desk word their assistant lines from
// (docs/UI-AI-QUIET.md, and its "Naming" amendment: the AI is shown as one assistant, "TEPHRA
// Assistant", whose skills are named by job). Every string goes in through el() (textContent);
// model-written text carries a short mark whose model id sits in its title and label, never in
// the visible text.

import { el, icon, ms, hhmmz, hhmmssz, airline } from "./util.js";

// The assistant's one name, and the skill names its work is shown under (docs/UI-AI-QUIET.md,
// Naming). Ids, file names and API fields keep their old names; only the words on screen change.
export const ASSISTANT = "TEPHRA Assistant";

// The assistant's one status (owner, 17 Oct: "don't say no model everywhere"), said once per
// screen: in the demo's tab bar, the /assistant board's title and the Desk's header, and only when
// it is not working normally: a dot and two words ("AI off", "AI paused", "AI unavailable"), the
// explanation behind an info button (wall/info.js) with the way to the cause ("Why ›" on the demo,
// "Assistant details ›" on the Desk). On, nothing shows; `said` is the screen-reader text in every
// state (the honesty label is never dropped). `w` is aiWords' words (its suffix names the skill in
// trouble).
export function stateLine(w, { stub = false, kind = "on" } = {}) {
  if (stub || kind === "off") {
    return { word: "AI off", tone: "off", icon: "st-off", why: false, said: `${ASSISTANT} off: no model is connected.`,
      info: "Offline stub: no model is connected. Code checks still run, and code templates write the drafts." };
  }
  if (kind === "paused") {
    return { word: "AI paused", tone: "caution", icon: "st-caution", why: true, said: `${ASSISTANT} paused.`,
      info: "Code still reads every feed and checks every flight. Must-do flights come straight to you." };
  }
  if (kind === "trouble") {
    const what = w?.suffix || "gave no result";
    return { word: "AI unavailable", tone: "caution", icon: "st-caution", why: true, said: `${ASSISTANT}: ${what}.`,
      info: `${what.charAt(0).toUpperCase()}${what.slice(1)}. Nothing was put in its place; code still checks every flight.` };
  }
  return { word: null, tone: "ok", icon: "st-ok", why: false, said: `${ASSISTANT} on.`, info: null };
}

// The mark set (docs/UI-AI-QUIET.md Q5, Naming): "Drafted by TEPHRA Assistant", "Read by {skill}",
// "Chosen by TEPHRA Assistant", and "Code only (assistant off)" when no model wrote it. Only for
// content a model actually produced (a model id, and an outcome that passed the checks); the
// model id goes in the title and the label.
export const MARK = { written: `Drafted by ${ASSISTANT}`, chosen: `Chosen by ${ASSISTANT}`, read: (skill) => `Read by ${skill}`, none: "Code only (assistant off)" };
export function aiMark(modelId, label, verb = MARK.written) {
  const no = label === "NO MODEL" || !modelId || modelId === "stub" || modelId === "none";
  if (no) return codeMark();
  return el("span", { class: "ai-mark", title: `${verb} (${modelId}). Code checked every number, time and id.`, "aria-label": `${verb} (${modelId})` },
    icon("ta-16"), el("span", { text: verb, "aria-hidden": "true" }));
}

// The per-item mark for text a code template wrote (owner, 17 Oct: "don't say no model
// everywhere"): a small "{ }" with a tooltip and screen-reader words, never capital NO MODEL
// words; the AI-off state itself is said once per screen (the Wall's tab-bar status).
export const TEMPLATE = "Written by a code template";
export const codeMark = (words = TEMPLATE) => el("span", { class: "ai-mark ai-mark--none ai-mark--code", role: "img", "aria-label": words, title: words }, icon("i-code"));

// A plain line (plainLine) without its "(code only)" words, and whether it had them: the caller
// shows codeMark() beside the shorter text. Lines a model wrote come back as they were.
export function templateText(text) {
  const t = String(text ?? "");
  const out = t
    .replace(/^Advisory text written by a code template \(code only\): /, "Advisory text: ")
    .replace(/^Written by code \(code only\): /, "")
    .replace(/^Code only: /, "")
    .replace(/ by a code template \(code only\)/g, "")
    .replace(/ \(code only\)/g, "");
  return { text: out === t ? t : out.charAt(0).toUpperCase() + out.slice(1), code: out !== t };
}

// The chip's mark by state (docs/UI-AI-QUIET.md 8.4, Desk spec 6.6): working when on, hollow bands
// while waiting, the cut band when not running or off (no model connected). One choice for the
// Wall chip, the board's pill, the Desk chip and the Desk's idle line.
export const aiSymbol = (kind) => (kind === "on" ? "ta-working" : kind === "paused" ? "ta-waiting" : "ta-unavailable");

// The REPLAY words: "Replay · recorded feeds from 05 Sep 2026" then " · not live"; the case title,
// and whether the switch was automatic, for a tooltip. The date is the recording's first day (UTC),
// as the server's banner words it. A case rebuilt from archives (its label ends "(reconstructed)")
// says so, as the welcome dialog does: "Replay · feeds rebuilt from archives, from 05 Sep 2026". A
// synthetic case (invented demo data) never says "recorded": "Replay · synthetic demo data".
const MON3 = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export function replayWords(replay) {
  const t = Date.parse(replay?.recorded_from || "");
  const d = Number.isFinite(t) ? new Date(t) : null;
  const day = d ? `${String(d.getUTCDate()).padStart(2, "0")} ${MON3[d.getUTCMonth()]} ${d.getUTCFullYear()}` : null;
  const auto = replay?.auto ? "switched automatically: no live activity" : null;
  // the label marks a case rebuilt from archives, read as replay-words.js isReconstructed reads it
  // (the Desk does not load that module)
  const rebuilt = /\(reconstructed\)/.test(String(replay?.label || ""));
  const feeds = rebuilt ? "feeds rebuilt from archives" : "recorded feeds";
  return {
    text: replay?.synthetic ? "Replay · synthetic demo data" : `Replay · ${feeds}${day ? `${rebuilt ? "," : ""} from ${day}` : ""}`,
    live: " · not live",
    title: [replay?.banner, "not live", replay?.label, auto].filter(Boolean).join(" · "),
    // for screen readers, after the visible words: the tooltip is not read on touch screens
    more: [replay?.label, auto].filter(Boolean).map((s) => ` · ${s}`).join(""),
  };
}
// What an RFA flight stands in for: a real aircraft seen on ADS-B, or in a synthetic replay an
// aircraft invented for the demo. Lower case; callers capitalise at the start of a line.
export const aircraftNoun = (state) => (state?.mode === "REPLAY" && state.replay?.synthetic ? "demo aircraft" : "real aircraft");
// A modal makes the rest of the page inert, so each modal carries the REPLAY sentence as sr-only
// text in its description (no visible label); live, the text is empty. `words` is the REPLAY text
// ("" when live). Call it just before showModal().
export function describeReplay(dlg, words) {
  if (!dlg || !dlg.id) return;
  const id = `${dlg.id}-replay`;
  let p = document.getElementById(id);
  if (!p || p.parentElement !== dlg) {
    if (p) p.remove();
    p = document.createElement("p");
    p.id = id;
    p.className = "sr-only";
    dlg.prepend(p);
  }
  const text = words ? `${words}.` : "";
  if (p.textContent !== text) p.textContent = text;
  const ids = (dlg.getAttribute("aria-describedby") || "").split(/\s+/).filter((x) => x && x !== id);
  if (words) ids.push(id);
  if (ids.length) dlg.setAttribute("aria-describedby", ids.join(" "));
  else dlg.removeAttribute("aria-describedby");
}
// "waiting for AI budget, next slot 0700Z" (the API's slot words, inside a model's pacing sentence)
export const pacingWords = (text) => String(text || "").replace(/waiting for AI budget, next slot (\d{4}Z)/g, "the next slot is at $1").replace(/waiting for AI budget/g, "waiting for the next slot");
// Server words that still say "AI" (their API values are pinned), in the assistant's words for a
// main view: "Every other AI step" (a model's jobs) -> "Every other skill"
export const jobsWords = (text) => (text ? String(text).replace(/\b(e|E)very other AI step\b/g, (_, e) => `${e}very other skill`) : text);

// ------------------------------------------------------------------ the AI state (UI-AI-QUIET 1.2)
// AI is in one state: on, paused (its model closed for the day, or work waiting for a slot),
// trouble (n causes) or off (stub). The cause of a pause (the free quota, the next slot, budgets)
// is said once, at the assistant's home (docs/UI-AI-QUIET.md 8.6 "Say the cause once"); main views
// say "paused" and what to do.
// Failures count by cause (helper + reason class), never by step or tick. Pure: the Wall passes
// its trace, newest Coordinator (duty officer) run, newest airport plan and the live budget; the
// Desk its failures, Coordinator run and budget.

// The assistant's skills, by job. "duty" is the coordinating agent (the code's Duty Officer).
export const HELPER_NAME = {
  duty: "Coordinator", plume: "Plume reader", sat: "Satellite reader", planner: "Flight planner", drafter: "Drafter", ask: "Ask",
  notice: "Notice reader", recovery: "Recovery planner", messages: "Message drafter", docs: "Paperwork drafter",
};
const HELPER_KEY = {
  DUTY: "duty", duty_officer: "duty", PLUME: "plume", SATELLITE: "sat", PLANNER: "planner", planner: "planner", DRAFTER: "drafter", drafter: "drafter",
  ASK: "ask", NOTICE: "notice", RECOVERY: "recovery", recovery: "recovery", MESSAGES: "messages", DOCS: "docs",
};
// What each helper's failure means for the dispatcher, said once at the AI home.
const CONSEQUENCE = {
  duty: "Its must-do jobs went to the Desk to plan by hand", recovery: "Plan the network by hand", planner: "Plan those flights by hand on the Desk",
  drafter: "Plan those flights by hand on the Desk", plume: "TEPHRA's area stays at the official reports", sat: "The satellite picture is supporting only",
  notice: "Read the notice yourself", ask: "Ask again later, or read the Wall", messages: "Write the message by hand", docs: "Complete the document by hand",
};
// Where the dispatcher acts on it: [link words, Details section].
const CAUSE_LINK = {
  duty: ["See the jobs to plan by hand ›", "decisions"], recovery: ["Airport closures ›", "recovery"], planner: ["See the jobs to plan by hand ›", "decisions"],
  drafter: ["See the jobs to plan by hand ›", "decisions"], plume: ["TEPHRA's estimate ›", "estimate"], sat: ["Satellite picture ›", "sat"], notice: ["Notices ›", "notices"],
};

// Why a hosted airline has no model at all (tephra/hosted/settings_for.py): no model chosen, no
// key set, or a key that cannot be read. No model is called, as for a quota refusal.
const UNAVAILABLE_RE = /no model key is set|no model is chosen|the model key cannot be read/i;

// The reason class of a failure (budget, unavailable, timeout, checks, error, other), from the
// recorded reason.
export function reasonClass(reason) {
  const r = String(reason || "");
  // the Coordinator ran and handed must-do work to the Desk: the model answered, nothing failed
  if (/^Duty Officer left \d+ mandatory item|DUTY OFFICER DID NOT DISPATCH/i.test(r)) return "undone";
  if (UNAVAILABLE_RE.test(r)) return "unavailable";
  if (/budget_exhausted|DAILY QUOTA|RESOURCE_EXHAUSTED|\b429\b|quota/i.test(r)) return "budget";
  if (/Timeout|timed out/i.test(r)) return "timeout";
  if (/FAILED CHECKS|validation|did not pass/i.test(r)) return "checks";
  if (/ERROR\b|Error\b|exception/i.test(r)) return "error";
  return "other";
}
// "{why}" in "{Skill} gave no result ({why})" (UI-AI-QUIET 1.1, Naming). `budget` is the cause in
// full, for the assistant's home only (8.6): a main view or a plain-words line says only that the
// step "did not run" (plainWhy gives no words for it), and "paused" only while the assistant is.
export const WHY = {
  timeout: "timed out", checks: "the answer failed the code's checks", error: "it stopped with an error", other: "it could not answer",
  budget: "today's free AI quota is used up", undone: "left for the Desk",
  unavailable: "AI UNAVAILABLE: no model can be used",
};
// No model was called for the step: the quota refused it (budget), or the airline has no usable
// model (unavailable). Either way it "did not run"; it never "gave no result".
export const notRun = (cls) => cls === "budget" || cls === "unavailable";
// "AI UNAVAILABLE: no model key is set" from a recorded reason (the assistant's home says it).
export function unavailableWhy(reason) {
  const m = UNAVAILABLE_RE.exec(String(reason || ""));
  return m ? `AI UNAVAILABLE: ${m[0].toLowerCase()}` : WHY.unavailable;
}
// A Plume reader's outcome as the pages word it: MODEL_FAILED whose note says no model could be
// used (a hosted airline with no model, no key or an unreadable key) is UNAVAILABLE: no model was
// called, so it "did not run" and never "gave no result".
export const plumeOutcome = (outcome, notes) => (outcome === "MODEL_FAILED" && reasonClass(notes) === "unavailable" ? "UNAVAILABLE" : outcome);
// A cause's reason in words, for the assistant's home: the airline's own reason when no model
// can be used, else the §1.1 words.
const whyOf = (c) => (c.reasonClass === "unavailable" ? unavailableWhy(c.items[0]?.reason || c.raw[0]) : WHY[c.reasonClass] || WHY.other);
// The state word, for a step refused while the whole assistant is paused (ai.kind "paused").
export const PAUSED = "assistant paused";
// "{why}" outside the assistant's home: none for a quota refusal (the place says "did not run",
// and "Why ›" or Technical detail holds the cause), the §1.1 words for any other cause.
export const plainWhy = (cls) => (notRun(cls) ? null : WHY[cls] || WHY.other);

// The helper a failure belongs to: a Coordinator line about a plume read is the Plume reader's.
function helperOf(stage, reason) {
  if ((stage === "DUTY" || stage === "duty_officer") && /^Plume read: /.test(String(reason || ""))) return "plume";
  return HELPER_KEY[stage] || String(stage || "").toLowerCase();
}

// The Plume reader's own model (the "main" tier), when it is not the lite one.
const mainModel = (budget) => {
  const tier = (budget?.tiers || []).find((t) => t.tier === "main");
  return tier && tier.model_id !== liteModel(budget)?.model_id ? (budget.models || []).find((m) => m.model_id === tier.model_id) || null : null;
};
const liteModel = (budget) => {
  const tier = (budget?.tiers || []).find((t) => t.tier === "lite");
  const models = Array.isArray(budget?.models) ? budget.models : [];
  return (tier && models.find((m) => m.model_id === tier.model_id)) || models.find((m) => /every other/i.test(m.jobs || "")) || null;
};

// Trace stages an AI helper writes (the roster in wall/board.js).
const AI_STAGES = new Set(["DUTY", "PLUME", "SATELLITE", "PLANNER", "DRAFTER", "RECOVERY", "DOCS", "NOTICE", "ASK", "MESSAGES"]);

// The AI steps that failed in a trace, as aiStateOf takes them. A recovery step code ran and lost
// (no schedule, an exception, actor "system") is a data failure, not an AI one: it keeps the red
// story line (storyFailures) and its own words.
export function aiErrorsOf(trace) {
  return (trace || []).filter((t) => t.level === "error" && AI_STAGES.has(t.stage) && !(t.stage === "RECOVERY" && t.actor === "system"))
    .map((t) => ({ stage: t.stage, reason: t.message, at: ms(t.at), raw: `${hhmmssz(ms(t.at))} · ${t.stage} · ${t.message}`, src: t }));
}

// The newest airport plan that a newer one has not replaced.
export const newestPlan = (plans) => (plans || []).slice().sort((a, b) => ms(b.created_at) - ms(a.created_at)).find((p) => p.status !== "SUPERSEDED") || null;

// "2 h 45 min", "14 min"
function span(msLeft) {
  const m = Math.max(1, Math.round(msLeft / 60000));
  if (m < 60) return `${m} min`;
  return m % 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m / 60} h`;
}

// A time on the real clock, in words that fit after "paused" (`until`) or "next slot" (`at`).
// Live it is the clock time ("until 0700Z"). In REPLAY the page shows the recording's clock, so
// a real time would read as a time on that clock: it is said as the time left ("for another 2 h
// 45 min", "next slot in 2 h 45 min"), which reads the same on either clock. A time already behind
// the real clock is never a countdown or a stale "until": it is `past`, with `due` in words after
// "was due" ("at 0700Z", "3 h 10 min ago").
export function realWhen(t, now, replay) {
  if (!Number.isFinite(t)) return null;
  if (t <= now) return { past: true, until: null, at: null, due: replay ? `${span(now - t)} ago` : `at ${hhmmz(t)}` };
  if (!replay) return { until: `until ${hhmmz(t)}`, at: hhmmz(t) };
  const left = span(t - now);
  return { until: `for another ${left}`, at: `in ${left}` };
}

// errors: [{ stage, reason, at (ms), raw }]. plan: the newest airport plan. duty: the newest run.
// `replay`: the page plays a recording. `now`: the real clock (ms), for the time left in REPLAY.
// `until` is the reset in words after "paused" ("until 0700Z", "for another 2 h 45 min"), `slotAt`
// the form after "next slot", and `overdue` the reset in words after "was due" when it is already
// behind the real clock and the model still reads as closed. They word the cause at the
// assistant's home only (docs/UI-AI-QUIET.md 8.6).
export function aiStateOf({ stub = false, budget = null, errors = [], duty = null, plan = null, replay = false, now = Date.now() }) {
  const lite = liteModel(budget);
  // closed by a 429 for the day, or every call of the day spent: paused either way, on the Desk
  // (which sees only the budget) as on the Wall (which also sees the runs that were refused)
  const closed = !stub && (lite?.closed === true || (lite?.limit > 0 && lite?.remaining <= 0));
  // a statement about now, from the current budget only
  const reset = closed ? realWhen(Date.parse(budget?.resets_at || ""), now, replay) : null;
  const until = reset?.until || null;
  const overdue = reset?.past ? reset.due : null;
  const groups = new Map();
  const add = (helperKey, reason, at, raw, src, stage) => {
    const cls = reasonClass(reason);
    const key = `${helperKey}|${cls}`;
    let g = groups.get(key);
    if (!g) { g = { key, helperKey, helper: HELPER_NAME[helperKey] || helperKey, reasonClass: cls, items: [], raw: [], main: false }; groups.set(key, g); }
    // the Plume reader's own calls run on the main model, not on the lite model a pause is about
    if (stage === "PLUME") g.main = true;
    g.items.push({ at, reason, src });
    g.raw.push(raw || reason);
    return g;
  };
  for (const e of errors) add(helperOf(e.stage, e.reason), e.reason, e.at, e.raw, e.src, e.stage);
  // the newest airport plan's own failure: older than the trace window, still a cause (D67)
  if (plan && plan.status === "AI_UNAVAILABLE" && !planProblem(plan)) {
    const reason = planReasons(plan).join(" · ") || "no reason given";
    const key = `recovery|${reasonClass(reason)}`;
    if (!groups.has(key)) add("recovery", reason, Date.parse(plan.created_at), reason, { plan });
  }
  // the Plume reader's own model out of calls today: the same cause on the Wall (which also sees
  // its refusals in the trace) and the Desk (which sees only the budget)
  const main = stub ? null : mainModel(budget);
  if (main && (main.closed === true || (main.limit > 0 && main.remaining <= 0)) && !groups.has("plume|budget")) {
    groups.set("plume|budget", { key: "plume|budget", helperKey: "plume", helper: HELPER_NAME.plume, reasonClass: "budget", items: [], raw: [`${main.model_id}: ${main.used} of ${main.limit} calls used today`], main: true });
  }
  const dutyReason = duty?.outcome === "MODEL_FAILED" ? (duty.validation_errors || [])[0] || "no reason recorded" : null;
  if (dutyReason && !groups.has(`duty|${reasonClass(dutyReason)}`)) add("duty", dutyReason, Date.parse(duty.finished_at), dutyReason, { duty });
  // a run that answered and left must-do work for the Desk, when its trace line is not held
  const left = !stub && duty && duty.outcome !== "MODEL_FAILED" && duty.outcome !== "STUB" ? (duty.undispatched || []).length : 0;
  if (left && !groups.has("duty|undone")) {
    const r = `Duty Officer left ${left} mandatory item(s) undone: to the Desk`;
    add("duty", r, Date.parse(duty.finished_at), r, { duty });
  }
  const paused = !stub && (closed || (dutyReason != null && reasonClass(dutyReason) === "budget"));
  // In "paused", a lite-model budget cause is the state itself and is not counted again as
  // trouble. Any other step that ran out of calls (the Plume reader's own model, a lane's share)
  // is a problem of its own, in every state.
  const causes = [...groups.values()].map((g) => {
    const ts = g.items.map((x) => x.at).filter(Number.isFinite);
    return { ...g, steps: g.items.length, first: ts.length ? Math.min(...ts) : NaN, last: ts.length ? Math.max(...ts) : NaN,
      absorbed: paused && g.reasonClass === "budget" && !g.main,
      consequence: g.reasonClass === "undone" ? "Plan them by hand" : CONSEQUENCE[g.helperKey] || "Do this step by hand", link: CAUSE_LINK[g.helperKey] || null };
  }).sort((a, b) => (b.last || 0) - (a.last || 0));
  const trouble = causes.filter((c) => !c.absorbed);
  const waiting = (Array.isArray(budget?.waiting) ? budget.waiting : []).filter((w) => w.status === "WAITING").map((w) => {
    const slot = realWhen(Date.parse(w.next_slot_at || ""), now, replay);
    return { job: w.label, kind: w.item?.kind || w.kind, slot: slot?.at || null, volcano: w.item?.volcano_id || null };
  });
  const kind = stub ? "off" : paused ? "paused" : trouble.length ? "trouble" : "on";
  // `model` and `slotAt` word the cause at the assistant's home only (aiLead)
  return { kind, until, slotAt: reset?.at || null, overdue, model: lite?.model_id || null, causes, trouble, waiting, paused };
}

const problems = (n) => `${n} problem${n === 1 ? "" : "s"}`;

// One cause in a few words, for the chip's tooltip, the board and the assistant home's lead. "Did
// not run" only where no model was called (a budget refusal); a model that was called and gave
// nothing usable "gave no result"; a run that answered and left work for the Desk says that (H8).
// A budget refusal names its cause only at the assistant's home (`home`, 8.6); elsewhere it says
// what happened and nothing more, never "paused" (a cause in "trouble" is not a pause).
export function causeShort(c, { home = false } = {}) {
  if (c.reasonClass === "undone") return `${c.helper} left must-do jobs for the Desk`;
  if (notRun(c.reasonClass)) {
    if (!home) return c.steps ? `${c.helper} did not run` : `${c.helper} cannot run now`;
    return c.steps ? `${c.helper} did not run (${whyOf(c)})` : `${c.helper} cannot run now (${whyOf(c)})`;
  }
  return `${c.helper} gave no result (${WHY[c.reasonClass] || WHY.other})`;
}
// "its place" for one cause, "their place" for more.
const place = (n) => (n === 1 ? "its place" : "their place");

// What happened to one skill, from its causes: "gave no result" (a model was called and gave nothing
// usable), "did not run" (only where no model was called: a budget refusal or no usable model), "left jobs for the
// Desk" (it answered and left must-do work), "had problems" when its causes differ.
function skillWord(list) {
  const cls = new Set(list.map((c) => (notRun(c.reasonClass) ? "notrun" : c.reasonClass === "undone" ? c.reasonClass : "none")));
  if (cls.size > 1) return "had problems";
  const [k] = cls;
  // a skill whose model is out with no refused step yet "cannot run now", as causeShort says it
  return k === "notrun" ? (list.every((c) => !c.steps) ? "cannot run now" : "did not run") : k === "undone" ? "left jobs for the Desk" : "gave no result";
}

// The chip's state words after "TEPHRA Assistant ·" when there is trouble, counted by skill, never
// by cause (one skill can fail two ways): one skill by name with the same verb its tooltip uses
// ("Recovery planner gave no result"), more than one counted ("2 skills gave no result").
function troubleWords(list) {
  const bySkill = new Map();
  for (const c of list) bySkill.set(c.helperKey, [...(bySkill.get(c.helperKey) || []), c]);
  if (bySkill.size === 1) return `${list[0].helper} ${skillWord(list)}`;
  const words = new Set([...bySkill.values()].map(skillWord));
  return `${bySkill.size} skills ${words.size === 1 ? [...words][0] : "had problems"}`;
}

// The causes in a few words for a tooltip, each said once.
const causeList = (list) => [...new Set(list.map(causeShort))].join(". ");

// The one state in words, for a chip (`label` and its `suffix`: "TEPHRA Assistant · on"), its
// tooltip and its label. `home` names the assistant home ("TEPHRA Assistant at work" on the Wall,
// the assistant sheet on the Desk); `opens` what the chip opens. `narrow` (420 px and less)
// drops the time and says the short name "Assistant" (the label and tooltip keep the full name).
// The model behind TEPHRA Assistant, as the disclosure lines name it: Gemini, or Gemma served by
// Ollama on the same computer (TEPHRA_LLM=ollama). Set from /api/state's llm.backend.
let modelFamily = "Gemini";
export const setModelBackend = (backend) => { modelFamily = backend === "ollama" ? "Gemma, on this computer" : "Gemini"; };
export const assistantIs = () => `TEPHRA Assistant is TEPHRA's AI assistant (${modelFamily}).`;

export function aiWords(s, { home = `${ASSISTANT} at work`, opens = `${ASSISTANT} at work`, narrow = false } = {}) {
  const never = "It can widen TEPHRA's estimate, never shrink the official area.";
  // one of the few places that say "AI" (disclosure, docs/UI-AI-QUIET.md Naming)
  const is = assistantIs();
  const label = narrow ? "Assistant" : ASSISTANT;
  if (s.kind === "off") return { label, suffix: narrow ? "off" : "off (code only)", tone: "off", aria: `${ASSISTANT} off: no model is connected, code only. Opens ${opens}.`, title: `${ASSISTANT} off: no model is connected. Code does every step, and code templates write the text. TEPHRA Assistant is TEPHRA's AI assistant when a model is connected. ${never}` };
  if (s.kind === "paused") {
    // one neutral word, no reason and no time (8.6): the cause and the time are said once, at the
    // assistant's home, one tap from the chip
    return { label, suffix: "paused", tone: "caution",
      aria: `${ASSISTANT} paused. Opens ${opens}.`,
      title: `${ASSISTANT} is paused: see why in ${home}. ${is} ${never}` };
  }
  if (s.kind === "trouble") {
    const n = s.trouble.length;
    const list = causeList(s.trouble);
    return { label, suffix: narrow ? problems(n) : troubleWords(s.trouble), tone: "caution",
      aria: `${ASSISTANT}, ${problems(n)}: ${list}. Opens ${opens}.`,
      title: `${ASSISTANT}, ${problems(n)}: ${list}. Nothing was put in ${place(n)}. ${is} ${never} Open ${home} for the details.` };
  }
  return { label, suffix: "on", tone: "on", aria: `${ASSISTANT} on. Opens ${opens}.`, title: `${is} ${never} What it wrote is marked "Drafted by ${ASSISTANT}".` };
}

// The calm lead at the assistant home (UI-AI-QUIET 5.1): one paragraph, a sentence per cause. Only
// the home (`home`, the default: Details › TEPHRA Assistant, the Desk's assistant sheet) says why
// the assistant is paused and until when (8.6); a main view (`home: false`, the Desk's idle pane)
// says the state and what still holds.
export function aiLead(s, { home = true } = {}) {
  const at = (t) => (Number.isFinite(t) ? ` at ${hhmmz(t)}` : "");
  const causeLine = (c) => `${causeShort(c, { home })}${at(c.last)}. ${c.consequence}.`;
  const lines = (list) => `${list.map(causeLine).join(" ")} Nothing was put in ${place(list.length)}.`;
  if (s.kind === "off") return [{ strong: `${ASSISTANT} is off.`, text: "No model is connected. Code does every step, and code templates write the text." }];
  if (s.kind === "on") return [{ strong: `${ASSISTANT} is on.`, text: `It can widen TEPHRA's estimate, never shrink the official area. What it wrote is marked.` }];
  if (s.kind === "trouble") return [{ strong: `${ASSISTANT} is on, ${problems(s.trouble.length)}.`, text: lines(s.trouble) }];
  if (!home) return [{ strong: `${ASSISTANT} is paused.`, text: "Code still checks every flight, and must-do flights come to you to plan by hand." }];
  // the time is said once, in the first words; a reset already behind the real clock is said as
  // overdue, never as a countdown or a stale "until"
  const n = s.waiting.length;
  const jobs = n ? `Queued work (${n} job${n === 1 ? "" : "s"}) ${s.until ? "runs then" : "waits"}, on the same model. Nothing is dropped or handed to another model. ` : "";
  const quota = `Google's free daily AI quota${s.model ? ` for ${s.model}` : ""}`;
  const why = s.until ? `Why: ${quota} is used up.`
    : s.overdue ? `Why: ${quota} is used up. Its reset was due ${s.overdue} (real time), and the model still reads as closed, so when it opens is not known.`
      : `Why: ${quota} was used up.`;
  const out = [{ strong: s.until ? `${ASSISTANT} is paused ${s.until}.` : `${ASSISTANT} is paused.`,
    text: `${why} ${jobs}Until then, code still checks every flight against the official area, and nothing is made up in place of an assistant step. Flights that need a plan are on the Desk to plan by hand.` }];
  if (s.trouble.length) out.push({ strong: "Also:", text: lines(s.trouble) });
  return out;
}

// One cause in §1.1 words, for the cause lists (What went wrong, the trace). A quota refusal names
// its cause only at the assistant's home (`home`); elsewhere it "did not run" (8.6).
export function causeTitle(c, { home = false } = {}) {
  if (c.reasonClass === "undone") return `${c.helper} passed must-do jobs to the Desk`;
  if (notRun(c.reasonClass)) {
    // `absorbed`: the step was refused because the whole assistant is paused
    if (c.absorbed) return c.steps ? `${c.helper} did not run: ${PAUSED}` : `${c.helper} is paused`;
    if (!home) return c.steps ? `${c.helper} did not run` : `${c.helper} cannot run now`;
    return c.steps ? `${c.helper} did not run: ${whyOf(c)}` : `${c.helper}: ${whyOf(c)}`;
  }
  return `${c.helper} gave no result (${WHY[c.reasonClass] || WHY.other})`;
}

// Why a flight has no assistant draft, when that is the assistant's doing: { word, why }, or null
// when the assistant is on and fine (or off: the stub drafts too). `paused`: no cause is said at
// the place, only that the draft is missing and what to do (8.6). `undone`: the Coordinator ran and
// left its must-do flights for the Desk; only those flights are missing a draft. `queued`: the
// draft waits in line (waiting, not missing).
export function draftBlock(s) {
  if (!s || s.kind === "off") return null;
  if (s.kind === "paused") return { word: "Assistant paused", paused: true };
  const mine = s.trouble.filter((x) => x.helperKey === "duty" || x.helperKey === "planner" || x.helperKey === "drafter");
  const c = mine.find((x) => x.reasonClass !== "undone");
  // "did not run" only where no model was called (a budget refusal), as causeShort says it
  if (c) return { word: `${c.helper} ${notRun(c.reasonClass) ? "did not run" : "gave no result"}`, why: plainWhy(c.reasonClass), unavailable: true };
  if (mine.length) return { word: "left for the Desk", undone: true, why: "the Coordinator did not hand them out" };
  if (s.waiting.some((x) => x.kind === "PLAN")) return { word: "Waiting in line", queued: true };
  return null;
}

// "Why ›" at a place that lacks an assistant output (paused, or a skill that did not run or gave
// no result): the cause is one tap away, in Details › TEPHRA Assistant (docs/UI-AI-QUIET.md 8.6).
export const whyLink = (focus) => el("button", { type: "button", class: "link-btn dk-link", dataset: { act: "details-sec", sec: "ai", focus }, "aria-label": `Why: open ${ASSISTANT}`, text: "Why ›" });

// A draftBlock in words, for one flight: "Drafter gave no result (timed out)", "Flight planner did
// not run", "the Coordinator left it for the Desk". A paused assistant has no phrase: the place
// says only what is missing and what to do (8.6).
export function blockPhrase(b) {
  if (!b || b.paused) return "";
  if (b.undone) return "the Coordinator left it for the Desk";
  return `${b.word}${b.why ? ` (${b.why})` : ""}`;
}

// Flights with no advisory while the assistant cannot draft (docs/UI-AI-QUIET.md D56): every RFA
// flight in or heading in, all volcanoes, with no current advisory among the ones the Wall holds,
// while the assistant is waiting or gave no result (a queued draft is waiting, not missing); when
// the Coordinator left work for the Desk, only its must-do flights. The must-do flights first,
// then inside now, then the soonest entry. `block` says why (draftBlock). `partial`: the Wall
// holds the newest 50 advisories, so an older one is not seen here; the Desk's Plan by hand list
// is the record.
export function handPlanOf(D, store, ai) {
  const block = draftBlock(ai);
  if (!D || !block || block.queued) return { block, flights: [], must: 0, partial: false };
  const run = store?.snapshot?.duty;
  const must = new Set((run?.undispatched || []).map((id) => (run.worklist || []).find((i) => i.id === id)).filter((i) => i && i.kind === "PLAN").map((i) => i.subject));
  const flights = D.exposed.map((f) => ({ f, p: f.properties, key: `${f.properties.hex}:${f.properties.volcano_id}` }))
    .filter((x) => { const a = D.advByFlight.get(x.key); return !a || a.status === "SUPERSEDED"; })
    .map((x) => ({ ...x, must: must.has(x.key) }))
    .filter((x) => !block.undone || x.must)
    .sort((a, b) => Number(b.must) - Number(a.must) || Number(!!b.p.inside) - Number(!!a.p.inside) || (a.p.minutes_to_entry ?? 0) - (b.p.minutes_to_entry ?? 0));
  return { block, flights, must: flights.filter((x) => x.must).length, partial: (store?.advisories?.length || 0) >= 50 };
}

// ------------------------------------------------------------------ plain words (UI-REDESIGN R12.7)
// Code-written trace and assistant lines in plain words. A fixed table of patterns: a line that matches
// none is shown verbatim and never paraphrased, and the raw line always stays reachable under
// "Technical detail". Shared with the Desk.

const HELPER = {
  assess_volcanoes: "the Satellite reader and Plume reader", plan_flights: "the Flight planner and Drafter",
  run_recovery: "the Recovery planner", draft_sra: "the Paperwork drafter",
};
const jobs = (n) => `${n} job${Number(n) === 1 ? "" : "s"}`;
// An action word in plain words. The ICAO word (MONITOR, HOLD...) stays under Technical detail
// and on the Desk; the Details main view shows the plain words only.
export function actionPlain(text) {
  const t = String(text || "").trim();
  let m;
  if (/^MONITOR$/.test(t)) return "keep watching";
  if (/^CONTINUE$/.test(t)) return "continue as planned";
  if ((m = /^HOLD(?: (FL\d{3}))?$/.exec(t))) return m[1] ? `hold at ${m[1]}` : "hold";
  if ((m = /^DIVERT(?: ([A-Z]{4}))?$/.exec(t))) return m[1] ? `divert to ${m[1]}` : "divert";
  if ((m = /^CHANGE[ _]LEVEL(?: (.+))?$/.exec(t))) return m[1] ? `change level to ${m[1]}` : "change level";
  if (/^REROUTE\b/.test(t)) return "reroute around the ash";
  return null;
}
const DIFF_WORDS = {
  LAG: "one source is older than another", ENVELOPE: "an observed height sits inside the official band",
  HEIGHT_MISMATCH: "the sources report different heights", DIRECTION_MISMATCH: "the sources send the ash different ways",
  SILENCE: "no VAA answers a reported eruption", CONFLICT: "a VAA says no ash while another source saw it",
};
const num = (n) => Number(n).toLocaleString("en-US");
const usdWords = (n) => `$${num(n)}`;
const PLAIN = [
  [/^NO MODEL: (.+)$/, (m) => (actionPlain(m[1]) ? `Flight planner (code only) chose: ${actionPlain(m[1])}` : null)],
  [/^NO MODEL: (\d+) delegation\(s\) made in urgency order\.?$/, (m) => `Coordinator (code only): handed out ${jobs(m[1])} in urgency order.`],
  [/^NO MODEL: urgency order\.?$/, () => "Next in urgency order (code only)"],
  [/^NO MODEL: the plan for the published closure cancels (\d+) flights? and delays (\d+), affects (\d+) passengers and costs (\d+) USD\.?$/,
    (m) => `Planned by code (code only): this plan cancels ${num(m[1])} flight${m[1] === "1" ? "" : "s"} and delays ${num(m[2])}. It affects ${num(m[3])} passengers and costs about ${usdWords(m[4])}.`],
  [/^NO MODEL: official products only\.?$/, () => "Code only: built from the official reports only"],
  [/^DRAFT (.+?) \(NO MODEL\)$/, (m) => `Advisory text written by a code template (code only): ${actionPlain(m[1].replace(/ AROUND HAZARD$/, "")) || m[1].toLowerCase()}`],
  [/^([A-Z0-9][A-Z0-9-]{1,11}): DRAFT (\w+(?: LEVEL)?) waiting for a dispatcher$/, (m) => `${m[1]}: advisory drafted to ${actionPlain(m[2]) || m[2].toLowerCase()}, waiting for a dispatcher`],
  [/^([A-Z0-9][A-Z0-9-]{1,11}): draft superseded \(entry now in (\d+) min\)$/, (m) => `${m[1]}: draft replaced by a newer one (entry now in ${m[2]} min)`],
  [/^(.+): cone OFFICIAL (\d+)% \(NO MODEL\), (\S+), (\d+) official layer\(s\)$/, (m) => `${m[1]}: TEPHRA's estimate is the official area (code only), ${m[3]}, from ${m[4]} official layer${m[4] === "1" ? "" : "s"}`],
  [/^RECOVERY DRAFT STUB: CLOSURE AS FORECAST\b.*$/i, () => "Airport plan drafted by code (code only): closure as forecast"],
  [/^Duty Officer -> run_recovery: Recovery agent started for (.+)$/, (m) => `Coordinator asked the Recovery planner to re-plan ${m[1]}`],
  [/^Duty Officer -> (\w+): ([^:;]+?)(?::|;|$)/, (m) => `Coordinator handed ${m[2]} to ${HELPER[m[1]] || m[1]}`],
  [/^Duty Officer -> (\w+)\b.*$/, (m) => `Coordinator handed a job to ${HELPER[m[1]] || m[1]}`],
  [/^Duty Officer brief: (\d+) delegation\(s\)$/, (m) => `Coordinator handed out ${jobs(m[1])}`],
  [/^ADS-B: no answer within (\d+) s; last good data kept\b.*$/, (m) => `Aircraft data did not answer in ${m[1]} s. Showing the last good positions.`],
  [/^ADS-B: (\d+) of (\d+) adsb\.lol points failed\b.*$/, (m) => `Aircraft data: ${m[1]} of ${m[2]} areas failed (bad reply)`],
  [/^plan_flights\(\).*$/, () => "Planned and drafted per flight"],
  [/^Closed airports changed: (.+); recovery agent started$/, (m) => `Airports closed by ash changed (${m[1]}). Re-planning.`],
  [/^Duty Officer · STUB · NO MODEL · TURNS 0 · OFFERED (\d+)$/, (m) => `Coordinator (code only): handed out ${jobs(m[1])} in urgency order`],
  [/^OFFERED (\d+) · (\d+) mandatory$/, (m) => `${jobs(m[1])} given (${m[2]} must do)`],
  [/^MANDATORY$/, () => "Must do"],
  [/^NO MODEL: stub plume estimate (OFFICIAL|WIDENED|HYPOTHESIS) FL(\d{3})-FL(\d{3}), (\d+)%$/, (m) => `Plume estimate by code (code only): ${m[1] === "OFFICIAL" ? "same as the official area" : m[1].toLowerCase()}, ${m[2] === "000" ? "SFC" : `FL${m[2]}`}–FL${m[3]}, confidence ${m[4]}%`],
  [/^SRA DRAFT FOR (.+?): EVIDENCE BY CODE, (\d+) NARRATIVE BOX(?:ES)? \((NO MODEL|AI-WRITTEN)\); NOT AN APPROVED SRA$/, (m) => `Safety risk assessment draft for ${m[1].replace(/\b([A-Z])([A-Z]+)\b/g, (_, a, b) => a + b.toLowerCase())}: evidence by code, ${m[2]} narrative box${m[2] === "1" ? "" : "es"} ${m[3] === "NO MODEL" ? "by a code template (code only)" : `drafted by ${ASSISTANT}`}. Not an approved SRA.`],
  [/^(.+): cone (OFFICIAL|WIDENED|HYPOTHESIS) (\d+)%(?: \(NO MODEL\))?, (\S+), (\d+) official layer\(s\)$/, (m) => `${m[1]}: TEPHRA's estimate is ${m[2] === "OFFICIAL" ? "the official area" : m[2] === "WIDENED" ? "wider than the official area" : "a hypothesis"}, ${m[4]}, from ${m[5]} official layer${m[5] === "1" ? "" : "s"}`],
  [/^(.+): no CAUTION or WARNING discrepancy, no HYPOTHESIS case and no airline aircraft seen within 250 NM; cone from official products only$/, (m) => `${m[1]}: nothing to check and no ${airline().code} flight within 250 NM, so TEPHRA's estimate is the official area`],
  [/^Plume read queued for the Duty Officer \((\w+) FL(\d{3})-FL(\d{3}), (\d+)%\)$/, (m) => `Plume read queued for the Coordinator (${m[2] === "000" ? "SFC" : `FL${m[2]}`}–FL${m[3]})`],
  [/^(.+) is active: (.+)$/, (m) => `${m[1]} is active. Reports: ${machineText(m[2].replace(/; Valid SIGMET ([A-Z]{4}) (\d+): names it/g, " · SIGMET $1 $2").replace(/^Valid SIGMET ([A-Z]{4}) (\d+): names it/, "SIGMET $1 $2"))}`],
  [/^(.+?): (\d+) new or changed record\(s\)$/, (m) => `${m[1]}: ${m[2]} new or changed record${m[2] === "1" ? "" : "s"}`],
  // The helpers' own tool calls (raw JSON stays under Technical detail; docs/UI-DETAILS-PANELS.md 5.1)
  [/^get_flight: \{"proxy_flight":"([^"]+)"/, (m) => `Flight planner looked up the position and track of ${m[1]}`],
  [/^list_alternates: /, () => "Flight planner checked alternate airports"],
  [/^list_reroutes: /, () => "Flight planner checked reroute options"],
  [/^check_level_band: \{"band":"FL(\d{3})-FL(\d{3})","clear_of_hazard":(true|false)/, (m) => `Flight planner checked levels ${m[1] === "000" ? "SFC" : `FL${m[1]}`}–FL${m[2]}: ${m[3] === "true" ? "clear of the ash" : "not clear of the ash"}`],
  [/^submit_plan: \{"accepted":(true|false)/, (m) => `Flight planner handed in its plan: the checks ${m[1] === "true" ? "accepted it" : "did not accept it"}`],
  [/^PLAN ACCEPTED: (.+)$/, (m) => `Flight planner's choice passed the checks: ${actionPlain(m[1]) || m[1].toLowerCase()}`],
  [/^PLAN REPAIRED(?: at \d+Z)?: (.+)$/, (m) => `Flight planner's second try passed the checks: ${actionPlain(m[1]) || m[1].toLowerCase()}`],
  [/^PLAN REJECTED; ONE REPAIR TURN$/, () => "Flight planner's plan failed the checks: one more try"],
  [/^DRAFT REJECTED; ONE REPAIR CALL$/, () => "Drafter's draft failed the checks: one more try"],
  [/^estimate_cost: \{"action":"(\w+)","minutes":(\d+),"fuel_kg":(\d+)/, (m) => `Flight planner priced ${actionPlain(m[1]) || m[1].toLowerCase()}: ${m[2]} min, ${Number(m[3]).toLocaleString("en-US")} kg fuel`],
  [/^check_alternate: \{"icao":"([A-Z]{4})","acceptable":(true|false)/, (m) => `Flight planner checked ${m[1]}: ${m[2] === "true" ? "acceptable" : "not acceptable"}`],
  [/^Duty Officer -> \w+: \{.*"error":"([^"]+)"/, (m) => `Coordinator: ${m[1].charAt(0) + m[1].slice(1).toLowerCase()}`],
  // any other tool call: its name in words; the JSON stays under Technical detail
  [/^([a-z]+(?:_[a-z]+)+): [{[]/, (m) => `Used the ${m[1].replace(/_/g, " ")} tool`],
  [/^DRAFT (.+?) \(AI-DRAFTED\)$/, (m) => `Drafter wrote the advisory: ${actionPlain(m[1].replace(/ AROUND HAZARD$/, "")) || m[1].toLowerCase()}`],
  [/^Plume Reader: asking \S+ \((\d+) texts?, (\d+) images?, (\d+) discrepanc(?:y|ies)\)$/, (m) => `Plume reader is reading ${m[1]} report${m[1] === "1" ? "" : "s"}${m[2] !== "0" ? `, ${m[2]} picture${m[2] === "1" ? "" : "s"}` : ""} and ${m[3]} difference${m[3] === "1" ? "" : "s"}`],
  [/^Plume Reader (accepted|repaired): (OFFICIAL|WIDENED|HYPOTHESIS) FL(\d{3})-FL(\d{3}), (\d+)%$/, (m) => `Plume reader's estimate passed the checks${m[1] === "repaired" ? " after one repair" : ""}: ${m[2] === "OFFICIAL" ? "same as the official area" : m[2] === "WIDENED" ? "wider than the official area" : "a hypothesis"}, ${m[3] === "000" ? "SFC" : `FL${m[3]}`}–FL${m[4]}, confidence ${m[5]}%`],
  [/^Duty Officer: (\d+) item\(s\) to dispatch\b.*$/, (m) => `Coordinator has ${jobs(m[1])} to hand out`],
  [/^Duty Officer deferred (\d+) item\(s\):/, (m) => `Coordinator left ${m[1]} optional ${Number(m[1]) === 1 ? "job" : "jobs"} for the next run`],
  [/^Duty Officer brief: (\d+) delegation\(s\), (\d+) deferred$/, (m) => `Coordinator handed out ${jobs(m[1])} and left ${m[2]} for the next run`],
  // a quota refusal in plain words says only that the step did not run: the line is history and
  // the refusal may be one skill's share, so it is never "paused"; the quota is said at the
  // assistant's home, and the raw line stays under Technical detail (8.6)
  [/^Duty Officer AI UNAVAILABLE \(budget_exhausted\); (\d+) delegation\(s\) made, (\d+) mandatory item\(s\) to the Desk$/,
    (m) => `Coordinator did not run. ${m[1] !== "0" ? `It handed out ${jobs(m[1])}; ` : ""}${jobs(m[2])} that must be done went to the Desk`],
  [/^Duty Officer AI UNAVAILABLE \(GEMINI DAILY QUOTA SPENT.*?\); (\d+) delegation\(s\) made, (\d+) mandatory item\(s\) to the Desk$/,
    (m) => `Coordinator did not run. ${m[1] !== "0" ? `It handed out ${jobs(m[1])}; ` : ""}${jobs(m[2])} that must be done went to the Desk`],
  [/^Duty Officer AI UNAVAILABLE \((.+)\); (\d+) delegation\(s\) made, (\d+) mandatory item\(s\) to the Desk$/,
    (m) => `Coordinator ${notRun(reasonClass(m[1])) ? "did not run." : `gave no result (${plainWhy(reasonClass(m[1]))}).`} ${m[2] !== "0" ? `It handed out ${jobs(m[2])}; ` : ""}${jobs(m[3])} that must be done went to the Desk`],
  [/^Plume read: (.+?) \((.+)\): not dispatched; the area stays at the official products$/,
    (m) => `Plume read for ${m[1]} was not handed out${notRun(reasonClass(m[2])) ? "" : ` (${m[2]})`}. TEPHRA's area stays at the official reports`],
  [/^Duty Officer left (\d+) mandatory item\(s\) undone: to the Desk$/, (m) => `Coordinator passed ${m[1]} must-do ${Number(m[1]) === 1 ? "job" : "jobs"} to the Desk`],
  [/^([A-Z0-9][A-Z0-9-]{1,11}) \([^)]*\) is inside the (.+) cone at (FL\d{3})$/, (m) => `${m[1]} is inside TEPHRA's area at ${m[2]}, ${m[3]}`],
  [/^([A-Z0-9][A-Z0-9-]{1,11}) \([^)]*\) enters the (.+) cone in (\d+) min at (FL\d{3}) if track and level are held$/, (m) => `${m[1]} enters TEPHRA's area at ${m[2]} in ${m[3]} min, at ${m[4]}, if track and level are held`],
  [/^([A-Z0-9][A-Z0-9-]{1,11}): draft superseded \(no longer exposed if track and level are held\)$/, (m) => `${m[1]}: draft withdrawn, no longer heading into the area if track and level are held`],
  [/^(.+): (OFFICIAL|WIDENED|HYPOTHESIS) (\d+)% (\S+); (\d+) flight\(s\) exposed$/, (m) => `${m[1]}: TEPHRA's estimate is ${m[2] === "OFFICIAL" ? "the official area" : m[2] === "WIDENED" ? "wider than the official area" : "a hypothesis"}, ${m[4]}, confidence ${m[3]}%; ${m[5]} flight${m[5] === "1" ? "" : "s"} inside or heading in`],
  [/^([A-Z0-9][A-Z0-9-]{1,11}): DRAFT (\w+(?: LEVEL)?) for a dispatcher$/, (m) => `${m[1]}: advisory drafted to ${actionPlain(m[2]) || m[2].toLowerCase()}, for a dispatcher`],
  [/^([A-Z0-9][A-Z0-9-]{1,11}): same advice as an open draft$/, (m) => `${m[1]}: same advice as an open draft, so no new one`],
  [/^disruption: \{/, () => "Recovery planner was given the closed airports and the day's flights"],
  [/^run_scenario: \{.*"label":"([^"]+)".*?"status":"([A-Z_]+)"/, (m) => `Recovery planner tried a scenario: ${m[1].toLowerCase()} (${m[2].toLowerCase().replace(/_/g, " ")})`],
  [/^(.+): (LAG|ENVELOPE|HEIGHT_MISMATCH|DIRECTION_MISMATCH|SILENCE|CONFLICT) - /, (m) => `${m[1]}: ${DIFF_WORDS[m[2]]}`],
  [/^AI UNAVAILABLE: RECOVERY AGENT ERROR: TimeoutError\b/, () => "Recovery planner gave no result (timed out). No plan was made, so a dispatcher must plan the network."],
  [/^AI UNAVAILABLE: RECOVERY AGENT ERROR: (\w+)/, (m) => `Recovery planner gave no result (it stopped with an error, ${m[1]}). No plan was made, so a dispatcher must plan the network.`],
  // Any other code-template line: say who wrote it in words, keep the rest as written.
  [/^NO MODEL: (.+)$/, (m) => `Written by code (code only): ${/[a-z]/.test(m[1]) ? m[1] : m[1].charAt(0) + m[1].slice(1).toLowerCase()}`],
  // Any other line the coordinating agent wrote: its name on screen is "Coordinator" (Naming); the
  // raw line, with the code's own name, stays under Technical detail.
  // A line that also carries a raw rule-9 reason ("AI UNAVAILABLE") is not paraphrased: it is
  // shown verbatim, like any line no pattern knows.
  [/\bDuty Officer\b/, (m) => (/AI UNAVAILABLE/.test(m.input) ? null : machineText(m.input.replace(/\bDuty Officer\b/g, "Coordinator")))],
  [/^AI UNAVAILABLE: NO FEASIBLE PLAN FOR THE PUBLISHED CLOSURE \((\w+)\).*$/, (m) => (m[1] === "UNKNOWN" ? "Airport plan: no plan found (the solver did not finish in time). A dispatcher must plan the network by hand." : `Airport plan: no plan found (solver: ${m[1]}). A dispatcher must plan the network by hand.`)],
];

export function plainLine(text) {
  const raw = String(text ?? "");
  for (const [re, fn] of PLAIN) {
    const m = re.exec(raw);
    const out = m ? fn(m) : null;
    if (out) return out;
  }
  return machineText(raw);
}

// ------------------------------------------------------------------ one failure in a few words
// One occurrence of a failed assistant step in a few words, for the occurrence lines under a cause
// (docs/UI-DETAILS-PANELS.md 3.3): a fixed table, like PLAIN. `num` is the number of jobs it left,
// for "1–18 must-do jobs per run". A line the table does not know keeps its own plain line; the
// raw line stays under Technical detail.
const CAUSES = [
  { stage: "DUTY", re: /^Duty Officer AI UNAVAILABLE \((?:budget_exhausted|GEMINI DAILY QUOTA SPENT[^;]*)\); \d+ delegation\(s\) made, (\d+) mandatory/, each: (m) => `${jobs(m[1])} to the Desk` },
  { stage: "DUTY", re: /^Plume read: (.+?) \((.+)\): not dispatched/, each: (m) => `${m[1]}: ${notRun(reasonClass(m[2])) ? "not handed out" : m[2]}` },
  { stage: "DUTY", re: /^Duty Officer left (\d+) mandatory item\(s\) undone: to the Desk$/, each: (m) => `${jobs(m[1])} to the Desk` },
  { stage: "RECOVERY", re: /RECOVERY AGENT ERROR: TimeoutError/, each: () => "timed out" },
  { stage: "RECOVERY", re: /RECOVERY AGENT ERROR: (\w+)/, each: (m) => m[1] },
  { stage: "RECOVERY", re: /NO FEASIBLE PLAN[^(]*\(UNKNOWN\)/, each: () => "no plan" },
  { stage: "RECOVERY", re: /NO FEASIBLE PLAN[^(]*\((\w+)\)/, each: (m) => `solver: ${m[1].toLowerCase()}` },
  { stage: "DRAFTER", re: /DRAFT FAILED CHECKS/, each: () => "failed the checks" },
];

export function failureEach(t) {
  const msg = String(t.message || "");
  for (const c of CAUSES) {
    if (c.stage !== t.stage) continue;
    const m = c.re.exec(msg);
    if (m) return { each: c.each(m), num: m[1] && /^\d+$/.test(m[1]) ? Number(m[1]) : null };
  }
  const plain = plainLine(msg);
  return { each: plain === msg && /AI UNAVAILABLE/i.test(msg) ? plainWhy(reasonClass(msg)) || "did not run" : plain, num: null };
}

// Who did a step, in words (stage chips: CODE / ADK / NO MODEL).
export const ACTOR_WORDS = { code: "by code", gemini: `by ${ASSISTANT}`, adk: `by ${ASSISTANT}`, stub: "code template", human: "by a person", system: "by the system" };
// Agent-framework ("adk") steps code writes before any model is called: the Coordinator's work
// list. They say "by code (agent worklist)"; "by TEPHRA Assistant" is kept for steps a model took
// (docs/UI-AI-QUIET.md D63).
const ADK_CODE = [/^Duty Officer: \d+ item\(s\) to dispatch\b/];
// With the assistant off (the stub backend) the agent framework still runs, but no model speaks:
// an "adk" or "gemini" step is then code following the skill's script, so it says "code
// template" (review 1, 6; the AI-off state itself is said once, by the tab-bar status).
export const actorWords = (actor, stub, message = "") => {
  if (stub && (actor === "adk" || actor === "gemini")) return ACTOR_WORDS.stub;
  if (actor === "adk" && ADK_CODE.some((re) => re.test(String(message)))) return "by code (agent worklist)";
  return ACTOR_WORDS[actor] || String(actor || "");
};

// "$62,525" (R2.8)
const USD = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
export const usd = (n) => (n == null || !Number.isFinite(Number(n)) ? "n/a" : USD.format(Number(n)));

// A plan's recorded reasons, each once: the planner often writes the same text as the plan's reason
// and as its only validation error.
// The comparison drops the "AI UNAVAILABLE: " prefix the plan's reason carries and its error does not.
const planReasons = (plan) => {
  const seen = new Set();
  return [plan.unavailable_reason, ...(plan.validation_errors || [])].filter(Boolean).filter((r) => {
    const k = String(r).replace(/^AI UNAVAILABLE:?\s*/i, "");
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
};

// A recovery plan that found no plan: the solver's status in plain words, never the assistant's
// failure (R2.6). Returns null when the plan's failure is not a solver result.
export function planProblem(plan) {
  if (!plan) return null;
  const raw = planReasons(plan).join(" · ");
  const fromText = /NO FEASIBLE PLAN[^(]*\(([A-Z_]+)\)|HAS NO PLAN \(([A-Z_]+)\)/.exec(raw);
  const noPlan = (plan.scenarios || []).find((s) => s.status === "NO_PLAN");
  const status = fromText ? fromText[1] || fromText[2] : plan.status === "AI_UNAVAILABLE" && noPlan ? noPlan.solver_status : null;
  if (!status) return null;
  const words = status === "INFEASIBLE"
    ? "No plan found: no plan fits the closures. A dispatcher must plan the network by hand."
    : status === "UNKNOWN"
      ? "No plan found: the solver did not finish in time. A dispatcher must plan the network by hand."
      : `No plan found (solver: ${status}). A dispatcher must plan the network by hand.`;
  return { status, words, raw };
}

// A plan with no plan, in plain words for Details › Airport closures: the solver's result when
// there is one (planProblem), else what stopped the recovery planner. Never "chosen by" a model
// when nothing was chosen. `raw` is the reason as recorded, for Technical detail; `place` the
// story's closure sub-line ("No airport plan (Recovery planner gave no result): plan the network
// by hand"); `ai` whether the assistant (not the solver) is why there is no plan.
export function planFailure(plan) {
  if (!plan || plan.status !== "AI_UNAVAILABLE") return null;
  const p = planProblem(plan);
  const raw = planReasons(plan).join(" · ") || "no reason given";
  if (p) {
    const solver = p.status.toLowerCase().replace(/_/g, " ");
    return {
      title: p.status === "UNKNOWN" ? "Recovery found no plan: the solver did not finish in time" : p.status === "INFEASIBLE" ? "Recovery found no plan: no plan fits the closures" : `Recovery found no plan (solver: ${solver})`,
      sub: "A dispatcher must plan the network by hand.", short: "no plan: plan the network by hand", raw, ai: false,
      place: `No airport plan (${p.status === "UNKNOWN" ? "the solver did not finish in time" : p.status === "INFEASIBLE" ? "no plan fits the closures" : `solver: ${solver}`}): plan the network by hand`,
    };
  }
  const m = /RECOVERY AGENT ERROR: (\w+)/.exec(raw);
  // `why` is the cause in full, for the assistant's home; `word` says what happened in a main
  // view: a quota refusal called no model, so it "did not run", with no cause (8.6)
  const cls = reasonClass(raw);
  const word = notRun(cls) ? "Recovery planner did not run" : `Recovery planner gave no result (${WHY[cls] || WHY.other})`;
  const base = { short: "no plan: plan the network by hand", raw, ai: true, cls, why: cls === "unavailable" ? unavailableWhy(raw) : WHY[cls] || WHY.other, word,
    place: `No airport plan (Recovery planner ${notRun(cls) ? "did not run" : "gave no result"}): plan the network by hand` };
  if (notRun(cls)) return { ...base, title: "No plan: Recovery planner did not run", sub: "Nothing was put in its place. A dispatcher must plan the network by hand." };
  if (m && m[1] === "TimeoutError") return { ...base, title: "Recovery planner timed out", sub: "No plan was made. A dispatcher must plan the network by hand." };
  if (m) return { ...base, title: "Recovery planner stopped with an error", sub: "No plan was made. A dispatcher must plan the network by hand." };
  return { ...base, title: "No plan: Recovery planner gave no result", sub: "Nothing was put in its place. A dispatcher must plan the network by hand." };
}

// Machine text shown on the page (a recorded reason, a trace line, a closure's reason, a contract
// label): its clause separator becomes the page's middle dot, so no page text carries a
// semicolon. The words are unchanged. Official products, advisory text and model-written prose
// are records and are shown exactly as written.
export const machineText = (t, sep = " · ") => String(t ?? "").replace(/\s*;\s+/g, sep);
// Code-written prose (a backtest caveat): each clause after a semicolon becomes its own sentence.
export const machineSentences = (t) => String(t ?? "").replace(/\s*;\s+(\S)/g, (_, c) => `. ${c.toUpperCase()}`);

// "Technical detail" disclosure holding raw machine text (R12.7).
export function techDetail(...lines) {
  const kept = lines.flat().filter((l) => l != null && l !== "");
  if (!kept.length) return null;
  return el("details", { class: "tech" }, el("summary", { text: "Technical detail" }), ...kept.map((l) => (l instanceof Node ? l : el("p", { class: "tech__line mono", text: machineText(l) }))));
}
