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

A hosted airline's chain is never walked whole at start (D25): its runtime restores the head
the last checkpoint persisted (with ``verified_through_seq``, how far a walk has checked it),
reads only the entries after that head (:func:`catch_up`, one :meth:`Store.page`) and later
walks only what lies past ``verified_through_seq`` (:func:`check_chain`); a whole walk happens
only when an ops manager asks for one. The demo walks whole once, then each start walks only
past the verified point its last checkpoint persisted (:func:`resume`).

Only the instance that holds the writer claim appends (:func:`gate`): with two instances up
during a rollout, two appends after one newest entry would fork the chain. A fork found later
is repaired by ``scripts/audit_fork_repair.py``, which moves the branch no later entry links to
into :data:`ARCHIVE_COLLECTION` (no hash is rewritten) and leaves :data:`REPAIR_DOC` for the
serving instance, whose next checkpoint then walks again.
"""

import asyncio
import weakref
from collections.abc import Awaitable, Callable, Mapping, Sequence
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
    "ARCHIVE_COLLECTION",
    "GENESIS_SHA256",
    "NOT_WALKED",
    "PAGE_SIZE",
    "REPAIR_DOC",
    "WALK_LIMIT",
    "AuditChain",
    "ChainedAuditEntry",
    "NotWriter",
    "catch_up",
    "chain",
    "check_chain",
    "entry_digest",
    "gate",
    "head_doc",
    "list_entries",
    "newest_entry",
    "record",
    "require_writer",
    "restore_head",
    "resume",
    "verify_chain",
    "verify_head",
    "writable",
]

GENESIS_SHA256: Final = "0" * 64
WALK_LIMIT: Final = 100_000
"""Entries one walk reads (one ``list_docs``; neither store pages)"""
NOT_WALKED: Final = "not yet walked on this instance"
WALK_PROBLEMS: Final = 50
"""Problems one walk lists; the rest are counted (a fork once cascaded into thousands)"""
CATCH_UP_LIMIT: Final = 5_000
"""Entries read after the held head when the newest entry is not it (a rollout overlap)"""
PAGE_SIZE: Final = 500
"""Entries one read of an incremental or paged walk takes (``Store.page``)"""
VERIFIED_THROUGH: Final = "verified_through_seq"
VERIFIED_SHA256: Final = "verified_sha256"
REPAIR_DOC: Final = "audit_repair"
"""``runtime/audit_repair``: ``repaired_at``, written by ``scripts/audit_fork_repair.py --apply``"""
ARCHIVE_COLLECTION: Final = "audit_forks_archive"
"""Fork branches the repair moved out of ``audit``: verbatim copies, never read by the app"""
type Gate = Callable[[], Awaitable[bool]]
_locks: "weakref.WeakKeyDictionary[Store, asyncio.Lock]" = weakref.WeakKeyDictionary()
_chains: "weakref.WeakKeyDictionary[Store, AuditChain]" = weakref.WeakKeyDictionary()
_gates: "weakref.WeakKeyDictionary[Store, tuple[Gate, Gate]]" = weakref.WeakKeyDictionary()


class NotWriter(RuntimeError):
    """This instance does not hold the writer claim (``runtime/writer``): it appends nothing,
    so a rollout's two instances never both link an entry to the same newest one."""


def gate(store: Store, check: Gate | None, *, ask: Gate | None = None) -> None:
    """Every append to ``store`` first awaits ``check`` (under the append lock); False refuses
    the append with :class:`NotWriter`. ``ask`` answers :func:`writable` (``check`` when
    omitted) and never changes who holds the writer: a request refused after the question
    (a bad session, a 404) must not have taken the claim. None removes the gate. The demo
    runtime sets it (``Runtime.may_append``, ``Runtime.may_write``); a store without one
    appends as before."""
    if check is None:
        _gates.pop(store, None)
    else:
        _gates[store] = (check, ask or check)


async def writable(store: Store) -> bool:
    """What ``store``'s gate says now (True without one). A caller about to store something it
    will then audit asks first, so nothing is stored that the append would refuse."""
    found = _gates.get(store)
    return found is None or await found[1]()


async def require_writer(store: Store) -> None:
    """Raise :class:`NotWriter` unless ``store``'s gate lets this instance write now: called
    just before a write that is audited after it (a draft, a superseded draft, a failure), so
    a background run on an instance another one has out-claimed stores nothing unaudited."""
    if not await writable(store):
        raise NotWriter("not stored: this instance does not hold the writer")


@dataclass
class AuditChain:
    """This process's view of one store's chain: ``head`` is None until a walk or an append;
    ``rewalk`` asks the next checkpoint for a walk. ``verified_through_seq`` is how far a walk
    has found the chain intact (entry ``verified_sha256``); an incremental walk starts there."""

    head: ChainHead | None = None
    rewalk: bool = False
    verified_through_seq: int = 0
    verified_sha256: str = GENESIS_SHA256

    def verified(self, head: ChainHead, *, whole: bool = False) -> None:
        """A walk found the chain intact through ``head``. A whole walk that found problems
        drops the verified point: a problem below it (an entry edited, a fork found late) is
        one an incremental walk would never read again, so the next walk starts at genesis."""
        if head.intact:
            self.verified_through_seq, self.verified_sha256 = head.seq, head.sha256
        elif whole:
            self.verified_through_seq, self.verified_sha256 = 0, GENESIS_SHA256


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
    """Append one entry. The append runs shielded: a tick cancelled at its deadline (or a
    request that goes away) never leaves an entry written but not taken into the held head;
    the append completes and the cancel takes effect after it."""
    return await asyncio.shield(
        _record(
            store,
            actor=actor,
            action=action,
            advisory_id=advisory_id,
            before=before,
            after=after,
            input_hashes=input_hashes,
            model_id=model_id,
            prompt_hash=prompt_hash,
            note=note,
        )
    )


async def _record(
    store: Store,
    *,
    actor: str,
    action: AuditAction,
    advisory_id: str | None,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    input_hashes: Sequence[str],
    model_id: str | None,
    prompt_hash: str | None,
    note: str | None,
) -> AuditEntry:
    async with _lock(store):
        found = _gates.get(store)
        if found is not None and not await found[0]():
            raise NotWriter(f"{action.value} not recorded: this instance does not hold the writer")
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
    docs = await store.page(
        Collection.AUDIT, field="seq", before=head.seq, limit=CATCH_UP_LIMIT, descending=False
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
        held.verified(head, whole=True)
        return head


async def check_chain(store: Store, *, whole: bool = False) -> ChainHead:
    """Walk the chain in pages and hold the head found. Only the entries past the held
    ``verified_through_seq`` are read unless ``whole`` (an ops manager's full check): the part
    already found intact is not read again. Never per request; a hosted airline's checkpoint
    and its ops manager's check call it."""
    async with _lock(store):
        held = chain(store)
        start_seq, start_sha256 = (
            (0, GENESIS_SHA256) if whole else (held.verified_through_seq, held.verified_sha256)
        )
        docs = await _pages(store, after=start_seq)
        tail = _walk(docs, start_seq=start_seq, start_sha256=start_sha256)
        # Everything up to the verified point was found intact by a walk, and a whole walk
        # that finds a problem drops that point (``AuditChain.verified``); everything after it
        # is read again here, so this walk's problems are the chain's.
        head = tail.model_copy(update={"entries": start_seq + tail.entries})
        held.head = head
        held.rewalk = False
        held.verified(head, whole=start_seq == 0)
        return head


async def catch_up(store: Store) -> ChainHead | None:
    """Move the held head (a restored one) over the entries written after it, reading only
    those (one page of at most ``CATCH_UP_LIMIT``): when they link up to the head, the head
    moves to the newest; when they do not, the head is marked not intact and a walk is asked
    for. Nothing is read before the head."""
    async with _lock(store):
        held = chain(store)
        head = held.head
        if head is None:
            return None
        docs = await store.page(
            Collection.AUDIT, field="seq", before=head.seq, limit=CATCH_UP_LIMIT, descending=False
        )
        if not docs:
            return head
        tail = _walk(docs, start_seq=head.seq, start_sha256=head.sha256)
        update: dict[str, Any] = {
            "seq": tail.seq,
            "sha256": tail.sha256,
            "entries": head.entries + tail.entries,
        }
        if not tail.intact:
            update["intact"] = False
            update["problems"] = [*head.problems, *tail.problems]
            held.rewalk = True
        held.head = head.model_copy(update=update)
        return held.head


async def resume(store: Store, doc: Mapping[str, Any] | None) -> ChainHead | None:
    """Start from the verified point a checkpoint persisted (``runtime/audit_head`` with
    ``verified_through_seq``) and walk only the entries after it (:func:`check_chain`); the
    head found is held. None, with nothing read or held, when ``doc`` carries no verified
    point: the caller walks the whole chain (:func:`verify_head`)."""
    if doc is None:
        return None
    through, sha256 = doc.get(VERIFIED_THROUGH), doc.get(VERIFIED_SHA256)
    if not (isinstance(through, int) and through > 0 and isinstance(sha256, str)):
        return None
    try:
        persisted = ChainHead.model_validate(doc)
    except ValidationError:
        return None
    if through > persisted.seq:
        return None
    held = chain(store)
    held.verified_through_seq, held.verified_sha256 = through, sha256
    return await check_chain(store)


def head_doc(store: Store, *, verified: bool = False) -> dict[str, Any] | None:
    """The held head as ``runtime/audit_head`` keeps it; with ``verified`` (a hosted airline)
    also how far a walk has checked it. None while no head is held."""
    held = chain(store)
    if held.head is None:
        return None
    doc = held.head.model_dump(mode="json")
    if verified:
        doc[VERIFIED_THROUGH] = held.verified_through_seq
        doc[VERIFIED_SHA256] = held.verified_sha256
    return doc


async def newest_entry(store: Store) -> ChainedAuditEntry | None:
    """The newest entry by ``seq`` (one read), or None while the chain is empty."""
    return await _last_entry(store)


def restore_head(
    store: Store, doc: Mapping[str, Any] | None, *, trusted: bool = False
) -> ChainHead | None:
    """Hold the head a checkpoint persisted (``runtime/audit_head``) and return it; None
    (nothing held) when ``doc`` is absent or not a head.

    The demo holds it as not yet walked on this instance, with a re-walk marked. A hosted
    airline (``trusted``) holds it as persisted, with the ``verified_through_seq`` it carries,
    and walks only past that point later (D25)."""
    if doc is None:
        return None
    try:
        persisted = ChainHead.model_validate(doc)
    except ValidationError:
        return None
    held = chain(store)
    if trusted:
        held.head = persisted
        held.rewalk = False
        through, sha256 = doc.get(VERIFIED_THROUGH), doc.get(VERIFIED_SHA256)
        if isinstance(through, int) and isinstance(sha256, str) and 0 <= through <= persisted.seq:
            held.verified_through_seq, held.verified_sha256 = through, sha256
        return persisted
    head = persisted.model_copy(update={"intact": False, "problems": [NOT_WALKED]})
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


async def _pages(store: Store, *, after: int) -> list[dict[str, Any]]:
    """Every entry with ``seq`` above ``after``, oldest first, read a page at a time."""
    docs: list[dict[str, Any]] = []
    cursor = after
    while len(docs) < WALK_LIMIT:
        page = await store.page(
            Collection.AUDIT, field="seq", before=cursor, limit=PAGE_SIZE, descending=False
        )
        docs.extend(page)
        if len(page) < PAGE_SIZE:
            break
        cursor = page[-1]["seq"]
    return docs


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
