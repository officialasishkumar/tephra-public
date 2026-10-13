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
  entryShort,
  entryState,
  hhmmz,
  parseTime,
  serverNow,
  setActiveClock,
  setServerTime,
} from './desk/format.js';
import { SESSION_ENDED, hideLogin, initLogin, setPending, showLogin } from './desk/login.js';
import { breakdownText, flashNew, renderQueue, showAllDrafts, showMostUrgent, updateTimes } from './desk/queue.js';
import { closeSheet, onSheetClick, openSheet, sheetBusy, sheetOpenFor, sheetReceiptHost, sheetStepBack, showStamp, syncSheet, updateSheetTimes } from './desk/review.js';
import { app, draftList } from './desk/state.js';
import { toast } from './desk/toast.js';
import { initAsk, focusAsk, setFlightContext } from './desk/ask.js';
import { drawAiChip, loadBudget, openBudget, setBudget } from './desk/budget.js';
import { clearHandover, loadDocs, loadHandover, onDocEvent, onDocsClick, renderDocs, docsToSign } from './desk/docs.js';
import { loadDuty, onDutyEvent } from './desk/duty.js';
import { loadFailures, onFailureEvent, openFailures, openHandled } from './desk/failures.js';
import { draftMessages, loadMessages, onMessageEvent, openMessage, requestMessageDrafts } from './desk/messages.js';
import { draftPlans, latestPlan, loadPlans, noteTrace, onNetworkClick, onRecoveryEvent, renderNetwork, chosenOf } from './desk/network.js';
import { loadNotices, onNoticeEvent, openNotice, openPaste } from './desk/notice.js';
import { goTab, initTabs, setBadges } from './desk/tabs.js';
import { closeBSheet } from './desk/ui.js';
import { loadCrewPolicy, openCrewForm, openCrewReport, renderCrewSection, setAircraft, setCrew } from './desk/crew.js';

const TICK_MS = 15000;
const SSE_OFFLINE_AFTER_MS = 10000;
const SSE_RETRY_MS = 5000;
const BACK_ONLINE_MS = 3000;
const SESSION_WARN_MS = 5 * 60000;
const STAMP_MS = 1200; // the decided stamp; kept under reduced motion (only its entrance moves)
const DECISION_TOAST_MS = 15000; // the receipt toast; other toasts keep 6 s

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

  // R10.1, docs/UI-AI-QUIET.md K78: one AI chip with the AI's state; the model ids are in its sheet.
  drawAiChip();
  applyActiveRegions(null);
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
  const n = app.me ? draftList().length + openFailures().length + draftMessages().length + draftPlans().length : 0;
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
  if (res.ok && res.data && res.data.snapshot) {
    applyActiveRegions(res.data.snapshot.volcanoes);
    applyCones(res.data.snapshot.cones);
    applyExposed(res.data.snapshot.aircraft);
    setCrew(res.data.snapshot.crew);
  }
  if (res.ok && res.data && Array.isArray(res.data.trace)) noteTrace(res.data.trace);
}

// The flights in or heading into TEPHRA's area now ("hex:volcano_id"), from the Wall's aircraft
// layer: Paperwork's VAR list is exactly these, so its count matches the Wall (review 1, item 3)
// and the server accepts every row (a VAR needs the flight in the current exposure set).
function applyExposed(fc) {
  if (!fc || !Array.isArray(fc.features)) return;
  setAircraft(fc);
  const ids = new Set();
  for (const f of fc.features) {
    const p = f && f.properties;
    if (p && p.exposed === true && typeof p.hex === 'string' && p.volcano_id != null) ids.add(`${p.hex}:${p.volcano_id}`);
  }
  app.exposedIds = ids;
  if (app.tab === 'docs' && app.me) renderDocs();
}

// Paperwork lists the regions with an active volcano first (R10.7): a region is active when an
// active volcano's vent sits inside its box. Worked out from the same snapshot as the Wall.
let lastVolcanoes = null;
function applyActiveRegions(fc) {
  if (fc) lastVolcanoes = fc;
  else fc = lastVolcanoes;
  const regions = (app.state && app.state.regions) || [];
  const keys = new Set();
  for (const f of (fc && Array.isArray(fc.features) ? fc.features : [])) {
    const c = f && f.geometry && f.geometry.coordinates;
    if (!f.properties || !f.properties.active || !Array.isArray(c)) continue;
    const r = regions.find((x) => x.bbox && c[0] >= x.bbox.west && c[0] <= x.bbox.east && c[1] >= x.bbox.south && c[1] <= x.bbox.north);
    if (r) keys.add(r.key);
  }
  app.activeRegions = keys;
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
    reconnecting: ['st-stale', 'Reconnecting…', 'Lost the update stream; trying again'],
    offline: ['st-serious', 'Offline', "Can't reach the TEPHRA server; decisions are off"],
    idle: ['st-never', 'Connecting…', 'Connecting to the TEPHRA server'],
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
  source.addEventListener('aircraft', (e) => applyExposed(parseEvent(e)));
  source.addEventListener('trace', (e) => noteTrace(parseEvent(e)));
  source.addEventListener('crew', (e) => setCrew(parseEvent(e)));
  source.addEventListener('budget', (e) => setBudget(parseEvent(e)));
  source.addEventListener('ai_failure', (e) => {
    if (app.me) onFailureEvent(parseEvent(e));
    updateBadges();
  });
  source.addEventListener('duty', (e) => onDutyEvent(parseEvent(e)));
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
  renderCrewSection();
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
  const sel = id && CSS.escape(id);
  const card = sel && (byId('q-next').querySelector(`.next__card[data-id="${sel}"] [data-open]`)
    || byId('cards').querySelector(`li[data-id="${sel}"]:not(.is-leaving) .card`));
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
  const sorted = draftList().sort(byUrgency);
  const next = sorted[Math.min(index, sorted.length - 1)] || null;
  // The dispatcher may have signed out, or a stream event may have moved the sheet meanwhile.
  const moveOn = Boolean(app.me) && sheetOpenFor() === decided.id;
  // The receipt names the draft the sheet moves on to; on a phone it sits in the sheet's flow.
  decisionToast(decided, moveOn ? next : draftList().sort(byUrgency)[0], moveOn && next && !isWide());
  if (!moveOn) return res;
  // R10.3: the sheet moves on to the next draft ("Next: RFA1530 · inside now"); no bulk approval,
  // the next one needs its own hold or confirm.
  if (next) announce(`Next: ${next.proxy_flight} · ${entryShort(next, activeNow())}`);
  if (isWide()) {
    if (next) selectDraft(next.id, { focus: false });
    else {
      app.selectedId = null;
      closeSheet();
    }
    afterListChange();
    focusCard(next && next.id);
  } else if (next) {
    if (history.state && history.state.sheet) history.replaceState({ sheet: next.id }, '');
    selectDraft(next.id, { push: false });
  } else {
    afterListChange();
    // The sheet is still marked busy with this request; the decision is done, so close it.
    closeReview({ force: true });
  }
  return res;
}

function toastTitle(adv) {
  const by = app.me ? app.me.name : '';
  if (adv.status === 'APPROVED') return `Approved: ${actionText(adv)} for ${adv.proxy_flight} · queued ${hhmmz(adv.decided_at)} under ${by}. Not sent to any aircraft.`;
  if (adv.status === 'EDITED') return `Approved with your edits: ${adv.proxy_flight} · both versions are in the audit log.`;
  return `Rejected: ${adv.proxy_flight} · reason recorded.`;
}

// 10.8: the toast carries the audit line: the first two SRC lines and the audit entry for this
// decision. It stays DECISION_TOAST_MS (longer than other toasts) so the receipt can be read.
// Only the entry that records this decision is shown; another entry is never put in its place.
async function decisionToast(adv, nextUp, inSheet) {
  const src = String(adv.header || '').split('\n').filter((l) => l.startsWith('SRC ')).slice(0, 2);
  const note = nextUp ? `Next: ${nextUp.proxy_flight} · ${entryShort(nextUp, activeNow())}` : '';
  const t = toast({ tone: adv.status === 'REJECTED' ? 'rejected' : 'ok', title: toastTitle(adv), note, lines: src, ttl: DECISION_TOAST_MS, inline: inSheet ? sheetReceiptHost() : null });
  const res = await api(PATHS.audit(adv.id));
  const entries = res.ok && res.data && Array.isArray(res.data.entries) ? res.data.entries : [];
  const entry = entries.find((e) => e && e.action === adv.status);
  if (entry) t.setLines(src, `AUDIT ${entry.action} ${entry.actor} ${hhmmz(entry.at)}`);
  else t.setLines([...src, res.ok ? 'Audit entry not listed yet: see History under Decided while this page was open.' : "Can't load the audit line: see History under Decided while this page was open."]);
}

// --- deep link (R10.3): #review/<id> selects a draft, #tab/<key> switches tab ------------------
// The hash is only a pointer: it never skips the session check, the hold or the confirm step.

const REVIEW_HASH = /^#review\/(adv_[0-9a-f]{12})$/;
const TAB_HASH = /^#tab\/(queue|ask|network|docs)$/;
// #crew-report opens the crew report form; #crew/<CR-id> opens one report (the Wall links both).
const CREW_HASH = /^#crew\/(CR-[0-9a-f]{12})$/;

function readHash() {
  const h = window.location.hash;
  const review = REVIEW_HASH.exec(h);
  if (review) return { review: review[1] };
  if (h === '#crew-report') return { crewForm: true };
  const crew = CREW_HASH.exec(h);
  if (crew) return { crew: crew[1] };
  const tab = TAB_HASH.exec(h);
  return tab ? { tab: tab[1] } : null;
}

function clearHash() {
  if (window.location.hash) history.replaceState(history.state, '', window.location.pathname + window.location.search);
}

// Signed out: name the flight from the public list, so the sign-in says what it leads to.
async function pendingLogin() {
  const r = readHash();
  if (!r || !r.review) {
    setPending('');
    return;
  }
  setPending('Sign in to review this advisory.');
  const res = await api(`/api/advisories?limit=200`);
  const adv = res.ok && res.data && Array.isArray(res.data.advisories) ? res.data.advisories.find((a) => a && a.id === r.review) : null;
  if (!app.me && readHash() && readHash().review === r.review && adv) setPending(`Sign in to review ${adv.proxy_flight}.`);
}

let routeToast = null;

async function route() {
  const r = readHash();
  if (!r) return;
  if (!app.me) {
    pendingLogin();
    return;
  }
  setPending('');
  if (r.tab) {
    clearHash();
    goTab(r.tab, { focus: true });
    return;
  }
  if (r.crewForm || r.crew) {
    // The form needs the tracked flights and a report needs the picture: both come with /api/wall.
    if (!app.crew) return; // crewChanged routes again once the picture is in
    clearHash();
    goTab('queue', { focus: false, quiet: true });
    if (r.crewForm) openCrewForm();
    else openCrewReport(r.crew);
    return;
  }
  if (!app.listLoaded) return; // enterDesk routes again once the list is in
  const id = r.review;
  clearHash();
  goTab('queue', { focus: false, quiet: true });
  if (app.drafts.has(id)) {
    selectDraft(id);
    return;
  }
  // Not a draft any more, or gone: say so and show the Decide list with the next decision.
  const closed = app.closed.get(id);
  let gone = false;
  if (!closed) {
    const res = await api(PATHS.audit(id));
    gone = res.ok && res.data && Array.isArray(res.data.entries) && res.data.entries.length === 0;
  }
  // It is about the Decide list: leaving that tab dismisses it (review 1, item 15).
  routeToast?.dismiss();
  routeToast = toast({ tone: 'caution', title: gone ? 'This advisory no longer exists.' : 'This advisory is no longer a draft.' });
  showMostUrgent();
  const top = draftList().sort(byUrgency)[0];
  if (top && isWide()) selectDraft(top.id, { focus: false });
  focusCard(top && top.id);
}

window.addEventListener('hashchange', () => {
  if (readHash()) route();
});

// --- the ⋯ menu on Decide (R10.4): Paste a notice, Refresh ------------------------------------

function initMoreMenu() {
  const button = byId('q-more-btn');
  const menu = byId('q-more');
  const close = (focus = false) => {
    menu.hidden = true;
    button.setAttribute('aria-expanded', 'false');
    if (focus) button.focus();
  };
  button.addEventListener('click', () => {
    if (menu.hidden) {
      menu.hidden = false;
      button.setAttribute('aria-expanded', 'true');
      menu.querySelector('button').focus();
    } else close();
  });
  menu.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      event.stopPropagation();
      close(true);
    }
    const items = [...menu.querySelectorAll('button')];
    const i = items.indexOf(document.activeElement);
    const dir = event.key === 'ArrowDown' ? 1 : event.key === 'ArrowUp' ? -1 : 0;
    if (dir && i >= 0) {
      event.preventDefault();
      items[(i + dir + items.length) % items.length].focus();
    }
  });
  menu.addEventListener('click', (event) => {
    if (event.target.closest('button')) close();
  });
  document.addEventListener('click', (event) => {
    if (!menu.hidden && !menu.contains(event.target) && !button.contains(event.target)) close();
  });
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
    route();
  });
  loadCones();
  loadExtras();
  loadCrewPolicy();
  renderCrewSection();
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
  byId('q-next').replaceChildren();
  for (const id of ['fail-section', 'msg-section', 'plan-section', 'notice-section', 'crew-section']) byId(id).replaceChildren();
  byId('crew-section').hidden = true;
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
  const want = app.wakeWanted && app.me && draftList().length > 0 && document.visibilityState === 'visible';
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
  if (changed && name !== 'queue' && routeToast) {
    routeToast.dismiss();
    routeToast = null;
  }
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
  loadDuty();
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

// R2.7: the Decide badge counts advisories, messages and open problems together, and says so.
function updateBadges() {
  setBadges({
    queue: draftList().length + openFailures().length + draftMessages().length,
    network: draftPlans().length,
    docs: docsToSign().length,
  }, { queue: breakdownText() });
  // Messages and problems change the Next decision's breakdown line too.
  if (app.me && app.listLoaded) renderQueue();
  setTitle();
  // failures and plans change the AI's state (one cause however many flights)
  drawAiChip();
}

// Decide links to an airport plan that waits for a decision; the plan itself is on Airports
// (R10.4): "Airport plan waiting: 3 airports closed, cancel 133 ›".
function afterPlans() {
  const host = byId('plan-section');
  const list = draftPlans();
  host.hidden = list.length === 0;
  if (list.length) {
    const p = list[0];
    const sc = chosenOf(p);
    const t = sc && sc.totals;
    const n = (p.closures || []).length;
    const bits = [`${n} airport${n === 1 ? '' : 's'} closed (all volcanoes)`];
    if (t) bits.push(`cancel ${t.cancelled_flights}`);
    else bits.push('no plan found');
    // the link names the plan it opens: an older draft is not the newest plan (K94)
    const latest = latestPlan();
    const head = latest && latest.id !== p.id ? `Earlier plan ${hhmmz(p.created_at)} waiting for your decision: ` : 'Airport plan waiting: ';
    host.replaceChildren(el('button', { type: 'button', class: 'qlink__btn', 'data-goto': 'network' },
      icon('i-network', 'icon qlink__ic'),
      el('span', { class: 'qlink__t' }, el('strong', { id: 'plan-title', text: head }), el('span', { text: bits.join(', ') })),
      icon('i-chevron-right', 'icon qlink__go')));
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
    // A new crew picture can flag or unflag a draft: its card, row and review follow.
    crewChanged: () => {
      if (!app.me) return;
      renderQueue();
      syncSheet();
      const r = readHash();
      if (r && (r.crewForm || r.crew)) route();
    },
  };
  initLogin((session) => {
    enterDesk(session);
    loadState();
  });
  initAccount({ onSignOut: signOut, onWakeChange: updateWake });
  initMoreMenu();

  document.addEventListener('click', (event) => {
    if (onSheetClick(event)) return;
    if (onNetworkClick(event) || onDocsClick(event)) return;
    const crew = event.target.closest('[data-crewform], [data-crew]');
    if (crew) {
      if (crew.dataset.crewform) openCrewForm();
      else if (crew.dataset.crew) openCrewReport(crew.dataset.crew);
      return;
    }
    const extra = event.target.closest('[data-handle], [data-msg], [data-notice], [data-paste], [data-goto]');
    if (extra) {
      if (extra.dataset.handle) openHandled(extra.dataset.handle);
      else if (extra.dataset.msg) openMessage(extra.dataset.msg);
      else if (extra.dataset.notice) openNotice(extra.dataset.notice);
      else if (extra.dataset.paste) openPaste();
      else if (extra.dataset.goto) goTab(extra.dataset.goto, { focus: true });
      return;
    }
    if (event.target.closest('[data-newest]')) {
      const top = draftList().sort(byUrgency)[0];
      // The Next decision follows the open review, so the most urgent is opened in it too.
      if (top && app.selectedId && app.selectedId !== top.id && isWide()) selectDraft(top.id, { focus: false });
      showMostUrgent();
      focusCard(top && top.id);
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
  byId('cards-all').addEventListener('click', () => {
    showAllDrafts();
    // focus moves to the first row that was hidden
    const first = byId('cards').querySelectorAll('li:not(.is-leaving) .card')[5];
    if (first) first.focus();
  });
  byId('refresh').addEventListener('click', () => {
    loadDrafts();
    loadExtras();
  });
  byId('budget-chip').addEventListener('click', openBudget);
  // the chip drops its time below 420 px (UI-AI-QUIET 5.2)
  window.addEventListener('resize', drawAiChip);
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape' || !sheetOpenFor() || app.tab !== 'queue') return;
    if (event.target.closest('dialog, #account-menu')) return;
    // One level per press: Reject or Edit (even from inside its text box) back to the review,
    // then, on a phone, the review back to Decide (review 2, item 9).
    if (sheetStepBack()) {
      event.preventDefault();
      return;
    }
    if (isWide() || event.target.closest('textarea, input')) return;
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
  if (!app.me) route();
}

boot();
