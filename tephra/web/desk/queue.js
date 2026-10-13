// Decide, the inbox (Desk redesign 5.2; docs/UI-REDESIGN.md R10.4). One count; the lead card, the
// advisory code says must be decided first (act-by order, format.js byActBy); Plan by hand
// (failures.js) directly under it; then one-line rows in deadline groups: Before entry (act-by),
// Keep watching (inside now, keep watching or continue: no clock), Other decisions (the airport
// plan, documents to sign, messages not tied to a flight), and the advisories decided since the
// page opened. The lead card never swaps under the thumb: a more urgent arrival shows "More
// urgent: … · Show" instead. Code sets the order; the Coordinator's order is only a note.

import { byId, el, icon } from './dom.js';
import {
  actBy,
  actionShort,
  activeNow,
  band,
  byActBy,
  deskName,
  entryLead,
  entryShort,
  entryState,
  fl,
  hhmmz,
  isStub,
  parseTime,
  pct,
  timeCell,
  watchOnly,
} from './format.js';
import { openFailures } from './failures.js';
import { aiMark } from './ui.js';
import { recordedWords } from '../wall/x-parts.js';
import { crewFlag, crewKey } from './crew.js';
import { KIND, draftMessages } from './messages.js';
import { docsToSign } from './docs.js';
import { draftPlans, latestPlan } from './network.js';
import { app, draftList, setAsideCount } from './state.js';

const OLD_DRAFT_MIN = 10;
const SOON_MIN = 10;
const ROWS_FIRST = 5;
const WATCH_FIRST = 3;
const NEW_TAG_MS = 120000;
const CLOSED_MAX = 8;
let showAllRows = false;
let showAllWatch = false;

export function showAllDrafts() {
  showAllRows = true;
  renderQueue();
}

export function showAllWatching() {
  showAllWatch = true;
  renderQueue();
}

export function coneFor(adv) {
  return app.cones.get(adv.cone_id) || null;
}

export function needsCarefulRead(adv) {
  return (adv.validation_notes || []).some((n) => typeof n === 'string' && n.startsWith('NEEDS_HUMAN'));
}

export const anyStaleSource = (adv) => (adv.sources || []).some((s) => s && s.stale);

// The flight's level now, from the Wall's aircraft layer (ADS-B alt_baro); null when not tracked.
export function levelNow(adv) {
  const p = (app.aircraft || []).find((a) => a.hex === adv.hex);
  return p && Number.isFinite(p.alt_baro_ft) ? Math.round(p.alt_baro_ft / 100) : null;
}

// The area words with the area's data swatch (5.3, 8): pink official, amber TEPHRA estimate.
export function modeChip(adv) {
  const conf = pct(adv.confidence);
  const parts = {
    OFFICIAL: [['official', 'official area only']],
    WIDENED: [['official', 'official'], ['tephra', 'TEPHRA estimate']],
    HYPOTHESIS: [['tephra', 'TEPHRA estimate only (HYPOTHESIS)']],
  }[adv.plume_mode] || [['tephra', String(adv.plume_mode || '')]];
  return el('span', { class: 'areaw', title: `TEPHRA area for this draft: ${adv.plume_mode}${conf ? ` ${conf}` : ''}${isStub(adv) ? ', set by code with TEPHRA Assistant off' : ''}` },
    parts.map(([kind, words], i) => [i ? el('span', { class: 'areaw__plus', text: ' + ' }) : null,
      el('span', { class: 'areaw__part' }, el('i', { class: `swatch swatch--${kind}`, 'aria-hidden': 'true' }), el('span', { text: words }))]));
}

function ageMinutes(adv, now) {
  const created = parseTime(adv.created_at);
  return now === null || created === null ? 0 : (now - created) / 60000;
}

// What needs the dispatcher's care, said on the item it affects: [shape, words, short word].
function cautions(adv) {
  const out = [];
  const flag = crewFlag(adv);
  if (flag) out.push(['i-pin', flag.line || 'Crew report of ash on this route', 'crew report']);
  if (adv.plume_mode === 'HYPOTHESIS') out.push(['st-caution', 'HYPOTHESIS: only Keep watching or Hold', 'hypothesis']);
  if (needsCarefulRead(adv)) out.push(['st-caution', 'Needs a careful read', 'read carefully']);
  if (anyStaleSource(adv)) out.push(['st-stale', 'Sources stale', 'sources stale']);
  return out;
}

const plural = (n, word, many = `${word}s`) => `${n} ${n === 1 ? word : many}`;
const langs = (m) => m.texts.map((t) => String(t.language || '').toUpperCase()).join(' · ');

// --- the walk order and the one count ---------------------------------------------------------

// Every advisory in the order Decide lists them and the review's "Next" walks them.
export const walkOrder = () => draftList().sort(byActBy);

// The advisory a message is about, when it is still on this page (a draft, or decided here).
function sourceAdvisory(m) {
  if (m.source_kind !== 'advisory' || !m.flight_no) return null;
  const pool = [...app.drafts.values(), ...app.closed.values()].filter((a) => a.proxy_flight === m.flight_no);
  return pool.sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))[0] || null;
}
const flightActBy = (m) => {
  const adv = sourceAdvisory(m);
  return adv && !watchOnly(adv) ? actBy(adv) : null;
};

// The one number (5.2, A11): every item on Decide that needs a person. The h1, the tab badge and
// the page title all read it.
export function waitingCount() {
  const advisories = draftList().length;
  const hand = openFailures().length;
  const messages = draftMessages().length;
  const plans = draftPlans().length;
  const docs = docsToSign().length;
  return { n: advisories + hand + messages + plans + docs, advisories, hand, messages, plans, docs };
}

// "23 advisories · 3 messages · 2 flights to plan by hand · 1 airport plan · 1 document to sign"
export function breakdownText() {
  const c = waitingCount();
  return [
    plural(c.advisories, 'advisory', 'advisories'),
    c.hand ? `${plural(c.hand, 'flight')} to plan by hand` : '',
    c.messages ? plural(c.messages, 'message') : '',
    c.plans ? plural(c.plans, 'airport plan') : '',
    c.docs ? `${plural(c.docs, 'document')} to sign` : '',
  ].filter(Boolean).join(' · ');
}

function countLine(items) {
  const c = waitingCount();
  if (!c.n) return '';
  if (c.hand) return `${c.n} waiting · ${plural(c.advisories, 'advisory', 'advisories')} · ${plural(c.hand, 'flight')} to plan by hand`;
  const now = activeNow();
  const soon = items.filter((a) => {
    const k = actBy(a);
    return k !== null && (now === null ? a.minutes_to_entry <= SOON_MIN : k - now <= SOON_MIN * 60000);
  }).length;
  return `${c.n} waiting${soon ? ` · ${soon} due in ${SOON_MIN} min` : ''}`;
}

function asideLine() {
  const aside = setAsideCount();
  if (!aside) return '';
  const other = app.state && app.state.mode === 'REPLAY' ? 'live' : 'replay';
  return `${plural(aside, `${other} draft`)} set aside until ${other === 'live' ? 'live feeds play' : 'that replay plays'} again`;
}

// --- the lead card ----------------------------------------------------------------------------

const factsText = (adv, now) => {
  const lvl = levelNow(adv);
  return [adv.volcano_name || adv.volcano_id, lvl !== null ? `now ${fl(lvl)}` : null, entryLead(adv, now)].filter(Boolean).join(' · ');
};

function timeNode(adv, now) {
  const tc = timeCell(adv, now);
  return el('span', { class: `tcell${tc.soon ? ' is-soon' : ''}`, 'data-slot': 'time', text: tc.text });
}

function staleLine(adv, now) {
  const age = ageMinutes(adv, now);
  return age > OLD_DRAFT_MIN ? `Drafted ${Math.floor(age)} min ago: entry time may have moved.` : '';
}

function buildLead(adv) {
  const now = activeNow();
  const who = [adv.proxy_flight, adv.callsign].filter(Boolean).join(' · ');
  const writer = [aiMark(undefined, isStub(adv) ? null : adv.model_id)];
  if (adv.recorded_answer && !isStub(adv)) writer.push(el('span', { text: ` ${recordedWords(adv.recorded_answer)}.` }));
  return el('article', { class: 'lead next__card', 'data-id': adv.id, 'data-version': String(adv.version), 'data-band': band(coneFor(adv)), 'data-crewkey': crewKey(adv), 'data-level': String(levelNow(adv)), 'aria-labelledby': 'next-flight next-action' },
    el('p', { class: 'lead__top' }, el('span', { class: 'lead__who', id: 'next-flight', text: who }), timeNode(adv, now)),
    el('h3', { class: 'lead__action', id: 'next-action', text: actionShort(adv) }),
    el('p', { class: 'lead__facts', 'data-slot': 'facts', text: factsText(adv, now) }),
    ...cautions(adv).map(([shape, words]) => el('p', { class: 'lead__caution' }, icon(shape, 'st'), el('span', { text: words }))),
    el('p', { class: 'lead__stale', 'data-slot': 'stale', text: staleLine(adv, now) }),
    el('p', { class: 'lead__by' }, ...writer),
    el('button', { type: 'button', class: 'btn btn--cta next__go', 'data-open': adv.id },
      el('span', { text: `Review ${adv.proxy_flight}` }), icon('i-chevron-right')));
}

// --- rows -------------------------------------------------------------------------------------

const timeWords = (adv, now) => {
  if (watchOnly(adv)) return 'inside the ash now';
  if (adv.inside_now) return 'inside the ash now, act now';
  const st = entryState(adv, now);
  return st.kind === 'ahead' ? `enters in ${plural(st.minutes, 'minute')}` : 'entry due now';
};

function advRow(adv) {
  const now = activeNow();
  const watch = watchOnly(adv);
  const lvl = levelNow(adv);
  const main = watch ? [lvl !== null ? fl(lvl) : null, adv.volcano_name].filter(Boolean).join(' · ') || 'Keep watching' : actionShort(adv);
  const marks = cautions(adv);
  const sentence = `${adv.proxy_flight}, ${main.toLowerCase().replace(/\bfl(\d)/g, 'FL$1')}, ${timeWords(adv, now)}${marks.length ? `. ${marks.map((m) => m[1]).join('. ')}` : ''}. Review.`;
  const extra = [adv.callsign, watch ? null : adv.volcano_name, watch || lvl === null ? null : fl(lvl)].filter(Boolean).join(' · ');
  const button = el('button', { type: 'button', class: 'card irow', 'data-open': adv.id, 'aria-label': sentence },
    el('span', { class: 'irow__who', 'aria-hidden': 'true', text: adv.proxy_flight }),
    el('span', { class: 'irow__main', 'aria-hidden': 'true' },
      el('span', { class: 'irow__text', text: main }),
      extra ? el('span', { class: 'irow__extra', text: ` · ${extra}` }) : null),
    marks.length ? el('span', { class: 'irow__flag', 'aria-hidden': 'true', title: marks.map((m) => m[1]).join('. ') }, icon(marks[0][0], 'st')) : null,
    el('span', { class: 'irow__new', 'data-slot': 'new', 'aria-hidden': 'true', hidden: true }),
    el('span', { 'aria-hidden': 'true' }, timeNode(adv, now)),
    icon('i-chevron-right', 'icon irow__go'));
  return el('li', { class: 'cards__item', 'data-id': adv.id, 'data-key': `${adv.id}|${adv.version}|${crewKey(adv)}|${lvl}` }, button);
}

// One row for something that is not an advisory: subject, words, its state word ("to approve").
function itemRow({ key, who = '', text, state, attrs, label }) {
  return el('li', { class: 'cards__item', 'data-id': key, 'data-key': `${key}|${who}|${text}|${state}` },
    el('button', { type: 'button', class: 'card irow', 'aria-label': label, ...attrs },
      el('span', { class: 'irow__who', 'aria-hidden': 'true', text: who }),
      el('span', { class: 'irow__main', 'aria-hidden': 'true' }, el('span', { class: 'irow__text', text })),
      el('span', { 'aria-hidden': 'true' }, el('span', { class: 'tcell', text: state })),
      icon('i-chevron-right', 'icon irow__go')));
}

const msgRow = (m) => {
  const words = `${(KIND[m.kind] || [m.kind])[0]} · ${langs(m)}`;
  return itemRow({ key: m.id, who: m.flight_no || '', text: words, state: 'to approve', attrs: { 'data-msg': m.id },
    label: `${m.flight_no ? `${m.flight_no}, ` : ''}${words.replace(' · ', ' in ')}, to approve. Open.` });
};

// Rebuilds a list from keyed rows, keeping the nodes that did not change (focus stays put).
function reconcile(list, rows) {
  const wanted = new Map(rows.map((r) => [r.dataset.id, r]));
  for (const li of [...list.children]) {
    if (!wanted.has(li.dataset.id) && !li.classList.contains('is-leaving')) leave(li);
  }
  rows.forEach((row, index) => {
    let li = [...list.children].find((c) => c.dataset.id === row.dataset.id && !c.classList.contains('is-leaving'));
    if (!li || li.dataset.key !== row.dataset.key) {
      const focused = li && li.contains(document.activeElement);
      if (li) li.replaceWith(row);
      li = row;
      if (focused) li.querySelector('button').focus({ preventScroll: true });
    }
    const live = [...list.children].filter((c) => !c.classList.contains('is-leaving'));
    if (live[index] !== li) list.insertBefore(li, live[index] || null);
  });
}

function markSelected(list) {
  for (const li of list.children) {
    const b = li.querySelector('[data-open]');
    if (!b) continue;
    if (b.dataset.open === app.selectedId) b.setAttribute('aria-current', 'true');
    else b.removeAttribute('aria-current');
    li.classList.toggle('is-busy', app.inFlight.has(b.dataset.open));
  }
}

// --- live values ------------------------------------------------------------------------------

// The time cells, the lead card's facts and its draft age; runs every 15 s.
export function updateTimes() {
  const now = activeNow();
  const lead = byId('q-next').querySelector('.lead');
  const leadAdv = lead && app.drafts.get(lead.dataset.id);
  if (leadAdv) {
    lead.querySelector('[data-slot="time"]').replaceWith(timeNode(leadAdv, now));
    lead.querySelector('[data-slot="facts"]').textContent = factsText(leadAdv, now);
    lead.querySelector('[data-slot="stale"]').textContent = staleLine(leadAdv, now);
  }
  for (const li of document.querySelectorAll('#cards > li, #watch-list > li')) {
    const adv = app.drafts.get(li.dataset.id);
    if (!adv) continue;
    const cell = li.querySelector('[data-slot="time"]');
    if (cell) cell.replaceWith(timeNode(adv, now));
    const arrived = app.arrivedAt.get(adv.id);
    const fresh = arrived !== undefined && performance.now() - arrived < NEW_TAG_MS;
    const tag = li.querySelector('[data-slot="new"]');
    if (tag) tag.hidden = !fresh;
  }
}

function skeleton() {
  const item = () =>
    el('li', { class: 'cards__item skeleton', 'aria-hidden': 'true' },
      el('span', { class: 'sk sk--a' }), el('span', { class: 'sk sk--b' }));
  return [item(), item(), item()];
}

// --- render -----------------------------------------------------------------------------------

let nextId = null;
export const nextDraftId = () => nextId;

export function showMostUrgent() {
  const items = walkOrder();
  nextId = items[0] ? items[0].id : null;
  renderQueue();
}

function groupHead(node, title, n, extra = '') {
  node.textContent = `${title} · ${n}${extra}`;
  node.hidden = false;
}

function renderWatch(items) {
  const host = byId('watch-section');
  host.hidden = items.length === 0;
  if (!items.length) {
    host.replaceChildren();
    showAllWatch = false;
    return;
  }
  let head = byId('watch-title');
  let list = byId('watch-list');
  let foot = host.querySelector('.grp__foot');
  if (!list) {
    head = el('h2', { id: 'watch-title', class: 'ghead' });
    list = el('ul', { id: 'watch-list', class: 'cards irows', 'aria-labelledby': 'watch-title' });
    foot = el('p', { class: 'grp__foot' });
    host.replaceChildren(head, list, foot);
  }
  groupHead(head, 'Keep watching', items.length, ' inside now');
  reconcile(list, items.map(advRow));
  markSelected(list);
  const capped = !showAllWatch && items.length > WATCH_FIRST + 1;
  [...list.children].forEach((li, i) => {
    li.hidden = capped && i >= WATCH_FIRST && li.dataset.id !== app.selectedId;
  });
  const hadFocus = foot.contains(document.activeElement) ? document.activeElement.dataset.watch : null;
  foot.replaceChildren(...[
    capped ? el('button', { type: 'button', class: 'linkbtn', 'data-watch': 'all' }, el('span', { text: `Show all ${items.length}` })) : null,
    el('button', { type: 'button', class: 'linkbtn', 'data-watch': 'one', 'data-open': items[0].id }, el('span', { text: 'Review one by one' }), icon('i-chevron-right')),
  ].filter(Boolean));
  if (hadFocus) foot.querySelector(`[data-watch="${hadFocus}"]`)?.focus({ preventScroll: true });
}

function renderOther(flightless) {
  const host = byId('other-section');
  const planHost = byId('plan-section');
  const msgs = byId('msg-section');
  const plans = draftPlans();
  const docs = docsToSign();
  const n = plans.length + docs.length + flightless.length;
  host.hidden = n === 0;
  groupHead(byId('other-title'), 'Other decisions', n);
  // the plan row names the plan it opens: an older draft is not the newest plan (K94)
  planHost.hidden = plans.length === 0;
  const latest = latestPlan();
  planHost.replaceChildren(...plans.slice(0, 1).map((p) => {
    const closed = (p.closures || []).length;
    const name = latest && latest.id !== p.id ? `Earlier airport plan ${hhmmz(p.created_at)}` : 'Airport plan';
    const text = `${name} · ${plural(closed, 'airport')} closed`;
    return el('button', { type: 'button', class: 'card irow', id: 'plan-title', 'data-goto': 'network', 'aria-label': `${text}, to approve. Opens Airports.` },
      el('span', { class: 'irow__main irow__main--wide', 'aria-hidden': 'true' }, el('span', { class: 'irow__text', text })),
      el('span', { 'aria-hidden': 'true' }, el('span', { class: 'tcell', text: 'to approve' })),
      icon('i-chevron-right', 'icon irow__go'));
  }));
  const docRows = planHost.parentElement;
  for (const li of docRows.querySelectorAll('.irow-doc')) li.remove();
  for (const d of docs) {
    docRows.append(el('li', { class: 'irow-doc' },
      el('button', { type: 'button', class: 'card irow', 'data-goto': 'docs', 'aria-label': `${d.title}, to sign. Opens Paperwork.` },
        el('span', { class: 'irow__main irow__main--wide', 'aria-hidden': 'true' }, el('span', { class: 'irow__text', text: d.title })),
        el('span', { 'aria-hidden': 'true' }, el('span', { class: 'tcell', text: 'to sign' })),
        icon('i-chevron-right', 'icon irow__go'))));
  }
  msgs.hidden = flightless.length === 0;
  reconcile(msgs, flightless.map(msgRow));
}

export function renderQueue() {
  const list = byId('cards');
  const stateBox = byId('q-state');
  const slot = byId('q-next');
  const items = walkOrder();
  const n = items.length;
  if (!nextId || !app.drafts.has(nextId) || !items.some((a) => a.id === nextId)) nextId = items[0] ? items[0].id : null;
  const lead = nextId ? app.drafts.get(nextId) : null;
  const position = lead ? items.indexOf(lead) + 1 : 0;
  byId('q-count').textContent = app.listLoaded ? countLine(items) : '';
  byId('q-breakdown').textContent = app.listLoaded ? asideLine() : '';
  const newer = byId('q-newer');
  newer.hidden = !(lead && position > 1);
  if (!newer.hidden) {
    const top = items[0];
    newer.replaceChildren(el('span', { text: `More urgent: ${top.proxy_flight} · ${entryShort(top, activeNow())}` }),
      el('button', { type: 'button', class: 'linkbtn', 'data-newest': '1' }, el('span', { text: 'Show' })));
  }

  if (!app.listLoaded && !app.listError) {
    stateBox.replaceChildren(el('p', { class: 'qstate__loading', text: 'Loading drafts…' }));
    if (!list.querySelector('.skeleton')) list.replaceChildren(...skeleton());
    slot.replaceChildren();
    byId('more-title').hidden = true;
    return;
  }
  for (const sk of list.querySelectorAll('.skeleton')) sk.remove();

  if (app.listError) {
    stateBox.replaceChildren(
      el('div', { class: 'panel panel--serious', role: 'status' },
        el('p', { class: 'panel__title' }, icon('st-serious', 'st'), el('span', { text: "Can't load drafts." })),
        el('details', { class: 'tech' }, el('summary', { text: 'Technical detail' }), el('p', { class: 'mono tech__line', text: app.listError })),
        el('button', { type: 'button', class: 'btn btn--outline', 'data-retry': '1' }, icon('i-refresh'), el('span', { text: 'Try again' }))),
    );
  } else if (n === 0) {
    const last = app.lastLoadedAt === null ? '' : ` Last update ${hhmmz(app.lastLoadedAt)}.`;
    // no "all clear" while flights wait to be planned by hand (H9)
    const hand = openFailures().length;
    stateBox.replaceChildren(
      el('div', { class: 'panel panel--empty' },
        el('p', { class: 'panel__title' }, icon(hand ? 'st-info' : 'i-check', hand ? 'st is-info' : 'st'), el('span', { text: hand ? 'No drafts to approve.' : 'Nothing waits for you.' })),
        el('p', { text: hand ? `${plural(hand, 'flight')} wait${hand === 1 ? 's' : ''} in Plan by hand.${last}` : `A draft appears here when a flight's projected track enters TEPHRA's estimated ash area.${last}` })),
    );
  } else {
    stateBox.replaceChildren();
  }

  // The lead card: rebuilt only when its advisory changed.
  const shown = slot.querySelector('.lead');
  if (!lead) slot.replaceChildren();
  else if (!shown || shown.dataset.id !== lead.id || Number(shown.dataset.version) !== lead.version || shown.dataset.band !== band(coneFor(lead)) || shown.dataset.crewkey !== crewKey(lead) || shown.dataset.level !== String(levelNow(lead))) {
    const hadFocus = shown && shown.contains(document.activeElement);
    slot.replaceChildren(buildLead(lead));
    if (hadFocus) slot.querySelector('.next__go').focus({ preventScroll: true });
  }
  const card = slot.querySelector('.lead');
  if (card) card.classList.toggle('is-current', lead.id === app.selectedId);

  // Before entry: the advisories with an act-by, and the messages for a flight still heading in.
  const rest = items.filter((a) => a.id !== nextId);
  const before = rest.filter((a) => !watchOnly(a));
  const watching = rest.filter(watchOnly);
  const msgs = draftMessages();
  const tied = msgs.filter((m) => flightActBy(m) !== null);
  const flightless = msgs.filter((m) => flightActBy(m) === null).sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)));
  const entries = [
    ...before.map((a) => ({ k: actBy(a), t: a.created_at, row: () => advRow(a), id: a.id })),
    ...tied.map((m) => ({ k: flightActBy(m), t: m.created_at, row: () => msgRow(m), id: m.id })),
  ].sort((x, y) => x.k - y.k || String(x.t).localeCompare(String(y.t)));
  const head = byId('more-title');
  head.hidden = entries.length === 0;
  if (entries.length) groupHead(head, 'Before entry', entries.length);
  reconcile(list, entries.map((e) => e.row()));
  markSelected(list);
  const capped = !showAllRows && entries.length > ROWS_FIRST + 1;
  [...list.children].forEach((li, i) => {
    li.hidden = capped && i >= ROWS_FIRST && li.dataset.id !== app.selectedId;
  });
  const allBtn = byId('cards-all');
  allBtn.hidden = !capped;
  if (capped) allBtn.querySelector('span').textContent = `Show all ${entries.length}`;

  renderWatch(watching);
  renderOther(flightless);
  updateTimes();
  renderClosed();
}

// A row leaves over --dur-3 (instantly under reduced motion).
function leave(li) {
  const focused = li.contains(document.activeElement);
  li.classList.add('is-leaving');
  li.style.setProperty('--h', `${li.offsetHeight}px`);
  const done = () => li.remove();
  li.addEventListener('animationend', done, { once: true });
  window.setTimeout(done, 400);
  if (focused) app.hub.focusQueueTitle();
}

// Marks a row as just arrived: a dot for two minutes, never a colour.
export function flashNew(id) {
  app.arrivedAt.set(id, performance.now());
  updateTimes();
}

const STATUS_VIEW = {
  APPROVED: ['i-approved', 'Approved', 'ok'],
  EDITED: ['i-approved', 'Approved with edits', 'ok'],
  REJECTED: ['i-rejected', 'Rejected', 'serious'],
  SUPERSEDED: ['i-superseded', 'Replaced by a newer draft', 'off'],
  DRAFT: ['i-clock', 'Awaiting dispatcher', 'neutral'],
};

export const statusView = (adv) => STATUS_VIEW[adv.status] || STATUS_VIEW.DRAFT;

export function statusBadge(adv) {
  const [shape, word, tone] = STATUS_VIEW[adv.status] || STATUS_VIEW.DRAFT;
  return el('span', { class: `adv-status adv-status--${tone}` }, icon(shape, 'st'), el('span', { text: word }));
}

export function decidedLine(adv) {
  const when = hhmmz(adv.decided_at || adv.updated_at);
  if (adv.status === 'SUPERSEDED') return `by TEPHRA at ${when}`;
  const who = deskName(adv.decided_by);
  return `${who ? `by ${who} ` : ''}at ${when}`;
}

function renderClosed() {
  const section = byId('closed');
  const list = byId('closed-list');
  const items = [...app.closed.values()]
    .sort((a, b) => (parseTime(b.updated_at) ?? 0) - (parseTime(a.updated_at) ?? 0))
    .slice(0, CLOSED_MAX);
  section.hidden = items.length === 0;
  byId('closed-title').textContent = app.pageOpenedAt === null ? 'Decided since this page opened' : `Decided since ${hhmmz(app.pageOpenedAt)}`;
  byId('closed-count').textContent = `· ${app.closed.size}`;
  list.replaceChildren(
    ...items.map((adv) =>
      el('li', {},
        el('button', { type: 'button', class: 'closed__item', 'data-open': adv.id, 'aria-current': adv.id === app.selectedId ? 'true' : null },
          statusBadge(adv),
          el('span', { class: 'closed__what' },
            el('span', { class: 'closed__flight', text: adv.proxy_flight }),
            el('span', { text: ` ${actionShort(adv)}` })),
          el('span', { class: 'closed__when', text: decidedLine(adv) }))),
    ),
  );
}
