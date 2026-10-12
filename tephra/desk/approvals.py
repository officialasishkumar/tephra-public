"""The advisory state machine: DRAFT -> APPROVED | EDITED | REJECTED (dispatcher) or
SUPERSEDED (code).

Only a DRAFT ever moves. Every transition is a compare-and-set on ``version`` (so two
dispatchers cannot both decide the same draft), an audit entry, and an ``advisory`` event.
APPROVED and EDITED advisories are copied to TEPHRA's own ``outbound`` collection, which is
as far as anything goes: nothing here calls an external system.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any, Final
from uuid import uuid4

from tephra.agents.validators import technique_problems
from tephra.config import ADVISORY_BODY_MAX_CHARS
from tephra.desk import audit
from tephra.models import (
    Advisory,
    AdvisoryStatus,
    AuditAction,
    OutboundMessage,
    SseEvent,
)
from tephra.store.base import Collection, Store, Where
from tephra.util import timeutil
from tephra.util.events import EventBus

__all__ = [
    "SYSTEM_ACTOR",
    "AdvisoryNotFound",
    "EditRejected",
    "InvalidTransition",
    "VersionConflict",
    "approve",
    "edit_and_approve",
    "get_advisory",
    "list_advisories",
    "reject",
    "submit_draft",
    "supersede",
]

SYSTEM_ACTOR: Final = "system"
RECENT_DECISION_MIN: Final = 60
"""An APPROVED/EDITED advisory suppresses an identical new draft for this long."""
MIN_REJECT_REASON_CHARS: Final = 3
MIN_CREW_REASON_CHARS: Final = 12
"""A reason to keep a flight on a route a crew report of ash flags must say something: a
sentence fragment, not a word."""
_QUEUED_STATUSES: Final = frozenset({AdvisoryStatus.APPROVED, AdvisoryStatus.EDITED})


class VersionConflict(Exception):
    """The dispatcher decided on a version that is no longer current."""

    def __init__(self, current: Advisory) -> None:
        super().__init__(f"advisory {current.id} is at version {current.version}")
        self.current = current


class InvalidTransition(Exception): ...


class AdvisoryNotFound(Exception): ...


class EditRejected(Exception):
    """A dispatcher's input failed validation: an edited body or a reject reason."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


# --- creation ---------------------------------------------------------------------------


async def submit_draft(
    store: Store, bus: EventBus, advisory: Advisory, *, replacing: Sequence[str] = ()
) -> Advisory | None:
    """Store a new DRAFT unless it repeats an open or recently approved one.

    An open DRAFT for the same flight with the same ``dedupe_key`` wins (None is
    returned); one with a different key is superseded by the new draft. ``replacing`` names
    open drafts the caller is replacing with this one: they never count as a repeat, and the
    caller supersedes them once this draft is stored, so a refused draft leaves them up. A
    decision on the same advice in the last hour wins only if it was made when the entry was
    at least as urgent (``urgency_bucket``): advice approved further out does not cover a
    flight that is now closer. Recorded (REPLAY) and live advisories are never compared: the
    same airframe can appear in both.
    """
    if advisory.status is not AdvisoryStatus.DRAFT or advisory.version != 1:
        raise InvalidTransition("only a new DRAFT at version 1 can be submitted")
    same_mode = Where("replay", "==", advisory.replay)
    open_drafts = await _query(
        store,
        Where("flight_id", "==", advisory.flight_id),
        Where("status", "==", AdvisoryStatus.DRAFT.value),
        same_mode,
    )
    replaced = set(replacing)
    if any(
        draft.dedupe_key == advisory.dedupe_key and draft.id not in replaced
        for draft in open_drafts
    ):
        return None
    if await _recently_queued(
        store, advisory, Where("dedupe_key", "==", advisory.dedupe_key), same_mode
    ):
        return None
    if not await store.compare_and_set_advisory(advisory.id, 0, advisory.model_dump(mode="json")):
        raise InvalidTransition(f"advisory {advisory.id} already exists")
    await audit.record(
        store,
        actor=SYSTEM_ACTOR,
        action=AuditAction.DRAFT_CREATED,
        advisory_id=advisory.id,
        after=_audit_view(advisory),
        input_hashes=_input_hashes(advisory),
        model_id=advisory.model_id,
        prompt_hash=advisory.prompt_hashes.get("drafter"),
    )
    bus.publish(SseEvent.ADVISORY, advisory)
    for draft in open_drafts:
        if draft.id in replaced:
            continue
        await supersede(
            store, bus, draft.id, reason="REPLACED BY A NEWER DRAFT", superseded_by=advisory.id
        )
    return advisory


async def _recently_queued(store: Store, advisory: Advisory, *where: Where) -> bool:
    """A decision counts only within the last hour up to ``now()`` (the replay clock loops,
    and a decision made later in the recording is not recent on the next pass), and only if
    it was made when the entry was at least as urgent as the new draft's."""
    at = timeutil.now()
    cutoff = at - timedelta(minutes=RECENT_DECISION_MIN)
    previous = await _query(store, *where)
    return any(
        item.status in _QUEUED_STATUSES
        and item.decided_at is not None
        and cutoff <= item.decided_at <= at
        and _as_urgent(item, advisory)
        for item in previous
    )


def _as_urgent(decided: Advisory, new: Advisory) -> bool:
    """A lower bucket is more urgent. Drafts from before ``urgency_bucket`` compare as they
    always did: any recent decision on the same advice covers the new draft."""
    if decided.urgency_bucket is None or new.urgency_bucket is None:
        return True
    return decided.urgency_bucket <= new.urgency_bucket


# --- dispatcher decisions ---------------------------------------------------------------


async def approve(
    store: Store,
    bus: EventBus,
    advisory_id: str,
    *,
    expected_version: int,
    actor: str,
    reason: str | None = None,
    note: str | None = None,
) -> Advisory:
    """``reason`` is the dispatcher's written reason when a rule asks for one (the caller
    checks the rule); ``note`` goes to the audit entry."""
    return await _decide(
        store,
        bus,
        advisory_id,
        expected_version=expected_version,
        actor=actor,
        status=AdvisoryStatus.APPROVED,
        changes={"decision_reason": reason},
        note=note,
    )


async def edit_and_approve(
    store: Store,
    bus: EventBus,
    advisory_id: str,
    *,
    expected_version: int,
    body: str,
    actor: str,
    reason: str | None = None,
    note: str | None = None,
) -> Advisory:
    edited = body.strip().upper()
    problems: list[str] = []
    if not edited:
        problems.append("edited body is empty")
    if len(edited) > ADVISORY_BODY_MAX_CHARS:
        problems.append(
            f"edited body is {len(edited)} characters; the limit is {ADVISORY_BODY_MAX_CHARS}"
        )
    problems.extend(technique_problems(edited))
    if problems:
        raise EditRejected(problems)
    return await _decide(
        store,
        bus,
        advisory_id,
        expected_version=expected_version,
        actor=actor,
        status=AdvisoryStatus.EDITED,
        changes={"edited_body": edited, "decision_reason": reason},
        note=note,
    )


async def reject(
    store: Store,
    bus: EventBus,
    advisory_id: str,
    *,
    expected_version: int,
    reason: str,
    actor: str,
) -> Advisory:
    cleaned = reason.strip()
    if len(cleaned) < MIN_REJECT_REASON_CHARS:
        raise EditRejected([f"a reject reason needs at least {MIN_REJECT_REASON_CHARS} characters"])
    return await _decide(
        store,
        bus,
        advisory_id,
        expected_version=expected_version,
        actor=actor,
        status=AdvisoryStatus.REJECTED,
        changes={"reject_reason": cleaned},
    )


async def _decide(
    store: Store,
    bus: EventBus,
    advisory_id: str,
    *,
    expected_version: int,
    actor: str,
    status: AdvisoryStatus,
    changes: Mapping[str, Any],
    note: str | None = None,
) -> Advisory:
    current = await _load(store, advisory_id)
    if current is None:
        raise AdvisoryNotFound(advisory_id)
    if current.version != expected_version:
        raise VersionConflict(current)
    if current.status is not AdvisoryStatus.DRAFT:
        raise InvalidTransition(f"advisory {advisory_id} is {current.status.value}, not DRAFT")
    at = timeutil.now()
    decided = _advance(
        current, status=status, at=at, changes={**changes, "decided_by": actor, "decided_at": at}
    )
    if not await store.compare_and_set_advisory(
        advisory_id, current.version, decided.model_dump(mode="json")
    ):
        latest = await _load(store, advisory_id)
        if latest is None:
            raise AdvisoryNotFound(advisory_id)
        raise VersionConflict(latest)
    await _audit_transition(
        store, current, decided, actor=actor, action=AuditAction(status.value), note=note
    )
    if decided.status in _QUEUED_STATUSES:
        await _queue_outbound(store, decided, actor=actor)
    bus.publish(SseEvent.ADVISORY, decided)
    return decided


async def _queue_outbound(store: Store, advisory: Advisory, *, actor: str) -> None:
    message = OutboundMessage(
        id=uuid4().hex,
        advisory_id=advisory.id,
        advisory_version=advisory.version,
        queued_at=timeutil.now(),
        proxy_flight=advisory.proxy_flight,
        status=advisory.status,
        approved_by=actor,
        text=advisory.final_text,
        replay=advisory.replay,
        replay_case_id=advisory.replay_case_id,
        queued_wall_at=timeutil.SystemClock().now(),
        policy_id=advisory.policy_id,
        policy_version=advisory.policy_version,
        policy_hash=advisory.policy_hash,
    )
    await store.put(Collection.OUTBOUND, message.id, message.model_dump(mode="json"))
    await audit.record(
        store,
        actor=actor,
        action=AuditAction.OUTBOUND_QUEUED,
        advisory_id=advisory.id,
        after={
            "outbound_id": message.id,
            "advisory_version": message.advisory_version,
            "destination": message.destination,
            "policy_id": advisory.policy_id,
            "policy_version": advisory.policy_version,
            "policy_hash": advisory.policy_hash,
        },
        input_hashes=_input_hashes(advisory),
        model_id=advisory.model_id,
        prompt_hash=advisory.prompt_hashes.get("drafter"),
    )


# --- code transitions -------------------------------------------------------------------


async def supersede(
    store: Store,
    bus: EventBus,
    advisory_id: str,
    *,
    reason: str,
    superseded_by: str | None = None,
) -> Advisory | None:
    """Retire an open DRAFT; None when it is gone or a dispatcher has already decided it."""
    current = await _load(store, advisory_id)
    if current is None or current.status is not AdvisoryStatus.DRAFT:
        return None
    retired = _advance(
        current,
        status=AdvisoryStatus.SUPERSEDED,
        at=timeutil.now(),
        changes={"superseded_by": superseded_by},
    )
    if not await store.compare_and_set_advisory(
        advisory_id, current.version, retired.model_dump(mode="json")
    ):
        return None
    await _audit_transition(
        store, current, retired, actor=SYSTEM_ACTOR, action=AuditAction.SUPERSEDED, note=reason
    )
    bus.publish(SseEvent.ADVISORY, retired)
    return retired


# --- reads ------------------------------------------------------------------------------


async def list_advisories(
    store: Store, *, status: AdvisoryStatus | None = None, limit: int = 50
) -> list[Advisory]:
    """Newest first."""
    where = [] if status is None else [Where("status", "==", status.value)]
    docs = await store.query(
        Collection.ADVISORIES, where, order_by="created_at", descending=True, limit=limit
    )
    return [Advisory.model_validate(doc) for doc in docs]


async def get_advisory(store: Store, advisory_id: str) -> Advisory | None:
    return await _load(store, advisory_id)


async def _load(store: Store, advisory_id: str) -> Advisory | None:
    doc = await store.get(Collection.ADVISORIES, advisory_id)
    return None if doc is None else Advisory.model_validate(doc)


async def _query(store: Store, *where: Where) -> list[Advisory]:
    docs = await store.query(
        Collection.ADVISORIES, list(where), order_by="created_at", descending=True, limit=200
    )
    return [Advisory.model_validate(doc) for doc in docs]


# --- helpers ----------------------------------------------------------------------------


def _advance(
    current: Advisory, *, status: AdvisoryStatus, at: datetime, changes: Mapping[str, Any]
) -> Advisory:
    data = current.model_dump()
    data.update(changes)
    data.update(status=status, version=current.version + 1, updated_at=at)
    return Advisory.model_validate(data)


async def _audit_transition(
    store: Store,
    before: Advisory,
    after: Advisory,
    *,
    actor: str,
    action: AuditAction,
    note: str | None = None,
) -> None:
    await audit.record(
        store,
        actor=actor,
        action=action,
        advisory_id=after.id,
        before=_audit_view(before),
        after=_audit_view(after),
        input_hashes=_input_hashes(after),
        model_id=after.model_id,
        prompt_hash=after.prompt_hashes.get("drafter"),
        note=note,
    )


def _audit_view(advisory: Advisory) -> dict[str, Any]:
    return {
        "status": advisory.status.value,
        "version": advisory.version,
        "body": advisory.body,
        "edited_body": advisory.edited_body,
        "reject_reason": advisory.reject_reason,
        "decision_reason": advisory.decision_reason,
        "policy_id": advisory.policy_id,
        "policy_version": advisory.policy_version,
        "policy_hash": advisory.policy_hash,
    }


def _input_hashes(advisory: Advisory) -> list[str]:
    return [advisory.input_hash, *(source.sha256 for source in advisory.sources)]
