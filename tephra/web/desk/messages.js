// Crew and passenger message drafts (WP5): DRAFT -> approved / edited / rejected by a dispatcher.
// The model writes the text with placeholders, code fills every fact; the sheet shows the filled
// text per language (EN / ID / JA) and who or what wrote it.

import { PATHS, api, errorCode, isUnavailable, problems, unavailableReason } from './api.js';
import { announce, byId, el, icon } from './dom.js';
import { holdButton } from './hold.js';
import { app } from './state.js';
import { toast } from './toast.js';
import { aiMark, openBSheet, unavailableCard } from './ui.js';

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
    app.hub.badges();
  }
}

export function onMessageEvent(m) {
  if (!m || typeof m !== 'object' || typeof m.id !== 'string' || !m.status) return;
  const known = app.messages.get(m.id);
  if (known && known.version > m.version) return;
  if (m.status === 'DRAFT') app.messages.set(m.id, m);
  else app.messages.delete(m.id);
  app.hub.badges();
  if (!known && m.status === 'DRAFT') announce(`New message draft: ${(KIND[m.kind] || [m.kind])[0]}${m.flight_no ? ` for ${m.flight_no}` : ''}.`);
}

const title = (m) => `${(KIND[m.kind] || [m.kind])[0]}${m.flight_no ? ` · ${m.flight_no}` : ''}`;

// Decide lists each draft message as one row (queue.js); app.hub.badges() redraws it.

// Drafting: from an approved advisory or an approved recovery plan.
// `openFirst`: from the receipt after an approval, the first draft opens as soon as it arrives.
export async function requestMessageDrafts(body, button = null, { openFirst = false } = {}) {
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
    app.hub.badges();
    const first = res.data.messages.find((m) => m.status === 'DRAFT' && m.kind === 'CREW_BRIEFING') || res.data.messages.find((m) => m.status === 'DRAFT');
    if (openFirst && first && (!button || button.isConnected)) {
      openMessage(first.id);
      return true;
    }
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
  let confirm = false; // the confirm step of the decision bar (tap on the primary)
  let hint = '';
  let hintTimer = 0;
  if (app.hub.leaveReview) app.hub.leaveReview();
  const sheet = openBSheet({ title: title(m), wide: true, full: true, onClose: () => window.clearTimeout(hintTimer) });

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

  // "Approve crew briefing (EN) for RFA1225": names only the languages that were drafted (5.5).
  const approveWords = (edited) => (edited
    ? `Approve edited text${current.flight_no ? ` for ${current.flight_no}` : ''}`
    : `Approve ${title(current).replace(/ · .*/, '').toLowerCase()} (${current.texts.map((t) => (LANG[t.language] || [t.language.toUpperCase()])[0]).join(', ')})${current.flight_no ? ` for ${current.flight_no}` : ''}`);
  const nowrapWords = (words) => {
    const at = current.flight_no ? words.lastIndexOf(current.flight_no) : -1;
    return at < 0 ? [document.createTextNode(words)]
      : [document.createTextNode(words.slice(0, at)), el('span', { class: 'nowrap', text: current.flight_no })];
  };

  function cancelConfirm() {
    confirm = false;
    setFooter();
    byId('bsheet').querySelector('.approve')?.focus();
  }

  function setHint(text) {
    hint = text;
    setFooter();
    announce(text);
    window.clearTimeout(hintTimer);
    hintTimer = window.setTimeout(() => {
      hint = '';
      setFooter();
    }, 4000);
  }

  // The one decision bar (6.5), the same as an advisory's but filled neutral (green stays
  // advisory-only): hold to approve, or tap for the confirm step; Edit and Reject at equal width.
  function setFooter() {
    if (busy) {
      sheet.setFooter(el('div', { class: 'fstack' }, el('button', { type: 'button', class: 'approve approve--neutral is-busy', disabled: true }, el('span', { class: 'spinner', 'aria-hidden': 'true' }), el('span', { text: 'Saving…' }))));
      return;
    }
    const offHint = el('p', { class: 'approve__hint', id: 'msg-hint', text: 'Reconnect to approve.' });
    if (view === 'reject') {
      const ok = reason.trim().length >= 3;
      const reject = el('button', { type: 'button', class: 'btn btn--neutral btn--block', 'aria-disabled': ok && !app.offline ? null : 'true', 'aria-describedby': app.offline ? 'msg-hint' : null, onclick: () => (app.offline ? null : ok ? submit('reject') : byId('msg-reason').focus()) }, el('span', { text: 'Reject message' }));
      sheet.setFooter(el('div', { class: 'fstack' }, reject, app.offline ? offHint : null,
        el('button', { type: 'button', class: 'btn btn--outline btn--block', onclick: () => go('review') }, el('span', { text: 'Cancel' }))));
      return;
    }
    const edited = view === 'edit';
    if (confirm) {
      const go2 = el('button', { type: 'button', class: 'btn btn--neutral', 'aria-disabled': app.offline ? 'true' : null, onclick: () => (app.offline ? null : submit(edited ? 'edit' : 'approve')) }, el('span', { text: 'Approve now' }));
      sheet.setFooter(el('div', { class: 'confirm', role: 'group', 'aria-labelledby': 'msg-confirm-q' },
        el('p', { id: 'msg-confirm-q', class: 'confirm__q', tabindex: '-1' }, ...nowrapWords(`${approveWords(edited)}?`)),
        el('p', { class: 'confirm__note', text: `Queued under ${app.me ? app.me.name : 'your name'} on TEPHRA's own outbound queue · nothing is sent to a passenger, crew member or aircraft.` }),
        app.offline ? offHint : null,
        el('div', { class: 'secondary' }, go2,
          el('button', { type: 'button', class: 'btn btn--outline', 'data-msg-cancel': '1', onclick: cancelConfirm }, el('span', { text: 'Cancel' })))));
      return;
    }
    const words = approveWords(edited);
    const primary = holdButton({
      label: () => nowrapWords(words),
      iconId: null,
      className: `approve approve--neutral${words.length > 34 ? ' approve--long' : ''}`,
      onHold: () => submit(edited ? 'edit' : 'approve'),
      onTap: () => {
        if (app.offline) return;
        confirm = true;
        setFooter();
        byId('msg-confirm-q')?.focus();
      },
      onEarlyRelease: setHint,
    });
    primary.setAttribute('aria-describedby', 'msg-hint');
    if (app.offline) primary.setAttribute('aria-disabled', 'true');
    const hintNode = el('p', { class: 'approve__hint', id: 'msg-hint' },
      el('span', { class: hint || app.offline ? 'hint-early' : null, text: app.offline ? 'Reconnect to approve.' : hint || 'Hold to approve, or tap to confirm.' }));
    sheet.setFooter(el('div', { class: 'fstack' }, primary, hintNode,
      el('div', { class: 'secondary' },
        el('button', { type: 'button', class: 'btn btn--outline', onclick: () => go(edited ? 'review' : 'edit') }, edited ? null : icon('i-pencil'), el('span', { text: edited ? 'Stop editing' : 'Edit text' })),
        el('button', { type: 'button', class: 'btn btn--outline', onclick: () => go('reject') }, el('span', { text: 'Reject…' })))));
  }

  function go(next) {
    view = next;
    notice = '';
    confirm = false;
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
        confirm = false;
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
    confirm = false;
    if (res.ok && res.data && res.data.id) {
      app.messages.delete(res.data.id);
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
