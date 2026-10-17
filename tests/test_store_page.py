"""``Store.page``: ordered pages past a cursor, on SQLite and on a fake Firestore client, and
the reads each backend reports for them."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from test_store_namespace import FakeDb, fake_firestore_store

from tephra.store.base import Collection, Store, Where
from tephra.store.sqlite_store import SqliteStore


class Ops:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def __call__(self, kind: str, n: int) -> None:
        self.counts[kind] = self.counts.get(kind, 0) + n

    def take(self) -> dict[str, int]:
        counts, self.counts = self.counts, {}
        return counts


@pytest.fixture(params=["sqlite", "firestore"])
async def backend(request: pytest.FixtureRequest, tmp_path: Path) -> AsyncIterator[Any]:
    if request.param == "sqlite":
        store: Store = SqliteStore(tmp_path / "t.sqlite3", tmp_path / "blobs")
        db = None
    else:
        root, db, _, _ = fake_firestore_store()
        store = root.sibling("RFB")
    yield store, db
    await store.aclose()


async def _seed(store: Store) -> None:
    for seq in range(1, 11):
        await store.put(Collection.AUDIT, f"e{seq:02d}", {"id": f"e{seq:02d}", "seq": seq})
    await store.put(Collection.AUDIT, "no-seq", {"id": "no-seq"})


async def test_page_newest_first_then_older_past_the_cursor(backend: Any) -> None:
    store, _ = backend
    await _seed(store)
    first = await store.page(Collection.AUDIT, field="seq", before=None, limit=4)
    assert [doc["seq"] for doc in first] == [10, 9, 8, 7]
    older = await store.page(Collection.AUDIT, field="seq", before=first[-1]["seq"], limit=4)
    assert [doc["seq"] for doc in older] == [6, 5, 4, 3]
    last = await store.page(Collection.AUDIT, field="seq", before=3, limit=4)
    assert [doc["seq"] for doc in last] == [2, 1]
    assert await store.page(Collection.AUDIT, field="seq", before=1, limit=4) == []


async def test_page_ascending_reads_only_the_tail(backend: Any) -> None:
    store, _ = backend
    await _seed(store)
    tail = await store.page(Collection.AUDIT, field="seq", before=7, limit=50, descending=False)
    assert [doc["seq"] for doc in tail] == [8, 9, 10]
    head = await store.page(Collection.AUDIT, field="seq", before=None, limit=2, descending=False)
    assert [doc["seq"] for doc in head] == [1, 2]


async def test_page_skips_documents_without_the_field_and_honours_zero(backend: Any) -> None:
    store, _ = backend
    await _seed(store)
    everything = await store.page(Collection.AUDIT, field="seq", before=None, limit=100)
    assert len(everything) == 10
    assert await store.page(Collection.AUDIT, field="seq", before=None, limit=0) == []


async def test_a_page_costs_one_read_per_document_returned(backend: Any) -> None:
    store, db = backend
    await _seed(store)
    ops = Ops()
    store.on_op = ops
    streamed_before = db.streamed if db is not None else 0
    page = await store.page(Collection.AUDIT, field="seq", before=8, limit=3)
    assert len(page) == 3
    assert ops.take() == {"reads": 3}
    if db is not None:
        assert db.streamed - streamed_before == 3  # the limit ran on the server
    assert await store.page(Collection.AUDIT, field="seq", before=1, limit=3) == []
    assert ops.take() == {"reads": 1}  # an empty query still bills one read


async def test_firestore_reads_count_every_streamed_snapshot_before_memory_filters() -> None:
    """A filter Firestore cannot run on its indexes streams every document of the
    collection, and the meter must see each one, not only those returned."""
    root, db, _, _ = fake_firestore_store()
    ops = Ops()
    root.on_op = ops
    for n in range(6):
        await root.put(Collection.PLANS, f"p{n}", {"id": f"p{n}", "n": n})
    ops.take()
    found = await root.query(Collection.PLANS, [Where("n", ">", 3)], limit=1)
    assert [doc["n"] for doc in found] == [4]
    assert isinstance(db, FakeDb)
    assert ops.take() == {"reads": 6}
    assert await root.count(Collection.PLANS) == 6
    assert ops.take() == {"reads": 1}
