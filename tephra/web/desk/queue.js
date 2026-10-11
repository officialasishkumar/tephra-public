// The queue (docs/UI-DESIGN.md 10.3): drafts awaiting decision, most urgent first, and the
// advisories that left DRAFT while this page was open ("Closed this session").

import { byId, el, icon, status } from './dom.js';
import {
  ACTION_ICON,
  actionText,
  activeNow,
  ago,
  band,
  byUrgency,
  deskName,
  hhmmz,
  isStub,
  parseTime,
  pct,
  sourcesSummary,
} from './format.js';
import { app, draftList } from './state.js';

const OLD_DRAFT_MIN = 10;
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
  const words = {
    OFFICIAL: `OFFICIAL ${pct(adv.confidence)}`,
    WIDENED: `WIDENED ${pct(adv.confidence)}`,
    HYPOTHESIS: long ? `HYPOTHESIS ${pct(adv.confidence)} · MONITOR or HOLD only` : `HYPOTHESIS ${pct(adv.confidence)}`,
  }[adv.plume_mode];
  return el(
    'span',
    { class: `chip chip--mode chip--${adv.plume_mode.toLowerCase()}`, title: 'TEPHRA cautious area for this draft' },
    icon(shape, 'st'),
    bare ? null : el('span', { class: 'caps chip__k', text: 'Area' }),
    el('span', { text: words }),
  );
}

export function modelChip(adv, { card = false } = {}) {
  return isStub(adv)
    ? el('span', { class: 'chip chip--stub', title: 'NO MODEL: written from a code template, not by a model' },
      icon('i-code', 'st'), el('span', { text: card ? 'NO MODEL' : 'Template · NO MODEL' }))
    : el('span', { class: 'chip chip--ai' }, icon('i-model', 'st'), el('span', { text: 'AI-drafted' }));
}

export function replayChip() {
  return el('span', { class: 'chip chip--replay' }, icon('i-replay', 'st'), el('span', { text: 'REPLAY' }));
}

function entryNode(adv, now) {
  if (adv.inside_now) {
    return el('span', { class: 'entry entry--inside' }, icon('st-inside', 'st'), el('span', { text: 'INSIDE NOW' }));
  }
  const created = parseTime(adv.created_at) ?? 0;
  const left = now === null ? adv.minutes_to_entry : Math.ceil((created + adv.minutes_to_entry * 60000 - now) / 60000);
  if (left > 0) {
    return el(
      'span',
      { class: 'entry' },
      el('span', { class: 'caps', text: 'Enters in' }),
      el('span', { class: 'entry__mins', text: `${left} MIN` }),
    );
  }
  return el(
    'span',
    { class: 'entry entry--due' },
    el('span', { class: 'caps', text: 'Entry was due' }),
    el('span', { class: 'entry__due', text: left === 0 ? 'NOW' : `${-left} MIN AGO` }),
  );
}

function ageMinutes(adv, now) {
  const created = parseTime(adv.created_at);
  return now === null || created === null ? 0 : (now - created) / 60000;
}

function tagsNode(adv, now) {
  const tags = el('span', { class: 'tags' }, modeChip(adv), modelChip(adv, { card: true }));
  if (adv.replay) tags.append(replayChip());
  if (needsCarefulRead(adv)) {
    tags.append(el('span', { class: 'chip chip--caution' }, icon('st-caution', 'st'), el('span', { text: 'Needs a careful read' })));
  }
  if (anyStaleSource(adv)) {
    tags.append(el('span', { class: 'chip chip--caution' }, icon('st-stale', 'st'), el('span', { text: 'Sources stale' })));
  }
  const age = ageMinutes(adv, now);
  if (age > OLD_DRAFT_MIN) {
    tags.append(
      el('span', { class: 'chip chip--caution' }, icon('i-clock', 'st'),
        el('span', { text: `Drafted ${Math.floor(age)} min ago: entry time may have moved` })),
    );
  }
  return tags;
}

function buildCard(adv) {
  const now = activeNow();
  const cone = coneFor(adv);
  const ident = [adv.callsign, adv.type_icao].filter((v) => typeof v === 'string' && v).join(' · ');
  const button = el(
    'button',
    { type: 'button', class: 'card', 'data-open': adv.id },
    el(
      'span',
      { class: 'card__row' },
      el('span', { class: 'card__who' },
        el('span', { class: 'card__flight', text: adv.proxy_flight }),
        el('span', { class: 'card__ident', text: ident || 'no callsign' })),
      el('span', { class: 'card__entry', 'data-slot': 'entry' }, entryNode(adv, now)),
    ),
    el(
      'span',
      { class: `card__action action--${adv.action.toLowerCase()}` },
      icon(ACTION_ICON[adv.action] || 'i-arrow-right'),
      el('span', { class: 'card__action-text', text: actionText(adv) }),
      band(cone) ? el('span', { class: 'band' }, el('span', { class: 'caps', text: 'Band' }), el('span', { text: band(cone) })) : null,
    ),
    el('span', { class: 'card__meta', 'data-slot': 'meta', text: metaText(adv, now) }),
    el('span', { class: 'card__src', 'data-slot': 'src' }, icon('i-file', 'st'), el('span', { text: sourcesSummary(adv, now) })),
    // A two-line preview of the text that would be queued; the full text is in the review.
    el('span', { class: 'card__body', 'aria-hidden': 'true', text: adv.edited_body ?? adv.body }),
    el('span', { 'data-slot': 'tags' }, tagsNode(adv, now)),
    el('span', { class: 'card__new', 'data-slot': 'new', hidden: true }, icon('i-plus', 'st'), el('span', { text: 'New' })),
  );
  const li = el('li', { class: 'cards__item', 'data-id': adv.id, 'data-version': String(adv.version), 'data-band': band(cone) }, button);
  return li;
}

function metaText(adv, now) {
  const created = parseTime(adv.created_at);
  const age = now === null || created === null ? `at ${hhmmz(adv.created_at)}` : ago(now - created);
  return `${adv.volcano_name || adv.volcano_id} · drafted ${age}`;
}

function setSlot(li, name, node) {
  const slot = li.querySelector(`[data-slot="${name}"]`);
  if (slot) slot.replaceChildren(node);
}

// Live values: the countdown, the draft age, and the age-based tag. Runs every 15 s.
export function updateTimes() {
  const now = activeNow();
  for (const li of byId('cards').children) {
    const adv = app.drafts.get(li.dataset.id);
    if (!adv) continue;
    setSlot(li, 'entry', entryNode(adv, now));
    const meta = li.querySelector('[data-slot="meta"]');
    if (meta) meta.textContent = metaText(adv, now);
    const src = li.querySelector('[data-slot="src"] > span');
    if (src) src.textContent = sourcesSummary(adv, now);
    setSlot(li, 'tags', tagsNode(adv, now));
    const arrived = app.arrivedAt.get(adv.id);
    const fresh = arrived !== undefined && performance.now() - arrived < NEW_TAG_MS;
    li.querySelector('[data-slot="new"]').hidden = !fresh;
    li.classList.toggle('is-fresh', fresh);
  }
}

function skeleton() {
  const item = () =>
    el('li', { class: 'cards__item skeleton', 'aria-hidden': 'true' },
      el('span', { class: 'sk sk--a' }), el('span', { class: 'sk sk--b' }), el('span', { class: 'sk sk--c' }));
  return [item(), item(), item()];
}

export function renderQueue() {
  const list = byId('cards');
  const stateBox = byId('q-state');
  const items = draftList().sort(byUrgency);
  const n = items.length;
  byId('q-count').textContent = app.listLoaded ? `${n} waiting` : '';

  if (!app.listLoaded && !app.listError) {
    stateBox.replaceChildren(el('p', { class: 'sr-only', text: 'Loading drafts…' }));
    if (!list.querySelector('.skeleton')) list.replaceChildren(...skeleton());
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
    stateBox.replaceChildren(
      el('div', { class: 'panel panel--empty' },
        el('p', { class: 'panel__title' }, icon('i-check', 'st'), el('span', { text: 'No drafts waiting.' })),
        el('p', { text: `A draft appears here when a flight's projected track enters TEPHRA's cautious area.${last}` })),
    );
  } else {
    stateBox.replaceChildren();
  }

  const wanted = new Set(items.map((a) => a.id));
  for (const li of [...list.children]) {
    if (!wanted.has(li.dataset.id) && !li.classList.contains('is-leaving')) leave(li);
  }
  items.forEach((adv, index) => {
    let li = list.querySelector(`li[data-id="${CSS.escape(adv.id)}"]`);
    // The band arrives with the cones, often after the first render.
    if (!li || Number(li.dataset.version) !== adv.version || li.dataset.band !== band(coneFor(adv))) {
      const card = buildCard(adv);
      if (li) li.replaceWith(card);
      li = card;
    }
    const live = [...list.children].filter((c) => !c.classList.contains('is-leaving'));
    if (live[index] !== li) list.insertBefore(li, live[index] || null);
    const btn = li.querySelector('.card');
    btn.toggleAttribute('aria-current', adv.id === app.selectedId);
    if (adv.id === app.selectedId) btn.setAttribute('aria-current', 'true');
    li.classList.toggle('is-busy', app.inFlight.has(adv.id));
  });
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

// Marks a card as just arrived: a short highlight and a "New" tag for two minutes.
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
  list.replaceChildren(
    ...items.map((adv) =>
      el('li', {},
        el('button', { type: 'button', class: 'closed__item', 'data-open': adv.id, 'aria-current': adv.id === app.selectedId ? 'true' : null },
          statusBadge(adv),
          el('span', { class: 'closed__what' },
            el('span', { class: 'closed__flight', text: adv.proxy_flight }),
            el('span', { text: ` ${actionText(adv)}` })),
          el('span', { class: 'closed__when', text: decidedLine(adv) }))),
    ),
  );
}
