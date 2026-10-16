// The Review accordion (onboarding page 9 and the workspace's Your answers): one row per page
// with its one-line summary and its state in a word and a shape, opening to the answers and an
// Edit link; and the account form that ends onboarding. Every answer goes in through el().

import { el, icon } from "../wall/util.js";
import { formatValue } from "../wall/policy.js";
import { ANSWER_PAGES, PROVIDER_WORDS, KEY_POLICY_VALUES, pageOf, summaryOf } from "./pages.js";
import { field, illus, input, note, passwordInput } from "./form.js";

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
      const rows = [["Preset", "Policy A · avoid every official ash area"]];
      for (const c of p.changes || []) {
        const base = named[c.name];
        const label = labels[c.name] || KEY_LABELS[c.name] || c.name;
        const now = base ? formatValue(c.name.split(".")[1], { value: c.value, unit: base.unit }) : String(c.value);
        const was = base ? ` (Policy A ${formatValue(c.name.split(".")[1], base)})` : "";
        rows.push([label, `${now}${was} · ${c.reason}`]);
      }
      if (!(p.changes || []).length) rows.push(["Values", "As Policy A"]);
      rows.push(["Risk owner", or(p.risk_owner)], ["Your SRA reference", or(p.sra_ref)]);
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
      return [["Positions", yes(f.positions)], ["Flight plans", yes(f.flight_plans)], ["Pilot reports", yes(f.pilot_reports)], ["Where they come from", or(f.source_system)]];
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

// rows: one per page 1-8. opts: { named, labels, problems: {page: n}, editHref(page) -> string|null,
// onEdit(page, event) }
export function reviewList(answers, opts = {}) {
  const box = el("div", { class: "rv" });
  for (const key of ANSWER_PAGES) {
    const page = pageOf(key);
    const n = opts.problems?.[key] || 0;
    // An optional page left out ("Skip for now" on Schedule and crews) is not "Complete": its
    // summary says "Not given", and the state that it may stay so.
    const skipped = key === "schedule" && !answers?.schedule?.provided;
    const state = n
      ? el("span", { class: "status status--caution" }, icon("st-caution"), el("span", { text: n === 1 ? "1 thing to check" : `${n} things to check` }))
      : skipped
        ? el("span", { class: "status status--quiet" }, el("span", { text: "Optional" }))
        : el("span", { class: "status status--ok" }, icon("i-check"), el("span", { text: "Complete" }));
    const href = opts.editHref ? opts.editHref(key) : null;
    const edit = href ? el("a", { class: "link rv__edit", href, text: `Edit ${page.name} ›` }) : null;
    if (edit && opts.onEdit) edit.addEventListener("click", (e) => opts.onEdit(key, e));
    box.append(el("details", { class: n ? "is-warn" : null, dataset: { page: key } },
      el("summary", {},
        el("span", { class: "n", "aria-hidden": "true", text: String(page.n) }),
        el("span", { class: "rv__t" }, el("b", { text: page.name }), key === "policy" ? illus() : null, el("small", { text: summaryOf(key, answers, opts.named) })),
        state,
        icon("i-chevron-down", "icon chev")),
      el("div", { class: "rv__body" }, dl(answerRows(key, answers, opts)), edit)));
  }
  return box;
}

// The account section of page 9. Returns { node, values(), setDisabled(on), fields }.
export function accountForm({ accountsOn }) {
  const email = input({ type: "email", autocomplete: "username", inputmode: "email", spellcheck: "false", autocapitalize: "off" });
  const pw = passwordInput({ id: "acct-password", autocomplete: "new-password" });
  const pw2 = passwordInput({ id: "acct-password2", autocomplete: "new-password" });
  const ack = el("input", { type: "checkbox", id: "acct-ack", "aria-describedby": "acct-ack-err" });
  const honeypot = el("input", { type: "text", name: "website", tabindex: "-1", autocomplete: "off", value: "" });
  const node = el("section", { class: "section", "aria-labelledby": "acct-h" },
    el("h2", { id: "acct-h", text: "Create your account" }),
    accountsOn ? null : note("caution", null, "Airline accounts are off on this server: TEPHRA_SESSION_SECRET is not set.", { role: "status" }),
    field({ id: "acct-email", label: "Email", hint: "You sign in with it. It can be the operations email.", control: email }),
    el("div", { class: "row2" },
      field({ id: "acct-password", label: "Password", hint: "12 characters or more", control: pw.control, slot: pw.wrap(pw.control) }),
      field({ id: "acct-password2", label: "Password again", control: pw2.control, slot: pw2.wrap(pw2.control) })),
    el("div", { class: "field" },
      el("label", { class: "check" }, ack, el("span", { text: "I understand TEPHRA is decision support only: a person decides, and nothing is sent to an aircraft." })),
      el("p", { id: "acct-ack-err", class: "err", hidden: true })),
    el("div", { class: "hp", "aria-hidden": "true" }, el("label", {}, "Leave this empty", honeypot)),
    note("info", null, el("span", {}, "Next you get a ", el("b", { text: "recovery code, shown once" }), ". Keep it: password reset by email is not built, so the code is how you get back in.")));
  return {
    node,
    fields: { email, password: pw.control, password2: pw2.control, ack },
    values: () => ({ email: email.value.trim().toLowerCase(), password: pw.control.value, password2: pw2.control.value, ack: ack.checked, website: honeypot.value }),
    clearSecrets: () => {
      pw.control.value = "";
      pw2.control.value = "";
    },
  };
}

export const passwordAside = () => el("aside", { class: "card aside-card", "aria-labelledby": "pw-aside-h" },
  el("h2", { id: "pw-aside-h" }, icon("i-lock"), el("span", { text: "How your password is kept" })),
  el("p", { text: "A salted scrypt hash: TEPHRA never stores the password itself. After 5 wrong tries, sign-in waits 15 minutes." }));

// The recovery code, shown once (after the account is made, and after a recovery sets a new
// password). `r`: { code, email, icao }. The code lives in a module variable of the caller, never
// in storage.
export function recoveryCard(r, { lead, oldGone = false, submitted = true }) {
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
  const open = el("a", { class: "btn btn--primary btn--block", href: "/workspace", "aria-disabled": "true", "aria-describedby": "rc-saved-why" }, el("span", { text: "Open my workspace" }), icon("i-arrow-right"));
  const why = el("p", { id: "rc-saved-why", class: "hint", text: "Tick the box above first." });
  open.addEventListener("click", (e) => {
    if (!saved.checked) {
      e.preventDefault();
      saved.focus();
    }
  });
  saved.addEventListener("change", () => {
    open.setAttribute("aria-disabled", saved.checked ? "false" : "true");
    why.hidden = saved.checked;
  });
  return el("div", { class: "auth__stage" }, el("div", { class: "auth__backdrop night", "aria-hidden": "true" }),
    el("section", { class: "card authcard auth__card", "aria-labelledby": "rc-h" },
      submitted ? el("p", { class: "status status--caution" }, icon("i-clock"), el("span", { text: "Submitted · pending verification" })) : null,
      el("h1", { id: "rc-h", class: "h2", text: "Save your recovery code" }),
      el("p", { class: "body2", text: lead }),
      oldGone ? el("p", { class: "body2", text: "Your old code no longer works." }) : null,
      el("div", { class: "recov" }, el("code", { id: "rc-code", "aria-label": "Recovery code", text: r.code }), el("div", { class: "recov__act" }, copy, dl)),
      el("label", { class: "check" }, saved, el("span", { text: "I have saved my recovery code" })),
      open, why));
}
