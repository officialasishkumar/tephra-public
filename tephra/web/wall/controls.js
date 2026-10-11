// Static-ish Wall controls: the Layers popover (docs/UI-DESIGN.md 7.7), the keyboard help
// (section 9) and the About dialog (7.3). Built with el(); no HTML strings.

import { el, icon } from "./util.js";
import { ATTRIBUTION } from "./panels.js";

const check = (key, label, on, hint, disabled = false) =>
  el("label", { class: `opt${disabled ? " opt--locked" : ""}` },
    el("input", { type: "checkbox", dataset: { layer: key, focus: `layer-${key}` }, checked: on ? true : null, disabled: disabled ? true : null }),
    el("span", { class: "opt__text" }, el("span", { text: label }), hint ? el("span", { class: "opt__hint", text: hint }) : null));

const radio = (name, value, label, on, hint) =>
  el("label", { class: "opt" },
    el("input", { type: "radio", name, value, dataset: { radio: name, focus: `${name}-${value}` }, checked: on ? true : null }),
    el("span", { class: "opt__text" }, el("span", { text: label }), hint ? el("span", { class: "opt__hint", text: hint }) : null));

export function renderLayers(ui) {
  const box = document.getElementById("layers-pop");
  const L = ui.layers;
  const group = (title, ...kids) => el("fieldset", { class: "opts" }, el("legend", { class: "caps", text: title }), ...kids);
  box.replaceChildren(
    el("div", { class: "layers-pop__head" },
      el("h2", { class: "caps", text: "Layers" }),
      el("button", { type: "button", class: "icon-btn", dataset: { act: "layers-close" }, "aria-label": "Close layers" }, icon("i-x"))),
    el("div", { class: "layers-pop__body" },
      group("Hazard",
        check("official", "Official ash area", true, "always on · binding", true),
        el("div", { class: "opts__sub", role: "radiogroup", "aria-label": "Official forecast steps" },
          el("span", { class: "opts__label", text: "Official forecast steps" }),
          el("div", { class: "opts__row" }, ...[["now", "Now"], ["f6", "+6 h"], ["f12", "+12 h"], ["f18", "+18 h"], ["all", "All"]].map(([k, t]) => radio("steps", k, t, ui.steps === k)))),
        check("tephra", "TEPHRA cautious area", L.tephra, "an estimate, never smaller than official"),
        check("rose", "Disagreement markers", L.rose, "direction arrows at the vent")),
      group("Traffic",
        check("aircraft", "Aircraft", L.aircraft),
        check("paths", "Exposure paths", L.paths),
        check("reroutes", "Reroutes", L.reroutes, "code-computed around the cautious area"),
        check("satboxes", "Satellite check boxes", L.satboxes, "drawn by the AI · supporting only"),
        check("acLabels", "Other aircraft labels", L.acLabels, "from zoom 7.5")),
      group("Context",
        check("context", "FIR and VAAC lines", L.context, "approximate"),
        check("navaids", "Navaids", L.navaids, "from zoom 8"),
        check("terrain", "Terrain shading", L.terrain, "Mapterhorn hillshade; sea tiles are absent")),
      group("Satellite context",
        radio("sat", "off", "Off", ui.sat === "off"),
        radio("sat", "ir", "Infrared", ui.sat === "ir", "context only"),
        radio("sat", "vis", "Visible", ui.sat === "vis", "context only, daylight"),
        radio("sat", "airmass", "Air mass", ui.sat === "airmass", "context only"),
        check("so2", "SO2 column (TROPOMI, daily)", ui.so2, "SO2 is not ash · context only"),
        check("btd", "Split-window BTD", ui.btd, "an indicator, not ash detection")),
      group("Levels",
        el("div", { class: "opts__row" },
          ...[["all", "All"], ["hazard", "Hazard"], ["low", "≤FL180"], ["high", "≥FL180"]].map(([k, t]) =>
            el("button", { type: "button", class: "chip-btn", dataset: { act: "level-preset", preset: k, focus: `lp-${k}` }, text: t }))))));
}

export const SHORTCUTS = [
  ["1 2 3", "Region presets"],
  ["[ ]", "Previous / next active volcano"],
  ["F", "Frame the selected volcano"],
  ["D", "3D on/off"],
  ["S", "Swipe compare on/off"],
  ["C", "Sources side by side (raw texts)"],
  ["I", "Satellite context: off, infrared, visible, air mass"],
  ["O", "SO2 context on/off"],
  ["B", "BTD indicator on/off"],
  ["L", "Legend and layers"],
  ["T", "Expand or collapse the reasoning trace"],
  ["P", "Presentation layout for recording: folds the legend, gives the map more room"],
  ["H", "Focus the level filter"],
  ["?", "This help"],
  ["Esc", "Close a dialog, popup or popover; leave compare or 3D"],
];

export function helpContent(enabled) {
  return el("div", { class: "help" },
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

export function aboutContent() {
  return el("div", { class: "about" },
    el("p", { text: "TEPHRA reads the official volcanic-ash products (SIGMET, VAA, VONA), shows where they disagree, and proposes a cautious area that is never smaller than the official one. Code works out which flights of a fictional airline would enter that area and drafts an advisory for each. A human dispatcher approves or rejects every advisory on the Desk." }),
    el("ul", { class: "about__list" },
      el("li", { text: "Decision support only. Not for operational use." }),
      el("li", { text: "Ring of Fire Air (RFA) is a fictional airline. RFA flight numbers are proxies for real aircraft." }),
      el("li", { text: "Approved text goes only to TEPHRA's own outbound queue. Nothing is sent to an aircraft or any real system." }),
      el("li", { text: "REPLAY shows recorded real feeds, labelled as such for the whole session." }),
      el("li", { text: "TEPHRA's cautious area is an estimate, never a forecast. The official products are binding." }),
      el("li", { text: "Satellite and SO2 layers are context only, never ash detection." })),
    el("h3", { class: "caps", text: "Acknowledgement" }),
    el("p", { text: "We acknowledge the use of imagery provided by services from NASA's Global Imagery Browse Services (GIBS), part of NASA's Earth Science Data and Information System (ESDIS). Himawari-9 data: JMA via NOAA. No source endorses TEPHRA." }),
    el("h3", { class: "caps", text: "Credits" }),
    el("table", { class: "table" },
      el("caption", { class: "sr-only", text: "Credits" }),
      el("thead", {}, el("tr", {}, ...["Source", "Used for", "Credit"].map((h) => el("th", { scope: "col", text: h })))),
      el("tbody", {}, ...CREDITS.map(([a, b, c]) => el("tr", {}, el("th", { scope: "row", text: a }), el("td", { text: b }), el("td", { text: c }))))),
    el("p", { class: "muted", text: `On screen: ${ATTRIBUTION}` }),
    el("h3", { class: "caps", text: "Operator policy" }),
    el("p", {},
      el("button", { type: "button", class: "honesty__about", "aria-haspopup": "dialog", dataset: { act: "policy" }, text: "Open the operator policy" }),
      " (illustrative): every margin, minimum and threshold TEPHRA applies, with its reason."),
    el("h3", { class: "caps", text: "Keyboard" }),
    el("p", { class: "muted", text: "Press ? for every shortcut." }));
}
