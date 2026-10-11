// TEPHRA Desk: the dispatcher's phone (docs/UI-DESIGN.md section 10, MODULES.md 5.9 and 8.5).
// Plain ES modules, no framework, no inline script (CSP). Feed and model text only ever goes
// in through textContent. No key press approves or rejects anything.

import { initAccount, setAccount } from './desk/account.js';
import { PATHS, api, isAdvisory, isSession, onReachability, parseEvent } from './desk/api.js';
import { announce, byId, el, icon, isWide, loadSprite } from './desk/dom.js';
import {
  actionText,
  activeNow,
  byUrgency,
  entryState,
  hhmmz,
  parseTime,
  serverNow,
  setActiveClock,
  setServerTime,
} from './desk/format.js';
import { SESSION_ENDED, hideLogin, initLogin, showLogin } from './desk/login.js';
import { flashNew, renderQueue, updateTimes } from './desk/queue.js';
import { closeSheet, onSheetClick, openSheet, sheetBusy, sheetOpenFor, showStamp, syncSheet, updateSheetTimes } from './desk/review.js';
import { app, draftList } from './desk/state.js';
import { toast } from './desk/toast.js';
import { initAsk, focusAsk, setFlightContext } from './desk/ask.js';
import { loadBudget, openBudget, setBudget } from './desk/budget.js';
import { clearHandover, loadDocs, loadHandover, onDocEvent, onDocsClick, renderDocs, docsToSign } from './desk/docs.js';
import { loadFailures, onFailureEvent, openFailures, openHandled } from './desk/failures.js';
import { draftMessages, loadMessages, onMessageEvent, openMessage, requestMessageDrafts } from './desk/messages.js';
import { draftPlans, loadPlans, onNetworkClick, onRecoveryEvent, renderNetwork, chosenOf } from './desk/network.js';
import { loadNotices, onNoticeEvent, openNotice, openPaste } from './desk/notice.js';
import { goTab, initTabs, setBadges } from './desk/tabs.js';
import { closeBSheet, fmtUsd } from './desk/ui.js';

const TICK_MS = 15000;
const SSE_OFFLINE_AFTER_MS = 10000;
const SSE_RETRY_MS = 5000;
const BACK_ONLINE_MS = 3000;
const SESSION_WARN_MS = 5 * 60000;
const STAMP_MS = 1200; // the decided stamp; kept under reduced motion (only its entrance moves)

let events = null;
let sseDownTimer = 0;
let sseRetryTimer = 0;
let sseDown = false;
let fetchFailed = false;
let tickTimer = 0;
let sessionTimer = 0;
let backOnlineTimer = 0;
let wakeLock = null;
let resumeId = null;
let firstListDone = false;
let askReady = false;

// --- system state: model label, REPLAY banner, disclaimer, clocks --------------------------

function applyState(state) {
  if (!state || typeof state !== 'object' || typeof state.mode !== 'string') return;
  const before = app.state;
  app.state = state;
  setActiveClock(state.now);
  setServerTime(state.server_time);

  const replay = state.mode === 'REPLAY';
  const bar = byId('replay-bar');
  bar.hidden = !replay;
  byId('replay-text').textContent = replay
    ? (state.replay && typeof state.replay.banner === 'string' && state.replay.banner) || 'REPLAY: recorded real feeds'
    : '';
  bar.title = replay && state.replay ? String(state.replay.label || '') : '';
  byId('replay-auto').hidden = !(replay && state.replay && state.replay.auto);
  if (typeof state.disclaimer === 'string' && state.disclaimer) byId('disclaimer').textContent = state.disclaimer;

  const llm = state.llm || {};
  const stub = llm.backend === 'stub';
  const chip = byId('model-chip');
  chip.classList.toggle('model-chip--stub', stub);
  chip.replaceChildren(icon(stub ? 'i-code' : 'i-model'), el('span', { text: String(llm.label || 'NO MODEL') }));
  chip.title = "Steps that call a model are marked AI-drafted; with NO MODEL, code templates stand in.";
  setTitle();
  measure();
  if (before && (before.mode !== state.mode || (before.replay || {}).case_id !== (state.replay || {}).case_id)) {
    if (app.me) {
      loadAll();
      loadCones();
    }
  }
}

function setTitle() {
  const n = app.me ? app.drafts.size + openFailures().length + draftMessages().length + draftPlans().length : 0;
  const replay = app.state && app.state.mode === 'REPLAY';
  document.title = `${replay ? 'REPLAY - ' : ''}${n ? `(${n}) ` : ''}TEPHRA Desk`;
}

async function loadState() {
  const res = await api(PATHS.state);
  if (res.ok) applyState(res.data);
}

// The hazard band is not on the advisory; it comes from the cone the draft names.
async function loadCones() {
  const res = await api(PATHS.wall);
  if (res.ok && res.data && res.data.snapshot) applyCones(res.data.snapshot.cones);
}

function applyCones(fc) {
  if (!fc || !Array.isArray(fc.features)) return;
  for (const f of fc.features) {
    const p = f && f.properties;
    if (p && p.part === 'cone' && typeof p.cone_id === 'string') {
      app.cones.set(p.cone_id, p);
      if (f.geometry) app.coneGeo.set(p.cone_id, f.geometry);
    }
  }
  renderQueue();
  syncSheet();
}

// --- connection: SSE, offline, back online ---------------------------------------------------

function setConn(conn) {
  app.conn = conn;
  const chip = byId('conn');
  // "Connected", not "Live": in REPLAY a green "Live" under the REPLAY bar reads as live data.
  const view = {
    live: ['st-ok', 'Connected', 'Connected to the TEPHRA server (updates stream in)'],
    reconnecting: ['st-stale', 'Reconnecting', 'Lost the update stream; trying again'],
    offline: ['st-serious', 'Offline', "Can't reach the TEPHRA server; decisions are off"],
    idle: ['st-never', 'Connecting', 'Connecting to the TEPHRA server'],
  }[conn];
  chip.dataset.conn = conn;
  chip.title = view[2];
  chip.replaceChildren(icon(view[0], 'st'), el('span', { text: view[1] }));
}

function openEvents() {
  if (events) events.close();
  window.clearTimeout(sseRetryTimer);
  const source = new EventSource(PATHS.events);
  events = source;
  source.addEventListener('open', () => {
    window.clearTimeout(sseDownTimer);
    const wasDown = sseDown;
    sseDown = false;
    setConn('live');
    refreshOffline();
    // A gap older than the server's history is not replayed: reload what the Desk shows.
    if (wasDown) {
      loadState();
      if (app.me) loadAll();
    }
  });
  source.addEventListener('error', () => {
    if (!sseDown) {
      sseDown = true;
      setConn('reconnecting');
      window.clearTimeout(sseDownTimer);
      sseDownTimer = window.setTimeout(() => {
        if (sseDown) refreshOffline();
      }, SSE_OFFLINE_AFTER_MS);
    }
    // EventSource retries by itself unless the server answered with an error status.
    if (source.readyState === EventSource.CLOSED) {
      sseRetryTimer = window.setTimeout(openEvents, SSE_RETRY_MS);
    }
  });
  source.addEventListener('state', (e) => applyState(parseEvent(e)));
  source.addEventListener('heartbeat', (e) => {
    const beat = parseEvent(e);
    if (!beat) return;
    setActiveClock(beat.now);
    if (app.state && beat.mode && beat.mode !== app.state.mode) loadState();
  });
  source.addEventListener('advisory', (e) => applyAdvisory(parseEvent(e), { stream: true }));
  source.addEventListener('cones', (e) => applyCones(parseEvent(e)));
  source.addEventListener('budget', (e) => setBudget(parseEvent(e)));
  source.addEventListener('ai_failure', (e) => {
    if (app.me) onFailureEvent(parseEvent(e));
    updateBadges();
  });
  source.addEventListener('message', (e) => {
    if (app.me) onMessageEvent(parseEvent(e));
    updateBadges();
  });
  source.addEventListener('recovery', (e) => {
    if (app.me) onRecoveryEvent(parseEvent(e));
  });
  source.addEventListener('doc', (e) => {
    if (app.me) onDocEvent(parseEvent(e));
  });
  source.addEventListener('notice', (e) => {
    if (app.me) onNoticeEvent(parseEvent(e));
  });
}

function refreshOffline() {
  const sseOffline = sseDown && byId('conn').dataset.conn !== 'live' && sseDownLongEnough();
  const offline = !navigator.onLine || fetchFailed || sseOffline;
  if (offline === app.offline) return;
  app.offline = offline;
  const banner = byId('net-banner');
  window.clearTimeout(backOnlineTimer);
  if (offline) {
    setConn('offline');
    banner.className = 'netbanner netbanner--offline';
    banner.replaceChildren(icon('i-offline'), el('span', { text: "You're offline. Can't approve right now: reconnect to decide. Drafts stay readable." }));
    banner.hidden = false;
    announce("You're offline. Decisions are off until you reconnect.");
  } else {
    setConn(sseDown ? 'reconnecting' : 'live');
    banner.className = 'netbanner netbanner--online';
    banner.replaceChildren(icon('i-online'), el('span', { text: 'Back online.' }));
    banner.hidden = false;
    announce('Back online.');
    backOnlineTimer = window.setTimeout(() => {
      banner.hidden = true;
      measure();
    }, BACK_ONLINE_MS);
    if (app.me) loadAll();
  }
  measure();
  syncSheet();
}

let sseDownSince = 0;
function sseDownLongEnough() {
  if (!sseDown) {
    sseDownSince = 0;
    return false;
  }
  if (!sseDownSince) sseDownSince = performance.now();
  return performance.now() - sseDownSince >= SSE_OFFLINE_AFTER_MS - 50;
}

onReachability((failed) => {
  if (failed === fetchFailed) return;
  fetchFailed = failed;
  refreshOffline();
});

// --- the draft list ----------------------------------------------------------------------

async function loadDrafts() {
  const seq = ++app.loadSeq;
  const refresh = byId('refresh');
  refresh.classList.add('is-spinning');
  refresh.setAttribute('aria-busy', 'true');
  const res = await api(PATHS.drafts);
  if (seq !== app.loadSeq) return;
  refresh.classList.remove('is-spinning');
  refresh.removeAttribute('aria-busy');
  if (res.status === 401) {
    handleUnauthorized();
    return;
  }
  if (!res.ok || !res.data || !Array.isArray(res.data.advisories)) {
    if (!app.listLoaded) {
      app.listError = res.status === 0
        ? "You're offline. Drafts will load when you reconnect."
        : (res.data && res.data.detail) || `The server answered HTTP ${res.status}.`;
    } else if (res.status !== 0) {
      toast({ tone: 'caution', title: "Can't refresh the drafts. Showing the last list loaded." });
    }
    renderQueue();
    return;
  }
  const fresh = new Map();
  for (const adv of res.data.advisories) {
    if (!isAdvisory(adv) || adv.status !== 'DRAFT') continue;
    const closed = app.closed.get(adv.id);
    if (closed && closed.version >= adv.version) continue;
    const known = app.drafts.get(adv.id);
    fresh.set(adv.id, known && known.version > adv.version ? known : adv);
  }
  // A draft that left the list without a stream event: keep it visible as closed if open.
  for (const [id, adv] of app.drafts) {
    if (!fresh.has(id) && sheetOpenFor() === id && !app.closed.has(id)) app.closed.set(id, { ...adv, status: 'SUPERSEDED' });
  }
  const arrivals = firstListDone ? [...fresh.keys()].filter((id) => !app.known.has(id)) : [];
  app.drafts = fresh;
  for (const id of fresh.keys()) app.known.add(id);
  app.listLoaded = true;
  app.listError = '';
  app.lastLoadedAt = activeNow();
  firstListDone = true;
  afterListChange();
  for (const id of arrivals) arrived(fresh.get(id));
}

function arrived(adv) {
  flashNew(adv.id);
  const st = entryState(adv, activeNow());
  const when = st.kind === 'inside' ? 'inside now' : st.kind === 'ahead' ? `enters in ${st.minutes} min` : 'entry due now';
  announce(`New draft: ${adv.proxy_flight}, ${actionText(adv)}, ${when}.`);
}

function applyAdvisory(adv, { stream }) {
  if (!isAdvisory(adv) || !app.me) return;
  const known = app.drafts.get(adv.id);
  if (known && known.version > adv.version) return;
  const closed = app.closed.get(adv.id);
  if (closed && closed.version >= adv.version) return;
  if (adv.status === 'DRAFT') {
    const isNew = !app.known.has(adv.id);
    app.drafts.set(adv.id, adv);
    app.known.add(adv.id);
    afterListChange();
    if (isNew && stream) arrived(adv);
    return;
  }
  app.drafts.delete(adv.id);
  if (known || app.known.has(adv.id)) app.closed.set(adv.id, adv);
  afterListChange();
  if (known && stream && !app.inFlight.has(adv.id) && sheetOpenFor() !== adv.id) {
    announce(adv.status === 'SUPERSEDED'
      ? `${adv.proxy_flight}: replaced by a newer draft.`
      : `${adv.proxy_flight}: ${adv.status.toLowerCase()} by another dispatcher.`);
  }
}

function afterListChange() {
  // At 1100 px and up the first card is always selected.
  if (isWide() && app.me) {
    const sorted = draftList().sort(byUrgency);
    const current = sheetOpenFor();
    if (!current || (!app.drafts.has(current) && !app.closed.has(current))) {
      if (sorted[0]) selectDraft(sorted[0].id, { focus: false });
      else if (current) {
        app.selectedId = null;
        closeSheet();
      }
    }
  }
  renderQueue();
  syncSheet();
  setTitle();
  updateWake();
  updateBadges();
}

// --- review navigation ---------------------------------------------------------------------

function findAdvisory(id) {
  return app.drafts.get(id) || app.closed.get(id) || null;
}

function selectDraft(id, { focus = true, push = true } = {}) {
  const adv = findAdvisory(id);
  if (!adv) return;
  app.selectedId = id;
  openSheet(adv, { focus });
  byId('desk-view').dataset.view = 'review';
  if (!isWide() && push && !(history.state && history.state.sheet === id)) {
    history.pushState({ sheet: id }, '');
  }
  renderQueue();
  measure();
}

function closeReview({ fromHistory = false, focusId = null, force = false } = {}) {
  if (sheetBusy() && !force) return;
  if (isWide()) {
    // The pane stays; the dispatcher just goes back to the list.
    focusCard(app.selectedId);
    return;
  }
  const was = app.selectedId;
  app.selectedId = null;
  closeSheet();
  byId('desk-view').dataset.view = 'queue';
  if (!fromHistory && history.state && history.state.sheet) history.back();
  renderQueue();
  measure();
  focusCard(focusId || was);
}

function focusCard(id) {
  const card = id && byId('cards').querySelector(`li[data-id="${CSS.escape(id)}"]:not(.is-leaving) .card`);
  if (card) card.focus();
  else focusQueueTitle();
}

function focusQueueTitle() {
  byId('q-title').focus({ preventScroll: false });
}

window.addEventListener('popstate', (event) => {
  if (isWide()) return;
  const id = event.state && event.state.sheet;
  if (id && findAdvisory(id)) selectDraft(id, { push: false });
  else if (sheetOpenFor()) closeReview({ fromHistory: true });
});

// --- decisions -----------------------------------------------------------------------------

async function decide(kind, adv, body) {
  app.inFlight.add(adv.id);
  renderQueue();
  const res = await api(PATHS.decide(adv.id, kind), { method: 'POST', body });
  app.inFlight.delete(adv.id);
  if (res.status === 401) {
    handleUnauthorized();
    return res;
  }
  if (!res.ok || !isAdvisory(res.data)) {
    renderQueue();
    if (res.data && res.data.current && isAdvisory(res.data.current)) applyAdvisory(res.data.current, { stream: false });
    return res;
  }
  const decided = res.data;
  // Focus goes to the card that took this one's place (the next most urgent).
  const index = Math.max(0, draftList().sort(byUrgency).findIndex((a) => a.id === decided.id));
  app.drafts.delete(decided.id);
  app.closed.set(decided.id, decided);
  announce(toastTitle(decided));
  // The human moment (10.8): the bar shows the decision, who and when, before the sheet closes.
  showStamp(decided);
  afterListChange();
  await new Promise((resolve) => window.setTimeout(resolve, STAMP_MS));
  decisionToast(decided);
  // The dispatcher may have signed out, or a stream event may have moved the sheet meanwhile.
  if (!app.me || sheetOpenFor() !== decided.id) return res;
  const sorted = draftList().sort(byUrgency);
  const next = sorted[Math.min(index, sorted.length - 1)] || null;
  if (isWide()) {
    if (next) selectDraft(next.id, { focus: false });
    else {
      app.selectedId = null;
      closeSheet();
    }
    afterListChange();
    focusCard(next && next.id);
  } else {
    afterListChange();
    // The sheet is still marked busy with this request; the decision is done, so close it.
    closeReview({ focusId: next && next.id, force: true });
  }
  return res;
}

function toastTitle(adv) {
  const by = app.me ? app.me.name : '';
  if (adv.status === 'APPROVED') return `Approved: ${actionText(adv)} for ${adv.proxy_flight} · queued ${hhmmz(adv.decided_at)} under ${by}. Not sent to any aircraft.`;
  if (adv.status === 'EDITED') return `Approved with your edits: ${adv.proxy_flight} · both versions are in the audit log.`;
  return `Rejected: ${adv.proxy_flight} · reason recorded.`;
}

// 10.8: the toast carries the audit line: the first two SRC lines and the newest audit entry.
async function decisionToast(adv) {
  const src = String(adv.header || '').split('\n').filter((l) => l.startsWith('SRC ')).slice(0, 2);
  const t = toast({ tone: adv.status === 'REJECTED' ? 'rejected' : 'ok', title: toastTitle(adv), lines: src });
  const res = await api(PATHS.audit(adv.id));
  const entries = res.ok && res.data && Array.isArray(res.data.entries) ? res.data.entries : [];
  const entry = entries.find((e) => e && e.action === adv.status) || entries[0];
  if (entry) t.setLines(src, `AUDIT ${entry.action} ${entry.actor} ${hhmmz(entry.at)}`);
}

// --- session ---------------------------------------------------------------------------------

function enterDesk(session, { focus = true } = {}) {
  app.me = session;
  hideLogin();
  byId('boot').hidden = true;
  byId('desk-view').hidden = false;
  setAccount(session);
  app.listLoaded = false;
  app.listError = '';
  byId('tabbar').hidden = false;
  if (!askReady) {
    initAsk();
    askReady = true;
  }
  renderQueue();
  loadDrafts().then(() => {
    if (resumeId && findAdvisory(resumeId)) selectDraft(resumeId);
    resumeId = null;
  });
  loadCones();
  loadExtras();
  goTab(app.tab, { focus: false, quiet: true });
  window.clearInterval(tickTimer);
  tickTimer = window.setInterval(() => {
    updateTimes();
    updateSheetTimes();
  }, TICK_MS);
  window.clearTimeout(sessionTimer);
  const warnIn = (parseTime(session.expires_at) ?? 0) - SESSION_WARN_MS - serverNow();
  if (warnIn > 0 && warnIn < 2 ** 31 - 1) {
    sessionTimer = window.setTimeout(() => toast({ tone: 'caution', title: `Your session ends at ${hhmmz(session.expires_at)}.`, ttl: 10000 }), warnIn);
  }
  if (focus) focusQueueTitle();
  measure();
}

function leaveDesk() {
  window.clearInterval(tickTimer);
  window.clearTimeout(sessionTimer);
  app.me = null;
  app.drafts.clear();
  app.closed.clear();
  app.known.clear();
  app.inFlight.clear();
  app.listLoaded = false;
  app.loadSeq += 1;
  firstListDone = false;
  app.selectedId = null;
  closeSheet();
  closeBSheet();
  app.failures.clear();
  app.messages.clear();
  app.plans = [];
  app.plansLoaded = false;
  app.docs = [];
  clearHandover();
  app.notices = [];
  byId('cards').replaceChildren();
  for (const id of ['fail-section', 'msg-section', 'plan-section', 'notice-section']) byId(id).replaceChildren();
  byId('tabbar').hidden = true;
  for (const t of ['ask', 'network', 'docs']) byId(`panel-${t}`).hidden = true;
  delete document.body.dataset.tab;
  byId('desk-view').hidden = true;
  byId('desk-view').dataset.view = 'queue';
  setAccount(null);
  setTitle();
  updateWake();
}

function handleUnauthorized() {
  if (!app.me) return;
  resumeId = app.selectedId;
  leaveDesk();
  showLogin(SESSION_ENDED);
}

async function signOut() {
  await api(PATHS.logout, { method: 'POST' });
  leaveDesk();
  showLogin('Signed out.', { info: true });
}

// --- wake lock (10.9): only while signed in, visible, and drafts wait ------------------------

async function updateWake() {
  const want = app.wakeWanted && app.me && app.drafts.size > 0 && document.visibilityState === 'visible';
  if (!('wakeLock' in navigator)) return;
  if (want && !wakeLock) {
    try {
      wakeLock = await navigator.wakeLock.request('screen');
      wakeLock.addEventListener('release', () => {
        wakeLock = null;
      });
    } catch {
      wakeLock = null; // silent if refused (battery saver, permissions policy)
    }
  } else if (!want && wakeLock) {
    const lock = wakeLock;
    wakeLock = null;
    lock.release().catch(() => {});
  }
}

// --- layout -----------------------------------------------------------------------------------

// The sticky sheet header sits under the page header, and the sheet body never hides its last
// row under the fixed action bar: both read these measured heights.
function measure() {
  const root = document.documentElement;
  const headH = byId('dhead').offsetHeight;
  root.style.setProperty('--dhead-h', `${headH}px`);
  root.style.setProperty('--head-h', `${headH + (isWide() && !byId('tabbar').hidden ? 48 : 0)}px`);
  const bar = byId('sheet-actions');
  root.style.setProperty('--bar-h', `${bar ? bar.offsetHeight : 0}px`);
  // The tab bar gives way to the review's fixed action bar on phones.
  const reviewing = app.tab === 'queue' && byId('desk-view').dataset.view === 'review' && !isWide();
  document.body.dataset.review = reviewing ? '1' : '0';
}

// --- tabs, extras, badges -------------------------------------------------------------------

function onTab(name, { changed, focus }) {
  measure();
  if (name === 'ask') {
    focusAsk();
  } else if (name === 'network') {
    renderNetwork();
    if (changed && app.me) loadPlans();
  } else if (name === 'docs') {
    renderDocs();
    if (changed && app.me) loadDocs();
  } else if (focus) focusQueueTitle();
  if (focus && name !== 'queue') {
    const title = byId({ network: 'net-title', docs: 'docs-title', ask: 'ask-title' }[name]);
    if (title) title.focus({ preventScroll: true });
  }
}

function loadExtras() {
  loadFailures();
  loadMessages();
  loadPlans();
  loadDocs();
  loadNotices();
  loadHandover();
}

function loadAll() {
  loadDrafts();
  loadExtras();
}

function updateBadges() {
  setBadges({
    queue: app.drafts.size + openFailures().length + draftMessages().length,
    network: draftPlans().length,
    docs: docsToSign().length,
  });
  setTitle();
}

// The Queue lists a recovery plan that waits for a decision; the plan itself is on Network.
function afterPlans() {
  const host = byId('plan-section');
  const list = draftPlans();
  host.hidden = list.length === 0;
  if (list.length) {
    const p = list[0];
    const sc = chosenOf(p);
    const t = sc && sc.totals;
    host.replaceChildren(
      el('div', { class: 'shead' }, el('h2', { class: 'shead__title', id: 'plan-title', text: 'Recovery plan to approve' }), el('span', { class: 'shead__count', text: String(list.length) })),
      el('button', { type: 'button', class: 'pcard', 'data-goto': 'network' },
        el('span', { class: 'pcard__row' }, icon('i-network'), el('span', { class: 'pcard__t', text: p.closures.map((c) => c.icao).join(', ') ? `${p.closures.map((c) => c.icao).join(', ')} closed` : 'Network plan' }), icon('i-chevron-right', 'icon pcard__go')),
        t ? el('span', { class: 'pcard__s', text: `${t.cancelled_flights} cancelled · ${t.delayed_flights} delayed · ${t.pax_affected.toLocaleString('en-US')} passengers · ${fmtUsd(t.total_usd)}` }) : el('span', { class: 'pcard__s', text: 'No recommendation: open it to choose by hand' }),
        el('span', { class: 'pcard__f', text: 'Open the Network tab to compare scenarios and decide.' })));
  } else host.replaceChildren();
  updateBadges();
}

function askAbout(adv) {
  setFlightContext(adv);
  closeReview({ force: true });
  goTab('ask', { focus: true });
}

// --- wiring -----------------------------------------------------------------------------------

function wire() {
  app.hub = {
    decide,
    closeReview: () => closeReview(),
    focusQueueTitle,
    applyState,
    measureBar: measure,
    goTab: (name) => goTab(name, { focus: true }),
    draftMessages: requestMessageDrafts,
    askAbout,
    afterPlans,
    badges: updateBadges,
  };
  initLogin((session) => {
    enterDesk(session);
    loadState();
  });
  initAccount({ onSignOut: signOut, onWakeChange: updateWake });

  document.addEventListener('click', (event) => {
    if (onSheetClick(event)) return;
    if (onNetworkClick(event) || onDocsClick(event)) return;
    const extra = event.target.closest('[data-handle], [data-msg], [data-notice], [data-paste], [data-goto]');
    if (extra) {
      if (extra.dataset.handle) openHandled(extra.dataset.handle);
      else if (extra.dataset.msg) openMessage(extra.dataset.msg);
      else if (extra.dataset.notice) openNotice(extra.dataset.notice);
      else if (extra.dataset.paste) openPaste();
      else if (extra.dataset.goto) goTab(extra.dataset.goto, { focus: true });
      return;
    }
    const open = event.target.closest('[data-open]');
    if (open) {
      selectDraft(open.dataset.open);
      return;
    }
    if (event.target.closest('[data-retry]')) {
      app.listError = '';
      app.listLoaded = false;
      renderQueue();
      loadDrafts();
    }
  });
  byId('refresh').addEventListener('click', () => {
    loadDrafts();
    loadExtras();
  });
  byId('budget-chip').addEventListener('click', openBudget);
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape' || !sheetOpenFor() || isWide() || app.tab !== 'queue') return;
    if (event.target.closest('textarea, input, dialog, #account-menu')) return;
    closeReview();
  });
  window.addEventListener('online', refreshOffline);
  window.addEventListener('offline', refreshOffline);
  document.addEventListener('visibilitychange', () => {
    updateWake();
    if (document.visibilityState !== 'visible') return;
    // Phones suspend background tabs: catch up when the Desk is looked at again.
    loadState();
    if (app.me) loadAll();
    if (!events || events.readyState === EventSource.CLOSED) openEvents();
  });
  new ResizeObserver(measure).observe(byId('dhead'));
  window.matchMedia('(min-width: 1100px)').addEventListener('change', () => {
    if (isWide()) {
      byId('desk-view').dataset.view = 'review';
      afterListChange();
    } else if (!sheetOpenFor()) byId('desk-view').dataset.view = 'queue';
    measure();
  });
}

async function boot() {
  await loadSprite();
  wire();
  setConn('idle');
  initTabs(onTab);
  loadState();
  loadBudget();
  openEvents();
  const res = await api(PATHS.me);
  byId('boot').hidden = true;
  if (res.ok && isSession(res.data)) enterDesk(res.data, { focus: false });
  else if (res.status === 503 && res.data && res.data.error === 'desk_disabled') showLogin('', { disabled: true });
  else if (res.status === 0) showLogin("You're offline. Reconnect to sign in.");
  else showLogin();
}

boot();
