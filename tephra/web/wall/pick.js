// The map's card (UI-DESIGN 7.23): select a plane, a volcano or an airport on the Wall map and one
// small card opens where it was selected, as a flight tracker does, with only what a reader needs
// (who, where, what it means here) and one link to the full Details section. The card follows the
// map. Every string is code-written from the snapshot and goes in through el() (textContent).

import { el, icon, fl, hhmmz, ms } from "./util.js";

const CODE_WORD = { RED: "Red", ORANGE: "Orange", YELLOW: "Yellow", GREEN: "Green", UNKNOWN: "Not given" };
const STATUS_WORD = { DRAFT: "Advisory waiting on the Desk", APPROVED: "Advisory approved", REJECTED: "Advisory rejected", EDITED: "Advisory approved (edited)" };

function card({ title, sub, lines, action }) {
  return el("div", { class: "mcard", role: "dialog", "aria-label": title },
    el("button", { type: "button", class: "mcard__x", "aria-label": "Close", dataset: { act: "card-close" } }, icon("i-x")),
    el("p", { class: "mcard__t" }, el("b", { text: title }), sub ? el("span", { class: "mcard__sub", text: sub }) : null),
    ...lines.filter(Boolean).map((l) => el("p", { class: `mcard__l${l.tone ? ` mcard__l--${l.tone}` : ""}`, text: l.text })),
    action ? el("button", { type: "button", class: "link-btn mcard__go", dataset: { act: action.act, sec: action.sec || null }, text: action.text }) : null);
}

// p: AircraftFeatureProps; adv: its newest advisory that is not superseded, if any
export function planeCard(p, adv) {
  const where = !p.exposed ? null
    : p.minutes_to_entry > 0 ? { text: `Enters TEPHRA's ash area in ${p.minutes_to_entry} min`, tone: "caution" }
      : { text: "Inside TEPHRA's ash area", tone: "serious" };
  const decided = adv && adv.decided_at ? ` ${hhmmz(ms(adv.decided_at))}` : "";
  return card({
    title: p.proxy_flight || p.callsign || p.hex,
    sub: p.proxy_flight ? [p.callsign, p.type_icao].filter(Boolean).join(" · ") : "Not an RFA flight",
    lines: [
      { text: [p.alt_baro_ft != null ? fl(p.alt_baro_ft) : null, p.gs_kt != null ? `${Math.round(p.gs_kt)} kt` : null].filter(Boolean).join(" · ") || "Level not reported" },
      p.origin_icao && p.dest_icao ? { text: `${p.origin_icao} → ${p.dest_icao}` } : null,
      where,
      adv ? { text: `${STATUS_WORD[adv.status] || adv.status}${decided}` } : null,
    ],
    action: p.proxy_flight ? { text: "Flight details ›", act: "details-open", sec: "flight" } : null,
  });
}

// p: VolcanoFeatureProps; band: the official band now ({ top, base }) or null; n: RFA flights in or
// heading in
export function volcanoCard(p, band, n) {
  return card({
    title: p.name,
    sub: `Alert colour: ${CODE_WORD[p.color_code] || "Not given"}`,
    lines: [
      band ? { text: band.base > 0 ? `Ash ${fl(band.base)}–${fl(band.top)} in the official reports` : `Ash up to ${fl(band.top)} in the official reports` } : { text: "No official ash area now" },
      p.active ? { text: n ? `${n} RFA ${n === 1 ? "flight" : "flights"} in or heading in` : "No RFA flight in or heading in", tone: n ? "caution" : null } : null,
    ],
    action: p.active ? { text: "This ash area ›", act: "details-open", sec: "area" } : null,
  });
}

// p: the airport's catalogue props; closure: the airport plan's Closure for it, or null
export function airportCard(p, closure) {
  return card({
    title: [p.icao, p.iata].filter(Boolean).join(" · "),
    sub: p.name,
    lines: [
      closure ? { text: `Closed until ${hhmmz(ms(closure.end))}`, tone: "serious" } : { text: "Open: no closure in the airport plan" },
      closure?.summary ? { text: closure.summary } : null,
      p.longest_runway_m ? { text: `Longest runway ${Number(p.longest_runway_m).toLocaleString("en")} m` } : null,
    ],
    action: closure ? { text: "Airport plan ›", act: "details-open", sec: "recovery" } : null,
  });
}
