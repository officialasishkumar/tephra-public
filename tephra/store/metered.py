"""Store operations counted per namespace and Pacific day, and the hosted airlines' caches.

With the hosted feature on, every store is wrapped in a :class:`MeteredStore`: the demo's and
the site's documents as namespace ``"demo"``, each airline's as its ICAO. The backends report
what Firestore bills (``on_op``), and the wrapper attributes it to its namespace in the one
:class:`StoreMeter`; what a member's request under ``/a/<ICAO>/api`` does in the root store is
attributed to that airline (``tephra.util.scope.charged_to``). Each airline has a daily
allowance (``cap x share / max_tenants``) and its ticks and pushes pause alone past it; its
people's reads stop at its ceiling (``cap / max_tenants``), so the airlines together never
pass a site cap. The site backstop sums the airlines only: what the demo and its visitors use
is shown on the console and never pauses an airline. Without the feature nothing is wrapped and
nothing is counted.

An airline's store fails closed: used outside that airline's binding (``bind_tenant`` and a
bound clock) it raises instead of reading or writing, so no work can reach an airline's data
on the demo's replay clock or on behalf of another airline.
"""

import copy
import math
import re
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final, Literal, cast, get_args

from pydantic import Field, ValidationError

from tephra.agents.quota import quota_day
from tephra.models import AuditEntry, FeedHealth, FeedId, TephraModel
from tephra.store import NAMESPACE_PATTERN
from tephra.store.base import Collection, Store, Where
from tephra.util import timeutil
from tephra.util.scope import charged_to, current_tenant

if TYPE_CHECKING:
    from tephra.config import Settings

__all__ = [
    "BLOB_PAUSED",
    "CACHE_MAX_ENTRIES",
    "CACHE_TTL_S",
    "DEMO_NAMESPACE",
    "PERSIST_EVERY",
    "TENANT_CACHED",
    "BlobAllowanceUsed",
    "MeterDay",
    "MeteredStore",
    "OpKind",
    "StoreMeter",
]

OpKind = Literal["reads", "writes", "deletes"]
_KINDS: Final[tuple[OpKind, ...]] = get_args(OpKind)
DEMO_NAMESPACE: Final = "demo"
"""The root namespace: the demo's documents and the site's own (accounts, tenants, meter)."""
TENANT_CACHED: Final = frozenset(
    {Collection.ADVISORIES, Collection.AI_FAILURES, Collection.CONNECTIONS}
)
"""What an airline's store caches (``MeteredStore(..., cache=TENANT_CACHED)``): the reads
every tick and every Desk poll repeat."""
CACHE_TTL_S: Final = 120.0
CACHE_MAX_ENTRIES: Final = 256
PERSIST_EVERY: Final = timedelta(minutes=10)
BLOB_PAUSED: Final = (
    "Satellite frames paused: the site's free storage operations for this month are used"
)
_NAMESPACE = re.compile(NAMESPACE_PATTERN)


class BlobAllowanceUsed(Exception):
    """An airline's frame upload past this month's site allowance: nothing is stored."""

    def __init__(self) -> None:
        super().__init__(BLOB_PAUSED)


class MeterDay(TephraModel):
    """``hosted_meter/<Pacific day>``: store operations by namespace, and this month's blob
    uploads by airlines."""

    day: date = Field(description="Pacific day: Firestore's free quota resets at midnight Pacific")
    reads: dict[str, int] = Field(default_factory=dict, description="Namespace -> reads")
    writes: dict[str, int] = Field(default_factory=dict)
    deletes: dict[str, int] = Field(default_factory=dict)
    blob_month: str = Field(pattern=r"^\d{4}-\d{2}$", description="Calendar month, UTC")
    blob_puts: int = Field(default=0, ge=0)


class StoreMeter:
    """One per process: counts every metered store's operations on the wall clock.

    Counts begin at zero in each process (``counted_since``) and :meth:`restore` takes the
    day's persisted counts; :meth:`persist` merges by the larger count per namespace, so two
    instances in a rollout never lower each other's numbers.
    """

    def __init__(self, *, blob_puts_cap: int, clock: timeutil.Clock | None = None) -> None:
        self._clock = clock if clock is not None else timeutil.SystemClock()
        self.blob_puts_cap = blob_puts_cap
        self.blobs_written: set[str] = set()
        """Blob keys this process stored: written once, never uploaded again (public data)."""
        now = self._now()
        self.counted_since = now
        self._day = MeterDay(day=quota_day(now), blob_month=_month(now))
        self._persisted_at: datetime | None = None

    # --- counting -----------------------------------------------------------------------

    def count(
        self, namespace: str, kind: Literal["reads", "writes", "deletes", "blob_puts"], n: int
    ) -> None:
        if n <= 0:
            return
        day = self._current()
        if kind == "blob_puts":
            day.blob_puts += n
            return
        counts: dict[str, int] = getattr(day, kind)
        counts[namespace] = counts.get(namespace, 0) + n

    def day(self) -> MeterDay:
        """Today's counts (a copy)."""
        return self._current().model_copy(deep=True)

    def allowance(self, settings: "Settings") -> dict[OpKind, int]:
        """One airline's daily allowance per kind: its share of each site cap."""
        if settings.hosted_max_tenants == 0:
            return dict.fromkeys(_KINDS, 0)
        share = settings.hosted_tenant_share / settings.hosted_max_tenants
        # round() first: 40,000 x 0.6 / 3 must come out as 8,000, not 7,999.
        return {kind: math.floor(round(_cap(settings, kind) * share, 6)) for kind in _KINDS}

    def ceiling(self, settings: "Settings") -> int:
        """Reads one airline may make in a day, its people's included: its even part of the
        site's read cap. Past it the airline's requests that read are refused, so the airlines
        together never pass the cap (the allowance below it pauses ticks and pushes first)."""
        if settings.hosted_max_tenants == 0:
            return 0
        return settings.hosted_reads_cap // settings.hosted_max_tenants

    def reads_spent(self, namespace: str, settings: "Settings") -> bool:
        """Whether ``namespace`` has read up to its :meth:`ceiling` today (never the demo)."""
        if namespace == DEMO_NAMESPACE:
            return False
        return self._current().reads.get(namespace, 0) >= self.ceiling(settings)

    def over(self, namespace: str, settings: "Settings") -> OpKind | None:
        """The first kind ``namespace`` has used its own allowance of today (never the demo)."""
        if namespace == DEMO_NAMESPACE:
            return None
        day = self._current()
        allowance = self.allowance(settings)
        for kind in _KINDS:
            counts: dict[str, int] = getattr(day, kind)
            if counts.get(namespace, 0) >= allowance[kind]:
                return kind
        return None

    def site_over(self, settings: "Settings") -> OpKind | None:
        """The first kind the hosted airlines together have used up to the site cap today.
        The demo's own use is left out: a visitor's reads never pause an airline."""
        day = self._current()
        for kind in _KINDS:
            counts: dict[str, int] = getattr(day, kind)
            if _airlines(counts) >= _cap(settings, kind):
                return kind
        return None

    def would_exceed(self, namespace: str, settings: "Settings", reads: int) -> bool:
        """Whether ``reads`` more reads would pass the namespace's allowance or the airlines'
        site cap (a full walk of a record, an export)."""
        day = self._current()
        if _airlines(day.reads) + reads > settings.hosted_reads_cap:
            return True
        if namespace == DEMO_NAMESPACE:
            return False
        return day.reads.get(namespace, 0) + reads > self.allowance(settings)["reads"]

    def blob_allowance_used(self) -> bool:
        return self._current().blob_puts >= self.blob_puts_cap

    # --- persistence --------------------------------------------------------------------

    async def persist(self, root: Store, *, allowed: bool, force: bool = False) -> bool:
        """Write today's counts to ``hosted_meter/<day>``, merged by the larger count per
        namespace inside the store's transaction, then hold the merged counts. At most every
        10 minutes (``force`` for shutdown), and only when ``allowed``: this instance has run a
        hosted pass and is not retired. Returns whether it wrote."""
        if not allowed:
            return False
        now = self._now()
        if (
            not force
            and self._persisted_at is not None
            and now - self._persisted_at < PERSIST_EVERY
        ):
            return False
        mine = self.day()

        def merge(stored: dict[str, Any] | None) -> dict[str, Any]:
            theirs = _meter_day(stored)
            merged = mine if theirs is None or theirs.day != mine.day else _max(mine, theirs)
            return merged.model_dump(mode="json")

        written = await root.update(Collection.HOSTED_METER, mine.day.isoformat(), merge)
        self._absorb(_meter_day(written))
        self._persisted_at = now
        return True

    async def restore(self, root: Store) -> None:
        """Take today's persisted counts (a restart or a new instance keeps counting on)."""
        day = self._current()
        self._absorb(_meter_day(await root.get(Collection.HOSTED_METER, day.day.isoformat())))

    # --- internals ----------------------------------------------------------------------

    def _now(self) -> datetime:
        return timeutil.ensure_utc(self._clock.now())

    def _current(self) -> MeterDay:
        """Today's counts, rolled at midnight Pacific; blob uploads roll by calendar month."""
        now = self._now()
        today, month = quota_day(now), _month(now)
        held = self._day
        if held.day != today:
            puts = held.blob_puts if held.blob_month == month else 0
            self._day = MeterDay(day=today, blob_month=month, blob_puts=puts)
        elif held.blob_month != month:
            self._day = held.model_copy(update={"blob_month": month, "blob_puts": 0})
        return self._day

    def _absorb(self, other: MeterDay | None) -> None:
        held = self._current()
        if other is not None and other.day == held.day:
            self._day = _max(held, other)


class MeteredStore(Store):
    """A store whose every operation is counted for ``namespace`` in ``meter``.

    One wrapper per backend object (the backend's hook is taken), and one backend object per
    namespace per process: the audit chain, decision locks and caches are held per object.
    Hashed and compared by identity, and weak-referenceable, for those per-store maps.
    """

    def __init__(
        self,
        inner: Store,
        meter: StoreMeter,
        namespace: str,
        *,
        cache: frozenset[str] = frozenset(),
    ) -> None:
        if namespace != DEMO_NAMESPACE and _NAMESPACE.fullmatch(namespace) is None:
            raise ValueError(f"namespace must be {DEMO_NAMESPACE!r} or an ICAO: {namespace!r}")
        if cache and namespace == DEMO_NAMESPACE:
            raise ValueError("the demo store is never cached")
        if not hasattr(inner, "on_op"):
            raise TypeError(f"{type(inner).__name__} reports no operations to meter")
        backend = cast(Any, inner)
        if backend.on_op is not None:
            raise ValueError("this store is already metered: one store object per namespace")
        backend.on_op = self._counted
        self.inner = inner
        self.meter = meter
        self.namespace = namespace
        self._cached = frozenset(str(name) for name in cache)
        self._cache_on = False
        self._entries: OrderedDict[tuple[Any, ...], tuple[float, Any]] = OrderedDict()
        self._generation: dict[str, int] = {}
        self._epoch = 0

    def __repr__(self) -> str:
        return f"MeteredStore({self.namespace!r}, {type(self.inner).__name__})"

    # --- cache control ------------------------------------------------------------------

    def enable_cache(self) -> None:
        """Start caching (the registry calls it at this instance's first hosted pass)."""
        self._cache_on = True

    def clear_cache(self) -> None:
        self._entries.clear()
        self._epoch += 1

    # --- documents ----------------------------------------------------------------------

    async def put(self, collection: str, doc_id: str, doc: Mapping[str, Any]) -> None:
        await self._write(collection, lambda: self.inner.put(collection, doc_id, doc))

    async def get(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        return await self._read(
            collection, ("get", doc_id), lambda: self.inner.get(collection, doc_id)
        )

    async def delete(self, collection: str, doc_id: str) -> None:
        await self._write(collection, lambda: self.inner.delete(collection, doc_id))

    async def delete_some(self, collection: str, *, limit: int) -> int:
        """The purge of a deleted airline: refused on the demo namespace."""
        if self.namespace == DEMO_NAMESPACE:
            raise RuntimeError("the demo store is never purged")
        return await self._write(
            collection, lambda: self.inner.delete_some(collection, limit=limit)
        )

    async def list_docs(
        self,
        collection: str,
        *,
        limit: int = 100,
        order_by: str | None = None,
        descending: bool = True,
    ) -> list[dict[str, Any]]:
        return await self._read(
            collection,
            ("list", limit, order_by, descending),
            lambda: self.inner.list_docs(
                collection, limit=limit, order_by=order_by, descending=descending
            ),
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
        return await self._read(
            collection,
            ("query", repr(tuple(where)), order_by, descending, limit),
            lambda: self.inner.query(
                collection, where, order_by=order_by, descending=descending, limit=limit
            ),
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
        self._check()
        return await self.inner.page(
            collection, field=field, before=before, limit=limit, descending=descending
        )

    async def count(self, collection: str, where: Sequence[Where] = ()) -> int:
        self._check()
        return await self.inner.count(collection, where)

    async def update(
        self,
        collection: str,
        doc_id: str,
        change: Callable[[dict[str, Any] | None], dict[str, Any]],
    ) -> dict[str, Any]:
        return await self._write(collection, lambda: self.inner.update(collection, doc_id, change))

    async def compare_and_set_advisory(
        self, advisory_id: str, expected_version: int, doc: Mapping[str, Any]
    ) -> bool:
        return await self._write(
            Collection.ADVISORIES,
            lambda: self.inner.compare_and_set_advisory(advisory_id, expected_version, doc),
        )

    async def append_audit(self, entry: AuditEntry) -> None:
        await self._write(Collection.AUDIT, lambda: self.inner.append_audit(entry))

    async def get_feed_state(self, feed: FeedId) -> FeedHealth | None:
        self._check()
        return await self.inner.get_feed_state(feed)

    async def put_feed_state(self, state: FeedHealth) -> None:
        await self._write(Collection.FEED_STATE, lambda: self.inner.put_feed_state(state))

    async def list_feed_states(self) -> list[FeedHealth]:
        self._check()
        return await self.inner.list_feed_states()

    # --- blobs --------------------------------------------------------------------------

    async def put_blob(self, key: str, data: bytes, content_type: str) -> None:
        """Blobs are public data shared by every namespace: a key this process stored is not
        uploaded again. An airline's upload counts against the month's allowance and is
        refused past it (:class:`BlobAllowanceUsed`)."""
        self._check()
        if key in self.meter.blobs_written:
            return
        airline = self.namespace != DEMO_NAMESPACE
        if airline and self.meter.blob_allowance_used():
            raise BlobAllowanceUsed
        await self.inner.put_blob(key, data, content_type)
        self.meter.blobs_written.add(key)
        if airline:
            self.meter.count(self.namespace, "blob_puts", 1)

    async def get_blob(self, key: str) -> tuple[bytes, str] | None:
        self._check()
        return await self.inner.get_blob(key)

    async def aclose(self) -> None:
        """Closing reads and writes nothing, so it needs no binding."""
        await self.inner.aclose()

    # --- internals ----------------------------------------------------------------------

    def _counted(self, kind: str, n: int) -> None:
        if kind not in _KINDS:
            raise ValueError(f"unknown store operation kind {kind!r}")
        namespace = self.namespace
        if namespace == DEMO_NAMESPACE:
            namespace = charged_to() or namespace  # a member's request: that airline's share
        self.meter.count(namespace, cast(OpKind, kind), n)

    def _check(self) -> None:
        if self.namespace == DEMO_NAMESPACE:
            return
        if current_tenant() != self.namespace or not timeutil.clock_bound():
            raise RuntimeError("tenant store used outside its binding")

    async def _read[T](
        self, collection: str, args: tuple[Any, ...], fetch: Callable[[], Awaitable[T]]
    ) -> T:
        self._check()
        name = str(collection)
        if not self._cache_on or name not in self._cached:
            return await fetch()
        key = (name, *args)
        now = time.monotonic()
        held = self._entries.get(key)
        if held is not None and now - held[0] <= CACHE_TTL_S:
            self._entries.move_to_end(key)
            return cast(T, copy.deepcopy(held[1]))
        mark = (self._epoch, self._generation.get(name, 0))
        value = await fetch()
        if self._cache_on and mark == (self._epoch, self._generation.get(name, 0)):
            self._entries[key] = (now, copy.deepcopy(value))
            self._entries.move_to_end(key)
            while len(self._entries) > CACHE_MAX_ENTRIES:
                self._entries.popitem(last=False)
        return value

    async def _write[T](self, collection: str, write: Callable[[], Awaitable[T]]) -> T:
        self._check()
        name = str(collection)
        self._forget(name)
        try:
            return await write()
        finally:
            self._forget(name)

    def _forget(self, collection: str) -> None:
        """Empty ``collection``'s entries, and keep a read already under way from storing what
        it found before this write."""
        self._generation[collection] = self._generation.get(collection, 0) + 1
        for key in [key for key in self._entries if key[0] == collection]:
            del self._entries[key]


def _airlines(counts: Mapping[str, int]) -> int:
    """The airlines' part of one kind's counts (every namespace but the demo's)."""
    return sum(n for name, n in counts.items() if name != DEMO_NAMESPACE)


def _cap(settings: "Settings", kind: OpKind) -> int:
    caps: dict[OpKind, int] = {
        "reads": settings.hosted_reads_cap,
        "writes": settings.hosted_writes_cap,
        "deletes": settings.hosted_deletes_cap,
    }
    return caps[kind]


def _month(at: datetime) -> str:
    return timeutil.ensure_utc(at).strftime("%Y-%m")


def _meter_day(doc: Mapping[str, Any] | None) -> MeterDay | None:
    if doc is None:
        return None
    try:
        return MeterDay.model_validate(doc)
    except ValidationError:
        return None


def _max(mine: MeterDay, theirs: MeterDay) -> MeterDay:
    """The larger count per namespace and kind; blob uploads from the later month."""

    def larger(a: dict[str, int], b: dict[str, int]) -> dict[str, int]:
        return {name: max(a.get(name, 0), b.get(name, 0)) for name in a.keys() | b.keys()}

    if mine.blob_month == theirs.blob_month:
        blob_month, blob_puts = mine.blob_month, max(mine.blob_puts, theirs.blob_puts)
    else:
        later = max(mine, theirs, key=lambda day: day.blob_month)
        blob_month, blob_puts = later.blob_month, later.blob_puts
    return MeterDay(
        day=mine.day,
        reads=larger(mine.reads, theirs.reads),
        writes=larger(mine.writes, theirs.writes),
        deletes=larger(mine.deletes, theirs.deletes),
        blob_month=blob_month,
        blob_puts=blob_puts,
    )
