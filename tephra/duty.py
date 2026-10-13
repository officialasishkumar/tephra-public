"""The Duty Officer's side of the desk: the work list code finds due, the specialists its tools
reach, and the safety line code holds when the run ends (``agents/duty_officer.py``).

The AI worker (``tephra.ai_worker``) runs the Duty Officer off the tick, over the part of the
work list each model's budget admits now. Work is offered once and again only after
``duty.rerun_min``, so an unchanged list costs no model call. A mandatory item the run leaves
undone goes to the Desk: a flight as an ``AiFailure`` (stage ``duty_officer``) for a dispatcher
to handle by hand, a plume read as an audited AI failure (the area stays at the official
products).
"""

import logging
from collections import Counter
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Final, Literal

from tephra.agents.budget import BudgetView
from tephra.agents.duty_officer import RecordedDuty, run_duty_officer
from tephra.desk import audit
from tephra.desk.approvals import SYSTEM_ACTOR
from tephra.models import (
    Advisory,
    AiFailure,
    AuditAction,
    DutyItem,
    DutyItemKind,
    DutyRun,
    ExposedFlight,
    RunMode,
    Severity,
    SseEvent,
    TickReport,
    TraceStage,
)
from tephra.regdocs.evidence import NoActiveVolcano, UnknownRegion
from tephra.regdocs.narrative import AiUnavailable
from tephra.regdocs.sra import draft_sra
from tephra.store.base import Collection
from tephra.util import timeutil
from tephra.util.hashing import stable_id

if TYPE_CHECKING:
    from tephra.pipeline import Runtime

__all__ = [
    "DUTY_RUN_LIMIT",
    "DeskUnreachable",
    "dispatch_duty",
    "drafts_by_flight",
    "duty_worklist",
]

logger = logging.getLogger(__name__)

DUTY_RUN_LIMIT: Final = 20
"""Duty Officer runs the Wall and the Desk list (newest first)."""
NETWORK: Final = "network"
_URGENCY_RECOVER: Final = 3
_URGENCY_SRA: Final = 4


class DeskUnreachable(Exception):
    """The open drafts could not be read: planning and draft retirement wait a tick."""


async def dispatch_duty(
    runtime: "Runtime",
    worklist: list[DutyItem],
    drafts: dict[str, list[Advisory]],
    at: datetime,
    report: TickReport,
    *,
    trigger: Literal["tick", "adsb"],
    epoch: int,
    waiting: int = 0,
) -> DutyRun:
    """One Duty Officer run over ``worklist`` (the items the AI worker admitted); ``waiting``
    routine items wait for budget and are named in the digest only as a count. A run that ends
    after the picture was reset (a mode switch or a replay loop) changes nothing."""
    executor = _RuntimeExecutor(runtime, at, report, drafts, epoch)
    budget = await runtime.budget_view()

    async def recall(question: str) -> RecordedDuty | None:
        recorded = await runtime.recorded_answer("duty", "duty", question)
        if recorded is None:
            return None
        return RecordedDuty(DutyRun.model_validate(recorded.payload), recorded.label)

    duty = await run_duty_officer(
        worklist,
        executor,
        runtime.llm,
        digest=_digest(runtime, worklist, budget, waiting),
        settings=runtime.settings,
        trigger=trigger,
        replay=runtime.mode is RunMode.REPLAY,
        trace=runtime.sink,
        recall=recall,
    )
    if runtime.epoch != epoch:
        runtime.trace(
            TraceStage.DUTY,
            "code",
            "Duty Officer run ended after the picture was reset; nothing it found is kept",
            level="warn",
        )
        return duty
    rerun = timedelta(minutes=runtime.policy.duty.rerun_min.value)
    for item in duty.worklist:
        runtime.duty_offered[item.id] = at
    runtime.duty_offered = {
        item_id: when for item_id, when in runtime.duty_offered.items() if at - when < 2 * rerun
    }
    duty = duty.model_copy(update={"recorded_wall_at": timeutil.SystemClock().now()})
    await _hold_the_line(runtime, duty)
    runtime.duty = duty
    await runtime.store.put(Collection.DUTY, duty.id, duty.model_dump(mode="json"))
    runtime.bus.publish(SseEvent.DUTY, duty)
    report.duty_runs += 1
    if duty.outcome in ("ACCEPTED", "REPAIRED") and duty.recorded_answer is None:
        await runtime.keep_answer(
            "duty", "duty", duty.prompt_hash, duty.model_id, duty.model_dump(mode="json")
        )
    await runtime.publish_budget()
    return duty


async def drafts_by_flight(runtime: "Runtime") -> dict[str, list[Advisory]]:
    drafts: dict[str, list[Advisory]] = {}
    for draft in await runtime.open_drafts():
        drafts.setdefault(draft.flight_id, []).append(draft)
    return drafts


def duty_worklist(
    runtime: "Runtime", at: datetime, drafts: dict[str, list[Advisory]]
) -> list[DutyItem]:
    """Every piece of AI work code finds due now, most urgent first.

    A plume read is mandatory too when its volcano has a mandatory flight: plans wait for the
    read, so deferring it would leave that flight with no plan."""
    plans = _plan_items(runtime, at, drafts)
    urgent_volcanoes = {item.volcano_id for item in plans if item.mandatory}
    assess = [
        item.model_copy(update={"mandatory": True, "urgency": 0})
        if item.volcano_id in urgent_volcanoes
        else item
        for item in _assess_items(runtime)
    ]
    items = [*assess, *plans, *_recover_items(runtime), *_sra_items(runtime, at)]
    return sorted(items, key=lambda item: (item.urgency, item.label))


# --- the work list ----------------------------------------------------------------------------


def _assess_items(runtime: "Runtime") -> list[DutyItem]:
    items: list[DutyItem] = []
    for volcano_id, input_hash in sorted(runtime.assess_due.items()):
        situation = runtime.situations.get(volcano_id)
        if situation is None:
            continue
        no_official = not situation.official_valid_now()
        ash_reported = any(vona.ash_observed for vona in situation.vonas)
        warning = any(d.severity is Severity.WARNING for d in situation.discrepancies)
        mandatory = (no_official and ash_reported) or warning
        why = (
            "ash reported, no official area"
            if no_official and ash_reported
            else "sources disagree (WARNING)"
            if warning
            else "sources or aircraft changed"
        )
        items.append(
            DutyItem(
                id=stable_id("DI", DutyItemKind.ASSESS, volcano_id, input_hash),
                kind=DutyItemKind.ASSESS,
                subject=volcano_id,
                label=f"Plume read: {situation.volcano.name} ({why})",
                mandatory=mandatory,
                urgency=0 if mandatory else 1,
                volcano_id=volcano_id,
            )
        )
    return items


def _plan_items(
    runtime: "Runtime", at: datetime, drafts: dict[str, list[Advisory]]
) -> list[DutyItem]:
    if not runtime.positions_fresh:
        return []
    items: list[DutyItem] = []
    divert_bucket = 1  # urgency buckets: 0 inside now, 1 entry within planner.divert_within_min
    for flight in runtime.exposed.values():
        urgency = runtime.plan_due(flight, drafts.get(flight.id, []), at)
        if urgency is None:
            continue
        items.append(plan_item(runtime, flight, urgency, mandatory=urgency <= divert_bucket))
    return items


def plan_item(
    runtime: "Runtime", flight: ExposedFlight, urgency: int, *, mandatory: bool
) -> DutyItem:
    where = (
        "inside the area now"
        if flight.inside_now
        else f"enters the area in {flight.minutes_to_entry} min"
    )
    return DutyItem(
        id=stable_id("DI", DutyItemKind.PLAN, flight.id, flight.cone_id, urgency),
        kind=DutyItemKind.PLAN,
        subject=flight.id,
        label=f"Plan {flight.proxy_flight} ({runtime.volcano_name(flight.volcano_id)}): {where}",
        mandatory=mandatory,
        urgency=urgency,
        volcano_id=flight.volcano_id,
    )


def _recover_items(runtime: "Runtime") -> list[DutyItem]:
    due = runtime.recovery_due
    if due is None:
        return []
    airports = sorted(due.airports)
    return [
        DutyItem(
            id=stable_id("DI", DutyItemKind.RECOVER, *airports),
            kind=DutyItemKind.RECOVER,
            subject=NETWORK,
            label=f"Network recovery: {', '.join(airports)} closed by the hazard",
            mandatory=False,
            urgency=_URGENCY_RECOVER,
        )
    ]


def _sra_items(runtime: "Runtime", at: datetime) -> list[DutyItem]:
    """A region gets one SRA draft a day once it carries exposed flights."""
    items: list[DutyItem] = []
    for region in runtime.settings.regions:
        if (region.key, at.date()) in runtime.sra_drafted:
            continue
        flights = [
            flight
            for flight in runtime.exposed.values()
            if (situation := runtime.situations.get(flight.volcano_id)) is not None
            and region.bbox.contains(situation.volcano.lat, situation.volcano.lon)
        ]
        if not flights:
            continue
        items.append(
            DutyItem(
                id=stable_id("DI", DutyItemKind.SRA, region.key, at.date().isoformat()),
                kind=DutyItemKind.SRA,
                subject=region.key,
                label=f"Draft SRA: {region.name} now carries {len(flights)} exposed flight(s)",
                mandatory=False,
                urgency=_URGENCY_SRA,
            )
        )
    return items


def _digest(
    runtime: "Runtime", worklist: list[DutyItem], budget: BudgetView, waiting: int = 0
) -> str:
    """The picture in a few code-written lines: the Duty Officer's only view besides tools."""
    lines: list[str] = []
    for volcano_id, situation in sorted(runtime.situations.items()):
        cone = runtime.cones.get(volcano_id)
        severities = Counter(d.severity.value for d in situation.discrepancies)
        flights = [f for f in runtime.exposed.values() if f.volcano_id == volcano_id]
        inside = sum(f.inside_now for f in flights)
        area = cone.label if cone is not None else "no area"
        disagree = ", ".join(f"{n} {name}" for name, n in sorted(severities.items())) or "none"
        lines.append(
            f"- {situation.volcano.name} ({volcano_id}): area {area}; discrepancies {disagree}; "
            f"{len(flights)} exposed flight(s), {inside} inside now"
        )
    mandatory = sum(item.mandatory for item in worklist)
    lines.append(f"- Work due: {len(worklist)} item(s), {mandatory} mandatory")
    if waiting:
        lines.append(f"- Routine work waiting for AI budget, not offered now: {waiting} item(s)")
    lines.extend(
        f"- AI budget today, {model.model_id} ({model.jobs}): {model.used} of {model.limit} used"
        for model in budget.models
    )
    return "\n".join(lines) if lines else "- No active volcano"


# --- what the tools reach -----------------------------------------------------------------------


class _RuntimeExecutor:
    """The specialists, reached through the runtime, at this run's clock."""

    def __init__(
        self,
        runtime: "Runtime",
        at: datetime,
        report: TickReport,
        drafts: dict[str, list[Advisory]],
        epoch: int,
    ) -> None:
        self._runtime = runtime
        self._at = at
        self._report = report
        self._drafts = drafts
        self._epoch = epoch

    async def assess(self, volcano_id: str) -> tuple[dict[str, Any], list[DutyItem]]:
        runtime = self._runtime
        result = await runtime.assess_volcano(volcano_id, self._at, self._report, epoch=self._epoch)
        new = [
            item
            for item in _plan_items(runtime, self._at, self._drafts)
            if item.volcano_id == volcano_id
        ]
        await runtime.publish()
        return result, new

    async def plan(self, flight_id: str) -> dict[str, Any]:
        drafts = self._drafts.get(flight_id, [])
        result = await self._runtime.plan_flight_now(
            flight_id, drafts, self._at, self._report, epoch=self._epoch
        )
        self._drafts[flight_id] = await _open_drafts_for(self._runtime, flight_id)
        await self._runtime.publish()
        return result

    async def recover(self) -> dict[str, Any]:
        return self._runtime.start_recovery(self._report)

    async def draft_sra(self, region: str) -> dict[str, Any]:
        runtime = self._runtime
        runtime.sra_drafted.add((region, self._at.date()))
        try:
            document = await draft_sra(runtime, region)
        except AiUnavailable as exc:
            return {"summary": f"SRA {region}: AI UNAVAILABLE ({exc})", "status": "ai_unavailable"}
        except (UnknownRegion, NoActiveVolcano) as exc:
            return {"error": f"NO SRA FOR {region}: {type(exc).__name__}"}
        return {
            "summary": f"SRA draft {document.id} for {document.region_name}",
            "doc_id": document.id,
        }


# --- the safety line --------------------------------------------------------------------------


async def _hold_the_line(runtime: "Runtime", duty: DutyRun) -> None:
    """Mandatory work the run left undone goes to the Desk; nothing is done in its place."""
    items = {item.id: item for item in duty.worklist}
    reason = (
        "DUTY OFFICER AI UNAVAILABLE: " + ("; ".join(duty.validation_errors[:2]) or "NO BRIEF")
        if duty.outcome == "MODEL_FAILED"
        else "DUTY OFFICER DID NOT DISPATCH THIS FLIGHT"
    )
    for item_id in duty.undispatched:
        item = items[item_id]
        if item.kind is DutyItemKind.PLAN:
            flight = runtime.exposed.get(item.subject)
            if flight is not None:
                await runtime.track_failure(_failure(runtime, flight, reason, duty))
        elif item.kind is DutyItemKind.ASSESS:
            runtime.trace(
                TraceStage.DUTY,
                "code",
                f"{item.label}: not dispatched; the area stays at the official products",
                level="error",
                volcano_id=item.subject,
            )
            await audit.record(
                runtime.store,
                actor=SYSTEM_ACTOR,
                action=AuditAction.AI_FAILED,
                after={"volcano_id": item.subject, "duty_run_id": duty.id},
                model_id=duty.model_id,
                note=f"{reason}: plume read not dispatched",
            )


def _failure(runtime: "Runtime", flight: ExposedFlight, reason: str, duty: DutyRun) -> AiFailure:
    return AiFailure(
        id=stable_id("AIF", flight.id, flight.cone_id, "duty_officer"),
        created_at=duty.finished_at,
        replay=runtime.mode is RunMode.REPLAY,
        stage="duty_officer",
        reason=reason,
        model_id=duty.model_id,
        volcano_id=flight.volcano_id,
        volcano_name=runtime.volcano_name(flight.volcano_id),
        flight_id=flight.id,
        proxy_flight=flight.proxy_flight,
        callsign=flight.callsign,
        hex=flight.hex,
        type_icao=flight.type_icao,
        cone_id=flight.cone_id,
        minutes_to_entry=flight.minutes_to_entry,
        inside_now=flight.inside_now,
    )


async def _open_drafts_for(runtime: "Runtime", flight_id: str) -> list[Advisory]:
    return [draft for draft in await runtime.open_drafts() if draft.flight_id == flight_id]
