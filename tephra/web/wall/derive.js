// Everything the Wall computes from the snapshot (docs/UI-DESIGN.md section 13). Pure
// functions of the store and the view state: no model is called and no time, number or
// place is invented; labels are composed from fields.

import { band, compassDeg, fl, hhmmz, idTime, isNight, ms, inBbox, kmBetween } from "./util.js";

export const STEP_OF_LAYER = { SIGMET: "now", OBS: "now", "FCST+6H": "f6", "FCST+12H": "f12", "FCST+18H": "f18" };
export const SEV_RANK = { WARNING: 3, CAUTION: 2, INFO: 1 };
export const LEVEL_MAX = 55000;
const NON_OBS = new Set(["NOT_IDENTIFIABLE", "NOT_OBSERVED", "NIGHT_BLIND"]);
export { NON_OBS };

export function actionWords(a) {
  if (!a) return "";
  const f = (n) => `FL${String(n).padStart(3, "0")}`;
  switch (a.action) {
    case "HOLD": return a.hold_fl != null ? `HOLD ${f(a.hold_fl)}` : "HOLD";
    case "DIVERT": return a.alternate_icao ? `DIVERT ${a.alternate_icao}` : "DIVERT";
    case "CHANGE_LEVEL":
      return a.change_level_fl_min != null ? `CHANGE LEVEL ${f(a.change_level_fl_min)}–${f(a.change_level_fl_max)}` : "CHANGE LEVEL";
    default: return a.action || "";
  }
}
export const deciderName = (a) => (a?.decided_by || "").replace(/^desk:/, "");

export const worstSeverity = (sit) => Math.max(0, ...sit.discrepancies.map((d) => SEV_RANK[d.severity] || 0));

// Priority of volcanoes: exposed count, worst severity, discrepancy count, name.
export function sortSituations(list) {
  const prio = (s) => [s.exposed_count || 0, worstSeverity(s), s.discrepancies.length];
  return list.slice().sort((a, b) => {
    const pa = prio(a), pb = prio(b);
    for (let i = 0; i < 3; i++) if (pa[i] !== pb[i]) return pb[i] - pa[i];
    return a.volcano_name.localeCompare(b.volcano_name);
  });
}

export const levelIsAll = (lv) => lv.min <= 0 && lv.max >= LEVEL_MAX;

// Level-filter scale (8.4): SFC-FL180 takes the lower half of the track, FL180-FL550 the
// upper half, so low ash bands and the traffic climbing through them stay readable.
const LEVEL_KNEE = 18000;
export const levelFrac = (ft) => {
  const v = Math.min(Math.max(ft, 0), LEVEL_MAX);
  return v <= LEVEL_KNEE ? (v / LEVEL_KNEE) * 0.5 : 0.5 + ((v - LEVEL_KNEE) / (LEVEL_MAX - LEVEL_KNEE)) * 0.5;
};
export const levelFromFrac = (f) => {
  const c = Math.min(Math.max(f, 0), 1);
  return c <= 0.5 ? (c / 0.5) * LEVEL_KNEE : LEVEL_KNEE + ((c - 0.5) / 0.5) * (LEVEL_MAX - LEVEL_KNEE);
};

// The first region whose bbox contains the vent, else null ("All areas").
export function regionOfVent(state, vent) {
  if (!vent) return null;
  return (state.regions || []).find((r) => inBbox(vent, r.bbox))?.key || null;
}

// The view's derived data. `ui` holds the selection and view choices.
export function derive(store, ui, now) {
  const { state, snapshot: snap } = store;
  const sits = sortSituations(snap.situations || []);
  const vents = new Map();
  for (const f of snap.volcanoes?.features || []) vents.set(f.properties.id, f.geometry.coordinates);
  // The area (region) scope is derived on every render, never stored (UI-REDESIGN R2.1): the
  // region chip's count and the empty-region story come from the same list, so they cannot
  // disagree. With no area chosen ("All areas") every active volcano is in scope.
  const regionOf = (key) => (state.regions || []).find((r) => r.key === key) || null;
  const area = ui.region ? regionOf(ui.region) : null;
  const inRegion = area ? sits.filter((s) => vents.get(s.volcano_id) && inBbox(vents.get(s.volcano_id), area.bbox)) : sits;
  const selected = inRegion.some((s) => s.volcano_id === ui.selected) ? ui.selected : inRegion[0]?.volcano_id ?? null;
  // Active volcanoes come from one source, the server's active list plus any situation card, so
  // the "with ash" counts, the area picker and the story always agree (review 1, item 1). An
  // active volcano whose situation card has not arrived yet is "being read": until it arrives the
  // Wall says so and never claims "no ash" for its area.
  const activeIds = [...new Set([...(state.active_volcano_ids || []), ...sits.map((s) => s.volcano_id)])];
  const pendingIds = activeIds.filter((id) => !sits.some((s) => s.volcano_id === id));
  const inArea = (id, r) => !!vents.get(id) && inBbox(vents.get(id), r.bbox);
  const pendingInScope = area ? pendingIds.filter((id) => inArea(id, area)) : pendingIds;
  // Before the server's first tick finishes nothing has been read yet: also "being read".
  const reading = inRegion.length === 0 && (pendingInScope.length > 0 || !state.last_tick);
  const regionEmpty = !!area && inRegion.length === 0 && !reading;
  const sit = sits.find((s) => s.volcano_id === selected) || null;
  const lvAll = levelIsAll(ui.level);
  const outOfLevel = (p) => !lvAll && (p.top_ft < ui.level.min || p.base_ft > ui.level.max);

  // ---- official: step, validity, fill without double counting, fade
  // TEPHRA's cone contains every official polygon valid before the cone ends, forecasts
  // included; those forecast polygons are always drawn (dashed), so the cone's extent is
  // explained by an official shape on the map, never by TEPHRA alone (5.2).
  const coneEnd = new Map();
  for (const f of snap.cones?.features || []) if (f.properties.part === "cone") coneEnd.set(f.properties.volcano_id, ms(f.properties.valid_to));
  const latestSig = new Map();
  const official = (snap.official?.features || []).map((f) => {
    const p = f.properties;
    const step = STEP_OF_LAYER[p.layer] || "now";
    const vf = ms(p.valid_from), vt = ms(p.valid_to);
    const valid = vf <= now && now <= vt;
    const future = vf > now;
    const inCone = step !== "now" && future && coneEnd.has(p.volcano_id) && vf <= coneEnd.get(p.volcano_id);
    let show = valid || inCone;
    if (step !== "now" && (ui.steps === "all" || ui.steps === step)) show = valid || future;
    return { type: "Feature", geometry: f.geometry, properties: { ...p, step, valid, show, inCone, fill: false } };
  });
  for (const f of official) {
    const p = f.properties;
    if (!p.show || p.step !== "now" || p.kind !== "SIGMET") continue;
    const key = `${p.volcano_id}|${p.source_id.split(":")[1]}`;
    const prev = latestSig.get(key);
    if (!prev || ms(p.valid_from) > ms(prev.properties.valid_from)) latestSig.set(key, f);
  }
  const sigVolcanoes = new Set([...latestSig.keys()].map((k) => k.split("|")[0]));
  const latestSet = new Set(latestSig.values());
  let hiddenOfficial = 0;
  for (const f of official) {
    const p = f.properties;
    if (p.show && p.step === "now") p.fill = p.kind === "SIGMET" ? latestSet.has(f) : !sigVolcanoes.has(p.volcano_id);
    p.sel = p.volcano_id === selected;
    // other volcanoes' areas: 0.6 of the fill and 0.85 of the edge (R6.1); never switched off
    let fade = p.sel ? 1 : 0.6;
    let lfade = p.sel ? 1 : 0.85;
    if (ui.steps !== "now" && ui.steps !== "all" && p.step !== ui.steps) { fade *= 0.5; lfade *= 0.5; }
    if (outOfLevel(p)) { fade = 0.15; lfade = 0.15; if (p.show && p.sel) hiddenOfficial++; }
    p.fade = fade;
    p.lfade = lfade;
  }
  const firsWithSigmet = [...new Set(official.filter((f) => f.properties.kind === "SIGMET" && f.properties.valid).map((f) => f.properties.source_id.split(":")[1]))];

  // ---- TEPHRA cones
  const cones = (snap.cones?.features || []).map((f) => {
    const p = f.properties;
    const sel = p.volcano_id === selected;
    return { type: "Feature", geometry: f.geometry, properties: { ...p, sel, fade: outOfLevel(p) ? 0.15 : sel ? 1 : 0.45 } };
  });
  const coneOf = (vid) => cones.find((f) => f.properties.volcano_id === vid && f.properties.part === "cone") || null;
  const sectorOf = (vid) => cones.find((f) => f.properties.volcano_id === vid && f.properties.part === "sector") || null;

  // ---- advisories by flight
  const advByFlight = new Map();
  // the flight's current advisory: the newest one that has not been replaced
  for (const a of store.advisories) {
    const prev = advByFlight.get(a.flight_id);
    const better = !prev
      || (prev.status === "SUPERSEDED" && a.status !== "SUPERSEDED")
      || ((prev.status === "SUPERSEDED") === (a.status === "SUPERSEDED") && ms(a.updated_at) > ms(prev.updated_at));
    if (better) advByFlight.set(a.flight_id, a);
  }

  // ---- aircraft
  let hiddenFlights = 0;
  let selHiddenByLevel = false;
  const selHex = ui.selFlight?.hex || null;
  const aircraft = [];
  for (const f of snap.aircraft?.features || []) {
    const p = f.properties;
    const ageS = (now - ms(p.observed_at)) / 1000;
    const stale = ageS > 60;
    const inside = !!p.exposed && p.minutes_to_entry === 0;
    const known = p.alt_baro_ft != null;
    // An RFA flight a crew report flags but TEPHRA's area does not: drawn and listed as an RFA
    // flight in the crew colour (UI-DESIGN 5.7), never as "other aircraft" under its callsign.
    const crewOnly = !!p.crew_report && !p.exposed;
    if (!lvAll && known && !p.exposed && !crewOnly && (p.alt_baro_ft < ui.level.min || p.alt_baro_ft > ui.level.max)) {
      hiddenFlights++;
      if (p.hex === selHex) selHiddenByLevel = true;
      continue;
    }
    const lvl = known ? fl(p.alt_baro_ft) : "level unknown";
    const mins = Math.max(1, Math.round(ageS / 60));
    // Exposed planes keep the TEPHRA colour when their position is old; the age is a word
    // on its own line instead (5.3). Lines: id, entry and level, decision, age.
    const l2 = p.exposed ? (inside ? `INSIDE NOW · ${lvl}` : `${p.minutes_to_entry} MIN · ${lvl}`) : lvl;
    const adv = p.exposed ? advByFlight.get(`${p.hex}:${p.volcano_id}`) : null;
    const ok = adv && (adv.status === "APPROVED" || adv.status === "EDITED");
    const l3 = ok ? "✓ APPROVED" : adv && adv.status === "REJECTED" ? "× REJECTED" : "";
    aircraft.push({
      type: "Feature",
      id: f.id,
      geometry: f.geometry,
      properties: {
        ...p, stale, inside, ageS, sel_vid: selected || "", picked: p.hex === selHex, crew_only: crewOnly,
        l1: `${p.proxy_flight}${p.callsign ? ` · ${p.callsign}` : ""}`,
        l2, l3, l3ok: !!ok,
        l4: stale ? `position ${mins} min old` : "",
        short: `${p.callsign || p.hex} ${lvl}`,
        // One line on the map (R6.3); level, decision and position age are in Details › This flight.
        elabel: p.exposed ? `${p.proxy_flight} · ${inside ? "inside" : `in ${p.minutes_to_entry} min`}` : crewOnly ? `${p.proxy_flight} · crew report` : "",
      },
    });
  }
  // flights flagged only by a crew report, soonest into the crew area first
  const crewFlights = aircraft.filter((f) => f.properties.crew_only);
  const exposed = aircraft.filter((f) => f.properties.exposed).sort((a, b) => {
    const pa = a.properties, pb = b.properties;
    const sa = pa.volcano_id === selected, sb = pb.volcano_id === selected;
    if (sa !== sb) return sa ? -1 : 1;
    if (pa.inside !== pb.inside) return pa.inside ? -1 : 1;
    return (pa.minutes_to_entry ?? 999) - (pb.minutes_to_entry ?? 999);
  });

  // The aircraft the viewer picked on the map or in the flights dock (7.8). It stays picked
  // until cleared; when it is missing, `selHiddenByLevel` says whether the level filter hid it.
  const selFlight = selHex ? aircraft.find((f) => f.properties.hex === selHex) || null : null;

  // Usual routes (origin to destination, VRS standing data): the server draws them for the RFA
  // flights in or heading in; the picked flight's comes from /api/routes when it is not one of
  // them (wall.js fetches it into store.routeLines). Never for other aircraft, never guessed. A
  // line is keyed by its two airports in alphabetical order: both directions share it. While the
  // picked flight's line is drawn, the other lines step back (`dim`).
  const sp = selFlight?.properties;
  const selEnds = sp?.origin_icao && sp?.dest_icao && sp.origin_icao !== sp.dest_icao ? [sp.origin_icao, sp.dest_icao].sort() : null;
  const selRoute = selEnds ? selEnds.join("-") : null;
  const routeFeatures = [...(snap.routes?.features || [])];
  if (selRoute && !routeFeatures.some((f) => f.id === selRoute)) routeFeatures.push(...(store.routeLines?.get(selRoute)?.features || []));
  const pickedLine = !!selRoute && routeFeatures.some((f) => f.id === selRoute);
  const seenPorts = new Set();
  const routes = [];
  for (const f of routeFeatures) {
    const p = f.properties;
    if (p.feature === "airport") {
      if (seenPorts.has(f.id)) continue;
      seenPorts.add(f.id);
    }
    const sel = p.feature === "line" ? f.id === selRoute : pickedLine && selEnds.includes(p.icao);
    routes.push({ ...f, properties: { ...p, sel, dim: pickedLine && p.feature === "line" && !sel } });
  }
  // The picked flight's own line runs through its current position: departure airport to the
  // plane ("since departure", fainter) and the plane to its destination ("ahead"). The shared
  // airport-pair line stays beneath, dimmed, for the other flights on that pair. Both legs are
  // great circles, not the flown track or the filed plan.
  if (pickedLine && selFlight) {
    const at = (icao) => routes.find((f) => f.properties.feature === "airport" && f.properties.icao === icao)?.geometry.coordinates;
    const from = at(sp.origin_icao), to = at(sp.dest_icao), here = selFlight.geometry.coordinates;
    if (from && to) {
      for (const r of routes) if (r.id === selRoute) r.properties = { ...r.properties, sel: false, dim: true };
      routes.push({ type: "Feature", id: `${selRoute}#flown`, geometry: { type: "LineString", coordinates: greatCircle(from, here) }, properties: { feature: "line", sel: true, leg: "flown" } });
      routes.push({ type: "Feature", id: `${selRoute}#ahead`, geometry: { type: "LineString", coordinates: greatCircle(here, to) }, properties: { feature: "line", sel: true, leg: "ahead" } });
    }
  }

  // Forecast steps chosen on the timeline that have no official polygon for the selected
  // volcano in the current products (8.3). Only a note: no other step is drawn in their place.
  let stepsMissing = [];
  if (sit && ui.steps !== "now") {
    const want = ui.steps === "all" ? ["f6", "f12", "f18"] : [ui.steps];
    const has = new Set(official.filter((f) => f.properties.volcano_id === selected && f.properties.show).map((f) => f.properties.step));
    stepsMissing = want.filter((k) => !has.has(k));
    if (ui.steps === "all" && stepsMissing.length < want.length) stepsMissing = [];
  }

  const selVent = selected ? vents.get(selected) : null;
  const volcanoes = (snap.volcanoes?.features || []).map((f) => ({
    ...f,
    properties: {
      ...f.properties,
      sel: f.properties.id === selected,
      near_sel: !!selVent && f.properties.id !== selected && kmBetween(f.geometry.coordinates, selVent) < 25,
    },
  }));

  // ---- direction rose for the selected volcano (section 6)
  let rose = null;
  if (sit && vents.get(sit.volcano_id)) {
    const dir = sit.discrepancies.find((d) => d.kind === "DIRECTION_MISMATCH" && d.aspect === "direction");
    if (dir) {
      let offDeg = null, obsDeg = null, offVal = "", obsVal = "", obsTime = NaN;
      const offNames = [];
      for (const [sid, val] of Object.entries(dir.values)) {
        const deg = compassDeg(val);
        if (sid.startsWith("VONA:")) { obsDeg = deg; obsVal = val; obsTime = idTime(sid); }
        else {
          if (offDeg == null) { offDeg = deg; offVal = val; }
          offNames.push(sid.split(":")[0]);
        }
      }
      if (offDeg != null && obsDeg != null) {
        const vent = vents.get(sit.volcano_id);
        const probe = sit.discrepancies.some((d) => d.kind === "DIRECTION_MISMATCH" && d.aspect === "polygon");
        rose = {
          vent, offDeg, obsDeg, offVal, obsVal, obsTime,
          offNames: [...new Set(offNames)],
          magnitude: Math.round(dir.magnitude ?? 0),
          night: Number.isFinite(obsTime) && isNight(obsTime, vent[0]),
          probe,
        };
      }
    }
  }

  // ---- movement per volcano from the SIGMET (else VAA) card, for the label box
  const moveByVolcano = {};
  for (const s of sits) {
    const c = s.cards.find((x) => x.kind === "SIGMET" && !x.missing) || s.cards.find((x) => x.kind === "VAA" && !x.missing);
    if (c?.display_fields?.Movement) moveByVolcano[s.volcano_id] = c.display_fields.Movement;
  }

  // ---- region counts (active volcanoes inside each region bbox)
  const regionCounts = {};
  for (const r of state.regions || []) regionCounts[r.key] = activeIds.filter((id) => inArea(id, r)).length;

  if (regionEmpty && regionCounts[ui.region] > 0) console.error("region invariant");

  const crew = deriveCrew(snap.crew, new Set(sits.map((x) => x.volcano_id)));

  return {
    state, now, mode: state.mode, sits, inRegion, regionEmpty, reading, activeCount: activeIds.length, area, selected, sit, vents, official, cones, coneOf, sectorOf,
    hasReroutes: (snap.reroutes?.features || []).length > 0,
    rerouteKeys: new Set((snap.reroutes?.features || []).map((f) => f.properties.flight_id)),
    hasSatBoxes: (snap.satellite || []).some((r) => r.boxes?.length),
    aircraft, exposed, crewFlights, exposures: snap.exposures || { type: "FeatureCollection", features: [] },
    routes, selRoute, hasRouteLine: routes.some((f) => f.properties.feature === "line"),
    volcanoes, rose, moveByVolcano, firsWithSigmet, advByFlight, regionCounts,
    levelAll: lvAll, hiddenOfficial, hiddenFlights, selFlight, selHiddenByLevel, stepsMissing,
    overlays: snap.overlays || { btd: [], frames: [] },
    crew,
  };
}

// ---- crew reports of ash (UI-DESIGN 5.7, 7.20): the server's CrewPicture, as the Wall draws it.
// Every word comes from the server's code-written fields (state_label, age_text, place_text,
// summary, discrepancy); the Wall only joins them. A crew area is a flag layer: it never changes
// an official area, a count or a cone here.
export const crewBand = (r) => (r.level_from_fl === r.level_to_fl ? fl(r.level_from_fl * 100) : `${fl(r.level_from_fl * 100)}–${fl(r.level_to_fl * 100)}`);

function deriveCrew(pic, activeIds) {
  const reports = Array.isArray(pic?.reports) ? pic.reports : [];
  const flags = Array.isArray(pic?.flags) ? pic.flags : [];
  const byId = new Map(reports.map((v) => [v.report.id, v]));
  const drawn = reports.filter((v) => v.state === "ACTIVE" || v.state === "COVERED");
  const flagByHex = new Map(flags.map((f) => [f.hex, f]));
  // The map source: the server's area, pin and path features, with the pin's two label lines.
  // The map source: the server's area, pin and path features. A pin's label is one short line
  // ("Crew report · 47 min ago"); the full label, band and flight are in Details › Crew reports.
  const features = (pic?.features?.features || []).map((f) => {
    const p = f.properties || {};
    if (p.feature !== "pin") return f;
    const age = String(p.age_text || "").replace(/^reported /, "");
    const line1 = p.state === "COVERED" ? "Crew report · covered by official area" : `Crew report · ${age}`;
    return { ...f, properties: { ...p, line1 } };
  });
  return {
    label: pic?.label || "",
    reports,
    flags,
    byId,
    drawn,
    flagByHex,
    // a report belongs to a volcano's story when it names that volcano; one near no active
    // volcano is in the all-volcanoes summary and in Details › Crew reports, never in another
    // volcano's story
    homeless: (v) => !v.report.volcano_id || !activeIds.has(v.report.volcano_id),
    map: { type: "FeatureCollection", features },
  };
}

// Movement in plain words: "MOV SE 10KT" -> "moving SE at 10 kt". Text that does not match the
// known forms is returned as it is, never paraphrased (UI-REDESIGN R12.4).
export function plainMove(text) {
  const t = String(text || "").trim();
  if (!t) return "";
  const m = /^(?:MOV(?:ING)?\s+)?(NNE|ENE|ESE|SSE|SSW|WSW|WNW|NNW|NE|SE|SW|NW|N|E|S|W)\s*(?:AT\s*)?(\d+)\s*KT$/i.exec(t);
  if (m) return `moving ${m[1].toUpperCase()} at ${m[2]} kt`;
  if (/^STNR$/i.test(t)) return "not moving (STNR)";
  return t;
}

// Official label for one volcano (UI-REDESIGN R6.3). The selected volcano gets two lines,
// "Official ash area · SFC–FL500 · until 1045Z" and "moving SE at 10 kt" (when movement is given);
// every other volcano gets its name only. Product ids stay out of the map; they are listed in
// Details › This ash area. `products` keeps them for that section.
export function officialLabelText(D, vid) {
  const feats = D.official.filter((f) => f.properties.volcano_id === vid && f.properties.show && f.properties.step === "now" && f.properties.valid);
  if (!feats.length) return null;
  const sigs = feats.filter((f) => f.properties.kind === "SIGMET");
  // An office's latest SIGMET replaces its earlier ones: name only the latest per FIR.
  const latest = new Map();
  for (const f of sigs) {
    const fir = f.properties.source_id.split(":")[1];
    if (!latest.has(fir) || ms(f.properties.valid_from) > ms(latest.get(fir).properties.valid_from)) latest.set(fir, f);
  }
  const vaas = feats.filter((f) => f.properties.kind !== "SIGMET");
  const products = [];
  for (const f of latest.values()) products.push(f.properties.label);
  for (const f of vaas) {
    const n = f.properties.label.replace(/ (EST|OBS)$/, "");
    if (!products.includes(n)) products.push(n);
  }
  const main = [...latest.values()][0] || vaas[0];
  const p = main.properties;
  const base = Math.min(...feats.map((f) => f.properties.base_ft));
  const top = Math.max(...feats.map((f) => f.properties.top_ft));
  const sel = vid === D.selected;
  const name = D.sits.find((s) => s.volcano_id === vid)?.volcano_name || vid;
  // line 2 only when a movement is given (R6.3)
  const rawMove = D.moveByVolcano[vid];
  const move = rawMove && !/^NOT (STATED|GIVEN)$/i.test(rawMove.trim()) ? plainMove(rawMove) : "";
  const vt = ms(p.valid_to);
  return {
    line1: sel ? `Official ash area · ${band(base, top)} · until ${hhmmz(vt)}` : name,
    line2: sel ? move : "",
    geometry: main.geometry, sel, name, products, base, top, validTo: vt, until: untilText(vt - D.now), kind: p.kind,
  };
}

export function untilText(deltaMs) {
  const m = Math.round(deltaMs / 60e3);
  if (m <= 0) return "expiring";
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)} h ${m % 60} min`;
}

// TEPHRA's label for the selected volcano (R6.3): what the estimate is, in plain words.
export function tephraLabelText(cone, stub) {
  if (!cone) return null;
  if (cone.mode === "HYPOTHESIS") return "TEPHRA's estimate · hypothesis";
  if (cone.mode === "WIDENED") return "TEPHRA's estimate · wider than official";
  return stub ? "TEPHRA's estimate · same as official (AI off)" : "TEPHRA's estimate · same as official";
}

// [lon, lat] points along the great circle from a to b, about one every 40 NM (as the server's
// route lines), longitudes unwrapped so a line never jumps across the map.
function greatCircle(a, b) {
  const rad = Math.PI / 180;
  const unit = ([lon, lat]) => [Math.cos(lat * rad) * Math.cos(lon * rad), Math.cos(lat * rad) * Math.sin(lon * rad), Math.sin(lat * rad)];
  const u = unit(a), v = unit(b);
  const angle = Math.acos(Math.max(-1, Math.min(1, u[0] * v[0] + u[1] * v[1] + u[2] * v[2])));
  const steps = Math.min(255, Math.max(1, Math.ceil((angle * 3440.065) / 40)));
  const out = [];
  let prev = null;
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const k1 = angle ? Math.sin((1 - t) * angle) / Math.sin(angle) : 1 - t, k2 = angle ? Math.sin(t * angle) / Math.sin(angle) : t;
    const x = k1 * u[0] + k2 * v[0], y = k1 * u[1] + k2 * v[1], z = k1 * u[2] + k2 * v[2];
    let lon = Math.atan2(y, x) / rad;
    const lat = Math.atan2(z, Math.hypot(x, y)) / rad;
    if (prev != null) while (lon - prev > 180) lon -= 360;
    if (prev != null) while (prev - lon > 180) lon += 360;
    prev = lon;
    out.push([lon, lat]);
  }
  return out;
}
