"""The own fleet of an airline's own TEPHRA: which aircraft it checks against the ash, and the
name each of its flights goes by.

Empty by default, so every aircraft is checked and named by a fictional Ring of Fire Air number,
as the demo does. Set, it narrows only which aircraft enter exposure: the map, pushes and
crew-report lookups still see every aircraft, and no validator changes. It also names every
flight by the airline's own name for it (:meth:`FleetFilter.flight_name`), never an RFA number.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Final, Self

from pydantic import Field, ValidationError, ValidationInfo, field_validator, model_validator

from tephra.config import Settings
from tephra.models import (
    PUSH_SOURCE_PREFIX,
    Aircraft,
    OwnFleet,
    PushedFlightPlan,
    TephraModel,
    is_airline_callsign,
)

__all__ = ["ALL_AIRCRAFT", "FleetFilter", "OwnSchedule", "ScheduleError"]


class ScheduleError(ValueError):
    """The airline's flights.json or fleet.json cannot be read; startup stops, naming it."""


# --- the airline's own files (flights.json and fleet.json) ----------------------------------


class _Row(TephraModel):
    """One flight of the airline's flights.json; other keys (origin, pax_booked...) are kept by
    the push tool and the onboarding check, not here."""

    flight_no: str = Field(pattern=r"^[A-Z0-9]{3,8}$")
    std_min: int = Field(ge=0, le=2879, description="Minutes after the anchor day's midnight")
    block_min: int = Field(gt=0)
    tail: str | None = None
    callsign: str | None = Field(default=None, pattern=r"^[A-Z0-9]{2,8}$")
    days: str | None = Field(default=None, pattern=r"^[1-7]{1,7}$", description="SSIM weekdays")

    @field_validator("tail", "days", mode="before")
    @classmethod
    def _text(cls, value: object) -> object:
        return None if value is None else (str(value).strip().upper() or None)

    def flies_on(self, day: date) -> bool:
        return self.days is None or str(day.isoweekday()) in self.days


class _Header(TephraModel):
    anchor_utc_offset_h: float | None = Field(default=None, ge=-12, le=14)


class _Flights(TephraModel):
    header: _Header
    flights: list[_Row]

    @model_validator(mode="after")
    def _anchored(self) -> Self:
        if self.flights and self.header.anchor_utc_offset_h is None:
            raise ValueError("header.anchor_utc_offset_h is not set")
        return self


class _Tail(TephraModel):
    tail: str = Field(pattern=r"^[A-Z0-9-]{2,10}$")
    hex: str | None = Field(default=None, pattern=r"^[0-9a-f]{6}$")

    @field_validator("tail", "hex", mode="before")
    @classmethod
    def _tidy(cls, value: object, info: ValidationInfo) -> object:
        if not isinstance(value, str):
            return value
        value = value.strip()
        return value.lower() if info.field_name == "hex" else value.upper()


class _Fleet(TephraModel):
    tails: list[_Tail]


@dataclass(frozen=True, slots=True)
class _Leg:
    flight: str
    std: datetime
    sta: datetime


def _flying(std: datetime | None, sta: datetime | None, at: datetime) -> bool:
    """Departed by ``at`` and not later than one block time after the scheduled arrival (a
    delay as long as the flight itself). Before the scheduled departure a flight is not
    taken to be flying: the name then falls to the registration, which is never wrong."""
    if std is None:
        return True
    if at < std:
        return False
    return sta is None or at <= sta + (sta - std)


@dataclass(frozen=True, slots=True)
class OwnSchedule:
    """The airline's schedule (``TEPHRA_AIRLINE_SCHEDULE``) and fleet (``TEPHRA_AIRLINE_FLEET``),
    read once at startup."""

    offset_h: float = 0.0
    rows: tuple[_Row, ...] = ()
    registrations: dict[str, str] = field(default_factory=dict)
    """hex -> registration"""

    def registration(self, hex_id: str) -> str | None:
        return self.registrations.get(hex_id)

    def flight_at(self, hex_id: str, callsign: str | None, at: datetime) -> str | None:
        """The scheduled flight the aircraft flies at ``at``: a row of its registration or of
        its callsign, departed and not long past its arrival; the latest departure wins. Two
        flights departing at the same minute name nothing (the file cannot say which)."""
        tail = self.registration(hex_id)
        legs = [
            leg
            for row in self.rows
            if (tail is not None and row.tail == tail) or (callsign and row.callsign == callsign)
            for leg in self._legs(row, at)
            if _flying(leg.std, leg.sta, at)
        ]
        if not legs:
            return None
        latest = max(leg.std for leg in legs)
        flights = {leg.flight for leg in legs if leg.std == latest}
        return flights.pop() if len(flights) == 1 else None

    def _legs(self, row: _Row, at: datetime) -> list[_Leg]:
        """The row on each service day whose flight can be in the air at ``at``: ``std_min``
        reaches into the next day, and a late flight runs one block time past its arrival."""
        zone = timezone(timedelta(hours=self.offset_h))
        today = at.astimezone(zone).date()
        legs = []
        for back in range(3):
            day = today - timedelta(days=back)
            if not row.flies_on(day):
                continue
            midnight = datetime(day.year, day.month, day.day, tzinfo=zone)
            std = midnight + timedelta(minutes=row.std_min)
            legs.append(_Leg(row.flight_no, std, std + timedelta(minutes=row.block_min)))
        return legs

    @classmethod
    def from_registrations(cls, registrations: Mapping[str, str]) -> Self:
        """A hosted airline's fleet from its onboarding answers (hex -> registration), with
        no schedule: its flights are named by pushed flight plans, callsigns and
        registrations (uploading flights.json is not built on hosted TEPHRA)."""
        return cls(registrations={hex_id.lower(): tail for hex_id, tail in registrations.items()})

    @classmethod
    def load(cls, data_dir: Path, schedule_file: str | None, fleet_file: str | None) -> Self:
        flights = _read(data_dir, schedule_file, _Flights) if schedule_file else None
        fleet = _read(data_dir, fleet_file, _Fleet) if fleet_file else None
        return cls(
            offset_h=(flights.header.anchor_utc_offset_h or 0.0) if flights else 0.0,
            rows=tuple(flights.flights) if flights else (),
            registrations={t.hex: t.tail for t in fleet.tails if t.hex} if fleet else {},
        )


def _read[M: TephraModel](data_dir: Path, name: str, model: type[M]) -> M:
    path = data_dir / name
    try:
        return model.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, ValidationError) as exc:
        raise ScheduleError(f"{path}: {exc}") from exc


# --- the filter and the names ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FleetFilter:
    prefixes: frozenset[str] = frozenset()
    hexes: frozenset[str] = frozenset()
    icao: str | None = None
    """The airline's ICAO designator (``TEPHRA_AIRLINE_ICAO``): its callsigns name its flights"""
    schedule: OwnSchedule = field(default_factory=OwnSchedule)

    @property
    def everyone(self) -> bool:
        return not (self.prefixes or self.hexes)

    @property
    def designators(self) -> frozenset[str]:
        """The callsign prefixes that are the airline's own: the listed ones and its ICAO."""
        return self.prefixes | ({self.icao} if self.icao else set())

    def admits(self, aircraft: Aircraft) -> bool:
        """Pushed positions are the airline's own by construction; an ADS-B target counts when
        its address is listed or its airline-style callsign starts with a listed prefix."""
        if aircraft.source_id.startswith(PUSH_SOURCE_PREFIX):
            return True
        return self.admits_flight(aircraft.hex, aircraft.callsign)

    def admits_flight(self, hex_id: str, callsign: str | None) -> bool:
        """:meth:`admits` for a flight known by its address and callsign only."""
        if self.everyone or hex_id in self.hexes:
            return True
        return is_airline_callsign(callsign) and (callsign or "")[:3] in self.prefixes

    def own_fleet(self) -> OwnFleet | None:
        if self.everyone:
            return None
        return OwnFleet(prefixes=sorted(self.prefixes), hex_count=len(self.hexes))

    def flight_name(
        self,
        hex_id: str,
        callsign: str | None,
        at: datetime,
        *,
        own: bool,
        plans: Sequence[PushedFlightPlan] = (),
    ) -> str:
        """What an airline's own TEPHRA calls a flight (``own``: :meth:`admits` holds). Its own
        flight: the callsign when it is an airline-style callsign of the airline (a listed
        prefix or its ICAO designator); else the flight number of a pushed flight plan for it
        that is flying now; else its flight in the airline's schedule; else its registration;
        else what ADS-B says (callsign, then address). Another airline's aircraft goes by
        what ADS-B says. Never a fictional RFA number."""
        seen = callsign or hex_id.upper()
        if not own:
            return seen
        if is_airline_callsign(callsign) and seen[:3] in self.designators:
            return seen
        for plan in plans:
            if _flying(plan.std, plan.sta, at):
                return plan.flight
        return (
            self.schedule.flight_at(hex_id, callsign, at)
            or self.schedule.registration(hex_id)
            or seen
        )

    def named(
        self, aircraft: Aircraft, at: datetime, plans: Sequence[PushedFlightPlan] = ()
    ) -> Aircraft:
        """``aircraft`` under its :meth:`flight_name`; unchanged while every aircraft is
        checked (the demo's RFA numbers)."""
        if self.everyone:
            return aircraft
        own = self.admits(aircraft)
        name = self.flight_name(aircraft.hex, aircraft.callsign, at, own=own, plans=plans)
        return aircraft.named(name)

    @classmethod
    def from_settings(cls, settings: Settings, schedule: OwnSchedule | None = None) -> Self:
        """Reads the schedule and fleet files when set, unless ``schedule`` is given (a hosted
        airline's, :meth:`OwnSchedule.from_registrations`); :class:`ScheduleError` stops
        startup."""
        if schedule is None:
            schedule = OwnSchedule.load(
                settings.data_dir, settings.airline_schedule, settings.airline_fleet
            )
        return cls(
            prefixes=settings.fleet_prefixes,
            hexes=settings.fleet_hexes,
            icao=settings.airline_icao,
            schedule=schedule,
        )


ALL_AIRCRAFT: Final = FleetFilter()
