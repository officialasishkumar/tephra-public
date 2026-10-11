// The Docs tab: regulator paperwork (SRA per region, VAR per flight) and the shift handover.
// Drafts only: a person completes the blanks and signs. Nothing leaves TEPHRA.

import { PATHS, api, errorCode, isUnavailable, problems, unavailableReason } from './api.js';
import { announce, byId, el, icon } from './dom.js';
import { activeNow, dayMonthHhmm, hhmmz } from './format.js';
import { renderDoc, renderHandover, roleName } from './docview.js';
import { app } from './state.js';
import { toast } from './toast.js';
import { emptyPanel, openBSheet, sectionHead, unavailableCard } from './ui.js';

const HO_KEY = 'tephra.desk.handover';
const WINDOWS = [4, 8, 12];

let handover = null;
let hoBusy = false;
let hoError = null; // { reason } | { text }
let hoHours = 8;
let ackBusy = false;
let drafting = ''; // key of the draft in progress
let draftError = null;

const store = {
  get() {
    try {
      return window.localStorage.getItem(HO_KEY);
    } catch {
      return null;
    }
  },
  set(v) {
    try {
      window.localStorage.setItem(HO_KEY, v);
    } catch {
      // The brief is still on screen; it just is not remembered.
    }
  },
};

export const docsToSign = () => app.docs.filter((d) => d.status === 'DRAFT');

export async function loadDocs() {
  const res = await api(PATHS.docs);
  if (res.ok && res.data && Array.isArray(res.data.docs)) {
    app.docs = res.data.docs.filter((d) => d && d.id).sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
    renderDocs();
    app.hub.badges();
  }
}

export async function loadHandover() {
  const id = store.get();
  if (!id || handover) return;
  const res = await api(PATHS.handoverGet(id));
  if (res.ok && res.data && res.data.id) {
    handover = res.data;
    renderDocs();
  }
}

export function onDocEvent(summary) {
  if (!summary || typeof summary !== 'object' || typeof summary.id !== 'string') return;
  if (summary.doc_type === 'handover') return;
  if (!Array.isArray(summary.missing_roles)) {
    // The event may carry the whole document: reduce it to the list line.
    if (!Array.isArray(summary.signatures)) return;
    summary = {
      id: summary.id,
      kind: summary.kind,
      status: summary.status,
      title: summary.kind === 'SRA' ? `SRA draft: ${summary.region_name}` : `VAR draft: ${summary.proxy_flight} / ${summary.volcano_name}`,
      created_at: summary.created_at,
      updated_at: summary.updated_at,
      replay: summary.replay,
      signed_roles: summary.signatures.filter((l) => l.signed_at).map((l) => l.role),
      missing_roles: summary.signatures.filter((l) => !l.signed_at).map((l) => l.role),
    };
  }
  app.docs = [summary, ...app.docs.filter((d) => d.id !== summary.id)].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
  renderDocs();
  app.hub.badges();
}

// --- the tab ---------------------------------------------------------------------------------------

const flightsForVar = () => {
  const seen = new Map();
  for (const a of [...app.drafts.values(), ...app.closed.values()]) if (/^[0-9a-f]{6}:[0-9]{1,10}$/.test(a.flight_id || '')) seen.set(a.flight_id, a);
  return [...seen.values()].slice(0, 12);
};

function draftBtn(key, label, onclick) {
  const on = drafting === key;
  return el('button', { type: 'button', class: 'btn', disabled: Boolean(drafting) || app.offline, 'aria-busy': on ? 'true' : null, onclick },
    on ? el('span', { class: 'spinner', 'aria-hidden': 'true' }) : icon('i-file'), el('span', { text: on ? 'Drafting…' : label }));
}

function docRow(d) {
  const open = d.missing_roles.length;
  return el('li', {}, el('button', { type: 'button', class: 'drow', 'data-doc': d.id },
    el('span', { class: 'drow__kind', text: d.kind }),
    el('span', { class: 'drow__what' }, el('span', { class: 'drow__t', text: d.title }),
      el('span', { class: 'drow__m', text: `${dayMonthHhmm(d.created_at)} · ${d.status === 'SIGNED' ? 'all lines signed' : `${d.signed_roles.length} of ${d.signed_roles.length + open} signed`}${d.replay ? ' · REPLAY' : ''}` })),
    el('span', { class: `adv-status adv-status--${d.status === 'SIGNED' ? 'ok' : 'neutral'}` }, icon(d.status === 'SIGNED' ? 'i-approved' : 'i-clock', 'st'), el('span', { text: d.status === 'SIGNED' ? 'Signed' : 'Draft' })),
    icon('i-chevron-right', 'icon nrow__go')));
}

function handoverSection() {
  const sec = el('section', { class: 'nsec', 'aria-labelledby': 'doc-ho' }, sectionHead('Shift handover', { id: 'doc-ho', sub: 'WEST and I-PASS. Code gathers the facts; an AI writes the situation and the if/then lines; the receiver reads it back.' }));
  const incoming = el('input', { id: 'ho-in', class: 'field', type: 'text', maxlength: '64', minlength: '2', autocomplete: 'off', placeholder: 'Name of the incoming dispatcher', 'aria-describedby': 'ho-msg' });
  incoming.value = sessionStorageGet('ho-incoming');
  incoming.addEventListener('input', () => sessionStorageSet('ho-incoming', incoming.value));
  const msg = el('div', { id: 'ho-msg', class: 'field-msg', 'aria-live': 'polite' });
  const seg = el('div', { class: 'seg', role: 'group', 'aria-label': 'Shift length' }, WINDOWS.map((h) =>
    el('button', { type: 'button', class: 'seg__btn', 'aria-pressed': String(h === hoHours), onclick: () => {
      hoHours = h;
      for (const b of seg.children) b.setAttribute('aria-pressed', String(b.dataset.h === String(h)));
    }, 'data-h': String(h), text: `Last ${h} h` })));
  const gen = el('button', { type: 'button', class: 'btn btn--neutral', disabled: hoBusy || app.offline, 'aria-busy': hoBusy ? 'true' : null },
    hoBusy ? el('span', { class: 'spinner', 'aria-hidden': 'true' }) : icon('i-sparkle'), el('span', { text: hoBusy ? 'Writing the brief…' : handover ? 'Generate a new handover' : 'Generate handover' }));
  gen.addEventListener('click', () => generateHandover(incoming, msg));
  sec.append(el('div', { class: 'hoform' },
    el('label', { class: 'flabel', for: 'ho-in', text: 'Incoming dispatcher' }), incoming, el('p', { class: 'fine', text: `Outgoing: ${app.me ? app.me.name : 'you'} (signed in)` }),
    el('p', { class: 'flabel', text: 'Shift covered' }), seg, msg, gen));
  if (hoError) sec.append(hoError.reason ? unavailableCard(hoError.reason, { instead: 'No brief was written. Hand over by voice or in writing.' }) : el('div', { class: 'panel panel--serious', role: 'alert' }, el('p', { class: 'panel__title' }, icon('st-serious', 'st'), el('span', { text: hoError.text }))));
  if (handover) {
    sec.append(renderHandover(handover, { onAck: ackHandover, ackBusy }),
      el('p', { class: 'dlinks' }, el('a', { class: 'btn', href: `/docs/${encodeURIComponent(handover.id)}`, target: '_blank', rel: 'noopener' }, icon('i-printer'), el('span', { text: 'Printable page' }))));
  }
  return sec;
}

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
  if (active && panel.contains(active) && /^(INPUT|TEXTAREA)$/.test(active.tagName) && !hoBusy) return;
  const head = el('div', { class: 'phead' },
    el('h1', { id: 'docs-title', class: 'phead__title', tabindex: '-1', text: 'Documents' }),
    el('p', { class: 'phead__sub', text: 'Regulator paperwork and the shift handover. Drafts for a person to complete and sign.' }),
    el('p', { class: 'phead__tags' }, el('span', { class: 'chip chip--fict' }, icon('i-info', 'st'), el('span', { text: 'DRAFT · not an approved document · fictional airline' }))));
  const parts = [head, handoverSection()];

  const regions = (app.state && app.state.regions) || [];
  const sra = el('section', { class: 'nsec', 'aria-labelledby': 'doc-sra' }, sectionHead('Safety risk assessment (SRA)', { id: 'doc-sra', sub: 'One draft per region, filled from TEPHRA\'s evidence. Blanks stay blank.' }));
  if (draftError && draftError.kind === 'SRA') sra.append(draftErrorNode());
  sra.append(el('ul', { class: 'dflights' }, regions.map((r) => el('li', { class: 'dflight' },
    el('span', { class: 'dflight__name', text: r.name }),
    draftBtn(`sra:${r.key}`, 'Draft SRA', () => draftSra(r))))));
  parts.push(sra);

  const flights = flightsForVar();
  const varSec = el('section', { class: 'nsec', 'aria-labelledby': 'doc-var' }, sectionHead('Volcanic activity report (VAR)', { id: 'doc-var', sub: 'Per exposed flight. Items 1 to 5 from ADS-B and the hazard; the pilot completes the rest. No model writes any of it.' }));
  if (draftError && draftError.kind === 'VAR') varSec.append(draftErrorNode());
  varSec.append(flights.length ? el('ul', { class: 'dflights' }, flights.map((a) => el('li', { class: 'dflight' },
    el('span', { class: 'dflight__name' }, el('span', { class: 'mono', text: a.proxy_flight }), el('span', { class: 'dflight__sub', text: `${a.volcano_name} · ${a.action.replace('_', ' ')}` })),
    draftBtn(`var:${a.flight_id}`, 'Draft VAR', () => draftVar(a))))) : el('p', { class: 'note', text: 'No exposed flight to report on right now.' }));
  parts.push(varSec);

  const list = el('section', { class: 'nsec', 'aria-labelledby': 'doc-list' }, sectionHead('Drafted documents', { id: 'doc-list', count: app.docs.length }));
  list.append(app.docs.length ? el('ul', { class: 'drows' }, app.docs.map(docRow)) : emptyPanel('No documents yet', 'Draft an SRA or a VAR above.'));
  parts.push(list);
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

export function openDoc(doc) {
  let current = doc;
  const sheet = openBSheet({ title: current.kind === 'SRA' ? `SRA draft: ${current.region_name}` : `VAR draft: ${current.proxy_flight}`, wide: true });
  const draw = () => {
    sheet.setBody(renderDoc(current, { onSign: signLine }));
    sheet.setFooter(el('div', { class: 'fstack' },
      el('a', { class: 'btn btn--block', href: `/docs/${encodeURIComponent(current.id)}`, target: '_blank', rel: 'noopener' }, icon('i-printer'), el('span', { text: 'Open printable page' }))));
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
        msg.replaceChildren(el('p', { class: 'msg msg--caution' }, icon('st-caution', 'st'), el('span', { text: 'Type the name to print, at least 2 characters.' })));
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
      msg.replaceChildren(el('p', { class: 'msg msg--serious' }, icon('st-serious', 'st'), el('span', { text: res.status === 409 ? ((res.data && res.data.detail) || 'Already signed.') : `Not signed: ${list.length ? list.join('; ') : (res.data && res.data.detail) || `HTTP ${res.status}`}` })));
    });
  };
  draw();
}

// --- handover --------------------------------------------------------------------------------------

async function generateHandover(incomingInput, msg) {
  if (hoBusy) return;
  const incoming = incomingInput.value.trim();
  if (incoming.length < 2) {
    msg.replaceChildren(el('p', { class: 'msg msg--caution' }, icon('st-caution', 'st'), el('span', { text: 'Name the incoming dispatcher (at least 2 characters).' })));
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
    store.set(res.data.id);
    hoError = null;
    announce('Handover brief ready.');
  } else if (isUnavailable(res)) hoError = { reason: unavailableReason(res) };
  else if (res.status === 422) hoError = { text: `Check the form: ${problems(res).join('; ') || 'a field was not accepted'}` };
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
  const t = event.target.closest('[data-doc]');
  if (!t || !byId('panel-docs').contains(t)) return false;
  openDocById(t.dataset.doc);
  return true;
}
