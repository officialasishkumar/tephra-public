// The right pane at 1100 px and up while no advisory and no flight list is open in it
// (docs/UI-DESIGN.md 10.16): instead of an empty box, what the Desk is waiting for and where the
// other work is. Built from what the Desk already holds; nothing is invented. The AI state is not
// said here: the header's status says it once for the whole Desk (owner, 17 Oct).

import { byId, el, icon } from './dom.js';
import { app, draftList } from './state.js';
import { docsToSign } from './docs.js';
import { draftPlans } from './network.js';
import { openFailures } from './failures.js';
import { TENANT } from '../base.js';

const plural = (n, word, many = `${word}s`) => `${n} ${n === 1 ? word : many}`;

function exposedLine() {
  const n = app.exposedIds ? app.exposedIds.size : null;
  if (n === null) return null;
  // an airline's own TEPHRA names its own airline (state.airline); the demo's is RFA
  const code = app.state?.airline?.code || 'RFA';
  if (n === 0) return `No ${code} flight is in or heading into the ash.`;
  return `${plural(n, `${code} flight`)} ${n === 1 ? 'is' : 'are'} in or heading into the ash. A draft comes here once TEPHRA Assistant has planned ${n === 1 ? 'it' : 'each one'}.`;
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
  const title = loading ? 'Loading the drafts…' : drafts ? 'Choose an advisory to review' : hand ? `Plan by hand · ${plural(hand, 'flight')}` : 'Nothing waits for a decision';
  const sub = loading ? null : drafts ? `${plural(drafts, 'advisory', 'advisories')} ${drafts === 1 ? 'waits' : 'wait'} on the left in act-by order: the one to decide first is at the top.` : hand ? 'TEPHRA Assistant made no plan for them. They are listed under Decide.' : exposedLine();
  const other = elsewhere();
  host.replaceChildren(
    el('div', { class: 'idle__box' },
      icon(loading ? 'i-clock' : drafts ? 'i-list' : hand ? 'st-caution' : 'i-check', 'icon idle__icon'),
      el('h2', { id: 'idle-title', class: 'idle__title', text: title }),
      sub ? el('p', { class: 'idle__lead', text: sub }) : null,
      !loading && !drafts && hand ? el('button', { type: 'button', class: 'btn btn--outline', 'data-failpane': 'open' }, el('span', { text: 'Show the flights' }), icon('i-chevron-right')) : null,
      other.length ? el('h3', { class: 'idle__h', text: 'Also waiting for you' }) : null,
      other.length ? el('ul', { class: 'idle__list' }, other) : null,
      TENANT ? null : el('a', { class: 'linkbtn idle__board', href: '/assistant', target: '_blank', rel: 'noopener' }, icon('ta-16'), el('span', { text: 'See TEPHRA Assistant at work' }), icon('i-external-link'))));
}
