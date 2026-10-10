"""Feed definitions: what each poller fetches, how often, and where its records land.

``poll`` runs one feed through the runtime's ``Source`` (live HTTP or a replay case),
merges the records into the in-memory :class:`LiveData`, writes new or changed records to
the store, and updates that feed's :class:`FeedHealth`. A failing feed never raises: the
error is recorded and the last good records stay in memory.

Records are compared on their content without provenance. A SIGMET's provenance hashes
the whole feed response, which changes whenever any FIR in the world updates; keeping the
first-seen copy of an unchanged record keeps its source id and hash stable, so the Plume
Reader is not re-triggered by someone else's SIGMET.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final, Protocol
from urllib.parse import urlsplit

import httpx

from tephra.config import Settings
from tephra.feeds.adsb import (
    MAX_CACHED_COPY_AGE_S,
    AdsbPointsFailed,
    fetch_aircraft,
    query_points,
)
from tephra.feeds.base import FetchError, FetchResult, Source, build_url
from tephra.feeds.satellite import fetch_frames
from tephra.feeds.sigmet import fetch_sigmets
from tephra.feeds.taf import fetch_metars, fetch_tafs
from tephra.feeds.vaac import DARWIN_BULLETIN_URLS, fetch_vaas
from tephra.feeds.vona import fetch_vonas
from tephra.feeds.winds import fetch_winds
from tephra.models import (
    AdsbQueryPoint,
    AdsbSnapshot,
    BtdResult,
    FeedHealth,
    FeedId,
    FeedStatus,
    Metar,
    Provenance,
    RunMode,
    SatelliteFrame,
    Sigmet,
    Taf,
    TephraModel,
    VaacAdvisory,
    Volcano,
    Vona,
    WindForecast,
    WindProfile,
)
from tephra.science.btd import ScienceUnavailable, btd_key, run_btd
from tephra.store.base import Collection
from tephra.util import timeutil

if TYPE_CHECKING:
    from tephra.pipeline import Runtime

__all__ = [
    "CONTEXT_FEEDS",
    "PRODUCT_FEEDS",
    "FeedPoll",
    "LiveData",
    "disabled_reason",
    "due_feeds",
    "health_view",
    "initial_health",
    "poll",
    "taf_icaos",
    "uncovered_feeds",
]

logger = logging.getLogger(__name__)

PRODUCT_FEEDS: Final = (FeedId.SIGMET, FeedId.VONA, FeedId.VAAC_TOKYO, FeedId.VAAC_DARWIN)
"""Polled before activity is decided: they are what makes a volcano active."""
CONTEXT_FEEDS: Final = (
    FeedId.ADSB,
    FeedId.TAF,
    FeedId.METAR,
    FeedId.WINDS,
    FeedId.FRAMES,
    FeedId.HSD,
)
"""Polled after activity is decided, for the active volcanoes and their airspace."""
VOLCANO_FEEDS: Final = frozenset(
    {FeedId.TAF, FeedId.METAR, FeedId.WINDS, FeedId.FRAMES, FeedId.HSD}
)
"""Only useful while some volcano is active."""

DUE_SLACK_S: Final = 5
"""A 60 s feed on a 60 s tick would otherwise miss every other tick by milliseconds."""
IDLE_ADSB_FACTOR: Final = 4
"""With nothing active, aircraft only decorate the map: poll adsb.lol four times less."""
POLL_BUDGET_SHARE: Final = 0.75
"""A feed poll may take this share of the tick interval: a host that accepts requests and
never answers (Open-Meteo, for five minutes on 10 Oct) costs the tick one bounded wait."""
GAP_RETRY_S: Final = 120
"""Minimum spacing of polls forced because an active volcano has no data of a kind yet."""
COLD_START_VONA_PAGES: Final = 2
ISSUE_SLACK: Final = timedelta(minutes=5)
"""A notice stamped this little after the replay clock already counts as issued."""
VAA_RETENTION_H: Final = 30
ALTERNATES_PER_VOLCANO: Final = 8
ALTERNATES_PER_FLIGHT: Final = 5
STALE_NOTE: Final = "live fetch failed; serving the last good copy"
UNREACHABLE_ERRORS: Final = (httpx.TimeoutException, httpx.ConnectError)
"""Transport failures that say the host itself is not answering (not an HTTP error)."""
VONA_OFF_NOTE: Final = (
    "live polling off: MAGMA's robots.txt disallows crawling (TEPHRA_VONA_LIVE); "
    "replays serve recorded VONAs"
)
HSD_OFF_NOTE: Final = "raw Himawari processing is off (TEPHRA_SCIENCE=0)"
NOT_RECORDED_NOTE: Final = "not in this replay case: no archive of this feed was recorded"


@dataclass(frozen=True)
class _Gap:
    keys: frozenset[str]
    """What an active volcano needs of the feed and has never had (TAF/METAR: ICAOs)."""
    since: datetime


@dataclass
class LiveData:
    """The current picture held in memory between ticks (the store has the history)."""

    sigmets: dict[str, Sigmet] = field(default_factory=dict)
    vonas: dict[str, Vona] = field(default_factory=dict)
    vaas: dict[str, VaacAdvisory] = field(default_factory=dict)
    tafs: dict[str, Taf] = field(default_factory=dict)
    metars: dict[str, Metar] = field(default_factory=dict)
    adsb: list[AdsbSnapshot] = field(default_factory=list)
    adsb_at: datetime | None = None
    winds: dict[str, list[WindProfile]] = field(default_factory=dict)
    frames: dict[str, list[SatelliteFrame]] = field(default_factory=dict)
    btd: dict[str, BtdResult] = field(default_factory=dict)
    active: dict[str, list[str]] = field(default_factory=dict)
    health: dict[FeedId, FeedHealth] = field(default_factory=dict)
    covered: dict[FeedId, set[str]] = field(default_factory=dict)
    """Per-volcano feeds: volcano ids (TAF/METAR: ICAOs) fetched successfully at least once."""
    gaps: dict[FeedId, _Gap] = field(default_factory=dict)
    """Feeds some active volcano still lacks; forced polls back off the longer a gap lasts."""


class FeedPoll(TephraModel):
    feed: FeedId
    ok: bool
    record_count: int = 0
    new_record_count: int = 0
    error: str | None = None
    stale: bool = False


class _Record(Protocol):
    @property
    def provenance(self) -> Provenance: ...


@dataclass(frozen=True)
class _Outcome:
    record_count: int
    new_record_count: int
    stale: bool
    error: str | None = None
    """Part of the feed failed and older data stands in for it (the outcome is stale)."""


# --- scheduling -------------------------------------------------------------------------


def disabled_reason(
    feed: FeedId,
    settings: Settings,
    *,
    replay: bool,
    recorded: frozenset[FeedId] | None = None,
) -> str | None:
    """Why ``feed`` is never polled under these settings, or None when it is polled.

    ``recorded`` is the set of feeds the playing replay case holds: a reconstruction from
    archives has no ADS-B or winds, and those feeds are absent, not failing.
    """
    if feed is FeedId.HSD and not settings.science:
        return HSD_OFF_NOTE
    if feed is FeedId.VONA and not (settings.vona_live or replay):
        return VONA_OFF_NOTE
    if replay and recorded is not None and feed not in recorded:
        return NOT_RECORDED_NOTE
    return None


def initial_health(
    settings: Settings, *, replay: bool, recorded: frozenset[FeedId] | None = None
) -> dict[FeedId, FeedHealth]:
    health: dict[FeedId, FeedHealth] = {}
    for feed in FeedId:
        reason = disabled_reason(feed, settings, replay=replay, recorded=recorded)
        health[feed] = FeedHealth(
            feed=feed,
            status=FeedStatus.NEVER if reason is None else FeedStatus.DISABLED,
            cadence_s=settings.cadence_s(feed),
            last_error=reason,
            replay=replay,
        )
    return health


def due_feeds(
    at: datetime,
    states: Mapping[FeedId, FeedHealth],
    settings: Settings,
    *,
    active: bool,
    replay: bool = False,
    recorded: frozenset[FeedId] | None = None,
) -> list[FeedId]:
    """Feeds whose cadence has elapsed since their last attempt, in ``FeedId`` order.

    ``active`` is whether any volcano is active: without one, the per-volcano feeds are
    never due and ADS-B slows down. Live VONA polling needs ``settings.vona_live``; a replay
    serves its recorded VONAs regardless.
    """
    due: list[FeedId] = []
    for feed in FeedId:
        if feed in VOLCANO_FEEDS and not active:
            continue
        if disabled_reason(feed, settings, replay=replay, recorded=recorded) is not None:
            continue
        state = states.get(feed)
        if state is None or state.last_attempt_at is None:
            due.append(feed)
            continue
        cadence = settings.cadence_s(feed)
        if feed is FeedId.ADSB and not active:
            cadence *= IDLE_ADSB_FACTOR
        if (at - state.last_attempt_at).total_seconds() >= cadence - DUE_SLACK_S:
            due.append(feed)
    return due


def uncovered_feeds(runtime: "Runtime", at: datetime) -> list[FeedId]:
    """Feeds to poll now, off-cadence, because an active volcano has no data of that kind.

    A volcano that becomes active should not wait up to an hour for its winds. Forced polls
    of a gap that stays open back off: the first retry waits :data:`GAP_RETRY_S`, each later
    one as long as the gap had lasted, up to the feed's cadence. A volcano newly missing
    from a feed starts its gap afresh.
    """
    live = runtime.live
    live.gaps = {
        feed: _continued(live.gaps.get(feed), keys, at) for feed, keys in _missing(runtime).items()
    }
    return [
        feed
        for feed, gap in live.gaps.items()
        if _retry_allowed(live.health.get(feed), gap, at, runtime.settings.cadence_s(feed))
        and disabled_reason(
            feed,
            runtime.settings,
            replay=runtime.mode is RunMode.REPLAY,
            recorded=runtime.recorded_feeds,
        )
        is None
    ]


def _missing(runtime: "Runtime") -> dict[FeedId, frozenset[str]]:
    live = runtime.live
    missing: dict[FeedId, frozenset[str]] = {}
    if live.adsb_at is None:
        missing[FeedId.ADSB] = frozenset()
    if not live.active:
        return missing
    active = frozenset(live.active)
    needed = {
        FeedId.WINDS: active,
        FeedId.FRAMES: active,
        FeedId.TAF: frozenset(taf_icaos(runtime)),
    }
    if runtime.settings.science:
        needed[FeedId.HSD] = active
    for feed, keys in needed.items():
        if uncovered := keys - live.covered.get(feed, set()):
            missing[feed] = uncovered
    return missing


def _continued(gap: _Gap | None, keys: frozenset[str], at: datetime) -> _Gap:
    if gap is not None and keys <= gap.keys:
        return _Gap(keys, gap.since)
    return _Gap(keys, at)


def _retry_allowed(state: FeedHealth | None, gap: _Gap, at: datetime, cadence_s: int) -> bool:
    if state is None or state.last_attempt_at is None:
        return True
    lasted = (state.last_attempt_at - gap.since).total_seconds()
    wait = min(max(GAP_RETRY_S, lasted), max(GAP_RETRY_S, cadence_s))
    return (at - state.last_attempt_at).total_seconds() >= wait


def health_view(
    states: Mapping[FeedId, FeedHealth], at: datetime, settings: Settings
) -> list[FeedHealth]:
    """Feed health with ages as of ``at``; an OK feed past its stale age reads STALE."""
    view: list[FeedHealth] = []
    for feed in FeedId:
        state = states.get(feed)
        if state is None:
            continue
        age = None if state.last_success_at is None else timeutil.age_s(state.last_success_at, at)
        status = state.status
        if status is FeedStatus.OK and age is not None and age > settings.stale_after_s(feed):
            status = FeedStatus.STALE
        view.append(state.model_copy(update={"age_s": age, "status": status}))
    return view


def taf_icaos(runtime: "Runtime") -> list[str]:
    """Aerodromes whose TAFs the planner may need: region alternates, plus the nearest
    alternates around every active volcano and every currently exposed flight."""
    settings = runtime.settings
    airports = runtime.airports
    icaos = {
        airport.icao
        for airport in airports.in_bbox(settings.region_preset.bbox)
        if airport.alternate_ok
    }
    for volcano in runtime.active_volcanoes():
        nearest = airports.nearest(
            volcano.lat,
            volcano.lon,
            limit=ALTERNATES_PER_VOLCANO,
            max_nm=settings.alternate_search_nm,
        )
        icaos.update(airport.icao for airport, _ in nearest)
    for flight in runtime.exposed.values():
        nearest = airports.nearest(
            flight.lat, flight.lon, limit=ALTERNATES_PER_FLIGHT, max_nm=settings.alternate_search_nm
        )
        icaos.update(airport.icao for airport, _ in nearest)
    return sorted(icaos)


# --- polling ----------------------------------------------------------------------------


async def poll(feed: FeedId, runtime: "Runtime") -> FeedPoll:
    at = timeutil.now()
    poller = _POLLERS[feed]
    budget_s = runtime.settings.tick_interval_s * POLL_BUDGET_SHARE
    try:
        async with asyncio.timeout(budget_s):
            outcome = await poller(runtime, at)
    except TimeoutError:
        return _failed(runtime, feed, at, f"no answer within {budget_s:g} s")
    except FetchError as exc:
        return _failed(runtime, feed, at, exc.reason)
    except ScienceUnavailable as exc:
        return _failed(runtime, feed, at, str(exc), status=FeedStatus.DISABLED)
    except Exception as exc:  # a parser bug must not stop the other feeds or the tick
        logger.exception("polling %s failed", feed.value)
        return _failed(runtime, feed, at, f"{type(exc).__name__}: {exc}")
    previous = runtime.live.health.get(feed)
    last_success = previous.last_success_at if previous is not None else None
    runtime.live.health[feed] = FeedHealth(
        feed=feed,
        status=FeedStatus.STALE if outcome.stale else FeedStatus.OK,
        cadence_s=runtime.settings.cadence_s(feed),
        last_attempt_at=at,
        last_success_at=last_success if outcome.stale else at,
        last_error=(outcome.error or STALE_NOTE) if outcome.stale else None,
        record_count=outcome.record_count,
        replay=runtime.mode is RunMode.REPLAY,
    )
    return FeedPoll(
        feed=feed,
        ok=True,
        record_count=outcome.record_count,
        new_record_count=outcome.new_record_count,
        error=outcome.error,
        stale=outcome.stale,
    )


def _failed(
    runtime: "Runtime",
    feed: FeedId,
    at: datetime,
    reason: str,
    *,
    status: FeedStatus = FeedStatus.ERROR,
) -> FeedPoll:
    previous = runtime.live.health.get(feed)
    runtime.live.health[feed] = FeedHealth(
        feed=feed,
        status=status,
        cadence_s=runtime.settings.cadence_s(feed),
        last_attempt_at=at,
        last_success_at=previous.last_success_at if previous is not None else None,
        last_error=reason,
        record_count=previous.record_count if previous is not None else 0,
        replay=runtime.mode is RunMode.REPLAY,
    )
    return FeedPoll(feed=feed, ok=False, error=reason)


async def _poll_sigmets(runtime: "Runtime", at: datetime) -> _Outcome:
    fetched = await fetch_sigmets(runtime.source)
    held = runtime.live.sigmets
    current: dict[str, Sigmet] = {}
    new = 0
    for sigmet in fetched:
        key = sigmet.provenance.source_id
        kept = held.get(key)
        if kept is not None and _same_content(kept, sigmet):
            current[key] = kept
            continue
        current[key] = sigmet
        new += 1
        await runtime.store.put(Collection.SIGMETS, key, sigmet.model_dump(mode="json"))
    runtime.live.sigmets = current
    return _Outcome(len(fetched), new, _any_stale(fetched))


async def _poll_vonas(runtime: "Runtime", at: datetime) -> _Outcome:
    live = runtime.live
    window = timedelta(hours=runtime.settings.vona_window_h)
    fetched = await fetch_vonas(
        runtime.source,
        since=at - window,
        known_urls=frozenset(vona.provenance.url for vona in live.vonas.values()),
        known_ids=frozenset(
            vona.magma_id for vona in live.vonas.values() if vona.magma_id is not None
        ),
        max_pages=1 if live.vonas else COLD_START_VONA_PAGES,
    )
    new = await _merge(runtime, Collection.VONAS, live.vonas, _issued_by(runtime, fetched, at))
    live.vonas = {key: vona for key, vona in live.vonas.items() if vona.issued_at >= at - window}
    return _Outcome(len(live.vonas), new, _any_stale(fetched))


def _vaa_poller(feed: FeedId) -> Callable[["Runtime", datetime], Awaitable[_Outcome]]:
    async def poll_vaas(runtime: "Runtime", at: datetime) -> _Outcome:
        live = runtime.live
        # The Darwin bulletin URLs are fixed and their content changes, so they are never
        # "known"; advisory pages from the lists are fetched once.
        known = frozenset(
            vaa.provenance.url
            for vaa in live.vaas.values()
            if vaa.provenance.feed is feed and vaa.provenance.url not in DARWIN_BULLETIN_URLS
        )
        fetched = await fetch_vaas(
            runtime.source, feed, since=at - timedelta(hours=24), known_urls=known
        )
        new = await _merge(runtime, Collection.VAAS, live.vaas, _issued_by(runtime, fetched, at))
        cutoff = at - timedelta(hours=VAA_RETENTION_H)
        live.vaas = {key: vaa for key, vaa in live.vaas.items() if vaa.issued_at >= cutoff}
        count = sum(1 for vaa in live.vaas.values() if vaa.provenance.feed is feed)
        return _Outcome(count, new, _any_stale(fetched))

    return poll_vaas


async def _poll_tafs(runtime: "Runtime", at: datetime) -> _Outcome:
    icaos = taf_icaos(runtime)
    if not icaos:
        return _Outcome(0, 0, False)
    tafs = await fetch_tafs(runtime.source, icaos)
    new = 0
    for taf in tafs:
        held = runtime.live.tafs.get(taf.icao)
        if held is not None and _same_content(held, taf):
            continue
        runtime.live.tafs[taf.icao] = taf
        new += 1
        await runtime.store.put(Collection.TAFS, taf.icao, taf.model_dump(mode="json"))
    runtime.live.covered.setdefault(FeedId.TAF, set()).update(icaos)
    return _Outcome(len(tafs), new, _any_stale(tafs))


async def _poll_metars(runtime: "Runtime", at: datetime) -> _Outcome:
    icaos = taf_icaos(runtime)
    if not icaos:
        return _Outcome(0, 0, False)
    metars = await fetch_metars(runtime.source, icaos)
    new = 0
    for metar in metars:
        held = runtime.live.metars.get(metar.icao)
        if held is not None and _same_content(held, metar):
            continue
        runtime.live.metars[metar.icao] = metar
        new += 1
        await runtime.store.put(Collection.METARS, metar.icao, metar.model_dump(mode="json"))
    runtime.live.covered.setdefault(FeedId.METAR, set()).update(icaos)
    return _Outcome(len(metars), new, _any_stale(metars))


async def _poll_adsb(runtime: "Runtime", at: datetime) -> _Outcome:
    settings = runtime.settings
    # Expired first: a poll cut short by its time budget changes nothing after this line.
    runtime.live.adsb = [
        snapshot
        for snapshot in runtime.live.adsb
        if timeutil.age_s(snapshot.provenance.fetched_at, at) <= MAX_CACHED_COPY_AGE_S
    ]
    points = query_points(
        settings.region_preset, runtime.active_volcanoes(), settings.adsb_radius_nm
    )
    held: list[AdsbSnapshot] = []
    error: str | None = None
    try:
        fresh = await fetch_aircraft(runtime.source, points)
    except AdsbPointsFailed as exc:
        held = _held_snapshots(runtime.live.adsb, exc.failed_points)
        if not exc.snapshots:
            runtime.live.adsb = held
            raise
        fresh, error = exc.snapshots, exc.reason
    snapshots = [*fresh, *held]
    runtime.live.adsb = snapshots
    stale = error is not None or _any_stale(snapshots)
    if not stale:  # positions count as refreshed only when every point answered live
        runtime.live.adsb_at = at
    count = sum(len(snapshot.aircraft) for snapshot in snapshots)
    return _Outcome(count, len(fresh), stale, error)


async def _poll_winds(runtime: "Runtime", at: datetime) -> _Outcome:
    async def one(source: Source, volcano: Volcano) -> tuple[int, int, bool]:
        profiles = await fetch_winds(source, volcano.lat, volcano.lon)
        runtime.live.winds[volcano.id] = profiles
        forecast = WindForecast(volcano_id=volcano.id, profiles=profiles)
        await runtime.store.put(Collection.WINDS, volcano.id, forecast.model_dump(mode="json"))
        return len(profiles), len(profiles), _any_stale(profiles)

    return await _per_volcano(runtime, FeedId.WINDS, one)


async def _poll_frames(runtime: "Runtime", at: datetime) -> _Outcome:
    async def one(source: Source, volcano: Volcano) -> tuple[int, int, bool]:
        held = {frame.provenance.source_id for frame in runtime.live.frames.get(volcano.id, [])}
        pairs = await fetch_frames(source, volcano, nict=runtime.settings.nict_frames)
        new = 0
        for frame, png in pairs:
            if frame.provenance.source_id in held:
                continue
            await runtime.store.put_blob(frame.image_key, png, "image/png")
            await runtime.store.put(
                Collection.FRAMES, frame.provenance.source_id, frame.model_dump(mode="json")
            )
            new += 1
        frames = [frame for frame, _ in pairs]
        if frames or volcano.id not in runtime.live.frames:
            runtime.live.frames[volcano.id] = frames
        return len(frames), new, _any_stale(frames)

    return await _per_volcano(runtime, FeedId.FRAMES, one)


async def _poll_hsd(runtime: "Runtime", at: datetime) -> _Outcome:
    if not runtime.settings.science:
        raise ScienceUnavailable(HSD_OFF_NOTE)

    async def one(source: Source, volcano: Volcano) -> tuple[int, int, bool]:
        result = await run_btd(source, volcano, at, runtime.settings)
        if result is None:
            return 0, 0, False
        btd, png = result
        held = runtime.live.btd.get(volcano.id)
        if held is not None and held.provenance.source_id == btd.provenance.source_id:
            return 1, 0, btd.provenance.stale
        image_key = btd.image_key or btd_key(volcano.id, btd.scan_start)
        btd = btd.model_copy(update={"image_key": image_key})
        await runtime.store.put_blob(image_key, png, "image/png")
        await runtime.store.put(
            Collection.BTD, btd.provenance.source_id, btd.model_dump(mode="json")
        )
        runtime.live.btd[volcano.id] = btd
        return 1, 1, btd.provenance.stale

    return await _per_volcano(runtime, FeedId.HSD, one)


async def _per_volcano(
    runtime: "Runtime",
    feed: FeedId,
    fetch_one: Callable[[Source, Volcano], Awaitable[tuple[int, int, bool]]],
) -> _Outcome:
    """Run a per-volcano fetch for every active volcano; one failure does not stop the rest.

    The feed counts as failed only when no volcano got through; otherwise failures, skips
    and last-good copies make the outcome stale (a volcano without a fresh answer keeps its
    previous data) and are named in its error. Once a host times out or refuses a
    connection, the remaining volcanoes skip it instead of each waiting out the same timeouts.
    """
    volcanoes = runtime.active_volcanoes()
    source = _HostBreaker(runtime.source)
    totals = [0, 0]
    failures: list[tuple[Volcano, Exception]] = []
    skipped: list[Volcano] = []
    stale: list[Volcano] = []
    for volcano in volcanoes:
        try:
            count, new, was_stale = await fetch_one(source, volcano)
        except ScienceUnavailable:
            raise
        except _HostSkipped:
            skipped.append(volcano)
            continue
        except Exception as exc:  # an unreadable answer for one volcano, not the feed
            logger.warning("%s for %s failed: %s", feed.value, volcano.name, exc)
            failures.append((volcano, exc))
            continue
        totals[0] += count
        totals[1] += new
        if was_stale:
            stale.append(volcano)
        runtime.live.covered.setdefault(feed, set()).add(volcano.id)
    if failures and len(failures) + len(skipped) == len(volcanoes):
        raise failures[0][1]
    parts: list[str] = []
    if failures:
        named = "; ".join(f"{volcano.name}: {_failure_text(exc)}" for volcano, exc in failures)
        parts.append(f"{len(failures)} of {len(volcanoes)} volcanoes failed ({named})")
    if skipped:
        hosts = ", ".join(sorted(source.down))
        parts.append(f"{len(skipped)} skipped while {hosts} did not answer ({_names(skipped)})")
    if stale:
        parts.append(f"last good copy served for {_names(stale)}")
    error = "; ".join(parts) or None
    return _Outcome(totals[0], totals[1], error is not None, error)


def _failure_text(exc: Exception) -> str:
    return exc.reason if isinstance(exc, FetchError) else f"{type(exc).__name__}: {exc}"


def _names(volcanoes: Iterable[Volcano]) -> str:
    return ", ".join(volcano.name for volcano in volcanoes)


class _HostSkipped(FetchError):
    """Not sent: the host timed out or refused a connection earlier in the same poll."""


class _HostBreaker:
    """The runtime's source as one per-volcano poll uses it: after a host times out or
    refuses a connection (Open-Meteo hung for five minutes on 10 Oct), the poll's later
    requests to that host fail at once."""

    def __init__(self, inner: Source) -> None:
        self._inner = inner
        self.down: dict[str, str] = {}

    async def fetch(
        self, url: str, *, feed: FeedId, params: Mapping[str, str] | None = None
    ) -> FetchResult:
        full_url = build_url(url, params)
        host = urlsplit(full_url).hostname or ""
        if host in self.down:
            reason = f"skipped: {host} did not answer ({self.down[host]})"
            raise _HostSkipped(full_url, feed, reason)
        try:
            result = await self._inner.fetch(url, feed=feed, params=params)
        except FetchError as exc:
            self._note(host, exc.reason)
            raise
        if result.stale and result.error is not None:  # the cache answered after a failure
            self._note(host, result.error)
        return result

    async def aclose(self) -> None:
        """The runtime owns and closes the inner source."""

    def _note(self, host: str, reason: str) -> None:
        if _unreachable(reason):
            self.down[host] = reason


def _unreachable(reason: str) -> bool:
    """Whether ``HttpSource`` reported a timeout or refused connection: it words a transport
    failure as '<httpx exception name>: <detail>'."""
    error = getattr(httpx, reason.partition(":")[0], None)
    return isinstance(error, type) and issubclass(error, UNREACHABLE_ERRORS)


_POLLERS: Final[dict[FeedId, Callable[["Runtime", datetime], Awaitable[_Outcome]]]] = {
    FeedId.SIGMET: _poll_sigmets,
    FeedId.VONA: _poll_vonas,
    FeedId.VAAC_TOKYO: _vaa_poller(FeedId.VAAC_TOKYO),
    FeedId.VAAC_DARWIN: _vaa_poller(FeedId.VAAC_DARWIN),
    FeedId.TAF: _poll_tafs,
    FeedId.METAR: _poll_metars,
    FeedId.ADSB: _poll_adsb,
    FeedId.WINDS: _poll_winds,
    FeedId.FRAMES: _poll_frames,
    FeedId.HSD: _poll_hsd,
}


# --- helpers ----------------------------------------------------------------------------


async def _merge[R: (Vona, VaacAdvisory)](
    runtime: "Runtime", collection: Collection, held: dict[str, R], fetched: Sequence[R]
) -> int:
    """Add new or changed records to ``held`` and the store; returns how many were written."""
    written = 0
    for record in fetched:
        key = record.provenance.source_id
        kept = held.get(key)
        if kept is not None and _same_content(kept, record):
            continue
        held[key] = record
        written += 1
        await runtime.store.put(collection, key, record.model_dump(mode="json"))
    return written


def _issued_by[R: (Vona, VaacAdvisory)](
    runtime: "Runtime", records: Sequence[R], at: datetime
) -> list[R]:
    """In REPLAY, a snapshot recorded later than the replay clock lists notices that were not
    issued yet at replay time: they wait for the clock. LIVE keeps whatever a feed issued, so
    a feed's clock error never hides a notice."""
    if runtime.mode is not RunMode.REPLAY:
        return list(records)
    return [record for record in records if record.issued_at <= at + ISSUE_SLACK]


def _held_snapshots(
    previous: Sequence[AdsbSnapshot], failed: Sequence[AdsbQueryPoint]
) -> list[AdsbSnapshot]:
    """A failed point's previous answer stands in for it (an empty sky there would retire its
    flights' drafts) until it is older than a cached copy may be (``_poll_adsb`` expires it)."""
    keys = {_point_key(point) for point in failed}
    return [snapshot for snapshot in previous if _point_key(snapshot.query) in keys]


def _point_key(point: AdsbQueryPoint) -> tuple[float, float, int]:
    return point.lat, point.lon, point.radius_nm


def _same_content(a: TephraModel, b: TephraModel) -> bool:
    return a.model_dump(mode="json", exclude={"provenance"}) == b.model_dump(
        mode="json", exclude={"provenance"}
    )


def _any_stale(records: Iterable[_Record]) -> bool:
    return any(record.provenance.stale for record in records)
