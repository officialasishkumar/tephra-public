// The right pane at 1100 px and up while no advisory and no flight list is open in it
// (docs/UI-DESIGN.md 10.16): instead of an empty box, what the Desk is waiting for and where the
// other work is. Built from what the Desk already holds; nothing is invented. The assistant line is the
// calm lead of the assistant sheet (wall/x-parts.js aiLead) in its main-view form: the state and
// what still holds, never why it is paused (that is in the sheet, docs/UI-AI-QUIET.md 8.6).

import { byId, el, icon } from './dom.js';
import { app, draftList } from './state.js';
import { deskAi } from './budget.js';
import { docsToSign } from './docs.js';
import { draftPlans } from './network.js';
import { openFailures } from './failures.js';
import { aiLead, aiSymbol } from '../wall/x-parts.js';

const plural = (n, word, many = `${word}s`) => `${n} ${n === 1 ? word : many}`;

function exposedLine() {
  const n = app.exposedIds ? app.exposedIds.size : null;
  if (n === null) return null;
  if (n === 0) return 'No RFA flight is in or heading into the ash.';
  return `${plural(n, 'RFA flight')} ${n === 1 ? 'is' : 'are'} in or heading into the ash. A draft comes here once TEPHRA Assistant has planned ${n === 1 ? 'it' : 'each one'}.`;
}

function elsewhere() {
  const out = [];
  const plans = draftPlans().length;
  const docs = docsToSign().length;
  if (plans) out.push(el('li', {}, el('button', { type: 'button', class: 'qlink__btn', 'data-goto': 'network' },
    icon('i-network', 'icon qlink__ic'), el('span', { class: 'qlink__t' }, el('strong', { text: 'Airports: ' }), el('span', { text: `${plural(plans, 'airport plan')} ${plans === 1 ? 'waits' : 'wait'} for a decision` })), icon('i-chevron-right', 'icon qlink__go'))));
  if (docs) out.push(el('li', {}, el('button', { type: 'button', class: 'qlink__btn', 'data-goto': 'docs' },
    icon('i-file', 'icon qlink__ic'), el('span', { class: 'qlink__t' }, el('strong', { text: 'Paperwork: ' }), el('span', { text: `${plural(docs, 'document')} to sign` })), icon('i-chevron-right', 'icon qlink__go'))));
  return out;
}

export function renderIdle() {
  const host = byId('idle-pane');
  if (!host) return;
  if (!app.me) {
    host.replaceChildren();
    return;
  }
  const loading = !app.listLoaded && !app.listError;
  const drafts = draftList().length;
  const hand = openFailures().length;
  const ai = deskAi();
  const lead = aiLead(ai, { home: false })[0];
  const title = loading ? 'Loading the drafts…' : drafts ? 'Choose an advisory to review' : hand ? `Plan by hand · ${plural(hand, 'flight')}` : 'Nothing waits for a decision';
  const sub = loading ? null : drafts ? `${plural(drafts, 'advisory', 'advisories')} ${drafts === 1 ? 'waits' : 'wait'} on the left in act-by order: the one to decide first is at the top.` : hand ? 'TEPHRA Assistant made no plan for them. They are listed under Decide.' : exposedLine();
  const other = elsewhere();
  host.replaceChildren(
    el('div', { class: 'idle__box' },
      icon(loading ? 'i-clock' : drafts ? 'i-list' : hand ? 'st-caution' : 'i-check', 'icon idle__icon'),
      el('h2', { id: 'idle-title', class: 'idle__title', text: title }),
      sub ? el('p', { class: 'idle__lead', text: sub }) : null,
      !loading && !drafts && hand ? el('button', { type: 'button', class: 'btn btn--outline', 'data-failpane': 'open' }, el('span', { text: 'Show the flights' }), icon('i-chevron-right')) : null,
      el('p', { class: `idle__ai idle__ai--${ai.kind}` }, icon(aiSymbol(ai.kind), 'st'),
        el('span', {}, el('strong', { text: lead.strong }), ` ${lead.text}`)),
      other.length ? el('h3', { class: 'idle__h', text: 'Also waiting for you' }) : null,
      other.length ? el('ul', { class: 'idle__list' }, other) : null,
      el('a', { class: 'linkbtn idle__board', href: '/#ai-at-work', target: '_blank', rel: 'noopener' }, icon('ta-16'), el('span', { text: 'See TEPHRA Assistant at work on the Wall' }), icon('i-external-link'))));
}
