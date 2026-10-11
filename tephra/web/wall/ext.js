// The Wall's AI-extension panels (docs/EXTENSIONS.md WP11): the Satellite check, Notices,
// Recovery board, Proof panel and the AI activity tray, plus the reroute popup. They live in
// the rail under their own tabs so the map stays the hero. Rule 0 (no fallbacks): when an AI
// step failed the panel says "AI unavailable: <reason>" and shows nothing in its place.
// Every feed or model string goes in through el() (textContent); AI-written text carries an
// "AI-written" mark with the model id, code-written values are plain.

import { $, el, icon, ms, hhmmz, hhmmssz, dayMon } from "./util.js";
import { frameFor } from "./ext-map.js";

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

const st = (id, color) => icon(id, "st", color);
const pct = (v, d = 1) => (v == null ? "n/a" : `${(v * 100).toFixed(d)}%`);
const clock = (iso) => { const t = ms(iso); return Number.isFinite(t) ? `${dayMon(t)} ${hhmmz(t)}` : "n/a"; };

// Marks AI-written text with the model id; the stub says NO MODEL.
function aiMark(modelId, label) {
  const no = label === "NO MODEL" || !modelId || modelId === "stub";
  return el("span", { class: `ai-mark${no ? " ai-mark--none" : ""}`, title: no ? "No model wrote this: the offline stub" : "Written by a model. Code checked every number, time and id." },
    icon("i-model"), el("span", { text: no ? "NO MODEL" : `AI-written · ${modelId}` }));
}

function unavailable(reason) {
  const text = String(reason || "no reason given").replace(/^AI UNAVAILABLE:?\s*/i, "");
  return el("div", { class: "x-fail", role: "status" }, st("st-serious", "var(--c-serious)"),
    el("p", {}, el("strong", { text: "AI unavailable: " }), text, el("span", { class: "x-fail__note", text: " Nothing was put in its place." })));
}

function pill(kind, text, title) {
  const ic = { ok: "st-ok", caution: "st-caution", serious: "st-serious", info: "st-info", off: "st-off" }[kind] || "st-info";
  const col = { ok: "var(--c-ok)", caution: "var(--c-caution)", serious: "var(--c-serious)", info: "var(--c-info)", off: "var(--c-off)" }[kind];
  return el("span", { class: `pill pill--${kind}`, title }, st(ic, col), el("span", { text }));
}

// CSP: no style attributes, so sizes and colours go through the CSSOM.
const fill = (w) => { const n = el("span"); n.style.width = `${w}%`; return n; };
const swatch = (c) => { const n = el("span", { class: "x-key__sw" }); n.style.background = c; return n; };
const section = (title, ...kids) => el("section", { class: "x-sec" }, el("h3", { class: "caps x-sec__title", text: title }), ...kids);
const empty = (title, text) => el("div", { class: "x-empty" }, el("strong", { text: title }), el("p", { text }));
const loadingBox = () => el("div", { class: "x-loading" }, el("div", { class: "skeleton" }), el("div", { class: "skeleton" }), el("div", { class: "skeleton" }));
const errBox = (what, msg) => el("div", { class: "x-fail", role: "status" }, st("st-caution", "var(--c-caution)"), el("p", {}, el("strong", { text: `${what} unavailable: ` }), msg));

// ------------------------------------------------------------------ Satellite check

const ANSWER = {
  yes: ["caution", "Ash seen in the picture", "The AI read red ash colours in the frame."],
  no: ["info", "No ash seen in the picture", "Not seeing ash in a picture is not evidence that there is none."],
  uncertain: ["caution", "Unclear", "The AI could not tell."],
};

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

function satCard(D, reading, sit, store, ui) {
  const vid = reading.volcano_id;
  const name = sit?.volcano_name || vid;
  const frames = [...(sit?.frames || []), ...(store.snapshot?.overlays?.frames || [])];
  const frame = frameFor(reading, frames);
  const card = el("article", { class: `x-card${vid === D.selected ? " x-card--sel" : ""}` });
  const head = el("header", { class: "x-card__head" },
    el("h3", { class: "x-card__title", text: name }),
    D.mode === "REPLAY" || reading.replay ? el("span", { class: "tag tag--replay", text: "recorded" }) : null,
    el("span", { class: "x-card__time mono", text: reading.observed_at ? `scan ${clock(reading.observed_at)}` : "" }));
  card.append(head);
  if (reading.status === "ai_unavailable") { card.append(unavailable(reading.reason)); return card; }
  if (reading.status === "no_frames") {
    card.append(el("p", { class: "x-quiet", text: reading.reason || "No satellite frame was available to read." }));
    return card;
  }
  const [kind, label, why] = ANSWER[reading.ash_visible] || ANSWER.uncertain;
  card.append(el("p", { class: "x-verdict" }, el("span", { class: "x-verdict__cap caps", text: "Satellite check" }), pill(kind, label, why)));
  const facts = el("div", { class: "x-pills" },
    pill(reading.so2_visible === "yes" ? "caution" : "off", `SO2: ${reading.so2_visible || "n/a"}`, "SO2 is not ash. Shown as context only."),
    pill(reading.obscured_by_cloud === "no" ? "ok" : "caution", `Cloud covers it: ${reading.obscured_by_cloud || "n/a"}`, "Cloud over a plume can hide it."),
    pill("info", `${reading.boxes.length} box${reading.boxes.length === 1 ? "" : "es"}`));
  card.append(facts, frameView(reading, frame));
  const placed = frame?.corners || reading.boxes.some((b) => b.polygon);
  card.append(el("p", { class: "x-sub" }, reading.boxes.length
    ? (placed ? "Boxes are placed on the map by code from the frame bounds." : "These boxes sit on the picture only: this frame has no map position, so none is drawn on the map.")
    : "The AI drew no box."));
  if (reading.limits) card.append(el("blockquote", { class: "x-quote" }, el("p", { text: reading.limits }), aiMark(reading.model_id, reading.label)));
  else card.append(aiMark(reading.model_id, reading.label));
  card.append(colourKey(), el("p", { class: "x-support" }, icon("i-info"), reading.note || "Supporting evidence only."));
  return card;
}

function satPanel(D, store) {
  const readings = store.snapshot?.satellite || [];
  const list = readings.slice().sort((a, b) => (a.volcano_id === D.selected ? -1 : 0) - (b.volcano_id === D.selected ? -1 : 0));
  const kids = [el("p", { class: "x-lede", text: "A model looks at the latest Himawari picture for each active volcano and says whether it sees ash. It never changes the hazard area, the flight levels or an action." })];
  if (!list.length) kids.push(empty("No satellite reading yet", "A reading appears when a new frame arrives for an active volcano."));
  for (const r of list) kids.push(satCard(D, r, D.sits.find((s) => s.volcano_id === r.volcano_id), store));
  return kids;
}

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
  const kids = [el("p", { class: "x-lede", text: "Notices pasted on the Desk, and JMA volcano reports. A pasted notice is read by a model, then every claim is checked against its own words; only a verified notice can enter the picture. JMA reports are read by code from JMA's XML." })];
  if (!ext.loaded.notices) kids.push(loadingBox());
  else if (ext.errors.notices) kids.push(errBox("Notices", ext.errors.notices));
  const pasted = ext.notices.filter((n) => !isJma(n));
  const jma = ext.notices.filter(isJma);
  if (ext.loaded.notices && !ext.errors.notices && !ext.notices.length) kids.push(empty("No notices yet", "Paste a notice on the Desk (EN, ID, JA or FIL) and it shows up here."));
  if (pasted.length) kids.push(section(`Pasted notices · ${pasted.length}`, ...pasted.map(noticeCard)));
  if (jma.length) kids.push(section(`JMA reports · ${jma.length}`, ...jma.map(noticeCard)));
  return kids;
}

// ------------------------------------------------------------------ Recovery board

const usd = (n) => (n == null ? "n/a" : `$${Number(n).toLocaleString("en")}`);
const PLAN_STATUS = {
  DRAFT: ["caution", "Draft · waiting for a dispatcher"], APPROVED: ["ok", "Approved"], REJECTED: ["serious", "Rejected"],
  SUPERSEDED: ["off", "Superseded"], AI_UNAVAILABLE: ["serious", "AI unavailable"],
};

function totalsGrid(t) {
  const cell = (n, l, cls) => el("div", { class: `x-stat${cls ? ` x-stat--${cls}` : ""}` }, el("dd", { text: String(n) }), el("dt", { text: l }));
  return el("dl", { class: "x-stats" },
    cell(t.kept_flights, "kept"), cell(t.delayed_flights, "delayed", t.delayed_flights ? "caution" : ""),
    cell(t.cancelled_flights, "cancelled", t.cancelled_flights ? "serious" : ""), cell(t.swapped_flights, "swapped"),
    cell(t.pax_affected.toLocaleString("en"), "passengers affected"), cell(usd(t.total_usd), "total cost"));
}

function recoveryPanel(D) {
  const kids = [el("p", { class: "x-lede", text: "Airports the ash closes, and the day's flights re-planned around them. An optimiser (code) builds the scenarios; a model only picks one and explains it. A dispatcher approves on the Desk." })];
  if (!ext.loaded.recovery) return [...kids, loadingBox()];
  if (ext.errors.recovery) return [...kids, errBox("Recovery", ext.errors.recovery)];
  const plans = ext.recovery.slice().sort((a, b) => ms(b.created_at) - ms(a.created_at));
  const plan = plans.find((p) => p.status !== "SUPERSEDED") || plans[0];
  if (!plan) return [...kids, empty("No recovery plan", "No RFA airport is closed by the hazard right now.")];
  const [kind, text] = PLAN_STATUS[plan.status] || ["info", plan.status];
  const card = el("article", { class: "x-card x-card--plan" });
  card.append(el("header", { class: "x-card__head" }, pill(kind, text),
    plan.replay ? el("span", { class: "tag tag--replay", text: "recorded" }) : null,
    el("span", { class: "tag", text: `v${plan.version}` }),
    el("span", { class: "x-card__time mono", text: clock(plan.created_at) })));
  card.append(el("p", { class: "x-fict", text: "Fictional airline RFA · synthetic schedule" }));
  if (plan.status === "AI_UNAVAILABLE") card.append(unavailable(plan.unavailable_reason));
  card.append(el("h4", { class: "caps x-h", text: `Closed airports · ${plan.closures.length}` }),
    el("ul", { class: "x-closures" }, ...plan.closures.map((c) => el("li", { class: "x-closure" }, el("strong", { class: "mono", text: c.icao }),
      el("span", { class: "mono", text: `${clock(c.start)} – ${c.open_ended ? "open" : clock(c.end)}` }),
      // One line written by code; the full reason and every source id stay behind the disclosure.
      c.summary ? el("span", { class: "x-closure__sum", text: c.summary }) : null,
      el("details", { class: "x-closure__more" }, el("summary", { text: "Full reason and sources" }),
        el("p", { class: "x-closure__why", text: c.reason }),
        c.source_ids?.length ? el("p", { class: "x-closure__src mono", text: c.source_ids.join(" · ") }) : null)))));
  if (plan.disruption) card.append(el("p", { class: "x-sub", text: `${plan.disruption.blocked_flights.length} flights and ${plan.disruption.blocked_pax.toLocaleString("en")} passengers blocked before re-planning.` }));
  const chosen = plan.chosen;
  if (chosen) {
    card.append(el("h4", { class: "caps x-h" }, "Chosen scenario"), el("p", { class: "x-chosen" }, el("strong", { text: chosen.label }), ` · ${chosen.status}`));
    if (chosen.totals) card.append(totalsGrid(chosen.totals));
  } else if (plan.status !== "AI_UNAVAILABLE") card.append(el("p", { class: "x-quiet", text: "No scenario chosen." }));
  if (plan.scenarios.length > 1) {
    const rows = plan.scenarios.map((s) => el("tr", { class: s.id === plan.chosen_scenario_id ? "is-chosen" : null },
      el("th", { scope: "row", text: s.label }), el("td", { class: "num", text: s.totals ? String(s.totals.cancelled_flights) : "–" }),
      el("td", { class: "num", text: s.totals ? String(s.totals.delayed_flights) : "–" }), el("td", { class: "num", text: s.totals ? usd(s.totals.total_usd) : s.status })));
    card.append(el("table", { class: "x-table" }, el("caption", { class: "sr-only", text: "Recovery scenarios" }),
      el("thead", {}, el("tr", {}, el("th", { scope: "col", text: "Scenario" }), el("th", { scope: "col", class: "num", text: "Cancel" }), el("th", { scope: "col", class: "num", text: "Delay" }), el("th", { scope: "col", class: "num", text: "Cost" }))),
      el("tbody", {}, ...rows)));
  }
  if (plan.rationale) card.append(el("h4", { class: "caps x-h", text: "Why" }), el("blockquote", { class: "x-quote" }, el("p", { text: plan.rationale }), aiMark(plan.model_id, plan.outcome === "STUB" ? "NO MODEL" : null)));
  if (plan.risks?.length) card.append(el("h4", { class: "caps x-h", text: "Risks" }), el("ul", { class: "x-problems" }, ...plan.risks.map((r) => el("li", { text: r }))));
  const decided = plan.decided_at ? `${plan.status === "REJECTED" ? "Rejected" : "Approved"} by ${(plan.decided_by || "a dispatcher").replace(/^desk:/, "")} at ${hhmmz(ms(plan.decided_at))}` : null;
  card.append(el("p", { class: "x-approval" }, icon(plan.status === "APPROVED" ? "i-approved" : "i-dispatcher"),
    decided || (plan.status === "DRAFT" ? "Waiting for a dispatcher. Nothing is sent anywhere." : "No decision.")));
  kids.push(card);
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

function armBlock(arm, s, lead) {
  const gain = s.coverage_gain_mean;
  const l = (lead || [])[0];
  const box = el("div", { class: "x-arm" }, el("h4", { class: "x-arm__title", text: ARM[arm] || `Arm ${arm}` }));
  box.append(
    meter("Area TEPHRA covers of later official areas", s.coverage_mean, "tephra"),
    meter("Area the official area alone covers", s.coverage_official_mean, "official"),
    el("dl", { class: "x-stats x-stats--proof" },
      el("div", { class: "x-stat" }, el("dd", { text: gain == null ? "n/a" : `${gain >= 0 ? "+" : ""}${(gain * 100).toFixed(2)} pts` }), el("dt", { text: "coverage gain vs official" })),
      el("div", { class: "x-stat" }, el("dd", { text: pct(s.overwarn_mean, 0) }), el("dt", { text: "over-warning" })),
      el("div", { class: "x-stat" }, el("dd", { text: s.excess_vs_official_mean == null ? "n/a" : `${s.excess_vs_official_mean.toFixed(2)}×` }), el("dt", { text: "area vs official" })),
      el("div", { class: "x-stat" }, el("dd", { text: l?.median_min == null ? "n/a" : `${Math.round(l.median_min)} min` }), el("dt", { text: l ? `median lead · ${l.n_covered_before_official} of ${l.n_footprints} earlier` : "median lead" })),
      el("div", { class: "x-stat" }, el("dd", { text: pct(s.vertical_hit_rate, 0) }), el("dt", { text: "top level reached" })),
      el("div", { class: "x-stat" }, el("dd", { text: s.ticks_scored.toLocaleString("en") }), el("dt", { text: "ticks scored" }))));
  if (arm === "D") box.append(el("p", { class: "x-sub", text: "This baseline makes no model call, so the zone equals the official area and the gain is zero by design. It checks the safety floor and the scoring; it is not a result for the AI." }));
  return box;
}

function proofPanel() {
  const kids = [];
  if (!ext.loaded.backtest) return [loadingBox()];
  if (ext.errors.backtest) return [errBox("Backtest", ext.errors.backtest)];
  const b = ext.backtest;
  const arms = Object.keys(b.overall || {});
  kids.push(el("div", { class: "x-caveat", role: "note" }, icon("i-alert"),
    el("div", {}, el("strong", { text: "Later official areas are not ash truth." }), el("p", { text: "TEPHRA is scored against the official areas issued after each moment. Those are partly built from the same reports and satellite data, so this measures agreement, not what the ash did." }))));
  for (const a of arms) kids.push(armBlock(a, b.overall[a], (b.overall_lead || {})[a]));
  if (!arms.includes("G")) kids.push(el("p", { class: "x-sub x-sub--warn", text: "The Gemini arm has not been run on these cases, so no improvement is claimed." }));
  kids.push(el("div", { class: "x-checks" },
    pill(b.floor_violations === 0 ? "ok" : "serious", `Safety floor: ${b.floor_violations} violations`, "A violation means the cone left out part of an official area."),
    pill(b.input_leaks === 0 ? "ok" : "serious", `Future data used: ${b.input_leaks}`, "Inputs stamped after the replayed moment. Must be zero.")));
  const rows = b.cases.map((c) => el("tr", {},
    el("th", { scope: "row" }, el("span", { class: "x-case__name", text: c.label.split(":")[0] }), el("span", { class: "x-case__meta mono", text: `${c.case_id} · arm ${c.arm}` })),
    el("td", { class: "num", text: pct(c.summary.coverage_mean) }), el("td", { class: "num", text: pct(c.summary.coverage_official_mean) }),
    el("td", { class: "num", text: pct(c.summary.overwarn_mean, 0) }), el("td", { class: "num", text: c.summary.ticks_scored.toLocaleString("en") })));
  kids.push(section("Per case", el("div", { class: "x-tablewrap" }, el("table", { class: "x-table x-table--cases" }, el("caption", { class: "sr-only", text: "Backtest results per case" }),
    el("thead", {}, el("tr", {}, el("th", { scope: "col", text: "Case" }), el("th", { scope: "col", class: "num", text: "TEPHRA" }), el("th", { scope: "col", class: "num", text: "Official" }), el("th", { scope: "col", class: "num", text: "Over-warn" }), el("th", { scope: "col", class: "num", text: "Ticks" }))),
    el("tbody", {}, ...rows)))));
  kids.push(section("Caveats", el("ul", { class: "x-problems x-problems--plain" }, ...(b.caveats || []).map((c) => el("li", { text: c })))));
  kids.push(el("p", { class: "x-sub mono", text: `Scored by code, no model writes a number · generated ${clock(b.generated_at)}Z · every case is a recorded replay` }));
  return kids;
}

// ------------------------------------------------------------------ AI activity tray

export const AGENTS = [
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
const AI_STAGES = new Set(AGENTS.map((a) => a.stage).filter(Boolean));
const RUNNING_MS = 6000;

export function agentStatus(store) {
  const trace = store.trace || [];
  const nowT = performance.now();
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
    return { ...a, state, count: mine.length, fails, last: last?.at || null, detail: last?.message || "No step yet" };
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

function aiPanel(D, store) {
  const agents = agentStatus(store);
  const failed = failureCount(store);
  const kids = [
    el("p", { class: "x-lede", text: "Every AI step on the Wall. Status comes from the reasoning trace. When a step fails it says why and nothing is made up in its place." }),
    failed ? el("div", { class: "x-fail x-fail--count", role: "status" }, st("st-serious", "var(--c-serious)"), el("p", {}, el("strong", { text: `${failed} AI step${failed === 1 ? "" : "s"} failed. ` }), "Each one is in the trace as an error.")) : null,
    el("ul", { class: "x-agents" }, ...agents.map((a) => {
      const [ic, col, word] = STATE_UI[a.state];
      return el("li", { class: `x-agent x-agent--${a.state}`, title: a.detail },
        el("span", { class: "x-agent__dot" }, st(ic, col)),
        el("span", { class: "x-agent__main" }, el("strong", { class: "x-agent__name", text: a.name }), el("span", { class: "x-agent__what", text: a.what })),
        el("span", { class: "x-agent__state" }, el("span", { class: "x-agent__word", text: word }), el("span", { class: "x-agent__n mono", text: a.stage ? `${a.count} step${a.count === 1 ? "" : "s"}${a.fails ? ` · ${a.fails} failed` : ""}` : a.detail })));
    })),
    section("Model budget", budgetBlock()),
  ];
  const lines = (store.trace || []).filter((t) => t.level === "error" && AI_STAGES.has(t.stage)).slice(-5).reverse();
  if (lines.length) kids.splice(3, 0, section("Latest failures", el("ul", { class: "x-fails" }, ...lines.map((t) => el("li", {}, el("span", { class: "mono x-fails__t", text: hhmmssz(ms(t.at)) }), el("span", { class: "trace__stage", text: t.stage }), el("span", { text: t.message }))))));
  return kids;
}

// ------------------------------------------------------------------ tabs and the chip

export const PANELS = [
  { id: "brief", label: "Situation", icon: "i-list" },
  { id: "sat", label: "Satellite", icon: "i-satellite" },
  { id: "notices", label: "Notices", icon: "i-raw-text" },
  { id: "recovery", label: "Recovery", icon: "i-recovery" },
  { id: "proof", label: "Proof", icon: "i-proof" },
  { id: "ai", label: "AI", icon: "i-model" },
];

function tabBadge(id, D, store) {
  if (id === "sat") { const n = (store.snapshot?.satellite || []).filter((r) => r.status === "read").length; return n ? { text: String(n) } : null; }
  if (id === "notices") { const n = ext.notices.length; return n ? { text: String(n) } : null; }
  if (id === "recovery") { const p = ext.recovery.find((x) => x.status !== "SUPERSEDED"); return p ? { text: p.status === "DRAFT" ? "draft" : p.status === "APPROVED" ? "ok" : "!" , tone: p.status === "AI_UNAVAILABLE" || p.status === "REJECTED" ? "serious" : null } : null; }
  if (id === "ai") { const f = failureCount(store); return f ? { text: String(f), tone: "serious" } : null; }
  return null;
}

export function renderXTabs(D, store, ui) {
  const box = $("xtabs");
  box.replaceChildren(...PANELS.map((p, i) => {
    const sel = ui.rail === p.id;
    const badge = D ? tabBadge(p.id, D, store) : null;
    return el("button", { type: "button", class: "xtab", role: "tab", id: `xtab-${p.id}`, "aria-selected": sel ? "true" : "false", "aria-controls": p.id === "brief" ? "brief" : "xpanel", tabindex: sel ? "0" : "-1", dataset: { xtab: p.id, focus: `xtab-${p.id}` } },
      icon(p.icon), el("span", { class: "xtab__label", text: p.label }),
      badge ? el("span", { class: `xtab__badge${badge.tone ? ` xtab__badge--${badge.tone}` : ""}`, text: badge.text }) : null);
  }));
}

export function renderXPanel(D, store, ui) {
  const panel = $("xpanel");
  const on = ui.rail !== "brief";
  panel.hidden = !on;
  document.body.dataset.rail = ui.rail;
  if (!on || !D) return;
  const top = panel.scrollTop;
  const title = PANELS.find((p) => p.id === ui.rail)?.label || "";
  panel.setAttribute("aria-labelledby", `xtab-${ui.rail}`);
  panel.dataset.panel = ui.rail;
  const body = { sat: satPanel, notices: noticesPanel, recovery: recoveryPanel, proof: proofPanel, ai: aiPanel }[ui.rail](D, store);
  panel.replaceChildren(el("h2", { class: "x-title", text: title === "AI" ? "AI activity" : title === "Sat" ? "Satellite check" : title }), ...body.filter(Boolean));
  panel.scrollTop = top;
}

export function renderAiChip(store) {
  const chip = $("ai-chip");
  if (!chip) return;
  const failed = failureCount(store);
  const agents = agentStatus(store);
  const running = agents.filter((a) => a.state === "running").length;
  const b = ext.budget;
  const main = b?.tiers?.find((t) => t.tier === "main");
  const stub = b?.backend === "stub";
  const kids = [icon("i-model"), el("span", { class: "caps ai-chip__cap", text: "AI" })];
  if (running) kids.push(el("span", { class: "ai-chip__run" }, st("st-info", "var(--c-observer)"), `${running} running`));
  if (b && !stub) kids.push(el("span", { class: "ai-chip__left mono", text: `${main.remaining} left` }));
  if (failed) kids.push(el("span", { class: "ai-chip__fail", "aria-label": `${failed} AI failures` }, st("st-serious", "var(--c-serious)"), String(failed)));
  chip.replaceChildren(...kids);
  chip.setAttribute("aria-label", `AI activity: ${running} running, ${failed} failed${b && !stub ? `, ${main.remaining} main-model calls left today` : ""}. Opens the AI panel.`);
  chip.classList.toggle("ai-chip--fail", failed > 0);
}

// ------------------------------------------------------------------ reroute popup

export function reroutePopup(props, D) {
  const dl = el("dl", { class: "pop__facts" });
  const row = (k, v, mono) => { if (v == null || v === "") return; dl.append(el("dt", { text: k }), el("dd", { class: mono ? "mono" : null, text: String(v) })); };
  row("Kind", props.kind === "REJOIN_TRACK" ? "Go around, then rejoin the track" : "Direct to destination");
  row("Side", props.side ? props.side.toLowerCase() : null);
  row("Extra distance", props.extra_nm != null ? `+${Math.round(props.extra_nm)} NM` : null, true);
  row("Extra time", props.extra_min != null ? `+${Math.round(props.extra_min)} min` : null, true);
  row("Status", props.status);
  const wps = Array.isArray(props.waypoint_labels) ? props.waypoint_labels : [];
  if (wps.length) row("Turn points", wps.join("  "), true);
  const adv = D?.advByFlight?.get(props.flight_id);
  const kids = [el("p", { class: "pop__title", text: `${props.proxy_flight} reroute` }), el("p", { class: "pop__sub", text: "Computed by code around the cautious area · a draft route for the dispatcher" }), dl];
  if (props.route_string) kids.push(el("p", { class: "pop__route mono", text: props.route_string }));
  if (adv) kids.push(el("p", { class: "pop__sub", text: `Advisory ${adv.action}${adv.status ? ` · ${adv.status.toLowerCase()}` : ""}` }));
  return el("div", { class: "pop" }, ...kids);
}
