// The invite page /join#<token> (SPEC hosted §5.1, D7, S8): an ops manager's one-time link. The
// token travels in the fragment only: workspace.js takes it before anything else runs and removes
// it from the address bar (history.replaceState), and from then on it lives in this module's
// memory, never in storage or a path. The invite is looked up (POST /api/hosted/invites/lookup),
// then the person joins with a new account, or signs in here and accepts; both end on the
// airline's own space. Every string goes in through el() (textContent).

import { el, icon } from "../wall/util.js";
import { ruleMessage } from "../onboard/pages.js";
import { field, input, passwordInput, segmented, setError } from "../onboard/form.js";
import { recoveryCard, supportTick } from "../onboard/review.js";
import { HOSTED, PATHS, call, errorCode, failWords, isIcao, minutesWords, retryMinutes, spacePath } from "./api.js";
import { ROLE_WORDS, whenWords } from "./golive.js";

const TOKEN = /^[A-Za-z0-9_-]{20,200}$/;
// The fragment's token, once: null when the page has none, "" when it is not a token. The address
// bar keeps /join only.
export function takeToken(loc = location, hist = history) {
  if (!/^\/join\/?$/.test(loc.pathname)) return null;
  const raw = loc.hash.startsWith("#") ? loc.hash.slice(1) : "";
  if (loc.hash) hist.replaceState(null, "", "/join");
  if (!raw) return null;
  return TOKEN.test(raw) ? raw : "";
}

export const GONE_WORDS = "This invite link is used, revoked or expired. Ask your ops manager for a new one.";
const ROLE_LINES = {
  ops_manager: "Ops managers decide TEPHRA's drafts and also change the airline's settings, people and keys, and start or stop TEPHRA.",
  dispatcher: "Dispatchers decide TEPHRA's drafts at the Desk: approve, edit or reject.",
  viewer: "Viewers see the map, the Desk and the record, and decide nothing.",
};
export const anyoneWords = (invite) => `Anyone with this link who gives the email it is for can join as ${ROLE_WORDS[invite.role] || invite.role} until ${whenWords(invite.expires_at)}. Emails are not checked.`;

const S = { token: null, invite: null, signedIn: false, mode: "join", email: "", main: null };

function page(...kids) {
  return el("div", { class: "narrow join" }, ...kids);
}

function goneCard(words = GONE_WORDS, title = "This invite cannot be used") {
  return el("section", { class: "card authcard", "aria-labelledby": "jn-h" },
    el("span", { class: "authcard__mark", "aria-hidden": "true" }, icon("i-x")),
    el("h1", { id: "jn-h", class: "h2", text: title }),
    el("p", { class: "body2", text: words }),
    el("a", { class: "btn btn--secondary btn--block", href: "/" }, el("span", { text: "TEPHRA's home" })));
}

export function inviteCard(invite) {
  return el("section", { class: "card authcard", "aria-labelledby": "jn-h" },
    el("p", { class: "eyebrow", text: "Invite" }),
    el("h1", { id: "jn-h", class: "h1 h1--auth", text: `Join ${invite.airline} on TEPHRA` }),
    el("dl", { class: "kv" },
      el("dt", { text: "Airline" }), el("dd", { text: `${invite.airline} (${invite.icao})` }),
      el("dt", { text: "Role" }), el("dd", { text: ROLE_WORDS[invite.role] || invite.role }),
      el("dt", { text: "Invited by" }), el("dd", { text: invite.invited_by }),
      el("dt", { text: "For" }), el("dd", { class: "mono", text: invite.email_hint })),
    el("p", { class: "body2", text: ROLE_LINES[invite.role] || "" }),
    el("p", { id: "jn-anyone", class: "note note--caution" }, icon("st-caution"), el("span", { text: anyoneWords(invite) })));
}

const statusLine = (id) => el("p", { id, class: "inline-alert", role: "status", hidden: true });
function say(line, words) {
  line.hidden = !words;
  line.replaceChildren(...(words ? [icon("st-caution"), el("span", { text: words })] : []));
}
const nameOf = (control) => control.value.trim().replace(/\s+/g, " ");
const open = () => location.assign(spacePath(S.invite.icao, "/"));

// A new account's recovery code, shown once before the airline opens (as onboarding shows it):
// it is how a member gets back in after forgetting the password, since TEPHRA sends no email. It
// lives only in the card's text, never in storage, and goes when the page moves on.
function showRecovery(code, email) {
  S.main.replaceChildren(recoveryCard({ code, email, icao: S.invite.icao }, {
    lead: `Your account is made and you are a member of ${S.invite.airline}. Here is your recovery code: it is shown once, and it is how you get back in if you forget your password.`,
    next: { href: spacePath(S.invite.icao, "/"), text: `Open ${S.invite.airline}` },
  }));
  const h = S.main.querySelector("h1");
  h.tabIndex = -1;
  h.focus();
}

// The answers both forms share.
function commonWords(res) {
  const code = errorCode(res);
  if (res.status === 404 || code === "invite_gone") return null;   // the gone card
  if (code === "wrong_email") return `This invite is for ${S.invite.email_hint}. Use that email.`;
  if (res.status === 429) return `Too many tries. Try again in ${minutesWords(retryMinutes(res))}.`;
  return failWords(res);
}

function nameField(id, value = "") {
  const control = input({ autocomplete: "nickname", maxlength: 32, value });
  return { control, node: field({ id, label: "Your name on TEPHRA", hint: `${S.invite.airline}'s members see it on your decisions and in its record. 2 to 32 characters.`, control }) };
}

// Signed in: accept with a name.
function acceptCard(rerender) {
  const you = S.invite.you || null;
  const name = nameField("jn-name", you?.name || "");
  const status = statusLine("jn-status");
  const go = el("button", { type: "submit", class: "btn btn--primary btn--block" }, el("span", { text: `Accept and open ${S.invite.airline}` }));
  const out = el("button", { type: "button", id: "jn-out", class: "linkbtn", text: "Sign out" });
  out.addEventListener("click", async () => {
    await call(PATHS.signOut, { method: "POST", body: {} });
    S.signedIn = false;
    S.invite = { ...S.invite, you: null };
    S.mode = "signin";
    rerender({ focus: true });
  });
  const form = el("form", { class: "authform", novalidate: true }, name.node, status, go);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const bad = ruleMessage("member.name", name.control.value);
    setError(name.control, bad);
    if (bad) {
      name.control.focus();
      return;
    }
    go.disabled = true;
    const res = await call(HOSTED.inviteAccept, { method: "POST", body: { token: S.token, display_name: nameOf(name.control) } });
    go.disabled = false;
    if (res.ok) {
      open();
      return;
    }
    if (errorCode(res) === "name_taken") {
      setError(name.control, "Another member uses this name. Choose another.");
      name.control.focus();
      return;
    }
    const words = commonWords(res);
    if (words === null) {
      rerender({ gone: true });
      return;
    }
    const wrong = errorCode(res) === "wrong_email";
    say(status, wrong ? wrongAccount() : words);
    (wrong ? out : go).focus();
  });
  const who = you ? `You are signed in as ${you.email_hint}.` : "You are signed in.";
  if (you && !you.for_you) {
    // the invite is for another email: say so before anything is tried, and offer the way out
    return el("section", { class: "card authcard", "aria-labelledby": "jn-acc-h" },
      el("h2", { id: "jn-acc-h", class: "h2", text: "Accept the invite" }),
      el("p", { id: "jn-wrong", class: "inline-alert", role: "status" }, icon("st-caution"), el("span", { text: `${who} ${wrongAccount()}` })),
      el("p", { class: "body2" }, out));
  }
  return el("section", { class: "card authcard", "aria-labelledby": "jn-acc-h" },
    el("h2", { id: "jn-acc-h", class: "h2", text: "Accept the invite" }),
    el("p", { class: "body2" }, `${who} Not the account this invite is for? `, out),
    form);
}
const wrongAccount = () => `This invite is for ${S.invite.email_hint}, and you are signed in with another email. Sign out, then sign in with that email.`;

// Signed out: a new account, or sign in here and then accept.
function joinForm(rerender) {
  const email = input({ type: "email", autocomplete: "username", inputmode: "email", spellcheck: "false", autocapitalize: "off", maxlength: 254, value: S.email });
  const pw = passwordInput({ id: "jn-pw", autocomplete: "new-password" });
  const name = nameField("jn-name");
  const ack = el("input", { type: "checkbox", id: "jn-ack", "aria-describedby": "jn-ack-err" });
  const status = statusLine("jn-status");
  const go = el("button", { type: "submit", class: "btn btn--primary btn--block" }, el("span", { text: `Join ${S.invite.airline}` }));
  const form = el("form", { class: "authform", novalidate: true },
    field({ id: "jn-email", label: "Email", hint: `The invite is for ${S.invite.email_hint}.`, control: email }),
    field({ id: "jn-pw", label: "Password", hint: "12 characters or more", control: pw.control, slot: pw.wrap(pw.control) }),
    name.node,
    supportTick(ack, "jn-ack-err"),
    status, go);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const mail = email.value.trim().toLowerCase();
    const problems = [
      [email, ruleMessage("acct.email", email.value)],
      [pw.control, ruleMessage("acct.password", pw.control.value) || (pw.control.value.trim().toLowerCase() === mail ? "The password must not be your email." : null)],
      [name.control, ruleMessage("member.name", name.control.value)],
      [ack, ack.checked ? null : "Tick this to go on."],
    ];
    for (const [c, m] of problems) setError(c, m);
    const first = problems.find(([, m]) => m);
    if (first) {
      first[0].focus();
      return;
    }
    go.disabled = true;
    const res = await call(HOSTED.inviteJoin, { method: "POST", body: { token: S.token, email: mail, password: pw.control.value, display_name: nameOf(name.control), acknowledge: true } });
    go.disabled = false;
    if (res.ok) {
      pw.control.value = "";
      if (typeof res.data?.recovery_code === "string") showRecovery(res.data.recovery_code, mail);
      else open();
      return;
    }
    const code = errorCode(res);
    if (code === "email_taken") {
      S.email = mail;
      S.mode = "signin";
      rerender({ said: "This email has an account already. Sign in with it, then accept.", focus: true });
      return;
    }
    if (code === "name_taken") {
      setError(name.control, "Another member uses this name. Choose another.");
      name.control.focus();
      return;
    }
    const words = commonWords(res);
    if (words === null) {
      rerender({ gone: true });
      return;
    }
    if (code === "wrong_email") {
      setError(email, words);
      email.focus();
      return;
    }
    say(status, words);
    go.focus();
  });
  return form;
}

function signinForm(rerender, said) {
  const email = input({ type: "email", autocomplete: "username", inputmode: "email", spellcheck: "false", autocapitalize: "off", maxlength: 254, value: S.email });
  const pw = passwordInput({ id: "jn-si-pw", autocomplete: "current-password" });
  const status = statusLine("jn-status");
  const go = el("button", { type: "submit", class: "btn btn--primary btn--block" }, el("span", { text: "Sign in" }));
  const form = el("form", { class: "authform", novalidate: true },
    field({ id: "jn-si-email", label: "Email", control: email }),
    field({ id: "jn-si-pw", label: "Password", control: pw.control, slot: pw.wrap(pw.control) }),
    status, go);
  if (said) say(status, said);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const bad = ruleMessage("acct.email", email.value) ? [email, "Enter an email address, like ops@rfb.example."] : !pw.control.value ? [pw.control, "Password is needed."] : null;
    setError(email, null);
    setError(pw.control, null);
    if (bad) {
      setError(bad[0], bad[1]);
      bad[0].focus();
      return;
    }
    go.disabled = true;
    const res = await call(PATHS.signIn, { method: "POST", body: { email: email.value.trim().toLowerCase(), password: pw.control.value } });
    go.disabled = false;
    if (res.ok) {
      pw.control.value = "";
      S.signedIn = true;
      const again = await call(HOSTED.inviteLookup, { method: "POST", body: { token: S.token } });
      if (again.ok && again.data && isIcao(again.data.icao)) S.invite = again.data;
      rerender({ focus: true });
      return;
    }
    if (res.status === 401) {
      const left = Number(res.headers?.get("x-tephra-tries-left"));
      const tries = Number.isFinite(left) && left <= 2 ? ` ${left} ${left === 1 ? "try" : "tries"} left before sign-in waits 15 minutes.` : "";
      say(status, `That email and password don't match.${tries}`);
      pw.control.select();
    } else if (res.status === 429) {
      say(status, `Too many tries. Try again in ${minutesWords(retryMinutes(res))}.`);
    } else {
      say(status, failWords(res));
    }
  });
  return form;
}

function signedOutCard(rerender, said) {
  const body = S.mode === "signin" ? signinForm(rerender, said) : joinForm(rerender);
  return el("section", { class: "card authcard", "aria-labelledby": "jn-acc-h" },
    el("h2", { id: "jn-acc-h", class: "h2", text: "Your account" }),
    segmented({
      label: "Your account", idBase: "jn-tab", value: S.mode,
      tabs: [{ key: "join", text: "New to TEPHRA", icon: "i-user" }, { key: "signin", text: "I have an account", icon: "i-lock" }],
      onChange: (k) => {
        S.mode = k;
        rerender();
        document.getElementById(`jn-tab-${k}`)?.focus();
      },
    }),
    el("div", { id: "jn-tab-panel", role: "tabpanel", "aria-labelledby": `jn-tab-${S.mode}` }, body),
    el("p", { class: "hint", text: "Password reset by email is not built: keep your password safe." }));
}

function headingFocus(main) {
  const h = main.querySelector("h1");
  if (!h) return;
  h.tabIndex = -1;
  h.focus();
}

// Draw the page for the token workspace.js took; `signedIn` from the session read.
export async function renderJoin(main, { token, signedIn }) {
  document.title = "Join an airline · TEPHRA";
  S.token = token;
  S.signedIn = signedIn;
  S.main = main;
  // `focus`: drawn again after an action, so focus goes to the first thing to do, never <body>
  const draw = ({ gone = false, said = null, focus = false } = {}) => {
    if (gone || !S.invite) {
      main.replaceChildren(page(goneCard()));
      if (focus || gone) headingFocus(main);
      return;
    }
    main.replaceChildren(page(inviteCard(S.invite), S.signedIn ? acceptCard(draw) : signedOutCard(draw, said)));
    if (focus) (main.querySelector("#jn-name") || main.querySelector("#jn-out") || main.querySelector(".authform input") || main.querySelector("h1"))?.focus();
  };
  if (!token) {
    main.replaceChildren(page(goneCard(token === "" ? GONE_WORDS : "This page needs the whole invite link, as your ops manager sent it. Open the link again.")));
    return;
  }
  const res = await call(HOSTED.inviteLookup, { method: "POST", body: { token } });
  if (res.ok && res.data && isIcao(res.data.icao)) {
    S.invite = res.data;
    draw();
    return;
  }
  if (res.status === 404) {
    draw({ gone: true });
    return;
  }
  main.replaceChildren(page(goneCard(res.status === 429 ? `Too many invite reads from this network. Try again in ${minutesWords(retryMinutes(res))}.` : failWords(res), "The invite could not be read")));
}
