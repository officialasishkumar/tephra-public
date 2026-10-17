// The info button (i): one short label stays on screen, the explanation sits one tap away. A real
// <button> with aria-expanded and aria-controls opens a small non-modal popover right after it in
// the DOM (the browser's top layer, so no panel, map edge or sticky header clips or offsets it);
// click, tap, Enter or Space open it, never hover alone. Esc closes it and returns focus to the
// button, as do a tap outside, focus leaving it and opening another one. The same words are a
// visually hidden span the button is described by, so a screen reader hears them on focus without
// opening it. Every string goes in through el() (textContent). The one component for the demo,
// /assistant and the Desk (desk/*.js import it); its look is info.css, loaded by both pages.

import { el, icon } from "./util.js";

let seq = 0;
const OPEN = new Set();
const supported = () => typeof HTMLElement !== "undefined" && "popover" in HTMLElement.prototype;
// a line is a string, a node or a list of them (one paragraph each line)
const lineText = (l) => (Array.isArray(l) ? l.map(lineText).join("") : l instanceof Node ? l.textContent : String(l));
const textOf = (lines) => lines.map(lineText).join(" ").replace(/\s+/g, " ").trim();

// { topic, text, label, actions, cls, face }: `text` is a string or a list of strings and nodes (a
// list becomes one line each); `label` the button's name ("About replay"; never "More info");
// `actions` optional buttons or links shown under the text (they stay reachable by Tab). With
// `face` (nodes), the button is a chip that shows them before the (i) glyph and is named by them
// (the Desk's REPLAY chip: one control, so a phone's header fits). `above`: open above the button
// when there is room, for an (i) whose explained line sits right under it (You decide).
export function infoButton({ topic, text, label = `About ${topic}`, actions = [], cls = "", face = null, above = false }) {
  const id = `info-${++seq}`;
  const lines = (Array.isArray(text) ? text : [text]).filter((x) => x != null && x !== "");
  const acts = [].concat(actions || []).filter(Boolean);
  const said = textOf(lines);
  const sr = el("span", { id: `${id}-sr`, class: "sr-only", text: said });
  const btn = el("button", { type: "button", class: "info__btn", "aria-expanded": "false", "aria-controls": id, "aria-label": label, "aria-describedby": sr.id, title: label, dataset: { info: topic } },
    face, glyph());
  if (face) {
    btn.classList.add("info__btn--chip");
    btn.removeAttribute("aria-label");
    btn.removeAttribute("title");
  }
  const pop = el("div", { id, class: "info__pop", role: "group", "aria-label": label, dataset: above ? { infoPop: topic, place: "above" } : { infoPop: topic } },
    ...lines.map((l) => el("p", { class: "info__line" }, l)),
    acts.length ? el("p", { class: "info__acts" }, ...acts) : null);
  // the text is already the button's description; only a popover with something to press is read
  if (!acts.length) pop.setAttribute("aria-hidden", "true");
  return wireInfo(el("span", { class: `info${cls ? ` ${cls}` : ""}` }, btn, sr, pop));
}

// The (i) glyph: a fragment of the page's own sprite when the page has put it in the document (the
// Desk does, so icons drawn while offline still show), else the sprite file.
function glyph() {
  const g = icon("i-info", "icon info__glyph");
  if (typeof document !== "undefined" && document.getElementById("i-info")) g.firstChild.setAttribute("href", "#i-info");
  return g;
}

// The behaviour, for a wrap built by infoButton or written in a page's HTML (the Desk's sign-in
// card, so its words are in the page before any script runs): <span class="info"> holding a
// .info__btn with aria-controls and its .info__pop (written `hidden`, so it never shows unstyled).
// `wrap.close()` closes it.
export function wireInfo(wrap) {
  const btn = wrap.querySelector(".info__btn");
  const pop = wrap.querySelector(".info__pop");
  if (!btn || !pop || wrap.dataset.wired) return wrap;
  wrap.dataset.wired = "1";
  if (!btn.title && btn.getAttribute("aria-label")) btn.title = btn.getAttribute("aria-label");
  if (supported()) {
    pop.setAttribute("popover", "auto");
    pop.hidden = false; // the popover rule hides it while closed
    btn.setAttribute("popovertarget", pop.id);
    pop.addEventListener("beforetoggle", (e) => { if (e.newState === "open") place(btn, pop); });
    pop.addEventListener("toggle", (e) => setState(btn, pop, e.newState === "open"));
  } else {
    pop.hidden = true;
    btn.addEventListener("click", (e) => { e.preventDefault(); if (pop.hidden) show(btn, pop); else hide(pop); });
  }
  // inside a <label> or a row with its own click, the (i) never ticks or opens the thing it sits
  // in: the click stops here, and a click on the popover's words does not reach a label
  btn.addEventListener("click", (e) => e.stopPropagation());
  pop.addEventListener("click", (e) => {
    if (e.target?.closest?.("a, button")) return;
    e.preventDefault();
    e.stopPropagation();
  });
  // pressing on the popover's own words keeps focus where it was (on the (i)), so the focus-out
  // rule below does not close it and Esc still has a button to return to; its links and buttons
  // take focus as usual
  pop.addEventListener("mousedown", (e) => { if (!e.target?.closest?.("a, button")) e.preventDefault(); });
  // focus moving out of it (Tab past it) closes it
  wrap.addEventListener("focusout", (e) => { if (e.relatedTarget && !wrap.contains(e.relatedTarget)) hide(pop); });
  wrap.close = () => hide(pop);
  return wrap;
}

// The popover's words, replaced in place (an open one keeps its place).
export function setInfo(wrap, text) {
  const pop = wrap.querySelector(".info__pop");
  const lines = (Array.isArray(text) ? text : [text]).filter((x) => x != null && x !== "");
  const said = textOf(lines);
  const sr = wrap.querySelector(".sr-only");
  if (sr.textContent === said) return;
  sr.textContent = said;
  const acts = pop.querySelector(".info__acts");
  pop.replaceChildren(...lines.map((l) => el("p", { class: "info__line" }, l)), ...(acts ? [acts] : []));
}

function setState(btn, pop, open) {
  btn.setAttribute("aria-expanded", String(open));
  if (open) { for (const p of [...OPEN]) if (p !== pop) hide(p); OPEN.add(pop); }
  else OPEN.delete(pop);
}

function show(btn, pop) {
  pop.hidden = false;
  place(btn, pop);
  setState(btn, pop, true);
}

export function hide(pop) {
  if (pop.matches?.(":popover-open")) pop.hidePopover();
  else if (!pop.hidden && !supported()) pop.hidden = true;
  const btn = document.querySelector(`[aria-controls="${pop.id}"]`);
  if (btn) setState(btn, pop, false);
}

// Under the button, held inside the window with a 16 px margin; above it when there is no room below
// (or first, for one that asked to be above the line it explains, when there is room there).
function place(btn, pop) {
  const vw = document.documentElement.clientWidth, vh = window.innerHeight;
  pop.style.setProperty("max-width", `${Math.min(320, vw - 32)}px`);
  const set = () => {
    const r = btn.getBoundingClientRect();
    const w = pop.offsetWidth, h = pop.offsetHeight;
    const left = Math.max(16, Math.min(r.left + r.width / 2 - 24, vw - w - 16));
    const below = r.bottom + 6;
    const roomAbove = r.top - h - 6 > 8;
    const top = (pop.dataset.place === "above" || below + h > vh - 8) && roomAbove ? r.top - h - 6 : Math.max(8, Math.min(below, vh - h - 8));
    pop.style.setProperty("left", `${Math.round(left)}px`);
    pop.style.setProperty("top", `${Math.round(top)}px`);
    pop.style.removeProperty("visibility");
  };
  // an open one moves at once; one opening is measured after the browser lays it out
  if (pop.offsetWidth) set();
  else { pop.style.setProperty("visibility", "hidden"); requestAnimationFrame(set); }
}

const openPops = () => [...OPEN].filter((p) => p.isConnected);

if (typeof window !== "undefined") {
  // Esc closes the open popover (and nothing else: the page's own Esc steps wait for the next
  // press); focus returns to its button. Keys typed inside a popover never reach the shortcuts.
  window.addEventListener("keydown", (e) => {
    const pops = openPops();
    if (e.key === "Escape" && pops.length) {
      e.preventDefault();
      e.stopPropagation();
      for (const p of pops) {
        const inside = p.contains(document.activeElement);
        hide(p);
        const btn = document.querySelector(`[aria-controls="${p.id}"]`);
        if (inside || document.activeElement === document.body) btn?.focus({ preventScroll: true });
      }
      return;
    }
    if (e.target?.closest?.(".info__pop") && !["Tab", "Enter", " "].includes(e.key)) e.stopPropagation();
  }, true);
  // a button or link inside it does its job and closes it
  document.addEventListener("click", (e) => {
    const pop = e.target?.closest?.(".info__acts")?.closest(".info__pop");
    if (pop) window.setTimeout(() => hide(pop), 0);
  });
  // a tap outside closes it (the browser does this for a popover; the fallback needs it too)
  document.addEventListener("pointerdown", (e) => {
    for (const p of openPops()) {
      const btn = document.querySelector(`[aria-controls="${p.id}"]`);
      if (!p.contains(e.target) && !btn?.contains(e.target) && !supported()) hide(p);
    }
  }, true);
  // a scroll under it moves it with its button (closed once the button scrolls away); a resize closes it
  window.addEventListener("resize", () => { for (const p of openPops()) hide(p); });
  document.addEventListener("scroll", (e) => {
    for (const p of openPops()) {
      if (e.target instanceof Node && p.contains(e.target)) continue;
      const btn = document.querySelector(`[aria-controls="${p.id}"]`);
      const r = btn?.getBoundingClientRect();
      if (!r || !r.width || r.bottom < 0 || r.top > window.innerHeight) hide(p);
      else place(btn, p);
    }
  }, true);
}
