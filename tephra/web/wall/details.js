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
  historySection, feedsSection, lagOf, timelineEvents, actionText, estimateOutcome, dayMonth, FEED_STATUS,
} from "./panels.js";
import { ext, renderXPanel, recoverySummary, proofTicks, rerouteBlock, replanning, aiState, handPlan, runsStatus } from "./ext.js";
import { has } from "./features.js";
import { renderLayers, layersStatus } from "./controls.js";
import { currentPlan, advisoryFacts, closuresFor } from "./story.js";
import { planFailure, techDetail, blockPhrase, whyLink, aircraftNoun } from "./x-parts.js";
import {
  dkHeader, dkPill, dkChip, dkTiles, dkGroup, dkRow, dkList, dkFacts, dkNote, dkEmpty, dkSection, dkDot, dkFromReplay,
  dkGlance, dkBand, dkMove, dkArrow, dkFact, dkLevelMark, dkCountdown, dkSources, dkSteps, dkLabel, dkFoot, dkQuiet,
} from "./dk.js";
import { chainSection } from "./chain.js";

// Section key, index group, title, host element id, the old rail panel id it stands for (R8.2),
// and the optional feature (wall/features.js) the section is listed under.
export const SECTIONS = [
  { key: "sources", group: "The ash", title: "What the official reports say", host: "brief", xtab: "brief" },
  { key: "disagree", group: "The ash", title: "Where the sources disagree", host: "brief" },
  { key: "estimate", group: "The ash", title: "TEPHRA's estimate", host: "brief" },
  { key: "sat", group: "The ash", title: "Satellite picture", host: "xpanel", xtab: "sat", feature: "satellite" },
  { key: "notices", group: "The ash", title: "Notices", host: "xpanel", xtab: "notices", feature: "notices" },
  { key: "crew", group: "The ash", title: "Crew reports of ash", host: "crew", feature: "crew" },
  { key: "flights", group: "The flights", title: "Flights heading in", host: "flights" },
  { key: "decisions", group: "The flights", title: "Decisions", host: "decisions" },
  { key: "recovery", group: "The flights", title: "Airport closures", host: "xpanel", xtab: "recovery" },
  { key: "history", group: "Time and height", title: "Timeline history", host: "history" },
  { key: "levels", group: "Time and height", title: "Height filter", host: "levels" },
  { key: "trace", group: "Behind the scenes", title: "How TEPHRA decided", host: "trace" },
  { key: "ai", group: "Behind the scenes", title: "TEPHRA Assistant", host: "xpanel", xtab: "ai" },
  { key: "proof", group: "Behind the scenes", title: "Track record", host: "xpanel", xtab: "proof" },
  { key: "runs", group: "Behind the scenes", title: "Runs on", host: "xpanel", xtab: "runs" },
  { key: "feeds", group: "Behind the scenes", title: "Data feeds", host: "feeds" },
  { key: "layers", group: "Behind the scenes", title: "Map layers, 3D and compare", host: "layers-pop" },
  // reached from the map and from lists, not from the index
  { key: "area", title: "This ash area", host: "brief", hidden: true },
  { key: "flight", title: "This flight", host: "flights", hidden: true },
  // "Why ›" on a Decisions row (act=chain): the advisory's reasoning chain, in the flight host
  { key: "chain", title: "Why this advice", host: "flights", hidden: true },
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
      // the story's one count set (derive.js D.counts) when it is there, so the hero and this row agree
      return { text: `${D.counts ? D.counts.exposed : list.length} · first is ${p.inside ? "inside now" : `in ${p.minutes_to_entry} min`}`, tone: "tephra" };
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
      // the one state, never red, and never in "Needs a look": the assistant's state is not a
      // dispatcher's action; the hand work it leaves is (Decisions, Airport closures) (D39, D40)
      if (!D) return { text: "–" };
      const ai = aiState(D, store);
      const n = ai.trouble.length;
      if (ai.kind === "off") return { text: "Off · code only" };
      // the state word only; why and until when are in the section it opens (8.6)
      if (ai.kind === "paused") return { text: "Paused", tone: "caution", noAttn: true };
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
    case "runs":
      return { text: runsStatus(store.state) };
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
    if (s.hidden || (s.feature && !has(s.feature))) continue;
    let g = groups.find((x) => x.name === s.group);
    if (!g) { g = { name: s.group, rows: [] }; groups.push(g); }
    const stt = indexStatus(s.key, D, store, ui);
    g.rows.push([s, stt]);
    if ((stt.tone === "serious" || stt.tone === "caution") && !stt.noAttn) attention.push([s, stt]);
  }
  const kids = [];
  // "Needs a look": at most three rows whose status is serious or caution, serious first. A row
  // listed there is said once: its group below leaves it out.
  const lifted = new Set();
  if (attention.length) {
    const top = attention.sort((a, b) => (a[1].tone === "serious" ? 0 : 1) - (b[1].tone === "serious" ? 0 : 1)).slice(0, 3);
    for (const [s] of top) lifted.add(s.key);
    kids.push(el("div", { role: "listitem", class: "dindex__attn" },
      el("h3", { class: "dindex__attnhead" }, st("st-caution", "var(--c-caution)"), el("span", { text: "Needs a look" })),
      el("div", { class: "dindex__card" }, ...top.map(([s, stt]) => indexRow(s, stt, { focus: `dattn-${s.key}` })))));
  }
  for (const g of groups) {
    const rows = g.rows.filter(([s]) => !lifted.has(s.key));
    if (!rows.length) continue;
    kids.push(el("div", { role: "listitem", class: "dindex__group" }, el("h3", { class: "dindex__head", text: g.name })));
    kids.push(el("div", { role: "listitem", class: "dindex__card" }, ...rows.map(([s, stt]) => indexRow(s, stt))));
  }
  const key = kids.map((k) => k.textContent).join("|");
  if (box.dataset.key !== key) { box.dataset.key = key; box.replaceChildren(...kids); }
}

// ------------------------------------------------------------------ This ash area, This flight (R8.3)


function areaDetail(D, store, vid) {
  const sit = D.sits.find((s) => s.volcano_id === vid);
  const host = $("brief");
  if (!sit) { host.replaceChildren(dkSection("area-d-head", dkHeader({ id: "area-d-head", title: "This ash area" }), dkEmpty("This volcano is no longer active.", null))); return; }
  const t = officialLabelText(D, vid);
  // the official card says the area is in force; the pill is kept only for its absence
  const kids = [dkHeader({ id: "area-d-head", pills: [t ? null : dkPill("caution", "No valid official area")], title: sit.volcano_name })];
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
    // The reports it is drawn from, one chip each: the newest SIGMET per office, and a VAA once by
    // its number however many layers it draws (review 2). The office's name is the chip's title.
    const chips = [...new Set(t.products.map((x) => x.split(" ").slice(0, 3).join(" ")))].map(productChip);
    kids.push(dkGlance({
      tone: "official", labelId: "area-off-h", label: "Official ash area · binding", until: dkCountdown(t.validTo, D.now),
      facts: [dkBand(t.base, t.top, "official"), dkMove(moves)],
      kids: [
        dkLabel("Drawn from"), dkSources(chips, "Drawn from these official reports"),
        dkLabel("Forecast"), steps.length ? dkSteps(steps) : el("p", { class: "gl-none", text: "No forecast steps in the current reports" }),
        dkFoot(...["SIGMET", "VAA"].filter((k) => sit.cards.some((c) => c.kind === k && !c.missing)).map((k) => dkQuiet(`${k} text`, { act: "raw", kind: k }, { label: `Raw text: ${k}` })),
          dkQuiet("All reports ›",{ act: "details-sec", sec: "sources", focus: "area-sources" }, { iconId: null }), techDetail(...t.products)),
      ],
    }));
  } else {
    kids.push(dkNote("caution", "No official area is valid for this volcano right now.", { action: el("button", { type: "button", class: "link-btn", dataset: { act: "details-sec", sec: "sources", focus: "area-sources" }, text: "What the official reports say ›" }) }));
  }
  const cone = D.coneOf(vid)?.properties;
  if (cone) {
    kids.push(dkGlance({
      tone: "tephra", labelId: "area-tep-h", label: "TEPHRA's estimate · not a forecast", until: dkCountdown(ms(cone.valid_to), D.now),
      lead: estimateOutcome(D, sit, cone),
      facts: [dkBand(cone.base_ft, cone.top_ft, "tephra"), el("p", { class: "gl-rule" }, icon("i-check", "icon"), "Never smaller than any valid official area")],
      kids: [dkFoot(techDetail(`mode ${cone.mode} · ${cone.label} · confidence ${Math.round((cone.confidence ?? 0) * 100)}%`))],
    }));
  }
  host.replaceChildren(dkSection("area-d-head", kids));
}

// "SIGMET WAAF 06" -> a chip "WAAF 06 · SIGMET" titled "Makassar airspace office (WAAF), SIGMET".
function productChip(label) {
  const [kind, code = "", nr = ""] = label.split(" ");
  const full = issuerWords({ kind, source_id: `${kind}:${code}` });
  return { code: kind === "SIGMET" ? `${code} ${nr}`.trim() : `${code.charAt(0)}${code.slice(1).toLowerCase()} ${nr}`.trim(), kind, full, tone: "official" };
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

// An advisory's state as a badge: a word and a shape, never red (a rejection is a decision, not an alarm).
function advState(a) {
  const by = `${deciderName(a)}${a.decided_at ? ` · ${hhmmz(ms(a.decided_at))}` : ""}`;
  return {
    DRAFT: ["Waiting for a dispatcher", "info", "i-clock"],
    APPROVED: [`Approved by ${by}`, "ok", "i-approved"],
    EDITED: [`Approved with edits by ${by}`, "ok", "i-approved"],
    REJECTED: [`Rejected by ${by}`, "muted", "i-rejected"],
    SUPERSEDED: ["Replaced by a newer draft", "muted", "i-superseded"],
  }[a.status] || ["Waiting for a dispatcher", "info", "i-clock"];
}

function flightDetail(D, ui, store) {
  const host = $("flights");
  const pick = ui.selFlight;
  if (!pick) { host.replaceChildren(dkSection("fl-head", dkHeader({ id: "fl-head", title: "This flight" }), dkEmpty("No flight is picked.", "Choose one on the map or in Flights heading in."))); return; }
  const f = D.selFlight;
  const clear = el("button", { type: "button", class: "link-btn fdetail__clear", "aria-label": "Clear the picked flight", dataset: { act: "flight-clear", focus: "flight-clear" }, text: "Clear" });
  if (!f) {
    host.replaceChildren(dkSection("fl-head", dkHeader({ id: "fl-head", title: pick.proxy, extra: clear }),
      D.selHiddenByLevel
        ? dkNote("info", `Hidden by the height filter ${fl(ui.level.min)}–${fl(ui.level.max)}.`, { action: el("button", { type: "button", class: "link-btn", dataset: { act: "level-reset", focus: "fdetail-reset" }, text: "Reset" }) })
        : dkEmpty("No current position for this flight in the aircraft data.", null)));
    return;
  }
  const p = f.properties;
  const entryPill = p.exposed ? (p.inside ? dkPill("inside", "Inside TEPHRA's area now") : dkPill("tephra", `Enters in ${p.minutes_to_entry} min (estimated)`)) : dkPill("ok", "Not projected to enter TEPHRA's area");
  // Glance first: the flight and where it stands against the ash, then four facts with a shape each.
  const route = p.origin_icao && p.dest_icao;
  const kids = [
    el("header", { class: "fl-id" },
      el("div", { class: "fl-id__row" }, el("h3", { class: "fl-id__name mono", id: "fl-head", text: p.proxy_flight }), entryPill),
      el("div", { class: "fl-id__sub" }, el("span", {}, `${aircraftNoun(D.state).replace(/^./, (c) => c.toUpperCase())} ${p.callsign || "with no callsign"} · `,
        el("span", { class: p.stale ? "dk-warn" : null, text: `position ${age(p.ageS)} old` })), clear)),
    el("div", { class: "gl-facts gl-facts--flight", role: "group", "aria-label": "This flight in numbers" },
      dkFact({ value: p.alt_baro_ft != null ? fl(p.alt_baro_ft) : "unknown", label: "Level", lead: p.alt_baro_ft != null ? dkLevelMark(p.alt_baro_ft, p.exposed ? "tephra" : "aircraft") : null,
        sub: p.alt_baro_ft != null ? `${Number(p.alt_baro_ft).toLocaleString("en")} ft${p.nav_altitude_mcp_ft != null ? ` · selected ${fl(p.nav_altitude_mcp_ft)}` : ""}` : null }),
      dkFact({ value: p.track_deg != null ? compassWord(p.track_deg) : "unknown", label: p.track_deg != null ? `Track · ${Math.round(p.track_deg)}°` : "Track", lead: p.track_deg != null ? dkArrow(p.track_deg) : null }),
      dkFact({ value: p.gs_kt != null ? `${Math.round(p.gs_kt)} kt` : "unknown", label: "Speed" }),
      // The callsign's usual route from VRS standing data (code, never guessed): not the filed plan.
      dkFact({ value: route ? `${p.origin_icao} → ${p.dest_icao}` : "Not known", label: route ? (p.route_source === "PLAN" ? `The airline's flight plan${p.flight_plan ? ` (${p.flight_plan})` : ""}` : "Usual route, not the filed plan") : "Route", size: "mid" })),
  ];
  const flag = D.crew.flagByHex.get(p.hex);
  if (flag) kids.push(crewFlagBlock(D, flag));
  const adv = p.exposed ? D.advByFlight.get(`${p.hex}:${p.volcano_id}`) : null;
  if (adv) {
    const [state, tone, ic] = advState(adv);
    kids.push(el("section", { class: `fl-now fl-now--${tone}`, "aria-labelledby": "fl-adv-h" },
      el("div", { class: "gl-top" }, el("h3", { class: "gl-label", id: "fl-adv-h", text: "Drafted action" }), el("span", { class: `ss-badge ss-badge--${tone}` }, icon(ic), state)),
      el("p", { class: "fl-now__act", text: actionText(adv) }),
      adv.decision_reason ? el("p", { class: "dk-sub__note" }, "Reason given: ", el("q", { text: adv.decision_reason })) : null,
      dkFoot(el("a", { class: "btn btn--small", href: `/desk#review/${encodeURIComponent(adv.id)}`, target: "_blank", rel: "noopener", text: adv.status === "DRAFT" ? "Open on the Desk ›" : "See it on the Desk ›" }),
        techDetail(`action ${actionWords(adv)} · status ${adv.status}${adv.version != null ? ` · version ${adv.version}` : ""}`))));
  } else if (p.exposed) {
    // no advisory because the assistant did not run: the job, here, once (D54)
    const hand = handPlan(D, store);
    const mine = hand.flights.find((x) => x.key === `${p.hex}:${p.volcano_id}`);
    if (mine) {
      const b = hand.block;
      // paused: what is missing and what to do; the cause is behind "Why ›" (docs/UI-AI-QUIET.md 8.6),
      // as it is for a skill that did not run or gave no result
      kids.push(dkNote("caution", [el("p", {}, b.paused ? "No advisory draft for this flight. " : `No advisory for this flight: ${blockPhrase(b)}. `,
        el("a", { class: "link-btn", href: "/desk", target: "_blank", rel: "noopener", text: "Plan it by hand on the Desk ›" }),
        b.paused || b.unavailable ? [" ", whyLink("fdetail-why")] : null,
        mine.must ? [" ", dkChip("Must do", { kind: "must", title: "Code requires this work this run" })] : null)], { role: "status" }));
    } else kids.push(dkEmpty("No advisory is drafted for this flight yet.", null));
  }
  const rr = (store_reroutes(D) || []).find((r) => r.properties.flight_id === `${p.hex}:${p.volcano_id}` || r.properties.proxy_flight === p.proxy_flight);
  if (rr) kids.push(rerouteBlock(rr.properties, D));
  kids.push(techDetail(`ADS-B ${p.callsign || "(no callsign)"} · hex ${String(p.hex || "").toUpperCase()}${p.type_icao ? ` · type ${p.type_icao}` : ""}`));
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
    el("p", { class: "dk-sub__note", text: "Operator policy A caution area, not a VAA or SIGMET. Approving Keep watching or Continue for this flight needs a written reason on the Desk." }),
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
    ["Entered", String(r.entered_by || "").startsWith("connect:")
      ? `pushed by ${String(r.entered_by).slice(8)} at ${hhmmz(ms(r.created_at))} (Connect)`
      : `${String(r.entered_by || "").replace(/^desk:/, "")} at ${hhmmz(ms(r.created_at))} on the Desk`],
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
    title: [el("span", { id: `crew-${r.id}`, text: r.flight }), r.replay && D?.mode !== "REPLAY" ? [" ", dkFromReplay(r.replay, false)] : null],
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
  const report = el("div", { class: "dk-actions" }, el("a", { class: "btn btn--small", href: "/desk#crew-report", target: "_blank", rel: "noopener", text: "Report ash from a crew on the Desk ›" }));
  const chip = dkChip("Operator policy A · not a VAA or SIGMET", { kind: "crew" });
  const title = "A dispatcher enters a crew report on the Desk. Code draws a caution area and flags flights that cross it.";
  if (!C.reports.length) {
    host.replaceChildren(dkSection("crew-head", dkHeader({ id: "crew-head", pills: [dkPill("ok", "None in the last 24 h")], title, chips: [chip] }),
      dkEmpty("No crew report of ash in the last 24 hours.", null), report));
    return;
  }
  const act = C.reports.filter((v) => v.state === "ACTIVE" || v.state === "COVERED").length;
  const out = C.reports.filter((v) => v.discrepancy).length;
  host.replaceChildren(dkSection("crew-head",
    dkHeader({ id: "crew-head", pills: [act ? dkPill("caution", `${act} with a caution area now`) : dkPill("off", "None active")], title, chips: [chip] }),
    dkTiles([
      { label: "Reports (24 h)", value: String(C.reports.length) },
      { label: "Caution area now", value: String(act), tone: act ? "caution" : null },
      { label: "Flights flagged", value: String(C.flags.length) },
      out ? { label: "Outside official area", value: String(out), tone: "caution" } : null,
    ], "Crew reports in numbers"),
    dkList(C.reports.map((v) => crewRow(D, v, ui.details.vid === v.report.id)), { first: 4, key: "crew" }),
    report));
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
    case "sat": case "notices": case "recovery": case "proof": case "ai": case "runs": renderXPanel(key, D, store); return;
    case "chain": chainSection(D, store, ui); return;
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
  // TEPHRA Assistant's section carries its mark (Strata, ta-16) beside the name (Naming)
  const tk = `${sec?.key || ""}|${t}`;
  if (title.dataset.k !== tk) { title.dataset.k = tk; title.replaceChildren(...(sec?.key === "ai" ? [icon("ta-16", "icon drawer__mark"), t] : [t])); }
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
