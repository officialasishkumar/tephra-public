// Onboarding (SPEC-v2 §6): the landing at /onboard, nine pages at /onboard/<page> (one topic per
// page, saved in this browser as you go), the account at the end and the recovery code at
// /onboard/done. Signed in while the airline is pending, /onboard/<page>?edit=1 edits the stored
// answers instead. Pages move with the history API; focus goes to each page's h1. Every string
// goes in through el() (textContent).

import { $, el, icon, inlineSprite } from "./wall/util.js";
import { applyFeatureNav, has, setFeatures } from "./wall/features.js";
import { formatValue, policyValues } from "./wall/policy.js";
import { initAccountNav } from "./account-nav.js";
import {
  ANSWER_PAGES, DEFAULT_OLLAMA_URL, airportCode, checkedValues, FLEET_FILE_MAX_BYTES, KEY_POLICY_VALUES, PAGES, PAGE_KEYS, PROVIDE, SCHEDULE_FILE_MAX_BYTES,
  cautionsOf, checkPage, checkSchedule, emptyValues, fileLine, fromAnswers, hexOf, isEditablePolicyValue, mapServerProblem,
  pageOf, parseFleetFile, ruleMessage, toAnswers, upper,
} from "./onboard/pages.js";
import { caret, choiceCards, chipsInput, fid, field, illus, input, listError, notBuilt, note, section, segmented, setError, setListError } from "./onboard/form.js";
import { clearDraft, clearOnboardStorage, draftSaver, loadDraft, loadLocal } from "./onboard/draft.js";
import { accountForm, passwordAside, recoveryCard, reviewList } from "./onboard/review.js";
import { COUNTRIES } from "./onboard/countries.js";
import { envLines } from "./workspace/kit.js";
import { modelChoice } from "./workspace/assistant.js";
import { ACCOUNTS_OFF, ONBOARD_OFF, PATHS, call, errorCode, minutesWords, problemsOf, retryMinutes } from "./workspace/api.js";

const MAX_BODY_BYTES = 128 * 1024;
const ROWS_STEP = 50;
const WIDE = window.matchMedia("(min-width: 1280px)");
const blankDraft = () => ({ v: 2, seen: [], at: null, values: emptyValues() });
// replaceChildren prints a null slot as "null": the optional parts are dropped first.
const put = (node, ...kids) => node.replaceChildren(...kids.flat().filter((k) => k != null && k !== false));

const S = {
  state: null, accounts: false, policy: null, named: {}, labels: {}, airports: new Map(), known: null, positions: null,
  draft: blankDraft(), local: { ollama_url: null, files: {} },
  edit: null, saved: null, flagged: new Set(), leaveAnyway: null, anywayFor: null, server: {}, recovery: null, envBefore: null,
  fleetShown: ROWS_STEP, fleetTab: "type", navMode: null, account: null,
};

const V = () => S.draft.values;
const ctxFor = (key) => ({ named: S.named, ollamaUrl: S.local.ollama_url ?? DEFAULT_OLLAMA_URL, schedule: key === "schedule" ? scheduleCheck() : null });

// --- saving -----------------------------------------------------------------------------------------

const SAVED_WORDS = {
  ok: ["i-check", "Saved in this browser"],
  quota: ["i-check", "Saved in this browser · not your schedule files (too large)"],
  blocked: ["st-caution", "Not saved: this browser blocks storage"],
};

// The status line changes only when the saved state changes (a status region re-reads what is
// written into it).
function setSaved(state) {
  if (S.edit || state === S.saved) return;
  S.saved = state;
  const [shape, words] = SAVED_WORDS[state];
  $("ob-saved").replaceChildren(icon(shape), el("span", { text: words }));
  $("ob-saved").dataset.state = state;
}

const saver = draftSaver(setSaved);

function changed() {
  if (S.edit) return;
  saver.schedule(S.draft, S.local);
  drawAside();
}

// --- loading ----------------------------------------------------------------------------------------

async function loadContext() {
  const [state, session, policy, airports] = await Promise.all([call(PATHS.state), call(PATHS.session), call(PATHS.policy), call(PATHS.airports)]);
  S.state = state.ok ? state.data : null;
  setFeatures(S.state?.features);
  applyFeatureNav();
  S.accounts = Boolean(session.ok && session.data?.accounts);
  if (policy.ok && policy.data?.policy) {
    S.policy = policy.data.policy;
    for (const g of policyValues(S.policy)) {
      for (const r of g.rows) {
        S.named[r.id] = { value: r.raw.value, unit: r.raw.unit };
        S.labels[r.id] = r.label;
      }
    }
  }
  if (airports.ok) {
    for (const f of airports.data?.features || []) {
      const p = f.properties || {};
      if (p.icao) S.airports.set(p.icao, { name: p.name, iata: p.iata, at: f.geometry?.coordinates });
    }
    S.known = new Set(S.airports.keys());
    S.positions = Object.fromEntries([...S.airports].filter(([, a]) => Array.isArray(a.at)).map(([k, a]) => [k, a.at]));
  }
}

// --- routing ----------------------------------------------------------------------------------------

function route() {
  const key = location.pathname.replace(/\/+$/, "").split("/")[2] || "";
  const edit = new URLSearchParams(location.search).get("edit") === "1";
  if (key === "done") return { view: "done" };
  if (PAGE_KEYS.includes(key)) return { view: "page", key, edit: edit && key !== "review" };
  return { view: "landing" };
}

function go(path) {
  history.pushState(null, "", path);
  render();
}

const pageHref = (key) => `/onboard/${key}${S.edit ? "?edit=1" : ""}`;

function frame(view) {
  document.body.dataset.view = view;
  const page = view === "page";
  $("ob-progress-row").hidden = !page;
  $("ob-steps").hidden = !page;
  $("ob-actions").hidden = !page;
  $("ob-aside").hidden = !page;
}

function focusHeading() {
  const h = $("main").querySelector("h1");
  if (!h) return;
  h.tabIndex = -1;
  h.focus();
  window.scrollTo(0, 0);
}

function announce(text) {
  const a = $("announcer");
  a.textContent = "";
  window.setTimeout(() => {
    a.textContent = text;
  }, 60);
}

// --- the step list and the progress row -------------------------------------------------------------

const problemCount = (key) => checkPage(key, V(), ctxFor(key)).length + (S.server[key]?.length || 0);

function stepState(key, current) {
  if (key === current) return "now";
  if (key === "review" || (!S.edit && !S.draft.seen.includes(key))) return "todo";
  return problemCount(key) ? "warn" : "done";
}

function stepList(states) {
  return el("ol", {}, ...PAGES.filter((p) => !S.edit || p.key !== "review").map((p) => {
    const st = states[p.key];
    const n = st === "warn" ? problemCount(p.key) : 0;
    const mark = st === "done" ? icon("i-check") : st === "warn" ? icon("st-caution") : el("span", { text: String(p.n) });
    const inner = [
      el("span", { class: "n", "aria-hidden": "true" }, mark),
      el("span", { class: "steps__t" },
        el("span", { text: p.name }),
        st === "done" ? el("span", { class: "sr-only", text: " (done)" }) : null,
        st === "warn" ? el("span", { class: "flag", text: n === 1 ? "1 thing to check" : `${n} things to check` }) : null),
    ];
    const reachable = S.edit || st === "now" || S.draft.seen.includes(p.key);
    return el("li", { class: `is-${st}` }, reachable
      ? el("a", { href: pageHref(p.key), "aria-current": st === "now" ? "step" : null, dataset: { go: p.key } }, ...inner)
      : el("span", { class: "steps__plain" }, ...inner));
  }));
}

function drawSteps(current) {
  const states = Object.fromEntries(PAGES.map((p) => [p.key, stepState(p.key, current)]));
  const done = Object.values(states).filter((s) => s === "done").length;
  const foot = S.edit
    ? el("div", { class: "steps__foot" }, el("p", { text: "Changes are saved to your workspace with Save changes." }))
    : el("div", { class: "steps__foot" },
      el("p", { text: "Answers stay in this browser until you create your account on Review." }),
      el("button", { type: "button", class: "linkbtn", dataset: { act: "clear" }, text: "Clear my answers" }));
  $("ob-steps").replaceChildren(
    el("h2", { class: "eyebrow steps__h", text: S.edit ? "Edit your answers" : "Onboard your airline" }),
    el("details", { class: "steps__phone" }, el("summary", {}, el("span", { text: `All pages · ${done} of ${S.edit ? 8 : 9} done` }), caret()), stepList(states)),
    el("div", { class: "steps__wide" }, stepList(states)),
    foot);
  const page = pageOf(current);
  $("ob-step").replaceChildren(...(S.edit
    ? [el("b", { text: "Editing your answers" }), " · Pending verification"]
    : [el("b", { text: `Step ${page.n} of 9` }), ` · ${page.name}`]));
  $("ob-progress").replaceChildren(...PAGES.map((p) => el("i", { class: p.key === current ? "is-now" : states[p.key] === "todo" ? null : "is-done" })));
}

// --- the aside: the setup kit so far ----------------------------------------------------------------

function drawAside() {
  const box = $("ob-aside-code");
  if (!box) return;
  const checked = { ...S.draft, values: checkedValues(V(), ctxFor) };
  const lines = envLines(toAnswers(checked), { positions: S.positions, regions: S.state?.regions, known: S.known, ollamaUrl: S.local.ollama_url || DEFAULT_OLLAMA_URL });
  const before = S.envBefore;
  S.envBefore = new Set(lines);
  box.replaceChildren(...lines.map((line) => el("span", { class: [line.startsWith("#") ? "c" : "", before && !before.has(line) ? "new" : ""].join(" ").trim() || null, text: `${line}\n` })));
  if (!before) return;
  // The box is shorter than the file: bring the first line this answer added into view.
  const added = box.querySelector(".new");
  if (added) box.scrollTop += added.getBoundingClientRect().top - box.getBoundingClientRect().top - 8;
  window.setTimeout(() => box.querySelectorAll(".new").forEach((n) => n.classList.remove("new")), 2000);
}

function aside() {
  const details = el("details", { class: "card aside-card kitsofar", open: WIDE.matches || null },
    el("summary", {}, icon("i-file"), el("span", { text: "Your setup kit so far" }), caret()),
    el("p", { text: "The airline.env lines your answers add. The kit is made in your workspace after you create your account; its secrets are made when you download it." }),
    el("pre", { id: "ob-aside-code", class: "code", tabindex: "0", "aria-label": "airline.env so far" }));
  WIDE.onchange = () => {
    details.open = WIDE.matches || details.open;
  };
  return details;
}

// --- problems on the page ---------------------------------------------------------------------------

function showProblems(key, { only = null } = {}) {
  const problems = checkPage(key, V(), ctxFor(key));
  const byId = new Map();
  for (const p of problems) if (!byId.has(fid(p.field))) byId.set(fid(p.field), p.message);
  for (const p of S.server[key] || []) if (p.field && !byId.has(fid(p.field))) byId.set(fid(p.field), p.text);
  if (only) {
    const c = document.getElementById(only);
    if (c) setError(c, byId.get(only) || null);
    return problems;
  }
  const main = $("main");
  for (const c of main.querySelectorAll("[aria-invalid]")) setError(c, null);
  for (const e of main.querySelectorAll("[data-list]")) setListError(e.dataset.list, null);
  for (const [id, message] of byId) {
    const c = document.getElementById(id);
    if (c && c.matches("input, select, textarea")) setError(c, message);
    else setListError(id, message);
  }
  return problems;
}

function focusFirstProblem() {
  const main = $("main");
  const bad = main.querySelector('[aria-invalid="true"]');
  if (bad) {
    bad.focus();
    return;
  }
  const err = main.querySelector(".err:not([hidden])");
  err?.closest(".section, .field")?.querySelector("input, select, textarea, button")?.focus();
}

const listErr = (field) => {
  const node = listError(fid(field));
  node.dataset.list = fid(field);
  return node;
};

// A text control bound to one answer; an error shown under it is re-checked as the person types.
function bound(control, get, set, page) {
  control.value = get() ?? "";
  control.addEventListener("input", () => {
    set(control.value);
    delete S.server[page];
    if (control.getAttribute("aria-invalid") === "true") showProblems(page, { only: control.id });
    changed();
  });
  return control;
}

const upperAsTyped = (c) => c.addEventListener("input", () => {
  const at = c.selectionStart;
  c.value = c.value.toUpperCase();
  c.setSelectionRange(at, at);
});

// --- page 1 · Airline ------------------------------------------------------------------------------

function airlinePage() {
  const a = V().airline;
  const t = (key, attrs = {}, { up = false, after = null } = {}) => {
    const c = bound(input(attrs), () => a[key], (v) => {
      a[key] = up ? v.toUpperCase() : v;
      if (after) after(v);
    }, "airline");
    if (up) upperAsTyped(c);
    return c;
  };
  const callsign = t("callsign_prefix", { mono: true, maxlength: 3 }, { up: true, after: () => { a.callsign_touched = true; } });
  const icao = t("icao", { mono: true, maxlength: 3 }, { up: true, after: (v) => {
    if (a.callsign_touched) return;
    a.callsign_prefix = v.toUpperCase();
    callsign.value = a.callsign_prefix;
  } });
  const baseHint = el("span", {});
  const nameBase = () => {
    const ap = S.airports.get(upper(a.main_base));
    baseHint.textContent = ap ? `ICAO airport code · ${ap.name}` : "ICAO airport code";
  };
  const base = t("main_base", { mono: true, maxlength: 4 }, { up: true, after: nameBase });
  nameBase();
  return [
    section("Name and designators", "s-names",
      field({ id: fid("airline.name"), label: "Airline name", control: t("name", { autocomplete: "organization", maxlength: 120 }) }),
      el("div", { class: "row3" },
        field({ id: fid("airline.icao"), label: "ICAO designator", hint: "3 letters", control: icao }),
        field({ id: fid("airline.iata"), label: "IATA code", optional: true, hint: "2 letters or digits", control: t("iata", { mono: true, maxlength: 2 }, { up: true }) }),
        field({ id: fid("airline.callsign_prefix"), label: "Callsign prefix", hint: "What your flights file as, e.g. RFA1654", control: callsign }))),
    section("Where you operate from", "s-where",
      el("div", { class: "row2" },
        field({ id: fid("airline.state_of_operator"), label: "State of the Operator", hint: "The State that issued your Air Operator Certificate (AOC)", control: t("state_of_operator", { list: "ob-countries", maxlength: 60, autocomplete: "country-name" }) }),
        field({ id: fid("airline.main_base"), label: "Main base", hint: baseHint, control: base })),
      field({ id: fid("airline.aoc_number"), label: "AOC number", optional: true, hint: "As printed on your Air Operator Certificate. A TEPHRA dispatcher checks it when verifying.", control: t("aoc_number", { mono: true, maxlength: 40 }) }),
      el("datalist", { id: "ob-countries" }, ...COUNTRIES.map((n) => el("option", { value: n })))),
    section("Operations contact", "s-contact",
      el("p", { class: "section__sub", text: "The address a TEPHRA dispatcher writes to when verifying your airline." }),
      el("div", { class: "row2" },
        field({ id: fid("airline.ops_email"), label: "Operations email", control: t("ops_email", { type: "email", autocomplete: "email", inputmode: "email", maxlength: 254, spellcheck: "false" }) }),
        field({ id: fid("airline.contact_name"), label: "Contact name", optional: true, control: t("contact_name", { autocomplete: "name", maxlength: 80 }) }))),
    note("info", null, "A TEPHRA dispatcher verifies every airline. Until then nothing runs under your name."),
  ];
}

// --- page 2 · Ash policy ---------------------------------------------------------------------------

const UNIT = { NM: "NM", ft: "ft", min: "min", m: "m", kt: "kt", deg: "°", FL: "FL", count: "", s: "s", USD: "USD" };

function valueRow(name, label) {
  const base = S.named[name];
  const changes = V().policy.changes;
  const id = fid(`policy.v.${name}`);
  const rid = fid(`policy.r.${name}`);
  const num = input({ mono: true, inputmode: "numeric", autocomplete: "off", maxlength: 6, value: changes[name] ? changes[name].value : String(base.value) });
  num.classList.add("input--num");
  const reason = el("textarea", { class: "input textarea", rows: "2", maxlength: "300" });
  reason.value = changes[name]?.reason || "";
  const reasonField = field({ id: rid, label: "Why this value? (your SRA section)", hint: "3 to 300 characters", control: reason });
  const isChanged = () => Boolean(changes[name]) && Number(changes[name].value) !== Number(base.value);
  num.addEventListener("input", () => {
    const v = num.value.trim();
    if (v === String(base.value)) delete changes[name];
    else changes[name] = { ...(changes[name] || {}), value: v, base: base.value, unit: base.unit, reason: reason.value };
    reasonField.hidden = !isChanged();
    delete S.server.policy;
    if (num.getAttribute("aria-invalid") === "true") showProblems("policy");
    changed();
  });
  reason.addEventListener("input", () => {
    if (changes[name]) changes[name].reason = reason.value;
    if (reason.getAttribute("aria-invalid") === "true") showProblems("policy", { only: rid });
    changed();
  });
  reasonField.hidden = !isChanged();
  return el("div", { class: "pval" },
    field({ id, label, hint: `Policy A: ${formatValue(name.split(".")[1], base)}`, control: num,
      slot: el("div", { class: "pval__in" }, num, el("span", { class: "pval__unit", "aria-hidden": "true", text: UNIT[base.unit] ?? base.unit })) }),
    reasonField);
}

function policyPage() {
  const p = V().policy;
  const out = [
    choiceCards({
      name: "ob-preset", legend: "Policy", value: "A", onChange: () => {},
      options: [
        { value: "A", title: "Policy A · avoid every official ash area", text: "Plan around every official ash area, merged, up to its highest top, with your margins.", chips: [illus()] },
        { value: "B", title: "Policy B · through, under or over", text: "Plan through, under or over where your safety risk assessment allows.", chips: [illus(), notBuilt()], disabled: true, reason: "No TEPHRA code applies a Policy B preset. The flight planner may still propose a level clear of the ash under Policy A." },
      ],
    }),
  ];
  if (!S.policy) {
    out.push(note("caution", null, "Can't load Policy A's values from this server. Reload to try again.", { role: "status" }));
  } else {
    const shown = new Set(KEY_POLICY_VALUES.map(([n]) => n));
    const more = Object.keys(S.named).filter((n) => isEditablePolicyValue(n) && !shown.has(n));
    const recovery = Object.keys(S.named).filter((n) => !isEditablePolicyValue(n));
    out.push(section("Margins", "s-margins",
      ...KEY_POLICY_VALUES.filter(([n]) => S.named[n]).map(([n, label]) => valueRow(n, label)),
      el("details", { class: "more", open: more.some((n) => p.changes[n]) || null },
        el("summary", {}, el("span", { text: `More values (${more.length})` }), caret()),
        el("div", { class: "more__body" }, ...more.map((n) => valueRow(n, S.labels[n] || n)))),
      el("details", { class: "more" },
        el("summary", {}, el("span", { text: `Recovery values (${recovery.length})` }), notBuilt(), caret()),
        el("div", { class: "more__body" },
          el("p", { class: "hint", text: "Only recovery re-planning reads these, and it is not built for your network." }),
          el("dl", { class: "kv" }, ...recovery.flatMap((n) => [el("dt", { text: S.labels[n] || n }), el("dd", { class: "mono", text: formatValue(n.split(".")[1], S.named[n]) })]))))));
  }
  out.push(
    section("Who owns it", "s-owner",
      el("div", { class: "row2" },
        field({ id: fid("policy.risk_owner"), label: "Risk owner", hint: "The post accountable for this policy in your safety management system.", control: bound(input({ placeholder: "e.g. Director of Flight Operations", maxlength: 80 }), () => p.risk_owner, (v) => { p.risk_owner = v; }, "policy") }),
        field({ id: fid("policy.sra_ref"), label: "Your SRA reference", optional: true, hint: "Document id and revision. Needed once any value changes.", control: bound(input({ mono: true, maxlength: 120 }), () => p.sra_ref, (v) => { p.sra_ref = v; }, "policy") }))),
    note("info", null, "Your policy file keeps the label ILLUSTRATIVE, not an airline SRA: TEPHRA cannot check an SRA. It records your numbers, your reasons and your SRA reference."));
  return out;
}

// --- page 3 · Fleet --------------------------------------------------------------------------------

// [key, label, input attributes, upper-case as typed, optional]
const FLEET_COLS = [
  ["registration", "Registration", { mono: true, maxlength: 10 }, true, false],
  ["type_icao", "Type", { mono: true, maxlength: 4 }, true, false],
  ["seats", "Seats", { inputmode: "numeric", maxlength: 4 }, false, false],
  ["home_base", "Home base", { mono: true, maxlength: 4 }, true, true],
  ["hex", "Hex address", { mono: true, maxlength: 8 }, false, true],
];
const OPTIONAL = " (optional)";

function fleetRow(row, i, { onEdit, onRemove }) {
  const cells = FLEET_COLS.map(([key, label, attrs, up, optional]) => {
    const id = fid(`fleet.aircraft.${i}.${key}`);
    const c = input({ ...attrs, value: row[key] ?? "", autocomplete: "off", "aria-label": `${label}, aircraft ${i + 1}${optional ? OPTIONAL : ""}` });
    c.id = id;
    c.setAttribute("aria-describedby", `${id}-err${key === "seats" ? " fleet-seats-hint" : ""}`);
    if (up) upperAsTyped(c);
    c.addEventListener("input", () => {
      row[key] = up ? c.value.toUpperCase() : c.value.trim().toLowerCase();
      if (c.getAttribute("aria-invalid") === "true") showProblems("fleet", { only: id });
      onEdit();
    });
    return el("td", { class: key === "registration" ? "wide" : null, dataset: { l: optional ? `${label}${OPTIONAL}` : label } }, c, el("p", { id: `${id}-err`, class: "err", hidden: true }));
  });
  const remove = el("button", { type: "button", class: "rowdel", "aria-label": `Remove ${row.registration || `aircraft ${i + 1}`}` }, icon("i-x"));
  remove.addEventListener("click", () => onRemove(i));
  return el("tr", {}, ...cells, el("td", {}, remove));
}

function fleetUpload(f, take) {
  const result = el("div", { class: "upres", role: "status" });
  const file = el("input", { type: "file", id: "fleet-file", accept: ".csv,.json,text/csv,application/json", class: "sr-only" });
  file.addEventListener("change", async () => {
    const one = file.files?.[0];
    file.value = "";
    if (!one) return;
    if (one.size > FLEET_FILE_MAX_BYTES) result.replaceChildren(note("caution", null, "This file is larger than 512 KB."));
    else take(await one.text(), one.name, result);
  });
  const paste = el("textarea", { class: "input textarea mono", rows: "5", spellcheck: "false", placeholder: "registration,type,seats,home_base,hex" });
  const read = el("button", { type: "button", class: "btn btn--secondary", text: "Read the pasted rows" });
  read.addEventListener("click", () => take(paste.value, "pasted.csv", result));
  return el("div", { class: "upload" },
    el("div", { class: "drop" },
      el("span", { class: "drop__ic" }, icon("i-file")),
      el("p", {}, el("b", { text: "A CSV, or the kit's fleet.json" }), el("br"), "Read in this browser, nothing is uploaded. CSV columns: registration, type, seats, home base, hex (header optional, comma or tab)."),
      el("label", { class: "btn btn--secondary", for: "fleet-file" }, icon("i-file"), el("span", { text: "Choose a file" })), file),
    field({ id: "fleet-paste", label: "Or paste rows", control: paste }),
    el("div", { class: "tool" }, read,
      el("button", { type: "button", class: "linkbtn", dataset: { act: "tpl-fleet-csv" }, text: "Download the header row (.csv)" }),
      el("button", { type: "button", class: "linkbtn", dataset: { act: "tpl-fleet-json" }, text: "Download an empty fleet.json" })),
    result);
}

function fleetPage() {
  const f = V().fleet;
  const check = el("dl", { class: "kv kv--mono" });
  const drawCheck = () => {
    const prefixes = [V().airline.callsign_prefix, ...(f.extra_prefixes || [])].map(upper).filter(Boolean);
    const hexes = f.aircraft.map((r) => hexOf(r.hex)).filter(Boolean);
    const bad = f.aircraft.filter((r) => r.hex && ruleMessage("fleet.hex", r.hex)).length;
    const shownHex = hexes.length ? `${hexes.slice(0, 8).join(",")}${hexes.length > 8 ? ` and ${hexes.length - 8} more` : ""}` : "–";
    check.replaceChildren(
      el("dt", { text: "TEPHRA_FLEET_PREFIXES" }), el("dd", { text: prefixes.join(",") || "–" }),
      el("dt", { text: "TEPHRA_FLEET_HEXES" }), el("dd", { text: `${shownHex}${bad ? ` · ${bad} to fix` : ""}` }));
  };
  const countH = el("h2", { id: "s-aircraft" });
  const table = el("div", { class: "fleet" });
  const redraw = (focusRow = null) => {
    countH.textContent = `Aircraft · ${f.aircraft.length}`;
    const rows = f.aircraft.slice(0, S.fleetShown);
    const more = f.aircraft.length > S.fleetShown ? el("button", { type: "button", class: "btn btn--secondary btn--sm", text: `Show ${Math.min(ROWS_STEP, f.aircraft.length - S.fleetShown)} more` }) : null;
    more?.addEventListener("click", () => {
      S.fleetShown += ROWS_STEP;
      redraw(S.fleetShown - ROWS_STEP);
    });
    const hooks = {
      onEdit: () => {
        drawCheck();
        changed();
      },
      onRemove: (i) => {
        f.aircraft.splice(i, 1);
        changed();
        redraw(Math.min(i, f.aircraft.length - 1));
        announce("Aircraft removed.");
      },
    };
    put(table,
      f.aircraft.length
        ? el("table", { class: "ftable" },
          el("thead", {}, el("tr", {}, ...FLEET_COLS.map(([, label, , , optional]) => el("th", { scope: "col" }, label, optional ? el("span", { class: "opt", text: OPTIONAL }) : null)), el("th", { scope: "col" }, el("span", { class: "sr-only", text: "Remove" })))),
          el("tbody", {}, ...rows.map((row, i) => fleetRow(row, i, hooks))))
        : el("p", { class: "hint", text: "No aircraft yet: add them one by one, or upload a fleet file." }),
      more);
    drawCheck();
    if (focusRow != null && focusRow >= 0) document.getElementById(fid(`fleet.aircraft.${focusRow}.registration`))?.focus();
  };
  const add = el("button", { type: "button", class: "btn btn--secondary" }, icon("i-plus"), el("span", { text: "Add aircraft" }));
  add.addEventListener("click", () => {
    f.aircraft.push({ registration: "", type_icao: "", seats: "", home_base: "", hex: "" });
    S.fleetShown = Math.max(S.fleetShown, Math.ceil(f.aircraft.length / ROWS_STEP) * ROWS_STEP);
    delete S.server.fleet;
    changed();
    redraw(f.aircraft.length - 1);
  });
  const take = (textIn, name, result) => {
    const res = parseFleetFile(textIn, name, f.aircraft);
    if (res.error) {
      result.replaceChildren(note("caution", null, res.error));
      return;
    }
    f.aircraft.push(...res.rows);
    delete S.server.fleet;
    changed();
    redraw();
    put(result,
      el("p", { class: "upres__sum" }, el("b", { text: `Added ${res.rows.length}` }), ` · ${res.refused.length} refused`),
      res.refused.length ? el("ul", { class: "upres__bad" }, ...res.refused.slice(0, 50).map((r) => el("li", { text: r.message }))) : null,
      res.refused.length > 50 ? el("p", { class: "hint", text: `And ${res.refused.length - 50} more refused rows.` }) : null);
  };
  redraw();
  const aircraft = el("section", { class: "section", "aria-labelledby": "s-aircraft" },
    countH, listErr("fleet.aircraft"), table,
    S.fleetTab === "type" ? el("div", { class: "tool" }, add) : null,
    el("p", { id: "fleet-seats-hint", class: "hint", text: "Seats: 0 for a freighter. The hex address is the aircraft's ICAO 24-bit address, as in your ADS-B data." }),
    el("details", { class: "help" }, el("summary", {}, el("span", { text: "Why the ICAO address" }), caret()),
      el("p", { text: "The 24-bit address matches your aircraft even when it flies under another callsign, a wet lease or a codeshare. ADS-B carries no registrations, so an aircraft without one is found only by its callsign prefix." })));
  const seg = segmented({
    label: "How to give your fleet", idBase: "fleet-how", value: S.fleetTab,
    tabs: [{ key: "type", text: "Type it in", icon: "i-pencil" }, { key: "upload", text: "Upload fleet file", icon: "i-file" }],
    onChange: (k) => {
      S.fleetTab = k;
      render({ keepFocus: true });
    },
  });
  const panel = el("div", { id: "fleet-how-panel", class: "tabpanel", role: "tabpanel", "aria-labelledby": `fleet-how-${S.fleetTab}` },
    S.fleetTab === "upload" ? fleetUpload(f, take) : null, aircraft);
  return [
    seg, panel,
    section("Other callsign prefixes", "s-prefixes",
      el("div", { class: "field" },
        el("label", { for: "fleet-prefixes" }, "Other callsign prefixes", el("span", { class: "opt", text: " (optional)" })),
        chipsInput({ id: "fleet-prefixes", label: "Other callsign prefixes", values: [...(f.extra_prefixes || [])], max: 4, placeholder: "3 letters, Enter to add", describedBy: `fleet-prefixes-hint ${fid("fleet.extra_prefixes")}-err`, onChange: (list) => {
          f.extra_prefixes = list;
          drawCheck();
          changed();
        } }),
        el("p", { id: "fleet-prefixes-hint", class: "hint", text: "Up to 4, three letters each: flights filed under these are yours too." }),
        listErr("fleet.extra_prefixes"))),
    section("What your TEPHRA will check", "s-check",
      el("div", { class: "filter-preview" }, check,
        el("p", { text: "Flights whose callsign starts with these letters, these aircraft, and every aircraft you push. Empty means every aircraft, as the demo does." }),
        el("p", { text: "TEPHRA checks only flights whose callsign is three letters and a flight number; one flying under its registration stays on the map but is not checked." }))),
  ];
}

// --- page 4 · Network ------------------------------------------------------------------------------

// "WIII · CGK · Soekarno-Hatta ..." (a list option), "CGK" (IATA) or "wiii" -> "WIII"
function networkPage() {
  const n = V().network;
  const main = upper(V().airline.main_base);
  const list = el("ul", { class: "aplist" });
  const coverage = el("div", {});
  const draw = (focusId = null) => {
    const codes = [...(main ? [main] : []), ...n.airports.filter((c) => c !== main)];
    const cautions = cautionsOf("network", V(), { airports: S.known, positions: S.positions, regions: S.state?.regions });
    list.replaceChildren(...codes.map((code) => {
      const ap = S.airports.get(code);
      const caution = cautions.find((c) => c.code === code);
      const end = code === main
        ? el("span", { class: "chip", text: "Main base" })
        : el("button", { type: "button", class: "rowdel", "aria-label": `Remove ${code}` }, icon("i-x"));
      if (code !== main) end.addEventListener("click", () => {
        n.airports = n.airports.filter((c) => c !== code);
        delete n.alternates[code];
        changed();
        draw("ap-add");
        announce(`Removed ${code}.`);
      });
      const altId = fid(`network.alternates.${code}`);
      return el("li", { class: "ap" },
        el("div", { class: "ap__h" }, el("code", { class: "ap__code", text: code }), el("span", { class: "ap__name", text: ap ? ap.name : "" }), end),
        caution ? el("p", { class: "ap__caution" }, icon("st-caution"), el("span", { text: caution.message })) : null,
        el("div", { class: "field" },
          el("label", { for: altId }, `Alternates you use (optional)`),
          chipsInput({ id: altId, label: `Alternates you use at ${code}`, values: [...(n.alternates[code] || [])], max: 5, placeholder: "ICAO code, Enter to add", describedBy: `net-alt-hint ${altId}-err`, onChange: (vals) => {
            n.alternates[code] = vals;
            delete S.server.network;
            changed();
          } }),
          el("p", { id: `${altId}-err`, class: "err", hidden: true, dataset: { list: altId } })));
    }));
    const outside = cautions.find((c) => c.field === "network.coverage");
    coverage.replaceChildren(...(outside ? [note("caution", null, outside.message)] : []));
    if (focusId) document.getElementById(focusId)?.focus();
  };
  const pick = el("input", { id: "ap-add", class: "input", list: "ob-airports", autocomplete: "off", spellcheck: "false", placeholder: "ICAO, IATA or name", "aria-describedby": "ap-add-hint ap-add-err" });
  const addBtn = el("button", { type: "button", class: "btn btn--secondary" }, icon("i-plus"), el("span", { text: "Add airport" }));
  const add = () => {
    const code = airportCode(pick.value, S.airports);
    if (!code) {
      setError(pick, "Four letters, A to Z, or one airport's name from the list.");
      return;
    }
    setError(pick, null);
    pick.value = "";
    if (code !== main && !n.airports.includes(code)) n.airports.push(code);
    delete S.server.network;
    changed();
    draw("ap-add");
    announce(`Added ${code}.`);
  };
  addBtn.addEventListener("click", add);
  pick.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    add();
  });
  draw();
  const count = S.airports.size;
  return [
    section("Airports", "s-airports",
      el("div", { class: "field" },
        el("label", { for: "ap-add", text: "Add an airport" }),
        el("div", { class: "addrow" }, pick, addBtn),
        el("p", { id: "ap-add-hint", class: "hint", text: `${count ? `Search TEPHRA's ${count} airports, or type any ICAO code.` : "Type an ICAO code."} Your main base from page 1 is the first row.` }),
        el("p", { id: "ap-add-err", class: "err", hidden: true }),
        el("datalist", { id: "ob-airports" }, ...[...S.airports].map(([code, ap]) => el("option", { value: `${code}${ap.iata ? ` · ${ap.iata}` : ""} · ${ap.name}` })))),
      listErr("network.airports"),
      list,
      coverage,
      el("p", { id: "net-alt-hint", class: "hint", text: "Alternates are kept in your setup kit for your dispatchers. TEPHRA picks alternates itself from its airport list within your policy's search radius." })),
  ];
}

// --- page 5 · Schedule and crews -------------------------------------------------------------------

function scheduleCheck() {
  return checkSchedule(S.local.files || {}, V().fleet.aircraft.map((r) => r.registration));
}

function schedulePage() {
  const s = V().schedule;
  const out = el("div", { class: "sched", role: "status" });
  const draw = () => {
    const res = scheduleCheck();
    s.summary = res.summary;
    if (res.flights || res.crews) s.skipped = false;
    put(out, 
      ...["flights", "crews"].map((k) => {
        const r = res[k];
        if (!r) return el("p", { class: "hint", text: `${k}.json · not given` });
        const remove = el("button", { type: "button", class: "linkbtn", "aria-label": `Remove ${k}.json`, text: "Remove" });
        remove.addEventListener("click", () => {
          const { [k]: _gone, ...rest } = S.local.files;
          S.local.files = rest;
          changed();
          draw();
          announce(`${k}.json removed.`);
        });
        return el("div", { class: `sfile${r.total ? " is-bad" : ""}` },
          el("p", {}, icon(r.total ? "st-caution" : "st-ok"), el("span", { text: fileLine(r) }), remove),
          r.problems.length ? el("ul", { class: "sfile__bad" }, ...r.problems.map((t) => el("li", { text: t }))) : null);
      }),
      res.summary
        ? el("p", { class: "sched__sum" }, el("b", { text: `${res.summary.flights} flights · ${res.summary.crews} crews` }), res.summary.crew_bases.length ? ` · crew bases ${res.summary.crew_bases.join(", ")}` : "")
        : res.ok && (res.flights || res.crews) ? el("p", { class: "hint", text: "Add both files: they go together." }) : null);
    showProblems("schedule");
    changed();
  };
  const fileInput = (k) => {
    const id = `sched-${k}`;
    const f = el("input", { type: "file", id, accept: ".json,application/json", class: "sr-only" });
    f.addEventListener("change", async () => {
      const one = f.files?.[0];
      f.value = "";
      if (!one) return;
      if (one.size > SCHEDULE_FILE_MAX_BYTES) {
        announce(`${k}.json is larger than 2 MB.`);
        out.prepend(note("caution", null, `${k}.json is larger than 2 MB.`));
        return;
      }
      S.local.files = { ...S.local.files, [k]: await one.text() };
      draw();
      announce(`${k}.json read.`);
    });
    return el("div", { class: "drop" },
      el("span", { class: "drop__ic" }, icon("i-file")),
      el("p", {}, el("b", { text: `${k}.json` }), el("br"), k === "flights" ? "One day's flights in TEPHRA's flights format (download an empty flights.json below), with your flight numbers and registrations." : "Your crews, each with its base and report time."),
      el("label", { class: "btn btn--secondary", for: id }, icon("i-file"), el("span", { text: `Choose ${k}.json` })), f);
  };
  const node = [
    section("Your files", "s-files",
      el("p", { class: "section__sub", text: "Read in this browser, nothing is uploaded. Only the counts go with your answers; the files go into your setup kit." }),
      fileInput("flights"), fileInput("crews"),
      el("div", { class: "tool" },
        el("button", { type: "button", class: "linkbtn", dataset: { act: "tpl-flights" }, text: "Download an empty flights.json" }),
        el("button", { type: "button", class: "linkbtn", dataset: { act: "tpl-crews" }, text: "Download an empty crews.json" })),
      listErr("schedule.files"),
      out),
    note("notbuilt", "Not built yet.", "Recovery re-planning for your network is not built. Your crews file is kept in your setup kit for when it is."),
  ];
  window.queueMicrotask(draw);
  return node;
}

// --- page 6 · Data feeds ---------------------------------------------------------------------------

function feedsPage() {
  const f = V().feeds;
  const none = el("p", { class: "hint", text: "None ticked: public ADS-B only, for now." });
  const syncNone = () => {
    none.hidden = Boolean(f.positions || f.flight_plans || f.pilot_reports);
  };
  const box = (key, label, hint) => {
    const c = el("input", { type: "checkbox", id: `feeds-${key}`, checked: Boolean(f[key]), "aria-describedby": `feeds-${key}-hint` });
    c.addEventListener("change", () => {
      f[key] = c.checked;
      syncNone();
      changed();
    });
    return el("div", { class: "checkrow" }, el("label", { class: "check" }, c, el("b", { text: label })), el("p", { id: `feeds-${key}-hint`, class: "hint", text: hint }));
  };
  syncNone();
  return [
    section("What you will send", "s-send",
      box("positions", "Positions", "From your own tracking. Each one carries the aircraft's ICAO 24-bit address and the time it was measured, within 5 minutes of your TEPHRA's clock. Only a position with an airline-style callsign (designator and flight number, e.g. RFA1654) is checked against the ash; one without stays on the map."),
      box("flight_plans", "Flight plans", "Origin, destination and times: your routes on the maps and the closed-airport check."),
      box("pilot_reports", "Pilot reports", "Special air-reports of volcanic ash (AIREP SPECIAL, VAR): where and when a crew saw ash, entered as caution areas, never shrinking the official one."),
      none,
      field({ id: fid("feeds.source_system"), label: "Where they come from", optional: true, control: bound(input({ placeholder: "e.g. our flight-following system", maxlength: 80 }), () => f.source_system, (v) => { f.source_system = v; }, "feeds") })),
    section("The format", "s-format",
      el("p", {}, "One JSON push in the ", el("code", { text: "tephra.airline/1" }), " format, with any of three sections. ", el("a", { class: "link", href: PATHS.schema, download: "", text: "Schema (JSON)" })),
      el("p", { text: "Your setup kit's push.py sends it, and stamps observed_at at send time for positions measured just then." }),
      el("p", { text: "After you create your account, try a file in the dry run in your workspace." })),
  ];
}

// --- page 7 · People -------------------------------------------------------------------------------

function peoplePage() {
  const p = V().people;
  const box = el("div", {});
  const draw = (focus = null) => {
    box.replaceChildren(p.dispatchers.length
      ? el("table", { class: "ftable ftable--people" },
        el("thead", {}, el("tr", {}, el("th", { scope: "col", text: "Name or initials" }), el("th", { scope: "col", text: "Role" }), el("th", { scope: "col" }, el("span", { class: "sr-only", text: "Remove" })))),
        el("tbody", {}, ...p.dispatchers.map((d, i) => {
          const nid = fid(`people.dispatchers.${i}.name`);
          const name = input({ value: d.name, maxlength: 32, autocomplete: "off", "aria-label": `Name or initials, dispatcher ${i + 1}` });
          name.id = nid;
          name.setAttribute("aria-describedby", `${nid}-err people-hint`);
          name.addEventListener("input", () => {
            d.name = name.value;
            if (name.getAttribute("aria-invalid") === "true") showProblems("people", { only: nid });
            changed();
          });
          const rid = fid(`people.dispatchers.${i}.role`);
          const role = el("select", { id: rid, class: "select", "aria-label": `Role, dispatcher ${i + 1}`, "aria-describedby": `${rid}-err` },
            el("option", { value: "", text: "Choose…", selected: !d.role || null }),
            el("option", { value: "approves", text: "Approves advisories", selected: d.role === "approves" || null }),
            el("option", { value: "views", text: "Views only", selected: d.role === "views" || null }));
          role.addEventListener("change", () => {
            d.role = role.value || null;
            if (role.getAttribute("aria-invalid") === "true") showProblems("people");
            changed();
          });
          const remove = el("button", { type: "button", class: "rowdel", "aria-label": `Remove ${d.name || `dispatcher ${i + 1}`}` }, icon("i-x"));
          remove.addEventListener("click", () => {
            p.dispatchers.splice(i, 1);
            changed();
            draw(Math.max(0, i - 1));
          });
          return el("tr", {},
            el("td", { class: "wide", dataset: { l: "Name or initials" } }, name, el("p", { id: `${nid}-err`, class: "err", hidden: true })),
            el("td", { dataset: { l: "Role" } }, role, el("p", { id: `${rid}-err`, class: "err", hidden: true })),
            el("td", {}, remove));
        })))
      : el("p", { class: "hint", text: "No dispatchers yet." }));
    if (focus != null && p.dispatchers.length) document.getElementById(fid(`people.dispatchers.${focus}.name`))?.focus();
  };
  const add = el("button", { type: "button", class: "btn btn--secondary" }, icon("i-plus"), el("span", { text: "Add a dispatcher" }));
  add.addEventListener("click", () => {
    if (p.dispatchers.length >= 50) return;
    p.dispatchers.push({ name: "", role: null });
    delete S.server.people;
    changed();
    draw(p.dispatchers.length - 1);
  });
  draw();
  return [
    section("Dispatchers", "s-people", listErr("people.dispatchers"), box, el("div", { class: "tool" }, add),
      el("p", { id: "people-hint", class: "hint", text: "Their names stay in your workspace and never go to a model. In your own TEPHRA each one signs in on the Desk with your Desk PIN and their name." })),
  ];
}

// --- page 8 · Assistant (AI model) -----------------------------------------------------------------

function assistantPage() {
  const choice = modelChoice(V().assistant, {
    ollama: S.edit ? null : { get: () => S.local.ollama_url ?? DEFAULT_OLLAMA_URL, set: (v) => { S.local.ollama_url = v; } },
    onChange: () => {
      delete S.server.assistant;
      changed();
    },
    recheck: (id) => showProblems("assistant", { only: id }),
  });
  return [section("Where its model runs", "s-model", choice)];
}

// --- page 9 · Review -------------------------------------------------------------------------------

let acct = null;

function allProblems() {
  const out = [];
  for (const key of ANSWER_PAGES) {
    const page = pageOf(key);
    for (const p of checkPage(key, V(), ctxFor(key))) out.push({ page: key, field: p.field, text: `${page.name}: ${p.message}` });
    for (const p of S.server[key] || []) out.push(p);
  }
  return out;
}

function reviewPage() {
  const answers = toAnswers(S.draft);
  acct = accountForm({ accountsOn: S.accounts });
  return [
    el("div", { id: "ob-errors", class: "ob-errors", role: "alert", tabindex: "-1", hidden: true }),
    reviewList(answers, { named: S.named, labels: S.labels, problems: Object.fromEntries(ANSWER_PAGES.map((k) => [k, problemCount(k)])), editHref: (k) => `/onboard/${k}` }),
    acct.node,
    passwordAside(),
  ];
}

// A problem on another page links to that page; one on this page links to its field and focuses it
// (the hash is never set: a hash change would re-render the page).
function problemLink(p) {
  if (p.id) {
    const a = el("a", { class: "link", href: `#${p.id}`, text: p.text });
    a.addEventListener("click", (e) => {
      e.preventDefault();
      document.getElementById(p.id)?.focus();
    });
    return a;
  }
  if (p.page && p.page !== "review") return el("a", { class: "link", href: `/onboard/${p.page}`, dataset: { go: p.page }, text: p.text });
  return el("span", { text: p.text });
}

function errorSummary(items, extra = null) {
  const box = $("ob-errors");
  const n = items.length;
  put(box,
    el("p", { class: "ob-errors__h" }, icon("st-caution"), el("b", { text: n ? `Fix ${n === 1 ? "1 thing" : `${n} things`} before you create your account` : "Your account was not created" })),
    n ? el("ul", {}, ...items.slice(0, 12).map((p) => el("li", {}, problemLink(p)))) : null,
    n > 12 ? el("p", { class: "hint", text: `And ${n - 12} more.` }) : null,
    extra);
  box.hidden = false;
  box.focus();
}

function accountProblems(v) {
  const out = [];
  const e = ruleMessage("acct.email", v.email);
  if (e) out.push(["acct-email", e]);
  const p = ruleMessage("acct.password", v.password);
  if (p) out.push(["acct-password", p]);
  else if (v.password.trim().toLowerCase() === v.email) out.push(["acct-password", "The password must not be your email."]);
  else if (v.password2 !== v.password) out.push(["acct-password2", "The two passwords differ."]);
  if (!v.ack) out.push(["acct-ack", "Tick this to go on."]);
  return out;
}

function createWords(res) {
  const code = errorCode(res);
  if (res.status === 409 && code === "email_taken") return el("p", {}, "An account with this email exists. ", el("a", { class: "link", href: "/signin", text: "Sign in instead." }));
  if (res.status === 429) return el("p", { text: `Too many tries from this address. Try again in about ${minutesWords(retryMinutes(res))}. Your answers are saved in this browser.` });
  if (res.status === 503 && code === "onboarding_full") return el("p", { text: "New airlines are paused on this server for now. Your answers are saved in this browser." });
  if (code === "accounts_off") return el("p", { text: ACCOUNTS_OFF });
  if (code === "feature_off") return el("p", { text: ONBOARD_OFF });
  if (res.status === 413) return el("p", { text: "Your answers are too large to send (more than 128 KB)." });
  if (res.status === 0) return el("p", { text: "You're offline. Your answers are saved in this browser." });
  return el("p", { text: `Your account was not created (HTTP ${res.status}). Your answers are saved in this browser.` });
}

async function createAccount(button) {
  const v = acct.values();
  for (const id of ["acct-email", "acct-password", "acct-password2", "acct-ack"]) setError($(id), null);
  const pageProblems = allProblems();
  const own = accountProblems(v);
  for (const [id, msg] of own) setError($(id), msg);
  if (pageProblems.length || own.length) {
    errorSummary([...pageProblems, ...own.map(([id, msg]) => ({ page: "review", id, text: `Your account: ${msg}` }))]);
    return;
  }
  const answers = toAnswers(S.draft);
  const body = JSON.stringify({ answers, email: v.email, password: v.password, acknowledge: true, website: v.website });
  if (new TextEncoder().encode(body).length > MAX_BODY_BYTES) {
    errorSummary([], el("p", { text: "Your answers are too large to send (more than 128 KB)." }));
    return;
  }
  const words = button.querySelector("span");
  button.disabled = true;
  words.textContent = "Creating…";
  const res = await call(PATHS.accounts, { method: "POST", raw: body });
  button.disabled = false;
  words.textContent = "Create account and submit";
  if (res.ok && typeof res.data?.recovery_code === "string") {
    acct.clearSecrets();
    S.recovery = { code: res.data.recovery_code, email: v.email, icao: answers.airline.icao };
    saver.flush();
    clearDraft();
    S.draft = blankDraft();
    S.navMode = null;
    go("/onboard/done");
    return;
  }
  if (res.status === 422 && errorCode(res) === "validation_failed") {
    S.server = {};
    const mapped = problemsOf(res).map((p) => mapServerProblem(p, answers));
    for (const m of mapped) if (m.page !== "review") (S.server[m.page] ||= []).push(m);
    errorSummary(mapped);
    drawSteps("review");
    return;
  }
  errorSummary([], createWords(res));
}

// --- one page --------------------------------------------------------------------------------------

const BUILDERS = { airline: airlinePage, policy: policyPage, fleet: fleetPage, network: networkPage, schedule: schedulePage, feeds: feedsPage, people: peoplePage, assistant: assistantPage, review: reviewPage };

function actionBar(key) {
  const i = PAGE_KEYS.indexOf(key);
  const bar = $("ob-actions");
  if (S.edit) {
    bar.replaceChildren(
      el("a", { class: "btn btn--secondary", href: "/workspace/answers", text: "‹ Workspace" }),
      el("p", { id: "ob-edit-status", class: "actions__mid actions__mid--keep", role: "status" }),
      el("button", { type: "submit", form: "ob-form", class: "btn btn--primary" }, el("span", { text: "Save changes" })));
    return;
  }
  const back = i === 0
    ? el("a", { class: "btn btn--secondary", href: "/onboard", dataset: { go: "" }, text: "‹ Overview" })
    : el("a", { class: "btn btn--secondary", href: `/onboard/${PAGE_KEYS[i - 1]}`, dataset: { go: PAGE_KEYS[i - 1] }, text: "‹ Back" });
  const words = key === "review" ? "Create account and submit" : S.leaveAnyway === key ? "Next anyway ›" : `Next: ${pageOf(PAGE_KEYS[i + 1]).name} ›`;
  const next = el("button", { type: "submit", form: "ob-form", class: "btn btn--primary", disabled: key === "review" && !S.accounts ? true : null }, el("span", { text: words }));
  const skip = key === "schedule" ? el("button", { type: "button", class: "btn btn--quiet", dataset: { act: "skip" }, text: "Skip for now" }) : null;
  put(bar, back, el("p", { class: "actions__mid", text: "Back and Next keep what you typed." }), skip, next);
}

function renderPage(key) {
  const page = pageOf(key);
  document.title = `${page.name} · Onboard · TEPHRA`;
  if (!S.edit) {
    if (!S.draft.seen.includes(key)) S.draft.seen.push(key);
    S.draft.at = key;
    saver.schedule(S.draft, S.local);
  }
  if (S.leaveAnyway !== key) S.leaveAnyway = null;
  const form = el("form", { id: "ob-form", class: "form", novalidate: true },
    el("div", { class: "form__head" }, el("h1", { text: page.h1 }), el("p", { text: page.why })),
    ...BUILDERS[key]());
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (key === "review") createAccount(e.submitter || $("ob-actions").querySelector(".btn--primary"));
    else if (S.edit) saveEdit(key);
    else next(key);
  });
  $("main").replaceChildren(form);
  const withAside = key !== "review" && !S.edit;
  $("ob-aside").replaceChildren(...(withAside ? [aside()] : []));
  $("ob-aside").hidden = !withAside;
  document.body.classList.toggle("ob--noaside", !withAside);
  drawAside();
  drawSteps(key);
  actionBar(key);
  if (S.flagged.has(key) || S.server[key]) showProblems(key);
}

function next(key) {
  const problems = showProblems(key);
  const blocked = key === "schedule" && !scheduleCheck().ok;
  // "Next anyway" passes the problems the viewer was shown, not new ones found since.
  const seen = problems.map((p) => `${p.field} ${p.message}`).join("\n");
  if (problems.length && (blocked || S.leaveAnyway !== key || S.anywayFor !== seen)) {
    S.flagged.add(key);
    if (!blocked) { S.leaveAnyway = key; S.anywayFor = seen; }
    actionBar(key);
    focusFirstProblem();
    announce(`${problems.length === 1 ? "1 thing" : `${problems.length} things`} to check on this page.`);
    return;
  }
  if (!problems.length) S.flagged.delete(key);
  S.leaveAnyway = null;
  saver.flush();
  go(`/onboard/${PAGE_KEYS[PAGE_KEYS.indexOf(key) + 1]}`);
}

async function saveEdit(key) {
  const status = $("ob-edit-status");
  showProblems(key);
  const problems = allProblems();
  if (problems.length) {
    status.textContent = `Not saved: ${problems.length === 1 ? "1 thing" : `${problems.length} things`} to check. ${problems[0].text}`;
    focusFirstProblem();
    return;
  }
  status.textContent = "Saving…";
  const answers = toAnswers({ values: V() });
  const res = await call(PATHS.answers, { method: "PUT", body: { version: S.edit.version, answers } });
  if (res.ok && res.data) {
    S.edit = res.data;
    status.textContent = "Saved. Your workspace shows the new answers.";
  } else if (res.status === 401) {
    location.assign(`/signin?next=${encodeURIComponent(`${location.pathname}?edit=1`)}`);
  } else if (res.status === 409) {
    status.textContent = "Someone changed these answers in another tab. Reload to see them.";
  } else if (res.status === 403) {
    status.textContent = typeof res.data?.detail === "string" ? res.data.detail : "Your answers can no longer be changed here.";
  } else if (res.status === 429) {
    status.textContent = "Not saved: too many saves today. Try again later.";
  } else if (res.status === 422) {
    status.textContent = `Not saved: ${problemsOf(res).map((p) => mapServerProblem(p, answers).text).slice(0, 3).join(" · ")}`;
  } else {
    status.textContent = res.status === 0 ? "You're offline. Nothing was saved." : `Not saved (HTTP ${res.status}).`;
  }
}

// --- the landing -----------------------------------------------------------------------------------

function landing() {
  document.title = "Onboard your airline · TEPHRA";
  const saved = loadDraft();
  const at = saved?.at ? pageOf(saved.at) : null;
  const me = S.account?.signedIn ? S.account : null;
  // Signed in, the airline is onboarded already: its workspace, never a second draft.
  const cta = me
    ? [el("a", { id: "ob-start", class: "btn btn--primary btn--lg", href: "/workspace" }, el("span", { text: "Open your workspace" }), icon("i-arrow-right")),
      el("p", { class: "body2", text: `You are signed in as ${[me.icao, me.name].filter(Boolean).join(" · ")}.` })]
    : [el("a", { id: "ob-start", class: "btn btn--primary btn--lg", href: `/onboard/${at ? at.key : "airline"}`, dataset: { go: at ? at.key : "airline" } },
      el("span", { text: at ? `Continue where you left off (page ${at.n} of 9)` : "Start with your airline" }), icon("i-arrow-right")),
    at ? el("button", { type: "button", class: "btn btn--quiet", dataset: { act: "startover" }, text: "Start over" }) : null,
    el("p", { class: "body2" }, "Already onboarded? ", el("a", { class: "link", href: "/signin", text: "Sign in" }))];
  $("main").replaceChildren(el("div", { class: "ostart" },
    el("div", { class: "ostart__head" },
      el("p", { class: "eyebrow", text: "Onboard your airline" }),
      el("h1", { class: "h1", text: "Set TEPHRA up for your airline, one topic per page." }),
      el("p", { class: "lead", text: "Nine short pages. Your answers are saved in this browser as you go and leave it only when you create your account on the last page." }),
      el("div", { class: "ostart__cta" }, ...cta.filter(Boolean))),
    el("section", { class: "provide", "aria-labelledby": "provide-h" },
      el("h2", { id: "provide-h", class: "h2", text: "How to onboard: what you provide" }),
      el("ol", { class: "provide__list" }, ...PROVIDE.map((p, i) => el("li", { class: "card provide__i" },
        el("span", { class: "provide__ic", "aria-hidden": "true" }, icon(p.icon)),
        el("div", {},
          el("b", {}, el("span", { class: "provide__n", text: String(i + 1) }), p.name),
          el("p", {}, `${p.text.charAt(0).toUpperCase()}${p.text.slice(1)}`, p.code ? el("code", { text: p.code }) : null, p.after || null)))))),
    el("div", { class: "get" },
      el("section", { id: "ob-after", class: "card", "aria-labelledby": "after-h" },
        el("h2", { id: "after-h", class: "h3" }, icon("i-clock"), el("span", { text: "After you submit" })),
        el("ol", { class: "next3" },
          el("li", {}, el("b", {}, el("i", { "aria-hidden": "true", text: "1" }), el("span", { text: "A recovery code, shown once." }))),
          el("li", {}, el("b", {}, el("i", { "aria-hidden": "true", text: "2" }), el("span", { text: "Pending verification until a TEPHRA dispatcher verifies your airline." }))),
          el("li", {}, el("b", {}, el("i", { "aria-hidden": "true", text: "3" }), el("span", { text: "Your setup kit, ready at once in your workspace." }))))),
      el("section", { id: "ob-private", class: "card", "aria-labelledby": "private-h" },
        el("h2", { id: "private-h", class: "h3" }, icon("i-lock"), el("span", { text: "Private" })),
        el("p", { class: "body2", text: "Only you and this site's TEPHRA dispatchers, who verify your airline, read your answers. Your workspace is never listed publicly, and nothing you enter appears on the demo's map or the Desk's picture." }))),
    el("div", { id: "ob-notbuilt", class: "note note--notbuilt", role: "note" }, icon("i-info"),
      el("p", {}, el("b", { text: "Not built yet. " }), "Running your live operation on this shared TEPHRA is not built, so no advisory is drafted under your airline's name here. Your own TEPHRA from the setup kit checks your fleet, but its drafts still name each flight by a Ring of Fire Air number."))));
}

// --- done and off ----------------------------------------------------------------------------------

function done() {
  document.title = "Recovery code · Onboard · TEPHRA";
  if (S.recovery) {
    $("main").replaceChildren(recoveryCard(S.recovery, { lead: "It is shown once. With it you can get back into your workspace if you forget your password; reset by email is not built." }));
    return;
  }
  $("main").replaceChildren(el("div", { class: "narrow" }, el("section", { class: "card authcard" },
    el("h1", { class: "h2", text: "Your recovery code was shown once" }),
    el("p", { class: "body2", text: "Your recovery code was shown once, when you created your account. If you did not save it, sign in with your password and keep it safe." }),
    el("a", { class: "btn btn--primary btn--block", href: "/workspace" }, el("span", { text: "Open my workspace" }), icon("i-arrow-right")))));
}

function offCard(words) {
  document.title = "Onboard your airline · TEPHRA";
  $("main").replaceChildren(el("div", { class: "narrow" }, el("section", { class: "card authcard" },
    el("h1", { class: "h2", text: words }),
    el("a", { class: "btn btn--primary btn--block", href: "/demo" }, el("span", { text: "Watch the demo" }), icon("i-arrow-right")))));
}

// --- render ----------------------------------------------------------------------------------------

async function render({ keepFocus = false } = {}) {
  const r = route();
  if (S.state && !has("onboard")) {
    frame("off");
    offCard(ONBOARD_OFF);
    focusHeading();
    return;
  }
  if (r.view === "page" && r.edit && !S.edit) {
    const me = await call(PATHS.me);
    if (me.status === 401) {
      location.replace(`/signin?next=${encodeURIComponent(`${location.pathname}?edit=1`)}`);
      return;
    }
    if (!me.ok || !me.data?.editable) {
      location.replace("/workspace/answers");
      return;
    }
    S.edit = me.data;
    S.draft = { v: 2, seen: [...ANSWER_PAGES], at: null, values: fromAnswers(me.data.answers, S.named) };
  } else if (r.view === "page" && !r.edit && S.edit) {
    S.edit = null;
    S.draft = loadDraft() || blankDraft();
  }
  frame(r.view);
  const navMode = r.view === "landing" ? "landing" : "page";
  if (navMode !== S.navMode) {
    S.navMode = navMode;
    S.account = await initAccountNav({ right: $("tn-right"), signin: navMode !== "landing" });
  }
  if (r.view === "page" && !r.edit && S.account?.signedIn) {
    location.replace("/workspace/answers");
    return;
  }
  if (r.view === "landing") landing();
  else if (r.view === "done") done();
  else renderPage(r.key);
  if (!keepFocus) focusHeading();
}

// --- clicks every view shares ----------------------------------------------------------------------

function download(name, body) {
  const url = URL.createObjectURL(new Blob([body], { type: name.endsWith(".csv") ? "text/csv" : "application/json" }));
  const a = el("a", { href: url, download: name, hidden: true });
  document.body.append(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// Empty files in TEPHRA's formats: the shape only, no rows.
const TEMPLATES = {
  "tpl-fleet-csv": ["fleet.csv", "registration,type,seats,home_base,hex\n"],
  "tpl-fleet-json": ["fleet.json", `${JSON.stringify({ tails: [] }, null, 2)}\n`],
  "tpl-flights": ["flights.json", `${JSON.stringify({ header: { label: "", anchor_utc_offset_h: null }, flights: [] }, null, 2)}\n`],
  "tpl-crews": ["crews.json", `${JSON.stringify({ crews: [] }, null, 2)}\n`],
};

function confirmClear(title) {
  const dlg = $("ob-dlg");
  const cancel = el("button", { type: "button", class: "btn btn--secondary", text: "Cancel" });
  const clear = el("button", { type: "button", class: "btn btn--primary", text: "Clear answers" });
  cancel.addEventListener("click", () => dlg.close());
  clear.addEventListener("click", () => {
    saver.flush();
    clearOnboardStorage();
    S.draft = blankDraft();
    S.local = { ollama_url: null, files: {} };
    S.flagged.clear();
    S.server = {};
    S.saved = null;
    $("ob-saved").replaceChildren();
    dlg.close();
    go("/onboard");
    announce("Your answers in this browser are cleared.");
  });
  dlg.replaceChildren(el("h2", { id: "ob-dlg-h", class: "h2", text: title }), el("p", { class: "body2", text: "Your answers in this browser are cleared." }), el("div", { class: "pdlg__acts" }, cancel, clear));
  dlg.setAttribute("aria-labelledby", "ob-dlg-h");
  dlg.showModal();
  cancel.focus();
}

document.addEventListener("click", (e) => {
  const t = e.target.closest("a[data-go], [data-act]");
  if (!t) return;
  if (t.tagName === "A" && t.dataset.go !== undefined) {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    go(t.getAttribute("href"));
    return;
  }
  const act = t.dataset.act;
  if (act === "clear") confirmClear("Clear your answers?");
  else if (act === "startover") confirmClear("Start over?");
  else if (act === "skip") {
    V().schedule = { skipped: true, summary: null };
    S.local.files = {};
    S.flagged.delete("schedule");
    S.leaveAnyway = null;
    changed();
    saver.flush();
    go("/onboard/feeds");
  } else if (TEMPLATES[act]) download(...TEMPLATES[act]);
});

window.addEventListener("popstate", () => render());
window.addEventListener("pagehide", () => saver.flush());

async function boot() {
  inlineSprite();
  const saved = loadDraft();
  if (saved) S.draft = { v: 2, seen: saved.seen, at: saved.at || null, values: { ...emptyValues(), ...saved.values } };
  S.local = loadLocal();
  await loadContext();
  await render();
}

boot();
