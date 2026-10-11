// Small shared pieces: the AI-written mark, the "AI unavailable" card, the bottom sheet.
// Every AI-written element carries its model id; code-written values stay plain. A failed AI
// step shows its reason and never a substitute (docs/EXTENSIONS.md rule 0).

import { byId, el, icon } from './dom.js';

// "AI-written · gemini-3.5-flash-lite", or the stub's honest "NO MODEL".
export function aiChip(modelId, backend, { verb = 'AI-written', sm = false } = {}) {
  const stub = backend === 'stub' || modelId === 'stub' || !modelId;
  const cls = `chip ${stub ? 'chip--stub' : 'chip--ai'}${sm ? ' chip--sm' : ''}`;
  if (stub) {
    return el('span', { class: cls, title: 'Written by the offline test stub: no model wrote this text' },
      icon('i-code', 'st'), el('span', { text: 'NO MODEL' }));
  }
  return el('span', { class: cls, title: `${verb} by ${modelId}. Checked by code before it is shown.` },
    icon('i-sparkle', 'st'), el('span', { text: `${verb} · ` }), el('span', { class: 'mono', text: String(modelId) }));
}

export const codeChip = (text = 'Code-written') =>
  el('span', { class: 'chip chip--code chip--sm', title: 'Computed by TEPHRA code from the feeds: no model wrote this' },
    icon('i-code', 'st'), el('span', { text }));

// The no-fallback card: the reason, and what the dispatcher does instead.
export function unavailableCard(reason, { instead = 'Nothing was substituted. Do this step by hand.', onRetry = null, title = 'AI unavailable' } = {}) {
  const card = el('div', { class: 'panel panel--serious unavail', role: 'alert' },
    el('p', { class: 'panel__title' }, icon('st-serious', 'st'), el('span', { text: `${title}: ${reason}` })),
    instead ? el('p', { class: 'unavail__instead', text: instead }) : null);
  if (onRetry) {
    card.append(el('button', { type: 'button', class: 'btn btn--outline', onclick: onRetry }, icon('i-refresh'), el('span', { text: 'Try again' })));
  }
  return card;
}

export function emptyPanel(title, text) {
  return el('div', { class: 'panel panel--empty' },
    el('p', { class: 'panel__title' }, icon('i-check', 'st'), el('span', { text: title })),
    text ? el('p', { text }) : null);
}

export function sectionHead(title, { count = null, sub = '', id = '', tone = '' } = {}) {
  return el('div', { class: `shead ${tone ? `shead--${tone}` : ''}`.trim() },
    el('h2', { class: 'shead__title', id: id || null, text: title }),
    count !== null && count !== undefined ? el('span', { class: 'shead__count', text: String(count) }) : null,
    sub ? el('p', { class: 'shead__sub', text: sub }) : null);
}

export function badge(n, label) {
  return el('span', { class: 'badge', 'aria-label': label || null, text: n > 99 ? '99+' : String(n) });
}

export const fmtUsd = (n) => (Number.isFinite(n) ? `$${Math.round(n).toLocaleString('en-US')}` : '–');

// --- bottom sheet ------------------------------------------------------------------------

let current = null;

// openSheet({ title, body, footer, wide }) -> { close, body, setFooter, setTitle }.
// A native <dialog>: focus is trapped, Escape closes, focus returns to the opener.
export function openBSheet({ title, body = null, footer = null, wide = false, onClose = null }) {
  const dlg = byId('bsheet');
  if (current) {
    current.dispose();
    if (dlg.open) dlg.close();
  }
  const titleNode = el('h2', { id: 'bsheet-title', class: 'bsheet__title', tabindex: '-1', text: title });
  const closeBtn = el('button', { type: 'button', class: 'iconbtn', 'aria-label': 'Close' }, icon('i-x'));
  const bodyNode = el('div', { class: 'bsheet__body' });
  const footNode = el('div', { class: 'bsheet__foot' });
  if (body) bodyNode.append(body);
  if (footer) footNode.append(footer);
  footNode.hidden = !footer;
  dlg.classList.toggle('bsheet--wide', wide);
  dlg.replaceChildren(el('div', { class: 'bsheet__head' }, titleNode, closeBtn), bodyNode, footNode);
  dlg.setAttribute('aria-labelledby', 'bsheet-title');
  const handle = {
    dispose: () => dispose(),
    body: bodyNode,
    close: () => {
      if (dlg.open) dlg.close();
    },
    setTitle: (text) => {
      titleNode.textContent = text;
    },
    setFooter: (node) => {
      footNode.replaceChildren(...(node ? [node] : []));
      footNode.hidden = !node;
    },
    setBody: (node) => {
      bodyNode.replaceChildren(node);
    },
  };
  const dispose = () => {
    dlg.removeEventListener('close', finish);
    dlg.removeEventListener('click', backdrop);
    if (current === handle) current = null;
    if (onClose) onClose();
  };
  const finish = () => {
    if (!dlg.open) dispose(); // a close event left over from the sheet this one replaced is ignored
  };
  const backdrop = (event) => {
    if (event.target === dlg) handle.close();
  };
  closeBtn.addEventListener('click', handle.close);
  dlg.addEventListener('close', finish);
  dlg.addEventListener('click', backdrop);
  current = handle;
  if (!dlg.open) dlg.showModal();
  bodyNode.scrollTop = 0;
  titleNode.focus({ preventScroll: true });
  return handle;
}

export const closeBSheet = () => {
  if (current) current.close();
};
