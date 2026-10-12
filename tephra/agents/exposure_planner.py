"""Exposure Planner: one action per exposed flight, from a fixed set.

With Gemini the planner is a Google ADK ``LlmAgent`` (built in ``tephra.agents.adk_app``)
whose function tools read this flight's ``PlannerContext`` from session state and record
the decision through ``submit_plan``. The stub backend uses ``rule_based_decision``. Either
way ``validators.validate_decision`` has the last word. When the model gives no plan that
passes it, there is no substitute: the plan has no decision and a dispatcher plans by hand.

There is no free airway database, so the model never names a waypoint: the actions are
CONTINUE, MONITOR, CHANGE_LEVEL, HOLD (present position), DIVERT (a screened alternate) and
REROUTE, which only picks one of the lateral routes ``tephra.geo.reroute`` computed.
"""

import asyncio
import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal

from tephra.agents.adk_runtime import ModelGuard, summarise
from tephra.agents.llm import (
    LlmBackend,
    LlmPart,
    gemini_call_fields,
    prompt_hash,
    sum_known,
    usage_tokens,
)
from tephra.agents.schemas import parse_json_model
from tephra.agents.validators import (
    allowed_actions,
    band_clears_hazard,
    first_problems,
    reroute_of,
    validate_decision,
)
from tephra.config import Settings
from tephra.feeds.airports import AirportCatalogue
from tephra.feeds.routes import RouteTable
from tephra.feeds.taf import assess_alternate
from tephra.geo.cone import polygon_iou
from tephra.geo.fuel import divert_line
from tephra.geo.reroute import plan_reroutes
from tephra.geo.units import destination_point, ft_to_fl, initial_bearing_deg, nm_to_km
from tephra.models import (
    ActionKind,
    Airport,
    AlternateCandidate,
    ExposedFlight,
    FlightRoute,
    FuelLine,
    HazardCone,
    LlmBackendName,
    OperatorPolicy,
    PlannedAction,
    PlannerContext,
    PlannerDecision,
    PlumeMode,
    RerouteOption,
    RerouteStatus,
    Situation,
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
_RING_POINTS: Final = 64
"""Vertices of the buffer disc; its edges fall at most 0.03 NM inside the true circle."""

PlanOutcome = Literal["ACCEPTED", "REPAIRED", "MODEL_FAILED", "STUB"]


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
    routes: RouteTable | None = None,
    situation: Situation | None = None,
) -> PlannerContext:
    """``routes`` and ``situation`` (its winds time the reroutes) are optional: without
    routes no destination is known, and without winds a reroute is timed in still air."""
    nearby = airports.nearest(
        flight.lat, flight.lon, max_nm=policy.alternates.search_radius_nm.value
    )
    alternates = [
        _alternate(flight, cone, airport, distance, tafs.get(airport.icao), at, policy)
        for airport, distance in nearby
    ]
    route = routes.lookup(flight, airports, policy) if routes is not None else None
    reroutes = _reroutes(flight, cone, situation, route, routes, airports, policy)
    allowed = allowed_actions(cone.mode)
    if cheapest_reroute(reroutes) is None:
        allowed = [action for action in allowed if action is not ActionKind.REROUTE]
    return PlannerContext(
        flight=flight,
        volcano_name=volcano_name,
        plume_mode=cone.mode,
        confidence=cone.confidence,
        hazard_base_ft=cone.base_ft,
        hazard_top_ft=cone.top_ft,
        vertical_margin_ft=policy.exposure.vertical_margin_ft.value,
        allowed_actions=allowed,
        alternates=alternates,
        hold=flight.hold,
        route=route,
        reroutes=reroutes,
        **planner_limits(policy),
    )


def _reroutes(
    flight: ExposedFlight,
    cone: HazardCone,
    situation: Situation | None,
    route: FlightRoute | None,
    routes: RouteTable | None,
    airports: AirportCatalogue,
    policy: OperatorPolicy,
) -> list[RerouteOption]:
    """Lateral options for the flight; none in HYPOTHESIS mode, which allows no route."""
    if cone.mode is PlumeMode.HYPOTHESIS:
        return []
    position = None
    if route is not None and routes is not None:
        position = routes.position(route.dest_icao, airports)
    return plan_reroutes(flight, cone, situation, route, policy, dest_position=position)


def cheapest_reroute(reroutes: Sequence[RerouteOption]) -> RerouteOption | None:
    """The OK option with the fewest extra minutes."""
    ok = [option for option in reroutes if option.status is RerouteStatus.OK]
    return min(ok, key=lambda option: (option.extra_min or 0.0, option.id), default=None)


def planner_limits(policy: OperatorPolicy) -> dict[str, int]:
    """The ``PlannerContext`` fields the operator policy's planner block sets."""
    rules = policy.planner
    return {
        "level_search_ft": rules.level_search_ft.value,
        "level_band_fl": rules.level_band_fl.value,
        "max_change_level_fl": rules.max_change_level_fl.value,
        "divert_within_min": rules.divert_within_min.value,
        "hold_within_min": rules.hold_within_min.value,
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
    urgent = flight.inside_now or flight.minutes_to_entry <= ctx.divert_within_min
    reroute = cheapest_reroute(ctx.reroutes)
    if reroute is not None and not urgent:
        return _rule(
            ActionKind.REROUTE,
            f"{hazard}, {entry}. NO CLEAR LEVEL WITHIN {ctx.level_search_ft} FT. THE LATERAL"
            f" ROUTE ({_side_text(reroute)}) ADDS {_minutes_text(reroute)}.",
            [ActionKind.HOLD, ActionKind.DIVERT, ActionKind.MONITOR],
            reroute_id=reroute.id,
        )
    alternate = nearest_ok_alternate(ctx)
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
    if flight.minutes_to_entry <= ctx.hold_within_min and hold_outside:
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


def _side_text(option: RerouteOption) -> str:
    return f"{option.side} SIDE" if option.side else "DIRECT"


def _minutes_text(option: RerouteOption) -> str:
    return f"{option.fuel.minutes} MIN" if option.fuel is not None else "TIME"


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
            "reroute_id": decision.reroute_id if action is ActionKind.REROUTE else None,
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
    if decision.action is ActionKind.REROUTE:
        option = reroute_of(decision, ctx)
        return option.fuel if option is not None else None
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
        "level_search_ft": ctx.level_search_ft,
        "decisive_action_within_min": ctx.divert_within_min,
        "hold_within_min": ctx.hold_within_min,
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


def reroutes_summary(ctx: PlannerContext) -> dict[str, Any]:
    """The lateral routes code computed: the usable ones in full, the rest with their reason."""
    usable = [_reroute_dict(o) for o in ctx.reroutes if o.status is RerouteStatus.OK]
    return {
        "reroutes": usable,
        "not_available": [
            {"kind": o.kind.value, "status": o.status.value, "reason": o.note}
            for o in ctx.reroutes
            if o.status is not RerouteStatus.OK
        ],
        "published_route": (
            {"origin": ctx.route.origin_icao, "destination": ctx.route.dest_icao}
            if ctx.route is not None
            else None
        ),
        "note": "Routes are free-route direct legs between computed turn points and need ATC"
        " approval; extra minutes and fuel are against the present track or the direct route.",
    }


def _reroute_dict(option: RerouteOption) -> dict[str, Any]:
    fuel = option.fuel
    return {
        "reroute_id": option.id,
        "kind": option.kind.value,
        "side": option.side,
        "turn_points": len(option.waypoints),
        "extra_nm": option.extra_nm,
        "extra_minutes": option.extra_min,
        "extra_fuel_kg": fuel.fuel_kg if fuel is not None else None,
        "cost": fuel.formula if fuel is not None else None,
        "route": option.route_string,
        "buffer_nm": option.buffer_nm,
        "wind": option.wind_note,
    }


def _margin_text(ctx: PlannerContext) -> str:
    return band_text(
        max(0, ctx.hazard_base_ft - ctx.vertical_margin_ft),
        ctx.hazard_top_ft + ctx.vertical_margin_ft,
    )


def cost_summary(
    ctx: PlannerContext, action: str, alternate_icao: str | None, reroute_id: str | None = None
) -> dict[str, Any]:
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
    if kind is ActionKind.REROUTE:
        option = next((o for o in ctx.reroutes if o.id == reroute_id), None)
        if option is None or option.fuel is None:
            return {"error": "REROUTE COST NEEDS reroute_id OF A LISTED OPTION"}
        return _fuel_dict(option.fuel)
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
    reroute_id: str | None = None,
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
            reroute_id=reroute_id.strip() if reroute_id else None,
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
    phash = planner_prompt_hash(ctx)
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
    except Exception as exc:  # ADK or API failure: no plan, agents never raise
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
            input_tokens=sum_known(run.input_tokens),
            output_tokens=sum_known(run.output_tokens),
        )
    reasons = "; ".join(first_problems(run.problems, 3)) or "NO PLAN"
    _emit(
        trace,
        ctx,
        "code",
        f"PLANNER AI UNAVAILABLE ({reasons}): NO PLAN, A DISPATCHER MUST PLAN THIS FLIGHT",
        level="error",
        detail={"problems": run.problems},
    )
    return _planned(
        ctx,
        None,
        backend=llm.name,
        model_id=model_id,
        prompt_hash=phash,
        outcome="MODEL_FAILED",
        tool_calls=run.records,
        errors=run.problems,
        input_tokens=sum_known(run.input_tokens),
        output_tokens=sum_known(run.output_tokens),
    )


def planner_prompt_hash(ctx: PlannerContext) -> str:
    """The hash of the planner's question for ``ctx``: its instructions and the flight's
    context. A REPLAY loop reuses a recorded plan only for exactly this question."""
    return prompt_hash(PROMPT_PATH.read_text(encoding="utf-8"), [_context_part(ctx)])


def plan_from_record(
    ctx: PlannerContext,
    recorded: PlannedAction,
    *,
    label: str,
    trace: TraceSink | None = None,
) -> PlannedAction | None:
    """A REPLAY loop's plan from the first pass's answer to the same question (the same
    planner instructions and flight context, :func:`planner_prompt_hash`): the same model's
    decision, checked again against the flight now. None when it was an answer to another
    question or no longer passes the checks (the caller then asks the model)."""
    if recorded.decision is None or recorded.prompt_hash != planner_prompt_hash(ctx):
        return None
    decision = normalise_decision(recorded.decision)
    problems = validate_decision(decision, ctx)
    if problems:
        _emit(
            trace,
            ctx,
            "code",
            "Recorded plan from the replay's first pass no longer fits; asking the model",
            level="warn",
            detail={"problems": problems},
        )
        return None
    _emit(trace, ctx, "adk", f"PLAN {_decision_line(decision)} ({label})")
    planned = _planned(
        ctx,
        decision,
        backend=recorded.llm_backend,
        model_id=recorded.model_id,
        prompt_hash=recorded.prompt_hash,
        outcome=recorded.outcome,
        tool_calls=recorded.tool_calls,
    )
    return planned.model_copy(update={"recorded_answer": label})


@dataclass
class _AgentRun:
    decision: PlannerDecision | None = None
    outcome: PlanOutcome = "ACCEPTED"
    records: list[ToolCallRecord] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    input_tokens: list[int | None] = field(default_factory=list)
    output_tokens: list[int | None] = field(default_factory=list)


class _TurnMeter:
    """Logs each ADK model turn as a ``gemini_call`` and keeps its token counts for the plan.

    It wraps the budget guard: a turn the guard stops never reaches the model and is not
    logged here. ADK 2.11 calls ``after_model`` with ``(callback_context, llm_response)``
    after every model response, including an answer ``on_model_error`` put in its place.
    """

    def __init__(self, guard: ModelGuard, run: _AgentRun, model_id: str) -> None:
        self._guard = guard
        self._run = run
        self._model_id = model_id
        self._started: float | None = None
        self._error_answered = False

    async def before_model(self, callback_context: Any, llm_request: Any) -> Any:
        stop = await self._guard(callback_context, llm_request)
        if stop is None:
            self._started = time.monotonic()
        return stop

    async def on_model_error(
        self, callback_context: Any, llm_request: Any, error: Exception
    ) -> Any:
        self._log("error", None, None)
        answer = await self._guard.on_model_error(callback_context, llm_request, error)
        self._error_answered = answer is not None
        return answer

    def after_model(self, callback_context: Any, llm_response: Any) -> None:
        if self._error_answered:
            self._error_answered = False
            return None
        if getattr(llm_response, "partial", False):
            return None
        input_tokens, output_tokens = usage_tokens(getattr(llm_response, "usage_metadata", None))
        self._run.input_tokens.append(input_tokens)
        self._run.output_tokens.append(output_tokens)
        failed = getattr(llm_response, "error_code", None) is not None
        self._log("error" if failed else "ok", input_tokens, output_tokens)
        return None

    def _log(self, outcome: str, input_tokens: int | None, output_tokens: int | None) -> None:
        started, self._started = self._started, None
        latency_ms = round((time.monotonic() - started) * 1000) if started is not None else 0
        logger.info(
            "llm backend=adk tier=lite model=%s outcome=%s latency_ms=%d "
            "input_tokens=%s output_tokens=%s",
            self._model_id,
            outcome,
            latency_ms,
            input_tokens,
            output_tokens,
            extra={
                "json_fields": gemini_call_fields(
                    tier="lite",
                    model=self._model_id,
                    outcome=outcome,
                    latency_ms=latency_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    actor="adk",
                )
            },
        )


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

    guard = ModelGuard(llm, max_turns=MAX_MODEL_TURNS)
    meter = _TurnMeter(guard, run, settings.model_lite)
    agent = build_planner_agent(
        settings.model_lite,
        before_model_callback=meter.before_model,
        after_model_callback=meter.after_model,
        on_model_error_callback=meter.on_model_error,
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
            summary = summarise(response.response)
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
        " Read the flight, alternates and reroutes with the tools, check any level band before"
        " proposing it, then call submit_plan exactly once."
    )


def _repair_text(problems: Sequence[str]) -> str:
    listed = "\n".join(f"- {problem}" for problem in first_problems(problems))
    return (
        "Code rejected the plan:\n"
        f"{listed}\n"
        "Fix these problems and call submit_plan again. Use only the allowed actions,"
        " listed alternates that are acceptable, listed reroutes that are available, and levels"
        " clear of the hazard band."
    )


# --- shared helpers ---------------------------------------------------------------------


def _planned(
    ctx: PlannerContext,
    decision: PlannerDecision | None,
    *,
    backend: LlmBackendName,
    model_id: str,
    prompt_hash: str,
    outcome: PlanOutcome,
    tool_calls: Sequence[ToolCallRecord] = (),
    errors: Sequence[str] = (),
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> PlannedAction:
    flight = ctx.flight
    return PlannedAction(
        id=stable_id("PLAN", flight.id, flight.cone_id),
        flight_id=flight.id,
        cone_id=flight.cone_id,
        decision=decision,
        fuel=fuel_for(decision, ctx) if decision is not None else None,
        tool_calls=list(tool_calls),
        llm_backend=backend,
        model_id=model_id,
        prompt_hash=prompt_hash,
        outcome=outcome,
        validation_errors=list(errors),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
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
        ActionKind.REROUTE: f" {decision.reroute_id}",
    }.get(decision.action, "")
    return f"{decision.action.value}{target}"


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
