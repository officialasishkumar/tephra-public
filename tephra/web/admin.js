// The operator console /admin (SPEC hosted §5.7, D9): TEPHRA's own operators, signed in with their
// own cookie, see every airline as a row (never its drafts, people or key), the free-tier meter and
// the hosted pass, and verify, approve hosting, suspend, resume or delete an airline's data, each
// destructive action behind a reason or the airline's code. /admin/join#<token> turns a one-time
// operator link into an account; the token leaves the address bar before anything else runs.
// Each note and dialog says one short line; what explains it sits behind the shared (i)
// (wall/info.js), and form errors are terse and wait until a typed field is left or the form is
// sent. Every string goes in through el() (textContent).

import { $, el, icon, inlineSprite } from "./wall/util.js";
import { applyFeatureNav, has, setFeatures } from "./wall/features.js";
import { themeControl } from "./theme.js";
import { ruleMessage } from "./onboard/pages.js";
import { checkOnLeave, field, infoTail, input, passwordInput, segmented, setError } from "./onboard/form.js";
import { infoButton } from "./wall/info.js";
import { call, errorCode, failWords, minutesWords, retryMinutes } from "./workspace/api.js";

export const ADMIN = {
  state: "/api/state",
  me: "/api/admin/me",
  signIn: "/api/admin/sign-in",
  signOut: "/api/admin/sign-out",
  airlines: "/api/admin/airlines",
  operators: "/api/admin/operators",
  operatorInvites: "/api/admin/operators/invites",
  inviteLookup: "/api/admin/invite/lookup",
  inviteAccept: "/api/admin/invite/accept",
  airline: (id, act) => `/api/admin/airlines/${encodeURIComponent(id)}/${act}`,
  tenant: (icao, act) => `/api/admin/tenants/${encodeURIComponent(icao)}/${act}`,
  operator: (k, act) => `/api/admin/operators/${encodeURIComponent(k)}/${act}`,
};

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const pad = (n) => String(n).padStart(2, "0");
const parse = (iso) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
};
export const day = (iso) => {
  const d = parse(iso);
  return d ? `${d.getUTCDate()} ${MON[d.getUTCMonth()]}` : "";
};
export const when = (iso) => {
  const d = parse(iso);
  return d ? `${d.getUTCDate()} ${MON[d.getUTCMonth()]}, ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC` : "";
};
const hms = (iso) => {
  const d = parse(iso);
  return d ? `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}Z` : "";
};
export const num = (n) => (Number.isFinite(n) ? n.toLocaleString("en-US") : "–");

// --- the airline rows: status shape and word, filters, the actions each status allows ------------

const RUNNING = new Set(["shadow", "live"]);
const TENANT = new Set(["setup", "shadow", "live", "suspended"]);
// A row's own state: "setup" is a verified airline with a checklist (its space exists).
export const rowState = (row) => (row.status === "verified" && row.checklist ? "setup" : row.status);
export const hasSpace = (row) => TENANT.has(rowState(row));
// What waits for an operator: an airline to verify (pending), or one the Desk verified whose
// hosting waits for approval (verified already, so never counted "to verify").
export const toVerify = (row) => row.status === "pending";
export const toApprove = (row) => row.status === "verified" && row.hosting === "desk" && !row.checklist;

const BADGE = {
  pending: "sbadge--pending",
  verified: "sbadge--verified",
  setup: "sbadge--verified",
  shadow: "sbadge--shadow",
  live: "sbadge--live",
  suspended: "sbadge--suspended",
  declined: "sbadge--declined",
  deleting: "sbadge--deleted",
  deleted: "sbadge--deleted",
};
export const FILTERS = [
  ["all", "All", () => true],
  ["verify", "To verify", toVerify],
  ["approve", "Approve hosting", toApprove],
  ["running", "Running", (r) => RUNNING.has(r.status)],
  ["suspended", "Suspended", (r) => r.status === "suspended"],
];

// Delete data opens 7 days after suspension (S11): until then the button says from when.
export function deleteOpen(row, now = Date.now()) {
  const at = parse(row.delete_after);
  return Boolean(at) && now >= at.getTime();
}

// { primary: [label, kind, disabledWhy] | null, menu: [[label, kind, disabledWhy]] } for a row.
export function rowActions(row, list, now = Date.now()) {
  const state = rowState(row);
  const full = Boolean(list.limit_reached);
  const menu = [];
  let primary = null;
  if (toVerify(row)) primary = ["Review…", "review", null];
  else if (toApprove(row)) primary = ["Approve hosting…", "approve", null];
  else if (state === "setup" || RUNNING.has(state)) primary = ["Suspend…", "suspend", null];
  else if (state === "suspended") {
    primary = ["Resume…", "resume", full ? `Airline limit reached: ${list.slots.used} of ${list.slots.max} places in use` : null];
    menu.push(["Delete data…", "delete", deleteOpen(row, now) ? null : `From ${when(row.delete_after)}`]);
  }
  if (row.status !== "deleted" && row.status !== "deleting") menu.push(["Contact", "contact", null]);
  if (hasSpace(row)) menu.push(["New ops-manager link…", "opsinvite", null]);
  return { primary, menu };
}

// The free-tier figures: a cap reached is red, past 80 % caution.
export function level(used, cap) {
  if (!Number.isFinite(used) || !Number.isFinite(cap) || cap <= 0) return "";
  if (used >= cap) return "over";
  return used / cap >= 0.8 ? "hi" : "";
}
// The caps pause the airlines on what the airlines themselves used; the demo's use is shown and
// never pauses them.
export function siteOver(meter) {
  return ["reads", "writes", "deletes"].filter((k) => level(meter.airlines?.[k], meter.caps?.[k]) === "over");
}
// The whole site (the demo's visitors included) past a cap while the airlines are not.
export function siteOnlyOver(meter) {
  return ["reads", "writes", "deletes"].filter((k) => level(meter[k], meter.caps?.[k]) === "over" && level(meter.airlines?.[k], meter.caps?.[k]) !== "over");
}

// --- small builders ------------------------------------------------------------------------------

const statusLine = (id) => el("p", { id, class: "inline-alert", role: "status", hidden: true });
function say(line, words) {
  line.hidden = !words;
  line.replaceChildren(...(words ? [icon("st-caution"), el("span", { text: words })] : []));
}
function bar(used, cap, words, { title = null } = {}) {
  const lv = level(used, cap);
  const fill = el("i");
  if (Number.isFinite(used) && Number.isFinite(cap) && cap > 0) fill.style.setProperty("--w", `${Math.min(100, Math.round((used / cap) * 100))}%`);
  return el("div", { class: `mini${lv ? ` mini--${lv}` : ""}`, title }, el("span", { text: words }), el("span", { class: "mini__bar", "aria-hidden": "true" }, fill));
}
// `more`: { topic, text } behind the note's (i)
function note(kind, lead, text, more = null) {
  const info = more ? { topic: more.topic, label: `About ${more.topic}`, text: more.text } : null;
  const head = !lead ? [] : info && !text ? [el("b", {}, ...infoTail(lead, info))] : [el("b", { text: `${lead} ` })];
  const body = !text ? [] : info ? infoTail(text, info) : [text];
  return el("div", { class: `note note--${kind}`, role: kind === "serious" ? "alert" : "note" },
    icon(kind === "caution" || kind === "serious" ? "i-alert" : "i-info"), el("p", {}, ...head, ...body));
}
// A dialog's one line, with the rest behind its (i).
const leadLine = (text, more) => el("p", { class: "body2" }, ...(more ? infoTail(text, more) : [text]));
const RECORDED = "It goes into the airline's record.";

export function badge(row) {
  return el("span", { class: `sbadge ${BADGE[rowState(row)] || "sbadge--draft"}` }, el("i", { "aria-hidden": "true" }), String(row.status_label || row.status).toUpperCase());
}

function copyButton(text) {
  const b = el("button", { type: "button", class: "btn btn--secondary btn--sm" }, icon("i-clipboard"), el("span", { text: "Copy" }));
  b.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(text);
      b.lastChild.textContent = "Copied";
    } catch {
      b.lastChild.textContent = "Select it and copy";
    }
  });
  return b;
}

// A link shown once (operator invite, ops-manager link), with what to do with it.
export function onceBox(link, words) {
  return el("div", { class: "once", role: "status" },
    el("p", {}, el("b", { text: "Shown once. " }), words),
    el("div", { class: "once__row" }, el("code", { text: link }), copyButton(link)));
}

// --- the page parts -------------------------------------------------------------------------------

const S = { me: null, list: null, ops: null, filter: "all", token: null };

export function tiles(list) {
  const full = list.slots.used >= list.slots.max;
  const pass = list.last_pass;
  const m = list.meter;
  const nsRows = Object.entries(m.by_namespace || {}).map(([ns, v]) => el("tr", {},
    el("th", { scope: "row", text: ns === "demo" ? "Demo" : ns }),
    ...["reads", "writes", "deletes"].map((k) => {
      const over = ns !== "demo" && level(v[k], m.allowance?.[k]) === "over";
      return el("td", { class: over ? "is-over" : null, text: num(v[k]) });
    })));
  const blob = m.blob_puts || {};
  const rss = list.process || {};
  return el("div", { class: "acount" },
    el("div", { class: full ? "full" : null }, el("b", { text: `${list.slots.used} / ${list.slots.max}` }), el("span", { text: "places in use (shadow or live)" })),
    el("div", {}, el("b", { text: num(list.to_verify + (list.to_approve || 0)) }), el("span", { text: "waiting for an operator" })),
    el("div", {}, el("b", { text: pass ? `${pass.seconds.toFixed(1)} s` : "–" }), el("span", { text: pass ? `last hosted pass, of ${pass.budget_s} s · ${hms(pass.at)}` : "no hosted pass on this instance yet" })),
    el("div", {}, el("b", { text: num(list.advisories_waiting) }), el("span", { text: "advisories waiting, all airlines" })),
    el("section", { class: "ftile", "aria-labelledby": "ft-h" },
      el("div", { class: "ftile__h" }, el("h2", { id: "ft-h", text: "Free tier today" }),
        infoButton({ topic: "the free tier", label: "About the free-tier bars", text: "The bars count the whole site, the demo included. The airlines pause on what they used together, never on the demo's use." }),
        el("span", { class: "tdim", text: `Pacific day ${day(m.day)} · counted since ${when(m.counted_since)} on this instance` })),
      el("div", { class: "ftile__bars" },
        ...["reads", "writes", "deletes"].map((k) => bar(m[k], m.caps?.[k], `${num(m[k])} / ${num(m.caps?.[k])} ${k} · airlines ${num(m.airlines?.[k])}`)),
        bar(blob.used, blob.cap, `${num(blob.used)} / ${num(blob.cap)} file uploads in ${blob.month || "this month"}`),
        bar(rss.rss_mb, rss.limit_mb, `${num(rss.rss_mb)} / ${num(rss.limit_mb)} MB memory`)),
      nsRows.length
        ? el("table", { class: "ntable" },
          el("caption", { class: "tdim", text: `Each airline's own daily allowance: ${num(m.allowance?.reads)} reads, ${num(m.allowance?.writes)} writes, ${num(m.allowance?.deletes)} deletes` }),
          el("thead", {}, el("tr", {}, el("th", { scope: "col", text: "Who" }), el("th", { scope: "col", text: "Reads" }), el("th", { scope: "col", text: "Writes" }), el("th", { scope: "col", text: "Deletes" }))),
          el("tbody", {}, ...nsRows))
        : null));
}

export function notes(list) {
  const out = [];
  const over = siteOver(list.meter);
  if (over.length) out.push(note("serious", "Every airline is paused.", `The airlines together reached today's free ${over.join(" and ")} cap. They resume at 00:00 Pacific.`, { topic: "the pause", text: "The demo keeps answering." }));
  const busy = siteOnlyOver(list.meter);
  if (busy.length) out.push(note("caution", "The site is past its free daily cap.", `Mostly the demo's ${busy.join(" and ")}. No airline is paused for it.`, { topic: "the cap", text: "Each airline stops only at its own share." }));
  if (list.hosting !== "always-on") out.push(note("caution", "Hosted airlines need always-on.", "This site runs on demand.", { topic: "always-on", text: "Nothing ticks for the airlines. The owner changes the deploy's hosting mode." }));
  // the places tile says how many are in use; the note says what the limit means
  if (list.limit_reached) out.push(note("caution", "Airline limit reached.", null, { topic: "the limit", text: `This free-tier site runs at most ${list.slots.max} airlines in shadow or live.` }));
  if (list.unreadable_keys > 0) out.push(note("caution", `${list.unreadable_keys} ${list.unreadable_keys === 1 ? "airline's model key cannot" : "airlines' model keys cannot"} be read.`, "Each is asked for its key again.", { topic: "unreadable keys", text: "The key secret changed. The Assistant tab of each airline asks for its key again." }));
  if (list.onboarding > 0) out.push(note("info", null, `${list.onboarding} ${list.onboarding === 1 ? "airline is" : "airlines are"} still onboarding.`, { topic: "onboarding airlines", text: "Their answers stay private until they submit." }));
  return out;
}

function feedsCell(f) {
  if (!f) return el("span", { class: "tdim", text: "–" });
  const total = f.ok + f.stale + f.error;
  const tail = f.note ? ` · ${f.note}` : "";
  if (!total) return el("span", { class: "fh fh--quiet" }, icon("st-off"), el("span", { text: f.note ? f.note.replace(/^./, (c) => c.toUpperCase()) : "No feed declared" }));
  if (f.error) return el("span", { class: "fh fh--serious" }, icon("st-serious"), el("span", { text: `${f.error} of ${total} not received${tail}` }));
  if (f.stale) return el("span", { class: "fh fh--quiet" }, icon("st-off"), el("span", { text: `${f.ok} of ${total} receiving${tail}` }));
  return el("span", { class: "fh fh--ok" }, icon("st-ok"), el("span", { text: `${f.ok} of ${total} receiving${tail}` }));
}

function problemCell(row) {
  const out = [];
  if (row.chain_intact === false) out.push("Record chain broken");
  if (row.paused) out.push(`Paused: ${row.paused.scope === "site" ? "site" : "airline"} ${row.paused.reason} allowance used`);
  if (row.runtime_problem) out.push(row.runtime_problem);
  if (!out.length) return el("span", { class: "tdim", text: "None" });
  return el("ul", { class: "probs" }, ...out.map((t) => el("li", { class: "fh fh--serious" }, icon("st-serious"), el("span", { text: t }))));
}

function sinceWords(row) {
  const state = rowState(row);
  if (state === "pending") return `submitted ${day(row.state_since)}`;
  if (state === "setup") return `setting up · checklist ${row.checklist}`;
  if (state === "suspended" && row.delete_after) return `since ${day(row.state_since)} · data deleted from ${day(row.delete_after)}`;
  return `since ${day(row.state_since)}`;
}

let menuSeq = 0;
function rowMenu(row, items) {
  menuSeq += 1;
  const id = `am-${menuSeq}`;
  const button = el("button", { type: "button", class: "btn btn--quiet btn--sm", "aria-haspopup": "menu", "aria-expanded": "false", "aria-controls": id },
    icon("i-more"), el("span", { class: "sr-only", text: `More for ${row.name}` }));
  const menu = el("div", { id, class: "tn-menu amenu", role: "menu", "aria-label": `More for ${row.name}`, hidden: true },
    ...items.map(([label, kind, why]) => el("button", { type: "button", role: "menuitem", class: `tn-menu__item${kind === "delete" ? " tn-menu__item--danger" : ""}`, dataset: { act: kind }, disabled: why ? true : null, "aria-disabled": why ? "true" : null },
      el("span", { text: label }), why ? el("small", { class: "tdim", text: ` ${why}` }) : null)));
  const entries = () => [...menu.querySelectorAll('[role="menuitem"]:not([disabled])')];
  const setOpen = (open, focus = false) => {
    menu.hidden = !open;
    button.setAttribute("aria-expanded", String(open));
    if (open && focus) entries()[0]?.focus();
  };
  button.addEventListener("click", () => setOpen(menu.hidden, true));
  menu.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
      button.focus();
      return;
    }
    const list = entries();
    const at = list.indexOf(document.activeElement);
    if (at < 0 || !["ArrowDown", "ArrowUp"].includes(e.key)) return;
    e.preventDefault();
    list[(at + (e.key === "ArrowDown" ? 1 : -1) + list.length) % list.length].focus();
  });
  menu.addEventListener("click", (e) => {
    const item = e.target.closest("[data-act]");
    if (!item || item.disabled) return;
    setOpen(false);
    act(item.dataset.act, row);
  });
  const wrap = el("div", { class: "amenu-wrap" }, button, menu);
  wrap.addEventListener("focusout", (e) => {
    if (!wrap.contains(e.relatedTarget)) setOpen(false);
  });
  return wrap;
}

export function rowNode(row, list, now = Date.now()) {
  const { primary, menu } = rowActions(row, list, now);
  const pb = primary ? el("button", { type: "button", class: `btn ${primary[1] === "review" || primary[1] === "approve" ? "btn--secondary" : "btn--quiet"} btn--sm`, dataset: { act: primary[1] }, disabled: primary[2] ? true : null, title: primary[2] }, el("span", { text: primary[0] })) : null;
  if (pb) pb.addEventListener("click", () => act(primary[1], row));
  return el("tr", { dataset: { icao: row.icao } },
    el("td", { "data-l": "Airline", class: "wide" }, el("div", { class: "air" }, el("span", { class: "ah-air__code", "aria-hidden": "true", text: row.icao }), el("span", {}, el("b", { text: row.name }), el("small", { text: row.ops_email })))),
    el("td", { "data-l": "Status" }, badge(row), el("br"), el("span", { class: "tdim", text: sinceWords(row) })),
    el("td", { "data-l": "Feeds" }, feedsCell(row.feeds)),
    el("td", { "data-l": "AI use today" }, row.ai && row.ai.length ? el("div", { class: "minis" }, ...row.ai.map((a) => bar(a.used, a.budget, `${a.model}: ${num(a.used)} / ${num(a.budget)}`, { title: `${a.model}: ${num(a.used)} of ${num(a.budget)} calls today on the airline's key` }))) : el("span", { class: "tdim", text: "–" })),
    el("td", { "data-l": "Advisories waiting", text: hasSpace(row) ? num(row.advisories_waiting) : "–" }),
    el("td", { "data-l": "Problem" }, problemCell(row)),
    el("td", { class: "wide" }, el("div", { class: "tacts" }, pb, menu.length ? rowMenu(row, menu) : null), primary && primary[2] ? el("p", { class: "tdim tacts__why", text: primary[2] }) : null));
}

export function airlinesCard(list, filter, onFilter, now = Date.now()) {
  const pred = (FILTERS.find(([k]) => k === filter) || FILTERS[0])[2];
  const rows = list.rows.filter(pred);
  return el("section", { class: "card wcard", "aria-labelledby": "al-h" },
    el("h2", { id: "al-h", class: "sr-only", text: "Airlines" }),
    segmented({
      label: "Show", idBase: "af", value: filter,
      tabs: FILTERS.map(([k, label, p]) => ({ key: k, text: `${label} · ${list.rows.filter(p).length}` })),
      onChange: onFilter,
    }),
    el("div", { id: "af-panel", role: "tabpanel", "aria-labelledby": `af-${filter}`, class: "atable-wrap" },
      rows.length
        ? el("table", { class: "atable" },
          el("thead", {}, el("tr", {}, ...["Airline", "Status", "Feeds", "AI use today", "Advisories waiting", "Problem"].map((h) => el("th", { scope: "col", text: h })), el("th", { scope: "col" }, el("span", { class: "sr-only", text: "Actions" })))),
          el("tbody", {}, ...rows.map((r) => rowNode(r, list, now))))
        : el("p", { class: "status status--quiet" }, icon("st-off"), el("span", { text: "No airline here." }))));
}

export function operatorsCard(ops, onChange) {
  const nameWords = () => {
    const nm = name.value.trim().replace(/\s+/g, " ");
    return !nm ? "Required" : nm.length < 2 || nm.length > 32 ? "2 to 32 characters" : null;
  };
  const name = checkOnLeave(input({ autocomplete: "off", maxlength: 32 }), nameWords);
  const email = checkOnLeave(input({ type: "email", autocomplete: "off", inputmode: "email", spellcheck: "false", autocapitalize: "off", maxlength: 254 }), () => ruleMessage("acct.email", email.value));
  const status = statusLine("op-status");
  const out = el("div", { id: "op-once" });
  const go = el("button", { type: "submit", class: "btn btn--secondary" }, el("span", { text: "Make an invite link" }));
  const form = el("form", { class: "opinvite", novalidate: true },
    field({ id: "op-name", label: "Name", control: name }),
    field({ id: "op-email", label: "Email", control: email }),
    el("div", { class: "opinvite__go" }, go), status);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const nm = name.value.trim().replace(/\s+/g, " ");
    const problems = [[name, nameWords()], [email, ruleMessage("acct.email", email.value)]];
    for (const [c, m] of problems) setError(c, m);
    const first = problems.find(([, m]) => m);
    if (first) {
      first[0].focus();
      return;
    }
    go.disabled = true;
    const res = await call(ADMIN.operatorInvites, { method: "POST", body: { name: nm, email: email.value.trim().toLowerCase() } });
    go.disabled = false;
    if (res.ok && res.data?.link) {
      out.replaceChildren(onceBox(res.data.link, `Email sending is not built: send it yourself. It works for ${email.value.trim().toLowerCase()} only, until ${when(res.data.expires_at)}.`));
      name.value = "";
      email.value = "";
      return;
    }
    say(status, errorCode(res) === "email_taken" ? "This email has an operator account already." : res.status === 429 ? `Too many invites today. Try again in ${minutesWords(retryMinutes(res))}.` : failWords(res));
  });
  const row = (op) => {
    const dis = op.disabled ? null : el("button", { type: "button", class: "btn btn--quiet btn--sm" }, el("span", { text: op.you ? "Disable yourself…" : "Disable…" }));
    if (dis) dis.addEventListener("click", () => disableDialog(op, onChange));
    return el("tr", {},
      el("td", { "data-l": "Operator", class: "wide" }, el("b", { text: op.name }), op.you ? el("small", { class: "tdim", text: " · you" }) : null),
      el("td", { "data-l": "Email", text: op.email }),
      el("td", { "data-l": "Added", text: day(op.created_at) }),
      el("td", { "data-l": "Last sign-in", text: op.last_sign_in_at ? when(op.last_sign_in_at) : "Never" }),
      el("td", { "data-l": "Status" }, op.disabled ? el("span", { class: "tdim", text: `Disabled ${day(op.disabled.at)} by ${String(op.disabled.by).split("#")[0].replace(/^operator:/, "")}` }) : el("span", { text: "Active" })),
      el("td", { class: "wide" }, el("div", { class: "tacts" }, dis)));
  };
  return el("section", { class: "card wcard", "aria-labelledby": "op-h" },
    el("div", { class: "wcard__h" }, el("span", { class: "wcard__ic", "aria-hidden": "true" }, icon("i-user")), el("h2", { id: "op-h", text: "Operators" })),
    el("table", { class: "atable optable" },
      el("thead", {}, el("tr", {}, ...["Operator", "Email", "Added", "Last sign-in", "Status"].map((h) => el("th", { scope: "col", text: h })), el("th", { scope: "col" }, el("span", { class: "sr-only", text: "Actions" })))),
      el("tbody", {}, ...ops.map(row))),
    el("h3", { class: "h3", text: "Invite an operator" }),
    form, out);
}

// --- the actions ------------------------------------------------------------------------------------

function dialog(headingId, ...kids) {
  const dlg = $("ad-dlg");
  const form = el("form", { class: "pdlg__form", novalidate: true }, ...kids);
  dlg.replaceChildren(form);
  dlg.setAttribute("aria-labelledby", headingId);
  dlg.showModal();
  return { dlg, form };
}
const cancelButton = (dlg) => {
  const b = el("button", { type: "button", class: "btn btn--secondary", text: "Cancel" });
  b.addEventListener("click", () => dlg.close());
  return b;
};
const ACT_WORDS = {
  wrong_state: "Its state changed meanwhile. Reload to see it.",
  airline_limit_reached: "All airline places are in use.",
  site_memory: "The site's memory is full.",
  too_soon: "Its data can be deleted only 7 days after suspension.",
  last_operator: "The last active operator cannot be disabled.",
  version_conflict: "Someone changed this airline meanwhile. Reload to see it.",
};
const actWords = (res) => ACT_WORDS[errorCode(res)] || (res.status === 409 ? "Someone changed this airline meanwhile. Reload to see it." : failWords(res));

// One confirm dialog: `reason` asks for a reason of min-max characters, `typeIcao` for the code.
// `lead` is the one line, `more` ({ topic, text }) what sits behind its (i), `record` a "Goes into
// the record" line.
const reasonWords = (box, [lo, hi]) => {
  const t = box.value.trim();
  return !t ? "Required" : t.length < lo || t.length > hi ? `${lo} to ${hi} characters` : null;
};
function confirmAct({ row, title, lead, more = null, go, serious = false, reason = null, typeIcao = false, send, done = "reload" }) {
  const id = "ad-h";
  const reasonBox = reason ? checkOnLeave(el("textarea", { class: "input textarea", rows: "3", maxlength: reason[1] }), () => reasonWords(reasonBox, reason)) : null;
  const icaoBox = typeIcao ? input({ autocomplete: "off", spellcheck: "false", autocapitalize: "characters", maxlength: 3 }) : null;
  const status = statusLine("ad-status");
  const button = el("button", { type: "submit", class: `btn ${serious ? "btn--serious" : "btn--primary"}` }, el("span", { text: go }));
  const { dlg, form } = dialog(id,
    el("h2", { id, class: "h2", text: title }),
    leadLine(lead, more ? { topic: more.topic, label: `About ${more.topic}`, text: more.text } : null),
    reasonBox ? field({ id: "ad-reason", label: "Reason", rule: `${reason[0]} to ${reason[1]} characters`, control: reasonBox,
      info: { topic: "the reason", label: "Who reads the reason", text: "The airline reads it in its record." } }) : null,
    icaoBox ? field({ id: "ad-icao", label: `Type ${row.icao} to confirm`, control: icaoBox }) : null,
    status,
    el("div", { class: "pdlg__acts" }, null, button));
  form.querySelector(".pdlg__acts").prepend(cancelButton(dlg));
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (reasonBox) {
      const bad = reasonWords(reasonBox, reason);
      setError(reasonBox, bad);
      if (bad) {
        reasonBox.focus();
        return;
      }
    }
    if (icaoBox) {
      const bad = !icaoBox.value.trim() ? "Required" : icaoBox.value.trim() !== row.icao ? `Type ${row.icao}` : null;
      setError(icaoBox, bad);
      if (bad) {
        icaoBox.focus();
        return;
      }
    }
    button.disabled = true;
    const res = await send({ reason: reasonBox?.value.trim(), icao: icaoBox?.value.trim() });
    button.disabled = false;
    if (res.ok) {
      if (done === "reload") {
        dlg.close();
        await refresh();
        focusRow(row.icao);
      } else done(res, form, status);
      return;
    }
    say(status, actWords(res));
  });
  (reasonBox || icaoBox || button).focus();
}

function reviewDialog(row) {
  const id = "ad-h";
  const noteBox = el("textarea", { class: "input textarea", rows: "2", maxlength: 300 });
  const reasonBox = checkOnLeave(el("textarea", { class: "input textarea", rows: "2", maxlength: 500 }), () => reasonWords(reasonBox, [3, 500]));
  const status = statusLine("ad-status");
  const verify = el("button", { type: "button", class: "btn btn--primary" }, el("span", { text: "Verify" }));
  const decline = el("button", { type: "button", class: "btn btn--serious" }, el("span", { text: "Decline…" }));
  const { dlg } = dialog(id,
    el("h2", { id, class: "h2", text: `Review ${row.name} (${row.icao})` }),
    leadLine(`Check who they are: write to ${row.ops_email} from an address you trust.`,
      { topic: "verifying", label: "About verifying", text: "Ask them to confirm the airline's name, its code and who is asking. Verifying also approves hosting here; it does not approve their policy." }),
    field({ id: "ad-note", label: "Note", optional: true, rule: "Up to 300 characters", control: noteBox,
      info: { topic: "the note", label: "About the note", text: "Kept with the decision." } }),
    field({ id: "ad-reason", label: "Reason, to decline", rule: "3 to 500 characters", control: reasonBox,
      info: { topic: "the reason", label: "Who reads the reason", text: "The airline reads it in its record." } }),
    status,
    el("div", { class: "pdlg__acts" }, cancelButton(dlg), decline, verify));
  verify.addEventListener("click", async () => {
    verify.disabled = true;
    const note = noteBox.value.trim();
    const res = await call(ADMIN.airline(row.airline_id, "verify"), { method: "POST", body: note ? { version: row.version, note } : { version: row.version } });
    verify.disabled = false;
    if (res.ok) {
      dlg.close();
      await refresh();
      focusRow(row.icao);
      return;
    }
    say(status, actWords(res));
  });
  decline.addEventListener("click", async () => {
    const t = reasonBox.value.trim();
    const bad = reasonWords(reasonBox, [3, 500]);
    setError(reasonBox, bad);
    if (bad) {
      reasonBox.focus();
      return;
    }
    decline.disabled = true;
    const res = await call(ADMIN.airline(row.airline_id, "decline"), { method: "POST", body: { version: row.version, reason: t } });
    decline.disabled = false;
    if (res.ok) {
      dlg.close();
      await refresh();
      focusRow(row.icao);
      return;
    }
    say(status, actWords(res));
  });
  noteBox.focus();
}

async function contactDialog(row) {
  const id = "ad-h";
  const res = await call(ADMIN.tenant(row.icao, "contact"));
  const c = res.ok ? res.data : null;
  const { dlg } = dialog(id,
    el("h2", { id, class: "h2", text: `Contact ${row.name}` }),
    c
      ? el("dl", { class: "kv" }, el("dt", { text: "Contact" }), el("dd", { text: c.contact_name || "Not given" }), el("dt", { text: "Operations email" }), el("dd", { class: "mono", text: c.ops_email }))
      : el("p", { class: "err" }, icon("i-alert"), el("span", { text: failWords(res) })),
    el("div", { class: "pdlg__acts" }, cancelButton(dlg),
      c ? copyButton(c.ops_email) : null,
      c && /^mailto:/.test(c.mailto) ? el("a", { class: "btn btn--primary", href: c.mailto }, el("span", { text: "Write an email" })) : null));
}

function disableDialog(op, onChange) {
  confirmAct({
    row: { icao: "" },
    title: `Disable ${op.name}?`,
    lead: op.you ? "You are signed out at once and cannot sign in again." : `${op.name} is signed out at once and cannot sign in again.`,
    more: { topic: "disabling", text: "An operator can invite them again later." },
    go: "Disable",
    serious: true,
    send: () => call(ADMIN.operator(op.k, "disable"), { method: "POST", body: {} }),
    done: (res) => {
      $("ad-dlg").close();
      if (op.you) location.reload();
      else onChange(res.data);
    },
  });
}

export function act(kind, row) {
  const name = `${row.name} (${row.icao})`;
  if (kind === "review") return reviewDialog(row);
  if (kind === "contact") return contactDialog(row);
  if (kind === "approve") {
    return confirmAct({
      row, title: `Approve hosting for ${name}?`,
      lead: "Its account holder can then set up its space. Nothing runs until shadow runs start.",
      more: { topic: "approving", text: `A TEPHRA dispatcher verified ${row.name} at the Desk. Hosting on this site needs an operator too.` },
      go: "Approve hosting",
      send: () => call(ADMIN.airline(row.airline_id, "approve-hosting"), { method: "POST", body: { version: row.version } }),
    });
  }
  if (kind === "suspend") {
    return confirmAct({
      row, title: `Suspend ${name}?`, serious: true, reason: [3, 300],
      lead: "Runs stop and pushes are refused at once; its members can still read.",
      more: { topic: "suspending", text: `From 7 days after suspension an operator can delete its data; nothing deletes it on its own. ${RECORDED}` },
      go: `Suspend ${row.icao}`,
      send: ({ reason }) => call(ADMIN.tenant(row.icao, "suspend"), { method: "POST", body: { reason } }),
    });
  }
  if (kind === "resume") {
    return confirmAct({
      row, title: `Resume ${name}?`,
      lead: "It resumes in SHADOW, never straight to LIVE, and takes one airline place.",
      more: { topic: "resuming", text: "Its ops manager switches to LIVE again when ready." },
      go: "Resume in SHADOW",
      send: () => call(ADMIN.tenant(row.icao, "resume"), { method: "POST", body: {} }),
    });
  }
  if (kind === "delete") {
    return confirmAct({
      row, title: `Delete ${name}'s data?`, serious: true, typeIcao: true,
      lead: "Everything in its space, its members and its invites go. It cannot be undone.",
      more: { topic: "what is deleted", text: "Advisories, messages, documents, keys, policy versions and its record. A tombstone keeps its code, name and dates, nothing about its people." },
      go: `Delete ${row.icao}'s data`,
      send: ({ icao }) => call(ADMIN.tenant(row.icao, "delete-data"), { method: "POST", body: { confirm_icao: icao } }),
    });
  }
  if (kind === "opsinvite") {
    return confirmAct({
      row, title: `New ops-manager link for ${name}`,
      lead: "For when no ops manager is left: accepting makes the airline's account an ops manager.",
      more: { topic: "the link", text: `The link is for the airline's account email and needs that account signed in. ${RECORDED}` },
      go: "Make the link",
      send: () => call(ADMIN.tenant(row.icao, "ops-manager-invite"), { method: "POST", body: {} }),
      done: (res, form) => {
        form.querySelector(".pdlg__acts").before(onceBox(res.data.link, `Email sending is not built: send it yourself to ${row.ops_email}. It works until ${when(res.data.expires_at)}.`));
        form.querySelector('button[type="submit"]').remove();
      },
    });
  }
  return null;
}

// --- signed out: sign in, or turn an operator link into an account -------------------------------

// `lead`: one line (or null), `info`: infoButton options for the (i) beside it
function authCard(id, title, lead, form, { info = null } = {}, ...more) {
  return el("div", { class: "narrow" }, el("section", { class: "card authcard", "aria-labelledby": id },
    el("span", { class: "authcard__mark", "aria-hidden": "true" }, icon("i-lock")),
    el("div", {}, el("h1", { id, class: "h1 h1--auth", text: title }), lead ? el("p", { class: "body2" }, ...(info ? infoTail(lead, info) : [lead])) : null),
    form, ...more));
}

export function signinCard() {
  const email = input({ type: "email", autocomplete: "username", inputmode: "email", spellcheck: "false", autocapitalize: "off", maxlength: 254 });
  const pw = passwordInput({ id: "as-pw", autocomplete: "current-password" });
  const status = statusLine("as-status");
  const go = el("button", { type: "submit", class: "btn btn--primary btn--block" }, el("span", { text: "Sign in" }));
  const emailWords = () => ruleMessage("acct.email", email.value);
  const pwWords = () => (pw.control.value ? null : "Required");
  checkOnLeave(email, emailWords);
  checkOnLeave(pw.control, pwWords);
  const form = el("form", { class: "authform", novalidate: true },
    field({ id: "as-email", label: "Email", control: email }),
    field({ id: "as-pw", label: "Password", control: pw.control, slot: pw.wrap(pw.control) }),
    status, go);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const bad = [[email, emailWords()], [pw.control, pwWords()]].filter(([, w]) => w);
    for (const c of [email, pw.control]) setError(c, null);
    for (const [c, w] of bad) setError(c, w);
    if (bad.length) {
      bad[0][0].focus();
      return;
    }
    go.disabled = true;
    const res = await call(ADMIN.signIn, { method: "POST", body: { email: email.value.trim().toLowerCase(), password: pw.control.value } });
    go.disabled = false;
    if (res.ok) {
      pw.control.value = "";
      await render();
      return;
    }
    if (res.status === 401) {
      const left = Number(res.headers?.get("x-tephra-tries-left") ?? res.data?.tries_left);
      const tries = Number.isFinite(left) && left <= 2 ? ` ${left} ${left === 1 ? "try" : "tries"} left before sign-in waits 15 minutes.` : "";
      say(status, `That email and password don't match.${tries}`);
      pw.control.select();
    } else {
      say(status, res.status === 429 ? `Too many tries. Try again in ${minutesWords(retryMinutes(res))}.` : failWords(res));
    }
  });
  // the footer says the console is for this site's operators; the title says sign-in
  return authCard("as-h", "Operator sign-in", null, form, {},
    el("p", { class: "body2 authcard__links" },
      el("span", {}, "Airline? ", el("a", { class: "link", href: "/signin", text: "Use the workspace" })),
      el("span", { class: "chip chip--notbuilt", text: "Email reset: not built" })));
}

export const OP_GONE = "This operator link is used or expired. Ask an operator for a new one.";

export async function joinCard(token) {
  if (!token) return authCard("aj-h", "This link cannot be used", token === "" ? OP_GONE : "This page needs the whole operator link. Open it again.", el("a", { class: "btn btn--secondary btn--block", href: "/admin" }, el("span", { text: "Operator sign-in" })), {});
  const res = await call(ADMIN.inviteLookup, { method: "POST", body: { token } });
  if (!res.ok || !res.data) {
    const words = res.status === 404 ? OP_GONE : res.status === 429 ? `Too many tries. Try again in ${minutesWords(retryMinutes(res))}.` : failWords(res);
    return authCard("aj-h", "This link cannot be used", words, el("a", { class: "btn btn--secondary btn--block", href: "/admin" }, el("span", { text: "Operator sign-in" })), {});
  }
  const inv = res.data;
  const email = input({ type: "email", autocomplete: "username", inputmode: "email", spellcheck: "false", autocapitalize: "off", maxlength: 254 });
  const pw = passwordInput({ id: "aj-pw", autocomplete: "new-password" });
  const status = statusLine("aj-status");
  const go = el("button", { type: "submit", class: "btn btn--primary btn--block" }, el("span", { text: "Create the operator account" }));
  const emailWords = () => ruleMessage("acct.email", email.value);
  const pwWords = () => ruleMessage("acct.password", pw.control.value) || (pw.control.value.trim().toLowerCase() === email.value.trim().toLowerCase() ? "Not your email" : null);
  checkOnLeave(email, emailWords);
  checkOnLeave(pw.control, pwWords);
  // "For" says which email the link is for; the password's rule is in its label
  const form = el("form", { class: "authform", novalidate: true },
    el("dl", { class: "kv" }, el("dt", { text: "Name" }), el("dd", { text: inv.name }), el("dt", { text: "For" }), el("dd", { class: "mono", text: inv.email_hint }), el("dt", { text: "Until" }), el("dd", { text: when(inv.expires_at) })),
    field({ id: "aj-email", label: "Email", control: email }),
    field({ id: "aj-pw", label: "Password · 12+ characters", rule: "12 characters or more", control: pw.control, slot: pw.wrap(pw.control) }),
    status, go);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const mail = email.value.trim().toLowerCase();
    const problems = [[email, emailWords()], [pw.control, pwWords()]];
    for (const [c, m] of problems) setError(c, m);
    const first = problems.find(([, m]) => m);
    if (first) {
      first[0].focus();
      return;
    }
    go.disabled = true;
    const r = await call(ADMIN.inviteAccept, { method: "POST", body: { token, email: mail, password: pw.control.value } });
    go.disabled = false;
    if (r.ok) {
      pw.control.value = "";
      location.replace("/admin");
      return;
    }
    const code = errorCode(r);
    say(status, r.status === 404 ? OP_GONE : code === "wrong_email" ? `This link is for ${inv.email_hint}.` : code === "email_taken" ? "This email has an operator account already: sign in instead." : failWords(r));
  });
  return authCard("aj-h", "Become an operator of TEPHRA", "Emails are not checked: the link is the proof.", form,
    { info: { topic: "operators", label: "What operators do", text: "Operators verify airlines and keep this site's hosted airlines inside the free tier." } });
}

// --- the header's account button -------------------------------------------------------------------

function operatorMenu(me) {
  const button = el("button", { type: "button", id: "tn-account", class: "tn-account", "aria-haspopup": "menu", "aria-expanded": "false", "aria-controls": "tn-account-menu" },
    el("span", { class: "tn-account__code", "aria-hidden": "true", text: "OP" }),
    el("span", { class: "tn-account__name", text: `Operator · ${me.name}` }), icon("i-chevron-down"));
  const out = el("button", { type: "button", class: "tn-menu__item", role: "menuitem" }, icon("i-log-out"), "Sign out");
  const menu = el("div", { id: "tn-account-menu", class: "tn-menu", role: "menu", "aria-label": "Your operator account", hidden: true },
    el("div", { class: "tn-menu__theme", role: "group", "aria-label": "Theme" }, themeControl()), out);
  const setOpen = (open) => {
    menu.hidden = !open;
    button.setAttribute("aria-expanded", String(open));
    if (open) out.focus();
  };
  button.addEventListener("click", () => setOpen(menu.hidden));
  menu.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
      button.focus();
    }
  });
  out.addEventListener("click", async () => {
    await call(ADMIN.signOut, { method: "POST", body: {} });
    location.replace("/admin");
  });
  const wrap = el("div", { class: "tn-account-wrap" }, button, menu);
  wrap.addEventListener("focusout", (e) => {
    if (!wrap.contains(e.relatedTarget)) setOpen(false);
  });
  return wrap;
}

// --- render -----------------------------------------------------------------------------------------

function drawConsole(now = Date.now()) {
  const list = S.list;
  const onFilter = (k) => {
    S.filter = k;
    drawConsole();
    document.getElementById(`af-${k}`)?.focus();
  };
  $("main").replaceChildren(el("div", { class: "apage" },
    el("header", { class: "hhead" }, el("div", {}, el("p", { class: "eyebrow", text: "TEPHRA operator console" }),
      el("div", { class: "hhead__t" }, el("h1", { class: "h1", text: "Airlines" }),
        infoButton({ topic: "what operators see", label: "What operators see", text: "Status, counts and contacts; never an airline's drafts, people or key." })))),
    ...notes(list),
    tiles(list),
    airlinesCard(list, S.filter, onFilter, now),
    S.ops ? operatorsCard(S.ops, (ops) => {
      S.ops = ops;
      drawConsole();
    }) : el("p", { class: "err" }, icon("i-alert"), el("span", { text: "The operators could not be read. Reload to try again." }))));
}

// After an action the console is drawn again: focus goes to that airline's row (its first
// button), or to the page heading, never to <body>.
function focusRow(icao) {
  const row = document.querySelector(`tr[data-icao="${icao}"]`);
  const target = row?.querySelector("button:not([disabled])") || document.querySelector("#main h1");
  if (!target) return;
  if (String(target.tagName).toUpperCase() !== "BUTTON") target.setAttribute("tabindex", "-1");
  target.focus();
}

async function refresh() {
  const [list, ops] = await Promise.all([call(ADMIN.airlines), call(ADMIN.operators)]);
  if (list.status === 401) {
    await render();
    return;
  }
  if (!list.ok || !list.data) {
    $("main").replaceChildren(el("div", { class: "narrow" }, el("p", { class: "err" }, icon("i-alert"), el("span", { text: `The airlines could not be read: ${failWords(list)}` }))));
    return;
  }
  S.list = list.data;
  S.ops = ops.ok && Array.isArray(ops.data) ? ops.data : null;
  drawConsole();
}

async function render() {
  const joining = /^\/admin\/join\/?$/.test(location.pathname);
  const me = joining ? { ok: false, status: 401 } : await call(ADMIN.me);
  if (me.ok && me.data) {
    S.me = me.data;
    document.title = "Airlines · Operator console · TEPHRA";
    $("tn-right").replaceChildren(operatorMenu(me.data));
    await refresh();
  } else if (joining) {
    document.title = "Operator link · TEPHRA";
    $("main").replaceChildren(await joinCard(S.token));
  } else if (me.status === 401) {
    document.title = "Operator sign-in · TEPHRA";
    $("tn-right").replaceChildren();
    $("main").replaceChildren(signinCard());
  } else {
    $("main").replaceChildren(el("div", { class: "narrow" }, el("p", { class: "err" }, icon("i-alert"), el("span", { text: failWords(me) }))));
  }
  const h = $("main").querySelector("h1");
  if (h) {
    h.tabIndex = -1;
    h.focus();
  }
}

// The operator link's token, once; the address bar keeps /admin/join only.
export function takeToken(loc = location, hist = history) {
  if (!/^\/admin\/join\/?$/.test(loc.pathname)) return null;
  const raw = loc.hash.startsWith("#") ? loc.hash.slice(1) : "";
  if (loc.hash) hist.replaceState(null, "", "/admin/join");
  if (!raw) return null;
  return /^[A-Za-z0-9_-]{20,200}$/.test(raw) ? raw : "";
}

// The footer's one line (in the page) gets its (i): what an operator's action leaves behind.
export function footInfo(doc = document) {
  const foot = doc.getElementById("ad-foot");
  if (foot && !foot.querySelector(".info")) foot.append(infoButton({ topic: "the record", label: "What is recorded", text: "Each action on an airline goes into that airline's record." }));
}

export async function boot() {
  S.token = takeToken();
  inlineSprite();
  footInfo();
  const state = await call(ADMIN.state);
  setFeatures(state.ok ? state.data?.features : []);
  applyFeatureNav();
  if (state.ok && !has("hosted")) {
    $("main").replaceChildren(el("div", { class: "narrow" }, el("p", { class: "status status--quiet" }, icon("st-off"), el("span", { text: "Airlines are not hosted on this server." }))));
    return;
  }
  await render();
}

if (typeof document !== "undefined" && document.body?.classList.contains("admin-shell")) boot();
