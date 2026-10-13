"""Flights the AI could not plan or draft for: stored once, audited, handled by a dispatcher,
or closed by code (audited under the system actor) once they no longer stand. There is no
substitute plan or template message."""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tephra.desk import audit
from tephra.desk.approvals import SYSTEM_ACTOR
from tephra.desk.failures import (
    DRAFT_WAITING,
    REPLAY_RUN_ENDED,
    FailureNotFound,
    close_failure,
    list_failures,
    mark_handled,
    record_failure,
)
from tephra.models import AiFailure, AuditAction, SseEvent
from tephra.store.base import Collection
from tephra.store.sqlite_store import SqliteStore
from tephra.util.events import EventBus
from tephra.util.timeutil import FixedClock, SystemClock, use_clock

AT = datetime(2026, 10, 9, 19, 40, tzinfo=UTC)


@pytest.fixture(autouse=True)
def clock() -> Iterator[None]:
    with use_clock(FixedClock(AT)):
        yield


@pytest.fixture
async def store(tmp_path: Path) -> AsyncIterator[SqliteStore]:
    opened = SqliteStore(tmp_path / "tephra.sqlite3", tmp_path / "blobs")
    yield opened
    await opened.aclose()


def failure(**changes: object) -> AiFailure:
    base = AiFailure(
        id="AIF00001",
        created_at=AT,
        replay=False,
        stage="planner",
        reason="PLANNER AGENT ERROR: RuntimeError",
        model_id="gemini-3.5-flash-lite",
        volcano_id="263300",
        volcano_name="Semeru",
        flight_id="8a0001:263300",
        proxy_flight="RFA4238",
        callsign="GIA417",
        hex="8a0001",
        type_icao="B738",
        cone_id="CONE0001",
        minutes_to_entry=12,
        inside_now=False,
    )
    return base.model_copy(update=changes)


async def test_a_failure_is_stored_once_audited_and_published(store: SqliteStore) -> None:
    bus = EventBus()
    queue = bus.subscribe()
    first = await record_failure(store, bus, failure())
    again = await record_failure(store, bus, failure(reason="another error"))
    assert first is not None
    assert again is None
    assert [item.id for item in await list_failures(store)] == ["AIF00001"]
    entries = await audit.list_entries(store, limit=10)
    assert [entry.action for entry in entries] == [AuditAction.AI_FAILED]
    assert entries[0].note == "PLANNER AGENT ERROR: RuntimeError"
    event = await queue.get(within_s=0.5)
    assert event is not None
    assert event.name == SseEvent.AI_FAILURE


async def test_a_dispatcher_marks_it_handled_once(store: SqliteStore) -> None:
    bus = EventBus()
    await record_failure(store, bus, failure())
    handled = await mark_handled(
        store, bus, "AIF00001", actor="desk:duty", note="  Called crew, climbing FL380  "
    )
    assert handled.handled_by == "desk:duty"
    assert handled.handled_at == AT
    assert handled.handled_note == "Called crew, climbing FL380"
    again = await mark_handled(store, bus, "AIF00001", actor="desk:other", note="late")
    assert again.handled_by == "desk:duty"
    assert await list_failures(store) == []
    assert [item.id for item in await list_failures(store, open_only=False)] == ["AIF00001"]
    actions = [entry.action for entry in await audit.list_entries(store, limit=10)]
    assert actions.count(AuditAction.AI_FAILURE_HANDLED) == 1


async def test_unknown_failure_is_refused(store: SqliteStore) -> None:
    with pytest.raises(FailureNotFound):
        await mark_handled(store, EventBus(), "AIF404", actor="desk:duty", note="")


async def test_replay_and_live_failures_are_listed_apart(store: SqliteStore) -> None:
    bus = EventBus()
    await record_failure(store, bus, failure())
    await record_failure(store, bus, failure(id="AIF00002", replay=True))
    assert [item.id for item in await list_failures(store, replay=True)] == ["AIF00002"]
    assert [item.id for item in await list_failures(store, replay=False)] == ["AIF00001"]


async def test_a_recorded_failure_carries_its_wall_clock_time(store: SqliteStore) -> None:
    before = SystemClock().now()
    recorded = await record_failure(store, EventBus(), failure())
    assert recorded is not None
    assert recorded.recorded_wall_at is not None
    assert recorded.recorded_wall_at >= before
    assert recorded.created_at == AT  # the active clock, as the replay plays it


async def test_code_closes_a_failure_as_the_system_never_as_a_dispatcher(
    store: SqliteStore,
) -> None:
    bus = EventBus()
    await record_failure(store, bus, failure())
    queue = bus.subscribe()
    closed = await close_failure(store, bus, "AIF00001", reason=DRAFT_WAITING)
    assert closed is not None
    assert (closed.closed_at, closed.closed_reason) == (AT, DRAFT_WAITING)
    assert (closed.handled_by, closed.handled_at, closed.handled_note) == (None, None, None)
    assert not closed.open
    assert await list_failures(store) == []
    assert await close_failure(store, bus, "AIF00001", reason=DRAFT_WAITING) is None
    entries = await audit.list_entries(store, limit=10)
    closing = [entry for entry in entries if entry.action is AuditAction.AI_FAILURE_CLOSED]
    assert [(entry.actor, entry.note) for entry in closing] == [(SYSTEM_ACTOR, DRAFT_WAITING)]
    event = await queue.get(within_s=0.5)
    assert event is not None
    assert event.name == SseEvent.AI_FAILURE
    assert event.data["closed_reason"] == DRAFT_WAITING


async def test_a_handled_failure_stays_the_dispatchers_and_a_closed_one_stays_closed(
    store: SqliteStore,
) -> None:
    bus = EventBus()
    await record_failure(store, bus, failure())
    await record_failure(store, bus, failure(id="AIF00002", flight_id="8a0002:263300"))
    await mark_handled(store, bus, "AIF00001", actor="desk:duty", note="Called the crew")
    assert await close_failure(store, bus, "AIF00001", reason=DRAFT_WAITING) is None
    await close_failure(store, bus, "AIF00002", reason=DRAFT_WAITING)
    late = await mark_handled(store, bus, "AIF00002", actor="desk:duty", note="too late")
    assert (late.handled_by, late.closed_reason) == (None, DRAFT_WAITING)
    handled = AiFailure.model_validate(await store.get(Collection.AI_FAILURES, "AIF00001"))
    assert (handled.handled_by, handled.closed_at) == ("desk:duty", None)
    actions = [entry.action for entry in await audit.list_entries(store, limit=20)]
    assert actions.count(AuditAction.AI_FAILURE_HANDLED) == 1
    assert actions.count(AuditAction.AI_FAILURE_CLOSED) == 1
    assert await close_failure(store, bus, "AIF404", reason=DRAFT_WAITING) is None


async def test_a_failure_code_closed_opens_again_when_it_recurs(store: SqliteStore) -> None:
    bus = EventBus()
    await record_failure(store, bus, failure())
    await close_failure(store, bus, "AIF00001", reason=DRAFT_WAITING)
    again = await record_failure(store, bus, failure(reason="PLANNER AGENT ERROR: TimeoutError"))
    assert again is not None
    assert again.open
    assert [item.reason for item in await list_failures(store)] == [
        "PLANNER AGENT ERROR: TimeoutError"
    ]


async def test_each_replay_run_has_its_own_failures(store: SqliteStore) -> None:
    """A replay plays the recording again on every run: the same flight failing again is a
    new failure of the new run, and the earlier run's failure closes with its run."""
    bus = EventBus()
    first_run = SystemClock().now() - timedelta(hours=2)
    earlier = failure(replay=True, recorded_wall_at=first_run + timedelta(minutes=5))
    await store.put(Collection.AI_FAILURES, earlier.id, earlier.model_dump(mode="json"))
    second_run = first_run + timedelta(hours=1)  # the recording plays again from its start
    assert await list_failures(store, replay=True, run_since=second_run) == []
    assert len(await list_failures(store, replay=True, run_since=first_run)) == 1

    again = await record_failure(store, bus, failure(replay=True), run_since=second_run)
    assert again is not None
    assert again.recorded_wall_at is not None
    assert again.recorded_wall_at >= second_run
    listed = await list_failures(store, replay=True, run_since=second_run)
    assert [(item.id, item.open) for item in listed] == [("AIF00001", True)]
    entries = await audit.list_entries(store, limit=10)
    assert [(entry.action, entry.actor) for entry in reversed(entries)] == [
        (AuditAction.AI_FAILURE_CLOSED, SYSTEM_ACTOR),
        (AuditAction.AI_FAILED, SYSTEM_ACTOR),
    ]
    assert entries[1].note == REPLAY_RUN_ENDED
