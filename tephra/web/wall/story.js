// The story column (docs/UI-REDESIGN.md R3.2, R5): the failure line, the story card, the map key,
// the trust line, the story notes and the "All volcanoes" line. Every sentence is built by code
// from fields and goes in with textContent; a missing field drops its line and is never guessed.
// The story is about the selected volcano; the "All volcanoes" line carries the global counts.

import { $, el, icon, hhmmz, ms, fl, kmBetween, reducedMotion } from "./util.js";
import { SEV_RANK, regionOfVent } from "./derive.js";
import { ext, replanning, aiState, handPlan } from "./ext.js";
import { planFailure, draftBlock, machineText } from "./x-parts.js";
import { FEED_NAME } from "./panels.js";

const CODE_WORD = { RED: "Red", ORANGE: "Orange", YELLOW: "Yellow", GREEN: "Green" };
const codeColor = (code) => `var(--c-code-${(code || "UNKNOWN").toLowerCase()})`;
const eruptIcon = (code, cls = "icon erupt") => icon("i-eruption", cls, codeColor(code));
const st = (id, color) => icon(id, "st", color);
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const ft = (n) => `${Number(n).toLocaleString("en")}`;
const setText = (node, text) => { if (node && node.textContent !== text) node.textContent = text; };

// Rows of the "All volcanoes" list shown before "+ n more", by width (R5.7); the fit pass below
// may lower it to 0 when the column is short.
let fitCap = Infinity;
const listRows = () => Math.min(fitCap, window.innerWidth <= 600 ? Infinity : window.innerWidth >= 1600 ? 3 : window.innerWidth >= 1360 ? 2 : 1);

// ------------------------------------------------------------------ facts shared with Details

// The current (not superseded) recovery plan, newest first.
export function currentPlan() {
  const plans = ext.recovery.slice().sort((a, b) => ms(b.created_at) - ms(a.created_at));
  return plans.find((p) => p.status !== "SUPERSEDED") || null;
}

// Airports the current plan closes because of this volcano: a closure belongs to a volcano when
// one of its source ids is that volcano's official product or TEPHRA cone (R5.3 L3).
export function closuresFor(D, vid, plan = currentPlan()) {
  if (!plan || !vid) return [];
  const ids = new Set();
  for (const f of D.official) if (f.properties.volcano_id === vid) ids.add(f.properties.source_id);
  for (const f of D.cones) if (f.properties.volcano_id === vid && f.properties.cone_id) ids.add(f.properties.cone_id);
  return plan.closures.filter((c) => (c.source_ids || []).some((s) => ids.has(s)));
}

// The selected volcano's advisories (R5.3 L5). The Wall loads the newest 50; when that page is
// full and holds fewer drafts than the server counts, the count says "at least".
export function advisoryFacts(D, store, vid) {
  const mine = store.advisories.filter((a) => a.volcano_id === vid && a.status !== "SUPERSEDED");
  const drafts = mine.filter((a) => a.status === "DRAFT");
  const approved = mine.filter((a) => a.status === "APPROVED" || a.status === "EDITED").length;
  const rejected = mine.filter((a) => a.status === "REJECTED").length;
  const allDrafts = store.advisories.filter((a) => a.status === "DRAFT").length;
  const partial = store.advisories.length >= 50 && D.state.draft_count != null && allDrafts < D.state.draft_count;
  // Most urgent first, in the Desk's order (desk/format.js byUrgency): inside now, then the
  // soonest entry on the clock (drafted time + minutes to entry), then the oldest draft. The Desk
  // opens this draft as its Next decision (review 2, item 6).
  const entryAt = (a) => ms(a.created_at) + (a.inside_now ? 0 : Math.max(0, a.minutes_to_entry || 0) * 60000);
  const urgent = drafts.slice().sort((a, b) => Number(!!b.inside_now) - Number(!!a.inside_now) || entryAt(a) - entryAt(b) || ms(a.created_at) - ms(b.created_at))[0] || null;
  return { drafts: drafts.length, approved, rejected, decided: approved + rejected, partial, urgent, unknown: D.state.draft_count === null };
}

// Official areas valid now for a volcano: the highest top and its base (R5.3 L1).
function officialBand(D, vid) {
  const feats = D.official.filter((f) => f.properties.volcano_id === vid && f.properties.valid && f.properties.step === "now");
  if (!feats.length) return null;
  const top = Math.max(...feats.map((f) => f.properties.top_ft));
  const highest = feats.filter((f) => f.properties.top_ft === top);
  const base = Math.min(...highest.map((f) => f.properties.base_ft));
  return { top, base };
}

const adsbWord = (status) => ({ ERROR: "failing", STALE: "stale", DISABLED: "off", NEVER: "not read yet" }[status] || "not working");

// ------------------------------------------------------------------ failures (R5.6)

// Every problem that threatens the picture, worst first, in plain words (R5.6): the connection,
// the page, the map, the feeds and the database. AI steps are not here: what their absence
// changes is said at the place it applies, and their health in the AI chip (docs/UI-AI-QUIET.md
// Q3, Q4). `who` is the part that failed, set in bold; `raw` is the machine text the plain words
// came from, kept in the item's title and, one tap in, under Technical detail in Details.
// `where` names the Details section that holds it.
export function storyFailures(D, store, conn, extra) {
  const out = [];
  if (conn.lostAt) out.push({ key: "stream", text: `Lost the live connection at ${hhmmz(conn.lostAt)}. Reconnecting…`, where: "feeds", lost: true });
  if (extra.error) out.push({ key: "load", text: extra.error, where: "feeds", action: "retry", actionText: "Retry now" });
  if (extra.mapError) out.push({ key: "map", text: `The map could not load: ${extra.mapError}.`, where: "layers" });
  if (!D) return out;
  for (const id of ["adsb", "sigmet", "vaac_darwin", "vaac_tokyo", "vona"]) {
    const f = store.feeds.find((x) => x.feed === id);
    if (!f || f.status !== "ERROR") continue;
    const good = ms(f.last_success_at);
    const what = id === "adsb" ? "positions" : "reports";
    const name = id === "adsb" ? "Aircraft data" : FEED_NAME[id] || id;
    out.push({ key: `feed-${id}`, who: name, text: `${name} is failing. Showing the last good ${what}${Number.isFinite(good) ? `, from ${hhmmz(good)}` : ""}.`, raw: f.last_error || null, where: "feeds" });
  }
  if (D.state.store && D.state.store.ok === false) out.push({ key: "db", who: "The database", text: "The database is failing: some counts may be unknown.", where: "feeds" });
  // airport re-planning that code could not run (no schedule, an exception): data, not AI
  const rec = (store.trace || []).filter((t) => t.stage === "RECOVERY");
  const lastRec = rec[rec.length - 1];
  if (lastRec && lastRec.level === "error" && lastRec.actor === "system") {
    const text = /^No RFA schedule: /.test(lastRec.message) ? "Airport re-planning cannot run: the RFA schedule could not be read." : "Airport re-planning stopped with an error.";
    out.push({ key: "recovery-data", who: "Airport re-planning", text, raw: lastRec.message, where: "recovery" });
  }
  return out;
}

const seenFailures = new Set();

function renderFailures(list) {
  const box = $("fail-line");
  const lost = $("lost-banner");
  const items = list.filter((f) => !f.lost);
  const lostItem = list.find((f) => f.lost);
  // #lost-banner keeps role=alert; it is written only when its words change.
  lost.hidden = !lostItem;
  if (lostItem) setText(lost, lostItem.text);
  const shown = items.slice(0, lostItem ? 1 : 2);
  const more = items.length - shown.length;
  const key = [...shown.map((f) => `${f.key}:${f.text}:${f.raw || ""}`), more].join("|");
  const ul = $("fail-list");
  if (ul.dataset.key !== key) {
    ul.dataset.key = key;
    // "+ n more problems ›" runs on at the end of the last item's words, so it never takes a line
    // of its own
    const moreBtn = more > 0 ? el("button", { type: "button", class: "link-btn fail-line__more", dataset: { act: "details-open", sec: items[shown.length].where, focus: "fail-more" }, text: `+ ${plural(more, "more problem", "more problems")} ›` }) : null;
    ul.replaceChildren(...shown.map((f, i) => {
      // role=alert only on the render where the failure first appears (R15.6)
      const fresh = !seenFailures.has(f.key);
      seenFailures.add(f.key);
      // the part that failed in bold, the rest in plain words; the machine text in the words'
      // tooltip, never on the item, where it would become the item's (and the alert's) name
      const title = f.raw ? `Recorded reason: ${machineText(f.raw)}` : null;
      const words = f.who && f.text.startsWith(f.who)
        ? el("span", { class: "fail-line__text", title }, el("strong", { class: "fail-line__who", text: f.who }), f.text.slice(f.who.length))
        : el("span", { class: "fail-line__text", title, text: f.text });
      const last = i === shown.length - 1 && moreBtn;
      return el("li", { class: "fail-line__item", role: fresh ? "alert" : null },
        st("st-serious", "var(--c-serious)"), el("span", { class: "fail-line__body" }, words, last ? [" ", moreBtn] : null),
        f.action ? el("button", { type: "button", class: "link-btn", dataset: { act: f.action, focus: `fail-${f.key}` }, text: f.actionText }) : null);
    }));
  }
  box.hidden = !list.length;
}

// ------------------------------------------------------------------ the story card (R5.1-R5.4)

// Eyebrow (R5.1): the eruption symbol and the volcano's name (the h1) on the first row with "as of"
// on its right; under them, muted, the area, the alert colour as a pill in words and, in REPLAY,
// the "Recorded" tag, so a frame of the story alone says it is a recording.
function eyebrow(D, sit, region, store) {
  const iconBox = $("eyebrow-icon");
  const rest = $("eyebrow-rest");
  const replay = D?.mode === "REPLAY";
  const asof = $("eyebrow-asof");
  asof.title = "Times ending in Z are UTC";
  if (!sit) {
    iconBox.replaceChildren();
    const k = replay ? "replay" : "";
    if (rest.dataset.key !== k) { rest.dataset.key = k; rest.replaceChildren(...(replay ? [el("span", { class: "tag tag--replay eyebrow__rec", text: "Recorded" })] : [])); }
    setText(asof, D ? `as of ${hhmmz(D.now)}` : "");
    return;
  }
  iconBox.replaceChildren(eruptIcon(sit.color_code));
  const regName = region ? (D.state.regions || []).find((r) => r.key === region)?.name : null;
  const code = CODE_WORD[sit.color_code] ? sit.color_code.toLowerCase() : "unknown";
  const alert = CODE_WORD[sit.color_code] ? `${CODE_WORD[sit.color_code]} alert` : "Alert colour not given";
  const k = [regName, alert, replay].join("|");
  if (rest.dataset.key !== k) {
    rest.dataset.key = k;
    rest.replaceChildren(...[
      regName ? el("span", { class: "eyebrow__region", text: regName }) : null,
      el("span", { class: `code-pill code-pill--${code}`, title: "The volcano's aviation colour code" }, el("span", { class: "code-pill__dot", "aria-hidden": "true" }), el("span", { text: alert })),
      replay ? el("span", { class: "tag tag--replay eyebrow__rec", text: "Recorded" }) : null].filter(Boolean));
  }
  setText(asof, `as of ${hhmmz(ms(sit.as_of))}`);
}

// The story of one volcano (docs/UI-DESIGN.md 7.6, redesigned 13 Oct 2026), as one model built by
// code from fields: a hero (the flights, the one number a dispatcher asks first), up to three fact
// tiles (the ash's height, the airports it closes, the advisories), one notice when the AI's
// absence or a missing airport plan changes the dispatcher's work, and the lines about sources
// that disagree and crew reports. Every fact a sentence used to carry is in a tile's words, its
// title or one tap in, in Details. `text` fields are the words for the change key and the
// announcement.
function storyModel(D, store, sit) {
  const m = { banner: null, hero: null, facts: [], notice: null, lines: [] };
  const cone = D.coneOf(sit.volcano_id)?.properties;
  const stub = D.state.llm?.backend === "stub";
  const ai = aiState(D, store);
  const hand = handPlan(D, store, ai);
  const handHere = hand.flights.filter((x) => x.p.volcano_id === sit.volcano_id).length;
  if (cone?.mode === "HYPOTHESIS") m.banner = "HYPOTHESIS: no valid official product. Only MONITOR or HOLD may be advised.";

  // the hero: the flights in or heading into TEPHRA's area, inside now against heading in
  const n = sit.exposed_count || 0;
  if (n > 0) {
    const mine = D.exposed.filter((f) => f.properties.volcano_id === sit.volcano_id);
    const inside = mine.filter((f) => f.properties.inside).length;
    const split = mine.length === n ? [inside ? `${inside} inside now` : null, n - inside ? `${n - inside} heading in` : null].filter(Boolean).join(" · ") : null;
    m.hero = { count: n, words: `RFA ${n === 1 ? "flight" : "flights"} in or heading into TEPHRA's ash area`, split, show: mine.length, text: `${n} RFA ${n === 1 ? "flight" : "flights"} in or heading into TEPHRA's ash area${split ? `. ${split}` : ""}.` };
  } else {
    const adsb = store.feeds.find((f) => f.feed === "adsb");
    const empty = adsb?.status === "OK" ? "Aircraft coverage here is patchy: an empty map is not an empty sky." : `Aircraft data is ${adsbWord(adsb?.status)}: an empty map is not an empty sky.`;
    m.hero = { count: null, words: "No RFA flight is seen heading into TEPHRA's ash area right now.", split: empty, text: "No RFA flight is seen heading into TEPHRA's ash area right now." };
  }

  // tile 1: the ash's height in the official reports
  if (cone?.mode !== "HYPOTHESIS") {
    const b = officialBand(D, sit.volcano_id);
    if (b) {
      const sentence = b.base > 0 ? `Official reports put the ash between ${ft(b.base)} and ${ft(b.top)} ft (${fl(b.base)}–${fl(b.top)}).` : `Official reports put the ash up to ${ft(b.top)} ft (${fl(b.top)}).`;
      m.facts.push({ key: "ash", label: b.base > 0 ? "Ash between" : "Ash up to", value: b.base > 0 ? `${fl(b.base)}–${fl(b.top)}` : fl(b.top), sub: b.base > 0 ? `${ft(b.base)}–${ft(b.top)} ft` : `${ft(b.top)} ft`, title: sentence, act: "sources", text: sentence });
    }
  }

  // tile 2: the RFA airports the ash closes (the airport plan covers the whole network)
  const plan = currentPlan();
  const closed = closuresFor(D, sit.volcano_id, plan);
  const re = replanning(store);
  const pf = plan?.closures.length ? planFailure(plan) : null;
  if (re) {
    // the trace does not say which volcano closed them: the scope is every volcano (review 2, item 2)
    m.facts.push({ key: "airports", label: "Airports closed", value: String(re.airports.length), sub: "re-planning the day…", busy: true, title: `Ash closes ${plural(re.airports.length, "RFA airport", "RFA airports")}, all volcanoes: ${re.airports.join(", ")}. Re-planning the day's flights, started ${hhmmz(re.at)}.`, act: "recovery", text: `${re.airports.length} RFA airports closed, re-planning` });
  } else if (closed.length || pf) {
    const here = [...new Set(closed.map((c) => c.icao))];
    const all = [...new Set(plan.closures.map((c) => c.icao))];
    const list = here.length ? here : all;
    const scope = here.length ? (all.length > here.length ? ` (${all.length} across all volcanoes)` : "") : " across the network";
    m.facts.push({ key: "airports", label: "Airports closed", value: String(list.length), sub: list.join(" · "),
      tone: pf ? "caution" : null, title: `Ash ${here.length ? `from ${sit.volcano_name} ` : ""}closes ${plural(list.length, "RFA airport", "RFA airports")}${scope}: ${list.join(", ")}. ${pf ? pf.place : `Airport plan as of ${hhmmz(ms(plan.created_at))}`}.`, act: "recovery", text: `${list.length} RFA airports closed${scope}` });
  }

  // tile 3: the advisories for this volcano's flights
  const a = advisoryFacts(D, store, sit.volcano_id);
  if (n > 0 || a.drafts || a.decided || a.unknown) {
    let fact;
    if (a.unknown) fact = { value: "?", label: "Advisories", sub: "unknown (database error)", tone: "serious" };
    else if (a.drafts > 0) {
      // drafts whose flight is not among the n seen heading in now, said so 30 next to 23 adds up
      const seen = new Set(D.exposed.filter((f) => f.properties.volcano_id === sit.volcano_id).map((f) => `${f.properties.hex}:${sit.volcano_id}`));
      const gone = store.advisories.filter((x) => x.volcano_id === sit.volcano_id && x.status === "DRAFT" && !seen.has(x.flight_id)).length;
      fact = { value: `${a.partial ? "≥" : ""}${a.drafts}`, label: "Advisories", sub: gone > 0 && !a.partial ? `to decide, ${gone} for flights gone` : "to decide", title: `${a.partial ? "At least " : ""}${plural(a.drafts, "advisory waits", "advisories wait")} for a dispatcher.${gone > 0 && !a.partial ? ` ${gone} of them ${gone === 1 ? "is for a flight" : "are for flights"} no longer seen heading in.` : ""}` };
    } else if (a.decided > 0) fact = { value: String(a.decided), label: "Advisories", sub: `decided · ${a.approved} approved, ${a.rejected} rejected` };
    else fact = { value: "0", label: "Advisories", sub: "drafted" };
    m.facts.push({ key: "advisories", ...fact, act: "decisions", title: fact.title || `Advisories: ${fact.value} ${fact.sub}.`, text: fact.title || `${fact.value} advisories ${fact.sub}.` });
  }

  // one notice: what the dispatcher must now do by hand, and why, said once (UI-AI-QUIET Q3)
  const block = hand.block || draftBlock(ai);
  const draftsGap = n > 0 && !a.drafts && !a.decided && !a.unknown && block && ((handHere && !block.undone) || block.word === "AI waiting");
  const undone = hand.block?.undone && handHere;
  if (draftsGap || undone || pf) {
    const nf = plural(handHere, "flight", "flights");
    const parts = [];
    const noDrafts = draftsGap && block.word !== "AI waiting";
    if (undone) parts.push(`The Duty Officer left ${handHere} must-do ${handHere === 1 ? "flight" : "flights"} for the Desk.`);
    else if (draftsGap && !noDrafts) parts.push("Advisories are not drafted yet.");
    // the missing pieces in one sentence when the same AI stop explains both
    if (noDrafts && pf?.ai) parts.push("No advisory drafts and no airport plan.");
    else {
      if (noDrafts) parts.push("No advisory drafts.");
      if (pf) parts.push(pf.ai ? "No airport plan." : `No airport plan: ${pf.place.replace(/^No airport plan \((.+)\): plan the network by hand$/, "$1")}.`);
    }
    const todo = [noDrafts || undone ? (handHere === 1 ? "the flight" : `the ${nf}`) : null, pf ? "the network" : null].filter(Boolean);
    if (todo.length) parts.push(`Plan ${todo.join(" and ")} by hand on the Desk.`);
    const aiCause = draftsGap || undone || pf?.ai;
    const title = draftsGap && block.word === "AI paused" ? `AI paused${block.until ? ` ${block.until}` : ""}`
      : draftsGap && block.word === "AI unavailable" ? `AI unavailable (${block.why})`
        : draftsGap && block.word === "AI waiting" ? `Waiting for AI${block.slot ? `, next slot ${block.slot}` : ""}`
          : undone ? "Must-do flights left for the Desk"
            : pf?.ai ? `AI unavailable (${pf.why})` : "No airport plan";
    m.notice = { title, body: parts.join(" "), why: aiCause ? { act: "ai", text: "Why ›", label: "Why: open AI helpers" } : { act: "recovery", text: "Airport closures ›", label: "Open Airport closures" },
      raw: pf ? pf.raw : null, text: `${title}. ${parts.join(" ")}` };
  }

  // sources that disagree: TEPHRA's reason to exist, so they stay in the story, one line each
  const dir = sit.discrepancies.find((d) => d.kind === "DIRECTION_MISMATCH" && d.aspect === "direction" && (SEV_RANK[d.severity] || 0) >= 2);
  if (dir) {
    let tail = null;
    if (cone?.mode === "WIDENED") tail = "TEPHRA's estimate covers both.";
    else if (cone?.mode === "OFFICIAL") {
      const outcome = sit.assessment?.outcome;
      tail = stub || outcome === "STUB" ? "TEPHRA's estimate has not been widened (AI off)."
        : outcome === "PENDING" ? "TEPHRA's estimate has not been widened yet (AI waiting)."
          : outcome === "MODEL_FAILED" ? "TEPHRA's estimate has not been widened (AI unavailable)." : "TEPHRA's estimate has not been widened.";
    }
    m.lines.push({ text: `The sources disagree on where the ash is heading, ${Math.round(dir.magnitude)}° apart.`, sub: tail, mark: "disagree", act: "disagree" });
  }
  if (sit.discrepancies.some((d) => d.kind === "SILENCE")) m.lines.push({ text: "Ash was reported and no VAA has followed.", mark: "disagree", act: "disagree" });
  if (sit.discrepancies.some((d) => d.kind === "CONFLICT")) m.lines.push({ text: "A no-ash VAA was in force when another report saw ash after it.", mark: "disagree", act: "disagree" });
  m.lines.push(...crewLines(D, sit));
  return m;
}

// Crew reports of ash (UI-DESIGN 7.6, 7.20): one line at most, for this volcano's active crew
// areas (a report near no active volcano: the all-volcanoes story, and a row in the volcano
// list). A covered area adds nothing the official lines do not already say, so it has no line.
// The line opens Details › Crew reports. A crew area is an operator-policy flag: its line never
// changes the official or TEPHRA lines.
export function crewLines(D, sit) {
  const C = D.crew;
  const mine = C.drawn.filter((v) => v.state === "ACTIVE" && (sit ? v.report.volcano_id === sit.volcano_id : C.homeless(v)));
  if (!mine.length) return [];
  const ids = new Set(mine.map((v) => v.report.id));
  const flagged = C.flags.filter((f) => f.report_ids.some((id) => ids.has(id)));
  const outside = mine.some((v) => v.discrepancy);
  const what = `${mine.length === 1 ? "Crew report" : `${mine.length} crew reports`} of ash${outside ? " outside the official area" : ""}`;
  // the flight numbers are one tap away (the line opens Details), so the line stays short
  const text = flagged.length ? `${what}: ${plural(flagged.length, "RFA flight", "RFA flights")} on ${mine.length === 1 ? "its" : "their"} route.` : `${what}, ${mine[0].age_text}.`;
  return [{ text, mark: outside ? "caution" : "pin", act: "crew" }];
}

let lastAnnounce = { at: 0, key: "" };

// A button that opens a Details section. Its visible words are its name (WCAG 2.5.3); `title`
// carries the full sentence for a pointer.
const openBtn = (act, cls, title, ...kids) => el("button", { type: "button", class: cls, title, dataset: { act: "details-open", sec: act, focus: `story-${cls.split(" ")[0]}-${act}` } }, ...kids);

// The trust note (R5.7, docs/UI-AI-QUIET.md W17): one sentence that holds in every AI state, one
// tap from "TEPHRA's ash area" in the hero; the map key's TEPHRA row says it on screen.
const TRUST = "TEPHRA's estimate is never smaller than the official area, which stays binding. AI can widen it, never shrink it.";
const trustNode = (open) => el("p", { id: "trust", class: "trust", hidden: !open }, icon("i-info", "icon trust__icon"),
  el("span", { class: "trust__body" }, el("span", { class: "trust__text", text: TRUST }),
    el("button", { type: "button", class: "link-btn trust__more", dataset: { act: "details-open", sec: "estimate", focus: "trust-more" }, text: "How TEPHRA built it ›" })));

// The hero: the number in TEPHRA amber, what it counts, and the split with "Show them".
function heroNode(h, ui) {
  const words = el("p", { class: "hero__words" }, h.words.replace(/TEPHRA's ash area$/, ""),
    h.count != null ? el("span", { class: "hero__area" }, "TEPHRA's ash area",
      el("button", { type: "button", class: "hero__info", "aria-expanded": ui.trustOpen ? "true" : "false", "aria-controls": "trust", "aria-label": "What is TEPHRA's ash area?", title: "What is TEPHRA's ash area?", dataset: { act: "trust-toggle", focus: "trust-toggle" } }, icon("i-info"))) : null);
  return el("div", { class: `hero${h.count == null ? " hero--none" : ""}` },
    h.count != null ? el("p", { class: "hero__num", "aria-hidden": "true", text: String(h.count) }) : null,
    el("div", { class: "hero__text" },
      h.count != null ? el("span", { class: "sr-only", text: `${h.count} ` }) : null,
      words,
      h.split ? el("p", { class: "hero__split" }, el("span", { text: h.split }),
        h.show ? [el("span", { class: "hero__dot", "aria-hidden": "true", text: " · " }), openBtn("flights", "link-btn hero__show", `Show the ${plural(h.show, "flight", "flights")} in Details`, h.show === 1 ? "Show it" : "Show them")] : null) : null),
    h.count != null ? trustNode(!!ui.trustOpen) : null);
}

function factNode(f) {
  return el("li", { class: `fact${f.tone ? ` fact--${f.tone}` : ""}` },
    openBtn(f.act, "fact__btn", f.title,
      el("span", { class: "fact__label", text: f.label }),
      el("span", { class: "fact__value" }, f.busy ? el("span", { class: "spinner", "aria-hidden": "true" }) : f.tone ? st(`st-${f.tone}`, `var(--c-${f.tone})`) : null, f.value),
      f.sub ? el("span", { class: "fact__sub", text: f.sub }) : null));
}

function noticeNode(nt) {
  // not a live region: in REPLAY its time left changes each minute; #announce speaks the change
  return el("div", { class: "notice" },
    icon("st-caution", "st notice__icon"),
    el("div", { class: "notice__body" },
      el("p", { class: "notice__title", text: nt.title }),
      el("p", { class: "notice__text", title: nt.raw ? `Recorded reason: ${nt.raw}` : null }, nt.body, " ",
        el("button", { type: "button", class: "link-btn notice__why", "aria-label": nt.why.label, dataset: { act: "details-open", sec: nt.why.act, focus: "story-why" }, text: nt.why.text }))));
}

function lineNode(l) {
  const mark = l.mark === "pin" ? icon("i-pin", "icon story__mark story__mark--crew") : l.mark === "disagree" ? icon("i-compare-sources", "icon story__mark story__mark--disagree") : st("st-caution", "var(--c-caution)");
  return el("li", {}, el("button", { type: "button", class: "sline", dataset: { act: "details-open", sec: l.act, focus: `story-line-${l.act}` } },
    mark, el("span", { class: "sline__text" }, el("span", { text: l.text }), l.sub ? el("span", { class: "sline__sub", text: l.sub }) : null),
    el("span", { class: "sline__go", "aria-hidden": "true", text: "›" })));
}

const modelKey = (m) => JSON.stringify([m.banner, m.hero, m.facts.map((f) => [f.label, f.value, f.sub, f.tone, f.title]), m.notice && [m.notice.title, m.notice.body], m.lines]);

function renderLines(D, store, ui, sit, announce) {
  const box = $("headline");
  let kids = [], key = "", text = "", count = "";
  if (!D) key = "";
  else if (sit) {
    const m = storyModel(D, store, sit);
    key = `${modelKey(m)}|${ui.trustOpen ? 1 : 0}`;
    // the notice's body, not its title: the time left in REPLAY must not make it speak each minute
    text = [m.hero.text, m.facts.find((f) => f.key === "advisories")?.text, m.notice?.body].filter(Boolean).join(" ");
    count = String(m.hero.count ?? "");
    if (box.dataset.key !== key) {
      kids = [
        m.banner ? el("p", { class: "story__hyp", role: "note" }, st("st-caution", "var(--c-caution)"), el("span", { text: m.banner })) : null,
        heroNode(m.hero, ui),
        m.facts.length ? el("ul", { class: `facts facts--${m.facts.length}`, "aria-label": "Key facts" }, ...m.facts.map(factNode)) : null,
        m.notice ? noticeNode(m.notice) : null,
        m.lines.length ? el("ul", { class: "slines", "aria-label": "Also here" }, ...m.lines.map(lineNode)) : null,
      ].filter(Boolean);
    }
  } else {
    let lead, note = null;
    if (D.reading) {
      // active volcanoes are known but their situation cards have not arrived: never "no ash"
      lead = "Reading the official reports…";
      note = D.state.last_tick ? "Ash is reported here. The summary appears when TEPHRA has read the reports, usually within a minute." : "TEPHRA has just started and is reading every feed for the first time. This takes up to a minute.";
    } else if (D.regionEmpty) lead = `No ash reported near ${D.area?.name || "this area"} right now.`;
    else lead = "No official ash report is in force in the watched regions right now.";
    const crew = crewLines(D, null);
    key = [lead, note, ...crew.map((l) => l.text)].join("|");
    if (box.dataset.key !== key) {
      kids = [el("p", { class: `hero__words hero__words--alone${D.reading ? " story__connecting" : ""}`, text: lead }), note ? el("p", { class: "story__note", text: note }) : null,
        crew.length ? el("ul", { class: "slines" }, ...crew.map(lineNode)) : null].filter(Boolean);
    }
  }
  // Replace the story only when its words change, so screen readers are not re-read every render.
  if (box.dataset.key !== key) {
    const prev = box.dataset.count || "";
    box.dataset.key = key;
    box.replaceChildren(...kids);
    if (prev && count && prev !== count && !reducedMotion()) box.querySelector(".hero__num")?.classList.add("is-changed");
    box.dataset.count = count;
  }
  // One announcement at most every 30 s, only when the volcano, the flights or the advisories
  // change (R15.6).
  if (sit && announce && text) {
    const t = performance.now();
    const akey = `${sit.volcano_id}|${text}`;
    if (lastAnnounce.key && akey !== lastAnnounce.key && t - lastAnnounce.at > 30e3) {
      announce(`${sit.volcano_name}: ${text}`);
      lastAnnounce = { at: t, key: akey };
    } else if (!lastAnnounce.key) lastAnnounce = { at: t, key: akey };
  }
}

function renderActions(D, store, ui, sit) {
  const box = $("story-actions");
  const kids = [];
  let ctaHref = "/desk", ctaText = "Open the Desk", primary = false, waiting = 0;
  if (D && sit) {
    const a = advisoryFacts(D, store, sit.volcano_id);
    waiting = a.drafts;
    if (a.urgent) { ctaHref = `/desk#review/${encodeURIComponent(a.urgent.id)}`; ctaText = "Decide on the Desk →"; primary = true; }
    // no drafts because the AI did not run: the Desk holds the hand-plan work (W18)
    else if (handPlan(D, store).flights.some((x) => x.p.volcano_id === sit.volcano_id)) { ctaText = "Decide on the Desk →"; primary = true; }
  } else if (D && D.regionEmpty) {
    const others = (D.state.regions || []).filter((r) => D.regionCounts[r.key] > 0);
    if (others.length) {
      kids.push(el("p", { class: "story__note", text: "Ash elsewhere:" }),
        el("div", { class: "btn-row" }, ...others.map((r) => el("button", { type: "button", class: "btn", dataset: { region: r.key, focus: `elsewhere-${r.key}` }, text: `${r.name} · ${D.regionCounts[r.key]}` }))));
    }
  }
  if (D) {
    kids.push(el("a", { id: "cta", class: primary ? "cta" : "btn cta--quiet", href: ctaHref, target: "_blank", rel: "noopener", dataset: { focus: "cta" } }, ctaText));
    // the way into AI at work (UI-DESIGN 7.21) in words, beside the one main action
    kids.push(el("button", { type: "button", class: "link-btn story__board", dataset: { act: "board-open", focus: "story-board" }, "aria-keyshortcuts": "A" }, icon("i-agent"), el("span", { text: "See the AI at work" })));
  }
  const key = kids.map((k) => `${k.textContent}|${k.getAttribute?.("href") || ""}`).join("§");
  if (box.dataset.key !== key) { box.dataset.key = key; box.replaceChildren(...kids); }
  // phone sticky call to action (R4.4)
  const sticky = $("cta-sticky");
  if (sticky) {
    sticky.href = ctaHref;
    setText(sticky, primary ? (waiting ? `Decide on the Desk (${waiting}) →` : "Decide on the Desk →") : "Open the Desk");
    sticky.classList.toggle("cta-sticky--quiet", !primary);
  }
}

// ------------------------------------------------------------------ key (R5.5)

// The map key sits on the map (top left) at 601 px and up, and under the map on a phone; it folds
// to one bar ("Map key" and three swatches). "never smaller than official" stays on its TEPHRA row
// (docs/UI-AI-QUIET.md 2.2).
export function keyRows(D, ui) {
  const rows = [];
  const sw = (id, cls) => icon(id, `sw ${cls}`);
  if (!D) return rows;
  if (D.official.some((f) => f.properties.show)) rows.push([sw("lg-area-official", "sw--official"), "Official ash area", "binding"]);
  if (ui.layers.tephra && D.cones.length) rows.push([sw("lg-area-tephra", "sw--tephra"), "TEPHRA's estimate", "never smaller than official"]);
  if (D.crew.drawn.length) rows.push([sw("lg-area-crew", "sw--crew"), "Crew report area", null]);
  if (ui.layers.aircraft && D.exposed.length) rows.push([sw("i-aircraft", "sw--exposed"), "RFA flight in or heading in", null]);
  if (ui.layers.aircraft && D.exposed.length >= 6) rows.push([sw("lg-flight-group", "sw--exposed"), "RFA flights close together", "click to zoom in"]);
  const step = D.official.find((f) => f.properties.show && f.properties.step !== "now");
  if (step) rows.push([sw("lg-area-forecast", "sw--official"), `Official forecast area (${step.properties.layer.replace("FCST+", "+").replace("H", " h")})`, null]);
  if (ui.layers.aircraft && D.aircraft.some((f) => !f.properties.exposed)) rows.push([sw("i-aircraft", "sw--aircraft"), "Other aircraft (not RFA)", null]);
  if (ui.layers.routes && D.hasRouteLine) rows.push([sw("lg-route", "sw--route"), "Route (origin to destination)", "airport codes at the ends"]);
  const pickedReroute = !!D.selFlight && D.rerouteKeys?.has(`${D.selFlight.properties.hex}:${D.selFlight.properties.volcano_id}`);
  if ((ui.layers.reroutes && D.hasReroutes) || pickedReroute) rows.push([sw("lg-reroute", "sw--reroute"), "Suggested reroute", null]);
  if (D.rose && ui.layers.rose) rows.push([sw("lg-arrow-observer", "sw--observer"), "Observatory's reported drift", null]);
  if (D.cones.some((f) => f.properties.part === "sector")) rows.push([sw("lg-area-hatch", "sw--tephra"), "Where TEPHRA widened the area", null]);
  if (ui.layers.satboxes && D.hasSatBoxes) rows.push([sw("lg-satbox", "sw--sat"), "Box marked on the satellite picture", "AI-read · supporting only"]);
  return rows;
}

function renderKey(D, ui) {
  const box = $("legend");
  const rows = keyRows(D, ui);
  box.hidden = !rows.length;
  const key = `${ui.keyOpen ? "open" : "shut"}§${rows.map((r) => `${r[1]}|${r[2]}`).join("§")}`;
  box.classList.toggle("is-open", !!ui.keyOpen);
  if (box.dataset.key === key && box.childElementCount) return;
  box.dataset.key = key;
  const glyphs = rows.slice(0, 3).map(([s]) => s.cloneNode(true));
  box.replaceChildren(
    el("button", { type: "button", class: "key__toggle", "aria-expanded": ui.keyOpen ? "true" : "false", "aria-controls": "key-rows", dataset: { act: "key-toggle", focus: "key-toggle" } },
      el("span", { class: "key__toggle-label", text: "Map key" }), el("span", { class: "key__glyphs", "aria-hidden": "true" }, ...glyphs),
      icon("i-chevron-down", "icon key__chev")),
    el("ul", { class: "key__rows", id: "key-rows", hidden: !ui.keyOpen }, ...rows.map(([s, label, sub]) => el("li", { class: "key__row" }, s, el("span", { class: "key__text" }, el("span", { class: "key__label", text: label }), sub ? el("span", { class: "key__sub", text: sub }) : null))),
      el("li", { class: "key__more-row" }, el("button", { type: "button", class: "link-btn key__more", dataset: { act: "help-map", focus: "key-more" }, text: "Full map key and alert colours ›" }))));
}

// ------------------------------------------------------------------ notes, all volcanoes

function renderNotes(notes) {
  const box = $("story-notes");
  const key = notes.map((n) => n.text).join("|");
  if (box.dataset.key === key) return;
  box.dataset.key = key;
  box.replaceChildren(...notes.map((n) => el("p", { class: "story-note" }, st("st-info", "var(--c-info)"), el("span", { text: n.text }))));
}

function renderAll(D, ui) {
  const kx = $("kpi-exposed");
  const s = D?.state;
  const active = D?.activeCount ?? 0;
  // One sentence, comma-separated, each count with its own words, so a wrapped line never starts
  // with a stray separator or a bare dash (review 2, item 13).
  const label = (id, text) => setText($(id).nextElementSibling, text);
  setText($("kpi-active"), !D ? "–" : active ? String(active) : "no");
  label("kpi-active", active === 1 ? "volcano with ash" : D && !active ? "volcano with ash reported" : "volcanoes with ash");
  // RFA is a fictional airline. At 0 the count shows a dash, never "0", "none" or "clear": the
  // feed only sees aircraft that broadcast on ADS-B (G17).
  const exposed = s?.exposed_count ?? 0;
  setText(kx, exposed > 0 ? String(exposed) : D ? "no" : "–");
  label("kpi-exposed", exposed > 0 ? `RFA flight${exposed === 1 ? "" : "s"} in or heading in` : D ? "RFA flight seen heading in" : "RFA flights in or heading in");
  kx.closest(".kpi").title = exposed > 0
    ? `${exposed} RFA (fictional) flight${exposed === 1 ? "" : "s"} in or heading into TEPHRA's estimated area, all volcanoes.`
    : "No RFA (fictional) flight seen heading in. Receiver coverage is patchy: an empty map is not an empty sky.";
  kx.setAttribute("aria-label", exposed > 0 ? String(exposed) : "0 seen. An empty map is not an empty sky");
  // null: the server could not read the drafts; an older count is not shown as current. Why a
  // count is 0 is the story's notice, said once there (not again here).
  setText($("kpi-drafts"), !D ? "–" : s.draft_count === null ? "unknown (database error)" : String(s.draft_count ?? 0));
  label("kpi-drafts", D && s.draft_count === 1 ? "advisory waiting" : "advisories waiting");
  const ul = $("volcano-tabs");
  if (!D) { ul.replaceChildren(); return; }
  const others = D.sits.filter((x) => x.volcano_id !== D.selected);
  // Crew areas near no active volcano belong to no volcano's story: one row says where they are.
  const away = D.sit ? D.crew.drawn.filter((v) => v.state === "ACTIVE" && D.crew.homeless(v)) : [];
  const outside = away.some((v) => v.discrepancy);
  const crewRow = away.length ? el("li", {}, el("button", { type: "button", class: "vrow", dataset: { act: "details-open", sec: "crew", focus: "vrow-crew" }, "aria-label": `${plural(away.length, "crew report", "crew reports")} of ash away from these volcanoes${outside ? ", outside the official area" : ""}. Show the crew reports.` },
    outside ? st("st-caution", "var(--c-caution)") : icon("i-pin", "icon vrow__crew"), el("span", { class: "vrow__text", text: `${plural(away.length, "crew report", "crew reports")} of ash elsewhere` }), el("span", { class: "vrow__go", "aria-hidden": "true", text: "›" }))) : null;
  // The volcano rows come first; the crew row shows only when they all fit with room for it,
  // else it folds into the "+ n more" line, which opens the full list with the row in it.
  const room = ui.vlistOpen ? Infinity : listRows();
  const crewShown = crewRow && room - others.length >= 1;
  const limit = room - (crewShown ? 1 : 0);
  const rows = others.slice(0, limit).map((x) => {
    const nCheck = x.discrepancies.filter((d) => (SEV_RANK[d.severity] || 0) >= 2).length;
    const n = x.exposed_count || 0;
    const words = [x.volcano_name, n ? plural(n, "flight", "flights") : "no flights", nCheck ? plural(nCheck, "thing to check", "things to check") : null].filter(Boolean).join(" · ");
    return el("li", {}, el("button", { type: "button", class: "vrow", dataset: { act: "select", vid: x.volcano_id, focus: `vrow-${x.volcano_id}` } },
      eruptIcon(x.color_code), el("span", { class: "vrow__text", text: words }), el("span", { class: "vrow__go", "aria-hidden": "true", text: "›" })));
  });
  if (crewShown) rows.push(crewRow);
  const folded = crewRow && !crewShown ? ` · ${plural(away.length, "crew report", "crew reports")}` : "";
  if (others.length > limit || folded) rows.push(el("li", {}, el("button", { type: "button", class: "link-btn vlist__more", "aria-expanded": "false", dataset: { act: "vlist-more", focus: "vlist-more" }, text: `+ ${Math.max(0, others.length - limit)} more${folded}` })));
  const key = rows.map((r) => r.textContent).join("|");
  if (ul.dataset.key !== key) { ul.dataset.key = key; ul.replaceChildren(...rows); }
}

// ------------------------------------------------------------------ entry

export function renderStory(D, store, ui, { conn, extra, announce, notes = [] }) {
  const sit = D?.sit || null;
  renderFailures(storyFailures(D, store, conn, extra));
  const h1 = $("volcano-name");
  if (!D) setText(h1, extra.error ? "TEPHRA" : "Connecting to TEPHRA…");
  else if (sit) setText(h1, sit.volcano_name);
  else if (D.regionEmpty || D.reading) setText(h1, D.area?.name || (D.reading ? "Watched regions" : "This area"));
  else setText(h1, "Watched regions");
  document.body.classList.toggle("is-connecting", (!D && !extra.error) || !!D?.reading);
  // A load error shows the failure line only: no numbers and never a cached story (R5.4).
  $("verdict").classList.toggle("verdict--error", !D && !!extra.error);
  eyebrow(D, sit, sit ? regionOfVent(D.state, D.vents.get(sit.volcano_id)) : null, store);
  if (!D && extra.error) { $("headline").replaceChildren(); $("headline").dataset.key = ""; }
  else renderLines(D, store, ui, sit, announce);
  $("verdict").classList.toggle("verdict--hypothesis", !!sit && D.coneOf(sit.volcano_id)?.properties.mode === "HYPOTHESIS");
  renderActions(D, store, ui, sit);
  renderKey(D, ui);
  renderNotes(notes);
  renderAll(D, ui);
  fitStory(D, ui);
}

// ------------------------------------------------------------------ fit (R4.1, review 2, item 4)

// The story column must not scroll at desktop widths: content was cut off half-visible under the
// pinned Details button. Each fit level tightens the column a step (spacing, then the lead line's
// size, the key rows, the button beside the flights link, the other-volcanoes rows folded into
// "+ n more", the fact lines, the Details sub-line) until it fits. The map key always shows its
// rows and notes (two columns, wall.css). Nothing is removed: folded rows stay one tap away, and the
// column still scrolls as a last resort, with a fade above the pinned button. Phones scroll the
// page and skip this.
//
// The pass measures the column as it is laid out at that moment, and the column's size can change
// with no render after it: at 1360-1599 px it comes back from under Details at the drawer's width
// and narrows while the stage animates, so a pass run on that render fitted a wider column than
// the one left on screen (story text review 2, item 1). A ResizeObserver runs the pass again once
// the column's box has settled.
const FIT_MAX = 8;
let fitKey = "";
let fitArgs = null;
let fitTimer = 0;
const fitObserver = new ResizeObserver(() => {
  clearTimeout(fitTimer);
  fitTimer = setTimeout(() => { if (fitArgs) fitStory(...fitArgs); }, 80);
});
let observed = null;
function fitStory(D, ui) {
  const box = $("story");
  if (!box) return;
  fitArgs = [D, ui];
  if (observed !== box) { fitObserver.observe(box); observed = box; }
  if (window.innerWidth <= 600 || !D) {
    if (box.dataset.fit) { delete box.dataset.fit; fitCap = Infinity; }
    fitKey = "";
    return;
  }
  // hidden under Details (1360-1599 px): nothing to measure; measure when it shows again
  if (!box.offsetHeight) { fitKey = ""; return; }
  const key = `${box.offsetWidth}x${box.offsetHeight}|${ui.vlistOpen ? 1 : 0}|${box.querySelector("#verdict")?.textContent}|${$("story-notes").textContent}|${$("fail-line").hidden ? "" : $("fail-line").textContent}|${$("allv").textContent}`;
  if (key === fitKey) return;
  fitKey = key;
  const over = () => box.scrollHeight - box.clientHeight > 1;
  const run = () => {
    let level = 0;
    box.dataset.fit = "0";
    if (fitCap !== Infinity) { fitCap = Infinity; renderAll(D, ui); }
    while (over() && level < FIT_MAX) {
      level += 1;
      box.dataset.fit = String(level);
      // level 6 folds the other-volcanoes rows into "+ n more"
      if (level === 6 && !ui.vlistOpen) { fitCap = 0; renderAll(D, ui); }
    }
  };
  run();
  // Folding every row may free more room than needed: give rows back while they still fit.
  if (fitCap === 0 && !over()) {
    for (let c = 1; c <= 3; c += 1) {
      fitCap = c;
      renderAll(D, ui);
      if (over()) { fitCap = c - 1; renderAll(D, ui); break; }
    }
  }
  box.classList.toggle("story--scrolls", over());
}
export function refitStory(D, ui) { fitKey = ""; fitStory(D, ui); }
// web fonts change line heights: measure again on the next render once they are in
document.fonts?.ready?.then(() => { fitKey = ""; });

// The coverage note for the selected volcano, when no aircraft at all is seen near it.
export function coverageNote(D, store) {
  const sit = D?.sit;
  if (!sit) return null;
  const adsb = store.feeds.find((f) => f.feed === "adsb");
  if (!adsb || adsb.status !== "OK") return null;
  const v = D.vents.get(sit.volcano_id);
  if (!v) return null;
  const near = D.aircraft.some((f) => kmBetween(f.geometry.coordinates, v) < 150);
  return near ? null : `No aircraft seen within 150 km of ${sit.volcano_name} in the open ADS-B feed. Receiver coverage is patchy here: an empty map is not an empty sky.`;
}

