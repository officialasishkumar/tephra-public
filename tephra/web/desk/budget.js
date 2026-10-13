// The Desk's one AI chip in the header (docs/UI-AI-QUIET.md K78, K79): the AI's state in words
// ("AI paused · 0700Z"), never red. It opens the "AI today" sheet: the calm lead, what went
// wrong by cause, the calls per model and the work waiting for budget. GET /api/budget at start,
// then the `budget` SSE event after every model job.

import { PATHS, api } from './api.js';
import { byId, el, icon } from './dom.js';
import { dayMonthHhmm, hhmmz } from './format.js';
import { app } from './state.js';
import { aiState, openBSheet } from './ui.js';
import { aiLead, aiWords, causeTitle } from '../wall/x-parts.js';

const LANE_WORDS = { urgent: 'Urgent', interactive: 'Desk', routine: 'Routine' };

// The Desk's AI state now: the live budget, the open AI failures, the newest Duty Officer run
// and airport plan, and the backend.
export function deskAi() {
  const failures = [...app.failures.values()].filter((f) => !f.handled_at);
  const plan = app.plans.find((p) => p.status !== 'SUPERSEDED') || null;
  return aiState({ budget: app.budget, failures, llm: app.state && app.state.llm, duty: app.duty, plan });
}

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

const level = (t) => (t.closed || t.limit <= 0 || t.remaining <= 0 ? 'out' : t.remaining / t.limit < 0.1 ? 'low' : 'ok');
const models = (b) => (Array.isArray(b.models) && b.models.length ? b.models : b.tiers);
const workWords = (w) => (w.status === 'RUNNING' ? 'running now' : w.status === 'QUEUED' ? 'queued for the AI worker' : w.reason || 'waiting for AI budget');

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
  const jobs = ai.waiting.length ? ` ${ai.waiting.length} job${ai.waiting.length === 1 ? '' : 's'} wait${ai.waiting.length === 1 ? 's' : ''}.` : '';
  chip.setAttribute('aria-label', w.aria.replace(/ Opens /, `${ai.kind === 'paused' ? jobs : ''} Opens `));
  chip.title = w.title;
  // Ask's paused note and other places that word the AI state redraw on this
  document.dispatchEvent(new CustomEvent('tephra:ai'));
}

function modelRow(m, stub) {
  const pct = m.limit ? Math.min(100, Math.round((m.used / m.limit) * 100)) : 100;
  const bar = el('span', { class: `bbar bbar--${level(m)}`, 'aria-hidden': 'true' }, el('span', { class: 'bbar__fill' }));
  bar.firstElementChild.style.setProperty('--w', `${Math.max(pct, m.used ? 2 : 0)}%`);
  const lanes = (m.lanes || []).filter((l) => l.share > 0 || l.used > 0).map((l) => `${LANE_WORDS[l.lane] || l.lane} ${l.used} of ${l.share}`).join(' · ');
  return el('li', { class: 'btier' },
    el('p', { class: 'btier__h' }, el('span', { class: 'btier__k', text: m.jobs || m.tier }), el('span', { class: 'btier__n', text: `${m.used} / ${m.limit}` })),
    bar,
    el('p', { class: 'fine' }, el('span', { class: 'mono', text: stub ? 'NO MODEL (offline stub)' : m.model_id }), ` · ${m.remaining} left`),
    lanes ? el('p', { class: 'fine mono', text: lanes }) : null,
    !stub && m.pacing ? el('p', { class: 'fine', text: m.pacing }) : null);
}

// The "AI today" sheet, the Desk's AI home (K80): the calm lead first, then what went wrong by
// cause, the calls per model (their ids, lanes and pacing) and the work waiting for budget.
export function openBudget() {
  const b = app.budget;
  const ai = deskAi();
  const stub = ai.kind === 'off';
  const work = b && Array.isArray(b.waiting) ? b.waiting : [];
  const queue = work.length
    ? [el('h3', { class: 'fine', text: 'AI work queued or waiting' }),
      el('ul', { class: 'btiers' }, ...work.map((w) => el('li', { class: 'fine' }, `${w.label}: ${workWords(w)}`))),
      el('p', { class: 'note', text: 'Waiting work is kept and runs on the same model when its slot comes. Nothing is dropped or handed to another model.' })]
    : [];
  const causes = ai.causes.length
    ? [el('h3', { class: 'fine', text: `What went wrong · ${ai.causes.length} cause${ai.causes.length === 1 ? '' : 's'}` }),
      el('ul', { class: 'btiers' }, ...ai.causes.map((c) => el('li', { class: 'fine' },
        el('strong', { text: causeTitle(c) }), ` · ${c.steps} ${c.steps === 1 ? 'time' : 'times'}${Number.isFinite(c.first) ? ` · ${hhmmz(c.first)}${c.last !== c.first ? `–${hhmmz(c.last)}` : ''}` : ''}`))),
      el('details', { class: 'tech' }, el('summary', { text: 'Technical detail' }), ...[...new Set(ai.causes.flatMap((c) => c.raw))].map((r) => el('p', { class: 'mono tech__line', text: r })))]
    : [];
  const resets = b && b.resets_at ? ` Counts start again at ${hhmmz(b.resets_at)}.` : '';
  openBSheet({
    title: 'AI today',
    body: el('div', { class: 'stack' },
      el('div', { class: 'ailead', role: 'status' }, ...aiLead(ai).map((p) => el('p', {}, el('strong', { text: p.strong }), ` ${p.text}`))),
      ...causes,
      b ? el('ul', { class: 'btiers' }, models(b).map((m) => modelRow(m, stub))) : el('p', { class: 'note', text: 'The budget has not loaded yet.' }),
      ...queue,
      b ? el('p', { class: 'note', text: `${b.note}${resets} As of ${dayMonthHhmm(b.as_of)}.` }) : null,
      el('p', { class: 'note', text: 'When a step runs out, it says AI unavailable and nothing is substituted.' })),
  });
}
