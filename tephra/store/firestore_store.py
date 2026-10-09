"""Firestore (documents) and Cloud Storage (blobs) for the Cloud Run deployment.

Runs only inside Cloud Run, where the clients authenticate as the service's runtime
service account; it is never used for Gemini. ``google-cloud-firestore`` and
``google-cloud-storage`` come from the ``[gcp]`` extra and are imported when the store is
constructed, so this module imports without them.

Firestore rejects nested arrays, and TEPHRA documents are full of them (GeoJSON rings,
flight paths). Each document is therefore stored as its JSON text in one field, next to
copies of its short top-level scalar fields, which are what queries filter and sort on.
"""

import asyncio
import inspect
import math
from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import Enum
from typing import Any, Final, NamedTuple

from tephra.models import AuditEntry, FeedHealth, FeedId
from tephra.store import check_blob_key, check_cas_doc, decode_doc, encode_doc
from tephra.store.base import Collection, Store, Where, escape_doc_id
from tephra.util import timeutil

__all__ = ["DOC_FIELD", "FirestoreStore", "QueryPlan", "index_fields", "matches", "plan_query"]

DOC_FIELD: Final = "tephra_doc"
MAX_INDEXED_STRING: Final = 256
"""Longer strings (raw feed texts, advisory bodies) are never filtered on, so not copied."""
MAX_IN_VALUES: Final = 30


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


def index_fields(doc: Mapping[str, Any]) -> dict[str, Any]:
    """Top-level scalar fields copied beside the JSON text so Firestore can query them."""
    fields: dict[str, Any] = {}
    for key, value in doc.items():
        if key == DOC_FIELD:
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


class FirestoreStore(Store):
    def __init__(self, project: str, database: str, bucket: str) -> None:
        from google.cloud import firestore, storage

        self._firestore: Any = firestore
        self._db: Any = firestore.AsyncClient(project=project, database=database)
        self._storage: Any = storage.Client(project=project)
        self._bucket: Any = self._storage.bucket(bucket)

    # --- documents ----------------------------------------------------------------------

    async def put(self, collection: str, doc_id: str, doc: Mapping[str, Any]) -> None:
        await self._ref(collection, doc_id).set(_payload(doc))

    async def get(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        snapshot = await self._ref(collection, doc_id).get()
        return _decode(snapshot)

    async def delete(self, collection: str, doc_id: str) -> None:
        await self._ref(collection, doc_id).delete()

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
        query = self._db.collection(str(collection))
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
        docs = [doc async for snapshot in query.stream() if (doc := _decode(snapshot)) is not None]
        docs = [doc for doc in docs if matches(doc, plan.memory)]
        if order_by is not None and not plan.server_order:
            docs.sort(key=lambda doc: _sort_key(doc.get(order_by), descending), reverse=descending)
        return docs[: max(0, limit)]

    async def compare_and_set_advisory(
        self, advisory_id: str, expected_version: int, doc: Mapping[str, Any]
    ) -> bool:
        check_cas_doc(expected_version, doc)
        ref = self._ref(Collection.ADVISORIES, advisory_id)
        payload = _payload(doc)

        @self._firestore.async_transactional
        async def swap(transaction: Any) -> bool:
            snapshot = await ref.get(transaction=transaction)
            stored = _decode(snapshot)
            current = None if stored is None else stored.get("version")
            ok = current is None if expected_version == 0 else current == expected_version
            if ok:
                transaction.set(ref, payload)
            return ok

        return bool(await swap(self._db.transaction()))

    async def append_audit(self, entry: AuditEntry) -> None:
        from google.api_core.exceptions import AlreadyExists

        ref = self._ref(Collection.AUDIT, entry.id)
        try:
            await ref.create(_payload(entry.model_dump(mode="json")))
        except AlreadyExists:
            return

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
        # Assumption: AsyncClient.close may be sync or async depending on the library
        # version; both are handled.
        closed = self._db.close()
        if inspect.isawaitable(closed):
            await closed
        await asyncio.to_thread(self._storage.close)

    def _ref(self, collection: str, doc_id: str) -> Any:
        return self._db.collection(str(collection)).document(escape_doc_id(doc_id))


def _payload(doc: Mapping[str, Any]) -> dict[str, Any]:
    text = encode_doc(doc)
    return {**index_fields(decode_doc(text)), DOC_FIELD: text}


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
