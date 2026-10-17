// Account menu (10.1, 10.9, 10.10): who is signed in and until when, the display mode switch
// (POST /api/mode; never on the queue), the optional screen wake lock, Airlines to verify and Data
// connections (SPEC-v2 7.8), and sign out. A visitor (SPEC 5.1) sees who they are and when the
// session ends, never the display switch, the airlines or the connections: the server refuses
// them (403 visitor_role). Below 600 px, where the shared nav is folded away, the menu lists the
// other pages.

import { PATHS, api, errorCode } from './api.js';
import { byId, el, icon } from './dom.js';
import { dayMonthHhmm, hhmmz, initials, sessionLabel } from './format.js';
import { app } from './state.js';
import { toast } from './toast.js';
import { describeReplayIn } from './ui.js';
import { has } from '../wall/features.js';
import { airlinesWaiting, openAirlines } from './airlines.js';
import { openConnections } from './connections.js';
import { TENANT } from '../base.js';

const PAGES_BELOW_PX = 600; // desk.css hides .topnav under this width

const WAKE_KEY = 'tephra.desk.wake';
export const wakeSupported = () => 'wakeLock' in navigator;

export function initAccount({ onSignOut, onWakeChange }) {
  // a hosted airline's Desk: the airline header's account menu takes this one's place
  if (TENANT) return;
  const button = byId('account-btn');
  const menu = byId('account-menu');
  try {
    app.wakeWanted = localStorage.getItem(WAKE_KEY) !== 'off';
  } catch {
    app.wakeWanted = true;
  }
  const close = (focus = false) => {
    menu.hidden = true;
    button.setAttribute('aria-expanded', 'false');
    if (focus) button.focus();
  };
  button.addEventListener('click', () => {
    const open = menu.hidden;
    if (open) {
      renderMenu();
      menu.hidden = false;
      button.setAttribute('aria-expanded', 'true');
      const first = menu.querySelector('button, input');
      if (first) first.focus();
    } else close();
  });
  menu.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') close(true);
  });
  document.addEventListener('click', (event) => {
    if (!menu.hidden && !menu.contains(event.target) && !button.contains(event.target)) close();
  });
  menu.addEventListener('click', (event) => {
    const t = event.target.closest('[data-menu]');
    if (!t) return;
    if (t.dataset.menu === 'signout') {
      close();
      onSignOut();
    } else if (t.dataset.menu === 'display') {
      close();
      openDisplayDialog();
    } else if (t.dataset.menu === 'airlines') {
      close();
      openAirlines();
    } else if (t.dataset.menu === 'connections') {
      close();
      openConnections();
    }
  });
  menu.addEventListener('change', (event) => {
    if (event.target.id !== 'wake-toggle') return;
    app.wakeWanted = event.target.checked;
    try {
      localStorage.setItem(WAKE_KEY, app.wakeWanted ? 'on' : 'off');
    } catch {
      // Not remembered; the choice still holds for this page.
    }
    onWakeChange();
  });
  byId('display-dialog').addEventListener('close', () => {
    byId('display-dialog').replaceChildren();
    button.focus();
  });
}

export function setAccount(session) {
  if (TENANT) return;
  const button = byId('account-btn');
  if (!session) {
    button.hidden = true;
    byId('account-menu').hidden = true;
    return;
  }
  button.hidden = false;
  button.textContent = initials(session.name);
  button.setAttribute('aria-label', `Signed in as ${sessionLabel(session)}. Account${session.role === 'visitor' ? '' : ' and display'} menu`);
}

function displayWords() {
  const s = app.state;
  if (!s) return 'Display: –';
  if (s.mode === 'REPLAY' && s.replay) return `Display: REPLAY · ${s.replay.label}`;
  return 'Display: LIVE · live feeds';
}

function renderMenu() {
  const menu = byId('account-menu');
  const me = app.me;
  const visitor = Boolean(me && me.role === 'visitor');
  const items = [
    el('div', { class: 'menu__block' },
      el('p', { class: 'menu__strong', text: `Signed in as ${me ? sessionLabel(me) : '–'}` }),
      el('p', { class: 'menu__fine', text: me ? `Session ends ${hhmmz(me.expires_at)}` : '' })),
  ];
  if (!visitor) {
    items.push(el('div', { class: 'menu__block' },
      el('p', { class: 'menu__strong', text: displayWords() }),
      el('p', { class: 'menu__fine', text: 'Changes what the demo and every Desk show.' }),
      el('button', { type: 'button', class: 'menu__item', 'data-menu': 'display' }, icon('i-replay'), el('span', { text: 'Change display…' }))));
  }
  if (wakeSupported()) {
    items.push(el('label', { class: 'menu__check' },
      el('input', { type: 'checkbox', id: 'wake-toggle', checked: app.wakeWanted }),
      el('span', { text: 'Keep the screen on while drafts wait' })));
  }
  if (window.innerWidth < PAGES_BELOW_PX) {
    items.push(el('div', { class: 'menu__block menu__pages' },
      el('p', { class: 'menu__fine', text: 'Pages' }),
      el('a', { class: 'menu__item', href: '/demo' }, icon('i-external-link'), el('span', { text: 'Demo' })),
      el('a', { class: 'menu__item', href: '/guide' }, icon('i-help'), el('span', { text: 'Guide' }))));
  }
  if (has('onboard') && !visitor) {
    const count = el('span', { class: 'menu__count' });
    items.push(el('button', { type: 'button', class: 'menu__item', 'data-menu': 'airlines' }, icon('i-inbox'), el('span', { text: 'Airlines to verify' }), count));
    airlinesWaiting().then((n) => {
      if (n != null) count.textContent = ` · ${n}`;
    });
  }
  if (has('connect') && !visitor) items.push(el('button', { type: 'button', class: 'menu__item', 'data-menu': 'connections' }, icon('i-network'), el('span', { text: 'Data connections' })));
  items.push(el('button', { type: 'button', class: 'menu__item', 'data-menu': 'signout' }, icon('i-log-out'), el('span', { text: 'Sign out' })));
  menu.replaceChildren(...items);
}

// --- display mode -----------------------------------------------------------------------

async function openDisplayDialog() {
  const dialog = byId('display-dialog');
  const body = el('div', { class: 'dlg__body' }, el('p', { class: 'note', text: 'Loading recordings…' }));
  dialog.replaceChildren(
    el('div', { class: 'dlg__head' },
      el('h2', { id: 'display-title', class: 'dlg__title', text: 'Change display' }),
      el('button', { type: 'button', class: 'iconbtn', 'aria-label': 'Close', onclick: () => dialog.close() }, icon('i-x'))),
    body,
  );
  dialog.setAttribute('aria-labelledby', 'display-title');
  describeReplayIn(dialog);
  dialog.showModal();
  const res = await api(PATHS.replays);
  if (!dialog.open) return;
  const cases = res.ok && res.data && Array.isArray(res.data.cases) ? res.data.cases : [];
  const current = app.state && app.state.mode === 'REPLAY' && app.state.replay ? app.state.replay.case_id : null;
  const options = [
    { mode: 'LIVE', id: null, title: 'Live feeds', detail: 'Public feeds as they arrive.', on: app.state && app.state.mode === 'LIVE' },
    ...cases.map((c) => ({
      mode: 'REPLAY',
      id: c.case_id,
      title: String(c.label || c.case_id),
      detail: `${dayMonthHhmm(c.recorded_from)} → ${dayMonthHhmm(c.recorded_to)} · ${c.record_count} records`,
      on: c.case_id === current,
    })),
  ];
  body.replaceChildren(
    el('p', { class: 'note', text: 'Switches what every screen shows.' }),
    el('ul', { class: 'choices' }, options.map((o) =>
      el('li', {}, el('button', { type: 'button', class: `choice ${o.on ? 'is-current' : ''}`.trim(), 'aria-current': o.on ? 'true' : null,
        onclick: () => confirmSwitch(o, body) },
      icon(o.mode === 'LIVE' ? 'i-live' : 'i-replay'),
      el('span', { class: 'choice__text' }, el('span', { class: 'choice__title', text: o.title }), el('span', { class: 'choice__detail', text: o.detail })),
      o.on ? el('span', { class: 'choice__now', text: 'Showing now' }) : null)))),
    // replaceChildren would print a null slot as "null".
    ...(res.ok ? [] : [el('p', { class: 'msg msg--serious' }, icon('st-serious', 'st'), el('span', { text: "Can't load the recordings." }))]),
  );
}

function confirmSwitch(option, body) {
  const live = option.mode === 'LIVE';
  const question = live
    ? 'Switch every screen to live feeds? The switch is recorded in the audit log under your name.'
    : `Switch every screen to REPLAY of ${option.title}? The switch is recorded in the audit log under your name.`;
  const error = el('p', { class: 'msg msg--serious', hidden: true });
  const go = el('button', { type: 'button', class: 'btn btn--neutral' }, el('span', { text: live ? 'Switch to live feeds' : 'Switch to replay' }));
  const cancel = el('button', { type: 'button', class: 'btn btn--outline', text: 'Cancel', onclick: () => byId('display-dialog').close() });
  const goWords = go.firstChild.textContent;
  go.addEventListener('click', async () => {
    go.disabled = true;
    cancel.disabled = true;
    go.firstChild.textContent = 'Switching…';
    const res = await api(PATHS.mode, { method: 'POST', body: live ? { mode: 'LIVE' } : { mode: 'REPLAY', case_id: option.id } });
    go.disabled = false;
    cancel.disabled = false;
    go.firstChild.textContent = goWords;
    if (res.ok) {
      app.hub.applyState(res.data);
      byId('display-dialog').close();
      toast({ tone: live ? 'info' : 'replay', title: `Display switched to ${live ? 'LIVE' : 'REPLAY'} by ${app.me ? app.me.name : 'you'}.` });
      return;
    }
    const code = errorCode(res);
    const text = res.status === 404 ? 'That recording is not on this server.'
      : code === 'invalid_transition' ? 'No recording is available.'
        : res.status === 0 ? "You're offline. Reconnect to switch the display."
          : res.status === 401 ? 'Your session has ended. Sign in again to decide.'
            : `Not switched (HTTP ${res.status}).`;
    error.replaceChildren(icon('st-serious', 'st'), el('span', { text }));
    error.hidden = false;
  });
  body.replaceChildren(el('p', { class: 'confirm__q', text: question }), error, el('div', { class: 'secondary' }, go, cancel));
  go.focus();
}
