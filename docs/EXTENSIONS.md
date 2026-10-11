# TEPHRA extensions: design contract

Eight AI extensions and a lateral reroute, built on 2026-10-11/12. Research is in
`research/18a` to `research/18f`. Read `CLAUDE.md`, `MODULES.md` and `docs/ARCHITECTURE.md`
first. This file is the contract the work packages (WP) code against.

## 0. Rules for every work package

1. **No fallbacks.** When a model call fails, is over budget, or its answer fails the checks
   after at most one repair, the feature returns an explicit failure: the trace line,
   the stored record and the HTTP response say `AI UNAVAILABLE: <reason>` (HTTP 503,
   `{"error": "ai_unavailable", "message": ...}`) and nothing is substituted. No canned
   answer, no rule-based stand-in, no template, no greedy heuristic in place of a solver,
   no browser speech in place of Gemini speech. A code path that is the *primary* design
   (the reroute geometry, the CP-SAT solver, the JMA XML parser, the backtest metrics) is not
   a fallback. If a WP believes a fallback is needed, it stops and says so in its report
   instead of adding one.
   `TEPHRA_LLM=stub` stays as the offline test mode (labelled NO MODEL); every new model
   step gets a deterministic stub answer for tests only.
2. **Free tier only.** New model steps run on `TEPHRA_MODEL_LITE` (`gemini-3.5-flash-lite`,
   tier `"lite"`) through `LlmBackend.structured` (budgeted, cached, timed out) or an ADK
   agent guarded like `exposure_planner._ModelGuard`. Never on a path that runs every tick
   without a gate. The main tier (`gemini-3.8-flash`, about 20/day) stays the Plume
   Reader's. Text-to-speech may use `TEPHRA_MODEL_TTS` (WP2 adds it).
3. **The model never writes a time, an id, a hash, a coordinate or a number that is not in
   its input.** Code renders them. Every model output gets a validator in the style of
   `agents/validators.py` (numbers, ICAO codes and ids must appear in the input).
4. **Human gate.** Anything that would leave TEPHRA (messages, recovery plans, documents)
   is a DRAFT until a dispatcher approves it on the Desk, and goes only to TEPHRA's own
   `outbound` collection. Every transition is an audit entry (`desk/audit.record`).
5. **Labels.** Fictional airline (Ring of Fire Air, RFA), REPLAY, DRAFT, "decision support
   only", AI-written vs code-written are always visible.
6. **Ownership.** A WP edits only the files listed for it. Shared contract changes are
   already made (section 1). A WP that needs another contract change says so in its report.
   Feature models live in the feature's own module (e.g. `tephra/recovery/models.py`) and
   subclass `tephra.models.TephraModel`. A WP never edits `pipeline.py`, `api/server.py`,
   `models.py`, `config.py`, `policy.py`, `data/policy/`, `MODULES.md` or the web files;
   the integration WP (WP9) and the UI WPs (WP10, WP11) do.
7. **API.** Each WP that serves HTTP writes `tephra/api/routes_<feature>.py` exporting
   `router = APIRouter()`, using the dependencies in `api/server.py` (`DeskSession`,
   `RuntimeDep`, `require_csrf`, `_json`, `ApiError`) by importing them. WP9 mounts the
   routers under `/api`. Desk routes need a session; POSTs need `require_csrf`.
8. **Tests.** Every WP adds tests under `tests/test_<feature>.py` (no network, stub or
   scripted LLM, `FixedClock`), runs `uv run pytest -q`, `uv run ruff check .` and
   `uv run ruff format --check .`, and leaves them green for its files. Live Gemini tests
   are `@pytest.mark.gemini` and are not run.
9. **Never** run gcloud/gsutil/bq/firebase, never commit, never print `GEMINI_API_KEY`.
10. **Report** at the end: files changed, public functions with signatures, endpoints, SSE
    events, store collections used, settings needed, tests added, anything left undone.

## 1. Shared contract already in place

- `ActionKind.REROUTE`; `RerouteKind`, `RerouteStatus`, `FlightRoute`, `RerouteOption`
  (models.py); `PlannerContext.route`, `PlannerContext.reroutes`,
  `PlannerDecision.reroute_id`, `Advisory.reroute`.
- `AuditAction`: `ASKED`, `NOTICE_READ`, `RECOVERY_PROPOSED`, `RECOVERY_DECIDED`,
  `MESSAGE_DRAFTED`, `MESSAGE_DECIDED`, `DOC_DRAFTED`, `DOC_SIGNED`, `HANDOVER_ACKED`,
  `AI_FAILED`, `AI_FAILURE_HANDLED`.
- `TraceStage`: `SATELLITE`, `NOTICE`, `ASK`, `RECOVERY`, `MESSAGES`, `DOCS`.
- `SseEvent`: `ai_failure`, `satellite`, `notice`, `recovery`, `message`, `doc`, `budget`.
- `Collection`: `ai_failures`, `reroutes`, `sat_readings`, `notices`, `ask_log`,
  `recovery`, `messages`, `docs`, `backtest`.
- Policy `2026.10.2`: blocks `reroute.*` and `recovery.*` (read the file for names, units
  and reasons). `tests/test_policy.py` fails until code reads every value.
- `AiFailure` + `desk/failures.py` (+ `/api/desk/ai-failures`): the no-fallback path for
  per-flight planning and drafting.

## 2. Work packages

### WP1 Reroute (geo + planner + drafter)

Files: `tephra/geo/reroute.py`, `tephra/feeds/routes.py`, `scripts/build_routes.py`,
`data/routes_apac.json`, `tephra/agents/{exposure_planner,adk_app,validators,dispatch_drafter}.py`,
`tephra/agents/prompts/{planner,drafter}.md`, `tephra/geo/fuel.py`, tests.

- **Routes.** `scripts/build_routes.py` downloads VRS standing data
  `https://vrs-standing-data.adsb.lol/routes.csv.gz` (CC0) once and writes
  `data/routes_apac.json`: callsign -> airport chain, kept only when every airport in the
  chain is in `data/airports.json` or lies inside TEPHRA's three regions' bounding boxes
  widened by 1,500 NM (keep the file under about 2 MB; record the source URL, fetch date,
  sha256 and licence in the file header object). `feeds/routes.py`:
  `load_routes(data_dir) -> RouteTable`, `RouteTable.lookup(aircraft, airports) -> FlightRoute | None`
  picks the leg whose great circle passes within `reroute.route_max_cross_track_nm` of the
  aircraft and that the aircraft's track points along (within 90 degrees of the bearing
  to the leg's destination). No network at runtime.
- **Algorithm** (`geo/reroute.py`; research/18a "Recommendation"):
  buffered-obstacle visibility graph + wind-priced Dijkstra in a local azimuthal
  equidistant projection (hand-written, no pyproj).
  1. Vertical filter: hazard layers (the cone at its band, and each official layer at its
     band and validity window) that meet the flight's level band +/- the vertical margin.
  2. Obstacle = union of those layers, simplified by `reroute.simplify_nm`, buffered by
     `reroute.buffer_nm + reroute.simplify_nm` (always a superset of the true area).
  3. Nodes: start (present position), the obstacle's exterior vertices (convex vertices
     only), the end candidates. `REJOIN_TRACK`: points on the present track extrapolated
     beyond the obstacle every `reroute.rejoin_step_nm`, outside the obstacle, from which
     the track ahead (to the lookahead horizon) is clear; the route ends at the first
     reachable one. `DIRECT_DEST`: the destination of `FlightRoute` (status `NO_DEST` with
     no route; `DEST_INSIDE` when the destination is inside).
  4. Edges: pairs whose segment does not enter the obstacle interior (shapely prepared
     geometry, vectorised). Edge cost = minutes = distance / ground speed, ground speed
     from the wind at the flight level sampled at the leg midpoint (`WindProfile` of the
     situation; TAS = ADS-B ground speed corrected by the wind, else
     `reroute.cruise_tas_kt`).
  5. Dijkstra on minutes. Post-process: drop collinear points; turn at each point <=
     `reroute.max_turn_deg`; at most `reroute.max_waypoints_count` turn points (raise the
     simplification once and retry; else `NO_ROUTE`). Waypoints rounded to one arc-minute
     after a check that the rounded path is still clear.
  6. Compare with the present track to the same end: `extra_min`. Over
     `reroute.max_extra_min` -> `TOO_LONG`; under `reroute.min_extra_min` -> `NO_BENEFIT`.
  7. Cache the obstacle and its vertex visibility graph per `(cone.id, level band)`; per
     flight only start/end edges are added. Target: < 100 ms per cone, < 10 ms per flight;
     `RerouteOption.compute_ms` records it. Add a micro-benchmark test with a generous bound.
  8. `route_string`: `DCT 0540S10930E DCT 0701S11215E DCT WADD` (rejoin: the rejoin point
     as a coordinate then `DCT` and nothing else); fuel via `fuel.reroute_line`.
  Public: `plan_reroutes(flight, cone, situation, route, policy) -> list[RerouteOption]`
  (both kinds, every status). Test cases T1 to T13 of research/18a (T13: `NO_DEST`, no
  substitute route) plus property tests: no OK path segment intersects the unbuffered
  official polygons or the cone; `covers` holds.
- **Planner.** `build_planner_context` fills `route` and `reroutes`. New ADK tools:
  `list_reroutes()` (summaries of OK options with extra minutes, fuel, side, waypoints count)
  and `submit_plan(..., reroute_id)`. `REROUTE` is allowed only when an OK option exists and
  the mode allows it (not HYPOTHESIS). The prompt states the CAP 1236 order of preference:
  lateral avoidance first, then level change, then hold or diversion; cost and urgency decide.
  `validate_decision`: `reroute_id` must be an OK option of this context; no other target
  fields with it. `rule_based_decision` (stub mode only) picks the cheapest OK reroute when
  entry is beyond `divert_within_min` and no clear band exists.
- **Drafter.** `facts` gain the reroute (route string, extra NM/min, fuel); the template and
  validator accept coordinates only as written in `route_string`; the body must contain the
  route string verbatim. `Advisory.reroute` is filled; `dedupe_key` includes the reroute id.

### WP2 Ask TEPHRA (chat + voice) and the AI budget meter

Files: `tephra/agents/ask.py`, `tephra/agents/prompts/ask.md`, `tephra/agents/voice.py`,
`tephra/api/routes_ask.py`, tests.

- `ask.py`: an ADK `LlmAgent` on the lite model with read-only FunctionTools over the
  runtime: `situation(volcano_id)`, `discrepancies(volcano_id)`, `cone(volcano_id)`,
  `exposed_flights()`, `flight(flight_id)`, `advisory(advisory_id|flight_id)`,
  `plan(flight_id)` (incl. reroute options), `feeds()`, `ai_failures()`, and deterministic
  what-if tools that never change state: `what_if_band(volcano_id, base_fl, top_fl)` and
  `what_if_extent(volcano_id, extra_km)` (re-run `find_exposed` on a modified copy of the
  cone; list flights that become or stop being exposed with minutes to entry),
  `reroute_options(flight_id)`. Every tool result carries an `evidence_id` (`T01`...) and
  the source ids it used. Output schema `AskAnswer {answer (<= 700 chars), claims[{text,
  evidence_ids>=1, kind: fact|number|inference}], status: answered|refused, refusal_reason,
  follow_ups[<=3], language}`. Validator: every evidence id exists; every number, FL,
  ICAO code, callsign and proxy flight in `answer`/`claims` appears in a cited tool result.
  One repair turn, then `AI UNAVAILABLE`. Out-of-scope ("is it safe", legal, forecasts
  beyond the products) -> `refused`. The answer is in the question's language (English,
  Bahasa Indonesia or Japanese). Stored in `ask_log` with tool calls; audit `ASKED`.
  Max 6 tool calls per question.
- `voice.py`: `transcribe(audio_bytes, mime) -> Transcript {text, language}` (one lite call,
  audio part) and `speak(text, language) -> wav bytes` (Gemini TTS model
  `TEPHRA_MODEL_TTS`, default `gemini-3.8-flash-lite-tts`; the response is 24 kHz PCM:
  wrap it in a WAV header). Failure -> `AI UNAVAILABLE` (the text answer still stands; the
  UI says "voice reply unavailable").
- Routes: `POST /api/desk/ask` `{question, flight_id?}` -> `AskAnswer` + trace steps;
  `POST /api/desk/ask/voice` (multipart audio, <= 1 MB, <= 30 s) -> `{transcript, answer}`;
  `POST /api/desk/ask/speak` `{answer_id}` -> `audio/wav`; `GET /api/budget` (public) ->
  calls used and limits per tier today (from `DailyBudget`), published as SSE `budget` by
  WP9 after each model call.

### WP3 Notices in any language + Satellite eyes

Files: `tephra/feeds/jma_volcano.py`, `tephra/agents/notice_reader.py`,
`tephra/agents/satellite_reader.py`, `tephra/agents/prompts/{notice_reader,satellite_reader}.md`,
`tephra/api/routes_notices.py`, `tests/fixtures/jma/`, `tests/fixtures/notices/synthetic_*`, tests.

- **JMA XML** (research/18c): poll the JMA Atom feed
  `https://www.data.jma.go.jp/developer/xml/feed/eqvol.xml` (PDL 1.0; credit "Source: Japan
  Meteorological Agency website"), follow entries of VFVO50/51/52/53/56/60 for the Kyushu
  volcanoes in `data/volcanoes.json`, parse deterministically into `Vona`-compatible records
  (`ash_observed`, plume top above sea level in ft, direction, eruption time UTC). Expose
  `fetch_jma_volcano(source, catalogue, *, since) -> list[Vona]` with provenance
  `feed=FeedId.VONA` and source ids `JMA-<code>-<eventid>` (WP9 adds `FeedId.JMA_VOLCANO`
  and the cadence if a separate feed is cleaner; say which in the report). Fixtures: real
  JMA XML (GREEN) saved under `tests/fixtures/jma/` with the credit in a README.
- **Notice Reader**: `read_notice(text, llm, catalogue, settings) -> NoticeReading`. One lite
  call. Output: per field `{value, evidence}` where evidence is a verbatim substring of the
  NFKC-normalised source; fields: volcano, notice time text + zone, colour code, local alert
  level, ash observed, plume height (value, unit, above summit/sea level), direction text,
  source/observer type. Code converts zones (WIB -7, WITA -8, WIT -9, JST -9, PHT -8) and
  metres to feet, marks `derived`. A notice that fails verification is stored as
  `verified=false`, shown as raw text with a "not verified" badge and never reaches the
  pipeline. A verified one becomes a `Vona` (`feed=FeedId.VONA`, `source_id` `NOTICE-<sha>`)
  that WP9 adds to the live picture. Languages: English, Bahasa Indonesia, Japanese,
  Filipino. Synthetic fixtures only for Indonesian and Filipino text (named `synthetic_*`;
  never ship real MAGMA or PHIVOLCS text). Route: `POST /api/desk/notices {text}` ->
  `NoticeReading`; `GET /api/notices`.
- **Satellite Reader**: `read_satellite(volcano, frames, official_layers, llm) -> SatelliteReading`
  on the latest JMA `DUST_RGB` (and `B13_IR`) crops already fetched by `feeds/satellite.py`
  (georeferenced bbox). One lite call with the images and the JMA Ash RGB colour key as
  text. Output: `ash_visible yes|no|uncertain`, `so2_visible`, `obscured_by_cloud`,
  `boxes [{label ash|so2, box_2d [ymin,xmin,ymax,xmax] 0-1000}]`, `limits`. Code converts
  boxes to lat/lon polygons and bearing/distance from the vent. It is supporting evidence
  only: it may add to the Plume Reader's input (`LlmPart` text with its source id
  `SAT-<hash>`), never narrows anything, never sets a height. Gate: run only when the Plume
  Reader is about to be called for that volcano and the newest frame changed. WP9 wires it.

### WP4 Network recovery agent

Files: `tephra/recovery/{__init__,models,schedule,closures,solver,agent}.py`,
`tephra/agents/prompts/recovery.md`, `scripts/build_rfa_schedule.py`, `data/rfa/*.json`,
`tephra/api/routes_recovery.py`, tests. Adds the dependency `ortools` (Apache 2.0) to
`pyproject.toml` (WP4 may edit `pyproject.toml` and `uv.lock` for this only).

- **Data** (synthetic, generated with a fixed seed by the script, committed): fictional RFA
  fleet of 30 A320-family tails based CGK/SUB/DPS (+ a few at UPG/KNO), one operating day of
  120-150 flights on real airport pairs from `data/routes_apac.json` and `data/airports.json`
  among Java/Bali/Sumatra/Sulawesi/Lombok airports, rotations by tail, bank structure,
  seats and booked pax, crews paired to tails with report times. Everything labelled
  fictional. The template day is rolled into a two-day window (the clock's operating day and the next); a flight is keyed by number and service date (`RFA239/06SEP`).
- **Closures** (`closures.py`): an airport is closed while the hazard area (cone, and every
  official layer) at any level from the surface to FL100 comes within
  `recovery.airport_closure_radius_nm`, or its TAF/METAR has `VA`. Closure start/end from
  the cone validity and the official layers' valid times; code-written reason with source ids.
- **Solver** (`solver.py`): CP-SAT model of research/18d section 2.3 / 7: per free flight
  choose keep (with delay in 5-minute steps up to `recovery.max_delay_min`), cancel (with its
  pair), or move to another tail (swap); tails flow in time; minimum turn; frozen window;
  FDP limit; no departure/arrival at a closed airport during its window; objective = the
  policy's USD weights. Time limit `recovery.solve_time_limit_s`. If CP-SAT returns no
  feasible plan, the result is `NO_PLAN` with the solver status: no greedy substitute.
  Deterministic: `recovery.solve_work_s` of CP-SAT deterministic time, interleaved search,
  fixed workers and seed (the Krakatau window: about 15 s, the same plan every run).
- **Agent** (`agent.py`): an ADK agent on the lite model that is the planner of the
  recovery: tools `disruption()` (closures, affected flights, pax), `run_scenario(extend_min,
  protect_flights[], max_delay_min)` (calls the solver; scenarios: closure as forecast,
  +`scenario_extend_1_min`, +`scenario_extend_2_min`), `compare(scenario_ids)` and
  `submit_recommendation(scenario_id, rationale, risks[])`. The rationale is validated (every
  number/flight/airport must come from tool results). Result `RecoveryPlan` (DRAFT): chosen
  scenario, per-flight actions (DELAY n min / CANCEL / SWAP to tail / KEEP), totals (delay
  minutes, cancellations, pax affected, USD), the other scenarios, rationale. Dispatcher
  approves/edits/rejects on the Desk (audit `RECOVERY_PROPOSED`/`RECOVERY_DECIDED`); approval
  hands the plan to WP5 for crew and passenger messages. On demand only (Desk button, or
  WP9 triggers it once per new closure set).
- Routes: `GET /api/recovery` (latest plans), `POST /api/desk/recovery/run`,
  `POST /api/desk/recovery/{id}/approve|reject`.

### WP5 Crew and passenger messages + shift handover

Files: `tephra/comms/{__init__,models,messages,handover}.py`,
`tephra/agents/prompts/{messages,handover}.md`, `tephra/api/routes_comms.py`, tests.

- **Messages**: from an approved advisory (crew briefing) or an approved recovery plan
  (passenger notice per cancelled or delayed flight, crew notice per affected tail).
  Languages by route: Indonesian domestic -> Bahasa Indonesia + English; Japan -> Japanese +
  English. The model writes text with placeholders only for facts (`{FLIGHT}`, `{ROUTE}`,
  `{NEW_DEP_LOCAL}`, `{DELAY_MIN}`, `{REASON_SOURCE}`, `{CONTACT}`...); code fills them; the
  validator rejects any digit outside placeholders and any missing required placeholder
  (PM 89/2015 content list in research/18d section 7.5: status, reason with official source,
  new time or next update, rebook/refund options, assistance, what is not owed under force
  majeure — phrased neutrally). `CrewPaxMessage` DRAFT -> APPROVED/EDITED/REJECTED with
  compare-and-set versions like advisories; approved messages go to `outbound` with
  `destination="tephra-outbound"`. Audit `MESSAGE_DRAFTED`/`MESSAGE_DECIDED`.
- **Handover**: `draft_handover(runtime, since, outgoing, incoming) -> HandoverBrief`
  (WEST + I-PASS schema in research/18e section E); code gathers the facts (advisories and
  their states, AI failures, recovery plans, feeds, discrepancies, decisions from the audit
  log since `since`); one lite call writes the narrative fields with `source_ids`;
  validator as Ask. The receiver taps "Read back" -> audit `HANDOVER_ACKED`; refused while
  any draft is mid-decision.
- Routes: `GET /api/desk/messages`, `POST /api/desk/messages/draft {advisory_id|recovery_id}`,
  `POST /api/desk/messages/{id}/approve|edit|reject`, `POST /api/desk/handover`,
  `POST /api/desk/handover/{id}/ack`.

### WP6 Regulator paperwork: SRA and VAR drafts

Files: `tephra/docs/{__init__,models,sra,var}.py`, `tephra/agents/prompts/sra.md`,
`tephra/api/routes_docs.py`, tests.

- `draft_sra(runtime, region) -> SraDraft`: the sections of research/18b recommendation A,
  filled by code from TEPHRA's evidence; Gemini (lite, one call) writes only the narrative
  boxes, validated (numbers/ids from input). Unfilled fields stay visibly blank. The Indonesia
  overlay box for SE-DJPU 15/2026 says "per press reports of the circular; verify against
  the PDF". Header: `DRAFT - NOT AN APPROVED SRA - FOR HUMAN SIGN-OFF`. Doc 9974 is cited as
  First Edition 2012.
- `draft_var(runtime, flight_id) -> VarDraft`: the ICAO Model VAR layout (research/18b
  section 4) with items 1-5 pre-filled from ADS-B and the hazard (proxy flight labelled),
  items 6-16 blank "PILOT/DISPATCHER TO COMPLETE"; no model call (the model must not invent
  crew observations); plus the AIREP SPECIAL line. Follow-ups list.
- Sign-off: `POST /api/desk/docs/{id}/sign` (name, role) -> audit `DOC_SIGNED`. Docs render
  to a printable HTML page (`GET /docs/{id}` page served by WP10) from JSON
  (`GET /api/docs/{id}`, `GET /api/docs`).

### WP7 Backtest agent

Files: `tephra/backtest/{__init__,metrics,runner,report}.py`, `scripts/backtest.py`,
`docs/backtest/` (outputs), `tephra/agents/prompts/backtest.md`, tests.

- Runs each replay case in `data/replay/` deterministically on a replay clock in 30-minute
  steps (no live network), records TEPHRA's cone and the official-only area at each tick,
  and scores them against the official areas published later (research/18f section 7):
  coverage (POD), coverage gain over the official baseline, over-warning (1 - precision),
  incremental lead time at tau = 0.9, area ratio, Hausdorff km, centroid km, vertical hit;
  CSI/FMS as secondary. Floor check: `floor_violations == 0` on every tick, and no input
  timestamp after the tick's clock.
- Arms: `D` = stub plume reader (deterministic, always), `G` = Gemini plume reads replayed
  from the LLM disk cache when present; never spends more than `--max-calls` (default 0).
- One lite call writes `docs/backtest/REPORT.md` from `scorecard.json`; a validator checks
  every number in the report against the scorecard; a failed check leaves only the
  scorecard and says `AI UNAVAILABLE` (no template report).
- `GET /api/backtest` (WP9 mounts) serves the latest scorecard; the Wall shows a "Proof"
  panel (WP11).

### WP9 Integration (after WP1-WP7)

Owns `pipeline.py`, `scheduler.py`, `api/server.py`, `config.py`, `models.py`, `MODULES.md`,
`docs/ARCHITECTURE.md`, `README.md`, `.env.example`, `CLAUDE.md`: mounts routers, wires
Satellite Reader into the plume path (gated), JMA notices and verified pasted notices into
the live picture, reroutes into planning (computes `RerouteOption`s per exposed flight,
stores them, puts them on the Wall snapshot as `reroutes` FeatureCollection), recovery
trigger, budget SSE, CSP and `permissions-policy: microphone=(self)` on `/desk` only,
settings (`TEPHRA_MODEL_TTS`, upload limits), and documents everything (including the
removal of fallbacks).

### WP10 Desk UI, WP11 Wall UI

Desk (`tephra/web/desk*`, `tephra/web/desk/*`): a bottom tab bar — **Queue** (advisories,
AI failures "handle by hand" with a Mark handled sheet, message drafts, recovery plans),
**Ask** (chat with streamed-looking answer cards, evidence chips that open the verbatim
item, "How I answered" step strip, push-to-talk mic using MediaRecorder -> Gemini, speaker
button that plays Gemini TTS), **Network** (recovery board: closures, scenarios compared,
per-flight actions, approve), **Docs** (SRA, VAR, handover with read-back). Reroute shown on
advisory review as a mini map + route string. Notice paste sheet. AI budget chip.
Wall (`tephra/web/index.html`, `wall.js`, `wall/*`, `wall.css`): reroute polylines with
turn-point labels, satellite-check card with box overlay, notices with language badge and
"verified" state, recovery board panel, Proof panel (backtest), AI activity tray (8 chips with
status and budget left). Both follow `docs/UI-DESIGN.md` tokens, CSP (no inline script,
`textContent` only), keyboard and screen-reader access, phone width 360 px.
