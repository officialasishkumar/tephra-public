"""The hosted airlines of this process: one space and at most one runtime per airline, and the
hosted pass that ticks them (SPEC §3.6).

- **One store object per namespace** (F6): each airline's :class:`TenantSpace` opens its store
  once, wrapped in the meter with the airline's cache; the runtime is given that same object
  and never closes it. The registry closes it on suspend, delete or shutdown.
- **The hosted pass** (``kick``, never awaited by a request): on this instance's first pass the
  caches and AI workers start; every pass empties the caches first. At the site's caps every
  airline pauses; an airline past its own daily allowance pauses alone; the others tick
  concurrently, each under a guard of ``hosted_tick_budget_s + 10`` seconds. Three failures in
  a row restart the airline's runtime after 1, 5, then 15 minutes, at most six times a Pacific
  day; then it stays stopped and says so. Nothing stands in for the work a pause or a failure
  stops.
- **Wall clock**: every airline's work runs inside its space's binding; the registry's own
  times are wall-clock times.
- **After a deploy** (``start_all``) runtimes are restored one at a time (no AI worker, no
  cache, no full audit walk); one that fails to start keeps its state and is retried every
  10 minutes.
- **Pushes** find their key in memory (``push_key``), rebuilt on every create, rotate and
  revoke: no store read.
"""

import asyncio
import logging
import os
import resource
import sys
from collections.abc import Awaitable, Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Final, Literal, Protocol, cast

from pydantic import Field

from tephra.agents.llm import backend_for
from tephra.agents.quota import day_bounds
from tephra.airline import accounts
from tephra.airline.models import AirlineAnswers, AirlineLogin, AirlineRecord
from tephra.config import Settings
from tephra.desk import audit
from tephra.desk.connections import (
    KeyIndex,
    create_connection,
    list_connections,
    revoke_connection,
    rotate_connection,
)
from tephra.feeds.airports import AirportCatalogue, load_airports
from tephra.hosted import members as hosted_members
from tephra.hosted import tenants
from tephra.hosted.access import AccessCache, effective
from tephra.hosted.feeds import ConnectionStats, FeedStats, Section
from tephra.hosted.golive import FEEDS_FRESH, checklist
from tephra.hosted.models import (
    RUNNING,
    STATE_WORDS,
    AdminAi,
    AdminFeeds,
    AdminList,
    AdminMeter,
    AdminRow,
    BlobPuts,
    GoLive,
    HostedRefused,
    LastPass,
    Member,
    Membership,
    MeterCounts,
    PausedLine,
    ProcessLine,
    RecordTab,
    Slots,
    TenantHeader,
    TenantRecord,
)
from tephra.hosted.policy import get_version, tenant_policy
from tephra.hosted.settings_for import model_key, tenant_settings
from tephra.models import (
    AdvisoryStatus,
    AuditAction,
    ChainHead,
    Connection,
    OperatorPolicy,
    TephraModel,
    UtcDatetime,
)
from tephra.pipeline import Runtime, create_runtime
from tephra.store import open_store
from tephra.store.base import Collection, Store, Where
from tephra.store.metered import TENANT_CACHED, MeteredStore, OpKind, StoreMeter
from tephra.util import timeutil
from tephra.util.scope import bind_tenant

__all__ = [
    "BACKOFF",
    "MAX_KEYS",
    "PURGE_PER_MINUTE",
    "START_TIMEOUT_S",
    "RuntimeHealth",
    "TenantHandle",
    "TenantRegistry",
    "TenantSpace",
    "process_rss_mb",
]

logger = logging.getLogger(__name__)

BACKOFF: Final[tuple[timedelta, ...]] = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
)
FAILURES_BEFORE_RESTART: Final = 3
START_TIMEOUT_S: Final = 60.0
START_RETRY: Final = timedelta(minutes=10)
PURGE_PER_MINUTE: Final = 500
PURGE_GAP: Final = timedelta(minutes=1)
MAX_KEYS: Final = 10
ADMIN_ROWS: Final = 200
"""Submitted airlines the console lists, newest first (a read each per load)."""
ROOT_ONLY: Final = frozenset(
    {
        Collection.HOSTED_TENANTS,
        Collection.HOSTED_MEMBERS,
        Collection.HOSTED_INVITES,
        Collection.HOSTED_SLOTS,
        Collection.HOSTED_METER,
        Collection.OPERATORS,
        Collection.OPERATOR_INVITES,
        Collection.AIRLINES,
        Collection.AIRLINE_LOGINS,
    }
)
"""Collections that live only at the root: an airline's purge never touches them."""


def process_rss_mb() -> int:
    """This process's resident memory. Linux (Cloud Run) reads it now; elsewhere the peak
    stands in, which only ever refuses a start sooner."""
    try:
        with open("/proc/self/statm", encoding="ascii") as statm:
            pages = int(statm.read().split()[1])
        return pages * os.sysconf("SC_PAGE_SIZE") // 2**20
    except (OSError, ValueError, IndexError):
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(peak // 2**20 if sys.platform == "darwin" else peak // 2**10)


class RuntimeHealth(TephraModel):
    running: bool = False
    last_tick_wall_at: UtcDatetime | None = None
    failures: int = Field(default=0, description="Failed ticks in a row")
    problem: str | None = Field(
        default=None, description="e.g. 'stopped at 14:02Z: TimeoutError; TEPHRA restarts it…'"
    )
    paused: OpKind | None = None
    paused_scope: Literal["airline", "site"] | None = None


class _Purgeable(Protocol):
    async def delete_some(self, collection: str, *, limit: int) -> int: ...


@dataclass(eq=False)
class TenantSpace:
    """An airline's documents and the in-memory counts of what it pushes. Exists in every
    state except deleted."""

    icao: str
    store: MeteredStore
    feed_stats: FeedStats
    conn_stats: ConnectionStats
    keys: KeyIndex = field(default_factory=lambda: KeyIndex({}))

    @contextmanager
    def bound(self) -> Iterator[None]:
        """The wall clock and this airline, for work on its store (no settings)."""
        with ExitStack() as stack:
            stack.enter_context(timeutil.bind_clock(timeutil.SystemClock()))
            stack.enter_context(bind_tenant(self.icao))
            yield


@dataclass(eq=False)
class TenantHandle:
    record: TenantRecord
    space: TenantSpace
    runtime: Runtime | None = None
    health: RuntimeHealth = field(default_factory=RuntimeHealth)
    ticking: bool = False
    restart_at: datetime | None = None
    restarts_in_a_row: int = 0
    start_retry_at: datetime | None = None
    gave_up: bool = False
    purged_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class _Pass:
    at: datetime
    seconds: float


def _hhmm(at: datetime) -> str:
    return f"{timeutil.ensure_utc(at):%H:%M}Z"


class TenantRegistry:
    def __init__(
        self,
        base: Settings,
        root: Store,
        demo: Runtime,
        meter: StoreMeter,
        access: AccessCache,
        *,
        factory: Callable[..., Awaitable[Runtime]] = create_runtime,
        source: Any | None = None,
        clock: timeutil.Clock | None = None,
        rss_mb: Callable[[], int] = process_rss_mb,
    ) -> None:
        self.base = base
        self.root = root
        self.demo = demo
        self.meter = meter
        self.access = access
        self._factory = factory
        self._clock = clock if clock is not None else timeutil.SystemClock()
        self._rss_mb = rss_mb
        self.source = source if source is not None else _shared_source(base)
        self._handles: dict[str, TenantHandle] = {}
        self._spaces: dict[str, TenantSpace] = {}
        self._airports: dict[int, AirportCatalogue] = {
            demo.policy.alternates.min_runway_m.value: demo.airports
        }
        self._passed = False
        self._pass_task: asyncio.Task[None] | None = None
        self._pass_lock = asyncio.Lock()
        self._on_demand_said = False
        self.last_pass: _Pass | None = None
        self.hosting: Literal["always-on", "on-demand"] = (
            "on-demand" if os.environ.get("K_SERVICE") and base.local_scheduler else "always-on"
        )

    # --- spaces and handles -------------------------------------------------------------

    def now(self) -> datetime:
        return timeutil.ensure_utc(self._clock.now())

    def handle(self, icao: str) -> TenantHandle | None:
        return self._handles.get(icao)

    def handles(self) -> list[TenantHandle]:
        return [self._handles[icao] for icao in sorted(self._handles)]

    def space(self, icao: str) -> TenantSpace:
        """The airline's space: its one store object in this process, opened on first use
        (``tenants.set_up`` needs it before the record exists)."""
        held = self._spaces.get(icao)
        if held is None:
            inner = open_store(self.base, namespace=icao, shared=self.root)
            store = MeteredStore(inner, self.meter, icao, cache=TENANT_CACHED)
            if self._passed:
                store.enable_cache()
            since = self.now()
            held = self._spaces[icao] = TenantSpace(
                icao=icao,
                store=store,
                feed_stats=FeedStats(since=since),
                conn_stats=ConnectionStats(since=since),
            )
        return held

    async def _close_space(self, icao: str) -> None:
        self._handles.pop(icao, None)
        space = self._spaces.pop(icao, None)
        if space is not None:
            await space.store.aclose()

    async def reload(self, icao: str) -> TenantHandle | None:
        """The handle with the record as stored now (None once deleted, or never set up).
        The key index is read when the handle is new."""
        record = await tenants.get_tenant(self.root, icao)
        if record is None or record.state == "deleted":
            await self._close_space(icao)
            return None
        handle = self._handles.get(icao)
        if handle is None:
            handle = self._handles[icao] = TenantHandle(record=record, space=self.space(icao))
            await self.refresh_keys(icao)
        else:
            handle.record = record
        return handle

    async def refresh_keys(self, icao: str) -> KeyIndex:
        """Rebuild the airline's push-key index from its connections (one read each)."""
        space = self.space(icao)
        with space.bound():
            space.keys = KeyIndex.build(await list_connections(space.store))
        return space.keys

    def push_key(self, icao: str, key: str) -> Connection | None:
        """The live key a push carries, from memory (D23): None for an unknown airline, a
        suspended or deleted one, or a wrong key alike."""
        handle = self._handles.get(icao)
        if handle is None or handle.record.state not in ("setup", "shadow", "live"):
            return None
        return handle.space.keys.find(key)

    # --- memory and places --------------------------------------------------------------

    def rss_mb(self) -> int:
        return self._rss_mb()

    def memory_ok(self) -> bool:
        return self._rss_mb() <= self.base.hosted_rss_limit_mb

    def require_memory(self) -> None:
        if not self.memory_ok():
            raise HostedRefused(
                409, "site_memory", "The site's memory is full: no airline starts now"
            )

    async def slots_used(self) -> int:
        return len((await tenants.slots(self.root)).holders)

    # --- lifecycle ----------------------------------------------------------------------

    async def start_all(self) -> None:
        """At startup, after the demo runtime: every airline's space, and a runtime for each
        one in shadow or live, one at a time (restore only)."""
        for record in await tenants.list_tenants(self.root):
            if record.state == "deleted":
                continue
            handle = await self.reload(record.icao)
            if handle is not None and record.state in RUNNING:
                await self._start_runtime(handle)

    async def start(self, icao: str) -> None:
        """A runtime for an airline now in shadow or live (setup → shadow, resume). Refused
        with 409 ``site_memory`` while the process is over its memory limit."""
        self.require_memory()
        handle = await self.reload(icao)
        if handle is None or handle.record.state not in RUNNING or handle.runtime is not None:
            return
        handle.gave_up = False
        handle.restarts_in_a_row = 0
        await self._start_runtime(handle)

    async def stop(self, icao: str, *, reason: str) -> None:
        """Stop the airline's runtime (stop runs, suspend): its last checkpoint is written and
        its streams end; the store stays open while the airline has a space."""
        handle = self._handles.get(icao)
        if handle is not None:
            await self._stop_runtime(handle)
            logger.info("hosted runtime stopped", extra={"tenant": icao, "reason": reason})
        await self.reload(icao)

    async def restart(self, icao: str) -> None:
        handle = self._handles.get(icao)
        if handle is None:
            return
        await self._stop_runtime(handle)
        handle = await self.reload(icao)
        if handle is not None and handle.record.state in RUNNING:
            await self._start_runtime(handle)

    async def reconfigure(self, icao: str) -> None:
        """The stage, model, key, daily limits or Desk reserve changed: the runtime swaps its
        settings and backend under its lock (no restart, D26)."""
        handle = await self.reload(icao)
        if handle is None or handle.runtime is None:
            return
        runtime = handle.runtime
        settings, unavailable = await self._settings(handle.record)
        settings = settings.model_copy(update={"session_secret": runtime.settings.session_secret})
        llm = backend_for(settings, unavailable=unavailable, quota=runtime.ledger)
        with handle.space.bound():
            await runtime.reconfigure(settings, llm=llm)

    async def apply_policy(self, icao: str) -> None:
        """A new policy version, or an SRA acceptance recorded or withdrawn: the runtime runs
        on it from its next step (drafts keep the version they were made under)."""
        handle = await self.reload(icao)
        if handle is None or handle.runtime is None:
            return
        policy = await self._policy(handle)
        with handle.space.bound():
            await handle.runtime.set_policy(policy)

    async def aclose(self) -> None:
        """Stop every runtime, write back the keys' counters and the meter, close every store
        and the shared source."""
        if self._pass_task is not None and not self._pass_task.done():
            self._pass_task.cancel()
            await asyncio.gather(self._pass_task, return_exceptions=True)
        for handle in list(self._handles.values()):
            await self._stop_runtime(handle)
        for space in list(self._spaces.values()):
            with space.bound():
                await space.conn_stats.flush(space.store, at=self.now(), force=True)
            await space.store.aclose()
        self._spaces.clear()
        self._handles.clear()
        await self.meter.persist(
            self.root, allowed=self._passed and not self.demo.retired, force=True
        )
        inner = getattr(self.source, "inner", None)
        if inner is not None:
            await inner.aclose()

    # --- runtimes -----------------------------------------------------------------------

    async def _answers(self, record: TenantRecord) -> AirlineAnswers:
        return (await accounts.get_record(self.root, record.airline_id)).submitted()

    async def _settings(self, record: TenantRecord) -> tuple[Settings, str | None]:
        key, unavailable = model_key(record, self.base)
        settings = tenant_settings(self.base, record, await self._answers(record), key)
        return settings, unavailable

    async def _policy(self, handle: TenantHandle) -> OperatorPolicy:
        with handle.space.bound():
            version = await get_version(handle.space.store, handle.record.policy_version)
        if version is None:
            raise LookupError(
                f"{handle.record.icao} has no policy version {handle.record.policy_version}"
            )
        return tenant_policy(self.demo.policy, version, handle.record)

    async def _airports_for(self, policy: OperatorPolicy) -> AirportCatalogue:
        runway = policy.alternates.min_runway_m.value
        held = self._airports.get(runway)
        if held is None:
            held = await asyncio.to_thread(load_airports, self.base.data_dir, min_runway_m=runway)
            self._airports[runway] = held
        return held

    async def _build(self, handle: TenantHandle) -> Runtime:
        from tephra.geo.fleet import OwnSchedule
        from tephra.pipeline import HostedParts

        record = handle.record
        answers = await self._answers(record)
        key, unavailable = model_key(record, self.base)
        settings = tenant_settings(self.base, record, answers, key)
        policy = await self._policy(handle)
        registrations = {a.hex: a.registration for a in answers.fleet.aircraft if a.hex}
        demo = self.demo
        parts = HostedParts(
            tenant=record.icao,
            store=handle.space.store,
            source=self.source,
            catalogue=demo.catalogue,
            airports=await self._airports_for(policy),
            routes=demo.routes,
            policy=policy,
            own_schedule=OwnSchedule.from_registrations(registrations),
            llm_unavailable=unavailable,
            fence=lambda: demo.retired,
        )
        with handle.space.bound():
            return await self._factory(settings, hosted=parts)

    async def _start_runtime(self, handle: TenantHandle) -> None:
        icao = handle.record.icao
        try:
            async with asyncio.timeout(START_TIMEOUT_S):
                runtime = await self._build(handle)
        except Exception as exc:
            now = self.now()
            handle.start_retry_at = now + START_RETRY
            handle.health = handle.health.model_copy(
                update={
                    "running": False,
                    "problem": f"TEPHRA could not start for {handle.record.name} at "
                    f"{_hhmm(now)}: {type(exc).__name__}. TEPHRA retries every 10 minutes.",
                }
            )
            logger.exception("hosted runtime did not start", extra={"tenant": icao})
            return
        handle.runtime = runtime
        handle.start_retry_at = None
        handle.health = handle.health.model_copy(
            update={"running": True, "problem": None, "failures": 0}
        )
        if self._passed:
            with handle.space.bound():
                runtime.start_worker()

    async def _stop_runtime(self, handle: TenantHandle) -> None:
        runtime, handle.runtime = handle.runtime, None
        handle.health = handle.health.model_copy(update={"running": False})
        if runtime is None:
            return
        try:
            with handle.space.bound():
                await runtime.aclose()
        except Exception:
            logger.exception(
                "hosted runtime did not close cleanly", extra={"tenant": handle.space.icao}
            )

    # --- the hosted pass ----------------------------------------------------------------

    def kick(self) -> None:
        """Start one hosted pass unless one is running (``POST /tasks/tick`` calls it before
        it awaits the demo's tick)."""
        if self._pass_task is not None and not self._pass_task.done():
            return
        self._pass_task = asyncio.create_task(self._safe_pass(), name="hosted-pass")

    async def _safe_pass(self) -> None:
        try:
            await self.run_pass()
        except Exception:
            logger.exception("hosted pass failed")

    async def run_pass(self) -> None:
        async with self._pass_lock:
            started = self.now()
            if self.hosting == "on-demand":
                if not self._on_demand_said:
                    logger.warning(
                        "hosted airlines need always-on hosting: nothing ticks in on-demand mode"
                    )
                    self._on_demand_said = True
                return
            first = not self._passed
            self._passed = True
            for space in self._spaces.values():
                if first:
                    space.store.enable_cache()
                space.store.clear_cache()
            await self._due_starts(started)
            await self._due_restarts(started)
            due = self._ticking_now(first)
            await asyncio.gather(*(self._tick(handle) for handle in due))
            await self._purge_due(started)
            for space in list(self._spaces.values()):
                with space.bound():
                    await space.conn_stats.flush(space.store, at=self.now())
            seconds = (self.now() - started).total_seconds()
            self.last_pass = _Pass(at=started, seconds=round(seconds, 1))
            await self.meter.persist(self.root, allowed=not self.demo.retired)

    def _ticking_now(self, first: bool) -> list[TenantHandle]:
        site = self.meter.site_over(self.base)
        due: list[TenantHandle] = []
        for handle in self.handles():
            runtime = handle.runtime
            if handle.record.state not in RUNNING or runtime is None:
                continue
            if first:
                with handle.space.bound():
                    runtime.start_worker()
            own = None if site is not None else self.meter.over(handle.record.icao, self.base)
            paused = site or own
            scope = "site" if site is not None else "airline" if own is not None else None
            handle.health = handle.health.model_copy(
                update={"paused": paused, "paused_scope": scope}
            )
            if paused is None and not handle.ticking:
                due.append(handle)
        return due

    async def _tick(self, handle: TenantHandle) -> None:
        runtime = handle.runtime
        if runtime is None:
            return
        handle.ticking = True
        try:
            with handle.space.bound():
                async with asyncio.timeout(self.base.hosted_tick_budget_s + 10):
                    await runtime.tick(reason="hosted")
        except Exception as exc:
            self._failed(handle, exc)
        else:
            handle.restarts_in_a_row = 0
            handle.health = handle.health.model_copy(
                update={"last_tick_wall_at": self.now(), "failures": 0, "problem": None}
            )
        finally:
            handle.ticking = False

    def _failed(self, handle: TenantHandle, exc: BaseException) -> None:
        icao = handle.record.icao
        now = self.now()
        failures = handle.health.failures + 1
        logger.warning(
            "hosted tick failed: %s", type(exc).__name__, extra={"tenant": icao}, exc_info=exc
        )
        problem = f"stopped at {_hhmm(now)}: {type(exc).__name__}; TEPHRA tries again next run"
        if failures >= FAILURES_BEFORE_RESTART and handle.restart_at is None:
            delay = BACKOFF[min(handle.restarts_in_a_row, len(BACKOFF) - 1)]
            handle.restart_at = now + delay
        if handle.restart_at is not None:
            problem = (
                f"stopped at {_hhmm(now)}: {type(exc).__name__}; TEPHRA restarts it at "
                f"{_hhmm(handle.restart_at)}"
            )
        handle.health = handle.health.model_copy(update={"failures": failures, "problem": problem})

    async def _due_starts(self, now: datetime) -> None:
        for handle in self.handles():
            retry = handle.start_retry_at
            if handle.record.state not in RUNNING or handle.runtime is not None:
                continue
            if retry is None or retry > now or handle.gave_up:
                continue
            await self._start_runtime(handle)

    async def _due_restarts(self, now: datetime) -> None:
        for handle in self.handles():
            due = handle.restart_at
            if due is None or due > now or handle.gave_up:
                continue
            handle.restart_at = None
            record = await tenants.get_tenant(self.root, handle.record.icao)
            day = tenants.quota_day(now).isoformat()
            if record is None or record.restarts.get(day, 0) >= tenants.MAX_RESTARTS:
                handle.gave_up = True
                await self._stop_runtime(handle)
                handle.health = handle.health.model_copy(
                    update={
                        "problem": f"stopped at {_hhmm(now)} after {tenants.MAX_RESTARTS} "
                        "restarts today; TEPHRA's operators see this on their console"
                    }
                )
                continue
            await tenants.note_restart(self.root, handle.record.icao, at=now)
            handle.restarts_in_a_row += 1
            failures = handle.health.failures
            await self.restart(handle.record.icao)
            restarted = self._handles.get(handle.record.icao)
            if restarted is not None and restarted.runtime is not None:
                restarted.health = restarted.health.model_copy(update={"failures": 0})
            elif restarted is not None:
                restarted.health = restarted.health.model_copy(update={"failures": failures})

    # --- deleting -----------------------------------------------------------------------

    async def _purge_due(self, now: datetime) -> None:
        for handle in self.handles():
            if handle.record.state != "deleting":
                continue
            if handle.purged_at is not None and now - handle.purged_at < PURGE_GAP:
                continue
            try:
                await self._purge(handle, now)
            except Exception:
                handle.purged_at = now
                logger.exception("hosted purge failed", extra={"tenant": handle.record.icao})

    def _deletes_left(self, icao: str) -> int:
        """At most :data:`PURGE_PER_MINUTE`, and never past the airline's deletes allowance
        or the site's cap for today."""
        day = self.meter.day()
        own = self.meter.allowance(self.base)["deletes"] - day.deletes.get(icao, 0)
        site = self.base.hosted_deletes_cap - sum(day.deletes.values())
        return max(0, min(PURGE_PER_MINUTE, own, site))

    async def _purge(self, handle: TenantHandle, now: datetime) -> None:
        """Delete up to a minute's share of the airline's documents; when none is left, its
        members and invites go and the record becomes a tombstone."""
        icao = handle.record.icao
        budget = self._deletes_left(icao)
        if budget == 0:
            return
        handle.purged_at = now
        store = cast(_Purgeable, handle.space.store)
        left = budget
        with handle.space.bound():
            for collection in Collection:
                if collection in ROOT_ONLY or left == 0:
                    continue
                left -= await store.delete_some(collection, limit=left)
        if left == 0:
            return
        for found in await hosted_members.members_of(self.root, icao):
            await self.root.delete(Collection.HOSTED_MEMBERS, f"{icao}~{found.login_key}")
        for made in await hosted_members.invites_of(self.root, icao):
            await self.root.delete(Collection.HOSTED_INVITES, made.sha256)
        await tenants.finish_delete(self.root, icao, at=now)
        await self._close_space(icao)
        self.access.drop(icao=icao)
        logger.info("hosted airline data deleted", extra={"tenant": icao})

    # --- keys ---------------------------------------------------------------------------

    async def create_key(self, icao: str, name: str, *, by: str) -> tuple[Connection, str]:
        """A push key (shown once): more than :data:`MAX_KEYS` live keys are refused."""
        space = self.space(icao)
        if len(space.keys) >= MAX_KEYS:
            raise HostedRefused(409, "too_many_keys", f"At most {MAX_KEYS} live push keys")
        with space.bound():
            made = await create_connection(space.store, name, actor=tenants.actor_of(by))
        await self.refresh_keys(icao)
        return made

    async def rotate_key(self, icao: str, connection_id: str, *, by: str) -> tuple[Connection, str]:
        space = self.space(icao)
        with space.bound():
            made = await rotate_connection(space.store, connection_id, actor=tenants.actor_of(by))
        await self.refresh_keys(icao)
        return made

    async def revoke_key(self, icao: str, connection_id: str, *, by: str) -> Connection:
        space = self.space(icao)
        with space.bound():
            gone = await revoke_connection(space.store, connection_id, actor=tenants.actor_of(by))
        await self.refresh_keys(icao)
        return gone

    async def connections(self, icao: str) -> list[Connection]:
        """Every key of the airline, revoked ones too (Feeds lists them)."""
        space = self.space(icao)
        with space.bound():
            return await list_connections(space.store)

    # --- airline actions the routes call ------------------------------------------------

    @property
    def base_policy(self) -> OperatorPolicy:
        """The site's policy A: every airline's versions are changes from it."""
        return self.demo.policy

    async def set_up(
        self, record: AirlineRecord, login: AirlineLogin, name: str
    ) -> tuple[TenantRecord, Member]:
        """(none) → setup for the record holder (``tenants.set_up`` with the site's table,
        policy and airports), and the airline's handle."""
        if record.answers is None:
            raise HostedRefused(409, "not_verified", "Only a verified airline can be hosted")
        icao = record.answers.airline.icao
        try:
            made = await tenants.set_up(
                self.root,
                record,
                login,
                name,
                space=self.space(icao),
                settings=self.base,
                base_policy=self.demo.policy,
                airports=self.demo.airports,
                at=self.now(),
            )
        except BaseException:
            if icao not in self._handles:
                await self._close_space(icao)
            raise
        await self.reload(icao)
        return made

    async def check_record(self, handle: TenantHandle, *, by: str) -> ChainHead:
        """An ops manager's whole walk of the airline's chain (once a day, by the route's
        throttle), refused with 503 ``airline_paused`` when its reads would pass the
        airline's allowance or the site's cap. Writes ``CHAIN_CHECKED``."""
        icao = handle.record.icao
        space = handle.space
        held = audit.chain(space.store).head
        entries = held.entries if held is not None else 0
        if self.meter.would_exceed(icao, self.base, entries):
            raise HostedRefused(
                503,
                "airline_paused",
                "A whole walk would use more of today's free database reads than are left",
            )
        with space.bound():
            head = await audit.check_chain(space.store, whole=True)
            await audit.record(
                space.store,
                actor=tenants.actor_of(by),
                action=AuditAction.CHAIN_CHECKED,
                note=f"Whole chain walked: {head.entries} entries, "
                + ("intact" if head.intact else f"{len(head.problems)} problems"),
            )
        await tenants.note_chain_checked(self.root, icao, by=by, at=self.now())
        await self.reload(icao)
        return head

    async def record_view(
        self,
        handle: TenantHandle,
        *,
        before_seq: int | None,
        is_ops_manager: bool,
        can_check: bool,
        can_export: bool,
    ) -> RecordTab:
        entries, next_before = await tenants.record_page(handle.space, before_seq=before_seq)
        return tenants.record_tab(
            entries,
            next_before,
            audit.chain(handle.space.store),
            is_ops_manager=is_ops_manager,
            can_check=can_check,
            can_export=can_export,
        )

    # --- views --------------------------------------------------------------------------

    def paused_line(self, handle: TenantHandle) -> PausedLine | None:
        health = handle.health
        if health.paused is None or health.paused_scope is None:
            return None
        resumes_at = day_bounds(self.meter.day().day)[1]
        return PausedLine(scope=health.paused_scope, reason=health.paused, resumes_at=resumes_at)

    async def header(self, handle: TenantHandle, you: Member) -> TenantHeader:
        """The airline header for ``you`` (one query for the switcher's memberships)."""
        rows: list[Membership] = []
        for held in await hosted_members.memberships(self.root, you.login_key):
            other = self._handles.get(held.icao)
            record = other.record if other is not None else None
            if record is None or record.state in ("deleting", "deleted"):
                continue
            role = effective(held, record).role
            rows.append(
                Membership(icao=record.icao, name=record.name, role=role, state=record.state)
            )
        health = handle.health
        return tenants.header(
            handle.record,
            you,
            rows,
            running=handle.runtime is not None,
            last_tick_wall_at=health.last_tick_wall_at,
            failures=health.failures,
            problem=health.problem,
            paused=self.paused_line(handle),
            chain=audit.chain(handle.space.store).head,
            wall_now=self.now(),
        )

    async def admin_list(self) -> AdminList:
        """The operator console: places, the meter, every submitted airline's row; airlines
        still onboarding only as a count."""
        base = self.base
        records = await accounts.list_airlines(self.root, "all", limit=ADMIN_ROWS)
        tenants_by_icao = {t.icao: t for t in await tenants.list_tenants(self.root)}
        rows = [await self._admin_row(record, tenants_by_icao) for record in records]
        used = await self.slots_used()
        day = self.meter.day()
        allowance = self.meter.allowance(base)
        namespaces = sorted(day.reads.keys() | day.writes.keys() | day.deletes.keys())
        return AdminList(
            slots=Slots(used=used, max=base.hosted_max_tenants),
            limit_reached=used >= base.hosted_max_tenants,
            hosting=self.hosting,
            # Pending airlines plus Desk-verified ones still waiting for an operator's hosting
            # approval: the console's "To verify" filter counts the same rows.
            to_verify=await accounts.pending_count(self.root)
            + sum(
                1
                for row in rows
                if row.status == "verified" and row.hosting == "desk" and row.checklist is None
            ),
            advisories_waiting=sum(row.advisories_waiting for row in rows),
            meter=AdminMeter(
                day=day.day,
                reads=sum(day.reads.values()),
                writes=sum(day.writes.values()),
                deletes=sum(day.deletes.values()),
                airlines=MeterCounts(
                    **{
                        kind: sum(n for name, n in getattr(day, kind).items() if name != "demo")
                        for kind in ("reads", "writes", "deletes")
                    }
                ),
                caps=MeterCounts(
                    reads=base.hosted_reads_cap,
                    writes=base.hosted_writes_cap,
                    deletes=base.hosted_deletes_cap,
                ),
                allowance=MeterCounts(**allowance),
                by_namespace={
                    name: MeterCounts(
                        reads=day.reads.get(name, 0),
                        writes=day.writes.get(name, 0),
                        deletes=day.deletes.get(name, 0),
                    )
                    for name in namespaces
                },
                blob_puts=BlobPuts(
                    month=day.blob_month, used=day.blob_puts, cap=self.meter.blob_puts_cap
                ),
                counted_since=self.meter.counted_since,
            ),
            process=ProcessLine(rss_mb=self.rss_mb(), limit_mb=base.hosted_rss_limit_mb),
            last_pass=None
            if self.last_pass is None
            else LastPass(
                at=self.last_pass.at,
                seconds=self.last_pass.seconds,
                budget_s=base.hosted_tick_budget_s,
            ),
            unreadable_keys=sum(
                1
                for t in tenants_by_icao.values()
                if t.model_key is not None and model_key(t, base)[1] is not None
            ),
            onboarding=await self.root.count(Collection.AIRLINES, [Where("status", "==", "draft")]),
            rows=rows,
        )

    async def go_live(self, handle: TenantHandle) -> GoLive:
        """The workspace's Go live card for the airline (setup and later)."""
        record = handle.record
        answers = await self._answers(record)
        now = self.now()
        return checklist(
            record,
            answers,
            settings=self.base,
            airports=self.demo.airports,
            stats=handle.space.feed_stats,
            live_keys=[c.id for c in handle.space.keys.by_sha256.values()],
            members=await hosted_members.members_of(self.root, record.icao, record=record),
            open_invites=len(await hosted_members.open_invites(self.root, record.icao, at=now)),
            slots_used=await self.slots_used(),
            memory_ok=self.memory_ok(),
            now=now,
        )

    async def _admin_row(self, record: AirlineRecord, by_icao: dict[str, TenantRecord]) -> AdminRow:
        answers = record.submitted()
        airline = answers.airline
        tenant = by_icao.get(airline.icao)
        if tenant is not None and tenant.airline_id != record.id:
            tenant = None
        handle = None if tenant is None else self._handles.get(tenant.icao)
        hosting: Literal["desk", "operator"] | None = None
        if record.status == "verified":
            hosting = "desk" if record.hosting is None else "operator"
        checklist_words = None
        if tenant is None:
            status = record.status
            label = _AIRLINE_WORDS[record.status]
            if hosting == "desk":
                label = "Verified (Desk)"
            since = record.decided_at or record.submitted_at
        else:
            status = "verified" if tenant.state == "setup" else tenant.state
            if tenant.state == "deleting":
                status = "deleted"
            label = STATE_WORDS[tenant.state]
            since = tenant.state_since
            if tenant.state == "setup" and handle is not None:
                card = await self.go_live(handle)
                checklist_words = f"{sum(item.done for item in card.items)}/{len(card.items)}"
        delete_after = None
        if tenant is not None and tenant.state == "suspended" and tenant.suspended is not None:
            delete_after = tenant.suspended.at + tenants.DELETE_AFTER
        running = handle is not None and handle.record.state in ("setup", *RUNNING)
        return AdminRow(
            airline_id=record.id,
            name=airline.name,
            icao=airline.icao,
            status=status,
            status_label=label,
            state_since=since,
            hosting=hosting,
            checklist=checklist_words,
            feeds=self._admin_feeds(handle, answers) if handle is not None and running else None,
            ai=[] if handle is None else await self._admin_ai(handle),
            advisories_waiting=0 if handle is None else await self._waiting(handle),
            runtime_problem=None if handle is None else handle.health.problem,
            paused=None if handle is None else self.paused_line(handle),
            chain_intact=True if handle is None else _chain_intact(handle),
            delete_after=delete_after,
            ops_email=airline.ops_email,
            version=record.version,
        )

    def _admin_feeds(self, handle: TenantHandle, answers: AirlineAnswers) -> AdminFeeds:
        """Declared sections: ok when one arrived through a live key in the last 10 minutes;
        a quiet optional section (pilot reports) or one in setup is stale; a quiet required
        one on a running airline is an error."""
        now = self.now()
        declared = answers.feeds
        wanted: list[tuple[Section, bool, bool]] = [
            ("positions", declared.positions, False),
            ("flight_plans", declared.flight_plans, False),
            ("pilot_reports", declared.pilot_reports, True),
        ]
        live = [c.id for c in handle.space.keys.by_sha256.values()]
        ok = stale = error = 0
        notes: list[str] = []
        for section, on, optional in wanted:
            if not on:
                continue
            last = handle.space.feed_stats.last_received(section, now=now, keys=live)
            if last is not None and now - last <= FEEDS_FRESH:
                ok += 1
                continue
            quiet = _SECTION_WORDS[section]
            quiet += (
                f" not received since {_hhmm(handle.space.feed_stats.since)}"
                if last is None
                else f" not received {int((now - last).total_seconds() // 60)} min"
            )
            if optional or handle.record.state == "setup":
                stale += 1
            else:
                error += 1
            notes.append(quiet)
        note = notes[0] if notes else None
        if not (declared.positions or declared.flight_plans or declared.pilot_reports):
            note = "public ADS-B only"
        return AdminFeeds(ok=ok, stale=stale, error=error, note=note)

    async def _admin_ai(self, handle: TenantHandle) -> list[AdminAi]:
        runtime = handle.runtime
        if runtime is None:
            return []
        with handle.space.bound():
            view = await runtime.budget_view()
        return [AdminAi(model=row.model_id, used=row.used, budget=row.limit) for row in view.models]

    async def _waiting(self, handle: TenantHandle) -> int:
        """Advisories waiting for a decision (one count: a read per 1,000)."""
        with handle.space.bound():
            return await handle.space.store.count(
                Collection.ADVISORIES, [Where("status", "==", AdvisoryStatus.DRAFT.value)]
            )


_AIRLINE_WORDS: Final[dict[str, str]] = {
    "draft": "Not submitted",
    "pending": "Pending",
    "verified": "Verified",
    "declined": "Declined",
}
_SECTION_WORDS: Final[dict[str, str]] = {
    "positions": "positions",
    "flight_plans": "flight plans",
    "pilot_reports": "pilot reports",
}


def _chain_intact(handle: TenantHandle) -> bool:
    head = audit.chain(handle.space.store).head
    return head is None or not [p for p in head.problems if p != audit.NOT_WALKED]


def _shared_source(base: Settings) -> Any:
    """The one live source every hosted runtime fetches through (one httpx client, one
    courtesy spacing for adsb.lol)."""
    from tephra.feeds.base import HttpSource, SharedHttpSource

    return SharedHttpSource(HttpSource.from_settings(base), settings=base)
