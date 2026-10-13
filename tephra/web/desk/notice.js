// "Paste a notice" (WP3 Notice Reader): a dispatcher pastes an observatory notice in English,
// Bahasa Indonesia, Japanese or Filipino. Gemini extracts fields; code checks each against the
// words it quoted. A field that is not a verbatim quote is dropped, and a notice that fails is
// shown as raw text with a "not verified" badge and never reaches the pipeline.

import { PATHS, api, isUnavailable, problems, unavailableReason } from './api.js';
import { announce, byId, el, icon } from './dom.js';
import { dayMonthHhmm } from './format.js';
import { app } from './state.js';
import { aiMark, codeChip, fromReplayChip, openBSheet, reportsHead, unavailableCard } from './ui.js';

const MAX_CHARS = 6000;
const MIN_CHARS = 20;
const FIELD_LABEL = {
  volcano: 'Volcano',
  notice_time: 'Notice time',
  colour_code: 'Colour code',
  alert_level: 'Alert level',
  ash_observed: 'Ash observed',
  plume_height: 'Plume height',
  direction: 'Direction',
  observer_type: 'Reported by',
};
const LANGS = { en: 'English', id: 'Bahasa Indonesia', ja: '日本語', fil: 'Filipino', other: 'Language not recognised' };
const LANG_CODE = { en: 'EN', id: 'ID', ja: 'JA', fil: 'FIL', other: '?' };
const SAMPLE_HINT = 'Paste the notice text exactly as published.';

export async function loadNotices() {
  const res = await api(PATHS.notices);
  if (res.ok && res.data && Array.isArray(res.data.notices)) {
    app.notices = res.data.notices;
    renderNotices();
  }
}

export function onNoticeEvent(n) {
  if (!n || typeof n !== 'object' || typeof n.id !== 'string') return;
  app.notices = [n, ...app.notices.filter((x) => x.id !== n.id)].slice(0, 20);
  renderNotices();
}

export const statusBadge = (n) => {
  if (n.status === 'verified') return el('span', { class: 'vbadge vbadge--ok' }, icon('i-check', 'st'), el('span', { text: 'Verified' }));
  if (n.status === 'ai_unavailable') return el('span', { class: 'vbadge vbadge--no' }, icon('st-caution', 'st'), el('span', { text: 'Not read (Notice reader gave no result)' }));
  return el('span', { class: 'vbadge vbadge--no' }, icon('st-caution', 'st'), el('span', { text: 'Not verified' }));
};

export function renderNotices() {
  const host = byId('notice-section');
  if (!host) return;
  host.hidden = app.notices.length === 0;
  reportsHead();
  if (!app.notices.length) {
    host.replaceChildren();
    return;
  }
  const rows = app.notices.slice(0, 6).map((n) => {
    const vol = n.vona ? n.vona.volcano_name : (n.fields.find((f) => f.name === 'volcano') || {}).value;
    return el('li', {}, el('button', { type: 'button', class: 'nrow', 'data-notice': n.id },
      statusBadge(n),
      el('span', { class: 'nrow__what' }, el('span', { class: 'nrow__vol', text: vol || 'Volcano not read' }),
        el('span', { class: 'nrow__meta', text: `${LANG_CODE[n.language] || '?'} · ${dayMonthHhmm(n.created_at)}` })),
      icon('i-chevron-right', 'icon nrow__go')));
  });
  // One line on Decide (R10.4) that opens in place: "Notices (4) ›".
  const box = el('details', { class: 'qlink__box ndisc', open: noticesOpen },
    el('summary', { class: 'qlink__btn' },
      el('span', { class: 'qlink__who', text: 'Notices' }),
      el('span', { class: 'qlink__t', text: `${app.notices.length} read from observatory text` }),
      icon('i-chevron-right', 'icon qlink__go disclosure')),
    el('ul', { class: 'nlist' }, rows));
  box.addEventListener('toggle', () => {
    noticesOpen = box.open;
  });
  host.replaceChildren(box);
}

let noticesOpen = false;

// Splits the notice into plain text and <mark>ed evidence, one mark per field, no overlaps.
function highlighted(text, fields) {
  const marks = [];
  fields.forEach((f, i) => {
    const at = f.evidence ? text.indexOf(f.evidence) : -1;
    if (at >= 0) marks.push({ start: at, end: at + f.evidence.length, i });
  });
  marks.sort((a, b) => a.start - b.start || b.end - a.end);
  const out = [];
  let pos = 0;
  for (const m of marks) {
    if (m.start < pos) continue;
    if (m.start > pos) out.push(document.createTextNode(text.slice(pos, m.start)));
    out.push(el('mark', { class: 'ev', 'data-f': String(m.i), tabindex: '-1', text: text.slice(m.start, m.end) }));
    pos = m.end;
  }
  if (pos < text.length) out.push(document.createTextNode(text.slice(pos)));
  return out;
}

export function readingView(n) {
  const out = [];
  const head = el('div', { class: 'nhead' }, statusBadge(n),
    el('span', { class: 'chip chip--sm', title: 'Language detected by the model', text: LANGS[n.language] || 'Language not recognised' }),
    fromReplayChip(n),
    n.status === 'ai_unavailable' ? null : aiMark('Read by Notice reader', n.llm_backend === 'stub' ? null : n.model_id));
  out.push(head);

  if (n.status === 'ai_unavailable') {
    out.push(unavailableCard(n.reason || 'no reason given', { title: 'Not read (Notice reader gave no result)', instead: 'Read it yourself. Nothing from it entered the picture.' }));
  } else if (n.status === 'verified') {
    out.push(el('div', { class: 'banner banner--approved', role: 'note' }, icon('i-check', 'st'),
      el('p', { text: `Every field below is a verbatim quote from the notice, checked by code. It joined the live picture as an observatory notice${n.vona ? ` for ${n.vona.volcano_name}` : ''} (${n.id}).` })));
  } else {
    out.push(el('div', { class: 'banner banner--caution', role: 'note' }, icon('st-caution', 'st'),
      el('p', {}, el('strong', { text: 'Not verified: ' }), `${(n.reason || 'a field did not match the notice.').replace(/^NOT VERIFIED:?\s*/i, '')} TEPHRA shows the raw text only and does not use this notice.`)));
  }
  if (n.problems && n.problems.length) {
    out.push(el('details', { class: 'disclose' }, el('summary', {}, icon('i-chevron-right', 'icon disclosure'), el('span', { text: `Checks that failed (${n.problems.length})` })),
      el('ul', { class: 'plist' }, n.problems.map((p) => el('li', { text: p })))));
  }

  const src = el('pre', { class: 'nsrc', lang: n.language && n.language !== 'other' ? n.language : null, 'aria-label': 'The notice, with quoted evidence highlighted' });
  src.append(...highlighted(n.text, n.fields));
  const fieldList = el('ul', { class: 'nfields' }, n.fields.map((f, i) => {
    const row = el('li', { class: 'nfield' },
      el('button', { type: 'button', class: 'nfield__btn', 'aria-pressed': 'false', 'data-f': String(i) },
        el('span', { class: 'nfield__k', text: FIELD_LABEL[f.name] || f.name }),
        el('span', { class: 'nfield__v', text: f.value }),
        el('span', { class: 'nfield__q' }, icon('i-quote', 'st'), el('span', { lang: n.language && n.language !== 'other' ? n.language : null, text: f.evidence }))),
      f.derived ? el('p', { class: 'nfield__d' }, codeChip('Code'), el('span', { text: f.derived })) : null);
    return row;
  }));
  fieldList.addEventListener('click', (event) => {
    const btn = event.target.closest('.nfield__btn');
    if (!btn) return;
    const on = btn.getAttribute('aria-pressed') !== 'true';
    for (const b of fieldList.querySelectorAll('.nfield__btn')) b.setAttribute('aria-pressed', 'false');
    for (const m of src.querySelectorAll('mark.ev')) m.classList.remove('is-on');
    if (on) {
      btn.setAttribute('aria-pressed', 'true');
      const mark = src.querySelector(`mark.ev[data-f="${btn.dataset.f}"]`);
      if (mark) {
        mark.classList.add('is-on');
        mark.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    }
  });
  if (n.fields.length) {
    out.push(el('h3', { class: 'ssub', text: `Extracted fields (${n.fields.length})` }),
      el('p', { class: 'fine', text: 'Tap a field to see its words in the notice. Values are what the model read, and the quote proves it.' }), fieldList);
  } else if (n.status !== 'ai_unavailable') {
    out.push(el('p', { class: 'note', text: 'No field passed the checks.' }));
  }
  out.push(el('h3', { class: 'ssub', text: 'The notice' }), src, el('p', { class: 'fine', text: `Notice id ${n.id}${n.vona ? ` · issued ${dayMonthHhmm(n.vona.issued_at)}` : ''}` }));
  return out;
}

export function openNotice(id) {
  const n = app.notices.find((x) => x.id === id);
  if (n) openBSheet({ title: 'Notice reading', body: el('div', { class: 'stack' }, ...readingView(n)), wide: true });
}

export function openPaste() {
  const area = el('textarea', {
    id: 'notice-text', class: 'field field--mono', rows: '9', maxlength: String(MAX_CHARS), spellcheck: 'false', autocomplete: 'off',
    placeholder: 'Paste the notice here', 'aria-describedby': 'notice-count notice-msg',
  });
  const count = el('p', { id: 'notice-count', class: 'counter' });
  const msg = el('div', { id: 'notice-msg', class: 'field-msg', 'aria-live': 'polite' });
  const result = el('div', { class: 'stack', 'aria-live': 'polite' });
  const go = el('button', { type: 'button', class: 'btn btn--neutral btn--block' }, icon('i-sparkle'), el('span', { text: 'Read the notice' }));
  const update = () => {
    const n = area.value.trim().length;
    count.textContent = `${n} / ${MAX_CHARS} · English, Bahasa Indonesia, Japanese or Filipino`;
    count.dataset.level = n > 0 && n < MIN_CHARS ? 'caution' : 'ok';
  };
  area.addEventListener('input', update);
  update();
  const sheet = openBSheet({
    title: 'Paste a notice',
    wide: true,
    body: el('div', { class: 'stack' },
      el('p', { class: 'note', text: `${SAMPLE_HINT} TEPHRA Assistant's Notice reader reads it, then code checks every field against the words it quoted. A notice that fails the check is not used.` }),
      el('label', { class: 'flabel', for: 'notice-text', text: 'Notice text' }), area, count, msg, result),
    footer: go,
  });
  go.addEventListener('click', async () => {
    const text = area.value.trim();
    if (text.length < MIN_CHARS) {
      msg.replaceChildren(el('p', { class: 'msg msg--caution' }, icon('st-caution', 'st'), el('span', { text: `Paste at least ${MIN_CHARS} characters.` })));
      area.focus();
      return;
    }
    if (app.offline) {
      msg.replaceChildren(el('p', { class: 'msg msg--serious' }, icon('st-serious', 'st'), el('span', { text: "You're offline. Reconnect to read a notice." })));
      return;
    }
    msg.replaceChildren();
    result.replaceChildren();
    go.disabled = true;
    go.replaceChildren(el('span', { class: 'spinner', 'aria-hidden': 'true' }), el('span', { text: 'Reading…' }));
    const res = await api(PATHS.noticePost, { method: 'POST', body: { text: area.value } });
    go.disabled = false;
    go.replaceChildren(icon('i-sparkle'), el('span', { text: 'Read another' }));
    if (res.ok && res.data && res.data.id) {
      onNoticeEvent(res.data);
      result.replaceChildren(...readingView(res.data));
      announce(`Notice read: ${res.data.status === 'verified' ? 'verified' : 'not verified'}.`);
      result.scrollIntoView({ block: 'start', behavior: 'smooth' });
      return;
    }
    if (isUnavailable(res)) {
      result.replaceChildren(unavailableCard(unavailableReason(res), { title: 'Not read (Notice reader gave no result)', instead: 'Read it yourself. Nothing from it entered the picture.' }));
      return;
    }
    const list = problems(res);
    const why = res.status === 0 ? "Can't reach the server." : res.status === 401 ? 'Your session has ended. Sign in again.' : `${(res.data && res.data.detail) || `HTTP ${res.status}`}${list.length ? `: ${list.join(' · ')}` : ''}`;
    msg.replaceChildren(el('p', { class: 'msg msg--serious' }, icon('st-serious', 'st'), el('span', { text: why })));
  });
  window.setTimeout(() => area.focus(), 50);
  return sheet;
}
