// Onboarding (SPEC-v2 §6, account first since 16 Oct 2026): the landing at /onboard with the
// sign-up form, the recovery code at /onboard/done, then nine pages at /onboard/<page>, one topic
// each, saved to the account on every Next and Back (PUT /api/airline/draft) until Review submits
// them for verification. Signing in again resumes at the first page not finished. Signed in while
// the airline is pending, /onboard/<page>?edit=1 edits the stored answers instead. Pages move with
// the history API; focus goes to each page's h1. Each page says one line under its h1; what explains
// it sits behind an (i) (wall/info.js). Errors wait until a field is left or Next is pressed. Every
// string goes in through el() (textContent).

import { $, el, icon, inlineSprite } from "./wall/util.js";
import { infoButton } from "./wall/info.js";
import { applyFeatureNav, has, setFeatures } from "./wall/features.js";
import { formatValue, policyValues } from "./wall/policy.js";
import { initAccountNav, showAccountWho } from "./account-nav.js";
import {
  ANSWER_PAGES, airportCode, FLEET_FILE_MAX_BYTES, KEY_POLICY_VALUES, PAGES, PAGE_KEYS, PROVIDE, SCHEDULE_FILE_MAX_BYTES,
  cautionsOf, checkPage, checkSchedule, emptyValues, fileLine, firstUnfinished, fromAnswers, isEditablePolicyValue, mapServerProblem,
  pageOf, parseFleetFile, problemText, siteLine, toAnswers, upper, WHO_READS,
} from "./onboard/pages.js";
import { caret, chipInfo, choiceCards, chipsInput, fid, field, illus, input, listError, notBuilt, note, section, segmented, setError, setListError } from "./onboard/form.js";
import { dropLegacyDraft, loadLegacyDraft, loadLocal, saveLocal } from "./onboard/draft.js";
import { accountFields, recoveryCard, reviewList } from "./onboard/review.js";
import { COUNTRIES } from "./onboard/countries.js";
import { modelChoice } from "./workspace/assistant.js";
import { ACCOUNTS_OFF, ACCOUNTS_OFF_HOW, ONBOARD_OFF, PATHS, call, errorCode, failWords, problemsOf, waitWords } from "./workspace/api.js";

const MAX_BODY_BYTES = 128 * 1024;
const KEEPALIVE_MAX_BYTES = 60 * 1024;
const ROWS_STEP = 50;
const blankDraft = () => ({ seen: [], at: null, values: emptyValues() });
const draftOf = (d) => ({ seen: Array.isArray(d?.seen) ? [...d.seen] : [], at: d?.at || null, values: { ...emptyValues(), ...(d?.values || {}) } });
// replaceChildren prints a null slot as "null": the optional parts are dropped first.
const put = (node, ...kids) => node.replaceChildren(...kids.flat().filter((k) => k != null && k !== false));

const S = {
  state: null, accounts: false, policy: null, named: {}, labels: {}, airports: new Map(), known: null, positions: null,
  draft: blankDraft(), local: { files: {} },
  edit: null, me: null, meFail: null, dirty: false, saving: false, flagged: new Set(), leaveAnyway: null, anywayFor: null, server: {}, recovery: null,
  fleetShown: ROWS_STEP, fleetTab: "type", navMode: null, account: null, legacy: null,
};

const V = () => S.draft.values;
const ctxFor = (key) => ({ named: S.named, schedule: key === "schedule" ? scheduleCheck() : null });

// --- saving to the account -------------------------------------------------------------------------

// The small mark in the progress row: "Saved" once the page is in the account, "Not saved" when the
// last save failed (the reason is said in the bar where Next is). Nothing while there are changes
// not saved yet.
function setSaved(state) {
  const mark = $("ob-saved");
  if (S.edit || !mark || mark.dataset.state === state) return;
  mark.dataset.state = state;
  mark.replaceChildren(...(state === "ok" ? [icon("i-check"), el("span", { text: "Saved" })] : state === "failed" ? [icon("st-caution"), el("span", { text: "Not saved" })] : []));
}

function changed() {
  if (S.edit) return;
  S.dirty = true;
  setSaved("");
}

const keepLocal = () => saveLocal(S.local);

const draftBody = () => JSON.stringify({ version: S.me.version, draft: { at: S.draft.at, seen: S.draft.seen, values: S.draft.values } });

// Words for a save the server did not take; the typed values stay on the page either way.
function notSavedWords(res) {
  const stays = "What you typed stays on this page.";
  if (res.status === 0) return `Not saved: you're offline. ${stays}`;
  if (res.status === 429) return `Not saved: too many saves today. ${stays} Try again in about ${waitWords(res)}.`;
  if (res.status === 409) return `Not saved: your answers changed in another tab. Reload to see them.`;
  if (res.status === 413) return `Not saved: your answers are larger than 128 KB. ${stays}`;
  return `Not saved (HTTP ${res.status}). ${stays}`;
}

// One save at a time; true when the account holds the page as it is now.
async function saveDraft() {
  if (S.saving) return false;
  const raw = draftBody();
  if (new TextEncoder().encode(raw).length > MAX_BODY_BYTES) {
    sayNotSaved({ status: 413 });
    return false;
  }
  S.saving = true;
  const res = await call(PATHS.draft, { method: "PUT", raw });
  S.saving = false;
  if (res.ok && res.data) {
    S.me = res.data;
    S.dirty = false;
    dropLegacyDraft();
    setSaved("ok");
    return true;
  }
  if (res.status === 401) {
    location.assign("/signin");
    return false;
  }
  if (res.status === 409 && errorCode(res) === "already_submitted") {
    location.assign("/workspace");
    return false;
  }
  sayNotSaved(res);
  return false;
}

function sayNotSaved(res) {
  const words = notSavedWords(res);
  setSaved("failed");
  const mid = $("ob-actions")?.querySelector(".actions__mid");
  if (mid) {
    mid.textContent = words;
    mid.classList.add("actions__mid--bad");
  }
  announce(words);
}

// Back, Next and the step list: the account takes the page first; a failed save stays here.
async function saveAndGo(path) {
  const key = path.split("?")[0].replace(/\/+$/, "").split("/")[2] || "";
  if (PAGE_KEYS.includes(key)) S.draft.at = key;
  if (await saveDraft()) {
    if (path.startsWith("/onboard/")) go(path);
    else location.assign(path);
  }
}

// A page closed with changes not saved: one last save the browser finishes on its own.
function saveOnLeave() {
  if (!S.me || S.me.status !== "draft" || S.edit || !S.dirty) return;
  const raw = draftBody();
  if (new TextEncoder().encode(raw).length <= KEEPALIVE_MAX_BYTES) call(PATHS.draft, { method: "PUT", raw, keepalive: true });
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
        el("span", { text: p.short }),
        st === "done" ? el("span", { class: "sr-only", text: " (done)" }) : null,
        st === "warn" ? el("span", { class: "flag", text: n === 1 ? "1 thing to check" : `${n} things to check` }) : null),
    ];
    // on Review every page is one tap away, opened or not (Review lists them all)
    const reachable = S.edit || st === "now" || S.draft.seen.includes(p.key) || states.review === "now";
    return el("li", { class: `is-${st}` }, reachable
      ? el("a", { href: pageHref(p.key), "aria-current": st === "now" ? "step" : null, dataset: { go: p.key } }, ...inner)
      : el("span", { class: "steps__plain" }, ...inner));
  }));
}

function drawSteps(current) {
  const states = Object.fromEntries(PAGES.map((p) => [p.key, stepState(p.key, current)]));
  const done = Object.values(states).filter((s) => s === "done").length;
  put($("ob-steps"),
    el("details", { class: "steps__phone" }, el("summary", {}, el("span", { text: `All pages · ${done} of ${S.edit ? 8 : 9} done` }), caret()), stepList(states)),
    el("div", { class: "steps__wide" }, stepList(states)));
  const page = pageOf(current);
  $("ob-step").replaceChildren(...(S.edit
    ? [el("b", { text: "Editing your answers" }), " · Pending verification"]
    : [el("b", { text: `Step ${page.n} of 9` })]));
  $("ob-progress").replaceChildren(...PAGES.map((p) => el("i", { class: p.key === current ? "is-now" : states[p.key] === "todo" ? null : "is-done" })));
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
  // a fold holding a field to fix opens by itself
  for (const d of main.querySelectorAll("details:not([open])")) if (d.querySelector('[aria-invalid="true"], .err:not([hidden])')) d.open = true;
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

// A text control bound to one answer. Its error shows once something was typed and the field is
// left (or on Next), and then follows the typing.
function bound(control, get, set, page) {
  control.value = get() ?? "";
  control.addEventListener("input", () => {
    control.dataset.typed = "1";
    set(control.value);
    delete S.server[page];
    if (control.getAttribute("aria-invalid") === "true") showProblems(page, { only: control.id });
    changed();
  });
  control.addEventListener("blur", () => {
    if (control.dataset.typed) showProblems(page, { only: control.id });
  });
  return control;
}

const upperAsTyped = (c) => c.addEventListener("input", () => {
  const at = c.selectionStart;
  c.value = c.value.toUpperCase();
  c.setSelectionRange(at, at);
});

// --- page 1 · Airline ------------------------------------------------------------------------------

// The four fields a dispatcher rarely needs on first sight sit in one fold, which opens by itself
// when one of them needs fixing (showProblems).
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
    baseHint.textContent = ap ? `ICAO code · ${ap.name}` : "ICAO code";
  };
  const base = t("main_base", { mono: true, maxlength: 4 }, { up: true, after: nameBase });
  nameBase();
  return [
    section("Names and codes", "s-names",
      el("div", { class: "row2" },
        field({ id: fid("airline.name"), label: "Airline name", control: t("name", { autocomplete: "organization", maxlength: 120 }) }),
        field({ id: fid("airline.icao"), label: "ICAO designator", hint: "3 letters", control: icao }))),
    section("Where you operate", "s-where",
      el("div", { class: "row2" },
        field({ id: fid("airline.state_of_operator"), label: "State of the Operator", hint: "The State that issued your AOC", control: t("state_of_operator", { list: "ob-countries", maxlength: 60, autocomplete: "country-name" }) }),
        field({ id: fid("airline.main_base"), label: "Main base", hint: baseHint, control: base })),
      field({ id: fid("airline.ops_email"), label: "Operations email", info: { topic: "the operations email", text: "A TEPHRA dispatcher writes here when verifying your airline." }, control: t("ops_email", { type: "email", autocomplete: "email", inputmode: "email", maxlength: 254, spellcheck: "false" }) }),
      el("datalist", { id: "ob-countries" }, ...COUNTRIES.map((n) => el("option", { value: n })))),
    el("details", { class: "more more--page" },
      el("summary", {}, el("span", { text: "IATA code, callsign, AOC and contact" }), caret()),
      el("div", { class: "more__body" },
        el("div", { class: "row2" },
          field({ id: fid("airline.iata"), label: "IATA code", optional: true, hint: "2 letters or digits", control: t("iata", { mono: true, maxlength: 2 }, { up: true }) }),
          field({ id: fid("airline.callsign_prefix"), label: "Callsign prefix", hint: "Filed as, e.g. RFA1654", control: callsign })),
        el("div", { class: "row2" },
          field({ id: fid("airline.aoc_number"), label: "AOC number", optional: true, control: t("aoc_number", { mono: true, maxlength: 40 }) }),
          field({ id: fid("airline.contact_name"), label: "Contact name", optional: true, control: t("contact_name", { autocomplete: "name", maxlength: 80 }) })))),
  ];
}

// --- page 2 · Ash policy ---------------------------------------------------------------------------

const UNIT = { NM: "NM", ft: "ft", min: "min", m: "m", kt: "kt", deg: "°", FL: "FL", count: "", s: "s", USD: "USD" };

// One value: the box holds Policy A's number; the default is said under it only once it changes,
// and the reason field opens with the change.
function valueRow(name, label) {
  const base = S.named[name];
  const changes = V().policy.changes;
  const id = fid(`policy.v.${name}`);
  const rid = fid(`policy.r.${name}`);
  const num = input({ mono: true, inputmode: "numeric", autocomplete: "off", maxlength: 6, value: changes[name] ? changes[name].value : String(base.value) });
  num.classList.add("input--num");
  const reason = el("textarea", { class: "input textarea", rows: "2", maxlength: "300" });
  reason.value = changes[name]?.reason || "";
  const reasonField = field({ id: rid, label: "Why this value?", rule: "3 to 300 characters", control: reason });
  const isChanged = () => Boolean(changes[name]) && Number(changes[name].value) !== Number(base.value);
  const was = el("span", {});
  const row = el("div", { class: "pval" },
    field({ id, label, hint: was, control: num,
      slot: el("div", { class: "pval__in" }, num, el("span", { class: "pval__unit", "aria-hidden": "true", text: UNIT[base.unit] ?? base.unit })) }),
    reasonField);
  const sync = () => {
    const on = isChanged();
    reasonField.hidden = !on;
    was.textContent = on ? `Default ${formatValue(name.split(".")[1], base)}` : "";
    was.parentElement.hidden = !on;
  };
  num.addEventListener("input", () => {
    num.dataset.typed = "1";
    const v = num.value.trim();
    if (v === String(base.value)) delete changes[name];
    else changes[name] = { ...(changes[name] || {}), value: v, base: base.value, unit: base.unit, reason: reason.value };
    sync();
    delete S.server.policy;
    if (num.getAttribute("aria-invalid") === "true") showProblems("policy");
    changed();
  });
  num.addEventListener("blur", () => {
    if (num.dataset.typed) showProblems("policy", { only: id });
  });
  reason.addEventListener("input", () => {
    reason.dataset.typed = "1";
    if (changes[name]) changes[name].reason = reason.value;
    if (reason.getAttribute("aria-invalid") === "true") showProblems("policy", { only: rid });
    changed();
  });
  reason.addEventListener("blur", () => {
    if (reason.dataset.typed) showProblems("policy", { only: rid });
  });
  sync();
  return row;
}

const ILLUS_INFO = { topic: "ILLUSTRATIVE", label: "About ILLUSTRATIVE", text: "Your policy file stays ILLUSTRATIVE, not an airline SRA: TEPHRA cannot check an SRA. It records your numbers, reasons and SRA reference." };

function policyPage() {
  const p = V().policy;
  const out = [
    choiceCards({
      name: "ob-preset", legend: "Policy", value: "A", onChange: () => {},
      options: [
        { value: "A", title: "Policy A: avoid official ash", chips: [chipInfo(illus(), ILLUS_INFO)] },
        { value: "B", title: "Policy B: through, under, over", disabled: true,
          chips: [illus(), chipInfo(notBuilt(), { topic: "Policy B", label: "Why Policy B is not built", text: "No TEPHRA code applies a Policy B preset. The flight planner may still propose a level clear of the ash under Policy A." })] },
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
        el("summary", {}, el("span", { text: `More values (${more.length + recovery.length})` }), caret()),
        el("div", { class: "more__body" }, ...more.map((n) => valueRow(n, S.labels[n] || n)),
          recovery.length
            ? el("div", { class: "pfixed" },
              el("p", { class: "pfixed__h" }, el("b", { text: `Recovery values (${recovery.length})` }),
                chipInfo(notBuilt(), { topic: "recovery values", label: "Why recovery values stay fixed", text: "Only recovery re-planning reads these, and it is not built for your network." })),
              el("dl", { class: "kv" }, ...recovery.flatMap((n) => [el("dt", { text: S.labels[n] || n }), el("dd", { class: "mono", text: formatValue(n.split(".")[1], S.named[n]) })])))
            : null))));
  }
  out.push(
    section("Who owns it", "s-owner",
      el("div", { class: "row2" },
        field({ id: fid("policy.risk_owner"), label: "Risk owner", control: bound(input({ placeholder: "e.g. Director of Flight Operations", maxlength: 80 }), () => p.risk_owner, (v) => { p.risk_owner = v; }, "policy") }),
        field({ id: fid("policy.sra_ref"), label: "SRA reference", optional: true, hint: "Needed if you change a value.", control: bound(input({ mono: true, maxlength: 120 }), () => p.sra_ref, (v) => { p.sra_ref = v; }, "policy") }))));
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
    c.setAttribute("aria-describedby", `${id}-err${key === "seats" || key === "hex" ? " fleet-seats-hint" : ""}`);
    if (up) upperAsTyped(c);
    c.addEventListener("input", () => {
      c.dataset.typed = "1";
      row[key] = up ? c.value.toUpperCase() : c.value.trim().toLowerCase();
      if (c.getAttribute("aria-invalid") === "true") showProblems("fleet", { only: id });
      onEdit();
    });
    c.addEventListener("blur", () => {
      if (c.dataset.typed) showProblems("fleet", { only: id });
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
      el("p", {}, el("b", { text: "A CSV or fleet.json" }), el("br"), "Read in your browser; nothing is uploaded. ",
        infoButton({ topic: "the CSV columns", label: "About the CSV columns", text: "Columns: registration, type, seats, home base, hex. A header row is optional; commas or tabs." })),
      el("label", { class: "btn btn--secondary", for: "fleet-file" }, icon("i-file"), el("span", { text: "Choose a file" })), file),
    field({ id: "fleet-paste", label: "Or paste rows", control: paste }),
    el("div", { class: "tool" }, read,
      el("button", { type: "button", class: "linkbtn", dataset: { act: "tpl-fleet-csv" }, text: "Empty .csv" }),
      el("button", { type: "button", class: "linkbtn", dataset: { act: "tpl-fleet-json" }, text: "Empty fleet.json" })),
    result);
}

function fleetPage() {
  const f = V().fleet;
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
      onEdit: () => changed(),
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
        : el("p", { class: "hint", text: "No aircraft yet." }),
      more);
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
    el("div", { class: "section__h" }, countH,
      infoButton({ topic: "which flights are checked", label: "Which flights are checked", text: "Checked: flights filed with your callsign letters, these aircraft, and what you push. A flight filed under a registration stays on the map, unchecked." })),
    listErr("fleet.aircraft"), table,
    S.fleetTab === "type" ? el("div", { class: "tool" }, add) : null,
    el("p", { class: "hint infoline" }, el("span", { id: "fleet-seats-hint", text: "Seats: 0 for a freighter. Hex: the ICAO 24-bit address." }),
      infoButton({ topic: "the ICAO address", label: "Why the ICAO address", text: "It matches your aircraft even under another callsign, a wet lease or a codeshare. ADS-B carries no registrations." })));
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
  const prefixes = [...(f.extra_prefixes || [])];
  return [
    seg, panel,
    el("details", { class: "more more--page", open: prefixes.length || null },
      el("summary", {}, el("span", { text: "Add other callsign prefixes" }), caret()),
      el("div", { class: "more__body" },
        el("div", { class: "field" },
          chipsInput({ id: "fleet-prefixes", label: "Other callsign prefixes (optional)", values: prefixes, max: 4, placeholder: "3 letters, Enter to add", describedBy: `fleet-prefixes-hint ${fid("fleet.extra_prefixes")}-err`, onChange: (list) => {
            f.extra_prefixes = list;
            changed();
          } }),
          el("p", { id: "fleet-prefixes-hint", class: "hint", text: "Up to 4, 3 letters each." }),
          listErr("fleet.extra_prefixes")))),
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
          chipsInput({ id: altId, label: `Alternates at ${code} (optional)`, values: [...(n.alternates[code] || [])], max: 5, placeholder: "+ Alternate", describedBy: `${altId}-err`, onChange: (vals) => {
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
  const pick = el("input", { id: "ap-add", class: "input", list: "ob-airports", autocomplete: "off", spellcheck: "false", placeholder: "Search or type ICAO", "aria-describedby": "ap-add-err" });
  const addBtn = el("button", { type: "button", class: "btn btn--secondary" }, icon("i-plus"), el("span", { text: "Add airport" }));
  const add = () => {
    const code = airportCode(pick.value, S.airports);
    if (!code) {
      setError(pick, "4 letters, or one name from the list");
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
  pick.addEventListener("input", () => {
    if (pick.getAttribute("aria-invalid") === "true") setError(pick, null);
  });
  draw();
  return [
    section({ title: "Airports", info: { topic: "alternates", label: "About alternates", text: "Your alternates stay with your answers for your dispatchers. TEPHRA picks its own within your policy's search radius." } }, "s-airports",
      el("div", { class: "field" },
        el("label", { for: "ap-add", text: "Add an airport" }),
        el("div", { class: "addrow" }, pick, addBtn),
        el("p", { id: "ap-add-err", class: "err", hidden: true }),
        el("datalist", { id: "ob-airports" }, ...[...S.airports].map(([code, ap]) => el("option", { value: `${code}${ap.iata ? ` · ${ap.iata}` : ""} · ${ap.name}` })))),
      listErr("network.airports"),
      list,
      coverage),
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
        if (!r) return null;
        const remove = el("button", { type: "button", class: "linkbtn", "aria-label": `Remove ${k}.json`, text: "Remove" });
        remove.addEventListener("click", () => {
          const { [k]: _gone, ...rest } = S.local.files;
          S.local.files = rest;
          keepLocal();
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
      const kept = keepLocal();
      draw();
      if (kept !== "ok") out.prepend(note("caution", null, `This browser could not keep ${k}.json: add it again if you reload.`));
      announce(`${k}.json read.`);
    });
    return el("div", { class: "drop" },
      el("span", { class: "drop__ic" }, icon("i-file")),
      el("p", {}, el("b", { text: `${k}.json` }),
        k === "crews" ? [" ", chipInfo(notBuilt(), { topic: "crew re-planning", label: "About crew re-planning", text: "Recovery re-planning for your network is not built." })] : null,
        el("br"), k === "flights" ? "One day's flights." : "Crews, with base and report time."),
      el("label", { class: "btn btn--secondary", for: id }, icon("i-file"), el("span", { text: `Choose ${k}.json` })), f);
  };
  const node = [
    section("Your files", "s-files",
      el("p", { class: "section__sub", text: "Read in your browser; only counts are sent." }),
      fileInput("flights"), fileInput("crews"),
      el("div", { class: "tool" },
        el("button", { type: "button", class: "linkbtn", dataset: { act: "tpl-flights" }, text: "Empty flights.json" }),
        el("button", { type: "button", class: "linkbtn", dataset: { act: "tpl-crews" }, text: "Empty crews.json" })),
      listErr("schedule.files"),
      out),
  ];
  window.queueMicrotask(draw);
  return node;
}

// --- page 6 · Data feeds ---------------------------------------------------------------------------

function feedsPage() {
  const f = V().feeds;
  const none = el("p", { class: "hint", text: "None ticked: public ADS-B only." });
  const syncNone = () => {
    none.hidden = Boolean(f.positions || f.flight_plans || f.pilot_reports);
  };
  // the (i) sits beside the hint, outside the label, so it never ticks the box
  const box = (key, label, hint, info) => {
    const c = el("input", { type: "checkbox", id: `feeds-${key}`, checked: Boolean(f[key]), "aria-describedby": `feeds-${key}-hint` });
    c.addEventListener("change", () => {
      f[key] = c.checked;
      syncNone();
      changed();
    });
    return el("div", { class: "checkrow" }, el("label", { class: "check" }, c, el("b", { text: label })),
      el("p", { class: "hint infoline" }, el("span", { id: `feeds-${key}-hint`, text: hint }), info ? infoButton(info) : null));
  };
  syncNone();
  return [
    section("What you send", "s-send",
      box("positions", "Positions", "From your own tracking.", { topic: "positions", label: "About positions", text: "Each carries the ICAO 24-bit address and its measurement time, within 5 minutes of TEPHRA's clock. Only airline-style callsigns (RFA1654) are checked." }),
      box("flight_plans", "Flight plans", "Routes and times.", { topic: "flight plans", label: "About flight plans", text: "They draw your routes on the maps and feed the closed-airport check." }),
      box("pilot_reports", "Pilot reports", "Where crews saw ash.", { topic: "pilot reports", label: "About pilot reports", text: "Special air-reports (AIREP SPECIAL, VAR) become caution areas. They never shrink the official one." }),
      none,
      field({ id: fid("feeds.source_system"), label: "Source system", optional: true, control: bound(input({ placeholder: "e.g. our flight-following system", maxlength: 80 }), () => f.source_system, (v) => { f.source_system = v; }, "feeds") })),
    el("details", { class: "more more--page" },
      el("summary", {}, el("span", { text: "Format: tephra.airline/1" }), caret()),
      el("div", { class: "more__body" },
        el("p", { class: "body2" }, "One JSON push with any of three sections. ", el("a", { class: "link", href: PATHS.schema, download: "", text: "Schema (JSON)" })),
        el("p", { class: "body2", text: "Once you submit, try a file in the dry run in your workspace." }))),
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
          name.setAttribute("aria-describedby", `${nid}-err`);
          name.addEventListener("input", () => {
            name.dataset.typed = "1";
            d.name = name.value;
            if (name.getAttribute("aria-invalid") === "true") showProblems("people", { only: nid });
            changed();
          });
          name.addEventListener("blur", () => {
            if (name.dataset.typed) showProblems("people", { only: nid });
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
    section({ title: "Dispatchers", info: { topic: "names", label: "About names", text: "Names stay in your airline's account and never reach a model." } }, "s-people",
      listErr("people.dispatchers"), box, el("div", { class: "tool" }, add)),
  ];
}

// --- page 8 · Assistant (AI model) -----------------------------------------------------------------

function assistantPage() {
  const choice = modelChoice(V().assistant, {
    onChange: () => {
      delete S.server.assistant;
      changed();
    },
    recheck: (id) => showProblems("assistant", { only: id }),
  });
  return [el("div", { class: "section" }, choice)];
}

// --- page 9 · Review -------------------------------------------------------------------------------

function allProblems() {
  const out = [];
  for (const key of ANSWER_PAGES) {
    for (const p of checkPage(key, V(), ctxFor(key))) out.push({ page: key, field: p.field, text: problemText(key, p) });
    for (const p of S.server[key] || []) out.push(p);
  }
  return out;
}

function reviewPage() {
  const answers = toAnswers(S.draft);
  return [
    el("div", { id: "ob-errors", class: "ob-errors", role: "alert", tabindex: "-1", hidden: true }),
    reviewList(answers, { named: S.named, labels: S.labels, problems: Object.fromEntries(ANSWER_PAGES.map((k) => [k, problemCount(k)])), unseen: new Set(ANSWER_PAGES.filter((k) => !S.draft.seen.includes(k))), editHref: (k) => `/onboard/${k}` }),
    el("p", { class: "hint", text: "A dispatcher verifies you next. You can still edit." }),
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
    el("p", { class: "ob-errors__h" }, icon("st-caution"), el("b", { text: n ? `Fix ${n === 1 ? "1 thing" : `${n} things`} before you submit` : "Not submitted" })),
    n ? el("ul", {}, ...items.slice(0, 12).map((p) => el("li", {}, problemLink(p)))) : null,
    n > 12 ? el("p", { class: "hint", text: `And ${n - 12} more.` }) : null,
    extra);
  box.hidden = false;
  box.focus();
}

function submitWords(res) {
  const code = errorCode(res);
  if (res.status === 429) return `Too many saves today. Try again in about ${waitWords(res)}.`;
  if (res.status === 503 && code === "onboarding_full") return "New airlines are paused on this server for now. Your answers stay in your account: submit again later.";
  if (res.status === 409) return "Your answers changed in another tab. Reload to see them.";
  if (res.status === 413) return "Your answers are too large to send (more than 128 KB).";
  if (res.status === 0) return "You're offline. Nothing was submitted.";
  return `Nothing was submitted (HTTP ${res.status}).`;
}

async function submitAnswers(button) {
  const problems = allProblems();
  if (problems.length) {
    errorSummary(problems);
    return;
  }
  const answers = toAnswers(S.draft);
  const raw = JSON.stringify({ version: S.me.version, answers });
  if (new TextEncoder().encode(raw).length > MAX_BODY_BYTES) {
    errorSummary([], el("p", { text: submitWords({ status: 413 }) }));
    return;
  }
  const words = button.querySelector("span");
  button.disabled = true;
  words.textContent = "Submitting…";
  const res = await call(PATHS.submit, { method: "POST", raw });
  button.disabled = false;
  words.textContent = "Submit for verification";
  if (res.ok || (res.status === 409 && errorCode(res) === "already_submitted")) {
    location.assign("/workspace");
    return;
  }
  if (res.status === 401) {
    location.assign("/signin");
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
  errorSummary([], el("p", { text: submitWords(res) }));
}

// --- one page --------------------------------------------------------------------------------------

const BUILDERS = { airline: airlinePage, policy: policyPage, fleet: fleetPage, network: networkPage, schedule: schedulePage, feeds: feedsPage, people: peoplePage, assistant: assistantPage, review: reviewPage };

function actionBar(key) {
  const i = PAGE_KEYS.indexOf(key);
  const bar = $("ob-actions");
  if (S.edit) {
    bar.replaceChildren(
      el("a", { class: "btn btn--secondary", href: "/workspace/answers", text: "‹ Your airline" }),
      el("p", { id: "ob-edit-status", class: "actions__mid actions__mid--keep", role: "status" }),
      el("button", { type: "submit", form: "ob-form", class: "btn btn--primary" }, el("span", { text: "Save changes" })));
    return;
  }
  const back = i === 0
    ? el("a", { class: "btn btn--secondary", href: "/workspace", dataset: { go: "" }, text: "‹ Your airline" })
    : el("a", { class: "btn btn--secondary", href: `/onboard/${PAGE_KEYS[i - 1]}`, dataset: { go: PAGE_KEYS[i - 1] }, text: "‹ Back" });
  const words = key === "review" ? "Submit for verification" : S.leaveAnyway === key ? "Next anyway ›" : `Next: ${pageOf(PAGE_KEYS[i + 1]).short} ›`;
  const next = el("button", { type: "submit", form: "ob-form", class: "btn btn--primary" }, el("span", { text: words }));
  const skip = key === "schedule" ? el("button", { type: "button", class: "btn btn--quiet", dataset: { act: "skip" }, text: "Skip for now" }) : null;
  // the middle says only a save that failed (sayNotSaved); the Saved mark says the rest
  put(bar, back, el("p", { class: "actions__mid" }), skip, next);
}

function renderPage(key) {
  const page = pageOf(key);
  document.title = `${page.name} · Onboard · TEPHRA`;
  // Where the airline is goes to the account with the page's next save; the values are what
  // the Saved mark speaks for.
  if (!S.edit) {
    if (!S.draft.seen.includes(key)) S.draft.seen.push(key);
    S.draft.at = key;
  }
  if (S.leaveAnyway !== key) S.leaveAnyway = null;
  const form = el("form", { id: "ob-form", class: "form", novalidate: true },
    el("div", { class: "form__head" },
      el("div", { class: "form__h1" }, el("h1", { text: page.h1 }), page.info ? infoButton({ topic: page.short, label: `About ${page.short}`, text: page.info }) : null),
      el("p", { text: page.why })),
    ...BUILDERS[key]());
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (key === "review") submitAnswers(e.submitter || $("ob-actions").querySelector(".btn--primary"));
    else if (S.edit) saveEdit(key);
    else next(key);
  });
  $("main").replaceChildren(form);
  drawSteps(key);
  actionBar(key);
  setSaved(S.dirty ? "" : "ok");
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
  // "Next anyway" stays offered until the save goes through (the next page clears it).
  saveAndGo(`/onboard/${PAGE_KEYS[PAGE_KEYS.indexOf(key) + 1]}`);
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
    status.textContent = "Saved. Your airline page shows the new answers.";
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

// --- the landing: the account first --------------------------------------------------------------

// What an airline provides, one line a page, in a fold the person opens when they want it.
function provideList() {
  return el("details", { id: "ob-provide", class: "provide" },
    el("summary", {}, el("span", { text: "What you will provide" }), caret()),
    el("ol", { class: "provide__list" }, ...PROVIDE.map((p, i) => el("li", { class: "provide__i" },
      el("span", { class: "provide__ic", "aria-hidden": "true" }, icon(p.icon)),
      el("p", {},
        el("b", {}, el("span", { class: "provide__n", text: String(i + 1) }), p.name),
        ` ${p.text}`, p.code ? el("code", { text: p.code }) : null)))));
}

function signupWords(res) {
  const code = errorCode(res);
  if (res.status === 409 && code === "email_taken") return el("p", {}, "An account with this email exists. ", el("a", { class: "link", href: "/signin", text: "Sign in instead." }));
  if (res.status === 429) return el("p", { text: `Too many tries from this address. Try again in about ${waitWords(res)}.` });
  if (res.status === 503 && code === "onboarding_full") return el("p", { text: "New airlines are paused on this server for now." });
  if (code === "accounts_off") return el("p", { text: ACCOUNTS_OFF });
  if (code === "feature_off") return el("p", { text: ONBOARD_OFF });
  if (res.status === 422) return el("p", { text: "Check the email and the password: the server refused them." });
  if (res.status === 0) return el("p", { text: "You're offline. No account was created." });
  return el("p", { text: `No account was created (HTTP ${res.status}).` });
}

async function createAccount(fields, button, box) {
  const v = fields.values();
  for (const id of ["acct-email", "acct-password", "acct-ack"]) setError($(id), null);
  box.hidden = true;
  const problems = fields.problems();
  for (const [id, msg] of problems) setError($(id), msg);
  if (problems.length) {
    $(problems[0][0]).focus();
    return;
  }
  const words = button.querySelector("span");
  button.disabled = true;
  words.textContent = "Creating…";
  const res = await call(PATHS.accounts, { method: "POST", body: { email: v.email, password: v.password, acknowledge: true, website: v.website } });
  button.disabled = false;
  words.textContent = "Create account";
  if (res.ok && typeof res.data?.recovery_code === "string" && res.data.airline) {
    fields.clearSecrets();
    S.recovery = { code: res.data.recovery_code, email: v.email, icao: null };
    S.me = res.data.airline;
    S.draft = draftOf(S.me.draft);
    S.dirty = false;
    // Answers an earlier version of these pages kept in this browser are offered, never moved in
    // unasked: on a shared computer they may be another airline's (done() asks).
    S.legacy = loadLegacyDraft();
    S.navMode = null;
    go("/onboard/done");
    return;
  }
  put(box, el("p", { class: "ob-errors__h" }, icon("st-caution"), el("b", { text: "No account was created" })), signupWords(res));
  box.hidden = false;
  box.focus();
}

function signupCard() {
  const fields = accountFields();
  const box = el("div", { id: "su-errors", class: "ob-errors", role: "alert", tabindex: "-1", hidden: true });
  const button = el("button", { type: "submit", class: "btn btn--primary btn--block", disabled: S.accounts ? null : true }, el("span", { text: "Create account" }));
  const off = S.accounts ? null : el("div", { class: "note note--caution", role: "status" }, icon("st-caution"),
    el("p", {}, ACCOUNTS_OFF, " ", infoButton({ topic: "the operator", label: "For the operator", text: ACCOUNTS_OFF_HOW })));
  const form = el("form", { id: "su-form", class: "authform", novalidate: true }, off, fields.node, box, button);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    createAccount(fields, button, box);
  });
  return el("section", { id: "ob-signup", class: "card signup", "aria-labelledby": "su-h" },
    el("h2", { id: "su-h", class: "h2", text: "Create your account" }),
    form,
    el("p", { class: "body2" }, "Have an account? ", el("a", { class: "link", href: "/signin", text: "Sign in" })),
    el("p", { id: "su-private", class: "infoline" }, icon("i-lock"), el("span", { text: "Private to your airline" }),
      infoButton({ topic: "who reads your answers", label: "Who reads your answers", text: WHO_READS, actions: [el("a", { class: "link", href: "/privacy", text: "Privacy" })] })));
}

function landing() {
  document.title = "Onboard your airline · TEPHRA";
  const me = S.account?.signedIn ? S.account : null;
  // Signed in, the airline has submitted already: its workspace, never a second account. When the
  // account did not load, the landing says so and claims nothing about the answers.
  const failed = me && S.meFail;
  const side = failed
    ? el("section", { id: "ob-signup", class: "card signup", "aria-labelledby": "su-h" },
      el("h2", { id: "su-h", class: "h2", text: "Your account did not load" }),
      el("p", { class: "err err--alarm", role: "alert", text: failWords(S.meFail) }))
    : me
    ? el("section", { id: "ob-signup", class: "card signup", "aria-labelledby": "su-h" },
      el("h2", { id: "su-h", class: "h2", text: "Answers submitted" }),
      el("p", { class: "body2", text: `Signed in as ${[me.icao, me.name].filter(Boolean).join(" · ")}.` }),
      el("a", { id: "ob-start", class: "btn btn--primary btn--block", href: "/workspace" }, el("span", { text: "Open your workspace" }), icon("i-arrow-right")))
    : signupCard();
  $("main").replaceChildren(el("div", { class: "ostart" },
    el("div", { class: "ostart__head" },
      el("h1", { class: "h1", text: "Set TEPHRA up for your airline" })),
    side,
    el("div", { class: "ostart__side" },
      provideList(),
      el("p", { id: "ob-notyet", class: "notyet" }, icon("i-info"), el("span", { text: siteLine(has("hosted")) })))));
}

// --- done and off ----------------------------------------------------------------------------------

function done() {
  document.title = "Recovery code · Onboard · TEPHRA";
  const key = firstUnfinished(S.draft, ctxFor);
  $("main").replaceChildren(recoveryCard(S.recovery, {
    lead: "Shown once. Your way back if you forget your password.",
    chip: "Email reset: not built",
    next: { href: `/onboard/${key}`, text: `Continue: ${pageOf(key).short}`, go: true },
    extra: S.legacy ? legacyOffer() : null,
  }));
}

// Answers an earlier version of these pages kept in this browser: the new account takes them only
// when asked; Discard removes them from the browser.
function legacyOffer() {
  const when = S.legacy?.at ? new Date(S.legacy.at) : null;
  const dated = when && !Number.isNaN(when.getTime()) ? ` (${when.toISOString().slice(0, 10)})` : "";
  const use = el("button", { type: "button", class: "btn btn--secondary btn--sm" }, el("span", { text: "Use them" }));
  const drop = el("button", { type: "button", class: "btn btn--quiet btn--sm" }, el("span", { text: "Discard" }));
  const said = el("p", { class: "body2", role: "status" });
  const box = el("div", { id: "ob-legacy", class: "legacy", role: "group", "aria-labelledby": "lg-h" },
    el("p", { id: "lg-h", class: "body2" }, el("b", { text: `Answers from an earlier visit are in this browser${dated}.` }), " Not yours? Discard."),
    el("div", { class: "legacy__act" }, use, drop), said);
  const settle = (words) => {
    S.legacy = null;
    box.querySelector(".legacy__act").remove();
    said.textContent = words;
    const next = $("main").querySelector(".auth__card a.btn--primary");
    const key = firstUnfinished(S.draft, ctxFor);
    if (next) { next.href = `/onboard/${key}`; next.querySelector("span").textContent = `Continue: ${pageOf(key).short}`; }
  };
  use.addEventListener("click", async () => {
    use.disabled = drop.disabled = true;
    S.draft = draftOf(S.legacy);
    S.dirty = true;
    const ok = await saveDraft();
    if (ok) settle("Answers added.");
    else use.disabled = drop.disabled = false;
  });
  drop.addEventListener("click", () => {
    dropLegacyDraft();
    settle("Discarded.");
  });
  return box;
}

function offCard(words) {
  document.title = "Onboard your airline · TEPHRA";
  $("main").replaceChildren(el("div", { class: "narrow" }, el("section", { class: "card authcard" },
    el("h1", { class: "h2", text: words }),
    el("a", { class: "btn btn--primary btn--block", href: "/demo" }, el("span", { text: "Watch the demo" }), icon("i-arrow-right")))));
}

// --- render ----------------------------------------------------------------------------------------

// The signed-in airline's record, read once per page load (null when signed out or the session
// has ended). A draft's pages come from it.
async function loadMe() {
  if (S.me || !S.account?.signedIn) return S.me;
  const res = await call(PATHS.me);
  S.meFail = res.ok && res.data ? null : res;
  if (!S.meFail) {
    S.me = res.data;
    if (S.me.status === "draft") S.draft = draftOf(S.me.draft);
  }
  return S.me;
}

function redirect(path, opts) {
  history.replaceState(null, "", path);
  return render(opts);
}

async function render({ keepFocus = false } = {}) {
  const r = route();
  if (S.state && !has("onboard")) {
    frame("off");
    offCard(ONBOARD_OFF);
    focusHeading();
    return;
  }
  const navMode = r.view === "landing" ? "landing" : "page";
  if (navMode !== S.navMode) {
    S.navMode = navMode;
    S.account = await initAccountNav({ right: $("tn-right"), signin: navMode !== "landing" });
  }
  const me = await loadMe();
  const draft = me?.status === "draft";
  // a draft's cookie names no airline: the account button says what page 1 holds, as the workspace does
  if (draft) showAccountWho({ icao: (V().airline?.icao || "").trim().toUpperCase(), name: (V().airline?.name || "").trim() });
  if (r.view === "page" && r.edit) {
    if (!me) {
      location.replace(`/signin?next=${encodeURIComponent(`${location.pathname}?edit=1`)}`);
      return;
    }
    if (!me.editable) {
      location.replace("/workspace/answers");
      return;
    }
    if (!S.edit) {
      S.edit = me;
      S.draft = { seen: [...ANSWER_PAGES], at: null, values: fromAnswers(me.answers, S.named) };
    }
  } else if (S.edit) {
    S.edit = null;
  }
  // Pages need the account; a submitted airline edits from its workspace; a draft resumes.
  if (r.view === "page" && !r.edit && !draft) {
    if (me) location.replace("/workspace/answers");
    else await redirect("/onboard", { keepFocus });
    return;
  }
  if (draft && (r.view === "landing" || (r.view === "done" && !S.recovery))) {
    await redirect(`/onboard/${firstUnfinished(S.draft, ctxFor)}`, { keepFocus });
    return;
  }
  if (r.view === "done" && !S.recovery) {
    await redirect(me ? "/workspace" : "/onboard", { keepFocus });
    return;
  }
  frame(r.view);
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

document.addEventListener("click", (e) => {
  const t = e.target.closest("a[data-go], [data-act]");
  if (!t || e.defaultPrevented) return;
  if (t.tagName === "A" && t.dataset.go !== undefined) {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    const href = t.getAttribute("href");
    if (document.body.dataset.view === "page" && !S.edit) saveAndGo(href);
    else go(href);
    return;
  }
  const act = t.dataset.act;
  if (act === "skip") {
    V().schedule = { skipped: true, summary: null };
    S.local.files = {};
    keepLocal();
    S.flagged.delete("schedule");
    S.leaveAnyway = null;
    changed();
    saveAndGo("/onboard/feeds");
  } else if (TEMPLATES[act]) download(...TEMPLATES[act]);
});

window.addEventListener("popstate", () => render());
window.addEventListener("pagehide", saveOnLeave);

async function boot() {
  inlineSprite();
  S.local = loadLocal();
  await loadContext();
  await render();
}

boot();
