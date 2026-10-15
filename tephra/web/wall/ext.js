// The Wall's AI-extension panels (docs/EXTENSIONS.md WP11): the Satellite check, Notices,
// Recovery board, Proof panel and the AI activity tray, plus the reroute popup. They live in
// the rail under their own tabs so the map stays the hero. Rule 0 (no fallbacks): when an
// assistant step failed the panel says so (the skill "gave no result") with what to do, and shows
// nothing in its place. The assistant's health has one home, Details › TEPHRA Assistant; the
// other panels say only what its absence changes, in caution tone (docs/UI-AI-QUIET.md, Naming).
// Every feed or model string goes in through el() (textContent); model-written text carries a
// short mark with the model id in its title.

import { $, el, icon, ms, hhmmz } from "./util.js";
import { frameFor } from "./ext-map.js";
import { aiMark, plainLine, techDetail, usd, planFailure, failureEach, aiStateOf, aiErrorsOf, newestPlan, aiLead, assistantIs, causeTitle, handPlanOf, reasonClass, realWhen, machineText, machineSentences, jobsWords, pacingWords, whyLink, WHY, MARK, ASSISTANT } from "./x-parts.js";
import { dutyDetail, dispatchedTools } from "./duty.js";
import { HELPERS } from "./board.js";
import { has } from "./features.js";
import {
  dkHeader, dkPill, dkChip, dkTiles, dkMeter, meterTone, dkGroup, dkRow, dkList, dkFacts, dkNote, dkAbout, dkEmpty, dkTech,
  dkSection, dkLink, dkFromReplay, dkWhen, timeRange, times, plural, dayTime,
} from "./dk.js";

// ------------------------------------------------------------------ state

export const ext = {
  notices: [], recovery: [], budget: null, backtest: null, docs: [], evals: null,
  loaded: { notices: false, recovery: false, budget: false, backtest: false, docs: false, evals: false },
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
    ["docs", "/api/docs", (d) => { ext.docs = d.docs || []; }],
    // the committed scorecards (docs/evals): the Plume reader's cases and the replay's speed figures
    ["evals", "/api/evals", (d) => { ext.evals = d; }],
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
  else if (name === "doc") upsert(ext.docs, data, true);
}

function upsert(list, item, front) {
  const i = list.findIndex((x) => x.id === item.id);
  if (i >= 0) list[i] = item; else if (front) list.unshift(item); else list.push(item);
}

export function noteTrace(t) {
  ext.arrivals.set(t.id, performance.now());
}

// ------------------------------------------------------------------ small parts

const pct = (v, d = 1) => (v == null ? "n/a" : `${(v * 100).toFixed(d)}%`);
const clock = (iso) => { const t = ms(iso); return Number.isFinite(t) ? dayTime(t) : "n/a"; };

// CSP: no style attributes, so sizes and colours go through the CSSOM.
const swatch = (c) => { const n = el("span", { class: "x-key__sw" }); n.style.background = c; return n; };
const loadingBox = () => el("div", { class: "x-loading" }, el("div", { class: "skeleton" }), el("div", { class: "skeleton" }), el("div", { class: "skeleton" }));

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
  return el("details", { class: "x-key", dataset: { k: "sat-colour-key" } },
    el("summary", {}, icon("i-chevron-right", "icon x-key__chev"), "Colour key · JMA RGB guide"),
    el("ul", { class: "x-key__list" }, ...COLOUR_KEY.map(([c, n, m]) => el("li", {}, swatch(c), el("strong", { text: n }), ` ${m}`))),
    el("p", { class: "x-key__note", text: "Colour alone cannot separate ash from dust, and the picture gives no height and no concentration." }));
}

// ------------------------------------------------------------------ Satellite picture (R8.3, R12.5)

// Neutral words (G26): they never say a model looked when the assistant is off.
const ASH_WORD = { yes: "yes", no: "not seen", uncertain: "can't tell" };
const yesNo = (v) => ({ yes: "yes", no: "no", uncertain: "can't tell" }[v] || "not given");
// Never green for "not seen": no ash seen is not evidence of no ash.
const ASH_TONE = { yes: "caution", no: "info", uncertain: "never" };

const readByCode = (reading) => !reading.model_id || reading.model_id === "stub" || reading.label === "NO MODEL";

function satRow(D, reading, sit, store) {
  const vid = reading.volcano_id;
  const name = sit?.volcano_name || vid;
  const frames = [...(sit?.frames || []), ...(store.snapshot?.overlays?.frames || [])];
  const frame = frameFor(reading, frames);
  const scan = reading.observed_at ? `scan ${clock(reading.observed_at)}` : "";
  const rec = dkFromReplay(reading.replay, D.mode === "REPLAY");
  if (reading.status === "ai_unavailable") {
    // a quota refusal says what happened ("paused" only while the whole assistant is), never its
    // cause: that is at the assistant's home, behind the section's "Why ›" (UI-AI-QUIET 8.6)
    const cls = reasonClass(reading.reason);
    const what = cls !== "budget" ? `Satellite reader gave no result (${WHY[cls] || WHY.other})` : aiState(D, store).kind === "paused" ? `${ASSISTANT} is paused` : "Satellite reader did not run";
    return dkRow({ key: `sat-${vid}`, dot: "caution", edge: "caution", title: name, sub: `Not read: ${what}. Nothing was put in its place.`, meta: scan,
      body: [dkTech(String(reading.reason || "no reason given"), reading.model_id ? `would have used ${reading.model_id}` : null)], open: vid === D.selected });
  }
  if (reading.status === "no_frames") {
    return dkRow({ key: `sat-${vid}`, dot: "never", title: name, sub: reading.reason || "No satellite picture was available to read.", meta: scan, cls: "dk-row--muted" });
  }
  const n = reading.boxes.length;
  const placed = frame?.corners || reading.boxes.some((b) => b.polygon);
  const ash = ASH_WORD[reading.ash_visible] ? capFirst(ASH_WORD[reading.ash_visible]) : "Can't tell";
  return dkRow({
    key: `sat-${vid}`, dot: ASH_TONE[reading.ash_visible] || "never", title: [name, rec ? [" ", rec] : null], open: vid === D.selected,
    sub: `Ash visible? ${ash}${n ? ` · ${n} box${n === 1 ? "" : "es"} marked` : ""}`, meta: el("span", { class: "mono", text: reading.observed_at ? hhmmz(ms(reading.observed_at)) : "" }),
    body: [
      dkFacts([
        ["Ash visible?", ash, reading.ash_visible === "yes" ? { tone: "caution" } : {}],
        ["Gas (SO2, not ash)", capFirst(yesNo(reading.so2_visible))],
        ["Cloud in the way", capFirst(yesNo(reading.obscured_by_cloud))],
        ["Ash marked on the picture", n ? `${n} box${n === 1 ? "" : "es"}` : "none"],
        ["Reading", aiMark(reading.model_id, reading.label, MARK.read("Satellite reader"))],
        ["Scan", scan.replace(/^scan /, ""), { mono: true }],
      ]),
      el("details", { class: "dk-about", dataset: { k: `sat-pic-${vid}` } },
        el("summary", { dataset: { focus: `sat-pic-${vid}` } }, icon("i-chevron-right", "icon dk-about__chev"), el("span", { text: "Show the picture" })),
        el("div", { class: "dk-about__body dk-about__body--flush" },
          frameView(reading, frame),
          el("p", { class: "dk-sub__note", text: n ? (placed ? "Boxes are placed on the map by code from the picture's bounds." : "These boxes sit on the picture only: it has no map position, so none is drawn on the map.") : "No box was drawn." }),
          reading.limits ? el("blockquote", { class: "x-quote" }, el("p", { text: reading.limits }), aiMark(reading.model_id, reading.label, MARK.read("Satellite reader"))) : aiMark(reading.model_id, reading.label, MARK.read("Satellite reader")),
          colourKey())),
      reading.note ? el("p", { class: "dk-sub__note", text: reading.note }) : null,
      readByCode(reading) ? null : dkTech(`read by ${reading.model_id}`),
    ],
  });
}

function satPanel(D, store) {
  const readings = store.snapshot?.satellite || [];
  const list = readings.slice().sort((a, b) => (a.volcano_id === D.selected ? -1 : 0) - (b.volcano_id === D.selected ? -1 : 0));
  const stub = D.state.llm?.backend === "stub";
  const bad = readings.filter((r) => r.status === "ai_unavailable").length;
  const head = dkHeader({
    id: "sat-head",
    pills: [dkPill("info", "Supporting evidence only"), bad ? dkPill("caution", `${bad} not read`) : null],
    title: stub ? "The newest Himawari picture for each active volcano, read by a code stub while TEPHRA Assistant is off." : "Newest Himawari picture per active volcano · supporting only",
    sub: "Supporting evidence only. It never changes the official area, TEPHRA's estimate, the heights or an advisory.",
  });
  // pictures the assistant did not read: that they are missing, what holds, and "Why ›" (8.6)
  const missing = bad ? dkNote("caution", [el("p", {}, `${bad === 1 ? "1 picture was" : `${bad} pictures were`} not read. Nothing was put in ${bad === 1 ? "its" : "their"} place, and the official area stands. `, whyLink("sat-why"))], { role: "status" }) : null;
  const body = list.length
    ? [missing, dkList(list.map((r) => satRow(D, r, D.sits.find((s) => s.volcano_id === r.volcano_id), store)), { first: 4, key: "sat" })]
    : dkEmpty("No satellite reading yet", "A reading appears when a new picture arrives for an active volcano.");
  return [dkSection("sat-head", head, body)];
}

const capFirst = (t) => (t ? t[0].toUpperCase() + t.slice(1) : t);

// ------------------------------------------------------------------ Notices

const LANG = { en: "EN", id: "ID", ja: "JA", fil: "FIL" };
const LANG_NAME = { EN: "English", ID: "Indonesian", JA: "Japanese", FIL: "Filipino" };
const langBadge = (code) => el("span", { class: "lang", title: LANG_NAME[LANG[code]] || "Another language" }, LANG[code] || "??");

const isJma = (n) => n.source_kind === "jma_xml";

function noticeState(n) {
  if (isJma(n)) return ["ok", "Verified", "Read by code from JMA's published XML. No model was used."];
  if (n.status === "verified") return ["ok", "Verified", "Every claim was found word for word in the notice and checked by code."];
  if (n.status === "ai_unavailable") return ["caution", "Not read (Notice reader gave no result)", "Read this notice yourself."];
  return ["caution", "Not verified", n.reason || "A check failed, so nothing from this notice entered the picture."];
}

// A JMA report comes from /api/notices like a pasted notice but was parsed by code from JMA's XML:
// its fields carry no quoted evidence and no model is named.
function noticeRow(n, modeReplay) {
  const [tone, word, why] = noticeState(n);
  const title = isJma(n) ? `JMA · ${n.vona?.volcano_name || "volcano report"}` : "Pasted notice";
  const fields = (n.fields || []).map((f) => [capFirst(f.name.replace(/_/g, " ")), el("span", {}, el("span", { class: "mono", text: f.derived || f.value }), f.evidence ? [" ", el("q", { class: "x-fields__ev", text: f.evidence })] : null)]);
  return dkRow({
    key: `notice-${n.id}`, dot: tone, edge: n.status === "ai_unavailable" ? "caution" : null,
    title: [langBadge(n.language), " ", title, n.replay && !modeReplay ? [" ", dkFromReplay(n.replay, modeReplay)] : null],
    sub: `${word}${n.fields?.length ? ` · ${plural(n.fields.length, "claim")}` : ""}`,
    meta: el("span", { class: "mono", text: clock(n.created_at) }),
    body: [
      el("p", { class: "dk-sub__note", text: `${LANG_NAME[LANG[n.language]] || "Another language"}. ${why}` }),
      n.status === "ai_unavailable" ? dkNote("caution", "Not read (Notice reader gave no result): read this notice yourself. Nothing from it entered the picture.", { role: "status" }) : null,
      n.status === "unverified" ? dkNote("caution", (n.reason || "Could not be verified.").replace(/^NOT VERIFIED:\s*/i, "")) : null,
      fields.length ? dkFacts(fields) : null,
      n.problems?.length ? el("ul", { class: "x-problems" }, ...n.problems.map((p) => el("li", { text: p }))) : null,
      !isJma(n) && n.status !== "ai_unavailable" ? aiMark(n.model_id, n.label, MARK.read("Notice reader")) : null,
      isJma(n) ? dkTech(n.id) : n.status === "ai_unavailable" ? dkTech(String(n.reason || "no reason given")) : null,
    ],
  });
}

function noticesPanel(D) {
  if (!ext.loaded.notices) return [loadingBox()];
  if (ext.errors.notices) return [dkNote("caution", `Notices unavailable: ${ext.errors.notices}`, { role: "status" })];
  const all = ext.notices.slice().sort((a, b) => ms(b.created_at) - ms(a.created_at));
  const pasted = all.filter((n) => !isJma(n));
  const jma = all.filter(isJma);
  const verified = all.filter((n) => isJma(n) || n.status === "verified").length;
  const notV = all.length - verified;
  const newest = all[0];
  const head = dkHeader({
    id: "notices-head",
    pills: newest ? [dkPill(noticeState(newest)[0], `Newest: ${noticeState(newest)[1]}`)] : [],
    title: all.length ? `${all.length} notice${all.length === 1 ? "" : "s"} · newest ${clock(newest.created_at)}` : "No notices yet",
    sub: "A notice only enters the picture once every claim is found word for word in it.",
  });
  if (!all.length) return [dkSection("notices-head", head, dkEmpty("Nothing to show", "Paste a notice on the Desk (EN, ID, JA or FIL) and it shows up here.", el("a", { class: "link-btn", href: "/desk", target: "_blank", rel: "noopener", text: "Open the Desk ›" })))];
  const tiles = dkTiles([
    { label: "Notices", value: String(all.length) },
    { label: "Verified", value: String(verified), tone: verified ? "ok" : null },
    { label: "Not verified", value: String(notV), tone: notV ? "caution" : null },
  ], "Notices in numbers");
  const modeReplay = D?.mode === "REPLAY";
  const row = (n) => noticeRow(n, modeReplay);
  const newestRows = all.slice(0, 3).map(row);
  const rest = all.slice(3);
  const more = rest.length ? el("details", { class: "dk-about", dataset: { k: "notices-all" } }, el("summary", { dataset: { focus: "notices-all" } }, icon("i-chevron-right", "icon dk-about__chev"), el("span", { text: `All notices and their claims (${all.length})` })),
    el("div", { class: "dk-about__body dk-about__body--flush" },
      pasted.length ? dkGroup(`Pasted notices · ${pasted.length}`, null, dkList(pasted.map(row), { first: 5, key: "notices-pasted" })) : null,
      jma.length ? dkGroup(`JMA reports · ${jma.length}`, null, dkList(jma.map(row), { first: 5, key: "notices-jma" })) : null)) : null;
  return [dkSection("notices-head", head, tiles, dkGroup("Newest", null, dkList(newestRows, { key: "notices-new" })), more)];
}

// ------------------------------------------------------------------ Recovery board

const PLAN_STATUS = {
  DRAFT: ["caution", "Waiting for a dispatcher"], APPROVED: ["ok", "Approved"], REJECTED: ["serious", "Rejected"],
  SUPERSEDED: ["off", "Superseded"], AI_UNAVAILABLE: ["caution", "No plan"],
};
const LEVEL = (ft) => (ft == null ? "?" : ft <= 0 ? "SFC" : `FL${String(Math.round(ft / 100)).padStart(3, "0")}`);

// The plan in one line, for the summary and the Details index (R8.3 `recovery`).
export function recoverySummary(plan) {
  if (!plan) return null;
  const fail = planFailure(plan);
  if (fail) return `${fail.title}. ${fail.sub}`;
  const icaos = [...new Set(plan.closures.map((c) => c.icao))];
  const tops = plan.closures.filter((c) => c.top_ft != null);
  const band = tops.length ? ` ${LEVEL(Math.min(...tops.map((c) => c.base_ft ?? 0)))}/${LEVEL(Math.max(...tops.map((c) => c.top_ft)))}` : "";
  const r = plan.closures.find((c) => c.radius_nm != null)?.radius_nm;
  const head = `${icaos.join(", ")} closed by ash (all volcanoes)${band}${r != null ? ` within ${Math.round(r)} NM` : ""}`;
  const t = plan.chosen?.totals;
  const what = t ? `cancel ${t.cancelled_flights}${t.delayed_flights ? `, delay ${t.delayed_flights}` : ""}, ${usd(t.total_usd)}` : "no scenario chosen";
  const status = plan.status === "DRAFT" ? "Plan waiting on the Desk" : plan.status === "APPROVED" ? "Plan approved" : plan.status === "REJECTED" ? "Plan rejected" : "Plan";
  return `${head} · ${status}: ${what}`;
}

// Airports a re-plan is running for (review 1, item 5): the newest airport-plan step in the trace
// says the closed airports changed and the recovery helper started, and no plan has landed since.
// Read from the trace's own fields; null when no re-plan is running.
const REPLAN = /^Closed airports changed: (.+); recovery agent started$/;
export function replanning(store) {
  let last = null;
  for (const t of store?.trace || []) if (t.stage === "RECOVERY" && (!last || ms(t.at) >= ms(last.at))) last = t;
  const m = last ? REPLAN.exec(last.message || "") : null;
  if (!m) return null;
  const at = ms(last.at);
  if (ext.recovery.some((p) => ms(p.created_at) >= at)) return null;
  const airports = Array.isArray(last.detail?.airports) && last.detail.airports.length ? last.detail.airports : m[1].split(/,\s*/);
  return { airports, at };
}

const SOLVER_WORD = { OPTIMAL: "best plan found", FEASIBLE: "workable plan found", UNKNOWN: "solver gave no answer", INFEASIBLE: "no plan fits", NO_PLAN: "no plan found" };
const solverWords = (sc) => SOLVER_WORD[sc.solver_status] || SOLVER_WORD[sc.status] || String(sc.status || "").toLowerCase().replace(/_/g, " ");
// "CLOSURE AS FORECAST" -> "Closure as forecast" (the Desk's wording).
const scenarioName = (label) => {
  const t = String(label || "").toLowerCase();
  return t.charAt(0).toUpperCase() + t.slice(1);
};

function recoveryPanel(D, store) {
  const re = replanning(store);
  const busy = re ? dkNote("info", el("p", {}, el("span", { class: "spinner", "aria-hidden": "true" }), ` Re-planning for ${re.airports.join(", ")}…`), { role: "status", cls: "x-busy" }) : null;
  if (!ext.loaded.recovery) return [loadingBox()];
  if (ext.errors.recovery) return [dkNote("caution", `Airport plan unavailable: ${ext.errors.recovery}`, { role: "status" })];
  const plans = ext.recovery.slice().sort((a, b) => ms(b.created_at) - ms(a.created_at));
  const plan = plans.find((p) => p.status !== "SUPERSEDED") || plans[0];
  if (!plan) {
    return [dkSection("rec-head", dkHeader({ id: "rec-head", pills: [re ? dkPill("info", "Re-planning") : dkPill("ok", "No airport closed")], title: re ? "Closed airports changed: a new plan is on its way." : "No RFA airport is closed by the ash right now." }), busy)];
  }
  const [tone, word] = PLAN_STATUS[plan.status] || ["info", plan.status];
  const fail = planFailure(plan);
  const icaos = [...new Set(plan.closures.map((c) => c.icao))];
  const t = plan.chosen?.totals;
  const title = `${plural(icaos.length, "airport")} closed by ash (all volcanoes): ${icaos.join(", ")}.`;
  const what = fail ? `${fail.title}. ${fail.sub}` : t ? `${plan.status === "DRAFT" ? "Plan waiting on the Desk" : plan.status === "APPROVED" ? "Plan approved" : plan.status === "REJECTED" ? "Plan rejected" : "Plan"}: cancel ${t.cancelled_flights}${t.delayed_flights ? `, delay ${t.delayed_flights}` : ""}, ${usd(t.total_usd)}.` : "No scenario chosen.";
  // "Chosen by TEPHRA Assistant" only when a model chose the plan; with no plan the "No plan" pill
  // says it once
  const chosenBy = plan.outcome === "STUB" ? dkChip("Planned by code (code only)") : plan.chosen ? aiMark(plan.model_id, null, MARK.chosen) : null;
  // the re-plan the budget holds for later, at the place it changes (D58)
  const queued = fail ? waitingWork().find((w) => w.status === "WAITING" && w.item?.kind === "RECOVER") : null;
  const head = dkHeader({
    id: "rec-head",
    pills: [dkPill(tone, word), dkFromReplay(plan.replay, D.mode === "REPLAY")],
    title, sub: fail ? null : what,
    chips: [dkChip(clock(plan.created_at), { label: "As of" }), chosenBy, dkChip(String(plan.version), { label: "Plan version" })],
  });
  const kids = [head, busy];
  if (fail) {
    kids.push(dkList([dkRow({ key: "rec-fail", dot: "caution", edge: "caution", title: fail.title, sub: fail.sub, open: false, body: [dkTech(fail.raw)] })], { key: "rec-fail" }));
    // that it waits, not when: the slot is said at the assistant's home (UI-AI-QUIET 8.6)
    if (queued) kids.push(dkNote("info", [el("p", {}, `A new plan waits in line for ${ASSISTANT}. `, whyLink("rec-why"))], { role: "status" }));
    // no plan because the assistant did not run or gave no result: the cause is one tap away (8.6)
    else if (fail.ai) kids.push(el("p", { class: "dk-foot" }, whyLink("rec-why")));
  }
  // closed airports: a row each; the full reason and its sources are one tap further in
  kids.push(dkGroup(`Closed airports, all volcanoes · ${plan.closures.length}`, null, dkList(plan.closures.map((c) => dkRow({
    key: `rec-ap-${c.icao}-${c.start}`, dot: "serious", title: c.icao, titleMono: true, sub: c.summary || null,
    foot: el("span", { class: "mono", text: `${clock(c.start)} – ${c.open_ended ? "open" : clock(c.end)}` }),
    body: [dkFacts([["Closed from", clock(c.start), { mono: true }], ["Until", c.open_ended ? "open-ended" : clock(c.end), { mono: true }], ["Heights", c.top_ft != null ? `${LEVEL(c.base_ft ?? 0)}–${LEVEL(c.top_ft)}` : null, { mono: true }], ["Radius", c.radius_nm != null ? `${Math.round(c.radius_nm)} NM` : null]]),
      el("details", { class: "tech x-closure__more" }, el("summary", { text: "Full reason and sources" }),
        el("p", { class: "tech__line mono", text: machineText(c.reason) }),
        c.source_ids?.length ? el("p", { class: "tech__line mono", text: c.source_ids.join(" · ") }) : null)],
  })), { first: 4, key: "rec-airports" })));
  if (plan.disruption) {
    const d = plan.disruption;
    kids.push(dkGroup("Before re-planning", "what the closures block", dkTiles([
      { label: "Flights blocked", value: d.blocked_flights.length.toLocaleString("en"), tone: d.blocked_flights.length ? "caution" : null, sub: `${d.blocked_pax.toLocaleString("en")} passengers on them` },
      { label: "Flights the plan can change", value: String(d.free_flights), sub: `${d.frozen_flights.toLocaleString("en")} more already departed` },
    ], "Disruption in numbers"), d.airborne_at_risk?.length ? dkNote("caution", `In the air and at risk: ${d.airborne_at_risk.join(", ")}`) : null));
  }
  const chosen = plan.chosen;
  if (chosen) {
    const tt = chosen.totals;
    kids.push(dkGroup(`Chosen scenario: ${scenarioName(chosen.label)}`, `${solverWords(chosen)} in ${Math.round(chosen.solve_ms / 1000)} s`,
      tt ? dkTiles([
        { label: "Cancelled", value: String(tt.cancelled_flights), tone: tt.cancelled_flights ? "serious" : null },
        { label: "Delayed", value: String(tt.delayed_flights), tone: tt.delayed_flights ? "caution" : null },
        { label: "Passengers affected", value: tt.pax_affected.toLocaleString("en") },
        { label: "Total cost", value: usd(tt.total_usd) },
        { label: "Kept", value: String(tt.kept_flights) },
        { label: "Swapped", value: String(tt.swapped_flights) },
      ], "Chosen scenario in numbers") : null));
  } else if (plan.status !== "AI_UNAVAILABLE") kids.push(dkEmpty("No scenario chosen.", null));
  if (plan.scenarios.length > 1) {
    const rows = plan.scenarios.map((sc) => el("tr", { class: sc.id === plan.chosen_scenario_id ? "is-chosen" : null },
      el("th", { scope: "row" }, sc.id === plan.chosen_scenario_id ? [icon("i-check", "icon"), " "] : null, scenarioName(sc.label), sc.id === plan.chosen_scenario_id ? el("span", { class: "sr-only", text: " (chosen)" }) : null),
      el("td", { class: "num", text: sc.totals ? String(sc.totals.cancelled_flights) : "–" }),
      el("td", { class: "num", text: sc.totals ? String(sc.totals.delayed_flights) : "–" }), el("td", { class: "num", text: sc.totals ? usd(sc.totals.total_usd) : sc.solver_status === "UNKNOWN" ? "no plan (solver did not finish)" : solverWords(sc) })));
    kids.push(dkAbout(`Compare the scenarios (${plan.scenarios.length})`, "rec-scen", el("div", { class: "x-tablewrap" }, el("table", { class: "x-table" }, el("caption", { class: "sr-only", text: "Recovery scenarios" }),
      el("thead", {}, el("tr", {}, el("th", { scope: "col", text: "Scenario" }), el("th", { scope: "col", class: "num", text: "Cancel" }), el("th", { scope: "col", class: "num", text: "Delay" }), el("th", { scope: "col", class: "num", text: "Cost" }))),
      el("tbody", {}, ...rows)))));
  }
  if (plan.rationale) kids.push(dkAbout("Why this plan", "rec-why", el("p", { class: "dk-quote", text: plainLine(plan.rationale) }), aiMark(plan.model_id, plan.outcome === "STUB" ? "NO MODEL" : null, "Explained by Recovery planner"), techDetail(plan.rationale, plan.chosen && plan.outcome !== "STUB" ? `chosen by ${plan.model_id}` : null)));
  if (plan.risks?.length) kids.push(dkAbout(`Risks (${plan.risks.length})`, "rec-risks", el("ul", { class: "dk-bullets" }, ...plan.risks.map((r) => el("li", { text: r })))));
  const decided = plan.decided_at ? `${plan.status === "REJECTED" ? "Rejected" : "Approved"} by ${(plan.decided_by || "a dispatcher").replace(/^desk:/, "")} at ${hhmmz(ms(plan.decided_at))}` : null;
  kids.push(dkNote(plan.status === "APPROVED" ? "info" : "info", decided || (plan.status === "DRAFT" ? "Waiting for a dispatcher. Nothing is sent anywhere." : fail ? "No plan to decide on. Nothing is sent anywhere." : "No decision."), { iconId: plan.status === "APPROVED" ? "i-approved" : "i-dispatcher" }));
  if (plans.length > 1) kids.push(el("p", { class: "dk-foot", text: `${plans.length - 1} earlier plan${plans.length === 2 ? "" : "s"} not shown.` }));
  return [dkSection("rec-head", kids)];
}

// ------------------------------------------------------------------ Proof

const ARM = { D: "Baseline: code only", G: "With the Plume reader (Gemini)" };
const ARM_SHORT = { D: "baseline", G: "with the Plume reader" };

function armStats(arm, s, lead) {
  const gain = s.coverage_gain_mean;
  const l = (lead || [])[0];
  return dkGroup(ARM[arm] || `Arm ${arm}`, null, dkTiles([
    { label: "Coverage gain vs official", value: gain == null ? "n/a" : `${gain >= 0 ? "+" : ""}${(gain * 100).toFixed(2)} pts` },
    { label: "Over-warning", value: pct(s.overwarn_mean, 0) },
    { label: "Area vs official", value: s.excess_vs_official_mean == null ? "n/a" : `${s.excess_vs_official_mean.toFixed(2)}×` },
    { label: "Median lead", value: l?.median_min == null ? "n/a" : `${Math.round(l.median_min)} min`, sub: l ? `${l.n_covered_before_official} of ${l.n_footprints} earlier` : null },
    { label: "Top level reached", value: pct(s.vertical_hit_rate, 0) },
    { label: "Moments scored", value: s.ticks_scored.toLocaleString("en") },
  ], `${ARM[arm] || arm} in numbers`),
  arm === "D" ? el("p", { class: "dk-sub__note", text: "The zone equals the official area and the gain is zero by design: it checks the safety floor and the scoring." }) : null);
}

export function proofTicks() {
  const b = ext.backtest;
  if (!b?.overall) return null;
  return Object.values(b.overall).reduce((n, a) => n + (a.ticks_scored || 0), 0);
}

const meterRow = (label, value, tone) => el("div", { class: "dk-meterrow" },
  el("div", { class: "dk-meterrow__top" }, el("span", { text: label }), el("strong", { class: "mono", text: pct(value) })),
  dkMeter({ value: value == null ? 0 : value * 100, max: 100, tone, label: `${label} ${pct(value)}` }));

function proofPanel() {
  if (!ext.loaded.backtest) return [loadingBox()];
  // the backtest is one group of the record; the scorecard groups below it stand on their own
  if (ext.errors.backtest) return [dkSection("proof-head", dkNote("caution", `Backtest unavailable: ${ext.errors.backtest}`, { role: "status" }), plumeScorecard(), speedAndCost())];
  const b = ext.backtest;
  const arms = Object.keys(b.overall || {});
  const ticks = proofTicks() || 0;
  const head = dkHeader({
    id: "proof-head",
    pills: [arms.includes("G") ? dkPill("ok", "Plume reader scored") : dkPill("caution", "Baseline only")],
    title: "How TEPHRA's area compares with the official areas issued later, scored by code on recorded replays.",
  });
  const kids = [head,
    dkNote("caution", [el("p", {}, el("strong", { text: "Later official areas are not ash truth." })), "TEPHRA is scored against the official areas issued after each moment. Those are partly built from the same reports and satellite data, so this measures agreement, not what the ash did."], { role: "note" }),
    dkTiles([
      { label: "Official area missed", value: String(b.floor_violations), of: " times", tone: b.floor_violations === 0 ? "ok" : "serious", sub: b.floor_violations === 0 ? "always kept it all" : "left part of one out" },
      { label: "Later data used", value: String(b.input_leaks), of: " times", tone: b.input_leaks === 0 ? "ok" : "serious", sub: b.input_leaks === 0 ? "a fair test" : "not a fair test" },
      { label: "Moments scored", value: ticks.toLocaleString("en"), sub: `in ${plural(b.cases.length, "case")}` },
    ], "Checks"),
  ];
  for (const a of arms) {
    kids.push(dkGroup(ARM[a] || `Arm ${a}`, null, el("div", { class: "dk-card" },
      meterRow("Area TEPHRA covers of later official areas", b.overall[a].coverage_mean, "tephra"),
      meterRow("Area the official area alone covers", b.overall[a].coverage_official_mean, "official"))));
  }
  if (!arms.includes("G")) kids.push(dkNote("info", "Baseline only: code, no model call. The Gemini Plume reader has not been scored yet, so no improvement is claimed."));
  kids.push(plumeScorecard(), speedAndCost());
  const rows = b.cases.map((c) => el("tr", {},
    el("th", { scope: "row" }, el("span", { class: "x-case__name", text: c.label.split(":")[0] }), el("span", { class: "x-case__meta mono", text: `${c.case_id} · ${ARM_SHORT[c.arm] || `arm ${c.arm}`}` })),
    el("td", { class: "num", text: pct(c.summary.coverage_mean) }), el("td", { class: "num", text: pct(c.summary.coverage_official_mean) }),
    el("td", { class: "num", text: pct(c.summary.overwarn_mean, 0) }), el("td", { class: "num", text: c.summary.ticks_scored.toLocaleString("en") })));
  kids.push(el("div", { class: "dk-abouts" },
    dkAbout("Every number", "proof-more", ...arms.map((a) => armStats(a, b.overall[a], (b.overall_lead || {})[a]))),
    dkAbout(`Per case (${b.cases.length})`, "proof-cases", el("div", { class: "x-tablewrap" }, el("table", { class: "x-table x-table--cases" }, el("caption", { class: "sr-only", text: "Backtest results per case" }),
      el("thead", {}, el("tr", {}, el("th", { scope: "col", text: "Case" }), el("th", { scope: "col", class: "num", text: "TEPHRA" }), el("th", { scope: "col", class: "num", text: "Official" }), el("th", { scope: "col", class: "num", text: "Over-warn" }), el("th", { scope: "col", class: "num", text: "Moments" }))),
      el("tbody", {}, ...rows)))),
    dkAbout(`Caveats (${(b.caveats || []).length})`, "proof-caveats", el("ul", { class: "dk-bullets" }, ...(b.caveats || []).map((c) => el("li", { text: machineSentences(c) }))))),
  el("p", { class: "dk-foot mono", text: `Scored by code · generated ${clock(b.generated_at)} · every case is a recorded replay` }));
  return [dkSection("proof-head", kids)];
}

// The Plume reader's scorecard (docs/evals/plume-scorecard.json through /api/evals): the counts the
// file holds, its own verdict as the pill, the case it missed by name, and what was not run.
const scoreWord = (v) => (String(v || "").split(" ")[0] || "INCOMPLETE").toUpperCase();
const SCORE_TONE = { PASS: "ok", FAIL: "serious" };
function plumeScorecard() {
  if (!ext.loaded.evals) return dkGroup("Plume reader scorecard", null, loadingBox());
  const p = ext.evals?.plume;
  if (ext.errors.evals || !p) return dkGroup("Plume reader scorecard", null, dkNote("info", `Not loaded: ${ext.errors.evals || "no scorecard file"}.`));
  const a = p.arm_i || {};
  const cases = Array.isArray(a.cases) ? a.cases : [];
  const n = a.existence?.cases ?? cases.length;
  const verdict = scoreWord(a.verdicts?.existence);
  const withDirection = cases.filter((c) => c.direction && c.direction !== "n/a").length;
  const missed = cases.filter((c) => c.class && c.call && (c.class === "ash" ? c.call !== "ash" : c.call === "ash")).map((c) => c.id);
  const notRun = Array.isArray(p.incomplete) ? p.incomplete : [];
  return dkGroup(`Plume reader on ${n} Tokyo VAAC cases`, p.model ? `${p.runs || 1} runs each` : null,
    el("div", { class: "dk-head__pills" }, dkPill(SCORE_TONE[verdict] || "caution", verdict, a.verdicts?.existence || null)),
    dkTiles([
      { label: "Ash seen or not", value: `${a.existence?.correct ?? "n/a"}/${n}`, sub: "called as the official report did" },
      { label: "Same answer every run", value: `${a.stability?.agreeing ?? "n/a"}/${a.stability?.cases ?? n}` },
      { label: "Direction", value: `${a.direction?.detected_within_45_deg ?? "n/a"} of ${withDirection}`, sub: "within 45°" },
      { label: "False alarms", value: String(a.existence?.quiet_high_confidence_ash ?? "n/a"), tone: a.existence?.quiet_high_confidence_ash === 0 ? "ok" : null, sub: "quiet pictures called ash" },
    ], "Plume reader scorecard"),
    missed.length ? dkNote("caution", `Missed: ${missed.join(", ")}.`) : null,
    dkNote("info", [`Texts (Semeru): ${p.arm_t ? "scored" : "not run"}.`, ...notRun.map((t) => `${t}.`)]));
}

// Speed and cost on the demo replay (docs/evals/replay-metrics.json): "n/a · not measured" where
// the file has no figure, never a guess.
function speedAndCost() {
  const m = ext.loaded.evals && !ext.errors.evals ? ext.evals?.replay_metrics : null;
  const speed = m?.speed?.median_minutes;
  const tokens = m?.tokens;
  const notMeasured = { value: "n/a", sub: "not measured" };
  return dkGroup("Speed and cost", null, dkTiles([
    { label: "Speed", ...(Number.isFinite(speed) ? { value: `${speed} min`, sub: `median to a draft · ${m.speed.label || "replay clock"}` } : notMeasured) },
    { label: "Cost", ...(tokens && typeof tokens === "object" && Number.isFinite(tokens.total) ? { value: `${tokens.total.toLocaleString("en")} tokens`, sub: tokens.label || null } : notMeasured) },
  ], "Speed and cost"));
}

// ------------------------------------------------------------------ Runs on (Details › Behind the scenes)

// Where this service runs (SystemState.cloud): code-written facts only, no model ids.
export function runsRows(state) {
  const c = state?.cloud;
  if (!c) return [];
  const store = c.store === "firestore" ? "Firestore" : "SQLite";
  const secrets = c.secrets === "secret-manager" ? "Secret Manager" : "Secrets from the environment";
  const model = { "gemini-api": "Gemini API", "ollama-local": "Gemma on this computer (Ollama)" }[c.model_access] || "No model connected (NO MODEL)";
  if (c.platform !== "cloud-run") {
    return [["Runs on", `This computer · ${store} · ${c.scheduler === "cloud-scheduler" ? "Cloud Scheduler" : "in-process scheduler"}`], ["Secrets", secrets], ["Model access", model]];
  }
  const build = state.build_sha ? ` · build ${String(state.build_sha).slice(0, 7)}` : "";
  return [
    ["Runs on", `Cloud Run · ${c.region || "region not set"}`],
    ["Revision", `${c.revision || "unknown"}${build}`],
    ["Record store", store],
    ["Scheduler", c.scheduler === "cloud-scheduler" ? "Cloud Scheduler · every minute" : "In-process scheduler"],
    ["Secrets", secrets],
    ["Model access", model],
    ["Writers", "One instance, one writer"],
  ];
}

// The audit chain's state for the footer and Runs on: "intact" only when this instance walked the
// chain and found it whole; "checking" before that walk; its problems when the walk found some.
export function auditLine(audit) {
  if (!audit) return { text: "Audit chain: checking", tone: "info", problems: [] };
  if (audit.intact) return { text: `Audit chain intact · ${plural(audit.entries, "entry", "entries")}`, tone: "ok", problems: [] };
  const problems = (audit.problems || []).filter((p) => !/not yet walked/i.test(p));
  if (!problems.length) return { text: "Audit chain: checking", tone: "info", problems: [] };
  return { text: `Audit chain: ${plural(problems.length, "problem")}`, tone: "serious", problems };
}

export const runsStatus = (state) => (!state ? "loading…" : !state.cloud ? "not reported" : state.cloud.platform === "cloud-run" ? `Cloud Run · ${state.cloud.region || "region not set"}` : "This computer");

function runsPanel(D, store) {
  const state = store.state;
  const rows = runsRows(state);
  const cloud = state?.cloud?.platform === "cloud-run";
  const head = dkHeader({ id: "runs-head", pills: [rows.length ? dkPill(cloud ? "ok" : "info", cloud ? "Google Cloud" : "Local run") : dkPill("info", "Not reported")], title: "Where this TEPHRA runs and where it keeps its record." });
  if (!rows.length) return [dkSection("runs-head", head, dkEmpty("This server does not say where it runs.", null))];
  const audit = auditLine(state.audit);
  return [dkSection("runs-head", head, dkFacts(rows), dkNote(audit.tone, audit.text, { role: "status" }), audit.problems.length ? techDetail(...audit.problems) : null)];
}

// ------------------------------------------------------------------ TEPHRA Assistant (docs/UI-DETAILS-PANELS.md 3; the AI helpers)

// The skills are board.js's roster (one table for the names, shared with TEPHRA Assistant at work),
// less the hidden features' skills, plus the backtest, which is code and calls no model. Read when
// drawn: the features arrive with the first state.
export const agents = () => [
  ...HELPERS.filter((h) => !h.feature || has(h.feature)).map(({ id, name, stage, does, skip, only }) => ({ id, name, stage, what: does, skip, only })),
  { id: "backtest", name: "Backtest", stage: null, what: "Scores TEPHRA against later official areas (code, no model)" },
];
// The Coordinator (duty officer) tool that reaches each specialist.
const DELEGATED_VIA = { plume: "assess_volcanoes", sat: "assess_volcanoes", planner: "plan_flights", drafter: "plan_flights", recovery: "run_recovery", sra: "draft_sra" };
const RUNNING_MS = 6000;

const STATE_ORDER = { failed: 0, waiting: 1, running: 2, done: 3, idle: 4 };

// The one AI state for the Wall (docs/UI-AI-QUIET.md 1.2): the chip, the story, Details and the
// map all word their assistant lines from it. Assistant steps that failed in the trace the Wall
// holds, the newest Coordinator run, the newest airport plan and the live budget.
export function aiState(D, store) {
  return aiStateOf({ stub: D?.state?.llm?.backend === "stub", budget: ext.budget, errors: aiErrorsOf(store?.trace), duty: store?.snapshot?.duty || null, plan: newestPlan(ext.recovery), replay: D?.mode === "REPLAY" });
}

// Flights to plan by hand (docs/UI-AI-QUIET.md D56), with the Wall's AI state.
export const handPlan = (D, store, ai = aiState(D, store)) => handPlanOf(D, store, ai);

// Each helper's state from facts, not only from the newest trace steps (D70): a plume read the
// Coordinator holds, the newest airport plan, the budget's queue and the newest run.
export function agentStatus(D, store, ai) {
  const trace = store.trace || [];
  const nowT = performance.now();
  const run = store.snapshot?.duty;
  const delegated = dispatchedTools(run);
  const plans = ext.recovery.slice().sort((a, b) => ms(b.created_at) - ms(a.created_at));
  const plan = plans.find((p) => p.status !== "SUPERSEDED") || null;
  const pf = planFailure(plan);
  const sra = ai.waiting.find((w) => w.kind === "SRA");
  const pending = (D?.sits || []).filter((x) => x.assessment?.outcome === "PENDING").length;
  return agents().map((a, i) => {
    if (!a.stage) {
      const ok = ext.backtest && !ext.errors.backtest;
      return { ...a, i, state: ok ? "done" : "idle", count: ok ? ext.backtest.cases.length : 0, last: ok ? ext.backtest.generated_at : null, detail: ok ? `${ext.backtest.cases.length} cases scored` : "Not run yet" };
    }
    const mine = trace.filter((t) => t.stage === a.stage && (!a.skip || !a.skip.test(t.message)) && (!a.only || a.only.test(t.message)));
    const last = mine[mine.length - 1];
    const fails = mine.filter((t) => t.level === "error").length;
    let state = "idle", words = null, badge = null, at = last?.at || null;
    if (last) state = last.level === "error" ? "failed" : nowT - (ext.arrivals.get(last.id) ?? -1e9) < RUNNING_MS ? "running" : "done";
    // the badge says what happened ("Not run" only where no model was called); `words` says why,
    // without repeating the badge (review H6)
    // the time is said once, in the lead above (review clutter 7)
    const paused = (cls) => (cls === "budget" ? (ai.paused ? `${ASSISTANT} paused` : WHY.budget) : `gave no result (${WHY[cls] || WHY.other})`);
    if (a.id === "duty" && run?.outcome === "MODEL_FAILED") {
      const cls = reasonClass((run.validation_errors || [])[0]);
      state = "failed"; badge = cls === "budget" ? "Not run" : "No brief"; words = paused(cls); at = at || run.finished_at;
    } else if (a.id === "plume" && pending) { state = "waiting"; words = "plume read queued for the Coordinator"; }
    else if (a.id === "recovery" && pf?.ai) { state = "failed"; badge = pf.cls === "budget" ? "Not run" : "No plan"; words = paused(pf.cls); at = plan.created_at; }
    // its own slot only when it is not the reset the lead already says (the time once)
    else if (a.id === "sra" && sra) { state = "waiting"; words = sra.slot && sra.slot !== ai.slotAt ? `next slot ${sra.slot}` : "waiting in line"; }
    else if (state === "failed") { const cls = reasonClass(last.message); badge = cls === "budget" ? "Not run" : cls === "undone" ? "Left for the Desk" : "No result"; words = cls === "undone" ? "must-do jobs passed to the Desk" : paused(cls); }
    return { ...a, i, state, words, badge, count: mine.length, fails, last: at, detail: last?.message || null, delegated: delegated.has(DELEGATED_VIA[a.id]) };
  });
}

// Never red: an assistant step that did not run is a caution; the picture keeps the red (Q4).
const STATE_UI = {
  idle: ["never", "Quiet"], running: ["running", "Working on it"], done: ["ok", "Done"], failed: ["caution", "Not run"], waiting: ["caution", "Waiting"],
};

const LANE_WORDS = { urgent: "Urgent", interactive: "Desk", routine: "Routine" };
const TIER_WORDS = { main: "Main", lite: "Lite", tts: "Speech" };

// What one queued job is doing, in the assistant's words. The server's reason ("waiting for AI
// budget, next slot 0700Z") is not shown: the next slot is said from next_slot_at, as the time
// left in REPLAY (a real-clock time would read as a time on the recording's clock).
// `reset`: the daily reset the lead already says (ms); a job whose slot is that reset (or a slot
// already behind the real clock) says only that it waits, so the time is said once.
function workWords(w, replay, reset = NaN) {
  if (w.status === "RUNNING") return "running now";
  if (w.status === "QUEUED") return `queued for ${ASSISTANT}`;
  const at = ms(w.next_slot_at);
  const slot = realWhen(at, Date.now(), replay);
  if (!slot?.at || Math.abs(at - reset) < 60000) return "waiting in line";
  return `waiting for the next slot, ${replay ? slot.at : `at ${slot.at}`}`;
}

const waitingWork = () => (Array.isArray(ext.budget?.waiting) ? ext.budget.waiting : []);

// Assistant work the worker holds: running, queued, or waiting for its model's next paced slot.
function waitingBlock(replay, reset) {
  const work = waitingWork();
  if (!work.length) return null;
  return el("div", { class: "dk-sub" },
    el("p", { class: "dk-sub__title", text: "Assistant work queued or waiting" }),
    dkFacts(work.map((w) => [w.lane === "urgent" ? "Urgent" : "Routine", `${w.label}: ${workWords(w, replay, reset)}`])),
    el("p", { class: "dk-sub__note", text: "Waiting work is kept and runs on the same model when its slot comes. Nothing is dropped or handed to another model." }));
}

// The budget meters never use the picture's red (Q4): a low or closed model is a caution.
const budgetTone = (left, stub, closed) => (closed ? "caution" : meterTone(left, stub) === "serious" ? "caution" : meterTone(left, stub));

// Free-tier calls per model, with a meter each (`x-tier`), the share each kind of work has and
// the pacing in words, in "Models and today's calls".
function budgetBlock(replay, ai = null) {
  if (!ext.loaded.budget) return loadingBox();
  if (ext.errors.budget || !ext.budget) return dkNote("caution", `Budget unavailable: ${ext.errors.budget || "no answer"}`, { role: "status" });
  const b = ext.budget;
  const stub = b.backend === "stub";
  const models = Array.isArray(b.models) ? b.models : [];
  const resets = ms(b.resets_at);
  // when counts start again, on the real clock (the time left in REPLAY), unless the lead already
  // says when a paused assistant opens again (the time once)
  const when = realWhen(resets, Date.now(), replay);
  const counts = when?.at && !(ai?.kind === "paused" && ai.until) ? ` Counts start again ${replay ? when.at : `at ${when.at}`}.` : "";
  return el("div", { class: "x-budget" },
    stub ? el("p", { class: "dk-sub__note", text: "Offline stub: no model is called, so no quota is spent." }) : null,
    ...models.map((m) => {
      const left = m.limit ? m.remaining / m.limit : 0;
      const lanes = (m.lanes || []).map((l) => `${LANE_WORDS[l.lane] || l.lane} ${l.used} of ${l.share}`).join(" · ");
      return el("div", { class: "x-tier" },
        el("div", { class: "x-tier__top" }, el("span", { class: "x-tier__name" }, el("strong", { text: jobsWords(m.jobs) }), dkChip(m.model_id, { mono: true })),
          el("span", { class: "mono", text: m.closed ? `Closed for today by Google (${m.remaining} of ${m.limit} unused)` : `${m.remaining} left of ${m.limit}` })),
        dkMeter({ value: m.remaining, max: m.limit, tone: budgetTone(left, stub, m.closed), label: `${jobsWords(m.jobs)}: ${m.remaining} of ${m.limit} calls left${m.closed ? ", closed for today by Google" : ""}` }),
        lanes ? el("p", { class: "dk-sub__note mono", text: lanes }) : null,
        stub ? null : el("p", { class: "dk-sub__note", text: pacingWords(m.pacing) }));
    }),
    waitingBlock(replay, resets),
    el("p", { class: "dk-sub__note", text: `${b.note || ""}${counts}`.trim() }));
}

const liteTier = () => ext.budget?.tiers?.find((t) => t.tier === "lite") || ext.budget?.tiers?.[0] || null;
const usedOf = (t) => (Number.isFinite(t.used) ? t.used : Math.max(0, t.limit - t.remaining));

// Assistant work waiting for its model's next paced slot, and the first such slot in words.
function waitingTail() {
  const waiting = waitingWork().filter((w) => w.status === "WAITING");
  if (!waiting.length) return "";
  const next = waiting.map((w) => w.reason).find((r) => r && r.includes("next slot"));
  return `${waiting.length} job${waiting.length === 1 ? "" : "s"} ${next || "waiting for the next slot"}`;
}

// The lite model's calls today (D65). While Google has closed it, the tile says so first, so
// "1 of 450" never reads as calls to spare.
function budgetTile(stub, ai) {
  const lite = liteTier();
  if (!lite) {
    return { label: "Assistant calls today", value: ext.loaded.budget ? "unknown" : "loading…", sub: ext.errors.budget ? `budget unavailable: ${ext.errors.budget}` : null, wide: true, tone: ext.errors.budget ? "caution" : null };
  }
  const main = ext.budget.tiers.find((t) => t.tier === "main" && t !== lite);
  const closed = (ext.budget.models || []).find((m) => m.model_id === lite.model_id)?.closed === true;
  const used = usedOf(lite);
  const left = lite.limit ? lite.remaining / lite.limit : 0;
  const waiting = ai.waiting.length ? `${ai.waiting.length} job${ai.waiting.length === 1 ? "" : "s"} waiting` : null;
  if (closed) {
    return {
      label: "Assistant calls today", value: "Closed for today", wide: true, tone: "caution",
      meter: { value: used, max: lite.limit, tone: "caution", label: `Assistant calls today: ${used} of ${lite.limit} used, closed for today by Google` },
      sub: [`Google closed the free quota after ${used.toLocaleString("en")} of ${lite.limit.toLocaleString("en")} calls`, waiting].filter(Boolean).join(" · "),
    };
  }
  return {
    label: "Assistant calls today", value: used.toLocaleString("en"), of: ` of ${lite.limit.toLocaleString("en")}`, wide: true,
    meter: { value: used, max: lite.limit, tone: budgetTone(left, stub, false), label: `Assistant calls today: ${used} of ${lite.limit} used` },
    sub: stub ? "Offline stub: no quota is spent" : [waitingTail() || null, main ? `Plume reader ${usedOf(main)} of ${main.limit}` : null, "resets at midnight Pacific"].filter(Boolean).join(" · "),
  };
}

// What a cause means for the dispatcher, under its title in What went wrong.
function causeSub(c, range) {
  if (c.helperKey === "duty" && c.reasonClass !== "undone") return `${range ? `${range} must-do ${range === "1" ? "job" : "jobs"} per run` : "Its must-do jobs"} went to the Desk, for a dispatcher to plan by hand. Nothing was substituted.`;
  if (c.reasonClass === "undone") return "A dispatcher does them by hand. Nothing was substituted.";
  if (c.helperKey === "recovery") return "No plan was made. A dispatcher must plan the network by hand.";
  if (c.helperKey === "plume") return c.steps ? "TEPHRA's area stays at the official reports. Nothing was widened or substituted." : "Until its calls reset, TEPHRA's area stays at the official reports. Nothing is widened or substituted.";
  return `Nothing was put in its place. ${c.consequence}.`;
}

// Assistant steps that did not run, one row per cause (D67): the cause in the §1.1 words, how many runs
// and when, where to act; every run and its raw line one tap in behind "Show the N runs".
function causeRows(causes) {
  return causes.map((c) => {
    const occ = c.items.map((x) => ({ t: x.at, ...(x.src?.stage ? failureEach(x.src) : { each: c.reasonClass === "timeout" ? "timed out" : plainLine(String(x.reason || "")), num: null }) }))
      .sort((a, b) => (b.t || 0) - (a.t || 0));
    const nums = occ.map((x) => x.num).filter((v) => v != null);
    const lo = nums.length ? Math.min(...nums) : null, hi = nums.length ? Math.max(...nums) : null;
    const range = lo == null ? null : lo === hi ? String(lo) : `${lo}–${hi}`;
    const when = Number.isFinite(c.first) ? timeRange(c.first, c.last) : null;
    return dkRow({
      key: `fail-${c.key}`, dot: "caution", edge: "caution", title: causeTitle(c, { home: true }), sub: causeSub(c, range), foot: dkWhen(c.steps, when),
      body: [
        c.link ? dkLink(c.link[0], { act: "details-sec", sec: c.link[1], focus: `fail-go-${c.key}` }) : null,
        occ.length ? dkList(occ.map((x) => el("div", { class: "dk-occ" }, el("span", { class: "dk-occ__t mono", text: Number.isFinite(x.t) ? hhmmz(x.t) : "" }), el("span", { class: "dk-occ__x", text: x.each }))),
          { first: c.steps > 1 ? 0 : 1, key: `fail-occ-${c.key}`, more: `Show the ${c.steps} runs` }) : null,
        dkTech(...c.raw),
      ],
    });
  });
}

function helperRow(a, store, n, stub, until, replay) {
  const [tone, word] = STATE_UI[a.state];
  const last = ms(a.last);
  const run = store.snapshot?.duty;
  let lastT = last;
  if (a.id === "duty" && run && !Number.isFinite(lastT)) lastT = ms(run.decided_at || run.finished_at);
  // "Quiet" only for a helper that is quiet; a row with a badge and no time shows no time
  const meta = Number.isFinite(lastT) ? el("span", { class: "mono", text: hhmmz(lastT) }) : a.state === "idle" ? el("span", { text: "Quiet" }) : null;
  const sub = [a.what, a.words, a.delegated ? "given a job by the Coordinator" : null].filter(Boolean).join(" · ");
  const badge = a.state === "failed" || a.state === "waiting" ? a.badge || word : null;
  let body;
  if (a.id === "duty") {
    body = [...dutyDetail(run, !!store.snapshot, until, replay), a.detail ? dkTech(`newest step: ${a.detail}`) : null];
  } else if (a.id === "backtest") {
    body = [dkFacts([["Status", a.state === "done" ? "Done: scored by code, no model" : "Not run yet"], ["Cases scored", a.state === "done" ? String(a.count) : null], ["Generated", Number.isFinite(last) ? dayTime(last) : null, { mono: true }]]),
      dkLink("Track record ›", { act: "details-sec", sec: "proof", focus: "helper-proof" })];
  } else {
    const status = a.words ? `${badge}: ${a.words}` : a.state === "idle" ? `Quiet: not seen in the newest ${n} steps` : a.state === "running" ? "Working on it" : a.state === "failed" ? badge : "Its newest step worked";
    const seen = a.count ? ` · ${plural(a.count, "step")}${a.fails ? `, ${a.fails} did not run` : ""} in the newest ${n}` : "";
    body = [dkFacts([
      ["Status", `${status}${seen}`],
      ["Last step", a.detail ? plainLine(a.detail) : null],
      ["Model", stub ? "Code only (assistant off): code follows the skill's script" : null],
    ]), a.detail ? dkTech(`${a.stage} · ${a.detail}`) : null];
  }
  return dkRow({ key: `helper-${a.id}`, dot: tone, title: a.name, sub, meta, body, badge });
}

// The state pill at the assistant home (D64): one state, never red.
export function aiPill(ai) {
  if (ai.kind === "off") return dkPill("off", "Off · code only");
  // the time is in the lead beside it, said once (review clutter 7)
  if (ai.kind === "paused") return dkPill("caution", "Paused");
  if (ai.kind === "trouble") return dkPill("caution", `On · ${plural(ai.trouble.length, "problem")}`);
  return dkPill("ok", "On");
}

function aiPanel(D, store) {
  const ai = aiState(D, store);
  const agents = agentStatus(D, store, ai);
  const run = store.snapshot?.duty;
  const stub = D.state.llm?.backend === "stub";
  const n = (store.trace || []).length;
  const tiers = ext.budget?.tiers || [];
  const ids = tiers.length ? tiers.map((t) => [TIER_WORDS[t.tier] || t.tier, t.model_id]) : String(D.state.llm?.label || "").split(" + ").filter(Boolean).map((id, i) => [i ? "Lite" : "Main", id]);
  const jobsN = run ? (run.dispatches || []).length : null;
  const runT = run ? ms(run.decided_at || run.finished_at) : NaN;

  const head = dkHeader({
    id: "ai-head",
    pills: [aiPill(ai)],
    title: stub ? "Code does every step, and code templates write the text a model would." : `${assistantIs()} Its skills can widen TEPHRA's estimate but never shrink the official area.`,
    chips: stub ? [dkChip("No model (offline stub)")] : ids.map(([k, id]) => dkChip(id, { label: k, mono: true })),
    extra: el("div", { class: "dk-actions" }, el("button", { type: "button", class: "btn btn--small", dataset: { act: "board-open", focus: "ai-board" }, "aria-keyshortcuts": "A" }, icon("ta-16"), `See ${ASSISTANT} at work`)),
  });
  // the calm lead (5.1): what state the assistant is in, what still holds, where the hand work is
  const lead = el("div", { class: "dk-lead", role: "status" }, ...aiLead(ai).map((p) => el("p", {}, el("strong", { text: p.strong }), ` ${p.text}`)));
  const tiles = dkTiles([
    budgetTile(stub, ai),
    { label: "Jobs handed out", value: jobsN == null ? "none yet" : String(jobsN), tone: jobsN == null ? "never" : null, sub: run ? `latest Coordinator run${Number.isFinite(runT) ? `, ${hhmmz(runT)}` : ""}` : "no Coordinator run yet" },
  ], "TEPHRA Assistant in numbers");

  const kids = [head, lead, tiles];
  if (ai.causes.length) {
    const steps = ai.causes.reduce((k, c) => k + c.steps, 0);
    kids.push(el("div", { id: "ai-fails", tabindex: "-1", class: "dk-anchor" }, dkGroup("What went wrong", `${plural(ai.causes.length, "cause")} · ${plural(steps, "step")}`,
      dkList(causeRows(ai.causes), { first: 3, key: "ai-fails" }),
      el("p", { class: "dk-foot" }, "Nothing was made up in their place. ", dkLink("See them in How TEPHRA decided ›", { act: "details-sec", sec: "trace", focus: "ai-trace" })))));
  }

  const order = agents.slice().sort((a, b) => STATE_ORDER[a.state] - STATE_ORDER[b.state] || a.i - b.i);
  const active = order.filter((a) => a.state !== "idle").length;
  const first = Math.min(6, active) || 3;
  const quiet = order.length - first;
  kids.push(dkGroup("Skills", `${active} of ${agents.length} active`,
    dkList(order.map((a) => helperRow(a, store, n, stub, null, D.mode === "REPLAY")), { first, key: "ai-helpers", more: order.slice(first).every((a) => a.state === "idle") ? `Show quiet skills (${quiet})` : `Show all ${order.length} skills` })));

  kids.push(el("div", { class: "dk-abouts" },
    dkAbout("Models and today's calls", "ai-budget", budgetBlock(D.mode === "REPLAY", ai))));
  return [dkSection("ai-head", kids)];
}

// ------------------------------------------------------------------ Details sections hosted in #xpanel

export const XSECTIONS = { sat: satPanel, notices: noticesPanel, recovery: recoveryPanel, proof: proofPanel, ai: aiPanel, runs: runsPanel };

export function renderXPanel(key, D, store) {
  const panel = $("xpanel");
  const build = XSECTIONS[key];
  if (!build || !D) return;
  panel.dataset.panel = key;
  panel.replaceChildren(...build(D, store).filter(Boolean));
}

// ------------------------------------------------------------------ a reroute, inside Details › This flight

export function rerouteBlock(props, D) {
  const kind = props.kind === "REJOIN_TRACK" ? "Go around, then rejoin the track" : "Direct to destination";
  const plus = [props.extra_nm != null ? `+${Math.round(props.extra_nm)} NM` : null, props.extra_min != null ? `+${Math.round(props.extra_min)} min` : null].filter(Boolean).join(" · ");
  const wps = Array.isArray(props.waypoint_labels) ? props.waypoint_labels : [];
  const ok = !props.status || /^OK$/i.test(String(props.status));
  return dkList([dkRow({
    key: "reroute", dot: icon("i-route", "icon", "var(--c-reroute, var(--c-info))"), edge: ok ? null : "caution",
    title: "Suggested reroute", sub: ok ? kind : `${kind} · ${String(props.status).toLowerCase().replace(/_/g, " ")}`, meta: plus || null,
    body: [
      el("p", { class: "dk-sub__note", text: "Computed by code around TEPHRA's estimate · a draft route for the dispatcher" }),
      dkFacts([["Kind", kind], ["Side", props.side ? props.side.toLowerCase() : null], ["Extra distance", props.extra_nm != null ? `+${Math.round(props.extra_nm)} NM` : null, { mono: true }],
        ["Extra time", props.extra_min != null ? `+${Math.round(props.extra_min)} min` : null, { mono: true }], ["Status", props.status ? String(props.status).toLowerCase().replace(/_/g, " ") : null],
        ["Turn points", wps.length ? wps.join("  ") : null, { mono: true }]]),
      props.route_string ? el("p", { class: "pop__route mono", text: props.route_string }) : null,
    ],
  })], { key: "reroute" });
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
