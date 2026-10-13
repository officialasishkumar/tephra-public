"""Tick orchestration and the local scheduler loop.

A tick polls the feeds that are due (``FeedHealth.last_attempt_at`` is the due-ness record;
it is checkpointed to the store), decides which volcanoes are active, runs the pipeline,
and publishes the Wall. Ticks never overlap: one that finds another tick running returns
``skipped=True`` at once. On Cloud Run, Cloud Scheduler calls ``POST /tasks/tick`` every
minute; with ``TEPHRA_LOCAL_SCHEDULER=1`` :func:`run_local_scheduler` ticks in process.
Between ticks, extra ADS-B passes keep aircraft at their 30 s cadence, timed from the start
of the tick; a tick that arrives while a pass holds the runtime's lock waits for it.

A step after the analysis that raises (exposure, crew reports, recovery, draft retirement)
becomes a note and a trace line; the Wall is still published and checkpointed. A tick makes no
model call: it ends by waking the AI worker (``tephra.ai_worker``), which runs the Duty Officer
and the specialists off the tick, so a tick takes seconds however long the models take.

Every tick names its instance in ``runtime/writer``. During a rollout the old revision's
instance stays up while its streams are open; :func:`run_writer_watchdog` and every ADS-B
pass read that doc, and an instance that another one has out-ticked retires (see
``Runtime.check_writer``).
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Sequence
from contextlib import suppress
from typing import TYPE_CHECKING, Final

from tephra.feeds.registry import (
    CONTEXT_FEEDS,
    PRODUCT_FEEDS,
    FeedPoll,
    disabled_reason,
    due_feeds,
    poll,
    uncovered_feeds,
)
from tephra.models import FeedHealth, FeedId, FeedStatus, RunMode, TickReport, TraceStage
from tephra.util import timeutil

if TYPE_CHECKING:
    from tephra.pipeline import Runtime

__all__ = ["run_adsb_pass", "run_local_scheduler", "run_tick", "run_writer_watchdog"]

logger = logging.getLogger(__name__)

SCHEDULER_INTERVAL_S: Final = 60
"""Cloud Scheduler's period (one job, every minute)."""
ADSB_PASS_MARGIN_S: Final = 10
"""No extra ADS-B pass this close to the next tick."""
WRITER_WATCH_S: Final = 60
"""How often an instance checks whether another one has taken the ticks."""
QUIET_TICKS: Final = 3
"""Ticks missed (Cloud Scheduler mode) before open streams are ended once."""
BUSY_NOTE: Final = "busy: another tick is still running"
STOPPED_NOTE: Final = "stopped: a mode switch at the Desk ended this tick"
FEED_LABELS: Final[dict[FeedId, str]] = {
    FeedId.SIGMET: "VA SIGMET",
    FeedId.VONA: "MAGMA VONA",
    FeedId.JMA_VOLCANO: "JMA volcano reports",
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
    requested = time.monotonic()
    if runtime.tick_running:
        at = timeutil.now()
        return TickReport(
            started_at=at,
            finished_at=at,
            mode=runtime.mode,
            reason=reason,
            skipped=True,
            notes=[BUSY_NOTE],
        )
    runtime.tick_running = True
    try:
        # An extra ADS-B pass or a mode switch holds the lock for seconds; skipping here
        # would lose the whole tick (Cloud Scheduler does not retry a skipped one).
        async with runtime.lock:
            runtime.tick_task = asyncio.ensure_future(_tick_steps(runtime, reason))
            try:
                report = await runtime.tick_task
            except asyncio.CancelledError:
                # stopped by a person's mode switch (Runtime.switch_mode); a cancel of this
                # tick itself still propagates
                if not runtime.tick_task.cancelled() or asyncio.current_task().cancelling():
                    raise
                at = timeutil.now()
                report = TickReport(
                    started_at=at,
                    finished_at=at,
                    mode=runtime.mode,
                    reason=reason,
                    skipped=True,
                    notes=[STOPPED_NOTE],
                )
            finally:
                runtime.tick_task = None
    finally:
        runtime.tick_running = False
        _schedule_adsb_passes(runtime, reason, requested)
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


async def _tick_steps(runtime: "Runtime", reason: str) -> TickReport:
    mode = runtime.mode
    started = timeutil.now()
    report = TickReport(started_at=started, finished_at=started, mode=mode, reason=reason)
    if reason != "startup":  # a revision's startup tick may run before traffic reaches it
        await runtime.claim_writer()
    await runtime.maybe_switch_mode(report)
    if runtime.mode is not mode:  # the rest of the tick runs on the other mode's clock
        report.started_at = timeutil.now()
    runtime.follow_replay_clock(report.started_at, report)
    await _poll_phase(runtime, PRODUCT_FEEDS, report)
    active = runtime.refresh_active(timeutil.now())
    await _poll_phase(runtime, CONTEXT_FEEDS, report)
    at = timeutil.now()
    await runtime.analyse(at, report)
    await _step(runtime, report, "exposure", runtime.update_exposures(at, report))
    await _step(runtime, report, "crew reports", runtime.update_crew(at, report))
    await _step(runtime, report, "network recovery", runtime.run_recovery(at, report))
    await _step(runtime, report, "draft retirement", runtime.settle_drafts(at, report))
    runtime.count_quiet_tick()
    report.active_volcano_ids = sorted(active)
    report.finished_at = timeutil.now()
    runtime.last_tick = report
    runtime.last_tick_wall_at = timeutil.SystemClock().now()
    await runtime.publish()
    await runtime.checkpoint()
    # The model work this tick made due runs in the AI worker, not here (ai_worker.py).
    runtime.worker.wake("tick")
    return report


async def _step(runtime: "Runtime", report: TickReport, name: str, step: Awaitable[None]) -> None:
    """Run one tick step; an error is noted and traced, and the tick goes on to publish."""
    try:
        await step
    except Exception as exc:
        logger.exception("tick step %s failed", name)
        failure = f"{name} failed this tick ({type(exc).__name__})"
        report.notes.append(failure)
        runtime.trace(TraceStage.SYSTEM, "system", failure, level="error")


async def run_adsb_pass(runtime: "Runtime") -> None:
    """Refresh aircraft and exposures between ticks (only while something is active)."""
    if await runtime.check_writer():  # retired: the serving instance polls
        return
    if runtime.tick_running or runtime.lock.locked() or not runtime.live.active:
        return
    replay = runtime.mode is RunMode.REPLAY
    off = disabled_reason(
        FeedId.ADSB, runtime.settings, replay=replay, recorded=runtime.recorded_feeds
    )
    if off is not None:  # e.g. a replay case reconstructed without aircraft
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
    """Tick every ``tick_interval_s`` counted from the start of each tick, as Cloud Scheduler
    does; a tick that overruns the interval is followed at once by the next."""
    reason = "startup"
    while not stop.is_set():
        started = time.monotonic()
        try:
            await runtime.tick(reason=reason)
        except Exception:  # keep the loop alive; the next tick starts clean
            logger.exception("tick failed")
        reason = "local"
        wait_s = started + runtime.settings.tick_interval_s - time.monotonic()
        if wait_s > 0:
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=wait_s)


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
            recorded=runtime.recorded_feeds,
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
            and before.status in (FeedStatus.ERROR, FeedStatus.DISABLED, FeedStatus.STALE)
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


def _schedule_adsb_passes(runtime: "Runtime", reason: str, started: float) -> None:
    if reason == "scheduler":
        interval = SCHEDULER_INTERVAL_S
    elif reason in ("local", "startup"):
        interval = runtime.settings.tick_interval_s
    else:
        return
    previous = runtime.adsb_passes
    if previous is not None:
        previous.cancel()
    runtime.adsb_passes = None
    cadence = runtime.settings.cadence_adsb_s
    if cadence <= 0:
        return
    elapsed = time.monotonic() - started
    offsets = [
        offset
        for offset in range(cadence, interval - ADSB_PASS_MARGIN_S + 1, cadence)
        if offset > elapsed
    ]
    if offsets:
        runtime.adsb_passes = runtime.spawn(_adsb_passes(runtime, started, offsets))


async def _adsb_passes(runtime: "Runtime", started: float, offsets: Sequence[int]) -> None:
    """Passes at ``started + offset`` seconds: offsets count from the start of the tick, so
    the last one keeps its margin before the next tick however long this tick took."""
    for offset in offsets:
        await asyncio.sleep(max(0.0, started + offset - time.monotonic()))
        try:
            await run_adsb_pass(runtime)
        except Exception:  # a background task's error would otherwise vanish
            logger.exception("extra ADS-B pass failed")


async def run_writer_watchdog(runtime: "Runtime") -> None:
    """Every :data:`WRITER_WATCH_S`: retire this instance if another one took the ticks.

    With Cloud Scheduler driving ticks, :data:`QUIET_TICKS` intervals with no tick also end
    the open streams, once per quiet spell (not again until a tick has come), so a tab left
    on an instance that no longer gets ticks reconnects.
    """
    started = time.monotonic()
    ended_after: float | None = None
    while True:
        await asyncio.sleep(WRITER_WATCH_S)
        try:
            await runtime.check_writer()
        except Exception:  # the next check runs in a minute; a store error must be seen
            logger.exception("writer check failed")
        if runtime.settings.local_scheduler:
            continue
        last = runtime.last_tick_clock if runtime.last_tick_clock is not None else started
        quiet = time.monotonic() - last > QUIET_TICKS * runtime.settings.tick_interval_s
        if quiet and ended_after != last:
            ended_after = last
            logger.warning(
                "no tick for %d intervals; ending the open event streams once", QUIET_TICKS
            )
            runtime.end_streams()
