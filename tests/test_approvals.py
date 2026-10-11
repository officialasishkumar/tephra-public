"""The desk's state machine: only a dispatcher moves a DRAFT, every move is versioned and
audited in a hash chain, and only APPROVED/EDITED advisories reach the outbound queue
(which never leaves the store)."""

import asyncio
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_api import make_advisory

from tephra.desk import audit
from tephra.desk.approvals import (
    SYSTEM_ACTOR,
    EditRejected,
    InvalidTransition,
    VersionConflict,
    approve,
    edit_and_approve,
    list_advisories,
    reject,
    submit_draft,
    supersede,
)
from tephra.models import Advisory, AdvisoryStatus, AuditAction
from tephra.store.base import Collection
from tephra.store.sqlite_store import SqliteStore
from tephra.util.events import EventBus
from tephra.util.timeutil import FixedClock, use_clock

AT = datetime(2026, 10, 9, 19, 40, tzinfo=UTC)
DESK = "desk:duty"


@pytest.fixture(autouse=True)
def clock() -> Iterator[None]:
    with use_clock(FixedClock(AT)):
        yield


@pytest.fixture
async def store(tmp_path: Path) -> AsyncIterator[SqliteStore]:
    opened = SqliteStore(tmp_path / "tephra.sqlite3", tmp_path / "blobs")
    yield opened
    await opened.aclose()


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


def draft(**changes: object) -> Advisory:
    return make_advisory().model_copy(update=changes)


async def outbound(store: SqliteStore) -> list[dict]:
    return await store.list_docs(Collection.OUTBOUND, limit=100)


async def actions(store: SqliteStore, advisory_id: str) -> list[AuditAction]:
    entries = await audit.list_entries(store, advisory_id=advisory_id)
    return [entry.action for entry in reversed(entries)]


async def test_submit_creates_a_draft_and_audits_it(store: SqliteStore, bus: EventBus) -> None:
    created = await submit_draft(store, bus, draft())
    assert created is not None
    assert created.status is AdvisoryStatus.DRAFT
    assert await actions(store, created.id) == [AuditAction.DRAFT_CREATED]
    assert await outbound(store) == []


async def test_approve_moves_to_outbound_and_bumps_version(
    store: SqliteStore, bus: EventBus
) -> None:
    created = await submit_draft(store, bus, draft())
    assert created is not None
    approved = await approve(store, bus, created.id, expected_version=1, actor=DESK)
    assert approved.status is AdvisoryStatus.APPROVED
    assert approved.version == 2
    assert approved.decided_by == DESK
    messages = await outbound(store)
    assert len(messages) == 1
    assert messages[0]["advisory_id"] == created.id
    assert await actions(store, created.id) == [
        AuditAction.DRAFT_CREATED,
        AuditAction.APPROVED,
        AuditAction.OUTBOUND_QUEUED,
    ]


async def test_every_decision_records_the_policy_the_draft_was_made_under(
    store: SqliteStore, bus: EventBus
) -> None:
    created = await submit_draft(
        store, bus, draft(policy_id="RFA-POLICY-A", policy_version="2026.10.1")
    )
    assert created is not None
    await approve(store, bus, created.id, expected_version=1, actor=DESK)
    entries = await audit.list_entries(store, advisory_id=created.id)
    views = {
        entry.action: entry.after
        for entry in entries
        if entry.action in {AuditAction.DRAFT_CREATED, AuditAction.APPROVED}
    }
    assert set(views) == {AuditAction.DRAFT_CREATED, AuditAction.APPROVED}
    for view in views.values():
        assert view is not None
        assert (view["policy_id"], view["policy_version"]) == ("RFA-POLICY-A", "2026.10.1")


async def test_stale_version_is_a_conflict(store: SqliteStore, bus: EventBus) -> None:
    created = await submit_draft(store, bus, draft())
    assert created is not None
    with pytest.raises(VersionConflict):
        await approve(store, bus, created.id, expected_version=7, actor=DESK)
    assert await outbound(store) == []


async def test_only_a_draft_can_be_decided(store: SqliteStore, bus: EventBus) -> None:
    created = await submit_draft(store, bus, draft())
    assert created is not None
    await approve(store, bus, created.id, expected_version=1, actor=DESK)
    with pytest.raises(InvalidTransition):
        await reject(store, bus, created.id, expected_version=2, reason="too late", actor=DESK)


async def test_reject_needs_a_reason_and_queues_nothing(store: SqliteStore, bus: EventBus) -> None:
    created = await submit_draft(store, bus, draft())
    assert created is not None
    with pytest.raises(EditRejected):
        await reject(store, bus, created.id, expected_version=1, reason=" x ", actor=DESK)
    rejected = await reject(
        store, bus, created.id, expected_version=1, reason="ALTERNATE CLOSED", actor=DESK
    )
    assert rejected.status is AdvisoryStatus.REJECTED
    assert rejected.reject_reason
    assert await outbound(store) == []


async def test_edit_keeps_both_bodies_and_sends_the_edited_one(
    store: SqliteStore, bus: EventBus
) -> None:
    created = await submit_draft(store, bus, draft())
    assert created is not None
    edited = await edit_and_approve(
        store, bus, created.id, expected_version=1, body="  hold fl330 report var  ", actor=DESK
    )
    assert edited.status is AdvisoryStatus.EDITED
    assert edited.body == created.body
    assert edited.edited_body == "HOLD FL330 REPORT VAR"
    messages = await outbound(store)
    assert len(messages) == 1
    assert "HOLD FL330 REPORT VAR" in messages[0]["text"]
    with pytest.raises(EditRejected):
        await edit_and_approve(store, bus, created.id, expected_version=2, body="   ", actor=DESK)


async def test_same_dedupe_key_is_not_drafted_twice(store: SqliteStore, bus: EventBus) -> None:
    assert await submit_draft(store, bus, draft()) is not None
    assert await submit_draft(store, bus, draft(id="adv_bbbbbbbbbbbb")) is None


async def test_new_plan_for_the_same_flight_supersedes_the_open_draft(
    store: SqliteStore, bus: EventBus
) -> None:
    first = await submit_draft(store, bus, draft())
    assert first is not None
    second = await submit_draft(
        store, bus, draft(id="adv_cccccccccccc", dedupe_key="DD-ffffffffffff")
    )
    assert second is not None
    drafts = await list_advisories(store, status=AdvisoryStatus.DRAFT)
    assert [a.id for a in drafts] == [second.id]
    superseded = await list_advisories(store, status=AdvisoryStatus.SUPERSEDED)
    assert [a.id for a in superseded] == [first.id]
    assert superseded[0].superseded_by == second.id


async def test_recently_approved_plan_is_not_redrafted(store: SqliteStore, bus: EventBus) -> None:
    created = await submit_draft(store, bus, draft())
    assert created is not None
    await approve(store, bus, created.id, expected_version=1, actor=DESK)
    assert await submit_draft(store, bus, draft(id="adv_dddddddddddd")) is None


async def test_two_dispatchers_at_once_decide_once(store: SqliteStore, bus: EventBus) -> None:
    created = await submit_draft(store, bus, draft())
    assert created is not None
    results = await asyncio.gather(
        approve(store, bus, created.id, expected_version=1, actor="desk:one"),
        edit_and_approve(
            store, bus, created.id, expected_version=1, body="HOLD FL330", actor="desk:two"
        ),
        approve(store, bus, created.id, expected_version=1, actor="desk:three"),
        return_exceptions=True,
    )
    decided = [result for result in results if isinstance(result, Advisory)]
    assert len(decided) == 1
    losers = [result for result in results if not isinstance(result, Advisory)]
    assert all(isinstance(loser, VersionConflict) for loser in losers)
    assert all(loser.current.version == 2 for loser in losers if isinstance(loser, VersionConflict))
    messages = await outbound(store)
    assert [(m["advisory_id"], m["approved_by"]) for m in messages] == [
        (created.id, decided[0].decided_by)
    ]
    assert await actions(store, created.id) == [
        AuditAction.DRAFT_CREATED,
        AuditAction(decided[0].status.value),
        AuditAction.OUTBOUND_QUEUED,
    ]
    assert await audit.verify_chain(store) == []


async def test_supersede_racing_a_dispatcher_moves_the_draft_once(
    store: SqliteStore, bus: EventBus
) -> None:
    created = await submit_draft(store, bus, draft())
    assert created is not None
    approved, retired = await asyncio.gather(
        approve(store, bus, created.id, expected_version=1, actor=DESK),
        supersede(store, bus, created.id, reason="NO LONGER EXPOSED"),
        return_exceptions=True,
    )
    final = (await list_advisories(store))[0]
    assert final.version == 2
    if isinstance(approved, Advisory):
        assert retired is None
        assert final.status is AdvisoryStatus.APPROVED
        assert len(await outbound(store)) == 1
    else:
        assert isinstance(approved, VersionConflict)
        assert final.status is AdvisoryStatus.SUPERSEDED
        assert await outbound(store) == []
    assert await audit.verify_chain(store) == []


async def test_audit_chain_holds_under_concurrent_writers(store: SqliteStore) -> None:
    await asyncio.gather(
        *(
            audit.record(store, actor=SYSTEM_ACTOR, action=AuditAction.AI_FAILED, note=str(n))
            for n in range(30)
        )
    )
    assert len(await audit.list_entries(store, limit=100)) == 30
    assert await audit.verify_chain(store) == []  # seq runs 1..30 and every link holds


async def test_audit_chain_detects_an_edited_entry(store: SqliteStore) -> None:
    for n in range(3):
        await audit.record(store, actor=SYSTEM_ACTOR, action=AuditAction.AI_FAILED, note=str(n))
    middle = (await audit.list_entries(store, limit=3))[1]
    doc = await store.get(Collection.AUDIT, middle.id)
    assert doc is not None
    await store.put(Collection.AUDIT, middle.id, {**doc, "note": "rewritten"})
    assert await audit.verify_chain(store) == [
        f"entry {middle.id}: content does not match its hash"
    ]


async def test_a_decision_after_now_does_not_block_a_new_draft(
    store: SqliteStore, bus: EventBus
) -> None:
    """The replay clock loops back to the recording's start, so the time of a decision made
    late in the recording lies ahead of ``now()`` on the next pass; that is not 'recent'."""
    created = await submit_draft(store, bus, draft())
    assert created is not None
    await approve(store, bus, created.id, expected_version=1, actor=DESK)
    with use_clock(FixedClock(AT - timedelta(hours=2))):
        again = await submit_draft(store, bus, draft(id="adv_dddddddddddd"))
    assert again is not None
    assert again.status is AdvisoryStatus.DRAFT


async def test_recorded_and_live_drafts_never_dedupe_against_each_other(
    store: SqliteStore, bus: EventBus
) -> None:
    """The same airframe can fly in a recorded case and live; a recording must not stop or
    retire a live advisory, nor the other way round."""
    replayed = await submit_draft(store, bus, draft(replay=True))
    assert replayed is not None
    live_same_advice = await submit_draft(store, bus, draft(id="adv_aaaaaaaaaaa1"))
    assert live_same_advice is not None
    live_new_advice = await submit_draft(
        store, bus, draft(id="adv_aaaaaaaaaaa2", dedupe_key="DD-aaaaaaaaaaaa")
    )
    assert live_new_advice is not None
    drafts = {a.id for a in await list_advisories(store, status=AdvisoryStatus.DRAFT)}
    assert drafts == {replayed.id, live_new_advice.id}


async def test_a_recorded_approval_does_not_suppress_live_advice(
    store: SqliteStore, bus: EventBus
) -> None:
    replayed = await submit_draft(store, bus, draft(replay=True))
    assert replayed is not None
    await approve(store, bus, replayed.id, expected_version=1, actor=DESK)
    assert await submit_draft(store, bus, draft(id="adv_aaaaaaaaaaa3")) is not None
    assert await submit_draft(store, bus, draft(id="adv_aaaaaaaaaaa4", replay=True)) is None


async def test_audit_chain_is_intact_after_every_kind_of_move(
    store: SqliteStore, bus: EventBus
) -> None:
    one = await submit_draft(store, bus, draft())
    two = await submit_draft(
        store,
        bus,
        draft(id="adv_eeeeeeeeeeee", flight_id="8a0999:263300", hex="8a0999", dedupe_key="DD-2"),
    )
    assert one is not None
    assert two is not None
    await approve(store, bus, one.id, expected_version=1, actor=DESK)
    await reject(store, bus, two.id, expected_version=1, reason="CREW ALREADY ADVISED", actor=DESK)
    assert await audit.verify_chain(store) == []
