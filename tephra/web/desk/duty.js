// The Duty Officer brief on Decide: the coordinator agent that orders the AI work and hands it to
// the specialists (tephra/agents/duty_officer.py). One line by default (UI-REDESIGN R10.4); tap to
// open the full brief in place (priorities with "Must do" tags, watch list, delegations,
// deferred). Work left undone is a failure and stays visible while the brief is folded. Rule 0 (no fallbacks): when the model failed the card says so, lists
// the work left undone and shows no brief. Model-written text (summary, reasons, watch,
// deferral reasons) sits under an AI-written chip with the model id; labels, counts and result
// lines are written by code and stay plain. Text goes in through textContent only.

import { PATHS, api } from './api.js';
import { append, byId, el, icon } from './dom.js';
import { hhmmz } from './format.js';
import { app } from './state.js';
import { aiMark } from './ui.js';
import { drawAiChip } from './budget.js';
// The Wall's plain-words table (wall/x-parts.js, R12.7), shared so both screens say the same.
import { machineText, plainLine, reasonClass } from '../wall/x-parts.js';

const RESULTS_SHOWN = 2;

const OUTCOME = {
  ACCEPTED: ['i-check', 'Accepted', 'ok'],
  REPAIRED: ['st-caution', 'Repaired', 'caution'],
  STUB: ['i-code', 'AI off · code', 'off'],
  MODEL_FAILED: ['st-caution', 'No brief (AI unavailable)', 'caution'],
};
// A run the quota refused never reached a model (docs/UI-AI-QUIET.md K93, H4).
const refused = (run) => run.outcome === 'MODEL_FAILED' && (run.validation_errors || []).some((e) => reasonClass(e) === 'budget');
const SPECIALIST = {
  assess_volcanoes: ['Satellite + Plume Reader', 'volcano'],
  plan_flights: ['Planner + Drafter', 'flight'],
  run_recovery: ['Recovery', 'network'],
  draft_sra: ['SRA drafter', 'region'],
};

let expanded = false;

const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
const labelOf = (run, id) => (run.worklist.find((i) => i.id === id) || {}).label || id;

export async function loadDuty() {
  const res = await api(PATHS.duty);
  if (res.ok && res.data && Array.isArray(res.data.runs)) {
    app.duty = res.data.runs[0] || null;
    app.dutyLoaded = true;
    app.hub.dutyChanged();
  }
}

export function onDutyEvent(run) {
  if (!run || typeof run !== 'object' || typeof run.id !== 'string' || !Array.isArray(run.worklist)) return;
  app.duty = run;
  app.dutyLoaded = true;
  app.hub.dutyChanged();
}

// One entry per tool, calls added up: the same tool called twice shows once.
function delegations(run) {
  const byTool = new Map();
  for (const d of run.dispatches) {
    const g = byTool.get(d.tool) || { tool: d.tool, ids: new Set(), calls: 0, failed: 0, ms: 0, results: [] };
    d.item_ids.forEach((id) => g.ids.add(id));
    g.calls += 1;
    g.failed += d.ok ? 0 : 1;
    g.ms += d.ms;
    g.results.push(d);
    byTool.set(d.tool, g);
  }
  return [...byTool.values()];
}

const stateChip = (tone, shape, word, title) =>
  el('span', { class: `chip chip--d-${tone}`, title }, icon(shape, 'st'), el('span', { text: word }));

// The stub's reason is code text ("NO MODEL: urgency order"), the same for every item: it is said
// once above the list ("In urgency order (AI off)"), not under each item (review 1, item 14).
const STUB_WHY = /^NO MODEL: urgency order$/;

function priority(run, p, stub) {
  const item = run.worklist.find((i) => i.id === p.item_id);
  const why = stub && STUB_WHY.test(p.why) ? null : p.why;
  return el('li', { class: 'dcard__p' },
    el('span', { class: 'dcard__plabel' },
      item && item.mandatory ? el('span', { class: 'dcard__must', text: 'Must do' }) : null,
      labelOf(run, p.item_id)),
    why ? el('span', { class: `dcard__why${stub ? '' : ' dcard__ai'}`, text: why }) : null);
}

// Failed results always show; the first two good ones show, the rest sit behind a disclosure.
function resultLines(results) {
  const line = (r) => el('span', { class: `dcard__dres${r.ok ? '' : ' is-bad'}`, text: r.result });
  const good = results.filter((r) => r.ok);
  const out = [...results.filter((r) => !r.ok).map(line), ...good.slice(0, RESULTS_SHOWN).map(line)];
  const rest = good.slice(RESULTS_SHOWN);
  if (rest.length) {
    out.push(el('details', { class: 'dcard__resmore' }, el('summary', { text: `${rest.length} more result${rest.length === 1 ? '' : 's'}` }), ...rest.map(line)));
  }
  return out;
}

function delegationRow(g) {
  const [name, unit] = SPECIALIST[g.tool] || [g.tool, 'item'];
  const bad = g.failed > 0;
  return el('li', { class: `dcard__d${bad ? ' dcard__d--bad' : ''}` },
    icon('i-arrow-right', 'icon dcard__arrow'),
    el('span', { class: 'dcard__dmain' },
      el('span', { class: 'dcard__dtop' },
        el('strong', { text: name }),
        el('span', { class: `dcard__dstat${bad ? ' is-bad' : ''}`, text: bad ? (g.failed === g.calls ? 'failed' : `${g.failed} of ${g.calls} failed`) : 'ok' })),
      el('span', { class: 'dcard__dnums', text: `${plural(g.ids.size, unit)}${g.calls > 1 ? ` · ${g.calls} calls` : ''} · ${g.ms.toLocaleString('en-US')} ms` }),
      ...resultLines(g.results)));
}

// Must-do work left undone that Plan by hand does not already list (K92): those flights carry
// "Must do" there; anything else stays here.
function undone(run) {
  const listed = new Set([...app.failures.values()].filter((f) => !f.handled_at).map((f) => f.flight_id));
  const rest = run.undispatched.filter((id) => {
    const item = run.worklist.find((i) => i.id === id);
    return !(item && item.kind === 'PLAN' && listed.has(item.subject));
  });
  if (!rest.length) return null;
  return el('div', { class: 'dcard__undone', role: 'status' },
    el('p', { class: 'dcard__undonet' }, icon('st-caution', 'st'),
      el('span', { text: `${plural(rest.length, 'must-do item')} not handed out: do ${rest.length === 1 ? 'it' : 'them'} by hand` })),
    el('ul', {}, rest.map((id) => el('li', { text: labelOf(run, id) }))));
}

// The one line Decide shows (R10.4): "Duty Officer (AI off): 3 flights need a plan first ›". A
// run that did not run points at Plan by hand, which holds its flights (K91).
function oneLine(run, failed, stub) {
  const who = stub ? 'Duty Officer (AI off)' : 'Duty Officer';
  // the cause is said once, in the Plan by hand group's head; this line says where the work went
  if (failed) return [who, 'no brief this run · its must-do flights are in Plan by hand'];
  if (run.undispatched.length) return [who, `${plural(run.undispatched.length, 'must-do item')} not handed out`];
  const prios = run.brief ? run.brief.priorities : [];
  if (prios.length) {
    // One noun for every run, with the run's time, so the line does not read as two different
    // counts when an aircraft-triggered run and a tick run alternate (review 2, item 14).
    return [who, `${plural(prios.length, 'item')} put in order of urgency · latest run ${hhmmz(run.finished_at)}`];
  }
  return [who, `${plural(run.dispatches.length, 'job')} handed out · latest run ${hhmmz(run.finished_at)}`];
}

function buildCard(run) {
  const [shape, word0, tone] = OUTCOME[run.outcome] || ['i-info', run.outcome, 'off'];
  const word = refused(run) ? 'Not run (AI paused)' : word0;
  const dispatched = delegations(run);
  const calls = run.dispatches.length;
  const failed = run.outcome === 'MODEL_FAILED';
  const b = run.brief;
  const stub = run.outcome === 'STUB' || run.llm_backend === 'stub';
  const [who, what] = oneLine(run, failed, stub);
  const left = undone(run);
  const bad = failed || Boolean(left);

  const toggle = el('button', {
    type: 'button',
    class: `dcard__head${bad ? ' is-bad' : ''}`,
    'aria-expanded': String(expanded),
    'aria-controls': 'duty-more',
  },
    icon(bad ? 'st-caution' : 'i-agent', bad ? 'st dcard__icon' : 'icon dcard__icon'),
    el('span', { class: 'dcard__title', id: 'duty-title' }, el('strong', { text: `${who}: ` }), el('span', { text: what }),
      !failed && !stub ? [' ', aiMark('AI-written', run.model_id)] : null),
    icon(expanded ? 'i-chevron-down' : 'i-chevron-right', 'icon dcard__chev'));

  const card = el('article', { class: `dcard dcard--${tone}${expanded ? ' is-open' : ''}`, 'aria-labelledby': 'duty-title' }, toggle);
  // The work left undone is never folded, even while the brief is collapsed.
  if (left) card.append(left);

  const more = el('div', { id: 'duty-more', class: 'dcard__more', hidden: !expanded });
  append(more, [el('p', { class: 'dcard__state' }, stateChip(tone, shape, word, failed ? (refused(run) ? "Today's free AI quota is used up: no model was called" : 'The model was called and gave no brief that passed the code checks') : 'Outcome of the last Duty Officer run'),
    failed ? null : el('span', { class: 'dcard__count', text: plural(calls, 'delegation') }))]);
  if (failed) {
    append(more, [el('p', { class: 'dcard__note', text: 'No brief was made up in its place.' })]);
  } else if (b) {
    const summary = stub && /^NO MODEL: \d+ delegation\(s\) made in urgency order\.$/.test(b.summary)
      ? `AI off: code handed out ${plural(calls, 'job')} in urgency order.`
      : b.summary;
    append(more, [
      stub ? null : el('div', { class: 'dcard__ai' }, aiMark('AI-written', run.model_id)),
      el('p', { class: `dcard__summary${stub ? '' : ' dcard__ai'}`, text: summary }),
      b.priorities.length ? el('h3', { class: 'dcard__h', text: stub && b.priorities.every((p) => STUB_WHY.test(p.why)) ? 'Do first · in urgency order (AI off)' : 'Do first' }) : null,
      b.priorities.length ? el('ol', { class: 'dcard__plist', 'aria-label': 'Priorities' }, b.priorities.map((p) => priority(run, p, stub))) : null,
      b.watch.length ? el('h3', { class: 'dcard__h', text: 'Watch' }) : null,
      b.watch.length ? el('ul', { class: 'dcard__wlist dcard__ai' }, b.watch.map((w) => el('li', { text: plainLine(w) }))) : null,
    ]);
  }
  // a run that did not run delegated nothing: no empty section for it (K93)
  if (dispatched.length || !failed) {
    more.append(el('h3', { class: 'dcard__h', text: 'Delegated to' }),
      dispatched.length
        ? el('ul', { class: 'dcard__dlist' }, dispatched.map(delegationRow))
        : el('p', { class: 'dcard__note', text: 'It delegated nothing this run.' }));
  }
  if (run.deferred.length) {
    more.append(el('h3', { class: 'dcard__h', text: `Deferred · ${run.deferred.length}` }),
      el('ul', { class: 'dcard__wlist' }, run.deferred.map((d) =>
        el('li', {}, el('span', { class: 'dcard__plabel', text: labelOf(run, d.item_id) }), el('span', { class: 'dcard__why dcard__ai', text: plainLine(d.reason) })))));
  }
  const mandatory = run.worklist.filter((i) => i.mandatory).length;
  // The run's machine facts (model, turns, offered, trigger) sit under Technical detail (item 14).
  // a refused run made no call, so it has no turns to count
  const meta = `${stub ? 'AI off (NO MODEL, offline stub)' : refused(run) ? `no call made · would have used ${run.model_id}` : run.model_id}${refused(run) ? '' : ` · ${plural(run.turns, 'turn')}`} · ${run.worklist.length} offered${mandatory ? `, ${mandatory} must do` : ''} · AI worker after ${run.trigger === 'adsb' ? 'new aircraft' : 'a tick'}, done ${hhmmz(run.finished_at)}${run.replay ? ' · recorded' : ''}${run.recorded_answer ? ` · ${run.recorded_answer}` : ''}`;
  more.append(el('details', { class: 'tech' }, el('summary', { text: 'Technical detail' }),
    el('p', { class: 'mono tech__line dcard__meta', text: meta }),
    b && stub && b.summary ? el('p', { class: 'mono tech__line', text: machineText(b.summary) }) : null,
    failed ? el('p', { class: 'mono tech__line', text: `Duty Officer AI unavailable: ${machineText(run.validation_errors[0] || 'no reason recorded')}` }) : null));
  card.append(more);

  toggle.addEventListener('click', () => {
    expanded = !expanded;
    renderDuty();
    byId('duty-section').querySelector('.dcard__head').focus({ preventScroll: true });
  });
  return card;
}

export function renderDuty() {
  const host = byId('duty-section');
  if (!host) return;
  const run = app.duty;
  host.hidden = !run;
  if (!run) {
    host.replaceChildren();
    return;
  }
  host.replaceChildren(buildCard(run));
  drawAiChip();
}
