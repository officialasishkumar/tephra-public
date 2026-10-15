// The Operator policy dialog (docs/UI-DESIGN.md 7.18), from GET /api/policy. Summary first: one
// sentence and the six values that shape most advice, then every value under a tab, grouped and
// searchable, each opening to why it has that value and its sources; the sources and the
// trust order have their own tabs, the metadata sits under "About this policy". Every fact of
// policy_a.json is reachable. The wording is the file's: the page only splits it for display
// (a semicolon becomes a full stop, the "TEPHRA illustrative choice:" opening becomes a tag) and
// leaves quotations of the sources exactly as published. Strings go in through el().

import { el, icon, safeExternalUrl } from "./util.js";
import { dkTiles, dkRow, dkList, dkFacts, dkAbout, dkChip, dkEmpty, dkNote } from "./dk.js";

// Sections in reading order, with a plain heading and what the values in it decide.
const SECTIONS = [
  ["exposure", "Height margin", "How far above and below the ash a flight must stay."],
  ["planner", "Flight plans", "When TEPHRA proposes a level change, a hold or a diversion."],
  ["reroute", "Reroutes", "How a route around the ash is drawn."],
  ["alternates", "Alternate airports", "Which airports a flight may divert to."],
  ["crew_reports", "Crew reports of ash", "The caution area drawn from a crew's report."],
  ["recovery", "Airport plan", "Re-planning the day's flights around airports the ash closes."],
  ["fuel", "Fuel", "What the fuel line costs."],
  ["drafts", "Drafts", "When an open advisory draft is retired."],
  ["duty", "Coordinator", "When left-over assistant work is offered again."],
];

// A name a person reads for each setting; an unknown setting shows its own words.
const LABELS = {
  "exposure.vertical_margin_ft": "Margin above and below the ash",
  "planner.level_search_ft": "How far to look for a clear level",
  "planner.level_band_fl": "Width of a proposed level band",
  "planner.max_change_level_fl": "Highest level proposed",
  "planner.divert_within_min": "Divert when entry is this close",
  "planner.hold_within_min": "Hold when entry is this close",
  "reroute.buffer_nm": "Distance kept from the ash",
  "reroute.simplify_nm": "Smoothing of the ash outline",
  "reroute.max_waypoints_count": "Most turn points in a route",
  "reroute.max_turn_deg": "Sharpest turn at a turn point",
  "reroute.rejoin_step_nm": "Spacing of the points to rejoin the track",
  "reroute.max_extra_min": "Longest detour offered",
  "reroute.min_extra_min": "Smallest gain worth a reroute",
  "reroute.route_max_cross_track_nm": "Furthest from a published route to use it",
  "reroute.cruise_tas_kt": "Speed assumed with no ground speed",
  "alternates.search_radius_nm": "Search radius for alternates",
  "alternates.min_runway_m": "Shortest runway accepted",
  "alternates.min_visibility_m": "Lowest forecast visibility accepted",
  "alternates.min_ceiling_ft": "Lowest forecast cloud ceiling accepted",
  "alternates.taf_eta_window_min": "Forecast window around arrival",
  "alternates.terminal_radius_nm": "Clearance between an alternate and the ash",
  "crew_reports.radius_nm": "Radius of a crew report area",
  "crew_reports.downwind_stretch_min": "Downwind stretch of the area",
  "crew_reports.stretch_wind_kt": "Wind that stretches the area",
  "crew_reports.level_margin_ft": "Margin around the reported level",
  "crew_reports.valid_min": "How long the area lasts",
  "recovery.min_turn_min": "Shortest turnaround",
  "recovery.max_delay_min": "Longest delay before cancelling",
  "recovery.freeze_window_min": "Departures too close to move",
  "recovery.horizon_after_closure_min": "How far past a closure to re-plan",
  "recovery.scenario_extend_1_min": "First longer-closure scenario",
  "recovery.scenario_extend_2_min": "Second longer-closure scenario",
  "recovery.solve_work_s": "Solver work per scenario",
  "recovery.solve_time_limit_s": "Solver time limit per scenario",
  "recovery.delay_cost_per_min_usd": "Delay cost per minute",
  "recovery.delay_cost_per_pax_hour_usd": "Delay cost per passenger hour",
  "recovery.cancel_cost_per_pax_usd": "Cancellation cost per passenger",
  "recovery.cancel_cost_fixed_usd": "Fixed cost of a cancellation",
  "recovery.swap_cost_usd": "Cost of moving a flight to another aircraft",
  "recovery.ferry_cost_per_block_min_usd": "Ferry cost per block minute",
  "recovery.max_fdp_min": "Longest crew duty period planned",
  "recovery.airport_closure_radius_nm": "Airport closed when the ash is this close",
  "recovery.pax_notice_min_delay_min": "Shortest delay that gets a passenger notice",
  "fuel.hold_min": "Length of hold costed",
  "fuel.divert_extra_min": "Approach time added to a diversion",
  "drafts.unexposed_retire_min": "Retire a draft once its flight is clear for",
  "drafts.position_lost_retire_min": "Keep a draft after its flight is lost for",
  "duty.rerun_min": "Offer left-over work again after",
};

// The values that shape most advice, shown first.
const KEY_VALUES = ["exposure.vertical_margin_ft", "reroute.buffer_nm", "planner.divert_within_min", "planner.hold_within_min", "recovery.airport_closure_radius_nm", "crew_reports.radius_nm"];

const isValue = (v) => v && typeof v === "object" && "value" in v && "unit" in v;
const NB = " "; // number and unit never wrap apart
const num = (n) => Number(n).toLocaleString("en");
const USD = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 0, maximumFractionDigits: 2 });
const capFirst = (t) => (t ? t.charAt(0).toUpperCase() + t.slice(1) : t);
const words = (key) => capFirst(key.replace(/_(ft|m|nm|kt|min|s|deg|count|usd|fl)$/i, "").replace(/_/g, " "));

export function formatValue(key, v) {
  const n = Number(v.value);
  if (!Number.isFinite(n)) return `${v.value}${NB}${v.unit}`;
  switch (v.unit) {
    case "min": return n >= 120 && n % 60 === 0 ? `${num(n)}${NB}min (${n / 60}${NB}h)` : `${num(n)}${NB}min`;
    case "deg": return `${num(n)}°`;
    case "USD": return USD.format(n);
    case "count": return num(n);
    case "FL": return /_band_fl$/.test(key) ? `${num(n)}${NB}FL (${num(n * 100)}${NB}ft)` : `FL${String(n).padStart(3, "0")}`;
    default: return `${num(n)}${NB}${v.unit}`;
  }
}

// The file's reason, split for display: its "TEPHRA illustrative choice" opening becomes a tag,
// and each semicolon a full stop. Nothing else changes.
export function reasonParts(text) {
  const m = /^TEPHRA illustrative choice(, [^:]+)?: /.exec(text || "");
  const tag = m ? `Illustrative choice${m[1] || ""}` : null;
  const rest = m ? capFirst(text.slice(m[0].length)) : text || "";
  const sentences = rest.replace(/;\s+(\S)/g, (_, c) => `. ${c.toUpperCase()}`);
  return { tag, text: sentences };
}

// Every value of the policy, grouped: the known sections in order, then any other block with values.
export function policyValues(p) {
  const known = SECTIONS.map(([k]) => k);
  const extra = Object.keys(p).filter((k) => !known.includes(k) && p[k] && typeof p[k] === "object" && !Array.isArray(p[k]) && Object.values(p[k]).some(isValue));
  return [...SECTIONS, ...extra.map((k) => [k, words(k), null])].map(([key, title, about]) => ({
    key, title, about,
    rows: Object.entries(p[key] || {}).filter(([, v]) => isValue(v)).map(([name, v]) => ({
      id: `${key}.${name}`, label: LABELS[`${key}.${name}`] || words(name), value: formatValue(name, v), raw: v,
    })),
  })).filter((g) => g.rows.length);
}

const shortRef = (c) => c.ref.replace(/^(ICAO Doc 9974), Flight Safety and Volcanic Ash, 1st ed\. 2012, /, "$1 ").replace(/, printed .*$/, "").replace(/ \(.*\)$/, "");

// Source chips: each opens its citation in the Sources tab.
function citeChips(ids, cites, go) {
  const list = (ids || []).map((id) => cites[id]).filter(Boolean);
  if (!list.length) return null;
  return el("ul", { class: "pcites", "aria-label": "Sources" }, ...list.map((c) => {
    const b = el("button", { type: "button", class: "dk-chip dk-chip--btn pcite", title: c.ref, "aria-label": `Source: ${c.ref}. Show it in Sources.` }, icon("i-quote", "icon"), el("span", { text: shortRef(c) }));
    b.addEventListener("click", () => go(c.id));
    return el("li", {}, b);
  }));
}

export function policyDialog(data) {
  const p = data?.policy;
  if (!p) return dkNote("caution", "The operator policy could not be loaded. Reload the page.", { role: "status" });
  const cites = Object.fromEntries((p.citations || []).map((c) => [c.id, c]));
  const groups = policyValues(p);
  const all = groups.flatMap((g) => g.rows);
  const byId = Object.fromEntries(all.map((r) => [r.id, r]));
  const hash = String(data.policy_hash || "");

  const tabs = [["overview", "Overview"], ["values", `Values (${all.length})`], ["sources", `Sources (${(p.citations || []).length})`], ["order", `Trust order (${(p.source_order || []).length})`]];
  const tabBtn = {};
  const panel = {};
  const select = (key, focus = false) => {
    for (const [k] of tabs) {
      tabBtn[k].setAttribute("aria-selected", k === key ? "true" : "false");
      tabBtn[k].tabIndex = k === key ? 0 : -1;
      panel[k].hidden = k !== key;
    }
    if (focus) tabBtn[key].focus();
  };
  const tablist = el("div", { class: "ptabs", role: "tablist", "aria-label": "Operator policy" }, ...tabs.map(([k, label]) => {
    tabBtn[k] = el("button", { type: "button", role: "tab", id: `ptab-${k}`, class: "ptabs__tab", "aria-controls": `ppanel-${k}`, text: label });
    tabBtn[k].addEventListener("click", () => select(k));
    return tabBtn[k];
  }));
  // Arrow keys move between tabs (the WAI-ARIA tabs pattern, automatic activation).
  tablist.addEventListener("keydown", (e) => {
    const keys = tabs.map(([k]) => k);
    const i = keys.indexOf(document.activeElement?.id?.replace("ptab-", ""));
    if (i < 0) return;
    const j = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: keys.length - 1 }[e.key];
    if (j == null) return;
    e.preventDefault();
    select(keys[(j + keys.length) % keys.length], true);
  });

  // Sources: one card per citation, with what uses it.
  const usedBy = {};
  const use = (id, what) => { (usedBy[id] ||= []).push(what); };
  (p.summary_citation_ids || []).forEach((id) => use(id, "The policy in full"));
  for (const r of all) (r.raw.citation_ids || []).forEach((id) => use(id, r.label));
  (p.source_order || []).forEach((r, i) => (r.citation_ids || []).forEach((id) => use(id, `Trust order, rule ${i + 1}`)));
  const showCite = (id) => {
    select("sources");
    const card = panel.sources.querySelector(`[data-cite="${CSS.escape(id)}"]`);
    card?.scrollIntoView({ block: "start" });
    card?.focus({ preventScroll: true });
  };

  // Values: grouped rows that open to the reason and the sources, with a filter.
  const rowsById = {};
  const groupBoxes = groups.map((g) => {
    const rows = g.rows.map((r) => {
      const { tag, text } = reasonParts(r.raw.source);
      const chips = citeChips(r.raw.citation_ids, cites, showCite);
      const row = dkRow({
        key: `pol-${r.id}`, title: r.label, meta: el("span", { class: "prow__value", text: r.value }), cls: "prow",
        body: [
          tag ? dkChip(tag, { kind: "caution" }) : null,
          el("p", { class: "prow__why", text }),
          chips,
          el("p", { class: "prow__key" }, "Setting ", el("code", { class: "mono", text: r.id }), ` · ${r.raw.value} ${r.raw.unit}`),
        ],
      });
      row.dataset.search = `${r.label} ${r.id} ${r.value} ${r.raw.source} ${(r.raw.citation_ids || []).map((id) => cites[id]?.ref || "").join(" ")}`.toLowerCase();
      rowsById[r.id] = row;
      return row;
    });
    const list = dkList(rows, { first: rows.length, key: `pol-${g.key}`, label: `${g.title}: ${rows.length} values` });
    return el("section", { class: "pgroup", "aria-labelledby": `pg-${g.key}` },
      el("div", { class: "pgroup__head" }, el("h3", { id: `pg-${g.key}`, class: "pgroup__title", text: g.title }), el("span", { class: "pgroup__count", text: `${g.rows.length}` })),
      g.about ? el("p", { class: "pgroup__about", text: g.about }) : null, list);
  });
  const count = el("p", { class: "psearch__count", role: "status", text: `${all.length} values` });
  const none = dkEmpty("No value matches", "Try a word from its name, its unit or its reason, such as margin, NM or crew.");
  none.hidden = true;
  const search = el("input", { type: "search", id: "policy-search", class: "psearch__input", placeholder: "Find a value, such as margin or NM", autocomplete: "off", spellcheck: "false" });
  search.addEventListener("input", () => {
    const q = search.value.trim().toLowerCase();
    let shown = 0;
    groupBoxes.forEach((box) => {
      let n = 0;
      box.querySelectorAll(".prow").forEach((row) => { const hit = !q || row.dataset.search.includes(q); row.hidden = !hit; n += hit ? 1 : 0; });
      box.hidden = n === 0;
      shown += n;
    });
    none.hidden = shown > 0;
    count.textContent = q ? `${shown} of ${all.length} values` : `${all.length} values`;
  });
  const showValue = (id) => {
    select("values");
    if (search.value) { search.value = ""; search.dispatchEvent(new Event("input")); }
    const row = rowsById[id];
    if (!row) return;
    row.open = true;
    row.scrollIntoView({ block: "center" });
    row.querySelector("summary")?.focus({ preventScroll: true });
  };

  // Overview: the sentence, the values that matter most, the policy in full, about it.
  const margin = p.exposure?.vertical_margin_ft;
  const lede = el("p", { class: "policy__lede" }, el("strong", { text: `Policy ${p.preset}: ` }),
    `avoid every official ash area${isValue(margin) ? `, with ${num(margin.value)}${NB}${margin.unit} above and below` : ""}.`);
  const tiles = dkTiles(KEY_VALUES.filter((id) => byId[id]).map((id) => ({
    label: byId[id].label, value: byId[id].value, sub: groups.find((g) => g.rows.includes(byId[id]))?.title,
    go: { act: "policy-value", value: id },
  })), "The values that shape most advice");
  tiles.querySelectorAll("[data-act='policy-value']").forEach((b) => b.addEventListener("click", (e) => { e.stopPropagation(); showValue(b.dataset.value); }));
  const full = reasonParts(p.summary_text || "").text;
  const summaryChips = citeChips(p.summary_citation_ids, cites, showCite);
  const label = /^[A-Z]{3,}\b/.test(p.label || "") ? p.label.replace(/^([A-Z])([A-Z]+)/, (_, a, b) => a + b.toLowerCase()) : p.label;
  panel.overview = el("div", { id: "ppanel-overview", class: "ppanel", role: "tabpanel", "aria-labelledby": "ptab-overview", tabindex: "0" },
    lede,
    el("div", { class: "dk-chips" }, dkChip(label || "Illustrative", { kind: "caution" }), dkChip(p.version, { label: "Version", mono: true }), dkChip(p.risk_owner, { label: "Risk owner" })),
    el("p", { class: "policy__note", text: "An example operator policy for this demo: every margin, minimum and threshold TEPHRA applies, with its reason. No airline has reviewed it." }),
    el("h3", { class: "policy__h", text: "The values that shape most advice" }),
    tiles,
    el("button", { type: "button", class: "link-btn", dataset: { focus: "policy-all" }, text: `All ${all.length} values ›` }),
    el("div", { class: "dk-abouts" },
      dkAbout("What the policy says in full", "policy-full", el("p", { class: "policy__full", text: full }), summaryChips),
      dkAbout("About this policy", "policy-meta", dkFacts([
        ["Name", p.title],
        ["Policy", p.policy_id, { mono: true }],
        ["Version", p.version, { mono: true }],
        ["Status", label],
        ["Risk owner", p.risk_owner],
        ["Safety risk assessment", p.sra_ref || "None: this policy is illustrative"],
        ["Content hash", el("span", { class: "mono policy__hash", title: "SHA-256 of the policy's content. Every advisory records the first 12 characters." }, el("strong", { text: hash.slice(0, 12) }), hash.slice(12))],
      ]))));
  panel.overview.querySelector("[data-focus='policy-all']").addEventListener("click", () => select("values", true));

  panel.values = el("div", { id: "ppanel-values", class: "ppanel", role: "tabpanel", "aria-labelledby": "ptab-values", hidden: true },
    el("div", { class: "psearch" }, el("label", { class: "psearch__label", for: "policy-search", text: "Find a value" }), search, count),
    el("div", { class: "pgroups", role: "group", "aria-label": "Operator policy values" }, ...groupBoxes), none);

  panel.sources = el("div", { id: "ppanel-sources", class: "ppanel", role: "tabpanel", "aria-labelledby": "ptab-sources", tabindex: "0", hidden: true },
    el("p", { class: "policy__note", text: "The documents the values and the policy text cite, quoted as published. Values with no source here are TEPHRA's own illustrative choices." }),
    el("ol", { class: "pcards" }, ...(p.citations || []).map((c) => {
      const url = safeExternalUrl(c.url);
      return el("li", { class: "pcard", tabindex: "-1", dataset: { cite: c.id } },
        el("p", { class: "pcard__ref", text: c.ref }),
        el("blockquote", { class: "pcard__quote" }, el("q", { text: c.text })),
        usedBy[c.id]?.length ? el("p", { class: "pcard__used" }, el("span", { class: "pcard__k", text: "Used by " }), usedBy[c.id].join(", ")) : null,
        url ? el("a", { class: "link-btn", href: url, target: "_blank", rel: "noopener noreferrer" }, icon("i-external-link"), "Open the source") : null);
    })));

  panel.order = el("div", { id: "ppanel-order", class: "ppanel", role: "tabpanel", "aria-labelledby": "ptab-order", tabindex: "0", hidden: true },
    el("p", { class: "policy__note", text: "When the sources disagree, this is the order TEPHRA's code trusts them in today. It is an operator choice: ICAO Doc 9974 2.4(d) asks the operator to resolve conflicts among its sources." }),
    el("ol", { class: "porder" }, ...(p.source_order || []).map((r) => {
      const { tag, text } = (() => { const m = /^Operator choice \(illustrative\): /.exec(r.text || ""); return { tag: m ? "Operator choice (illustrative)" : null, text: m ? capFirst(r.text.slice(m[0].length)) : r.text }; })();
      const chips = citeChips(r.citation_ids, cites, showCite);
      return el("li", { class: "porder__item" },
        el("p", { class: "porder__text", text: reasonParts(text).text }),
        tag ? dkChip(tag, { kind: "caution" }) : null,
        el("p", { class: "porder__code" }, el("span", { class: "pcard__k", text: "Applied by " }), el("code", { class: "mono", text: r.enforced_by })),
        chips);
    })));

  select("overview");
  return el("div", { class: "policy" }, tablist, panel.overview, panel.values, panel.sources, panel.order);
}
