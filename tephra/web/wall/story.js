// The story column (docs/UI-REDESIGN.md R3.2, R5): the failure line, the story card, the map key,
// the trust line, the story notes and the "All volcanoes" line. Every sentence is built by code
// from fields and goes in with textContent; a missing field drops its line and is never guessed.
// The story is about the selected volcano; the "All volcanoes" line carries the global counts.

import { $, el, icon, hhmmz, ms, fl, kmBetween, reducedMotion } from "./util.js";
import { SEV_RANK, regionOfVent } from "./derive.js";
import { ext, failureCount, replanning } from "./ext.js";
import { planProblem } from "./x-parts.js";
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

// Every problem the story must show without a tap, worst first. `where` names the Details
// section that holds it.
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
    out.push({ key: `feed-${id}`, text: `${name} is failing. Showing the last good ${what}${Number.isFinite(good) ? `, from ${hhmmz(good)}` : ""}.`, where: "feeds" });
  }
  if (D.state.store && D.state.store.ok === false) out.push({ key: "db", text: "The database is failing: some counts may be unknown.", where: "feeds" });
  const plan = currentPlan();
  if (plan?.status === "AI_UNAVAILABLE") {
    const p = planProblem(plan);
    out.push({ key: `plan-${plan.id}`, text: p ? `Airport plan: ${p.words.replace(/^No plan found: /, "no plan found, ").replace(" the network by hand", " by hand")}` : `Airport plan: AI unavailable (${String(plan.unavailable_reason || "no reason given").replace(/^AI UNAVAILABLE:?\s*/i, "")}).`, where: "recovery" });
  }
  for (const r of store.snapshot?.satellite || []) {
    if (r.status !== "ai_unavailable") continue;
    out.push({ key: `sat-${r.volcano_id}`, text: `Satellite reader: AI unavailable (${String(r.reason || "no reason given").replace(/^AI UNAVAILABLE:?\s*/i, "")}).`, where: "sat" });
  }
  const duty = store.snapshot?.duty;
  if (duty?.outcome === "MODEL_FAILED") out.push({ key: `duty-${duty.id}`, text: `Duty Officer: AI unavailable (${duty.validation_errors?.[0] || "no reason recorded"}).`, where: "ai" });
  const fails = failureCount(store);
  if (fails) out.push({ key: `trace-fails-${fails}`, text: `${plural(fails, "AI step", "AI steps")} failed.`, where: "ai", quiet: true });
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
  const key = [...shown.map((f) => f.key), more].join("|");
  const ul = $("fail-list");
  if (ul.dataset.key !== key) {
    ul.dataset.key = key;
    ul.replaceChildren(...shown.map((f) => {
      // role=alert only on the render where the failure first appears (R15.6)
      const fresh = !seenFailures.has(f.key);
      seenFailures.add(f.key);
      return el("li", { class: "fail-line__item", role: fresh && !f.quiet ? "alert" : null },
        st("st-serious", "var(--c-serious)"), el("span", { text: f.text }),
        f.action ? el("button", { type: "button", class: "link-btn", dataset: { act: f.action, focus: `fail-${f.key}` }, text: f.actionText }) : null);
    }), ...(more > 0 ? [el("li", {}, el("button", { type: "button", class: "link-btn fail-line__more", dataset: { act: "details-open", sec: items[shown.length].where, focus: "fail-more" }, text: `+ ${plural(more, "more problem", "more problems")} ›` }))] : []));
  }
  box.hidden = !list.length;
}

// ------------------------------------------------------------------ the story card (R5.1-R5.4)

function eyebrow(D, sit, region, store) {
  const iconBox = $("eyebrow-icon");
  if (!sit) {
    iconBox.replaceChildren();
    setText($("eyebrow-rest"), "");
    setText($("eyebrow-asof"), D ? `as of ${hhmmz(D.now)}` : "");
    return;
  }
  iconBox.replaceChildren(eruptIcon(sit.color_code));
  const regName = region ? (D.state.regions || []).find((r) => r.key === region)?.name : null;
  const alert = CODE_WORD[sit.color_code] ? `alert ${CODE_WORD[sit.color_code]}` : "alert colour not given";
  // a no-break space before each "·" keeps the dot at the end of a line, never at the start of
  // the next one (review 2, item 13)
  setText($("eyebrow-rest"), [regName, alert].filter(Boolean).map((t) => `\u00a0· ${t}`).join(""));
  setText($("eyebrow-asof"), `as of ${hhmmz(ms(sit.as_of))}`);
  $("eyebrow-asof").title = "Times ending in Z are UTC";
}

// The lines of the story, as { text, cls, title, tag } objects.
function storyLines(D, store, ui, sit) {
  const lines = [];
  const cone = D.coneOf(sit.volcano_id)?.properties;
  const stub = D.state.llm?.backend === "stub";
  if (cone?.mode === "HYPOTHESIS") {
    lines.push({ text: "HYPOTHESIS: no valid official product. Only MONITOR or HOLD may be advised.", cls: "story__hyp", banner: true });
  } else {
    const b = officialBand(D, sit.volcano_id);
    if (b) {
      lines.push({
        text: b.base > 0
          ? `Official reports put the ash between ${ft(b.base)} and ${ft(b.top)} ft (${fl(b.base)}–${fl(b.top)}).`
          : `Official reports put the ash up to ${ft(b.top)} ft (${fl(b.top)}).`,
      });
    }
  }
  const dir = sit.discrepancies.find((d) => d.kind === "DIRECTION_MISMATCH" && d.aspect === "direction" && (SEV_RANK[d.severity] || 0) >= 2);
  if (dir) {
    let tail = "";
    if (cone?.mode === "WIDENED") tail = " TEPHRA's estimate covers both.";
    else if (cone?.mode === "OFFICIAL") tail = stub ? " TEPHRA's estimate has not been widened (AI off)." : " TEPHRA's estimate has not been widened.";
    lines.push({ text: `The sources disagree on where the ash is heading (${Math.round(dir.magnitude)}° apart).${tail}`, cls: "story__dis" });
  }
  const silence = sit.discrepancies.find((d) => d.kind === "SILENCE");
  if (silence) lines.push({ text: "Ash was reported and no VAA has followed.", cls: "story__dis" });
  const conflict = sit.discrepancies.find((d) => d.kind === "CONFLICT");
  if (conflict) lines.push({ text: "A no-ash VAA was in force when another report saw ash after it.", cls: "story__dis" });
  const plan = currentPlan();
  const closed = closuresFor(D, sit.volcano_id, plan);
  const re = replanning(store);
  if (re) {
    // The trace does not say which volcano closed them, so the line says its scope: every
    // volcano (review 2, item 2, spec G8).
    lines.push({ text: `Ash closes ${plural(re.airports.length, "RFA airport", "RFA airports")} (all volcanoes): ${re.airports.join(", ")}. Re-planning the day's flights…`, title: `Re-plan started at ${hhmmz(re.at)}` });
  } else if (closed.length) {
    const icaos = [...new Set(closed.map((c) => c.icao))];
    const all = new Set(plan.closures.map((c) => c.icao)).size;
    lines.push({ text: `Ash from ${sit.volcano_name} closes ${plural(icaos.length, "RFA airport", "RFA airports")}: ${icaos.join(", ")}${all > icaos.length ? ` (${all} across all volcanoes)` : ""}.`, title: `Airport plan as of ${hhmmz(ms(plan.created_at))}` });
  }
  const n = sit.exposed_count || 0;
  if (n > 0) {
    lines.push({ text: `${n} ${n === 1 ? "flight" : "flights"} of RFA, our fictional airline, ${n === 1 ? "is" : "are"} in or heading into TEPHRA's estimated ash area.`, cls: "story__flights", count: n });
    const a = advisoryFacts(D, store, sit.volcano_id);
    let t, goneNote = null;
    if (a.unknown) t = "Advisory count unknown (database error).";
    // One advisory per flight; a draft can outlive the flight's exposure, so the count is of
    // advisories, never "n of their" (review 1, item 3).
    else if (a.drafts > 0) {
      t = `${a.partial ? "At least " : ""}${a.drafts} ${a.drafts === 1 ? "advisory waits" : "advisories wait"} for a dispatcher.`;
      // drafts whose flight is not among the n seen heading in now, said once so 30 next to 23 adds up
      const seen = new Set(D.exposed.filter((f) => f.properties.volcano_id === sit.volcano_id).map((f) => `${f.properties.hex}:${sit.volcano_id}`));
      const gone = store.advisories.filter((x) => x.volcano_id === sit.volcano_id && x.status === "DRAFT" && !seen.has(x.flight_id)).length;
      if (gone > 0 && !a.partial) goneNote = `${gone} of them ${gone === 1 ? "is for a flight" : "are for flights"} no longer seen heading in.`;
    }
    else if (a.decided > 0) t = `All ${a.decided} advisories are decided: ${a.approved} approved, ${a.rejected} rejected.`;
    else t = "Their advisories are not drafted yet.";
    lines.push({ text: t, cls: "story__wait" });
    if (goneNote) lines.push({ text: goneNote, cls: "story__note" });
  } else {
    const adsb = store.feeds.find((f) => f.feed === "adsb");
    const ok = adsb?.status === "OK";
    lines.push({ text: "No RFA flight is seen heading into TEPHRA's area right now." });
    lines.push({ text: ok ? "Aircraft coverage here is patchy: an empty map is not an empty sky." : `Aircraft data is ${adsbWord(adsb?.status)}: an empty map is not an empty sky.`, cls: "story__note" });
  }
  return [...lines, ...crewLines(D, sit)];
}

// Crew reports of ash (UI-DESIGN 7.6, 7.20): one line at most, after the flights, for this
// volcano's active crew areas (a report near no active volcano: the all-volcanoes story, and a
// row in the volcano list). A covered area adds nothing the official lines do not already say,
// so it has no line. The line opens Details › Crew reports. A crew area is an operator-policy
// flag: its line never changes the official or TEPHRA lines above.
export function crewLines(D, sit) {
  const C = D.crew;
  const mine = C.drawn.filter((v) => v.state === "ACTIVE" && (sit ? v.report.volcano_id === sit.volcano_id : C.homeless(v)));
  if (!mine.length) return [];
  const ids = new Set(mine.map((v) => v.report.id));
  const flagged = C.flags.filter((f) => f.report_ids.some((id) => ids.has(id)));
  const outside = mine.some((v) => v.discrepancy);
  const what = `${mine.length === 1 ? "Crew report" : `${mine.length} crew reports`} of ash${outside ? " outside the official area" : ""}`;
  let text;
  // the flight numbers are one tap away (the line opens Details), so the line stays two lines
  if (flagged.length) text = `${what}: ${plural(flagged.length, "RFA flight", "RFA flights")} on ${mine.length === 1 ? "its" : "their"} route.`;
  else text = `${what}, ${mine[0].age_text}.`;
  return [{ text, cls: "story__crew", mark: outside ? "caution" : "pin", act: "crew" }];
}

let lastAnnounce = { at: 0, key: "" };

function renderLines(D, store, ui, sit, announce) {
  const box = $("headline");
  let lines;
  if (!D) lines = [{ text: "Connecting to TEPHRA…", cls: "story__note story__connecting" }];
  else if (sit) lines = storyLines(D, store, ui, sit);
  else if (D.reading) {
    // Active volcanoes are known but their situation cards have not arrived: never "no ash".
    lines = [{ text: "Reading the official reports…", cls: "story__connecting" },
      { text: D.state.last_tick ? "Ash is reported here. The summary appears when TEPHRA has read the reports, usually within a minute." : "TEPHRA has just started and is reading every feed for the first time. This takes up to a minute.", cls: "story__note" }];
  } else if (D.regionEmpty) {
    const name = D.area?.name || "this area";
    lines = [{ text: `No ash reported near ${name} right now.` }];
  } else lines = [{ text: "No official ash report is in force in the watched regions right now." }];
  if (D && !sit) lines.push(...crewLines(D, null));
  const replay = D?.mode === "REPLAY" && !!sit;
  // Replace the lines only when their words change, so screen readers are not re-read every render.
  const key = [replay, ...lines.map((l) => `${l.cls || ""}:${l.text}`)].join("|");
  if (box.dataset.key !== key) {
    const prev = box.dataset.count || "";
    box.dataset.key = key;
    box.replaceChildren(...lines.map((l, i) => {
      if (l.banner) return el("p", { class: "story__hyp", role: "note" }, st("st-caution", "var(--c-caution)"), el("span", { text: l.text }));
      const p = el("p", { class: `story__line ${l.cls || ""}`.trim(), title: l.title || null });
      if (replay && i === 0) p.append(el("span", { class: "tag tag--replay story__rec", text: "Recorded" }), " ");
      // a line that opens its Details section is one button, the whole sentence its label
      const host = l.act ? el("button", { type: "button", class: "story__act", dataset: { act: "details-open", sec: l.act, focus: `story-${l.act}` } }) : p;
      if (l.mark === "pin") host.append(icon("i-pin", "icon story__pin"), " ");
      else if (l.mark === "caution") host.append(st("st-caution", "var(--c-caution)"), " ");
      host.append(l.text);
      if (l.act) p.append(host);
      return p;
    }));
    const flights = lines.find((l) => l.count != null);
    const now = String(flights?.count ?? "");
    if (prev && now && prev !== now && !reducedMotion()) {
      const node = box.querySelector(".story__flights");
      node?.classList.add("is-changed");
    }
    box.dataset.count = now;
  }
  // One announcement at most every 30 s, only when the volcano, flight count or waiting count
  // changes (R15.6). The message is the L4 and L5 lines.
  if (sit && announce) {
    const l4 = lines.find((l) => l.cls === "story__flights");
    const l5 = lines.find((l) => l.cls === "story__wait");
    const akey = [sit.volcano_id, l4?.count ?? 0, l5?.text || ""].join("|");
    const t = performance.now();
    if (lastAnnounce.key && akey !== lastAnnounce.key && t - lastAnnounce.at > 30e3 && l4) {
      announce(`${sit.volcano_name}: ${l4.text}${l5 ? ` ${l5.text}` : ""}`);
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
  } else if (D && D.regionEmpty) {
    const others = (D.state.regions || []).filter((r) => D.regionCounts[r.key] > 0);
    if (others.length) {
      kids.push(el("p", { class: "story__line story__note", text: "Ash elsewhere:" }),
        el("div", { class: "btn-row" }, ...others.map((r) => el("button", { type: "button", class: "btn", dataset: { region: r.key, focus: `elsewhere-${r.key}` }, text: `${r.name} · ${D.regionCounts[r.key]}` }))));
    }
  }
  if (D) {
    kids.push(el("a", { id: "cta", class: primary ? "cta" : "btn cta--quiet", href: ctaHref, target: "_blank", rel: "noopener", dataset: { focus: "cta" } }, ctaText));
    const n = sit ? D.exposed.filter((f) => f.properties.volcano_id === sit.volcano_id).length : 0;
    if (sit && n > 0) kids.push(el("button", { type: "button", class: "link-btn story__show", dataset: { act: "details-open", sec: "flights", focus: "show-flights" }, text: `Show the ${n} ${n === 1 ? "flight" : "flights"}` }));
  }
  const key = kids.map((k) => `${k.textContent}|${k.getAttribute?.("href") || ""}`).join("§");
  if (box.dataset.key !== key) { box.dataset.key = key; box.replaceChildren(...kids); }
  // phone sticky call to action (R4.4)
  const sticky = $("cta-sticky");
  if (sticky) {
    sticky.href = ctaHref;
    setText(sticky, primary ? `Decide on the Desk (${waiting}) →` : "Open the Desk");
    sticky.classList.toggle("cta-sticky--quiet", !primary);
  }
}

// ------------------------------------------------------------------ key (R5.5)

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
  if (step) rows.push([sw("lg-area-forecast", "sw--official"), `Official forecast area\u00a0(${step.properties.layer.replace("FCST+", "+").replace("H", "\u00a0h")})`, null]);
  if (ui.layers.aircraft && D.aircraft.some((f) => !f.properties.exposed)) rows.push([sw("i-aircraft", "sw--aircraft"), "Other aircraft (not RFA)", null]);
  if (ui.layers.routes && D.hasRouteLine) rows.push([sw("lg-route", "sw--route"), "Route (origin to destination)", "airport codes at the ends"]);
  const pickedReroute = !!D.selFlight && D.rerouteKeys?.has(`${D.selFlight.properties.hex}:${D.selFlight.properties.volcano_id}`);
  if ((ui.layers.reroutes && D.hasReroutes) || pickedReroute) rows.push([sw("lg-reroute", "sw--reroute"), "Suggested reroute", null]);
  if (D.rose && ui.layers.rose) rows.push([sw("lg-arrow-observer", "sw--observer"), "Observatory's reported drift", null]);
  if (D.cones.some((f) => f.properties.part === "sector")) rows.push([sw("lg-area-hatch", "sw--tephra"), "Where TEPHRA widened the area", null]);
  if (ui.layers.satboxes && D.hasSatBoxes) rows.push([sw("lg-satbox", "sw--sat"), "Box marked on the satellite picture", "supporting only"]);
  return rows;
}

function renderKey(D, ui) {
  const box = $("legend");
  const rows = keyRows(D, ui);
  const key = `${ui.keyOpen ? "open" : "shut"}§${rows.map((r) => `${r[1]}|${r[2]}`).join("§")}`;
  box.classList.toggle("is-open", !!ui.keyOpen);
  if (box.dataset.key === key && box.childElementCount) return;
  box.dataset.key = key;
  // Under the Details drawer (601-1599 px, .key--pinned) the key folds to one bar with the first
  // three swatches; the bar is hidden elsewhere (wall.css), where the rows always show.
  const glyphs = rows.slice(0, 3).map(([s]) => s.cloneNode(true));
  box.replaceChildren(
    el("ul", { class: "key__rows", id: "key-rows" }, ...rows.map(([s, label, sub]) => el("li", {}, s, el("span", {}, el("span", { class: "key__label", text: label }), sub ? el("span", { class: "key__sub", text: ` · ${sub}` }) : null)))),
    el("button", { type: "button", class: "link-btn key__more", dataset: { act: "help-map", focus: "key-more" }, text: "Full map key and alert colours ›" }),
    el("button", { type: "button", class: "key__toggle", "aria-expanded": ui.keyOpen ? "true" : "false", "aria-controls": "key-rows", dataset: { act: "key-toggle", focus: "key-toggle" } },
      el("span", { class: "key__toggle-label", text: "Map key" }), el("span", { class: "key__glyphs", "aria-hidden": "true" }, ...glyphs),
      el("span", { class: "key__toggle-word", text: ui.keyOpen ? "Hide" : `${rows.length} item${rows.length === 1 ? "" : "s"}` }), icon("i-chevron-up", "icon key__chev")));
}

// ------------------------------------------------------------------ trust, notes, all volcanoes

function renderTrust(D) {
  const box = $("trust");
  if (!D) { box.replaceChildren(); return; }
  const stub = D.state.llm?.backend === "stub";
  const text = stub ? "AI: off · code built this summary from the official reports" : `AI: on (${D.state.llm?.label || "model"}) · it can widen TEPHRA's estimate, never shrink the official area`;
  if (box.textContent === text) return;
  box.replaceChildren(icon(stub ? "i-code" : "i-model"), el("span", { text }));
}

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
  kx.closest(".kpi").classList.toggle("kpi--hot", exposed > 0);
  kx.closest(".kpi").title = exposed > 0
    ? `${exposed} RFA (fictional) flight${exposed === 1 ? "" : "s"} in or heading into TEPHRA's estimated area, all volcanoes.`
    : "No RFA (fictional) flight seen heading in. Receiver coverage is patchy: an empty map is not an empty sky.";
  kx.setAttribute("aria-label", exposed > 0 ? String(exposed) : "0 seen; an empty map is not an empty sky");
  // null: the server could not read the drafts; an older count is not shown as current.
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
  renderTrust(D);
  renderNotes(notes);
  renderAll(D, ui);
  fitStory(D, ui);
}

// ------------------------------------------------------------------ fit (R4.1, review 2, item 4)

// The story column must not scroll at desktop widths: content was cut off half-visible under the
// pinned Details button. Each fit level tightens the column a step (spacing, then line size, the
// key in two columns, the button beside the flights link, the other-volcanoes rows folded into
// "+ n more", the Details sub-line) until it fits. Nothing is removed: folded rows stay one tap
// away, and the column still scrolls as a last resort. Phones scroll the page and skip this.
const FIT_MAX = 8;
let fitKey = "";
function fitStory(D, ui) {
  const box = $("story");
  if (!box) return;
  if (window.innerWidth <= 600 || !D) {
    if (box.dataset.fit) { delete box.dataset.fit; fitCap = Infinity; }
    fitKey = "";
    return;
  }
  const key = `${window.innerWidth}x${window.innerHeight}|${ui.vlistOpen ? 1 : 0}|${box.querySelector("#verdict")?.textContent}|${$("legend").textContent}|${$("story-notes").textContent}|${$("fail-line").hidden ? "" : $("fail-line").textContent}|${$("allv").textContent}`;
  if (key === fitKey) return;
  fitKey = key;
  const over = () => box.scrollHeight - box.clientHeight > 1;
  let level = 0;
  box.dataset.fit = "0";
  if (fitCap !== Infinity) { fitCap = Infinity; renderAll(D, ui); }
  while (over() && level < FIT_MAX) {
    level += 1;
    box.dataset.fit = String(level);
    // level 6 folds the other-volcanoes rows into "+ n more"
    if (level === 6 && !ui.vlistOpen) { fitCap = 0; renderAll(D, ui); }
  }
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

