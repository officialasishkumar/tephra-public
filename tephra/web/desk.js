// TEPHRA Desk: the dispatcher's phone view (MODULES.md 5.9 and 8.5).
// Plain DOM, no framework, no inline script (CSP). Feed and model text is only ever
// written with textContent, never parsed as HTML.

const API = {
  me: '/api/desk/me',
  login: '/api/desk/login',
  logout: '/api/desk/logout',
  drafts: '/api/desk/advisories?status=DRAFT&limit=100',
  decide: (id, kind) => `/api/desk/advisories/${encodeURIComponent(id)}/${kind}`,
  state: '/api/state',
  events: '/api/events',
};

const CSRF_HEADER = 'X-Tephra-Desk'; // tephra.api.auth.CSRF_HEADER
const BODY_MAX_CHARS = 400; // tephra.config.ADVISORY_BODY_MAX_CHARS
const REASON_MIN_CHARS = 3; // RejectRequest.reason in tephra/models.py
const REASON_MAX_CHARS = 500;
const ADVISORY_ID = /^adv_[0-9a-f]{12}$/;
const STATUSES = new Set(['DRAFT', 'APPROVED', 'EDITED', 'REJECTED', 'SUPERSEDED']);
const ACTIONS = new Set(['CONTINUE', 'MONITOR', 'CHANGE_LEVEL', 'HOLD', 'DIVERT']);
const NAME_KEY = 'tephra.desk.name';
const NOTICE_LIMIT = 4;
const NOTICE_TTL_MS = 8000;
const AGE_TICK_MS = 15000;
const SSE_RETRY_MS = 5000;
// A second tap on the card button can land on the dialog's submit button.
const GHOST_TAP_MS = 400;
const URGENT_MIN = 15;
const SOON_MIN = 30;

const byId = (id) => document.getElementById(id);

const els = {
  boot: byId('boot'),
  modeBadge: byId('mode-badge'),
  conn: byId('conn-status'),
  disclaimer: byId('disclaimer'),
  airline: byId('airline'),
  modelLabel: byId('model-label'),
  replayBanner: byId('replay-banner'),
  loginView: byId('login-view'),
  loginForm: byId('login-form'),
  loginName: byId('login-name'),
  loginPin: byId('login-pin'),
  loginSubmit: byId('login-submit'),
  loginError: byId('login-error'),
  deskView: byId('desk-view'),
  who: byId('who'),
  logout: byId('logout-btn'),
  title: byId('drafts-title'),
  count: byId('draft-count'),
  refresh: byId('refresh-btn'),
  notices: byId('notices'),
  loading: byId('list-loading'),
  listError: byId('list-error'),
  listErrorText: byId('list-error-text'),
  listRetry: byId('list-retry'),
  empty: byId('empty-state'),
  cards: byId('cards'),
  template: byId('card-template'),
  editBody: byId('edit-body'),
  editCount: byId('edit-count'),
  rejectReason: byId('reject-reason'),
  rejectCount: byId('reject-count'),
  dialogs: {
    approve: byId('approve-dialog'),
    edit: byId('edit-dialog'),
    reject: byId('reject-dialog'),
  },
};

const desk = {
  me: null, // SessionInfo
  advisories: new Map(), // id -> open DRAFT Advisory
  closed: new Map(), // id -> last non-DRAFT Advisory seen, so a stale list cannot revive it
  inFlight: new Set(), // advisory ids with a decision request outstanding
  listLoaded: false,
  listError: null,
  loadSeq: 0,
  clockOffsetMs: 0, // active clock (REPLAY moves it) minus this phone's clock
  mode: 'LIVE',
  events: null,
  eventsDown: false,
  reconnectTimer: null,
  ageTimer: null,
  dialog: null, // { kind, id, seen, opener, openedAt, busy, gone }
};

// --- HTTP ---------------------------------------------------------------------------------

async function api(path, { method = 'GET', body } = {}) {
  const headers = { Accept: 'application/json', [CSRF_HEADER]: '1' };
  const init = { method, headers, credentials: 'same-origin', cache: 'no-store' };
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(path, init);
  } catch {
    return { ok: false, status: 0, data: null, headers: null };
  }
  let data = null;
  if ((response.headers.get('content-type') || '').includes('application/json')) {
    try {
      data = await response.json();
    } catch {
      data = null;
    }
  }
  return { ok: response.ok, status: response.status, data, headers: response.headers };
}

function errorCode(res) {
  return res.data && typeof res.data.error === 'string' ? res.data.error : '';
}

function errorText(res, fallback) {
  if (res.status === 0) return 'Cannot reach TEPHRA. Check the connection and try again.';
  const data = res.data;
  if (data && typeof data.detail === 'string' && data.detail) {
    const problems = Array.isArray(data.problems)
      ? data.problems.filter((p) => typeof p === 'string')
      : [];
    return problems.length ? `${data.detail}: ${problems.join('; ')}` : data.detail;
  }
  return `${fallback} (HTTP ${res.status}).`;
}

// --- validation of data crossing into the page ---------------------------------------------

function isAdvisory(value) {
  return (
    value !== null &&
    typeof value === 'object' &&
    typeof value.id === 'string' &&
    ADVISORY_ID.test(value.id) &&
    Number.isInteger(value.version) &&
    STATUSES.has(value.status) &&
    ACTIONS.has(value.action) &&
    typeof value.proxy_flight === 'string' &&
    typeof value.body === 'string'
  );
}

function isSession(value) {
  return value !== null && typeof value === 'object' && typeof value.name === 'string';
}

function eventData(event) {
  try {
    return JSON.parse(event.data);
  } catch {
    return null;
  }
}

// --- formatting ---------------------------------------------------------------------------

const pad2 = (n) => String(n).padStart(2, '0');

function parseTime(iso) {
  const t = typeof iso === 'string' ? Date.parse(iso) : NaN;
  return Number.isFinite(t) ? t : null;
}

function ddhhmmz(iso) {
  const t = parseTime(iso);
  if (t === null) return 'unknown';
  const d = new Date(t);
  return `${pad2(d.getUTCDate())}${pad2(d.getUTCHours())}${pad2(d.getUTCMinutes())}Z`;
}

function hhmmz(iso) {
  const t = parseTime(iso);
  if (t === null) return 'unknown';
  const d = new Date(t);
  return `${pad2(d.getUTCHours())}${pad2(d.getUTCMinutes())}Z`;
}

function durationText(ms) {
  const minutes = Math.floor(Math.max(0, ms) / 60000);
  if (minutes < 1) return 'under 1 min';
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${pad2(minutes % 60)} min`;
}

function activeNow() {
  return Date.now() + desk.clockOffsetMs;
}

function flightLevel(fl) {
  return `FL${String(Math.round(fl)).padStart(3, '0')}`;
}

function actionText(adv) {
  switch (adv.action) {
    case 'CHANGE_LEVEL':
      return Number.isFinite(adv.change_level_fl_min) && Number.isFinite(adv.change_level_fl_max)
        ? `CHANGE LEVEL ${flightLevel(adv.change_level_fl_min)}-${flightLevel(adv.change_level_fl_max)}`
        : 'CHANGE LEVEL';
    case 'HOLD':
      return Number.isFinite(adv.hold_fl) ? `HOLD ${flightLevel(adv.hold_fl)}` : 'HOLD';
    case 'DIVERT':
      return typeof adv.alternate_icao === 'string' ? `DIVERT ${adv.alternate_icao}` : 'DIVERT';
    default:
      return adv.action;
  }
}

function flightTitle(adv) {
  return `${adv.proxy_flight} - ${actionText(adv)} - version ${adv.version}`;
}

function deciderName(adv) {
  const who = typeof adv.decided_by === 'string' ? adv.decided_by : '';
  return who.startsWith('desk:') ? who.slice(5) : who;
}

function outcomeText(adv) {
  if (adv.status === 'SUPERSEDED') {
    return adv.superseded_by
      ? `${adv.proxy_flight}: draft replaced by a newer draft for the same flight.`
      : `${adv.proxy_flight}: draft withdrawn by TEPHRA.`;
  }
  const who = deciderName(adv);
  return `${adv.proxy_flight}: ${adv.status}${who ? ` by ${who}` : ''}.`;
}

function successText(adv) {
  if (adv.status === 'REJECTED') return `${adv.proxy_flight} rejected. Nothing was queued.`;
  const how = adv.status === 'EDITED' ? 'approved with your edits' : 'approved';
  return `${adv.proxy_flight} ${how} and placed on TEPHRA's outbound queue.`;
}

// Estimated entry instant on the active clock: draft time plus minutes to entry.
function entryAt(adv) {
  const created = parseTime(adv.created_at) ?? 0;
  return adv.inside_now ? created : created + Math.max(0, adv.minutes_to_entry || 0) * 60000;
}

function byUrgency(a, b) {
  return entryAt(a) - entryAt(b) || (parseTime(b.created_at) ?? 0) - (parseTime(a.created_at) ?? 0);
}

// --- notices ------------------------------------------------------------------------------

function notify(text, tone = 'info') {
  const item = document.createElement('li');
  item.className = `notice notice-${tone}`;
  const message = document.createElement('p');
  message.textContent = text;
  const dismiss = document.createElement('button');
  dismiss.type = 'button';
  dismiss.className = 'btn btn-quiet notice-dismiss';
  dismiss.textContent = 'Dismiss';
  dismiss.setAttribute('aria-label', `Dismiss: ${text}`);
  dismiss.addEventListener('click', () => item.remove());
  item.append(message, dismiss);
  els.notices.prepend(item);
  while (els.notices.children.length > NOTICE_LIMIT) els.notices.lastElementChild.remove();
  if (tone !== 'warn') {
    window.setTimeout(() => {
      if (!item.contains(document.activeElement)) item.remove();
    }, NOTICE_TTL_MS);
  }
}

// --- system state (mode, replay banner, disclaimer) ----------------------------------------

function setMode(mode, banner) {
  desk.mode = mode === 'REPLAY' ? 'REPLAY' : 'LIVE';
  els.modeBadge.textContent = desk.mode;
  els.modeBadge.dataset.mode = desk.mode;
  if (desk.mode === 'REPLAY') {
    els.replayBanner.textContent = banner || 'REPLAY: recorded real feeds';
    els.replayBanner.hidden = false;
  } else {
    els.replayBanner.hidden = true;
    els.replayBanner.textContent = '';
  }
}

function syncClock(iso) {
  const t = parseTime(iso);
  if (t !== null) desk.clockOffsetMs = t - Date.now();
}

function applySystemState(state) {
  if (!state || typeof state !== 'object') return;
  setMode(state.mode, state.replay && typeof state.replay.banner === 'string' ? state.replay.banner : '');
  syncClock(state.now);
  if (typeof state.disclaimer === 'string' && state.disclaimer) {
    els.disclaimer.textContent = state.disclaimer;
  }
  const airline = state.airline;
  if (airline && typeof airline.name === 'string' && typeof airline.code === 'string') {
    els.airline.textContent = `${airline.name} (${airline.code}) is a fictional airline.`;
  }
  if (state.llm && typeof state.llm.label === 'string') {
    els.modelLabel.textContent = `Drafts by: ${state.llm.label}`;
  }
  updateAges();
}

async function loadState() {
  const res = await api(API.state);
  if (res.ok) applySystemState(res.data);
}

function applyHeartbeat(beat) {
  if (!beat || typeof beat !== 'object') return;
  syncClock(beat.now);
  const mode = beat.mode === 'REPLAY' ? 'REPLAY' : 'LIVE';
  // The heartbeat carries no banner text; fetch the full state when the mode flips.
  if (mode !== desk.mode) loadState();
  updateAges();
}

// --- views --------------------------------------------------------------------------------

function showLogin(message = '') {
  els.boot.hidden = true;
  els.deskView.hidden = true;
  els.loginView.hidden = false;
  setConn('idle');
  showLoginError(message);
  (els.loginName.value ? els.loginPin : els.loginName).focus();
}

function showLoginError(message) {
  els.loginError.textContent = message;
  els.loginError.hidden = !message;
}

function enterDesk(session, { focus = true } = {}) {
  desk.me = session;
  els.boot.hidden = true;
  els.loginView.hidden = true;
  els.deskView.hidden = false;
  els.who.textContent = `Signed in as ${session.name}`;
  desk.listLoaded = false;
  desk.listError = null;
  renderList();
  loadDrafts();
  openEvents();
  window.clearInterval(desk.ageTimer);
  desk.ageTimer = window.setInterval(updateAges, AGE_TICK_MS);
  if (focus) els.title.focus();
}

function leaveDesk() {
  closeDialog({ restoreFocus: false });
  closeEvents();
  window.clearInterval(desk.ageTimer);
  desk.ageTimer = null;
  desk.me = null;
  desk.advisories.clear();
  desk.closed.clear();
  desk.inFlight.clear();
  desk.listLoaded = false;
  desk.listError = null;
  desk.loadSeq += 1;
  els.refresh.disabled = false;
  els.refresh.textContent = 'Refresh';
  els.cards.replaceChildren();
  els.notices.replaceChildren();
  document.title = 'TEPHRA Desk';
}

function handleUnauthorized() {
  leaveDesk();
  showLogin('Your desk session has ended. Sign in again.');
}

// --- login and logout ---------------------------------------------------------------------

async function onLogin(event) {
  event.preventDefault();
  const name = els.loginName.value.trim().replace(/\s+/g, ' ');
  const pin = els.loginPin.value;
  if (name.length < 2 || name.length > 32) {
    showLoginError('Enter your name or initials (2 to 32 characters).');
    els.loginName.focus();
    return;
  }
  if (!pin) {
    showLoginError('Enter the desk PIN.');
    els.loginPin.focus();
    return;
  }
  showLoginError('');
  els.loginSubmit.disabled = true;
  els.loginSubmit.textContent = 'Signing in...';
  const res = await api(API.login, { method: 'POST', body: { pin, name } });
  els.loginPin.value = '';
  els.loginSubmit.disabled = false;
  els.loginSubmit.textContent = 'Sign in';
  if (res.ok && isSession(res.data)) {
    try {
      localStorage.setItem(NAME_KEY, res.data.name);
    } catch {
      // Remembering the name is a convenience only.
    }
    enterDesk(res.data);
    loadState();
    return;
  }
  showLoginError(loginErrorText(res));
  els.loginPin.focus();
}

function loginErrorText(res) {
  const code = errorCode(res);
  if (code === 'bad_pin') return 'Wrong PIN. Repeated failures lock sign-in for a few minutes.';
  if (code === 'too_many_attempts') {
    const seconds = Number(res.headers && res.headers.get('retry-after'));
    const wait = Number.isFinite(seconds) && seconds > 0 ? ` in ${Math.ceil(seconds / 60)} min` : ' later';
    return `Too many failed attempts. Try again${wait}.`;
  }
  if (code === 'desk_disabled') return 'The desk is switched off on this server (no desk PIN is set).';
  return errorText(res, 'Sign-in failed');
}

async function onLogout() {
  els.logout.disabled = true;
  await api(API.logout, { method: 'POST' });
  els.logout.disabled = false;
  leaveDesk();
  showLogin('Signed out.');
}

// --- the draft list -----------------------------------------------------------------------

async function loadDrafts() {
  const seq = ++desk.loadSeq;
  els.refresh.disabled = true;
  els.refresh.textContent = 'Refreshing...';
  const res = await api(API.drafts);
  if (seq !== desk.loadSeq) return false;
  els.refresh.disabled = false;
  els.refresh.textContent = 'Refresh';
  if (res.status === 401) {
    handleUnauthorized();
    return false;
  }
  if (!res.ok || !res.data || !Array.isArray(res.data.advisories)) {
    desk.listError = desk.listLoaded
      ? `${errorText(res, 'Could not refresh the drafts')} Showing the last list loaded.`
      : errorText(res, 'Could not load the drafts');
    renderList();
    return false;
  }
  const fresh = new Map();
  for (const adv of res.data.advisories) {
    if (!isAdvisory(adv) || adv.status !== 'DRAFT') continue;
    const closed = desk.closed.get(adv.id);
    if (closed && closed.version >= adv.version) continue;
    const known = desk.advisories.get(adv.id);
    fresh.set(adv.id, known && known.version > adv.version ? known : adv);
  }
  desk.advisories = fresh;
  desk.listLoaded = true;
  desk.listError = null;
  renderList();
  syncDialog();
  return true;
}

function applyAdvisory(adv, { announce }) {
  if (!isAdvisory(adv)) return;
  const known = desk.advisories.get(adv.id);
  if (known && known.version > adv.version) return;
  const closed = desk.closed.get(adv.id);
  if (closed && closed.version >= adv.version) return;
  if (adv.status === 'DRAFT') {
    desk.advisories.set(adv.id, adv);
    if (!known && announce) notify(`New draft: ${adv.proxy_flight} ${actionText(adv)}.`, 'info');
  } else {
    desk.closed.set(adv.id, adv);
    desk.advisories.delete(adv.id);
    if (known && announce && !desk.inFlight.has(adv.id)) {
      notify(outcomeText(adv), adv.status === 'SUPERSEDED' ? 'info' : 'warn');
    }
  }
  renderList();
  syncDialog();
}

function renderList() {
  const items = [...desk.advisories.values()].sort(byUrgency);
  const n = items.length;
  els.count.textContent = desk.listLoaded ? `${n} draft${n === 1 ? '' : 's'} waiting` : '';
  document.title = n ? `(${n}) TEPHRA Desk` : 'TEPHRA Desk';
  els.loading.hidden = desk.listLoaded || Boolean(desk.listError);
  els.listError.hidden = !desk.listError;
  els.listErrorText.textContent = desk.listError || '';
  els.empty.hidden = !(desk.listLoaded && !desk.listError && n === 0);

  const wanted = new Set(items.map((adv) => adv.id));
  for (const li of [...els.cards.children]) {
    if (!wanted.has(li.dataset.id)) li.remove();
  }
  items.forEach((adv, index) => {
    let li = els.cards.querySelector(`li[data-id="${CSS.escape(adv.id)}"]`);
    if (!li || Number(li.dataset.version) !== adv.version) {
      const card = buildCard(adv);
      if (li) li.replaceWith(card);
      li = card;
    }
    const at = els.cards.children[index];
    if (at !== li) els.cards.insertBefore(li, at || null);
  });
  updateAges();
}

function buildCard(adv) {
  const li = els.template.content.firstElementChild.cloneNode(true);
  li.dataset.id = adv.id;
  li.dataset.version = String(adv.version);
  const field = (name) => li.querySelector(`[data-f="${name}"]`);

  const titleId = `title-${adv.id}`;
  field('flight').id = titleId;
  field('flight').textContent = adv.proxy_flight;
  li.querySelector('article').setAttribute('aria-labelledby', titleId);

  const callsign = typeof adv.callsign === 'string' && adv.callsign.trim() ? adv.callsign.trim() : 'no callsign';
  const ident = [`Proxy for ADS-B ${callsign}`, `hex ${String(adv.hex || '').toUpperCase()}`];
  if (adv.type_icao) ident.push(String(adv.type_icao));
  field('ident').textContent = ident.join(' - ');

  field('replay').hidden = !adv.replay;
  field('model').textContent = adv.llm_backend === 'stub' ? 'NO MODEL' : `AI-drafted - ${adv.model_id || 'model'}`;
  field('model').classList.toggle('tag-nomodel', adv.llm_backend === 'stub');
  field('version').textContent = `v${adv.version}`;

  const action = field('action');
  action.textContent = actionText(adv);
  action.classList.add(`action-${adv.action.toLowerCase()}`);

  field('entry').textContent = adv.inside_now
    ? 'Inside the cone at drafting'
    : `${adv.minutes_to_entry} min after drafting`;
  field('volcano').textContent = adv.volcano_name || adv.volcano_id || 'unknown';
  field('cone').textContent = coneText(adv);
  field('fuel').textContent = adv.fuel_line || 'No fuel cost for this action';
  field('cost').textContent = adv.cost_note || '';
  field('cost').hidden = !adv.cost_note;
  field('body').textContent = adv.body;
  field('header').textContent = adv.header || '';

  const notes = Array.isArray(adv.validation_notes) ? adv.validation_notes.filter((n) => typeof n === 'string') : [];
  field('notes').hidden = notes.length === 0;
  field('notes-list').replaceChildren(...notes.map(textItem));

  const sources = Array.isArray(adv.sources) ? adv.sources : [];
  field('sources-summary').textContent = `Sources (${sources.length}) with issue times and hashes`;
  field('sources').replaceChildren(...sources.map(sourceItem));

  for (const button of li.querySelectorAll('[data-action]')) {
    const verb = { approve: 'Approve', edit: 'Edit', reject: 'Reject' }[button.dataset.action];
    button.setAttribute('aria-label', `${verb} ${adv.proxy_flight} ${actionText(adv)}`);
  }
  return li;
}

function coneText(adv) {
  const pct = Number.isFinite(adv.confidence) ? `${Math.round(adv.confidence * 100)}%` : '';
  const base = `${adv.plume_mode || 'UNKNOWN'} ${pct}`.trim();
  return adv.plume_mode === 'HYPOTHESIS'
    ? `${base} - no valid official polygon; only MONITOR or HOLD may be advised`
    : base;
}

function textItem(text) {
  const li = document.createElement('li');
  li.textContent = text;
  return li;
}

function sourceItem(src) {
  const li = document.createElement('li');
  li.className = 'source';
  if (!src || typeof src !== 'object') {
    li.textContent = 'Unreadable source entry';
    return li;
  }
  const head = document.createElement('p');
  head.className = 'source-head';
  const feed = document.createElement('span');
  feed.className = 'tag';
  feed.textContent = String(src.feed || '').toUpperCase();
  const id = document.createElement('span');
  id.className = 'mono source-id';
  id.textContent = String(src.source_id || '');
  head.append(feed, ' ', id);
  if (src.stale) {
    const stale = document.createElement('span');
    stale.className = 'tag tag-stale';
    stale.textContent = 'STALE';
    head.append(' ', stale);
  }
  const times = document.createElement('p');
  times.className = 'mono source-times';
  const issued = src.issued_at ? ddhhmmz(src.issued_at) : 'not stated';
  times.textContent = `ISSUED ${issued} - FETCHED ${ddhhmmz(src.fetched_at)} - #${src.sha256_short || ''}`;
  li.append(head, times);
  if (typeof src.url === 'string' && /^https:\/\//i.test(src.url)) {
    const link = document.createElement('a');
    link.href = src.url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.className = 'source-link';
    link.textContent = 'Open the public source';
    li.append(link);
  }
  return li;
}

function updateAges() {
  const now = activeNow();
  for (const li of els.cards.children) {
    const adv = desk.advisories.get(li.dataset.id);
    if (!adv) continue;
    const created = parseTime(adv.created_at);
    const age = li.querySelector('[data-f="age"]');
    age.textContent = created === null ? 'unknown' : `${hhmmz(adv.created_at)}, ${durationText(now - created)} ago`;

    const left = li.querySelector('[data-f="entry-left"]');
    const urgency = li.querySelector('[data-f="urgency"]');
    const minutesLeft = Math.floor((entryAt(adv) - now) / 60000);
    let level = 'later';
    if (adv.inside_now) {
      left.textContent = '';
      urgency.textContent = 'INSIDE AT DRAFT';
      level = 'urgent';
    } else if (minutesLeft >= 0) {
      left.textContent = `(about ${minutesLeft} min from now if track and level held)`;
      urgency.textContent = `ENTRY ~${minutesLeft} MIN`;
      if (minutesLeft <= URGENT_MIN) level = 'urgent';
      else if (minutesLeft <= SOON_MIN) level = 'soon';
    } else {
      left.textContent = '(expected entry time has passed; check the live position)';
      urgency.textContent = 'ENTRY PASSED';
      level = 'urgent';
    }
    urgency.dataset.level = level;
    li.dataset.level = level;
  }
}

// --- Server-Sent Events -------------------------------------------------------------------

function setConn(conn) {
  const labels = { idle: 'Offline', connecting: 'Connecting', live: 'Live updates', down: 'Updates paused' };
  els.conn.dataset.conn = conn;
  els.conn.textContent = labels[conn];
}

function openEvents() {
  closeEvents();
  const source = new EventSource(API.events);
  desk.events = source;
  setConn('connecting');
  source.addEventListener('open', () => {
    setConn('live');
    if (desk.eventsDown) {
      desk.eventsDown = false;
      loadDrafts();
      loadState();
    }
  });
  source.addEventListener('error', () => {
    desk.eventsDown = true;
    setConn('down');
    // EventSource retries by itself unless the server answered with an error status.
    if (source.readyState === EventSource.CLOSED) scheduleReconnect();
  });
  source.addEventListener('advisory', (event) => applyAdvisory(eventData(event), { announce: true }));
  source.addEventListener('state', (event) => applySystemState(eventData(event)));
  source.addEventListener('heartbeat', (event) => applyHeartbeat(eventData(event)));
}

function closeEvents() {
  window.clearTimeout(desk.reconnectTimer);
  desk.reconnectTimer = null;
  if (desk.events) desk.events.close();
  desk.events = null;
  desk.eventsDown = false;
}

function scheduleReconnect() {
  window.clearTimeout(desk.reconnectTimer);
  desk.reconnectTimer = window.setTimeout(() => {
    if (!desk.me) return;
    openEvents();
    desk.eventsDown = true; // refetch the list once the new stream opens
  }, SSE_RETRY_MS);
}

// --- decision dialogs ---------------------------------------------------------------------

function dialogPart(kind, name) {
  return els.dialogs[kind].querySelector(`[data-d="${name}"]`);
}

function openDecision(kind, id, opener) {
  const adv = desk.advisories.get(id);
  if (!adv || desk.dialog) return;
  desk.dialog = { kind, id, seen: adv, opener, openedAt: Date.now(), busy: false, gone: false };
  setDialogMessage('conflict', '');
  setDialogMessage('error', '');
  const submit = dialogPart(kind, 'submit');
  submit.hidden = false;
  submit.disabled = false;
  submit.textContent = submit.dataset.label;
  const cancel = dialogPart(kind, 'cancel');
  cancel.disabled = false;
  cancel.textContent = 'Cancel';
  fillDialog();
  if (kind === 'edit') {
    els.editBody.value = adv.edited_body ?? adv.body;
    updateEditCounter();
  } else if (kind === 'reject') {
    els.rejectReason.value = '';
    updateReasonCounter();
  }
  els.dialogs[kind].showModal();
  if (kind === 'edit') els.editBody.focus();
  else if (kind === 'reject') els.rejectReason.focus();
  else dialogPart(kind, 'cancel').focus();
}

function fillDialog() {
  const { kind, seen } = desk.dialog;
  dialogPart(kind, 'flight').textContent = flightTitle(seen);
  const body = dialogPart(kind, 'body');
  if (body) body.textContent = seen.body;
  const fuel = dialogPart(kind, 'fuel');
  if (fuel) fuel.textContent = seen.fuel_line || 'No fuel cost for this action';
  if (kind === 'edit') updateEditCounter();
}

function setDialogMessage(name, text) {
  if (!desk.dialog) return;
  const part = dialogPart(desk.dialog.kind, name);
  part.textContent = text;
  part.hidden = !text;
}

function setDialogBusy(busy) {
  const d = desk.dialog;
  d.busy = busy;
  const submit = dialogPart(d.kind, 'submit');
  const cancel = dialogPart(d.kind, 'cancel');
  cancel.disabled = busy;
  if (busy) {
    submit.disabled = true;
    submit.textContent = 'Sending...';
  } else {
    submit.textContent = submit.dataset.label;
    submit.disabled = false;
    if (d.kind === 'edit') updateEditCounter();
    if (d.kind === 'reject') updateReasonCounter();
  }
}

// The draft left DRAFT before this dialog's decision was applied: only Close remains.
function markDialogGone(message) {
  const d = desk.dialog;
  d.gone = true;
  setDialogMessage('conflict', message);
  setDialogMessage('error', '');
  dialogPart(d.kind, 'submit').hidden = true;
  const cancel = dialogPart(d.kind, 'cancel');
  cancel.disabled = false;
  cancel.textContent = 'Close';
  cancel.focus();
}

function closeDialog({ restoreFocus = true } = {}) {
  const d = desk.dialog;
  if (!d) return;
  desk.dialog = null;
  const dialog = els.dialogs[d.kind];
  if (dialog.open) dialog.close();
  if (!restoreFocus) return;
  if (d.opener && d.opener.isConnected) d.opener.focus();
  else els.title.focus();
}

// Called after every list change: tells the dispatcher if the open draft moved under them.
function syncDialog() {
  const d = desk.dialog;
  if (!d || d.busy || d.gone) return;
  const latest = desk.advisories.get(d.id);
  if (!latest) {
    const closed = desk.closed.get(d.id);
    markDialogGone(
      closed
        ? `${outcomeText(closed)} This draft is no longer open, so your decision cannot be applied.`
        : 'This draft is no longer open, so your decision cannot be applied.',
    );
    return;
  }
  if (latest.version !== d.seen.version) {
    const before = d.seen.version;
    d.seen = latest;
    fillDialog();
    setDialogMessage(
      'conflict',
      `This draft changed while open (version ${before} to ${latest.version}). Review it before deciding.`,
    );
  }
}

function normalizedEdit() {
  return els.editBody.value.trim().toUpperCase();
}

function editProblem() {
  const text = normalizedEdit();
  if (!text) return 'The advisory text cannot be empty.';
  if (text.length > BODY_MAX_CHARS) return `Shorten the text to ${BODY_MAX_CHARS} characters or fewer.`;
  if (desk.dialog && text === desk.dialog.seen.body.trim().toUpperCase()) {
    return 'The text is unchanged. Use Approve instead.';
  }
  return '';
}

function updateEditCounter() {
  const length = normalizedEdit().length;
  const problem = editProblem();
  els.editCount.textContent = `${length} / ${BODY_MAX_CHARS} characters${problem ? ` - ${problem}` : ''}`;
  els.editCount.classList.toggle('counter-bad', Boolean(problem));
  if (desk.dialog && desk.dialog.kind === 'edit' && !desk.dialog.busy) {
    dialogPart('edit', 'submit').disabled = Boolean(problem);
  }
}

function onEditInput(event) {
  const area = els.editBody;
  // Rewriting the value mid-composition would break IME input.
  if (!event.isComposing) {
    const upper = area.value.toUpperCase();
    if (upper !== area.value) {
      const { selectionStart, selectionEnd } = area;
      area.value = upper;
      area.setSelectionRange(selectionStart, selectionEnd);
    }
  }
  updateEditCounter();
}

function updateReasonCounter() {
  const length = els.rejectReason.value.trim().length;
  const short = length < REASON_MIN_CHARS;
  els.rejectCount.textContent = short
    ? `${length} / ${REASON_MAX_CHARS} characters - at least ${REASON_MIN_CHARS} needed`
    : `${length} / ${REASON_MAX_CHARS} characters`;
  els.rejectCount.classList.toggle('counter-bad', short);
  if (desk.dialog && desk.dialog.kind === 'reject' && !desk.dialog.busy) {
    dialogPart('reject', 'submit').disabled = short;
  }
}

function requestBody(d) {
  if (d.kind === 'approve') return { version: d.seen.version };
  if (d.kind === 'edit') return { version: d.seen.version, body: normalizedEdit() };
  return { version: d.seen.version, reason: els.rejectReason.value.trim() };
}

async function onDecisionSubmit(event) {
  event.preventDefault();
  const d = desk.dialog;
  if (!d || d.busy || Date.now() - d.openedAt < GHOST_TAP_MS) return;
  if (d.gone) {
    closeDialog();
    return;
  }
  const problem = d.kind === 'edit' ? editProblem() : '';
  if (problem) {
    setDialogMessage('error', problem);
    return;
  }
  if (d.kind === 'reject' && els.rejectReason.value.trim().length < REASON_MIN_CHARS) {
    setDialogMessage('error', `Give a reason of at least ${REASON_MIN_CHARS} characters.`);
    return;
  }
  setDialogMessage('error', '');
  setDialogBusy(true);
  desk.inFlight.add(d.id);
  const res = await api(API.decide(d.id, d.kind), { method: 'POST', body: requestBody(d) });
  desk.inFlight.delete(d.id);
  const stillOpen = desk.dialog === d;
  if (stillOpen) setDialogBusy(false);

  if (res.ok && isAdvisory(res.data)) {
    // Close first: removing the card would otherwise read as "decided elsewhere".
    if (stillOpen) closeDialog({ restoreFocus: false });
    applyAdvisory(res.data, { announce: false });
    notify(successText(res.data), 'ok');
    if (stillOpen) els.title.focus();
    return;
  }
  if (res.status === 401) {
    if (desk.me) handleUnauthorized();
    return;
  }
  if (!stillOpen) {
    if (desk.me) {
      notify(`${d.seen.proxy_flight}: ${errorText(res, 'the decision was not saved')}`, 'warn');
      loadDrafts();
    }
    return;
  }
  if (res.status === 409) {
    await handleConflict(d, res);
    return;
  }
  if (res.status === 404) {
    desk.advisories.delete(d.id);
    renderList();
    markDialogGone('This advisory no longer exists. Your decision was not applied.');
    loadDrafts();
    return;
  }
  setDialogMessage('error', errorText(res, 'The decision was not saved'));
}

async function handleConflict(d, res) {
  const before = d.seen.version;
  const current = res.data && isAdvisory(res.data.current) ? res.data.current : null;
  if (current) applyAdvisory(current, { announce: false });
  await loadDrafts();
  if (desk.dialog !== d) return;
  const latest = desk.advisories.get(d.id);
  if (latest && !d.gone) {
    d.seen = latest;
    fillDialog();
    setDialogMessage(
      'conflict',
      `Not applied: this draft changed while you were deciding (version ${before} to ${latest.version}). ` +
        'Review the current version below and decide again.',
    );
    notify(`${latest.proxy_flight}: draft changed before your decision. Decide again.`, 'warn');
    return;
  }
  const outcome = current ? outcomeText(current) : 'This draft is no longer open.';
  if (!d.gone) markDialogGone(`${outcome} Your decision was not applied.`);
  notify(`${outcome} Your decision was not applied.`, 'warn');
}

// --- wiring -------------------------------------------------------------------------------

function wire() {
  els.loginForm.addEventListener('submit', onLogin);
  els.logout.addEventListener('click', onLogout);
  els.refresh.addEventListener('click', () => loadDrafts());
  els.listRetry.addEventListener('click', () => loadDrafts());
  els.cards.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-action]');
    if (!button) return;
    const card = button.closest('li[data-id]');
    if (card) openDecision(button.dataset.action, card.dataset.id, button);
  });
  els.editBody.addEventListener('input', onEditInput);
  els.rejectReason.addEventListener('input', updateReasonCounter);
  for (const [kind, dialog] of Object.entries(els.dialogs)) {
    const submit = dialogPart(kind, 'submit');
    submit.dataset.label = submit.textContent;
    dialog.querySelector('form').addEventListener('submit', onDecisionSubmit);
    dialogPart(kind, 'cancel').addEventListener('click', () => closeDialog());
    dialog.addEventListener('cancel', (event) => {
      event.preventDefault();
      if (desk.dialog && !desk.dialog.busy) closeDialog();
    });
    // Some browsers close a modal on a repeated Escape despite preventDefault.
    dialog.addEventListener('close', () => {
      if (!desk.dialog || desk.dialog.kind !== kind) return;
      const { opener } = desk.dialog;
      desk.dialog = null;
      if (opener && opener.isConnected) opener.focus();
    });
  }
  // Phones suspend background tabs; catch up when the Desk is looked at again.
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState !== 'visible' || !desk.me) return;
    loadDrafts();
    if (!desk.events || desk.events.readyState === EventSource.CLOSED) openEvents();
  });
}

async function boot() {
  wire();
  try {
    const saved = localStorage.getItem(NAME_KEY);
    if (saved) els.loginName.value = saved;
  } catch {
    // Storage can be blocked; the name field simply starts empty.
  }
  loadState();
  const res = await api(API.me);
  if (res.ok && isSession(res.data)) enterDesk(res.data, { focus: false });
  else if (res.status === 0) showLogin('Cannot reach TEPHRA. Check the connection and reload.');
  else showLogin();
}

boot();
