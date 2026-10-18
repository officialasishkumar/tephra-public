// Ask TEPHRA (WP2): a chat over TEPHRA's own tools. Every answer carries claims, each with the
// evidence ids it rests on; a chip opens that evidence verbatim. A "How I answered" strip shows
// the tool calls, the validator and the model. A refusal is its own card. Push-to-talk records
// with MediaRecorder; a spoken reply plays from a blob URL. Nothing here changes any state.

import { PATHS, api, isUnavailable, problems, unavailableReason } from './api.js';
import { announce, byId, el, icon, reducedMotion } from './dom.js';
import { app } from './state.js';
import { aiMark, fromReplayChip, openBSheet, unavailableCard } from './ui.js';
import { infoButton } from '../wall/info.js';
import { deskAi, openBudget } from './budget.js';
import { reasonClass } from '../wall/x-parts.js';
import { has } from '../wall/features.js';

const MAX_Q = 500;
const MAX_REC_S = 30;
const KIND_WORD = { fact: 'Fact', number: 'Number', inference: 'Inference' };
const LANG_NAME = { en: 'English', id: 'Bahasa Indonesia', ja: '日本語' };
const SUGGESTED = [
  'Which flights enter the area soonest?',
  'Where do the official products disagree?',
  'What if the ash extends 50 km further?',
];
const READ_ONLY = 'Read-only: Ask changes nothing.';

// R10.5: each evidence chip says in words what it rests on; the raw tool id is under "How I
// answered". Unknown tools keep their own name (never a paraphrase).
const TOOL_WORDS = {
  exposed_flights: 'flights heading in',
  cone: "TEPHRA's area",
  flight: 'this flight',
  plan: "the flight's plan",
  feeds: 'data feeds',
  ai_failures: 'Hand-plan list',
  duty_brief: 'Coordinator brief',
};
const toolWords = (tool) => TOOL_WORDS[tool] || String(tool);

// The offline stub's text is written by code, so it is put in plain words here (R10.5, R12.10).
// A model's answer is always shown exactly as written. The stub's opening sentence is the same on
// every answer: it is said once, above the conversation (STUB_NOTE), not on each bubble (owner,
// 17 Oct: "don't say no model everywhere"); each answer keeps the code mark.
const STUB_PREFIX = 'NO MODEL: this is the offline stub, which does not read the question.';
const STUB_NOTE = 'Answers are code counts: the question is not read.';
function stubWords(text, a) {
  if (a.llm_backend !== 'stub' || typeof text !== 'string') return text;
  return text.replace(STUB_PREFIX, '').trim().replace(/\ba hazard cone\b/g, "TEPHRA's area");
}
const stubOn = () => Boolean(app.state && app.state.llm && app.state.llm.backend === 'stub');

const canRecord = () => Boolean(navigator.mediaDevices) && typeof MediaRecorder !== 'undefined';

let busy = null; // AbortController while a question is out
let recorder = null;
let log = null;
let composer = null;
let audio = null; // { el, url, id }
let seq = 0;

// --- layout ----------------------------------------------------------------------------------

export function initAsk() {
  const panel = byId('panel-ask');
  log = el('div', { id: 'ask-log', class: 'alog', role: 'log', 'aria-label': 'Conversation with Ask TEPHRA', 'aria-live': 'off' });
  const input = el('textarea', {
    id: 'ask-input', class: 'field askin', rows: '1', maxlength: String(MAX_Q), autocomplete: 'off', enterkeyhint: 'send',
    placeholder: 'Type a question…', 'aria-label': 'Your question',
  });
  const mic = el('button', { type: 'button', id: 'ask-mic', class: 'abtn abtn--mic', 'aria-label': 'Talk: tap to start recording, tap again to send' }, icon('i-mic'));
  const send = el('button', { type: 'submit', id: 'ask-send', class: 'abtn abtn--send', 'aria-label': 'Send question' }, icon('i-send'));
  const ctx = el('p', { id: 'ask-ctx', class: 'actx', hidden: true });
  // while the assistant is paused Ask says so before a question, not after (docs/UI-AI-QUIET.md
  // K102); why it is paused is said in the assistant sheet, behind "Why ›" (8.6)
  const paused = el('p', { id: 'ask-paused', class: 'note', role: 'status', hidden: true });
  // with no model connected, what an answer is, said once for the conversation
  const stubNote = el('p', { id: 'ask-stub', class: 'note astub', hidden: true }, icon('i-code', 'st'), el('span', { text: STUB_NOTE }));
  const form = el('form', { class: 'acomposer', novalidate: true }, paused, ctx, el('div', { class: 'acomposer__row' }, input, mic, send),
    el('p', { id: 'ask-status', class: 'fine acomposer__note', 'aria-live': 'polite', text: READ_ONLY }));
  composer = { form, input, mic, send, ctx };
  // Desk redesign 5.8: a conversation, oldest at the top; the newest answer scrolls into view
  // above the composer, which is pinned at the bottom of the Ask drawer (UI-DESIGN 10.18). The suggestions show
  // only before the first question.
  const sugg = el('div', { id: 'ask-sugg', class: 'asugg-wrap' });
  panel.replaceChildren(
    el('div', { class: 'phead' },
      el('div', { class: 'phead__line' },
        el('h1', { id: 'ask-title', class: 'phead__title', tabindex: '-1', text: 'Ask TEPHRA' }),
        infoButton({ topic: 'ask', label: 'About Ask TEPHRA', text: "Answers use only TEPHRA's own tools and show where each claim comes from. English, Bahasa Indonesia or Japanese." })),
      stubNote),
    sugg, log, form);
  sugg.addEventListener('click', onLogClick);
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    if (busy) {
      busy.abort();
      return;
    }
    submit();
  });
  input.addEventListener('input', () => autosize(input));
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      form.requestSubmit();
    }
  });
  mic.addEventListener('click', toggleMic);
  if (!canRecord()) {
    mic.disabled = true;
    mic.title = 'This browser cannot record audio. Type your question.';
  }
  log.addEventListener('click', onLogClick);
  drawEmpty();
  drawPaused();
  drawStub();
  document.addEventListener('tephra:ai', drawStub);
  drawVoice();
  document.addEventListener('tephra:ai', drawPaused);
  // the features arrive with the state, which redraws the chip (budget.js drawAiChip)
  document.addEventListener('tephra:ai', drawVoice);
}

// Push-to-talk is the `voice` feature (SPEC 5.3): without it the mic is not drawn; typing stays.
function drawVoice() {
  if (composer) composer.mic.hidden = !has('voice');
}

function drawPaused() {
  const note = byId('ask-paused');
  if (!note) return;
  const ai = deskAi();
  // the newest answer already says it is paused, with its own "Why ›": said once (review clutter 5)
  const said = Boolean(log && log.lastElementChild && log.lastElementChild.querySelector('[data-paused]'));
  note.hidden = ai.kind !== 'paused' || said;
  if (ai.kind !== 'paused') {
    note.replaceChildren();
    return;
  }
  if (note.childNodes.length) return;
  note.replaceChildren('Ask cannot answer while the assistant is paused. ',
    el('button', { type: 'button', class: 'linkbtn', 'aria-label': 'Why: open the TEPHRA Assistant sheet', onclick: openBudget }, el('span', { text: 'Why ›' })));
}

function drawStub() {
  const note = byId('ask-stub');
  if (note) note.hidden = !stubOn();
}

function autosize(input) {
  input.style.height = 'auto';
  input.style.height = `${Math.min(input.scrollHeight, 120)}px`;
}

function drawEmpty() {
  const host = byId('ask-sugg');
  host.replaceChildren(
    el('ul', { class: 'asugg', 'aria-label': 'Suggested questions' }, SUGGESTED.map((q) =>
      el('li', {}, el('button', { type: 'button', class: 'asugg__btn', 'data-q': q }, el('span', { text: q }))))));
}

export function setFlightContext(adv) {
  app.askFlight = adv ? { id: adv.flight_id, proxy: adv.proxy_flight } : null;
  const ctx = composer.ctx;
  if (!app.askFlight) {
    ctx.hidden = true;
    ctx.replaceChildren();
    return;
  }
  ctx.hidden = false;
  ctx.replaceChildren(icon('i-aircraft', 'st'), el('span', { text: `About ${app.askFlight.proxy}` }),
    el('button', { type: 'button', class: 'actx__x', 'aria-label': `Stop asking about ${app.askFlight.proxy}`, onclick: () => setFlightContext(null) }, icon('i-x')));
}

// The drawer opens ready to type: the question box takes focus.
export function focusAsk() {
  const input = byId('ask-input');
  if (input) input.focus({ preventScroll: true });
  scrollEnd();
}

// --- sending ---------------------------------------------------------------------------------

function onLogClick(event) {
  const q = event.target.closest('[data-q]');
  if (q) {
    composer.input.value = q.dataset.q;
    submit();
    return;
  }
  const chip = event.target.closest('[data-ev]');
  if (chip) {
    const msg = chip.closest('.amsg');
    const answer = msg && msg._answer;
    if (answer) openEvidence(answer, chip.dataset.ev);
    return;
  }
  const speak = event.target.closest('[data-speak]');
  if (speak) speakAnswer(speak);
  const follow = event.target.closest('[data-follow]');
  if (follow) {
    composer.input.value = follow.dataset.follow;
    submit();
  }
}

function setBusy(on) {
  composer.send.replaceChildren(icon(on ? 'i-stop' : 'i-send'));
  composer.send.setAttribute('aria-label', on ? 'Stop waiting for the answer' : 'Send question');
  composer.send.classList.toggle('is-stop', on);
  composer.input.disabled = on;
  composer.mic.disabled = on || !canRecord();
}

// Brings the newest turn into view above the pinned composer. With `target` (the answer that just
// landed) its first lines go just under the sticky header when it would start under the composer
// or above the header, so an answer never lands below the fold on a phone (5.8, A19).
function scrollEnd(target = null) {
  window.requestAnimationFrame(() => {
    const node = target && target.isConnected ? target : log.lastElementChild;
    if (!node) return;
    // the drawer's panel scrolls, under its pinned composer
    const box = byId('panel-ask');
    const r = node.getBoundingClientRect();
    const top = box.getBoundingClientRect().top;
    const floor = composer.form.getBoundingClientRect().top;
    if (r.top >= top && r.bottom <= floor) return;
    // the answer's top at the drawer's top; a short answer sits just above the composer instead
    const delta = r.height < floor - top - 16 ? r.bottom - floor + 8 : r.top - top - 16;
    box.scrollTo({ top: Math.max(0, box.scrollTop + delta), behavior: reducedMotion() ? 'auto' : 'smooth' });
  });
}

const youBubble = (text, { voice = false } = {}) =>
  el('div', { class: 'amsg amsg--you' }, el('p', { class: 'abubble' }, voice ? icon('i-mic', 'st') : null, el('span', { text })));

function thinking(label) {
  return el('div', { class: 'amsg amsg--ai amsg--wait', role: 'status' },
    el('div', { class: 'acard acard--wait' }, el('span', { class: 'spinner', 'aria-hidden': 'true' }), el('span', { text: label }), el('span', { class: 'sr-only', text: 'Waiting for TEPHRA' })));
}

async function submit() {
  const text = composer.input.value.trim();
  if (!text || busy) return;
  if (app.offline) {
    announce("You're offline. Reconnect to ask.");
    composer.form.querySelector('#ask-status').textContent = "You're offline. Reconnect to ask.";
    return;
  }
  composer.form.querySelector('#ask-status').textContent = READ_ONLY;
  const wait = thinking("Reading TEPHRA's tools…");
  byId('ask-sugg').hidden = true;
  log.append(el('div', { class: 'aturn' }, youBubble(text), wait));
  drawPaused();
  composer.input.value = '';
  autosize(composer.input);
  scrollEnd();
  busy = new AbortController();
  setBusy(true);
  const body = { question: text };
  if (app.askFlight) body.flight_id = app.askFlight.id;
  const res = await api(PATHS.ask, { method: 'POST', body, signal: busy.signal });
  busy = null;
  setBusy(false);
  composer.input.focus({ preventScroll: true });
  finish(wait, res, text);
}

function finish(wait, res, question) {
  if (res.aborted) {
    wait.replaceWith(el('div', { class: 'amsg amsg--ai' }, el('p', { class: 'acard acard--note', text: 'Stopped. TEPHRA may still have used a model call for this question.' })));
    return;
  }
  if (res.ok && res.data && typeof res.data.answer === 'string') {
    const node = answerCard(res.data);
    wait.replaceWith(node);
    // said once, in full, through the page's one polite region (the log itself stays aria-live
    // off), with the same attribution the card shows: the mark's words only when a model answered
    const said = res.data.status === 'refused' ? `Not in the evidence TEPHRA has. ${res.data.refusal_reason || ''}` : stubWords(res.data.answer, res.data);
    const by = res.data.llm_backend === 'stub' || !res.data.model_id || res.data.model_id === 'stub' ? '' : ' Answered by TEPHRA Assistant.';
    announce(`Answer: ${said.trim()}${by}`);
    scrollEnd(node);
    return;
  }
  let card;
  let paused = false;
  const retry = () => { composer.input.value = question; submit(); };
  if (isUnavailable(res)) {
    // a quota refusal: what happened and "Why ›", never the cause (it is in the assistant sheet,
    // 8.6). "Paused" only while the whole assistant is; then there is no retry until it is back, and
    // the question goes back into the box so it is not typed again. Any other cause can be asked
    // again now.
    const quota = reasonClass(unavailableReason(res)) === 'budget';
    paused = quota && deskAi().kind === 'paused';
    card = unavailableCard(unavailableReason(res), paused
      ? { title: 'TEPHRA Assistant is paused.', instead: 'Your question is back in the box: send it again when the assistant is on. The Wall shows every flight and count.', onWhy: openBudget }
      : quota
        ? { title: 'No answer: Ask did not run', instead: 'Ask again, or read the Wall.', onRetry: retry, onWhy: openBudget }
        : { title: 'No answer: Ask gave no result', instead: 'Ask again, or read the Wall.', onRetry: retry });
    if (paused && !composer.input.value.trim()) {
      composer.input.value = question;
      autosize(composer.input);
    }
  } else if (res.status === 401) card = unavailableCard('Your session has ended. Sign in again.', { title: 'Not asked', instead: '', serious: true });
  else if (res.status === 0) card = unavailableCard("Can't reach the server.", { title: 'Not asked', instead: 'Check your connection and ask again.', onRetry: retry, serious: true });
  else card = unavailableCard((res.data && res.data.detail) || `HTTP ${res.status}`, { title: 'Not answered', instead: '', serious: true });
  const failNode = el('div', { class: 'amsg amsg--ai', 'data-paused': paused ? '1' : null }, card);
  wait.replaceWith(failNode);
  announce('The question was not answered.');
  drawPaused();
  scrollEnd(failNode);
}

// --- the answer card -------------------------------------------------------------------------

const evLabel = (a, id) => {
  const e = a.evidence.find((x) => x.id === id);
  return e ? `${id}` : id;
};

function chipRow(answer, ids) {
  return ids.map((id) => {
    const e = answer.evidence.find((x) => x.id === id);
    return el('button', {
      type: 'button', class: 'evchip', 'data-ev': id,
      'aria-label': `From ${e ? toolWords(e.tool) : id} (evidence ${id}): open the verbatim result`, title: e ? `${id} ${e.tool}: ${e.summary}` : id,
    }, el('span', { class: 'evchip__tool', text: `from: ${e ? toolWords(e.tool) : evLabel(answer, id)}` }));
  });
}

function stepStrip(a) {
  const steps = [];
  steps.push(['i-chat', 'Question', a.flight_id ? `about flight ${a.flight_id}` : 'asked', 'ok']);
  for (const e of a.evidence) steps.push(['i-code', `${e.id} ${e.tool} (${toolWords(e.tool)})`, e.summary, 'ok', e.id]);
  const nTools = a.tool_calls.length;
  if (!a.evidence.length) steps.push(['i-info', 'No tool was called', 'The model answered from the question alone.', 'warn']);
  const cited = new Set(a.claims.flatMap((c) => c.evidence_ids));
  steps.push(['i-check', 'validator', `${a.claims.length} claim${a.claims.length === 1 ? '' : 's'} checked against ${cited.size} evidence item${cited.size === 1 ? '' : 's'}: every number, flight and airport in the answer appears in a tool result${a.repaired ? ' (after one repair)' : ''}`, 'ok']);
  steps.push(['i-model', 'model', a.llm_backend === 'stub' ? 'none: the offline stub' : a.model_id, 'ok']);
  steps.push(['i-user', 'human gate', 'Ask only reads. It cannot approve or change anything.', 'ok']);
  const list = el('ol', { class: 'steps' }, steps.map(([ic, k, v, tone, ev], i) =>
    el('li', { class: `step step--${tone}` },
      el('span', { class: 'step__dot' }, icon(ic, 'st')),
      el('span', { class: 'step__body' }, el('span', { class: 'step__k', text: k }),
        el('span', { class: 'step__v', text: v }),
        ev ? el('button', { type: 'button', class: 'step__open', 'data-ev': ev }, el('span', { text: `Open ${ev}` })) : null))));
  return el('details', { class: 'disclose how' },
    el('summary', {}, icon('i-chevron-right', 'icon disclosure'), el('span', { text: 'How I answered' }),
      el('span', { class: 'how__sum', text: `${nTools} tool call${nTools === 1 ? '' : 's'} · validator passed` })), list);
}

export function answerCard(a) {
  const wrap = el('div', { class: 'amsg amsg--ai' });
  wrap._answer = a;
  const refused = a.status === 'refused';
  const card = el('article', { class: `acard ${refused ? 'acard--refused' : ''}`.trim(), 'aria-label': refused ? 'Refusal' : 'Answer' });
  if (refused) {
    card.append(el('p', { class: 'acard__refuse' }, icon('st-info', 'st'), el('span', { text: 'Not in the evidence I have' })),
      el('p', { class: 'acard__text', lang: a.language, text: stubWords(a.answer || a.refusal_reason || '', a) }));
    if (a.refusal_reason && a.refusal_reason !== a.answer) card.append(el('p', { class: 'fine', text: a.refusal_reason }));
    if (a.evidence.length) {
      card.append(el('p', { class: 'caps acard__k', text: 'What I checked' }), el('div', { class: 'evrow' }, chipRow(a, a.evidence.map((e) => e.id))));
    }
  } else {
    card.append(el('p', { class: 'acard__text', lang: a.language, text: stubWords(a.answer, a) }));
    // Claims first (R10.5): each one with the evidence it rests on, in words.
    if (a.claims.length) {
      card.append(el('ul', { class: 'clist', 'aria-label': `Claims (${a.claims.length}), each resting on evidence` }, a.claims.map((c) =>
        el('li', { class: `claim claim--${c.kind}` },
          el('span', { class: 'claim__kind', text: KIND_WORD[c.kind] || c.kind }),
          el('span', { class: 'claim__text', lang: a.language, text: stubWords(c.text, a) }),
          el('span', { class: 'evrow' }, chipRow(a, c.evidence_ids))))));
    }
  }
  card.append(stepStrip(a));
  if (a.follow_ups && a.follow_ups.length) {
    card.append(el('div', { class: 'afollow' }, a.follow_ups.map((q) => el('button', { type: 'button', class: 'asugg__btn', 'data-follow': q }, el('span', { text: q })))));
  }
  // who answered: a model's mark sits in the foot; the code mark leads the answer's words, so it
  // never reads as a mark on the language chip beside it (UX verify, 17 Oct)
  const mark = aiMark('Answered by TEPHRA Assistant', a.llm_backend === 'stub' ? null : a.model_id, { code: 'Counted by code' });
  const byCode = mark.classList.contains('ai-mark--none');
  const lead = card.querySelector('.acard__text');
  if (byCode && lead) {
    mark.setAttribute('lang', 'en');
    lead.prepend(mark, ' ');
  }
  card.append(el('div', { class: 'acard__foot' },
    has('voice') ? el('button', { type: 'button', class: 'spk', 'data-speak': a.id, 'aria-label': 'Play the answer aloud' }, icon('i-volume'), el('span', { text: 'Listen' })) : null,
    el('span', { class: 'acard__meta' },
      byCode && lead ? null : mark,
      el('span', { class: 'chip chip--sm', title: 'Language of the question and the answer', text: LANG_NAME[a.language] || a.language }),
      fromReplayChip(a)),
    el('span', { class: 'spk__msg fine', role: 'status' })));
  wrap.append(card);
  return wrap;
}

function openEvidence(a, id) {
  const e = a.evidence.find((x) => x.id === id);
  if (!e) return;
  const cited = a.claims.filter((c) => c.evidence_ids.includes(id));
  openBSheet({
    title: `Evidence ${e.id}: ${toolWords(e.tool)}`,
    wide: true,
    body: el('div', { class: 'stack' },
      el('p', { class: 'evh' }, el('span', { class: 'evchip evchip--static' }, el('span', { class: 'evchip__id', text: e.id }), el('span', { class: 'evchip__tool', text: e.tool })), e.args && Object.keys(e.args).length ? el('span', { class: 'mono evh__args', text: JSON.stringify(e.args) }) : null),
      el('p', { class: 'evsum', text: e.summary }),
      e.source_ids && e.source_ids.length ? el('div', {}, el('p', { class: 'caps', text: 'Source ids' }), el('ul', { class: 'srcids' }, e.source_ids.map((s) => el('li', { class: 'mono', text: s })))) : null,
      cited.length ? el('div', {}, el('p', { class: 'caps', text: 'Claims resting on it' }), el('ul', { class: 'plist' }, cited.map((c) => el('li', { text: c.text })))) : null,
      el('p', { class: 'caps', text: 'Tool result, verbatim' }),
      el('pre', { class: 'acars evpre', tabindex: '0', 'aria-label': 'The tool result as returned', text: JSON.stringify(e.result, null, 2) }),
      el('p', { class: 'fine', text: 'Written by TEPHRA code from the feeds. A what-if is not an advisory and changed nothing.' })),
  });
}

// --- spoken answer ---------------------------------------------------------------------------

async function speakAnswer(button) {
  const msg = button.parentElement.querySelector('.spk__msg');
  if (audio && audio.id === button.dataset.speak && audio.el && !audio.el.paused) {
    audio.el.pause();
    button.classList.remove('is-playing');
    return;
  }
  stopAudio();
  button.disabled = true;
  button.classList.add('is-loading');
  msg.textContent = 'Preparing the voice reply…';
  const res = await api(PATHS.askSpeak, { method: 'POST', body: { answer_id: button.dataset.speak }, blob: true });
  button.disabled = false;
  button.classList.remove('is-loading');
  if (res.ok && res.data instanceof Blob) {
    const url = URL.createObjectURL(res.data);
    const player = new Audio(url);
    audio = { el: player, url, id: button.dataset.speak };
    player.addEventListener('ended', () => {
      button.classList.remove('is-playing');
      msg.textContent = '';
    });
    player.addEventListener('error', () => {
      button.classList.remove('is-playing');
      msg.textContent = 'Voice reply unavailable: this browser could not play the audio. The text answer stands.';
    });
    button.classList.add('is-playing');
    msg.textContent = 'Playing (Gemini speech).';
    player.play().catch(() => {
      button.classList.remove('is-playing');
      msg.textContent = 'Voice reply unavailable: the browser blocked playback. Tap Listen again.';
    });
    return;
  }
  button.classList.remove('is-playing');
  msg.textContent = isUnavailable(res) ? `Voice reply unavailable: ${unavailableReason(res)}. The text answer stands.` : res.status === 0 ? "Voice reply unavailable: can't reach the server." : `Voice reply unavailable (HTTP ${res.status}). The text answer stands.`;
}

function stopAudio() {
  if (!audio) return;
  audio.el.pause();
  URL.revokeObjectURL(audio.url);
  for (const b of log.querySelectorAll('.spk.is-playing')) b.classList.remove('is-playing');
  audio = null;
}

// --- push to talk ----------------------------------------------------------------------------

function pickMime() {
  for (const m of ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']) {
    if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(m)) return m;
  }
  return '';
}

function micStatus(text) {
  composer.form.querySelector('#ask-status').textContent = text;
}

async function toggleMic() {
  if (recorder) {
    stopRecording();
    return;
  }
  if (busy) return;
  if (app.offline) {
    micStatus("You're offline. Reconnect to talk, or type your question.");
    return;
  }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    micStatus('Microphone blocked or missing. Allow it in the browser, or type your question.');
    announce('Microphone unavailable. Type your question.');
    return;
  }
  const mime = pickMime();
  let rec;
  try {
    rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
  } catch {
    for (const t of stream.getTracks()) t.stop();
    micStatus('This browser cannot record audio. Type your question.');
    return;
  }
  const chunks = [];
  const started = performance.now();
  rec.addEventListener('dataavailable', (e) => {
    if (e.data && e.data.size) chunks.push(e.data);
  });
  rec.addEventListener('stop', () => {
    for (const t of stream.getTracks()) t.stop();
    window.clearInterval(recorder && recorder.timer);
    const cancelled = recorder && recorder.cancelled;
    recorder = null;
    composer.mic.classList.remove('is-rec');
    composer.mic.setAttribute('aria-pressed', 'false');
    composer.mic.setAttribute('aria-label', 'Talk: tap to start recording, tap again to send');
    if (cancelled || !chunks.length || performance.now() - started < 500) {
      micStatus('Too short. Tap the mic, speak, then tap it again.');
      return;
    }
    sendVoice(new Blob(chunks, { type: rec.mimeType || mime || 'audio/webm' }));
  });
  recorder = { rec, timer: 0, cancelled: false };
  rec.start();
  composer.mic.classList.add('is-rec');
  composer.mic.setAttribute('aria-pressed', 'true');
  composer.mic.setAttribute('aria-label', 'Recording: tap to stop and send');
  announce('Recording. Tap the mic again to send.');
  const tick = () => {
    const s = Math.floor((performance.now() - started) / 1000);
    micStatus(`Recording ${s}s of ${MAX_REC_S}s. Tap the mic to send.`);
    if (s >= MAX_REC_S) stopRecording();
  };
  tick();
  recorder.timer = window.setInterval(tick, 500);
}

function stopRecording() {
  if (recorder && recorder.rec.state !== 'inactive') recorder.rec.stop();
}

async function sendVoice(blob) {
  if (blob.size > 1024 * 1024) {
    micStatus('That recording is too long (over 1 MB). Try a shorter question.');
    return;
  }
  const mine = ++seq;
  const wait = thinking('Listening to your question…');
  byId('ask-sugg').hidden = true;
  log.append(el('div', { class: 'aturn' }, wait));
  scrollEnd();
  micStatus('Sending the recording…');
  const form = new FormData();
  const ext = blob.type.includes('mp4') ? 'm4a' : blob.type.includes('ogg') ? 'ogg' : 'webm';
  form.append('audio', blob, `question.${ext}`);
  if (app.askFlight) form.append('flight_id', app.askFlight.id);
  busy = new AbortController();
  setBusy(true);
  const res = await api(PATHS.askVoice, { method: 'POST', form, signal: busy.signal });
  busy = null;
  setBusy(false);
  micStatus(READ_ONLY);
  if (mine !== seq) return;
  if (res.ok && res.data && res.data.answer) {
    const heard = res.data.transcript && res.data.transcript.text;
    const you = youBubble(heard || res.data.answer.question, { voice: true });
    you.querySelector('.abubble').append(el('span', { class: 'abubble__src', text: `heard by ${res.data.transcript.model_id === 'stub' ? 'the offline stub' : res.data.transcript.model_id}` }));
    wait.before(you);
    finish(wait, { ok: true, data: res.data.answer }, heard || '');
    return;
  }
  const heard = (problems(res).find((p) => p.startsWith('transcript:')) || '').replace(/^transcript:\s*/, '');
  if (heard) wait.before(youBubble(heard, { voice: true }));
  finish(wait, res, heard);
}
