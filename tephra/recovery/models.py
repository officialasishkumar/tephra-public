"""Data shapes of network recovery: the synthetic RFA schedule, closures, scenarios, plans."""

from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Any, Final, Literal

from pydantic import Field, computed_field

from tephra.models import LlmBackendName, TephraModel, ToolCallRecord, UtcDatetime

__all__ = [
    "AI_UNAVAILABLE",
    "MINUTES_PER_DAY",
    "AiUnavailableBody",
    "Closure",
    "ClosureBasis",
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
    "RfaTemplateFlight",
    "RunRequest",
    "Schedule",
    "ScheduleHeader",
    "SolveStatus",
    "flight_key",
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


MINUTES_PER_DAY: Final = 1440


class RfaTemplateFlight(TephraModel):
    """One line of the daily template in ``data/rfa/flights.json``: the same flight number flies
    every day, at ``std_min`` minutes after the start of that day."""

    flight_no: str = Field(pattern=r"^RFA\d{3}$")
    origin: str = Field(pattern=r"^[A-Z]{4}$")
    dest: str = Field(pattern=r"^[A-Z]{4}$")
    std_min: int = Field(description="Scheduled departure, minutes after the start of the day")
    block_min: int = Field(gt=0)
    tail: str
    pax_booked: int = Field(ge=0)
    pair_id: str | None = Field(
        default=None, description="Out and back of one excursion; cancelled together"
    )


class RfaFlight(RfaTemplateFlight):
    """A template flight on one service date. Real airlines reuse the flight number every day,
    so a flight is identified by :attr:`key`, for example ``RFA239/06SEP``."""

    service_date: date = Field(description="Local calendar date of the departure")
    day_offset: int = Field(ge=0, description="Days after the schedule's first operating day")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def key(self) -> str:
        return flight_key(self.flight_no, self.service_date)


def flight_key(flight_no: str, service_date: date) -> str:
    return f"{flight_no}/{service_date:%d%b}".upper()


class Schedule(TephraModel):
    """A rolling window of RFA flights: the operating day that holds the clock and the next one.

    ``std_min`` of every flight counts from the first day's anchor, so the second day's flights
    leave ``MINUTES_PER_DAY`` later than the template says. :func:`load_schedule` builds it."""

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


ClosureBasis = Literal["HAZARD", "OFFICIAL", "TAF", "METAR", "ENTERED"]
OFFICIAL_PREFIXES: Final = ("SIGMET:", "VAA:")


def _level(ft: int) -> str:
    return "SFC" if ft <= 0 else f"FL{round(ft / 100):03d}"


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
    basis: list[ClosureBasis] = Field(
        default_factory=list, description="What closed it: written by code, merged with the reason"
    )
    base_ft: int | None = Field(default=None, description="Lowest base of the ash behind it")
    top_ft: int | None = Field(default=None, description="Highest top of the ash behind it")
    radius_nm: float | None = Field(default=None, description="The policy's closure radius")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def summary(self) -> str:
        """One line for a card; ``reason`` and ``source_ids`` keep the full audit trail."""
        parts: list[str] = []
        if {"HAZARD", "OFFICIAL"} & set(self.basis):
            band = (
                f" {_level(self.base_ft)}/{_level(self.top_ft)}"
                if self.base_ft is not None and self.top_ft is not None
                else ""
            )
            near = f" within {self.radius_nm:g} NM" if self.radius_nm is not None else " nearby"
            parts.append(f"Ash{band}{near}")
        if "TAF" in self.basis:
            parts.append("TAF forecasts VA")
        if "METAR" in self.basis:
            parts.append("METAR reports VA")
        if "ENTERED" in self.basis:
            parts.append("Entered by dispatcher")
        official = sum(1 for source in self.source_ids if source.startswith(OFFICIAL_PREFIXES))
        if official:
            parts.append(f"{official} official product{'' if official == 1 else 's'}")
        return " · ".join(parts)


class Disruption(TephraModel):
    """What the closures do to the unmodified schedule."""

    closures: list[Closure]
    blocked_flights: list[str] = Field(description="Keys of flights that depart or land closed")
    blocked_pax: int
    airborne_at_risk: list[str] = Field(
        description="Keys of flights already airborne to an airport that is closed on arrival"
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
    flight_key: str = Field(description="flight_no and service date, e.g. RFA239/06SEP")
    service_date: date
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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def chosen(self) -> RecoveryScenario | None:
        """The recommended scenario, so a client need not search ``scenarios`` for it."""
        return next((s for s in self.scenarios if s.id == self.chosen_scenario_id), None)

    def to_doc(self) -> dict[str, Any]:
        """The stored form: ``chosen`` is derived, so it is not kept a second time."""
        return self.model_dump(mode="json", exclude={"chosen"})


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
