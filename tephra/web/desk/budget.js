// The Desk's one AI chip in the header (docs/UI-AI-QUIET.md K78, K79): the AI's state in words
// ("AI paused · 0700Z"), never red, from the same aiStateOf() as the Wall's AI chip and its AI
// at work board. It opens the "AI today" sheet: the calm lead, what went wrong by cause, the work
// waiting for budget, the calls per model and the way to AI at work on the Wall. GET /api/budget
// at start, then the `budget` SSE event after every model job.

import { PATHS, api } from './api.js';
import { byId, el, icon } from './dom.js';
import { dayMonthHhmm, hhmmz, parseTime, serverNow } from './format.js';
import { app } from './state.js';
import { aiState, openBSheet } from './ui.js';
import { aiLead, aiWords, causeTitle, machineText, realWhen } from '../wall/x-parts.js';

const LANE_WORDS = { urgent: 'flights in or near the ash', interactive: 'the Desk (questions, notices, messages, documents)', routine: 'routine work, paced through the day' };
const BOARD_URL = '/#ai-at-work';

// The Desk's AI state now: the live budget, the open AI failures, the newest Duty Officer run
// and airport plan, and the backend.
export function deskAi() {
  const failures = [...app.failures.values()].filter((f) => !f.handled_at && !f.closed_at);
  const plan = app.plans.find((p) => p.status !== 'SUPERSEDED') || null;
  return aiState({ budget: app.budget, failures, llm: app.state && app.state.llm, duty: app.duty, plan, replay: Boolean(app.state && app.state.mode === 'REPLAY') });
}

// A budget slot (real clock) in words after "next slot": "0700Z", or in REPLAY "in 2 h 45 min",
// which reads the same on either clock (the AI state's rule, wall/x-parts.js realWhen).
export const slotWords = (iso) => realWhen(parseTime(iso) ?? NaN, serverNow(), Boolean(app.state && app.state.mode === 'REPLAY'))?.at || null;

function valid(b) {
  return b && typeof b === 'object' && Array.isArray(b.tiers) && b.tiers.every((t) => t && Number.isFinite(t.used) && Number.isFinite(t.limit));
}

export async function loadBudget() {
  const res = await api(PATHS.budget);
  if (res.ok && valid(res.data)) setBudget(res.data);
}

export function setBudget(b) {
  if (!valid(b)) return;
  app.budget = b;
  drawAiChip();
}

const models = (b) => (Array.isArray(b.models) && b.models.length ? b.models : b.tiers);
const isOut = (m) => Boolean(m.closed) || m.limit <= 0 || m.remaining <= 0;
const plural = (n, word, many = `${word}s`) => `${n} ${n === 1 ? word : many}`;

// The chip: the one state; `model-chip` is its label span (re-parented in desk.html).
export function drawAiChip() {
  const chip = byId('budget-chip');
  const label = byId('model-chip');
  if (!chip || !label || !app.state) return;
  const ai = deskAi();
  const narrow = window.innerWidth <= 420;
  const w = aiWords(ai, { home: 'AI today', opens: 'AI today', narrow });
  chip.dataset.tone = w.tone;
  label.textContent = w.label;
  const kids = [icon(ai.kind === 'off' ? 'i-code' : 'i-model'), label];
  if (w.suffix) kids.push(el('span', { class: 'budget__w', text: `· ${w.suffix}` }));
  chip.replaceChildren(...kids);
  const jobs = ai.waiting.length ? ` ${plural(ai.waiting.length, 'job')} wait${ai.waiting.length === 1 ? 's' : ''}.` : '';
  chip.setAttribute('aria-label', w.aria.replace(/ Opens /, `${ai.kind === 'paused' ? jobs : ''} Opens `));
  chip.title = w.title;
  // Ask's paused note and other places that word the AI state redraw on this
  document.dispatchEvent(new CustomEvent('tephra:ai'));
}

// A model Google closed for today shows as closed, with a full bar, so its unused calls never read
// as calls to spare (D71, the Wall's "Closed for today by Google").
function modelRow(m, until) {
  const out = isOut(m);
  const pct = m.closed ? 100 : m.limit ? Math.min(100, Math.round((m.used / m.limit) * 100)) : 100;
  const bar = el('span', { class: `bbar bbar--${out ? 'out' : m.remaining / m.limit < 0.1 ? 'low' : 'ok'}`, 'aria-hidden': 'true' }, el('span', { class: 'bbar__fill' }));
  bar.firstElementChild.style.setProperty('--w', `${Math.max(pct, m.used ? 2 : 0)}%`);
  const status = m.closed
    ? `Closed for today by Google${until ? ` ${until}` : ''} (${m.remaining.toLocaleString('en')} of ${m.limit.toLocaleString('en')} unused)`
    : out ? 'Used up for today' : `${m.remaining.toLocaleString('en')} left today`;
  return el('li', { class: 'aimodel' },
    el('p', { class: 'aimodel__h' },
      el('span', { class: 'aimodel__jobs', text: m.jobs || m.tier }),
      el('span', { class: 'aimodel__n', text: m.closed ? 'Closed' : `${m.used.toLocaleString('en')} of ${m.limit.toLocaleString('en')} calls` })),
    bar,
    el('p', { class: `aimodel__status${out ? ' is-out' : ''}` }, icon(out ? 'st-caution' : 'st-ok', 'st'), el('span', { text: status })),
    el('p', { class: 'aimodel__id mono', text: m.model_id }));
}

function workRow(w) {
  const slot = slotWords(w.next_slot_at);
  const when = w.status === 'RUNNING' ? 'running now'
    : w.status === 'QUEUED' ? 'queued for the AI worker'
      : slot ? `waits for AI budget, next slot ${slot}` : 'waits for AI budget';
  return el('li', { class: 'aiwork' }, icon(w.status === 'RUNNING' ? 'i-play' : 'i-clock', 'st'),
    el('span', {}, el('span', { class: 'aiwork__label', text: w.label }), el('span', { class: 'aiwork__when', text: when })));
}

function lanes(b) {
  const rows = models(b).flatMap((m) => (m.lanes || []).filter((l) => l.share > 0 || l.used > 0).map((l) =>
    el('li', {}, el('span', { class: 'mono', text: m.model_id }), ` · ${LANE_WORDS[l.lane] || l.lane}: ${l.used} of ${l.share}`)));
  const pacing = models(b).filter((m) => m.pacing).map((m) => el('li', {}, el('span', { class: 'mono', text: m.model_id }), ` · ${m.pacing}`));
  if (!rows.length && !pacing.length) return null;
  return el('details', { class: 'more aisheet__more' },
    el('summary', {}, icon('i-chevron-right', 'icon disclosure'), el('span', { text: 'How the calls are shared' })),
    rows.length ? el('ul', { class: 'aisheet__lanes' }, rows) : null,
    pacing.length ? el('ul', { class: 'aisheet__lanes' }, pacing) : null);
}

// The "AI today" sheet, the Desk's AI home (K80): the calm lead first, then what went wrong by
// cause, the work waiting for budget, the calls per model (their ids, lanes and pacing) and the
// way to AI at work on the Wall.
export function openBudget() {
  const b = app.budget;
  const ai = deskAi();
  const stub = ai.kind === 'off';
  const work = b && Array.isArray(b.waiting) ? b.waiting : [];
  const lead = el('div', { class: `aisheet__lead aisheet__lead--${ai.kind}`, role: 'status' },
    ...aiLead(ai).map((p, i) => el('p', { class: i === 0 ? 'aisheet__head' : null }, el('strong', { text: p.strong }), ` ${p.text}`)));
  const causes = ai.causes.length
    ? el('section', { class: 'aisheet__sec', 'aria-labelledby': 'ai-causes-title' },
      el('h3', { id: 'ai-causes-title', class: 'aisheet__h', text: `What went wrong · ${plural(ai.causes.length, 'cause')}` }),
      el('ul', { class: 'aiworks' }, ...ai.causes.map((c) => el('li', { class: 'aiwork' }, icon('st-caution', 'st'),
        el('span', {}, el('span', { class: 'aiwork__label', text: causeTitle(c) }),
          el('span', { class: 'aiwork__when', text: [c.steps ? `${c.steps} ${c.steps === 1 ? 'time' : 'times'}` : null, Number.isFinite(c.first) ? `${hhmmz(c.first)}${c.last !== c.first ? `–${hhmmz(c.last)}` : ''}` : null, c.consequence].filter(Boolean).join(' · ') }))))),
      el('details', { class: 'tech' }, el('summary', { text: 'Technical detail' }), ...[...new Set(ai.causes.flatMap((c) => c.raw))].map((r) => el('p', { class: 'mono tech__line', text: machineText(r) }))))
    : null;
  const queue = work.length
    ? el('section', { class: 'aisheet__sec', 'aria-labelledby': 'ai-work-title' },
      el('h3', { id: 'ai-work-title', class: 'aisheet__h', text: `AI work waiting · ${work.length}` }),
      el('ul', { class: 'aiworks' }, work.map(workRow)),
      el('p', { class: 'note', text: 'Waiting work keeps its place and runs on the same model when its slot comes. Nothing is dropped or handed to another model.' }))
    : null;
  const calls = b && !stub
    ? el('section', { class: 'aisheet__sec', 'aria-labelledby': 'ai-calls-title' },
      el('h3', { id: 'ai-calls-title', class: 'aisheet__h', text: 'Calls today, per model' }),
      el('ul', { class: 'aimodels' }, models(b).map((m) => modelRow(m, ai.until))),
      lanes(b))
    : null;
  const board = el('a', { class: 'btn btn--outline btn--block aisheet__board', href: BOARD_URL, target: '_blank', rel: 'noopener' },
    icon('i-agent'), el('span', { text: 'See the AI at work on the Wall' }), icon('i-external-link'));
  const foot = stub
    ? el('p', { class: 'note', text: 'With no model, no AI calls are made or counted.' })
    : b
      ? el('p', { class: 'note', text: `${b.note}${b.resets_at ? ` Counts start again ${slotWords(b.resets_at) === hhmmz(b.resets_at) ? `at ${hhmmz(b.resets_at)}` : slotWords(b.resets_at)}.` : ''} As of ${dayMonthHhmm(b.as_of)}.` })
      : el('p', { class: 'note', text: "Today's AI calls have not loaded yet." });
  openBSheet({
    title: 'AI today',
    body: el('div', { class: 'stack aisheet' }, lead, causes, queue, calls, board, foot,
      el('p', { class: 'note', text: 'When a step runs out, it says AI unavailable and nothing is substituted.' })),
  });
}
