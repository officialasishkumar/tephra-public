"""What the runtime tells the pages about itself (``SystemState``), the replay minute, and the
hidden features whose scheduled model work stops (TEPHRA_FEATURES)."""

import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_pipeline import AT, SEMERU, FixtureSource, make_runtime, make_settings, tick_and_work

from tephra import pipeline as pipeline_module
from tephra.config import ALL_FEATURES, Settings
from tephra.feeds.jma_volcano import JMA_EQVOL_URL
from tephra.feeds.registry import FEATURE_OFF_NOTE, disabled_reason, initial_health
from tephra.models import FeedId, FeedStatus, ReplayCase, RunMode
from tephra.replay.cases import start_replay_clock
from tephra.util import timeutil
from tephra.util.timeutil import FixedClock, ReplayClock, use_clock

CASE = ReplayCase(
    case_id="quantum-fixture",
    label="A window for the clock",
    recorded_from=datetime(2026, 9, 5, 10, 0, tzinfo=UTC),
    recorded_to=datetime(2026, 9, 5, 19, 0, tzinfo=UTC),
    region="java_bali",
    records=[],
)


@pytest.fixture(autouse=True)
def restore_clock() -> Iterator[None]:
    """A replay clock is process-wide; put back whatever was there before."""
    with use_clock(timeutil.get_clock()):
        yield


@pytest.fixture
def clock() -> Iterator[FixedClock]:
    fixed = FixedClock(AT)
    with use_clock(fixed):
        yield fixed


# --- SystemState ------------------------------------------------------------------------


async def test_state_carries_features_cloud_and_visitor_access(
    tmp_path: Path, clock: FixedClock
) -> None:
    runtime = make_runtime(make_settings(tmp_path, features="connect,btd"), FixtureSource())
    try:
        state = await runtime.system_state()
    finally:
        await runtime.aclose()

    assert state.features == ["btd", "connect"], "sorted, so the pages compare lists"
    assert state.visitor_access is False, "LIVE: no visitor"
    shown = state.model_dump(mode="json")
    assert {"features", "cloud", "audit", "visitor_access"} <= set(shown)
    assert shown["features"] == ["btd", "connect"]

    everything = make_runtime(make_settings(tmp_path), FixtureSource())
    try:
        assert (await everything.system_state()).features == sorted(ALL_FEATURES)
    finally:
        await everything.aclose()


async def test_visitor_access_is_true_only_in_replay_with_the_setting_on(
    tmp_path: Path, clock: FixedClock
) -> None:
    async def visitor_access(mode: RunMode, setting: str) -> bool:
        settings = make_settings(tmp_path, visitor_access=setting)
        runtime = make_runtime(settings, FixtureSource(), mode=mode)
        try:
            return (await runtime.system_state()).visitor_access
        finally:
            await runtime.aclose()

    assert await visitor_access(RunMode.REPLAY, "replay") is True
    assert await visitor_access(RunMode.REPLAY, "off") is False
    assert await visitor_access(RunMode.LIVE, "replay") is False, "LIVE never admits a visitor"
    assert await visitor_access(RunMode.LIVE, "off") is False


# --- the replay minute ------------------------------------------------------------------


def test_the_replay_clock_takes_its_quantum_from_the_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(time, "monotonic", lambda: 1000.0)
    monkeypatch.setattr(time, "time", lambda: 1_700_000_020.0)

    exact = start_replay_clock(CASE, speed=1.0)
    assert exact.quantum_s == 0, "today's behaviour: the exact second"

    quantised = start_replay_clock(CASE, speed=1.0, quantum_s=60)
    assert quantised.quantum_s == 60
    assert timeutil.get_clock() is quantised

    settings = Settings(_env_file=None, replay_quantum_s=60)
    assert pipeline_module._start_clock(settings, CASE) is None
    wired = timeutil.get_clock()
    assert isinstance(wired, ReplayClock)
    assert wired.quantum_s == 60

    windowed = Settings(
        _env_file=None,
        replay_quantum_s=60,
        replay_case=CASE.case_id,
        replay_start=CASE.recorded_from + timedelta(hours=1),
        replay_end=CASE.recorded_from + timedelta(hours=2),
    )
    assert pipeline_module._start_clock(windowed, CASE) == (
        windowed.replay_start,
        windowed.replay_end,
    )
    looped = timeutil.get_clock()
    assert isinstance(looped, ReplayClock)
    assert looped.quantum_s == 60
    assert looped.start == windowed.replay_start


async def test_the_state_clock_keeps_its_seconds_under_a_replay_quantum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monotonic, wall = 1000.0, 1_699_999_980.0  # a wall minute boundary
    monkeypatch.setattr(time, "monotonic", lambda: monotonic)
    monkeypatch.setattr(time, "time", lambda: wall)
    start_replay_clock(CASE, speed=1.0, quantum_s=60)
    monotonic += 20.0  # twenty seconds into the minute
    monkeypatch.setattr(time, "monotonic", lambda: monotonic)
    assert timeutil.now() == CASE.recorded_from, "ticks see the floored minute"
    assert timeutil.now_exact() == CASE.recorded_from + timedelta(seconds=20)

    runtime = make_runtime(make_settings(tmp_path), FixtureSource(), mode=RunMode.REPLAY)
    try:
        state = await runtime.system_state()
    finally:
        await runtime.aclose()
    assert state.now == CASE.recorded_from + timedelta(seconds=20), "the Wall clock keeps seconds"


# --- hidden features stop their scheduled model work ----------------------------------------


async def test_a_hidden_satellite_feature_queues_no_satellite_read(
    tmp_path: Path, clock: FixedClock
) -> None:
    hidden = make_runtime(make_settings(tmp_path / "hidden", features="hero"), FixtureSource())
    try:
        report = await tick_and_work(hidden, reason="manual")
        assert report.assessments_run > 0, "the Plume reader still runs"
        assert report.satellite_reads == 0
        assert hidden.satellite == {}
        assert SEMERU in hidden.situations
        assert hidden.situations[SEMERU].supporting == [], "no reading, so no evidence"
    finally:
        await hidden.aclose()

    shown = make_runtime(make_settings(tmp_path / "shown"), FixtureSource())
    try:
        report = await tick_and_work(shown, reason="manual")
        assert report.satellite_reads > 0, "with the feature on, the read happens"
        assert SEMERU in shown.satellite
    finally:
        await shown.aclose()


def test_a_hidden_notices_feature_never_polls_the_jma_feed() -> None:
    hidden = Settings(_env_file=None, features="hero")
    assert disabled_reason(FeedId.JMA_VOLCANO, hidden, replay=False) == FEATURE_OFF_NOTE
    assert disabled_reason(FeedId.JMA_VOLCANO, hidden, replay=True) == FEATURE_OFF_NOTE
    assert disabled_reason(FeedId.SIGMET, hidden, replay=False) is None, "only the JMA feed"
    health = initial_health(hidden, replay=False)
    assert health[FeedId.JMA_VOLCANO].status is FeedStatus.DISABLED
    assert health[FeedId.JMA_VOLCANO].last_error == FEATURE_OFF_NOTE

    shown = Settings(_env_file=None, features="notices")
    assert disabled_reason(FeedId.JMA_VOLCANO, shown, replay=False) is None
    assert initial_health(shown, replay=False)[FeedId.JMA_VOLCANO].status is FeedStatus.NEVER


async def test_a_tick_with_notices_hidden_asks_jma_for_nothing(
    tmp_path: Path, clock: FixedClock
) -> None:
    source = FixtureSource()
    runtime = make_runtime(make_settings(tmp_path, features="satellite"), source)
    try:
        report = await tick_and_work(runtime, reason="manual")
    finally:
        await runtime.aclose()
    assert FeedId.JMA_VOLCANO not in report.feeds_polled
    assert not any(url.startswith(JMA_EQVOL_URL) for url in source.requested)
    assert FeedId.SIGMET in report.feeds_polled, "the rest of the picture is unchanged"
