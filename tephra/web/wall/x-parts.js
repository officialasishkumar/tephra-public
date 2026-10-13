// Small building blocks shared by the Wall's Details sections (ext.js, duty.js, panels.js), and the
// one derived AI state both the Wall and the Desk word their AI lines from (docs/UI-AI-QUIET.md).
// Every string goes in through el() (textContent); AI-written text carries a short mark whose
// model id sits in its title and label, never in the visible text.

import { el, icon, hhmmz } from "./util.js";

// The mark set (docs/UI-AI-QUIET.md Q5): "AI-written", "AI-read", "AI-chosen", and "Code (AI off)"
// when no model wrote it. Only for content a model actually produced (a model id, and an outcome
// that passed the checks); the model id goes in the title and the label.
export function aiMark(modelId, label, verb = "AI-written") {
  const no = label === "NO MODEL" || !modelId || modelId === "stub" || modelId === "none";
  const title = no ? "No model wrote this: code did (the offline stub, NO MODEL)" : `${verb} by ${modelId}. Code checked every number, time and id.`;
  return el("span", { class: `ai-mark${no ? " ai-mark--none" : ""}`, title, "aria-label": no ? "Code (AI off)" : `${verb} by ${modelId}` },
    icon(no ? "i-code" : "i-model"), el("span", { text: no ? "Code (AI off)" : verb, "aria-hidden": "true" }));
}

// ------------------------------------------------------------------ the AI state (UI-AI-QUIET 1.2)
// AI is in one state: on, paused (today's quota used up), trouble (n causes) or off (stub).
// Failures count by cause (helper + reason class), never by step or tick. Pure: the Wall passes
// its trace, newest Duty Officer run, newest airport plan and the live budget; the Desk its
// failures, Duty Officer run and budget.

export const HELPER_NAME = {
  duty: "Duty Officer", plume: "Plume Reader", sat: "Satellite reader", planner: "Planner", drafter: "Drafter", ask: "Ask",
  notice: "Notice reader", recovery: "Recovery planner", messages: "Messages", docs: "Paperwork drafter",
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

// The reason class of a failure (budget, timeout, checks, error, other), from the recorded reason.
export function reasonClass(reason) {
  const r = String(reason || "");
  if (/budget_exhausted|DAILY QUOTA|RESOURCE_EXHAUSTED|\b429\b|quota/i.test(r)) return "budget";
  if (/Timeout|timed out/i.test(r)) return "timeout";
  if (/FAILED CHECKS|validation|did not pass/i.test(r)) return "checks";
  if (/ERROR\b|Error\b|exception/i.test(r)) return "error";
  return "other";
}
// "{why}" in "AI unavailable ({why})" (UI-AI-QUIET 1.1).
export const WHY = {
  timeout: "timed out", checks: "the answer failed the code's checks", error: "the AI stopped with an error", other: "the AI could not answer",
  budget: "daily quota", undone: "left undone",
};

// The helper a failure belongs to: a Duty Officer line about a plume read is the Plume Reader's.
function helperOf(stage, reason) {
  if ((stage === "DUTY" || stage === "duty_officer") && /^Plume read: /.test(String(reason || ""))) return "plume";
  return HELPER_KEY[stage] || String(stage || "").toLowerCase();
}

const liteModel = (budget) => {
  const tier = (budget?.tiers || []).find((t) => t.tier === "lite");
  const models = Array.isArray(budget?.models) ? budget.models : [];
  return (tier && models.find((m) => m.model_id === tier.model_id)) || models.find((m) => /every other/i.test(m.jobs || "")) || null;
};

// errors: [{ stage, reason, at (ms), raw }]. plan: the newest airport plan. duty: the newest run.
export function aiStateOf({ stub = false, budget = null, errors = [], duty = null, plan = null }) {
  const lite = liteModel(budget);
  const closed = !stub && lite?.closed === true;
  const resets = Date.parse(budget?.resets_at || "");
  // a statement about now, on the real clock, from the current budget only: shown in REPLAY too
  const until = closed && Number.isFinite(resets) ? hhmmz(resets) : null;
  const groups = new Map();
  const add = (helperKey, reason, at, raw, src) => {
    const special = /^Duty Officer left \d+ mandatory item/.test(String(reason || ""));
    const cls = special ? "undone" : reasonClass(reason);
    const key = `${helperKey}|${cls}`;
    let g = groups.get(key);
    if (!g) { g = { key, helperKey, helper: HELPER_NAME[helperKey] || helperKey, reasonClass: cls, items: [], raw: [] }; groups.set(key, g); }
    g.items.push({ at, reason, src });
    g.raw.push(raw || reason);
    return g;
  };
  for (const e of errors) add(helperOf(e.stage, e.reason), e.reason, e.at, e.raw, e.src);
  // the newest airport plan's own failure: older than the trace window, still a cause (D67)
  if (plan && plan.status === "AI_UNAVAILABLE" && !planProblem(plan)) {
    const reason = planReasons(plan).join("; ") || "no reason given";
    const key = `recovery|${reasonClass(reason)}`;
    if (!groups.has(key)) add("recovery", reason, Date.parse(plan.created_at), reason, { plan });
  }
  const dutyReason = duty?.outcome === "MODEL_FAILED" ? (duty.validation_errors || [])[0] || "no reason recorded" : null;
  if (dutyReason && !groups.has(`duty|${reasonClass(dutyReason)}`)) add("duty", dutyReason, Date.parse(duty.finished_at), dutyReason, { duty });
  const causes = [...groups.values()].map((g) => {
    const ts = g.items.map((x) => x.at).filter(Number.isFinite);
    return { ...g, steps: g.items.length, first: ts.length ? Math.min(...ts) : NaN, last: ts.length ? Math.max(...ts) : NaN,
      consequence: CONSEQUENCE[g.helperKey] || "Do this step by hand", link: CAUSE_LINK[g.helperKey] || null };
  }).sort((a, b) => (b.last || 0) - (a.last || 0));
  const paused = !stub && (closed || (dutyReason != null && reasonClass(dutyReason) === "budget"));
  // in "paused", a budget cause is the state itself and is not counted again as trouble
  const trouble = causes.filter((c) => c.reasonClass !== "budget" && c.reasonClass !== "undone");
  const waiting = (Array.isArray(budget?.waiting) ? budget.waiting : []).filter((w) => w.status === "WAITING").map((w) => {
    const t = Date.parse(w.next_slot_at || "");
    return { job: w.label, kind: w.item?.kind || w.kind, slot: Number.isFinite(t) ? hhmmz(t) : null, volcano: w.item?.volcano_id || null };
  });
  const kind = stub ? "off" : paused ? "paused" : trouble.length ? "trouble" : "on";
  return { kind, until, causes, trouble, waiting, paused };
}

const problems = (n) => `${n} problem${n === 1 ? "" : "s"}`;

// The one state in words, for a chip (`label` and its `suffix`), its tooltip and its label.
// `home` names the AI home ("AI helpers" on the Wall, "AI today" on the Desk); `opens` what the
// chip opens. `narrow` (420 px and less) drops the time and the "on".
export function aiWords(s, { home = "AI helpers", opens = "Details, AI helpers", narrow = false } = {}) {
  const never = "AI can widen TEPHRA's estimate, never shrink the official area.";
  if (s.kind === "off") return { label: "AI off", suffix: null, tone: "off", aria: `AI off, code only. Opens ${opens}.`, title: "AI off: no model is connected. Code does every step; code templates write the text." };
  if (s.kind === "paused") {
    const u = s.until ? ` until ${s.until}` : "";
    return { label: "AI paused", suffix: !narrow && s.until ? s.until : null, tone: "caution",
      aria: `AI paused${u}: today's free AI quota is used up. Opens ${opens}.`,
      title: `AI paused${u}: today's free AI quota is used up.${s.until ? " Queued work runs then." : ""} ${never} Open ${home} for models and today's calls.` };
  }
  if (s.kind === "trouble") {
    const n = s.trouble.length;
    return { label: narrow ? "AI" : "AI on", suffix: problems(n), tone: "caution",
      aria: `AI on, ${problems(n)}: ${s.trouble.map((c) => `${c.helper} did not run`).join(", ")}. Opens ${opens}.`,
      title: `AI on, ${problems(n)}: ${s.trouble.map((c) => `${c.helper} did not run (${WHY[c.reasonClass]}); nothing was put in its place`).join("; ")}. ${never} Open ${home} for the details.` };
  }
  return { label: "AI on", suffix: null, tone: "on", aria: `AI on. Opens ${opens}.`, title: `AI on. It can widen TEPHRA's estimate, never shrink the official area. AI-written parts are marked.` };
}

// The calm lead at the AI home (UI-AI-QUIET 5.1): one paragraph, a sentence per cause.
export function aiLead(s) {
  const at = (t) => (Number.isFinite(t) ? ` at ${hhmmz(t)}` : "");
  const causeLine = (c) => `${c.helper} did not run (${WHY[c.reasonClass]})${at(c.last)}; nothing was put in its place. ${c.consequence}.`;
  if (s.kind === "off") return [{ strong: "AI off.", text: "No model is connected. Code does every step; code templates write the text." }];
  if (s.kind === "on") return [{ strong: "AI on.", text: "It can widen TEPHRA's estimate, never shrink the official area. AI-written parts are marked." }];
  if (s.kind === "trouble") return [{ strong: `AI on, ${problems(s.trouble.length)}.`, text: s.trouble.map(causeLine).join(" ") }];
  const n = s.waiting.length;
  const jobs = n ? `Queued work (${n} job${n === 1 ? "" : "s"}) ${s.until ? "runs then" : "waits"}, on the same model; nothing is dropped or handed to another model. ` : "";
  const out = [{ strong: s.until ? `AI paused until ${s.until}.` : "AI paused.",
    text: `${s.until ? "Google reported today's free AI quota used up." : "Today's free AI quota was used up."} ${jobs}Until then, code still checks every flight against the official area, and nothing is made up in place of an AI step. Flights that need a plan are on the Desk to plan by hand.` }];
  if (s.trouble.length) out.push({ strong: "Also:", text: s.trouble.map(causeLine).join(" ") });
  return out;
}

// One cause in §1.1 words, for the cause lists (What went wrong, the trace).
export function causeTitle(c) {
  if (c.reasonClass === "undone") return `${c.helper} passed must-do jobs to the Desk`;
  if (c.reasonClass === "budget") return `${c.helper} did not run: AI paused (daily quota)`;
  return `${c.helper} did not run: AI unavailable (${WHY[c.reasonClass]})`;
}

// Why a flight has no AI draft, when that is the AI's doing: { word, marker, until/why/slot }, or
// null when the AI is on and fine (or off: the stub drafts too).
export function draftBlock(s) {
  if (!s || s.kind === "off") return null;
  if (s.kind === "paused") return { word: "AI paused", until: s.until };
  const c = s.trouble.find((x) => x.helperKey === "duty" || x.helperKey === "planner" || x.helperKey === "drafter");
  if (c) return { word: "AI unavailable", why: WHY[c.reasonClass] };
  const w = s.waiting.find((x) => x.kind === "PLAN");
  if (w) return { word: "AI waiting", slot: w.slot };
  return null;
}

// Flights to plan by hand (docs/UI-AI-QUIET.md D56): every RFA flight in or heading in, all
// volcanoes, with no current advisory while the AI cannot draft (paused or unavailable; a queued
// draft is waiting, not missing). The Duty Officer's must-do flights first, then inside now, then
// the soonest entry. `block` says why (draftBlock); no flights when the AI can draft.
export function handPlanOf(D, store, ai) {
  const block = draftBlock(ai);
  if (!D || !block || block.word === "AI waiting") return { block, flights: [], must: 0 };
  const run = store?.snapshot?.duty;
  const must = new Set((run?.undispatched || []).map((id) => (run.worklist || []).find((i) => i.id === id)).filter((i) => i && i.kind === "PLAN").map((i) => i.subject));
  const flights = D.exposed.map((f) => ({ f, p: f.properties, key: `${f.properties.hex}:${f.properties.volcano_id}` }))
    .filter((x) => { const a = D.advByFlight.get(x.key); return !a || a.status === "SUPERSEDED"; })
    .map((x) => ({ ...x, must: must.has(x.key) }))
    .sort((a, b) => Number(b.must) - Number(a.must) || Number(!!b.p.inside) - Number(!!a.p.inside) || (a.p.minutes_to_entry ?? 0) - (b.p.minutes_to_entry ?? 0));
  return { block, flights, must: flights.filter((x) => x.must).length };
}

// ------------------------------------------------------------------ plain words (UI-REDESIGN R12.7)
// Code-written trace and AI lines in plain words. A fixed table of patterns: a line that matches
// none is shown verbatim and never paraphrased, and the raw line always stays reachable under
// "Technical detail". Shared with the Desk.

const HELPER = {
  assess_volcanoes: "the Satellite and Plume helpers", plan_flights: "the Planner and Drafter",
  run_recovery: "the Recovery helper", draft_sra: "the SRA drafter",
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
  [/^NO MODEL: (.+)$/, (m) => (actionPlain(m[1]) ? `Planner (AI off) chose: ${actionPlain(m[1])}` : null)],
  [/^NO MODEL: (\d+) delegation\(s\) made in urgency order\.?$/, (m) => `Duty Officer (AI off): handed out ${jobs(m[1])} in urgency order.`],
  [/^NO MODEL: urgency order\.?$/, () => "Next in urgency order (AI off)"],
  [/^NO MODEL: the plan for the published closure cancels (\d+) flights? and delays (\d+), affects (\d+) passengers and costs (\d+) USD\.?$/,
    (m) => `Planned by code (AI off): this plan cancels ${num(m[1])} flight${m[1] === "1" ? "" : "s"} and delays ${num(m[2])}. It affects ${num(m[3])} passengers and costs about ${usdWords(m[4])}.`],
  [/^NO MODEL: official products only\.?$/, () => "AI off: built from the official reports only"],
  [/^DRAFT (.+?) \(NO MODEL\)$/, (m) => `Advisory text written by a code template (AI off): ${actionPlain(m[1].replace(/ AROUND HAZARD$/, "")) || m[1].toLowerCase()}`],
  [/^(RFA\d+): DRAFT (\w+(?: LEVEL)?) waiting for a dispatcher$/, (m) => `${m[1]}: advisory drafted to ${actionPlain(m[2]) || m[2].toLowerCase()}, waiting for a dispatcher`],
  [/^(RFA\d+): draft superseded \(entry now in (\d+) min\)$/, (m) => `${m[1]}: draft replaced by a newer one (entry now in ${m[2]} min)`],
  [/^(.+): cone OFFICIAL (\d+)% \(NO MODEL\), (\S+), (\d+) official layer\(s\)$/, (m) => `${m[1]}: TEPHRA's estimate is the official area (AI off), ${m[3]}, from ${m[4]} official layer${m[4] === "1" ? "" : "s"}`],
  [/^RECOVERY DRAFT STUB: CLOSURE AS FORECAST\b.*$/i, () => "Airport plan drafted by code (AI off): closure as forecast"],
  [/^Duty Officer -> run_recovery: Recovery agent started for (.+)$/, (m) => `Duty Officer asked the Recovery helper to re-plan ${m[1]}`],
  [/^Duty Officer -> (\w+): ([^:;]+?)(?::|;|$)/, (m) => `Duty Officer handed ${m[2]} to ${HELPER[m[1]] || m[1]}`],
  [/^Duty Officer -> (\w+)\b.*$/, (m) => `Duty Officer handed a job to ${HELPER[m[1]] || m[1]}`],
  [/^Duty Officer brief: (\d+) delegation\(s\)$/, (m) => `Duty Officer handed out ${jobs(m[1])}`],
  [/^ADS-B: no answer within (\d+) s; last good data kept\b.*$/, (m) => `Aircraft data did not answer in ${m[1]} s. Showing the last good positions.`],
  [/^ADS-B: (\d+) of (\d+) adsb\.lol points failed\b.*$/, (m) => `Aircraft data: ${m[1]} of ${m[2]} areas failed (bad reply)`],
  [/^plan_flights\(\).*$/, () => "Planned and drafted per flight"],
  [/^Closed airports changed: (.+); recovery agent started$/, (m) => `Airports closed by ash changed (${m[1]}). Re-planning.`],
  [/^Duty Officer · STUB · NO MODEL · TURNS 0 · OFFERED (\d+)$/, (m) => `Duty Officer (AI off): handed out ${jobs(m[1])} in urgency order`],
  [/^OFFERED (\d+) · (\d+) mandatory$/, (m) => `${jobs(m[1])} given (${m[2]} must do)`],
  [/^MANDATORY$/, () => "Must do"],
  [/^NO MODEL: stub plume estimate (OFFICIAL|WIDENED|HYPOTHESIS) FL(\d{3})-FL(\d{3}), (\d+)%$/, (m) => `Plume estimate by code (AI off): ${m[1] === "OFFICIAL" ? "same as the official area" : m[1].toLowerCase()}, ${m[2] === "000" ? "SFC" : `FL${m[2]}`}–FL${m[3]}, confidence ${m[4]}%`],
  [/^SRA DRAFT FOR (.+?): EVIDENCE BY CODE, (\d+) NARRATIVE BOX(?:ES)? \((NO MODEL|AI-WRITTEN)\); NOT AN APPROVED SRA$/, (m) => `Safety risk assessment draft for ${m[1].replace(/\b([A-Z])([A-Z]+)\b/g, (_, a, b) => a + b.toLowerCase())}: evidence by code, ${m[2]} narrative box${m[2] === "1" ? "" : "es"} ${m[3] === "NO MODEL" ? "by a code template (AI off)" : "written by AI"}. Not an approved SRA.`],
  [/^(.+): cone (OFFICIAL|WIDENED|HYPOTHESIS) (\d+)%(?: \(NO MODEL\))?, (\S+), (\d+) official layer\(s\)$/, (m) => `${m[1]}: TEPHRA's estimate is ${m[2] === "OFFICIAL" ? "the official area" : m[2] === "WIDENED" ? "wider than the official area" : "a hypothesis"}, ${m[4]}, from ${m[5]} official layer${m[5] === "1" ? "" : "s"}`],
  [/^(.+): no CAUTION or WARNING discrepancy, no HYPOTHESIS case and no airline aircraft seen within 250 NM; cone from official products only$/, (m) => `${m[1]}: nothing to check and no RFA flight within 250 NM, so TEPHRA's estimate is the official area`],
  [/^Plume read queued for the Duty Officer \((\w+) FL(\d{3})-FL(\d{3}), (\d+)%\)$/, (m) => `Plume read queued for the Duty Officer (${m[2] === "000" ? "SFC" : `FL${m[2]}`}–FL${m[3]})`],
  [/^(.+) is active: (.+)$/, (m) => `${m[1]} is active. Reports: ${m[2].replace(/; Valid SIGMET ([A-Z]{4}) (\d+): names it/g, "; SIGMET $1 $2").replace(/^Valid SIGMET ([A-Z]{4}) (\d+): names it/, "SIGMET $1 $2")}`],
  [/^(.+?): (\d+) new or changed record\(s\)$/, (m) => `${m[1]}: ${m[2]} new or changed record${m[2] === "1" ? "" : "s"}`],
  // The helpers' own tool calls (raw JSON stays under Technical detail; docs/UI-DETAILS-PANELS.md 5.1)
  [/^get_flight: \{"proxy_flight":"(RFA\d+)"/, (m) => `Planner looked up the position and track of ${m[1]}`],
  [/^list_alternates: /, () => "Planner checked alternate airports"],
  [/^list_reroutes: /, () => "Planner checked reroute options"],
  [/^check_level_band: \{"band":"FL(\d{3})-FL(\d{3})","clear_of_hazard":(true|false)/, (m) => `Planner checked levels ${m[1] === "000" ? "SFC" : `FL${m[1]}`}–FL${m[2]}: ${m[3] === "true" ? "clear of the ash" : "not clear of the ash"}`],
  [/^submit_plan: \{"accepted":(true|false)/, (m) => `Planner handed in its plan: the checks ${m[1] === "true" ? "accepted it" : "did not accept it"}`],
  [/^PLAN ACCEPTED: (.+)$/, (m) => `Planner's choice passed the checks: ${actionPlain(m[1]) || m[1].toLowerCase()}`],
  [/^DRAFT (.+?) \(AI-DRAFTED\)$/, (m) => `Drafter wrote the advisory (AI-written): ${actionPlain(m[1].replace(/ AROUND HAZARD$/, "")) || m[1].toLowerCase()}`],
  [/^Plume Reader: asking \S+ \((\d+) texts?, (\d+) images?, (\d+) discrepanc(?:y|ies)\)$/, (m) => `Plume Reader is reading ${m[1]} report${m[1] === "1" ? "" : "s"}${m[2] !== "0" ? `, ${m[2]} picture${m[2] === "1" ? "" : "s"}` : ""} and ${m[3]} difference${m[3] === "1" ? "" : "s"}`],
  [/^Plume Reader (accepted|repaired): (OFFICIAL|WIDENED|HYPOTHESIS) FL(\d{3})-FL(\d{3}), (\d+)%$/, (m) => `Plume Reader's estimate passed the checks${m[1] === "repaired" ? " after one repair" : ""}: ${m[2] === "OFFICIAL" ? "same as the official area" : m[2] === "WIDENED" ? "wider than the official area" : "a hypothesis"}, ${m[3] === "000" ? "SFC" : `FL${m[3]}`}–FL${m[4]}, confidence ${m[5]}%`],
  [/^Duty Officer: (\d+) item\(s\) to dispatch\b.*$/, (m) => `Duty Officer has ${jobs(m[1])} to hand out`],
  [/^Duty Officer deferred (\d+) item\(s\):/, (m) => `Duty Officer left ${m[1]} optional ${Number(m[1]) === 1 ? "job" : "jobs"} for the next run`],
  [/^Duty Officer brief: (\d+) delegation\(s\), (\d+) deferred$/, (m) => `Duty Officer handed out ${jobs(m[1])} and left ${m[2]} for the next run`],
  [/^Duty Officer AI UNAVAILABLE \(budget_exhausted\); (\d+) delegation\(s\) made, (\d+) mandatory item\(s\) to the Desk$/,
    (m) => `Duty Officer did not run: AI paused (daily quota). ${m[1] !== "0" ? `It handed out ${jobs(m[1])}; ` : ""}${jobs(m[2])} that must be done went to the Desk`],
  [/^Duty Officer AI UNAVAILABLE \(GEMINI DAILY QUOTA SPENT.*?\); (\d+) delegation\(s\) made, (\d+) mandatory item\(s\) to the Desk$/,
    (m) => `Duty Officer did not run: AI paused (daily quota). ${m[1] !== "0" ? `It handed out ${jobs(m[1])}; ` : ""}${jobs(m[2])} that must be done went to the Desk`],
  [/^Plume read: (.+?) \((.+)\): not dispatched; the area stays at the official products$/,
    (m) => `Plume read for ${m[1]} was not handed out (${m[2]}). TEPHRA's area stays at the official reports`],
  [/^Duty Officer left (\d+) mandatory item\(s\) undone: to the Desk$/, (m) => `Duty Officer passed ${m[1]} must-do ${Number(m[1]) === 1 ? "job" : "jobs"} to the Desk`],
  [/^(RFA\d+) \([^)]*\) is inside the (.+) cone at (FL\d{3})$/, (m) => `${m[1]} is inside TEPHRA's area at ${m[2]}, ${m[3]}`],
  [/^(RFA\d+) \([^)]*\) enters the (.+) cone in (\d+) min at (FL\d{3}) if track and level are held$/, (m) => `${m[1]} enters TEPHRA's area at ${m[2]} in ${m[3]} min, at ${m[4]}, if track and level are held`],
  [/^(RFA\d+): draft superseded \(no longer exposed if track and level are held\)$/, (m) => `${m[1]}: draft withdrawn, no longer heading into the area if track and level are held`],
  [/^(.+): (OFFICIAL|WIDENED|HYPOTHESIS) (\d+)% (\S+); (\d+) flight\(s\) exposed$/, (m) => `${m[1]}: TEPHRA's estimate is ${m[2] === "OFFICIAL" ? "the official area" : m[2] === "WIDENED" ? "wider than the official area" : "a hypothesis"}, ${m[4]}, confidence ${m[3]}%; ${m[5]} flight${m[5] === "1" ? "" : "s"} inside or heading in`],
  [/^(RFA\d+): DRAFT (\w+(?: LEVEL)?) for a dispatcher$/, (m) => `${m[1]}: advisory drafted to ${actionPlain(m[2]) || m[2].toLowerCase()}, for a dispatcher`],
  [/^(RFA\d+): same advice as an open draft$/, (m) => `${m[1]}: same advice as an open draft, so no new one`],
  [/^disruption: \{/, () => "Recovery planner was given the closed airports and the day's flights"],
  [/^run_scenario: \{.*"label":"([^"]+)".*?"status":"([A-Z_]+)"/, (m) => `Recovery planner tried a scenario: ${m[1].toLowerCase()} (${m[2].toLowerCase().replace(/_/g, " ")})`],
  [/^(.+): (LAG|ENVELOPE|HEIGHT_MISMATCH|DIRECTION_MISMATCH|SILENCE|CONFLICT) - /, (m) => `${m[1]}: ${DIFF_WORDS[m[2]]}`],
  [/^AI UNAVAILABLE: RECOVERY AGENT ERROR: TimeoutError\b/, () => "Recovery planner did not run: AI unavailable (timed out). No plan was made; a dispatcher must plan the network."],
  [/^AI UNAVAILABLE: RECOVERY AGENT ERROR: (\w+)/, (m) => `Recovery planner did not run: AI unavailable (the AI stopped with an error, ${m[1]}). No plan was made; a dispatcher must plan the network.`],
  // Any other code-template line: say who wrote it in words, keep the rest as written.
  [/^NO MODEL: (.+)$/, (m) => `Written by code (AI off): ${/[a-z]/.test(m[1]) ? m[1] : m[1].charAt(0) + m[1].slice(1).toLowerCase()}`],
  [/^AI UNAVAILABLE: NO FEASIBLE PLAN FOR THE PUBLISHED CLOSURE \((\w+)\).*$/, (m) => (m[1] === "UNKNOWN" ? "Airport plan: no plan found (the solver did not finish in time). A dispatcher must plan the network by hand." : `Airport plan: no plan found (solver: ${m[1]}). A dispatcher must plan the network by hand.`)],
];

export function plainLine(text) {
  const raw = String(text ?? "");
  for (const [re, fn] of PLAIN) {
    const m = re.exec(raw);
    const out = m ? fn(m) : null;
    if (out) return out;
  }
  return raw;
}

// ------------------------------------------------------------------ one failure in a few words
// One occurrence of a failed AI step in a few words, for the occurrence lines under a cause
// (docs/UI-DETAILS-PANELS.md 3.3): a fixed table, like PLAIN. `num` is the number of jobs it left,
// for "1–18 must-do jobs per run". A line the table does not know keeps its own plain line; the
// raw line stays under Technical detail.
const CAUSES = [
  { stage: "DUTY", re: /^Duty Officer AI UNAVAILABLE \((?:budget_exhausted|GEMINI DAILY QUOTA SPENT[^;]*)\); \d+ delegation\(s\) made, (\d+) mandatory/, each: (m) => `${jobs(m[1])} to the Desk` },
  { stage: "DUTY", re: /^Plume read: (.+?) \((.+)\): not dispatched/, each: (m) => `${m[1]}: ${m[2]}` },
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
  return { each: plain === msg && /AI UNAVAILABLE/i.test(msg) ? "could not answer" : plain, num: null };
}

// Who did a step, in words (stage chips: CODE / ADK / NO MODEL).
export const ACTOR_WORDS = { code: "by code", gemini: "by an AI helper", adk: "by an AI helper", stub: "AI off", human: "by a person", system: "by the system" };
// Agent-framework ("adk") steps code writes before any model is called: the Duty Officer's work
// list. They say "by code (agent worklist)"; "by an AI helper" is kept for steps a model took
// (docs/UI-AI-QUIET.md D63).
const ADK_CODE = [/^Duty Officer: \d+ item\(s\) to dispatch\b/, /^Duty Officer: the same work as on the first pass\b/];
// With AI off (the stub backend) the agent framework still runs, but no model speaks: an "adk"
// or "gemini" step is then code following the helper's script, so it says "AI off" (review 1, 6).
export const actorWords = (actor, stub, message = "") => {
  if (stub && (actor === "adk" || actor === "gemini")) return "AI off";
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

// A recovery plan that found no plan: the solver's status in plain words, never "AI unavailable"
// (R2.6). Returns null when the plan's failure is not a solver result.
export function planProblem(plan) {
  if (!plan) return null;
  const raw = planReasons(plan).join("; ");
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
// story's closure sub-line ("No airport plan (AI unavailable): plan the network by hand"); `ai`
// whether the AI (not the solver) is why there is no plan.
export function planFailure(plan) {
  if (!plan || plan.status !== "AI_UNAVAILABLE") return null;
  const p = planProblem(plan);
  const raw = planReasons(plan).join("; ") || "no reason given";
  if (p) {
    const solver = p.status.toLowerCase().replace(/_/g, " ");
    return {
      title: p.status === "UNKNOWN" ? "Recovery found no plan: the solver did not finish in time" : p.status === "INFEASIBLE" ? "Recovery found no plan: no plan fits the closures" : `Recovery found no plan (solver: ${solver})`,
      sub: "A dispatcher must plan the network by hand.", short: "no plan: plan the network by hand", raw, ai: false,
      place: `No airport plan (${p.status === "UNKNOWN" ? "the solver did not finish in time" : p.status === "INFEASIBLE" ? "no plan fits the closures" : `solver: ${solver}`}): plan the network by hand`,
    };
  }
  const m = /RECOVERY AGENT ERROR: (\w+)/.exec(raw);
  const base = { short: "no plan: plan the network by hand", raw, ai: true, why: WHY[reasonClass(raw)], place: "No airport plan (AI unavailable): plan the network by hand" };
  if (m && m[1] === "TimeoutError") return { ...base, title: "Recovery planner timed out", sub: "No plan was made. A dispatcher must plan the network by hand." };
  if (m) return { ...base, title: "Recovery planner stopped with an error", sub: "No plan was made. A dispatcher must plan the network by hand." };
  return { ...base, title: "No plan: AI unavailable", sub: "Nothing was put in its place. A dispatcher must plan the network by hand." };
}

// "Technical detail" disclosure holding raw machine text (R12.7).
export function techDetail(...lines) {
  const kept = lines.flat().filter((l) => l != null && l !== "");
  if (!kept.length) return null;
  return el("details", { class: "tech" }, el("summary", { text: "Technical detail" }), ...kept.map((l) => (l instanceof Node ? l : el("p", { class: "tech__line mono", text: String(l) }))));
}
