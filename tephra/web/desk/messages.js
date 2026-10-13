// Crew and passenger message drafts (WP5): DRAFT -> approved / edited / rejected by a dispatcher.
// The model writes the text with placeholders, code fills every fact; the sheet shows the filled
// text per language (EN / ID / JA) and who or what wrote it.

import { PATHS, api, errorCode, isUnavailable, problems, unavailableReason } from './api.js';
import { announce, byId, el, icon } from './dom.js';
import { hhmmz } from './format.js';
import { app } from './state.js';
import { toast } from './toast.js';
import { aiMark, openBSheet, sectionHead, unavailableCard } from './ui.js';

export const KIND = {
  CREW_BRIEFING: ['Crew briefing', 'i-aircraft'],
  PASSENGER_NOTICE: ['Passenger notice', 'i-user'],
  CREW_NOTICE: ['Crew notice', 'i-dispatcher'],
};
const LANG = { en: ['EN', 'English'], id: ['ID', 'Bahasa Indonesia'], ja: ['JA', '日本語 (Japanese)'] };
const LANG_ATTR = { en: 'en', id: 'id', ja: 'ja' };
const REASON_MAX = 500;

export const draftMessages = () => [...app.messages.values()].filter((m) => m.status === 'DRAFT');

export async function loadMessages() {
  const res = await api(PATHS.messages('DRAFT'));
  if (res.ok && res.data && Array.isArray(res.data.messages)) {
    app.messages = new Map(res.data.messages.filter((m) => m && m.id).map((m) => [m.id, m]));
    renderMessages();
    app.hub.badges();
  }
}

export function onMessageEvent(m) {
  if (!m || typeof m !== 'object' || typeof m.id !== 'string' || !m.status) return;
  const known = app.messages.get(m.id);
  if (known && known.version > m.version) return;
  if (m.status === 'DRAFT') app.messages.set(m.id, m);
  else app.messages.delete(m.id);
  renderMessages();
  app.hub.badges();
  if (!known && m.status === 'DRAFT') announce(`New message draft: ${(KIND[m.kind] || [m.kind])[0]}${m.flight_no ? ` for ${m.flight_no}` : ''}.`);
}

const title = (m) => `${(KIND[m.kind] || [m.kind])[0]}${m.flight_no ? ` · ${m.flight_no}` : ''}`;

function card(m) {
  const first = m.texts[0];
  const langs = m.texts.map((t) => (LANG[t.language] || [t.language.toUpperCase()])[0]).join(' · ');
  return el('li', { class: 'mcard' },
    el('button', { type: 'button', class: 'mcard__btn', 'data-msg': m.id },
      el('span', { class: 'mcard__row' },
        icon((KIND[m.kind] || [0, 'i-raw-text'])[1], 'icon'),
        el('span', { class: 'mcard__title', text: title(m) }),
        el('span', { class: 'mcard__langs', text: langs })),
      m.route ? el('span', { class: 'mcard__meta', text: `${m.route}${m.tail ? ` · ${m.tail}` : ''}` }) : null,
      el('span', { class: 'mcard__body', 'aria-hidden': 'true', lang: LANG_ATTR[first.language] || null, text: m.final_bodies[first.language] || first.body }),
      el('span', { class: 'tags' }, aiMark(undefined, m.llm_backend === 'stub' ? null : m.model_id),
        m.replay ? el('span', { class: 'chip chip--replay chip--sm' }, icon('i-replay', 'st'), el('span', { text: 'REPLAY' })) : null,
        el('span', { class: 'chip chip--sm' }, icon('i-clock', 'st'), el('span', { text: `drafted ${hhmmz(m.created_at)}` })))));
}

export function renderMessages() {
  const host = byId('msg-section');
  if (!host) return;
  const list = draftMessages().sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
  host.hidden = list.length === 0;
  if (!list.length) {
    host.replaceChildren();
    return;
  }
  // One line on Decide (R10.4) that opens in place: "Messages to approve (3) ›".
  const box = el('details', { class: 'qlink__box', open: msgOpen },
    el('summary', { class: 'qlink__btn' }, icon('i-dispatcher', 'icon qlink__ic'),
      el('span', { class: 'qlink__t' }, el('strong', { id: 'msg-title', text: `Messages to approve (${list.length})` })),
      icon('i-chevron-right', 'icon qlink__go disclosure')),
    el('p', { class: 'qlink__sub', text: "Crew and passenger drafts. Approved text goes only to TEPHRA's own outbound queue." }),
    el('ul', { class: 'mcards', 'aria-labelledby': 'msg-title' }, list.map(card)));
  box.addEventListener('toggle', () => {
    msgOpen = box.open;
  });
  host.replaceChildren(box);
}

let msgOpen = false;

// Drafting: from an approved advisory or an approved recovery plan.
export async function requestMessageDrafts(body, button = null) {
  if (app.offline) {
    toast({ tone: 'caution', title: "You're offline. Reconnect to draft messages." });
    return false;
  }
  const label = button ? [...button.childNodes] : null;
  if (button) {
    button.disabled = true;
    button.replaceChildren(el('span', { class: 'spinner', 'aria-hidden': 'true' }), el('span', { text: 'Drafting messages…' }));
  }
  const res = await api(PATHS.messageDraft, { method: 'POST', body });
  if (button) {
    button.disabled = false;
    button.replaceChildren(...label);
  }
  if (res.ok && res.data && Array.isArray(res.data.messages)) {
    for (const m of res.data.messages) if (m.status === 'DRAFT') app.messages.set(m.id, m);
    renderMessages();
    app.hub.badges();
    toast({ tone: 'ok', title: res.data.messages.length ? `${res.data.messages.length} message draft${res.data.messages.length === 1 ? '' : 's'} ready on Decide.` : 'No new messages to draft.' });
    app.hub.goTab('queue');
    return true;
  }
  if (isUnavailable(res)) {
    openBSheet({ title: 'Messages not drafted', body: unavailableCard(unavailableReason(res), { instead: 'No message was written. Write the crew or passenger text by hand.' }) });
    return false;
  }
  const why = res.status === 409 ? (res.data && res.data.detail) || 'The source is not approved yet.' : res.status === 404 ? 'The source no longer exists.' : (res.data && res.data.detail) || `HTTP ${res.status}`;
  toast({ tone: 'caution', title: `Messages not drafted: ${why}` });
  return false;
}

// --- the message sheet -------------------------------------------------------------------

export function openMessage(id) {
  const m = app.messages.get(id);
  if (!m) return;
  let view = 'review'; // review | edit | reject
  let lang = m.texts[0].language;
  let current = m;
  let busy = false;
  const edits = {};
  let reason = '';
  let notice = '';
  const sheet = openBSheet({ title: title(m), wide: true });

  const bodyOf = (msg, l) => msg.final_bodies[l] ?? (msg.texts.find((t) => t.language === l) || {}).body ?? '';

  function tabs() {
    const list = el('div', { class: 'ltabs', role: 'tablist', 'aria-label': 'Language' },
      current.texts.map((t) => el('button', {
        type: 'button', role: 'tab', id: `ltab-${t.language}`, class: 'ltab', 'aria-selected': String(t.language === lang),
        'aria-controls': 'lpanel', tabindex: t.language === lang ? '0' : '-1', lang: LANG_ATTR[t.language] || null,
        onclick: () => {
          lang = t.language;
          draw();
          byId(`ltab-${lang}`).focus();
        },
        onkeydown: (event) => {
          const i = current.texts.findIndex((x) => x.language === lang);
          const dir = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
          if (!dir) return;
          event.preventDefault();
          lang = current.texts[(i + dir + current.texts.length) % current.texts.length].language;
          draw();
          byId(`ltab-${lang}`).focus();
        },
      }, el('span', { class: 'ltab__code', text: (LANG[t.language] || [t.language])[0] }), el('span', { class: 'ltab__name', text: (LANG[t.language] || [0, ''])[1] }))));
    return list;
  }

  function draw() {
    const head = [
      el('p', { class: 'mmeta' },
        aiMark(undefined, current.llm_backend === 'stub' ? null : current.model_id),
        current.replay ? el('span', { class: 'chip chip--replay chip--sm' }, icon('i-replay', 'st'), el('span', { text: 'REPLAY' })) : null,
        el('span', { class: 'chip chip--sm', text: `v${current.version}` })),
      el('p', { class: 'note mnote', text: `${current.route ? `${current.route}. ` : ''}Written from the ${current.source_kind === 'advisory' ? 'approved advisory' : 'approved airport plan'}. ${current.llm_backend === 'stub' ? 'A code template wrote the words' : 'TEPHRA Assistant drafted the words'}. Code filled in every time, number and flight.` }),
    ];
    if (notice) head.push(el('div', { class: 'banner banner--caution', role: 'alert' }, icon('st-caution', 'st'), el('p', { text: notice })));
    const parts = [...head, tabs()];
    const active = current.texts.find((t) => t.language === lang) || current.texts[0];
    const panel = el('div', { id: 'lpanel', role: 'tabpanel', 'aria-labelledby': `ltab-${lang}`, class: 'lpanel' });
    if (view === 'edit') {
      const area = el('textarea', { id: 'msg-edit', class: 'field', rows: '10', lang: LANG_ATTR[lang] || null, 'aria-describedby': 'msg-edit-note' });
      area.value = edits[lang] ?? bodyOf(current, lang);
      area.addEventListener('input', () => {
        edits[lang] = area.value;
      });
      panel.append(el('label', { class: 'flabel', for: 'msg-edit', text: `Text in ${(LANG[lang] || [0, lang])[1]}` }), area,
        el('p', { id: 'msg-edit-note', class: 'note', text: 'Edit any language, then approve. Code checks that no number or time was added that is not a filled fact. Both versions stay in the audit log.' }));
    } else if (view === 'reject') {
      const area = el('textarea', { id: 'msg-reason', class: 'field', rows: '4', maxlength: String(REASON_MAX), 'aria-describedby': 'msg-reason-note' });
      area.value = reason;
      area.addEventListener('input', () => {
        reason = area.value;
        setFooter();
      });
      panel.append(el('label', { class: 'flabel', for: 'msg-reason', text: 'Reason (required, at least 3 characters)' }), area,
        el('p', { id: 'msg-reason-note', class: 'note', text: 'The reason is recorded in the audit log. A rejected message is not queued.' }));
    } else {
      panel.append(el('pre', { class: 'acars acars--body msg-text', lang: LANG_ATTR[lang] || null, text: bodyOf(current, lang) }));
      if (current.edited_bodies && current.edited_bodies[lang]) panel.append(el('p', { class: 'fine', text: 'Edited by a dispatcher.' }));
    }
    sheet.setBody(el('div', { class: 'stack' }, ...parts, panel));
    setFooter();
  }

  function setFooter() {
    if (busy) {
      sheet.setFooter(el('button', { type: 'button', class: 'btn btn--block is-busy', disabled: true }, el('span', { class: 'spinner', 'aria-hidden': 'true' }), el('span', { text: 'Saving…' })));
      return;
    }
    const off = app.offline ? el('p', { class: 'actions__offline' }, icon('i-offline', 'st'), el('span', { text: "You're offline. Reconnect to decide." })) : null;
    if (view === 'edit') {
      sheet.setFooter(el('div', { class: 'fstack' }, off,
        el('button', { type: 'button', class: 'btn btn--approve btn--block', disabled: app.offline, onclick: () => submit('edit') }, icon('i-check'), el('span', { text: 'Approve edited text' })),
        el('button', { type: 'button', class: 'btn btn--block', onclick: () => go('review') }, el('span', { text: 'Cancel' }))));
    } else if (view === 'reject') {
      const ok = reason.trim().length >= 3;
      sheet.setFooter(el('div', { class: 'fstack' }, off,
        el('button', { type: 'button', class: 'btn btn--reject-solid btn--block', 'aria-disabled': ok ? null : 'true', disabled: app.offline, onclick: () => (ok ? submit('reject') : byId('msg-reason').focus()) }, icon('i-x'), el('span', { text: 'Reject message' })),
        el('button', { type: 'button', class: 'btn btn--block', onclick: () => go('review') }, el('span', { text: 'Cancel' }))));
    } else {
      sheet.setFooter(el('div', { class: 'fstack' }, off,
        el('button', { type: 'button', class: 'btn btn--approve btn--block btn--primary', disabled: app.offline, onclick: () => submit('approve') }, icon('i-check'), el('span', { text: `Approve ${current.texts.length} language${current.texts.length === 1 ? '' : 's'}` })),
        el('p', { class: 'approve__hint', text: "Queues on TEPHRA's own outbound queue. Nothing is sent to a passenger, crew member or aircraft." }),
        el('div', { class: 'secondary' },
          el('button', { type: 'button', class: 'btn', onclick: () => go('edit') }, icon('i-pencil'), el('span', { text: 'Edit text' })),
          el('button', { type: 'button', class: 'btn btn--reject', onclick: () => go('reject') }, icon('i-x'), el('span', { text: 'Reject…' })))));
    }
  }

  function go(next) {
    view = next;
    notice = '';
    draw();
  }

  async function submit(kind) {
    if (busy || app.offline) return;
    let body = { version: current.version };
    if (kind === 'edit') {
      const bodies = {};
      for (const t of current.texts) {
        const text = (edits[t.language] ?? bodyOf(current, t.language)).trim();
        if (text && text !== t.body) bodies[t.language] = text;
      }
      if (!Object.keys(bodies).length) {
        view = 'review';
        notice = 'Unchanged from the draft. Approve it as drafted, or change the text.';
        draw();
        return;
      }
      body = { version: current.version, bodies };
    } else if (kind === 'reject') body = { version: current.version, reason: reason.trim() };
    busy = true;
    setFooter();
    const res = await api(PATHS.messageDecide(current.id, kind), { method: 'POST', body });
    busy = false;
    if (res.ok && res.data && res.data.id) {
      app.messages.delete(res.data.id);
      renderMessages();
      app.hub.badges();
      sheet.close();
      const word = { approve: 'Approved', edit: 'Approved with your edits', reject: 'Rejected' }[kind];
      toast({ tone: kind === 'reject' ? 'rejected' : 'ok', title: `${word}: ${title(res.data)}${kind === 'reject' ? ' · reason recorded.' : ` · queued under ${app.me ? app.me.name : 'you'}. Not sent to anyone.`}` });
      announce(`${word}: ${title(res.data)}.`);
      return;
    }
    if (res.status === 409 && res.data && res.data.current) {
      current = res.data.current;
      if (current.status === 'DRAFT') app.messages.set(current.id, current);
      else app.messages.delete(current.id);
      renderMessages();
      app.hub.badges();
      notice = current.status === 'DRAFT' ? 'This message changed while you were reviewing it. Review the new version.' : `This message was already ${current.status.toLowerCase()}.`;
      view = 'review';
      draw();
      return;
    }
    if (res.status === 422) {
      const list = problems(res);
      notice = `Check the text: ${list.length ? list.join(' · ') : 'the change was not accepted'}`;
      draw();
      return;
    }
    notice = res.status === 0 ? "Can't reach the server. Try again when you are back online." : res.status === 401 ? 'Your session has ended. Sign in again to decide.' : `Not saved: ${(res.data && res.data.detail) || errorCode(res) || `HTTP ${res.status}`}`;
    draw();
  }

  draw();
}
