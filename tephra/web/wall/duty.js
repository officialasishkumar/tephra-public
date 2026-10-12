// The Duty Officer's latest run (the coordinator agent, tephra/agents/duty_officer.py), shown
// inside Details › AI helpers as the body of its helper row: how the run ended, what it handed
// to each specialist, what it passed to the Desk, its brief and what it left for later. Data is
// the newest DutyRun (snapshot.duty, SSE "duty"). Rule 0 (no fallbacks): when the model failed
// the row says so and shows the work it did not coordinate; it never invents a brief. Text the
// model wrote (summary, reasons, watch items, deferral reasons) carries an AI-written mark with
// the model id; labels, counts, timings and result lines are written by code. Every string goes
// in through el() (textContent).

import { el, ms } from "./util.js";
import { aiMark, plainLine } from "./x-parts.js";
import { dkPill, dkChip, dkFacts, dkRow, dkList, dkNote, dkEmpty, dkTech, dkRecorded, collapseRuns, seconds, plural, dayTime } from "./dk.js";

// What each Duty Officer tool reaches. Tool names are fixed by the backend toolkit.
export const SPECIALISTS = {
  assess_volcanoes: { name: "Satellite reader and Plume Reader", does: "reads the plume, rebuilds the area", unit: "volcano" },
  plan_flights: { name: "Planner and Drafter", does: "plans and drafts per flight", unit: "flight" },
  run_recovery: { name: "Recovery planner", does: "re-plans the RFA network", unit: "network" },
  draft_sra: { name: "Safety risk assessment drafter", does: "drafts the safety risk assessment", unit: "region" },
};

// How the run ended, in words (no machine caps in the main view).
export const OUTCOME = {
  ACCEPTED: ["ok", "Passed the checks", "The brief passed the code's checks."],
  REPAIRED: ["caution", "Passed after one repair", "The brief passed after one repair."],
  STUB: ["off", "AI off", "The offline stub ran the work in urgency order. No model wrote the brief."],
  MODEL_FAILED: ["serious", "Failed", "The model gave no brief that passed the code's checks."],
};

export const dutyModel = (run) => (run.outcome === "STUB" || run.llm_backend === "stub" ? null : run.model_id);

// Tools the run called, in the order it first called them.
export function dispatchedTools(run) {
  return new Set((run?.dispatches || []).map((d) => d.tool));
}

// One row per tool: the same tool called twice shows once, with its calls added up.
export function groupDispatches(run) {
  const byTool = new Map();
  for (const d of run.dispatches || []) {
    const g = byTool.get(d.tool) || { tool: d.tool, itemIds: new Set(), calls: 0, failed: 0, ms: 0, results: [] };
    d.item_ids.forEach((id) => g.itemIds.add(id));
    g.calls += 1;
    g.failed += d.ok ? 0 : 1;
    g.ms += d.ms;
    g.results.push({ ok: d.ok, text: d.result });
    byTool.set(d.tool, g);
  }
  return [...byTool.values()];
}

const itemLabel = (run, id) => run.worklist.find((i) => i.id === id)?.label || id;
const finishedAt = (run) => ms(run.finished_at);

// Lines that repeat with other flights collapse into one ("RFA1225, RFA1530 and 19 more: ...").
function collapsedLines(lines, key, first, tone = null) {
  const runs = collapseRuns(lines.map((text, i) => ({ text, _t: i })), { textOf: (x) => x.text, timeOf: () => NaN });
  return dkList(runs.map((r) => el("div", { class: `dk-line${tone ? ` dk-line--${tone}` : ""}` },
    el("span", { class: "dk-line__text", text: r.label }), r.count > 1 ? el("span", { class: "dk-badge", text: `${r.count}` }) : null)), { first, key });
}

// The run in one line for the helper row: "Passed the checks · 1 job handed out · 1036Z".
export function dutySummary(run) {
  if (!run) return null;
  const [, word] = OUTCOME[run.outcome] || ["info", run.outcome];
  const n = (run.dispatches || []).length;
  return `${word} · ${plural(n, "job")} handed out`;
}

function handedTo(run) {
  const groups = groupDispatches(run);
  if (!groups.length) return dkEmpty("It handed nothing out this run", null);
  const rows = groups.map((g) => {
    const spec = SPECIALISTS[g.tool];
    const bad = g.failed > 0;
    const items = g.itemIds.size;
    const count = spec ? plural(items, spec.unit) : plural(items, "item");
    const bad_ = g.results.filter((r) => !r.ok);
    const good = g.results.filter((r) => r.ok);
    return dkRow({
      key: `duty-tool-${g.tool}`,
      dot: bad ? "serious" : "ok",
      edge: bad ? "serious" : null,
      title: spec ? spec.name : g.tool,
      sub: [count, g.calls > 1 ? `${g.calls} calls` : null, seconds(g.ms)].filter(Boolean).join(" · "),
      meta: bad ? (g.failed === g.calls ? "failed" : `${g.failed} of ${g.calls} failed`) : "returned",
      body: [
        bad_.length ? collapsedLines(bad_.map((r) => plainLine(r.text)), `duty-bad-${g.tool}`, 3, "serious") : null,
        good.length ? collapsedLines(good.map((r) => plainLine(r.text)), `duty-good-${g.tool}`, 3) : null,
        dkTech(`${g.tool}()${spec ? ` · ${spec.does}` : ""} · ${g.ms.toLocaleString("en")} ms in all`, ...g.results.map((r) => `${r.ok ? "ok" : "failed"} · ${r.text}`)),
      ],
    });
  });
  return el("div", { class: "dk-sub", role: "group", "aria-label": "Delegation diagram: the specialists the Duty Officer called this run" },
    el("p", { class: "dk-sub__title", text: "Handed to" }), dkList(rows, { first: 4, key: "duty-tools" }));
}

function undispatched(run) {
  if (!run.undispatched.length) return null;
  return el("div", { class: "dk-sub", role: "group", "aria-label": "Mandatory work not dispatched" },
    el("p", { class: "dk-sub__title", text: `Passed to the Desk · ${plural(run.undispatched.length, "must-do job")}` }),
    collapsedLines(run.undispatched.map((id) => itemLabel(run, id)), "duty-undone", 3, "serious"),
    el("p", { class: "dk-sub__note", text: "A dispatcher handles these by hand. Nothing was substituted." }));
}

function brief(run) {
  const b = run.brief;
  if (!b) return dkNote("info", "The run ended without a brief.");
  const model = dutyModel(run);
  const mustDo = (id) => run.worklist.find((i) => i.id === id)?.mandatory;
  // The stub gives every item the same reason: say it once, not per row.
  const sameStub = b.priorities.every((p) => /^NO MODEL: urgency order\.?$/.test(p.why || ""));
  const prio = b.priorities.map((p, i) => el("div", { class: "dk-prio" },
    el("span", { class: "dk-prio__n mono", text: String(i + 1) }),
    el("span", { class: "dk-prio__main" },
      el("span", { class: "dk-prio__label" }, itemLabel(run, p.item_id), mustDo(p.item_id) ? [" ", dkChip("Must do", { kind: "must", title: "Code requires this work this run" })] : null),
      sameStub ? null : el("span", { class: "dk-prio__why", text: plainLine(p.why) }))));
  return el("div", { class: "dk-sub" },
    el("div", { class: "dk-sub__titlerow" }, el("p", { class: "dk-sub__title", text: "Brief" }), aiMark(model, model ? null : "NO MODEL")),
    el("p", { class: "dk-quote", text: plainLine(b.summary) }),
    b.priorities.length ? el("p", { class: "dk-sub__title", text: `Priorities · ${b.priorities.length}` }) : null,
    sameStub && b.priorities.length ? el("p", { class: "dk-sub__note", text: "In urgency order: code ordered them (AI off)." }) : null,
    b.priorities.length ? dkList(prio, { first: 5, key: "duty-prio" }) : null,
    b.watch.length ? el("p", { class: "dk-sub__title", text: "Watch" }) : null,
    b.watch.length ? el("ul", { class: "dk-bullets" }, ...b.watch.map((w) => el("li", { text: plainLine(w) }))) : null);
}

function deferred(run) {
  if (!run.deferred.length) return null;
  const model = dutyModel(run);
  return el("div", { class: "dk-sub" },
    el("div", { class: "dk-sub__titlerow" }, el("p", { class: "dk-sub__title", text: `Left for the next run · ${run.deferred.length}` }), aiMark(model, model ? null : "NO MODEL")),
    el("p", { class: "dk-sub__note", text: "Optional work it left for later. The reasons are the model's." }),
    dkList(run.deferred.map((d) => el("div", { class: "dk-prio" }, el("span", { class: "dk-prio__main" },
      el("span", { class: "dk-prio__label", text: itemLabel(run, d.item_id) }), el("span", { class: "dk-prio__why", text: plainLine(d.reason) })))), { first: 3, key: "duty-defer" }));
}

// The body of the Duty Officer's helper row.
export function dutyDetail(run, loaded) {
  if (!run) {
    return [dkEmpty(loaded ? "No Duty Officer run yet" : "Waiting for the first run", "It runs when code finds AI work due: a plume to read, a flight to plan, a network to re-plan.")];
  }
  const [tone, word, why] = OUTCOME[run.outcome] || ["info", run.outcome, ""];
  const t = finishedAt(run);
  const mandatory = run.worklist.filter((i) => i.mandatory).length;
  const model = dutyModel(run);
  const kids = [
    el("div", { class: "dk-inline" }, dkPill(tone, word, why), dkRecorded(run.replay), el("span", { class: "dk-inline__meta mono", text: Number.isFinite(t) ? `finished ${dayTime(t)}` : "" })),
    dkFacts([
      ["Model", model ? dkChip(model, { mono: true }) : "AI off"],
      ["Turns", String(run.turns), { mono: true }],
      ["Jobs given", `${run.worklist.length}${mandatory ? ` (${mandatory} must do)` : ""}`],
      ["Run by", run.trigger === "adsb" ? "AI worker, after new aircraft" : "AI worker, after a scheduler tick"],
      // a replay loop reuses this model's own run for the same question; the label says so
      ["Answer", run.recorded_answer || null],
    ]),
  ];
  if (run.outcome === "MODEL_FAILED") {
    kids.push(dkNote("serious", ["The model gave no brief that passed the code's checks.", "No brief was made up in its place. The work below was not coordinated."], { role: "status" }),
      dkTech(run.validation_errors[0] || "no reason recorded"));
  }
  kids.push(undispatched(run), handedTo(run));
  if (run.outcome !== "MODEL_FAILED") kids.push(brief(run));
  kids.push(deferred(run));
  return kids.filter(Boolean);
}
