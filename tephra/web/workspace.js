// The airline's side (SPEC-v2 §7): sign in at /signin (and /signin/recover), then the private
// workspace at /workspace and /workspace/<section>: Overview, Your answers, Data feeds and
// Assistant. An airline still onboarding (a draft) has the Overview alone, which sends it back to
// its pages; the rest comes once it submits. Signed out, a workspace
// address goes to sign in with ?next= kept (only workspace and edit paths are followed). Sections
// move with the history API. Every string goes in through el() (textContent).
// With hosting on (SPEC hosted §5.1), a verified airline's Overview carries Go live on TEPHRA
// (workspace/golive.js), a login that only belongs to hosted airlines (no onboarding record) gets
// "Your airlines", and /join#<token> is the invite page (workspace/join.js), whose token is taken
// out of the address bar before anything else runs.

import { $, el, icon, inlineSprite } from "./wall/util.js";
import { applyFeatureNav, has, setFeatures } from "./wall/features.js";
import { initAccountNav, showAccountWho } from "./account-nav.js";
import { WHO_READS, safeNext } from "./onboard/pages.js";
import { clearOnboardStorage } from "./onboard/draft.js";
import { reviewList } from "./onboard/review.js";
import { renderRecover, renderSignin } from "./workspace/signin.js";
import { renderOverview } from "./workspace/overview.js";
import { renderFeeds } from "./workspace/feeds.js";
import { renderAssistant } from "./workspace/assistant.js";
import { airlinesList, loadHosted } from "./workspace/golive.js";
import { renderJoin, takeToken } from "./workspace/join.js";
import { ACCOUNTS_OFF, ACCOUNTS_OFF_HOW, HOSTED, ONBOARD_OFF, PATHS, call, errorCode, failWords, minutesWords, retryMinutes, spacePath } from "./workspace/api.js";
import { infoButton } from "./wall/info.js";
import { setError } from "./onboard/form.js";

const SECTIONS = [
  ["", "Overview", "i-gauge"],
  ["answers", "Your answers", "i-list"],
  ["feeds", "Data feeds", "i-inbox"],
  ["assistant", "Assistant", "ta-16"],
];
const PILL = {
  draft: ["badge--draft", "i-pencil"],
  pending: ["badge--caution", "i-clock"],
  verified: ["badge--ok", "i-check"],
  declined: ["badge--serious", "st-off"],
};
const S = { view: null, named: {}, navMode: null, joinToken: null };

function route() {
  const parts = location.pathname.replace(/\/+$/, "").split("/");
  if (parts[1] === "signin") return { area: "signin", recover: parts[2] === "recover" };
  if (parts[1] === "join") return { area: "join" };
  return { area: "workspace", section: parts[2] || "" };
}

function go(path) {
  history.pushState(null, "", path);
  render();
}

function focusHeading(sel = "h1") {
  const h = $("main").querySelector(sel) || $("main").querySelector("h1");
  if (!h) return;
  h.tabIndex = -1;
  h.focus();
  window.scrollTo(0, 0);
}

// `how`: the operator's step, behind an (i) beside the heading
function offCard(words, how = null) {
  $("main").replaceChildren(el("div", { class: "narrow" }, el("section", { class: "card authcard" },
    el("div", { class: "form__h1" }, el("h1", { class: "h2", text: words }), how ? infoButton({ topic: "the operator", label: "For the operator", text: how }) : null),
    el("a", { class: "btn btn--primary btn--block", href: "/demo" }, el("span", { text: "Watch the demo" }), icon("i-arrow-right")))));
}

// --- the account menu's Delete account… -------------------------------------------------------------

function deleteItem() {
  const item = el("button", { type: "button", role: "menuitem", class: "tn-menu__item tn-menu__item--danger", id: "tn-delete" }, icon("i-x"), el("span", { text: "Delete account…" }));
  item.addEventListener("click", openDelete);
  return item;
}

// An account a hosted airline still needs (SPEC hosted §3.4).
const DELETE_REFUSED = {
  hosted_airline: "Your airline still has its space on TEPHRA. Ask TEPHRA's operators to suspend it and delete its data first.",
  last_ops_manager: "You are the last ops manager of an airline on TEPHRA. Make another member ops manager first, in its Settings › People.",
};

function openDelete() {
  const dlg = $("ob-dlg");
  const pw = el("input", { id: "del-pw", class: "input", type: "password", autocomplete: "current-password", "aria-describedby": "del-pw-err" });
  const err = el("p", { id: "del-pw-err", class: "err", hidden: true });
  const cancel = el("button", { type: "button", class: "btn btn--secondary", text: "Cancel" });
  const del = el("button", { type: "submit", class: "btn btn--serious" }, el("span", { text: "Delete account" }));
  const form = el("form", { class: "pdlg__form", novalidate: true },
    el("h2", { id: "del-h", class: "h2", text: "Delete your account?" }),
    el("p", { class: "body2", text: "Deletes your answers and workspace for good." }),
    el("div", { class: "field" }, el("label", { for: "del-pw", text: "Your password" }), pw, err),
    el("div", { class: "pdlg__acts" }, cancel, del));
  cancel.addEventListener("click", () => dlg.close());
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!pw.value) {
      setError(pw, "Required");
      pw.focus();
      return;
    }
    del.disabled = true;
    const res = await call(PATHS.remove, { method: "POST", body: { password: pw.value } });
    del.disabled = false;
    if (res.status === 204 || res.ok) {
      pw.value = "";
      clearOnboardStorage();
      location.assign("/");
      return;
    }
    setError(pw, res.status === 401 ? "That password doesn't match." : res.status === 429 ? `Too many tries. Try again in ${minutesWords(retryMinutes(res))}.` : DELETE_REFUSED[errorCode(res)] || failWords(res));
    pw.select();
  });
  dlg.replaceChildren(form);
  dlg.setAttribute("aria-labelledby", "del-h");
  dlg.addEventListener("close", () => {
    pw.value = "";
  }, { once: true });
  dlg.showModal();
  pw.focus();
}

// --- the workspace frame ----------------------------------------------------------------------------

// A draft's name and ICAO are as typed on page 1 until it submits; none typed, "Your airline".
const identity = (view) => (view.answers ? view.answers.airline : { name: view.draft?.values?.airline?.name?.trim() || "Your airline", icao: view.draft?.values?.airline?.icao?.trim().toUpperCase() || "" });

// On a submitted airline's Overview the status card says the status, once; the pill stays on the
// other sections (and for a draft).
function header(view, { pill = true } = {}) {
  const a = identity(view);
  showAccountWho(a.name === "Your airline" ? { icao: a.icao } : a);
  const [cls, shape] = PILL[view.status] || PILL.pending;
  const reason = view.status === "declined" ? view.steps.find((s) => s.kind === "declined")?.reason : null;
  return el("header", { class: "ws__head" },
    el("span", { class: "ws__logo", "aria-hidden": "true", text: a.icao }),
    el("div", { class: "ws__title" }, el("h1", { class: "h1", text: a.name }), el("p", { class: "ws__private" }, icon("i-lock"), el("span", { text: "Private to your airline" }),
      infoButton({ topic: "who reads your answers", label: "Who reads your answers", text: WHO_READS, actions: [el("a", { class: "link", href: "/privacy", text: "Privacy" })] }))),
    pill
      ? el("div", { class: "ws__pill" },
        el("span", { class: `badge ${cls}` }, icon(shape), el("span", { text: view.status_label })),
        reason ? el("p", { class: "ws__reason", text: reason }) : null)
      : null);
}

// Once the airline has its own space on this site, the space's Feeds and Settings › Assistant are
// where those live: the nav drops the onboarding's Data feeds and Assistant (as the Overview drops
// their rows), and their addresses open the space's pages.
const SPACE_PAGE = { feeds: "/feeds", assistant: "/settings/assistant" };
async function ownSpace(view) {
  if (view.status !== "verified" || !has("hosted")) return null;
  const icao = view.answers?.airline?.icao;
  if (view.hosted !== undefined) return view.hosted?.own ? icao : null;
  const me = await call(HOSTED.me);
  return me.ok && (me.data?.memberships || []).some((m) => m.icao === icao) ? icao : null;
}

function sectionNav(section, view, space = null) {
  const shown = view.status === "draft" ? SECTIONS.slice(0, 1) : SECTIONS.filter(([k]) => !(space && SPACE_PAGE[k]));
  return el("nav", { class: "ws__nav", "aria-label": "Your airline" },
    ...shown.map(([key, label, ic]) => el("a", { href: `/workspace${key ? `/${key}` : ""}`, "aria-current": key === section ? "page" : null, dataset: { go: "" } }, icon(ic), el("span", { text: label }))),
    el("hr"),
    el("p", { class: "ws__who", text: `Signed in as ${view.email}` }));
}

function answersSection(main, view) {
  const editable = view.editable;
  main.append(
    el("section", { class: "wsec", "aria-labelledby": "ans-h" },
      el("h2", { id: "ans-h", class: "h2", text: "Your answers" }),
      editable ? null : el("p", { class: "body2", text: "Locked. Ask a dispatcher to change them." }),
      reviewList(view.answers, { named: S.named, editHref: editable ? (k) => `/onboard/${k}?edit=1` : null })));
}

async function loadNamed() {
  if (Object.keys(S.named).length) return;
  const res = await call(PATHS.policy);
  const p = res.ok ? res.data?.policy : null;
  if (!p) return;
  for (const block of Object.keys(p)) {
    if (!p[block] || typeof p[block] !== "object" || Array.isArray(p[block])) continue;
    for (const [k, v] of Object.entries(p[block])) if (v && typeof v === "object" && "value" in v && "unit" in v) S.named[`${block}.${k}`] = { value: v.value, unit: v.unit };
  }
}

// A login with no onboarding record belongs only to hosted airlines: its workspace is the list.
async function memberOnly(section) {
  if (section) history.replaceState(null, "", "/workspace");
  document.title = "Your airlines · TEPHRA";
  showAccountWho(null);
  const me = await call(HOSTED.me);
  if (!me.ok || !me.data) {
    offCard(failWords(me));
    return;
  }
  const list = me.data.memberships || [];
  $("main").replaceChildren(el("div", { class: "narrow yourairs" },
    el("h1", { class: "h1", text: "Your airlines" }),
    el("p", { class: "body2", text: "Each airline's pages are private to its members and TEPHRA's operators." }),
    list.length
      ? airlinesList(list, { title: list.length === 1 ? "Your airline" : `${list.length} airlines` })
      : el("p", { class: "status status--quiet" }, icon("st-off"), el("span", { text: "No airline yet. An ops manager's invite link adds you." }))));
}

async function workspace(section) {
  const known = SECTIONS.map(([k]) => k);
  if (!known.includes(section)) {
    offCard("No such workspace page.");
    return;
  }
  const me = await call(PATHS.me);
  if (me.status === 401) {
    location.replace(`/signin?next=${encodeURIComponent(location.pathname)}`);
    return;
  }
  if (me.status === 404 && errorCode(me) === "no_airline_record") {
    await memberOnly(section);
    return;
  }
  if (!me.ok || !me.data) {
    offCard(failWords(me));
    return;
  }
  S.view = me.data;
  const view = S.view;
  // this site hosts airlines: an operator, not only a Desk dispatcher, may verify (overview words)
  view.hostedSite = has("hosted");
  if (view.status === "draft" && section) {
    history.replaceState(null, "", "/workspace");
    await workspace("");
    return;
  }
  // hosting on this site: the Overview's Go live card (null when the server has it off)
  if (section === "" && view.status === "verified" && has("hosted")) {
    view.hosted = await loadHosted(view.answers?.airline?.icao);
    view.onHostedChange = () => workspace(section).then(() => focusHeading("#gl-h"));
  }
  const space = await ownSpace(view);
  if (space && SPACE_PAGE[section]) {
    location.replace(spacePath(space, SPACE_PAGE[section]));
    return;
  }
  const label = SECTIONS.find(([k]) => k === section)[1];
  document.title = `${section ? `${label} · ` : ""}Your airline · ${[identity(view).icao, "TEPHRA"].filter(Boolean).join(" · ")}`;
  const content = el("div", { class: "ws__main" }, header(view, { pill: section !== "" || view.status === "draft" }));
  $("main").replaceChildren(el("div", { class: "ws" }, sectionNav(section, view, space), content));
  if (section === "") renderOverview(content, view);
  else if (section === "answers") {
    await loadNamed();
    answersSection(content, view);
  } else if (section === "feeds") renderFeeds(content);
  else if (section === "assistant") renderAssistant(content, view, { onSaved: (v) => { S.view = v; } });
}

// --- render -----------------------------------------------------------------------------------------

async function render({ first = false } = {}) {
  const r = route();
  const navMode = r.area === "workspace" ? "workspace" : r.area;
  if (navMode !== S.navMode) {
    S.navMode = navMode;
    initAccountNav({ right: $("tn-right"), signin: false, items: navMode === "workspace" ? [deleteItem()] : [] });
  }
  if (r.area === "join") {
    if (!has("hosted")) offCard("Airlines are not hosted on this server.");
    else await renderJoin($("main"), { token: S.joinToken, signedIn: S.signedIn });
  } else if (r.area === "signin") {
    const next = new URLSearchParams(location.search).get("next");
    if (S.signedIn) {
      location.replace(safeNext(next));
      return;
    }
    if (r.recover) renderRecover($("main"));
    else renderSignin($("main"), { next });
  } else {
    await workspace(r.section);
  }
  focusHeading(first ? "h1" : r.area === "workspace" && r.section ? "main h2" : "h1");
}

document.addEventListener("click", (e) => {
  const a = e.target.closest("a[data-go]");
  if (!a || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
  const href = a.getAttribute("href");
  if (!/^\/(workspace|signin)/.test(href)) return;
  e.preventDefault();
  go(href);
});
window.addEventListener("popstate", () => render());

async function boot() {
  // the invite token leaves the address bar before any request or render
  S.joinToken = takeToken();
  inlineSprite();
  const [state, session] = await Promise.all([call(PATHS.state), call(PATHS.session)]);
  setFeatures(state.ok ? state.data?.features : []);
  applyFeatureNav();
  if (state.ok && !has("onboard")) {
    document.title = "Your airline · TEPHRA";
    offCard(ONBOARD_OFF);
    return;
  }
  if (session.ok && session.data && !session.data.accounts) {
    document.title = "Your airline · TEPHRA";
    offCard(ACCOUNTS_OFF, ACCOUNTS_OFF_HOW);
    return;
  }
  S.signedIn = Boolean(session.ok && session.data?.signed_in);
  await render({ first: true });
}

boot();
