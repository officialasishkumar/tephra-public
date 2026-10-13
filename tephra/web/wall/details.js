// The Details drawer (docs/UI-REDESIGN.md R8): everything on the Wall that is not the story, one
// tap away. It opens on a plain index of four groups; every row shows its live count or failure
// in words. A section opens summary first; long tables sit behind "Show all" disclosures. The
// section builders are the Wall's existing ones (panels.js, ext.js), re-parented here.
// Placement by width: a pushing column at 1600 px and up, the story column's place from 601 to
// 1599 px, a full-screen sheet at 600 px and below. Feed text goes in with textContent (el()).

import { $, el, icon, ms, hhmmz, age, fl, compassWord } from "./util.js";
import { SEV_RANK, NON_OBS, actionWords, deciderName, officialLabelText, plainMove, levelIsAll, tephraLabelText, untilText, crewBand } from "./derive.js";
import {
  sourcesSection, disagreeSection, areaSection, decisionsSection, renderFlights, renderTrace, traceLines, renderLevels,
  historySection, feedsSection, lagOf, timelineEvents, advisoryLine, actionText, estimateOutcome, dayMonth, FEED_STATUS,
} from "./panels.js";
import { ext, renderXPanel, recoverySummary, proofTicks, rerouteBlock, replanning, aiState, handPlan } from "./ext.js";
import { renderLayers, layersStatus } from "./controls.js";
import { currentPlan, advisoryFacts, closuresFor } from "./story.js";
import { planFailure, techDetail, blockPhrase } from "./x-parts.js";
import { dkHeader, dkPill, dkChip, dkTiles, dkGroup, dkRow, dkList, dkFacts, dkNote, dkAbout, dkEmpty, dkSection, dkRecorded, dkDot } from "./dk.js";

// Section key, index group, title, host element id, the old rail panel id it stands for (R8.2).
export const SECTIONS = [
  { key: "sources", group: "The ash", title: "What the official reports say", host: "brief", xtab: "brief" },
  { key: "disagree", group: "The ash", title: "Where the sources disagree", host: "brief" },
  { key: "estimate", group: "The ash", title: "TEPHRA's estimate", host: "brief" },
  { key: "sat", group: "The ash", title: "Satellite picture", host: "xpanel", xtab: "sat" },
  { key: "notices", group: "The ash", title: "Notices", host: "xpanel", xtab: "notices" },
  { key: "crew", group: "The ash", title: "Crew reports of ash", host: "crew" },
  { key: "flights", group: "The flights", title: "Flights heading in", host: "flights" },
  { key: "decisions", group: "The flights", title: "Decisions", host: "decisions" },
  { key: "recovery", group: "The flights", title: "Airport closures", host: "xpanel", xtab: "recovery" },
  { key: "history", group: "Time and height", title: "Timeline history", host: "history" },
  { key: "levels", group: "Time and height", title: "Height filter", host: "levels" },
  { key: "trace", group: "Behind the scenes", title: "How TEPHRA decided", host: "trace" },
  { key: "ai", group: "Behind the scenes", title: "AI helpers", host: "xpanel", xtab: "ai" },
  { key: "proof", group: "Behind the scenes", title: "Track record", host: "xpanel", xtab: "proof" },
  { key: "feeds", group: "Behind the scenes", title: "Data feeds", host: "feeds" },
  { key: "layers", group: "Behind the scenes", title: "Map layers, 3D and compare", host: "layers-pop" },
  // reached from the map and from lists, not from the index
  { key: "area", title: "This ash area", host: "brief", hidden: true },
  { key: "flight", title: "This flight", host: "flights", hidden: true },
];
const HOSTS = ["brief", "xpanel", "flights", "decisions", "trace", "levels", "layers-pop", "feeds", "history", "crew"];
export const sectionOf = (key) => SECTIONS.find((s) => s.key === key) || null;
// the old rail panel ids (setRail, ui.rail) map to section keys
export const PANELS = [{ id: "brief", sec: "sources" }, ...SECTIONS.filter((s) => s.xtab && s.xtab !== "brief").map((s) => ({ id: s.xtab, sec: s.key }))];

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
// "newest SIGMET, VAA and VONA": the section shows one card per kind (the newest of each), so the
// row names the kinds, not a count that would read against the Desk's per-draft source list or the
// "reasons" list (review 2, item 3).
export function reportCount(cards) {
  const kinds = ["SIGMET", "VAA", "VONA"].filter((k) => cards.some((c) => c.kind === k));
  if (!kinds.length) return "none";
  return `newest ${kinds.length > 1 ? `${kinds.slice(0, -1).join(", ")} and ${kinds[kinds.length - 1]}` : kinds[0]}`;
}
const st = (id, color) => icon(id, "st", color);

// ------------------------------------------------------------------ the index (R8.2)

// The live status of one index row, in words. tone "serious" rows get the serious shape.
export function indexStatus(key, D, store, ui) {
  const sit = D?.sit;
  switch (key) {
    case "sources": {
      if (!sit) return { text: "no volcano selected" };
      // the same split as the section's summary: official reports (SIGMET, VAA) and the
      // observatory's notice (VONA) are counted apart (review 2, item 3)
      const cards = sit.cards.filter((c) => !c.missing);
      const newest = Math.max(...cards.map((c) => ms(c.issued_at)).filter(Number.isFinite));
      return { text: cards.length ? `${reportCount(cards)} · ${age((D.now - newest) / 1000)} ago` : "none in force" };
    }
    case "disagree": {
      if (!sit) return { text: "–" };
      const check = sit.discrepancies.filter((d) => d.severity !== "INFO");
      const minor = sit.discrepancies.length - check.length + sit.cards.filter((c) => !c.missing && NON_OBS.has(c.evidence)).length;
      const worst = Math.max(0, ...check.map((d) => SEV_RANK[d.severity] || 0));
      return { text: `${check.length ? `${check.length} to check` : "nothing to check"}${minor ? ` · ${minor} minor` : ""}`, tone: worst >= 3 ? "serious" : worst >= 2 ? "caution" : null };
    }
    case "estimate": {
      const cone = sit ? D.coneOf(sit.volcano_id)?.properties : null;
      if (!cone) return { text: "none yet" };
      return { text: tephraLabelText(cone, sit.assessment?.outcome, D.state.llm?.backend === "stub").replace("TEPHRA's estimate · ", "") };
    }
    case "sat": {
      const r = store.snapshot?.satellite || [];
      const bad = r.filter((x) => x.status === "ai_unavailable").length;
      const mine = r.find((x) => x.volcano_id === D?.selected && x.status === "read");
      // supporting only: a picture not read is information, never in "Needs a look" (D42)
      if (bad) return { text: `${plural(r.length, "reading", "readings")} · ${bad} not read`, tone: "info", noAttn: true };
      if (!r.length) return { text: "no reading yet" };
      return { text: `${plural(r.length, "reading", "readings")}${mine ? ` · ash visible? ${({ yes: "yes", no: "not seen" })[mine.ash_visible] || "can't tell"}` : ""}` };
    }
    case "notices":
      if (!ext.loaded.notices) return { text: "loading…" };
      if (ext.errors.notices) return { text: "could not load", tone: "serious" };
      return { text: ext.notices.length ? plural(ext.notices.length, "notice", "notices") : "none" };
    case "crew": {
      const C = D?.crew;
      if (!C || !C.reports.length) return { text: "none in the last 24 h" };
      const act = C.reports.filter((v) => v.state === "ACTIVE").length;
      const cov = C.reports.filter((v) => v.state === "COVERED").length;
      const out = C.reports.filter((v) => v.discrepancy).length;
      const parts = [act ? `${act} active` : null, cov ? `${cov} covered` : null, !act && !cov ? `${plural(C.reports.length, "report", "reports")}, none active` : null,
        C.flags.length ? `${plural(C.flags.length, "flight", "flights")} flagged` : null, out ? `${out} outside the official area` : null].filter(Boolean);
      return { text: parts.join(" · "), tone: out ? "caution" : null };
    }
    case "flights": {
      const list = sit ? D.exposed.filter((f) => f.properties.volcano_id === sit.volcano_id) : [];
      if (!list.length) return { text: "– · coverage is patchy" };
      const p = list[0].properties;
      return { text: `${list.length} · first is ${p.inside ? "inside now" : `in ${p.minutes_to_entry} min`}`, tone: "tephra" };
    }
    case "decisions": {
      if (D?.state.draft_count === null) return { text: "count unknown (database error)", tone: "serious" };
      const advs = store.advisories.filter((a) => a.status !== "SUPERSEDED");
      const w = advs.filter((a) => a.status === "DRAFT").length;
      const ok = advs.filter((a) => a.status === "APPROVED" || a.status === "EDITED").length;
      const hand = D ? handPlan(D, store).flights.length : 0;
      if (hand && !(D.state.draft_count ?? w)) return { text: `0 waiting · ${hand} to plan by hand`, tone: "caution" };
      return { text: `${D?.state.draft_count ?? w} waiting, all volcanoes · ${ok} approved` };
    }
    case "recovery": {
      if (!ext.loaded.recovery) return { text: "loading…" };
      if (ext.errors.recovery) return { text: "could not load", tone: "serious" };
      const plan = currentPlan();
      const re = replanning(store);
      if (re) return { text: `${plural(re.airports.length, "airport", "airports")} (all volcanoes) · re-planning…`, tone: "caution" };
      if (!plan) return { text: "no airport closed" };
      if (plan.status === "AI_UNAVAILABLE") return { text: planFailure(plan).short, tone: "caution" };
      // the same scope words as the story and the Desk: this volcano's, then every volcano's (G8)
      const n = new Set(plan.closures.map((c) => c.icao)).size;
      const mine = sit ? new Set(closuresFor(D, sit.volcano_id, plan).map((c) => c.icao)).size : 0;
      const scope = sit && mine !== n ? `${mine} from ${sit.volcano_name}, ${n} across all volcanoes` : `${plural(n, "airport", "airports")} (all volcanoes)`;
      return { text: `${scope} · plan ${plan.status === "DRAFT" ? "waiting" : plan.status.toLowerCase()}` };
    }
    case "history": {
      const lag = lagOf(sit);
      return { text: lag ? `lag ${age(lag.magnitude * 60)}` : D ? plural(timelineEvents(D, store).length, "event", "events") : "–" };
    }
    case "levels":
      return { text: levelIsAll(ui.level) ? "all heights" : `${fl(ui.level.min)}–${fl(ui.level.max)}`, tone: levelIsAll(ui.level) ? null : "caution" };
    case "trace":
      return { text: plural(traceLines(store, D, { traceScope: "all" }).length, "step", "steps") };
    case "ai": {
      // the one state, never red, and never in "Needs a look": the AI's state is not a
      // dispatcher's action; the hand work it leaves is (Decisions, Airport closures) (D39, D40)
      if (!D) return { text: "–" };
      const ai = aiState(D, store);
      const n = ai.trouble.length;
      if (ai.kind === "off") return { text: "Off · code only" };
      if (ai.kind === "paused") return { text: ai.until ? `Paused until ${ai.until}` : "Paused", tone: "caution", noAttn: true };
      if (ai.kind === "trouble") return { text: `On · ${n} problem${n === 1 ? "" : "s"}`, tone: "caution", noAttn: true };
      return { text: "On" };
    }
    case "proof": {
      if (!ext.loaded.backtest) return { text: "loading…" };
      if (ext.errors.backtest) return { text: "could not load", tone: "serious" };
      const n = proofTicks();
      return { text: n != null ? `backtest · ${n.toLocaleString("en")} moments` : "backtest" };
    }
    case "feeds": {
      const by = {};
      for (const f of store.feeds) by[f.status] = (by[f.status] || 0) + 1;
      const parts = [by.ERROR ? `${by.ERROR} error${by.ERROR === 1 ? "" : "s"}` : null, by.STALE ? `${by.STALE} stale` : null, `${by.OK || 0} working`, by.DISABLED ? `${by.DISABLED} off` : null].filter(Boolean);
      return { text: parts.join(" · "), tone: by.ERROR ? "serious" : by.STALE ? "caution" : null };
    }
    case "layers":
      return { text: layersStatus(ui) };
    default:
      return { text: "" };
  }
}

const INDEX_DOT = { serious: ["st-serious", "var(--c-serious)"], caution: ["st-caution", "var(--c-caution)"], tephra: ["st-inside", "var(--c-tephra)"], info: ["st-info", "var(--c-info)"] };

// One index row: a shape for its tone, the title over its live status, a chevron.
function indexRow(s, stt, { focus = `drow-${s.key}`, id = `xtab-${s.xtab || s.key}` } = {}) {
  const tone = stt.tone ? ` dindex__row--${stt.tone}` : "";
  const dot = INDEX_DOT[stt.tone];
  return el("button", { type: "button", class: `dindex__row${tone}`, id, dataset: { act: "details-sec", sec: s.key, xtab: id ? s.xtab || null : null, focus } },
    el("span", { class: "dindex__dot" }, dot ? st(dot[0], dot[1]) : null),
    el("span", { class: "dindex__text" }, el("span", { class: "dindex__label", text: s.title }), el("span", { class: "dindex__status", text: stt.text })),
    icon("i-chevron-right", "icon dindex__go"));
}

function renderIndex(D, store, ui) {
  const box = $("xtabs");
  const groups = [];
  const attention = [];
  for (const s of SECTIONS) {
    if (s.hidden) continue;
    let g = groups.find((x) => x.name === s.group);
    if (!g) { g = { name: s.group, rows: [] }; groups.push(g); }
    const stt = indexStatus(s.key, D, store, ui);
    g.rows.push([s, stt]);
    if ((stt.tone === "serious" || stt.tone === "caution") && !stt.noAttn) attention.push([s, stt]);
  }
  const kids = [];
  // "Needs a look": at most three rows whose status is serious or caution, serious first. The
  // same rows stay in their groups below; this card only points at them.
  if (attention.length) {
    const top = attention.sort((a, b) => (a[1].tone === "serious" ? 0 : 1) - (b[1].tone === "serious" ? 0 : 1)).slice(0, 3);
    kids.push(el("div", { role: "listitem", class: "dindex__attn" },
      el("h3", { class: "dindex__attnhead" }, st("st-caution", "var(--c-caution)"), el("span", { text: "Needs a look" })),
      el("div", { class: "dindex__card" }, ...top.map(([s, stt]) => indexRow(s, stt, { focus: `dattn-${s.key}`, id: null })))));
  }
  for (const g of groups) {
    kids.push(el("div", { role: "listitem", class: "dindex__group" }, el("h3", { class: "dindex__head", text: g.name })));
    kids.push(el("div", { role: "listitem", class: "dindex__card" }, ...g.rows.map(([s, stt]) => indexRow(s, stt))));
  }
  const key = kids.map((k) => k.textContent).join("|");
  if (box.dataset.key !== key) { box.dataset.key = key; box.replaceChildren(...kids); }
}

// ------------------------------------------------------------------ This ash area, This flight (R8.3)

const inWords = (dt) => (Number.isFinite(dt) && dt > 0 ? `in ${untilText(dt)}` : untilText(dt));

function areaDetail(D, store, vid) {
  const sit = D.sits.find((s) => s.volcano_id === vid);
  const host = $("brief");
  if (!sit) { host.replaceChildren(dkSection("area-d-head", dkHeader({ id: "area-d-head", title: "This ash area" }), dkEmpty("This volcano is no longer active.", null))); return; }
  const t = officialLabelText(D, vid);
  const kids = [dkHeader({ id: "area-d-head", pills: [t ? dkPill("ok", "Official area in force") : dkPill("caution", "No valid official area")], title: sit.volcano_name })];
  if (t) {
    const rawMove = (D.moveByVolcano[vid] || "").trim();
    const moves = /^NOT (STATED|GIVEN)$/i.test(rawMove) ? rawMove.toLowerCase() : plainMove(rawMove);
    // One entry per forecast step, at its own valid time: two reports with the same +6 h step are
    // one step on the map (review 2, item 7).
    const stepAt = new Map();
    for (const f of D.official.filter((x) => x.properties.volcano_id === vid && x.properties.step !== "now")) {
      const k = f.properties.layer.replace("FCST+", "+").replace("H", " h");
      const ft = ms(f.properties.valid_from);
      if (!stepAt.has(k) || ft < stepAt.get(k)) stepAt.set(k, ft);
    }
    const steps = [...stepAt].sort((a, b) => a[1] - b[1]);
    // Which reports, in words; their ids are under Technical detail.
    // One VAA can draw several layers (observed, estimated): it is counted once, by its number.
    const sigs = t.products.filter((x) => /^SIGMET\b/.test(x)).length;
    const vaas = new Set(t.products.filter((x) => /^VAA\b/.test(x)).map((x) => x.split(" ").slice(0, 3).join(" "))).size;
    kids.push(el("section", { class: "dk-card dk-card--official", "aria-labelledby": "area-off-h" },
      el("h3", { class: "dk-card__title dk-card__title--official", id: "area-off-h", text: "Official ash area · binding" }),
      dkTiles([
        { label: "Heights", value: `${fl(t.base)}–${fl(t.top)}` },
        { label: "Valid until", value: hhmmz(t.validTo), sub: inWords(t.validTo - D.now) },
      ], "Official area in numbers"),
      dkFacts([
        ["Movement", moves || "not given"],
        ["Drawn from", [sigs ? `${sigs} ${sigs === 1 ? "SIGMET (airspace warning)" : "SIGMETs (airspace warnings), the newest per office"}` : null, vaas ? `${vaas} ${vaas === 1 ? "VAA (ash advisory)" : "VAAs (ash advisories)"}` : null].filter(Boolean).join(" + ") || `${t.products.length} official reports`],
        ["Issued by", [...new Set(D.official.filter((f) => f.properties.volcano_id === vid && f.properties.valid).map((f) => issuerWords(f.properties)))].join(" · ")],
        ["Forecast steps", steps.length ? el("span", { class: "dk-chips" }, ...steps.map(([k, ft]) => dkChip(`${k} · ${hhmmz(ft)}`))) : "none in the current reports"],
      ]),
      el("div", { class: "dk-actions" }, ...["SIGMET", "VAA"].filter((k) => sit.cards.some((c) => c.kind === k && !c.missing)).map((k) => el("button", { type: "button", class: "btn btn--small", dataset: { act: "raw", kind: k } }, icon("i-raw-text"), `Raw text: ${k}`))),
      techDetail(...t.products)));
  } else {
    kids.push(dkNote("caution", "No official area is valid for this volcano right now."));
  }
  const cone = D.coneOf(vid)?.properties;
  if (cone) {
    kids.push(el("section", { class: "dk-card dk-card--tephra", "aria-labelledby": "area-tep-h" },
      el("h3", { class: "dk-card__title dk-card__title--tephra", id: "area-tep-h", text: "TEPHRA's estimate · an estimate, not a forecast" }),
      el("p", { class: "dk-card__line", text: estimateOutcome(D, sit, cone) }),
      dkTiles([
        { label: "Heights", value: `${fl(cone.base_ft)}–${fl(cone.top_ft)}` },
        { label: "Valid until", value: hhmmz(ms(cone.valid_to)), sub: inWords(ms(cone.valid_to) - D.now) },
      ], "Estimate in numbers"),
      el("div", { class: "dk-chips" }, dkChip("Never smaller than any valid official area", { kind: "tephra" })),
      techDetail(`mode ${cone.mode} · ${cone.label} · confidence ${Math.round((cone.confidence ?? 0) * 100)}%`)));
  }
  kids.push(el("p", {}, el("button", { type: "button", class: "link-btn", dataset: { act: "details-sec", sec: "sources", focus: "area-sources" }, text: "What the official reports say ›" })));
  host.replaceChildren(dkSection("area-d-head", kids));
}

// The office behind a report, in words with its code kept: "Jakarta airspace (WIIF)". A code
// not in this list keeps its code and says what kind of office it is; no name is guessed.
const FIR_NAME = {
  WIIF: "Jakarta", WAAF: "Makassar", YMMM: "Melbourne", YBBB: "Brisbane", RJJJ: "Fukuoka", RPHI: "Manila",
  WMFC: "Kuala Lumpur", WSJC: "Singapore", WBFC: "Kota Kinabalu", AYPM: "Port Moresby", NZZO: "Auckland",
  PAZA: "Anchorage", UHHH: "Khabarovsk", UHPP: "Petropavlovsk", RCAA: "Taipei", VTBB: "Bangkok", RKRR: "Incheon",
};
function issuerWords(p) {
  const code = String(p.source_id || "").split(":")[1] || "";
  if (p.kind === "SIGMET") return FIR_NAME[code] ? `${FIR_NAME[code]} airspace office (${code}), SIGMET` : `airspace office ${code}, SIGMET`;
  const vaac = code ? code.charAt(0) + code.slice(1).toLowerCase() : "";
  return `${vaac} ash advisory centre (VAAC), VAA`;
}

function flightDetail(D, ui, store) {
  const host = $("flights");
  const pick = ui.selFlight;
  if (!pick) { host.replaceChildren(dkSection("fl-head", dkHeader({ id: "fl-head", title: "This flight" }), dkEmpty("No flight is picked.", "Choose one on the map or in Flights heading in."))); return; }
  const f = D.selFlight;
  const clear = el("button", { type: "button", class: "link-btn fdetail__clear", "aria-label": "Clear the picked flight", dataset: { act: "flight-clear", focus: "flight-clear" }, text: "Clear" });
  if (!f) {
    host.replaceChildren(dkSection("fl-head", dkHeader({ id: "fl-head", pills: [dkRecorded(D.mode === "REPLAY")], title: pick.proxy, extra: clear }),
      D.selHiddenByLevel
        ? dkNote("info", `Hidden by the height filter ${fl(ui.level.min)}–${fl(ui.level.max)}.`, { action: el("button", { type: "button", class: "link-btn", dataset: { act: "level-reset", focus: "fdetail-reset" }, text: "Reset" }) })
        : dkEmpty("No current position for this flight in the aircraft data.", null)));
    return;
  }
  const p = f.properties;
  const entryPill = p.exposed ? (p.inside ? dkPill("inside", "Inside TEPHRA's area now") : dkPill("tephra", `Enters in ${p.minutes_to_entry} min (estimated)`)) : dkPill("ok", "Not projected to enter TEPHRA's area");
  const kids = [
    dkHeader({ id: "fl-head", pills: [entryPill, dkRecorded(D.mode === "REPLAY")], title: f.properties.proxy_flight, extra: clear }),
    dkNote("info", `RFA is a fictional airline. This flight stands in for ${p.callsign || "an aircraft with no callsign"}.`),
    dkTiles([
      { label: "Level", value: p.alt_baro_ft != null ? fl(p.alt_baro_ft) : "unknown", sub: p.alt_baro_ft != null ? `${Number(p.alt_baro_ft).toLocaleString("en")} ft${p.nav_altitude_mcp_ft != null ? ` · selected ${fl(p.nav_altitude_mcp_ft)}` : ""}` : null },
      { label: "Speed", value: p.gs_kt != null ? `${Math.round(p.gs_kt)} kt` : "unknown" },
      { label: "Track", value: p.track_deg != null ? `${Math.round(p.track_deg)}° ${compassWord(p.track_deg)}` : "unknown" },
      // The callsign's usual route from VRS standing data (code, never guessed): not the filed plan.
      { label: "Route", value: p.origin_icao && p.dest_icao ? `${p.origin_icao} → ${p.dest_icao}` : "Not known", sub: p.origin_icao && p.dest_icao ? "usual route, not the filed plan" : null },
    ], "This flight in numbers"),
    el("p", { class: "dk-foot", text: `Position ${age(p.ageS)} old.` }),
  ];
  const flag = D.crew.flagByHex.get(p.hex);
  if (flag) kids.push(crewFlagBlock(D, flag));
  const adv = p.exposed ? D.advByFlight.get(`${p.hex}:${p.volcano_id}`) : null;
  if (adv) {
    kids.push(el("section", { class: "dk-card", "aria-labelledby": "fl-adv-h" },
      el("p", { class: "dk-tile__label", id: "fl-adv-h", text: "Drafted action" }),
      el("p", { class: "dk-card__big", text: actionText(adv) }),
      el("p", {}, advisoryLine(adv, false)),
      adv.decision_reason ? el("p", { class: "dk-sub__note" }, "Reason given: ", el("q", { text: adv.decision_reason })) : null,
      techDetail(`action ${actionWords(adv)} · status ${adv.status}${adv.version != null ? ` · version ${adv.version}` : ""}`),
      el("div", { class: "dk-actions" }, el("a", { class: "btn btn--small", href: `/desk#review/${encodeURIComponent(adv.id)}`, target: "_blank", rel: "noopener", text: adv.status === "DRAFT" ? "Open on the Desk ›" : "See it on the Desk ›" }))));
  } else if (p.exposed) {
    // no advisory because the AI did not run: the job, here, once (D54)
    const hand = handPlan(D, store);
    const mine = hand.flights.find((x) => x.key === `${p.hex}:${p.volcano_id}`);
    if (mine) {
      const b = hand.block;
      kids.push(dkNote("caution", [el("p", {}, `No advisory for this flight: ${blockPhrase(b)}. `,
        el("a", { class: "link-btn", href: "/desk", target: "_blank", rel: "noopener", text: "Plan it by hand on the Desk ›" }),
        mine.must ? [" ", dkChip("Must do", { kind: "must", title: "Code requires this work this run" })] : null)], { role: "status" }));
    } else kids.push(dkEmpty("No advisory is drafted for this flight yet.", null));
  }
  const rr = (store_reroutes(D) || []).find((r) => r.properties.flight_id === `${p.hex}:${p.volcano_id}` || r.properties.proxy_flight === p.proxy_flight);
  if (rr) kids.push(rerouteBlock(rr.properties, D));
  kids.push(el("div", { class: "dk-abouts" }, dkAbout("How the entry is estimated", "flight", p.exposed ? "Code projection from the last position, if track, speed and level are held." : "Code projects the last position along its track, speed and level; this flight does not reach TEPHRA's area."),
    dkAbout("Where the route comes from", "flight-route", "The usual route for this callsign, from VRS standing data. It is not the filed flight plan, and TEPHRA never guesses one.")),
    techDetail(`ADS-B ${p.callsign || "(no callsign)"} · hex ${String(p.hex || "").toUpperCase()}${p.type_icao ? ` · type ${p.type_icao}` : ""}`));
  host.replaceChildren(dkSection("fl-head", kids));
}
let store_reroutes = () => [];

// ------------------------------------------------------------------ Crew reports of ash (7.20)

const CUE_WORDS = { ASH_SEEN: "ash seen", SULPHUR_SMELL: "sulphur smell", HAZE: "haze or dust in the cabin", ST_ELMOS_FIRE: "St Elmo's fire", ENGINE: "engine signs", NO_ASH_SEEN: "no ash seen" };
const CREW_STATE_SHAPE = { ACTIVE: ["i-pin", "var(--c-crew-text)"], COVERED: ["st-info", "var(--c-info)"], EXPIRED: ["st-off", "var(--c-off)"], WITHDRAWN: ["st-off", "var(--c-off)"], NO_AREA: ["st-info", "var(--c-info)"] };
const latLon = (r) => `${Math.abs(r.lat).toFixed(2)}${r.lat >= 0 ? "N" : "S"} ${Math.abs(r.lon).toFixed(2)}${r.lon >= 0 ? "E" : "W"}`;
const whenFlag = (f) => (f.inside_now ? "is inside the crew report area now" : `enters the crew report area in ${f.minutes_to_entry} min if track and level are held`);

// "Crew report of ash on this route" in This flight (7.8): which report, and when the projected
// track meets its area. A flag only: nothing is re-planned because of it.
function crewFlagBlock(D, flag) {
  const views = flag.report_ids.map((id) => D.crew.byId.get(id)).filter(Boolean);
  return dkNote("crew", [
    el("p", {}, el("strong", { text: flag.line })),
    flag.reporter ? null : el("p", { text: `${flag.proxy_flight} ${whenFlag(flag)}.` }),
    ...views.map((v) => el("p", { text: `${v.report.flight} reported ${v.report.cues.map((c) => CUE_WORDS[c] || c).join(", ")} at ${crewBand(v.report)}, ${v.age_text} · ${v.state_label}` })),
    el("p", { class: "dk-sub__note", text: "Operator policy A caution area; not a VAA or SIGMET. Approving Keep watching or Continue for this flight needs a written reason on the Desk." }),
  ].filter(Boolean), { iconId: "i-pin", action: el("button", { type: "button", class: "link-btn", dataset: { act: "details-open", sec: "crew", focus: `flag-crew-${flag.hex}` }, text: "Crew reports of ash ›" }) });
}

const CREW_TONE = { ACTIVE: "caution", COVERED: "info", EXPIRED: "off", WITHDRAWN: "off", NO_AREA: "info" };
function crewRow(D, v, picked) {
  const r = v.report;
  const a = r.area;
  const [shape, colour] = CREW_STATE_SHAPE[v.state] || CREW_STATE_SHAPE.NO_AREA;
  // the flights it flags, from the report's own view (v.flagged), named from the picture's flags
  const flagged = (v.flagged || []).map((hex) => D.crew.flagByHex.get(hex)).filter(Boolean);
  const drawn = v.state === "ACTIVE" || v.state === "COVERED";
  const ended = v.state === "WITHDRAWN"
    ? `Withdrawn by ${String(r.withdrawn_by || "").replace(/^desk:/, "")} at ${hhmmz(ms(r.withdrawn_at))}: ${r.withdraw_reason || "no reason recorded"}. It no longer flags any flight.`
    : v.state === "EXPIRED" ? "Expired: it no longer flags any flight." : null;
  const reported = dkFacts([
    ["Crew reported", r.cues.map((c) => CUE_WORDS[c] || c).join(", ")],
    ["At", `${crewBand(r)} · observed ${hhmmz(ms(r.observed_at))}`],
    ["Position", `${latLon(r)} · ${r.position_basis === "ADSB_FIX" ? `ADS-B fix at ${hhmmz(ms(r.position_observed_at))}` : "typed by dispatcher"}`],
    ["Near", v.place_text],
    ["Entered", `${String(r.entered_by || "").replace(/^desk:/, "")} at ${hhmmz(ms(r.created_at))} on the Desk`],
    ["Remarks", r.remarks ? el("q", { text: r.remarks }) : null],
  ]);
  const area = a ? dkFacts([
    ["Caution area", `${a.radius_nm} NM around the position · ${fl(a.base_ft)}–${fl(a.top_ft)}`],
    ["Wind stretch", a.stretch_note],
    ["Valid", `${hhmmz(ms(a.valid_from))} to ${hhmmz(ms(a.valid_to))}${drawn ? ` (${untilText(ms(a.valid_to) - D.now)} left)` : ""}`],
    ["Covered by", v.state === "COVERED" ? `${plural(v.covered_by.length, "official area", "official areas")} (display only: the area and its flags stay)` : null],
    ["Flights flagged", drawn ? (flagged.length ? el("span", { class: "dk-chips" }, ...flagged.map((f) => el("button", { type: "button", class: "dk-chip dk-chip--btn", dataset: { flight: f.hex, focus: `crew-flight-${r.id}-${f.hex}` }, text: `${f.proxy_flight} · ${f.reporter ? "the reporting flight" : f.inside_now ? "inside now" : `in ${f.minutes_to_entry} min`}` }))) : "none seen crossing it") : null],
  ]) : null;
  return dkRow({
    key: `crew-${r.id}`, open: picked, dot: icon(shape, "st", colour), edge: v.discrepancy ? "caution" : drawn ? "crew" : null, cls: drawn ? null : "dk-row--muted",
    title: [el("span", { id: `crew-${r.id}`, text: r.flight }), r.replay ? [" ", el("span", { class: "tag tag--replay", text: "entered in REPLAY" })] : null],
    sub: [r.cues.map((c) => CUE_WORDS[c] || c).join(", "), ` · ${crewBand(r)}`, v.place_text ? ` · ${v.place_text}` : ""],
    foot: [el("span", { class: `dk-crewstate dk-crewstate--${CREW_TONE[v.state] || "info"}`, text: v.state_label }), el("span", { text: v.age_text }), flagged.length && drawn ? el("span", { text: `${plural(flagged.length, "flight", "flights")} flagged` }) : null],
    body: [
      v.discrepancy ? dkNote("caution", `${v.discrepancy}. ${v.outside_detail || ""} A dispatcher can start a message to the weather office and the VAAC on the Desk.`.replace(/\s+/g, " ")) : null,
      ended ? dkNote("info", ended) : null,
      el("div", { class: "dk-sub" }, el("p", { class: "dk-sub__title", text: "What was reported" }), reported),
      area ? el("div", { class: "dk-sub" }, el("p", { class: "dk-sub__title", text: "Caution area" }), area) : null,
      el("div", { class: "dk-actions" },
        drawn ? el("button", { type: "button", class: "btn btn--small", dataset: { act: "crew-show", report: r.id, focus: `crew-show-${r.id}` } }, icon("i-frame"), "Show on the map") : null,
        el("a", { class: "btn btn--small", href: `/desk#crew/${encodeURIComponent(r.id)}`, target: "_blank", rel: "noopener" }, "Open on the Desk ›")),
      techDetail(`report ${r.id}`, r.position_source_id ? `position ${r.position_source_id}` : null, a?.wind_source_id ? `wind ${a.wind_source_id}` : null,
        v.covered_by.length ? `covered by ${v.covered_by.join(", ")}` : null, `policy ${r.policy_id} v${r.policy_version} #${r.policy_hash}`, r.replay_case_id ? `replay case ${r.replay_case_id}` : null),
    ],
  });
}

function crewSection(D, ui) {
  const C = D.crew;
  const host = $("crew");
  const label = C.label || "Crew report caution area (operator policy A; not a VAA or SIGMET)";
  const about = el("div", { class: "dk-abouts" }, dkAbout("How crew reports work", "crew",
    `${label}.`, "A dispatcher enters a crew (pilot) report on the Desk; code draws a caution area around the reported position over the reported levels. It flags flights whose projected track crosses it.",
    "It never shrinks or replaces an official area, re-plans nothing and calls no model. A sulphur smell or haze alone is a routine report with no area; a no-ash report never removes one."));
  const report = el("div", { class: "dk-actions" }, el("a", { class: "btn btn--small", href: "/desk#crew-report", target: "_blank", rel: "noopener", text: "Report ash from a crew on the Desk ›" }));
  const chip = dkChip("Operator policy A · not a VAA or SIGMET", { kind: "crew" });
  const title = "A dispatcher enters a crew report on the Desk; code draws a caution area and flags flights that cross it.";
  if (!C.reports.length) {
    host.replaceChildren(dkSection("crew-head", dkHeader({ id: "crew-head", pills: [dkPill("ok", "None in the last 24 h")], title, chips: [chip] }),
      dkEmpty("No crew report of ash in the last 24 hours.", null), report, about));
    return;
  }
  const act = C.reports.filter((v) => v.state === "ACTIVE" || v.state === "COVERED").length;
  const out = C.reports.filter((v) => v.discrepancy).length;
  host.replaceChildren(dkSection("crew-head",
    dkHeader({ id: "crew-head", pills: [act ? dkPill("caution", `${act} with a caution area now`) : dkPill("off", "None active"), dkRecorded(D.mode === "REPLAY")], title, chips: [chip] }),
    dkTiles([
      { label: "Reports (24 h)", value: String(C.reports.length) },
      { label: "Caution area now", value: String(act), tone: act ? "caution" : null },
      { label: "Flights flagged", value: String(C.flags.length) },
      out ? { label: "Outside official area", value: String(out), tone: "caution" } : null,
    ], "Crew reports in numbers"),
    dkList(C.reports.map((v) => crewRow(D, v, ui.details.vid === v.report.id)), { first: 4, key: "crew" }),
    report, about));
}

// ------------------------------------------------------------------ rendering

function keepOpenDetails(host, fn) {
  const open = new Set();
  const counts = new Map();
  const keyOf = (d) => {
    if (d.dataset.k) return d.dataset.k;
    const s = d.querySelector(":scope > summary")?.textContent || "";
    const n = (counts.get(s) || 0) + 1;
    counts.set(s, n);
    return `${s}#${n}`;
  };
  for (const d of host.querySelectorAll("details")) if (d.open) open.add(keyOf(d));
  counts.clear();
  fn();
  if (!open.size) return;
  for (const d of host.querySelectorAll("details")) if (open.has(keyOf(d))) d.open = true;
}

function renderSection(key, D, store, ui, conn) {
  const sit = D?.sit;
  const none = (host) => $(host).replaceChildren(el("p", { class: "dsum", text: D?.reading ? "Reading the official reports… The sections fill in when TEPHRA has read them." : D?.regionEmpty ? "No volcano is active in this area. Choose another area or volcano." : "No volcano is selected." }));
  switch (key) {
    case "sources": if (!sit) return none("brief"); $("brief").replaceChildren(sourcesSection(D, sit)); return;
    case "disagree": if (!sit) return none("brief"); $("brief").replaceChildren(disagreeSection(D, sit, ui)); return;
    case "estimate": if (!sit) return none("brief"); $("brief").replaceChildren(areaSection(D, sit, ui)); return;
    case "area": areaDetail(D, store, ui.details.vid || D.selected); return;
    case "sat": case "notices": case "recovery": case "proof": case "ai": renderXPanel(key, D, store); return;
    case "flights": renderFlights(D, store, ui); return;
    case "crew": crewSection(D, ui); return;
    case "flight": flightDetail(D, ui, store); return;
    case "decisions": decisionsSection(D, store, ui); return;
    case "history": historySection(D, store, ui); return;
    case "levels": renderLevels(D, ui); return;
    case "trace": renderTrace(D, store, ui, conn); return;
    case "feeds": feedsSection(D, store); return;
    case "layers": renderLayers(ui, window.innerWidth <= 600); return;
    default:
  }
}

function renderStrip(D, store) {
  const box = $("story-strip");
  if (!D) { box.replaceChildren(); return; }
  const sit = D.sit;
  const parts = [];
  if (sit) {
    const n = sit.exposed_count || 0;
    const a = advisoryFacts(D, store, sit.volcano_id);
    parts.push(sit.volcano_name, n ? plural(n, "flight", "flights") : "no flights seen", `${a.partial ? "at least " : ""}${a.drafts} waiting`);
  } else parts.push(D.area?.name || "No volcano selected");
  const key = parts.join("|");
  if (box.dataset.key === key) return;
  box.dataset.key = key;
  box.replaceChildren(
    el("button", { type: "button", class: "link-btn story-strip__back", dataset: { act: "details-close", focus: "strip-back" }, text: "‹ Story" }),
    el("span", { class: "story-strip__text", text: parts.join(" · ") }),
    el("a", { class: "desk-link desk-link--small", href: "/desk", target: "_blank", rel: "noopener", text: "Desk →" }));
}

function renderSwitcher(D, ui) {
  const sel = $("details-volcano");
  if (!D) return;
  const key = D.sits.map((s) => s.volcano_id).join("|");
  if (sel.dataset.key !== key) {
    sel.dataset.key = key;
    sel.replaceChildren(...D.sits.map((s) => el("option", { value: s.volcano_id, text: s.volcano_name })));
  }
  // Crew reports are listed for every volcano and for none: the volcano picker does nothing there.
  sel.hidden = !D.sits.length || ui.details.sec === "crew";
  if (D.selected) sel.value = D.selected;
}

export function renderDetails(D, store, ui, conn, extras = {}) {
  if (extras.reroutes) store_reroutes = extras.reroutes;
  const box = $("details");
  const open = ui.details.open;
  box.hidden = !open;
  $("details-btn").setAttribute("aria-expanded", open ? "true" : "false");
  if (!open) return;
  const sec = ui.details.sec ? sectionOf(ui.details.sec) : null;
  $("details-back").hidden = !sec;
  const title = $("details-title");
  const t = sec ? sec.title : "Details";
  if (title.textContent !== t) title.textContent = t;
  renderSwitcher(D, ui);
  renderStrip(D, store);
  $("xtabs").hidden = !!sec;
  if (!sec) renderIndex(D, store, ui);
  for (const h of HOSTS) {
    const node = $(h);
    const on = !!sec && sec.host === h;
    node.hidden = !on;
    if (on && D) keepOpenDetails(node, () => renderSection(sec.key, D, store, ui, conn));
  }
  document.body.dataset.rail = sec?.xtab || (sec ? sec.key : "index");
}
