"""Store namespaces: an airline's documents beside the root ones, on both backends.

Firestore runs against an in-memory fake of the client surface FirestoreStore uses (no
google-cloud packages, no emulator): the paths and the billed counts are what is checked.
"""

import sys
import types
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from tephra.config import Settings
from tephra.models import AuditAction, AuditEntry
from tephra.store import open_store, tenant_sqlite_path
from tephra.store.base import Collection, Where
from tephra.store.firestore_store import DOC_FIELD, FirestoreStore
from tephra.store.sqlite_store import SqliteStore

PNG = b"\x89PNG\r\n\x1a\nfake"

# --- a fake of the Firestore and Cloud Storage clients ----------------------------------


@dataclass(frozen=True)
class FieldFilter:
    field_path: str
    op_string: str
    value: Any


class Query:
    ASCENDING = "ASCENDING"
    DESCENDING = "DESCENDING"


class AlreadyExists(Exception):
    pass


def async_transactional(function: Callable[..., Any]) -> Callable[..., Any]:
    async def run(transaction: "FakeTransaction") -> Any:
        return await function(transaction)

    return run


FAKE_FIRESTORE = types.SimpleNamespace(
    FieldFilter=FieldFilter, Query=Query, async_transactional=async_transactional
)


@dataclass
class Snapshot:
    exists: bool
    data: dict[str, Any] | None
    reference: "FakeDocument | None" = None

    def to_dict(self) -> dict[str, Any] | None:
        return None if self.data is None else dict(self.data)


@dataclass
class FakeDb:
    docs: dict[tuple[str, ...], dict[str, Any]] = field(default_factory=dict)
    streamed: int = 0
    closed: bool = False

    def collection(self, name: str) -> "FakeCollection":
        return FakeCollection(self, (name,))

    def transaction(self) -> "FakeTransaction":
        return FakeTransaction()

    def close(self) -> None:
        self.closed = True

    def paths(self) -> list[str]:
        return sorted("/".join(path) for path in self.docs)


class FakeTransaction:
    def set(self, ref: "FakeDocument", data: dict[str, Any]) -> None:
        ref.db.docs[ref.path] = dict(data)


@dataclass
class FakeDocument:
    db: FakeDb
    path: tuple[str, ...]

    def collection(self, name: str) -> "FakeCollection":
        return FakeCollection(self.db, (*self.path, name))

    async def get(self, transaction: FakeTransaction | None = None) -> Snapshot:
        data = self.db.docs.get(self.path)
        return Snapshot(data is not None, data)

    async def set(self, data: dict[str, Any]) -> None:
        self.db.docs[self.path] = dict(data)

    async def create(self, data: dict[str, Any]) -> None:
        if self.path in self.db.docs:
            raise AlreadyExists(self.path)
        self.db.docs[self.path] = dict(data)

    async def delete(self) -> None:
        self.db.docs.pop(self.path, None)


@dataclass
class FakeCollection:
    db: FakeDb
    path: tuple[str, ...]
    filters: tuple[FieldFilter, ...] = ()
    order: tuple[str, str] | None = None
    cap: int | None = None

    def document(self, doc_id: str) -> FakeDocument:
        return FakeDocument(self.db, (*self.path, doc_id))

    def where(self, *, filter: FieldFilter) -> "FakeCollection":
        return FakeCollection(self.db, self.path, (*self.filters, filter), self.order, self.cap)

    def order_by(self, field_path: str, *, direction: str) -> "FakeCollection":
        return FakeCollection(self.db, self.path, self.filters, (field_path, direction), self.cap)

    def limit(self, count: int) -> "FakeCollection":
        return FakeCollection(self.db, self.path, self.filters, self.order, count)

    def _matching(self) -> list[tuple[tuple[str, ...], dict[str, Any]]]:
        depth = len(self.path) + 1
        docs = [
            (path, data)
            for path, data in sorted(self.db.docs.items())
            if len(path) == depth and path[:-1] == self.path
        ]
        for item in self.filters:
            docs = [(path, doc) for path, doc in docs if _passes(doc, item)]
        if self.order is not None:
            name, direction = self.order
            docs = [(path, doc) for path, doc in docs if doc.get(name) is not None]
            docs.sort(key=lambda pair: pair[1][name], reverse=direction == Query.DESCENDING)
        return docs if self.cap is None else docs[: self.cap]

    async def stream(self) -> AsyncIterator[Snapshot]:
        for path, data in self._matching():
            self.db.streamed += 1
            yield Snapshot(True, data, FakeDocument(self.db, path))

    def count(self, *, alias: str) -> "FakeCount":
        return FakeCount(len(self._matching()))


@dataclass
class FakeCount:
    n: int

    async def get(self) -> list[list[Any]]:
        return [[types.SimpleNamespace(value=self.n)]]


def _passes(doc: dict[str, Any], item: FieldFilter) -> bool:
    value = doc.get(item.field_path)
    match item.op_string:
        case "==":
            return bool(value == item.value)
        case "in":
            return value in item.value
        case "<":
            return value is not None and value < item.value
        case ">":
            return value is not None and value > item.value
    raise AssertionError(item.op_string)


@dataclass
class FakeBucket:
    blobs: dict[str, bytes] = field(default_factory=dict)

    def blob(self, key: str) -> Any:
        bucket = self

        class Blob:
            def upload_from_string(self, data: bytes, content_type: str) -> None:
                bucket.blobs[key] = data

        return Blob()

    def get_blob(self, key: str) -> Any:
        if key not in self.blobs:
            return None
        data = self.blobs[key]
        return types.SimpleNamespace(download_as_bytes=lambda: data, content_type="image/png")


@dataclass
class FakeStorage:
    closed: bool = False

    def close(self) -> None:
        self.closed = True


def fake_firestore_store() -> tuple[FirestoreStore, FakeDb, FakeBucket, FakeStorage]:
    db, bucket, storage = FakeDb(), FakeBucket(), FakeStorage()
    return FirestoreStore.from_clients(FAKE_FIRESTORE, db, storage, bucket), db, bucket, storage


@pytest.fixture
def already_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    """``append_audit`` imports google.api_core's AlreadyExists; the fake raises its own."""
    exceptions = types.ModuleType("google.api_core.exceptions")
    exceptions.AlreadyExists = AlreadyExists  # type: ignore[attr-defined]
    api_core = types.ModuleType("google.api_core")
    api_core.exceptions = exceptions  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google.api_core", api_core)
    monkeypatch.setitem(sys.modules, "google.api_core.exceptions", exceptions)


# --- Firestore ----------------------------------------------------------------------------


async def test_firestore_sibling_writes_under_tenants_and_leaves_the_root_alone(
    already_exists: None,
) -> None:
    root, db, _, _ = fake_firestore_store()
    airline = root.sibling("RFB")
    await root.put(Collection.ADVISORIES, "adv_root", {"id": "adv_root", "version": 1})
    await airline.put(Collection.ADVISORIES, "adv_1", {"id": "adv_1", "version": 1})
    assert await airline.compare_and_set_advisory("adv_2", 0, {"id": "adv_2", "version": 1})
    await airline.update(Collection.RUNTIME, "state", lambda _: {"mode": "LIVE"})
    await airline.append_audit(
        AuditEntry(
            id="e1", at="2026-10-17T14:02:00Z", actor="system", action=AuditAction.HOSTED_SETUP
        )
    )
    assert db.paths() == [
        "advisories/adv_root",
        "tenants/RFB/advisories/adv_1",
        "tenants/RFB/advisories/adv_2",
        "tenants/RFB/audit/e1",
        "tenants/RFB/runtime/state",
    ]
    assert await airline.get(Collection.ADVISORIES, "adv_root") is None
    assert [doc["id"] for doc in await root.list_docs(Collection.ADVISORIES)] == ["adv_root"]
    assert [doc["id"] for doc in await airline.query(Collection.ADVISORIES)] == ["adv_1", "adv_2"]
    assert await airline.count(Collection.ADVISORIES, [Where("version", "==", 1)]) == 2
    await airline.delete(Collection.ADVISORIES, "adv_1")
    assert "tenants/RFB/advisories/adv_1" not in db.paths()
    assert "advisories/adv_root" in db.paths()


async def test_firestore_doc_ids_are_escaped_inside_a_namespace() -> None:
    root, db, _, _ = fake_firestore_store()
    await root.sibling("RFB").put(Collection.VAAS, "VAA:DARWIN:2026/1157", {"v": 1})
    assert db.paths() == ["tenants/RFB/vaas/VAA:DARWIN:2026%2F1157"]
    assert DOC_FIELD in db.docs[("tenants", "RFB", "vaas", "VAA:DARWIN:2026%2F1157")]


async def test_firestore_delete_some_purges_only_the_airlines_namespace() -> None:
    root, db, _, _ = fake_firestore_store()
    airline = root.sibling("RFB")
    counted: list[tuple[str, int]] = []
    airline.on_op = lambda kind, n: counted.append((kind, n))
    await root.put(Collection.ADVISORIES, "adv_root", {"id": "adv_root"})
    for n in range(3):
        await airline.put(Collection.ADVISORIES, f"adv_{n}", {"id": f"adv_{n}"})
    counted.clear()
    assert await airline.delete_some(Collection.ADVISORIES, limit=2) == 2
    assert counted == [("reads", 2), ("deletes", 1), ("deletes", 1)]
    assert await airline.delete_some(Collection.ADVISORIES, limit=5) == 1
    assert await airline.delete_some(Collection.ADVISORIES, limit=5) == 0
    assert db.paths() == ["advisories/adv_root"]


async def test_firestore_blobs_are_shared_and_a_sibling_closes_nothing() -> None:
    root, db, bucket, storage = fake_firestore_store()
    airline = root.sibling("RFB")
    await airline.put_blob("frames/x.png", PNG, "image/png")
    assert bucket.blobs == {"frames/x.png": PNG}
    assert await root.get_blob("frames/x.png") == (PNG, "image/png")
    await airline.aclose()
    assert not db.closed
    assert not storage.closed
    await root.aclose()
    assert db.closed
    assert storage.closed


def test_open_store_gives_a_firestore_sibling_on_the_shared_clients() -> None:
    root, _, _, _ = fake_firestore_store()
    settings = Settings(
        _env_file=None, store="firestore", gcp_project="tephra-test", gcs_bucket="tephra-test"
    )
    airline = open_store(settings, namespace="RFB", shared=root)
    assert isinstance(airline, FirestoreStore)
    assert airline is not root
    assert airline._db is root._db
    assert airline._namespace == "RFB"


# --- SQLite -------------------------------------------------------------------------------


def test_tenant_sqlite_file_sits_beside_the_root_file(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None, sqlite_path=tmp_path / "state" / "tephra.sqlite3", cache_dir=tmp_path
    )
    assert tenant_sqlite_path(settings, "RFB") == tmp_path / "state" / "tenants" / "RFB.sqlite3"
    with pytest.raises(ValueError, match="ICAO"):
        tenant_sqlite_path(settings, "rfb")


async def test_sqlite_namespaces_are_separate_files_with_shared_blobs(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None, sqlite_path=tmp_path / "tephra.sqlite3", cache_dir=tmp_path / "cache"
    )
    root = open_store(settings)
    airline = open_store(settings, namespace="RFB")
    other = open_store(settings, namespace="RFC")
    assert isinstance(airline, SqliteStore)
    try:
        await root.put(Collection.ADVISORIES, "a", {"id": "a"})
        await airline.put(Collection.ADVISORIES, "b", {"id": "b"})
        assert await root.get(Collection.ADVISORIES, "b") is None
        assert await other.get(Collection.ADVISORIES, "b") is None
        assert await airline.get(Collection.ADVISORIES, "b") == {"id": "b"}
        assert (tmp_path / "tenants" / "RFB.sqlite3").exists()
        await airline.put_blob("frames/x.png", PNG, "image/png")
        assert await root.get_blob("frames/x.png") == (PNG, "image/png")
        assert (tmp_path / "cache" / "blobs" / "frames" / "x.png").exists()
    finally:
        for store in (root, airline, other):
            await store.aclose()


async def test_sqlite_delete_some_purges_one_collection_of_one_airline(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None, sqlite_path=tmp_path / "tephra.sqlite3", cache_dir=tmp_path / "cache"
    )
    root = open_store(settings)
    airline = open_store(settings, namespace="RFB")
    counted: list[tuple[str, int]] = []
    try:
        await root.put(Collection.ADVISORIES, "a", {"id": "a"})
        for n in range(3):
            await airline.put(Collection.ADVISORIES, f"b{n}", {"id": f"b{n}"})
        await airline.put(Collection.OUTBOUND, "m", {"id": "m"})
        airline.on_op = lambda kind, n: counted.append((kind, n))  # type: ignore[attr-defined]
        assert await airline.delete_some(Collection.ADVISORIES, limit=2) == 2
        assert counted == [("reads", 2), ("deletes", 2)]
        assert await airline.delete_some(Collection.ADVISORIES, limit=500) == 1
        assert await airline.query(Collection.ADVISORIES) == []
        assert await airline.get(Collection.OUTBOUND, "m") == {"id": "m"}
        assert await root.get(Collection.ADVISORIES, "a") == {"id": "a"}
    finally:
        for store in (root, airline):
            await store.aclose()


@pytest.mark.parametrize("namespace", ["rfb", "RFBX", "../x", "demo", ""])
def test_open_store_refuses_a_namespace_that_is_not_an_icao(tmp_path: Path, namespace: str) -> None:
    settings = Settings(_env_file=None, sqlite_path=tmp_path / "t.sqlite3")
    with pytest.raises(ValueError, match="ICAO"):
        open_store(settings, namespace=namespace)


def test_open_store_without_a_namespace_is_unchanged(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, sqlite_path=tmp_path / "t.sqlite3", cache_dir=tmp_path)
    store = open_store(settings)
    assert isinstance(store, SqliteStore)
    assert store._path == tmp_path / "t.sqlite3"
    assert store._blob_dir == tmp_path / "blobs"
    assert store.on_op is None
