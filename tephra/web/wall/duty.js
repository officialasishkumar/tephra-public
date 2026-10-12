// The Wall's Duty Officer panel (the coordinator agent, tephra/agents/duty_officer.py): its latest
// brief, the work it delegated to the specialist agents, and what it left undone. Data is the
// newest DutyRun (snapshot.duty, SSE "duty"). Rule 0 (no fallbacks): when the model failed the
// panel says so and shows the undispatched work; it never invents a brief. Text the model wrote
// (summary, reasons, watch items, deferral reasons) is marked AI-written with the model id; labels,
// counts, timings and result lines are written by code and stay plain. Every string goes in
// through el() (textContent).

import { el, icon, ms, hhmmz, dayMon } from "./util.js";
import { st, aiMark, pill, section, plainLine } from "./x-parts.js";

// What each Duty Officer tool reaches. Tool names are fixed by the backend toolkit.
export const SPECIALISTS = {
  assess_volcanoes: { name: "Satellite + Plume Reader", does: "reads the plume, rebuilds the cone", unit: "volcano" },
  plan_flights: { name: "Planner + Drafter", does: "plans and drafts per flight", unit: "flight" },
  run_recovery: { name: "Recovery", does: "re-plans the RFA network", unit: "network" },
  draft_sra: { name: "SRA drafter", does: "drafts the safety risk assessment", unit: "region" },
};

const OUTCOME = {
  ACCEPTED: ["ok", "ACCEPTED", "The brief passed the code's checks."],
  REPAIRED: ["caution", "REPAIRED", "The brief passed after one repair."],
  STUB: ["off", "AI off", "The offline stub ran the work in urgency order. No model wrote the brief."],
  MODEL_FAILED: ["serious", "AI unavailable", "The model gave no brief that passed the code's checks."],
};

const PRIO_SHOWN = 5;
const RESULTS_SHOWN = 2;
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

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

function head(run) {
  const [kind, word, why] = OUTCOME[run.outcome] || ["info", run.outcome, ""];
  const finished = ms(run.finished_at);
  return el("header", { class: "x-card__head" },
    el("h3", { class: "x-card__title", text: "Duty Officer" }),
    pill(kind, word, why),
    run.replay ? el("span", { class: "tag tag--replay", text: "recorded" }) : null,
    el("span", { class: "x-card__time mono", text: Number.isFinite(finished) ? `${dayMon(finished)} ${hhmmz(finished)}` : "" }));
}

function facts(run) {
  const mandatory = run.worklist.filter((i) => i.mandatory).length;
  const model = dutyModel(run);
  return el("dl", { class: "duty__facts" },
    el("div", {}, el("dt", { text: "Model" }), el("dd", { class: "mono", text: model || "AI off" })),
    el("div", {}, el("dt", { text: "Turns" }), el("dd", { class: "mono", text: String(run.turns) })),
    el("div", {}, el("dt", { text: "Jobs given" }), el("dd", { class: "mono", text: `${run.worklist.length}${mandatory ? ` (${mandatory} must do)` : ""}` })),
    el("div", {}, el("dt", { text: "Run by" }), el("dd", { text: run.trigger === "adsb" ? "new aircraft" : "scheduler tick" })));
}

function failure(run) {
  const reason = run.validation_errors[0] || "no reason recorded";
  return el("div", { class: "x-fail", role: "status" }, st("st-serious", "var(--c-serious)"),
    el("p", {}, el("strong", { text: "Duty Officer AI unavailable: " }), reason,
      el("span", { class: "x-fail__note", text: " No brief was made up in its place. The work below was not coordinated." })));
}

function brief(run) {
  const b = run.brief;
  if (!b) return el("p", { class: "x-quiet", text: "The run ended without a brief." });
  const model = dutyModel(run);
  const kids = [
    el("div", { class: "duty__briefhead" }, el("h4", { class: "caps x-h", text: "Brief" }), aiMark(model, model ? null : "NO MODEL")),
    el("p", { class: "duty__summary duty__ai", text: plainLine(b.summary) }),
  ];
  if (b.priorities.length) {
    // The stub gives every item the same reason: say it once under the heading, not per row.
    const sameStub = b.priorities.every((p) => /^NO MODEL: urgency order\.?$/.test(p.why || ""));
    const row = (p) => {
      const item = run.worklist.find((i) => i.id === p.item_id);
      return el("li", {},
        el("span", { class: "duty__label" }, item?.mandatory ? el("span", { class: "duty__must", title: "Code requires this work this run", text: "Must do" }) : null, itemLabel(run, p.item_id)),
        sameStub ? null : el("span", { class: "duty__why duty__ai", text: plainLine(p.why) }));
    };
    kids.push(el("h4", { class: "caps x-h", text: "Priorities" }),
      sameStub ? el("p", { class: "x-sub", text: "In urgency order: code ordered them (AI off)." }) : null,
      el("ol", { class: "duty__prio" }, ...b.priorities.slice(0, PRIO_SHOWN).map(row)));
    const rest = b.priorities.slice(PRIO_SHOWN);
    if (rest.length) {
      kids.push(el("details", { class: "duty__more" }, el("summary", { text: `${rest.length} more in order` }),
        el("ol", { class: "duty__prio", start: String(PRIO_SHOWN + 1) }, ...rest.map(row))));
    }
  }
  if (b.watch.length) {
    kids.push(el("h4", { class: "caps x-h", text: "Watch" }),
      el("ul", { class: "duty__watch" }, ...b.watch.map((w) => el("li", { class: "duty__ai", text: plainLine(w) }))));
  }
  return el("div", { class: "duty__brief" }, ...kids);
}

// Failed results always show; the first two good ones show, the rest sit behind a disclosure.
function resultLines(results) {
  const line = (r) => el("p", { class: `dg__result${r.ok ? "" : " dg__result--bad"}`, text: r.text });
  const bad = results.filter((r) => !r.ok);
  const good = results.filter((r) => r.ok);
  const out = [...bad.map(line), ...good.slice(0, RESULTS_SHOWN).map(line)];
  const rest = good.slice(RESULTS_SHOWN);
  if (rest.length) out.push(el("details", { class: "dg__resmore" }, el("summary", { text: `${rest.length} more result${rest.length === 1 ? "" : "s"}` }), ...rest.map(line)));
  return out;
}

// The Duty Officer at the top, an arrow to each specialist it called this run.
function diagram(run) {
  const groups = groupDispatches(run);
  const model = dutyModel(run);
  const root = el("div", { class: "dg__root" },
    icon("i-agent", "icon dg__icon"),
    el("span", { class: "dg__rootmain" }, el("strong", { text: "Duty Officer" }),
      el("span", { class: "dg__sub mono", text: `${model || "AI off"} · ${plural(run.worklist.length, "job")} offered` })));
  if (!groups.length) {
    return el("div", { class: "dg", role: "group", "aria-label": "Delegation diagram" }, root,
      el("p", { class: "dg__none", text: "It delegated nothing this run." }));
  }
  const nodes = groups.map((g) => {
    const spec = SPECIALISTS[g.tool];
    const bad = g.failed > 0;
    const items = g.itemIds.size;
    const count = spec ? `${items} ${spec.unit}${items === 1 ? "" : "s"}` : plural(items, "item");
    return el("li", { class: `dg__node${bad ? " dg__node--bad" : ""}` }, el("div", { class: "dg__card" },
      el("div", { class: "dg__top" },
        el("strong", { class: "dg__name", text: spec ? spec.name : g.tool }),
        pill(bad ? "serious" : "ok", bad ? (g.failed === g.calls ? "failed" : `${g.failed} of ${g.calls} failed`) : "ok", bad ? "The specialist reported a failure" : "The specialist returned")),
      el("p", { class: "dg__stats mono" },
        el("span", { text: count }), g.calls > 1 ? el("span", { text: `${g.calls} calls` }) : null, el("span", { text: `${g.ms.toLocaleString("en")} ms` })),
      el("p", { class: "dg__tool mono", text: `${g.tool}()${spec ? ` · ${spec.does}` : ""}` }),
      ...resultLines(g.results)));
  });
  return el("div", { class: "dg", role: "group", "aria-label": "Delegation diagram: the specialists the Duty Officer called this run" }, root,
    el("ul", { class: "dg__list" }, ...nodes));
}

function deferred(run) {
  if (!run.deferred.length) return null;
  const model = dutyModel(run);
  return section(`Deferred · ${run.deferred.length}`,
    el("p", { class: "x-sub", text: "Optional work it left for the next run. The reasons are the model's." }),
    el("ul", { class: "duty__defer" }, ...run.deferred.map((d) => el("li", {},
      el("span", { class: "duty__label", text: itemLabel(run, d.item_id) }),
      el("span", { class: "duty__why duty__ai", text: plainLine(d.reason) })))),
    aiMark(model, model ? null : "NO MODEL"));
}

function undispatched(run) {
  if (!run.undispatched.length) return null;
  return el("section", { class: "duty__undone", role: "alert", "aria-label": "Mandatory work not dispatched" },
    el("h3", { class: "duty__undonehead" }, st("st-serious", "var(--c-serious)"), `${plural(run.undispatched.length, "mandatory item")} not dispatched: sent to the Desk`),
    el("ul", {}, ...run.undispatched.map((id) => el("li", { text: itemLabel(run, id) }))),
    el("p", { class: "x-sub", text: "A dispatcher handles these by hand. Nothing was substituted." }));
}

export function dutyPanel(run, loaded) {
  const lede = el("p", { class: "x-lede", text: "One coordinator agent orders the day's AI work and hands it to the specialists through tools. Code builds the work list and holds the safety line; the Duty Officer decides the order and writes the brief." });
  if (!run) {
    return [section("Duty Officer", lede,
      el("div", { class: "x-empty" }, el("strong", { text: loaded ? "No Duty Officer run yet" : "Waiting for the first run" }),
        el("p", { text: "It runs when code finds AI work due: a plume to read, a flight to plan, a network to re-plan." })))];
  }
  const card = el("article", { class: `x-card duty duty--${run.outcome.toLowerCase()}`, "aria-label": "Duty Officer" }, head(run), facts(run));
  if (run.outcome === "MODEL_FAILED") card.append(failure(run));
  const undone = undispatched(run);
  if (undone) card.append(undone);
  card.append(el("h4", { class: "caps x-h", text: "Delegation" }), diagram(run));
  if (run.outcome !== "MODEL_FAILED") card.append(brief(run));
  const defer = deferred(run);
  if (defer) card.append(defer);
  return [lede, card];
}
