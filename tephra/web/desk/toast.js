// Toasts (10.8): bottom, 6 s (a decision toast 15 s), role="status", kept while focused or hovered. A decision toast
// carries the audit line ("AUDIT APPROVED desk:AK 0632Z") first, then the SRC lines.

import { byId, el, icon } from './dom.js';

const TTL_MS = 6000;
const MAX = 3;

const TONE_ICON = { ok: 'i-approved', rejected: 'i-rejected', caution: 'st-caution', info: 'i-info', replay: 'i-replay' };

function fillAudit(audit, lines, auditLine) {
  audit.replaceChildren(
    ...(auditLine ? [el('span', { class: 'toast__auditline', text: auditLine })] : []),
    ...lines.map((line) => el('span', { class: 'toast__src', text: line })),
  );
}

export function toast({ title, lines = [], auditLine = '', tone = 'info', ttl = TTL_MS }) {
  const host = byId('toasts');
  const audit = el('p', { class: 'toast__audit' });
  fillAudit(audit, lines, auditLine);
  const close = el('button', { type: 'button', class: 'toast__close', 'aria-label': 'Dismiss' }, icon('i-x'));
  const node = el(
    'div',
    { class: `toast toast--${tone}`, role: 'status', tabindex: '-1' },
    el('p', { class: 'toast__title' }, icon(TONE_ICON[tone] || 'i-info'), el('span', { text: title })),
    lines.length || auditLine ? audit : null,
    close,
  );
  let timer = 0;
  const remove = () => {
    window.clearTimeout(timer);
    node.classList.add('is-leaving');
    window.setTimeout(() => node.remove(), 240);
  };
  const arm = () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      // Touch screens keep :hover on the last tap point, so only a real hover holds the toast.
      const hovered = window.matchMedia('(hover: hover)').matches && node.matches(':hover');
      if (hovered || node.contains(document.activeElement)) arm();
      else remove();
    }, ttl);
  };
  close.addEventListener('click', remove);
  node.addEventListener('focusout', arm);
  node.addEventListener('mouseleave', arm);
  host.append(node);
  while (host.children.length > MAX) host.firstElementChild.remove();
  arm();
  // The audit lines may arrive after the toast is shown.
  return {
    node,
    setLines(next, nextAudit = '') {
      fillAudit(audit, next, nextAudit);
      if (!audit.isConnected) node.insertBefore(audit, close);
      arm();
    },
  };
}
