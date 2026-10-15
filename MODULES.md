# TEPHRA module contract

This file is the contract that every module is coded against in parallel. If your code
needs something from another module, call it exactly as written here. If something you
need is missing, write a private helper inside your own files; do not edit files you do
not own. Shared shapes live in `tephra/models.py`; settings and constants in
`tephra/config.py`. Read both before you start: their docstrings are part of this contract.

Background reading: `docs/ARCHITECTURE.md` (the system and its safety rules) and the
research notes in `research/` (read-only). Research that changed this contract:
`research/05` (feed terms: frame captions, no NICT imagery for Gemini), `research/06`
(free-tier quota, ADK 2.x), `research/07` (parsing and dispatch rules), `research/10`
(Gemini 3 temperature, Google's quota day, the plume eval protocol), `research/12` (raw
Himawari split window), `research/13` (what counts as a contradiction, Darwin VAAC source),
`research/14` (30-day census: SILENCE and SIGMET hand-over rules), `research/18a` to `18f`
(reroute, regulator paperwork, JMA and satellite reading, recovery and messages, shift
handover and Ask, backtest). `docs/EXTENSIONS.md` is the design contract the extension
modules (sections 5.11 to 5.17) were built against.

## 1. Where things live

| Area | Files |
|---|---|
| architect (contract files) | `pyproject.toml`, `MODULES.md`, `CLAUDE.md`, `README.md`, `docs/*.md`, `docs/ARCHITECTURE.md`, `docs/EXTENSIONS.md`, `tephra/__init__.py`, `tephra/config.py`, `tephra/models.py`, `tephra/feeds/__init__.py`, `tephra/feeds/base.py`, `tephra/store/base.py`, `tephra/util/__init__.py`, `tephra/util/timeutil.py`, `tephra/util/hashing.py`, `tephra/util/events.py`, `tephra/policy.py`, `data/policy/policy_a.json`, `tests/test_contract.py`, `tests/test_policy.py` |
| feeds-text | `tephra/feeds/sigmet.py`, `tephra/feeds/vona.py`, `tephra/feeds/vaac.py`, `tephra/feeds/taf.py`, `tests/test_feeds_text.py`, `tests/test_live_feeds_text.py`, `tests/test_vona_archive.py` |
| feeds-geo | `tephra/feeds/adsb.py`, `tephra/feeds/winds.py`, `tephra/feeds/satellite.py`, `tephra/feeds/volcanoes.py`, `tephra/feeds/airports.py`, `data/volcanoes.json`, `data/airports.json`, `tests/test_feeds_geo.py`, `tests/test_live_feeds_geo.py` |
| science | `tephra/science/__init__.py`, `tephra/science/hsd_segments.py`, `tephra/science/btd.py`, `tests/test_science.py` |
| geo | `tephra/geo/__init__.py`, `tephra/geo/units.py`, `tephra/geo/cone.py`, `tephra/geo/exposure.py`, `tephra/geo/fuel.py`, `tests/test_geo.py`, `tests/test_geo_props.py` |
| reconcile-plume | `tephra/reconcile/__init__.py`, `tephra/reconcile/discrepancies.py`, `tephra/agents/__init__.py`, `tephra/agents/llm.py`, `tephra/agents/schemas.py`, `tephra/agents/budget.py`, `tephra/agents/quota.py`, `tephra/agents/plume_reader.py`, `tephra/agents/prompts/plume_reader.md`, `tests/test_discrepancies.py`, `tests/test_plume_reader.py`, `tests/test_quota.py` |
| planner-drafter | `tephra/agents/exposure_planner.py`, `tephra/agents/dispatch_drafter.py`, `tephra/agents/validators.py`, `tephra/agents/adk_app.py`, `tephra/agents/prompts/planner.md`, `tephra/agents/prompts/drafter.md`, `tests/test_drafter.py`, `tests/test_planner.py` |
| core | `tephra/pipeline.py`, `tephra/scheduler.py`, `tephra/ai_worker.py`, `tephra/agents/answers.py`, `tests/test_ai_worker.py`, `tests/test_ai_answers.py`, `tephra/feeds/registry.py`, `tephra/recovery/network.py`, `tephra/store/__init__.py`, `tephra/store/sqlite_store.py`, `tephra/store/firestore_store.py`, `tephra/desk/__init__.py`, `tephra/desk/approvals.py`, `tephra/desk/audit.py`, `tephra/replay/__init__.py`, `tephra/replay/cases.py`, `tests/test_approvals.py`, `tests/test_pipeline.py`, `tests/test_replay.py`, `tests/test_store.py` |
| api | `tephra/main.py`, `tephra/api/__init__.py`, `tephra/api/server.py`, `tephra/api/auth.py`, `tephra/api/sse.py`, `tests/test_api.py`, `tests/test_integration.py` |
| duty | `tephra/agents/duty_officer.py`, `tephra/agents/adk_runtime.py`, `tephra/agents/prompts/duty_officer.md`, `tephra/duty.py`, `tephra/api/routes_duty.py`, `tests/test_duty_officer.py` |
| reroute | `tephra/geo/reroute.py`, `tephra/geo/fuel.py` (`reroute_line`), `tephra/feeds/routes.py`, `scripts/build_routes.py`, `data/routes_apac.json`, `tests/test_reroute.py`, `tests/test_routes.py`, `tests/test_reroute_agents.py` |
| ask | `tephra/agents/ask.py`, `tephra/agents/voice.py`, `tephra/agents/prompts/ask.md`, `tephra/api/routes_ask.py`, `tests/test_ask.py` |
| notices | `tephra/feeds/jma_volcano.py`, `tephra/agents/notice_reader.py`, `tephra/agents/satellite_reader.py`, `tephra/agents/prompts/{notice_reader,satellite_reader}.md`, `tephra/api/routes_notices.py`, `tests/test_notices.py`, `tests/test_satellite_reader.py`, `tests/fixtures/{jma,notices}/` |
| recovery | `tephra/recovery/{__init__,models,schedule,closures,solver,agent,tools,decisions}.py`, `tephra/agents/prompts/recovery.md`, `tephra/api/routes_recovery.py`, `scripts/build_rfa_schedule.py`, `data/rfa/*.json`, `tests/test_recovery.py` |
| comms | `tephra/comms/{__init__,models,messages,handover}.py`, `tephra/agents/prompts/{messages,handover}.md`, `tephra/api/routes_comms.py`, `tests/test_comms.py` |
| regdocs | `tephra/regdocs/{__init__,models,common,runtime,evidence,narrative,sra,var,registry}.py`, `tephra/agents/prompts/sra.md`, `tephra/api/routes_regdocs.py`, `tests/test_regdocs.py` |
| backtest | `tephra/backtest/{__init__,models,metrics,runner,report}.py`, `tephra/agents/prompts/backtest.md`, `tephra/api/routes_backtest.py`, `scripts/backtest.py`, `docs/backtest/`, `tests/test_backtest.py` |
| web-wall | `tephra/web/index.html`, `tephra/web/wall.js`, `tephra/web/wall/*.js`, `tephra/web/wall.css`, `tephra/web/data/`, `tephra/web/og.{svg,png}`, `tephra/web/mapui.css` (map controls, shared), `tephra/web/guide.{html,js,css}` (the guide page) |
| web-desk | `tephra/web/desk.html`, `tephra/web/desk.js`, `tephra/web/desk/*.js`, `tephra/web/desk.css` |
| connect | `tephra/desk/connections.py`, `tephra/desk/sample_feed.py`, `tephra/api/routes_connect.py`, `scripts/push_sample.py`, `tephra/web/connect.{html,js,css}`, `tephra/web/topnav.css` (the nav every page shares), `tests/test_connect.py` (airline data connections: section 5.20) |
| crew | `tephra/geo/crew_area.py`, `tephra/desk/crew_reports.py`, `tephra/api/routes_crew.py` (crew reports of ash: section 5.19) |
| ops-evals | `Dockerfile`, `.dockerignore`, `.gcloudignore`, `.env.example`, `deploy/_common.sh`, `deploy/cloudbuild.yaml`, `deploy/cloudrun.sh`, `deploy/ar-cleanup.json`, `scripts/live_smoke.sh`, `deploy/scheduler.sh`, `deploy/secrets.sh`, `deploy/firestore.rules`, `deploy/README.md`, `deploy/github_deploy_setup.sh`, `deploy/deploy_paths.py`, `deploy/report_interrupted.sh`, `.github/workflows/ci.yml`, `.github/workflows/deploy.yml`, `scripts/record_replay.py`, `scripts/count_traffic.py`, `scripts/count_model_calls.py`, `scripts/plume_eval.py`, `scripts/make_plume_cases.py`, `scripts/free_model_check.py`, `scripts/*.mjs`, `scripts/public_export.py`, `deploy/public/`, `evals/plume/README.md`, `evals/free_models/`, `data/replay/README.md`, `tests/test_scripts.py`, `tests/test_record_replay.py`, `tests/fixtures/ops_evals/` |

Each module may also create test fixtures under `tests/fixtures/<module_key>/` (e.g.
`tests/fixtures/feeds_text/`). There is **no shared `tests/conftest.py`**: each test file
defines its own fixtures. Fixtures may be copied from `research/data/census/raw/` or typed
from texts quoted in `research/13`.

## 2. Layering (who may import whom)

Import only from a lower layer (or from your own files in the same layer).

| Layer | Modules |
|---|---|
| L0 | `tephra.util.*`, `tephra.models`, `tephra.config`, `tephra.policy` (config and policy import models; models never import either) |
| L1 | `tephra.feeds.base`, `tephra.store.base`, `tephra.geo.*` (`geo.reroute` included) |
| L2 | `tephra.feeds.{sigmet,vona,vaac,taf,adsb,winds,satellite,volcanoes,airports,routes,jma_volcano}`, `tephra.science.*` |
| L3 | `tephra.reconcile.*`, `tephra.agents.{quota,llm,schemas,budget,answers}` (`quota` and `answers` import `tephra.store.base` only) |
| L4 | `tephra.agents.{adk_runtime,plume_reader,validators,exposure_planner,dispatch_drafter,adk_app,satellite_reader,notice_reader,ask,voice,duty_officer}`, `tephra.recovery.{models,schedule,closures,solver,tools,agent,network}` |
| L5 | `tephra.store.{sqlite_store,firestore_store}` and `tephra.store` (the factory), `tephra.desk.*`, `tephra.replay.*`, `tephra.recovery.decisions`, `tephra.comms.*`, `tephra.regdocs.*` |
| L6 | `tephra.feeds.registry`, `tephra.duty`, `tephra.ai_worker`, `tephra.pipeline`, `tephra.scheduler` (`tephra.duty` reaches the runtime only through its methods and names `Runtime` for type checking only) |
| L7 | `tephra.api.*`, `tephra.main`, `tephra.backtest.*` (the runner builds a `Runtime`) |

The feature route modules (`tephra.api.routes_*`) import `DeskSession`, `RuntimeDep` and `_json`
from `tephra.api.server`, so `create_app` imports them inside `_include_feature_routers`, never at
the top of `server.py`. The library modules above take the runtime as a Protocol
(`AskRuntime`, `CommsRuntime`, `HandoverRuntime`, `DocsRuntime`, `NetworkRuntime`) instead of
importing `tephra.pipeline`.

Package `__init__.py` files must stay import-light: no network, no heavy SDK imports
(`google.adk`, `google.cloud`, `satpy`) at package import. Import those inside the module
or function that needs them.

## 3. Conventions every module follows

**Python.** 3.12, full type hints, pydantic v2 models from `tephra.models`, small functions,
docstrings only for a non-obvious why. No dead code, no TODO stubs that pretend to work. If
something cannot be verified without running it, implement it fully and leave a one-line
comment naming the assumption. Ruff config is in `pyproject.toml` (line length 100;
`DTZ` is on, so every datetime must be timezone-aware).

**Settings.** Library functions take `settings: Settings` (or plain values) as arguments.
Only composition roots call `get_settings()`: `tephra.main`, `tephra.api.server.create_app`
(when no settings are passed) and `tephra.agents.adk_app` (to build `root_agent` at import).
`tephra.pipeline.create_runtime` takes the settings it is given; `scripts/*` build their own
`Settings`. Tests build `Settings(_env_file=None, **overrides)`; they never read `.env`.

**Time.** All datetimes are aware UTC. Use `tephra.util.timeutil`: `now()` for the current
time on the active clock (REPLAY moves it), the parsers for feed formats, `to_iso`,
`compact`, `hhmmz`. Never call `datetime.now()` / `utcnow()` directly in library code.
Tests use `with use_clock(FixedClock(...)):`.

**Units and directions.** As documented at the top of `tephra/models.py`: units in field
names; heights compared on one scale (FL x 100 = ft, AMSL vs pressure altitude ignored and
said so); `*_toward_deg` is direction of motion, `WindLevel.from_deg` is meteorological;
plume sectors sweep clockwise from `bearing_from_deg` to `bearing_to_deg`; GeoJSON is
`(lon, lat)`.

**Provenance and ids.** Every feed record carries `Provenance` built with
`FetchResult.provenance(source_id, issued_at=..., valid_from=..., valid_to=...)`. Ids are
built with `make_source_id(KIND, *parts)` and times with `timeutil.compact(dt)`:

| Record | `source_id` recipe | Example |
|---|---|---|
| Sigmet | `SIGMET:{fir_id}:{series_id}:{compact(valid_from)}` | `SIGMET:WAAF:12:20261007T1030Z`, `SIGMET:WAAF:12_AREA_2:20261007T1030Z` |
| Vona | `VONA:{source_slug(volcano_name)}:{compact(issued_at)}` | `VONA:SEMERU:20260923T2221Z` |
| VaacAdvisory | `VAA:{vaac}:{volcano_number or source_slug(volcano_name)}:{advisory_nr}` | `VAA:TOKYO:282080:2026/249` |
| Taf | `TAF:{icao}:{compact(issued_at)}` | `TAF:WARR:20261010T0500Z` |
| Metar | `METAR:{icao}:{compact(observed_at)}` | `METAR:WARR:20261010T0530Z` |
| AdsbSnapshot | `ADSB:{lat:.3f}:{lon:.3f}:{compact(fetched_at, seconds=True)}` | `ADSB:-8.200:113.600:20261010T053012Z` |
| WindProfile | `WINDS:{lat:.2f}:{lon:.2f}:{compact(valid_at)}` | `WINDS:-8.11:112.92:20261010T0600Z` |
| SatelliteFrame | `FRAME:{product}:{volcano_id}:{compact(observed_at)}` | `FRAME:DUST_RGB:263300:20261010T0530Z` |
| BtdResult | `BTD:{volcano_id}:{compact(scan_start)}` | `BTD:263300:20261010T0530Z` |

`make_source_id` writes spaces in a part as `_`. Other ids use `stable_id(prefix, *parts)`
(deterministic) as each model's field description says: discrepancies `D-` (8 chars),
assessments `PA-`, cones `CONE-`, plans `PLAN-`, dedupe keys `DD-`. Advisory ids are
`"adv_" + uuid4().hex[:12]`; audit and outbound ids are `uuid4().hex`.

**Errors.** Feed fetchers let `FetchError` propagate (the registry records it). Parsers raise
`ValueError` for input they cannot read; a fetcher that parses many items skips a bad item,
logs it with `logging.getLogger(__name__).warning`, and keeps the rest. A fetcher that asks
several URLs never reports an outage as an empty answer: Darwin VAAs and satellite frames
raise `FetchError` when nothing came back, and ADS-B raises `AdsbPointsFailed` when any point
failed (section 5.2). Agents never raise on model failure: they repair once and then return an explicit
failure, `AI UNAVAILABLE: <reason>`, and nothing is substituted (next paragraph).

**No fallbacks.** When a model call fails, is over budget, or its answer fails the code's checks
after at most one repair, the feature returns `AI UNAVAILABLE: <reason>`: the trace line, the
stored record and the HTTP response (503 `{"error": "ai_unavailable", "message": ..., "detail":
...}`) all say so, and no canned answer, rule-based stand-in, template, greedy heuristic or
browser speech takes its place. Three things are not fallbacks: the cone is always built on the
official polygons (binding, whatever the model does); the reroute geometry, the CP-SAT solver, the
JMA XML parser and the backtest metrics are the primary design of those steps; and
`TEPHRA_LLM=stub`, the offline test mode, gives every model step a deterministic answer labelled
`NO MODEL` (voice transcription and speech have none: they answer `AI UNAVAILABLE`).

**Logging.** `logging.getLogger(__name__)`; never log secrets, PINs, cookies or API keys;
never log raw request bodies of desk endpoints.

**Async.** I/O functions are `async def`. CPU-heavy work (HSD decoding, PNG rendering) is a
plain function that core calls with `asyncio.to_thread`. Event-bus `publish` is called only
from the event-loop thread.

**Tests.** `pytest` with `asyncio_mode = "auto"`. No network in default tests (mark live
calls `@pytest.mark.network`, Gemini calls `@pytest.mark.gemini`; both are deselected by
default). HTTP is faked with `httpx.MockTransport` passed to `HttpSource(transport=...)`, or
by a small in-test `Source` that returns canned `FetchResult`s. `TEPHRA_LLM=stub` is the
default, so tests never need a key.

**Data minimisation.** Gemini receives public feed content only: no dispatcher names, no
audit entries, no registrations, and no NICT true-colour frames (research/05 does not clear
them for the model). Only aircraft with airline-style callsigns (`Aircraft.airline`) become
proxy flights.

## 4. Contract files (already written; read them)

### 4.1 `tephra.util.timeutil`

`UTC`, `ensure_utc(dt)`, `now()`, `now_exact()`, `get_clock()`, `set_clock(clock)`,
`use_clock(clock)`; clocks `SystemClock()`, `FixedClock(at)` (`.set`, `.advance`),
`ReplayClock(start, end, *, speed=1.0, loop=True, begin=None, quantum_s=0)` (starts at `begin`,
clamped into the window, else at `start`; with `loop` it wraps back to `start` after `end`).
With `quantum_s > 0` (`TEPHRA_REPLAY_QUANTUM_S`) the clock's `now()` is floored to that many
seconds and the quanta are anchored to the wall clock's own boundaries (`_t0` is moved back by
`time.time() % quantum_s`), so a tick Cloud Scheduler fires at :00 plus jitter sees the same
replay minute on every loop and every deploy and finds its kept answers; `ReplayClock.now_exact()`
keeps the seconds. The module-level `now_exact()` is the replay clock's exact instant, or `now()`
on any other clock: the Wall clock, heartbeats and `SystemState.now` use it, ticks and the AI
worker use `now()`. The `Clock` protocol is unchanged (`now()` only). Parsers:
`parse_slash_dtg("20260923/2221Z")`, `parse_day_time("25/1800Z", ref)`,
`parse_ddhhmm("251252", ref)`, `parse_hhmmz("1010Z", ref)`, `resolve_day(day, hour, minute,
ref)` (hour 24 accepted), `parse_iso(str | int | float | datetime)` (naive = UTC, epoch s or
ms). Formatters: `to_iso(dt)` -> `2026-10-07T10:32:00.000Z`, `iso_times(value)` (every
datetime inside a mapping, list or tuple written by `to_iso`), `compact(dt, *,
seconds=False)` -> `20261007T1032Z`, `hhmmz(dt)` -> `1032Z`, `ddhhmmz(dt)` -> `071032Z`,
`slash_dtg(dt)` -> `20261007/1032Z`. Arithmetic: `minutes_between(a, b)`, `age_s(then,
at=None)`, `floor_minutes(dt, minutes)`.

### 4.2 `tephra.util.hashing`

`sha256_bytes`, `sha256_text`, `canonical_json`, `sha256_json`, `short_hash(digest, 12)`,
`combine_hashes(iterable)` (order-independent), `stable_id(prefix, *parts, length=12)`,
`proxy_flight_number(hex)` -> `RFA4821`. `canonical_json` (sorted keys, no whitespace) writes
every datetime with `to_iso` (through `iso_times`), so a hash never depends on how pydantic
would print a raw datetime.

### 4.3 `tephra.util.events`

`get_bus() -> EventBus`. `EventBus(history_per_event=200)`. `EventBus.publish(name, data) ->
Event` (data: model, mapping or list; serialised to JSON-safe values, every datetime written
by `to_iso`), `.subscribe(maxsize=256) -> Subscription` (`ValueError` when `maxsize < 1`: an
unbounded queue would never drop), `.unsubscribe(sub)`, `.recent(name, limit=50) ->
list[Event]` (oldest first), `.last(name)`, `.subscriber_count`. `Subscription` is an async
context manager and async iterator; `await sub.get(within_s=15)` returns `None` on timeout.
A full queue drops its oldest event and counts it in `Subscription.dropped`, so a slow
subscriber never blocks a publisher. `Event(id: int, name: str, data: Any, at: datetime)`.
Event names are `SseEvent` values.

### 4.4 `tephra.models`

All shared models, enums and helpers. Highlights you will use:
`TephraModel`, `UtcDatetime`, `Position`, `PRESSURE_LEVEL_FL`; enums `FeedId`, `RunMode`,
`AviationColor`, `VaacCentre`, `FrameProduct`, `BtdIndicator`, `EvidenceState`,
`DiscrepancyKind`, `Severity` (+ `DISCREPANCY_SEVERITY`), `PlumeMode`, `ActionKind`
(+ `ALLOWED_ACTIONS`), `AircraftCategory`, `AdvisoryStatus` (+ `TERMINAL_STATUSES`),
`AuditAction`, `FeedStatus`, `TraceStage`, `TraceActor`, `SseEvent`, `LlmBackendName`, `RerouteKind`,
`RerouteStatus`;
GeoJSON `GeoPoint`, `GeoLineString`, `GeoPolygon`, `GeoMultiPolygon`, `Geometry`,
`polygon_from_latlon`, `point`, `feature`, `feature_collection`, `EMPTY_FEATURE_COLLECTION`,
`BBox` (`corners_lonlat()` is MapLibre image order), `blob_url(key)`; ids `source_slug`,
`make_source_id`, `Provenance`, `SourceRef.from_provenance`; catalogues `Volcano`,
`VolcanoFile`, `Airport`, `AirportFile`, `AdsbQueryPoint`, `Region`; feed records `Sigmet`
(`is_valid`), `Vona` (`is_recent`), `VaLayer`, `VaacStep`, `VaacAdvisory` (`valid_until`,
`is_current`), `TafPeriod`, `Taf`, `Metar`, `Aircraft` (`proxy_flight`, `airline`),
`is_airline_callsign`, `AdsbSnapshot`, `WindLevel` (`toward_deg`), `WindProfile`,
`WindForecast`, `SatelliteFrame`, `BtdResult`; reasoning `Discrepancy`, `OfficialLayer`
(`is_valid`, `to_feature`), `Situation` (`provenances`, `source_ids`, `official_valid_now`,
`official_top_ft`, `official_base_ft`, `input_hash`), `DisagreementReading`, `PlumeEstimate`
(`sector_width_deg`), `PlumeAssessment`, `HazardCone` (`label`, `to_features`), `FuelLine`,
`ExposedFlight`, `FlightRoute`, `RerouteOption`, `SupportingEvidence`, `AiFailure`; operator policy `OperatorPolicy` (`named_values`, `content_hash`),
`PolicyValue`, `ExposurePolicy`, `AlternatePolicy`, `PlannerPolicy`, `FuelPolicy`,
`ReroutePolicy`, `RecoveryPolicy`, `SourceRule`, `PolicyCitation`, `PolicySummary` (`of`); `AlternateCheck`, `AlternateCandidate`, `PlannerContext`,
`PlannerDecision`, `ToolCallRecord`, `PlannedAction`, `DraftText`, `Advisory`
(`final_body`, `final_text`), `OutboundMessage`, `AuditEntry`, `FeedHealth`, `TraceEvent`
(`TraceEvent.new(...)`), `TraceSink`, `TickReport`, `ReplayRecord`, `ReplayCase`; Wall and
API shapes in section 8.

Enum additions of the extensions: `FeedId.JMA_VOLCANO` (`jma_volcano`); `ActionKind.REROUTE`;
`AuditAction` `AI_FAILED`, `AI_FAILURE_HANDLED`, `ASKED`, `NOTICE_READ`, `RECOVERY_PROPOSED`,
`RECOVERY_DECIDED`, `MESSAGE_DRAFTED`, `MESSAGE_DECIDED`, `DOC_DRAFTED`, `DOC_SIGNED`,
`HANDOVER_ACKED`; `TraceStage` `SATELLITE`, `NOTICE`, `ASK`, `RECOVERY`, `MESSAGES`, `DOCS`;
`SseEvent` `reroutes`, `routes` (the usual routes of the flights heading in), `ai_failure`, `satellite`, `notice`, `recovery`, `message`, `doc`, `budget`, `push`,
`duty`; `TraceStage.DUTY`; `PlumeAssessment.outcome` `PENDING` (a plume read queued for the Duty
Officer: official products only until it runs, never reused as current). Duty Officer models:
`DutyItemKind` (ASSESS, PLAN, RECOVER, SRA), `DutyItem`, `DutyPriority`, `DutyBrief`,
`DutyDispatch`, `DutyDeferral`, `DutyRun`; `AiFailure.stage` adds `duty_officer`;
`TickReport.duty_runs` (the AI worker's report; a tick runs none); `WallSnapshot.duty` (the newest run).
`Advisory.drafted_at: UtcDatetime | None`: when the body was written, never later than
`created_at` (the time of the advisory's facts); the same model's body for materially the same
plan keeps the time it was written (section 5.7, model answers). None only on advisories stored
before the field; the UI then shows `created_at`. The same holds for the other model texts:
`DutyRun.decided_at` (when the Duty Officer model made the run's decisions and wrote its brief;
a run that made the same model's decisions again keeps their time; None: `finished_at`),
`AskAnswer.answered_at` (when the model gave the answer; None for NO MODEL answers),
`SraDraft.narrative_at` and `HandoverBrief.narrative_at` (when the model wrote the narrative
parts; None: `created_at`). The UI shows these times for those texts (the Duty Officer's run and
brief time, a document's "Parts drafted by TEPHRA Assistant <time>" line). No model carries a
label saying an answer was reused.
`PlannerContext.route` and `.reroutes` carry the published route and the code's lateral options;
`PlannerDecision.reroute_id` names the chosen option; `Advisory.reroute` embeds it.
Crew reports (section 5.19): `AuditAction` `CREW_REPORT_ENTERED`, `CREW_REPORT_WITHDRAWN`,
`CREW_REPORT_EXPIRED` and `DOC_WITHDRAWN` (a crew report message withdrawn with its report);
`SseEvent.CREW` (`crew`); `CrewCue` (+ `CREW_CUE_TEXT`, `CREW_AREA_CUES`,
`CREW_SMELL_AND_HAZE`), `CrewReportKind`, `CrewPositionBasis`, `CrewArea` (`is_valid`),
`CrewReport` (`flight`), `CrewReportState`, `CrewReportView`, `CrewFlag`, `CrewFeatureProps`,
`CrewPicture`, the labels `CREW_AREA_LABEL`, `CREW_FLAG_LINE`, `CREW_REPORTER_LINE`,
`CREW_OUTSIDE_LINE`, `NO_CATALOGUED_VOLCANO`;
`WallSnapshot.crew`; `AircraftFeatureProps.crew_report`; `Advisory.decision_reason` (the
dispatcher's written reason when a rule asks for one, None otherwise); `DecisionRequest.reason`
(optional, at most 500 characters; `EditRequest` inherits it); `CrewReportPolicy` and
`OperatorPolicy.crew_reports`.
`Situation.supporting` holds texts other model steps wrote (the Satellite Reader's), each under
its own source id; they are included in `source_ids()` so the Plume Reader may cite them, and
left out of `input_hash`, so a new picture alone never triggers a Plume Reader call.
`PlannedAction.decision` is None when the model gave no plan that passed the checks (outcome
`MODEL_FAILED`); `AiFailure` is then the Desk's item. `PlumeAssessment` and `PlannedAction`
carry `input_tokens` and `output_tokens` (`int | None`): the sum over the model calls that
reported usage, None when none did (stub, `OFFICIAL_ONLY`, a cache hit, a call that failed
before Gemini answered); never estimated. `Advisory.input_tokens` and `output_tokens` are the
drafter's prompt and answer tokens for a fresh draft, None on a reused body (and on older
drafts); `DutyRun.input_tokens` and `output_tokens` the same for a Duty Officer run (None until
the coordinator reports them). Feature-owned models (recovery, comms,
regdocs, backtest, ask, notices, satellite) live in their own modules and subclass
`TephraModel`.

`Situation.input_hash` combines each SIGMET, VONA and VAA's source id with the SHA-256 of its
own `raw_text`, plus the BTD indicator; it never uses `provenance.sha256`, which hashes the
whole HTTP response (every VA SIGMET worldwide shares one). `ReplayCase` rejects a
`recorded_to` earlier than its `recorded_from`. `model_dump(mode="json")` keeps NaN and
infinities; the store and the SSE stream write them as null.

The policy models (`PolicyModel` and its subclasses) are frozen and refuse unknown keys
(`extra="forbid"`), unlike `TephraModel`: a misspelt value name stops startup instead of
leaving the code without that value. `OperatorPolicy` checks that every cited id names one
of its `citations`, that every value is zero or more and the names in
`POSITIVE_POLICY_VALUES` above zero, and that `divert_within_min <= hold_within_min` and
`level_band_fl <= max_change_level_fl`. `Advisory.policy_id`, `policy_version` and
`policy_hash` (the first 12 hex characters of `OperatorPolicy.content_hash()`) record the
policy a draft was made under (None on drafts from before each field).
`Advisory.replay_case_id` names the replay case a REPLAY draft was made from (None when live).
`ReplayCase.reconstructed` (a plain property, not serialised) is True when the manifest's
`notes` start with `Reconstructed from archives`. `OutboundMessage` carries `replay`,
`replay_case_id`, `policy_id`, `policy_version` and `policy_hash` copied from the advisory,
and `queued_wall_at`, the wall-clock time it was queued (`queued_at` follows the REPLAY
clock); `queued_wall_at` is None only on records written before the field, and on approved
crew and passenger messages until `comms.messages` sets it.
`approve` and `edit_and_approve` store `reason` as `decision_reason` (the caller checks
whether a rule asks for one: section 8.5).
`Advisory.urgency_bucket` records the urgency bucket the draft was made in (core's
`_urgency`: 0 inside the cone, then one more per time limit the entry lies beyond; None on
older drafts). `PlannerContext` carries the planner block's values as plain ints
(`level_search_ft`, `level_band_fl`, `max_change_level_fl`, `divert_within_min`,
`hold_within_min`) beside `vertical_margin_ft`; it never carries the policy id or version.

`StoreHealth` `{ok, last_ok_at, last_error, last_error_at}` is the database as the runtime last
found it, in wall-clock time: `ok` turns False on a failed checked read or write and True again
on the next successful write; `last_error` is the newest error (cut to 300 characters) and
`last_error_at` when the current run of failures began. `SystemState.store` carries it (a
`StoreHealth()` default, ok with no times, where nothing reports one), and
`SystemState.draft_count` counts the open drafts of the mode playing (`Runtime.open_drafts`, the
list the Desk shows), None when they could not be read (never an older count). The database is not a `FeedId`: `due_feeds` and the pollers iterate `FeedId`.

AI failures and replay runs (13 Oct 2026). A REPLAY plays its recording again from the start on
every run (a process start, a switch to REPLAY, a loop), so records stamped on the replay clock
cannot tell one run from the next. `AiFailure.recorded_wall_at` and `DutyRun.recorded_wall_at`
are the wall-clock time the record was stored (`created_at` and `started_at` follow the REPLAY
clock); None only on records stored before the field. `AiFailure.closed_at` and `closed_reason`
are set by code when a failure no longer stands (section 5.7, `desk.failures`); a dispatcher's
decision is `handled_by`, `handled_at` and `handled_note`, which code never fills.
`AiFailure.open` (a property, not stored) is true while neither is set. `AuditAction.AI_FAILURE_CLOSED`
records code's closing, always under the system actor, with the reason as the note.

Visitor, chain and demo fields (15 Oct 2026; every one optional, with today's behaviour as
its default). `SessionRole = Literal["dispatcher", "visitor"]` beside `RunMode`;
`SessionInfo.role` (default `dispatcher`) and `SessionInfo.sid` (the session id from the
cookie, None on older sessions, so visitor caps are counted per session). `AuditAction`
`VISITOR_ENTERED` (a visitor entered the Desk) and `REPLAY_RESTARTED` (the replay was started
again from the window's start). `AuditEntry.seq`, `prev_sha256` and `sha256` (all None on the
base model; `tephra.desk.audit`'s `ChainedAuditEntry` requires them) name the entry's place in
the hash chain. `Advisory.plan_key` is the first 16 hex characters of the planner question's
material hash, reserved for planning keyed by it (None today; section 5.7).
`ReplayRecord.reconstructed` (default False) marks a replay body rebuilt from the notice's
facts (CP-05d); `url` and `fetched_at` stay the original fetch's. `CloudInfo` (`platform`
`cloud-run` | `local`, `service` = `K_SERVICE`, `revision` = `K_REVISION`, `region` =
`settings.cloud_region`, `store`, `scheduler` `cloud-scheduler` | `in-process`, `secrets`
`secret-manager` | `environment` from `settings.secrets_source` and never inferred,
`model_access` `gemini-api` | `none` for the stub, `instances` `one`) is where the service
runs; `ChainHead` (`seq`, `sha256`, `checked_at`, `entries`, `intact`, `problems`) is the
verified head of the audit chain (`tephra.desk.audit.verify_head`). `SystemState.features`
(the names in `Settings.features`, for `wall/features.js`), `SystemState.cloud`
(`CloudInfo | None`), `SystemState.audit` (`ChainHead | None`) and `SystemState.visitor_access`
(True when a visitor may enter the Desk without a PIN while a replay plays) carry them to the
pages. `RerouteOption.id` is `stable_id('RR', flight_id, kind, sha256 of route string and
level)`: the same route under a new cone keeps its id.

### 4.5 `tephra.config`

`Settings` (every env var; see the class), `get_settings()`, `apply_process_env(settings)`,
`PROJECT_ROOT`, `REGIONS`, `RegionKey`. Product constants `AIRLINE_CODE`, `AIRLINE_NAME`,
`DISCLAIMER`, `NO_MODEL_LABEL`, `REPLAY_BANNER_TEMPLATE`. Safety constants (not
configurable): `MAX_PLUME_EXTENT_KM=500`, `MAX_SECTOR_WIDTH_DEG=180`, `MAX_HORIZON_H=18`,
`FEED_CLOCK_SLACK=timedelta(minutes=5)`, `MIN_SECRET_CHARS=32`, `ADVISORY_BODY_MAX_CHARS=400`,
`MAX_BODY_BYTES=16 KiB` (the request-body cap) and `MAX_NOTICE_BODY_BYTES=32 KiB` (a pasted notice:
up to 6,000 characters, three bytes each in Japanese).
Operator values (margins, buffers, minima, thresholds) are not here: they live in the policy
file (section 4.8). `MOVED_TO_POLICY` names the former settings `TEPHRA_VERTICAL_MARGIN_FT`
and `TEPHRA_ALTERNATE_SEARCH_NM`; `Settings` refuses to start while either is set in the
environment or `.env`, because it would otherwise ignore them silently.

Rules: `Settings` ignores empty env values (`env_ignore_empty=True`), so a `KEY=` line copied
from `.env.example` means unset, not an empty secret. `session_secret` and `task_token`, when
set, must hold at least `MIN_SECRET_CHARS` characters after stripping, or `Settings` raises.
`FEED_CLOCK_SLACK` is how long after "now" a product may be stamped and still count as
issued; `reconcile.select_records` and `geo.cone.official_layers` share it, or a VAAC's
polygons would drop out of the cone for a tick. `replay_start` (`TEPHRA_REPLAY_START`) is the
UTC time the replay clock starts at, clamped into the case window. `replay_end`
(`TEPHRA_REPLAY_END`, UTC, default unset) ends a looping window that starts at `replay_start`:
`Settings` refuses it without `replay_start` and `replay_case`, when `replay_start` has no UTC
offset, and when it is not after `replay_start`; `start_replay_clock` refuses a window outside
the case's recording, and neither clamps it. `nict_frames`
(`TEPHRA_NICT_FRAMES`, default false) turns on the NICT true-colour crops (non-commercial
terms; research/05 did not clear them). `model_tts` (`TEPHRA_MODEL_TTS`, default `gemini-3.8-flash-lite-tts`) is the speech model of Ask
TEPHRA's spoken answers; `model_lite` carries every other new model step (section 6).
`cadence_jma_volcano_s` (`TEPHRA_CADENCE_JMA_VOLCANO_S`, 300) is the JMA feed's cadence.
`crew_fix_history_min` (`TEPHRA_CREW_FIX_HISTORY_MIN`, 30, 1 to 360) is how long airline ADS-B
positions are kept in memory to place a crew report at its flight's fix (section 5.19).
`recovery_auto` (`TEPHRA_RECOVERY_AUTO`, default true) lets the pipeline start one recovery
agent session when the set of closed RFA airports changes; the Desk's run button works either
way. `max_upload_bytes` (`TEPHRA_MAX_UPLOAD_BYTES`, default 1,310,720, at least `MAX_BODY_BYTES`)
is the body cap of `POST /api/desk/ask/voice` alone (a recording up to 1 MiB plus multipart
overhead); a pasted notice has `MAX_NOTICE_BODY_BYTES`, every other route `MAX_BODY_BYTES`.
`max_event_streams` (`TEPHRA_MAX_EVENT_STREAMS`,
default 200, at least 1) caps open `GET /api/events` streams; each holds a Cloud Run request
slot, so it must stay below the service's `--concurrency`.
`build_sha` (`TEPHRA_BUILD_SHA`, default unset) is the commit the image was built from: the
Dockerfile sets it from the `BUILD_SHA` build arg (`unknown` when none is given), and
`GET /api/state` shows it (kept answers are not keyed by it, 5.7).
Leave it unset locally.

Model budgets (section 5.5's `agents.quota`). `ModelLimit` (`rpm`, `rpd`, `tpm: int | None`)
and `DEFAULT_MODEL_LIMITS` hold Google's free-tier rows per model id (3.8 Flash 5/20, 3.5 and
3.1 Flash-Lite 15/500, 3.8 Flash-Lite TTS 3/10, Gemma 4 31B and 26B 30/14,400 with 16,000 tpm);
`model_limits` (`TEPHRA_MODEL_LIMITS`, JSON) adds rows or replaces them. `ai_budget_margin`
(`TEPHRA_AI_BUDGET_MARGIN`, 0.1, 0 to <1) is the share of each free limit left unused:
`daily_budget(model_id)` is `floor(rpd x (1 - margin))` (18 and 450 by default), or the
`model_daily_budget` / `model_lite_daily_budget` override (`TEPHRA_MODEL_DAILY_BUDGET`,
`TEPHRA_MODEL_LITE_DAILY_BUDGET`, default unset) for the model TEPHRA_MODEL or TEPHRA_MODEL_LITE
names, or 0 for a model with no row (it is never called; `unlimited_models()` lists them and
`create_runtime` logs them). `paced_rpm(model_id)` is `rpm x (1 - margin)` (at least 1) and
`paced_tpm(model_id)` the same for tpm. Budgets count calls per Google quota day, midnight to
midnight Pacific. `ai_urgent_share` (0.3), `ai_interactive_share` (0.2; their sum below 1),
`ai_routine_burst` (0.05) and `ai_reserve_release` (0.75) split each budget into lanes (5.5).
Model answers (5.7): `ai_answer_keep_h` (`TEPHRA_AI_ANSWER_KEEP_H`, 72) is how long, in wall-clock
hours, a kept answer stays in `ai_answers` at most (a LIVE answer no longer than its skill's own
limit); `ai_answer_plan_min` (60), `ai_answer_duty_min` (30) and `ai_answer_ask_min` (10) are the
limits, on the run's clock, of a plan and its draft, of a Duty Officer run's decisions and of an
Ask TEPHRA answer. `ai_answer_replay_keep_h` (`TEPHRA_AI_ANSWER_REPLAY_KEEP_H`, 2160) is the
wall-clock hours a REPLAY answer is kept: a replay asks the same question every loop, and the
kept answer is what lets a loop run at no call.
The former `TEPHRA_MODEL_RPM` and `TEPHRA_MODEL_LITE_RPM` are gone: pacing follows the table.

Demo, replay minute, visitor and cloud settings (15 Oct 2026; each defaults to today's
behaviour). `features` (`TEPHRA_FEATURES`, default `all`; `Feature`, `ALL_FEATURES`,
`HERO_FEATURES`): the optional features the pages show (`connect`, `crew`, `notices`,
`satellite`, `btd`, `voice`, `example`, `present`), as `all`, `hero` (none of them: the hero path
and its three acts only; `""` means the same) or a comma list; an unknown name fails startup
(`unknown feature(s): nope`). Hidden features keep their routes and tests; their scheduled model
work stops. `replay_quantum_s` (`TEPHRA_REPLAY_QUANTUM_S`, default 0, 0 to 300): in REPLAY the
clock ticks and the AI worker see is floored to this many seconds, anchored to the wall minute
(4.1); 0 keeps the exact clock. `cloud_region` (`TEPHRA_CLOUD_REGION`, unset) is the region
shown under Details > Runs on; `secrets_source` (`TEPHRA_SECRETS_SOURCE`, `environment` |
`secret-manager`, default `environment`) is set by `deploy/cloudrun.sh` beside `--set-secrets`
and never inferred. `visitor_access` (`TEPHRA_VISITOR_ACCESS`, `off` | `replay`, default `off`):
with `replay`, anyone may enter the Desk as a visitor (no PIN) while a replay plays;
`visitor_session_ttl_h` (`TEPHRA_VISITOR_SESSION_TTL_H`, 2), `visitor_decision_cap`
(`TEPHRA_VISITOR_DECISION_CAP`, 40, at least 1) and `visitor_ask_cap`
(`TEPHRA_VISITOR_ASK_CAP`, 3, 0 or more) bound a visitor session. `tick_deadline_s`
(`TEPHRA_TICK_DEADLINE_S`, 100, at least 20) is how long a tick may take before it publishes
what it has, under Cloud Scheduler's 120 s attempt deadline.

### 4.6 `tephra.feeds.base`

`USER_AGENT`, `FetchError(url, feed, reason)`, `FetchResult` (frozen dataclass: `feed, url,
status_code, content, content_type, fetched_at, sha256, from_cache, stale, stale_age_s,
replay, error`; methods `text()`, `json()`, `provenance(source_id, *, issued_at,
valid_from, valid_to)`), `Source` protocol (`async fetch(url, *, feed, params=None) ->
FetchResult`, `async aclose()`), `build_url(url, params)`, `HttpSource(*, cache_dir,
timeout_s=20, retries=2, host_intervals_s=None, transport=None)` and
`HttpSource.from_settings(settings)`, `LastGoodCache`, `RecordingSource(inner, case_dir)`
(`.records`, `.manifest(case_id=, label=, region=, volcano_ids=, notes=) -> ReplayCase`,
`.write_manifest(case) -> Path`).

`HttpSource` is GET-only, serialises and spaces requests per host (adsb.lol >= 1.1 s, others
0.5 s), retries network errors and 408/420/425/429/500/502/503/504, honours `Retry-After` on
420/429, and on final failure returns the last good copy marked `stale=True`, with its age in
`stale_age_s` and the live failure in `error` (or raises `FetchError`). It words a transport
failure as `"<httpx exception name>: <detail>"` and an HTTP failure as `"HTTP <status>"`. The
last-good cache keeps copies for 48 hours; HSD segments and satellite frames
(`UNCACHED_FEEDS`) are never cached, because their per-scan URLs are never read twice.
`fetched_at` is always wall-clock time, even under a replay clock. Build `params` in a fixed
key order.

### 4.7 `tephra.store.base`

`Collection` (names and document ids in section 7), `Where(field, op, value)`, `WhereOp`,
`BLOB_KEY_PATTERN`, `escape_doc_id`/`unescape_doc_id`, and the `Store` protocol:
`put`, `get`, `delete`, `list_docs`, `query`, `update`, `compare_and_set_advisory`, `append_audit`,
`get_feed_state`, `put_feed_state`, `list_feed_states`, `put_blob`, `get_blob`, `aclose`.
`update(collection, doc_id, change)` atomically replaces a document with `change(stored)` (None
when missing) and returns what it wrote: a SQLite `BEGIN IMMEDIATE` transaction, a Firestore
transaction (which may call `change` again on contention, so it has no side effects). An
exception from `change` writes nothing and propagates. The AI budget counts with it.
(The method is `list_docs`, not `list`, so implementations can still annotate with `list[...]`.)
`Collection` has no `adsb`, `wall` or `exposures` member: nothing read them back, so aircraft,
exposures and the Wall are no longer stored and rebuild on the first tick after a restart.

### 4.8 `tephra.policy` and `data/policy/policy_a.json`

```python
POLICY_FILE: Final = Path("policy") / "policy_a.json"       # relative to Settings.data_dir
def load_policy(data_dir: Path) -> OperatorPolicy
```
The operator policy holds every margin, buffer, minimum and threshold the code applies on
the operator's behalf, each with its unit, a `source` saying why it has that value, and
optional `citation_ids`. Header: `policy_id` (`RFA-POLICY-A`), `version` (`2026.10.9`),
`preset` (`A`), `title`, `label` (`ILLUSTRATIVE, not an airline SRA`), `sra_ref` (null for A),
`risk_owner` (`Flight Operations`), `summary_text` (the Policy A text) and
`summary_citation_ids`. The Policy A text follows the Doc 9974 App 5 5.4(d)(2) default for
ungraded areas, adds that where a State grades contamination (App 5 5.4(d)(1)) Policy A still
treats every graded area as high contamination, and says that an airborne level change above
or below the area carries an OVER ASH or UNDER ASH line. Blocks: `exposure`
(`vertical_margin_ft`), `alternates` (`search_radius_nm`, `min_runway_m`, `min_visibility_m`, `min_ceiling_ft`,
`taf_eta_window_min`, `terminal_radius_nm`), `planner` (`level_search_ft`, `level_band_fl`,
`max_change_level_fl`, `divert_within_min`, `hold_within_min`; one hold time in every plume
mode), `reroute` (`buffer_nm`, `simplify_nm`, `max_waypoints_count`,
`max_turn_deg`, `rejoin_step_nm`, `max_extra_min`, `min_extra_min`, `route_max_cross_track_nm`,
`cruise_tas_kt`), `recovery` (`min_turn_min`, `max_delay_min`, `freeze_window_min`,
`horizon_after_closure_min`, `scenario_extend_1_min`, `scenario_extend_2_min`,
`solve_work_s`, `solve_time_limit_s`, the delay, cancel, swap and ferry costs in USD, `max_fdp_min`,
`airport_closure_radius_nm`, `pax_notice_min_delay_min`), `fuel` (`hold_min`, `divert_extra_min`),
`drafts` (`unexposed_retire_min`, `position_lost_retire_min`: how long an open draft waits
after its flight leaves the cone, section 5.7), `duty` (`rerun_min`: when deferred Duty
Officer work is offered again, section 5.18), `crew_reports` (`radius_nm` 60, `downwind_stretch_min`
30, `stretch_wind_kt` 30, `level_margin_ft` 2000, `valid_min` 360: the crew report caution
area, section 5.19).
Then `source_order`
(the source-trust order, most trusted first) and `citations` (quoted word for word). Each
`SourceRule` has `rule_id`, `text`, `enforced_by` (required: the code that applies the rule
today, named by file and function) and `citation_ids`. The order is the operator's own
illustrative choice: Doc 9974 2.4(d) asks the operator to resolve conflicts among its sources,
so each rule cites that paragraph. No code acts on the list (the Wall policy dialog and the
SRA draft only show it); `enforced_by` names where each rule is coded. Citations: `9974-app5-5.4d2`, `9974-app5-5.4d1`, `9974-2.10`,
`9974-2.4d`, the UK comparison rows `cap1236-2.24`, `cap1236-2.28` and `cap1236-2.29`
cited by `vertical_margin_ft` (2.24 and 2.29 also by `crew_reports.level_margin_ft`),
`eurnat-vacp-3.1.8bi` (EUR Doc 019 / NAT Doc 006 Part II Ed. 2.0.0 3.1.8 b) i), cited by the
crew radius and stretch), `faa-jo-7110.65-2-6-2` (a sulphur smell alone is a routine report)
and `nwsi-10-811-6.3.1.1` (VA SIGMET validity, cited by `crew_reports.valid_min`). Every value's `source` either says it is a TEPHRA illustrative
choice or placeholder, or names its outside basis.

Rules: only the composition root (`create_runtime`) loads the file; library code takes the
values as arguments. Pure functions (geo, feeds) take plain numbers; the planner takes the
`OperatorPolicy`. A value enters the file only with the code that reads it
(`tests/test_policy.py` checks each is dereferenced as `.<name>.value` somewhere in
`tephra/`). Any change to the content needs a new `version`, and the test pins each version's
`content_hash()`. Policy B is not here yet. The planner already proposes level bands above
or below an affected area (the Policy A text says so), but no code reads a preset, so a B
file would change labels, not behaviour.

## 5. Module APIs

Signatures are exact. "Rules" are behaviour other modules and tests rely on.

### 5.1 feeds-text

`tephra/feeds/sigmet.py`
```python
SIGMET_URL: Final = "https://aviationweather.gov/api/data/isigmet"
SIGMET_PARAMS: Final = {"format": "json", "hazard": "va"}
def parse_sigmets(result: FetchResult) -> list[Sigmet]
async def fetch_sigmets(source: Source) -> list[Sigmet]   # one GET with SIGMET_PARAMS
# Text helpers shared with tephra.feeds.vaac (SIGMETs and VAAs write these groups alike):
class LevelBand(NamedTuple):   # base_ft: int, top_ft: int
class Movement(NamedTuple):    # toward_deg: float | None, speed_kt: float | None, stationary: bool = False
def parse_dm_point(lat_token: str, lon_token: str) -> tuple[float, float] | None
def find_dm_points(text: str) -> list[tuple[float, float]]
def parse_level_band(text: str) -> LevelBand | None
def parse_movement(text: str) -> Movement | None
def polygon_or_none(points: Iterable[tuple[float, float]]) -> GeoPolygon | None
```
Rules: keep hazard VA only, all FIRs (no region filter here). De-duplicate records with the
same `(rawSigmet, seriesId)`. A series id ending in `F` is the forecast polygon of the same
SIGMET: keep it as its own record with `observed=False`. Polygon from JSON `coords`
(decimal); if absent, from the raw text, where coordinates are **degrees and minutes**
(`S0806 E11255` = -(8 + 6/60), 112 + 55/60), never decimals; only the `PSN` group is left
out, so a vertex on the vent is kept. `base_ft` 0 for SFC. Levels: JSON `base` and `top` win;
else the raw band (`SFC/FL150`) or `TOP FLnnn` (a top). `ABV FLnnn` gives `base_ft` = nnn x 100
with `top_ft` None (top not stated), and `TOP ABV FLnnn` gives `top_ft` None. Movement
`MOV NE 05KT` -> `movement_toward_deg=45`, `movement_speed_kt=5` (KMH converted to kt);
`STNR` -> `stationary=True`. `CNL SIGMET` -> `cancelled=True`. `observed`: True for `VA CLD
OBS`, False for forecast-only, None for `VA NOT IDENTIFIABLE` or unknown. `observed_at` from
`OBS AT 1010Z` via `parse_hhmmz(..., ref=valid_from)`. Volcano name and `PSN` from the raw
text: the name runs from the last `FIR`/`VA`/`CLD`/`ERUPTION`/`MT` word to `PSN`; the JSON
`qualifier` is the fallback. A SIGMET describing several clouds joined by `AND` yields one
extra record per later cloud: `series_id` `"<series> AREA <n>"`, source id
`SIGMET:{fir_id}:{series}_AREA_{n}:{compact(valid_from)}`, with its own polygon, band,
movement and intensity read from its text (AWC's `coords` describe the first cloud only).
`provenance.issued_at` is the DTG in the raw header if parseable, else `receiptTime`;
`valid_from`/`valid_to` are also set on it. Drop records whose `validTimeTo` is already past
at parse time only in `fetch_sigmets`, never in `parse_sigmets` (replay tests need them).

`tephra/feeds/vona.py`
```python
VONA_LIST_URL: Final = "https://magma.esdm.go.id/v1/vona"
MAX_LIST_PAGES: Final = 40        # hard stop for paging
class VonaListItem(TephraModel):   # url, magma_id: int, volcano_name, issued_at, color_code, summary
def parse_vona_list(result: FetchResult) -> list[VonaListItem]
def parse_vona_page(result: FetchResult, item: VonaListItem | None = None) -> Vona
def parse_vona_card(listing: FetchResult, item: VonaListItem) -> Vona   # from the list card alone
async def fetch_vonas(source: Source, *, since: datetime,
                      known_urls: frozenset[str] = frozenset(),
                      known_ids: frozenset[int] = frozenset(), max_pages: int = 1) -> list[Vona]
```
Rules: page 1 is fetched with no params, page n with `{"page": str(n)}`. Notices issued after
`now()` are skipped (a replay serves list pages saved after its clock), and a page that holds
only such notices does not count towards `max_pages`. Paging stops after `max_pages` pages
with current notices, at a page whose oldest notice is older than `since`, at an empty page,
or after `MAX_LIST_PAGES`. Only detail pages of notices issued at or after `since`, not in
`known_urls` and whose MAGMA id is not in `known_ids`, are fetched (MAGMA's robots.txt
disallows crawling, research/05; live polling is opt-in, section 5.7). The detail page is
fetched with the signed link exactly as listed. When it cannot be fetched or read and the list
card carries the notice text, `parse_vona_card` builds the VONA from the card (provenance of
the list page); otherwise the notice is skipped with a warning. `ash_observed=False` when the
notice says ash is not observed. Cloud top: parse the **metre** value and set
`cloud_top_ft = round(m * 3.28084)` (MAGMA's printed feet use a factor of 3.2; research/13).
Direction words ("north east", "northeast", "NE", "to the east") -> `movement_toward_deg`
via `tephra.geo.units.compass_to_deg`; keep the original in `movement_text`. Cloud top and
direction are set only when ash is observed.

`tephra/feeds/vaac.py`
```python
TOKYO_LIST_URL: Final = "https://ds.data.jma.go.jp/svd/vaac/data/vaac_list.html"
DARWIN_BACKUP_LIST_URL: Final = "https://ds.data.jma.go.jp/svd/vaac/data/vaac_darwin_list.html"
DARWIN_BULLETIN_URLS: Final = tuple(
    f"https://tgftp.nws.noaa.gov/data/raw/fv/fvau{n:02d}.adrm..txt" for n in range(1, 11))
class VaacListItem(TephraModel):   # vaac, url, volcano_name, area, issued_at, advisory_nr | None
def parse_vaac_list(result: FetchResult, vaac: VaacCentre) -> list[VaacListItem]
def parse_vaa_text(text: str, result: FetchResult) -> VaacAdvisory | None
def parse_vaa(result: FetchResult) -> VaacAdvisory | None     # extracts the text from HTML/plain
async def fetch_vaas(source: Source, feed: FeedId, *, since: datetime,
                     known_urls: frozenset[str] = frozenset()) -> list[VaacAdvisory]
```
Rules: `feed` is `FeedId.VAAC_TOKYO` (Tokyo list -> `TextData/...` pages, relative links
resolved against the list URL) or `FeedId.VAAC_DARWIN`. **Darwin advisories come from the
NOAA tgftp bulletins** `DARWIN_BULLETIN_URLS`: Darwin rotates over ten WMO headers, FVAU01 to
FVAU10, and each slot's file holds its latest bulletin (GET, all ten every poll; advisories
issued before `since` are dropped). BoM's page loads its list by POST and TEPHRA is GET-only;
the JMA "Darwin backup" list holds only advisories Tokyo issued while backing Darwin up
(research/13) and is also polled under `VAAC_DARWIN`. `fetch_vaas(VAAC_DARWIN)` raises
`FetchError` when every tgftp slot fails, even if the backup list answers; a backup-list
failure is only logged. `VaacAdvisory.vaac` is taken from the text's `VAAC:` line. Return
`None` for `VOLCANO: NOTICE` pseudo-advisories (number 999999) and for `STATUS: TEST` or
`STATUS: EXER` bulletins, which may name real volcanoes. Accept `+6 HR` and `+6HR`;
`NXT ADVISORY` styles `WILL BE ISSUED BY 20260925/1500Z`, `NO LATER THAN 20261009/2020Z`,
`NO FURTHER ADVISORIES` (-> `final=True`, never an all-clear); optional `AVIATION COLOUR
CODE`. `EST VA CLD` -> `estimated=True`; `VA NOT IDENTIFIABLE FM SATELLITE DATA` ->
`not_identifiable=True`; `NO VA EXP` -> `no_ash_expected=True`; `NOT AVBL`/`NOT PROVIDED`
-> `not_available=True`. Layers `SFC/FL150 S0803 E11253 - ... MOV E 10KT`, several per
step allowed; coordinates are degrees and minutes. Step times via `parse_day_time(..., ref=issued_at)`.

`tephra/feeds/taf.py`
```python
TAF_URL: Final = "https://aviationweather.gov/api/data/taf"
METAR_URL: Final = "https://aviationweather.gov/api/data/metar"
def station_params(icaos: Sequence[str]) -> dict[str, str]   # {"ids": ",".join(sorted(set(icaos))), "format": "json"}
def parse_tafs(result: FetchResult) -> list[Taf]
def parse_metars(result: FetchResult) -> list[Metar]
async def fetch_tafs(source: Source, icaos: Sequence[str]) -> list[Taf]      # chunks of 20 sorted ids
async def fetch_metars(source: Source, icaos: Sequence[str]) -> list[Metar]
def assess_alternate(taf: Taf | None, eta: datetime, *, min_visibility_m: int, min_ceiling_ft: int,
                     window_min: int, icao: str | None = None) -> AlternateCheck
    # minima and window from the policy's alternates block; icao names the aerodrome when there is no TAF
```
`assess_alternate` rules (simplified planning minima, labelled as such in the UI): no TAF ->
not ok (`NO TAF`); TAF not valid at `eta` -> not ok (`TAF NOT VALID AT ETA`); every period
(base, FM, BECMG, TEMPO, PROBxx) overlapping `eta +/- window_min` is screened:
`VA` in weather -> not ok; visibility below `min_visibility_m` -> not ok; ceiling
below `min_ceiling_ft` -> not ok; `TS` -> reason recorded, still ok. Reasons are
short upper-case code-written strings naming the group (`"VIS 1500 M BELOW 3000 M IN BASE
FORECAST"`, `"TS IN TEMPO GROUP"`). The prevailing group (base, FM or BECMG) before a BECMG
is screened until that BECMG's `timeBec`: the parser extends that `TafPeriod.valid_to`,
because an improving BECMG applies only once the change completes. aviationweather.gov
allows 100 requests/minute and needs a custom User-Agent (HttpSource sets it).

### 5.2 feeds-geo

`tephra/feeds/volcanoes.py`
```python
class VolcanoCatalogue:
    def __init__(self, volcanoes: Sequence[Volcano]) -> None
    def all(self) -> list[Volcano]
    def get(self, volcano_id: str) -> Volcano | None
    def resolve(self, name: str) -> Volcano | None            # case-insensitive name/alias/GVP number
    def find_in_text(self, text: str) -> Volcano | None       # alias as a whole word in raw SIGMET/VAA text
    def by_magma_code(self, code: str) -> Volcano | None
    def nearest(self, lat: float, lon: float, max_km: float) -> Volcano | None
    def in_bbox(self, bbox: BBox) -> list[Volcano]
def load_volcanoes(data_dir: Path) -> VolcanoCatalogue        # reads data/volcanoes.json (VolcanoFile)
```
`data/volcanoes.json` is a `VolcanoFile`: JAPAC volcanoes with Smithsonian GVP numbers as
`id`, MAGMA codes for Indonesian ones (`SMR` Semeru, `KRA` Anak Krakatau, `LWK` Lewotobi
Laki-laki, `IBU`, `DUK`, ...), aliases as feeds print them (`SEMERU`, `AIRA`, `SAKURAJIMA
(AIRA CALDERA)`), summit elevation in metres, observatory, and VAAC area. At minimum every
volcano in the three regions plus Ibu, Dukono, Ruang, Taal, Mayon, Kanlaon, Bagana, Manam.
`source_note` cites GVP and MAGMA.

`tephra/feeds/airports.py`
```python
class AirportCatalogue:
    def __init__(self, airports: Sequence[Airport], *, min_runway_m: int) -> None
    def all(self) -> list[Airport]
    def get(self, icao: str) -> Airport | None
    def icaos(self) -> set[str]
    def in_bbox(self, bbox: BBox) -> list[Airport]
    def nearest(self, lat: float, lon: float, *, limit: int = 5, max_nm: float,
                alternates_only: bool = True) -> list[tuple[Airport, float]]   # (airport, distance_nm), nearest first
    def alternate_ok(self, airport: Airport) -> bool               # longest_runway_m >= min_runway_m
def load_airports(data_dir: Path, *, min_runway_m: int) -> AirportCatalogue   # reads data/airports.json (AirportFile)
```
`data/airports.json` is an `AirportFile` of public aerodromes across the three regions and
their usual alternates (for example WIII, WIHH, WICA, WARR, WAHI, WADD for Java/Bali; WAMT,
WAMM for Halmahera; RJFK, RJFT, RJFM, RJFO, RJFU, RJFF for Kyushu). Verify every code
against a current source: Indonesia re-coded several Central Java aerodromes (WARx ->
WAHx). Real ICAO codes only; runway length in metres where known; `source_note` cites the
source. Whether an airport is a jet alternate is not stored: the catalogue compares its
`longest_runway_m` with the policy's `alternates.min_runway_m`.

`tephra/feeds/adsb.py`
```python
ADSB_POINT_URL: Final = "https://api.adsb.lol/v2/point/{lat}/{lon}/{radius_nm}"
MAX_CACHED_COPY_AGE_S: Final = 120
class AdsbPointsFailed(FetchError):   # .failed_points: list[AdsbQueryPoint], .snapshots: list[AdsbSnapshot]
    def __init__(self, failed: Sequence[tuple[AdsbQueryPoint, str]],
                 snapshots: Sequence[AdsbSnapshot], *, tried: int) -> None
def point_url(point: AdsbQueryPoint) -> str                   # lat/lon with 3 decimals
def query_points(region: Region, volcanoes: Sequence[Volcano], radius_nm: int) -> list[AdsbQueryPoint]
def parse_adsb(result: FetchResult, query: AdsbQueryPoint) -> AdsbSnapshot
async def fetch_aircraft(source: Source, points: Sequence[AdsbQueryPoint]) -> list[AdsbSnapshot]
def merge_aircraft(snapshots: Sequence[AdsbSnapshot]) -> list[Aircraft]
```
Rules: `query_points` = the region's points plus one per given (active) volcano at
`radius_nm` (clamped to 1..250), dropping a volcano point within 50 nm of one already chosen.
Calls are sequential (HttpSource spaces them >= 1.1 s and backs off on 420/429). Every point
is tried in order; if any point fails, is unreadable, or answers only with a cached copy older
than `MAX_CACHED_COPY_AGE_S` (or of unknown age), `fetch_aircraft` then raises
`AdsbPointsFailed`, whose reason reads `"<n> of <m> adsb.lol points failed (<lat>,<lon>/<r>nm:
<reason>; ...)"` and which carries the snapshots that did answer, so a lost point never reads
as an empty sky. A recent cached copy is returned marked stale. Parse fields `hex, flight,
lat, lon, alt_baro, alt_geom, gs, track, nav_altitude_mcp, t, baro_rate, seen_pos`; drop
`alt_baro == "ground"` and targets whose `lat` or `lon` is missing; never keep `r`
(registration), and drop a callsign that is just the registration. Any non-finite or
out-of-range number (NaN, Infinity, `"nan"`, `"inf"`, `1e999`) reads as missing; a target
whose numbers overflow (an impossible `seen_pos`) is skipped with a warning. `parse_adsb`
raises only `ValueError` for a bad response, an unreadable `now` included, so one bad point
never ends the pass. `observed_at` = response `now` (ms) minus `seen_pos` (or `seen`).
`nav_altitude_mcp` is rounded to 100 ft. `merge_aircraft` de-duplicates by `hex`, keeping the
newest, sorted by `hex`. UI attribution: "Aircraft: adsb.lol (ODbL 1.0)".

`tephra/feeds/winds.py`
```python
OPEN_METEO_URL: Final = "https://api.open-meteo.com/v1/forecast"
def wind_params(lat: float, lon: float) -> dict[str, str]
def parse_winds(result: FetchResult, *, lat: float, lon: float) -> list[WindProfile]
async def fetch_winds(source: Source, lat: float, lon: float) -> list[WindProfile]
def profile_at(profiles: Sequence[WindProfile], at: datetime) -> WindProfile | None   # nearest valid_at
def wind_at_fl(profile: WindProfile, flight_level: int) -> WindLevel                 # nearest level
```
`wind_params` key order: `latitude`, `longitude` (2 decimals), `hourly` (for each hPa in
`PRESSURE_LEVEL_FL` ascending: `wind_speed_{p}hPa,wind_direction_{p}hPa`), `wind_speed_unit=kn`,
`timezone=GMT`, `past_hours=1`, `forecast_hours=24`. One `WindProfile` per hour.

`tephra/feeds/satellite.py`
```python
JMA_IMAGE_URL: Final = "https://www.data.jma.go.jp/mscweb/data/himawari/img/{area}/{area}_{band}_{hhmm}.jpg"
JMA_SLOTS_URL: Final = "https://www.data.jma.go.jp/mscweb/data/himawari/sat_img.php"
NICT_LATEST_URL: Final = "https://himawari8.nict.go.jp/img/D531106/latest.json"
NICT_TILE_URL: Final = "https://himawari8.nict.go.jp/img/D531106/{level}d/550/{year}/{month}/{day}/{hhmmss}_{x}_{y}.png"
REUSE_S: Final = 60.0
JMA_AREAS: Final[tuple[JmaArea, ...]]    # se3 (Southeast Asia 3) and jpn (Japan)
def frame_key(volcano_id: str, product: FrameProduct, observed_at: datetime) -> str
    # "frames/{volcano_id}_{product}_{compact(observed_at)}.png"
async def fetch_frames(source: Source, volcano: Volcano, *, half_width_km: float = 300.0,
                       areas: Sequence[JmaArea] = JMA_AREAS, nict_level: int = NICT_DEFAULT_LEVEL,
                       nict: bool = True
                       ) -> list[tuple[SatelliteFrame, bytes]]   # PNG bytes to store at frame.image_key
```
Rules: JMA MSC realtime images (`b13` Band-13 IR and `dst` Dust RGB) for the first JMA area
that covers the volcano (`se3` for Indonesia, `jpn` for Japan). The files are named by HHMM
only, so the slot's date comes from the `sat_img.php` slot list, and only a slot at least
35 minutes old is used; a slot list or image served from cache is refused, because a
date-less name may hold another day's image. NICT true colour only in local daylight (solar
hours 7 to 17), from at most four tiles; `nict=False` skips it entirely (the registry passes
`settings.nict_frames`, off by default). Crop around the volcano with Pillow, re-encode PNG.
Set `bbox` only if the image is a plain lat/lon grid: JMA `se3` crops (equirectangular, 0.05 deg/px,
origin checked against `web/data/land_apac.geojson` to about one pixel) carry the crop's exact
rectangle; the Mercator `jpn` crops and NICT's geostationary tiles keep `bbox=None` and the Wall shows
them in a side strip, never on the map. The caption names the product and scan time, cites the source
("Source: JMA Meteorological Satellite Center (<area> image)" or "Source: NICT Himawari
real-time web (non-commercial use only)"), says "cropped by TEPHRA" (JMA's Public Data
License 1.0 asks for the source and an edit notice) and ends "context only; not used to
draw the cone". A product that fails is skipped, not fatal; when products were tried and
none came back, `fetch_frames` raises `FetchError` listing each failure. A product that does
not apply (NICT at night, no JMA area) is not a failure. One source's answers, failures
included, are reused for `REUSE_S` (60 s on the active clock), so a poll that asks volcano by
volcano downloads each slot list, image and tile once.

### 5.3 science

`tephra/science/hsd_segments.py`
```python
HSD_BUCKET_URL: Final = "https://storage.googleapis.com/noaa-himawari9/"   # NOAA NODD on GCS; same keys as https://noaa-himawari9.s3.amazonaws.com/
class HsdObject(TephraModel):   # key, url, band: int, segment: int, size_bytes: int, scan_start: UtcDatetime
def listing_params(scan_start: datetime) -> dict[str, str]   # {"list-type": "2", "prefix": "AHI-L1b-FLDK/YYYY/MM/DD/HHMM/"}
def parse_listing(result: FetchResult) -> list[HsdObject]   # ListBucketResult XML, namespace ignored (S3 or GCS)
def segments_for_bbox(bbox: BBox, projection: GeosProjection = HIMAWARI_AHI_2KM) -> list[int]
    # 1..10 full-disk segments covering it
async def find_latest_scan(source: Source, at: datetime, bands: Sequence[int],
                           segments: Sequence[int], *, lookback_slots: int = 6
                           ) -> tuple[datetime, list[HsdObject]] | None
async def download(source: Source, objects: Sequence[HsdObject]) -> list[tuple[HsdObject, bytes]]   # bz2 bytes
```
`tephra/science/btd.py`
```python
class ScienceUnavailable(RuntimeError): ...
STANDARD_CAVEATS: Final[tuple[str, ...]]     # water vapour masking, ice-coated/thin ash missed, cold tops, resolution
def btd_key(volcano_id: str, scan_start: datetime) -> str    # "btd/{volcano_id}_{compact(scan_start)}.png"
def compute_btd(segments: Sequence[tuple[HsdObject, bytes]], volcano: Volcano, *,
                band_pair: Literal["B13-B15", "B14-B15"], half_width_km: float,
                threshold_k: float, listing_url: str, fetched_at: datetime
                ) -> tuple[BtdResult, bytes]    # sync and CPU-bound
async def run_btd(source: Source, volcano: Volcano, at: datetime, settings: Settings
                  ) -> tuple[BtdResult, bytes] | None
    # finds the scan, downloads, runs compute_btd via asyncio.to_thread; None if no complete scan
```
Rules: HSD decoding may be numpy-only (research/12 measured it at 0.12 s per segment) and
use satpy/pyresample only if installed; raise `ScienceUnavailable` if neither path works.
Resample the crop onto a regular lat/lon grid so `BtdResult.bbox` corners georeference the
PNG exactly. `provenance.feed = FeedId.HSD`, `url = listing_url`, `sha256 =
combine_hashes(segment_sha256)`. `indicator` is `NEGATIVE_BTD_PRESENT`, `SILENT` or
`INCONCLUSIVE` (e.g. most pixels colder than 233 K). **SILENT and INCONCLUSIVE never mean
"no ash"**; the caption says so of both. Credit: "Himawari-9 data: JMA, distributed by NOAA
(NODD / AWS Open Data); processed by TEPHRA, not original JMA data". Never re-serve raw HSD
files.

### 5.4 geo

`tephra/geo/units.py`
```python
FT_PER_M: Final = 3.28084; KM_PER_NM: Final = 1.852; EARTH_RADIUS_KM: Final = 6371.0088
def ft_to_fl(ft: float) -> int                 # nearest FL, halves rounded up
def fl_to_ft(fl: float) -> int
def m_to_ft(m: float) -> float
def ft_to_m(ft: float) -> float
def km_to_nm(km: float) -> float
def nm_to_km(nm: float) -> float
def kt_to_km_per_min(kt: float) -> float
def normalize_lon(lon: float) -> float                      # [-180, 180)
def unwrap_lon(lon: float, ref_lon: float) -> float         # shifted by 360 to within 180 of ref_lon
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float
def distance_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float
def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float
def destination_point(lat: float, lon: float, bearing_deg: float, distance_km: float) -> tuple[float, float]  # (lat, lon)
def bearing_diff_deg(a: float, b: float) -> float           # 0..180
def compass_to_deg(text: str) -> float | None               # 16-point names and words; None if unknown
def deg_to_compass(deg: float) -> str                       # 16-point
def sector_width_deg(bearing_from_deg: float, bearing_to_deg: float) -> float
    # clockwise; equal bearings give 0, 0 -> 360 gives 360 (a full circle)
def solar_hour(lon: float, at: datetime) -> float           # local mean solar time, 0..24 (night flag)
```

`tephra/geo/cone.py`
```python
FORECAST_WINDOW_H: Final = 3.0                # a VAA forecast polygon stands for +/- 3 h
UNKNOWN_TOP_FT: Final = 60_000                # a SIGMET with no stated top is binding to FL600
VAA_CLOCK_SLACK: Final = FEED_CLOCK_SLACK
def official_layers(volcano: Volcano, sigmets: Sequence[Sigmet], vaas: Sequence[VaacAdvisory],
                    at: datetime) -> list[OfficialLayer]
def sector_polygon(lat: float, lon: float, bearing_from_deg: float, bearing_to_deg: float,
                   extent_km: float, *, steps: int = 32) -> GeoPolygon | None
    # None if extent 0, zero width or no area; a 360 degree sweep is a disc
def build_cone(situation: Situation, assessment: PlumeAssessment) -> HazardCone
def covers_official(cone: HazardCone, layers: Sequence[OfficialLayer]) -> bool
def polygon_iou(a: GeoPolygon | GeoMultiPolygon, b: GeoPolygon | GeoMultiPolygon) -> float
def contains_point(cone: HazardCone, lat: float, lon: float) -> bool
def points_in_cone(cone: HazardCone, points: Sequence[tuple[float, float]]) -> list[bool]
def geometry_entries(geometry: GeoPolygon | GeoMultiPolygon, tracks: Sequence[Sequence[tuple[float, float]]]
                     ) -> list[tuple[int, tuple[float, float]] | None]   # (step, (lat, lon)) per track
def geometry_to_shape(geometry: GeoPolygon | GeoMultiPolygon, *, ref_lon: float) -> BaseGeometry
def shape_to_geometry(shape: BaseGeometry) -> GeoPolygon | GeoMultiPolygon | None
```
`official_layers` rules (the "official floor", research/07 rule 13): every SIGMET with a
polygon that is not cancelled (window = its validity; with no stated top it is binding up to
`UNKNOWN_TOP_FT` and its label ends `TOP NOT STATED`); for each VAAC, the newest VAA issued by
`at + VAA_CLOCK_SLACK` (by `vaa_order`), if it replaces the floor (`replaces_vaa_floor`: it
draws an OBS/EST or forecast polygon, is final, or is an explicit negative, `is_negative_vaa`)
and is still current (`at <= valid_until()`; a newer advisory replaces an older one even after
it lapses). A newest VAA that does not replace the floor (VA NOT IDENTIFIABLE, forecasts NOT
AVBL/NOT PROVIDED, a blank cloud field) is a non-observation and never shrinks the hazard
(policy S3): `kept_vaa` walks back to the first older VAA of that VAAC that replaces the
floor and, when it draws an area, its layers stay on the floor under their own windows, each
label ending ` (kept: VAA <newer nr> gives no area)`. A final or negative VAA in between ends
the walk, so a superseded area never comes back; the kept layers end when their windows end
or a VAA with an area, a final or a negative VAA arrives. Layers drawn: OBS/EST layers with
polygons (window `[observation.valid_at, max(observation.valid_at, vaa.valid_until())]`) and
each forecast layer (window `[valid_at - 3 h, valid_at + 3 h]`). Keep a layer when its window
ends at or after `at` and starts no later than `at + MAX_HORIZON_H`. SIGMET layers come
first, then by start time. `label` and `layer` as in the model docstring; a VAA step with
several layers adds each layer's band to its label. `cone` also exports the VAA helpers the
reconcile layer uses (geo may not import reconcile): `vaa_order(vaa) -> (issued_at, year,
number)`, `draws_vaa_area`, `is_negative_vaa`, `replaces_vaa_floor` and
`kept_vaa(newest, older) -> VaacAdvisory | None` (`older` newest first).

`build_cone` rules: geometry = union of **all** `situation.official_layers` polygons, plus
the sector from the estimate when mode is WIDENED or HYPOTHESIS (OFFICIAL ignores the
sector). The union is made with shapely in lon/lat degrees (regional scale; longitudes are
unwrapped around the vent, so a shape crossing the antimeridian stays continuous) and is
**never simplified, buffered inward or clipped**, so the cone always covers every official
polygon (`covers_official` is the property the tests check with hypothesis). An invalid
official ring (one that crosses, folds back over or touches itself) counts as everything its
rings enclose: `geometry_to_shape` nodes the rings and unions every face, and
`covers_official` repairs it the same way. `covers_official` also checks the vertical band,
and treats a layer whose ring encloses no area as laterally covered, even by a cone with no
geometry. Vertical band: `base_ft = min(estimate.base_fl*100, official bases)`, `top_ft =
max(estimate.top_fl*100, official tops)`. `created_at = situation.as_of`, `horizon_h =
estimate.horizon_h`, `valid_to = assessment.created_at + horizon`, `llm_backend =
assessment.llm_backend`, `id = stable_id("CONE", volcano_id, assessment.id)`.
`geometry=None` only when there is no official layer and no sector, or none of them encloses
any area.

`tephra/geo/exposure.py`
```python
MIN_MOVING_GS_KT: Final = 50.0
def extrapolate(aircraft: Aircraft, minutes: int, *, step_min: int = 1) -> list[tuple[float, float]]  # (lat, lon), t=0 first
def find_exposed(cone: HazardCone, aircraft: Sequence[Aircraft], at: datetime, *,
                 lookahead_min: int, vertical_margin_ft: int, hold_minutes: int) -> list[ExposedFlight]
    # vertical_margin_ft and hold_minutes from the policy (exposure, fuel.hold_min)
class Crossing(NamedTuple): target: Aircraft; band: tuple[int, int]; step: int; entry: tuple[float, float]; path: list[Position]
def find_crossings(geometry: GeoPolygon | GeoMultiPolygon, base_ft: int, top_ft: int,
                   aircraft: Sequence[Aircraft], at: datetime, *, lookahead_min: int,
                   vertical_margin_ft: int) -> list[Crossing]
    # the test find_exposed runs on a cone, for any area and band (a crew report area too)
```
Rules: only `aircraft.airline` targets with `alt_baro_ft` are considered; never use
`alt_geom_ft`. The lookahead is `min(cone.horizon_h * 60, lookahead_min)`. A target whose
position is older than the lookahead is skipped; a younger position is projected from its
age, so `minutes_to_entry` counts from `at`. Positions step along `track_deg` at `gs_kt` with
`destination_point` (the great circle) each minute ("if current track and level are held");
targets whose `gs_kt` or `track_deg` is missing or not finite, or below 50 kt, are checked
at their reported position only. Vertical: the aircraft band is `[min, max]` of `alt_baro_ft`
and `nav_altitude_mcp_ft` (if present); exposed only if it overlaps `[cone.base_ft -
vertical_margin_ft, cone.top_ft + vertical_margin_ft]`. Horizontal (`cone.geometry_entries`):
each one-minute step is tested on the segment from the previous point, so a track that
crosses a corner or a narrow part of the cone between two points is still caught.
`minutes_to_entry` is the minute at the end of the first segment that meets the cone (0 only
when inside now, which sets `inside_now`); the entry point is that minute's point if it is
inside, else where the segment comes in. `path` runs from the reported position to the entry
point (GeoJSON order); `hold = fuel.hold_line(category, minutes=hold_minutes)`; `id = f"{hex}:{cone.volcano_id}"`;
a non-finite `gs_kt` or `track_deg` is stored as None. Sorted by `minutes_to_entry`, then
`hex`.

`tephra/geo/fuel.py`
```python
BURN_KG_PER_MIN: Final[dict[AircraftCategory, float]] = {LIGHT: 5, TURBOPROP: 12, REGIONAL_JET: 25,
                                                         NARROWBODY: 42, WIDEBODY: 110, UNKNOWN: 42}
def category_for_type(type_icao: str | None) -> AircraftCategory
def hold_line(category: AircraftCategory, *, minutes: int) -> FuelLine     # policy fuel.hold_min
def divert_line(category: AircraftCategory, *, alternate_icao: str, distance_nm: float,
                gs_kt: float | None, extra_minutes: int) -> FuelLine
    # distance/gs*60 + extra_minutes (policy fuel.divert_extra_min); gs None, not finite or < 150 -> 250 kt assumed, said in formula
```
`formula` strings are code-written upper case, e.g. `"HOLD 20 MIN x 42 KG/MIN (NARROWBODY) =
840 KG"`, `"DIVERT WARR 182 NM AT 430 KT = 26 MIN + 15 MIN = 41 MIN x 42 KG/MIN (NARROWBODY)
= 1722 KG"`. Minutes and kg are integers (rounded up). The divert minutes come from the
whole NM and KT the formula prints, so the formula reproduces its own numbers. UNKNOWN types
use the narrowbody rate and the formula says `(TYPE UNKNOWN, NARROWBODY RATE)`.

### 5.5 reconcile-plume

`tephra/reconcile/discrepancies.py` (re-exported from `tephra/reconcile/__init__.py`)
```python
def find_active(catalogue: VolcanoCatalogue, *, sigmets: Sequence[Sigmet], vonas: Sequence[Vona],
                vaas: Sequence[VaacAdvisory], at: datetime, settings: Settings) -> dict[str, list[str]]
def select_records(catalogue: VolcanoCatalogue, volcano: Volcano, *, sigmets: Sequence[Sigmet],
                   vonas: Sequence[Vona], vaas: Sequence[VaacAdvisory], at: datetime,
                   settings: Settings) -> tuple[list[Sigmet], list[Vona], list[VaacAdvisory]]
def select_floor_vaas(catalogue: VolcanoCatalogue, volcano: Volcano, *,
                      vaas: Sequence[VaacAdvisory], at: datetime) -> list[VaacAdvisory]
def evidence_state(record: Sigmet | Vona | VaacAdvisory, volcano: Volcano, at: datetime) -> EvidenceState
def find_discrepancies(volcano: Volcano, *, sigmets: Sequence[Sigmet], vonas: Sequence[Vona],
                       vaas: Sequence[VaacAdvisory], at: datetime, settings: Settings,
                       feed_health: Mapping[FeedId, FeedHealth] | None = None) -> list[Discrepancy]
def feed_degraded(feed: FeedId, feed_health: Mapping[FeedId, FeedHealth] | None, at: datetime,
                  settings: Settings) -> FeedHealth | None
def build_situation(volcano: Volcano, *, active_reasons: list[str], sigmets: Sequence[Sigmet],
                    vonas: Sequence[Vona], vaas: Sequence[VaacAdvisory], winds: Sequence[WindProfile],
                    frames: Sequence[SatelliteFrame], btd: BtdResult | None, at: datetime,
                    mode: RunMode, settings: Settings,
                    feed_health: Mapping[FeedId, FeedHealth] | None = None,
                    floor_vaas: Sequence[VaacAdvisory] | None = None) -> Situation
```
"Newest" VAA means by DTG, then by advisory number (Darwin can issue two with one DTG).

Activity (`find_active` returns `volcano_id -> human reasons`; the reasons carry no ages, so
a situation changes only when the products do): a VONA for it issued within
`vona_window_h`; or the newest VAA a VAAC issued for it `is_current(at)` (a VAA that a later
one replaced or closed no longer counts); or a valid VA SIGMET that belongs to it. A SIGMET
that names a catalogue volcano (`catalogue.find_in_text` on the raw text, else
`resolve(volcano_name)`) belongs to that volcano only; a SIGMET whose name the catalogue does
not know goes to the nearest vent its polygon lies within `active_radius_km` of. A polygon
with a vertex more than 90 degrees of longitude from a vent is out of its reach.
`select_records`: SIGMETs belonging to the volcano that are not cancelled and are valid at
`at` or start within `MAX_HORIZON_H` (forecast `F` series included), latest start first;
VONAs within the window (newest first); per VAAC the newest VAA issued in the last 24 h, up
to `FEED_CLOCK_SLACK` after `at` (newest first). `select_floor_vaas`: the same newest VAA per
VAAC plus, when it gives no area and is neither final nor negative, the older VAA that
`cone.kept_vaa` keeps from the same 24 h window (newest first); core passes it as
`build_situation(floor_vaas=...)`. `build_situation` sets `official_layers =
tephra.geo.cone.official_layers(volcano, sigmets, floor_vaas, at)` (`vaas` in its place when
`floor_vaas` is None) and `discrepancies = find_discrepancies(...)` (with `feed_health`);
`Situation.vaas`, the discrepancies and the source cards use only `vaas`, so they compare the
newest VAA alone. Its winds are the hourly profiles from the current hour to the horizon, or
the newest older one when the forecast has run out.

Discrepancy rules (deterministic; Gemini never decides what counts):
- **Non-observations are never CONFLICT.** "Ash-cloud is not observed", "VA NOT
  IDENTIFIABLE", NIGHT_BLIND and absence are evidence states, not contradictions
  (research/13: the 7 Oct pair is a non-observation, the 25 Sep pair is ENVELOPE + LAG).
- What is compared: the SIGMETs in force (not cancelled, `observed` not False), each merged
  with any current VAA it echoes; the newest current VAA of each VAAC; and the VONAs.
- One office never disagrees with itself: SIGMETs of one FIR are never compared with each
  other, so the clouds of one SIGMET (`05`, `05 AREA 2`) and series run side by side never
  disagree. A SIGMET leaves the comparisons once a later SIGMET of its FIR replaces it: with
  the same series letters, a later start (or the same start with a higher number) replaces
  it; with different letters, only one issued more than 10 min later (`SERIES_SPLIT_WINDOW`).
- CONFLICT: an explicit negative assertion (VAA `NO VA EXP`, or a final VAA) from a VAA whose
  observation draws no ash and is not `VA NOT IDENTIFIABLE`, `NOT AVBL`/`NOT PROVIDED` or
  blank, in force at `at`, while another product observed ash (SIGMET `observed=True`, VONA
  `ash_observed=True`, VAA OBS layer) after the negative VAA's observation and before its
  validity ends. An older positive observation is a LAG, not a CONFLICT.
- LAG: two products' observation times differ by more than `lag_threshold_min` (a SIGMET's
  `OBS AT`, else its issue time; a VAA's observation step; a VONA's issue time). The newest
  VONA is compared with the SIGMETs in force when it was issued (else those in force now) and
  the VAAs. Magnitude in minutes.
- ENVELOPE: one product's top lies inside the other's band, or outside it by no more than
  `height_tolerance_ft`; magnitude = signed difference in ft. A VONA's top is a point
  checked against an official band.
- HEIGHT_MISMATCH: tops differ beyond `height_tolerance_ft` with neither inside the other.
- DIRECTION_MISMATCH: movement directions differ by more than `direction_tolerance_deg`
  (aspect `direction`; a stationary product is not compared), or a point 15 km down the
  newest directional ash VONA's drift lies outside every probed polygon (aspect `polygon`;
  research/13 finding 4). The probe set is the direction comparators: for a VONA issued in
  the last 6 h, the SIGMETs in force at its issue time (else those in force now) and every
  OBS/EST layer polygon of the current VAAs not echoed by a SIGMET; for an older VONA, only
  the SIGMETs and VAAs in force when it was issued. Every probed source is cited in `values`.
  A VONA older than 6 h is compared on direction only with the products in force when it was
  issued.
- SILENCE: a VONA with ash that no VAA answers (none in force when it was issued, other than
  a closing one, and none issued since) for more than `silence_threshold_min`; a valid
  SIGMET that no VAA has been in force with since its observation time, once it has been
  valid for more than `silence_threshold_min`; or the newest VAA of a VAAC past its next
  advisory time + 10 min ("overdue"). Magnitude in minutes since. None of these fire when
  `feed_health` shows the volcano's VAAC feed not OK, never run, or older than
  `stale_after_s`, or not polled at all (DISABLED or missing): a polling gap is not a
  silent VAAC. With no `feed_health` the records are trusted.

`feed_degraded` returns the feed's `FeedHealth` when TEPHRA's copy may be out of date: status
ERROR, STALE or NEVER, no `last_success_at`, or a last success older than
`settings.stale_after_s(feed)` at `at`. It returns None for a current feed, for a DISABLED
one (VONA off by robots.txt, a feed a replay did not record), for a feed with no health entry
and when `feed_health` is None. The Dispatch Drafter uses it for the OFFICIAL PICTURE
INCOMPLETE header line.
- A SIGMET whose polygon repeats a VAA polygon vertex for vertex is the same source twice
  (research/13): no discrepancy between them, and `summary` of any other discrepancy that
  involves both names them together. Only a SIGMET in force now absorbs its VAA.
`summary` and `values` are code-written (`"VONA 13,701 ft inside SIGMET SFC/FL150"`). The
list is sorted by severity (WARNING, CAUTION, INFO), then kind.

`tephra/agents/llm.py`
```python
Tier = Literal["main", "lite", "tts"]   # TEPHRA_MODEL, TEPHRA_MODEL_LITE, TEPHRA_MODEL_TTS
class LlmPart(TephraModel):        # kind: Literal["text","image","audio"]; text: str|None; data: bytes|None; mime_type: str|None; label: str|None
    @classmethod
    def of_text(cls, text: str) -> Self
    @classmethod
    def of_image(cls, data: bytes, *, label: str, mime_type: str = "image/png") -> Self
    @classmethod
    def of_audio(cls, data: bytes, *, label: str, mime_type: str) -> Self
class LlmCall(TephraModel):        # backend, model_id, prompt_hash, latency_ms, input_tokens, output_tokens, raw_text, error: str|None, cached: bool
class LlmBackend(Protocol):
    @property
    def name(self) -> LlmBackendName: ...
    def model_id(self, tier: Tier) -> str: ...
    async def reserve(self, tier: Tier) -> str | None: ...   # count one HTTP attempt on the tier's model, in the current lane; None = send, else why not
    async def exhaust(self, tier: Tier) -> None: ...         # Google reported the model's daily quota spent: close that model (only) until the quota day ends
    async def pace(self, tier: Tier, tokens: int = 0) -> None: ...   # wait for the model's per-minute slot (requests, and input tokens where Google sets tpm)
    async def structured[T: BaseModel](self, *, tier: Tier, system: str,
                                       parts: Sequence[LlmPart], schema: type[T],
                                       stub: Callable[[], T], temperature: float | None = None
                                       ) -> tuple[T | None, LlmCall]: ...
class GeminiBackend: ...           # google-genai Client(api_key=..., vertexai=False).aio.models.generate_content, JSON mime + response_json_schema; .quota: QuotaLedger
class StubBackend: ...             # returns stub(), model_id "stub", never touches the network; reserve grants, exhaust does nothing
class RatePacer: ...               # rpm sends (and, with tpm, input tokens) in any 60 s, per model
def get_llm(settings: Settings, *, quota: QuotaLedger | None = None) -> LlmBackend   # without a ledger the Gemini backend counts in memory
def estimate_tokens(texts: Iterable[str]) -> int                 # characters / 3.5, for tokens-a-minute pacing
def prompt_hash(system: str, parts: Sequence[LlmPart]) -> str   # images and recordings contribute their sha256
def temperature_for(model_id: str) -> float                      # 1.0 for gemini-3* model ids, else 0.2
def daily_quota_spent(exc: BaseException) -> bool                # a 429 whose QuotaFailure names a per-day quota
def usage_tokens(usage: Any) -> tuple[int | None, int | None]    # (prompt_token_count, candidates + thoughts) from usage_metadata
def sum_known(values: Iterable[int | None]) -> int | None        # sum of the known counts, None when none is known
def gemini_call_fields(*, tier: Tier, model: str, outcome: str, latency_ms: int,
                       input_tokens: int | None, output_tokens: int | None,
                       cached: bool = False, actor: str = "llm") -> dict[str, Any]
```
Rules: `structured` never raises for model trouble: on API error, timeout, quota, invalid
JSON or schema failure it returns `(None, call)` with `call.error` set. Tier `main` uses
`settings.model`, tier `lite` uses `settings.model_lite`. `temperature=None` means
`temperature_for(model_id)`: 1.0 for Gemini 3 model ids (`gemini-3*`; research/10 C9, lower
values may loop) and 0.2 otherwise. Validated answers are cached on disk under
`<cache_dir>/llm`, keyed by model, prompt hash, schema and temperature; a cache hit spends no
budget. Every HTTP attempt, each retry included, is reserved from its model's daily budget
(`tephra.agents.quota`, below) before it is sent, in the lane of the work (`current_lane()`,
and `current_admitted()` inside a routine job the AI worker admitted);
a refusal -> `(None, call)` with `error="budget_exhausted"` and nothing sent. 5xx answers,
per-minute 429s and transport errors are retried twice (after 2 s and 8 s); a 429 whose
QuotaFailure names a per-day quota is not retried and closes that model (`exhaust`), not the
other tiers' models, until the quota day ends. `structured` paces and then reserves each
attempt itself (the slot first, so an attempt cancelled while it waits is not counted); every ADK agent reserves and paces each model turn through `ModelGuard` (section 5.18)
and closes its model on a per-day 429. ADK's Gemini model and the google-genai client retry
nothing on their own (TEPHRA sets no `retry_options`), so one turn is one HTTP attempt. Speech
(`voice.speak`) reserves from the `tts` tier's model and closes only that model on a per-day
429. The stub's `reserve` always grants and its `exhaust` does nothing.

`tephra/agents/quota.py` (L3): the daily budgets.
```python
Lane = Literal["urgent", "interactive", "routine"]
def current_lane() -> Lane                     # the lane of calls made here: "interactive" unless the AI worker set one
def current_admitted() -> bool                 # inside a routine job the AI worker admitted (pacing no longer applies)
def use_lane(lane: Lane, *, admitted: bool = False) -> ContextManager   # the AI worker wraps each job in its lane
def quota_day(at: datetime) -> date            # Google's day, midnight to midnight Pacific (wall clock, even in REPLAY)
def day_bounds(day: date) -> tuple[datetime, datetime]
class ModelDay(TephraModel):                   # ai_budget/<quota day>/<model id>: quota_day, model_id, used: {lane: n}, closed, closed_reason, updated_at
class Shares:                                  # budget, urgent, interactive, routine, burst, release_after; Shares.of(settings, model_id)
class Admission(NamedTuple):                   # ok, reason, next_slot (routine work: when it fits again)
def judge(day, shares, lane, fraction, calls=1, *, admitted=False) -> Admission   # admitted: the daily cap only
def next_routine_slot(day, shares, now, calls=1) -> datetime
class QuotaLedger:
    def __init__(self, settings: Settings, store: Store | None, *, now=SystemClock().now)
    async def reserve(self, model_id: str, lane: Lane, *, admitted: bool = False) -> str | None   # counted in one store transaction, checked again there
    async def close(self, model_id: str, reason: str) -> None          # a per-day 429
    async def load(self, model_id: str, *, fresh: bool = False) -> ModelDay
    async def load_all(self, model_ids, *, fresh: bool = False) -> list[ModelDay]
    def admission(self, model_id: str, lane: Lane, calls: int = 1) -> Admission   # from the copy in memory (the AI worker); a closed model's slot is the next quota day
    def unreadable(self, model_id: str) -> str | None   # why the count cannot be read or written now (the store), or None
```
Rules: counts are kept per model id (two tiers on one model share one count) and quota day in
the store collection `ai_budget`, so a new instance, a crash or a redeploy carries on from the
day's count. Each model's budget (`Settings.daily_budget`) is its free limit less
`TEPHRA_AI_BUDGET_MARGIN`, or the `TEPHRA_MODEL_DAILY_BUDGET` / `TEPHRA_MODEL_LITE_DAILY_BUDGET`
override; a model with no `TEPHRA_MODEL_LIMITS` row has budget 0 and is never called. The
budget splits into lanes: urgent (`TEPHRA_AI_URGENT_SHARE`, 30%; only on models urgent work
uses, TEPHRA_MODEL and TEPHRA_MODEL_LITE) is never paced and only the budget caps it;
interactive (`TEPHRA_AI_INTERACTIVE_SHARE`, 20%, on TEPHRA_MODEL_LITE; all of TEPHRA_MODEL_TTS's
budget, since speech has neither urgent nor routine work) may take routine's share but never
the unused urgent reserve; routine (the rest, on TEPHRA_MODEL and TEPHRA_MODEL_LITE) is admitted
only while its use stays within its share x the part of the quota day gone by, plus a burst
(`TEPHRA_AI_ROUTINE_BURST` of the budget, at least one call). After `TEPHRA_AI_RESERVE_RELEASE`
(0.75) of the day the unused urgent and interactive reserves flow to routine, all of them by
midnight Pacific. Pacing decides when a routine job starts: the calls of a job the AI worker
admitted (`use_lane("routine", admitted=True)`) are counted as routine but checked only against
the daily cap, so a run that needs more calls than its estimate finishes instead of failing
part-way. A refusal names its reason in plain words; a routine refusal carries the next slot.
If the store cannot be read or written, every call to that model is refused ("the AI budget
store could not be reached ...": the caller reports AI UNAVAILABLE, the AI worker keeps routine
work waiting with that reason) and the store is tried again on the next call; a new instance
never starts the day at zero on a failed read. With no store at all (`QuotaLedger(settings,
None)`: an offline backtest, a test) the count is kept in memory by design. `budget.py`
(`budget_view`) shows the counts; nothing outside `quota.py` counts calls.

`tephra/agents/budget.py` (L3): what the Wall and the Desk show.
```python
class AiWork(TephraModel):       # ai_work/<id>: id, kind ("duty_item" | "recover"), label, item: DutyItem | None,
                                 # airports, model_id, lane, urgency, status ("QUEUED" | "WAITING" | "RUNNING"),
                                 # since (wall clock), next_slot_at, reason ("waiting for AI budget, next slot 1432Z"), replay
class BudgetLane(TephraModel):   # lane, words, used, share
class BudgetModel(TephraModel):  # model_id, jobs (plain words, first letter capitalised), used, limit, free_limit,
                                 # remaining, closed, lanes (only those with a share or a use),
                                 # routine_allowed_now, next_routine_slot (None on a model with no routine share),
                                 # pacing (plain words: how the routine share is spread through the day, the
                                 # next slot, "Count unknown: ..." when the store cannot be read)
class BudgetTier(TephraModel):   # tier, model_id, used, limit, remaining (its model's count)
class BudgetView(TephraModel):   # backend, as_of, quota_day, resets_at, models, tiers, waiting: list[AiWork], note
async def budget_view(settings: Settings, llm: LlmBackend, quota: QuotaLedger,
                      work: Sequence[AiWork] = ()) -> BudgetView   # the stub reads zero used
def slot_words(next_slot_at: datetime | None) -> str            # "waiting for AI budget, next slot HHMMZ"
```
`genai.Client(api_key=..., vertexai=False)` only; never Vertex AI, never ADC. Image parts are
sent with a preceding text part `IMAGE {label}`, at high media resolution; an audio part is sent
as inline bytes with its mime type and no announcement (and sets no media resolution). Each request
times out after `llm_timeout_s`.

Every `GeminiBackend.structured` call ends in one INFO line on the `tephra.agents.llm` logger
whose `json_fields` are `gemini_call_fields(...)`: `event="gemini_call"`, `actor="llm"`,
`tier`, `model`, `outcome` (`ok`, `cache_hit`, `budget_exhausted`, `error`, `empty`,
`invalid`), `latency_ms`, `input_tokens`, `output_tokens` (None when Gemini reported none) and
`cached`. The fields never carry a prompt, a volcano or flight id, or a name; Cloud Logging
reads them as `jsonPayload.*` (deploy/monitoring.sh counts them). `read_plume` sums the token
counts of the calls it made into `PlumeAssessment.input_tokens` and `.output_tokens`
(`sum_known`; a call refused by the budget is not counted).

`tephra/agents/schemas.py`
```python
def gemini_schema(model: type[BaseModel]) -> dict[str, Any]   # JSON schema inlined ($defs resolved), no title/default/additionalProperties
def parse_json_model[T: BaseModel](text: str, model: type[T]) -> T   # tolerant of ```json fences; raises ValueError
```

`tephra/agents/plume_reader.py`
```python
PROMPT_PATH: Final[Path]                          # agents/prompts/plume_reader.md
async def read_plume(situation: Situation, llm: LlmBackend, *, images: Sequence[LlmPart] = (),
                     settings: Settings, trace: TraceSink | None = None,
                     call_model: bool = True) -> PlumeAssessment
def plume_question(situation: Situation, *, max_age: timedelta) -> Question
                     # material: the products by content (situation.input_hash), the
                     # discrepancies by id and severity, and the supporting evidence (source id
                     # and text hash: the Satellite Reader's reading) (section 5.7, model answers)
def reused_assessment(answer: AiAnswer, held: PlumeAssessment, situation: Situation, *,
                      trace: TraceSink | None = None) -> tuple[PlumeAssessment | None, list[str]]
                     # the kept reading, checked again with validate_estimate against situation
                     # (with its supporting evidence, as a fresh read gets it);
                     # created_at = answer.shown_at(now); (None, problems) when it fails
def build_parts(situation: Situation, images: Sequence[LlmPart]) -> list[LlmPart]
def validate_estimate(estimate: PlumeEstimate, situation: Situation) -> list[str]
def stub_estimate(situation: Situation, settings: Settings) -> PlumeEstimate
def official_only(situation: Situation, settings: Settings, note: str) -> PlumeEstimate
```
One `llm.structured(tier="main", schema=PlumeEstimate, ...)` call (plus at most one
repair), at the tier's default temperature. Input to the model, in order: the volcano; the
official floor (each layer's source id, label and band, the highest official top and whether
a polygon is in force now); the verbatim raw texts of every SIGMET/VONA/VAA with their source
ids, evidence states and observation ages in minutes; the discrepancy list; winds by flight
level (`toward_deg` and speed per FL, profiles about +0, +3, +6 and +12 h); the BTD summary
(stats, indicator, caveats; a SILENT or INCONCLUSIVE BTD adds "<SILENT|INCONCLUSIVE> never
means no ash."); the images; and the task block (allowed modes, limits, citable ids).
`images` holds the stored frame PNGs and the BTD PNG (core loads them); an image whose label
is not a source id of the situation is not sent, and a trace line counts it. A `SUPPORTING EVIDENCE` block, present only when `situation.supporting` is not
empty, follows the images: the Satellite Reader's text under its `SAT-` id, which the model may
cite and which can only raise uncertainty or point to ash outside the official area. The prompt
tells the model to cite sources by id only and to write no times or dates.

Validator (`validate_estimate` returns problems; empty = accepted):
1. every `sources_used` and `which_source_we_lean_on` is in `situation.source_ids()` or is an
   official layer's source id (a kept VAA is not in `situation.vaas`); every `discrepancy_id`
   is in the situation's discrepancies; the task block's citable ids are the same set;
2. no timestamp anywhere in the text fields (`rationale`, `uncertainty_notes`, and each
   disagreement's `reading` and `why`, with source and discrepancy ids removed first):
   reject `\d{8}/\d{4}Z?`, ISO dates `\d{4}-\d{2}-\d{2}`, `(?<![\d/])\d{1,2}/\d{4}Z?(?!\d)`,
   `(?<!\d)\d{6}Z`, `(?<!\d)\d{4}Z`, `(?<!\d)\d{1,2}:\d{2}(?!\d)`, and clock times with a zone
   word, `validators.ZONE_TIME_PATTERN` =
   `(?<!\d)\d{4}\s?(?:UTC|GMT|Z|LT|LCL|LOCAL|WIB|WITA|WIT|JST|PHT|HRS)(?![A-Z])`, matched
   ignoring case (the same pattern is in `validators.CLOCK_PATTERNS`);
3. HYPOTHESIS while `situation.official_valid_now()` is rejected; OFFICIAL or WIDENED with
   no official layer is rejected;
4. `top_fl * 100 < situation.official_top_ft()` is rejected (never shrink);
5. `sector_width_deg() > MAX_SECTOR_WIDTH_DEG` rejected; `extent_km > MAX_PLUME_EXTENT_KM`
   rejected; `horizon_h > MAX_HORIZON_H` or `horizon_h < 1` rejected (core keeps an
   assessment for its horizon, so minutes would re-ask every tick); `base_fl >= top_fl`
   rejected (the code-built OFFICIAL estimate with no layers, band 0/0, is never put through
   these rules);
6. a SILENT or INCONCLUSIVE BTD or a non-observation may not be the source leaned on
   (`which_source_we_lean_on`), and no sentence may name one ("silent", "inconclusive", "not
   observed", "night", ...) next to a narrowing verb that is not negated;
7. a HYPOTHESIS estimate needs `base_fl <= ceil(volcano.summit_elev_ft / 100)`, so ash
   below a higher base is never left out ("HYPOTHESIS base_fl B starts above the summit
   (FLS); ash below it would be left out; give base_fl <= S"); while a recent ash VONA exists
   (the newest VONA with `ash_observed` issued in the last 6 h), it also needs
   `extent_km > 0`, `sector_width_deg() > 0` and `top_fl >= min(600, ceil(cloud_top_ft /
   100))` when the VONA gives a top. While HYPOTHESIS is allowed the task block says so ("A
   HYPOTHESIS starts at or below the summit: base_fl <= S." and "<VONA> reports ash, so a
   HYPOTHESIS needs top_fl >= N, extent_km > 0 and two different bearings."); the prompt
   states the VONA rule.
On rejection, when the model answered (`raw_text` not empty): exactly one repair call that
lists the problems and quotes the previous answer. If that still fails, or the model returned
nothing, there is no model reading: outcome `MODEL_FAILED`, `validation_errors` kept, and the
estimate is `official_only(..., "AI UNAVAILABLE: <reason>.")`, which is not a fallback but the
binding floor: mode OFFICIAL, band from the official layers rounded outward (0/0 when none),
`bearing_from_deg = bearing_to_deg = 0`, `extent_km = 0`, `horizon_h =
settings.default_horizon_h`, `confidence = 1.0`, `sources_used` = official source ids. With no
official layer nothing is drawn (the trace line says so); no model-free hypothesis is made.
Core writes an `AI_FAILED` audit entry and the trace line is `error` level. `attempts` counts
the calls made, not a call refused by the budget.

`stub_estimate` (backend `stub`, outcome `STUB`, deterministic): with an official layer ->
OFFICIAL (band from layers, confidence 1.0); else with a VONA reporting ash in the last 6 h
-> HYPOTHESIS: sector centred on the wind `toward_deg` at the VONA top's flight level (the
top is the VONA's cloud top, else the summit), or on the VONA movement if no wind, +/- 30
degrees; `extent_km = min(300, wind_kt * 1.852 * 3)` with winds, 300 on the VONA movement,
and at least 25; `base_fl = 0`, `top_fl = min(600, ceil(top ft / 1000) * 10 + 20)`,
`horizon_h = 3`, confidence 0.3; else (no ash VONA, or neither winds nor a direction)
OFFICIAL with no layers. `rationale` starts with `"NO MODEL:"`. With the stub backend a stub
estimate that fails `validate_estimate` is replaced by `official_only`.

`call_model=False` (core decided no call is needed, section 5.7) returns the
`official_only` estimate with `uncertainty_notes = "No model call was needed; official
products only."`, outcome `OFFICIAL_ONLY`, `attempts=0`, `model_id="none"` and a `code` trace
line. With the stub backend the outcome is always `STUB`. `read_plume` sets
`PlumeAssessment.id = stable_id("PA", volcano_id, input_hash, prompt_hash, model_id)`.

### 5.6 planner-drafter

`tephra/agents/validators.py`
```python
MAX_LEVEL_FL: Final = 600              # bound on any level named; the highest proposed is ctx.max_change_level_fl
COST_NOTE_MAX_CHARS: Final = 120
REASONING_MAX_CHARS: Final = 800
ZONE_TIME_PATTERN: Final = r"(?<!\d)\d{4}\s?(?:UTC|GMT|Z|LT|LCL|LOCAL|WIB|WITA|WIT|JST|PHT|HRS)(?![A-Z])"
CLOCK_PATTERNS: Final[tuple[re.Pattern[str], ...]]   # the plume time and date patterns + ZONE_TIME_PATTERN, ignoring case
ACTION_WORDS: Final[dict[ActionKind, tuple[str, ...]]]
VOCABULARY: Final[frozenset[str]]                   # plain words of four or five capitals that are not places
def allowed_actions(mode: PlumeMode) -> list[ActionKind]          # from ALLOWED_ACTIONS, fixed order
def band_clears_hazard(fl_min: int, fl_max: int, *, ctx: PlannerContext) -> bool   # wholly outside band plus margin
def validate_decision(decision: PlannerDecision, ctx: PlannerContext) -> list[str]
def validate_draft(draft: DraftText, *, ctx: PlannerContext, plan: PlannedAction) -> list[str]
TECHNIQUE_PROBLEM: Final = "BODY GIVES ENGINE-HANDLING OR ESCAPE TECHNIQUE: CREW FOLLOWS ITS QRH AND OPERATOR PROCEDURES; DISPATCH ADVISES ROUTE ONLY"
def technique_problems(upper: str) -> list[str]     # [TECHNIQUE_PROBLEM] or []; drafts and Desk edits
```
Decision rules: the action must be in `allowed_actions(ctx.plume_mode)` as well as in
`ctx.allowed_actions` (HYPOTHESIS: MONITOR or HOLD only). CHANGE_LEVEL needs
`change_level_fl_min/max`, ordered, at or below `ctx.max_change_level_fl`, whose band clears `[hazard_base_ft -
margin, hazard_top_ft + margin]`. HOLD needs `hold_fl` (1 to 600); while `flight.inside_now`,
`hold_fl` must clear the hazard band plus margin; a `hold_fl` other than the present FL is a
level change, so it is not allowed in HYPOTHESIS and must be at or below
`ctx.max_change_level_fl`. CONTINUE needs
the aircraft's present and selected levels (`aircraft_band_ft`) clear of the hazard band plus
margin. DIVERT needs an `alternate_icao` that is one of `ctx.alternates` with `check.ok` and a
`taf_source_id`. `reasoning` is not empty, at most 800 characters, and has no clock times
(`CLOCK_PATTERNS`).

Draft rules: the action is allowed in the mode, and a DIVERT's alternate is listed, has a TAF
and passed the screen. Body: not empty, upper case, `len <= ADVISORY_BODY_MAX_CHARS`,
printable ASCII; it names the action (`ACTION_WORDS`), and a DIVERT names the alternate, a
CHANGE_LEVEL states a band FL and a HOLD states the holding FL; in HYPOTHESIS it may not say
DIVERT, CLIMB, DESCEND, CHANGE LEVEL or LEVEL CHANGE in any inflection (DIVERTING, DIVERSION,
DESCENT, CLIMBING); any word of four or five capitals (an ICAO code, or a 5-letter word that
looks like a waypoint) must be a word of the input (alternate ICAO codes, the airline name,
volcano, flight, callsign, type, alternate names, fuel formulas, screen reasons) or in
`VOCABULARY`, a fixed list of plain English and ACARS words that holds no ICAO location id or
place name; no clock times or dates (`CLOCK_PATTERNS`: `1830 UTC` and `0930UTC` included);
every number in the body must appear in the input (FLs and feet of the hazard band and
margin, present and selected levels, minutes to entry, confidence, speed, track, alternate
distances and bearings, and the numbers in the input texts and fuel formulas); body must
not say `CLOSED` or any form of `CLOSE` (TEPHRA writes company advisories, research/07 rule
21); body must ask the crew for a volcanic activity report (contains `VAR`); body must not
give engine handling or escape technique (`technique_problems`: IDLE, THRUST, POWER TO, POWER
BACK, AUTOTHRUST, AUTOTHROTTLE, ESCAPE MANOEUVRE or MANEUVER, DESCEND... TURN, 180 DEG or
180 TURN, U-TURN; TURN, REVERSE TRACK, HEADING 180 and FL180 stay legal, and `VOCABULARY`
holds no IDLE). `cost_note`:
one line, <= 120 chars, printable ASCII, no clock times, and the same place check (ignoring
case) and number rule.

`tephra/agents/exposure_planner.py`
```python
PROMPT_PATH: Final[Path]
CONTEXT_STATE_KEY: Final = "tephra_ctx"
DECISION_STATE_KEY: Final = "tephra_decision"
MAX_MODEL_TURNS: Final = 10
DAILY_QUOTA_SPENT: Final = "GEMINI DAILY QUOTA SPENT (429): LITE TIER CLOSED FOR THE QUOTA DAY"
def build_planner_context(flight: ExposedFlight, cone: HazardCone, *, volcano_name: str,
                          airports: AirportCatalogue, tafs: Mapping[str, Taf], at: datetime,
                          policy: OperatorPolicy, routes: RouteTable | None = None,
                          situation: Situation | None = None) -> PlannerContext
def cheapest_reroute(reroutes: Sequence[RerouteOption]) -> RerouteOption | None   # the OK option with the fewest extra minutes
def planner_limits(policy: OperatorPolicy) -> dict[str, int]      # the PlannerContext fields from policy.planner
def rule_based_decision(ctx: PlannerContext) -> PlannerDecision
async def plan_flight(ctx: PlannerContext, llm: LlmBackend, *, settings: Settings,
                      trace: TraceSink | None = None, reuse: Reuse | None = None) -> PlannedAction
                      # reuse: the same model's plan for the same material question, used when
                      # normalise_decision + validate_decision pass for ctx now (no ADK run, no
                      # budget); else the agent runs and a plan that passes is kept
def planner_question(ctx: PlannerContext, *, cone_version: str, policy_version: str,
                     max_age: timedelta) -> Question
                      # material: flight, cone id and version, plume mode, allowed actions, policy
                      # version, urgency_band(ctx), level in 2,000 ft steps (LEVEL_STEP_FL), open
                      # alternates
def cone_version(cone: HazardCone) -> str   # hash of the cone's content without created_at and
                                            # valid_to: a cone rebuilt on new winds keeps its id
                                            # but not its version
def urgency_band(ctx: PlannerContext) -> int   # 0 inside; 1 + limits (divert, hold) the entry lies beyond
```
`build_planner_context`: alternates are the 5 nearest from `airports.nearest(flight.lat,
flight.lon, max_nm=policy.alternates.search_radius_nm)`; `divert = fuel.divert_line(...,
extra_minutes=policy.fuel.divert_extra_min)`; the ETA is `at` plus the divert line's cruise
minutes; each is screened with `tephra.feeds.taf.assess_alternate` and the policy's minima;
an alternate inside the cone or within `alternates.terminal_radius_nm` of it (a disc of that
radius that overlaps the cone, by `polygon_iou`) is not ok with reason `"INSIDE HAZARD
CONE"`; `allowed_actions = allowed_actions(cone.mode)`; `vertical_margin_ft` and
`planner_limits(policy)` fill the policy fields. `route = routes.lookup(flight, airports, policy)`
(the leg of the callsign's chain the aircraft flies, or None) and `reroutes = plan_reroutes(...)`
(section 5.11; the destination's position from `routes.position`, the winds from `situation`;
`[]` in HYPOTHESIS mode). `REROUTE` is dropped from `allowed_actions` unless an OK option exists.

`rule_based_decision` (the stub backend's plan only, deterministic; every threshold is a
`PlannerContext` field from the policy, policy A values in brackets): HYPOTHESIS -> HOLD at
the current FL if `minutes_to_entry <= hold_within_min` (30) and the hold is outside the hazard (not
`inside_now`, or the current FL clears the band plus margin), else MONITOR.
OFFICIAL/WIDENED -> CONTINUE when the present and selected levels are above the hazard top
plus margin; else CHANGE_LEVEL to the nearest `level_band_fl` (2,000 ft) band clear of the
hazard plus margin within `level_search_ft` (4,000 ft) of the current level and at or below
`max_change_level_fl` (FL410) (ties go to the higher band); else REROUTE (the cheapest OK
lateral option) when one exists and the flight is not urgent (not `inside_now`, entry beyond
`divert_within_min`); else if `inside_now` or `minutes_to_entry <= divert_within_min` (15) and
an alternate with `check.ok` and a TAF exists, DIVERT to the nearest; else if `inside_now`, MONITOR (a hold at present position
would stay inside the hazard; the dispatcher advises the exit); else if `minutes_to_entry <=
hold_within_min` (30), HOLD at the current FL; else MONITOR. Reasoning always starts with `"NO MODEL:"`.

`plan_flight`: backend `stub` -> `rule_based_decision`, outcome `STUB`. Backend `gemini` ->
ADK `LlmAgent` on `settings.model_lite` with FunctionTools that read the context from
`tool_context.state[CONTEXT_STATE_KEY]` (a `PlannerContext` JSON dump): `get_flight()`,
`list_alternates()`, `check_alternate(icao)`, `check_level_band(fl_min, fl_max)`,
`estimate_cost(action, alternate_icao=None)`, and `submit_plan(action, reasoning,
change_level_fl_min=None, change_level_fl_max=None, hold_fl=None, alternate_icao=None,
alternatives_considered=None)`, which validates the `PlannerDecision`, records it in
`state[DECISION_STATE_KEY]` and answers `{accepted, problems}`. A tool that raises on the
model's arguments answers an error to the model instead of ending the run. Tool calls become
`ToolCallRecord`s (kept when the run fails) and are streamed to `trace` as
`TraceStage.PLANNER`, actor `adk`. The `before_model_callback` takes every model turn from
the lite model's budget (`await llm.reserve("lite")`) and stops the run after `MAX_MODEL_TURNS`; the
`on_model_error_callback` (async) turns a 429 whose QuotaFailure names a per-day quota into
`await llm.exhaust("lite")` and ends the run with no repair turn (ADK 2.11 surfaces that 429 as
`_ResourceExhaustedError`, a `ClientError` that keeps `.code` and `.details`). Invalid or
missing decision -> one repair turn with the problems -> outcome `MODEL_FAILED`: `decision` is
None, the problems are kept as `validation_errors` (`DAILY_QUOTA_SPENT` after a spent quota
day) and the trace line says `AI UNAVAILABLE`; an ADK or API exception ends the same way.
Core then records an `AiFailure` (`ai_failure`, stage `planner`) for the Desk and drafts
nothing. `submit_plan` and `estimate_cost` take an optional `reroute_id`, `list_reroutes()` is a
fifth read tool, and a REROUTE decision must name an OK option of the context and no other
target field (`validators.reroute_of`). Each agent turn is bounded by `llm_timeout_s`. ADK runs
with `InMemoryRunner` inside the process (google-adk 2.11; research/06). The planner's model
callbacks go through a turn meter around the `ModelGuard`: every turn that reaches Gemini logs
the `gemini_call` fields (section 5.5) with `actor="adk"`, `tier="lite"` and `cached=False`,
from the `after_model_callback` (ADK 2.11 calls it as `(callback_context, llm_response)` and it
returns None, so the response is kept; tokens from `llm_response.usage_metadata`) or, with
outcome `error`, from the `on_model_error_callback`. A turn the guard stops is not logged. The
plan's `input_tokens` and `output_tokens` are `sum_known` over those turns, the repair turn
included, and are kept on a `MODEL_FAILED` plan too.
`PlannedAction.id = stable_id("PLAN", flight.id, cone_id)`; its `fuel` is the hold line for
HOLD, the alternate's divert line for DIVERT, the reroute's `reroute_line` for REROUTE, else None.

`tephra/agents/dispatch_drafter.py`
```python
PROMPT_PATH: Final[Path]
HEADER_TITLE: Final = "TEPHRA COMPANY ADVISORY - RING OF FIRE AIR (FICTIONAL) - NOT FOR OPERATIONAL USE"
NEEDS_HUMAN: Final = "NEEDS_HUMAN"
POLICY_A_AVOID: Final = "POLICY A ADVISES AVOIDING THE AREA (DOC 9974 APP 5 5.4(D)(2)); NO DRIFT-DOWN OR ESCAPE CHECK MADE"
def render_header(*, ctx: PlannerContext, plan: PlannedAction, cone: HazardCone,
                  sources: Sequence[SourceRef], at: datetime, replay: bool = False,
                  replay_case: ReplayCase | None = None,
                  degraded_feeds: Sequence[FeedHealth] = (),
                  drafted_at: datetime | None = None) -> str
def stub_draft(ctx: PlannerContext, plan: PlannedAction) -> DraftText
def select_sources(situation: Situation, flight: ExposedFlight) -> list[SourceRef]
async def draft_advisory(*, situation: Situation, assessment: PlumeAssessment, cone: HazardCone,
                         ctx: PlannerContext, plan: PlannedAction, llm: LlmBackend,
                         settings: Settings, policy: OperatorPolicy,
                         trace: TraceSink | None = None,
                         feed_health: Mapping[FeedId, FeedHealth] | None = None,
                         replay_case: ReplayCase | None = None,
                         reuse: Reuse | None = None) -> Advisory | AiFailure
                         # stamps policy_id, policy_version, policy_hash and replay_case_id
def drafter_question(ctx: PlannerContext, plan: PlannedAction, *, cone_version: str,
                     policy_version: str, max_age: timedelta) -> Question
                         # material: flight, cone id and version, policy version (the advisory
                         # records the policy it was drafted under), action and its target (band,
                         # hold FL, alternate, reroute option id)
```
``reuse`` is the same model's body and cost note for the same material question: when
``validate_draft`` passes for this context and plan now, it is used without a model call (no
repair, no budget), the advisory keeps its model id and drafter prompt hash, and `drafted_at`
is the time it was written (`AiAnswer.shown_at`); otherwise the model is asked as usual and a
draft that passes is kept. The header's `DRAFTED` line is `drafted_at`; when that is an earlier
minute than the facts' time (`created_at`), the entry line ends `AT HHMMZ` (the facts' time).
`render_header` (code only) prints, upper case: `HEADER_TITLE`; `{proxy_flight} (ADS-B
{callsign or NO CALLSIGN} {hex})`; for a REPLAY draft `REPLAY - RECONSTRUCTED FROM ARCHIVES
{case_id} ({recorded_from as DD MON YYYY}) - NOT LIVE` when `replay_case.reconstructed`,
otherwise `REPLAY - RECORDED FROM LIVE FEEDS {case_id} ({date}) - NOT LIVE`, or `REPLAY - NOT
LIVE` when `replay` is set with no case; `VOLCANO {name}`; `ACTION` with level band, holding FL or
alternate; for a CHANGE_LEVEL band (or a CONTINUE flight's present FL) wholly above
`hazard_top_ft + vertical_margin_ft`, `OVER ASH: FL{low} IS {low*100 - top} FT ABOVE THE
FL{top//100} TOP. {POLICY_A_AVOID}`, and wholly below `hazard_base_ft - vertical_margin_ft`,
`UNDER ASH: FL{high} IS {base - high*100} FT BELOW THE FL{base//100} BASE. {POLICY_A_AVOID}`;
`ENTRY {n} MIN` or `INSIDE NOW`; `CONE {mode} {confidence%}` (+ `NO MODEL` when the
cone's backend is `stub`); one `OFFICIAL PICTURE INCOMPLETE: {feed} NOT UPDATED SINCE
{ddhhmmz of last_success_at or NEVER}; CONFIRM THE CURRENT VAA AND SIGMET WITH MET BEFORE
ACTING` per entry of `degraded_feeds` (information only: it changes no action or gate);
`DRAFTED {hhmmz(at)}`; then one `SRC` line per source: `{feed}
{source_id} ISSUED {ddhhmmz or N/A} FETCHED {ddhhmmz} #{sha256_short}` (+ `STALE`), the
binding product (SIGMET) first. `select_sources`: the valid SIGMETs (latest start first), the
latest VONA, the latest VAA and the wind profile nearest the flight's observation time. The
flight's ADS-B snapshot is not cited: its provenance reaches neither the `Situation` nor the
`ExposedFlight`, so the header's `(ADS-B ...)` line names the target instead.
`draft_advisory`: Gemini (`tier="lite"`, `schema=DraftText`, the tier's default temperature)
writes `body` and `cost_note` only, from a facts JSON with no clock times, ids or hashes (a
REROUTE adds its route string, extra NM and minutes, and fuel line; the body must contain the
route string verbatim and coordinates are accepted only as written in it); validate with
`validate_draft`; one repair when the model answered (a draft, or raw text quoted back up to
2,000 characters). No answer, or a draft that still fails the checks, returns an `AiFailure`
(stage `drafter`, `ai_failure(...)`) and a trace line `DRAFTER AI UNAVAILABLE (...): NO DRAFT, A
DISPATCHER MUST WRITE THE MESSAGE`; nothing is substituted. `stub_draft` (the stub backend's
draft, labelled NO MODEL, `llm_backend="stub"`) exists for tests only. The stub draft tells an aircraft
already inside its new band `DO NOT CLIMB ABOVE FLnnn` or `DO NOT DESCEND BELOW FLnnn`, and
an inside-now MONITOR (not HYPOTHESIS) `MONITOR AND COORDINATE EXIT WITH ATC. DISPATCH TO
ADVISE.` Returns an `Advisory` with `status=DRAFT`, `version=1`,
`created_at=updated_at=timeutil.now()`, `drafted_at` (`created_at`, or a kept body's time),
`replay=situation.mode is REPLAY`,
`replay_case_id` from `replay_case` (a `replay_case` with a LIVE situation is a ValueError),
`policy_hash=policy.content_hash()[:12]`, `prompt_hashes`
for `plume_reader`/`planner`/`drafter`, `dedupe_key = stable_id("DD", hex, volcano_id,
action, change_level_fl_min, hold_fl, alternate_icao, reroute id)`, `reroute` = the chosen option, `input_hash =
situation.input_hash`. The header's `degraded_feeds` are `discrepancies.feed_degraded` at
`created_at` for `FeedId.SIGMET` and the volcano's VAAC feed (`VAAC_TOKYO` or `VAAC_DARWIN`).
It does not store anything.

`tephra/agents/adk_app.py`
```python
AGENT_NAME = "tephra_exposure_planner"
def build_planner_agent(model: str, *, before_model_callback: Any = None,
                        on_model_error_callback: Any = None) -> "LlmAgent"
root_agent: "LlmAgent"     # build_planner_agent(get_settings().model_lite) at import
agent = sys.modules[__name__]
```
`build_planner_agent` runs the model at `temperature_for(model)`, reads its instruction from
`prompts/planner.md`, and answers a tool that raised with an error for the model
(`on_tool_error_callback`). For ADK evaluation
(`AgentEvaluator.evaluate(agent_module="tephra.agents.adk_app", ...)`): the module exposes
`root_agent` and defines `agent` as the module itself (`agent = sys.modules[__name__]`),
which google-adk 2.11's AgentEvaluator needs for `agent_module="tephra.agents.adk_app"`.
Eval cases put a `PlannerContext` dump in `session_input.state["tephra_ctx"]`.

Prompts (`agents/prompts/*.md`) are versioned by content: `prompt_hash` covers the file text.

### 5.7 core

`tephra/store/__init__.py`
```python
def open_store(settings: Settings) -> Store      # SqliteStore or FirestoreStore (imports google.cloud lazily)
def encode_doc(doc: Mapping[str, Any]) -> str     # compact strict JSON: NaN and infinities become null
def decode_doc(text: str) -> dict[str, Any]
```
`tephra/store/sqlite_store.py`: `class SqliteStore(Store)`, constructor `(path: Path,
blob_dir: Path)`; stdlib `sqlite3` via `asyncio.to_thread`; one table `docs(collection, id,
doc JSON, PRIMARY KEY(collection, id))`; CAS in a transaction (a failed COMMIT rolls back);
blobs under `cache_dir/blobs/`. `tephra/store/firestore_store.py`: `class
FirestoreStore(Store)`, constructor `(project: str, database: str, bucket: str)`;
`google.cloud.firestore.AsyncClient` and Cloud Storage for blobs (runs only inside Cloud Run
with its service account); each document is stored as its JSON text in the field
`tephra_doc` beside copies of its short top-level scalar fields (for a collection in
`INDEXED_ONLY`, `ai_answers`, only those fields: `expires_at`); equality filters (and one
`in`) run on the server and the rest in memory, so no composite index is needed; CAS in a
Firestore transaction; ids escaped with `escape_doc_id`. Both write documents with
`encode_doc`.

`tephra/desk/audit.py`
```python
GENESIS_SHA256: Final = "0" * 64
class ChainedAuditEntry(AuditEntry):   # + seq: int (1, 2, ...), prev_sha256: str, sha256: str
async def record(store: Store, *, actor: str, action: AuditAction, advisory_id: str | None = None,
                 before: Mapping[str, Any] | None = None, after: Mapping[str, Any] | None = None,
                 input_hashes: Sequence[str] = (), model_id: str | None = None,
                 prompt_hash: str | None = None, note: str | None = None) -> AuditEntry
async def list_entries(store: Store, *, advisory_id: str | None = None, limit: int = 100) -> list[AuditEntry]
async def verify_chain(store: Store, *, limit: int = 100_000) -> list[str]   # problems; empty = intact
```
The audit trail is hash-chained: each entry carries `seq`, the previous entry's `sha256`
(`prev_sha256`, zeros for the first) and its own `sha256` over every other field
(canonical JSON), so an edited entry breaks its own hash and a deleted one breaks the next
link. Entries are chained under a per-store lock in one process. `list_entries` is newest
first (by `seq`).

`tephra/desk/approvals.py`
```python
class VersionConflict(Exception): current: Advisory
class InvalidTransition(Exception): ...
class AdvisoryNotFound(Exception): ...
class EditRejected(Exception): problems: list[str]
async def submit_draft(store: Store, bus: EventBus, advisory: Advisory, *,
                       replacing: Sequence[str] = ()) -> Advisory | None
async def approve(store: Store, bus: EventBus, advisory_id: str, *, expected_version: int, actor: str,
                  reason: str | None = None, note: str | None = None) -> Advisory
async def edit_and_approve(store: Store, bus: EventBus, advisory_id: str, *, expected_version: int,
                           body: str, actor: str, reason: str | None = None,
                           note: str | None = None) -> Advisory
async def reject(store: Store, bus: EventBus, advisory_id: str, *, expected_version: int,
                 reason: str, actor: str) -> Advisory
async def supersede(store: Store, bus: EventBus, advisory_id: str, *, reason: str,
                    superseded_by: str | None = None) -> Advisory | None
async def list_advisories(store: Store, *, status: AdvisoryStatus | None = None, limit: int = 50) -> list[Advisory]
async def get_advisory(store: Store, advisory_id: str) -> Advisory | None
```
Transition rules: only DRAFT moves. approve -> APPROVED; edit -> EDITED (body stripped,
upper-cased, 1..`ADVISORY_BODY_MAX_CHARS` chars, no engine handling or escape technique
(`validators.technique_problems`), both `body` and `edited_body` kept); reject
-> REJECTED (`reason` >= 3 chars after stripping); supersede -> SUPERSEDED (actor `system`,
`superseded_by` set, the reason kept as the audit note). Each transition increments
`version` through `compare_and_set_advisory`, sets `decided_by`/`decided_at` (dispatcher
transitions), writes an `AuditEntry` (before/after = status, version, body, edited_body,
reject_reason, decision_reason, policy_id, policy_version, policy_hash; `note` = the caller's
note for approve and edit; `input_hashes` = advisory `input_hash` + every source sha256; `model_id`;
`prompt_hash` = drafter hash) and publishes `SseEvent.ADVISORY`. APPROVED and EDITED also
write an `OutboundMessage` (text = `advisory.final_text`; `replay`, `replay_case_id` and the
policy id, version and hash copied from the advisory; `queued_wall_at =
timeutil.SystemClock().now()`) to `outbound` and an `OUTBOUND_QUEUED` audit entry whose
`after` adds `policy_id`, `policy_version` and `policy_hash`. Nothing ever leaves the store. `submit_draft` compares only
advisories with the same `replay` value (recorded and live advice never dedupe or supersede
each other): if an open DRAFT for the same flight, other than those named in `replacing`,
has the same `dedupe_key`, return None; if the same `dedupe_key` was APPROVED or EDITED with
`cutoff <= decided_at <= now()` (cutoff = now minus 60 minutes; a looping replay clock can put
a decision in the future) at an `urgency_bucket` at most the new draft's (either None counts
as covered), return None: advice approved further out does not cover a flight that is now
closer. Otherwise the draft is created (a `DRAFT_CREATED` entry and an `advisory` event), and
every other open DRAFT of the flight is superseded with reason `REPLACED BY A NEWER DRAFT`,
except those in `replacing`, which the caller supersedes.

`tephra/replay/cases.py`
```python
MANIFEST_NAME: Final = "manifest.json"
def cases_dir(data_dir: Path) -> Path                          # data_dir / "replay"
def case_path(data_dir: Path, case_id: str) -> Path            # ValueError for an unsafe case id
def list_cases(data_dir: Path) -> list[ReplayCase]             # newest recorded_from first
def load_case(data_dir: Path, case_id: str) -> ReplayCase
def select_case(data_dir: Path, case_id: str | None) -> ReplayCase   # the named case, else the newest
class ReplaySource(Source):
    def __init__(self, case_dir: Path, case: ReplayCase) -> None
    @property
    def case(self) -> ReplayCase
def replay_banner(case: ReplayCase) -> str                     # REPLAY_BANNER_TEMPLATE
def replay_info(case: ReplayCase, *, auto: bool,
                window: tuple[datetime, datetime] | None = None) -> ReplayInfo   # window -> window_from/to; case volcano_ids
def start_replay_clock(case: ReplayCase, *, speed: float, begin: datetime | None = None,
                       end: datetime | None = None
                       ) -> timeutil.ReplayClock               # set_clock(ReplayClock(...)); raises on a bad case
def first_aircraft_at(case: ReplayCase) -> datetime              # first ADS-B answer with status 200, else recorded_from
def stop_replay_clock() -> None                                # set_clock(SystemClock())
```
`ReplaySource.fetch` matches the exact final URL (`build_url(url, params)`): the latest
record with `fetched_at <= now()`, else the earliest record for that URL; no match ->
`FetchError`. Results have `replay=True` and the recorded `fetched_at` and `sha256`
(verified against the file; a record path that leaves the case directory is refused).
`list_cases` skips, with a warning, an unreadable manifest and one whose `case_id` differs
from its directory; `load_case` raises for both.

`tephra/feeds/registry.py`
```python
PRODUCT_FEEDS: Final = (FeedId.SIGMET, FeedId.VONA, FeedId.JMA_VOLCANO, FeedId.VAAC_TOKYO, FeedId.VAAC_DARWIN)
CONTEXT_FEEDS: Final = (FeedId.ADSB, FeedId.TAF, FeedId.METAR, FeedId.WINDS, FeedId.FRAMES, FeedId.HSD)
class FeedPoll(TephraModel):   # feed, ok, record_count, new_record_count, error: str|None, stale: bool
@dataclass
class LiveData: ...            # the in-memory picture: records, adsb and adsb_at, active, health, coverage
async def poll(feed: FeedId, runtime: "Runtime") -> FeedPoll
def disabled_reason(feed: FeedId, settings: Settings, *, replay: bool,
                    recorded: frozenset[FeedId] | None = None) -> str | None
def initial_health(settings: Settings, *, replay: bool,
                   recorded: frozenset[FeedId] | None = None) -> dict[FeedId, FeedHealth]
def due_feeds(at: datetime, states: Mapping[FeedId, FeedHealth], settings: Settings,
              *, active: bool, replay: bool = False,
              recorded: frozenset[FeedId] | None = None) -> list[FeedId]
def uncovered_feeds(runtime: "Runtime", at: datetime) -> list[FeedId]
def health_view(states: Mapping[FeedId, FeedHealth], at: datetime, settings: Settings) -> list[FeedHealth]
def taf_icaos(runtime: "Runtime") -> list[str]
async def save_unsaved(runtime: "Runtime") -> None   # the checkpoint's retry of failed record writes
```
Registry rules:
- Memory first, store second. A poller finishes its in-memory pass (with the VONA and VAA
  windows and the TAF and METAR `covered` sets) before it writes, then writes each new or
  changed record on its own. A record is marked in `runtime.unsaved` before its write and
  unmarked once written, so a failed write, or a poll cut short by its time budget, leaves it
  for `save_unsaved` at the next checkpoint. A database error is logged with its collection,
  goes to `Runtime.store_health`, and never fails the poll: the feed's health stays OK. Winds
  are written only when the profiles changed apart from their provenance.
- `disabled_reason`: HSD without `settings.science` ("raw Himawari processing is off
  (TEPHRA_SCIENCE=0)"); VONA unless `settings.vona_live` (TEPHRA_VONA_LIVE) or REPLAY
  ("live polling off: MAGMA's robots.txt disallows crawling (TEPHRA_VONA_LIVE); replays serve
  recorded VONAs"); in REPLAY, a feed the case did not record (`NOT_RECORDED_NOTE`, "not in
  this replay case: no archive of this feed was recorded"). Such a feed reads DISABLED with
  that note, is never polled, and a restart does not bring back its stored state.
- JMA volcano reports (`FeedId.JMA_VOLCANO`, `fetch_jma_volcano`) are a product feed polled
  every `cadence_jma_volcano_s` in LIVE with no switch (JMA's data is open, PDL 1.0; the
  `TEPHRA_VONA_LIVE` switch is about MAGMA's robots.txt) and in REPLAY only when the case
  recorded them. Its `Vona`s (source id `JMA-VFVO52-<EventID>`), MAGMA's, and verified pasted
  notices (`NOTICE-<sha12>`, via `Runtime.add_verified_notice`) share `live.vonas`, so all of
  them make a volcano active and reach the Plume Reader like any VONA. Each poller counts only
  its own records (`_is_magma`, `_is_jma`) and expires old ones in place (`_expire`): the
  pollers of a tick run side by side and merge into the same dict, so rebinding it would drop
  the records another poller is still adding.
- `due_feeds`: a feed is due when its cadence (less 5 s) has passed since its last attempt.
  TAF, METAR, winds, frames and HSD are due only while a volcano is active; with none active,
  ADS-B runs at four times its cadence. `uncovered_feeds` adds off-cadence polls for an active
  volcano's missing winds, frames or HSD, missing TAF ICAOs, and ADS-B before the first fresh
  positions. These forced polls back off: the first retry waits `GAP_RETRY_S` (120 s); each
  later retry waits as long as the gap had lasted at the last attempt, up to
  `max(GAP_RETRY_S, the feed's cadence)`. A newly uncovered volcano or ICAO starts the gap over.
- `poll` never raises. Each poll, extra ADS-B passes included, runs under
  `asyncio.timeout(tick_interval_s x 0.75)` (`POLL_BUDGET_SHARE`); a poll that runs out reads
  ERROR `no answer within <n> s` and keeps its last data. A
  `FetchError` reads ERROR with its reason, `ScienceUnavailable` reads DISABLED, any other
  exception ERROR; the last good records stay in memory. A poll answered by last-good copies,
  or that lost part of the feed, reads STALE with the reason.
- Records are stored when new or changed, compared on content without provenance; an
  unchanged record keeps its first-seen copy, so its source id and hash stay stable. VONAs
  are kept for `vona_window_h` (2 list pages on a cold start, then 1; known URLs and MAGMA
  ids skipped), VAAs for 30 h (asked from the last 24 h; Darwin's bulletin URLs never count
  as known). In REPLAY, VONAs and VAAs issued more than 5 min after the replay clock wait for
  it; LIVE keeps whatever a feed issued.
- ADS-B: the query points are the region's plus one per active volcano (`adsb_radius_nm`).
  Each poll first expires positions older than `MAX_CACHED_COPY_AGE_S`. On `AdsbPointsFailed`
  the points that answered are used and each failed point's previous snapshot stands in
  until it expires, and the feed reads STALE with the reason; a total failure reads ERROR.
  `live.adsb_at` (positions fresh) advances only when every point answered live.
- Per-volcano feeds (winds, frames, HSD) try every active volcano; one volcano's failure does
  not stop the rest. After a host times out or refuses a connection (judged from
  `HttpSource`'s `"<httpx exception name>: <detail>"` wording, or from a cached answer served
  after such a failure), the poll's remaining requests to that host are skipped. The feed is
  OK only when every volcano answered live, ERROR when none got through, and STALE otherwise,
  with the error `"<n> of <m> volcanoes failed (<name>: <reason>; ...); <k> skipped while
  <host> did not answer (<names>); last good copy served for <names>"`.
- TAF and METAR ICAOs (`taf_icaos`): the region's alternates, plus the 8 nearest alternates
  of each active volcano and the 5 nearest of each exposed flight, within the policy's
  `alternates.search_radius_nm`; region alternates are those `airports.alternate_ok`.
- Frames polls call `fetch_frames(..., nict=settings.nict_frames)`, so NICT true colour is
  fetched only with `TEPHRA_NICT_FRAMES=true`.

`tephra/scheduler.py`
```python
async def run_tick(runtime: "Runtime", *, reason: str) -> TickReport
async def run_adsb_pass(runtime: "Runtime") -> None
async def run_local_scheduler(runtime: "Runtime", stop: asyncio.Event) -> None
async def run_writer_watchdog(runtime: "Runtime") -> None     # every WRITER_WATCH_S (60 s): check_writer, quiet-tick stream end
```
`tephra/pipeline.py`
```python
@dataclass(eq=False)
class Runtime:
    settings: Settings; store: Store; bus: EventBus; source: Source; llm: LlmBackend
    catalogue: VolcanoCatalogue; airports: AirportCatalogue; routes: RouteTable; policy: OperatorPolicy
    mode: RunMode; replay_case: ReplayCase | None; auto_replay: bool
    ledger: QuotaLedger | None = None                             # create_runtime shares one with the Gemini backend; made when None
    policy_summary: PolicySummary; live: LiveData; lock: asyncio.Lock; tick_running: bool   # set by the runtime
    worker: AiWorker                                              # tephra.ai_worker: the model work, off the tick
    epoch: int                                                    # +1 at every picture reset (mode switch, replay loop)
    store_health: StoreHealth                                     # SystemState.store
    unsaved: set[tuple[Collection, str]]                          # feed records whose write failed
    situations; assessments; cones; exposed                      # the picture, by volcano id or flight id
    reroutes: dict[str, list[RerouteOption]]                      # flight id -> options computed at planning
    satellite: dict[str, SatelliteReading]                        # volcano id -> newest Satellite Reader reading
    crew_reports: dict[str, CrewReport]; crew: CrewPicture; fixes: FixHistory   # section 5.19
    instance_id: str                                              # uuid4 hex, made once per Runtime
    retired: bool                                                 # another instance ticked after this one
    adsb_passes: asyncio.Task[None] | None                        # the pending extra ADS-B passes
    last_tick_clock: float | None                                 # time.monotonic() when the last tick began
    last_tick: TickReport | None; last_tick_wall_at: datetime | None  # set by scheduler._tick_steps; wall clock, not restored
    @property
    def urgency_limits_min(self) -> tuple[int, int]              # (policy divert_within_min, hold_within_min)
    @property
    def quota(self) -> QuotaLedger                               # the day's model-call counts (agents.quota)
    @property
    def recorded_feeds(self) -> frozenset[FeedId] | None          # feeds the playing case holds; None when LIVE
    async def tick(self, *, reason: str = "scheduler") -> TickReport
    async def system_state(self) -> SystemState
    async def wall_snapshot(self) -> WallSnapshot
    async def switch_mode(self, mode: RunMode, *, auto: bool = False,
                          case: ReplayCase | None = None) -> None
    async def publish_budget(self) -> None                       # SSE `budget` (budget_view)
    async def budget_view(self) -> BudgetView                    # counts per model, pacing, the AI worker's queue
    def start_worker(self) -> None                               # create_runtime: the AI worker's loop (aclose stops it)
    answers: AiAnswers | None                                     # property: the kept model answers; None for the stub
    plan_answer_age: timedelta; duty_answer_age: timedelta        # properties: ai_answer_plan_min, ai_answer_duty_min
    async def answered(self, item: DutyItem) -> bool              # every answer the item needs is on hand (ASSESS, PLAN, SRA)
    async def coordinator_answered(self, items: Sequence[DutyItem]) -> bool   # the Duty Officer's for these items
    def coordinator_question(self, items: Sequence[DutyItem]) -> Question       # with this policy and duty_answer_age
    def known_routes(self) -> dict[str, FlightRoute]             # hex -> RouteTable.lookup of each airline target (every publish)
    def route_layer(self, known: Mapping[str, FlightRoute]) -> dict[str, Any]   # WallSnapshot.routes: exposed flights only
    async def add_verified_notice(self, vona: Vona) -> None      # a verified pasted notice joins live.vonas and the store
    # crew reports (section 5.19): a flag layer beside the cones
    async def restore_crew_reports(self) -> None                 # create_runtime: every stored report, both modes
    def crew_picture(self, at: datetime) -> CrewPicture         # pure: build_picture over the current mode
    async def update_crew(self, at: datetime, report: TickReport) -> None   # expiry audits, picture, traces
    def crew_flag(self, hex_id: str) -> CrewFlag | None
    def crew_view(self, report_id: str) -> CrewReportView | None
    def crew_fix(self, hex_id: str | None, callsign: str | None, at: datetime) -> FixLookup
    async def enter_crew_report(self, entry: CrewEntry, *, actor: str) -> CrewReportView   # raises CrewReportRefused
    async def withdraw_crew_report(self, report_id: str, *, reason: str, actor: str) -> CrewReportView
    async def run_recovery(self, at: datetime, report: TickReport) -> None   # queues RECOVER work when the closed airports change
    async def update_exposures(self, at: datetime, report: TickReport) -> None
    async def settle_drafts(self, at: datetime, report: TickReport) -> None  # draft retirement
    async def run_exposures(self, at: datetime, report: TickReport) -> None  # an ADS-B pass: the two above, then worker.wake("adsb")
    async def open_drafts(self) -> list[Advisory]                # current mode; raises DeskUnreachable on a store error
    def store_ok(self) -> None; def store_failed(self, exc: Exception, *, calls: Literal["reads", "writes"] = "writes") -> None
    async def restore_replay_choice(self) -> None                # create_runtime: resume the replay playing before a restart
    # what the Duty Officer's tools reach (tephra.duty._RuntimeExecutor); each takes `lock` only
    # to read and to commit, never while a model works, and commits nothing after a reset (epoch):
    async def assess_volcano(self, volcano_id: str, at: datetime, report: TickReport, *,
                             epoch: int | None = None) -> dict[str, Any]
    async def plan_flight_now(self, flight_id: str, drafts: Sequence[Advisory], at: datetime,
                              report: TickReport, *, epoch: int | None = None) -> dict[str, Any]
    def plan_due(self, flight: ExposedFlight, drafts: Sequence[Advisory], at: datetime) -> int | None
    def start_recovery(self, report: TickReport) -> dict[str, Any]   # queues a recovery job in the AI worker
    async def recover_queued(self, airports: Sequence[str]) -> None   # the AI worker's recovery job
    async def claim_writer(self) -> None                         # every tick but the startup one: write runtime/writer, end a retirement
    async def check_writer(self) -> bool                         # True when retired (reads runtime/writer)
    def end_streams(self) -> None                                # publish END_STREAMS: every open stream ends once
    def spawn(self, coroutine: Coroutine[Any, Any, None]) -> asyncio.Task[None]   # cancelled by aclose
    async def aclose(self) -> None
async def create_runtime(settings: Settings) -> Runtime     # loads the policy, then airports with its min_runway_m, then routes_apac.json (raises when missing)
```
The scheduler also calls the runtime's step methods (`maybe_switch_mode`,
`follow_replay_clock`, `refresh_active`, `analyse`, `update_exposures`, `run_recovery`,
`settle_drafts`, `publish`, `checkpoint`, ...) and ends every tick with `worker.wake("tick")`;
they are internal to core.

`tephra/ai_worker.py` (L6)
```python
MAX_ROUTINE_ITEMS = 3; RECOVERY_WORK_ID = "recover"
class AiWorker:
    paced: bool                                    # False only in the offline backtest
    def queue(self) -> list[AiWork]                # queued, running and WAITING work, most urgent first
    def wake(self, trigger: Literal["tick", "adsb"] = "tick") -> None
    def enqueue_recovery(self, airports: Iterable[str]) -> None
    def recovery_queued(self) -> bool
    def clear(self) -> None                        # a picture reset drops the queued work
    async def restore(self) -> None                # LIVE: the queue the last instance left (ai_work)
    async def run(self) -> None                    # the loop: on a wake, at the next slot, at least every 60 s
    async def work_once(self, report: TickReport) -> bool   # one pass; True when a job ran
    async def drain(self) -> TickReport            # passes until nothing more runs (tests, backtest)
```

`tephra/agents/answers.py` (L3; the model answers bullet below)
```python
Skill = Literal["plume_reader", "satellite_reader", "flight_planner", "drafter", "coordinator",
                "notice_reader", "messages", "ask", "handover", "sra"]
class Question(NamedTuple): skill: Skill; material: Mapping[str, Any]; max_age: timedelta | None = None
class AnswerScope(NamedTuple): mode: RunMode; case_id: str | None; epoch: int = 0   # epoch: not in the key
class AiAnswer(TephraModel):       # ai_answers/<key>: key, mode, case_id, build, skill, model_id,
                                   # fingerprint, answered_at (run clock), stored_at, expires_at
                                   # (wall clock), prompt_hash, payload (the skill's answer model)
    def age(self, now: datetime) -> timedelta       # abs(now - answered_at), on the run's clock
    def shown_at(self, now: datetime) -> datetime   # min(answered_at, now)
class AiAnswers:
    def __init__(self, store: Store, settings: Settings, *, scope: Callable[[], AnswerScope])
    scope: Callable[[], AnswerScope]                # the mode, case and epoch playing now
    counts: Counter[tuple[Skill, Outcome]]          # hit, miss, expired, rejected, kept, dropped, not_on_hand
    def reuse(self, question: Question) -> Reuse    # the question, put now
    async def recall(self, question, model_id, scope: AnswerScope | None = None) -> AiAnswer | None
    async def peek(self, question: Question, model_id: str) -> AiAnswer | None   # the same, uncounted
    def rejected(self, question, problems: list[str], scope: AnswerScope | None = None) -> None
    async def keep(self, question, model_id, payload, *, prompt_hash: str, answered_at: datetime,
                   scope: AnswerScope | None = None) -> None   # dropped when scope is not the one now
    async def sweep(self) -> int                    # at most every 10 min, at most SWEEP_PAGES pages
class Reuse:                                        # Reuse(book, question): scope taken when put
    book: AiAnswers; question: Question; scope: AnswerScope
    async def recall(self, model_id: str) -> AiAnswer | None
    async def recall_as(self, model_id: str, schema: type[T]) -> tuple[AiAnswer, T] | None
                                                    # a payload that no longer reads: rejected
    def rejected(self, problems: list[str]) -> None
    async def keep(self, model_id, payload, *, prompt_hash: str, answered_at: datetime) -> None
class NotOnHand(Exception): skill: Skill            # inside on_hand_only: no good answer, no model asked
def on_hand_only(enabled: bool = True) -> ContextManager[None]
def prompt_version(system: str) -> str             # a skill's instructions, in its material
```

Core rules:
- One tick at a time. A tick that finds another tick running returns
  `TickReport(skipped=True, notes=["busy: another tick is still running"])`; one that finds
  the runtime lock held by an extra ADS-B pass or a mode switch waits for it. Cloud Scheduler
  calls `POST /tasks/tick` every minute; with `TEPHRA_LOCAL_SCHEDULER=1` the local loop ticks
  every `tick_interval_s` counted from each tick's start (a tick that overruns is followed at
  once by the next). After a tick, extra ADS-B passes run every `cadence_adsb_s` timed from
  the tick's start, none within `ADSB_PASS_MARGIN_S` (10 s) of the next tick (one pass 30 s
  into a 60 s tick); a pass runs only while a volcano is active, ADS-B is not DISABLED (a
  replay case without aircraft) and the lock is free. A new tick cancels the passes the previous
  tick left pending (`Runtime.adsb_passes`).
- Writer fence (rollouts). `--max-instances 1` holds per revision: during a rollout the old
  revision's instance stays up while its event streams are open, but ticks reach only the
  serving revision. Every tick but the startup tick starts with `claim_writer`, which puts `runtime/writer`
  `{revision: K_REVISION or "local", instance: instance_id, at: wall-clock ISO}`. Every extra
  ADS-B pass and the lifespan's `run_writer_watchdog` (every 60 s) call `check_writer`: when
  the doc names another instance and its `at` is newer than this instance's own last claim,
  the runtime retires. It cancels its pending ADS-B passes, `run_adsb_pass` and `checkpoint`
  become no-ops (so `aclose` leaves `runtime/state` as the serving instance wrote it), it
  publishes `SseEvent.END_STREAMS` so every open stream ends and the browser reconnects to the
  serving revision, and it logs one warning. An instance that has not ticked yet never
  retires. A tick that reaches a retired instance (traffic moved back) ends the retirement.
  With Cloud Scheduler (`local_scheduler` false), `QUIET_TICKS` (3) x `tick_interval_s` with no
  tick ends the open streams once per quiet spell, so a tab left on an instance without ticks
  reconnects (a paused Scheduler costs each tab one reconnect). Advisory ids stay random.
- Publish only what changed. `publish` always sends `state`, `exposures`, `aircraft` and
  `budget`. `volcanoes`, `official`, `cones`, `reroutes`, `overlays`, `crew` and each `situation` card
  (per `volcano_id`) are sent only when their `sha256_json` digest differs from the last one
  sent (`Runtime._published`); a card whose volcano leaves the active list loses its digest,
  so it is sent again if the volcano comes back. Every mode switch (a replay loop included)
  clears the digests, so the Wall is republished whole. A page that opens or reconnects reads
  the whole picture from `/api/wall` or the bus history, so a skipped repeat carries nothing.
- Tick order: auto-replay check -> replay clock check -> due product feeds (SIGMET, VONA,
  VAACs) -> `find_active` -> due context feeds (ADS-B, TAF, METAR, winds, frames; HSD and
  the BTD only with `settings.science`) -> per active volcano: `select_records` ->
  `build_situation` (with the feed health) -> the plume gate (a read that matters is queued, the
  area held) -> `build_cone` -> `find_exposed` over every cone -> crew reports (`update_crew`:
  expiry audits, the crew picture and its flags; section 5.19) -> the recovery check (queues
  RECOVER work) -> draft retirement -> publish (Wall sections, then `budget`) -> checkpoint ->
  `worker.wake("tick")`. A tick makes no model call. An extra ADS-B pass runs exposure -> crew
  reports -> draft retirement -> `worker.wake("adsb")`. One volcano's failure keeps its previous
  picture and does not stop the others.
  Exposure, crew reports, the recovery check and draft retirement each run
  guarded: one that raises becomes a note (`<step> failed this tick (<error type>)`) and an
  error trace line, and publish and checkpoint still run. The extra ADS-B passes are scheduled
  even when a tick raises.
- AI worker (`tephra.ai_worker`). One background task per process (`create_runtime` starts it)
  runs the scheduled model work off the tick, most urgent first. A pass takes `lock` to read the
  open drafts and `tephra.duty.duty_worklist`, keeps the items not offered for `duty.rerun_min`,
  and starts one job: an urgent Duty Officer run over every mandatory item (lane `urgent`, never
  paced); else the more urgent of a routine Duty Officer run (lane `routine`: the most urgent
  routine items whose estimated calls fit every model's routine pacing now, at most
  `MAX_ROUTINE_ITEMS`, a plan only with or after its volcano's plume read, strictly in urgency
  order) and a queued recovery job (lane `routine`, urgency 3). Duty Officer runs go one at a
  time. A recovery job runs beside the worker (`Runtime.spawn`), so urgent runs still start
  while it runs; no routine Duty Officer run starts until it ends. A routine job, once started,
  runs with `use_lane("routine", admitted=True)`: its calls meet only the daily cap, so it is
  never cut off part-way by pacing. Routine work that does not fit is WAITING with the time of
  its next slot (`QuotaLedger.admission`), or with the reason when there is none (the budget
  store cannot be read); it is not offered to the Duty Officer (waiting costs no call), not
  dropped and never given to another model. When no routine work is admitted and some waits,
  the waiting items whose model answers are all on hand (`Runtime.answered`: an ASSESS item's
  plume read with the satellite reading it would be given, a PLAN item's plan and draft, an SRA
  item's narrative boxes; a RECOVER item never) and for which the Duty Officer's own answer for
  exactly those items is on hand (`Runtime.coordinator_answered`) run now, at most
  `MAX_ROUTINE_ITEMS`, even while the assistant is paused: they cost no call. Such a run is
  `on_hand_only` (and `use_lane("routine")` not admitted): every answer is checked again, and a
  step whose answer is missing or no longer passes asks no model but raises `NotOnHand`. The
  run then stores no Duty Officer run; what was done stays done, what was not is due as before
  (`assess_due`, the flight's plan marks and the region's SRA mark are restored), is not marked
  offered and waits for budget again (never AI UNAVAILABLE for want of a slot); the look ahead
  passes over those item ids for `duty.rerun_min`. Ask, voice, notices, messages, documents and a
  Desk-started recovery call the models directly, beside the worker; each call is counted all
  the same. A recovery job records the closed airports it planned for (the set of the moment,
  not the queued one), so a change while it waited does not queue a second run. Every item a run was given is marked offered,
  whatever came of it, so no pass repeats it. The queue (`AiWork`, section 5.5's `budget.py`) is
  kept in `ai_work` (written when it changes, never by a retired instance) and restored after a
  restart (LIVE; running work becomes QUEUED; a recovery job runs again on the picture of the
  moment). The worker does nothing before the runtime's first tick, nor on a retired instance.
  Model calls run outside `lock`: `assess_volcano` reads outside it and commits under it (a
  reading whose inputs changed meanwhile is used only where `_holds_while_pending` allows, else
  the read is queued again); `plan_flight_now` plans and drafts outside it and commits under it
  only while the flight is in the same cone of the same picture (`epoch`), else the result is
  traced and dropped and the flight is due again. The worker publishes the Wall after each
  delegation and `budget` after each job.
- Model answers (`tephra/agents/answers.py`, collection `ai_answers`). A model is asked only
  when something material changed, in LIVE and in REPLAY. Each skill states what is material to
  its question as a `Question(skill, material, max_age)`; an answer that passed the code's checks
  is kept as an `AiAnswer` under a key of `KEY_VERSION`, the mode (LIVE, or REPLAY and its
  case), the model id, the skill and the material's hash (every material includes the skill's
  prompt version; the build is not part of the key, so a deploy finds its kept answers). Material per skill, and the age limit on
  the run's clock (the replay clock in REPLAY):

  | Skill | Material | Age limit |
  |---|---|---|
  | Plume reader | the products by content (`input_hash`), the discrepancies by id and severity, the supporting evidence (the Satellite Reader's reading of the newest frames: source id and text hash) | `REASK_UNCHANGED` (3 h) |
  | Satellite reader | the volcano, the scans read (source ids and times) | none |
  | Flight planner | flight, cone id and `cone_version`, plume mode, allowed actions, policy version, urgency band (inside, within the divert limit, within the hold limit, later), level in 2,000 ft steps, open alternates | `ai_answer_plan_min` (60 min) |
  | Drafter | flight, cone id and version, policy version, action and its target (band, hold FL, alternate, reroute option) | `ai_answer_plan_min` |
  | Coordinator | the policy version and the work list's item kinds, subjects, mandatory flags and urgency buckets (not the digest: budget counts and other moving lines are left out) | `ai_answer_duty_min` (30 min); deferrals only within `duty.rerun_min` |
  | Notice reader | the normalised text | none |
  | Messages | the template spec (kind, status, jurisdiction, languages, placeholders: everything the model sees) | none |
  | Ask | the question (case, spacing and closing punctuation aside), the flight, each volcano's `input_hash` and cone id; on recall every tool the answer used must return the same results now | `ai_answer_ask_min` (10 min) |
  | Handover, SRA | every fact the model is given (the handover's `as_of` clock line aside) | none |

  `AiAnswers.recall(question, model_id)` returns the answer while it is within the age limit and
  the store's expiry; the skill then checks it again with the same validators as a fresh answer,
  against the input of the moment (numbers, ids and times must be in the current input, the
  action still allowed, the band still clear, the alternate still open, the reroute still OK,
  the Coordinator's delegations coming out as they did and its deferral reasons and brief
  passing their checks against this run's input, the digest and this run's tool results), and
  uses it only when it passes. A payload that no longer reads as the skill's answer model counts
  as rejected (`Reuse.recall_as`). A hit makes no
  model call and spends no budget. When it fails (`rejected`, logged with the problems), or there
  is none, the model is asked as usual (budget and pacing apply) and a new answer that passes is
  kept (a newer answer replaces the older); when the model cannot be asked the step reports AI
  UNAVAILABLE exactly as before, and the kept answer is never shown in its place (rule 9). A
  reused answer keeps the time the model gave it, `AiAnswer.shown_at(now) = min(answered_at,
  now)`: a plume read's and a satellite reading's `created_at`, a notice reading's `created_at`,
  an advisory's `drafted_at` and header `DRAFTED` line, a Duty Officer run's `decided_at` and
  `turns`, an Ask answer's `answered_at`, an SRA's and a handover's `narrative_at`. Code-built
  records around a reused text (an advisory's facts, a message, a document, a Duty Officer run's
  delegations) carry the time code built them. Nothing in the UI says an answer was reused; the trace says what was done and when
  ("Plume Reader accepted at 1830Z: ...", "PLAN ACCEPTED at 1830Z: ..."). Every hit, miss,
  expiry, rejection and keep is a log line (`event="ai_answer"`, `skill`, `outcome`, `mode`) and
  counted in `AiAnswers.counts`. The offline stub keeps nothing (`Runtime.answers` is None).
  A plume read first takes the satellite reading of the newest frames, as a fresh read does
  (`_with_satellite`: the held reading when current, else the Satellite Reader, which reuses its
  own kept reading of those frames), and the question and its re-check include that evidence. A
  Coordinator hit makes the kept delegations again through the same tools (each specialist asks
  its own question again); each must come out as it did then (`_outcome_of`: done or not, and
  the result's status, outcome, mode and action), its deferrals are made again through `defer`
  (whose reason is checked like the brief's figures) only within `duty.rerun_min` of the
  decision, and its brief goes through `validate_brief`; when any of that fails, the kept brief
  and deferrals are dropped (the delegations done stay, and the task text lists them) and the
  model finishes the run. A `Reuse` takes the scope (mode, case, picture epoch) when the question
  is put: it looks the answer up there, and an answer that comes back after a mode switch or a
  replay loop is dropped, not kept. `expires_at` (wall clock) is `stored_at + ai_answer_keep_h`
  (LIVE: no later than the age limit) or `stored_at + ai_answer_replay_keep_h` for a REPLAY
  answer (a replay asks the same question every loop); `AiAnswers.sweep` (at a checkpoint, at most every ten
  minutes and at most `SWEEP_PAGES` pages of `SWEEP_PAGE`) deletes expired answers, oldest expiry
  first, by a single-field order Firestore serves from its automatic index; in Firestore only
  `expires_at` is copied beside an answer's JSON text (`INDEXED_ONLY`). Answers read once are
  held in memory (up to 2,000), so a recurring question reads the store once.
- Store errors. The open drafts are read with documents that no longer validate skipped and
  logged. When they cannot be read (`DeskUnreachable`), the Duty Officer's dispatch and draft
  retirement are skipped for the tick (an unread list is never taken as empty, which would
  draft flights twice or retire drafts) with the note `Desk store unreachable: drafts not
  updated this tick` and one DESK trace line. `system_state` reports `draft_count` None when
  the read fails, never an older count. Every checked call updates `store_health`; the first
  failure of a run traces `Database writes failing: <error>` (or `reads`) as a warning, and
  the next successful write traces `Database working again`. Calls that are part of a
  transaction (`compare_and_set_advisory`, audit appends) get no `asyncio.timeout`: a
  cancelled commit has an unknown outcome.
  A `MODEL_FAILED` assessment writes an `AI_FAILED` audit entry.
- Plume quota gate. `situation.input_hash` covers only the SIGMET, VONA and VAA texts and the
  BTD indicator. An assessment with an unchanged `input_hash` is reused until `created_at +
  max(estimate.horizon_h, 3 h)` (`REASK_UNCHANGED`), so an unchanged input is asked again at
  most every 3 h. Otherwise `read_plume(..., call_model=True)` runs only when at least one
  holds: a CAUTION or WARNING discrepancy exists; no official layer is valid now but a VONA
  reports ash (HYPOTHESIS territory); an airline aircraft is within `adsb_radius_nm` of the
  vent. Such a read is not made in the gate: the volcano goes to `Runtime.assess_due` (an ASSESS
  work item for the Duty Officer) and, until it is dispatched, the cone is built on the last
  reading when it is within its horizon and its mode fits the official products now
  (`_holds_while_pending`), else on a `PENDING` assessment (official products only, never
  reused as current). The Duty Officer's `assess_volcanoes` (in the AI worker) then runs
  `read_plume(..., call_model=True)`, rebuilds the cone and that volcano's exposure. Otherwise a PLUME trace line is written (`"<volcano>: no CAUTION or WARNING
  discrepancy, no HYPOTHESIS case and no airline aircraft seen within <adsb_radius_nm> NM;
  cone from official products only"`) and `read_plume` runs with `call_model=False`
  (OFFICIAL_ONLY). This keeps TEPHRA near the ~20 calls/day free tier of 3.8 Flash; the
  model's daily budget in `agents/quota` is the hard stop.
- Satellite Reader gate. Within a dispatched plume read, just before `read_plume` is called with `call_model=True` for a volcano,
  `Runtime._with_satellite` reads the newest Dust RGB and B13 frames (from the store's blobs) with
  `read_satellite` unless `is_current(held reading, frames)` says the last reading was made from
  these frames. No Dust RGB frame means no reading and no call. The reading (read, `no_frames` or
  `ai_unavailable`) is kept in `Runtime.satellite`, stored in `sat_readings`, published as SSE
  `satellite`, and an unavailable one writes an `AI_FAILED` audit entry; a stored failure for the
  same frames blocks a retry until a new frame arrives. A current `read` reading becomes
  `Situation.supporting` for that call only (`plume_part(reading)` under its `SAT-` id). The
  satellite reading comes before the Plume Reader's kept answer is looked up: it is part of the
  question (model answers above). The look ahead uses `kept_reading` (a kept reading of the
  newest frames, checked, nothing asked).
- Advisory header facts. `_plan_and_draft` passes `feed_health=runtime.live.health` to
  `draft_advisory`, and `replay_case=runtime.replay_case` when the mode is REPLAY.
- Reroutes. `_plan_and_draft` passes `routes=runtime.routes` and the situation to
  `build_planner_context`, stores every `RerouteOption` of the context in `reroutes` (each time
  the flight is planned) and keeps them in `Runtime.reroutes` for the Wall. Options are dropped
  when the flight leaves the exposed set or its cone changes (`_keep_current_reroutes`); a
  restart restores them from the store. The Wall's `reroutes` section is built by
  `_reroute_features`: per option with a path, a `LineString` (`feature: "path"`) with
  `RerouteFeatureProps` and one `Point` per turn point (`feature: "waypoint"`, `label` its ICAO
  coordinate), the path carrying `waypoint_labels`. An option is the route as planned, not
  recomputed each tick.
- Automatic recovery. After the exposure step, `run_recovery` computes the closures of the
  airports of the RFA schedule (`recovery.network.network_closures`, from `live.tafs`, `live.metars`,
  the cones and the official layers) and compares the set of closed ICAOs with the last one
  (kept in the bookkeeping as `closed_airports`). A change to a non-empty set is queued as
  `Runtime.recovery_due` (a RECOVER work item); when the Duty Officer dispatches it,
  `start_recovery` queues a recovery job in the AI worker, which runs one `recommend_recovery`
  on the closures of the moment (`recover_queued`, under the recovery lock that the Desk's run
  button shares; a Desk run in progress or a queued job covers the change), and `submit_plan`
  stores the draft and publishes SSE `recovery`. A change
  to the empty set is recorded and makes no plan. A deferred recovery stays queued and is
  offered again after `duty.rerun_min`. `TEPHRA_RECOVERY_AUTO=false` turns it off. The schedule is read once a day.
- Budget. `publish`, the AI worker and the satellite and recovery steps publish SSE `budget`
  (`Runtime.budget_view`: the ledger's counts per model and the worker's queue); `GET
  /api/budget` serves the same.
- Plume Reader images: the stored frame PNGs and the BTD PNG. Frames with product
  `TRUE_COLOR` (NICT, fetched only with `TEPHRA_NICT_FRAMES=true`) are never sent to the
  model (research/05); the Wall still shows them.
- Planning. A flight is planned once per cone and urgency bucket. The buckets are inside
  now, entry within the policy's `divert_within_min` (15), within `hold_within_min` (30), and
  later: the same limits the rules apply (`urgency_limits_min`). A flight is planned again for a
  new cone or a more urgent bucket; a less urgent bucket is not planned again, and an open draft
  for the cone counts as planned at its own urgency. What the planner is asked is the material
  question (section 5.7: band, urgency, level step, open alternates, usable reroutes, not the
  cone id), so a cone reissued with the same band is answered from the kept answer, not the
  model. Planning by that key instead of the cone was measured on the Krakatau recording at
  1.75 times the planner calls (docs/evals/call-counts.json) and is not used. The new draft carries its bucket
  (`urgency_bucket`) and is submitted with the flight's open drafts drafted at a less urgent
  bucket as `replacing`; only once it is stored are those superseded (`superseded_by` set,
  reason `ENTRY NOW IN N MIN` or `INSIDE THE CONE NOW`), so a refused or failed submit leaves
  the flight its earlier card. A flight is marked planned only when planning finishes (an
  `AiFailure` recorded for the Desk counts as finished). Planning that raises leaves no mark:
  the flight is planned again `PLAN_RETRY_MIN` (1, then 5, then every 15) minutes later for
  the same cone and bucket, or at once for a new cone or a more urgent bucket.
- Exposure and retirement. When every ADS-B snapshot is a stale last-good copy, the step plans
  nothing and retires nothing: it keeps the previous exposures (dropping those whose cone is
  gone) and notes `ADS-B is stale: exposures and open drafts kept until positions refresh`.
  A draft whose flight is no longer exposed is superseded only after a grace time from the
  policy's `drafts` block, counted on fresh positions only: a flight seen in the ADS-B picture
  but outside every cone after `unexposed_retire_min` (3; `NO LONGER EXPOSED IF TRACK AND LEVEL
  ARE HELD`, or `VOLCANO NO LONGER ACTIVE` when its volcano is no longer active), a flight
  missing from the picture after `position_lost_retire_min` (10; `POSITION LOST FOR N MIN`,
  never "no longer exposed": a dropped position says nothing about the ash). Nothing is
  retired, and both grace times restart, while every snapshot is stale or `live.adsb_at` is
  older than the ADS-B stale age. Planning, escalation and retirement
  consider only open drafts whose `replay` flag matches the current mode.
- Trace lines (`TraceEvent.new`) for each step go to `bus.publish(SseEvent.TRACE, event)`;
  agents receive `trace=` callbacks that do the same. In REPLAY every trace line carries
  `detail.replay = true`. DISCREPANCY lines are `warn` for CAUTION and WARNING and `info` for
  INFO.
- Live state (aircraft, exposures, the Wall) is held in memory only and rebuilds on the first
  tick after a restart. The checkpoint, at most every 5 minutes, writes `runtime/state` first,
  then each feed's state when its status, error or record count changed, then the feed
  records still in `unsaved`; each write is tried on its own. Durable records (feed products on change,
  assessments, situations and cones on change, plans, advisories, audit, outbound) are
  written when they change. A situation's clock-only fields (`as_of`, each discrepancy's
  `magnitude` and `summary`) and a cone's `created_at` do not count as a change. Target under
  10,000 Firestore writes a day (free tier is 20,000).
- Crew reports are durable (`crew_reports`, written on entry, withdrawal and expiry) and are
  restored in both modes by `restore_crew_reports` before anything else; the fix history is
  memory only and starts empty after a restart or a mode switch (section 5.19).
- AI failures (`desk.failures`). A flight has at most one open failure on the Desk.
  `Runtime.track_failure(failure)` records one (the planner's and the drafter's through
  `_record_failure`, the Duty Officer's undone flights through `tephra.duty`) and keeps it in
  `Runtime.open_failures` (flight id -> failure); a newer failure for the same flight closes the
  older one. Code closes a flight's open failure, audited as `AI_FAILURE_CLOSED` under the system
  actor, when it no longer stands: `NEWER_FAILURE`; `DRAFT_WAITING` when a draft for the flight is
  stored; and, with the draft retirement rules and grace times (`_retire_gone`), `NO LONGER
  EXPOSED IF TRACK AND LEVEL ARE HELD`, `VOLCANO NO LONGER ACTIVE` or `POSITION LOST FOR N MIN`.
  `record_failure(store, bus, failure, *, run_since=None)` stamps `recorded_wall_at` and returns
  None while the same flight, cone and stage already stands (open or handled, in this run); one
  closed by code, or recorded in an earlier replay run, is replaced (an open one of an earlier
  run is closed first with `REPLAY_RUN_ENDED`). `close_failure(store, bus, failure_id, *, reason)`
  closes one only while it is still open (one transaction; None otherwise), and
  `mark_handled` returns a failure code already closed unchanged, with nobody recorded as
  handling it. `list_failures(store, *, open_only, replay, run_since, limit)` reads the newest
  `LIST_WINDOW` (200) records by `recorded_wall_at` (records without it sort last; Firestore
  leaves them out) and keeps, with `run_since`, only the replay run that started then.
  `Runtime.replay_run_since` is that wall-clock start (None when live). Once per picture (a
  start, a mode switch, a loop) the first `settle_drafts` follows the failures back from the
  store (`_follow_failures`): in REPLAY every open REPLAY draft is superseded first with
  `DRAFT_RUN_ENDED` ("THE REPLAY RUN IT WAS DRAFTED IN HAS ENDED", audited `SUPERSEDED` under
  the system actor, one DESK trace line each): the AI works only after this first pass, so such a
  draft was made in an earlier run and its picture has ended. An earlier replay run's open
  failures close with `REPLAY_RUN_ENDED`, this mode's are followed, one per flight. A picture reset also clears
  `Runtime.duty`, so the Wall shows no Duty Officer run of an earlier picture.
- Restart. A LIVE runtime restores from the store the feed health (except feeds the settings
  switch off and states saved during a replay), the SIGMETs still valid, the VONAs within
  `vona_window_h`, the VAAs of the last 30 h, and the bookkeeping (planned marks, the latest
  assessments, quiet ticks, the closed-airport set), the newest satellite reading per volcano
  and the stored reroutes, so an unchanged input does not spend a call after a restart. A
  REPLAY always starts from its recording. The last tick is not restored: the Wall's waiting
  note stands until this process has ticked. With `TEPHRA_MODE=LIVE`,
  `restore_replay_choice` first reads `runtime/state`: a REPLAY chosen from the Desk
  (`auto_replay` false) resumes on the same case, and an automatic one resumes while
  `TEPHRA_AUTO_REPLAY` is still on and the live SIGMET probe finds no activity; either starts
  again from the case's start (`replay_start`) and writes one `MODE_SWITCH` audit entry with
  the note `restored after restart`. A case that can no longer be loaded starts LIVE with a
  SYSTEM trace line saying why. With `TEPHRA_MODE=REPLAY` the setting wins. Every mode switch
  writes `runtime/state` at once, so the choice survives a restart before the next checkpoint.
- REPLAY: `create_runtime` (with `TEPHRA_MODE=REPLAY`) and `switch_mode` call
  `start_replay_clock(case, speed=settings.replay_speed, begin=settings.replay_start)` and
  use `ReplaySource`. With no `replay_start` the clock starts, and loops back, at
  `first_aircraft_at(case)` (anak-krakatau-20260905: 5 Sep 10:01Z, not the 06:00Z recording
  start), so a replay never opens on hours with no aircraft data. With `replay_end` set, the case named by `replay_case` plays
  `ReplayClock(replay_start, replay_end, speed, loop=True)` instead, after checking
  `recorded_from <= replay_start < replay_end <= recorded_to` (a `ValueError` naming the case
  window otherwise, so `create_runtime` fails at startup and a switch fails without changing
  mode); `Runtime.replay_window` holds the window and `system_state` reports it as
  `ReplayInfo.window_from`/`window_to`. Any other case chosen at the Desk plays its whole
  recording from its start. A replay case's missing feeds read DISABLED with `NOT_RECORDED_NOTE` and
  are never polled (`Runtime.recorded_feeds`). When the looping replay clock goes back to the
  start, the picture starts afresh (every feed due again), with a note and a SYSTEM trace
  line.
- `switch_mode`: REPLAY plays `case`, else the case playing, else `TEPHRA_REPLAY_CASE` or the
  newest case. Asking for the mode and case already running changes nothing; another case
  restarts the replay on it. The
  replay clock starts (and checks the case) before the source is swapped, so a switch that
  fails leaves LIVE polling live. `replay_case` is assigned inside the runtime lock, only
  after the switch succeeds; `POST /api/mode` passes the case instead of setting
  `runtime.replay_case`. Every switch starts a fresh picture, writes a `MODE_SWITCH` audit
  entry and a SYSTEM trace line, and publishes the Wall at once.
- Auto-replay: with `settings.auto_replay`, after `auto_replay_after_ticks` consecutive LIVE
  ticks with no active volcano inside `settings.region_preset.bbox` and no exposed flight,
  switch to REPLAY (`ReplayInfo.auto=True`, audit `MODE_SWITCH`); while auto-replaying, each
  tick also polls the live SIGMET feed only (through the live `HttpSource` it kept) and
  switches back to LIVE when a VA SIGMET for a catalogue volcano inside the region's bbox is
  valid at wall-clock time (`SystemClock().now()`, not the replay clock). Activity at a
  volcano outside the region counts for neither. A REPLAY a person chose (`auto=False`) is
  never left automatically. `HttpSource` always stamps `fetched_at` with wall-clock time.
- `wall_snapshot()` builds `WallSnapshot` (section 8.3) from memory. Situation cards: for
  each active volcano, exactly three `SourceCard`s in the order SIGMET, VONA, VAA (the
  latest of each; others listed in `extra_source_ids`; a missing kind gets `missing=True`
  and a code-written `missing_note`), `evidence` from `reconcile.evidence_state`,
  code-written `display_fields` (band, movement, ash observed, colour code, validity), and
  `discrepancy_ids` of the discrepancies that cite that card's source. A missing card's
  `missing_reason` (`NONE_SEEN`, `NOT_READ`, `NOT_RECORDED` or `FEED_DOWN`; default
  `NONE_SEEN`) and note follow the health of the feed that carries the kind
  (`FeedId.SIGMET`, `FeedId.VONA`, or the volcano's VAAC feed), so a feed TEPHRA did not
  read never reads as "none issued":
  - `DISABLED` with `VONA_OFF_NOTE`: `NOT_READ`, `"Not read: live MAGMA polling is off
    (robots.txt disallows crawling); replays play recorded VONAs"`. Any other `DISABLED`:
    `NOT_READ`, `"Not read: <last_error>"`.
  - `DISABLED` with `NOT_RECORDED_NOTE`: `NOT_RECORDED`, `"Not in this replay: no VONA
    archive was recorded"` (SIGMET, VONA or VAA).
  - `ERROR` or `NEVER` (a situation's volcano is always active): `FEED_DOWN`, `"SIGMET feed
    not answering since 0412Z: none seen"`, or `"... not answering yet: none seen"` with no
    success yet.
  - Otherwise `NONE_SEEN`: `"No valid VA SIGMET"`, `"No VONA in the last 24 h"`,
    `"No VAA since VONA 2221Z (47 min)"` or `"No VAA in the last 24 h"`.

### 5.8 api

`tephra/main.py`: `app = create_app(settings)` (built at import, with JSON logging set up by
`configure_logging`) and `def run() -> None`: uvicorn on `0.0.0.0:{settings.port}` with
`proxy_headers=True` and `forwarded_allow_ips="*"` (Cloud Run's front end is the only peer and
sets `X-Forwarded-Proto`, so desk cookies are marked Secure), no uvicorn access log, log
level from settings, and a 5 s graceful shutdown (SSE streams never end by themselves).
Console script `tephra`.

`tephra/api/server.py`
```python
CONTENT_SECURITY_POLICY: Final = "; ".join([...])   # the policy in section 8.1
WEB_DIR: Final = Path(__file__).resolve().parent.parent / "web"
type RuntimeFactory = Callable[[Settings], Awaitable[Runtime]]
def create_app(settings: Settings | None = None, *, runtime_factory: RuntimeFactory | None = None) -> FastAPI
def configure_logging(level: str) -> None    # one JSON object per line on stdout (Cloud Logging shape)
```
The lifespan builds the replay catalogue for `GET /api/replays` (section 8.2), creates the
runtime with `runtime_factory` (default `create_runtime`; tests swap it), starts
`run_writer_watchdog`, and starts `run_local_scheduler` when `settings.local_scheduler`, and
otherwise runs one `tick(reason="startup")` in the background, so the picture does not wait up
to a minute for Cloud Scheduler (an overlapping scheduler tick skips itself; the startup tick
does not claim `runtime/writer`, since it may run before traffic reaches the revision). On
shutdown it cancels the watchdog, stops the loop or that tick (waiting up to 10 s) and closes
the runtime. Until the runtime exists, routes that need
it answer 503 `starting`. `create_app` mounts the feature routers (`routes_ask`,
`routes_notices`, `routes_recovery`, `routes_comms`, `routes_regdocs`, `routes_backtest`,
`routes_duty`, `routes_crew`) under
`/api` through `_include_feature_routers`, which imports them at call time. A pure ASGI
middleware adds the security headers (section 8.1, with `microphone=(self)` on `/desk` alone) to
every response, caps request bodies whether or not they carry `Content-Length` (413
`too_large`): 16 KiB, 32 KiB for `POST /api/desk/notices`, `settings.max_upload_bytes` for
`POST /api/desk/ask/voice`; and writes one access-log line per request. The OpenAPI document is at
`/api/openapi.json`; there is no docs UI. Routes and shapes: section 8.

`tephra/api/auth.py`
```python
COOKIE_NAME: Final = "tephra_desk"
TASK_HEADER: Final = "X-Tephra-Task-Token"
CSRF_HEADER: Final = "X-Tephra-Desk"
def desk_enabled(settings: Settings) -> bool                     # PIN and session secret both set and not blank
def sign_session(name: str, settings: Settings, *, at: datetime) -> tuple[str, datetime]
def verify_session(token: str, settings: Settings, *, at: datetime) -> SessionInfo | None
def client_key(request: Request) -> str                          # what the login throttle counts against
async def require_desk_enabled(request: Request) -> None         # 503 desk_disabled
async def require_desk(request: Request) -> SessionInfo          # 503 desk_disabled, else 401 without a valid cookie
async def require_csrf(request: Request) -> None                 # 403 for a request a cross-site page could send
async def require_task_token(request: Request) -> None           # 403 unless header matches settings.task_token
class LoginThrottle:                                             # 5 failures per client key per 10 min -> 429
    def __init__(self, *, max_failures: int = 5, window_s: float = 600.0,
                 max_clients: int = 10_000, clock: Callable[[], float] = time.monotonic) -> None
```
Cookie value `b64url(json{"n": name, "exp": epoch_s, "sid": hex}).b64url(hmac_sha256)` keyed
by `settings.session_secret`; `HttpOnly; SameSite=Strict; Path=/; Max-Age=ttl`; `Secure`
when the request is https (or `X-Forwarded-Proto: https`). Sessions expire on wall-clock
time, not the replay clock. A blank secret signs nothing (`sign_session` raises) and verifies
nothing (`verify_session` returns None); a blank task token refuses every tick. PIN and token
compared with `hmac.compare_digest`. Audit `LOGIN_OK`/`LOGIN_FAILED` (actor `desk:<name>`,
never the PIN). `require_csrf` refuses `Sec-Fetch-Site: cross-site`, an `Origin` whose host
is not the request's `Host`, and any request with neither a JSON body (`Content-Type:
application/json`) nor `X-Tephra-Desk: 1`; either one forces a CORS preflight, which TEPHRA
never answers. `LoginThrottle` counts failures per `client_key`: the rightmost
`X-Forwarded-For` entry (the one Cloud Run's front end appends), falling back to the peer
address when the header is absent. `main.run` trusts every proxy only for
`X-Forwarded-Proto`; uvicorn then reports the spoofable leftmost entry as `request.client`,
which nothing uses for security. This holds only while nothing, such as an external
Application Load Balancer, sits in front of Cloud Run appending its own address.

`tephra/api/sse.py`
```python
RETRY_MS: Final = 3000
def event_stream(bus: EventBus, *, heartbeat_s: float = 15.0, last_event_id: int | None = None,
                 mode: Callable[[], RunMode] = lambda: RunMode.LIVE) -> AsyncGenerator[str, None]
def format_event(event: Event) -> str      # "id: {id}\nevent: {name}\ndata: {json}\n\n"
def missed_events(bus: EventBus, after_id: int) -> list[Event]   # history events with a larger id, oldest first
def parse_last_event_id(header: str | None) -> int | None
class StreamSlots:                         # open streams, capped at settings.max_event_streams
    def __init__(self, limit: int) -> None
    def acquire(self) -> bool
    def release(self) -> None
class EventStreamResponse(StreamingResponse):
    def __init__(self, stream: AsyncGenerator[str, None], slots: StreamSlots) -> None
```
`event_stream` is an async generator. It subscribes before sending anything, starts with
`retry: 3000\n\n`, replays `missed_events` after `last_event_id` (every event name but
`heartbeat`, from the bus history of 200 events per name), then sends live events and a
`heartbeat` event (`{"now": iso, "mode": mode()}`, no id) when idle for `heartbeat_s`. A
client whose 256-event queue has dropped events is disconnected before anything newer is
sent; the browser reconnects with `Last-Event-ID`. NaN and infinities are sent as null.
`EventStreamResponse` (`text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering:
no`) releases its slot and closes the generator however the response ends (normal end,
error, or client gone).

### 5.9 web-wall and web-desk

Plain HTML/CSS/JS, no build step, no frameworks. MapLibre GL JS from
`https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js` and `.../maplibre-gl.css`;
basemap `https://tiles.openfreemap.org/styles/dark`. No Google Maps, no inline scripts or
inline event handlers (CSP in section 8.1), no `innerHTML` with feed or model text (use
`textContent`). Both pages reopen a closed event stream themselves and then reload what
they show (section 8.4).

Wall (`/`, `index.html` + `wall.js` + `wall.css`): fetch `GET /api/wall`, then subscribe to
`GET /api/events` and replace sections per section 8.4. Layers: volcanoes by colour code;
official polygons with expiry countdown (`valid_to`); cone (dashed outline, label =
`label`); optional BTD image source using `corners`; aircraft arrows rotated by
`track_deg`, amber when `exposed`, label with minutes to entry; exposure paths. Region
presets from `state.regions` (fly-to). Right rail: the three source cards side by side with
raw text, evidence state and discrepancy badges; the live trace; the advisory list with
status. Top bar: LIVE/REPLAY badge (`state.mode`, `state.replay.banner` as a permanent
banner), LLM label (`state.llm.label`, "AI-drafted" marking), feed health ages, and the
`state.disclaimer` line, with a short "Policy A · illustrative" button (`state.policy`; on
phones it is hidden and the About dialog carries it, so the credit line keeps its room) that
opens `GET /api/policy` as the Operator policy dialog (`wall/policy.js`: a one-line summary
and the key values, then every value under a name a person reads, with its unit, its reason
and its sources, and the policy's metadata; docs/UI-DESIGN.md 7.18). "AI at work"
(`wall/board.js`, `wall/board-view.js`; docs/UI-DESIGN.md 7.21) draws the Duty Officer, its
helpers and the Desk from `/api/wall`, `/api/budget`, `/api/recovery`, `/api/docs` and the
stream, and opens from the AI chip, the A key or `/#ai-at-work`. The AI's one state in words
(`aiStateOf()` in `wall/x-parts.js`, shared with the Desk and the board; docs/UI-AI-QUIET.md)
comes from `state.llm`, `/api/budget`, the trace, the newest Duty Officer run and airport plan.
Readable at 1280x720, keyboard accessible (focusable controls,
visible focus, no hover-only information). Attribution: OpenFreeMap/OpenStreetMap,
"Aircraft: adsb.lol (ODbL 1.0)", "Himawari-9 data: JMA via NOAA".

Desk (`/desk`, `desk.html` + `desk.js` + `desk.css`): PIN + name login (`POST
/api/desk/login`; every desk request sends `X-Tephra-Desk: 1`), list of DRAFT cards (`GET
/api/desk/advisories?status=DRAFT`) showing proxy flight and callsign, action, minutes to
entry (and draft age from `created_at`), fuel line, body, sources with issue times and short
hashes, cone mode and confidence, the operator policy the draft was made under (`policy_id`,
`policy_version`); Approve / Edit (textarea, 400-char counter) / Reject
(reason required). Send `version`; on 409 show the current version and let the dispatcher
re-decide. Refresh on `advisory` SSE events. Works at 375 px width, tap targets >= 44 px.
Flights to handle by hand (`desk/failures.js`) come from `GET /api/desk/ai-failures` and the
`ai_failure` event (a record with `handled_at` or `closed_at` leaves the list); the header's AI
status (`desk/budget.js`) from `/api/state` and `/api/budget` (docs/UI-DESIGN.md 10.16).
From 1280 px the map of the flight under review (`desk/map.js`, docs/UI-DESIGN.md 10.18) draws the
`GET /api/wall` snapshot the Desk already reads (cones, exposures, aircraft, volcanoes) and the
reroute the draft under review proposes (`Advisory.reroute.path`),
follows the `cones` and `aircraft` events and reads the snapshot again every minute; it is
read-only. The night basemap (`wall/basemap.js`) and the map controls (`mapui.css`) are shared by
the Wall, the flow board and the Desk.

Crew reports of ash (section 5.19; the screens are docs/UI-DESIGN.md 5.7, 7.20 and 10.15): the
Wall draws `WallSnapshot.crew` (replaced whole by the `crew` event) beneath the official areas,
with the story lines, Details › Crew reports of ash and the flag in This flight; it is
read-only. The Desk (`tephra/web/desk/crew.js`) enters reports (`GET /api/desk/crew-reports/fix`,
then `POST /api/desk/crew-reports`), withdraws them, starts the message to the weather office
and the VAAC (`POST /api/desk/crew-reports/{id}/message`), marks flagged drafts from `CrewPicture.flags`, and sends the
dispatcher's `reason` with approve and edit for a flagged CONTINUE or MONITOR (422
`reason_required` opens the reason box).

### 5.10 ops-evals

Files are listed in section 1. Requirements: `Dockerfile` (python:3.12-slim, uv 0.11.17,
`uv sync --frozen --no-dev --extra gcp` from the required `uv.lock`, plus `--extra science`
with `--build-arg SCIENCE=1`; copies `tephra/` and `data/`; `ENV TEPHRA_DATA_DIR=/app/data
TEPHRA_CACHE_DIR=/tmp/tephra-cache`; non-root user; `CMD ["tephra"]`); deploy scripts that
take the project (`TEPHRA_PROJECT`) and region (`TEPHRA_GCP_REGION`) from the environment and
never hard-code an account (they are run later by the user from a personal-account context,
never by an agent on this machine); `deploy/_common.sh` refuses the `default` gcloud
configuration and any credential override (access-token file, credential-file override,
impersonation). `deploy/cloudrun.sh` builds with Cloud Build (`deploy/cloudbuild.yaml`),
creates the runtime service account `tephra-run` with exactly the three roles in
`docs/ARCHITECTURE.md` section 4, and deploys Cloud Run with `--service-account`,
`--min-instances` and CPU throttling from `TEPHRA_HOSTING` (below), `--max-instances=1`,
1 CPU, 1 GiB (2 GiB with science) and `--timeout 3600`; secrets `GEMINI_API_KEY`,
`TEPHRA_DESK_PIN`, `TEPHRA_TASK_TOKEN`, `TEPHRA_SESSION_SECRET` from Secret Manager
(`deploy/secrets.sh` refuses a session secret or task token under 32 characters, and a token
with characters a header cannot carry); one Cloud Scheduler job `POST /tasks/tick` every
minute (attempt deadline 120 s) with header `X-Tephra-Task-Token`; Firestore native mode; a
US-region bucket for blobs (free tier). `.env.example` lists every setting by its env name,
with optional secrets commented out. `scripts/record_replay.py` writes
`data/replay/<case_id>/`: `live` records the real pollers through `RecordingSource`;
`noaaport` and `backfill` rebuild a past window from archives (aviationweather.gov `date=`
SIGMET snapshots, NOAAPort bulletins, the census's MAGMA list pages, and the TAF, METAR,
winds and ADS-B history the pollers' URLs need); `probe` replays chosen times. Nothing from
ftp.bom.gov.au goes into a case, and MAGMA is never fetched except by `live --with-vona`.
Plume evals score bearing error with `tephra.geo.units.bearing_diff_deg` against the VAA
polygon centroid (no IoU; research/10 section 5); Arm I's wind is the VAA's `WIND FL180`
group, else Open-Meteo's 500 hPa (FL180) wind at the vent. CI (manual `workflow_dispatch`
only) runs `ruff check`, `ruff format --check`, and `pytest` with `TEPHRA_LLM=stub`.

Deploys are gated and traceable (`deploy/README.md`). Every push to `main` that changes a deployable
file (the workflow's `paths:` list: what the image is built from, `deploy/`,
`scripts/live_smoke.sh`, `tests/test_policy.py`, the workflow; read by `deploy/deploy_paths.py`)
runs `.github/workflows/deploy.yml`,
which runs `cloudrun.sh` in CI mode (`TEPHRA_DEPLOY_CI=true` with `GITHUB_ACTIONS=true`) as the
`tephra-deployer` service account through workload identity federation set up once by
`deploy/github_deploy_setup.sh`; one deploy at a time, in push order. `cloudrun.sh` refuses a
dirty tree or a `HEAD` not on `origin/main` (in CI: not the pushed commit; when `main` has moved on it stands down only if a later push
changed deployable files, and `deploy/report_interrupted.sh` reports a step stopped part-way), tags the image `<12-char commit>-<UTC time>` and builds it with
`_BUILD_SHA` (`--build-arg BUILD_SHA`); `.gcloudignore` uploads only what the Dockerfile
copies. `TEPHRA_HOSTING` is `always-on` (default: `--min-instances 1`,
`--no-cpu-throttling`, Scheduler ticks) or `on-demand` (`--min-instances 0`,
`--cpu-throttling`, `TEPHRA_LOCAL_SCHEDULER=true`; untested). It forwards `TEPHRA_MODE`,
`TEPHRA_REPLAY_CASE`, `TEPHRA_REPLAY_START`, `TEPHRA_REPLAY_END`, `TEPHRA_REPLAY_SPEED`,
`TEPHRA_AUTO_REPLAY`, `TEPHRA_REGION`, `TEPHRA_MODEL`, `TEPHRA_MODEL_LITE`, `TEPHRA_MODEL_DAILY_BUDGET` and
`TEPHRA_MODEL_LITE_DAILY_BUDGET` when set. A new revision is deployed `--no-traffic --tag
candidate`, smoke-tested read-only, then given 100% and smoke-tested on the main URL; a
failure leaves traffic alone and prints the rollback to the previous revision. It applies
`deploy/ar-cleanup.json` (keep `keep-*` tags, keep the 5 newest, delete the rest after 30
days) and adds `TEPHRA_KEEP_TAG` to the image when set. `scripts/live_smoke.sh <url>
[--read-only] [--watch MINUTES]` (python3 standard library, public endpoints, no secrets)
retries a 429 or 503 for up to 90 s (noted on the line; a 429/503 after the service has
answered in the run fails the check; no retries in `--watch`) and checks `/health`, `/api/state` (tick age under 3 x `TICK_INTERVAL_S`, policy hash against
`/api/policy` and the newest pin in `tests/test_policy.py`, `EXPECT_SHA`, `EXPECT_MODE`,
`EXPECT_CASE`, store health when exposed), `/` and `/desk` with CSP and their `/static/`
files, a first SSE event within 30 s, and a refused token-less `POST /tasks/tick`; it exits
non-zero on any failure. `--read-only` skips the two tick checks.

### 5.11 reroute

`tephra/geo/reroute.py`
```python
def plan_reroutes(flight: ExposedFlight, cone: HazardCone, situation: Situation | None,
                  route: FlightRoute | None, policy: OperatorPolicy, *,
                  dest_position: tuple[float, float] | None = None) -> list[RerouteOption]
def clear_cache() -> None
def coordinate_text(lat: float, lon: float) -> str        # '0812S11245E'
```
`tephra/geo/fuel.py`: `reroute_line(category, extra_min, extra_nm) -> FuelLine`.
`tephra/feeds/routes.py`
```python
ROUTES_FILE: Final = "routes_apac.json"
def load_routes(data_dir: Path) -> RouteTable             # raises when the file is missing: no empty default
class RouteTable:
    def lookup(self, aircraft, airports: AirportCatalogue, policy: OperatorPolicy) -> FlightRoute | None
    def position(self, icao: str, airports: AirportCatalogue) -> tuple[float, float] | None
    def chain(self, callsign: str | None) -> tuple[str, ...] | None
def great_circle(lat1, lon1, lat2, lon2) -> list[Position]   # (lon, lat), one point about every 40 NM
def route_features(legs: Mapping[tuple[str, str], Iterable[str]], table: RouteTable,
                   airports: AirportCatalogue) -> dict[str, Any]   # FeatureCollection, RouteFeatureProps
```
Both reroute kinds are returned for every exposed flight, each with a `RerouteStatus`: `OK`,
`NOT_EXPOSED` (level outside the hazard band), `START_INSIDE`, `DEST_INSIDE`, `NO_DEST` (no
published route: the direct option is never guessed), `NO_ROUTE`, `TOO_LONG`, `NO_BENEFIT`.
Algorithm: a local azimuthal equidistant plane (hand-written, no pyproj); the obstacle is the
cone simplified by `reroute.simplify_nm` and buffered by `reroute.buffer_nm + simplify_nm`, then
**the convex hull of each connected piece** (hulls that touch merge and are hulled again), so it
is always a superset of the hazard and has far fewer vertices and turns; nodes are the start,
the hull's convex vertices and the end candidates (`REJOIN_TRACK`: points on the present track
beyond the obstacle every `rejoin_step_nm`, the first reachable and cheapest ending the route;
`DIRECT_DEST`: the destination); edges are legs that do not enter the obstacle; Dijkstra on
minutes with the ground speed from the wind at the flight level (`NO WIND DATA: TIMED AT <n> KT`
when the situation has none). At most `max_waypoints_count` turn points (one retry with twice
the simplification, else `NO_ROUTE`), no turn above `max_turn_deg`, turn points rounded to one
arc-minute and re-checked against the buffer, `extra_min` between `min_extra_min` and
`max_extra_min`. The obstacle graph is cached per `(cone id, band)`; `compute_ms` is recorded.
`route_string` is `DCT 0540S10930E DCT 0701S11215E DCT WADD` (a rejoin ends on its coordinate and
a trailing `DCT`). Benchmark (`tests/test_reroute.py`, 200 random flights against a four-part
jagged cone): 22 convex vertices, graph build 2 ms, about 1 ms a flight; 83 of 200 got
`NO_ROUTE` (more than 3 turn points), against 85 before the hull (the four parts merge into
one blob either way); at 4 turn points 26, at 5 nine, at 6 three, at 8 none.

`data/routes_apac.json` (built by `scripts/build_routes.py` from the VRS standing data
`routes.csv.gz` and `airports.csv.gz` at `vrs-standing-data.adsb.lol`, CC0, fetched
2026-10-11; both URLs, SHA-256 and the licence are in the file header): `routes`, callsign ->
hyphen-joined airport chain (62,341 callsigns), kept when every airport has a known position
and lies in `data/airports.json` or within 1,500 NM of a TEPHRA region; `airports`, the
`[lat, lon]` of the 613 chain airports the catalogue lacks. About 1.5 MB. `lookup` picks the leg
whose great circle passes within `reroute.route_max_cross_track_nm` of the aircraft, between
its ends, with the track within 90 degrees of the bearing to the destination.

Route lines on the Wall: `great_circle` densifies the great circle (at most 256 points) and
unwraps each longitude against the one before, so a leg across the antimeridian runs on past 180
and MapLibre draws it continuously. `route_features` writes one `line` per pair of airports, id
`<a>-<b>` with the two codes in alphabetical order and `ends` `[a, b]`: both directions of a pair
share it (it has no arrows, and two faint lines stacked read as the picked one). It carries the
hexes of the flights it is drawn for (both directions), plus one `airport` Point per end, id
`<icao>@<lon>`. A leg from an airport to itself is dropped, and a pair whose airport has no known
position is left out (no guessed place).

### 5.12 ask

`tephra/agents/ask.py`
```python
async def answer_question(runtime: AskRuntime, llm: LlmBackend, question: str, *,
                          flight_id: str | None = None, trace: TraceSink | None = None
                          ) -> AskAnswer | AskFailure                   # never raises for model trouble
def ask_question(runtime: AskRuntime, question: str, flight_id: str | None, *,
                 max_age: timedelta) -> Question                        # section 5.7, model answers
async def store_ask(store: Store, result: AskAnswer | AskFailure, *, actor: str) -> None
def validate_reply(reply: AskReply, evidence: Sequence[AskEvidence], *, question: str,
                   airport_icaos: Iterable[str]) -> list[str]
def build_ask_agent(model: str, toolkit: AskToolkit, *, before_model_callback=None,
                    on_model_error_callback=None) -> LlmAgent
```
An ADK `LlmAgent` on `model_lite` with read-only tools over the runtime: `situation`,
`discrepancies`, `cone`, `exposed_flights`, `flight`, `advisory`, `plan`, `reroute_options`,
`feeds`, `ai_failures`, and the what-if tools `what_if_band(volcano_id, base_fl, top_fl)` and
`what_if_extent(volcano_id, extra_km)`, which re-run exposure on a modified copy of the cone and
change no state (every result is labelled "NOTHING IN TEPHRA CHANGED; THIS IS NOT AN ADVISORY").
At most 6 tool calls. Every result is an `AskEvidence` (`T01`, ...) with its source ids. The
reply is `{answer (at most 700 characters), claims [{text, evidence_ids, kind}], status
answered|refused, refusal_reason, follow_ups, language}`; the validator requires every number,
level, ICAO code, callsign, time and id in `answer` and `claims` to appear in a cited result,
rejects "is safe" phrasing, allows one repair turn, then `AskFailure`. No dispatcher name is in a
tool result. The stub answers with a labelled count of exposed flights. `AskRuntime.answers`
(`AiAnswers | None`): the same model's answer to the same question in the same picture is
checked again by running the tool calls it made again (code): their results must be what they
were (a hash of every result kept with the answer) and the reply must validate against them;
when it passes, no model is asked (the answer's model id, prompt hash and `answered_at` are the
kept ones); else the agent runs, and an answer that passes is kept with its tool calls.
`tephra/agents/voice.py`: `transcribe(llm, audio, mime_type) -> Transcript` (one lite call with
an audio part), `speak(text, language, *, llm, client_factory, timeout_s) -> bytes`
(Gemini TTS on the backend's `tts` tier, 24 kHz 16-bit PCM wrapped in a WAV header),
`make_tts_client(settings)`, `SpeechCache`, `MAX_AUDIO_BYTES = 1 MiB`. Both raise
`AiUnavailable`; the stub has neither a transcript nor audio. `speak` reserves and paces the
speech model's own budget (speech has its own free-tier pool) and a per-day 429 closes only the
speech model, never the lite model. `GET /api/budget` is `Runtime.budget_view()` (section 5.5).

### 5.13 notices (JMA XML, Notice Reader, Satellite Reader)

`tephra/feeds/jma_volcano.py`: `fetch_jma_volcano(source, catalogue, *, since, known_urls) ->
list[Vona]`, `parse_jma_entries`, `parse_jma_report`. Reads the Atom feed
`https://www.data.jma.go.jp/developer/xml/feed/eqvol.xml` and the VFVO52 (eruption observation)
and VFVO56 (eruption flash) documents of catalogue volcanoes with a parser and no model;
`ash_observed` is true for an eruption (the conservative side), `color_code` is UNKNOWN (JMA
publishes alert levels), the provenance feed is `FeedId.JMA_VOLCANO`. Credit: "Source: Japan
Meteorological Agency website (parsed by TEPHRA)".
`tephra/agents/notice_reader.py`
```python
async def read_notice(text: str, llm: LlmBackend, catalogue: VolcanoCatalogue, *, replay: bool = False,
                      answers: AiAnswers | None = None) -> NoticeReading
                      # answers: the same model's reading of the same text, checked again with
                      # check_extraction now; created_at is when it was read
def notice_question(source: str) -> Question
def check_extraction(extraction, source, catalogue, at) -> Check
def normalise_notice(text: str) -> str            # NFKC
def notice_id(text: str) -> str                   # NOTICE-<sha12>
```
One lite call (and at most one repair) returns, per field, a value and a verbatim evidence
substring. A reading is `verified` only if every claim's evidence occurs in the normalised text,
numbers and enums match their evidence, the volcano is in the catalogue and the notice states a
date with its year, a clock time and a zone word (a zone is never assumed). Code converts zones
(WIB -7, WITA -8, WIT -9, JST -9, PHT -8) and metres to feet and marks them `derived`. A verified
reading carries a `Vona`; anything else stays raw text, "not verified", and never reaches the
pipeline. A model failure is stored as `ai_unavailable`.
`tephra/agents/satellite_reader.py`
```python
async def read_satellite(volcano, frames: Sequence[tuple[SatelliteFrame, bytes]], official_layers,
                         llm, *, replay: bool = False, trace: TraceSink | None = None,
                         answers: AiAnswers | None = None) -> SatelliteReading
                         # answers: the same model's reading of the same scans, checked again with
                         # validate_extraction, boxes placed by code now, created_at when it was read
async def kept_reading(volcano, frames, official_layers, llm, answers, *, replay=False
                       ) -> SatelliteReading | None   # the look ahead: a kept, checked reading;
                                                      # nothing asked, counted or traced
def satellite_question(volcano, chosen) -> Question
def select_frames(volcano, frames) -> dict[FrameProduct, tuple[SatelliteFrame, bytes]]
def is_current(reading, volcano, frames) -> bool         # the gate: same newest frames
def plume_part(reading) -> LlmPart | None                # the text the Plume Reader may cite
```
One lite call on the newest Dust RGB and B13 crops with the colour key as text. Output: `ash_visible`,
`so2_visible` (code rejects any answer but `uncertain`: Dust RGB cannot show SO2),
`obscured_by_cloud` (each yes, no or uncertain), at most four ash boxes (`box_2d` as
`[ymin, xmin, ymax, xmax]`, 0 to 1000) and `limits` with no digits. Boxes become polygons, a
bearing and a distance from the vent only when the frame is georeferenced (`bbox`; none is today).
It never narrows anything: "no ash" while cloud may cover the area is rejected.

### 5.14 recovery

`tephra/recovery/` (feature models in `models.py`: `Schedule`, `Closure`, `RecoveryScenario`,
`RecoveryPlan`, `FlightAction`, `RunRequest`).
```python
load_schedule(data_dir: Path, at: datetime) -> Schedule                      # raises ScheduleError
find_closures(airports, *, cones, layers, tafs, metars, at, horizon_end, policy) -> list[Closure]
merge_closures(closures) -> list[Closure]
network_closures(runtime, schedule, *, at, tafs, metars) -> list[Closure]    # network.py
solve_recovery(schedule, closures, *, now, policy, airports, extend_min=0,
               protect_flights=(), max_delay_min=None) -> RecoveryScenario    # CP-SAT; NO_PLAN, never greedy
describe_disruption(schedule, closures, *, now, policy) -> Disruption
async recommend_recovery(schedule, closures, llm, *, settings, policy, airports,
                         replay, trace=None) -> RecoveryPlan                  # never raises
async submit_plan / approve / reject(store, bus, plan_id, *, expected_version, ...) , list_plans, get_plan   # decisions.py
```
Data: `data/rfa/{fleet,crews,flights}.json`, built by `scripts/build_rfa_schedule.py` with seed
20260907: 30 tails (25 A320, 5 A321), 142 flights on real airport pairs from
`routes_apac.json`, all labelled fictional. `data/rfa/flights.json` is one template day (`RfaTemplateFlight`);
`load_schedule` rolls it into a window of two operating days, the one holding the clock and the next
(every rotation returns to its start, so day 2 repeats the template `MINUTES_PER_DAY` later). A flight
(`RfaFlight`) has `service_date`, `day_offset` and the stable key `key`, e.g. `RFA239/06SEP`, used for solver
variables, `protect_flights`, `FlightAction.flight_key`, `Disruption.blocked_flights`, comms targets
(`RecoveryChange.flight_key`) and the UIs; the bare number repeats daily. `RecoveryPlan.chosen` is a computed
field (the chosen scenario) so the API returns it; it is not stored. `Closure` carries `basis`, `base_ft`,
`top_ft`, `radius_nm` and the computed one-line `summary`, beside the full `reason` and `source_ids`. An airport
is closed while a hazard area from the surface to FL100 comes within
`recovery.airport_closure_radius_nm`, or its TAF or METAR carries `VA` (a METAR `VA` with no end
is closed until the planning horizon and marked `open_ended`). The solver frees flights from now
to `horizon_after_closure_min` after the last closure, freezes the rest, and chooses keep (a delay
in 5-minute steps up to `max_delay_min`), cancel with the paired leg, or swap, under minimum turn,
`max_fdp_min`, closed-airport and seat constraints, minimising the policy's USD weights. The search
is deterministic: `solve_work_s` of CP-SAT deterministic time with interleaved search on a fixed 8
workers and seed, so the same disruption gives the same plan on every run and machine;
`solve_time_limit_s` is only a wall-clock guard. There is no solution hint and no greedy plan. The ADK agent has the tools
`disruption`, `run_scenario(extend_min, protect_flights, max_delay_min)`, `compare` and
`submit_recommendation(scenario_id, rationale, risks)`; scenarios are the closure as forecast,
`+scenario_extend_1_min` and `+scenario_extend_2_min`; every number, flight and airport in the
rationale must come from a tool result. A failed run is stored with status `AI_UNAVAILABLE` and
cannot be decided. Approval stores nothing outbound; messages are drafted from the approved plan.
HTTP in section 8.7; SSE `recovery` carries the full plan (about 60 KB).

### 5.15 comms

`tephra/comms/messages.py`
```python
async def draft_messages(runtime: CommsRuntime, *, advisory_id: str | None = None,
                         recovery_id: str | None = None, actor: str) -> list[CrewPaxMessage]
async def approve / reject(store, bus, message_id, *, expected_version, ..., actor)
async def edit_and_approve(store, bus, message_id, *, expected_version, bodies, actor)
def passenger_targets(plan: RecoveryInput, airports, policy: OperatorPolicy) -> list[Target]
def languages_for(origin: Airport, dest: Airport) -> list[Language]
def template_problems(templates, spec, *, known_codes) -> list[str]
def templates_question(spec: TemplateSpec) -> Question   # section 5.7, model answers
```
`CommsRuntime.answers` (`AiAnswers | None`): templates for the same spec from the same model are
used when `template_problems` passes now (no call); new ones that pass are kept. A message's
`created_at` is when code filled and stored it.
Messages come from an approved advisory (an English crew briefing) or an approved recovery plan (a
crew notice per tail and a passenger notice per cancelled flight or delayed flight whose delay is
at least `recovery.pax_notice_min_delay_min`, 30 minutes, PM 89/2015 category 1; a swap gets
none). Languages follow the route: Indonesian domestic Bahasa Indonesia and English, Japan
Japanese and English, both all three, else English. The model writes one template per language
for each (kind, status, jurisdiction, languages) group with `{FLIGHT}`, `{ROUTE}`,
`{NEW_DEP_LOCAL}`, `{DELAY_MIN}`, `{REASON_SOURCE}`, `{CONTACT}`, ... and never sees a value; code
fills them. The validator rejects a digit outside a placeholder (full-width digits included), a
missing, unknown or malformed placeholder, a URL or e-mail address, an airport code, text in the
wrong script and a wrong language set; one repair, then `AiUnavailable`, and nothing is stored.
`CrewPaxMessage` is DRAFT -> APPROVED, EDITED or REJECTED with a version compare-and-set; an
approved message is written to `outbound`. `tephra/comms/handover.py`
```python
async def draft_handover(runtime: HandoverRuntime, since: datetime, outgoing: str, incoming: str) -> HandoverBrief
async def acknowledge(runtime, handover_id: str, *, actor: str) -> HandoverBrief
def handover_question(facts_text: str) -> Question   # every fact but the as_of clock line
```
Code gathers the facts (advisories and their states, AI failures, recovery plans, feeds,
discrepancies, decisions since `since`) and sets `severity`; one lite call writes `situation` and
`contingencies` with source ids, checked so cited ids exist and every number appears in the
evidence. The same model's narrative for identical inputs is used when it passes those checks
now. The facts carry no dispatcher names. The brief lists the advisory, message and recovery
drafts open at that moment in `handed_over_open` (and as `actions_open` lines starting `HANDED
OVER OPEN:`); `acknowledge` is allowed while drafts are open and records the ones still open in
`receiver_ack.open_drafts` and the `HANDOVER_ACKED` audit entry; a second read-back keeps the
first. `HandoverBrief` is stored in `docs` with `doc_type = "handover"` (ids `ho_<12 hex>`).

### 5.16 regdocs

`tephra/regdocs/`
```python
async def draft_sra(runtime: DocsRuntime, region: str, *, actor: str = "system") -> SraDraft   # sra.py; raises UnknownRegion, NoActiveVolcano, AiUnavailable
async def write_narrative(llm, facts, *, answers: AiAnswers | None = None) -> Narrated
                         # narrative.py; Narrated(narrative, call, written_at): the same model's
                         # boxes for identical facts, checked again, keep their time
def narrative_question(facts: Mapping[str, Any]) -> Question   # DocsRuntime.answers feeds it
async def draft_var(runtime: DocsRuntime, flight_id: str, *, actor: str = "system") -> VarDraft  # var.py; raises FlightNotExposed; no model call
async def draft_crew_message(runtime: DocsRuntime, view: CrewReportView, *, vaac: VaacCentre | None,
                             actor: str = "system") -> CrewMessageDraft   # crew_message.py; raises NotAnAshReport; no model call
async def sign_doc(store, bus, doc_id: str, *, role, name, actor) -> doc                         # registry.py; a WITHDRAWN doc is refused
async def withdraw_crew_messages(store, bus, report_id: str, *, reason, actor) -> list[CrewMessageDraft]  # registry.py
async def get_doc / list_docs(store, ...); record_new_doc(store, bus, doc, *, actor, ...)
```
The SRA (regions `java_bali`, `halmahera`, `kyushu`) follows the sections of research/18b: code
fills every table and field from TEPHRA's evidence; one lite call writes four boxes (information
sources, hazard, exposure, mitigation), rejected if they hold a clock time or a number not in the
facts, an id, an airport or flight code not in the facts, or "safe", "approved", "compliant" or
"ash gone". Unfilled fields (AOC number, engines, fleet, executive, acceptance reference, eruption
phase, MEL relief, severity, probability, tolerability) stay blank and marked "human". The header
is `DRAFT - NOT AN APPROVED SRA - FOR HUMAN SIGN-OFF`; ICAO Doc 9974 is cited as First Edition
2012 by title; the Indonesian circular SE-DJPU 15/2026 is "per press reports; verify against the
PDF". The VAR fills items 1 to 5 from the ADS-B proxy flight (item 5 labelled "NOT a crew
observation") and leaves items 6 to 16 "PILOT/DISPATCHER TO COMPLETE", with an AIREP SPECIAL
template. The message to the weather office and the VAAC (`CrewMessageDraft`, kind
`CREW_MESSAGE`, EUR Doc 019 3.2.9 e) is started from a crew report (`draft_crew_message`): its
`to` lines (the MWO for the FIR, the attributed volcano's VAAC or "the VAAC responsible for the
area", from the fictional airline's dispatch), a `subject` (outside, partly outside or inside
the published VA area) and a code-written `body`: who reported what, where, at which level and
when; whether the position is the ADS-B fix or typed; how it stands against the valid VA SIGMET
and advisory areas; the nearest catalogued volcano only as a distance ("the source is not
known"), or none within `active_radius_km`; the crew remarks; a request to take it into
account. A tracked flight is named as the fictional airline's proxy flight for its ADS-B
callsign; a typed callsign as "typed by the dispatcher; not tracked by TEPHRA". `facts` give
what each line rests on; one `DISPATCHER` signature line. Only an `ASH` report that is not
withdrawn qualifies. Withdrawing the report sets every message drafted from it `WITHDRAWN`
(`withdrawn_note`, audit `DOC_WITHDRAWN`), signed or not; a withdrawn message cannot be
signed. Signatures are per role (`DISPATCHER`, `SAFETY_MANAGER`, `ACCOUNTABLE_EXECUTIVE`,
`PILOT_IN_COMMAND`); a document is `SIGNED` when every line is filled and its header never changes.
Nothing is queued to `outbound`.

### 5.17 backtest

`tephra/backtest/`
```python
async def run_case(case_id, *, settings, arm="D", step=timedelta(minutes=30), max_calls=0, on_tick=None) -> CaseScore
async def run_backtest(case_ids, *, settings, arms=("D",), step=..., max_calls=0) -> BacktestScorecard
write_scorecard / load_scorecard(path); async store_scorecard(store, scorecard)   # collection backtest, doc latest
async def build_report(scorecard, llm) -> str            # report.py; raises ReportUnavailable("AI UNAVAILABLE: ...")
def score_tick(...) -> TickScore; lead_minutes(...); summarise(...)                # metrics.py
```
Replays each case in `data/replay/` tick by tick on a fixed clock (with the automatic recovery
off), records TEPHRA's cone and the official-only area, and scores them against the official areas
issued later (those issued more than `FEED_CLOCK_SLACK` after the tick, so nothing leaks): coverage,
gain over the official baseline, over-warning (1 - precision), area ratio, incremental lead time
at tau 0.9, vertical hit. `floor_violations` and `input_leaks` must be 0 (the script exits 2
otherwise). Arm D is the stub reader (deterministic: it adds nothing over the official floor by
construction); arm G replays cached Gemini reads, never spends more than `max_calls`, and is run
by hand. The prose report is one lite call checked number by number against the scorecard; on any
failure no `REPORT.md` is written. Scorecard in `docs/backtest/scorecard.json` (arm D, 30-minute
steps: 90.3% coverage, equal to the official-only 90.3%, 29.0% over-warning, over 1,391 snapshots
of three cases); `GET /api/backtest` serves it.

### 5.18 duty (the Duty Officer, the coordinator agent)

```python
# tephra/agents/adk_runtime.py: what every ADK agent shares
class ModelGuard:            # before_model_callback: reserves and paces each turn on the tier's model, caps turns;
    def __init__(self, llm: LlmBackend, *, max_turns: int, tier: Tier = "lite") -> None   # async on_model_error closes that model on a per-day 429
def request_tokens(llm_request) -> int             # estimated input tokens of a turn (tokens-a-minute pacing)
def stop_response(reason: str) -> LlmResponse      # an answer with no function call, which ends the run
def tool_record(name, args, result) -> ToolCallRecord ; def summarise(result, limit=240) -> str
DAILY_QUOTA_SPENT, BUDGET_EXHAUSTED

# tephra/agents/duty_officer.py
class DutyExecutor(Protocol):        # what the tools act on; tephra.duty implements it over the runtime
    async def assess(self, volcano_id: str) -> tuple[dict[str, Any], list[DutyItem]]
    async def plan(self, flight_id: str) -> dict[str, Any]
    async def recover(self) -> dict[str, Any]
    async def draft_sra(self, region: str) -> dict[str, Any]
@dataclass class DutyToolkit         # the work list as the run goes: pending, done, replaced, deferred
async def run_duty_officer(worklist, executor, llm, *, digest: str, settings: Settings,
                           trigger: Literal["tick", "adsb"], replay: bool,
                           trace: TraceSink | None = None,
                           reuse: Reuse | None = None, rerun: timedelta | None = None) -> DutyRun
def coordinator_question(worklist: Sequence[DutyItem], *, policy_version: str,
                         max_age: timedelta) -> Question
                           # material: the policy version and (kind, subject, mandatory, urgency)
                           # of each item, sorted
class DutyDecisions(TephraModel):    # the kept answer: delegations [{tool, subjects, outcome}],
                                     # deferrals and priorities [{kind, subject, text}], summary,
                                     # watch, outcome, turns
def build_duty_agent(model, toolkit, *, before_model_callback=None, on_model_error_callback=None) -> LlmAgent
def validate_brief(brief: DutyBrief, toolkit: DutyToolkit) -> list[str]

# tephra/duty.py
class DeskUnreachable(Exception)     # the open drafts could not be read
async def dispatch_duty(runtime, worklist, drafts, at, report, *, trigger, epoch, waiting=0) -> DutyRun
def duty_worklist(runtime, at, drafts_by_flight) -> list[DutyItem]
async def drafts_by_flight(runtime) -> dict[str, list[Advisory]]
```

The work list (code, `duty_worklist`, most urgent first):

| Kind | When it is due | Mandatory | Item id |
|---|---|---|---|
| ASSESS | the plume gate queued a read (`Runtime.assess_due`) | no official area valid but a VONA reports ash, or a WARNING discrepancy | `stable_id("DI", ASSESS, volcano_id, input_hash)` |
| PLAN | `Runtime.plan_due(flight)`: a new cone, a more urgent bucket, or a planning error's retry time (positions fresh only) | inside now or entry within `planner.divert_within_min` | `stable_id("DI", PLAN, flight_id, cone_id, bucket)` |
| RECOVER | `Runtime.recovery_due` (closed airports changed) | never | `stable_id("DI", RECOVER, *airports)` |
| SRA | a region (by `Region.bbox`) carries exposed flights and has had no SRA dispatched today | never | `stable_id("DI", SRA, region, date)` |

The AI worker (section 5.7) calls `dispatch_duty` with the items it admitted (those not offered
for `duty.rerun_min`, 5 min, that their lane allows now), inside `use_lane("urgent")` for a run
of mandatory items or `use_lane("routine", admitted=True)`, with a digest per active volcano
(area label, discrepancies by severity, exposed and inside counts), the work count, the number
of routine items waiting for budget and the day's budget per model. The same model's
decisions for the same work (`coordinator_question`, section 5.7) are made again instead
(`DutyDecisions`, in subjects: item ids change with a cone or an input hash): its delegations
in its order through the same tools (each must come out as it did), its deferrals (within
`rerun`, the policy's `duty.rerun_min`), then its brief (priorities mapped to this run's item
ids) through `validate_brief`; when one of those fails, or mandatory work is left undone, the
kept brief and deferrals are dropped and the model finishes the run. The run keeps the model's
`decided_at` and `turns`. A run that ends after a picture reset (`epoch`) changes nothing.

The agent (`AGENT_NAME = "tephra_duty_officer"`, lite tier, at most 12 model turns,
`duty_run_timeout_s` per run) has six tools:

| Tool | Reaches | Code rules |
|---|---|---|
| `assess_volcanoes(volcano_ids)` | `Runtime.assess_volcano`: Satellite Reader, Plume Reader, `build_cone`, the volcano's exposure | only volcanoes with an ASSESS item; returns the PLAN items the new cone made due (an older item for the same flight is replaced, not left undone) |
| `plan_flights(flight_ids)` | `Runtime.plan_flight_now`: reroutes, Exposure Planner, Dispatch Drafter, the Desk | only flights with a PLAN item; refused while the flight's volcano has an ASSESS item; results are the draft or the AI failure |
| `run_recovery()` | `Runtime.start_recovery`: a recovery job queued in the AI worker | only with a RECOVER item |
| `draft_sra(region)` | `regdocs.sra.draft_sra` | only with an SRA item; marked done for the day even when it fails; while an unsigned SRA draft of the region in the mode playing waits, that draft is returned and no new one is made (the day's mark is in memory, so a replay run or a restart would otherwise add one more to sign) |
| `defer(item_ids, reason)` | nothing | mandatory items, items with no reason, and a reason with a clock time or a number or RFA flight not in the run's input (as the brief) are refused |
| `submit_brief(summary, priority_item_ids, priority_reasons, watch)` | the brief | `validate_brief`: summary 500 chars, reasons 160, at most 4 watch lines of 160; known item ids, each once; no clock times; every number and RFA flight must appear in the digest, the work list or a tool result |

After the first turn, a missing or rejected brief, or mandatory work still undone, gets one
repair turn naming the problems and the undone items (outcome `REPAIRED`). A run that ends
with no valid brief (model error, budget, turn limit, timeout) is `MODEL_FAILED`; its
delegations stand. Then `_hold_the_line`: each undone mandatory PLAN item becomes an
`AiFailure` (stage `duty_officer`, reason `DUTY OFFICER AI UNAVAILABLE: ...` or `DUTY OFFICER
DID NOT DISPATCH THIS FLIGHT`) on the Desk; an undone mandatory ASSESS item writes an error trace
line and an `AI_FAILED` audit entry (the area stays at the official products). The run is stored
in `duty`, kept as `Runtime.duty` (restored on restart), published as SSE `duty`, and counted in
the AI worker's `TickReport.duty_runs`. Each run is stamped `recorded_wall_at` before it is stored, and
`_hold_the_line` records undone flights through `Runtime.track_failure` (section 5.7), so a
flight's failure of an earlier run or cone is closed, not listed twice. `GET /api/duty` reads the
newest 200 runs by `recorded_wall_at` and lists those of the current mode and, in REPLAY, of the
replay run playing (`Runtime.replay_run_since`). Trace lines use stage `DUTY`. With `TEPHRA_LLM=stub` the run dispatches
everything, plume reads first, most urgent first, and briefs `NO MODEL: ...` (outcome `STUB`).

### 5.19 crew (crew reports of ash)

A dispatcher enters a crew (pilot) report of ash on the Desk. Code draws a "crew report
caution area" from it; no model is involved and nothing is ingested from a feed. The area is a
**flag only**: it lives in `Runtime.crew`, beside the situations and cones and never inside
them, so it never shrinks or replaces an official area, never changes a cone, a plan or the
Plume Reader's input, and never makes the code think an official area is in force
(`Situation.official_valid_now` does not see it). No planning, no drafts, no model calls.

`tephra/geo/crew_area.py` (pure)
```python
CIRCLE_STEPS: Final = 64; CIRCLE_SLACK: Final = 1.001; WIND_PROFILE_SLACK: Final = timedelta(minutes=60)
class StretchWind(NamedTuple): level: WindLevel; source_id: str; valid_at: datetime
class AreaRelation(NamedTuple): relation: Literal["COVERED", "OVERLAPS", "OUTSIDE"]; covered_by: list[str]
def circle_ring(lat: float, lon: float, radius_km: float) -> list[tuple[float, float]]   # (lon, lat), circumscribed
def area_polygon(lat: float, lon: float, radius_nm: float, *, stretch_nm: float = 0.0,
                 toward_deg: float = 0.0) -> GeoPolygon      # circle, or hull of it and the circle moved downwind
def pick_wind(profiles: Sequence[WindProfile], observed_at: datetime, base_ft: int, top_ft: int
              ) -> StretchWind | None
def stretch_note(wind: StretchWind | None, *, threshold_kt: int, stretch_nm: float, wind_place: str,
                 no_wind_reason: str) -> str          # wind_place: "at the report position", or the recorded volcano profile
def relation_to_official(polygon: GeoPolygon, base_ft: int, top_ft: int,
                         layers: Sequence[OfficialLayer], at: datetime) -> AreaRelation
```
`tephra/desk/crew_reports.py`
```python
LIST_WINDOW: Final = timedelta(hours=24); LOAD_LIMIT: Final = 500
class CrewReportRefused(Exception): problems: list[str]
class CrewReportNotFound(Exception); class AlreadyWithdrawn(Exception)
class CrewEntry(TephraModel)        # POST body: hex | callsign (exactly one), cues, level_from_fl, level_to_fl?, observed_at, lat?, lon?, remarks?
class WithdrawRequest(TephraModel)  # {reason (3-500 chars)}
class CrewFix(NamedTuple)           # hex, callsign, lat, lon, alt_baro_ft, observed_at, source_id
class FixLookup(TephraModel)        # {found, hex, proxy_flight, callsign, lat, lon, alt_baro_ft, observed_at, source_id, note}
class FixHistory:                   # airline ADS-B positions per hex, kept TEPHRA_CREW_FIX_HISTORY_MIN
    def add(aircraft, at); def clear(); def fixes(hex) -> Sequence[CrewFix]; def hexes(); def callsigns(hex)
def report_kind(cues: Sequence[CrewCue]) -> CrewReportKind
def resolve_flight(hex_id: str | None, typed: str | None, aircraft, history: FixHistory) -> tuple[str | None, str | None]
def find_fix(hex_id: str | None, observed_at: datetime, aircraft, history, *, within: timedelta) -> CrewFix | None
def observed_problem(observed_at, at, policy) -> str | None          # "observed_at: ..." when in the future or too old
class CheckedEntry(NamedTuple): kind; levels: tuple[int, int]; lat; lon; basis: CrewPositionBasis
def check_entry(entry: CrewEntry, *, at, flight, fix, fix_within, policy) -> CheckedEntry   # raises CrewReportRefused
def build_report(entry, checked: CheckedEntry, *, actor, at, replay_case_id, flight, fix, volcano: Volcano | None,
                 winds: Sequence[WindProfile], wind_place: str, no_wind_reason: str, policy, summary) -> CrewReport
async def record_entry(store, report) -> None                       # put + CREW_REPORT_ENTERED
async def withdraw(store, report, *, reason, actor) -> CrewReport   # put + CREW_REPORT_WITHDRAWN (note = reason)
async def expire(store, report, at, *, note=None) -> CrewReport     # put + CREW_REPORT_EXPIRED (system), once
async def load_reports(store) -> list[CrewReport]
def build_picture(reports, *, at, replay_case_id, replay, replay_run_since: datetime | None, aircraft,
                  layers, lookahead_min) -> CrewPicture
def report_view(report, layers, at) -> CrewReportView               # a report the picture does not list
```
Rules:
- **Kind.** `ASH_SEEN`, `ST_ELMOS_FIRE` or `ENGINE` (`CREW_AREA_CUES`), or `SULPHUR_SMELL`
  together with `HAZE` (`CREW_SMELL_AND_HAZE`, the smell-plus-haze encounter cue), make an `ASH`
  report, which draws an area. `SULPHUR_SMELL` or `HAZE` alone is `ROUTINE` (FAA JO 7110.65
  2-6-2 for the smell): recorded, no area. `NO_ASH_SEEN` alone is `NO_ASH`: recorded, and it never removes
  or shortens anything. `ASH_SEEN` with `NO_ASH_SEEN` is refused.
- **Refused, never guessed** (422 `validation_failed`, every problem listed): no level (no band
  is invented); the upper level below the lower; `observed_at` in the future or more than
  `crew_reports.valid_min` ago (checked before the position, which is looked up at that time,
  and by `GET .../fix` too, so the form says so before asking for a position); a `hex` that is not a tracked airline flight; a callsign that is
  not airline-style, or that more than one tracked flight flies; half a position; no position
  when no fix is held; a typed position when a fix is held.
- **Position.** The reporting flight's ADS-B fix nearest `observed_at` within the ADS-B stale
  age (`settings.stale_after_s(FeedId.ADSB)`, 90 s), from the live aircraft and `FixHistory`
  (`position_basis ADSB_FIX`, `position_source_id` the snapshot). Otherwise the position the
  dispatcher typed (`TYPED`, shown "typed by dispatcher"). A fix older than the history
  (`TEPHRA_CREW_FIX_HISTORY_MIN`, 30) is not held, so a late entry types the position.
- **Volcano.** The nearest catalogued volcano within `settings.active_radius_km` (300 km);
  none gives an unattributed report (`volcano_id` None, labelled `no catalogued volcano`),
  never the nearest volcano further away. A report never makes a volcano active.
- **Area** (`ASH` only): `area_polygon` of `crew_reports.radius_nm` (60 NM) around the
  position, circumscribed; band `[max(0, from_fl x 100 - level_margin_ft), to_fl x 100 +
  level_margin_ft]`; valid `observed_at` to `observed_at + valid_min` (360). Stretch: in LIVE
  the Open-Meteo profile at the report position, fetched at entry (`fetch_winds(...,
  past_hours=ceil(valid_min / 60) + 1)`, a public GET; a failed fetch is said in the note); in
  REPLAY, which never reaches a live feed, the profile recorded above the attributed volcano,
  named with its distance in the note, or none. The hourly profile within 60 min of
  `observed_at`, the strongest pressure level inside the band (else the level nearest its
  middle); when its speed is above `stretch_wind_kt` (30) the
  area is the hull of the circle and the circle moved `speed x downwind_stretch_min / 60` NM
  downwind (30 min), fixed at entry. No wind held: not stretched, and `stretch_note` says why.
  A new report draws a new area; nothing extends an old one.
- **States** (`build_picture`, each update): `WITHDRAWN`; `NO_AREA` (ROUTINE, NO_ASH);
  `EXPIRED` after `valid_to`; `COVERED` when the official layers valid now whose band spans the
  area's together contain it ("Covered by official area", display only: the area and its flags
  stay); otherwise `ACTIVE`, with `outside_official`, `discrepancy` "Crew report outside the
  official area" and `outside_detail` whenever any of it lies outside every valid official
  layer, laterally or vertically ("No valid official area meets it, sideways or in height." or
  "Part of it lies outside every valid official area, sideways or in height."). No official
  product, NO VA EXP, NOT IDENTIFIABLE or no-ash report ends or shortens an area.
- **Flags.** For each ACTIVE or COVERED area, `find_crossings` over the airline aircraft with
  the area's band as it is (it already holds `level_margin_ft`; no exposure margin is added),
  looking ahead `min(exposure_lookahead_min, minutes to valid_to)`. One `CrewFlag` per flight
  (the earliest entry; every report id); `reporter` and line `CREW_REPORTER_LINE` ("This
  flight's crew reported ash") for the reporting flight, else "Crew report of ash on this
  route". `AircraftFeatureProps.crew_report` marks it on the map.
- **Picture.** Reports of the current mode (and, in REPLAY, the playing case and run) observed by
  now and within `LIST_WINDOW`, newest first, with code-written `age_text` ("reported just
  now", "reported 47 min ago"), `place_text` and `state_label`. Features: `area` (Polygon) and
  `pin` (Point at the report position) for ACTIVE and COVERED areas, and a `path` LineString
  per flag.
- **Expiry.** `Runtime.update_crew` writes `CREW_REPORT_EXPIRED` once per lapsed area of the
  current mode (`expiry_recorded_at`); a failed write is retried at the next update. A recorded
  expiry stands: the state is `EXPIRED` from then on, whatever the clock says.
- **REPLAY.** Reports entered in REPLAY carry `replay` and `replay_case_id`, are shown only while
  that case plays, and never mix with LIVE ones. Each replay run (a process start, a switch to
  REPLAY, a loop of the replay clock) starts at `Runtime._replay_run_wall`; a report entered in
  an earlier run (`entered_wall_at` before it) is not shown and its area is ended with
  `CREW_REPORT_EXPIRED` ("the replay run it was entered in has ended"), so a replay played
  again never brings it back.

### 5.20 Airline data connections (connect)

An airline pushes its own data in (`tephra.airline/1`; `tephra.positions/1` is positions only), in
three sections, each with a place to go:
- `positions` (`PushedPosition`): join the ADS-B targets and are checked against the ash the
  same way (exposure, drafts, the Wall, the Desk, Ask).
- `flight_plans` (`PushedFlightPlan`: the airline's flight number, the aircraft's hex or
  callsign, origin, destination, optional times and cruise level): held in
  `Runtime.flight_plans` until 3 h after arrival; `known_routes()` uses a plan's origin and
  destination before the callsign's usual route (`FlightRoute.source` `airline-plan`;
  `AircraftFeatureProps.route_source` `PLAN`, `flight_plan` its number), and a plan departing
  or landing at an airport the current airport plan closes is a `closed_hits` entry. The
  re-planning solver still plans the RFA schedule (`data/rfa`); pushed plans do not join it.
- `pilot_reports` (a `CrewEntry`, as the Desk enters one): each is entered through
  `Runtime.enter_crew_report` with actor `connect:<connection name>` (same checks, caution area
  and flags; a report on a tracked flight is placed at its fix); the same report pushed again
  is not entered twice.

The first section, in detail: `tephra.desk.connections`: `create_connection(store, name, *, actor,
sample=False) -> (Connection, key)` (key `tph_` + 32 url-safe characters, shown once, only its
SHA-256 stored), `find_by_key`, `list_connections`, `revoke_connection`, `save_counts`,
`checked_positions(raw, connection, at) -> (list[Aircraft], list[PushProblem])` (source id
`PUSH:<connection id>:<DDHHMMZ>`; `PUSH_FRESH_S` 300). `Runtime.take_push(connection, raw)`
keeps the positions that pass in `Runtime.pushed` (hex -> newest; cleared on a picture reset),
runs `run_exposures` and `publish_live` when no tick holds the lock (else the next tick does),
saves the counters, keeps the summary in `Runtime.push_log` (the newest 400), publishes `push` and returns `PushResult`; `retime` stamps every record with the active clock first (uploads). `Runtime.connect_live()` builds `ConnectLive`. `Runtime.aircraft()` merges the
ADS-B targets and the pushed positions not older than `PUSH_FRESH_S` (newest per address), so
exposure, drafts, the Wall, the Desk and Ask all see them; `AircraftFeatureProps.data_source`
says `AIRLINE` for them. `tephra.desk.sample_feed`: the sample feed is real airline aircraft
(address, callsign, type, position, level, speed, track) from the replay cases' recorded ADS-B;
each is moved along its own track at its own speed from its recorded fix (a 900 km leg, then
again) and pushed every 5 s through `take_push`, flights whose leg crosses an ash area first;
`Runtime.start_sample_feed(*, actor)`, `stop_sample_feed()`; it stops itself after an hour.
`scripts/push_sample.py` does the same from any computer with a key (standard library only).

## 6. Quota and model use

| Step | Backend | Model | When it runs |
|---|---|---|---|
| Duty Officer | ADK `LlmAgent` + delegation tools | `TEPHRA_MODEL_LITE` | in the AI worker, off the tick, when the work list holds an item not offered for `duty.rerun_min` (5 min) that its lane admits (urgent: always; routine: when it fits the pacing); every model turn counts (at most 12 a run, one repair turn); its delegations spend their own specialists' calls |
| Plume Reader | google-genai, structured output | `TEPHRA_MODEL` (gemini-3.8-flash) | only when a volcano's texts or BTD indicator change (or an unchanged input's assessment is older than `max(horizon_h, 3 h)`) and the quota gate (5.7) says the call matters; at most one repair; budget 20 less the margin (18) |
| Satellite Reader | google-genai, structured output, images | `TEPHRA_MODEL_LITE` | only within a plume read the Duty Officer dispatched for that volcano and the newest frame is not the one the last reading used; at most one repair |
| Exposure Planner | ADK `LlmAgent` + FunctionTools | `TEPHRA_MODEL_LITE` (gemini-3.5-flash-lite) | once per exposed flight per cone and urgency bucket; every model turn counts (at most 10 per plan); budget 500 less the margin (450), shared by every step on that model |
| Dispatch Drafter | google-genai, structured output | `TEPHRA_MODEL_LITE` | once per new plan, plus at most one repair |
| Recovery agent | ADK `LlmAgent` + FunctionTools around CP-SAT | `TEPHRA_MODEL_LITE` | once when the set of closed RFA airports changes (`TEPHRA_RECOVERY_AUTO`), or when a dispatcher presses run; one at a time |
| Messages | google-genai, structured output | `TEPHRA_MODEL_LITE` | on demand: one call per group of messages sharing kind, status, jurisdiction and languages, plus at most one repair each |
| Handover brief | google-genai, structured output | `TEPHRA_MODEL_LITE` | on demand: one call, at most one repair |
| SRA narrative | google-genai, structured output | `TEPHRA_MODEL_LITE` | on demand: one call, at most one repair (the VAR makes none) |
| Notice Reader | google-genai, structured output | `TEPHRA_MODEL_LITE` | on demand, once per distinct pasted text (a repeat is answered from the store), plus at most one repair |
| Ask TEPHRA | ADK `LlmAgent` + read-only tools | `TEPHRA_MODEL_LITE` | on demand: up to about four calls a question (6 tool calls, one repair turn) |
| Voice in | google-genai, structured output, audio part | `TEPHRA_MODEL_LITE` | on demand: one call per recording of at most 1 MiB |
| Voice out | google-genai text-to-speech | `TEPHRA_MODEL_TTS` (gemini-3.8-flash-lite-tts) | on demand: one call per answer, cached for the process; its own budget (10 less the margin, 9) |
| Backtest report | google-genai, structured output | `TEPHRA_MODEL_LITE` | by hand (`scripts/backtest.py --report`), one call, at most one repair |

Every request is also paced per model to the free tier's per-minute limits less the margin
(`Settings.paced_rpm`: 4 for 3.8 Flash, 13 for Flash-Lite; tokens a minute too where Google sets
one): `GeminiBackend.pace` waits on the model's `RatePacer` before each attempt, and the ADK
`ModelGuard` awaits it before each agent turn, so a Duty Officer run that plans several flights
waits for its slots instead of earning 429s. A per-minute 429 that still comes back is retried
after the `retryDelay` Google names (capped at 60 s); a per-day 429 closes that model only.

Gemini 3 models run at temperature 1.0 (`temperature_for`). Budgets are counted per model id
and Google quota day (midnight to midnight Pacific) in the store (`ai_budget`), every HTTP
attempt before it is sent, retries included, so instance replacement and redeploys do not reset
them (section 5.5). Each budget is split into urgent (30%, never paced), interactive (20%, the
Desk) and routine work (paced through the day); routine work the pacing does not admit waits in
the AI worker's queue with its next slot, shown on the Wall and the Desk, and is never moved to
another model. Once a routine job starts, pacing no longer applies to it: it finishes within
the daily cap. In LIVE and REPLAY alike, a model is asked again only when something material to
its question changed: until then the same model's answer, checked again by code against the input
of the moment, is used at no call and no budget (section 5.7, model answers). REPLAY answers live
`ai_answer_replay_keep_h` (90 days by default); the key is `KEY_VERSION`, mode, case, model,
skill and the material hash (no build), so a replay loop and a deploy find the answers already
given. Free-tier limits are reported, not published
(research/06): about 20 requests/day for 3.8 Flash and 500 for 3.5 Flash-Lite. Over budget, or
after a per-day 429, **every step stops and says `AI UNAVAILABLE`**; nothing falls back to code. The Plume Reader's failure leaves the cone on
the official products alone (binding), the planner's and drafter's failures put the flight on the
Desk for a dispatcher (`AiFailure`), and every other step answers HTTP 503 `ai_unavailable`.
`GET /api/budget` and the SSE `budget` event show the day's counts per model, the pacing state
and the work waiting. With `TEPHRA_LLM=stub` no
call is made and every step but voice has a deterministic answer labelled NO MODEL.

Usage is logged as structured `json_fields` (`event="gemini_call"`, section 5.5): every
`structured` call and every Exposure Planner turn. The other ADK agents (Duty Officer, Ask
TEPHRA, recovery) and text-to-speech do not log these fields yet. The Plume Reader's and the
planner's token totals are stored on `PlumeAssessment` and `PlannedAction`.
`deploy/monitoring.sh` (optional, run by a person) turns the log lines into Cloud Monitoring
metrics.

## 7. Store collections

| Collection | Doc id | Document | Written by |
|---|---|---|---|
| `sigmets`, `vonas`, `vaas`, `frames`, `btd` | `source_id` | `Sigmet`, `Vona` (MAGMA, JMA and verified pasted notices), `VaacAdvisory`, `SatelliteFrame`, `BtdResult` | core (new or changed content only) |
| `tafs`, `metars` | ICAO | latest `Taf`, `Metar` | core (on change) |
| `winds` | volcano_id | `WindForecast` | core (when a winds poll brings new numbers; provenance aside) |
| `situations` | volcano_id | latest `Situation` | core (on change, clock-only fields aside) |
| `assessments` | assessment id | `PlumeAssessment` | core (each Plume Reader run) |
| `cones` | volcano_id | latest `HazardCone` | core (on change) |
| `plans` | plan id | `PlannedAction` | core |
| `ai_failures` | failure id | `AiFailure` (a flight with no plan or draft; handled by hand, or closed by code once it no longer stands) | core (`desk.failures`, through `Runtime.track_failure`) |
| `duty` | run id | `DutyRun` | duty (`tephra.duty.dispatch_duty`, run by the AI worker) |
| `crew_reports` | `CR-<12 hex>` | `CrewReport` (both modes; withdrawn and expired ones kept) | crew (`tephra.desk.crew_reports`, through `Runtime.enter_crew_report`, `withdraw_crew_report`, `update_crew`) |
| `connections` | `CN-<10 hex>` | `Connection` (the key's SHA-256 only, never the key; revoked ones kept) | connect (`tephra.desk.connections`) |
| `reroutes` | `RerouteOption` id | `RerouteOption` (every option of a planned flight) | core |
| `sat_readings` | reading id (`SAT-...`) | `SatelliteReading` | core |
| `notices` | `NOTICE-<sha12>` | `NoticeReading` | `routes_notices` |
| `ask_log` | `ask_<12 hex>` | `AskAnswer` or an unavailable `AskFailure` | `agents.ask` |
| `recovery` | plan id (`REC-...`) | `RecoveryPlan` | `recovery.decisions` |
| `messages` | message id | `CrewPaxMessage` (DRAFT, APPROVED, EDITED, REJECTED) | `comms.messages` |
| `docs` | `DOC-<12 hex>` or `ho_<12 hex>` | `SraDraft`, `VarDraft`, `CrewMessageDraft`, `HandoverBrief` | `regdocs.registry`, `comms.handover` |
| `backtest` | `latest` | `BacktestScorecard` | `backtest.runner.store_scorecard` |
| `advisories` | advisory id | `Advisory` (CAS on `version`) | desk.approvals only |
| `outbound` | message id | `OutboundMessage` (approved advisories; approved messages, with `advisory_id` set to the message id) | desk.approvals, comms.messages |
| `audit` | entry id | `ChainedAuditEntry` (append-only, hash-chained) | desk.audit only |
| `feed_state` | FeedId value | `FeedHealth` | core (throttled; when status, error or record count changes, not for `age_s`, `last_attempt_at` or `last_success_at` alone, so a restored `last_success_at` may be older than the true one) |
| `runtime` | `writer` | `{revision, instance, at}`: the instance that ticked last (the writer fence, section 5.7) | core (every tick) |
| `runtime` | `state` | core bookkeeping: `mode`, `auto_replay`, `case_id` (read at startup to resume a replay), `quiet_ticks`, `planned` (`{flight_id: [cone_id, urgency]}`), `closed_airports`, `assessment_ids` (read back after a LIVE restart), `saved_at` | core (first at every checkpoint, and at every mode switch) |
| `ai_budget` | `<quota day>/<model id>` | `ModelDay`: that model's calls per lane on that Google quota day, and whether Google closed it | `agents.quota` (one transaction per HTTP attempt, before it is sent) |
| `ai_work` | work id (a Duty item id, or `recover`) | `AiWork`: AI work queued, running or WAITING for budget with its next slot | core (`tephra.ai_worker`, on change; restored after a LIVE restart) |
| `ai_answers` | 32 hex (hash of `KEY_VERSION`, mode, case, model, skill and material; no build) | `AiAnswer`: a model's answer that passed the code's checks, for the same material question (`expires_at` is the sweep's field: `ai_answer_keep_h` in LIVE, `ai_answer_replay_keep_h` in REPLAY) | core (`tephra.agents.answers`; a newer answer replaces it; swept every ten minutes; in Firestore only `expires_at` is indexed) |
| blobs | `frames/*.png`, `btd/*.png` | PNG bytes | core |

Documents are strict JSON (`tephra.store.encode_doc`): NaN and infinities are stored as null.

A failed write of a feed record (`sigmets`, `vonas`, `vaas`, `tafs`, `metars`, `winds`) never
fails the poll: the record is already in memory, its `(collection, doc id)` waits in
`Runtime.unsaved`, and the next checkpoint writes the record held then (or drops the key when
the picture no longer holds it). Each checkpoint write is tried on its own.

## 8. HTTP API (api implements, web consumes)

All JSON bodies are the named models dumped with `model_dump(mode="json")` (datetimes as
`2026-10-07T10:32:00.000Z`). They live in `tephra/models.py`, except the API-only `Health`,
`FeedList`, `ReplayCaseSummary`, `ReplayCaseList` and `ModeRequest` in `tephra/api/server.py`.
Errors are `ErrorBody` with these `error` codes:
`bad_request` (400), `bad_pin` (401), `unauthenticated` (401), `forbidden` (403),
`not_found` (404), `method_not_allowed` (405), `version_conflict` (409, `current` set),
`invalid_transition` (409), `reason_required` (422, `problems` set: approving a CONTINUE or
MONITOR for a flight a crew report flags without a written reason), `too_large` (413; a body over `MAX_BODY_BYTES`, 16 KiB, except
`POST /api/desk/notices` at 32 KiB and `POST /api/desk/ask/voice` at `max_upload_bytes`), `validation_failed` (422, `problems` set),
`too_many_attempts` (429, `Retry-After`), `internal` (500), `desk_disabled` (503),
`starting` (503; the runtime is not ready), `too_many_streams` (503, `Retry-After: 5`),
`ai_unavailable` (503; `detail` and, on the feature routes, `message` read `AI UNAVAILABLE:
<reason>`; nothing is substituted), and the feature errors of section 8.7. A
request validation error from FastAPI is reshaped into `validation_failed`, with locations
and messages only (the input may be a PIN). No error body carries a stack trace or echoes
request input.

### 8.1 Pages and static files

| Method, path | Response |
|---|---|
| `GET /` | `tephra/web/index.html` |
| `GET /assistant` | `tephra/web/index.html` again: `page-mode.js` marks it `data-page="assistant"` and `wall.js` shows the TEPHRA Assistant board in place of the Wall (UI-DESIGN 7.27) |
| `GET /desk` | `tephra/web/desk.html` |
| `GET /privacy` | `tephra/web/privacy.html`, the privacy notice (linked from the guide's foot, the Desk sign-in and README) |
| `GET /guide` | `tephra/web/guide.html`, the guide: how to read the map, the words used, the keyboard, About and credits, and the operator policy (linked from the Wall footer, `?` and the map key) |
| `GET /robots.txt` | `text/plain`: `User-agent: *` and `Disallow: /`; every page also carries `<meta name="robots" content="noindex, nofollow">` |
| `GET /static/{path}` | files under `tephra/web/` (`wall.js`, `wall.css`, `desk.js`, `desk.css`, `favicon.svg` (the icon every page links), ...) |
| `GET /health`, `GET /healthz` | `{"ok": true, "mode": "LIVE"}`; probe `/health` on Cloud Run, which reserves `/healthz` |

Every response carries:
`Content-Security-Policy: default-src 'self'; script-src 'self'
https://unpkg.com/maplibre-gl@4.7.1/ https://unpkg.com/@maplibre/maplibre-gl-compare@0.5.0/;
style-src 'self' https://unpkg.com; img-src 'self' data: blob: https://tiles.openfreemap.org
https://gibs.earthdata.nasa.gov https://tiles.mapterhorn.com; connect-src 'self'
https://tiles.openfreemap.org https://gibs.earthdata.nasa.gov https://tiles.mapterhorn.com;
media-src 'self' blob:; worker-src 'self' blob:; child-src blob:; font-src 'self';
frame-ancestors 'none'; base-uri 'none'; form-action 'self'`, plus `X-Content-Type-Options: nosniff`, `Referrer-Policy:
no-referrer`, `X-Frame-Options: DENY`, `Permissions-Policy: camera=(), microphone=(),
geolocation=()` (`microphone=(self)` on `GET /desk` only, for push-to-talk), `Cache-Control: no-store` under `/api/` and `no-cache` elsewhere (unless the
route sets its own), and `Strict-Transport-Security: max-age=31536000` over https.

Responses of 1024 bytes or more are gzip-compressed when the client sends
`Accept-Encoding: gzip` (Starlette `GZipMiddleware`, which adds `Vary: Accept-Encoding`). Its
default exclusions keep `text/event-stream` (the SSE stream, 8.4), images and fonts as they are.
The headers above are unchanged by compression.

### 8.2 Read endpoints (public, read-only)

| Method, path | Response model |
|---|---|
| `GET /api/state` | `SystemState` (`store`: `StoreHealth`; `draft_count` null when the drafts could not be read); besides the picture's counts it carries `server_time` (wall clock), `last_tick_wall_at` (wall-clock end of this process's last tick, `null` until its first) and `build_sha` (`TEPHRA_BUILD_SHA`), which `scripts/live_smoke.sh` checks. `/healthz` stays exactly `{ok, mode}` |
| `GET /api/wall` | `WallResponse` = `{state: SystemState, snapshot: WallSnapshot, advisories: [Advisory] (every open draft of the mode playing, newest first, then that mode's newest other advisories, 50 in all unless the drafts alone are more: in REPLAY `created_at` follows a clock that loops, so the store's newest 50 could hide this run's drafts), trace: [TraceEvent] (last 100, oldest first)}` |
| `GET /api/advisories?status=DRAFT&limit=50` | `AdvisoryList` (newest first; every status when `status` is absent) |
| `GET /api/audit?advisory_id=...&limit=100` | `AuditList` (newest first; `advisory_id` must match `adv_[0-9a-f]{12}`) |
| `GET /api/outbound?limit=50` | `OutboundList` (newest first by `queued_wall_at`, so recorded and live rows never interleave by replay time; rows whose `queued_wall_at` is null come last; Firestore leaves out records written before the field, which lack the key) |
| `GET /api/feeds` | `FeedList` = `{feeds: [FeedHealth]}` (ages as of now) |
| `GET /api/policy` | `PolicyResponse` = `{policy: OperatorPolicy, policy_hash}`: the active operator policy and its `content_hash()` |
| `GET /api/replays` | `ReplayCaseList` = `{cases: [ReplayCaseSummary]}`: each recorded case without its records (`case_id`, `label`, `recorded_from`, `recorded_to`, `region`, `volcano_ids`, `notes`, `record_count`, `banner`). Built once per app in the lifespan (`ReplayCatalogue` on `app.state.replays`: summaries, serialised bytes, strong `ETag` = quoted sha256 of the bytes); a manifest that cannot be read fails startup. Served with `Cache-Control: no-cache` and the `ETag`; a matching `If-None-Match` answers 304 with no body |
| `GET /api/routes/{origin_icao}/{dest_icao}` | FeatureCollection (`RouteFeatureProps`, `routes.route_features`): the great circle between two airports and a Point at each end, for the route of a flight picked on the Wall that is not in `WallSnapshot.routes` (the line's id is the pair in alphabetical order, whichever order is asked). Which airports a flight flies between comes only from `AircraftFeatureProps`; this answer depends only on the two positions, so it is sent with `Cache-Control: public, max-age=86400`. 404 `not_found` for a code that is not 4 capitals or digits, the same airport twice, or an airport with no known position |
| `GET /api/airports` | FeatureCollection of the airport catalogue (`data/airports.json`, `Airport`): a Point per airport with `icao`, `iata`, `name`, `country`, `longest_runway_m` (feature id the ICAO code), for the maps to place the airports an airport plan closes. The catalogue changes only with a deploy: `Cache-Control: public, max-age=3600` |
| `GET /connect` | `tephra/web/connect.html`, TEPHRA Connect (UI-DESIGN 7.24) |
| `GET /api/connect/format` | `FormatInfo` `{format, max_positions, fresh_s, push_url, schema}`: the push format `tephra.positions/1` and its JSON Schema |
| `GET /api/connect/schema.json`, `GET /api/connect/sample.json` | Downloads (`Content-Disposition: attachment`): the JSON Schema, and an example push of 12 real recorded flights (`sample_feed`) at their recorded fixes, timed on the active clock now, accepted as it is for `PUSH_FRESH_S` |
| `GET /api/connect/live` | `ConnectLive` `{wall_at, sample_running, sample_connection_id, flows: [ConnectFlow], dots: [PushedDot], recent: [PushSummary]}`: the pushed flights updated in the last 60 s, each connection's positions / min and 5-minute sparkline (wall clock), the newest 14 pushes; public, so a reload of the page starts complete |
| `POST /api/desk/upload` | `Upload` (`PositionBatch` plus `retime`, default true: stamp every record with the active clock) -> `PushResult`, through the "Uploaded files" connection (made the first time); desk session, CSRF |
| `GET /api/desk/connections` | `ConnectionList` `{connections: [ConnectionView], sample_running, sample_connection_id}` (desk session) |
| `POST /api/desk/connections` | `{name}` -> `ConnectionView` with `key`, the only time the key is shown; audit `CONNECTION_CREATED` (desk session, CSRF) |
| `POST /api/desk/connections/{id}/revoke` | `ConnectionView`; the key stops working at once; audit `CONNECTION_REVOKED`; stops the sample feed when it is the sample connection (desk session, CSRF) |
| `POST /api/desk/sample-feed` | `{on}` -> `ConnectionList`: starts or stops the sample feed (desk session, CSRF) |
| `POST /api/push/positions` | `PositionBatch` `{format: "tephra.airline/1" or "tephra.positions/1", positions, flight_plans, pilot_reports}` (at most 1000, 1000 and 20) with `Authorization: Bearer <key>` -> `PushResult` `{connection_id, received_at, accepted, rejected: [{section, index, reason}], in_ash, plans_taken, reports_taken, closed_hits}`. 401 without a live key; 429 `too_many_pushes` faster than one a second. Each record is checked alone: a position must have `observed_at` within `PUSH_FRESH_S` (300 s) before, or 120 s after, the active clock |
| `GET /api/blobs/{key}` | PNG bytes; `key` must match `BLOB_KEY_PATTERN` (else 404); `Cache-Control: public, max-age=86400, immutable` |
| `GET /api/duty?limit=10` | `DutyRunList` `{runs: [DutyRun]}`, current mode (in REPLAY, the replay run playing), newest first (`limit` 1 to 20) |
| `GET /api/budget` | `BudgetView` `{backend, as_of, quota_day, resets_at, models: [{model_id, jobs, used, limit, free_limit, remaining, closed, lanes: [{lane, words, used, share}], routine_allowed_now, next_routine_slot, pacing}], tiers: [{tier, model_id, used, limit, remaining}], waiting: [AiWork], note}` |
| `GET /api/notices?limit=` | `{notices: [NoticeReading]}`, current mode, newest first; includes the JMA volcano reports of the live picture (`JMA-` VONA records) as `source_kind "jma_xml"`, language `ja`, verified, no model |
| `GET /api/recovery?limit=` | `{plans: [RecoveryPlan]}`, current mode, newest first |
| `GET /api/docs?kind=&limit=` and `GET /api/docs/{DOC-id}` | `{docs: [DocSummary]}`; `SraDraft`, `VarDraft` or `CrewMessageDraft` |
| `GET /api/backtest` | `BacktestScorecard` (the store's `backtest/latest`, else `docs/backtest/scorecard.json`); 404 `not_found`, 503 `unavailable` |
| `GET /api/events` | `text/event-stream` (section 8.4); 503 `too_many_streams` while `TEPHRA_MAX_EVENT_STREAMS` streams are open |
| `GET /api/audit/verify` | `ChainHead` `{seq, sha256, checked_at, entries, intact, problems}`: the audit chain's head as this instance last verified it (count and hash only; public); `problems` names a broken link |
| `GET /api/advisories/{id}/chain` | the reasoning chain behind one advisory: the Coordinator run, the plume read, the plan and the draft that led to it, each with the source it leaned on, its tool calls, repair count and the code's checks; 404 `not_found` |
| `GET /api/evals` | the published evaluation results (`docs/evals/*.json`): the backtest scorecard and the plume scorecard with its INCOMPLETE state where true; 404 `not_found` when none is published |

`limit` is 1 to 200 everywhere.

`SystemState.replay` is a `ReplayInfo` (`case_id`, `label`, `recorded_from`, `recorded_to`,
`banner`, `auto`, `window_from`, `window_to`). `window_from` and `window_to` are null unless
the replay loops over a configured window (`TEPHRA_REPLAY_START` to `TEPHRA_REPLAY_END`); the
Wall's timeline then shows `Replay loops 1028Z-1058Z` and its progress through the loop.

### 8.3 Wall snapshot sections

`WallSnapshot.volcanoes`: FeatureCollection of `Point` with `VolcanoFeatureProps`
(catalogue volcanoes in all regions; `color_code` from the latest VONA/VAA, else UNKNOWN).
`official`: `OfficialLayer.to_feature()` for every layer of every active situation.
`cones`: `HazardCone.to_features()` (parts `cone` and `sector`).
`exposures`: per exposed flight a `LineString` (`kind: "path"`) and a `Point` at the entry
(`kind: "entry"`) with `ExposureFeatureProps`.
`reroutes`: per lateral option with a path, a `LineString` (`feature: "path"`, id `<option id>#path`)
and a `Point` per turn point (`feature: "waypoint"`), with `RerouteFeatureProps` (`flight_id`,
`proxy_flight`, `volcano_id`, `kind`, `status`, `route_string`, `extra_nm`, `extra_min`, `side`,
`label`, `waypoint_labels`).
`routes`: the usual route (`RouteTable.lookup`, VRS standing data, never the filed flight plan)
of each RFA flight in or heading into an area, computed by code at every publish:
`RouteFeatureProps` (`feature` `line` | `airport`, `ends` (line: the two codes, alphabetical),
`icao` (airport), `hexes`, `source`), from `routes.route_features`. One line per pair of airports
(flights on the same pair share it, in either direction; id `<a>-<b>`), one Point per airport. A
flight's direction is in `AircraftFeatureProps.origin_icao` and `dest_icao`. A flight whose leg is
not found has no line: no route is guessed.
`satellite`: the newest `SatelliteReading` of each active volcano that has one.
`crew`: `CrewPicture` `{label, reports: [CrewReportView], flags: [CrewFlag], features}`
(section 5.19). `features` is a FeatureCollection with `CrewFeatureProps` (`report_id`,
`feature` `area` | `pin` | `path`, `state`, `label`, `flight`, `volcano_id`, `age_text`, `base_ft`,
`top_ft`, `valid_to`, `replay`): an `area` Polygon and a `pin` Point per ACTIVE or COVERED
report (ids `<report id>#area`, `#pin`) and a `path` LineString per flagged flight
(`<hex>#crew-path`). The crew area is drawn beneath the official areas and never replaces one.
`duty`: the newest `DutyRun` (or null).
`aircraft`: `Point` per merged aircraft with `AircraftFeatureProps` (`exposed`,
`minutes_to_entry` and `volcano_id` from the earliest exposure; `crew_report` when a crew report
area flags it; `origin_icao` and `dest_icao`, the usual route from `RouteTable.lookup` for an
airline callsign flying along a leg of it, else null).
`situations`: `SituationCard` per active volcano (cards exactly `[SIGMET, VONA, VAA]`).
`overlays`: `BtdOverlay` per active volcano with a BTD result (`image_url =
blob_url(image_key)`, `corners = bbox.corners_lonlat()`), `FrameThumb` per stored frame.

### 8.4 Server-Sent Events (`GET /api/events`)

Framing: `id: <int>\nevent: <name>\ndata: <json>\n\n`; first line `retry: 3000`. A client
whose 256-event queue has dropped events is disconnected before anything newer is sent. The
browser reconnects with `Last-Event-ID`, and the server first replays the newer events still
in the bus history (200 per event name). A gap older than that history is not replayed: the
Wall resyncs from `/api/wall` and the Desk reloads its list when the stream reopens.

| `event` | `data` | Client action |
|---|---|---|
| `state` | `SystemState` (its `feeds` is the feed health) | replace top bar state and feed health |
| `volcanoes` | FeatureCollection | replace layer |
| `official` | FeatureCollection | replace layer |
| `cones` | FeatureCollection | replace layer |
| `exposures` | FeatureCollection | replace layer |
| `aircraft` | FeatureCollection | replace layer |
| `reroutes` | FeatureCollection | replace layer |
| `routes` | FeatureCollection (`WallSnapshot.routes`) | replace layer |
| `overlays` | `Overlays` | replace overlays |
| `situation` | `SituationCard` | upsert card by `volcano_id` |
| `trace` | `TraceEvent` | append (keep last 200) |
| `advisory` | `Advisory` | upsert by `id` (Wall list and Desk cards) |
| `ai_failure` | `AiFailure` | upsert by `id` (Desk queue) |
| `satellite` | `SatelliteReading` | upsert by `volcano_id` |
| `notice` | `NoticeReading` | upsert by `id` |
| `recovery` | `RecoveryPlan` | upsert by `id` |
| `message` | `CrewPaxMessage` | upsert by `id` |
| `doc` | `DocSummary` (`kind` SRA, VAR, CREW_MESSAGE or HANDOVER; status DRAFT, SIGNED, ACKNOWLEDGED or WITHDRAWN) | upsert by `id`; a HANDOVER summary tells the Desk to refetch `/api/desk/handovers` |
| `budget` | `BudgetView` | replace the AI budget chip |
| `duty` | `DutyRun` | replace the Duty Officer panel and the Desk's brief card |
| `crew` | `CrewPicture` | replace the crew report areas, their list and the flags (Wall and Desk) |
| `push` | `PushSummary` | the Connect page: a push taken (its connection, counts, up to 3 refusal reasons, the positions as dots with `in_ash`) |
| `heartbeat` | `{"now": iso, "mode": "LIVE"}` (no `id`) | update clock |

Core publishes `state`, `volcanoes`, `situation`, `official`, `cones`, `exposures`,
`reroutes`, `routes`, `aircraft`, `overlays`, `crew`, `trace`, `advisory`, `ai_failure`, `satellite`, `recovery`
and `budget` (the Wall layers only when they changed, section 5.7); the feature routes publish
`notice`, `message`, `doc` and `budget` (after a model call) too. The SSE endpoint sends
`heartbeat`. NaN and infinities in a payload are sent as null. There is no `feeds` event:
`state.feeds` carries the feed health.

`SseEvent.END_STREAMS` (`end_streams`) is never sent: on the bus it ends every open stream at
once (no frame), so the browser reconnects. Core publishes it when the runtime retires and
when ticks stop arriving (section 5.7). It is not replayed from the history.

The Wall closes its stream after its tab has been hidden for 5 minutes (no lost banner) and,
when the tab is shown again, resyncs from `/api/wall` and opens a new stream. A visible Wall
never pauses. The Desk keeps its stream open while hidden: its tab title counts new drafts.

### 8.5 Desk endpoints (cookie session; CSRF guard on every POST)

| Method, path | Request | Response |
|---|---|---|
| `POST /api/desk/login` | `LoginRequest` `{pin (1-64 chars), name}` | 200 `SessionInfo` + `Set-Cookie`; 401 `bad_pin`; 429 `too_many_attempts` with `Retry-After`; 422 `validation_failed` for a name that is not 2 to 32 letters, digits, spaces or `. ' - _`; 503 `desk_disabled` |
| `POST /api/desk/logout` | none | 204, cookie cleared (the CSRF guard applies, also when the desk is disabled) |
| `GET /api/desk/me` | none | `SessionInfo`, 401 or 503 `desk_disabled` |
| `GET /api/desk/advisories?status=DRAFT&limit=50` | none | `AdvisoryList` (default status DRAFT, newest first) |
| `POST /api/desk/advisories/{id}/approve` | `DecisionRequest` `{version, reason?}` | `Advisory` (APPROVED); 409 `version_conflict`/`invalid_transition`; 404; 422 `reason_required` |
| `POST /api/desk/advisories/{id}/edit` | `EditRequest` `{version, body, reason?}` | `Advisory` (EDITED); 422 `validation_failed` (empty, or over 400 characters once stripped and upper-cased); 422 `reason_required` |
| `POST /api/desk/advisories/{id}/reject` | `RejectRequest` `{version, reason (3-500 chars)}` | `Advisory` (REJECTED); 422 when the reason is too short |
| `GET /api/desk/ai-failures?open_only=true&limit=50` | none | `AiFailureList`: flights the AI could not plan or draft for, in the current mode (in REPLAY, the replay run playing), newest recorded first; open means neither handled nor closed by code |
| `POST /api/desk/ai-failures/{id}/handled` | `HandledRequest` `{note}` | `AiFailure` with `handled_by`, `handled_at`; marking twice keeps the first, and a failure code closed meanwhile is returned unchanged (no `handled_by`); 404. The Desk's "Mark several handled" sends one request per ticked flight, so each is its own audit entry |
| `POST /api/desk/visitor` | `{name}` (2-32 characters, as `LoginRequest.name`) | 200 `SessionInfo` with `role: visitor` + `Set-Cookie`; no PIN. Only while `TEPHRA_VISITOR_ACCESS=replay` and a replay plays: 403 `visitor_off` otherwise, 409 `visitor_replay_only` in LIVE, 429 `too_many_visitors` past the open-session cap. Audit `VISITOR_ENTERED` under `visitor:<name>` |
| `POST /api/desk/replay/restart` | none | `SystemState`: the replay starts again from its window's start (same case, same quantum); audit `REPLAY_RESTARTED`; 409 `not_replay` in LIVE, 429 `restart_too_soon` with `Retry-After` inside the restart interval |
| `POST /api/mode` | `ModeRequest` `{mode, case_id?}` | `SystemState` after the switch. REPLAY plays `case_id` (404 `not_found` when there is no such case), else the case playing, else the newest recorded case (409 `invalid_transition` when none exists). Writes a `MODE_SWITCH` audit entry with the dispatcher as actor, beside the runtime's own entry for a switch that happens. A tick in progress is stopped, not waited for (`Runtime.switch_mode(preempt=True)`; its report is skipped with the note "stopped: a mode switch at the Desk ended this tick"): a LIVE tick can wait minutes on public feeds. |

The CSRF guard (`auth.require_csrf`, 403 `forbidden`) refuses a cross-site `Sec-Fetch-Site`
or `Origin`, and any POST with neither a JSON body nor `X-Tephra-Desk: 1`. `desk_disabled`
(503) is answered by `POST /api/desk/login` and by every endpoint that needs a session
(`GET /api/desk/me`, `GET /api/desk/advisories`, approve, edit, reject, `POST /api/mode`)
when `TEPHRA_DESK_PIN` is unset or blank (also when the session secret is blank, which
config prevents). It comes after the CSRF guard (403) and before body or query validation
(422); the exception is malformed JSON, which FastAPI rejects with 422 before any dependency
runs. An advisory id that does not match `adv_[0-9a-f]{12}` answers 404. Approve and edit of a
CONTINUE or MONITOR draft of the current mode whose flight (`hex`) a crew report area flags now
(`Runtime.crew_flag`; every tracked flight is airborne) need `reason`, at least 12 characters
(`approvals.MIN_CREW_REASON_CHARS`) once
whitespace is collapsed, else 422 `reason_required` ("Crew report of ash on this route: approving
MONITOR needs a written reason"); the reason is kept as `Advisory.decision_reason` and the audit
note names the reports. Any other approval keeps a reason it is given. The actor recorded
is `desk:<SessionInfo.name>`, or `visitor:<SessionInfo.name>` for a visitor session.

Visitor sessions (`SessionInfo.role == "visitor"`) make real, audited decisions in REPLAY only,
capped per session (`sid`): 403 `visitor_role` on `POST /api/mode`, the sample feed,
connections, upload and notices; 409 `visitor_replay_only` on any decision in LIVE; 429
`visitor_cap` past `TEPHRA_VISITOR_DECISION_CAP` decisions and 429 `visitor_ask_cap` past
`TEPHRA_VISITOR_ASK_CAP` Ask questions. The decision guard applies to every session: 409
`rule_blocked` when the rules refuse the action (a DIVERT or REROUTE in HYPOTHESIS mode) and
409 `cone_changed` when the situation the draft was made for has changed (Reject stays open).

### 8.6 Task endpoint

`POST /tasks/tick` with header `X-Tephra-Task-Token: <TEPHRA_TASK_TOKEN>` -> 200 `TickReport`
(with `skipped=true` and the note `busy: another tick is still running` if a tick is already
running); 403 `forbidden` when the header is missing or wrong or the token is unset or
blank. Cloud Scheduler calls it every minute.

### 8.7 Feature endpoints (mounted under `/api` by `create_app`)

All are Desk routes (session; every POST needs the CSRF guard); the public ones are in 8.2. A model
failure is HTTP 503 `{"error": "ai_unavailable", "message": "AI UNAVAILABLE: <reason>", "detail":
<same>, "problems": []}`. The actor recorded is `desk:<name>`.

| Method, path | Request | Response |
|---|---|---|
| `POST /api/desk/ask` | `{question (1-500 chars), flight_id?}` | `AskAnswer`; 503 |
| `POST /api/desk/ask/voice` | multipart: `audio` (at most 1 MiB, audio mime types), `flight_id?` | `{transcript, answer}`; 413 over the cap; 503 (`problems` holds `transcript: <text>` when only the answer failed) |
| `POST /api/desk/ask/speak` | `{answer_id: ask_<12 hex>}` | `audio/wav`; 404 unknown answer; 503 |
| `POST /api/desk/notices` | `{text (20-6000 chars)}` | `NoticeReading`; a verified one joins the live picture; a repeat paste is answered from the store; 422; 503 |
| `POST /api/desk/recovery/run` | `{closures: [{icao, start, end, reference}]}` (optional dispatcher-entered closures) | `RecoveryPlan` (DRAFT); 409 `no_closure`, `busy`; 422; 503 `schedule_unavailable` and `ai_unavailable` |
| `POST /api/desk/recovery/{id}/approve`, `.../reject` | `{version}`, `{version, reason}` | `RecoveryPlan`; 404, 409 `version_conflict`, `invalid_transition` |
| `GET /api/desk/messages?status=&limit=` | none | `{messages: [CrewPaxMessage]}`, current mode |
| `POST /api/desk/messages/draft` | `{advisory_id}` or `{recovery_id}` | `{messages: [...]}`; 409 `source_not_approved`, `source_unusable`; 503 |
| `POST /api/desk/messages/{id}/approve`, `.../edit`, `.../reject` | `{version}`, `{version, bodies: {lang: text}}`, `{version, reason}` | `CrewPaxMessage`; 409 `version_conflict` (`current` set), `invalid_transition`; 422 |
| `POST /api/desk/handover` | `{since, incoming, outgoing?}` | `HandoverBrief` (`outgoing` defaults to the session name); 503 |
| `GET /api/desk/handovers?limit=` | none | `{handovers: [HandoverBrief]}`, current mode, latest first |
| `GET /api/desk/handover/{ho_id}` | none | `HandoverBrief` |
| `GET /docs/{DOC-id or ho_id}` | none | the printable page `web/doc.html` (same headers as the other pages); 404 for any other id |
| `POST /api/desk/handover/{ho_id}/ack` | none (send `X-Tephra-Desk: 1`) | `HandoverBrief` with `receiver_ack`; open drafts are recorded, not refused |
| `POST /api/desk/docs/sra` | `{region}` | `SraDraft`; 404 unknown region; 409 `no_active_volcano`; 503 |
| `POST /api/desk/docs/var` | `{flight_id}` | `VarDraft`; 404 flight not exposed |
| `POST /api/desk/docs/{DOC-id}/sign` | `{name, role}` | the document; 409 `invalid_transition` (role already signed); 422 |
| `GET /api/desk/crew-reports` | none | `CrewPicture` (the current mode; the same as `WallSnapshot.crew`) |
| `GET /api/desk/crew-reports/fix?observed_at=&hex=` or `&callsign=` | none | `FixLookup`: the ADS-B fix within 90 s that an entry would use (`found`), or why none; 422 (an `observed_at` in the future or older than `valid_min` is refused here first) |
| `POST /api/desk/crew-reports` | `CrewEntry` `{hex \| callsign, cues: [ASH_SEEN, SULPHUR_SMELL, HAZE, ST_ELMOS_FIRE, ENGINE, NO_ASH_SEEN], level_from_fl, level_to_fl?, observed_at, lat?, lon?, remarks? (300)}` | `CrewReportView`; 422 `validation_failed` with every problem (section 5.19); writes `CREW_REPORT_ENTERED`, publishes `crew` and `aircraft` |
| `POST /api/desk/crew-reports/{CR-id}/withdraw` | `{reason (3-500 chars)}` | `CrewReportView` (WITHDRAWN); 404; 409 `invalid_transition` when already withdrawn; writes `CREW_REPORT_WITHDRAWN` and withdraws every message drafted from it (`DOC_WITHDRAWN`) |
| `POST /api/desk/crew-reports/{CR-id}/message` | none (send `X-Tephra-Desk: 1`) | `CrewMessageDraft` (the message to the weather office and the VAAC, section 5.16; nothing is sent); 404; 409 `invalid_transition` (not an ASH report, withdrawn, or not in the current picture) |
