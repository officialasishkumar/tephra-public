// The guide page (UI-DESIGN 7.22, 7.29): a tour of each page with annotated screenshots
// (guide/shot.js), then Map key, How it works, About and the operator policy folded under More,
// built from the same builders the Wall's dialogs used. Everything goes in through el()
// (textContent). The reads are public GETs; a policy that does not load says so in its own fold.
// "Start here" and the tour are static markup; this module fills the case paragraph from the Wall's
// one source (wall/case.js), the Desk step and the folds, and draws the marks.

import { el } from "./wall/util.js";
import { helpContent, aboutContent } from "./wall/controls.js";
import { policyDialog } from "./wall/policy.js";
import { EXPLAIN } from "./wall/explain.js";
import { has, setFeatures, applyFeatureNav } from "./wall/features.js";
import { caseStrip, loadCases, caseOf } from "./wall/case.js";
import { initShots } from "./guide/shot.js";

async function getJson(path) {
  try {
    const res = await fetch(path, { headers: { Accept: "application/json" }, cache: "no-store", signal: AbortSignal.timeout(8000) });
    return res.ok ? await res.json() : null;
  } catch {
    return null;
  }
}

// The problem paragraph: the replaying case's strip, the same words as the Wall's. Its "Sources ›"
// becomes a link into the Wall's Details, and its third line goes (the lead above says it). Live
// feeds have no case; without the state the line sends the reader to the Wall.
function caseBlock(state) {
  if (state?.mode === "LIVE") return el("p", { class: "muted", text: "Live feeds are playing: no recorded case is on the Wall now." });
  const strip = state && caseStrip(caseOf(state.replay?.case_id), { mode: state.mode });
  if (!strip) return el("p", { class: "muted", text: "Open the Wall for the case." });
  strip.removeAttribute("id");
  strip.querySelector(".case__what")?.remove();
  const sources = strip.querySelector(".case__sources");
  if (sources) sources.replaceWith(el("a", { class: "link-btn case__sources", href: "/#details-sources", title: sources.title || null, text: "Sources ›" }));
  return strip;
}

async function fillStart(state) {
  if (state?.replay) await loadCases(() => {});
  document.getElementById("start-case").replaceChildren(caseBlock(state));
  if (state?.visitor_access === true) {
    document.getElementById("try-desk").replaceChildren(
      el("a", { href: "/desk" }, el("b", { text: "Enter the Desk as a visitor" }), el("span", { text: "Hold to approve, then open Record" })));
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
  applyFeatureNav();
  for (const part of document.querySelectorAll("[data-feature]")) part.hidden = !has(part.dataset.feature);
  initShots(shots);
  await fillStart(state);
  document.getElementById("read-body").replaceChildren(helpContent(false, { page: true }));
  document.getElementById("how-body").replaceChildren(
    ...EXPLAIN.flatMap(([id, title, paras]) => [el("h3", { id: `how-${id}`, class: "help__h", text: title }), ...paras.map((p) => el("p", { text: p }))]));
  document.getElementById("about-body").replaceChildren(aboutContent(state, { page: true }));
  document.getElementById("policy-body").replaceChildren(policyDialog(policy));
  landOnHash();
}

window.addEventListener("hashchange", landOnHash);
build();
