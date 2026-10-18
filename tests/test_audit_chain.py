"""The audit chain's head: advanced on every append from the entry written, walked from the
first entry once (``verify_head``), checkpointed beside ``runtime/state`` with the point a walk
found it intact through, and walked at a later start only past that point (``resume``)."""

import asyncio
from collections.abc import AsyncIterator, Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from test_pipeline import AT, DATA_DIR, POLICY, ROUTES, FixtureSource, make_settings, trace_events

from tephra.agents.llm import get_llm
from tephra.config import Settings
from tephra.desk import audit
from tephra.desk.approvals import SYSTEM_ACTOR
from tephra.feeds.airports import load_airports
from tephra.feeds.volcanoes import load_volcanoes
from tephra.models import AuditAction, AuditEntry, AuditList, ChainHead, RunMode
from tephra.pipeline import AUDIT_HEAD_DOC, Runtime
from tephra.store.base import Collection, Store, Where
from tephra.store.sqlite_store import SqliteStore
from tephra.util.events import EventBus
from tephra.util.timeutil import FixedClock, use_clock


@pytest.fixture(autouse=True)
def clock() -> Iterator[None]:
    with use_clock(FixedClock(AT)):
        yield


class CountingStore(SqliteStore):
    """A SQLite store that counts its reads (``get`` and every query, which ``list_docs``
    goes through) and the full chain walks among them."""

    def __init__(self, path: Path, blob_dir: Path) -> None:
        super().__init__(path, blob_dir)
        self.reads = 0
        self.walks = 0
        self.paged: list[int] = []
        """seq of every audit entry a page read returned (an incremental walk)"""

    async def get(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        self.reads += 1
        return await super().get(collection, doc_id)

    async def query(
        self,
        collection: str,
        where: Sequence[Where] = (),
        *,
        order_by: str | None = None,
        descending: bool = True,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self.reads += 1
        if collection == Collection.AUDIT and limit == audit.WALK_LIMIT and not descending:
            self.walks += 1
        return await super().query(
            collection, where, order_by=order_by, descending=descending, limit=limit
        )

    async def page(
        self,
        collection: str,
        *,
        field: str,
        before: Any | None,
        limit: int,
        descending: bool = True,
    ) -> list[dict[str, Any]]:
        docs = await super().page(
            collection, field=field, before=before, limit=limit, descending=descending
        )
        if collection == Collection.AUDIT:
            self.paged.extend(doc["seq"] for doc in docs)
        return docs


@pytest.fixture
async def store(tmp_path: Path) -> AsyncIterator[CountingStore]:
    counting = CountingStore(tmp_path / "audit.sqlite3", tmp_path / "blobs")
    yield counting
    await counting.aclose()


async def append(store: Store, n: int, *, note: str = "entry") -> list[AuditEntry]:
    return [
        await audit.record(
            store, actor=SYSTEM_ACTOR, action=AuditAction.AI_FAILED, note=f"{note} {i}"
        )
        for i in range(n)
    ]


def make_runtime(settings: Settings, store: Store, *, mode: RunMode = RunMode.LIVE) -> Runtime:
    return Runtime(
        settings=settings,
        store=store,
        bus=EventBus(),
        source=FixtureSource(),
        llm=get_llm(settings),
        catalogue=load_volcanoes(DATA_DIR),
        airports=load_airports(DATA_DIR, min_runway_m=POLICY.alternates.min_runway_m.value),
        routes=ROUTES,
        policy=POLICY,
        mode=mode,
        replay_case=None,
        auto_replay=False,
    )


# --- the API shape --------------------------------------------------------------------------


async def test_the_audit_api_shape_carries_the_chain_fields(store: CountingStore) -> None:
    written = await append(store, 3)
    listed = await audit.list_entries(store, limit=10)
    assert [entry.seq for entry in listed] == [3, 2, 1], "newest first, from the stored docs"
    assert all(isinstance(entry, AuditEntry) for entry in listed)

    shown = AuditList(entries=listed).model_dump(mode="json")
    newest = shown["entries"][0]
    assert newest["seq"] == 3
    assert newest["prev_sha256"] == written[1].sha256
    assert newest["sha256"] == written[2].sha256
    assert shown["entries"][2]["prev_sha256"] == audit.GENESIS_SHA256

    again = AuditList.model_validate(shown)
    assert [entry.sha256 for entry in again.entries] == [entry.sha256 for entry in listed]


# --- one read per append, the head advanced from the entry written ----------------------------


async def test_an_append_reads_the_store_at_most_once(store: CountingStore) -> None:
    await audit.verify_head(store)
    store.reads = store.walks = 0
    written = await append(store, 5)
    assert store.reads <= 5, "one read of the newest entry per append, nothing else"
    assert store.walks == 0

    head = audit.chain(store).head
    assert head is not None
    assert head.seq == 5
    assert head.sha256 == written[-1].sha256
    assert head.entries == 5
    assert head.intact is True, "the walk said so and every append since was this writer's"
    assert head.problems == []


async def test_an_append_before_any_walk_holds_a_head_that_is_not_yet_walked(
    store: CountingStore,
) -> None:
    written = await append(store, 2)
    head = audit.chain(store).head
    assert head is not None
    assert (head.seq, head.sha256) == (2, written[-1].sha256)
    assert head.intact is False
    assert head.problems == [audit.NOT_WALKED]
    assert audit.chain(store).rewalk is True, "the next checkpoint walks it"


# --- the walk -------------------------------------------------------------------------------


async def test_verify_head_walks_from_genesis_once_at_startup(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    seeded = SqliteStore(settings.sqlite_path, settings.cache_dir / "blobs")
    await append(seeded, 4, note="before the start")
    await seeded.aclose()

    store = CountingStore(settings.sqlite_path, settings.cache_dir / "blobs")
    runtime = make_runtime(settings, store)
    try:
        assert runtime.audit_head is None, "nothing is claimed before the chain was seen"
        await runtime.restore()
        assert store.walks == 1, "no persisted head: walked from the first entry at startup"
        head = runtime.audit_head
        assert head is not None
        assert (head.seq, head.entries, head.intact, head.problems) == (4, 4, True, [])
        assert head.checked_at.tzinfo is not None

        for _ in range(3):
            state = await runtime.system_state()
            assert state.audit == head, "the state reads memory"
        await append(store, 2, note="after the start")
        await runtime.checkpoint(force=True)
        assert store.walks == 1, "a request or a checkpoint never walks an intact chain again"
        advanced = runtime.audit_head
        assert advanced is not None
        assert (advanced.seq, advanced.entries, advanced.intact) == (6, 6, True)
        assert advanced.checked_at == head.checked_at, "the time of the last walk"
        assert [e["message"] for e in trace_events(runtime)] == [], "an intact chain is quiet"
    finally:
        await runtime.aclose()


async def test_a_duplicate_seq_is_reported_as_a_fork(store: CountingStore) -> None:
    written = await append(store, 2)
    other = written[1].model_copy(update={"id": "another-writer", "note": "its own seq 2"})
    other = other.model_copy(update={"sha256": audit.entry_digest(other)})
    await store.append_audit(other)

    head = await audit.verify_head(store)
    assert head.intact is False
    assert "fork at seq 2" in head.problems
    assert head.entries == 3
    assert head.seq == 2
    assert audit.chain(store).head == head
    assert audit.chain(store).rewalk is False


async def test_a_broken_link_is_named_by_its_seq(store: CountingStore) -> None:
    written = await append(store, 3)
    await store.delete(Collection.AUDIT, written[1].id)

    head = await audit.verify_head(store)
    assert head.intact is False
    assert head.problems == [
        f"entry {written[2].id}: seq 3, expected 2",
        "broken link at seq 3",
    ]
    assert head.entries == 2
    assert await audit.verify_chain(store) == head.problems, "the two walks agree"

    doc = await store.get(Collection.AUDIT, written[0].id)
    assert doc is not None
    await store.put(Collection.AUDIT, written[0].id, {**doc, "note": "rewritten"})
    assert (await audit.verify_head(store)).problems[0] == (
        f"entry {written[0].id}: content does not match its hash"
    )


async def test_an_empty_chain_has_a_genesis_head(store: CountingStore) -> None:
    head = await audit.verify_head(store)
    assert head == ChainHead(
        seq=0,
        sha256=audit.GENESIS_SHA256,
        checked_at=head.checked_at,
        entries=0,
        intact=True,
    )


# --- another writer (a rollout overlap) -----------------------------------------------------


async def test_another_writer_that_linked_correctly_is_caught_up_silently(
    tmp_path: Path,
) -> None:
    """A rollout overlap: the serving instance keeps appending while the candidate holds an
    older head. The candidate's next append walks only what came after its head; those
    entries link up, so the head moves on and nothing is flagged."""
    path, blobs = tmp_path / "shared.sqlite3", tmp_path / "blobs"
    serving = CountingStore(path, blobs)
    candidate = SqliteStore(path, blobs)
    try:
        await append(serving, 2, note="serving")
        assert (await audit.verify_head(serving)).intact is True

        await append(candidate, 3, note="candidate")
        mine = await append(serving, 1, note="serving again")
        head = audit.chain(serving).head
        assert head is not None
        assert head.intact is True
        assert head.problems == []
        assert (head.seq, head.sha256) == (6, mine[0].sha256), "advanced from the entry written"
        assert head.entries == 6
        assert audit.chain(serving).rewalk is False
        assert serving.walks == 1, "no full walk: only the three entries after the head were read"

        walked = await audit.verify_head(serving)
        assert walked.intact is True
        assert walked.entries == 6
    finally:
        await candidate.aclose()
        await serving.aclose()


async def test_another_writer_that_forked_marks_the_head_not_intact(tmp_path: Path) -> None:
    path, blobs = tmp_path / "shared.sqlite3", tmp_path / "blobs"
    serving = CountingStore(path, blobs)
    candidate = SqliteStore(path, blobs)
    try:
        written = await append(serving, 2, note="serving")
        assert (await audit.verify_head(serving)).intact is True

        stray = written[1].model_copy(
            update={"id": "stray", "seq": 3, "prev_sha256": "f" * 64, "note": "a bad link"}
        )
        await candidate.append_audit(stray.model_copy(update={"sha256": audit.entry_digest(stray)}))
        mine = await append(serving, 1, note="serving again")
        head = audit.chain(serving).head
        assert head is not None
        assert head.intact is False
        assert head.problems == ["another writer appended after seq 2"]
        assert (head.seq, head.sha256) == (4, mine[0].sha256), "advanced from the entry written"
        assert audit.chain(serving).rewalk is True

        await append(serving, 1, note="serving once more")
        later = audit.chain(serving).head
        assert later is not None
        assert later.problems == ["another writer appended after seq 2"], "said once"
        assert later.seq == 5

        walked = await audit.verify_head(serving)
        assert walked.intact is False
        assert walked.problems == ["broken link at seq 3"]
        assert walked.entries == 5
        assert audit.chain(serving).rewalk is False
    finally:
        await candidate.aclose()
        await serving.aclose()


async def test_a_run_of_forks_is_one_problem_and_the_walk_goes_on(store: CountingStore) -> None:
    """Two instances that appended side by side for five seqs (the live chain's history) are
    one problem, not one per entry after them; the entry after the run links to either
    branch, and the list is capped."""
    written = await append(store, 3)
    other_prev = written[2].sha256
    for seq in range(4, 9):
        mine = (await append(store, 1, note=f"mine {seq}"))[0]
        assert mine.seq == seq
        other = mine.model_copy(
            update={"id": f"other-{seq}", "prev_sha256": other_prev, "note": f"other {seq}"}
        )
        other = other.model_copy(update={"sha256": audit.entry_digest(other)})
        await store.append_audit(other)
        other_prev = other.sha256
    await append(store, 3, note="after the overlap")

    head = await audit.verify_head(store)
    assert head.problems == ["fork at seq 4-8"]
    assert head.intact is False
    assert head.entries == 16
    assert head.seq == 11

    capped = audit._walk([{"id": f"bad-{i}"} for i in range(audit.WALK_PROBLEMS + 7)])
    assert len(capped.problems) == audit.WALK_PROBLEMS + 1
    assert capped.problems[-1] == "7 more problems not listed"


async def test_a_checkpoint_walks_again_only_when_marked(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    store = CountingStore(settings.sqlite_path, settings.cache_dir / "blobs")
    other = SqliteStore(settings.sqlite_path, settings.cache_dir / "blobs")
    runtime = make_runtime(settings, store)
    try:
        await runtime.restore()
        assert store.walks == 1
        mine = (await append(store, 1, note="mine"))[0]
        stray = mine.model_copy(
            update={"id": "stray", "seq": 2, "prev_sha256": "f" * 64, "note": "badly linked"}
        )
        await other.append_audit(stray.model_copy(update={"sha256": audit.entry_digest(stray)}))
        await append(store, 1, note="mine again")
        assert audit.chain(store).rewalk is True
        held = runtime.audit_head
        assert held is not None
        assert held.intact is False
        store.paged.clear()  # the append's catch-up read the stray entry

        await runtime.checkpoint(force=True)
        assert store.paged == [1, 2, 3], "the marked re-walk ran at the checkpoint"
        head = runtime.audit_head
        assert head is not None
        assert (head.seq, head.intact, head.problems) == (3, False, ["broken link at seq 2"])
        persisted = await store.get(Collection.RUNTIME, AUDIT_HEAD_DOC)
        assert persisted is not None
        assert persisted == {
            **head.model_dump(mode="json"),
            "verified_through_seq": 0,
            "verified_sha256": audit.GENESIS_SHA256,
        }, "never found intact past the empty chain: the next start walks it whole"

        runtime._last_checkpoint = None
        await runtime.checkpoint(force=True)
        assert store.paged == [1, 2, 3], "nothing marked: no walk"
    finally:
        await other.aclose()
        await runtime.aclose()


# --- checkpoint and restore --------------------------------------------------------------------


async def test_a_later_start_walks_only_past_the_verified_point(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    first_store = SqliteStore(settings.sqlite_path, settings.cache_dir / "blobs")
    await append(first_store, 3, note="before the first start")
    first = make_runtime(settings, first_store)
    try:
        await first.restore()
        written = await append(first.store, 2, note="first process")
        await first.checkpoint(force=True)
        walked_at = first.audit_head.checked_at if first.audit_head else None
    finally:
        await first.aclose()
    assert walked_at is not None

    store = CountingStore(settings.sqlite_path, settings.cache_dir / "blobs")
    second = make_runtime(settings, store)
    try:
        await second.restore()
        assert store.walks == 0, "a verified point was persisted: no whole walk"
        assert store.paged == [4, 5], "only what came after the first start's walk is read"
        head = second.audit_head
        assert head is not None
        assert (head.seq, head.sha256) == (5, written[-1].sha256)
        assert (head.entries, head.intact, head.problems) == (5, True, [])
        assert head.checked_at >= walked_at, "the time of this instance's walk"
        assert (await second.system_state()).audit == head
        persisted = await store.get(Collection.RUNTIME, AUDIT_HEAD_DOC)
        assert persisted is not None
        await second.checkpoint(force=True)
        persisted = await store.get(Collection.RUNTIME, AUDIT_HEAD_DOC)
        assert persisted is not None
        assert persisted["verified_through_seq"] == 5
    finally:
        await second.aclose()


async def test_a_problem_past_the_verified_point_is_found_at_the_next_start(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    first_store = SqliteStore(settings.sqlite_path, settings.cache_dir / "blobs")
    await append(first_store, 2, note="before the first start")
    first = make_runtime(settings, first_store)
    try:
        await first.restore()
        written = await append(first.store, 2, note="first process")
        await first.checkpoint(force=True)
    finally:
        await first.aclose()
    edited = SqliteStore(settings.sqlite_path, settings.cache_dir / "blobs")
    doc = await edited.get(Collection.AUDIT, written[0].id)
    assert doc is not None
    await edited.put(Collection.AUDIT, written[0].id, {**doc, "note": "rewritten"})
    await edited.aclose()

    store = CountingStore(settings.sqlite_path, settings.cache_dir / "blobs")
    second = make_runtime(settings, store)
    try:
        await second.restore()
        assert store.walks == 0
        head = second.audit_head
        assert head is not None
        assert head.intact is False
        assert head.problems == [f"entry {written[0].id}: content does not match its hash"]
    finally:
        await second.aclose()


async def test_a_persisted_head_behind_the_newest_entry_is_walked_at_startup(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    first = make_runtime(settings, SqliteStore(settings.sqlite_path, settings.cache_dir / "blobs"))
    try:
        await first.restore()
        await append(first.store, 2, note="checkpointed")
        await first.checkpoint(force=True)
        first.retired = True  # no checkpoint on close: the head stays at seq 2
        await append(first.store, 1, note="after the checkpoint")
    finally:
        await first.aclose()

    store = CountingStore(settings.sqlite_path, settings.cache_dir / "blobs")
    second = make_runtime(settings, store, mode=RunMode.REPLAY)
    try:
        await second.restore()
        assert store.walks == 1, "both modes walk a head that is behind"
        head = second.audit_head
        assert head is not None
        assert (head.seq, head.entries, head.intact, head.problems) == (3, 3, True, [])
    finally:
        await second.aclose()


async def test_an_unreadable_persisted_head_is_walked_at_startup(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    store = CountingStore(settings.sqlite_path, settings.cache_dir / "blobs")
    await store.put(Collection.RUNTIME, AUDIT_HEAD_DOC, {"seq": "three", "junk": True})
    runtime = make_runtime(settings, store)
    try:
        await runtime.restore()
        assert store.walks == 1
        head = runtime.audit_head
        assert head is not None
        assert (head.seq, head.intact) == (0, True)
    finally:
        await runtime.aclose()


async def test_a_chain_that_is_not_intact_is_traced_at_startup(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    store = CountingStore(settings.sqlite_path, settings.cache_dir / "blobs")
    written = await append(store, 2)
    doc = await store.get(Collection.AUDIT, written[0].id)
    assert doc is not None
    await store.put(Collection.AUDIT, written[0].id, {**doc, "actor": "someone else"})
    runtime = make_runtime(settings, store)
    try:
        await runtime.restore()
        head = runtime.audit_head
        assert head is not None
        assert head.intact is False
        messages = [e["message"] for e in trace_events(runtime)]
        assert messages == [
            f"Audit chain not intact at seq 2: entry {written[0].id}: content does not match"
            " its hash"
        ]
    finally:
        await runtime.aclose()


async def test_concurrent_appends_advance_the_head_in_order(store: CountingStore) -> None:
    await audit.verify_head(store)
    await asyncio.gather(*(append(store, 1, note=f"writer {n}") for n in range(20)))
    head = audit.chain(store).head
    assert head is not None
    assert (head.seq, head.entries, head.intact) == (20, 20, True)
    assert head == (await audit.verify_head(store)).model_copy(
        update={"checked_at": head.checked_at}
    )
