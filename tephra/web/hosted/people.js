// Settings › People (SPEC-FINAL 5.6, mockup a-settings-people.html): who can sign in to the
// airline's space, from GET /api/tenant/people (PeopleTab). Ops managers invite by email and role:
// the link is shown once and copied by hand (TEPHRA sends no email and does not check emails),
// change roles, remove people and revoke open invites; the server keeps at least one ops manager.
// Emails are shown to ops managers only. Anyone may leave. Every string goes in through el().

import { el, icon } from "../wall/util.js";
import { api } from "../base.js";
import { whenWords, hhmmZ, dayMonth, ROLE_WORDS, serverNow, personName } from "../tenant-nav.js";
import { input } from "../onboard/form.js";
import { can, call, errorWords, pageHead, loadingCard, failCard, onceBox, openDialog, inlineStatus, announce, refocus, headInfo, checkedField } from "../hosted.js";

export const TITLE = "People";
export const lead = (h) => `Who can sign in to ${h.name}'s space. Names never go to a model.`;
const ROLES = ["ops_manager", "dispatcher", "viewer"];
const ms = (iso) => (iso ? Date.parse(iso) : NaN);
const LAST_OPS = "Keep at least one ops manager: make someone else an ops manager first.";
// "13:58 UTC" today, "16 Oct, 22:10 UTC" before
const when = (t, now) => (!Number.isFinite(t) ? "Not yet" : now - t < 20 * 3600e3 ? hhmmZ(t).replace("Z", " UTC") : whenWords(t));

export function inviteWords(invite, link) {
  const role = (ROLE_WORDS[invite.role] || invite.role).toLowerCase();
  const until = whenWords(ms(invite.expires_at));
  return {
    lead: el("span", {}, el("b", { text: `Invite link for ${invite.email}, ${ROLE_WORDS[invite.role] || invite.role}.` }), " Shown once."),
    link,
    words: ["Not built: email sending. Send this link yourself.", `It joins one person as ${role}, until ${until}. Emails are not checked.`],
  };
}

export function membersTable(p, h, { editable, onRole, onRemove }) {
  const now = serverNow();
  return el("table", { class: "ptable" },
    el("caption", { class: "sr-only", text: "Members" }),
    el("thead", {}, el("tr", {}, ...["Name", "Role", "Joined", "Last sign-in"].map((t) => el("th", { scope: "col", text: t })), el("th", { scope: "col" }, el("span", { class: "sr-only", text: "Actions" })))),
    el("tbody", {}, ...(p.members || []).map((m) => {
      let role;
      if (editable) {
        role = el("select", { class: "select rolepick", "aria-label": `Role of ${m.name}` }, ...ROLES.map((r) => el("option", { value: r, selected: r === m.role ? true : null, text: ROLE_WORDS[r] })));
        role.addEventListener("change", () => onRole(m, role));
      } else role = el("span", { text: ROLE_WORDS[m.role] || m.role });
      const remove = editable && !m.you ? el("button", { type: "button", class: "btn btn--quiet btn--sm", "aria-label": `Remove ${m.name}…`, text: "Remove…" }) : null;
      remove?.addEventListener("click", () => onRemove(m));
      return el("tr", {},
        el("td", { "data-l": "Name", class: "wide" }, el("b", { text: m.name }), m.you ? el("span", { class: "you", text: "you" }) : null, m.email ? el("span", { class: "pemail", text: m.email }) : null),
        el("td", { "data-l": "Role" }, role),
        el("td", { "data-l": "Joined", text: dayMonth(ms(m.joined_at)) }),
        el("td", { "data-l": "Last sign-in", text: when(ms(m.last_sign_in_at), now) }),
        el("td", { class: "wide" }, remove ? el("div", { class: "tacts" }, remove) : null));
    })));
}

export function invitesList(p, { editable, onRevoke }) {
  const list = p.invites || [];
  if (!list.length) return el("p", { class: "body2", text: "No open invites." });
  return el("ul", { class: "ilist", "aria-label": "Open invites" }, ...list.map((iv) => {
    const revoke = editable ? el("button", { type: "button", class: "btn btn--quiet btn--sm", "aria-label": `Revoke the invite for ${iv.email ?? ROLE_WORDS[iv.role]}`, text: "Revoke" }) : null;
    revoke?.addEventListener("click", () => onRevoke(iv));
    return el("li", {},
      el("span", { class: "ilist__what" }, el("b", { text: iv.email || "An invite" }),
        el("span", { class: "tdim", text: `${ROLE_WORDS[iv.role] || iv.role} · until ${whenWords(ms(iv.expires_at))} · by ${personName(iv.created?.by)}` })),
      revoke);
  }));
}

// What each role may do: reference, one tap away (a closed fold that names what is inside).
export function rolesCard() {
  return el("details", { class: "rolesfold" }, el("summary", { text: "What each role can do" }),
    el("div", { class: "roles" },
      el("div", {}, el("b", {}, icon("i-gauge"), "Ops manager"), "Settings, people, policy acceptance, push keys, starting shadow runs and switching to LIVE. At least one always."),
      el("div", {}, el("b", {}, icon("i-dispatcher"), "Dispatcher"), "Decides drafts at the Desk: approve, edit, reject. Checks a push with the dry run."),
      el("div", {}, el("b", {}, icon("i-eye"), "Viewer"), "Reads the map, the Desk and the record. Decides nothing.")));
}

export function render(h, p, handlers = {}, fresh = null) {
  const editable = can(h, "ops_manager");
  const invite = editable ? inviteCard(p, h, handlers.invite, fresh) : null;
  const leave = el("button", { type: "button", class: "btn btn--secondary btn--sm", text: `Leave ${h.name}…` });
  leave.addEventListener("click", () => handlers.leave?.());
  return [
    pageHead(TITLE, lead(h)),
    invite,
    el("section", { class: "card wcard", "aria-labelledby": "mem-h" },
      el("div", { class: "wcard__h" }, el("span", { class: "wcard__ic", "aria-hidden": "true" }, icon("i-user")), el("h2", { id: "mem-h", text: `Members · ${(p.members || []).length}` })),
      membersTable(p, h, { editable, onRole: handlers.role, onRemove: handlers.remove }),
      el("h3", { class: "h3", text: `Open invites · ${(p.invites || []).length}` }),
      invitesList(p, { editable, onRevoke: handlers.revoke }),
      rolesCard()),
    el("section", { class: "card wcard", "aria-labelledby": "leave-h" },
      el("div", { class: "wcard__h" }, el("h2", { id: "leave-h", text: "Leave this airline" }), leave)),
  ].filter(Boolean);
}

// The invite's email: said wrong only after it is left or on submit, in terse words.
export const emailError = (v) => (!v ? "Required" : /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) ? null : "Not an email");
export const limitsWords = (p) => `At most ${p.limits?.open_invites ?? 20} open invites and ${p.limits?.members ?? 50} people. A link works once, for 72 hours.`;

function inviteCard(p, h, onInvite, fresh) {
  const email = checkedField({ id: "inv-email", label: "Work email", control: input({ type: "email", autocomplete: "off", maxlength: "254" }), check: emailError });
  const role = el("select", { id: "inv-role", class: "select" }, ...ROLES.map((r) => el("option", { value: r, selected: r === "dispatcher" ? true : null, text: ROLE_WORDS[r] })));
  const go = el("button", { type: "submit", class: "btn btn--primary", text: "Make invite link" });
  const status = inlineStatus("inv-status");
  const form = el("form", { class: "invite", novalidate: true },
    email,
    el("div", { class: "field" }, el("label", { for: "inv-role", text: "Role" }), role),
    go);
  form.addEventListener("submit", (e) => { e.preventDefault(); onInvite({ email, role, go, status }); });
  const box = fresh ? (() => { const w = inviteWords(fresh.invite, fresh.link); return onceBox(w.lead, w.link, ...w.words); })() : null;
  return el("section", { class: "card wcard", "aria-labelledby": "inv-h" },
    el("div", { class: "wcard__h" }, el("span", { class: "wcard__ic", "aria-hidden": "true" }, icon("i-plus")),
      headInfo(el("h2", { id: "inv-h", text: "Invite someone" }), { topic: "invites", text: limitsWords(p) })),
    form,
    status,
    box);
}

// ------------------------------------------------------------------ the page

export async function mount(host, h) {
  host.replaceChildren(pageHead(TITLE, lead(h)), loadingCard("People"));
  const res = await call(api("/tenant/people"));
  if (!res.ok || !res.data) {
    host.replaceChildren(pageHead(TITLE, lead(h)), failCard(res, h, { title: "People did not load" }));
    return;
  }
  draw(host, h, res.data);
}

function draw(host, h, p, fresh = null) {
  const again = (data, keep = null) => { draw(host, h, data, keep); refocus(host, "#mem-h"); };
  const reload = async (keep = null) => {
    const r = await call(api("/tenant/people"));
    if (r.ok && r.data) again(r.data, keep);
  };
  host.replaceChildren(...render(h, p, {
    invite: async ({ email, role, go, status }) => {
      status.say("");
      if (!email.ok()) return;
      const e = email.value();
      go.disabled = true;
      const res = await call(api("/tenant/people/invites"), { method: "POST", body: { email: e, role: role.value } });
      go.disabled = false;
      if (res.ok && res.data?.link) { announce("Invite link made. It is shown once."); reload({ invite: res.data.invite, link: res.data.link }); return; }
      const code = res.data?.error;
      status.say(code === "already_member" ? "That email is already one of your people."
        : code === "too_many_invites" ? "There are 20 open invites. Revoke one first."
          : code === "members_full" ? "This airline has 50 people, the most it can have." : errorWords(res, h));
    },
    role: async (m, select) => {
      const res = await call(api(`/tenant/people/${encodeURIComponent(m.id)}/role`), { method: "POST", body: { role: select.value } });
      if (res.ok && res.data) { announce(`${m.name} is now ${ROLE_WORDS[select.value]}.`); again(res.data); return; }
      select.value = m.role;
      const status = inlineStatus("role-status");
      select.closest("table")?.after(status);
      status.say(res.data?.error === "last_ops_manager" ? LAST_OPS : errorWords(res, h));
    },
    remove: (m) => openDialog({
      id: "prm", title: `Remove ${m.name}?`, goText: `Remove ${m.name}`, tone: "serious",
      body: [el("p", { class: "body2", text: `${m.name} is signed out at once and their open invites are revoked. Their decisions stay in the record.` })],
      go: async (status) => {
        const res = await call(api(`/tenant/people/${encodeURIComponent(m.id)}/remove`), { method: "POST", body: {} });
        if (res.ok && res.data) { again(res.data); announce(`${m.name} removed.`); return true; }
        status.say(res.data?.error === "last_ops_manager" ? LAST_OPS : errorWords(res, h));
        return false;
      },
    }),
    revoke: async (iv) => {
      const res = await call(api(`/tenant/people/invites/${encodeURIComponent(iv.id)}/revoke`), { method: "POST", body: {} });
      if (res.ok && res.data) { announce("Invite revoked."); again(res.data); }
    },
    leave: () => openDialog({
      id: "pleave", title: `Leave ${h.name}?`, goText: `Leave ${h.name}`, tone: "serious",
      body: [el("p", { class: "body2", text: "You lose access at once, on every device. An ops manager can invite you again." })],
      go: async (status) => {
        const res = await call(api("/tenant/people/me/leave"), { method: "POST", body: {} });
        if (res.status === 204 || res.ok) { location.assign("/workspace"); return true; }
        status.say(res.data?.error === "last_ops_manager" ? "You are the last ops manager. Make someone else an ops manager first." : errorWords(res, h));
        return false;
      },
    }),
  }, fresh));
}
