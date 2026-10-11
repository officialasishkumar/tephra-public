"""The recovery plan's state machine: DRAFT -> APPROVED | REJECTED (dispatcher) or SUPERSEDED
(a newer DRAFT of the same mode).

Every move is a version check, an audit entry and a ``recovery`` event. Approval stores
nothing outbound: crew and passenger messages for an approved plan are drafted (and approved
again) by the message module. A run that ended ``AI_UNAVAILABLE`` is stored and audited as an
AI failure, and nothing can decide it.
"""

import asyncio
import weakref
from typing import Final

from tephra.desk import audit
from tephra.models import AuditAction, SseEvent
from tephra.recovery.models import RecoveryPlan
from tephra.store.base import Collection, Store
from tephra.util import timeutil
from tephra.util.events import EventBus

__all__ = [
    "InvalidTransition",
    "PlanNotFound",
    "RejectedInput",
    "VersionConflict",
    "approve",
    "list_plans",
    "reject",
    "submit_plan",
]

SYSTEM_ACTOR: Final = "system"
MIN_REJECT_REASON_CHARS: Final = 3
_locks: "weakref.WeakKeyDictionary[Store, asyncio.Lock]" = weakref.WeakKeyDictionary()


class PlanNotFound(Exception): ...


class InvalidTransition(Exception): ...


class RejectedInput(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


class VersionConflict(Exception):
    def __init__(self, current: RecoveryPlan) -> None:
        super().__init__(f"recovery plan {current.id} is at version {current.version}")
        self.current = current


def _lock(store: Store) -> asyncio.Lock:
    lock = _locks.get(store)
    if lock is None:
        lock = _locks[store] = asyncio.Lock()
    return lock


async def submit_plan(store: Store, bus: EventBus, plan: RecoveryPlan) -> RecoveryPlan:
    """Store a new plan. A DRAFT retires the open DRAFTs of the same mode."""
    async with _lock(store):
        await store.put(Collection.RECOVERY, plan.id, plan.model_dump(mode="json"))
        if plan.status == "AI_UNAVAILABLE":
            await audit.record(
                store,
                actor=SYSTEM_ACTOR,
                action=AuditAction.AI_FAILED,
                after={"recovery_id": plan.id, "stage": "recovery"},
                model_id=plan.model_id,
                prompt_hash=plan.prompt_hash,
                note=plan.unavailable_reason,
            )
        else:
            await _retire_older(store, bus, plan)
            await audit.record(
                store,
                actor=SYSTEM_ACTOR,
                action=AuditAction.RECOVERY_PROPOSED,
                after=_view(plan),
                model_id=plan.model_id,
                prompt_hash=plan.prompt_hash,
            )
    bus.publish(SseEvent.RECOVERY, plan)
    return plan


async def approve(
    store: Store, bus: EventBus, plan_id: str, *, expected_version: int, actor: str
) -> RecoveryPlan:
    return await _decide(
        store, bus, plan_id, expected_version=expected_version, actor=actor, status="APPROVED"
    )


async def reject(
    store: Store, bus: EventBus, plan_id: str, *, expected_version: int, reason: str, actor: str
) -> RecoveryPlan:
    cleaned = reason.strip()
    if len(cleaned) < MIN_REJECT_REASON_CHARS:
        raise RejectedInput(
            [f"a reject reason needs at least {MIN_REJECT_REASON_CHARS} characters"]
        )
    return await _decide(
        store,
        bus,
        plan_id,
        expected_version=expected_version,
        actor=actor,
        status="REJECTED",
        reject_reason=cleaned,
    )


async def list_plans(
    store: Store, *, replay: bool | None = None, limit: int = 20
) -> list[RecoveryPlan]:
    """Newest first."""
    docs = await store.list_docs(Collection.RECOVERY, limit=200, order_by="created_at")
    plans = [RecoveryPlan.model_validate(doc) for doc in docs]
    return [plan for plan in plans if replay is None or plan.replay == replay][:limit]


async def get_plan(store: Store, plan_id: str) -> RecoveryPlan | None:
    doc = await store.get(Collection.RECOVERY, plan_id)
    return None if doc is None else RecoveryPlan.model_validate(doc)


async def _decide(
    store: Store,
    bus: EventBus,
    plan_id: str,
    *,
    expected_version: int,
    actor: str,
    status: str,
    reject_reason: str | None = None,
) -> RecoveryPlan:
    async with _lock(store):
        current = await get_plan(store, plan_id)
        if current is None:
            raise PlanNotFound(plan_id)
        if current.version != expected_version:
            raise VersionConflict(current)
        if current.status != "DRAFT":
            raise InvalidTransition(f"recovery plan {plan_id} is {current.status}, not DRAFT")
        decided = current.model_copy(
            update={
                "status": status,
                "version": current.version + 1,
                "decided_by": actor,
                "decided_at": timeutil.now(),
                "reject_reason": reject_reason,
            }
        )
        await store.put(Collection.RECOVERY, plan_id, decided.model_dump(mode="json"))
        await audit.record(
            store,
            actor=actor,
            action=AuditAction.RECOVERY_DECIDED,
            before=_view(current),
            after=_view(decided),
            model_id=decided.model_id,
            prompt_hash=decided.prompt_hash,
            note=reject_reason,
        )
    bus.publish(SseEvent.RECOVERY, decided)
    return decided


async def _retire_older(store: Store, bus: EventBus, plan: RecoveryPlan) -> None:
    for old in await list_plans(store, replay=plan.replay, limit=200):
        if old.id == plan.id or old.status != "DRAFT":
            continue
        retired = old.model_copy(update={"status": "SUPERSEDED", "version": old.version + 1})
        await store.put(Collection.RECOVERY, old.id, retired.model_dump(mode="json"))
        bus.publish(SseEvent.RECOVERY, retired)


def _view(plan: RecoveryPlan) -> dict[str, object]:
    chosen = plan.chosen
    return {
        "status": plan.status,
        "version": plan.version,
        "chosen_scenario_id": plan.chosen_scenario_id,
        "total_usd": chosen.totals.total_usd if chosen and chosen.totals else None,
        "cancelled_flights": chosen.totals.cancelled_flights if chosen and chosen.totals else None,
        "rationale": plan.rationale,
    }
