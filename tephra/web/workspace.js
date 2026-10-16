// The airline's side after onboarding (SPEC-v2 §7): sign in at /signin (and /signin/recover), then
// the private workspace at /workspace and /workspace/<section>: Overview, Your answers, Data feeds,
// Assistant and Setup kit. Signed out, a workspace address goes to sign in with ?next= kept (only
// workspace and edit paths are followed). Sections move with the history API. Every string goes
// in through el() (textContent).

import { $, el, icon, inlineSprite } from "./wall/util.js";
import { applyFeatureNav, has, setFeatures } from "./wall/features.js";
import { initAccountNav } from "./account-nav.js";
import { safeNext } from "./onboard/pages.js";
import { clearOnboardStorage } from "./onboard/draft.js";
import { reviewList } from "./onboard/review.js";
import { renderRecover, renderSignin } from "./workspace/signin.js";
import { renderOverview } from "./workspace/overview.js";
import { renderFeeds } from "./workspace/feeds.js";
import { renderAssistant } from "./workspace/assistant.js";
import { renderKitPage } from "./workspace/kit.js";
import { ACCOUNTS_OFF, ONBOARD_OFF, PATHS, call, failWords, minutesWords, retryMinutes } from "./workspace/api.js";
import { setError } from "./onboard/form.js";

const SECTIONS = [
  ["", "Overview", "i-gauge"],
  ["answers", "Your answers", "i-list"],
  ["feeds", "Data feeds", "i-inbox"],
  ["assistant", "Assistant", "ta-16"],
  ["kit", "Setup kit", "i-file"],
];
const PILL = {
  pending: ["badge--caution", "i-clock"],
  verified: ["badge--ok", "i-check"],
  declined: ["badge--serious", "st-serious"],
};
const S = { view: null, named: {}, navMode: null };

function route() {
  const parts = location.pathname.replace(/\/+$/, "").split("/");
  if (parts[1] === "signin") return { area: "signin", recover: parts[2] === "recover" };
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

function offCard(words) {
  $("main").replaceChildren(el("div", { class: "narrow" }, el("section", { class: "card authcard" },
    el("h1", { class: "h2", text: words }),
    el("a", { class: "btn btn--primary btn--block", href: "/demo" }, el("span", { text: "Watch the demo" }), icon("i-arrow-right")))));
}

// --- the account menu's Delete account… -------------------------------------------------------------

function deleteItem() {
  const item = el("button", { type: "button", role: "menuitem", class: "tn-menu__item tn-menu__item--danger", id: "tn-delete" }, icon("i-x"), el("span", { text: "Delete account…" }));
  item.addEventListener("click", openDelete);
  return item;
}

function openDelete() {
  const dlg = $("ob-dlg");
  const pw = el("input", { id: "del-pw", class: "input", type: "password", autocomplete: "current-password", "aria-describedby": "del-pw-err" });
  const err = el("p", { id: "del-pw-err", class: "err", hidden: true });
  const cancel = el("button", { type: "button", class: "btn btn--secondary", text: "Cancel" });
  const del = el("button", { type: "submit", class: "btn btn--serious" }, el("span", { text: "Delete account" }));
  const form = el("form", { class: "pdlg__form", novalidate: true },
    el("h2", { id: "del-h", class: "h2", text: "Delete your account?" }),
    el("p", { class: "body2", text: "Your answers and your workspace are deleted. It cannot be undone." }),
    el("div", { class: "field" }, el("label", { for: "del-pw", text: "Your password" }), pw, err),
    el("div", { class: "pdlg__acts" }, cancel, del));
  cancel.addEventListener("click", () => dlg.close());
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!pw.value) {
      setError(pw, "Your password is needed.");
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
    setError(pw, res.status === 401 ? "That password doesn't match." : res.status === 429 ? `Too many tries. Try again in ${minutesWords(retryMinutes(res))}.` : failWords(res));
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

function header(view) {
  const a = view.answers.airline;
  const [cls, shape] = PILL[view.status] || PILL.pending;
  const reason = view.status === "declined" ? view.steps.find((s) => s.kind === "declined")?.reason : null;
  return el("header", { class: "ws__head" },
    el("span", { class: "ws__logo", "aria-hidden": "true", text: a.icao }),
    el("div", { class: "ws__title" }, el("h1", { class: "h1", text: a.name }), el("p", { text: "Airline workspace · private to your account" })),
    el("div", { class: "ws__pill" },
      el("span", { class: `badge ${cls}` }, icon(shape), el("span", { text: view.status_label })),
      reason ? el("p", { class: "ws__reason", text: reason }) : null));
}

function sectionNav(section, view) {
  return el("nav", { class: "ws__nav", "aria-label": "Workspace" },
    ...SECTIONS.map(([key, label, ic]) => el("a", { href: `/workspace${key ? `/${key}` : ""}`, "aria-current": key === section ? "page" : null, dataset: { go: "" } }, icon(ic), el("span", { text: label }))),
    el("hr"),
    el("p", { class: "ws__who", text: `Signed in as ${view.email}` }));
}

function answersSection(main, view) {
  const editable = view.editable;
  main.append(
    el("section", { class: "wsec", "aria-labelledby": "ans-h" },
      el("h2", { id: "ans-h", class: "h2", text: "Your answers" }),
      editable
        ? el("p", { class: "body2", text: "Pending verification: you can still change them. Each Edit opens that page with your stored answers." })
        : el("p", { class: "body2", text: `Your answers are kept as ${view.status === "declined" ? "declined" : "verified"}. Ask a TEPHRA dispatcher to change them.` }),
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
  if (!me.ok || !me.data) {
    offCard(failWords(me));
    return;
  }
  S.view = me.data;
  const view = S.view;
  const label = SECTIONS.find(([k]) => k === section)[1];
  document.title = `${section ? `${label} · ` : ""}Workspace · ${view.answers.airline.icao} · TEPHRA`;
  const content = el("div", { class: "ws__main" }, header(view));
  $("main").replaceChildren(el("div", { class: "ws" }, sectionNav(section, view), content));
  if (section === "") renderOverview(content, view);
  else if (section === "answers") {
    await loadNamed();
    answersSection(content, view);
  } else if (section === "feeds") renderFeeds(content);
  else if (section === "assistant") renderAssistant(content, view, { onSaved: (v) => { S.view = v; } });
  else if (section === "kit") await renderKitPage(content, view);
}

// --- render -----------------------------------------------------------------------------------------

async function render({ first = false } = {}) {
  const r = route();
  const navMode = r.area === "signin" ? "signin" : "workspace";
  if (navMode !== S.navMode) {
    S.navMode = navMode;
    initAccountNav({ right: $("tn-right"), signin: false, items: navMode === "workspace" ? [deleteItem()] : [] });
  }
  if (r.area === "signin") {
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
  inlineSprite();
  const [state, session] = await Promise.all([call(PATHS.state), call(PATHS.session)]);
  setFeatures(state.ok ? state.data?.features : []);
  applyFeatureNav();
  if (state.ok && !has("onboard")) {
    document.title = "Workspace · TEPHRA";
    offCard(ONBOARD_OFF);
    return;
  }
  if (session.ok && session.data && !session.data.accounts) {
    document.title = "Workspace · TEPHRA";
    offCard(ACCOUNTS_OFF);
    return;
  }
  S.signedIn = Boolean(session.ok && session.data?.signed_in);
  await render({ first: true });
}

boot();
