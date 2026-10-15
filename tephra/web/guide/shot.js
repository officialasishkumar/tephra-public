// The Guide's annotated screenshots (UI-DESIGN 7.29). Each <figure class="shot" data-shot="name">
// in guide.html holds the image and its numbered legend; this module draws a numbered mark over the
// image for each entry in data/guide-shots.json and keeps the two in step: hover or focus on a mark
// lights its legend item and dims the rest, and the other way round; a click on either pins it and
// brings its partner into view. The image opens large in one <dialog>, with its own marks and legend.
// Marks are buttons; the legend's text is static markup and is never rebuilt from data.

import { el, icon } from "../wall/util.js";

const BADGE = 24; // px; the smallest tap target the badges keep at any width
const reduced = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// Each badge sits on a corner of its mark: the first corner whose badge does not cover one already
// placed, kept inside the image; a pin (a patch of an ash area) has its badge in the middle.
// Recomputed when the image changes size.
function placeBadges(stage, marks, nodes) {
  const W = stage.clientWidth;
  const H = stage.clientHeight;
  if (!W || !H) return;
  const r = BADGE / 2;
  const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);
  const placed = [];
  marks.forEach((m, i) => {
    const x0 = (m.x / 100) * W;
    const y0 = (m.y / 100) * H;
    const x1 = x0 + (m.w / 100) * W;
    const y1 = y0 + (m.h / 100) * H;
    const spots = m.pin ? [[(x0 + x1) / 2, (y0 + y1) / 2]] : [[x0, y0], [x1, y0], [x0, y1], [x1, y1]];
    const corners = spots.map(([x, y]) => [clamp(x, r, W - r), clamp(y, r, H - r)]);
    const free = corners.find(([x, y]) => placed.every(([px, py]) => Math.max(Math.abs(px - x), Math.abs(py - y)) >= BADGE + 2));
    const [bx, by] = free || corners[0];
    placed.push([bx, by]);
    nodes[i].badge.style.setProperty("--bx", `${bx - x0}px`);
    nodes[i].badge.style.setProperty("--by", `${by - y0}px`);
  });
}

// One image and one legend kept in step. Returns the size watcher, for the dialog to stop it.
function bind(figure, stage, legend, marks, titleOf) {
  let pinned = null;
  let hovered = null;
  const items = new Map([...legend.querySelectorAll(".shot__item")].map((b) => [Number(b.dataset.n), b]));
  const nodes = marks.map((m) => {
    const badge = el("span", { class: "shot__badge", "aria-hidden": "true", text: String(m.n) });
    const mark = el("button", { type: "button", class: `shot__mark${m.pin ? " shot__mark--pin" : ""}`, "aria-label": `${m.n}: ${titleOf(m.n)}`, dataset: { n: String(m.n) } }, badge);
    mark.style.left = `${m.x}%`;
    mark.style.top = `${m.y}%`;
    mark.style.width = `${m.w}%`;
    mark.style.height = `${m.h}%`;
    stage.append(mark);
    return { n: m.n, mark, badge };
  });
  const byN = new Map(nodes.map((x) => [x.n, x]));

  const show = () => {
    const on = hovered ?? pinned;
    figure.classList.toggle("has-active", on != null);
    for (const x of nodes) x.mark.classList.toggle("is-active", x.n === on);
    for (const [n, b] of items) b.classList.toggle("is-active", n === on);
  };
  const pulse = (node) => {
    node.classList.remove("is-pulse");
    if (reduced()) return;
    void node.offsetWidth;
    node.classList.add("is-pulse");
  };
  const pin = (n) => {
    pinned = pinned === n ? null : n;
    show();
  };
  const hover = (n) => { hovered = n; show(); };

  for (const x of nodes) {
    x.mark.addEventListener("pointerenter", () => hover(x.n));
    x.mark.addEventListener("pointerleave", () => hover(null));
    x.mark.addEventListener("focus", () => hover(x.n));
    x.mark.addEventListener("blur", () => hover(null));
    x.mark.addEventListener("click", (e) => {
      e.stopPropagation();
      pin(x.n);
      const item = items.get(x.n);
      if (!item || pinned == null) return;
      item.scrollIntoView({ block: "nearest", behavior: reduced() ? "auto" : "smooth" });
      pulse(item);
    });
  }
  for (const [n, b] of items) {
    if (!byN.has(n)) continue;
    b.addEventListener("pointerenter", () => hover(n));
    b.addEventListener("pointerleave", () => hover(null));
    b.addEventListener("focus", () => hover(n));
    b.addEventListener("blur", () => hover(null));
    b.addEventListener("click", () => {
      pin(n);
      if (pinned == null) return;
      const { mark } = byN.get(n);
      mark.scrollIntoView({ block: "nearest", inline: "nearest", behavior: reduced() ? "auto" : "smooth" });
      pulse(mark);
    });
  }
  const layout = () => placeBadges(stage, marks, nodes);
  const watch = new ResizeObserver(layout);
  watch.observe(stage);
  layout();
  return watch;
}

// A figure's legend titles by number, for the marks' accessible names.
const titlesOf = (legend) => {
  const t = new Map([...legend.querySelectorAll(".shot__item")].map((b) => [Number(b.dataset.n), b.querySelector("b")?.textContent || ""]));
  return (n) => t.get(n) || "";
};

function openBox(figure, marks, opener) {
  const box = document.getElementById("shot-box");
  const body = document.getElementById("shot-box-body");
  const img = figure.querySelector(".shot__img");
  const legend = figure.querySelector(".shot__legend").cloneNode(true);
  legend.removeAttribute("aria-label");
  for (const b of legend.querySelectorAll(".shot__item")) b.classList.remove("is-active", "is-pulse");
  const stage = el("div", { class: "shot__stage" }, el("img", { class: "shot__img", src: img.currentSrc || img.src, width: img.getAttribute("width"), height: img.getAttribute("height"), alt: img.alt }));
  const big = el("figure", { class: `shot shot--box${figure.classList.contains("shot--phone") ? " shot--phone" : ""}` },
    el("div", { class: "shot__pan" }, el("div", { class: "shot__frame" }, stage)), legend);
  body.replaceChildren(big);
  document.getElementById("shot-box-t").textContent = figure.closest("section")?.querySelector("h2")?.textContent || "Screenshot";
  const watch = bind(big, stage, legend, marks, titlesOf(legend));
  box.addEventListener("close", () => { watch.disconnect(); body.replaceChildren(); opener?.focus(); }, { once: true });
  box.showModal();
}

export function initShots(data) {
  const box = document.getElementById("shot-box");
  box?.addEventListener("click", (e) => {
    if (e.target === box || e.target.closest("[data-shot-close]")) box.close();
  });
  for (const figure of document.querySelectorAll("figure.shot[data-shot]")) {
    const entry = data?.[figure.dataset.shot];
    const stage = figure.querySelector(".shot__stage");
    const legend = figure.querySelector(".shot__legend");
    if (!entry || !stage || !legend) continue;
    const marks = entry.marks || [];
    bind(figure, stage, legend, marks, titlesOf(legend));
    const zoom = el("button", { type: "button", class: "shot__zoom", "aria-haspopup": "dialog", "aria-label": `Enlarge: ${figure.querySelector(".shot__img")?.alt || "screenshot"}` },
      icon("i-frame"), el("span", { class: "shot__zoom-t", "aria-hidden": "true", text: "Enlarge" }));
    stage.append(zoom);
    const open = () => openBox(figure, marks, zoom);
    zoom.addEventListener("click", open);
    stage.querySelector(".shot__img")?.addEventListener("click", open);
  }
}
