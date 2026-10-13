// Flights to plan by hand (docs/UI-AI-QUIET.md K77, K81-K84; docs/EXTENSIONS.md rule 0): a flight
// the AI could not plan or draft for. There is no substitute plan. The flights sit in one compact
// group per cause, after the Next decision: the cause said once in the group's head, a short row
// per flight, and the dispatcher marks each handled with a note (audit AI_FAILURE_HANDLED).

import { PATHS, api, errorCode } from './api.js';
import { announce, byId, el, icon } from './dom.js';
import { hhmmz } from './format.js';
import { app } from './state.js';
import { openBSheet } from './ui.js';
import { toast } from './toast.js';
import { deskAi, openBudget } from './budget.js';
import { renderDuty } from './duty.js';
import { WHY, reasonClass } from '../wall/x-parts.js';

const NOTE_MAX = 500;
const ROWS_FIRST = 5;
const HANDLED_CHIPS = ['Contacted the flight by phone', 'Re-planned by hand', 'Flight already clear', 'Duplicate'];

export const openFailures = () => [...app.failures.values()].filter((f) => !f.handled_at);

export async function loadFailures() {
  const res = await api(PATHS.failures);
  if (res.ok && res.data && Array.isArray(res.data.failures)) {
    app.failures = new Map(res.data.failures.filter((f) => f && f.id).map((f) => [f.id, f]));
    renderFailures();
    app.hub.badges();
  }
}

// One announcement per batch, not one per flight (K84): the first says the whole group and why,
// later ones only the change in count.
let heard = 0;
let batch = 0;
function announceBatch() {
  window.clearTimeout(batch);
  batch = window.setTimeout(() => {
    const n = openFailures().length;
    if (n > heard) {
      const ai = deskAi();
      const word = ai.kind === 'paused' ? 'AI paused' : 'AI unavailable';
      announce(heard === 0 ? `${n} ${n === 1 ? 'flight' : 'flights'} to plan by hand: ${word}.` : `${n - heard} more ${n - heard === 1 ? 'flight' : 'flights'} to plan by hand.`);
    }
    heard = n;
  }, 800);
}

export function onFailureEvent(f) {
  if (!f || typeof f !== 'object' || typeof f.id !== 'string') return;
  const had = app.failures.has(f.id);
  if (f.handled_at) app.failures.delete(f.id);
  else app.failures.set(f.id, f);
  renderFailures();
  app.hub.badges();
  if (!had && !f.handled_at) announceBatch();
}

// The Duty Officer's must-do flights ("hex:volcano_id") in its newest run.
function mustDo() {
  const run = app.duty;
  if (!run || !Array.isArray(run.undispatched)) return new Set();
  return new Set(run.undispatched.map((id) => (run.worklist || []).find((i) => i.id === id)).filter((i) => i && i.kind === 'PLAN').map((i) => i.subject));
}

const HELPER = { duty_officer: 'duty', planner: 'planner', drafter: 'drafter' };
const causeOf = (f) => `${HELPER[f.stage] || f.stage}|${reasonClass(f.reason)}`;
// "AI paused until 0700Z" or "AI unavailable (timed out)", from the cause and the live budget.
function causeWords(cls, ai) {
  if (cls === 'budget') return ai.kind === 'paused' && ai.until ? `AI paused until ${ai.until}` : 'AI paused';
  return `AI unavailable (${WHY[cls] || WHY.other})`;
}

// One flight in one line (about 56 px): what it is, where it is, when it was left, Must do.
function row(f, must) {
  const entry = f.inside_now ? 'Inside the ash now' : `enters in ${f.minutes_to_entry} min when found (est.)`;
  return el('li', { class: 'hrow', 'data-id': f.id },
    el('span', { class: 'hrow__line' },
      el('strong', { class: 'hrow__flight', text: f.proxy_flight }), ' · ',
      el('span', { class: `hrow__entry${f.inside_now ? ' is-inside' : ''}`, text: entry }),
      must ? [' ', el('span', { class: 'dcard__must', text: 'Must do' })] : null),
    el('span', { class: 'hrow__line hrow__meta', text: `${f.callsign || 'no callsign'} · ${f.volcano_name} · left ${hhmmz(f.created_at)}` }),
    el('button', { type: 'button', class: 'btn btn--outline btn--sm fcard__btn', 'data-handle': f.id, disabled: app.offline, 'aria-label': `Mark ${f.proxy_flight} handled` },
      icon('i-hand'), el('span', { text: 'Mark handled…' })));
}

function group(key, list, ai, must, many) {
  const cls = key.split('|')[1];
  const n = list.length;
  const id = `fail-title-${key.replace(/[^a-z]/gi, '-')}`;
  const duty = app.duty && app.duty.outcome === 'MODEL_FAILED' && key.startsWith('duty|')
    ? el('p', { class: 'hgroup__fact', text: `No Duty Officer brief this run (${cls === 'budget' ? 'AI paused' : 'AI unavailable'}).` }) : null;
  const raws = [...new Set(list.map((f) => `${f.reason}${f.model_id && f.model_id !== 'stub' ? ` · would have used ${f.model_id}` : ''}`))];
  const items = list.map((f) => row(f, must.has(f.flight_id)));
  return el('div', { class: 'hgroup', role: 'group', 'aria-labelledby': id },
    el('div', { class: 'hgroup__head' },
      el('h2', { class: 'hgroup__title', id }, icon('st-caution', 'st'), el('span', { text: `Plan by hand · ${n} ${n === 1 ? 'flight' : 'flights'}` })),
      el('button', { type: 'button', class: 'linkbtn hgroup__why', 'data-why': '1', 'aria-label': 'Why: open AI today' }, el('span', { text: 'Why ›' }))),
    el('p', { class: 'hgroup__sub', text: `No AI plan for ${n === 1 ? 'this flight' : 'these flights'}: ${causeWords(cls, ai)}. Nothing was substituted. Decide each flight, then mark it handled.` }),
    duty,
    el('ul', { class: 'hrows', 'aria-labelledby': id }, items.slice(0, ROWS_FIRST)),
    n > ROWS_FIRST ? el('details', { class: 'hmore', open: many ? true : null }, el('summary', { text: `Show all ${n} flights` }), el('ul', { class: 'hrows' }, items.slice(ROWS_FIRST))) : null,
    el('details', { class: 'tech' }, el('summary', { text: 'Technical detail' }), ...raws.map((r) => el('p', { class: 'mono tech__line', text: r }))));
}

export function renderFailures() {
  const host = byId('fail-section');
  if (!host) return;
  // the Duty Officer card drops the must-do flights this group lists (K92)
  renderDuty();
  const must = mustDo();
  // inside the ash first; must-do first inside each; then the soonest entry
  const list = openFailures().sort((a, b) => Number(b.inside_now) - Number(a.inside_now)
    || Number(must.has(b.flight_id)) - Number(must.has(a.flight_id)) || a.minutes_to_entry - b.minutes_to_entry);
  host.hidden = list.length === 0;
  if (!list.length) {
    heard = 0;
    host.replaceChildren();
    return;
  }
  const open = new Set([...host.querySelectorAll('details.hmore[open]')].map((d) => d.closest('.hgroup')?.getAttribute('aria-labelledby')));
  const groups = new Map();
  for (const f of list) {
    const k = causeOf(f);
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(f);
  }
  const ai = deskAi();
  host.replaceChildren(...[...groups].map(([k, l]) => group(k, l, ai, must, open.has(`fail-title-${k.replace(/[^a-z]/gi, '-')}`))));
  if (!host.dataset.wired) {
    host.dataset.wired = '1';
    host.addEventListener('click', (event) => {
      if (event.target.closest('[data-why]')) openBudget();
    });
  }
}

export function openHandled(id) {
  const f = app.failures.get(id);
  if (!f) return;
  const area = el('textarea', { id: 'handled-note', class: 'field', rows: '4', maxlength: String(NOTE_MAX), autocomplete: 'off', 'aria-describedby': 'handled-count' });
  const count = el('p', { id: 'handled-count', class: 'counter', text: `0 / ${NOTE_MAX} · optional` });
  const msg = el('div', { class: 'field-msg', 'aria-live': 'polite' });
  const chips = el('div', { class: 'reason-chips' }, HANDLED_CHIPS.map((text) =>
    el('button', { type: 'button', class: 'reason-chip', onclick: () => {
      area.value = area.value ? `${area.value.replace(/[.\s]+$/, '')}. ${text}` : text;
      area.dispatchEvent(new Event('input'));
      area.focus();
    } }, text)));
  area.addEventListener('input', () => {
    count.textContent = `${area.value.length} / ${NOTE_MAX} · optional`;
  });
  const go = el('button', { type: 'button', class: 'btn btn--approve btn--block', disabled: app.offline },
    icon('i-check'), el('span', { text: `Mark ${f.proxy_flight} handled` }));
  const sheet = openBSheet({
    title: `Handle ${f.proxy_flight} by hand`,
    body: el('div', { class: 'stack' },
      el('p', { class: 'panel__note', text: `No AI plan for this flight (${reasonClass(f.reason) === 'budget' ? 'AI paused: daily quota' : `AI unavailable: ${WHY[reasonClass(f.reason)]}`}).` }),
      el('p', { class: 'note', text: `Entry ${f.inside_now ? 'was inside the area when found' : `in ${f.minutes_to_entry} min when found`}. Record what you did. The note goes in the audit log under your name.` }),
      el('label', { class: 'flabel', for: 'handled-note', text: 'What did you do? (optional)' }), chips, area, count, msg,
      el('details', { class: 'tech' }, el('summary', { text: 'Technical detail' }), el('p', { class: 'mono tech__line', text: `${f.reason}${f.model_id && f.model_id !== 'stub' ? ` · would have used ${f.model_id}` : ''}` }))),
    footer: go,
  });
  go.addEventListener('click', async () => {
    go.disabled = true;
    go.replaceChildren(el('span', { class: 'spinner', 'aria-hidden': 'true' }), el('span', { text: 'Saving…' }));
    const res = await api(PATHS.failureHandled(id), { method: 'POST', body: { note: area.value.trim() } });
    if (res.ok) {
      app.failures.delete(id);
      renderFailures();
      app.hub.badges();
      sheet.close();
      toast({ tone: 'ok', title: `${f.proxy_flight} marked handled. Recorded under ${app.me ? app.me.name : 'you'}.` });
      announce(`${f.proxy_flight} marked handled.`);
      return;
    }
    go.disabled = false;
    go.replaceChildren(icon('i-check'), el('span', { text: `Mark ${f.proxy_flight} handled` }));
    const why = res.status === 404 ? 'This item no longer exists.' : res.status === 401 ? 'Your session has ended. Sign in again.' : (res.data && res.data.detail) || (errorCode(res) ? errorCode(res) : `HTTP ${res.status}`);
    msg.replaceChildren(el('p', { class: 'msg msg--serious' }, icon('st-serious', 'st'), el('span', { text: `Not saved: ${why}` })));
    if (res.status === 404) loadFailures();
  });
  window.setTimeout(() => area.focus(), 50);
}
