"""SQLite document store for local runs: one JSON table, blobs as files on disk.

The stdlib ``sqlite3`` driver is synchronous, so every call runs in a worker thread
(``asyncio.to_thread``) on one shared connection guarded by a lock. Filters and ordering
are pushed into SQL with ``json_extract``; field paths and values are always bound as
parameters, never formatted into the statement.
"""

import asyncio
import mimetypes
import re
import sqlite3
import threading
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Final

from tephra.models import AuditEntry, FeedHealth, FeedId
from tephra.store import check_blob_key, check_cas_doc, decode_doc, encode_doc
from tephra.store.base import Collection, Store, Where
from tephra.util import timeutil

__all__ = ["SqliteStore"]

_SCHEMA: Final = (
    "CREATE TABLE IF NOT EXISTS docs ("
    "collection TEXT NOT NULL, id TEXT NOT NULL, doc TEXT NOT NULL, "
    "PRIMARY KEY (collection, id)) WITHOUT ROWID"
)
_FIELD: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
_SQL_OPS: Final[dict[str, str]] = {
    "==": "=",
    "!=": "!=",
    "<": "<",
    "<=": "<=",
    ">": ">",
    ">=": ">=",
}
_MAX_DOC_ID: Final = 500


class SqliteStore(Store):
    def __init__(self, path: Path, blob_dir: Path) -> None:
        self._path = path
        self._blob_dir = blob_dir
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    # --- documents ----------------------------------------------------------------------

    async def put(self, collection: str, doc_id: str, doc: Mapping[str, Any]) -> None:
        text = encode_doc(doc)
        await self._run(
            lambda conn: conn.execute(
                "INSERT OR REPLACE INTO docs (collection, id, doc) VALUES (?, ?, ?)",
                (str(collection), _doc_id(doc_id), text),
            )
        )

    async def get(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        row = await self._run(
            lambda conn: conn.execute(
                "SELECT doc FROM docs WHERE collection = ? AND id = ?",
                (str(collection), _doc_id(doc_id)),
            ).fetchone()
        )
        return None if row is None else decode_doc(row[0])

    async def delete(self, collection: str, doc_id: str) -> None:
        await self._run(
            lambda conn: conn.execute(
                "DELETE FROM docs WHERE collection = ? AND id = ?",
                (str(collection), _doc_id(doc_id)),
            )
        )

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
        statement = _select(str(collection), where, order_by, descending, limit)
        if statement is None:
            return []
        sql, params = statement
        rows = await self._run(lambda conn: conn.execute(sql, params).fetchall())
        return [decode_doc(row[0]) for row in rows]

    async def count(self, collection: str, where: Sequence[Where] = ()) -> int:
        clauses = _where(str(collection), where)
        if clauses is None:
            return 0
        sql, params = clauses
        row = await self._run(
            lambda conn: conn.execute(f"SELECT COUNT(*) FROM docs WHERE {sql}", params).fetchone()
        )
        return int(row[0])

    async def update(
        self,
        collection: str,
        doc_id: str,
        change: Callable[[dict[str, Any] | None], dict[str, Any]],
    ) -> dict[str, Any]:
        key = _doc_id(doc_id)

        def apply(conn: sqlite3.Connection) -> dict[str, Any]:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT doc FROM docs WHERE collection = ? AND id = ?",
                    (str(collection), key),
                ).fetchone()
                text = encode_doc(change(None if row is None else decode_doc(row[0])))
                conn.execute(
                    "INSERT OR REPLACE INTO docs (collection, id, doc) VALUES (?, ?, ?)",
                    (str(collection), key, text),
                )
                conn.execute("COMMIT")
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            return decode_doc(text)

        return await self._run(apply)

    async def compare_and_set_advisory(
        self, advisory_id: str, expected_version: int, doc: Mapping[str, Any]
    ) -> bool:
        check_cas_doc(expected_version, doc)
        key = _doc_id(advisory_id)
        text = encode_doc(doc)

        def swap(conn: sqlite3.Connection) -> bool:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT doc FROM docs WHERE collection = ? AND id = ?",
                    (Collection.ADVISORIES.value, key),
                ).fetchone()
                stored = None if row is None else decode_doc(row[0]).get("version")
                matches = stored is None if expected_version == 0 else stored == expected_version
                if matches:
                    conn.execute(
                        "INSERT OR REPLACE INTO docs (collection, id, doc) VALUES (?, ?, ?)",
                        (Collection.ADVISORIES.value, key, text),
                    )
                # A failed COMMIT leaves the transaction open; every later write would join
                # it and never be committed, so it must be rolled back below as well.
                conn.execute("COMMIT")
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            return matches

        return await self._run(swap)

    async def append_audit(self, entry: AuditEntry) -> None:
        text = encode_doc(entry.model_dump(mode="json"))
        await self._run(
            lambda conn: conn.execute(
                "INSERT OR IGNORE INTO docs (collection, id, doc) VALUES (?, ?, ?)",
                (Collection.AUDIT.value, _doc_id(entry.id), text),
            )
        )

    # --- feed health --------------------------------------------------------------------

    async def get_feed_state(self, feed: FeedId) -> FeedHealth | None:
        doc = await self.get(Collection.FEED_STATE, feed.value)
        return None if doc is None else FeedHealth.model_validate(doc)

    async def put_feed_state(self, state: FeedHealth) -> None:
        await self.put(Collection.FEED_STATE, state.feed.value, state.model_dump(mode="json"))

    async def list_feed_states(self) -> list[FeedHealth]:
        docs = await self.list_docs(Collection.FEED_STATE, limit=len(FeedId) * 2)
        states = [FeedHealth.model_validate(doc) for doc in docs]
        order = list(FeedId)
        return sorted(states, key=lambda state: order.index(state.feed))

    # --- blobs --------------------------------------------------------------------------

    async def put_blob(self, key: str, data: bytes, content_type: str) -> None:
        check_blob_key(key)
        expected = _content_type(key)
        if content_type != expected:
            raise ValueError(f"blob {key!r} must be {expected}, got {content_type}")
        await asyncio.to_thread(self._write_blob, key, data)

    async def get_blob(self, key: str) -> tuple[bytes, str] | None:
        try:
            check_blob_key(key)
        except ValueError:
            return None
        path = self._blob_dir / key
        try:
            data = await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError:
            return None
        return data, _content_type(key)

    async def aclose(self) -> None:
        await asyncio.to_thread(self._close)

    # --- internals ----------------------------------------------------------------------

    async def _run[T](self, operation: Callable[[sqlite3.Connection], T]) -> T:
        return await asyncio.to_thread(self._call, operation)

    def _call[T](self, operation: Callable[[sqlite3.Connection], T]) -> T:
        with self._lock:
            return operation(self._connection())

    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self._path, check_same_thread=False, isolation_level=None)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute(_SCHEMA)
            self._conn = conn
        return self._conn

    def _close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def _write_blob(self, key: str, data: bytes) -> None:
        target = self._blob_dir / key
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.tmp")
        temporary.write_bytes(data)
        temporary.replace(target)


def _select(
    collection: str,
    where: Sequence[Where],
    order_by: str | None,
    descending: bool,
    limit: int,
) -> tuple[str, list[Any]] | None:
    """SQL and parameters for a query, or None when it cannot match (an empty ``in``)."""
    clauses = _where(collection, where)
    if clauses is None:
        return None
    sql, params = clauses
    direction = "DESC" if descending else "ASC"
    sql = f"SELECT doc FROM docs WHERE {sql}"
    if order_by is not None:
        sql += f" ORDER BY json_extract(doc, ?) {direction}, id {direction}"
        params.append(_json_path(order_by))
    else:
        sql += f" ORDER BY id {direction}"
    sql += " LIMIT ?"
    params.append(max(0, limit))
    return sql, params


def _where(collection: str, where: Sequence[Where]) -> tuple[str, list[Any]] | None:
    """The WHERE clause and its parameters, or None when it cannot match (an empty ``in``)."""
    clauses = ["collection = ?"]
    params: list[Any] = [collection]
    for item in where:
        path = _json_path(item.field)
        if item.op == "in":
            values = [_sql_value(value) for value in item.value]
            if not values:
                return None
            placeholders = ", ".join("?" for _ in values)
            clauses.append(f"json_extract(doc, ?) IN ({placeholders})")
            params.extend([path, *values])
        elif item.value is None and item.op in ("==", "!="):
            clauses.append(f"json_extract(doc, ?) IS {'NOT ' if item.op == '!=' else ''}NULL")
            params.append(path)
        else:
            clauses.append(f"json_extract(doc, ?) {_SQL_OPS[item.op]} ?")
            params.extend([path, _sql_value(item.value)])
    return " AND ".join(clauses), params


def _json_path(field: str) -> str:
    if _FIELD.fullmatch(field) is None:
        raise ValueError(f"unsupported field name {field!r}")
    return f"$.{field}"


def _sql_value(value: Any) -> Any:
    """Bind values the way they were stored by ``model_dump(mode="json")``."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return timeutil.to_iso(value)
    if isinstance(value, bool | int | float | str) or value is None:
        return value
    raise TypeError(f"cannot filter on a {type(value).__name__}")


def _doc_id(doc_id: str) -> str:
    if not doc_id or len(doc_id) > _MAX_DOC_ID:
        raise ValueError("document ids must be 1 to 500 characters")
    return doc_id


def _content_type(key: str) -> str:
    return mimetypes.guess_type(key)[0] or "application/octet-stream"
