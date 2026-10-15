"""Append-only audit trail, hash-chained so that an edited or deleted entry shows.

Each entry carries a sequence number, the SHA-256 of the entry before it and its own
SHA-256 over everything else it holds. Rewriting any stored entry breaks its own hash;
deleting one breaks the next entry's link. :func:`verify_chain` checks both.

Entries are chained in one process (Cloud Run runs one instance), so a per-store lock is
enough to keep two coroutines from linking to the same predecessor.

The chain's head (:class:`tephra.models.ChainHead`) is held in memory per store: one full walk
from the first entry (:func:`verify_head`, at startup and when a re-walk is marked) says whether
the chain is intact, and every append advances the head from the entry just written. The one
read of the newest entry per append is the fork detector across a rollout overlap, when a
no-traffic candidate and the serving instance both hold a head: a newest entry that is not the
head's marks the head not intact until the next walk.
"""

import asyncio
import weakref
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final
from uuid import uuid4

from pydantic import Field, ValidationError
from pydantic_core import to_jsonable_python

from tephra.models import AuditAction, AuditEntry, ChainHead
from tephra.store.base import Collection, Store, Where
from tephra.util import timeutil
from tephra.util.hashing import sha256_json

__all__ = [
    "GENESIS_SHA256",
    "NOT_WALKED",
    "WALK_LIMIT",
    "AuditChain",
    "ChainedAuditEntry",
    "chain",
    "entry_digest",
    "list_entries",
    "newest_entry",
    "record",
    "restore_head",
    "verify_chain",
    "verify_head",
]

GENESIS_SHA256: Final = "0" * 64
WALK_LIMIT: Final = 100_000
"""Entries one walk reads (one ``list_docs``; neither store pages)"""
NOT_WALKED: Final = "not yet walked on this instance"
WALK_PROBLEMS: Final = 50
"""Problems one walk lists; the rest are counted (a fork once cascaded into thousands)"""
CATCH_UP_LIMIT: Final = 5_000
"""Entries read after the held head when the newest entry is not it (a rollout overlap)"""
_locks: "weakref.WeakKeyDictionary[Store, asyncio.Lock]" = weakref.WeakKeyDictionary()
_chains: "weakref.WeakKeyDictionary[Store, AuditChain]" = weakref.WeakKeyDictionary()


@dataclass
class AuditChain:
    """This process's view of one store's chain: ``head`` is None until a walk or an append;
    ``rewalk`` asks the next checkpoint for a full walk."""

    head: ChainHead | None = None
    rewalk: bool = False


def chain(store: Store) -> AuditChain:
    found = _chains.get(store)
    if found is None:
        found = _chains[store] = AuditChain()
    return found


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
        await _catch_up(store, chain(store), previous)
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
        _advance(chain(store), previous, entry)
        return entry


async def _catch_up(store: Store, held: AuditChain, previous: ChainedAuditEntry | None) -> None:
    """When the newest entry is not the head this process holds, another instance wrote
    after it (a rollout overlap: the serving instance kept appending while the candidate
    walked). Walk only what came after the head: when those entries link up to the head and
    end at the newest, the head moves to the newest and nothing is flagged; the next append
    then marks the overlap and asks for a full walk."""
    head = held.head
    if head is None or previous is None:
        return
    if previous.seq == head.seq and previous.sha256 == head.sha256:
        return
    if previous.seq <= head.seq:
        return
    docs = await store.query(
        Collection.AUDIT,
        [Where("seq", ">", head.seq)],
        order_by="seq",
        descending=False,
        limit=CATCH_UP_LIMIT,
    )
    tail = _walk(docs, start_seq=head.seq, start_sha256=head.sha256)
    if tail.intact and (tail.seq, tail.sha256) == (previous.seq, previous.sha256):
        held.head = head.model_copy(
            update={"seq": tail.seq, "sha256": tail.sha256, "entries": head.entries + tail.entries}
        )


def _advance(
    held: AuditChain, previous: ChainedAuditEntry | None, entry: ChainedAuditEntry
) -> None:
    head = held.head
    if head is None:
        held.head = ChainHead(
            seq=entry.seq,
            sha256=entry.sha256,
            checked_at=entry.at,
            entries=entry.seq,
            intact=False,
            problems=[NOT_WALKED],
        )
        held.rewalk = True
        return
    update: dict[str, Any] = {
        "seq": entry.seq,
        "sha256": entry.sha256,
        "entries": head.entries + 1,
    }
    if previous is not None and (previous.seq != head.seq or previous.sha256 != head.sha256):
        update["intact"] = False
        update["problems"] = [*head.problems, f"another writer appended after seq {head.seq}"]
        held.rewalk = True
    held.head = head.model_copy(update=update)


async def list_entries(
    store: Store, *, advisory_id: str | None = None, limit: int = 100
) -> list[AuditEntry]:
    """Newest first."""
    where = [] if advisory_id is None else [Where("advisory_id", "==", advisory_id)]
    docs = await store.query(Collection.AUDIT, where, order_by="seq", descending=True, limit=limit)
    return [ChainedAuditEntry.model_validate(doc) for doc in docs]


async def verify_chain(store: Store, *, limit: int = WALK_LIMIT) -> list[str]:
    """Problems found walking the chain from the first entry; empty when it is intact."""
    docs = await store.list_docs(Collection.AUDIT, limit=limit, order_by="seq", descending=False)
    return _walk(docs).problems


async def verify_head(store: Store, *, limit: int = WALK_LIMIT) -> ChainHead:
    """One full walk from the first entry; the head it finds is held for ``store`` until the
    next append advances it. Called at startup, at a checkpoint after a re-walk was marked and
    by ``scripts/verify_audit.py``: never per request."""
    async with _lock(store):
        docs = await store.list_docs(
            Collection.AUDIT, limit=limit, order_by="seq", descending=False
        )
        head = _walk(docs)
        held = chain(store)
        held.head = head
        held.rewalk = False
        return head


async def newest_entry(store: Store) -> ChainedAuditEntry | None:
    """The newest entry by ``seq`` (one read), or None while the chain is empty."""
    return await _last_entry(store)


def restore_head(store: Store, doc: Mapping[str, Any] | None) -> ChainHead | None:
    """Hold the head a checkpoint persisted (``runtime/audit_head``) as not yet walked on this
    instance, with a re-walk marked, and return it; None (nothing held) when ``doc`` is absent
    or not a head."""
    if doc is None:
        return None
    try:
        persisted = ChainHead.model_validate(doc)
    except ValidationError:
        return None
    head = persisted.model_copy(update={"intact": False, "problems": [NOT_WALKED]})
    held = chain(store)
    held.head = head
    held.rewalk = True
    return head


def _walk(
    docs: Sequence[Mapping[str, Any]], *, start_seq: int = 0, start_sha256: str = GENESIS_SHA256
) -> ChainHead:
    """Walk entries in ``seq`` order from the entry ``start_seq``/``start_sha256`` (genesis by
    default). Two entries at one seq are a fork: both are followed, so the entry after a fork
    links to either branch and a run of forked seqs is one problem, not one per entry after
    it. A seq that skips ahead is named once, then the walk goes on from it. The list of
    problems is capped (``WALK_PROBLEMS``); the count of the rest is its last line."""
    problems: list[str] = []
    seen_seq = start_seq
    branches: set[str] = {start_sha256}  # sha256 of every entry at seen_seq
    growing: set[str] = set()  # sha256 of every entry at the seq being read
    fork_run: tuple[int, int] | None = None
    last: ChainedAuditEntry | None = None

    def close_fork_run() -> None:
        nonlocal fork_run
        if fork_run is not None:
            first, until = fork_run
            problems.append(
                f"fork at seq {first}" if first == until else f"fork at seq {first}-{until}"
            )
            fork_run = None

    for doc in docs:
        try:
            entry = ChainedAuditEntry.model_validate(doc)
        except ValidationError:
            problems.append(f"entry {doc.get('id')!r} is not a chained audit entry")
            branches, growing = set(), set()
            continue
        if entry.seq == seen_seq and last is not None:
            fork_run = (entry.seq, entry.seq) if fork_run is None else (fork_run[0], entry.seq)
        else:
            if fork_run is not None and seen_seq != fork_run[1]:
                close_fork_run()
            if entry.seq != seen_seq + 1:
                problems.append(f"entry {entry.id}: seq {entry.seq}, expected {seen_seq + 1}")
            if growing:
                branches = growing
            growing = set()
            seen_seq = entry.seq
        if entry.prev_sha256 not in branches:
            problems.append(f"broken link at seq {entry.seq}")
        if entry.sha256 != entry_digest(entry):
            problems.append(f"entry {entry.id}: content does not match its hash")
        growing.add(entry.sha256)
        last = entry
    close_fork_run()
    if len(problems) > WALK_PROBLEMS:
        rest = len(problems) - WALK_PROBLEMS
        problems = [*problems[:WALK_PROBLEMS], f"{rest} more problems not listed"]
    return ChainHead(
        seq=start_seq if last is None else last.seq,
        sha256=start_sha256 if last is None else last.sha256,
        checked_at=timeutil.SystemClock().now(),
        entries=len(docs),
        intact=not problems,
        problems=problems,
    )


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
