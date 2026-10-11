"""Which airports the volcanic ash closes, and for how long.

An airport is closed while a hazard area (the TEPHRA cone, or an official layer) that reaches
any level from the surface to FL100 comes within the policy's radius of it, or while its TAF
carries ``VA`` or its latest METAR reports ``VA``. The window is the hazard's validity; the
reason text and the source ids are written by code.
"""

import math
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime

import numpy as np
import shapely
from shapely.geometry.base import BaseGeometry

from tephra.geo.cone import geometry_to_shape
from tephra.geo.units import fl_to_ft, nm_to_km
from tephra.models import Airport, HazardCone, Metar, OfficialLayer, OperatorPolicy, Taf
from tephra.recovery.models import Closure

__all__ = ["find_closures", "merge_closures"]

SURFACE_BAND_TOP_FL = 100
"""The levels a runway user meets: surface up to this flight level (research/18d)."""
_KM_PER_DEG = 111.32


def find_closures(
    airports: Iterable[Airport],
    *,
    cones: Sequence[HazardCone],
    layers: Sequence[OfficialLayer],
    tafs: Mapping[str, Taf],
    metars: Mapping[str, Metar],
    at: datetime,
    horizon_end: datetime,
    policy: OperatorPolicy,
) -> list[Closure]:
    """Closures that are open at ``at`` or start later, merged per airport, by start time."""
    radius_km = nm_to_km(policy.recovery.airport_closure_radius_nm.value)
    found: list[Closure] = []
    for airport in airports:
        found.extend(_hazard_closures(airport, cones, layers, at, radius_km, policy))
        found.extend(_forecast_closures(airport, tafs.get(airport.icao), at))
        found.extend(_observed_closure(airport, metars.get(airport.icao), at, horizon_end))
    return merge_closures(found)


def _hazard_closures(
    airport: Airport,
    cones: Sequence[HazardCone],
    layers: Sequence[OfficialLayer],
    at: datetime,
    radius_km: float,
    policy: OperatorPolicy,
) -> list[Closure]:
    top_ft = fl_to_ft(SURFACE_BAND_TOP_FL)
    found: list[Closure] = []
    for cone in cones:
        if cone.geometry is None or cone.base_ft > top_ft or cone.valid_to <= at:
            continue
        if _within(airport, geometry_to_shape(cone.geometry, ref_lon=airport.lon), radius_km):
            found.append(_cone_closure(airport, cone, policy))
    for layer in layers:
        if layer.base_ft > top_ft or layer.valid_to <= at:
            continue
        if _within(airport, geometry_to_shape(layer.polygon, ref_lon=airport.lon), radius_km):
            found.append(
                _layer_closure(airport, layer, policy.recovery.airport_closure_radius_nm.value)
            )
    return found


def merge_closures(closures: Iterable[Closure]) -> list[Closure]:
    """Overlapping or touching windows of one airport become one, reasons and sources joined."""
    merged: list[Closure] = []
    for closure in sorted(closures, key=lambda c: (c.icao, c.start, c.end)):
        last = merged[-1] if merged else None
        if last is not None and last.icao == closure.icao and closure.start <= last.end:
            merged[-1] = last.model_copy(
                update={
                    "end": max(last.end, closure.end),
                    "reason": _join(last.reason, closure.reason),
                    "source_ids": sorted({*last.source_ids, *closure.source_ids}),
                    "open_ended": last.open_ended or closure.open_ended,
                    "basis": sorted({*last.basis, *closure.basis}),
                    "base_ft": _lowest(last.base_ft, closure.base_ft),
                    "top_ft": _highest(last.top_ft, closure.top_ft),
                    "radius_nm": last.radius_nm
                    if last.radius_nm is not None
                    else closure.radius_nm,
                }
            )
        else:
            merged.append(closure)
    return sorted(merged, key=lambda c: (c.start, c.icao))


def _lowest(first: int | None, second: int | None) -> int | None:
    return second if first is None else first if second is None else min(first, second)


def _highest(first: int | None, second: int | None) -> int | None:
    return second if first is None else first if second is None else max(first, second)


def _join(first: str, second: str) -> str:
    return first if second in first.split("; ") else f"{first}; {second}"


def _within(airport: Airport, shape: BaseGeometry, radius_km: float) -> bool:
    """True when the shape is within ``radius_km`` of the airport (local flat projection)."""
    scale = math.cos(math.radians(airport.lat))
    origin = np.array([airport.lon, airport.lat])
    local = shapely.transform(shape, lambda xy: (xy - origin) * [scale, 1.0] * _KM_PER_DEG)
    return bool(shapely.distance(local, shapely.Point(0.0, 0.0)) <= radius_km)


def _cone_closure(airport: Airport, cone: HazardCone, policy: OperatorPolicy) -> Closure:
    radius = policy.recovery.airport_closure_radius_nm.value
    return Closure(
        icao=airport.icao,
        start=cone.created_at,
        end=cone.valid_to,
        reason=f"HAZARD CONE {cone.id} WITHIN {radius} NM OF {airport.icao}",
        source_ids=[cone.id, *cone.official_source_ids],
        basis=["HAZARD"],
        base_ft=cone.base_ft,
        top_ft=cone.top_ft,
        radius_nm=radius,
    )


def _layer_closure(airport: Airport, layer: OfficialLayer, radius_nm: float) -> Closure:
    return Closure(
        icao=airport.icao,
        start=layer.valid_from,
        end=layer.valid_to,
        reason=f"{layer.label} NEAR {airport.icao}",
        source_ids=[layer.source_id],
        basis=["OFFICIAL"],
        base_ft=layer.base_ft,
        top_ft=layer.top_ft,
        radius_nm=radius_nm,
    )


def _forecast_closures(airport: Airport, taf: Taf | None, at: datetime) -> list[Closure]:
    if taf is None:
        return []
    return [
        Closure(
            icao=airport.icao,
            start=period.valid_from,
            end=period.valid_to,
            reason=f"TAF {airport.icao} FORECASTS VA",
            source_ids=[taf.provenance.source_id],
            basis=["TAF"],
        )
        for period in taf.periods
        if period.valid_to > at and any(_is_va(token) for token in period.weather)
    ]


def _observed_closure(
    airport: Airport, metar: Metar | None, at: datetime, horizon_end: datetime
) -> list[Closure]:
    if metar is None or not any(_is_va(token) for token in metar.weather):
        return []
    return [
        Closure(
            icao=airport.icao,
            start=min(metar.observed_at, at),
            end=horizon_end,
            reason=f"METAR {airport.icao} REPORTS VA; NO END IS PUBLISHED",
            source_ids=[metar.provenance.source_id],
            open_ended=True,
            basis=["METAR"],
        )
    ]


def _is_va(token: str) -> bool:
    return token.lstrip("+-").removeprefix("VC") == "VA"
