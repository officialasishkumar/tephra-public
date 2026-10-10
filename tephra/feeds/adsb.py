"""Aircraft positions from the adsb.lol v2 point API (readsb JSON).

adsb.lol asks for at least one second between calls. :class:`HttpSource` serialises and
spaces requests to ``api.adsb.lol`` (>= 1.1 s) and backs off on 420/429, so this module
only has to call points one after another. Data is ODbL 1.0: the UI credits
"Aircraft: adsb.lol (ODbL 1.0)". Registrations (``r``) are never kept.

A point that fails must not look like an empty sky: adsb.lol rate-limits bursts (the first
live run got HTTP 429 on the fourth call of every pass), and the aircraft near that point
would simply vanish. :func:`fetch_aircraft` therefore tries every point and then raises
:class:`AdsbPointsFailed`, which carries the snapshots that did come back.
"""

import logging
import math
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any, Final

from tephra.feeds.base import FetchError, FetchResult, Source
from tephra.geo.units import distance_nm
from tephra.models import (
    AdsbQueryPoint,
    AdsbSnapshot,
    Aircraft,
    FeedId,
    Region,
    Volcano,
    make_source_id,
)
from tephra.util import timeutil

__all__ = [
    "ADSB_POINT_URL",
    "MAX_CACHED_COPY_AGE_S",
    "AdsbPointsFailed",
    "fetch_aircraft",
    "merge_aircraft",
    "parse_adsb",
    "point_url",
    "query_points",
]

logger = logging.getLogger(__name__)

ADSB_POINT_URL: Final = "https://api.adsb.lol/v2/point/{lat}/{lon}/{radius_nm}"
MAX_RADIUS_NM: Final = 250
VOLCANO_POINT_SPACING_NM: Final = 50.0
"""A volcano query point closer than this to one already chosen adds little coverage."""
MAX_CACHED_COPY_AGE_S: Final = 120
"""A last-good copy older than this (four 30 s passes) no longer stands for current traffic.

Its positions are older still: readsb itself stops reporting a position after 60 s.
"""


class AdsbPointsFailed(FetchError):
    """Some query points gave no usable answer; ``snapshots`` are the points that did."""

    def __init__(
        self,
        failed: Sequence[tuple[AdsbQueryPoint, str]],
        snapshots: Sequence[AdsbSnapshot],
        *,
        tried: int,
    ) -> None:
        details = "; ".join(
            f"{point.lat:.3f},{point.lon:.3f}/{point.radius_nm}nm: {reason}"
            for point, reason in failed
        )
        super().__init__(
            point_url(failed[0][0]),
            FeedId.ADSB,
            f"{len(failed)} of {tried} adsb.lol points failed ({details})",
        )
        self.failed_points = [point for point, _ in failed]
        self.snapshots = list(snapshots)


def point_url(point: AdsbQueryPoint) -> str:
    return ADSB_POINT_URL.format(
        lat=f"{point.lat:.3f}", lon=f"{point.lon:.3f}", radius_nm=point.radius_nm
    )


def query_points(
    region: Region, volcanoes: Sequence[Volcano], radius_nm: int
) -> list[AdsbQueryPoint]:
    """The region's fixed points plus one circle per active volcano, without near-duplicates."""
    chosen = list(region.adsb_points)
    radius = max(1, min(radius_nm, MAX_RADIUS_NM))
    for volcano in volcanoes:
        if any(
            distance_nm(volcano.lat, volcano.lon, point.lat, point.lon) < VOLCANO_POINT_SPACING_NM
            for point in chosen
        ):
            continue
        chosen.append(
            AdsbQueryPoint(lat=round(volcano.lat, 3), lon=round(volcano.lon, 3), radius_nm=radius)
        )
    return chosen


def parse_adsb(result: FetchResult, query: AdsbQueryPoint) -> AdsbSnapshot:
    """A bad response raises ValueError, which fails this point and no other; any other
    exception would end the whole pass in :func:`fetch_aircraft`."""
    try:
        payload = result.json()
    except ValueError as exc:
        raise ValueError(f"adsb.lol response is not JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("adsb.lol response has no 'now' timestamp")
    response_at = _response_time(payload.get("now"))
    source_id = make_source_id(
        "ADSB",
        f"{query.lat:.3f}",
        f"{query.lon:.3f}",
        timeutil.compact(result.fetched_at, seconds=True),
    )
    aircraft: list[Aircraft] = []
    for entry in payload.get("ac") or []:
        try:
            parsed = _parse_aircraft(entry, response_at=response_at, source_id=source_id)
        except (OverflowError, TypeError, ValueError) as exc:
            logger.warning("skipping adsb.lol target %r: %s", _hex_of(entry), exc)
            continue
        if parsed is not None:
            aircraft.append(parsed)
    return AdsbSnapshot(
        provenance=result.provenance(source_id, issued_at=response_at),
        query=query,
        aircraft=aircraft,
    )


async def fetch_aircraft(source: Source, points: Sequence[AdsbQueryPoint]) -> list[AdsbSnapshot]:
    """One GET per point, in order.

    Raises :class:`AdsbPointsFailed` once every point was tried if any of them failed, was
    unreadable, or came back only as a cached copy older than ``MAX_CACHED_COPY_AGE_S``.
    """
    snapshots: list[AdsbSnapshot] = []
    failed: list[tuple[AdsbQueryPoint, str]] = []
    for point in points:
        try:
            snapshots.append(await _fetch_point(source, point))
        except (FetchError, ValueError) as exc:
            reason = exc.reason if isinstance(exc, FetchError) else str(exc)
            logger.warning("adsb.lol point %s failed: %s", point_url(point), reason)
            failed.append((point, reason))
    if failed:
        raise AdsbPointsFailed(failed, snapshots, tried=len(points))
    return snapshots


def merge_aircraft(snapshots: Sequence[AdsbSnapshot]) -> list[Aircraft]:
    """One record per ICAO address (the newest position wins), sorted by address."""
    newest: dict[str, Aircraft] = {}
    for snapshot in snapshots:
        for aircraft in snapshot.aircraft:
            current = newest.get(aircraft.hex)
            if current is None or aircraft.observed_at > current.observed_at:
                newest[aircraft.hex] = aircraft
    return [newest[key] for key in sorted(newest)]


async def _fetch_point(source: Source, point: AdsbQueryPoint) -> AdsbSnapshot:
    result = await source.fetch(point_url(point), feed=FeedId.ADSB)
    age = result.stale_age_s
    if result.stale and (age is None or age > MAX_CACHED_COPY_AGE_S):
        raise ValueError(f"live fetch failed ({result.error}); only a cached copy {age} s old")
    return parse_adsb(result, point)


def _response_time(now: object) -> datetime:
    if not isinstance(now, int | float | str):
        raise ValueError("adsb.lol response has no 'now' timestamp")
    try:
        return timeutil.parse_iso(now)
    except (OSError, OverflowError, ValueError) as exc:
        raise ValueError(f"adsb.lol 'now' is not a timestamp: {exc}") from exc


def _parse_aircraft(
    entry: Mapping[str, Any], *, response_at: datetime, source_id: str
) -> Aircraft | None:
    """An airborne target with a position, or None for ground targets and position-less ones."""
    if not isinstance(entry, Mapping):
        raise TypeError("aircraft entry is not an object")
    hex_id = str(entry.get("hex") or "").strip().lower()
    if not hex_id:
        raise ValueError("no hex address")
    alt_baro = entry.get("alt_baro")
    lat, lon = _float(entry.get("lat")), _float(entry.get("lon"))
    if alt_baro == "ground" or lat is None or lon is None:
        return None
    seen_s = _float(entry.get("seen_pos"))
    if seen_s is None:
        seen_s = _float(entry.get("seen"))
    observed_at = response_at - timedelta(seconds=seen_s or 0.0)
    return Aircraft(
        hex=hex_id,
        callsign=_callsign(entry.get("flight"), entry.get("r")),
        type_icao=_text(entry.get("t")),
        lat=lat,
        lon=lon,
        alt_baro_ft=_int(alt_baro),
        alt_geom_ft=_int(entry.get("alt_geom")),
        nav_altitude_mcp_ft=_selected_altitude(entry.get("nav_altitude_mcp")),
        gs_kt=_float(entry.get("gs")),
        track_deg=_float(entry.get("track")),
        baro_rate_fpm=_int(entry.get("baro_rate")),
        seen_pos_s=seen_s,
        observed_at=observed_at,
        source_id=source_id,
    )


def _callsign(flight: object, registration: object) -> str | None:
    """Trimmed callsign; dropped when it is just the registration (general aviation)."""
    callsign = _text(flight)
    if callsign is None:
        return None
    reg = (_text(registration) or "").replace("-", "").upper()
    return None if reg and callsign.upper() == reg else callsign


def _selected_altitude(value: object) -> int | None:
    """MCP/FCU altitude is quantised by the encoding (31008 means FL310): round to 100 ft."""
    feet = _float(value)
    return None if feet is None else round(feet / 100.0) * 100


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _float(value: object) -> float | None:
    """A finite number or None: json.loads reads NaN and Infinity, float() reads 'nan'."""
    if value is None or isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _int(value: object) -> int | None:
    number = _float(value)
    return None if number is None else round(number)


def _hex_of(entry: object) -> object:
    return entry.get("hex") if isinstance(entry, Mapping) else entry
