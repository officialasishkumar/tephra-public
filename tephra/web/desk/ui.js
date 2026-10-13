// Small shared pieces: the assistant mark, the AI state, the "gave no result" card, the bottom
// sheet. TEPHRA Assistant's health has one home on the Desk, the header chip and its assistant
// sheet; elsewhere a step that did not run says what to do, in caution tone, and never shows a
// substitute (docs/UI-AI-QUIET.md and its Naming amendment, docs/EXTENSIONS.md rule 0).

import { byId, el, icon } from './dom.js';
import { serverNow } from './format.js';
import { aiStateOf, machineText, MARK } from '../wall/x-parts.js';

// The one mark set (UI-AI-QUIET Q5, Naming): the Strata mark and the visible words only
// ("Drafted by TEPHRA Assistant", "Read by Notice reader", "Answered by TEPHRA Assistant"), the
// model id in the title and the label; "Code only (assistant off)" when no model wrote it. Only
// for content a model produced and the code's checks passed.
export function aiMark(verb = MARK.written, modelId = null, { backend = null } = {}) {
  const stub = backend === 'stub' || !modelId || modelId === 'stub' || modelId === 'none';
  if (stub) {
    return el('span', { class: 'ai-mark ai-mark--none', title: 'NO MODEL: code templates wrote this text, not a model', 'aria-label': MARK.none },
      icon('i-code', 'st'), el('span', { 'aria-hidden': 'true', text: MARK.none }));
  }
  return el('span', { class: 'ai-mark', title: `${verb} (${modelId}). Checked by code before it is shown.`, 'aria-label': `${verb} (${modelId})` },
    icon('ta-16', 'st'), el('span', { 'aria-hidden': 'true', text: verb }));
}

// The Desk's one AI state (UI-AI-QUIET 1.2), with the Wall's rules: the live budget, the open
// assistant failures (one cause however many flights), the newest Coordinator run and airport plan.
export function aiState({ budget = null, failures = [], llm = null, duty = null, plan = null, replay = false } = {}) {
  const errors = failures.map((f) => ({ stage: f.stage, reason: f.reason, at: Date.parse(f.created_at || ''), raw: `${f.reason}${f.model_id ? ` · would have used ${f.model_id}` : ''}` }));
  const stub = (llm && llm.backend === 'stub') || (budget && budget.backend === 'stub');
  return aiStateOf({ stub, budget, errors, duty, plan, replay, now: serverNow() });
}

export const codeChip = (text = 'Code-written') =>
  el('span', { class: 'chip chip--code chip--sm', title: 'Computed by TEPHRA code from the feeds: no model wrote this' },
    icon('i-code', 'st'), el('span', { text }));

// The no-fallback card: what did not run and what the dispatcher does instead. An assistant step is a
// caution (role=status) with its raw reason under Technical detail; a connection or session
// failure (`serious`) keeps the red, role=alert and its reason in the title (UI-AI-QUIET Q4).
export function unavailableCard(reason, { instead = 'Nothing was put in its place. Do this step by hand.', onRetry = null, retryLabel = 'Try again', retryDisabled = false, title = 'No result from TEPHRA Assistant', serious = false } = {}) {
  const card = serious
    ? el('div', { class: 'panel panel--serious unavail', role: 'alert' },
      el('p', { class: 'panel__title' }, icon('st-serious', 'st'), el('span', { text: `${title}: ${machineText(reason)}` })),
      instead ? el('p', { class: 'unavail__instead', text: instead }) : null)
    : el('div', { class: 'panel panel--caution unavail', role: 'status' },
      el('p', { class: 'panel__title' }, icon('st-caution', 'st'), el('span', { text: title })),
      instead ? el('p', { class: 'unavail__instead', text: instead }) : null,
      reason ? el('details', { class: 'tech' }, el('summary', { text: 'Technical detail' }), el('p', { class: 'mono tech__line', text: machineText(reason) })) : null);
  if (onRetry) {
    card.append(el('button', { type: 'button', class: 'btn btn--outline', onclick: onRetry, disabled: retryDisabled }, icon('i-refresh'), el('span', { text: retryLabel })));
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
