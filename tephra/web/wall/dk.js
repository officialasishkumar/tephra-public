// The Details kit (docs/UI-DETAILS-PANELS.md section 2): one small set of components that every
// Details section is built from, so the drawer reads as one designed system. Answer first (a
// header with a status pill and one sentence), then the few numbers that matter as tiles, then
// lists of rows that open one tap in; raw machine text only ever sits under "Technical detail".
// Every string goes in through el() (textContent). Sizes and colours set from code go through
// the CSSOM (CSP: no style attributes). Every disclosure carries data-k so keepOpenDetails keeps
// it open through a re-render, and every control a data-focus key so focus survives one.

import { el, icon, hhmmz, fl, compassDeg } from "./util.js";
import { techDetail } from "./x-parts.js";

// The shape and colour of each status word (UI-DESIGN 3.2): never colour alone.
export const TONE = {
  ok: ["st-ok", "var(--c-ok)"],
  caution: ["st-caution", "var(--c-caution)"],
  stale: ["st-stale", "var(--c-caution)"],
  serious: ["st-serious", "var(--c-serious)"],
  info: ["st-info", "var(--c-info)"],
  off: ["st-off", "var(--c-off)"],
  never: ["st-never", "var(--c-off)"],
  inside: ["st-inside", "var(--c-tephra)"],
  tephra: ["st-inside", "var(--c-tephra)"],
  running: ["st-info", "var(--c-observer)"],
};

export const dkDot = (tone, cls = "st dk-dot") => {
  const [id, colour] = TONE[tone] || TONE.info;
  return icon(id, cls, colour);
};

// A status pill: shape plus word, in the tone's colours.
export function dkPill(tone, text, title = null) {
  return el("span", { class: `dk-pill dk-pill--${tone}`, title }, dkDot(tone, "st"), el("span", { text }));
}

// A small muted pill for model ids, labels and kinds. Never interactive.
export function dkChip(text, { label = null, mono = false, kind = null, title = null } = {}) {
  return el("span", { class: `dk-chip${kind ? ` dk-chip--${kind}` : ""}`, title },
    label ? el("span", { class: "dk-chip__k", text: label }) : null,
    el("span", { class: mono ? "dk-chip__v mono" : "dk-chip__v", text }));
}

// REPLAY is said by the page (its title and clock), not by each record. A record keeps a tag only
// when its mode differs from what plays: a replay record seen while live feeds play says "From a replay", the
// one wording on the Wall and the Desk (desk/ui.js fromReplayChip).
export const dkFromReplay = (recordReplay, modeReplay) => (recordReplay && !modeReplay ? el("span", { class: "tag tag--replay", text: "From a replay" }) : null);

// The section header: pills, one plain sentence, an optional muted line and chips. With
// `srTitle` the sentence is for screen readers only, when the pill and the counts already say it.
export function dkHeader({ id, pills = [], title, sub = null, chips = [], extra = null, srTitle = false }) {
  const p = pills.filter(Boolean);
  const c = chips.filter(Boolean);
  return el("header", { class: "dk-head" },
    p.length ? el("div", { class: "dk-head__pills" }, ...p) : null,
    title ? el("p", { class: srTitle ? "sr-only" : "dk-head__title", id, text: title }) : null,
    sub ? el("p", { class: "dk-head__sub" }, sub) : null,
    c.length ? el("div", { class: "dk-chips" }, ...c) : null,
    extra);
}

// A thin meter (6 px). Tone by the share left: the thresholds the budget always used.
export function dkMeter({ value, max, tone = null, label }) {
  const share = max ? Math.max(0, Math.min(1, value / max)) : 0;
  const box = el("div", { class: `dk-meter dk-meter--${tone || "ok"}`, role: "meter", "aria-valuemin": "0", "aria-valuemax": String(max ?? 0), "aria-valuenow": String(value ?? 0), "aria-label": label });
  const fill = el("span", { class: "dk-meter__fill" });
  fill.style.width = `${(share * 100).toFixed(1)}%`;
  box.append(fill);
  return box;
}
export const meterTone = (left, stub = false) => (stub ? "off" : left < 0.15 ? "serious" : left < 0.4 ? "caution" : "ok");

// Number tiles. A tile with `go` is a button (data-act and friends), the rest are plain.
// The grid takes its columns from the count (wall.css), so a fourth tile never sits alone.
export function dkTiles(tiles, label) {
  const list = tiles.filter(Boolean);
  const n = list.filter((t) => !t.wide).length;
  return el("ul", { class: `dk-tiles dk-tiles--n${Math.min(n, 6)}`, "aria-label": label },
    ...list.map((t) => {
      const inner = [
        el("span", { class: "dk-tile__label", text: t.label }),
        el("span", { class: "dk-tile__value" }, t.tone && t.tone !== "plain" ? dkDot(t.tone, "st") : null, el("span", { text: t.value }), t.of ? el("span", { class: "dk-tile__of", text: t.of }) : null),
        t.meter ? dkMeter(t.meter) : null,
        t.sub ? el("span", { class: "dk-tile__sub", text: t.sub }) : null,
      ];
      const cls = `dk-tile${t.tone ? ` dk-tile--${t.tone}` : ""}`;
      const body = t.go ? el("button", { type: "button", class: `${cls} dk-tile--go`, dataset: t.go }, ...inner) : el("div", { class: cls }, ...inner);
      return el("li", { class: t.wide ? "dk-tiles__wide" : null }, body);
    }));
}

// A group: a sentence-case label with an optional aside, then its content.
export function dkGroup(title, aside, ...kids) {
  return el("section", { class: "dk-group" },
    el("div", { class: "dk-group__head" }, el("h3", { class: "dk-group__title", text: title }), aside ? el("span", { class: "dk-group__aside", text: aside }) : null),
    ...kids);
}

// One row. With a body it is a <details> whose summary carries the dot, title, sub line, meta
// and a chevron; without one it is a plain row with no chevron (it never looks tappable when it
// is not). `tone` colours the edge for attention rows.
export function dkRow({ key, dot = null, title, titleMono = false, sub = null, foot = null, meta = null, badge = null, body = null, open = false, edge = null, cls = null }) {
  const head = [
    el("span", { class: "dk-row__dot" }, dot ? (dot instanceof Node ? dot : dkDot(dot)) : null),
    el("span", { class: "dk-row__main" },
      el("span", { class: `dk-row__title${titleMono ? " mono" : ""}` }, title, badge ? [" ", el("span", { class: `dk-badge${dot === "serious" ? " dk-badge--serious" : ""}`, text: badge })] : null),
      sub ? el("span", { class: "dk-row__sub" }, sub) : null,
      foot ? el("span", { class: "dk-row__foot" }, foot) : null),
    meta != null ? el("span", { class: "dk-row__meta" }, meta) : el("span"),
  ];
  const c = `dk-row${edge ? ` dk-row--${edge}` : ""}${cls ? ` ${cls}` : ""}`;
  const kids = [body].flat().filter(Boolean);
  if (!kids.length) return el("div", { class: `${c} dk-row--flat` }, el("div", { class: "dk-row__head" }, ...head));
  const d = el("details", { class: c, dataset: { k: key } },
    el("summary", { class: "dk-row__head", dataset: { focus: `dk-${key}` } }, ...head, icon("i-chevron-right", "icon dk-row__chev")),
    el("div", { class: "dk-row__body" }, ...kids));
  if (open) d.open = true;
  return d;
}

// A row that navigates (a flight, a section): a button with a "›".
export function dkLinkRow({ dot = null, title, sub = null, meta = null, dataset, label = null, cls = null }) {
  return el("button", { type: "button", class: `dk-row dk-row--link${cls ? ` ${cls}` : ""}`, dataset, "aria-label": label },
    el("span", { class: "dk-row__head" },
      el("span", { class: "dk-row__dot" }, dot ? (dot instanceof Node ? dot : dkDot(dot)) : null),
      el("span", { class: "dk-row__main" }, el("span", { class: "dk-row__title" }, title), sub ? el("span", { class: "dk-row__sub" }, sub) : null),
      meta != null ? el("span", { class: "dk-row__meta" }, meta) : el("span"),
      el("span", { class: "dk-row__go", "aria-hidden": "true", text: "›" })));
}

// Rows in one rounded container; past `first` the rest sit behind "Show all N". The rows that
// open are one accordion (<details name>): opening one closes the one open before, so a list
// never unfolds into a wall of detail.
export function dkList(rows, { first = 5, key, noun = null, label = null, more = null } = {}) {
  const all = rows.filter(Boolean);
  for (const r of all) {
    const d = r instanceof HTMLDetailsElement ? r : r.firstElementChild;
    if (key && d instanceof HTMLDetailsElement && d.classList.contains("dk-row")) d.setAttribute("name", `dk-${key}`);
  }
  const box = el("div", { class: "dk-list", role: label ? "group" : null, "aria-label": label });
  if (!all.length) return box;
  box.append(...all.slice(0, first));
  const rest = all.slice(first);
  if (rest.length) {
    const word = more || `Show all ${all.length}${noun ? ` ${noun}` : ""}`;
    box.append(el("details", { class: "dk-more", dataset: { k: `more-${key}` } },
      el("summary", { dataset: { focus: `more-${key}` } }, icon("i-chevron-down", "icon dk-more__chev"),
        el("span", { class: "dk-more__closed", text: word }), el("span", { class: "dk-more__open", text: "Show fewer" })),
      el("div", { class: "dk-more__rows" }, ...rest)));
  }
  return box;
}

// Label and value pairs. Empty values are skipped, never shown as a dash.
export function dkFacts(rows, cls = null) {
  const dl = el("dl", { class: `dk-facts${cls ? ` ${cls}` : ""}` });
  for (const r of rows) {
    if (!r) continue;
    const [k, v, opt = {}] = r;
    if (v == null || v === "") continue;
    dl.append(el("div", { class: `dk-facts__row${opt.tone ? ` dk-facts__row--${opt.tone}` : ""}` },
      el("dt", { text: k }),
      el("dd", { class: opt.mono ? "mono" : null }, opt.tone ? dkDot(opt.tone, "st") : null, v instanceof Node ? v : String(v), opt.flag ? el("span", { class: "sr-only", text: ` ${opt.flag}` }) : null)));
  }
  return dl;
}

// A callout: one or two sentences with a shape. Tones info, caution, serious.
export function dkNote(tone, text, { iconId = null, action = null, role = null, cls = null } = {}) {
  const ic = iconId ? icon(iconId, "icon dk-note__icon") : dkDot(tone, "st dk-note__icon");
  return el("div", { class: `dk-note dk-note--${tone}${cls ? ` ${cls}` : ""}`, role },
    ic, el("div", { class: "dk-note__body" }, ...(Array.isArray(text) ? text : [text]).map((t) => (t instanceof Node ? t : el("p", { text: t }))), action));
}

// The quiet "How this works" disclosure for explanatory paragraphs: one per section.
export function dkAbout(summary, key, ...paras) {
  return el("details", { class: "dk-about", dataset: { k: `about-${key}` } },
    el("summary", { dataset: { focus: `about-${key}` } }, icon("i-chevron-right", "icon dk-about__chev"), el("span", { text: summary })),
    el("div", { class: "dk-about__body" }, ...paras.flat().filter(Boolean).map((p) => (p instanceof Node ? p : el("p", { text: p })))));
}

export const dkEmpty = (title, text, action = null) =>
  el("div", { class: "dk-empty" }, icon("i-info", "icon dk-empty__icon"), el("div", {}, el("p", { class: "dk-empty__title", text: title }), text ? el("p", { class: "dk-empty__text", text }) : null, action));

export const dkTech = techDetail;

// A section root: the header's sentence names the region for screen readers.
export const dkSection = (labelId, ...kids) => el("div", { class: "dk", role: "region", "aria-labelledby": labelId }, ...kids.flat().filter(Boolean));

export const dkLink = (text, dataset) => el("button", { type: "button", class: "link-btn dk-link", dataset, text });

// ------------------------------------------------------------------ the glance kit (UI-DESIGN 7.31)
// An ash area or a flight read at a glance: a kind label with its colour and the validity as a
// countdown pill on one line, the heights as a bar and big type, the movement as an arrow, the
// sources as chips, the forecast steps as a timeline, and the raw material as quiet links in a
// footer. The shapes are decoration (aria-hidden); the words beside them carry every fact.

export function dkGlance({ tone, label, labelId, until = null, lead = null, facts = [], kids = [] }) {
  const f = facts.filter(Boolean);
  return el("section", { class: `gl gl--${tone}`, "aria-labelledby": labelId },
    el("div", { class: "gl-top" }, el("h3", { class: "gl-kind", id: labelId }, el("i", { "aria-hidden": "true" }), label), until),
    lead ? el("p", { class: "gl-lead", text: lead }) : null,
    f.length ? el("div", { class: `gl-facts gl-facts--n${f.length}` }, ...f) : null,
    ...kids.flat().filter(Boolean));
}

const SCALE_FT = 60000; // the height bar's top: FL600, the same scale on every card
const share = (ft) => Math.max(0, Math.min(1, (ft || 0) / SCALE_FT));

// "SFC–FL350" in big type beside a bar that fills that band of SFC–FL600, in the area's colour.
export function dkBand(base, top, tone = "official") {
  const fill = el("span", { class: "gl-gauge__fill" });
  fill.style.bottom = `${(share(base) * 100).toFixed(1)}%`;
  fill.style.height = `${((share(top) - share(base)) * 100).toFixed(1)}%`;
  return el("div", { class: "gl-fact" },
    el("span", { class: `gl-gauge gl-gauge--${tone}`, "aria-hidden": "true" }, fill),
    el("span", { class: "gl-fact__txt" }, el("b", { class: "gl-big", text: `${fl(base)}–${fl(top)}` }), el("span", { class: "gl-k", text: "Heights" })));
}

// "moving W at 15 kt" as an arrow toward W, the direction big and the speed under it. Anything
// else (not given, not moving) is said in words, never drawn.
export function dkMove(words) {
  const m = /^moving (\S+) at (\d+) kt$/.exec(words || "");
  const deg = m ? compassDeg(m[1]) : null;
  if (deg == null) return el("div", { class: "gl-fact" }, el("span", { class: "gl-fact__txt" }, el("b", { class: "gl-mid", text: words || "not given" }), el("span", { class: "gl-k", text: "Movement" })));
  return el("div", { class: "gl-fact" },
    dkArrow(deg),
    el("span", { class: "gl-fact__txt", "aria-hidden": "true" }, el("b", { class: "gl-big", text: m[1] }), el("span", { class: "gl-k", text: `Moving · ${m[2]} kt` })),
    el("span", { class: "sr-only", text: `Movement: ${words}` }));
}

// One fact: an optional shape (a bar, a dial), the value big or medium, a small label and a sub line.
export function dkFact({ value, label, sub = null, lead = null, size = "big", tone = null }) {
  return el("div", { class: `gl-fact${tone ? ` gl-fact--${tone}` : ""}` }, lead,
    el("span", { class: "gl-fact__txt" }, el("b", { class: size === "big" ? "gl-big" : "gl-mid", text: value }), el("span", { class: "gl-k", text: label }),
      sub ? el("span", { class: "gl-k gl-k--sub", text: sub }) : null));
}

// One level on the height bar's scale, as a mark (an aircraft's level).
export function dkLevelMark(ft, tone = "aircraft") {
  const mark = el("span", { class: "gl-gauge__mark" });
  mark.style.bottom = `calc(${(share(ft) * 100).toFixed(1)}% - 2px)`;
  return el("span", { class: `gl-gauge gl-gauge--${tone}`, "aria-hidden": "true" }, mark);
}

// An arrow in a dial, pointing the way something moves (degrees true, 0 = north).
export function dkArrow(deg, cls = "") {
  const arrow = icon("i-arrow-right", "icon gl-arrow");
  arrow.style.transform = `rotate(${deg - 90}deg)`;
  return el("span", { class: `gl-dial${cls ? ` ${cls}` : ""}`, "aria-hidden": "true" }, arrow);
}

// The validity as a pill: the clock time in mono and what is left; caution in the last hour.
export function dkCountdown(validTo, now) {
  const m = Math.round((validTo - now) / 60e3);
  const left = m <= 0 ? "expiring" : m < 60 ? `${m} min left` : `${Math.floor(m / 60)} h ${m % 60} min left`;
  return el("span", { class: `gl-until${m < 60 ? " gl-until--soon" : ""}` },
    icon("i-clock", "icon"), el("b", { class: "mono", "aria-hidden": "true", text: hhmmz(validTo) }), el("span", { class: "gl-until__left", "aria-hidden": "true", text: left }),
    el("span", { class: "sr-only", text: `Valid until ${hhmmz(validTo)}, ${left}` }));
}

// Source chips: the issuing office's code in mono and the kind of report, with the kind's dot
// (official pink, observatory blue); the full name is the chip's title and its screen-reader text.
export function dkSources(list, label) {
  return el("ul", { class: "gl-srcs", "aria-label": label },
    ...list.map((s) => el("li", { class: `gl-src gl-src--${s.tone || "official"}`, title: s.full || null },
      el("i", { "aria-hidden": "true" }), el("b", { class: "mono", text: s.code }), el("span", { class: "gl-src__kind", text: s.kind }),
      s.full ? el("span", { class: "sr-only", text: `: ${s.full}` }) : null)));
}

// Forecast steps as a timeline: now, then each step's offset over its valid time.
export function dkSteps(steps, label = "Forecast steps") {
  return el("ol", { class: "gl-steps", "aria-label": label },
    el("li", { class: "gl-step gl-step--now" }, el("i", { "aria-hidden": "true" }), el("b", { text: "Now" })),
    ...steps.map(([k, t]) => el("li", { class: "gl-step" }, el("i", { "aria-hidden": "true" }), el("b", { text: k }), el("span", { class: "mono", text: hhmmz(t) }))));
}

// A small caps label over one part of a glance card.
export const dkLabel = (text) => el("p", { class: "gl-label", text });

// The quiet footer: link buttons first, Technical detail last (it opens on its own line).
export const dkFoot = (...kids) => {
  const k = kids.flat().filter(Boolean);
  return k.length ? el("div", { class: "gl-foot" }, ...k) : null;
};
export const dkQuiet = (text, dataset, { label = null, iconId = "i-raw-text" } = {}) =>
  el("button", { type: "button", class: "gl-link", dataset, "aria-label": label }, iconId ? icon(iconId, "icon") : null, el("span", { text }));

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
// "5 Sep 1036Z"
export const dayTime = (t) => (Number.isFinite(t) ? `${new Date(t).getUTCDate()} ${MON[new Date(t).getUTCMonth()]} ${hhmmz(t)}` : "");

// "1034Z–1036Z", or one time when they are the same minute.
export function timeRange(a, b) {
  const x = hhmmz(a), y = hhmmz(b);
  return x === y ? x : `${x}–${y}`;
}
// "4 times · 1031Z–1036Z" under a row's sentence.
export const dkWhen = (count, when) => (count || when ? [count ? el("span", { class: "dk-badge", text: times(count) }) : null, when ? el("span", { class: "mono", text: when }) : null] : null);
export const times = (n) => `${n} time${n === 1 ? "" : "s"}`;
export const plural = (n, one, many = `${one}s`) => `${n.toLocaleString ? n.toLocaleString("en") : n} ${n === 1 ? one : many}`;
// "785 s", "9.4 s", "320 ms"
export function seconds(msv) {
  if (!Number.isFinite(msv)) return "";
  if (msv < 1000) return `${Math.round(msv)} ms`;
  const s = msv / 1000;
  return s < 10 ? `${s.toFixed(1)} s` : `${Math.round(s).toLocaleString("en")} s`;
}

// ------------------------------------------------------------------ collapsing repeated lines (2.7)

const NUM = /\d+(?:[.,]\d+)*/g;
const FLIGHT = /\bRFA\d{3,4}\b/g;
// "1 job" and "18 jobs" are one shape: the noun after a number counts as singular (D62).
const shapeOfText = (t) => String(t).replace(FLIGHT, "RFA#").replace(/\b[0-9a-f]{10,}\b/g, "#id").replace(NUM, "#").replace(/# (\w+?)s\b/g, "# $1");

// Lines that say the same thing become one run: a run keeps every item, the count and the time
// range. Runs come newest first. `textOf` gives the plain line, `groupOf` anything that must
// also match (stage, level). The label shows varying numbers as a range and varying flights by
// name ("RFA1225, RFA1530 and 3 more"). Nothing is dropped: every item stays in `items`.
export function collapseRuns(items, { textOf, timeOf, groupOf = () => "" }) {
  const runs = new Map();
  for (const it of items) {
    const text = textOf(it);
    const k = `${groupOf(it)}|${shapeOfText(text)}`;
    let r = runs.get(k);
    if (!r) { r = { key: k, items: [], texts: [] }; runs.set(k, r); }
    r.items.push(it);
    r.texts.push(text);
  }
  const out = [...runs.values()].map((r) => {
    const ts = r.items.map(timeOf).filter(Number.isFinite);
    const first = ts.length ? Math.min(...ts) : NaN;
    const last = ts.length ? Math.max(...ts) : NaN;
    const newestText = r.texts[r.items.reduce((best, it, i) => (timeOf(it) >= timeOf(r.items[best]) ? i : best), 0)];
    const merged = r.items.length > 1 ? mergeTexts(r.texts, newestText) : { text: r.texts[0], newestOnly: false };
    return { ...r, count: r.items.length, first, last, label: merged.text, newestOnly: merged.newestOnly };
  });
  return out.sort((a, b) => (b.last || 0) - (a.last || 0));
}

// The run's sentence. One varying number becomes a range ("22–23 jobs"); varying flights are
// named ("RFA1225, RFA1530 and 3 more"). When several numbers vary, or a number sits next to a
// range dash already, a range would misread: the newest line is shown and marked as the newest.
function mergeTexts(texts, newest) {
  const flights = texts.map((t) => t.match(FLIGHT) || []);
  const nums = texts.map((t) => (t.replace(FLIGHT, "RFA#").match(NUM) || []));
  const width = Math.max(...nums.map((n) => n.length));
  const varies = [];
  for (let i = 0; i < width; i++) if (new Set(nums.map((n) => n[i])).size > 1) varies.push(i);
  const base = newest.replace(FLIGHT, "RFA#");
  let clean = varies.length <= 1;
  let i = 0;
  let out = base.replace(NUM, (m, off, whole) => {
    const k = i++;
    if (!varies.includes(k)) return m;
    if (/[–\-/]\D{0,2}$/.test(whole.slice(Math.max(0, off - 3), off)) || /^\D{0,2}[–\-/]/.test(whole.slice(off + m.length, off + m.length + 3))) clean = false;
    const col = nums.map((n) => n[k]).filter((v) => v != null);
    const vals = col.map((v) => Number(v.replace(/,/g, "")));
    const lo = Math.min(...vals), hi = Math.max(...vals);
    const prefix = /FL$/.test(whole.slice(0, off)) ? "FL" : "";
    return `${col[vals.indexOf(lo)]}–${prefix}${col[vals.indexOf(hi)]}`;
  });
  if (!clean) out = base;
  // a range counts more than one: "1–18 job" reads "1–18 jobs"
  else out = out.replace(/(\d–(?:FL)?\d+) (job|flight|item|step|time|record|report|delegation)\b(?!s)/g, "$1 $2s");
  let j = 0;
  out = out.replace(/RFA#( is| enters| was)?/g, (m, verb) => {
    const col = [...new Set(flights.map((f) => f[j]).filter(Boolean))];
    j += 1;
    if (col.length <= 1) return `${col[0] || "RFA"}${verb || ""}`;
    const names = col.length <= 3 ? `${col.slice(0, -1).join(", ")} and ${col[col.length - 1]}` : `${col.slice(0, 2).join(", ")} and ${col.length - 2} more`;
    const plur = { " is": " are", " enters": " enter", " was": " were" }[verb] || "";
    return `${names}${plur}`;
  });
  return { text: out, newestOnly: !clean };
}

// One collapsed run as a row: the merged sentence, "N times", the time range, and one tap in
// every occurrence with its own time and line, plus one Technical detail with the raw lines.
export function runRow(run, { key, tone = null, dot = null, sub = null, lineOf = null, rawOf = null, extra = null, open = false, titleOf = null }) {
  const single = run.count === 1;
  const when = Number.isFinite(run.first) ? timeRange(run.first, run.last) : "";
  const foot = [dkWhen(single ? null : run.count, when), run.newestOnly ? el("span", { text: "the newest is shown" }) : null];
  const occ = single ? [] : [dkList(run.items.slice().sort((a, b) => (b._t ?? 0) - (a._t ?? 0)).map((it) => el("div", { class: "dk-occ" },
    el("span", { class: "dk-occ__t mono", text: Number.isFinite(it._t) ? hhmmz(it._t) : "" }), el("span", { class: "dk-occ__x", text: lineOf ? lineOf(it) : "" }))), { first: 3, key: `${key}-occ` })];
  const raw = rawOf ? run.items.map(rawOf).filter(Boolean) : [];
  const body = [...occ, extra, raw.length ? dkTech(...raw) : null].flat().filter(Boolean);
  return dkRow({ key, dot: dot || tone, edge: tone === "serious" || tone === "caution" ? tone : null, title: titleOf ? titleOf(run) : run.label, sub, foot, body, open });
}
