"""The hosted airlines' registry (SPEC §3.6): one space per airline, runtimes restored at start
without a worker or a cache, the hosted pass on the wall clock, failure isolation and the
restart cap, the guard timeout, the pauses, reconfigure and a new policy without a restart,
pushes with no store read, the memory guard, the purge and the meter's persistence.

Most tests run a fake runtime (``FakeRuntime``); ``test_a_real_hosted_runtime_...`` runs H2's
``create_runtime(hosted=...)``."""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from tephra.agents.llm import UnavailableBackend
from tephra.feeds.routes import load_routes
from tephra.feeds.volcanoes import load_volcanoes
from tephra.hosted import keys, members, registry, tenants
from tephra.hosted.access import AccessCache
from tephra.hosted.models import HostedRefused
from tephra.hosted.registry import TenantRegistry
from tephra.models import AuditAction
from tephra.pipeline import create_runtime
from tephra.store import open_store
from tephra.store.base import Collection
from tephra.store.metered import MeteredStore, StoreMeter
from tephra.store.sqlite_store import SqliteStore
from tephra.util import timeutil
from tephra.util.scope import current_tenant
from tests.test_hosted_tenants import (
    OPERATOR,
    airline_account,
    airports,
    base_policy,
    demo_on_replay_clock,
    site,
    wall,
)

KEY = "AIzaTestKeyRFB0123456789abcdefghijKLMN"


@dataclass
class FakeRuntime:
    """What the registry uses of a hosted runtime; records what happened to it."""

    settings: Any
    parts: Any
    fail: bool = False
    sleep_s: float = 0.0
    ticks: list[tuple[datetime, str | None, bool]] = field(default_factory=list)
    workers: int = 0
    closed: bool = False
    reconfigured: list[tuple[Any, Any]] = field(default_factory=list)
    policies: list[Any] = field(default_factory=list)
    ledger: Any = None

    @property
    def hosted(self) -> str:
        return self.parts.tenant

    @property
    def store(self) -> Any:
        return self.parts.store

    async def tick(self, *, reason: str) -> None:
        assert reason == "hosted"
        self.ticks.append((timeutil.now(), current_tenant(), timeutil.clock_bound()))
        if self.sleep_s:
            await asyncio.sleep(self.sleep_s)
        if self.fail:
            raise RuntimeError("tick broke")

    def start_worker(self) -> None:
        self.workers += 1

    async def aclose(self) -> None:
        self.closed = True

    async def reconfigure(self, settings: Any, *, llm: Any = None) -> None:
        self.reconfigured.append((settings, llm))

    async def set_policy(self, policy: Any) -> None:
        self.policies.append(policy)

    async def budget_view(self) -> Any:
        return SimpleNamespace(models=[])


class Factory:
    def __init__(self) -> None:
        self.made: list[FakeRuntime] = []
        self.broken: set[str] = set()
        self.failing: set[str] = set()
        self.sleepy: set[str] = set()
        self.bindings: list[tuple[str | None, bool]] = []

    async def __call__(self, settings: Any, *, hosted: Any) -> FakeRuntime:
        self.bindings.append((current_tenant(), timeutil.clock_bound()))
        if hosted.tenant in self.broken:
            raise RuntimeError("could not restore")
        runtime = FakeRuntime(
            settings,
            hosted,
            fail=hosted.tenant in self.failing,
            sleep_s=1.0 if hosted.tenant in self.sleepy else 0.0,
        )
        self.made.append(runtime)
        return runtime

    def latest(self, icao: str) -> FakeRuntime:
        return [r for r in self.made if r.hosted == icao][-1]


@dataclass
class Site:
    registry: TenantRegistry
    factory: Factory
    clock: timeutil.FixedClock
    demo: Any

    @property
    def root(self) -> Any:
        return self.registry.root

    @property
    def meter(self) -> StoreMeter:
        return self.registry.meter


def build(tmp_path: Path, *, rss: int = 100, factory: Any = None, **overrides: Any) -> Site:
    settings = site(tmp_path, **overrides)
    meter = StoreMeter(blob_puts_cap=settings.hosted_blob_puts_cap)
    root = MeteredStore(open_store(settings), meter, "demo")
    demo = SimpleNamespace(
        policy=base_policy(), airports=airports(), catalogue=None, routes=None, retired=False
    )
    made = factory if factory is not None else Factory()
    clock = timeutil.FixedClock(wall())
    reg = TenantRegistry(
        settings,
        root,
        demo,  # type: ignore[arg-type]
        meter,
        AccessCache(),
        factory=made,
        source=SimpleNamespace(),
        clock=clock,
        rss_mb=lambda: rss,
    )
    return Site(reg, made, clock, demo)


async def hosted(s: Site, icao: str, state: str = "shadow") -> None:
    record, login = await airline_account(s.root, icao)
    _, member = await s.registry.set_up(record, login, "Ana Ops")
    if state == "setup":
        return
    await tenants.start(
        s.root,
        icao,
        region="java_bali",
        by=tenants.member_by(member),
        max_slots=3,
        space=s.registry.space(icao),
        at=wall(),
    )
    await s.registry.start(icao)


async def test_start_all_restores_running_airlines_without_a_worker(tmp_path: Path) -> None:
    s = build(tmp_path)
    await hosted(s, "RFB")
    await hosted(s, "RFC", "setup")
    await s.registry.aclose()
    again = build(tmp_path)
    await again.registry.start_all()
    assert [r.hosted for r in again.factory.made] == ["RFB"]
    assert again.factory.bindings == [("RFB", True)]
    rfb = again.registry.handle("RFB")
    rfc = again.registry.handle("RFC")
    assert rfb is not None
    assert rfc is not None
    assert rfb.runtime is again.factory.latest("RFB")
    assert rfc.runtime is None
    assert again.factory.latest("RFB").workers == 0
    assert rfb.space.store is again.factory.latest("RFB").store
    assert rfb.space.store._cache_on is False
    await again.registry.aclose()


async def test_the_first_pass_starts_workers_and_caches_and_every_pass_empties_them(
    tmp_path: Path,
) -> None:
    s = build(tmp_path)
    await hosted(s, "RFB")
    rfb = s.registry.handle("RFB")
    assert rfb is not None
    await s.registry.run_pass()
    store = rfb.space.store
    assert store._cache_on is True
    assert s.factory.latest("RFB").workers == 1
    epoch = store._epoch
    await s.registry.run_pass()
    assert store._epoch == epoch + 1
    assert s.factory.latest("RFB").workers == 1
    assert len(s.factory.latest("RFB").ticks) == 2
    await s.registry.aclose()


async def test_ticks_run_on_the_wall_clock_while_the_demo_replays(tmp_path: Path) -> None:
    s = build(tmp_path)
    await hosted(s, "RFB")
    await hosted(s, "RFC")
    with demo_on_replay_clock():
        await s.registry.run_pass()
    now = wall()
    for icao in ("RFB", "RFC"):
        ((at, tenant, bound),) = s.factory.latest(icao).ticks
        assert abs((at - now).total_seconds()) < 5
        assert (tenant, bound) == (icao, True)
    await s.registry.aclose()


async def test_a_failing_airline_never_stops_the_others_and_is_restarted_on_backoff(
    tmp_path: Path,
) -> None:
    s = build(tmp_path)
    s.factory.failing.add("RFB")
    await hosted(s, "RFB")
    await hosted(s, "RFC")
    for _ in range(3):
        await s.registry.run_pass()
    rfb = s.registry.handle("RFB")
    assert rfb is not None
    assert rfb.health.failures == 3
    assert rfb.restart_at == s.clock.now() + registry.BACKOFF[0]
    assert rfb.health.problem is not None
    assert "RuntimeError; TEPHRA restarts it at" in rfb.health.problem
    assert len(s.factory.latest("RFC").ticks) == 3
    first = s.factory.latest("RFB")
    s.clock.advance(timedelta(minutes=1, seconds=1))
    await s.registry.run_pass()
    assert first.closed is True
    assert s.factory.latest("RFB") is not first
    record = await tenants.get_tenant(s.root, "RFB")
    assert record is not None
    assert sum(record.restarts.values()) == 1
    await s.registry.aclose()


async def test_after_six_restarts_a_day_the_airline_stays_stopped(tmp_path: Path) -> None:
    s = build(tmp_path)
    s.factory.failing.add("RFB")
    await hosted(s, "RFB")
    for _ in range(tenants.MAX_RESTARTS):
        await tenants.note_restart(s.root, "RFB", at=s.clock.now())
    for _ in range(3):
        await s.registry.run_pass()
    s.clock.advance(timedelta(minutes=2))
    await s.registry.run_pass()
    rfb = s.registry.handle("RFB")
    assert rfb is not None
    assert rfb.gave_up is True
    assert rfb.runtime is None
    assert rfb.health.problem is not None
    assert "after 6 restarts today" in rfb.health.problem
    made = len(s.factory.made)
    s.clock.advance(timedelta(hours=1))
    await s.registry.run_pass()
    assert len(s.factory.made) == made
    await s.registry.aclose()


async def test_a_tick_past_its_guard_is_a_failure(tmp_path: Path) -> None:
    s = build(tmp_path)
    s.factory.sleepy.add("RFB")
    await hosted(s, "RFB")
    # a guard of 0.05 s (budget + 10), set after the runtime's settings were made
    s.registry.base = s.registry.base.model_copy(update={"hosted_tick_budget_s": -9.95})
    await s.registry.run_pass()
    rfb = s.registry.handle("RFB")
    assert rfb is not None
    assert rfb.health.failures == 1
    assert rfb.health.problem is not None
    assert "TimeoutError" in rfb.health.problem
    assert rfb.ticking is False
    await s.registry.aclose()


async def test_an_airline_over_its_allowance_pauses_alone(tmp_path: Path) -> None:
    s = build(tmp_path)
    await hosted(s, "RFB")
    await hosted(s, "RFC")
    allowance = s.meter.allowance(s.registry.base)["writes"]
    s.meter.count("RFB", "writes", allowance)
    await s.registry.run_pass()
    rfb, rfc = s.registry.handle("RFB"), s.registry.handle("RFC")
    assert rfb is not None
    assert rfc is not None
    assert s.factory.latest("RFB").ticks == []
    assert len(s.factory.latest("RFC").ticks) == 1
    assert (rfb.health.paused, rfb.health.paused_scope) == ("writes", "airline")
    line = s.registry.paused_line(rfb)
    assert line is not None
    assert (line.scope, line.reason) == ("airline", "writes")
    assert rfc.health.paused is None
    # the demo's visitors reading the whole cap pause no airline (H1)
    s.meter.count("demo", "reads", s.registry.base.hosted_reads_cap)
    await s.registry.run_pass()
    assert len(s.factory.latest("RFC").ticks) == 2
    assert rfc.health.paused is None
    # the airlines together reaching the cap pause every airline
    s.meter.count("RFB", "reads", s.registry.base.hosted_reads_cap)
    await s.registry.run_pass()
    assert len(s.factory.latest("RFC").ticks) == 2
    assert (rfc.health.paused, rfc.health.paused_scope) == ("reads", "site")
    await s.registry.aclose()


async def test_reconfigure_and_a_new_policy_reach_the_same_runtime(tmp_path: Path) -> None:
    s = build(tmp_path)
    await hosted(s, "RFB")
    runtime = s.factory.latest("RFB")
    space = s.registry.space("RFB")
    sealed = keys.seal("RFB", KEY, s.registry.base, by="Ana Ops#MB-1", at=wall())
    await tenants.set_key(s.root, "RFB", sealed, by="Ana Ops#MB-1", space=space, at=wall())
    await s.registry.reconfigure("RFB")
    settings, llm = runtime.reconfigured[-1]
    assert settings.gemini_api_key.get_secret_value() == KEY
    assert settings.session_secret == runtime.settings.session_secret
    assert llm is not None
    assert not isinstance(llm, UnavailableBackend)
    from tephra.airline.models import PolicyChange

    await tenants.set_policy_version(
        s.root,
        "RFB",
        [PolicyChange(name="exposure.vertical_margin_ft", value=4000, reason="SOP 4.2 says so.")],
        base_version=1,
        note=None,
        base_policy=base_policy(),
        by="Ana Ops#MB-1",
        space=space,
        at=wall(),
    )
    await s.registry.apply_policy("RFB")
    assert runtime.policies[-1].version == "RFB-2"
    assert runtime.policies[-1].exposure.vertical_margin_ft.value == 4000
    assert len(s.factory.made) == 1
    await s.registry.aclose()


async def test_without_a_key_the_runtime_is_told_why(tmp_path: Path) -> None:
    s = build(tmp_path)
    await hosted(s, "RFB")
    assert s.factory.latest("RFB").parts.llm_unavailable == "no model key is set"
    await s.registry.aclose()


async def test_push_keys_are_found_with_no_store_read(tmp_path: Path) -> None:
    s = build(tmp_path)
    await hosted(s, "RFB")
    made, key = await s.registry.create_key("RFB", "ops-feed-1", by="Ana Ops#MB-1")
    reads = sum(s.meter.day().reads.values())
    found = s.registry.push_key("RFB", key)
    assert found is not None
    assert found.id == made.id
    assert s.registry.push_key("RFC", key) is None
    assert s.registry.push_key("RFB", "tph_wrong") is None
    assert sum(s.meter.day().reads.values()) == reads
    _, rotated = await s.registry.rotate_key("RFB", made.id, by="Ana Ops#MB-1")
    assert s.registry.push_key("RFB", key) is None
    assert s.registry.push_key("RFB", rotated) is not None
    await tenants.suspend(
        s.root, "RFB", by=OPERATOR, reason="Hold.", space=s.registry.space("RFB"), at=wall()
    )
    await s.registry.stop("RFB", reason="suspended")
    assert s.registry.push_key("RFB", rotated) is None
    await s.registry.aclose()


async def test_at_most_ten_live_keys(tmp_path: Path) -> None:
    s = build(tmp_path)
    await hosted(s, "RFB", "setup")
    for n in range(registry.MAX_KEYS):
        await s.registry.create_key("RFB", f"feed-{n}", by="Ana Ops#MB-1")
    with pytest.raises(HostedRefused, match="too_many_keys"):
        await s.registry.create_key("RFB", "one more", by="Ana Ops#MB-1")
    await s.registry.aclose()


async def test_no_airline_starts_while_memory_is_full(tmp_path: Path) -> None:
    s = build(tmp_path, rss=900)
    await hosted(s, "RFB", "setup")
    with pytest.raises(HostedRefused) as refused:
        await s.registry.start("RFB")
    assert (refused.value.status, refused.value.code) == (409, "site_memory")
    handle = s.registry.handle("RFB")
    assert handle is not None
    card = await s.registry.go_live(handle)
    assert card.items[0].key == "feeds"
    await s.registry.aclose()


async def test_an_airline_that_cannot_start_says_so_and_is_retried(tmp_path: Path) -> None:
    s = build(tmp_path)
    s.factory.broken.add("RFB")
    await hosted(s, "RFB")
    rfb = s.registry.handle("RFB")
    assert rfb is not None
    assert rfb.runtime is None
    assert rfb.health.problem == (
        f"TEPHRA could not start for Ring of Fire Charter at {s.clock.now():%H:%M}Z: "
        "RuntimeError. TEPHRA retries every 10 minutes."
    )
    s.factory.broken.clear()
    await s.registry.run_pass()
    assert rfb.runtime is None
    s.clock.advance(timedelta(minutes=10))
    await s.registry.run_pass()
    assert rfb.runtime is s.factory.latest("RFB")
    assert rfb.health.problem is None
    await s.registry.aclose()


async def test_on_demand_hosting_ticks_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("K_SERVICE", "tephra")
    s = build(tmp_path, local_scheduler=True)
    await hosted(s, "RFB")
    assert s.registry.hosting == "on-demand"
    await s.registry.run_pass()
    assert s.factory.latest("RFB").ticks == []
    await s.registry.aclose()


async def test_the_meter_is_written_after_a_pass_unless_the_demo_retired(tmp_path: Path) -> None:
    s = build(tmp_path)
    await hosted(s, "RFB")
    s.demo.retired = True
    await s.registry.run_pass()
    day = s.meter.day().day.isoformat()
    assert await s.root.get(Collection.HOSTED_METER, day) is None
    s.demo.retired = False
    s.registry._passed = True
    await s.registry.run_pass()
    stored = await s.root.get(Collection.HOSTED_METER, day)
    assert stored is not None
    assert stored["reads"]["RFB"] > 0
    await s.registry.aclose()


async def test_the_header_and_the_record_come_from_memory(tmp_path: Path) -> None:
    s = build(tmp_path)
    await hosted(s, "RFB")
    await hosted(s, "RFC")
    rfb = s.registry.handle("RFB")
    assert rfb is not None
    found = await members.members_of(s.root, "RFB")
    header = await s.registry.header(rfb, found[0])
    assert header.state == "shadow"
    assert header.you.role == "ops_manager"
    assert [m.icao for m in header.memberships] == ["RFB"]
    assert header.chain.intact is True
    assert header.runtime.running is True
    assert header.runtime.updating is False
    assert header.started is not None
    assert header.started.by == "Ana Ops"  # the name only, as the page shows it
    record = await s.registry.record_view(
        rfb, before_seq=None, is_ops_manager=True, can_check=True, can_export=False
    )
    assert [e.action for e in record.entries] == [
        AuditAction.HOSTED_SHADOW,
        AuditAction.HOSTED_SETUP,
    ]
    assert record.next_before_seq is None
    assert record.can_export is False
    head = await s.registry.check_record(rfb, by="Ana Ops#MB-1")
    assert head.intact is True
    again = await s.registry.record_view(
        rfb, before_seq=None, is_ops_manager=True, can_check=True, can_export=True
    )
    assert again.entries[0].action == AuditAction.CHAIN_CHECKED
    assert again.head is not None
    assert again.head.verified_through_seq == 2
    await s.registry.aclose()


async def test_a_whole_walk_past_the_allowance_is_refused(tmp_path: Path) -> None:
    s = build(tmp_path)
    await hosted(s, "RFB")
    rfb = s.registry.handle("RFB")
    assert rfb is not None
    s.meter.count("RFB", "reads", s.meter.allowance(s.registry.base)["reads"])
    with pytest.raises(HostedRefused) as refused:
        await s.registry.check_record(rfb, by="Ana Ops#MB-1")
    assert (refused.value.status, refused.value.code) == (503, "airline_paused")
    await s.registry.aclose()


async def test_the_admin_list_counts_onboarding_and_rows_every_submitted_airline(
    tmp_path: Path,
) -> None:
    s = build(tmp_path)
    await hosted(s, "RFB")
    await hosted(s, "RFC", "setup")
    await airline_account(s.root, "RFD", hosting=False)
    await airline_account(s.root, "RFE", verified=False)
    from tephra.airline import accounts

    await accounts.create_account(
        s.root,
        email="draft@rfz.example",
        password_hash="scrypt$x",
        recovery_sha256="0" * 64,
        at=wall(),
    )
    listing = await s.registry.admin_list()
    rows = {row.icao: row for row in listing.rows}
    assert listing.onboarding == 1
    assert listing.to_verify == 2  # RFE pending and RFD verified on the Desk, not yet hosted
    assert (listing.slots.used, listing.slots.max) == (1, 3)
    assert (rows["RFB"].status, rows["RFB"].status_label) == ("shadow", "Shadow")
    assert (rows["RFC"].status, rows["RFC"].checklist) == ("verified", "0/4")
    assert (rows["RFD"].status_label, rows["RFD"].hosting) == ("Verified (Desk)", "desk")
    assert (rows["RFE"].status, rows["RFE"].hosting) == ("pending", None)
    assert listing.meter.allowance.reads == 8000
    assert "RFB" in listing.meter.by_namespace
    await s.registry.aclose()


async def test_the_purge_keeps_to_its_pace_and_leaves_a_tombstone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    deleted: list[tuple[str, int]] = []
    left = {"n": 1200}

    async def delete_some(self: MeteredStore, collection: str, *, limit: int) -> int:
        if collection != Collection.ADVISORIES:
            return 0
        n = min(limit, left["n"])
        left["n"] -= n
        self.meter.count(self.namespace, "deletes", n)
        deleted.append((collection, n))
        return n

    monkeypatch.setattr(MeteredStore, "delete_some", delete_some, raising=False)
    s = build(tmp_path)
    await hosted(s, "RFB")
    at = s.clock.now() - timedelta(days=8)
    space = s.registry.space("RFB")
    await tenants.suspend(s.root, "RFB", by=OPERATOR, reason="Hold.", space=space, at=at)
    await s.registry.stop("RFB", reason="suspended")
    await tenants.mark_deleting(s.root, "RFB", by=OPERATOR, at=s.clock.now())
    await s.registry.reload("RFB")
    await s.registry.run_pass()
    assert deleted == [(Collection.ADVISORIES, 500)]
    await s.registry.run_pass()
    assert len(deleted) == 1
    s.clock.advance(registry.PURGE_GAP)
    s.meter.count("RFB", "deletes", s.meter.allowance(s.registry.base)["deletes"] - 600)
    await s.registry.run_pass()
    assert deleted[-1] == (Collection.ADVISORIES, 100)
    s.registry.meter = StoreMeter(blob_puts_cap=4000)  # the next Pacific day
    for _ in range(4):
        s.clock.advance(registry.PURGE_GAP)
        await s.registry.run_pass()
    record = await tenants.get_tenant(s.root, "RFB")
    assert record is not None
    assert record.state == "deleted"
    assert s.registry.handle("RFB") is None
    assert await members.members_of(s.root, "RFB") == []
    await s.registry.aclose()


async def test_the_purge_empties_the_airlines_own_store_and_leaves_a_tombstone(
    tmp_path: Path,
) -> None:
    s = build(tmp_path)
    await hosted(s, "RFB")
    await hosted(s, "RFC")
    space = s.registry.space("RFB")
    with space.bound():
        assert await space.store.count(Collection.AUDIT) > 0
    store = space.store
    at = s.clock.now() - timedelta(days=8)
    await tenants.suspend(s.root, "RFB", by=OPERATOR, reason="Hold.", space=space, at=at)
    await s.registry.stop("RFB", reason="suspended")
    await tenants.mark_deleting(s.root, "RFB", by=OPERATOR, at=s.clock.now())
    await s.registry.reload("RFB")
    for _ in range(3):
        await s.registry.run_pass()
        s.clock.advance(registry.PURGE_GAP)
    record = await tenants.get_tenant(s.root, "RFB")
    assert record is not None
    assert record.state == "deleted"
    # the tombstone: code, name, times and the deletion stamp; nothing about the people
    kept = record.model_dump(mode="json", exclude_defaults=True)
    assert set(kept) <= {
        "icao",
        "airline_id",
        "name",
        "version",
        "state",
        "state_since",
        "created",
        "deleted",
        "policy_version",
        "ops_managers",
    }
    assert record.created.by == tenants.TOMBSTONE_BY
    assert record.ops_managers == []
    assert record.sra is None
    assert record.suspend_reason is None
    assert "#MB-" not in json.dumps(kept)
    inner = cast(SqliteStore, store.inner)
    rows = inner._call(lambda conn: conn.execute("SELECT COUNT(*) FROM docs").fetchone())
    assert rows[0] == 0
    rfc = s.registry.space("RFC")
    with rfc.bound():
        assert await rfc.store.count(Collection.AUDIT) > 0
    await s.registry.aclose()


async def test_a_real_hosted_runtime_runs_on_the_airlines_own_store(tmp_path: Path) -> None:
    settings = site(tmp_path)
    demo = SimpleNamespace(
        policy=base_policy(),
        airports=airports(),
        catalogue=load_volcanoes(settings.data_dir),
        routes=load_routes(settings.data_dir),
        retired=False,
    )
    s = build(tmp_path, factory=create_runtime)
    s.registry.demo = demo  # type: ignore[assignment]
    await hosted(s, "RFB")
    rfb = s.registry.handle("RFB")
    assert rfb is not None
    runtime = rfb.runtime
    assert runtime is not None
    assert runtime.hosted == "RFB"
    assert runtime.store is rfb.space.store
    assert isinstance(runtime.llm, UnavailableBackend)
    assert runtime.settings.hosted_stage == "shadow"
    assert runtime.policy.version == "RFB-1"
    assert runtime.retired is False
    demo.retired = True
    assert runtime.retired is True
    demo.retired = False
    await s.registry.aclose()
    assert rfb.space.store.inner is not None


def test_process_memory_is_read() -> None:
    assert registry.process_rss_mb() > 10


async def test_after_a_restart_a_real_runtime_reads_only_the_tail_of_its_record(
    tmp_path: Path,
) -> None:
    settings = site(tmp_path)

    def real_demo() -> SimpleNamespace:
        return SimpleNamespace(
            policy=base_policy(),
            airports=airports(),
            catalogue=load_volcanoes(settings.data_dir),
            routes=load_routes(settings.data_dir),
            retired=False,
        )

    first = build(tmp_path, factory=create_runtime)
    first.registry.demo = real_demo()  # type: ignore[assignment]
    await hosted(first, "RFB")
    space = first.registry.space("RFB")
    with space.bound():
        for n in range(300):
            await audit_record(space.store, n)
    await first.registry.aclose()
    again = build(tmp_path, factory=create_runtime)
    again.registry.demo = real_demo()  # type: ignore[assignment]
    before = again.meter.day().reads.get("RFB", 0)
    await again.registry.start_all()
    rfb = again.registry.handle("RFB")
    assert rfb is not None
    assert rfb.runtime is not None
    reads = again.meter.day().reads.get("RFB", 0) - before
    assert reads < 100, f"{reads} reads to restore a 302-entry record"
    await again.registry.aclose()


async def audit_record(store: Any, n: int) -> None:
    from tephra.desk import audit

    await audit.record(store, actor="system", action=AuditAction.CONNECTION_CREATED, note=str(n))


async def test_a_purge_that_fails_never_stops_the_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build(tmp_path)
    await hosted(s, "RFB")
    await hosted(s, "RFC")
    space = s.registry.space("RFB")
    at = s.clock.now() - timedelta(days=8)
    await tenants.suspend(s.root, "RFB", by=OPERATOR, reason="Hold.", space=space, at=at)
    await s.registry.stop("RFB", reason="suspended")
    await tenants.mark_deleting(s.root, "RFB", by=OPERATOR, at=s.clock.now())
    await s.registry.reload("RFB")

    async def broken(self: MeteredStore, collection: str, *, limit: int) -> int:
        raise OSError("the store is unreachable")

    monkeypatch.setattr(MeteredStore, "delete_some", broken)
    await s.registry.run_pass()
    assert s.registry.handle("RFB").record.state == "deleting"
    assert len(s.factory.latest("RFC").ticks) == 1
    assert s.registry.last_pass is not None
    await s.registry.aclose()
