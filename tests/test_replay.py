"""Replay cases: the manifest, the replay clock, ``ReplaySource``, recording, and labelled
REPLAY runs.

The case under test is made the way ``scripts/record_replay.py`` makes one: a live runtime
whose source is a ``RecordingSource`` around the feeds (here the fixture feeds of
``test_pipeline``), ticked twice a minute apart, then ``manifest`` and ``write_manifest``.
"""

import asyncio
import shutil
import time
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from test_pipeline import (
    ADSB_PREFIX,
    AIRCRAFT,
    AT,
    DATA_DIR,
    GIA417,
    SEMERU,
    SIGMET_FEED_URL,
    FixtureSource,
    Gate,
    make_runtime,
    make_settings,
    tick_and_work,
)

from tephra.api import server
from tephra.config import Settings
from tephra.desk.approvals import list_advisories
from tephra.feeds.base import FetchError, RecordingSource
from tephra.feeds.registry import NOT_RECORDED_NOTE
from tephra.feeds.sigmet import SIGMET_PARAMS, SIGMET_URL
from tephra.models import (
    AdvisoryStatus,
    DiscrepancyKind,
    FeedId,
    FeedStatus,
    ReplayCase,
    RunMode,
    SessionInfo,
    SseEvent,
)
from tephra.pipeline import Runtime, create_runtime
from tephra.replay.cases import (
    MANIFEST_NAME,
    ReplaySource,
    case_path,
    list_cases,
    load_case,
    replay_banner,
    replay_info,
    select_case,
    start_replay_clock,
    stop_replay_clock,
)
from tephra.scheduler import STOPPED_NOTE, run_adsb_pass, run_tick
from tephra.util import timeutil
from tephra.util.events import EventBus
from tephra.util.hashing import sha256_bytes
from tephra.util.timeutil import FixedClock, SystemClock, use_clock

CASE_ID = "semeru-fixtures"
LABEL = "Semeru, fixture feeds of 9 Oct 2026"
BANNER = "REPLAY: recorded real feeds from 09 Oct 2026"


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    for name in ("volcanoes.json", "airports.json", "routes_apac.json"):
        shutil.copy(DATA_DIR / name, data / name)
    shutil.copytree(DATA_DIR / "policy", data / "policy")
    return data


@pytest.fixture(autouse=True)
def restore_clock() -> Iterator[None]:
    """REPLAY installs a process-wide clock; put back whatever was there before."""
    with use_clock(timeutil.get_clock()):
        yield


async def record_case(
    data_dir: Path, workdir: Path, aircraft: Sequence[Mapping[str, Any]] = AIRCRAFT
) -> ReplayCase:
    """Two ticks a minute apart through ``RecordingSource``, VONAs included."""
    recorder = RecordingSource(FixtureSource(aircraft), case_path(data_dir, CASE_ID))
    clock = FixedClock(AT)
    with use_clock(clock):
        runtime = make_runtime(make_settings(workdir, vona_live=True), recorder)
        try:
            await tick_and_work(runtime, reason="record")
            clock.advance(timedelta(seconds=60))
            await tick_and_work(runtime, reason="record")
        finally:
            await runtime.aclose()
    case = recorder.manifest(case_id=CASE_ID, label=LABEL, region="java_bali")
    recorder.write_manifest(case)
    return case


def replay_settings(data_dir: Path, workdir: Path, **changes: object) -> Settings:
    return make_settings(
        workdir, mode=RunMode.REPLAY, replay_case=CASE_ID, data_dir=data_dir, **changes
    )


def replay_runtime(case: ReplayCase, settings: Settings) -> Runtime:
    runtime = make_runtime(
        settings,
        ReplaySource(case_path(settings.data_dir, case.case_id), case),
        mode=RunMode.REPLAY,
    )
    runtime.replay_case = case
    return runtime


# --- recording --------------------------------------------------------------------------


async def test_recording_source_keeps_exactly_what_the_live_fetch_returned(
    tmp_path: Path,
) -> None:
    inner = FixtureSource()
    recorder = RecordingSource(inner, tmp_path / "case")
    with use_clock(FixedClock(AT)):
        live = await recorder.fetch(SIGMET_URL, feed=FeedId.SIGMET, params=SIGMET_PARAMS)
        inner.stale.add(ADSB_PREFIX)
        cached = await recorder.fetch(f"{ADSB_PREFIX}-8.200/113.600/250", feed=FeedId.ADSB)

    assert cached.from_cache
    [record] = recorder.records  # a last-good copy was not fetched in the window
    assert record.url == live.url == SIGMET_FEED_URL
    assert (tmp_path / "case" / record.path).read_bytes() == live.content
    assert record.sha256 == live.sha256 == sha256_bytes(live.content)
    assert (record.feed, record.fetched_at, record.status_code) == (FeedId.SIGMET, AT, 200)
    assert record.content_type == live.content_type


async def test_a_recorded_case_loads_with_its_manifest(data_dir: Path, tmp_path: Path) -> None:
    case = await record_case(data_dir, tmp_path / "record")

    loaded = load_case(data_dir, CASE_ID)
    assert loaded == case
    assert (loaded.recorded_from, loaded.recorded_to) == (AT, AT + timedelta(seconds=60))
    assert {record.feed for record in loaded.records} >= {
        FeedId.SIGMET,
        FeedId.VONA,
        FeedId.VAAC_DARWIN,
        FeedId.ADSB,
    }
    assert [item.case_id for item in list_cases(data_dir)] == [CASE_ID]
    assert select_case(data_dir, None) == case
    assert replay_banner(case) == BANNER


# --- cases and their errors -------------------------------------------------------------


def test_a_missing_case_fails_with_a_clear_error(data_dir: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no replay case under"):
        select_case(data_dir, None)
    with pytest.raises(FileNotFoundError, match=r"replay case 'semeru-gone' has no manifest"):
        load_case(data_dir, "semeru-gone")
    with pytest.raises(ValueError, match="invalid replay case id"):
        load_case(data_dir, "../secrets")


async def test_a_manifest_moved_to_another_directory_is_not_offered(
    data_dir: Path, tmp_path: Path
) -> None:
    await record_case(data_dir, tmp_path / "record")
    case_path(data_dir, CASE_ID).rename(case_path(data_dir, "semeru-renamed"))

    with pytest.raises(ValueError, match="names case"):
        load_case(data_dir, "semeru-renamed")
    assert list_cases(data_dir) == []
    with pytest.raises(FileNotFoundError):
        select_case(data_dir, None)


# --- ReplaySource -----------------------------------------------------------------------


async def test_replay_source_serves_the_recording_as_of_the_replay_clock(
    data_dir: Path, tmp_path: Path
) -> None:

    case = await record_case(data_dir, tmp_path / "record")
    source = ReplaySource(case_path(data_dir, CASE_ID), case)
    adsb_url = next(record.url for record in case.records if record.feed is FeedId.ADSB)
    fetched: dict[timedelta, datetime] = {}
    for offset in (timedelta(minutes=-5), timedelta(seconds=30), timedelta(minutes=5)):
        with use_clock(FixedClock(AT + offset)):
            result = await source.fetch(adsb_url, feed=FeedId.ADSB)
        assert result.replay
        assert result.sha256 == sha256_bytes(result.content)
        fetched[offset] = result.fetched_at

    # Before the recording starts: its first answer; then the latest one at or before now.
    assert fetched == {
        timedelta(minutes=-5): AT,
        timedelta(seconds=30): AT,
        timedelta(minutes=5): AT + timedelta(seconds=60),
    }


async def test_replay_source_refuses_what_it_cannot_vouch_for(
    data_dir: Path, tmp_path: Path
) -> None:
    case = await record_case(data_dir, tmp_path / "record")
    case_dir = case_path(data_dir, CASE_ID)
    sigmet = next(record for record in case.records if record.feed is FeedId.SIGMET)
    outside = sigmet.model_copy(update={"url": "https://example.org/x", "path": "../../x"})
    source = ReplaySource(case_dir, case.model_copy(update={"records": [*case.records, outside]}))

    with use_clock(FixedClock(AT)):
        with pytest.raises(FetchError, match="not recorded"):
            await source.fetch("https://example.org/never", feed=FeedId.SIGMET)
        with pytest.raises(FetchError, match="leaves the case directory"):
            await source.fetch("https://example.org/x", feed=FeedId.SIGMET)
        (case_dir / sigmet.path).write_bytes(b"[]")
        with pytest.raises(FetchError, match="sha256"):
            await source.fetch(SIGMET_URL, feed=FeedId.SIGMET, params=SIGMET_PARAMS)


# --- the replay clock -------------------------------------------------------------------


def test_the_replay_clock_starts_at_the_recording_and_moves() -> None:
    case = ReplayCase(
        case_id=CASE_ID,
        label=LABEL,
        recorded_from=AT,
        recorded_to=AT + timedelta(hours=1),
        region="java_bali",
        records=[],
    )
    start_replay_clock(case, speed=3600.0)  # one recorded hour per second
    first = timeutil.now()
    time.sleep(0.05)
    later = timeutil.now()
    stop_replay_clock()

    assert AT <= first < AT + timedelta(seconds=30)
    assert timedelta(seconds=60) < later - first < timedelta(minutes=30)
    assert isinstance(timeutil.get_clock(), SystemClock)


# --- labelled REPLAY runs ---------------------------------------------------------------


async def test_a_replay_run_is_labelled_everywhere(data_dir: Path, tmp_path: Path) -> None:
    await record_case(data_dir, tmp_path / "record")
    settings = replay_settings(data_dir, tmp_path / "replay")
    assert not settings.vona_live

    runtime = await create_runtime(settings)
    runtime.bus = EventBus()
    try:
        report = await runtime.tick(reason="manual")
        await runtime.worker.drain()
        state = await runtime.system_state()
        advisories = await list_advisories(runtime.store)
    finally:
        await runtime.aclose()

    assert report.mode is RunMode.REPLAY
    assert state.mode is RunMode.REPLAY
    assert state.replay is not None
    assert (state.replay.case_id, state.replay.banner, state.replay.auto) == (
        CASE_ID,
        BANNER,
        False,
    )
    assert all(feed.replay for feed in state.feeds)
    # MAGMA is never polled live here, but the recorded VONAs are served.
    assert runtime.live.health[FeedId.VONA].status is FeedStatus.OK
    assert runtime.live.vonas
    for situation in runtime.situations.values():
        assert situation.mode is RunMode.REPLAY
        assert all(provenance.replay for provenance in situation.provenances())
    assert [(a.hex, a.replay) for a in advisories] == [(GIA417, True)]
    published = runtime.bus.last(SseEvent.STATE)
    assert published is not None
    assert published.data["replay"]["banner"] == BANNER
    traces = runtime.bus.recent(SseEvent.TRACE, limit=200)
    assert traces
    assert all(event.data["detail"].get("replay") is True for event in traces)


async def test_when_the_replay_clock_loops_the_replay_starts_over(
    data_dir: Path, tmp_path: Path
) -> None:
    case = await record_case(data_dir, tmp_path / "record")
    clock = FixedClock(AT + timedelta(seconds=60))
    with use_clock(clock):
        runtime = replay_runtime(case, replay_settings(data_dir, tmp_path / "replay"))
        try:
            await tick_and_work(runtime, reason="manual")
            clock.set(AT)  # the recording ran out and the clock wrapped to its start
            report = await tick_and_work(runtime, reason="manual")
        finally:
            await runtime.aclose()

    assert FeedId.SIGMET in report.feeds_polled
    assert any("from the start" in note for note in report.notes)
    polled = {feed: runtime.live.health[feed].last_attempt_at for feed in report.feeds_polled}
    assert set(polled.values()) == {AT}
    assert SEMERU in runtime.situations


async def test_a_replay_admits_no_notice_issued_after_its_clock(
    data_dir: Path, tmp_path: Path
) -> None:
    case = await record_case(data_dir, tmp_path / "record")
    # 16:40Z: before VONA 22889 (18:00Z) and VAA DARWIN 2026/1157 (18:20Z) were issued, while
    # the only snapshots recorded are from 19:40Z.
    at = AT - timedelta(hours=3)
    with use_clock(FixedClock(at)):
        runtime = replay_runtime(case, replay_settings(data_dir, tmp_path / "replay"))
        try:
            await tick_and_work(runtime, reason="manual")
        finally:
            await runtime.aclose()

    issued = sorted(vona.issued_at for vona in runtime.live.vonas.values())
    assert issued  # 22880 (8 Oct 21:03Z) and 22881 (9 Oct 01:37Z) were out by then
    assert issued[-1] <= at
    assert all(vaa.issued_at <= at for vaa in runtime.live.vaas.values())


async def test_switching_to_replay_relabels_the_wall_at_once(
    data_dir: Path, tmp_path: Path
) -> None:
    await record_case(data_dir, tmp_path / "record")
    settings = make_settings(tmp_path / "live", data_dir=data_dir, replay_case=CASE_ID)
    with use_clock(FixedClock(AT + timedelta(days=3))):
        runtime = make_runtime(settings, FixtureSource())
    try:
        await runtime.switch_mode(RunMode.REPLAY)
        published = runtime.bus.last(SseEvent.STATE)
    finally:
        await runtime.aclose()

    assert published is not None
    assert published.data["mode"] == "REPLAY"
    assert published.data["replay"]["banner"] == BANNER


async def test_a_switch_that_fails_leaves_live_polling_live(data_dir: Path, tmp_path: Path) -> None:
    case = await record_case(data_dir, tmp_path / "record")
    backwards = case.model_copy(update={"recorded_to": case.recorded_from - timedelta(hours=1)})
    (case_path(data_dir, CASE_ID) / MANIFEST_NAME).write_text(backwards.model_dump_json())
    live = FixtureSource()
    runtime = make_runtime(make_settings(tmp_path / "live", data_dir=data_dir), live)
    try:
        # A backwards window fails when the manifest is read, so no case is left to play.
        with pytest.raises(ValidationError, match="recorded_to is before recorded_from"):
            load_case(data_dir, CASE_ID)
        with pytest.raises(FileNotFoundError, match="no replay case"):
            await runtime.switch_mode(RunMode.REPLAY)
        assert (runtime.mode, runtime.source) == (RunMode.LIVE, live)
    finally:
        await runtime.aclose()


async def test_a_tick_that_switches_to_replay_reports_on_one_clock(
    data_dir: Path, tmp_path: Path
) -> None:
    await record_case(data_dir, tmp_path / "record")
    settings = make_settings(
        tmp_path / "live",
        data_dir=data_dir,
        replay_case=CASE_ID,
        auto_replay=True,
        auto_replay_after_ticks=1,
    )
    quiet = FixtureSource()
    quiet.failing.add("https://")  # nothing answers, so nothing is active
    with use_clock(FixedClock(AT + timedelta(days=3))):
        runtime = make_runtime(settings, quiet)
        try:
            await tick_and_work(runtime, reason="manual")
            report = await tick_and_work(runtime, reason="manual")
        finally:
            await runtime.aclose()

    assert report.mode is RunMode.REPLAY
    assert any("REPLAY" in note for note in report.notes)
    assert report.duration_ms >= 0
    assert report.started_at < AT + timedelta(days=1)


async def test_a_switch_takes_its_case_under_the_lock(data_dir: Path, tmp_path: Path) -> None:
    case = await record_case(data_dir, tmp_path / "record")
    source = FixtureSource()
    gate = source.gates[SIGMET_FEED_URL] = Gate()
    runtime = make_runtime(make_settings(tmp_path / "live", data_dir=data_dir), source)
    try:
        tick = asyncio.create_task(run_tick(runtime, reason="manual"))
        await asyncio.wait_for(gate.arrived.wait(), 5)
        switch = asyncio.create_task(runtime.switch_mode(RunMode.REPLAY, case=case))
        await asyncio.sleep(0.05)
        while_ticking = (runtime.mode, runtime.replay_case, (await runtime.system_state()).replay)
        gate.release.set()
        await tick
        await switch
    finally:
        await runtime.aclose()

    assert while_ticking == (RunMode.LIVE, None, None)
    assert (runtime.mode, runtime.replay_case) == (RunMode.REPLAY, case)


async def test_a_switch_that_fails_keeps_the_case_playing(data_dir: Path, tmp_path: Path) -> None:
    case = await record_case(data_dir, tmp_path / "record")
    outside = case.model_copy(update={"case_id": "../outside"})
    with use_clock(FixedClock(AT)):
        runtime = replay_runtime(case, replay_settings(data_dir, tmp_path / "replay"))
        try:
            with pytest.raises(ValueError, match="invalid replay case id"):
                await runtime.switch_mode(RunMode.REPLAY, case=outside)
            state = await runtime.system_state()
        finally:
            await runtime.aclose()

    assert runtime.replay_case == case
    assert state.replay is not None
    assert state.replay.case_id == CASE_ID


async def test_the_desk_names_a_replay_case_only_once_it_plays(
    data_dir: Path, tmp_path: Path
) -> None:
    case = await record_case(data_dir, tmp_path / "record")
    settings = make_settings(tmp_path / "live", data_dir=data_dir)
    runtime = make_runtime(settings, FixtureSource())
    request = server.ModeRequest(mode=RunMode.REPLAY, case_id=CASE_ID)
    session = SessionInfo(name="Ana K", expires_at=AT + timedelta(days=365))
    try:
        async with runtime.lock:  # a tick is running
            switch = asyncio.create_task(server.switch_mode(request, session, runtime, settings))
            await asyncio.sleep(0.05)
            while_ticking = runtime.replay_case
        response = await switch
    finally:
        await runtime.aclose()

    assert while_ticking is None
    assert response.status_code == 200
    assert (runtime.mode, runtime.replay_case) == (RunMode.REPLAY, case)


async def test_a_desk_switch_stops_a_tick_waiting_on_a_feed(data_dir: Path, tmp_path: Path) -> None:
    """A LIVE tick can wait minutes on public feeds; a person's switch at the Desk does not wait
    for it: the tick stops and the switch is made at once."""
    case = await record_case(data_dir, tmp_path / "record")
    settings = make_settings(tmp_path / "live", data_dir=data_dir)
    source = FixtureSource()
    gate = source.gates[SIGMET_FEED_URL] = Gate()
    runtime = make_runtime(settings, source)
    request = server.ModeRequest(mode=RunMode.REPLAY, case_id=CASE_ID)
    session = SessionInfo(name="Ana K", expires_at=AT + timedelta(days=365))
    try:
        tick = asyncio.create_task(run_tick(runtime, reason="manual"))
        await asyncio.wait_for(gate.arrived.wait(), 5)
        response = await asyncio.wait_for(
            server.switch_mode(request, session, runtime, settings), 5
        )
        report = await asyncio.wait_for(tick, 5)
    finally:
        gate.release.set()
        await runtime.aclose()

    assert response.status_code == 200
    assert (runtime.mode, runtime.replay_case) == (RunMode.REPLAY, case)
    assert report.skipped
    assert report.notes == [STOPPED_NOTE]
    assert runtime.tick_task is None
    assert not runtime.tick_running


async def test_a_replay_leaves_the_live_desks_drafts_alone(data_dir: Path, tmp_path: Path) -> None:
    case = await record_case(data_dir, tmp_path / "record", aircraft=[])  # an empty sky
    clock = FixedClock(AT)
    with use_clock(clock):
        live = make_runtime(make_settings(tmp_path / "desk", data_dir=data_dir), FixtureSource())
        try:
            await tick_and_work(live, reason="manual")
            [draft] = await list_advisories(live.store)
        finally:
            await live.aclose()
        replay = replay_runtime(case, replay_settings(data_dir, tmp_path / "desk"))
        try:
            for _ in range(2):  # two exposure runs without the flight, as a retirement needs
                clock.advance(timedelta(seconds=30))
                await tick_and_work(replay, reason="manual")
            kept = await list_advisories(replay.store)
        finally:
            await replay.aclose()

    assert [(advisory.id, advisory.status) for advisory in kept] == [
        (draft.id, AdvisoryStatus.DRAFT)
    ]


SEMERU_CASE = "semeru-20260923"


@pytest.mark.skipif(
    not (case_path(DATA_DIR, SEMERU_CASE) / MANIFEST_NAME).is_file(),
    reason="the semeru-20260923 replay case is not in this checkout",
)
async def test_the_semeru_case_puts_the_vona_against_the_official_movement(
    tmp_path: Path,
) -> None:
    settings = make_settings(
        tmp_path,
        mode=RunMode.REPLAY,
        replay_case=SEMERU_CASE,
        data_dir=DATA_DIR,
        replay_start=datetime(2026, 9, 25, 16, 0, tzinfo=UTC),
    )
    runtime = await create_runtime(settings)
    runtime.bus = EventBus()
    try:
        await runtime.tick(reason="manual")
        state = await runtime.system_state()
    finally:
        await runtime.aclose()

    [mismatch] = [
        item
        for item in runtime.situations[SEMERU].discrepancies
        if item.kind is DiscrepancyKind.DIRECTION_MISMATCH and item.aspect == "direction"
    ]
    assert mismatch.magnitude == 135.0
    assert "moving N vs SIGMET WAAF 12 = VAA DARWIN 2026/1098 MOV SE" in mismatch.summary
    traces = [event.data for event in runtime.bus.recent(SseEvent.TRACE, limit=500)]
    [line] = [event for event in traces if event["detail"].get("discrepancy_id") == mismatch.id]
    assert line["level"] == "warn"  # a CAUTION, not background information

    feeds = {feed.feed: feed for feed in state.feeds}
    recorded = {
        FeedId.SIGMET,
        FeedId.VONA,
        FeedId.VAAC_DARWIN,
        FeedId.TAF,
        FeedId.METAR,
        FeedId.WINDS,
    }
    assert {feed for feed, health in feeds.items() if health.status is FeedStatus.OK} == recorded
    for feed in set(FeedId) - recorded - {FeedId.HSD}:
        assert (feeds[feed].status, feeds[feed].last_error) == (
            FeedStatus.DISABLED,
            NOT_RECORDED_NOTE,
        )

    # Ibu is in the recording but not the case's volcano: the gate says why there is no
    # model call, and its cone comes from the official products only.
    ibu = [event for event in traces if event["volcano_id"] == "268030"]
    plume = [event for event in ibu if event["stage"] == "PLUME"]
    assert runtime.replay_case is not None
    assert "268030" not in runtime.replay_case.volcano_ids
    assert plume[0]["actor"] == "code"
    assert plume[0]["message"] == (
        "Ibu: not this replay's volcano; cone from official products only"
    )
    assert "268030" not in runtime.assess_due


async def test_adsb_pass_leaves_a_feed_the_case_never_recorded_alone(
    data_dir: Path, tmp_path: Path
) -> None:
    """A case reconstructed without aircraft shows ADS-B as not recorded, never as an error."""
    case = await record_case(data_dir, tmp_path / "record")
    no_aircraft = case.model_copy(
        update={"records": [r for r in case.records if r.feed is not FeedId.ADSB]}
    )
    (case_path(data_dir, CASE_ID) / MANIFEST_NAME).write_text(no_aircraft.model_dump_json())
    runtime = replay_runtime(no_aircraft, replay_settings(data_dir, tmp_path / "replay"))
    try:
        with use_clock(FixedClock(AT)):
            await tick_and_work(runtime, reason="manual")
            assert runtime.live.active
            await run_adsb_pass(runtime)
        adsb = runtime.live.health[FeedId.ADSB]
        assert adsb.status is FeedStatus.DISABLED
        assert adsb.last_attempt_at is None
        assert adsb.last_error == NOT_RECORDED_NOTE
    finally:
        await runtime.aclose()


def test_replay_info_names_the_case_volcanoes() -> None:
    """The Wall opens a replay on the case's own volcano (UI-REDESIGN R2.2)."""
    case = ReplayCase(
        case_id=CASE_ID,
        label=LABEL,
        recorded_from=AT,
        recorded_to=AT + timedelta(hours=1),
        region="java_bali",
        volcano_ids=["262000"],
        records=[],
    )
    info = replay_info(case, auto=False)
    assert info.volcano_ids == ["262000"]
    assert replay_info(case.model_copy(update={"volcano_ids": []}), auto=False).volcano_ids == []
