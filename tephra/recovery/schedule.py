"""Loads the synthetic RFA schedule (``data/rfa/``) and rolls it over calendar days.

The file holds one template day, in minutes after the start of that day. The schedule the
solver sees is a window of ``OPERATING_DAYS`` consecutive days that starts with the operating
day holding the clock, so a late-evening clock still has the whole next day to re-plan. Every
aircraft's rotation returns to where it started, so each later day repeats the template one
``MINUTES_PER_DAY`` later, under the same flight numbers and a new service date.
"""

import math
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from tephra.models import TephraModel
from tephra.recovery.models import (
    MINUTES_PER_DAY,
    RfaCrew,
    RfaFlight,
    RfaTail,
    RfaTemplateFlight,
    Schedule,
    ScheduleHeader,
)

__all__ = [
    "OPERATING_DAYS",
    "SCHEDULE_DIR",
    "ScheduleError",
    "block_minutes",
    "load_schedule",
    "operating_day",
]

SCHEDULE_DIR: Final = "rfa"
OPERATING_DAYS: Final = 2
"""The clock's operating day and the next one."""
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
    flights: list[RfaTemplateFlight]


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
    day = operating_day(at, flights.header).date()
    schedule = Schedule(
        day=day,
        header=flights.header,
        tails=fleet.tails,
        crews=crews.crews,
        flights=_window(flights.flights, day),
    )
    problems = _problems(schedule)
    if problems:
        raise ScheduleError("; ".join(problems[:5]))
    return schedule


def _window(template: list[RfaTemplateFlight], first_day: date) -> list[RfaFlight]:
    flights = [
        RfaFlight(
            **flight.model_dump(),
            service_date=first_day + timedelta(days=offset),
            day_offset=offset,
        ).model_copy(update={"std_min": flight.std_min + offset * MINUTES_PER_DAY})
        for offset in range(OPERATING_DAYS)
        for flight in template
    ]
    return sorted(flights, key=lambda f: (f.std_min, f.flight_no))


def _problems(schedule: Schedule) -> list[str]:
    tails = {tail.tail: tail for tail in schedule.tails}
    crews = {crew.crew_id for crew in schedule.crews}
    numbers = [flight.key for flight in schedule.flights]
    problems = [
        f"tail {tail.tail} has unknown crew {tail.crew_id}"
        for tail in schedule.tails
        if tail.crew_id not in crews
    ]
    if len(set(numbers)) != len(numbers):
        problems.append("duplicate flight keys")
    chains: dict[str, list[RfaFlight]] = defaultdict(list)
    for flight in schedule.flights:
        tail = tails.get(flight.tail)
        if tail is None:
            problems.append(f"{flight.key} is on unknown tail {flight.tail}")
            continue
        if flight.origin == flight.dest:
            problems.append(f"{flight.key} departs and lands at {flight.origin}")
        if flight.pax_booked > tail.seats:
            problems.append(f"{flight.key} has more passengers than {tail.tail} has seats")
        chains[flight.tail].append(flight)
    for tail, chain in chains.items():
        for before, after in pairwise(chain):
            if before.dest != after.origin:
                problems.append(f"{tail}: {before.key} lands where {after.key} does not start")
            if before.std_min + before.block_min > after.std_min:
                problems.append(f"{tail}: {after.key} departs before {before.key} lands")
    return problems
