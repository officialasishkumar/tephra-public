"""Whole ticks through ``run_tick`` on recorded feed responses.

Stub LLM, SQLite under ``tmp_path``, a fixed clock and no network: every URL TEPHRA asks for
is answered from ``tests/fixtures`` (fetched 2026-10-09 19:36-19:44Z, see its README) or
refused with a ``FetchError``, as an unreachable host would be. The clock stands at 19:40Z,
when four Indonesian VA SIGMETs were valid (Krakatau, Semeru, Dukono, Ibu).
"""

import asyncio
import itertools
import json
import time
from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from tephra import pipeline as pipeline_module
from tephra.agents.llm import get_llm
from tephra.config import PROJECT_ROOT, Settings
from tephra.desk import audit
from tephra.desk.approvals import SYSTEM_ACTOR, list_advisories
from tephra.desk.failures import (
    DRAFT_WAITING,
    NEWER_FAILURE,
    REPLAY_RUN_ENDED,
    list_failures,
)
from tephra.feeds import registry
from tephra.feeds.adsb import MAX_CACHED_COPY_AGE_S
from tephra.feeds.airports import load_airports
from tephra.feeds.base import FetchError, FetchResult, HttpSource, Source, build_url
from tephra.feeds.jma_volcano import JMA_EQVOL_URL
from tephra.feeds.registry import due_feeds, initial_health
from tephra.feeds.routes import load_routes
from tephra.feeds.volcanoes import load_volcanoes
from tephra.geo.cone import covers_official
from tephra.models import (
    ActionKind,
    AdsbQueryPoint,
    Advisory,
    AdvisoryStatus,
    AiFailure,
    AuditAction,
    DiscrepancyKind,
    DutyRun,
    FeedHealth,
    FeedId,
    FeedStatus,
    FrameProduct,
    PlumeMode,
    RunMode,
    SseEvent,
    TickReport,
    TraceStage,
)
from tephra.pipeline import Runtime
from tephra.policy import load_policy
from tephra.scheduler import run_adsb_pass, run_local_scheduler, run_tick
from tephra.store.base import Collection
from tephra.store.sqlite_store import SqliteStore
from tephra.util import timeutil
from tephra.util.events import EventBus
from tephra.util.hashing import proxy_flight_number, sha256_bytes
from tephra.util.timeutil import FixedClock, use_clock


async def tick_and_work(runtime: Runtime, *, reason: str) -> TickReport:
    """A tick, then the AI work it made due (the AI worker runs that off the tick), with
    what the work did added to the tick's report."""
    report = await run_tick(runtime, reason=reason)
    work = await runtime.worker.drain()
    for name in COUNTED:
        setattr(report, name, getattr(report, name) + getattr(work, name))
    report.notes += work.notes
    return report


COUNTED = (
    "assessments_run",
    "satellite_reads",
    "recovery_plans",
    "duty_runs",
    "drafts_created",
    "drafts_superseded",
)


FIXTURES = Path(__file__).parent / "fixtures"
DATA_DIR = PROJECT_ROOT / "data"
POLICY = load_policy(DATA_DIR)
ROUTES = load_routes(DATA_DIR)
AT = datetime(2026, 10, 9, 19, 40, tzinfo=UTC)

KRAKATAU, SEMERU, DUKONO, IBU = "262000", "263300", "268010", "268030"

ADSB_PREFIX = "https://api.adsb.lol/v2/point/"
CACHED_AGE_S = 60
"""Age of a last-good copy served after a live failure (recent enough to be used)."""
SIGMET_FEED_URL = "https://aviationweather.gov/api/data/isigmet?format=json&hazard=va"
FVAU02_URL = "https://tgftp.nws.noaa.gov/data/raw/fv/fvau02.adrm..txt"
OPEN_METEO = "https://api.open-meteo.com/v1/forecast?"
KRAKATAU_WINDS = f"{OPEN_METEO}latitude=-6.10&longitude=105.42"
SEMERU_WINDS = f"{OPEN_METEO}latitude=-8.11&longitude=112.92"
CONNECT_TIMEOUT = "ConnectTimeout: timed out"
"""How ``HttpSource`` words a host that never accepted the connection."""

# Darwin's Semeru advisory as served by NOAA tgftp, quoted in research/05 section 3.7.
FVAU02_SEMERU = """FVAU02 ADRM 091820
VA ADVISORY
DTG: 20261009/1820Z
VAAC: DARWIN
VOLCANO: SEMERU 263300
ADVISORY NR: 2026/1157
INFO SOURCE: HIMAWARI-9, CVGHM
ERUPTION DETAILS: VA TO FL150 OBS AT 09/1800Z, MOV E
OBS VA CLD: SFC/FL150 S0803 E11253 - S0754 E11316 - S0807
        E11324 - S0820 E11318 - S0811 E11253 MOV E 10KT
FCST VA CLD +6 HR: 10/0000Z SFC/FL150 S0803 E11253 - S0753
        E11317 - S0807 E11324 - S0821 E11318 - S0811 E11253
RMK: VA IDENTIFIABLE ON CURRENT SATELLITE IMAGERY MOVING
        EAST. DISCRETE EMISSIONS ARE ONGOING. AREA IS PARTIALLY
        OBSCURED BY MET CLOUD. HEIGHT AND MOVEMENT BASED ON
        SATELLITE IMAGERY, GROUND REPORTS AND MODEL GUIDANCE.
NXT ADVISORY: NO LATER THAN 20261010/0020Z=
"""

MAGMA = "https://magma.esdm.go.id/v1/vona"
JMA_VAAC = "https://ds.data.jma.go.jp/svd/vaac/data/"
JMA_MSC = "https://www.data.jma.go.jp/mscweb/data/himawari/"
VONA_PAGES = {  # magma id: (signature in the list's link, fixture)
    22880: ("9678e5287b728bc1210c62090abbbab47c3fa7e66f72a155954ab56c74cc2d03", "semeru_ash"),
    22881: ("9b1dd1019782c6c6dc83817dc6f9538e08b294a61f3ec41481dbcb4a462b58df", "ibu_ash"),
    22889: ("5412ce61fc8ab19051a3a1682ceb3ec3cfcf9aca8457455414c1cadda2305bad", "semeru_no_ash"),
}
PAGES: dict[str, str] = {
    SIGMET_FEED_URL: "isigmet/isigmet_va.json",
    MAGMA: "magma/vona_list.html",
    **{
        f"{MAGMA}/{magma_id}?signature={signature}": f"magma/vona_{magma_id}_{name}.html"
        for magma_id, (signature, name) in VONA_PAGES.items()
    },
    f"{JMA_VAAC}vaac_list.html": "tokyo_vaac/vaac_list.html",
    f"{JMA_VAAC}vaac_darwin_list.html": "darwin_vaac/vaac_darwin_list.html",
    f"{JMA_MSC}sat_img.php?area=se3": "himawari/jma_mscweb_sat_img_se3.html",
    "https://himawari8.nict.go.jp/img/D531106/latest.json": "himawari/nict_latest.json",
}
PREFIXES: dict[str, str] = {
    OPEN_METEO: "openmeteo/semeru_pressure_level_winds.json",
    "https://aviationweather.gov/api/data/taf?": "wx/taf.json",
    "https://aviationweather.gov/api/data/metar?": "wx/metar.json",
    f"{JMA_MSC}img/se3/se3_b13_": "himawari/jma_se3_b13_1920.jpg",
    f"{JMA_MSC}img/se3/se3_dst_": "himawari/jma_se3_dst_1920.jpg",
}

GIA417 = "8a0123"
"""An airline target at FL120, 35 km east of Semeru's SIGMET polygon, flying west into it."""
AIRCRAFT: list[dict[str, Any]] = [
    {
        "hex": GIA417,
        "flight": "GIA417  ",
        "t": "B738",
        "lat": -8.15,
        "lon": 113.70,
        "alt_baro": 12000,
        "alt_geom": 12400,
        "gs": 420.0,
        "track": 270.0,
        "nav_altitude_mcp": 12000,
        "seen_pos": 0.4,
    },
    {  # same track, above the SFC/FL150 band and its margin
        "hex": "76cd01",
        "flight": "SIA231  ",
        "t": "B77W",
        "lat": -8.15,
        "lon": 113.72,
        "alt_baro": 35000,
        "gs": 480.0,
        "track": 270.0,
        "seen_pos": 0.4,
    },
    {  # inside the band, but general aviation: never a proxy flight
        "hex": "8a0f00",
        "flight": "PKSAM   ",
        "r": "PK-SAM",
        "t": "C208",
        "lat": -8.15,
        "lon": 113.42,
        "alt_baro": 9000,
        "gs": 150.0,
        "track": 270.0,
        "seen_pos": 0.4,
    },
]

PIPELINE_ORDER = [
    TraceStage.POLL,
    TraceStage.SYSTEM,
    TraceStage.DISCREPANCY,
    TraceStage.PLUME,
    TraceStage.CONE,
    TraceStage.EXPOSURE,
    TraceStage.PLANNER,
    TraceStage.DRAFTER,
    TraceStage.DESK,
]


@dataclass
class Gate:
    """Holds requests to one URL prefix: ``arrived`` is set when one comes in, and it goes
    on once the test sets ``release``."""

    arrived: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)


class FixtureSource:
    """Answers feed URLs from ``tests/fixtures``; anything else fails like a dead host.

    ``failing`` URL prefixes raise ``FetchError``, ``unreachable`` ones raise it worded as
    ``HttpSource`` words a connect timeout, ``garbage`` prefixes answer with bytes no parser
    can read, ``stale`` prefixes answer as ``HttpSource`` does from its last-good cache after
    a live failure (``stale_error`` says why), and ``gates`` hold requests until the test
    releases them.
    """

    def __init__(self, aircraft: Sequence[Mapping[str, Any]] = AIRCRAFT) -> None:
        self.aircraft = list(aircraft)
        self.requested: list[str] = []
        self.failing: set[str] = set()
        self.unreachable: set[str] = set()
        self.garbage: set[str] = set()
        self.stale: set[str] = set()
        self.stale_error = "HTTP 429"
        self.gates: dict[str, Gate] = {}

    async def fetch(
        self, url: str, *, feed: FeedId, params: Mapping[str, str] | None = None
    ) -> FetchResult:
        full_url = build_url(url, params)
        self.requested.append(full_url)
        for prefix, gate in self.gates.items():
            if full_url.startswith(prefix):
                gate.arrived.set()
                await gate.release.wait()
        if any(full_url.startswith(prefix) for prefix in self.failing):
            raise FetchError(full_url, feed, "connection refused")
        if any(full_url.startswith(prefix) for prefix in self.unreachable):
            raise FetchError(full_url, feed, CONNECT_TIMEOUT)
        stale = any(full_url.startswith(prefix) for prefix in self.stale)
        fetched_at = timeutil.now() - timedelta(seconds=CACHED_AGE_S if stale else 0)
        if any(full_url.startswith(prefix) for prefix in self.garbage):
            content, content_type = b"<html>Service Unavailable</html>", "text/html"
        else:
            content, content_type = self._answer(full_url, feed, fetched_at)
        return FetchResult(
            feed=feed,
            url=full_url,
            status_code=200,
            content=content,
            content_type=content_type,
            fetched_at=fetched_at,
            sha256=sha256_bytes(content),
            from_cache=stale,
            stale=stale,
            stale_age_s=CACHED_AGE_S if stale else None,
            error=self.stale_error if stale else None,
        )

    async def aclose(self) -> None:
        return None

    def _answer(self, url: str, feed: FeedId, fetched_at: datetime) -> tuple[bytes, str]:
        if url.startswith(ADSB_PREFIX):
            return self._adsb(fetched_at), "application/json"
        if url == FVAU02_URL:
            return FVAU02_SEMERU.encode(), "text/plain"
        if url == JMA_EQVOL_URL:  # JMA's real Atom feed: no eruption report among its entries
            return (FIXTURES / "jma" / "eqvol.xml").read_bytes(), "application/atom+xml"
        name = PAGES.get(url) or next(
            (path for prefix, path in PREFIXES.items() if url.startswith(prefix)), None
        )
        if name is None and url.endswith("_Text.html"):
            name = next(
                (
                    f"{folder}/{page.name}"
                    for folder in ("tokyo_vaac", "darwin_vaac")
                    for page in (FIXTURES / folder).glob("*_Text.html")
                    if url.endswith(f"/{page.name}")
                ),
                None,
            )
        if name is None:
            raise FetchError(url, feed, "not in the fixtures")
        content = (FIXTURES / name).read_bytes()
        kind = {".json": "application/json", ".jpg": "image/jpeg"}.get(Path(name).suffix)
        return content, kind or "text/html; charset=UTF-8"

    def _adsb(self, fetched_at: datetime) -> bytes:
        now_ms = int(fetched_at.timestamp() * 1000)
        body = {"msg": "No error", "now": now_ms, "total": len(self.aircraft), "ac": self.aircraft}
        return json.dumps(body).encode()


def make_settings(tmp_path: Path, **changes: Any) -> Settings:
    return Settings(
        _env_file=None,
        llm="stub",
        store="sqlite",
        sqlite_path=tmp_path / "tephra.sqlite3",
        cache_dir=tmp_path / "cache",
        **{"recovery_auto": False, **changes},
    )


def make_runtime(settings: Settings, source: Source, *, mode: RunMode = RunMode.LIVE) -> Runtime:
    return Runtime(
        settings=settings,
        store=SqliteStore(settings.sqlite_path, settings.cache_dir / "blobs"),
        bus=EventBus(),
        source=source,
        llm=get_llm(settings),
        catalogue=load_volcanoes(DATA_DIR),
        airports=load_airports(DATA_DIR, min_runway_m=POLICY.alternates.min_runway_m.value),
        routes=ROUTES,
        policy=POLICY,
        mode=mode,
        replay_case=None,
        auto_replay=False,
    )


def trace_events(runtime: Runtime) -> list[dict[str, Any]]:
    return [event.data for event in runtime.bus.recent(SseEvent.TRACE, limit=200)]


def point_key(point: AdsbQueryPoint) -> tuple[float, float, int]:
    return point.lat, point.lon, point.radius_nm


def winds_asked(source: FixtureSource) -> list[str]:
    """The Open-Meteo requests made, cut to the volcano's coordinates."""
    asked = [url for url in source.requested if url.startswith(OPEN_METEO)]
    return [url.partition("&hourly=")[0] for url in asked]


def first_index(events: Sequence[Mapping[str, Any]], stage: TraceStage) -> int:
    return next(index for index, event in enumerate(events) if event["stage"] == stage.value)


@pytest.fixture
def clock() -> Iterator[FixedClock]:
    fixed = FixedClock(AT)
    with use_clock(fixed):
        yield fixed


@pytest.fixture
def source() -> FixtureSource:
    return FixtureSource()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
async def runtime(
    settings: Settings, source: FixtureSource, clock: FixedClock
) -> AsyncIterator[Runtime]:
    built = make_runtime(settings, source)
    yield built
    await built.aclose()


# --- one tick, end to end ---------------------------------------------------------------


async def test_one_tick_from_feeds_to_a_draft(runtime: Runtime) -> None:
    report = await tick_and_work(runtime, reason="manual")

    assert not report.skipped
    assert report.feed_errors == {}
    assert report.active_volcano_ids == [KRAKATAU, SEMERU, DUKONO, IBU]
    assert sorted(runtime.situations) == report.active_volcano_ids

    # A SIGMET in force with no current VAA is SILENCE; Semeru's SIGMET repeats Darwin's
    # polygon vertex for vertex (research/13), so the echo is not a disagreement.
    kinds = {vid: [d.kind for d in s.discrepancies] for vid, s in runtime.situations.items()}
    assert kinds == {
        KRAKATAU: [DiscrepancyKind.SILENCE],
        SEMERU: [],
        DUKONO: [DiscrepancyKind.SILENCE],
        IBU: [],
    }

    semeru = runtime.situations[SEMERU]
    assert [layer.kind for layer in semeru.official_layers] == ["SIGMET", "VAA", "VAA"]
    for vid, situation in runtime.situations.items():
        cone = runtime.cones[vid]
        assert situation.official_layers
        assert covers_official(cone, situation.official_layers), vid

    assert sorted(runtime.exposed) == [f"{GIA417}:{SEMERU}"]
    flight = runtime.exposed[f"{GIA417}:{SEMERU}"]
    assert not flight.inside_now
    assert 0 < flight.minutes_to_entry <= 5
    assert flight.cone_id == runtime.cones[SEMERU].id
    assert report.exposed_flights == 1

    advisories = await list_advisories(runtime.store)
    assert [(a.status, a.flight_id) for a in advisories] == [(AdvisoryStatus.DRAFT, flight.id)]
    draft = advisories[0]
    assert draft.cone_id == flight.cone_id
    assert draft.llm_backend == "stub"
    assert not draft.replay
    assert report.drafts_created == 1

    events = trace_events(runtime)
    order = [first_index(events, stage) for stage in PIPELINE_ORDER]
    assert order == sorted(order)
    for_semeru = [
        e["stage"] for e in events if e["volcano_id"] == SEMERU and e["stage"] != "SYSTEM"
    ]
    # Code queues the plume read and holds the official area; the Duty Officer then hands the
    # read to the Satellite Reader and the Plume Reader (the cone is rebuilt), and only then
    # the flight to the Planner and the Drafter.
    assert for_semeru == [
        "PLUME",
        "CONE",
        "EXPOSURE",
        "SATELLITE",
        "SATELLITE",
        "PLUME",
        "CONE",
        "PLANNER",
        "DRAFTER",
        "DESK",
    ]
    duty = [e["message"] for e in events if e["stage"] == "DUTY"]
    assert duty[0].startswith("Duty Officer -> assess_volcanoes")
    assert any(line.startswith("Duty Officer -> plan_flights: RFA") for line in duty)
    assert duty[-1].startswith("Duty Officer brief")
    assert runtime.duty is not None
    assert runtime.duty.outcome == "STUB"
    assert runtime.duty.undispatched == []


async def test_a_flight_the_planner_cannot_plan_goes_to_the_desk_without_a_draft(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No rule-based plan stands in for the model: no advisory, one AI failure, and the
    trace says a dispatcher must handle the flight."""
    real_plan_flight = pipeline_module.plan_flight

    async def failing_plan_flight(*args: Any, **kwargs: Any) -> Any:
        plan = await real_plan_flight(*args, **kwargs)
        return plan.model_copy(
            update={
                "decision": None,
                "fuel": None,
                "outcome": "MODEL_FAILED",
                "validation_errors": ["PLANNER AGENT ERROR: RuntimeError"],
            }
        )

    monkeypatch.setattr(pipeline_module, "plan_flight", failing_plan_flight)
    report = await tick_and_work(runtime, reason="manual")
    assert report.exposed_flights == 1
    assert report.drafts_created == 0
    assert await list_advisories(runtime.store) == []
    failures = await list_failures(runtime.store)
    assert [(f.stage, f.flight_id) for f in failures] == [("planner", f"{GIA417}:{SEMERU}")]
    assert failures[0].reason == "PLANNER AGENT ERROR: RuntimeError"
    messages = [e["message"] for e in trace_events(runtime) if e["level"] == "error"]
    assert any("AI UNAVAILABLE" in message for message in messages)


def failing_planner(monkeypatch: pytest.MonkeyPatch) -> None:
    real_plan_flight = pipeline_module.plan_flight

    async def failing_plan_flight(*args: Any, **kwargs: Any) -> Any:
        plan = await real_plan_flight(*args, **kwargs)
        return plan.model_copy(
            update={
                "decision": None,
                "fuel": None,
                "outcome": "MODEL_FAILED",
                "validation_errors": ["PLANNER AGENT ERROR: RuntimeError"],
            }
        )

    monkeypatch.setattr(pipeline_module, "plan_flight", failing_plan_flight)


async def closings(runtime: Runtime) -> list[tuple[str, str | None]]:
    """(actor, reason) of every AI_FAILURE_CLOSED audit entry, oldest first."""
    entries = await audit.list_entries(runtime.store, limit=100)
    closed = [e for e in entries if e.action is AuditAction.AI_FAILURE_CLOSED]
    return [(e.actor, e.note) for e in reversed(closed)]


async def test_a_draft_for_the_flight_closes_its_ai_failure(
    runtime: Runtime, source: FixtureSource, clock: FixedClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The flight now has advice for a dispatcher: its failure no longer stands, and code (not
    a person) closes it."""
    with monkeypatch.context() as patched:
        failing_planner(patched)
        await tick_and_work(runtime, reason="manual")
    [failure] = await list_failures(runtime.store)
    assert {fid: item.id for fid, item in runtime.open_failures.items()} == {
        failure.flight_id: failure.id
    }

    inside = {**AIRCRAFT[0], "lat": -8.10, "lon": 113.20}  # now inside Semeru's area
    source.aircraft = [inside, *AIRCRAFT[1:]]
    clock.advance(timedelta(seconds=60))
    report = await tick_and_work(runtime, reason="manual")

    assert report.drafts_created == 1
    assert await list_failures(runtime.store) == []
    [closed] = await list_failures(runtime.store, open_only=False)
    assert (closed.closed_reason, closed.handled_by) == (DRAFT_WAITING, None)
    assert runtime.open_failures == {}
    assert await closings(runtime) == [(SYSTEM_ACTOR, DRAFT_WAITING)]


async def test_a_failed_flight_lost_from_the_picture_closes_after_the_grace_time(
    runtime: Runtime, source: FixtureSource, clock: FixedClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The draft retirement rules, applied to a failure: a lost position is POSITION LOST,
    never "no longer exposed"."""
    failing_planner(monkeypatch)
    await tick_and_work(runtime, reason="manual")
    source.aircraft = []
    clock.advance(timedelta(seconds=60))
    await tick_and_work(runtime, reason="manual")
    assert len(await list_failures(runtime.store)) == 1, "kept while the grace time lasts"

    lost_min = runtime.policy.drafts.position_lost_retire_min.value
    clock.advance(timedelta(minutes=lost_min))
    await tick_and_work(runtime, reason="manual")

    assert await list_failures(runtime.store) == []
    assert await closings(runtime) == [(SYSTEM_ACTOR, f"POSITION LOST FOR {lost_min} MIN")]


async def test_a_newer_failure_closes_the_flights_older_one(runtime: Runtime) -> None:
    """One open failure per flight, however many cones and stages failed for it."""
    first = make_failure("AIF-000000000001", cone_id="CONE-000000000001")
    second = make_failure("AIF-000000000002", cone_id="CONE-000000000002")
    assert await runtime.track_failure(first) is not None
    assert await runtime.track_failure(first) is None, "the same failure is stored once"
    assert await runtime.track_failure(second) is not None

    assert [f.id for f in await list_failures(runtime.store)] == [second.id]
    assert runtime.open_failures[second.flight_id].id == second.id
    assert await closings(runtime) == [(SYSTEM_ACTOR, NEWER_FAILURE)]


async def test_a_new_replay_run_closes_the_failures_an_earlier_run_left(
    tmp_path: Path, source: FixtureSource, clock: FixedClock
) -> None:
    """Each replay run plays the recording from its start: failures recorded in an earlier
    run (or before the field existed) close, and the run's own are followed."""
    replay = make_runtime(make_settings(tmp_path), source, mode=RunMode.REPLAY)
    try:
        since = replay.replay_run_since
        assert since is not None
        earlier = make_failure("AIF-000000000001", replay=True, recorded_wall_at=None)
        mine = make_failure(
            "AIF-000000000002", replay=True, flight_id="8a0999:263300", recorded_wall_at=since
        )
        for item in (earlier, mine):
            await replay.store.put(Collection.AI_FAILURES, item.id, item.model_dump(mode="json"))

        await replay.settle_drafts(
            AT, TickReport(started_at=AT, finished_at=AT, mode=RunMode.REPLAY, reason="manual")
        )

        listed = await list_failures(replay.store, open_only=False)
        assert {f.id: f.closed_reason for f in listed} == {
            earlier.id: REPLAY_RUN_ENDED,
            mine.id: None,
        }
        assert list(replay.open_failures) == [mine.flight_id]

        replay.duty = DutyRun(
            id="DUTY-000000000001",
            started_at=AT,
            finished_at=AT,
            replay=True,
            trigger="tick",
            worklist=[],
            outcome="STUB",
            llm_backend="stub",
            model_id="stub",
            prompt_hash="0" * 64,
        )
        replay.follow_replay_clock(
            AT, TickReport(started_at=AT, finished_at=AT, mode=RunMode.REPLAY, reason="manual")
        )
        replay.follow_replay_clock(
            AT - timedelta(hours=1),
            TickReport(started_at=AT, finished_at=AT, mode=RunMode.REPLAY, reason="manual"),
        )
        assert replay.duty is None, "a loop starts a fresh picture: no Duty Officer run yet"
        assert replay.open_failures == {}
        assert replay.replay_run_since is not None
        assert replay.replay_run_since >= since
    finally:
        await replay.aclose()


async def test_a_new_replay_run_retires_the_drafts_an_earlier_run_left(
    tmp_path: Path, source: FixtureSource, clock: FixedClock
) -> None:
    """A replay plays its recording again on every run, and the AI works only after the run's
    first pass: an open REPLAY draft then is an earlier run's, superseded under the system actor
    and never counted as this run's work. A LIVE draft is the live desk's and stays."""
    replay = make_runtime(make_settings(tmp_path), source, mode=RunMode.REPLAY)
    try:
        earlier = make_draft("adv_000000000001", replay=True)
        live = make_draft("adv_000000000002", replay=False, flight_id=f"8a0999:{SEMERU}")
        for item in (earlier, live):
            await replay.store.put(Collection.ADVISORIES, item.id, item.model_dump(mode="json"))
        assert (await replay.system_state()).draft_count == 1, "this mode's drafts only"

        await replay.settle_drafts(
            AT, TickReport(started_at=AT, finished_at=AT, mode=RunMode.REPLAY, reason="manual")
        )

        status = {a.id: a.status for a in await list_advisories(replay.store, limit=10)}
        assert status == {earlier.id: AdvisoryStatus.SUPERSEDED, live.id: AdvisoryStatus.DRAFT}
        entries = await audit.list_entries(replay.store, limit=10)
        retired = [e for e in entries if e.action is AuditAction.SUPERSEDED]
        assert [(e.actor, e.note) for e in retired] == [
            (SYSTEM_ACTOR, pipeline_module.DRAFT_RUN_ENDED)
        ]
        assert (await replay.system_state()).draft_count == 0
    finally:
        await replay.aclose()


def make_draft(
    advisory_id: str, *, replay: bool, flight_id: str = f"{GIA417}:{SEMERU}"
) -> Advisory:
    hex_id = flight_id.split(":")[0]
    return Advisory(
        id=advisory_id,
        version=1,
        status=AdvisoryStatus.DRAFT,
        created_at=AT,
        updated_at=AT,
        replay=replay,
        volcano_id=SEMERU,
        volcano_name="Semeru",
        flight_id=flight_id,
        proxy_flight=proxy_flight_number(hex_id),
        callsign="GIA417",
        hex=hex_id,
        type_icao="B738",
        action=ActionKind.MONITOR,
        minutes_to_entry=14,
        inside_now=False,
        fuel_line="",
        plume_mode=PlumeMode.OFFICIAL,
        confidence=1.0,
        cone_id="CONE-0123456789ab",
        assessment_id="PA-0123456789ab",
        plan_id="PLAN-0123456789ab",
        header="TEPHRA COMPANY ADVISORY - RING OF FIRE AIR (FICTIONAL) - NOT FOR OPERATIONAL USE",
        body="MONITOR. ASH SFC/FL150 AHEAD, ENTRY 14 MIN. REPORT VAR.",
        cost_note="NO EXTRA FUEL",
        sources=[],
        input_hash="0" * 64,
        llm_backend="stub",
        model_id="stub",
        prompt_hashes={},
        dedupe_key=f"DD-{advisory_id[-12:]}",
    )


def make_failure(failure_id: str, **changes: Any) -> AiFailure:
    base = AiFailure(
        id=failure_id,
        created_at=AT,
        replay=False,
        stage="planner",
        reason="PLANNER AGENT ERROR: RuntimeError",
        model_id="stub",
        volcano_id=SEMERU,
        volcano_name="Semeru",
        flight_id=f"{GIA417}:{SEMERU}",
        proxy_flight="RFA0001",
        hex=GIA417,
        cone_id="CONE-000000000001",
        minutes_to_entry=4,
        inside_now=False,
    )
    return base.model_copy(update=changes)


async def test_a_second_tick_does_not_draft_again(runtime: Runtime, clock: FixedClock) -> None:
    await tick_and_work(runtime, reason="manual")
    first = await list_advisories(runtime.store)

    clock.advance(timedelta(seconds=60))
    report = await tick_and_work(runtime, reason="manual")

    assert report.exposed_flights == 1
    assert report.drafts_created == 0
    again = await list_advisories(runtime.store)
    assert [(a.id, a.status, a.version) for a in again] == [
        (a.id, AdvisoryStatus.DRAFT, 1) for a in first
    ]


async def test_a_restarted_runtime_does_not_draft_again(
    runtime: Runtime, settings: Settings, source: FixtureSource, clock: FixedClock
) -> None:
    await tick_and_work(runtime, reason="manual")
    await runtime.aclose()

    clock.advance(timedelta(seconds=60))
    restarted = make_runtime(settings, source)
    await restarted.restore()
    try:
        report = await tick_and_work(restarted, reason="manual")
        advisories = await list_advisories(restarted.store)
    finally:
        await restarted.aclose()
    assert report.drafts_created == 0
    assert [a.status for a in advisories] == [AdvisoryStatus.DRAFT]


async def test_a_restart_reads_planned_marks_left_in_the_older_layout(runtime: Runtime) -> None:
    older = {"mode": "LIVE", "planned": {f"{GIA417}:{SEMERU}": "CONE-0123456789ab"}}
    await runtime.store.put(Collection.RUNTIME, "state", older)

    await runtime.restore()
    report = await tick_and_work(runtime, reason="manual")

    assert report.drafts_created == 1  # planned afresh: the open drafts would have said so


def gia417_at(lon: float) -> list[dict[str, Any]]:
    """GIA417 on its westbound track at FL120, ``lon`` degrees east (the Semeru cone's
    eastern edge is near 113.4 E; at 420 kt a degree of longitude takes about 8.5 min)."""
    return [{**AIRCRAFT[0], "lon": lon}]


async def test_a_monitor_given_far_out_is_planned_again_as_the_entry_nears(
    runtime: Runtime, source: FixtureSource, clock: FixedClock
) -> None:
    source.aircraft = gia417_at(118.1)  # 40 min out
    await tick_and_work(runtime, reason="manual")
    [far] = await list_advisories(runtime.store)
    source.aircraft = gia417_at(114.6)  # 11 min out, same cone
    clock.advance(timedelta(minutes=1))
    nearer = await tick_and_work(runtime, reason="manual")
    source.aircraft = gia417_at(115.6)  # back out to 19 min: less urgent, not planned again
    clock.advance(timedelta(minutes=1))
    later = await tick_and_work(runtime, reason="manual")

    assert (far.action, far.minutes_to_entry) == (ActionKind.MONITOR, 40)
    advisories = {advisory.id: advisory for advisory in await list_advisories(runtime.store)}
    assert advisories[far.id].status is AdvisoryStatus.SUPERSEDED
    [near] = [a for a in advisories.values() if a.status is AdvisoryStatus.DRAFT]
    assert (near.action, near.minutes_to_entry, near.cone_id) == (
        ActionKind.DIVERT,
        11,
        far.cone_id,
    )
    assert (nearer.drafts_created, nearer.drafts_superseded) == (1, 1)
    assert (later.drafts_created, later.drafts_superseded) == (0, 0)


async def test_entering_the_cone_replaces_a_draft_even_with_the_same_advice(
    runtime: Runtime, source: FixtureSource, clock: FixedClock
) -> None:
    await tick_and_work(runtime, reason="manual")  # 3 min out: DIVERT WARR
    [outside] = await list_advisories(runtime.store)
    source.aircraft = gia417_at(113.3)  # inside the cone now: DIVERT WARR again
    clock.advance(timedelta(minutes=1))
    await tick_and_work(runtime, reason="manual")

    advisories = {advisory.id: advisory for advisory in await list_advisories(runtime.store)}
    assert advisories[outside.id].status is AdvisoryStatus.SUPERSEDED
    [inside] = [a for a in advisories.values() if a.status is AdvisoryStatus.DRAFT]
    assert inside.dedupe_key == outside.dedupe_key
    assert (outside.inside_now, inside.inside_now) == (False, True)


async def test_an_unchanged_situation_keeps_its_assessment_past_the_horizon(
    tmp_path: Path, source: FixtureSource, clock: FixedClock
) -> None:
    runtime = make_runtime(make_settings(tmp_path, default_horizon_h=1.0), source)
    try:
        await tick_and_work(runtime, reason="manual")
        first = runtime.assessments[SEMERU]
        clock.advance(timedelta(minutes=70))  # past the one-hour horizon
        await tick_and_work(runtime, reason="manual")
        kept = runtime.assessments[SEMERU]
        clock.advance(timedelta(hours=2))  # 3 h 10 min after the first ask
        await tick_and_work(runtime, reason="manual")
        asked = runtime.assessments[SEMERU]
    finally:
        await runtime.aclose()

    assert runtime.situations[SEMERU].input_hash == first.input_hash
    assert kept is first
    assert asked.created_at == AT + timedelta(minutes=190)


async def test_true_colour_frames_are_shown_but_never_sent_to_the_model(runtime: Runtime) -> None:
    await tick_and_work(runtime, reason="manual")
    semeru = runtime.situations[SEMERU]
    jma = semeru.frames[0]
    blob = await runtime.store.get_blob(jma.image_key)
    assert blob is not None
    nict = jma.model_copy(
        update={
            "product": FrameProduct.TRUE_COLOR,
            "image_key": "frames/263300_TRUE_COLOR_20261009T1930Z.png",
            "provenance": jma.provenance.model_copy(
                update={"source_id": "FRAME:TRUE_COLOR:263300:20261009T1930Z"}
            ),
        }
    )
    await runtime.store.put_blob(nict.image_key, blob[0], "image/png")
    runtime.situations[SEMERU] = semeru.model_copy(update={"frames": [*semeru.frames, nict]})

    parts = await runtime._images(runtime.situations[SEMERU])
    wall = await runtime.wall_snapshot()

    # research/05 does not clear NICT's imagery for the model step; the Wall still shows it.
    assert [part.label for part in parts] == [frame.provenance.source_id for frame in semeru.frames]
    assert nict.provenance.source_id in {thumb.source_id for thumb in wall.overlays.frames}


async def test_with_live_vonas_a_non_observation_is_never_a_conflict(
    tmp_path: Path, clock: FixedClock
) -> None:
    runtime = make_runtime(make_settings(tmp_path, vona_live=True), FixtureSource())
    try:
        await tick_and_work(runtime, reason="manual")
    finally:
        await runtime.aclose()
    semeru = runtime.situations[SEMERU]
    assert {vona.ash_observed for vona in semeru.vonas} == {True, False}
    assert semeru.discrepancies
    every = [d for s in runtime.situations.values() for d in s.discrepancies]
    assert DiscrepancyKind.CONFLICT not in {d.kind for d in every}
    assert runtime.live.health[FeedId.VONA].status is FeedStatus.OK


# --- feed health ------------------------------------------------------------------------


async def test_vona_reads_disabled_with_its_reason_when_live_polling_is_off(
    runtime: Runtime, source: FixtureSource
) -> None:
    await tick_and_work(runtime, reason="manual")

    feeds = {state.feed: state for state in (await runtime.system_state()).feeds}
    assert feeds[FeedId.VONA].status is FeedStatus.DISABLED
    assert "robots.txt" in (feeds[FeedId.VONA].last_error or "")
    assert feeds[FeedId.HSD].status is FeedStatus.DISABLED
    assert not [url for url in source.requested if "magma.esdm.go.id" in url]


def test_a_replay_polls_recorded_vonas_even_with_live_polling_off(settings: Settings) -> None:
    assert not settings.vona_live
    replay_health = initial_health(settings, replay=True)
    assert replay_health[FeedId.VONA].status is FeedStatus.NEVER
    assert FeedId.VONA in due_feeds(AT, replay_health, settings, active=False, replay=True)
    assert FeedId.VONA not in due_feeds(AT, replay_health, settings, active=False)


async def test_a_restart_keeps_vona_disabled_after_a_run_that_polled_it(
    tmp_path: Path, source: FixtureSource, clock: FixedClock
) -> None:
    polled = make_runtime(make_settings(tmp_path, vona_live=True), source)
    await tick_and_work(polled, reason="manual")
    await polled.aclose()
    assert polled.live.health[FeedId.VONA].status is FeedStatus.OK

    restarted = make_runtime(make_settings(tmp_path), source)
    try:
        await restarted.restore()
        vona = {state.feed: state for state in (await restarted.system_state()).feeds}[FeedId.VONA]
    finally:
        await restarted.aclose()
    assert vona.status is FeedStatus.DISABLED


# --- tick safety ------------------------------------------------------------------------


async def test_a_tick_that_finds_another_running_is_skipped_as_busy(
    runtime: Runtime, source: FixtureSource
) -> None:
    gate = source.gates[SIGMET_FEED_URL] = Gate()
    first = asyncio.create_task(run_tick(runtime, reason="manual"))
    await asyncio.wait_for(gate.arrived.wait(), 5)

    second = await run_tick(runtime, reason="scheduler")
    gate.release.set()
    done = await first

    assert second.skipped
    assert any("busy" in note for note in second.notes)
    assert not done.skipped
    assert (await runtime.worker.drain()).drafts_created == 1


async def test_a_tick_waits_for_an_adsb_pass_instead_of_being_lost(
    runtime: Runtime, source: FixtureSource, clock: FixedClock
) -> None:
    await tick_and_work(runtime, reason="manual")
    clock.advance(timedelta(seconds=60))
    gate = source.gates[ADSB_PREFIX] = Gate()
    adsb_pass = asyncio.create_task(run_adsb_pass(runtime))
    await asyncio.wait_for(gate.arrived.wait(), 5)

    tick = asyncio.create_task(run_tick(runtime, reason="scheduler"))
    await asyncio.sleep(0.05)
    gate.release.set()
    await adsb_pass
    report = await tick

    assert not report.skipped
    assert FeedId.SIGMET in report.feeds_polled


async def test_a_failing_feed_does_not_abort_the_tick(
    runtime: Runtime, source: FixtureSource
) -> None:
    source.failing.add("https://ds.data.jma.go.jp/svd/vaac/data/vaac_list.html")
    source.garbage.add(SIGMET_FEED_URL)

    report = await tick_and_work(runtime, reason="manual")

    assert set(report.feed_errors) == {FeedId.SIGMET.value, FeedId.VAAC_TOKYO.value}
    for feed in (FeedId.SIGMET, FeedId.VAAC_TOKYO):
        health = runtime.live.health[feed]
        assert health.status is FeedStatus.ERROR
        assert health.last_error == report.feed_errors[feed.value]
    assert runtime.live.health[FeedId.VAAC_DARWIN].status is FeedStatus.OK
    # Darwin's current VAA alone keeps Semeru active, and the rest of the tick still runs.
    assert report.active_volcano_ids == [SEMERU]
    assert report.drafts_created == 1


async def test_one_volcanos_unreadable_winds_do_not_cost_the_others_theirs(
    runtime: Runtime, source: FixtureSource
) -> None:
    source.garbage.add("https://api.open-meteo.com/v1/forecast?latitude=-6.10&longitude=105.42")

    report = await tick_and_work(runtime, reason="manual")

    assert sorted(runtime.live.winds) == [SEMERU, DUKONO, IBU]
    assert runtime.live.covered[FeedId.WINDS] == {SEMERU, DUKONO, IBU}
    health = runtime.live.health[FeedId.WINDS]
    assert health.status is FeedStatus.STALE
    assert health.last_error == report.feed_errors[FeedId.WINDS.value]
    assert "1 of 4 volcanoes" in health.last_error
    assert "Anak Krakatau" in health.last_error


async def test_a_volcano_served_from_the_last_good_copy_is_named(
    runtime: Runtime, source: FixtureSource
) -> None:
    source.stale.add(SEMERU_WINDS)  # throttled; the cache answers for Semeru alone

    report = await tick_and_work(runtime, reason="manual")

    health = runtime.live.health[FeedId.WINDS]
    assert health.status is FeedStatus.STALE
    assert health.last_error == report.feed_errors[FeedId.WINDS.value]
    assert health.last_error == "last good copy served for Semeru"


async def test_a_host_that_times_out_is_skipped_for_the_rest_of_the_poll(
    runtime: Runtime, source: FixtureSource
) -> None:
    source.unreachable.add(SEMERU_WINDS)  # Open-Meteo stops answering after Anak Krakatau

    report = await tick_and_work(runtime, reason="manual")

    assert winds_asked(source) == [KRAKATAU_WINDS, SEMERU_WINDS]
    assert sorted(runtime.live.winds) == [KRAKATAU]
    health = runtime.live.health[FeedId.WINDS]
    assert health.status is FeedStatus.STALE
    assert health.last_error == report.feed_errors[FeedId.WINDS.value]
    assert health.last_error == (
        f"1 of 4 volcanoes failed (Semeru: {CONNECT_TIMEOUT}); "
        "2 skipped while api.open-meteo.com did not answer (Dukono, Ibu)"
    )


async def test_a_host_httpsource_cannot_reach_is_asked_once_per_poll(
    tmp_path: Path, clock: FixedClock
) -> None:
    asked: list[str] = []

    def never_connects(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        raise httpx.ConnectTimeout("timed out", request=request)

    transport = httpx.MockTransport(never_connects)
    source = HttpSource(cache_dir=tmp_path / "http", retries=0, transport=transport)
    runtime = make_runtime(make_settings(tmp_path), source)
    runtime.live.active = {vid: ["test"] for vid in (KRAKATAU, SEMERU, DUKONO, IBU)}
    try:
        result = await registry.poll(FeedId.WINDS, runtime)
    finally:
        await runtime.aclose()

    assert len(asked) == 1
    assert result.error == "ConnectTimeout: timed out"


async def test_a_host_that_answered_from_cache_after_a_timeout_is_skipped_too(
    runtime: Runtime, source: FixtureSource
) -> None:
    source.stale.add(KRAKATAU_WINDS)
    source.stale_error = "ReadTimeout: timed out"

    await tick_and_work(runtime, reason="manual")

    assert winds_asked(source) == [KRAKATAU_WINDS]
    health = runtime.live.health[FeedId.WINDS]
    assert health.status is FeedStatus.STALE
    assert health.last_error == (
        "3 skipped while api.open-meteo.com did not answer (Semeru, Dukono, Ibu); "
        "last good copy served for Anak Krakatau"
    )


async def test_a_hung_host_costs_the_tick_one_bounded_wait(
    tmp_path: Path, source: FixtureSource, clock: FixedClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(registry, "POLL_BUDGET_SHARE", 0.2)  # 2 s of a 10 s tick
    source.gates[OPEN_METEO] = Gate()  # accepts the request and never answers
    runtime = make_runtime(make_settings(tmp_path, tick_interval_s=10), source)
    try:
        report = await asyncio.wait_for(run_tick(runtime, reason="manual"), 10)
        work = await runtime.worker.drain()
    finally:
        await runtime.aclose()

    assert report.feed_errors[FeedId.WINDS.value] == "no answer within 2 s"
    assert runtime.live.health[FeedId.WINDS].status is FeedStatus.ERROR
    assert work.drafts_created == 1  # every other step of the tick ran, and its AI work after


@dataclass
class TimedRuntime:
    """Just what ``run_local_scheduler`` touches: a tick that takes ``tick_s`` seconds."""

    settings: SimpleNamespace
    tick_s: float
    starts: list[float] = field(default_factory=list)

    async def tick(self, *, reason: str = "scheduler") -> None:
        self.starts.append(time.monotonic())
        await asyncio.sleep(self.tick_s)


async def test_the_local_loop_ticks_every_interval_not_interval_plus_tick() -> None:
    runtime = TimedRuntime(settings=SimpleNamespace(tick_interval_s=0.25), tick_s=0.15)
    stop = asyncio.Event()
    loop = asyncio.create_task(run_local_scheduler(runtime, stop))  # type: ignore[arg-type]
    await asyncio.sleep(0.9)
    stop.set()
    await loop

    gaps = [later - earlier for earlier, later in itertools.pairwise(runtime.starts)]
    assert len(runtime.starts) >= 4
    assert max(gaps) < 0.33


async def test_extra_adsb_passes_are_timed_from_the_start_of_the_tick(
    tmp_path: Path, source: FixtureSource, clock: FixedClock
) -> None:
    runtime = make_runtime(make_settings(tmp_path, tick_interval_s=11, cadence_adsb_s=1), source)
    await tick_and_work(runtime, reason="manual")  # makes volcanoes active; schedules no pass
    gate = source.gates[SIGMET_FEED_URL] = Gate()
    asyncio.get_running_loop().call_later(0.6, gate.release.set)
    clock.advance(timedelta(seconds=60))
    try:
        await tick_and_work(runtime, reason="local")  # takes 0.6 s; one pass due 1 s after it began
        polled = len(source.requested)
        await asyncio.sleep(0.6)
        passes = [url for url in source.requested[polled:] if url.startswith(ADSB_PREFIX)]
    finally:
        await runtime.aclose()
    assert passes


async def test_adsb_from_the_last_good_cache_does_not_count_as_fresh_positions(
    runtime: Runtime, source: FixtureSource, clock: FixedClock
) -> None:
    await tick_and_work(runtime, reason="manual")
    [draft] = await list_advisories(runtime.store)

    # adsb.lol throttles; the cache serves a recent copy, from before the flight was seen.
    source.stale.add(ADSB_PREFIX)
    source.aircraft = []
    notes: list[str] = []
    for _ in range(2):
        clock.advance(timedelta(seconds=60))
        report = await tick_and_work(runtime, reason="manual")
        notes += report.notes

    assert runtime.live.health[FeedId.ADSB].status is FeedStatus.STALE
    assert runtime.live.adsb_at == AT
    assert any("ADS-B is stale" in note for note in notes)
    [kept] = await list_advisories(runtime.store)
    assert (kept.id, kept.status) == (draft.id, AdvisoryStatus.DRAFT)


async def test_a_flight_seen_only_in_stale_copies_gets_no_draft(
    runtime: Runtime, source: FixtureSource, clock: FixedClock
) -> None:
    source.aircraft = []
    await tick_and_work(runtime, reason="manual")  # live answers, and nothing in the sky
    source.stale.add(ADSB_PREFIX)  # then every point answers from the last-good cache
    source.aircraft = list(AIRCRAFT)
    clock.advance(timedelta(seconds=30))
    report = await tick_and_work(runtime, reason="manual")

    assert await list_advisories(runtime.store) == []
    assert runtime.exposed == {}
    assert any("ADS-B is stale" in note for note in report.notes)


async def test_stale_copies_of_every_point_retire_no_draft(
    runtime: Runtime, source: FixtureSource, clock: FixedClock
) -> None:
    await tick_and_work(runtime, reason="manual")
    [draft] = await list_advisories(runtime.store)
    source.stale.add(ADSB_PREFIX)
    source.aircraft = []  # the copies no longer show the flight
    for _ in range(2):  # two runs inside ADS-B's stale age, as a retirement needs
        clock.advance(timedelta(seconds=30))
        await tick_and_work(runtime, reason="manual")

    [kept] = await list_advisories(runtime.store)
    assert (kept.id, kept.status) == (draft.id, AdvisoryStatus.DRAFT)
    assert f"{GIA417}:{SEMERU}" in runtime.exposed


async def test_stale_positions_keep_no_exposure_to_a_cone_that_is_gone(
    runtime: Runtime, source: FixtureSource, clock: FixedClock
) -> None:
    await tick_and_work(runtime, reason="manual")
    source.stale.add(ADSB_PREFIX)
    clock.advance(timedelta(hours=6))  # Semeru's SIGMET and VAA have run out
    report = await tick_and_work(runtime, reason="manual")

    assert SEMERU not in report.active_volcano_ids
    assert runtime.exposed == {}


async def test_one_failed_adsb_point_keeps_the_others_fresh_and_its_own_aircraft(
    runtime: Runtime, source: FixtureSource, clock: FixedClock
) -> None:
    await tick_and_work(runtime, reason="manual")
    before = {point_key(snapshot.query): snapshot for snapshot in runtime.live.adsb}
    failed = next(key for key in before if key[0] > 0)  # the Halmahera circle
    source.failing.add(f"{ADSB_PREFIX}{failed[0]:.3f}/{failed[1]:.3f}/")
    clock.advance(timedelta(seconds=60))
    report = await tick_and_work(runtime, reason="manual")

    after = {point_key(snapshot.query): snapshot for snapshot in runtime.live.adsb}
    assert set(after) == set(before)
    assert after[failed] == before[failed]
    fresh = [snapshot for key, snapshot in after.items() if key != failed]
    assert {s.provenance.fetched_at for s in fresh} == {AT + timedelta(seconds=60)}
    assert runtime.live.adsb_at == AT
    health = runtime.live.health[FeedId.ADSB]
    assert health.status is FeedStatus.STALE
    assert health.last_error == report.feed_errors[FeedId.ADSB.value]
    assert "1 of" in (health.last_error or "")
    assert f"{GIA417}:{SEMERU}" in runtime.exposed


async def test_a_situation_is_stored_again_only_when_it_changes(
    runtime: Runtime, clock: FixedClock
) -> None:
    await tick_and_work(runtime, reason="manual")
    silence = runtime.situations[KRAKATAU].discrepancies[0]
    written: list[str] = []
    put = runtime.store.put

    async def counting_put(collection: str, doc_id: str, doc: Mapping[str, Any]) -> None:
        written.append(f"{collection}/{doc_id}")
        await put(collection, doc_id, doc)

    runtime.store.put = counting_put  # type: ignore[method-assign]
    for _ in range(3):
        clock.advance(timedelta(seconds=60))
        await tick_and_work(runtime, reason="manual")

    # Only the SILENCE minutes moved; a silent volcano would cost 1,440 writes a day.
    later = runtime.situations[KRAKATAU].discrepancies[0]
    assert (later.id, later.kind) == (silence.id, DiscrepancyKind.SILENCE)
    assert later.magnitude != silence.magnitude
    assert [doc for doc in written if doc.startswith("situations/")] == []


async def test_a_lasting_partial_failure_is_traced_once(
    runtime: Runtime, source: FixtureSource, clock: FixedClock
) -> None:
    source.failing.add("https://api.open-meteo.com/v1/forecast?latitude=-6.10&longitude=105.42")
    for _ in range(3):
        await tick_and_work(runtime, reason="manual")
        clock.advance(timedelta(minutes=61))

    warnings = [
        event["message"]
        for event in trace_events(runtime)
        if event["stage"] == "POLL" and event["detail"].get("feed") == FeedId.WINDS.value
    ]
    assert len(warnings) == 1
    assert warnings[0].startswith("Winds: 1 of 4 volcanoes failed (Anak Krakatau")


@pytest.mark.parametrize(
    ("feed", "active", "elapsed_s", "due"),
    [
        (FeedId.SIGMET, False, 55, True),  # 60 s cadence, 5 s slack for a 60 s tick
        (FeedId.SIGMET, False, 50, False),
        (FeedId.ADSB, True, 25, True),
        (FeedId.ADSB, False, 100, False),  # four times slower with nothing active
        (FeedId.ADSB, False, 115, True),
        (FeedId.WINDS, False, 7200, False),  # per-volcano feeds wait for an active volcano
        (FeedId.WINDS, True, 1800, False),
        (FeedId.WINDS, True, 3595, True),
        (FeedId.HSD, True, 7200, False),  # TEPHRA_SCIENCE is off
    ],
)
def test_due_feeds_follows_each_cadence(
    settings: Settings, feed: FeedId, active: bool, elapsed_s: int, due: bool
) -> None:
    last = AT - timedelta(seconds=elapsed_s)
    states = {
        feed: FeedHealth(
            feed=feed,
            status=FeedStatus.OK,
            cadence_s=settings.cadence_s(feed),
            last_attempt_at=last,
        )
    }
    assert (feed in due_feeds(AT, states, settings, active=active)) is due


async def test_forced_polls_of_a_lasting_gap_back_off(
    runtime: Runtime, source: FixtureSource, clock: FixedClock
) -> None:
    source.failing.add(KRAKATAU_WINDS)  # the one volcano whose winds never come
    polled: list[int] = []
    for minute in range(17):
        report = await tick_and_work(runtime, reason="manual")
        if FeedId.WINDS in report.feeds_polled:
            polled.append(minute)
        clock.advance(timedelta(minutes=1))

    # The first retry waits GAP_RETRY_S (2 min); each later one as long as the gap has lasted.
    assert polled == [0, 2, 4, 8, 16]


async def test_positions_held_through_an_outage_expire_like_a_cached_copy(
    runtime: Runtime, source: FixtureSource, clock: FixedClock
) -> None:
    await tick_and_work(runtime, reason="manual")
    [draft] = await list_advisories(runtime.store)
    source.failing.add(ADSB_PREFIX)  # adsb.lol unreachable, nothing cached

    clock.advance(timedelta(seconds=60))
    await tick_and_work(runtime, reason="manual")
    assert f"{GIA417}:{SEMERU}" in runtime.exposed  # a minute-old position still stands

    clock.advance(timedelta(seconds=MAX_CACHED_COPY_AGE_S))
    report = await tick_and_work(runtime, reason="manual")
    assert runtime.live.adsb == []
    assert runtime.exposed == {}
    assert any("ADS-B is stale" in note for note in report.notes)
    [kept] = await list_advisories(runtime.store)
    assert (kept.id, kept.status) == (draft.id, AdvisoryStatus.DRAFT)


async def test_positions_expire_when_a_hung_adsb_poll_is_cut_short(
    tmp_path: Path, source: FixtureSource, clock: FixedClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = make_runtime(make_settings(tmp_path, tick_interval_s=10), source)
    try:
        await tick_and_work(runtime, reason="manual")
        monkeypatch.setattr(registry, "POLL_BUDGET_SHARE", 0.05)  # 0.5 s of a 10 s tick
        source.gates[ADSB_PREFIX] = Gate()  # adsb.lol accepts and never answers
        clock.advance(timedelta(seconds=MAX_CACHED_COPY_AGE_S + 1))
        report = await asyncio.wait_for(run_tick(runtime, reason="manual"), 10)
    finally:
        await runtime.aclose()

    assert report.feed_errors[FeedId.ADSB.value] == "no answer within 0.5 s"
    assert runtime.live.adsb == []
    assert runtime.exposed == {}
