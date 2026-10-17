"""The store meter (counts per namespace and Pacific day, allowances, persistence), the
airline stores' cache, blob dedupe and the monthly cap, and the fail-closed binding."""

import weakref
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tephra.config import Settings
from tephra.models import AuditAction, AuditEntry
from tephra.store import metered
from tephra.store.base import Collection, Where
from tephra.store.metered import (
    CACHE_MAX_ENTRIES,
    TENANT_CACHED,
    BlobAllowanceUsed,
    MeterDay,
    MeteredStore,
    StoreMeter,
)
from tephra.store.sqlite_store import SqliteStore
from tephra.util import timeutil
from tephra.util.scope import bind_tenant

# 06:59Z on 17 Oct is 23:59 on 16 Oct in Los Angeles (PDT, UTC-7).
LATE_PACIFIC = datetime(2026, 10, 17, 6, 59, tzinfo=UTC)
PNG = b"\x89PNG\r\n\x1a\nfake"


def settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **overrides)


@contextmanager
def airline(icao: str = "RFB") -> Iterator[None]:
    with bind_tenant(icao), timeutil.bind_clock(timeutil.SystemClock()):
        yield


class Backend(SqliteStore):
    """SQLite that remembers the calls reaching it, to see what the cache answers."""

    def __init__(self, path: Path, blob_dir: Path) -> None:
        super().__init__(path, blob_dir)
        self.calls: list[str] = []

    async def get(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        self.calls.append(f"get {collection}")
        return await super().get(collection, doc_id)

    async def query(self, collection: str, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(f"query {collection}")
        return await super().query(collection, *args, **kwargs)

    async def put_blob(self, key: str, data: bytes, content_type: str) -> None:
        self.calls.append(f"put_blob {key}")
        await super().put_blob(key, data, content_type)


@pytest.fixture
def clock() -> timeutil.FixedClock:
    return timeutil.FixedClock(LATE_PACIFIC)


@pytest.fixture
def meter(clock: timeutil.FixedClock) -> StoreMeter:
    return StoreMeter(blob_puts_cap=2, clock=clock)


@pytest.fixture
async def demo(tmp_path: Path, meter: StoreMeter) -> AsyncIterator[MeteredStore]:
    store = MeteredStore(Backend(tmp_path / "root.sqlite3", tmp_path / "blobs"), meter, "demo")
    yield store
    await store.aclose()


@pytest.fixture
async def rfb(tmp_path: Path, meter: StoreMeter) -> AsyncIterator[MeteredStore]:
    store = MeteredStore(
        Backend(tmp_path / "RFB.sqlite3", tmp_path / "blobs"),
        meter,
        "RFB",
        cache=TENANT_CACHED,
    )
    yield store
    await store.aclose()


# --- counting -----------------------------------------------------------------------------


async def test_every_operation_is_counted_for_its_namespace(
    demo: MeteredStore, rfb: MeteredStore, meter: StoreMeter
) -> None:
    await demo.put(Collection.PLANS, "p1", {"id": "p1", "n": 1})
    await demo.put(Collection.PLANS, "p2", {"id": "p2", "n": 2})
    await demo.get(Collection.PLANS, "p1")
    await demo.get(Collection.PLANS, "missing")
    await demo.query(Collection.PLANS, [Where("n", ">", 0)])
    await demo.query(Collection.PLANS, [Where("n", ">", 9)])
    await demo.count(Collection.PLANS)
    await demo.update(Collection.RUNTIME, "state", lambda _: {"mode": "LIVE"})
    assert await demo.compare_and_set_advisory("a", 0, {"id": "a", "version": 1})
    assert not await demo.compare_and_set_advisory("a", 0, {"id": "a", "version": 1})
    await demo.append_audit(
        AuditEntry(id="e1", at=LATE_PACIFIC, actor="system", action=AuditAction.APPROVED)
    )
    await demo.page(Collection.AUDIT, field="seq", before=None, limit=5)
    await demo.delete(Collection.PLANS, "p2")
    with airline():
        await rfb.put(Collection.PLANS, "x", {"id": "x"})
    day = meter.day()
    # get 2 + query 2 (+1 for the empty one) + count 1 + update 1 + CAS 2 + page 1 (no seq)
    assert day.reads == {"demo": 10}
    assert day.writes == {"demo": 5, "RFB": 1}
    assert day.deletes == {"demo": 1}
    assert day.day == date(2026, 10, 16)


async def test_the_pacific_day_rolls_at_midnight_los_angeles(
    demo: MeteredStore, meter: StoreMeter, clock: timeutil.FixedClock
) -> None:
    await demo.put(Collection.PLANS, "p", {"id": "p"})
    meter.count("RFB", "blob_puts", 1)
    assert meter.day().writes == {"demo": 1}
    clock.advance(timedelta(minutes=1))
    rolled = meter.day()
    assert rolled.day == date(2026, 10, 17)
    assert rolled.writes == {}
    assert rolled.blob_puts == 1  # blob uploads count by calendar month
    clock.set(datetime(2026, 11, 1, 0, 30, tzinfo=UTC))
    assert meter.day().blob_month == "2026-11"
    assert meter.day().blob_puts == 0


def test_each_airline_has_its_own_allowance_and_the_demo_none(meter: StoreMeter) -> None:
    caps = settings(hosted_writes_cap=100, hosted_tenant_share=0.6, hosted_max_tenants=3)
    assert meter.allowance(caps)["writes"] == 20
    assert meter.allowance(settings())["reads"] == 8000
    assert meter.allowance(settings())["writes"] == 3200
    meter.count("RFB", "writes", 19)
    assert meter.over("RFB", caps) is None
    meter.count("RFB", "writes", 1)
    assert meter.over("RFB", caps) == "writes"
    assert meter.over("RFC", caps) is None
    meter.count("demo", "writes", 500)
    assert meter.over("demo", caps) is None
    assert meter.site_over(caps) is None  # the demo's own use never pauses an airline
    meter.count("RFC", "writes", 79)
    assert meter.site_over(caps) is None
    meter.count("RFC", "writes", 1)
    assert meter.site_over(caps) == "writes"  # the airlines together at the site's cap
    assert meter.allowance(settings(hosted_max_tenants=0)) == {
        "reads": 0,
        "writes": 0,
        "deletes": 0,
    }


def test_would_exceed_checks_the_airline_and_the_airlines_site_total(meter: StoreMeter) -> None:
    caps = settings(hosted_reads_cap=1000, hosted_tenant_share=0.6, hosted_max_tenants=3)
    meter.count("RFB", "reads", 150)
    assert not meter.would_exceed("RFB", caps, 50)
    assert meter.would_exceed("RFB", caps, 51)
    assert not meter.would_exceed("demo", caps, 800)
    meter.count("demo", "reads", 5000)  # the demo's visitors: never counted against airlines
    assert not meter.would_exceed("RFC", caps, 200)
    meter.count("RFC", "reads", 200)
    meter.count("RFD", "reads", 600)
    assert meter.would_exceed("demo", caps, 51)  # 950 of the airlines' 1000
    assert meter.would_exceed("RFE", caps, 51)


def test_an_airline_s_reads_stop_at_its_even_part_of_the_site_cap(meter: StoreMeter) -> None:
    caps = settings(hosted_reads_cap=900, hosted_tenant_share=0.6, hosted_max_tenants=3)
    assert meter.ceiling(caps) == 300
    assert meter.allowance(caps)["reads"] == 180  # ticks and pushes pause first
    meter.count("RFB", "reads", 299)
    assert not meter.reads_spent("RFB", caps)
    meter.count("RFB", "reads", 1)
    assert meter.reads_spent("RFB", caps)
    assert not meter.reads_spent("RFC", caps)
    meter.count("demo", "reads", 10_000)
    assert not meter.reads_spent("demo", caps)
    assert meter.ceiling(settings(hosted_max_tenants=0)) == 0


async def test_a_member_s_root_store_use_is_charged_to_their_airline(
    demo: MeteredStore, meter: StoreMeter
) -> None:
    """Inside an airline request, once the caller is a member (``Charge.icao`` set), what the
    root store reads is that airline's; before that, and outside, it is the demo's (H1)."""
    from tephra.util.scope import bind_charge

    await demo.put(Collection.PLANS, "p", {"id": "p"})
    await demo.get(Collection.PLANS, "p")
    with bind_charge() as charge:
        await demo.get(Collection.PLANS, "p")
        charge.icao = "RFB"
        await demo.get(Collection.PLANS, "p")
        await demo.get(Collection.PLANS, "p")
    await demo.get(Collection.PLANS, "p")
    assert meter.day().reads == {"demo": 3, "RFB": 2}


# --- persistence --------------------------------------------------------------------------


async def test_persist_merges_by_max_and_never_lowers_a_count(
    demo: MeteredStore, clock: timeutil.FixedClock
) -> None:
    first = StoreMeter(blob_puts_cap=10, clock=clock)
    second = StoreMeter(blob_puts_cap=10, clock=clock)
    first.count("demo", "reads", 500)
    first.count("RFB", "writes", 3)
    second.count("demo", "reads", 300)
    second.count("RFB", "writes", 7)
    second.count("RFC", "blob_puts", 4)
    assert not await first.persist(demo, allowed=False)
    assert await demo.get(Collection.HOSTED_METER, "2026-10-16") is None
    assert await first.persist(demo, allowed=True)
    assert await second.persist(demo, allowed=True)
    stored = MeterDay.model_validate(await demo.get(Collection.HOSTED_METER, "2026-10-16"))
    assert stored.reads["demo"] >= 500
    assert stored.writes["RFB"] == 7
    assert stored.blob_puts == 4
    assert second.day().reads["demo"] >= 500  # the merged counts are held
    assert await first.persist(demo, allowed=True, force=True)
    again = MeterDay.model_validate(await demo.get(Collection.HOSTED_METER, "2026-10-16"))
    assert again.writes["RFB"] == 7
    assert again.reads["demo"] >= stored.reads["demo"]


async def test_persist_runs_at_most_every_ten_minutes(
    demo: MeteredStore, meter: StoreMeter, clock: timeutil.FixedClock
) -> None:
    assert await meter.persist(demo, allowed=True)
    clock.advance(timedelta(minutes=9))
    assert not await meter.persist(demo, allowed=True)
    clock.advance(timedelta(minutes=1))
    assert await meter.persist(demo, allowed=True)


async def test_restore_takes_todays_persisted_counts(
    demo: MeteredStore, clock: timeutil.FixedClock
) -> None:
    old = StoreMeter(blob_puts_cap=10, clock=clock)
    old.count("RFB", "deletes", 42)
    await old.persist(demo, allowed=True)
    new = StoreMeter(blob_puts_cap=10, clock=clock)
    await new.restore(demo)
    assert new.day().deletes["RFB"] == 42
    clock.advance(timedelta(days=1))
    fresh = StoreMeter(blob_puts_cap=10, clock=clock)
    await fresh.restore(demo)
    assert fresh.day().deletes == {}


# --- blobs --------------------------------------------------------------------------------


async def test_blobs_are_written_once_and_airline_uploads_stop_at_the_monthly_cap(
    demo: MeteredStore, rfb: MeteredStore, meter: StoreMeter
) -> None:
    backend = rfb.inner
    assert isinstance(backend, Backend)
    await demo.put_blob("frames/shared.png", PNG, "image/png")
    with airline():
        await rfb.put_blob("frames/shared.png", PNG, "image/png")  # the demo stored it
        assert backend.calls == []
        await rfb.put_blob("frames/a.png", PNG, "image/png")
        await rfb.put_blob("frames/a.png", PNG, "image/png")
        await rfb.put_blob("frames/b.png", PNG, "image/png")
        assert meter.day().blob_puts == 2
        with pytest.raises(BlobAllowanceUsed, match="Satellite frames paused"):
            await rfb.put_blob("frames/c.png", PNG, "image/png")
        assert await rfb.get_blob("frames/c.png") is None
        await rfb.put_blob("frames/a.png", PNG, "image/png")  # already stored: no upload
    assert backend.calls == ["put_blob frames/a.png", "put_blob frames/b.png"]
    assert meter.blobs_written == {"frames/shared.png", "frames/a.png", "frames/b.png"}
    await demo.put_blob("frames/d.png", PNG, "image/png")  # the demo is not capped
    assert meter.day().blob_puts == 2


# --- cache --------------------------------------------------------------------------------


async def test_the_cache_is_off_until_enabled_and_then_a_repeat_costs_no_read(
    rfb: MeteredStore, meter: StoreMeter
) -> None:
    backend = rfb.inner
    assert isinstance(backend, Backend)
    with airline():
        await rfb.put(Collection.ADVISORIES, "a", {"id": "a", "status": "DRAFT"})
        await rfb.query(Collection.ADVISORIES, [Where("status", "==", "DRAFT")])
        await rfb.query(Collection.ADVISORIES, [Where("status", "==", "DRAFT")])
        assert backend.calls.count("query advisories") == 2
        rfb.enable_cache()
        reads = meter.day().reads["RFB"]
        await rfb.query(Collection.ADVISORIES, [Where("status", "==", "DRAFT")])
        await rfb.query(Collection.ADVISORIES, [Where("status", "==", "DRAFT")])
        await rfb.get(Collection.ADVISORIES, "a")
        await rfb.get(Collection.ADVISORIES, "a")
        assert backend.calls.count("query advisories") == 3
        assert backend.calls.count("get advisories") == 1
        assert meter.day().reads["RFB"] == reads + 2
        await rfb.query(Collection.PLANS)  # not a cached collection
        await rfb.query(Collection.PLANS)
        assert backend.calls.count("query plans") == 2
        rfb.clear_cache()
        await rfb.get(Collection.ADVISORIES, "a")
        assert backend.calls.count("get advisories") == 2


async def test_cached_answers_are_copies(rfb: MeteredStore) -> None:
    with airline():
        rfb.enable_cache()
        await rfb.put(Collection.ADVISORIES, "a", {"id": "a", "tags": ["x"]})
        first = await rfb.get(Collection.ADVISORIES, "a")
        assert first is not None
        first["tags"].append("changed")
        assert await rfb.get(Collection.ADVISORIES, "a") == {"id": "a", "tags": ["x"]}
        listed = await rfb.list_docs(Collection.ADVISORIES)
        listed[0]["id"] = "changed"
        assert (await rfb.list_docs(Collection.ADVISORIES))[0]["id"] == "a"


@pytest.mark.parametrize("write", ["put", "delete", "update", "cas", "audit_untouched"])
async def test_every_write_empties_its_collection(rfb: MeteredStore, write: str) -> None:
    backend = rfb.inner
    assert isinstance(backend, Backend)
    with airline():
        rfb.enable_cache()
        await rfb.compare_and_set_advisory("a", 0, {"id": "a", "version": 1})
        await rfb.put(Collection.CONNECTIONS, "c", {"id": "c"})
        assert await rfb.get(Collection.ADVISORIES, "a") == {"id": "a", "version": 1}
        await rfb.get(Collection.CONNECTIONS, "c")
        match write:
            case "put":
                await rfb.put(Collection.ADVISORIES, "a", {"id": "a", "version": 9})
                expected: dict[str, Any] | None = {"id": "a", "version": 9}
            case "delete":
                await rfb.delete(Collection.ADVISORIES, "a")
                expected = None
            case "update":
                await rfb.update(Collection.ADVISORIES, "a", lambda doc: {**(doc or {}), "x": 1})
                expected = {"id": "a", "version": 1, "x": 1}
            case "cas":
                await rfb.compare_and_set_advisory("a", 1, {"id": "a", "version": 2})
                expected = {"id": "a", "version": 2}
            case _:
                await rfb.append_audit(
                    AuditEntry(id="e", at=LATE_PACIFIC, actor="system", action=AuditAction.ASKED)
                )
                expected = {"id": "a", "version": 1}
        assert await rfb.get(Collection.ADVISORIES, "a") == expected
        await rfb.get(Collection.CONNECTIONS, "c")
        assert backend.calls.count("get connections") == 1  # another collection kept its entry
        assert backend.calls.count("get advisories") == (1 if write == "audit_untouched" else 2)


async def test_the_cache_holds_at_most_256_entries_for_120_seconds(
    rfb: MeteredStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = rfb.inner
    assert isinstance(backend, Backend)
    now = [1000.0]
    monkeypatch.setattr(metered.time, "monotonic", lambda: now[0])
    with airline():
        rfb.enable_cache()
        for n in range(CACHE_MAX_ENTRIES + 1):
            await rfb.get(Collection.ADVISORIES, f"a{n}")
        assert len(rfb._entries) == CACHE_MAX_ENTRIES
        await rfb.get(Collection.ADVISORIES, "a0")  # evicted first, read again
        assert backend.calls.count("get advisories") == CACHE_MAX_ENTRIES + 2
        await rfb.get(Collection.ADVISORIES, "a5")
        assert backend.calls.count("get advisories") == CACHE_MAX_ENTRIES + 2
        now[0] += 121
        await rfb.get(Collection.ADVISORIES, "a5")
        assert backend.calls.count("get advisories") == CACHE_MAX_ENTRIES + 3


# --- binding and identity -----------------------------------------------------------------


async def test_an_airline_store_fails_closed_outside_its_binding(rfb: MeteredStore) -> None:
    with pytest.raises(RuntimeError, match="outside its binding"):
        await rfb.get(Collection.PLANS, "x")
    outside = pytest.raises(RuntimeError, match="outside its binding")
    with bind_tenant("RFC"), timeutil.bind_clock(timeutil.SystemClock()), outside:
        await rfb.put(Collection.PLANS, "x", {})
    with bind_tenant("RFB"), pytest.raises(RuntimeError, match="outside its binding"):
        await rfb.query(Collection.PLANS)  # no wall clock bound
    with timeutil.bind_clock(timeutil.SystemClock()), pytest.raises(RuntimeError, match="outside"):
        await rfb.put_blob("frames/x.png", PNG, "image/png")
    with airline():
        assert await rfb.get(Collection.PLANS, "x") is None


async def test_the_demo_store_needs_no_binding_and_is_never_cached(
    tmp_path: Path, meter: StoreMeter
) -> None:
    with pytest.raises(ValueError, match="never cached"):
        MeteredStore(
            SqliteStore(tmp_path / "d.sqlite3", tmp_path),
            meter,
            "demo",
            cache=frozenset({Collection.ADVISORIES}),
        )
    with pytest.raises(ValueError, match="namespace"):
        MeteredStore(SqliteStore(tmp_path / "x.sqlite3", tmp_path), meter, "rfb")


async def test_one_wrapper_per_backend_and_identity_semantics(
    tmp_path: Path, rfb: MeteredStore, meter: StoreMeter
) -> None:
    with pytest.raises(ValueError, match="one store object per namespace"):
        MeteredStore(rfb.inner, meter, "RFB")
    other = MeteredStore(SqliteStore(tmp_path / "o.sqlite3", tmp_path), meter, "RFB")
    assert other != rfb
    assert hash(rfb) == object.__hash__(rfb)
    locks: weakref.WeakKeyDictionary[Any, int] = weakref.WeakKeyDictionary()
    locks[rfb] = 1
    locks[other] = 2
    assert locks[rfb] == 1
    assert weakref.ref(rfb)() is rfb
    await other.aclose()


async def test_the_purge_is_counted_for_the_airline_and_refused_on_the_demo(
    demo: MeteredStore, rfb: MeteredStore, meter: StoreMeter
) -> None:
    with airline():
        for n in range(3):
            await rfb.put(Collection.ADVISORIES, f"a{n}", {"id": f"a{n}"})
        rfb.enable_cache()
        assert len(await rfb.query(Collection.ADVISORIES)) == 3
        before = meter.day().deletes.get("RFB", 0)
        assert await rfb.delete_some(Collection.ADVISORIES, limit=2) == 2
        assert meter.day().deletes["RFB"] == before + 2
        assert len(await rfb.query(Collection.ADVISORIES)) == 1  # the cache was emptied
    with pytest.raises(RuntimeError, match="outside"):
        await rfb.delete_some(Collection.ADVISORIES, limit=1)
    with pytest.raises(RuntimeError, match="never purged"):
        await demo.delete_some(Collection.ADVISORIES, limit=1)
