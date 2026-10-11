// The Wall's AI-extension panels (docs/EXTENSIONS.md WP11): the Satellite check, Notices,
// Recovery board, Proof panel and the AI activity tray, plus the reroute popup. They live in
// the rail under their own tabs so the map stays the hero. Rule 0 (no fallbacks): when an AI
// step failed the panel says "AI unavailable: <reason>" and shows nothing in its place.
// Every feed or model string goes in through el() (textContent); AI-written text carries an
// "AI-written" mark with the model id, code-written values are plain.

import { $, el, icon, ms, hhmmz, dayMon } from "./util.js";
import { frameFor } from "./ext-map.js";
import { st, aiMark, pill, section, plainLine, techDetail, usd, planProblem } from "./x-parts.js";
import { dutyPanel, dispatchedTools } from "./duty.js";

// ------------------------------------------------------------------ state

export const ext = {
  notices: [], recovery: [], budget: null, backtest: null,
  loaded: { notices: false, recovery: false, budget: false, backtest: false },
  errors: {},
  arrivals: new Map(), // trace id -> performance.now() when it arrived on the stream
  lastSeenSat: new Map(),
};

const getJson = async (url) => {
  const res = await fetch(url, { headers: { Accept: "application/json" }, cache: "no-store" });
  if (!res.ok) {
    let detail = "";
    try { detail = (await res.json()).detail || ""; } catch { /* no body */ }
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return res.json();
};

export async function loadExt(onChange) {
  const jobs = [
    ["notices", "/api/notices", (d) => { ext.notices = d.notices || []; }],
    ["recovery", "/api/recovery", (d) => { ext.recovery = d.plans || []; }],
    ["budget", "/api/budget", (d) => { ext.budget = d; }],
    ["backtest", "/api/backtest", (d) => { ext.backtest = d; }],
  ];
  await Promise.all(jobs.map(async ([key, url, set]) => {
    try { set(await getJson(url)); ext.errors[key] = null; } catch (e) { ext.errors[key] = e.message; }
    ext.loaded[key] = true;
  }));
  onChange();
}

export function ingest(name, data) {
  if (name === "notice") upsert(ext.notices, data, true);
  else if (name === "recovery") upsert(ext.recovery, data, true);
  else if (name === "budget") { ext.budget = data; ext.errors.budget = null; ext.loaded.budget = true; }
}

function upsert(list, item, front) {
  const i = list.findIndex((x) => x.id === item.id);
  if (i >= 0) list[i] = item; else if (front) list.unshift(item); else list.push(item);
}

export function noteTrace(t) { ext.arrivals.set(t.id, performance.now()); }

// ------------------------------------------------------------------ small parts

const pct = (v, d = 1) => (v == null ? "n/a" : `${(v * 100).toFixed(d)}%`);
const clock = (iso) => { const t = ms(iso); return Number.isFinite(t) ? `${dayMon(t)} ${hhmmz(t)}` : "n/a"; };

function unavailable(reason) {
  const text = String(reason || "no reason given").replace(/^AI UNAVAILABLE:?\s*/i, "");
  return el("div", { class: "x-fail", role: "status" }, st("st-serious", "var(--c-serious)"),
    el("p", {}, el("strong", { text: "AI unavailable: " }), text, el("span", { class: "x-fail__note", text: " Nothing was put in its place." })));
}

// CSP: no style attributes, so sizes and colours go through the CSSOM.
const fill = (w) => { const n = el("span"); n.style.width = `${w}%`; return n; };
const swatch = (c) => { const n = el("span", { class: "x-key__sw" }); n.style.background = c; return n; };
const empty = (title, text) => el("div", { class: "x-empty" }, el("strong", { text: title }), el("p", { text }));
const loadingBox = () => el("div", { class: "x-loading" }, el("div", { class: "skeleton" }), el("div", { class: "skeleton" }), el("div", { class: "skeleton" }));
const errBox = (what, msg) => el("div", { class: "x-fail", role: "status" }, st("st-caution", "var(--c-caution)"), el("p", {}, el("strong", { text: `${what} unavailable: ` }), msg));

function frameView(reading, frame) {
  const wrap = el("div", { class: "x-frame" });
  const safe = frame?.image_url && /^\/[^/]/.test(frame.image_url);
  if (safe) wrap.append(el("img", { class: "x-frame__img", src: frame.image_url, alt: `${frame.product === "DUST_RGB" ? "Himawari Dust RGB" : "Satellite"} frame ${frame.caption || ""}`, loading: "lazy" }));
  else wrap.append(el("div", { class: "x-frame__none", text: "Frame image not on the Wall" }));
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 1000 1000");
  svg.setAttribute("preserveAspectRatio", "none");
  svg.setAttribute("class", "x-frame__boxes");
  svg.setAttribute("aria-hidden", "true");
  reading.boxes.forEach((b, i) => {
    const [y0, x0, y1, x1] = b.box_2d;
    const r = document.createElementNS(NS, "rect");
    r.setAttribute("x", String(x0)); r.setAttribute("y", String(y0));
    r.setAttribute("width", String(Math.max(1, x1 - x0))); r.setAttribute("height", String(Math.max(1, y1 - y0)));
    r.setAttribute("class", "x-frame__box"); r.setAttribute("vector-effect", "non-scaling-stroke");
    svg.append(r);
    const t = document.createElementNS(NS, "text");
    t.setAttribute("x", String(x0 + 8)); t.setAttribute("y", String(Math.max(46, y0 - 8)));
    t.setAttribute("class", "x-frame__tag");
    t.textContent = String(i + 1);
    svg.append(t);
  });
  wrap.append(svg);
  return wrap;
}

const COLOUR_KEY = [
  ["#e53935", "Red", "ash, deeper red is thicker"],
  ["#43e65a", "Bright green", "SO2"],
  ["#d9a441", "In between", "ash and SO2 mixed"],
  ["#c64fd1", "Magenta, pink", "dust or ash: the Dust RGB frame cannot tell them apart"],
];

function colourKey() {
  return el("details", { class: "x-key" },
    el("summary", {}, icon("i-chevron-right", "icon x-key__chev"), "Colour key · JMA RGB guide"),
    el("ul", { class: "x-key__list" }, ...COLOUR_KEY.map(([c, n, m]) => el("li", {}, swatch(c), el("strong", { text: n }), ` ${m}`))),
    el("p", { class: "x-key__note", text: "Colour alone cannot separate ash from dust, and the picture gives no height and no concentration." }));
}

// ------------------------------------------------------------------ Satellite picture (R8.3, R12.5)

// Neutral words (G26): they never say an AI looked when AI is off.
const ASH_WORD = { yes: "yes", no: "not seen", uncertain: "can't tell" };
const yesNo = (v) => ({ yes: "yes", no: "no", uncertain: "can't tell" }[v] || "not given");

function readBy(reading) {
  const no = !reading.model_id || reading.model_id === "stub" || reading.label === "NO MODEL";
  return no ? "code stub (AI off)" : reading.model_id;
}

function satCard(D, reading, sit, store) {
  const vid = reading.volcano_id;
  const name = sit?.volcano_name || vid;
  const frames = [...(sit?.frames || []), ...(store.snapshot?.overlays?.frames || [])];
  const frame = frameFor(reading, frames);
  const card = el("article", { class: `x-card${vid === D.selected ? " x-card--sel" : ""}` });
  card.append(el("header", { class: "x-card__head" },
    el("h3", { class: "x-card__title", text: name }),
    D.mode === "REPLAY" || reading.replay ? el("span", { class: "tag tag--replay", text: "recorded" }) : null,
    el("span", { class: "x-card__time mono", text: reading.observed_at ? `scan ${clock(reading.observed_at)}` : "" })));
  if (reading.status === "ai_unavailable") { card.append(unavailable(reading.reason)); return card; }
  if (reading.status === "no_frames") {
    card.append(el("p", { class: "x-quiet", text: reading.reason || "No satellite picture was available to read." }));
    return card;
  }
  const n = reading.boxes.length;
  card.append(el("dl", { class: "x-facts" },
    el("dt", { text: "Ash visible?" }), el("dd", { class: reading.ash_visible === "yes" ? "x-facts--caution" : null, text: ASH_WORD[reading.ash_visible] ? capFirst(ASH_WORD[reading.ash_visible]) : "Can't tell" }),
    el("dt", { text: "Gas (SO2, not ash)" }), el("dd", { text: capFirst(yesNo(reading.so2_visible)) }),
    el("dt", { text: "Cloud in the way" }), el("dd", { text: capFirst(yesNo(reading.obscured_by_cloud)) }),
    el("dt", { text: "Ash marked on the picture" }), el("dd", { text: n ? `${n} box${n === 1 ? "" : "es"}` : "none" }),
    el("dt", { text: "Read by" }), el("dd", { text: readBy(reading) })));
  const placed = frame?.corners || reading.boxes.some((b) => b.polygon);
  const pic = el("details", { class: "more", dataset: { k: `sat-pic-${vid}` } }, el("summary", { text: "Show the picture" }),
    frameView(reading, frame),
    el("p", { class: "x-sub", text: n ? (placed ? "Boxes are placed on the map by code from the picture's bounds." : "These boxes sit on the picture only: it has no map position, so none is drawn on the map.") : "No box was drawn." }),
    reading.limits ? el("blockquote", { class: "x-quote" }, el("p", { text: reading.limits }), aiMark(reading.model_id, reading.label)) : aiMark(reading.model_id, reading.label),
    colourKey());
  card.append(pic, el("p", { class: "x-support" }, icon("i-info"), reading.note || "Supporting evidence only. It never changes the official area, TEPHRA's estimate, the heights or an advisory."));
  return card;
}

function satPanel(D, store) {
  const readings = store.snapshot?.satellite || [];
  const list = readings.slice().sort((a, b) => (a.volcano_id === D.selected ? -1 : 0) - (b.volcano_id === D.selected ? -1 : 0));
  const stub = D.state.llm?.backend === "stub";
  const kids = [el("p", { class: "dnote", text: stub
    ? "The latest Himawari picture for each active volcano, read by a code stub while AI is off. It is supporting evidence only and never changes the hazard area, the flight levels or an action."
    : "A model looks at the latest Himawari picture for each active volcano and says whether it sees ash. It never changes the hazard area, the flight levels or an action." })];
  if (!list.length) kids.push(empty("No satellite reading yet", "A reading appears when a new picture arrives for an active volcano."));
  for (const r of list) kids.push(satCard(D, r, D.sits.find((s) => s.volcano_id === r.volcano_id), store));
  return kids;
}

const capFirst = (t) => (t ? t[0].toUpperCase() + t.slice(1) : t);

// ------------------------------------------------------------------ Notices

const LANG = { en: "EN", id: "ID", ja: "JA", fil: "FIL" };
const langBadge = (code) => el("span", { class: "lang", title: { EN: "English", ID: "Indonesian", JA: "Japanese", FIL: "Filipino" }[LANG[code]] || "Another language" }, LANG[code] || "??");

const isJma = (n) => n.source_kind === "jma_xml";

function noticeStatus(n) {
  if (isJma(n)) return pill("ok", "Verified", "Read by code from JMA's published XML. No model was used.");
  if (n.status === "verified") return pill("ok", "Verified", "Every claim was found word for word in the notice and checked by code.");
  if (n.status === "ai_unavailable") return pill("serious", "AI unavailable", n.reason || "");
  return pill("caution", "Not verified", n.reason || "A check failed, so nothing from this notice entered the picture.");
}

// A JMA report comes from /api/notices like a pasted notice but was parsed by code from JMA's XML:
// its fields carry no quoted evidence and no model is named.
function noticeCard(n) {
  const card = el("article", { class: "x-card" });
  card.append(el("header", { class: "x-card__head" },
    langBadge(n.language), noticeStatus(n),
    isJma(n) ? el("span", { class: "x-card__title x-card__title--sm", text: `JMA · ${n.vona?.volcano_name || "volcano report"}` }) : null,
    n.replay ? el("span", { class: "tag tag--replay", text: "recorded" }) : null,
    el("span", { class: "x-card__time mono", text: clock(n.created_at) })));
  if (n.status === "ai_unavailable") card.append(unavailable(n.reason));
  else if (n.status === "unverified") card.append(el("p", { class: "x-quiet", text: (n.reason || "Could not be verified.").replace(/^NOT VERIFIED:\s*/i, "") }));
  if (n.fields?.length) {
    const dl = el("dl", { class: "x-fields" });
    for (const f of n.fields) {
      dl.append(el("dt", { text: f.name.replace(/_/g, " ") }), el("dd", {}, el("span", { class: "mono", text: f.derived || f.value }), f.evidence ? el("q", { class: "x-fields__ev", text: f.evidence }) : null));
    }
    card.append(dl);
  }
  if (n.problems?.length) card.append(el("ul", { class: "x-problems" }, ...n.problems.map((p) => el("li", { text: p }))));
  if (isJma(n)) card.append(el("p", { class: "x-sub mono", text: n.id }));
  else if (n.status !== "ai_unavailable") card.append(aiMark(n.model_id, n.label));
  return card;
}

function noticesPanel() {
  const kids = [];
  if (!ext.loaded.notices) return [loadingBox()];
  if (ext.errors.notices) return [errBox("Notices", ext.errors.notices)];
  const pasted = ext.notices.filter((n) => !isJma(n));
  const jma = ext.notices.filter(isJma);
  const newest = ext.notices.slice().sort((a, b) => ms(b.created_at) - ms(a.created_at))[0];
  kids.push(el("p", { class: "dsum", text: ext.notices.length ? `${ext.notices.length} notice${ext.notices.length === 1 ? "" : "s"} · newest ${clock(newest.created_at)}` : "No notices yet" }),
    el("p", { class: "dnote", text: "Notices pasted on the Desk, and JMA volcano reports. A pasted notice is read by a model, then every claim is checked against its own words; only a verified notice can enter the picture. JMA reports are read by code from JMA's XML." }));
  if (!ext.notices.length) { kids.push(empty("Nothing to show", "Paste a notice on the Desk (EN, ID, JA or FIL) and it shows up here.")); return kids; }
  kids.push(noticeCard(newest));
  const rest = ext.notices.filter((n) => n !== newest);
  if (rest.length) {
    const more = el("details", { class: "more", dataset: { k: "notices-all" } }, el("summary", { text: `All notices and their claims (${ext.notices.length})` }));
    if (pasted.length) more.append(section(`Pasted notices · ${pasted.length}`, ...pasted.map(noticeCard)));
    if (jma.length) more.append(section(`JMA reports · ${jma.length}`, ...jma.map(noticeCard)));
    kids.push(more);
  }
  return kids;
}

// ------------------------------------------------------------------ Recovery board

const PLAN_STATUS = {
  DRAFT: ["caution", "Waiting for a dispatcher"], APPROVED: ["ok", "Approved"], REJECTED: ["serious", "Rejected"],
  SUPERSEDED: ["off", "Superseded"], AI_UNAVAILABLE: ["serious", "No plan"],
};
const LEVEL = (ft) => (ft == null ? "?" : ft <= 0 ? "SFC" : `FL${String(Math.round(ft / 100)).padStart(3, "0")}`);

function totalsGrid(t) {
  const cell = (n, l, cls) => el("div", { class: `x-stat${cls ? ` x-stat--${cls}` : ""}` }, el("dd", { text: String(n) }), el("dt", { text: l }));
  return el("dl", { class: "x-stats" },
    cell(t.kept_flights, "kept"), cell(t.delayed_flights, "delayed", t.delayed_flights ? "caution" : ""),
    cell(t.cancelled_flights, "cancelled", t.cancelled_flights ? "serious" : ""), cell(t.swapped_flights, "swapped"),
    cell(t.pax_affected.toLocaleString("en"), "passengers affected"), cell(usd(t.total_usd), "total cost"));
}

// The plan in one line, for the summary and the Details index (R8.3 `recovery`).
export function recoverySummary(plan) {
  if (!plan) return null;
  const p = planProblem(plan);
  if (p) return p.words;
  if (plan.status === "AI_UNAVAILABLE") return `No plan: AI unavailable (${String(plan.unavailable_reason || "no reason given").replace(/^AI UNAVAILABLE:?\s*/i, "")}). A dispatcher must plan the network by hand.`;
  const icaos = [...new Set(plan.closures.map((c) => c.icao))];
  const tops = plan.closures.filter((c) => c.top_ft != null);
  const band = tops.length ? ` ${LEVEL(Math.min(...tops.map((c) => c.base_ft ?? 0)))}/${LEVEL(Math.max(...tops.map((c) => c.top_ft)))}` : "";
  const r = plan.closures.find((c) => c.radius_nm != null)?.radius_nm;
  const head = `${icaos.join(", ")} closed by ash${band}${r != null ? ` within ${Math.round(r)} NM` : ""}`;
  const t = plan.chosen?.totals;
  const what = t ? `cancel ${t.cancelled_flights}${t.delayed_flights ? `, delay ${t.delayed_flights}` : ""}, ${usd(t.total_usd)}` : "no scenario chosen";
  const status = plan.status === "DRAFT" ? "Plan waiting on the Desk" : plan.status === "APPROVED" ? "Plan approved" : plan.status === "REJECTED" ? "Plan rejected" : "Plan";
  return `${head} · ${status}: ${what}`;
}

function recoveryPanel(D) {
  if (!ext.loaded.recovery) return [loadingBox()];
  if (ext.errors.recovery) return [errBox("Airport plan", ext.errors.recovery)];
  const plans = ext.recovery.slice().sort((a, b) => ms(b.created_at) - ms(a.created_at));
  const plan = plans.find((p) => p.status !== "SUPERSEDED") || plans[0];
  const lede = el("p", { class: "dnote", text: "Airports the ash closes, and the day's flights of RFA (a fictional airline, synthetic schedule) re-planned around them. An optimiser (code) builds the scenarios; a model only picks one and explains it. A dispatcher approves on the Desk." });
  if (!plan) return [el("p", { class: "dsum", text: "No RFA airport is closed by the ash right now." }), lede];
  const [kind, text] = PLAN_STATUS[plan.status] || ["info", plan.status];
  const problem = planProblem(plan);
  const kids = [
    el("p", { class: "dsum", title: `as of ${clock(plan.created_at)}` }, el("span", { text: recoverySummary(plan) }), plan.replay ? el("span", { class: "tag tag--replay", text: "recorded" }) : null),
    el("p", { class: "dnote", text: `as of ${clock(plan.created_at)} · ${plan.outcome === "STUB" ? "planned by code (AI off)" : `chosen by ${plan.model_id}`} · version ${plan.version}` }),
  ];
  if (problem) kids.push(el("div", { class: "x-fail", role: "status" }, st("st-serious", "var(--c-serious)"), el("p", {}, el("strong", { text: problem.words })), techDetail(problem.raw)));
  else if (plan.status === "AI_UNAVAILABLE") kids.push(unavailable(plan.unavailable_reason));
  const card = el("article", { class: "x-card x-card--plan" });
  card.append(el("header", { class: "x-card__head" }, pill(kind, text), el("span", { class: "x-card__time mono", text: clock(plan.created_at) })));
  card.append(el("h4", { class: "x-h", text: `Closed airports · ${plan.closures.length}` }),
    el("ul", { class: "x-closures" }, ...plan.closures.map((c) => el("li", { class: "x-closure" }, el("strong", { class: "mono", text: c.icao }),
      el("span", { class: "mono", text: `${clock(c.start)} – ${c.open_ended ? "open" : clock(c.end)}` }),
      // One line written by code; the full reason and every source id stay behind the disclosure.
      c.summary ? el("span", { class: "x-closure__sum", text: c.summary }) : null,
      el("details", { class: "x-closure__more" }, el("summary", { text: "Full reason and sources" }),
        el("p", { class: "x-closure__why", text: c.reason }),
        c.source_ids?.length ? el("p", { class: "x-closure__src mono", text: c.source_ids.join(" · ") }) : null)))));
  if (plan.disruption) {
    const d = plan.disruption;
    card.append(el("p", { class: "x-sub", text: `${d.blocked_flights.length} flights and ${d.blocked_pax.toLocaleString("en")} passengers blocked before re-planning · can still change ${d.free_flights} · can't change (already departed) ${d.frozen_flights}${d.airborne_at_risk?.length ? ` · in the air and at risk: ${d.airborne_at_risk.join(", ")}` : ""}` }));
  }
  const chosen = plan.chosen;
  if (chosen) {
    card.append(el("h4", { class: "x-h" }, "Chosen scenario"), el("p", { class: "x-chosen" }, el("strong", { text: chosen.label }), ` · ${chosen.solver_status === "OPTIMAL" ? "best plan found" : chosen.solver_status === "UNKNOWN" ? "solver gave no answer" : chosen.status.toLowerCase()} (${Math.round(chosen.solve_ms / 1000)} s)`));
    if (chosen.totals) card.append(totalsGrid(chosen.totals));
  } else if (plan.status !== "AI_UNAVAILABLE") card.append(el("p", { class: "x-quiet", text: "No scenario chosen." }));
  if (plan.scenarios.length > 1) {
    const rows = plan.scenarios.map((sc) => el("tr", { class: sc.id === plan.chosen_scenario_id ? "is-chosen" : null },
      el("th", { scope: "row", text: sc.label }), el("td", { class: "num", text: sc.totals ? String(sc.totals.cancelled_flights) : "–" }),
      el("td", { class: "num", text: sc.totals ? String(sc.totals.delayed_flights) : "–" }), el("td", { class: "num", text: sc.totals ? usd(sc.totals.total_usd) : sc.solver_status === "UNKNOWN" ? "no plan (solver did not finish)" : sc.status })));
    card.append(el("table", { class: "x-table" }, el("caption", { class: "sr-only", text: "Recovery scenarios" }),
      el("thead", {}, el("tr", {}, el("th", { scope: "col", text: "Scenario" }), el("th", { scope: "col", class: "num", text: "Cancel" }), el("th", { scope: "col", class: "num", text: "Delay" }), el("th", { scope: "col", class: "num", text: "Cost" }))),
      el("tbody", {}, ...rows)));
  }
  if (plan.rationale) card.append(el("h4", { class: "x-h", text: "Why" }), el("blockquote", { class: "x-quote" }, el("p", { text: plainLine(plan.rationale) }), aiMark(plan.model_id, plan.outcome === "STUB" ? "NO MODEL" : null), techDetail(plan.rationale)));
  if (plan.risks?.length) card.append(el("h4", { class: "x-h", text: "Risks" }), el("ul", { class: "x-problems" }, ...plan.risks.map((r) => el("li", { text: r }))));
  const decided = plan.decided_at ? `${plan.status === "REJECTED" ? "Rejected" : "Approved"} by ${(plan.decided_by || "a dispatcher").replace(/^desk:/, "")} at ${hhmmz(ms(plan.decided_at))}` : null;
  card.append(el("p", { class: "x-approval" }, icon(plan.status === "APPROVED" ? "i-approved" : "i-dispatcher"),
    decided || (plan.status === "DRAFT" ? "Waiting for a dispatcher. Nothing is sent anywhere." : "No decision.")));
  kids.push(el("details", { class: "more", dataset: { k: "plan-more" } }, el("summary", { text: "Per-airport reasons, scenarios and numbers" }), card), lede);
  if (plans.length > 1) kids.push(el("p", { class: "x-sub", text: `${plans.length - 1} earlier plan${plans.length === 2 ? "" : "s"} not shown.` }));
  return kids;
}

// ------------------------------------------------------------------ Proof

const ARM = { D: "Baseline: code only, no model call", G: "With the Gemini Plume Reader" };

function meter(label, value, tone) {
  const w = value == null ? 0 : Math.max(0, Math.min(1, value)) * 100;
  return el("div", { class: "x-meter" },
    el("div", { class: "x-meter__top" }, el("span", { text: label }), el("strong", { class: "mono", text: pct(value) })),
    el("div", { class: `x-meter__bar x-meter__bar--${tone}`, role: "img", "aria-label": `${label} ${pct(value)}` }, fill(w)));
}

function armStats(arm, s, lead) {
  const gain = s.coverage_gain_mean;
  const l = (lead || [])[0];
  const box = el("div", { class: "x-arm" }, el("h4", { class: "x-arm__title", text: ARM[arm] || `Arm ${arm}` }),
    el("dl", { class: "x-stats x-stats--proof" },
      el("div", { class: "x-stat" }, el("dd", { text: gain == null ? "n/a" : `${gain >= 0 ? "+" : ""}${(gain * 100).toFixed(2)} pts` }), el("dt", { text: "coverage gain vs official" })),
      el("div", { class: "x-stat" }, el("dd", { text: pct(s.overwarn_mean, 0) }), el("dt", { text: "over-warning" })),
      el("div", { class: "x-stat" }, el("dd", { text: s.excess_vs_official_mean == null ? "n/a" : `${s.excess_vs_official_mean.toFixed(2)}×` }), el("dt", { text: "area vs official" })),
      el("div", { class: "x-stat" }, el("dd", { text: l?.median_min == null ? "n/a" : `${Math.round(l.median_min)} min` }), el("dt", { text: l ? `median lead · ${l.n_covered_before_official} of ${l.n_footprints} earlier` : "median lead" })),
      el("div", { class: "x-stat" }, el("dd", { text: pct(s.vertical_hit_rate, 0) }), el("dt", { text: "top level reached" })),
      el("div", { class: "x-stat" }, el("dd", { text: s.ticks_scored.toLocaleString("en") }), el("dt", { text: "moments scored" }))));
  if (arm === "D") box.append(el("p", { class: "x-sub", text: "This baseline makes no model call, so the zone equals the official area and the gain is zero by design. It checks the safety floor and the scoring; it is not a result for the AI." }));
  return box;
}

export function proofTicks() {
  const b = ext.backtest;
  if (!b?.overall) return null;
  return Object.values(b.overall).reduce((n, a) => n + (a.ticks_scored || 0), 0);
}

function proofPanel() {
  if (!ext.loaded.backtest) return [loadingBox()];
  if (ext.errors.backtest) return [errBox("Track record", ext.errors.backtest)];
  const b = ext.backtest;
  const arms = Object.keys(b.overall || {});
  const kids = [el("div", { class: "x-caveat", role: "note" }, icon("i-alert"),
    el("div", {}, el("strong", { text: "Later official areas are not ash truth." }), el("p", { text: "TEPHRA is scored against the official areas issued after each moment. Those are partly built from the same reports and satellite data, so this measures agreement, not what the ash did." })))];
  for (const a of arms) {
    kids.push(el("div", { class: "x-arm x-arm--sum" }, el("h4", { class: "x-arm__title", text: ARM[a] || `Arm ${a}` }),
      meter("Area TEPHRA covers of later official areas", b.overall[a].coverage_mean, "tephra"),
      meter("Area the official area alone covers", b.overall[a].coverage_official_mean, "official")));
  }
  if (!arms.includes("G")) kids.push(el("p", { class: "x-sub x-sub--warn", text: "The Gemini arm has not been run on these cases, so no improvement is claimed." }));
  const rows = b.cases.map((c) => el("tr", {},
    el("th", { scope: "row" }, el("span", { class: "x-case__name", text: c.label.split(":")[0] }), el("span", { class: "x-case__meta mono", text: `${c.case_id} · arm ${c.arm}` })),
    el("td", { class: "num", text: pct(c.summary.coverage_mean) }), el("td", { class: "num", text: pct(c.summary.coverage_official_mean) }),
    el("td", { class: "num", text: pct(c.summary.overwarn_mean, 0) }), el("td", { class: "num", text: c.summary.ticks_scored.toLocaleString("en") })));
  kids.push(el("details", { class: "more", dataset: { k: "proof-more" } }, el("summary", { text: "Every number, check and case" }),
    ...arms.map((a) => armStats(a, b.overall[a], (b.overall_lead || {})[a])),
    el("div", { class: "x-checks" },
      pill(b.floor_violations === 0 ? "ok" : "serious", `Safety floor: ${b.floor_violations} violations`, "A violation means the estimate left out part of an official area."),
      pill(b.input_leaks === 0 ? "ok" : "serious", `Future data used: ${b.input_leaks}`, "Inputs stamped after the replayed moment. Must be zero.")),
    section("Per case", el("div", { class: "x-tablewrap" }, el("table", { class: "x-table x-table--cases" }, el("caption", { class: "sr-only", text: "Backtest results per case" }),
      el("thead", {}, el("tr", {}, el("th", { scope: "col", text: "Case" }), el("th", { scope: "col", class: "num", text: "TEPHRA" }), el("th", { scope: "col", class: "num", text: "Official" }), el("th", { scope: "col", class: "num", text: "Over-warn" }), el("th", { scope: "col", class: "num", text: "Moments" }))),
      el("tbody", {}, ...rows)))),
    section("Caveats", el("ul", { class: "x-problems x-problems--plain" }, ...(b.caveats || []).map((c) => el("li", { text: c })))),
    el("p", { class: "x-sub mono", text: `Scored by code, no model writes a number · generated ${clock(b.generated_at)}Z · every case is a recorded replay` })));
  return kids;
}

// ------------------------------------------------------------------ AI activity tray

export const AGENTS = [
  { id: "duty", name: "Duty Officer", stage: "DUTY", what: "Coordinates the others and writes the brief" },
  { id: "plume", name: "Plume Reader", stage: "PLUME", what: "Proposes the cautious area" },
  { id: "sat", name: "Satellite eyes", stage: "SATELLITE", what: "Reads the satellite picture" },
  { id: "planner", name: "Planner", stage: "PLANNER", what: "Chooses an action per flight" },
  { id: "drafter", name: "Drafter", stage: "DRAFTER", what: "Writes the advisories" },
  { id: "ask", name: "Ask", stage: "ASK", what: "Answers questions from the data" },
  { id: "notice", name: "Notice Reader", stage: "NOTICE", what: "Reads pasted notices" },
  { id: "recovery", name: "Recovery", stage: "RECOVERY", what: "Re-plans the day's flights" },
  { id: "messages", name: "Messages", stage: "MESSAGES", what: "Drafts crew and passenger messages", skip: /HANDOVER/i },
  { id: "sra", name: "SRA", stage: "DOCS", what: "Drafts regulator paperwork" },
  { id: "handover", name: "Handover", stage: "MESSAGES", what: "Writes the shift handover", only: /HANDOVER/i },
  { id: "backtest", name: "Backtest", stage: null, what: "Scores the zone against later official areas" },
];
// The Duty Officer tool that reaches each specialist.
const DELEGATED_VIA = { plume: "assess_volcanoes", sat: "assess_volcanoes", planner: "plan_flights", drafter: "plan_flights", recovery: "run_recovery", sra: "draft_sra" };
const AI_STAGES = new Set(AGENTS.map((a) => a.stage).filter(Boolean));
const RUNNING_MS = 6000;

export function agentStatus(store) {
  const trace = store.trace || [];
  const nowT = performance.now();
  const delegated = dispatchedTools(store.snapshot?.duty);
  return AGENTS.map((a) => {
    if (!a.stage) {
      const ok = ext.backtest && !ext.errors.backtest;
      return { ...a, state: ok ? "done" : "idle", count: ok ? ext.backtest.cases.length : 0, fails: 0, last: ok ? ext.backtest.generated_at : null, detail: ok ? `${ext.backtest.cases.length} cases scored` : "Not run yet" };
    }
    const mine = trace.filter((t) => t.stage === a.stage && (!a.skip || !a.skip.test(t.message)) && (!a.only || a.only.test(t.message)));
    const last = mine[mine.length - 1];
    const fails = mine.filter((t) => t.level === "error").length;
    let state = "idle";
    if (last) state = last.level === "error" ? "failed" : nowT - (ext.arrivals.get(last.id) ?? -1e9) < RUNNING_MS ? "running" : "done";
    return { ...a, state, count: mine.length, fails, last: last?.at || null, detail: last?.message || "No step yet", delegated: delegated.has(DELEGATED_VIA[a.id]) };
  });
}

export function failureCount(store) {
  return (store.trace || []).filter((t) => t.level === "error" && AI_STAGES.has(t.stage)).length;
}

const STATE_UI = {
  idle: ["st-never", "var(--c-off)", "Idle"], running: ["st-info", "var(--c-observer)", "Running"],
  done: ["st-ok", "var(--c-ok)", "Done"], failed: ["st-serious", "var(--c-serious)", "Failed"],
};

function budgetBlock() {
  if (!ext.loaded.budget) return loadingBox();
  if (ext.errors.budget || !ext.budget) return errBox("Budget", ext.errors.budget || "no answer");
  const b = ext.budget;
  return el("div", { class: "x-budget" },
    el("p", { class: "x-lede x-lede--tight" }, b.backend === "stub" ? "Offline stub: no model is called, so no quota is spent." : "Free-tier calls left today."),
    ...b.tiers.map((t) => {
      const left = t.limit ? t.remaining / t.limit : 0;
      const tone = b.backend === "stub" ? "off" : left < 0.15 ? "serious" : left < 0.4 ? "caution" : "ok";
      return el("div", { class: "x-tier" },
        el("div", { class: "x-tier__top" }, el("span", {}, el("strong", { text: t.tier === "main" ? "Main model" : "Lite model" }), el("span", { class: "x-tier__id mono", text: ` ${t.model_id}` })),
          el("strong", { class: "mono", text: `${t.remaining} left of ${t.limit}` })),
        el("div", { class: `x-meter__bar x-meter__bar--${tone}`, role: "img", "aria-label": `${t.remaining} of ${t.limit} calls left` }, fill(Math.round(left * 100))));
    }),
    el("p", { class: "x-sub", text: b.note }));
}

export function budgetWords() {
  const b = ext.budget;
  const main = b?.tiers?.find((t) => t.tier === "main");
  if (!main) return null;
  return `AI calls today: ${Math.max(0, main.limit - main.remaining)} of ${main.limit}`;
}

function aiPanel(D, store) {
  const agents = agentStatus(store);
  const failed = failureCount(store);
  const lines = (store.trace || []).filter((t) => t.level === "error" && AI_STAGES.has(t.stage)).slice(-5).reverse();
  const run = store.snapshot?.duty;
  const stub = D.state.llm?.backend === "stub";
  const jobsN = run ? (run.dispatches || []).length : 0;
  const duty = run
    ? `Duty Officer (${run.outcome === "MODEL_FAILED" ? "AI unavailable" : stub || run.outcome === "STUB" ? "AI off" : dutyModelLabel(run)}): handed out ${jobsN} job${jobsN === 1 ? "" : "s"} in urgency order`
    : "Duty Officer: no run yet";
  const kids = [
    el("p", { class: "dsum", text: `${stub ? "AI off: code does every step, and code templates write the text a model would." : `AI on (${D.state.llm?.label}): it can widen TEPHRA's estimate, never shrink the official area.`}` }),
    el("p", { class: "dline" }, icon("i-agent"), el("span", { text: duty })),
  ];
  if (failed) kids.push(el("div", { class: "x-fail x-fail--count", role: "status" }, st("st-serious", "var(--c-serious)"), el("p", {}, el("strong", { text: `${failed} AI step${failed === 1 ? "" : "s"} failed. ` }), "Each one is in How TEPHRA decided as an error; nothing was made up in its place.")));
  if (lines.length) kids.push(el("ul", { class: "x-fails" }, ...lines.map((t) => el("li", {}, el("span", { class: "mono x-fails__t", text: hhmmz(ms(t.at)) }), el("span", { text: plainLine(t.message) }), techDetail(`${t.stage} · ${t.message}`)))));
  const bw = budgetWords();
  if (bw) kids.push(el("p", { class: "dline" }, icon("i-gauge"), el("span", { text: bw })));
  kids.push(el("details", { class: "more", dataset: { k: "ai-more" } }, el("summary", { text: "Delegation, every helper and the budget" }),
    ...dutyPanel(run, !!store.snapshot),
    section("Every AI helper",
      el("p", { class: "x-lede x-lede--tight", text: "Every AI step on the Wall. Status comes from How TEPHRA decided. When a step fails it says why and nothing is made up in its place." }),
      el("ul", { class: "x-agents" }, ...agents.map((a) => {
        const [ic, col, word] = STATE_UI[a.state];
        return el("li", { class: `x-agent x-agent--${a.state}`, title: plainLine(a.detail) },
          el("span", { class: "x-agent__dot" }, st(ic, col)),
          el("span", { class: "x-agent__main" }, el("strong", { class: "x-agent__name", text: a.name }), el("span", { class: "x-agent__what", text: a.what }),
            a.delegated ? el("span", { class: "x-agent__via" }, icon("i-agent"), "given a job by the Duty Officer") : null),
          el("span", { class: "x-agent__state" }, el("span", { class: "x-agent__word", text: word }), el("span", { class: "x-agent__n mono", text: a.stage ? `${a.count} step${a.count === 1 ? "" : "s"}${a.fails ? ` · ${a.fails} failed` : ""}` : a.detail })));
      }))),
    section("Model budget", budgetBlock())));
  return kids;
}

const dutyModelLabel = (run) => run.model_id || "model";

// ------------------------------------------------------------------ Details sections hosted in #xpanel

export const XSECTIONS = { sat: satPanel, notices: noticesPanel, recovery: recoveryPanel, proof: proofPanel, ai: aiPanel };

export function renderXPanel(key, D, store) {
  const panel = $("xpanel");
  const build = XSECTIONS[key];
  if (!build || !D) return;
  panel.dataset.panel = key;
  panel.replaceChildren(...build(D, store).filter(Boolean));
}

// ------------------------------------------------------------------ a reroute, inside Details › This flight

export function rerouteBlock(props, D) {
  const dl = el("dl", { class: "pop__facts" });
  const row = (k, v, mono) => { if (v == null || v === "") return; dl.append(el("dt", { text: k }), el("dd", { class: mono ? "mono" : null, text: String(v) })); };
  row("Kind", props.kind === "REJOIN_TRACK" ? "Go around, then rejoin the track" : "Direct to destination");
  row("Side", props.side ? props.side.toLowerCase() : null);
  row("Extra distance", props.extra_nm != null ? `+${Math.round(props.extra_nm)} NM` : null, true);
  row("Extra time", props.extra_min != null ? `+${Math.round(props.extra_min)} min` : null, true);
  row("Status", props.status ? String(props.status).toLowerCase() : null);
  const wps = Array.isArray(props.waypoint_labels) ? props.waypoint_labels : [];
  if (wps.length) row("Turn points", wps.join("  "), true);
  const kids = [el("h3", { class: "sec__title", text: "Suggested reroute" }), el("p", { class: "dnote", text: "Computed by code around TEPHRA's estimate · a draft route for the dispatcher" }), dl];
  if (props.route_string) kids.push(el("p", { class: "pop__route mono", text: props.route_string }));
  return el("section", { class: "sec reroute" }, ...kids);
}

// Satellite context scale (5.6): only for layers whose NASA GIBS entry publishes a colour map
// legend (Himawari band 13 infrared and TROPOMI SO2). Visible and Air Mass RGB have none, and
// none is drawn. The colours and labels come from GIBS at run time; when that file does not
// load, the strip says so and shows nothing in its place.
const SCALE = {
  ir: { file: "Clean_Longwave_Infrared_Window_Band", note: "drawn in grey, as on the map" },
  so2: { file: "OMI_SO2_Lower_Troposphere", note: null },
};
const scales = new Map();

// The map shows infrared with raster-saturation -1 and raster-contrast 0.2 (map.js); MapLibre
// turns those into "average of r, g, b" and "(c - 0.5) * 1.25 + 0.5". The strip does the same.
const greyIr = ([r, g, b]) => {
  const v = Math.round(Math.min(255, Math.max(0, ((r + g + b) / 3 / 255 - 0.5) * 1.25 * 255 + 127.5)));
  return [v, v, v];
};

async function loadScale(key, onChange) {
  scales.set(key, { state: "loading", at: Date.now() });
  try {
    const res = await fetch(`https://gibs.earthdata.nasa.gov/colormaps/v1.3/${SCALE[key].file}.xml`, { cache: "force-cache", signal: AbortSignal.timeout(10000) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const doc = new DOMParser().parseFromString(await res.text(), "application/xml");
    if (doc.querySelector("parsererror")) throw new Error("unreadable colour map");
    const cmap = [...doc.getElementsByTagName("ColorMap")].find((c) => c.getAttribute("units"));
    const legend = cmap?.getElementsByTagName("Legend")[0];
    if (!legend) throw new Error("no legend in the colour map");
    const entries = [...legend.getElementsByTagName("LegendEntry")]
      .filter((e) => /\d/.test(e.getAttribute("tooltip") || ""))
      .map((e) => ({ rgb: (e.getAttribute("rgb") || "").split(",").map(Number), label: e.getAttribute("showLabel") === "true" ? e.getAttribute("label") : null }));
    if (entries.length < 2 || entries.some((e) => e.rgb.length !== 3 || e.rgb.some((v) => !Number.isFinite(v)))) throw new Error("unexpected legend entries");
    scales.set(key, { state: "ok", title: cmap.getAttribute("title") || "", units: cmap.getAttribute("units"), min: legend.getAttribute("minLabel"), max: legend.getAttribute("maxLabel"), entries });
  } catch (e) {
    scales.set(key, { state: "failed", at: Date.now(), reason: e.message });
  }
  onChange();
}

export function satScale(key, onChange) {
  const spec = SCALE[key];
  if (!spec) return null;
  const s = scales.get(key);
  if (!s || (s.state === "failed" && Date.now() - s.at > 5 * 60e3)) loadScale(key, onChange);
  const cur = scales.get(key);
  if (cur.state === "loading") return el("p", { class: "ctx-scale glass ctx-scale--note", text: "Scale loading from NASA GIBS…" });
  if (cur.state === "failed") return el("p", { class: "ctx-scale glass ctx-scale--note", role: "status", text: "Scale unavailable: the NASA GIBS colour map did not load. No scale is shown in its place." });
  const n = cur.entries.length;
  const colour = (rgb) => `rgb(${(key === "ir" ? greyIr(rgb) : rgb).join(" ")})`;
  const stops = cur.entries.map((e, i) => `${colour(e.rgb)} ${((i / n) * 100).toFixed(2)}% ${(((i + 1) / n) * 100).toFixed(2)}%`);
  const bar = el("span", { class: "ctx-scale__bar", "aria-hidden": "true" });
  bar.style.backgroundImage = `linear-gradient(to right, ${stops.join(", ")})`;
  const ticks = el("span", { class: "ctx-scale__ticks", "aria-hidden": "true" });
  const tick = (text, at, edge) => {
    const t = el("span", { class: `ctx-scale__tick${edge ? ` ctx-scale__tick--${edge}` : ""}`, text });
    t.style.left = `${at}%`;
    ticks.append(t);
  };
  if (cur.min) tick(cur.min, 0, "start");
  // inner labels too close to an end label would overlap it on a 360 px strip
  cur.entries.forEach((e, i) => {
    const at = ((i + 0.5) / n) * 100;
    if (e.label && !(cur.min && at < 12) && !(cur.max && at > 88)) tick(e.label, at, null);
  });
  if (cur.max) tick(cur.max, 100, "end");
  const caption = `Scale: ${cur.title}${cur.units ? ` (${cur.units})` : ""} · NASA GIBS colour map${spec.note ? ` · ${spec.note}` : ""}`;
  return el("div", { class: "ctx-scale glass", role: "img", "aria-label": `${caption}, from ${cur.min} to ${cur.max}` }, el("span", { class: "ctx-scale__cap", text: caption }), bar, ticks);
}
