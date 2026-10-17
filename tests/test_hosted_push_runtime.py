"""A hosted airline's pushes in its runtime (D23, F3, S6): positions and plans only mark the
picture, and one exposure pass runs at most every EXPOSURE_GAP_S from the runtime's own task;
pilot reports past the hourly limit are refused with a reason; a push reads and writes nothing in
the store (counters are the registry's, in memory); refused records are counted per section."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from test_hosted_runtime import hosted_runtime
from test_pipeline import AT, FixtureSource, make_runtime, make_settings

from tephra import pipeline
from tephra.models import Connection, PushSummary, SseEvent
from tephra.pipeline import Runtime
from tephra.store.metered import StoreMeter
from tephra.util import timeutil
from tephra.util.timeutil import FixedClock, use_clock

PUSHED_HEX = "8a0999"


def connection() -> Connection:
    return Connection(
        id="CN-0123456789",
        name="RFB ops",
        created_at=AT,
        created_by="desk:Ana Ops#MB-1a2b3c4d5e",
        key_sha256="0" * 64,
        key_hint="abcd",
    )


def position(**changes: Any) -> dict[str, Any]:
    """A position in the Semeru area on the fixture's track, pushed by the airline."""
    return {
        "hex": PUSHED_HEX,
        "callsign": "RFB6711",
        "type_icao": "A320",
        "lat": -8.15,
        "lon": 113.70,
        "alt_baro_ft": 12000,
        "gs_kt": 420.0,
        "track_deg": 270.0,
        "observed_at": timeutil.to_iso(AT),
        **changes,
    }


def count_exposure_passes(runtime: Runtime) -> list[str]:
    passes: list[str] = []
    inner = runtime.run_exposures

    async def counted(at: Any, report: Any) -> None:
        passes.append(report.reason)
        await inner(at, report)

    runtime.run_exposures = counted  # type: ignore[method-assign]
    return passes


@pytest.fixture
def meter() -> StoreMeter:
    return StoreMeter(blob_puts_cap=4_000)


async def test_ten_quick_pushes_make_one_exposure_pass_then_one_more(
    tmp_path: Path, meter: StoreMeter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline, "EXPOSURE_GAP_S", 0.4)
    rfb = await hosted_runtime(tmp_path, meter)
    rfb.wall_clock = FixedClock(AT)
    try:
        await rfb.tick(reason="manual")
        assert rfb.live.active, "the fixture's Semeru area is active"
        passes = count_exposure_passes(rfb)
        with rfb.bound():
            for n in range(10):  # ten pushes over 0.2 s, half the gap
                await rfb.take_push(connection(), [position(lat=-8.15 + n * 0.001)])
                await asyncio.sleep(0.02)
        assert passes == ["push"], "one pass for the burst"
        assert rfb.exposure_dirty, "the rest of the burst waits for the gap"
        await asyncio.sleep(0.6)
        assert passes == ["push", "push"]
        assert not rfb.exposure_dirty
        assert any(flight.hex == PUSHED_HEX for flight in rfb.exposed.values())
    finally:
        await rfb.aclose()


async def test_a_hosted_push_reads_and_writes_nothing_in_the_store(
    tmp_path: Path, meter: StoreMeter
) -> None:
    rfb = await hosted_runtime(tmp_path, meter)
    rfb.wall_clock = FixedClock(AT)
    try:
        before = meter.day()
        with rfb.bound():
            result = await rfb.take_push(
                connection(), [position(), position(hex="zz"), position(observed_at="x")]
            )
        after = meter.day()
        summary = rfb.bus.last(SseEvent.PUSH)
    finally:
        await rfb.aclose()

    assert result.accepted == 1
    assert after.reads.get("RFB", 0) == before.reads.get("RFB", 0)
    assert after.writes.get("RFB", 0) == before.writes.get("RFB", 0)
    assert summary is not None
    assert summary.data["rejected_by_section"] == {"positions": 2}


async def test_pilot_reports_past_the_hourly_limit_are_refused_with_a_reason(
    tmp_path: Path, meter: StoreMeter, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert pipeline.PILOT_REPORTS_PER_HOUR == 60
    monkeypatch.setattr(pipeline, "PILOT_REPORTS_PER_HOUR", 3)
    rfb = await hosted_runtime(tmp_path, meter)
    rfb.wall_clock = FixedClock(AT)
    try:
        with rfb.bound():
            first = await rfb.take_push(connection(), reports=[{}, {}, {}])
            second = await rfb.take_push(connection(), reports=[{}])
    finally:
        await rfb.aclose()

    assert [p.section for p in first.rejected] == ["pilot_reports"] * 3
    assert not any("last hour" in p.reason for p in first.rejected)
    assert len(second.rejected) == 1
    assert "3 pilot reports in the last hour" in second.rejected[0].reason


async def test_the_demo_push_path_is_unchanged(tmp_path: Path) -> None:
    with use_clock(FixedClock(AT)):
        demo = make_runtime(make_settings(tmp_path), FixtureSource())
        try:
            await demo.tick(reason="manual")
            passes = count_exposure_passes(demo)
            await demo.take_push(connection(), [position(), position(hex="zz")])
            summary = demo.push_log[0]
            assert passes == ["push"], "the demo checks a push against the ash at once"
            assert not demo.exposure_dirty
        finally:
            await demo.aclose()
    assert isinstance(summary, PushSummary)
    assert "rejected_by_section" not in summary.model_dump(mode="json")
