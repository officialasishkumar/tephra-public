// Settings › Policy (SPEC-FINAL 5.6, mockup a-settings-policy.html): the ash policy every draft is
// made with, from GET /api/tenant/policy (PolicyTab). The current version's values with their base
// and the version that changed them (recovery values "Not built for your network"); a change makes
// version n+1 and needs a reason per value; an ops manager confirms the version the go-live
// checklist needs; and the acceptance under the airline's own SRA is recorded by the airline,
// never checked by TEPHRA. Until it is recorded for the current version, the policy and every
// draft say ILLUSTRATIVE. Policy B stays Not built. Every string goes in through el().

import { el, icon } from "../wall/util.js";
import { api } from "../base.js";
import { policyValues, formatValue } from "../wall/policy.js";
import { personName, whenWords } from "../tenant-nav.js";
import { can, call, errorWords, pageHead, loadingCard, failCard, openDialog, inlineStatus, announce, refocus } from "../hosted.js";
import { reloadTenantHeader } from "../tenant-nav.js";

export const TITLE = "Ash policy";
export const LEAD = "The margins every draft is made with. Each change makes a new version with its reason.";
export const NOT_BUILT_NETWORK = "Not built for your network";
const ms = (iso) => (iso ? Date.parse(iso) : NaN);
const isIllustrative = (p) => String(p.label || "").startsWith("ILLUSTRATIVE");
// "17 Oct 2026" from "2026-10-17"
export function dateWords(day) {
  const t = Date.parse(`${day}T00:00:00Z`);
  if (!Number.isFinite(t)) return String(day || "");
  const d = new Date(t);
  return `${d.getUTCDate()} ${["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

// The version that last changed a value (the newest version naming it), or null when it is as Policy A.
export function changedIn(p, name) {
  const v = (p.versions || []).filter((x) => (x.changed || []).includes(name)).sort((a, b) => b.version - a.version)[0];
  return v ? v.version : null;
}

// PolicyTab.values as the demo's policy dialog groups them (wall/policy.js), so a value reads the
// same here and there.
export function valueGroups(p) {
  const blocks = {};
  for (const v of p.values || []) {
    const [block, name] = v.name.split(".");
    (blocks[block] ||= {})[name] = { value: v.value, unit: v.unit };
  }
  const by = Object.fromEntries((p.values || []).map((v) => [v.name, v]));
  return policyValues(blocks).map((g) => ({ ...g, rows: g.rows.map((r) => ({ ...r, v: by[r.id] })) }));
}

export function sraCard(p, h, { editable, onRecord, onWithdraw }) {
  const n = p.current.version;
  const sra = p.sra;
  const accepted = sra && sra.version === n;
  if (accepted) {
    const withdraw = el("button", { type: "button", class: "btn btn--quiet btn--sm", text: "Withdraw acceptance…" });
    withdraw.addEventListener("click", onWithdraw);
    return el("section", { class: "card wcard sra sra--ok", "aria-labelledby": "sra-h" },
      el("div", { class: "wcard__h" }, el("span", { class: "wcard__ic", "aria-hidden": "true" }, icon("i-pen-line")), el("h2", { id: "sra-h", text: "Acceptance under your SRA" }),
        el("span", { class: "status status--ok" }, icon("st-ok"), el("span", { text: "Recorded" }))),
      el("p", { text: `Accepted under ${h.name}'s SRA by ${sra.accepted_by}, on ${dateWords(sra.accepted_on)}${sra.sra_ref ? ` (${sra.sra_ref})` : ""} · recorded by the airline, TEPHRA does not check it. Version v${n}.` }),
      el("p", { class: "hint", text: `Recorded by ${personName(sra.recorded?.by)}, ${whenWords(ms(sra.recorded?.at))}. A later change makes a new version, ILLUSTRATIVE until accepted again.` }),
      editable ? el("div", { class: "wcard__foot" }, withdraw) : null);
  }
  const older = sra && sra.version !== n ? el("p", { class: "hint", text: `Version v${sra.version} was accepted on ${dateWords(sra.accepted_on)}; v${n} is not.` }) : null;
  const status = inlineStatus("sra-status");
  const by = el("input", { id: "sra-by", class: "input", maxlength: "80", autocomplete: "off" });
  const on = el("input", { id: "sra-on", class: "input mono", type: "date" });
  const ref = el("input", { id: "sra-ref", class: "input mono", maxlength: "120", autocomplete: "off" });
  const tick = el("input", { type: "checkbox", id: "sra-tick" });
  const go = el("button", { type: "button", class: "btn btn--primary", text: `Record acceptance of v${n}` });
  go.addEventListener("click", () => onRecord({ by, on, ref, tick, status, go }));
  return el("section", { class: "card wcard sra", "aria-labelledby": "sra-h" },
    el("div", { class: "wcard__h" }, el("span", { class: "wcard__ic", "aria-hidden": "true" }, icon("i-pen-line")), el("h2", { id: "sra-h", text: "Acceptance under your SRA" }),
      el("span", { class: "status status--caution" }, icon("st-caution"), el("span", { text: "Not recorded" }))),
    el("p", { text: "Until an ops manager records that your safety risk assessment accepts this version, the policy and every draft made with it say ILLUSTRATIVE." }),
    older,
    editable ? [
      el("div", { class: "row3" },
        el("div", { class: "field" }, el("label", { for: "sra-by", text: "Accepted by" }), by),
        el("div", { class: "field" }, el("label", { for: "sra-on", text: "On" }), on),
        el("div", { class: "field" }, el("label", { for: "sra-ref" }, "SRA reference ", el("span", { class: "opt", text: "(optional)" })), ref)),
      el("label", { class: "check" }, tick, el("span", {}, el("b", { text: `Our SRA accepts version v${n}` }), " as shown below.")),
      el("div", { class: "wcard__foot" }, go, el("span", { class: "hint", text: "A later change makes a new version, ILLUSTRATIVE until accepted again." })),
      status,
    ] : null);
}

// The margins a dispatcher weighs first (mockup a-settings-policy): shown at once with every value
// a version changed; the rest are one tap away under "All n values".
export const KEY_VALUES = [
  "exposure.vertical_margin_ft", "reroute.buffer_nm", "reroute.max_extra_min", "planner.divert_within_min", "planner.hold_within_min",
  "alternates.search_radius_nm", "alternates.min_runway_m", "alternates.min_visibility_m", "fuel.hold_min",
];

function valueRows(p, groups, { notBuiltOnce }) {
  const rows = [];
  for (const g of groups) {
    // a group none of whose values is built for the airline's network says so once, on its heading
    const allNotBuilt = notBuiltOnce && g.rows.every((r) => r.v?.not_built);
    rows.push(el("tr", {}, el("th", { colspan: "3", scope: "colgroup", text: allNotBuilt ? `${g.title} · ${NOT_BUILT_NETWORK}` : g.title })));
    for (const r of g.rows) {
      const v = r.v;
      const changed = changedIn(p, r.id);
      const note = v.not_built ? (allNotBuilt ? "" : NOT_BUILT_NETWORK) : changed ? `changed in v${changed}` : "as Policy A";
      rows.push(el("tr", {},
        el("td", { text: r.label }),
        el("td", { class: changed ? "chg" : null, text: r.value }),
        el("td", { class: v.not_built ? "nb" : null, text: note })));
    }
  }
  return rows;
}

export function valuesCard(p, { editable, onChange }) {
  const n = p.current.version;
  const change = el("button", { type: "button", class: "btn btn--secondary btn--sm" }, icon("i-pencil"), el("span", { text: "Change a value…" }));
  change.addEventListener("click", onChange);
  const groups = valueGroups(p);
  const total = groups.reduce((k, g) => k + g.rows.length, 0);
  const key = groups.map((g) => ({ ...g, rows: g.rows.filter((r) => KEY_VALUES.includes(r.id) || changedIn(p, r.id)) })).filter((g) => g.rows.length);
  const shown = key.reduce((k, g) => k + g.rows.length, 0);
  const table = (gs, caption, opts) => el("table", { class: "mtable" }, el("caption", { class: "sr-only", text: caption }), el("tbody", {}, ...valueRows(p, gs, opts)));
  return el("section", { class: "card wcard", "aria-labelledby": "m-h" },
    el("div", { class: "wcard__h" }, el("span", { class: "wcard__ic", "aria-hidden": "true" }, icon("i-levels")), el("h2", { id: "m-h", text: `Margins in v${n}` }), editable ? change : null),
    shown < total
      ? [table(key, `Key policy values in version ${n}`, { notBuiltOnce: false }),
        el("details", { class: "mall" }, el("summary", { text: `All ${total} values` }), table(groups, `Every policy value in version ${n}`, { notBuiltOnce: true }))]
      : table(groups, `Policy values in version ${n}`, { notBuiltOnce: true }));
}

export function versionsCard(p, { editable, onConfirm }) {
  const n = p.current.version;
  const conf = p.confirmed;
  const confirmed = conf && conf.version === n;
  const confirm = el("button", { type: "button", class: "btn btn--primary btn--sm", text: `Confirm version ${n}` });
  confirm.addEventListener("click", onConfirm);
  const labels = Object.fromEntries((p.values || []).map((v) => [v.name, v]));
  const nameOf = (name) => valueGroups({ values: [labels[name] || { name, value: 0, unit: "" }] })[0]?.rows[0]?.label || name;
  // #versions: the go-live checklist's Policy link lands here, at Confirm
  return el("section", { id: "versions", class: "card wcard", "aria-labelledby": "v-h" },
    el("div", { class: "wcard__h" }, el("span", { class: "wcard__ic", "aria-hidden": "true" }, icon("i-clock")), el("h2", { id: "v-h", tabindex: "-1", text: "Versions" }),
      confirmed ? el("span", { class: "status status--ok" }, icon("st-ok"), el("span", { text: `v${n} confirmed` })) : editable ? confirm : el("span", { class: "status status--caution" }, icon("st-caution"), el("span", { text: `v${n} not confirmed` }))),
    confirmed ? null : el("p", { class: "hint", text: `An ops manager confirms the version TEPHRA runs with. Going live on TEPHRA needs version ${n} confirmed.` }),
    el("ol", { class: "vers" }, ...[...(p.versions || [])].sort((a, b) => b.version - a.version).map((v) => {
      const now = v.version === n;
      const what = v.changed && v.changed.length ? v.changed.map(nameOf).join(", ") : "Started from Policy A, TEPHRA's illustrative default";
      const note = now ? p.current.note : null;
      return el("li", {},
        el("span", { class: "vers__v", text: `v${v.version}` }),
        el("span", { class: "vers__what" },
          el("span", {}, what, now ? el("span", { class: "vers__now", text: "In use" }) : null),
          note ? el("q", { text: note }) : null,
          el("span", { class: "vers__who", text: `${personName(v.created?.by)} · ${whenWords(ms(v.created?.at))}${now && confirmed ? ` · confirmed by ${personName(conf.by)}, ${whenWords(ms(conf.at))}` : ""}` })),
        el("span"));
    })));
}

// ------------------------------------------------------------------ the page

export async function mount(host, h) {
  host.replaceChildren(pageHead(TITLE, LEAD), loadingCard("Ash policy"));
  const res = await call(api("/tenant/policy"));
  if (!res.ok || !res.data) {
    host.replaceChildren(pageHead(TITLE, LEAD), failCard(res, h, { title: "The policy did not load" }));
    return;
  }
  draw(host, h, res.data);
}

export function render(h, p, handlers = {}) {
  const editable = can(h, "ops_manager");
  const chip = isIllustrative(p) ? el("span", { class: "chip chip--illus", title: p.label, text: "ILLUSTRATIVE" }) : null;
  return [
    pageHead(TITLE, LEAD, chip),
    sraCard(p, h, { editable, onRecord: handlers.record, onWithdraw: handlers.withdraw }),
    valuesCard(p, { editable, onChange: handlers.change }),
    versionsCard(p, { editable, onConfirm: handlers.confirm }),
    el("section", { class: "card wcard policyb", "aria-labelledby": "pb-h" },
      el("div", { class: "wcard__h" }, el("span", { class: "wcard__ic", "aria-hidden": "true" }, icon("i-gauge")), el("h2", { id: "pb-h", text: "Policy B" }), el("span", { class: "chip chip--notbuilt", text: "Not built" })),
      el("p", { text: "A second policy to compare against is not built." })),
  ].filter(Boolean);
}

function draw(host, h, p) {
  const again = (data) => { draw(host, h, data); refocus(host, "#v-h"); reloadTenantHeader(); };
  host.replaceChildren(...render(h, p, {
    record: (f) => recordSra(h, p, f, again),
    withdraw: () => withdrawDialog(h, again),
    change: () => changeDialog(h, p, again),
    confirm: () => confirmVersion(h, p, again),
  }));
}

async function recordSra(h, p, { by, on, ref, tick, status, go }, again) {
  const n = p.current.version;
  const who = by.value.trim();
  if (who.length < 2) { status.say("Say who accepted it (2 to 80 characters)."); by.focus(); return; }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(on.value)) { status.say("Give the date of the acceptance."); on.focus(); return; }
  if (!tick.checked) { status.say(`Tick that your SRA accepts version v${n}.`); tick.focus(); return; }
  go.disabled = true;
  const res = await call(api("/tenant/policy/sra"), { method: "POST", body: { version: n, accepted_by: who, accepted_on: on.value, sra_ref: ref.value.trim() || null } });
  go.disabled = false;
  if (res.ok && res.data) { announce(`Acceptance of v${n} recorded.`); again(res.data); return; }
  status.say(res.status === 422 ? "The date cannot be in the future." : res.status === 409 ? `Version v${n} is no longer the current version. Reload to see the new one.` : errorWords(res, h));
}

function withdrawDialog(h, again) {
  const why = el("textarea", { id: "sra-why", class: "input textarea", rows: "3", maxlength: "300" });
  openDialog({
    id: "sraw", title: "Withdraw the acceptance?", goText: "Withdraw", tone: "serious",
    body: [el("p", { class: "body2", text: "The policy and every new draft say ILLUSTRATIVE again. The withdrawal goes into your record." }),
      el("div", { class: "field" }, el("label", { for: "sra-why", text: "Why" }), why)],
    go: async (status) => {
      const reason = why.value.trim();
      if (reason.length < 3) { status.say("Give a reason of at least 3 characters."); why.focus(); return false; }
      const res = await call(api("/tenant/policy/sra/withdraw"), { method: "POST", body: { reason } });
      if (res.ok && res.data) { again(res.data); announce("Acceptance withdrawn."); return true; }
      status.say(errorWords(res, h));
      return false;
    },
  });
}

async function confirmVersion(h, p, again) {
  const n = p.current.version;
  const res = await call(api("/tenant/policy/confirm"), { method: "POST", body: { version: n } });
  if (res.ok && res.data) { announce(`Version ${n} confirmed.`); again(res.data); return; }
  const btn = document.querySelector("#v-h")?.parentElement?.querySelector("button");
  const status = inlineStatus("confirm-status");
  btn?.after(status);
  status.say(res.status === 409 ? "A newer version exists. Reload to see it." : errorWords(res, h));
}

// The change dialog: every editable value with its base; each changed value needs its reason
// (10-300 characters); Save makes version n+1.
function changeDialog(h, p, again) {
  const rows = [];
  for (const g of valueGroups(p)) {
    for (const r of g.rows) {
      const v = r.v;
      if (!v.editable) continue;
      const id = `pv-${r.id.replace(/[^a-z0-9]+/gi, "-")}`;
      const val = el("input", { id, class: "input mono", type: "number", min: "0", max: "100000", step: "1", value: String(v.value), "aria-describedby": `${id}-base` });
      const why = el("textarea", { id: `${id}-why`, class: "input textarea", rows: "2", maxlength: "300" });
      const whyField = el("div", { class: "field", hidden: true }, el("label", { for: `${id}-why`, text: `Why it changes (10 to 300 characters)` }), why);
      why.reveal = () => { whyField.hidden = false; };
      val.addEventListener("input", () => { whyField.hidden = Number(val.value) === Number(v.value); });
      rows.push({ r, v, val, why, node: el("div", { class: "pchg__row" },
        el("div", { class: "pchg__top" }, el("label", { for: id }, r.label, el("small", { id: `${id}-base`, text: `now ${r.value} · Policy A ${formatValue(r.id.split(".")[1], { value: v.base, unit: v.unit })}` })), val),
        whyField) });
    }
  }
  const note = el("input", { id: "pv-note", class: "input", maxlength: "300", autocomplete: "off" });
  const { dlg } = openDialog({
    id: "pchg", title: `Change values: makes v${p.current.version + 1}`, goText: `Save v${p.current.version + 1}`,
    body: [el("p", { class: "body2", text: "Each value you change needs its reason (10 to 300 characters). The new version is ILLUSTRATIVE and not confirmed until an ops manager confirms it and your SRA acceptance is recorded again." }),
      el("div", { class: "pchg" }, ...rows.map((x) => x.node)),
      el("div", { class: "field" }, el("label", { for: "pv-note" }, "Note for the version ", el("span", { class: "opt", text: "(optional)" })), note)],
    go: async (status) => {
      const changes = [];
      for (const x of rows) {
        const value = Number(x.val.value);
        if (value === Number(x.v.value)) continue;
        if (!Number.isInteger(value) || value < 0 || value > 100000) { status.say(`${x.r.label}: a whole number from 0 to 100,000.`); x.val.focus(); return false; }
        const reason = x.why.value.trim();
        if (reason.length < 10) { status.say(`${x.r.label}: give its reason (at least 10 characters).`); x.why.reveal(); x.why.focus(); return false; }
        changes.push({ name: x.r.id, value, reason });
      }
      if (!changes.length) { status.say("Change at least one value."); return false; }
      const res = await call(api("/tenant/policy"), { method: "POST", body: { base_version: p.current.version, changes, note: note.value.trim() || null } });
      if (res.ok && res.data) { again(res.data); announce(`Version ${res.data.current.version} saved.`); return true; }
      const code = res.data?.error;
      status.say(code === "version_conflict" ? "Someone saved a newer version while you edited. Close this and reload to see it."
        : code === "policy_refused" ? `Refused: ${res.data?.detail || "a value breaks a rule of the policy"}.` : errorWords(res, h));
      return false;
    },
  });
  dlg.classList.add("pdlg--wide");
}
