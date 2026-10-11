// Formatting and the small amount of arithmetic the Desk does (docs/UI-DESIGN.md section 13).
// Every value comes from an API field; nothing here invents a time, a number or a place.

// --- clocks -------------------------------------------------------------------------------

// The active clock is state.now (REPLAY moves it). It ticks locally from performance.now()
// between `state` and `heartbeat` events and is never read from this phone's own clock.
const clock = { base: null, at: 0 };
// Session expiry is on the server's wall clock (server_time), not the replay clock.
let serverOffsetMs = 0;

export function setActiveClock(iso) {
  const t = parseTime(iso);
  if (t === null) return;
  clock.base = t;
  clock.at = performance.now();
}

export function setServerTime(iso) {
  const t = parseTime(iso);
  if (t !== null) serverOffsetMs = t - Date.now();
}

export function activeNow() {
  if (clock.base === null) return null;
  return clock.base + (performance.now() - clock.at);
}

export const serverNow = () => Date.now() + serverOffsetMs;

export function parseTime(iso) {
  const t = typeof iso === 'string' ? Date.parse(iso) : NaN;
  return Number.isFinite(t) ? t : null;
}

const pad2 = (n) => String(n).padStart(2, '0');

export function hhmmz(value) {
  const t = typeof value === 'number' ? value : parseTime(value);
  if (t === null) return '–';
  const d = new Date(t);
  return `${pad2(d.getUTCHours())}${pad2(d.getUTCMinutes())}Z`;
}

// "251120Z": day, hours, minutes, the form aviation text uses.
export function ddhhmmz(value) {
  const t = typeof value === 'number' ? value : parseTime(value);
  if (t === null) return '–';
  const d = new Date(t);
  return `${pad2(d.getUTCDate())}${pad2(d.getUTCHours())}${pad2(d.getUTCMinutes())}Z`;
}

const MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];

export function dayMonthHhmm(value) {
  const t = typeof value === 'number' ? value : parseTime(value);
  if (t === null) return '–';
  const d = new Date(t);
  return `${pad2(d.getUTCDate())} ${MONTHS[d.getUTCMonth()]} ${pad2(d.getUTCHours())}${pad2(d.getUTCMinutes())}Z`;
}

// "27 s", "14 min", "2 h 5 min"
export function span(ms) {
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  return m % 60 ? `${h} h ${m % 60} min` : `${h} h`;
}

export function ago(ms) {
  if (ms < 60000) return 'just now';
  return `${span(ms)} ago`;
}

// --- advisory fields ----------------------------------------------------------------------

export const fl = (n) => `FL${String(Math.round(n)).padStart(3, '0')}`;

// 11.7 action words: "HOLD FL250", "CHANGE LEVEL FL300–FL340", "DIVERT WARR", "MONITOR".
export function actionText(adv) {
  switch (adv.action) {
    case 'CHANGE_LEVEL':
      return Number.isFinite(adv.change_level_fl_min) && Number.isFinite(adv.change_level_fl_max)
        ? `CHANGE LEVEL ${fl(adv.change_level_fl_min)}–${fl(adv.change_level_fl_max)}`
        : 'CHANGE LEVEL';
    case 'HOLD':
      return Number.isFinite(adv.hold_fl) ? `HOLD ${fl(adv.hold_fl)}` : 'HOLD';
    case 'DIVERT':
      return typeof adv.alternate_icao === 'string' && adv.alternate_icao
        ? `DIVERT ${adv.alternate_icao}`
        : 'DIVERT';
    case 'REROUTE': {
      const r = adv.reroute;
      if (!r) return 'REROUTE';
      const side = r.side ? ` ${r.side}` : '';
      const extra = Number.isFinite(r.extra_min) ? ` +${Math.round(r.extra_min)} MIN` : '';
      return `REROUTE${side}${extra}`;
    }
    default:
      return String(adv.action);
  }
}

// Review-sheet phrasing: "HOLD at FL250".
export function actionSentence(adv) {
  if (adv.action === 'HOLD' && Number.isFinite(adv.hold_fl)) return `HOLD at ${fl(adv.hold_fl)}`;
  return actionText(adv);
}

export const ACTION_ICON = {
  HOLD: 'i-hold',
  CHANGE_LEVEL: 'i-levels',
  DIVERT: 'i-airport',
  MONITOR: 'i-eye',
  CONTINUE: 'i-arrow-right',
  REROUTE: 'i-route',
};

export function band(cone) {
  if (!cone) return '';
  const base = Number(cone.base_ft);
  const top = Number(cone.top_ft);
  if (!Number.isFinite(base) || !Number.isFinite(top)) return '';
  const lo = base <= 0 ? 'SFC' : fl(base / 100);
  return `${lo}–${fl(top / 100)}`;
}

export const pct = (x) => (Number.isFinite(x) ? `${Math.round(x * 100)}%` : '');

export const isStub = (adv) => adv.llm_backend === 'stub';

// 11.2 mode words.
export const MODE_SHORT = {
  OFFICIAL: 'TEPHRA area = official',
  WIDENED: 'TEPHRA area widened',
  HYPOTHESIS: 'HYPOTHESIS: MONITOR or HOLD only',
};
export const MODE_SENTENCE = {
  OFFICIAL: 'Same as the official area: TEPHRA adds nothing.',
  WIDENED: "Official area plus the observatory's drift, never smaller.",
  HYPOTHESIS: 'No valid official product: a hypothesis. Only MONITOR or HOLD may be advised.',
};

export function modeLabel(adv) {
  return `${adv.plume_mode} ${pct(adv.confidence)}${isStub(adv) ? ' (NO MODEL)' : ''}`.trim();
}

// Entry instant on the active clock: drafted time plus the drafted minutes to entry.
export function entryAt(adv) {
  const created = parseTime(adv.created_at) ?? 0;
  return adv.inside_now ? created : created + Math.max(0, adv.minutes_to_entry || 0) * 60000;
}

// What the countdown shows now. kind: inside | ahead | due
export function entryState(adv, now) {
  if (adv.inside_now) return { kind: 'inside', minutes: 0 };
  if (now === null) return { kind: 'ahead', minutes: adv.minutes_to_entry };
  const left = Math.ceil((entryAt(adv) - now) / 60000);
  if (left > 0) return { kind: 'ahead', minutes: left };
  return { kind: 'due', minutes: -left };
}

// Queue order (10.3): inside now first, then minutes to entry, then oldest draft first.
export function byUrgency(a, b) {
  return (
    Number(b.inside_now) - Number(a.inside_now) ||
    entryAt(a) - entryAt(b) ||
    (parseTime(a.created_at) ?? 0) - (parseTime(b.created_at) ?? 0)
  );
}

export const deskName = (actor) =>
  typeof actor === 'string' && actor.startsWith('desk:') ? actor.slice(5) : actor || '';

export const FEED_NAMES = {
  sigmet: 'VA SIGMET (AWC)',
  vona: 'VONA (MAGMA)',
  vaac_tokyo: 'VAA Tokyo',
  vaac_darwin: 'VAA Darwin',
  taf: 'TAF',
  metar: 'METAR',
  adsb: 'ADS-B (adsb.lol)',
  winds: 'Winds (Open-Meteo)',
  frames: 'Satellite frames',
  hsd: 'Himawari split window',
};

// Binding products first (SIGMET, then VAA), then the observatory, then context.
const FEED_RANK = { sigmet: 0, vaac_darwin: 1, vaac_tokyo: 1, vona: 2 };
export const bySourceRank = (a, b) => (FEED_RANK[a.feed] ?? 9) - (FEED_RANK[b.feed] ?? 9);

export function initials(name) {
  const parts = String(name || '').trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
