// Toasts (10.8): bottom, 6 s (a decision toast 15 s), role="status", kept while focused or hovered. A decision toast
// is the one-line receipt and "Next: …"; the audit line ("AUDIT APPROVED desk:AK 0632Z") and the SRC lines sit
// under "Technical detail".

import { byId, el, icon } from './dom.js';

const TTL_MS = 6000;
const MAX = 3;

const TONE_ICON = { ok: 'i-approved', rejected: 'i-rejected', caution: 'st-caution', info: 'i-info', replay: 'i-replay' };

// The audit entry and the SRC lines are machine text: they fold under "Technical detail" so the
// receipt is one plain line and the toast stays small (review 1, item 9).
function fillAudit(audit, lines, auditLine) {
  const box = audit.querySelector('.toast__audit');
  box.replaceChildren(
    ...(auditLine ? [el('span', { class: 'toast__auditline', text: auditLine })] : []),
    ...lines.map((line) => el('span', { class: 'toast__src', text: line })),
  );
  audit.hidden = !(lines.length || auditLine);
}

export function toast({ title, lines = [], auditLine = '', note = '', tone = 'info', ttl = TTL_MS }) {
  const host = byId('toasts');
  const audit = el('details', { class: 'toast__tech' }, el('summary', { text: 'Technical detail' }), el('p', { class: 'toast__audit' }));
  fillAudit(audit, lines, auditLine);
  const noteNode = el('p', { class: 'toast__note', text: note, hidden: !note });
  const close = el('button', { type: 'button', class: 'toast__close', 'aria-label': 'Dismiss' }, icon('i-x'));
  const node = el(
    'div',
    { class: `toast toast--${tone}`, role: 'status', tabindex: '-1' },
    el('p', { class: 'toast__title' }, icon(TONE_ICON[tone] || 'i-info'), el('span', { text: title })),
    noteNode,
    audit,
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
  // Closes the toast early, e.g. when the view it is about is left.
  node.dismiss = remove;
  return {
    node,
    dismiss: remove,
    setLines(next, nextAudit = '') {
      fillAudit(audit, next, nextAudit);
      arm();
    },
  };
}
