"""SqliteStore against the Store contract, plus the pure helpers of the Firestore store."""

import asyncio
import math
import sqlite3
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tephra.models import AuditAction, AuditEntry, FeedHealth, FeedId, FeedStatus
from tephra.store import decode_doc, encode_doc
from tephra.store.base import Collection, Where
from tephra.store.firestore_store import DOC_FIELD, index_fields, matches, plan_query
from tephra.store.sqlite_store import SqliteStore

AT = datetime(2026, 10, 9, 19, 40, tzinfo=UTC)


@pytest.fixture
async def store(tmp_path: Path) -> AsyncIterator[SqliteStore]:
    opened = SqliteStore(tmp_path / "tephra.sqlite3", tmp_path / "blobs")
    yield opened
    await opened.aclose()


async def _seed(store: SqliteStore) -> None:
    docs = [
        {"id": "a", "n": 1, "kind": "SIGMET", "at": "2026-10-09T18:00:00.000Z", "flag": True},
        {"id": "b", "n": 2, "kind": "VONA", "at": "2026-10-09T19:00:00.000Z", "flag": False},
        {"id": "c", "n": 3, "kind": "VAA", "at": "2026-10-09T20:00:00.000Z", "flag": True},
        {"id": "d", "n": 4, "kind": "VONA", "at": "2026-10-09T21:00:00.000Z", "gone": None},
    ]
    for doc in docs:
        await store.put("things", doc["id"], doc)


async def test_put_get_delete_round_trip_with_awkward_ids(store: SqliteStore) -> None:
    doc_id = "VAA:DARWIN:263300:2026/1157"
    doc = {"source_id": doc_id, "polygon": [[[112.9, -8.0], [113.2, -7.9], [112.9, -8.0]]]}
    await store.put(Collection.VAAS, doc_id, doc)
    assert await store.get(Collection.VAAS, doc_id) == doc
    await store.delete(Collection.VAAS, doc_id)
    assert await store.get(Collection.VAAS, doc_id) is None
    await store.delete(Collection.VAAS, doc_id)


async def test_put_replaces_and_collections_are_separate(store: SqliteStore) -> None:
    await store.put("one", "x", {"v": 1})
    await store.put("one", "x", {"v": 2})
    await store.put("two", "x", {"v": 3})
    assert await store.get("one", "x") == {"v": 2}
    assert await store.get("two", "x") == {"v": 3}


async def test_query_operators(store: SqliteStore) -> None:
    await _seed(store)

    async def ids(*where: Where) -> list[str]:
        docs = await store.query("things", list(where), order_by="n", descending=False)
        return [doc["id"] for doc in docs]

    assert await ids(Where("kind", "==", "VONA")) == ["b", "d"]
    assert await ids(Where("kind", "!=", "VONA")) == ["a", "c"]
    assert await ids(Where("n", "<", 3)) == ["a", "b"]
    assert await ids(Where("n", ">=", 3)) == ["c", "d"]
    assert await ids(Where("at", ">", "2026-10-09T19:00:00.000Z")) == ["c", "d"]
    assert await ids(Where("kind", "in", ["VAA", "SIGMET"])) == ["a", "c"]
    assert await ids(Where("kind", "in", [])) == []
    assert await ids(Where("flag", "==", True)) == ["a", "c"]
    assert await ids(Where("gone", "==", None)) == ["a", "b", "c", "d"]
    assert await ids(Where("kind", "==", "VONA"), Where("n", ">", 2)) == ["d"]


async def test_query_order_and_limit(store: SqliteStore) -> None:
    await _seed(store)
    newest = await store.query("things", order_by="at", descending=True, limit=2)
    assert [doc["id"] for doc in newest] == ["d", "c"]
    listed = await store.list_docs("things", limit=10, order_by="n", descending=False)
    assert [doc["id"] for doc in listed] == ["a", "b", "c", "d"]


async def test_query_rejects_unsafe_field_names(store: SqliteStore) -> None:
    with pytest.raises(ValueError, match="field name"):
        await store.query("things", [Where("n') OR 1=1 --", "==", 1)])


async def test_compare_and_set_advisory(store: SqliteStore) -> None:
    assert await store.compare_and_set_advisory("adv_1", 0, {"id": "adv_1", "version": 1})
    assert not await store.compare_and_set_advisory("adv_1", 0, {"id": "adv_1", "version": 1})
    assert not await store.compare_and_set_advisory("adv_1", 2, {"id": "adv_1", "version": 3})
    assert await store.compare_and_set_advisory("adv_1", 1, {"id": "adv_1", "version": 2})
    assert (await store.get(Collection.ADVISORIES, "adv_1")) == {"id": "adv_1", "version": 2}
    assert not await store.compare_and_set_advisory("adv_2", 1, {"id": "adv_2", "version": 2})
    with pytest.raises(ValueError, match="version"):
        await store.compare_and_set_advisory("adv_1", 2, {"id": "adv_1", "version": 2})


class _CommitFails:
    """A connection whose next COMMIT fails, as it can when the disk is full."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.armed = True

    @property
    def in_transaction(self) -> bool:
        return self.conn.in_transaction

    def execute(self, sql: str, *params: Any) -> sqlite3.Cursor:
        if sql == "COMMIT" and self.armed:
            self.armed = False
            raise sqlite3.OperationalError("database or disk is full")
        return self.conn.execute(sql, *params)


async def test_failed_commit_leaves_no_transaction_open(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "tephra.sqlite3", tmp_path / "blobs")
    await store.put("things", "warm", {"v": 0})
    real = store._conn
    assert real is not None
    flaky = _CommitFails(real)
    store._conn = flaky  # type: ignore[assignment]
    with pytest.raises(sqlite3.OperationalError):
        await store.compare_and_set_advisory("adv_1", 0, {"id": "adv_1", "version": 1})
    assert not real.in_transaction
    await store.put("things", "after", {"v": 1})
    assert await store.compare_and_set_advisory("adv_1", 0, {"id": "adv_1", "version": 1})
    store._conn = real
    await store.aclose()
    reopened = SqliteStore(tmp_path / "tephra.sqlite3", tmp_path / "blobs")
    assert await reopened.get("things", "after") == {"v": 1}
    await reopened.aclose()


async def test_concurrent_compare_and_set_has_one_winner(store: SqliteStore) -> None:
    assert await store.compare_and_set_advisory("adv_1", 0, {"id": "adv_1", "version": 1})
    results = await asyncio.gather(
        *(
            store.compare_and_set_advisory("adv_1", 1, {"id": "adv_1", "version": 2, "by": n})
            for n in range(10)
        )
    )
    assert results.count(True) == 1
    stored = await store.get(Collection.ADVISORIES, "adv_1")
    assert stored is not None
    assert stored["by"] == results.index(True)


async def test_update_applies_each_change_atomically(store: SqliteStore) -> None:
    """Twenty concurrent increments of one count: none is lost (the AI budget relies on it)."""

    def bump(stored: dict[str, Any] | None) -> dict[str, Any]:
        return {"n": (stored or {"n": 0})["n"] + 1}

    await asyncio.gather(*(store.update("counts", "2026-10-13/m", bump) for _ in range(20)))
    assert await store.get("counts", "2026-10-13/m") == {"n": 20}
    assert await store.update("counts", "2026-10-13/m", bump) == {"n": 21}


async def test_an_update_whose_change_raises_writes_nothing(store: SqliteStore) -> None:
    await store.put("counts", "c", {"n": 1})

    def refuse(_: dict[str, Any] | None) -> dict[str, Any]:
        raise LookupError("over budget")

    with pytest.raises(LookupError):
        await store.update("counts", "c", refuse)
    assert await store.get("counts", "c") == {"n": 1}
    await store.put("counts", "after", {"n": 2})  # no transaction was left open
    assert await store.get("counts", "after") == {"n": 2}


async def test_append_audit_never_overwrites(store: SqliteStore) -> None:
    first = AuditEntry(id="e1", at=AT, actor="system", action=AuditAction.DRAFT_CREATED, note="a")
    second = first.model_copy(update={"note": "b"})
    await store.append_audit(first)
    await store.append_audit(second)
    stored = await store.get(Collection.AUDIT, "e1")
    assert stored is not None
    assert stored["note"] == "a"


async def test_feed_state_round_trip(store: SqliteStore) -> None:
    vona = FeedHealth(feed=FeedId.VONA, status=FeedStatus.OK, cadence_s=300, last_success_at=AT)
    sigmet = FeedHealth(feed=FeedId.SIGMET, status=FeedStatus.ERROR, cadence_s=60)
    await store.put_feed_state(vona)
    await store.put_feed_state(sigmet)
    assert await store.get_feed_state(FeedId.VONA) == vona
    assert await store.get_feed_state(FeedId.ADSB) is None
    assert [state.feed for state in await store.list_feed_states()] == [FeedId.SIGMET, FeedId.VONA]


async def test_blobs(store: SqliteStore) -> None:
    png = b"\x89PNG\r\n\x1a\nfake"
    await store.put_blob("btd/263300_20261009T1800Z.png", png, "image/png")
    assert await store.get_blob("btd/263300_20261009T1800Z.png") == (png, "image/png")
    assert await store.get_blob("btd/missing.png") is None
    assert await store.get_blob("../etc/passwd") is None
    with pytest.raises(ValueError, match="blob key"):
        await store.put_blob("other/x.png", png, "image/png")
    with pytest.raises(ValueError, match="image/png"):
        await store.put_blob("frames/x.png", png, "image/jpeg")


async def test_documents_survive_reopening(tmp_path: Path) -> None:
    first = SqliteStore(tmp_path / "db.sqlite3", tmp_path / "blobs")
    await first.put("things", "k", {"v": 1})
    await first.aclose()
    second = SqliteStore(tmp_path / "db.sqlite3", tmp_path / "blobs")
    assert await second.get("things", "k") == {"v": 1}
    await second.aclose()


async def test_non_finite_numbers_are_stored_as_null(store: SqliteStore) -> None:
    await store.put(Collection.BTD, "BTD:263300:x", {"median_btd_k": math.nan, "n": math.inf})
    assert await store.get(Collection.BTD, "BTD:263300:x") == {"median_btd_k": None, "n": None}


def test_encode_decode_round_trip() -> None:
    doc = {"a": [1, 2.5, None], "b": {"c": "Semeru ✓"}}
    assert decode_doc(encode_doc(doc)) == doc
    with pytest.raises(ValueError, match="JSON object"):
        decode_doc("[1, 2]")


# --- Firestore helpers (no google-cloud needed) -----------------------------------------


def test_index_fields_copies_short_scalars_only() -> None:
    doc = {
        "status": "DRAFT",
        "version": 2,
        "confidence": 0.5,
        "replay": False,
        "decided_at": None,
        "raw_text": "X" * 300,
        "polygon": [[1.0, 2.0]],
        "nested": {"a": 1},
        "bad": math.nan,
        DOC_FIELD: "ignored",
    }
    assert index_fields(doc) == {
        "status": "DRAFT",
        "version": 2,
        "confidence": 0.5,
        "replay": False,
        "decided_at": None,
    }


def test_plan_query_keeps_composite_index_work_in_memory() -> None:
    no_filter = plan_query([], "created_at")
    assert no_filter.server_order
    assert no_filter.server_limit

    equality = plan_query([Where("status", "==", "DRAFT")], None)
    assert [item.field for item in equality.server] == ["status"]
    assert equality.server_limit

    ordered = plan_query([Where("status", "==", "DRAFT")], "created_at")
    assert not ordered.server_order
    assert not ordered.server_limit

    mixed = plan_query(
        [
            Where("dedupe_key", "==", "DD-1"),
            Where("n", ">", 3),
            Where("kind", "in", ["A"]),
            Where("other", "in", ["B"]),
            Where("gone", "==", None),
        ],
        None,
    )
    assert [item.field for item in mixed.server] == ["dedupe_key", "kind"]
    assert [item.field for item in mixed.memory] == ["n", "other", "gone"]
    assert not mixed.server_limit


def test_matches_in_memory() -> None:
    doc = {"n": 3, "kind": "VONA", "at": "2026-10-09T19:00:00.000Z", "gone": None}
    assert matches(doc, [Where("n", ">", 2), Where("kind", "in", ["VONA", "VAA"])])
    assert matches(doc, [Where("gone", "==", None), Where("missing", "==", None)])
    assert not matches(doc, [Where("gone", "!=", None)])
    assert not matches(doc, [Where("n", "<", "a string")])
    assert not matches(doc, [Where("missing", ">", 1)])
