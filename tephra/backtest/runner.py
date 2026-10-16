"""Replay each case on a stepped clock and score the zone against the official areas issued later.

A case is played through the real pipeline (``run_tick`` on a ``ReplaySource``, a fixed clock
moved ``step`` at a time, no network). After every tick the zone TEPHRA drew and the official
area it was built on are kept. Official areas published later are collected from the same
replay: whatever a tick's situation holds was issued by that tick's clock, so a footprint
first seen at tick u was issued after every tick before it. A tick is scored against the
footprints issued after it, and only those its zone claims to reach (valid at or before the
cone's ``valid_to``).

Arm D (stub plume reader) spends no model call. Arm G reads the Plume Reader's Gemini answers
from the LLM disk cache and spends at most ``max_calls`` new calls, none by default.
"""

import tempfile
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Final

from shapely.geometry import Point, Polygon
from shapely.geometry.base import BaseGeometry

from tephra.agents.llm import GeminiBackend, LlmBackend, Tier, get_llm
from tephra.backtest.metrics import (
    TAUS,
    Footprint,
    Projection,
    coverage,
    footprint_lead,
    score_tick,
    summarise,
    summarise_leads,
    union,
)
from tephra.backtest.models import (
    Arm,
    BacktestScorecard,
    CaseScore,
    FootprintLead,
    LeadSummary,
    ModelUse,
    TickScore,
)
from tephra.config import FEED_CLOCK_SLACK, Settings
from tephra.feeds.airports import load_airports
from tephra.feeds.routes import load_routes
from tephra.feeds.volcanoes import load_volcanoes
from tephra.geo.cone import covers_official
from tephra.models import (
    FeedId,
    HazardCone,
    OfficialLayer,
    ReplayCase,
    RunMode,
    Sigmet,
    Situation,
    VaacAdvisory,
    Volcano,
)
from tephra.pipeline import Runtime
from tephra.policy import load_policy
from tephra.replay.cases import ReplaySource, case_path, load_case
from tephra.scheduler import run_tick
from tephra.store.base import Collection, Store
from tephra.store.sqlite_store import SqliteStore
from tephra.util import timeutil
from tephra.util.events import EventBus

__all__ = [
    "DEFAULT_STEP",
    "SyntheticCase",
    "load_scorecard",
    "run_backtest",
    "run_case",
    "store_scorecard",
    "write_scorecard",
]

DEFAULT_STEP: Final = timedelta(minutes=30)
LATEST_DOC: Final = "latest"
PRODUCT_FEEDS: Final = (FeedId.SIGMET, FeedId.VONA, FeedId.VAAC_DARWIN, FeedId.VAAC_TOKYO)
CAVEATS: Final = (
    "The official product issued later is partly derived from the same VONA and satellite "
    "inputs, so it is not independent ground truth.",
    "An Indonesian SIGMET copies the Darwin VAA, so 'official later' is effectively one voice.",
    "Satellite retrievals miss coarse ash, and the official polygon has its own lag.",
    "TEPHRA's zone is a decision margin that may only widen the official area, not a forecast "
    "of observed ash; Jaccard (CSI, FMS) against a later polygon is low by construction.",
    "Ticks are sampled every step minutes, so an advisory that a later one replaced inside "
    "one step is not scored.",
)


class _CappedGemini(GeminiBackend):
    """Arm G's backend: the disk cache is free, and new calls stop at ``max_calls``."""

    def __init__(self, settings: Settings, *, max_calls: int) -> None:
        super().__init__(settings)
        self._max_calls = max_calls
        self.calls = 0

    async def reserve(self, tier: Tier) -> str | None:
        """The cap is this offline run's whole budget: no daily pacing applies to it."""
        if self.calls >= self._max_calls:
            return f"the backtest's cap of {self._max_calls} calls is reached"
        self.calls += 1
        return None


@dataclass(frozen=True)
class _Snapshot:
    """What one tick left for one volcano, projected, until all footprints are known."""

    t: datetime
    volcano_id: str
    cone_mode: str
    zone: BaseGeometry
    official: BaseGeometry
    zone_top_ft: int
    valid_to: datetime
    floor_ok: bool
    input_leaks: int


def tick_times(case: ReplayCase, step: timedelta) -> list[datetime]:
    times = [case.recorded_from]
    while times[-1] + step <= case.recorded_to:
        times.append(times[-1] + step)
    return times


def input_stamps(situation: Situation) -> list[datetime]:
    """When each input was fetched and issued. A VONA's fetch time is left out: the cases hold
    MAGMA list pages saved weeks after the events, and the poller admits a notice by the time
    it was issued."""
    stamps: list[datetime] = []
    for provenance in situation.provenances():
        if provenance.feed is not FeedId.VONA:
            stamps.append(provenance.fetched_at)
        if provenance.issued_at is not None:
            stamps.append(provenance.issued_at)
    return stamps


def input_leaks(situation: Situation, at: datetime) -> int:
    """Inputs stamped after the clock, with the slack the pipeline itself allows (a live
    recording's first answers can lie seconds after its start)."""
    limit = at + FEED_CLOCK_SLACK
    return sum(stamp > limit for stamp in input_stamps(situation))


def footprints_of(situation: Situation, projection: Projection) -> list[Footprint]:
    """Every polygon the situation's advisories and SIGMETs carry, with issue and valid time."""
    volcano_id = situation.volcano.id
    found = [
        footprint
        for vaa in situation.vaas
        for footprint in _vaa_footprints(vaa, volcano_id, projection)
    ]
    for sigmet in situation.sigmets:
        footprint = _sigmet_footprint(sigmet, volcano_id, projection)
        if footprint is not None:
            found.append(footprint)
    return found


def _vaa_footprints(
    vaa: VaacAdvisory, volcano_id: str, projection: Projection
) -> Iterator[Footprint]:
    steps = [vaa.observation, *vaa.forecasts]
    for step in steps:
        if step is None:
            continue
        layers = [layer for layer in step.layers if layer.polygon is not None]
        shape = union(projection.shape(layer.polygon) for layer in layers if layer.polygon)
        if shape.is_empty:
            continue
        name = "OBS" if step.offset_h == 0 else f"FCST+{step.offset_h}H"
        yield Footprint(
            footprint_id=f"{vaa.provenance.source_id}#{name}",
            volcano_id=volcano_id,
            issued_at=vaa.issued_at,
            valid_at=step.valid_at,
            shape=shape,
            top_ft=max(layer.top_ft for layer in layers),
        )


def _sigmet_footprint(sigmet: Sigmet, volcano_id: str, projection: Projection) -> Footprint | None:
    if sigmet.cancelled or sigmet.polygon is None:
        return None
    return Footprint(
        footprint_id=sigmet.provenance.source_id,
        volcano_id=volcano_id,
        issued_at=sigmet.provenance.issued_at or sigmet.valid_from,
        valid_at=sigmet.valid_from,
        shape=projection.shape(sigmet.polygon),
        top_ft=sigmet.top_ft,
    )


def _snapshot(
    t: datetime, cone: HazardCone, situation: Situation, projection: Projection
) -> _Snapshot:
    layers: list[OfficialLayer] = situation.official_layers
    official = union(projection.shape(layer.polygon) for layer in layers)
    # Unioned in the projected plane so projection noise cannot put the zone under the
    # official area; ``floor_ok`` below judges the cone itself.
    zone = union([projection.shape(cone.geometry) if cone.geometry else Polygon(), official])
    return _Snapshot(
        t=t,
        volcano_id=cone.volcano_id,
        cone_mode=cone.mode.value,
        zone=zone,
        official=official,
        zone_top_ft=cone.top_ft,
        valid_to=cone.valid_to,
        floor_ok=covers_official(cone, layers),
        input_leaks=input_leaks(situation, t),
    )


@contextmanager
def _workdir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="tephra-backtest-") as name:
        yield Path(name)


def _llm_for(arm: Arm, settings: Settings, max_calls: int) -> LlmBackend:
    if arm == "D":
        return get_llm(settings)
    if settings.llm != "gemini":
        raise ValueError("arm G needs TEPHRA_LLM=gemini and GEMINI_API_KEY (cache reads only)")
    return _CappedGemini(settings, max_calls=max_calls)


def _runtime(case: ReplayCase, settings: Settings, llm: LlmBackend, work: Path) -> Runtime:
    policy = load_policy(settings.data_dir, settings.policy_file)
    return Runtime(
        settings=settings,
        store=SqliteStore(work / "backtest.sqlite3", work / "blobs"),
        bus=EventBus(),
        source=ReplaySource(case_path(settings.data_dir, case.case_id), case),
        llm=llm,
        catalogue=load_volcanoes(settings.data_dir),
        airports=load_airports(
            settings.data_dir, min_runway_m=policy.alternates.min_runway_m.value
        ),
        routes=load_routes(settings.data_dir),
        policy=policy,
        mode=RunMode.REPLAY,
        replay_case=case,
        auto_replay=False,
    )


class SyntheticCase(ValueError):
    """A synthetic demo case was offered for scoring: its products are invented, so a score
    against them would say nothing about TEPHRA's zone."""

    def __init__(self, case_id: str) -> None:
        super().__init__(
            f"replay case {case_id} is synthetic demo data; the backtest scores only "
            "recorded or reconstructed cases"
        )
        self.case_id = case_id


async def run_case(
    case_id: str,
    *,
    settings: Settings,
    arm: Arm = "D",
    step: timedelta = DEFAULT_STEP,
    max_calls: int = 0,
    on_tick: Callable[[datetime], None] | None = None,
) -> CaseScore:
    settings = settings.model_copy(update={"recovery_auto": False})  # scoring needs no plans
    if arm == "D":
        settings = settings.model_copy(update={"llm": "stub"})
    case = load_case(settings.data_dir, case_id)
    if case.synthetic:
        raise SyntheticCase(case_id)
    times = tick_times(case, step)
    llm = _llm_for(arm, settings, max_calls)
    snapshots: list[_Snapshot] = []
    footprints: dict[str, Footprint] = {}
    projections: dict[str, Projection] = {}
    volcanoes: dict[str, Volcano] = {}
    vaacs: set[str] = set()
    latest_input: datetime | None = None
    with _workdir() as work, timeutil.use_clock(timeutil.FixedClock(case.recorded_from)) as clock:
        runtime = _runtime(case, settings, llm, work)
        runtime.worker.paced = False  # every tick's AI work runs before it is scored
        try:
            for at in times:
                clock.set(at)  # type: ignore[attr-defined]
                await run_tick(runtime, reason="backtest")
                await runtime.worker.drain()
                for vid, cone in runtime.cones.items():
                    situation = runtime.situations.get(vid)
                    if situation is None:
                        continue
                    volcano = situation.volcano
                    volcanoes[vid] = volcano
                    projection = projections.setdefault(vid, Projection(volcano.lat, volcano.lon))
                    snapshots.append(_snapshot(at, cone, situation, projection))
                    for footprint in footprints_of(situation, projection):
                        footprints.setdefault(footprint.footprint_id, footprint)
                    vaacs.update(vaa.vaac.value for vaa in situation.vaas)
                    stamps = input_stamps(situation)
                    latest_input = max([*stamps, *([latest_input] if latest_input else [])])
                if on_tick is not None:
                    on_tick(at)
            airports = {airport.icao: airport for airport in runtime.airports.all()}
        finally:
            await runtime.aclose()
    return _score_case(
        case,
        arm=arm,
        step=step,
        times=times,
        snapshots=snapshots,
        footprints=list(footprints.values()),
        projections=projections,
        volcanoes=volcanoes,
        airports=airports,
        vaacs=sorted(vaacs),
        latest_input=latest_input,
        models=_model_use(llm),
    )


def _model_use(llm: LlmBackend) -> ModelUse:
    if isinstance(llm, _CappedGemini):
        return ModelUse(backend="gemini", model_id=llm.model_id("main"), calls=llm.calls)
    return ModelUse(backend="stub", model_id="stub", calls=0)


def _score_case(
    case: ReplayCase,
    *,
    arm: Arm,
    step: timedelta,
    times: Sequence[datetime],
    snapshots: Sequence[_Snapshot],
    footprints: Sequence[Footprint],
    projections: dict[str, Projection],
    volcanoes: dict[str, Volcano],
    airports: dict[str, Any],
    vaacs: list[str],
    latest_input: datetime | None,
    models: ModelUse,
) -> CaseScore:
    spots = {
        vid: {
            icao: Point(*projection.point(airport.lat, airport.lon))
            for icao, airport in airports.items()
        }
        for vid, projection in projections.items()
    }
    by_volcano = {vid: [fp for fp in footprints if fp.volcano_id == vid] for vid in volcanoes}
    ticks: list[TickScore] = []
    pair_cover: dict[tuple[str, datetime], dict[str, tuple[float | None, float | None, bool]]] = {}
    for snap in snapshots:
        later = _later(by_volcano[snap.volcano_id], snap)
        truth = union(fp.shape for fp in later)
        ticks.append(
            score_tick(
                t=snap.t,
                volcano_id=snap.volcano_id,
                cone_mode=snap.cone_mode,
                zone=snap.zone,
                official=snap.official,
                truth=truth,
                footprints=later,
                zone_top_ft=snap.zone_top_ft,
                airports=spots[snap.volcano_id],
                floor_ok=snap.floor_ok,
                input_leaks=snap.input_leaks,
            )
        )
        pair_cover[(snap.volcano_id, snap.t)] = {
            fp.footprint_id: (
                coverage(snap.zone, fp.shape),
                coverage(snap.official, fp.shape),
                fp.top_ft is None or snap.zone_top_ft >= fp.top_ft,
            )
            for fp in later
        }
    lead = [summarise_leads(tau, _leads(footprints, times, pair_cover, tau)) for tau in TAUS]
    notes = _notes(times, snapshots, footprints)
    feeds = {record.feed for record in case.records} & set(PRODUCT_FEEDS)
    return CaseScore(
        case_id=case.case_id,
        label=case.label,
        arm=arm,
        region=case.region,
        vaacs=vaacs,
        t_first=times[0],
        t_last=times[-1],
        step_min=int(step.total_seconds() // 60),
        volcano_ids=sorted(volcanoes),
        sources_used=sorted(feed.value for feed in feeds),
        latest_input_ts=latest_input,
        ticks=ticks,
        summary=summarise(ticks),
        lead=lead,
        floor_violations=sum(not tick.floor_ok for tick in ticks),
        input_leaks=sum(tick.input_leaks for tick in ticks),
        models=models,
        notes=notes,
    )


def _later(footprints: Sequence[Footprint], snap: _Snapshot) -> list[Footprint]:
    """Footprints issued after the tick (beyond the feed slack) that its zone claims to reach."""
    return [
        fp
        for fp in footprints
        if fp.issued_at > snap.t + FEED_CLOCK_SLACK and fp.valid_at <= snap.valid_to
    ]


def _leads(
    footprints: Sequence[Footprint],
    times: Sequence[datetime],
    pair_cover: dict[tuple[str, datetime], dict[str, tuple[float | None, float | None, bool]]],
    tau: float,
) -> list[FootprintLead]:
    leads: list[FootprintLead] = []
    for fp in sorted(footprints, key=lambda item: (item.issued_at, item.footprint_id)):
        if fp.valid_at > fp.issued_at + FEED_CLOCK_SLACK:  # a forecast step has no lead of its own
            continue
        zone_ticks: list[tuple[datetime, bool]] = []
        official_ticks: list[tuple[datetime, bool]] = []
        for at in times:
            if at + FEED_CLOCK_SLACK >= fp.issued_at:
                break
            cell = pair_cover.get((fp.volcano_id, at), {}).get(fp.footprint_id)
            cov_z, cov_o, vertical = cell if cell is not None else (None, None, False)
            zone_ticks.append((at, cov_z is not None and cov_z >= tau and vertical))
            official_ticks.append((at, cov_o is not None and cov_o >= tau and vertical))
        if zone_ticks:  # one issued before the first tick was never "later"
            leads.append(footprint_lead(fp, zone_ticks, official_ticks))
    return leads


def _notes(
    times: Sequence[datetime], snapshots: Sequence[_Snapshot], footprints: Sequence[Footprint]
) -> list[str]:
    notes: list[str] = []
    active = {snap.t for snap in snapshots}
    if len(active) < len(times):
        notes.append(f"{len(times) - len(active)} of {len(times)} ticks had no active volcano")
    if not footprints:
        notes.append("no official polygon in the case, so nothing could be scored")
    return notes


async def run_backtest(
    case_ids: Sequence[str],
    *,
    settings: Settings,
    arms: Sequence[Arm] = ("D",),
    step: timedelta = DEFAULT_STEP,
    max_calls: int = 0,
) -> BacktestScorecard:
    cases = [
        await run_case(case_id, settings=settings, arm=arm, step=step, max_calls=max_calls)
        for case_id in case_ids
        for arm in arms
    ]
    overall: dict[str, Any] = {}
    overall_lead: dict[str, list[LeadSummary]] = {}
    for arm in arms:
        scored = [case for case in cases if case.arm == arm]
        overall[arm] = summarise([tick for case in scored for tick in case.ticks])
        overall_lead[arm] = [
            summarise_leads(
                tau,
                [
                    lead
                    for case in scored
                    for summary in case.lead
                    if summary.tau == tau
                    for lead in summary.footprints
                ],
            )
            for tau in TAUS
        ]
    return BacktestScorecard(
        generated_at=timeutil.SystemClock().now().replace(microsecond=0),
        step_min=int(step.total_seconds() // 60),
        cases=cases,
        overall=overall,
        overall_lead=overall_lead,
        floor_violations=sum(case.floor_violations for case in cases),
        input_leaks=sum(case.input_leaks for case in cases),
        caveats=list(CAVEATS),
    )


def write_scorecard(scorecard: BacktestScorecard, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(scorecard.model_dump_json(indent=1) + "\n", encoding="utf-8")


def load_scorecard(path: Path) -> BacktestScorecard:
    return BacktestScorecard.model_validate_json(path.read_bytes())


async def store_scorecard(store: Store, scorecard: BacktestScorecard) -> None:
    await store.put(Collection.BACKTEST, LATEST_DOC, scorecard.model_dump(mode="json"))
