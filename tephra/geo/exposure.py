"""Which tracked flights enter a hazard cone if they hold their current track and level.

This is a straight-line projection, not a flight-plan prediction: it says what happens
"if current track and level are held", which is how the Wall and the advisories word it.
"""

import math
from collections.abc import Sequence
from datetime import datetime
from typing import Final, NamedTuple

from tephra.geo.cone import AreaGeometry, geometry_entries
from tephra.geo.fuel import category_for_type, hold_line
from tephra.geo.units import destination_point, kt_to_km_per_min, unwrap_lon
from tephra.models import Aircraft, ExposedFlight, HazardCone, Position

MIN_MOVING_GS_KT: Final = 50.0
"""Slower targets (taxiing, hovering, bad data) are checked where they are, not projected."""


class Crossing(NamedTuple):
    """Where one airline target's projected track first meets an area within its band."""

    target: Aircraft
    band: tuple[int, int]
    step: int
    entry: tuple[float, float]
    path: list[Position]


def extrapolate(
    aircraft: Aircraft, minutes: int, *, step_min: int = 1
) -> list[tuple[float, float]]:
    """``(lat, lon)`` every ``step_min`` minutes along the great circle of the current track."""
    return _project(aircraft, start_min=0.0, minutes=minutes, step_min=step_min)


def find_exposed(
    cone: HazardCone,
    aircraft: Sequence[Aircraft],
    at: datetime,
    *,
    lookahead_min: int,
    vertical_margin_ft: int,
    hold_minutes: int,
) -> list[ExposedFlight]:
    """``vertical_margin_ft`` and ``hold_minutes`` come from the operator policy."""
    if cone.geometry is None:
        return []
    crossings = find_crossings(
        cone.geometry,
        cone.base_ft,
        cone.top_ft,
        aircraft,
        at,
        lookahead_min=max(0, min(int(cone.horizon_h * 60), lookahead_min)),
        vertical_margin_ft=vertical_margin_ft,
    )
    exposed = [_exposed_flight(crossing, cone, hold_minutes) for crossing in crossings]
    return sorted(exposed, key=lambda flight: (flight.minutes_to_entry, flight.hex))


def find_crossings(
    geometry: AreaGeometry,
    base_ft: int,
    top_ft: int,
    aircraft: Sequence[Aircraft],
    at: datetime,
    *,
    lookahead_min: int,
    vertical_margin_ft: int,
) -> list[Crossing]:
    """Airline targets whose track, held for ``lookahead_min`` minutes from ``at``, meets
    ``geometry`` while their level band is within the area's band widened by the margin."""
    hazard_low = base_ft - vertical_margin_ft
    hazard_high = top_ft + vertical_margin_ft
    candidates: list[tuple[Aircraft, tuple[int, int], list[tuple[float, float]]]] = []
    for target in aircraft:
        if not target.airline or target.alt_baro_ft is None:
            continue
        band = _level_band(target.alt_baro_ft, target.nav_altitude_mcp_ft)
        if band[1] < hazard_low or band[0] > hazard_high:
            continue
        # A position report is up to a poll interval old (longer in REPLAY). Projecting from
        # where the target is at `at` makes minutes_to_entry count from `at`; a report older
        # than the lookahead says nothing about where the target is now.
        age_min = (at - target.observed_at).total_seconds() / 60.0
        if age_min > lookahead_min:
            continue
        start = max(age_min, 0.0)
        candidates.append((target, band, _project(target, start_min=start, minutes=lookahead_min)))
    entries = geometry_entries(geometry, [points for _, _, points in candidates])
    return [
        Crossing(target, band, entry[0], entry[1], _entry_path(target, points, entry))
        for (target, band, points), entry in zip(candidates, entries, strict=True)
        if entry is not None
    ]


def _project(
    aircraft: Aircraft, *, start_min: float, minutes: int, step_min: int = 1
) -> list[tuple[float, float]]:
    if step_min <= 0:
        raise ValueError("step_min must be positive")
    gs_kt, track_deg = _finite(aircraft.gs_kt), _finite(aircraft.track_deg)
    if gs_kt is None or track_deg is None or gs_kt < MIN_MOVING_GS_KT:
        return [(aircraft.lat, aircraft.lon)]
    km_per_min = kt_to_km_per_min(gs_kt)
    return [
        destination_point(aircraft.lat, aircraft.lon, track_deg, km_per_min * (start_min + t))
        for t in range(0, max(minutes, 0) + 1, step_min)
    ]


def _level_band(alt_baro_ft: int, nav_altitude_mcp_ft: int | None) -> tuple[int, int]:
    """Pressure altitude widened to the selected altitude it climbs or descends to."""
    if nav_altitude_mcp_ft is None:
        return alt_baro_ft, alt_baro_ft
    return min(alt_baro_ft, nav_altitude_mcp_ft), max(alt_baro_ft, nav_altitude_mcp_ft)


def _finite(value: float | None) -> float | None:
    """A reported speed or track, or None for a missing, NaN or infinite one."""
    return value if value is not None and math.isfinite(value) else None


def _entry_path(
    target: Aircraft, points: list[tuple[float, float]], entry: tuple[int, tuple[float, float]]
) -> list[Position]:
    step, (entry_lat, entry_lon) = entry
    path: list[Position] = [(target.lon, target.lat)]
    for lat, lon in [*points[:step], (entry_lat, entry_lon)]:
        position = (unwrap_lon(lon, target.lon), lat)
        if position != path[-1]:
            path.append(position)
    if len(path) == 1:
        path.append(path[0])  # a GeoJSON LineString needs two positions
    return path


def _exposed_flight(crossing: Crossing, cone: HazardCone, hold_minutes: int) -> ExposedFlight:
    target = crossing.target
    entry_lat, entry_lon = crossing.entry
    category = category_for_type(target.type_icao)
    return ExposedFlight(
        id=f"{target.hex}:{cone.volcano_id}",
        hex=target.hex,
        callsign=target.callsign,
        proxy_flight=target.proxy_flight,
        type_icao=target.type_icao,
        category=category,
        lat=target.lat,
        lon=target.lon,
        alt_baro_ft=target.alt_baro_ft,
        nav_altitude_mcp_ft=target.nav_altitude_mcp_ft,
        gs_kt=_finite(target.gs_kt),
        track_deg=_finite(target.track_deg),
        observed_at=target.observed_at,
        source_id=target.source_id,
        volcano_id=cone.volcano_id,
        cone_id=cone.id,
        inside_now=crossing.step == 0,
        minutes_to_entry=crossing.step,
        entry_lat=entry_lat,
        entry_lon=entry_lon,
        aircraft_band_ft=crossing.band,
        hazard_band_ft=(cone.base_ft, cone.top_ft),
        path=crossing.path,
        hold=hold_line(category, minutes=hold_minutes),
    )
