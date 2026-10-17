// Feeds /a/<ICAO>/feeds (SPEC-FINAL 5.5, mockup a-feeds.html): what the airline's systems push, as
// it arrives. Three cards (positions, flight plans, pilot reports) from GET /api/tenant/feeds, the
// push keys (ops managers), the uploader (kit/push.py, members only) and the shared dry run. In setup a push is checked and counted, never
// taken in, and the page says so. Counts are kept in memory since `counted_since`; refused records
// are not stored, so the cards give reasons and counts only. Every string goes in through el().

import { el, icon } from "../wall/util.js";
import { infoButton } from "../wall/info.js";
import { api } from "../base.js";
import { mountDryRun } from "../dryrun.js";
import { personName, dayMonth, hhmmZ, serverNow } from "../tenant-nav.js";
import { input } from "../onboard/form.js";
import { can, call, errorWords, pageHead, loadingCard, failCard, onceBox, openDialog, inlineStatus, notBuiltNote, announce, refocus, headInfo, checkedField } from "../hosted.js";

export const LEAD = { text: "What your systems push, as it arrives.", info: { topic: "feeds", text: "Public feeds (ash reports, satellite, winds) are on the map, under Details › Data feeds." } };
export const SETUP_STRIP = "Checked, not taken in: TEPHRA starts in SHADOW from your workspace.";
// the uploader (tephra/web/kit/push.py), served to the airline's people only
export const UPLOADER = "/tenant/feeds/uploader";
export const UPLOADER_INFO = "push.py sends your flight plans and positions with a push key. Python 3, nothing to install; --dry-run sends nothing.";
export const NOT_BUILT = "schedule upload, counts kept over a restart, a grace window for a rotated key.";
export const KEYS_INFO = "Rotate makes a new key and stops the old one at once. Revoke stops a key at once.";
const FEEDS = {
  positions: { name: "Positions", icon: "i-aircraft", unit: ["record", "records"] },
  flight_plans: { name: "Flight plans", icon: "i-route", unit: ["record", "records"] },
  pilot_reports: { name: "Pilot reports", icon: "i-quote", unit: ["record", "records"] },
};
const SECTION_WORDS = { positions: "positions", flight_plans: "flight plans", pilot_reports: "pilot reports" };
// positions and flight plans count as received when one came in the last 10 minutes (the go-live rule)
const FRESH_S = 600;
const ms = (iso) => (iso ? Date.parse(iso) : NaN);
const num = (n) => Number(n || 0).toLocaleString("en");
const pad = (n) => String(n).padStart(2, "0");
const hms = (t) => { const d = new Date(t); return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}Z`; };

export function ago(seconds) {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  return h < 48 ? `${h} h ago` : `${Math.round(h / 24)} days ago`;
}
// "14:02:31Z" today, "16 Oct 22:40Z" before
export function receivedAt(t, now) {
  if (!Number.isFinite(t)) return "";
  return now - t < 20 * 3600e3 ? hms(t) : `${dayMonth(t)} ${hhmmZ(t)}`;
}

// A card's state in a word and a shape: receiving, no push yet, not received (a real alarm for
// positions only), quiet, not declared.
export function cardState(card, now, takenIn, suspended = false) {
  const last = ms(card.last_received_at);
  const age = (now - last) / 1000;
  // nothing a suspended airline pushes is taken in or checked: no card reads as receiving
  if (suspended) return { tone: "quiet", icon: "st-off", word: "Refused while suspended", empty: !Number.isFinite(last), suspended: true };
  if (!card.declared && !card.optional) return { tone: "quiet", icon: "st-off", word: "Not declared", empty: !Number.isFinite(last), undeclared: true };
  if (!Number.isFinite(last)) return { tone: "quiet", icon: "st-never", word: "No push yet", empty: true };
  if (card.feed === "pilot_reports") return age <= 3600 ? { tone: "ok", icon: "st-ok", word: takenIn ? "Receiving" : "Checked" } : { tone: "quiet", icon: "st-off", word: "None this hour" };
  if (age <= FRESH_S) return { tone: "ok", icon: "st-ok", word: takenIn ? "Receiving" : "Checked" };
  const mins = Math.round(age / 60);
  if (card.feed === "positions") return { tone: "serious", icon: "st-serious", word: `Not received ${mins >= 120 ? `${Math.floor(mins / 60)} h` : `${mins} min`}`, alarm: true };
  return { tone: "quiet", icon: "st-off", word: `None for ${mins >= 120 ? `${Math.floor(mins / 60)} h` : `${mins} min`}` };
}

export function feedCard(card, { now, countedSince, takenIn, suspended = false }) {
  const f = FEEDS[card.feed] || { name: card.feed, icon: "i-network", unit: ["record", "records"] };
  const st = cardState(card, now, takenIn, suspended);
  const last = ms(card.last_received_at);
  const since = ms(countedSince);
  const lastHour = Number.isFinite(since) && now - since < 3600e3 ? `Since ${hhmmZ(since)}` : "Last hour";
  const refused = Number(card.refused_last_hour || 0);
  const reasons = (card.reasons || []).slice(0, 3);
  return el("section", { class: "card fcard", "aria-labelledby": `fc-${card.feed}` },
    el("div", { class: "fcard__h" },
      el("span", { class: "fcard__ic", "aria-hidden": "true" }, icon(f.icon)),
      el("h2", { id: `fc-${card.feed}`, text: f.name }),
      el("span", { class: `status status--${st.tone}` }, icon(st.icon), el("span", { text: st.word }))),
    st.empty
      ? (st.suspended ? null : el("p", { class: "fnone", text: st.undeclared ? "Your onboarding answers do not list this feed." : card.optional ? "Optional. Crews report ash rarely; a quiet hour is normal." : "Make a push key below, then send with the uploader." }))
      : el("dl", { class: "fstat" },
        el("dt", { text: "Last received" }), el("dd", {}, receivedAt(last, now), Number.isFinite(last) ? el("small", { text: ago((now - last) / 1000) }) : null),
        el("dt", { text: lastHour }), el("dd", { text: `${num(card.records_last_hour)} ${Number(card.records_last_hour) === 1 ? f.unit[0] : f.unit[1]}` }),
        el("dt", { text: "Refused" }), el("dd", {}, refused ? el("span", { class: "bad", text: num(refused) }) : "0")),
    reasons.length ? el("ul", { class: "freasons", "aria-label": `Why ${f.name.toLowerCase()} were refused` },
      ...reasons.map((r) => el("li", {}, el("span", { text: r.reason }), el("b", { text: num(r.count) })))) : null,
    st.alarm ? el("p", { class: "falarm", text: "Your flights are on the map at their last position. Which head into ash is unknown until positions arrive." }) : null,
    !st.empty && card.optional ? el("p", { class: "fnone", text: "Optional. Crews report ash rarely; a quiet hour is normal." }) : null,
    st.undeclared && !st.empty ? el("p", { class: "fnone", text: "Your onboarding answers do not list this feed." }) : null);
}

export const hasSent = (k) => (k.sections_seen || []).map((s) => SECTION_WORDS[s] || s).join(", ").replace(/^./, (c) => c.toUpperCase()) || "Nothing yet";

export function keysTable(keys, { now, countedSince, editable, onRotate, onRevoke }) {
  const since = ms(countedSince);
  const rows = [...keys].sort((a, b) => Number(Boolean(a.revoked_at)) - Number(Boolean(b.revoked_at))).map((k) => {
    const revoked = Boolean(k.revoked_at);
    const made = ms(k.created_at);
    const last = ms(k.last_push_at);
    const acts = [];
    if (editable && !revoked) {
      const rot = el("button", { type: "button", class: "btn btn--quiet btn--sm", "aria-label": `Rotate ${k.name}…`, text: "Rotate…" });
      const rev = el("button", { type: "button", class: "btn btn--quiet btn--sm", "aria-label": `Revoke ${k.name}…`, text: "Revoke…" });
      rot.addEventListener("click", () => onRotate(k));
      rev.addEventListener("click", () => onRevoke(k));
      acts.push(rot, rev);
    }
    return el("tr", { class: revoked ? "is-revoked" : null },
      el("td", { "data-l": "Name" }, el("b", { text: k.name })),
      el("td", { "data-l": "Key" }, el("span", { class: "keyhint", text: `…${k.key_hint}` })),
      el("td", { "data-l": "Has sent", text: revoked ? `Revoked ${dayMonth(ms(k.revoked_at))}` : hasSent(k) }),
      el("td", { "data-l": "Made", class: "tdim", text: `${dayMonth(made)} · ${personName(k.created_by)}` }),
      el("td", { "data-l": "Last push", class: Number.isFinite(last) ? null : "tdim", text: Number.isFinite(last) ? receivedAt(last, now) : "Not yet" }),
      el("td", { class: "wide" }, acts.length ? el("div", { class: "tacts" }, ...acts) : null));
  });
  return el("table", { class: "ktable" },
    el("caption", { class: "sr-only", text: "Push keys" }),
    el("thead", {}, el("tr", {}, ...["Name", "Key", `Has sent${Number.isFinite(since) ? ` (since ${hhmmZ(since)})` : ""}`, "Made", "Last push"].map((t) => el("th", { scope: "col", text: t })), el("th", { scope: "col" }, el("span", { class: "sr-only", text: "Actions" })))),
    el("tbody", {}, ...rows));
}

// ------------------------------------------------------------------ the page

export async function mount(host, h) {
  host.replaceChildren(pageHead("Feeds", LEAD), loadingCard("Your feeds"));
  const res = await call(api("/tenant/feeds"));
  if (!res.ok || !res.data) {
    host.replaceChildren(pageHead("Feeds", LEAD), failCard(res, h, { title: "Your feeds did not load" }));
    return;
  }
  draw(host, h, res.data);
}

function draw(host, h, view, fresh = null) {
  const now = serverNow();
  const ops = can(h, "ops_manager");
  const suspended = h.state === "suspended";
  const opts = { now, countedSince: view.counted_since, takenIn: view.taken_in, suspended };
  const reload = async (keep) => {
    const r = await call(api("/tenant/feeds"));
    if (r.ok && r.data) { draw(host, h, r.data, keep); refocus(host, "#keys-h"); }
  };
  const keys = el("section", { class: "card wcard wcard--wide", "aria-labelledby": "keys-h" });
  const status = inlineStatus("keys-status");
  const newKey = el("button", { type: "button", class: "btn btn--secondary btn--sm" }, icon("i-plus"), el("span", { text: "New push key" }));
  newKey.addEventListener("click", () => newKeyDialog(h, (made) => reload(made)));
  const address = `${location.origin}${view.push_url}`;
  const heading = el("h2", { id: "keys-h", text: "Push keys" });
  keys.append(...[
    el("div", { class: "wcard__h" }, el("span", { class: "wcard__ic", "aria-hidden": "true" }, icon("i-lock")),
      ops ? headInfo(heading, { topic: "push keys", text: KEYS_INFO }) : heading,
      el("span", { class: "wcard__acts" }, uploaderLink(), ops ? newKey : null)),
    el("div", { class: "endpoint" }, el("span", { class: "verb", text: "POST" }), el("code", { text: address }),
      el("span", { class: "tdim" }, "format ", el("code", { text: "tephra.airline/1" })),
      el("a", { class: "link body2", href: api("/connect/schema.json"), download: "" }, el("span", { text: "Schema (JSON)" }), icon("i-external-link"))),
    fresh ? onceBox(el("span", {}, el("b", { text: `${fresh.rotated ? "New key for" : "New key"} “${fresh.name}”.` }), " Shown once: copy it now."), fresh.key,
      `TEPHRA keeps only its fingerprint.${fresh.rotated ? " The old key stopped." : ""}`) : null,
    ops
      ? (view.keys || []).length
        ? keysTable(view.keys, { ...opts, editable: true, onRotate: (k) => rotateDialog(h, k, (made) => reload(made)), onRevoke: (k) => revokeDialog(h, k, () => reload(null)) })
        : el("p", { class: "body2", text: "No push key yet." })
      : el("p", { class: "body2", text: "Ops managers make, rotate and revoke push keys." }),
    status].filter(Boolean));
  // suspended: the red line under the header says pushes are refused, and each card says so
  host.replaceChildren(...[
    pageHead("Feeds", LEAD),
    suspended || view.taken_in ? null : el("p", { class: "fsetup", role: "status" }, el("span", {}, el("b", { text: "Checked, not taken in:" }), " TEPHRA starts in SHADOW from your workspace. "), el("a", { class: "link", href: "/workspace", text: "Your workspace ›" })),
    el("div", { class: "fcards" }, ...(view.cards || []).map((c) => feedCard(c, opts))),
    keys].filter(Boolean));
  if (can(h, "dispatcher")) mountDryRun(host, { path: api("/tenant/feeds/dry-run"), info: "Each record is checked as a real push would be. Nothing is taken in." });
  // each not-built item and what it means here, in the note's order
  host.append(notBuiltNote(NOT_BUILT, { topic: "what is not built", text: [
    "No schedule upload: your flights are named by your pushed flight plans, callsigns and registrations.",
    `Counts start again when TEPHRA restarts: these cards count since ${hhmmZ(ms(view.counted_since))}.`,
    "A rotated or revoked key stops working at once.",
  ] }));
}

// The uploader, for every member: a file, never a page (Content-Disposition: attachment).
export function uploaderLink() {
  return el("span", { class: "chipinfo" },
    el("a", { class: "btn btn--quiet btn--sm", href: api(UPLOADER), download: "push.py" }, icon("i-file"), el("span", { text: "Download uploader" })),
    infoButton({ topic: "the uploader", text: UPLOADER_INFO }));
}

// A key's name: 2 to 48 characters (the server's rule), said in the label.
export const keyNameError = (v) => (!v ? "Required" : v.length < 2 ? "2+ characters" : null);
function keyName(id) {
  return checkedField({ id, label: "Name · 2-48 characters", control: input({ maxlength: "48", autocomplete: "off", placeholder: "ops-feed-2" }), check: keyNameError });
}

function newKeyDialog(h, done) {
  const name = keyName("key-name");
  openDialog({
    id: "newkey", title: "New push key", goText: "Make the key",
    body: [name],
    go: async (status) => {
      if (!name.ok()) return false;
      const res = await call(api("/tenant/keys"), { method: "POST", body: { name: name.value() } });
      if (res.ok && res.data?.key) {
        done({ name: res.data.name, key: res.data.key });
        announce(`Push key ${res.data.name} made. It is shown once.`);
        return true;
      }
      status.say(res.data?.error === "too_many_keys" ? "There are 10 active keys already. Revoke one first." : errorWords(res, h));
      return false;
    },
  });
}

function rotateDialog(h, k, done) {
  openDialog({
    id: "rotate", title: `Rotate “${k.name}”?`, goText: "Rotate the key",
    body: [el("p", { class: "body2", text: `The old key (…${k.key_hint}) stops at once. The new one is shown once.` })],
    go: async (status) => {
      const res = await call(api(`/tenant/keys/${encodeURIComponent(k.id)}/rotate`), { method: "POST", body: {} });
      if (res.ok && res.data?.key) {
        done({ name: res.data.name, key: res.data.key, rotated: true });
        announce(`New key for ${res.data.name}. It is shown once.`);
        return true;
      }
      status.say(errorWords(res, h));
      return false;
    },
  });
}

function revokeDialog(h, k, done) {
  openDialog({
    id: "revoke", title: `Revoke “${k.name}”?`, goText: "Revoke the key", tone: "serious",
    body: [el("p", { class: "body2", text: `The key (…${k.key_hint}) stops at once. This cannot be undone.` })],
    go: async (status) => {
      const res = await call(api(`/tenant/keys/${encodeURIComponent(k.id)}/revoke`), { method: "POST", body: {} });
      if (res.ok) {
        done();
        announce(`Push key ${k.name} revoked.`);
        return true;
      }
      status.say(errorWords(res, h));
      return false;
    },
  });
}
