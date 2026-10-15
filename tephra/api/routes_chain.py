"""``GET /api/advisories/{id}/chain``: the four-step reasoning chain behind one advisory
(Coordinator, Plume reader, Flight planner, Drafter), assembled by code from the records each
skill left in the store. Public and read-only like the other Wall data.

Every part is the record as stored, trimmed to what a reader needs: no dispatcher name, no
budget, no clock time the model wrote. A part whose record is missing is ``null``, never a 500.
"""

import re
from typing import Final, Literal

from fastapi import APIRouter
from pydantic import ValidationError
from starlette.responses import Response

from tephra.agents.validators import _number_tokens  # private until T07 exports number_tokens
from tephra.api import ApiError
from tephra.api.server import RuntimeDep, _json
from tephra.models import (
    ActionKind,
    Advisory,
    DisagreementReading,
    DutyItemKind,
    DutyRun,
    PlannedAction,
    PlannerDecision,
    PlumeAssessment,
    PlumeMode,
    TephraModel,
    ToolCallRecord,
    UtcDatetime,
)
from tephra.store.base import Collection, Store

router = APIRouter()

ADVISORY_ID: Final = re.compile(r"^adv_[0-9a-f]{12}$")
"""The Advisory id recipe (``models.Advisory.id``: 'adv_' + 12 hex chars)."""

DUTY_WINDOW: Final = 20
"""Newest Coordinator runs searched for the one that dispatched this flight's plan."""

PLAN_TOOL: Final = "plan_flights"
"""The Coordinator's tool that delegates a flight to the Flight planner and the Drafter."""

PLUME_CHECKS: Final = (
    "citations",
    "times",
    "numbers",
    "mode",
    "geometry",
    "hypothesis",
    "narrowing",
)
"""``plume_reader.validate_estimate``'s validators, in order."""

REASONING_CHECKS: Final = ("clock words",)
"""The planner's reasoning is checked for emptiness, length and clock words only."""

_ACTION_CHECK: Final[dict[ActionKind, str]] = {
    ActionKind.CHANGE_LEVEL: "level band clear of the hazard",
    ActionKind.HOLD: "hold level and time",
    ActionKind.DIVERT: "listed alternate",
    ActionKind.REROUTE: "listed reroute",
    ActionKind.CONTINUE: "continue only when clear",
}
"""``validators.validate_decision``'s rule for each action (MONITOR has none of its own)."""

DRAFT_CHECKS: Final = (
    "allowed action",
    "listed alternate",
    "listed reroute",
    "numbers from facts",
    "places from facts",
    "no clock times",
    "no CLOSED",
    "VAR line",
)
"""``validators.validate_draft``'s rules."""

Outcome = Literal["ACCEPTED", "REPAIRED", "MODEL_FAILED", "OFFICIAL_ONLY", "PENDING", "STUB"]


class CoordinatorStep(TephraModel):
    run_id: str
    decided_at: UtcDatetime
    outcome: Outcome
    rank: int | None = None
    of: int
    why: str | None = None


class PlumeStep(TephraModel):
    assessment_id: str
    model_id: str
    outcome: Outcome
    attempts: int
    mode: PlumeMode
    base_fl: int
    top_fl: int
    sources_used: list[str]
    leaned_on: list[DisagreementReading]
    rationale: str
    uncertainty_notes: str
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    checks: list[str]


class PlanStep(TephraModel):
    plan_id: str
    model_id: str
    outcome: Outcome
    repaired: bool
    tool_calls: list[ToolCallRecord]
    reasoning: str | None
    reasoning_checks: list[str]
    action: ActionKind | None
    target: str | None
    input_tokens: int | None
    output_tokens: int | None
    checks: list[str]


class DraftStep(TephraModel):
    model_id: str
    outcome: Outcome
    repaired: bool
    numbers_in_body: int
    validation_notes: list[str]
    drafted_at: UtcDatetime
    checks: list[str]


class AdvisoryChain(TephraModel):
    advisory_id: str
    flight: str
    volcano_name: str
    coordinator: CoordinatorStep | None
    plume: PlumeStep | None
    plan: PlanStep | None
    draft: DraftStep


@router.get("/advisories/{advisory_id}/chain", response_model=AdvisoryChain)
async def get_chain(advisory_id: str, runtime: RuntimeDep) -> Response:
    if not ADVISORY_ID.match(advisory_id):
        raise ApiError(404, "not_found", "No such advisory")
    advisory = await _advisory(runtime.store, advisory_id)
    return _json(
        AdvisoryChain(
            advisory_id=advisory.id,
            flight=advisory.proxy_flight,
            volcano_name=advisory.volcano_name,
            coordinator=await _coordinator(runtime.store, advisory),
            plume=await _plume(runtime.store, advisory.assessment_id),
            plan=await _plan(runtime.store, advisory.plan_id),
            draft=_draft(advisory),
        )
    )


async def _advisory(store: Store, advisory_id: str) -> Advisory:
    doc = await store.get(Collection.ADVISORIES, advisory_id)
    if doc is None:
        raise ApiError(404, "not_found", "No such advisory")
    try:
        return Advisory.model_validate(doc)
    except ValidationError:
        # Stored by an older build: its chain cannot be read, and that is a 404, never a 500.
        raise ApiError(404, "not_found", "This advisory's record is not on hand") from None


async def _coordinator(store: Store, advisory: Advisory) -> CoordinatorStep | None:
    """The newest run of the advisory's mode whose ``plan_flights`` dispatch held this flight."""
    docs = await store.query(
        Collection.DUTY, [], order_by="recorded_wall_at", descending=True, limit=DUTY_WINDOW
    )
    for doc in docs:
        try:
            run = DutyRun.model_validate(doc)
        except ValidationError:
            continue  # a run stored by an older build
        if run.replay != advisory.replay:
            continue
        item_id = _planned_item(run, advisory.flight_id)
        if item_id is not None:
            return _coordinator_step(run, item_id)
    return None


def _planned_item(run: DutyRun, flight_id: str) -> str | None:
    items = {
        item.id
        for item in run.worklist
        if item.kind is DutyItemKind.PLAN and item.subject == flight_id
    }
    for dispatch in run.dispatches:
        if dispatch.tool == PLAN_TOOL:
            held = items.intersection(dispatch.item_ids)
            if held:
                return min(held)
    return None


def _coordinator_step(run: DutyRun, item_id: str) -> CoordinatorStep:
    priorities = run.brief.priorities if run.brief is not None else []
    rank = next((n for n, p in enumerate(priorities, start=1) if p.item_id == item_id), None)
    why = next((p.why for p in priorities if p.item_id == item_id), None)
    return CoordinatorStep(
        run_id=run.id,
        decided_at=run.decided_at if run.decided_at is not None else run.finished_at,
        outcome=run.outcome,
        rank=rank,
        of=len(priorities),
        why=why,
    )


async def _plume(store: Store, assessment_id: str) -> PlumeStep | None:
    doc = await store.get(Collection.ASSESSMENTS, assessment_id)
    if doc is None:
        return None
    try:
        assessment = PlumeAssessment.model_validate(doc)
    except ValidationError:
        return None
    estimate = assessment.estimate
    return PlumeStep(
        assessment_id=assessment.id,
        model_id=assessment.model_id,
        outcome=assessment.outcome,
        attempts=assessment.attempts,
        mode=estimate.mode,
        base_fl=estimate.base_fl,
        top_fl=estimate.top_fl,
        sources_used=estimate.sources_used,
        leaned_on=estimate.disagreements_explained,
        rationale=estimate.rationale,
        uncertainty_notes=estimate.uncertainty_notes,
        latency_ms=assessment.latency_ms,
        input_tokens=assessment.input_tokens,
        output_tokens=assessment.output_tokens,
        checks=list(PLUME_CHECKS),
    )


async def _plan(store: Store, plan_id: str) -> PlanStep | None:
    doc = await store.get(Collection.PLANS, plan_id)
    if doc is None:
        return None
    try:
        plan = PlannedAction.model_validate(doc)
    except ValidationError:
        return None
    decision = plan.decision
    return PlanStep(
        plan_id=plan.id,
        model_id=plan.model_id,
        outcome=plan.outcome,
        repaired=plan.outcome == "REPAIRED",
        tool_calls=plan.tool_calls,
        reasoning=decision.reasoning if decision is not None else None,
        reasoning_checks=list(REASONING_CHECKS),
        action=decision.action if decision is not None else None,
        target=_target(decision) if decision is not None else None,
        input_tokens=plan.input_tokens,
        output_tokens=plan.output_tokens,
        checks=_decision_checks(decision.action) if decision is not None else [],
    )


def _target(decision: PlannerDecision) -> str | None:
    """The code-rendered target of the action: a level band, a hold level, an alternate or a
    reroute option. CONTINUE and MONITOR have none."""
    match decision.action:
        case ActionKind.CHANGE_LEVEL:
            if decision.change_level_fl_min is None or decision.change_level_fl_max is None:
                return None
            return f"FL{decision.change_level_fl_min:03d}-FL{decision.change_level_fl_max:03d}"
        case ActionKind.HOLD:
            return f"FL{decision.hold_fl:03d}" if decision.hold_fl is not None else None
        case ActionKind.DIVERT:
            return decision.alternate_icao
        case ActionKind.REROUTE:
            return decision.reroute_id
        case _:
            return None


def _decision_checks(action: ActionKind) -> list[str]:
    checks = ["allowed action"]
    own = _ACTION_CHECK.get(action)
    if own is not None:
        checks.append(own)
    checks.extend(("reroute id only on a reroute", "reasoning"))
    return checks


def _draft(advisory: Advisory) -> DraftStep:
    """``Advisory`` records no repair flag or outcome: a note means the first body was
    rejected once and the second passed; the stub's bodies are NO MODEL."""
    stub = advisory.llm_backend == "stub" or advisory.model_id == "stub"
    repaired = bool(advisory.validation_notes)
    return DraftStep(
        model_id=advisory.model_id,
        outcome="STUB" if stub else ("REPAIRED" if repaired else "ACCEPTED"),
        repaired=repaired,
        numbers_in_body=len(_number_tokens(advisory.body)),
        validation_notes=advisory.validation_notes,
        drafted_at=advisory.drafted_at if advisory.drafted_at is not None else advisory.created_at,
        checks=list(DRAFT_CHECKS),
    )
