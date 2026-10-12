"""Dispatch Drafter: the advisory body and cost note for one planned action.

Gemini (structured output, Flash-Lite) writes only ``body`` and ``cost_note``. Code renders
the header: the flight, the UTC times and every source with its timestamps and short
hash, so the model never writes a time, an id or a hash. ``validators.validate_draft``
checks the text and allows one repair. A draft that still fails, or no answer at all, gives
no advisory: an ``AiFailure`` goes to the Desk and a dispatcher writes the message.
"""

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Final, Literal, NamedTuple
from uuid import uuid4

from tephra.agents.exposure_planner import band_text, flight_summary, present_fl
from tephra.agents.llm import LlmBackend, LlmCall, LlmPart, prompt_hash
from tephra.agents.validators import (
    ACTION_WORDS,
    COST_NOTE_MAX_CHARS,
    first_problems,
    reroute_of,
    validate_draft,
)
from tephra.config import AIRLINE_NAME, Settings
from tephra.models import (
    ActionKind,
    Advisory,
    AdvisoryStatus,
    AiFailure,
    DraftText,
    ExposedFlight,
    FeedHealth,
    FeedId,
    HazardCone,
    LlmBackendName,
    OperatorPolicy,
    PlannedAction,
    PlannerContext,
    PlannerDecision,
    PlumeAssessment,
    PlumeMode,
    ReplayCase,
    RerouteOption,
    RunMode,
    Situation,
    SourceRef,
    TraceActor,
    TraceEvent,
    TraceSink,
    TraceStage,
    VaacCentre,
    WindProfile,
)
from tephra.reconcile.discrepancies import feed_degraded
from tephra.util import timeutil
from tephra.util.hashing import stable_id

PROMPT_PATH: Final[Path] = Path(__file__).resolve().parent / "prompts" / "drafter.md"
AI_UNAVAILABLE: Final = "AI UNAVAILABLE"
REPAIR_ECHO_CHARS: Final = 2000
"""How much of an unreadable answer the repair prompt quotes back."""
HEADER_TITLE: Final = (
    f"TEPHRA COMPANY ADVISORY - {AIRLINE_NAME.upper()} (FICTIONAL) - NOT FOR OPERATIONAL USE"
)
POLICY_A_AVOID: Final = (
    "POLICY A ADVISES AVOIDING THE AREA (DOC 9974 APP 5 5.4(D)(2)); NO DRIFT-DOWN OR ESCAPE"
    " CHECK MADE"
)
"""Appended to an OVER ASH or UNDER ASH line: the band clears the hazard vertically, which
Policy A does not plan for (vertical avoidance is a Policy B choice)."""
_VAAC_FEEDS: Final = {VaacCentre.TOKYO: FeedId.VAAC_TOKYO, VaacCentre.DARWIN: FeedId.VAAC_DARWIN}


# --- header (code only) -----------------------------------------------------------------


def render_header(
    *,
    ctx: PlannerContext,
    plan: PlannedAction,
    cone: HazardCone,
    sources: Sequence[SourceRef],
    at: datetime,
    replay: bool = False,
    replay_case: ReplayCase | None = None,
    degraded_feeds: Sequence[FeedHealth] = (),
) -> str:
    """Every line is code-written. A REPLAY header names its case right after the flight
    line; a degraded official feed adds an information line and changes no action."""
    flight = ctx.flight
    cone_line = f"CONE {cone.mode.value} {round(cone.confidence * 100)}%"
    if cone.llm_backend == "stub":
        cone_line += " NO MODEL"
    lines = [
        HEADER_TITLE,
        f"{flight.proxy_flight} (ADS-B {flight.callsign or 'NO CALLSIGN'} {flight.hex})",
        *([_replay_line(replay_case)] if replay or replay_case is not None else []),
        f"VOLCANO {ctx.volcano_name}",
        f"ACTION {_action_text(plan.decision)}",
        *_vertical_lines(ctx, plan.decision),
        "INSIDE NOW" if flight.inside_now else f"ENTRY {flight.minutes_to_entry} MIN",
        cone_line,
        *(_incomplete_line(health) for health in degraded_feeds),
        f"DRAFTED {timeutil.hhmmz(at)}",
    ]
    source_lines = [_source_line(source) for source in _binding_first(sources)]
    return "\n".join([*(_ascii_upper(line) for line in lines), *source_lines])


def _replay_line(case: ReplayCase | None) -> str:
    if case is None:
        return "REPLAY - NOT LIVE"
    how = "RECONSTRUCTED FROM ARCHIVES" if case.reconstructed else "RECORDED FROM LIVE FEEDS"
    day = case.recorded_from.strftime("%d %b %Y")
    return f"REPLAY - {how} {case.case_id} ({day}) - NOT LIVE"


def _vertical_lines(ctx: PlannerContext, decision: PlannerDecision) -> list[str]:
    """OVER ASH or UNDER ASH when the advised band (CHANGE_LEVEL) or the present level
    (CONTINUE) clears the hazard vertically by more than the margin."""
    match decision.action:
        case ActionKind.CHANGE_LEVEL:
            low, high = decision.change_level_fl_min, decision.change_level_fl_max
        case ActionKind.CONTINUE:
            low = high = present_fl(ctx.flight)
        case _:
            return []
    if low is None or high is None:
        return []
    top, base, margin = ctx.hazard_top_ft, ctx.hazard_base_ft, ctx.vertical_margin_ft
    if low * 100 > top + margin:
        return [
            f"OVER ASH: FL{low:03d} IS {low * 100 - top} FT ABOVE THE FL{top // 100:03d} TOP."
            f" {POLICY_A_AVOID}"
        ]
    if high * 100 < base - margin:
        return [
            f"UNDER ASH: FL{high:03d} IS {base - high * 100} FT BELOW THE FL{base // 100:03d}"
            f" BASE. {POLICY_A_AVOID}"
        ]
    return []


def _incomplete_line(health: FeedHealth) -> str:
    last = health.last_success_at
    since = timeutil.ddhhmmz(last) if last is not None else "NEVER"
    return (
        f"OFFICIAL PICTURE INCOMPLETE: {health.feed.value} NOT UPDATED SINCE {since};"
        " CONFIRM THE CURRENT VAA AND SIGMET WITH MET BEFORE ACTING"
    )


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
        case ActionKind.REROUTE:
            return "REROUTE AROUND HAZARD"
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


# --- template (stub backend only) ----------------------------------------------------


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
        case ActionKind.REROUTE:
            option = reroute_of(decision, ctx)
            route = option.route_string if option is not None else ""
            return f"REROUTE AROUND HAZARD {route}, ATC PERMITTING."
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


class RecordedDraft(NamedTuple):
    """The first pass's draft for the same question, on a REPLAY loop."""

    draft: DraftText
    model_id: str
    prompt_hash: str
    """The hash of the call that wrote it (a repair call's, when it was repaired)"""
    question_hash: str
    """:func:`drafter_prompt_hash` of the question it answered"""
    label: str


def drafter_prompt_hash(ctx: PlannerContext, plan: PlannedAction) -> str:
    """The hash of the drafter's first question for this flight and plan: its instructions
    and the facts it may use. A REPLAY loop reuses a recorded draft only for exactly this
    question."""
    return prompt_hash(PROMPT_PATH.read_text(encoding="utf-8"), _draft_parts(ctx, plan))


def _draft_parts(ctx: PlannerContext, plan: PlannedAction) -> list[LlmPart]:
    return [_text_part(json.dumps(_facts(ctx, plan), indent=1), "facts")]


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
    feed_health: Mapping[FeedId, FeedHealth] | None = None,
    replay_case: ReplayCase | None = None,
    recorded: RecordedDraft | None = None,
) -> Advisory | AiFailure:
    """``policy`` is stamped on the advisory (id, version and short content hash) so every
    decision on it records the operator policy it was drafted under. ``feed_health`` adds an
    OFFICIAL PICTURE INCOMPLETE line for a degraded SIGMET or VAAC feed; ``replay_case``
    names the case on a REPLAY draft. ``recorded`` (REPLAY only) is the first pass's draft
    for the same question (:func:`drafter_prompt_hash`): used, labelled, when it passes the
    checks now; otherwise the model is asked as usual."""
    if plan.decision is None:
        raise ValueError(f"plan {plan.id} has no decision to draft")
    if replay_case is not None and not _replay(situation):
        raise ValueError(f"replay case {replay_case.case_id} given for a LIVE situation")
    system = PROMPT_PATH.read_text(encoding="utf-8")
    parts = _draft_parts(ctx, plan)
    reused = (
        recorded
        if recorded is not None
        and recorded.question_hash == prompt_hash(system, parts)
        and not _recorded_problems(recorded, ctx, plan, trace)
        else None
    )
    if reused is not None:
        draft: DraftText | None = reused.draft
        call = LlmCall(
            backend="gemini",
            model_id=reused.model_id,
            prompt_hash=reused.prompt_hash,
            raw_text=reused.draft.model_dump_json(),
            cached=True,
        )
        problems: list[str] = []
    else:
        draft, call = await _ask(llm, system, parts, ctx, plan)
        problems = _problems(draft, call, ctx, plan)
    drafter_hash = call.prompt_hash
    # The model answered (even unreadably): one repair. No answer at all (budget, API
    # error) is a failure straight away.
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

    backend: LlmBackendName = "gemini" if reused is not None else llm.name
    model_id = call.model_id
    if draft is None or problems:
        reason = _failure_reason(draft, call, problems)
        _emit(
            trace,
            ctx,
            "code",
            f"DRAFTER {AI_UNAVAILABLE} ({reason}): NO DRAFT, A DISPATCHER MUST WRITE THE MESSAGE",
            level="error",
            detail={"problems": problems},
        )
        return ai_failure(
            ctx,
            stage="drafter",
            reason=reason,
            model_id=model_id,
            replay=_replay(situation),
            plan_id=plan.id,
        )
    line = _draft_line(plan, backend)
    _emit(trace, ctx, _actor(backend), f"{line} ({reused.label})" if reused else line)

    created = timeutil.now()
    sources = select_sources(situation, ctx.flight)
    official_feeds = (FeedId.SIGMET, _VAAC_FEEDS[situation.volcano.vaac])
    degraded = [
        health
        for feed in official_feeds
        if (health := feed_degraded(feed, feed_health, created, settings)) is not None
    ]
    header = render_header(
        ctx=ctx,
        plan=plan,
        cone=cone,
        sources=sources,
        at=created,
        replay=_replay(situation),
        replay_case=replay_case,
        degraded_feeds=degraded,
    )
    return _advisory(
        situation=situation,
        assessment=assessment,
        cone=cone,
        ctx=ctx,
        plan=plan,
        policy=policy,
        draft=draft,
        sources=sources,
        header=header,
        replay_case=replay_case,
        created=created,
        backend=backend,
        model_id=model_id,
        prompt_hashes={
            "plume_reader": assessment.prompt_hash,
            "planner": plan.prompt_hash,
            "drafter": drafter_hash,
        },
        recorded_answer=_recorded_words(
            plan.recorded_answer, reused.label if reused is not None else None
        ),
    )


def _recorded_words(plan_label: str | None, draft_label: str | None) -> str | None:
    """Which part of the advisory a REPLAY loop reused from its first pass, if any."""
    if plan_label is not None and draft_label is not None:
        return f"Plan and draft: {draft_label}"
    if plan_label is not None:
        return f"Plan: {plan_label}; the draft was written by the model now"
    if draft_label is not None:
        return f"Draft: {draft_label}; the plan was made by the model now"
    return None


def _recorded_problems(
    recorded: RecordedDraft, ctx: PlannerContext, plan: PlannedAction, trace: TraceSink | None
) -> list[str]:
    problems = validate_draft(recorded.draft, ctx=ctx, plan=plan)
    if problems:
        _emit(
            trace,
            ctx,
            "code",
            "Recorded draft from the replay's first pass no longer fits; asking the model",
            level="warn",
            detail={"problems": problems},
        )
    return problems


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


def _failure_reason(draft: DraftText | None, call: LlmCall, problems: Sequence[str]) -> str:
    if draft is None:
        return f"NO DRAFT RETURNED ({call.error or 'unknown error'})"
    return f"DRAFT FAILED CHECKS AFTER REPAIR: {'; '.join(first_problems(problems, 3))}"


def _replay(situation: Situation) -> bool:
    return situation.mode is RunMode.REPLAY


def ai_failure(
    ctx: PlannerContext,
    *,
    stage: Literal["planner", "drafter"],
    reason: str,
    model_id: str,
    replay: bool,
    plan_id: str | None = None,
) -> AiFailure:
    """The Desk item for a flight the AI could not plan or draft for."""
    flight = ctx.flight
    return AiFailure(
        id=stable_id("AIF", flight.id, flight.cone_id, stage),
        created_at=timeutil.now(),
        replay=replay,
        stage=stage,
        reason=reason,
        model_id=model_id,
        volcano_id=flight.volcano_id,
        volcano_name=ctx.volcano_name,
        flight_id=flight.id,
        proxy_flight=flight.proxy_flight,
        callsign=flight.callsign,
        hex=flight.hex,
        type_icao=flight.type_icao,
        cone_id=flight.cone_id,
        minutes_to_entry=flight.minutes_to_entry,
        inside_now=flight.inside_now,
        plan_id=plan_id,
    )


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
    replay_case: ReplayCase | None,
    created: datetime,
    backend: LlmBackendName,
    model_id: str,
    prompt_hashes: dict[str, str],
    recorded_answer: str | None,
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
        reroute=reroute_of(decision, ctx),
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
        policy_hash=policy.content_hash()[:12],
        replay_case_id=replay_case.case_id if replay_case is not None else None,
        header=header,
        body=draft.body.strip(),
        cost_note=draft.cost_note.strip(),
        sources=sources,
        input_hash=situation.input_hash,
        llm_backend=backend,
        model_id=model_id,
        prompt_hashes=prompt_hashes,
        recorded_answer=recorded_answer,
        validation_notes=[],
        dedupe_key=stable_id(
            "DD",
            flight.hex,
            volcano_id,
            decision.action,
            decision.change_level_fl_min,
            decision.hold_fl,
            decision.alternate_icao,
            *([decision.reroute_id] if decision.reroute_id else []),
        ),
    )


# --- model input ------------------------------------------------------------------------


def _facts(ctx: PlannerContext, plan: PlannedAction) -> dict[str, Any]:
    """Everything the drafter may say, with no clock times, ids or hashes in it."""
    decision = plan.decision
    alternate = next((alt for alt in ctx.alternates if alt.icao == decision.alternate_icao), None)
    reroute = reroute_of(decision, ctx)
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
            "reroute": _reroute_facts(reroute),
            "planner_reasoning": decision.reasoning,
        },
        "cost": _cost_facts(plan),
        "listed_icao_codes": [alt.icao for alt in ctx.alternates],
    }


def _reroute_facts(option: RerouteOption | None) -> dict[str, Any] | None:
    if option is None:
        return None
    return {
        "route_string": option.route_string,
        "side": option.side,
        "buffer_nm": option.buffer_nm,
        "end": option.end_icao,
        "wind": option.wind_note,
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


def _draft_line(plan: PlannedAction, backend: LlmBackendName) -> str:
    label = "AI-DRAFTED" if backend == "gemini" else "NO MODEL"
    return f"DRAFT {_action_text(plan.decision)} ({label})"


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
