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
  const regionEmpty = !!area && inRegion.length === 0;
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
    if (!lvAll && known && !p.exposed && (p.alt_baro_ft < ui.level.min || p.alt_baro_ft > ui.level.max)) {
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
        ...p, stale, inside, ageS, sel_vid: selected || "", picked: p.hex === selHex,
        l1: `${p.proxy_flight}${p.callsign ? ` · ${p.callsign}` : ""}`,
        l2, l3, l3ok: !!ok,
        l4: stale ? `position ${mins} min old` : "",
        short: `${p.callsign || p.hex} ${lvl}`,
        // One line on the map (R6.3); level, decision and position age are in Details › This flight.
        elabel: p.exposed ? `${p.proxy_flight} · ${inside ? "inside" : `in ${p.minutes_to_entry} min`}` : "",
      },
    });
  }
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
  for (const r of state.regions || []) regionCounts[r.key] = sits.filter((s) => vents.get(s.volcano_id) && inBbox(vents.get(s.volcano_id), r.bbox)).length;

  if (regionEmpty && regionCounts[ui.region] > 0) console.error("region invariant");

  return {
    state, now, mode: state.mode, sits, inRegion, regionEmpty, area, selected, sit, vents, official, cones, coneOf, sectorOf,
    hasReroutes: (snap.reroutes?.features || []).length > 0,
    rerouteKeys: new Set((snap.reroutes?.features || []).map((f) => f.properties.flight_id)),
    hasSatBoxes: (snap.satellite || []).some((r) => r.boxes?.length),
    aircraft, exposed, exposures: snap.exposures || { type: "FeatureCollection", features: [] },
    volcanoes, rose, moveByVolcano, firsWithSigmet, advByFlight, regionCounts,
    levelAll: lvAll, hiddenOfficial, hiddenFlights, selFlight, selHiddenByLevel, stepsMissing,
    overlays: snap.overlays || { btd: [], frames: [] },
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
