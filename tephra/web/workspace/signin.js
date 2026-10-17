// Sign in (/signin) and recovery (/signin/recover) for an airline's account; one still onboarding
// goes back to its pages. The answers never say whether an email has an account: one wording for
// a wrong email or password, the tries left only when two or fewer remain, and the wait in words
// after too many. Field errors are terse and wait until a field is left or the form is sent.

import { el, icon } from "../wall/util.js";
import { ruleMessage, safeNext } from "../onboard/pages.js";
import { checkOnLeave, field, input, passwordInput, setError } from "../onboard/form.js";
import { recoveryCard } from "../onboard/review.js";
import { PATHS, call, errorCode, failWords, minutesWords, retryMinutes } from "./api.js";

function stage(...kids) {
  return el("div", { class: "auth__stage" }, el("div", { class: "auth__backdrop night", "aria-hidden": "true" }), ...kids);
}

const statusLine = () => el("p", { id: "si-status", class: "inline-alert", role: "status", hidden: true });
function say(line, words) {
  line.hidden = !words;
  line.replaceChildren(...(words ? [icon("st-caution"), el("span", { text: words })] : []));
}

function busy(button, on, words) {
  button.disabled = on;
  button.querySelector("span").textContent = words;
}

export function renderSignin(main, { next }) {
  document.title = "Sign in · TEPHRA";
  const email = input({ type: "email", autocomplete: "username", inputmode: "email", spellcheck: "false", autocapitalize: "off", maxlength: 254 });
  const pw = passwordInput({ id: "si-pw", autocomplete: "current-password" });
  const status = statusLine();
  const go = el("button", { type: "submit", class: "btn btn--primary btn--block" }, el("span", { text: "Sign in" }));
  const emailWords = () => ruleMessage("acct.email", email.value);
  const pwWords = () => (pw.control.value ? null : "Required");
  checkOnLeave(email, emailWords);
  checkOnLeave(pw.control, pwWords);
  const form = el("form", { class: "authform", novalidate: true },
    field({ id: "si-email", label: "Email", control: email }),
    field({ id: "si-pw", label: "Password", control: pw.control, slot: pw.wrap(pw.control) }),
    status, go);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const bad = [[email, emailWords()], [pw.control, pwWords()]].filter(([, w]) => w);
    setError(email, null);
    setError(pw.control, null);
    for (const [c, w] of bad) setError(c, w);
    if (bad.length) {
      bad[0][0].focus();
      return;
    }
    busy(go, true, "Signing in…");
    const res = await call(PATHS.signIn, { method: "POST", body: { email: email.value.trim().toLowerCase(), password: pw.control.value } });
    busy(go, false, "Sign in");
    if (res.ok) {
      pw.control.value = "";
      // An airline still onboarding goes back to the first page it has not finished.
      location.assign(res.data?.status === "draft" && !next ? "/onboard" : safeNext(next));
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
  main.replaceChildren(stage(
    el("section", { class: "card authcard auth__card", "aria-labelledby": "si-h" },
      el("span", { class: "authcard__mark", "aria-hidden": "true" }, icon("i-lock")),
      el("h1", { id: "si-h", class: "h1 h1--auth", text: "Sign in to your workspace" }),
      form,
      el("p", { class: "body2 authcard__links" },
        el("a", { class: "link", href: "/signin/recover", dataset: { go: "" }, text: "Forgot password?" }),
        el("span", {}, "Dispatcher? ", el("a", { class: "link", href: "/desk", text: "Use the Desk" })))),
    el("p", { class: "signin__new body2" }, "New airline? ", el("a", { class: "link", href: "/onboard", text: "Onboard" }))));
}

export function renderRecover(main) {
  document.title = "Use your recovery code · TEPHRA";
  const email = input({ type: "email", autocomplete: "username", inputmode: "email", spellcheck: "false", autocapitalize: "off", maxlength: 254 });
  const code = input({ mono: true, autocomplete: "one-time-code", maxlength: 32, placeholder: "XXXX-XXXX-XXXX-XXXX" });
  const pw = passwordInput({ id: "rv-pw", autocomplete: "new-password" });
  const pw2 = passwordInput({ id: "rv-pw2", autocomplete: "new-password" });
  const status = statusLine();
  const go = el("button", { type: "submit", class: "btn btn--primary btn--block" }, el("span", { text: "Set the new password" }));
  const typedCode = () => code.value.replace(/[\s-]/g, "").toUpperCase();
  const checks = [
    [email, () => ruleMessage("acct.email", email.value)],
    [code, () => (!code.value.trim() ? "Required" : /^[A-Z0-9]{16}$/.test(typedCode()) ? null : "16 letters and digits")],
    [pw.control, () => ruleMessage("acct.password", pw.control.value)],
    [pw2.control, () => (!pw2.control.value ? "Required" : pw2.control.value !== pw.control.value ? "Passwords differ" : null)],
  ];
  for (const [c, words] of checks) checkOnLeave(c, words);
  const form = el("form", { class: "authform", novalidate: true },
    field({ id: "rv-email", label: "Email", control: email }),
    field({ id: "rv-code", label: "Recovery code", control: code }),
    field({ id: "rv-pw", label: "New password · 12+ characters", rule: "12 characters or more", control: pw.control, slot: pw.wrap(pw.control) }),
    field({ id: "rv-pw2", label: "New password again", control: pw2.control, slot: pw2.wrap(pw2.control) }),
    status, go);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    for (const c of [email, code, pw.control, pw2.control]) setError(c, null);
    const problems = checks.map(([c, words]) => [c, words()]).filter(([, w]) => w);
    for (const [c, msg] of problems) setError(c, msg);
    if (problems.length) {
      problems[0][0].focus();
      return;
    }
    busy(go, true, "Setting it…");
    const mail = email.value.trim().toLowerCase();
    const res = await call(PATHS.recover, { method: "POST", body: { email: mail, recovery_code: typedCode(), new_password: pw.control.value } });
    busy(go, false, "Set the new password");
    if (res.ok && typeof res.data?.recovery_code === "string") {
      pw.control.value = "";
      pw2.control.value = "";
      main.replaceChildren(recoveryCard({ code: res.data.recovery_code, email: mail, icao: null }, {
        lead: "Password set. Keep this code: it is shown once, and the old one no longer works.",
      }));
      const h = main.querySelector("h1");
      h.tabIndex = -1;
      h.focus();
      return;
    }
    if (res.status === 401) say(status, "That email and recovery code don't match.");
    else if (res.status === 429) say(status, `Too many tries. Try again in ${minutesWords(retryMinutes(res))}.`);
    else if (res.status === 422 && errorCode(res) === "validation_failed") say(status, "The new password needs 12 characters or more, and not your email.");
    else say(status, failWords(res));
  });
  main.replaceChildren(stage(
    el("section", { class: "card authcard auth__card", "aria-labelledby": "rv-h" },
      el("span", { class: "authcard__mark", "aria-hidden": "true" }, icon("i-lock")),
      el("div", {}, el("h1", { id: "rv-h", class: "h1 h1--auth", text: "Use your recovery code" }), el("p", { class: "body2", text: "Email reset is not built. You get a new code; other browsers are signed out." })),
      form,
      el("p", { class: "body2" }, el("a", { class: "link", href: "/signin", dataset: { go: "" }, text: "‹ Back to sign in" })))));
}
