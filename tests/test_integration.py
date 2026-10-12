"""The wiring of the extensions into the runtime: reroutes, the Satellite Reader gate, JMA
reports and pasted notices in the live picture, the automatic recovery run, and the budget.

The feature modules have their own tests; these check that the pipeline calls them when, and
only when, it should. Everything runs on the stub LLM and a fixed clock, with no network.
"""

from collections.abc import AsyncIterator, Iterator, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_notices import CATALOGUE, ScriptedLlm, indonesian, text_of
from test_pipeline import (
    AT,
    DATA_DIR,
    SEMERU,
    FixtureSource,
    make_runtime,
    make_settings,
    tick_and_work,
)

from tephra.agents.notice_reader import read_notice
from tephra.agents.plume_reader import build_parts
from tephra.agents.satellite_reader import SatelliteReading
from tephra.feeds import registry
from tephra.feeds.base import FetchError, FetchResult, build_url
from tephra.feeds.jma_volcano import JMA_EQVOL_URL
from tephra.geo.units import destination_point, nm_to_km
from tephra.models import (
    FeedId,
    FeedStatus,
    HazardCone,
    PlumeMode,
    RerouteStatus,
    RunMode,
    SseEvent,
    TickReport,
    TraceStage,
    polygon_from_latlon,
)
from tephra.pipeline import Runtime
from tephra.recovery.network import run_lock
from tephra.store.base import Collection
from tephra.util.hashing import sha256_bytes
from tephra.util.timeutil import FixedClock, use_clock

JMA_DIR = Path(__file__).parent / "fixtures" / "jma"
VFVO52 = "20261008050115_0_VFVO52_400000.xml"
DATA_URL = "https://www.data.jma.go.jp/developer/xml/data/"


@pytest.fixture
def clock() -> Iterator[FixedClock]:
    fixed = FixedClock(AT)
    with use_clock(fixed):
        yield fixed


@pytest.fixture
async def semeru(tmp_path: Path, clock: FixedClock) -> AsyncIterator[Runtime]:
    runtime = make_runtime(make_settings(tmp_path), FixtureSource())
    await tick_and_work(runtime, reason="manual")
    yield runtime
    await runtime.aclose()


# --- reroutes ---------------------------------------------------------------------------


async def test_planning_stores_every_reroute_option_and_the_wall_draws_them(
    semeru: Runtime,
) -> None:
    assert semeru.exposed, "the fixture aircraft must be exposed"
    stored = await semeru.store.list_docs(Collection.REROUTES)
    assert stored
    held = [option for options in semeru.reroutes.values() for option in options]
    assert {doc["id"] for doc in stored} == {option.id for option in held}
    for flight_id, options in semeru.reroutes.items():
        assert flight_id in semeru.exposed
        assert {o.kind.value for o in options} == {"REJOIN_TRACK", "DIRECT_DEST"}

    snapshot = await semeru.wall_snapshot()
    features = snapshot.reroutes["features"]
    drawn = [o for o in held if len(o.path) >= 2]
    paths = [f for f in features if f["properties"]["feature"] == "path"]
    assert len(paths) == len(drawn)
    for item in paths:
        props = item["properties"]
        assert item["geometry"]["type"] == "LineString"
        assert props["flight_id"] in semeru.exposed
        assert props["proxy_flight"] == semeru.exposed[props["flight_id"]].proxy_flight
        assert {"kind", "status", "route_string", "extra_nm", "extra_min", "side"} <= set(props)
        assert props["waypoint_labels"] == [
            f["properties"]["label"]
            for f in features
            if f["properties"]["feature"] == "waypoint"
            and f["id"].startswith(item["id"].removesuffix("#path"))
        ]
    event = semeru.bus.last(SseEvent.REROUTES)
    assert event is not None
    assert event.data["features"] == features


async def test_reroutes_of_a_flight_that_leaves_the_cone_leave_the_wall(semeru: Runtime) -> None:
    assert semeru.reroutes
    semeru.exposed.clear()
    semeru._keep_current_reroutes()
    assert semeru.reroutes == {}
    assert (await semeru.wall_snapshot()).reroutes["features"] == []


async def test_a_reroute_computed_for_an_old_cone_is_dropped(semeru: Runtime) -> None:
    flight_id, options = next(iter(semeru.reroutes.items()))
    stale = [options[0].model_copy(update={"cone_id": "CONE-ffffffffffff"})]
    semeru.reroutes[flight_id] = stale
    semeru._keep_current_reroutes()
    assert flight_id not in semeru.reroutes


async def test_the_planner_gets_the_routes_and_the_situation(semeru: Runtime) -> None:
    plans = await semeru.store.list_docs(Collection.PLANS)
    assert plans
    # The option ids are stable per flight, cone and kind: the planner's context and the
    # stored documents are the same options.
    assert all(option.id.startswith("RR-") for o in semeru.reroutes.values() for option in o)
    assert any(
        option.status is not RerouteStatus.NOT_EXPOSED
        for options in semeru.reroutes.values()
        for option in options
    )


# --- Satellite Reader -------------------------------------------------------------------


async def test_the_satellite_reader_runs_once_per_new_scan_before_the_plume_reader(
    semeru: Runtime,
) -> None:

    reading = semeru.satellite[SEMERU]
    assert reading.status == "read"
    assert reading.label == "NO MODEL"  # the stub backend
    stored = await semeru.store.get(Collection.SAT_READINGS, reading.id)
    assert stored is not None
    assert SatelliteReading.model_validate(stored).id == reading.id
    events = [e for e in semeru.bus.recent(SseEvent.SATELLITE) if e.data["volcano_id"] == SEMERU]
    assert [e.data["id"] for e in events] == [reading.id]
    snapshot = await semeru.wall_snapshot()
    on_wall = {item["volcano_id"]: item["id"] for item in snapshot.satellite}
    assert on_wall[SEMERU] == reading.id
    # Ibu's picture needs no model call (no CAUTION, no airline aircraft), so no scan was read.
    assert set(on_wall) < set(semeru.situations)

    situation = semeru.situations[SEMERU]
    again = TickReport(started_at=AT, finished_at=AT, mode=RunMode.LIVE, reason="t")
    second = await semeru._with_satellite(situation, again)
    assert again.satellite_reads == 0, "the same scan is not read twice"
    assert reading.id in second.source_ids()
    assert [item.source_id for item in second.supporting] == [reading.id]
    assert second.input_hash == situation.input_hash, "evidence never triggers a Plume Reader call"


async def test_a_newer_scan_is_read_again(semeru: Runtime) -> None:
    held = semeru.satellite[SEMERU]
    newer = []
    for frame in semeru.live.frames[SEMERU]:
        moved = frame.model_copy(
            update={
                "observed_at": frame.observed_at + timedelta(minutes=10),
                "provenance": frame.provenance.model_copy(
                    update={"source_id": frame.provenance.source_id + "-next"}
                ),
            }
        )
        newer.append(moved)
        blob = await semeru.store.get_blob(frame.image_key)
        assert blob is not None
        await semeru.store.put_blob(moved.image_key, blob[0], "image/png")
    semeru.live.frames[SEMERU] = newer
    report = TickReport(started_at=AT, finished_at=AT, mode=RunMode.LIVE, reason="t")
    situation = await semeru._with_satellite(semeru.situations[SEMERU], report)
    assert report.satellite_reads == 1
    assert semeru.satellite[SEMERU].id != held.id
    assert situation.supporting


async def test_no_dust_frame_means_no_reading_and_no_call(semeru: Runtime) -> None:
    semeru.satellite.clear()
    semeru.live.frames[SEMERU] = []
    report = TickReport(started_at=AT, finished_at=AT, mode=RunMode.LIVE, reason="t")
    situation = await semeru._with_satellite(semeru.situations[SEMERU], report)
    assert report.satellite_reads == 0
    assert SEMERU not in semeru.satellite
    assert situation.supporting == []


async def test_the_plume_reader_is_shown_the_satellite_reading_and_may_cite_it(
    semeru: Runtime,
) -> None:
    reading = semeru.satellite[SEMERU]
    report = TickReport(started_at=AT, finished_at=AT, mode=RunMode.LIVE, reason="t")
    situation = await semeru._with_satellite(semeru.situations[SEMERU], report)
    texts = "\n".join(part.text or "" for part in build_parts(situation, []))
    assert "SUPPORTING EVIDENCE" in texts
    assert f"[{reading.id}]" in texts
    assert reading.id in situation.source_ids()
    plain = "\n".join(part.text or "" for part in build_parts(semeru.situations[SEMERU], []))
    assert "SUPPORTING EVIDENCE" not in plain


# --- JMA reports and pasted notices -----------------------------------------------------


class JmaSource:
    """JMA's Atom feed listing one real eruption report, and that report."""

    def __init__(self) -> None:
        self.requested: list[str] = []
        self.entry = f"{DATA_URL}{VFVO52}"

    async def fetch(
        self, url: str, *, feed: FeedId, params: Mapping[str, str] | None = None
    ) -> FetchResult:
        full_url = build_url(url, params)
        self.requested.append(full_url)
        if full_url == JMA_EQVOL_URL:
            content = (
                '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>t</title>'
                f'<updated>2026-10-08T05:01:15Z</updated><link href="{self.entry}"/></entry></feed>'
            ).encode()
        elif full_url == self.entry:
            content = (JMA_DIR / VFVO52).read_bytes()
        else:
            raise FetchError(full_url, feed, "not in the fixtures")
        return FetchResult(
            feed=feed,
            url=full_url,
            status_code=200,
            content=content,
            content_type="application/xml",
            fetched_at=datetime(2026, 10, 8, 5, 30, tzinfo=UTC),
            sha256=sha256_bytes(content),
        )

    async def aclose(self) -> None:
        return None


async def test_a_jma_eruption_report_joins_the_picture_like_a_vona(tmp_path: Path) -> None:
    with use_clock(FixedClock(datetime(2026, 10, 8, 5, 30, tzinfo=UTC))):
        source = JmaSource()
        runtime = make_runtime(make_settings(tmp_path), source)  # type: ignore[arg-type]
        try:
            result = await registry.poll(FeedId.JMA_VOLCANO, runtime)
            assert result.ok
            assert result.new_record_count == 1
            (key,) = [k for k in runtime.live.vonas if k.startswith("JMA-VFVO52-")]
            vona = runtime.live.vonas[key]
            assert vona.provenance.feed is FeedId.JMA_VOLCANO
            assert vona.ash_observed
            assert runtime.live.health[FeedId.JMA_VOLCANO].status is FeedStatus.OK
            assert runtime.live.health[FeedId.JMA_VOLCANO].record_count == 1
            assert await runtime.store.get(Collection.VONAS, key) is not None
            active = runtime.refresh_active(datetime(2026, 10, 8, 5, 30, tzinfo=UTC))
            assert any("VONA" in reason for reasons in active.values() for reason in reasons)

            again = await registry.poll(FeedId.JMA_VOLCANO, runtime)
            assert again.new_record_count == 0
            assert source.requested.count(source.entry) == 1, "a known report is not fetched again"
        finally:
            await runtime.aclose()


async def test_jma_and_magma_pollers_do_not_drop_each_others_records(tmp_path: Path) -> None:
    """They run side by side in a tick; each merges into the same dict."""
    with use_clock(FixedClock(AT)):
        runtime = make_runtime(make_settings(tmp_path, vona_live=True), FixtureSource())
        try:
            await tick_and_work(runtime, reason="manual")
            feeds = {vona.provenance.feed for vona in runtime.live.vonas.values()}
            assert FeedId.VONA in feeds
            assert runtime.live.health[FeedId.JMA_VOLCANO].status is FeedStatus.OK
            assert runtime.live.health[FeedId.VONA].record_count == len(
                [v for v in runtime.live.vonas.values() if v.provenance.feed is FeedId.VONA]
            )
        finally:
            await runtime.aclose()


async def test_a_verified_notice_joins_the_live_picture(semeru: Runtime) -> None:
    with use_clock(FixedClock(datetime(2026, 10, 11, 20, 30, tzinfo=UTC))):
        reading = await read_notice(
            text_of("synthetic_id_ash_seen.txt"), ScriptedLlm([indonesian()]), CATALOGUE
        )
    assert reading.vona is not None
    await semeru.add_verified_notice(reading.vona)
    key = reading.vona.provenance.source_id
    assert semeru.live.vonas[key] is reading.vona
    assert await semeru.store.get(Collection.VONAS, key) is not None
    # A MAGMA poll neither counts it nor expires it early.
    assert registry._is_magma(reading.vona) is False


# --- automatic recovery -----------------------------------------------------------------


def cone_over(lat: float, lon: float) -> HazardCone:
    ring = [destination_point(lat, lon, bearing, nm_to_km(12.0)) for bearing in range(0, 360, 45)]
    return HazardCone(
        id="CONE-0123456789ab",
        volcano_id="262000",
        assessment_id="PA-0123456789ab",
        mode=PlumeMode.OFFICIAL,
        confidence=0.9,
        llm_backend="stub",
        created_at=AT,
        horizon_h=6.0,
        valid_to=AT + timedelta(hours=6),
        geometry=polygon_from_latlon(ring),
        base_ft=0,
        top_ft=40_000,
        official_source_ids=["SIGMET:WIIF:1"],
    )


async def test_the_recovery_agent_runs_once_when_the_closed_airports_change(
    tmp_path: Path, clock: FixedClock
) -> None:
    """A changed set of closed airports is queued for the Duty Officer, which hands it to the
    recovery agent once; the same set is not queued again."""
    runtime = make_runtime(make_settings(tmp_path, recovery_auto=True), FixtureSource())
    try:
        jakarta = runtime.airports.get("WIII")
        assert jakarta is not None
        report = TickReport(started_at=AT, finished_at=AT, mode=RunMode.LIVE, reason="t")

        await runtime.run_recovery(AT, report)  # first look, nothing closed: only recorded
        assert runtime.recovery_due is None
        assert runtime._closed_airports == frozenset()

        runtime.cones["262000"] = cone_over(jakarta.lat, jakarta.lon)
        await runtime.run_recovery(AT, report)
        assert runtime.recovery_due is not None
        assert report.recovery_plans == 0  # queued, not run: the Duty Officer dispatches it
        runtime.last_tick = report  # the AI worker works once the picture has been built
        work = await runtime.worker.drain()
        duty = runtime.duty
        assert duty is not None
        assert [d.tool for d in duty.dispatches] == ["run_recovery"]
        assert work.recovery_plans == 1
        assert not runtime.worker.recovery_queued(), "the AI worker ran the queued recovery"
        plans = await runtime.store.list_docs(Collection.RECOVERY)
        assert len(plans) == 1
        assert plans[0]["status"] == "DRAFT"
        assert plans[0]["llm_backend"] == "stub"
        event = runtime.bus.last(SseEvent.RECOVERY)
        assert event is not None
        assert event.data["id"] == plans[0]["id"]
        assert runtime.bus.last(SseEvent.BUDGET) is not None
        assert "WIII" in (runtime._closed_airports or frozenset())
        assert runtime._bookkeeping()["closed_airports"] == sorted(runtime._closed_airports or [])

        await runtime.run_recovery(AT, report)  # the same set: nothing queued
        assert runtime.recovery_due is None
        assert len(await runtime.store.list_docs(Collection.RECOVERY)) == 1

        runtime.cones.clear()  # airports reopen: recorded, nothing planned
        await runtime.run_recovery(AT, report)
        assert runtime.recovery_due is None
        assert runtime._closed_airports == frozenset()
        stages = [e.data["stage"] for e in runtime.bus.recent(SseEvent.TRACE, limit=200)]
        assert TraceStage.RECOVERY.value in stages
    finally:
        await runtime.aclose()


async def test_a_queued_recovery_counts_the_closures_it_ran_on(
    tmp_path: Path, clock: FixedClock
) -> None:
    """Review of 28e8b20, item 6: a recovery queued for one set of airports ran on the set of
    the moment but recorded the queued set, so the next tick queued a second run over the same
    airports. It now records the set it planned for."""
    runtime = make_runtime(make_settings(tmp_path, recovery_auto=True), FixtureSource())
    try:
        jakarta = runtime.airports.get("WIII")
        surabaya = runtime.airports.get("WARR")
        assert jakarta is not None
        assert surabaya is not None
        report = TickReport(started_at=AT, finished_at=AT, mode=RunMode.LIVE, reason="t")
        await runtime.run_recovery(AT, report)
        runtime.cones["262000"] = cone_over(jakarta.lat, jakarta.lon)
        await runtime.run_recovery(AT, report)
        queued = runtime.start_recovery(report)["airports"]
        assert "WARR" not in queued

        runtime.cones["263300"] = cone_over(surabaya.lat, surabaya.lon)  # while it waits
        await runtime.recover_queued(queued)
        closed = runtime._closed_airports or frozenset()
        assert {"WIII", "WARR"} <= closed
        assert len(await runtime.store.list_docs(Collection.RECOVERY)) == 1

        await runtime.run_recovery(AT, report)
        assert runtime.recovery_due is None, "the run covered the new set: no second run"
    finally:
        await runtime.aclose()


async def test_recovery_is_off_when_the_setting_says_so(tmp_path: Path, clock: FixedClock) -> None:
    runtime = make_runtime(make_settings(tmp_path), FixtureSource())  # recovery_auto=False
    try:
        jakarta = runtime.airports.get("WIII")
        assert jakarta is not None
        runtime.cones["262000"] = cone_over(jakarta.lat, jakarta.lon)
        report = TickReport(started_at=AT, finished_at=AT, mode=RunMode.LIVE, reason="t")
        await runtime.run_recovery(AT, report)
        assert report.recovery_plans == 0
        assert runtime._closed_airports is None
    finally:
        await runtime.aclose()


async def test_a_desk_run_in_progress_covers_the_change(tmp_path: Path, clock: FixedClock) -> None:
    runtime = make_runtime(make_settings(tmp_path, recovery_auto=True), FixtureSource())
    try:
        jakarta = runtime.airports.get("WIII")
        assert jakarta is not None
        runtime.cones["262000"] = cone_over(jakarta.lat, jakarta.lon)
        report = TickReport(started_at=AT, finished_at=AT, mode=RunMode.LIVE, reason="t")
        async with run_lock(runtime):
            await runtime.run_recovery(AT, report)
        assert report.recovery_plans == 0
        assert await runtime.store.list_docs(Collection.RECOVERY) == []
    finally:
        await runtime.aclose()


async def test_a_restart_restores_the_closed_set_so_it_does_not_replan(
    tmp_path: Path, clock: FixedClock
) -> None:
    settings = make_settings(tmp_path, recovery_auto=True)
    first = make_runtime(settings, FixtureSource())
    first._closed_airports = frozenset({"WIII"})
    await first.checkpoint(force=True)
    await first.aclose()

    second = make_runtime(settings, FixtureSource())
    try:
        await second.restore()
        assert second._closed_airports == frozenset({"WIII"})
    finally:
        await second.aclose()


# --- budget -----------------------------------------------------------------------------


async def test_every_tick_publishes_the_budget(semeru: Runtime) -> None:
    event = semeru.bus.last(SseEvent.BUDGET)
    assert event is not None
    tiers = {tier["tier"]: tier for tier in event.data["tiers"]}
    assert set(tiers) == {"main", "lite", "tts"}
    assert tiers["main"]["used"] == 0  # the stub spends no quota
    assert tiers["main"]["limit"] == semeru.settings.daily_budget(semeru.settings.model)
    models = {model["model_id"]: model for model in event.data["models"]}
    assert set(models) == {
        semeru.settings.model,
        semeru.settings.model_lite,
        semeru.settings.model_tts,
    }
    assert event.data["backend"] == "stub"


def test_the_runtime_loads_the_routes_and_the_data_files_exist() -> None:
    assert (DATA_DIR / "routes_apac.json").is_file()
