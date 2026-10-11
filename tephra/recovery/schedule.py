"""Loads the synthetic RFA schedule (``data/rfa/``) and anchors it to a calendar day.

The files hold minutes after the start of an operating day, not dates, so the same fictional
day can stand on the replay's or the live clock's day.
"""

import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from tephra.models import TephraModel
from tephra.recovery.models import RfaCrew, RfaFlight, RfaTail, Schedule, ScheduleHeader

__all__ = ["SCHEDULE_DIR", "ScheduleError", "block_minutes", "load_schedule", "operating_day"]

SCHEDULE_DIR: Final = "rfa"
BLOCK_STEP_MIN: Final = 5
"""Block times are rounded up to this step, like the delay steps the solver offers."""


class ScheduleError(ValueError):
    """The schedule files are missing, unreadable or inconsistent."""


class _FleetFile(TephraModel):
    tails: list[RfaTail]


class _CrewFile(TephraModel):
    crews: list[RfaCrew]


class _FlightFile(TephraModel):
    header: ScheduleHeader
    flights: list[RfaFlight]


def block_minutes(distance_nm: float, header: ScheduleHeader) -> int:
    raw = distance_nm / header.cruise_kt * 60.0 + header.overhead_min
    return math.ceil(raw / BLOCK_STEP_MIN) * BLOCK_STEP_MIN


def operating_day(at: datetime, header: ScheduleHeader) -> datetime:
    """The operating day (a date at midnight, UTC-tagged) whose local day holds ``at``."""
    local = at.astimezone(UTC) + timedelta(hours=header.anchor_utc_offset_h)
    return datetime(local.year, local.month, local.day, tzinfo=UTC)


def load_schedule(data_dir: Path, at: datetime) -> Schedule:
    folder = data_dir / SCHEDULE_DIR
    try:
        fleet = _FleetFile.model_validate_json((folder / "fleet.json").read_bytes())
        crews = _CrewFile.model_validate_json((folder / "crews.json").read_bytes())
        flights = _FlightFile.model_validate_json((folder / "flights.json").read_bytes())
    except (OSError, ValidationError) as exc:
        raise ScheduleError(f"RFA schedule files in {folder} are unusable: {exc}") from exc
    schedule = Schedule(
        day=operating_day(at, flights.header).date(),
        header=flights.header,
        tails=fleet.tails,
        crews=crews.crews,
        flights=sorted(flights.flights, key=lambda f: (f.std_min, f.flight_no)),
    )
    problems = _problems(schedule)
    if problems:
        raise ScheduleError("; ".join(problems[:5]))
    return schedule


def _problems(schedule: Schedule) -> list[str]:
    tails = {tail.tail: tail for tail in schedule.tails}
    crews = {crew.crew_id for crew in schedule.crews}
    numbers = [flight.flight_no for flight in schedule.flights]
    problems = [
        f"tail {tail.tail} has unknown crew {tail.crew_id}"
        for tail in schedule.tails
        if tail.crew_id not in crews
    ]
    if len(set(numbers)) != len(numbers):
        problems.append("duplicate flight numbers")
    chains: dict[str, list[RfaFlight]] = defaultdict(list)
    for flight in schedule.flights:
        tail = tails.get(flight.tail)
        if tail is None:
            problems.append(f"{flight.flight_no} is on unknown tail {flight.tail}")
            continue
        if flight.origin == flight.dest:
            problems.append(f"{flight.flight_no} departs and lands at {flight.origin}")
        if flight.pax_booked > tail.seats:
            problems.append(f"{flight.flight_no} has more passengers than {tail.tail} has seats")
        chains[flight.tail].append(flight)
    for tail, chain in chains.items():
        for before, after in pairwise(chain):
            if before.dest != after.origin:
                problems.append(
                    f"{tail}: {before.flight_no} lands where {after.flight_no} does not start"
                )
            if before.std_min + before.block_min > after.std_min:
                problems.append(
                    f"{tail}: {after.flight_no} departs before {before.flight_no} lands"
                )
    return problems
