// TEPHRA Desk: the dispatcher's phone (docs/UI-DESIGN.md section 10, MODULES.md 5.9 and 8.5).
// Plain ES modules, no framework, no inline script (CSP). Feed and model text only ever goes
// in through textContent. No key press approves or rejects anything.

import { initAccount, setAccount } from './desk/account.js';
import { PATHS, api, isAdvisory, isSession, onReachability, parseEvent } from './desk/api.js';
import { WIDE_QUERY, announce, byId, el, icon, isDesktop, isWide, loadSprite } from './desk/dom.js';
import {
  actionText,
  activeNow,
  entryState,
  hhmmz,
  parseTime,
  serverNow,
  setActiveClock,
  setServerTime,
} from './desk/format.js';
import { SESSION_ENDED, hideLogin, initLogin, setPending, showLogin, syncVisitorCard } from './desk/login.js';
import { breakdownText, flashNew, openClosed, renderQueue, showAllDrafts, showAllWatching, showMostUrgent, updateTimes, waitingCount, walkOrder } from './desk/queue.js';
import { closeSheet, onSheetClick, openSheet, receiptWords, refreshFacts, setReceipt, sheetBusy, sheetOpenFor, sheetStepBack, showStamp, syncSheet, updateSheetTimes } from './desk/review.js';
import { app, draftList } from './desk/state.js';
import { initDeskMap, patchDeskSnapshot, setDeskSnapshot } from './desk/map.js';
import { toast } from './desk/toast.js';
import { initAsk, focusAsk, setFlightContext } from './desk/ask.js';
import { drawAiChip, fitHead, loadBudget, openBudget, setBudget } from './desk/budget.js';
import { drawModeChip } from './desk/modechip.js';
import { clearHandover, loadDocs, loadHandover, onDocEvent, onDocsClick, renderDocs } from './desk/docs.js';
import { loadDuty, onDutyEvent } from './desk/duty.js';
import { loadFailures, onFailureEvent, openBulk, openFailures, openHandled, renderFailures } from './desk/failures.js';
import { renderIdle } from './desk/idle.js';
import { loadMessages, onMessageEvent, openMessage, requestMessageDrafts } from './desk/messages.js';
import { loadPlans, noteTrace, onNetworkClick, onRecoveryEvent, renderNetwork } from './desk/network.js';
import { loadNotices, onNoticeEvent, openNotice, openPaste } from './desk/notice.js';
import { goTab, initTabs, setBadges } from './desk/tabs.js';
import { closeBSheet, describeReplayIn } from './desk/ui.js';
import { loadCrewPolicy, openCrewForm, openCrewReport, renderCrewSection, setAircraft, setCrew } from './desk/crew.js';
import { applyFeatureNav, has, setFeatures } from './wall/features.js';
import { setModelBackend } from './wall/x-parts.js';
import { TENANT, rewriteLinks, tenantPath } from './base.js';
import { mountTenantNav, onTenantHeader, titleFor } from './tenant-nav.js';
import { isViewer } from './desk/ui.js';

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

// --- system state: model label, clocks --------------------------

function applyState(state) {
  if (!state || typeof state !== 'object' || typeof state.mode !== 'string') return;
  const before = app.state;
  app.state = state;
  setFeatures(state.features);
  setModelBackend(state.llm && state.llm.backend);
  applyFeatures();
  syncVisitorCard();
  setActiveClock(state.now);
  setServerTime(state.server_time);

  // a sheet open across a mode switch gets the new REPLAY words in its sr-only description
  for (const dlg of document.querySelectorAll('dialog[open]')) describeReplayIn(dlg);

  // R10.1, docs/UI-AI-QUIET.md K78: one AI status with the AI's state; the model ids are in its
  // sheet. REPLAY and its clock: one header chip (owner's lead, 17 Oct).
  drawAiChip();
  drawModeChip();
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

// The optional features the server shows (SystemState.features, TEPHRA_FEATURES): the Desk's
// entries for a hidden feature are hidden, their ids and code stay (SPEC 5.3). Ask's mic and the
// account menu's Data connections consult has() where they are drawn; the
// nav's Onboard link follows wall/features.js applyFeatureNav.
function applyFeatures() {
  // a hosted airline's viewer enters no crew report and pastes no notice (SPEC-FINAL 6.1)
  byId('crew-report-btn').hidden = !has('crew');
  byId('paste-notice').hidden = !has('notices');
  if (isViewer()) {
    byId('crew-report-btn').hidden = true;
    byId('paste-notice').hidden = true;
  }
  applyFeatureNav();
}

// The page title, the Decide badge and Decide's count read the same number (waitingCount).
function setTitle() {
  const n = app.me ? waitingCount().n : 0;
  const replay = app.state && app.state.mode === 'REPLAY';
  if (TENANT) {
    document.title = `${n ? `(${n}) ` : ''}${titleFor(tenantNow, 'Desk')}`;
    return;
  }
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
    setDeskSnapshot(res.data.snapshot);
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
  patchDeskSnapshot('aircraft', fc);
  const ids = new Set();
  for (const f of fc.features) {
    const p = f && f.properties;
    if (p && p.exposed === true && typeof p.hex === 'string' && p.volcano_id != null) ids.add(`${p.hex}:${p.volcano_id}`);
  }
  app.exposedIds = ids;
  if (app.tab === 'docs' && app.me) renderDocs();
  // the levels on Decide's rows and in the review's Check facts come from this layer
  if (app.me) {
    renderQueue();
    refreshFacts();
  }
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
  patchDeskSnapshot('cones', fc);
  for (const f of fc.features) {
    const p = f && f.properties;
    if (p && p.part === 'cone' && typeof p.cone_id === 'string') {
      app.cones.set(p.cone_id, p);
      if (f.geometry) app.coneGeo.set(p.cone_id, f.geometry);
    }
  }
  renderQueue();
  syncSheet();
  refreshFacts();
}

// --- connection: SSE, offline, back online ---------------------------------------------------

function setConn(conn) {
  app.conn = conn;
  const chip = byId('conn');
  // "Connected", not "Live": in REPLAY a green "Live" under the REPLAY bar reads as live data.
  const view = {
    live: ['st-ok', 'Connected', 'Connected to the TEPHRA server (updates stream in)'],
    reconnecting: ['st-stale', 'Reconnecting…', 'Lost the update stream, trying again'],
    offline: ['st-serious', 'Offline', "Can't reach the TEPHRA server, so decisions are off"],
    idle: ['st-never', 'Connecting…', 'Connecting to the TEPHRA server'],
  }[conn];
  chip.dataset.conn = conn;
  chip.title = view[2];
  chip.replaceChildren(icon(view[0], 'st'), el('span', { text: view[1] }));
  fitHead();
}

function openEvents() {
  if (events) events.close();
  window.clearTimeout(sseRetryTimer);
  const source = new EventSource(tenantPath(PATHS.events));
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
  if (app.pageOpenedAt === null) app.pageOpenedAt = app.lastLoadedAt;
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
  // At 1100 px and up the right pane is never empty while there is work: the first card is
  // selected, or, with no draft, the flights to plan by hand open there.
  if (isWide() && app.me && app.pane !== 'failures') {
    const sorted = walkOrder();
    const current = sheetOpenFor();
    if (!current || (!app.drafts.has(current) && !app.closed.has(current))) {
      if (sorted[0]) selectDraft(sorted[0].id, { focus: false });
      else {
        if (current) {
          app.selectedId = null;
          closeSheet();
        }
        if (app.listLoaded && openFailures().length) openFailPane({ focus: false });
      }
    }
  }
  syncPanes();
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
  if (app.pane === 'failures') {
    app.pane = null;
    renderFailures();
  }
  app.selectedId = id;
  openSheet(adv, { focus });
  byId('desk-view').dataset.view = 'review';
  if (!isWide() && push && !(history.state && history.state.sheet === id)) {
    history.pushState({ sheet: id }, '');
  }
  syncPanes();
  renderQueue();
  measure();
}

// --- the flights to plan by hand: the right pane at 1100 px and up, a view of its own on a
// phone (with a history entry, so Back returns to Decide) -------------------------------------

function openFailPane({ focus = true, push = true } = {}) {
  if (!openFailures().length) return;
  app.pane = 'failures';
  if (isWide()) {
    app.selectedId = null;
    closeSheet();
  } else {
    byId('desk-view').dataset.view = 'failures';
    if (push && !(history.state && history.state.failures)) history.pushState({ failures: true }, '');
    window.scrollTo({ top: 0 });
  }
  renderFailures();
  syncPanes();
  renderQueue();
  measure();
  if (focus) byId('fp-title')?.focus({ preventScroll: true });
}

function closeFailPane({ fromHistory = false, focus = false } = {}) {
  if (app.pane !== 'failures') return;
  app.pane = null;
  if (!isWide()) {
    byId('desk-view').dataset.view = 'queue';
    if (!fromHistory && history.state && history.state.failures) history.back();
  }
  renderFailures();
  syncPanes();
  measure();
  if (focus) byId('fail-section').querySelector('[data-failpane]')?.focus();
}

// Which of the right-hand panes shows: the review (review.js owns #sheet), the flights to handle
// by hand, or the idle pane (CSS shows it at 1100 px and up while the other two are hidden).
function syncPanes() {
  const view = byId('desk-view').dataset.view;
  byId('fail-pane').hidden = !(app.pane === 'failures' && (isWide() || view === 'failures'));
  renderIdle();
}

function closeReview({ fromHistory = false, focusId = null, force = false } = {}) {
  if (sheetBusy() && !force) return;
  // The receipt line stays until the next decision or until the dispatcher closes the review;
  // after the last decision (forced close) it stays on Decide.
  if (!force) setReceipt(null);
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
    || byId('desk-view').querySelector(`li[data-id="${sel}"]:not(.is-leaving):not([hidden]) .card`));
  if (card) card.focus();
  else focusQueueTitle();
}

function focusQueueTitle() {
  byId('q-title').focus({ preventScroll: false });
}

window.addEventListener('popstate', (event) => {
  if (isWide()) return;
  const st = event.state || {};
  if (st.sheet && findAdvisory(st.sheet)) {
    selectDraft(st.sheet, { push: false });
    return;
  }
  if (sheetOpenFor()) closeReview({ fromHistory: true });
  if (st.failures) openFailPane({ push: false });
  else closeFailPane({ fromHistory: true, focus: true });
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
  // "Next" follows the act-by order from the item decided: the one that took its place.
  const index = Math.max(0, walkOrder().findIndex((a) => a.id === decided.id));
  app.drafts.delete(decided.id);
  app.closed.set(decided.id, decided);
  // The human moment (10.8): the bar shows the decision, who and when, before the sheet moves on.
  showStamp(decided);
  afterListChange();
  await new Promise((resolve) => window.setTimeout(resolve, STAMP_MS));
  const sorted = walkOrder();
  const next = sorted[Math.min(index, sorted.length - 1)] || null;
  // The dispatcher may have signed out, or a stream event may have moved the sheet meanwhile.
  const moveOn = Boolean(app.me) && sheetOpenFor() === decided.id;
  // D3: one receipt line, pinned above the next review (or on Decide), said once. No toast.
  setReceipt(decided);
  announce(`${receiptWords(decided)}.${moveOn && next ? ` Next: ${next.proxy_flight}.` : ''}`);
  if (!moveOn) return res;
  // R10.3: the sheet moves on to the next draft; no bulk approval, the next one needs its own
  // hold or confirm.
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

// "Skip for now" (5.3): the next item in the act-by order opens; this one stays in Decide. It is
// not a decision and is not audited.
function skipTo(id) {
  if (!app.drafts.has(id) || sheetBusy()) return;
  if (!isWide() && history.state && history.state.sheet) history.replaceState({ sheet: id }, '');
  selectDraft(id, { push: false });
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
    // Ask is a drawer over any tab, not a tab: #tab/ask opens it (UI-DESIGN 10.18).
    if (r.tab === 'ask') openAsk();
    else goTab(r.tab, { focus: true });
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
  const top = walkOrder()[0];
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
  initDeskMap((id) => selectDraft(id));
  setAccount(session);
  fitHead();
  app.listLoaded = false;
  app.listError = '';
  byId('tabbar').hidden = false;
  // Ask is a dispatcher's: a hosted airline's viewer reads only
  byId('ask-btn').hidden = isViewer();
  applyFeatures();
  if (!askReady) {
    initAsk();
    askReady = true;
  }
  renderQueue();
  loadDrafts().then(() => {
    if (resumeId && findAdvisory(resumeId)) selectDraft(resumeId);
    // A visitor came to decide: the lead review opens at once, on every width (SPEC 5.1); a deep
    // link still wins (route() below).
    else if (session.role === 'visitor' && walkOrder()[0]) selectDraft(walkOrder()[0].id, { focus: false });
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
  app.pageOpenedAt = null;
  app.loadSeq += 1;
  firstListDone = false;
  app.selectedId = null;
  app.pane = null;
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
  setReceipt(null);
  for (const id of ['fail-section', 'fail-pane', 'idle-pane', 'msg-section', 'plan-section', 'notice-section', 'crew-section', 'watch-section']) byId(id).replaceChildren();
  byId('fail-pane').hidden = true;
  byId('crew-section').hidden = true;
  byId('reports').hidden = true;
  byId('tabbar').hidden = true;
  for (const t of ['network', 'docs']) byId(`panel-${t}`).hidden = true;
  closeAsk();
  byId('ask-btn').hidden = true;
  delete document.body.dataset.tab;
  byId('desk-view').hidden = true;
  byId('desk-view').dataset.view = 'queue';
  setAccount(null);
  setTitle();
  updateWake();
}

function handleUnauthorized() {
  if (TENANT) {
    location.assign(`/signin?next=${encodeURIComponent(location.pathname)}`);
    return;
  }
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
  root.style.setProperty('--head-h', `${headH + (isDesktop() && !byId('tabbar').hidden ? 48 : 0)}px`);
  const bar = byId('sheet-actions');
  // a bar placed after the content (review.js placeBar) takes no room from it
  root.style.setProperty('--bar-h', `${bar && !bar.classList.contains('actions--after') ? bar.offsetHeight : 0}px`);
  // The tab bar gives way to the review's fixed action bar on phones.
  const reviewing = app.tab === 'queue' && byId('desk-view').dataset.view === 'review' && !isDesktop();
  document.body.dataset.review = reviewing ? '1' : '0';
}

// --- tabs, extras, badges -------------------------------------------------------------------

function onTab(name, { changed, focus }) {
  if (changed && name !== 'queue' && routeToast) {
    routeToast.dismiss();
    routeToast = null;
  }
  measure();
  if (name === 'network') {
    renderNetwork();
    if (changed && app.me) loadPlans();
  } else if (name === 'docs') {
    renderDocs();
    if (changed && app.me) loadDocs();
  } else if (focus) focusQueueTitle();
  if (focus && name !== 'queue') {
    const title = byId({ network: 'net-title', docs: 'docs-title' }[name]);
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

// One waiting count (Desk redesign 3, A11): only Decide has a badge, and it is the h1's number
// and the page title's. Its label says what it counts.
function updateBadges() {
  setBadges({ queue: waitingCount().n }, { queue: breakdownText() });
  // Messages, plans, documents and flights to plan by hand are rows on Decide too.
  if (app.me && app.listLoaded) renderQueue();
  renderIdle();
  setTitle();
  // failures and plans change the AI's state (one cause however many flights)
  drawAiChip();
}

// An airport plan waiting for a decision is a row in Decide's Other decisions (queue.js); the
// plan itself is on Airports.
function afterPlans() {
  updateBadges();
}

// Ask opens beside whatever is open (the review stays, so a question about a flight keeps it in
// view); Escape, the close button or the Ask button again closes it.
function openAsk() {
  byId('ask-drawer').hidden = false;
  byId('ask-btn').setAttribute('aria-expanded', 'true');
  document.body.dataset.ask = '1';
  focusAsk();
}

function closeAsk() {
  if (byId('ask-drawer').hidden) return;
  byId('ask-drawer').hidden = true;
  byId('ask-btn').setAttribute('aria-expanded', 'false');
  document.body.dataset.ask = '0';
  byId('ask-btn').focus({ preventScroll: true });
}

function askAbout(adv) {
  setFlightContext(adv);
  openAsk();
}

// --- wiring -----------------------------------------------------------------------------------

function wire() {
  app.hub = {
    decide,
    closeReview: () => closeReview(),
    focusQueueTitle,
    applyState,
    closeFailPane: () => closeFailPane(),
    // With no draft to review, the flights to plan by hand fill the right pane (1100 px and up).
    failuresChanged: () => {
      if (app.me && isWide() && !sheetOpenFor() && app.pane !== 'failures' && openFailures().length) openFailPane({ focus: false });
      syncPanes();
    },
    // a new Duty Officer run changes the must-do marks and the AI's state (renderFailures draws
    // the Duty Officer card too)
    dutyChanged: () => {
      renderFailures();
      updateBadges();
    },
    measureBar: measure,
    goTab: (name) => goTab(name, { focus: true }),
    draftMessages: requestMessageDrafts,
    skipTo,
    openDraft: (id) => selectDraft(id),
    // the review reloads the list once after a cone_changed refusal (review.js decide)
    reloadDrafts: () => loadDrafts(),
    // Sheets never stack (3): on a phone the review closes before a message sheet opens; the
    // receipt line stays on Decide. At 1100 px and up the review is a pane and stays.
    leaveReview: () => {
      if (!isWide() && sheetOpenFor()) closeReview({ force: true });
    },
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
    const pane = event.target.closest('[data-failpane], [data-failbulk]');
    if (pane) {
      if (pane.dataset.failbulk) openBulk();
      else if (pane.dataset.failpane === 'close') closeFailPane({ focus: true });
      else if (app.pane !== 'failures') openFailPane();
      else byId('fp-title')?.focus();
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
    if (event.target.closest('[data-watch="all"]')) {
      showAllWatching();
      const rows = byId('watch-list') ? byId('watch-list').querySelectorAll('li:not(.is-leaving) .card') : [];
      if (rows[3]) rows[3].focus();
      return;
    }
    if (event.target.closest('[data-newest]')) {
      const top = walkOrder()[0];
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
  byId('closed-open').addEventListener('click', openClosed);
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
  // the status drops its words when the header row is full (budget.js fitHead)
  window.addEventListener('resize', drawAiChip);
  byId('ask-btn').addEventListener('click', () => (byId('ask-drawer').hidden ? openAsk() : closeAsk()));
  byId('ask-close').addEventListener('click', closeAsk);
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !byId('ask-drawer').hidden && event.target.closest('#ask-drawer')) {
      event.preventDefault();
      closeAsk();
      return;
    }
    if (event.key !== 'Escape' || app.tab !== 'queue' || event.target.closest('dialog, #account-menu')) return;
    if (app.pane === 'failures' && !isWide()) {
      closeFailPane({ focus: true });
      return;
    }
    if (!sheetOpenFor()) return;
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
  window.matchMedia(WIDE_QUERY).addEventListener('change', () => {
    if (isWide()) {
      byId('desk-view').dataset.view = 'review';
      afterListChange();
    } else if (!sheetOpenFor()) byId('desk-view').dataset.view = app.pane === 'failures' ? 'failures' : 'queue';
    syncPanes();
    measure();
  });
}

// A hosted airline's Desk (/a/<ICAO>/desk, SPEC-FINAL 5.4): the airline header replaces the nav and
// the account button; the member's own session is the Desk session (no PIN, no visitor), and the
// Desk opens only while TEPHRA runs for the airline (shadow or live).
let tenantNow = null;
let tenantOpen = false;
function tenantNote(kids) {
  let note = byId('ah-desk-note');
  if (!kids) { note?.remove(); return; }
  if (!note) {
    note = el('section', { id: 'ah-desk-note', class: 'panel panel--empty ah-desknote', role: 'status' });
    byId('main').prepend(note);
  }
  note.replaceChildren(...kids);
}
function tenantBoot() {
  rewriteLinks(document);
  mountTenantNav({ bar: byId('dhead').querySelector('.dhead__row'), section: 'desk', chips: [byId('ai-status'), byId('ask-btn'), byId('conn')], theme: false });
  // the assistant status (its chip and its (i), moved together), Ask and the connection pill say
  // something only while TEPHRA runs for the airline: in setup, suspended or with no access
  // nothing connects, so they are not shown
  const runningChips = (on) => { for (const id of ['ai-status', 'conn']) byId(id).hidden = !on; if (!on) byId('ask-btn').hidden = true; };
  onTenantHeader(async (h, { error }) => {
    tenantNow = h;
    setTitle();
    if (!h) {
      byId('boot').hidden = true;
      if (error && error !== 'offline') runningChips(false);
      return;
    }
    runningChips(h.state === 'shadow' || h.state === 'live');
    if (h.state !== 'shadow' && h.state !== 'live') {
      byId('boot').hidden = true;
      if (app.me) leaveDesk();
      tenantOpen = false;
      // only an ops manager can finish Go live: everyone else is told who does
      const finish = h.you?.role === 'ops_manager'
        ? el('a', { class: 'linkbtn', href: '/workspace' }, el('span', { text: 'Finish Go live on Your airline' }), icon('i-chevron-right'))
        : el('p', { text: `${h.name}'s ops manager starts it from Your airline.` });
      tenantNote(h.state === 'setup'
        ? [el('p', { class: 'panel__title' }, el('span', { text: `TEPHRA has not started for ${h.name} yet.` })), finish]
        : [el('p', { class: 'panel__title' }, el('span', { text: `TEPHRA is not running for ${h.name}.` })), el('p', { text: 'Its drafts wait until TEPHRA runs for it again.' })]);
      return;
    }
    tenantNote(null);
    if (tenantOpen) return;
    tenantOpen = true;
    loadState();
    loadBudget();
    openEvents();
    const res = await api(PATHS.me);
    byId('boot').hidden = true;
    if (res.ok && isSession(res.data)) enterDesk(res.data, { focus: false });
    else if (res.status === 401) handleUnauthorized();
    else tenantNote([el('p', { class: 'panel__title' }, el('span', { text: `The Desk did not open (HTTP ${res.status}).` }))]);
  });
}

async function boot() {
  await loadSprite();
  wire();
  setConn('idle');
  initTabs(onTab);
  if (TENANT) {
    tenantBoot();
    return;
  }
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
