// The guide page (UI-DESIGN 7.22): Help, About and the operator policy, built from the same builders
// the Wall's dialogs used. Everything goes in through el() (textContent). The two reads are public
// GETs; a policy that does not load says so in its own section. "Start here" is static markup; this
// module fills its case paragraph from the Wall's one source (wall/case.js) and its Desk step.

import { el } from "./wall/util.js";
import { helpContent, aboutContent } from "./wall/controls.js";
import { policyDialog } from "./wall/policy.js";
import { EXPLAIN } from "./wall/explain.js";
import { setFeatures, applyFeatureNav } from "./wall/features.js";
import { caseStrip, loadCases, caseOf } from "./wall/case.js";

async function getJson(path) {
  try {
    const res = await fetch(path, { headers: { Accept: "application/json" }, cache: "no-store", signal: AbortSignal.timeout(8000) });
    return res.ok ? await res.json() : null;
  } catch {
    return null;
  }
}

const section = (id, title, body) => el("section", { id, class: "guide__sec", "aria-labelledby": `${id}-h` },
  el("h2", { id: `${id}-h`, class: "guide__h", text: title }), body);

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
      el("a", { href: "/desk", text: "Enter the Desk as a visitor" }), ": when a draft waits, decide on it (hold to approve) and open its record line; when none waits, the Desk says why and what to do by hand.");
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
  const [state, policy] = await Promise.all([getJson("/api/state"), getJson("/api/policy")]);
  setFeatures(state?.features);
  applyFeatureNav();
  await fillStart(state);
  document.getElementById("guide").replaceChildren(
    section("read", "Read the map", helpContent(false, { page: true })),
    section("how", "How each part works", el("div", { class: "guide__how" },
      ...EXPLAIN.flatMap(([id, title, paras]) => [el("h3", { id: `how-${id}`, class: "help__h", text: title }), ...paras.map((p) => el("p", { text: p }))]))),
    section("about", "About TEPHRA", aboutContent(state, { page: true })),
    section("policy", "Operator policy", policyDialog(policy)));
  landOnHash();
}

build();
