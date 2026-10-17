// The guide page (UI-DESIGN 7.22, 7.29): a tour of each page with annotated screenshots
// (guide/shot.js), then Map key, How it works, About, the operator policy and Credits folded under More,
// built from the same builders the demo's dialogs use. Everything goes in through el()
// (textContent). The reads are public GETs; a policy that does not load says so in its own fold.
// "Start here" and the tour are static markup; this module fills the five steps (five-steps.js,
// the welcome dialog's source too), the case paragraph from the demo's one source (wall/case.js),
// the Desk step and the folds, the theme control in the foot, and draws the marks.

import { el, setAirline } from "./wall/util.js";
import { helpContent, aboutContent, creditsContent } from "./wall/controls.js";
import { policyDialog } from "./wall/policy.js";
import { EXPLAIN } from "./wall/explain.js";
import { has, setFeatures, applyFeatureNav } from "./wall/features.js";
import { caseStrip, loadCases, caseOf } from "./wall/case.js";
import { initShots } from "./guide/shot.js";
import { stepsList } from "./five-steps.js";
import { themeControl } from "./theme.js";
import { initAccountNav } from "./account-nav.js";

async function getJson(path) {
  try {
    const res = await fetch(path, { headers: { Accept: "application/json" }, cache: "no-store", signal: AbortSignal.timeout(8000) });
    return res.ok ? await res.json() : null;
  } catch {
    return null;
  }
}

// The problem paragraph: the replaying case's strip, the same words as the demo's: one line, and
// "What went wrong" opens the rest. Its "Sources ›" becomes a link into the demo's Details, and its
// third line goes (the lead above says it). Live feeds have no case; without the state the line
// sends the reader to the demo.
function caseBlock(state) {
  if (state?.mode === "LIVE") return el("p", { class: "muted", text: "Live feeds are playing: no recorded case is on the demo now." });
  const strip = state && caseStrip(caseOf(state.replay?.case_id), { mode: state.mode });
  if (!strip) return el("p", { class: "muted", text: "Open the demo for the case." });
  strip.removeAttribute("id");
  strip.querySelector(".case__what")?.remove();
  const sources = strip.querySelector(".case__sources");
  if (sources) sources.replaceWith(el("a", { class: "link-btn case__sources", href: "/demo#details-sources", title: sources.title || null, text: "Sources ›" }));
  const toggle = strip.querySelector(".case__toggle");
  const more = strip.querySelector(".case__more");
  if (toggle && more) {
    toggle.addEventListener("click", () => {
      more.hidden = !more.hidden;
      toggle.setAttribute("aria-expanded", String(!more.hidden));
    });
  }
  return strip;
}

async function fillStart(state) {
  if (state?.replay) await loadCases(() => {});
  document.getElementById("start-case").replaceChildren(caseBlock(state));
  if (state?.visitor_access === true) {
    document.getElementById("try-desk").replaceChildren(
      el("a", { href: "/desk" }, el("b", { text: "Enter the Desk as a visitor" })));
  }
}

// A link to a section (/guide#help-key) lands on it once the page is built; a folded part opens.
function landOnHash() {
  const at = location.hash && document.getElementById(location.hash.slice(1));
  if (!at) return;
  const fold = at.closest("details");
  if (fold) fold.open = true;
  at.scrollIntoView({ block: "start" });
}

async function build() {
  const [state, policy, shots] = await Promise.all([getJson("/api/state"), getJson("/api/policy"), getJson("/static/data/guide-shots.json")]);
  setFeatures(state?.features);
  setAirline(state?.airline);
  applyFeatureNav();
  for (const part of document.querySelectorAll("main [data-feature]")) part.hidden = !has(part.dataset.feature);
  initAccountNav();
  initShots(shots);
  await fillStart(state);
  document.getElementById("read-body").replaceChildren(helpContent(false, { page: true }));
  document.getElementById("how-body").replaceChildren(
    ...EXPLAIN.flatMap(([id, title, paras]) => [el("h3", { id: `how-${id}`, class: "help__h", text: title }), ...paras.map((p) => el("p", { text: p }))]));
  document.getElementById("about-body").replaceChildren(aboutContent(state, { page: true }));
  document.getElementById("credits-body").replaceChildren(creditsContent({ heading: false }));
  document.getElementById("policy-body").replaceChildren(policyDialog(policy));
  landOnHash();
}

// "What is real?" lands on About › Safety limits even when the address already ends in its hash.
document.addEventListener("click", (e) => {
  const a = e.target.closest('a[href^="#"]');
  if (a && a.getAttribute("href") === location.hash) setTimeout(landOnHash);
});

// Run it: a command's copy button copies it and says so for a moment.
document.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-copy]");
  if (!btn) return;
  const code = btn.parentElement.querySelector("code");
  try {
    await navigator.clipboard.writeText(code.textContent);
  } catch {
    return; // no clipboard here (an http page, a refusal): the command stays selectable
  }
  btn.classList.add("is-done");
  btn.setAttribute("aria-label", "Copied");
  setTimeout(() => { btn.classList.remove("is-done"); btn.setAttribute("aria-label", "Copy the command"); }, 1600);
});

window.addEventListener("hashchange", landOnHash);
document.getElementById("gpipe").replaceChildren(stepsList({ lines: "sr" }));
document.getElementById("guide-theme").replaceChildren(themeControl());
build();
