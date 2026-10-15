// The case strip (docs/UI-DESIGN.md 7.6, redesign A3): three lines under the eyebrow that say what
// happened, where the reports disagreed and what TEPHRA does about it. The words come from
// /static/data/cases.json, read once here, one entry per replay case, every number a claims-register
// row (research/README.md). Shown only in REPLAY, for a case with an entry; silent otherwise.

import { el } from "./util.js";

export const WHAT = "TEPHRA shows where the reports disagree, finds the flights heading into the ash area, and drafts an advisory a dispatcher decides.";

// Pure: the section for one case's story, or null when there is nothing to show.
export function caseStrip(caseStory, { mode } = {}) {
  if (mode !== "REPLAY" || !caseStory || !caseStory.happened) return null;
  return el("section", { id: "case-strip", class: "case", "aria-label": "This case" },
    el("p", { class: "case__happened", text: caseStory.happened }),
    caseStory.disagreed ? el("p", { class: "case__disagreed" }, el("span", { text: caseStory.disagreed }), " ",
      el("button", { type: "button", class: "link-btn case__sources", title: caseStory.sources || null, dataset: { act: "details-open", sec: "sources", focus: "case-sources" }, text: "Sources ›" })) : null,
    el("p", { class: "case__what", text: WHAT }));
}

// The entries, read once; null until they arrive and when the read failed (the strip then stays
// hidden, with no message: the story is complete without it). `onLoad` runs once the entries are
// in, so the story can draw the strip without waiting for the next tick.
let cases = null;
let loading = null;
export function loadCases(onLoad) {
  if (!loading) {
    loading = fetch("/static/data/cases.json", { headers: { Accept: "application/json" } })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => { cases = data && typeof data === "object" ? data : null; })
      .catch(() => { cases = null; });
  }
  return loading.then(() => { if (cases) onLoad(); });
}
export const caseOf = (caseId) => (cases && caseId && cases[caseId]) || null;
