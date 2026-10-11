// The AI budget chip in the header: model calls used today against the free-tier limit.
// GET /api/budget at start, then the `budget` SSE event after every model call.

import { PATHS, api } from './api.js';
import { byId, el, icon } from './dom.js';
import { dayMonthHhmm } from './format.js';
import { app } from './state.js';
import { openBSheet } from './ui.js';

const TIER_WORDS = { main: 'Main model (plume reader)', lite: 'Lite model (everything else, speech included)' };

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

const level = (t) => (t.limit <= 0 || t.remaining <= 0 ? 'out' : t.remaining / t.limit < 0.1 ? 'low' : 'ok');

function draw() {
  const chip = byId('budget-chip');
  if (!chip || !app.budget) return;
  const lite = app.budget.tiers.find((t) => t.tier === 'lite') || app.budget.tiers[0];
  const worst = app.budget.tiers.map(level).includes('out') ? 'out' : app.budget.tiers.map(level).includes('low') ? 'low' : 'ok';
  chip.hidden = false;
  chip.dataset.level = worst;
  const kids = [icon('i-gauge'), el('span', { class: 'budget__n', text: `${lite.used}/${lite.limit}` })];
  if (worst !== 'ok') kids.push(el('span', { class: 'budget__w', text: worst }));
  chip.replaceChildren(...kids);
  chip.setAttribute('aria-label', `AI calls today: ${app.budget.tiers.map((t) => `${TIER_WORDS[t.tier] || t.tier} ${t.used} of ${t.limit}`).join('; ')}. Open details.`);
  chip.title = 'AI calls used today (free tier). Tap for details.';
}

export function openBudget() {
  const b = app.budget;
  if (!b) return;
  const rows = b.tiers.map((t) => {
    const pct = t.limit ? Math.min(100, Math.round((t.used / t.limit) * 100)) : 100;
    const bar = el('span', { class: `bbar bbar--${level(t)}`, 'aria-hidden': 'true' }, el('span', { class: 'bbar__fill' }));
    bar.firstElementChild.style.setProperty('--w', `${Math.max(pct, t.used ? 2 : 0)}%`);
    return el('li', { class: 'btier' },
      el('p', { class: 'btier__h' }, el('span', { class: 'btier__k', text: TIER_WORDS[t.tier] || t.tier }), el('span', { class: 'btier__n', text: `${t.used} / ${t.limit}` })),
      bar,
      el('p', { class: 'fine' }, el('span', { class: 'mono', text: t.model_id === 'stub' ? 'NO MODEL (offline stub)' : t.model_id }), ` · ${t.remaining} left`));
  });
  openBSheet({
    title: 'AI budget today',
    body: el('div', { class: 'stack' },
      el('ul', { class: 'btiers' }, rows),
      el('p', { class: 'note', text: `${b.note} As of ${dayMonthHhmm(b.as_of)}.` }),
      el('p', { class: 'note', text: 'When a step runs out, it says AI unavailable and nothing is substituted.' })),
  });
}
