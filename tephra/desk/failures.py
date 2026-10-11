"""Flights the AI could not plan or draft for.

There is no substitute plan or template message. Each failure is stored once per flight,
cone and stage, audited, and shown on the Desk until a dispatcher marks it handled by hand.
"""

from typing import Final

from tephra.desk import audit
from tephra.desk.approvals import SYSTEM_ACTOR
from tephra.models import AiFailure, AuditAction, SseEvent
from tephra.store.base import Collection, Store
from tephra.util import timeutil
from tephra.util.events import EventBus

__all__ = ["FailureNotFound", "list_failures", "mark_handled", "record_failure"]

MAX_NOTE_CHARS: Final = 500


class FailureNotFound(Exception): ...


async def record_failure(store: Store, bus: EventBus, failure: AiFailure) -> AiFailure | None:
    """Store a new failure; None when the same flight, cone and stage already failed."""
    if await store.get(Collection.AI_FAILURES, failure.id) is not None:
        return None
    await store.put(Collection.AI_FAILURES, failure.id, failure.model_dump(mode="json"))
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
    bus.publish(SseEvent.AI_FAILURE, failure)
    return failure


async def mark_handled(
    store: Store, bus: EventBus, failure_id: str, *, actor: str, note: str
) -> AiFailure:
    """A dispatcher says the flight was handled by hand; marking twice keeps the first."""
    doc = await store.get(Collection.AI_FAILURES, failure_id)
    if doc is None:
        raise FailureNotFound(failure_id)
    failure = AiFailure.model_validate(doc)
    if failure.handled_at is not None:
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
    store: Store, *, open_only: bool = True, replay: bool | None = None, limit: int = 50
) -> list[AiFailure]:
    """Newest first."""
    docs = await store.query(
        Collection.AI_FAILURES, [], order_by="created_at", descending=True, limit=200
    )
    failures = [AiFailure.model_validate(doc) for doc in docs]
    return [
        failure
        for failure in failures
        if (not open_only or failure.handled_at is None)
        and (replay is None or failure.replay == replay)
    ][:limit]
