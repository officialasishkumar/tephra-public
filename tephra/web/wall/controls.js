// Static-ish Wall controls (docs/UI-REDESIGN.md R8.3, R9): Details › Map layers, 3D and compare,
// the Help dialog (read the map, the full key, the words used, the keyboard) and the About dialog.
// Built with el(); no HTML strings.

import { el, icon } from "./util.js";
import { ATTRIBUTION } from "./panels.js";
import { GLOSSARY, GASES_SCOPE } from "./glossary.js";

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
  const group = (title, ...kids) => el("fieldset", { class: "opts" }, el("legend", { class: "opts__legend", text: title }), ...kids);
  const more = el("details", { class: "more", open: ui.layersMore ? true : null, dataset: { k: "layers-more", act: "layers-more" } },
    el("summary", { text: "Satellite pictures, 3D and compare" }),
    group("Satellite picture (context only, never ash detection)",
      radio("sat", "off", "Off", ui.sat === "off"),
      radio("sat", "ir", "Infrared", ui.sat === "ir", "context only"),
      radio("sat", "vis", "Visible", ui.sat === "vis", "context only, daylight"),
      radio("sat", "airmass", "Air mass", ui.sat === "airmass", "context only"),
      el("button", { type: "button", class: "chip-btn", dataset: { tool: "sat", focus: "tool-sat" }, "aria-pressed": ui.sat !== "off" ? "true" : "false", "aria-keyshortcuts": "I", title: "Next satellite picture (I)" }, "Next picture: ", el("span", { id: "sat-state", text: SAT_WORD[ui.sat] })),
      check("so2", "SO2 (TROPOMI, daily)", ui.so2, `context only · ${GASES_SCOPE}`),
      check("btd", "Split-window BTD", ui.btd, "an indicator, not ash detection")),
    group("View",
      el("div", { class: "seg", role: "group", "aria-label": "View" },
        el("button", { type: "button", dataset: { act: "view-2d", focus: "view-2d" }, "aria-pressed": ui.d3 ? "false" : "true", text: "2D" }),
        el("button", { type: "button", dataset: { tool: "3d", focus: "tool-3d" }, "aria-pressed": ui.d3 ? "true" : "false", "aria-keyshortcuts": "D", title: "3D view, heights exaggerated six times (D)", text: "3D" })),
      phone ? el("p", { class: "opt__hint", text: "Compare is not offered on a phone." })
        : el("button", { type: "button", class: "chip-btn", dataset: { tool: "compare", focus: "tool-compare" }, "aria-pressed": ui.compare ? "true" : "false", "aria-keyshortcuts": "S", title: "Swipe compare (S)" }, icon("i-swipe"), "Compare: official only vs with TEPHRA")));
  box.replaceChildren(
    el("p", { class: "dsum", text: layersStatus(ui) }),
    group("On the map",
      check("official", "Official ash area", true, "always on · binding", true),
      check("tephra", "TEPHRA's estimate", L.tephra, "never smaller than official"),
      check("aircraft", "Aircraft", L.aircraft),
      check("acLabels", "Other aircraft labels", L.acLabels, "from zoom 7.5"),
      check("paths", "Flight paths into the area", L.paths),
      check("reroutes", "Suggested reroutes", L.reroutes, "computed by code around TEPHRA's estimate"),
      check("satboxes", "Satellite boxes", L.satboxes, "marked on the picture · supporting only"),
      check("rose", "Disagreement arrows", L.rose, "the directions at the vent"),
      check("context", "FIR and VAAC lines", L.context, "approximate"),
      check("navaids", "Navaids", L.navaids, "from zoom 8"),
      check("terrain", "Terrain shading", L.terrain, "Mapterhorn hillshade; sea tiles are absent")),
    el("button", { type: "button", class: "link-btn", dataset: { tool: "levels", focus: "tool-levels" }, "aria-keyshortcuts": "H", text: "Height filter ›" }),
    more);
}

// Keyboard (R16). Every shortcut also has a visible control.
export const SHORTCUTS = [
  ["1 2 3", "Choose an area"],
  ["[ ]", "Previous / next volcano; the area follows"],
  ["F", "Fit the selected volcano"],
  ["D", "3D on/off"],
  ["S", "Compare on/off (not on a phone)"],
  ["C", "Sources side by side (raw texts)"],
  ["I", "Satellite picture: off, infrared, visible, air mass"],
  ["O", "SO2 on/off"],
  ["B", "BTD indicator on/off"],
  ["L", "Details › Map layers (again: close)"],
  ["T", "Details › How TEPHRA decided"],
  ["H", "Details › Height filter"],
  ["P", "Presentation layout for recording (keeps Details closed)"],
  ["?", "This help"],
  ["Esc", "Close a dialog or menu; a Details section, then Details; History; the picked flight; compare; 3D"],
];

// Help (R9.1): read the map in 3 steps, the full key, the words used here, the keyboard.
export function helpContent(enabled) {
  const sw = (id, cls) => icon(id, `sw ${cls}`);
  const keyRow = (s, label, sub) => el("li", {}, s, el("span", {}, el("strong", { text: label }), sub ? el("span", { class: "key__sub", text: ` · ${sub}` }) : null));
  const codes = ["GREEN", "YELLOW", "ORANGE", "RED", "UNKNOWN"].map((c) => icon("i-eruption", "icon", `var(--c-code-${c.toLowerCase()})`));
  return el("div", { class: "help" },
    el("h3", { id: "help-read", class: "help__h", tabindex: "-1", text: "Read the map in 3 steps" }),
    el("ol", { class: "help__steps" },
      el("li", {}, sw("lg-area-official", "sw--official"), el("span", { text: "Pink = the official ash area. It is binding." })),
      el("li", {}, sw("lg-area-tephra", "sw--tephra"), el("span", { text: "Amber dashes = TEPHRA's estimate. It is never smaller than the official area." })),
      el("li", {}, sw("i-aircraft", "sw--exposed"), el("span", { text: "Amber planes = flights of RFA, our fictional airline, in or heading into it. A person approves every advisory on the Desk." }))),
    el("ul", { class: "help__list" },
      el("li", { text: "The story on the left says what is happening at the selected volcano. Details holds everything else: the sources, the timeline, how TEPHRA decided, the AI helpers and the data feeds." }),
      el("li", { text: "Nothing is sent to an aircraft or to any real system." }),
      el("li", { text: "REPLAY means the data was recorded or reconstructed earlier; it is not live." }),
      el("li", { text: "Times ending in Z are UTC." })),
    el("h3", { id: "help-key", class: "help__h", text: "Full map key" }),
    el("ul", { class: "key__rows help__key" },
      keyRow(sw("lg-area-official", "sw--official"), "Official ash area", "binding"),
      keyRow(sw("lg-area-forecast", "sw--official"), "Official forecast area (+6, +12, +18 h)", "dashed"),
      keyRow(sw("lg-area-tephra", "sw--tephra"), "TEPHRA's estimate", "never smaller than official"),
      keyRow(sw("lg-area-hatch", "sw--tephra"), "Where TEPHRA widened the area", null),
      keyRow(sw("i-aircraft", "sw--exposed"), "RFA flight in or heading in", "RFA is a fictional airline"),
      keyRow(sw("i-aircraft", "sw--aircraft"), "Other aircraft (not RFA)", null),
      keyRow(sw("lg-reroute", "sw--reroute"), "Suggested reroute", null),
      keyRow(sw("lg-arrow-official", "sw--official"), "Official movement", null),
      keyRow(sw("lg-arrow-observer", "sw--observer"), "Observatory's reported drift", null),
      keyRow(sw("lg-satbox", "sw--sat"), "Box marked on the satellite picture", "supporting only"),
      el("li", { class: "help__codes" }, el("span", { class: "codes" }, ...codes), el("span", { text: "Alert colour: green, yellow, orange, red; grey = not given" }))),
    el("p", { class: "muted", text: "FIR and VAAC lines are approximate. Times ending in Z are UTC. Satellite, SO2 and BTD layers are context only, never ash detection." }),
    el("h3", { id: "help-words", class: "help__h", text: "Words used here" }),
    el("dl", { class: "help__glossary" }, ...GLOSSARY.flatMap(([term, meaning]) => [el("dt", { text: term }), el("dd", { text: meaning })])),
    el("h3", { id: "help-keys", class: "help__h", text: "Keyboard" }),
    el("table", { class: "table" },
      el("caption", { class: "sr-only", text: "Keyboard shortcuts" }),
      el("thead", {}, el("tr", {}, el("th", { scope: "col", text: "Key" }), el("th", { scope: "col", text: "Action" }))),
      el("tbody", {}, ...SHORTCUTS.map(([k, a]) => el("tr", {}, el("td", {}, ...k.split(" ").map((x) => el("kbd", { text: x }))), el("td", { text: a }))))),
    el("p", { class: "muted", text: "Shortcuts work when focus is not in a text field and no modifier key is held. Every shortcut also has a visible control. On the map: arrow keys pan, plus and minus zoom." }),
    el("label", { class: "opt" },
      el("input", { type: "checkbox", dataset: { act: "shortcuts-toggle" }, checked: enabled ? true : null }),
      el("span", { text: "Single-key shortcuts on" })));
}

const CREDITS = [
  ["OpenFreeMap", "Dark basemap style, vector tiles, Noto Sans glyphs", "OpenFreeMap © OpenMapTiles · Data © OpenStreetMap contributors (ODbL 1.0)"],
  ["Mapterhorn", "Terrain tiles for hillshade (Copernicus GLO-30 DEM over Indonesia and the Philippines)", "© Mapterhorn"],
  ["NASA GIBS", "Himawari-9 infrared, visible and Air Mass tiles; TROPOMI SO2 (context only)", "Imagery: NASA GIBS · Himawari-9 data: JMA via NOAA · Contains modified Copernicus Sentinel data 2026"],
  ["adsb.lol", "Aircraft positions", "Aircraft: adsb.lol (ODbL 1.0)"],
  ["NOAA/NWS Aviation Weather Center", "FIR and VAAC boundaries (approximate); VA SIGMETs", "Public domain"],
  ["Natural Earth", "Offline coastline fallback", "Made with Natural Earth (public domain)"],
  ["OurAirports", "Navaids", "Public domain"],
  ["Open-Meteo", "Winds", "Weather data by Open-Meteo.com (CC BY 4.0)"],
  ["MapLibre GL JS 4.7.1, maplibre-gl-compare 0.5.0", "Map rendering, swipe compare", "BSD-3-Clause, ISC"],
  ["IBM Plex Sans and Mono", "Interface type", "SIL Open Font License 1.1"],
  ["Lucide, Material Symbols", "Icons; the aircraft glyph", "ISC / MIT; Apache License 2.0"],
];

// About (R9.2): what TEPHRA is, the safety limits, the credits, the acknowledgement.
export function aboutContent(state, attribution = ATTRIBUTION) {
  const replay = state?.mode === "REPLAY" ? state.replay : null;
  return el("div", { class: "about" },
    el("h3", { class: "help__h", text: "What TEPHRA is" }),
    el("p", { text: "TEPHRA reads the official volcanic-ash reports (SIGMET, VAA, VONA), shows where they disagree, and draws an estimate of the ash area that is never smaller than the official one. Code works out which flights of a fictional airline would enter that area and drafts an advisory for each. A human dispatcher approves or rejects every advisory on the Desk." }),
    replay ? el("p", { class: "about__replay" }, el("strong", { text: `${replay.banner} · not live. ` }), el("span", { text: `Case: ${replay.label}` })) : null,
    el("h3", { class: "help__h", text: "Safety limits" }),
    el("ul", { class: "about__list" },
      el("li", { text: "Decision support only. Not for operational use." }),
      el("li", { text: "Ring of Fire Air (RFA) is a fictional airline. RFA flight numbers are proxies for real aircraft." }),
      el("li", { text: "Approved text goes only to TEPHRA's own outbound queue. Nothing is sent to an aircraft or any real system." }),
      el("li", { text: "REPLAY shows recorded real feeds, labelled as such for the whole session." }),
      el("li", { text: "TEPHRA's estimate is an estimate, never a forecast. The official reports are binding." }),
      el("li", { text: "Satellite and SO2 layers are context only, never ash detection." }),
      el("li", { text: GASES_SCOPE })),
    el("p", {}, el("button", { type: "button", class: "honesty__about", dataset: { act: "details-open", sec: "proof" }, text: "Track record ›" }), " How TEPHRA's estimate scored against later official areas."),
    el("h3", { id: "about-credits", class: "help__h", tabindex: "-1", text: "Credits" }),
    el("table", { class: "table" },
      el("caption", { class: "sr-only", text: "Credits" }),
      el("thead", {}, el("tr", {}, ...["Source", "Used for", "Credit"].map((h) => el("th", { scope: "col", text: h })))),
      el("tbody", {}, ...CREDITS.map(([a, b, c]) => el("tr", {}, el("th", { scope: "row", text: a }), el("td", { text: b }), el("td", { text: c }))))),
    el("p", { class: "about__attrib", text: `On screen: ${attribution}` }),
    el("h3", { class: "help__h", text: "Acknowledgement" }),
    el("p", { text: "We acknowledge the use of imagery provided by services from NASA's Global Imagery Browse Services (GIBS), part of NASA's Earth Science Data and Information System (ESDIS). Himawari-9 data: JMA via NOAA. No source endorses TEPHRA." }),
    el("h3", { class: "help__h", text: "Operator policy" }),
    el("p", {},
      el("button", { type: "button", class: "honesty__about", "aria-haspopup": "dialog", dataset: { act: "policy" }, text: "Open the operator policy" }),
      " (illustrative): every margin, minimum and threshold TEPHRA applies, with its reason."),
    el("h3", { class: "help__h", text: "Help" }),
    el("p", {},
      el("button", { type: "button", class: "honesty__about", "aria-haspopup": "dialog", dataset: { act: "help" }, text: "Open Help" }),
      ": how to read this screen, the words used and every keyboard shortcut (or press ?)."));
}
