// The Duty Officer brief card at the top of the Queue: the coordinator agent that orders the AI
// work and hands it to the specialists (tephra/agents/duty_officer.py). Compact by default
// (summary, top three priorities, watch item, outcome, delegations); tap to open the full brief
// and the delegation list. Rule 0 (no fallbacks): when the model failed the card says so, lists
// the work left undone and shows no brief. Model-written text (summary, reasons, watch,
// deferral reasons) sits under an AI-written chip with the model id; labels, counts and result
// lines are written by code and stay plain. Text goes in through textContent only.

import { PATHS, api } from './api.js';
import { byId, el, icon } from './dom.js';
import { hhmmz } from './format.js';
import { app } from './state.js';
import { aiChip } from './ui.js';

const TOP = 3;
const RESULTS_SHOWN = 2;

const OUTCOME = {
  ACCEPTED: ['i-check', 'Accepted', 'ok'],
  REPAIRED: ['st-caution', 'Repaired', 'caution'],
  STUB: ['i-code', 'NO MODEL', 'off'],
  MODEL_FAILED: ['st-serious', 'AI unavailable', 'serious'],
};
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
    renderDuty();
  }
}

export function onDutyEvent(run) {
  if (!run || typeof run !== 'object' || typeof run.id !== 'string' || !Array.isArray(run.worklist)) return;
  app.duty = run;
  app.dutyLoaded = true;
  renderDuty();
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

function priority(run, p) {
  const item = run.worklist.find((i) => i.id === p.item_id);
  return el('li', { class: 'dcard__p' },
    el('span', { class: 'dcard__plabel' },
      item && item.mandatory ? el('span', { class: 'dcard__must', text: 'MANDATORY' }) : null,
      labelOf(run, p.item_id)),
    el('span', { class: 'dcard__why dcard__ai', text: p.why }));
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

function undone(run) {
  if (!run.undispatched.length) return null;
  return el('div', { class: 'dcard__undone', role: 'alert' },
    el('p', { class: 'dcard__undonet' }, icon('st-serious', 'st'),
      el('span', { text: `${plural(run.undispatched.length, 'mandatory item')} not dispatched: sent to the Desk` })),
    el('ul', {}, run.undispatched.map((id) => el('li', { text: labelOf(run, id) }))));
}

function buildCard(run) {
  const [shape, word, tone] = OUTCOME[run.outcome] || ['i-info', run.outcome, 'off'];
  const dispatched = delegations(run);
  const calls = run.dispatches.length;
  const failed = run.outcome === 'MODEL_FAILED';
  const b = run.brief;
  const stub = run.outcome === 'STUB' || run.llm_backend === 'stub';

  const toggle = el('button', {
    type: 'button',
    class: 'dcard__head',
    'aria-expanded': String(expanded),
    'aria-controls': 'duty-more',
    'aria-label': `Duty Officer brief, ${word}, ${plural(calls, 'delegation')}. ${expanded ? 'Collapse' : 'Expand'} the full brief.`,
  },
    icon('i-agent', 'icon dcard__icon'),
    el('span', { class: 'dcard__title', text: 'Duty Officer' }),
    stateChip(tone, shape, word, failed ? 'The model gave no brief that passed the code checks' : 'Outcome of the last Duty Officer run'),
    el('span', { class: 'dcard__count', text: plural(calls, 'delegation') }),
    icon('i-chevron-down', 'icon dcard__chev'));

  const card = el('article', { class: `dcard dcard--${tone}${expanded ? ' is-open' : ''}`, 'aria-labelledby': 'duty-title' }, toggle);
  toggle.querySelector('.dcard__title').id = 'duty-title';

  if (failed) {
    card.append(el('div', { class: 'dcard__fail', role: 'status' }, icon('st-serious', 'st'),
      el('p', { text: `Duty Officer AI unavailable: ${run.validation_errors[0] || 'no reason recorded'}` })),
    el('p', { class: 'dcard__note', text: 'No brief was made up in its place.' }));
  } else if (b) {
    card.append(
      stub ? null : el('div', { class: 'dcard__ai' }, aiChip(run.model_id, run.llm_backend, { sm: true })),
      el('p', { class: 'dcard__summary dcard__ai', text: b.summary }),
      b.priorities.length ? el('ol', { class: 'dcard__plist', 'aria-label': 'Top priorities' }, b.priorities.slice(0, TOP).map((p) => priority(run, p))) : null,
      b.watch.length ? el('p', { class: 'dcard__watch dcard__ai' }, el('strong', { text: 'Watch: ' }), b.watch[0], b.watch.length > 1 && !expanded ? ` (+${b.watch.length - 1} more)` : '') : null);
  }
  const left = undone(run);
  if (left) card.append(left);

  const more = el('div', { id: 'duty-more', class: 'dcard__more', hidden: !expanded });
  if (b && !failed) {
    if (b.priorities.length > TOP) {
      more.append(el('h3', { class: 'dcard__h', text: 'More priorities' }),
        el('ol', { class: 'dcard__plist', start: String(TOP + 1) }, b.priorities.slice(TOP).map((p) => priority(run, p))));
    }
    if (b.watch.length > 1) {
      more.append(el('h3', { class: 'dcard__h', text: 'Also watch' }),
        el('ul', { class: 'dcard__wlist dcard__ai' }, b.watch.slice(1).map((w) => el('li', { text: w }))));
    }
  }
  more.append(el('h3', { class: 'dcard__h', text: 'Delegated to' }),
    dispatched.length
      ? el('ul', { class: 'dcard__dlist' }, dispatched.map(delegationRow))
      : el('p', { class: 'dcard__note', text: 'It delegated nothing this run.' }));
  if (run.deferred.length) {
    more.append(el('h3', { class: 'dcard__h', text: `Deferred · ${run.deferred.length}` }),
      el('ul', { class: 'dcard__wlist' }, run.deferred.map((d) =>
        el('li', {}, el('span', { class: 'dcard__plabel', text: labelOf(run, d.item_id) }), el('span', { class: 'dcard__why dcard__ai', text: d.reason })))));
  }
  const mandatory = run.worklist.filter((i) => i.mandatory).length;
  more.append(el('p', { class: 'dcard__meta', text: `${stub ? 'NO MODEL' : run.model_id} · ${plural(run.turns, 'turn')} · ${run.worklist.length} offered${mandatory ? `, ${mandatory} mandatory` : ''} · ${run.trigger === 'adsb' ? 'new aircraft' : 'tick'} ${hhmmz(run.finished_at)}${run.replay ? ' · recorded' : ''}` }));
  card.append(more);

  card.addEventListener('click', (event) => {
    if (event.target.closest('.dcard__more') || getSelection().toString()) return;
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
}
