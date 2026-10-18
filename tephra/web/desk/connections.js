// Data connections (SPEC-v2 §7.8, V10): the dispatcher tools of the retired Connect page, in a
// Desk sheet. The connections and their push keys (a key is shown once), the sample feed of real
// recorded flights, and a file uploaded or pasted through the "Uploaded files" connection. The
// push API itself is unchanged (POST /api/push/positions with a key). A visitor never sees the
// menu item, and the server refuses a visitor anyway.

import { api } from './api.js';
import { announce, el, icon } from './dom.js';
import { dayMonthHhmm } from './format.js';
import { openBSheet } from './ui.js';

const PATH = {
  list: '/api/desk/connections',
  revoke: (id) => `/api/desk/connections/${encodeURIComponent(id)}/revoke`,
  sample: '/api/desk/sample-feed',
  upload: '/api/desk/upload',
  schema: '/api/connect/schema.json',
  sampleFile: '/api/connect/sample.json',
};
const S = { sheet: null, list: null, key: null, result: null, retime: true };

const errLine = (text) => el('p', { class: 'msg msg--serious', role: 'alert' }, icon('st-serious', 'st'), el('span', { text }));
const failText = (res) => (res.status === 0 ? "You're offline. Reconnect to manage connections." : res.status === 401 ? 'Your session has ended. Sign in again.' : res.status === 403 ? 'Only a dispatcher can manage connections.' : `Not done (HTTP ${res.status}).`);

export async function openConnections() {
  S.key = null;
  S.result = null;
  S.sheet = openBSheet({ title: 'Data connections', wide: true });
  S.sheet.setBody(el('p', { class: 'note', text: 'Loading connections…' }));
  await load();
}

async function load() {
  const res = await api(PATH.list);
  if (!res.ok) {
    S.sheet.setBody(errLine(failText(res)));
    return;
  }
  S.list = res.data;
  draw();
}

function draw(focusId = null) {
  const sheet = S.sheet;
  sheet.setBody(el('div', { class: 'dc' },
    el('p', { class: 'dc-lead' }, "An airline's own system pushes positions, flight plans and pilot reports with a key, in the ", el('code', { text: 'tephra.airline/1' }), ' format. ', el('a', { class: 'linkbtn linkbtn--inline', href: PATH.schema, download: '', text: 'Schema (JSON)' })),
    connectionsBlock(), newBlock(), sampleBlock(), uploadBlock()));
  sheet.setFooter(el('p', { class: 'al-foot', text: 'What is pushed here enters this TEPHRA\'s picture, as the push API does.' }));
  if (focusId) document.getElementById(focusId)?.focus();
}

// --- connections and keys ---------------------------------------------------------------------------

function connectionsBlock() {
  const mine = (S.list?.connections || []).filter((c) => !c.sample);
  const rows = mine.map((c) => {
    const revoked = Boolean(c.revoked_at);
    const facts = [
      `key …${c.key_hint}`,
      `made ${dayMonthHhmm(c.created_at)} by ${String(c.created_by || '').replace(/^desk:/, '')}`,
      c.last_push_at ? `last push ${dayMonthHhmm(c.last_push_at)}` : 'no push yet',
      `${c.pushes} pushes · ${c.accepted} taken · ${c.rejected} refused`,
    ];
    const revoke = revoked ? el('span', { class: 'chip chip--sm', text: 'Revoked' }) : el('button', { type: 'button', class: 'btn btn--outline btn--reject dc-revoke', 'aria-label': `Revoke ${c.name}…`, onclick: () => askRevoke(c) }, el('span', { text: 'Revoke…' }));
    return el('li', { class: `dc-row${revoked ? ' is-revoked' : ''}` },
      el('div', { class: 'dc-row__main' }, el('b', { text: c.name }), el('span', { class: 'dc-row__facts', text: facts.join(' · ') })),
      revoke);
  });
  return el('section', { class: 'dc-sec', 'aria-labelledby': 'dc-list-h' },
    el('h3', { id: 'dc-list-h', class: 'al-h', text: `Connections · ${mine.filter((c) => !c.revoked_at).length}` }),
    rows.length ? el('ul', { class: 'dc-rows' }, ...rows) : el('p', { class: 'fine', text: 'No connections yet.' }));
}

function askRevoke(c) {
  const go = el('button', { type: 'button', class: 'btn btn--reject-solid' }, el('span', { text: `Revoke ${c.name}` }));
  const cancel = el('button', { type: 'button', class: 'btn btn--outline', text: 'Cancel', onclick: () => draw() });
  const error = el('p', { class: 'msg msg--serious', role: 'alert', hidden: true });
  go.addEventListener('click', async () => {
    go.disabled = true;
    const res = await api(PATH.revoke(c.id), { method: 'POST', body: {} });
    go.disabled = false;
    if (!res.ok) {
      error.replaceChildren(icon('st-serious', 'st'), el('span', { text: failText(res) }));
      error.hidden = false;
      return;
    }
    announce(`${c.name} revoked.`);
    await load();
  });
  S.sheet.setBody(el('div', { class: 'confirm' }, el('p', { class: 'confirm__q', tabindex: '-1', text: `Revoke ${c.name}? Its key stops working at once.` }), error, el('div', { class: 'secondary' }, go, cancel)));
  S.sheet.body.querySelector('.confirm__q').focus();
}

function newBlock() {
  if (S.key) {
    const copy = el('button', { type: 'button', class: 'btn btn--outline' }, icon('i-clipboard'), el('span', { text: 'Copy' }));
    copy.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(S.key);
        copy.lastChild.textContent = 'Copied';
      } catch {
        copy.lastChild.textContent = 'Select the key and copy it';
      }
    });
    return el('section', { class: 'dc-sec', 'aria-labelledby': 'dc-new-h' },
      el('h3', { id: 'dc-new-h', class: 'al-h', text: 'Your new key' }),
      el('div', { class: 'dc-key' }, el('code', { id: 'dc-key', text: S.key }), copy),
      el('p', { class: 'fine', text: 'Shown once. Keep it with your push script. TEPHRA keeps only its fingerprint.' }));
  }
  const name = el('input', { id: 'dc-name', class: 'field', type: 'text', minlength: '2', maxlength: '48', autocomplete: 'off', placeholder: 'e.g. RFA operations', 'aria-describedby': 'dc-name-err' });
  const err = el('p', { id: 'dc-name-err', class: 'msg msg--invalid', hidden: true });
  const go = el('button', { type: 'submit', class: 'btn btn--neutral' }, icon('i-plus'), el('span', { text: 'New connection' }));
  const form = el('form', { class: 'dc-new', novalidate: true },
    el('div', { class: 'fgroup' }, el('label', { class: 'flabel', for: 'dc-name', text: 'Name' }), name, err), go);
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const n = name.value.trim();
    if (n.length < 2) {
      err.className = 'msg msg--invalid';
      err.replaceChildren(icon('st-caution', 'st'), el('span', { text: 'A name of 2 to 48 characters.' }));
      err.hidden = false;
      name.setAttribute('aria-invalid', 'true');
      name.focus();
      return;
    }
    go.disabled = true;
    const res = await api(PATH.list, { method: 'POST', body: { name: n } });
    go.disabled = false;
    if (!res.ok || !res.data?.key) {
      err.className = 'msg msg--serious';
      err.replaceChildren(icon('st-serious', 'st'), el('span', { text: failText(res) }));
      err.hidden = false;
      return;
    }
    S.key = res.data.key;
    const list = await api(PATH.list);
    if (list.ok) S.list = list.data;
    draw('dc-key');
    announce('New connection made. Its key is shown once.');
  });
  return el('section', { class: 'dc-sec', 'aria-labelledby': 'dc-new-h' }, el('h3', { id: 'dc-new-h', class: 'al-h', text: 'New connection' }), form);
}

// --- the sample feed --------------------------------------------------------------------------------

function sampleBlock() {
  const on = Boolean(S.list?.sample_running);
  const sw = el('button', { type: 'button', id: 'dc-sample', class: 'dc-switch', role: 'switch', 'aria-checked': String(on), 'aria-labelledby': 'dc-sample-h', 'aria-describedby': 'dc-sample-what' }, el('i'));
  sw.addEventListener('click', async () => {
    sw.disabled = true;
    const res = await api(PATH.sample, { method: 'POST', body: { on: !on } });
    sw.disabled = false;
    if (res.ok) S.list = res.data;
    draw('dc-sample');
    announce(res.ok ? `Sample feed ${!on ? 'on' : 'off'}.` : failText(res));
  });
  return el('section', { class: 'dc-sec dc-sample' },
    el('div', {}, el('h3', { id: 'dc-sample-h', class: 'al-h', text: 'Sample feed' }),
      el('p', { id: 'dc-sample-what', class: 'fine', text: "Real recorded flights, timed on TEPHRA's clock, pushed every few seconds." })),
    sw);
}

// --- a file uploaded or pasted ----------------------------------------------------------------------

function resultBlock() {
  const r = S.result;
  if (!r) return null;
  if (r.error) return errLine(r.error);
  const reasons = r.rejected.slice(0, 6).map((x) => `${x.section.replace('_', ' ')} ${x.index + 1}: ${x.reason}`);
  return el('div', { class: 'dc-result', role: 'status' },
    el('p', {}, el('b', { text: `taken ${r.accepted}` }), ` · in the ash ${r.in_ash.length} · refused ${r.rejected.length}${r.plans_taken ? ` · ${r.plans_taken} flight plans` : ''}${r.reports_taken ? ` · ${r.reports_taken} pilot reports` : ''}`),
    reasons.length ? el('ul', { class: 'dc-reasons' }, ...reasons.map((t) => el('li', { text: t }))) : null);
}

async function send(text) {
  let body;
  try {
    const parsed = JSON.parse(text);
    body = Array.isArray(parsed) ? { format: 'tephra.positions/1', positions: parsed } : parsed;
  } catch (e) {
    S.result = { error: `This is not JSON: ${e.message}` };
    draw('dc-upload-h');
    return;
  }
  const res = await api(PATH.upload, { method: 'POST', body: { ...body, retime: S.retime } });
  S.result = res.ok ? res.data : { error: res.status === 422 ? 'The file is not a TEPHRA push (tephra.airline/1 with positions, flight_plans or pilot_reports).' : failText(res) };
  const list = await api(PATH.list);
  if (list.ok) S.list = list.data;
  draw('dc-upload-h');
}

function uploadBlock() {
  const file = el('input', { type: 'file', id: 'dc-file', accept: '.json,application/json', class: 'sr-only' });
  file.addEventListener('change', async () => {
    const one = file.files?.[0];
    file.value = '';
    if (one) send(await one.text());
  });
  const paste = el('textarea', { id: 'dc-paste', class: 'field mono', rows: '4', spellcheck: 'false', placeholder: '{"format": "tephra.airline/1", "positions": […]}' });
  const sendPaste = el('button', { type: 'button', class: 'btn btn--outline', onclick: () => send(paste.value) }, el('span', { text: 'Send the pasted JSON' }));
  const stamp = el('input', { type: 'checkbox', id: 'dc-retime', checked: S.retime });
  stamp.addEventListener('change', () => {
    S.retime = stamp.checked;
  });
  return el('section', { class: 'dc-sec', 'aria-labelledby': 'dc-upload-h' },
    el('h3', { id: 'dc-upload-h', class: 'al-h', tabindex: '-1', text: 'Upload a file' }),
    el('p', { class: 'fine', text: 'Taken through the "Uploaded files" connection, exactly as a push.' }),
    el('div', { class: 'dc-tools' },
      el('label', { class: 'btn btn--outline', for: 'dc-file' }, icon('i-file'), el('span', { text: 'Choose a file' })), file,
      el('a', { class: 'linkbtn linkbtn--inline', href: PATH.sampleFile, download: '', text: 'Sample file' })),
    el('label', { class: 'menu__check dc-check' }, stamp, el('span', { text: "Stamp every record with TEPHRA's clock now" })),
    el('div', { class: 'fgroup' }, el('label', { class: 'flabel', for: 'dc-paste', text: 'Or paste JSON' }), paste),
    sendPaste,
    resultBlock());
}
