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
import { plainLine, techDetail, actorWords, actionPlain } from "./x-parts.js";

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
const SEV = {
  WARNING: ["serious", "st-serious", "SERIOUS"],
  CAUTION: ["caution", "st-caution", "CAUTION"],
  INFO: ["info", "st-info", "INFO"],
};
const MODE_LINE = {
  OFFICIAL: "Same as the official area: TEPHRA adds nothing.",
  WIDENED: "The official area plus the observatory's drift, never smaller.",
  HYPOTHESIS: "No valid official product: a hypothesis. Only MONITOR or HOLD may be advised.",
};
const OUTCOME = {
  STUB: "AI off: official reports only",
  ACCEPTED: "Gemini reading accepted by the validators",
  REPAIRED: "Accepted after one repair",
  MODEL_FAILED: "AI unavailable: official products only, nothing assessed beyond them",
  OFFICIAL_ONLY: "No model call needed: official products only",
  PENDING: "Plume read queued for the Duty Officer: official products only until it runs",
};
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
const sevOf = (d) => SEV[d.severity] || SEV.INFO;
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

export function renderChrome(D, store, ui) {
  const s = D.state;
  const replay = s.mode === "REPLAY";
  document.body.dataset.mode = s.mode;
  document.title = `${replay ? "REPLAY - " : ""}TEPHRA Wall`;
  const banner = $("replay-banner");
  banner.hidden = !replay;
  if (replay && s.replay) {
    // role=status: write only when the words change, so a screen reader announces it once.
    setText($("replay-banner-text"), s.replay.banner);
    // the phone's one-line band: "REPLAY: recorded 05 Sep 2026" (the full words stay in the title)
    setText($("replay-banner-short"), s.replay.banner.replace(/recorded real feeds from/i, "recorded"));
    setText($("replay-banner-case"), ` · ${s.replay.label}${s.replay.auto ? " · switched automatically: no live activity" : ""}`);
    banner.title = `${s.replay.banner} · not live · ${s.replay.label}`;
  }
  const badge = $("mode-badge");
  badge.className = `mode-badge mode-badge--${replay ? "replay" : "live"}`;
  const word = replay ? "Replay" : "Live";
  if (badge.dataset.word !== word) { badge.dataset.word = word; badge.replaceChildren(icon(replay ? "i-replay" : "i-live"), word); }

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

  // The merged AI chip (R3.1): the model state in words, failures in red with their shape.
  const stub = s.llm?.backend === "stub";
  const fails = failedSteps(store);
  const chip = $("ai-chip");
  const label = stub ? `AI: off${narrow() ? "" : " · code only"}` : `AI: on · ${s.llm?.label || "model"}`;
  setText($("model-chip"), label);
  const failBox = chip.querySelector(".ai-chip__fail");
  failBox.hidden = !fails;
  if (fails && failBox.dataset.n !== String(fails)) { failBox.dataset.n = String(fails); failBox.replaceChildren(st("st-serious", "var(--c-serious)"), ` · ${fails} failed`); }
  chip.classList.toggle("ai-chip--fail", fails > 0);
  chip.querySelector("use")?.setAttribute("href", `${chip.querySelector("use").getAttribute("href").split("#")[0]}#${stub ? "i-code" : "i-model"}`);
  chip.title = stub
    ? "No AI model is connected. Code does every step; code templates write the text."
    : `AI model: ${s.llm?.label || ""}. Steps that call a model are marked AI-written. Times, ids and hashes are always written by code.`;
  chip.setAttribute("aria-label", `${label}${fails ? `, ${fails} failed` : ""}. Opens Details, AI helpers.`);

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

let failedSteps = () => 0;
export function setFailureCounter(fn) { failedSteps = fn; }

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

// "Keep watching (MONITOR)": the plain action first, the ICAO word in brackets (R12.10).
export function actionText(a) {
  const raw = actionWords(a);
  const t = actionPlain(raw) || raw;
  return t.charAt(0).toUpperCase() + t.slice(1);
}

export function advisoryLine(a, recorded) {
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
  return el("span", { class: `adv adv--${tone}` }, icon(ic), el("span", { text }), a.status === "EDITED" ? icon("i-pencil") : null, recorded ? el("span", { class: "tag tag--replay", text: "recorded" }) : null);
}

// ------------------------------------------------------------------ Details › Flights heading in (R8.3)

const FLIGHTS_FIRST = 5;

function flightRow(D, f) {
  const p = f.properties;
  const plane = icon("i-aircraft", "flights__plane");
  plane.style.transform = `rotate(${p.track_deg || 0}deg)`;
  const entry = p.inside ? "inside now" : `in ${p.minutes_to_entry} min, est.`;
  const lvl = p.alt_baro_ft != null ? fl(p.alt_baro_ft) : "level unknown";
  const old = p.stale ? `position ${Math.max(1, Math.round(p.ageS / 60))} min old` : null;
  const adv = D.advByFlight.get(`${p.hex}:${p.volcano_id}`);
  return el("li", {}, el("button", { class: "flights__row", type: "button", dataset: { flight: f.id ?? p.hex, focus: `flight-${p.hex}` }, "aria-label": `${p.proxy_flight}, proxy for ${p.callsign || p.hex}, ${p.inside ? "inside TEPHRA's area now" : `enters in ${p.minutes_to_entry} minutes, estimated`}, ${lvl}${old ? `, ${old}` : ""}${p.crew_report ? ", crew report of ash on this route" : ""}. Show this flight.` },
    plane,
    el("span", { class: "flights__id" },
      el("span", { class: "flights__proxy", text: p.proxy_flight }),
      el("span", { class: "flights__meta", text: `proxy for ${p.callsign || String(p.hex || "").toUpperCase()} · ${lvl}${old ? ` · ${old}` : ""}` }),
      p.crew_report ? el("span", { class: "flights__crew" }, icon("i-pin", "icon"), "Crew report of ash on this route") : null),
    el("span", { class: p.inside ? "flights__inside" : "flights__mins" }, p.inside ? st("st-inside", "var(--c-tephra)") : null, entry),
    adv ? el("span", { class: "flights__status" }, advisoryLine(adv, false)) : null));
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
  const replay = D.mode === "REPLAY";
  const adsb = store.feeds.find((f) => f.feed === "adsb");
  const coverage = !adsb || adsb.status !== "OK"
    ? (replay ? "No aircraft data in this recording." : `Aircraft data is ${({ ERROR: "failing", STALE: "stale", DISABLED: "off" })[adsb?.status] || "not working"}: an empty map is not an empty sky.`)
    : "Aircraft coverage is patchy: an empty map is not an empty sky. Entry times are estimates: a straight line from the last position.";
  const head = el("p", { class: "dsum" },
    el("strong", { text: flights.length ? `${flights.length} RFA ${flights.length === 1 ? "flight" : "flights"} in or heading into TEPHRA's estimated area${scopeName ? ` at ${scopeName}` : ""}` : `No RFA flight is projected to enter TEPHRA's area${scopeName ? ` at ${scopeName}` : ""}.` }),
    replay ? el("span", { class: "tag tag--replay", text: "recorded" }) : null);
  const note = el("p", { class: "dnote", text: `RFA (Ring of Fire Air) is a fictional airline; each flight number stands in for a real aircraft. ${coverage}` });
  const foot = others.size ? el("div", { class: "flights__foot" }, ...[...others].map(([vid, n]) => {
    const name = D.sits.find((x) => x.volcano_id === vid)?.volcano_name || vid;
    return el("button", { type: "button", class: "link-btn", dataset: { act: "select", vid, focus: `others-${vid}` }, text: `+${n} heading in at ${name}` });
  })) : null;
  // RFA flights only a crew report of ash flags (not TEPHRA's area): their own short list, so
  // This flight opens from here too (UI-DESIGN 5.7).
  const crew = crewList(D);
  if (!flights.length) { target.replaceChildren(head, ...crew, note, ...(foot ? [foot] : [])); return; }
  const first = el("ol", { class: "flights__list" }, ...flights.slice(0, FLIGHTS_FIRST).map((f) => flightRow(D, f)));
  const rest = flights.slice(FLIGHTS_FIRST);
  const more = rest.length ? el("details", { class: "more", dataset: { k: "flights-all" } }, el("summary", { text: `All ${flights.length}` }), el("ol", { class: "flights__list", start: String(FLIGHTS_FIRST + 1) }, ...rest.map((f) => flightRow(D, f)))) : null;
  target.replaceChildren(head, first, ...(more ? [more] : []), ...crew, note, ...(foot ? [foot] : []));
}

function crewList(D) {
  const flagged = D.crewFlights
    .map((f) => [f, D.crew.flagByHex.get(f.properties.hex)])
    .filter(([, flag]) => flag)
    .sort(([, a], [, b]) => a.minutes_to_entry - b.minutes_to_entry);
  if (!flagged.length) return [];
  return [
    el("p", { class: "dsum flights__crewhead" }, icon("i-pin", "icon"), el("strong", { text: `${flagged.length} more RFA ${flagged.length === 1 ? "flight" : "flights"} on the route of a crew report of ash` })),
    el("ol", { class: "flights__list" }, ...flagged.map(([f, flag]) => {
      const p = f.properties;
      const lvl = p.alt_baro_ft != null ? fl(p.alt_baro_ft) : "level unknown";
      const when = flag.reporter ? "reported ash" : flag.inside_now ? "inside now" : `in ${flag.minutes_to_entry} min`;
      return el("li", {}, el("button", { class: "flights__row", type: "button", dataset: { flight: f.id ?? p.hex, focus: `flight-${p.hex}` }, "aria-label": `${p.proxy_flight}, proxy for ${p.callsign || p.hex}, ${flag.line}, ${when}, ${lvl}. Show this flight.` },
        icon("i-aircraft", "flights__plane flights__plane--crew"),
        el("span", { class: "flights__id" },
          el("span", { class: "flights__proxy", text: p.proxy_flight }),
          el("span", { class: "flights__meta", text: `proxy for ${p.callsign || String(p.hex || "").toUpperCase()} · ${lvl}` }),
          el("span", { class: "flights__crew" }, icon("i-pin", "icon"), flag.line)),
        el("span", { class: "flights__mins", text: when })));
    })),
  ];
}

// ------------------------------------------------------------------ Details › How TEPHRA decided (R8.3, R12.7)

export function traceLines(store, D, ui) {
  const sel = D?.selected;
  const all = ui.traceScope === "all";
  return store.trace.filter((t) => all || !t.volcano_id || t.volcano_id === sel);
}

const TRACE_FIRST = 14;

function traceItem(t, ui, stub) {
  const [ic, name] = ACTOR[t.actor] || ["i-system", String(t.actor || "").toUpperCase()];
  const lvl = t.level === "error" ? st("st-serious", "var(--c-serious)") : t.level === "warn" ? st("st-caution", "var(--c-caution)") : null;
  const plain = plainLine(t.message);
  return el("li", { class: `trace__line${ui.freshTrace?.has(t.id) ? " is-new" : ""}${t.level === "error" ? " trace__line--error" : ""}` },
    el("span", { class: "trace__time", text: hhmmz(ms(t.at)) }),
    el("span", { class: "trace__msg" }, lvl, el("span", { text: plain }), el("span", { class: "trace__who", text: ` · ${actorWords(t.actor, stub)}` })),
    techDetail(
      el("p", { class: "tech__line" }, el("span", { class: "mono", text: `${hhmmssz(ms(t.at))} · ${t.stage}` }), " ", el("span", { class: `actor actor--${t.actor}` }, icon(ic), name)),
      el("p", { class: "tech__line mono", text: t.message })));
}

export function renderTrace(D, store, ui, conn, target = $("trace")) {
  const lines = traceLines(store, D, ui);
  const scope = el("div", { class: "seg", role: "group", "aria-label": "Which steps" },
    el("button", { type: "button", "aria-pressed": ui.traceScope !== "all" ? "true" : "false", dataset: { act: "trace-scope", scope: "volcano", focus: "trace-scope-v" }, text: "This volcano" }),
    el("button", { type: "button", "aria-pressed": ui.traceScope === "all" ? "true" : "false", dataset: { act: "trace-scope", scope: "all", focus: "trace-scope-a" }, text: "Everything" }));
  const head = el("div", { class: "dsum dsum--row" },
    el("strong", { text: conn.lostAt ? `${lines.length} steps · paused at ${hhmmz(conn.lostAt)}` : `${lines.length} step${lines.length === 1 ? "" : "s"}, newest first` }),
    D?.mode === "REPLAY" ? el("span", { class: "tag tag--replay", text: "recorded" }) : null, scope);
  if (!D) { target.replaceChildren(head, el("div", { class: "skeleton" })); return; }
  const newest = lines.slice().reverse();
  const ol = el("ol", { class: "trace__list", role: "log", "aria-live": "off", "aria-label": "How TEPHRA decided, newest first" });
  if (!newest.length) ol.append(el("li", { class: "trace__empty", text: "No steps yet." }));
  for (const t of newest.slice(0, TRACE_FIRST)) ol.append(traceItem(t, ui, D?.state.llm?.backend === "stub"));
  const rest = newest.slice(TRACE_FIRST);
  const more = rest.length ? el("details", { class: "more", dataset: { k: "trace-all" } }, el("summary", { text: `Show all (${newest.length})` }), el("ol", { class: "trace__list", "aria-live": "off" }, ...rest.map((t) => traceItem(t, ui, D?.state.llm?.backend === "stub")))) : null;
  target.classList.toggle("is-stale", !!conn.lostAt);
  target.replaceChildren(head, el("p", { class: "dnote", text: "Each step in plain words. Lines TEPHRA has no plain wording for are shown as written; the raw line is under Technical detail." }), ol, ...(more ? [more] : []));
}

// ------------------------------------------------------------------ Details › the ash (R8.3)

export function hypothesisBanner(sit) {
  return el("p", { class: "hyp-banner", role: "note" }, st("st-caution", "var(--c-caution)"),
    el("span", { text: `HYPOTHESIS: no valid official product for ${sit.volcano_name}. TEPHRA's area is a hypothesis built from the observatory report. Advisories are limited to MONITOR or HOLD.` }));
}

function secHead(id, title, aside) {
  return el("div", { class: "sec__head" }, el("h3", { id, class: "sec__title", text: title }), aside ? el("span", { class: "sec__aside", text: aside }) : null);
}

// What the official reports say (R8.3 `sources`): the provenance line, then SIGMET and VAA | VONA
// side by side with plain row labels (R12.4). Raw text, hashes and ids are one tap away.
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
      if (card.kind === "VONA") return f["Cloud top"] ? [plainValue(f["Cloud top"].replace(/\s*\(.*\)$/, "")), f["Cloud top"]] : "—";
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
  const cell = (card, row, role) => {
    let v = value(card, row);
    let title = null;
    if (Array.isArray(v)) [v, title] = v;
    // An empty cell says why in words, the same words in every column (R12.4, review 2, item 8).
    const empty = v === "—";
    if (empty) v = row === "code" && card.kind === "SIGMET" ? "not in a SIGMET" : row === "valid" && card.kind === "VONA" ? "no end time stated" : "not given";
    const flag = flagged.get(`${card.source_id}|${row}`);
    const cls = ["cmp__cell", empty || v === "not given" ? "cmp__cell--empty" : "", flag ? "cmp__cell--flag" : card.kind === "VONA" && row === "move" ? "cmp__cell--observer" : ""].filter(Boolean).join(" ");
    return el("div", { class: cls, role, title: title || null }, flag ? st("st-caution", "var(--c-caution)") : null, el("span", { text: v }), flag ? el("span", { class: "sr-only", text: " (flagged: disagrees)" }) : null);
  };
  const footOf = (card, role) => el("div", { class: "cmp__foot", role },
    el("button", { type: "button", class: "link-btn", dataset: { act: "raw", kind: card.kind, focus: `raw-${card.kind}` }, "aria-label": `Raw text of ${card.title}` }, icon("i-raw-text"), "Raw text"));
  const parts = { D, sit, order, rows, vent, flagged, cell, footOf };
  // The drawer is narrow (480 or 440 px), so each source is one card with its rows in full and no
  // column is ever cut off (R2.8). The side-by-side view of the raw texts is the C dialog.
  const body = sourceCards(parts);
  const ids = order.filter((c) => !c.missing).map((c) => `${c.title}: ${c.source_id} · #${c.sha256_short || ""}`);
  // Kinds, not a count (review 2, item 3): one card per kind, the newest of each. The Desk lists
  // every product a draft used, and "Why … " lists reasons; neither is this number.
  const has = (k) => order.some((c) => !c.missing && c.kind === k);
  const official = ["SIGMET", "VAA"].filter(has);
  const lead = official.length ? `The newest ${official.join(" and ")} (official, binding)` : "No official report";
  const summary = `${lead}${has("VONA") ? " and the observatory's VONA (supporting)" : ""} ${official.length || has("VONA") ? "name" : "names"} ${sit.volcano_name}. One card per kind below, the newest of each.`;
  return el("section", { class: "sec", "aria-labelledby": "h-sources" },
    el("p", { class: "dsum", id: "h-sources", text: summary }),
    el("details", { class: "more", dataset: { k: "src-why" } }, el("summary", { text: `Why TEPHRA shows ${sit.volcano_name}: ${sit.active_reasons.length} reason${sit.active_reasons.length === 1 ? "" : "s"}` }),
      el("ul", { class: "reasons" }, ...sit.active_reasons.map((r) => el("li", { text: r })))),
    el("p", { class: "dnote", text: "A pink edge marks an official report, a blue edge the observatory. A yellow cell disagrees with another source." }),
    body,
    el("button", { type: "button", class: "btn btn--small", dataset: { act: "raw", kind: "", focus: "src-side" } }, icon("i-raw-text"), "Raw texts side by side (C)"),
    sourceQuotes(order),
    el("details", { class: "more", dataset: { k: "src-ids" } }, el("summary", { text: "Technical ids" }), el("ul", { class: "tech__list mono" }, ...ids.map((t) => el("li", { text: t })))));
}

// wide drawer: the row-major table, SIGMET and VAA | VONA. No empty label header cell (R2.8).
function sourceGrid({ D, sit, order, rows, vent, flagged, cell, footOf }) {
  const grid = el("div", { class: "cmp", role: "table", "aria-label": "Official reports side by side: SIGMET, VAA and VONA" });
  const hdrRow = el("div", { class: "cmp__row cmp__row--head", role: "row" }, el("div", { class: "cmp__corner", role: "columnheader" }, el("span", { class: "sr-only", text: "Field" })));
  order.forEach((card, i) => {
    if (i === 2) hdrRow.append(el("div", { class: "cmp__divider", "aria-hidden": "true" }));
    hdrRow.append(colHead(D, sit, card, vent, flagged));
  });
  grid.append(hdrRow);
  for (const [row, label] of rows) {
    const r = el("div", { class: "cmp__row", role: "row" }, el("div", { class: "cmp__rowlabel", role: "rowheader", text: label }));
    order.forEach((card, i) => {
      if (i === 2) r.append(el("div", { class: "cmp__divider", "aria-hidden": "true" }));
      r.append(card.missing ? el("div", { class: "cmp__cell cmp__cell--missing", role: "cell" }, el("span", { class: "sr-only", text: "none" })) : cell(card, row, "cell"));
    });
    grid.append(r);
  }
  const foot = el("div", { class: "cmp__row cmp__row--foot", role: "row" }, el("div", { role: "cell" }));
  order.forEach((card, i) => {
    if (i === 2) foot.append(el("div", { class: "cmp__divider", "aria-hidden": "true" }));
    foot.append(card.missing ? el("div", { role: "cell" }) : footOf(card, "cell"));
  });
  grid.append(foot);
  return grid;
}

// narrow drawer and phone: one card per source, its head then label and value rows wrapping in full
function sourceCards({ D, sit, order, rows, vent, flagged, cell, footOf }) {
  return el("div", { class: "cmp-cards" }, ...order.map((card) => {
    const head = colHead(D, sit, card, vent, flagged);
    head.removeAttribute("role");
    const box = el("div", { class: `cmp-card${card.missing ? " cmp-card--missing" : ""}`, role: "group", "aria-label": head.querySelector(".cmp__kind").textContent }, head);
    if (card.missing) return box;
    for (const [row, label] of rows) box.append(el("div", { class: "cmp-card__row" }, el("div", { class: "cmp__rowlabel", text: label }), cell(card, row, null)));
    box.append(footOf(card, null));
    return box;
  }));
}

// Long verbatim fields stay out of the grid: full-width quoted lines under it, by source kind.
const QUOTED = { VAA: ["Info source", "Remarks"], VONA: ["Activity", "Cloud height"] };
function sourceQuotes(order) {
  const blocks = order.filter((c) => !c.missing && QUOTED[c.kind]).map((c) => {
    const f = c.display_fields || {};
    const lines = QUOTED[c.kind].filter((k) => f[k]).map((k) => el("p", { class: "cmp-quote__line" }, el("span", { class: "cmp-quote__label", text: `${k}: ` }), el("q", { text: f[k] })));
    if (!lines.length) return null;
    const observer = c.kind === "VONA";
    return el("div", { class: `cmp-quote${observer ? " cmp-quote--observer" : ""}` }, el("div", { class: "cmp__kind", text: KIND_LABEL[c.kind] }), ...lines);
  }).filter(Boolean);
  return blocks.length ? el("details", { class: "more", dataset: { k: "src-quotes" } }, el("summary", { text: "What they say in their own words" }), el("div", { class: "cmp-quotes" }, ...blocks)) : null;
}

function colHead(D, sit, card, vent, flagged) {
  const observer = card.kind === "VONA";
  const cls = `cmp__colhead${observer ? " cmp__colhead--observer" : ""}${card.missing ? " cmp__colhead--missing" : ""}${flagged.get(`${card.source_id}|head`) ? " cmp__colhead--flag" : ""}`;
  const kind = KIND_LABEL[card.kind] || card.kind;
  if (card.missing) {
    const hyp = D.coneOf(sit.volcano_id)?.properties.mode === "HYPOTHESIS" && !observer;
    return el("div", { class: cls, role: "columnheader" }, el("div", { class: "cmp__kind", text: kind }), el("div", { class: "cmp__title" }, missingHead(card, hyp ? "No valid official product" : "None in force")),
      card.missing_note ? el("div", { class: "cmp__note", text: card.missing_note }) : null,
      el("div", { class: "cmp__note cmp__note--quiet", text: "Absence is not evidence of no ash." }));
  }
  const t = ms(card.issued_at);
  const [tone, sid, word, long] = EVID[card.evidence] || EVID.UNKNOWN;
  const kids = [
    el("div", { class: "cmp__kind", text: kind }),
    el("div", { class: "cmp__title", text: observer ? `VONA ${hhmmz(t)}` : card.title }),
    el("div", { class: "cmp__age", text: `${hhmmz(t)} · ${age((D.now - t) / 1000)} ago` }),
    el("div", { class: `evid evid--${tone}`, title: long }, st(sid, tone === "seen" ? "var(--c-ok)" : tone === "est" ? "var(--c-info)" : tone === "off" ? "var(--c-off)" : "var(--c-caution)"), word),
  ];
  if (observer && vent && Number.isFinite(t)) {
    const h = solarHour(t, vent[0]);
    const night = isNight(t, vent[0]);
    const hh = Math.floor(h), mm = Math.round((h - hh) * 60) % 60;
    kids.push(el("div", { class: `daynight${night ? " daynight--night" : ""}`, text: `${night ? "Night" : "Day"} at the vent · ${pad(hh)}:${pad(mm)} local solar` }));
  }
  if (card.stale) kids.push(el("div", { class: "evid evid--stale" }, st("st-stale", "var(--c-caution)"), `Stale: last good copy ${age(card.stale_age_s)} old`));
  return el("div", { class: cls, role: "columnheader" }, ...kids);
}

// Where the sources disagree (R8.3 `disagree`): CAUTION and SERIOUS first; minor ones folded.
export function disagreeSection(D, sit, ui) {
  const items = sit.discrepancies.slice().sort((a, b) => (SEV_RANK[b.severity] || 0) - (SEV_RANK[a.severity] || 0));
  const check = items.filter((d) => d.severity !== "INFO");
  const info = items.filter((d) => d.severity === "INFO");
  const infoRows = info.map((d) => infoRow(d));
  for (const card of sit.cards) {
    if (card.missing || !NON_OBS.has(card.evidence)) continue;
    infoRows.push(el("li", { class: "dis__item dis__item--info" },
      el("div", { class: "dis__sev" }, el("span", { class: "sev sev--info" }, st("st-info", "var(--c-info)"), "INFO"), el("span", { class: "dis__kind", text: "NOT OBSERVED" })),
      el("div", {}, el("p", { class: "dis__headline", text: `${card.kind} could not see the ash` }), el("p", { class: "dis__detail", text: "Not evidence of no ash; it never shrinks TEPHRA's area or weakens an advisory." }))));
  }
  const head = check.length
    ? `${check.length} to check${infoRows.length ? ` · ${infoRows.length} minor` : ""}`
    : `Nothing that needs checking${infoRows.length ? ` (${infoRows.length} minor difference${infoRows.length === 1 ? "" : "s"})` : ""}`;
  const list = el("ol", { class: "dis" }, ...check.map((d) => disCard(D, sit, d, ui)));
  if (!items.length && !infoRows.length) list.append(el("li", { class: "empty", text: "No differences found between the reports in force." }));
  const minor = infoRows.length ? el("details", { class: "more", dataset: { k: "dis-minor" } }, el("summary", { text: `Minor differences (${infoRows.length})` }), el("ol", { class: "dis" }, ...infoRows)) : null;
  return el("section", { class: "sec", "aria-labelledby": "h-dis" },
    el("p", { class: "dsum", id: "h-dis", text: head }), list, minor);
}

function disCard(D, sit, d, ui) {
  const [tone, sid, word] = sevOf(d);
  const [kind, headline] = kindOf(d);
  const body = el("div", { class: "dis__body" }, el("p", { class: "dis__headline", text: headline }), el("p", { class: "dis__detail", text: d.summary }));
  const vals = Object.entries(d.values);
  if (d.kind === "DIRECTION_MISMATCH" && d.aspect === "direction") {
    const offV = vals.find(([k]) => !k.startsWith("VONA:"))?.[1] || "";
    const obsV = vals.find(([k]) => k.startsWith("VONA:"))?.[1] || "";
    const offDeg = /\b(NNE|ENE|ESE|SSE|SSW|WSW|WNW|NNW|NE|SE|SW|NW|N|E|S|W)\b/.exec(offV)?.[1] || offV;
    const obsDeg = /\b(NNE|ENE|ESE|SSE|SSW|WSW|WNW|NNW|NE|SE|SW|NW|N|E|S|W)\b/.exec(obsV)?.[1] || obsV.replace(/^moving /, "");
    body.append(el("p", { class: "dis__explain" }, "Official area moves ", el("b", { class: "off", text: offDeg }), ". Observatory reports ash moving ", el("b", { class: "obs", text: obsDeg }), `. ${Math.round(d.magnitude)}° apart.`));
  } else if (d.kind === "DIRECTION_MISMATCH" && d.aspect === "polygon") {
    const cone = D.coneOf(sit.volcano_id)?.properties;
    const sector = D.sectorOf(sit.volcano_id);
    let tail = "";
    if (cone?.mode === "WIDENED" && sector && D.rose) tail = pointInGeom(dest(D.rose.vent, D.rose.obsDeg, 15), sector.geometry) || pointInGeom(dest(D.rose.vent, D.rose.obsDeg, 15), D.coneOf(sit.volcano_id).geometry) ? " TEPHRA's area covers it." : "";
    else if (cone?.mode === "OFFICIAL") tail = D.state.llm?.backend === "stub" ? " TEPHRA has not widened the area (AI off)." : " TEPHRA has not widened the area.";
    body.append(el("p", { class: "dis__explain", text: `A point 15 km along the observatory's drift is outside the official polygon.${tail}` }));
  } else if (EXPLAIN[d.kind]) {
    body.append(el("p", { class: "dis__explain", text: EXPLAIN[d.kind] }));
  }
  if (d.kind === "DIRECTION_MISMATCH" && D.rose) body.append(el("button", { type: "button", class: "link-btn", dataset: { act: "frame", focus: `show-${d.id}` } }, icon("i-frame"), "Show on the map"));
  return el("li", { class: `dis__item dis__item--${tone}${ui.freshDis?.has(d.id) ? " is-new" : ""}` },
    el("div", { class: "dis__sev" }, el("span", { class: `sev sev--${tone}` }, st(sid, `var(--c-${tone})`), word), el("span", { class: "dis__kind", text: kind })),
    body);
}

const capFirst = (t) => (t ? t[0].toUpperCase() + t.slice(1) : t);

function infoRow(d) {
  const [kind, headline] = kindOf(d);
  return el("li", { class: "dis__item dis__item--info" },
    el("div", { class: "dis__sev" }, el("span", { class: "sev sev--info" }, st("st-info", "var(--c-info)"), "INFO"), el("span", { class: "dis__kind", text: kind })),
    el("div", {}, el("p", { class: "dis__headline", text: `${headline}. ${capFirst(EXPLAIN[d.kind] ? EXPLAIN[d.kind].replace(/^Harmless: /, "") : "")}`.trim() }), el("p", { class: "dis__detail", text: d.summary })));
}

// TEPHRA's estimate (R8.3 `estimate`): the outcome sentence, the rule, who read it, valid until.
export function estimateOutcome(D, sit, cone) {
  const outcome = sit.assessment?.outcome;
  const stub = outcome === "STUB" || (!outcome && D.state.llm?.backend === "stub");
  if (cone.mode === "OFFICIAL") return stub ? "Same as the official area (AI off, nothing added)." : outcome === "MODEL_FAILED" ? "Same as the official area: AI unavailable, nothing assessed beyond the official reports." : "Same as the official area: the model found nothing to add.";
  return MODE_LINE[cone.mode] || "";
}

export function areaSection(D, sit, ui) {
  const coneF = D.coneOf(sit.volcano_id);
  const wrap = (kids) => el("section", { class: "sec", "aria-labelledby": "h-area" }, ...kids);
  if (!coneF) return wrap([el("p", { class: "empty", id: "h-area", text: "No TEPHRA estimate yet for this volcano." })]);
  const cone = coneF.properties;
  const a = sit.assessment;
  const outcome = a?.outcome;
  const stub = outcome === "STUB" || (!outcome && D.state.llm?.backend === "stub");
  const facts = el("dl", { class: "area__facts" },
    el("dt", { text: "Rule" }), el("dd", { text: "Never smaller than any valid official area" }),
    el("dt", { text: "Heights" }), el("dd", { class: "mono", text: band(cone.base_ft, cone.top_ft) }),
    el("dt", { text: "Read by" }), el("dd", { text: stub ? "Code (AI off): official reports only" : outcome === "PENDING" ? OUTCOME.PENDING : `${a && a.llm_backend !== "stub" && a.model_id ? a.model_id : D.state.llm?.label || "model"} · ${OUTCOME[outcome] || "—"}` }),
    el("dt", { text: "Valid until" }), el("dd", { class: "mono", text: hhmmz(ms(cone.valid_to)) }));
  if (cone.mode !== "OFFICIAL") facts.append(el("dt", { text: "Confidence" }), el("dd", { text: `${Math.round((cone.confidence ?? 0) * 100)}% in the widening` }));
  const kids = [
    el("p", { class: "dsum", id: "h-area", text: estimateOutcome(D, sit, cone) }),
    el("p", { class: "dnote", text: "TEPHRA's estimate is an estimate, not a forecast. It is drawn as the amber dashed line, never smaller than the official area, which stays binding." }),
  ];
  if (outcome === "MODEL_FAILED") kids.push(el("p", { class: "area__note" }, st("st-caution", "var(--c-caution)"), `AI unavailable: ${a?.estimate?.uncertainty_notes || "no usable model output"}`));
  kids.push(facts, techDetail(`Mode ${cone.mode} · label ${cone.label} · ${cone.cone_id || ""}`));
  const est = a?.estimate;
  const model = a && a.llm_backend && a.llm_backend !== "stub" && outcome !== "STUB";
  if (model && est) {
    const read = el("details", { class: "area__read more", open: ui.readOpen ? true : null, dataset: { k: "area-read" } },
      el("summary", {}, icon("i-model"), "How the model read it", el("span", { class: "tag", text: "AI-written" })));
    const ul = el("ul", { class: "area__readings" });
    for (const r of est.disagreements_explained || []) {
      const lean = r.which_source_we_lean_on ? cardName(sit, r.which_source_we_lean_on) : null;
      ul.append(el("li", {}, el("span", { text: r.reading || "" }),
        lean ? el("span", { class: "area__lean", text: ` Leans on ${lean}` }) : null,
        r.why ? el("span", { class: "area__lean", text: `: ${r.why}` }) : null));
    }
    if (ul.children.length) read.append(ul);
    if (est.rationale) read.append(el("p", {}, el("strong", { text: "Rationale. " }), el("span", { text: est.rationale })));
    if (est.uncertainty_notes) read.append(el("p", {}, el("strong", { text: "Uncertainty. " }), el("span", { text: est.uncertainty_notes })));
    kids.push(read);
  }
  const card = el("div", { class: `area area--${cone.mode.toLowerCase()}` }, ...kids);
  return wrap([cone.mode === "HYPOTHESIS" ? hypothesisBanner(sit) : null, card]);
}

// Decisions (R8.3 `decisions`): the counts first, then the list.
export function decisionsSection(D, store, ui, target = $("decisions")) {
  const all = store.advisories.slice().sort((a, b) => ms(b.updated_at) - ms(a.updated_at));
  const advs = all.filter((a) => a.status !== "SUPERSEDED");
  const superseded = all.filter((a) => a.status === "SUPERSEDED");
  const waiting = advs.filter((a) => a.status === "DRAFT").length;
  const approved = advs.filter((a) => a.status === "APPROVED" || a.status === "EDITED").length;
  const rejected = advs.filter((a) => a.status === "REJECTED").length;
  const replay = D.mode === "REPLAY";
  const list = el("ol", { class: "decisions" });
  for (const a of advs) {
    const decided = a.status === "APPROVED" || a.status === "EDITED" || a.status === "REJECTED";
    const tone = a.status === "REJECTED" ? "serious" : decided ? "ok" : "draft";
    const fresh = ui.freshDecisions?.has(a.id);
    const right = a.status === "DRAFT"
      ? el("span", { class: "decisions__who", text: `drafted ${age((D.now - ms(a.created_at)) / 1000)} ago` })
      : el("span", { class: "decisions__who mono", text: `${deciderName(a)}${a.decided_at ? ` · ${hhmmz(ms(a.decided_at))}` : ""}` });
    const status = {
      DRAFT: ["i-clock", "Waiting for a dispatcher"], APPROVED: ["i-approved", "Approved"], EDITED: ["i-approved", "Approved with edits"],
      REJECTED: ["i-rejected", "Rejected"],
    }[a.status] || ["i-clock", a.status];
    list.append(el("li", { class: `decisions__item decisions__item--${tone}${fresh ? " is-stamped" : ""}`, dataset: { adv: a.id } },
      el("span", { class: `decisions__status adv--${tone}` }, icon(status[0]), el("span", { text: status[1] }), a.status === "EDITED" ? icon("i-pencil") : null),
      el("span", { class: "decisions__what" }, el("b", { text: a.proxy_flight }), ` · ${actionText(a)}`, el("span", { class: "decisions__vol", text: ` · ${a.volcano_name}` })),
      right,
      a.status === "REJECTED" && a.reject_reason ? el("q", { class: "decisions__reason", text: a.reject_reason }) : null));
  }
  if (superseded.length) {
    list.append(el("li", { class: "decisions__item decisions__item--off" },
      el("span", { class: "decisions__status adv--off" }, icon("i-superseded"), el("span", { text: "Replaced by a newer draft" })),
      el("span", { class: "decisions__what", text: `${superseded.length} earlier draft${superseded.length === 1 ? "" : "s"}: ${[...new Set(superseded.map((a) => a.proxy_flight))].join(", ")}` }),
      el("span", { class: "decisions__who", text: "" })));
  }
  // The waiting count is the server's (the same one the Desk reads, R2.7); the list holds the newest 50.
  const summary = all.length
    ? `${D.state.draft_count === null ? "unknown (database error)" : D.state.draft_count ?? waiting} waiting · ${approved} approved · ${rejected} rejected${all.length >= 50 ? " (of the newest 50)" : ""}`
    : "No advisories yet. A draft appears when a flight's projected track enters TEPHRA's area.";
  target.replaceChildren(
    el("p", { class: "dsum", id: "h-dec" }, el("strong", { text: summary }), replay ? el("span", { class: "tag tag--replay", text: "recorded" }) : null),
    el("p", { class: "dnote", text: "Approve on the Desk · nothing is sent anywhere. Approved text goes only to TEPHRA's own outbound queue. Nothing is sent to an aircraft or any real system." }),
    all.length ? el("details", { class: "more", dataset: { k: "dec-all" } }, el("summary", { text: `The full list (${advs.length}${all.length >= 50 ? ", newest 50 loaded" : ""})` }), list) : el("span"));
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
  const readout = levelIsAll(ui.level) ? "All heights" : `${fl(ui.level.min)}–${fl(ui.level.max)}`;
  box.replaceChildren(
    el("p", { class: "dsum" }, el("span", { id: "levels-title", text: "Showing: " }), el("strong", { class: "levels__readout", "aria-live": "polite", text: readout })),
    el("p", { class: "dnote", text: "Drag a handle or use the arrow keys. Official areas outside the heights are faded, never removed, and a pill on the map says so. FL350 is about 35,000 ft." }),
    el("div", { class: "levels__wrap" }, track,
      el("ul", { class: "levels__key" },
        el("li", {}, el("span", { class: "levels__sw levels__sw--official" }), "Official band"),
        el("li", {}, el("span", { class: "levels__sw levels__sw--tephra" }), "TEPHRA's band"),
        el("li", {}, el("span", { class: "levels__sw levels__sw--ac" }), "Aircraft (amber: RFA heading in)"))),
    el("div", { class: "levels__presets seg", role: "group", "aria-label": "Height presets" },
      ...[["all", "All"], ["hazard", "Hazard"], ["low", "≤FL180"], ["high", "≥FL180"]].map(([k, t]) =>
        el("button", { type: "button", dataset: { act: "level-preset", preset: k, focus: `lv-${k}` }, "aria-pressed": (k === "all" && levelIsAll(ui.level)) || (k === "hazard" && hazardOn) ? "true" : "false", text: t }))));
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
    if (t.stage === "EXPOSURE" && t.flight_id) { seen.add(k); out.push({ lane: "tephra", t: ms(t.at), icon: "i-aircraft", cls: "tl__mark--tephra", title: `Flight heading in ${hhmmz(ms(t.at))}`, kind: "flight", words: `A flight heading in was found ${hhmmz(ms(t.at))}` }); }
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
  let pill, recSpan = null;
  if (replay) {
    const a = ms(s.replay.recorded_from), b = ms(s.replay.recorded_to);
    const loop = !!s.replay.window_from;
    const pa = loop ? ms(s.replay.window_from) : a, pb = loop ? ms(s.replay.window_to) : b;
    const p = Math.max(0, Math.min(1, (D.now - pa) / (pb - pa)));
    const bar = el("span");
    bar.style.width = `${(p * 100).toFixed(1)}%`;
    const pctText = `${Math.round(p * 100)}%`;
    meta.append(
      el("span", { class: "tl__mode" }, icon("i-replay"), "Replay"),
      // The clock, then how far the recording has played. The recording's own span sits in the
      // tooltip and in History, not beside the 12 h axis, so two time scales never sit side by
      // side (review 2, item 12).
      el("span", { class: "tl__window", text: `${hhmmz(D.now)} · ${pctText} played`, title: `${loop ? "The replay loops over" : "Recording"} ${dayMonth(pa)} ${hhmmz(pa)} to ${dayMonth(pb)} ${hhmmz(pb)}` }),
      el("span", { class: "tl__progress", role: "progressbar", title: `${loop ? "The replay loops over" : "Recording"} ${dayMonth(pa)} ${hhmmz(pa)} to ${dayMonth(pb)} ${hhmmz(pb)}`, "aria-label": loop ? "Replay loop progress" : "Replay progress", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(Math.round(p * 100)), "aria-valuetext": `${pctText} of the recording, ${hhmmz(pa)} to ${hhmmz(pb)}` }, bar));
    recSpan = `${loop ? "Replay loops over" : "Recording"} ${pb - pa > 20 * 3600e3 ? `${dayMonth(pa)} ${hhmmz(pa)} – ${dayMonth(pb)} ${hhmmz(pb)}` : `${hhmmz(pa)}–${hhmmz(pb)}`}, ${pctText} played`;
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
  const every = window.innerWidth < 1600 ? 3 : 2;
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
          lagEl = el("span", { class: "tl__lag", text: `lag ${durMin(lag.magnitude)} between the observatory and the official reports` });
        }
      }
    }
    history.append(el("div", { class: "tl__histhead" }, el("strong", { text: "When each source last reported" }), el("span", { class: "tl__span", text: `9 h back, 3 h ahead${recSpan ? ` · ${recSpan}` : ""}` }), lagEl), lanes);
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

// Details › Timeline history (R8.3): the same events in words, newest first, with the lag.
export function historySection(D, store, ui) {
  const box = $("history");
  if (!D?.sit) { box.replaceChildren(el("p", { class: "dsum", text: "No volcano is selected." })); return; }
  const events = timelineEvents(D, store).slice().reverse();
  const lag = lagOf(D.sit);
  box.replaceChildren(...[
    el("p", { class: "dsum", text: lag ? `The observatory and the official reports are ${durMin(lag.magnitude)} apart (lag).` : "No lag between the sources." }),
    el("p", { class: "dnote", text: "Official reports are reissued every few hours, so they trail the observatory: a lag is usual. The time bar's History shows these events on three lanes." }),
    el("button", { type: "button", class: "btn btn--small", dataset: { act: "history", focus: "hist-open" }, text: ui.historyOpen ? "Hide History on the time bar" : "Show History on the time bar" }),
    D.stepsMissing?.length ? el("p", { class: "dnote", text: "The chosen forecast step has no official area in the current products; no other step is drawn in its place." }) : null,
    el("ol", { class: "hist" }, ...events.map((e) => el("li", { class: `hist__item hist__item--${e.lane}` }, el("span", { class: "mono hist__t", text: hhmmz(e.t) }), el("span", { text: e.words })))),
    events.length ? null : el("p", { class: "empty", text: "No events in the last 9 hours." })].filter(Boolean));
}

// ------------------------------------------------------------------ Details › Data feeds (R8.3, R12.8)

export function feedsSection(D, store, target = $("feeds")) {
  const rows = store.feeds.slice().sort((a, b) => (FEED_STATUS[a.status]?.[3] ?? 9) - (FEED_STATUS[b.status]?.[3] ?? 9));
  const now = D?.now ?? Date.now();
  const ul = el("ul", { class: "feeds" });
  for (const f of rows) {
    const [id, color, word] = FEED_STATUS[f.status] || FEED_STATUS.NEVER;
    const last = ms(f.last_success_at);
    const statusWord = f.status === "DISABLED" && f.feed === "vona" ? "Off: no PVMBG permission (replay only)" : word;
    let line;
    if (f.status === "OK") line = `updated ${age((now - last) / 1000)} ago`;
    else if (f.status === "STALE") line = `last good ${age((now - last) / 1000)} ago · showing the last good copy`;
    else if (f.status === "ERROR") line = `last good ${Number.isFinite(last) ? `${age((now - last) / 1000)} ago` : "never"}`;
    else line = "";
    ul.append(el("li", { class: `feeds__row feeds__row--${f.status.toLowerCase()}` },
      el("span", { class: "feeds__name" }, FEED_NAME[f.feed] || f.feed, f.replay ? el("span", { class: "tag tag--replay", text: "recorded" }) : null),
      el("span", { class: `status status--${f.status.toLowerCase()}` }, st(id, color), statusWord),
      el("span", { class: "feeds__age", text: line }),
      techDetail(`last good (UTC): ${Number.isFinite(last) ? `${dayMonth(last)} ${hhmmz(last)}` : "never"} · records: ${f.record_count ?? 0} · feed key: ${f.feed}`, f.last_error || null)));
  }
  const db = store.state?.store;
  if (db) {
    const [id, color] = FEED_STATUS[db.ok ? "OK" : "ERROR"];
    const okAt = ms(db.last_ok_at);
    ul.append(el("li", { class: `feeds__row feeds__row--${db.ok ? "ok" : "error"}` },
      el("span", { class: "feeds__name", text: "Database" }),
      el("span", { class: `status status--${db.ok ? "ok" : "error"}` }, st(id, color), db.ok ? "Working" : "Error"),
      el("span", { class: "feeds__age", text: db.ok ? "reads and writes go through" : `failing since ${hhmmz(ms(db.last_error_at))}` }),
      techDetail(`last good (UTC): ${Number.isFinite(okAt) ? `${dayMonth(okAt)} ${hhmmz(okAt)}` : "never"}`, db.ok ? null : db.last_error)));
  }
  const by = {};
  for (const f of store.feeds) by[f.status] = (by[f.status] || 0) + 1;
  const replay = D?.mode === "REPLAY" && D.state.replay;
  target.replaceChildren(
    el("p", { class: "dsum", text: `${by.ERROR ? `${by.ERROR} failing · ` : ""}${by.STALE ? `${by.STALE} stale · ` : ""}${by.OK || 0} working · ${(by.DISABLED || 0) + (by.NEVER || 0)} off or not read` }),
    el("p", { class: "dnote", text: replay ? `REPLAY: every feed below plays a recording (${replay.label}). Nothing is live.` : "When a feed fails, TEPHRA shows the last good data with its time, and says so. It never shows substitute data." }),
    ul);
}

// The operator policy (GET /api/policy), summary first (R9.3): what it does in one sentence, then
// every margin, buffer and minimum the code applies, with its unit and why it has that value.
const POLICY_BLOCKS = [["exposure", "Exposure"], ["alternates", "Alternates"], ["planner", "Planner"], ["reroute", "Reroutes"], ["recovery", "Airport plan"], ["fuel", "Fuel"], ["drafts", "Drafts"], ["duty", "Duty Officer"]];
const isValue = (v) => v && typeof v === "object" && "value" in v && "unit" in v;

export function policyDialog(data) {
  const p = data?.policy;
  if (!p) return el("p", { text: "The operator policy could not be loaded." });
  const cites = Object.fromEntries((p.citations || []).map((c) => [c.id, c]));
  const margin = p.exposure?.vertical_margin_ft;
  const tbody = [];
  let n = 0;
  for (const [key, title] of POLICY_BLOCKS) {
    const rows = Object.entries(p[key] || {}).filter(([, v]) => isValue(v));
    if (!rows.length) continue;
    tbody.push(el("tbody", {}, el("tr", {}, el("th", { scope: "colgroup", colspan: "3", class: "policy__block", text: title })),
      ...rows.map(([name, v]) => {
        n++;
        const refs = (v.citation_ids || []).map((id) => cites[id]?.ref).filter(Boolean);
        return el("tr", {},
          el("th", { scope: "row", class: "mono", text: `${key}.${name}` }),
          el("td", { class: "mono", text: `${v.value} ${v.unit}` }),
          el("td", { text: [v.source, ...refs].join(" · ") }));
      })));
  }
  const quotes = (p.citations || []).map((c) => {
    const url = safeExternalUrl(c.url);
    return el("li", {}, el("strong", { text: c.ref }), el("q", { text: c.text }),
      url ? el("a", { class: "link-btn", href: url, target: "_blank", rel: "noopener noreferrer" }, icon("i-external-link"), "Source") : null);
  });
  return el("div", { class: "policy" },
    el("p", { class: "policy__lede" }, el("strong", { text: `Policy ${p.preset} (illustrative): ` }),
      `avoid every official ash area${isValue(margin) ? `, with ${Number(margin.value).toLocaleString("en")} ${margin.unit} above and below` : ""}. Not reviewed by an airline.`),
    el("p", { class: "muted", text: `${p.title} · v${p.version} · ${p.label} · risk owner: ${p.risk_owner} · SRA: ${p.sra_ref || "none (illustrative)"} · content hash #${String(data.policy_hash || "").slice(0, 12)}` }),
    el("details", { class: "more" }, el("summary", { text: "What the policy says in full" }), el("p", { text: p.summary_text })),
    el("details", { class: "more" }, el("summary", { text: `Show all ${n} values` }),
      el("table", { class: "table" }, el("caption", { class: "sr-only", text: "Operator policy values" }),
        el("thead", {}, el("tr", {}, ...["Name", "Value", "Why this value"].map((h) => el("th", { scope: "col", text: h })))), ...tbody)),
    el("details", { class: "more" }, el("summary", { text: "Source-trust order (what the code does today)" }),
      el("p", { class: "muted", text: "Operator choice. Doc 9974 asks the operator to resolve conflicts among its sources (2.4(d))." }),
      el("ol", { class: "policy__order" }, ...(p.source_order || []).map((r) => el("li", {}, el("span", { text: r.text }),
        el("span", { class: "muted", text: ` Applied by: ${r.enforced_by}` }))))),
    el("details", { class: "more" }, el("summary", { text: `Citations (${quotes.length})` }), el("ul", { class: "policy__cites" }, ...quotes)));
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
