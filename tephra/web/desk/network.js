// Airports (UI-REDESIGN R10.6, was Network recovery, WP4): the airports the ash closes, the day's
// flights re-planned by a CP-SAT solver in three scenarios (code), and the recommendation with its
// rationale. One decision card first (what closes, what the plan does, what it costs, approve or
// reject inside the card); closed airports, the other plans, why, flight by flight and the numbers
// sit in disclosures under it. Re-plan now is in the ⋯ menu. The airline and its schedule are
// fictional (Ring of Fire Air, synthetic).

import { PATHS, api, errorCode, isUnavailable, problems, unavailableReason } from './api.js';
import { announce, byId, el, icon } from './dom.js';
import { activeNow, dayMonthHhmm, deskName, hhmmz, secs } from './format.js';
import { app } from './state.js';
import { toast } from './toast.js';
import { aiMark, fmtUsd, fromReplayChip, openBSheet, unavailableCard } from './ui.js';
import { machineText, notRun, plainWhy, reasonClass } from '../wall/x-parts.js';
import { openBudget } from './budget.js';
import { TENANT } from '../base.js';

const STATUS = {
  DRAFT: ['i-clock', 'Waiting for your decision', 'neutral'],
  APPROVED: ['i-approved', 'Approved', 'ok'],
  REJECTED: ['i-rejected', 'Rejected', 'neutral'], // a decision, not an alarm: never red (D4)
  SUPERSEDED: ['i-superseded', 'Replaced by a newer plan', 'off'],
  AI_UNAVAILABLE: ['st-caution', 'No result', 'caution'],
};

// Why a plan has no recommendation, in the §1.1 words (docs/UI-AI-QUIET.md K95, Naming): "Recovery
// planner gave no result (timed out)", or "did not run" for a quota refusal, whose cause is said in
// the assistant sheet only, behind "Why ›" (8.6). The raw reason stays under Technical detail.
function noRecWords(p) {
  const cls = reasonClass([p.unavailable_reason, ...(p.validation_errors || [])].join(' '));
  return notRun(cls) ? 'Recovery planner did not run.' : `Recovery planner gave no result (${plainWhy(cls)}).`;
}
const whyBtn = () => el('button', { type: 'button', class: 'linkbtn', 'aria-label': 'Why: open the TEPHRA Assistant sheet', onclick: openBudget }, el('span', { text: 'Why ›' }));
// The re-plan the queue holds for later: that it waits, not when (the slot is in the assistant sheet).
function queuedReplan() {
  const w = app.budget && Array.isArray(app.budget.waiting) ? app.budget.waiting.find((x) => x.status === 'WAITING' && x.item && x.item.kind === 'RECOVER') : null;
  return w ? 'A new plan waits in line for TEPHRA Assistant.' : '';
}

// A plan that found no plan (R2.6): the solver's status in plain words, never the assistant's failure.
// The raw string stays under Technical detail. Null when the failure is not a solver result.
export function planProblem(plan) {
  if (!plan) return null;
  const raw = [plan.unavailable_reason, ...(plan.validation_errors || [])].filter(Boolean).join(' · ');
  const fromText = /NO FEASIBLE PLAN[^(]*\(([A-Z_]+)\)|HAS NO PLAN \(([A-Z_]+)\)/.exec(raw);
  const noPlan = (plan.scenarios || []).find((sc) => sc.status === 'NO_PLAN');
  const status = fromText ? fromText[1] || fromText[2] : plan.status === 'AI_UNAVAILABLE' && noPlan ? noPlan.solver_status : null;
  if (!status) return null;
  return { status, words: `${solverWords(status)}. A dispatcher must plan the network by hand.`, raw };
}

function solverWords(status) {
  if (status === 'INFEASIBLE') return 'No plan found: no plan fits the closures';
  if (status === 'UNKNOWN') return 'No plan found: the solver did not finish in time';
  return `No plan found (solver: ${status})`;
}

// "Best plan found (43 s)" / "solver gave no answer after 43 s" (R12.6).
function solveLine(sc) {
  const t = secs(sc.solve_ms);
  if (sc.solver_status === 'OPTIMAL') return `Best plan found (${t})`;
  if (sc.solver_status === 'FEASIBLE') return `Plan found, not proven best (${t})`;
  if (sc.solver_status === 'UNKNOWN') return `solver gave no answer after ${t}`;
  if (sc.solver_status === 'INFEASIBLE') return `no plan fits the closures (${t})`;
  return `solved in ${t}`;
}

// "CLOSURE AS FORECAST" -> "Closure as forecast".
const scenarioName = (label) => {
  const t = String(label || '').toLowerCase();
  return t.charAt(0).toUpperCase() + t.slice(1);
};
const KIND = {
  CANCEL: ['i-x', 'Cancel'],
  DELAY: ['i-timer', 'Delay'],
  SWAP: ['i-refresh', 'Swap tail'],
  KEEP: ['i-check', 'Keep'],
};

let viewing = null; // scenario id being looked at
let running = false;
let runError = null; // { reason } | { text }
let checkedAt = null; // active-clock ms of the last good list
let menuOpen = false;
const opened = new Set(); // disclosures kept open across re-renders

export const draftPlans = () => app.plans.filter((p) => p.status === 'DRAFT');

// The server starts a re-plan when the closed airports change and says so in the trace ("Closed
// airports changed: WARA, WIHH, WIII; recovery agent started"). Until a plan newer than that line
// is stored, the tab says it is re-planning for those airports, never "No airport is closed"
// (review 2, item 1). The same line drives the Wall's story (wall/ext.js replanning()).
const REPLAN = /^Closed airports changed: (.+); recovery agent started$/;
export function noteTrace(lines) {
  let changed = false;
  for (const t of Array.isArray(lines) ? lines : [lines]) {
    if (!t || t.stage !== 'RECOVERY') continue;
    const m = REPLAN.exec(t.message || '');
    const at = Date.parse(t.at);
    if (!m || !Number.isFinite(at) || (app.replan && app.replan.at > at)) continue;
    const airports = Array.isArray(t.detail && t.detail.airports) && t.detail.airports.length ? t.detail.airports.map(String) : m[1].split(/,\s*/);
    app.replan = { airports, at };
    changed = true;
  }
  if (changed && app.tab === 'network') renderNetwork();
}
// The re-plan in progress, or null once a plan as new as its trace line exists.
export function replanInProgress() {
  const r = app.replan;
  if (!r) return null;
  return app.plans.some((p) => Date.parse(p.created_at) >= r.at) ? null : r;
}
export const latestPlan = () => app.plans[0] || null;

export async function loadPlans() {
  if (TENANT) {
    // re-planning an airline's own network is not built (D15): nothing to load
    app.plansLoaded = true;
    app.hub.afterPlans();
    return;
  }
  const res = await api(PATHS.recovery);
  if (res.ok && res.data && Array.isArray(res.data.plans)) {
    app.plans = res.data.plans.filter((p) => p && p.id).sort(byNewest);
    checkedAt = activeNow();
  }
  if (res.status !== 0) app.plansLoaded = true;
  renderNetwork();
  app.hub.afterPlans();
}

// The API returns the recommended scenario as `chosen` (a computed field of the plan).
export const chosenOf = (p) => p.chosen || null;

const byNewest = (a, b) => String(b.created_at).localeCompare(String(a.created_at));

export function onRecoveryEvent(p) {
  if (!p || typeof p !== 'object' || typeof p.id !== 'string' || !p.status) return;
  const known = app.plans.find((x) => x.id === p.id);
  if (known && known.version > p.version) return;
  const wasTop = latestPlan() && latestPlan().id;
  app.plans = [p, ...app.plans.filter((x) => x.id !== p.id)].sort(byNewest);
  if (!known || latestPlan().id !== wasTop) viewing = null;
  renderNetwork();
  app.hub.afterPlans();
  if (!known && p.status === 'DRAFT') announce('A new airport plan is waiting on the Airports tab.');
}

// --- pieces ----------------------------------------------------------------------------------

function window_(c) {
  const end = c.open_ended ? `${dayMonthHhmm(c.end)} (planning horizon)` : dayMonthHhmm(c.end);
  return `${dayMonthHhmm(c.start)} to ${end}`;
}

function closuresList(p) {
  const list = p.closures || [];
  if (!list.length) return [el('p', { class: 'note', text: 'No airport of the RFA network is closed.' })];
  return [el('p', { class: 'fine', text: 'Closed while the ash area comes within the closure radius. Written by code from the official products.' }),
    el('ul', { class: 'clos' }, list.map((c) =>
      el('li', { class: 'clo' },
        el('p', { class: 'clo__line' },
          el('span', { class: 'clo__icao' }, icon('st-closed', 'st'), el('span', { text: c.icao })),
          el('span', { class: 'clo__text', text: `${window_(c)}${c.summary ? ` · ${c.summary.replace(/^Ash /, 'ash ')}` : ''}` }),
          c.open_ended ? el('span', { class: 'chip chip--caution chip--sm' }, icon('st-caution', 'st'), el('span', { text: 'no end published' })) : null),
        // The full reason and every source id stay for audit.
        el('details', { class: 'clo__more' },
          el('summary', {}, icon('i-chevron-right', 'icon disclosure'), el('span', { text: 'Full reason and sources' })),
          el('p', { class: 'clo__why', text: machineText(c.reason) }),
          c.source_ids && c.source_ids.length ? el('p', { class: 'clo__src mono', text: c.source_ids.join(' · ') }) : null))))];
}

// "Numbers" (R10.6): a two-column table; the flights in the air and at risk are a wrapped list.
function numbersTable(p) {
  const d = p.disruption;
  if (!d) return [el('p', { class: 'note', text: 'No disruption figures on this plan.' })];
  const row = (k, v) => el('tr', {}, el('th', { scope: 'row', text: k }), el('td', {}, v));
  const air = d.airborne_at_risk || [];
  return [el('table', { class: 'ntable' },
    el('caption', { class: 'sr-only', text: 'Disruption numbers' }),
    el('tbody', {},
      row('Flights blocked', String(d.blocked_flights.length)),
      row('Passengers blocked', d.blocked_pax.toLocaleString('en-US')),
      row('Can still change', String(d.free_flights)),
      row("Can't change (already departed)", String(d.frozen_flights)),
      row('In the air and at risk', air.length ? el('span', { class: 'ntable__list', text: air.join(', ') }) : 'none listed')))];
}

const stat = (k, v) => el('div', { class: 'dstat' }, el('dt', { text: k }), el('dd', { text: String(v) }));

// The bar's width is set through the CSSOM: the page's CSP forbids style attributes.
function barNode(pct) {
  const fill = el('span', { class: 'sc__fill' });
  fill.style.setProperty('--w', `${pct}%`);
  return el('span', { class: 'sc__bar', 'aria-hidden': 'true' }, fill);
}

function scenarioCard(p, s, maxUsd) {
  const t = s.totals;
  const chosen = s.id === p.chosen_scenario_id;
  const on = s.id === (viewing || p.chosen_scenario_id);
  const body = [];
  if (t) {
    body.push(el('p', { class: 'sc__usd' }, el('span', { class: 'sc__usdn', text: fmtUsd(t.total_usd) }), el('span', { class: 'sc__usdk', text: 'estimated cost' })),
      barNode(maxUsd ? Math.max(4, Math.round((t.total_usd / maxUsd) * 100)) : 4),
      el('dl', { class: 'sc__st' },
        stat('Cancelled', t.cancelled_flights), stat('Delayed', t.delayed_flights), stat('Swapped', t.swapped_flights),
        stat('Delay', `${t.delay_min} min`), stat('Passengers', t.pax_affected.toLocaleString('en-US')), stat('Ferry legs', t.ferries)));
  } else {
    body.push(el('p', { class: 'sc__none' }, icon('st-caution', 'st'), el('span', { text: solverWords(s.solver_status) })));
  }
  const btn = el('button', {
    type: 'button', class: `sc ${on ? 'is-on' : ''} ${chosen ? 'is-chosen' : ''}`.trim(), 'data-scenario': s.id, 'aria-pressed': String(on),
    'aria-label': `${scenarioName(s.label)}${chosen ? ', recommended' : ''}${t ? `, ${fmtUsd(t.total_usd)}` : ', no plan'}. Show its flights`,
  },
  el('span', { class: 'sc__head' }, el('span', { class: 'sc__label', text: scenarioName(s.label) }),
    chosen ? el('span', { class: 'sc__rec' }, icon('i-sparkle', 'st'), el('span', { text: 'Recommended' })) : null),
  ...body,
  el('span', { class: 'sc__fine', text: solveLine(s) }));
  return el('li', { class: 'sc__item' }, btn);
}

function scenariosList(p) {
  const list = p.scenarios || [];
  const max = Math.max(0, ...list.map((sc) => (sc.totals ? sc.totals.total_usd : 0)));
  return [
    el('p', { class: 'fine', text: "The same day re-planned if the closure lasts as forecast, or longer. Solved by code. Costs use the operator's illustrative weights." }),
    list.length ? el('ul', { class: 'scs' }, list.map((sc) => scenarioCard(p, sc, max))) : el('p', { class: 'note', text: 'No scenario was solved.' }),
    list.length ? el('p', { class: 'fine', text: 'Tap a scenario to see its flights under Flight by flight.' }) : null,
  ];
}

// The stub's rationale is code text with a raw dollar figure: said in plain words (R12.7), raw
// under Technical detail. A model's rationale is shown as written, under its assistant mark.
const STUB_WHY = /^NO MODEL: the plan for the published closure cancels (\d+) flights and delays (\d+), affects (\d+) passengers and costs (\d+) USD\.$/;

function whyContent(p) {
  if (p.status === 'AI_UNAVAILABLE' || (!p.rationale && p.outcome === 'MODEL_FAILED')) {
    const problem = planProblem(p);
    if (problem) return [el('p', { text: problem.words }), techNode(problem.raw)];
    // the card above already says it: the words once more here, quietly, the reason one tap in (K96)
    const solved = (p.scenarios || []).length > 0;
    return [el('p', { role: 'status', text: `${noRecWords(p)} ${solved ? "The solver's plans stand, but no recommendation was made. Choose by hand." : 'No plan was solved: plan the network by hand.'}` }),
      techNode(p.unavailable_reason || (p.validation_errors || []).join(' · ') || 'no reason given')];
  }
  const m = STUB_WHY.exec(p.rationale || '');
  const text = m
    ? `Code picked the plan for the closure as published. It cancels ${Number(m[1]).toLocaleString('en-US')} flights and delays ${Number(m[2]).toLocaleString('en-US')}, affects ${Number(m[3]).toLocaleString('en-US')} passengers and costs ${fmtUsd(Number(m[4]))}.`
    : p.rationale || '';
  const card = el('div', { class: 'why' },
    el('p', { class: 'why__meta' }, aiMark('Explained by Recovery planner', p.llm_backend === 'stub' ? null : p.model_id, { code: 'Picked by code' }),
      p.outcome === 'REPAIRED' ? el('span', { class: 'chip chip--sm', text: 'repaired once' }) : null,
      el('span', { class: 'chip chip--sm', text: 'numbers checked by code' })),
    el('p', { class: 'why__text', text }));
  if (p.risks && p.risks.length) card.append(el('p', { class: 'caps', text: 'Risks' }), el('ul', { class: 'plist' }, p.risks.map((r) => el('li', { text: r }))));
  if (p.validation_errors && p.validation_errors.length) {
    card.append(el('details', { class: 'disclose' }, el('summary', {}, icon('i-chevron-right', 'icon disclosure'), el('span', { text: `Checks that failed (${p.validation_errors.length})` })),
      el('ul', { class: 'plist' }, p.validation_errors.map((r) => el('li', { text: r })))));
  }
  if (m) card.append(techNode(p.rationale));
  return [card];
}

const techNode = (raw) => (raw ? el('details', { class: 'tech' }, el('summary', { text: 'Technical detail' }), el('p', { class: 'mono tech__line', text: machineText(raw) })) : null);

// A flight number repeats every day, so a flight is shown by its key: number and service date.
const flightLabel = (a) => a.flight_key || a.flight_no;

function actionRow(a) {
  const [shape, word] = KIND[a.kind] || KIND.KEEP;
  const detail = a.kind === 'DELAY' ? `+${a.delay_min} min, departs ${dayMonthHhmm(a.new_std)}` : a.kind === 'SWAP' ? `to ${a.new_tail} (was ${a.tail})` : a.kind === 'CANCEL' ? (a.pair_id ? 'cancelled with its return leg' : 'cancelled') : '';
  return el('tr', { class: `ar ar--${a.kind.toLowerCase()}` },
    el('th', { scope: 'row' }, el('span', { class: 'ar__f mono', text: flightLabel(a) }), el('span', { class: 'ar__r', text: `${a.origin} → ${a.dest} · ${dayMonthHhmm(a.std)}` })),
    el('td', {}, el('span', { class: `akind akind--${a.kind.toLowerCase()}` }, icon(shape, 'st'), el('span', { text: word })), detail ? el('span', { class: 'ar__d', text: detail }) : null),
    el('td', { class: 'ar__p', text: String(a.pax_booked) }));
}

function flightsContent(p) {
  const sc = (p.scenarios || []).find((x) => x.id === (viewing || p.chosen_scenario_id)) || chosenOf(p);
  if (!sc) return [el('p', { class: 'note', text: 'No plan was found, so no flight changes are listed.' })];
  const acts = [...(sc.actions || [])].sort((a, b) => String(a.std).localeCompare(String(b.std)) || String(a.flight_key).localeCompare(String(b.flight_key)));
  const out = [el('p', { class: 'fine', text: `${scenarioName(sc.label)}${sc.id === p.chosen_scenario_id ? ' (recommended)' : ''}. Every other free flight keeps its schedule.` })];
  if (!acts.length) {
    out.push(el('p', { class: 'note', text: sc.totals ? 'No flight changes in this scenario.' : 'No plan was found for this scenario.' }));
    return out;
  }
  out.push(el('div', { class: 'atable-wrap' }, el('table', { class: 'atable' },
    el('caption', { class: 'sr-only', text: `Flights changed in ${scenarioName(sc.label)}` }),
    el('thead', {}, el('tr', {}, el('th', { scope: 'col', text: 'Flight' }), el('th', { scope: 'col', text: 'Action' }), el('th', { scope: 'col', class: 'ar__p', text: 'Pax' }))),
    el('tbody', {}, acts.map(actionRow)))));
  if (sc.ferry_legs && sc.ferry_legs.length) {
    out.push(el('p', { class: 'caps', text: 'Ferry legs (no passengers)' }),
      el('ul', { class: 'plist' }, sc.ferry_legs.map((f) => el('li', { text: `${f.tail} ${f.origin} → ${f.dest}, departs ${dayMonthHhmm(f.dep)}, ${f.block_min} min` }))));
  }
  return out;
}

const flightCount = (p) => {
  const sc = (p.scenarios || []).find((x) => x.id === (viewing || p.chosen_scenario_id)) || chosenOf(p);
  return sc ? (sc.actions || []).length : 0;
};

// The decision, inside the card (R10.6): never a sticky bar over the numbers.
function decisionRow(p, canApprove) {
  if (p.status === 'DRAFT') {
    return el('div', { class: 'plan__dec', role: 'group', 'aria-label': 'Decide the airport plan' },
      canApprove ? el('button', { type: 'button', class: 'btn btn--cta', 'data-plan-approve': p.id, disabled: app.offline }, icon('i-check'), el('span', { text: 'Approve plan…' })) : null,
      el('button', { type: 'button', class: 'btn btn--reject', 'data-plan-reject': p.id, disabled: app.offline }, icon('i-x'), el('span', { text: 'Reject…' })));
  }
  if (p.status === 'APPROVED') {
    return el('div', { class: 'plan__dec plan__dec--done', role: 'group' },
      el('p', { class: 'plan__done' }, icon('i-approved', 'st'), el('strong', { text: `Approved by ${deskName(p.decided_by) || 'a dispatcher'} at ${hhmmz(p.decided_at)}` }), el('span', { text: ' · queued, not sent anywhere' })),
      el('button', { type: 'button', class: 'btn btn--cta', 'data-plan-msgs': p.id, disabled: app.offline }, icon('i-sparkle'), el('span', { text: 'Draft crew and passenger messages' })));
  }
  if (p.status === 'REJECTED') {
    return el('div', { class: 'plan__dec plan__dec--done', role: 'group' }, el('p', { class: 'plan__done' }, icon('i-rejected', 'st'),
      el('strong', { text: `Rejected by ${deskName(p.decided_by) || 'a dispatcher'} at ${hhmmz(p.decided_at)}` }), p.reject_reason ? el('span', { text: `: ${p.reject_reason}` }) : null));
  }
  return null;
}

function disclosure(key, title, kids, { open = false } = {}) {
  const d = el('details', { class: 'nsec ndisc', 'data-key': key, open: opened.has(key) || open },
    el('summary', { class: 'ndisc__sum' }, el('span', { text: title }), icon('i-chevron-right', 'icon disclosure')),
    el('div', { class: 'ndisc__body' }, kids));
  d.addEventListener('toggle', () => {
    if (d.open) opened.add(key);
    else opened.delete(key);
  });
  return d;
}

// --- the panel ---------------------------------------------------------------------------------

function moreMenu(p) {
  const btn = el('button', { type: 'button', id: 'net-more-btn', class: 'iconbtn', 'aria-label': 'More actions', title: 'More actions', 'aria-haspopup': 'true', 'aria-expanded': String(menuOpen), 'aria-controls': 'net-more', 'data-netmenu': '1' }, icon('i-more'));
  const menu = el('div', { id: 'net-more', class: 'menu qmore__menu', hidden: !menuOpen },
    el('button', { type: 'button', class: 'menu__item', 'data-run': '1', disabled: running || app.offline, 'aria-busy': running ? 'true' : null },
      running ? el('span', { class: 'spinner', 'aria-hidden': 'true' }) : icon('i-refresh'), el('span', { text: running ? 'Re-planning…' : p ? 'Re-plan now' : 'Plan now' })));
  return el('div', { class: 'qmore' }, btn, menu);
}

export function renderNetwork() {
  const panel = byId('panel-network');
  if (!panel) return;
  const p = latestPlan();
  const keep = panel.contains(document.activeElement) ? (document.activeElement.dataset.run ? 'run' : document.activeElement.id) : '';
  const head = el('div', { class: 'phead phead--row' },
    el('h1', { id: 'net-title', class: 'phead__title', tabindex: '-1', text: 'Airport plan' }),
    moreMenu(p));
  const parts = [head];
  const re = replanInProgress();
  if (running || re) {
    const icaos = re ? re.airports.join(', ') : p ? (p.closures || []).map((c) => c.icao).join(', ') : '';
    parts.push(el('p', { class: 'plan__busy', role: 'status', 'aria-busy': 'true' }, el('span', { class: 'spinner', 'aria-hidden': 'true' }), el('span', { text: icaos ? `Re-planning for ${icaos}…` : 'Re-planning…' })));
  }
  if (runError) {
    parts.push(runError.reason ? unavailableCard(runError.reason, { instead: 'No plan was made. Re-plan the day by hand.', onRetry: runRecovery }) : el('div', { class: 'panel panel--serious', role: 'alert' }, el('p', { class: 'panel__title' }, icon('st-serious', 'st'), el('span', { text: runError.text }))));
  }
  if (!p && re) {
    // Airports are closed and the first plan is being built: say which, with no other numbers.
    parts.push(el('div', { class: 'plan plan--empty' },
      el('p', { class: 'plan__lead', text: `Ash closes ${re.airports.length} RFA airport${re.airports.length === 1 ? '' : 's'} (all volcanoes): ${re.airports.join(', ')}.` }),
      el('p', { class: 'plan__foot', text: `The plan for the day's flights is being built (started ${hhmmz(re.at)}). It appears here for your decision when it is ready.` }),
      el('p', { class: 'plan__tags' }, el('span', { class: 'chip chip--fict', title: 'Ring of Fire Air and its schedule are made up' }, icon('i-info', 'st'), el('span', { text: 'Fictional airline RFA · synthetic schedule' })))));
    panel.replaceChildren(...parts);
    restoreFocus(panel, keep);
    return;
  }
  if (!p) {
    parts.push(app.plansLoaded
      ? el('div', { class: 'plan plan--empty' },
        el('p', { class: 'plan__lead', text: 'No RFA airport is closed by ash right now.' }),
        el('p', { class: 'plan__foot', text: `Last checked ${checkedAt === null ? '–' : hhmmz(checkedAt)}. A plan appears here when the ash closes an airport of the RFA network. You can also choose Plan now in the ⋯ menu.` }),
        el('p', { class: 'plan__tags' }, el('span', { class: 'chip chip--fict', title: 'Ring of Fire Air and its schedule are made up' }, icon('i-info', 'st'), el('span', { text: 'Fictional airline RFA · synthetic schedule' }))))
      : el('p', { class: 'boot' }, el('span', { class: 'spinner', 'aria-hidden': 'true' }), el('span', { text: 'Loading…' })));
    panel.replaceChildren(...parts);
    restoreFocus(panel, keep);
    return;
  }
  const closures = p.closures || [];
  const chosen = chosenOf(p);
  const t = chosen && chosen.totals;
  const problem = planProblem(p);
  const solvedAny = (p.scenarios || []).length > 0;
  // the status says what is missing; the line below says why once (review clutter 12)
  const [shape, word, tone] = problem ? ['st-caution', 'No plan found', 'serious']
    : p.status === 'AI_UNAVAILABLE' ? ['st-caution', solvedAny ? 'No recommendation' : 'No plan', 'caution'] : STATUS[p.status] || STATUS.DRAFT;
  const n = closures.length;
  const card = el('section', { class: `plan plan--${tone}`, 'aria-labelledby': 'plan-eyebrow' },
    el('p', { class: 'plan__eyebrow', id: 'plan-eyebrow' }, el('span', { text: 'Airport plan' }), el('span', { class: `plan__status plan__status--${tone}` }, icon(shape, 'st'), el('span', { text: word }))),
    el('p', { class: 'plan__lead', text: n ? `Ash closes ${n} RFA airport${n === 1 ? '' : 's'} (all volcanoes): ${closures.map((c) => c.icao).join(', ')}.` : 'No RFA airport is closed by ash in this plan.' }));
  if (problem) {
    card.append(el('p', { class: 'plan__problem' }, icon('st-caution', 'st'), el('span', { text: problem.words })), techNode(problem.raw));
  } else if (t) {
    card.append(
      el('p', { class: 'plan__line', text: `Plan: cancel ${t.cancelled_flights} flight${t.cancelled_flights === 1 ? '' : 's'}, delay ${t.delayed_flights}${t.swapped_flights ? `, swap ${t.swapped_flights}` : ''} · ${t.pax_affected.toLocaleString('en-US')} passengers` }),
      el('p', { class: 'plan__cost' }, el('span', { class: 'plan__costk', text: 'Estimated cost ' }), el('span', { class: 'plan__costv', text: fmtUsd(t.total_usd) })));
  } else if (p.status === 'AI_UNAVAILABLE') {
    // no plan because the assistant did not run: the job, and the queued re-plan, at the place (K95)
    const solved = (p.scenarios || []).length > 0;
    // "Why ›" on its own line: a 44 px target inside a sentence would open a gap in it
    card.append(el('p', { class: 'plan__line', text: [noRecWords(p), solved ? 'Compare the plans below and decide by hand.' : 'No plan was solved: plan the network by hand.', queuedReplan()].filter(Boolean).join(' ') }), whyBtn());
  } else {
    card.append(el('p', { class: 'plan__line', text: (p.scenarios || []).length ? 'No recommendation was made. Compare the plans below and decide by hand.' : 'No recommendation was made. No plan was solved: plan the network by hand.' }));
  }
  card.append(
    el('p', { class: 'plan__tags' },
      el('span', { class: 'chip chip--fict', title: 'Ring of Fire Air and its schedule are made up' }, icon('i-info', 'st'), el('span', { text: 'Fictional airline RFA · synthetic schedule' })),
      fromReplayChip(p)),
    // "explained by" only when a model explained something (K95, H7)
    el('p', { class: 'plan__foot', text: `${solvedAny || p.status !== 'AI_UNAVAILABLE' ? 'Planned' : 'Tried'} ${hhmmz(p.created_at)}${solvedAny ? ' by code' : ''} · version ${p.version}${p.rationale && p.llm_backend !== 'stub' && p.model_id && p.model_id !== 'stub' ? ' · explained by the Recovery planner' : ''}` }));
  const dec = decisionRow(p, Boolean(t) && !problem);
  if (dec) card.append(dec);
  parts.push(card);

  const scs = p.scenarios || [];
  parts.push(
    disclosure('closed', `Closed airports (${n})`, closuresList(p)),
    disclosure('plans', `Other plans compared (${scs.length})`, scenariosList(p), { open: Boolean(problem) }),
    disclosure('why', 'Why this plan', whyContent(p)),
    disclosure('flights', `Flight by flight (${flightCount(p)})`, flightsContent(p)),
    disclosure('numbers', 'Numbers', numbersTable(p)));
  if (app.plans.length > 1) {
    // a plan still waiting for a decision first, with a caution mark, so it is not buried (K97)
    const earlier = app.plans.slice(1).sort((a, b) => Number(b.status === 'DRAFT') - Number(a.status === 'DRAFT'));
    parts.push(disclosure('earlier', `Earlier plans (${app.plans.length - 1})`,
      [el('ul', { class: 'plist' }, earlier.map((x) => el('li', {},
        x.status === 'DRAFT' ? [icon('st-caution', 'st'), ' '] : null,
        `${hhmmz(x.created_at)} · ${planProblem(x) ? 'No plan found' : (STATUS[x.status] || [0, x.status])[1]}${chosenOf(x) && chosenOf(x).totals ? ` · ${fmtUsd(chosenOf(x).totals.total_usd)}` : ''}`)))]));
  }
  // the decision-support sentence is not page chrome any more (owner, 17 Oct: "don't put this
  // everywhere"); what approving does stays at the place you approve
  parts.push(el('p', { class: 'fine plan__fine', text: "Approving queues the plan on TEPHRA's own outbound queue. Nothing is sent to an airline system." }));
  panel.replaceChildren(...parts);
  restoreFocus(panel, keep);
}

function restoreFocus(panel, keep) {
  if (!keep) return;
  const again = keep === 'run' ? panel.querySelector('[data-run]') : byId(keep);
  if (again && panel.contains(again)) again.focus({ preventScroll: true });
}

// --- actions -----------------------------------------------------------------------------------

export async function runRecovery() {
  if (running) return;
  if (app.offline) {
    toast({ tone: 'caution', title: "You're offline. Reconnect to re-plan." });
    return;
  }
  running = true;
  runError = null;
  renderNetwork();
  menuOpen = false;
  announce('Re-planning. This can take a few seconds.');
  const res = await api(PATHS.recoveryRun, { method: 'POST', body: { closures: [] } });
  running = false;
  if (res.ok && res.data && res.data.id) {
    onRecoveryEvent(res.data);
    toast({ tone: 'ok', title: 'Airport plan drafted. Review it before you decide.' });
    return;
  }
  if (isUnavailable(res)) runError = { reason: unavailableReason(res) };
  else if (res.status === 409) runError = { text: errorCode(res) === 'no_closure' ? 'No airport of the RFA network is closed, so there is nothing to re-plan.' : errorCode(res) === 'busy' ? 'A plan is already being made. Wait for it.' : (res.data && res.data.detail) || 'Not run.' };
  else if (res.status === 401) runError = { text: 'Your session has ended. Sign in again.' };
  else runError = { text: res.status === 0 ? "Can't reach the server." : `Not re-planned: ${(res.data && res.data.detail) || `HTTP ${res.status}`}` };
  renderNetwork();
}

function confirmApprove(p) {
  const t = chosenOf(p) && chosenOf(p).totals;
  const go = el('button', { type: 'button', class: 'btn btn--approve btn--block btn--primary' }, icon('i-check'), el('span', { text: 'Approve the airport plan' }));
  const msg = el('div', { 'aria-live': 'polite' });
  const sheet = openBSheet({
    title: 'Approve the airport plan?',
    body: el('div', { class: 'stack' },
      el('p', { class: 'lead', text: chosenOf(p) ? `Plan: ${scenarioName(chosenOf(p).label)}` : 'Recommended plan' }),
      // One plain sentence instead of five caps tiles (review 1, item 15): the confirm step repeats
      // the facts, the plan card above holds the full numbers.
      t ? el('p', { class: 'confirm__facts', text: `Cancels ${t.cancelled_flights} flight${t.cancelled_flights === 1 ? '' : 's'}, delays ${t.delayed_flights}${t.swapped_flights ? ` and swaps aircraft on ${t.swapped_flights}` : ''} · ${t.pax_affected.toLocaleString('en-US')} passengers affected · estimated cost ${fmtUsd(t.total_usd)}.` }) : null,
      el('p', { class: 'note', text: `Queues the plan on TEPHRA's own outbound queue under ${app.me ? app.me.name : 'your name'}. Nothing is sent to an airline system. You can then draft crew and passenger messages.` }), msg),
    footer: go,
  });
  go.addEventListener('click', async () => {
    go.disabled = true;
    go.replaceChildren(el('span', { class: 'spinner', 'aria-hidden': 'true' }), el('span', { text: 'Approving…' }));
    const res = await api(PATHS.recoveryDecide(p.id, 'approve'), { method: 'POST', body: { version: p.version } });
    if (res.ok && res.data && res.data.id) {
      onRecoveryEvent(res.data);
      sheet.close();
      toast({ tone: 'ok', title: `Airport plan approved under ${app.me ? app.me.name : 'you'}. Not sent to any system.` });
      return;
    }
    go.disabled = false;
    go.replaceChildren(icon('i-check'), el('span', { text: 'Approve the airport plan' }));
    msg.replaceChildren(el('p', { class: 'msg msg--serious' }, icon('st-serious', 'st'), el('span', { text: res.status === 409 ? 'This plan changed or was already decided. Reload the Airports tab.' : `Not approved: ${(res.data && res.data.detail) || `HTTP ${res.status}`}` })));
    if (res.status === 409) loadPlans();
  });
}

function confirmReject(p) {
  const area = el('textarea', { id: 'plan-reason', class: 'field', rows: '4', maxlength: '500', 'aria-describedby': 'plan-reason-note' });
  const msg = el('div', { 'aria-live': 'polite' });
  const go = el('button', { type: 'button', class: 'btn btn--reject-solid btn--block' }, icon('i-x'), el('span', { text: 'Reject plan' }));
  const sheet = openBSheet({
    title: 'Reject the airport plan',
    body: el('div', { class: 'stack' }, el('label', { class: 'flabel', for: 'plan-reason', text: 'Reason (required, at least 3 characters)' }), area,
      el('p', { id: 'plan-reason-note', class: 'note', text: 'The reason is recorded in the audit log. Nothing is queued.' }), msg),
    footer: go,
  });
  go.addEventListener('click', async () => {
    const reason = area.value.trim();
    if (reason.length < 3) {
      msg.replaceChildren(el('p', { class: 'msg msg--invalid' }, icon('st-caution', 'st'), el('span', { text: 'Give a reason of at least 3 characters.' })));
      area.focus();
      return;
    }
    go.disabled = true;
    const res = await api(PATHS.recoveryDecide(p.id, 'reject'), { method: 'POST', body: { version: p.version, reason } });
    go.disabled = false;
    if (res.ok && res.data && res.data.id) {
      onRecoveryEvent(res.data);
      sheet.close();
      toast({ tone: 'rejected', title: 'Airport plan rejected · reason recorded.' });
      return;
    }
    const list = problems(res);
    // A 422 lists what to fix in the reason (caution + triangle); red is for the server.
    const bad = res.status === 422 ? ['msg--invalid', 'st-caution'] : ['msg--serious', 'st-serious'];
    msg.replaceChildren(el('p', { class: `msg ${bad[0]}` }, icon(bad[1], 'st'), el('span', { text: `Not rejected: ${list.length ? list.join(' · ') : (res.data && res.data.detail) || `HTTP ${res.status}`}` })));
  });
  window.setTimeout(() => area.focus(), 50);
}

export function onNetworkClick(event) {
  const t = event.target.closest('button');
  if (!t || !byId('panel-network').contains(t)) {
    if (menuOpen) {
      menuOpen = false;
      renderNetwork();
    }
    return false;
  }
  if (t.dataset.netmenu) {
    menuOpen = !menuOpen;
    renderNetwork();
    const first = menuOpen ? byId('net-more').querySelector('button') : byId('net-more-btn');
    if (first) first.focus();
    return true;
  }
  if (menuOpen && !t.closest('#net-more')) {
    menuOpen = false;
    renderNetwork();
  }
  if (t.dataset.run) {
    menuOpen = false;
    runRecovery();
    return true;
  }
  if (t.dataset.scenario) {
    viewing = t.dataset.scenario;
    opened.add('flights');
    renderNetwork();
    const again = byId('panel-network').querySelector(`[data-scenario="${CSS.escape(viewing)}"]`);
    if (again) again.focus({ preventScroll: true });
    return true;
  }
  const p = latestPlan();
  if (t.dataset.planApprove && p) confirmApprove(p);
  else if (t.dataset.planReject && p) confirmReject(p);
  else if (t.dataset.planMsgs && p) app.hub.draftMessages({ recovery_id: p.id }, t);
  else return false;
  return true;
}

// Esc closes the ⋯ menu and returns focus to its button.
document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape' || !menuOpen) return;
  menuOpen = false;
  renderNetwork();
  const b = byId('net-more-btn');
  if (b) b.focus();
});
