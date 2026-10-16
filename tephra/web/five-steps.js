// The five steps of how TEPHRA works, said once for every place that shows them: the Guide's
// Start here, the demo's welcome dialog and the side panel's mini pipeline. Words and icons live
// only here (tests/test_five_steps.py); each place picks a size.

import { el, icon } from "./wall/util.js";

export const FIVE_STEPS = [
  { key: "feeds", icon: "i-satellite", name: "Public feeds", short: "Feeds", line: "SIGMET · VAA · VONA · JMA · winds · aircraft" },
  { key: "code", icon: "i-code", name: "Code checks", short: "Checks", line: "Every disagreement, every flight at risk" },
  { key: "ai", icon: "ta-16", name: "TEPHRA Assistant", short: "Assistant", line: "Reads the ash, plans each flight, drafts" },
  { key: "desk", icon: "i-dispatcher", name: "A person decides", short: "You decide", line: "Approve, edit or reject on the Desk" },
  { key: "record", icon: "i-proof", name: "The record", short: "Record", line: "Every step, hash-chained" },
];

function largeStep(step, n) {
  return el("li", { class: `steps5__n steps5__n--${step.key}` },
    el("span", { class: "steps5__node" }, icon(step.icon), el("span", { class: "steps5__num", "aria-hidden": "true", text: n })),
    el("b", {}, el("span", { class: "sr-only", text: `Step ${n}: ` }), step.name),
    el("span", { class: "steps5__line", text: step.line }));
}

function smallStep(step) {
  return el("li", { class: `steps5__n steps5__n--${step.key}`, dataset: { step: step.key } },
    el("span", { class: "steps5__node" }, icon(step.icon)),
    el("span", { class: "steps5__short", text: step.short }));
}

// size "lg": 56 px nodes with a number badge and the words under each (welcome dialog, Guide);
// "sm": 32 px nodes with the short names only (the side panel). `current` is a step key: that
// node is ringed and its item carries aria-current="step".
export function stepsList({ size = "lg", current = null, label = "How TEPHRA works, in five steps", id = null } = {}) {
  const items = FIVE_STEPS.map((step, i) => (size === "sm" ? smallStep(step) : largeStep(step, i + 1)));
  const list = el("ol", { class: `steps5 steps5--${size}`, "aria-label": label, id }, items);
  setCurrentStep(list, current);
  return list;
}

// Moves the ring to another step (or none) without rebuilding the list.
export function setCurrentStep(list, key) {
  FIVE_STEPS.forEach((step, i) => {
    const li = list.children[i];
    const now = step.key === key;
    li.classList.toggle("is-now", now);
    if (now) li.setAttribute("aria-current", "step");
    else li.removeAttribute("aria-current");
  });
}
