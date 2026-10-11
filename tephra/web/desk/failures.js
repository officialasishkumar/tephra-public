// AI failures (docs/EXTENSIONS.md rule 0): a flight the AI could not plan or draft for. There is
// no substitute plan, so the card says so and the dispatcher handles the flight by hand, then
// marks it handled with a note (audit AI_FAILURE_HANDLED).

import { PATHS, api, errorCode } from './api.js';
import { announce, byId, el, icon } from './dom.js';
import { hhmmz } from './format.js';
import { app } from './state.js';
import { aiChip, openBSheet, sectionHead } from './ui.js';
import { toast } from './toast.js';

const STAGE = { planner: 'planning the action', drafter: 'drafting the advisory' };
const NOTE_MAX = 500;
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

export function onFailureEvent(f) {
  if (!f || typeof f !== 'object' || typeof f.id !== 'string') return;
  const had = app.failures.has(f.id);
  if (f.handled_at) app.failures.delete(f.id);
  else app.failures.set(f.id, f);
  renderFailures();
  app.hub.badges();
  if (!had && !f.handled_at) announce(`AI could not plan ${f.proxy_flight}. Handle it by hand.`);
}

function card(f) {
  const entry = f.inside_now ? 'INSIDE NOW' : `enters in ${f.minutes_to_entry} min when found`;
  return el('li', { class: 'fcard', 'data-id': f.id },
    el('div', { class: 'fcard__row' },
      el('span', { class: 'fcard__flight', text: f.proxy_flight }),
      el('span', { class: 'fcard__ident', text: [f.callsign, f.type_icao].filter(Boolean).join(' · ') || 'no callsign' }),
      el('span', { class: `fcard__entry ${f.inside_now ? 'is-inside' : ''}`.trim(), text: entry })),
    el('p', { class: 'fcard__what' }, icon('st-serious', 'st'),
      el('span', { text: `AI unavailable: ${f.reason}` })),
    el('p', { class: 'fcard__meta', text: `${f.volcano_name} · failed ${STAGE[f.stage] || f.stage} at ${hhmmz(f.created_at)} · ` }, aiChip(f.model_id, f.model_id === 'stub' ? 'stub' : 'gemini', { verb: 'AI tried', sm: true })),
    el('p', { class: 'fcard__note', text: 'No substitute plan or template was made. Decide this flight by hand.' }),
    el('button', { type: 'button', class: 'btn btn--outline fcard__btn', 'data-handle': f.id, disabled: app.offline },
      icon('i-hand'), el('span', { text: 'Mark handled…' })));
}

export function renderFailures() {
  const host = byId('fail-section');
  if (!host) return;
  const list = openFailures().sort((a, b) => (a.inside_now === b.inside_now ? a.minutes_to_entry - b.minutes_to_entry : a.inside_now ? -1 : 1));
  host.hidden = list.length === 0;
  if (!list.length) {
    host.replaceChildren();
    return;
  }
  host.replaceChildren(
    sectionHead('Handle by hand', { count: list.length, tone: 'serious', id: 'fail-title', sub: 'The AI could not plan or draft these flights. Nothing was substituted.' }),
    el('ul', { class: 'fcards', 'aria-labelledby': 'fail-title' }, list.map(card)));
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
      el('p', { class: 'panel__note', text: `AI unavailable: ${f.reason}` }),
      el('p', { class: 'note', text: `Entry ${f.inside_now ? 'was inside the area when found' : `in ${f.minutes_to_entry} min when found`}. Record what you did. The note goes in the audit log under your name.` }),
      el('label', { class: 'flabel', for: 'handled-note', text: 'What did you do? (optional)' }), chips, area, count, msg),
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
