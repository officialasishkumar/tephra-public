// Network recovery board (WP4): the airports the ash closes, the day's flights re-planned by a
// CP-SAT solver in three scenarios (code), and the AI's recommendation with its rationale. The
// dispatcher approves or rejects the plan; approval can hand it to the message drafter.
// The airline and its schedule are fictional (Ring of Fire Air, synthetic).

import { PATHS, api, errorCode, isUnavailable, problems, unavailableReason } from './api.js';
import { announce, byId, el, icon } from './dom.js';
import { dayMonthHhmm, deskName, hhmmz } from './format.js';
import { app } from './state.js';
import { toast } from './toast.js';
import { aiChip, codeChip, emptyPanel, fmtUsd, openBSheet, sectionHead, unavailableCard } from './ui.js';

const STATUS = {
  DRAFT: ['i-clock', 'Awaiting your decision', 'neutral'],
  APPROVED: ['i-approved', 'Approved', 'ok'],
  REJECTED: ['i-rejected', 'Rejected', 'serious'],
  SUPERSEDED: ['i-superseded', 'Replaced by a newer plan', 'off'],
  AI_UNAVAILABLE: ['st-serious', 'AI unavailable', 'serious'],
};
const KIND = {
  CANCEL: ['i-x', 'Cancel'],
  DELAY: ['i-timer', 'Delay'],
  SWAP: ['i-refresh', 'Swap tail'],
  KEEP: ['i-check', 'Keep'],
};

let viewing = null; // scenario id being looked at
let running = false;
let runError = null; // { reason } | { text }

export const draftPlans = () => app.plans.filter((p) => p.status === 'DRAFT');
export const latestPlan = () => app.plans[0] || null;

export async function loadPlans() {
  const res = await api(PATHS.recovery);
  if (res.ok && res.data && Array.isArray(res.data.plans)) app.plans = res.data.plans.filter((p) => p && p.id).sort(byNewest);
  if (res.status !== 0) app.plansLoaded = true;
  renderNetwork();
  app.hub.afterPlans();
}

export const chosenOf = (p) => (p.scenarios || []).find((s) => s.id === p.chosen_scenario_id) || null;

const byNewest = (a, b) => String(b.created_at).localeCompare(String(a.created_at));

export function onRecoveryEvent(p) {
  if (!p || typeof p !== 'object' || typeof p.id !== 'string' || !p.status) return;
  const known = app.plans.find((x) => x.id === p.id);
  if (known && known.version > p.version) return;
  const wasTop = latestPlan() && latestPlan().id;
  app.plans = [p, ...app.plans.filter((x) => x.id !== p.id)].sort(byNewest);
  if (!known || latestPlan().id !== wasTop) viewing = null;
  renderNetwork();
  app.hub.afterPlans();
  if (!known && p.status === 'DRAFT') announce('A new recovery plan is waiting on the Network tab.');
}

// --- pieces ----------------------------------------------------------------------------------

function statusChip(p) {
  const [shape, word, tone] = STATUS[p.status] || STATUS.DRAFT;
  return el('span', { class: `adv-status adv-status--${tone}` }, icon(shape, 'st'), el('span', { text: word }));
}

function window_(c) {
  const end = c.open_ended ? `${dayMonthHhmm(c.end)} (planning horizon)` : dayMonthHhmm(c.end);
  return `${dayMonthHhmm(c.start)} to ${end}`;
}

function closuresBlock(p) {
  const list = p.closures || [];
  const out = [sectionHead('Closed airports', { count: list.length, id: 'net-closed', sub: 'Closed while the ash area comes within the closure radius. Written by code from the official products.' })];
  if (!list.length) {
    out.push(el('p', { class: 'note', text: 'No airport of the RFA network is closed.' }));
    return el('section', { class: 'nsec', 'aria-labelledby': 'net-closed' }, ...out);
  }
  out.push(el('ul', { class: 'clos' }, list.map((c) =>
    el('li', { class: 'clo' },
      el('span', { class: 'clo__icao' }, icon('i-airport', 'st'), el('span', { text: c.icao })),
      el('span', { class: 'clo__win' }, el('span', { text: window_(c) }), c.open_ended ? el('span', { class: 'chip chip--caution chip--sm' }, icon('st-caution', 'st'), el('span', { text: 'no end published' })) : null),
      el('details', { class: 'clo__more' },
        el('summary', {}, icon('i-chevron-right', 'icon disclosure'), el('span', { text: 'Why it is closed' })),
        el('p', { class: 'clo__why', text: c.reason }),
        c.source_ids && c.source_ids.length ? el('p', { class: 'clo__src mono', text: c.source_ids.join(' · ') }) : null)))));
  const d = p.disruption;
  if (d) {
    out.push(el('dl', { class: 'dstats' },
      stat('Flights blocked', d.blocked_flights.length),
      stat('Passengers blocked', d.blocked_pax.toLocaleString('en-US')),
      stat('Free to change', d.free_flights),
      stat('Frozen', d.frozen_flights),
      d.airborne_at_risk.length ? stat('Airborne at risk', d.airborne_at_risk.join(', ')) : null));
  }
  return el('section', { class: 'nsec', 'aria-labelledby': 'net-closed' }, ...out);
}

const stat = (k, v) => el('div', { class: 'dstat' }, el('dt', { text: k }), el('dd', { text: String(v) }));

// The bar's width is set through the CSSOM: the page's CSP forbids style attributes.
function barNode(pct) {
  const fill = el('span', { class: 'sc__fill' });
  fill.style.setProperty('--w', `${pct}%`);
  return el('span', { class: 'sc__bar', 'aria-hidden': 'true' }, fill);
}

function scenarioCard(p, s, maxUsd) {
  const t = s.totals;
  const chosen = s.id === p.chosen_scenario_id;
  const on = s.id === (viewing || p.chosen_scenario_id);
  const body = [];
  if (t) {
    body.push(el('p', { class: 'sc__usd' }, el('span', { class: 'sc__usdn', text: fmtUsd(t.total_usd) }), el('span', { class: 'sc__usdk', text: 'estimated cost' })),
      barNode(maxUsd ? Math.max(4, Math.round((t.total_usd / maxUsd) * 100)) : 4),
      el('dl', { class: 'sc__st' },
        stat('Cancelled', t.cancelled_flights), stat('Delayed', t.delayed_flights), stat('Swapped', t.swapped_flights),
        stat('Delay', `${t.delay_min} min`), stat('Passengers', t.pax_affected.toLocaleString('en-US')), stat('Ferry legs', t.ferries)));
  } else {
    body.push(el('p', { class: 'sc__none' }, icon('st-serious', 'st'), el('span', { text: `No plan found (solver ${s.solver_status})` })));
  }
  const btn = el('button', {
    type: 'button', class: `sc ${on ? 'is-on' : ''} ${chosen ? 'is-chosen' : ''}`.trim(), 'data-scenario': s.id, 'aria-pressed': String(on),
    'aria-label': `${s.label}${chosen ? ', recommended' : ''}${t ? `, ${fmtUsd(t.total_usd)}` : ', no plan'}. Show its flights`,
  },
  el('span', { class: 'sc__head' }, el('span', { class: 'sc__label', text: s.label }),
    chosen ? el('span', { class: 'sc__rec' }, icon('i-sparkle', 'st'), el('span', { text: 'Recommended' })) : null),
  ...body,
  el('span', { class: 'sc__fine', text: `solved in ${s.solve_ms} ms · ${s.solver_status}` }));
  return el('li', { class: 'sc__item' }, btn);
}

function scenariosBlock(p) {
  const list = p.scenarios || [];
  const max = Math.max(0, ...list.map((s) => (s.totals ? s.totals.total_usd : 0)));
  return el('section', { class: 'nsec', 'aria-labelledby': 'net-sc' },
    sectionHead('Scenarios compared', { id: 'net-sc', count: list.length, sub: 'The same day re-planned if the closure lasts as forecast, or longer. Solved by code; costs use the operator\'s illustrative weights.' }),
    list.length ? el('ul', { class: 'scs' }, list.map((s) => scenarioCard(p, s, max))) : el('p', { class: 'note', text: 'No scenario was solved.' }),
    el('p', { class: 'fine', text: 'Tap a scenario to see its flights below.' }));
}

function rationaleBlock(p) {
  if (p.status === 'AI_UNAVAILABLE' || (!p.rationale && p.outcome === 'MODEL_FAILED')) {
    return el('section', { class: 'nsec' },
      sectionHead('Recommendation', { id: 'net-why' }),
      unavailableCard((p.unavailable_reason || 'no reason given').replace(/^AI UNAVAILABLE:?\s*/i, ''), { instead: 'The solver\'s scenarios stand, but no recommendation was made. Choose by hand.' }));
  }
  const card = el('div', { class: 'why' },
    el('p', { class: 'why__meta' }, aiChip(p.model_id, p.llm_backend, { sm: true }),
      p.outcome === 'REPAIRED' ? el('span', { class: 'chip chip--sm', text: 'repaired once' }) : null,
      el('span', { class: 'chip chip--sm', text: 'numbers checked by code' })),
    el('p', { class: 'why__text', text: p.rationale || '' }));
  if (p.risks && p.risks.length) card.append(el('p', { class: 'caps', text: 'Risks' }), el('ul', { class: 'plist' }, p.risks.map((r) => el('li', { text: r }))));
  if (p.validation_errors && p.validation_errors.length) {
    card.append(el('details', { class: 'disclose' }, el('summary', {}, icon('i-chevron-right', 'icon disclosure'), el('span', { text: `Checks that failed (${p.validation_errors.length})` })),
      el('ul', { class: 'plist' }, p.validation_errors.map((r) => el('li', { text: r })))));
  }
  return el('section', { class: 'nsec', 'aria-labelledby': 'net-why' }, sectionHead('Why this scenario', { id: 'net-why' }), card);
}

function actionRow(a) {
  const [shape, word] = KIND[a.kind] || KIND.KEEP;
  const detail = a.kind === 'DELAY' ? `+${a.delay_min} min, departs ${hhmmz(a.new_std)}` : a.kind === 'SWAP' ? `to ${a.new_tail} (was ${a.tail})` : a.kind === 'CANCEL' ? (a.pair_id ? 'cancelled with its return leg' : 'cancelled') : '';
  return el('tr', { class: `ar ar--${a.kind.toLowerCase()}` },
    el('th', { scope: 'row' }, el('span', { class: 'ar__f mono', text: a.flight_no }), el('span', { class: 'ar__r', text: `${a.origin} → ${a.dest} · ${hhmmz(a.std)}` })),
    el('td', {}, el('span', { class: `akind akind--${a.kind.toLowerCase()}` }, icon(shape, 'st'), el('span', { text: word })), detail ? el('span', { class: 'ar__d', text: detail }) : null),
    el('td', { class: 'ar__p', text: String(a.pax_booked) }));
}

function actionsBlock(p) {
  const s = (p.scenarios || []).find((x) => x.id === (viewing || p.chosen_scenario_id)) || chosenOf(p);
  if (!s) return null;
  const acts = [...(s.actions || [])].sort((a, b) => String(a.std).localeCompare(String(b.std)));
  const sec = el('section', { class: 'nsec', 'aria-labelledby': 'net-acts' },
    sectionHead('Flight by flight', { id: 'net-acts', count: acts.length, sub: `${s.label}${s.id === p.chosen_scenario_id ? ' (recommended)' : ''}. Every other free flight keeps its schedule.` }));
  if (!acts.length) {
    sec.append(el('p', { class: 'note', text: s.totals ? 'No flight changes in this scenario.' : 'No plan was found for this scenario.' }));
    return sec;
  }
  sec.append(el('div', { class: 'atable-wrap' }, el('table', { class: 'atable' },
    el('caption', { class: 'sr-only', text: `Flights changed in ${s.label}` }),
    el('thead', {}, el('tr', {}, el('th', { scope: 'col', text: 'Flight' }), el('th', { scope: 'col', text: 'Action' }), el('th', { scope: 'col', class: 'ar__p', text: 'Pax' }))),
    el('tbody', {}, acts.map(actionRow)))));
  if (s.ferry_legs && s.ferry_legs.length) {
    sec.append(el('p', { class: 'caps', text: 'Ferry legs (no passengers)' }),
      el('ul', { class: 'plist' }, s.ferry_legs.map((f) => el('li', { text: `${f.tail} ${f.origin} → ${f.dest}, departs ${hhmmz(f.dep)}, ${f.block_min} min` }))));
  }
  return sec;
}

function decisionBar(p) {
  if (p.status === 'DRAFT') {
    const t = chosenOf(p) && chosenOf(p).totals;
    return el('div', { class: 'ndec', role: 'group', 'aria-label': 'Decide the recovery plan' },
      el('p', { class: 'ndec__what' }, el('strong', { text: 'Recovery plan awaiting you' }),
        t ? el('span', { text: ` · ${t.cancelled_flights} cancel · ${t.delayed_flights} delay · ${fmtUsd(t.total_usd)}` }) : null),
      el('div', { class: 'secondary' },
        el('button', { type: 'button', class: 'btn btn--approve', 'data-plan-approve': p.id, disabled: app.offline }, icon('i-check'), el('span', { text: 'Approve plan…' })),
        el('button', { type: 'button', class: 'btn btn--reject', 'data-plan-reject': p.id, disabled: app.offline }, icon('i-x'), el('span', { text: 'Reject…' }))));
  }
  if (p.status === 'APPROVED') {
    return el('div', { class: 'ndec ndec--ok', role: 'group' },
      el('p', { class: 'ndec__what' }, icon('i-approved', 'st'), el('strong', { text: `Approved by ${deskName(p.decided_by) || 'a dispatcher'} at ${hhmmz(p.decided_at)}` }), el('span', { text: ' · queued, not sent anywhere' })),
      el('button', { type: 'button', class: 'btn btn--neutral', 'data-plan-msgs': p.id, disabled: app.offline }, icon('i-sparkle'), el('span', { text: 'Draft crew and passenger messages' })));
  }
  if (p.status === 'REJECTED') {
    return el('div', { class: 'ndec ndec--no', role: 'group' }, el('p', { class: 'ndec__what' }, icon('i-rejected', 'st'),
      el('strong', { text: `Rejected by ${deskName(p.decided_by) || 'a dispatcher'} at ${hhmmz(p.decided_at)}` }), p.reject_reason ? el('span', { text: `: ${p.reject_reason}` }) : null));
  }
  return null;
}

// --- the panel ---------------------------------------------------------------------------------

export function renderNetwork() {
  const panel = byId('panel-network');
  if (!panel) return;
  const p = latestPlan();
  const run = el('button', { type: 'button', class: `btn ${p ? '' : 'btn--neutral'}`.trim(), 'data-run': '1', disabled: running || app.offline, 'aria-busy': running ? 'true' : null },
    running ? el('span', { class: 'spinner', 'aria-hidden': 'true' }) : icon('i-refresh'), el('span', { text: running ? 'Planning…' : p ? 'Run recovery again' : 'Run recovery' }));
  const head = el('div', { class: 'phead' },
    el('h1', { id: 'net-title', class: 'phead__title', tabindex: '-1', text: 'Network recovery' }),
    el('p', { class: 'phead__sub', text: 'Closed airports, the day re-planned, your decision.' }),
    el('p', { class: 'phead__tags' },
      el('span', { class: 'chip chip--fict', title: 'Ring of Fire Air and its schedule are made up' }, icon('i-info', 'st'), el('span', { text: 'Fictional airline RFA · synthetic schedule' })),
      p && p.replay ? el('span', { class: 'chip chip--replay chip--sm' }, icon('i-replay', 'st'), el('span', { text: 'REPLAY' })) : null),
    run);
  const parts = [head];
  if (runError) {
    parts.push(runError.reason ? unavailableCard(runError.reason, { instead: 'No plan was made. Re-plan the day by hand.', onRetry: runRecovery }) : el('div', { class: 'panel panel--serious', role: 'alert' }, el('p', { class: 'panel__title' }, icon('st-serious', 'st'), el('span', { text: runError.text }))));
  }
  if (!p) {
    parts.push(app.plansLoaded ? emptyPanel('No recovery plan yet', 'A plan appears when the ash closes an airport of the RFA network. You can also run one now.') : el('p', { class: 'boot' }, el('span', { class: 'spinner', 'aria-hidden': 'true' }), el('span', { text: 'Loading…' })));
    panel.replaceChildren(...parts);
    return;
  }
  parts.push(el('div', { class: 'nstat' }, statusChip(p), el('span', { class: 'nstat__t', text: `Planned ${hhmmz(p.created_at)} · v${p.version}` }), p.model_id ? codeChip('Solver: code') : null));
  parts.push(closuresBlock(p), scenariosBlock(p));
  const why = rationaleBlock(p);
  if (why) parts.push(why);
  const acts = actionsBlock(p);
  if (acts) parts.push(acts);
  if (app.plans.length > 1) {
    parts.push(el('details', { class: 'disclose' }, el('summary', {}, icon('i-chevron-right', 'icon disclosure'), el('span', { text: `Earlier plans (${app.plans.length - 1})` })),
      el('ul', { class: 'plist' }, app.plans.slice(1).map((x) => el('li', { text: `${hhmmz(x.created_at)} · ${(STATUS[x.status] || [0, x.status])[1]}${chosenOf(x) && chosenOf(x).totals ? ` · ${fmtUsd(chosenOf(x).totals.total_usd)}` : ''}` })))));
  }
  parts.push(el('p', { class: 'fine', text: 'Decision support only. Approving a plan queues it on TEPHRA\'s own outbound queue; nothing is sent to an airline system.' }));
  const bar = decisionBar(p);
  panel.replaceChildren(...parts, ...(bar ? [bar] : []));
}

// --- actions -----------------------------------------------------------------------------------

export async function runRecovery() {
  if (running) return;
  if (app.offline) {
    toast({ tone: 'caution', title: "You're offline. Reconnect to run recovery." });
    return;
  }
  running = true;
  runError = null;
  renderNetwork();
  announce('Planning recovery. This can take a few seconds.');
  const res = await api(PATHS.recoveryRun, { method: 'POST', body: { closures: [] } });
  running = false;
  if (res.ok && res.data && res.data.id) {
    onRecoveryEvent(res.data);
    toast({ tone: 'ok', title: 'Recovery plan drafted. Review it before you decide.' });
    return;
  }
  if (isUnavailable(res)) runError = { reason: unavailableReason(res) };
  else if (res.status === 409) runError = { text: errorCode(res) === 'no_closure' ? 'No airport of the RFA network is closed, so there is nothing to re-plan.' : errorCode(res) === 'busy' ? 'A recovery plan is already being made. Wait for it.' : (res.data && res.data.detail) || 'Not run.' };
  else if (res.status === 401) runError = { text: 'Your session has ended. Sign in again.' };
  else runError = { text: res.status === 0 ? "Can't reach the server." : `Recovery was not run: ${(res.data && res.data.detail) || `HTTP ${res.status}`}` };
  renderNetwork();
}

function confirmApprove(p) {
  const t = chosenOf(p) && chosenOf(p).totals;
  const go = el('button', { type: 'button', class: 'btn btn--approve btn--block btn--primary' }, icon('i-check'), el('span', { text: 'Approve recovery plan' }));
  const msg = el('div', { 'aria-live': 'polite' });
  const sheet = openBSheet({
    title: 'Approve recovery plan?',
    body: el('div', { class: 'stack' },
      el('p', { class: 'lead', text: chosenOf(p) ? `Scenario: ${chosenOf(p).label}` : 'Recommended scenario' }),
      t ? el('dl', { class: 'dstats' }, stat('Cancelled', t.cancelled_flights), stat('Delayed', t.delayed_flights), stat('Swapped', t.swapped_flights), stat('Passengers', t.pax_affected.toLocaleString('en-US')), stat('Cost', fmtUsd(t.total_usd))) : null,
      el('p', { class: 'note', text: `Queues the plan on TEPHRA's own outbound queue under ${app.me ? app.me.name : 'your name'}. Nothing is sent to an airline system. You can then draft crew and passenger messages.` }), msg),
    footer: go,
  });
  go.addEventListener('click', async () => {
    go.disabled = true;
    go.replaceChildren(el('span', { class: 'spinner', 'aria-hidden': 'true' }), el('span', { text: 'Approving…' }));
    const res = await api(PATHS.recoveryDecide(p.id, 'approve'), { method: 'POST', body: { version: p.version } });
    if (res.ok && res.data && res.data.id) {
      onRecoveryEvent(res.data);
      sheet.close();
      toast({ tone: 'ok', title: `Recovery plan approved under ${app.me ? app.me.name : 'you'}. Not sent to any system.` });
      return;
    }
    go.disabled = false;
    go.replaceChildren(icon('i-check'), el('span', { text: 'Approve recovery plan' }));
    msg.replaceChildren(el('p', { class: 'msg msg--serious' }, icon('st-serious', 'st'), el('span', { text: res.status === 409 ? 'This plan changed or was already decided. Reload the Network tab.' : `Not approved: ${(res.data && res.data.detail) || `HTTP ${res.status}`}` })));
    if (res.status === 409) loadPlans();
  });
}

function confirmReject(p) {
  const area = el('textarea', { id: 'plan-reason', class: 'field', rows: '4', maxlength: '500', 'aria-describedby': 'plan-reason-note' });
  const msg = el('div', { 'aria-live': 'polite' });
  const go = el('button', { type: 'button', class: 'btn btn--reject-solid btn--block' }, icon('i-x'), el('span', { text: 'Reject plan' }));
  const sheet = openBSheet({
    title: 'Reject recovery plan',
    body: el('div', { class: 'stack' }, el('label', { class: 'flabel', for: 'plan-reason', text: 'Reason (required, at least 3 characters)' }), area,
      el('p', { id: 'plan-reason-note', class: 'note', text: 'The reason is recorded in the audit log. Nothing is queued.' }), msg),
    footer: go,
  });
  go.addEventListener('click', async () => {
    const reason = area.value.trim();
    if (reason.length < 3) {
      msg.replaceChildren(el('p', { class: 'msg msg--caution' }, icon('st-caution', 'st'), el('span', { text: 'Give a reason of at least 3 characters.' })));
      area.focus();
      return;
    }
    go.disabled = true;
    const res = await api(PATHS.recoveryDecide(p.id, 'reject'), { method: 'POST', body: { version: p.version, reason } });
    go.disabled = false;
    if (res.ok && res.data && res.data.id) {
      onRecoveryEvent(res.data);
      sheet.close();
      toast({ tone: 'rejected', title: 'Recovery plan rejected · reason recorded.' });
      return;
    }
    const list = problems(res);
    msg.replaceChildren(el('p', { class: 'msg msg--serious' }, icon('st-serious', 'st'), el('span', { text: `Not rejected: ${list.length ? list.join('; ') : (res.data && res.data.detail) || `HTTP ${res.status}`}` })));
  });
  window.setTimeout(() => area.focus(), 50);
}

export function onNetworkClick(event) {
  const t = event.target.closest('button');
  if (!t || !byId('panel-network').contains(t)) return false;
  if (t.dataset.run) {
    runRecovery();
    return true;
  }
  if (t.dataset.scenario) {
    viewing = t.dataset.scenario;
    renderNetwork();
    const again = byId('panel-network').querySelector(`[data-scenario="${CSS.escape(viewing)}"]`);
    if (again) again.focus({ preventScroll: true });
    return true;
  }
  const p = latestPlan();
  if (t.dataset.planApprove && p) confirmApprove(p);
  else if (t.dataset.planReject && p) confirmReject(p);
  else if (t.dataset.planMsgs && p) app.hub.draftMessages({ recovery_id: p.id }, t);
  else return false;
  return true;
}
