// HTTP for the Desk (MODULES.md 8.2 and 8.5). Every request sends X-Tephra-Desk: 1 and JSON
// bodies; a network failure resolves to { status: 0 } so callers never see an exception.

export const PATHS = {
  state: '/api/state',
  wall: '/api/wall',
  events: '/api/events',
  me: '/api/desk/me',
  login: '/api/desk/login',
  logout: '/api/desk/logout',
  drafts: '/api/desk/advisories?status=DRAFT&limit=100',
  decide: (id, kind) => `/api/desk/advisories/${encodeURIComponent(id)}/${kind}`,
  audit: (id) => `/api/audit?advisory_id=${encodeURIComponent(id)}&limit=50`,
  replays: '/api/replays',
  mode: '/api/mode',
  budget: '/api/budget',
  failures: '/api/desk/ai-failures?open_only=true&limit=50',
  failureHandled: (id) => `/api/desk/ai-failures/${encodeURIComponent(id)}/handled`,
  messages: (status = 'DRAFT') => `/api/desk/messages?status=${status}&limit=50`,
  messageDraft: '/api/desk/messages/draft',
  messageDecide: (id, kind) => `/api/desk/messages/${encodeURIComponent(id)}/${kind}`,
  notices: '/api/notices?limit=20',
  noticePost: '/api/desk/notices',
  ask: '/api/desk/ask',
  askVoice: '/api/desk/ask/voice',
  askSpeak: '/api/desk/ask/speak',
  duty: '/api/duty?limit=1',
  recovery: '/api/recovery?limit=10',
  recoveryRun: '/api/desk/recovery/run',
  recoveryDecide: (id, kind) => `/api/desk/recovery/${encodeURIComponent(id)}/${kind}`,
  docs: '/api/docs?limit=50',
  doc: (id) => `/api/docs/${encodeURIComponent(id)}`,
  docSra: '/api/desk/docs/sra',
  docVar: '/api/desk/docs/var',
  docSign: (id) => `/api/desk/docs/${encodeURIComponent(id)}/sign`,
  handover: '/api/desk/handover',
  handovers: '/api/desk/handovers?limit=1',
  handoverGet: (id) => `/api/desk/handover/${encodeURIComponent(id)}`,
  handoverAck: (id) => `/api/desk/handover/${encodeURIComponent(id)}/ack`,
  crewReports: '/api/desk/crew-reports',
  crewFix: '/api/desk/crew-reports/fix',
  crewWithdraw: (id) => `/api/desk/crew-reports/${encodeURIComponent(id)}/withdraw`,
  crewVar: (id) => `/api/desk/crew-reports/${encodeURIComponent(id)}/var`,
};

export const BODY_MAX_CHARS = 400; // tephra.config.ADVISORY_BODY_MAX_CHARS
export const BODY_CAUTION_CHARS = 380;
export const REASON_MIN_CHARS = 3; // RejectRequest.reason
export const REASON_MAX_CHARS = 500;
const ADVISORY_ID = /^adv_[0-9a-f]{12}$/;
const STATUSES = new Set(['DRAFT', 'APPROVED', 'EDITED', 'REJECTED', 'SUPERSEDED']);
const ACTIONS = new Set(['CONTINUE', 'MONITOR', 'CHANGE_LEVEL', 'HOLD', 'DIVERT', 'REROUTE']);
const MODES = new Set(['OFFICIAL', 'WIDENED', 'HYPOTHESIS']);

const listeners = new Set();
// Called with true after a network failure and false after any answer from the server.
export const onReachability = (fn) => listeners.add(fn);

// `form` sends multipart (the browser sets the boundary); `signal` lets the caller stop
// waiting; `blob` returns the body as a Blob when the answer is not JSON (spoken answers).
export async function api(path, { method = 'GET', body, form, signal, blob = false } = {}) {
  const headers = { Accept: blob ? 'audio/wav, application/json' : 'application/json', 'X-Tephra-Desk': '1' };
  const init = { method, headers, credentials: 'same-origin', cache: 'no-store', signal };
  if (form !== undefined) {
    init.body = form;
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(path, init);
  } catch (error) {
    if (error && error.name === 'AbortError') return { ok: false, status: 0, aborted: true, data: null, headers: null };
    for (const fn of listeners) fn(true);
    return { ok: false, status: 0, data: null, headers: null };
  }
  for (const fn of listeners) fn(false);
  let data = null;
  if (blob && response.ok && !(response.headers.get('content-type') || '').includes('application/json')) {
    try {
      data = await response.blob();
    } catch {
      data = null;
    }
  } else if ((response.headers.get('content-type') || '').includes('application/json')) {
    try {
      data = await response.json();
    } catch {
      data = null;
    }
  }
  return { ok: response.ok, status: response.status, data, headers: response.headers };
}

export const errorCode = (res) =>
  res && res.data && typeof res.data.error === 'string' ? res.data.error : '';

// The 503 every AI step answers when its model failed (docs/EXTENSIONS.md rule 0). The reason
// is the server's text; nothing is substituted.
export const isUnavailable = (res) => Boolean(res) && res.status === 503 && errorCode(res) === 'ai_unavailable';

export function unavailableReason(res) {
  const raw = res && res.data ? String(res.data.message || res.data.detail || '') : '';
  return raw.replace(/^AI UNAVAILABLE:?\s*/i, '').trim() || 'no reason given';
}

export function problems(res) {
  const list = res && res.data && Array.isArray(res.data.problems) ? res.data.problems : [];
  return list.filter((p) => typeof p === 'string');
}

export function retryAfterS(res) {
  const n = Number(res && res.headers && res.headers.get('retry-after'));
  return Number.isFinite(n) && n > 0 ? Math.ceil(n) : 0;
}

// Data crossing into the page is checked before it is shown.
export function isAdvisory(v) {
  return (
    v !== null &&
    typeof v === 'object' &&
    typeof v.id === 'string' &&
    ADVISORY_ID.test(v.id) &&
    Number.isInteger(v.version) &&
    STATUSES.has(v.status) &&
    ACTIONS.has(v.action) &&
    MODES.has(v.plume_mode) &&
    typeof v.proxy_flight === 'string' &&
    typeof v.body === 'string' &&
    typeof v.created_at === 'string'
  );
}

export const isSession = (v) =>
  v !== null && typeof v === 'object' && typeof v.name === 'string' && typeof v.expires_at === 'string';

export function parseEvent(event) {
  try {
    return JSON.parse(event.data);
  } catch {
    return null;
  }
}
