"""The TEPHRA runtime: the services, the live picture, and the per-volcano pipeline.

One :class:`Runtime` lives in the process. Each tick (``tephra.scheduler.run_tick``) polls
the feeds that are due, then for every active volcano: situation and discrepancies ->
plume assessment (Gemini only behind the quota gate) -> hazard cone -> exposed flights ->
plan and draft for each newly exposed flight -> DRAFT advisories on the desk. The Wall is
built from memory and pushed over the event bus.

Writes are rationed for the Firestore free tier: feed records, assessments, plans,
advisories and audit entries are written when they change; feed health and the bookkeeping
in ``runtime/state`` are checkpointed at most every five minutes. Aircraft, exposures and the
Wall are not stored: they rebuild from the feeds on the first tick after a restart.

A database error never drops a record already in memory and never stops a tick: the record
waits in ``unsaved`` for the next checkpoint, the step that needed a read is skipped for the
tick (an unread list is never taken as empty), and ``store_health`` says so on the Wall.
"""

import asyncio
import json
import logging
import math
import os
import time
import uuid
from collections import deque
from collections.abc import Awaitable, Coroutine, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Final, Literal, NamedTuple

import shapely
from pydantic import BaseModel, ValidationError
from pydantic.main import IncEx

from tephra.agents.answers import AiAnswers, AnswerScope, NotOnHand, Question
from tephra.agents.budget import BudgetView, budget_view
from tephra.agents.dispatch_drafter import ai_failure, draft_advisory, drafter_question
from tephra.agents.duty_officer import coordinator_question
from tephra.agents.exposure_planner import (
    build_planner_context,
    cone_version,
    plan_flight,
    planner_question,
)
from tephra.agents.llm import LlmBackend, LlmPart, get_llm
from tephra.agents.plume_reader import plume_question, read_plume, reused_assessment
from tephra.agents.quota import QuotaLedger
from tephra.agents.satellite_reader import (
    SatelliteReading,
    is_current,
    kept_reading,
    plume_part,
    read_satellite,
    select_frames,
)
from tephra.ai_worker import AiWorker
from tephra.config import (
    AIRLINE_CODE,
    AIRLINE_NAME,
    DISCLAIMER,
    NO_MODEL_LABEL,
    Settings,
    apply_process_env,
)
from tephra.desk import audit, connections, crew_reports, sample_feed
from tephra.desk.approvals import SYSTEM_ACTOR, submit_draft, supersede
from tephra.desk.crew_reports import CheckedEntry, CrewEntry, FixHistory, FixLookup
from tephra.desk.failures import (
    DRAFT_WAITING,
    LIST_WINDOW,
    NEWER_FAILURE,
    REPLAY_RUN_ENDED,
    close_failure,
    list_failures,
    of_run,
    record_failure,
)
from tephra.duty import DeskUnreachable
from tephra.feeds.adsb import merge_aircraft
from tephra.feeds.airports import AirportCatalogue, load_airports
from tephra.feeds.base import FetchError, HttpSource, Source
from tephra.feeds.registry import (
    NOT_RECORDED_NOTE,
    VONA_OFF_NOTE,
    LiveData,
    disabled_reason,
    health_view,
    initial_health,
    save_unsaved,
)
from tephra.feeds.routes import (
    RouteTable,
    cross_track_nm,
    great_circle,
    load_routes,
    route_features,
)
from tephra.feeds.sigmet import fetch_sigmets
from tephra.feeds.volcanoes import VolcanoCatalogue, load_volcanoes
from tephra.feeds.winds import fetch_winds
from tephra.geo.cone import build_cone, geometry_to_shape
from tephra.geo.exposure import find_exposed
from tephra.geo.reroute import coordinate_text
from tephra.geo.units import deg_to_compass, distance_nm, ft_to_fl, haversine_km
from tephra.models import (
    CREW_CUE_TEXT,
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
    ChainHead,
    CloudInfo,
    ConnectFlow,
    Connection,
    ConnectLive,
    CrewFlag,
    CrewPicture,
    CrewReport,
    CrewReportKind,
    CrewReportView,
    DutyItem,
    DutyItemKind,
    DutyRun,
    ExposedFlight,
    ExposureFeatureProps,
    FeedHealth,
    FeedId,
    FeedStatus,
    FlightRoute,
    FrameProduct,
    FrameThumb,
    GeoLineString,
    HazardCone,
    LlmInfo,
    MissingReason,
    OperatorPolicy,
    Overlays,
    PlanLine,
    PlannedAction,
    PlannerContext,
    PlumeAssessment,
    PlumeMode,
    PolicySummary,
    ProductKind,
    PushedDot,
    PushedFlightPlan,
    PushProblem,
    PushResult,
    PushSummary,
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
    StoreHealth,
    SupportingEvidence,
    SystemState,
    Taf,
    TickReport,
    TraceActor,
    TraceEvent,
    TraceStage,
    VaacAdvisory,
    VaacCentre,
    VaacStep,
    Volcano,
    VolcanoFeatureProps,
    Vona,
    WallSnapshot,
    WindProfile,
    blob_url,
    feature,
    feature_collection,
    point,
)
from tephra.policy import load_policy
from tephra.reconcile.discrepancies import (
    build_situation,
    evidence_state,
    find_active,
    select_floor_vaas,
    select_records,
)
from tephra.recovery import decisions as recovery_decisions
from tephra.recovery.agent import recommend_recovery
from tephra.recovery.models import Closure, Schedule
from tephra.recovery.network import network_closures, run_lock
from tephra.recovery.schedule import ScheduleError, load_schedule
from tephra.regdocs.evidence import NoActiveVolcano, UnknownRegion, gather_evidence
from tephra.regdocs.narrative import narrative_question
from tephra.regdocs.registry import withdraw_crew_messages
from tephra.regdocs.sra import narrative_facts
from tephra.replay.cases import (
    ReplaySource,
    answers_path,
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
from tephra.util.hashing import proxy_flight_number, sha256_json

__all__ = ["Runtime", "create_runtime"]

logger = logging.getLogger(__name__)

CHECKPOINT_S: Final = 300.0
PUSH_LOG_SIZE: Final = 400
CONNECT_LIVE_S: Final = 60
"""Pushes the Connect page's rates and ticker are worked out from (5 min of the sample feed)"""
WRITER_DOC: Final = "writer"
"""``runtime/writer``: the instance that ticked last; only the serving revision gets ticks"""
AUDIT_HEAD_DOC: Final = "audit_head"
"""``runtime/audit_head``: the audit chain's head as this instance last checkpointed it"""
OPEN_DRAFT_LIMIT: Final = 500
DRAFTS_COPY_S: Final = 60.0
"""The open drafts read from the store at least this often (wall seconds), whatever the
in-process writes said: a write by another instance during a rollout, or one whose advisory
event never went out, is seen within a tick."""
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
_VAA_FEEDS: Final = {VaacCentre.TOKYO: FeedId.VAAC_TOKYO, VaacCentre.DARWIN: FeedId.VAAC_DARWIN}
VONA_NOT_READ_NOTE: Final = (
    "Not read: live MAGMA polling is off (robots.txt disallows crawling); "
    "replays play recorded VONAs"
)
SITUATION_CLOCK_FIELDS: Final[IncEx] = {
    "as_of": True,
    "discrepancies": {"__all__": {"magnitude", "summary"}},
}
"""Situation fields that move with the clock alone (a SILENCE counts its minutes): storing the
situation again for them would cost 1,440 writes a day per silent volcano."""

RESTORED_NOTE: Final = "restored after restart"
DESK_UNREACHABLE_NOTE: Final = "Desk store unreachable: drafts not updated this tick"
DRAFT_RUN_ENDED: Final = "THE REPLAY RUN IT WAS DRAFTED IN HAS ENDED"
STORE_ERROR_CHARS: Final = 300
FEED_STATE_CLOCK_FIELDS: Final[IncEx] = {"age_s", "last_attempt_at", "last_success_at"}
"""Feed-state fields that move on every poll: storing them would rewrite every feed's state at
every checkpoint. Feed state is written when its status, error or count changes instead, so a
restored ``last_success_at`` can be older than the true one; that only makes it look staler."""

TraceLevel = Literal["info", "warn", "error"]


class RecoveryDue(NamedTuple):
    schedule: Schedule
    closures: list[Closure]
    airports: frozenset[str]


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
    ledger: QuotaLedger | None = None
    """The day's model-call counts; ``create_runtime`` shares one with the Gemini backend"""
    policy_summary: PolicySummary = field(init=False)
    live: LiveData = field(init=False, default_factory=LiveData)
    lock: asyncio.Lock = field(init=False, default_factory=asyncio.Lock, repr=False)
    tick_running: bool = field(init=False, default=False)
    tick_task: "asyncio.Task[TickReport] | None" = field(init=False, default=None, repr=False)
    """The running tick's steps, which a person's mode switch at the Desk stops (switch_mode)"""
    situations: dict[str, Situation] = field(init=False, default_factory=dict)
    assessments: dict[str, PlumeAssessment] = field(init=False, default_factory=dict)
    cones: dict[str, HazardCone] = field(init=False, default_factory=dict)
    exposed: dict[str, ExposedFlight] = field(init=False, default_factory=dict)
    reroutes: dict[str, list[RerouteOption]] = field(init=False, default_factory=dict)
    """flight id -> the lateral options computed when the flight was planned"""
    satellite: dict[str, SatelliteReading] = field(init=False, default_factory=dict)
    """volcano id -> the newest Satellite Reader reading"""
    last_tick: TickReport | None = field(init=False, default=None)
    last_tick_wall_at: datetime | None = field(init=False, default=None)
    """Wall-clock time the last tick of this process finished; not restored on a restart"""
    duty: DutyRun | None = field(init=False, default=None)
    """The newest Duty Officer run, for the Wall and the Desk"""
    worker: AiWorker = field(init=False)
    """Runs the model work off the tick (``tephra.ai_worker``)"""
    epoch: int = field(init=False, default=0)
    """Counts picture resets (mode switches, replay loops): AI work that started before one is
    not committed after it"""
    _planned: dict[str, tuple[str, int]] = field(init=False, default_factory=dict)
    _drafts_copy: "_DraftsCopy | None" = field(init=False, default=None)
    """flight id -> (cone id, the most urgent bucket it was planned in for that cone)"""
    _plan_failures: dict[str, _PlanFailure] = field(init=False, default_factory=dict)
    """flight id -> its last planning error, until it is planned or leaves the cone"""
    open_failures: dict[str, AiFailure] = field(init=False, default_factory=dict)
    """flight id -> its open AI failure on the Desk (one per flight), until it no longer stands"""
    _failures_followed: bool = field(init=False, default=False)
    pushed: dict[str, Aircraft] = field(init=False, default_factory=dict)
    """hex -> the newest position an airline connection pushed (``take_push``)"""
    sample_stop: asyncio.Event | None = field(init=False, default=None, repr=False)
    """Set to end the running sample feed; None while none runs"""
    sample_connection_id: str | None = field(init=False, default=None)
    flight_plans: dict[str, tuple[PushedFlightPlan, datetime]] = field(
        init=False, default_factory=dict
    )
    """hex, or 'cs:<callsign>' -> the airline's newest flight plan for it and when it came"""
    _report_keys: set[str] = field(init=False, default_factory=set, repr=False)
    """Pilot reports already entered from a push (a repeat is not entered twice)"""
    push_log: "deque[PushSummary]" = field(
        init=False, default_factory=lambda: deque(maxlen=PUSH_LOG_SIZE), repr=False
    )
    """The newest pushes taken (no dots), for the Connect page after a reload"""
    """This picture's open failures were read back from the store (``_follow_failures``)"""
    _unexposed_since: dict[str, datetime] = field(init=False, default_factory=dict)
    """flight id -> since when an open draft's flight is seen outside every cone"""
    _unseen_since: dict[str, datetime] = field(init=False, default_factory=dict)
    """flight id -> since when an open draft's flight is missing from the ADS-B picture"""
    _digests: dict[str, str] = field(init=False, default_factory=dict)
    _published: dict[str, str] = field(init=False, default_factory=dict)
    """Wall layer (or ``situation/<volcano id>``) -> digest of the payload last published"""
    instance_id: str = field(init=False, default_factory=lambda: uuid.uuid4().hex)
    retired: bool = field(init=False, default=False)
    """Another instance ticked after this one (a rollout): no ADS-B passes, no checkpoints"""
    adsb_passes: asyncio.Task[None] | None = field(init=False, default=None, repr=False)
    last_tick_clock: float | None = field(init=False, default=None)
    """``time.monotonic()`` when the last tick began"""
    _writer_at: datetime | None = field(init=False, default=None)
    _quiet_ticks: int = field(init=False, default=0)
    _closed_airports: frozenset[str] | None = field(init=False, default=None)
    """RFA-network airports with a closure now or in the horizon, at the last recovery run"""
    recovery_due: RecoveryDue | None = field(init=False, default=None)
    """A changed set of closed airports, waiting for the Duty Officer to dispatch recovery"""
    assess_due: dict[str, str] = field(init=False, default_factory=dict)
    """volcano id -> input hash of a plume read waiting for the Duty Officer"""
    duty_offered: dict[str, datetime] = field(init=False, default_factory=dict)
    """work item id -> when it was last offered to the Duty Officer"""
    sra_drafted: set[tuple[str, date]] = field(init=False, default_factory=set)
    """(region key, day) pairs whose SRA draft was dispatched (or failed) once"""
    positions_fresh: bool = field(init=False, default=True)
    _schedule: tuple[date, Schedule] | None = field(init=False, default=None)
    _live_source: Source | None = field(init=False, default=None)
    _replay_at: datetime | None = field(init=False, default=None)
    replay_window: tuple[datetime, datetime] | None = field(init=False, default=None)
    """The looping window the replay clock plays (TEPHRA_REPLAY_START to TEPHRA_REPLAY_END)"""
    _last_checkpoint: float | None = field(init=False, default=None)
    _tasks: set[asyncio.Task[None]] = field(init=False, default_factory=set, repr=False)
    store_health: StoreHealth = field(init=False, default_factory=StoreHealth)
    unsaved: set[tuple[Collection, str]] = field(init=False, default_factory=set)
    """Records held in memory whose store write failed; retried at the next checkpoint."""
    crew_reports: dict[str, CrewReport] = field(init=False, default_factory=dict)
    """Every crew report entered (both modes; the picture filters by mode and replay case)"""
    crew: CrewPicture = field(init=False, default_factory=CrewPicture)
    """Crew report caution areas and the flights they flag, as of the last update"""
    fixes: FixHistory = field(init=False)
    """Recent airline ADS-B positions, to place a crew report entered after its observation"""
    _crew_traced: set[str] = field(init=False, default_factory=set)
    """'<report id>' (outside the official area) and '<report id>/<hex>' (flag) lines traced"""
    _replay_run_wall: datetime = field(init=False)
    """Wall-clock start of the replay run playing: a process start, a switch to REPLAY or a
    loop. Crew reports entered in an earlier run end with it and are not shown again."""
    _answer_book: AiAnswers = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.ledger is None:
            self.ledger = QuotaLedger(self.settings, self.store)
        self.worker = AiWorker(self)
        self._answer_book = AiAnswers(self.store, self.settings, scope=self._answer_scope)
        self.policy_summary = PolicySummary.of(self.policy)
        self.fixes = FixHistory(timedelta(minutes=self.settings.crew_fix_history_min))
        self._replay_run_wall = timeutil.SystemClock().now()
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
    def answers(self) -> AiAnswers | None:
        """The models' answers kept for the mode playing (``tephra.agents.answers``); None with
        the offline stub, whose NO MODEL results are no model's answers."""
        return None if self.llm.name == "stub" else self._answer_book

    @property
    def plan_answer_age(self) -> timedelta:
        return timedelta(minutes=self.settings.ai_answer_plan_min)

    @property
    def duty_answer_age(self) -> timedelta:
        return timedelta(minutes=self.settings.ai_answer_duty_min)

    @property
    def quota(self) -> QuotaLedger:
        assert self.ledger is not None  # set in __post_init__
        return self.ledger

    @property
    def replay_run_since(self) -> datetime | None:
        """Wall-clock start of the replay run playing (None when live): records of an earlier
        run of the same recording belong to a picture that has ended."""
        return self._replay_run_wall if self.mode is RunMode.REPLAY else None

    @property
    def audit_head(self) -> ChainHead | None:
        """The audit chain's head as this process holds it (``tephra.desk.audit``): None
        before the startup walk or restore has seen the chain."""
        return audit.chain(self.store).head

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
        """``draft_count`` counts the open drafts of the mode playing (``open_drafts``), as the
        Desk lists them; None when the drafts cannot be read: an older count would be presented
        as current."""
        at = timeutil.now_exact()
        draft_count: int | None
        try:
            draft_count = len(await self.open_drafts())
        except DeskUnreachable:
            draft_count = None
        replay = None
        if self.mode is RunMode.REPLAY and self.replay_case is not None:
            replay = replay_info(self.replay_case, auto=self.auto_replay, window=self.replay_window)
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
            draft_count=draft_count,
            store=self.store_health,
            policy=self.policy_summary,
            last_tick=self.last_tick,
            last_tick_wall_at=self.last_tick_wall_at,
            build_sha=self.settings.build_sha,
            features=sorted(self.settings.features),
            cloud=self._cloud_info(),
            audit=self.audit_head,
            visitor_access=self.settings.visitor_access == "replay" and self.mode is RunMode.REPLAY,
        )

    def _cloud_info(self) -> CloudInfo:
        """Where this service runs: Cloud Run's own environment names the service and
        revision; the rest is settings, never inferred (``secrets_source`` is set by
        ``deploy/cloudrun.sh`` beside ``--set-secrets``)."""
        settings = self.settings
        service = os.environ.get("K_SERVICE") or None
        return CloudInfo(
            platform="cloud-run" if service else "local",
            service=service,
            revision=os.environ.get("K_REVISION") or None,
            region=settings.cloud_region,
            store=settings.store,
            scheduler="in-process" if settings.local_scheduler else "cloud-scheduler",
            secrets=settings.secrets_source,
            model_access="gemini-api" if settings.llm == "gemini" else "none",
        )

    async def wall_snapshot(self) -> WallSnapshot:
        at = timeutil.now()
        situations = [self.situations[vid] for vid in sorted(self.situations)]
        colors = _color_codes(self.catalogue, self.live.vonas.values(), self.live.vaas.values())
        cones = [self.cones[vid] for vid in sorted(self.cones)]
        routes = self.known_routes()
        return WallSnapshot(
            generated_at=at,
            volcanoes=_volcano_features(self.catalogue, colors, set(self.live.active)),
            official=feature_collection(
                layer.to_feature() for item in situations for layer in item.official_layers
            ),
            cones=feature_collection(part for cone in cones for part in cone.to_features()),
            exposures=_exposure_features(self.exposed.values()),
            aircraft=_aircraft_features(
                self.aircraft(), self.exposed.values(), self.crew, routes, self.plan_numbers()
            ),
            reroutes=_reroute_features(self.reroutes, self.exposed),
            routes=self.route_layer(routes),
            duty=self.duty,
            crew=self.crew,
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
        self,
        mode: RunMode,
        *,
        auto: bool = False,
        case: ReplayCase | None = None,
        preempt: bool = False,
    ) -> None:
        """``case`` is taken under the lock, with the switch: while a tick runs, or after a
        switch that failed, the REPLAY banner never names a case that is not playing.

        ``preempt`` (a person's switch at the Desk) stops a tick in progress instead of waiting
        for it: a LIVE tick waits on public feeds for minutes, and the switch resets the picture
        and the epoch, so nothing the stopped tick began is kept."""
        if preempt and self.tick_task is not None and not self.tick_task.done():
            self.tick_task.cancel()
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
        LIVE ticks; leave it as soon as a live VA SIGMET for a catalogue volcano inside the
        region is valid. A REPLAY a person chose is never left here."""
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
            report.notes.append("live VA SIGMET for a volcano in the region: switched back to LIVE")
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
                f"{self.volcano_name(vid)} is active: {reasons}",
                volcano_id=vid,
            )
        for vid in sorted(self.live.active.keys() - active.keys()):
            self.trace(
                TraceStage.SYSTEM,
                "code",
                f"{self.volcano_name(vid)} is no longer active",
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

    async def update_exposures(self, at: datetime, report: TickReport) -> None:
        """Which flights enter which cone. Planning them is the Duty Officer's work list."""
        self.fixes.add(self.aircraft(), at)
        if self._positions_stale():
            # Nothing to draft from, and a flight missing from an old copy is no reason to
            # retire a dispatcher's pending draft: the picture waits for live positions.
            self.positions_fresh = False
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
        self.positions_fresh = True
        self._replace_exposures(self._expose(self.cones.values(), at))
        report.exposed_flights = len(self.exposed)

    async def settle_drafts(self, at: datetime, report: TickReport) -> None:
        """Retire drafts, and close AI failures, whose flight has left every cone or the ADS-B
        picture (MODULES.md 5.7), once the Duty Officer has planned what was due."""
        await self._follow_failures()
        if not self.positions_fresh:
            return
        exposed = self.exposed
        try:
            open_drafts = await self.open_drafts()
        except DeskUnreachable:
            self.desk_unreachable(report)
            return
        seen = {target.hex for target in self.aircraft()}
        report.drafts_superseded += await self._retire_gone(open_drafts, seen, at, report)
        self._planned = {fid: mark for fid, mark in self._planned.items() if fid in exposed}
        self._plan_failures = {
            fid: failure for fid, failure in self._plan_failures.items() if fid in exposed
        }

    async def run_exposures(self, at: datetime, report: TickReport) -> None:
        """Exposure and draft retirement, then a wake for the AI worker: the ADS-B pass
        between ticks runs this; a tick runs the steps around network recovery."""
        await self.update_exposures(at, report)
        try:
            await self.update_crew(at, report)
        except Exception:  # a flag layer: its failure must not hold up the AI work
            logger.exception("crew report update failed in an ADS-B pass")
            self.trace(TraceStage.SYSTEM, "system", "crew reports failed this pass", level="error")
        await self.settle_drafts(at, report)
        self.worker.wake("adsb")

    def start_worker(self) -> None:
        """Start the AI worker's loop (``create_runtime`` does; ``aclose`` stops it)."""
        self.spawn(self.worker.run())

    def desk_unreachable(self, report: TickReport) -> None:
        """Note and trace, once a tick, that drafts were neither planned nor retired."""
        if DESK_UNREACHABLE_NOTE in report.notes:
            return
        report.notes.append(DESK_UNREACHABLE_NOTE)
        self.trace(TraceStage.DESK, "system", DESK_UNREACHABLE_NOTE, level="error")

    def _expose(self, cones: Iterable[HazardCone], at: datetime) -> dict[str, ExposedFlight]:
        aircraft = self.aircraft()
        exposed: dict[str, ExposedFlight] = {}
        for cone in cones:
            for flight in find_exposed(
                cone,
                aircraft,
                at,
                lookahead_min=self.settings.exposure_lookahead_min,
                vertical_margin_ft=self.policy.exposure.vertical_margin_ft.value,
                hold_minutes=self.policy.fuel.hold_min.value,
            ):
                exposed[flight.id] = flight
        return exposed

    def _replace_exposures(
        self, exposed: dict[str, ExposedFlight], *, volcano_id: str | None = None
    ) -> None:
        """Take ``exposed`` as the exposure of every cone, or of one volcano's cone."""
        kept = (
            {}
            if volcano_id is None
            else {fid: f for fid, f in self.exposed.items() if f.volcano_id != volcano_id}
        )
        for flight in sorted(exposed.values(), key=_entry_order):
            if flight.id not in self.exposed:
                self.trace(
                    TraceStage.EXPOSURE,
                    "code",
                    _exposure_message(flight, self.volcano_name(flight.volcano_id)),
                    level="warn",
                    volcano_id=flight.volcano_id,
                    flight_id=flight.id,
                    detail={"minutes_to_entry": flight.minutes_to_entry, "cone_id": flight.cone_id},
                )
        self.exposed = {**kept, **exposed}
        self._keep_current_reroutes()

    async def run_recovery(self, at: datetime, report: TickReport) -> None:
        """Queue network recovery for the Duty Officer when the set of airports the hazard
        closes differs from the set the last recovery run was for.

        No airport closed queues nothing. A Desk run in progress covers the change. Recovery
        stays queued (and is offered again) until the Duty Officer dispatches it."""
        self.recovery_due = None
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
        if not closed:
            self._closed_airports = closed
            self.trace(TraceStage.RECOVERY, "code", "No RFA airport is closed by the hazard now")
            return
        if run_lock(self).locked() or self.worker.recovery_queued():
            return
        self.recovery_due = RecoveryDue(schedule, list(closures), closed)

    def start_recovery(self, report: TickReport) -> dict[str, Any]:
        """The Duty Officer's ``run_recovery``: the run is queued as an AI worker job of its
        own, since three CP-SAT solves and a model run must not hold the Duty Officer."""
        due = self.recovery_due
        if due is None:
            return {"error": "NO NETWORK RECOVERY IS DUE"}
        self.recovery_due = None
        self._closed_airports = due.airports
        airports = ", ".join(sorted(due.airports))
        self.trace(
            TraceStage.RECOVERY,
            "code",
            f"Closed airports changed: {airports}; recovery agent queued",
            level="warn",
            detail={"airports": sorted(due.airports)},
        )
        report.recovery_plans += 1
        self.worker.enqueue_recovery(due.airports)
        return {
            "summary": f"Recovery agent queued for {airports}",
            "airports": sorted(due.airports),
        }

    async def recover_queued(self, airports: Sequence[str]) -> None:
        """The AI worker's recovery job: closures as they stand now (a job queued before a
        restart runs on today's picture), then the agent."""
        at = timeutil.now()
        async with self.lock:
            schedule = await self._rfa_schedule(at)
            if schedule is None:
                return
            closures = network_closures(
                self, schedule, at=at, tafs=self.live.tafs, metars=self.live.metars
            )
            # The set this run covers is the one it plans for now, not the one it was queued
            # for: a change while it waited must not queue a second run over the same airports.
            self._closed_airports = frozenset(closure.icao for closure in closures)
        if not closures:
            self.trace(
                TraceStage.RECOVERY,
                "code",
                f"{', '.join(airports)} no longer closed by the hazard: no recovery run",
            )
            return
        await self._recover(schedule, closures)

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
                    trace=self.sink,
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

    # --- crew (pilot) reports: a flag layer beside the cones, never inside them ----------

    async def restore_crew_reports(self) -> None:
        """Every stored crew report, both modes: the picture shows those of the mode and
        replay case playing. A report that no longer validates is skipped and logged."""
        docs = await self.store.query(
            Collection.CREW_REPORTS,
            [],
            order_by="created_at",
            descending=True,
            limit=crew_reports.LOAD_LIMIT,
        )
        for doc in docs:
            try:
                report = CrewReport.model_validate(doc)
            except ValidationError:
                logger.warning("ignoring an unreadable stored crew report")
                continue
            self.crew_reports[report.id] = report
        self.crew = self.crew_picture(timeutil.now())

    def crew_picture(self, at: datetime) -> CrewPicture:
        layers = [layer for item in self.situations.values() for layer in item.official_layers]
        return crew_reports.build_picture(
            self.crew_reports.values(),
            at=at,
            replay=self.mode is RunMode.REPLAY,
            replay_case_id=self._replay_case_id(),
            aircraft=self.aircraft(),
            replay_run_since=self._replay_run_wall if self.mode is RunMode.REPLAY else None,
            layers=layers,
            lookahead_min=self.settings.exposure_lookahead_min,
        )

    async def update_crew(self, at: datetime, report: TickReport) -> None:
        """Record the expiry of lapsed areas once, rebuild the picture, and trace each new
        flag and each area outside the official ones once. A flag only: nothing is planned,
        drafted or asked of a model here."""
        replay_case_id = self._replay_case_id()
        replay = self.mode is RunMode.REPLAY
        for item in list(self.crew_reports.values()):
            area = item.area
            if (
                area is None
                or item.withdrawn_at is not None
                or item.expiry_recorded_at is not None
                or item.replay != replay
                or item.replay_case_id != replay_case_id
            ):
                continue
            earlier_run = replay and item.entered_wall_at < self._replay_run_wall
            if not earlier_run and at <= area.valid_to:
                continue
            note = (
                "the replay run it was entered in has ended; a replay played again never"
                " brings it back"
                if earlier_run
                else None
            )
            try:
                self.crew_reports[item.id] = await crew_reports.expire(
                    self.store, item, at, note=note
                )
            except Exception as exc:  # retried next update: the area is expired either way
                logger.warning("recording the expiry of crew report %s failed: %s", item.id, exc)
                self.store_failed(exc)
                continue
            self.trace(
                TraceStage.SYSTEM,
                "code",
                f"Crew report area of {item.flight} ({timeutil.hhmmz(item.observed_at)}) ended"
                f" with the replay run it was entered in"
                if earlier_run
                else f"Crew report area of {item.flight} ({timeutil.hhmmz(item.observed_at)})"
                f" expired at {timeutil.hhmmz(area.valid_to)}",
                volcano_id=item.volcano_id,
                detail={"report_id": item.id},
            )
        self.crew = self.crew_picture(at)
        self._trace_crew()
        if self.crew.flags:
            report.notes.append(f"{len(self.crew.flags)} flight(s) flagged by crew reports")

    def _trace_crew(self) -> None:
        for view in self.crew.reports:
            item = view.report
            if view.discrepancy is not None and item.id not in self._crew_traced:
                self._crew_traced.add(item.id)
                self.trace(
                    TraceStage.DISCREPANCY,
                    "code",
                    f"{view.discrepancy}: {item.flight} at {timeutil.hhmmz(item.observed_at)},"
                    f" {view.place_text}",
                    level="warn",
                    volcano_id=item.volcano_id,
                    detail={"report_id": item.id},
                )
        for flag in self.crew.flags:
            for report_id in flag.report_ids:
                key = f"{report_id}/{flag.hex}"
                if key in self._crew_traced:
                    continue
                self._crew_traced.add(key)
                when = (
                    "inside the area now"
                    if flag.inside_now
                    else f"enters it in {flag.minutes_to_entry} min if track and level are held"
                )
                self.trace(
                    TraceStage.EXPOSURE,
                    "code",
                    f"{flag.proxy_flight} ({flag.callsign or flag.hex.upper()}): {flag.line};"
                    f" {when}",
                    level="warn",
                    detail={"report_id": report_id, "hex": flag.hex},
                )

    def crew_flag(self, hex_id: str) -> CrewFlag | None:
        return next((flag for flag in self.crew.flags if flag.hex == hex_id), None)

    def crew_fix(self, entry_hex: str | None, callsign: str | None, at: datetime) -> FixLookup:
        """The fix a crew report entered now would be placed at, or why there is none. A time
        the report would be refused for is refused here too, before any position is asked."""
        problem = crew_reports.observed_problem(at, timeutil.now(), self.policy.crew_reports)
        if problem is not None:
            raise crew_reports.CrewReportRefused([problem])
        hex_id, flight_callsign = crew_reports.resolve_flight(
            entry_hex, callsign, self.aircraft(), self.fixes
        )
        within = timedelta(seconds=self.settings.stale_after_s(FeedId.ADSB))
        fix = crew_reports.find_fix(hex_id, at, self.aircraft(), self.fixes, within=within)
        name = (proxy_flight_number(hex_id) if hex_id else flight_callsign) or "the flight"
        if fix is None:
            return FixLookup(
                found=False,
                hex=hex_id,
                proxy_flight=proxy_flight_number(hex_id) if hex_id else None,
                callsign=flight_callsign,
                note=f"No ADS-B fix of {name} within {round(within.total_seconds())} s of"
                f" {timeutil.hhmmz(at)}: type the position the crew reported",
            )
        return FixLookup(
            found=True,
            hex=fix.hex,
            proxy_flight=proxy_flight_number(fix.hex),
            callsign=fix.callsign,
            lat=fix.lat,
            lon=fix.lon,
            alt_baro_ft=fix.alt_baro_ft,
            observed_at=fix.observed_at,
            source_id=fix.source_id,
            note=f"ADS-B fix of {name} at {timeutil.hhmmz(fix.observed_at)}",
        )

    async def enter_crew_report(self, entry: CrewEntry, *, actor: str) -> CrewReportView:
        """Store a crew report a dispatcher entered and show it at once. Raises
        :class:`crew_reports.CrewReportRefused` with every problem; nothing is stored then."""
        at = timeutil.now()
        flight = crew_reports.resolve_flight(entry.hex, entry.callsign, self.aircraft(), self.fixes)
        within = timedelta(seconds=self.settings.stale_after_s(FeedId.ADSB))
        fix = crew_reports.find_fix(
            flight[0], entry.observed_at, self.aircraft(), self.fixes, within=within
        )
        checked = crew_reports.check_entry(
            entry,
            at=at,
            flight=flight,
            fix=fix,
            fix_within=within,
            policy=self.policy.crew_reports,
        )
        radius_km = self.settings.active_radius_km
        volcano = self.catalogue.nearest(checked.lat, checked.lon, radius_km)
        winds, wind_place, no_wind = await self._crew_winds(checked, volcano)
        item = crew_reports.build_report(
            entry,
            checked,
            actor=actor,
            at=at,
            replay_case_id=self._replay_case_id(),
            flight=flight,
            fix=fix,
            volcano=volcano,
            winds=winds,
            wind_place=wind_place,
            no_wind_reason=no_wind,
            policy=self.policy.crew_reports,
            summary=self.policy_summary,
        )
        await crew_reports.record_entry(self.store, item)
        self.crew_reports[item.id] = item
        self.trace(
            TraceStage.DESK,
            "human",
            f"Crew report entered: {item.flight} at {timeutil.hhmmz(item.observed_at)},"
            f" {', '.join(CREW_CUE_TEXT[cue] for cue in item.cues)}",
            volcano_id=item.volcano_id,
            detail={"report_id": item.id, "kind": item.kind.value},
        )
        return await self._show_crew(item.id, at)

    async def _crew_winds(
        self, checked: CheckedEntry, volcano: Volcano | None
    ) -> tuple[list[WindProfile], str, str]:
        """``(profiles, where they are from, why there are none)`` for a report's stretch. LIVE
        asks Open-Meteo for the profile at the report position (a public GET, no model);
        REPLAY never reaches a live feed, so only a profile recorded above a volcano near the
        report can be used, and the note says which and how far."""
        if checked.kind is not CrewReportKind.ASH:
            return [], "", ""
        if self.mode is RunMode.LIVE:
            hours = math.ceil(self.policy.crew_reports.valid_min.value / 60) + 1
            try:
                profiles = await fetch_winds(
                    self.source, checked.lat, checked.lon, past_hours=hours
                )
            except (FetchError, ValueError) as exc:
                reason = exc.reason if isinstance(exc, FetchError) else str(exc)
                return [], "", f"the wind fetch at the report position failed: {reason}"
            return profiles, "at the report position", ""
        if volcano is None:
            return [], "", "this replay recorded winds only above active volcanoes"
        profiles = list(self.live.winds.get(volcano.id, ()))
        distance = round(haversine_km(checked.lat, checked.lon, volcano.lat, volcano.lon))
        if not profiles:
            return [], "", f"this replay recorded no winds above {volcano.name}"
        return profiles, f"recorded above {volcano.name}, {distance} km from the report", ""

    async def withdraw_crew_report(
        self, report_id: str, *, reason: str, actor: str
    ) -> CrewReportView:
        item = self.crew_reports.get(report_id)
        if item is None:
            raise crew_reports.CrewReportNotFound(report_id)
        withdrawn = await crew_reports.withdraw(self.store, item, reason=reason, actor=actor)
        self.crew_reports[report_id] = withdrawn
        await withdraw_crew_messages(
            self.store, self.bus, report_id, reason=withdrawn.withdraw_reason or reason, actor=actor
        )
        self.trace(
            TraceStage.DESK,
            "human",
            f"Crew report of {item.flight} ({timeutil.hhmmz(item.observed_at)}) withdrawn",
            volcano_id=item.volcano_id,
            detail={"report_id": report_id},
        )
        return await self._show_crew(report_id, timeutil.now())

    def crew_view(self, report_id: str) -> CrewReportView | None:
        return next((v for v in self.crew.reports if v.report.id == report_id), None)

    async def _show_crew(self, report_id: str, at: datetime) -> CrewReportView:
        """Rebuild and publish the crew picture now, not at the next tick, and return the
        report's view (one the picture does not list, from another mode or older than its
        window, gets a view of its own with no flags)."""
        self.crew = self.crew_picture(at)
        self._trace_crew()
        self._publish_changed(SseEvent.CREW, self.crew)
        self.bus.publish(
            SseEvent.AIRCRAFT,
            _aircraft_features(
                self.aircraft(),
                self.exposed.values(),
                self.crew,
                self.known_routes(),
                self.plan_numbers(),
            ),
        )
        view = self.crew_view(report_id)
        if view is not None:
            return view
        layers = [layer for item in self.situations.values() for layer in item.official_layers]
        return crew_reports.report_view(self.crew_reports[report_id], layers, at)

    def _replay_case_id(self) -> str | None:
        if self.mode is RunMode.REPLAY and self.replay_case is not None:
            return self.replay_case.case_id
        return None

    def _keep_current_reroutes(self) -> None:
        """Reroutes only for flights still exposed to the cone they were computed for."""
        self.reroutes = {
            fid: options
            for fid, options in self.reroutes.items()
            if fid in self.exposed and options and options[0].cone_id == self.exposed[fid].cone_id
        }

    def count_quiet_tick(self) -> None:
        if self.mode is RunMode.LIVE and self.settings.auto_replay:
            quiet = not any(self._in_region(vid) for vid in self.live.active) and not self.exposed
            self._quiet_ticks = self._quiet_ticks + 1 if quiet else 0

    async def publish(self) -> None:
        snapshot = await self.wall_snapshot()
        state = await self.system_state()
        bus = self.bus
        bus.publish(SseEvent.STATE, state)
        self._publish_changed(SseEvent.VOLCANOES, snapshot.volcanoes)
        self._publish_changed(SseEvent.OFFICIAL, snapshot.official)
        self._publish_changed(SseEvent.CONES, snapshot.cones)
        bus.publish(SseEvent.EXPOSURES, snapshot.exposures)
        self._publish_changed(SseEvent.REROUTES, snapshot.reroutes)
        self._publish_changed(SseEvent.ROUTES, snapshot.routes)
        bus.publish(SseEvent.AIRCRAFT, snapshot.aircraft)
        self._publish_changed(SseEvent.OVERLAYS, snapshot.overlays)
        self._publish_changed(SseEvent.CREW, snapshot.crew)
        prefix = f"{SseEvent.SITUATION.value}/"
        shown = {f"{prefix}{card.volcano_id}" for card in snapshot.situations}
        for card in snapshot.situations:
            self._publish_changed(SseEvent.SITUATION, card, key=f"{prefix}{card.volcano_id}")
        # The Wall drops a card whose volcano left the active list; one that comes back is new.
        for key in [key for key in self._published if key.startswith(prefix) and key not in shown]:
            del self._published[key]
        await self.publish_budget()

    def _publish_changed(
        self, name: SseEvent, data: BaseModel | dict[str, Any], *, key: str | None = None
    ) -> None:
        """Publish a Wall layer only when it changed: a new or reconnecting page reads the
        whole picture from ``/api/wall`` (or the bus history), so a repeat carries nothing."""
        key = key or name.value
        digest = sha256_json(data)
        if self._published.get(key) == digest:
            return
        self.bus.publish(name, data)
        self._published[key] = digest

    async def publish_budget(self) -> None:
        """The day's model-call counts and the AI work waiting (the Wall's AI tray, the Desk's
        budget chip)."""
        self.bus.publish(SseEvent.BUDGET, await self.budget_view())

    async def budget_view(self) -> BudgetView:
        return await budget_view(self.settings, self.llm, self.quota, self.worker.queue())

    # --- the models' kept answers (tephra.agents.answers) --------------------------------

    def _answer_scope(self) -> AnswerScope:
        return AnswerScope(self.mode, self._replay_case_id(), self.epoch)

    async def answered(self, item: DutyItem) -> bool:
        """Whether every model answer a work item needs is on hand for the question it would
        ask now, so it costs no model call (the AI worker's look ahead; when the item runs, the
        answers are checked again, and one that no longer passes sends the item back to wait,
        :class:`~tephra.agents.answers.NotOnHand`). A recovery run always asks."""
        answers = self.answers
        if answers is None:
            return False
        if item.kind is DutyItemKind.ASSESS:
            return await self._plume_answered(item.subject, answers)
        if item.kind is DutyItemKind.PLAN:
            return await self._plan_answered(item.subject, answers)
        if item.kind is DutyItemKind.SRA:
            return await self._sra_answered(item.subject, answers)
        return False

    async def coordinator_answered(self, items: Sequence[DutyItem]) -> bool:
        answers = self.answers
        if answers is None:
            return False
        question = self.coordinator_question(items)
        return await answers.peek(question, self.llm.model_id("lite")) is not None

    def coordinator_question(self, items: Sequence[DutyItem]) -> Question:
        return coordinator_question(
            items, policy_version=self.policy.version, max_age=self.duty_answer_age
        )

    async def _plume_answered(self, volcano_id: str, answers: AiAnswers) -> bool:
        situation = self.situations.get(volcano_id)
        seen = await self._satellite_on_hand(situation) if situation is not None else None
        if seen is None:
            return False
        question = plume_question(seen, max_age=REASK_UNCHANGED)
        return await answers.peek(question, self.llm.model_id("main")) is not None

    async def _plan_answered(self, flight_id: str, answers: AiAnswers) -> bool:
        flight = self.exposed.get(flight_id)
        cone = self.cones.get(flight.volcano_id) if flight is not None else None
        if flight is None or cone is None:
            return False
        ctx = self._planner_context(flight, cone, timeutil.now())
        if ctx is None:
            return False
        model = self.llm.model_id("lite")
        plan = await answers.peek(self._planner_question(ctx, cone), model)
        if plan is None:
            return False
        try:
            held = PlannedAction.model_validate(plan.payload)
        except ValidationError:
            return False
        if held.decision is None:
            return False
        draft = await answers.peek(self._drafter_question(ctx, cone, held), model)
        return draft is not None

    async def _sra_answered(self, region: str, answers: AiAnswers) -> bool:
        try:
            evidence = await gather_evidence(self, region)
        except (UnknownRegion, NoActiveVolcano):
            return False
        question = narrative_question(narrative_facts(evidence, self.policy))
        return await answers.peek(question, self.llm.model_id("lite")) is not None

    def _planner_question(self, ctx: PlannerContext, cone: HazardCone) -> Question:
        return planner_question(
            ctx,
            cone_version=cone_version(cone),
            policy_version=self.policy.version,
            max_age=self.plan_answer_age,
        )

    def _drafter_question(
        self, ctx: PlannerContext, cone: HazardCone, plan: PlannedAction
    ) -> Question:
        return drafter_question(
            ctx,
            plan,
            cone_version=cone_version(cone),
            policy_version=self.policy.version,
            max_age=self.plan_answer_age,
        )

    async def publish_live(self) -> None:
        """The between-ticks update after an extra ADS-B poll: aircraft, exposures, state."""
        routes = self.known_routes()
        self.bus.publish(
            SseEvent.AIRCRAFT,
            _aircraft_features(
                self.aircraft(), self.exposed.values(), self.crew, routes, self.plan_numbers()
            ),
        )
        self.bus.publish(SseEvent.EXPOSURES, _exposure_features(self.exposed.values()))
        self._publish_changed(SseEvent.ROUTES, self.route_layer(routes))
        self._publish_changed(SseEvent.CREW, self.crew)
        self.bus.publish(SseEvent.STATE, await self.system_state())

    async def checkpoint(self, *, force: bool = False) -> None:
        """Persist the live picture, at most every :data:`CHECKPOINT_S` unless forced. A
        retired instance writes nothing: the serving one owns ``runtime/state`` (so ``aclose``
        on a retired instance leaves it as the serving instance wrote it)."""
        if self.retired:
            return
        clock = time.monotonic()
        last = self._last_checkpoint
        if not force and last is not None and clock - last < CHECKPOINT_S:
            return
        self._last_checkpoint = clock
        try:
            await self._persist_live()
        except Exception:  # a checkpoint is a cache; losing one must not fail the tick
            logger.exception("checkpoint failed; the live picture stays in memory")
        await self._checkpoint_audit_head()
        try:
            await self._answer_book.sweep()
        except Exception as exc:  # the next sweep tries again
            logger.warning("removing expired AI answers failed: %s", exc)

    # --- helpers the registry and scheduler use ------------------------------------------

    def active_volcanoes(self) -> list[Volcano]:
        found = (self.catalogue.get(vid) for vid in sorted(self.live.active))
        return [volcano for volcano in found if volcano is not None]

    def aircraft(self) -> list[Aircraft]:
        """ADS-B targets and the positions airline connections pushed, newest per address.
        A pushed position counts while it is :data:`connections.PUSH_FRESH_S` old or less."""
        merged = {target.hex: target for target in merge_aircraft(self.live.adsb)}
        at = timeutil.now()
        for target in self.pushed.values():
            if timeutil.age_s(target.observed_at, at) > connections.PUSH_FRESH_S:
                continue
            held = merged.get(target.hex)
            if held is None or target.observed_at >= held.observed_at:
                merged[target.hex] = target
        return [merged[key] for key in sorted(merged)]

    # --- airline data connections (tephra.desk.connections) -------------------------------

    async def take_push(
        self,
        connection: Connection,
        positions: Sequence[dict[str, Any]] = (),
        *,
        plans: Sequence[dict[str, Any]] = (),
        reports: Sequence[dict[str, Any]] = (),
        retime: bool = False,
    ) -> PushResult:
        """Take one push (``tephra.airline/1``). Positions that pass join the aircraft and are
        checked against the ash as an ADS-B pass does (when no tick holds the lock; else the
        tick does). Flight plans that pass give their flights the airline's route and the
        closed-airport check. Each pilot report is entered as a crew report, as the Desk enters
        one (same checks, same caution area and flags). Refused records change nothing; the
        ``push`` event says what came. ``retime`` (an upload a dispatcher marks as current)
        stamps every position and report with TEPHRA's clock now before the checks."""
        at = timeutil.now()
        if retime:
            stamp = timeutil.to_iso(at)
            positions = [
                {**r, "observed_at": stamp} if isinstance(r, dict) else r for r in positions
            ]
            reports = [{**r, "observed_at": stamp} if isinstance(r, dict) else r for r in reports]
        accepted, problems = connections.checked_positions(positions, connection, at)
        for target in accepted:
            self.pushed[target.hex] = target
        plans_ok, plan_problems = connections.checked_plans(plans)
        problems += plan_problems
        self.take_plans(plans_ok, at)
        if (accepted or plans_ok) and self.live.active and not self.lock.locked():
            async with self.lock:
                report = TickReport(started_at=at, finished_at=at, mode=self.mode, reason="push")
                await self.run_exposures(at, report)
                await self.publish_live()
        reports_taken = 0
        for index, raw in enumerate(reports):
            reason = await self._take_pilot_report(connection, raw)
            if reason is None:
                reports_taken += 1
            else:
                problems.append(PushProblem(section="pilot_reports", index=index, reason=reason))
        exposed = {flight.hex for flight in self.exposed.values()}
        in_ash = sorted({t.hex for t in accepted if t.hex in exposed})
        closed = self.closed_now()
        closed_hits = sorted(
            {p.flight for p in plans_ok if p.origin_icao in closed or p.dest_icao in closed}
        )
        saved = await connections.save_counts(
            self.store, connection, accepted=len(accepted), rejected=len(problems), at=at
        )
        summary = PushSummary(
            connection_id=saved.id,
            name=saved.name,
            sample=saved.sample,
            at=at,
            wall_at=timeutil.SystemClock().now(),
            accepted=len(accepted),
            rejected=len(problems),
            in_ash=len(in_ash),
            plans=len(plans_ok),
            reports=reports_taken,
            closed_hits=len(closed_hits),
            reasons=list(dict.fromkeys(problem.reason for problem in problems))[:3],
        )
        self.push_log.appendleft(summary)
        dots = [_pushed_dot(t, exposed) for t in accepted[:200]]
        self.bus.publish(SseEvent.PUSH, summary.model_copy(update={"dots": dots}))
        return PushResult(
            connection_id=saved.id,
            received_at=at,
            accepted=len(accepted),
            rejected=problems,
            in_ash=in_ash,
            plans_taken=len(plans_ok),
            reports_taken=reports_taken,
            closed_hits=closed_hits,
        )

    async def _take_pilot_report(self, connection: Connection, raw: Any) -> str | None:
        """Enter one pushed pilot report as a crew report; the reason when it is refused. The
        same report (flight and time) pushed again is not entered twice."""
        try:
            entry = CrewEntry.model_validate(raw)
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(part) for part in first.get("loc", ())) or "report"
            return f"{where}: {first.get('msg', 'invalid')}"
        key = f"{connection.id}|{entry.hex or entry.callsign}|{timeutil.to_iso(entry.observed_at)}"
        if key in self._report_keys:
            return None
        try:
            await self.enter_crew_report(entry, actor=f"connect:{connection.name}")
        except crew_reports.CrewReportRefused as exc:
            return "; ".join(exc.problems)
        self._report_keys.add(key)
        return None

    def connect_live(self) -> ConnectLive:
        """The Connect page's whole picture now: every pushed flight updated in the last
        :data:`CONNECT_LIVE_S` (the analysis keeps them for ``PUSH_FRESH_S``), each connection's
        flow over the last 5 minutes (wall clock) and the newest pushes."""
        wall = timeutil.SystemClock().now()
        at = timeutil.now()
        exposed = {flight.hex for flight in self.exposed.values()}
        dots = [
            _pushed_dot(target, exposed)
            for target in self.pushed.values()
            if timeutil.age_s(target.observed_at, at) <= CONNECT_LIVE_S
        ]
        flows: dict[str, ConnectFlow] = {}
        for push in self.push_log:
            age = (wall - push.wall_at).total_seconds()
            flow = flows.get(push.connection_id)
            if flow is None:
                flow = flows[push.connection_id] = ConnectFlow(
                    connection_id=push.connection_id,
                    name=push.name,
                    sample=push.sample,
                    per_min=0,
                    spark=[0] * 20,
                    last_push_wall_at=push.wall_at,
                )
            if age < 60:
                flow.per_min += push.accepted
            bucket = 19 - int(age // 15)
            if 0 <= bucket < 20:
                flow.spark[bucket] += push.accepted
        return ConnectLive(
            wall_at=wall,
            sample_running=self.sample_stop is not None,
            sample_connection_id=self.sample_connection_id,
            flows=list(flows.values()),
            dots=dots,
            plans=self.plan_lines(),
            reports=self.crew.features,
            recent=list(self.push_log)[:14],
        )

    def sample_areas(self) -> list[Any]:
        """The ash areas now, as shapes, for the sample feed's choice of flights."""
        volcanoes = {v.id: v for v in self.active_volcanoes()}
        return [
            geometry_to_shape(cone.geometry, ref_lon=volcanoes[cone.volcano_id].lon)
            for cone in self.cones.values()
            if cone.geometry is not None and cone.volcano_id in volcanoes
        ]

    async def start_sample_feed(self, *, actor: str) -> Connection:
        """Start pushing real recorded flights through the sample connection (made once)."""
        existing = [c for c in await connections.list_connections(self.store) if c.sample]
        live = next((c for c in existing if c.revoked_at is None), None)
        if live is None:
            live, _ = await connections.create_connection(
                self.store, "Sample airline feed", actor=actor, sample=True
            )
        if self.sample_stop is not None:
            return live
        pool = await asyncio.to_thread(
            sample_feed.load_pool, self.settings.data_dir, self.settings.region_preset.bbox
        )
        skip = {target.hex for target in merge_aircraft(self.live.adsb)}
        flights = sample_feed.pick_flights(
            pool, self.sample_areas(), skip=skip, prefer=self._has_route
        )
        stop = asyncio.Event()
        self.sample_stop, self.sample_connection_id = stop, live.id
        connection = live
        plans = self.sample_plans(flights)
        pushes = 0

        async def push(positions: list[dict[str, Any]]) -> None:
            # positions every push; the flight plans with the first and every minute after; a
            # pilot report from a sample flight in the ash 15 s in, then every 4 minutes
            nonlocal pushes
            pushes += 1
            exposed = {flight.hex for flight in self.exposed.values()}
            in_ash = [p for p in positions if p["hex"] in exposed]
            report_due = pushes == 4 or (pushes > 4 and pushes % 48 == 4)
            now = timeutil.now()
            reports = [sample_feed.pilot_report(p, now) for p in in_ash[: 2 if pushes == 4 else 1]]
            await self.take_push(
                connection,
                positions,
                plans=plans if pushes % 12 == 1 else (),
                reports=reports if report_due else (),
            )

        async def run() -> None:
            try:
                await sample_feed.run_sample_feed(flights, push, stop)
            finally:
                if self.sample_stop is stop:
                    self.sample_stop, self.sample_connection_id = None, None

        self.spawn(run())
        return live

    def _has_route(self, flight: sample_feed.SampleFlight) -> bool:
        return self.routes.lookup(flight, self.airports, self.policy) is not None

    def sample_plans(self, flights: Sequence[sample_feed.SampleFlight]) -> list[dict[str, Any]]:
        return sample_feed.plans_for(
            flights,
            lambda flight: self.routes.lookup(flight, self.airports, self.policy),
            lambda icao: self.routes.position(icao, self.airports),
            timeutil.now(),
        )

    def sample_bundle(self, limit: int = 12) -> dict[str, Any]:
        """The downloadable sample: every section, real flights, on TEPHRA's clock now."""
        pool = sample_feed.load_pool(self.settings.data_dir, self.settings.region_preset.bbox)
        areas = self.sample_areas()
        flights = sample_feed.pick_flights(
            pool, areas, skip=set(), limit=limit, prefer=self._has_route
        )
        shape = shapely.union_all(areas) if areas else None

        def in_ash(position: dict[str, Any]) -> bool:
            return shape is not None and shape.contains(
                shapely.Point(position["lon"], position["lat"])
            )

        return sample_feed.sample_batch(flights, self.sample_plans(flights), in_ash, timeutil.now())

    def stop_sample_feed(self) -> None:
        if self.sample_stop is not None:
            self.sample_stop.set()
            self.sample_stop, self.sample_connection_id = None, None

    def known_routes(self) -> dict[str, FlightRoute]:
        """hex -> the route of each airline target: the airline's own flight plan when one was
        pushed for it (``airline-plan``), else its callsign's usual route when it flies along a
        leg of it (VRS standing data)."""
        known: dict[str, FlightRoute] = {}
        for target in self.aircraft():
            plan = self.plan_for(target)
            if plan is not None:
                route = self._plan_route(target, plan)
                if route is not None:
                    known[target.hex] = route
                    continue
            if not target.airline:
                continue
            route = self.routes.lookup(target, self.airports, self.policy)
            if route is not None:
                known[target.hex] = route
        return known

    # --- pushed flight plans (tephra.desk.connections) ------------------------------------

    def plan_for(self, target: Aircraft) -> PushedFlightPlan | None:
        held = self.flight_plans.get(target.hex)
        if held is None and target.callsign:
            held = self.flight_plans.get(f"cs:{target.callsign}")
        return held[0] if held is not None else None

    def plan_numbers(self) -> dict[str, str]:
        """hex -> the airline's flight number, for the aircraft a held plan names."""
        out: dict[str, str] = {}
        for target in self.aircraft():
            plan = self.plan_for(target)
            if plan is not None:
                out[target.hex] = plan.flight
        return out

    def _plan_route(self, target: Aircraft, plan: PushedFlightPlan) -> FlightRoute | None:
        origin = self.routes.position(plan.origin_icao, self.airports)
        dest = self.routes.position(plan.dest_icao, self.airports)
        if origin is None or dest is None:
            return None
        cross = cross_track_nm(target, *origin, *dest)
        if cross is None:  # beyond an end of the leg: the distance to the nearer end
            cross = min(distance_nm(target.lat, target.lon, *p) for p in (origin, dest))
        return FlightRoute(
            callsign=target.callsign or plan.flight,
            origin_icao=plan.origin_icao,
            dest_icao=plan.dest_icao,
            cross_track_nm=round(cross, 1),
            source="airline-plan",
        )

    def closed_now(self) -> frozenset[str]:
        """The airports the current airport plan closes (empty before one is made)."""
        return self._closed_airports or frozenset()

    def take_plans(self, plans: Sequence[PushedFlightPlan], at: datetime) -> None:
        for plan in plans:
            if plan.hex:
                self.flight_plans[plan.hex] = (plan, at)
            if plan.callsign:
                self.flight_plans[f"cs:{plan.callsign}"] = (plan, at)
        # a plan is held until 3 h after its arrival, or 12 h after it came without one
        for key, (plan, got) in list(self.flight_plans.items()):
            until = (plan.sta or got + timedelta(hours=9)) + timedelta(hours=3)
            if at > until:
                del self.flight_plans[key]

    def plan_lines(self) -> list[PlanLine]:
        closed = self.closed_now()
        lines: dict[str, PlanLine] = {}
        for plan, _ in self.flight_plans.values():
            if plan.flight in lines:
                continue
            origin = self.routes.position(plan.origin_icao, self.airports)
            dest = self.routes.position(plan.dest_icao, self.airports)
            if origin is None or dest is None:
                continue
            lines[plan.flight] = PlanLine(
                flight=plan.flight,
                origin_icao=plan.origin_icao,
                dest_icao=plan.dest_icao,
                closed=plan.origin_icao in closed or plan.dest_icao in closed,
                coordinates=great_circle(*origin, *dest),
            )
        return list(lines.values())

    def route_layer(self, known: Mapping[str, FlightRoute]) -> dict[str, Any]:
        """The Wall's route lines: only for the RFA flights in or heading into an area."""
        legs: dict[tuple[str, str], set[str]] = {}
        for flight in self.exposed.values():
            route = known.get(flight.hex)
            if route is not None:
                legs.setdefault((route.origin_icao, route.dest_icao), set()).add(flight.hex)
        return route_features(legs, self.routes, self.airports)

    def spawn(self, coroutine: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    # --- the writer fence (rollouts) -----------------------------------------------------

    async def claim_writer(self) -> None:
        """Name this instance in ``runtime/writer`` at the start of every tick.

        ``--max-instances 1`` holds per revision: during a rollout the old revision's instance
        lives on while its streams stay open, but ticks reach only the serving revision. A
        tick is therefore the proof of serving, and it also ends a retirement (traffic moved
        back to this revision).
        """
        at = timeutil.SystemClock().now()
        await self.store.put(
            Collection.RUNTIME,
            WRITER_DOC,
            {
                "revision": os.environ.get("K_REVISION") or "local",
                "instance": self.instance_id,
                "at": timeutil.to_iso(at),
            },
        )
        self._writer_at = at
        self.last_tick_clock = time.monotonic()
        if self.retired:
            self.retired = False
            logger.warning("ticks reach this instance again; it polls and checkpoints again")

    async def check_writer(self) -> bool:
        """True when this instance is retired: another instance ticked after it last did.

        An instance that has not ticked yet has nothing of its own to fence, so it never
        retires on a writer doc it found at startup.
        """
        if self.retired:
            return True
        if self._writer_at is None:
            return False
        doc = await self.store.get(Collection.RUNTIME, WRITER_DOC)
        if doc is None or doc.get("instance") == self.instance_id:
            return False
        if timeutil.parse_iso(doc["at"]) <= self._writer_at:
            return False
        self._retire(doc)
        return True

    def _retire(self, writer: Mapping[str, Any]) -> None:
        self.retired = True
        passes = self.adsb_passes
        if passes is not None and passes is not asyncio.current_task():
            passes.cancel()
        self.adsb_passes = None
        self.end_streams()
        logger.warning(
            "retired: revision %s (instance %s) ticked after this instance; no more ADS-B "
            "passes, checkpoints or events here, and open streams were ended",
            writer.get("revision"),
            writer.get("instance"),
        )

    def end_streams(self) -> None:
        """End every open event stream once; each browser reconnects (to the serving
        revision) and resyncs from ``/api/wall``."""
        self.bus.publish(SseEvent.END_STREAMS)

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

    def store_ok(self) -> None:
        """A checked store write succeeded; the first after a failure ends the episode.

        Only writes end an episode: with reads failing and writes working (Firestore meters
        them apart), a successful read would otherwise flip the health every tick. The
        checkpoint writes ``runtime/state`` every five minutes, so a read failure that has
        passed clears by then."""
        at = timeutil.SystemClock().now()
        recovered = not self.store_health.ok
        self.store_health = self.store_health.model_copy(update={"ok": True, "last_ok_at": at})
        if recovered:
            self.trace(TraceStage.SYSTEM, "system", "Database working again")

    def store_failed(self, exc: Exception, *, calls: Literal["reads", "writes"] = "writes") -> None:
        """A checked store call failed; the first failure of an episode is traced."""
        error = f"{type(exc).__name__}: {exc}"[:STORE_ERROR_CHARS]
        first = self.store_health.ok
        update: dict[str, object] = {"ok": False, "last_error": error}
        if first:
            update["last_error_at"] = timeutil.SystemClock().now()
        self.store_health = self.store_health.model_copy(update=update)
        if first:
            self.trace(
                TraceStage.SYSTEM, "system", f"Database {calls} failing: {error}", level="warn"
            )

    async def restore(self) -> None:
        """Warm a LIVE runtime from the store after a restart.

        Official products come back with their original provenance, so their input hash is
        unchanged and a restart does not spend a Gemini call; the TAFs still valid come back
        too, so a planned flight's question (its open alternates) is the same after the
        restart and its kept answer still matches. Everything else refreshes on the first
        tick. A REPLAY always starts from its recording, with the answers its case folder
        keeps. Both modes first take up the audit chain's head (``_restore_audit_head``).
        """
        await self._restore_audit_head()
        if self.mode is RunMode.REPLAY:
            await self._seed_answers()
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
        tafs = await self._restore_records(
            Collection.TAFS, Taf, Where("valid_to", ">=", timeutil.to_iso(at))
        )
        self.live.sigmets = {record.provenance.source_id: record for record in sigmets}
        self.live.vonas = {record.provenance.source_id: record for record in vonas}
        self.live.vaas = {record.provenance.source_id: record for record in vaas}
        self.live.tafs = {taf.icao: taf for taf in tafs}
        await self._restore_bookkeeping()
        await self._restore_readings()
        await self._restore_duty()
        await self.worker.restore()

    async def _restore_audit_head(self) -> None:
        """One full walk of the chain at startup, unless the head the last checkpoint
        persisted (``runtime/audit_head``) still names the newest entry: that head is held as
        not yet walked on this instance and the first checkpoint walks it. A head below the
        newest entry, or none, is walked now."""
        persisted = audit.restore_head(
            self.store, await self.store.get(Collection.RUNTIME, AUDIT_HEAD_DOC)
        )
        newest = await audit.newest_entry(self.store)
        newest_seq = 0 if newest is None else newest.seq
        if persisted is not None and persisted.seq >= newest_seq:
            return
        self._trace_audit_head(await audit.verify_head(self.store))

    async def _seed_answers(self) -> None:
        """Answers the same model gave this case on an earlier run (``answers_path``), put in
        the store where ``recall`` finds them; every recall still goes through the skill's
        validators, and a newer answer already in the store is left alone."""
        if self.replay_case is None:
            return
        case_id = self.replay_case.case_id
        path = answers_path(case_path(self.settings.data_dir, case_id))
        if not path.is_file():
            return
        docs = await asyncio.to_thread(_read_answer_lines, path)
        summary = await asyncio.to_thread(_read_answer_summary, path.with_name("answers.json"))
        n = await self._answer_book.seed(docs)
        logger.info("ai_answer seed: %d answers for %s", n, case_id)
        models = {"main": self.settings.model, "lite": self.settings.model_lite}
        for problem in self._answer_book.seed_problems(docs, summary, models=models):
            logger.warning("ai_answer seed: %s", problem)

    async def _restore_duty(self) -> None:
        """The newest live Duty Officer run, so the Wall shows its brief after a restart."""
        docs = await self.store.query(
            Collection.DUTY,
            [Where("replay", "==", False)],
            order_by="started_at",
            descending=True,
            limit=1,
        )
        for doc in docs:
            try:
                self.duty = DutyRun.model_validate(doc)
            except ValidationError:
                logger.warning("ignoring an unreadable stored Duty Officer run")

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
        all_vaas = list(live.vaas.values())
        sigmets, vonas, vaas = select_records(
            self.catalogue,
            volcano,
            sigmets=list(live.sigmets.values()),
            vonas=list(live.vonas.values()),
            vaas=all_vaas,
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
            floor_vaas=select_floor_vaas(self.catalogue, volcano, vaas=all_vaas, at=at),
        )
        previous = self.situations.get(volcano.id)
        self.situations[volcano.id] = situation
        if await self._write_on_change(
            Collection.SITUATIONS, volcano.id, situation, SITUATION_CLOCK_FIELDS
        ):
            self._trace_new_discrepancies(situation, previous)
        assessment = await self._assessment(situation, at, report)
        await self._set_cone(situation, assessment)

    async def assess_volcano(
        self, volcano_id: str, at: datetime, report: TickReport, *, epoch: int | None = None
    ) -> dict[str, Any]:
        """The Duty Officer's ``assess_volcanoes`` for one volcano: the Satellite Reader and the
        Plume Reader read it, code rebuilds the cone and that volcano's exposure.

        The read runs outside ``lock`` (ticks go on meanwhile); its result is committed under
        it. A read whose inputs changed meanwhile is kept only where it still fits the official
        products now, as a held reading would be; a read that ends after the picture was
        reset (``epoch``) changes nothing."""
        epoch = self.epoch if epoch is None else epoch
        async with self.lock:
            situation = self.situations.get(volcano_id)
            if self.epoch != epoch or situation is None or volcano_id not in self.assess_due:
                return {"volcano_id": volcano_id, "error": "NO PLUME READ IS DUE"}
            del self.assess_due[volcano_id]
        try:
            assessment = await self._plume_read(situation, report)
        except NotOnHand:
            async with self.lock:  # the read waits for budget, due as it was
                if self.epoch == epoch and volcano_id not in self.assess_due:
                    self.assess_due[volcano_id] = situation.input_hash
            raise
        async with self.lock:
            current = self.situations.get(volcano_id)
            if self.epoch != epoch or current is None:
                return {"volcano_id": volcano_id, "error": "THE PICTURE CHANGED DURING THE READ"}
            if current.input_hash != situation.input_hash:
                if not _holds_while_pending(assessment, current, timeutil.now()):
                    self.trace(
                        TraceStage.PLUME,
                        "code",
                        f"{current.volcano.name}: the sources changed while the plume was read; "
                        "the reading is not used and the read is queued again",
                        level="warn",
                        volcano_id=volcano_id,
                    )
                    self.assess_due[volcano_id] = current.input_hash
                    return {
                        "volcano_id": volcano_id,
                        "error": "THE SOURCES CHANGED DURING THE READ; IT IS QUEUED AGAIN",
                    }
                situation = current
            self.assessments[volcano_id] = assessment
            cone = await self._set_cone(situation, assessment)
            if self.positions_fresh:
                self._replace_exposures(self._expose([cone], at), volcano_id=volcano_id)
        exposed = sum(flight.volcano_id == volcano_id for flight in self.exposed.values())
        band = _band_text(cone.base_ft, cone.top_ft)
        failed = assessment.outcome == "MODEL_FAILED"
        summary = (
            f"{situation.volcano.name}: plume read AI UNAVAILABLE, official products only "
            f"{band}; {exposed} flight(s) exposed"
            if failed
            else f"{situation.volcano.name}: {cone.label} {band}; {exposed} flight(s) exposed"
        )
        return {
            "volcano_id": volcano_id,
            "summary": summary,
            "status": "ai_unavailable" if failed else "ok",
            "outcome": assessment.outcome,
            "mode": cone.mode.value,
            "exposed_flights": exposed,
        }

    async def _set_cone(self, situation: Situation, assessment: PlumeAssessment) -> HazardCone:
        volcano = situation.volcano
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
        return cone

    async def _assessment(
        self, situation: Situation, at: datetime, report: TickReport
    ) -> PlumeAssessment:
        """The quota gate in front of the Plume Reader (MODULES.md 5.7). A read that matters is
        not made here: it is queued for the Duty Officer, and until it runs the area holds the
        last reading (when it still fits the official products) or the official products."""
        volcano = situation.volcano
        previous = self.assessments.get(volcano.id)
        if previous is not None and _still_current(previous, situation.input_hash, at):
            self.assess_due.pop(volcano.id, None)
            return previous
        outside_case = self._outside_replay_case(volcano.id)
        if outside_case or not self._model_call_matters(situation):
            self.assess_due.pop(volcano.id, None)
            why = (
                "not this replay's volcano"
                if outside_case
                else "no CAUTION or WARNING discrepancy, no HYPOTHESIS case and no airline"
                f" aircraft seen within {self.settings.adsb_radius_nm} NM"
            )
            self.trace(
                TraceStage.PLUME,
                "code",
                f"{volcano.name}: {why}; cone from official products only",
                volcano_id=volcano.id,
            )
            assessment = await self._read(situation, report, call_model=False)
        else:
            self.assess_due[volcano.id] = situation.input_hash
            if previous is not None and _holds_while_pending(previous, situation, at):
                return previous
            assessment = await self._read(situation, report, call_model=False, pending=True)
        self.assessments[volcano.id] = assessment
        return assessment

    async def _plume_read(self, situation: Situation, report: TickReport) -> PlumeAssessment:
        """The Plume Reader's reading of the products with the satellite reading of the newest
        frames: the same model's reading of the same input when it passes the checks now, else
        a model read, kept when it passes."""
        answers = self.answers
        if answers is None:
            return await self._read(situation, report, call_model=True)
        seen = await self._with_satellite(situation, report)
        reuse = answers.reuse(plume_question(seen, max_age=REASK_UNCHANGED))
        found = await reuse.recall_as(self.llm.model_id("main"), PlumeAssessment)
        if found is not None:
            answer, held = found
            known, problems = reused_assessment(answer, held, seen, trace=self.sink)
            if known is not None:
                report.assessments_run += 1
                await self.store.put(
                    Collection.ASSESSMENTS, known.id, known.model_dump(mode="json")
                )
                return known
            reuse.rejected(problems)
        assessment = await self._read(seen, report, call_model=True)
        if assessment.outcome in ("ACCEPTED", "REPAIRED"):
            await reuse.keep(
                assessment.model_id,
                assessment.model_dump(mode="json"),
                prompt_hash=assessment.prompt_hash,
                answered_at=assessment.created_at,
            )
        return assessment

    async def _satellite_on_hand(self, situation: Situation) -> Situation | None:
        """The look ahead's :meth:`_with_satellite`: the situation with the reading of the
        newest frames as the Plume Reader would get it, when that needs no model (the reading
        is current, or the same model's reading of these frames is kept); else None."""
        volcano = situation.volcano
        probe = self._frame_probe(volcano.id)
        held = self.satellite.get(volcano.id)
        if not is_current(held, volcano, probe):
            if FrameProduct.DUST_RGB not in select_frames(volcano, probe):
                return situation
            answers = self.answers
            if answers is None:
                return None
            held = await kept_reading(
                volcano,
                probe,
                situation.official_layers,
                self.llm,
                answers,
                replay=self.mode is RunMode.REPLAY,
            )
            if held is None:
                return None
        return _supported(situation, held, probe)

    def _frame_probe(self, volcano_id: str) -> list[tuple[SatelliteFrame, bytes]]:
        return [(frame, b"") for frame in self.live.frames.get(volcano_id, [])]

    async def _hold_satellite(self, reading: SatelliteReading) -> None:
        self.satellite[reading.volcano_id] = reading
        await self.store.put(Collection.SAT_READINGS, reading.id, reading.model_dump(mode="json"))
        self.bus.publish(SseEvent.SATELLITE, reading)

    async def _read(
        self,
        situation: Situation,
        report: TickReport,
        *,
        call_model: bool,
        pending: bool = False,
    ) -> PlumeAssessment:
        volcano = situation.volcano
        images = await self._images(situation) if call_model else []
        if call_model:
            situation = await self._with_satellite(situation, report)
        assessment = await read_plume(
            situation,
            self.llm,
            images=images,
            settings=self.settings,
            trace=self.sink,
            call_model=call_model,
            pending=pending,
        )
        if not pending:
            report.assessments_run += 1
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
        is not repeated; its text goes to the Plume Reader as supporting evidence. A hidden
        satellite feature (TEPHRA_FEATURES) reads nothing: no scheduled model work."""
        if "satellite" not in self.settings.features:
            return situation
        volcano = situation.volcano
        held = self.satellite.get(volcano.id)
        probe = self._frame_probe(volcano.id)
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
                trace=self.sink,
                answers=self.answers,
            )
            report.satellite_reads += 1
            await self._hold_satellite(held)
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
        return _supported(situation, held, probe)

    def _outside_replay_case(self, volcano_id: str) -> bool:
        """In REPLAY the main model reads only the case's own volcanoes: the region's other
        bulletins in the recording (Semeru, Dukono, Ibu on the Krakatau day) cost 15 of the 29
        reads a loop against 18 a day, for cones the case is not about. Their cones are drawn
        from the official products, as for any read that does not matter."""
        case = self.replay_case
        return (
            self.mode is RunMode.REPLAY
            and case is not None
            and bool(case.volcano_ids)
            and volcano_id not in case.volcano_ids
        )

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

    def plan_due(
        self, flight: ExposedFlight, drafts: Sequence[Advisory], at: datetime
    ) -> int | None:
        """The urgency bucket the flight is due to be planned in, or None: a flight is planned
        once per cone and bucket, again for a more urgent bucket, and after a planning error on
        the ``PLAN_RETRY_MIN`` schedule."""
        cone = self.cones.get(flight.volcano_id)
        if cone is None:
            return None
        urgency = _urgency(flight.inside_now, flight.minutes_to_entry, self.urgency_limits_min)
        planned = self._planned_urgency(flight.id, cone.id, drafts)
        if planned is not None and planned <= urgency:
            self._planned[flight.id] = (cone.id, planned)
            return None
        failed = self._plan_failures.get(flight.id)
        if failed is not None and (failed.cone_id, failed.urgency) == (cone.id, urgency):
            return None if at < failed.retry_at else urgency
        return urgency

    async def plan_flight_now(
        self,
        flight_id: str,
        drafts: Sequence[Advisory],
        at: datetime,
        report: TickReport,
        *,
        epoch: int | None = None,
    ) -> dict[str, Any]:
        """The Duty Officer's ``plan_flights`` for one flight: plan and draft it now.

        The models run outside ``lock``; the result is committed under it, and only while the
        flight is still in the same area of the same picture (``epoch``). The flight is marked
        planned only once a result is committed, so an error part-way (a store fault, say) or a
        changed area never leaves it marked with no draft: it is due again on the
        ``PLAN_RETRY_MIN`` schedule, or at once for a new cone or a more urgent entry."""
        epoch = self.epoch if epoch is None else epoch
        async with self.lock:
            flight = self.exposed.get(flight_id)
            if self.epoch != epoch or flight is None:
                return {"flight_id": flight_id, "error": "THE FLIGHT IS NO LONGER EXPOSED"}
            urgency = self.plan_due(flight, drafts, at)
            if urgency is None:
                return {"flight_id": flight_id, "error": "NO PLAN IS DUE FOR THIS FLIGHT"}
            cone = self.cones[flight.volcano_id]
        limits = self.urgency_limits_min
        outdated = [
            d for d in drafts if _urgency(d.inside_now, d.minutes_to_entry, limits) > urgency
        ]
        view = {"flight_id": flight.id, "proxy_flight": flight.proxy_flight}
        try:
            outcome, committed = await self._plan_and_draft(
                flight, cone, urgency, at, report, outdated, epoch
            )
        except NotOnHand:
            raise  # not planned: the flight waits for budget, due as it was
        except Exception as exc:
            logger.exception("planning %s failed", flight.id)
            failed = self._plan_failures.get(flight.id)
            if failed is not None and (failed.cone_id, failed.urgency) != (cone.id, urgency):
                failed = None  # a new cone or a new bucket counts afresh
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
            return {**view, "error": f"PLANNING FAILED ({failure}); DUE AGAIN IN {delay} MIN"}
        if not committed:
            return {**view, **outcome}
        self._plan_failures.pop(flight.id, None)
        self._planned[flight.id] = (cone.id, urgency)
        return {**view, **outcome}

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
        epoch: int,
    ) -> tuple[dict[str, Any], bool]:
        """Plan and draft one flight; returns what came of it, for the Duty Officer, and
        whether it was committed (False: the picture moved on while the models worked)."""
        situation = self.situations[flight.volcano_id]
        assessment = self.assessments[flight.volcano_id]
        ctx = self._planner_context(flight, cone, at)
        if ctx is None:
            raise KeyError(f"no situation for {flight.volcano_id}")
        answers = self.answers
        plan = await plan_flight(
            ctx,
            self.llm,
            settings=self.settings,
            trace=self.sink,
            reuse=None if answers is None else answers.reuse(self._planner_question(ctx, cone)),
        )
        advisory: Advisory | AiFailure | None = None
        if plan.decision is not None:
            advisory = await draft_advisory(
                situation=situation,
                assessment=assessment,
                cone=cone,
                ctx=ctx,
                plan=plan,
                llm=self.llm,
                settings=self.settings,
                policy=self.policy,
                trace=self.sink,
                feed_health=self.live.health,
                replay_case=self.replay_case if self.mode is RunMode.REPLAY else None,
                reuse=(
                    None
                    if answers is None
                    else answers.reuse(self._drafter_question(ctx, cone, plan))
                ),
            )
        async with self.lock:
            stale = self._planned_too_late(flight, cone, epoch)
            if stale is not None:
                self.trace(
                    TraceStage.PLANNER,
                    "code",
                    f"{flight.proxy_flight}: {stale}",
                    level="warn",
                    volcano_id=flight.volcano_id,
                    flight_id=flight.id,
                )
                return {"error": stale.upper()}, False
            await self._store_reroutes(flight, ctx.reroutes)
            await self.store.put(Collection.PLANS, plan.id, plan.model_dump(mode="json"))
            return await self._commit_draft(
                ctx, flight, plan, advisory, urgency, report, outdated
            ), True

    def _planned_too_late(self, flight: ExposedFlight, cone: HazardCone, epoch: int) -> str | None:
        """Why a plan made outside the lock no longer applies, or None."""
        if self.epoch != epoch:
            return "the picture was reset while the flight was planned; no draft"
        current = self.exposed.get(flight.id)
        if current is None:
            return "left every area while it was planned; no draft"
        held = self.cones.get(flight.volcano_id)
        if held is None or held.id != cone.id or current.cone_id != cone.id:
            return "the area changed while the flight was planned; it is planned again for it"
        return None

    def _planner_context(
        self, flight: ExposedFlight, cone: HazardCone, at: datetime
    ) -> PlannerContext | None:
        situation = self.situations.get(flight.volcano_id)
        if situation is None:
            return None
        return build_planner_context(
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

    async def _commit_draft(
        self,
        ctx: PlannerContext,
        flight: ExposedFlight,
        plan: PlannedAction,
        advisory: Advisory | AiFailure | None,
        urgency: int,
        report: TickReport,
        outdated: Sequence[Advisory],
    ) -> dict[str, Any]:
        if plan.decision is None or advisory is None:
            reason = "; ".join(plan.validation_errors[:3]) or "NO PLAN"
            failure = ai_failure(
                ctx,
                stage="planner",
                reason=reason,
                model_id=plan.model_id,
                replay=self.mode is RunMode.REPLAY,
            )
            await self._record_failure(failure)
            return _failed(failure)
        if isinstance(advisory, AiFailure):
            await self._record_failure(advisory)
            return _failed(advisory)
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
            # The action too: a delegation's outcome reads the same whether the draft was
            # stored now or was already open, so a kept Coordinator decision is not refused
            # (CAME OUT OTHERWISE) for a difference that is not the decision's.
            return {
                "summary": f"{flight.proxy_flight}: same advice as an open draft",
                "action": advisory.action.value,
            }
        reason = (
            "INSIDE THE CONE NOW"
            if flight.inside_now
            else f"ENTRY NOW IN {flight.minutes_to_entry} MIN"
        )
        for draft in outdated:
            report.drafts_superseded += await self._supersede_draft(
                draft, reason, superseded_by=created.id
            )
        await self._close_failure_of(flight.id, DRAFT_WAITING)
        report.drafts_created += 1
        self.trace(
            TraceStage.DESK,
            "code",
            f"{flight.proxy_flight}: DRAFT {created.action.value} waiting for a dispatcher",
            volcano_id=flight.volcano_id,
            flight_id=flight.id,
            detail={"advisory_id": created.id},
        )
        return {
            "summary": f"{flight.proxy_flight}: DRAFT {created.action.value} for a dispatcher",
            "advisory_id": created.id,
            "action": created.action.value,
        }

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
        if await self.track_failure(failure) is None:
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

    async def track_failure(self, failure: AiFailure) -> AiFailure | None:
        """Record a failure for the Desk (``desk.failures``) and follow it: the flight's earlier
        open failure no longer stands. None when the same failure already stands."""
        recorded = await record_failure(
            self.store, self.bus, failure, run_since=self.replay_run_since
        )
        if recorded is None:
            return None
        previous = self.open_failures.get(recorded.flight_id)
        self.open_failures[recorded.flight_id] = recorded
        if previous is not None and previous.id != recorded.id:
            await close_failure(self.store, self.bus, previous.id, reason=NEWER_FAILURE)
        return recorded

    async def _close_failure_of(self, flight_id: str, reason: str) -> None:
        failure = self.open_failures.pop(flight_id, None)
        if failure is not None:
            await close_failure(self.store, self.bus, failure.id, reason=reason)

    async def _follow_failures(self) -> None:
        """Once per picture (a start, a mode switch, a replay loop): retire the open drafts
        and close the open failures an earlier replay run left, and follow this mode's open
        failures, one per flight, so a flight that leaves the area or gets a draft closes its
        own."""
        if self._failures_followed:
            return
        run_since = self.replay_run_since
        replay = self.mode is RunMode.REPLAY
        if replay and not await self._retire_earlier_drafts():
            return
        for failure in await list_failures(self.store, replay=replay, limit=LIST_WINDOW):
            current = self.open_failures.get(failure.flight_id)
            if not of_run(failure, run_since):
                await close_failure(self.store, self.bus, failure.id, reason=REPLAY_RUN_ENDED)
            elif current is None:
                self.open_failures[failure.flight_id] = failure
            elif current.id != failure.id:  # listed newest first: this one is older
                await close_failure(self.store, self.bus, failure.id, reason=NEWER_FAILURE)
        self._failures_followed = True

    async def _retire_earlier_drafts(self) -> bool:
        """A replay plays its recording again on every run, and the AI works only after this
        first pass, so every open REPLAY draft here was made in an earlier run: its picture has
        ended, and a dispatcher must never see it as this run's work. False when the store
        cannot be read (the next pass tries again)."""
        try:
            drafts = await self.open_drafts()
        except DeskUnreachable:
            return False
        for draft in drafts:
            await self._supersede_draft(draft, DRAFT_RUN_ENDED)
        return True

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

    async def open_drafts(self) -> list[Advisory]:
        """Open drafts of the current mode: a replay's picture says nothing about the live
        desk's flights, nor the live picture about a replay's. Raises
        :class:`DeskUnreachable` when the store cannot be read."""
        drafts = await self._all_open_drafts()
        replay = self.mode is RunMode.REPLAY
        return [draft for draft in drafts if draft.replay == replay]

    async def _all_open_drafts(self) -> list[Advisory]:
        """The open drafts of both modes, read from the store only when an advisory was written
        in this process since the last read (every write publishes its advisory event) or the
        copy is older than :data:`DRAFTS_COPY_S`. Every worker pass, plan and publish asked the
        store for all of them: tens of thousands of document reads a replay loop."""
        last = self.bus.last(SseEvent.ADVISORY)
        written = last.id if last is not None else 0
        wall = time.monotonic()
        copy = self._drafts_copy
        if copy is not None and copy.written == written and wall - copy.read_at < DRAFTS_COPY_S:
            return list(copy.drafts)
        self._drafts_copy = None
        try:
            drafts = await _list_drafts(self.store)
        except Exception as exc:
            logger.warning("reading the open drafts failed: %s", exc)
            self.store_failed(exc, calls="reads")
            raise DeskUnreachable(str(exc)) from exc
        self._drafts_copy = _DraftsCopy(tuple(drafts), written, wall)
        return drafts

    def _positions_stale(self) -> bool:
        """Every position held is a last-good copy, served after its point's live fetch
        failed."""
        snapshots = self.live.adsb
        return bool(snapshots) and all(snapshot.provenance.stale for snapshot in snapshots)

    async def _retire_gone(
        self, open_drafts: Sequence[Advisory], seen: set[str], at: datetime, report: TickReport
    ) -> int:
        """Retire the open drafts, and close the open AI failures, of flights out of every cone,
        after the policy's grace time; returns the drafts retired.

        A flight seen outside every cone (or whose volcano is no longer active) keeps its
        draft or failure for ``drafts.unexposed_retire_min``; one missing from the ADS-B picture
        keeps it for ``drafts.position_lost_retire_min`` and is retired as POSITION LOST, never
        as no longer exposed: a dropped position says nothing about the ash. Only fresh
        positions count towards either time."""
        candidates = [draft for draft in open_drafts if draft.flight_id not in self.exposed]
        failed = [item for fid, item in self.open_failures.items() if fid not in self.exposed]
        if not (candidates or failed) or not self._adsb_fresh(at):
            self._forget_absences()
            if candidates:
                report.notes.append("ADS-B is stale: open drafts kept until positions refresh")
            return 0
        hexes = {item.flight_id: item.hex for item in [*candidates, *failed]}
        unseen = {fid for fid, hex_ in hexes.items() if hex_ not in seen}
        unexposed = hexes.keys() - unseen
        self._unseen_since = {fid: self._unseen_since.get(fid, at) for fid in unseen}
        self._unexposed_since = {fid: self._unexposed_since.get(fid, at) for fid in unexposed}
        retired = 0
        for draft in candidates:
            if (reason := self._gone_reason(draft.flight_id, draft.volcano_id, at)) is not None:
                retired += await self._supersede_draft(draft, reason)
        for failure in failed:
            if (reason := self._gone_reason(failure.flight_id, failure.volcano_id, at)) is not None:
                await self._close_failure_of(failure.flight_id, reason)
        return retired

    def _gone_reason(self, flight_id: str, volcano_id: str, at: datetime) -> str | None:
        """Why a flight out of every cone needs its draft or failure no more; None while its
        grace time lasts."""
        rules = self.policy.drafts
        if flight_id in self._unseen_since:
            lost = at - self._unseen_since[flight_id]
            if lost < timedelta(minutes=rules.position_lost_retire_min.value):
                return None
            return f"POSITION LOST FOR {int(lost.total_seconds() // 60)} MIN"
        away = at - self._unexposed_since[flight_id]
        if away < timedelta(minutes=rules.unexposed_retire_min.value):
            return None
        if volcano_id in self.live.active:
            return "NO LONGER EXPOSED IF TRACK AND LEVEL ARE HELD"
        return "VOLCANO NO LONGER ACTIVE"

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

    def volcano_name(self, volcano_id: str) -> str:
        volcano = self.catalogue.get(volcano_id)
        return volcano.name if volcano is not None else volcano_id

    def sink(self, event: TraceEvent) -> None:
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
        health = self.live.health
        return SituationCard(
            volcano_id=volcano.id,
            volcano_name=volcano.name,
            color_code=colors.get(volcano.id, AviationColor.UNKNOWN),
            active_reasons=situation.active_reasons,
            as_of=situation.as_of,
            cards=[
                _sigmet_card(situation, at, health.get(FeedId.SIGMET)),
                _vona_card(situation, at, self.settings.vona_window_h, health.get(FeedId.VONA)),
                _vaa_card(situation, at, health.get(_VAA_FEEDS[volcano.vaac])),
            ],
            discrepancies=situation.discrepancies,
            assessment=self.assessments.get(volcano.id),
            cone_id=cone.id if cone is not None else None,
            btd=situation.btd,
            frames=[_frame_thumb(frame) for frame in situation.frames],
            exposed_count=sum(1 for f in self.exposed.values() if f.volcano_id == volcano.id),
        )

    # --- mode switching ------------------------------------------------------------------

    async def _switch(
        self,
        mode: RunMode,
        *,
        auto: bool,
        case: ReplayCase | None = None,
        note: str | None = None,
    ) -> None:
        """Change mode. REPLAY plays ``case``, else the case playing, else
        ``TEPHRA_REPLAY_CASE`` or the newest recorded case; picking another case while
        replaying restarts the replay on it. ``note`` replaces the banner as the audit
        entry's note."""
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
            window = _start_clock(self.settings, case)  # raises on a bad case or window
            if playing is None:
                self._live_source = self.source
            else:
                await self.source.aclose()
            self.source = replay_source
            self.replay_case, self.auto_replay = case, auto
            self.replay_window = window
        else:
            if playing is None:
                return
            stop_replay_clock()
            await self.source.aclose()
            self.source = self._live_source or HttpSource.from_settings(self.settings)
            self._live_source = None
            self.replay_case, self.auto_replay = None, False
            self.replay_window = None
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
            note=note or banner,
        )
        # The choice must survive a restart before the next checkpoint.
        await self._checkpoint_write(
            Collection.RUNTIME, self.store.put(Collection.RUNTIME, "state", self._bookkeeping())
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
        self.epoch += 1
        self._drafts_copy = None
        self.worker.clear()
        self.assess_due.clear()
        self.duty_offered.clear()
        self.live = LiveData(
            health=initial_health(
                self.settings, replay=self.mode is RunMode.REPLAY, recorded=self.recorded_feeds
            )
        )
        self.situations.clear()
        self.assessments.clear()
        self.cones.clear()
        self.pushed.clear()
        self.exposed.clear()
        self.reroutes.clear()
        self.satellite.clear()
        self._closed_airports = None
        self._schedule = None
        self._planned.clear()
        self._plan_failures.clear()
        self.open_failures.clear()
        self._failures_followed = False
        self.duty = None
        self._forget_absences()
        self._digests.clear()
        self._published.clear()
        self._quiet_ticks = 0
        self._replay_at = None
        self.fixes.clear()
        self._crew_traced.clear()
        self._replay_run_wall = timeutil.SystemClock().now()
        self.crew = self.crew_picture(timeutil.now())

    async def _live_activity(self) -> bool:
        source = self.source if self.mode is RunMode.LIVE else self._live_source
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
        return any(self._in_region(vid) for vid in active)

    def _in_region(self, volcano_id: str) -> bool:
        """Auto-replay weighs only the deployed region's volcanoes: activity elsewhere in the
        catalogue neither keeps LIVE from going quiet nor ends a replay."""
        volcano = self.catalogue.get(volcano_id)
        return volcano is not None and self.settings.region_preset.bbox.contains(
            volcano.lat, volcano.lon
        )

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
        """Checkpoint what a restart reads back: ``runtime/state`` first, then feed state,
        then records whose earlier write failed. Each write is tried on its own, so one
        failing document does not skip the others."""
        await self._checkpoint_write(
            Collection.RUNTIME, self.store.put(Collection.RUNTIME, "state", self._bookkeeping())
        )
        for state in self.live.health.values():
            await self._checkpoint_write(
                Collection.FEED_STATE,
                self._write_on_change(
                    Collection.FEED_STATE, state.feed.value, state, FEED_STATE_CLOCK_FIELDS
                ),
            )
        await save_unsaved(self)

    async def _checkpoint_audit_head(self) -> None:
        """Walk the audit chain again when an append found another writer's entry, then
        persist the head beside ``runtime/state`` for the next start."""
        held = audit.chain(self.store)
        if held.rewalk:
            try:
                head = await audit.verify_head(self.store)
            except Exception as exc:  # the mark stays; the next checkpoint walks again
                logger.warning("audit chain walk failed: %s", exc)
                self.store_failed(exc, calls="reads")
            else:
                self._trace_audit_head(head)
        if held.head is None:
            return
        await self._checkpoint_write(
            Collection.RUNTIME,
            self.store.put(Collection.RUNTIME, AUDIT_HEAD_DOC, held.head.model_dump(mode="json")),
        )

    def _trace_audit_head(self, head: ChainHead) -> None:
        if head.intact:
            return
        self.trace(
            TraceStage.SYSTEM,
            "system",
            f"Audit chain not intact at seq {head.seq}: {'; '.join(head.problems[:3])}",
            level="warn",
        )

    async def _checkpoint_write(self, collection: Collection, write: Awaitable[object]) -> None:
        try:
            await write
        except Exception as exc:
            logger.warning("checkpoint write to %s failed: %s", collection.value, exc)
            self.store_failed(exc)
        else:
            self.store_ok()

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
            "saved_at": timeutil.to_iso(timeutil.now()),
        }

    async def restore_replay_choice(self) -> None:
        """After a restart of a LIVE-configured process, come back to the replay it was
        playing: a dispatcher's choice from the Desk always, an automatic one while
        ``TEPHRA_AUTO_REPLAY`` is still on and the live SIGMETs show no activity. The replay
        starts again from its start; ``TEPHRA_MODE=REPLAY`` never reaches here."""
        if self.mode is not RunMode.LIVE:
            return
        doc = await self.store.get(Collection.RUNTIME, "state")
        if doc is None or doc.get("mode") != RunMode.REPLAY.value:
            return
        auto = doc.get("auto_replay") is True
        if auto and not self.settings.auto_replay:
            return
        case_id = doc.get("case_id")
        try:
            case = await asyncio.to_thread(
                select_case, self.settings.data_dir, case_id if isinstance(case_id, str) else None
            )
        except (OSError, ValueError) as exc:
            self.trace(
                TraceStage.SYSTEM,
                "system",
                f"The replay playing before the restart cannot be loaded ({exc}); starting LIVE",
                level="warn",
            )
            return
        if auto and await self._live_activity():
            self.trace(
                TraceStage.SYSTEM,
                "system",
                "Live VA SIGMET for a volcano in the region: the automatic replay from before the "
                "restart is not resumed",
            )
            return
        await self._switch(RunMode.REPLAY, auto=auto, case=case, note=RESTORED_NOTE)

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
    window: tuple[datetime, datetime] | None = None
    source: Source
    if settings.mode is RunMode.REPLAY:
        replay_case = select_case(settings.data_dir, settings.replay_case)
        source = ReplaySource(case_path(settings.data_dir, replay_case.case_id), replay_case)
        window = _start_clock(settings, replay_case)
    else:
        source = HttpSource.from_settings(settings)
    store = open_store(settings)
    ledger = QuotaLedger(settings, store)
    if settings.llm == "gemini" and settings.unlimited_models():
        logger.warning(
            "no free-tier limits for %s: those models are never called (AI UNAVAILABLE) "
            "until TEPHRA_MODEL_LIMITS has a row for each",
            ", ".join(settings.unlimited_models()),
        )
    runtime = Runtime(
        settings=settings,
        store=store,
        bus=get_bus(),
        source=source,
        llm=get_llm(settings, quota=ledger),
        catalogue=catalogue,
        airports=airports,
        routes=routes,
        policy=policy,
        mode=settings.mode,
        replay_case=replay_case,
        auto_replay=False,
        ledger=ledger,
    )
    runtime.replay_window = window
    await runtime.restore_crew_reports()
    await runtime.restore_replay_choice()
    await runtime.restore()
    runtime.start_worker()
    return runtime


def _start_clock(settings: Settings, case: ReplayCase) -> tuple[datetime, datetime] | None:
    """Start the replay clock on ``case`` and return the looping window it plays, if any.

    The configured window (TEPHRA_REPLAY_START to TEPHRA_REPLAY_END) belongs to
    TEPHRA_REPLAY_CASE alone; another case chosen at the Desk plays its whole recording.
    """
    speed, quantum_s = settings.replay_speed, settings.replay_quantum_s
    if settings.replay_start is None or settings.replay_end is None:
        start_replay_clock(case, speed=speed, begin=settings.replay_start, quantum_s=quantum_s)
        return None
    if case.case_id != settings.replay_case:
        start_replay_clock(case, speed=speed, quantum_s=quantum_s)
        return None
    window = (settings.replay_start, settings.replay_end)
    start_replay_clock(case, speed=speed, begin=window[0], end=window[1], quantum_s=quantum_s)
    return window


def _read_answer_summary(path: Path) -> dict[str, Any] | None:
    """The ``answers.json`` written beside a seed file; None when absent or unreadable."""
    if not path.is_file():
        return None
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        logger.warning("skipping an unreadable %s", path)
        return None
    return summary if isinstance(summary, dict) else None


def _read_answer_lines(path: Path) -> list[dict[str, Any]]:
    """The JSON objects of a ``.jsonl`` file; a line that is not one is logged and skipped."""
    docs: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            doc = json.loads(line)
        except ValueError:
            logger.warning("skipping unreadable answer line %d of %s", number, path)
            continue
        if isinstance(doc, dict):
            docs.append(doc)
        else:
            logger.warning("skipping answer line %d of %s: not an object", number, path)
    return docs


# --- quota and planning rules (pure) ----------------------------------------------------


def _supported(
    situation: Situation,
    held: SatelliteReading | None,
    probe: Sequence[tuple[SatelliteFrame, bytes]],
) -> Situation:
    """The situation with the reading's text as supporting evidence, when the reading is of
    the newest frames and has text for the Plume Reader."""
    part = plume_part(held) if held is not None else None
    if held is None or part is None or not is_current(held, situation.volcano, probe):
        return situation
    evidence = SupportingEvidence(source_id=held.id, text=part.text or "")
    return situation.model_copy(update={"supporting": [evidence]})


def _still_current(assessment: PlumeAssessment, input_hash: str, at: datetime) -> bool:
    """The same input keeps its assessment through the estimate's horizon, and past it until
    :data:`REASK_UNCHANGED` has gone by since the ask."""
    if assessment.input_hash != input_hash:
        return False
    keep = max(timedelta(hours=assessment.estimate.horizon_h), REASK_UNCHANGED)
    return at < assessment.created_at + keep


def _holds_while_pending(previous: PlumeAssessment, situation: Situation, at: datetime) -> bool:
    """Whether the last reading may stand while a new read waits for the Duty Officer: a model
    reading still within its horizon whose mode fits the official products now (a HYPOTHESIS
    once an official area is valid, or an OFFICIAL/WIDENED area without one, may not)."""
    if previous.outcome == "PENDING":
        return False
    if at >= previous.created_at + timedelta(hours=previous.estimate.horizon_h):
        return False
    if previous.estimate.mode is PlumeMode.HYPOTHESIS:
        return not situation.official_valid_now()
    return bool(situation.official_layers)


def _failed(failure: AiFailure) -> dict[str, Any]:
    return {
        "summary": f"{failure.proxy_flight}: AI UNAVAILABLE ({failure.stage}), to the Desk",
        "status": "ai_unavailable",
        "reason": failure.reason,
    }


class _DraftsCopy(NamedTuple):
    drafts: tuple[Advisory, ...]
    written: int
    """The id of the last advisory event when the drafts were read"""
    read_at: float


async def _list_drafts(store: Store) -> list[Advisory]:
    """Open drafts, newest first. A stored draft that no longer validates is skipped and
    logged, as a restore skips one: it must not stop every tick's publish."""
    docs = await store.query(
        Collection.ADVISORIES,
        [Where("status", "==", AdvisoryStatus.DRAFT.value)],
        order_by="created_at",
        descending=True,
        limit=OPEN_DRAFT_LIMIT,
    )
    drafts: list[Advisory] = []
    for doc in docs:
        try:
            drafts.append(Advisory.model_validate(doc))
        except ValidationError:
            logger.warning("ignoring unreadable stored advisory %s", doc.get("id"))
    return drafts


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
    aircraft: Sequence[Aircraft],
    exposed: Iterable[ExposedFlight],
    crew: CrewPicture,
    routes: Mapping[str, FlightRoute],
    plans: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """``plans``: hex -> the airline's flight number, for the flights a pushed plan names."""
    earliest: dict[str, ExposedFlight] = {}
    for flight in exposed:
        held = earliest.get(flight.hex)
        if held is None or flight.minutes_to_entry < held.minutes_to_entry:
            earliest[flight.hex] = flight
    flagged = {flag.hex for flag in crew.flags}
    features = []
    for target in aircraft:
        hit = earliest.get(target.hex)
        route = routes.get(target.hex)
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
            crew_report=target.hex in flagged,
            origin_icao=route.origin_icao if route is not None else None,
            dest_icao=route.dest_icao if route is not None else None,
            label=_aircraft_label(target, hit),
            data_source="AIRLINE" if target.source_id.startswith("PUSH:") else "ADSB",
            route_source=None
            if route is None
            else "PLAN"
            if route.source == "airline-plan"
            else "VRS",
            flight_plan=(plans or {}).get(target.hex),
        )
        features.append(feature(point(target.lat, target.lon), props, feature_id=target.hex))
    return feature_collection(features)


def _stamped(record: Any, stamp: str) -> Any:
    return {**record, "observed_at": stamp} if isinstance(record, dict) else record


def _pushed_dot(target: Aircraft, exposed: set[str]) -> PushedDot:
    return PushedDot(
        hex=target.hex,
        callsign=target.callsign,
        lat=target.lat,
        lon=target.lon,
        alt_baro_ft=target.alt_baro_ft or 0,
        track_deg=target.track_deg,
        in_ash=target.hex in exposed,
    )


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


def _missing_card(kind: ProductKind, health: FeedHealth | None, none_seen: str) -> SourceCard:
    reason, note = _missing_reason(kind, health, none_seen)
    return SourceCard(kind=kind, missing=True, missing_reason=reason, missing_note=note, title=kind)


def _missing_reason(
    kind: ProductKind, health: FeedHealth | None, none_seen: str
) -> tuple[MissingReason, str]:
    """Why ``kind`` has no product. Only a feed that answers may say none was issued: a
    feed TEPHRA does not read, one the replay did not record, or one that is down says so.
    Situations exist only for active volcanoes, so a feed never polled yet counts as down."""
    if health is None or health.status in (FeedStatus.ERROR, FeedStatus.NEVER):
        since = (
            f"since {timeutil.hhmmz(health.last_success_at)}"
            if health is not None and health.last_success_at is not None
            else "yet"
        )
        return "FEED_DOWN", f"{kind} feed not answering {since}: none seen"
    if health.status is FeedStatus.DISABLED:
        if health.last_error == VONA_OFF_NOTE:
            return "NOT_READ", VONA_NOT_READ_NOTE
        if health.last_error == NOT_RECORDED_NOTE:
            return "NOT_RECORDED", f"Not in this replay: no {kind} archive was recorded"
        return (
            "NOT_READ",
            f"Not read: {health.last_error}" if health.last_error else "Not read: this feed is off",
        )
    return "NONE_SEEN", none_seen


def _sigmet_card(situation: Situation, at: datetime, health: FeedHealth | None) -> SourceCard:
    records = sorted(
        situation.sigmets,
        key=lambda sigmet: (sigmet.valid_from, sigmet.provenance.source_id),
        reverse=True,
    )
    if not records:
        return _missing_card("SIGMET", health, "No valid VA SIGMET")
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


def _vona_card(
    situation: Situation, at: datetime, window_h: float, health: FeedHealth | None
) -> SourceCard:
    records = sorted(situation.vonas, key=lambda vona: vona.issued_at, reverse=True)
    if not records:
        return _missing_card("VONA", health, f"No VONA in the last {window_h:g} h")
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


def _vaa_card(situation: Situation, at: datetime, health: FeedHealth | None) -> SourceCard:
    records = sorted(situation.vaas, key=lambda vaa: vaa.issued_at, reverse=True)
    if not records:
        return _missing_card("VAA", health, _missing_vaa_note(situation, at))
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
