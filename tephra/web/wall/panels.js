// The Wall's HTML panels (docs/UI-DESIGN.md section 7): command bar, honesty strip, legend,
// headline, flights and trace docks, timeline, level filter, the situation rail and the
// dialogs. Every feed or model string goes in with textContent (via el()).

import {
  $, el, icon, age, band, dayMon, durMin, fl, hhmmz, hhmmssz, idTime, hhmmBefore, ms, pad, solarHour, isNight,
  compassWord, kmBetween, safeExternalUrl, pointInGeom, dest, inBbox,
} from "./util.js";
import { actionWords, deciderName, SEV_RANK, NON_OBS, worstSeverity, LEVEL_MAX, levelIsAll, levelFrac } from "./derive.js";
import { CODE_LETTER } from "./images.js";
import { SAT } from "./map.js";

// ------------------------------------------------------------------ vocabulary (section 11)

export const FEED_NAME = {
  sigmet: "VA SIGMET (AWC)", vona: "VONA (MAGMA)", vaac_tokyo: "VAA Tokyo", vaac_darwin: "VAA Darwin", taf: "TAF",
  metar: "METAR", adsb: "ADS-B (adsb.lol)", winds: "Winds (Open-Meteo)", frames: "Satellite frames", hsd: "Himawari split window",
};
const FEED_STATUS = {
  ERROR: ["st-serious", "var(--c-serious)", "Error", 0],
  STALE: ["st-stale", "var(--c-caution)", "Stale", 1],
  OK: ["st-ok", "var(--c-ok)", "OK", 2],
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
const MODE_SHORT = { OFFICIAL: "TEPHRA area = official", WIDENED: "TEPHRA area widened", HYPOTHESIS: "HYPOTHESIS: MONITOR or HOLD only" };
const MODE_LINE = {
  OFFICIAL: "Same as the official area: TEPHRA adds nothing.",
  WIDENED: "Official area plus the observatory's drift, never smaller.",
  HYPOTHESIS: "No valid official product: a hypothesis. Only MONITOR or HOLD may be advised.",
};
const OUTCOME = {
  STUB: "NO MODEL: official products only",
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
export const ATTRIBUTION = "OpenFreeMap © OpenMapTiles · Data © OpenStreetMap contributors · © Mapterhorn · Aircraft: adsb.lol (ODbL 1.0) · Himawari-9 data: JMA via NOAA · FIR and VAAC lines: NOAA/NWS AWC (approximate)";

const codeColor = (code) => `var(--c-code-${(code || "UNKNOWN").toLowerCase()})`;
export const eruptIcon = (code, cls = "icon erupt") => icon("i-eruption", cls, codeColor(code));
const st = (id, color, cls = "st") => icon(id, cls, color);
const sevOf = (d) => SEV[d.severity] || SEV.INFO;
const kindOf = (d) => KIND[`${d.kind}/${d.aspect}`] || KIND[d.kind] || [d.kind, d.kind];
const cardName = (sit, sid) => sit.cards.find((c) => c.source_id === sid)?.title || sid.split(":").slice(0, 3).join(" ");

// ------------------------------------------------------------------ command bar, banner, strip

export function renderChrome(D, store, ui, A) {
  const s = D.state;
  const replay = s.mode === "REPLAY";
  document.body.dataset.mode = s.mode;
  document.title = `${replay ? "REPLAY - " : ""}TEPHRA Wall`;
  const banner = $("replay-banner");
  banner.hidden = !replay;
  if (replay && s.replay) {
    $("replay-banner-text").textContent = s.replay.banner;
    $("replay-banner-case").textContent = `· ${s.replay.label}${s.replay.auto ? " · switched automatically: no live activity" : ""}`;
    banner.title = s.replay.label;
  }
  const badge = $("mode-badge");
  badge.className = `mode-badge mode-badge--${replay ? "replay" : "live"}`;
  badge.replaceChildren(icon(replay ? "i-replay" : "i-live"), replay ? "REPLAY" : "LIVE");

  // region presets
  const cur = ui.region || s.region?.key;
  const regions = s.regions || [];
  $("regions").replaceChildren(...regions.map((r, i) => {
    const n = D.regionCounts[r.key] || 0;
    return el("button", { class: "region-btn", type: "button", "aria-pressed": r.key === cur ? "true" : "false", "aria-keyshortcuts": String(i + 1), dataset: { region: r.key, focus: `region-${r.key}` }, title: `${r.name} (key ${i + 1})` },
      el("kbd", { text: String(i + 1) }), el("span", { class: "region-btn__name", text: r.name }),
      n ? el("span", { class: "count", text: String(n), "aria-label": `${n} active` }) : null);
  }));
  const sel = $("region-select");
  if (sel) {
    sel.replaceChildren(...regions.map((r) => el("option", { value: r.key, text: `${r.name}${D.regionCounts[r.key] ? ` · ${D.regionCounts[r.key]} active` : ""}` })));
    sel.value = cur;
  }

  $("kpi-active").textContent = String(s.active_volcano_ids?.length ?? 0);
  $("kpi-exposed").textContent = String(s.exposed_count ?? 0);
  $("kpi-drafts").textContent = String(s.draft_count ?? 0);

  const model = $("model-chip");
  const stub = s.llm?.backend === "stub";
  model.className = `model-chip${stub ? "" : " model-chip--model"}`;
  model.replaceChildren(icon(stub ? "i-code" : "i-model"), el("span", { text: s.llm?.label || "NO MODEL" }));
  model.title = "Steps that call a model are marked AI-drafted; with NO MODEL, code templates stand in.";

  const by = {};
  for (const f of store.feeds) by[f.status] = (by[f.status] || 0) + 1;
  const parts = [];
  for (const k of ["ERROR", "STALE", "OK", "NEVER", "DISABLED"]) {
    if (!by[k]) continue;
    const [id, color] = FEED_STATUS[k];
    const word = { ERROR: "error", STALE: "stale", OK: "OK", NEVER: "not polled", DISABLED: "off" }[k];
    parts.push(el("span", { class: `feeds-chip__part feeds-chip__part--${k.toLowerCase()}` }, st(id, color), `${by[k]} ${word}`));
  }
  $("feeds-chip").replaceChildren(el("span", { class: "caps feeds-chip__cap", text: "Feeds" }), ...parts);
  $("feeds-chip").setAttribute("aria-label", `Feed health: ${parts.map((p) => p.textContent).join(", ")}. Open details.`);

  $("disclaimer").textContent = s.disclaimer || "Decision support only - fictional airline - not for operational use";
  const policy = s.policy;
  const policyBtn = $("policy-btn");
  policyBtn.hidden = !policy;
  if (policy) {
    // Short: the footer's credit line shares this row (phones open it from About instead).
    policyBtn.textContent = `Policy ${policy.preset} · illustrative`;
    policyBtn.title = `${policy.policy_id} v${policy.version}: ${policy.label}. Open its values and sources.`;
  }
  const extra = [];
  if (ui.sat !== "off") extra.push("Imagery: NASA GIBS");
  if (ui.so2) extra.push(`${ui.sat === "off" ? "Imagery: NASA GIBS · " : ""}Contains modified Copernicus Sentinel data ${new Date(D.now).getUTCFullYear()}`);
  const attrib = [ATTRIBUTION, ...extra].join(" · ");
  $("attribution").textContent = attrib;
  $("attribution").title = attrib;
}

export function renderClock(D, conn) {
  if (!D) return;
  // While the stream is lost the clock stops at the last event: the data froze there too.
  $("clock-time").textContent = hhmmssz(conn.lostAt ? conn.lostAt : D.now);
  $("clock-time").dataset.stale = conn.lostAt ? "true" : "false";
  const sub = $("clock-sub");
  if (conn.lostAt) {
    sub.textContent = `STREAM LOST · last ${hhmmssz(conn.lostAt)}`;
    sub.dataset.tone = "caution";
  } else {
    sub.textContent = `${dayMon(D.now)} · ${D.mode === "REPLAY" ? "REPLAY CLOCK" : "UTC"}`;
    sub.dataset.tone = D.mode === "REPLAY" ? "replay" : "";
  }
}

// ------------------------------------------------------------------ legend (7.5)

export function renderLegend(D, ui) {
  const box = $("legend");
  const open = ui.legendOpen;
  box.classList.toggle("legend--collapsed", !open);
  const btn = el("button", { class: "legend__toggle", type: "button", "aria-expanded": open ? "true" : "false", "aria-controls": "legend-body", "aria-keyshortcuts": "L", dataset: { act: "legend", focus: "legend-toggle" } },
    el("span", { class: "caps", text: "Legend" }), icon(open ? "i-chevron-up" : "i-chevron-down"), el("kbd", { text: "L" }));
  if (!open) { box.replaceChildren(btn); return; }
  const li = (sw, label, sub) => el("li", {}, sw, el("span", {}, el("strong", { text: label }), sub ? el("span", { class: "legend__sub", text: ` ${sub}` }) : null));
  const sw = (id, cls) => icon(id, `sw ${cls}`);
  const hasStep = D.official.some((f) => f.properties.show && f.properties.step !== "now");
  const hasSector = D.cones.some((f) => f.properties.part === "sector");
  const anyExposed = D.exposed.length > 0;
  const anyOther = D.aircraft.some((f) => !f.properties.exposed);
  const rows = [
    li(sw("lg-area-official", "sw--official"), "Official ash area", "· binding"),
    hasStep ? li(sw("lg-area-forecast", "sw--official"), "Official forecast", "· +6 h dashed") : null,
    ui.layers.tephra && D.cones.length ? li(sw("lg-area-tephra", "sw--tephra"), "TEPHRA cautious area", "· never smaller; drawn just outside what it contains") : null,
    hasSector ? li(sw("lg-area-hatch", "sw--tephra"), "Widened by the model") : null,
    D.rose && ui.layers.rose ? li(sw("lg-arrow-official", "sw--official"), "Official movement") : null,
    D.rose && ui.layers.rose ? li(sw("lg-arrow-observer", "sw--observer"), "Observatory drift") : null,
    anyExposed ? li(sw("i-aircraft", "sw--exposed"), "Flight entering the area") : null,
    ui.layers.reroutes && D.hasReroutes ? li(sw("lg-reroute", "sw--reroute"), "Reroute", "· turn points in ICAO form") : null,
    ui.layers.satboxes && D.hasSatBoxes ? li(sw("lg-satbox", "sw--sat"), "Satellite check box", "· AI-drawn, supporting only") : null,
    anyOther ? li(sw("i-aircraft", "sw--aircraft"), "Other airline flight") : null,
    el("li", { class: "legend__codes" }, el("span", { class: "codes" }, ...["GREEN", "YELLOW", "ORANGE", "RED", "UNKNOWN"].map((c) => eruptIcon(c, "icon"))), el("span", { text: "Aviation colour code: G Y O R, U unknown" })),
    ui.d3 ? li(sw("i-3d", "sw--plain"), "3D view", "· heights ×6") : null,
    ui.compare ? li(sw("i-swipe", "sw--plain"), "Compare", "· A official products only, B with TEPHRA's area") : null,
  ];
  if (ui.sat !== "off") rows.push(li(sw("i-satellite", "sw--plain"), `${SAT[ui.sat].short} satellite`, "· context only"));
  if (ui.so2) rows.push(li(sw("i-satellite", "sw--plain"), "SO2 column", "· context only, SO2 is not ash"));
  const body = el("div", { id: "legend-body" }, el("ul", {}, rows), el("p", { class: "legend__ctx", text: "FIR and VAAC lines approximate" }));
  box.replaceChildren(btn, body);
}

// ------------------------------------------------------------------ headline and notes (7.6)

export function renderHeadline(D, ui, notes, store) {
  const h = $("headline");
  const sit = D.sit;
  if (!sit) { h.hidden = true; } else {
    h.hidden = false;
    const cone = D.coneOf(sit.volcano_id)?.properties;
    const kids = [el("span", { class: "headline__volcano" }, eruptIcon(sit.color_code), sit.volcano_name.toUpperCase())];
    const sep = () => el("span", { class: "headline__sep", "aria-hidden": "true", text: "·" });
    const worst = sit.discrepancies.filter((d) => d.severity !== "INFO").sort((a, b) => (SEV_RANK[b.severity] || 0) - (SEV_RANK[a.severity] || 0))[0];
    if (worst) {
      const [tone, sid, word] = sevOf(worst);
      const dir = sit.discrepancies.find((d) => d.kind === "DIRECTION_MISMATCH" && d.aspect === "direction");
      const text = worst.severity === "WARNING" ? `${word}: ${kindOf(worst)[1].replace(/^A /, "a ")}` : dir ? `Direction disagreement ${Math.round(dir.magnitude)}°` : kindOf(worst)[1];
      kids.push(sep(), el("span", { class: `headline__dis headline__dis--${tone}` }, st(sid, `var(--c-${tone})`), text));
    }
    if (cone) kids.push(sep(), el("span", { class: "headline__area", text: MODE_SHORT[cone.mode] || cone.mode }));
    const n = sit.exposed_count || 0;
    kids.push(sep(), el("span", { class: n ? "headline__flights" : "", text: `${n} flight${n === 1 ? "" : "s"} entering` }));
    const decided = store.advisories.filter((a) => a.volcano_id === sit.volcano_id && (a.status === "APPROVED" || a.status === "EDITED"));
    if (decided.length) kids.push(sep(), el("span", { class: "headline__ok" }, icon("i-approved"), `${decided.length} approved`));
    if (ui.d3) kids.push(el("span", { class: "headline__chip", title: "3D view, heights exaggerated six times", text: "3D ×6" }));
    h.classList.toggle("headline--hypothesis", cone?.mode === "HYPOTHESIS");
    if (cone?.mode === "HYPOTHESIS") {
      h.replaceChildren(st("st-caution", "var(--c-caution)"), el("span", { text: `HYPOTHESIS: no valid official product for ${sit.volcano_name}. MONITOR or HOLD only.` }));
    } else h.replaceChildren(...kids);
  }
  const box = $("map-notes");
  box.replaceChildren(...notes.map((n) => el("p", { class: `map-note map-note--${n.tone || "info"}`, role: n.tone === "serious" ? "alert" : null },
    n.tone === "serious" ? st("st-serious", "var(--c-serious)") : n.tone === "caution" ? st("st-caution", "var(--c-caution)") : st("st-info", "var(--c-info)"),
    el("span", { text: n.text }), n.action ? el("button", { type: "button", class: "link-btn", dataset: { act: n.action }, text: n.actionText }) : null)));
}

export function mapNotes(D, ui, store, extra) {
  const notes = [];
  if (extra.error) notes.push({ tone: "serious", text: extra.error, action: "retry", actionText: "Retry now" });
  if (extra.basemap) notes.push({ tone: "info", text: extra.basemap });
  if (!D) return notes;
  if (!D.levelAll) {
    const parts = [];
    if (D.hiddenOfficial) parts.push(`${D.hiddenOfficial} official area${D.hiddenOfficial === 1 ? "" : "s"}`);
    if (D.hiddenFlights) parts.push(`${D.hiddenFlights} flight${D.hiddenFlights === 1 ? "" : "s"}`);
    notes.push({ tone: "caution", text: `Level filter ${fl(ui.level.min)}–${fl(ui.level.max)}${parts.length ? ` hides ${parts.join(" and ")}` : " is on"}` });
  }
  const cov = coverageNote(D, store);
  if (cov && ui.layers.aircraft) notes.push({ tone: "info", text: cov });
  return notes;
}

function coverageNote(D, store) {
  const sit = D.sit;
  if (!sit) return null;
  const adsb = store.feeds.find((f) => f.feed === "adsb");
  if (!adsb || adsb.status !== "OK") return null;
  const v = D.vents.get(sit.volcano_id);
  if (!v) return null;
  const near = D.aircraft.some((f) => kmBetween(f.geometry.coordinates, v) < 150);
  return near ? null : `No aircraft seen within 150 km of ${sit.volcano_name} in the open ADS-B feed. Receiver coverage is patchy here: an empty map is not an empty sky.`;
}

// ------------------------------------------------------------------ advisory status line (3.2)

export function advisoryLine(a, recorded) {
  if (!a) return null;
  const act = actionWords(a);
  const who = deciderName(a);
  const at = a.decided_at ? hhmmz(ms(a.decided_at)) : "";
  const M = {
    DRAFT: ["i-clock", "draft", `${act} drafted · awaiting dispatcher`],
    APPROVED: ["i-approved", "ok", `${act} approved by ${who}${at ? ` · ${at}` : ""}`],
    EDITED: ["i-approved", "ok", `${act} approved with edits by ${who}${at ? ` · ${at}` : ""}`],
    REJECTED: ["i-rejected", "serious", `Rejected by ${who}${at ? ` · ${at}` : ""}`],
    SUPERSEDED: ["i-superseded", "off", "Replaced by a newer draft"],
  };
  const [ic, tone, text] = M[a.status] || M.DRAFT;
  return el("span", { class: `adv adv--${tone}` }, icon(ic), el("span", { text }), a.status === "EDITED" ? icon("i-pencil") : null, recorded ? el("span", { class: "tag tag--replay", text: "recorded" }) : null);
}

// ------------------------------------------------------------------ flights dock (7.8)

export function renderFlights(D, store, ui, target = $("flights"), opts = {}) {
  if (!D) {
    target.replaceChildren(el("div", { class: "dock__head" }, el("h2", { class: "caps", text: "Flights entering TEPHRA's area" })), el("div", { class: "skeleton" }), el("div", { class: "skeleton" }));
    return;
  }
  // Scoped to the selected volcano (or the empty region), so the dock, the headline and the
  // map count the same flights; the rest are one click away.
  const region = (D.state.regions || []).find((r) => r.key === (ui.region || D.state.region?.key));
  const scopeName = D.sit ? D.sit.volcano_name : region ? region.name : null;
  const inScope = (f) => (D.sit ? f.properties.volcano_id === D.selected : region ? (D.vents.get(f.properties.volcano_id) ? inBbox(D.vents.get(f.properties.volcano_id), region.bbox) : false) : true);
  const flights = D.exposed.filter(inScope);
  const others = new Map();
  for (const f of D.exposed) if (!inScope(f)) others.set(f.properties.volcano_id, (others.get(f.properties.volcano_id) || 0) + 1);
  const max = opts.max ?? (window.innerWidth < 1600 ? 3 : 4);
  const replay = D.mode === "REPLAY";
  const shownN = opts.all ? flights.length : Math.min(max, flights.length);
  const head = el("div", { class: "dock__head" },
    el("h2", { class: "caps flights__title" }, "Flights entering", scopeName ? el("span", { class: "flights__scope", text: ` · ${scopeName}` }) : null),
    el("span", { class: "dock__count", text: flights.length > shownN ? `${shownN} of ${flights.length}` : String(flights.length) }),
    replay ? el("span", { class: "tag tag--replay", text: "recorded" }) : null);
  const foot = others.size ? el("div", { class: "flights__foot" }, ...[...others].slice(0, 2).map(([vid, n]) => {
    const name = D.sits.find((s) => s.volcano_id === vid)?.volcano_name || vid;
    return el("button", { type: "button", class: "link-btn", dataset: { act: "select", vid, focus: `others-${vid}` }, text: `+${n} entering at ${name}` });
  })) : null;
  if (!flights.length) {
    const adsb = store.feeds.find((f) => f.feed === "adsb");
    let note;
    if (!adsb || adsb.status !== "OK") note = replay ? "No aircraft data in this recording." : "No aircraft data right now (ADS-B feed not OK).";
    else note = coverageNote(D, store) || "Tracks are projected on current heading, speed and level.";
    const where = D.sit ? "TEPHRA's area" : scopeName ? `a TEPHRA area in ${scopeName}` : "TEPHRA's area";
    target.replaceChildren(head, el("p", { class: "dock__empty" }, el("strong", { text: `No flight is projected to enter ${where}.` }), " ", note), ...(foot ? [foot] : []));
    target.classList.add("dock--empty");
    return;
  }
  target.classList.remove("dock--empty");
  const list = el("ol", { class: "flights__list" });
  for (const f of flights.slice(0, shownN)) {
    const p = f.properties;
    const plane = icon("i-aircraft", "flights__plane");
    plane.style.transform = `rotate(${p.track_deg || 0}deg)`;
    const right = p.inside
      ? el("span", { class: "flights__inside" }, st("st-inside", "var(--c-tephra)"), "INSIDE NOW")
      : el("span", { class: "flights__mins" }, el("b", { text: String(p.minutes_to_entry) }), " MIN");
    const lvl = p.alt_baro_ft != null ? fl(p.alt_baro_ft) : "level unknown";
    const meta = [p.callsign, p.type_icao, lvl].filter(Boolean).join(" · ");
    const old = p.stale ? `position ${Math.max(1, Math.round(p.ageS / 60))} min old` : null;
    const adv = D.advByFlight.get(`${p.hex}:${p.volcano_id}`);
    const btn = el("button", { class: "flights__row", type: "button", title: old ? `${p.proxy_flight}: ${old}` : null, dataset: { flight: f.id ?? p.hex, focus: `flight-${p.hex}` }, "aria-label": `${p.proxy_flight}, ${meta}, ${p.inside ? "inside TEPHRA's area now" : `enters in ${p.minutes_to_entry} minutes`}${old ? `, ${old}` : ""}. Show on map.` },
      plane,
      el("span", { class: "flights__id" },
        el("span", { class: "flights__proxy", text: p.proxy_flight }),
        el("span", { class: "flights__meta", text: meta })),
      right,
      adv ? el("span", { class: "flights__status" }, advisoryLine(adv, false)) : null);
    list.append(el("li", {}, btn));
  }
  target.replaceChildren(head, list, ...(foot ? [foot] : []));
}

// ------------------------------------------------------------------ trace dock (7.9)

export function traceLines(store, D, ui) {
  const sel = D?.selected;
  const all = ui.traceScope === "all";
  return store.trace.filter((t) => all || !t.volcano_id || t.volcano_id === sel);
}

export function renderTrace(D, store, ui, conn, target = $("trace"), opts = {}) {
  const lines = traceLines(store, D, ui);
  const expanded = ui.traceExpanded || opts.full;
  const n = opts.full ? 60 : expanded ? 14 : window.innerWidth < 1360 ? 1 : window.innerWidth < 1600 || ui.present ? 2 : 4;
  const shown = lines.slice(-n);
  target.classList.toggle("trace--expanded", !!ui.traceExpanded && !opts.full);
  target.classList.toggle("is-stale", !!conn.lostAt);
  const scope = el("div", { class: "seg seg--small", role: "group", "aria-label": "Trace scope" },
    el("button", { type: "button", "aria-pressed": ui.traceScope !== "all" ? "true" : "false", dataset: { act: "trace-scope", scope: "volcano", focus: "trace-scope-v" }, text: "This volcano" }),
    el("button", { type: "button", "aria-pressed": ui.traceScope === "all" ? "true" : "false", dataset: { act: "trace-scope", scope: "all", focus: "trace-scope-a" }, text: "All" }));
  const head = el("div", { class: "dock__head" },
    el("h2", { class: "caps", text: "Reasoning trace" }),
    D?.mode === "REPLAY" ? el("span", { class: "tag tag--replay", text: "recorded" }) : null,
    el("span", { class: "dock__count", text: conn.lostAt ? `paused at ${hhmmssz(conn.lostAt)}` : `${lines.length} step${lines.length === 1 ? "" : "s"}` }),
    scope,
    opts.full ? null : el("button", { type: "button", class: "link-btn trace__expand", "aria-expanded": ui.traceExpanded ? "true" : "false", "aria-keyshortcuts": "T", dataset: { act: "trace-expand", focus: "trace-expand" } }, ui.traceExpanded ? "Collapse" : "Expand", el("kbd", { text: "T" })));
  if (!D) { target.replaceChildren(head, el("div", { class: "skeleton" }), el("div", { class: "skeleton" })); return; }
  const ol = el("ol", { class: "trace__list", role: "log", "aria-live": "off", "aria-label": "Reasoning trace steps", tabindex: "0" });
  if (!shown.length) ol.append(el("li", { class: "trace__empty", text: "No steps yet." }));
  for (const t of shown) {
    const [ic, name] = ACTOR[t.actor] || ["i-system", String(t.actor || "").toUpperCase()];
    const lvl = t.level === "error" ? st("st-serious", "var(--c-serious)") : t.level === "warn" ? st("st-caution", "var(--c-caution)") : null;
    ol.append(el("li", { class: `trace__line${ui.freshTrace?.has(t.id) ? " is-new" : ""}`, title: t.message },
      el("span", { class: "trace__time", text: hhmmssz(ms(t.at)) }),
      el("span", { class: "trace__stage", text: t.stage }),
      el("span", { class: `actor actor--${t.actor}` }, icon(ic), name),
      el("span", { class: "trace__msg" }, lvl, el("span", { text: t.message }))));
  }
  target.replaceChildren(head, ol);
  ol.scrollTop = ol.scrollHeight;
}

// ------------------------------------------------------------------ volcano tabs (7.10)

export function renderTabs(D, conn) {
  const box = $("volcano-tabs");
  if (!D) { box.replaceChildren(el("span", { class: "skeleton skeleton--tab" }), el("span", { class: "skeleton skeleton--tab" })); return; }
  box.classList.toggle("is-stale", !!conn.lostAt);
  const anySel = D.sits.some((s) => s.volcano_id === D.selected);
  box.replaceChildren(...D.sits.map((s, i) => {
    const sel = s.volcano_id === D.selected;
    const worst = worstSeverity(s);
    const nCheck = s.discrepancies.filter((d) => (SEV_RANK[d.severity] || 0) >= 2).length;
    const cone = D.coneOf(s.volcano_id)?.properties;
    const kids = [eruptIcon(s.color_code), el("span", { class: "vtab__name", text: s.volcano_name })];
    if (cone?.mode === "HYPOTHESIS") kids.push(el("span", { class: "badge badge--caution", "aria-label": "hypothesis" }, st("st-caution", "var(--c-caution)"), "H"));
    if (nCheck) kids.push(el("span", { class: `badge badge--${worst >= 3 ? "serious" : "caution"}`, "aria-label": `${nCheck} difference${nCheck === 1 ? "" : "s"} to check` }, st(worst >= 3 ? "st-serious" : "st-caution", worst >= 3 ? "var(--c-serious)" : "var(--c-caution)"), String(nCheck)));
    if (s.exposed_count) kids.push(el("span", { class: "badge badge--flights", "aria-label": `${s.exposed_count} flight${s.exposed_count === 1 ? "" : "s"} entering` }, icon("i-aircraft"), String(s.exposed_count)));
    return el("button", { class: "vtab", role: "tab", type: "button", id: `tab-${s.volcano_id}`, "aria-selected": sel ? "true" : "false", "aria-controls": "brief", tabindex: sel || (!anySel && i === 0) ? "0" : "-1", dataset: { vid: s.volcano_id, focus: `tab-${s.volcano_id}` } }, ...kids);
  }));
}

// ------------------------------------------------------------------ situation rail

export function renderBrief(D, store, ui, A) {
  const brief = $("brief");
  if (!D) {
    brief.replaceChildren(...[1, 2, 3, 4, 5].map(() => el("div", { class: "skeleton skeleton--block" })));
    return;
  }
  const sit = D.sit;
  if (!sit) {
    const region = (D.state.regions || []).find((r) => r.key === (ui.region || D.state.region?.key));
    const others = (D.state.regions || []).filter((r) => D.regionCounts[r.key]);
    brief.replaceChildren(
      el("section", { class: "sec sec--empty", "data-ptab": "brief" },
        el("h1", { class: "vhead__name", text: `No active volcano in ${region?.name || "this region"}.` }),
        el("p", { class: "muted", text: "A volcano is active when it has a VONA in the last 24 h, a current VAA, or a valid VA SIGMET near it." }),
        el("div", { class: "btn-row" }, ...others.map((r) => el("button", { type: "button", class: "btn", dataset: { region: r.key }, text: `${r.name} · ${D.regionCounts[r.key]} active` })))),
      decisionsSection(D, store, ui));
    return;
  }
  const cone = D.coneOf(sit.volcano_id)?.properties;
  const head = el("section", { class: "vhead-wrap", "data-ptab": "brief" },
    el("div", { class: "vhead" },
      el("h1", { class: "vhead__name", id: "volcano-name", tabindex: "-1", text: sit.volcano_name }),
      el("span", { class: "code-chip", title: `Aviation colour code ${sit.color_code}` }, eruptIcon(sit.color_code), sit.color_code),
      el("span", { class: "vhead__asof", text: `as of ${hhmmz(ms(sit.as_of))}` })),
    el("p", { class: "vreasons", text: sit.active_reasons.join(" · ") }),
    cone?.mode === "HYPOTHESIS" ? hypothesisBanner(sit) : null);
  brief.replaceChildren(head, sourcesSection(D, sit, A), disagreeSection(D, sit, ui), areaSection(D, sit, ui),
    el("section", { class: "sec sec--phone", "data-ptab": "flights", id: "rail-flights" }),
    decisionsSection(D, store, ui),
    el("section", { class: "sec sec--phone", "data-ptab": "trace", id: "rail-trace" }));
}

function hypothesisBanner(sit) {
  return el("p", { class: "hyp-banner", role: "note" }, st("st-caution", "var(--c-caution)"),
    el("span", { text: `HYPOTHESIS: no valid official product for ${sit.volcano_name}. TEPHRA's area is a hypothesis built from the observatory report. Advisories are limited to MONITOR or HOLD.` }));
}

function secHead(id, title, aside) {
  return el("div", { class: "sec__head" }, el("h2", { id, class: "caps", text: title }), aside ? el("span", { class: "sec__aside", text: aside }) : null);
}

// 7.12 the comparison grid: SIGMET, VAA | VONA
function sourcesSection(D, sit) {
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
  const grid = el("div", { class: "cmp", role: "table", "aria-label": "Sources side by side: SIGMET, VAA and VONA" });
  const hdrRow = el("div", { class: "cmp__row cmp__row--head", role: "row" }, el("div", { class: "cmp__corner", role: "columnheader" }, el("span", { class: "sr-only", text: "Field" })));
  order.forEach((card, i) => {
    if (i === 2) hdrRow.append(el("div", { class: "cmp__divider", "aria-hidden": "true" }));
    hdrRow.append(colHead(D, sit, card, vent, flagged));
  });
  grid.append(hdrRow);
  const value = (card, row) => {
    const f = card.display_fields || {};
    if (row === "seen") {
      if (lag?.values[card.source_id]) return lag.values[card.source_id];
      if (card.kind === "VONA") return f.Issued ? `${f.Issued.split("/")[1] || f.Issued}` : "—";
      if (card.kind === "VAA") return f.Observation || "—";
      return f.Observed || "—";
    }
    if (row === "height") {
      if (card.kind === "VONA") return f["Cloud top"] ? [f["Cloud top"].replace(/\s*\(.*\)$/, ""), f["Cloud top"]] : "—";
      return f.Band || "—";
    }
    if (row === "move") return dirD?.values[card.source_id] || f.Movement || "—";
    if (row === "valid") {
      if (card.kind === "SIGMET") return card.valid_to ? `until ${hhmmz(ms(card.valid_to))}` : "—";
      if (card.kind === "VAA") {
        const m = /(\d{8})\/(\d{4})Z/.exec(f["Next advisory"] || "");
        return m ? `next by ${m[2]}Z` : f["Next advisory"] || "—";
      }
      return "—";
    }
    if (row === "code") return card.kind === "SIGMET" ? "—" : f["Colour code"] || "—";
    return "—";
  };
  const compact = window.innerWidth < 1360 && window.innerWidth > 600;
  const rows = [["seen", "Seen at"], ["height", "Height"], ["move", "Movement"], ["valid", "Valid"], ["code", "Colour code"]].filter(([r]) => !compact || ["seen", "height", "move"].includes(r));
  for (const [row, label] of rows) {
    const r = el("div", { class: "cmp__row", role: "row" }, el("div", { class: "cmp__rowlabel", role: "rowheader", text: label }));
    order.forEach((card, i) => {
      if (i === 2) r.append(el("div", { class: "cmp__divider", "aria-hidden": "true" }));
      if (card.missing) {
        r.append(el("div", { class: "cmp__cell cmp__cell--missing", role: "cell" }, el("span", { class: "sr-only", text: "none" })));
        return;
      }
      let v = value(card, row);
      let title = null;
      if (Array.isArray(v)) [v, title] = v;
      const flag = flagged.get(`${card.source_id}|${row}`);
      const cls = ["cmp__cell", v === "—" ? "cmp__cell--empty" : "", flag ? "cmp__cell--flag" : card.kind === "VONA" && row === "move" ? "cmp__cell--observer" : ""].filter(Boolean).join(" ");
      r.append(el("div", { class: cls, role: "cell", title: title || (v !== "—" ? v : null) }, flag ? st("st-caution", "var(--c-caution)") : null, el("span", { text: v }), flag ? el("span", { class: "sr-only", text: " (flagged: disagrees)" }) : null));
    });
    grid.append(r);
  }
  const foot = el("div", { class: "cmp__row cmp__row--foot", role: "row" }, el("div", { role: "cell" }));
  order.forEach((card, i) => {
    if (i === 2) foot.append(el("div", { class: "cmp__divider", "aria-hidden": "true" }));
    foot.append(card.missing ? el("div", { role: "cell" }) : el("div", { class: "cmp__foot", role: "cell" },
      el("span", { class: "mono", text: `#${card.sha256_short || ""}` }),
      el("button", { type: "button", class: "link-btn", dataset: { act: "raw", kind: card.kind, focus: `raw-${card.kind}` }, "aria-label": `Raw text of ${card.title}` }, icon("i-raw-text"), "Raw text")));
  });
  grid.append(foot);
  return el("section", { class: "sec", "aria-labelledby": "h-sources", "data-ptab": "sources" }, secHead("h-sources", "What the sources say", "Official products are binding"), grid);
}

function colHead(D, sit, card, vent, flagged) {
  const observer = card.kind === "VONA";
  const cls = `cmp__colhead${observer ? " cmp__colhead--observer" : ""}${card.missing ? " cmp__colhead--missing" : ""}${flagged.get(`${card.source_id}|head`) ? " cmp__colhead--flag" : ""}`;
  const kind = card.kind === "VONA" ? "VONA · observatory" : card.kind === "SIGMET" ? "SIGMET · binding" : "VAA · VAAC";
  if (card.missing) {
    const hyp = D.coneOf(sit.volcano_id)?.properties.mode === "HYPOTHESIS" && !observer;
    return el("div", { class: cls, role: "columnheader" }, el("div", { class: "cmp__kind", text: kind }), el("div", { class: "cmp__title", text: hyp ? "No valid official product" : "None in force" }),
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

// 7.13 where they disagree
function disagreeSection(D, sit, ui) {
  const items = sit.discrepancies.slice().sort((a, b) => (SEV_RANK[b.severity] || 0) - (SEV_RANK[a.severity] || 0));
  const check = items.filter((d) => d.severity !== "INFO");
  const info = items.filter((d) => d.severity === "INFO");
  const list = el("ol", { class: "dis" });
  for (const d of check) list.append(disCard(D, sit, d, ui));
  const infoRows = info.map((d) => infoRow(d));
  for (const card of sit.cards) {
    if (card.missing || !NON_OBS.has(card.evidence)) continue;
    infoRows.push(el("li", { class: "dis__item dis__item--info" },
      el("div", { class: "dis__sev" }, el("span", { class: "sev sev--info" }, st("st-info", "var(--c-info)"), "INFO"), el("span", { class: "dis__kind", text: "NOT OBSERVED" })),
      el("div", {}, el("p", { class: "dis__headline", text: `${card.kind} could not see the ash` }), el("p", { class: "dis__detail", text: "Not evidence of no ash; it never shrinks TEPHRA's area or weakens an advisory." }))));
  }
  if (infoRows.length > 2 && !ui.harmlessOpen) {
    const kinds = [...info.map((d) => kindOf(d)[0]), ...sit.cards.filter((c) => !c.missing && NON_OBS.has(c.evidence)).map(() => "NOT OBSERVED")];
    list.append(el("li", { class: "dis__item dis__item--info dis__item--more" },
      el("button", { type: "button", class: "link-btn dis__more", "aria-expanded": "false", dataset: { act: "harmless", focus: "harmless" } }, st("st-info", "var(--c-info)"), `Harmless (${infoRows.length}): ${kinds.join(" · ")}`, icon("i-chevron-down"))));
  } else {
    list.append(...infoRows);
    if (infoRows.length > 2) list.append(el("li", {}, el("button", { type: "button", class: "link-btn", "aria-expanded": "true", dataset: { act: "harmless", focus: "harmless" } }, "Collapse the harmless items", icon("i-chevron-up"))));
  }
  if (!items.length && !infoRows.length) list.append(el("li", { class: "empty", text: "No differences found between the products in force." }));
  return el("section", { class: "sec", "aria-labelledby": "h-dis", "data-ptab": "brief" },
    secHead("h-dis", "Where they disagree", `${check.length} to check · ${infoRows.length} harmless`), list);
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
    else if (cone?.mode === "OFFICIAL") tail = ` TEPHRA has not widened the area (${D.state.llm?.label || "NO MODEL"}).`;
    body.append(el("p", { class: "dis__explain", text: `A point 15 km along the observatory's drift is outside the official polygon.${tail}` }));
  } else if (EXPLAIN[d.kind]) {
    body.append(el("p", { class: "dis__explain", text: EXPLAIN[d.kind] }));
  }
  if (d.kind === "DIRECTION_MISMATCH" && D.rose) body.append(el("button", { type: "button", class: "link-btn", dataset: { act: "frame", focus: `show-${d.id}` } }, icon("i-frame"), "Show on map"));
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

// 7.13 TEPHRA cautious area card
function areaSection(D, sit, ui) {
  const coneF = D.coneOf(sit.volcano_id);
  const wrap = (kids) => el("section", { class: "sec", "aria-labelledby": "h-area", "data-ptab": "brief" }, secHead("h-area", "TEPHRA cautious area", "an estimate, not a forecast"), ...kids);
  if (!coneF) return wrap([el("p", { class: "empty", text: "No TEPHRA area yet for this volcano." })]);
  const cone = coneF.properties;
  const a = sit.assessment;
  const outcome = a?.outcome;
  const facts = el("dl", { class: "area__facts" },
    el("dt", { text: "Rule" }), el("dd", { text: "Never smaller than any valid official polygon" }),
    el("dt", { text: "Read by" }), el("dd", { text: outcome === "STUB" || (!outcome && D.state.llm?.backend === "stub") ? OUTCOME.STUB : outcome === "PENDING" ? OUTCOME.PENDING : `${a && a.llm_backend !== "stub" && a.model_id ? a.model_id : D.state.llm?.label || "NO MODEL"} · ${OUTCOME[outcome] || "—"}` }),
    el("dt", { text: "Valid until" }), el("dd", { class: "mono", text: hhmmz(ms(cone.valid_to)) }));
  if (cone.mode !== "OFFICIAL") facts.append(el("dt", { text: "Confidence" }), el("dd", { text: `${Math.round((cone.confidence ?? 0) * 100)}% in the widening` }));
  const kids = [
    el("div", { class: "area__top" }, el("span", { class: `mode-chip mode-chip--${cone.mode.toLowerCase()}`, text: cone.mode }), el("span", { class: "area__band", text: band(cone.base_ft, cone.top_ft) }), el("span", { class: "area__label mono", text: cone.label })),
    el("p", { class: "area__line", text: MODE_LINE[cone.mode] || "" }),
  ];
  if (outcome === "MODEL_FAILED") kids.push(el("p", { class: "area__note" }, st("st-caution", "var(--c-caution)"), `AI unavailable: ${a?.estimate?.uncertainty_notes || "no usable model output"}`));
  kids.push(facts);
  const est = a?.estimate;
  const model = a && a.llm_backend && a.llm_backend !== "stub" && outcome !== "STUB";
  if (model && est) {
    const read = el("details", { class: "area__read", open: ui.readOpen ? true : null, dataset: { act: "read-toggle" } },
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

// 7.14 decisions list
function decisionsSection(D, store, ui) {
  const all = store.advisories.slice().sort((a, b) => ms(b.updated_at) - ms(a.updated_at)).slice(0, 20);
  const advs = all.filter((a) => a.status !== "SUPERSEDED");
  const superseded = all.filter((a) => a.status === "SUPERSEDED");
  const list = el("ol", { class: "decisions" });
  const replay = D.mode === "REPLAY";
  for (const a of advs) {
    const decided = a.status === "APPROVED" || a.status === "EDITED" || a.status === "REJECTED";
    const tone = a.status === "REJECTED" ? "serious" : decided ? "ok" : "draft";
    const fresh = ui.freshDecisions?.has(a.id);
    const right = a.status === "DRAFT"
      ? el("span", { class: "decisions__who", text: `drafted ${age((D.now - ms(a.created_at)) / 1000)} ago` })
      : el("span", { class: "decisions__who mono", text: `${deciderName(a)}${a.decided_at ? ` · ${hhmmz(ms(a.decided_at))}` : ""}` });
    const status = {
      DRAFT: ["i-clock", "Awaiting dispatcher"], APPROVED: ["i-approved", "Approved"], EDITED: ["i-approved", "Approved with edits"],
      REJECTED: ["i-rejected", "Rejected"],
    }[a.status] || ["i-clock", a.status];
    list.append(el("li", { class: `decisions__item decisions__item--${tone}${fresh ? " is-stamped" : ""}`, dataset: { adv: a.id } },
      el("span", { class: `decisions__status adv--${tone}` }, icon(status[0]), el("span", { text: status[1] }), a.status === "EDITED" ? icon("i-pencil") : null),
      el("span", { class: "decisions__what" }, el("b", { text: a.proxy_flight }), ` · ${actionWords(a)}`, el("span", { class: "decisions__vol", text: ` · ${a.volcano_name}` })),
      right,
      a.status === "REJECTED" && a.reject_reason ? el("q", { class: "decisions__reason", text: a.reject_reason }) : null));
  }
  if (superseded.length) {
    list.append(el("li", { class: "decisions__item decisions__item--off" },
      el("span", { class: "decisions__status adv--off" }, icon("i-superseded"), el("span", { text: "Replaced by a newer draft" })),
      el("span", { class: "decisions__what", text: `${superseded.length} earlier draft${superseded.length === 1 ? "" : "s"}: ${[...new Set(superseded.map((a) => a.proxy_flight))].join(", ")}` }),
      el("span", { class: "decisions__who", text: "" })));
  }
  if (!all.length) list.append(el("li", { class: "empty", text: "No advisories yet. A draft appears when a flight's projected track enters TEPHRA's area." }));
  const head = secHead("h-dec", "Decisions", "Approve on the Desk · nothing is sent anywhere");
  if (replay) head.querySelector("h2").after(el("span", { class: "tag tag--replay", text: "recorded" }));
  return el("section", { class: "sec", "aria-labelledby": "h-dec", "data-ptab": "flights", id: "decisions" }, head, list);
}

// ------------------------------------------------------------------ level filter (8.4)

export function renderLevels(D, ui) {
  const box = $("levels");
  const H = window.innerWidth < 1600 ? (window.innerHeight < 1000 ? 190 : 220) : window.innerHeight < 1000 ? 240 : 270;
  const y = (ft) => (1 - levelFrac(ft)) * H;
  const track = el("div", { class: "levels__track", dataset: { act: "level-track" } });
  track.style.height = `${H}px`;
  track.append(el("div", { class: "levels__rail" }));
  const hc0 = D?.sit ? D.coneOf(D.sit.volcano_id)?.properties : null;
  const hazardOn0 = !!hc0 && ui.level.min === Math.max(0, hc0.base_ft) && ui.level.max === Math.min(LEVEL_MAX, hc0.top_ft);
  track.classList.toggle("levels__track--hazard", hazardOn0);
  if (D?.sit) {
    const offs = D.official.filter((f) => f.properties.volcano_id === D.sit.volcano_id && f.properties.valid && f.properties.step === "now");
    if (offs.length) {
      const b0 = Math.min(...offs.map((f) => f.properties.base_ft)), t0 = Math.max(...offs.map((f) => f.properties.top_ft));
      const bar = el("div", { class: "levels__band levels__band--official", title: `Official band ${band(b0, t0)}` });
      bar.style.top = `${y(t0)}px`; bar.style.height = `${Math.max(3, y(b0) - y(t0))}px`;
      track.append(bar);
    }
    const cone = D.coneOf(D.sit.volcano_id)?.properties;
    if (cone) {
      const bar = el("div", { class: "levels__band levels__band--tephra", title: `TEPHRA band ${band(cone.base_ft, cone.top_ft)}` });
      bar.style.top = `${y(cone.top_ft)}px`; bar.style.height = `${Math.max(3, y(cone.base_ft) - y(cone.top_ft))}px`;
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
    const s = el("span", { class: "levels__scale", title: fl(ft), "aria-hidden": "true" });
    s.style.top = `${y(ft)}px`;
    track.append(s);
  }
  const thumb = (which, ft, label) => {
    const t = el("div", { class: "levels__thumb", role: "slider", tabindex: "0", "aria-label": label, "aria-valuemin": "0", "aria-valuemax": String(LEVEL_MAX), "aria-valuenow": String(ft), "aria-valuetext": ft <= 0 ? "surface" : fl(ft), "aria-orientation": "vertical", "aria-keyshortcuts": "H", dataset: { thumb: which, focus: `thumb-${which}` }, text: fl(ft) });
    t.style.top = `${y(ft)}px`;
    return t;
  };
  track.append(thumb("max", ui.level.max, "Highest level shown"), thumb("min", ui.level.min, "Lowest level shown"));
  const readout = levelIsAll(ui.level) ? "All" : `${fl(ui.level.min)}–${fl(ui.level.max)}`;
  const hc = D?.sit ? D.coneOf(D.sit.volcano_id)?.properties : null;
  const hazardOn = !!hc && ui.level.min === Math.max(0, hc.base_ft) && ui.level.max === Math.min(LEVEL_MAX, hc.top_ft);
  box.replaceChildren(
    el("span", { class: "caps levels__title", id: "levels-title", text: "Levels" }),
    el("span", { class: "levels__readout", "aria-live": "polite", text: readout }),
    track,
    el("div", { class: "levels__presets", role: "group", "aria-label": "Level presets" },
      el("button", { type: "button", dataset: { act: "level-preset", preset: "all", focus: "lv-all" }, "aria-pressed": levelIsAll(ui.level) ? "true" : "false", text: "All" }),
      el("button", { type: "button", dataset: { act: "level-preset", preset: "hazard", focus: "lv-hazard" }, "aria-pressed": hazardOn ? "true" : "false", text: "Hazard" })));
  box.dataset.h = String(H);
}

// ------------------------------------------------------------------ timeline (8.3)

export function renderTimeline(D, store, ui, conn) {
  const box = $("timeline");
  if (!D) { box.replaceChildren(el("div", { class: "tl__meta" }, el("span", { class: "skeleton" }))); return; }
  const s = D.state, sit = D.sit;
  const t0 = D.now - 9 * 3600e3, t1 = D.now + 3 * 3600e3;
  const pct = (t) => `${(((t - t0) / (t1 - t0)) * 100).toFixed(3)}%`;
  box.classList.toggle("is-stale", !!conn.lostAt);
  const meta = el("div", { class: "tl__meta" });
  if (s.mode === "REPLAY" && s.replay) {
    const a = ms(s.replay.recorded_from), b = ms(s.replay.recorded_to);
    const p = Math.max(0, Math.min(1, (D.now - a) / (b - a)));
    const bar = el("span");
    bar.style.width = `${(p * 100).toFixed(1)}%`;
    meta.append(el("span", { class: "tl__mode" }, icon("i-replay"), "REPLAY"),
      el("span", { class: "tl__window", text: `${dayMon(a)} ${hhmmz(a)} → ${dayMon(b)} ${hhmmz(b)}` }),
      el("span", { class: "tl__progress", role: "progressbar", "aria-label": "Replay progress", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(Math.round(p * 100)) }, bar),
      el("span", { class: "tl__window tl__pct", text: `${Math.round(p * 100)}% through the recording` }),
      el("span", { class: "tl__phone", text: `REPLAY · ${dayMon(D.now)} ${hhmmz(D.now)} · ${Math.round(p * 100)}%` }));
  } else {
    meta.append(el("span", { class: "tl__mode tl__mode--live" }, icon("i-live"), "LIVE"), el("span", { class: "tl__window", text: "Last 9 h and next 3 h" }),
      el("span", { class: "tl__phone", text: `LIVE · ${dayMon(D.now)} ${hhmmz(D.now)}` }));
  }
  if (conn.lostAt) meta.append(el("span", { class: "tl__window tl__stale", text: `last update ${hhmmz(conn.lostAt)}` }));
  const labels = el("div", { class: "tl__labels", "aria-hidden": "true" }, el("span", { text: "Official" }), el("span", { text: "Observatory" }), el("span", { text: "TEPHRA" }));
  const track = el("div", { class: "tl__track", role: "group", "aria-label": `Timeline ${hhmmz(t0)} to ${hhmmz(t1)}. Arrow keys move between markers.` });
  const lane = (n) => { const l = el("div", { class: `tl__lane tl__lane--${n}` }); track.append(l); return l; };
  const offL = lane("official"), obsL = lane("observer"), tepL = lane("tephra");
  const marks = [];
  const mark = (laneEl, t, id, cls, title, act) => {
    if (!(t >= t0 && t <= t1)) return;
    const b = el("button", { type: "button", class: `tl__mark ${cls}`, title, "aria-label": title, tabindex: "-1", dataset: { act: "tl-mark", ...act, focus: `tl-${marks.length}` } }, icon(id, "st"));
    b.style.left = pct(t);
    laneEl.append(b);
    marks.push(b);
  };
  if (sit) {
    for (const card of sit.cards) {
      if (card.missing) continue;
      if (card.kind === "VONA") {
        for (const sid of [card.source_id, ...(card.extra_source_ids || [])]) {
          const t = idTime(sid);
          mark(obsL, t, sid === card.source_id ? "st-ok" : "st-off", "tl__mark--observer", `VONA ${dayMon(t)} ${hhmmz(t)}`, { kind: "VONA" });
        }
      } else {
        const vf = ms(card.valid_from), vt = ms(card.valid_to);
        if (Number.isFinite(vf) && Number.isFinite(vt) && vt > t0 && vf < t1) {
          const bar = el("div", { class: "tl__bar", "aria-hidden": "true" });
          bar.style.left = pct(Math.max(vf, t0));
          bar.style.width = `${((Math.min(vt, t1) - Math.max(vf, t0)) / (t1 - t0)) * 100}%`;
          offL.append(bar);
        }
        mark(offL, ms(card.issued_at), card.kind === "SIGMET" ? "st-stale" : "st-ok", "tl__mark--official", `${card.title} issued ${hhmmz(ms(card.issued_at))}`, { kind: card.kind });
      }
    }
    const lag = sit.discrepancies.find((d) => d.kind === "LAG");
    if (lag) {
      const times = Object.values(lag.values).map((v) => hhmmBefore(v, D.now)).filter(Number.isFinite);
      if (times.length >= 2) {
        const a = Math.max(t0, Math.min(...times)), b = Math.min(t1, Math.max(...times));
        if (b > a) {
          const g = el("div", { class: "tl__gap", "aria-hidden": "true" }, el("span", { text: `lag ${durMin(lag.magnitude)}` }));
          g.style.left = pct(a);
          g.style.width = `${((b - a) / (t1 - t0)) * 100}%`;
          track.append(g);
        }
      }
    }
    const seen = new Set();
    for (const t of store.trace) {
      if (t.volcano_id !== sit.volcano_id) continue;
      const k = `${t.stage}|${t.at.slice(0, 16)}`;
      if (seen.has(k)) continue;
      if (t.stage === "DISCREPANCY") { seen.add(k); mark(tepL, ms(t.at), "st-caution", "tl__mark--caution", `Disagreement found ${hhmmz(ms(t.at))}`, { kind: "dis" }); }
      if (t.stage === "EXPOSURE" && t.flight_id) { seen.add(k); mark(tepL, ms(t.at), "i-aircraft", "tl__mark--tephra", `Flight entering ${hhmmz(ms(t.at))}`, { kind: "flight" }); }
    }
    for (const a of store.advisories) {
      if (a.volcano_id !== sit.volcano_id || !a.decided_at) continue;
      const ok = a.status === "APPROVED" || a.status === "EDITED";
      mark(tepL, ms(a.decided_at), ok ? "i-approved" : "i-rejected", ok ? "tl__mark--ok" : "tl__mark--serious", `${a.proxy_flight} ${ok ? "approved" : "rejected"} by ${deciderName(a)} ${hhmmz(ms(a.decided_at))}`, { kind: "decision" });
    }
  }
  if (marks.length) marks[marks.length - 1].tabIndex = 0;
  // Hour ticks: every hour at 1600+, every second hour below; none within 36 px of NOW.
  const axis = el("div", { class: "tl__axis", "aria-hidden": "true" });
  const every = window.innerWidth < 1600 ? 2 : 1;
  const trackW = box.querySelector(".tl__track")?.clientWidth || Math.max(1, window.innerWidth - 1000);
  const nearNow = (t) => (Math.abs(t - D.now) / (t1 - t0)) * trackW < 36;
  for (let h = Math.ceil(t0 / 3600e3) * 3600e3; h <= t1; h += 3600e3) {
    const hr = new Date(h).getUTCHours();
    if (hr % every || nearNow(h)) continue;
    const sp = el("span", { class: "tl__hour", text: `${pad(hr)}Z` });
    sp.style.left = pct(h);
    axis.append(sp);
  }
  track.append(axis);
  const nowEl = el("div", { class: "tl__now", "aria-hidden": "true" }, el("span", { text: hhmmz(D.now) }));
  nowEl.style.left = pct(D.now);
  track.append(nowEl);
  const steps = el("div", { class: "tl__steps seg seg--small", role: "group", "aria-label": "Official forecast steps" },
    ...[["now", "Now"], ["f6", "+6 h"], ["f12", "+12 h"], ["f18", "+18 h"], ["all", "All"]].map(([k, label]) =>
      el("button", { type: "button", "aria-pressed": ui.steps === k ? "true" : "false", dataset: { act: "steps", steps: k, focus: `steps-${k}` }, text: label })));
  box.replaceChildren(meta, labels, track, el("div", { class: "tl__right" }, el("span", { class: "caps", text: "Forecast steps" }), steps));
}

// ------------------------------------------------------------------ dialogs

export function feedsDialog(D, store) {
  const rows = store.feeds.slice().sort((a, b) => (FEED_STATUS[a.status]?.[3] ?? 9) - (FEED_STATUS[b.status]?.[3] ?? 9));
  const now = D?.now ?? Date.now();
  const tbody = el("tbody");
  for (const f of rows) {
    const [id, color, word] = FEED_STATUS[f.status] || FEED_STATUS.NEVER;
    const last = ms(f.last_success_at);
    const statusWord = f.status === "DISABLED" && f.feed === "vona" ? "Off by policy" : word;
    let line;
    if (f.status === "OK") line = `updated ${age((now - last) / 1000)} ago`;
    else if (f.status === "STALE") line = `last good ${age((now - last) / 1000)} ago · showing the last good copy`;
    else if (f.status === "ERROR") line = `last good ${Number.isFinite(last) ? `${age((now - last) / 1000)} ago` : "never"}`;
    else line = "";
    tbody.append(el("tr", {},
      el("th", { scope: "row" }, FEED_NAME[f.feed] || f.feed, f.replay ? el("span", { class: "tag tag--replay", text: "recorded" }) : null),
      el("td", {}, el("span", { class: `status status--${f.status.toLowerCase()}` }, st(id, color), statusWord)),
      el("td", { class: "mono", text: Number.isFinite(last) ? age((now - last) / 1000) : "—" }),
      el("td", { class: "mono", text: Number.isFinite(last) ? `${dayMon(last)} ${hhmmz(last)}` : "never" }),
      el("td", { class: "mono", text: String(f.record_count ?? 0) }),
      el("td", { class: "feeds__note", text: [line, f.last_error].filter(Boolean).join(" · ") })));
  }
  return el("table", { class: "table" }, el("caption", { class: "sr-only", text: "Feed health" }),
    el("thead", {}, el("tr", {}, ...["Feed", "Status", "Age", "Last good (UTC)", "Records", "Note"].map((h) => el("th", { scope: "col", text: h })))), tbody);
}

// The operator policy (GET /api/policy): every margin, buffer and minimum the code applies,
// with its unit and why it has that value.
const POLICY_BLOCKS = [["exposure", "Exposure"], ["alternates", "Alternates"], ["planner", "Planner"], ["fuel", "Fuel"]];

export function policyDialog(data) {
  const p = data?.policy;
  if (!p) return el("p", { text: "The operator policy could not be loaded." });
  const cites = Object.fromEntries((p.citations || []).map((c) => [c.id, c]));
  const tbody = el("tbody");
  for (const [key, title] of POLICY_BLOCKS) {
    for (const [name, v] of Object.entries(p[key] || {})) {
      const refs = (v.citation_ids || []).map((id) => cites[id]?.ref).filter(Boolean);
      tbody.append(el("tr", {},
        el("th", { scope: "row", class: "mono", text: `${key}.${name}` }),
        el("td", { class: "mono", text: `${v.value} ${v.unit}` }),
        el("td", { text: [v.source, ...refs].join(" · ") }),
        el("td", { class: "muted", text: title })));
    }
  }
  const quotes = (p.citations || []).map((c) => {
    const url = safeExternalUrl(c.url);
    return el("li", {}, el("strong", { text: c.ref }), el("q", { text: c.text }),
      url ? el("a", { class: "link-btn", href: url, target: "_blank", rel: "noopener noreferrer" }, icon("i-external-link"), "Source") : null);
  });
  return el("div", { class: "policy" },
    el("p", {}, el("strong", { text: `${p.title} · v${p.version} · ${p.label}` })),
    el("p", { class: "muted", text: `Risk owner: ${p.risk_owner} · SRA: ${p.sra_ref || "none (illustrative)"} · content hash #${String(data.policy_hash || "").slice(0, 12)}` }),
    el("p", { text: p.summary_text }),
    el("h3", { text: "Values" }),
    el("table", { class: "table" }, el("caption", { class: "sr-only", text: "Operator policy values" }),
      el("thead", {}, el("tr", {}, ...["Name", "Value", "Why this value", "Block"].map((h) => el("th", { scope: "col", text: h })))), tbody),
    el("h3", { text: "Source-trust order" }),
    el("ol", {}, ...(p.source_order || []).map((r) => el("li", { text: r.text }))),
    el("h3", { text: "Citations" }),
    el("ul", { class: "policy__cites" }, ...quotes));
}

export function sourcesDialog(D, focusKind) {
  const sit = D?.sit;
  if (!sit) return el("p", { text: "No active volcano selected." });
  const byKind = Object.fromEntries(sit.cards.map((c) => [c.kind, c]));
  const cols = [byKind.SIGMET, byKind.VAA, byKind.VONA].filter(Boolean).map((c) => {
    const url = c.url ? safeExternalUrl(c.url) : null;
    const col = el("section", { class: `raw raw--${c.kind.toLowerCase()}`, "aria-label": c.title, dataset: { kind: c.kind } },
      el("h3", { class: "raw__title" }, el("span", { class: "cmp__kind", text: c.kind === "VONA" ? "VONA · observatory" : c.kind === "SIGMET" ? "SIGMET · binding" : "VAA · VAAC" }), el("span", { text: c.missing ? "None in force" : c.title })));
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

export function popupContent(kind, props, D, store) {
  const dl = el("dl", { class: "pop__facts" });
  const row = (k, v, mono) => { if (v == null || v === "") return; dl.append(el("dt", { text: k }), el("dd", { class: mono ? "mono" : null, text: String(v) })); };
  let title = "", sub = null, extra = null;
  if (kind === "official") {
    title = props.label;
    sub = props.kind === "SIGMET" ? "Official · binding" : "Official · VAAC";
    const vf = ms(props.valid_from), vt = ms(props.valid_to);
    row("Kind", props.kind); row("Layer", props.layer); row("Band", band(props.base_ft, props.top_ft), true);
    row("Valid", `${dayMon(vf)} ${hhmmz(vf)} – ${dayMon(vt)} ${hhmmz(vt)}`, true);
    if (vt > D.now) row("Ends in", durMin((vt - D.now) / 60e3));
    row("Source id", props.source_id, true);
    const k = props.kind === "SIGMET" ? "SIGMET" : "VAA";
    extra = el("button", { type: "button", class: "btn btn--small", dataset: { act: "raw", kind: k } }, icon("i-raw-text"), "Show raw text");
  } else if (kind === "area") {
    title = "TEPHRA cautious area";
    sub = "an estimate, not a forecast";
    row("Mode", props.mode); row("Confidence", `${Math.round((props.confidence ?? 0) * 100)}%`); row("Band", band(props.base_ft, props.top_ft), true);
    row("Label", props.label); row("Valid to", hhmmz(ms(props.valid_to)), true); row("Rule", "Never smaller than the official area");
  } else if (kind === "aircraft") {
    title = props.proxy_flight;
    sub = `proxy for ADS-B ${props.callsign || ""} (hex ${String(props.hex || "").toUpperCase()})`;
    row("Type", props.type_icao); row("Level", props.alt_baro_ft != null ? `${fl(props.alt_baro_ft)} (${props.alt_baro_ft} ft baro)` : "level unknown", true);
    if (props.nav_altitude_mcp_ft != null) row("Selected", fl(props.nav_altitude_mcp_ft), true);
    if (props.gs_kt != null) row("Ground speed", `${Math.round(props.gs_kt)} kt`, true);
    if (props.track_deg != null) row("Track", `${Math.round(props.track_deg)}° (${compassWord(props.track_deg)})`, true);
    row("Position age", age((D.now - ms(props.observed_at)) / 1000));
    if (props.exposed) row("TEPHRA area", props.minutes_to_entry === 0 ? "INSIDE NOW" : `enters in ${props.minutes_to_entry} min`);
    const adv = D.advByFlight.get(`${props.hex}:${props.volcano_id}`);
    if (adv) extra = advisoryLine(adv, D.mode === "REPLAY");
  } else if (kind === "volcano") {
    title = props.name;
    const sit = D.sits.find((s) => s.volcano_id === props.id);
    sub = props.active ? "Active" : "Catalogue volcano";
    dl.append(el("dt", { text: "Colour code" }), el("dd", {}, eruptIcon(props.color_code, "icon"), ` ${props.color_code} (${CODE_LETTER[props.color_code] || "U"})`));
    if (sit) row("Why active", sit.active_reasons.join(" · "));
    if (props.summit_elev_ft) row("Summit", `${props.summit_elev_ft.toLocaleString("en")} ft`, true);
    if (sit && sit.volcano_id !== D.selected) extra = el("button", { type: "button", class: "btn btn--small", dataset: { vid: sit.volcano_id, act: "select" } }, "Select this volcano");
  }
  return el("div", { class: "pop" }, el("p", { class: "pop__title", text: title }), sub ? el("p", { class: "pop__sub", text: sub }) : null, dl, extra);
}
