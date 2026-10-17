// Home's picture of how TEPHRA works (owner, 17 Oct 2026: the map backdrop "looks repetitve to the
// map"). The five steps come from five-steps.js, words and icons both: the first three sit on a
// flowing path that ends at an example advisory card, where A person decides and The record live.
// One pulse runs down the path and each ring glows as it passes (home.css; nothing moves under
// reduced motion). It carries no data: the card says Example, names no flight and the Approve
// shape is not a control. The whole picture is one role="img" with a label and nothing in it is
// focusable. Every word goes in through el() / textContent.

import { el, icon } from "../wall/util.js";
import { FIVE_STEPS } from "../five-steps.js";

const SVG = "http://www.w3.org/2000/svg";
const BOX = { w: 520, h: 600 }; // the picture's own units; home.css keeps this aspect ratio
// where the path's rings sit, in BOX units; the last is A person decides, on the card's left edge
// (home.css hangs the card from it and runs it to the right edge)
const PATH_AT = { feeds: [48, 52], code: [134, 154], ai: [196, 258], desk: [220, 384] };
const PULSE_SHARE = 0.6; // of each cycle the pulse travels; the rest the card answers (home.css)

const step = (key) => FIVE_STEPS.find((s) => s.key === key);

// A cubic from each point to the next with vertical tangents: a calm S between every pair.
function curve(points) {
  const segs = [];
  for (let i = 1; i < points.length; i++) {
    const [ax, ay] = points[i - 1];
    const [bx, by] = points[i];
    const dy = (by - ay) / 2;
    segs.push([[ax, ay], [ax, ay + dy], [bx, by - dy], [bx, by]]);
  }
  return segs;
}

function bezierLength([p0, p1, p2, p3]) {
  let len = 0;
  let prev = p0;
  for (let i = 1; i <= 24; i++) {
    const t = i / 24;
    const u = 1 - t;
    const pt = [0, 1].map((k) => u * u * u * p0[k] + 3 * u * u * t * p1[k] + 3 * u * t * t * p2[k] + t * t * t * p3[k]);
    len += Math.hypot(pt[0] - prev[0], pt[1] - prev[1]);
    prev = pt;
  }
  return len;
}

function svgNode(tag, attrs) {
  const node = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  return node;
}

// Places a node at a point of BOX and tells home.css when the pulse reaches it (a share of the
// cycle). Custom properties through the CSSOM: the page's CSP refuses a style attribute.
function place(node, [x, y], share) {
  node.style.setProperty("--x", `${((x / BOX.w) * 100).toFixed(3)}%`);
  node.style.setProperty("--y", `${((y / BOX.h) * 100).toFixed(3)}%`);
  node.style.setProperty("--at", share.toFixed(4));
  return node;
}

function ring(s, cls) {
  return el("span", { class: `how__ring how__ring--${s.key}${cls ? ` ${cls}` : ""}` }, icon(s.icon));
}

function label() {
  const names = FIVE_STEPS.map((s) => s.name);
  return `Illustration of how TEPHRA works: ${names.join(", then ")}. The advisory card is an example, not real data.`;
}

export function howPicture(host) {
  const keys = Object.keys(PATH_AT);
  const segs = curve(keys.map((k) => PATH_AT[k]));
  const lengths = segs.map(bezierLength);
  const total = lengths.reduce((a, b) => a + b, 0);
  let run = 0;
  const share = { [keys[0]]: 0 };
  segs.forEach((_, i) => {
    run += lengths[i];
    share[keys[i + 1]] = (run / total) * PULSE_SHARE;
  });
  const d = segs.map(([a, b, c, e], i) => `${i ? "" : `M${a[0]} ${a[1]} `}C${b[0]} ${b[1]} ${c[0]} ${c[1]} ${e[0]} ${e[1]}`).join(" ");

  const wire = svgNode("svg", { class: "how__wire", viewBox: `0 0 ${BOX.w} ${BOX.h}`, "aria-hidden": "true", focusable: "false" });
  // the wire is neutral and dotted (an example, not a live link); only the pulse moves along it
  wire.append(svgNode("path", { class: "how__path", d }), svgNode("path", { class: "how__pulse", d, pathLength: 100 }));

  const nodes = ["feeds", "code", "ai"].map((k) =>
    place(el("span", { class: `how__n how__n--${k}` }, ring(step(k)), el("b", { class: "how__name", text: step(k).name })), PATH_AT[k], share[k]));

  const desk = step("desk");
  const record = step("record");
  const card = place(el("div", { class: "how__card" },
    el("div", { class: "how__head" },
      el("b", { class: "how__name", text: desk.name }),
      el("span", { class: "how__tag", text: "Example" })),
    el("span", { class: "how__bars" }, el("span", { class: "how__bar" }), el("span", { class: "how__bar how__bar--ash" }), el("span", { class: "how__bar" })),
    el("span", { class: "how__approve" }, icon("i-check"), el("span", { text: "Approve" })),
    el("span", { class: "how__foot" }, ring(record, "how__ring--sm"), el("span", { class: "how__name how__name--sm", text: record.name }))),
  PATH_AT.desk, share.desk);
  const deskRing = place(el("span", { class: "how__n how__n--desk" }, ring(desk)), PATH_AT.desk, share.desk);

  host.setAttribute("role", "img");
  host.setAttribute("aria-label", label());
  host.replaceChildren(wire, ...nodes, card, deskRing);
  return host;
}
