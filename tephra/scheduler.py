"""Tick orchestration and the local scheduler loop.

A tick polls the feeds that are due (``FeedHealth.last_attempt_at`` is the due-ness record;
it is checkpointed to the store), decides which volcanoes are active, runs the pipeline,
and publishes the Wall. Ticks never overlap: one that finds the runtime's lock held returns
``skipped=True`` at once. On Cloud Run, Cloud Scheduler calls ``POST /tasks/tick`` every
minute; with ``TEPHRA_LOCAL_SCHEDULER=1`` :func:`run_local_scheduler` ticks in process.
Between ticks, extra ADS-B passes keep aircraft at their 30 s cadence.
"""

import asyncio
import logging
import time
from collections.abc import Sequence
from contextlib import suppress
from typing import TYPE_CHECKING, Final

from tephra.feeds.registry import (
    CONTEXT_FEEDS,
    PRODUCT_FEEDS,
    FeedPoll,
    due_feeds,
    poll,
    uncovered_feeds,
)
from tephra.models import FeedHealth, FeedId, FeedStatus, RunMode, TickReport, TraceStage
from tephra.util import timeutil

if TYPE_CHECKING:
    from tephra.pipeline import Runtime

__all__ = ["run_adsb_pass", "run_local_scheduler", "run_tick"]

logger = logging.getLogger(__name__)

SCHEDULER_INTERVAL_S: Final = 60
"""Cloud Scheduler's period (one job, every minute)."""
ADSB_PASS_MARGIN_S: Final = 10
"""No extra ADS-B pass this close to the next tick."""
FEED_LABELS: Final[dict[FeedId, str]] = {
    FeedId.SIGMET: "VA SIGMET",
    FeedId.VONA: "MAGMA VONA",
    FeedId.VAAC_TOKYO: "Tokyo VAAC",
    FeedId.VAAC_DARWIN: "Darwin VAAC",
    FeedId.TAF: "TAF",
    FeedId.METAR: "METAR",
    FeedId.ADSB: "ADS-B",
    FeedId.WINDS: "Winds",
    FeedId.FRAMES: "Satellite frames",
    FeedId.HSD: "Himawari HSD",
}


async def run_tick(runtime: "Runtime", *, reason: str) -> TickReport:
    started = timeutil.now()
    if runtime.lock.locked():
        return TickReport(
            started_at=started, finished_at=started, mode=runtime.mode, reason=reason, skipped=True
        )
    async with runtime.lock:
        report = TickReport(
            started_at=started, finished_at=started, mode=runtime.mode, reason=reason
        )
        await runtime.maybe_switch_mode(report)
        await _poll_phase(runtime, PRODUCT_FEEDS, report)
        active = runtime.refresh_active(timeutil.now())
        await _poll_phase(runtime, CONTEXT_FEEDS, report)
        at = timeutil.now()
        await runtime.analyse(at, report)
        await runtime.run_exposures(at, report)
        runtime.count_quiet_tick()
        report.active_volcano_ids = sorted(active)
        report.finished_at = timeutil.now()
        runtime.last_tick = report
        await runtime.publish()
        await runtime.checkpoint()
    _schedule_adsb_passes(runtime, reason)
    logger.info(
        "tick %s: %d feeds, %d active, %d exposed, %d drafts, %d superseded",
        reason,
        len(report.feeds_polled),
        len(report.active_volcano_ids),
        report.exposed_flights,
        report.drafts_created,
        report.drafts_superseded,
    )
    return report


async def run_adsb_pass(runtime: "Runtime") -> None:
    """Refresh aircraft and exposures between ticks (only while something is active)."""
    if runtime.lock.locked() or not runtime.live.active:
        return
    async with runtime.lock:
        before = runtime.live.health.get(FeedId.ADSB)
        result = await poll(FeedId.ADSB, runtime)
        _trace_poll(runtime, result, before)
        if not result.ok:
            return
        at = timeutil.now()
        report = TickReport(started_at=at, finished_at=at, mode=runtime.mode, reason="adsb")
        await runtime.run_exposures(at, report)
        await runtime.publish_live()


async def run_local_scheduler(runtime: "Runtime", stop: asyncio.Event) -> None:
    reason = "startup"
    while not stop.is_set():
        try:
            await runtime.tick(reason=reason)
        except Exception:  # keep the loop alive; the next tick starts clean
            logger.exception("tick failed")
        reason = "local"
        with suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=runtime.settings.tick_interval_s)


async def _poll_phase(runtime: "Runtime", feeds: Sequence[FeedId], report: TickReport) -> None:
    at = timeutil.now()
    health = runtime.live.health
    due = [
        feed
        for feed in due_feeds(
            at,
            health,
            runtime.settings,
            active=bool(runtime.live.active),
            replay=runtime.mode is RunMode.REPLAY,
        )
        if feed in feeds
    ]
    due += [feed for feed in uncovered_feeds(runtime, at) if feed in feeds and feed not in due]
    if not due:
        return
    before = {feed: health.get(feed) for feed in due}
    results = await asyncio.gather(*(poll(feed, runtime) for feed in due))
    for result in results:
        report.feeds_polled.append(result.feed)
        if result.error is not None:
            report.feed_errors[result.feed.value] = result.error
        _trace_poll(runtime, result, before[result.feed])


def _trace_poll(runtime: "Runtime", result: FeedPoll, before: FeedHealth | None) -> None:
    """Trace what changed: new records, a new error, or a switch to the last good copy."""
    label = FEED_LABELS[result.feed]
    if result.error is not None:
        repeated = (
            before is not None
            and before.status in (FeedStatus.ERROR, FeedStatus.DISABLED)
            and before.last_error == result.error
        )
        if not repeated:
            runtime.trace(
                TraceStage.POLL,
                "code",
                f"{label}: {result.error}; last good data kept",
                level="warn",
                detail={"feed": result.feed.value},
            )
        return
    if result.stale:
        if before is None or before.status is not FeedStatus.STALE:
            runtime.trace(
                TraceStage.POLL,
                "code",
                f"{label}: live fetch failed, serving the last good copy (marked stale)",
                level="warn",
                detail={"feed": result.feed.value},
            )
        return
    if result.new_record_count and result.feed is not FeedId.ADSB:
        runtime.trace(
            TraceStage.POLL,
            "code",
            f"{label}: {result.new_record_count} new or changed record(s)",
            detail={"feed": result.feed.value, "records": result.record_count},
        )


def _schedule_adsb_passes(runtime: "Runtime", reason: str) -> None:
    if reason == "scheduler":
        interval = SCHEDULER_INTERVAL_S
    elif reason in ("local", "startup"):
        interval = runtime.settings.tick_interval_s
    else:
        return
    cadence = runtime.settings.cadence_adsb_s
    if cadence <= 0:
        return
    offsets = list(range(cadence, interval - ADSB_PASS_MARGIN_S + 1, cadence))
    if offsets:
        runtime.spawn(_adsb_passes(runtime, offsets))


async def _adsb_passes(runtime: "Runtime", offsets: Sequence[int]) -> None:
    start = time.monotonic()
    for offset in offsets:
        await asyncio.sleep(max(0.0, start + offset - time.monotonic()))
        try:
            await run_adsb_pass(runtime)
        except Exception:  # a background task's error would otherwise vanish
            logger.exception("extra ADS-B pass failed")
