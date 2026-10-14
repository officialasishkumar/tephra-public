// The review sheet (Desk redesign 5.3; docs/UI-DESIGN.md 10.4-10.8): it reads top to bottom. The
// flight, the action in plain words and the entry line; "Check before you approve", the facts code
// computed (level, ash band, area, sources, fuel, route), each said once; "Text to approve", the
// code-written header dim above the body that is approved; who wrote it; and one decision bar
// (hold, or tap and confirm). The rest is one tap away on four pages inside the sheet: Sources,
// Area, Route and Record (ids, policy, the header, history). Computed facts and model-written
// text are never mixed in one sentence. Full screen on phones, the right pane from 1100 px.

import {
  BODY_CAUTION_CHARS,
  BODY_MAX_CHARS,
  PATHS,
  REASON_MAX_CHARS,
  REASON_MIN_CHARS,
  api,
  errorCode,
  problems,
} from './api.js';
import { announce, append, byId, el, icon, isDesktop, isWide } from './dom.js';
import {
  FEED_NAMES,
  MODE_SENTENCE,
  actionShort,
  actionText,
  approveText,
  activeNow,
  band,
  ago,
  ddhhmmz,
  deskName,
  draftedAt,
  entryAt,
  entryState,
  fl,
  hhmmz,
  isBindingFeed,
  isStub,
  parseTime,
  productName,
  sourceList,
  sourceTime,
} from './format.js';
import { EARLY_RELEASE_HINT, holdButton } from './hold.js';
import { anyStaleSource, coneFor, decidedLine, levelNow, modeChip, needsCarefulRead, statusBadge, statusView, walkOrder } from './queue.js';
import { app } from './state.js';
import { routeMap } from './route.js';
import { aiMark, codeChip, fromReplayChip } from './ui.js';
import { CREW_REASON_MIN, crewBox, crewKey, crewReasonNeeded } from './crew.js';

const GHOST_TAP_MS = 450;
const OFFLINE_HINT = 'Reconnect to approve';
// A crew report of ash on the flight's route: keeping it on its route needs a written reason.
const CREW_REASON_HINT = 'A crew reported ash on this route: write the reason above before approving.';
const REJECT_REASONS = [
  'Flight already outside the area',
  'Level already outside the ash band',
  'Duplicate of another draft',
  'Ash data look wrong',
];
const PAGES = { sources: 'Sources', area: 'Area', route: 'Route', record: 'Record' };

// sheet: { id, seen, view, page, bar, busy, edit, editTried, reason, error, problems, conflict,
//   confirmAt, hint, reasonTouched, stamp, crewReason, crewError, crewKey, crewForced }
let sheet = null;

export const sheetOpenFor = () => (sheet ? sheet.id : null);
export const sheetBusy = () => Boolean(sheet && sheet.busy);

export function openSheet(adv, { focus = true } = {}) {
  sheet = {
    id: adv.id,
    seen: adv,
    view: adv.status === 'DRAFT' ? 'review' : 'closed',
    page: null,
    bar: 'decide',
    busy: false,
    edit: adv.edited_body ?? adv.body,
    editTried: false,
    reason: '',
    error: '',
    problems: [],
    conflict: null,
    confirmAt: 0,
    hint: '',
    reasonTouched: false,
    stamp: null,
    crewReason: '',
    crewError: '',
    crewKey: crewKey(adv),
    // set when the server asked for a reason the page had not seen a flag for yet (422)
    crewForced: false,
  };
  render();
  if (focus) focusTitle();
}

export function closeSheet() {
  sheet = null;
  const host = byId('sheet');
  host.replaceChildren();
  host.hidden = true;
  placeReceipt();
}

function focusTitle() {
  const title = byId('s-title');
  if (title) title.focus({ preventScroll: true });
  const body = byId('sheet').querySelector('.sheet__body');
  if (body) body.scrollTop = 0;
  if (!isWide()) window.scrollTo({ top: 0 });
}

// Called by desk.js whenever the open advisory may have changed (stream, list, offline).
export function syncSheet() {
  if (!sheet) return;
  if (sheet.busy) {
    renderBar();
    return;
  }
  const draft = app.drafts.get(sheet.id);
  const closed = app.closed.get(sheet.id);
  if (sheet.view === 'conflict' || sheet.view === 'gone') {
    renderBar();
    return;
  }
  if (draft && draft.version !== sheet.seen.version && sheet.view !== 'closed') {
    sheet.conflict = { current: draft, before: sheet.seen };
    sheet.view = 'conflict';
    sheet.page = null;
    render();
    return;
  }
  if (!draft && closed && sheet.view !== 'closed') {
    // Decided elsewhere or replaced by TEPHRA while open: shown as such, read-only.
    sheet.seen = closed;
    sheet.view = 'closed';
    sheet.bar = 'decide';
    render();
    announce(`${closed.proxy_flight}: ${closedSentence(closed)}`);
    return;
  }
  if (draft) sheet.seen = draft;
  // A crew report that flags (or stops flagging) this flight changes the review itself.
  if ((sheet.view === 'review' || sheet.view === 'edit') && crewKey(sheet.seen) !== sheet.crewKey) {
    sheet.crewKey = crewKey(sheet.seen);
    const typing = document.activeElement && document.activeElement.id;
    render();
    const again = typing && byId(typing);
    if (again) again.focus({ preventScroll: true });
    return;
  }
  renderHead();
  renderBar();
  updateSheetTimes();
}

const reasonNeeded = (adv) => crewReasonNeeded(adv) || Boolean(sheet && sheet.crewForced);
const reasonShort = (adv) => reasonNeeded(adv) && sheet.crewReason.trim().length < CREW_REASON_MIN;

// The reason box (UI-DESIGN 10.15): CONTINUE or MONITOR for an airborne flight whose projected
// track crosses a crew report area. Every tracked flight is airborne (ADS-B ground targets are
// dropped). The reason goes with the decision and into the audit log.
function crewReasonField(adv) {
  const area = el('textarea', {
    id: 'crew-reason', class: 'field', rows: '3', maxlength: String(REASON_MAX_CHARS), autocomplete: 'off',
    'aria-describedby': 'crew-reason-note crew-reason-msg', required: true, 'aria-invalid': sheet.crewError ? 'true' : null,
  });
  area.value = sheet.crewReason;
  const count = el('p', { class: 'counter' });
  const msg = el('div', { id: 'crew-reason-msg', class: 'field-msg', 'aria-live': 'polite' });
  const update = () => {
    const n = sheet.crewReason.trim().length;
    count.textContent = n < CREW_REASON_MIN ? `${n} / ${REASON_MAX_CHARS} · at least ${CREW_REASON_MIN} characters` : `${n} / ${REASON_MAX_CHARS}`;
    count.dataset.level = n < CREW_REASON_MIN && sheet.crewError ? 'caution' : 'ok';
    msg.replaceChildren(...(sheet.crewError ? [el('p', { class: 'msg msg--serious' }, icon('st-serious', 'st'), el('span', { text: sheet.crewError }))] : []));
  };
  area.addEventListener('input', () => {
    sheet.crewReason = area.value;
    sheet.crewError = '';
    area.removeAttribute('aria-invalid');
    update();
    renderBar();
  });
  update();
  return el('div', { class: 'crewreason' },
    el('label', { class: 'flabel', for: 'crew-reason', text: `Reason to ${adv.action === 'CONTINUE' ? 'continue' : 'keep watching'} on this route (required)` }),
    el('p', { id: 'crew-reason-note', class: 'fine', text: 'Recorded with the decision and in the audit log. The crew report stays on the Wall either way.' }),
    area, count, msg);
}

function crewReasonMissing() {
  sheet.crewError = `Give a reason of at least ${CREW_REASON_MIN} characters: a crew reported ash on this route.`;
  sheet.bar = 'decide';
  sheet.page = null;
  render();
  const f = byId('crew-reason');
  if (f) {
    f.focus();
    f.scrollIntoView({ block: 'center' });
  }
  announce(sheet.crewError);
}

export function updateSheetTimes() {
  if (!sheet) return;
  const host = byId('sheet');
  const slot = host.querySelector('[data-slot="entry"]');
  if (slot) slot.replaceWith(entryLine(sheet.seen));
  const src = host.querySelector('[data-slot="srcsum"]');
  if (src) src.textContent = sourcesFact(sheet.seen);
  const confirmEntry = byId('confirm-entry');
  if (confirmEntry) confirmEntry.textContent = confirmFacts(sheet.seen);
}

// --- render ---------------------------------------------------------------------------

function render() {
  const host = byId('sheet');
  host.hidden = false;
  const adv = sheet.seen;
  const head = el('div', { class: 'sheet__head' });
  const body = el('div', { class: 'sheet__body' });
  if (sheet.view === 'edit') body.append(...editView(adv));
  else if (sheet.view === 'reject') body.append(...rejectView(adv));
  else if (sheet.view === 'conflict') body.append(...conflictView());
  else if (sheet.view === 'gone') body.append(...goneView());
  else if (sheet.page) body.append(...pageView(adv, sheet.page));
  else body.append(...reviewView(adv));
  const bar = el('div', { class: 'actions', id: 'sheet-actions' });
  host.replaceChildren(head, receiptSlot, body, bar);
  // a page has its own way back (to the review), so it never reads as the review itself
  host.dataset.view = sheet.page && sheet.view !== 'edit' && sheet.view !== 'reject' ? 'page' : sheet.view;
  renderHead();
  renderBar();
  // after the frame: the caller switches Decide to the review view once this returns
  window.requestAnimationFrame(placeBar);
}

// The words come before the button (review: the body sat under the pinned bar). On a phone the
// decision bar is pinned only when the first lines of the text to approve are above it when the
// review opens; otherwise (a short screen, a reroute's sketch, a receipt line) it sits after the
// content, where reading down reaches it once the text has been read. Pages keep it pinned.
function placeBar() {
  const bar = byId('sheet-actions');
  if (!bar || !sheet) return;
  bar.classList.remove('actions--after');
  const text = byId('sheet').querySelector('.textbox__body');
  if (!isDesktop() && text && !sheet.page && (sheet.view === 'review' || sheet.view === 'closed')) {
    const lines = 2 * (parseFloat(getComputedStyle(text).lineHeight) || 20);
    const textTop = text.getBoundingClientRect().top + window.scrollY;
    if (textTop + Math.min(text.offsetHeight, lines) > window.innerHeight - bar.offsetHeight) bar.classList.add('actions--after');
  }
  app.hub.measureBar();
}

// The top bar (5.3): "‹ Decide", where this item sits in the act-by order, "Skip for now ›".
function renderHead() {
  const head = byId('sheet').querySelector('.sheet__head');
  if (!head || !sheet) return;
  const sub = sheet.view === 'edit' || sheet.view === 'reject';
  const order = walkOrder();
  const at = order.findIndex((a) => a.id === sheet.id);
  const draft = sheet.view === 'review' && !sheet.page && app.drafts.has(sheet.id) && at >= 0;
  const next = draft ? skipTarget() : null;
  const hadFocus = head.contains(document.activeElement) ? (document.activeElement.dataset.skip ? '[data-skip]' : '[data-back]') : null;
  head.replaceChildren();
  append(head, [
    el('button', { type: 'button', class: 'sheet__back', 'data-back': '1' }, icon('i-chevron-left'),
      el('span', { text: sheet.page && !sub ? sheet.seen.proxy_flight : sub ? 'Review' : 'Decide' })),
    // the walk is the advisories only, so it says so: "1 of 15 advisories" next to "16 waiting"
    // (which also counts messages, plans, documents and flights to plan by hand) is not a second count
    draft ? el('span', { class: 'sheet__pos', text: `${at + 1} of ${order.length} ${order.length === 1 ? 'advisory' : 'advisories'}` }) : el('span', { class: 'sheet__pos' }),
    next ? el('button', { type: 'button', class: 'sheet__skip', 'data-skip': next.id, 'aria-label': `Skip for now: open ${next.proxy_flight}, leave ${sheet.seen.proxy_flight} in Decide` },
      el('span', { text: 'Skip for now' }), icon('i-chevron-right')) : null]);
  if (hadFocus) head.querySelector(hadFocus)?.focus({ preventScroll: true });
}

// The next item in the act-by order after this one ("Skip for now" opens it; nothing is decided).
function skipTarget() {
  const order = walkOrder();
  const at = order.findIndex((a) => a.id === sheet.id);
  return at >= 0 && order.length > 1 ? order[(at + 1) % order.length] : null;
}

const fine = (text) => el('span', { class: 'fine', text });

function fact(label, value, { page = null, slot = null } = {}) {
  const v = el('dd', { 'data-slot': slot }, value);
  if (!page) return el('div', { class: 'fact' }, el('dt', { text: label }), v);
  // the whole row is the way into its page (› always goes somewhere)
  return el('div', { class: 'fact fact--go' }, el('dt', { text: label }), v,
    el('button', { type: 'button', class: 'fact__go', 'data-page': page, 'aria-label': `${label}: ${PAGES[page]} page` }, icon('i-chevron-right')));
}

// "Entry due now (est.)", "Enters in 3 min (est.)", "Inside the ash now": once, under the action.
function entryLine(adv) {
  const st = entryState(adv, activeNow());
  const soon = st.kind === 'due' || (st.kind === 'ahead' && st.minutes <= 10);
  const text = st.kind === 'inside' ? 'Inside the ash now'
    : st.kind === 'ahead' ? `Enters in ${st.minutes} min (est.)`
      : st.minutes ? `Entry was due ${st.minutes} min ago (est.)` : 'Entry due now (est.)';
  return el('p', { class: `rv2__entry${soon ? ' is-soon' : ''}`, 'data-slot': 'entry' },
    icon(st.kind === 'inside' ? 'st-inside' : soon ? 'st-caution' : 'i-clock', 'st'), el('span', { text }));
}

// "now FL310 → hold at FL226": the level now (ADS-B) and the level the action asks for.
function levelFact(adv) {
  const now = levelNow(adv);
  const target = adv.action === 'HOLD' && Number.isFinite(adv.hold_fl) ? `hold at ${fl(adv.hold_fl)}`
    : adv.action === 'CHANGE_LEVEL' && Number.isFinite(adv.change_level_fl_min) ? `change to ${fl(adv.change_level_fl_min)}${adv.change_level_fl_max !== adv.change_level_fl_min ? `–${fl(adv.change_level_fl_max)}` : ''}` : null;
  if (now === null) return target;
  return `now ${fl(now)}${target ? ` → ${target}` : ''}`;
}

// "7 · 5 official · newest 3 min"
function sourcesFact(adv) {
  const list = sourceList(adv);
  if (!list.length) return 'none listed';
  const official = list.filter((s) => isBindingFeed(s.feed)).length;
  const times = list.map(sourceTime).filter(Boolean).map((x) => x.t);
  const now = activeNow();
  const newest = times.length ? (now === null ? `newest ${hhmmz(Math.max(...times))}` : `newest ${ago(now - Math.max(...times)).replace(/ ago$/, '')}`) : '';
  return [String(list.length), `${official} official`, newest].filter(Boolean).join(' · ');
}

// The text box (5.3): the header code wrote, dim and not editable, folded to one line ("Header
// written by code ▸") so the body, what gets approved, is on the first screen above the decision
// bar; the full header is one tap away here and in Record. Nothing is left out of what is approved.
function textBox(adv, { body = true } = {}) {
  const lines = String(adv.header || '').split('\n').filter((l) => l.trim() !== '');
  return el('div', { class: 'textbox' },
    lines.length ? el('details', { class: 'textbox__hdr' },
      el('summary', {}, icon('i-chevron-right', 'icon disclosure'),
        el('span', { text: `Header written by code · ${lines.length} line${lines.length === 1 ? '' : 's'}` })),
      el('pre', { class: 'textbox__head', text: lines.join('\n') })) : null,
    body ? el('pre', { class: 'textbox__body', text: adv.edited_body ?? adv.body }) : null);
}

// Who wrote the text, as one line under the box: the mark only where a model wrote it.
function writerLine(adv) {
  const stub = isStub(adv);
  const words = [];
  if (adv.edited_body != null) words.push(`edited by ${deskName(adv.decided_by) || 'a dispatcher'}`);
  return el('p', { class: 'writer-note' }, aiMark(undefined, stub ? null : adv.model_id), words.length ? el('span', { text: ` · ${words.join(' · ')}` }) : null);
}

function hypothesisBanner() {
  return el('div', { class: 'banner banner--hypothesis', role: 'note' }, icon('st-caution', 'st'),
    el('p', {}, el('strong', { text: 'HYPOTHESIS' }), ' · only Keep watching or Hold can be approved for this flight.'));
}

function reviewView(adv) {
  const out = [];
  if (sheet.view === 'closed') {
    out.push(el('div', { class: `banner banner--closed banner--${adv.status.toLowerCase()}`, role: 'note' },
      statusBadge(adv), el('p', { text: closedSentence(adv) })));
  }
  if (adv.plume_mode === 'HYPOTHESIS') out.push(hypothesisBanner());
  // REPLAY is said by the frame strip; a replay draft opened while live feeds play says so here,
  // since the strip then says nothing about it (UI-DESIGN 7.1, cross-mode records).
  const fromReplay = fromReplayChip(adv);
  if (fromReplay) out.push(el('p', { class: 'replay-note' }, fromReplay, el('span', { text: 'Drafted while a replay played, not from live feeds' })));
  const who =[adv.proxy_flight, adv.callsign].filter(Boolean).join(' · ');
  out.push(
    el('p', { class: 'rv2__who' }, el('span', { text: who }), el('span', { class: 'rv2__ver', title: 'Version of this advisory', text: `v${adv.version}` })),
    el('h1', { id: 's-title', class: 'rv2__action', tabindex: '-1', text: actionShort(adv) }),
    entryLine(adv));
  // Cautions the validator or the clock raised stay in the main view, said on the item.
  const careful = needsCarefulRead(adv);
  const stale = anyStaleSource(adv);
  if (careful || stale) {
    out.push(el('p', { class: 'rv2__careful' }, icon('st-caution', 'st'),
      el('span', { text: [careful ? 'Needs a careful read: the code checks flagged this text (see Record)' : '', stale ? 'Some sources are stale (see Sources)' : ''].filter(Boolean).join('. ') + '.' })));
  }
  out.push(crewBox(adv, { reason: sheet.view === 'review' && reasonNeeded(adv) }),
    sheet.view === 'review' && reasonNeeded(adv) ? crewReasonField(adv) : null);

  out.push(checkSection(adv));
  out.push(
    el('h2', { class: 'ghead', text: adv.edited_body != null ? 'Text to approve · edited' : 'Text to approve' }),
    textBox(adv),
    writerLine(adv),
    el('button', { type: 'button', class: 'recordbtn', 'data-page': 'record' },
      el('span', {}, el('strong', { text: 'Record' }), el('span', { text: ' · ids, policy, history, audit' })), icon('i-chevron-right')));
  return out.filter(Boolean);
}

// "Check before you approve": the facts code computed, each once. The level and the ash band
// come from the Wall's picture, so they are drawn again when it arrives (refreshFacts).
function checkSection(adv) {
  const cone = coneFor(adv);
  const level = levelFact(adv);
  const ash = [band(cone), adv.volcano_name].filter(Boolean).join(' · ');
  const facts = el('dl', { class: 'facts' },
    level ? fact('Level', level) : null,
    ash ? fact('Ash', ash) : null,
    fact('Area', modeChip(adv), { page: 'area' }),
    fact('Sources', el('span', { 'data-slot': 'srcsum', text: sourcesFact(adv) }), { page: 'sources' }),
    adv.fuel_line ? fact('Fuel', adv.fuel && Number.isFinite(adv.fuel.fuel_kg) ? `+${Math.round(adv.fuel.fuel_kg).toLocaleString('en-US')} kg` : adv.fuel_line) : null,
    adv.reroute ? fact('Route', routeSummary(adv.reroute), { page: 'route' }) : null);
  const map = adv.reroute ? routeMap(adv.reroute, app.coneGeo.get(adv.cone_id), { mode: adv.plume_mode, small: true }) : null;
  return el('section', { id: 'why', class: 'check', 'aria-labelledby': 'check-title', 'data-key': `${level}|${ash}|${Boolean(map)}` },
    el('h2', { id: 'check-title', class: 'ghead', text: 'Check before you approve' }),
    facts,
    map ? el('figure', { class: 'rfig rfig--small' }, map) : null);
}

// The Wall's picture (aircraft levels, cones) arrived or moved: the Check facts follow, in place.
export function refreshFacts() {
  if (!sheet || sheet.page || (sheet.view !== 'review' && sheet.view !== 'closed')) return;
  const old = byId('why');
  if (!old) return;
  const next = checkSection(sheet.seen);
  if (next.dataset.key === old.dataset.key) return;
  const focused = old.contains(document.activeElement) ? document.activeElement.dataset.page : null;
  old.replaceWith(next);
  if (focused) next.querySelector(`[data-page="${focused}"]`)?.focus({ preventScroll: true });
  placeBar();
}

function routeSummary(r) {
  const bits = [r.side ? `${String(r.side).toLowerCase()} of the area` : 'around the area'];
  if (Number.isFinite(r.extra_min)) bits.push(`+${Math.round(r.extra_min)} min`);
  if (Number.isFinite(r.extra_nm)) bits.push(`+${Math.round(r.extra_nm)} NM`);
  return bits.join(' · ');
}

// --- the pages inside the review (› pushes a page; the decision bar stays) --------------------

function pageView(adv, page) {
  const head = el('div', { class: 'pagehead' },
    el('h1', { id: 's-title', class: 'pagehead__title', tabindex: '-1', text: page === 'sources' ? `Sources · ${sourceList(adv).length}` : PAGES[page] }));
  const body = { sources: sourcesPage, area: areaPage, route: routePage, record: recordPage }[page](adv);
  return [head, ...body];
}

function sourceAge(s, now) {
  const st = sourceTime(s);
  if (!st) return 'time not stated';
  return now === null ? `${st.kind} ${hhmmz(st.t)}` : `${st.kind} ${hhmmz(st.t)} · ${ago(now - st.t).replace(/ ago$/, '')}`;
}

function sourceItem(s, now) {
  const name = productName(s) || FEED_NAMES[s.feed] || String(s.feed);
  const binding = isBindingFeed(s.feed);
  const links = [];
  if (typeof s.url === 'string' && /^https:\/\//i.test(s.url)) {
    links.push(el('a', { href: s.url, target: '_blank', rel: 'noopener noreferrer' }, el('span', { text: 'Public source' }), icon('i-external-link')));
  }
  if (s.feed === 'winds') links.push(el('a', { href: 'https://open-meteo.com/', target: '_blank', rel: 'noopener noreferrer', text: 'Weather data by Open-Meteo.com' }));
  return el('li', {},
    el('details', { class: 'srcrow' },
      el('summary', {},
        el('span', { class: 'srcrow__name', text: name }),
        el('span', { class: 'srcrow__age', text: sourceAge(s, now) }),
        s.stale ? el('span', { class: 'srcrow__stale' }, icon('st-stale', 'st'), el('span', { text: 'stale' })) : null,
        icon('i-chevron-right', 'icon disclosure')),
      el('div', { class: 'srcrow__more' },
        el('p', { class: 'srcrow__feed', text: `${FEED_NAMES[s.feed] || s.feed}${binding ? ' · binding' : ''}` }),
        el('p', { class: 'mono srcrow__id', text: String(s.source_id || 'no product id') }),
        el('p', { class: 'fine', text: `issued ${s.issued_at ? ddhhmmz(s.issued_at) : 'not stated'} · fetched ${ddhhmmz(s.fetched_at)}` }),
        el('p', { class: 'mono srcrow__id', text: `#${s.sha256_short || String(s.sha256 || '').slice(0, 12)}` }),
        links.length ? el('p', { class: 'evidence__links' }, links) : null)));
}

function sourcesPage(adv) {
  const now = activeNow();
  const list = sourceList(adv);
  if (!list.length) return [el('p', { class: 'note', text: 'No sources are listed on this draft.' })];
  const official = list.filter((s) => isBindingFeed(s.feed));
  const context = list.filter((s) => !isBindingFeed(s.feed));
  return [
    official.length ? el('h2', { class: 'ghead', text: `Official · ${official.length}` }) : null,
    official.length ? el('ul', { class: 'srclist' }, official.map((s) => sourceItem(s, now))) : null,
    context.length ? el('h2', { class: 'ghead', text: `CONTEXT ONLY · ${context.length}` }) : null,
    context.length ? el('ul', { class: 'srclist' }, context.map((s) => sourceItem(s, now))) : null,
    el('p', { class: 'fine', text: 'Official products are binding. Context sources never shrink the area.' }),
  ].filter(Boolean);
}

function areaPage(adv) {
  const cone = coneFor(adv);
  const out = [
    el('p', { class: 'areapage__words' }, modeChip(adv)),
    el('p', { text: MODE_SENTENCE[adv.plume_mode] || '' }),
    el('p', { class: 'note', text: "TEPHRA's area is never smaller than the official area." }),
  ];
  const facts = el('dl', { class: 'facts' },
    band(cone) ? fact('Ash band', band(cone)) : null,
    fact('Volcano', adv.volcano_name || adv.volcano_id),
    fact('Set by', isStub(adv) ? 'code (TEPHRA Assistant off)' : 'code, from the official area and the Plume reader'));
  out.push(facts);
  return out;
}

function routePage(adv) {
  const r = adv.reroute;
  if (!r) return [el('p', { class: 'note', text: 'This advisory has no computed route.' })];
  const out = [];
  const map = routeMap(r, app.coneGeo.get(adv.cone_id), { mode: adv.plume_mode });
  if (map) out.push(el('figure', { class: 'rfig' }, map,
    el('figcaption', { class: 'rfig__cap' },
      el('span', { class: 'rleg' }, el('i', { class: 'rleg__sw rleg__sw--route' }), 'Route'),
      el('span', { class: 'rleg' }, el('i', { class: 'rleg__sw rleg__sw--direct' }), 'Straight line'),
      el('span', { class: 'rleg' }, el('i', { class: `rleg__sw rleg__sw--zone-${adv.plume_mode === 'OFFICIAL' ? 'official' : 'tephra'}` }), 'TEPHRA area'))));
  const stats = el('dl', { class: 'facts' });
  if (Number.isFinite(r.extra_nm)) stats.append(fact('Extra distance', `+${Math.round(r.extra_nm)} NM`));
  if (Number.isFinite(r.extra_min)) stats.append(fact('Extra time', `+${Math.round(r.extra_min)} min`));
  if (r.fuel && Number.isFinite(r.fuel.fuel_kg)) stats.append(fact('Extra fuel', `${Math.round(r.fuel.fuel_kg).toLocaleString('en-US')} kg`));
  if (r.side) stats.append(fact('Passes', `${r.side.toLowerCase()} of the area`));
  out.push(stats);
  if (r.route_string) out.push(el('h2', { class: 'ghead', text: 'Route string' }), el('pre', { class: 'acars rroute', text: r.route_string }));
  const bits = [r.kind === 'REJOIN_TRACK' ? 'Rejoins the present track beyond the area' : `Direct to ${r.end_icao || 'the destination'} around the area`];
  if (r.buffer_nm) bits.push(`area buffered by ${r.buffer_nm} NM`);
  if (Number.isFinite(r.fl)) bits.push(`flown at ${fl(r.fl)}`);
  out.push(fine(`${bits.join(' · ')}. Turn points are coordinates only: no named waypoint is invented.`));
  out.push(el('p', { class: 'rcode' }, codeChip('Route computed by code')));
  return out;
}

function draftedByValue(adv) {
  const out = [el('span', { class: 'v-strong', text: isStub(adv) ? 'Written by a code template (NO MODEL)' : `TEPHRA Assistant · ${adv.model_id}` })];
  out.push(fine(isStub(adv)
    ? 'Built from the official reports only. A code template wrote the text. Code writes every time, id and hash.'
    : 'Model-written body, checked by code. Times, ids and hashes are written by code.'));
  const notes = (adv.validation_notes || []).filter((n) => typeof n === 'string');
  if (notes.length) {
    const careful = needsCarefulRead(adv);
    out.push(el('div', { class: `notebox ${careful ? 'notebox--caution' : ''}` },
      el('p', { class: 'notebox__title' }, icon(careful ? 'st-caution' : 'st-info', 'st'),
        el('span', { text: careful ? 'Needs a careful read' : 'Validator notes' })),
      el('ul', {}, notes.map((n) => el('li', { text: n })))));
  }
  return out;
}

// When the text was written and where the flight stood: one line when both are of the same
// minute, else each with its own time (the text is never shown as newer than it is).
function draftedFacts(adv) {
  const drafted = hhmmz(draftedAt(adv));
  const facts = hhmmz(adv.created_at);
  const entry = adv.inside_now ? "inside TEPHRA's area" : `${adv.minutes_to_entry} min to entry, if track and level are held`;
  if (drafted === facts) return [fact('Drafted', adv.inside_now ? `at ${facts}, ${entry}` : `at ${facts} with ${entry}`)];
  return [fact('Drafted', `at ${drafted}`), fact('Entry', `at ${facts}, ${entry}`)];
}

function recordPage(adv) {
  const hex = String(adv.hex || '').toUpperCase();
  const costNote = typeof adv.cost_note === 'string' ? adv.cost_note.trim() : '';
  const history = el('ol', { class: 'timeline', 'data-slot': 'history' }, el('li', { class: 'timeline__loading', text: 'Loading history…' }));
  loadHistory(adv.id, history);
  return [
    el('dl', { class: 'facts facts--record' },
      fact('Advisory', el('span', { class: 'mono', text: `${adv.id} · v${adv.version}` })),
      fact('Flight', `${adv.proxy_flight}, proxy for ADS-B ${adv.callsign || 'no callsign'} (hex ${hex})${adv.type_icao ? ` · ${adv.type_icao}` : ''}`),
      ...draftedFacts(adv),
      fact('Action code', actionText(adv)),
      adv.fuel_line ? fact('Fuel formula', [el('span', { class: 'mono', text: adv.fuel_line }), fine('Simple TEPHRA formula, not airline tables')]) : null,
      costNote && costNote !== String(adv.fuel_line || '').trim() ? fact('Cost note', costNote) : null,
      fact('Drafted by', draftedByValue(adv)),
      adv.policy_version ? fact('Operator policy', [el('span', { class: 'mono', text: `${adv.policy_id} v${adv.policy_version}${adv.policy_hash ? ` #${adv.policy_hash}` : ''}` }),
        fine('Illustrative values, not an airline SRA, and not reviewed by an airline dispatcher')]) : null),
    el('h2', { class: 'ghead', text: 'Header written by code' }),
    el('pre', { class: 'acars acars--header', text: adv.header || '' }),
    el('h2', { class: 'ghead', text: 'History (audit log)' }),
    history,
    el('button', { type: 'button', class: 'linkbtn', 'data-askflight': '1' }, icon('i-chat'), el('span', { text: `Ask TEPHRA about ${adv.proxy_flight}` }), icon('i-chevron-right')),
  ].filter(Boolean);
}

const AUDIT_WORDS = {
  DRAFT_CREATED: ['i-system', 'Drafted by TEPHRA'],
  APPROVED: ['i-approved', 'Approved'],
  EDITED: ['i-approved', 'Approved with edits'],
  REJECTED: ['i-rejected', 'Rejected'],
  SUPERSEDED: ['i-superseded', 'Replaced by a newer draft'],
  OUTBOUND_QUEUED: ['i-outbound', "Queued on TEPHRA's outbound queue · not sent to any aircraft"],
  AI_FAILED: ['st-caution', 'TEPHRA Assistant gave no result: no substitute was made'],
  AI_FAILURE_HANDLED: ['st-ok', 'Handled by hand by a dispatcher'],
};

async function loadHistory(id, list) {
  const res = await api(PATHS.audit(id));
  if (!list.isConnected) return;
  const entries = res.ok && res.data && Array.isArray(res.data.entries) ? res.data.entries : null;
  if (!entries) {
    list.replaceChildren(el('li', { class: 'timeline__loading', text: res.status === 0 ? "Can't load the history while offline." : "Can't load the history." }));
    return;
  }
  const rows = entries
    .filter((e) => e && typeof e === 'object')
    .sort((a, b) => (parseTime(a.at) ?? 0) - (parseTime(b.at) ?? 0))
    .map((e) => {
      const [shape, word] = AUDIT_WORDS[e.action] || ['i-info', String(e.action)];
      const actor = e.actor === 'system' ? 'TEPHRA (code)' : deskName(e.actor);
      const detail = [];
      if (e.action === 'REJECTED' && e.after && typeof e.after.reject_reason === 'string') detail.push(`Reason: ${e.after.reject_reason}`);
      if (e.action === 'EDITED' && e.after && typeof e.after.edited_body === 'string') detail.push(`Edited text: ${e.after.edited_body}`);
      if (typeof e.note === 'string' && e.note) detail.push(e.note);
      if (e.action === 'DRAFT_CREATED' && e.model_id) detail.push(e.model_id === 'stub' ? 'Written by a code template (NO MODEL)' : `Drafted by TEPHRA Assistant · ${e.model_id}`);
      const hashes = Array.isArray(e.input_hashes) ? e.input_hashes.length : 0;
      return el('li', { class: `timeline__item timeline__item--${String(e.action).toLowerCase()}` },
        el('span', { class: 'timeline__time', text: hhmmz(e.at) }),
        el('span', { class: 'timeline__dot' }, icon(shape, 'st')),
        el('span', { class: 'timeline__text' },
          el('span', { class: 'timeline__what', text: `${word}${actor && e.actor !== 'system' ? ` · ${actor}` : ''}` }),
          detail.map((d) => el('span', { class: 'timeline__detail', text: d })),
          hashes ? el('span', { class: 'timeline__hash', text: `${hashes} input hash${hashes === 1 ? '' : 'es'} recorded` }) : null));
    });
  list.replaceChildren(...(rows.length ? rows : [el('li', { class: 'timeline__loading', text: 'No audit entries yet.' })]));
}

// --- edit and reject ------------------------------------------------------------------------

// `tried`: the "unchanged" note shows only after an approve attempt with no change (5.3).
function editProblem(text, { tried = false } = {}) {
  const clean = text.trim();
  if (!clean) return { tone: 'serious', text: 'The text cannot be empty.' };
  if (clean.length > BODY_MAX_CHARS) return { tone: 'serious', text: `Shorten the text by ${clean.length - BODY_MAX_CHARS} characters.` };
  if (clean.toUpperCase() === (sheet.seen.body || '').trim().toUpperCase()) {
    return tried ? { tone: 'info', text: 'Unchanged from the draft. Approve it as drafted, or change the text.' } : { tone: 'quiet', text: '' };
  }
  return null;
}

function editView(adv) {
  const area = el('textarea', {
    id: 'edit-body', class: 'field field--mono', rows: '7', spellcheck: 'false', autocapitalize: 'characters',
    autocomplete: 'off', 'aria-describedby': 'edit-count edit-msg', 'aria-label': `Text to approve for ${adv.proxy_flight} (upper case)`,
  });
  area.value = sheet.edit;
  const count = el('p', { id: 'edit-count', class: 'counter', 'aria-live': 'off' });
  const msg = el('div', { id: 'edit-msg', class: 'field-msg', 'aria-live': 'polite' });
  const update = () => {
    sheet.edit = area.value;
    const n = area.value.trim().length;
    count.textContent = `${n} / ${BODY_MAX_CHARS}`;
    count.dataset.level = n > BODY_MAX_CHARS ? 'serious' : n >= BODY_CAUTION_CHARS ? 'caution' : 'ok';
    const problem = editProblem(area.value, { tried: sheet.editTried });
    const lines = [];
    if (problem && problem.text) lines.push(el('p', { class: `msg msg--${problem.tone}` }, icon(problem.tone === 'serious' ? 'st-serious' : 'st-info', 'st'), el('span', { text: problem.text })));
    if (sheet.problems.length) {
      lines.push(el('p', { class: 'msg msg--serious' }, icon('st-serious', 'st'), el('span', { text: `Check the text: ${sheet.problems.join(' · ')}` })));
    }
    msg.replaceChildren(...lines);
    renderBar();
  };
  area.addEventListener('input', () => {
    sheet.problems = [];
    sheet.editTried = false;
    update();
  });
  sheet.refreshEdit = () => {
    if (area.isConnected) update();
    else render();
  };
  queueMicrotask(update);
  return [
    el('p', { class: 'rv2__who' }, el('span', { text: adv.proxy_flight }), el('span', { class: 'rv2__ver', text: `v${adv.version}` })),
    el('h1', { id: 's-title', class: 'rv2__action', tabindex: '-1', text: `Edit ${adv.proxy_flight}` }),
    el('h2', { class: 'ghead', text: 'Text to approve · editing' }),
    el('div', { class: 'textbox textbox--edit' }, textBox(adv, { body: false }), area),
    el('div', { class: 'editfoot' }, count,
      el('details', { class: 'disclose editfoot__drafted' },
        el('summary', {}, el('span', { text: 'Show drafted' }), icon('i-chevron-right', 'icon disclosure')),
        el('pre', { class: 'acars', text: adv.body }))),
    msg,
    el('p', { class: 'writer-note' }, aiMark(undefined, isStub(adv) ? null : adv.model_id), el('span', { text: ` · edited by ${app.me ? app.me.name : 'you'}` })),
    el('p', { class: 'note', text: 'Both versions are kept in the audit log. The header is written by code and cannot be edited.' }),
    reasonNeeded(adv) ? crewBox(adv, { reason: true }) : null,
    reasonNeeded(adv) ? crewReasonField(adv) : null,
  ].filter(Boolean);
}

function rejectView(adv) {
  const area = el('textarea', {
    id: 'reject-reason', class: 'field', rows: '2', maxlength: String(REASON_MAX_CHARS), autocomplete: 'off',
    'aria-describedby': 'reject-count reject-msg', required: true,
  });
  area.value = sheet.reason;
  const count = el('p', { id: 'reject-count', class: 'counter' });
  const msg = el('div', { id: 'reject-msg', class: 'field-msg', 'aria-live': 'polite' });
  const chipButtons = [];
  const update = () => {
    sheet.reason = area.value;
    const n = area.value.trim().length;
    count.textContent = n < REASON_MIN_CHARS ? `${n} / ${REASON_MAX_CHARS} · at least ${REASON_MIN_CHARS} characters` : `${n} / ${REASON_MAX_CHARS}`;
    // Quiet until the dispatcher has typed or tried to reject: an untouched field is not an error.
    count.dataset.level = n < REASON_MIN_CHARS && sheet.reasonTouched ? 'caution' : 'ok';
    for (const chip of chipButtons) chip.setAttribute('aria-pressed', String(area.value.includes(chip.dataset.reason)));
    msg.replaceChildren(...(sheet.error ? [el('p', { class: 'msg msg--serious' }, icon('st-serious', 'st'), el('span', { text: sheet.error }))] : []));
    renderBar();
  };
  area.addEventListener('input', () => {
    sheet.error = '';
    sheet.reasonTouched = true;
    update();
  });
  for (const text of REJECT_REASONS) {
    chipButtons.push(el('button', {
      type: 'button', class: 'reason-chip', 'aria-pressed': 'false', 'data-reason': text,
      onclick: () => {
        if (area.value.includes(text)) {
          area.focus();
          return;
        }
        const current = area.value.trim();
        area.value = current ? `${current}. ${text}` : text;
        sheet.error = '';
        sheet.reasonTouched = true;
        update();
        area.focus();
      },
    }, icon('i-plus', 'icon reason-chip__add'), icon('i-check', 'icon reason-chip__on'), el('span', { text })));
  }
  // "Other…" inserts nothing: it takes the dispatcher to the reason box to write their own
  const other = el('button', { type: 'button', class: 'reason-chip reason-chip--other', 'aria-controls': 'reject-reason', onclick: () => area.focus() },
    el('span', { text: 'Other…' }));
  const chips = el('div', { class: 'reason-chips', role: 'group', 'aria-label': 'Quick reasons (inserted into the text, still editable)' }, chipButtons, other);
  queueMicrotask(update);
  return [
    el('h1', { id: 's-title', class: 'rv2__action', tabindex: '-1', text: `Reject the draft for ${adv.proxy_flight}` }),
    el('label', { class: 'flabel', for: 'reject-reason', text: 'Reason (required)' }),
    chips,
    area,
    count,
    msg,
    el('p', { class: 'note', text: 'The reason is recorded in the audit log. A rejected draft is not queued.' }),
  ];
}

function diffRow(label, before, now, { shape = null } = {}) {
  if (before === now && label === 'Text') {
    // Identical text twice would take a screen of space and say nothing.
    return [
      el('span', { class: 'diff__label', text: label }),
      el('span', { class: 'diff__cell diff__same', text: 'Same text' }),
    ];
  }
  const changed = before !== now;
  return [
    el('span', { class: 'diff__label', text: label }),
    el('span', { class: 'diff__cell', text: before }),
    el('span', { class: `diff__cell ${changed ? 'is-changed' : ''}`.trim() },
      shape ? el('span', { class: 'diff__now' }, icon(shape, 'st'), el('span', { text: now })) : el('span', { text: now }),
      changed ? el('span', { class: 'diff__flag' }, icon('st-caution', 'st'), el('span', { text: 'changed' })) : null),
  ];
}

const entryWords = (a) => (a.inside_now ? 'Inside the ash now' : `${a.minutes_to_entry} min`);
const statusWord = (a) => statusView(a)[1];

function conflictView() {
  const { before, current } = sheet.conflict;
  const grid = el('div', { class: 'diff', role: 'table', 'aria-label': 'What changed' },
    el('span', { class: 'diff__head' }),
    el('span', { class: 'diff__head', text: `You saw (version ${before.version})` }),
    el('span', { class: 'diff__head', text: `Now (version ${current.version})` }),
    ...diffRow('Status', statusWord(before), statusWord(current), { shape: statusView(current)[0] }),
    ...diffRow('Action', actionShort(before), actionShort(current)),
    ...diffRow('Entry', entryWords(before), entryWords(current)),
    ...diffRow('Text', before.edited_body ?? before.body, current.edited_body ?? current.body));
  for (const cell of grid.children) cell.setAttribute('role', 'cell');
  const out = [
    el('h1', { id: 's-title', class: 'rv2__action', tabindex: '-1', text: `Review ${current.proxy_flight}` }),
    el('div', { class: 'banner banner--caution', role: 'alert' }, icon('st-caution', 'st'),
      el('p', { text: 'This advisory changed while you were reviewing it.' })),
  ];
  // The outcome first, as strong as the diff: shape, word, who and when.
  if (current.status !== 'DRAFT') {
    const tone = statusView(current)[2];
    out.push(el('div', { class: `outcome outcome--${tone}` }, statusBadge(current), el('p', { class: 'outcome__text', text: closedSentence(current) })));
  } else {
    out.push(el('p', { class: 'note', text: 'Your decision was not applied. Review the new version before deciding.' }));
  }
  out.push(grid);
  return out;
}

function goneView() {
  const out = [el('h1', { id: 's-title', class: 'rv2__action', tabindex: '-1', text: `Review ${sheet.seen.proxy_flight}` }),
    el('div', { class: 'banner banner--caution', role: 'alert' }, icon('st-caution', 'st'), el('p', { text: sheet.gone.title }))];
  if (sheet.gone.detail) out.push(el('p', { class: 'lead', text: sheet.gone.detail }));
  return out;
}

function closedSentence(adv) {
  const at = hhmmz(adv.decided_at || adv.updated_at);
  const who = deskName(adv.decided_by);
  switch (adv.status) {
    case 'APPROVED': return `${who || 'A dispatcher'} approved it at ${at}.`;
    case 'EDITED': return `${who || 'A dispatcher'} approved it with edits at ${at}.`;
    case 'REJECTED': return `${who || 'A dispatcher'} rejected it at ${at}${adv.reject_reason ? `: ${adv.reject_reason}` : '.'}`;
    case 'SUPERSEDED': return `TEPHRA replaced it with a newer draft at ${at}.`;
    default: return `Status ${adv.status} ${decidedLine(adv)}.`;
  }
}

// --- the decision bar (6.5): the primary, its hint, then two equal secondaries ----------------

function offlineAttrs(button) {
  if (app.offline) {
    button.setAttribute('aria-disabled', 'true');
    button.setAttribute('aria-describedby', 'approve-hint');
  }
  return button;
}

// "Approve: hold RFA1456 at FL226" (R12.10). The flight number never breaks inside.
const nowrap = (text) => el('span', { class: 'nowrap', text });
function approveWords(adv, edited, question = false) {
  const words = edited ? `Approve edited text for ${adv.proxy_flight}` : approveText(adv);
  const at = words.indexOf(adv.proxy_flight);
  const parts = at < 0 ? [words] : [words.slice(0, at), nowrap(adv.proxy_flight), words.slice(at + adv.proxy_flight.length)];
  if (question) parts.push('?');
  return parts.filter((p) => p !== '').map((p) => (typeof p === 'string' ? document.createTextNode(p) : p));
}

// Node.append would print a skipped (null) slot as the text "null".
const put = (node, ...kids) => append(node, kids);

// The confirm step names the entry and the version (5.3): "Entry due now · version 1". Computed by
// code from the draft's created_at and minutes_to_entry; never a model's time.
function confirmFacts(adv) {
  const st = entryState(adv, activeNow());
  const at = hhmmz(entryAt(adv));
  const entry = st.kind === 'inside' ? `Inside the ash at ${hhmmz(adv.created_at)}`
    : st.kind === 'ahead' ? `Enters in ${st.minutes} min, est. ${at}`
      : `Entry ${st.minutes ? `was due ${st.minutes} min ago` : 'due now'}, est. ${at}`;
  return `${entry} · version ${adv.version}`;
}

function busyLabel() {
  return { approve: 'Approving…', edit: 'Approving…', reject: 'Rejecting…' }[sheet.busy] || 'Sending…';
}

function spinnerButton(cls) {
  return el('button', { type: 'button', class: `${cls} is-busy`, disabled: true },
    el('span', { class: 'spinner', 'aria-hidden': 'true' }), el('span', { text: busyLabel() }));
}

function renderBar() {
  const bar = byId('sheet-actions');
  if (!bar || !sheet) return;
  const adv = sheet.seen;
  const inner = el('div', { class: 'actions__inner' });

  if (sheet.stamp) {
    put(inner, stampNode(sheet.stamp));
  } else if (sheet.view === 'closed' || sheet.view === 'gone' || (sheet.view === 'conflict' && sheet.conflict.current.status !== 'DRAFT')) {
    const newer = adv.superseded_by && app.drafts.get(adv.superseded_by);
    const approved = adv.status === 'APPROVED' || adv.status === 'EDITED';
    put(inner, approved ? el('button', { type: 'button', class: 'btn btn--neutral', 'data-draftmsg': adv.id, disabled: app.offline },
      el('span', { text: 'Draft crew briefing' }), icon('i-chevron-right')) : null,
    el('div', { class: 'secondary' },
      newer ? el('button', { type: 'button', class: 'btn btn--neutral', 'data-open': newer.id }, el('span', { text: 'Open the newer draft' })) : null,
      el('button', { type: 'button', class: 'btn btn--outline', 'data-back': '1' }, icon('i-chevron-left'), el('span', { text: 'Back to Decide' }))));
  } else if (sheet.view === 'conflict') {
    put(inner, el('button', { type: 'button', class: 'btn btn--neutral btn--primary', 'data-renew': '1' }, el('span', { text: 'Review the new version' })),
      el('button', { type: 'button', class: 'btn btn--outline', 'data-back': '1' }, el('span', { text: 'Back to Decide' })));
  } else if (sheet.view === 'reject') {
    const n = sheet.reason.trim().length;
    const reject = sheet.busy === 'reject'
      ? spinnerButton('btn btn--neutral btn--primary')
      : offlineAttrs(el('button', { type: 'button', class: 'btn btn--neutral btn--primary', 'data-decide': 'reject', 'aria-disabled': n < REASON_MIN_CHARS ? 'true' : null },
        el('span', { text: `Reject draft for ${adv.proxy_flight}` })));
    put(inner, reject,
      app.offline ? el('p', { class: 'approve__hint', id: 'approve-hint', text: OFFLINE_HINT }) : null,
      el('button', { type: 'button', class: 'btn btn--outline', 'data-go': 'review', disabled: Boolean(sheet.busy) }, el('span', { text: 'Cancel' })));
  } else if (sheet.bar === 'confirm') {
    const edited = sheet.view === 'edit';
    const go = sheet.busy
      ? spinnerButton('btn btn--approve')
      : offlineAttrs(el('button', { type: 'button', class: 'btn btn--approve', 'data-decide': edited ? 'edit' : 'approve' }, icon('i-check'), el('span', { text: 'Approve now' })));
    put(inner, el('div', { class: 'confirm', role: 'group', 'aria-labelledby': 'confirm-q' },
      el('p', { id: 'confirm-q', class: 'confirm__q', tabindex: '-1' }, approveWords(adv, edited, true)),
      el('p', { id: 'confirm-entry', class: 'confirm__facts', text: confirmFacts(adv) }),
      reasonNeeded(adv) ? el('p', { class: 'confirm__facts', text: `Reason (crew report of ash on this route): ${sheet.crewReason.trim()}` }) : null,
      el('p', { class: 'confirm__note', text: `Queued under ${app.me ? app.me.name : 'your name'} on TEPHRA's own outbound queue · nothing is sent to an aircraft.` }),
      el('div', { class: 'secondary' }, go,
        el('button', { type: 'button', class: 'btn btn--outline', 'data-confirm-back': '1', disabled: Boolean(sheet.busy) }, el('span', { text: 'Cancel' })))));
  } else {
    const edited = sheet.view === 'edit';
    const blockedByRule = adv.plume_mode === 'HYPOTHESIS' && !['MONITOR', 'HOLD'].includes(adv.action);
    const editBad = edited && editProblem(sheet.edit);
    const editBlocks = editBad && editBad.tone === 'serious';
    const attempt = (then) => () => {
      // An unchanged edit is said only now, at the attempt (5.3), once: by the field's own polite
      // message line, updated in place (re-rendering would replace the region and lose it).
      if (edited && editProblem(sheet.edit)) {
        sheet.editTried = true;
        if (sheet.refreshEdit) sheet.refreshEdit();
        else render();
        byId('edit-body')?.focus();
        return;
      }
      then();
    };
    let primary;
    if (sheet.busy) primary = spinnerButton('approve');
    else {
      primary = holdButton({
        label: () => approveWords(adv, edited),
        onHold: attempt(() => decide(edited ? 'edit' : 'approve')),
        onTap: attempt(() => openConfirm()),
        onEarlyRelease: (hint) => setHint(hint),
      });
      offlineAttrs(primary);
      // Long outcomes ("CHANGE LEVEL FL300–FL340") step down a size on phones: two lines, not three.
      if (primary.querySelector('.approve__label').textContent.length > 34) primary.classList.add('approve--long');
      if (blockedByRule || editBlocks || reasonShort(adv)) primary.setAttribute('aria-disabled', 'true');
      // A tap on the blocked button says why and goes to the reason box.
      if (!blockedByRule && !editBlocks && reasonShort(adv)) primary.addEventListener('click', crewReasonMissing);
    }
    const hint = el('p', { class: 'approve__hint', id: 'approve-hint' }, el('span', { text: 'Hold to approve, or tap to confirm.' }));
    if (app.offline) hint.replaceChildren(el('span', { class: 'hint-early', text: OFFLINE_HINT }));
    else if (sheet.hint) hint.replaceChildren(el('span', { class: 'hint-early', text: sheet.hint }));
    else if (reasonShort(adv)) hint.replaceChildren(el('span', { class: 'hint-early', text: CREW_REASON_HINT }));
    if (blockedByRule) {
      hint.replaceChildren(el('span', { class: 'hint-early', text: 'HYPOTHESIS allows only Keep watching or Hold: this draft cannot be approved. Reject it.' }));
    }
    if (!primary.hasAttribute('aria-describedby')) primary.setAttribute('aria-describedby', 'approve-hint');
    put(inner, primary, hint, el('div', { class: 'secondary' },
      el('button', { type: 'button', class: 'btn btn--outline', 'data-go': edited ? 'review' : 'edit', disabled: Boolean(sheet.busy) },
        edited ? null : icon('i-pencil'), el('span', { text: edited ? 'Stop editing' : 'Edit text' })),
      el('button', { type: 'button', class: 'btn btn--outline', 'data-go': 'reject', disabled: Boolean(sheet.busy) }, el('span', { text: 'Reject…' }))));
  }
  const hadFocus = bar.contains(document.activeElement) ? document.activeElement : null;
  const focusKey = hadFocus
    ? (hadFocus.id === 'decided-stamp' ? 'stamp' : hadFocus.dataset.decide || hadFocus.dataset.go || (hadFocus.classList.contains('approve') ? 'approve' : ''))
    : '';
  bar.replaceChildren(inner);
  if (focusKey) {
    const again = focusKey === 'approve' ? bar.querySelector('.approve')
      : focusKey === 'stamp' ? byId('decided-stamp')
        : bar.querySelector(`[data-decide="${focusKey}"], [data-go="${focusKey}"]`);
    if (again) again.focus({ preventScroll: true });
  }
  app.hub.measureBar();
}

// 10.8: the human moment. After a decision succeeds the bar shows what was decided, by whom and
// when, for --dur-stamp before the sheet moves on (desk.js times it). Not interactive.
const STAMP_VIEW = {
  APPROVED: ['i-approved', 'Approved', 'queued, not sent to any aircraft'],
  EDITED: ['i-approved', 'Approved with your edits', 'queued, not sent to any aircraft'],
  REJECTED: ['i-rejected', 'Rejected', 'reason recorded, nothing queued'],
};

function stampNode(adv) {
  const [shape, word, tail] = STAMP_VIEW[adv.status] || STAMP_VIEW.APPROVED;
  const who = deskName(adv.decided_by) || (app.me ? app.me.name : '');
  return el('div', { class: `decided-stamp decided-stamp--${adv.status === 'REJECTED' ? 'rejected' : 'approved'}`, tabindex: '-1', id: 'decided-stamp' },
    el('p', { class: 'decided-stamp__word' }, icon(shape, 'icon decided-stamp__icon'), el('span', { text: word })),
    el('p', { class: 'decided-stamp__what' }, nowrap(actionShort(adv)), document.createTextNode(' for '), nowrap(adv.proxy_flight)),
    el('p', { class: 'decided-stamp__who', text: `${who ? `${who} · ` : ''}${hhmmz(adv.decided_at || adv.updated_at)} · ${tail}` }));
}

export function showStamp(adv) {
  if (!sheet || sheet.id !== adv.id) return;
  sheet.stamp = adv;
  renderBar();
  const stamp = byId('decided-stamp');
  if (stamp) stamp.focus({ preventScroll: true });
}

// --- the receipt line (D3, 6.9): one line per decision, pinned above the next review --------
// It replaces the 15 s toast: it stays until the next decision, or until the dispatcher closes
// the review. "Audit" opens in place and shows only the audit entry the server lists for this
// decision; nothing is put in its place while it is not listed yet.

const receiptSlot = el('div', { class: 'sheet__receipts', id: 'sheet-receipts' });
let receipt = null; // { adv, open, line }

export function receiptWords(adv) {
  const at = hhmmz(adv.decided_at || adv.updated_at);
  const who = deskName(adv.decided_by) || (app.me ? app.me.name : '');
  if (adv.status === 'APPROVED') return `Approved: ${approveText(adv).replace(/^Approve: /, '')} · ${at} · ${who}`;
  if (adv.status === 'EDITED') return `Approved with your edits: ${adv.proxy_flight} · both versions are in the audit log · ${at} · ${who}`;
  return `Rejected: ${adv.proxy_flight} · reason recorded · ${at} · ${who}`;
}

export function setReceipt(adv) {
  receipt = adv ? { adv, open: false, line: null } : null;
  placeReceipt();
}

function receiptNode() {
  const { adv, open, line } = receipt;
  const approved = adv.status === 'APPROVED' || adv.status === 'EDITED';
  return el('div', { id: 'receipt', class: `receipt receipt--${approved ? 'ok' : 'rejected'}` },
    el('p', { class: 'receipt__line' }, icon(approved ? 'i-check' : 'i-x', 'st'), el('span', { text: receiptWords(adv) })),
    el('p', { class: 'receipt__links' },
      approved ? el('button', { type: 'button', class: 'linkbtn', 'data-draftmsg': adv.id, 'data-receipt': '1' }, el('span', { text: 'Draft crew briefing' }), icon('i-chevron-right')) : null,
      el('button', { type: 'button', class: 'linkbtn', 'data-audit': '1', 'aria-expanded': String(open), 'aria-controls': 'receipt-audit' },
        el('span', { text: 'Audit' }), icon('i-chevron-right', 'icon disclosure'))),
    open ? el('p', { id: 'receipt-audit', class: 'receipt__audit', text: line || 'Loading the audit line…' }) : null);
}

function placeReceipt() {
  const decide = byId('q-receipt');
  const host = sheet ? receiptSlot : decide;
  const other = sheet ? decide : receiptSlot;
  if (other) other.replaceChildren();
  if (!host) return;
  const focused = host.contains(document.activeElement) ? (document.activeElement.dataset.audit ? '[data-audit]' : '[data-draftmsg]') : null;
  host.replaceChildren(...(receipt ? [receiptNode()] : []));
  if (focused) host.querySelector(focused)?.focus({ preventScroll: true });
  if (sheet) placeBar();
}

async function toggleAudit() {
  if (!receipt) return;
  receipt.open = !receipt.open;
  placeReceipt();
  if (!receipt.open) return;
  const mine = receipt;
  const res = await api(PATHS.audit(mine.adv.id));
  if (receipt !== mine) return;
  const entries = res.ok && res.data && Array.isArray(res.data.entries) ? res.data.entries : [];
  const entry = entries.find((e) => e && e.action === mine.adv.status);
  mine.line = entry ? `AUDIT ${entry.action} ${entry.actor} ${hhmmz(entry.at)}`
    : res.ok ? 'Audit line not listed yet. It appears in Record when the server lists it.' : "Can't load the audit line now. It appears in Record when the server lists it.";
  placeReceipt();
}

let hintTimer = 0;
function setHint(text) {
  sheet.hint = text;
  renderBar();
  announce(text);
  window.clearTimeout(hintTimer);
  hintTimer = window.setTimeout(() => {
    if (!sheet) return;
    sheet.hint = '';
    renderBar();
  }, 4000);
}

function openConfirm() {
  if (!sheet || app.offline) return;
  sheet.bar = 'confirm';
  sheet.confirmAt = performance.now();
  renderBar();
  const q = byId('confirm-q');
  if (q) q.focus({ preventScroll: true });
}

function goPage(page) {
  if (!sheet) return;
  sheet.page = page;
  const was = page ? null : sheet.lastPage;
  sheet.lastPage = page;
  render();
  if (page) focusTitle();
  else {
    const back = was && byId('sheet').querySelector(`.sheet__body [data-page="${was}"]`);
    if (back) back.focus({ preventScroll: false });
    else focusTitle();
  }
}

// --- events (delegated from desk.js) ---------------------------------------------------------

export function onSheetClick(event) {
  const target = event.target.closest('button, a');
  if (target && target.closest('#receipt')) {
    if (target.dataset.audit) toggleAudit();
    else if (target.dataset.draftmsg) app.hub.draftMessages({ advisory_id: target.dataset.draftmsg }, target, { openFirst: true });
    return true;
  }
  if (!sheet) return false;
  if (!target || !byId('sheet').contains(target)) return false;
  if (target.dataset.draftmsg) {
    app.hub.draftMessages({ advisory_id: target.dataset.draftmsg }, target, { openFirst: true });
    return true;
  }
  if (target.dataset.page) {
    goPage(target.dataset.page);
    return true;
  }
  if (target.dataset.skip) {
    app.hub.skipTo(target.dataset.skip);
    return true;
  }
  if (target.dataset.askflight) {
    app.hub.askAbout(sheet.seen);
    return true;
  }
  if (target.dataset.back) {
    if (sheet.view === 'edit' || sheet.view === 'reject') goView('review');
    else if (sheet.page) goPage(null);
    else app.hub.closeReview();
    return true;
  }
  if (target.dataset.go) {
    goView(target.dataset.go);
    return true;
  }
  if (target.dataset.confirmBack) {
    sheet.bar = 'decide';
    renderBar();
    const primary = byId('sheet-actions').querySelector('.approve');
    if (primary) primary.focus({ preventScroll: true });
    return true;
  }
  if (target.dataset.renew) {
    const current = app.drafts.get(sheet.id) || sheet.conflict.current;
    openSheet(current);
    return true;
  }
  if (target.dataset.decide) {
    if (target.getAttribute('aria-disabled') === 'true') {
      if (target.dataset.decide === 'reject' && !app.offline) {
        sheet.error = `Give a reason of at least ${REASON_MIN_CHARS} characters.`;
        sheet.reasonTouched = true;
        render();
        byId('reject-reason').focus();
      }
      return true;
    }
    // A fast second tap on the spot where the primary was must not approve.
    if (sheet.bar === 'confirm' && performance.now() - sheet.confirmAt < GHOST_TAP_MS) return true;
    decide(target.dataset.decide);
    return true;
  }
  return false;
}

function goView(view) {
  if (!sheet || sheet.busy) return;
  sheet.view = view;
  sheet.page = null;
  sheet.bar = 'decide';
  sheet.error = '';
  sheet.problems = [];
  sheet.hint = '';
  sheet.editTried = false;
  sheet.reasonTouched = Boolean(sheet.reason.trim());
  render();
  if (view === 'edit') byId('edit-body').focus();
  else if (view === 'reject') byId('reject-reason').focus();
  else focusTitle();
}

async function decide(kind) {
  if (!sheet || sheet.busy || app.offline) return;
  const adv = sheet.seen;
  let body = { version: adv.version };
  if (kind !== 'reject' && reasonShort(adv)) {
    crewReasonMissing();
    return;
  }
  if (kind === 'edit') {
    if (editProblem(sheet.edit)) return;
    body = { version: adv.version, body: sheet.edit.trim() };
  } else if (kind === 'reject') {
    if (sheet.reason.trim().length < REASON_MIN_CHARS) return;
    body = { version: adv.version, reason: sheet.reason.trim() };
  }
  if (kind !== 'reject' && reasonNeeded(adv)) body.reason = sheet.crewReason.trim();
  const mine = sheet;
  mine.busy = kind;
  renderBar();
  const res = await app.hub.decide(kind, adv, body);
  if (sheet !== mine) return;
  mine.busy = false;
  if (res.ok) return; // desk.js shows the stamp, moves on and pins the receipt
  if (res.status === 401 || res.status === 0) {
    renderBar();
    return;
  }
  const code = errorCode(res);
  if (code === 'version_conflict' && res.data && res.data.current) {
    sheet.conflict = { before: adv, current: res.data.current };
    sheet.view = 'conflict';
    sheet.page = null;
    render();
    focusTitle();
    announce('This advisory changed while you were reviewing it.');
    return;
  }
  if (code === 'invalid_transition') {
    const known = app.closed.get(adv.id);
    sheet.gone = { title: 'This advisory is no longer a draft.', detail: known ? closedSentence(known) : '' };
    sheet.view = 'gone';
    sheet.page = null;
    render();
    focusTitle();
    return;
  }
  if (res.status === 404) {
    sheet.gone = { title: 'This advisory no longer exists.', detail: '' };
    sheet.view = 'gone';
    sheet.page = null;
    render();
    focusTitle();
    return;
  }
  if (res.status === 422 && code === 'reason_required') {
    // The server knows of a crew report flag this page had not drawn yet: ask for the reason.
    sheet.crewForced = true;
    sheet.bar = 'decide';
    sheet.page = null;
    sheet.crewError = `${(res.data && res.data.detail) || 'A crew reported ash on this route'}. Give a reason of at least ${CREW_REASON_MIN} characters.`;
    render();
    const f = byId('crew-reason');
    if (f) f.focus();
    announce(sheet.crewError);
    return;
  }
  if (res.status === 422) {
    const list = problems(res);
    if (kind === 'edit') {
      sheet.problems = list.length ? list : ['the text was not accepted'];
      render();
      byId('edit-body').focus();
    } else if (kind === 'reject') {
      sheet.error = list.length ? `Check the reason: ${list.join(' · ')}` : `Give a reason of at least ${REASON_MIN_CHARS} characters.`;
      render();
      byId('reject-reason').focus();
    }
    return;
  }
  sheet.hint = `Not saved: ${(res.data && res.data.detail) || `HTTP ${res.status}`}. Try again.`;
  sheet.bar = 'decide';
  renderBar();
}

export const sheetEditing = () => Boolean(sheet && (sheet.view === 'edit' || sheet.view === 'reject'));

// Escape steps back one level inside the sheet (review 2, item 9): the confirm bar to the decide
// bar, a page to the review, Edit or Reject to the review (their text is kept). True when it stepped.
export function sheetStepBack() {
  if (!sheet || sheet.busy) return false;
  if (sheet.bar === 'confirm') {
    sheet.bar = 'decide';
    renderBar();
    const primary = byId('sheet-actions').querySelector('.approve');
    if (primary) primary.focus({ preventScroll: true });
    return true;
  }
  if (sheet.page) {
    goPage(null);
    return true;
  }
  if (sheet.view === 'edit' || sheet.view === 'reject') {
    goView('review');
    return true;
  }
  return false;
}
export const EARLY_HINT = EARLY_RELEASE_HINT;
