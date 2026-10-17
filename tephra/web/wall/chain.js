// The four-step reasoning chain behind one advisory draft (GET /api/advisories/{id}/chain):
// Coordinator, Plume reader, Flight planner, Drafter. Each step is one line and a "More"
// disclosure, so a reader sees what each skill decided before the words it used. Shared by the
// Wall (Details › Decisions › "Why ›", drawn in the flight host) and the Desk ("Why this advice").
// Every string goes in through el() (textContent). Model-written text (a reading, a rationale, the
// planner's reasoning, the Coordinator's why) sits under its step's mark; the one-line summaries
// hold code words only. Code never invents a value: every number, time and id is a field of the
// record, rendered by code.

import { $, el, icon, hhmmz, ms } from "./util.js";
import { actionWords } from "./derive.js";
import { aiMark, machineText, plainLine, plumeOutcome, templateText, MARK } from "./x-parts.js";
import { dkHeader, dkEmpty, dkSection } from "./dk.js";

// The skills in the order they ran, named once each (the step title).
export const SKILLS = ["Coordinator", "Plume reader", "Flight planner", "Drafter"];
// A step whose record the store does not hold.
export const NOT_ON_HAND = "not on hand";
// The sentence a reader needs about the Drafter, before the counts: what the code checked.
export const DRAFT_CHECKED = "Checked by code: action allowed · every number and place from the facts · no clock time";

const MODE_WORD = { OFFICIAL: "Same as official", WIDENED: "Wider than official", HYPOTHESIS: "Hypothesis" };
const flWord = (n) => `FL${String(n ?? 0).padStart(3, "0")}`;
const count = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
const isStub = (s) => s.outcome === "STUB" || s.model_id === "stub";
// A model's words stay as written; the stub's code-written stand-ins read in plain words, without
// "(code only)": the step's own mark (codeMark) says it once.
const words = (text, stub) => (stub ? templateText(plainLine(String(text).replace(/^NO MODEL:\s*/, ""))).text : String(text));

// The source's card title (code-written) for a source id; the id's first parts when the
// situation is not on hand (the Desk).
export const sourceName = (sit, sid) => sit?.cards?.find((c) => c.source_id === sid)?.title || String(sid || "").split(":").slice(0, 3).join(" ");
// The other side of the disagreement a reading settled: the discrepancy's other source id.
const otherSource = (sit, r) => {
  const d = sit?.discrepancies?.find((x) => x.id === r.discrepancy_id);
  return d ? Object.keys(d.values || {}).find((k) => k !== r.which_source_we_lean_on) || null : null;
};

// One step: the number, the skill, the line, its mark, then "More" and a footer of code facts.
function step(n, skill, key, { line, mark = null, more = [], foot = null }) {
  const body = more.flat().filter(Boolean);
  return el("li", { class: "chain__step", dataset: { step: key } },
    el("div", { class: "chain__head" },
      el("span", { class: "chain__n", "aria-hidden": "true", text: String(n) }),
      el("div", { class: "chain__main" },
        el("p", { class: "chain__title" }, el("b", { class: "chain__skill", text: skill }), mark),
        el("p", { class: "chain__line" }, ...(Array.isArray(line) ? line : [line])))),
    body.length ? el("details", { class: "dk-about chain__more", dataset: { k: `chain-${key}` } },
      el("summary", { dataset: { focus: `chain-${key}` } }, icon("i-chevron-right", "icon dk-about__chev"), el("span", { text: "More" })),
      el("div", { class: "dk-about__body" }, ...body)) : null,
    foot ? el("p", { class: "chain__foot", text: foot }) : null);
}
const sub = (title, node) => (node ? el("div", { class: "dk-sub" }, el("p", { class: "dk-sub__title", text: title }), node) : null);
const quote = (text, stub) => el("p", { class: "dk-quote", text: words(text, stub) });

// 1 · Coordinator: where this flight stood in the run's priorities, in the brief's own words.
function coordinatorStep(c) {
  if (!c) return step(1, SKILLS[0], "coordinator", { line: NOT_ON_HAND });
  const when = el("p", { class: "dk-sub__note", text: `Run decided at ${hhmmz(ms(c.decided_at))} · ${c.run_id}` });
  if (c.outcome === "MODEL_FAILED") return step(1, SKILLS[0], "coordinator", { line: "gave no result · its must-do flights went to the Desk", more: [when] });
  const stub = c.outcome === "STUB";
  const rank = c.rank != null ? `Planned ${c.rank} of ${c.of}` : c.of ? `Planned, not ranked among the ${c.of} priorities` : "Planned without a brief";
  return step(1, SKILLS[0], "coordinator", {
    line: [rank, c.why ? ` · ${words(c.why, stub)}` : null],
    mark: aiMark(stub ? "stub" : "Coordinator", null, MARK.chosen),
    more: [when],
  });
}

// 2 · Plume reader: the area it read and which source it leaned on, with each reading quoted
// under "More". On the Wall the rationale lives in Details › TEPHRA's estimate, linked, not repeated.
function plumeStep(p, sit, wall) {
  if (!p) return step(2, SKILLS[1], "plume", { line: NOT_ON_HAND });
  const area = `${MODE_WORD[p.mode] || p.mode} ${flWord(p.base_fl)}-${flWord(p.top_fl)}`;
  if (p.outcome === "MODEL_FAILED") {
    const notRun = plumeOutcome(p.outcome, p.uncertainty_notes) === "UNAVAILABLE";
    return step(2, SKILLS[1], "plume", {
      line: `${notRun ? "did not run (AI UNAVAILABLE)" : "gave no result"} · the official area stands, nothing put in its place`,
      more: [p.uncertainty_notes ? el("p", { class: "dk-sub__note", text: machineText(p.uncertainty_notes) }) : null],
    });
  }
  if (p.outcome === "PENDING") return step(2, SKILLS[1], "plume", { line: `waits in line · official area ${area} until it runs` });
  if (p.outcome === "OFFICIAL_ONLY") return step(2, SKILLS[1], "plume", { line: `no read needed · official area ${area}` });
  const stub = isStub(p);
  const leaned = (p.leaned_on || []).map((r) => {
    const over = otherSource(sit, r);
    return { line: `leaned on ${sourceName(sit, r.which_source_we_lean_on)}${over ? ` over ${sourceName(sit, over)}` : ""}`, r };
  });
  const readings = leaned.map(({ line, r }) => el("div", { class: "dk-sub chain__lean" },
    el("p", { class: "dk-sub__title", text: line[0].toUpperCase() + line.slice(1) }),
    el("blockquote", { class: "dk-quote" }, el("p", { text: words(r.reading, stub) }), r.why ? el("p", { class: "chain__why", text: words(r.why, stub) }) : null)));
  const rest = wall
    ? [el("p", {}, el("button", { type: "button", class: "link-btn dk-link", dataset: { act: "details-sec", sec: "estimate", focus: "chain-estimate" }, text: "TEPHRA's estimate ›" }))]
    : [sub("Rationale", p.rationale ? quote(p.rationale, stub) : null), sub("Uncertainty", p.uncertainty_notes ? quote(p.uncertainty_notes, stub) : null)];
  const repairs = Math.max(0, (p.attempts || 1) - 1);
  const foot = [`${count(p.checks.length, "check")} passed`, count(repairs, "repair"), p.latency_ms != null ? `${(p.latency_ms / 1000).toFixed(1)} s` : null].filter(Boolean).join(" · ");
  return step(2, SKILLS[1], "plume", {
    line: [area, ...leaned.map((x) => ` · ${x.line}`)],
    mark: aiMark(stub ? "stub" : p.model_id, null, MARK.read(SKILLS[1])),
    more: [...readings, ...rest],
    foot,
  });
}

// 3 · Flight planner: the action it submitted and the tools it called; its reasoning only under
// "More" with its mark, because code checks that prose for clock words alone (the footer says so).
function planStep(q) {
  if (!q) return step(3, SKILLS[2], "plan", { line: NOT_ON_HAND });
  const calls = (q.tool_calls || []).map((t) => el("p", { class: "chain__call" }, el("b", { class: "mono", text: t.name }), ` · ${t.result_summary}`));
  const tools = calls.length ? el("div", { class: "dk-sub" }, el("p", { class: "dk-sub__title", text: "Tool calls" }), ...calls) : null;
  if (q.outcome === "MODEL_FAILED") return step(3, SKILLS[2], "plan", { line: "gave no result · no plan, the flight went to the Desk", more: [tools] });
  const stub = isStub(q);
  const n = calls.length;
  const names = [...new Set((q.tool_calls || []).map((t) => t.name))].join(", ");
  const what = q.action ? `${q.action.replace(/_/g, " ")}${q.target ? ` ${q.target}` : ""}` : "No plan";
  const reasoning = q.reasoning
    ? el("div", { class: "dk-sub chain__reasoning" },
      el("div", { class: "dk-sub__titlerow" }, el("p", { class: "dk-sub__title", text: "Reasoning" }), aiMark(stub ? "stub" : q.model_id, null, MARK.chosen)),
      quote(q.reasoning, stub))
    : null;
  const rules = q.checks?.length ? el("p", { class: "dk-sub__note", text: `Decision checked by code: ${q.checks.join(" · ")}` }) : null;
  const foot = [q.reasoning ? `reasoning checked for ${(q.reasoning_checks || []).join(", ")} only` : null, q.repaired ? "rejected once, then accepted" : null].filter(Boolean).join(" · ");
  return step(3, SKILLS[2], "plan", {
    line: `${what} after ${count(n, "tool call")}${names ? `: ${names}` : ""}`,
    mark: aiMark(stub ? "stub" : q.model_id, null, MARK.chosen),
    more: [tools, reasoning, rules],
    foot: foot || null,
  });
}

// 4 · Drafter: what the code checked on the text, how many numbers it holds and whether a first
// body was rejected; the rejection notes under "More".
function draftStep(d) {
  if (!d) return step(4, SKILLS[3], "draft", { line: NOT_ON_HAND });
  const stub = isStub(d);
  const repairs = d.repaired ? 1 : 0;
  const notes = (d.validation_notes || []).map((note) => el("p", { class: "dk-sub__note", text: `rejected once: ${note}` }));
  return step(4, SKILLS[3], "draft", {
    line: `${DRAFT_CHECKED} · ${count(d.numbers_in_body, "number")} in the text, every one from the facts given · ${count(repairs, "repair")}`,
    mark: aiMark(stub ? "stub" : d.model_id, null, MARK.written),
    more: [...notes, el("p", { class: "dk-sub__note", text: `Drafted at ${hhmmz(ms(d.drafted_at))}` }), d.checks?.length ? el("p", { class: "dk-sub__note", text: `The code's rules: ${d.checks.join(" · ")}` }) : null],
  });
}

// The chain as a list. `sit` names sources through their cards when the Wall has the situation
// (null on the Desk). `mode` is the surface: "wall" links the plume step to Details › TEPHRA's
// estimate instead of repeating the rationale; any other value (the Desk) quotes it under "More".
export function chainView(chain, { sit = null, mode = "desk" } = {}) {
  const wall = mode === "wall";
  return el("ol", { class: "chain", "aria-label": "The four steps behind this draft" },
    coordinatorStep(chain.coordinator), plumeStep(chain.plume, sit, wall), planStep(chain.plan), draftStep(chain.draft));
}

// ------------------------------------------------------------------ the Wall's section (act=chain)

// Chains by advisory id: the record, or when it was last found missing (a store that answers 404
// or 503 is asked again after a minute, never every tick).
const chains = new Map();
const RETRY_MS = 60_000;
let last = null;

// Where the chain is asked for: /api, or a hosted airline's /a/<ICAO>/api (wall/details.js sets it
// from base.js; this file imports nothing more, so it runs alone under the tests).
let apiPath = (path) => `/api${path}`;
export function setChainApi(fn) { apiPath = fn; }

async function fetchChain(id) {
  chains.set(id, { pending: true });
  let chain = null;
  try {
    const res = await fetch(apiPath(`/advisories/${encodeURIComponent(id)}/chain`), { headers: { Accept: "application/json" } });
    if (res.ok) chain = await res.json();
  } catch {
    chain = null;
  }
  chains.set(id, chain ? { chain } : { missedAt: Date.now() });
  if (last && last.ui.details.sec === "chain" && last.ui.details.vid === id) chainSection(last.D, last.store, last.ui, last.host);
}

// "Why this advice" in the flight host, for the advisory in ui.details.vid: the chain when the
// store serves it; while it is fetched, one line; when it is not on hand, said so with the way back.
export function chainSection(D, store, ui, host = $("flights")) {
  const id = ui.details.vid;
  const adv = store.advisories.find((a) => a.id === id) || null;
  const back = el("button", { type: "button", class: "link-btn", dataset: { act: "details-sec", sec: "decisions", focus: "chain-back" }, text: "Decisions ›" });
  if (!adv) {
    host.replaceChildren(dkSection("chain-head", dkHeader({ id: "chain-head", title: "Why this advice" }), dkEmpty("No draft is picked.", "Choose one under Decisions.", back)));
    return;
  }
  last = { D, store, ui, host };
  const got = chains.get(adv.id);
  if (!got || (got.missedAt && Date.now() - got.missedAt > RETRY_MS)) fetchChain(adv.id);
  const sit = D?.sits?.find((s) => s.volcano_id === adv.volcano_id) || null;
  const body = got?.chain
    ? chainView(got.chain, { sit, mode: "wall" })
    : got?.missedAt ? dkEmpty("The reasoning chain for this draft is not on hand.", "Nothing stands in for it.", back)
      : el("p", { class: "dk-foot chain__wait", text: "Fetching the chain…" });
  host.replaceChildren(dkSection("chain-head",
    dkHeader({ id: "chain-head", title: `${adv.proxy_flight} · ${actionWords(adv)}`, sub: "What each skill decided before this draft, and what code checked. Approve or reject on the Desk." }),
    body));
}
