// Static-ish Wall controls (docs/UI-REDESIGN.md R8.3, R9): Details › Map layers, 3D and compare,
// the Help dialog (read the map, the full key, the words used, the keyboard) and the About dialog.
// Built with el(); no HTML strings.

import { el, icon, airline, otherAircraft } from "./util.js";
import { GLOSSARY, GASES_SCOPE } from "./glossary.js";
import { has } from "./features.js";

const check = (key, label, on, hint, disabled = false) =>
  el("label", { class: `opt${disabled ? " opt--locked" : ""}` },
    el("input", { type: "checkbox", dataset: { layer: key, focus: `layer-${key}` }, checked: on ? true : null, disabled: disabled ? true : null }),
    el("span", { class: "opt__text" }, el("span", { text: label }), hint ? el("span", { class: "opt__hint", text: hint }) : null));

const radio = (name, value, label, on, hint) =>
  el("label", { class: "opt" },
    el("input", { type: "radio", name, value, dataset: { radio: name, focus: `${name}-${value}` }, checked: on ? true : null }),
    el("span", { class: "opt__text" }, el("span", { text: label }), hint ? el("span", { class: "opt__hint", text: hint }) : null));

const SAT_WORD = { off: "off", ir: "infrared", vis: "visible", airmass: "air mass" };

export function layersStatus(ui) {
  const parts = [ui.sat === "off" ? "satellite off" : `satellite: ${SAT_WORD[ui.sat]}`];
  if (ui.so2) parts.push("SO2 on");
  if (ui.btd) parts.push("BTD on");
  if (ui.d3) parts.push("3D");
  if (ui.compare) parts.push("compare");
  return parts.join(" · ");
}

export function renderLayers(ui, phone) {
  const box = document.getElementById("layers-pop");
  const L = ui.layers;
  // One card per kind of layer; the checkboxes are drawn as switches (wall.css), still real
  // checkboxes for keyboards and screen readers.
  const group = (title, ...kids) => el("fieldset", { class: "opts" }, el("legend", { class: "opts__legend", text: title }), ...kids);
  const status = layersStatus(ui);
  const more = el("details", { class: "dk-about", open: ui.layersMore ? true : null, dataset: { k: "layers-more", act: "layers-more" } },
    el("summary", { dataset: { focus: "layers-more" } }, icon("i-chevron-right", "icon dk-about__chev"), el("span", { text: "Satellite pictures, 3D and compare" })),
    el("div", { class: "dk-about__body dk-about__body--flush" },
      group("Satellite picture · context only, never ash detection",
        radio("sat", "off", "Off", ui.sat === "off"),
        radio("sat", "ir", "Infrared", ui.sat === "ir"),
        radio("sat", "vis", "Visible", ui.sat === "vis", "daylight"),
        radio("sat", "airmass", "Air mass", ui.sat === "airmass"),
        el("button", { type: "button", class: "chip-btn", dataset: { tool: "sat", focus: "tool-sat" }, "aria-pressed": ui.sat !== "off" ? "true" : "false", "aria-keyshortcuts": "I", title: "Next satellite picture (I)" }, "Next picture: ", el("span", { id: "sat-state", text: SAT_WORD[ui.sat] }))),
      // "context only, never ash detection" is said once in this fold, by the satellite group's title
      group("Gases and indicators",
        check("so2", "SO2 (TROPOMI, daily)", ui.so2, GASES_SCOPE),
        has("btd") ? check("btd", "Split-window BTD", ui.btd, "an indicator") : null),
      group("View",
        el("div", { class: "seg", role: "group", "aria-label": "View" },
          el("button", { type: "button", dataset: { act: "view-2d", focus: "view-2d" }, "aria-pressed": ui.d3 ? "false" : "true", text: "2D" }),
          el("button", { type: "button", dataset: { tool: "3d", focus: "tool-3d" }, "aria-pressed": ui.d3 ? "true" : "false", "aria-keyshortcuts": "D", title: "3D view, heights exaggerated six times (D)", text: "3D" })),
        phone ? el("p", { class: "opt__hint", text: "Compare is not offered on a phone." })
          : el("button", { type: "button", class: "chip-btn", dataset: { tool: "compare", focus: "tool-compare" }, "aria-pressed": ui.compare ? "true" : "false", "aria-keyshortcuts": "S", title: "Swipe compare (S)" }, icon("i-swipe"), "Compare: official only vs with TEPHRA"))));
  box.replaceChildren(el("div", { class: "dk", role: "region", "aria-labelledby": "layers-head" },
    el("header", { class: "dk-head" },
      el("div", { class: "dk-head__pills" }, el("span", { class: "dk-pill dk-pill--info", text: status.charAt(0).toUpperCase() + status.slice(1) })),
      el("p", { class: "dk-head__title", id: "layers-head", text: "Choose what the map shows. The official ash area and crew report areas are always on." })),
    group("Ash areas",
      check("official", "Official ash area", true, "always on · binding", true),
      check("tephra", "TEPHRA's estimate", L.tephra),
      has("crew") ? check("crew", "Crew report caution areas", true, "always on", true) : null,
      check("rose", "Disagreement arrows", L.rose, "the directions at the vent"),
      has("satellite") ? check("satboxes", "Satellite boxes", L.satboxes, "Read by Satellite reader") : null),
    group("Aircraft",
      check("aircraft", "Aircraft", L.aircraft),
      check("acLabels", "Other aircraft labels", L.acLabels, "from zoom 7.5"),
      check("paths", "Flight paths into the area", L.paths),
      check("routes", "Flight routes", L.routes, `origin to destination · ${airline().code} flights heading in, and the picked one`),
      check("reroutes", "Suggested reroutes", L.reroutes, "around TEPHRA's estimate")),
    group("Airports",
      check("airports", "Airports", L.airports, "the ones the airport plan closes are ringed red, with their closure radius")),
    group("Map context",
      check("context", "FIR and VAAC lines", L.context, "approximate"),
      check("navaids", "Navaids", L.navaids, "from zoom 8"),
      check("terrain", "Terrain shading", L.terrain, "Mapterhorn hillshade, no sea tiles")),
    el("div", { class: "dk-actions" }, el("button", { type: "button", class: "btn btn--small", dataset: { tool: "levels", focus: "tool-levels" }, "aria-keyshortcuts": "H", text: "Height filter ›" })),
    el("div", { class: "dk-abouts" }, more)));
}

// Keyboard (R16). Every shortcut also has a visible control; a hidden feature's key is left out.
const SHORTCUT_ROWS = [
  ["W", "How it works: the demo's welcome, the five steps"],
  ["E", "Expand or fold the story"],
  ["1 2 3", "Choose an area"],
  ["[ ]", "Previous / next volcano (the area follows)"],
  ["F", "Fit the selected volcano"],
  ["D", "3D on/off"],
  ["S", "Compare on/off (not on a phone)"],
  ["C", "Sources side by side (raw texts)"],
  ["I", "Satellite picture: off, infrared, visible, air mass"],
  ["O", "SO2 on/off"],
  ["B", "BTD indicator on/off", "btd"],
  ["L", "Details › Map layers (again: close)"],
  ["T", "Details › How TEPHRA decided"],
  ["H", "Details › Height filter"],
  ["P", "Presentation layout for recording (keeps Details closed)", "present"],
  ["A", "The side panel's TEPHRA Assistant tab: every step, newest first"],
  ["?", "Open the Guide"],
  ["Esc", "Close, one step at a time: a dialog or menu, a Details section, Details, History, the picked flight, compare, 3D"],
];
export const shortcuts = () => SHORTCUT_ROWS.filter(([, , feature]) => !feature || has(feature)).map(([k, a]) => [k, a]);

// Help (R9.1): read the map (three lines), the full key, the words used here, the keyboard. On the
// guide page (`page`) the words and the keyboard fold (one tap in) and the Wall's own shortcut
// switch is left out.
export function helpContent(enabled, { page = false } = {}) {
  const sw = (id, cls) => icon(id, `sw ${cls}`);
  const fold = (head, ...body) => (page
    ? el("details", { class: "more guide__fold" }, el("summary", {}, head), ...body)
    : [head, ...body]);
  const keyRow = (s, label, sub) => el("li", {}, s, el("span", {}, el("strong", { text: label }), sub ? el("span", { class: "key__sub", text: ` · ${sub}` }) : null));
  const codes = ["GREEN", "YELLOW", "ORANGE", "RED", "UNKNOWN"].map((c) => icon("i-eruption", "icon", `var(--c-code-${c.toLowerCase()})`));
  const { code } = airline();
  return el("div", { class: "help" },
    el("h3", { id: "help-read", class: "help__h", tabindex: "-1", text: "Read the map" }),
    el("ol", { class: "help__steps" },
      el("li", {}, sw("lg-area-official", "sw--official"), el("span", { text: "Pink: official ash area, binding." })),
      el("li", {}, sw("lg-area-tephra", "sw--tephra"), el("span", { text: "Amber dashes: TEPHRA's estimate, never smaller than the official area." })),
      el("li", {}, sw("i-aircraft", "sw--exposed"), el("span", { text: `Amber planes: ${code} flights heading in.` }))),
    el("h3", { id: "help-key", class: "help__h", text: "Full map key" }),
    el("ul", { class: "key__rows help__key" },
      keyRow(sw("lg-area-official", "sw--official"), "Official ash area", "binding"),
      keyRow(sw("lg-area-forecast", "sw--official"), "Official forecast area (+6, +12, +18 h)", "dashed"),
      keyRow(sw("lg-area-tephra", "sw--tephra"), "TEPHRA's estimate", "the amber dashed line"),
      keyRow(sw("lg-area-hatch", "sw--tephra"), "Where TEPHRA widened the area", null),
      keyRow(sw("lg-area-crew", "sw--crew"), "Crew report caution area, with a pin at the report", "operator policy A, not a VAA or SIGMET, drawn beneath the official area"),
      keyRow(sw("i-aircraft", "sw--exposed"), `${code} flight in or heading in`, null),
      keyRow(sw("lg-flight-group", "sw--exposed"), `Six or more ${code} flights close together`, "the badge is the count, click to zoom in"),
      keyRow(sw("i-aircraft", "sw--crew"), `${code} flight on a crew report's route`, "when TEPHRA's area does not reach it"),
      keyRow(sw("i-aircraft", "sw--aircraft"), otherAircraft(), null),
      keyRow(sw("lg-route", "sw--route"), "Route (origin to destination)", "the callsign's usual route (VRS standing data), not the filed flight plan. The small tags at its ends are the airport codes"),
      keyRow(sw("lg-reroute", "sw--reroute"), "Suggested reroute", null),
      keyRow(sw("st-closed", "sw--closed"), "Closed airport", "in TEPHRA's airport plan, dashed: its closure radius"),
      keyRow(sw("lg-arrow-official", "sw--official"), "Official movement", null),
      keyRow(sw("lg-arrow-observer", "sw--observer"), "Observatory's reported drift", null),
      keyRow(sw("lg-satbox", "sw--sat"), "Box marked on the satellite picture", "Read by Satellite reader · supporting only"),
      el("li", { class: "help__codes" }, el("span", { class: "codes" }, ...codes), el("span", { text: "Alert colour: green, yellow, orange, red. Grey: not given" }))),
    el("p", { class: "muted", text: "FIR and VAAC lines are approximate. Z is UTC." }),
    fold(el("h3", { id: "help-words", class: "help__h", text: "Words used here" }),
      el("dl", { class: "help__glossary" }, ...GLOSSARY.flatMap(([term, meaning]) => [el("dt", { text: term }), el("dd", { text: meaning })]))),
    fold(el("h3", { id: "help-keys", class: "help__h", text: "Keyboard, on the Wall" }),
      el("table", { class: "table" },
        el("caption", { class: "sr-only", text: "Keyboard shortcuts" }),
        el("thead", {}, el("tr", {}, el("th", { scope: "col", text: "Key" }), el("th", { scope: "col", text: "Action" }))),
        el("tbody", {}, ...shortcuts().map(([k, a]) => el("tr", {}, el("td", {}, ...k.split(" ").map((x) => el("kbd", { text: x }))), el("td", { text: a }))))),
      el("p", { class: "muted", text: "Shortcuts work outside text fields. Arrows pan, plus and minus zoom." })),
    page ? null : el("label", { class: "opt" },
      el("input", { type: "checkbox", dataset: { act: "shortcuts-toggle" }, checked: enabled ? true : null }),
      el("span", { text: "Single-key shortcuts on" })));
}

const CREDITS = [
  ["OpenFreeMap", "Dark basemap style, vector tiles, Noto Sans glyphs", "OpenFreeMap © OpenMapTiles · Data © OpenStreetMap contributors (ODbL 1.0)"],
  ["Mapterhorn", "Terrain tiles for hillshade (Copernicus GLO-30 DEM over Indonesia and the Philippines)", "© Mapterhorn"],
  ["NASA GIBS", "Himawari-9 infrared, visible and Air Mass tiles, TROPOMI SO2 (context only)", "Imagery: NASA GIBS · Himawari-9 data: JMA via NOAA · Contains modified Copernicus Sentinel data 2026"],
  ["adsb.lol", "Aircraft positions", "Aircraft: adsb.lol (ODbL 1.0)"],
  ["NOAA/NWS Aviation Weather Center", "FIR and VAAC boundaries (approximate), VA SIGMETs", "Public domain"],
  ["Natural Earth", "Offline coastline fallback", "Made with Natural Earth (public domain)"],
  ["OurAirports", "Navaids", "Public domain"],
  ["Open-Meteo", "Winds", "Weather data by Open-Meteo.com (CC BY 4.0)"],
  ["MapLibre GL JS 4.7.1, maplibre-gl-compare 0.5.0", "Map rendering, swipe compare", "BSD-3-Clause, ISC"],
  ["IBM Plex Sans and Mono", "Interface type", "SIL Open Font License 1.1"],
  ["Lucide, Material Symbols", "Icons, and the aircraft glyph", "ISC / MIT, Apache License 2.0"],
  ["Feed content", "SIGMETs, advisories and observatory notices", "Credited on each card: BMKG, Tokyo and Darwin VAAC, PVMBG; relays by NWS and IEM"],
];

// The credits and the acknowledgement: inside About in the demo, their own fold on the Guide.
export function creditsContent({ heading = true } = {}) {
  return el("div", { class: "about__credits" },
    heading ? el("h3", { id: "about-credits", class: "help__h", tabindex: "-1", text: "Credits" }) : null,
    el("table", { class: "table" },
      el("caption", { class: "sr-only", text: "Credits" }),
      el("thead", {}, el("tr", {}, ...["Source", "Used for", "Credit"].map((h) => el("th", { scope: "col", text: h })))),
      el("tbody", {}, ...CREDITS.map(([a, b, c]) => el("tr", {}, el("th", { scope: "row", text: a }), el("td", { text: b }), el("td", { text: c }))))),
    el("p", { class: "muted" }, el("a", { href: "/static/THIRD_PARTY.md", text: "Full licence inventory" }), ": every asset and service the pages load, with its licence."),
    el("h3", { class: "help__h", text: "Acknowledgement" }),
    el("p", { text: "We acknowledge the use of imagery provided by services from NASA's Global Imagery Browse Services (GIBS), part of NASA's Earth Science Data and Information System (ESDIS). Himawari-9 data: JMA via NOAA. No source endorses TEPHRA." }));
}

// About (R9.2): the AI line, the replay, the safety limits (the one home of each honesty sentence:
// decision support only, the fictional airline, nothing sent, REPLAY), then the credits. On the
// guide page (`page`) the safety limits carry the #what-is-real anchor, the credits are their own
// fold (guide.js) and its links go to the demo and to the guide's own sections.
export function aboutContent(state, { page = false } = {}) {
  const replay = state?.mode === "REPLAY" ? state.replay : null;
  const own = state?.airline?.fictional === false ? state.airline : null;
  return el("div", { class: "about" },
    // the About disclosure (docs/UI-AI-QUIET.md 8.4): one of the few places that say "AI"
    el("p", { text: "TEPHRA Assistant is an AI assistant. It reads feeds and drafts text. Code does every number and safety rule. You approve everything." }),
    replay ? el("p", { class: "about__replay" }, el("strong", { text: `${replay.banner} · not live. ` }), el("span", { text: `Case: ${replay.label}` })) : null,
    el("h3", { id: page ? "what-is-real" : null, class: "help__h", tabindex: page ? "-1" : null, text: "Safety limits" }),
    el("ul", { class: "about__list" },
      el("li", { text: "Decision support only. Not for operational use." }),
      el("li", { text: own ? `This TEPHRA checks only ${own.name}'s own flights (${own.code}), each named by its callsign, schedule or registration.` : replay?.synthetic ? "Ring of Fire Air (RFA) is a fictional airline. In this demo replay its flight numbers stand for invented aircraft." : "Ring of Fire Air (RFA) is a fictional airline. RFA flight numbers are proxies for real aircraft." }),
      el("li", { text: "Approved text goes only to TEPHRA's own outbound queue. Nothing is sent to an aircraft or any real system." }),
      el("li", { text: replay?.synthetic ? "This REPLAY is synthetic demo data: real volcanoes, airports and routes, with invented reports, weather and aircraft. Nothing in it happened. It is labelled as such for the whole session." : "REPLAY shows recorded real feeds, labelled as such for the whole session." }),
      el("li", { text: "TEPHRA's estimate is an estimate, never a forecast. The official reports are binding." }),
      el("li", { text: "Satellite, SO2 and BTD layers are context only, never ash detection. TEPHRA does not model gases." })),
    el("p", {}, page ? el("a", { class: "honesty__about", href: "/demo#track-record", text: "Track record ›" }) : el("button", { type: "button", class: "honesty__about", dataset: { act: "details-open", sec: "proof" }, text: "Track record ›" }), " How TEPHRA's estimate scored against later official areas."),
    page ? null : creditsContent(),
    page ? null : el("h3", { class: "help__h", text: "Operator policy" }),
    page ? null : el("p", {},
      el("button", { type: "button", class: "honesty__about", "aria-haspopup": "dialog", dataset: { act: "policy" }, text: "Open the operator policy" }),
      " (illustrative): every margin, minimum and threshold TEPHRA applies, with its reason."),
    page ? null : el("h3", { class: "help__h", text: "Help" }),
    page ? null : el("p", {},
      el("button", { type: "button", class: "honesty__about", "aria-haspopup": "dialog", dataset: { act: "help" }, text: "Open Help" }),
      ": how to read this screen, the words used and every keyboard shortcut (or press ?)."));
}
