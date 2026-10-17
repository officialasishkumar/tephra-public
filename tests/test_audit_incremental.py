"""A hosted airline's audit chain is never walked whole at start (D25, S5, S24): a restart takes
the persisted head and reads only the entries after it, a later check reads only past
``verified_through_seq``, a held head is reused, and a cancelled caller never leaves an entry
written but not taken into the head. Reads are counted by the store meter, as Firestore bills
them."""

import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from test_hosted_runtime import (
    POLICY,
    ROUTES,
    FixtureSource,
    hosted_runtime,
    hosted_settings,
    rfb_aircraft,
)

from tephra.desk import audit
from tephra.desk.audit import GENESIS_SHA256, ChainedAuditEntry, entry_digest
from tephra.feeds.airports import load_airports
from tephra.feeds.volcanoes import load_volcanoes
from tephra.models import AuditAction
from tephra.pipeline import AUDIT_HEAD_DOC, HostedParts, create_runtime
from tephra.store import encode_doc
from tephra.store.base import Collection
from tephra.store.metered import MeteredStore, StoreMeter
from tephra.store.sqlite_store import SqliteStore
from tephra.util import timeutil
from tephra.util.scope import bind_tenant
from tephra.util.timeutil import FixedClock

AT = datetime(2026, 10, 17, 6, 0, tzinfo=UTC)
CHAIN = 10_000


def chained(n: int, *, after: ChainedAuditEntry | None = None) -> list[ChainedAuditEntry]:
    entries: list[ChainedAuditEntry] = []
    previous = after
    for _ in range(n):
        seq = 1 if previous is None else previous.seq + 1
        unsigned = ChainedAuditEntry(
            id=f"e{seq:06d}",
            at=AT + timedelta(seconds=seq),
            actor="system",
            action=AuditAction.MEMBER_JOINED,
            after={"member_id": f"MB-{seq:010d}"},
            seq=seq,
            prev_sha256=GENESIS_SHA256 if previous is None else previous.sha256,
            sha256="",
        )
        previous = unsigned.model_copy(update={"sha256": entry_digest(unsigned)})
        entries.append(previous)
    return entries


async def write_raw(store: SqliteStore, entries: list[ChainedAuditEntry]) -> None:
    rows = [(Collection.AUDIT.value, e.id, encode_doc(e.model_dump(mode="json"))) for e in entries]
    await store._run(
        lambda conn: conn.executemany(
            "INSERT INTO docs (collection, id, doc) VALUES (?, ?, ?)", rows
        )
    )


def reads(meter: StoreMeter) -> int:
    return meter.day().reads.get("RFB", 0)


@pytest.fixture
def meter() -> StoreMeter:
    return StoreMeter(blob_puts_cap=4_000)


async def test_a_restart_reads_only_the_tail_and_a_check_only_past_the_verified_point(
    tmp_path: Path, meter: StoreMeter
) -> None:
    settings = hosted_settings(tmp_path)
    settings.sqlite_path.parent.mkdir(parents=True)
    raw = SqliteStore(settings.sqlite_path, settings.cache_dir / "blobs")
    body = chained(CHAIN)
    await write_raw(raw, body)
    first = MeteredStore(raw, meter, "RFB")
    with timeutil.bind_clock(FixedClock(AT)), bind_tenant("RFB"):
        head = await audit.check_chain(first, whole=True)
        assert (head.seq, head.entries, head.intact) == (CHAIN, CHAIN, True)
        assert audit.chain(first).verified_through_seq == CHAIN
        await first.put(
            Collection.RUNTIME, AUDIT_HEAD_DOC, audit.head_doc(first, verified=True) or {}
        )
        await write_raw(raw, chained(5, after=body[-1]))  # written after the checkpoint
    await first.aclose()

    before = reads(meter)
    rfb = await hosted_runtime(tmp_path, meter)  # a new process: a new store object
    try:
        restarted = reads(meter) - before
        held = audit.chain(rfb.store)
        assert held.head is not None
        assert (held.head.seq, held.head.entries, held.head.intact) == (CHAIN + 5, CHAIN + 5, True)
        assert held.verified_through_seq == CHAIN
        assert restarted < 100, f"a restart read {restarted} documents, not the chain"

        with rfb.bound():
            before = reads(meter)
            checked = await audit.check_chain(rfb.store)
            incremental = reads(meter) - before
            before = reads(meter)
            whole = await audit.check_chain(rfb.store, whole=True)
            walked = reads(meter) - before
    finally:
        await rfb.aclose()
        await rfb.store.aclose()

    assert (checked.seq, checked.entries, checked.intact) == (CHAIN + 5, CHAIN + 5, True)
    assert incremental <= 6, "only the five entries past the verified point"
    assert walked >= CHAIN + 5
    assert whole.intact
    assert whole.model_dump(exclude={"checked_at"}) == checked.model_dump(exclude={"checked_at"})


async def test_an_incremental_check_finds_a_broken_tail(tmp_path: Path, meter: StoreMeter) -> None:
    settings = hosted_settings(tmp_path)
    settings.sqlite_path.parent.mkdir(parents=True)
    raw = SqliteStore(settings.sqlite_path, settings.cache_dir / "blobs")
    store = MeteredStore(raw, meter, "RFB")
    body = chained(20)
    await write_raw(raw, body)
    with timeutil.bind_clock(FixedClock(AT)), bind_tenant("RFB"):
        await audit.check_chain(store, whole=True)
        tampered = chained(1, after=body[-1])[0].model_copy(update={"note": "changed later"})
        await write_raw(raw, [tampered])
        head = await audit.check_chain(store)
    await store.aclose()
    assert head.intact is False
    assert head.problems == ["entry e000021: content does not match its hash"]
    assert audit.chain(store).verified_through_seq == 20, "the verified point does not move"


async def test_a_held_head_is_reused_when_the_runtime_restarts_on_the_same_store(
    tmp_path: Path, meter: StoreMeter
) -> None:
    rfb = await hosted_runtime(tmp_path, meter)
    with rfb.bound():
        for n in range(3):
            await audit.record(
                rfb.store, actor="system", action=AuditAction.CHAIN_CHECKED, note=f"{n}"
            )
        await rfb.checkpoint(force=True)
    held = audit.chain(rfb.store).head
    assert held is not None
    await rfb.aclose()

    data = rfb.settings.data_dir
    parts = HostedParts(
        tenant="RFB",
        store=rfb.store,
        source=FixtureSource(rfb_aircraft()),
        catalogue=load_volcanoes(data),
        airports=load_airports(data, min_runway_m=POLICY.alternates.min_runway_m.value),
        routes=ROUTES,
        policy=POLICY,
        own_schedule=None,
        llm_unavailable=None,
        fence=lambda: False,
    )
    again = await create_runtime(rfb.settings, hosted=parts)
    try:
        assert audit.chain(again.store).head == held, "kept as held, not restored as unwalked"
    finally:
        await again.aclose()
        await again.store.aclose()


async def test_a_cancelled_caller_never_leaves_an_append_out_of_the_head(
    tmp_path: Path, meter: StoreMeter
) -> None:
    rfb = await hosted_runtime(tmp_path, meter)
    try:
        with rfb.bound():
            await audit.record(rfb.store, actor="system", action=AuditAction.CHAIN_CHECKED)
            started = asyncio.Event()

            async def caller() -> Any:
                started.set()
                return await audit.record(
                    rfb.store, actor="system", action=AuditAction.CHAIN_CHECKED, note="cut"
                )

            task = asyncio.create_task(caller())
            await started.wait()
            await asyncio.sleep(0)
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            # the shielded append completes; the next one queues behind it on the store's lock
            await audit.record(rfb.store, actor="system", action=AuditAction.CHAIN_CHECKED)
            newest = await audit.newest_entry(rfb.store)
            problems = await audit.verify_chain(rfb.store)
            head = audit.chain(rfb.store).head
    finally:
        await rfb.aclose()
        await rfb.store.aclose()

    assert newest is not None
    assert head is not None
    assert newest.seq == 3
    assert (head.seq, head.sha256) == (newest.seq, newest.sha256)
    assert problems == []
    assert not any("another writer" in problem for problem in head.problems)
