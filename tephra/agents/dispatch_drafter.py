"""Dispatch Drafter: the advisory body and cost note for one planned action.

Gemini (structured output, Flash-Lite) writes only ``body`` and ``cost_note``. Code renders
the header: the flight, the UTC times and every source with its timestamps and short
hash, so the model never writes a time, an id or a hash. ``validators.validate_draft``
checks the text; after one repair a code template takes over and the advisory carries a
``NEEDS_HUMAN`` note listing what the model got wrong.
"""

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Final, Literal
from uuid import uuid4

from tephra.agents.exposure_planner import band_text, flight_summary
from tephra.agents.llm import LlmBackend, LlmCall, LlmPart
from tephra.agents.validators import (
    ACTION_WORDS,
    COST_NOTE_MAX_CHARS,
    first_problems,
    validate_draft,
)
from tephra.config import AIRLINE_NAME, Settings
from tephra.models import (
    ActionKind,
    Advisory,
    AdvisoryStatus,
    DraftText,
    ExposedFlight,
    FeedId,
    HazardCone,
    LlmBackendName,
    OperatorPolicy,
    PlannedAction,
    PlannerContext,
    PlannerDecision,
    PlumeAssessment,
    PlumeMode,
    RunMode,
    Situation,
    SourceRef,
    TraceActor,
    TraceEvent,
    TraceSink,
    TraceStage,
    WindProfile,
)
from tephra.util import timeutil
from tephra.util.hashing import stable_id

PROMPT_PATH: Final[Path] = Path(__file__).resolve().parent / "prompts" / "drafter.md"
NEEDS_HUMAN: Final = "NEEDS_HUMAN"
REPAIR_ECHO_CHARS: Final = 2000
"""How much of an unreadable answer the repair prompt quotes back."""
HEADER_TITLE: Final = (
    f"TEPHRA COMPANY ADVISORY - {AIRLINE_NAME.upper()} (FICTIONAL) - NOT FOR OPERATIONAL USE"
)


# --- header (code only) -----------------------------------------------------------------


def render_header(
    *,
    ctx: PlannerContext,
    plan: PlannedAction,
    cone: HazardCone,
    sources: Sequence[SourceRef],
    at: datetime,
) -> str:
    flight = ctx.flight
    cone_line = f"CONE {cone.mode.value} {round(cone.confidence * 100)}%"
    if cone.llm_backend == "stub":
        cone_line += " NO MODEL"
    lines = [
        HEADER_TITLE,
        f"{flight.proxy_flight} (ADS-B {flight.callsign or 'NO CALLSIGN'} {flight.hex})",
        f"VOLCANO {ctx.volcano_name}",
        f"ACTION {_action_text(plan.decision)}",
        "INSIDE NOW" if flight.inside_now else f"ENTRY {flight.minutes_to_entry} MIN",
        cone_line,
        f"DRAFTED {timeutil.hhmmz(at)}",
    ]
    source_lines = [_source_line(source) for source in _binding_first(sources)]
    return "\n".join([*(_ascii_upper(line) for line in lines), *source_lines])


def _action_text(decision: PlannerDecision) -> str:
    match decision.action:
        case ActionKind.CHANGE_LEVEL:
            return (
                f"CHANGE LEVEL FL{decision.change_level_fl_min:03d}"
                f"-FL{decision.change_level_fl_max:03d}"
            )
        case ActionKind.HOLD:
            return f"HOLD FL{decision.hold_fl:03d}"
        case ActionKind.DIVERT:
            return f"DIVERT {decision.alternate_icao}"
        case _:
            return decision.action.value


def _source_line(source: SourceRef) -> str:
    """Upper case except the short hash, which stays as ``sha256_short`` prints it."""
    issued = timeutil.ddhhmmz(source.issued_at) if source.issued_at is not None else "N/A"
    line = _ascii_upper(
        f"SRC {source.feed.value} {source.source_id} ISSUED {issued}"
        f" FETCHED {timeutil.ddhhmmz(source.fetched_at)}"
    )
    line = f"{line} #{source.sha256_short}"
    return f"{line} STALE" if source.stale else line


def _binding_first(sources: Sequence[SourceRef]) -> list[SourceRef]:
    """SIGMETs are the binding product, so they lead; the rest keep their order."""
    return sorted(sources, key=lambda source: source.feed is not FeedId.SIGMET)


def select_sources(situation: Situation, flight: ExposedFlight) -> list[SourceRef]:
    # The flight's ADS-B snapshot provenance is not part of a Situation; the header's
    # "(ADS-B callsign hex)" line names the target instead of citing a hash TEPHRA lacks here.
    at = situation.as_of
    valid = [sigmet for sigmet in situation.sigmets if sigmet.is_valid(at)]
    records: list[Any] = sorted(valid, key=lambda sigmet: sigmet.valid_from, reverse=True)
    if situation.vonas:
        records.append(max(situation.vonas, key=lambda vona: vona.issued_at))
    if situation.vaas:
        records.append(max(situation.vaas, key=lambda vaa: vaa.issued_at))
    wind = _wind_used(situation.winds, flight.observed_at)
    if wind is not None:
        records.append(wind)
    return [SourceRef.from_provenance(record.provenance) for record in records]


def _wind_used(profiles: Sequence[WindProfile], at: datetime) -> WindProfile | None:
    if not profiles:
        return None
    return min(profiles, key=lambda profile: abs((profile.valid_at - at).total_seconds()))


# --- template (stub and last resort) ----------------------------------------------------


def stub_draft(ctx: PlannerContext, plan: PlannedAction) -> DraftText:
    flight = ctx.flight
    hazard = band_text(ctx.hazard_base_ft, ctx.hazard_top_ft)
    lines = [f"{flight.proxy_flight} {_ascii_upper(ctx.volcano_name)} VA HAZARD {hazard}."]
    if ctx.plume_mode is PlumeMode.HYPOTHESIS:
        lines.append("TEPHRA ESTIMATE, NO VALID OFFICIAL PRODUCT.")
    if flight.inside_now:
        lines.append("INSIDE HAZARD AREA NOW.")
    else:
        lines.append(f"ENTRY {flight.minutes_to_entry} MIN IF TRACK AND LEVEL HELD.")
    lines.append(_instruction_line(ctx, plan))
    lines.append("REPORT ANY VOLCANIC ACTIVITY (VAR).")
    return DraftText(body=" ".join(lines), cost_note=_template_cost_note(plan))


def _instruction_line(ctx: PlannerContext, plan: PlannedAction) -> str:
    decision = plan.decision
    match decision.action:
        case ActionKind.CHANGE_LEVEL:
            return _level_line(ctx, decision)
        case ActionKind.HOLD:
            return f"HOLD PRESENT POSITION FL{decision.hold_fl:03d} OUTSIDE HAZARD, ATC PERMITTING."
        case ActionKind.DIVERT:
            distance = plan.fuel.distance_nm if plan.fuel is not None else None
            via = f" {round(distance)} NM" if distance is not None else ""
            return f"DIVERT {decision.alternate_icao}{via}, ATC PERMITTING."
        case ActionKind.CONTINUE:
            return "CONTINUE, PRESENT LEVEL IS ABOVE HAZARD WITH MARGIN."
        case ActionKind.MONITOR if ctx.flight.inside_now and (
            ctx.plume_mode is not PlumeMode.HYPOTHESIS
        ):
            return "MONITOR AND COORDINATE EXIT WITH ATC. DISPATCH TO ADVISE."
        case ActionKind.MONITOR:
            return "MONITOR, NO CHANGE NOW. DISPATCH UPDATES TO FOLLOW."


def _level_line(ctx: PlannerContext, decision: PlannerDecision) -> str:
    low, high = decision.change_level_fl_min or 0, decision.change_level_fl_max or 0
    altitude = ctx.flight.alt_baro_ft or 0
    if altitude < low * 100:
        return f"CLIMB TO FL{low:03d}-FL{high:03d} TO CLEAR HAZARD, ATC PERMITTING."
    if altitude > high * 100:
        return f"DESCEND TO FL{low:03d}-FL{high:03d} TO CLEAR HAZARD, ATC PERMITTING."
    # Already in the band: the selected level would take it into the hazard, so stop there.
    if low * 100 > ctx.hazard_top_ft:
        return f"DO NOT DESCEND BELOW FL{low:03d}, STAY CLEAR OF HAZARD, ATC PERMITTING."
    return f"DO NOT CLIMB ABOVE FL{high:03d}, STAY CLEAR OF HAZARD, ATC PERMITTING."


def _template_cost_note(plan: PlannedAction) -> str:
    fuel = plan.fuel
    if fuel is None:
        if plan.decision.action is ActionKind.CHANGE_LEVEL:
            return "NO EXTRA HOLD OR DIVERSION FUEL; LEVEL CHANGE COST NOT ESTIMATED."
        return "NO EXTRA HOLD OR DIVERSION FUEL."
    if len(fuel.formula) <= COST_NOTE_MAX_CHARS:
        return fuel.formula
    return f"{fuel.action.value} {fuel.minutes} MIN {fuel.fuel_kg} KG BY TEPHRA FORMULA"


# --- drafting ---------------------------------------------------------------------------


async def draft_advisory(
    *,
    situation: Situation,
    assessment: PlumeAssessment,
    cone: HazardCone,
    ctx: PlannerContext,
    plan: PlannedAction,
    llm: LlmBackend,
    settings: Settings,
    policy: OperatorPolicy,
    trace: TraceSink | None = None,
) -> Advisory:
    """``policy`` is stamped on the advisory (id and version) so every decision on it records
    the operator policy it was drafted under."""
    system = PROMPT_PATH.read_text(encoding="utf-8")
    parts = [_text_part(json.dumps(_facts(ctx, plan), indent=1), "facts")]
    draft, call = await _ask(llm, system, parts, ctx, plan)
    drafter_prompt_hash = call.prompt_hash
    problems = _problems(draft, call, ctx, plan)
    # The model answered (even unreadably): one repair. No answer at all (budget, API
    # error) goes straight to the template.
    answered = draft is not None or bool(call.raw_text)
    if problems and answered and llm.name != "stub":
        _emit(
            trace,
            ctx,
            "code",
            "DRAFT REJECTED; ONE REPAIR CALL",
            level="warn",
            detail={"problems": problems},
        )
        repair = _text_part(_repair_text(draft, call, problems), "repair")
        draft, call = await _ask(llm, system, [*parts, repair], ctx, plan)
        problems = _problems(draft, call, ctx, plan)

    backend: LlmBackendName = llm.name
    model_id = call.model_id
    notes = _planner_notes(plan)
    if draft is None or problems:
        if llm.name != "stub":
            notes.append(_fallback_note(draft, call, problems))
            backend, model_id = "stub", "stub"
        draft = stub_draft(ctx, plan)
        leftover = validate_draft(draft, ctx=ctx, plan=plan)
        if leftover:
            notes.append(f"{NEEDS_HUMAN}: TEMPLATE CHECKS: {'; '.join(first_problems(leftover))}")
    _emit(
        trace,
        ctx,
        _actor(backend),
        _draft_line(plan, backend, notes),
        level="warn" if notes else "info",
    )

    created = timeutil.now()
    sources = select_sources(situation, ctx.flight)
    return _advisory(
        situation=situation,
        assessment=assessment,
        cone=cone,
        ctx=ctx,
        plan=plan,
        policy=policy,
        draft=draft,
        sources=sources,
        header=render_header(ctx=ctx, plan=plan, cone=cone, sources=sources, at=created),
        created=created,
        backend=backend,
        model_id=model_id,
        prompt_hashes={
            "plume_reader": assessment.prompt_hash,
            "planner": plan.prompt_hash,
            "drafter": drafter_prompt_hash,
        },
        notes=notes,
    )


async def _ask(
    llm: LlmBackend,
    system: str,
    parts: Sequence[LlmPart],
    ctx: PlannerContext,
    plan: PlannedAction,
) -> tuple[DraftText | None, LlmCall]:
    return await llm.structured(
        tier="lite",
        system=system,
        parts=parts,
        schema=DraftText,
        stub=lambda: stub_draft(ctx, plan),
    )


def _problems(
    draft: DraftText | None, call: LlmCall, ctx: PlannerContext, plan: PlannedAction
) -> list[str]:
    if draft is None:
        return [f"NO DRAFT RETURNED ({call.error or 'unknown error'})"]
    return validate_draft(draft, ctx=ctx, plan=plan)


def _fallback_note(draft: DraftText | None, call: LlmCall, problems: Sequence[str]) -> str:
    if draft is None:
        return f"DRAFTER MODEL UNAVAILABLE ({call.error or 'unknown error'}); TEMPLATE USED"
    return (
        f"{NEEDS_HUMAN}: MODEL DRAFT FAILED CHECKS AFTER REPAIR; TEMPLATE USED:"
        f" {'; '.join(first_problems(problems))}"
    )


def _planner_notes(plan: PlannedAction) -> list[str]:
    if plan.outcome != "FALLBACK_RULES":
        return []
    reasons = "; ".join(first_problems(plan.validation_errors, 3)) or "NO PLAN"
    return [f"PLANNER FELL BACK TO RULES: {reasons}"]


def _advisory(
    *,
    situation: Situation,
    assessment: PlumeAssessment,
    cone: HazardCone,
    ctx: PlannerContext,
    plan: PlannedAction,
    policy: OperatorPolicy,
    draft: DraftText,
    sources: list[SourceRef],
    header: str,
    created: datetime,
    backend: LlmBackendName,
    model_id: str,
    prompt_hashes: dict[str, str],
    notes: list[str],
) -> Advisory:
    flight = ctx.flight
    decision = plan.decision
    volcano_id = situation.volcano.id
    return Advisory(
        id="adv_" + uuid4().hex[:12],
        version=1,
        status=AdvisoryStatus.DRAFT,
        created_at=created,
        updated_at=created,
        replay=situation.mode is RunMode.REPLAY,
        volcano_id=volcano_id,
        volcano_name=ctx.volcano_name,
        flight_id=flight.id,
        proxy_flight=flight.proxy_flight,
        callsign=flight.callsign,
        hex=flight.hex,
        type_icao=flight.type_icao,
        action=decision.action,
        change_level_fl_min=decision.change_level_fl_min,
        change_level_fl_max=decision.change_level_fl_max,
        hold_fl=decision.hold_fl,
        alternate_icao=decision.alternate_icao,
        minutes_to_entry=flight.minutes_to_entry,
        inside_now=flight.inside_now,
        fuel=plan.fuel,
        fuel_line=plan.fuel.formula if plan.fuel is not None else "",
        plume_mode=cone.mode,
        confidence=cone.confidence,
        cone_id=cone.id,
        assessment_id=assessment.id,
        plan_id=plan.id,
        policy_id=policy.policy_id,
        policy_version=policy.version,
        header=header,
        body=draft.body.strip(),
        cost_note=draft.cost_note.strip(),
        sources=sources,
        input_hash=situation.input_hash,
        llm_backend=backend,
        model_id=model_id,
        prompt_hashes=prompt_hashes,
        validation_notes=notes,
        dedupe_key=stable_id(
            "DD",
            flight.hex,
            volcano_id,
            decision.action,
            decision.change_level_fl_min,
            decision.hold_fl,
            decision.alternate_icao,
        ),
    )


# --- model input ------------------------------------------------------------------------


def _facts(ctx: PlannerContext, plan: PlannedAction) -> dict[str, Any]:
    """Everything the drafter may say, with no clock times, ids or hashes in it."""
    decision = plan.decision
    alternate = next((alt for alt in ctx.alternates if alt.icao == decision.alternate_icao), None)
    return {
        "airline": f"{AIRLINE_NAME} (fictional)",
        "flight": flight_summary(ctx),
        "hazard": {
            "volcano": ctx.volcano_name,
            "mode": ctx.plume_mode.value,
            "official_product_valid": ctx.plume_mode is not PlumeMode.HYPOTHESIS,
            "band": band_text(ctx.hazard_base_ft, ctx.hazard_top_ft),
            "vertical_margin_ft": ctx.vertical_margin_ft,
        },
        "action": {
            "kind": decision.action.value,
            "say_one_of": list(ACTION_WORDS[decision.action]),
            "change_level_band": (
                _action_text(decision).removeprefix("CHANGE LEVEL ")
                if decision.action is ActionKind.CHANGE_LEVEL
                else None
            ),
            "hold_fl": decision.hold_fl,
            "alternate": (
                {
                    "icao": alternate.icao,
                    "name": alternate.name,
                    "distance_nm": round(alternate.distance_nm),
                    "screen": alternate.check.reasons,
                }
                if alternate is not None
                else None
            ),
            "planner_reasoning": decision.reasoning,
        },
        "cost": _cost_facts(plan),
        "listed_icao_codes": [alt.icao for alt in ctx.alternates],
    }


def _cost_facts(plan: PlannedAction) -> dict[str, Any] | None:
    fuel = plan.fuel
    if fuel is None:
        return None
    return {"formula": fuel.formula, "minutes": fuel.minutes, "fuel_kg": fuel.fuel_kg}


def _repair_text(draft: DraftText | None, call: LlmCall, problems: Sequence[str]) -> str:
    listed = "\n".join(f"- {problem}" for problem in first_problems(problems))
    if draft is not None:
        previous = json.dumps(draft.model_dump(mode="json"), indent=1)
    else:
        previous = (call.raw_text or "")[:REPAIR_ECHO_CHARS]
    return (
        "Code checks rejected your draft:\n"
        f"{listed}\n"
        f"Your draft was:\n{previous}\n"
        "Write body and cost_note again, fixing every problem and keeping every other rule."
    )


def _text_part(text: str, label: str) -> LlmPart:
    return LlmPart(kind="text", text=text, data=None, mime_type=None, label=label)


# --- small helpers ----------------------------------------------------------------------


def _ascii_upper(text: str) -> str:
    return text.upper().encode("ascii", "ignore").decode("ascii")


def _actor(backend: LlmBackendName) -> TraceActor:
    return "gemini" if backend == "gemini" else "stub"


def _draft_line(plan: PlannedAction, backend: LlmBackendName, notes: Sequence[str]) -> str:
    label = "AI-DRAFTED" if backend == "gemini" else "NO MODEL"
    text = f"DRAFT {_action_text(plan.decision)} ({label})"
    return f"{text}; {notes[-1]}" if notes else text


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
            TraceStage.DRAFTER,
            actor,
            message,
            level=level,
            volcano_id=ctx.flight.volcano_id,
            flight_id=ctx.flight.id,
            detail=detail,
        )
    )
