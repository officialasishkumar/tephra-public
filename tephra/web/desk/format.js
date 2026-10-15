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

// Act-by (Desk redesign 5.2): the instant code says a dispatcher must decide by. A flight heading
// in: its entry. A flight inside now whose draft changes it (HOLD, CHANGE_LEVEL, REROUTE, DIVERT):
// the draft's own time (act now). A flight inside now told to keep watching or continue: no
// act-by (null); those wait in the Keep watching group.
export const watchOnly = (adv) => Boolean(adv.inside_now) && (adv.action === 'MONITOR' || adv.action === 'CONTINUE');

export function actBy(adv) {
  if (watchOnly(adv)) return null;
  return adv.inside_now ? parseTime(adv.created_at) ?? 0 : entryAt(adv);
}

// The Decide order and the review's "Next": act-by first (ties: the older draft), then the
// Keep watching drafts, inside longest first. Code sets this order; the Coordinator's order is
// only a note.
export function byActBy(a, b) {
  const ka = actBy(a);
  const kb = actBy(b);
  if ((ka === null) !== (kb === null)) return ka === null ? 1 : -1;
  return (ka === null ? 0 : ka - kb) || (parseTime(a.created_at) ?? 0) - (parseTime(b.created_at) ?? 0);
}

// Kept for callers of the old name; the inside-first rule is gone (Desk redesign 5.2).
export const byUrgency = byActBy;

// The time cell at the right of a row (5.2): { text, soon }. "soon" (10 min or less) is the
// caution tone, always with its words.
export function timeCell(adv, now) {
  if (watchOnly(adv)) return { text: 'inside', soon: false };
  if (adv.inside_now) return { text: 'now', soon: true };
  const st = entryState(adv, now);
  if (st.kind === 'due') return { text: 'now', soon: true };
  return { text: `${st.minutes} min`, soon: st.minutes <= 10 };
}

export const deskName = (actor) =>
  typeof actor === 'string' && actor.startsWith('desk:') ? actor.slice(5) : actor || '';

// How a session signs its decisions: a dispatcher by name, a visitor as visitor:<name>, the
// actor the public record shows (SPEC 5.1).
export const sessionLabel = (me) => (me && me.role === 'visitor' ? `visitor:${me.name}` : (me && me.name) || '');

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

export const isBindingFeed = (feed) => feed === 'sigmet' || String(feed).startsWith('vaac');

// A source's own time: when it was issued, or when TEPHRA fetched it if no issue time is stated.
// `kind` says which, so the age is never shown as an issue age when it is a fetch age.
export function sourceTime(s) {
  const issued = parseTime(s.issued_at);
  if (issued !== null) return { t: issued, kind: 'issued' };
  const fetched = parseTime(s.fetched_at);
  return fetched === null ? null : { t: fetched, kind: 'fetched' };
}

export const sourceList = (adv) =>
  [...(adv.sources || [])].filter((s) => s && typeof s === 'object').sort(bySourceRank);

// "7 sources · newest 3 min ago" for the Next decision card and the review (UI-REDESIGN R10.4);
// ages on the active clock. The oldest age stays in the Why list, on each named source.
export function sourcesSummary(adv, now) {
  const list = sourceList(adv);
  if (!list.length) return 'No sources listed';
  // Scope stated (review 2, item 3): every product this draft used, the official ones counted
  // apart. The Wall's sources section shows the newest of each kind, so it names kinds instead.
  const official = list.filter((s) => isBindingFeed(s.feed)).length;
  const head = `${list.length} source${list.length === 1 ? '' : 's'} on this draft (${official} official)`;
  const times = list.map(sourceTime).filter(Boolean).map((x) => x.t);
  if (!times.length) return head;
  const newest = Math.max(...times);
  return now === null ? `${head} · newest ${hhmmz(newest)}` : `${head} · newest ${ago(now - newest)}`;
}

// --- plain words (UI-REDESIGN R12.10): the plain action first, the ICAO word in brackets ---------

// "Keep watching", "Hold at FL250", "Divert to WARR", "Change level to FL300–FL340".
export function actionShort(adv) {
  switch (adv.action) {
    case 'MONITOR':
      return 'Keep watching';
    case 'CONTINUE':
      return 'Continue as planned';
    case 'HOLD':
      return Number.isFinite(adv.hold_fl) ? `Hold at ${fl(adv.hold_fl)}` : 'Hold';
    case 'DIVERT':
      return typeof adv.alternate_icao === 'string' && adv.alternate_icao ? `Divert to ${adv.alternate_icao}` : 'Divert';
    case 'CHANGE_LEVEL':
      return Number.isFinite(adv.change_level_fl_min) && Number.isFinite(adv.change_level_fl_max)
        ? `Change level to ${fl(adv.change_level_fl_min)}–${fl(adv.change_level_fl_max)}`
        : 'Change level';
    case 'REROUTE': {
      const r = adv.reroute;
      const side = r && r.side ? ` ${String(r.side).toLowerCase()} of the area` : ' around the area';
      const extra = r && Number.isFinite(r.extra_min) ? `, +${Math.round(r.extra_min)} min` : '';
      return `Reroute${side}${extra}`;
    }
    default:
      return String(adv.action);
  }
}

const ICAO_WORD = { MONITOR: 'MONITOR', CONTINUE: 'CONTINUE', HOLD: 'HOLD', DIVERT: 'DIVERT', CHANGE_LEVEL: 'CHANGE LEVEL', REROUTE: 'REROUTE' };

// "Keep watching (MONITOR)": the line the dispatcher reads; the advisory text keeps the ICAO words.
export const actionPlain = (adv) => `${actionShort(adv)} (${ICAO_WORD[adv.action] || adv.action})`;

// The approve button (R12.10): "Approve: keep watching RFA1225".
export function approveText(adv) {
  const f = adv.proxy_flight;
  switch (adv.action) {
    case 'MONITOR':
      return `Approve: keep watching ${f}`;
    case 'CONTINUE':
      return `Approve: continue ${f}`;
    case 'HOLD':
      return Number.isFinite(adv.hold_fl) ? `Approve: hold ${f} at ${fl(adv.hold_fl)}` : `Approve: hold ${f}`;
    case 'DIVERT':
      return adv.alternate_icao ? `Approve: divert ${f} to ${adv.alternate_icao}` : `Approve: divert ${f}`;
    case 'CHANGE_LEVEL':
      return `Approve: change level for ${f}`;
    case 'REROUTE':
      return `Approve: reroute ${f}`;
    default:
      return `Approve: ${String(adv.action).toLowerCase()} for ${f}`;
  }
}

// "Inside the ash now" / "Enters in 12 min (est.)" / "Entry was due 3 min ago (est.)".
export function entryWords(adv, now) {
  const st = entryState(adv, now);
  if (st.kind === 'inside') return 'Inside the ash now';
  if (st.kind === 'ahead') return `Enters in ${st.minutes} min (est.)`;
  return st.minutes ? `Entry was due ${st.minutes} min ago (est.)` : 'Entry is due now (est.)';
}

// When the advisory's text was written: the model's own time, never later than the draft's
// facts (created_at, which advisories stored before drafted_at fall back to).
export const draftedAt = (adv) => adv.drafted_at || adv.created_at;

// The lead card's entry words (5.2): "entry due now", "enters in 23 min", "inside at 0957Z" (the
// draft knows the flight was inside at the time of its facts, not when it entered).
export function entryLead(adv, now) {
  const st = entryState(adv, now);
  if (st.kind === 'inside') return `inside at ${hhmmz(adv.created_at)}`;
  if (st.kind === 'ahead') return `enters in ${st.minutes} min`;
  return st.minutes ? `entry due ${st.minutes} min ago` : 'entry due now';
}

// The short form for one-line rows: "inside now", "enters in 12 min".
export function entryShort(adv, now) {
  const st = entryState(adv, now);
  if (st.kind === 'inside') return 'inside now';
  if (st.kind === 'ahead') return `enters in ${st.minutes} min`;
  return st.minutes ? `entry due ${st.minutes} min ago` : 'entry due now';
}

const PRODUCT_WORD = { SIGMET: 'SIGMET', VAA: 'VAA', VONA: 'VONA', TAF: 'TAF', METAR: 'METAR', CONE: 'TEPHRA area', WINDS: 'Winds' };
const STAMP = /^\d{8}T\d{4}Z?$/;
const nameCase = (part) => (/^[A-Z_]+$/.test(part) && part.length > 4
  ? part.split('_').map((w) => w.charAt(0) + w.slice(1).toLowerCase()).join(' ')
  : part.replace(/_/g, ' '));

// The product a source is, named from its own record (R10.4): "SIGMET WIIF 15 (area 2)",
// "VAA Darwin 2026/176", "VONA Anak Krakatau". Never merged by hash and never invented: with no
// source_id the feed name stands alone and the caller adds the issue time.
export function productName(s) {
  const id = typeof s.source_id === 'string' ? s.source_id.trim() : '';
  if (!id) return null;
  const parts = id.split(':').filter((p) => p && !STAMP.test(p));
  if (!parts.length) return id;
  const head = PRODUCT_WORD[parts[0]] || parts[0];
  const rest = parts.slice(1)
    .filter((p) => !(parts[0] === 'VAA' && /^\d{6}$/.test(p))) // the volcano number in a VAA id
    .map((p) => {
      const area = /^(.*)_AREA_(\d+)$/.exec(p);
      return area ? `${nameCase(area[1])} (area ${area[2]})` : nameCase(p);
    });
  return [head, ...rest].join(' ');
}

const USD = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
// "$62,525" (R2.8); "–" when the number is unknown, never 0.
export const usd = (n) => (Number.isFinite(n) ? USD.format(n) : '–');

// "43 s", "2 min 5 s": solver times (R12.6).
export function secs(ms) {
  if (!Number.isFinite(ms)) return '–';
  const s = Math.max(1, Math.round(ms / 1000));
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min${s % 60 ? ` ${s % 60} s` : ''}`;
}

export function initials(name) {
  const parts = String(name || '').trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
