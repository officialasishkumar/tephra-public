// The workspace overview (/workspace): an airline still onboarding sees where it left off and goes
// back to its pages; once submitted, verification first (what the status pill means, once), then
// the setup kit, the answers, the data feeds, the assistant and the people. Both end with the one
// "Not built yet" line. Every value goes in through el().

import { el, icon } from "../wall/util.js";
import { ANSWER_PAGES, NOT_BUILT, PROVIDER_WORDS, checkPage, emptyValues, firstUnfinished, fromAnswers, pageOf } from "../onboard/pages.js";
import { kitCard } from "./kit.js";

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const pad = (n) => String(n).padStart(2, "0");
export function utcDay(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : `${d.getUTCDate()} ${MON[d.getUTCMonth()]}, ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`;
}

const VERIFY_WORDS = {
  pending: "A TEPHRA dispatcher checks every new airline. Until then your answers stay editable and nothing is drafted under your airline's name. You can download your setup kit now.",
  verified: "A TEPHRA dispatcher checked who you are. It does not approve your policy or your use of TEPHRA.",
};

function verification(view) {
  const step = (kind) => view.steps.find((s) => s.kind === kind);
  const declined = view.status === "declined";
  const items = [
    { key: "submitted", label: "Submitted", at: step("submitted")?.at, state: "done" },
    { key: "verifying", label: "Verifying", at: null, state: view.status === "pending" ? "now" : "done" },
    declined
      ? { key: "declined", label: "Declined", at: step("declined")?.at, state: "now" }
      : { key: "verified", label: "Verified", at: step("verified")?.at, state: view.status === "verified" ? "now" : "todo" },
  ];
  const text = declined ? `A TEPHRA dispatcher declined this airline: ${step("declined")?.reason || "no reason given"}.` : VERIFY_WORDS[view.status];
  return el("section", { class: `card pending pending--${view.status}`, "aria-labelledby": "vf-h" },
    icon(view.status === "verified" ? "st-ok" : declined ? "st-serious" : "st-caution"),
    el("div", {},
      el("h2", { id: "vf-h", text: "Verification" }),
      el("p", { text }),
      el("ol", { class: "track", "aria-label": "Verification steps" }, ...items.map((s) => el("li", { class: `is-${s.state}`, "aria-current": s.state === "now" ? "step" : null },
        el("b", { text: s.label }),
        el("span", { text: s.at ? utcDay(s.at) : s.state === "now" ? "A dispatcher reviews it" : "" }))))));
}

function card(id, iconId, title, ...kids) {
  return el("section", { class: "card wcard", "aria-labelledby": id },
    el("div", { class: "wcard__h" }, el("span", { class: "wcard__ic", "aria-hidden": "true" }, icon(iconId)), el("h2", { id, text: title })),
    ...kids);
}

// Pages of the stored answers that pass the page rules (Review counts once the account exists).
function completeness(answers) {
  const values = fromAnswers(answers);
  const open = ANSWER_PAGES.map((k) => ({ key: k, problems: checkPage(k, values) })).filter((p) => p.problems.length);
  return { done: 9 - open.length, first: open[0] ? `${pageOf(open[0].key).name}: ${open[0].problems[0].message}` : null };
}

const notBuilt = () => el("div", { class: "note note--notbuilt", role: "note" }, icon("i-info"),
  el("p", {}, el("b", { text: "Not built yet. " }), NOT_BUILT));

// A draft: the page to go back to, counted as onboarding counts it (Review is page 9).
function continueCard(view) {
  const key = firstUnfinished({ ...view.draft, values: { ...emptyValues(), ...(view.draft?.values || {}) } });
  const page = pageOf(key);
  return el("section", { class: "card pending pending--draft", "aria-labelledby": "vf-h" },
    icon("i-pencil"),
    el("div", {},
      el("h2", { id: "vf-h", text: `Continue onboarding · step ${page.n} of 9` }),
      el("p", { text: "Your answers are saved to your account. Submit them on Review: a TEPHRA dispatcher then verifies your airline, and your setup kit is ready here." }),
      el("a", { class: "btn btn--primary pending__go", href: `/onboard/${key}` }, el("span", { text: `Continue: ${page.name}` }), icon("i-arrow-right"))));
}

export function renderOverview(main, view) {
  if (view.status === "draft") {
    main.append(continueCard(view), notBuilt());
    return;
  }
  const a = view.answers;
  const c = completeness(a);
  const meter = el("div", { class: "meter" }, el("span", { class: "meter__bar", "aria-hidden": "true" }, ...Array.from({ length: 9 }, (_, i) => el("i", { class: i < c.done ? "on" : null }))), el("span", { text: `${c.done} of 9 pages` }));
  const feeds = [a.feeds.positions && "positions", a.feeds.flight_plans && "flight plans", a.feeds.pilot_reports && "pilot reports"].filter(Boolean);
  const approvers = a.people.dispatchers.filter((d) => d.role === "approves").length;
  main.append(
    verification(view),
    kitCard(view),
    el("div", { class: "wgrid" },
      card("ov-answers", "i-list", "Your answers",
        meter,
        c.first ? el("p", { class: "status status--caution" }, icon("st-caution"), el("span", { text: c.first })) : null,
        view.editable
          ? el("div", { class: "wcard__foot" }, el("a", { class: "btn btn--secondary btn--sm", href: "/workspace/answers", dataset: { go: "" }, text: "Edit answers" }))
          : el("p", { text: "Ask a TEPHRA dispatcher to change them." })),
      card("ov-feeds", "i-inbox", "Data feeds",
        el("dl", { class: "kv" }, el("dt", { text: "Format" }), el("dd", {}, el("code", { text: "tephra.airline/1" })), el("dt", { text: "Sends" }), el("dd", { text: feeds.length ? feeds.join(", ").replace(/^./, (m) => m.toUpperCase()) : "Public ADS-B only" })),
        el("p", { text: "Try a file with the dry run: every record is checked, nothing is taken in." }),
        el("div", { class: "wcard__foot" }, el("a", { class: "btn btn--secondary btn--sm", href: "/workspace/feeds", dataset: { go: "" }, text: "Try a file" }))),
      card("ov-assistant", "ta-16", "Assistant",
        el("dl", { class: "kv" },
          el("dt", { text: "Provider" }), el("dd", { text: PROVIDER_WORDS[a.assistant.provider] || "–" }),
          ...(a.assistant.provider !== "none" ? [el("dt", { text: "Models" }), el("dd", { class: "mono", text: [a.assistant.model, a.assistant.model_lite].filter(Boolean).join(" · ") })] : [])),
        el("div", { class: "wcard__foot" }, el("a", { class: "btn btn--secondary btn--sm", href: "/workspace/assistant", dataset: { go: "" }, text: "Change" }))),
      card("ov-people", "i-dispatcher", "People",
        el("p", { text: `${approvers} ${approvers === 1 ? "dispatcher" : "dispatchers"} will approve advisories in your TEPHRA. Their names never go to a model.` }))),
    notBuilt());
}
