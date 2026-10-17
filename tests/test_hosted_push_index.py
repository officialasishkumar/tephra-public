"""Pushes cost no store read (D23): the in-memory key index, rotation that stops the old key at
once, and the per-section and per-key counts written back at most every 10 minutes."""

from datetime import timedelta
from pathlib import Path

import pytest

from tephra.desk.connections import (
    ConnectionNotFound,
    KeyIndex,
    create_connection,
    list_connections,
    rotate_connection,
)
from tephra.hosted.feeds import FLUSH_EVERY, ConnectionStats, FeedStats
from tephra.models import AuditAction, PushProblem, PushResult
from tephra.store.base import Collection
from tests.test_hosted_tenants import chain_of, set_up, wall, world


async def test_the_index_finds_live_keys_without_reading(tmp_path: Path) -> None:
    w = world(tmp_path)
    await set_up(w)
    space = w.space("RFB")
    with space.bound():
        one, key_one = await create_connection(space.store, "ops-feed-1", actor="desk:Ana")
        _two, key_two = await create_connection(space.store, "ops-feed-2", actor="desk:Ana")
        index = KeyIndex.build(await list_connections(space.store))
    reads = sum(w.meter.day().reads.values())
    found = index.find(key_one)
    assert found is not None
    assert found.id == one.id
    assert index.find(key_two) is not None
    assert index.find("tph_" + "x" * 32) is None
    assert index.find(key_one[4:]) is None
    assert sum(w.meter.day().reads.values()) == reads
    assert len(index) == 2
    await w.aclose()


async def test_rotation_stops_the_old_key_at_once_and_writes_both_entries(tmp_path: Path) -> None:
    w = world(tmp_path)
    await set_up(w)
    space = w.space("RFB")
    with space.bound():
        old, old_key = await create_connection(space.store, "ops-feed-1", actor="desk:Ana")
        new, new_key = await rotate_connection(space.store, old.id, actor="desk:Ana")
        index = KeyIndex.build(await list_connections(space.store))
        with pytest.raises(ConnectionNotFound):
            await rotate_connection(space.store, old.id, actor="desk:Ana")
    assert new.name == "ops-feed-1"
    assert new.id != old.id
    assert index.find(old_key) is None
    rotated = index.find(new_key)
    assert rotated is not None
    assert rotated.id == new.id
    actions = [e.action for e in await chain_of(w, "RFB")][-3:]
    assert actions == [
        AuditAction.CONNECTION_CREATED,
        AuditAction.CONNECTION_REVOKED,
        AuditAction.CONNECTION_CREATED,
    ]
    await w.aclose()


def test_feed_cards_count_the_last_hour_and_group_reasons_by_their_words() -> None:
    now = wall()
    stats = FeedStats(since=now - timedelta(hours=2))
    late = (
        "observed_at 2026-10-17T13:50:00.000Z is not within 5 min of TEPHRA's clock "
        "(2026-10-17T14:00:00.000Z)"
    )
    later = late.replace("13:50", "13:51").replace("14:00:00", "14:01:00")
    result = PushResult(
        connection_id="CN-0a1b2c3d4e",
        received_at=now,
        accepted=8,
        rejected=[
            PushProblem(section="positions", index=4, reason=late),
            PushProblem(section="positions", index=7, reason=later),
            PushProblem(section="flight_plans", index=0, reason="flight: needed"),
        ],
        plans_taken=2,
    )
    stats.record_push(result, wall_at=now - timedelta(minutes=70))
    stats.record_push(result, wall_at=now - timedelta(minutes=5))
    positions = stats.card("positions", declared=True, now=now)
    assert positions.records_last_hour == 10
    assert positions.refused_last_hour == 2
    assert [(r.reason, r.count) for r in positions.reasons] == [
        ("observed_at is not within 5 min of TEPHRA's clock", 2)
    ]
    assert positions.last_received_at == now - timedelta(minutes=5)
    plans = stats.card("flight_plans", declared=True, now=now)
    assert (plans.records_last_hour, plans.refused_last_hour) == (3, 1)
    reports = stats.card("pilot_reports", declared=False, now=now, optional=True)
    assert (reports.records_last_hour, reports.last_received_at, reports.optional) == (
        0,
        None,
        True,
    )


def test_a_reason_counts_every_refusal_of_every_push() -> None:
    """Pushes of 1 then 9 stale records: the card says 10 refused and the reason 10, in words
    without the record's index or times (UX finding 2)."""
    now = wall()
    stats = FeedStats(since=now - timedelta(hours=2))

    def stale(n: int) -> PushResult:
        return PushResult(
            connection_id="CN-0a1b2c3d4e",
            received_at=now,
            accepted=0,
            rejected=[
                PushProblem(
                    section="positions",
                    index=i,
                    reason=f"observed_at 2026-10-17T13:{10 + i}:00.000Z is not within 5 min "
                    "of TEPHRA's clock (2026-10-17T14:00:00.000Z)",
                )
                for i in range(n)
            ]
            + [PushProblem(section="positions", index=n, reason="lat: needed")],
        )

    stats.record_push(stale(1), wall_at=now - timedelta(minutes=2))
    stats.record_push(stale(9), wall_at=now - timedelta(minutes=1))
    card = stats.card("positions", declared=True, now=now)
    assert card.refused_last_hour == 12
    assert [(r.reason, r.count) for r in card.reasons] == [
        ("observed_at is not within 5 min of TEPHRA's clock", 10),
        ("lat: needed", 2),
    ]


async def test_key_counters_are_written_back_at_most_every_ten_minutes(tmp_path: Path) -> None:
    w = world(tmp_path)
    await set_up(w)
    space = w.space("RFB")
    with space.bound():
        made, _ = await create_connection(space.store, "ops-feed-1", actor="desk:Ana")
    now = wall()
    counts = ConnectionStats(since=now)
    counts.note(made.id, accepted=10, rejected=1, sections={"positions"}, at=now)
    assert counts.wait_s(made, at=now + timedelta(seconds=4), gap_s=10) == pytest.approx(6)
    assert counts.wait_s(made, at=now + timedelta(seconds=10), gap_s=10) is None
    with space.bound():
        assert await counts.flush(space.store, at=now) == 1
        counts.note(made.id, accepted=5, rejected=0, sections={"flight_plans"}, at=now)
        assert await counts.flush(space.store, at=now + timedelta(minutes=1)) == 0
        assert await counts.flush(space.store, at=now + FLUSH_EVERY) == 1
        doc = await space.store.get(Collection.CONNECTIONS, made.id)
    assert doc is not None
    assert (doc["pushes"], doc["accepted"], doc["rejected"]) == (2, 15, 1)
    assert counts.sections_seen(made.id) == ["positions", "flight_plans"]
    await w.aclose()


async def test_a_failed_write_back_keeps_its_counts(tmp_path: Path) -> None:
    w = world(tmp_path)
    await set_up(w)
    space = w.space("RFB")
    with space.bound():
        made, _ = await create_connection(space.store, "ops-feed-1", actor="desk:Ana")
    counts = ConnectionStats(since=wall())
    counts.note(made.id, accepted=3, rejected=0, sections={"positions"}, at=wall())
    with pytest.raises(RuntimeError, match="outside its binding"):
        await counts.flush(space.store, at=wall(), force=True)
    assert counts.merged(made).accepted == 3
    with space.bound():
        assert await counts.flush(space.store, at=wall(), force=True) == 1
    await w.aclose()
