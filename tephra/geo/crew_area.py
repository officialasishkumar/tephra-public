"""The caution area drawn from a crew (pilot) report of ash, and how it relates to the
official areas.

The shape follows the precautionary danger area of the ICAO EUR/NAT Volcanic Ash Contingency
Plan (EUR Doc 019 / NAT Doc 006 Part II, Ed. 2.0.0, 3.1.8 b) i)): a circle, extended downwind
by half an hour of wind when the wind is above 30 kt. Here it is centred on the reported
position instead of a volcano, and every number comes from the operator policy. The area only
ever adds caution: nothing here shrinks or replaces an official area, and the official areas
never shrink it.
"""

import math
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Final, Literal, NamedTuple

import shapely
from shapely.geometry import MultiPoint

from tephra.geo.cone import geometry_to_shape, shape_to_geometry
from tephra.geo.units import (
    deg_to_compass,
    destination_point,
    ft_to_fl,
    nm_to_km,
    unwrap_lon,
)
from tephra.models import GeoPolygon, OfficialLayer, WindLevel, WindProfile
from tephra.util import timeutil

__all__ = [
    "CIRCLE_SLACK",
    "CIRCLE_STEPS",
    "WIND_PROFILE_SLACK",
    "AreaRelation",
    "StretchWind",
    "area_polygon",
    "circle_ring",
    "pick_wind",
    "relation_to_official",
    "stretch_note",
]

CIRCLE_STEPS: Final = 64
"""Vertices of the circle; the polygon is circumscribed, so it contains the true circle."""

CIRCLE_SLACK: Final = 1.001
"""Extra reach for the vertices: the edges are straight in longitude and latitude, not on the
sphere, and without it the true circle pokes out of them by up to a metre. Checked to 60 deg
latitude and 250 NM radius: 0.1 % more reach (about 110 m at 60 NM) keeps all of it inside."""

WIND_PROFILE_SLACK: Final = timedelta(minutes=60)
"""The hourly wind profile used must be within this long of the observation time."""


class StretchWind(NamedTuple):
    """The wind the stretch was judged on, and where it came from."""

    level: WindLevel
    source_id: str
    valid_at: datetime


class AreaRelation(NamedTuple):
    relation: Literal["COVERED", "OVERLAPS", "OUTSIDE"]
    covered_by: list[str]
    """Official layer ids whose union covers the area, laterally and vertically (COVERED)"""


def circle_ring(lat: float, lon: float, radius_km: float) -> list[tuple[float, float]]:
    """``(lon, lat)`` vertices of a polygon whose edges lie outside the circle: each vertex
    sits at ``radius / cos(pi / n)`` (plus :data:`CIRCLE_SLACK`), so the polygon contains the
    whole circle."""
    reach = radius_km / math.cos(math.pi / CIRCLE_STEPS) * CIRCLE_SLACK
    ring: list[tuple[float, float]] = []
    for i in range(CIRCLE_STEPS):
        vertex_lat, vertex_lon = destination_point(lat, lon, 360.0 * i / CIRCLE_STEPS, reach)
        ring.append((unwrap_lon(vertex_lon, lon), vertex_lat))
    return ring


def area_polygon(
    lat: float,
    lon: float,
    radius_nm: float,
    *,
    stretch_nm: float = 0.0,
    toward_deg: float = 0.0,
) -> GeoPolygon:
    """The circle around the report, or the hull of it and the same circle moved
    ``stretch_nm`` downwind (toward ``toward_deg``)."""
    radius_km = nm_to_km(radius_nm)
    points = circle_ring(lat, lon, radius_km)
    if stretch_nm > 0:
        moved_lat, moved_lon = destination_point(lat, lon, toward_deg, nm_to_km(stretch_nm))
        points += [
            (unwrap_lon(x, lon), y)
            for x, y in circle_ring(moved_lat, unwrap_lon(moved_lon, lon), radius_km)
        ]
    geometry = shape_to_geometry(MultiPoint(points).convex_hull)
    if not isinstance(geometry, GeoPolygon):
        raise ValueError("a crew report area must be one polygon")
    return geometry


def pick_wind(
    profiles: Sequence[WindProfile], observed_at: datetime, base_ft: int, top_ft: int
) -> StretchWind | None:
    """The strongest wind at a pressure level inside the band, from the hourly profile nearest
    the observation time; with no level inside the band, the level nearest its middle. None
    when no profile lies within :data:`WIND_PROFILE_SLACK` of the observation."""
    near = [p for p in profiles if abs(p.valid_at - observed_at) <= WIND_PROFILE_SLACK and p.levels]
    if not near:
        return None
    profile = min(near, key=lambda p: (abs(p.valid_at - observed_at), p.valid_at))
    inside = [level for level in profile.levels if base_ft <= level.flight_level * 100 <= top_ft]
    if inside:
        level = max(inside, key=lambda item: (item.speed_kt, -item.flight_level))
    else:
        middle_fl = ft_to_fl((base_ft + top_ft) / 2)
        level = min(
            profile.levels,
            key=lambda item: (abs(item.flight_level - middle_fl), item.flight_level),
        )
    return StretchWind(level, profile.provenance.source_id, profile.valid_at)


def stretch_note(
    wind: StretchWind | None,
    *,
    threshold_kt: int,
    stretch_nm: float,
    wind_place: str,
    no_wind_reason: str,
) -> str:
    """Why the area was stretched, and how far, or why not. ``wind_place`` says where the
    wind profile is from (the report position, or a volcano's recorded profile)."""
    if wind is None:
        return f"Not stretched: wind not known ({no_wind_reason})"
    level = wind.level
    speed, source = round(level.speed_kt), round(level.from_deg)
    at = f"{speed} kt from {source:03d} at FL{level.flight_level:03d}"
    when = f"{timeutil.hhmmz(wind.valid_at)} profile {wind_place}"
    if stretch_nm <= 0:
        return f"Not stretched: wind {at} ({when}) is not above {threshold_kt} kt"
    toward = deg_to_compass(level.toward_deg)
    return f"Stretched {stretch_nm:.0f} NM toward {toward}: wind {at} ({when})"


def relation_to_official(
    polygon: GeoPolygon, base_ft: int, top_ft: int, layers: Sequence[OfficialLayer], at: datetime
) -> AreaRelation:
    """COVERED when the official layers valid at ``at`` whose band spans the area's band
    together contain it; OUTSIDE when no valid layer meets it both laterally and vertically;
    OVERLAPS otherwise. A display state only: the area's geometry never changes."""
    valid = [layer for layer in layers if layer.is_valid(at)]
    ref_lon = polygon.coordinates[0][0][0]
    area = geometry_to_shape(polygon, ref_lon=ref_lon)
    spanning = [layer for layer in valid if layer.base_ft <= base_ft and layer.top_ft >= top_ft]
    if spanning:
        shapes = [geometry_to_shape(layer.polygon, ref_lon=ref_lon) for layer in spanning]
        union = shapely.union_all(shapes)
        if union.covers(area):
            return AreaRelation("COVERED", sorted({layer.source_id for layer in spanning}))
    meets = any(
        layer.base_ft <= top_ft
        and layer.top_ft >= base_ft
        and geometry_to_shape(layer.polygon, ref_lon=ref_lon).intersects(area)
        for layer in valid
    )
    return AreaRelation("OVERLAPS" if meets else "OUTSIDE", [])
