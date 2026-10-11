# Lateral reroute around a 3-D ash volume: research report for TEPHRA

I did not run project code or gcloud, and I edited nothing in the repo. Facts marked UNVERIFIED are not confirmed against a primary source. The adsb.lol routeset result in section 5 contradicts the source code, so read it before relying on that endpoint.

## 0. Context skimmed

- **Existing geometry.** `tephra/geo/cone.py` builds the cone as a shapely lon/lat union of all official polygons plus a sector, "never simplified, buffered inward or clipped". It carries a vertical band `base_ft`/`top_ft`, and exposure uses `vertical_margin_ft` = 2000 ft (`data/policy/policy_a.json`, citing CAP 1236 2.24). `exposure.py` extrapolates tracks and tests them against the cone.
- **Existing fuel code.** `fuel.py` has a `FuelLine` with a human-readable `formula` string. `pyproject.toml` has shapely and numpy as core dependencies, and pyproj only in the optional `science` extra. A reroute built on shapely plus a hand-written azimuthal-equidistant projection therefore adds no dependency.
- **Policy ordering.** research/15 quotes CAP 1236 on the order of preference: laterally avoid forecast ash where possible, then overflight, underflight, and lastly penetration. This ordering supports trying a lateral reroute before CHANGE_LEVEL.

## 1. Algorithms in practice and in the literature

### 1.1 Visibility graph with tangents (the classic exact method)

- Build a graph on start, goal and obstacle vertices, then run Dijkstra. Shortest s-t path is O(n log n + K) with K = O(n²) visibility edges, and K ranges from Ω(n) to O(n²). Faster specialised algorithms exist but are not worth implementing here. https://en.wikipedia.org/wiki/Visibility_graph
- Shortest paths around obstacles consist only of common-tangent segments, so a pruned tangent graph is enough. https://calhoun.nps.edu/entities/publication/7dc0c9a9-320a-4ea1-bfbe-7f971826b0cf
- Weather work approximates cells by over-approximating polygons. Avoid polygons only 2-3 miles larger than the core were sufficient for forecast uncertainty in almost all cases. A patent reports pruning to obstacles crossed by the s-t line, giving 4 nodes and 3 edges instead of 18 nodes and 71 edges. https://ntrs.nasa.gov/api/citations/20160010026/downloads/20160010026.pdf
- Concave-hull obstacles give routes about 2% shorter on average than convex hulls. https://if-mstuca.ru/CE/?p=16834
- I found no source with a stated complexity bound for moving obstacles, so the time-dependent handling in 1.5 is my own synthesis.

### 1.2 Grid methods: A*, Theta*, Lazy Theta*

- Theta* and Lazy Theta* are any-angle A* variants. Basic Theta* is fast, finds short paths, and is not guaranteed to find true shortest paths. https://jair.org/index.php/jair/article/view/10676
- Lazy Theta* does one line-of-sight check per expanded vertex, with about 10x fewer line-of-sight checks and the same path length. https://ojs.aaai.org/index.php/AAAI/article/view/7566
- Grid methods suit varied wind fields or many obstacles. They are overkill for a handful of polygons in a 600 NM corridor, and the paths are not tangent-exact.

### 1.3 Airway graphs and wind

- Operational planners treat the problem as shortest path on an airway graph with time-dependent winds, and use A* with a "super-optimal wind" potential as the heuristic. https://opus4.kobv.de/opus4-zib/frontdoor/deliver/index/docId/6404/file/main.pdf
- Zermelo's problem is the continuous wind-optimal formulation. Dijkstra or A* on a network is the discrete counterpart. https://skoge.folk.ntnu.no/prost/proceedings/cdc-ecc-2011/data/papers/1820.pdf and https://ar5iv.labs.arxiv.org/html/1804.00905
- With no airway data for Indonesia (section 4), TEPHRA cannot use the airway-graph approach.

### 1.4 NASA Dynamic Weather Routes (DWR), FAA CDR/playbook, Eurocontrol FRA

- **DWR.** It recomputes trajectories every 12 s, looks for at least 5 wind-corrected minutes of saving, and limits the eligible return fixes. Starting from the direct route as a reference, it inserts up to 2 auxiliary waypoints to find a minimum-delay route that avoids the weather and rejoins the plan at a downstream fix. In the 2012 American Airlines trial, about 45% of proposals were rated acceptable (as proposed or modified) by the dispatchers and coordinators who evaluated them. These details come from search-result summaries of the NASA pages, which I did not fetch directly. https://technology.nasa.gov/patent/TOP2-168, https://aviationsystems.arc.nasa.gov/publications/2013/DASC2013_Sheth.pdf, https://aviationsystems.arc.nasa.gov/research/strategic/atd3.shtml
- **FAA CDRs and SWAP playbook.** These are pre-coordinated route lists, not computed routes. Operators have the right to refuse a reroute and elect an alternative. Route strings are uppercase tokens separated by spaces. https://www.faa.gov/air_traffic/publications/atpubs/foa_html/chap18_section_16.html and https://nbaa.org/aircraft-operations/airspace/tfm/tools-used-for-traffic-flow-management/routes-reroutes-severe-weather-avoidance-plan-swap/
- **Eurocontrol FRA.** The operator files its own route between entry and exit points. Extra turning points to avoid danger areas can be navaids, published points or "points with specified coordinates". Plans crossing restricted areas are rejected. https://skybrary.aero/articles/free-route-airspace-fra and https://www.eurocontrol.int/concept/free-route-airspace

### 1.5 Time-dependent obstacles

- The forecast steps are T+0/6/12/18, each valid for ±3 h in `cone.py`. A time-expanded visibility graph is possible but overkill.
- Recommended: a conservative two-pass scheme (section 7). In the first pass the obstacle is the union of every layer whose window overlaps the flight's possible exposure interval. The second pass re-checks using only layers whose windows contain the flight's actual ETA at each leg. This is safe, because only a union can over-avoid, and it is easy to test.

### 1.6 Keeping it fast

- Work in a local azimuthal-equidistant projection centred on the origin-destination midpoint. Error over under 1500 km is under 1%. Use plain spherical formulas, with no pyproj.
- Filter obstacles to those intersecting a corridor around the direct route, using an STRtree or bounding-box test.
- Simplify with Douglas-Peucker at about 1-2 NM, then buffer outward by the safety buffer plus the simplification tolerance. This guarantees a superset of the official polygon, which matches the "never shrink the official polygon" rule.
- Test visibility edges with a prepared geometry and shapely 2 vectorised `intersects`.
- Cache per (cone.id, time-step mask): the obstacle-vertex visibility graph is built once. Each flight then adds only about 2V start/goal edges plus the rejoin candidates.
- Sizes: V ≈ 50-150 vertices gives about 10-20k edge tests, tens of ms. Dijkstra over E edges is O(E log V).

## 2. Operational constraints

- **Lateral avoidance comes first.** CAP 1236 says operators "should, where possible, laterally avoid forecast areas of ash contamination", and may consider overflight, underflight and lastly penetration only where that is unacceptably restrictive (PDF text, para about 2.28; paragraph number UNVERIFIED). https://www.caa.co.uk/publication/download/14978
- **No official lateral buffer exists.** I found no number in ICAO Doc 9974 or in CAP 1236. The UK document says "ATS providers do not need to apply any additional buffers" and gives only vertical rules (2000 ft below the base, para 2.29; and 2.24 above the top, already in policy_a). The Icelandic danger area (120 NM radius around the volcano, or 60 NM downwind) is source-centred and applies only close to an eruption. CAP 1236 v3 notes ICAO IVATF recommendation 4/16: do not declare danger areas except near the volcano. https://www.caa.co.uk/publication/download/14978
- **My reading of Doc 9974.** Text available to me (a 9-page COPAC extract, not the full Doc 9974) says planning must "enable crews to avoid areas" and allow "re-planning at short notice". https://www.copac.es/wp-content/uploads/2021/09/ICAO-Guidance-on-Flight-Operations-and-Volcanic-Ash.pdf
- **EUR/NAT Doc 019.** I could not confirm any lateral buffer figure. The proactive phase uses the +6 h forecast in a SIGMET and +12/+18 h in NOTAMs. Edition 2.2.0 (Jan 2024) is listed on ICAO's EUR/NAT page and was not read. https://unitingaviation.com/regions/eurnat/volcanic-ash-preparedness-in-the-eur-and-nat-regions/
- **Buffer to use.** The buffer is therefore an operator choice, to be labelled "TEPHRA illustrative choice" in policy, like the other planner numbers.
- **Turn geometry.** Fly-by turn radius R_ft = V_kt² / (11.26 · tan(bank)). At 450 kt and 25° bank, R ≈ 38,600 ft ≈ 6.4 NM. Turn anticipation is R · tan(Δ/2). A 60° turn needs about 3.7 NM, a 90° turn about 6.4 NM. The buffer must exceed this so a smoothed turn stays outside the true ash edge. The formula is standard aeronautical practice and I did not verify it against a source.
- **Waypoint count.** DWR uses at most 2 inserted waypoints. Keep ≤ 3 so an ACARS message stays short and a human can check it.
- **FIR boundaries.** FRA flight plans may be rejected for leaving the free-route area. Eurocontrol also publishes time-limited DCT restrictions. I found no freely redistributable FIR polygons or Indonesian equivalents. Treat FIR crossing as an advisory remark in the dispatcher message: "ATC coordination/approval required". Tephra proposes, a human approves.
- **Endurance, extra distance and fuel.** Cost the reroute with `fuel.py` burn rates for the extra minutes, plus an existing-style `formula` string. Compare against a ceiling on extra time.
- **How airlines express a reroute.** ICAO Doc 4444 Item 15 coordinates are DDMM[N|S]DDDMM[E|W] (11 characters), e.g. `0812S11245E`. There is also a degrees-only 7-character form, `46N078W`. Example from Lithuanian AIP ENR 1.10: `4620N07805W`. Points are space-separated in the route string, and `DCT` is the direct-to token. https://www.iaa.ie/docs/default-source/publications/advisory-memoranda/aeronautical-services-advisory-memoranda-(asam)/policy-on-naming-of-significant-points.pdf?sfvrsn=4 (naming policy). The AIP excerpt is secondary. The primary text is Doc 4444 Appendix 2, which I could not retrieve.
- **FAA route-string rules.** Uppercase only, space-separated, no leading zeros on airway names. https://nbaa.org/aircraft-operations/airspace/tfm/tools-used-for-traffic-flow-management/routes-reroutes-severe-weather-avoidance-plan-swap/

## 3. Wind pricing

- **Open-Meteo pressure-level wind.** Available levels (hPa) are 1000, 975, 950, 925, 900, 850, 800, 700, 600, 500, 400, 300, 250, 200, 150, 100, 70, 50, 30. Variables are `wind_speed_{level}hPa`, `wind_direction_{level}hPa` and `geopotential_height_{level}hPa`. Wind speed units can be set to knots. Multiple comma-separated lat/lon pairs are accepted in one request. The page warns that "pressure level variables do not have fixed altitudes". https://open-meteo.com/en/docs
- **Terms.** Non-commercial free tier, attribution required, data CC BY 4.0, and daily/hourly/minute limits (example given: 10,000 calls/day). Commercial use needs a paid plan. A hackathon demo is probably non-commercial, but the licence page was a stub in my fetch. https://open-meteo.com/en/features#terms
- **Multi-location call weighting.** UNVERIFIED whether N coordinates count as N calls. Keep to at most 16 points per request and cache per hour.
- **Flight level to hPa (ISA).** p = 1013.25 · (1 − 6.8756e-6 · h_ft)^5.2559. FL300 ≈ 301 hPa and FL350 ≈ 238 hPa. Interpolate wind between the two bracketing levels, linearly in ln p (u and v components, not direction).
- **Edge cost.** For a leg with track θ, wind from φ at speed w, and TAS V, compute `cross = w·sin(φ−θ)` and `tail = −w·cos(φ−θ)`. Then `GS = sqrt(V² − cross²) + tail`, and edge time = dist / GS using the wind sampled at the leg midpoint. For legs over about 150 NM, split in 2-3 segments and sum.
- **Optimality caveat.** The edge-cost method treats each leg as a straight great-circle segment and does not solve the full Zermelo problem. It is sufficient for choosing a side and pricing a detour.
- **TAS source.** Use a category default of about 450 kt (narrowbody cruise). Where ADS-B provides `tas` and wind, prefer them. readsb outputs these in aircraft.json when the aircraft transmits the relevant Mode S data (UNVERIFIED for adsb.lol).

## 4. Airway and waypoint data

| Source | Covers | Licence | Redistribute in public repo? |
|---|---|---|---|
| OurAirports `navaids.csv` | Worldwide navaids only (VOR, NDB, DME, TACAN). Indonesia 216 (163 NDB, 52 VOR-DME, 1 TACAN). Japan 219. No airways, no RNAV fixes. 11,008 rows total as downloaded today. | Public domain, no warranty, credit welcome. https://ourairports.com/data/ and https://ourairports.com/about.html | Yes |
| OurAirports airports | Airports with lat/lon/elevation | Public domain | Yes |
| VRS standing-data airports | Airports (schema 1: Code, Name, ICAO, IATA, Location, CountryISO2, Latitude, Longitude, AltitudeFeet). WIII = -6.12557, 106.655998 | CC0-1.0 (LICENSE file confirmed) | Yes |
| X-Plane default `earth_awy.dat` / `earth_nav.dat` / `earth_fix.dat` | Global airways and fixes, cycle frozen for XP12 | The developer docs state no licence and point to the file header. The airway spec says the copyright message must be kept intact if redistributed. Default data origin not stated. https://developer.x-plane.com/?p=6508 and https://developer.x-plane.com/wp-content/uploads/2019/01/XP-AWY1101-Spec.pdf | Do not commit. UNVERIFIED licence |
| Little Navmap | Reads sim and Navigraph data | Navigraph data is personal, simulation-only, non-transferable. https://developers.navigraph.com/docs/general/restrictions | No |
| FAA CIFP | US-focused; X-Plane docs call it free of charge. https://developer.x-plane.com/article/navdata-in-x-plane-11/ | US government data, not verified here | Not useful for Indonesia/Japan |
| OpenAIP | Airports, airspaces, navaids, etc. | CC BY-NC 4.0 per a secondary source; the openaip.net terms page returned 404. A webmaster allowed informal app use with attribution. https://groups.google.com/g/openaip/c/mUdnOppU5Eo | Non-commercial only. UNVERIFIED terms and coverage. Do not commit |
| AIP Indonesia ENR 3 (AirNav) | Official | I found no terms page for Indonesia. Australia's AIP, for comparison, forbids redistribution without written permission. https://www.airservicesaustralia.com/aip/ | Assume no |
| VATSIM sector files | Not checked | UNVERIFIED | UNVERIFIED |

**Conclusion:** there is no freely redistributable airway or RNAV-waypoint dataset for Indonesia, SE Asia or Japan. Tephra should therefore compute free-route DCT routes with lat/lon turn points. This is a valid, explainable output and matches FRA practice. OurAirports navaids (public domain) could optionally be used to give "nearest VOR" context in the message, but this is not needed.

## 5. Origin and destination per ADS-B aircraft

- **Standing data.**
  - Repo: https://github.com/vradarserver/standing-data (CC0-1.0).
  - Per callsign JSON, confirmed today: `https://vrs-standing-data.adsb.lol/routes/GI/GIA101.json`, the first two letters of the callsign, HTTP 200, `cache-control: max-age=600`.
  - Example fields: `callsign, number, airline_code, airport_codes ("WIPP-WIII"), _airport_codes_iata, _airports[{name, icao, iata, location, countryiso2, lat, lon, alt_feet, alt_meters}]`.
  - Whole-database CSV: `https://vrs-standing-data.adsb.lol/routes.csv.gz`, 4.5 MB gz, about 620,700 lines. Columns are `Callsign, Code, Number, AirlineCode, AirportCodes`, where AirportCodes is a hyphen-joined chain such as `WIPP-WIII`.
  - Repo layout: `routes/schema-01/<first letter>/<CODE>-all.csv`, e.g. `G/GIA-all.csv`. Airports are in `airports/schema-01/W/WI.csv` and similar.
  - Callsign normalisation (strip leading zeros, IATA to ICAO) is documented in `routes/schema-01/README.md`.
  - Routes are crowd-sourced per callsign, so they may be stale or wrong. Pair them with the plausibility check below.
- **Routeset endpoint.**
  - Source code: `POST /api/0/routeset` with body `{"planes":[{"callsign":..., "lat":..., "lng":...}]}`, at most 100 planes, returning a list with `airport_codes`, `_airports` and a `plausible` flag. https://raw.githubusercontent.com/adsblol/api/main/src/adsb_api/utils/api_routes.py
  - The deprecated GET `/api/0/route/{callsign}` returns a 302 redirect to the static JSON above, after a 5-second delay.
  - **Live check failed.** Today a POST to `https://api.adsb.lol/api/0/routeset` returned HTTP 201 with an empty body (twice, with different headers). `/openapi.json` and `/docs` returned 404 or no content. UNVERIFIED that routeset currently works. Prefer the static JSON or CSV.
- **Terms.** The API README says rate limits are dynamic and an API key may later be required (obtained by feeding adsb.lol). It states no licence for API data. https://raw.githubusercontent.com/adsblol/api/main/README.md. adsb.lol's historical data is described as ODbL in secondary results, which I did not confirm. The VRS standing-data repo is CC0, so it can be redistributed.
- **Plausibility check (own implementation).** A multi-leg `AAAA-BBBB-CCCC` chain is the flight's candidate legs. For each leg, test that the aircraft is near the great circle, e.g. cross-track under 100 NM and between the endpoints. If no leg passes, set `origin/dest = unknown` and fall back to a direct reroute to a downstream point along the current track.
- **Fictional airline.** RFA flights are proxies, so the demo assigns each proxy its real-world callsign's O/D and says so in the UI.

## 6. Test case geometry (WIII to WADD)

- WIII (-6.1256, 106.6560) to WADD Bali (-8.7482, 115.1672): great circle 530.6 NM (haversine, computed), initial track about 107°. Midpoint is about (-7.45, 110.9) near Central Java.

## Recommendation for TEPHRA

**Algorithm: buffered-obstacle tangent visibility graph with wind-priced Dijkstra, in a local azimuthal-equidistant (AEQD) projection, with an optional rejoin of the original track.** The reasons are:

- The obstacle is a few polygons, so visibility-graph vertices stay under about 150 and the graph is exact.
- Output is 1-3 waypoints, which fits ACARS and the DWR limit of 2 auxiliary waypoints.
- It reuses the shapely geometry already in `cone.py`.
- It needs no airway data.
- It works with winds and forecast steps.

### Files and policy fields

Add `tephra/geo/reroute.py`. In `data/policy/policy_a.json`, add under `planner`, each with `source: "TEPHRA illustrative choice"`:

- `reroute_buffer_nm`: 20 (lateral buffer around the official ash area).
- `reroute_simplify_nm`: 2 (Douglas-Peucker tolerance, added to the buffer so the result stays a superset).
- `reroute_max_waypoints`: 3.
- `reroute_max_turn_deg`: 90.
- `reroute_bank_deg`: 25.
- `reroute_rejoin_step_nm`: 25 (spacing of candidate rejoin points on the original track).
- `reroute_max_extra_min`: 30 (the ceiling, above which choose HOLD or DIVERT).
- `reroute_min_extra_min`: 3 (below this, say "no benefit").
- `cruise_tas_kt` per category (about 450 for narrowbody, set in `fuel.py` style).

### Data structure

```python
@dataclass(frozen=True)
class RerouteOption:
    flight_id: str
    status: Literal["OK","NO_ROUTE","START_INSIDE","DEST_INSIDE","NO_BENEFIT","NO_DEST"]
    waypoints: list[tuple[float,float]]   # inserted turn points (lat, lon), 1..3
    rejoin: tuple[float,float] | None     # point on the original track, or None for direct to destination
    side: Literal["LEFT","RIGHT"] | None
    dist_nm: float; extra_nm: float
    time_min: float; extra_min: float     # wind-priced
    buffer_nm: float; max_turn_deg: float
    obstacle_ids: list[str]               # cone/layer ids avoided
    fuel: FuelLine                        # extra_min x burn rate, formula string
    route_string: str                     # "DCT 0540S10930E 0701S11215E DCT WADD"
    wind_note: str                        # e.g. "WIND 250HPA 28 KT TAILWIND LEFT SIDE"
```

### Pseudocode

```python
def plan_reroute(flight, orig, dest, layers, wind, policy, at):
    # 1. 3-D filter: keep only layers whose vertical band meets the flight level +/- margin
    fl_ft = flight.alt_baro_ft
    L = [l for l in layers if l.base_ft - m <= fl_ft <= l.top_ft + m]
    if not L: return None                        # not exposed; no reroute needed

    # 2. local AEQD projection centred on orig/dest midpoint, km or NM units
    P = Aeqd(mid_lat, mid_lon)

    # 3. corridor filter: keep polygons that touch the ellipse around orig-dest (sum of distances < 1.5 x direct)
    # 4. obstacle = union(simplify(poly, tol)).buffer(buffer_nm + tol + turn_anticipation, join="mitre"/round)
    obst = union_of_buffered(L_in_corridor)
    if obst.contains(orig):  return START_INSIDE
    if obst.contains(dest):  return DEST_INSIDE

    # 5. nodes: start, dest, every exterior vertex of obst (convex ones are enough), rejoin candidates
    #    rejoin candidates: points on the ORIGINAL track downstream, every rejoin_step_nm,
    #    kept only if outside obst AND the original track from there to dest is clear
    V = [start, dest] + hull_or_convex_vertices(obst) + rejoins

    # 6. visibility edges: segment i-j is an edge iff it does not cross the interior of obst
    #    (prepared geometry, vectorised intersects, small eps inset)
    E = {(i,j): time(i,j, wind) for visible pairs}   # time = dist / GS(wind at midpoint)
    for r in rejoins: E[(r, dest)] = time along the original track (already known clear)

    # 7. Dijkstra on time -> path; no path => NO_ROUTE
    path = dijkstra(V, E, start, dest)

    # 8. post-process: drop collinear nodes; check turns <= max_turn_deg at each waypoint;
    #    if waypoints > reroute_max_waypoints, raise simplify tolerance and retry once
    # 9. time-dependent pass: compute ETA at each leg; re-test each leg against only the
    #    layers valid at that ETA; if any leg fails, add that layer and re-run (max 2 iterations)
    # 10. compare with the original: extra_min = time(path) - time(original route)
    #    if extra_min > reroute_max_extra_min -> NO_ROUTE (planner falls back to HOLD/DIVERT)
    # 11. emit RerouteOption; round waypoints to 1 arc-minute (<= 0.9 NM, absorbed by the buffer)
```

### Complexity and speed

- **Per cone.** V ≤ 150 gives ≤ ~11k visibility tests with a prepared geometry. Dijkstra is O(E log V). Expected cost is about 20-100 ms per cone.
- **Per flight.** Reuse the cached obstacle-vertex graph keyed by (cone.id, step mask), and add only start/goal edges (about 2V tests). Dijkstra is then well under 10 ms per flight.
- **Memory.** Under 1 MB.
- **If obstacles grow.** Switch to Lazy Theta* on a 5 NM grid (O(N log N) with far fewer line-of-sight checks), which is not needed for the three demo regions.

### ACARS draft format

```
RFA123 (proxy) REROUTE PROPOSAL, SUBJECT TO ATC APPROVAL
AVOID VA AREA +20 NM. FL350.
DCT 0540S10930E DCT 0701S11215E DCT WADD
EXTRA 14 NM / 2 MIN / ~84 KG (WIND 250HPA 28 KT TAILWIND)
```

Rules for the message:
- The coordinates use `DDMM[N|S]DDDMM[E|W]`, rounded to one minute.
- Waypoints are flown in order and followed by `DCT` to the destination or the rejoin point.
- Flag any FIR crossing as "ATC COORDINATION REQUIRED".
- The human dispatcher approves.

### Planner ordering

1. Compute `plan_reroute`. Accept it if `status == OK` and extra time is within [reroute_min_extra_min, reroute_max_extra_min]. Show CONTINUE if no 3-D exposure.
2. Otherwise fall back to the existing CHANGE_LEVEL, then HOLD or DIVERT, using the existing policy windows.
3. This follows the ICAO/CAP 1236 order of preference (lateral avoidance first, then overflight or underflight) while staying within TEPHRA's illustrative policy.

### Test cases (pytest + hypothesis where noted)

| # | Setup | Expected |
|---|---|---|
| T1 | Circular cone, 40 NM radius, centred on the WIII-WADD midpoint (-7.45, 110.9), FL0-400, flight FL350, buffer 20 NM | OK, 1 waypoint, extra about 13-16 NM (analytic: 2·√(265²−60²) + 27 = 543.6 NM vs 530.6 NM). Path never intersects the buffered polygon. |
| T2 | Same cone offset 100 NM from the track | `NO_BENEFIT`/no exposure: route equals the original. |
| T3 | Cone covering WADD | `DEST_INSIDE`, planner falls to HOLD/DIVERT. |
| T4 | Aircraft position inside the buffered cone | `START_INSIDE`, escalate, no route. |
| T5 | Vertical band FL400-600 and flight FL350 with margin 2000 ft | Not exposed (vertical filter), no reroute. |
| T6 | Two 25 NM cones with a 30 NM gap (smaller than 2 × buffer) | The buffered union closes the gap, so the path goes around both, not through the gap. |
| T7 | Layer valid only at T+12 and flight crosses at T+1 (window ±3 h) | Layer ignored, original route kept. |
| T8 | Tailwind 80 kt on the longer side | Chooses the longer side if the time is shorter; `wind_note` says so. |
| T9 | Official polygon with concave notch | Result stays outside the notch's buffered boundary. Property test: `covers_official` still holds for the obstacle (hypothesis). |
| T10 | Waypoint rounding to 1 arc-minute | Rounded path still clear of the unbuffered official polygon by at least buffer minus 1 NM. |
| T11 | Turn angle > 90° at a vertex | Rejected, or an extra waypoint is inserted; never silently accepted. |
| T12 | Output string format | `0812S11245E` regex `^\d{4}[NS]\d{5}[EW]$` for every waypoint. |
| T13 | Unknown destination (`NO_DEST`) | Direct-to a downstream track point is proposed, with a visible "destination unknown" warning. |

## Source list (consolidated)

- https://en.wikipedia.org/wiki/Visibility_graph
- https://calhoun.nps.edu/entities/publication/7dc0c9a9-320a-4ea1-bfbe-7f971826b0cf
- https://ntrs.nasa.gov/api/citations/20160010026/downloads/20160010026.pdf
- https://if-mstuca.ru/CE/?p=16834
- https://jair.org/index.php/jair/article/view/10676
- https://ojs.aaai.org/index.php/AAAI/article/view/7566
- https://opus4.kobv.de/opus4-zib/frontdoor/deliver/index/docId/6404/file/main.pdf
- https://skoge.folk.ntnu.no/prost/proceedings/cdc-ecc-2011/data/papers/1820.pdf
- https://ar5iv.labs.arxiv.org/html/1804.00905
- https://technology.nasa.gov/patent/TOP2-168
- https://aviationsystems.arc.nasa.gov/publications/2013/DASC2013_Sheth.pdf
- https://aviationsystems.arc.nasa.gov/research/strategic/atd3.shtml
- https://www.faa.gov/air_traffic/publications/atpubs/foa_html/chap18_section_16.html
- https://nbaa.org/aircraft-operations/airspace/tfm/tools-used-for-traffic-flow-management/routes-reroutes-severe-weather-avoidance-plan-swap/
- https://skybrary.aero/articles/free-route-airspace-fra
- https://www.eurocontrol.int/concept/free-route-airspace
- https://www.caa.co.uk/publication/download/14978
- https://www.copac.es/wp-content/uploads/2021/09/ICAO-Guidance-on-Flight-Operations-and-Volcanic-Ash.pdf
- https://unitingaviation.com/regions/eurnat/volcanic-ash-preparedness-in-the-eur-and-nat-regions/
- https://www.iaa.ie/docs/default-source/publications/advisory-memoranda/aeronautical-services-advisory-memoranda-(asam)/policy-on-naming-of-significant-points.pdf?sfvrsn=4
- https://open-meteo.com/en/docs
- https://open-meteo.com/en/features#terms
- https://ourairports.com/data/
- https://ourairports.com/about.html
- https://github.com/vradarserver/standing-data
- https://raw.githubusercontent.com/vradarserver/standing-data/main/routes/schema-01/README.md
- https://vrs-standing-data.adsb.lol/routes/GI/GIA101.json
- https://vrs-standing-data.adsb.lol/routes.csv.gz
- https://raw.githubusercontent.com/adsblol/api/main/src/adsb_api/utils/api_routes.py
- https://raw.githubusercontent.com/adsblol/api/main/README.md
- https://developer.x-plane.com/?p=6508
- https://developer.x-plane.com/wp-content/uploads/2019/01/XP-AWY1101-Spec.pdf
- https://developer.x-plane.com/article/navdata-in-x-plane-11/
- https://developers.navigraph.com/docs/general/restrictions
- https://groups.google.com/g/openaip/c/mUdnOppU5Eo
- https://www.airservicesaustralia.com/aip/
