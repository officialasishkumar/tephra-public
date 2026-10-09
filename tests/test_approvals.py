"""The desk's state machine: only a dispatcher moves a DRAFT, every move is versioned and
audited in a hash chain, and only APPROVED/EDITED advisories reach the outbound queue
(which never leaves the store)."""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_api import make_advisory

from tephra.desk import audit
from tephra.desk.approvals import (
    EditRejected,
    InvalidTransition,
    VersionConflict,
    approve,
    edit_and_approve,
    list_advisories,
    reject,
    submit_draft,
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
