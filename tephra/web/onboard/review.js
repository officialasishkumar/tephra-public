// The Review accordion (onboarding page 9 and the workspace's Your answers): one row per page
// with its one-line summary and its state (a tick when complete, words only when something needs
// a look), opening to the answers and an Edit link; the sign-up fields that start onboarding; and
// the recovery code, shown once. Every answer goes in through el().

import { el, icon } from "../wall/util.js";
import { formatValue } from "../wall/policy.js";
import { infoButton } from "../wall/info.js";
import { ANSWER_PAGES, PROVIDER_WORDS, KEY_POLICY_VALUES, pageOf, ruleMessage, summaryOf } from "./pages.js";
import { checkOnLeave, field, illus, input, passwordInput, setError } from "./form.js";

const NOT_GIVEN = "Not given";
const or = (v) => (v == null || v === "" ? NOT_GIVEN : String(v));
const yes = (b) => (b ? "Yes" : "No");
const KEY_LABELS = Object.fromEntries(KEY_POLICY_VALUES);
const ROLE_WORDS = { approves: "Approves advisories", views: "Views only" };

const dl = (rows) => el("dl", {}, ...rows.flatMap(([k, v]) => [el("dt", { text: k }), el("dd", {}, v instanceof Node ? v : String(v))]));

// labels: policy value name -> the words a person reads (wall/policy.js labels via policyValues)
export function answerRows(page, answers, { named = {}, labels = {} } = {}) {
  const x = answers || {};
  switch (page) {
    case "airline": {
      const a = x.airline || {};
      return [
        ["Name", or(a.name)], ["ICAO · callsign prefix", `${or(a.icao)} · ${or(a.callsign_prefix)}`], ["IATA code", or(a.iata)],
        ["State of the Operator", or(a.state_of_operator)], ["AOC number", or(a.aoc_number)], ["Main base", or(a.main_base)],
        ["Operations email", or(a.ops_email)], ["Contact name", or(a.contact_name)],
      ];
    }
    case "policy": {
      const p = x.policy || {};
      const rows = [["Preset", "Policy A: avoid official ash"]];
      for (const c of p.changes || []) {
        const base = named[c.name];
        const label = labels[c.name] || KEY_LABELS[c.name] || c.name;
        const now = base ? formatValue(c.name.split(".")[1], { value: c.value, unit: base.unit }) : String(c.value);
        const was = base ? ` (Policy A ${formatValue(c.name.split(".")[1], base)})` : "";
        rows.push([label, `${now}${was} · ${c.reason}`]);
      }
      if (!(p.changes || []).length) rows.push(["Values", "As Policy A"]);
      rows.push(["Risk owner", or(p.risk_owner)], ["SRA reference", or(p.sra_ref)]);
      return rows;
    }
    case "fleet": {
      const rows = (x.fleet?.aircraft || []);
      const shown = rows.slice(0, 12).map((r) => [r.registration || "–", [r.type_icao, `${r.seats ?? "–"} seats`, r.home_base, r.hex].filter((v) => v != null && v !== "").join(" · ")]);
      if (rows.length > 12) shown.push(["And", `${rows.length - 12} more aircraft`]);
      return [...shown, ["Other callsign prefixes", (x.fleet?.extra_prefixes || []).join(", ") || NOT_GIVEN]];
    }
    case "network": {
      const list = x.network?.airports || [];
      const shown = list.slice(0, 20).map((a) => [a.icao, a.alternates?.length ? `alternates ${a.alternates.join(", ")}` : "no alternates given"]);
      if (list.length > 20) shown.push(["And", `${list.length - 20} more airports`]);
      return shown.length ? shown : [["Airports", NOT_GIVEN]];
    }
    case "schedule": {
      const s = x.schedule || {};
      if (!s.provided) return [["Schedule", NOT_GIVEN]];
      return [["Flights", String(s.flights)], ["Aircraft named", String(s.tails)], ["Crews", String(s.crews)], ["Crew bases", (s.crew_bases || []).join(", ") || NOT_GIVEN]];
    }
    case "feeds": {
      const f = x.feeds || {};
      return [["Positions", yes(f.positions)], ["Flight plans", yes(f.flight_plans)], ["Pilot reports", yes(f.pilot_reports)], ["Source system", or(f.source_system)]];
    }
    case "people":
      return (x.people?.dispatchers || []).map((d) => [d.name || "–", ROLE_WORDS[d.role] || "–"]);
    case "assistant": {
      const m = x.assistant || {};
      return [["Where it runs", m.provider ? PROVIDER_WORDS[m.provider] : NOT_GIVEN], ...(m.provider && m.provider !== "none" ? [["Model", or(m.model)], ["Lighter model", or(m.model_lite)]] : [])];
    }
    default:
      return [];
  }
}

// rows: one per page 1-8. opts: { named, labels, problems: {page: n}, unseen: Set of pages never
// opened (their answers are the defaults), editHref(page) -> string|null, onEdit(page, event) }
export function reviewList(answers, opts = {}) {
  const box = el("div", { class: "rv" });
  for (const key of ANSWER_PAGES) {
    const page = pageOf(key);
    const n = opts.problems?.[key] || 0;
    // An optional page left out ("Skip for now" on Schedule and crews) is not "Complete": its
    // summary says "Not given", and the state that it may stay so.
    const skipped = key === "schedule" && !answers?.schedule?.provided;
    // a page never opened holds the defaults: said so, never "Complete"
    const unseen = opts.unseen?.has(key);
    const state = n
      ? el("span", { class: "status status--caution" }, icon("st-caution"), el("span", { text: n === 1 ? "1 thing to check" : `${n} things to check` }))
      : unseen
        ? el("span", { class: "status status--quiet" }, el("span", { text: "Not opened · default" }))
        : skipped
        ? el("span", { class: "status status--quiet" }, el("span", { text: "Optional" }))
        : el("span", { class: "status status--ok" }, icon("i-check"), el("span", { class: "sr-only", text: "Complete" }));
    const href = opts.editHref ? opts.editHref(key) : null;
    const edit = href ? el("a", { class: "link rv__edit", href, text: `Edit ${page.short} ›` }) : null;
    if (edit && opts.onEdit) edit.addEventListener("click", (e) => opts.onEdit(key, e));
    box.append(el("details", { class: n ? "is-warn" : null, dataset: { page: key } },
      el("summary", {},
        el("span", { class: "n", "aria-hidden": "true", text: String(page.n) }),
        el("span", { class: "rv__t" }, el("b", { text: page.short }), key === "policy" ? illus() : null, el("small", { text: summaryOf(key, answers) })),
        state,
        icon("i-chevron-down", "icon chev")),
      el("div", { class: "rv__body" }, dl(answerRows(key, answers, opts)), edit)));
  }
  return box;
}

// The sign-up fields on the onboarding landing (the account comes first): the email, the password
// with its rule in the label, and the decision-support tick with its (i) beside it (the (i) never
// ticks the box; the words do). Returns { node, values(), problems(), clearSecrets() }. The page
// says when accounts are off (onboard.js signupCard).
// The decision-support tick, said once: short words, the rest behind its (i), which sits beside the
// label, outside it, so a tap on the (i) never ticks the box. Sign-up and the invite page (/join).
export function supportTick(ack, errId) {
  return el("div", { class: "field" },
    el("div", { class: "checkline" },
      el("label", { class: "check" }, ack, el("span", { text: "I understand TEPHRA is decision support only" })),
      infoButton({ topic: "decision support", label: "About decision support", text: "A person decides, and nothing is sent to an aircraft." })),
    el("p", { id: errId, class: "err", hidden: true }));
}

export function accountFields() {
  const email = input({ type: "email", autocomplete: "username", inputmode: "email", spellcheck: "false", autocapitalize: "off", maxlength: 254 });
  const pw = passwordInput({ id: "acct-password", autocomplete: "new-password" });
  const ack = el("input", { type: "checkbox", id: "acct-ack", "aria-describedby": "acct-ack-err" });
  const honeypot = el("input", { type: "text", name: "website", tabindex: "-1", autocomplete: "off", value: "" });
  const mail = () => email.value.trim().toLowerCase();
  const emailWords = () => ruleMessage("acct.email", email.value);
  const pwWords = () => ruleMessage("acct.password", pw.control.value) || (pw.control.value.trim().toLowerCase() === mail() ? "Not your email" : null);
  checkOnLeave(email, emailWords);
  checkOnLeave(pw.control, pwWords);
  ack.addEventListener("change", () => {
    if (ack.checked) setError(ack, null);
  });
  const node = el("div", { class: "signup__fields" },
    field({ id: "acct-email", label: "Work email", control: email }),
    field({ id: "acct-password", label: "Password · 12+ characters", rule: "12 characters or more", control: pw.control, slot: pw.wrap(pw.control) }),
    supportTick(ack, "acct-ack-err"),
    el("div", { class: "hp", "aria-hidden": "true" }, el("label", {}, "Leave this empty", honeypot)));
  return {
    node,
    values: () => ({ email: mail(), password: pw.control.value, ack: ack.checked, website: honeypot.value }),
    // [control id, words] for each field that is not right yet, in page order
    problems: () => [["acct-email", emailWords()], ["acct-password", pwWords()], ["acct-ack", ack.checked ? null : "Tick to continue"]].filter(([, w]) => w),
    clearSecrets: () => {
      pw.control.value = "";
    },
  };
}

// The recovery code, shown once (after the account is made, and after a recovery sets a new
// password). `r`: { code, email, icao }. The code lives in a module variable of the caller, never
// in storage. `lead` is the one line under the heading; `chip` a short label beside it (sign-up says
// "Email reset: not built" there). `next`: where the button goes once the code is saved, its
// words, and `go` when the page moves there itself (onboarding keeps the account's answers in
// memory on the way).
export function recoveryCard(r, { lead, chip = null, next = { href: "/workspace", text: "Open my workspace" }, extra = null }) {
  const copy = el("button", { type: "button", class: "btn btn--secondary btn--sm" }, icon("i-clipboard"), el("span", { text: "Copy" }));
  copy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(r.code);
      copy.lastChild.textContent = "Copied";
      window.setTimeout(() => {
        copy.lastChild.textContent = "Copy";
      }, 1600);
    } catch {
      const range = document.createRange();
      range.selectNodeContents(document.getElementById("rc-code"));
      getSelection().removeAllRanges();
      getSelection().addRange(range);
      copy.lastChild.textContent = "Selected: copy it";
    }
  });
  const dl = el("button", { type: "button", class: "btn btn--secondary btn--sm" }, icon("i-file"), el("span", { text: "Download .txt" }));
  dl.addEventListener("click", () => {
    const body = `TEPHRA recovery code\n\n${r.code}\n\nAccount email: ${r.email}\nSite: ${location.origin}\n\nKeep this file private.\n`;
    const url = URL.createObjectURL(new Blob([body], { type: "text/plain" }));
    const a = el("a", { href: url, download: `tephra-recovery-${String(r.icao || "airline").toLowerCase()}.txt`, hidden: true });
    document.body.append(a);
    a.click();
    a.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  const saved = el("input", { type: "checkbox", id: "rc-saved" });
  const open = el("a", { class: "btn btn--primary btn--block", href: next.href, "aria-disabled": "true", "aria-describedby": "rc-saved-why", dataset: next.go ? { go: "" } : null }, el("span", { text: next.text }), icon("i-arrow-right"));
  // said to a screen reader from the start; on screen only after a click the tick blocked
  const why = el("p", { id: "rc-saved-why", class: "err sr-only" }, icon("st-caution"), el("span", { text: "Tick to continue" }));
  open.addEventListener("click", (e) => {
    if (!saved.checked) {
      e.preventDefault();
      why.classList.remove("sr-only");
      saved.focus();
    }
  });
  saved.addEventListener("change", () => {
    open.setAttribute("aria-disabled", saved.checked ? "false" : "true");
    why.hidden = saved.checked;
  });
  return el("div", { class: "auth__stage" }, el("div", { class: "auth__backdrop night", "aria-hidden": "true" }),
    el("section", { class: "card authcard auth__card", "aria-labelledby": "rc-h" },
      el("h1", { id: "rc-h", class: "h2", text: "Save your recovery code" }),
      el("p", { class: "body2" }, lead, chip ? [" ", el("span", { class: "chip chip--notbuilt", text: chip })] : null),
      el("div", { class: "recov" }, el("code", { id: "rc-code", "aria-label": "Recovery code", text: r.code }), el("div", { class: "recov__act" }, copy, dl)),
      el("label", { class: "check" }, saved, el("span", { text: "I saved my code" })),
      open, why, extra));
}
