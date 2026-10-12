// Crew (pilot) reports of ash on the Desk (docs/UI-DESIGN.md 10.15, MODULES.md 5.19): the "Report
// ash from a crew" form, the one-line Decide link with the reports, a report's full record with
// withdrawal and the offer to start a message (a VAR draft) to the weather office and the VAAC,
// and the "Crew report of ash on this route" line on affected drafts. Code draws every area and
// writes every time, id and coordinate; a report is refused rather than completed with a guess.
// Nothing here re-plans a flight, calls a model or sends anything.

import { PATHS, api, problems } from './api.js';
import { announce, byId, el, icon } from './dom.js';
import { actionShort, activeNow, fl, hhmmz } from './format.js';
import { loadDocs, openDoc } from './docs.js';
import { app, draftList } from './state.js';
import { toast } from './toast.js';
import { openBSheet } from './ui.js';

const CREW_LABEL = 'Crew report caution area (operator policy A; not a VAA or SIGMET)';
const FLAG_LINE = 'Crew report of ash on this route';
// models.CrewCue, in the order a crew report is usually read; the words are CREW_CUE_TEXT.
const CUES = [
  ['ASH_SEEN', 'Ash seen'],
  ['HAZE', 'Haze or dust in the cabin'],
  ['ST_ELMOS_FIRE', "St Elmo's fire"],
  ['ENGINE', 'Engine signs'],
  ['SULPHUR_SMELL', 'Sulphur smell'],
  ['NO_ASH_SEEN', 'No ash seen'],
];
const CUE_WORDS = Object.fromEntries(CUES.map(([k, w]) => [k, w.toLowerCase().replace("st elmo's", "St Elmo's")]));
const AREA_CUES = new Set(['ASH_SEEN', 'HAZE', 'ST_ELMOS_FIRE', 'ENGINE']);
// tephra.models._AIRLINE_CALLSIGN: only airline-style callsigns are RFA proxy flights.
const AIRLINE = /^[A-Z]{3}[0-9][0-9A-Z]{0,3}$/;
// server.REASON_ACTIONS: advice that keeps a flagged flight on its route needs a written reason.
const REASON_ACTIONS = new Set(['CONTINUE', 'MONITOR']);
const REMARKS_MAX = 300; // crew_reports.MAX_REMARKS_CHARS
const WITHDRAW_MIN = 3; // crew_reports.MIN_WITHDRAW_REASON_CHARS
const WITHDRAW_MAX = 500;
const WITHDRAW_REASONS = ['Wrong flight', 'Wrong position', 'Wrong time', 'Wrong level', 'Entered twice'];
const STATE_VIEW = {
  ACTIVE: ['i-pin', 'crew'],
  COVERED: ['st-info', 'info'],
  EXPIRED: ['st-off', 'off'],
  WITHDRAWN: ['st-off', 'off'],
  NO_AREA: ['st-info', 'info'],
};

let policy = null; // crew_reports block of GET /api/policy, for the form's hints only
let sectionOpen = null; // the Decide link's open state, kept across re-renders (null: not chosen yet)

// --- data ------------------------------------------------------------------------------------

const isPicture = (p) => p && typeof p === 'object' && Array.isArray(p.reports) && Array.isArray(p.flags);

// The `crew` event and WallSnapshot.crew carry the whole picture of the current mode.
export function setCrew(pic) {
  if (!isPicture(pic)) return;
  app.crew = pic;
  renderCrewSection();
  if (app.hub.crewChanged) app.hub.crewChanged();
}

// The tracked RFA flights the form offers, from the Wall's aircraft layer (airline callsigns only).
export function setAircraft(fc) {
  if (!fc || !Array.isArray(fc.features)) return;
  app.aircraft = fc.features.map((f) => f && f.properties).filter((p) => p && typeof p.hex === 'string' && AIRLINE.test(p.callsign || ''));
}

export async function loadCrewPolicy() {
  const res = await api('/api/policy');
  const block = res.ok && res.data && res.data.policy && res.data.policy.crew_reports;
  if (block) policy = block;
}

const value = (key) => (policy && policy[key] && Number.isFinite(policy[key].value) ? policy[key].value : null);
const views = () => (app.crew ? app.crew.reports : []);
const viewOf = (id) => views().find((v) => v.report.id === id) || null;

// The flag on a draft's flight, when its projected track crosses an active crew report area.
// The picture is of the current mode; a draft of the other mode is never matched to it.
export function crewFlag(adv) {
  if (!adv || !app.crew || !app.state) return null;
  if (Boolean(adv.replay) !== (app.state.mode === 'REPLAY')) return null;
  return app.crew.flags.find((f) => f.hex === adv.hex) || null;
}

export const crewReasonNeeded = (adv) => Boolean(crewFlag(adv)) && REASON_ACTIONS.has(adv.action);

// A key that changes when the flag on a draft changes, so its card and review re-render.
export function crewKey(adv) {
  const f = crewFlag(adv);
  return f ? `${f.report_ids.join(',')}|${f.inside_now ? 0 : f.minutes_to_entry}` : '';
}

const cueText = (r) => r.cues.map((c) => CUE_WORDS[c] || c).join(', ');
const bandText = (r) => (r.level_from_fl === r.level_to_fl ? fl(r.level_from_fl) : `${fl(r.level_from_fl)}–${fl(r.level_to_fl)}`);
const latLon = (lat, lon) => `${Math.abs(lat).toFixed(2)}${lat >= 0 ? 'N' : 'S'} ${Math.abs(lon).toFixed(2)}${lon >= 0 ? 'E' : 'W'}`;
const whenFlag = (f) => (f.inside_now ? 'is inside the crew report area now' : `enters the crew report area in ${f.minutes_to_entry} min if track and level are held`);
const who = (actor) => String(actor || '').replace(/^desk:/, '');

// A row's short state word; the full code-written label stays in its title and in the record.
const SHORT_STATE = { ACTIVE: 'Active', COVERED: 'Covered', EXPIRED: 'Expired', WITHDRAWN: 'Withdrawn' };
const shortState = (v) => SHORT_STATE[v.state] || (v.report.kind === 'ROUTINE' ? 'Routine' : 'No ash seen');

function stateBadge(v, { short = false } = {}) {
  const [shape, tone] = STATE_VIEW[v.state] || STATE_VIEW.NO_AREA;
  return el('span', { class: `crew-state crew-state--${tone}`, title: short ? v.state_label : null }, icon(shape, 'st'), el('span', { text: short ? shortState(v) : v.state_label }));
}

// "Crew report of ash on this route" on a draft (the review and the Next decision card).
export function crewBox(adv, { reason = false } = {}) {
  const flag = crewFlag(adv);
  if (!flag) return null;
  const reports = flag.report_ids.map(viewOf).filter(Boolean);
  return el('div', { class: 'crewbox', role: 'note' },
    el('p', { class: 'crewbox__line' }, icon('i-pin', 'icon crewbox__pin'), el('strong', { text: FLAG_LINE })),
    el('p', { class: 'crewbox__when', text: `${flag.proxy_flight} ${whenFlag(flag)}.` }),
    ...reports.map((v) => el('p', { class: 'crewbox__rep' },
      el('span', { text: `${v.report.flight} reported ${cueText(v.report)} at ${bandText(v.report)}, ${v.age_text}, ${v.place_text} · ${v.state_label}. ` }),
      el('button', { type: 'button', class: 'linkbtn', 'data-crew': v.report.id }, el('span', { text: 'See the report' }), icon('i-chevron-right')))),
    el('p', { class: 'fine', text: `${CREW_LABEL}. A flag only: nothing was re-planned.${reason ? ' Approving this advice needs a written reason below.' : ''}` }));
}

// --- the Decide link (R10.4 one-line links) ---------------------------------------------------

export function renderCrewSection() {
  const host = byId('crew-section');
  if (!host) return;
  host.hidden = !app.me;
  if (!app.me) {
    host.dataset.key = '';
    host.replaceChildren();
    return;
  }
  const list = views();
  if (!list.length) {
    host.dataset.key = '';
    host.replaceChildren(el('button', { type: 'button', class: 'qlink__btn', 'data-crewform': '1' },
      icon('i-pin', 'icon qlink__ic'),
      el('span', { class: 'qlink__t' }, el('strong', { text: 'Report ash from a crew' }), el('span', { class: 'qlink__sub', text: ' · a pilot saw ash, smelled sulphur or had engine signs' })),
      icon('i-chevron-right', 'icon qlink__go')));
    return;
  }
  const drawn = list.filter((v) => v.state === 'ACTIVE' || v.state === 'COVERED').length;
  const outside = list.filter((v) => v.discrepancy);
  const flags = app.crew.flags.length;
  const sub = [drawn ? `${drawn} with a caution area` : 'none with a caution area now', flags ? `${flags} flight${flags === 1 ? '' : 's'} flagged` : null].filter(Boolean).join(' · ');
  const rows = list.map((v) => el('li', {},
    el('button', { type: 'button', class: 'nrow crow', 'data-crew': v.report.id, 'aria-label': `${v.report.flight}, ${v.state_label}, ${bandText(v.report)}, ${v.age_text}, ${v.place_text}` },
      stateBadge(v, { short: true }),
      el('span', { class: 'nrow__what' },
        el('span', { class: 'nrow__vol', text: `${v.report.flight} · ${bandText(v.report)}` }),
        el('span', { class: 'nrow__meta', text: `${v.age_text} · ${v.place_text}` })),
      icon('i-chevron-right', 'icon nrow__go')),
    v.discrepancy ? outsideOffer(v) : null));
  // The drafts of flagged flights, so the ones that need a reason are one tap away.
  const flaggedDrafts = draftList().filter((a) => crewFlag(a)).sort((a, b) => String(a.proxy_flight).localeCompare(String(b.proxy_flight)));
  const draftsLine = flaggedDrafts.length ? el('div', { class: 'crewdrafts' },
    el('p', { class: 'fine', text: `Drafts for flagged flights (${flaggedDrafts.length}). Keep watching or Continue needs a written reason:` }),
    el('ul', { class: 'crewdrafts__list' }, flaggedDrafts.map((a) => el('li', {},
      el('button', { type: 'button', class: 'reason-chip', 'data-open': a.id }, el('span', { text: `${a.proxy_flight} · ${REASON_ACTIONS.has(a.action) ? `${actionShort(a)}: reason needed` : actionShort(a)}` }), icon('i-chevron-right')))))) : null;
  const open = sectionOpen === null ? outside.length > 0 || flaggedDrafts.length > 0 : sectionOpen;
  const box = el('details', { class: 'qlink__box ndisc crewsec', open },
    el('summary', { class: 'qlink__btn' }, icon('i-pin', 'icon qlink__ic'),
      el('span', { class: 'qlink__t' },
        el('strong', { text: `Crew reports of ash (${list.length})` }),
        el('span', { class: 'qlink__sub', text: ` · ${sub}` }),
        outside.length ? el('span', { class: 'crewsec__dis' }, icon('st-caution', 'st'), el('span', { text: ` ${outside.length} outside the official area` })) : null),
      icon('i-chevron-right', 'icon qlink__go disclosure')),
    draftsLine,
    el('ul', { class: 'nlist' }, rows),
    el('button', { type: 'button', class: 'btn btn--neutral crewsec__new', 'data-crewform': '1' }, icon('i-pin'), el('span', { text: 'Report ash from a crew' })));
  box.addEventListener('toggle', () => {
    sectionOpen = box.open;
  });
  // Redrawn only when its words change, and the focused control keeps focus.
  const key = box.textContent + String(open) + String(app.offline);
  if (host.dataset.key === key && host.firstChild) return;
  host.dataset.key = key;
  const had = document.activeElement && host.contains(document.activeElement) ? document.activeElement : null;
  const sel = had && ['data-crew', 'data-crewvar', 'data-open', 'data-crewform'].map((a) => (had.hasAttribute(a) ? `[${a}="${CSS.escape(had.getAttribute(a))}"]` : '')).find(Boolean);
  host.replaceChildren(box);
  if (had) (sel && host.querySelector(sel) || host.querySelector('summary')).focus({ preventScroll: true });
}

// "Crew report outside the official area": the offer to start the message to the weather office
// and the VAAC (EUR Doc 019 3.2.9 e). A VAR draft a person completes and signs; nothing is sent.
function outsideOffer(v) {
  return el('div', { class: 'crewdis', role: 'note' },
    el('p', { class: 'crewdis__t' }, icon('st-caution', 'st'), el('span', { text: `${v.discrepancy}: ${v.report.flight}, ${v.age_text}.` })),
    el('p', { class: 'fine', text: 'No valid official area meets it, sideways or in height. Pass the difference on to the weather office and the VAAC.' }),
    el('button', { type: 'button', class: 'btn crewdis__go', 'data-crewvar': v.report.id, disabled: app.offline },
      icon('i-file'), el('span', { text: 'Start a message to the weather office and VAAC' })));
}

// --- a report's full record, withdrawal, the VAR ----------------------------------------------

export function openCrewReport(id) {
  const v = viewOf(id);
  if (!v) {
    toast({ tone: 'caution', title: 'That crew report is not in the current picture (another mode, or older than 24 hours).' });
    return;
  }
  showReport(openBSheet({ title: `Crew report: ${v.report.flight}`, wide: true }), v);
}

// One report in the sheet: its record, then the VAR (when no outside-the-area offer already
// shows it) and the withdrawal, both only while the report is not withdrawn.
function showReport(sheet, v, note = null) {
  const draw = (view, n = null) => {
    sheet.setTitle(`Crew report: ${view.report.flight}`);
    sheet.setBody(reportBody(view, n));
    sheet.body.scrollTop = 0;
    const open = view.state !== 'WITHDRAWN';
    sheet.setFooter(open ? el('div', { class: 'secondary' },
      view.report.kind === 'ASH' && !view.discrepancy ? el('button', { type: 'button', class: 'btn', disabled: app.offline, onclick: (e) => draftVar(view, e.currentTarget, sheet) }, icon('i-file'), el('span', { text: 'Draft the VAR (weather office and VAAC)' })) : null,
      el('button', { type: 'button', class: 'btn btn--outline btn--reject', disabled: app.offline, onclick: () => withdrawView(view, sheet, draw) }, icon('i-x'), el('span', { text: 'Withdraw (entry error)…' }))) : null);
  };
  draw(v, note);
}

function factRow(dl, k, val) {
  if (val) dl.append(el('div', { class: 'srow' }, el('dt', { text: k }), el('dd', { text: val })));
}

function reportBody(v, note) {
  const r = v.report;
  const a = r.area;
  const flagged = app.crew ? app.crew.flags.filter((f) => f.report_ids.includes(r.id)) : [];
  const dl = el('dl', { class: 'summary crewfacts' });
  factRow(dl, 'Crew reported', cueText(r));
  factRow(dl, 'Level', bandText(r));
  factRow(dl, 'Observed', `${hhmmz(r.observed_at)} (${v.age_text})`);
  factRow(dl, 'Position', `${latLon(r.lat, r.lon)} · ${r.position_basis === 'ADSB_FIX' ? `ADS-B fix at ${hhmmz(r.position_observed_at)}` : 'typed by dispatcher'}`);
  factRow(dl, 'Near', v.place_text);
  if (a) {
    factRow(dl, 'Caution area', `${a.radius_nm} NM around the position · ${fl(a.base_ft / 100)}–${fl(a.top_ft / 100)} · valid ${hhmmz(a.valid_from)} to ${hhmmz(a.valid_to)}`);
    factRow(dl, 'Wind stretch', a.stretch_note);
    factRow(dl, 'Flights flagged', flagged.length ? flagged.map((f) => `${f.proxy_flight} (${f.inside_now ? 'inside now' : `in ${f.minutes_to_entry} min`})`).join(', ') : 'none seen crossing it');
  }
  if (v.state === 'COVERED') factRow(dl, 'Covered by', `${v.covered_by.length} official area${v.covered_by.length === 1 ? '' : 's'}: display only, the area and its flags stay`);
  factRow(dl, 'Entered', `${who(r.entered_by)} at ${hhmmz(r.created_at)}`);
  if (r.remarks) factRow(dl, 'Remarks', r.remarks);
  if (v.state === 'WITHDRAWN') factRow(dl, 'Withdrawn', `${who(r.withdrawn_by)} at ${hhmmz(r.withdrawn_at)}: ${r.withdraw_reason || ''}`);
  return el('div', { class: 'stack' },
    note,
    el('p', { class: 'crewhead' }, stateBadge(v), el('span', { class: 'fine', text: v.age_text }),
      r.replay ? el('span', { class: 'chip chip--replay chip--sm' }, icon('i-replay', 'st'), el('span', { text: 'REPLAY' })) : null),
    v.discrepancy ? outsideOffer(v) : null,
    el('p', { class: 'note', text: a
      ? `${CREW_LABEL}. Code drew it from this report; it flags flights whose projected track crosses it and never shrinks or replaces an official area.`
      : 'Recorded with its audit entry. No caution area was drawn, and nothing was removed or shortened.' }),
    dl,
    el('p', { class: 'crewsum', text: v.summary }),
    el('details', { class: 'disclose' },
      el('summary', {}, icon('i-chevron-right', 'icon disclosure'), el('span', { text: 'Technical ids' })),
      el('ul', { class: 'plist mono' }, [
        `report ${r.id}`,
        r.position_source_id ? `position ${r.position_source_id}` : null,
        a && a.wind_source_id ? `wind ${a.wind_source_id}` : null,
        v.covered_by.length ? `covered by ${v.covered_by.join(', ')}` : null,
        `policy ${r.policy_id} v${r.policy_version} #${r.policy_hash}`,
        r.replay_case_id ? `replay case ${r.replay_case_id}` : null,
      ].filter(Boolean).map((t) => el('li', { text: t })))));
}

function withdrawView(v, sheet, draw) {
  const area = el('textarea', { id: 'crew-withdraw', class: 'field', rows: '3', maxlength: String(WITHDRAW_MAX), autocomplete: 'off', 'aria-describedby': 'crew-withdraw-msg' });
  const msg = el('div', { id: 'crew-withdraw-msg', class: 'field-msg', 'aria-live': 'polite' });
  const chips = el('div', { class: 'reason-chips', role: 'group', 'aria-label': 'Quick reasons (inserted into the text, still editable)' },
    WITHDRAW_REASONS.map((t) => el('button', { type: 'button', class: 'reason-chip', 'aria-pressed': 'false', onclick: () => {
      area.value = area.value.trim() ? `${area.value.trim()}. ${t}` : t;
      area.focus();
    } }, icon('i-plus', 'icon reason-chip__add'), el('span', { text: t }))));
  sheet.setTitle(`Withdraw crew report: ${v.report.flight}`);
  sheet.setBody(el('div', { class: 'stack' },
    el('p', { class: 'note', text: 'Withdraw only an entry error: the wrong flight, position, time or level. The report and its audit entries are kept. A later "no ash" report is not a reason: it never removes an area.' }),
    el('label', { class: 'flabel', for: 'crew-withdraw', text: 'Reason (required)' }), chips, area, msg));
  const go = el('button', { type: 'button', class: 'btn btn--reject-solid' }, icon('i-x'), el('span', { text: 'Withdraw report' }));
  const cancel = el('button', { type: 'button', class: 'btn btn--outline' }, el('span', { text: 'Cancel' }));
  cancel.addEventListener('click', () => draw(viewOf(v.report.id) || v));
  go.addEventListener('click', async () => {
    const reason = area.value.trim();
    if (reason.length < WITHDRAW_MIN) {
      msg.replaceChildren(errLine(`Give a reason of at least ${WITHDRAW_MIN} characters.`));
      area.focus();
      return;
    }
    go.disabled = true;
    const res = await api(PATHS.crewWithdraw(v.report.id), { method: 'POST', body: { reason } });
    go.disabled = false;
    if (res.ok && res.data && res.data.report) {
      draw(res.data, el('div', { class: 'banner banner--approved', role: 'status' }, icon('i-check', 'st'), el('p', { text: `Withdrawn by ${app.me ? app.me.name : 'you'}. The reason is in the audit log.` })));
      announce(`Crew report from ${v.report.flight} withdrawn.`);
      return;
    }
    const why = res.status === 409 ? 'This report is already withdrawn.' : res.status === 404 ? 'This crew report no longer exists.' : res.status === 0 ? "Can't reach the server." : `Not withdrawn: ${problems(res).join('; ') || (res.data && res.data.detail) || `HTTP ${res.status}`}`;
    msg.replaceChildren(errLine(why));
  });
  sheet.setFooter(el('div', { class: 'secondary' }, go, cancel));
  window.setTimeout(() => area.focus(), 50);
}

const errLine = (text) => el('p', { class: 'msg msg--serious' }, icon('st-serious', 'st'), el('span', { text }));

// POST …/var: the VAR pre-filled from the report, opened like any Paperwork draft.
export async function draftCrewVar(id, button = null, sheet = null) {
  const v = viewOf(id);
  if (v) return draftVar(v, button, sheet);
  toast({ tone: 'caution', title: 'That crew report is not in the current picture.' });
  return null;
}

async function draftVar(v, button, sheet) {
  if (button) {
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
  }
  const res = await api(PATHS.crewVar(v.report.id), { method: 'POST' });
  if (button) {
    button.disabled = false;
    button.removeAttribute('aria-busy');
  }
  if (res.ok && res.data && res.data.id) {
    loadDocs();
    openDoc(res.data);
    announce(`VAR draft for ${v.report.flight} ready. Nothing is sent.`);
    return res.data;
  }
  const why = res.status === 409 ? ((res.data && res.data.detail) || 'Only a crew report of ash that is not withdrawn becomes a VAR.')
    : res.status === 0 ? "Can't reach the server." : `No VAR drafted: ${(res.data && res.data.detail) || `HTTP ${res.status}`}`;
  if (sheet) sheet.setBody(el('div', { class: 'stack' }, errLine(why), reportBody(viewOf(v.report.id) || v, null)));
  else toast({ tone: 'caution', title: why });
  return null;
}

// --- the form: "Report ash from a crew" -------------------------------------------------------

const pad2 = (n) => String(n).padStart(2, '0');
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const dayWord = (t) => `${pad2(new Date(t).getUTCDate())} ${MONTHS[new Date(t).getUTCMonth()]}`;

function kindLine(cues) {
  if (cues.has('ASH_SEEN') && cues.has('NO_ASH_SEEN')) return ['serious', "'Ash seen' and 'No ash seen' cannot both be reported."];
  if ([...cues].some((c) => AREA_CUES.has(c))) {
    const r = value('radius_nm');
    return ['area', `Draws a crew report caution area${r ? ` of ${r} NM` : ''} around the position.`];
  }
  if (cues.has('SULPHUR_SMELL')) return ['info', 'A sulphur smell alone is recorded as a routine report: no area is drawn.'];
  if (cues.has('NO_ASH_SEEN')) return ['info', 'Recorded. A no-ash report never removes or shortens any area.'];
  return ['none', 'Choose at least one.'];
}

// observed_at from the chosen day of the active clock and HHMM; null when not a valid time.
function observedAt(day, hhmm) {
  const m = /^([01]\d|2[0-3])([0-5]\d)$/.exec(hhmm);
  const now = activeNow();
  if (!m || now === null) return null;
  const d = new Date(now - (day === 'yesterday' ? 86400000 : 0));
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), Number(m[1]), Number(m[2]));
}

const FIELD_OF = { hex: 'flight', callsign: 'flight', cues: 'cues', level: 'level', level_from_fl: 'level', level_to_fl: 'level', observed_at: 'time', position: 'pos', lat: 'pos', lon: 'pos', remarks: 'remarks' };

export function openCrewForm({ hex = null } = {}) {
  if (!app.me) return null;
  if (!policy) loadCrewPolicy();
  const f = { flight: hex || '', callsign: '', cues: new Set(), day: 'today', fix: null, fixState: 'idle', fixNote: '', seq: 0, busy: false };
  const msgs = {};
  const msgNode = (key) => (msgs[key] = el('div', { id: `crew-${key}-msg`, class: 'field-msg', 'aria-live': 'polite' }));
  const setMsg = (key, text) => msgs[key].replaceChildren(...(text ? [errLine(text)] : []));

  // Flight: a tracked RFA flight, or a typed airline callsign.
  const tracked = [...app.aircraft].sort((a, b) => String(a.proxy_flight).localeCompare(String(b.proxy_flight)));
  const flightSel = el('select', { id: 'crew-flight', class: 'field field--select', 'aria-describedby': 'crew-flight-msg' },
    el('option', { value: '', text: tracked.length ? 'Choose a tracked RFA flight' : 'No RFA flight is tracked right now' }),
    tracked.map((p) => el('option', { value: p.hex, selected: p.hex === f.flight ? true : null,
      text: `${p.proxy_flight} · ${p.callsign}${p.alt_baro_ft != null ? ` · ${fl(p.alt_baro_ft / 100)}` : ''}` })),
    el('option', { value: '__typed', text: 'Another flight: type its callsign' }));
  const callsign = el('input', { id: 'crew-callsign', class: 'field crewmono', type: 'text', maxlength: '7', autocapitalize: 'characters', autocomplete: 'off', spellcheck: 'false', placeholder: 'e.g. GIA417', hidden: true, 'aria-label': 'Callsign', 'aria-describedby': 'crew-flight-msg' });

  // What the crew reported.
  const kind = el('p', { class: 'crewkind', 'aria-live': 'polite' });
  const cueBtns = CUES.map(([k, w]) => el('button', { type: 'button', class: 'reason-chip cuechip', 'aria-pressed': 'false', 'data-cue': k },
    icon('i-plus', 'icon reason-chip__add'), icon('i-check', 'icon reason-chip__on'), el('span', { text: w })));
  const showKind = () => {
    const [tone, text] = kindLine(f.cues);
    kind.dataset.tone = tone;
    kind.replaceChildren(icon(tone === 'area' ? 'i-pin' : tone === 'serious' ? 'st-serious' : 'st-info', 'st'), el('span', { text }));
  };
  for (const b of cueBtns) {
    b.addEventListener('click', () => {
      const k = b.dataset.cue;
      if (f.cues.has(k)) f.cues.delete(k);
      else f.cues.add(k);
      b.setAttribute('aria-pressed', String(f.cues.has(k)));
      setMsg('cues', '');
      showKind();
    });
  }
  showKind();

  // Level: one flight level, or a band.
  const flFrom = el('input', { id: 'crew-fl-from', class: 'field crewmono crewfl', type: 'text', inputmode: 'numeric', maxlength: '3', autocomplete: 'off', placeholder: '350', 'aria-describedby': 'crew-level-hint crew-level-msg' });
  const flTo = el('input', { id: 'crew-fl-to', class: 'field crewmono crewfl', type: 'text', inputmode: 'numeric', maxlength: '3', autocomplete: 'off', 'aria-label': 'Top of the band, flight level (optional)', 'aria-describedby': 'crew-level-hint crew-level-msg' });
  const margin = value('level_margin_ft');
  const levelHint = el('p', { id: 'crew-level-hint', class: 'fine', text: `The level the crew gave; fill the second box only for a band.${margin ? ` The area spans it ${margin.toLocaleString('en')} ft above and below.` : ''} A report with no level is refused: TEPHRA never invents one.` });

  // Observed at (UTC), on the active clock: today or yesterday, HHMM.
  const now0 = activeNow();
  const seg = el('div', { class: 'seg', role: 'group', 'aria-label': 'Day of the observation (UTC)' },
    ['today', 'yesterday'].map((d) => el('button', { type: 'button', class: 'seg__btn', 'data-day': d, 'aria-pressed': String(d === f.day),
      text: now0 === null ? (d === 'today' ? 'Today' : 'Yesterday') : `${d === 'today' ? 'Today' : 'Yesterday'} (${dayWord(now0 - (d === 'today' ? 0 : 86400000))})` })));
  const time = el('input', { id: 'crew-time', class: 'field crewmono crewtime', type: 'text', inputmode: 'numeric', maxlength: '4', autocomplete: 'off', placeholder: 'HHMM', 'aria-describedby': 'crew-time-hint crew-time-msg' });
  const nowBtn = el('button', { type: 'button', class: 'btn btn--outline crewnow' }, icon('i-clock'), el('span', { text: 'Now' }));
  const valid = value('valid_min');
  const timeHint = el('p', { id: 'crew-time-hint', class: 'fine', text: `UTC on TEPHRA's clock. Not in the future${valid ? `, and not more than ${valid / 60 === Math.round(valid / 60) ? `${valid / 60} h` : `${valid} min`} ago (an area lasts that long from the observation)` : ''}.` });

  // Position: the flight's ADS-B fix at that time, or what the dispatcher types.
  const pos = el('div', { class: 'crewpos', 'aria-live': 'polite' });
  const lat = el('input', { id: 'crew-lat', class: 'field crewmono', type: 'text', inputmode: 'decimal', autocomplete: 'off', placeholder: '6.8', 'aria-describedby': 'crew-pos-msg' });
  // No hemisphere is preselected: a wrong default would put the report on the wrong side.
  const latH = el('select', { class: 'field field--select crewhemi', 'aria-label': 'North or south' }, el('option', { value: '', text: 'N/S' }), el('option', { value: 'N', text: 'N' }), el('option', { value: 'S', text: 'S' }));
  const lon = el('input', { id: 'crew-lon', class: 'field crewmono', type: 'text', inputmode: 'decimal', autocomplete: 'off', placeholder: '110.1', 'aria-describedby': 'crew-pos-msg' });
  const lonH = el('select', { class: 'field field--select crewhemi', 'aria-label': 'East or west' }, el('option', { value: '', text: 'E/W' }), el('option', { value: 'E', text: 'E' }), el('option', { value: 'W', text: 'W' }));
  const typedBox = el('div', { class: 'crewtyped' },
    el('div', { class: 'crewll' }, el('label', { class: 'flabel', for: 'crew-lat', text: 'Latitude (degrees)' }), el('div', { class: 'crewll__row' }, lat, latH)),
    el('div', { class: 'crewll' }, el('label', { class: 'flabel', for: 'crew-lon', text: 'Longitude (degrees)' }), el('div', { class: 'crewll__row' }, lon, lonH)),
    el('p', { class: 'fine', text: 'Typed by dispatcher: the report is marked so on every screen.' }));
  const drawPos = () => {
    const kids = [];
    if (f.fixState === 'idle') kids.push(el('p', { class: 'fine', text: "Choose the flight and the time first. TEPHRA then looks for the flight's ADS-B fix at that time." }));
    else if (f.fixState === 'loading') kids.push(el('p', { class: 'fine' }, el('span', { class: 'spinner', 'aria-hidden': 'true' }), el('span', { text: ' Looking for the ADS-B fix…' })));
    else if (f.fixState === 'found') {
      const x = f.fix;
      kids.push(el('p', { class: 'crewfix' }, icon('st-ok', 'st'), el('span', { text: `${x.note}: ${latLon(x.lat, x.lon)}${x.alt_baro_ft != null ? `, ${fl(x.alt_baro_ft / 100)}` : ''}. The report is placed at this fix.` })));
    } else if (f.fixState === 'none') {
      kids.push(el('p', { class: 'crewfix crewfix--none' }, icon('st-caution', 'st'), el('span', { text: `${f.fixNote}.` })), typedBox);
    } else if (f.fixState === 'error') kids.push(errLine(f.fixNote));
    pos.replaceChildren(...kids);
  };
  drawPos();

  const remarks = el('textarea', { id: 'crew-remarks', class: 'field', rows: '2', maxlength: String(REMARKS_MAX), autocomplete: 'off', 'aria-describedby': 'crew-remarks-msg', placeholder: 'Optional: the crew\'s words, shown as text' });
  const summary = el('div', { class: 'field-msg', role: 'alert' });
  const result = el('div', { class: 'stack' });

  const flightParam = () => {
    if (flightSel.value === '__typed') {
      const c = callsign.value.replace(/\s+/g, '').toUpperCase();
      return c ? { callsign: c } : null;
    }
    return flightSel.value ? { hex: flightSel.value } : null;
  };

  // The fix lookup follows the flight and the time; an older answer never overwrites a newer one.
  let lookupTimer = 0;
  const lookup = () => {
    window.clearTimeout(lookupTimer);
    lookupTimer = window.setTimeout(async () => {
      const who2 = flightParam();
      const at = observedAt(f.day, time.value.trim());
      if (!who2 || at === null) {
        f.fixState = 'idle';
        f.fix = null;
        drawPos();
        return;
      }
      const seq = ++f.seq;
      f.fixState = 'loading';
      drawPos();
      const q = new URLSearchParams({ observed_at: new Date(at).toISOString(), ...who2 });
      const res = await api(`${PATHS.crewFix}?${q}`);
      if (seq !== f.seq) return;
      if (res.ok && res.data && typeof res.data.found === 'boolean') {
        f.fix = res.data.found ? res.data : null;
        f.fixState = res.data.found ? 'found' : 'none';
        f.fixNote = res.data.note || '';
      } else {
        f.fix = null;
        f.fixState = 'error';
        f.fixNote = res.status === 0 ? "Can't reach the server to look for the ADS-B fix." : `No fix lookup: ${problems(res).join('; ') || (res.data && res.data.detail) || `HTTP ${res.status}`}`;
      }
      drawPos();
    }, 250);
  };
  flightSel.addEventListener('change', () => {
    callsign.hidden = flightSel.value !== '__typed';
    if (!callsign.hidden) callsign.focus();
    setMsg('flight', '');
    lookup();
  });
  callsign.addEventListener('input', () => {
    setMsg('flight', '');
    lookup();
  });
  time.addEventListener('input', () => {
    setMsg('time', '');
    lookup();
  });
  nowBtn.addEventListener('click', () => {
    const now = activeNow();
    if (now === null) return;
    const d = new Date(now);
    time.value = `${pad2(d.getUTCHours())}${pad2(d.getUTCMinutes())}`;
    f.day = 'today';
    for (const b of seg.children) b.setAttribute('aria-pressed', String(b.dataset.day === 'today'));
    setMsg('time', '');
    lookup();
  });
  seg.addEventListener('click', (event) => {
    const b = event.target.closest('[data-day]');
    if (!b) return;
    f.day = b.dataset.day;
    for (const x of seg.children) x.setAttribute('aria-pressed', String(x.dataset.day === f.day));
    lookup();
  });

  const form = el('div', { class: 'stack crewform' },
    el('p', { class: 'note', text: 'Enter what the crew reported. Ash seen or any encounter sign draws a caution area that flags the flights crossing it. Nothing is sent, nothing is re-planned and no AI is used. TEPHRA refuses a report rather than guess a missing level, time or position.' }),
    summary,
    el('div', { class: 'fgroup' }, el('label', { class: 'flabel', for: 'crew-flight', text: 'Flight' }), flightSel, callsign, msgNode('flight')),
    el('fieldset', { class: 'fgroup crewcues' }, el('legend', { class: 'flabel', text: 'What the crew reported' }),
      el('div', { class: 'reason-chips', role: 'group', 'aria-label': 'What the crew reported' }, cueBtns), kind, msgNode('cues')),
    el('fieldset', { class: 'fgroup' }, el('legend', { class: 'flabel', text: 'Reported level' }),
      el('div', { class: 'crewlevel' }, el('label', { class: 'crewlevel__k', for: 'crew-fl-from', text: 'FL' }), flFrom, el('label', { class: 'crewlevel__k', for: 'crew-fl-to', text: 'to FL' }), flTo),
      levelHint, msgNode('level')),
    el('fieldset', { class: 'fgroup' }, el('legend', { class: 'flabel', text: 'Observed at (UTC)' }), seg,
      el('div', { class: 'crewlevel' }, time, el('span', { class: 'crewlevel__k', text: 'Z' }), nowBtn), timeHint, msgNode('time')),
    el('fieldset', { class: 'fgroup' }, el('legend', { class: 'flabel', text: 'Position' }), pos, msgNode('pos')),
    el('div', { class: 'fgroup' }, el('label', { class: 'flabel', for: 'crew-remarks', text: 'Remarks' }), remarks, msgNode('remarks')),
    result);

  const submit = el('button', { type: 'button', class: 'btn btn--neutral btn--block' }, icon('i-pin'), el('span', { text: 'Record crew report' }));
  const sheet = openBSheet({ title: 'Report ash from a crew', wide: true, body: form, footer: submit });

  const fieldError = (key, text, focus) => {
    setMsg(key, text);
    if (focus) focus.setAttribute('aria-invalid', 'true');
  };
  for (const [n, key] of [[flightSel, 'flight'], [callsign, 'flight'], [flFrom, 'level'], [flTo, 'level'], [time, 'time'], [lat, 'pos'], [lon, 'pos'], [remarks, 'remarks']]) {
    n.addEventListener('input', () => {
      n.removeAttribute('aria-invalid');
      setMsg(key, '');
    });
  }

  submit.addEventListener('click', async () => {
    if (f.busy) return;
    if (app.offline) {
      summary.replaceChildren(errLine("You're offline. Reconnect to record a crew report."));
      return;
    }
    for (const k of Object.keys(msgs)) setMsg(k, '');
    summary.replaceChildren();
    const local = [];
    const who2 = flightParam();
    if (!who2) {
      fieldError('flight', flightSel.value === '__typed' ? 'Type the callsign, for example GIA417.' : 'Choose the flight that reported.', flightSel.value === '__typed' ? callsign : flightSel);
      local.push(flightSel.value === '__typed' ? callsign : flightSel);
    } else if (who2.callsign && !AIRLINE.test(who2.callsign)) {
      fieldError('flight', 'An airline callsign: three letters and a number, such as GIA417.', callsign);
      local.push(callsign);
    }
    if (!f.cues.size) {
      setMsg('cues', 'Choose what the crew reported.');
      local.push(cueBtns[0]);
    }
    const from = flFrom.value.trim();
    const to = flTo.value.trim();
    if (!from) {
      fieldError('level', 'A crew report needs the reported flight level or band; TEPHRA never invents one.', flFrom);
      local.push(flFrom);
    } else if (!/^\d{1,3}$/.test(from) || (to && !/^\d{1,3}$/.test(to))) {
      fieldError('level', 'Flight levels are numbers, such as 350 for FL350.', flFrom);
      local.push(flFrom);
    }
    const at = observedAt(f.day, time.value.trim());
    if (at === null) {
      fieldError('time', 'Give the time as four digits, HHMM, such as 0915.', time);
      local.push(time);
    }
    let latV = null;
    let lonV = null;
    if (f.fixState === 'none') {
      latV = Number(lat.value.trim());
      lonV = Number(lon.value.trim());
      if (!lat.value.trim() || !lon.value.trim() || !Number.isFinite(latV) || !Number.isFinite(lonV) || latV < 0 || latV > 90 || lonV < 0 || lonV > 180 || !latH.value || !lonH.value) {
        fieldError('pos', 'Type the position the crew reported: degrees of latitude (0 to 90) and longitude (0 to 180), with N/S and E/W.', lat);
        local.push(lat);
      }
      if (latH.value === 'S') latV = -latV;
      if (lonH.value === 'W') lonV = -lonV;
    } else if (f.fixState === 'loading' || f.fixState === 'idle') {
      if (at !== null && who2) {
        setMsg('pos', 'Still looking for the ADS-B fix. Try again in a moment.');
        local.push(submit);
      }
    } else if (f.fixState === 'error') {
      setMsg('pos', f.fixNote);
      local.push(submit);
    }
    if (local.length) {
      summary.replaceChildren(errLine('Not recorded yet: check the fields marked below.'));
      local[0].focus();
      return;
    }
    const body = { ...who2, cues: [...f.cues], level_from_fl: Number(from), observed_at: new Date(at).toISOString() };
    if (to) body.level_to_fl = Number(to);
    if (f.fixState === 'none') {
      body.lat = latV;
      body.lon = lonV;
    }
    if (remarks.value.trim()) body.remarks = remarks.value.trim();
    f.busy = true;
    submit.disabled = true;
    submit.replaceChildren(el('span', { class: 'spinner', 'aria-hidden': 'true' }), el('span', { text: 'Recording…' }));
    const res = await api(PATHS.crewReports, { method: 'POST', body });
    f.busy = false;
    submit.disabled = false;
    submit.replaceChildren(icon('i-pin'), el('span', { text: 'Record crew report' }));
    if (res.ok && res.data && res.data.report) {
      recorded(res.data, sheet);
      return;
    }
    if (res.status === 401) {
      summary.replaceChildren(errLine('Your session has ended. Sign in again to record a crew report.'));
      return;
    }
    const list = problems(res);
    if (res.status === 422 && list.length) {
      summary.replaceChildren(el('div', { class: 'panel panel--serious' },
        el('p', { class: 'panel__title' }, icon('st-serious', 'st'), el('span', { text: 'Not recorded. TEPHRA refused the report rather than guess:' })),
        el('ul', { class: 'plist' }, list.map((p) => el('li', { text: p.replace(/^[a-z_]+:\s*/, '') })))));
      for (const p of list) {
        const key = FIELD_OF[(/^([a-z_]+):/.exec(p) || [])[1]];
        if (key && msgs[key]) setMsg(key, p.replace(/^[a-z_]+:\s*/, ''));
      }
      // The fix may have aged out (or appeared) since the lookup: look again.
      if (list.some((p) => p.startsWith('position:'))) lookup();
      sheet.body.scrollTop = 0;
      return;
    }
    summary.replaceChildren(errLine(res.status === 0 ? "Can't reach the server. The report was not recorded." : `Not recorded: ${(res.data && res.data.detail) || `HTTP ${res.status}`}`));
  });
  window.setTimeout(() => (f.flight ? time : flightSel).focus(), 50);
  if (f.flight) lookup();
  return sheet;
}

// After a report is stored: what was drawn, which flights it flags, and the next steps.
function recorded(v, sheet) {
  const r = v.report;
  const flagged = v.flagged.length;
  const head = r.kind === 'ASH'
    ? `Crew report recorded: ${r.flight} · caution area drawn · ${flagged ? `${flagged} flight${flagged === 1 ? '' : 's'} flagged` : 'no flight seen crossing it'}.`
    : `Crew report recorded: ${r.flight} · ${v.state_label}.`;
  toast({ tone: 'ok', title: head });
  announce(head);
  const another = el('button', { type: 'button', class: 'linkbtn crew-another' }, icon('i-plus'), el('span', { text: 'Report another' }));
  another.addEventListener('click', () => openCrewForm());
  showReport(sheet, v, el('div', { class: 'stack' },
    el('div', { class: 'banner banner--approved', role: 'status' }, icon('i-check', 'st'),
      el('p', { text: `Recorded under ${app.me ? app.me.name : 'your name'} at ${hhmmz(r.created_at)}. The Wall shows it now; the audit log has the entry.` })),
    another));
}

