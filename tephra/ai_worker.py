"""The AI worker: the desk's scheduled model work, run off the tick, most urgent first.

A tick (or an ADS-B pass between ticks) only wakes the worker. The worker reads the Duty
Officer's work list (code decides what is due, exactly as before), checks it against each model's
budget, and starts one job:

* an urgent Duty Officer run over every mandatory item (a flight inside or about to enter an
  area, and the plume read it waits on). Urgent work is never paced; only the budget caps it.
* else the most urgent of: a routine Duty Officer run over the routine items whose estimated
  calls fit the routine pacing now (at most :data:`MAX_ROUTINE_ITEMS`, so a routine run stays
  short), or a queued network recovery run.

Duty Officer runs go one at a time. A recovery run (many model turns and three solver runs) goes
on beside the worker instead, so urgent work never waits behind it; while it runs no routine
Duty Officer run starts, so routine work is not paced twice over.

Pacing decides when routine work may start. Once admitted, a job's calls are checked only
against the daily cap (``use_lane(..., admitted=True)``), so a run that needs more calls than
estimated finishes instead of failing part-way. Routine work that does not fit stays WAITING,
with the time of its next slot (the Wall and Desk say "waiting for AI budget, next slot HHMMZ").
It is not offered to the Duty Officer, so waiting costs no model call; it is not dropped; and it
is never handed to another model.

Work whose model answers are all on hand (``tephra.agents.answers``: the same model's answers to
the same material questions, the Duty Officer's for exactly that work too) costs no call, so it
does not wait for a slot, even while the assistant is paused. It runs ``on_hand_only``: each
answer is still checked again, and a step whose answer no longer passes asks no model; it
raises ``NotOnHand``, what was not done stays due and waits for budget as before (never AI
UNAVAILABLE for want of a slot), and the look ahead passes over those items for the policy's
re-offer time.

The worker runs only the scheduled work. Ask, voice, notices, messages, documents and a recovery
run started from the Desk call the models directly, at the same time as the worker's jobs; every
call, wherever it comes from, is counted against its model's budget before it is sent.

The queue is kept in the store (``ai_work``): after a restart the waiting work shows again at
once, and a recovery run that was queued or running runs again. The worker holds
``runtime.lock`` only to read the work list and to commit each result
(``Runtime.assess_volcano``, ``Runtime.plan_flight_now``); model calls run outside it, so ticks
and HTTP requests stay responsive however long the models take.
"""

import asyncio
import logging
from collections.abc import Iterable, Mapping
from contextlib import suppress
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final, Literal, NamedTuple

from pydantic import ValidationError

from tephra.agents.answers import NotOnHand, on_hand_only
from tephra.agents.budget import AiWork, WorkStatus, slot_words
from tephra.agents.llm import Tier
from tephra.agents.quota import Lane, use_lane
from tephra.duty import DeskUnreachable, dispatch_duty, drafts_by_flight, duty_worklist
from tephra.models import Advisory, DutyItem, DutyItemKind, RunMode, TickReport
from tephra.store.base import Collection
from tephra.util import timeutil
from tephra.util.hashing import sha256_json

if TYPE_CHECKING:
    from tephra.pipeline import Runtime

__all__ = ["MAX_ROUTINE_ITEMS", "RECOVERY_WORK_ID", "AiWorker"]

logger = logging.getLogger(__name__)

MAX_ROUTINE_ITEMS: Final = 3
"""Routine items per Duty Officer run: a routine run stays a few minutes long at most."""
IDLE_WAKE_S: Final = 60.0
"""The worker looks again at least this often (a slot opens, a deferral expires)."""
QUEUE_LIMIT: Final = 200
RECOVERY_WORK_ID: Final = "recover"
DUTY_TURNS: Final = 3
"""Estimated Duty Officer turns of a run besides one per delegation (the brief, a repair)."""
ITEM_CALLS: Final[Mapping[DutyItemKind, Mapping[Tier, int]]] = {
    DutyItemKind.ASSESS: {"main": 2, "lite": 3},  # Plume Reader (+ repair), Satellite Reader
    DutyItemKind.PLAN: {"lite": 8},  # planner turns (at most 10) and the drafter
    DutyItemKind.RECOVER: {"lite": 1},  # the run itself is a job of its own
    DutyItemKind.SRA: {"lite": 2},
}
"""Estimated calls per item, to admit routine work only when it fits. Every real call is still
counted when it is sent; a run that needs more than its estimate finishes within the daily cap,
and the extra calls come out of the routine share."""
RECOVERY_CALLS: Final[Mapping[Tier, int]] = {"lite": 10}


class _Wait(NamedTuple):
    """Why routine work waits: its next slot (None when it has none) and the words shown."""

    slot: datetime | None
    reason: str

    def behind(self, own: "_Wait | None") -> "_Wait":
        """An item that waits behind this one: never before this one's slot."""
        if self.slot is None or own is None or own.slot is None or own.slot <= self.slot:
            return self
        return own


class AiWorker:
    """The runtime's single AI worker (``Runtime.worker``)."""

    def __init__(self, runtime: "Runtime") -> None:
        self._runtime = runtime
        self._queue: dict[str, AiWork] = {}
        self._saved: dict[str, str] = {}
        """work id -> digest of the document last written to ``ai_work``"""
        self._wake = asyncio.Event()
        self._trigger: Literal["tick", "adsb"] = "tick"
        self.paced = True
        """False only for an offline backtest, whose own call cap is its budget"""
        self._pass = asyncio.Lock()
        """One pass at a time, whether the loop or ``drain`` runs it"""
        self._recovery: asyncio.Task[None] | None = None
        """The recovery run going on beside the worker, if any"""
        self._not_on_hand: dict[str, datetime] = {}
        """item id -> when (run clock) a run on answers on hand found one no longer passing"""

    # --- what the rest of the runtime calls -----------------------------------------------

    def queue(self) -> list[AiWork]:
        """The work queued, running or waiting for budget, most urgent first."""
        return sorted(self._queue.values(), key=lambda work: (work.urgency, work.since, work.id))

    def wake(self, trigger: Literal["tick", "adsb"] = "tick") -> None:
        """New work may be due (the tick's analysis or new aircraft): look now."""
        self._trigger = trigger
        self._wake.set()

    def enqueue_recovery(self, airports: Iterable[str]) -> None:
        """Queue a network recovery run (the Duty Officer's ``run_recovery``); it replaces a
        queued one for an earlier set of airports."""
        runtime = self._runtime
        existing = self._queue.get(RECOVERY_WORK_ID)
        if existing is not None and existing.status == "RUNNING":
            return
        names = sorted(airports)
        self._queue[RECOVERY_WORK_ID] = AiWork(
            id=RECOVERY_WORK_ID,
            kind="recover",
            label=f"Network recovery: {', '.join(names)} closed by the hazard",
            airports=names,
            model_id=runtime.llm.model_id("lite"),
            lane="routine",
            urgency=3,
            status="QUEUED",
            since=timeutil.SystemClock().now(),
            replay=runtime.mode is RunMode.REPLAY,
        )
        self._wake.set()

    def recovery_queued(self) -> bool:
        return RECOVERY_WORK_ID in self._queue

    def clear(self) -> None:
        """The picture was reset (a mode switch or a replay loop): queued work is for the old
        picture. A job running now finishes and finds the picture changed."""
        self._queue = {key: work for key, work in self._queue.items() if work.status == "RUNNING"}
        self._not_on_hand.clear()

    async def restore(self) -> None:
        """The queue as the last instance left it (LIVE only: a replay starts afresh). Work
        that was running is queued again; the first pass after the first tick checks it."""
        runtime = self._runtime
        try:
            docs = await runtime.store.list_docs(Collection.AI_WORK, limit=QUEUE_LIMIT)
        except Exception as exc:
            logger.warning("reading the AI work queue failed: %s", exc)
            return
        for doc in docs:
            try:
                work = AiWork.model_validate(doc)
            except ValidationError:
                logger.warning("ignoring an unreadable AI work document")
                continue
            self._saved[work.id] = sha256_json(doc)
            if work.replay:
                continue
            status: WorkStatus = "QUEUED" if work.status == "RUNNING" else work.status
            self._queue[work.id] = work.model_copy(update={"status": status})
        if self._queue:
            logger.info("AI work queue restored: %d item(s)", len(self._queue))

    async def run(self) -> None:
        """The worker's loop (one task per process, started with the app)."""
        while True:
            with suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=self._idle_s())
            self._wake.clear()
            try:
                while await self.work_once(self._report()):
                    pass
            except asyncio.CancelledError:
                raise
            except Exception:  # keep the worker alive; the next wake starts clean
                logger.exception("AI worker pass failed")

    async def drain(self) -> TickReport:
        """Run passes until nothing more is admitted and no recovery run is going on (tests,
        the backtest); what the jobs did."""
        report = self._report()
        while True:
            while await self.work_once(report):
                pass
            recovery = self._recovery
            if recovery is None:
                break
            await asyncio.gather(recovery, return_exceptions=True)
        report.finished_at = timeutil.now()
        return report

    # --- one pass -------------------------------------------------------------------------

    async def work_once(self, report: TickReport) -> bool:
        """Read the work list, update the queue, and run the most urgent job that fits; what
        it did goes on ``report``. True when a job ran."""
        async with self._pass:
            return await self._work_once(report)

    async def _work_once(self, report: TickReport) -> bool:
        runtime = self._runtime
        if runtime.retired or runtime.last_tick is None:
            return False  # a retired instance does no work; before the first tick there is none
        async with runtime.lock:
            epoch = runtime.epoch
            at = timeutil.now()
            try:
                drafts = await drafts_by_flight(runtime)
            except DeskUnreachable:
                return False  # the open drafts cannot be read: planning waits (MODULES.md 5.7)
            worklist = duty_worklist(runtime, at, drafts)
        rerun = timedelta(minutes=runtime.policy.duty.rerun_min.value)
        fresh = [
            item
            for item in worklist
            if (offered := runtime.duty_offered.get(item.id)) is None or at - offered >= rerun
        ]
        await runtime.quota.load_all(runtime.llm.model_id(tier) for tier in ("main", "lite"))
        urgent = [item for item in fresh if item.mandatory]
        routine, waiting, later = self._admit([item for item in fresh if not item.mandatory])
        on_hand = False
        if not routine and waiting:
            routine = await self._on_hand([item for item in fresh if item.id in waiting], at)
            on_hand = bool(routine)
            for item in routine:
                del waiting[item.id]
        self._sync(fresh, [*urgent, *routine, *later], waiting)
        recovery = self._recovery_ready()
        await self._persist()
        await runtime.publish_budget()
        if urgent:
            await self._duty(urgent, "urgent", drafts, at, epoch, len(waiting), report)
            return True
        if self._recovery is not None:
            return False  # routine work starts once the recovery run is done
        routine_urgency = min((item.urgency for item in routine), default=None)
        if recovery is not None and (routine_urgency is None or recovery.urgency < routine_urgency):
            await self._start_recovery(recovery)
            return True
        if routine:
            await self._duty(
                routine, "routine", drafts, at, epoch, len(waiting), report, on_hand=on_hand
            )
            return True
        return False

    def _admit(
        self, items: list[DutyItem]
    ) -> tuple[list[DutyItem], dict[str, _Wait], list[DutyItem]]:
        """Split routine items into those whose estimated calls fit the routine pacing now
        (most urgent first, at most :data:`MAX_ROUTINE_ITEMS`, a plan only with or after its
        volcano's plume read), those waiting (for budget, or for a plume read), and those that
        fit but wait for a later run.

        Strictly in urgency order: once an item waits for budget, every less urgent one waits
        behind it, so a small job never takes the calls a more urgent one is waiting for."""
        runtime = self._runtime
        unpaced = not runtime.llm.metered or not self.paced
        admitted: list[DutyItem] = []
        waiting: dict[str, _Wait] = {}
        later: list[DutyItem] = []
        needed: dict[Tier, int] = {"lite": DUTY_TURNS}
        blocked: _Wait | None = None
        for item in sorted(items, key=lambda item: (item.urgency, item.label)):
            if (
                item.kind is DutyItemKind.PLAN
                and item.volcano_id in runtime.assess_due
                and not any(
                    done.kind is DutyItemKind.ASSESS and done.volcano_id == item.volcano_id
                    for done in admitted
                )
            ):
                waiting[item.id] = _Wait(None, "waiting for its plume read")
                continue
            trial = dict(needed)
            for tier, calls in ITEM_CALLS[item.kind].items():
                trial[tier] = trial.get(tier, 0) + calls
            trial["lite"] += 1  # the Duty Officer's turn that delegates it
            wait = None if unpaced else self._wait(trial)
            if blocked is not None:
                waiting[item.id] = blocked.behind(wait)
            elif wait is not None:
                waiting[item.id] = blocked = wait
            elif len(admitted) < MAX_ROUTINE_ITEMS:
                admitted.append(item)
                needed = trial
            else:
                later.append(item)
        return admitted, waiting, later

    async def _on_hand(self, items: list[DutyItem], at: datetime) -> list[DutyItem]:
        """Routine items waiting for budget whose model answers are all on hand, the Duty
        Officer's for this very work list too: run now, they cost no model call, even while the
        assistant is paused. At most :data:`MAX_ROUTINE_ITEMS`, most urgent first, a plan only
        with or after its volcano's plume read; not an item a run on answers on hand found
        short within the policy's re-offer time. Nothing when the Duty Officer would have to
        be asked."""
        runtime = self._runtime
        rerun = timedelta(minutes=runtime.policy.duty.rerun_min.value)
        self._not_on_hand = {
            item_id: when for item_id, when in self._not_on_hand.items() if abs(at - when) < rerun
        }
        chosen: list[DutyItem] = []
        for item in sorted(items, key=lambda item: (item.urgency, item.label)):
            if len(chosen) >= MAX_ROUTINE_ITEMS:
                break
            if item.id in self._not_on_hand:
                continue
            if (
                item.kind is DutyItemKind.PLAN
                and item.volcano_id in runtime.assess_due
                and not any(
                    done.kind is DutyItemKind.ASSESS and done.volcano_id == item.volcano_id
                    for done in chosen
                )
            ):
                continue
            if await runtime.answered(item):
                chosen.append(item)
        if chosen and await runtime.coordinator_answered(chosen):
            return chosen
        return []

    def _wait(self, calls: Mapping[Tier, int]) -> _Wait | None:
        """None when ``calls`` routine calls fit every model now, else why not: the latest of
        the models' next slots, or the reason when a model has no slot (its count cannot be
        read)."""
        runtime = self._runtime
        slots: list[datetime] = []
        for tier, count in calls.items():
            admission = runtime.quota.admission(runtime.llm.model_id(tier), "routine", count)
            if admission.ok:
                continue
            if admission.next_slot is None:
                return _Wait(None, f"waiting: {admission.reason}")
            slots.append(admission.next_slot)
        if not slots:
            return None
        slot = max(slots)
        return _Wait(slot, slot_words(slot))

    def _recovery_ready(self) -> AiWork | None:
        work = self._queue.get(RECOVERY_WORK_ID)
        if work is None or work.status == "RUNNING":
            return None
        unpaced = not self._runtime.llm.metered or not self.paced
        wait = None if unpaced else self._wait(RECOVERY_CALLS)
        if wait is None:
            ready = work.model_copy(
                update={"status": "QUEUED", "next_slot_at": None, "reason": None}
            )
            self._queue[work.id] = ready
            return ready
        self._queue[work.id] = work.model_copy(
            update={"status": "WAITING", "next_slot_at": wait.slot, "reason": wait.reason}
        )
        return None

    def _sync(
        self,
        fresh: list[DutyItem],
        queued: list[DutyItem],
        waiting: Mapping[str, _Wait],
    ) -> None:
        """The queue's Duty Officer items: those about to run and those waiting for budget.
        Items offered recently (deferred, or done) are on the Duty Officer's panel instead."""
        runtime = self._runtime
        now = timeutil.SystemClock().now()
        model = runtime.llm.model_id("lite")
        replay = runtime.mode is RunMode.REPLAY
        shown = {item.id for item in queued} | set(waiting)
        kept: dict[str, AiWork] = {
            key: work for key, work in self._queue.items() if work.kind == "recover"
        }
        for item in fresh:
            if item.id not in shown:
                continue
            held = self._queue.get(item.id)
            wait = waiting.get(item.id)
            is_waiting = wait is not None
            slot = wait.slot if wait is not None else None
            reason = wait.reason if wait is not None else None
            kept[item.id] = AiWork(
                id=item.id,
                kind="duty_item",
                label=item.label,
                item=item,
                model_id=model,
                lane="urgent" if item.mandatory else "routine",
                urgency=item.urgency,
                status="WAITING" if is_waiting else "QUEUED",
                since=held.since if held is not None else now,
                next_slot_at=slot,
                reason=reason,
                replay=replay,
            )
        self._queue = kept

    def _idle_s(self) -> float:
        """Until the earliest next slot of waiting work, but at least once a minute."""
        now = timeutil.SystemClock().now()
        slots = [w.next_slot_at for w in self._queue.values() if w.next_slot_at is not None]
        if not slots:
            return IDLE_WAKE_S
        return min(IDLE_WAKE_S, max(1.0, (min(slots) - now).total_seconds()))

    # --- jobs -----------------------------------------------------------------------------

    async def _duty(
        self,
        items: list[DutyItem],
        lane: Lane,
        drafts: dict[str, list[Advisory]],
        at: datetime,
        epoch: int,
        waiting: int,
        report: TickReport,
        *,
        on_hand: bool = False,
    ) -> None:
        """``on_hand`` (a routine run started because its answers are on hand): no model is
        asked; when a step would have to ask one, what was not done waits for budget again."""
        runtime = self._runtime
        self._mark(items, "RUNNING")
        await self._persist()
        await runtime.publish_budget()
        offered = True
        try:
            admitted = lane == "routine" and not on_hand  # on hand: no call is admitted
            with use_lane(lane, admitted=admitted), on_hand_only(on_hand):
                await dispatch_duty(
                    runtime,
                    items,
                    drafts,
                    at,
                    report,
                    trigger=self._trigger,
                    epoch=epoch,
                    waiting=waiting,
                )
        except DeskUnreachable:
            runtime.desk_unreachable(report)
        except NotOnHand as exc:
            logger.info("routine work waits for budget again: %s", exc)
            offered = False
            self._not_on_hand.update((item.id, at) for item in items)
        finally:
            for item in items:
                self._queue.pop(item.id, None)
                if offered and runtime.epoch == epoch:  # offered, whatever came of it
                    runtime.duty_offered[item.id] = max(at, runtime.duty_offered.get(item.id, at))
            await self._persist()
            await runtime.publish_budget()

    async def _start_recovery(self, work: AiWork) -> None:
        """Start the recovery run beside the worker; the worker goes on with urgent work."""
        self._queue[work.id] = work.model_copy(update={"status": "RUNNING"})
        await self._persist()
        await self._runtime.publish_budget()
        self._recovery = self._runtime.spawn(self._recover(work))

    async def _recover(self, work: AiWork) -> None:
        runtime = self._runtime
        try:
            with use_lane(work.lane, admitted=True):
                await runtime.recover_queued(work.airports)
        except Exception:  # the job's own errors are traced in Runtime._recover
            logger.exception("recovery run failed")
        finally:
            self._recovery = None
            held = self._queue.get(work.id)
            if held is not None and held.status == "RUNNING":
                del self._queue[work.id]
            with suppress(Exception):
                await self._persist()
                await runtime.publish_budget()
            self._wake.set()

    def _report(self) -> TickReport:
        at = timeutil.now()
        return TickReport(started_at=at, finished_at=at, mode=self._runtime.mode, reason="ai")

    def _mark(self, items: Iterable[DutyItem], status: WorkStatus) -> None:
        for item in items:
            held = self._queue.get(item.id)
            if held is not None:
                self._queue[item.id] = held.model_copy(update={"status": status})

    async def _persist(self) -> None:
        """Write what changed in the queue to ``ai_work``; a retired instance writes nothing.
        A store error leaves the queue in memory and is retried at the next pass."""
        runtime = self._runtime
        if runtime.retired:
            return
        docs = {key: work.model_dump(mode="json") for key, work in self._queue.items()}
        try:
            for key in [key for key in self._saved if key not in docs]:
                await runtime.store.delete(Collection.AI_WORK, key)
                del self._saved[key]
            for key, doc in docs.items():
                digest = sha256_json(doc)
                if self._saved.get(key) != digest:
                    await runtime.store.put(Collection.AI_WORK, key, doc)
                    self._saved[key] = digest
        except Exception as exc:
            logger.warning("writing the AI work queue failed: %s", exc)
