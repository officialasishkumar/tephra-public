"""Append-only audit trail, hash-chained so that an edited or deleted entry shows.

Each entry carries a sequence number, the SHA-256 of the entry before it and its own
SHA-256 over everything else it holds. Rewriting any stored entry breaks its own hash;
deleting one breaks the next entry's link. :func:`verify_chain` checks both.

Entries are chained in one process (Cloud Run runs one instance), so a per-store lock is
enough to keep two coroutines from linking to the same predecessor.
"""

import asyncio
import weakref
from collections.abc import Mapping, Sequence
from typing import Any, Final
from uuid import uuid4

from pydantic import Field, ValidationError
from pydantic_core import to_jsonable_python

from tephra.models import AuditAction, AuditEntry
from tephra.store.base import Collection, Store, Where
from tephra.util import timeutil
from tephra.util.hashing import sha256_json

__all__ = [
    "GENESIS_SHA256",
    "ChainedAuditEntry",
    "entry_digest",
    "list_entries",
    "record",
    "verify_chain",
]

GENESIS_SHA256: Final = "0" * 64
_locks: "weakref.WeakKeyDictionary[Store, asyncio.Lock]" = weakref.WeakKeyDictionary()


class ChainedAuditEntry(AuditEntry):
    """An :class:`AuditEntry` with its place in the hash chain."""

    seq: int = Field(ge=1, description="1 for the first entry, then +1 per entry")
    prev_sha256: str = Field(description="sha256 of the previous entry; zeros for the first")
    sha256: str = Field(description="sha256 of this entry's other fields (canonical JSON)")


def entry_digest(entry: ChainedAuditEntry) -> str:
    return sha256_json(entry.model_dump(mode="json", exclude={"sha256"}))


async def record(
    store: Store,
    *,
    actor: str,
    action: AuditAction,
    advisory_id: str | None = None,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    input_hashes: Sequence[str] = (),
    model_id: str | None = None,
    prompt_hash: str | None = None,
    note: str | None = None,
) -> AuditEntry:
    async with _lock(store):
        previous = await _last_entry(store)
        unsigned = ChainedAuditEntry(
            id=uuid4().hex,
            at=timeutil.now(),
            actor=actor,
            action=action,
            advisory_id=advisory_id,
            before=_plain(before),
            after=_plain(after),
            input_hashes=list(input_hashes),
            model_id=model_id,
            prompt_hash=prompt_hash,
            note=note,
            seq=1 if previous is None else previous.seq + 1,
            prev_sha256=GENESIS_SHA256 if previous is None else previous.sha256,
            sha256="",
        )
        entry = unsigned.model_copy(update={"sha256": entry_digest(unsigned)})
        await store.append_audit(entry)
        return entry


async def list_entries(
    store: Store, *, advisory_id: str | None = None, limit: int = 100
) -> list[AuditEntry]:
    """Newest first."""
    where = [] if advisory_id is None else [Where("advisory_id", "==", advisory_id)]
    docs = await store.query(Collection.AUDIT, where, order_by="seq", descending=True, limit=limit)
    return [ChainedAuditEntry.model_validate(doc) for doc in docs]


async def verify_chain(store: Store, *, limit: int = 100_000) -> list[str]:
    """Problems found walking the chain from the first entry; empty when it is intact."""
    docs = await store.list_docs(Collection.AUDIT, limit=limit, order_by="seq", descending=False)
    problems: list[str] = []
    expected_prev = GENESIS_SHA256
    for position, doc in enumerate(docs, start=1):
        try:
            entry = ChainedAuditEntry.model_validate(doc)
        except ValidationError:
            problems.append(f"entry {doc.get('id')!r} is not a chained audit entry")
            expected_prev = ""
            continue
        if entry.seq != position:
            problems.append(f"entry {entry.id}: seq {entry.seq}, expected {position}")
        if entry.prev_sha256 != expected_prev:
            problems.append(f"entry {entry.id}: link to the previous entry is broken")
        if entry.sha256 != entry_digest(entry):
            problems.append(f"entry {entry.id}: content does not match its hash")
        expected_prev = entry.sha256
    return problems


async def _last_entry(store: Store) -> ChainedAuditEntry | None:
    docs = await store.list_docs(Collection.AUDIT, limit=1, order_by="seq", descending=True)
    return ChainedAuditEntry.model_validate(docs[0]) if docs else None


def _lock(store: Store) -> asyncio.Lock:
    lock = _locks.get(store)
    if lock is None:
        lock = _locks[store] = asyncio.Lock()
    return lock


def _plain(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """JSON-safe copy, so the hash computed now matches the document read back later."""
    return None if value is None else dict(to_jsonable_python(dict(value)))
