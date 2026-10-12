// The AI budget chip in the header: model calls used today against the free-tier limit, per
// model, and the AI work waiting for budget ("waiting for AI budget, next slot 1432Z").
// GET /api/budget at start, then the `budget` SSE event after every model job.

import { PATHS, api } from './api.js';
import { byId, el, icon } from './dom.js';
import { dayMonthHhmm, hhmmz } from './format.js';
import { app } from './state.js';
import { openBSheet } from './ui.js';

const LANE_WORDS = { urgent: 'Urgent', interactive: 'Desk', routine: 'Routine' };

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
  draw();
}

const level = (t) => (t.closed || t.limit <= 0 || t.remaining <= 0 ? 'out' : t.remaining / t.limit < 0.1 ? 'low' : 'ok');
const models = (b) => (Array.isArray(b.models) && b.models.length ? b.models : b.tiers);
const waiting = (b) => (Array.isArray(b.waiting) ? b.waiting.filter((w) => w.status === 'WAITING') : []);
const workWords = (w) => (w.status === 'RUNNING' ? 'running now' : w.status === 'QUEUED' ? 'queued for the AI worker' : w.reason || 'waiting for AI budget');

function draw() {
  const chip = byId('budget-chip');
  if (!chip || !app.budget) return;
  const b = app.budget;
  const lite = b.tiers.find((t) => t.tier === 'lite') || b.tiers[0];
  const levels = models(b).map(level);
  const worst = levels.includes('out') ? 'out' : levels.includes('low') ? 'low' : 'ok';
  const held = waiting(b);
  chip.hidden = false;
  chip.dataset.level = worst;
  // R10.1: "AI calls today: 0 of 450"; on a phone "AI 0/450" (the aria-label is always full).
  const kids = [icon('i-gauge'),
    el('span', { class: 'budget__long', text: `AI calls today: ${lite.used} of ${lite.limit}` }),
    el('span', { class: 'budget__short', 'aria-hidden': 'true', text: `AI ${lite.used}/${lite.limit}` })];
  if (worst !== 'ok') kids.push(el('span', { class: 'budget__w', text: worst }));
  if (held.length) kids.push(el('span', { class: 'budget__w', text: `${held.length} waiting` }));
  chip.replaceChildren(...kids);
  const counts = models(b).map((m) => `${m.jobs || m.tier} (${m.model_id}) ${m.used} of ${m.limit}`).join('; ');
  chip.setAttribute('aria-label', `AI calls today: ${counts}.${held.length ? ` ${held.length} AI jobs waiting for budget.` : ''} Open details.`);
  chip.title = 'AI calls used today (free tier), per model. Tap for details.';
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

export function openBudget() {
  const b = app.budget;
  if (!b) return;
  const stub = b.backend === 'stub';
  const work = Array.isArray(b.waiting) ? b.waiting : [];
  const queue = work.length
    ? [el('h3', { class: 'fine', text: 'AI work queued or waiting' }),
      el('ul', { class: 'btiers' }, ...work.map((w) => el('li', { class: 'fine' }, `${w.label}: ${workWords(w)}`))),
      el('p', { class: 'note', text: 'Waiting work is kept and runs on the same model when its slot comes. Nothing is dropped or handed to another model.' })]
    : [];
  const resets = b.resets_at ? ` Counts start again at ${hhmmz(b.resets_at)}.` : '';
  openBSheet({
    title: 'AI budget today',
    body: el('div', { class: 'stack' },
      el('ul', { class: 'btiers' }, models(b).map((m) => modelRow(m, stub))),
      ...queue,
      el('p', { class: 'note', text: `${b.note}${resets} As of ${dayMonthHhmm(b.as_of)}.` }),
      el('p', { class: 'note', text: 'When a step runs out, it says AI unavailable and nothing is substituted.' })),
  });
}
