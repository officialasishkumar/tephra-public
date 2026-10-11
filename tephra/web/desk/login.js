// Sign-in (docs/UI-DESIGN.md 10.2): name, PIN with an on-screen PIN pad, and the states
// wrong PIN, too many attempts (429 + Retry-After countdown), Desk switched off (503),
// invalid name (422) and offline.

import { PATHS, api, errorCode, isSession, retryAfterS } from './api.js';
import { byId, el, icon } from './dom.js';

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
};

let lockTimer = 0;
let lockUntil = 0;
let onSignedIn = () => {};

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
  e.pin.addEventListener('input', () => setError('pin', ''));
  e.name.addEventListener('input', () => setError('name', ''));
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
  const map = { name: [e.nameErr, e.name], pin: [e.pinErr, e.pin], form: [e.formErr, null] };
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
  setError('name', '');
  setError('pin', '');
  setError('form', '');
  if (message) {
    setError('form', message);
    e.formErr.classList.toggle('form-msg--info', info);
  }
  if (!disabled) (e.name.value ? e.pin : e.name).focus();
}

export const hideLogin = () => {
  els().view.hidden = true;
};

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

// 429: the button stays disabled and counts down from Retry-After.
function lock(seconds) {
  const e = els();
  lockUntil = Date.now() + seconds * 1000;
  setError('form', MSG.locked(Math.max(1, Math.ceil(seconds / 60))));
  for (const key of e.pad.querySelectorAll('button')) key.disabled = true;
  e.pin.disabled = true;
  const tick = () => {
    const left = Math.ceil((lockUntil - Date.now()) / 1000);
    if (left <= 0) {
      window.clearInterval(lockTimer);
      lockUntil = 0;
      e.submit.disabled = false;
      e.pin.disabled = false;
      for (const key of e.pad.querySelectorAll('button')) key.disabled = false;
      e.submit.replaceChildren(el('span', { text: 'Sign in' }));
      setError('form', '');
      return;
    }
    e.submit.disabled = true;
    const m = Math.floor(left / 60);
    const s = String(left % 60).padStart(2, '0');
    e.submit.replaceChildren(icon('i-lock'), el('span', { text: `Try again in ${m}:${s}` }));
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
