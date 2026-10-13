// The tab bar (UI-REDESIGN R10.2, Desk redesign D5 and 11, UI-DESIGN 10.18): Decide · Airports ·
// Paperwork, a real tablist (role=tab, aria-selected, aria-controls; the panels are tabpanels). The
// data-tab keys (queue, network, docs) and the sessionStorage key are unchanged. Ask is not a tab:
// it is a drawer the header's Ask button opens over any tab (desk.js openAsk). Only Decide has a badge: Decide is the inbox and
// its one count (waitingCount in desk.js) is the h1, the badge and the page title alike.

import { byId, el, icon } from './dom.js';
import { app } from './state.js';

export const TABS = ['queue', 'network', 'docs'];
const LABEL = { queue: 'Decide', network: 'Airports', docs: 'Paperwork' };
const ICON = { queue: 'i-inbox', network: 'i-network', docs: 'i-file' };
const PANEL = (name) => (name === 'queue' ? 'desk-view' : `panel-${name}`);
const KEY = 'tephra.desk.tab';

let onChange = () => {};

export function initTabs(handler) {
  onChange = handler;
  const bar = byId('tabbar');
  bar.setAttribute('role', 'tablist');
  bar.setAttribute('aria-label', 'Desk sections');
  bar.replaceChildren(...TABS.map((name) =>
    el('button', { type: 'button', role: 'tab', id: `tab-${name}`, class: 'tab', 'data-tab': name, 'aria-controls': PANEL(name), 'aria-selected': 'false', tabindex: '-1' },
      el('span', { class: 'tab__ic' }, icon(ICON[name]), name === 'queue' ? el('span', { class: 'tab__badge', 'data-badge': name, 'aria-hidden': 'true', hidden: true }) : null),
      el('span', { class: 'tab__l', text: LABEL[name] }))));
  for (const name of TABS) {
    const panel = byId(PANEL(name));
    if (!panel) continue;
    panel.setAttribute('role', 'tabpanel');
    panel.setAttribute('aria-labelledby', `tab-${name}`);
  }
  bar.addEventListener('click', (event) => {
    const b = event.target.closest('.tab');
    if (b) goTab(b.dataset.tab, { focus: true });
  });
  bar.addEventListener('keydown', (event) => {
    const keys = { ArrowRight: 1, ArrowLeft: -1, Home: 'first', End: 'last' };
    const dir = keys[event.key];
    if (!dir) return;
    const i = TABS.indexOf(app.tab);
    const next = dir === 'first' ? TABS[0] : dir === 'last' ? TABS[TABS.length - 1] : TABS[(i + dir + TABS.length) % TABS.length];
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
    const on = b.dataset.tab === name;
    b.setAttribute('aria-selected', String(on));
    b.tabIndex = on ? 0 : -1;
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

// The one waiting count on Decide's tab; `detail` names what it counts ("21 advisories · 2
// flights to plan by hand · 1 airport plan").
export function setBadges(counts, detail = {}) {
  const node = byId('tabbar').querySelector('[data-badge="queue"]');
  if (!node) return;
  const n = counts.queue || 0;
  node.hidden = n === 0;
  node.textContent = n > 99 ? '99+' : String(n);
  const tab = node.closest('.tab');
  tab.setAttribute('aria-label', n ? `${LABEL.queue}, ${n} waiting${detail.queue ? `: ${detail.queue}` : ''}` : LABEL.queue);
  tab.title = n && detail.queue ? detail.queue : '';
}
