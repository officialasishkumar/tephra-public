"""Firestore (documents) and Cloud Storage (blobs) for the Cloud Run deployment.

Runs only inside Cloud Run, where the clients authenticate as the service's runtime
service account; it is never used for Gemini. ``google-cloud-firestore`` and
``google-cloud-storage`` come from the ``[gcp]`` extra and are imported when the store is
constructed, so this module imports without them.

Firestore rejects nested arrays, and TEPHRA documents are full of them (GeoJSON rings,
flight paths). Each document is therefore stored as its JSON text in one field, next to
copies of its short top-level scalar fields, which are what queries filter and sort on.

A hosted airline's documents live under ``tenants/<ICAO>/<collection>`` (a :meth:`sibling`
on the same clients); the root collections are the demo's and the site's. ``on_op(kind, n)``
hears what Firestore bills: a read per snapshot streamed (before any filter or limit applied
in memory, at least one per query), a read per 1,000 entries of a count aggregation, a read
for each transaction attempt of an update or compare-and-set and a write when it commits.
"""

import asyncio
import inspect
import math
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from enum import Enum
from typing import Any, Final, NamedTuple

from tephra.models import AuditEntry, FeedHealth, FeedId
from tephra.store import (
    OpHook,
    billed_count_reads,
    billed_reads,
    check_blob_key,
    check_cas_doc,
    decode_doc,
    encode_doc,
)
from tephra.store.base import Collection, Store, Where, escape_doc_id
from tephra.util import timeutil

__all__ = ["DOC_FIELD", "FirestoreStore", "QueryPlan", "index_fields", "matches", "plan_query"]

DOC_FIELD: Final = "tephra_doc"
MAX_INDEXED_STRING: Final = 256
"""Longer strings (raw feed texts, advisory bodies) are never filtered on, so not copied."""
MAX_IN_VALUES: Final = 30
INDEXED_ONLY: Final[Mapping[str, frozenset[str]]] = {
    Collection.AI_ANSWERS: frozenset({"expires_at"}),
    Collection.AIRLINES: frozenset({"status", "submitted_at"}),
    Collection.AIRLINE_LOGINS: frozenset(),
    Collection.HOSTED_MEMBERS: frozenset({"icao", "login_key"}),
    Collection.HOSTED_INVITES: frozenset({"icao", "expires_at"}),
    Collection.HOSTED_TENANTS: frozenset({"state"}),
    Collection.HOSTED_SLOTS: frozenset(),
    Collection.HOSTED_METER: frozenset(),
    Collection.OPERATORS: frozenset(),
    Collection.OPERATOR_INVITES: frozenset(),
}
"""Collections read by key and queried on a few fields only: just those fields are copied
beside the JSON text (Firestore indexes every copied field on every write)."""


class QueryPlan(NamedTuple):
    """How a query splits between Firestore and memory.

    Equality filters go to the server, which answers them from automatic single-field
    indexes. Inequalities, ordering combined with filters, and null comparisons run in
    memory, so TEPHRA never depends on a composite index that someone must create by hand.
    """

    server: list[Where]
    memory: list[Where]
    server_order: bool
    server_limit: bool


def plan_query(where: Sequence[Where], order_by: str | None) -> QueryPlan:
    server: list[Where] = []
    memory: list[Where] = []
    has_in = False
    for item in where:
        pushable = item.op == "==" and item.value is not None
        if item.op == "in" and not has_in and 0 < len(item.value) <= MAX_IN_VALUES:
            pushable = has_in = True
        (server if pushable else memory).append(item)
    server_order = order_by is not None and not where
    server_limit = not memory and (order_by is None or server_order)
    return QueryPlan(server, memory, server_order, server_limit)


def index_fields(doc: Mapping[str, Any], collection: str | None = None) -> dict[str, Any]:
    """Top-level scalar fields copied beside the JSON text so Firestore can query them (for a
    collection in :data:`INDEXED_ONLY`, only its fields)."""
    only = INDEXED_ONLY.get(collection) if collection is not None else None
    fields: dict[str, Any] = {}
    for key, value in doc.items():
        if key == DOC_FIELD or (only is not None and key not in only):
            continue
        if isinstance(value, str) and len(value) > MAX_INDEXED_STRING:
            continue
        if isinstance(value, float) and not math.isfinite(value):
            continue
        if value is None or isinstance(value, bool | int | float | str):
            fields[key] = value
    return fields


def matches(doc: Mapping[str, Any], where: Sequence[Where]) -> bool:
    return all(_matches_one(doc.get(item.field), item.op, _plain(item.value)) for item in where)


TENANTS_ROOT: Final = "tenants"
"""Root collection holding one document per hosted airline, each with its own collections."""


class FirestoreStore(Store):
    # Class defaults keep a store built without __init__ (test fakes) a root store, unmetered.
    _namespace: str | None = None
    _owns_clients: bool = True
    on_op: OpHook | None = None

    def __init__(
        self,
        project: str,
        database: str,
        bucket: str,
        *,
        namespace: str | None = None,
        on_op: OpHook | None = None,
    ) -> None:
        from google.cloud import firestore, storage

        client = storage.Client(project=project)
        self._attach(
            firestore,
            firestore.AsyncClient(project=project, database=database),
            client,
            client.bucket(bucket),
            namespace=namespace,
            owns_clients=True,
        )
        self.on_op = on_op

    @classmethod
    def from_clients(
        cls,
        firestore: Any,
        db: Any,
        storage: Any,
        bucket: Any,
        *,
        namespace: str | None = None,
        owns_clients: bool = True,
    ) -> "FirestoreStore":
        """A store on clients made elsewhere (``sibling``, and fakes in tests)."""
        store = cls.__new__(cls)
        store._attach(
            firestore, db, storage, bucket, namespace=namespace, owns_clients=owns_clients
        )
        store.on_op = None
        return store

    def _attach(
        self,
        firestore: Any,
        db: Any,
        storage: Any,
        bucket: Any,
        *,
        namespace: str | None,
        owns_clients: bool,
    ) -> None:
        self._firestore: Any = firestore
        self._db: Any = db
        self._storage: Any = storage
        self._bucket: Any = bucket
        self._namespace = namespace
        self._owns_clients = owns_clients

    def sibling(self, namespace: str) -> "FirestoreStore":
        """The airline ``namespace``'s store on this store's clients and bucket. Closing it
        closes nothing: the clients belong to the root store."""
        return FirestoreStore.from_clients(
            self._firestore,
            self._db,
            self._storage,
            self._bucket,
            namespace=namespace,
            owns_clients=False,
        )

    # --- documents ----------------------------------------------------------------------

    async def put(self, collection: str, doc_id: str, doc: Mapping[str, Any]) -> None:
        await self._ref(collection, doc_id).set(_payload(doc, collection))
        self._count("writes", 1)

    async def get(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        snapshot = await self._ref(collection, doc_id).get()
        self._count("reads", 1)
        return _decode(snapshot)

    async def delete(self, collection: str, doc_id: str) -> None:
        await self._ref(collection, doc_id).delete()
        self._count("deletes", 1)

    async def list_docs(
        self,
        collection: str,
        *,
        limit: int = 100,
        order_by: str | None = None,
        descending: bool = True,
    ) -> list[dict[str, Any]]:
        return await self.query(
            collection, (), order_by=order_by, descending=descending, limit=limit
        )

    async def query(
        self,
        collection: str,
        where: Sequence[Where] = (),
        *,
        order_by: str | None = None,
        descending: bool = True,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        plan = plan_query(where, order_by)
        query = self._collection(collection)
        filter_type = self._firestore.FieldFilter
        for item in plan.server:
            value = [_plain(v) for v in item.value] if item.op == "in" else _plain(item.value)
            query = query.where(filter=filter_type(item.field, item.op, value))
        if plan.server_order and order_by is not None:
            directions = self._firestore.Query
            direction = directions.DESCENDING if descending else directions.ASCENDING
            query = query.order_by(order_by, direction=direction)
        if plan.server_limit:
            query = query.limit(max(0, limit))
        snapshots = [snapshot async for snapshot in query.stream()]
        self._count("reads", billed_reads(len(snapshots)))
        docs = [doc for snapshot in snapshots if (doc := _decode(snapshot)) is not None]
        docs = [doc for doc in docs if matches(doc, plan.memory)]
        if order_by is not None and not plan.server_order:
            docs.sort(key=lambda doc: _sort_key(doc.get(order_by), descending), reverse=descending)
        return docs[: max(0, limit)]

    async def page(
        self,
        collection: str,
        *,
        field: str,
        before: Any | None,
        limit: int,
        descending: bool = True,
    ) -> list[dict[str, Any]]:
        """``where field < before order by field desc limit n`` (or ascending past ``before``):
        one automatic single-field index serves it, and the limit runs on the server."""
        directions = self._firestore.Query
        query = self._collection(collection)
        if before is not None:
            cursor = self._firestore.FieldFilter(field, "<" if descending else ">", _plain(before))
            query = query.where(filter=cursor)
        query = query.order_by(
            field, direction=directions.DESCENDING if descending else directions.ASCENDING
        ).limit(max(0, limit))
        snapshots = [snapshot async for snapshot in query.stream()]
        self._count("reads", billed_reads(len(snapshots)))
        return [doc for snapshot in snapshots if (doc := _decode(snapshot)) is not None]

    async def count(self, collection: str, where: Sequence[Where] = ()) -> int:
        """A count aggregation (one read per 1,000 matches) when every filter runs on the
        server; otherwise the documents are read and counted."""
        plan = plan_query(where, None)
        if plan.memory:
            return len(await self.query(collection, where, limit=2**31 - 1))
        query = self._collection(collection)
        filter_type = self._firestore.FieldFilter
        for item in plan.server:
            value = [_plain(v) for v in item.value] if item.op == "in" else _plain(item.value)
            query = query.where(filter=filter_type(item.field, item.op, value))
        results = await query.count(alias="n").get()
        total = int(results[0][0].value)
        self._count("reads", billed_count_reads(total))
        return total

    async def delete_some(self, collection: str, *, limit: int) -> int:
        """Stream up to ``limit`` documents (``limit`` runs on the server) and delete each by
        its reference: one read and one delete per document."""
        query = self._collection(collection).limit(max(0, limit))
        snapshots = [snapshot async for snapshot in query.stream()]
        self._count("reads", billed_reads(len(snapshots)))
        for snapshot in snapshots:
            await snapshot.reference.delete()
            self._count("deletes", 1)
        return len(snapshots)

    async def update(
        self,
        collection: str,
        doc_id: str,
        change: Callable[[dict[str, Any] | None], dict[str, Any]],
    ) -> dict[str, Any]:
        ref = self._ref(collection, doc_id)

        @self._firestore.async_transactional
        async def apply(transaction: Any) -> dict[str, Any]:
            snapshot = await ref.get(transaction=transaction)
            self._count("reads", 1)
            text = encode_doc(change(_decode(snapshot)))
            doc = decode_doc(text)
            transaction.set(ref, {**index_fields(doc, collection), DOC_FIELD: text})
            return doc

        result: dict[str, Any] = await apply(self._db.transaction())
        self._count("writes", 1)
        return result

    async def compare_and_set_advisory(
        self, advisory_id: str, expected_version: int, doc: Mapping[str, Any]
    ) -> bool:
        check_cas_doc(expected_version, doc)
        ref = self._ref(Collection.ADVISORIES, advisory_id)
        payload = _payload(doc, Collection.ADVISORIES)

        @self._firestore.async_transactional
        async def swap(transaction: Any) -> bool:
            snapshot = await ref.get(transaction=transaction)
            self._count("reads", 1)
            stored = _decode(snapshot)
            current = None if stored is None else stored.get("version")
            ok = current is None if expected_version == 0 else current == expected_version
            if ok:
                transaction.set(ref, payload)
            return ok

        swapped = bool(await swap(self._db.transaction()))
        if swapped:
            self._count("writes", 1)
        return swapped

    async def append_audit(self, entry: AuditEntry) -> None:
        from google.api_core.exceptions import AlreadyExists

        ref = self._ref(Collection.AUDIT, entry.id)
        try:
            await ref.create(_payload(entry.model_dump(mode="json"), Collection.AUDIT))
        except AlreadyExists:
            return
        self._count("writes", 1)

    # --- feed health --------------------------------------------------------------------

    async def get_feed_state(self, feed: FeedId) -> FeedHealth | None:
        doc = await self.get(Collection.FEED_STATE, feed.value)
        return None if doc is None else FeedHealth.model_validate(doc)

    async def put_feed_state(self, state: FeedHealth) -> None:
        await self.put(Collection.FEED_STATE, state.feed.value, state.model_dump(mode="json"))

    async def list_feed_states(self) -> list[FeedHealth]:
        docs = await self.list_docs(Collection.FEED_STATE, limit=len(FeedId) * 2)
        order = list(FeedId)
        states = [FeedHealth.model_validate(doc) for doc in docs]
        return sorted(states, key=lambda state: order.index(state.feed))

    # --- blobs --------------------------------------------------------------------------

    async def put_blob(self, key: str, data: bytes, content_type: str) -> None:
        check_blob_key(key)
        blob = self._bucket.blob(key)
        await asyncio.to_thread(blob.upload_from_string, data, content_type=content_type)

    async def get_blob(self, key: str) -> tuple[bytes, str] | None:
        try:
            check_blob_key(key)
        except ValueError:
            return None
        blob = await asyncio.to_thread(self._bucket.get_blob, key)
        if blob is None:
            return None
        data = await asyncio.to_thread(blob.download_as_bytes)
        return data, blob.content_type or "application/octet-stream"

    async def aclose(self) -> None:
        if not self._owns_clients:
            return
        # Assumption: AsyncClient.close may be sync or async depending on the library
        # version; both are handled.
        closed = self._db.close()
        if inspect.isawaitable(closed):
            await closed
        await asyncio.to_thread(self._storage.close)

    def _collection(self, collection: str) -> Any:
        if self._namespace is None:
            return self._db.collection(str(collection))
        tenant = self._db.collection(TENANTS_ROOT).document(self._namespace)
        return tenant.collection(str(collection))

    def _ref(self, collection: str, doc_id: str) -> Any:
        return self._collection(collection).document(escape_doc_id(doc_id))

    def _count(self, kind: str, n: int) -> None:
        if self.on_op is not None and n > 0:
            self.on_op(kind, n)


def _payload(doc: Mapping[str, Any], collection: str) -> dict[str, Any]:
    text = encode_doc(doc)
    return {**index_fields(decode_doc(text), collection), DOC_FIELD: text}


def _decode(snapshot: Any) -> dict[str, Any] | None:
    if not snapshot.exists:
        return None
    data = snapshot.to_dict() or {}
    text = data.get(DOC_FIELD)
    return decode_doc(text) if isinstance(text, str) else None


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return timeutil.to_iso(value)
    if isinstance(value, list | tuple | set | frozenset):
        return [_plain(item) for item in value]
    return value


def _matches_one(actual: Any, op: str, expected: Any) -> bool:
    try:
        match op:
            case "==":
                return bool(actual == expected)
            case "!=":
                return actual is not None and bool(actual != expected)
            case "in":
                return actual in expected
            case _ if actual is None or expected is None:
                return False
            case "<":
                return bool(actual < expected)
            case "<=":
                return bool(actual <= expected)
            case ">":
                return bool(actual > expected)
            case ">=":
                return bool(actual >= expected)
    except TypeError:
        return False
    raise ValueError(f"unsupported operator {op!r}")


def _sort_key(value: Any, descending: bool) -> tuple[bool, Any]:
    """Missing values sort last in either direction."""
    present = value is not None
    return (present if descending else not present), value
