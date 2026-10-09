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
from datetime import datetime, timedelta
from typing import Any, Final, Literal

from pydantic import BaseModel, ValidationError

from tephra.agents.dispatch_drafter import draft_advisory
from tephra.agents.exposure_planner import build_planner_context, plan_flight
from tephra.agents.llm import LlmBackend, LlmPart, get_llm
from tephra.agents.plume_reader import read_plume
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
from tephra.feeds.adsb import merge_aircraft
from tephra.feeds.airports import AirportCatalogue, load_airports
from tephra.feeds.base import FetchError, HttpSource, Source
from tephra.feeds.registry import LiveData, health_view, initial_health
from tephra.feeds.sigmet import fetch_sigmets
from tephra.feeds.volcanoes import VolcanoCatalogue, load_volcanoes
from tephra.geo.cone import build_cone
from tephra.geo.exposure import find_exposed
from tephra.geo.units import deg_to_compass, distance_nm, ft_to_fl
from tephra.models import (
    Advisory,
    AdvisoryStatus,
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
    FrameThumb,
    GeoLineString,
    HazardCone,
    LlmInfo,
    Overlays,
    PlumeAssessment,
    ReplayCase,
    RunMode,
    SatelliteFrame,
    Severity,
    Sigmet,
    Situation,
    SituationCard,
    SourceCard,
    SseEvent,
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
from tephra.reconcile.discrepancies import (
    build_situation,
    evidence_state,
    find_active,
    select_records,
)
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
RETIRE_AFTER_RUNS: Final = 2
"""A draft is superseded only after its flight is missing from two exposure runs in a row,
so one dropped ADS-B position does not throw away a dispatcher's pending decision."""
BTD_CREDIT: Final = "Himawari-9 data: JMA via NOAA (NODD), processed by TEPHRA."

TraceLevel = Literal["info", "warn", "error"]


@dataclass(eq=False)
class Runtime:
    settings: Settings
    store: Store
    bus: EventBus
    source: Source
    llm: LlmBackend
    catalogue: VolcanoCatalogue
    airports: AirportCatalogue
    mode: RunMode
    replay_case: ReplayCase | None
    auto_replay: bool
    live: LiveData = field(init=False, default_factory=LiveData)
    lock: asyncio.Lock = field(init=False, default_factory=asyncio.Lock, repr=False)
    situations: dict[str, Situation] = field(init=False, default_factory=dict)
    assessments: dict[str, PlumeAssessment] = field(init=False, default_factory=dict)
    cones: dict[str, HazardCone] = field(init=False, default_factory=dict)
    exposed: dict[str, ExposedFlight] = field(init=False, default_factory=dict)
    last_tick: TickReport | None = field(init=False, default=None)
    _planned: dict[str, str] = field(init=False, default_factory=dict)
    _missing_runs: dict[str, int] = field(init=False, default_factory=dict)
    _digests: dict[str, str] = field(init=False, default_factory=dict)
    _quiet_ticks: int = field(init=False, default=0)
    _live_source: Source | None = field(init=False, default=None)
    _snapshot: WallSnapshot | None = field(init=False, default=None)
    _persisted_exposures: set[str] = field(init=False, default_factory=set)
    _last_checkpoint: float | None = field(init=False, default=None)
    _tasks: set[asyncio.Task[None]] = field(init=False, default_factory=set, repr=False)

    def __post_init__(self) -> None:
        self.live.health = initial_health(self.settings, replay=self.mode is RunMode.REPLAY)

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
            situations=[self._situation_card(situation, at, colors) for situation in situations],
            overlays=Overlays(
                btd=[
                    _btd_overlay(s.btd, s.btd.image_key)
                    for s in situations
                    if s.btd is not None and s.btd.image_key is not None
                ],
                frames=[_frame_thumb(frame) for s in situations for frame in s.frames],
            ),
        )

    async def switch_mode(self, mode: RunMode, *, auto: bool = False) -> None:
        async with self.lock:
            await self._switch(mode, auto=auto)

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
        settings = self.settings
        aircraft = self.aircraft()
        exposed: dict[str, ExposedFlight] = {}
        for cone in self.cones.values():
            for flight in find_exposed(
                cone,
                aircraft,
                at,
                lookahead_min=settings.exposure_lookahead_min,
                vertical_margin_ft=settings.vertical_margin_ft,
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
        report.exposed_flights = len(exposed)

        open_drafts = await list_advisories(
            self.store, status=AdvisoryStatus.DRAFT, limit=OPEN_DRAFT_LIMIT
        )
        drafts_by_flight: dict[str, list[Advisory]] = {}
        for draft in open_drafts:
            drafts_by_flight.setdefault(draft.flight_id, []).append(draft)
        for flight in sorted(exposed.values(), key=_entry_order):
            cone = self.cones[flight.volcano_id]
            if self._planned.get(flight.id) == cone.id:
                continue
            if any(draft.cone_id == cone.id for draft in drafts_by_flight.get(flight.id, [])):
                self._planned[flight.id] = cone.id
                continue
            # Marked planned even on failure: retrying a broken flight every tick would
            # spend model calls on the same error. A new cone plans it again.
            self._planned[flight.id] = cone.id
            try:
                if await self._plan_and_draft(flight, cone, at):
                    report.drafts_created += 1
            except Exception as exc:
                logger.exception("planning %s failed", flight.id)
                failure = type(exc).__name__
                report.notes.append(f"{flight.proxy_flight}: planning failed ({failure})")
                self.trace(
                    TraceStage.PLANNER,
                    "system",
                    f"{flight.proxy_flight}: planning failed; no draft this cone",
                    level="error",
                    volcano_id=flight.volcano_id,
                    flight_id=flight.id,
                )
        report.drafts_superseded += await self._retire_drafts(open_drafts, at, report)
        self._planned = {fid: cid for fid, cid in self._planned.items() if fid in exposed}

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
        bus.publish(SseEvent.AIRCRAFT, snapshot.aircraft)
        bus.publish(SseEvent.OVERLAYS, snapshot.overlays)
        for card in snapshot.situations:
            bus.publish(SseEvent.SITUATION, card)

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
        self.bus.publish(SseEvent.TRACE, event)
        return event

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
            if state.replay or (state.feed is FeedId.HSD and not self.settings.science):
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
        )
        previous = self.situations.get(volcano.id)
        self.situations[volcano.id] = situation
        if await self._write_on_change(Collection.SITUATIONS, volcano.id, situation, {"as_of"}):
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
        if (
            previous is not None
            and previous.input_hash == situation.input_hash
            and at < previous.created_at + timedelta(hours=previous.estimate.horizon_h)
        ):
            return previous
        call_model = self._model_call_matters(situation)
        images = await self._images(situation) if call_model else []
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
        if not call_model:
            self.trace(
                TraceStage.PLUME,
                "code",
                f"{volcano.name}: official products changed with no disagreement, no "
                "HYPOTHESIS case and no aircraft near; cone from official products only",
                volcano_id=volcano.id,
            )
        if assessment.outcome == "FALLBACK_OFFICIAL":
            await audit.record(
                self.store,
                actor=SYSTEM_ACTOR,
                action=AuditAction.PLUME_FALLBACK,
                after={"volcano_id": volcano.id, "assessment_id": assessment.id},
                input_hashes=[situation.input_hash],
                model_id=assessment.model_id,
                prompt_hash=assessment.prompt_hash,
                note="; ".join(assessment.validation_errors) or "model returned nothing usable",
            )
        return assessment

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
        keyed = [(frame.provenance.source_id, frame.image_key) for frame in situation.frames]
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

    async def _plan_and_draft(self, flight: ExposedFlight, cone: HazardCone, at: datetime) -> bool:
        situation = self.situations[flight.volcano_id]
        assessment = self.assessments[flight.volcano_id]
        ctx = build_planner_context(
            flight,
            cone,
            volcano_name=situation.volcano.name,
            airports=self.airports,
            tafs=self.live.tafs,
            at=at,
            settings=self.settings,
        )
        plan = await plan_flight(ctx, self.llm, settings=self.settings, trace=self._sink)
        await self.store.put(Collection.PLANS, plan.id, plan.model_dump(mode="json"))
        advisory = await draft_advisory(
            situation=situation,
            assessment=assessment,
            cone=cone,
            ctx=ctx,
            plan=plan,
            llm=self.llm,
            settings=self.settings,
            trace=self._sink,
        )
        created = await submit_draft(self.store, self.bus, advisory)
        if created is None:
            self.trace(
                TraceStage.DESK,
                "code",
                f"{flight.proxy_flight}: same advice as an open or just-approved advisory; "
                "no new draft",
                volcano_id=flight.volcano_id,
                flight_id=flight.id,
            )
            return False
        self.trace(
            TraceStage.DESK,
            "code",
            f"{flight.proxy_flight}: DRAFT {created.action.value} waiting for a dispatcher",
            volcano_id=flight.volcano_id,
            flight_id=flight.id,
            detail={"advisory_id": created.id},
        )
        return True

    async def _retire_drafts(
        self, open_drafts: Sequence[Advisory], at: datetime, report: TickReport
    ) -> int:
        candidates = [draft for draft in open_drafts if draft.flight_id not in self.exposed]
        missing = {draft.flight_id for draft in candidates}
        self._missing_runs = {fid: self._missing_runs.get(fid, 0) + 1 for fid in missing}
        if not candidates:
            return 0
        if not self._adsb_fresh(at):
            report.notes.append("ADS-B is stale: open drafts kept until positions refresh")
            return 0
        retired = 0
        for draft in candidates:
            volcano_active = draft.volcano_id in self.live.active
            if volcano_active and self._missing_runs[draft.flight_id] < RETIRE_AFTER_RUNS:
                continue
            reason = (
                "NO LONGER EXPOSED IF TRACK AND LEVEL ARE HELD"
                if volcano_active
                else "VOLCANO NO LONGER ACTIVE"
            )
            if await supersede(self.store, self.bus, draft.id, reason=reason) is None:
                continue
            retired += 1
            self.trace(
                TraceStage.DESK,
                "system",
                f"{draft.proxy_flight}: draft superseded ({reason.lower()})",
                volcano_id=draft.volcano_id,
                flight_id=draft.flight_id,
                detail={"advisory_id": draft.id},
            )
        return retired

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
                level="warn" if item.severity is Severity.WARNING else "info",
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

    def _volcano_name(self, volcano_id: str) -> str:
        volcano = self.catalogue.get(volcano_id)
        return volcano.name if volcano is not None else volcano_id

    def _sink(self, event: TraceEvent) -> None:
        self.bus.publish(SseEvent.TRACE, event)

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

    async def _switch(self, mode: RunMode, *, auto: bool) -> None:
        """Change mode. REPLAY plays ``replay_case`` when a caller has set it, else
        ``TEPHRA_REPLAY_CASE`` or the newest recorded case; picking another case while
        replaying restarts the replay on it."""
        playing = self.source.case if isinstance(self.source, ReplaySource) else None
        previous = {"mode": self.mode.value, "case_id": playing.case_id if playing else None}
        if mode is RunMode.REPLAY:
            case = self.replay_case or select_case(
                self.settings.data_dir, self.settings.replay_case
            )
            if playing is not None and playing.case_id == case.case_id:
                return
            replay_source = ReplaySource(case_path(self.settings.data_dir, case.case_id), case)
            if playing is None:
                self._live_source = self.source
            else:
                await self.source.aclose()
            self.source = replay_source
            start_replay_clock(case, speed=self.settings.replay_speed)
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

    def _reset_picture(self) -> None:
        """Nothing recorded and nothing live may mix: a mode switch starts a fresh picture."""
        self.live = LiveData(
            health=initial_health(self.settings, replay=self.mode is RunMode.REPLAY)
        )
        self.situations.clear()
        self.assessments.clear()
        self.cones.clear()
        self.exposed.clear()
        self._planned.clear()
        self._missing_runs.clear()
        self._digests.clear()
        self._quiet_ticks = 0
        self._snapshot = None

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
        self, collection: Collection, doc_id: str, model: BaseModel, exclude: set[str]
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
            "planned": dict(self._planned),
            "assessment_ids": {vid: item.id for vid, item in self.assessments.items()},
            "last_tick": self.last_tick.model_dump(mode="json") if self.last_tick else None,
            "saved_at": timeutil.to_iso(timeutil.now()),
        }

    async def _restore_bookkeeping(self) -> None:
        doc = await self.store.get(Collection.RUNTIME, "state")
        if doc is None or doc.get("mode") != RunMode.LIVE.value:
            return
        self._quiet_ticks = int(doc.get("quiet_ticks") or 0)
        self._planned = {str(fid): str(cid) for fid, cid in (doc.get("planned") or {}).items()}
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
    catalogue = await asyncio.to_thread(load_volcanoes, settings.data_dir)
    airports = await asyncio.to_thread(load_airports, settings.data_dir)
    replay_case: ReplayCase | None = None
    source: Source
    if settings.mode is RunMode.REPLAY:
        replay_case = select_case(settings.data_dir, settings.replay_case)
        source = ReplaySource(case_path(settings.data_dir, replay_case.case_id), replay_case)
        start_replay_clock(replay_case, speed=settings.replay_speed)
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
        mode=settings.mode,
        replay_case=replay_case,
        auto_replay=False,
    )
    await runtime.restore()
    return runtime


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
