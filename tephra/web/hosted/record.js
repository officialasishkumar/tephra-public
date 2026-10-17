// Settings › Record (SPEC-FINAL 5.6, mockup a-settings-record.html): every draft, decision and
// setting change in the airline's own audit chain, newest first, 50 at a time, from
// GET /api/tenant/record (RecordTab). The chain line is the head TEPHRA holds (no walk on a read);
// an ops manager may walk the whole chain and export it once a day each. Filters work on the
// entries loaded. A broken chain is a real alarm, in red. Every string goes in through el().

import { el, icon } from "../wall/util.js";
import { api } from "../base.js";
import { personName, hhmmZ, dayMonth, serverNow } from "../tenant-nav.js";
import { can, call, errorWords, pageHead, loadingCard, failCard, inlineStatus, announce } from "../hosted.js";

export const TITLE = "Record";
export const lead = (h) => `Every draft, decision and setting change in ${h.name}'s space. Each entry is linked to the one before by its hash.`;
const ms = (iso) => (iso ? Date.parse(iso) : NaN);
const num = (n) => Number(n || 0).toLocaleString("en");
const pad = (n) => String(n).padStart(2, "0");

export const FILTERS = [
  { key: "all", name: "All" },
  { key: "decisions", name: "Decisions" },
  { key: "settings", name: "Settings" },
  { key: "people", name: "People" },
  { key: "feeds", name: "Feeds" },
];
const GROUP = {
  decisions: ["APPROVED", "EDITED", "REJECTED", "MESSAGE_DECIDED", "RECOVERY_DECIDED", "DOC_SIGNED", "DOC_WITHDRAWN", "HANDOVER_ACKED", "AI_FAILURE_HANDLED", "CREW_REPORT_ENTERED", "CREW_REPORT_WITHDRAWN"],
  settings: ["HOSTED_SETUP", "HOSTED_SHADOW", "HOSTED_LIVE", "HOSTED_STOPPED", "HOSTED_SUSPENDED", "HOSTED_RESUMED", "POLICY_CHANGED", "POLICY_CONFIRMED", "SRA_RECORDED", "SRA_WITHDRAWN", "MODEL_KEY_SET", "MODEL_KEY_REMOVED", "ASSISTANT_CHANGED", "CHAIN_CHECKED"],
  people: ["MEMBER_INVITED", "MEMBER_JOINED", "MEMBER_ROLE_CHANGED", "MEMBER_REMOVED", "INVITE_REVOKED", "OPS_MANAGER_RESTORED", "LOGIN_OK", "LOGIN_FAILED"],
  feeds: ["CONNECTION_CREATED", "CONNECTION_REVOKED"],
};
export const groupOf = (action) => Object.keys(GROUP).find((g) => GROUP[g].includes(action)) || "other";
export const inFilter = (entry, key) => key === "all" || groupOf(entry.action) === key;

const WORDS = {
  DRAFT_CREATED: "Drafted advisory", APPROVED: "Approved advisory", EDITED: "Approved with edits", REJECTED: "Rejected advisory",
  SUPERSEDED: "Draft replaced", OUTBOUND_QUEUED: "Put on the outbound list", AI_FAILED: "Assistant gave no result", AI_FAILURE_HANDLED: "Planned by hand",
  AI_FAILURE_CLOSED: "No longer needed", ASKED: "Asked", NOTICE_READ: "Notice read", MESSAGE_DRAFTED: "Message drafted", MESSAGE_DECIDED: "Message decided",
  DOC_DRAFTED: "Document drafted", DOC_SIGNED: "Document signed", DOC_WITHDRAWN: "Document withdrawn", HANDOVER_ACKED: "Handover read",
  CREW_REPORT_ENTERED: "Crew report entered", CREW_REPORT_WITHDRAWN: "Crew report withdrawn", CREW_REPORT_EXPIRED: "Crew report expired",
  CONNECTION_CREATED: "Push key made", CONNECTION_REVOKED: "Push key revoked",
  HOSTED_SETUP: "Set up on TEPHRA", HOSTED_SHADOW: "Shadow runs", HOSTED_LIVE: "Switched to LIVE", HOSTED_STOPPED: "Runs stopped",
  HOSTED_SUSPENDED: "Suspended by TEPHRA's operators", HOSTED_RESUMED: "Resumed by TEPHRA's operators", POLICY_CHANGED: "Policy changed",
  POLICY_CONFIRMED: "Policy confirmed", SRA_RECORDED: "SRA acceptance recorded", SRA_WITHDRAWN: "SRA acceptance withdrawn", MODEL_KEY_SET: "Model key set",
  MODEL_KEY_REMOVED: "Model key removed", ASSISTANT_CHANGED: "Assistant changed", MEMBER_INVITED: "Invite made", MEMBER_JOINED: "Joined",
  MEMBER_ROLE_CHANGED: "Role changed", MEMBER_REMOVED: "Removed", INVITE_REVOKED: "Invite revoked", OPS_MANAGER_RESTORED: "Ops manager invite by TEPHRA's operators",
  CHAIN_CHECKED: "Whole chain checked", LOGIN_OK: "Signed in", LOGIN_FAILED: "Sign-in refused",
};
export const actionWords = (e) => WORDS[e.action] || e.action.toLowerCase().replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
export const whoOf = (actor) => (!actor || actor === "system" ? "TEPHRA" : personName(actor));
export function whenOf(t, now) {
  if (!Number.isFinite(t)) return "";
  const d = new Date(t);
  const hms = `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}Z`;
  return now - t < 20 * 3600e3 ? hms : `${dayMonth(t)} ${hhmmZ(t)}`;
}
const shortHash = (h) => (h ? `${h.slice(0, 4)}…${h.slice(-4)}` : "");
const isShadow = (e) => Boolean(e.after && e.after.shadow === true) || /\bSHADOW - NOT FOR USE\b/.test(e.note || "");

// The chain line: "Chain intact · 212 entries", or in red where it broke.
export function chainLine(head) {
  if (head.intact) {
    return el("p", { class: "chainline" },
      el("span", { class: "chainbadge" }, icon("i-check"), el("span", { text: `Chain intact · ${num(head.entries)} entries` })),
      head.checked_at ? el("span", { class: "tdim", text: `checked ${hhmmZ(ms(head.checked_at))}` }) : null);
  }
  const first = (head.problems || [])[0] || "";
  const at = /entry (\d+)/.exec(first)?.[1] ?? (Number.isFinite(head.verified_through_seq) ? head.verified_through_seq + 1 : null);
  return el("div", { class: "chainline", role: "alert" },
    el("span", { class: "chainbadge chainbadge--bad" }, icon("i-alert-serious"), el("span", { text: at != null ? `Chain broken at entry ${num(at)}` : "Chain broken" })),
    el("p", { class: "body2", text: `${first ? `${first.replace(/^./, (c) => c.toUpperCase())}. ` : ""}TEPHRA's operators see this on their console. Export still works and shows where.` }));
}

export function entriesTable(entries, filter, now = Date.now()) {
  const rows = entries.filter((e) => inFilter(e, filter));
  if (!rows.length) return el("p", { class: "body2", text: filter === "all" ? "No entries yet." : "None of the loaded entries is of this kind." });
  return el("table", { class: "rtable" },
    el("caption", { class: "sr-only", text: "Record entries, newest first" }),
    el("thead", {}, el("tr", {}, ...["When (UTC)", "Who", "What", "Hash"].map((t) => el("th", { scope: "col", text: t })))),
    el("tbody", {}, ...rows.map((e) => el("tr", {},
      el("td", { "data-l": "When", text: whenOf(ms(e.at), now) }),
      el("td", { "data-l": "Who", text: whoOf(e.actor) }),
      el("td", { "data-l": "What", class: "wide" }, actionWords(e), e.note ? ` · ${e.note}` : "", isShadow(e) ? el("span", { class: "rtag", text: "SHADOW" }) : null),
      el("td", { "data-l": "Hash", class: "hash", title: e.sha256 || "", text: shortHash(e.sha256) })))));
}

export function render(h, view, { entries, filter, onFilter, onOlder, onCheck, older, checkStatus }) {
  const ops = can(h, "ops_manager");
  const exp = ops && view.can_export ? el("a", { class: "btn btn--secondary", href: api("/tenant/record/export"), download: "" }, el("span", { text: "Export (.ndjson)" })) : null;
  const check = ops && view.can_check ? el("button", { type: "button", class: "btn btn--quiet btn--sm", text: "Check the whole chain" }) : null;
  check?.addEventListener("click", () => onCheck(check));
  const seg = el("div", { class: "seg", role: "group", "aria-label": "Show" }, ...FILTERS.map((f) => {
    const b = el("button", { type: "button", class: "seg__b", "aria-pressed": f.key === filter ? "true" : "false", text: f.name });
    b.addEventListener("click", () => onFilter(f.key));
    return b;
  }));
  return [
    pageHead(TITLE, lead(h), exp),
    el("section", { class: "card wcard", "aria-labelledby": "rec-h" },
      el("h2", { id: "rec-h", class: "sr-only", text: "Entries" }),
      el("div", { class: "racts" }, chainLine(view.head), check),
      checkStatus,
      ops ? el("p", { class: "hint", text: "Checking the whole chain and exporting work once a day each." }) : null,
      seg,
      entriesTable(entries, filter, serverNow()),
      older),
  ];
}

// ------------------------------------------------------------------ the page

export async function mount(host, h) {
  host.replaceChildren(pageHead(TITLE, lead(h)), loadingCard("Record"));
  const res = await call(api("/tenant/record"));
  if (!res.ok || !res.data) {
    host.replaceChildren(pageHead(TITLE, lead(h)), failCard(res, h, { title: "The record did not load" }));
    return;
  }
  const S = { view: res.data, entries: [...(res.data.entries || [])], next: res.data.next_before_seq, filter: "all" };
  const checkStatus = inlineStatus("chk-status");
  const draw = () => {
    const older = S.next != null ? el("button", { type: "button", class: "btn btn--quiet", text: "Load older entries" }) : null;
    older?.addEventListener("click", async () => {
      older.disabled = true;
      const r = await call(api(`/tenant/record?before_seq=${encodeURIComponent(S.next)}`));
      if (r.ok && r.data) {
        S.entries.push(...(r.data.entries || []));
        S.next = r.data.next_before_seq;
        draw();
        announce(`${(r.data.entries || []).length} older entries loaded.`);
      } else { older.disabled = false; checkStatus.say(errorWords(r, h)); }
    });
    host.replaceChildren(...render(h, S.view, {
      entries: S.entries, filter: S.filter, older, checkStatus,
      onFilter: (k) => { S.filter = k; draw(); host.querySelector(`.seg [aria-pressed="true"]`)?.focus(); },
      onCheck: async (btn) => {
        btn.disabled = true;
        checkStatus.say("Checking the whole chain…", "ok");
        const r = await call(api("/tenant/record/check"), { method: "POST", body: {} });
        if (r.ok && r.data) {
          S.view = r.data;
          S.entries = [...(r.data.entries || [])];
          S.next = r.data.next_before_seq;
          draw();
          checkStatus.say(r.data.head.intact ? "The whole chain was walked and is intact." : "The whole chain was walked: it is broken.", r.data.head.intact ? "ok" : "bad");
          return;
        }
        btn.disabled = false;
        checkStatus.say(r.status === 429 ? "The whole chain was already checked today." : errorWords(r, h));
      },
    }));
  };
  draw();
}
