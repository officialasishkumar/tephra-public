"""Data shapes of network recovery: the synthetic RFA schedule, closures, scenarios, plans."""

from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Final, Literal

from pydantic import Field

from tephra.models import LlmBackendName, TephraModel, ToolCallRecord, UtcDatetime

__all__ = [
    "AI_UNAVAILABLE",
    "AiUnavailableBody",
    "Closure",
    "Disruption",
    "FerryLeg",
    "FlightAction",
    "ManualClosure",
    "PlanStatus",
    "RecoveryActionKind",
    "RecoveryPlan",
    "RecoveryPlanList",
    "RecoveryScenario",
    "RecoveryTotals",
    "RfaCrew",
    "RfaFlight",
    "RfaTail",
    "RunRequest",
    "Schedule",
    "ScheduleHeader",
    "SolveStatus",
]

AI_UNAVAILABLE: Final = "AI UNAVAILABLE"
FICTIONAL_LABEL: Final = "FICTIONAL AIRLINE RFA - SYNTHETIC SCHEDULE - DECISION SUPPORT ONLY"


# --- the synthetic RFA schedule -----------------------------------------------------------


class ScheduleHeader(TephraModel):
    label: str
    seed: int
    anchor_utc_offset_h: int = Field(
        description="The day starts at 00:00 at this offset from UTC; std_min counts from there"
    )
    cruise_kt: int = Field(description="Block-time model: distance at this speed ...")
    overhead_min: int = Field(description="... plus this many minutes for taxi, climb and approach")
    generated_by: str


class RfaTail(TephraModel):
    tail: str = Field(pattern=r"^RFA-T\d{2}$")
    type: str
    seats: int = Field(gt=0)
    home_base: str = Field(pattern=r"^[A-Z]{4}$")
    crew_id: str


class RfaCrew(TephraModel):
    crew_id: str
    base: str = Field(pattern=r"^[A-Z]{4}$")
    report_min: int = Field(description="Duty starts this many minutes after the day's anchor")


class RfaFlight(TephraModel):
    flight_no: str = Field(pattern=r"^RFA\d{3}$")
    origin: str = Field(pattern=r"^[A-Z]{4}$")
    dest: str = Field(pattern=r"^[A-Z]{4}$")
    std_min: int = Field(description="Scheduled departure, minutes after the day's anchor")
    block_min: int = Field(gt=0)
    tail: str
    pax_booked: int = Field(ge=0)
    pair_id: str | None = Field(
        default=None, description="Out and back of one excursion; cancelled together"
    )


class Schedule(TephraModel):
    """One operating day of RFA, anchored to a calendar day by :func:`load_schedule`."""

    day: date
    header: ScheduleHeader
    tails: list[RfaTail]
    crews: list[RfaCrew]
    flights: list[RfaFlight]

    @property
    def anchor(self) -> datetime:
        """UTC instant of 00:00 on ``day`` at the schedule's offset from UTC."""
        midnight = datetime(self.day.year, self.day.month, self.day.day, tzinfo=UTC)
        return midnight - timedelta(hours=self.header.anchor_utc_offset_h)

    def at(self, minutes: int) -> datetime:
        return self.anchor + timedelta(minutes=minutes)

    def minutes_of(self, moment: datetime) -> float:
        return (moment - self.anchor).total_seconds() / 60.0


# --- closures and disruption ----------------------------------------------------------------


class Closure(TephraModel):
    """An airport that cannot be used between two instants. Reason and sources are code-written."""

    icao: str = Field(pattern=r"^[A-Z]{4}$")
    start: UtcDatetime
    end: UtcDatetime
    reason: str
    source_ids: list[str] = Field(default_factory=list)
    open_ended: bool = Field(
        default=False, description="No end is published; planned to the end of the horizon"
    )


class Disruption(TephraModel):
    """What the closures do to the unmodified schedule."""

    closures: list[Closure]
    blocked_flights: list[str] = Field(description="Flight numbers that depart or land closed")
    blocked_pax: int
    airborne_at_risk: list[str] = Field(
        description="Flights already airborne to an airport that is closed on arrival"
    )
    free_flights: int = Field(description="Flights the solver may change")
    frozen_flights: int
    horizon_end: UtcDatetime


# --- scenarios and plans ----------------------------------------------------------------------


class SolveStatus(StrEnum):
    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    NO_PLAN = "NO_PLAN"


class RecoveryActionKind(StrEnum):
    KEEP = "KEEP"
    DELAY = "DELAY"
    CANCEL = "CANCEL"
    SWAP = "SWAP"


class FlightAction(TephraModel):
    flight_no: str
    origin: str
    dest: str
    std: UtcDatetime
    kind: RecoveryActionKind
    new_std: UtcDatetime | None = None
    delay_min: int = 0
    tail: str = Field(description="Aircraft in the published schedule")
    new_tail: str | None = Field(default=None, description="Set for SWAP")
    pax_booked: int
    pair_id: str | None = None


class FerryLeg(TephraModel):
    tail: str
    origin: str
    dest: str
    dep: UtcDatetime
    arr: UtcDatetime
    block_min: int


class RecoveryTotals(TephraModel):
    free_flights: int
    kept_flights: int
    delayed_flights: int
    cancelled_flights: int
    swapped_flights: int
    ferries: int
    delay_min: int
    pax_delayed: int
    pax_cancelled: int
    pax_affected: int
    delay_usd: int
    cancel_usd: int
    swap_usd: int
    ferry_usd: int
    total_usd: int


class RecoveryScenario(TephraModel):
    id: str = Field(description="stable_id('SC', plan inputs); code-written")
    label: str
    extend_min: int
    protect_flights: list[str] = Field(default_factory=list)
    max_delay_min: int
    status: SolveStatus
    solver_status: str = Field(description="OR-Tools status name, e.g. OPTIMAL or UNKNOWN")
    solve_ms: int
    totals: RecoveryTotals | None = None
    actions: list[FlightAction] = Field(
        default_factory=list, description="Every free flight that is not KEEP"
    )
    ferry_legs: list[FerryLeg] = Field(default_factory=list)
    closures: list[Closure] = Field(description="As planned in this scenario (end extended)")


PlanStatus = Literal["DRAFT", "APPROVED", "REJECTED", "SUPERSEDED", "AI_UNAVAILABLE"]


class RecoveryPlan(TephraModel):
    """The recovery agent's recommendation. A DRAFT until a dispatcher decides it."""

    id: str
    created_at: UtcDatetime
    replay: bool
    status: PlanStatus
    version: int = 1
    label: str = FICTIONAL_LABEL
    closures: list[Closure]
    disruption: Disruption | None = None
    scenarios: list[RecoveryScenario] = Field(default_factory=list)
    chosen_scenario_id: str | None = None
    rationale: str | None = Field(default=None, description="AI-written; numbers checked by code")
    risks: list[str] = Field(default_factory=list)
    unavailable_reason: str | None = Field(
        default=None, description=f"Set with status AI_UNAVAILABLE: '{AI_UNAVAILABLE}: <reason>'"
    )
    llm_backend: LlmBackendName
    model_id: str
    prompt_hash: str
    outcome: Literal["ACCEPTED", "REPAIRED", "MODEL_FAILED", "STUB"]
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    decided_by: str | None = None
    decided_at: UtcDatetime | None = None
    reject_reason: str | None = None

    @property
    def chosen(self) -> RecoveryScenario | None:
        return next((s for s in self.scenarios if s.id == self.chosen_scenario_id), None)


class RecoveryPlanList(TephraModel):
    plans: list[RecoveryPlan]


class ManualClosure(TephraModel):
    """A closure the dispatcher enters, for example from a NOTAM. It is labelled as entered."""

    icao: str = Field(pattern=r"^[A-Z]{4}$")
    start: UtcDatetime
    end: UtcDatetime
    reference: str = Field(default="", max_length=40, pattern=r"^[A-Za-z0-9 ./-]*$")


class RunRequest(TephraModel):
    closures: list[ManualClosure] = Field(default_factory=list, max_length=8)


class AiUnavailableBody(TephraModel):
    """HTTP 503 body when the model gave no valid recovery plan (docs/EXTENSIONS.md rule 1)."""

    error: Literal["ai_unavailable"] = "ai_unavailable"
    message: str
