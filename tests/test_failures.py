"""Flights the AI could not plan or draft for: stored once, audited, and closed only by a
dispatcher. There is no substitute plan or template message."""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tephra.desk import audit
from tephra.desk.failures import FailureNotFound, list_failures, mark_handled, record_failure
from tephra.models import AiFailure, AuditAction, SseEvent
from tephra.store.sqlite_store import SqliteStore
from tephra.util.events import EventBus
from tephra.util.timeutil import FixedClock, use_clock

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
