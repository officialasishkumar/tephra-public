// The Desk's one assistant chip in the header (docs/UI-AI-QUIET.md K78, K79, Naming): TEPHRA
// Assistant's state in words ("TEPHRA Assistant · paused"), never red, from the same
// aiStateOf() as the Wall's chip and its "TEPHRA Assistant at work" board. It opens the assistant
// sheet: the calm lead, what went wrong by cause, the work waiting for its slot, the calls per
// model and the way to the board on the Wall. GET /api/budget at start, then the `budget` SSE
// event after every model job.

import { PATHS, api } from './api.js';
import { byId, el, icon } from './dom.js';
import { dayMonthHhmm, hhmmz, parseTime, serverNow } from './format.js';
import { app } from './state.js';
import { aiState, openBSheet } from './ui.js';
import { infoButton } from '../wall/info.js';
import { aiLead, aiWords, causeTitle, jobsWords, pacingWords, machineText, realWhen, stateLine, ASSISTANT } from '../wall/x-parts.js';
import { TENANT, PAGE_BASE } from '../base.js';

const LANE_WORDS = { urgent: 'flights in or near the ash', interactive: 'the Desk (questions, notices, messages, documents)', routine: 'routine work, paced through the day' };
const BOARD_URL = '/assistant';

// The Desk's AI state now: the live budget, the open assistant failures, the newest Coordinator run
// and airport plan, and the backend.
export function deskAi() {
  const failures = [...app.failures.values()].filter((f) => !f.handled_at && !f.closed_at);
  const plan = app.plans.find((p) => p.status !== 'SUPERSEDED') || null;
  return aiState({ budget: app.budget, failures, llm: app.state && app.state.llm, duty: app.duty, plan, replay: Boolean(app.state && app.state.mode === 'REPLAY') });
}

// A budget slot (real clock) in words after "next slot": "0700Z", or in REPLAY "in 2 h 45 min",
// which reads the same on either clock (the AI state's rule, wall/x-parts.js realWhen).
const slotWords = (iso) => realWhen(parseTime(iso) ?? NaN, serverNow(), Boolean(app.state && app.state.mode === 'REPLAY'))?.at || null;

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

// The header row never scrolls sideways (review: 406 px at 390 with the state words and
// "Connecting…"). The AI words are the one place the Desk says the AI is off, paused or
// unavailable, so they go last (honesty verify, 17 Oct: a phone saw only a dot). When the row does
// not fit: the connection words go and the gaps close; then the wordmark and the REPLAY chip get
// compact; then the AI (i), the status's dot (its words say it) and the REPLAY chip's glyph go
// (each chip still opens what it explains); then the REPLAY clock (the chip keeps "REPLAY"); only
// then, on a row narrower than any phone, the AI words. Labels keep every state.
export function fitHead() {
  const row = document.querySelector('.dhead__row');
  const chip = byId('budget-chip');
  if (!row || !chip) return;
  chip.classList.remove('is-tight');
  row.classList.remove('is-tight', 'is-tighter', 'is-tightest', 'is-tiniest');
  const over = () => row.scrollWidth > row.clientWidth;
  const steps = ['is-tight', 'is-tighter', 'is-tightest', 'is-tiniest'].map((c) => () => row.classList.add(c));
  for (const step of [...steps, () => chip.classList.add('is-tight')]) {
    if (!over()) break;
    step();
  }
}

// The AI state in the header, said once for the whole Desk (owner, 17 Oct: "don't say no model
// everywhere"), in the demo's words (wall/x-parts.js stateLine, one copy for both pages): nothing
// but the assistant mark while it is on; otherwise a dot and two words, and an (i) whose popover
// says why and what still holds, with the way to the assistant sheet.

// The status: the one state; `model-chip` is its label span (desk.html).
export function drawAiChip() {
  const chip = byId('budget-chip');
  const label = byId('model-chip');
  const wrap = byId('ai-status');
  if (!chip || !label || !wrap || !app.state) return;
  const ai = deskAi();
  const w = aiWords(ai, { home: 'the assistant sheet', opens: 'the assistant sheet' });
  const line = stateLine(w, { kind: ai.kind, reason: ai.reason });
  const key = `${ai.kind}|${line.word}|${line.info || ''}`;
  chip.dataset.tone = w.tone;
  chip.dataset.kind = ai.kind;
  label.textContent = line.word || '';
  chip.replaceChildren(...(ai.kind === 'on' ? [icon('ta-16')] : [el('span', { class: 'aistat__dot', 'aria-hidden': 'true' }), label]));
  const jobs = ai.waiting.length ? ` ${plural(ai.waiting.length, 'job')} wait${ai.waiting.length === 1 ? 's' : ''}.` : '';
  chip.setAttribute('aria-label', w.aria.replace(/ Opens /, `${ai.kind === 'paused' ? jobs : ''} Opens `));
  chip.title = ai.kind === 'on' ? `${ASSISTANT} on` : line.word;
  // the (i) is redrawn only when what it says changes, so an open popover is not thrown away by a
  // budget event that changed nothing it shows
  if (wrap.dataset.key !== key) {
    wrap.dataset.key = key;
    const old = wrap.querySelector('.info');
    if (old) {
      old.close();
      old.remove();
    }
    if (line.info) {
      wrap.append(infoButton({
        topic: 'assistant', label: 'About the assistant state',
        text: line.info,
        actions: el('button', { type: 'button', class: 'linkbtn', onclick: openBudget }, el('span', { text: 'Assistant details ›' })),
      }));
    }
  }
  fitHead();
  // Ask's paused note and other places that word the assistant state redraw on this
  document.dispatchEvent(new CustomEvent('tephra:ai'));
}

// A model Google closed for today shows as closed, with a full bar, so its unused calls never read
// as calls to spare (D71, the Wall's "Closed for today by Google").
function modelRow(m) {
  const out = isOut(m);
  const pct = m.closed ? 100 : m.limit ? Math.min(100, Math.round((m.used / m.limit) * 100)) : 100;
  const bar = el('span', { class: `bbar bbar--${out ? 'out' : m.remaining / m.limit < 0.1 ? 'low' : 'ok'}`, 'aria-hidden': 'true' }, el('span', { class: 'bbar__fill' }));
  bar.firstElementChild.style.setProperty('--w', `${Math.max(pct, m.used ? 2 : 0)}%`);
  const status = m.closed
    ? `Closed for today by Google (${m.remaining.toLocaleString('en')} of ${m.limit.toLocaleString('en')} unused)`
    : out ? 'Used up for today' : `${m.remaining.toLocaleString('en')} left today`;
  return el('li', { class: 'aimodel' },
    el('p', { class: 'aimodel__h' },
      el('span', { class: 'aimodel__jobs', text: jobsWords(m.jobs) || m.tier }),
      el('span', { class: 'aimodel__n', text: m.closed ? 'Closed' : `${m.used.toLocaleString('en')} of ${m.limit.toLocaleString('en')} calls` })),
    bar,
    el('p', { class: `aimodel__status${out ? ' is-out' : ''}` }, icon(out ? 'st-caution' : 'st-ok', 'st'), el('span', { text: status })),
    el('p', { class: 'aimodel__id mono', text: m.model_id }));
}

// A job's own slot only when it is not the reset the lead already says (or already past): the time
// is said once (review clutter 7).
function workRow(w, reset) {
  const at = parseTime(w.next_slot_at) ?? NaN;
  const slot = Math.abs(at - reset) < 60000 ? null : slotWords(w.next_slot_at);
  const when = w.status === 'RUNNING' ? 'running now'
    : w.status === 'QUEUED' ? 'queued for the assistant'
      : slot ? `waits for its slot (${slot})` : 'waits in line';
  return el('li', { class: 'aiwork' }, icon(w.status === 'RUNNING' ? 'i-play' : 'i-clock', 'st'),
    el('span', {}, el('span', { class: 'aiwork__label', text: w.label }), el('span', { class: 'aiwork__when', text: when })));
}

function lanes(b) {
  const rows = models(b).flatMap((m) => (m.lanes || []).filter((l) => l.share > 0 || l.used > 0).map((l) =>
    el('li', {}, el('span', { class: 'mono', text: m.model_id }), ` · ${LANE_WORDS[l.lane] || l.lane}: ${l.used} of ${l.share}`)));
  const pacing = models(b).filter((m) => m.pacing).map((m) => el('li', {}, el('span', { class: 'mono', text: m.model_id }), ` · ${pacingWords(m.pacing)}`));
  if (!rows.length && !pacing.length) return null;
  return el('details', { class: 'more aisheet__more' },
    el('summary', {}, icon('i-chevron-right', 'icon disclosure'), el('span', { text: 'How the calls are shared' })),
    rows.length ? el('ul', { class: 'aisheet__lanes' }, rows) : null,
    pacing.length ? el('ul', { class: 'aisheet__lanes' }, pacing) : null);
}

// Where the service runs (SystemState.cloud, SPEC B07): one line, only on Cloud Run; the Wall's
// Details > Runs on carries the rest. Nothing is said for a local run.
function runsOn() {
  const c = app.state && app.state.cloud;
  if (!c || c.platform !== 'cloud-run') return null;
  const where = c.region ? ` (${c.region})` : '';
  const rev = c.revision ? `, revision ${c.revision}` : '';
  return el('p', { class: 'note', text: `Runs on Cloud Run${where}${rev}` });
}

// The assistant sheet, the Desk's home for TEPHRA Assistant (K80, Naming): the mark and the calm
// lead first, then what went wrong by cause, the work waiting for its slot, the calls per model
// (their ids, lanes and pacing), the way to the board on the Wall and the About line.
export function openBudget() {
  const b = app.budget;
  const ai = deskAi();
  const stub = ai.kind === 'off';
  const work = b && Array.isArray(b.waiting) ? b.waiting : [];
  const reset = parseTime(b && b.resets_at) ?? NaN;
  // the lead says when a paused assistant opens again; the foot does not say it a second time
  const resetSaid = ai.kind === 'paused' && Boolean(ai.until);
  const counts = b && b.resets_at && !resetSaid && slotWords(b.resets_at)
    ? ` Counts start again ${slotWords(b.resets_at) === hhmmz(b.resets_at) ? `at ${hhmmz(b.resets_at)}` : slotWords(b.resets_at)}.` : '';
  const mark = el('p', { class: `aisheet__mark aisheet__mark--${ai.kind}` }, icon('ta-64', 'aisheet__logo'));
  const lead = el('div', { class: `aisheet__lead aisheet__lead--${ai.kind}`, role: 'status' },
    ...aiLead(ai).map((p, i) => el('p', { class: i === 0 ? 'aisheet__head' : null }, el('strong', { text: p.strong }), ` ${p.text}`)));
  const causes = ai.causes.length
    ? el('section', { class: 'aisheet__sec', 'aria-labelledby': 'ai-causes-title' },
      el('h3', { id: 'ai-causes-title', class: 'aisheet__h', text: `What went wrong · ${plural(ai.causes.length, 'cause')}` }),
      el('ul', { class: 'aiworks' }, ...ai.causes.map((c) => el('li', { class: 'aiwork' }, icon('st-caution', 'st'),
        el('span', {}, el('span', { class: 'aiwork__label', text: causeTitle(c, { home: true }) }),
          el('span', { class: 'aiwork__when', text: [c.steps ? `${c.steps} ${c.steps === 1 ? 'time' : 'times'}` : null, Number.isFinite(c.first) ? `${hhmmz(c.first)}${c.last !== c.first ? `–${hhmmz(c.last)}` : ''}` : null, c.consequence].filter(Boolean).join(' · ') }))))),
      el('details', { class: 'tech' }, el('summary', { text: 'Technical detail' }), ...[...new Set(ai.causes.flatMap((c) => c.raw))].map((r) => el('p', { class: 'mono tech__line', text: machineText(r) }))))
    : null;
  const queue = work.length
    ? el('section', { class: 'aisheet__sec', 'aria-labelledby': 'ai-work-title' },
      el('h3', { id: 'ai-work-title', class: 'aisheet__h', text: `Waiting in line · ${work.length}` }),
      el('ul', { class: 'aiworks' }, work.map((w) => workRow(w, reset))),
      el('p', { class: 'note', text: 'Waiting work keeps its place and runs on the same model when its slot comes.' }))
    : null;
  const calls = b && !stub
    ? el('section', { class: 'aisheet__sec', 'aria-labelledby': 'ai-calls-title' },
      el('h3', { id: 'ai-calls-title', class: 'aisheet__h', text: 'Calls today, per model' }),
      el('ul', { class: 'aimodels' }, models(b).map((m) => modelRow(m))),
      lanes(b))
    : null;
  // a hosted airline: its model, key and daily limits are in Settings › Assistant; the board is the demo's
  const board = TENANT
    ? el('a', { class: 'btn btn--outline btn--block aisheet__board', href: `${PAGE_BASE}/settings/assistant` }, icon('i-model'), el('span', { text: 'Model, key and daily limits: Settings › Assistant' }), icon('i-chevron-right'))
    : el('a', { class: 'btn btn--outline btn--block aisheet__board', href: BOARD_URL, target: '_blank', rel: 'noopener' },
      icon('ta-16'), el('span', { text: `See ${ASSISTANT} at work` }), icon('i-external-link'));
  const notBuilt = TENANT
    ? el('section', { class: 'aisheet__sec', 'aria-labelledby': 'ai-nb-title' },
      el('h3', { id: 'ai-nb-title', class: 'aisheet__h', text: 'Not built' }),
      el('ul', { class: 'aisheet__nb' }, el('li', { text: 'Recovery re-planning for your network is not built.' })))
    : null;
  const foot = stub
    ? null
    : b
      ? el('p', { class: 'note', text: `${b.note}${counts} As of ${dayMonthHhmm(b.as_of)}.` })
      : el('p', { class: 'note', text: "Today's assistant calls have not loaded yet." });
  openBSheet({
    title: ASSISTANT,
    body: el('div', { class: 'stack aisheet' }, mark, lead, causes, queue, calls, board, notBuilt, foot, runsOn(),
      el('p', { class: 'note aisheet__about', text: 'About TEPHRA Assistant: TEPHRA Assistant is an AI assistant. It reads feeds and drafts text. Code does every number and safety rule. You approve everything.' })),
  });
}
