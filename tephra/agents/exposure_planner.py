"""Exposure Planner: one action per exposed flight, from a fixed set, never a reroute.

With Gemini the planner is a Google ADK ``LlmAgent`` (built in ``tephra.agents.adk_app``)
whose function tools read this flight's ``PlannerContext`` from session state and record
the decision through ``submit_plan``. The stub backend, and every fallback, use
``rule_based_decision``. Either way ``validators.validate_decision`` has the last word.

There is no free airway database, so any waypoint would be invented: the actions are
CONTINUE, MONITOR, CHANGE_LEVEL, HOLD (present position) and DIVERT (a screened alternate).
"""

import asyncio
import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal

from tephra.agents.llm import LlmBackend, LlmPart, daily_quota_spent, prompt_hash
from tephra.agents.schemas import parse_json_model
from tephra.agents.validators import (
    allowed_actions,
    band_clears_hazard,
    first_problems,
    validate_decision,
)
from tephra.config import Settings
from tephra.feeds.airports import AirportCatalogue
from tephra.feeds.taf import assess_alternate
from tephra.geo.cone import polygon_iou
from tephra.geo.fuel import divert_line
from tephra.geo.units import destination_point, ft_to_fl, initial_bearing_deg, nm_to_km
from tephra.models import (
    ActionKind,
    Airport,
    AlternateCandidate,
    ExposedFlight,
    FuelLine,
    HazardCone,
    LlmBackendName,
    OperatorPolicy,
    PlannedAction,
    PlannerContext,
    PlannerDecision,
    PlumeMode,
    Taf,
    ToolCallRecord,
    TraceActor,
    TraceEvent,
    TraceSink,
    TraceStage,
    polygon_from_latlon,
)
from tephra.util.hashing import stable_id

if TYPE_CHECKING:
    from google.adk.runners import InMemoryRunner

logger = logging.getLogger(__name__)

PROMPT_PATH: Final[Path] = Path(__file__).resolve().parent / "prompts" / "planner.md"
CONTEXT_STATE_KEY: Final = "tephra_ctx"
DECISION_STATE_KEY: Final = "tephra_decision"
ADK_APP_NAME: Final = "tephra_planner"
ADK_USER_ID: Final = "tephra-dispatch"
"""ADK sessions need a user id; no person is behind it and no name is sent to Gemini."""

MAX_MODEL_TURNS: Final = 10
"""Model calls allowed per planning turn (tool round trips included) before code stops it."""
DAILY_QUOTA_SPENT: Final = "GEMINI DAILY QUOTA SPENT (429): LITE TIER CLOSED FOR THE QUOTA DAY"
_RING_POINTS: Final = 64
"""Vertices of the buffer disc; its edges fall at most 0.03 NM inside the true circle."""
_SUMMARY_CHARS: Final = 240

PlanOutcome = Literal["ACCEPTED", "REPAIRED", "FALLBACK_RULES", "STUB"]


# --- context ----------------------------------------------------------------------------


def build_planner_context(
    flight: ExposedFlight,
    cone: HazardCone,
    *,
    volcano_name: str,
    airports: AirportCatalogue,
    tafs: Mapping[str, Taf],
    at: datetime,
    policy: OperatorPolicy,
) -> PlannerContext:
    nearby = airports.nearest(
        flight.lat, flight.lon, max_nm=policy.alternates.search_radius_nm.value
    )
    alternates = [
        _alternate(flight, cone, airport, distance, tafs.get(airport.icao), at, policy)
        for airport, distance in nearby
    ]
    return PlannerContext(
        flight=flight,
        volcano_name=volcano_name,
        plume_mode=cone.mode,
        confidence=cone.confidence,
        hazard_base_ft=cone.base_ft,
        hazard_top_ft=cone.top_ft,
        vertical_margin_ft=policy.exposure.vertical_margin_ft.value,
        allowed_actions=allowed_actions(cone.mode),
        alternates=alternates,
        hold=flight.hold,
        **planner_limits(policy),
    )


def planner_limits(policy: OperatorPolicy) -> dict[str, int]:
    """The ``PlannerContext`` fields the operator policy's planner block sets."""
    rules = policy.planner
    return {
        "level_search_ft": rules.level_search_ft.value,
        "level_band_fl": rules.level_band_fl.value,
        "max_change_level_fl": rules.max_change_level_fl.value,
        "divert_within_min": rules.divert_within_min.value,
        "hold_within_min": rules.hold_within_min.value,
        "hypothesis_hold_within_min": rules.hypothesis_hold_within_min.value,
    }


def _alternate(
    flight: ExposedFlight,
    cone: HazardCone,
    airport: Airport,
    distance: float,
    taf: Taf | None,
    at: datetime,
    policy: OperatorPolicy,
) -> AlternateCandidate:
    screen = policy.alternates
    extra = policy.fuel.divert_extra_min.value
    divert = divert_line(
        flight.category,
        alternate_icao=airport.icao,
        distance_nm=distance,
        gs_kt=flight.gs_kt,
        extra_minutes=extra,
    )
    eta = at + timedelta(minutes=divert.minutes - extra)
    check = assess_alternate(
        taf,
        eta,
        min_visibility_m=screen.min_visibility_m.value,
        min_ceiling_ft=screen.min_ceiling_ft.value,
        window_min=screen.taf_eta_window_min.value,
    )
    update: dict[str, Any] = {"icao": airport.icao}  # the no-TAF check carries no ICAO
    if _near_cone(cone, airport.lat, airport.lon, screen.terminal_radius_nm.value):
        update |= {"ok": False, "reasons": [*check.reasons, "INSIDE HAZARD CONE"]}
    check = check.model_copy(update=update)
    return AlternateCandidate(
        icao=airport.icao,
        name=airport.name,
        distance_nm=round(distance, 1),
        bearing_deg=round(initial_bearing_deg(flight.lat, flight.lon, airport.lat, airport.lon)),
        check=check,
        divert=divert,
    )


def _near_cone(cone: HazardCone, lat: float, lon: float, radius_nm: float) -> bool:
    """Inside the cone or within ``radius_nm`` of it (the policy's terminal radius).

    The whole buffer disc is overlapped with the cone: a narrow plume can pass between the
    airport and any ring of sample points.
    """
    if cone.geometry is None:
        return False
    radius_km = nm_to_km(radius_nm)
    disc = polygon_from_latlon(
        destination_point(lat, lon, i * 360.0 / _RING_POINTS, radius_km)
        for i in range(_RING_POINTS)
    )
    return polygon_iou(cone.geometry, disc) > 0.0


# --- rules ------------------------------------------------------------------------------


def rule_based_decision(ctx: PlannerContext) -> PlannerDecision:
    flight = ctx.flight
    level_fl = present_fl(flight)
    if ctx.plume_mode is PlumeMode.HYPOTHESIS:
        return _hypothesis_rule(ctx, level_fl)
    hazard = f"HAZARD {band_text(ctx.hazard_base_ft, ctx.hazard_top_ft)}"
    entry = _entry_text(flight)
    if flight.aircraft_band_ft[0] > ctx.hazard_top_ft + ctx.vertical_margin_ft:
        return _rule(
            ActionKind.CONTINUE,
            f"{hazard}. AIRCRAFT LEVEL IS ABOVE THE HAZARD TOP PLUS"
            f" {ctx.vertical_margin_ft} FT MARGIN.",
            [ActionKind.MONITOR],
        )
    band = nearest_clear_band(ctx)
    if band is not None:
        return _rule(
            ActionKind.CHANGE_LEVEL,
            f"{hazard} PLUS {ctx.vertical_margin_ft} FT MARGIN, {entry}."
            f" FL{band[0]:03d}-FL{band[1]:03d} CLEARS IT WITHIN {ctx.level_search_ft} FT OF"
            " PRESENT LEVEL.",
            [ActionKind.HOLD, ActionKind.DIVERT, ActionKind.MONITOR],
            change_level_fl_min=band[0],
            change_level_fl_max=band[1],
        )
    alternate = nearest_ok_alternate(ctx)
    urgent = flight.inside_now or flight.minutes_to_entry <= ctx.divert_within_min
    if urgent and alternate is not None:
        return _rule(
            ActionKind.DIVERT,
            f"{hazard}, {entry}. NO CLEAR LEVEL WITHIN {ctx.level_search_ft} FT."
            f" {alternate} IS THE NEAREST ALTERNATE THAT PASSES THE TAF AND CONE SCREEN.",
            [ActionKind.CHANGE_LEVEL, ActionKind.HOLD],
            alternate_icao=alternate,
        )
    if flight.inside_now:
        # Holding at present position would keep the aircraft in the ash.
        return _rule(
            ActionKind.MONITOR,
            f"{hazard}, {entry}. NO CLEAR LEVEL WITHIN {ctx.level_search_ft} FT AND NO ACCEPTABLE"
            " ALTERNATE; A HOLD HERE IS INSIDE THE HAZARD. DISPATCHER TO ADVISE THE EXIT.",
            [ActionKind.HOLD, ActionKind.CHANGE_LEVEL, ActionKind.DIVERT],
        )
    if flight.minutes_to_entry <= ctx.hold_within_min and level_fl is not None:
        reason = "NO ACCEPTABLE ALTERNATE" if urgent else "ENTRY IS CLOSE"
        return _rule(
            ActionKind.HOLD,
            f"{hazard}, {entry}. NO CLEAR LEVEL WITHIN {ctx.level_search_ft} FT AND {reason};"
            " HOLD AT PRESENT POSITION OUTSIDE THE HAZARD PENDING THE NEXT PRODUCT.",
            [ActionKind.CHANGE_LEVEL, ActionKind.DIVERT, ActionKind.MONITOR],
            hold_fl=level_fl,
        )
    return _rule(
        ActionKind.MONITOR,
        f"{hazard}, {entry}. ENTRY IS NOT IMMINENT; WATCH FOR UPDATED PRODUCTS.",
        [ActionKind.HOLD, ActionKind.DIVERT],
    )


def _hypothesis_rule(ctx: PlannerContext, level_fl: int | None) -> PlannerDecision:
    flight = ctx.flight
    basis = "NO OFFICIAL PRODUCT IS VALID; THE HAZARD IS A TEPHRA HYPOTHESIS"
    # Inside the cone a hold at present position is outside the hazard only above or below it.
    hold_outside = level_fl is not None and (
        not flight.inside_now or band_clears_hazard(level_fl, level_fl, ctx=ctx)
    )
    if flight.minutes_to_entry <= ctx.hypothesis_hold_within_min and hold_outside:
        return _rule(
            ActionKind.HOLD,
            f"{basis}, {_entry_text(flight)}. HOLD AT PRESENT POSITION UNTIL AN OFFICIAL"
            " PRODUCT CONFIRMS OR CLEARS IT.",
            [ActionKind.MONITOR],
            hold_fl=level_fl,
        )
    return _rule(
        ActionKind.MONITOR,
        f"{basis}, {_entry_text(flight)}. ONLY MONITOR OR HOLD MAY BE ADVISED.",
        [ActionKind.HOLD],
    )


def _rule(
    action: ActionKind,
    reasoning: str,
    considered: Sequence[ActionKind],
    **targets: Any,
) -> PlannerDecision:
    return PlannerDecision(
        action=action,
        reasoning=f"NO MODEL: {reasoning}",
        alternatives_considered=list(considered),
        **targets,
    )


def nearest_clear_band(ctx: PlannerContext) -> tuple[int, int] | None:
    """The policy-width band clear of hazard plus margin nearest the present level, if close."""
    altitude = ctx.flight.alt_baro_ft
    if altitude is None:
        return None
    best: tuple[int, int, int] | None = None
    for fl_min in range(0, ctx.max_change_level_fl - ctx.level_band_fl + 1, 10):
        fl_max = fl_min + ctx.level_band_fl
        if not band_clears_hazard(fl_min, fl_max, ctx=ctx):
            continue
        low, high = fl_min * 100, fl_max * 100
        gap = 0 if low <= altitude <= high else min(abs(altitude - low), abs(altitude - high))
        # Ties go to the higher band: ash from a vent rises from the surface.
        if gap <= ctx.level_search_ft and (best is None or (gap, -fl_min) < (best[0], -best[1])):
            best = (gap, fl_min, fl_max)
    return None if best is None else (best[1], best[2])


def nearest_ok_alternate(ctx: PlannerContext) -> str | None:
    candidates = [
        alt for alt in ctx.alternates if alt.check.ok and alt.check.taf_source_id is not None
    ]
    return min(candidates, key=lambda alt: alt.distance_nm).icao if candidates else None


def present_fl(flight: ExposedFlight) -> int | None:
    return ft_to_fl(flight.alt_baro_ft) if flight.alt_baro_ft is not None else None


def band_text(base_ft: int, top_ft: int) -> str:
    base = "SFC" if base_ft <= 0 else f"FL{ft_to_fl(base_ft):03d}"
    return f"{base}/FL{ft_to_fl(top_ft):03d}"


def _entry_text(flight: ExposedFlight) -> str:
    if flight.inside_now:
        return "INSIDE THE HAZARD NOW"
    return f"ENTRY IN {flight.minutes_to_entry} MIN IF TRACK AND LEVEL ARE HELD"


def normalise_decision(decision: PlannerDecision) -> PlannerDecision:
    """Keep only the target fields that belong to the chosen action."""
    action = decision.action
    icao = decision.alternate_icao.strip().upper() if decision.alternate_icao else None
    return decision.model_copy(
        update={
            "change_level_fl_min": (
                decision.change_level_fl_min if action is ActionKind.CHANGE_LEVEL else None
            ),
            "change_level_fl_max": (
                decision.change_level_fl_max if action is ActionKind.CHANGE_LEVEL else None
            ),
            "hold_fl": decision.hold_fl if action is ActionKind.HOLD else None,
            "alternate_icao": icao if action is ActionKind.DIVERT else None,
            "reasoning": decision.reasoning.strip(),
        }
    )


def fuel_for(decision: PlannerDecision, ctx: PlannerContext) -> FuelLine | None:
    if decision.action is ActionKind.HOLD:
        return ctx.hold
    if decision.action is ActionKind.DIVERT:
        return next(
            (alt.divert for alt in ctx.alternates if alt.icao == decision.alternate_icao), None
        )
    return None


# --- tool bodies (wrapped as ADK FunctionTools in tephra.agents.adk_app) ------------------


def context_from_state(value: Any) -> PlannerContext | None:
    """The PlannerContext an ADK session (or an eval case) carries under CONTEXT_STATE_KEY."""
    if value is None:
        return None
    if isinstance(value, PlannerContext):
        return value
    if isinstance(value, str | bytes):
        return PlannerContext.model_validate_json(value)
    return PlannerContext.model_validate(value)


def flight_summary(ctx: PlannerContext) -> dict[str, Any]:
    flight = ctx.flight
    return {
        "proxy_flight": flight.proxy_flight,
        "callsign": flight.callsign,
        "aircraft_type": flight.type_icao,
        "category": flight.category.value,
        "present_fl": present_fl(flight),
        "selected_fl": (
            ft_to_fl(flight.nav_altitude_mcp_ft) if flight.nav_altitude_mcp_ft is not None else None
        ),
        "ground_speed_kt": round(flight.gs_kt) if flight.gs_kt is not None else None,
        "track_deg": round(flight.track_deg) if flight.track_deg is not None else None,
        "inside_hazard_now": flight.inside_now,
        "minutes_to_entry": flight.minutes_to_entry,
        "volcano": ctx.volcano_name,
        "plume_mode": ctx.plume_mode.value,
        "confidence_pct": round(ctx.confidence * 100),
        "hazard_band": band_text(ctx.hazard_base_ft, ctx.hazard_top_ft),
        "vertical_margin_ft": ctx.vertical_margin_ft,
        "allowed_actions": [action.value for action in ctx.allowed_actions],
        "hold_cost": ctx.hold.formula,
    }


def limits_summary(ctx: PlannerContext) -> dict[str, Any]:
    """The operator policy's planning limits, for the planner's ``get_flight`` tool. Kept out
    of ``flight_summary``, which the drafter's facts reuse: they are no part of an advisory."""
    return {
        "max_change_level_fl": ctx.max_change_level_fl,
        "level_band_ft": ctx.level_band_fl * 100,
        "decisive_action_within_min": ctx.divert_within_min,
    }


def alternates_summary(ctx: PlannerContext) -> dict[str, Any]:
    return {
        "alternates": [_alternate_dict(alt) for alt in ctx.alternates],
        "note": "Simplified planning minima from the TAF; alternates in or near the cone fail.",
    }


def alternate_summary(ctx: PlannerContext, icao: str) -> dict[str, Any]:
    code = icao.strip().upper()
    candidate = next((alt for alt in ctx.alternates if alt.icao == code), None)
    if candidate is None:
        listed = [alt.icao for alt in ctx.alternates]
        return {"error": f"{code} IS NOT A LISTED ALTERNATE", "listed": listed}
    return _alternate_dict(candidate)


def _alternate_dict(alt: AlternateCandidate) -> dict[str, Any]:
    return {
        "icao": alt.icao,
        "name": alt.name,
        "distance_nm": round(alt.distance_nm),
        "bearing_deg": round(alt.bearing_deg),
        "acceptable": alt.check.ok,
        "reasons": alt.check.reasons,
        "has_taf": alt.check.taf_source_id is not None,
        "divert_minutes": alt.divert.minutes,
        "divert_fuel_kg": alt.divert.fuel_kg,
        "divert_cost": alt.divert.formula,
    }


def level_band_summary(ctx: PlannerContext, fl_min: int, fl_max: int) -> dict[str, Any]:
    low, high = sorted((fl_min, fl_max))
    clear = band_clears_hazard(low, high, ctx=ctx) and high <= ctx.max_change_level_fl
    altitude = ctx.flight.alt_baro_ft
    change_ft = None
    if altitude is not None:
        nearest_ft = min(max(altitude, low * 100), high * 100)
        change_ft = nearest_ft - altitude
    return {
        "band": f"FL{low:03d}-FL{high:03d}",
        "clear_of_hazard": clear,
        "hazard_with_margin": _margin_text(ctx),
        "change_from_present_ft": change_ft,
        "max_fl": ctx.max_change_level_fl,
    }


def _margin_text(ctx: PlannerContext) -> str:
    return band_text(
        max(0, ctx.hazard_base_ft - ctx.vertical_margin_ft),
        ctx.hazard_top_ft + ctx.vertical_margin_ft,
    )


def cost_summary(ctx: PlannerContext, action: str, alternate_icao: str | None) -> dict[str, Any]:
    try:
        kind = ActionKind(action.strip().upper())
    except ValueError:
        return {"error": f"UNKNOWN ACTION {action}", "actions": [a.value for a in ActionKind]}
    if kind is ActionKind.HOLD:
        return _fuel_dict(ctx.hold)
    if kind is ActionKind.DIVERT:
        if not alternate_icao:
            return {"error": "DIVERT COST NEEDS alternate_icao"}
        code = alternate_icao.strip().upper()
        candidate = next((alt for alt in ctx.alternates if alt.icao == code), None)
        if candidate is None:
            return {"error": f"{code} IS NOT A LISTED ALTERNATE"}
        return _fuel_dict(candidate.divert)
    return {
        "action": kind.value,
        "minutes": 0,
        "fuel_kg": 0,
        "formula": "NO EXTRA HOLD OR DIVERSION FUEL",
    }


def _fuel_dict(line: FuelLine) -> dict[str, Any]:
    return {
        "action": line.action.value,
        "minutes": line.minutes,
        "fuel_kg": line.fuel_kg,
        "formula": line.formula,
    }


def submit_decision(
    ctx: PlannerContext,
    *,
    action: str,
    reasoning: str,
    change_level_fl_min: int | None,
    change_level_fl_max: int | None,
    hold_fl: int | None,
    alternate_icao: str | None,
    alternatives_considered: Sequence[str] | None,
) -> tuple[PlannerDecision | None, list[str]]:
    """Build and check a submitted plan; the problems go straight back to the model."""
    try:
        kind = ActionKind(action.strip().upper())
    except ValueError:
        return None, [f"UNKNOWN ACTION {action}; USE ONE OF {[a.value for a in ActionKind]}"]
    considered: list[ActionKind] = []
    problems: list[str] = []
    for name in alternatives_considered or ():
        try:
            considered.append(ActionKind(name.strip().upper()))
        except ValueError:
            problems.append(f"UNKNOWN ACTION {name} IN alternatives_considered")
    decision = normalise_decision(
        PlannerDecision(
            action=kind,
            change_level_fl_min=change_level_fl_min,
            change_level_fl_max=change_level_fl_max,
            hold_fl=hold_fl,
            alternate_icao=alternate_icao,
            reasoning=reasoning,
            alternatives_considered=considered,
        )
    )
    return decision, [*problems, *validate_decision(decision, ctx)]


# --- planning ---------------------------------------------------------------------------


async def plan_flight(
    ctx: PlannerContext,
    llm: LlmBackend,
    *,
    settings: Settings,
    trace: TraceSink | None = None,
) -> PlannedAction:
    system = PROMPT_PATH.read_text(encoding="utf-8")
    phash = prompt_hash(system, [_context_part(ctx)])
    if llm.name == "stub":
        decision = rule_based_decision(ctx)
        _emit(trace, ctx, "stub", f"NO MODEL: {_decision_line(decision)}")
        return _planned(
            ctx,
            decision,
            backend="stub",
            model_id=llm.model_id("lite"),
            prompt_hash=phash,
            outcome="STUB",
        )
    model_id = llm.model_id("lite")
    run = _AgentRun()
    try:
        await _run_agent(ctx, llm, run, settings=settings, trace=trace)
    except Exception as exc:  # ADK or API failure: agents fall back, they never raise
        logger.warning("planner agent failed for %s: %s", ctx.flight.id, type(exc).__name__)
        run.decision = None
        run.problems = [f"PLANNER AGENT ERROR: {type(exc).__name__}"]
    if run.decision is not None and not run.problems:
        _emit(trace, ctx, "adk", f"PLAN {run.outcome}: {_decision_line(run.decision)}")
        return _planned(
            ctx,
            run.decision,
            backend=llm.name,
            model_id=model_id,
            prompt_hash=phash,
            outcome=run.outcome,
            tool_calls=run.records,
        )
    decision = rule_based_decision(ctx)
    _emit(
        trace,
        ctx,
        "code",
        f"PLANNER FELL BACK TO RULES (NO MODEL): {_decision_line(decision)}",
        level="warn",
        detail={"problems": run.problems},
    )
    return _planned(
        ctx,
        decision,
        backend=llm.name,
        model_id=model_id,
        prompt_hash=phash,
        outcome="FALLBACK_RULES",
        tool_calls=run.records,
        errors=run.problems,
    )


@dataclass
class _AgentRun:
    decision: PlannerDecision | None = None
    outcome: PlanOutcome = "ACCEPTED"
    records: list[ToolCallRecord] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


async def _run_agent(
    ctx: PlannerContext,
    llm: LlmBackend,
    run: _AgentRun,
    *,
    settings: Settings,
    trace: TraceSink | None,
) -> None:
    """Fills ``run`` as it goes, so the tool calls made before a failure stay on record."""
    from google.adk.runners import InMemoryRunner

    from tephra.agents.adk_app import build_planner_agent

    guard = _ModelGuard(llm)
    agent = build_planner_agent(
        settings.model_lite,
        before_model_callback=guard,
        on_model_error_callback=guard.on_model_error,
    )
    runner = InMemoryRunner(agent=agent, app_name=ADK_APP_NAME)
    try:
        session = await runner.session_service.create_session(
            app_name=ADK_APP_NAME,
            user_id=ADK_USER_ID,
            state={CONTEXT_STATE_KEY: ctx.model_dump(mode="json")},
        )
        recorder = _ToolRecorder(ctx, trace, run.records)
        text = await _turn(runner, session.id, _task_text(ctx), recorder, settings)
        run.decision, run.problems = await _read_decision(runner, session.id, text, ctx)
        if run.problems and guard.stop_reason is None:
            _emit(
                trace,
                ctx,
                "code",
                "PLAN REJECTED; ONE REPAIR TURN",
                level="warn",
                detail={"problems": run.problems},
            )
            text = await _turn(runner, session.id, _repair_text(run.problems), recorder, settings)
            run.decision, run.problems = await _read_decision(runner, session.id, text, ctx)
            run.outcome = "REPAIRED"
        if run.decision is None and guard.stop_reason is not None:
            run.problems = [*run.problems, guard.stop_reason]
    finally:
        await runner.close()


class _ModelGuard:
    """The daily budget in front of every ADK model turn.

    As ``before_model_callback`` it takes each turn from the budget and caps turns; as
    ``on_model_error_callback`` (``on_model_error``) it closes the lite tier for the quota day
    when Gemini answers 429 for a per-day quota, which no retry clears. Either one answers in
    the model's place to stop; with no function call in that answer, the run ends.
    """

    def __init__(self, llm: LlmBackend) -> None:
        self._llm = llm
        self.turns = 0
        self.stop_reason: str | None = None

    def __call__(self, callback_context: Any, llm_request: Any) -> Any:
        self.turns += 1
        if self.turns > MAX_MODEL_TURNS:
            self.stop_reason = f"MODEL TURN LIMIT {MAX_MODEL_TURNS} REACHED"
        elif not self._llm.reserve("lite"):
            self.stop_reason = "budget_exhausted"
        return None if self.stop_reason is None else _stop(self.stop_reason)

    def on_model_error(self, callback_context: Any, llm_request: Any, error: Exception) -> Any:
        if not daily_quota_spent(error):
            return None
        self._llm.exhaust("lite")
        self.stop_reason = DAILY_QUOTA_SPENT
        return _stop(self.stop_reason)


def _stop(reason: str) -> Any:
    from google.adk.models import LlmResponse
    from google.genai import types

    stop = types.Part(text=f"STOPPED: {reason}")
    return LlmResponse(content=types.Content(role="model", parts=[stop]))


class _ToolRecorder:
    """Pairs function calls with their responses and streams each one to the trace."""

    def __init__(
        self, ctx: PlannerContext, trace: TraceSink | None, records: list[ToolCallRecord]
    ) -> None:
        self._ctx = ctx
        self._trace = trace
        self._records = records
        self._pending: dict[str, tuple[str, dict[str, Any]]] = {}

    def observe(self, event: Any) -> None:
        for call in event.get_function_calls():
            self._pending[call.id or call.name] = (call.name, dict(call.args or {}))
        for response in event.get_function_responses():
            name, args = self._pending.pop(response.id or response.name, (response.name, {}))
            summary = _summarise(response.response)
            self._records.append(ToolCallRecord(name=name, args=args, result_summary=summary))
            _emit(self._trace, self._ctx, "adk", f"{name}: {summary}", detail={"args": args})


async def _turn(
    runner: "InMemoryRunner",
    session_id: str,
    message: str,
    recorder: _ToolRecorder,
    settings: Settings,
) -> str:
    from google.genai import types

    content = types.Content(role="user", parts=[types.Part(text=message)])
    last_text = ""
    async with asyncio.timeout(settings.llm_timeout_s):
        async for event in runner.run_async(
            user_id=ADK_USER_ID, session_id=session_id, new_message=content
        ):
            recorder.observe(event)
            text = _event_text(event)
            if text:
                last_text = text
    return last_text


def _event_text(event: Any) -> str:
    content = getattr(event, "content", None)
    if content is None or not content.parts:
        return ""
    return "".join(part.text for part in content.parts if part.text and not part.thought).strip()


async def _read_decision(
    runner: "InMemoryRunner", session_id: str, text: str, ctx: PlannerContext
) -> tuple[PlannerDecision | None, list[str]]:
    session = await runner.session_service.get_session(
        app_name=ADK_APP_NAME, user_id=ADK_USER_ID, session_id=session_id
    )
    raw = session.state.get(DECISION_STATE_KEY) if session is not None else None
    try:
        if raw is not None:
            decision = PlannerDecision.model_validate(raw)
        elif text:
            decision = parse_json_model(text, PlannerDecision)
        else:
            return None, ["NO PLAN SUBMITTED: CALL submit_plan ONCE WITH THE CHOSEN ACTION"]
    except ValueError:
        return None, ["NO VALID PLAN: CALL submit_plan ONCE WITH THE CHOSEN ACTION"]
    decision = normalise_decision(decision)
    return decision, validate_decision(decision, ctx)


def _task_text(ctx: PlannerContext) -> str:
    return (
        f"Plan for exposed flight {ctx.flight.proxy_flight} near {ctx.volcano_name}."
        " Read the flight and alternates with the tools, check any level band before"
        " proposing it, then call submit_plan exactly once."
    )


def _repair_text(problems: Sequence[str]) -> str:
    listed = "\n".join(f"- {problem}" for problem in first_problems(problems))
    return (
        "Code rejected the plan:\n"
        f"{listed}\n"
        "Fix these problems and call submit_plan again. Use only the allowed actions,"
        " listed alternates that are acceptable, and levels clear of the hazard band."
    )


# --- shared helpers ---------------------------------------------------------------------


def _planned(
    ctx: PlannerContext,
    decision: PlannerDecision,
    *,
    backend: LlmBackendName,
    model_id: str,
    prompt_hash: str,
    outcome: PlanOutcome,
    tool_calls: Sequence[ToolCallRecord] = (),
    errors: Sequence[str] = (),
) -> PlannedAction:
    flight = ctx.flight
    return PlannedAction(
        id=stable_id("PLAN", flight.id, flight.cone_id),
        flight_id=flight.id,
        cone_id=flight.cone_id,
        decision=decision,
        fuel=fuel_for(decision, ctx),
        tool_calls=list(tool_calls),
        llm_backend=backend,
        model_id=model_id,
        prompt_hash=prompt_hash,
        outcome=outcome,
        validation_errors=list(errors),
    )


def _context_part(ctx: PlannerContext) -> LlmPart:
    return LlmPart(
        kind="text",
        text=ctx.model_dump_json(),
        data=None,
        mime_type=None,
        label=CONTEXT_STATE_KEY,
    )


def _decision_line(decision: PlannerDecision) -> str:
    target = {
        ActionKind.CHANGE_LEVEL: (
            f" FL{decision.change_level_fl_min}-FL{decision.change_level_fl_max}"
        ),
        ActionKind.HOLD: f" FL{decision.hold_fl}",
        ActionKind.DIVERT: f" {decision.alternate_icao}",
    }.get(decision.action, "")
    return f"{decision.action.value}{target}"


def _summarise(response: Any) -> str:
    text = json.dumps(response, default=str, separators=(",", ":"), ensure_ascii=True)
    return text if len(text) <= _SUMMARY_CHARS else text[: _SUMMARY_CHARS - 3] + "..."


def _emit(
    trace: TraceSink | None,
    ctx: PlannerContext,
    actor: TraceActor,
    message: str,
    *,
    level: Literal["info", "warn", "error"] = "info",
    detail: Mapping[str, Any] | None = None,
) -> None:
    if trace is None:
        return
    trace(
        TraceEvent.new(
            TraceStage.PLANNER,
            actor,
            message,
            level=level,
            volcano_id=ctx.flight.volcano_id,
            flight_id=ctx.flight.id,
            detail=detail,
        )
    )
