"""The TEPHRA runtime: the services, the live picture, and the per-volcano pipeline.

One :class:`Runtime` lives in the process. Each tick (``tephra.scheduler.run_tick``) polls
the feeds that are due, then for every active volcano: situation and discrepancies ->
plume assessment (Gemini only behind the quota gate) -> hazard cone -> exposed flights ->
plan and draft for each newly exposed flight -> DRAFT advisories on the desk. The Wall is
built from memory and pushed over the event bus.

Writes are rationed for the Firestore free tier: feed records, assessments, plans,
advisories and audit entries are written when they change; the live picture (aircraft,
exposures, feed health, the Wall) is checkpointed at most every five minutes.
"""

import asyncio
import logging
import time
from collections.abc import Coroutine, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Final, Literal, NamedTuple

from pydantic import BaseModel, ValidationError
from pydantic.main import IncEx

from tephra.agents.budget import budget_view
from tephra.agents.dispatch_drafter import ai_failure, draft_advisory
from tephra.agents.exposure_planner import build_planner_context, plan_flight
from tephra.agents.llm import LlmBackend, LlmPart, get_llm
from tephra.agents.plume_reader import read_plume
from tephra.agents.satellite_reader import (
    SatelliteReading,
    is_current,
    plume_part,
    read_satellite,
    select_frames,
)
from tephra.config import (
    AIRLINE_CODE,
    AIRLINE_NAME,
    DISCLAIMER,
    NO_MODEL_LABEL,
    Settings,
    apply_process_env,
)
from tephra.desk import audit
from tephra.desk.approvals import SYSTEM_ACTOR, list_advisories, submit_draft, supersede
from tephra.desk.failures import record_failure
from tephra.feeds.adsb import merge_aircraft
from tephra.feeds.airports import AirportCatalogue, load_airports
from tephra.feeds.base import FetchError, HttpSource, Source
from tephra.feeds.registry import LiveData, disabled_reason, health_view, initial_health
from tephra.feeds.routes import RouteTable, load_routes
from tephra.feeds.sigmet import fetch_sigmets
from tephra.feeds.volcanoes import VolcanoCatalogue, load_volcanoes
from tephra.geo.cone import build_cone
from tephra.geo.exposure import find_exposed
from tephra.geo.reroute import coordinate_text
from tephra.geo.units import deg_to_compass, distance_nm, ft_to_fl
from tephra.models import (
    Advisory,
    AdvisoryStatus,
    AiFailure,
    Aircraft,
    AircraftFeatureProps,
    AirlineInfo,
    AuditAction,
    AviationColor,
    BtdOverlay,
    BtdResult,
    ExposedFlight,
    ExposureFeatureProps,
    FeedId,
    FrameProduct,
    FrameThumb,
    GeoLineString,
    HazardCone,
    LlmInfo,
    OperatorPolicy,
    Overlays,
    PlumeAssessment,
    PolicySummary,
    ReplayCase,
    RerouteFeatureProps,
    RerouteKind,
    RerouteOption,
    RunMode,
    SatelliteFrame,
    Severity,
    Sigmet,
    Situation,
    SituationCard,
    SourceCard,
    SseEvent,
    SupportingEvidence,
    SystemState,
    TickReport,
    TraceActor,
    TraceEvent,
    TraceStage,
    VaacAdvisory,
    VaacStep,
    Volcano,
    VolcanoFeatureProps,
    Vona,
    WallSnapshot,
    blob_url,
    dump_all,
    feature,
    feature_collection,
    point,
)
from tephra.policy import load_policy
from tephra.reconcile.discrepancies import (
    build_situation,
    evidence_state,
    find_active,
    select_records,
)
from tephra.recovery import decisions as recovery_decisions
from tephra.recovery.agent import recommend_recovery
from tephra.recovery.models import Closure, Schedule
from tephra.recovery.network import network_closures, run_lock
from tephra.recovery.schedule import ScheduleError, load_schedule
from tephra.replay.cases import (
    ReplaySource,
    case_path,
    replay_info,
    select_case,
    start_replay_clock,
    stop_replay_clock,
)
from tephra.scheduler import run_tick
from tephra.store import open_store
from tephra.store.base import Collection, Store, Where
from tephra.util import timeutil
from tephra.util.events import EventBus, get_bus
from tephra.util.hashing import sha256_json

__all__ = ["Runtime", "create_runtime"]

logger = logging.getLogger(__name__)

CHECKPOINT_S: Final = 300.0
OPEN_DRAFT_LIMIT: Final = 500
RESTORE_LIMIT: Final = 500
VAA_RESTORE_H: Final = 30
PLAN_RETRY_MIN: Final = (1, 5, 15)
"""Minutes before a flight whose planning raised is planned again: the first retry comes on
the next tick (a store fault that has passed), later ones back off so a lasting fault does
not spend a model call every tick. The last step repeats."""
REASK_UNCHANGED: Final = timedelta(hours=3)
"""An unchanged input goes back to the model only once its estimate's horizon has passed and
this long after it was asked: a lasting disagreement (Semeru's DIRECTION_MISMATCH held for
78 census hours) would otherwise cost a call every horizon."""
BTD_CREDIT: Final = "Himawari-9 data: JMA via NOAA (NODD), processed by TEPHRA."
SITUATION_CLOCK_FIELDS: Final[IncEx] = {
    "as_of": True,
    "discrepancies": {"__all__": {"magnitude", "summary"}},
}
"""Situation fields that move with the clock alone (a SILENCE counts its minutes): storing the
situation again for them would cost 1,440 writes a day per silent volcano."""

TraceLevel = Literal["info", "warn", "error"]


class _PlanFailure(NamedTuple):
    cone_id: str
    urgency: int
    attempts: int
    retry_at: datetime


@dataclass(eq=False)
class Runtime:
    settings: Settings
    store: Store
    bus: EventBus
    source: Source
    llm: LlmBackend
    catalogue: VolcanoCatalogue
    airports: AirportCatalogue
    routes: RouteTable
    policy: OperatorPolicy
    mode: RunMode
    replay_case: ReplayCase | None
    auto_replay: bool
    policy_summary: PolicySummary = field(init=False)
    live: LiveData = field(init=False, default_factory=LiveData)
    lock: asyncio.Lock = field(init=False, default_factory=asyncio.Lock, repr=False)
    tick_running: bool = field(init=False, default=False)
    situations: dict[str, Situation] = field(init=False, default_factory=dict)
    assessments: dict[str, PlumeAssessment] = field(init=False, default_factory=dict)
    cones: dict[str, HazardCone] = field(init=False, default_factory=dict)
    exposed: dict[str, ExposedFlight] = field(init=False, default_factory=dict)
    reroutes: dict[str, list[RerouteOption]] = field(init=False, default_factory=dict)
    """flight id -> the lateral options computed when the flight was planned"""
    satellite: dict[str, SatelliteReading] = field(init=False, default_factory=dict)
    """volcano id -> the newest Satellite Reader reading"""
    last_tick: TickReport | None = field(init=False, default=None)
    _planned: dict[str, tuple[str, int]] = field(init=False, default_factory=dict)
    """flight id -> (cone id, the most urgent bucket it was planned in for that cone)"""
    _plan_failures: dict[str, _PlanFailure] = field(init=False, default_factory=dict)
    """flight id -> its last planning error, until it is planned or leaves the cone"""
    _unexposed_since: dict[str, datetime] = field(init=False, default_factory=dict)
    """flight id -> since when an open draft's flight is seen outside every cone"""
    _unseen_since: dict[str, datetime] = field(init=False, default_factory=dict)
    """flight id -> since when an open draft's flight is missing from the ADS-B picture"""
    _digests: dict[str, str] = field(init=False, default_factory=dict)
    _quiet_ticks: int = field(init=False, default=0)
    _closed_airports: frozenset[str] | None = field(init=False, default=None)
    """RFA-network airports with a closure now or in the horizon, at the last recovery check"""
    _schedule: tuple[date, Schedule] | None = field(init=False, default=None)
    _live_source: Source | None = field(init=False, default=None)
    _snapshot: WallSnapshot | None = field(init=False, default=None)
    _replay_at: datetime | None = field(init=False, default=None)
    _persisted_exposures: set[str] = field(init=False, default_factory=set)
    _last_checkpoint: float | None = field(init=False, default=None)
    _tasks: set[asyncio.Task[None]] = field(init=False, default_factory=set, repr=False)

    def __post_init__(self) -> None:
        self.policy_summary = PolicySummary.of(self.policy)
        self.live.health = initial_health(
            self.settings, replay=self.mode is RunMode.REPLAY, recorded=self.recorded_feeds
        )

    @property
    def urgency_limits_min(self) -> tuple[int, int]:
        """With "inside now" and "later", entry within the policy's divert and hold times makes
        the urgency buckets, the same limits the rules apply: a flight is planned once per cone
        and bucket, and again when its entry moves to a more urgent bucket (a MONITOR given 40
        minutes out does not stand at 15 minutes)."""
        rules = self.policy.planner
        return rules.divert_within_min.value, rules.hold_within_min.value

    @property
    def recorded_feeds(self) -> frozenset[FeedId] | None:
        """Feeds the playing replay case holds; None when live."""
        if isinstance(self.source, ReplaySource):
            return frozenset(record.feed for record in self.source.case.records)
        return None

    # --- contract ------------------------------------------------------------------------

    async def tick(self, *, reason: str = "scheduler") -> TickReport:
        return await run_tick(self, reason=reason)

    async def system_state(self) -> SystemState:
        at = timeutil.now()
        drafts = await list_advisories(
            self.store, status=AdvisoryStatus.DRAFT, limit=OPEN_DRAFT_LIMIT
        )
        replay = None
        if self.mode is RunMode.REPLAY and self.replay_case is not None:
            replay = replay_info(self.replay_case, auto=self.auto_replay)
        return SystemState(
            mode=self.mode,
            now=at,
            server_time=timeutil.SystemClock().now(),
            replay=replay,
            llm=self._llm_info(),
            airline=AirlineInfo(code=AIRLINE_CODE, name=AIRLINE_NAME),
            disclaimer=DISCLAIMER,
            region=self.settings.region_preset,
            regions=self.settings.regions,
            feeds=health_view(self.live.health, at, self.settings),
            active_volcano_ids=sorted(self.live.active),
            exposed_count=len(self.exposed),
            draft_count=len(drafts),
            policy=self.policy_summary,
            last_tick=self.last_tick,
        )

    async def wall_snapshot(self) -> WallSnapshot:
        at = timeutil.now()
        situations = [self.situations[vid] for vid in sorted(self.situations)]
        colors = _color_codes(self.catalogue, self.live.vonas.values(), self.live.vaas.values())
        cones = [self.cones[vid] for vid in sorted(self.cones)]
        return WallSnapshot(
            generated_at=at,
            volcanoes=_volcano_features(self.catalogue, colors, set(self.live.active)),
            official=feature_collection(
                layer.to_feature() for item in situations for layer in item.official_layers
            ),
            cones=feature_collection(part for cone in cones for part in cone.to_features()),
            exposures=_exposure_features(self.exposed.values()),
            aircraft=_aircraft_features(self.aircraft(), self.exposed.values()),
            reroutes=_reroute_features(self.reroutes, self.exposed),
            situations=[self._situation_card(situation, at, colors) for situation in situations],
            overlays=Overlays(
                btd=[
                    _btd_overlay(s.btd, s.btd.image_key)
                    for s in situations
                    if s.btd is not None and s.btd.image_key is not None
                ],
                frames=[_frame_thumb(frame) for s in situations for frame in s.frames],
            ),
            satellite=[
                self.satellite[s.volcano.id].model_dump(mode="json")
                for s in situations
                if s.volcano.id in self.satellite
            ],
        )

    async def switch_mode(
        self, mode: RunMode, *, auto: bool = False, case: ReplayCase | None = None
    ) -> None:
        """``case`` is taken under the lock, with the switch: while a tick runs, or after a
        switch that failed, the REPLAY banner never names a case that is not playing."""
        async with self.lock:
            await self._switch(mode, auto=auto, case=case)

    async def aclose(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self.checkpoint(force=True)
        if self._live_source is not None:
            await self._live_source.aclose()
        await self.source.aclose()
        if self.mode is RunMode.REPLAY:
            stop_replay_clock()
        await self.store.aclose()

    # --- steps the scheduler runs, in tick order -----------------------------------------

    async def maybe_switch_mode(self, report: TickReport) -> None:
        """Auto-replay (``TEPHRA_AUTO_REPLAY=1``): enter a labelled REPLAY after enough quiet
        LIVE ticks; leave it as soon as a live VA SIGMET for a catalogue volcano is valid."""
        if not self.settings.auto_replay:
            return
        if self.mode is RunMode.LIVE and self._quiet_ticks >= self.settings.auto_replay_after_ticks:
            try:
                await self._switch(RunMode.REPLAY, auto=True)
            except (OSError, ValueError) as exc:
                self._quiet_ticks = 0
                report.notes.append(f"auto-replay unavailable: {exc}")
            else:
                report.notes.append("nothing active: switched to labelled REPLAY")
        elif self.mode is RunMode.REPLAY and self.auto_replay and await self._live_activity():
            await self._switch(RunMode.LIVE)
            report.notes.append("live VA SIGMET for a catalogue volcano: switched back to LIVE")
        report.mode = self.mode

    def follow_replay_clock(self, at: datetime, report: TickReport) -> None:
        """Start the picture afresh when the looping replay clock wraps to the recording's
        start: records from its end would otherwise stand in for its beginning, and every
        feed's last attempt would lie in the future, so none would be polled again."""
        if self.mode is not RunMode.REPLAY:
            return
        if self._replay_at is not None and at < self._replay_at:
            self._reset_picture()
            report.notes.append("replay clock looped: the recording plays again from the start")
            self.trace(
                TraceStage.SYSTEM,
                "system",
                "REPLAY looped: the recording plays again from the start",
                level="warn",
            )
        self._replay_at = at

    def refresh_active(self, at: datetime) -> dict[str, list[str]]:
        active = find_active(
            self.catalogue,
            sigmets=list(self.live.sigmets.values()),
            vonas=list(self.live.vonas.values()),
            vaas=list(self.live.vaas.values()),
            at=at,
            settings=self.settings,
        )
        for vid in sorted(active.keys() - self.live.active.keys()):
            reasons = "; ".join(active[vid])
            self.trace(
                TraceStage.SYSTEM,
                "code",
                f"{self._volcano_name(vid)} is active: {reasons}",
                volcano_id=vid,
            )
        for vid in sorted(self.live.active.keys() - active.keys()):
            self.trace(
                TraceStage.SYSTEM,
                "code",
                f"{self._volcano_name(vid)} is no longer active",
                volcano_id=vid,
            )
        self.live.active = active
        return active

    async def analyse(self, at: datetime, report: TickReport) -> None:
        for vid in list(self.situations):
            if vid not in self.live.active:
                self._forget(vid)
        for vid, reasons in sorted(self.live.active.items()):
            volcano = self.catalogue.get(vid)
            if volcano is None:
                continue
            try:
                await self._analyse_volcano(volcano, reasons, at, report)
            except Exception as exc:  # one volcano's failure must not blank the others
                logger.exception("analysis of %s failed", volcano.name)
                report.notes.append(f"{volcano.name}: analysis failed ({type(exc).__name__})")
                self.trace(
                    TraceStage.SYSTEM,
                    "system",
                    f"{volcano.name}: analysis failed; the previous picture is kept",
                    level="error",
                    volcano_id=vid,
                )

    async def run_exposures(self, at: datetime, report: TickReport) -> None:
        if self._positions_stale():
            # Nothing to draft from, and a flight missing from an old copy is no reason to
            # retire a dispatcher's pending draft: the picture waits for live positions.
            self.exposed = {
                fid: flight
                for fid, flight in self.exposed.items()
                if flight.volcano_id in self.cones
            }
            self._forget_absences()
            self._keep_current_reroutes()
            report.exposed_flights = len(self.exposed)
            report.notes.append(
                "ADS-B is stale: exposures and open drafts kept until positions refresh"
            )
            return
        settings = self.settings
        aircraft = self.aircraft()
        exposed: dict[str, ExposedFlight] = {}
        for cone in self.cones.values():
            for flight in find_exposed(
                cone,
                aircraft,
                at,
                lookahead_min=settings.exposure_lookahead_min,
                vertical_margin_ft=self.policy.exposure.vertical_margin_ft.value,
                hold_minutes=self.policy.fuel.hold_min.value,
            ):
                exposed[flight.id] = flight
        for flight in sorted(exposed.values(), key=_entry_order):
            if flight.id not in self.exposed:
                self.trace(
                    TraceStage.EXPOSURE,
                    "code",
                    _exposure_message(flight, self._volcano_name(flight.volcano_id)),
                    level="warn",
                    volcano_id=flight.volcano_id,
                    flight_id=flight.id,
                    detail={"minutes_to_entry": flight.minutes_to_entry, "cone_id": flight.cone_id},
                )
        self.exposed = exposed
        self._keep_current_reroutes()
        report.exposed_flights = len(exposed)

        open_drafts = await self._open_drafts()
        drafts_by_flight: dict[str, list[Advisory]] = {}
        for draft in open_drafts:
            drafts_by_flight.setdefault(draft.flight_id, []).append(draft)
        for flight in sorted(exposed.values(), key=_entry_order):
            await self._plan_once(flight, drafts_by_flight.get(flight.id, []), at, report)
        seen = {target.hex for target in aircraft}
        report.drafts_superseded += await self._retire_drafts(open_drafts, seen, at, report)
        self._planned = {fid: mark for fid, mark in self._planned.items() if fid in exposed}
        self._plan_failures = {
            fid: failure for fid, failure in self._plan_failures.items() if fid in exposed
        }

    async def run_recovery(self, at: datetime, report: TickReport) -> None:
        """Start the recovery agent once when the set of airports the hazard closes changes.

        The first look only records the set (a restart restores it from the bookkeeping); a
        later change to a non-empty set makes one draft plan on the lite budget, and no airport
        closed makes none. A Desk run in progress covers the change and is not repeated. The
        change is recorded before the agent runs, so a failed plan is not retried every tick.
        """
        if not self.settings.recovery_auto:
            return
        schedule = await self._rfa_schedule(at)
        if schedule is None:
            return
        closures = network_closures(
            self, schedule, at=at, tafs=self.live.tafs, metars=self.live.metars
        )
        closed = frozenset(closure.icao for closure in closures)
        if closed == self._closed_airports:
            return
        self._closed_airports = closed
        if not closed:
            self.trace(TraceStage.RECOVERY, "code", "No RFA airport is closed by the hazard now")
            return
        if run_lock(self).locked():
            return
        self.trace(
            TraceStage.RECOVERY,
            "code",
            f"Closed airports changed: {', '.join(sorted(closed))}; "
            "running the recovery agent once",
            level="warn",
            detail={"airports": sorted(closed)},
        )
        report.recovery_plans += 1
        # In the background: three CP-SAT solves and a model run must not hold the tick.
        self.spawn(self._recover(schedule, closures))

    async def _recover(self, schedule: Schedule, closures: Sequence[Closure]) -> None:
        try:
            async with run_lock(self):
                plan = await recommend_recovery(
                    schedule,
                    closures,
                    self.llm,
                    settings=self.settings,
                    policy=self.policy,
                    airports={airport.icao: airport for airport in self.airports.all()},
                    replay=self.mode is RunMode.REPLAY,
                    trace=self._sink,
                )
                await recovery_decisions.submit_plan(self.store, self.bus, plan)
            await self.publish_budget()
        except Exception:  # a background task's error would otherwise vanish
            logger.exception("automatic recovery plan failed")
            self.trace(
                TraceStage.RECOVERY, "system", "Automatic recovery plan failed", level="error"
            )

    async def _rfa_schedule(self, at: datetime) -> Schedule | None:
        """The fictional RFA day for ``at``'s date, read once a day."""
        held = self._schedule
        if held is not None and held[0] == at.date():
            return held[1]
        try:
            schedule = await asyncio.to_thread(load_schedule, self.settings.data_dir, at)
        except ScheduleError as exc:
            self.trace(
                TraceStage.RECOVERY,
                "system",
                f"No RFA schedule: {exc}; no recovery plans",
                level="error",
            )
            return None
        self._schedule = (at.date(), schedule)
        return schedule

    async def add_verified_notice(self, vona: Vona) -> None:
        """A pasted notice that passed every check joins the live picture like a VONA."""
        key = vona.provenance.source_id
        self.live.vonas[key] = vona
        await self.store.put(Collection.VONAS, key, vona.model_dump(mode="json"))

    def _keep_current_reroutes(self) -> None:
        """Reroutes only for flights still exposed to the cone they were computed for."""
        self.reroutes = {
            fid: options
            for fid, options in self.reroutes.items()
            if fid in self.exposed and options and options[0].cone_id == self.exposed[fid].cone_id
        }

    def count_quiet_tick(self) -> None:
        if self.mode is RunMode.LIVE and self.settings.auto_replay:
            quiet = not self.live.active and not self.exposed
            self._quiet_ticks = self._quiet_ticks + 1 if quiet else 0

    async def publish(self) -> None:
        snapshot = await self.wall_snapshot()
        state = await self.system_state()
        self._snapshot = snapshot
        bus = self.bus
        bus.publish(SseEvent.STATE, state)
        bus.publish(SseEvent.FEEDS, {"feeds": dump_all(state.feeds)})
        bus.publish(SseEvent.VOLCANOES, snapshot.volcanoes)
        bus.publish(SseEvent.OFFICIAL, snapshot.official)
        bus.publish(SseEvent.CONES, snapshot.cones)
        bus.publish(SseEvent.EXPOSURES, snapshot.exposures)
        bus.publish(SseEvent.REROUTES, snapshot.reroutes)
        bus.publish(SseEvent.AIRCRAFT, snapshot.aircraft)
        bus.publish(SseEvent.OVERLAYS, snapshot.overlays)
        for card in snapshot.situations:
            bus.publish(SseEvent.SITUATION, card)
        await self.publish_budget()

    async def publish_budget(self) -> None:
        """The day's model-call counts, after the tick's model calls (the Wall's AI tray)."""
        self.bus.publish(SseEvent.BUDGET, await budget_view(self.settings, self.llm))

    async def publish_live(self) -> None:
        """The between-ticks update after an extra ADS-B poll: aircraft, exposures, state."""
        self.bus.publish(
            SseEvent.AIRCRAFT, _aircraft_features(self.aircraft(), self.exposed.values())
        )
        self.bus.publish(SseEvent.EXPOSURES, _exposure_features(self.exposed.values()))
        self.bus.publish(SseEvent.STATE, await self.system_state())

    async def checkpoint(self, *, force: bool = False) -> None:
        """Persist the live picture, at most every :data:`CHECKPOINT_S` unless forced."""
        clock = time.monotonic()
        last = self._last_checkpoint
        if not force and last is not None and clock - last < CHECKPOINT_S:
            return
        self._last_checkpoint = clock
        try:
            await self._persist_live()
        except Exception:  # a checkpoint is a cache; losing one must not fail the tick
            logger.exception("checkpoint failed; the live picture stays in memory")

    # --- helpers the registry and scheduler use ------------------------------------------

    def active_volcanoes(self) -> list[Volcano]:
        found = (self.catalogue.get(vid) for vid in sorted(self.live.active))
        return [volcano for volcano in found if volcano is not None]

    def aircraft(self) -> list[Aircraft]:
        return merge_aircraft(self.live.adsb)

    def spawn(self, coroutine: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def trace(
        self,
        stage: TraceStage,
        actor: TraceActor,
        message: str,
        *,
        level: TraceLevel = "info",
        volcano_id: str | None = None,
        flight_id: str | None = None,
        detail: Mapping[str, Any] | None = None,
    ) -> TraceEvent:
        event = TraceEvent.new(
            stage,
            actor,
            message,
            level=level,
            volcano_id=volcano_id,
            flight_id=flight_id,
            detail=detail,
        )
        labelled = self._labelled(event)
        self.bus.publish(SseEvent.TRACE, labelled)
        return labelled

    async def restore(self) -> None:
        """Warm a LIVE runtime from the store after a restart.

        Official products come back with their original provenance, so their input hash is
        unchanged and a restart does not spend a Gemini call. Everything else refreshes on
        the first tick. A REPLAY always starts from its recording.
        """
        if self.mode is RunMode.REPLAY:
            return
        at = timeutil.now()
        for state in await self.store.list_feed_states():
            if state.replay or disabled_reason(state.feed, self.settings, replay=False):
                continue
            self.live.health[state.feed] = state
        window = timedelta(hours=self.settings.vona_window_h)
        sigmets = await self._restore_records(
            Collection.SIGMETS, Sigmet, Where("valid_to", ">=", timeutil.to_iso(at))
        )
        vonas = await self._restore_records(
            Collection.VONAS, Vona, Where("issued_at", ">=", timeutil.to_iso(at - window))
        )
        since = at - timedelta(hours=VAA_RESTORE_H)
        vaas = await self._restore_records(
            Collection.VAAS, VaacAdvisory, Where("issued_at", ">=", timeutil.to_iso(since))
        )
        self.live.sigmets = {record.provenance.source_id: record for record in sigmets}
        self.live.vonas = {record.provenance.source_id: record for record in vonas}
        self.live.vaas = {record.provenance.source_id: record for record in vaas}
        await self._restore_bookkeeping()
        await self._restore_readings()

    async def _restore_readings(self) -> None:
        """The newest Satellite Reader reading per volcano and the stored reroutes, so a restart
        neither re-reads a scan it already read nor loses the routes of flights still exposed
        (``_keep_current_reroutes`` drops those that no longer apply)."""
        docs = await self.store.query(
            Collection.SAT_READINGS, [], order_by="created_at", descending=True, limit=RESTORE_LIMIT
        )
        for doc in docs:
            try:
                reading = SatelliteReading.model_validate(doc)
            except ValidationError:
                logger.warning("ignoring unreadable stored satellite reading")
                continue
            if not reading.replay:
                self.satellite.setdefault(reading.volcano_id, reading)
        for doc in await self.store.list_docs(Collection.REROUTES, limit=RESTORE_LIMIT):
            try:
                option = RerouteOption.model_validate(doc)
            except ValidationError:
                logger.warning("ignoring unreadable stored reroute")
                continue
            self.reroutes.setdefault(option.flight_id, []).append(option)

    # --- per volcano ---------------------------------------------------------------------

    async def _analyse_volcano(
        self, volcano: Volcano, reasons: list[str], at: datetime, report: TickReport
    ) -> None:
        live = self.live
        sigmets, vonas, vaas = select_records(
            self.catalogue,
            volcano,
            sigmets=list(live.sigmets.values()),
            vonas=list(live.vonas.values()),
            vaas=list(live.vaas.values()),
            at=at,
            settings=self.settings,
        )
        situation = build_situation(
            volcano,
            active_reasons=reasons,
            sigmets=sigmets,
            vonas=vonas,
            vaas=vaas,
            winds=live.winds.get(volcano.id, []),
            frames=live.frames.get(volcano.id, []),
            btd=live.btd.get(volcano.id),
            at=at,
            mode=self.mode,
            settings=self.settings,
            feed_health=self.live.health,
        )
        previous = self.situations.get(volcano.id)
        self.situations[volcano.id] = situation
        if await self._write_on_change(
            Collection.SITUATIONS, volcano.id, situation, SITUATION_CLOCK_FIELDS
        ):
            self._trace_new_discrepancies(situation, previous)
        assessment = await self._assessment(situation, at, report)
        cone = build_cone(situation, assessment)
        self.cones[volcano.id] = cone
        if await self._write_on_change(Collection.CONES, volcano.id, cone, {"created_at"}):
            self.trace(
                TraceStage.CONE,
                "code",
                _cone_message(volcano, cone, len(situation.official_layers)),
                volcano_id=volcano.id,
                detail={"cone_id": cone.id, "assessment_id": assessment.id},
            )

    async def _assessment(
        self, situation: Situation, at: datetime, report: TickReport
    ) -> PlumeAssessment:
        """The quota gate in front of the Plume Reader (MODULES.md 5.7)."""
        volcano = situation.volcano
        previous = self.assessments.get(volcano.id)
        if previous is not None and _still_current(previous, situation.input_hash, at):
            return previous
        call_model = self._model_call_matters(situation)
        if not call_model:
            self.trace(
                TraceStage.PLUME,
                "code",
                f"{volcano.name}: no CAUTION or WARNING discrepancy, no HYPOTHESIS case and no "
                f"airline aircraft seen within {self.settings.adsb_radius_nm} NM; cone from "
                "official products only",
                volcano_id=volcano.id,
            )
        images = await self._images(situation) if call_model else []
        if call_model:
            situation = await self._with_satellite(situation, report)
        assessment = await read_plume(
            situation,
            self.llm,
            images=images,
            settings=self.settings,
            trace=self._sink,
            call_model=call_model,
        )
        report.assessments_run += 1
        self.assessments[volcano.id] = assessment
        await self.store.put(
            Collection.ASSESSMENTS, assessment.id, assessment.model_dump(mode="json")
        )
        if assessment.outcome == "MODEL_FAILED":
            await audit.record(
                self.store,
                actor=SYSTEM_ACTOR,
                action=AuditAction.AI_FAILED,
                after={"volcano_id": volcano.id, "assessment_id": assessment.id},
                input_hashes=[situation.input_hash],
                model_id=assessment.model_id,
                prompt_hash=assessment.prompt_hash,
                note="; ".join(assessment.validation_errors) or "model returned nothing usable",
            )
        return assessment

    async def _with_satellite(self, situation: Situation, report: TickReport) -> Situation:
        """The Satellite Reader, gated twice: it runs only when the Plume Reader is about to
        be asked about this volcano (the caller) and only when the newest frames are not the
        ones the last reading used. A reading made from the current frames, read or failed,
        is not repeated; its text goes to the Plume Reader as supporting evidence."""
        volcano = situation.volcano
        held = self.satellite.get(volcano.id)
        probe = [(frame, b"") for frame in self.live.frames.get(volcano.id, [])]
        if not is_current(held, volcano, probe):
            chosen = select_frames(volcano, probe)
            pairs: list[tuple[SatelliteFrame, bytes]] = []
            for frame, _ in chosen.values():
                blob = await self.store.get_blob(frame.image_key)
                if blob is not None:
                    pairs.append((frame, blob[0]))
            if not any(frame.product is FrameProduct.DUST_RGB for frame, _ in pairs):
                return situation
            held = await read_satellite(
                volcano,
                pairs,
                situation.official_layers,
                self.llm,
                replay=self.mode is RunMode.REPLAY,
                trace=self._sink,
            )
            report.satellite_reads += 1
            self.satellite[volcano.id] = held
            await self.store.put(Collection.SAT_READINGS, held.id, held.model_dump(mode="json"))
            self.bus.publish(SseEvent.SATELLITE, held)
            if held.status == "ai_unavailable":
                await audit.record(
                    self.store,
                    actor=SYSTEM_ACTOR,
                    action=AuditAction.AI_FAILED,
                    after={"volcano_id": volcano.id, "satellite_reading_id": held.id},
                    model_id=held.model_id,
                    prompt_hash=held.prompt_hash,
                    note=held.reason,
                )
            await self.publish_budget()
        part = plume_part(held) if held is not None else None
        if held is None or part is None or not is_current(held, volcano, probe):
            return situation
        evidence = SupportingEvidence(source_id=held.id, text=part.text or "")
        return situation.model_copy(update={"supporting": [evidence]})

    def _model_call_matters(self, situation: Situation) -> bool:
        if any(
            item.severity in (Severity.CAUTION, Severity.WARNING)
            for item in situation.discrepancies
        ):
            return True
        hypothesis = not situation.official_valid_now()
        if hypothesis and any(vona.ash_observed for vona in situation.vonas):
            return True
        vent = situation.volcano
        radius = self.settings.adsb_radius_nm
        return any(
            target.airline and distance_nm(vent.lat, vent.lon, target.lat, target.lon) <= radius
            for target in self.aircraft()
        )

    async def _images(self, situation: Situation) -> list[LlmPart]:
        # research/05 does not clear NICT's true colour imagery for the model step; the Wall
        # still shows it.
        keyed = [
            (frame.provenance.source_id, frame.image_key)
            for frame in situation.frames
            if frame.product is not FrameProduct.TRUE_COLOR
        ]
        if situation.btd is not None and situation.btd.image_key is not None:
            keyed.append((situation.btd.provenance.source_id, situation.btd.image_key))
        parts: list[LlmPart] = []
        for source_id, key in keyed:
            blob = await self.store.get_blob(key)
            if blob is None:
                continue
            data, mime_type = blob
            parts.append(LlmPart.of_image(data, label=source_id, mime_type=mime_type))
        return parts

    async def _plan_once(
        self, flight: ExposedFlight, drafts: Sequence[Advisory], at: datetime, report: TickReport
    ) -> None:
        """Plan a flight once per cone and urgency bucket; open drafts given when its entry
        was less urgent are replaced by the new one.

        The flight is marked planned only once planning has finished, so an error part-way
        (a store fault, say) never leaves it marked with no draft: it is planned again on the
        ``PLAN_RETRY_MIN`` schedule, or at once for a new cone or a more urgent entry."""
        cone = self.cones[flight.volcano_id]
        limits = self.urgency_limits_min
        urgency = _urgency(flight.inside_now, flight.minutes_to_entry, limits)
        planned = self._planned_urgency(flight.id, cone.id, drafts)
        if planned is not None and planned <= urgency:
            self._planned[flight.id] = (cone.id, planned)
            return
        failed = self._plan_failures.get(flight.id)
        if failed is not None and (failed.cone_id, failed.urgency) != (cone.id, urgency):
            failed = None  # a new cone or a new bucket: plan now, and count afresh
        if failed is not None and at < failed.retry_at:
            return
        outdated = [
            d for d in drafts if _urgency(d.inside_now, d.minutes_to_entry, limits) > urgency
        ]
        try:
            await self._plan_and_draft(flight, cone, urgency, at, report, outdated)
        except Exception as exc:
            logger.exception("planning %s failed", flight.id)
            attempts = 1 if failed is None else failed.attempts + 1
            delay = PLAN_RETRY_MIN[min(attempts, len(PLAN_RETRY_MIN)) - 1]
            retry_at = at + timedelta(minutes=delay)
            self._plan_failures[flight.id] = _PlanFailure(cone.id, urgency, attempts, retry_at)
            failure = type(exc).__name__
            report.notes.append(f"{flight.proxy_flight}: planning failed ({failure})")
            self.trace(
                TraceStage.PLANNER,
                "system",
                f"{flight.proxy_flight}: planning failed ({failure}); planned again at "
                f"{retry_at:%H%M}Z",
                level="error",
                volcano_id=flight.volcano_id,
                flight_id=flight.id,
            )
            return
        self._plan_failures.pop(flight.id, None)
        self._planned[flight.id] = (cone.id, urgency)

    def _planned_urgency(
        self, flight_id: str, cone_id: str, drafts: Sequence[Advisory]
    ) -> int | None:
        """The most urgent bucket the flight was planned in for this cone. An open draft for
        the cone counts: the marker is lost in a restart between checkpoints."""
        limits = self.urgency_limits_min
        found = [
            _urgency(d.inside_now, d.minutes_to_entry, limits)
            for d in drafts
            if d.cone_id == cone_id
        ]
        marker = self._planned.get(flight_id)
        if marker is not None and marker[0] == cone_id:
            found.append(marker[1])
        return min(found, default=None)

    async def _plan_and_draft(
        self,
        flight: ExposedFlight,
        cone: HazardCone,
        urgency: int,
        at: datetime,
        report: TickReport,
        outdated: Sequence[Advisory],
    ) -> None:
        situation = self.situations[flight.volcano_id]
        assessment = self.assessments[flight.volcano_id]
        ctx = build_planner_context(
            flight,
            cone,
            volcano_name=situation.volcano.name,
            airports=self.airports,
            tafs=self.live.tafs,
            at=at,
            policy=self.policy,
            routes=self.routes,
            situation=situation,
        )
        await self._store_reroutes(flight, ctx.reroutes)
        plan = await plan_flight(ctx, self.llm, settings=self.settings, trace=self._sink)
        await self.store.put(Collection.PLANS, plan.id, plan.model_dump(mode="json"))
        if plan.decision is None:
            reason = "; ".join(plan.validation_errors[:3]) or "NO PLAN"
            failure = ai_failure(
                ctx,
                stage="planner",
                reason=reason,
                model_id=plan.model_id,
                replay=self.mode is RunMode.REPLAY,
            )
            await self._record_failure(failure)
            return
        advisory = await draft_advisory(
            situation=situation,
            assessment=assessment,
            cone=cone,
            ctx=ctx,
            plan=plan,
            llm=self.llm,
            settings=self.settings,
            policy=self.policy,
            trace=self._sink,
        )
        if isinstance(advisory, AiFailure):
            await self._record_failure(advisory)
            return
        # Outdated drafts go only once the new one is stored: a refused or failed submit
        # leaves the flight its earlier card instead of none.
        advisory = advisory.model_copy(update={"urgency_bucket": urgency})
        created = await submit_draft(
            self.store, self.bus, advisory, replacing=[draft.id for draft in outdated]
        )
        if created is None:
            kept = "; the earlier draft stays up" if outdated else ""
            self.trace(
                TraceStage.DESK,
                "code",
                f"{flight.proxy_flight}: same advice as an open or just-approved advisory; "
                f"no new draft{kept}",
                volcano_id=flight.volcano_id,
                flight_id=flight.id,
            )
            return
        reason = (
            "INSIDE THE CONE NOW"
            if flight.inside_now
            else f"ENTRY NOW IN {flight.minutes_to_entry} MIN"
        )
        for draft in outdated:
            report.drafts_superseded += await self._supersede_draft(
                draft, reason, superseded_by=created.id
            )
        report.drafts_created += 1
        self.trace(
            TraceStage.DESK,
            "code",
            f"{flight.proxy_flight}: DRAFT {created.action.value} waiting for a dispatcher",
            volcano_id=flight.volcano_id,
            flight_id=flight.id,
            detail={"advisory_id": created.id},
        )

    async def _store_reroutes(
        self, flight: ExposedFlight, options: Sequence[RerouteOption]
    ) -> None:
        """Keep the lateral options computed for the flight: in the store (``reroutes``) and,
        for the Wall, in memory until the flight leaves the cone."""
        if not options:
            self.reroutes.pop(flight.id, None)
            return
        self.reroutes[flight.id] = list(options)
        for option in options:
            await self.store.put(Collection.REROUTES, option.id, option.model_dump(mode="json"))

    async def _record_failure(self, failure: AiFailure) -> None:
        """No plan or no draft: the flight goes to the Desk for a dispatcher, and outdated
        drafts stay up, since there is no newer advice to replace them."""
        if await record_failure(self.store, self.bus, failure) is None:
            return
        self.trace(
            TraceStage.DESK,
            "code",
            f"{failure.proxy_flight}: AI UNAVAILABLE ({failure.stage}); "
            "a dispatcher must handle this flight by hand",
            level="error",
            volcano_id=failure.volcano_id,
            flight_id=failure.flight_id,
            detail={"failure_id": failure.id, "reason": failure.reason},
        )

    async def _supersede_draft(
        self, draft: Advisory, reason: str, *, superseded_by: str | None = None
    ) -> bool:
        retired = await supersede(
            self.store, self.bus, draft.id, reason=reason, superseded_by=superseded_by
        )
        if retired is None:
            return False  # gone, or a dispatcher decided it meanwhile
        self.trace(
            TraceStage.DESK,
            "system",
            f"{draft.proxy_flight}: draft superseded ({reason.lower()})",
            volcano_id=draft.volcano_id,
            flight_id=draft.flight_id,
            detail={"advisory_id": draft.id},
        )
        return True

    async def _open_drafts(self) -> list[Advisory]:
        """Open drafts of the current mode: a replay's picture says nothing about the live
        desk's flights, nor the live picture about a replay's."""
        drafts = await list_advisories(
            self.store, status=AdvisoryStatus.DRAFT, limit=OPEN_DRAFT_LIMIT
        )
        replay = self.mode is RunMode.REPLAY
        return [draft for draft in drafts if draft.replay == replay]

    def _positions_stale(self) -> bool:
        """Every position held is a last-good copy, served after its point's live fetch
        failed."""
        snapshots = self.live.adsb
        return bool(snapshots) and all(snapshot.provenance.stale for snapshot in snapshots)

    async def _retire_drafts(
        self, open_drafts: Sequence[Advisory], seen: set[str], at: datetime, report: TickReport
    ) -> int:
        """Retire the open drafts of flights out of every cone, after the policy's grace time.

        A flight seen outside every cone (or whose volcano is no longer active) keeps its
        draft for ``drafts.unexposed_retire_min``; one missing from the ADS-B picture keeps it
        for ``drafts.position_lost_retire_min`` and is retired as POSITION LOST, never as no
        longer exposed: a dropped position says nothing about the ash. Only fresh positions
        count towards either time."""
        candidates = [draft for draft in open_drafts if draft.flight_id not in self.exposed]
        if not candidates or not self._adsb_fresh(at):
            self._forget_absences()
            if candidates:
                report.notes.append("ADS-B is stale: open drafts kept until positions refresh")
            return 0
        unseen = {draft.flight_id for draft in candidates if draft.hex not in seen}
        unexposed = {draft.flight_id for draft in candidates} - unseen
        self._unseen_since = {fid: self._unseen_since.get(fid, at) for fid in unseen}
        self._unexposed_since = {fid: self._unexposed_since.get(fid, at) for fid in unexposed}
        rules = self.policy.drafts
        retired = 0
        for draft in candidates:
            if draft.flight_id in unseen:
                lost = at - self._unseen_since[draft.flight_id]
                if lost < timedelta(minutes=rules.position_lost_retire_min.value):
                    continue
                reason = f"POSITION LOST FOR {int(lost.total_seconds() // 60)} MIN"
            else:
                away = at - self._unexposed_since[draft.flight_id]
                if away < timedelta(minutes=rules.unexposed_retire_min.value):
                    continue
                reason = (
                    "NO LONGER EXPOSED IF TRACK AND LEVEL ARE HELD"
                    if draft.volcano_id in self.live.active
                    else "VOLCANO NO LONGER ACTIVE"
                )
            retired += await self._supersede_draft(draft, reason)
        return retired

    def _forget_absences(self) -> None:
        """Grace times restart: stale or no positions are no evidence a flight has gone."""
        self._unexposed_since.clear()
        self._unseen_since.clear()

    def _adsb_fresh(self, at: datetime) -> bool:
        seen = self.live.adsb_at
        if seen is None:
            return False
        return (at - seen).total_seconds() <= self.settings.stale_after_s(FeedId.ADSB)

    def _trace_new_discrepancies(self, situation: Situation, previous: Situation | None) -> None:
        known = {item.id for item in previous.discrepancies} if previous is not None else set()
        for item in situation.discrepancies:
            if item.id in known:
                continue
            self.trace(
                TraceStage.DISCREPANCY,
                "code",
                f"{situation.volcano.name}: {item.kind.value} - {item.summary}",
                level="info" if item.severity is Severity.INFO else "warn",
                volcano_id=situation.volcano.id,
                detail={
                    "discrepancy_id": item.id,
                    "severity": item.severity.value,
                    "source_ids": item.source_ids,
                },
            )

    def _forget(self, volcano_id: str) -> None:
        self.situations.pop(volcano_id, None)
        self.assessments.pop(volcano_id, None)
        self.cones.pop(volcano_id, None)
        self.satellite.pop(volcano_id, None)

    def _volcano_name(self, volcano_id: str) -> str:
        volcano = self.catalogue.get(volcano_id)
        return volcano.name if volcano is not None else volcano_id

    def _sink(self, event: TraceEvent) -> None:
        self.bus.publish(SseEvent.TRACE, self._labelled(event))

    def _labelled(self, event: TraceEvent) -> TraceEvent:
        """A REPLAY trace line carries the label itself: the trace history (``/api/wall``)
        outlives a switch back to LIVE."""
        if self.mode is not RunMode.REPLAY:
            return event
        return event.model_copy(update={"detail": {**event.detail, "replay": True}})

    def _llm_info(self) -> LlmInfo:
        main = self.llm.model_id("main")
        if self.llm.name == "stub":
            return LlmInfo(backend="stub", model_id=main, label=NO_MODEL_LABEL)
        lite = self.llm.model_id("lite")
        label = main if main == lite else f"{main} + {lite}"
        return LlmInfo(backend=self.llm.name, model_id=main, label=label)

    # --- the Wall ------------------------------------------------------------------------

    def _situation_card(
        self, situation: Situation, at: datetime, colors: Mapping[str, AviationColor]
    ) -> SituationCard:
        volcano = situation.volcano
        cone = self.cones.get(volcano.id)
        return SituationCard(
            volcano_id=volcano.id,
            volcano_name=volcano.name,
            color_code=colors.get(volcano.id, AviationColor.UNKNOWN),
            active_reasons=situation.active_reasons,
            as_of=situation.as_of,
            cards=[
                _sigmet_card(situation, at),
                _vona_card(situation, at, self.settings.vona_window_h),
                _vaa_card(situation, at),
            ],
            discrepancies=situation.discrepancies,
            assessment=self.assessments.get(volcano.id),
            cone_id=cone.id if cone is not None else None,
            btd=situation.btd,
            frames=[_frame_thumb(frame) for frame in situation.frames],
            exposed_count=sum(1 for f in self.exposed.values() if f.volcano_id == volcano.id),
        )

    # --- mode switching ------------------------------------------------------------------

    async def _switch(self, mode: RunMode, *, auto: bool, case: ReplayCase | None = None) -> None:
        """Change mode. REPLAY plays ``case``, else the case playing, else
        ``TEPHRA_REPLAY_CASE`` or the newest recorded case; picking another case while
        replaying restarts the replay on it."""
        playing = self.source.case if isinstance(self.source, ReplaySource) else None
        previous = {"mode": self.mode.value, "case_id": playing.case_id if playing else None}
        if mode is RunMode.REPLAY:
            case = (
                case
                or self.replay_case
                or select_case(self.settings.data_dir, self.settings.replay_case)
            )
            if playing is not None and playing.case_id == case.case_id:
                return
            replay_source = ReplaySource(case_path(self.settings.data_dir, case.case_id), case)
            start_replay_clock(  # raises on a bad case
                case, speed=self.settings.replay_speed, begin=self.settings.replay_start
            )
            if playing is None:
                self._live_source = self.source
            else:
                await self.source.aclose()
            self.source = replay_source
            self.replay_case, self.auto_replay = case, auto
        else:
            if playing is None:
                return
            stop_replay_clock()
            await self.source.aclose()
            self.source = self._live_source or HttpSource.from_settings(self.settings)
            self._live_source = None
            self.replay_case, self.auto_replay = None, False
        self.mode = mode
        self._reset_picture()
        case_id = self.replay_case.case_id if self.replay_case is not None else None
        banner = replay_info(self.replay_case, auto=auto).banner if self.replay_case else None
        await audit.record(
            self.store,
            actor=SYSTEM_ACTOR,
            action=AuditAction.MODE_SWITCH,
            before=previous,
            after={"mode": mode.value, "case_id": case_id, "auto": auto},
            note=banner,
        )
        self.trace(
            TraceStage.SYSTEM,
            "system",
            banner if banner is not None else "LIVE: polling public feeds",
            level="warn" if mode is RunMode.REPLAY else "info",
            detail={"auto": auto, "case_id": case_id},
        )
        # The Wall's badge, banner and layers change now, not at the next tick's publish.
        await self.publish()

    def _reset_picture(self) -> None:
        """Nothing recorded and nothing live may mix: a mode switch starts a fresh picture."""
        self.live = LiveData(
            health=initial_health(
                self.settings, replay=self.mode is RunMode.REPLAY, recorded=self.recorded_feeds
            )
        )
        self.situations.clear()
        self.assessments.clear()
        self.cones.clear()
        self.exposed.clear()
        self.reroutes.clear()
        self.satellite.clear()
        self._closed_airports = None
        self._schedule = None
        self._planned.clear()
        self._plan_failures.clear()
        self._forget_absences()
        self._digests.clear()
        self._quiet_ticks = 0
        self._snapshot = None
        self._replay_at = None

    async def _live_activity(self) -> bool:
        source = self._live_source
        if source is None:
            return False
        try:
            sigmets = await fetch_sigmets(source)
        except FetchError as exc:
            logger.warning("auto-replay live SIGMET probe failed: %s", exc.reason)
            return False
        wall_clock = timeutil.SystemClock().now()
        valid = [sigmet for sigmet in sigmets if sigmet.is_valid(wall_clock)]
        active = find_active(
            self.catalogue, sigmets=valid, vonas=[], vaas=[], at=wall_clock, settings=self.settings
        )
        return bool(active)

    # --- persistence ---------------------------------------------------------------------

    async def _write_on_change(
        self, collection: Collection, doc_id: str, model: BaseModel, exclude: IncEx
    ) -> bool:
        """Write the document when its content (minus per-tick fields) changed."""
        digest = sha256_json(model.model_dump(mode="json", exclude=exclude))
        key = f"{collection.value}/{doc_id}"
        if self._digests.get(key) == digest:
            return False
        await self.store.put(collection, doc_id, model.model_dump(mode="json"))
        self._digests[key] = digest
        return True

    async def _persist_live(self) -> None:
        for state in self.live.health.values():
            await self._write_on_change(Collection.FEED_STATE, state.feed.value, state, {"age_s"})
        await self.store.put(Collection.ADSB, "latest", {"snapshots": dump_all(self.live.adsb)})
        for flight in self.exposed.values():
            await self._write_on_change(Collection.EXPOSURES, flight.id, flight, set())
        for gone in sorted(self._persisted_exposures - self.exposed.keys()):
            await self.store.delete(Collection.EXPOSURES, gone)
            self._digests.pop(f"{Collection.EXPOSURES.value}/{gone}", None)
        self._persisted_exposures = set(self.exposed)
        if self._snapshot is not None:
            await self.store.put(Collection.WALL, "current", self._snapshot.model_dump(mode="json"))
        await self.store.put(Collection.RUNTIME, "state", self._bookkeeping())

    def _bookkeeping(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "auto_replay": self.auto_replay,
            "case_id": self.replay_case.case_id if self.replay_case is not None else None,
            "quiet_ticks": self._quiet_ticks,
            "closed_airports": None
            if self._closed_airports is None
            else sorted(self._closed_airports),
            "planned": {
                fid: [cone_id, urgency] for fid, (cone_id, urgency) in self._planned.items()
            },
            "assessment_ids": {vid: item.id for vid, item in self.assessments.items()},
            "last_tick": self.last_tick.model_dump(mode="json") if self.last_tick else None,
            "saved_at": timeutil.to_iso(timeutil.now()),
        }

    async def _restore_bookkeeping(self) -> None:
        doc = await self.store.get(Collection.RUNTIME, "state")
        if doc is None or doc.get("mode") != RunMode.LIVE.value:
            return
        self._quiet_ticks = int(doc.get("quiet_ticks") or 0)
        closed = doc.get("closed_airports")
        self._closed_airports = frozenset(map(str, closed)) if isinstance(closed, list) else None
        self._planned = _planned_marks(doc.get("planned"))
        for vid, assessment_id in (doc.get("assessment_ids") or {}).items():
            stored = await self.store.get(Collection.ASSESSMENTS, str(assessment_id))
            if stored is None:
                continue
            try:
                self.assessments[str(vid)] = PlumeAssessment.model_validate(stored)
            except ValidationError:
                logger.warning("ignoring unreadable stored assessment %s", assessment_id)

    async def _restore_records[R: (Sigmet, Vona, VaacAdvisory)](
        self, collection: Collection, model: type[R], where: Where
    ) -> list[R]:
        docs = await self.store.query(collection, [where], limit=RESTORE_LIMIT)
        records: list[R] = []
        for doc in docs:
            try:
                record = model.model_validate(doc)
            except ValidationError:
                logger.warning("ignoring unreadable stored %s document", collection.value)
                continue
            if not record.provenance.replay:
                records.append(record)
        return records


async def create_runtime(settings: Settings) -> Runtime:
    """Build the process-wide runtime (composition root; settings come from the caller)."""
    apply_process_env(settings)
    policy = await asyncio.to_thread(load_policy, settings.data_dir)
    catalogue = await asyncio.to_thread(load_volcanoes, settings.data_dir)
    airports = await asyncio.to_thread(
        load_airports, settings.data_dir, min_runway_m=policy.alternates.min_runway_m.value
    )
    routes = await asyncio.to_thread(load_routes, settings.data_dir)
    replay_case: ReplayCase | None = None
    source: Source
    if settings.mode is RunMode.REPLAY:
        replay_case = select_case(settings.data_dir, settings.replay_case)
        source = ReplaySource(case_path(settings.data_dir, replay_case.case_id), replay_case)
        start_replay_clock(replay_case, speed=settings.replay_speed, begin=settings.replay_start)
    else:
        source = HttpSource.from_settings(settings)
    runtime = Runtime(
        settings=settings,
        store=open_store(settings),
        bus=get_bus(),
        source=source,
        llm=get_llm(settings),
        catalogue=catalogue,
        airports=airports,
        routes=routes,
        policy=policy,
        mode=settings.mode,
        replay_case=replay_case,
        auto_replay=False,
    )
    await runtime.restore()
    return runtime


# --- quota and planning rules (pure) ----------------------------------------------------


def _still_current(assessment: PlumeAssessment, input_hash: str, at: datetime) -> bool:
    """The same input keeps its assessment through the estimate's horizon, and past it until
    :data:`REASK_UNCHANGED` has gone by since the ask."""
    if assessment.input_hash != input_hash:
        return False
    keep = max(timedelta(hours=assessment.estimate.horizon_h), REASK_UNCHANGED)
    return at < assessment.created_at + keep


def _urgency(inside_now: bool, minutes_to_entry: int, limits: Sequence[int]) -> int:
    """0 inside the cone now; otherwise 1 plus the number of limits the entry lies beyond."""
    if inside_now:
        return 0
    return 1 + sum(minutes_to_entry > limit for limit in limits)


def _planned_marks(stored: object) -> dict[str, tuple[str, int]]:
    """The bookkeeping's ``planned`` map; an entry in another layout is dropped (the open
    drafts still show what was planned)."""
    if not isinstance(stored, dict):
        return {}
    return {
        str(fid): (str(mark[0]), mark[1])
        for fid, mark in stored.items()
        if isinstance(mark, list) and len(mark) == 2 and isinstance(mark[1], int)
    }


# --- Wall builders (pure) ---------------------------------------------------------------


def _entry_order(flight: ExposedFlight) -> tuple[int, str]:
    return flight.minutes_to_entry, flight.id


def _fl_text(ft: int | None) -> str:
    if ft is None:
        return "NOT STATED"
    return "SFC" if ft <= 0 else f"FL{ft_to_fl(ft):03d}"


def _band_text(base_ft: int | None, top_ft: int | None) -> str:
    return f"{_fl_text(base_ft)}/{_fl_text(top_ft)}"


def _movement_text(
    toward_deg: float | None, speed_kt: float | None, *, stationary: bool = False
) -> str:
    if stationary:
        return "STNR"
    if toward_deg is None:
        return "NOT STATED"
    text = f"MOV {deg_to_compass(toward_deg)}"
    return f"{text} {speed_kt:g} KT" if speed_kt is not None else text


def _exposure_message(flight: ExposedFlight, volcano_name: str) -> str:
    who = f"{flight.proxy_flight} ({flight.callsign or flight.hex.upper()})"
    level = _fl_text(flight.alt_baro_ft)
    if flight.inside_now:
        return f"{who} is inside the {volcano_name} cone at {level}"
    return (
        f"{who} enters the {volcano_name} cone in {flight.minutes_to_entry} min at {level} "
        "if track and level are held"
    )


def _cone_message(volcano: Volcano, cone: HazardCone, official_count: int) -> str:
    band = _band_text(cone.base_ft, cone.top_ft)
    return f"{volcano.name}: cone {cone.label}, {band}, {official_count} official layer(s)"


def _color_codes(
    catalogue: VolcanoCatalogue, vonas: Iterable[Vona], vaas: Iterable[VaacAdvisory]
) -> dict[str, AviationColor]:
    """Latest colour code per volcano: the observatory's VONA wins over a VAA's copy."""
    colors: dict[str, AviationColor] = {}
    for vaa in sorted(vaas, key=lambda item: item.issued_at):
        volcano = _vaa_volcano(catalogue, vaa)
        if volcano is not None and vaa.aviation_color not in (None, AviationColor.UNKNOWN):
            colors[volcano.id] = vaa.aviation_color
    for vona in sorted(vonas, key=lambda item: item.issued_at):
        volcano = _vona_volcano(catalogue, vona)
        if volcano is not None and vona.color_code is not AviationColor.UNKNOWN:
            colors[volcano.id] = vona.color_code
    return colors


def _vona_volcano(catalogue: VolcanoCatalogue, vona: Vona) -> Volcano | None:
    found = catalogue.by_magma_code(vona.volcano_code) if vona.volcano_code else None
    return found or catalogue.resolve(vona.volcano_name)


def _vaa_volcano(catalogue: VolcanoCatalogue, vaa: VaacAdvisory) -> Volcano | None:
    found = catalogue.get(vaa.volcano_number) if vaa.volcano_number else None
    return found or catalogue.resolve(vaa.volcano_name)


def _volcano_features(
    catalogue: VolcanoCatalogue, colors: Mapping[str, AviationColor], active: set[str]
) -> dict[str, Any]:
    features = []
    for volcano in catalogue.all():
        color = colors.get(volcano.id, AviationColor.UNKNOWN)
        label = volcano.name if color is AviationColor.UNKNOWN else f"{volcano.name} {color.value}"
        props = VolcanoFeatureProps(
            id=volcano.id,
            name=volcano.name,
            color_code=color,
            active=volcano.id in active,
            vaac=volcano.vaac,
            summit_elev_ft=volcano.summit_elev_ft,
            label=label,
        )
        features.append(feature(point(volcano.lat, volcano.lon), props, feature_id=volcano.id))
    return feature_collection(features)


def _aircraft_features(
    aircraft: Sequence[Aircraft], exposed: Iterable[ExposedFlight]
) -> dict[str, Any]:
    earliest: dict[str, ExposedFlight] = {}
    for flight in exposed:
        held = earliest.get(flight.hex)
        if held is None or flight.minutes_to_entry < held.minutes_to_entry:
            earliest[flight.hex] = flight
    features = []
    for target in aircraft:
        hit = earliest.get(target.hex)
        props = AircraftFeatureProps(
            hex=target.hex,
            callsign=target.callsign,
            proxy_flight=target.proxy_flight,
            type_icao=target.type_icao,
            alt_baro_ft=target.alt_baro_ft,
            nav_altitude_mcp_ft=target.nav_altitude_mcp_ft,
            gs_kt=target.gs_kt,
            track_deg=target.track_deg,
            observed_at=target.observed_at,
            exposed=hit is not None,
            minutes_to_entry=hit.minutes_to_entry if hit is not None else None,
            volcano_id=hit.volcano_id if hit is not None else None,
            label=_aircraft_label(target, hit),
        )
        features.append(feature(point(target.lat, target.lon), props, feature_id=target.hex))
    return feature_collection(features)


def _aircraft_label(target: Aircraft, hit: ExposedFlight | None) -> str:
    name = target.proxy_flight if target.airline else (target.callsign or target.hex.upper())
    if target.alt_baro_ft is not None:
        name += f" {_fl_text(target.alt_baro_ft)}"
    if hit is None:
        return name
    return f"{name} INSIDE" if hit.inside_now else f"{name} +{hit.minutes_to_entry} MIN"


def _exposure_features(exposed: Iterable[ExposedFlight]) -> dict[str, Any]:
    features = []
    for flight in sorted(exposed, key=_entry_order):
        for kind in ("path", "entry"):
            props = ExposureFeatureProps(
                flight_id=flight.id,
                proxy_flight=flight.proxy_flight,
                volcano_id=flight.volcano_id,
                kind=kind,
                minutes_to_entry=flight.minutes_to_entry,
            )
            geometry = (
                GeoLineString(coordinates=flight.path)
                if kind == "path"
                else point(flight.entry_lat, flight.entry_lon)
            )
            features.append(feature(geometry, props, feature_id=f"{flight.id}#{kind}"))
    return feature_collection(features)


def _reroute_features(
    reroutes: Mapping[str, Sequence[RerouteOption]], exposed: Mapping[str, ExposedFlight]
) -> dict[str, Any]:
    """Each option with a path: the path as a LineString and every turn point as a Point.

    Options with no path (no route, level outside the band) have nothing to draw.
    """
    features: list[dict[str, Any]] = []
    for flight in sorted(exposed.values(), key=_entry_order):
        for option in reroutes.get(flight.id, ()):
            if len(option.path) < 2:
                continue
            labels = [coordinate_text(lat, lon) for lon, lat in option.waypoints]
            shared = {
                "flight_id": flight.id,
                "proxy_flight": flight.proxy_flight,
                "volcano_id": flight.volcano_id,
                "kind": option.kind,
                "status": option.status,
                "route_string": option.route_string,
                "extra_nm": option.extra_nm,
                "extra_min": option.extra_min,
                "side": option.side,
            }
            name = "REJOIN" if option.kind is RerouteKind.REJOIN_TRACK else "DIRECT"
            extra = f" +{option.extra_nm:.0f} NM" if option.extra_nm is not None else ""
            path = RerouteFeatureProps(
                **shared,
                feature="path",
                label=f"{flight.proxy_flight} {name}{extra}",
                waypoint_labels=labels,
            )
            features.append(
                feature(
                    GeoLineString(coordinates=option.path), path, feature_id=f"{option.id}#path"
                )
            )
            for index, (position, label) in enumerate(zip(option.waypoints, labels, strict=True)):
                props = RerouteFeatureProps(**shared, feature="waypoint", label=label)
                geometry = point(position[1], position[0])
                features.append(feature(geometry, props, feature_id=f"{option.id}#wp{index + 1}"))
    return feature_collection(features)


def _btd_overlay(btd: BtdResult, image_key: str) -> BtdOverlay:
    return BtdOverlay(
        source_id=btd.provenance.source_id,
        volcano_id=btd.volcano_id,
        image_url=blob_url(image_key),
        corners=btd.bbox.corners_lonlat(),
        scan_start=btd.scan_start,
        indicator=btd.indicator,
        negative_fraction=btd.negative_fraction,
        caption=(
            f"Split-window BTD {btd.band_pair}: {btd.indicator.value}, "
            f"{btd.negative_fraction:.1%} of pixels below {btd.threshold_k:g} K. "
            "An indicator, not detection; a silent result is not evidence of no ash. "
            f"{BTD_CREDIT}"
        ),
    )


def _frame_thumb(frame: SatelliteFrame) -> FrameThumb:
    return FrameThumb(
        source_id=frame.provenance.source_id,
        volcano_id=frame.volcano_id,
        product=frame.product,
        observed_at=frame.observed_at,
        image_url=blob_url(frame.image_key),
        corners=frame.bbox.corners_lonlat() if frame.bbox is not None else None,
        caption=frame.caption,
    )


def _source_card(
    kind: Literal["SIGMET", "VONA", "VAA"],
    record: Sigmet | Vona | VaacAdvisory,
    others: Sequence[Sigmet | Vona | VaacAdvisory],
    situation: Situation,
    at: datetime,
    *,
    title: str,
    issued_at: datetime | None,
    fields: dict[str, str],
) -> SourceCard:
    provenance = record.provenance
    return SourceCard(
        kind=kind,
        missing=False,
        evidence=evidence_state(record, situation.volcano, at),
        source_id=provenance.source_id,
        title=title,
        issued_at=issued_at,
        valid_from=provenance.valid_from,
        valid_to=provenance.valid_to,
        fetched_at=provenance.fetched_at,
        sha256_short=provenance.sha256_short,
        url=provenance.url,
        raw_text=record.raw_text,
        stale=provenance.stale,
        stale_age_s=provenance.stale_age_s,
        display_fields=fields,
        discrepancy_ids=[
            item.id for item in situation.discrepancies if provenance.source_id in item.source_ids
        ],
        extra_source_ids=[other.provenance.source_id for other in others],
    )


def _sigmet_card(situation: Situation, at: datetime) -> SourceCard:
    records = sorted(
        situation.sigmets,
        key=lambda sigmet: (sigmet.valid_from, sigmet.provenance.source_id),
        reverse=True,
    )
    if not records:
        return SourceCard(
            kind="SIGMET", missing=True, missing_note="No valid VA SIGMET", title="SIGMET"
        )
    latest = records[0]
    if latest.observed_at is not None:
        observed = f"OBS {timeutil.hhmmz(latest.observed_at)}"
    else:
        observed = "FCST" if latest.observed is False else "NOT STATED"
    fields = {
        "FIR": latest.fir_id,
        "Band": _band_text(latest.base_ft, latest.top_ft),
        "Movement": _movement_text(
            latest.movement_toward_deg, latest.movement_speed_kt, stationary=latest.stationary
        ),
        "Observed": observed,
        "Valid": f"{timeutil.ddhhmmz(latest.valid_from)}-{timeutil.ddhhmmz(latest.valid_to)}",
    }
    if latest.intensity_change:
        fields["Change"] = latest.intensity_change
    if latest.cancelled:
        fields["Status"] = "CANCELLED"
    return _source_card(
        "SIGMET",
        latest,
        records[1:],
        situation,
        at,
        title=f"SIGMET {latest.fir_id} {latest.series_id}",
        issued_at=latest.provenance.issued_at,
        fields=fields,
    )


def _vona_card(situation: Situation, at: datetime, window_h: float) -> SourceCard:
    records = sorted(situation.vonas, key=lambda vona: vona.issued_at, reverse=True)
    if not records:
        note = f"No VONA in the last {window_h:g} h"
        return SourceCard(kind="VONA", missing=True, missing_note=note, title="VONA")
    latest = records[0]
    if latest.cloud_top_ft is not None:
        top = f"{latest.cloud_top_ft:,} FT AMSL"
        if latest.cloud_top_m is not None:
            top += f" ({latest.cloud_top_m:,} M)"
    else:
        top = "NOT GIVEN"
    movement = latest.movement_text or _movement_text(latest.movement_toward_deg, None)
    fields = {
        "Colour code": latest.color_code.value,
        "Ash": "OBSERVED" if latest.ash_observed else "NOT OBSERVED",
        "Cloud top": top,
        "Movement": movement,
        "Issued": timeutil.slash_dtg(latest.issued_at),
    }
    if latest.source_text:
        fields["Source"] = latest.source_text
    return _source_card(
        "VONA",
        latest,
        records[1:],
        situation,
        at,
        title=f"VONA {latest.volcano_name.upper()} {timeutil.slash_dtg(latest.issued_at)}",
        issued_at=latest.issued_at,
        fields=fields,
    )


def _vaa_card(situation: Situation, at: datetime) -> SourceCard:
    records = sorted(situation.vaas, key=lambda vaa: vaa.issued_at, reverse=True)
    if not records:
        return SourceCard(
            kind="VAA", missing=True, missing_note=_missing_vaa_note(situation, at), title="VAA"
        )
    latest = records[0]
    observation = latest.observation
    layers = observation.layers if observation is not None else []
    fields = {
        "VAAC": latest.vaac.value,
        "Observation": _observation_text(observation),
        "Band": _band_text(
            min((layer.base_ft for layer in layers), default=None),
            max((layer.top_ft for layer in layers), default=None),
        ),
        "Movement": _movement_text(layers[0].movement_toward_deg, layers[0].movement_speed_kt)
        if layers
        else "NOT STATED",
        "Colour code": latest.aviation_color.value if latest.aviation_color else "NOT GIVEN",
        "Next advisory": "NO FURTHER ADVISORIES"
        if latest.final
        else (latest.next_advisory_text or "NOT STATED"),
        "Valid until": timeutil.ddhhmmz(latest.valid_until()),
    }
    return _source_card(
        "VAA",
        latest,
        records[1:],
        situation,
        at,
        title=f"VAA {latest.vaac.value} {latest.advisory_nr}",
        issued_at=latest.issued_at,
        fields=fields,
    )


def _observation_text(step: VaacStep | None) -> str:
    if step is None:
        return "NONE"
    if step.not_identifiable:
        return "VA NOT IDENTIFIABLE"
    if step.no_ash_expected:
        return "NO VA EXP"
    if step.not_available:
        return "NOT AVBL"
    if not step.layers:
        return "NO LAYER GIVEN"
    return "EST" if step.estimated else "OBS"


def _missing_vaa_note(situation: Situation, at: datetime) -> str:
    with_ash = sorted(
        (vona for vona in situation.vonas if vona.ash_observed),
        key=lambda vona: vona.issued_at,
        reverse=True,
    )
    if not with_ash:
        return "No VAA in the last 24 h"
    latest = with_ash[0]
    minutes = max(0, int(timeutil.minutes_between(latest.issued_at, at)))
    return f"No VAA since VONA {timeutil.hhmmz(latest.issued_at)} ({minutes} min)"
