# TEPHRA module contract

This file is the contract that every module is coded against in parallel. If your code
needs something from another module, call it exactly as written here. If something you
need is missing, write a private helper inside your own files; do not edit files you do
not own. Shared shapes live in `tephra/models.py`; settings and constants in
`tephra/config.py`. Read both before you start: their docstrings are part of this contract.

Background reading: `docs/ARCHITECTURE.md` (the system and its safety rules) and the
research notes in `research/` (read-only). Research that changed this contract:
`research/06` (free-tier quota, ADK 2.x), `research/07` (parsing and dispatch rules),
`research/12` (raw Himawari split window), `research/13` (what counts as a contradiction,
Darwin VAAC source).

## 1. Where things live

| Area | Files |
|---|---|
| architect (contract, do not edit) | `pyproject.toml`, `MODULES.md`, `CLAUDE.md`, `docs/ARCHITECTURE.md`, `tephra/__init__.py`, `tephra/config.py`, `tephra/models.py`, `tephra/feeds/__init__.py`, `tephra/feeds/base.py`, `tephra/store/base.py`, `tephra/util/__init__.py`, `tephra/util/timeutil.py`, `tephra/util/hashing.py`, `tephra/util/events.py` |
| feeds-text | `tephra/feeds/sigmet.py`, `tephra/feeds/vona.py`, `tephra/feeds/vaac.py`, `tephra/feeds/taf.py`, `tests/test_feeds_text.py` |
| feeds-geo | `tephra/feeds/adsb.py`, `tephra/feeds/winds.py`, `tephra/feeds/satellite.py`, `tephra/feeds/volcanoes.py`, `tephra/feeds/airports.py`, `data/volcanoes.json`, `data/airports.json`, `tests/test_feeds_geo.py` |
| science | `tephra/science/__init__.py`, `tephra/science/hsd_segments.py`, `tephra/science/btd.py`, `tests/test_science.py` |
| geo | `tephra/geo/__init__.py`, `tephra/geo/units.py`, `tephra/geo/cone.py`, `tephra/geo/exposure.py`, `tephra/geo/fuel.py`, `tests/test_geo.py` |
| reconcile-plume | `tephra/reconcile/__init__.py`, `tephra/reconcile/discrepancies.py`, `tephra/agents/__init__.py`, `tephra/agents/llm.py`, `tephra/agents/schemas.py`, `tephra/agents/plume_reader.py`, `tephra/agents/prompts/plume_reader.md`, `tests/test_discrepancies.py`, `tests/test_plume_reader.py` |
| planner-drafter | `tephra/agents/exposure_planner.py`, `tephra/agents/dispatch_drafter.py`, `tephra/agents/validators.py`, `tephra/agents/adk_app.py`, `tephra/agents/prompts/planner.md`, `tephra/agents/prompts/drafter.md`, `tests/test_drafter.py` |
| core | `tephra/pipeline.py`, `tephra/scheduler.py`, `tephra/feeds/registry.py`, `tephra/store/__init__.py`, `tephra/store/sqlite_store.py`, `tephra/store/firestore_store.py`, `tephra/desk/__init__.py`, `tephra/desk/approvals.py`, `tephra/desk/audit.py`, `tephra/replay/__init__.py`, `tephra/replay/cases.py`, `tests/test_approvals.py`, `tests/test_pipeline_stub.py`, `tests/test_store.py` |
| api | `tephra/main.py`, `tephra/api/__init__.py`, `tephra/api/server.py`, `tephra/api/auth.py`, `tephra/api/sse.py`, `tests/test_api.py` |
| web-wall | `tephra/web/index.html`, `tephra/web/wall.js`, `tephra/web/wall.css` |
| web-desk | `tephra/web/desk.html`, `tephra/web/desk.js`, `tephra/web/desk.css` |
| ops-evals | `Dockerfile`, `.dockerignore`, `.env.example`, `deploy/cloudrun.sh`, `deploy/scheduler.sh`, `deploy/secrets.sh`, `deploy/firestore.rules`, `deploy/README.md`, `.github/workflows/ci.yml`, `scripts/record_replay.py`, `scripts/count_traffic.py`, `scripts/plume_eval.py`, `scripts/make_plume_cases.py`, `evals/plume/README.md`, `evals/plume/cases.example.json`, `evals/drafter/advisories.test.json`, `data/replay/README.md` |

Each module may also create test fixtures under `tests/fixtures/<module_key>/` (e.g.
`tests/fixtures/feeds_text/`). There is **no shared `tests/conftest.py`**: each test file
defines its own fixtures. Fixtures may be copied from `research/data/census/raw/` or typed
from texts quoted in `research/13`.

## 2. Layering (who may import whom)

Import only from a lower layer (or from your own files in the same layer).

| Layer | Modules |
|---|---|
| L0 | `tephra.util.*`, `tephra.models`, `tephra.config` (config imports models; models never import config) |
| L1 | `tephra.feeds.base`, `tephra.store.base`, `tephra.geo.*` |
| L2 | `tephra.feeds.{sigmet,vona,vaac,taf,adsb,winds,satellite,volcanoes,airports}`, `tephra.science.*` |
| L3 | `tephra.reconcile.*`, `tephra.agents.llm`, `tephra.agents.schemas` |
| L4 | `tephra.agents.{plume_reader,validators,exposure_planner,dispatch_drafter,adk_app}` |
| L5 | `tephra.store.{sqlite_store,firestore_store}` and `tephra.store` (the factory), `tephra.desk.*`, `tephra.replay.*` |
| L6 | `tephra.feeds.registry`, `tephra.pipeline`, `tephra.scheduler` |
| L7 | `tephra.api.*`, `tephra.main` |

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
Only composition roots call `get_settings()`: `tephra.api.server`, `tephra.pipeline.create_runtime`,
`scripts/*`. Tests build `Settings(_env_file=None, **overrides)`; they never read `.env`.

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
| Sigmet | `SIGMET:{fir_id}:{series_id}:{compact(valid_from)}` | `SIGMET:WAAF:12:20261007T1030Z` |
| Vona | `VONA:{source_slug(volcano_name)}:{compact(issued_at)}` | `VONA:SEMERU:20260923T2221Z` |
| VaacAdvisory | `VAA:{vaac}:{volcano_number or source_slug(volcano_name)}:{advisory_nr}` | `VAA:TOKYO:282080:2026/249` |
| Taf | `TAF:{icao}:{compact(issued_at)}` | `TAF:WARR:20261010T0500Z` |
| Metar | `METAR:{icao}:{compact(observed_at)}` | `METAR:WARR:20261010T0530Z` |
| AdsbSnapshot | `ADSB:{lat:.3f}:{lon:.3f}:{compact(fetched_at, seconds=True)}` | `ADSB:-8.200:113.600:20261010T053012Z` |
| WindProfile | `WINDS:{lat:.2f}:{lon:.2f}:{compact(valid_at)}` | `WINDS:-8.11:112.92:20261010T0600Z` |
| SatelliteFrame | `FRAME:{product}:{volcano_id}:{compact(observed_at)}` | `FRAME:DUST_RGB:263300:20261010T0530Z` |
| BtdResult | `BTD:{volcano_id}:{compact(scan_start)}` | `BTD:263300:20261010T0530Z` |

Other ids use `stable_id(prefix, *parts)` (deterministic) as each model's field description
says: discrepancies `D-` (8 chars), assessments `PA-`, cones `CONE-`, plans `PLAN-`, dedupe
keys `DD-`. Advisory ids are `"adv_" + uuid4().hex[:12]`; audit and outbound ids are
`uuid4().hex`.

**Errors.** Feed fetchers let `FetchError` propagate (the registry records it). Parsers raise
`ValueError` for input they cannot read; a fetcher that parses many items skips a bad item,
logs it with `logging.getLogger(__name__).warning`, and keeps the rest. Agents never raise
on model failure: they repair once and then fall back (sections 5.5 and 5.6).

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
audit entries, no registrations. Only aircraft with airline-style callsigns
(`Aircraft.airline`) become proxy flights.

## 4. Contract files (already written; read them)

### 4.1 `tephra.util.timeutil`

`UTC`, `ensure_utc(dt)`, `now()`, `get_clock()`, `set_clock(clock)`, `use_clock(clock)`;
clocks `SystemClock()`, `FixedClock(at)` (`.set`, `.advance`), `ReplayClock(start, end, *,
speed=1.0, loop=True)`. Parsers: `parse_slash_dtg("20260923/2221Z")`,
`parse_day_time("25/1800Z", ref)`, `parse_ddhhmm("251252", ref)`, `parse_hhmmz("1010Z", ref)`,
`resolve_day(day, hour, minute, ref)` (hour 24 accepted), `parse_iso(str | int | float |
datetime)` (naive = UTC, epoch s or ms). Formatters: `to_iso(dt)` ->
`2026-10-07T10:32:00.000Z`, `compact(dt, *, seconds=False)` -> `20261007T1032Z`,
`hhmmz(dt)` -> `1032Z`, `ddhhmmz(dt)` -> `071032Z`, `slash_dtg(dt)` -> `20261007/1032Z`.
Arithmetic: `minutes_between(a, b)`, `age_s(then, at=None)`, `floor_minutes(dt, minutes)`.

### 4.2 `tephra.util.hashing`

`sha256_bytes`, `sha256_text`, `canonical_json`, `sha256_json`, `short_hash(digest, 12)`,
`combine_hashes(iterable)` (order-independent), `stable_id(prefix, *parts, length=12)`,
`proxy_flight_number(hex)` -> `RFA4821`.

### 4.3 `tephra.util.events`

`get_bus() -> EventBus`. `EventBus.publish(name, data) -> Event` (data: model, mapping or
list; serialised to JSON-safe values), `.subscribe(maxsize=256) -> Subscription`,
`.recent(name, limit=50) -> list[Event]` (oldest first), `.last(name)`. `Subscription` is an
async context manager and async iterator; `await sub.get(within_s=15)` returns `None` on
timeout. `Event(id: int, name: str, data: Any, at: datetime)`. Event names are `SseEvent`
values.

### 4.4 `tephra.models`

All shared models, enums and helpers. Highlights you will use:
`TephraModel`, `UtcDatetime`, `Position`, `PRESSURE_LEVEL_FL`; enums `FeedId`, `RunMode`,
`AviationColor`, `VaacCentre`, `FrameProduct`, `BtdIndicator`, `EvidenceState`,
`DiscrepancyKind`, `Severity` (+ `DISCREPANCY_SEVERITY`), `PlumeMode`, `ActionKind`
(+ `ALLOWED_ACTIONS`), `AircraftCategory`, `AdvisoryStatus` (+ `TERMINAL_STATUSES`),
`AuditAction`, `FeedStatus`, `TraceStage`, `TraceActor`, `SseEvent`, `LlmBackendName`;
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
`ExposedFlight`, `AlternateCheck`, `AlternateCandidate`, `PlannerContext`,
`PlannerDecision`, `ToolCallRecord`, `PlannedAction`, `DraftText`, `Advisory`
(`final_body`, `final_text`), `OutboundMessage`, `AuditEntry`, `FeedHealth`, `TraceEvent`
(`TraceEvent.new(...)`), `TraceSink`, `TickReport`, `ReplayRecord`, `ReplayCase`; Wall and
API shapes in section 8.

### 4.5 `tephra.config`

`Settings` (every env var; see the class), `get_settings()`, `apply_process_env(settings)`,
`PROJECT_ROOT`, `REGIONS`, `RegionKey`. Product constants `AIRLINE_CODE`, `AIRLINE_NAME`,
`DISCLAIMER`, `NO_MODEL_LABEL`, `REPLAY_BANNER_TEMPLATE`. Safety constants (not
configurable): `MAX_PLUME_EXTENT_KM=500`, `MAX_SECTOR_WIDTH_DEG=180`, `MAX_HORIZON_H=18`,
`ADVISORY_BODY_MAX_CHARS=400`, `HOLD_MINUTES=20`, `DIVERT_EXTRA_MINUTES=15`,
`ALTERNATE_MIN_VISIBILITY_M=3000`, `ALTERNATE_MIN_CEILING_FT=1000`,
`ALTERNATE_ETA_WINDOW_MIN=60`.

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
0.5 s), retries network errors and 408/420/425/429/5xx, honours `Retry-After` on 420/429,
and on final failure returns the last good copy marked `stale=True` (or raises
`FetchError`). HSD segments are never cached. Build `params` in a fixed key order.

### 4.7 `tephra.store.base`

`Collection` (names and document ids in section 7), `Where(field, op, value)`, `WhereOp`,
`BLOB_KEY_PATTERN`, `escape_doc_id`/`unescape_doc_id`, and the `Store` protocol:
`put`, `get`, `delete`, `list_docs`, `query`, `compare_and_set_advisory`, `append_audit`,
`get_feed_state`, `put_feed_state`, `list_feed_states`, `put_blob`, `get_blob`, `aclose`.
(The method is `list_docs`, not `list`, so implementations can still annotate with `list[...]`.)

## 5. Module APIs

Signatures are exact. "Rules" are behaviour other modules and tests rely on.

### 5.1 feeds-text

`tephra/feeds/sigmet.py`
```python
SIGMET_URL: Final = "https://aviationweather.gov/api/data/isigmet"
SIGMET_PARAMS: Final = {"format": "json", "hazard": "va"}
def parse_sigmets(result: FetchResult) -> list[Sigmet]
async def fetch_sigmets(source: Source) -> list[Sigmet]   # one GET with SIGMET_PARAMS
```
Rules: keep hazard VA only, all FIRs (no region filter here). De-duplicate records with the
same `(rawSigmet, seriesId)`. A series id ending in `F` is the forecast polygon of the same
SIGMET: keep it as its own record with `observed=False`. Polygon from JSON `coords`
(decimal); if absent, from the raw text, where coordinates are **degrees and minutes**
(`S0806 E11255` = -(8 + 6/60), 112 + 55/60), never decimals. `base_ft` 0 for SFC;
`top_ft` from JSON `top` or raw `FLnnn`/`TOP FLnnn`/`ABV FLnnn`. Movement `MOV NE 05KT` ->
`movement_toward_deg=45`, `movement_speed_kt=5`; `STNR` -> `stationary=True`. `CNL SIGMET`
-> `cancelled=True`. `observed_at` from `OBS AT 1010Z` via `parse_hhmmz(..., ref=valid_from)`.
Volcano name and `PSN` from the raw text. `provenance.issued_at` is the DTG in the raw
header if parseable, else `receiptTime`; `valid_from`/`valid_to` are also set on it. Drop
records whose `validTimeTo` is already past at parse time only in `fetch_sigmets`, never in
`parse_sigmets` (replay tests need them).

`tephra/feeds/vona.py`
```python
VONA_LIST_URL: Final = "https://magma.esdm.go.id/v1/vona"
class VonaListItem(TephraModel):   # url, magma_id: int, volcano_name, issued_at, color_code, summary
def parse_vona_list(result: FetchResult) -> list[VonaListItem]
def parse_vona_page(result: FetchResult, item: VonaListItem | None = None) -> Vona
async def fetch_vonas(source: Source, *, since: datetime,
                      known_urls: frozenset[str] = frozenset(), max_pages: int = 1) -> list[Vona]
```
Rules: page 1 is fetched with no params, page n with `{"page": str(n)}`. Only detail pages
not in `known_urls` and issued at or after `since` are fetched (MAGMA is a small public
service; research/06 asks us not to crawl it). `ash_observed=False` when the notice says ash
is not observed. Cloud top: parse the **metre** value and set
`cloud_top_ft = round(m * 3.28084)` (MAGMA's printed feet use a factor of 3.2; research/13).
Direction words ("north east", "northeast", "NE", "to the east") -> `movement_toward_deg`
via `tephra.geo.units.compass_to_deg`; keep the original in `movement_text`.

`tephra/feeds/vaac.py`
```python
TOKYO_LIST_URL: Final = "https://ds.data.jma.go.jp/svd/vaac/data/vaac_list.html"
DARWIN_BACKUP_LIST_URL: Final = "https://ds.data.jma.go.jp/svd/vaac/data/vaac_darwin_list.html"
DARWIN_BULLETIN_URLS: Final = tuple(
    f"https://tgftp.nws.noaa.gov/data/raw/fv/fvau0{n}.adrm..txt" for n in (1, 2, 3, 4))
class VaacListItem(TephraModel):   # vaac, url, volcano_name, area, issued_at, advisory_nr | None
def parse_vaac_list(result: FetchResult, vaac: VaacCentre) -> list[VaacListItem]
def parse_vaa_text(text: str, result: FetchResult) -> VaacAdvisory | None
def parse_vaa(result: FetchResult) -> VaacAdvisory | None     # extracts the text from HTML/plain
async def fetch_vaas(source: Source, feed: FeedId, *, since: datetime,
                     known_urls: frozenset[str] = frozenset()) -> list[VaacAdvisory]
```
Rules: `feed` is `FeedId.VAAC_TOKYO` (Tokyo list -> `TextData/...` pages, relative links
resolved against the list URL) or `FeedId.VAAC_DARWIN`. **Darwin advisories come from the
NOAA tgftp bulletins** `DARWIN_BULLETIN_URLS` (latest bulletin per header, GET). BoM's page
loads its list by POST and TEPHRA is GET-only; the JMA "Darwin backup" list holds only
advisories Tokyo issued while backing Darwin up (research/13) and is also polled under
`VAAC_DARWIN`. `VaacAdvisory.vaac` is taken from the text's `VAAC:` line. Return `None`
for `VOLCANO: NOTICE` pseudo-advisories (number 999999). Accept `+6 HR` and `+6HR`;
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
def assess_alternate(taf: Taf | None, eta: datetime) -> AlternateCheck
```
`assess_alternate` rules (simplified planning minima, labelled as such in the UI): no TAF ->
not ok (`NO TAF`); TAF not valid at `eta` -> not ok; every period (base, FM, BECMG, TEMPO,
PROBxx) overlapping `eta +/- ALTERNATE_ETA_WINDOW_MIN` is screened: `VA` in weather -> not
ok; visibility below `ALTERNATE_MIN_VISIBILITY_M` -> not ok; ceiling below
`ALTERNATE_MIN_CEILING_FT` -> not ok; `TS` -> reason recorded, still ok. Reasons are short
upper-case code-written strings (`"VIS 1500 M BELOW 3000 M"`). aviationweather.gov allows
100 requests/minute and needs a custom User-Agent (HttpSource sets it).

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
    def __init__(self, airports: Sequence[Airport]) -> None
    def all(self) -> list[Airport]
    def get(self, icao: str) -> Airport | None
    def icaos(self) -> set[str]
    def in_bbox(self, bbox: BBox) -> list[Airport]
    def nearest(self, lat: float, lon: float, *, limit: int = 5, max_nm: float = 400.0,
                alternates_only: bool = True) -> list[tuple[Airport, float]]   # (airport, distance_nm), nearest first
def load_airports(data_dir: Path) -> AirportCatalogue          # reads data/airports.json (AirportFile)
```
`data/airports.json` is an `AirportFile` of public aerodromes across the three regions and
their usual alternates (for example WIII, WIHH, WICA, WARR, WAHI, WADD for Java/Bali; WAMT,
WAMM for Halmahera; RJFK, RJFT, RJFM, RJFO, RJFU, RJFF for Kyushu). Verify every code
against a current source: Indonesia re-coded several Central Java aerodromes (WARx ->
WAHx). Real ICAO codes only; runway length in metres where known; `source_note` cites the
source.

`tephra/feeds/adsb.py`
```python
ADSB_POINT_URL: Final = "https://api.adsb.lol/v2/point/{lat}/{lon}/{radius_nm}"
def point_url(point: AdsbQueryPoint) -> str                   # lat/lon with 3 decimals
def query_points(region: Region, volcanoes: Sequence[Volcano], radius_nm: int) -> list[AdsbQueryPoint]
def parse_adsb(result: FetchResult, query: AdsbQueryPoint) -> AdsbSnapshot
async def fetch_aircraft(source: Source, points: Sequence[AdsbQueryPoint]) -> list[AdsbSnapshot]
def merge_aircraft(snapshots: Sequence[AdsbSnapshot]) -> list[Aircraft]
```
Rules: `query_points` = the region's points plus one per given (active) volcano at
`radius_nm`, dropping a volcano point within 50 nm of one already chosen. Calls are
sequential (HttpSource spaces them >= 1.1 s and backs off on 420/429); a failed point is
logged and skipped. Parse fields `hex, flight, lat, lon, alt_baro, alt_geom, gs, track,
nav_altitude_mcp, t, baro_rate, seen_pos`; drop `alt_baro == "ground"` and targets without
position; never keep `r` (registration). `observed_at` = response `now` (ms) minus
`seen_pos` (or `seen`). `merge_aircraft` de-duplicates by `hex`, keeping the newest. UI
attribution: "Aircraft: adsb.lol (ODbL 1.0)".

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
NICT_LATEST_URL: Final = "https://himawari8.nict.go.jp/img/D531106/latest.json"
def frame_key(volcano_id: str, product: FrameProduct, observed_at: datetime) -> str
    # "frames/{volcano_id}_{product}_{compact(observed_at)}.png"
async def fetch_frames(source: Source, volcano: Volcano, *, half_width_km: float = 300.0
                       ) -> list[tuple[SatelliteFrame, bytes]]   # PNG bytes to store at frame.image_key
```
Rules: JMA MSC realtime images (`area` `se3` for Indonesia with `band` `b13` Band-13 IR and
`dst` Dust RGB, 10-minute files named by HHMM and kept about 23 hours; pick the area that
covers the volcano and verify the Japan-area name for Kyushu). NICT true colour only in
local daylight. Crop around the volcano with Pillow, re-encode PNG. Set `bbox` only if the
image projection and corner coordinates are known exactly; otherwise `bbox=None` and the
Wall shows the frame in a side strip, never on the map. Caption names the product and says
"context only; not used to draw the cone". A product that fails is skipped, not fatal.

### 5.3 science

`tephra/science/hsd_segments.py`
```python
HSD_BUCKET_URL: Final = "https://noaa-himawari9.s3.amazonaws.com/"
class HsdObject(TephraModel):   # key, url, band: int, segment: int, size_bytes: int, scan_start: UtcDatetime
def listing_params(scan_start: datetime) -> dict[str, str]   # {"list-type": "2", "prefix": "AHI-L1b-FLDK/YYYY/MM/DD/HHMM/"}
def parse_listing(result: FetchResult) -> list[HsdObject]
def segments_for_bbox(bbox: BBox) -> list[int]                # 1..10 full-disk segments covering it
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
`INCONCLUSIVE` (e.g. most pixels colder than 233 K). **SILENT never means "no ash"**; the
caption must say so. Credit: "Himawari-9 data: JMA, distributed by NOAA (NODD / AWS Open
Data); processed by TEPHRA, not original JMA data". Never re-serve raw HSD files.

### 5.4 geo

`tephra/geo/units.py`
```python
FT_PER_M: Final = 3.28084; KM_PER_NM: Final = 1.852; EARTH_RADIUS_KM: Final = 6371.0088
def ft_to_fl(ft: float) -> int                 # rounds to nearest
def fl_to_ft(fl: float) -> int
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float
def distance_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float
def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float
def destination_point(lat: float, lon: float, bearing_deg: float, distance_km: float) -> tuple[float, float]  # (lat, lon)
def bearing_diff_deg(a: float, b: float) -> float           # 0..180
def compass_to_deg(text: str) -> float | None               # 16-point names and words; None if unknown
def deg_to_compass(deg: float) -> str                       # 16-point
def sector_width_deg(bearing_from_deg: float, bearing_to_deg: float) -> float  # clockwise
def solar_hour(lon: float, at: datetime) -> float           # local mean solar time, 0..24 (night flag)
```

`tephra/geo/cone.py`
```python
def official_layers(volcano: Volcano, sigmets: Sequence[Sigmet], vaas: Sequence[VaacAdvisory],
                    at: datetime) -> list[OfficialLayer]
def sector_polygon(lat: float, lon: float, bearing_from_deg: float, bearing_to_deg: float,
                   extent_km: float, *, steps: int = 32) -> GeoPolygon | None   # None if extent 0 or zero width
def build_cone(situation: Situation, assessment: PlumeAssessment) -> HazardCone
def covers_official(cone: HazardCone, layers: Sequence[OfficialLayer]) -> bool
def polygon_iou(a: GeoPolygon | GeoMultiPolygon, b: GeoPolygon | GeoMultiPolygon) -> float
def contains_point(cone: HazardCone, lat: float, lon: float) -> bool
```
`official_layers` rules (the "official floor", research/07 rule 13): every SIGMET with a
polygon, valid or starting within `MAX_HORIZON_H` (window = its validity); for the latest
current VAA per VAAC: OBS/EST layers with polygons (window `[observation.valid_at,
vaa.valid_until()]`) and each forecast layer (window `[valid_at - 3 h, valid_at + 3 h]`).
Keep a layer when its window ends at or after `at` and starts no later than `at +
MAX_HORIZON_H`. `label` and `layer` as in the model docstring.

`build_cone` rules: geometry = union of **all** `situation.official_layers` polygons, plus
the sector from the estimate when mode is WIDENED or HYPOTHESIS (OFFICIAL ignores the
sector). The union is made with shapely in lon/lat degrees (regional scale; no antimeridian
in JAPAC scope) and is **never simplified, buffered inward or clipped**, so the cone always
covers every official polygon (`covers_official` is the property the tests check with
hypothesis). Vertical band: `base_ft = min(estimate.base_fl*100, official bases)`, `top_ft =
max(estimate.top_fl*100, official tops)`. `horizon_h = estimate.horizon_h`, `valid_to =
assessment.created_at + horizon`, `llm_backend = assessment.llm_backend`, `id =
stable_id("CONE", volcano_id, assessment.id)`. `geometry=None` only when there is no official layer and
no sector.

`tephra/geo/exposure.py`
```python
def extrapolate(aircraft: Aircraft, minutes: int, *, step_min: int = 1) -> list[tuple[float, float]]  # (lat, lon), t=0 first
def find_exposed(cone: HazardCone, aircraft: Sequence[Aircraft], at: datetime, *,
                 lookahead_min: int, vertical_margin_ft: int) -> list[ExposedFlight]
```
Rules: only `aircraft.airline` targets with `alt_baro_ft` are considered; never use
`alt_geom_ft`. Lookahead is `min(cone.horizon_h * 60, lookahead_min)`; positions step along
`track_deg` at `gs_kt` with `destination_point` each minute ("if current track and level
are held"); targets without `gs_kt`/`track_deg` or below 50 kt are checked at their current
position only. Vertical: the aircraft band is `[min, max]` of `alt_baro_ft` and
`nav_altitude_mcp_ft` (if present); exposed only if it overlaps `[cone.base_ft -
vertical_margin_ft, cone.top_ft + vertical_margin_ft]`. Horizontal: the first extrapolated
point inside the cone. `minutes_to_entry` is that step index; `path` runs from the current
position to the entry point (GeoJSON order); `hold = fuel.hold_line(category)`;
`id = f"{hex}:{cone.volcano_id}"`. Sorted by `minutes_to_entry`.

`tephra/geo/fuel.py`
```python
BURN_KG_PER_MIN: Final[dict[AircraftCategory, float]] = {LIGHT: 5, TURBOPROP: 12, REGIONAL_JET: 25,
                                                         NARROWBODY: 42, WIDEBODY: 110, UNKNOWN: 42}
def category_for_type(type_icao: str | None) -> AircraftCategory
def hold_line(category: AircraftCategory) -> FuelLine                    # HOLD_MINUTES
def divert_line(category: AircraftCategory, *, alternate_icao: str, distance_nm: float,
                gs_kt: float | None) -> FuelLine    # distance/gs*60 + DIVERT_EXTRA_MINUTES; gs None or <150 -> 250 kt assumed, said in formula
```
`formula` strings are code-written upper case, e.g. `"HOLD 20 MIN x 42 KG/MIN (NARROWBODY) =
840 KG"`, `"DIVERT WARR 182 NM AT 430 KT = 25 MIN + 15 MIN = 40 MIN x 42 KG/MIN = 1680
KG"`. Minutes and kg are integers (rounded up). UNKNOWN types use the narrowbody rate and
the formula says `(TYPE UNKNOWN, NARROWBODY RATE)`.

### 5.5 reconcile-plume

`tephra/reconcile/discrepancies.py` (re-exported from `tephra/reconcile/__init__.py`)
```python
def find_active(catalogue: VolcanoCatalogue, *, sigmets: Sequence[Sigmet], vonas: Sequence[Vona],
                vaas: Sequence[VaacAdvisory], at: datetime, settings: Settings) -> dict[str, list[str]]
def select_records(catalogue: VolcanoCatalogue, volcano: Volcano, *, sigmets: Sequence[Sigmet],
                   vonas: Sequence[Vona], vaas: Sequence[VaacAdvisory], at: datetime,
                   settings: Settings) -> tuple[list[Sigmet], list[Vona], list[VaacAdvisory]]
def evidence_state(record: Sigmet | Vona | VaacAdvisory, volcano: Volcano, at: datetime) -> EvidenceState
def find_discrepancies(volcano: Volcano, *, sigmets: Sequence[Sigmet], vonas: Sequence[Vona],
                       vaas: Sequence[VaacAdvisory], at: datetime, settings: Settings) -> list[Discrepancy]
def build_situation(volcano: Volcano, *, active_reasons: list[str], sigmets: Sequence[Sigmet],
                    vonas: Sequence[Vona], vaas: Sequence[VaacAdvisory], winds: Sequence[WindProfile],
                    frames: Sequence[SatelliteFrame], btd: BtdResult | None, at: datetime,
                    mode: RunMode, settings: Settings) -> Situation
```
Activity (`find_active` returns `volcano_id -> human reasons`): a VONA for it issued within
`vona_window_h`; or a VAA for it that `is_current(at)`; or a valid VA SIGMET that names it
(`catalogue.find_in_text`) or whose polygon lies within `active_radius_km` of the vent.
`select_records`: SIGMETs matching as above that are not cancelled and are valid at `at` or
start within `MAX_HORIZON_H` (forecast `F` series included); VONAs within the window
(newest first); per VAAC the newest VAA issued in the last 24 h (newest first). `build_situation`
sets `official_layers = tephra.geo.cone.official_layers(...)` and `discrepancies =
find_discrepancies(...)`.

Discrepancy rules (deterministic; Gemini never decides what counts):
- **Non-observations are never CONFLICT.** "Ash-cloud is not observed", "VA NOT
  IDENTIFIABLE", NIGHT_BLIND and absence are evidence states, not contradictions
  (research/13: the 7 Oct pair is a non-observation, the 25 Sep pair is ENVELOPE + LAG).
- CONFLICT: an explicit negative assertion (VAA `NO VA EXP`, or a final VAA) valid at the same
  time as a positive observation (SIGMET `observed=True`, VONA `ash_observed=True`, VAA OBS
  layer) from another product.
- LAG: two products' observation/issue times differ by more than `lag_threshold_min`;
  magnitude in minutes.
- ENVELOPE: one product's top lies inside the other's band, or outside it by no more than
  `height_tolerance_ft`; magnitude = signed difference in ft.
- HEIGHT_MISMATCH: tops differ beyond `height_tolerance_ft` with neither inside the other.
- DIRECTION_MISMATCH: movement directions differ by more than `direction_tolerance_deg`
  (aspect `direction`), or a point 15 km down a VONA's direction lies outside the SIGMET
  polygon valid at that VONA's time (aspect `polygon`; research/13 finding 4).
- SILENCE: a VONA with ash and no VAA issued after it for more than
  `silence_threshold_min`; a valid SIGMET with no current VAA; or a VAA past its next
  advisory time with no newer one ("overdue"). Magnitude in minutes since.
- A SIGMET whose polygon repeats a VAA polygon vertex for vertex is the same source twice
  (research/13): no discrepancy between them, and `summary` of any other discrepancy that
  involves both names them together.
`summary` and `values` are code-written (`"VONA 13,701 ft inside SIGMET SFC/FL150"`).

`tephra/agents/llm.py`
```python
class LlmPart(TephraModel):        # kind: Literal["text","image"]; text: str|None; data: bytes|None; mime_type: str|None; label: str|None
class LlmCall(TephraModel):        # backend, model_id, prompt_hash, latency_ms, input_tokens, output_tokens, raw_text, error: str|None
class LlmBackend(Protocol):
    @property
    def name(self) -> LlmBackendName: ...
    def model_id(self, tier: Literal["main", "lite"]) -> str: ...
    def reserve(self, tier: Literal["main", "lite"]) -> bool: ...   # take one call from today's budget
    async def structured[T: BaseModel](self, *, tier: Literal["main", "lite"], system: str,
                                       parts: Sequence[LlmPart], schema: type[T],
                                       stub: Callable[[], T], temperature: float = 0.2
                                       ) -> tuple[T | None, LlmCall]: ...
class GeminiBackend: ...           # google-genai Client(api_key=...).aio.models.generate_content, JSON mime + response_schema
class StubBackend: ...             # returns stub(), model_id "stub", never touches the network
class BudgetExhausted(RuntimeError): ...
def get_llm(settings: Settings) -> LlmBackend
def prompt_hash(system: str, parts: Sequence[LlmPart]) -> str   # images contribute their sha256
```
Rules: `structured` never raises for model trouble: on API error, timeout, quota, invalid
JSON or schema failure it returns `(None, call)` with `call.error` set. Tier `main` uses
`settings.model`, tier `lite` uses `settings.model_lite`. Per-tier daily budgets
(`model_daily_budget`, `model_lite_daily_budget`, counted per UTC day in process memory)
are enforced before calling; over budget -> `(None, call)` with `error="budget_exhausted"`.
`structured` calls `reserve` itself; the ADK planner calls `llm.reserve("lite")` from a
`before_model_callback` on every model turn and ends the run (falling back to rules) when it
returns False. The stub's `reserve` always returns True.
`genai.Client(api_key=...)` only; never Vertex AI, never ADC. Image parts are sent with a
preceding text part `IMAGE {label}`.

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
def build_parts(situation: Situation, images: Sequence[LlmPart]) -> list[LlmPart]
def validate_estimate(estimate: PlumeEstimate, situation: Situation) -> list[str]
def stub_estimate(situation: Situation, settings: Settings) -> PlumeEstimate
def official_fallback(situation: Situation, settings: Settings) -> PlumeEstimate
```
One `llm.structured(tier="main", schema=PlumeEstimate, ...)` call (plus at most one
repair). Input to the model: raw texts of every SIGMET/VONA/VAA with their source ids and evidence
states, the discrepancy list, winds by flight level (`toward_deg` and speed per FL), the BTD
summary (stats, indicator, caveats) and the images (`images` holds the stored frame PNGs and
the BTD PNG; core loads them). No timestamps are sent except as source ids; the prompt
tells the model to cite sources by id only.

Validator (`validate_estimate` returns problems; empty = accepted):
1. every `sources_used` and `which_source_we_lean_on` is in `situation.source_ids()`; every
   `discrepancy_id` is in the situation's discrepancies;
2. no timestamp anywhere in the text fields: reject `\d{4}Z`, `\d{6}Z`, `\d{1,2}:\d{2}`,
   `\d{8}/\d{4}Z?`, ISO dates `\d{4}-\d{2}-\d{2}`, `\d{1,2}/\d{4}Z`;
3. HYPOTHESIS while `situation.official_valid_now()` is rejected; OFFICIAL with no
   official layer is rejected;
4. `top_fl * 100 < situation.official_top_ft()` is rejected (never shrink);
5. `sector_width_deg() > MAX_SECTOR_WIDTH_DEG` rejected; `extent_km > MAX_PLUME_EXTENT_KM`
   rejected; `horizon_h > MAX_HORIZON_H` rejected; `base_fl >= top_fl` rejected (except
   the code-built OFFICIAL fallback with no layers);
6. a SILENT BTD or a non-observation may not be cited as a reason to narrow anything.
On rejection: exactly one repair call with the problems listed; if it still fails (or the
model returned nothing), `official_fallback`: mode OFFICIAL, band from the official layers
(0/0 when none), `bearing_from_deg = bearing_to_deg = 0`, `extent_km = 0`, `horizon_h =
settings.default_horizon_h`, `confidence = 1.0`, `sources_used` = official source ids,
`uncertainty_notes = "Model output rejected; official products only."`. Outcome
`FALLBACK_OFFICIAL`, `validation_errors` kept, and an audit-worthy trace line (core writes
the `PLUME_FALLBACK` audit entry).

`stub_estimate` (backend `stub`, outcome `STUB`, deterministic): with an official layer ->
OFFICIAL (band from layers, confidence 1.0); else with a VONA reporting ash in the last 6 h
-> HYPOTHESIS: sector centred on the wind `toward_deg` at the VONA top's flight level (or the
VONA movement if no wind) +/- 30 degrees, `extent_km = min(300, wind_kt * 1.852 * 3)`,
`base_fl = 0`, `top_fl = ceil(VONA top ft / 1000) * 10 + 20`, `horizon_h = 3`, confidence
0.3; else OFFICIAL with no layers. `rationale` starts with `"NO MODEL:"`.

`call_model=False` (core decided no call is needed, section 5.7) returns the
`official_fallback` estimate with outcome `OFFICIAL_ONLY`, `attempts=0`, `model_id="none"`
and no trace of a model. With the stub backend the outcome is always `STUB`.
`read_plume` sets `PlumeAssessment.id = stable_id("PA", volcano_id, input_hash,
prompt_hash, model_id)`.

### 5.6 planner-drafter

`tephra/agents/validators.py`
```python
def allowed_actions(mode: PlumeMode) -> list[ActionKind]          # from ALLOWED_ACTIONS, fixed order
def validate_decision(decision: PlannerDecision, ctx: PlannerContext) -> list[str]
def validate_draft(draft: DraftText, *, ctx: PlannerContext, plan: PlannedAction) -> list[str]
```
Decision rules: action in `ctx.allowed_actions` (HYPOTHESIS: MONITOR or HOLD only);
CHANGE_LEVEL needs `change_level_fl_min/max` whose band clears `[hazard_base_ft -
margin, hazard_top_ft + margin]`; HOLD needs `hold_fl`; DIVERT needs `alternate_icao` that
is one of `ctx.alternates` with `check.ok`; no clock times in `reasoning` (same regexes as
the plume validator). Draft rules: body upper case, `len <= ADVISORY_BODY_MAX_CHARS`,
printable ASCII; action word matches `plan.decision.action`; any 4-letter ICAO code or
5-letter all-caps word that looks like a waypoint must be one of the input's ICAO codes or
an allowed vocabulary word (keep a fixed vocabulary list of plain English and ACARS words);
no clock times or dates; every number in the body must appear in the input (FLs, minutes to
entry, fuel figures, distances); body must not say "AIRSPACE CLOSED" or "CLOSED" (TEPHRA
writes company advisories, research/07 rule 21); body must ask the crew for a volcanic
activity report (contains `VAR`); `cost_note` one line, <= 120 chars, same number rule.

`tephra/agents/exposure_planner.py`
```python
PROMPT_PATH: Final[Path]
CONTEXT_STATE_KEY: Final = "tephra_ctx"
def build_planner_context(flight: ExposedFlight, cone: HazardCone, *, volcano_name: str,
                          airports: AirportCatalogue, tafs: Mapping[str, Taf], at: datetime,
                          settings: Settings) -> PlannerContext
def rule_based_decision(ctx: PlannerContext) -> PlannerDecision
async def plan_flight(ctx: PlannerContext, llm: LlmBackend, *, settings: Settings,
                      trace: TraceSink | None = None) -> PlannedAction
```
`build_planner_context`: alternates from `airports.nearest(flight.lat, flight.lon,
max_nm=settings.alternate_search_nm)`; ETA from distance and ground speed; each screened
with `tephra.feeds.taf.assess_alternate`; an alternate inside the cone (or within 20 nm of
it) is not ok with reason `"INSIDE HAZARD CONE"` (research/07 rule 20); `divert =
fuel.divert_line(...)`; `allowed_actions = allowed_actions(cone.mode)`.

`rule_based_decision` (stub and last-resort fallback, deterministic): HYPOTHESIS -> HOLD at
the current FL if `minutes_to_entry <= 20`, else MONITOR. OFFICIAL/WIDENED -> if a level
band clear of the hazard (with margin) is within 4,000 ft of the current level and at or
below FL410, CHANGE_LEVEL to the nearest such 2,000 ft band; else if `inside_now` or
`minutes_to_entry <= 15` and an ok alternate exists, DIVERT to the nearest ok alternate;
else if `minutes_to_entry <= 30`, HOLD at the current FL; else MONITOR. Reasoning starts
with `"NO MODEL:"` when produced for the stub.

`plan_flight`: backend `stub` -> `rule_based_decision`, outcome `STUB`. Backend `gemini` ->
ADK `LlmAgent` on `settings.model_lite` with FunctionTools that read the context from
`tool_context.state[CONTEXT_STATE_KEY]` (a `PlannerContext` JSON dump): `get_flight()`,
`list_alternates()`, `check_alternate(icao)`, `check_level_band(fl_min, fl_max)`,
`estimate_cost(action, alternate_icao=None)`, and `submit_plan(action, reasoning,
change_level_fl_min=None, change_level_fl_max=None, hold_fl=None, alternate_icao=None,
alternatives_considered=None)` which records the `PlannerDecision`. Tool calls become
`ToolCallRecord`s and are streamed to `trace` as `TraceStage.PLANNER`, actor `adk`. Invalid
or missing decision -> one repair turn with the problems -> `rule_based_decision` with
outcome `FALLBACK_RULES`. ADK runs with `InMemoryRunner` (or the ADK 2.x equivalent) inside
the process; the ADK version is 2.x (research/06): check the current API at adk.dev before
coding and keep this design.

`tephra/agents/dispatch_drafter.py`
```python
PROMPT_PATH: Final[Path]
def render_header(*, ctx: PlannerContext, plan: PlannedAction, cone: HazardCone,
                  sources: Sequence[SourceRef], at: datetime) -> str
def stub_draft(ctx: PlannerContext, plan: PlannedAction) -> DraftText
def select_sources(situation: Situation, flight: ExposedFlight) -> list[SourceRef]
async def draft_advisory(*, situation: Situation, assessment: PlumeAssessment, cone: HazardCone,
                         ctx: PlannerContext, plan: PlannedAction, llm: LlmBackend,
                         settings: Settings, trace: TraceSink | None = None) -> Advisory
```
`render_header` (code only) prints, upper case: the line `TEPHRA COMPANY ADVISORY - RING OF
FIRE AIR (FICTIONAL) - NOT FOR OPERATIONAL USE`; `{proxy_flight} (ADS-B {callsign}
{hex})`; volcano; action with level/alternate; `ENTRY {n} MIN` or `INSIDE NOW`; `CONE
{mode} {confidence%}` (+ `NO MODEL` for stub); drafted time `hhmmz(at)`; then one `SRC`
line per source: `{feed} {source_id} ISSUED {ddhhmmz} FETCHED {ddhhmmz} #{sha256_short}`,
the binding product (SIGMET) first. `select_sources`: latest valid SIGMET(s), latest VONA,
latest VAA, the wind profile used, and the ADS-B snapshot of the flight (the "four feed
timestamps and hashes", plus the aircraft).
`draft_advisory`: Gemini (`tier="lite"`, `schema=DraftText`) writes `body` and `cost_note`
only; validate with `validate_draft`; one repair; then `stub_draft` with a
`validation_notes` entry. Returns an `Advisory` with `status=DRAFT`, `version=1`,
`created_at=updated_at=timeutil.now()`, `replay=situation.mode is REPLAY`, `prompt_hashes`
for `plume_reader`/`planner`/`drafter`, `dedupe_key = stable_id("DD", hex, volcano_id,
action, change_level_fl_min, hold_fl, alternate_icao)`, `input_hash =
situation.input_hash`. It does not store anything.

`tephra/agents/adk_app.py`
```python
def build_planner_agent(model: str) -> "LlmAgent"
root_agent: "LlmAgent"     # build_planner_agent(get_settings().model_lite) at import
```
For ADK evaluation (`AgentEvaluator.evaluate(agent_module="tephra.agents.adk_app", ...)`):
the module exposes `root_agent` and must not define a module-level name `agent`. Eval cases
put a `PlannerContext` dump in `session_input.state["tephra_ctx"]`.

Prompts (`agents/prompts/*.md`) are versioned by content: `prompt_hash` covers the file text.

### 5.7 core

`tephra/store/__init__.py`
```python
def open_store(settings: Settings) -> Store      # SqliteStore or FirestoreStore (imports google.cloud lazily)
```
`tephra/store/sqlite_store.py`: `class SqliteStore(Store)`, constructor `(path: Path,
blob_dir: Path)`; stdlib `sqlite3` via `asyncio.to_thread`; one table `docs(collection, id,
doc JSON, PRIMARY KEY(collection, id))`; CAS in a transaction; blobs under
`cache_dir/blobs/`. `tephra/store/firestore_store.py`: `class FirestoreStore(Store)`,
constructor `(project: str, database: str, bucket: str)`; `google.cloud.firestore.AsyncClient`
and Cloud Storage for blobs (runs only inside Cloud Run with its service account); CAS in a
Firestore transaction; ids escaped with `escape_doc_id`.

`tephra/desk/audit.py`
```python
async def record(store: Store, *, actor: str, action: AuditAction, advisory_id: str | None = None,
                 before: Mapping[str, Any] | None = None, after: Mapping[str, Any] | None = None,
                 input_hashes: Sequence[str] = (), model_id: str | None = None,
                 prompt_hash: str | None = None, note: str | None = None) -> AuditEntry
async def list_entries(store: Store, *, advisory_id: str | None = None, limit: int = 100) -> list[AuditEntry]
```
`tephra/desk/approvals.py`
```python
class VersionConflict(Exception): current: Advisory
class InvalidTransition(Exception): ...
class AdvisoryNotFound(Exception): ...
class EditRejected(Exception): problems: list[str]
async def submit_draft(store: Store, bus: EventBus, advisory: Advisory) -> Advisory | None
async def approve(store: Store, bus: EventBus, advisory_id: str, *, expected_version: int, actor: str) -> Advisory
async def edit_and_approve(store: Store, bus: EventBus, advisory_id: str, *, expected_version: int,
                           body: str, actor: str) -> Advisory
async def reject(store: Store, bus: EventBus, advisory_id: str, *, expected_version: int,
                 reason: str, actor: str) -> Advisory
async def supersede(store: Store, bus: EventBus, advisory_id: str, *, reason: str,
                    superseded_by: str | None = None) -> Advisory | None
async def list_advisories(store: Store, *, status: AdvisoryStatus | None = None, limit: int = 50) -> list[Advisory]
```
Transition rules: only DRAFT moves. approve -> APPROVED; edit -> EDITED (body stripped,
upper-cased, 1..`ADVISORY_BODY_MAX_CHARS` chars, both `body` and `edited_body` kept); reject
-> REJECTED (`reason` >= 3 chars); supersede -> SUPERSEDED (actor `system`). Each transition
increments `version` through `compare_and_set_advisory`, sets `decided_by`/`decided_at`
(dispatcher transitions), writes an `AuditEntry` (before/after = status, version, body,
edited_body, reject_reason; `input_hashes` = advisory `input_hash` + every source sha256;
`model_id`; `prompt_hash` = drafter hash) and publishes `SseEvent.ADVISORY`. APPROVED and
EDITED also write an `OutboundMessage` (text = `advisory.final_text`) to `outbound` and an
`OUTBOUND_QUEUED` audit entry. Nothing ever leaves the store. `submit_draft` de-duplicates:
if an open DRAFT for the same flight has the same `dedupe_key`, return None; if it has a
different one, supersede it and create the new draft; if the same `dedupe_key` was APPROVED
or EDITED within the last 60 minutes, return None. Creation writes a `DRAFT_CREATED` entry.

`tephra/replay/cases.py`
```python
def cases_dir(data_dir: Path) -> Path                          # data_dir / "replay"
def list_cases(data_dir: Path) -> list[ReplayCase]             # newest recorded_from first
def load_case(data_dir: Path, case_id: str) -> ReplayCase
class ReplaySource(Source):
    def __init__(self, case_dir: Path, case: ReplayCase) -> None
def replay_banner(case: ReplayCase) -> str                     # REPLAY_BANNER_TEMPLATE
```
`ReplaySource.fetch` matches the exact final URL (`build_url(url, params)`): the latest
record with `fetched_at <= now()`, else the earliest record for that URL; no match ->
`FetchError`. Results have `replay=True` and the recorded `fetched_at` and `sha256`
(verified against the file).

`tephra/feeds/registry.py`
```python
class FeedPoll(TephraModel):   # feed, ok, record_count, new_record_count, error: str|None, stale: bool
async def poll(feed: FeedId, runtime: "Runtime") -> FeedPoll
def due_feeds(at: datetime, states: Mapping[FeedId, FeedHealth], settings: Settings,
              *, active: bool, replay: bool = False) -> list[FeedId]
# VONA is due only when settings.vona_live (TEPHRA_VONA_LIVE) or replay: MAGMA's robots.txt
# disallows crawling, so live VONA polling is opt-in.
```
`tephra/scheduler.py`
```python
async def run_local_scheduler(runtime: "Runtime", stop: asyncio.Event) -> None
```
`tephra/pipeline.py`
```python
@dataclass
class Runtime:
    settings: Settings; store: Store; bus: EventBus; source: Source; llm: LlmBackend
    catalogue: VolcanoCatalogue; airports: AirportCatalogue
    mode: RunMode; replay_case: ReplayCase | None; auto_replay: bool
    async def tick(self, *, reason: str = "scheduler") -> TickReport
    async def system_state(self) -> SystemState
    async def wall_snapshot(self) -> WallSnapshot
    async def switch_mode(self, mode: RunMode, *, auto: bool = False) -> None
    async def aclose(self) -> None
async def create_runtime(settings: Settings) -> Runtime
```
Core rules:
- One tick at a time (an `asyncio.Lock`); a tick that finds the lock held returns
  `TickReport(skipped=True)`. Under Cloud Scheduler (one tick per minute) the tick polls
  ADS-B at the start and again 30 s later; with `TEPHRA_LOCAL_SCHEDULER=1` the local loop
  ticks every `tick_interval_s`.
- Tick order: due feeds -> store new/changed records only (compare sha256) -> `find_active`
  -> per active volcano winds/frames/BTD (BTD only with `settings.science`, in a thread) ->
  `build_situation` -> plume assessment -> `build_cone` -> `find_exposed` -> for each exposed flight without an open
  draft for this cone: `build_planner_context` -> `plan_flight` -> `draft_advisory` ->
  `submit_draft` -> drafts for flights no longer exposed are superseded -> wall snapshot ->
  SSE events. A `FALLBACK_OFFICIAL` assessment writes a `PLUME_FALLBACK` audit entry.
- Plume quota gate. `situation.input_hash` covers only the official texts and the BTD
  indicator. If it equals the last assessment's, reuse that assessment (no call). If it
  changed, call `read_plume(..., call_model=True)` only when at least one holds: a CAUTION
  or WARNING discrepancy exists; no official layer is valid now but a VONA reports ash
  (HYPOTHESIS territory); an airline aircraft is within `adsb_radius_nm` of the vent.
  Otherwise call it with `call_model=False` (OFFICIAL_ONLY). This keeps TEPHRA near the
  ~20 calls/day free tier of 3.8 Flash; the per-tier daily budget in `agents/llm` is the
  hard stop.
- Trace lines (`TraceEvent.new`) for each step go to `bus.publish(SseEvent.TRACE, event)`;
  agents receive `trace=` callbacks that do the same.
- Live state (aircraft, exposures, wall snapshot, feed health) is held in memory and
  persisted at most every 5 minutes; durable records (feed products on change,
  assessments, cones on change, plans, advisories, audit, outbound) are written when they
  change. Target under 10,000 Firestore writes a day (free tier is 20,000).
- REPLAY: `create_runtime` installs `ReplayClock(case.recorded_from, case.recorded_to,
  speed=settings.replay_speed)` with `set_clock` and uses `ReplaySource`. Auto-replay:
  with `settings.auto_replay`, after `auto_replay_after_ticks` consecutive LIVE ticks with no
  active volcano and no exposed flight, switch to REPLAY (`ReplayInfo.auto=True`, audit
  `MODE_SWITCH`); while auto-replaying, each tick also polls the live SIGMET feed only
  (through a separate `HttpSource`) and switches back to LIVE when a VA SIGMET for a
  catalogue volcano is valid at wall-clock time (`SystemClock().now()`, not the replay
  clock). `HttpSource` always stamps `fetched_at` with wall-clock time.
- `wall_snapshot()` builds `WallSnapshot` (section 8.3) from memory. Situation cards: for
  each active volcano, exactly three `SourceCard`s in the order SIGMET, VONA, VAA (the
  latest of each; others listed in `extra_source_ids`; a missing kind gets `missing=True`
  and a code-written `missing_note` such as `"No VAA since VONA 2221Z (47 min)"`),
  `evidence` from `reconcile.evidence_state`, code-written `display_fields` (top, base,
  movement, ash observed, colour code, validity), and `discrepancy_ids` of the
  discrepancies that cite that card's source.

### 5.8 api

`tephra/main.py`: `app = create_app()` and `def run() -> None` (uvicorn on
`0.0.0.0:{settings.port}`, `proxy_headers=True`, log level from settings). Console script
`tephra`.

`tephra/api/server.py`: `def create_app(settings: Settings | None = None) -> FastAPI`. The
lifespan creates the runtime with `create_runtime`, starts `run_local_scheduler` when
`settings.local_scheduler`, and closes both on shutdown. Routes and shapes: section 8.

`tephra/api/auth.py`
```python
COOKIE_NAME: Final = "tephra_desk"
TASK_HEADER: Final = "X-Tephra-Task-Token"
def sign_session(name: str, settings: Settings, *, at: datetime) -> tuple[str, datetime]
def verify_session(token: str, settings: Settings, *, at: datetime) -> SessionInfo | None
async def require_desk(request: Request) -> SessionInfo          # FastAPI dependency; 401 otherwise
async def require_task_token(request: Request) -> None           # 403 unless header matches settings.task_token
class LoginThrottle: ...                                         # 5 failures per client IP per 10 min -> 429
```
Cookie value `b64url(json{"n": name, "exp": epoch_s, "sid": hex}).b64url(hmac_sha256)` keyed
by `settings.session_secret`; `HttpOnly; SameSite=Strict; Path=/; Max-Age=ttl`; `Secure`
when the request is https (or `X-Forwarded-Proto: https`). PIN and token compared with
`hmac.compare_digest`. Audit `LOGIN_OK`/`LOGIN_FAILED` (actor `desk:<name>`, never the PIN).

`tephra/api/sse.py`
```python
async def event_stream(bus: EventBus, *, heartbeat_s: float = 15.0) -> AsyncIterator[str]
def format_event(event: Event) -> str      # "id: {id}\nevent: {name}\ndata: {json}\n\n"
```
The stream starts with `retry: 3000\n\n`, sends a `heartbeat` event when idle for
`heartbeat_s`, and closes when the client disconnects.

### 5.9 web-wall and web-desk

Plain HTML/CSS/JS, no build step, no frameworks. MapLibre GL JS from
`https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js` and `.../maplibre-gl.css`;
basemap `https://tiles.openfreemap.org/styles/dark`. No Google Maps, no inline scripts or
inline event handlers (CSP below), no `innerHTML` with feed or model text (use
`textContent`).

Wall (`/`, `index.html` + `wall.js` + `wall.css`): fetch `GET /api/wall`, then subscribe to
`GET /api/events` and replace sections per section 8.4. Layers: volcanoes by colour code;
official polygons with expiry countdown (`valid_to`); cone (dashed outline, label =
`label`); optional BTD image source using `corners`; aircraft arrows rotated by
`track_deg`, amber when `exposed`, label with minutes to entry; exposure paths. Region
presets from `state.regions` (fly-to). Right rail: the three source cards side by side with
raw text, evidence state and discrepancy badges; the live trace; the advisory list with
status. Top bar: LIVE/REPLAY badge (`state.mode`, `state.replay.banner` as a permanent
banner), LLM label (`state.llm.label`, "AI-drafted" marking), feed health ages, and the
`state.disclaimer` line. Readable at 1280x720, keyboard accessible (focusable controls,
visible focus, no hover-only information). Attribution: OpenFreeMap/OpenStreetMap,
"Aircraft: adsb.lol (ODbL 1.0)", "Himawari-9 data: JMA via NOAA".

Desk (`/desk`, `desk.html` + `desk.js` + `desk.css`): PIN + name login (`POST
/api/desk/login`), list of DRAFT cards (`GET /api/desk/advisories?status=DRAFT`) showing
proxy flight and callsign, action, minutes to entry (and draft age from `created_at`), fuel
line, body, sources with issue times and short hashes, cone mode and confidence;
Approve / Edit (textarea, 400-char counter) / Reject (reason required). Send `version`; on
409 show the current version and let the dispatcher re-decide. Refresh on `advisory` SSE
events. Works at 375 px width, tap targets >= 44 px.

### 5.10 ops-evals

Files are listed in section 1. Requirements: `Dockerfile` (python:3.12-slim, uv, `uv sync
--frozen --no-dev --extra gcp`, copies `tephra/` and `data/`, `ENV TEPHRA_DATA_DIR=/app/data
TEPHRA_CACHE_DIR=/tmp/tephra-cache`, non-root user, `CMD ["tephra"]`); deploy scripts that
take `PROJECT_ID`/`REGION` from the environment and never hard-code an account (they are run
later by the user from a personal-account context, never by an agent on this machine);
Cloud Run `--min-instances=1 --max-instances=1 --no-cpu-throttling`; secrets
`GEMINI_API_KEY`, `TEPHRA_DESK_PIN`, `TEPHRA_TASK_TOKEN`, `TEPHRA_SESSION_SECRET` from
Secret Manager; one Cloud Scheduler job `POST /tasks/tick` every minute with header
`X-Tephra-Task-Token`; Firestore native mode; a US-region bucket for blobs (free tier).
`.env.example` lists variable names only. `scripts/record_replay.py` uses
`RecordingSource` around `HttpSource` and the feed fetchers, writes
`data/replay/<case_id>/` (aviationweather.gov `isigmet` accepts `date=YYYY-MM-DDTHH:MM:SSZ`
for past SIGMETs). Plume evals score IoU with `tephra.geo.cone.polygon_iou` and bearing
error with `tephra.geo.units.bearing_diff_deg`. CI runs `ruff check`, `ruff format
--check`, and `pytest` with `TEPHRA_LLM=stub`.

## 6. Quota and model use

| Step | Backend | Model | When it runs |
|---|---|---|---|
| Plume Reader | google-genai, structured output | `TEPHRA_MODEL` (gemini-3.8-flash) | only when a volcano's official texts or BTD indicator change and the quota gate (5.7) says the call matters; budget `TEPHRA_MODEL_DAILY_BUDGET` (18) |
| Exposure Planner | ADK `LlmAgent` + FunctionTools | `TEPHRA_MODEL_LITE` (gemini-3.5-flash-lite) | once per newly exposed flight per cone |
| Dispatch Drafter | google-genai, structured output | `TEPHRA_MODEL_LITE` | once per new plan |

Free-tier limits are reported, not published (research/06): about 20 requests/day for 3.8
Flash and 500 for 3.5 Flash-Lite. Over budget, every step falls back to code (OFFICIAL
cone, rule-based plan, template draft) and says so in the trace and on the card.

## 7. Store collections

| Collection | Doc id | Document | Written by |
|---|---|---|---|
| `sigmets`, `vonas`, `vaas`, `frames`, `btd` | `source_id` | `Sigmet`, `Vona`, `VaacAdvisory`, `SatelliteFrame`, `BtdResult` | core (new or changed sha256 only) |
| `tafs`, `metars` | ICAO | latest `Taf`, `Metar` | core |
| `adsb` | `latest` | `{"snapshots": [AdsbSnapshot]}` | core (throttled) |
| `winds` | volcano_id | `WindForecast` | core |
| `situations` | volcano_id | latest `Situation` | core (on change) |
| `assessments` | assessment id | `PlumeAssessment` | core |
| `cones` | volcano_id | latest `HazardCone` | core |
| `exposures` | flight id | `ExposedFlight` (current set) | core (throttled) |
| `plans` | plan id | `PlannedAction` | core |
| `advisories` | advisory id | `Advisory` (CAS on `version`) | desk.approvals only |
| `outbound` | message id | `OutboundMessage` | desk.approvals only |
| `audit` | entry id | `AuditEntry` (append-only) | desk.audit only |
| `feed_state` | FeedId value | `FeedHealth` | core |
| `wall` | `current` | `WallSnapshot` | core (throttled) |
| `runtime` | `state` | core bookkeeping | core |
| blobs | `frames/*.png`, `btd/*.png` | PNG bytes | core |

## 8. HTTP API (api implements, web consumes)

All JSON bodies are the named models dumped with `model_dump(mode="json")` (datetimes as
`2026-10-07T10:32:00.000Z`). Errors are `ErrorBody` with these `error` codes:
`bad_pin` (401), `unauthenticated` (401), `forbidden` (403), `desk_disabled` (503),
`too_many_attempts` (429), `not_found` (404), `version_conflict` (409, `current` set),
`invalid_transition` (409), `validation_failed` (422, `problems` set). A request validation
error from FastAPI is reshaped into `validation_failed`.

### 8.1 Pages and static files

| Method, path | Response |
|---|---|
| `GET /` | `tephra/web/index.html` |
| `GET /desk` | `tephra/web/desk.html` |
| `GET /static/{file}` | files in `tephra/web/` (`wall.js`, `wall.css`, `desk.js`, `desk.css`) |
| `GET /healthz` | `{"ok": true, "mode": "LIVE"}` |

Every HTML response carries:
`Content-Security-Policy: default-src 'self'; script-src 'self' https://unpkg.com;
style-src 'self' https://unpkg.com; img-src 'self' data: blob: https://tiles.openfreemap.org;
connect-src 'self' https://tiles.openfreemap.org; worker-src 'self' blob:; child-src blob:;
font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'`, plus
`X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Cache-Control: no-cache`.

### 8.2 Read endpoints (public, read-only)

| Method, path | Response model |
|---|---|
| `GET /api/state` | `SystemState` |
| `GET /api/wall` | `WallResponse` = `{state: SystemState, snapshot: WallSnapshot, advisories: [Advisory] (newest 50, all statuses), trace: [TraceEvent] (last 100, oldest first)}` |
| `GET /api/advisories?status=DRAFT&limit=50` | `AdvisoryList` |
| `GET /api/audit?advisory_id=...&limit=100` | `AuditList` |
| `GET /api/outbound?limit=50` | `OutboundList` |
| `GET /api/blobs/{key}` | PNG bytes; `key` must match `BLOB_KEY_PATTERN` (else 404) |
| `GET /api/events` | `text/event-stream` (section 8.4) |

### 8.3 Wall snapshot sections

`WallSnapshot.volcanoes`: FeatureCollection of `Point` with `VolcanoFeatureProps`
(catalogue volcanoes in all regions; `color_code` from the latest VONA/VAA, else UNKNOWN).
`official`: `OfficialLayer.to_feature()` for every layer of every active situation.
`cones`: `HazardCone.to_features()` (parts `cone` and `sector`).
`exposures`: per exposed flight a `LineString` (`kind: "path"`) and a `Point` at the entry
(`kind: "entry"`) with `ExposureFeatureProps`.
`aircraft`: `Point` per merged aircraft with `AircraftFeatureProps` (`exposed`,
`minutes_to_entry` and `volcano_id` from the earliest exposure).
`situations`: `SituationCard` per active volcano (cards exactly `[SIGMET, VONA, VAA]`).
`overlays`: `BtdOverlay` per active volcano with a BTD result (`image_url =
blob_url(image_key)`, `corners = bbox.corners_lonlat()`), `FrameThumb` per stored frame.

### 8.4 Server-Sent Events (`GET /api/events`)

Framing: `id: <int>\nevent: <name>\ndata: <json>\n\n`; first line `retry: 3000`.

| `event` | `data` | Client action |
|---|---|---|
| `state` | `SystemState` | replace top bar state |
| `feeds` | `{"feeds": [FeedHealth]}` | replace feed health |
| `volcanoes` | FeatureCollection | replace layer |
| `official` | FeatureCollection | replace layer |
| `cones` | FeatureCollection | replace layer |
| `exposures` | FeatureCollection | replace layer |
| `aircraft` | FeatureCollection | replace layer |
| `overlays` | `Overlays` | replace overlays |
| `situation` | `SituationCard` | upsert card by `volcano_id` |
| `trace` | `TraceEvent` | append (keep last 200) |
| `advisory` | `Advisory` | upsert by `id` (Wall list and Desk cards) |
| `heartbeat` | `{"now": iso, "mode": "LIVE"}` | update clock |

Core publishes every event except `heartbeat` (the SSE endpoint sends it).

### 8.5 Desk endpoints (cookie session; JSON bodies; `Content-Type: application/json` required)

| Method, path | Request | Response |
|---|---|---|
| `POST /api/desk/login` | `LoginRequest` `{pin, name}` | 200 `SessionInfo` + `Set-Cookie`; 401 `bad_pin`; 429; 503 `desk_disabled` when `TEPHRA_DESK_PIN` unset |
| `POST /api/desk/logout` | none | 204, cookie cleared |
| `GET /api/desk/me` | none | `SessionInfo` or 401 |
| `GET /api/desk/advisories?status=DRAFT` | none | `AdvisoryList` (default status DRAFT, newest first) |
| `POST /api/desk/advisories/{id}/approve` | `DecisionRequest` `{version}` | `Advisory` (APPROVED); 409 `version_conflict`/`invalid_transition`; 404 |
| `POST /api/desk/advisories/{id}/edit` | `EditRequest` `{version, body}` | `Advisory` (EDITED); 422 `validation_failed` |
| `POST /api/desk/advisories/{id}/reject` | `RejectRequest` `{version, reason}` | `Advisory` (REJECTED); 422 when reason too short |

The actor recorded is `desk:<SessionInfo.name>`.

### 8.6 Task endpoint

`POST /tasks/tick` with header `X-Tephra-Task-Token: <TEPHRA_TASK_TOKEN>` -> 200 `TickReport`
(with `skipped=true` if a tick is already running); 403 `forbidden` when the header is
missing or wrong or the token is unset. Cloud Scheduler calls it every minute.
