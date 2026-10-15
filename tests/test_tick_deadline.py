"""A tick that runs past ``tick_deadline_s`` publishes what it has: the slow step is cut, the
report says so, the trace carries the line, and the tick still finishes (SPEC T27)."""

import asyncio
from pathlib import Path

import pytest
from test_pipeline import AT, FixtureSource, make_runtime, make_settings, trace_events

from tephra import scheduler
from tephra.models import TraceStage
from tephra.util.timeutil import FixedClock, use_clock


@pytest.fixture(autouse=True)
def clock():
    with use_clock(FixedClock(AT)):
        yield


async def test_a_slow_step_is_cut_at_the_deadline_and_the_tick_still_publishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = make_runtime(make_settings(tmp_path), FixtureSource())
    try:
        settled: list[str] = []

        async def slow_recovery(at, report) -> None:
            await asyncio.sleep(5)

        async def settle(at, report) -> None:
            settled.append("ran")

        monkeypatch.setattr(runtime, "run_recovery", slow_recovery)
        monkeypatch.setattr(runtime, "settle_drafts", settle)
        monkeypatch.setattr(scheduler, "_deadline_s", lambda runtime: 0.3)

        report = await scheduler.run_tick(runtime, reason="manual")
        assert report.skipped is False
        assert report.notes == [scheduler.CUT_SHORT_NOTE.format(seconds=0.3)]
        assert settled == [], "the step after the cut waits for the next tick"
        assert runtime.last_tick is report, "published"
        assert runtime.tick_running is False
        lines = [e for e in trace_events(runtime) if e.get("stage") == TraceStage.SYSTEM.value]
        assert any("tick cut short after 0.3 s" in e.get("message", "") for e in lines)
    finally:
        await runtime.aclose()


async def test_a_tick_inside_the_deadline_has_no_note(tmp_path: Path) -> None:
    runtime = make_runtime(make_settings(tmp_path), FixtureSource())
    try:
        report = await scheduler.run_tick(runtime, reason="manual")
        assert report.skipped is False
        assert all("cut short" not in n for n in report.notes)
    finally:
        await runtime.aclose()
