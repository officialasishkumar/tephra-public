// Small building blocks shared by the Wall's rail panels (ext.js, duty.js). Every string goes in
// through el() (textContent); AI-written text carries an "AI-written" mark with the model id.

import { el, icon } from "./util.js";

export const st = (id, color) => icon(id, "st", color);

// Marks AI-written text with the model id; the stub says NO MODEL.
export function aiMark(modelId, label) {
  const no = label === "NO MODEL" || !modelId || modelId === "stub";
  return el("span", { class: `ai-mark${no ? " ai-mark--none" : ""}`, title: no ? "No model wrote this: the offline stub" : "Written by a model. Code checked every number, time and id." },
    icon("i-model"), el("span", { text: no ? "NO MODEL" : `AI-written · ${modelId}` }));
}

export function pill(kind, text, title) {
  const ic = { ok: "st-ok", caution: "st-caution", serious: "st-serious", info: "st-info", off: "st-off" }[kind] || "st-info";
  const col = { ok: "var(--c-ok)", caution: "var(--c-caution)", serious: "var(--c-serious)", info: "var(--c-info)", off: "var(--c-off)" }[kind];
  return el("span", { class: `pill pill--${kind}`, title }, st(ic, col), el("span", { text }));
}

export const section = (title, ...kids) => el("section", { class: "x-sec" }, el("h3", { class: "caps x-sec__title", text: title }), ...kids);
