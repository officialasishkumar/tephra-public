// Paperwork (UI-REDESIGN R10.7, was Docs): regulator paperwork (SRA per region, VAR per flight)
// and the shift handover. What waits for a signature comes first ("Ready for you"); the three
// starters follow, one line each, and open in place. Drafts only: a person completes the blanks
// and signs. Nothing leaves TEPHRA.

import { PATHS, api, errorCode, isUnavailable, problems, unavailableReason } from './api.js';
import { announce, byId, el, icon } from './dom.js';
import { actionShort, activeNow, dayMonthHhmm } from './format.js';
import { renderDoc, renderHandover, roleName } from './docview.js';
import { openBudget } from './budget.js';
import { app } from './state.js';
import { toast } from './toast.js';
import { openBSheet, unavailableCard, shadowStamp, isViewer } from './ui.js';
import { page } from '../base.js';

const WINDOWS = [4, 8, 12];

let handover = null;
let hoBusy = false;
let hoError = null; // { reason } | { text }
let hoHours = 8;
let ackBusy = false;
let drafting = ''; // key of the draft in progress
let draftError = null;
let sraRegion = '';
const opened = new Set(); // starters kept open across re-renders

// Drafts to sign: this mode's, and one SRA per region (the newest). Before 13 Oct 2026 every
// replay run and restart drafted the same region's SRA again, so older unsigned copies can wait
// in the store; they and the other mode's drafts are listed apart, one tap in, never dropped.
const ofMode = (d) => !app.state || Boolean(d.replay) === (app.state.mode === 'REPLAY');
function splitDrafts() {
  const sign = [];
  const apart = [];
  const regions = new Set();
  for (const d of app.docs.filter((x) => x.status === 'DRAFT')) {
    if (!ofMode(d)) apart.push([d, d.replay ? 'from a replay, set aside while live feeds play' : 'from live feeds, set aside while a replay plays']);
    else if (d.kind === 'SRA' && regions.has(d.region)) apart.push([d, 'an older draft of the same region']);
    else {
      if (d.kind === 'SRA') regions.add(d.region);
      sign.push(d);
    }
  }
  return { sign, apart };
}
export const docsToSign = () => splitDrafts().sign;

export async function loadDocs() {
  const res = await api(PATHS.docs);
  if (res.ok && res.data && Array.isArray(res.data.docs)) {
    app.docs = res.data.docs.filter((d) => d && d.id).sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
    renderDocs();
    app.hub.badges();
  }
}

// The latest brief of this mode comes from the server (GET /api/desk/handovers, latest first), so
// it survives a reload and a change of phone; nothing is kept in the browser.
export async function loadHandover() {
  const res = await api(PATHS.handovers);
  if (res.ok && res.data && Array.isArray(res.data.handovers)) {
    handover = res.data.handovers.find((b) => b && b.id) || null;
    renderDocs();
  }
}

export function clearHandover() {
  handover = null;
}

// The `doc` event carries a DocSummary: id, kind (SRA, VAR, CREW_MESSAGE or HANDOVER), status, title,
// created_at, updated_at, replay, signed_roles, missing_roles and the region or flight it is about.
const SUMMARY_KINDS = new Set(['SRA', 'VAR', 'CREW_MESSAGE', 'HANDOVER']);
// The short kind word on a row; a crew report message is a message, not a form.
const KIND_WORD = { CREW_MESSAGE: 'MSG' };
// Status words and tones: a withdrawn message (its crew report was withdrawn) is never sent.
const STATUS_VIEW = { SIGNED: ['ok', 'i-approved', 'Signed'], WITHDRAWN: ['neutral', 'i-x', 'Withdrawn'], DRAFT: ['neutral', 'i-clock', 'Draft'] };
const isSummary = (s) => s && typeof s === 'object' && typeof s.id === 'string' && SUMMARY_KINDS.has(s.kind)
  && typeof s.status === 'string' && typeof s.title === 'string' && typeof s.created_at === 'string'
  && Array.isArray(s.missing_roles) && Array.isArray(s.signed_roles);

export function onDocEvent(summary) {
  if (!isSummary(summary)) return;
  if (summary.kind === 'HANDOVER') {
    // A brief or its read-back: fetch the brief itself; the event is only the list line.
    loadHandover();
    return;
  }
  app.docs = [summary, ...app.docs.filter((d) => d.id !== summary.id)].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
  renderDocs();
  app.hub.badges();
}

// --- the tab ---------------------------------------------------------------------------------------

// One row per flight whose current advisory is still in force: the newest advisory per flight,
// dropped when code replaced or retired it (SUPERSEDED: the flight left the ash, or a newer draft
// is on its way). So the count matches the flights on the Wall, not every advisory ever seen
// (review 1, item 3).
const flightsForVar = () => {
  const newest = new Map();
  const t = (a) => Date.parse(a.updated_at || a.created_at || '') || 0;
  for (const a of [...app.closed.values(), ...app.drafts.values()]) {
    if (!/^[0-9a-f]{6}:[0-9]{1,10}$/.test(a.flight_id || '')) continue;
    const prev = newest.get(a.flight_id);
    if (!prev || a.status === 'DRAFT' || (prev.status !== 'DRAFT' && t(a) >= t(prev))) newest.set(a.flight_id, a);
  }
  const live = [...newest.values()].filter((a) => a.status !== 'SUPERSEDED');
  // Only flights still in or heading into the area (the Wall's count). Until the aircraft layer is
  // read the list is empty and says it is reading, never "none needed".
  return app.exposedIds ? live.filter((a) => app.exposedIds.has(a.flight_id)) : [];
};

function draftBtn(key, label, onclick) {
  const on = drafting === key;
  return el('button', { type: 'button', class: 'btn', disabled: Boolean(drafting) || app.offline, 'aria-busy': on ? 'true' : null, onclick },
    on ? el('span', { class: 'spinner', 'aria-hidden': 'true' }) : icon('i-file'), el('span', { text: on ? 'Drafting…' : label }));
}

function docRow(d, why = null) {
  const open = d.missing_roles.length;
  const [tone, shape, word] = STATUS_VIEW[d.status] || STATUS_VIEW.DRAFT;
  const signing = d.status === 'WITHDRAWN' ? 'crew report withdrawn, not to be sent' : d.status === 'SIGNED' ? 'all lines signed' : `${d.signed_roles.length} of ${d.signed_roles.length + open} signed`;
  return el('li', {}, el('button', { type: 'button', class: 'drow', 'data-doc': d.id },
    el('span', { class: 'drow__kind', text: KIND_WORD[d.kind] || d.kind }),
    el('span', { class: 'drow__what' }, el('span', { class: 'drow__t', text: d.title }),
      el('span', { class: 'drow__m', text: `${why || signing} · drafted ${dayMonthHhmm(d.created_at)}` })),
    el('span', { class: `adv-status adv-status--${tone}` }, icon(shape, 'st'), el('span', { text: word })),
    icon('i-chevron-right', 'icon nrow__go')));
}

function handoverBody() {
  const out = [el('p', { class: 'fine', text: 'WEST and I-PASS. Code gathers the facts, TEPHRA Assistant drafts the situation and the if/then lines, and the receiver reads it back.' })];
  const incoming = el('input', { id: 'ho-in', class: 'field', type: 'text', maxlength: '64', minlength: '2', autocomplete: 'off', placeholder: 'Name of the incoming dispatcher', 'aria-describedby': 'ho-msg' });
  incoming.value = sessionStorageGet('ho-incoming');
  incoming.addEventListener('input', () => sessionStorageSet('ho-incoming', incoming.value));
  const msg = el('div', { id: 'ho-msg', class: 'field-msg', 'aria-live': 'polite' });
  const seg = el('div', { class: 'seg', role: 'group', 'aria-label': 'Shift length' }, WINDOWS.map((h) =>
    el('button', { type: 'button', class: 'seg__btn', 'aria-pressed': String(h === hoHours), onclick: () => {
      hoHours = h;
      for (const b of seg.children) b.setAttribute('aria-pressed', String(b.dataset.h === String(h)));
    }, 'data-h': String(h), text: `Last ${h} h` })));
  const gen = el('button', { type: 'button', class: 'btn btn--cta', disabled: hoBusy || app.offline, 'aria-busy': hoBusy ? 'true' : null },
    hoBusy ? el('span', { class: 'spinner', 'aria-hidden': 'true' }) : icon('i-sparkle'), el('span', { text: hoBusy ? 'Writing the handover…' : handover ? 'Write a new handover' : 'Write the handover' }));
  gen.addEventListener('click', () => generateHandover(incoming, msg));
  out.push(el('div', { class: 'hoform' },
    el('label', { class: 'flabel', for: 'ho-in', text: 'Incoming dispatcher' }), incoming, el('p', { class: 'fine', text: `Outgoing: ${app.me ? app.me.name : 'you'} (signed in)` }),
    el('p', { class: 'flabel', text: 'Shift covered' }), seg, msg, gen));
  if (hoError) out.push(hoError.reason ? unavailableCard(hoError.reason, { instead: 'No brief was written. Hand over by voice or in writing.' }) : el('div', { class: 'panel panel--serious', role: 'alert' }, el('p', { class: 'panel__title' }, icon('st-serious', 'st'), el('span', { text: hoError.text }))));
  if (handover) {
    out.push(shadowStamp(handover), renderHandover(handover, { onAck: isViewer() ? null : ackHandover, ackBusy }),
      el('p', { class: 'dlinks' }, el('a', { class: 'btn', href: page(`/docs/${encodeURIComponent(handover.id)}`), target: '_blank', rel: 'noopener' }, icon('i-printer'), el('span', { text: 'Printable page' }))));
  }
  return out;
}

// One starter: a single line that opens in place (R10.7).
function starter(key, title, sub, kids, { open = false } = {}) {
  const d = el('details', { class: 'nsec ndisc', id: `start-${key}`, open: opened.has(key) || open },
    el('summary', { class: 'ndisc__sum' }, el('span', {}, el('span', { class: 'ndisc__t', text: title }), sub ? el('span', { class: 'ndisc__s', text: sub }) : null), icon('i-chevron-right', 'icon disclosure')),
    el('div', { class: 'ndisc__body' }, kids));
  d.addEventListener('toggle', () => {
    if (d.open) opened.add(key);
    else opened.delete(key);
  });
  return d;
}

const handoverWaiting = () => handover && !(handover.receiver_ack && handover.receiver_ack.read_back_by);

const sessionStorageGet = (k) => {
  try {
    return window.sessionStorage.getItem(k) || '';
  } catch {
    return '';
  }
};
const sessionStorageSet = (k, v) => {
  try {
    window.sessionStorage.setItem(k, v);
  } catch {
    // Not remembered; the field still works.
  }
};

export function renderDocs() {
  const panel = byId('panel-docs');
  if (!panel) return;
  // The handover form keeps focus while it is typed in: redraw only when the panel is not being edited.
  const active = document.activeElement;
  if (active && panel.contains(active) && /^(INPUT|TEXTAREA|SELECT)$/.test(active.tagName) && !hoBusy) return;
  const head = el('div', { class: 'phead' },
    el('h1', { id: 'docs-title', class: 'phead__title', tabindex: '-1', text: 'Paperwork' }),
    el('p', { class: 'phead__tags' }, el('span', { class: 'chip chip--fict' }, icon('i-info', 'st'), el('span', { text: app.state?.airline?.fictional === false ? 'DRAFT · not an approved document' : 'DRAFT · not an approved document · fictional airline' }))));
  const parts = [head];

  // Primary: what waits for a person (drafts to sign, a handover to read back).
  const { sign: toSign, apart } = splitDrafts();
  const signed = app.docs.filter((d) => d.status !== 'DRAFT');
  const n = toSign.length + (handoverWaiting() ? 1 : 0);
  const ready = el('section', { class: 'ready', 'aria-labelledby': 'doc-list' },
    el('h2', { id: 'doc-list', class: 'ready__title', text: `Ready for you (${n})` }));
  const rows = toSign.map(docRow);
  if (handoverWaiting()) {
    rows.unshift(el('li', {}, el('button', { type: 'button', class: 'drow', 'data-open-start': 'ho' },
      el('span', { class: 'drow__kind', text: 'SHIFT' }),
      el('span', { class: 'drow__what' }, el('span', { class: 'drow__t', text: `Shift handover to ${handover.incoming || 'the next dispatcher'}` }),
        el('span', { class: 'drow__m', text: 'waiting for the read-back' })),
      el('span', { class: 'adv-status adv-status--neutral' }, icon('i-clock', 'st'), el('span', { text: 'Open' })),
      icon('i-chevron-right', 'icon nrow__go'))));
  }
  ready.append(rows.length ? el('ul', { class: 'drows' }, rows)
    : el('p', { class: 'ready__none', text: 'Nothing waits for your signature. Start a document below.' }));
  if (apart.length) {
    const box = el('details', { class: 'ready__signed', open: opened.has('apart') },
      el('summary', {}, icon('i-chevron-right', 'icon disclosure'), el('span', { text: `Other drafts (${apart.length})` })),
      el('ul', { class: 'drows' }, apart.map(([d, why]) => docRow(d, why))));
    box.addEventListener('toggle', () => (box.open ? opened.add('apart') : opened.delete('apart')));
    ready.append(box);
  }
  if (signed.length) {
    const box = el('details', { class: 'ready__signed', open: opened.has('signed') },
      el('summary', {}, icon('i-chevron-right', 'icon disclosure'), el('span', { text: `${signed.some((d) => d.status === 'WITHDRAWN') ? 'Signed or withdrawn' : 'Signed'} (${signed.length})` })),
      el('ul', { class: 'drows' }, signed.map(docRow)));
    box.addEventListener('toggle', () => (box.open ? opened.add('signed') : opened.delete('signed')));
    ready.append(box);
  }
  parts.push(ready);

  // Then three starters, one line each.
  // a viewer starts nothing: the handover and the paperwork drafts are dispatchers' (SPEC-FINAL 6.1)
  if (isViewer()) {
    panel.replaceChildren(...parts);
    return;
  }
  parts.push(el('h2', { class: 'more__title', text: 'Start a document' }));
  parts.push(starter('ho', 'Hand over the shift', handover ? (handoverWaiting() ? 'brief written, waiting for the read-back' : 'last brief read back') : 'WEST and I-PASS brief for the incoming dispatcher', handoverBody(), { open: hoBusy || Boolean(hoError) }));

  // SRA: one region select, active regions first (G20).
  const regions = (app.state && app.state.regions) || [];
  const activeKeys = app.activeRegions || new Set();
  const ordered = [...regions].sort((a, b) => Number(activeKeys.has(b.key)) - Number(activeKeys.has(a.key)));
  if (!sraRegion || !regions.some((r) => r.key === sraRegion)) sraRegion = ordered[0] ? ordered[0].key : '';
  const select = el('select', { id: 'sra-region', class: 'field field--select', 'aria-describedby': 'sra-note' },
    ordered.map((r) => el('option', { value: r.key, selected: r.key === sraRegion ? true : null, text: `${r.name}${activeKeys.has(r.key) ? ' (active volcano)' : ''}` })));
  select.addEventListener('change', () => {
    sraRegion = select.value;
  });
  const sraKids = [el('p', { id: 'sra-note', class: 'fine', text: "One draft per region, filled from TEPHRA's evidence. Blanks stay blank." })];
  // an SRA the budget holds for later, at the place it would land (docs/UI-AI-QUIET.md K98)
  const queued = app.budget && Array.isArray(app.budget.waiting) ? app.budget.waiting.find((w) => w.status === 'WAITING' && w.item && w.item.kind === 'SRA') : null;
  // that it waits, not when: the slot is said in the assistant sheet (docs/UI-AI-QUIET.md 8.6)
  const queuedWords = queued ? 'Waiting in line for TEPHRA Assistant' : '';
  // the summary line says it waits; the note says only what to do (review clutter 11)
  // why it waits is one tap away, in the assistant sheet (8.6)
  if (queued) {
    sraKids.push(el('p', { class: 'note', role: 'status' }, icon('st-caution', 'st'), el('span', { text: 'Complete it by hand if it cannot wait.' })),
      el('button', { type: 'button', class: 'linkbtn', 'aria-label': 'Why: open the TEPHRA Assistant sheet', onclick: openBudget }, el('span', { text: 'Why ›' })));
  }
  if (draftError && draftError.kind === 'SRA') sraKids.push(draftErrorNode());
  sraKids.push(regions.length
    ? el('div', { class: 'sraform' }, el('label', { class: 'flabel', for: 'sra-region', text: 'Region' }), select,
      draftBtn(`sra:${sraRegion}`, 'Draft SRA', () => {
        const r = regions.find((x) => x.key === select.value);
        if (r) draftSra(r);
      }))
    : el('p', { class: 'note', text: 'No regions are configured on this server.' }));
  parts.push(starter('sra', 'Safety risk assessment (SRA)', [activeKeys.size ? `${activeKeys.size} region${activeKeys.size === 1 ? '' : 's'} with an active volcano` : 'one draft per region', queuedWords].filter(Boolean).join(' · '), sraKids, { open: (draftError && draftError.kind === 'SRA') || drafting.startsWith('sra:') }));

  // VAR: one row per exposed flight.
  const flights = flightsForVar();
  const varKids = [el('p', { class: 'fine', text: 'Per exposed flight. Items 1 to 5 come from ADS-B and the hazard. The pilot completes the rest. No model writes any of it.' })];
  if (draftError && draftError.kind === 'VAR') varKids.push(draftErrorNode());
  varKids.push(flights.length ? el('ul', { class: 'dflights' }, flights.map((a) => el('li', { class: 'dflight' },
    el('span', { class: 'dflight__name' }, el('span', { class: 'mono', text: a.proxy_flight }), el('span', { class: 'dflight__sub', text: `${a.volcano_name} · ${actionShort(a)}` })),
    draftBtn(`var:${a.flight_id}`, 'Draft VAR', () => draftVar(a)))))
    : el('p', { class: 'note', text: app.exposedIds ? 'None needed: no RFA flight is in or heading into an ash area.' : 'Reading the flights in or heading into the ash…' }));
  parts.push(starter('var', app.exposedIds ? `Pilot ash reports (VAR): ${flights.length} flight${flights.length === 1 ? '' : 's'}` : 'Pilot ash reports (VAR)', flights.length ? 'one per flight in or heading into the ash' : app.exposedIds ? 'none needed right now' : 'reading the flights…', varKids, { open: (draftError && draftError.kind === 'VAR') || drafting.startsWith('var:') }));

  panel.replaceChildren(...parts);
}

const draftErrorNode = () => draftError.reason
  ? unavailableCard(draftError.reason, { instead: 'No document was written. Complete it by hand.' })
  : el('div', { class: 'panel panel--serious', role: 'alert' }, el('p', { class: 'panel__title' }, icon('st-serious', 'st'), el('span', { text: draftError.text })));

// --- drafting --------------------------------------------------------------------------------------

async function draft(key, kind, path, body) {
  if (drafting) return;
  drafting = key;
  draftError = null;
  renderDocs();
  const res = await api(path, { method: 'POST', body });
  drafting = '';
  if (res.ok && res.data && res.data.id) {
    await loadDocs();
    openDoc(res.data);
    return;
  }
  if (isUnavailable(res)) draftError = { kind, reason: unavailableReason(res) };
  else if (res.status === 409) draftError = { kind, text: errorCode(res) === 'no_active_volcano' ? 'No volcano of this region is in the current picture, so there is nothing to assess.' : (res.data && res.data.detail) || 'Not drafted.' };
  else if (res.status === 404) draftError = { kind, text: 'That flight is no longer in the exposure set.' };
  else draftError = { kind, text: res.status === 0 ? "Can't reach the server." : `Not drafted: ${(res.data && res.data.detail) || `HTTP ${res.status}`}` };
  renderDocs();
}

const draftSra = (region) => draft(`sra:${region.key}`, 'SRA', PATHS.docSra, { region: region.key });
const draftVar = (adv) => draft(`var:${adv.flight_id}`, 'VAR', PATHS.docVar, { flight_id: adv.flight_id });

// --- one document ----------------------------------------------------------------------------------

export async function openDocById(id) {
  const res = await api(PATHS.doc(id));
  if (res.ok && res.data && res.data.id) openDoc(res.data);
  else toast({ tone: 'caution', title: res.status === 404 ? 'That document no longer exists.' : "Can't open the document." });
}

const docTitle = (doc) => (doc.kind === 'SRA' ? `SRA draft: ${doc.region_name}` : doc.kind === 'CREW_MESSAGE' ? `Message draft: ${doc.flight}` : `VAR draft: ${doc.proxy_flight}`);

export function openDoc(doc) {
  let current = doc;
  const sheet = openBSheet({ title: docTitle(current), wide: true });
  const draw = () => {
    const view = renderDoc(current, { onSign: isViewer() ? null : signLine });
    sheet.setBody(current.shadow ? el('div', { class: 'stack' }, shadowStamp(current), view) : view);
    sheet.setFooter(el('div', { class: 'fstack' },
      el('a', { class: 'btn btn--block', href: page(`/docs/${encodeURIComponent(current.id)}`), target: '_blank', rel: 'noopener' }, icon('i-printer'), el('span', { text: 'Open printable page' }))));
  };
  const signLine = (line, li, trigger) => {
    const input = el('input', { class: 'field', type: 'text', maxlength: '200', autocomplete: 'name', 'aria-label': `Name to sign as ${roleName(line.role)}` });
    input.value = app.me ? app.me.name : '';
    const msg = el('div', { class: 'field-msg', 'aria-live': 'polite' });
    const go = el('button', { type: 'button', class: 'btn btn--approve' }, icon('i-check'), el('span', { text: `Sign as ${roleName(line.role)}` }));
    const form = el('div', { class: 'signform' }, input, go, msg);
    trigger.replaceWith(form);
    input.focus();
    go.addEventListener('click', async () => {
      const name = input.value.trim();
      if (name.length < 2) {
        msg.replaceChildren(el('p', { class: 'msg msg--invalid' }, icon('st-caution', 'st'), el('span', { text: 'Type the name to print, at least 2 characters.' })));
        input.focus();
        return;
      }
      go.disabled = true;
      const res = await api(PATHS.docSign(current.id), { method: 'POST', body: { name, role: line.role } });
      go.disabled = false;
      if (res.ok && res.data && res.data.id) {
        current = res.data;
        draw();
        loadDocs();
        announce(`Signed as ${roleName(line.role)}.`);
        return;
      }
      const list = problems(res);
      // 422 (the name or role needs fixing) and 409 (already signed) are not alarms: red is for the server.
      const tone = res.status === 422 ? ['msg--invalid', 'st-caution'] : res.status === 409 ? ['msg--caution', 'st-caution'] : ['msg--serious', 'st-serious'];
      msg.replaceChildren(el('p', { class: `msg ${tone[0]}` }, icon(tone[1], 'st'), el('span', { text: res.status === 409 ? ((res.data && res.data.detail) || 'Already signed.') : `Not signed: ${list.length ? list.join(' · ') : (res.data && res.data.detail) || `HTTP ${res.status}`}` })));
    });
  };
  draw();
}

// --- handover --------------------------------------------------------------------------------------

async function generateHandover(incomingInput, msg) {
  if (hoBusy) return;
  const incoming = incomingInput.value.trim();
  if (incoming.length < 2) {
    msg.replaceChildren(el('p', { class: 'msg msg--invalid' }, icon('st-caution', 'st'), el('span', { text: 'Name the incoming dispatcher (at least 2 characters).' })));
    incomingInput.focus();
    return;
  }
  hoBusy = true;
  hoError = null;
  renderDocs();
  const now = activeNow() ?? Date.now();
  const since = new Date(now - hoHours * 3600000).toISOString();
  const res = await api(PATHS.handover, { method: 'POST', body: { since, incoming } });
  hoBusy = false;
  if (res.ok && res.data && res.data.id) {
    handover = res.data;
    hoError = null;
    announce('Handover brief ready.');
  } else if (isUnavailable(res)) hoError = { reason: unavailableReason(res) };
  else if (res.status === 422) hoError = { text: `Check the form: ${problems(res).join(' · ') || 'a field was not accepted'}` };
  else hoError = { text: res.status === 0 ? "Can't reach the server." : `No brief: ${(res.data && res.data.detail) || `HTTP ${res.status}`}` };
  renderDocs();
}

async function ackHandover() {
  if (!handover || ackBusy) return;
  ackBusy = true;
  renderDocs();
  const res = await api(PATHS.handoverAck(handover.id), { method: 'POST' });
  ackBusy = false;
  if (res.ok && res.data && res.data.id) {
    handover = res.data;
    hoError = null;
    toast({ tone: 'ok', title: `Read back by ${app.me ? app.me.name : 'you'}. Open drafts are recorded as handed over open.` });
  } else {
    hoError = { text: `Read-back refused: ${(res.data && res.data.detail) || `HTTP ${res.status}`}` };
  }
  renderDocs();
}

export function onDocsClick(event) {
  const start = event.target.closest('[data-open-start]');
  if (start && byId('panel-docs').contains(start)) {
    opened.add(start.dataset.openStart);
    renderDocs();
    const box = byId(`start-${start.dataset.openStart}`);
    if (box) {
      box.scrollIntoView({ block: 'start' });
      const field = box.querySelector('input, button');
      if (field) field.focus({ preventScroll: true });
    }
    return true;
  }
  const t = event.target.closest('[data-doc]');
  if (!t || !byId('panel-docs').contains(t)) return false;
  openDocById(t.dataset.doc);
  return true;
}
