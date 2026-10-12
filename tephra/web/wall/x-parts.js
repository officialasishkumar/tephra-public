// Small building blocks shared by the Wall's rail panels (ext.js, duty.js). Every string goes in
// through el() (textContent); AI-written text carries an "AI-written" mark with the model id.

import { el, icon } from "./util.js";

export const st = (id, color) => icon(id, "st", color);

// Marks AI-written text with the model id; with no model it says code wrote it (AI off).
export function aiMark(modelId, label) {
  const no = label === "NO MODEL" || !modelId || modelId === "stub";
  return el("span", { class: `ai-mark${no ? " ai-mark--none" : ""}`, title: no ? "No model wrote this: a code template (the offline stub, NO MODEL)" : "Written by a model. Code checked every number, time and id." },
    icon(no ? "i-code" : "i-model"), el("span", { text: no ? "Written by code (AI off)" : `AI-written · ${modelId}` }));
}

export function pill(kind, text, title) {
  const ic = { ok: "st-ok", caution: "st-caution", serious: "st-serious", info: "st-info", off: "st-off" }[kind] || "st-info";
  const col = { ok: "var(--c-ok)", caution: "var(--c-caution)", serious: "var(--c-serious)", info: "var(--c-info)", off: "var(--c-off)" }[kind];
  return el("span", { class: `pill pill--${kind}`, title }, st(ic, col), el("span", { text }));
}

export const section = (title, ...kids) => el("section", { class: "x-sec" }, el("h3", { class: "caps x-sec__title", text: title }), ...kids);

// ------------------------------------------------------------------ plain words (UI-REDESIGN R12.7)
// Code-written trace and AI lines in plain words. A fixed table of patterns: a line that matches
// none is shown verbatim and never paraphrased, and the raw line always stays reachable under
// "Technical detail". Shared with the Desk.

const HELPER = {
  assess_volcanoes: "the Satellite and Plume helpers", plan_flights: "the Planner and Drafter",
  run_recovery: "the Recovery helper", draft_sra: "the SRA drafter",
};
const jobs = (n) => `${n} job${Number(n) === 1 ? "" : "s"}`;
// An action word in plain words with the ICAO word kept in brackets (R12.10).
export function actionPlain(text) {
  const t = String(text || "").trim();
  let m;
  if (/^MONITOR$/.test(t)) return "keep watching (MONITOR)";
  if (/^CONTINUE$/.test(t)) return "continue (CONTINUE)";
  if ((m = /^HOLD(?: (FL\d{3}))?$/.exec(t))) return m[1] ? `hold at ${m[1]} (HOLD)` : "hold (HOLD)";
  if ((m = /^DIVERT(?: ([A-Z]{4}))?$/.exec(t))) return m[1] ? `divert to ${m[1]} (DIVERT)` : "divert (DIVERT)";
  if ((m = /^CHANGE[ _]LEVEL(?: (.+))?$/.exec(t))) return m[1] ? `change level to ${m[1]} (CHANGE LEVEL)` : "change level (CHANGE LEVEL)";
  if (/^REROUTE\b/.test(t)) return "reroute around the ash (REROUTE)";
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
  [/^(RFA\d+): DRAFT (\w+(?: LEVEL)?) waiting for a dispatcher$/, (m) => `${m[1]}: advisory drafted (${m[2]}), waiting for a dispatcher`],
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
  [/^get_flight: \{"proxy_flight":"(RFA\d+)"/, (m) => `Planner looked up ${m[1]}'s position and track`],
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
  [/^Duty Officer left (\d+) mandatory item\(s\) undone: to the Desk$/, (m) => `Duty Officer passed ${m[1]} must-do ${Number(m[1]) === 1 ? "job" : "jobs"} to the Desk`],
  [/^(RFA\d+) \([^)]*\) is inside the (.+) cone at (FL\d{3})$/, (m) => `${m[1]} is inside TEPHRA's area at ${m[2]}, ${m[3]}`],
  [/^(RFA\d+) \([^)]*\) enters the (.+) cone in (\d+) min at (FL\d{3}) if track and level are held$/, (m) => `${m[1]} enters TEPHRA's area at ${m[2]} in ${m[3]} min, at ${m[4]}, if track and level are held`],
  [/^(RFA\d+): draft superseded \(no longer exposed if track and level are held\)$/, (m) => `${m[1]}: draft withdrawn, no longer heading into the area if track and level are held`],
  [/^(.+): (OFFICIAL|WIDENED|HYPOTHESIS) (\d+)% (\S+); (\d+) flight\(s\) exposed$/, (m) => `${m[1]}: TEPHRA's estimate is ${m[2] === "OFFICIAL" ? "the official area" : m[2] === "WIDENED" ? "wider than the official area" : "a hypothesis"}, ${m[4]}, confidence ${m[3]}%; ${m[5]} flight${m[5] === "1" ? "" : "s"} inside or heading in`],
  [/^(RFA\d+): DRAFT (\w+(?: LEVEL)?) for a dispatcher$/, (m) => `${m[1]}: advisory drafted (${actionPlain(m[2]) || m[2].toLowerCase()}) for a dispatcher`],
  [/^(RFA\d+): same advice as an open draft$/, (m) => `${m[1]}: same advice as an open draft, so no new one`],
  [/^disruption: \{/, () => "Recovery planner was given the closed airports and the day's flights"],
  [/^run_scenario: \{.*"label":"([^"]+)".*?"status":"([A-Z_]+)"/, (m) => `Recovery planner tried a scenario: ${m[1].toLowerCase()} (${m[2].toLowerCase().replace(/_/g, " ")})`],
  [/^(.+): (LAG|ENVELOPE|HEIGHT_MISMATCH|DIRECTION_MISMATCH|SILENCE|CONFLICT) - /, (m) => `${m[1]}: ${DIFF_WORDS[m[2]]}`],
  [/^AI UNAVAILABLE: RECOVERY AGENT ERROR: TimeoutError\b/, () => "Recovery planner timed out. No plan was made; a dispatcher must plan the network."],
  [/^AI UNAVAILABLE: RECOVERY AGENT ERROR: (\w+)/, (m) => `Recovery planner stopped with an error (${m[1]}). No plan was made; a dispatcher must plan the network.`],
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

// ------------------------------------------------------------------ failures grouped by cause
// A failed AI step's cause in plain words (docs/UI-DETAILS-PANELS.md 3.3): a fixed table, like
// PLAIN. `title` names what failed, `sub` what it means for the dispatcher, `each` one
// occurrence in a few words. A line the table does not know keeps the helper's name and its own
// plain line; nothing is paraphrased beyond the table. The raw line stays under Technical detail.
const HELPER_OF_STAGE = {
  DUTY: "Duty Officer", PLUME: "Plume Reader", SATELLITE: "Satellite reader", PLANNER: "Planner", DRAFTER: "Drafter",
  ASK: "Ask", NOTICE: "Notice reader", RECOVERY: "Recovery planner", MESSAGES: "Messages", DOCS: "Paperwork drafter",
};
const CAUSES = [
  { stage: "DUTY", re: /^Duty Officer left (\d+) mandatory item\(s\) undone: to the Desk$/, key: "duty-undone",
    title: (n) => `Duty Officer passed ${n} must-do jobs to the Desk`, sub: "A dispatcher does them by hand. Nothing was substituted.",
    each: (m) => `${m[1]} jobs`, link: null },
  { stage: "RECOVERY", re: /RECOVERY AGENT ERROR: TimeoutError/, key: "recovery-timeout",
    title: () => "Recovery planner timed out", sub: "No plan was made. A dispatcher must plan the network.", each: () => "timed out", link: ["Airport closures", "recovery"] },
  { stage: "RECOVERY", re: /RECOVERY AGENT ERROR: (\w+)/, key: "recovery-error",
    title: () => "Recovery planner stopped with an error", sub: "No plan was made. A dispatcher must plan the network.", each: (m) => m[1], link: ["Airport closures", "recovery"] },
  { stage: "RECOVERY", re: /NO FEASIBLE PLAN[^(]*\(UNKNOWN\)/, key: "recovery-unknown",
    title: () => "Recovery found no plan: the solver did not finish in time", sub: "A dispatcher must plan the network by hand.", each: () => "no plan", link: ["Airport closures", "recovery"] },
  { stage: "RECOVERY", re: /NO FEASIBLE PLAN[^(]*\((\w+)\)/, key: "recovery-noplan",
    title: () => "Recovery found no plan", sub: "A dispatcher must plan the network by hand.", each: (m) => `solver: ${m[1].toLowerCase()}`, link: ["Airport closures", "recovery"] },
  { stage: "DRAFTER", re: /DRAFT FAILED CHECKS/, key: "drafter-checks",
    title: () => "Drafter's advisory failed the code's checks", sub: "No advisory was drafted for that flight. A dispatcher must write it.", each: () => "failed the checks", link: ["Decisions", "decisions"] },
];

export function failureCause(t) {
  const msg = String(t.message || "");
  for (const c of CAUSES) {
    if (c.stage !== t.stage) continue;
    const m = c.re.exec(msg);
    if (m) return { key: c.key, title: c.title, sub: c.sub, each: c.each(m), num: m[1] && /^\d+$/.test(m[1]) ? Number(m[1]) : null, link: c.link };
  }
  const who = HELPER_OF_STAGE[t.stage] || t.stage;
  if (/AI UNAVAILABLE/i.test(msg)) return { key: `${t.stage}-unavailable`, title: () => `${who} could not answer`, sub: "Nothing was put in its place.", each: plainLine(msg) === msg ? "could not answer" : plainLine(msg), num: null, link: null };
  const plain = plainLine(msg);
  return { key: `${t.stage}-other-${plain}`, title: () => `${who} reported a failure`, sub: plain !== msg ? plain : null, each: plain, num: null, link: null };
}

// Who did a step, in words (stage chips: CODE / ADK / NO MODEL).
export const ACTOR_WORDS = { code: "by code", gemini: "by an AI helper", adk: "by an AI helper", stub: "AI off", human: "by a person", system: "by the system" };
// With AI off (the stub backend) the agent framework still runs, but no model speaks: an "adk"
// or "gemini" step is then code following the helper's script, so it says "AI off" (review 1, 6).
export const actorWords = (actor, stub) => (stub && (actor === "adk" || actor === "gemini") ? "AI off" : ACTOR_WORDS[actor] || String(actor || ""));

// "$62,525" (R2.8)
const USD = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
export const usd = (n) => (n == null || !Number.isFinite(Number(n)) ? "n/a" : USD.format(Number(n)));

// A recovery plan that found no plan: the solver's status in plain words, never "AI unavailable"
// (R2.6). Returns null when the plan's failure is not a solver result.
export function planProblem(plan) {
  if (!plan) return null;
  const raw = [plan.unavailable_reason, ...(plan.validation_errors || [])].filter(Boolean).join("; ");
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

// "Technical detail" disclosure holding raw machine text (R12.7).
export function techDetail(...lines) {
  const kept = lines.flat().filter((l) => l != null && l !== "");
  if (!kept.length) return null;
  return el("details", { class: "tech" }, el("summary", { text: "Technical detail" }), ...kept.map((l) => (l instanceof Node ? l : el("p", { class: "tech__line mono", text: String(l) }))));
}
