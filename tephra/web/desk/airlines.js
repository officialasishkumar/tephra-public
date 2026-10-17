// Airlines to verify (SPEC-v2 §7.8): the airlines that onboarded on this site, for this site's
// dispatchers only. A list by status, then one airline's answers, the reviewer's hints and its
// private history, with Verify and Decline (and Delete record for a declined one). Verifying says
// a person checked who the operator is; it approves no policy, publishes nothing and changes no
// picture. Every answer goes in through el() (textContent).

import { api, errorCode } from './api.js';
import { announce, el, icon } from './dom.js';
import { dayMonthHhmm } from './format.js';
import { openBSheet } from './ui.js';
import { toast } from './toast.js';
import { ANSWER_PAGES, pageOf, summaryOf } from '../onboard/pages.js';
import { answerRows } from '../onboard/review.js';

const PATH = {
  list: (status) => `/api/desk/airlines?status=${status}&limit=200`,
  summary: '/api/desk/airlines/summary',
  one: (id) => `/api/desk/airlines/${encodeURIComponent(id)}`,
  act: (id, what) => `/api/desk/airlines/${encodeURIComponent(id)}/${what}`,
  policy: '/api/policy',
};
const FILTERS = [['pending', 'Pending'], ['verified', 'Verified'], ['declined', 'Declined'], ['all', 'All']];
const PILL = { pending: ['st-caution', 'chip--d-caution'], verified: ['st-ok', 'chip--d-ok'], declined: ['st-off', 'chip--d-serious'] };
const ACTIONS = { created: 'Submitted', answers_changed: 'Answers changed', assistant_changed: 'Model choice changed', verified: 'Verified', declined: 'Declined' };
const FOOT = "Airlines are private to this site's dispatchers. Nothing here reaches the demo, the Desk's decisions or the public record.";

let named = null;
const state = { filter: 'pending', pending: null, sheet: null };

// The number the account menu shows: pending airlines, or null when it cannot be read.
export async function airlinesWaiting() {
  const res = await api(PATH.summary);
  return res.ok && Number.isInteger(res.data?.pending) ? res.data.pending : null;
}

const pill = (status, label) => {
  const [shape, cls] = PILL[status] || PILL.pending;
  return el('span', { class: `chip ${cls}` }, icon(shape, 'st'), el('span', { text: label }));
};

const errLine = (text) => el('p', { class: 'msg msg--serious', role: 'alert' }, icon('st-serious', 'st'), el('span', { text }));

function failText(res) {
  if (res.status === 0) return "You're offline. Reconnect to review airlines.";
  if (res.status === 401) return 'Your session has ended. Sign in again.';
  if (res.status === 403) return 'Only a dispatcher can review airlines.';
  if (errorCode(res) === 'feature_off') return 'Onboarding is off on this server.';
  return `Not loaded (HTTP ${res.status}).`;
}

export function openAirlines() {
  state.sheet = openBSheet({ title: 'Airlines to verify', wide: true });
  showList();
}

// --- the list ---------------------------------------------------------------------------------------

async function showList({ focusFilter = false } = {}) {
  const sheet = state.sheet;
  sheet.setTitle('Airlines to verify');
  sheet.setFooter(el('p', { class: 'al-foot', text: FOOT }));
  const rows = el('div', { class: 'al-rows' }, el('p', { class: 'note', text: 'Loading airlines…' }));
  const filters = el('div', { class: 'seg al-seg', role: 'group', 'aria-label': 'Show airlines' }, ...FILTERS.map(([key, label]) =>
    el('button', { type: 'button', class: 'seg__btn', 'aria-pressed': String(key === state.filter), dataset: { filter: key }, text: key === 'pending' && state.pending != null ? `${label} (${state.pending})` : label,
      onclick: () => {
        state.filter = key;
        showList({ focusFilter: true });
      } })));
  sheet.setBody(el('div', { class: 'al' }, filters, rows));
  if (focusFilter) filters.querySelector('[aria-pressed="true"]')?.focus();
  const [res, waiting] = await Promise.all([api(PATH.list(state.filter)), airlinesWaiting()]);
  if (state.sheet !== sheet) return;
  if (waiting != null && waiting !== state.pending) {
    state.pending = waiting;
    const b = filters.querySelector('[data-filter="pending"]');
    if (b) b.textContent = `Pending (${waiting})`;
  }
  if (!res.ok) {
    rows.replaceChildren(errLine(failText(res)));
    return;
  }
  const list = Array.isArray(res.data?.airlines) ? res.data.airlines : [];
  if (!list.length) {
    rows.replaceChildren(el('p', { class: 'note', text: state.filter === 'pending' ? 'No airline waits to be verified.' : 'No airlines here.' }));
    return;
  }
  rows.replaceChildren(el('ul', { class: 'irows al-list' }, ...list.map((a) => {
    const hints = a.flags?.length || 0;
    const label = `${a.name}, ${a.icao}, ${a.state_of_operator}. Submitted ${dayMonthHhmm(a.submitted_at)}. ${a.status_label}${hints ? `, ${hints} ${hints === 1 ? 'hint' : 'hints'}` : ''}.`;
    return el('li', {}, el('button', { type: 'button', class: 'card irow al-row', 'aria-label': label, onclick: () => showOne(a.id) },
      el('span', { class: 'al-code', 'aria-hidden': 'true', text: a.icao }),
      el('span', { class: 'irow__main al-main', 'aria-hidden': 'true' },
        el('span', { class: 'al-top' }, el('span', { class: 'al-name', text: a.name }), pill(a.status, a.status_label)),
        el('span', { class: 'al-sub', text: `${a.icao} · ${a.state_of_operator} · Submitted ${dayMonthHhmm(a.submitted_at)}` }),
        hints ? el('span', { class: 'al-hints' }, icon('i-alert', 'st'), el('span', { text: `${hints} ${hints === 1 ? 'hint' : 'hints'}` })) : null),
      icon('i-chevron-right', 'icon irow__go al-go')));
  })));
}

// --- one airline ------------------------------------------------------------------------------------

async function loadNamed() {
  if (named) return named;
  const res = await api(PATH.policy);
  const p = res.ok ? res.data?.policy : null;
  if (!p) return {};
  named = {};
  for (const [block, values] of Object.entries(p)) {
    if (!values || typeof values !== 'object' || Array.isArray(values)) continue;
    for (const [k, v] of Object.entries(values)) if (v && typeof v === 'object' && 'value' in v && 'unit' in v) named[`${block}.${k}`] = { value: v.value, unit: v.unit };
  }
  return named;
}

const dl = (rows) => el('dl', { class: 'al-dl' }, ...rows.flatMap(([k, v]) => [el('dt', { text: k }), el('dd', {}, v instanceof Node ? v : String(v))]));

async function showOne(id, { notice = null } = {}) {
  const sheet = state.sheet;
  sheet.setBody(el('p', { class: 'note', text: 'Loading the airline…' }));
  const [res, values] = await Promise.all([api(PATH.one(id)), loadNamed()]);
  if (state.sheet !== sheet) return;
  if (!res.ok || !res.data) {
    sheet.setBody(el('div', { class: 'al' }, backButton(), errLine(res.status === 404 ? 'This airline is no longer on this site.' : failText(res))));
    return;
  }
  const a = res.data;
  sheet.setTitle(a.name);
  const answers = a.answers;
  const pages = ANSWER_PAGES.map((key) => el('details', { class: 'al-page' },
    el('summary', {}, el('b', { text: `${pageOf(key).n} · ${pageOf(key).name}` }), el('span', { class: 'al-sum', text: summaryOf(key, answers, values) }), icon('i-chevron-down', 'icon al-chev')),
    dl(answerRows(key, answers, { named: values }))));
  const broken = a.history_ok === false ? a.history_broken_at : null;
  const history = el('ol', { class: 'al-history' }, ...a.history.map((h) => el('li', {},
    el('span', { class: 'mono al-at', text: dayMonthHhmm(h.at) }),
    el('span', { text: `${ACTIONS[h.action] || h.action} · ${String(h.actor).replace(/^desk:/, '')}${h.note ? ` · ${h.note}` : ''}` }))));
  const body = el('div', { class: 'al' },
    backButton(),
    notice ? el('p', { class: 'msg msg--info', role: 'status' }, icon('i-info', 'st'), el('span', { text: notice })) : null,
    el('div', { class: 'al-head' }, el('span', { class: 'al-code al-code--lg', 'aria-hidden': 'true', text: a.icao }),
      el('div', {}, el('p', { class: 'al-name', text: a.name }), el('p', { class: 'al-sub', text: `Submitted ${dayMonthHhmm(a.submitted_at)}` })),
      pill(a.status, a.status_label)),
    dl([
      ['Account email', a.email],
      ['Operations email', a.ops_email],
      ['State of the Operator', a.state_of_operator],
      ['AOC number', a.aoc_number || 'Not given'],
    ]),
    a.flags?.length
      ? el('section', { class: 'al-sec', 'aria-labelledby': 'al-hints-h' },
        el('h3', { id: 'al-hints-h', class: 'al-h', text: 'Hints for the reviewer' }),
        el('ul', { class: 'al-flags' }, ...a.flags.map((f) => el('li', {}, icon('i-alert', 'st'), el('span', { text: f })))),
        el('p', { class: 'fine', text: 'Computed by code from the answers. They never block and are never shown to the airline.' }))
      : null,
    el('section', { class: 'al-sec', 'aria-labelledby': 'al-ans-h' }, el('h3', { id: 'al-ans-h', class: 'al-h', text: 'The answers' }), ...pages),
    el('section', { class: 'al-sec', 'aria-labelledby': 'al-hist-h' },
      el('h3', { id: 'al-hist-h', class: 'al-h', text: 'Private history' }),
      a.history_ok === false ? el('p', { class: 'msg msg--caution', role: 'status' }, icon('st-caution', 'st'), el('span', { text: broken ? `History does not check out at entry ${broken}.` : 'History does not check out.' })) : null,
      history),
    el('div', { class: 'al-acts' }, ...actions(a)));
  sheet.setBody(body);
  body.querySelector('.al-back')?.focus();
}

function backButton() {
  return el('button', { type: 'button', class: 'linkbtn al-back', onclick: () => showList() }, icon('i-chevron-left'), el('span', { text: 'Airlines' }));
}

function actions(a) {
  if (a.status === 'pending') {
    return [
      el('button', { type: 'button', class: 'btn btn--neutral', onclick: () => confirmVerify(a) }, icon('i-check'), el('span', { text: `Verify ${a.name}` })),
      el('button', { type: 'button', class: 'btn btn--outline', onclick: () => askDecline(a) }, el('span', { text: 'Decline…' })),
    ];
  }
  if (a.status === 'declined') {
    return [el('button', { type: 'button', class: 'btn btn--outline btn--reject', onclick: () => confirmDelete(a) }, icon('i-x'), el('span', { text: 'Delete record…' }))];
  }
  return [];
}

// --- decisions --------------------------------------------------------------------------------------

function confirmBox({ question, field = null, go, goWords, tone = 'btn--neutral' }) {
  const error = el('p', { class: 'msg msg--serious', role: 'alert', hidden: true });
  const button = el('button', { type: 'button', class: `btn ${tone}` }, el('span', { text: goWords }));
  const cancel = el('button', { type: 'button', class: 'btn btn--outline', text: 'Cancel' });
  const box = el('div', { class: 'confirm al-confirm' },
    el('p', { class: 'confirm__q', tabindex: '-1', text: question }), field, error, el('div', { class: 'secondary' }, button, cancel));
  button.addEventListener('click', async () => {
    button.disabled = true;
    const text = await go();
    button.disabled = false;
    if (text) {
      error.replaceChildren(icon('st-serious', 'st'), el('span', { text }));
      error.hidden = false;
    }
  });
  return { box, cancel };
}

function showConfirm(a, parts) {
  const { box, cancel } = confirmBox(parts);
  cancel.addEventListener('click', () => showOne(a.id));
  state.sheet.setBody(el('div', { class: 'al' }, backButton(), box));
  box.querySelector('.confirm__q').focus();
}

async function decide(a, what, body, done) {
  const res = await api(PATH.act(a.id, what), { method: 'POST', body: { version: a.version, ...body } });
  if (res.ok || res.status === 204) {
    done();
    return null;
  }
  if (res.status === 409) {
    showOne(a.id, { notice: 'Someone changed this airline. Reloaded.' });
    return null;
  }
  if (errorCode(res) === 'not_pending') {
    showOne(a.id, { notice: 'This airline was already decided. Reloaded.' });
    return null;
  }
  return failText(res);
}

function confirmVerify(a) {
  const note = el('textarea', { id: 'al-note', class: 'field', rows: '2', maxlength: '300', 'aria-describedby': 'al-note-hint' });
  showConfirm(a, {
    question: `Verify ${a.name}? Verifying records that a person checked who this operator is (for example its designator, its AOC and the email domain). It does not approve its policy or its use of TEPHRA, publishes nothing and changes no picture.`,
    field: el('div', { class: 'fgroup' }, el('label', { class: 'flabel', for: 'al-note', text: 'Note (optional)' }), note, el('p', { id: 'al-note-hint', class: 'fine', text: 'Up to 300 characters, kept in this airline\'s private history.' })),
    goWords: `Verify ${a.name}`,
    go: () => decide(a, 'verify', { note: note.value.trim() || null }, () => {
      toast({ tone: 'ok', title: `${a.name} verified.` });
      announce(`${a.name} verified.`);
      showOne(a.id);
    }),
  });
}

function askDecline(a) {
  const reason = el('textarea', { id: 'al-reason', class: 'field', rows: '3', maxlength: '500', 'aria-describedby': 'al-reason-hint' });
  showConfirm(a, {
    question: `Decline ${a.name}? The airline sees your reason in its workspace.`,
    field: el('div', { class: 'fgroup' }, el('label', { class: 'flabel', for: 'al-reason', text: 'Reason' }), reason, el('p', { id: 'al-reason-hint', class: 'fine', text: '3 to 500 characters.' })),
    goWords: 'Decline',
    tone: 'btn--reject-solid',
    go: () => {
      const text = reason.value.trim();
      if (text.length < 3) return Promise.resolve('Give a reason of 3 to 500 characters.');
      return decide(a, 'decline', { reason: text }, () => {
        toast({ tone: 'rejected', title: `${a.name} declined.` });
        announce(`${a.name} declined.`);
        showOne(a.id);
      });
    },
  });
}

function confirmDelete(a) {
  showConfirm(a, {
    question: `Delete ${a.name}'s record and account? It cannot be undone.`,
    goWords: 'Delete record',
    tone: 'btn--reject-solid',
    go: () => decide(a, 'delete', {}, () => {
      toast({ tone: 'info', title: `${a.name}'s record deleted.` });
      announce(`${a.name}'s record deleted.`);
      showList();
    }),
  });
}
