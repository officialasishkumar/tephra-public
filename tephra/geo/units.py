"""Unit conversions and spherical-earth helpers.

Distances use a spherical earth of mean radius ``EARTH_RADIUS_KM``; over the few hundred
kilometres TEPHRA works with, the error against the ellipsoid is well under 0.5 %.
Bearings are degrees true, 0..360, clockwise from north.
"""

import math
import re
from datetime import datetime
from typing import Final

FT_PER_M: Final = 3.28084
KM_PER_NM: Final = 1.852
EARTH_RADIUS_KM: Final = 6371.0088

COMPASS_POINTS: Final[tuple[str, ...]] = (
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
)  # fmt: skip
_POINT_DEG: Final[dict[str, float]] = {name: i * 22.5 for i, name in enumerate(COMPASS_POINTS)}
_DIRECTION_WORDS: Final[dict[str, str]] = {
    "north": "N",
    "south": "S",
    "east": "E",
    "west": "W",
    "northeast": "NE",
    "northwest": "NW",
    "southeast": "SE",
    "southwest": "SW",
}
# Whole words only: a letter group glued to digits ("S0806") is a coordinate, not a direction.
_TOKEN = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]+(?![A-Za-z0-9])")
_APOSTROPHE = re.compile(r"['\u2019]")  # "cloud's" must not leave a stray "s" token
_WARD_SUFFIX = re.compile(r"wards?$")  # "eastward" moves east; "-erly" (where FROM) is not read


# --- linear units -----------------------------------------------------------------------


def ft_to_fl(ft: float) -> int:
    """Nearest flight level, halves rounded up (15,050 ft -> FL151)."""
    return math.floor(ft / 100.0 + 0.5)


def fl_to_ft(fl: float) -> int:
    return round(fl * 100)


def m_to_ft(m: float) -> float:
    return m * FT_PER_M


def ft_to_m(ft: float) -> float:
    return ft / FT_PER_M


def km_to_nm(km: float) -> float:
    return km / KM_PER_NM


def nm_to_km(nm: float) -> float:
    return nm * KM_PER_NM


def kt_to_km_per_min(kt: float) -> float:
    return kt * KM_PER_NM / 60.0


# --- great circle -----------------------------------------------------------------------


def normalize_lon(lon: float) -> float:
    """Longitude in [-180, 180)."""
    return (lon + 180.0) % 360.0 - 180.0


def unwrap_lon(lon: float, ref_lon: float) -> float:
    """``lon`` shifted by 360 when that brings it within 180 degrees of ``ref_lon``.

    Keeps a shape that straddles the antimeridian continuous for planar geometry. Values
    already within 180 degrees are returned untouched, bit for bit, so official polygon
    vertices are never perturbed in the usual (JAPAC) case.
    """
    if abs(lon - ref_lon) <= 180.0:
        return lon
    return lon - 360.0 if lon > ref_lon else lon + 360.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2.0 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def distance_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return km_to_nm(haversine_km(lat1, lon1, lat2, lon2))


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlmb = math.radians(lon2 - lon1)
    y = math.sin(dlmb) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlmb)
    return math.degrees(math.atan2(y, x)) % 360.0


def destination_point(
    lat: float, lon: float, bearing_deg: float, distance_km: float
) -> tuple[float, float]:
    """``(lat, lon)`` reached by following a great circle from the start; lon in [-180, 180)."""
    if distance_km == 0:
        return lat, lon
    delta = distance_km / EARTH_RADIUS_KM
    theta = math.radians(bearing_deg)
    phi1, lmb1 = math.radians(lat), math.radians(lon)
    sin_phi2 = math.sin(phi1) * math.cos(delta) + math.cos(phi1) * math.sin(delta) * math.cos(theta)
    phi2 = math.asin(max(-1.0, min(1.0, sin_phi2)))
    lmb2 = lmb1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(phi1),
        math.cos(delta) - math.sin(phi1) * sin_phi2,
    )
    return math.degrees(phi2), normalize_lon(math.degrees(lmb2))


# --- directions -------------------------------------------------------------------------


def bearing_diff_deg(a: float, b: float) -> float:
    """Smallest angle between two bearings, 0..180."""
    return abs((a - b + 180.0) % 360.0 - 180.0)


def sector_width_deg(bearing_from_deg: float, bearing_to_deg: float) -> float:
    """Clockwise sweep from the first bearing to the second; 0 -> 360 is a full circle."""
    width = (bearing_to_deg - bearing_from_deg) % 360.0
    if width == 0 and bearing_to_deg != bearing_from_deg:
        return 360.0
    return width


def deg_to_compass(deg: float) -> str:
    return COMPASS_POINTS[int(((deg % 360.0) + 11.25) // 22.5) % 16]


def compass_to_deg(text: str) -> float | None:
    """Direction of a compass phrase as feeds write it, or None if it names none.

    Accepts 16-point abbreviations written in capitals (``NE``, ``WSW``) and English words in
    any case, joined or not (``north east``, ``north-northeast``, ``to the east``). A phrase
    naming several directions (MAGMA's ``from northeast to east``) gives their circular
    mean, the centre of the span; opposite directions cancel and give None.
    """
    directions = [_POINT_DEG[name] for name in _direction_names(text)]
    if not directions:
        return None
    if len(directions) == 1:
        return directions[0]
    x = sum(math.cos(math.radians(d)) for d in directions)
    y = sum(math.sin(math.radians(d)) for d in directions)
    if math.hypot(x, y) < 1e-6 * len(directions):
        return None
    return round(math.degrees(math.atan2(y, x)) % 360.0, 1)


def _direction_names(text: str) -> list[str]:
    """16-point names in ``text``; adjacent direction words merge ("north east" -> NE)."""
    names: list[str] = []
    group: list[str] = []

    def flush() -> None:
        merged = "".join(group)
        if merged in _POINT_DEG:
            names.append(merged)
        else:
            names.extend(part for part in group if part in _POINT_DEG)
        group.clear()

    for token in _TOKEN.findall(_APOSTROPHE.sub("", text)):
        word = _DIRECTION_WORDS.get(_WARD_SUFFIX.sub("", token.lower()))
        if word is not None:
            group.append(word)
            continue
        flush()
        if token.isupper() and token in _POINT_DEG:
            names.append(token)
    flush()
    return names


# --- time -------------------------------------------------------------------------------


def solar_hour(lon: float, at: datetime) -> float:
    """Local mean solar time in hours, 0..24 (a coarse day/night flag for satellite use)."""
    utc_hours = at.hour + at.minute / 60.0 + at.second / 3600.0
    return (utc_hours + lon / 15.0) % 24.0
