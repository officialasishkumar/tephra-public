// The tab bar (UI-REDESIGN R10.2): Decide / Ask / Airports / Paperwork, each an icon and a word
// with a count badge. The data-tab keys (queue, ask, network, docs) and the sessionStorage key are
// unchanged; only the labels changed. One panel is shown at a time.

import { byId, el, icon } from './dom.js';
import { app } from './state.js';

export const TABS = ['queue', 'ask', 'network', 'docs'];
const LABEL = { queue: 'Decide', ask: 'Ask', network: 'Airports', docs: 'Paperwork' };
const WAITING = { queue: 'waiting', network: 'plan waiting', docs: 'to sign' };
const ICON = { queue: 'i-inbox', ask: 'i-chat', network: 'i-network', docs: 'i-file' };
const KEY = 'tephra.desk.tab';

let onChange = () => {};

export function initTabs(handler) {
  onChange = handler;
  const bar = byId('tabbar');
  bar.replaceChildren(...TABS.map((name) =>
    el('button', { type: 'button', class: 'tab', 'data-tab': name, 'aria-controls': name === 'queue' ? 'desk-view' : `panel-${name}` },
      el('span', { class: 'tab__ic' }, icon(ICON[name]), el('span', { class: 'tab__badge', 'data-badge': name, hidden: true })),
      el('span', { class: 'tab__l', text: LABEL[name] }))));
  bar.addEventListener('click', (event) => {
    const b = event.target.closest('.tab');
    if (b) goTab(b.dataset.tab, { focus: true });
  });
  bar.addEventListener('keydown', (event) => {
    const dir = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
    if (!dir) return;
    const i = TABS.indexOf(app.tab);
    const next = TABS[(i + dir + TABS.length) % TABS.length];
    event.preventDefault();
    goTab(next, { focus: true });
    bar.querySelector(`[data-tab="${next}"]`).focus();
  });
  let saved = 'queue';
  try {
    saved = window.sessionStorage.getItem(KEY) || 'queue';
  } catch {
    saved = 'queue';
  }
  goTab(TABS.includes(saved) ? saved : 'queue', { focus: false, quiet: true });
}

export function goTab(name, { focus = false, quiet = false } = {}) {
  if (!TABS.includes(name)) return;
  const changed = app.tab !== name;
  app.tab = name;
  document.body.dataset.tab = name;
  for (const b of byId('tabbar').children) {
    if (b.dataset.tab === name) b.setAttribute('aria-current', 'page');
    else b.removeAttribute('aria-current');
  }
  for (const t of TABS) {
    if (t === 'queue') continue;
    const panel = byId(`panel-${t}`);
    if (panel) panel.hidden = t !== name;
  }
  try {
    window.sessionStorage.setItem(KEY, name);
  } catch {
    // The tab is simply not remembered.
  }
  if (!quiet) window.scrollTo({ top: 0 });
  onChange(name, { changed, focus });
}

// `detail` names what a badge counts (R2.7): "Decide, 28 waiting: 23 advisories · 3 messages · …".
export function setBadges(counts, detail = {}) {
  for (const name of TABS) {
    const node = byId('tabbar').querySelector(`[data-badge="${name}"]`);
    if (!node) continue;
    const n = counts[name] || 0;
    node.hidden = n === 0;
    node.textContent = n > 99 ? '99+' : String(n);
    const tab = node.closest('.tab');
    const what = detail[name] ? `: ${detail[name]}` : '';
    tab.setAttribute('aria-label', n ? `${LABEL[name]}, ${n} ${WAITING[name] || 'waiting'}${what}` : LABEL[name]);
    tab.title = n && detail[name] ? detail[name] : '';
  }
}
