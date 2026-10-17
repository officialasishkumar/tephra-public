// The workspace overview (/workspace): an airline still onboarding sees where it left off and goes
// back to its pages; once submitted, where verification stands in one line (what it means behind
// its (i)), then, when this site hosts airlines (view.hosted, from workspace.js), Go live on TEPHRA
// (golive.js), then the answers, the data feeds, the assistant and the people, a line each (once
// the airline has its own space, only the answers stay). Both end with the one line that says this
// site runs no airline's operation yet, or, once hosting is open to the airline, the site's limit;
// once the airline has its space that line goes (its places line says the limit where it matters).
// Every value goes in through el().

import { el, icon } from "../wall/util.js";
import { infoButton } from "../wall/info.js";
import { ANSWER_PAGES, NOT_ON_YET, PROVIDER_WORDS, notBuiltHosted, checkPage, emptyValues, firstUnfinished, fromAnswers, pageOf, problemText } from "../onboard/pages.js";
import { WAITING_WORDS, hostedCards } from "./golive.js";

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const pad = (n) => String(n).padStart(2, "0");
export function utcDay(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : `${d.getUTCDate()} ${MON[d.getUTCMonth()]}, ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`;
}

// The status in one line (the Overview's header shows no pill: this card says it); what it means
// behind the (i). A declined airline's line carries the dispatcher's reason.
const VERIFY = {
  pending: ["A dispatcher is checking your airline. Answers stay editable.", "Until verified, nothing is drafted under your airline's name."],
  verified: ["Verified.", "A TEPHRA dispatcher checked who you are. It does not approve your policy or your use of TEPHRA."],
  declined: ["Declined.", "A TEPHRA dispatcher declined this airline. Your answers stay as they are."],
};
// Where this site hosts airlines, a dispatcher or one of TEPHRA's operators verifies: the words
// name neither (the record says who).
const VERIFY_HOSTED = {
  pending: ["TEPHRA is checking your airline. Answers stay editable.", "Until verified, nothing is drafted under your airline's name."],
  verified: ["Verified.", "TEPHRA checked who you are. It does not approve your policy or your use of TEPHRA."],
  declined: ["Declined.", "TEPHRA declined this airline. Your answers stay as they are."],
};

function verification(view, waiting = false) {
  const step = (kind) => view.steps.find((s) => s.kind === kind);
  const declined = view.status === "declined";
  const words = view.hostedSite ? VERIFY_HOSTED : VERIFY;
  const [said, more] = words[view.status] || words.pending;
  const reason = declined ? step("declined")?.reason : null;
  const line = reason ? `Declined: ${reason}` : said;
  const cut = line.lastIndexOf(" ") + 1;
  const [lead, last] = [line.slice(0, cut), line.slice(cut)];
  const items = [
    { label: "Submitted", at: step("submitted")?.at, state: "done" },
    { label: "Verifying", at: null, state: view.status === "pending" ? "now" : "done" },
    declined
      ? { label: "Declined", at: step("declined")?.at, state: "now" }
      : { label: "Verified", at: step("verified")?.at, state: view.status === "verified" ? "now" : "todo" },
  ];
  return el("section", { class: `card pending pending--${view.status}`, "aria-label": "Verification" },
    icon(view.status === "verified" ? "st-ok" : declined ? "st-off" : "st-caution"),
    el("div", {},
      // the (i) stays on the line with the last word, never alone on a line of its own
      el("p", { id: "vf-line", class: "pending__line" }, el("span", { text: lead }),
        el("span", { class: "pending__tail" }, last, infoButton({ topic: "verification", label: "About verification", text: more }))),
      waiting ? el("p", { id: "vf-hosting", class: "pending__hosting", text: WAITING_WORDS }) : null,
      view.status === "verified"
        ? null
        : el("ol", { class: "track", "aria-label": "Verification steps" }, ...items.map((s) => el("li", { class: `is-${s.state}`, "aria-current": s.state === "now" ? "step" : null },
          el("b", { text: s.label }),
          s.at ? el("span", { text: utcDay(s.at) }) : null)))));
}

// One row: an icon, a name, what it holds now, and where to change it.
function row(iconId, name, value, ...end) {
  return el("li", { class: "wrow" },
    el("span", { class: "wrow__ic", "aria-hidden": "true" }, icon(iconId)),
    el("b", { class: "wrow__name", text: name }),
    el("span", { class: "wrow__val" }, value),
    ...end);
}

const go = (href, text) => el("a", { class: "link wrow__go", href, dataset: { go: "" }, text });

// Pages of the stored answers that pass the page rules (Review counts once the account exists).
function completeness(answers) {
  const values = fromAnswers(answers);
  const open = ANSWER_PAGES.map((k) => ({ key: k, problems: checkPage(k, values) })).filter((p) => p.problems.length);
  return { done: 9 - open.length, first: open[0] ? problemText(open[0].key, open[0].problems[0]) : null };
}

// `max`: the site's airline limit once hosting is open to the airline (null: today's line)
const notYet = (max = null) => el("p", { id: "ws-notyet", class: "notyet" }, icon("i-info"), el("span", { text: max != null ? notBuiltHosted(max) : NOT_ON_YET }));

// A draft: the page to go back to, counted as onboarding counts it (Review is page 9).
function continueCard(view) {
  const key = firstUnfinished({ ...view.draft, values: { ...emptyValues(), ...(view.draft?.values || {}) } });
  const page = pageOf(key);
  return el("section", { class: "card pending pending--draft", "aria-labelledby": "vf-h" },
    icon("i-pencil"),
    el("div", {},
      el("h2", { id: "vf-h", text: `Step ${page.n} of 9` }),
      el("p", { text: "Saved. Submit on Review when you are done." }),
      el("a", { class: "btn btn--primary pending__go", href: `/onboard/${key}` }, el("span", { text: `Continue: ${page.short}` }), icon("i-arrow-right"))));
}

export function renderOverview(main, view) {
  if (view.status === "draft") {
    main.append(continueCard(view), notYet());
    return;
  }
  const a = view.answers;
  const c = completeness(a);
  const feeds = [a.feeds.positions && "positions", a.feeds.flight_plans && "flight plans", a.feeds.pilot_reports && "pilot reports"].filter(Boolean);
  const approvers = a.people.dispatchers.filter((d) => d.role === "approves").length;
  const model = a.assistant.provider !== "none" ? [...new Set([a.assistant.model, a.assistant.model_lite].filter(Boolean))].join(" ·\u00a0") : "";
  // hosting on this site: view.hosted is null when it is off; a read that failed says so itself
  const hosted = view.status === "verified" ? view.hosted || null : null;
  const waiting = Boolean(hosted?.me && hosted.me.waiting === "hosting_not_approved");
  // once the airline has its space on this site, Go live's checklist and the space's own Feeds and
  // Settings say what these rows said: only the answers stay (mockup workspace-golive), so nothing
  // here repeats or contradicts the checklist
  const spaced = Boolean(hosted?.own && hosted.header);
  main.append(
    verification(view, waiting),
    ...hostedCards(view, hosted, { onChange: () => view.onHostedChange?.() }),
    el("ul", { class: "wrows", "aria-label": "Your workspace" },
      row("i-list", "Your answers",
        [`${c.done} of 9`, c.first ? el("span", { class: "status status--caution" }, " ", icon("st-caution"), el("span", { text: c.first })) : null],
        view.editable ? go("/workspace/answers", "Edit") : el("span", { class: "wrow__note", text: "Locked: ask a dispatcher" })),
      spaced ? null : row("i-inbox", "Data feeds", feeds.length ? feeds.join(", ").replace(/^./, (m) => m.toUpperCase()) : "Public ADS-B only", go("/workspace/feeds", "Dry run")),
      spaced ? null : row("ta-16", "Assistant", [PROVIDER_WORDS[a.assistant.provider] || "–", model ? el("span", { class: "mono wrow__sub", text: ` ·\u00a0${model}` }) : null], go("/workspace/assistant", "Change")),
      spaced ? null : row("i-dispatcher", "People", `${approvers} ${approvers === 1 ? "approver" : "approvers"}`,
        infoButton({ topic: "names", label: "About names", text: "Names never go to a model." }))),
    ...(spaced ? [] : [notYet(hosted && !hosted.error && hosted.me ? hosted.me.max_airlines : null)]));
}
