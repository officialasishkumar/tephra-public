// The review sheet (docs/UI-DESIGN.md 10.4-10.8): a check-answers list for one draft, the
// decision bar (hold or tap-and-confirm), edit, reject, the version-conflict diff, and the
// advisory's audit history. Full screen on phones, the right pane from 1100 px.

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
import { announce, append, byId, el, icon, isWide } from './dom.js';
import {
  ACTION_ICON,
  FEED_NAMES,
  MODE_SENTENCE,
  actionSentence,
  actionText,
  activeNow,
  band,
  bySourceRank,
  ddhhmmz,
  deskName,
  entryState,
  fl,
  hhmmz,
  isStub,
  parseTime,
} from './format.js';
import { EARLY_RELEASE_HINT, holdButton } from './hold.js';
import { anyStaleSource, coneFor, decidedLine, modeChip, needsCarefulRead, replayChip, statusBadge, statusView } from './queue.js';
import { app } from './state.js';
import { routeMap } from './route.js';
import { codeChip } from './ui.js';

const GHOST_TAP_MS = 450;
const OFFLINE_NOTE = "You're offline. Can't approve right now: reconnect to decide. Drafts stay readable.";
const QUEUE_SENTENCE = "Queues this text on TEPHRA's own outbound queue; nothing is sent to an aircraft.";
const REJECT_REASONS = [
  'Flight already clear of the area',
  'Level already outside the hazard band',
  'Duplicate of another advisory',
  'Hazard data look wrong',
];

// sheet: { id, seen, view, bar, busy, edit, reason, error, problems, conflict, confirmAt, hint,
//   reasonTouched, stamp }
let sheet = null;

export const sheetOpenFor = () => (sheet ? sheet.id : null);
export const sheetBusy = () => Boolean(sheet && sheet.busy);

export function openSheet(adv, { focus = true } = {}) {
  sheet = {
    id: adv.id,
    seen: adv,
    view: adv.status === 'DRAFT' ? 'review' : 'closed',
    bar: 'decide',
    busy: false,
    edit: adv.edited_body ?? adv.body,
    reason: '',
    error: '',
    problems: [],
    conflict: null,
    confirmAt: 0,
    hint: '',
    reasonTouched: false,
    stamp: null,
  };
  render();
  if (focus) focusTitle();
}

export function closeSheet() {
  sheet = null;
  const host = byId('sheet');
  host.replaceChildren();
  host.hidden = true;
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
  renderBar();
  updateSheetTimes();
}

export function updateSheetTimes() {
  if (!sheet) return;
  const slot = byId('sheet').querySelector('[data-slot="entry"]');
  if (slot) slot.replaceChildren(...entryValue(sheet.seen));
}

// --- render ---------------------------------------------------------------------------

function render() {
  const host = byId('sheet');
  host.hidden = false;
  const adv = sheet.seen;
  const titles = {
    review: `Review ${adv.proxy_flight}`,
    closed: `${adv.proxy_flight}`,
    edit: `Edit ${adv.proxy_flight}`,
    reject: `Reject ${adv.proxy_flight}`,
    conflict: `Review ${adv.proxy_flight}`,
    gone: `Review ${adv.proxy_flight}`,
  };
  const head = el(
    'div',
    { class: 'sheet__head' },
    el('button', { type: 'button', class: 'sheet__back', 'data-back': '1' }, icon('i-chevron-left'),
      el('span', { text: sheet.view === 'edit' || sheet.view === 'reject' ? 'Review' : 'Drafts' })),
    el('h1', { id: 's-title', class: 'sheet__title', tabindex: '-1', text: titles[sheet.view] }),
    el('span', { class: 'sheet__ver', title: 'Version of this advisory',
      text: sheet.view === 'conflict' && sheet.conflict ? `v${sheet.conflict.before.version} → v${sheet.conflict.current.version}` : `v${adv.version}` }),
  );
  const body = el('div', { class: 'sheet__body' });
  if (sheet.view === 'edit') body.append(...editView(adv));
  else if (sheet.view === 'reject') body.append(...rejectView(adv));
  else if (sheet.view === 'conflict') body.append(...conflictView());
  else if (sheet.view === 'gone') body.append(...goneView());
  else body.append(...reviewView(adv));
  const bar = el('div', { class: 'actions', id: 'sheet-actions' });
  host.replaceChildren(head, body, bar);
  host.dataset.view = sheet.view;
  renderBar();
}

function row(label, value, { stack = false, cls = '' } = {}) {
  return el('div', { class: `srow ${stack ? 'srow--stack' : ''} ${cls}`.trim() },
    el('dt', { text: label }), el('dd', {}, value));
}

const fine = (text) => el('span', { class: 'fine', text });

function entryValue(adv) {
  const st = entryState(adv, activeNow());
  const drafted = hhmmz(adv.created_at);
  if (st.kind === 'inside') {
    return [el('span', { class: 'entry-big entry-big--inside' }, icon('st-inside', 'st'), el('span', { text: 'INSIDE NOW' })),
      fine(`Inside TEPHRA's area when drafted at ${drafted}`)];
  }
  if (st.kind === 'ahead') {
    return [el('span', { class: 'entry-big', text: `Enters TEPHRA's area in ${st.minutes} min` }),
      fine(`Drafted at ${drafted} with ${adv.minutes_to_entry} min to entry, if track and level are held`)];
  }
  return [el('span', { class: 'entry-big entry-big--due' }, icon('st-caution', 'st'),
    el('span', { text: st.minutes ? `Entry was due ${st.minutes} min ago` : 'Entry is due now' })),
  fine(`Drafted at ${drafted} with ${adv.minutes_to_entry} min to entry. Check the live position on the Wall.`)];
}

function flightValue(adv) {
  const hex = String(adv.hex || '').toUpperCase();
  const parts = [`Proxy for ADS-B ${adv.callsign || 'no callsign'} (hex ${hex})`];
  if (adv.type_icao) parts.push(adv.type_icao);
  return [el('span', { class: 'v-strong', text: adv.proxy_flight }), fine(parts.join(' · '))];
}

function sourcesValue(adv) {
  const sources = [...(adv.sources || [])].filter((s) => s && typeof s === 'object').sort(bySourceRank);
  const summary = el('summary', {},
    icon('i-chevron-right', 'icon disclosure'),
    el('span', { text: `Evidence: ${sources.length} source${sources.length === 1 ? '' : 's'}` }),
    anyStaleSource(adv) ? el('span', { class: 'chip chip--caution chip--sm' }, icon('st-stale', 'st'), el('span', { text: 'stale' })) : null);
  const list = el('ol', { class: 'evidence' });
  for (const s of sources) {
    const binding = s.feed === 'sigmet' || String(s.feed).startsWith('vaac');
    const item = el('li', { class: `evidence__item ${binding ? 'is-binding' : ''}`.trim() },
      el('p', { class: 'evidence__head' },
        el('span', { class: `feed feed--${binding ? 'official' : s.feed === 'vona' ? 'observer' : 'context'}`, text: FEED_NAMES[s.feed] || String(s.feed) }),
        binding ? el('span', { class: 'caps evidence__binding', text: 'Binding' }) : null,
        s.stale ? el('span', { class: 'chip chip--caution chip--sm' }, icon('st-stale', 'st'), el('span', { text: 'stale' })) : null),
      el('p', { class: 'evidence__id', text: String(s.source_id || '') }),
      el('p', { class: 'evidence__times' },
        el('span', { text: `issued ${s.issued_at ? ddhhmmz(s.issued_at) : 'not stated'}` }),
        el('span', { text: ` · fetched ${ddhhmmz(s.fetched_at)}` }),
        el('span', { class: 'hash', text: ` · #${s.sha256_short || String(s.sha256 || '').slice(0, 12)}` })),
    );
    const links = el('p', { class: 'evidence__links' });
    if (typeof s.url === 'string' && /^https:\/\//i.test(s.url)) {
      links.append(el('a', { href: s.url, target: '_blank', rel: 'noopener noreferrer' },
        el('span', { text: 'Public source' }), icon('i-external-link')));
    }
    if (s.feed === 'winds') {
      links.append(el('a', { href: 'https://open-meteo.com/', target: '_blank', rel: 'noopener noreferrer', text: 'Weather data by Open-Meteo.com' }));
    }
    if (links.childNodes.length) item.append(links);
    list.append(item);
  }
  if (!sources.length) list.append(el('li', { class: 'evidence__item', text: 'No sources are listed on this draft.' }));
  return el('details', { class: 'disclose' }, summary, list);
}

// The computed lateral route (WP1): a sketch, the route string to copy, and what it costs.
function rerouteValue(adv, cone) {
  const r = adv.reroute;
  const out = [];
  const map = routeMap(r, app.coneGeo.get(adv.cone_id), { mode: adv.plume_mode });
  if (map) out.push(el('figure', { class: 'rfig' }, map,
    el('figcaption', { class: 'rfig__cap' },
      el('span', { class: 'rleg' }, el('i', { class: 'rleg__sw rleg__sw--route' }), 'Route'),
      el('span', { class: 'rleg' }, el('i', { class: 'rleg__sw rleg__sw--direct' }), 'Straight line'),
      el('span', { class: 'rleg' }, el('i', { class: `rleg__sw rleg__sw--zone-${adv.plume_mode === 'OFFICIAL' ? 'official' : 'tephra'}` }), 'TEPHRA area'))));
  const stats = el('dl', { class: 'rstats' });
  const stat = (k, v) => stats.append(el('div', { class: 'rstat' }, el('dt', { text: k }), el('dd', { text: v })));
  if (Number.isFinite(r.extra_nm)) stat('Extra distance', `+${Math.round(r.extra_nm)} NM`);
  if (Number.isFinite(r.extra_min)) stat('Extra time', `+${Math.round(r.extra_min)} min`);
  if (r.fuel && Number.isFinite(r.fuel.fuel_kg)) stat('Extra fuel', `${Math.round(r.fuel.fuel_kg).toLocaleString('en-US')} kg`);
  if (r.side) stat('Passes', `${r.side.toLowerCase()} of the area`);
  out.push(stats);
  if (r.route_string) {
    out.push(el('p', { class: 'caps rroute__k', text: 'Route string' }), el('pre', { class: 'acars rroute', text: r.route_string }));
  }
  const bits = [r.kind === 'REJOIN_TRACK' ? 'Rejoins the present track beyond the area' : `Direct to ${r.end_icao || 'the destination'} around the area`];
  if (r.buffer_nm) bits.push(`area buffered by ${r.buffer_nm} NM`);
  if (Number.isFinite(r.fl)) bits.push(`flown at ${fl(r.fl)}`);
  out.push(fine(`${bits.join(' · ')}. Turn points are coordinates only: no named waypoint is invented.`));
  out.push(el('p', { class: 'rcode' }, codeChip('Route computed by code')));
  return out;
}

function draftedByValue(adv) {
  const who = isStub(adv)
    ? el('span', { class: 'v-strong' }, 'Template · NO MODEL')
    : el('span', { class: 'v-strong' }, `${adv.model_id} · AI-drafted`);
  const out = [who];
  out.push(fine(isStub(adv) ? 'NO MODEL: official products only. Code templates wrote this text.' : 'Model-written body; times, ids and hashes are written by code.'));
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

function historyValue(adv) {
  const list = el('ol', { class: 'timeline', 'data-slot': 'history' }, el('li', { class: 'timeline__loading', text: 'Loading history…' }));
  const details = el('details', { class: 'disclose' },
    el('summary', {}, icon('i-chevron-right', 'icon disclosure'), el('span', { text: 'History (audit log)' })), list);
  details.addEventListener('toggle', () => {
    if (details.open) loadHistory(adv.id, list);
  });
  return details;
}

const AUDIT_WORDS = {
  DRAFT_CREATED: ['i-system', 'Drafted by TEPHRA'],
  APPROVED: ['i-approved', 'Approved'],
  EDITED: ['i-approved', 'Approved with edits'],
  REJECTED: ['i-rejected', 'Rejected'],
  SUPERSEDED: ['i-superseded', 'Replaced by a newer draft'],
  OUTBOUND_QUEUED: ['i-outbound', "Queued on TEPHRA's outbound queue · not sent to any aircraft"],
  AI_FAILED: ['st-caution', 'AI unavailable: no substitute was made'],
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
      if (e.action === 'DRAFT_CREATED' && e.model_id) detail.push(e.model_id === 'stub' ? 'Template · NO MODEL' : `${e.model_id} · AI-drafted`);
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

function hypothesisBanner() {
  return el('div', { class: 'banner banner--hypothesis', role: 'note' }, icon('st-caution', 'st'),
    el('p', {}, el('strong', { text: 'HYPOTHESIS: ' }), MODE_SENTENCE.HYPOTHESIS));
}

function reviewView(adv) {
  const out = [];
  if (sheet.view === 'closed') {
    out.push(el('div', { class: `banner banner--closed banner--${adv.status.toLowerCase()}`, role: 'note' },
      statusBadge(adv), el('p', { text: closedSentence(adv) })));
  }
  if (adv.plume_mode === 'HYPOTHESIS') out.push(hypothesisBanner());
  if (adv.replay) {
    out.push(el('p', { class: 'replay-note' }, replayChip(), el('span', { text: 'Drafted from recorded feeds.' })));
  }
  const cone = coneFor(adv);
  const text = adv.edited_body ?? adv.body;
  // The words being queued sit right under the action, so they share the screen with Approve.
  const costNote = typeof adv.cost_note === 'string' ? adv.cost_note.trim() : '';
  const dl = el('dl', { class: 'summary' },
    row('Flight', [...flightValue(adv), el('button', { type: 'button', class: 'linkbtn', 'data-askflight': '1' }, icon('i-chat'), el('span', { text: 'Ask TEPHRA about this flight' }))]),
    row('Action', el('span', { class: 'v-action' }, icon(ACTION_ICON[adv.action] || 'i-arrow-right'), el('span', { text: actionSentence(adv) }))),
    row(adv.edited_body != null ? 'Advisory text (edited)' : 'Advisory text', [
      el('pre', { class: 'acars acars--body', text }),
      sheet.view === 'review' ? el('button', { type: 'button', class: 'linkbtn', 'data-go': 'edit' }, icon('i-pencil'), el('span', { text: 'Edit text' })) : null,
    ], { stack: true, cls: 'srow--text' }),
    adv.reroute ? row('Route', rerouteValue(adv, cone), { stack: true, cls: 'srow--route' }) : null,
    row('Entry', el('span', { class: 'v-entry', 'data-slot': 'entry' }, entryValue(adv))),
    band(cone) ? row('Hazard band', [el('span', { class: 'v-band', text: band(cone) }), fine("TEPHRA's cautious area, vertical extent")]) : null,
    row('TEPHRA area', [modeChip(adv, { long: true, bare: true }), fine(MODE_SENTENCE[adv.plume_mode] || '')]),
    row('Fuel and time', [el('span', { class: 'mono v-fuel', text: adv.fuel_line || 'No estimate: the formula covers holds and diversions only' }),
      fine('Simple TEPHRA formula, not airline tables')], { stack: true }),
    // On diversions the cost note often repeats the fuel line word for word.
    costNote && costNote !== String(adv.fuel_line || '').trim() ? row('Cost note', el('span', { text: costNote })) : null,
    row('Drafted by', draftedByValue(adv)),
    // The policy this draft was made under, which can differ from the one in force now.
    adv.policy_version ? row('Operator policy', [
      el('span', { class: 'mono', text: `${adv.policy_id} v${adv.policy_version}${adv.policy_hash ? ` #${adv.policy_hash}` : ''}` }),
      fine('Illustrative values, not an airline SRA; not reviewed by an airline dispatcher')]) : null,
    // The disclosure's own summary names these rows, so their labels are for screen readers only.
    row('Evidence', sourcesValue(adv), { stack: true, cls: 'srow--disclose' }),
    row('Header', el('details', { class: 'disclose' },
      el('summary', {}, icon('i-chevron-right', 'icon disclosure'), el('span', { text: 'Advisory header (written by code)' })),
      el('pre', { class: 'acars acars--header', text: adv.header || '' })), { stack: true, cls: 'srow--disclose' }),
    row('History', historyValue(adv), { stack: true, cls: 'srow--disclose' }),
  );
  out.push(dl);
  return out;
}

function editProblem(text) {
  const clean = text.trim();
  if (!clean) return { tone: 'serious', text: 'The text cannot be empty.' };
  if (clean.length > BODY_MAX_CHARS) return { tone: 'serious', text: `Shorten the text by ${clean.length - BODY_MAX_CHARS} characters.` };
  if (clean.toUpperCase() === (sheet.seen.body || '').trim().toUpperCase()) {
    return { tone: 'info', text: 'Unchanged from the draft. Go back and approve it as drafted, or change the text.' };
  }
  return null;
}

function counterText(n) {
  const left = BODY_MAX_CHARS - n;
  return left >= 0 ? `${n} / ${BODY_MAX_CHARS} · ${left} characters left` : `${n} / ${BODY_MAX_CHARS} · ${-left} over the limit`;
}

function editView(adv) {
  const area = el('textarea', {
    id: 'edit-body', class: 'field field--mono', rows: '9', spellcheck: 'false', autocapitalize: 'characters',
    autocomplete: 'off', 'aria-describedby': 'edit-count edit-msg',
  });
  area.value = sheet.edit;
  const count = el('p', { id: 'edit-count', class: 'counter', 'aria-live': 'off' });
  const msg = el('div', { id: 'edit-msg', class: 'field-msg', 'aria-live': 'polite' });
  const update = () => {
    sheet.edit = area.value;
    const n = area.value.trim().length;
    count.textContent = counterText(n);
    count.dataset.level = n > BODY_MAX_CHARS ? 'serious' : n >= BODY_CAUTION_CHARS ? 'caution' : 'ok';
    const problem = editProblem(area.value);
    const lines = [];
    if (problem) lines.push(el('p', { class: `msg msg--${problem.tone}` }, icon(problem.tone === 'serious' ? 'st-serious' : 'st-info', 'st'), el('span', { text: problem.text })));
    if (sheet.problems.length) {
      lines.push(el('p', { class: 'msg msg--serious' }, icon('st-serious', 'st'), el('span', { text: `Check the text: ${sheet.problems.join('; ')}` })));
    }
    msg.replaceChildren(...lines);
    renderBar();
  };
  area.addEventListener('input', () => {
    sheet.problems = [];
    update();
  });
  queueMicrotask(update);
  return [
    el('label', { class: 'flabel', for: 'edit-body', text: 'Advisory text (upper case)' }),
    area,
    count,
    msg,
    el('details', { class: 'disclose' },
      el('summary', {}, icon('i-chevron-right', 'icon disclosure'), el('span', { text: 'Show the drafted text' })),
      el('pre', { class: 'acars', text: adv.body })),
    el('p', { class: 'note', text: 'Both versions are kept in the audit log. The header with sources and times is written by code and cannot be edited.' }),
  ];
}

function rejectView() {
  const area = el('textarea', {
    id: 'reject-reason', class: 'field', rows: '4', maxlength: String(REASON_MAX_CHARS), autocomplete: 'off',
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
  const chips = el('div', { class: 'reason-chips', role: 'group', 'aria-label': 'Quick reasons (inserted into the text, still editable)' }, chipButtons);
  queueMicrotask(update);
  return [
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

const entryWords = (a) => (a.inside_now ? 'INSIDE NOW' : `${a.minutes_to_entry} min`);
const statusWord = (a) => statusView(a)[1];

function conflictView() {
  const { before, current } = sheet.conflict;
  const grid = el('div', { class: 'diff', role: 'table', 'aria-label': 'What changed' },
    el('span', { class: 'diff__head' }),
    el('span', { class: 'diff__head', text: `You saw (v${before.version})` }),
    el('span', { class: 'diff__head', text: `Now (v${current.version})` }),
    ...diffRow('Status', statusWord(before), statusWord(current), { shape: statusView(current)[0] }),
    ...diffRow('Action', actionText(before), actionText(current)),
    ...diffRow('Entry', entryWords(before), entryWords(current)),
    ...diffRow('Text', before.edited_body ?? before.body, current.edited_body ?? current.body));
  for (const cell of grid.children) cell.setAttribute('role', 'cell');
  const out = [
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
  const out = [el('div', { class: 'banner banner--caution', role: 'alert' }, icon('st-caution', 'st'),
    el('p', { text: sheet.gone.title }))];
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

// --- the action bar -----------------------------------------------------------------------

function offlineAttrs(button) {
  if (app.offline) {
    button.setAttribute('aria-disabled', 'true');
    button.setAttribute('aria-describedby', 'offline-note');
  }
  return button;
}

// "Approve CHANGE LEVEL FL300–FL340 for RFA1373": the action and the flight never break inside.
const nowrap = (text) => el('span', { class: 'nowrap', text });
const approveWords = (adv, edited, question = false) => [
  edited ? 'Approve edited text' : 'Approve ',
  edited ? null : nowrap(actionText(adv)),
  ' for ',
  nowrap(adv.proxy_flight),
  question ? '?' : null,
].filter((part) => part !== null).map((part) => (typeof part === 'string' ? document.createTextNode(part) : part));

// Node.append would print a skipped (null) slot as the text "null".
const put = (node, ...kids) => append(node, kids);

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
  const offlineNote = app.offline
    ? el('p', { id: 'offline-note', class: 'actions__offline' }, icon('i-offline', 'st'), el('span', { text: OFFLINE_NOTE }))
    : null;

  if (sheet.stamp) {
    put(inner, stampNode(sheet.stamp));
  } else if (sheet.view === 'closed' || sheet.view === 'gone' || (sheet.view === 'conflict' && sheet.conflict.current.status !== 'DRAFT')) {
    const newer = adv.superseded_by && app.drafts.get(adv.superseded_by);
    const approved = adv.status === 'APPROVED' || adv.status === 'EDITED';
    put(inner, approved ? el('button', { type: 'button', class: 'btn btn--neutral', 'data-draftmsg': adv.id, disabled: app.offline },
      icon('i-sparkle'), el('span', { text: 'Draft crew briefing (EN / ID / JA)' })) : null,
    el('div', { class: 'secondary' },
      newer ? el('button', { type: 'button', class: 'btn btn--neutral', 'data-open': newer.id }, el('span', { text: 'Open the newer draft' })) : null,
      el('button', { type: 'button', class: 'btn btn--outline', 'data-back': '1' }, icon('i-chevron-left'), el('span', { text: 'Back to drafts' }))));
  } else if (sheet.view === 'conflict') {
    put(inner, el('button', { type: 'button', class: 'btn btn--neutral btn--primary', 'data-renew': '1' }, el('span', { text: 'Review the new version' })),
      el('button', { type: 'button', class: 'btn btn--outline', 'data-back': '1' }, el('span', { text: 'Back to drafts' })));
  } else if (sheet.view === 'reject') {
    const n = sheet.reason.trim().length;
    const reject = sheet.busy === 'reject'
      ? spinnerButton('btn btn--reject-solid btn--primary')
      : offlineAttrs(el('button', { type: 'button', class: 'btn btn--reject-solid btn--primary', 'data-decide': 'reject', 'aria-disabled': n < REASON_MIN_CHARS ? 'true' : null },
        icon('i-x'), el('span', { text: `Reject advisory for ${adv.proxy_flight}` })));
    put(inner, offlineNote, reject,
      el('button', { type: 'button', class: 'btn btn--outline', 'data-go': 'review', disabled: Boolean(sheet.busy) }, el('span', { text: 'Cancel' })));
  } else if (sheet.bar === 'confirm') {
    const edited = sheet.view === 'edit';
    const go = sheet.busy
      ? spinnerButton('btn btn--approve')
      : offlineAttrs(el('button', { type: 'button', class: 'btn btn--approve', 'data-decide': edited ? 'edit' : 'approve' }, icon('i-check'), el('span', { text: 'Approve now' })));
    put(inner, offlineNote, el('div', { class: 'confirm', role: 'group', 'aria-labelledby': 'confirm-q' },
      el('p', { id: 'confirm-q', class: 'confirm__q', tabindex: '-1' }, approveWords(adv, edited, true)),
      el('p', { class: 'confirm__note', text: `Queues this text on TEPHRA's own outbound queue under ${app.me ? app.me.name : 'your name'}. Nothing is sent to an aircraft.` }),
      el('div', { class: 'secondary' }, go,
        el('button', { type: 'button', class: 'btn btn--outline', 'data-confirm-back': '1', disabled: Boolean(sheet.busy) }, el('span', { text: 'Back' })))));
  } else {
    const edited = sheet.view === 'edit';
    const blockedByRule = adv.plume_mode === 'HYPOTHESIS' && !['MONITOR', 'HOLD'].includes(adv.action);
    const editBad = edited && editProblem(sheet.edit);
    let primary;
    if (sheet.busy) primary = spinnerButton('approve');
    else {
      primary = holdButton({
        label: () => approveWords(adv, edited),
        onHold: () => decide(edited ? 'edit' : 'approve'),
        onTap: () => openConfirm(),
        onEarlyRelease: (hint) => setHint(hint),
      });
      offlineAttrs(primary);
      // Long outcomes ("CHANGE LEVEL FL300–FL340") step down a size on phones: two lines, not three.
      if (primary.querySelector('.approve__label').textContent.length > 34) primary.classList.add('approve--long');
      if (blockedByRule || editBad) primary.setAttribute('aria-disabled', 'true');
    }
    const hint = el('p', { class: 'approve__hint', id: 'approve-hint' },
      el('span', { class: 'hint-long', text: `Hold to approve, or tap for a confirmation step. ${QUEUE_SENTENCE}` }),
      el('span', { class: 'hint-short', text: 'Hold to approve, or tap to confirm.' }));
    if (sheet.hint) hint.replaceChildren(el('span', { class: 'hint-early', text: sheet.hint }));
    if (blockedByRule) {
      hint.replaceChildren(el('span', { class: 'hint-early', text: 'HYPOTHESIS allows only MONITOR or HOLD: this draft cannot be approved. Reject it.' }));
    }
    if (!primary.hasAttribute('aria-describedby')) primary.setAttribute('aria-describedby', 'approve-hint');
    put(inner, offlineNote, primary, hint);
    if (edited) {
      put(inner, el('button', { type: 'button', class: 'btn btn--outline', 'data-go': 'review', disabled: Boolean(sheet.busy) }, el('span', { text: 'Cancel' })));
    } else {
      put(inner, el('div', { class: 'secondary' },
        el('button', { type: 'button', class: 'btn btn--outline', 'data-go': 'edit', disabled: Boolean(sheet.busy) }, icon('i-pencil'), el('span', { text: 'Edit text' })),
        el('button', { type: 'button', class: 'btn btn--outline btn--reject', 'data-go': 'reject', disabled: Boolean(sheet.busy) }, icon('i-x'), el('span', { text: 'Reject…' }))));
    }
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
// when, for --dur-stamp before the sheet closes (desk.js times it). Not interactive.
const STAMP_VIEW = {
  APPROVED: ['i-approved', 'Approved', "queued, not sent to any aircraft"],
  EDITED: ['i-approved', 'Approved with your edits', "queued, not sent to any aircraft"],
  REJECTED: ['i-rejected', 'Rejected', 'reason recorded, nothing queued'],
};

function stampNode(adv) {
  const [shape, word, tail] = STAMP_VIEW[adv.status] || STAMP_VIEW.APPROVED;
  const who = deskName(adv.decided_by) || (app.me ? app.me.name : '');
  return el('div', { class: `decided-stamp decided-stamp--${adv.status === 'REJECTED' ? 'rejected' : 'approved'}`, tabindex: '-1', id: 'decided-stamp' },
    el('p', { class: 'decided-stamp__word' }, icon(shape, 'icon decided-stamp__icon'), el('span', { text: word })),
    el('p', { class: 'decided-stamp__what' }, nowrap(actionText(adv)), document.createTextNode(' for '), nowrap(adv.proxy_flight)),
    el('p', { class: 'decided-stamp__who', text: `${who ? `${who} · ` : ''}${hhmmz(adv.decided_at || adv.updated_at)} · ${tail}` }));
}

export function showStamp(adv) {
  if (!sheet || sheet.id !== adv.id) return;
  sheet.stamp = adv;
  renderBar();
  const stamp = byId('decided-stamp');
  if (stamp) stamp.focus({ preventScroll: true });
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

// --- events (delegated from desk.js) ---------------------------------------------------------

export function onSheetClick(event) {
  if (!sheet) return false;
  const target = event.target.closest('button, a');
  if (!target || !byId('sheet').contains(target)) return false;
  if (target.dataset.draftmsg) {
    app.hub.draftMessages({ advisory_id: target.dataset.draftmsg }, target);
    return true;
  }
  if (target.dataset.askflight) {
    app.hub.askAbout(sheet.seen);
    return true;
  }
  if (target.dataset.back) {
    if (sheet.view === 'edit' || sheet.view === 'reject') goView('review');
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
        sheet.error = 'Give a reason of at least 3 characters.';
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
  sheet.bar = 'decide';
  sheet.error = '';
  sheet.problems = [];
  sheet.hint = '';
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
  if (kind === 'edit') {
    if (editProblem(sheet.edit)) return;
    body = { version: adv.version, body: sheet.edit.trim() };
  } else if (kind === 'reject') {
    if (sheet.reason.trim().length < REASON_MIN_CHARS) return;
    body = { version: adv.version, reason: sheet.reason.trim() };
  }
  const mine = sheet;
  mine.busy = kind;
  renderBar();
  const res = await app.hub.decide(kind, adv, body);
  if (sheet !== mine) return;
  mine.busy = false;
  if (res.ok) return; // desk.js closes the sheet and shows the toast
  if (res.status === 401 || res.status === 0) {
    renderBar();
    return;
  }
  const code = errorCode(res);
  if (code === 'version_conflict' && res.data && res.data.current) {
    sheet.conflict = { before: adv, current: res.data.current };
    sheet.view = 'conflict';
    render();
    focusTitle();
    announce('This advisory changed while you were reviewing it.');
    return;
  }
  if (code === 'invalid_transition') {
    const known = app.closed.get(adv.id);
    sheet.gone = { title: 'This advisory is no longer a draft.', detail: known ? closedSentence(known) : '' };
    sheet.view = 'gone';
    render();
    focusTitle();
    return;
  }
  if (res.status === 404) {
    sheet.gone = { title: 'This advisory no longer exists.', detail: '' };
    sheet.view = 'gone';
    render();
    focusTitle();
    return;
  }
  if (res.status === 422) {
    const list = problems(res);
    if (kind === 'edit') {
      sheet.problems = list.length ? list : ['the text was not accepted'];
      render();
      byId('edit-body').focus();
    } else if (kind === 'reject') {
      sheet.error = list.length ? `Check the reason: ${list.join('; ')}` : 'Give a reason of at least 3 characters.';
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
export const EARLY_HINT = EARLY_RELEASE_HINT;
