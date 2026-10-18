"""Flights the AI could not plan or draft for.

There is no substitute plan or template message. Each failure is stored once per flight,
cone and stage, audited, and shown on the Desk until a dispatcher marks it handled by hand,
or until code closes it because it no longer stands (``close_failure``): a newer failure or a
new draft for the same flight, the flight leaving the area, or the end of the replay run it was
recorded in. Code's closing is audited as ``AI_FAILURE_CLOSED`` under the system actor and
fills ``closed_at``, never ``handled_by``: it is never a dispatcher's decision.

A REPLAY plays its recording again from the start on every run (a process start, a switch to
REPLAY, a loop), so failures carry the wall-clock time they were recorded: a run lists only its
own, and the same flight, cone and stage failing again in a later run is a new failure.

The cone a flight is exposed to gets a new id whenever the area is recomputed, so a flight the
AI cannot serve fails again every minute or so with the same reason. Every one of those is
stored and shown on the Desk, but the audit trail records the flight's failure once per stage,
reason and quota day (``AI_FAILED``) and its close once (``AI_FAILURE_CLOSED``): a repeat that
only carries a newer cone, and the close of such a repeat, add no audit entry. A failure this
process did not record (an earlier instance's) is always audited when it closes.
"""

import weakref
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Final

from tephra.agents.quota import quota_day
from tephra.desk import audit
from tephra.desk.approvals import SYSTEM_ACTOR
from tephra.models import AiFailure, AuditAction, SseEvent
from tephra.store.base import Collection, Store
from tephra.util import timeutil
from tephra.util.events import EventBus

__all__ = [
    "DRAFT_WAITING",
    "LIST_WINDOW",
    "NEWER_FAILURE",
    "REPLAY_RUN_ENDED",
    "FailureNotFound",
    "close_failure",
    "list_failures",
    "mark_handled",
    "of_run",
    "record_failure",
]

MAX_NOTE_CHARS: Final = 500
LIST_WINDOW: Final = 200
"""Newest records read (by wall-clock recording time) when failures are listed."""
NEWER_FAILURE: Final = "A NEWER AI FAILURE FOR THIS FLIGHT IS OPEN"
DRAFT_WAITING: Final = "AN ADVISORY DRAFT FOR THIS FLIGHT NOW WAITS FOR A DISPATCHER"
REPLAY_RUN_ENDED: Final = "THE REPLAY RUN IT WAS RECORDED IN HAS ENDED"


class FailureNotFound(Exception): ...


@dataclass
class _Audited:
    """What one store's failures have put in the audit trail, in this process."""

    day: date | None = None
    keys: set[tuple[str, str, str]] = field(default_factory=set)
    """(flight id, stage, reason) recorded as ``AI_FAILED`` on ``day``"""
    unaudited: set[str] = field(default_factory=set)
    """Ids of open failures stored without an ``AI_FAILED`` entry (repeats)"""

    def audited_today(self, failure: AiFailure) -> bool:
        """True when its flight's failure with that stage and reason is already in the audit
        trail for this quota day (the wall clock's, as the model budget counts)."""
        today = quota_day(timeutil.SystemClock().now())
        if self.day != today:
            self.day, self.keys = today, set()
        return _key(failure) in self.keys

    def audited(self, failure: AiFailure) -> None:
        self.keys.add(_key(failure))
        self.unaudited.discard(failure.id)


def _key(failure: AiFailure) -> tuple[str, str, str]:
    return failure.flight_id, failure.stage, failure.reason


_audited: "weakref.WeakKeyDictionary[Store, _Audited]" = weakref.WeakKeyDictionary()


def _audit_book(store: Store) -> _Audited:
    book = _audited.get(store)
    if book is None:
        book = _audited[store] = _Audited()
    return book


def of_run(failure: AiFailure, run_since: datetime | None) -> bool:
    """Recorded in the replay run that started at ``run_since`` (wall clock); every failure
    belongs to the run when ``run_since`` is None (live)."""
    if run_since is None:
        return True
    # Stored times keep milliseconds (to_iso), so the run's start is compared at that precision.
    since = run_since.replace(microsecond=run_since.microsecond // 1000 * 1000)
    return failure.recorded_wall_at is not None and failure.recorded_wall_at >= since


async def record_failure(
    store: Store, bus: EventBus, failure: AiFailure, *, run_since: datetime | None = None
) -> AiFailure | None:
    """Store a new failure. None when the same flight, cone and stage already failed and that
    record still stands (open or handled, in this run); one closed by code or recorded in an
    earlier replay run is replaced (an open one of an earlier run is closed first)."""
    doc = await store.get(Collection.AI_FAILURES, failure.id)
    if doc is not None:
        stored = AiFailure.model_validate(doc)
        if stored.closed_at is None and of_run(stored, run_since):
            return None
        if stored.open:
            await close_failure(store, bus, stored.id, reason=REPLAY_RUN_ENDED)
    failure = failure.model_copy(
        update={
            "recorded_wall_at": timeutil.SystemClock().now(),
            "handled_by": None,
            "handled_at": None,
            "handled_note": None,
            "closed_at": None,
            "closed_reason": None,
        }
    )
    await audit.require_writer(store)
    await store.put(Collection.AI_FAILURES, failure.id, failure.model_dump(mode="json"))
    book = _audit_book(store)
    if book.audited_today(failure):
        book.unaudited.add(failure.id)
        bus.publish(SseEvent.AI_FAILURE, failure)
        return failure
    await audit.record(
        store,
        actor=SYSTEM_ACTOR,
        action=AuditAction.AI_FAILED,
        after={
            "failure_id": failure.id,
            "stage": failure.stage,
            "flight_id": failure.flight_id,
            "proxy_flight": failure.proxy_flight,
            "cone_id": failure.cone_id,
        },
        model_id=failure.model_id,
        note=failure.reason,
    )
    book.audited(failure)
    bus.publish(SseEvent.AI_FAILURE, failure)
    return failure


async def close_failure(
    store: Store, bus: EventBus, failure_id: str, *, reason: str
) -> AiFailure | None:
    """Code closes a failure that no longer stands; None when it is gone or no longer open (a
    dispatcher handled it, or code closed it already)."""
    doc = await store.get(Collection.AI_FAILURES, failure_id)
    if doc is None or not AiFailure.model_validate(doc).open:
        return None
    await audit.require_writer(store)
    closing = False

    def change(stored: dict[str, Any] | None) -> dict[str, Any]:
        # Runs again when a Firestore transaction retries: only its last run counts.
        nonlocal closing
        if stored is None:
            raise FailureNotFound(failure_id)
        current = AiFailure.model_validate(stored)
        closing = current.open
        if not closing:
            return stored
        update = {"closed_at": timeutil.now(), "closed_reason": reason}
        return current.model_copy(update=update).model_dump(mode="json")

    try:
        written = AiFailure.model_validate(
            await store.update(Collection.AI_FAILURES, failure_id, change)
        )
    except FailureNotFound:
        return None
    if not closing:
        return None
    book = _audit_book(store)
    if written.id in book.unaudited:
        book.unaudited.discard(written.id)
        bus.publish(SseEvent.AI_FAILURE, written)
        return written
    await audit.record(
        store,
        actor=SYSTEM_ACTOR,
        action=AuditAction.AI_FAILURE_CLOSED,
        after={
            "failure_id": written.id,
            "flight_id": written.flight_id,
            "proxy_flight": written.proxy_flight,
        },
        note=reason,
    )
    bus.publish(SseEvent.AI_FAILURE, written)
    return written


async def mark_handled(
    store: Store, bus: EventBus, failure_id: str, *, actor: str, note: str
) -> AiFailure:
    """A dispatcher says the flight was handled by hand; marking twice keeps the first, and a
    failure code closed meanwhile is returned as it is, with nobody recorded as handling it."""
    doc = await store.get(Collection.AI_FAILURES, failure_id)
    if doc is None:
        raise FailureNotFound(failure_id)
    failure = AiFailure.model_validate(doc)
    if not failure.open:
        return failure
    handled = failure.model_copy(
        update={
            "handled_by": actor,
            "handled_at": timeutil.now(),
            "handled_note": note.strip()[:MAX_NOTE_CHARS] or None,
        }
    )
    await store.put(Collection.AI_FAILURES, failure_id, handled.model_dump(mode="json"))
    await audit.record(
        store,
        actor=actor,
        action=AuditAction.AI_FAILURE_HANDLED,
        after={"failure_id": failure_id, "flight_id": failure.flight_id},
        note=handled.handled_note,
    )
    bus.publish(SseEvent.AI_FAILURE, handled)
    return handled


async def list_failures(
    store: Store,
    *,
    open_only: bool = True,
    replay: bool | None = None,
    run_since: datetime | None = None,
    limit: int = 50,
) -> list[AiFailure]:
    """Newest recorded first, from the newest ``LIST_WINDOW`` records. ``run_since`` keeps only
    the replay run that started then (wall clock). Records stored before ``recorded_wall_at``
    existed sort last (Firestore leaves them out)."""
    docs = await store.query(
        Collection.AI_FAILURES, [], order_by="recorded_wall_at", descending=True, limit=LIST_WINDOW
    )
    failures = [AiFailure.model_validate(doc) for doc in docs]
    return [
        failure
        for failure in failures
        if (not open_only or failure.open)
        and (replay is None or failure.replay == replay)
        and of_run(failure, run_since)
    ][:limit]
