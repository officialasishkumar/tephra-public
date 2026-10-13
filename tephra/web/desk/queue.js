// Decide (docs/UI-REDESIGN.md R10.4, was the Queue): the Next decision card first, then one
// line per other draft, most urgent first, and the advisories that left DRAFT while this page was
// open (collapsed).

import { byId, el, icon } from './dom.js';
import {
  ACTION_ICON,
  actionPlain,
  actionShort,
  activeNow,
  ago,
  band,
  byUrgency,
  deskName,
  entryShort,
  entryState,
  entryWords,
  hhmmz,
  isStub,
  parseTime,
  pct,
  sourcesSummary,
} from './format.js';
import { openFailures } from './failures.js';
import { aiMark } from './ui.js';
import { crewFlag, crewKey } from './crew.js';
import { draftMessages } from './messages.js';
import { app, draftList, setAsideCount } from './state.js';

const OLD_DRAFT_MIN = 10;
const ROWS_FIRST = 5;
let showAllRows = false;

export function showAllDrafts() {
  showAllRows = true;
  renderQueue();
}
const NEW_TAG_MS = 120000;
const CLOSED_MAX = 8;

export function coneFor(adv) {
  return app.cones.get(adv.cone_id) || null;
}

export function needsCarefulRead(adv) {
  return (adv.validation_notes || []).some((n) => typeof n === 'string' && n.startsWith('NEEDS_HUMAN'));
}

export const anyStaleSource = (adv) => (adv.sources || []).some((s) => s && s.stale);

// On a card the chip carries a visible "Area" prefix so "OFFICIAL 100%" is not read as a
// certainty score; in the review the row label already says "TEPHRA area" (bare).
export function modeChip(adv, { long = false, bare = false } = {}) {
  const shape = { OFFICIAL: 'lg-area-official', WIDENED: 'lg-area-hatch', HYPOTHESIS: 'lg-area-hatch' }[adv.plume_mode];
  // Plain words (review 2, item 5); the mode code and confidence stay in the tooltip.
  const conf = pct(adv.confidence);
  const words = {
    OFFICIAL: 'Official area only',
    WIDENED: `Wider than the official area${conf ? ` · ${conf} confidence` : ''}`,
    HYPOTHESIS: long ? 'HYPOTHESIS · MONITOR or HOLD only' : 'HYPOTHESIS',
  }[adv.plume_mode] || String(adv.plume_mode || '');
  return el(
    'span',
    { class: `chip chip--mode chip--${String(adv.plume_mode || '').toLowerCase()}`, title: `TEPHRA cautious area for this draft (${adv.plume_mode}${conf ? ` ${conf}` : ''}${isStub(adv) ? ', set by code with AI off' : ''})` },
    icon(shape, 'st'),
    bare ? null : el('span', { class: 'caps chip__k', text: 'Area' }),
    el('span', { text: words }),
  );
}

export function replayChip() {
  return el('span', { class: 'chip chip--replay' }, icon('i-replay', 'st'), el('span', { text: 'REPLAY' }));
}

// The entry status in words, with its shape (R12.10): "Inside the ash now", "Enters in 12 min
// (est.)". Computed by code from the draft's created_at and minutes_to_entry.
function entryNode(adv, now) {
  const st = entryState(adv, now);
  const tone = st.kind === 'inside' ? 'inside' : st.kind === 'due' ? 'due' : 'ahead';
  return el('span', { class: `entry entry--${tone}` },
    icon(st.kind === 'inside' ? 'st-inside' : st.kind === 'due' ? 'st-caution' : 'i-clock', 'st'),
    el('span', { text: entryWords(adv, now) }));
}

function ageMinutes(adv, now) {
  const created = parseTime(adv.created_at);
  return now === null || created === null ? 0 : (now - created) / 60000;
}

// Only what needs the dispatcher's care stays on the card (R10.4): the area mode, model and
// REPLAY chips moved to the header and the review's "Why". HYPOTHESIS is a safety rule, so it stays.
// Each caution: [shape, the card's words, the row's short word]. A row shows the short word next
// to its shape, never a bare icon (review 1, item 15).
function cautions(adv, now) {
  const out = [];
  // A crew report of ash on the route comes first: it is the newest evidence and needs a reason
  // to keep the flight on its route (UI-DESIGN 10.15).
  const flag = crewFlag(adv);
  if (flag) out.push(['i-pin', flag.line || 'Crew report of ash on this route', 'crew report']);
  if (adv.plume_mode === 'HYPOTHESIS') out.push(['st-caution', 'HYPOTHESIS: only MONITOR or HOLD', 'hypothesis']);
  if (needsCarefulRead(adv)) out.push(['st-caution', 'Needs a careful read', 'read carefully']);
  if (anyStaleSource(adv)) out.push(['st-stale', 'Sources stale', 'sources stale']);
  const age = ageMinutes(adv, now);
  if (age > OLD_DRAFT_MIN) out.push(['i-clock', `Drafted ${Math.floor(age)} min ago: entry time may have moved`, `${Math.floor(age)} min old`]);
  return out;
}

// The row's caution: the most important one's shape and short word, "+n" for the rest.
function rowMark(marks) {
  if (!marks.length) return null;
  const all = marks.map((m) => m[1]).join('. ');
  return el('span', { class: 'row__mark', title: all },
    icon(marks[0][0], 'st'),
    el('span', { class: 'row__markword', 'aria-hidden': 'true', text: `${marks[0][2]}${marks.length > 1 ? ` +${marks.length - 1}` : ''}` }),
    el('span', { class: 'sr-only', text: all }));
}

function tagsNode(adv, now) {
  const list = cautions(adv, now);
  return el('span', { class: 'tags' }, list.map(([shape, word]) =>
    el('span', { class: 'chip chip--caution' }, icon(shape, 'st'), el('span', { text: word }))));
}

// Who wrote the text, as a mark (the model id in its title) and the instruction (K86).
const writerLine = (adv) => [aiMark('AI-written', isStub(adv) ? null : adv.model_id),
  el('span', { text: ` ${adv.recorded_answer && !isStub(adv) ? `${adv.recorded_answer}. ` : ''}Check the sources first.` })];

const identText = (adv) => {
  const bits = [adv.callsign ? `proxy for ${adv.callsign}` : 'proxy, no callsign'];
  if (adv.type_icao) bits.push(adv.type_icao);
  return bits.join(' · ');
};

function metaText(adv, now) {
  const created = parseTime(adv.created_at);
  const age = now === null || created === null ? `at ${hhmmz(adv.created_at)}` : ago(now - created);
  const b = band(coneFor(adv));
  return `${adv.volcano_name || adv.volcano_id}${b ? ` · ash ${b}` : ''} · drafted ${age}`;
}

// The Next decision card (R10.4): one draft, expanded, with one neutral button into its review.
function buildNext(adv, items) {
  const now = activeNow();
  const position = items.findIndex((a) => a.id === adv.id) + 1;
  const card = el('article', { class: 'next__card', 'data-id': adv.id, 'data-version': String(adv.version), 'data-band': band(coneFor(adv)), 'data-crewkey': crewKey(adv), 'aria-labelledby': 'next-flight' },
    el('div', { class: 'next__row' },
      el('p', { class: 'next__who' },
        el('span', { class: 'next__flight', id: 'next-flight', text: adv.proxy_flight }),
        el('span', { class: 'next__ident', text: identText(adv) })),
      el('span', { class: 'next__entry', 'data-slot': 'entry' }, entryNode(adv, now))),
    el('p', { class: 'next__action' }, icon(ACTION_ICON[adv.action] || 'i-arrow-right'), el('span', { text: actionPlain(adv) })),
    el('p', { class: 'next__meta', 'data-slot': 'meta', text: metaText(adv, now) }),
    el('p', { class: 'next__body', text: adv.edited_body ?? adv.body }),
    el('p', { class: 'next__writer' }, ...writerLine(adv)),
    el('p', { class: 'next__src', 'data-slot': 'src' }, icon('i-file', 'st'), el('span', { text: sourcesSummary(adv, now) })),
    el('span', { 'data-slot': 'tags' }, tagsNode(adv, now)),
    el('button', { type: 'button', class: 'btn btn--cta next__go', 'data-open': adv.id, 'aria-describedby': 'next-flight' },
      el('span', { text: `Review ${adv.proxy_flight}` }), icon('i-chevron-right')));
  card.dataset.position = String(position);
  return card;
}

// One compact row per other draft: "RFA1530 · inside now · Keep watching ›".
function buildRow(adv) {
  const now = activeNow();
  const marks = cautions(adv, now);
  const button = el('button', { type: 'button', class: 'card card--row', 'data-open': adv.id },
    el('span', { class: 'row__flight', text: adv.proxy_flight }),
    el('span', { class: `row__entry row__entry--${entryState(adv, now).kind}`, 'data-slot': 'entry', text: entryShort(adv, now) }),
    el('span', { class: 'row__action', text: actionShort(adv) }),
    el('span', { class: 'row__marks', 'data-slot': 'tags' }, rowMark(marks)),
    el('span', { class: 'card__new', 'data-slot': 'new', hidden: true }, el('span', { text: 'New' })),
    icon('i-chevron-right', 'icon row__go'));
  return el('li', { class: 'cards__item', 'data-id': adv.id, 'data-version': String(adv.version), 'data-band': band(coneFor(adv)), 'data-crewkey': crewKey(adv) }, button);
}

function setSlot(root, name, node) {
  const slot = root.querySelector(`[data-slot="${name}"]`);
  if (slot) slot.replaceChildren(node);
}

// Live values: the countdown, the draft age, and the age-based tag. Runs every 15 s.
export function updateTimes() {
  const now = activeNow();
  const next = byId('q-next').querySelector('.next__card');
  const nextAdv = next && app.drafts.get(next.dataset.id);
  if (nextAdv) {
    setSlot(next, 'entry', entryNode(nextAdv, now));
    next.querySelector('[data-slot="meta"]').textContent = metaText(nextAdv, now);
    next.querySelector('[data-slot="src"] > span').textContent = sourcesSummary(nextAdv, now);
    setSlot(next, 'tags', tagsNode(nextAdv, now));
  }
  for (const li of byId('cards').children) {
    const adv = app.drafts.get(li.dataset.id);
    if (!adv) continue;
    const marks = li.querySelector('.row__marks');
    if (marks) {
      const m = rowMark(cautions(adv, now));
      if ((marks.textContent || '') !== (m ? m.textContent : '')) marks.replaceChildren(...(m ? [m] : []));
    }
    const entry = li.querySelector('[data-slot="entry"]');
    if (entry) {
      entry.textContent = entryShort(adv, now);
      entry.className = `row__entry row__entry--${entryState(adv, now).kind}`;
    }
    const arrived = app.arrivedAt.get(adv.id);
    const fresh = arrived !== undefined && performance.now() - arrived < NEW_TAG_MS;
    const tag = li.querySelector('[data-slot="new"]');
    if (tag) tag.hidden = !fresh;
    li.classList.toggle('is-fresh', fresh);
  }
}

function skeleton() {
  const item = () =>
    el('li', { class: 'cards__item skeleton', 'aria-hidden': 'true' },
      el('span', { class: 'sk sk--a' }), el('span', { class: 'sk sk--b' }));
  return [item(), item(), item()];
}

// The Next decision stays put while the dispatcher reads it (R14.6): a newer, more urgent draft
// shows the line "1 more urgent draft arrived · Show" instead of swapping the card.
let nextId = null;

export const nextDraftId = () => nextId;

export function showMostUrgent() {
  const items = draftList().sort(byUrgency);
  nextId = items[0] ? items[0].id : null;
  renderQueue();
}

const plural = (n, word, many = `${word}s`) => `${n} ${n === 1 ? word : many}`;

// "23 advisories · 3 messages · 2 flights to plan by hand" (R2.7, K85): what the Decide badge counts.
export function breakdownText() {
  const parts = [plural(draftList().length, 'advisory', 'advisories')];
  const m = draftMessages().length;
  const f = openFailures().length;
  if (m) parts.push(plural(m, 'message'));
  if (f) parts.push(`${plural(f, 'flight')} to plan by hand`);
  return parts.join(' · ');
}

// Under the Next decision header only when it adds something to "1 of 23 advisories".
function breakdownLine() {
  const aside = setAsideCount();
  const other = app.state && app.state.mode === 'REPLAY' ? 'live' : 'replay';
  const note = aside ? `${plural(aside, `${other} draft`)} set aside until ${other === 'live' ? 'live feeds play' : 'that replay plays'} again` : '';
  return [draftList().length && (draftMessages().length || openFailures().length) ? breakdownText() : '', note].filter(Boolean).join(' · ');
}

export function renderQueue() {
  const list = byId('cards');
  const stateBox = byId('q-state');
  const slot = byId('q-next');
  const items = draftList().sort(byUrgency);
  const n = items.length;
  // The draft open in the review is the Next decision, so one flight is primary at a time: a
  // deep link from the Wall ("Decide on the Desk") or a tapped row puts that draft in the card
  // (review 2, item 6). Its place in the urgency order stays visible ("5 of 41").
  if (app.selectedId && app.drafts.has(app.selectedId)) nextId = app.selectedId;
  if (!nextId || !app.drafts.has(nextId)) nextId = items[0] ? items[0].id : null;
  const nextAdv = nextId ? app.drafts.get(nextId) : null;
  const position = nextAdv ? items.indexOf(nextAdv) + 1 : 0;
  byId('q-count').textContent = app.listLoaded && n
    ? `${position} of ${plural(n, 'advisory', 'advisories')} · most urgent first`
    : '';
  byId('q-breakdown').textContent = app.listLoaded ? breakdownLine() : '';
  const newer = byId('q-newer');
  newer.hidden = !(nextAdv && position > 1);
  if (!newer.hidden) {
    newer.replaceChildren(icon('st-caution', 'st'),
      el('span', { text: `${plural(position - 1, 'draft')} ${position === 2 ? 'is' : 'are'} more urgent` }),
      el('button', { type: 'button', class: 'linkbtn', 'data-newest': '1' }, el('span', { text: 'Show the most urgent' })));
  }

  if (!app.listLoaded && !app.listError) {
    stateBox.replaceChildren(el('p', { class: 'sr-only', text: 'Loading drafts…' }));
    if (!list.querySelector('.skeleton')) list.replaceChildren(...skeleton());
    slot.replaceChildren();
    byId('more-title').hidden = true;
    return;
  }
  for (const sk of list.querySelectorAll('.skeleton')) sk.remove();

  if (app.listError) {
    stateBox.replaceChildren(
      el('div', { class: 'panel panel--serious', role: 'alert' },
        el('p', { class: 'panel__title' }, icon('st-serious', 'st'), el('span', { text: "Can't load drafts." })),
        el('p', { text: app.listError }),
        el('button', { type: 'button', class: 'btn btn--outline', 'data-retry': '1' }, icon('i-refresh'), el('span', { text: 'Try again' }))),
    );
  } else if (n === 0) {
    const last = app.lastLoadedAt === null ? '' : ` Last update ${new Date(app.lastLoadedAt).toISOString().slice(11, 19)}Z.`;
    // no green "all clear" while flights wait to be planned by hand (H9)
    const hand = openFailures().length;
    stateBox.replaceChildren(
      el('div', { class: 'panel panel--empty' },
        el('p', { class: 'panel__title' }, icon(hand ? 'st-info' : 'i-check', hand ? 'st is-info' : 'st'), el('span', { text: hand ? 'No drafts to approve.' : 'No drafts waiting.' })),
        el('p', { text: hand ? `${plural(hand, 'flight')} to plan by hand are below.${last}` : `A draft appears here when a flight's projected track enters TEPHRA's estimated ash area.${last}` })),
    );
  } else {
    stateBox.replaceChildren();
  }

  // The Next decision card.
  const shown = slot.querySelector('.next__card');
  if (!nextAdv) slot.replaceChildren();
  else if (!shown || shown.dataset.id !== nextAdv.id || Number(shown.dataset.version) !== nextAdv.version || shown.dataset.band !== band(coneFor(nextAdv)) || shown.dataset.crewkey !== crewKey(nextAdv)) {
    const hadFocus = shown && shown.contains(document.activeElement);
    slot.replaceChildren(buildNext(nextAdv, items));
    if (hadFocus) slot.querySelector('.next__go').focus({ preventScroll: true });
  }
  const card = slot.querySelector('.next__card');
  if (card) card.classList.toggle('is-current', nextAdv.id === app.selectedId);

  // The rest, one line each.
  const rest = items.filter((a) => a.id !== nextId);
  const more = byId('more-title');
  more.hidden = rest.length === 0;
  more.textContent = `${rest.length} more waiting`;
  const wanted = new Set(rest.map((a) => a.id));
  for (const li of [...list.children]) {
    if (!wanted.has(li.dataset.id) && !li.classList.contains('is-leaving')) leave(li);
  }
  // At most ROWS_FIRST rows until "Show all n" (review 1, item 8), so the one-line links under
  // the list (airport plan, Duty Officer, messages) stay near the top. The selected row is never hidden.
  const capped = !showAllRows && rest.length > ROWS_FIRST + 1;
  rest.forEach((adv, index) => {
    let li = list.querySelector(`li[data-id="${CSS.escape(adv.id)}"]`);
    if (!li || Number(li.dataset.version) !== adv.version || li.dataset.band !== band(coneFor(adv)) || li.dataset.crewkey !== crewKey(adv)) {
      const row = buildRow(adv);
      if (li) li.replaceWith(row);
      li = row;
    }
    const live = [...list.children].filter((c) => !c.classList.contains('is-leaving'));
    if (live[index] !== li) list.insertBefore(li, live[index] || null);
    const btn = li.querySelector('.card');
    if (adv.id === app.selectedId) btn.setAttribute('aria-current', 'true');
    else btn.removeAttribute('aria-current');
    li.classList.toggle('is-busy', app.inFlight.has(adv.id));
    li.hidden = capped && index >= ROWS_FIRST && adv.id !== app.selectedId;
  });
  const allBtn = byId('cards-all');
  if (allBtn) {
    allBtn.hidden = !capped;
    if (capped) allBtn.querySelector('span').textContent = `Show all ${rest.length}`;
  }
  updateTimes();
  renderClosed();
}

// The card leaves over --dur-3 (instantly under reduced motion).
function leave(li) {
  const focused = li.contains(document.activeElement);
  li.classList.add('is-leaving');
  li.style.setProperty('--h', `${li.offsetHeight}px`);
  const done = () => li.remove();
  li.addEventListener('animationend', done, { once: true });
  window.setTimeout(done, 400);
  if (focused) app.hub.focusQueueTitle();
}

// Marks a row as just arrived: a short highlight and a "New" tag for two minutes.
export function flashNew(id) {
  app.arrivedAt.set(id, performance.now());
  const li = byId('cards').querySelector(`li[data-id="${CSS.escape(id)}"]`);
  if (!li) return;
  li.classList.remove('is-arriving');
  void li.offsetWidth; // restart the animation
  li.classList.add('is-arriving');
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
  byId('closed-count').textContent = `(${app.closed.size})`;
  list.replaceChildren(
    ...items.map((adv) =>
      el('li', {},
        el('button', { type: 'button', class: 'closed__item', 'data-open': adv.id, 'aria-current': adv.id === app.selectedId ? 'true' : null },
          statusBadge(adv),
          el('span', { class: 'closed__what' },
            el('span', { class: 'closed__flight', text: adv.proxy_flight }),
            el('span', { text: ` ${actionPlain(adv)}` })),
          el('span', { class: 'closed__when', text: decidedLine(adv) }))),
    ),
  );
}
