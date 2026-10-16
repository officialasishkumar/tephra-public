// Sign in (/signin) and recovery (/signin/recover) for an airline's account; one still onboarding
// goes back to its pages. The answers never say whether an email has an account: one wording for
// a wrong email or password, the tries left only when two or fewer remain, and the wait in words
// after too many.

import { el, icon } from "../wall/util.js";
import { ruleMessage, safeNext } from "../onboard/pages.js";
import { field, input, passwordInput, setError } from "../onboard/form.js";
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
  const form = el("form", { class: "authform", novalidate: true },
    field({ id: "si-email", label: "Email", control: email }),
    field({ id: "si-pw", label: "Password", control: pw.control, slot: pw.wrap(pw.control) }),
    status, go);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const bad = ruleMessage("acct.email", email.value) ? [email, "Enter an email address, like ops@rfa.example."] : !pw.control.value ? [pw.control, "Password is needed."] : null;
    setError(email, null);
    setError(pw.control, null);
    if (bad) {
      setError(bad[0], bad[1]);
      bad[0].focus();
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
      el("div", {}, el("h1", { id: "si-h", class: "h1 h1--auth", text: "Sign in" }), el("p", { class: "body2", text: "To your airline's workspace." })),
      form,
      el("p", { class: "or", text: "or" }),
      el("a", { class: "btn btn--secondary btn--block", href: "/signin/recover", dataset: { go: "" } }, el("span", { text: "Use your recovery code" })),
      el("p", { class: "body2" }, "Password reset by email is not built. Dispatchers sign in ", el("a", { class: "link", href: "/desk", text: "on the Desk" }), ".")),
    el("p", { class: "signin__new body2" }, "New here? ", el("a", { class: "link", href: "/onboard", text: "Onboard your airline" }))));
}

export function renderRecover(main) {
  document.title = "Use your recovery code · TEPHRA";
  const email = input({ type: "email", autocomplete: "username", inputmode: "email", spellcheck: "false", autocapitalize: "off", maxlength: 254 });
  const code = input({ mono: true, autocomplete: "one-time-code", maxlength: 32, placeholder: "XXXX-XXXX-XXXX-XXXX" });
  const pw = passwordInput({ id: "rv-pw", autocomplete: "new-password" });
  const pw2 = passwordInput({ id: "rv-pw2", autocomplete: "new-password" });
  const status = statusLine();
  const go = el("button", { type: "submit", class: "btn btn--primary btn--block" }, el("span", { text: "Set the new password" }));
  const form = el("form", { class: "authform", novalidate: true },
    field({ id: "rv-email", label: "Email", control: email }),
    field({ id: "rv-code", label: "Recovery code", hint: "Capitals or small letters, with or without the dashes.", control: code }),
    field({ id: "rv-pw", label: "New password", hint: "12 characters or more", control: pw.control, slot: pw.wrap(pw.control) }),
    field({ id: "rv-pw2", label: "New password again", control: pw2.control, slot: pw2.wrap(pw2.control) }),
    status, go);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    for (const c of [email, code, pw.control, pw2.control]) setError(c, null);
    const typedCode = code.value.replace(/[\s-]/g, "").toUpperCase();
    const problems = [
      ruleMessage("acct.email", email.value) && [email, "Enter an email address, like ops@rfa.example."],
      !/^[A-Z0-9]{16}$/.test(typedCode) && [code, "A recovery code is 16 letters and digits."],
      ruleMessage("acct.password", pw.control.value) && [pw.control, ruleMessage("acct.password", pw.control.value)],
      !ruleMessage("acct.password", pw.control.value) && pw2.control.value !== pw.control.value && [pw2.control, "The two passwords differ."],
    ].filter(Boolean);
    for (const [c, msg] of problems) setError(c, msg);
    if (problems.length) {
      problems[0][0].focus();
      return;
    }
    busy(go, true, "Setting it…");
    const mail = email.value.trim().toLowerCase();
    const res = await call(PATHS.recover, { method: "POST", body: { email: mail, recovery_code: typedCode, new_password: pw.control.value } });
    busy(go, false, "Set the new password");
    if (res.ok && typeof res.data?.recovery_code === "string") {
      pw.control.value = "";
      pw2.control.value = "";
      main.replaceChildren(recoveryCard({ code: res.data.recovery_code, email: mail, icao: null }, {
        lead: "Your new password is set. Here is your new recovery code: it is shown once, and it is how you get back in if you forget your password.",
        oldGone: true,
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
      el("div", {}, el("h1", { id: "rv-h", class: "h1 h1--auth", text: "Use your recovery code" }), el("p", { class: "body2", text: "It sets a new password and gives you a new code. Every other browser signed in to your workspace is signed out." })),
      form,
      el("p", { class: "body2" }, el("a", { class: "link", href: "/signin", dataset: { go: "" }, text: "‹ Back to sign in" })))));
}
