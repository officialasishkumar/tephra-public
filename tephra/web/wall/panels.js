// The Wall's HTML parts (docs/UI-REDESIGN.md R3, R7, R8): the top bar and footer, the time bar,
// and the builders for the Details sections that show the official reports, the disagreements,
// TEPHRA's estimate, the flights, the decisions, the trace, the height filter and the data feeds,
// plus the dialogs. Every feed or model string goes in with textContent (via el()).

import {
  $, el, icon, age, band, dayMon, durMin, fl, hhmmz, hhmmssz, idTime, hhmmBefore, ms, pad, solarHour, isNight,
  compassWord, kmBetween, safeExternalUrl, pointInGeom, dest, inBbox,
} from "./util.js";
import { actionWords, deciderName, SEV_RANK, NON_OBS, worstSeverity, LEVEL_MAX, levelIsAll, levelFrac } from "./derive.js";
import { plainMove } from "./derive.js";
import { plainLine, techDetail, actorWords, actionPlain, aiWords, aiMark, aiSymbol, recordedWords, replayWords, stripLabel, describeReplay, handPlanOf, causeTitle, blockPhrase, whyLink, machineText, MARK, ASSISTANT } from "./x-parts.js";
import {
  dkHeader, dkPill, dkChip, dkTiles, dkGroup, dkRow, dkLinkRow, dkList, dkFacts, dkNote, dkAbout, dkEmpty, dkTech, dkSection, dkLink,
  dkWhen, dkDot, dkFromReplay, collapseRuns, runRow, timeRange, plural, dayTime, times,
} from "./dk.js";

// ------------------------------------------------------------------ vocabulary (section 11)

// Feed names on screen (UI-REDESIGN R12.8).
export const FEED_NAME = {
  sigmet: "VA SIGMET (AWC)", vona: "VONA (MAGMA)", vaac_tokyo: "VAA Tokyo", vaac_darwin: "VAA Darwin", taf: "TAF",
  metar: "METAR", adsb: "Aircraft data (adsb.lol)", winds: "Winds (Open-Meteo)", frames: "Satellite pictures",
  hsd: "Himawari raw processing", jma_volcano: "JMA volcano reports",
};
export const FEED_STATUS = {
  ERROR: ["st-serious", "var(--c-serious)", "Error", 0],
  STALE: ["st-stale", "var(--c-caution)", "Stale", 1],
  OK: ["st-ok", "var(--c-ok)", "Working", 2],
  NEVER: ["st-never", "var(--c-off)", "Not polled yet", 3],
  DISABLED: ["st-off", "var(--c-off)", "Off", 4],
};
const EVID = {
  OBSERVED_SAT: ["seen", "st-ok", "Ash seen by satellite", "The product reports ash identified in satellite data."],
  OBSERVED_GROUND: ["seen", "st-ok", "Ash seen from the ground", "A ground observer reported ash."],
  ESTIMATED: ["est", "st-info", "Position estimated", "The VAAC estimated the ash position."],
  NOT_IDENTIFIABLE: ["nonobs", "st-caution", "Not identifiable", "Ash could not be identified (cloud or night). Not evidence of no ash."],
  NOT_OBSERVED: ["nonobs", "st-caution", "Not observed", "The observer did not see ash. Not evidence of no ash."],
  NIGHT_BLIND: ["nonobs", "st-caution", "Night: observer blind", "Night-time: the observer cannot see ash. Not evidence of no ash."],
  NO_VA_EXPECTED: ["est", "st-info", "No ash expected", "The VAAC says no ash is expected."],
  FORECAST_NOT_AVAILABLE: ["est", "st-info", "No forecast", "The VAAC gave no forecast."],
  STALE: ["stale", "st-stale", "Older than 6 h", "This report describes an earlier puff."],
  UNKNOWN: ["off", "st-off", "Unknown", "The product does not say."],
};
const KIND = {
  "DIRECTION_MISMATCH/direction": ["DIRECTION", "The sources send the ash different ways"],
  "DIRECTION_MISMATCH/polygon": ["DIRECTION OUTSIDE", "The observatory's drift leaves the official area"],
  LAG: ["LAG", "One source is older than the other"],
  ENVELOPE: ["ENVELOPE", "The observed height sits inside the official band"],
  HEIGHT_MISMATCH: ["HEIGHT", "The sources report different heights"],
  SILENCE: ["SILENCE", "No VAA answers a reported eruption"],
  CONFLICT: ["CONFLICT", "A VAA says no ash while another source saw it"],
};
const EXPLAIN = {
  LAG: "Usual: official products are reissued every few hours, so they trail the observatory.",
  ENVELOPE: "Harmless: the heights agree within the official band.",
  HEIGHT_MISMATCH: "One source puts the ash outside the official band.",
  SILENCE: "Ash was reported and no VAA has followed. Silence is not evidence of no ash.",
  CONFLICT: "A no-ash VAA was in force when another product observed ash after it.",
};
const MODE_LINE = {
  OFFICIAL: "Same as the official area: TEPHRA adds nothing.",
  WIDENED: "The official area plus the observatory's drift, never smaller.",
  HYPOTHESIS: "No valid official product: a hypothesis. Only MONITOR or HOLD may be advised.",
};
const OUTCOME = {
  STUB: "Code only (assistant off): official reports only",
  ACCEPTED: "Reading accepted by the code's checks",
  REPAIRED: "Accepted after one repair",
  MODEL_FAILED: "Plume reader gave no result: official products only, nothing assessed beyond them",
  OFFICIAL_ONLY: "No read needed: official products only",
  PENDING: "Plume read queued for the Coordinator: official products only until it runs",
};
// The model-checked outcomes: only these were read by a model (H1, H2).
const MODEL_READ = new Set(["ACCEPTED", "REPAIRED"]);
const ACTOR = {
  code: ["i-code", "CODE"], gemini: ["i-model", "GEMINI"], adk: ["i-agent", "ADK"], stub: ["st-never", "NO MODEL"],
  human: ["i-user", "HUMAN"], system: ["i-system", "SYSTEM"],
};
// Plain words for values in the sources grid (R12.4). The mono codes stay as they are.
const PLAIN_VALUE = {
  EST: "estimated", "NOT GIVEN": "not given", "NOT STATED": "not stated", "NOT OBSERVED": "not observed", OBSERVED: "observed", OBS: "observed",
  // a SIGMET's "FCST": the area is forecast, not seen (review 2, item 8)
  FCST: "forecast, not seen",
  RED: "Red", ORANGE: "Orange", YELLOW: "Yellow", GREEN: "Green", UNASSIGNED: "not assigned",
};
const plainValue = (v) => {
  if (typeof v !== "string") return v;
  if (PLAIN_VALUE[v]) return PLAIN_VALUE[v];
  const seen = /^OBS (\d{4}Z)$/.exec(v);
  if (seen) return `seen ${seen[1]}`;
  return v;
};
const KIND_LABEL = { SIGMET: "SIGMET (airspace warning) · binding", VAA: "VAA (ash advisory)", VONA: "VONA (volcano observatory notice)" };
export const ATTRIBUTION = "OpenFreeMap © OpenMapTiles · Data © OpenStreetMap contributors · © Mapterhorn · Aircraft: adsb.lol (ODbL 1.0) · Himawari-9 data: JMA via NOAA · FIR and VAAC lines: NOAA/NWS AWC (approximate)";

const codeColor = (code) => `var(--c-code-${(code || "UNKNOWN").toLowerCase()})`;
export const eruptIcon = (code, cls = "icon erupt") => icon("i-eruption", cls, codeColor(code));
const st = (id, color, cls = "st") => icon(id, cls, color);
// A missing card whose feed was not read, not recorded or down never says "None in force".
const UNREAD = { NOT_READ: "Not read", NOT_RECORDED: "Not recorded", FEED_DOWN: "Feed down" };
const missingHead = (card, noneText) => UNREAD[card.missing_reason]
  ? el("span", { class: "cmp__note--quiet" }, st("st-off", "var(--c-off)"), el("span", { text: ` ${UNREAD[card.missing_reason]}` }))
  : el("span", { text: noneText });
const kindOf = (d) => KIND[`${d.kind}/${d.aspect}`] || KIND[d.kind] || [d.kind, d.kind];
const cardName = (sit, sid) => sit.cards.find((c) => c.source_id === sid)?.title || sid.split(":").slice(0, 3).join(" ");

// ------------------------------------------------------------------ top bar, band, footer (R3.1, R3.3)

const setText = (node, text) => { if (node && node.textContent !== text) node.textContent = text; };
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const dayMonth = (t) => { if (!Number.isFinite(t)) return "—"; const d = new Date(t); return `${d.getUTCDate()} ${MON[d.getUTCMonth()]}`; };
const narrow = () => window.innerWidth < 1360;

// The area picker's words: "Area: Java / Bali · 2 with ash", or "Area: All areas".
export function areaWords(D, key) {
  const r = (D.state.regions || []).find((x) => x.key === key);
  if (!r) return "All areas";
  const n = D.regionCounts[r.key] || 0;
  // before the first tick "none" would be a claim about something not yet read (review 1, item 1)
  return `${r.name} · ${n ? `${n} with ash` : D.state.last_tick ? "none" : "reading…"}`;
}

// The frame strip and the page title: drawn on every render, the board's included (the board
// covers the Wall, which is not redrawn while it is open, but the strip stays on screen above it).
export function renderFrame(s) {
  const replay = s.mode === "REPLAY";
  document.body.dataset.mode = s.mode;
  document.title = `${replay ? "REPLAY - " : ""}TEPHRA Wall`;
  // The frame strip says REPLAY once (UI-DESIGN 7.1); the case title is in its tooltip.
  const banner = $("replay-banner");
  banner.hidden = !replay;
  $("frame").setAttribute("aria-label", stripLabel(replay));
  if (replay) {
    const w = replayWords(s.replay);
    setText($("replay-banner-text"), w.text);
    setText($("replay-banner-case"), w.more);
    banner.title = w.title;
  }
  // A modal open before the state arrived (the board from #ai-at-work) or across a mode switch
  // gets the strip's current REPLAY words in its sr-only description (x-parts describeReplay).
  const stripWords = replay ? banner.textContent.replace(/\s+/g, " ").trim() : "";
  for (const dlg of document.querySelectorAll("dialog[open]")) describeReplay(dlg, stripWords);
}

export function renderChrome(D, store, ui) {
  const s = D.state;
  const replay = s.mode === "REPLAY";
  renderFrame(s);
  // The mode pill is not a control: in REPLAY the strip says it, so the pill only says "Live".
  const badge = $("mode-badge");
  badge.hidden = replay;
  badge.className = "mode-badge mode-badge--live";
  if (!replay && badge.dataset.word !== "Live") { badge.dataset.word = "Live"; badge.replaceChildren(icon("i-live"), "Live"); }

  // Area picker (R3.1): one menu button; the phone keeps the native select.
  const regions = s.regions || [];
  const cur = ui.region;
  setText($("area-label"), `Area: ${areaWords(D, cur)}`);
  const menu = $("regions");
  const items = [
    ...regions.map((r, i) => ({ key: r.key, text: areaWords(D, r.key), kbd: String(i + 1) })),
    { key: "", text: "All areas", kbd: null },
  ];
  const mkey = items.map((x) => `${x.key}:${x.text}:${x.key === (cur || "")}`).join("|");
  if (menu.dataset.key !== mkey) {
    menu.dataset.key = mkey;
    menu.replaceChildren(...items.map((x) => el("button", { type: "button", role: "menuitemradio", class: "area-menu__item", "aria-checked": x.key === (cur || "") ? "true" : "false", tabindex: "-1", "aria-keyshortcuts": x.kbd, dataset: { region: x.key || "all" } },
      icon("i-check", "icon area-menu__check"), el("span", { text: x.text }), x.kbd ? el("kbd", { text: x.kbd }) : null)));
  }
  const sel = $("region-select");
  const skey = items.map((x) => `${x.key}:${x.text}`).join("|");
  if (sel.dataset.key !== skey) {
    sel.dataset.key = skey;
    // the phone's native picker: the short form, "Java / Bali · 2" (R4.4)
    sel.replaceChildren(...items.map((x) => el("option", { value: x.key || "all", text: x.text.replace(/ with ash$/, "").replace(/ · none$/, "") })));
  }
  sel.value = cur || "all";

  // The AI chip (R3.1, docs/UI-AI-QUIET.md W1-W3, Naming): TEPHRA Assistant's one state in words,
  // never a count of failed steps and never red. It opens TEPHRA Assistant at work (UI-DESIGN
  // 7.21), which leads with the same words and links to Details › TEPHRA Assistant for the model
  // ids, budgets and causes: the one place that says why it is paused (docs/UI-AI-QUIET.md 8.6).
  const ai = aiStateNow(D, store);
  const w = aiWords(ai, { home: `Details › ${ASSISTANT}`, opens: `${ASSISTANT} at work`, narrow: window.innerWidth <= 420 });
  const chip = $("ai-chip");
  setText($("model-chip"), w.label);
  const suffix = chip.querySelector(".ai-chip__fail");
  suffix.hidden = !w.suffix;
  setText(suffix, w.suffix ? `· ${w.suffix}` : "");
  chip.dataset.tone = w.tone;
  chip.querySelector("use")?.setAttribute("href", `${chip.querySelector("use").getAttribute("href").split("#")[0]}#${aiSymbol(ai.kind)}`);
  chip.title = w.title;
  chip.setAttribute("aria-label", w.aria);
  // shown first with its state, so the bar never jumps to its real width (W5)
  chip.classList.remove("is-pending");

  // Data chip: "Data: 6 working · 5 off", worst first.
  const by = {};
  for (const f of store.feeds) by[f.status] = (by[f.status] || 0) + 1;
  const words = { ERROR: ["error", "errors"], STALE: ["stale", "stale"], OK: narrow() ? ["ok", "ok"] : ["working", "working"], NEVER: ["not read", "not read"], DISABLED: ["off", "off"] };
  const parts = [];
  for (const k of ["ERROR", "STALE", "OK", "NEVER", "DISABLED"]) {
    if (!by[k]) continue;
    const [id, color] = FEED_STATUS[k];
    const w = words[k][by[k] === 1 ? 0 : 1];
    parts.push(el("span", { class: `feeds-chip__part feeds-chip__part--${k.toLowerCase()}` }, k === "ERROR" || k === "STALE" ? st(id, color) : null, `${by[k]} ${w}`));
  }
  const fc = $("feeds-chip");
  const fkey = parts.map((p) => p.textContent).join("|");
  if (fc.dataset.key !== fkey) {
    fc.dataset.key = fkey;
    const kids = [el("span", { class: "feeds-chip__cap", text: "Data:" })];
    parts.forEach((p, i) => { if (i) kids.push(el("span", { class: "feeds-chip__sep", "aria-hidden": "true", text: "·" })); kids.push(p); });
    fc.replaceChildren(...kids);
  }
  fc.classList.toggle("feeds-chip--error", !!by.ERROR);
  fc.setAttribute("aria-label", `Data feeds: ${parts.map((p) => p.textContent).join(", ")}. Opens Details, Data feeds.`);

  setText($("disclaimer"), s.disclaimer || "Decision support only - fictional airline - not for operational use");
  const policy = s.policy;
  const policyBtn = $("policy-btn");
  policyBtn.hidden = !policy;
  if (policy) {
    setText(policyBtn, `Policy ${policy.preset} (illustrative)`);
    policyBtn.title = `${policy.policy_id} v${policy.version}: ${policy.label}. Open its values and sources.`;
  }
  const extra = [];
  if (ui.sat !== "off") extra.push("Imagery: NASA GIBS");
  if (ui.so2) extra.push(`${ui.sat === "off" ? "Imagery: NASA GIBS · " : ""}Contains modified Copernicus Sentinel data ${new Date(D.now).getUTCFullYear()}`);
  const attrib = [ATTRIBUTION, ...extra].join(" · ");
  // The full credit string: in the drawer footer and About › Credits; OSM stays on the map (R6.6).
  setText($("drawer-attrib"), attrib);
  $("attribution").title = attrib;
}

// The Wall's AI state (ext.js aiState), set by wall.js so this file does not import ext.js.
let aiStateNow = () => ({ kind: "on", until: null, causes: [], trouble: [], waiting: [] });
export function setAiState(fn) { aiStateNow = fn; }

export function renderClock(D, conn) {
  if (!D) return;
  // While the stream is lost the clock stops at the last event: the data froze there too.
  setText($("clock-time"), hhmmssz(conn.lostAt ? conn.lostAt : D.now));
  $("clock-time").dataset.stale = conn.lostAt ? "true" : "false";
  const sub = $("clock-sub");
  const replay = D.mode === "REPLAY";
  if (conn.lostAt) {
    setText(sub, `Stopped · ${dayMonth(conn.lostAt)} · UTC`);
    sub.dataset.tone = "caution";
  } else {
    setText(sub, narrow() ? (replay ? "Replay · UTC" : "UTC") : `${replay ? "Replay clock · " : ""}${dayMonth(D.now)} · UTC`);
    sub.dataset.tone = replay ? "replay" : "";
  }
  setText($("stale-text"), conn.lostAt ? `Not updating since ${hhmmz(conn.lostAt)}` : "");
}

// Map status pills (R6.4): only while true, at most 3 (the third becomes "+n more").
export function mapPills(D, ui, extra) {
  const pills = [];
  if (!D) return pills;
  if (!D.levelAll) {
    const what = D.hiddenOfficial
      ? ` hides ${D.hiddenOfficial} official area${D.hiddenOfficial === 1 ? "" : "s"}${D.hiddenFlights ? ` and ${D.hiddenFlights} flight${D.hiddenFlights === 1 ? "" : "s"}` : ""}`
      : D.hiddenFlights ? ` hides ${D.hiddenFlights} flight${D.hiddenFlights === 1 ? "" : "s"}` : "";
    pills.push({ tone: "caution", text: `Height filter ${fl(ui.level.min)}–${fl(ui.level.max)}${what}`, action: "level-reset", actionText: "Reset" });
  }
  if (ui.steps !== "now" && D.sit) {
    const word = { f6: "+6 h", f12: "+12 h", f18: "+18 h" }[ui.steps];
    if (D.stepsMissing?.length) {
      pills.push({ tone: "info", text: ui.steps === "all" ? "No official forecast area (+6, +12 or +18 h) in the current products" : `No official ${word} area in the current products`, action: "steps-now", actionText: "Back to now" });
    } else {
      const f = D.official.find((x) => x.properties.sel && x.properties.show && (ui.steps === "all" ? x.properties.step !== "now" : x.properties.step === ui.steps));
      const at = f ? ` for ${hhmmz(ms(f.properties.valid_from) + 3 * 3600e3)}` : "";
      pills.push({ tone: "info", text: ui.steps === "all" ? "Showing every official forecast area" : `Showing the official forecast${at} (${word})`, action: "steps-now", actionText: "Back to now" });
    }
  }
  if (extra.basemap && extra.basemapPill) pills.push({ tone: "info", text: extra.basemap });
  return pills;
}

// ------------------------------------------------------------------ advisory status line (3.2)

// "Keep watching": the plain action. The ICAO word is on the Desk and under Technical detail.
export function actionText(a) {
  const raw = actionWords(a);
  const t = actionPlain(raw) || raw;
  return t.charAt(0).toUpperCase() + t.slice(1);
}

export function advisoryLine(a) {
  if (!a) return null;
  const act = actionText(a);
  const who = deciderName(a);
  const at = a.decided_at ? hhmmz(ms(a.decided_at)) : "";
  const M = {
    DRAFT: ["i-clock", "draft", `Drafted: ${act} · waiting for a dispatcher`],
    APPROVED: ["i-approved", "ok", `Approved: ${act} · by ${who}${at ? ` · ${at}` : ""}`],
    EDITED: ["i-approved", "ok", `Approved with edits: ${act} · by ${who}${at ? ` · ${at}` : ""}`],
    REJECTED: ["i-rejected", "serious", `Rejected by ${who}${at ? ` · ${at}` : ""}`],
    SUPERSEDED: ["i-superseded", "off", "Replaced by a newer draft"],
  };
  const [ic, tone, text] = M[a.status] || M.DRAFT;
  return el("span", { class: `adv adv--${tone}` }, icon(ic), el("span", { text }), a.status === "EDITED" ? icon("i-pencil") : null);
}

// ------------------------------------------------------------------ Details › Flights heading in (R8.3)

const FLIGHTS_FIRST = 5;

// One flight as a row that opens This flight: the proxy flight, what it stands in for and its
// level, the entry, and the advisory's state in a word. The rows are grouped "Inside now" and
// "Heading in", so a row inside says nothing more about its entry; one heading in gives its time.
const ADV_WORD = { DRAFT: ["Advisory waiting", "i-clock"], APPROVED: ["Advisory approved", "i-approved"], EDITED: ["Approved with edits", "i-approved"], REJECTED: ["Advisory rejected", "i-rejected"], SUPERSEDED: ["Advisory replaced", "i-superseded"] };
function flightRow(D, f, ui, allStale = false, hand = null) {
  const p = f.properties;
  const plane = icon("i-aircraft", "icon dk-plane");
  plane.style.transform = `rotate(${p.track_deg || 0}deg)`;
  const entry = p.inside ? null : `in ${p.minutes_to_entry} min (est.)`;
  const lvl = p.alt_baro_ft != null ? fl(p.alt_baro_ft) : "level unknown";
  const old = p.stale ? `position ${Math.max(1, Math.round(p.ageS / 60))} min old` : null;
  const adv = D.advByFlight.get(`${p.hex}:${p.volcano_id}`);
  const oldShown = allStale ? null : old;
  const [advWord, advIcon] = adv ? ADV_WORD[adv.status] || ADV_WORD.DRAFT : [null, null];
  // no advisory because the assistant did not run: the row says the fact, the list's note says why and
  // what to do, once (D53, review clutter 5)
  const handRow = hand?.flights.find((x) => x.key === `${p.hex}:${p.volcano_id}`) || null;
  const handMeta = handRow ? el("span", { class: "dk-adv dk-adv--hand" }, el("span", { text: "No advisory" }), handRow.must ? dkChip("Must do", { kind: "must", title: "Code requires this work this run" }) : null) : null;
  return dkLinkRow({
    dot: plane,
    title: entry ? [p.proxy_flight, " ", el("span", { class: "dk-entry" }, entry)] : p.proxy_flight,
    sub: [`${lvl} · real aircraft ${p.callsign || String(p.hex || "").toUpperCase()}`, oldShown ? [" · ", el("span", { class: "dk-warn", text: oldShown })] : null, p.crew_report ? [" · ", el("span", { class: "dk-crewword" }, icon("i-pin", "icon"), "crew report on this route")] : null],
    meta: handMeta || (adv ? el("span", { class: `dk-adv dk-adv--${adv.status.toLowerCase()}` }, icon(advIcon), el("span", { text: advWord })) : el("span", { class: "dk-adv", text: "No advisory yet" })),
    dataset: { flight: f.id ?? p.hex, focus: `flight-${p.hex}` },
    label: `${p.proxy_flight}, proxy for ${p.callsign || p.hex}, ${p.inside ? "inside TEPHRA's area now" : `enters in ${p.minutes_to_entry} minutes, estimated`}, ${lvl}${old ? `, ${old}` : ""}${p.crew_report ? ", crew report of ash on this route" : ""}${handRow ? `, no advisory: ${blockPhrase(hand.block)}, plan by hand${handRow.must ? ", must do" : ""}` : adv ? `, ${advWord.toLowerCase()}` : ""}. Show this flight.`,
    cls: ui?.selFlight?.hex === p.hex ? "is-picked" : null,
  });
}

export function coverageWords(D, store) {
  const adsb = store.feeds.find((f) => f.feed === "adsb");
  const replay = D.mode === "REPLAY";
  if (adsb && adsb.status === "OK") return "Aircraft coverage is patchy: an empty map is not an empty sky. Entry times are estimates: a straight line from the last position.";
  if (adsb?.status === "STALE") return "Aircraft data is stale: the last good positions are shown, and an empty map is not an empty sky.";
  if (adsb?.status === "ERROR") return "Aircraft data is failing: the last good positions are shown, and an empty map is not an empty sky.";
  if (replay) return "No aircraft data in this recording.";
  return `Aircraft data is ${adsb?.status === "DISABLED" ? "off" : "not working"}: an empty map is not an empty sky.`;
}

export function renderFlights(D, store, ui, target = $("flights")) {
  if (!D) { target.replaceChildren(el("div", { class: "skeleton" }), el("div", { class: "skeleton" })); return; }
  // Scoped to the selected volcano (or the empty area), so the story, this list and the map count
  // the same flights; the rest are one click away.
  const area = D.area;
  const scopeName = D.sit ? D.sit.volcano_name : area ? area.name : null;
  const inScope = (f) => (D.sit ? f.properties.volcano_id === D.selected : area ? (D.vents.get(f.properties.volcano_id) ? inBbox(D.vents.get(f.properties.volcano_id), area.bbox) : false) : true);
  const flights = D.exposed.filter(inScope);
  const others = new Map();
  for (const f of D.exposed) if (!inScope(f)) others.set(f.properties.volcano_id, (others.get(f.properties.volcano_id) || 0) + 1);
  const inside = flights.filter((f) => f.properties.inside).length;
  const heading = flights.length - inside;
  const nextIn = Math.min(...flights.filter((f) => !f.properties.inside).map((f) => f.properties.minutes_to_entry));
  const crew = crewList(D, ui);
  // When every position is old (a stale feed), say it once in the header, not on every row.
  const allStale = flights.length > 1 && flights.every((f) => f.properties.stale);
  const oldest = allStale ? Math.max(...flights.map((f) => Math.max(1, Math.round(f.properties.ageS / 60)))) : 0;
  const head = dkHeader({
    id: "flights-head",
    sub: allStale ? el("span", { class: "dk-warn", text: `Every position is old: up to ${oldest} min.` }) : null,
    // the counts are the tiles' and the groups' to say; the header pill only marks the empty case
    pills: [flights.length ? null : dkPill("ok", "None projected")],
    title: flights.length ? `${flights.length} RFA ${flights.length === 1 ? "flight" : "flights"} in or heading into TEPHRA's estimated area${scopeName ? ` at ${scopeName}` : ""}` : `No RFA flight is projected to enter TEPHRA's area${scopeName ? ` at ${scopeName}` : ""}.`,
  });
  const tiles = flights.length || crew ? dkTiles([
    { label: "Inside now", value: String(inside), tone: inside ? "inside" : null },
    { label: "Heading in", value: String(heading), sub: heading ? `first in ${nextIn} min (est.)` : null },
    crew ? { label: "On a crew report's route", value: String(crew.n), tone: "plain" } : null,
  ], "Flights in numbers") : null;
  const note = dkNote("info", `RFA (Ring of Fire Air) is a fictional airline. Each flight number stands in for a real aircraft. ${coverageWords(D, store)}`);
  const othersBox = others.size ? dkGroup("Other volcanoes", null, el("div", { class: "dk-actions" }, ...[...others].map(([vid, n]) => {
    const name = D.sits.find((x) => x.volcano_id === vid)?.volcano_name || vid;
    return el("button", { type: "button", class: "btn btn--small", dataset: { act: "select", vid, focus: `others-${vid}` }, text: `+${n} heading in at ${name}` });
  }))) : null;
  const hand = handPlanOf(D, store, aiStateNow(D, store));
  const handHere = hand.flights.filter((x) => flights.some((f) => `${f.properties.hex}:${f.properties.volcano_id}` === x.key)).length;
  // why those rows have no advisory and what to do, said once for the list
  // paused: what is missing and what to do, the cause behind "Why ›" (docs/UI-AI-QUIET.md 8.6)
  const whose = handHere === flights.length ? (handHere === 1 ? "this flight" : `these ${handHere} flights`) : `${handHere} of these flights`;
  const handNote = handHere ? dkNote("caution", [el("p", {}, hand.block.paused ? `No advisory drafts yet for ${whose}. ` : `No advisory for ${whose}: ${hand.block.undone ? "the Coordinator left them for the Desk" : blockPhrase(hand.block)}. `, `Plan ${handHere === 1 ? "it" : "them"} by hand. `,
    el("a", { class: "link-btn", href: "/desk", target: "_blank", rel: "noopener", text: "Open the Desk ›" }), hand.block.paused ? [" ", whyLink("flights-why")] : null)], { role: "status" }) : null;
  const group = (title, aside, rows, key) => (rows.length ? dkGroup(title, aside, dkList(rows.map((f) => flightRow(D, f, ui, allStale, hand)), { first: FLIGHTS_FIRST, key, label: title })) : null);
  const list = flights.length
    ? [handNote, group("Inside now", null, flights.filter((f) => f.properties.inside), "flights-inside"), group("Heading in", "soonest first", flights.filter((f) => !f.properties.inside), "flights-heading")]
    : dkEmpty("No flight heading in", "TEPHRA projects each RFA flight's last position along its track and level.");
  target.replaceChildren(dkSection("flights-head", head, tiles, ...[list].flat(), crew?.node, note, othersBox));
}

// RFA flights only a crew report of ash flags (not TEPHRA's area): their own short list, so
// This flight opens from here too (UI-DESIGN 5.7).
function crewList(D, ui) {
  const flagged = D.crewFlights
    .map((f) => [f, D.crew.flagByHex.get(f.properties.hex)])
    .filter(([, flag]) => flag)
    .sort(([, a], [, b]) => a.minutes_to_entry - b.minutes_to_entry);
  if (!flagged.length) return null;
  return { n: flagged.length, node: dkGroup(`On the route of a crew report of ash · ${flagged.length}`, "operator policy A",
    dkList(flagged.map(([f, flag]) => {
      const p = f.properties;
      const lvl = p.alt_baro_ft != null ? fl(p.alt_baro_ft) : "level unknown";
      const when = flag.reporter ? "reported ash" : flag.inside_now ? "inside now" : `in ${flag.minutes_to_entry} min`;
      return dkLinkRow({
        dot: icon("i-aircraft", "icon dk-plane dk-plane--crew"), title: [p.proxy_flight, " ", el("span", { class: "dk-entry", text: when })],
        sub: [`${lvl} · real aircraft ${p.callsign || String(p.hex || "").toUpperCase()} · `, el("span", { class: "dk-crewword" }, icon("i-pin", "icon"), flag.line)],
        dataset: { flight: f.id ?? p.hex, focus: `flight-${p.hex}` }, cls: ui?.selFlight?.hex === p.hex ? "is-picked" : null,
        label: `${p.proxy_flight}, proxy for ${p.callsign || p.hex}, ${flag.line}, ${when}, ${lvl}. Show this flight.`,
      });
    }), { first: 5, key: "flights-crew" })) };
}

// ------------------------------------------------------------------ Details › How TEPHRA decided (R8.3, R12.7)

export function traceLines(store, D, ui) {
  const sel = D?.selected;
  const all = ui.traceScope === "all";
  return store.trace.filter((t) => all || !t.volcano_id || t.volcano_id === sel);
}

const TRACE_RUNS_FIRST = 8;
const LEVEL_TONE = { error: "serious", warn: "caution" };

// Steps that say the same thing collapse into one row (docs/UI-DETAILS-PANELS.md 2.7): the
// sentence with its varying numbers as a range, how many times and when; every step one tap in,
// the raw lines under one Technical detail.
function traceRun(run, ui, stub, ai) {
  const t0 = run.items[0];
  // an assistant step that did not run is a caution, one row per cause (D62); red stays for the picture
  const cause = t0._cause ? ai.causes.find((c) => c.key === t0._cause) : null;
  const tone = cause ? "caution" : LEVEL_TONE[t0.level] || null;
  const [ic] = ACTOR[t0.actor] || ["i-system"];
  const who = actorWords(t0.actor, stub, t0.message);
  const nums = cause ? run.items.map((t) => /(\d+) mandatory item/.exec(t.message)?.[1]).filter(Boolean).map(Number) : [];
  const range = nums.length ? (Math.min(...nums) === Math.max(...nums) ? String(nums[0]) : `${Math.min(...nums)}–${Math.max(...nums)}`) : null;
  const row = runRow(run, {
    key: `trace-${run.key}`, tone, dot: tone ? null : icon(ic, "icon dk-actor"),
    sub: cause && cause.helperKey === "duty" && range ? `${range} must-do ${range === "1" ? "job" : "jobs"} per run went to the Desk` : stepWho(t0.stage, who),
    titleOf: cause ? () => `${causeTitle(cause)}.` : null,
    extra: cause?.link ? dkLink(cause.link[0], { act: "details-sec", sec: cause.link[1], focus: `trace-go-${cause.key}` }) : null,
    lineOf: (t) => plainLine(t.message),
    rawOf: (t) => `${hhmmssz(t._t)} · ${t.stage} · ${(ACTOR[t.actor] || [null, String(t.actor || "")])[1]} · ${t.message}`,
  });
  if (run.items.some((t) => ui.freshTrace?.has(t.id))) row.classList.add("is-new");
  return row;
}
// Which step it was and who did it: "Flight check · done by code", "Flight planner · code only".
const STAGE_WORD = {
  DUTY: "Coordinator", PLUME: "Plume reader", SATELLITE: "Satellite reader", PLANNER: "Flight planner", DRAFTER: "Drafter", RECOVERY: "Recovery planner",
  EXPOSURE: "Flight check", CONE: "TEPHRA's estimate", DISCREPANCY: "Disagreement check", DOCS: "Paperwork", MESSAGES: "Messages", NOTICE: "Notices", ASK: "Ask",
  DESK: "Desk", POLL: "Data feeds",
};
function stepWho(stage, who) {
  const name = STAGE_WORD[stage] || (stage ? stage.charAt(0) + stage.slice(1).toLowerCase() : "");
  const by = /^by /.test(who) ? `done ${who}` : who;
  return [name, by].filter(Boolean).join(" · ");
}

export function renderTrace(D, store, ui, conn, target = $("trace")) {
  const lines = traceLines(store, D, ui);
  if (!D) { target.replaceChildren(el("div", { class: "skeleton" })); return; }
  const stub = D?.state.llm?.backend === "stub";
  const ai = aiStateNow(D, store);
  // assistant steps that did not run, keyed by cause (helper + reason class, never by their words)
  const causeOf = new Map(ai.causes.flatMap((c) => c.items.filter((x) => x.src?.id).map((x) => [x.src.id, c.key])));
  const problems = lines.filter((t) => t.level === "error" || t.level === "warn");
  const aiErr = lines.filter((t) => causeOf.has(t.id));
  const errors = lines.filter((t) => t.level === "error" && !causeOf.has(t.id)).length;
  const causesHere = new Set(aiErr.map((t) => causeOf.get(t.id)));
  const shown = ui.traceFilter === "problems" ? problems : lines;
  const runs = collapseRuns(shown.map((t) => ({ ...t, _t: ms(t.at), _cause: causeOf.get(t.id) || null })), {
    textOf: (t) => (t._cause ? `cause ${t._cause}` : plainLine(t.message)), timeOf: (t) => t._t, groupOf: (t) => `${t.stage}|${t.level}|${t._cause ? "" : t.actor}` });
  const seg = (label, act, key, opts) => el("div", { class: "seg", role: "group", "aria-label": label },
    ...opts.map(([v, text]) => el("button", { type: "button", "aria-pressed": (ui[key] || opts[0][0]) === v ? "true" : "false", dataset: { act, [act === "trace-scope" ? "scope" : "filter"]: v, focus: `${act}-${v}` }, text })));
  const head = dkHeader({
    id: "trace-head",
    pills: [conn.lostAt ? dkPill("caution", `Paused at ${hhmmz(conn.lostAt)}`) : dkPill("info", "Updating", "New steps appear here as they happen")],
    title: `${plural(lines.length, "step")}, newest first. Repeats are grouped.`,
  });
  const tiles = dkTiles([
    { label: "Steps", value: lines.length.toLocaleString("en"), sub: ui.traceScope === "all" ? "every volcano" : "this volcano and general" },
    { label: "Problems", value: String(problems.length - aiErr.length + causesHere.size), tone: errors ? "serious" : problems.length ? "caution" : "ok",
      sub: [errors ? `${errors} failed` : null, plural(problems.length - errors - aiErr.length, "warning"), aiErr.length ? `Assistant: ${causesHere.size === ai.causes.length ? plural(causesHere.size, "cause") : `${causesHere.size} of ${plural(ai.causes.length, "cause")}`} (${plural(aiErr.length, "step")})` : null].filter(Boolean).join(" · ") },
  ], "Steps in numbers");
  const controls = el("div", { class: "dk-actions" },
    seg("Which steps", "trace-scope", "traceScope", [["volcano", "This volcano"], ["all", "Everything"]]),
    seg("Which kind", "trace-filter", "traceFilter", [["all", "All"], ["problems", "Problems only"]]));
  const list = runs.length
    ? dkList(runs.map((r) => traceRun(r, ui, stub, ai)), { first: TRACE_RUNS_FIRST, key: "trace-all", more: `Show all ${runs.length} (${plural(shown.length, "step")})` })
    : dkEmpty(ui.traceFilter === "problems" ? "No problems in these steps" : "No steps yet", null);
  if (runs.length) { list.setAttribute("role", "log"); list.setAttribute("aria-live", "off"); list.setAttribute("aria-label", "How TEPHRA decided, newest first"); }
  target.classList.toggle("is-stale", !!conn.lostAt);
  target.replaceChildren(dkSection("trace-head", head, tiles, controls, list,
    el("div", { class: "dk-abouts" }, dkAbout("How to read this", "trace", "Each step in plain words. Steps that say the same thing are one row with how many times and when. Open a row for each step. Lines TEPHRA has no plain wording for are shown as written, and the raw line is always under Technical detail."))));
}

// ------------------------------------------------------------------ Details › the ash (R8.3)

export function hypothesisBanner(sit) {
  return dkNote("caution", `HYPOTHESIS: no valid official product for ${sit.volcano_name}. TEPHRA's area is a hypothesis built from the observatory report. Advisories are limited to MONITOR or HOLD.`, { role: "note" });
}

// What the official reports say (R8.3 `sources`): which reports name the volcano, then one row per
// kind (the newest of each), official first. A row opens to its five facts in plain words, its
// own words, the raw text and its ids.
export function sourcesSection(D, sit) {
  const byKind = Object.fromEntries(sit.cards.map((c) => [c.kind, c]));
  const order = [byKind.SIGMET, byKind.VAA, byKind.VONA].filter(Boolean);
  const lag = sit.discrepancies.find((d) => d.kind === "LAG");
  const dirD = sit.discrepancies.find((d) => d.kind === "DIRECTION_MISMATCH" && d.aspect === "direction");
  const ROW = { direction: "move", polygon: "move", top: "height", base: "height", ash_observed: "seen", presence: "head" };
  const flagged = new Map();
  for (const d of sit.discrepancies) {
    const row = ROW[d.aspect];
    if (!row || d.severity === "INFO") continue;
    const ids = d.kind === "DIRECTION_MISMATCH" ? Object.keys(d.values).filter((s) => s.startsWith("VONA:")) : Object.keys(d.values);
    for (const sid of ids) flagged.set(`${sid}|${row}`, d);
  }
  const vent = D.vents.get(sit.volcano_id);
  const value = (card, row) => {
    const f = card.display_fields || {};
    if (row === "seen") {
      if (lag?.values[card.source_id]) return plainValue(lag.values[card.source_id]);
      if (card.kind === "VONA") return f.Issued ? `${f.Issued.split("/")[1] || f.Issued}` : "—";
      if (card.kind === "VAA") return plainValue(f.Observation) || "—";
      return plainValue(f.Observed) || "—";
    }
    if (row === "height") {
      if (card.kind === "VONA") return f["Cloud top"] ? plainValue(f["Cloud top"].replace(/\s*\(.*\)$/, "")) : "—";
      return f.Band || "—";
    }
    if (row === "move") return plainValue(plainMove(dirD?.values[card.source_id] || f.Movement)) || "—";
    if (row === "valid") {
      if (card.kind === "SIGMET") return card.valid_to ? `until ${hhmmz(ms(card.valid_to))}` : "—";
      if (card.kind === "VAA") {
        const m = /(\d{8})\/(\d{4})Z/.exec(f["Next advisory"] || "");
        return m ? `next by ${m[2]}Z` : f["Next advisory"] || "—";
      }
      return "—";
    }
    if (row === "code") return card.kind === "SIGMET" ? "—" : plainValue(f["Colour code"]) || "—";
    return "—";
  };
  const rows = [["seen", "Seen"], ["height", "Height"], ["move", "Movement"], ["valid", "Valid"], ["code", "Alert colour"]];
  // An empty value says why in words, the same words for every source (R12.4, review 2, item 8).
  const shown = (card, row) => {
    const v = value(card, row);
    if (v !== "—") return v;
    return row === "code" && card.kind === "SIGMET" ? "not in a SIGMET" : row === "valid" && card.kind === "VONA" ? "no end time stated" : "not given";
  };
  const has = (k) => order.some((c) => !c.missing && c.kind === k);
  const official = ["SIGMET", "VAA"].filter(has);
  const lead = official.length ? `The newest ${official.join(" and ")} (official, binding)` : "No official report";
  const summary = `${lead}${has("VONA") ? " and the observatory's VONA (supporting)" : ""} ${official.length || has("VONA") ? "name" : "names"} ${sit.volcano_name}.`;
  const sourceRow = (card) => {
    const observer = card.kind === "VONA";
    const kind = KIND_LABEL[card.kind] || card.kind;
    if (card.missing) {
      const hyp = D.coneOf(sit.volcano_id)?.properties.mode === "HYPOTHESIS" && !observer;
      const word = UNREAD[card.missing_reason] || (hyp ? "No valid official product" : "None in force");
      return dkRow({ key: `src-${card.kind}`, dot: "off", title: word, sub: [kind, card.missing_note ? ` · ${card.missing_note}` : "", " · Absence is not evidence of no ash."], cls: "dk-row--muted" });
    }
    const t = ms(card.issued_at);
    const [tone, sid, word, long] = EVID[card.evidence] || EVID.UNKNOWN;
    const flags = rows.filter(([r]) => flagged.get(`${card.source_id}|${r}`));
    const headFlag = flagged.get(`${card.source_id}|head`);
    const glance = [value(card, "height"), value(card, "move"), value(card, "valid")].filter((v) => v && v !== "—" && !/^not (given|stated)$/.test(v)).join(" · ");
    const evidColour = tone === "seen" ? "var(--c-ok)" : tone === "est" ? "var(--c-info)" : tone === "off" ? "var(--c-off)" : "var(--c-caution)";
    let dayNight = null;
    if (observer && vent && Number.isFinite(t)) {
      const h = solarHour(t, vent[0]);
      const hh = Math.floor(h), mm = Math.round((h - hh) * 60) % 60;
      dayNight = `${isNight(t, vent[0]) ? "Night" : "Day"} at the vent · ${pad(hh)}:${pad(mm)} local solar`;
    }
    const f = card.display_fields || {};
    const quotes = (QUOTED[card.kind] || []).filter((k) => f[k]).map((k) => el("p", { class: "cmp-quote__line" }, el("span", { class: "cmp-quote__label", text: `${k}: ` }), el("q", { text: f[k] })));
    return dkRow({
      key: `src-${card.kind}`,
      dot: flags.length || headFlag ? "caution" : null,
      edge: observer ? "observer" : "official",
      title: observer ? `VONA ${hhmmz(t)}` : card.title,
      sub: [kind, glance ? ` · ${glance}` : ""],
      foot: [el("span", { class: "dk-evid", title: long }, st(sid, evidColour), word), card.stale ? el("span", { class: "dk-warn", text: `Stale: last good copy ${age(card.stale_age_s)} old` }) : null, flags.length ? el("span", { class: "dk-warn", text: `${flags.length} ${flags.length === 1 ? "value disagrees" : "values disagree"}` }) : null],
      meta: el("span", {}, el("span", { class: "mono", text: hhmmz(t) }), el("br"), el("span", { text: `${age((D.now - t) / 1000)} ago` })),
      body: [
        dkFacts(rows.map(([r, label]) => {
          const fl_ = flagged.get(`${card.source_id}|${r}`);
          return [label, shown(card, r), fl_ ? { tone: "caution", flag: "(flagged: disagrees)" } : { mono: r !== "code" && r !== "move" }];
        })),
        dayNight ? el("p", { class: "dk-sub__note", text: dayNight }) : null,
        quotes.length ? el("div", { class: `dk-sub cmp-quote${observer ? " cmp-quote--observer" : ""}` }, el("p", { class: "dk-sub__title", text: "In its own words" }), ...quotes) : null,
        el("div", { class: "dk-actions" }, el("button", { type: "button", class: "btn btn--small", dataset: { act: "raw", kind: card.kind, focus: `raw-${card.kind}` }, "aria-label": `Raw text of ${card.title}` }, icon("i-raw-text"), "Raw text")),
        dkTech(`${card.title}: ${card.source_id} · #${card.sha256_short || ""}`),
      ],
    });
  };
  const chips = order.filter((c) => !c.missing).map((c) => {
    const t = ms(c.issued_at);
    const old = Number.isFinite(t) && D.now - t > 6 * 3600e3;
    return dkChip(`${c.kind} · ${age((D.now - t) / 1000)} ago`, { kind: old ? "caution" : c.kind === "VONA" ? "observer" : "official" });
  });
  const nOfficial = official.length;
  return dkSection("h-sources",
    dkHeader({ id: "h-sources", pills: [nOfficial ? dkPill("ok", `${nOfficial} official ${nOfficial === 1 ? "report" : "reports"} in force`) : dkPill("caution", "No official report")], title: summary, chips }),
    el("p", { class: "dk-legend" }, el("span", { class: "dk-swatch dk-swatch--official" }), "official report ", el("span", { class: "dk-swatch dk-swatch--observer" }), "observatory ", st("st-caution", "var(--c-caution)"), " disagrees with another source"),
    dkList(order.map(sourceRow), { first: 3, key: "src" }),
    el("div", { class: "dk-actions" }, el("button", { type: "button", class: "btn btn--small", dataset: { act: "raw", kind: "", focus: "src-side" } }, icon("i-raw-text"), "Raw texts side by side (C)")),
    dkGroup("Why this volcano is shown", null, dkList([dkRow({ key: "src-why", dot: "info", title: `Why TEPHRA shows ${sit.volcano_name}`, sub: plural(sit.active_reasons.length, "reason"), body: el("ul", { class: "dk-bullets" }, ...sit.active_reasons.map((r) => el("li", { text: r }))) })], { key: "src-why" })),
    el("div", { class: "dk-abouts" }, dkAbout("How to read this", "src", "One row per kind of report, the newest of each. A pink edge marks an official report (SIGMET, VAA): it is binding. A blue edge marks the observatory (VONA): it supports. A value that disagrees with another source carries the caution shape.")));
}

// Long verbatim fields stay out of the facts: quoted lines in the row body, by source kind.
const QUOTED = { VAA: ["Info source", "Remarks"], VONA: ["Activity", "Cloud height"] };

// Where the sources disagree (R8.3 `disagree`): CAUTION and SERIOUS first; minor ones folded.
const SEV_WORD = { WARNING: ["serious", "Serious"], CAUTION: ["caution", "Caution"], INFO: ["info", "Minor"] };
export function disagreeSection(D, sit, ui) {
  const items = sit.discrepancies.slice().sort((a, b) => (SEV_RANK[b.severity] || 0) - (SEV_RANK[a.severity] || 0));
  const check = items.filter((d) => d.severity !== "INFO");
  const info = items.filter((d) => d.severity === "INFO");
  const minor = info.map((d) => {
    const [kind, headline] = kindOf(d);
    return { _t: NaN, text: headline, why: capFirst(EXPLAIN[d.kind] ? EXPLAIN[d.kind].replace(/^Harmless: /, "") : ""), raw: `${kind} · ${d.id || ""} · ${d.summary}`, detail: machineText(d.summary) };
  });
  for (const card of sit.cards) {
    if (card.missing || !NON_OBS.has(card.evidence)) continue;
    minor.push({ _t: NaN, text: `${card.kind} could not see the ash`, why: "Not evidence of no ash. It never shrinks TEPHRA's area or weakens an advisory.", raw: `NOT OBSERVED · ${card.source_id}`, detail: null });
  }
  const worst = check.some((d) => d.severity === "WARNING") ? "serious" : "caution";
  const headText = check.length
    ? `${check.length} to check${minor.length ? ` · ${minor.length} minor` : ""}`
    : `Nothing that needs checking${minor.length ? ` (${minor.length} minor difference${minor.length === 1 ? "" : "s"})` : ""}`;
  const runs = collapseRuns(minor, { textOf: (m) => m.text, timeOf: () => NaN });
  const minorRows = runs.map((r) => dkRow({
    key: `dis-minor-${r.key}`, dot: "info", title: r.label, badge: r.count > 1 ? times(r.count) : null, sub: r.items[0].why,
    body: [r.items.some((m) => m.detail) ? dkList(r.items.filter((m) => m.detail).map((m) => el("div", { class: "dk-line" }, el("span", { class: "dk-line__text", text: m.detail }))), { first: 3, key: `dis-minor-d-${r.key}` }) : null, dkTech(...r.items.map((m) => m.raw))],
  }));
  return dkSection("h-dis",
    dkHeader({ id: "h-dis", pills: [check.length ? dkPill(worst, `${check.length} to check`) : dkPill("ok", "Nothing to check")], title: headText }),
    items.length || minor.length ? dkTiles([
      { label: "To check", value: String(check.length), tone: check.length ? worst : "ok" },
      { label: "Minor", value: String(minor.length), tone: "plain", sub: "usual, folded below" },
    ], "Disagreements in numbers") : dkEmpty("No differences found between the reports in force.", null),
    check.length ? dkGroup("To check", null, dkList(check.map((d) => disRow(D, sit, d, ui)), { first: 5, key: "dis-check" })) : null,
    minor.length ? dkList(minorRows, { first: 0, key: "dis-minor", more: `Minor differences (${minor.length})` }) : null);
}

function disRow(D, sit, d, ui) {
  const [tone, word] = SEV_WORD[d.severity] || SEV_WORD.INFO;
  const [kind, headline] = kindOf(d);
  let explain = EXPLAIN[d.kind] || null;
  const vals = Object.entries(d.values);
  if (d.kind === "DIRECTION_MISMATCH" && d.aspect === "direction") {
    const offV = vals.find(([k]) => !k.startsWith("VONA:"))?.[1] || "";
    const obsV = vals.find(([k]) => k.startsWith("VONA:"))?.[1] || "";
    const offDeg = /\b(NNE|ENE|ESE|SSE|SSW|WSW|WNW|NNW|NE|SE|SW|NW|N|E|S|W)\b/.exec(offV)?.[1] || offV;
    const obsDeg = /\b(NNE|ENE|ESE|SSE|SSW|WSW|WNW|NNW|NE|SE|SW|NW|N|E|S|W)\b/.exec(obsV)?.[1] || obsV.replace(/^moving /, "");
    explain = el("span", { class: "dis__explain" }, "Official area moves ", el("b", { class: "off", text: offDeg }), ". Observatory reports ash moving ", el("b", { class: "obs", text: obsDeg }), `. ${Math.round(d.magnitude)}° apart.`);
  } else if (d.kind === "DIRECTION_MISMATCH" && d.aspect === "polygon") {
    const cone = D.coneOf(sit.volcano_id)?.properties;
    const sector = D.sectorOf(sit.volcano_id);
    let tail = "";
    if (cone?.mode === "WIDENED" && sector && D.rose) tail = pointInGeom(dest(D.rose.vent, D.rose.obsDeg, 15), sector.geometry) || pointInGeom(dest(D.rose.vent, D.rose.obsDeg, 15), D.coneOf(sit.volcano_id).geometry) ? " TEPHRA's area covers it." : "";
    else if (cone?.mode === "OFFICIAL") {
      const outcome = sit.assessment?.outcome;
      tail = D.state.llm?.backend === "stub" || outcome === "STUB" ? " TEPHRA has not widened the area (code only)."
        : outcome === "PENDING" ? " TEPHRA has not widened the area yet (Plume reader waiting)."
          : outcome === "MODEL_FAILED" ? " TEPHRA has not widened the area (Plume reader gave no result)." : " TEPHRA has not widened the area.";
    }
    explain = `A point 15 km along the observatory's drift is outside the official polygon.${tail}`;
  }
  const row = dkRow({
    key: `dis-${d.id}`, dot: tone, edge: tone, title: headline, sub: explain, badge: word,
    body: [el("p", { class: "dk-sub__note", text: machineText(d.summary) }),
      d.kind === "DIRECTION_MISMATCH" && D.rose ? el("div", { class: "dk-actions" }, el("button", { type: "button", class: "btn btn--small", dataset: { act: "frame", focus: `show-${d.id}` } }, icon("i-frame"), "Show on the map")) : null,
      dkTech(`${kind} · ${d.kind}/${d.aspect || ""} · ${d.severity} · ${d.id || ""}`)],
  });
  if (ui.freshDis?.has(d.id)) row.classList.add("is-new");
  return row;
}

const capFirst = (t) => (t ? t[0].toUpperCase() + t.slice(1) : t);

// TEPHRA's estimate (R8.3 `estimate`): the outcome sentence, the rule, who read it, valid until.
// "The Plume reader found nothing to add" only when a model read it (H1): a queued read is waiting, and
// an official-only volcano needed no read.
export function estimateOutcome(D, sit, cone) {
  const outcome = sit.assessment?.outcome;
  const stub = outcome === "STUB" || (!outcome && D.state.llm?.backend === "stub");
  if (cone.mode !== "OFFICIAL") return MODE_LINE[cone.mode] || "";
  if (stub) return "Same as the official area (code only, nothing added).";
  if (outcome === "MODEL_FAILED") return "Same as the official area: the Plume reader gave no result, nothing assessed beyond the official reports.";
  // a queued read waits in line; when it runs is said at the assistant's home (8.6)
  if (outcome === "PENDING") return "Same as the official area: the Plume reader's read waits in line.";
  if (outcome === "OFFICIAL_ONLY") return "Same as the official area: no Plume reader read was needed.";
  if (MODEL_READ.has(outcome)) return "Same as the official area: the Plume reader found nothing to add.";
  return MODE_LINE.OFFICIAL;
}

const MODE_PILL = { OFFICIAL: ["info", "Same as official"], WIDENED: ["tephra", "Wider than official"], HYPOTHESIS: ["caution", "Hypothesis"] };
export function areaSection(D, sit, ui) {
  const coneF = D.coneOf(sit.volcano_id);
  if (!coneF) return dkSection("h-area", dkHeader({ id: "h-area", title: "No TEPHRA estimate yet for this volcano." }));
  const cone = coneF.properties;
  const a = sit.assessment;
  const outcome = a?.outcome;
  const stub = outcome === "STUB" || (!outcome && D.state.llm?.backend === "stub");
  const [tone, word] = MODE_PILL[cone.mode] || ["info", cone.mode];
  // the model's name only where a model read it (Q5); a queued read says it waits (D44)
  const modelRead = MODEL_READ.has(outcome) && a?.model_id && a.model_id !== "none" && a.model_id !== "stub";
  const readBy = stub ? OUTCOME.STUB
    : outcome === "PENDING" ? `Plume reader waiting · ${OUTCOME.PENDING}.`
      : modelRead ? [aiMark(a.model_id, null, MARK.read("Plume reader")), " ", OUTCOME[outcome]] : OUTCOME[outcome] || "not given";
  const est = a?.estimate;
  let read = null;
  // "How the Plume reader read it" only for a reading a model gave and the checks passed (H2); the same
  // text written by code sits under "How TEPHRA built it", marked as code. Nothing is hidden.
  const why = est && (est.rationale || est.uncertainty_notes || (est.disagreements_explained || []).length);
  if (why && outcome !== "MODEL_FAILED") {
    const readings = (est.disagreements_explained || []).map((r) => {
      const lean = r.which_source_we_lean_on ? cardName(sit, r.which_source_we_lean_on) : null;
      return el("div", { class: "dk-prio" }, el("span", { class: "dk-prio__main" }, el("span", { class: "dk-prio__label", text: r.reading || "" }),
        lean || r.why ? el("span", { class: "dk-prio__why" }, lean ? dkChip(`Leans on ${lean}`) : null, r.why ? ` ${r.why}` : null) : null));
    });
    read = el("details", { class: "dk-about area__read", open: ui.readOpen ? true : null, dataset: { k: "area-read" } },
      el("summary", { dataset: { focus: "area-read" } }, icon("i-chevron-right", "icon dk-about__chev"), el("span", { text: modelRead ? "How the Plume reader read it" : "How TEPHRA built it" }), modelRead ? aiMark(a.model_id, null, MARK.read("Plume reader")) : el("span", { class: "dk-chip dk-chip--code", text: "Code-written" })),
      el("div", { class: "dk-about__body" },
        readings.length ? dkList(readings, { first: 5, key: "area-readings" }) : null,
        // code's own sentences say their clauses with the page's dot; a model's words stay as written
        est.rationale ? el("div", { class: "dk-sub" }, el("p", { class: "dk-sub__title", text: "Rationale" }), el("p", { class: "dk-quote", text: modelRead ? est.rationale : machineText(est.rationale) })) : null,
        est.uncertainty_notes ? el("div", { class: "dk-sub" }, el("p", { class: "dk-sub__title", text: "Uncertainty" }), el("p", { class: "dk-quote", text: modelRead ? est.uncertainty_notes : machineText(est.uncertainty_notes) })) : null));
  }
  return dkSection("h-area",
    cone.mode === "HYPOTHESIS" ? hypothesisBanner(sit) : null,
    dkHeader({ id: "h-area", pills: [dkPill(tone, word)], title: estimateOutcome(D, sit, cone), chips: [dkChip("Never smaller than any valid official area", { kind: "tephra" }), dkChip("An estimate, not a forecast")] }),
    dkTiles([
      { label: "Heights", value: band(cone.base_ft, cone.top_ft) },
      { label: "Valid until", value: hhmmz(ms(cone.valid_to)), sub: untilWords(ms(cone.valid_to) - D.now) },
      cone.mode !== "OFFICIAL" ? { label: "Confidence", value: `${Math.round((cone.confidence ?? 0) * 100)}%`, sub: "in the widening" } : null,
    ], "Estimate in numbers"),
    outcome === "MODEL_FAILED" ? dkNote("caution", `Plume reader gave no result: ${machineText(a?.estimate?.uncertainty_notes || "no usable model output")}. TEPHRA shows the official area only, and nothing was put in its place.`, { role: "status" }) : null,
    // A replay loop reuses the same model's reading of the same input; the label says so.
    dkFacts([["Reading", el("span", {}, readBy)], ["Answer", recordedWords(a?.recorded_answer) || null]]),
    read,
    dkTech(`Mode ${cone.mode} · label ${cone.label} · ${cone.cone_id || ""}`),
    el("div", { class: "dk-abouts" }, dkAbout("About the estimate", "area", "TEPHRA's estimate is an estimate, not a forecast. It is drawn as the amber dashed line, never smaller than the official area, which stays binding.")));
}
const untilWords = (dt) => (Number.isFinite(dt) ? (dt > 0 ? `in ${age(dt / 1000)}` : `${age(-dt / 1000)} ago`) : null);

// Decisions (R8.3 `decisions`): the counts first, then the list.
export function decisionsSection(D, store, ui, target = $("decisions")) {
  const all = store.advisories.slice().sort((a, b) => ms(b.updated_at) - ms(a.updated_at));
  const advs = all.filter((a) => a.status !== "SUPERSEDED");
  const superseded = all.filter((a) => a.status === "SUPERSEDED");
  const draft = advs.filter((a) => a.status === "DRAFT");
  const ok = advs.filter((a) => a.status === "APPROVED" || a.status === "EDITED");
  const rej = advs.filter((a) => a.status === "REJECTED");
  const capped = all.length >= 50;
  const serverWaiting = D.state.draft_count;
  const row = (a) => {
    const fresh = ui.freshDecisions?.has(a.id);
    const status = {
      DRAFT: ["i-clock", "var(--c-text-2)"], APPROVED: ["i-approved", "var(--c-ok)"], EDITED: ["i-approved", "var(--c-ok)"], REJECTED: ["i-rejected", "var(--c-serious)"],
    }[a.status] || ["i-clock", "var(--c-text-2)"];
    const when = a.status === "DRAFT" ? `drafted ${age((D.now - ms(a.created_at)) / 1000)} ago` : `${a.status === "REJECTED" ? "rejected" : "approved"} by ${deciderName(a)}${a.decided_at ? ` · ${hhmmz(ms(a.decided_at))}` : ""}${a.status === "EDITED" ? " · with edits" : ""}`;
    const r = el("a", { class: `dk-row dk-row--link dk-dec${fresh ? " is-stamped" : ""}`, href: `/desk#review/${encodeURIComponent(a.id)}`, target: "_blank", rel: "noopener", dataset: { adv: a.id } },
      el("span", { class: "dk-row__head" },
        el("span", { class: "dk-row__dot" }, icon(status[0], "icon", status[1])),
        el("span", { class: "dk-row__main" }, el("span", { class: "dk-row__title" }, el("b", { text: a.proxy_flight }), ` · ${actionText(a)}`),
          el("span", { class: "dk-row__sub", text: `${a.volcano_name} · ${when}` }),
          a.status === "REJECTED" && a.reject_reason ? el("q", { class: "dk-row__sub dk-reason", text: a.reject_reason }) : null),
        el("span"), el("span", { class: "dk-row__go", "aria-hidden": "true", text: "›" })));
    return r;
  };
  // flights with no draft because the assistant did not run: the dispatcher's work, here (D56)
  const hand = handPlanOf(D, store, aiStateNow(D, store));
  const waitingN = serverWaiting ?? draft.length;
  const handN = hand.flights.length;
  const head = dkHeader({
    id: "h-dec",
    pills: [serverWaiting === null ? dkPill("serious", "Count unknown") : waitingN ? dkPill("caution", "Waiting for a dispatcher") : handN ? dkPill("caution", "Nothing to approve") : dkPill("ok", "Nothing waiting")],
    title: all.length ? "Every advisory is a draft until a dispatcher decides on the Desk." : "No advisories yet. A draft appears when a flight's projected track enters TEPHRA's area.",
    sub: handN && !waitingN ? el("span", {}, hand.block.paused ? `No advisory drafts yet for the ${handN === 1 ? "flight" : `${handN} flights`}. ` : `No drafts: ${hand.block.undone ? "the Coordinator left its must-do flights for the Desk" : blockPhrase(hand.block)}. `,
      el("a", { class: "link-btn", href: "/desk", target: "_blank", rel: "noopener", text: "Plan by hand on the Desk ›" }), hand.block.paused ? [" ", whyLink("dec-why")] : null) : null,
  });
  const tiles = all.length ? dkTiles([
    { label: "Waiting", value: serverWaiting === null ? "unknown" : String(serverWaiting ?? draft.length), tone: serverWaiting === null ? "serious" : "caution", sub: serverWaiting === null ? "database error" : "all volcanoes" },
    { label: "Approved", value: String(ok.length), tone: ok.length ? "ok" : null, sub: capped ? "in the newest 50" : null },
    { label: "Rejected", value: String(rej.length), sub: capped ? "in the newest 50" : null },
  ], "Decisions in numbers") : null;
  const caption = all.length ? el("p", { class: "dk-foot", text: `The waiting count covers every advisory of this mode on the server. The lists below show the ${capped ? "newest 50 loaded" : `${all.length} loaded`}.` }) : null;
  const note = dkNote("info", "Approve on the Desk · nothing is sent anywhere. Approved text goes only to TEPHRA's own outbound queue. Nothing is sent to an aircraft or any real system.", { iconId: "i-outbound" });
  const groups = [];
  if (handN) {
    // the Coordinator's "Passed to the Desk" list, copied here where the dispatcher acts (D69)
    // the rows say no assistant word: the head above says why, once (review clutter 5). The Wall sees the
    // newest 50 advisories and not the Desk's handled marks; the Desk's list is the record (H3).
    const scope = [hand.must ? `${hand.must} must do first` : null, hand.partial ? "no advisory among the newest 50" : "no advisory", "mark each handled on the Desk"].filter(Boolean).join(" · ");
    groups.push(dkGroup(`To plan by hand · ${handN}`, scope, el("div", { id: "dec-hand", tabindex: "-1", class: "dk-anchor" }, dkList(hand.flights.map((x) => el("a", { class: "dk-row dk-row--link", href: "/desk", target: "_blank", rel: "noopener" },
      el("span", { class: "dk-row__head" },
        el("span", { class: "dk-row__dot" }, st("st-caution", "var(--c-caution)")),
        el("span", { class: "dk-row__main" }, el("span", { class: "dk-row__title" }, el("b", { text: x.p.proxy_flight }), ` · ${x.p.inside ? "inside now" : `in ${x.p.minutes_to_entry} min (est.)`}`, x.must ? [" ", dkChip("Must do", { kind: "must", title: "Code requires this work this run" })] : null),
          el("span", { class: "dk-row__sub", text: D.sits.find((v) => v.volcano_id === x.p.volcano_id)?.volcano_name || x.p.volcano_id })),
        el("span"), el("span", { class: "dk-row__go", "aria-hidden": "true", text: "›" })))), { first: 5, key: "dec-hand" }))));
  }
  if (draft.length) groups.push(dkGroup(`Waiting for a dispatcher · ${draft.length}`, "open on the Desk", dkList(draft.map(row), { first: 5, key: "dec-draft" })));
  if (ok.length) groups.push(dkGroup(`Approved · ${ok.length}`, null, dkList(ok.map(row), { first: 3, key: "dec-ok" })));
  if (rej.length) groups.push(dkGroup(`Rejected · ${rej.length}`, null, dkList(rej.map(row), { first: 3, key: "dec-rej" })));
  if (superseded.length) {
    const names = [...new Set(superseded.map((a) => a.proxy_flight))];
    groups.push(dkGroup(`Replaced by a newer draft · ${superseded.length}`, null, dkList([dkRow({ key: "dec-sup", dot: icon("i-superseded", "icon", "var(--c-off)"), title: `${plural(superseded.length, "earlier draft")}`, sub: names.length > 4 ? `${names.slice(0, 4).join(", ")} and ${names.length - 4} more` : names.join(", "), body: el("p", { class: "dk-sub__note", text: names.join(", ") }) })])));
  }
  target.replaceChildren(dkSection("h-dec", head, tiles, caption, note, ...groups));
}

// ------------------------------------------------------------------ Details › Height filter (8.4, R8.3)

const LEVEL_TRACK_H = 270;

export function renderLevels(D, ui) {
  const box = $("levels");
  const H = LEVEL_TRACK_H;
  const y = (ft) => (1 - levelFrac(ft)) * H;
  const track = el("div", { class: "levels__track", dataset: { act: "level-track" } });
  track.style.height = `${H}px`;
  track.append(el("div", { class: "levels__rail" }));
  const hc = D?.sit ? D.coneOf(D.sit.volcano_id)?.properties : null;
  const hazardOn = !!hc && ui.level.min === Math.max(0, hc.base_ft) && ui.level.max === Math.min(LEVEL_MAX, hc.top_ft);
  track.classList.toggle("levels__track--hazard", hazardOn);
  if (D?.sit) {
    const offs = D.official.filter((f) => f.properties.volcano_id === D.sit.volcano_id && f.properties.valid && f.properties.step === "now");
    if (offs.length) {
      const b0 = Math.min(...offs.map((f) => f.properties.base_ft)), t0 = Math.max(...offs.map((f) => f.properties.top_ft));
      const bar = el("div", { class: "levels__band levels__band--official", title: `Official band ${band(b0, t0)}` });
      bar.style.top = `${y(t0)}px`; bar.style.height = `${Math.max(3, y(b0) - y(t0))}px`;
      track.append(bar);
    }
    if (hc) {
      const bar = el("div", { class: "levels__band levels__band--tephra", title: `TEPHRA band ${band(hc.base_ft, hc.top_ft)}` });
      bar.style.top = `${y(hc.top_ft)}px`; bar.style.height = `${Math.max(3, y(hc.base_ft) - y(hc.top_ft))}px`;
      track.append(bar);
    }
    let n = 0;
    for (const f of D.aircraft) {
      const a = f.properties.alt_baro_ft;
      if (a == null || n++ > 60) continue;
      const t = el("div", { class: `levels__tick${f.properties.exposed ? " levels__tick--exposed" : ""}` });
      t.style.top = `${y(a)}px`;
      track.append(t);
    }
  }
  const sel = el("div", { class: "levels__sel" });
  sel.style.top = `${y(ui.level.max)}px`;
  sel.style.height = `${y(ui.level.min) - y(ui.level.max)}px`;
  track.append(sel);
  for (const ft of [0, 6000, 18000, 35000, 55000]) {
    const s = el("span", { class: "levels__scale", "aria-hidden": "true" }, el("span", { class: "levels__scale-label", text: fl(ft) }));
    s.style.top = `${y(ft)}px`;
    track.append(s);
  }
  const thumb = (which, ft, label) => {
    const t = el("div", { class: "levels__thumb", role: "slider", tabindex: "0", "aria-label": label, "aria-valuemin": "0", "aria-valuemax": String(LEVEL_MAX), "aria-valuenow": String(ft), "aria-valuetext": ft <= 0 ? "surface" : fl(ft), "aria-orientation": "vertical", "aria-keyshortcuts": "H", dataset: { thumb: which, focus: `thumb-${which}` }, text: fl(ft) });
    t.style.top = `${y(ft)}px`;
    return t;
  };
  track.append(thumb("max", ui.level.max, "Highest level shown"), thumb("min", ui.level.min, "Lowest level shown"));
  const all = levelIsAll(ui.level);
  const readout = all ? "All heights" : `${fl(ui.level.min)}–${fl(ui.level.max)}`;
  box.replaceChildren(el("div", { class: "dk" },
    el("header", { class: "dk-head" },
      el("div", { class: "dk-head__pills" },
        el("span", { class: `dk-pill dk-pill--${all ? "ok" : "caution"}` }, icon(all ? "st-ok" : "st-caution", "st", all ? "var(--c-ok)" : "var(--c-caution)"),
          el("span", { id: "levels-title", text: "Showing: " }), el("strong", { class: "levels__readout", "aria-live": "polite", text: readout })),
        all ? null : el("button", { type: "button", class: "link-btn", dataset: { act: "level-reset", focus: "lv-reset" }, text: "Reset" })),
      el("p", { class: "dk-head__sub", text: "Drag a handle or use the arrow keys. Official areas outside the heights are faded, never removed, and a pill on the map says so. FL350 is about 35,000 ft." })),
    el("div", { class: "dk-card levels__card" },
      el("div", { class: "levels__wrap" }, track,
        el("ul", { class: "levels__key" },
          el("li", {}, el("span", { class: "levels__sw levels__sw--official" }), "Official band"),
          el("li", {}, el("span", { class: "levels__sw levels__sw--tephra" }), "TEPHRA's band"),
          el("li", {}, el("span", { class: "levels__sw levels__sw--ac" }), "Aircraft (amber: RFA heading in)"))),
      el("div", { class: "levels__presets seg", role: "group", "aria-label": "Height presets" },
        ...[["all", "All"], ["hazard", "Hazard"], ["low", "≤FL180"], ["high", "≥FL180"]].map(([k, t]) =>
          el("button", { type: "button", dataset: { act: "level-preset", preset: k, focus: `lv-${k}` }, "aria-pressed": (k === "all" && all) || (k === "hazard" && hazardOn) ? "true" : "false", text: t }))))));
  box.dataset.h = String(H);
}

// ------------------------------------------------------------------ the time bar (R7)

// The timeline's events for the selected volcano: official reports, observatory notices, TEPHRA's
// disagreements, flights and decisions. Shared by the time bar and Details › Timeline history.
export function timelineEvents(D, store) {
  const sit = D?.sit;
  const out = [];
  if (!sit) return out;
  for (const card of sit.cards) {
    if (card.missing) continue;
    if (card.kind === "VONA") {
      for (const sid of [card.source_id, ...(card.extra_source_ids || [])]) {
        const t = idTime(sid);
        out.push({ lane: "observer", t, icon: sid === card.source_id ? "st-ok" : "st-off", cls: "tl__mark--observer", title: `VONA ${dayMonth(t)} ${hhmmz(t)}`, kind: "VONA", words: `Observatory notice (VONA) issued ${hhmmz(t)}` });
      }
    } else {
      const t = ms(card.issued_at);
      out.push({ lane: "official", t, icon: card.kind === "SIGMET" ? "st-stale" : "st-ok", cls: "tl__mark--official", title: `${card.title} issued ${hhmmz(t)}`, kind: card.kind, words: `${card.title} issued ${hhmmz(t)}`, vf: ms(card.valid_from), vt: ms(card.valid_to) });
    }
  }
  const seen = new Set();
  for (const t of store.trace) {
    if (t.volcano_id !== sit.volcano_id) continue;
    const k = `${t.stage}|${t.at.slice(0, 16)}`;
    if (seen.has(k)) continue;
    if (t.stage === "DISCREPANCY") { seen.add(k); out.push({ lane: "tephra", t: ms(t.at), icon: "st-caution", cls: "tl__mark--caution", title: `Disagreement found ${hhmmz(ms(t.at))}`, kind: "dis", words: `TEPHRA found a disagreement ${hhmmz(ms(t.at))}` }); }
    if (t.stage === "EXPOSURE" && t.flight_id) { seen.add(k); out.push({ lane: "tephra", t: ms(t.at), icon: "i-aircraft", cls: "tl__mark--tephra", title: `Flight heading in ${hhmmz(ms(t.at))}`, kind: "flight", words: `TEPHRA found a flight heading in ${hhmmz(ms(t.at))}` }); }
  }
  for (const a of store.advisories) {
    if (a.volcano_id !== sit.volcano_id || !a.decided_at) continue;
    const ok = a.status === "APPROVED" || a.status === "EDITED";
    const t = ms(a.decided_at);
    out.push({ lane: "tephra", t, icon: ok ? "i-approved" : "i-rejected", cls: ok ? "tl__mark--ok" : "tl__mark--serious", title: `${a.proxy_flight} ${ok ? "approved" : "rejected"} by ${deciderName(a)} ${hhmmz(t)}`, kind: "decision", words: `${a.proxy_flight} ${ok ? "approved" : "rejected"} by ${deciderName(a)} ${hhmmz(t)}` });
  }
  return out.filter((e) => Number.isFinite(e.t)).sort((a, b) => a.t - b.t);
}

export function lagOf(sit) {
  return sit?.discrepancies.find((d) => d.kind === "LAG") || null;
}

export function renderTimeline(D, store, ui, conn) {
  const box = $("timeline");
  if (!D) { box.replaceChildren(el("div", { class: "tl__meta" }, el("span", { class: "skeleton" }))); return; }
  const s = D.state, sit = D.sit;
  const t0 = D.now - 9 * 3600e3, t1 = D.now + 3 * 3600e3;
  const pct = (t) => `${(((t - t0) / (t1 - t0)) * 100).toFixed(3)}%`;
  const replay = s.mode === "REPLAY" && s.replay;
  box.classList.toggle("is-stale", !!conn.lostAt);
  box.classList.toggle("timebar--history", !!ui.historyOpen);

  // 1. mode and window
  const meta = el("div", { class: "tl__meta", title: "Times ending in Z are UTC" });
  let pill, recChips = [];
  if (replay) {
    const a = ms(s.replay.recorded_from), b = ms(s.replay.recorded_to);
    const loop = !!s.replay.window_from;
    const pa = loop ? ms(s.replay.window_from) : a, pb = loop ? ms(s.replay.window_to) : b;
    const p = Math.max(0, Math.min(1, (D.now - pa) / (pb - pa)));
    const bar = el("span");
    bar.style.width = `${(p * 100).toFixed(1)}%`;
    const pctText = `${Math.round(p * 100)}%`;
    meta.append(
      // the frame strip says REPLAY; here the icon marks the replay clock, and the time follows
      el("span", { class: "tl__mode", title: "Replay clock" }, icon("i-replay"), el("span", { class: "sr-only", text: "Replay clock" })),
      // The clock, then how far the recording has played. The recording's own span sits in the
      // tooltip and in History, not beside the 12 h axis, so two time scales never sit side by
      // side (review 2, item 12).
      el("span", { class: "tl__window", text: `${hhmmz(D.now)} · ${pctText} played`, title: `${loop ? "The replay loops over" : "Recording"} ${dayMonth(pa)} ${hhmmz(pa)} to ${dayMonth(pb)} ${hhmmz(pb)}` }),
      el("span", { class: "tl__progress", role: "progressbar", title: `${loop ? "The replay loops over" : "Recording"} ${dayMonth(pa)} ${hhmmz(pa)} to ${dayMonth(pb)} ${hhmmz(pb)}`, "aria-label": loop ? "Replay loop progress" : "Replay progress", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(Math.round(p * 100)), "aria-valuetext": `${pctText} of the recording, ${hhmmz(pa)} to ${hhmmz(pb)}` }, bar));
    recChips = [
      `${loop ? "Replay loops" : "Recording"} ${pb - pa > 20 * 3600e3 ? `${dayMonth(pa)} ${hhmmz(pa)} – ${dayMonth(pb)} ${hhmmz(pb)}` : `${hhmmz(pa)}–${hhmmz(pb)}`}`,
      `${pctText} played`,
    ];
    pill = `⟲ ${hhmmz(D.now)} · ${ui.steps === "now" ? "Now" : { f6: "+6 h", f12: "+12 h", f18: "+18 h", all: "All steps" }[ui.steps]} ▾`;
  } else {
    meta.append(el("span", { class: "tl__mode tl__mode--live" }, icon("i-live"), "Live"), el("span", { class: "tl__window", text: "9 h back, 3 h ahead" }));
    pill = `● ${hhmmz(D.now)} · ${ui.steps === "now" ? "Now" : { f6: "+6 h", f12: "+12 h", f18: "+18 h", all: "All steps" }[ui.steps]} ▾`;
  }
  if (conn.lostAt) meta.append(el("span", { class: "tl__window tl__stale", text: `last update ${hhmmz(conn.lostAt)}` }));
  const tp = $("time-pill");
  if (tp) { tp.textContent = pill; tp.setAttribute("aria-expanded", document.body.classList.contains("tl-sheet") ? "true" : "false"); }

  // 2. the scrubber: one slim track; with History open the marks move to three lanes above it
  const events = timelineEvents(D, store).filter((e) => e.t >= t0 && e.t <= t1);
  const marks = [];
  const mark = (e) => {
    const b = el("button", { type: "button", class: `tl__mark ${e.cls}`, title: e.title, "aria-label": e.title, tabindex: "-1", dataset: { act: "tl-mark", kind: e.kind, focus: `tl-${marks.length}` } }, icon(e.icon, "st"));
    b.style.left = pct(e.t);
    marks.push(b);
    return b;
  };
  const track = el("div", { class: "tl__track", role: "group", "aria-label": `Timeline ${hhmmz(t0)} to ${hhmmz(t1)}. Arrow keys move between events.` });
  const rail = el("div", { class: "tl__rail", "aria-hidden": "true" });
  track.append(rail);
  const nowEl = el("div", { class: "tl__now", "aria-hidden": "true" });
  nowEl.style.left = pct(D.now);
  track.append(nowEl);
  const axis = el("div", { class: "tl__axis", "aria-hidden": "true" });
  // an hour label every 1, 2, 3, 6 or 12 hours, the fewest that keep about 48 px between labels
  // on the track as it was last laid out (Details open narrows it)
  const trackW = $("timeline").querySelector(".tl__track")?.clientWidth || (window.innerWidth < 1600 ? 300 : 500);
  const perHour = trackW / Math.max(1, (t1 - t0) / 3600e3);
  const every = [1, 2, 3, 6, 12].find((n) => n * perHour >= 48) || 24;
  for (let h = Math.ceil(t0 / 3600e3) * 3600e3; h <= t1; h += 3600e3) {
    const hr = new Date(h).getUTCHours();
    if (hr % every || Math.abs(h - D.now) < 0.6 * 3600e3) continue;
    const sp = el("span", { class: "tl__hour", text: `${pad(hr)}Z` });
    sp.style.left = pct(h);
    axis.append(sp);
  }
  track.append(axis);
  let history = null;
  if (ui.historyOpen) {
    history = el("div", { class: "tl__history glass", role: "group", "aria-label": "When each source last reported" });
    const lanes = el("div", { class: "tl__lanes" });
    const lane = (name, label) => {
      const l = el("div", { class: `tl__lane tl__lane--${name}` }, el("span", { class: "tl__lanelabel", text: label }));
      lanes.append(l);
      return l;
    };
    const L = { official: lane("official", "Official"), observer: lane("observer", "Observatory"), tephra: lane("tephra", "TEPHRA") };
    for (const e of events) {
      if (e.lane === "official" && Number.isFinite(e.vf) && Number.isFinite(e.vt) && e.vt > t0 && e.vf < t1) {
        const bar = el("div", { class: "tl__bar", "aria-hidden": "true" });
        bar.style.left = pct(Math.max(e.vf, t0));
        bar.style.width = `${((Math.min(e.vt, t1) - Math.max(e.vf, t0)) / (t1 - t0)) * 100}%`;
        L.official.append(bar);
      }
      L[e.lane].append(mark(e));
    }
    const hnow = el("div", { class: "tl__now tl__now--lanes", "aria-hidden": "true" });
    hnow.style.left = pct(D.now);
    L.official.append(hnow);
    // Lag bracket (R7.3): its label sits above the lanes, left of the now-line, never on it.
    const lag = lagOf(sit);
    let lagEl = null;
    if (lag) {
      const times = Object.values(lag.values).map((v) => hhmmBefore(v, D.now)).filter(Number.isFinite);
      if (times.length >= 2) {
        const a = Math.max(t0, Math.min(...times)), b = Math.min(t1, Math.max(...times));
        if (b > a) {
          const g = el("div", { class: "tl__gap", "aria-hidden": "true" });
          g.style.left = pct(a);
          g.style.width = `${((b - a) / (t1 - t0)) * 100}%`;
          L.official.append(g);
          const minutes = Math.round(Math.abs(lag.magnitude));
          const lagText = minutes % 60 === 0 ? `${minutes / 60} h` : durMin(minutes);
          lagEl = el("p", { class: "tl__lag", text: `The official reports trail the observatory by ${lagText}.` });
        }
      }
    }
    history.append(
      el("div", { class: "tl__histhead" },
        el("strong", { text: "When each source last reported" }),
        el("span", { class: "tl__chips" }, ...["9 h back to 3 h ahead", ...recChips].map((t) => el("span", { class: "tl__chip", text: t })))),
      lagEl, lanes);
  } else {
    for (const e of events) track.append(mark(e));
  }
  if (marks.length) marks[marks.length - 1].tabIndex = 0;

  // 3. forecast steps, 4. previous / next, 5. History
  const steps = el("div", { class: "tl__steps" }, el("span", { class: "tl__label", text: "Forecast:" }),
    el("div", { class: "seg", role: "group", "aria-label": "Official forecast steps" },
      ...[["now", "Now"], ["f6", "+6 h"], ["f12", "+12 h"], ["f18", "+18 h"], ["all", "All"]].map(([k, label]) =>
        el("button", { type: "button", "aria-pressed": ui.steps === k ? "true" : "false", dataset: { act: "steps", steps: k, focus: `steps-${k}` }, text: label }))));
  const nav = el("div", { class: "tl__nav", role: "group", "aria-label": "Timeline events" });
  const hist = el("button", { type: "button", class: "tl__histbtn", "aria-expanded": ui.historyOpen ? "true" : "false", dataset: { act: "history", focus: "tl-history" } }, ui.historyOpen ? "History ▾" : "History ▴");
  box.replaceChildren(meta, track, steps, nav, hist, ...(history ? [history] : []));
  // aria-disabled, not disabled: the focused button keeps focus when it reaches the end.
  const btn = (dir, label, text, reason) => {
    const off = !timelineTargetIn(box, dir, ui.tlCurrent);
    const word = el("span", { class: "tl__stepword", text: text.replace(/[‹›]/g, "").trim() });
    return el("button", { type: "button", class: "tl__step", title: off ? reason : label, "aria-label": label, "aria-disabled": off ? "true" : "false", dataset: { act: "tl-step", dir: String(dir), focus: `tl-step-${dir}` } },
      dir < 0 ? "‹ " : null, word, dir > 0 ? " ›" : null);
  };
  nav.append(btn(-1, "Previous timeline event", "‹ Previous", "No earlier event"), btn(1, "Next timeline event", "Next ›", "No later event"));
  const cur = ui.tlCurrent ? marks.find((m) => m.title === ui.tlCurrent) : null;
  if (cur) {
    cur.classList.add("is-current");
    cur.setAttribute("aria-current", "true");
    for (const m of marks) m.tabIndex = m === cur ? 0 : -1;
  }
}

const leftOf = (n) => parseFloat(n.style.left);
function timelineTargetIn(box, dir, current) {
  const marks = [...box.querySelectorAll(".tl__mark")].sort((a, b) => leftOf(a) - leftOf(b));
  if (!marks.length) return null;
  const i = current ? marks.findIndex((m) => m.title === current) : -1;
  if (i >= 0) return marks[i + dir] || null;
  const nowEl = box.querySelector(".tl__now");
  const now = nowEl ? leftOf(nowEl) : Infinity;
  if (dir < 0) return marks.filter((m) => leftOf(m) <= now).pop() || null;
  return marks.find((m) => leftOf(m) > now) || null;
}
export const timelineTarget = (dir, current) => timelineTargetIn($("timeline"), dir, current);

// Details › Timeline history (R8.3): the same events in words, newest first, with the lag. Events
// that say the same thing are one row with their times.
const LANE_WORD = { all: "All", official: "Official", observer: "Observatory", tephra: "TEPHRA" };
const LANE_SUB = { official: "Official reports", observer: "The observatory", tephra: "TEPHRA's own checks" };
export function historySection(D, store, ui) {
  const box = $("history");
  if (!D?.sit) { box.replaceChildren(dkEmpty("No volcano is selected", null)); return; }
  const lane = ui.historyLane || "all";
  const allEvents = timelineEvents(D, store);
  const events = allEvents.filter((e) => lane === "all" || e.lane === lane);
  const lag = lagOf(D.sit);
  const strip = (w) => w.replace(/ \d{4}Z$/, "").replace(/ issued \d{4}Z$/, " issued");
  const runs = collapseRuns(events.map((e) => ({ ...e, _t: e.t })), { textOf: (e) => strip(e.words), timeOf: (e) => e._t, groupOf: (e) => e.lane });
  const head = dkHeader({
    id: "hist-head",
    pills: [lag ? dkPill("info", "Lag is usual") : dkPill("ok", "No lag")],
    title: lag ? `The observatory and the official reports are ${durMin(lag.magnitude)} apart (lag).` : "No lag between the sources.",
  });
  const counts = { official: 0, observer: 0, tephra: 0 };
  for (const e of allEvents) counts[e.lane] = (counts[e.lane] || 0) + 1;
  const seg = el("div", { class: "seg", role: "group", "aria-label": "Which lane" },
    ...Object.entries(LANE_WORD).map(([k, t]) => el("button", { type: "button", "aria-pressed": lane === k ? "true" : "false", dataset: { act: "history-lane", lane: k, focus: `hist-lane-${k}` }, text: k === "all" ? `${t} ${allEvents.length}` : `${t} ${counts[k] || 0}` })));
  const list = runs.length
    ? dkList(runs.map((r) => runRow(r, { key: `hist-${r.key}`, dot: el("span", { class: `dk-lane dk-lane--${r.items[0].lane}`, "aria-hidden": "true" }), sub: LANE_SUB[r.items[0].lane] || LANE_WORD[r.items[0].lane], lineOf: (e) => e.words })), { first: 8, key: "hist-all", more: `Show all ${runs.length} (${plural(events.length, "event")})` })
    : dkEmpty("No events in the last 9 hours.", null);
  box.replaceChildren(dkSection("hist-head", head,
    el("div", { class: "dk-actions" }, el("button", { type: "button", class: "btn btn--small", dataset: { act: "history", focus: "hist-open" }, text: ui.historyOpen ? "Hide History on the time bar" : "Show History on the time bar" })),
    D.stepsMissing?.length ? dkNote("info", "The chosen forecast step has no official area in the current products. No other step is drawn in its place.") : null,
    seg, list,
    el("div", { class: "dk-abouts" }, dkAbout("About lag", "hist", "Official reports are reissued every few hours, so they trail the observatory: a lag is usual. The time bar's History shows these events on three lanes."))));
}

// ------------------------------------------------------------------ Details › Data feeds (R8.3, R12.8)

// Why a feed is off, in words; the setting names stay under Technical detail.
function offWords(f) {
  const e = String(f.last_error || "");
  if (f.feed === "vona") return "Off: no PVMBG permission (replay only).";
  if (/not in this replay case|no archive/i.test(e)) return "Not in this recording.";
  if (/TEPHRA_\w+=0|is off|disabled/i.test(e)) return "Switched off on this server.";
  if (f.status === "NEVER") return "Not polled yet.";
  return e ? "Off." : "Off.";
}

export function feedsSection(D, store, target = $("feeds")) {
  const now = D?.now ?? Date.now();
  const rowOf = (f) => {
    const [, , word] = FEED_STATUS[f.status] || FEED_STATUS.NEVER;
    const tone = { ERROR: "serious", STALE: "stale", OK: "ok", NEVER: "never", DISABLED: "off" }[f.status] || "never";
    const last = ms(f.last_success_at);
    const ago = Number.isFinite(last) ? `${age((now - last) / 1000)} ago` : "never";
    let sub;
    if (f.status === "OK") sub = `Working · updated ${ago}`;
    else if (f.status === "STALE") sub = `Stale · last good ${ago} · showing the last good copy`;
    else if (f.status === "ERROR") sub = `Error · last good ${ago}`;
    else sub = offWords(f);
    return el("div", { class: `feeds__row feeds__row--${f.status.toLowerCase()}` }, dkRow({
      key: `feed-${f.feed}`, dot: tone, title: [FEED_NAME[f.feed] || f.feed, f.replay && D?.mode !== "REPLAY" ? [" ", dkFromReplay(f.replay, false)] : null], sub,
      meta: f.status === "OK" || f.status === "STALE" ? el("span", { class: "mono", text: Number.isFinite(last) ? hhmmz(last) : "" }) : null,
      body: [dkFacts([["Status", word], ["Last good", Number.isFinite(last) ? `${dayTime(last)} (${ago})` : "never"], ["Records", String(f.record_count ?? 0), { mono: true }]]),
        techDetail(`last good (UTC): ${Number.isFinite(last) ? `${dayMonth(last)} ${hhmmz(last)}` : "never"} · records: ${f.record_count ?? 0} · feed key: ${f.feed}`, f.last_error || null)],
    }));
  };
  const db = store.state?.store;
  const dbRow = db ? (() => {
    const okAt = ms(db.last_ok_at);
    return el("div", { class: `feeds__row feeds__row--${db.ok ? "ok" : "error"}` }, dkRow({
      key: "feed-db", dot: db.ok ? "ok" : "serious", title: "Database",
      sub: db.ok ? "Working · reads and writes go through" : `Error · failing since ${hhmmz(ms(db.last_error_at))}`,
      body: [dkFacts([["Last good", Number.isFinite(okAt) ? dayTime(okAt) : "never"]]), techDetail(`last good (UTC): ${Number.isFinite(okAt) ? `${dayMonth(okAt)} ${hhmmz(okAt)}` : "never"}`, db.ok ? null : db.last_error)],
    }));
  })() : null;
  const sorted = store.feeds.slice().sort((a, b) => (FEED_STATUS[a.status]?.[3] ?? 9) - (FEED_STATUS[b.status]?.[3] ?? 9));
  const look = sorted.filter((f) => f.status === "ERROR" || f.status === "STALE");
  const working = sorted.filter((f) => f.status === "OK");
  const off = sorted.filter((f) => f.status === "DISABLED" || f.status === "NEVER");
  const by = {};
  for (const f of store.feeds) by[f.status] = (by[f.status] || 0) + 1;
  const replay = D?.mode === "REPLAY" && D.state.replay;
  // The pill and the numbers count feeds, as the top bar's Data chip does; the database has its
  // own row and only adds to the pill when it fails.
  const offN = (by.DISABLED || 0) + (by.NEVER || 0);
  const errN = (by.ERROR || 0) + (db && !db.ok ? 1 : 0);
  const pill = errN ? dkPill("serious", `${errN} ${errN === 1 ? "error" : "errors"}`) : by.STALE ? dkPill("stale", `${by.STALE} stale`)
    : offN ? dkPill("off", [by.DISABLED ? `${by.DISABLED} off` : null, by.NEVER ? `${by.NEVER} not read` : null].filter(Boolean).join(" · ")) : dkPill("ok", "All working");
  const dbBad = db && !db.ok;
  target.replaceChildren(dkSection("feeds-head",
    dkHeader({ id: "feeds-head", pills: [pill], title: `${by.ERROR ? `${by.ERROR} failing · ` : ""}${by.STALE ? `${by.STALE} stale · ` : ""}${by.OK || 0} working${offN ? ` · ${offN} off or not read` : ""}`, sub: db ? (db.ok ? "The database is working too." : "The database is failing.") : null }),
    dkTiles([
      { label: "Working", value: String(by.OK || 0), tone: by.OK ? "ok" : null, sub: "feeds" },
      by.STALE ? { label: "Stale", value: String(by.STALE), tone: "stale" } : null,
      errN ? { label: "Errors", value: String(errN), tone: "serious", sub: dbBad ? (by.ERROR ? "feeds and the database" : "the database") : "feeds" } : null,
      { label: "Off or not read", value: String(offN), tone: "plain", sub: offN ? (replay ? "not in this recording or switched off" : "switched off or not polled yet") : null },
    ], "Feeds in numbers"),
    dkNote("info", "When a feed fails, TEPHRA shows the last good data with its time, and says so. It never shows substitute data."),
    look.length || dbBad ? dkGroup("Needs a look", null, dkList([dbBad ? dbRow : null, ...look.map(rowOf)], { first: 6, key: "feeds-look" })) : null,
    dkGroup("Working", null, dkList([...working.map(rowOf), db?.ok ? dbRow : null], { first: 8, key: "feeds-ok" })),
    off.length ? dkGroup(`Off or not read · ${off.length}`, null, dkList(off.map(rowOf), { first: 0, key: "feeds-off", more: `Show ${off.length} feeds that are off` })) : null));
}

export function sourcesDialog(D, focusKind) {
  const sit = D?.sit;
  if (!sit) return el("p", { text: "No active volcano selected." });
  const byKind = Object.fromEntries(sit.cards.map((c) => [c.kind, c]));
  const cols = [byKind.SIGMET, byKind.VAA, byKind.VONA].filter(Boolean).map((c) => {
    const url = c.url ? safeExternalUrl(c.url) : null;
    const col = el("section", { class: `raw raw--${c.kind.toLowerCase()}`, "aria-label": c.title, dataset: { kind: c.kind } },
      el("h3", { class: "raw__title" }, el("span", { class: "cmp__kind", text: KIND_LABEL[c.kind] || c.kind }), c.missing ? missingHead(c, "None in force") : el("span", { text: c.title })));
    if (c.missing) { col.append(el("p", { class: "muted", text: `${c.missing_note || "None in force"}. Absence is not evidence of no ash.` })); return col; }
    col.append(
      el("dl", { class: "raw__facts" },
        el("dt", { text: "Source id" }), el("dd", { class: "mono", text: c.source_id }),
        el("dt", { text: "Issued" }), el("dd", { class: "mono", text: `${dayMon(ms(c.issued_at))} ${hhmmz(ms(c.issued_at))}` }),
        el("dt", { text: "Fetched" }), el("dd", { class: "mono", text: `${dayMon(ms(c.fetched_at))} ${hhmmz(ms(c.fetched_at))}` }),
        el("dt", { text: "Hash" }), el("dd", { class: "mono", text: `#${c.sha256_short}` })),
      el("pre", { class: "raw__text", tabindex: "0", text: c.raw_text || "" }),
      url ? el("a", { class: "link-btn", href: url, target: "_blank", rel: "noopener noreferrer" }, icon("i-external-link"), "Open the source") : null);
    if (c.extra_source_ids?.length) col.append(el("details", {}, el("summary", { text: `Earlier reports (${c.extra_source_ids.length})` }), el("ul", { class: "mono raw__extra" }, ...c.extra_source_ids.map((x) => el("li", { text: x })))));
    return col;
  });
  const grid = el("div", { class: "raw-grid" }, ...cols);
  if (focusKind) grid.dataset.focus = focusKind;
  return grid;
}
