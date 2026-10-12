// The Details drawer (docs/UI-REDESIGN.md R8): everything on the Wall that is not the story, one
// tap away. It opens on a plain index of four groups; every row shows its live count or failure
// in words. A section opens summary first; long tables sit behind "Show all" disclosures. The
// section builders are the Wall's existing ones (panels.js, ext.js), re-parented here.
// Placement by width: a pushing column at 1600 px and up, the story column's place from 601 to
// 1599 px, a full-screen sheet at 600 px and below. Feed text goes in with textContent (el()).

import { $, el, icon, ms, hhmmz, age, fl, compassWord } from "./util.js";
import { SEV_RANK, NON_OBS, actionWords, deciderName, officialLabelText, plainMove, levelIsAll, tephraLabelText, untilText } from "./derive.js";
import {
  sourcesSection, disagreeSection, areaSection, decisionsSection, renderFlights, renderTrace, traceLines, renderLevels,
  historySection, feedsSection, lagOf, timelineEvents, advisoryLine, actionText, estimateOutcome, dayMonth, FEED_STATUS,
} from "./panels.js";
import { ext, renderXPanel, failureCount, recoverySummary, proofTicks, budgetWords, rerouteBlock, replanning } from "./ext.js";
import { renderLayers, layersStatus } from "./controls.js";
import { currentPlan, advisoryFacts, closuresFor } from "./story.js";
import { planProblem, techDetail } from "./x-parts.js";

// Section key, index group, title, host element id, the old rail panel id it stands for (R8.2).
export const SECTIONS = [
  { key: "sources", group: "The ash", title: "What the official reports say", host: "brief", xtab: "brief" },
  { key: "disagree", group: "The ash", title: "Where the sources disagree", host: "brief" },
  { key: "estimate", group: "The ash", title: "TEPHRA's estimate", host: "brief" },
  { key: "sat", group: "The ash", title: "Satellite picture", host: "xpanel", xtab: "sat" },
  { key: "notices", group: "The ash", title: "Notices", host: "xpanel", xtab: "notices" },
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
const HOSTS = ["brief", "xpanel", "flights", "decisions", "trace", "levels", "layers-pop", "feeds", "history"];
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
      return { text: tephraLabelText(cone, D.state.llm?.backend === "stub").replace("TEPHRA's estimate · ", "") };
    }
    case "sat": {
      const r = store.snapshot?.satellite || [];
      const bad = r.filter((x) => x.status === "ai_unavailable").length;
      const mine = r.find((x) => x.volcano_id === D?.selected && x.status === "read");
      if (bad) return { text: `${plural(r.length, "reading", "readings")} · ${bad} AI unavailable`, tone: "serious" };
      if (!r.length) return { text: "no reading yet" };
      return { text: `${plural(r.length, "reading", "readings")}${mine ? ` · ash visible? ${({ yes: "yes", no: "not seen" })[mine.ash_visible] || "can't tell"}` : ""}` };
    }
    case "notices":
      if (!ext.loaded.notices) return { text: "loading…" };
      if (ext.errors.notices) return { text: "could not load", tone: "serious" };
      return { text: ext.notices.length ? plural(ext.notices.length, "notice", "notices") : "none" };
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
      return { text: `${D?.state.draft_count ?? w} waiting, all volcanoes · ${ok} approved` };
    }
    case "recovery": {
      if (!ext.loaded.recovery) return { text: "loading…" };
      if (ext.errors.recovery) return { text: "could not load", tone: "serious" };
      const plan = currentPlan();
      const re = replanning(store);
      if (re) return { text: `${plural(re.airports.length, "airport", "airports")} (all volcanoes) · re-planning…`, tone: "caution" };
      if (!plan) return { text: "no airport closed" };
      if (plan.status === "AI_UNAVAILABLE") return { text: planProblem(plan) ? "no plan found" : "AI unavailable", tone: "serious" };
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
      const f = failureCount(store);
      const stub = D?.state.llm?.backend === "stub";
      return { text: `${stub ? "AI off" : "AI on"}${f ? ` · ${f} failed` : ""}`, tone: f ? "serious" : null };
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

function renderIndex(D, store, ui) {
  const box = $("xtabs");
  const groups = [];
  for (const s of SECTIONS) {
    if (s.hidden) continue;
    let g = groups.find((x) => x.name === s.group);
    if (!g) { g = { name: s.group, rows: [] }; groups.push(g); }
    g.rows.push(s);
  }
  const kids = [];
  for (const g of groups) {
    kids.push(el("div", { role: "listitem", class: "dindex__group" }, el("h3", { class: "dindex__head", text: g.name })));
    for (const s of g.rows) {
      const stt = indexStatus(s.key, D, store, ui);
      const tone = stt.tone ? ` dindex__row--${stt.tone}` : "";
      kids.push(el("div", { role: "listitem" }, el("button", { type: "button", class: `dindex__row${tone}`, id: `xtab-${s.xtab || s.key}`, dataset: { act: "details-sec", sec: s.key, xtab: s.xtab || null, focus: `drow-${s.key}` } },
        el("span", { class: "dindex__label", text: s.title }),
        el("span", { class: "dindex__status" }, stt.tone === "serious" ? st("st-serious", "var(--c-serious)") : stt.tone === "caution" ? st("st-caution", "var(--c-caution)") : null, el("span", { text: stt.text })),
        el("span", { class: "dindex__go", "aria-hidden": "true", text: "›" }))));
    }
  }
  const key = kids.map((k) => k.textContent).join("|");
  if (box.dataset.key !== key) { box.dataset.key = key; box.replaceChildren(...kids); }
}

// ------------------------------------------------------------------ This ash area, This flight (R8.3)

function areaDetail(D, store, vid) {
  const sit = D.sits.find((s) => s.volcano_id === vid);
  const host = $("brief");
  if (!sit) { host.replaceChildren(el("p", { class: "dsum", text: "This volcano is no longer active." })); return; }
  const t = officialLabelText(D, vid);
  const kids = [el("p", { class: "dsum", text: sit.volcano_name })];
  if (t) {
    const rawMove = (D.moveByVolcano[vid] || "").trim();
    const moves = /^NOT (STATED|GIVEN)$/i.test(rawMove) ? rawMove.toLowerCase() : plainMove(rawMove);
    // One entry per forecast step, at its own valid time: two reports with the same +6 h step are
    // one step on the map (review 2, item 7).
    const stepAt = new Map();
    for (const f of D.official.filter((x) => x.properties.volcano_id === vid && x.properties.step !== "now")) {
      const k = f.properties.layer.replace("FCST+", "+").replace("H", " h");
      const t = ms(f.properties.valid_from);
      if (!stepAt.has(k) || t < stepAt.get(k)) stepAt.set(k, t);
    }
    const steps = [...stepAt].sort((a, b) => a[1] - b[1]).map(([k, t]) => `${k} (${hhmmz(t)})`);
    const dl = el("dl", { class: "area__facts" });
    const row = (k, v, mono) => { if (v) dl.append(el("dt", { text: k }), el("dd", { class: mono ? "mono" : null, text: v })); };
    // Which reports, in words; their ids are under Technical ids.
    // One VAA can draw several layers (observed, estimated): it is counted once, by its number.
    const sigs = t.products.filter((x) => /^SIGMET\b/.test(x)).length;
    const vaas = new Set(t.products.filter((x) => /^VAA\b/.test(x)).map((x) => x.split(" ").slice(0, 3).join(" "))).size;
    row("Drawn from", [sigs ? `${sigs} ${sigs === 1 ? "SIGMET (airspace warning)" : "SIGMETs (airspace warnings), the newest per office"}` : null, vaas ? `${vaas} ${vaas === 1 ? "VAA (ash advisory)" : "VAAs (ash advisories)"}` : null].filter(Boolean).join(" + ") || `${t.products.length} official reports`);
    row("Issued by", [...new Set(D.official.filter((f) => f.properties.volcano_id === vid && f.properties.valid).map((f) => issuerWords(f.properties)))].join(" · "));
    row("Heights", `${fl(t.base)}–${fl(t.top)}`, true);
    row("Movement", moves || "not given");
    row("Valid until", `${hhmmz(t.validTo)} (${untilText(t.validTo - D.now)})`, true);
    row("Forecast steps", steps.length ? steps.join(" · ") : "none in the current reports");
    kids.push(el("section", { class: "sec" }, el("h3", { class: "sec__title sec__title--official", text: "Official ash area · binding" }), dl,
      el("div", { class: "btn-row" }, ...["SIGMET", "VAA"].filter((k) => sit.cards.some((c) => c.kind === k && !c.missing)).map((k) => el("button", { type: "button", class: "btn btn--small", dataset: { act: "raw", kind: k } }, icon("i-raw-text"), `Raw text: ${k}`))),
      el("details", { class: "more", dataset: { k: "area-ids" } }, el("summary", { text: "Technical ids" }), el("ul", { class: "tech__list mono" }, ...t.products.map((x) => el("li", { text: x }))))));
  } else {
    kids.push(el("p", { class: "dnote", text: "No official area is valid for this volcano right now." }));
  }
  const cone = D.coneOf(vid)?.properties;
  if (cone) {
    const dl = el("dl", { class: "area__facts" },
      el("dt", { text: "Rule" }), el("dd", { text: "Never smaller than any valid official area" }),
      el("dt", { text: "What it is" }), el("dd", { text: estimateOutcome(D, sit, cone) }),
      el("dt", { text: "Heights" }), el("dd", { class: "mono", text: `${fl(cone.base_ft)}–${fl(cone.top_ft)}` }),
      el("dt", { text: "Valid until" }), el("dd", { class: "mono", text: hhmmz(ms(cone.valid_to)) }));
    kids.push(el("section", { class: "sec" }, el("h3", { class: "sec__title sec__title--tephra", text: "TEPHRA's estimate · an estimate, not a forecast" }), dl,
      techDetail(`mode ${cone.mode} · ${cone.label} · confidence ${Math.round((cone.confidence ?? 0) * 100)}%`)));
  }
  kids.push(el("p", {}, el("button", { type: "button", class: "link-btn", dataset: { act: "details-sec", sec: "sources", focus: "area-sources" }, text: "What the official reports say ›" })));
  host.replaceChildren(...kids);
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

function flightDetail(D, ui) {
  const host = $("flights");
  const pick = ui.selFlight;
  if (!pick) { host.replaceChildren(el("p", { class: "dsum", text: "No flight is picked. Choose one on the map or in Flights heading in." })); return; }
  const f = D.selFlight;
  const kids = [el("p", { class: "dsum" }, el("strong", { text: f ? f.properties.proxy_flight : pick.proxy }), D.mode === "REPLAY" ? el("span", { class: "tag tag--replay", text: "recorded" }) : null,
    el("button", { type: "button", class: "link-btn fdetail__clear", "aria-label": "Clear the picked flight", dataset: { act: "flight-clear", focus: "flight-clear" }, text: "Clear" }))];
  if (!f) {
    kids.push(D.selHiddenByLevel
      ? el("p", { class: "fdetail__gone" }, `Hidden by the height filter ${fl(ui.level.min)}–${fl(ui.level.max)}. `,
        el("button", { type: "button", class: "link-btn", dataset: { act: "level-reset", focus: "fdetail-reset" }, text: "Reset" }))
      : el("p", { class: "fdetail__gone", text: "No current position for this flight in the aircraft data." }));
    host.replaceChildren(...kids);
    return;
  }
  const p = f.properties;
  kids.push(el("p", { class: "dnote", text: `RFA is a fictional airline · this flight stands in for ADS-B ${p.callsign || "(no callsign)"}, hex ${String(p.hex || "").toUpperCase()}${p.type_icao ? `, a ${p.type_icao}` : ""}` }));
  const dl = el("dl", { class: "fdetail__facts" });
  const row = (k, v) => { if (v != null && v !== "") dl.append(el("dt", { text: k }), el("dd", { text: String(v) })); };
  if (p.exposed) {
    row("Entry (estimated)", p.inside ? "Inside TEPHRA's area now" : `In ${p.minutes_to_entry} min`);
    row("Basis", "Code projection from the last position, if track, speed and level are held");
  } else {
    row("Entry (estimated)", "Not projected to enter TEPHRA's area");
  }
  row("Level", p.alt_baro_ft != null ? `${fl(p.alt_baro_ft)} (${Number(p.alt_baro_ft).toLocaleString("en")} ft)${p.nav_altitude_mcp_ft != null ? ` · selected ${fl(p.nav_altitude_mcp_ft)}` : ""}` : "level unknown");
  const move = [p.gs_kt != null ? `${Math.round(p.gs_kt)} kt` : null, p.track_deg != null ? `${Math.round(p.track_deg)}° ${compassWord(p.track_deg)}` : null].filter(Boolean).join(" · ");
  row("Speed and track", move);
  row("Position age", age(p.ageS));
  kids.push(dl);
  const adv = p.exposed ? D.advByFlight.get(`${p.hex}:${p.volcano_id}`) : null;
  if (adv) {
    kids.push(el("p", { class: "fdetail__adv" }, el("span", { class: "fdetail__k", text: "Drafted action: " }), el("strong", { text: actionText(adv) })),
      el("p", { class: "fdetail__adv" }, advisoryLine(adv, D.mode === "REPLAY")),
      el("p", {}, el("a", { class: "btn btn--small", href: `/desk#review/${encodeURIComponent(adv.id)}`, target: "_blank", rel: "noopener", text: adv.status === "DRAFT" ? "Open on the Desk ›" : "See it on the Desk ›" })));
  } else if (p.exposed) kids.push(el("p", { class: "dnote", text: "No advisory is drafted for this flight yet." }));
  const rr = (store_reroutes(D) || []).find((r) => r.properties.flight_id === `${p.hex}:${p.volcano_id}` || r.properties.proxy_flight === p.proxy_flight);
  if (rr) kids.push(rerouteBlock(rr.properties, D));
  host.replaceChildren(...kids);
}
let store_reroutes = () => [];

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
    case "flight": flightDetail(D, ui); return;
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

function renderSwitcher(D) {
  const sel = $("details-volcano");
  if (!D) return;
  const key = D.sits.map((s) => s.volcano_id).join("|");
  if (sel.dataset.key !== key) {
    sel.dataset.key = key;
    sel.replaceChildren(...D.sits.map((s) => el("option", { value: s.volcano_id, text: s.volcano_name })));
  }
  sel.hidden = !D.sits.length;
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
  renderSwitcher(D);
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
