"""TEPHRA's labelled planning formula for the time and fuel cost of a hold, diversion or reroute.

This is a deliberately simple, flat burn rate per aircraft category, not airline
performance data. Every number it produces carries its formula, written by code, so the
dispatcher can see exactly how it was reached.
"""

import math
from typing import Final

from tephra.models import ActionKind, AircraftCategory, FuelLine

BURN_KG_PER_MIN: Final[dict[AircraftCategory, float]] = {
    AircraftCategory.LIGHT: 5,
    AircraftCategory.TURBOPROP: 12,
    AircraftCategory.REGIONAL_JET: 25,
    AircraftCategory.NARROWBODY: 42,
    AircraftCategory.WIDEBODY: 110,
    AircraftCategory.UNKNOWN: 42,
}

ASSUMED_GS_KT: Final = 250.0
MIN_TRUSTED_GS_KT: Final = 150.0
"""Below this the ADS-B ground speed (climb, descent, a hold) says little about a diversion."""

_TYPE_CATEGORY: Final[dict[str, AircraftCategory]] = {
    **dict.fromkeys(("C152", "C172", "C182", "C206", "C208", "P28A", "P28B", "P28R", "DA40",
                     "DA42", "SR22"),
                    AircraftCategory.LIGHT),
    **dict.fromkeys(("AT43", "AT45", "AT46", "AT72", "AT75", "AT76", "DH8A", "DH8B", "DH8C",
                     "DH8D", "DHC6", "SF34", "B190", "JS41", "Y12"),
                    AircraftCategory.TURBOPROP),
    **dict.fromkeys(("CRJ2", "CRJ7", "CRJ9", "CRJX", "E135", "E145", "E170", "E75L", "E75S",
                     "E190", "E195", "E290", "E295", "BCS1", "BCS3", "SU95", "AJ27"),
                    AircraftCategory.REGIONAL_JET),
    **dict.fromkeys(("A318", "A319", "A320", "A321", "A19N", "A20N", "A21N", "B736", "B737",
                     "B738", "B739", "B37M", "B38M", "B39M", "B3XM", "B752", "B753", "C919"),
                    AircraftCategory.NARROWBODY),
    **dict.fromkeys(("A306", "A30B", "A310", "A332", "A333", "A338", "A339", "A342", "A343",
                     "A345", "A346", "A359", "A35K", "A388", "B744", "B748", "B762", "B763",
                     "B764", "B772", "B773", "B77L", "B77W", "B778", "B779", "B788", "B789",
                     "B78X", "MD11"),
                    AircraftCategory.WIDEBODY),
}  # fmt: skip


def category_for_type(type_icao: str | None) -> AircraftCategory:
    if not type_icao:
        return AircraftCategory.UNKNOWN
    return _TYPE_CATEGORY.get(type_icao.strip().upper(), AircraftCategory.UNKNOWN)


def hold_line(category: AircraftCategory, *, minutes: int) -> FuelLine:
    """``minutes`` is the operator policy's hold length (``fuel.hold_min``)."""
    burn = BURN_KG_PER_MIN[category]
    fuel_kg = _ceil(minutes * burn)
    formula = f"HOLD {minutes} MIN x {_num(burn)} KG/MIN ({_rate_label(category)}) = {fuel_kg} KG"
    return FuelLine(
        action=ActionKind.HOLD,
        minutes=minutes,
        fuel_kg=fuel_kg,
        burn_kg_per_min=burn,
        category=category,
        formula=formula,
    )


def divert_line(
    category: AircraftCategory,
    *,
    alternate_icao: str,
    distance_nm: float,
    gs_kt: float | None,
    extra_minutes: int,
) -> FuelLine:
    """``extra_minutes`` is the operator policy's approach and landing allowance
    (``fuel.divert_extra_min``)."""
    burn = BURN_KG_PER_MIN[category]
    # The minutes come from the whole numbers the formula prints, so it reproduces exactly.
    distance = round(distance_nm)
    if gs_kt is None or not math.isfinite(gs_kt) or gs_kt < MIN_TRUSTED_GS_KT:
        speed, speed_text = ASSUMED_GS_KT, f"{_num(ASSUMED_GS_KT)} KT (ASSUMED)"
    else:
        speed = round(gs_kt)
        speed_text = f"{speed} KT"
    cruise_min = _ceil(distance / speed * 60.0)
    minutes = cruise_min + extra_minutes
    fuel_kg = _ceil(minutes * burn)
    formula = (
        f"DIVERT {alternate_icao} {distance} NM AT {speed_text} = {cruise_min} MIN"
        f" + {extra_minutes} MIN = {minutes} MIN x {_num(burn)} KG/MIN"
        f" ({_rate_label(category)}) = {fuel_kg} KG"
    )
    return FuelLine(
        action=ActionKind.DIVERT,
        minutes=minutes,
        fuel_kg=fuel_kg,
        burn_kg_per_min=burn,
        category=category,
        alternate_icao=alternate_icao,
        distance_nm=round(distance_nm, 1),
        formula=formula,
    )


def reroute_line(category: AircraftCategory, extra_min: float, extra_nm: float) -> FuelLine:
    """The extra time and distance of a lateral reroute over the present track (never negative)."""
    burn = BURN_KG_PER_MIN[category]
    distance = max(0, round(extra_nm))
    minutes = _ceil(max(0.0, extra_min))
    fuel_kg = _ceil(minutes * burn)
    formula = (
        f"REROUTE +{distance} NM = +{minutes} MIN x {_num(burn)} KG/MIN"
        f" ({_rate_label(category)}) = {fuel_kg} KG"
    )
    return FuelLine(
        action=ActionKind.REROUTE,
        minutes=minutes,
        fuel_kg=fuel_kg,
        burn_kg_per_min=burn,
        category=category,
        distance_nm=float(distance),
        formula=formula,
    )


def _rate_label(category: AircraftCategory) -> str:
    if category is AircraftCategory.UNKNOWN:
        return f"TYPE UNKNOWN, {AircraftCategory.NARROWBODY.value} RATE"
    return category.value


def _ceil(value: float) -> int:
    # Rounding to 6 places first keeps float noise (25.000000000000004) from adding a unit.
    return math.ceil(round(value, 6))


def _num(value: float) -> str:
    return str(round(value))
