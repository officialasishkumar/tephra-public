// Flights to plan by hand (docs/UI-AI-QUIET.md K77, K81-K84, docs/UI-DESIGN.md 10.16,
// docs/EXTENSIONS.md rule 0): flights TEPHRA Assistant could not plan, draft or hand out. There is no
// substitute plan. Decide shows one "Plan by hand" card after the Next decision: the cause once,
// in caution (never the picture's red), the counts and "Show the flights". The list opens in the
// right pane at 1100 px and up and as its own view on a phone, inside the ash first, must-do first.
// A flight opens its own sheet; "Mark several handled…" ticks several, and each is still its own
// request and its own audit entry (AI_FAILURE_HANDLED) under the dispatcher's name.
//
// Code closes a failure that no longer stands (a draft now waits for the flight, it left the
// area, the replay run ended): the `ai_failure` event then carries `closed_at` and the flight
// leaves the list. Nobody is recorded as handling it.

import { PATHS, api, errorCode } from './api.js';
import { announce, byId, el, icon } from './dom.js';
import { hhmmz } from './format.js';
import { app } from './state.js';
import { openBSheet } from './ui.js';
import { toast } from './toast.js';
import { openBudget } from './budget.js';
import { renderDuty } from './duty.js';
import { WHY, machineText, reasonClass } from '../wall/x-parts.js';

const NOTE_MAX = 500;
const HANDLED_CHIPS = ['Contacted the flight by phone', 'Re-planned by hand', 'Flight already outside the area', 'Duplicate'];

const isOpen = (f) => !f.handled_at && !f.closed_at;
const plural = (n, word, many = `${word}s`) => `${n} ${n === 1 ? word : many}`;

// The Coordinator's must-do flights ("hex:volcano_id") in its newest run.
function mustDo() {
  const run = app.duty;
  if (!run || !Array.isArray(run.undispatched)) return new Set();
  return new Set(run.undispatched.map((id) => (run.worklist || []).find((i) => i.id === id)).filter((i) => i && i.kind === 'PLAN').map((i) => i.subject));
}

// One open failure per flight (the server keeps one; an older record is skipped here too): inside
// the ash first, must-do first inside each, then the soonest entry.
export function openFailures() {
  const byFlight = new Map();
  for (const f of app.failures.values()) {
    if (!isOpen(f)) continue;
    const had = byFlight.get(f.flight_id);
    if (!had || String(f.created_at) > String(had.created_at)) byFlight.set(f.flight_id, f);
  }
  const must = mustDo();
  return [...byFlight.values()].sort((a, b) => Number(b.inside_now) - Number(a.inside_now)
    || Number(must.has(b.flight_id)) - Number(must.has(a.flight_id)) || a.minutes_to_entry - b.minutes_to_entry);
}

const HELPER = { duty_officer: 'duty', planner: 'planner', drafter: 'drafter' };
const causeOf = (f) => `${HELPER[f.stage] || f.stage}|${reasonClass(f.reason)}`;
// "the assistant gave no result (timed out)" or, for a Coordinator that ran and did not hand the
// flight out, that (review H8). A quota refusal has no cause words here: the place says what is
// missing and what to do, and "Why ›" opens the assistant sheet, the one place that says why the
// step did not run (docs/UI-AI-QUIET.md 8.6). Null for a quota refusal.
function causeWords(cls) {
  if (cls === 'undone') return 'the Coordinator ran and left it for the Desk';
  if (cls === 'budget') return null;
  return `the assistant gave no result (${WHY[cls] || WHY.other})`;
}
const causeSentence = (cls, n) => (causeWords(cls) || '').replace(/left it for/, n === 1 ? 'left it for' : 'left them for');

// A few words per cause, for a row when the list mixes causes. A quota refusal says what happened,
// never "paused": the refusal may have been one skill's share while the assistant is on (8.6).
const SHORT = { budget: 'did not run', undone: 'left for the Desk', timeout: 'timed out', checks: 'failed the checks', error: 'stopped with an error', other: 'no answer' };

function causes(list) {
  const by = new Map();
  for (const f of list) {
    const k = causeOf(f);
    by.set(k, { cls: k.split('|')[1], n: (by.get(k)?.n || 0) + 1 });
  }
  return [...by.values()];
}

const ident = (f) => [f.callsign ? `proxy for ${f.callsign}` : null, f.type_icao].filter(Boolean).join(' · ');
const entryWords = (f) => (f.inside_now ? 'Inside the ash now' : `Enters in ${f.minutes_to_entry} min (when found, est.)`);
const entryShort = (f) => (f.inside_now ? 'inside now' : `in ${f.minutes_to_entry} min`);

export async function loadFailures() {
  const res = await api(PATHS.failures);
  if (res.ok && res.data && Array.isArray(res.data.failures)) {
    app.failures = new Map(res.data.failures.filter((f) => f && f.id && isOpen(f)).map((f) => [f.id, f]));
    renderFailures();
    app.hub.badges();
    app.hub.failuresChanged();
  }
}

// One announcement per batch, not one per flight (K84): the first says the whole group and why,
// later ones only the change; flights code took off the list are said together too.
let heard = 0;
let batch = 0;
let gone = [];
function announceBatch() {
  window.clearTimeout(batch);
  batch = window.setTimeout(() => {
    const list = openFailures();
    const n = list.length;
    const lines = [];
    if (n > heard) {
      const word = causeSentence(reasonClass(list[0].reason), n);
      lines.push(heard === 0 ? `${plural(n, 'flight')} to plan by hand${word ? `: ${word}` : ''}.` : `${plural(n - heard, 'more flight')} to plan by hand.`);
    }
    if (gone.length) lines.push(gone.length === 1 ? closedWords(gone[0]) : `${plural(gone.length, 'flight')} no longer ${gone.length === 1 ? 'needs' : 'need'} planning by hand.`);
    if (lines.length) announce(lines.join(' '));
    heard = n;
    gone = [];
  }, 800);
}

// Code's reasons for closing (desk/failures.py and the draft retirement rules), in words.
function closedWords(f) {
  const r = String(f.closed_reason || '');
  if (/DRAFT/.test(r)) return `${f.proxy_flight} no longer needs planning by hand: an advisory draft now waits for it.`;
  if (/POSITION LOST/.test(r)) return `${f.proxy_flight} left the list: its position has been lost for a while.`;
  if (/NO LONGER EXPOSED|NO LONGER ACTIVE/.test(r)) return `${f.proxy_flight} left the list: it is no longer in or heading into the ash.`;
  return `${f.proxy_flight} left the list.`;
}

export function onFailureEvent(f) {
  if (!f || typeof f !== 'object' || typeof f.id !== 'string') return;
  const had = app.failures.has(f.id);
  // A newer failure for a flight already listed replaces it in place: no new announcement.
  const listed = openFailures().some((x) => x.flight_id === f.flight_id);
  if (isOpen(f)) app.failures.set(f.id, f);
  else app.failures.delete(f.id);
  renderFailures();
  app.hub.badges();
  app.hub.failuresChanged();
  if (had && f.closed_at) gone.push(f);
  if ((!listed && isOpen(f)) || (had && f.closed_at)) announceBatch();
}

// --- Decide: the Plan by hand card -----------------------------------------------------------

function counts(list, must) {
  const inside = list.filter((f) => f.inside_now).length;
  const m = list.filter((f) => must.has(f.flight_id)).length;
  return [inside ? `${inside} inside the ash now` : null, list.length - inside ? `${list.length - inside} heading in` : null, m ? `${m} must do` : null].filter(Boolean).join(' · ');
}

// The cause once: one sentence for one cause, a short list when causes differ. A quota refusal says
// only what is missing and what to do; the card's "Why ›" opens the cause (8.6).
function causeBlock(list) {
  const cs = causes(list);
  const n = list.length;
  if (cs.length === 1) {
    const word = causeSentence(cs[0].cls, n);
    return [el('p', { class: 'hcard__why', text: word
      ? `No plan for ${n === 1 ? 'this flight' : 'these flights'}: ${word}. Nothing was substituted.`
      : `No advisory drafts for ${n === 1 ? 'this flight' : `these ${n} flights`}. Plan ${n === 1 ? 'it' : 'them'} by hand. Nothing was substituted.` })];
  }
  return [el('p', { class: 'hcard__why', text: 'No plan for these flights. Nothing was substituted.' }),
    el('ul', { class: 'hcard__causes' }, cs.map((c) => el('li', { text: `${plural(c.n, 'flight')}: ${causeSentence(c.cls, c.n) || 'the assistant did not run'}` })))];
}

function summaryCard(list, shown, must) {
  const n = list.length;
  return el('div', { class: 'hcard' },
    el('div', { class: 'hcard__head' },
      el('h2', { id: 'fail-title', class: 'hcard__title' }, icon('st-caution', 'st'), el('span', { text: `Plan by hand · ${plural(n, 'flight')}` })),
      el('button', { type: 'button', class: 'linkbtn hcard__whybtn', 'data-why': '1', 'aria-label': 'Why: open the TEPHRA Assistant sheet' }, el('span', { text: 'Why ›' }))),
    ...causeBlock(list),
    el('p', { class: 'hcard__counts', text: counts(list, must) }),
    el('button', { type: 'button', class: 'btn btn--outline hcard__go', 'data-failpane': 'open', 'aria-controls': 'fail-pane', 'aria-expanded': shown ? 'true' : 'false' },
      el('span', { text: shown ? `Showing the ${n === 1 ? 'flight' : 'flights'}` : n === 1 ? 'Show the flight' : `Show the ${n} flights` }), icon(shown ? 'i-check' : 'i-chevron-right')));
}

// --- the list (the right pane, or a phone's own view) ----------------------------------------

function row(f, mixed, must) {
  return el('li', { class: 'frow__item' },
    el('button', { type: 'button', class: 'frow', 'data-handle': f.id, 'aria-label': `${f.proxy_flight}, ${entryShort(f)}, ${f.volcano_name}${must ? ', must do' : ''}. Plan by hand.` },
      el('span', { class: 'frow__main' },
        el('span', { class: 'frow__flight', text: f.proxy_flight }),
        el('span', { class: 'frow__ident', text: ident(f) }),
        must ? el('span', { class: 'dcard__must', text: 'Must do' }) : null),
      el('span', { class: `frow__entry${f.inside_now ? ' is-inside' : ''}` },
        icon(f.inside_now ? 'st-inside' : 'i-clock', 'st'), el('span', { text: entryShort(f) })),
      el('span', { class: 'frow__meta', text: [f.volcano_name, `since ${hhmmz(f.created_at)}`, mixed ? SHORT[reasonClass(f.reason)] || SHORT.other : null].filter(Boolean).join(' · ') }),
      icon('i-chevron-right', 'icon frow__go')));
}

function group(title, items, mixed, key, must) {
  if (!items.length) return null;
  return el('section', { class: 'flgroup', 'aria-labelledby': `flg-${key}` },
    el('h3', { id: `flg-${key}`, class: 'flgroup__title' }, el('span', { text: title }), el('span', { class: 'flgroup__n', text: String(items.length) })),
    el('ul', { class: 'frows' }, items.map((f) => row(f, mixed, must.has(f.flight_id)))));
}

function paneBody(list, must) {
  const mixed = causes(list).length > 1;
  const raws = [...new Set(list.map((f) => `${machineText(f.reason)}${f.model_id && f.model_id !== 'stub' ? ` · would have used ${f.model_id}` : ''}`))];
  return [
    el('div', { class: 'fpane__head' },
      el('button', { type: 'button', class: 'linkbtn fpane__back', 'data-failpane': 'close' }, icon('i-chevron-left'), el('span', { text: 'Decide' })),
      el('h2', { id: 'fp-title', class: 'fpane__title', tabindex: '-1', text: `Plan by hand · ${plural(list.length, 'flight')}` })),
    el('div', { class: 'fcause', role: 'note' },
      icon('st-caution', 'st fcause__icon'),
      el('div', { class: 'fcause__body' }, ...causeBlock(list),
        // on a phone this list replaces Decide and its card: the cause is one tap from here too (8.6)
        el('p', { text: 'Decide each flight by hand, then mark it handled.' }),
        el('button', { type: 'button', class: 'linkbtn fcause__why', 'aria-label': 'Why: open the TEPHRA Assistant sheet', onclick: openBudget }, el('span', { text: 'Why ›' })),
        el('details', { class: 'tech' }, el('summary', { text: 'Technical detail' }), ...raws.map((r) => el('p', { class: 'mono tech__line', text: r }))))),
    el('div', { class: 'fpane__actions' },
      list.length > 1 ? el('button', { type: 'button', class: 'btn btn--outline', 'data-failbulk': '1', disabled: app.offline }, icon('i-hand'), el('span', { text: 'Mark several handled…' })) : null,
      el('p', { class: 'fine', text: 'Open a flight for its details. Each one is recorded on its own, under your name.' })),
    group('Inside the ash now', list.filter((f) => f.inside_now), mixed, 'inside', must),
    group('Heading in, soonest first', list.filter((f) => !f.inside_now), mixed, 'ahead', must),
  ];
}

// The Decide card and, while it is open, the list. `app.pane` says whether the list is open.
export function renderFailures() {
  const host = byId('fail-section');
  const pane = byId('fail-pane');
  if (!host || !pane) return;
  // the Coordinator card drops the must-do flights this list holds (K92)
  renderDuty();
  const list = openFailures();
  if (!list.length && app.pane === 'failures') app.hub.closeFailPane();
  const shown = app.pane === 'failures';
  host.hidden = list.length === 0;
  if (!list.length) heard = 0;
  const must = mustDo();
  // a redraw keeps focus on the card's own controls
  const had = host.contains(document.activeElement) ? (document.activeElement.dataset.failpane ? '[data-failpane]' : document.activeElement.dataset.why ? '[data-why]' : null) : null;
  host.replaceChildren(...(list.length ? [summaryCard(list, shown, must)] : []));
  if (had) host.querySelector(had)?.focus({ preventScroll: true });
  if (!host.dataset.wired) {
    host.dataset.wired = '1';
    host.addEventListener('click', (event) => {
      if (event.target.closest('[data-why]')) openBudget();
    });
  }
  if (!shown || !list.length) {
    pane.replaceChildren();
    return;
  }
  const keep = document.activeElement && pane.contains(document.activeElement) ? document.activeElement.dataset.handle || document.activeElement.dataset.failbulk || document.activeElement.id : null;
  const top = pane.scrollTop;
  pane.replaceChildren(...paneBody(list, must).filter(Boolean));
  pane.scrollTop = top;
  if (keep) {
    const again = pane.querySelector(`[data-handle="${CSS.escape(keep)}"], [data-failbulk="${CSS.escape(keep)}"], #${CSS.escape(keep)}`);
    if (again) again.focus({ preventScroll: true });
  }
}

// --- one flight -------------------------------------------------------------------------------

function noteField(id) {
  const area = el('textarea', { id, class: 'field', rows: '3', maxlength: String(NOTE_MAX), autocomplete: 'off', 'aria-describedby': `${id}-count` });
  const count = el('p', { id: `${id}-count`, class: 'counter', text: `0 / ${NOTE_MAX} · optional` });
  const chips = el('div', { class: 'reason-chips', role: 'group', 'aria-label': 'Quick notes (inserted into the text, still editable)' }, HANDLED_CHIPS.map((text) =>
    el('button', { type: 'button', class: 'reason-chip', onclick: () => {
      area.value = area.value ? `${area.value.replace(/[.\s]+$/, '')}. ${text}` : text;
      area.dispatchEvent(new Event('input'));
      area.focus();
    } }, icon('i-plus', 'icon reason-chip__add'), el('span', { text }))));
  area.addEventListener('input', () => {
    count.textContent = `${area.value.length} / ${NOTE_MAX} · optional`;
  });
  return { area, nodes: [el('label', { class: 'flabel', for: id, text: 'What did you do? (optional)' }), chips, area, count] };
}

const notSaved = (res) => (res.status === 404 ? 'it no longer exists' : res.status === 401 ? 'your session has ended, sign in again' : (res.data && res.data.detail) || errorCode(res) || `HTTP ${res.status}`);

export function openHandled(id) {
  const f = app.failures.get(id);
  if (!f) return;
  const note = noteField('handled-note');
  const msg = el('div', { class: 'field-msg', 'aria-live': 'polite' });
  const must = mustDo().has(f.flight_id);
  const facts = el('dl', { class: 'ffacts' },
    el('dt', { text: 'Where' }), el('dd', { class: f.inside_now ? 'is-inside' : null, text: entryWords(f) }),
    el('dt', { text: 'Aircraft' }), el('dd', { text: [ident(f) || 'no callsign', `hex ${String(f.hex || '').toUpperCase()}`].join(' · ') }),
    el('dt', { text: 'Volcano' }), el('dd', { text: f.volcano_name }),
    el('dt', { text: 'Since' }), el('dd', { text: hhmmz(f.created_at) }),
    el('dt', { text: 'What happened' }), el('dd', {}, el('span', { text: causeWords(reasonClass(f.reason)) ? `No plan for this flight: ${causeWords(reasonClass(f.reason))}. Nothing was put in its place.` : 'No advisory draft for this flight. Nothing was put in its place. ' }),
      causeWords(reasonClass(f.reason)) ? null : el('button', { type: 'button', class: 'linkbtn', 'aria-label': 'Why: open the TEPHRA Assistant sheet', onclick: openBudget }, el('span', { text: 'Why ›' })),
      must ? [' ', el('span', { class: 'dcard__must', text: 'Must do' })] : null));
  const tech = el('details', { class: 'tech' }, el('summary', { text: 'Technical detail' }),
    el('p', { class: 'mono tech__line', text: `${machineText(f.reason)}${f.model_id && f.model_id !== 'stub' ? ` · would have used ${f.model_id}` : ''}` }),
    el('p', { class: 'mono tech__line', text: `stage ${f.stage} · ${f.id} · cone ${f.cone_id}` }));
  const go = el('button', { type: 'button', class: 'btn btn--approve btn--block', disabled: app.offline },
    icon('i-check'), el('span', { text: `Mark ${f.proxy_flight} handled` }));
  const sheet = openBSheet({
    title: `Plan ${f.proxy_flight} by hand`,
    body: el('div', { class: 'stack' }, facts, tech,
      el('p', { class: 'note', text: 'Record what you did. The note goes in the audit log under your name.' }), ...note.nodes, msg),
    footer: go,
  });
  go.addEventListener('click', async () => {
    go.disabled = true;
    go.replaceChildren(el('span', { class: 'spinner', 'aria-hidden': 'true' }), el('span', { text: 'Saving…' }));
    const res = await api(PATHS.failureHandled(id), { method: 'POST', body: { note: note.area.value.trim() } });
    if (res.ok) {
      const rows = [...byId('fail-pane').querySelectorAll('[data-handle]')].map((b) => b.dataset.handle);
      const next = rows[rows.indexOf(id) + 1] || rows[rows.indexOf(id) - 1] || null;
      app.failures.delete(id);
      renderFailures();
      app.hub.badges();
      sheet.close();
      focusAfter(next);
      toast({ tone: 'ok', title: `${f.proxy_flight} marked handled. Recorded under ${app.me ? app.me.name : 'you'}.` });
      announce(`${f.proxy_flight} marked handled.`);
      return;
    }
    go.disabled = false;
    go.replaceChildren(icon('i-check'), el('span', { text: `Mark ${f.proxy_flight} handled` }));
    msg.replaceChildren(el('p', { class: 'msg msg--serious' }, icon('st-serious', 'st'), el('span', { text: `Not saved: ${notSaved(res)}.` })));
    if (res.status === 404) loadFailures();
  });
  window.setTimeout(() => note.area.focus(), 50);
}

// After a flight leaves the list, focus goes to the next one, else to the list's title, else to
// Decide's (the list closes when it is empty).
function focusAfter(id) {
  const next = id && byId('fail-pane').querySelector(`[data-handle="${CSS.escape(id)}"]`);
  const target = next || byId('fp-title') || byId('q-title');
  if (target && target.offsetParent !== null) target.focus({ preventScroll: !next });
  else byId('q-title')?.focus();
}

// --- several flights: the dispatcher ticks each one, and each is saved on its own ---------------

export function openBulk() {
  const list = openFailures();
  if (!list.length) return;
  const note = noteField('bulk-note');
  const msg = el('div', { class: 'field-msg', 'aria-live': 'polite' });
  const boxes = list.map((f) => el('input', { type: 'checkbox', id: `bulk-${f.id}`, value: f.id }));
  const all = el('input', { type: 'checkbox', id: 'bulk-all' });
  const go = el('button', { type: 'button', class: 'btn btn--approve btn--block', disabled: true });
  const chosen = () => boxes.filter((b) => b.checked && !b.disabled);
  const label = () => {
    const n = chosen().length;
    go.disabled = n === 0 || app.offline;
    go.replaceChildren(icon('i-check'), el('span', { text: n ? `Mark ${plural(n, 'flight')} handled` : 'Tick the flights you handled' }));
    const live = boxes.filter((b) => !b.disabled);
    all.checked = live.length > 0 && n === live.length;
    all.indeterminate = n > 0 && n < live.length;
  };
  all.addEventListener('change', () => {
    for (const b of boxes) if (!b.disabled) b.checked = all.checked;
    label();
  });
  for (const b of boxes) b.addEventListener('change', label);
  const must = mustDo();
  const rows = list.map((f, i) => el('li', { class: 'bulk__row' },
    boxes[i],
    el('label', { for: boxes[i].id, class: 'bulk__label' },
      el('span', { class: 'bulk__flight', text: f.proxy_flight }),
      el('span', { class: `bulk__entry${f.inside_now ? ' is-inside' : ''}`, text: entryShort(f) }),
      el('span', { class: 'bulk__meta', text: f.volcano_name }),
      must.has(f.flight_id) ? el('span', { class: 'dcard__must', text: 'Must do' }) : null),
    el('span', { class: 'bulk__state', 'data-state': '' })));
  const sheet = openBSheet({
    title: 'Mark flights handled',
    wide: true,
    body: el('div', { class: 'stack bulk' },
      el('p', { class: 'note', text: 'Tick each flight you have planned by hand. Each one is saved on its own, with the note below, under your name in the audit log.' }),
      el('fieldset', { class: 'bulk__set' },
        el('legend', { class: 'flabel', text: 'Flights' }),
        el('p', { class: 'bulk__all' }, all, el('label', { for: 'bulk-all', text: `All ${plural(list.length, 'flight')}` })),
        el('ul', { class: 'bulk__list' }, rows)),
      ...note.nodes, msg),
    footer: go,
  });
  label();
  go.addEventListener('click', async () => {
    const picked = chosen();
    if (!picked.length) return;
    go.disabled = true;
    let saved = 0;
    const failed = [];
    for (const [i, box] of picked.entries()) {
      go.replaceChildren(el('span', { class: 'spinner', 'aria-hidden': 'true' }), el('span', { text: `Saving ${i + 1} of ${picked.length}…` }));
      const f = app.failures.get(box.value);
      const state = box.closest('li').querySelector('.bulk__state');
      const res = await api(PATHS.failureHandled(box.value), { method: 'POST', body: { note: note.area.value.trim() } });
      if (res.ok) {
        saved += 1;
        app.failures.delete(box.value);
        box.checked = false;
        box.disabled = true;
        state.replaceChildren(icon('i-check', 'st'), el('span', { text: 'Saved' }));
        state.dataset.state = 'ok';
      } else {
        failed.push(`${f ? f.proxy_flight : box.value} (${notSaved(res)})`);
        state.replaceChildren(icon('st-serious', 'st'), el('span', { text: 'Not saved' }));
        state.dataset.state = 'bad';
        if (res.status === 401) break;
      }
    }
    renderFailures();
    app.hub.badges();
    label();
    const who = app.me ? app.me.name : 'you';
    if (!failed.length) {
      sheet.close();
      focusAfter(null);
      toast({ tone: 'ok', title: `${plural(saved, 'flight')} marked handled. Each is recorded under ${who}.` });
      announce(`${plural(saved, 'flight')} marked handled.`);
      return;
    }
    msg.replaceChildren(el('p', { class: 'msg msg--serious' }, icon('st-serious', 'st'),
      el('span', { text: `${saved ? `${plural(saved, 'flight')} saved. ` : ''}Not saved: ${failed.join(', ')}.` })));
    announce(`${failed.length} not saved.`);
    loadFailures();
  });
}
