// Sign-in (docs/UI-DESIGN.md 10.2): name, PIN with an on-screen PIN pad, and the states
// wrong PIN, too many attempts (429 + Retry-After countdown), Desk switched off (503),
// invalid name (422) and offline. While /api/state says visitor_access, two tabs choose the way in:
// the visitor card (SPEC 5.1: one tap, an optional name, no PIN, REPLAY only) or the PIN form.

import { PATHS, api, errorCode, isSession, retryAfterS } from './api.js';
import { byId, el, icon } from './dom.js';
import { app } from './state.js';

const NAME_KEY = 'tephra.desk.name';
const NAME_RULE = /^[\p{L}\p{N} .'_-]{2,32}$/u;
const MSG = {
  bad_pin: 'That PIN is not right. Check it and try again.',
  locked: (min) => `Too many attempts. Wait ${min} minute${min === 1 ? '' : 's'} and try again.`,
  disabled: 'The Desk is switched off on this server (no Desk PIN is set).',
  name: "Use 2 to 32 letters, digits, spaces or . ' - _",
  pin: 'Enter the Desk PIN.',
  offline: "You're offline. Reconnect to sign in.",
  ended: 'Your session has ended. Sign in again to decide.',
  visitorOff: 'Visitor access is switched off on this server.',
};
const VISITOR_LABEL = 'Enter as a visitor →';

let lockTimer = 0;
let lockUntil = 0;
let onSignedIn = () => {};
// The tab chosen while visitor access is on: null until the tabs first show, then the visitor's
// one tap unless this browser has signed in a dispatcher before.
let way = null;

const els = () => ({
  view: byId('login-view'),
  form: byId('login-form'),
  name: byId('login-name'),
  nameErr: byId('login-name-err'),
  pin: byId('login-pin'),
  pinErr: byId('login-pin-err'),
  submit: byId('login-submit'),
  formErr: byId('login-error'),
  disabled: byId('login-disabled'),
  pad: byId('pin-pad'),
  title: byId('login-title'),
  visitor: byId('visitor-card'),
  dispatcher: byId('dispatcher-card'),
  tabs: byId('login-tabs'),
  vform: byId('visitor-form'),
  vname: byId('visitor-name'),
  vnameErr: byId('visitor-name-err'),
  vsubmit: byId('visitor-submit'),
  vErr: byId('visitor-error'),
});

export function initLogin(signedIn) {
  onSignedIn = signedIn;
  const e = els();
  try {
    const saved = localStorage.getItem(NAME_KEY);
    if (saved) e.name.value = saved;
  } catch {
    // Storage can be blocked; the field simply starts empty.
  }
  e.form.addEventListener('submit', submit);
  e.vform.addEventListener('submit', enterAsVisitor);
  e.pin.addEventListener('input', () => setError('pin', ''));
  e.name.addEventListener('input', () => setError('name', ''));
  e.vname.addEventListener('input', () => setError('vname', ''));
  e.tabs.addEventListener('click', (event) => {
    const tab = event.target.closest('[data-way]');
    if (tab) chooseWay(tab.dataset.way, { focus: true });
  });
  e.tabs.addEventListener('keydown', (event) => {
    const keys = { ArrowLeft: 'visitor', ArrowRight: 'dispatcher', Home: 'visitor', End: 'dispatcher' };
    if (!keys[event.key]) return;
    event.preventDefault();
    chooseWay(keys[event.key]);
    byId(`tab-${way}`).focus();
  });
  const keys = ['1', '2', '3', '4', '5', '6', '7', '8', '9', 'clear', '0', 'back'];
  for (const key of keys) {
    const label = key === 'clear' ? 'Clear' : key === 'back' ? null : key;
    const button = el('button', {
      type: 'button',
      class: `pin-key ${key.length > 1 ? 'pin-key--fn' : ''}`.trim(),
      'aria-label': key === 'back' ? 'Delete last digit' : key === 'clear' ? 'Clear PIN' : null,
      'data-key': key,
    }, key === 'back' ? icon('i-chevron-left') : el('span', { text: label }));
    e.pad.append(button);
  }
  e.pad.addEventListener('click', (event) => {
    const key = event.target.closest('[data-key]');
    if (!key || key.disabled) return;
    const k = key.dataset.key;
    if (k === 'back') e.pin.value = e.pin.value.slice(0, -1);
    else if (k === 'clear') e.pin.value = '';
    else if (e.pin.value.length < 64) e.pin.value += k;
    setError('pin', '');
  });
}

function setError(which, text) {
  const e = els();
  const map = { name: [e.nameErr, e.name], pin: [e.pinErr, e.pin], form: [e.formErr, null], vname: [e.vnameErr, e.vname], vform: [e.vErr, null] };
  const [box, field] = map[which];
  box.replaceChildren(...(text ? [icon('st-serious', 'st'), el('span', { text })] : []));
  box.hidden = !text;
  if (field) field.setAttribute('aria-invalid', text ? 'true' : 'false');
}

export function showLogin(message = '', { disabled = false, info = false } = {}) {
  const e = els();
  e.view.hidden = false;
  e.disabled.hidden = !disabled;
  e.form.hidden = disabled;
  e.dispatcher.querySelector('.login__hint').hidden = disabled;
  setError('name', '');
  setError('pin', '');
  setError('form', '');
  setError('vname', '');
  setError('vform', '');
  if (message) {
    setError('form', message);
    e.formErr.classList.toggle('form-msg--info', info);
  }
  syncVisitorCard();
  if (disabled) return;
  focusWay();
}

function focusWay() {
  const e = els();
  if (!e.visitor.hidden) e.vsubmit.focus();
  else (e.name.value ? e.pin : e.name).focus();
}

export const hideLogin = () => {
  els().view.hidden = true;
};

// The tabs show only while the server says a visitor may enter (SystemState.visitor_access: the
// setting is on and a replay plays); desk.js calls this on every state arrival, so they follow a
// display switch. With the tabs, the title names the whole sign-in; without them, the PIN form
// is the only way in.
export function syncVisitorCard() {
  const e = els();
  const on = Boolean(app.state && app.state.visitor_access === true) && e.form.hidden === false;
  const appeared = on && e.tabs.hidden;
  e.tabs.hidden = !on;
  e.title.textContent = on ? 'Sign in to the Desk' : 'Dispatcher sign-in';
  if (!on) {
    e.visitor.hidden = true;
    e.dispatcher.hidden = false;
    e.dispatcher.setAttribute('aria-labelledby', 'login-title');
    return;
  }
  if (way === null) way = e.name.value ? 'dispatcher' : 'visitor';
  e.dispatcher.setAttribute('aria-labelledby', 'tab-dispatcher');
  chooseWay(way);
  // The state usually lands after the form took focus: the chosen way in becomes the first stop
  // when nothing has been typed yet.
  if (appeared && document.activeElement === e.name && !e.name.value) focusWay();
}

function chooseWay(which, { focus = false } = {}) {
  const e = els();
  way = which;
  for (const tab of e.tabs.querySelectorAll('[data-way]')) {
    const on = tab.dataset.way === which;
    tab.setAttribute('aria-selected', String(on));
    tab.tabIndex = on ? 0 : -1;
  }
  e.visitor.hidden = which !== 'visitor';
  e.dispatcher.hidden = which !== 'dispatcher';
  if (focus) focusWay();
}

async function enterAsVisitor(event) {
  event.preventDefault();
  const e = els();
  if (Date.now() < lockUntil) return;
  const name = e.vname.value.trim().replace(/\s+/g, ' ');
  setError('vform', '');
  if (name && !NAME_RULE.test(name)) {
    setError('vname', MSG.name);
    e.vname.focus();
    return;
  }
  e.vsubmit.disabled = true;
  e.vsubmit.replaceChildren(el('span', { class: 'spinner', 'aria-hidden': 'true' }), el('span', { text: 'Entering…' }));
  const res = await api(PATHS.visitor, { method: 'POST', body: { name: name || null } });
  e.vsubmit.disabled = false;
  e.vsubmit.replaceChildren(el('span', { text: VISITOR_LABEL }));
  if (res.ok && isSession(res.data)) {
    onSignedIn(res.data);
    return;
  }
  const code = errorCode(res);
  if (res.status === 0) setError('vform', MSG.offline);
  else if (code === 'visitor_off') setError('vform', MSG.visitorOff);
  else if (code === 'too_many_visitors') lock(retryAfterS(res) || 600, { visitor: true });
  else if (code === 'desk_disabled') showLogin('', { disabled: true });
  else if (res.status === 422) {
    setError('vname', MSG.name);
    e.vname.focus();
  } else setError('vform', (res.data && res.data.detail) || `Could not enter (HTTP ${res.status}).`);
}

async function submit(event) {
  event.preventDefault();
  const e = els();
  if (Date.now() < lockUntil) return;
  const name = e.name.value.trim().replace(/\s+/g, ' ');
  const pin = e.pin.value;
  setError('form', '');
  let bad = false;
  if (!NAME_RULE.test(name)) {
    setError('name', MSG.name);
    bad = true;
  }
  if (!pin) {
    setError('pin', MSG.pin);
    if (!bad) e.pin.focus();
    bad = true;
  }
  if (bad) {
    if (!NAME_RULE.test(name)) e.name.focus();
    return;
  }
  e.submit.disabled = true;
  e.submit.replaceChildren(el('span', { class: 'spinner', 'aria-hidden': 'true' }), el('span', { text: 'Signing in…' }));
  const res = await api(PATHS.login, { method: 'POST', body: { pin, name } });
  e.pin.value = '';
  e.submit.disabled = false;
  e.submit.replaceChildren(el('span', { text: 'Sign in' }));
  if (res.ok && isSession(res.data)) {
    try {
      localStorage.setItem(NAME_KEY, res.data.name);
    } catch {
      // Remembering the name is a convenience only.
    }
    onSignedIn(res.data);
    return;
  }
  const code = errorCode(res);
  if (res.status === 0) setError('form', MSG.offline);
  else if (code === 'bad_pin') {
    setError('pin', MSG.bad_pin);
    e.pin.focus();
  } else if (code === 'too_many_attempts') lock(retryAfterS(res) || 600);
  else if (code === 'desk_disabled') showLogin('', { disabled: true });
  else if (res.status === 422) {
    setError('name', MSG.name);
    e.name.focus();
  } else setError('form', (res.data && res.data.detail) || `Sign-in failed (HTTP ${res.status}).`);
}

// 429: the button that was used stays disabled and counts down from Retry-After; both ways in
// are locked, since the server counts the client, not the form.
function lock(seconds, { visitor = false } = {}) {
  const e = els();
  const button = visitor ? e.vsubmit : e.submit;
  const label = visitor ? VISITOR_LABEL : 'Sign in';
  lockUntil = Date.now() + seconds * 1000;
  setError(visitor ? 'vform' : 'form', MSG.locked(Math.max(1, Math.ceil(seconds / 60))));
  for (const key of e.pad.querySelectorAll('button')) key.disabled = true;
  e.pin.disabled = true;
  const tick = () => {
    const left = Math.ceil((lockUntil - Date.now()) / 1000);
    if (left <= 0) {
      window.clearInterval(lockTimer);
      lockUntil = 0;
      e.submit.disabled = false;
      e.vsubmit.disabled = false;
      e.pin.disabled = false;
      for (const key of e.pad.querySelectorAll('button')) key.disabled = false;
      button.replaceChildren(el('span', { text: label }));
      setError(visitor ? 'vform' : 'form', '');
      return;
    }
    e.submit.disabled = true;
    e.vsubmit.disabled = true;
    const m = Math.floor(left / 60);
    const s = String(left % 60).padStart(2, '0');
    button.replaceChildren(icon('i-lock'), el('span', { text: `Try again in ${m}:${s}` }));
  };
  window.clearInterval(lockTimer);
  lockTimer = window.setInterval(tick, 1000);
  tick();
}

export const SESSION_ENDED = MSG.ended;

// A deep link waiting for sign-in (UI-REDESIGN R10.3): "Sign in to review RFA1225." After sign-in
// desk.js resumes the hash; the hash never skips the session, the hold or the confirm step.
export function setPending(text) {
  const node = byId('login-pending');
  if (!node) return;
  node.textContent = text;
  node.hidden = !text;
}
