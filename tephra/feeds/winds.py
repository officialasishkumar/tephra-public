"""Hourly pressure-level winds above a volcano from Open-Meteo.

Each pressure level stands for one flight level through the ISA table
``PRESSURE_LEVEL_FL`` (850 hPa = FL050 ... 150 hPa = FL450). Open-Meteo returns parallel
arrays under ``hourly``; ``time`` strings carry no zone and are UTC because we ask for
``timezone=GMT``. Directions are meteorological (where the wind blows from).
"""

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any, Final

from tephra.feeds.base import FetchResult, Source
from tephra.models import PRESSURE_LEVEL_FL, FeedId, WindLevel, WindProfile, make_source_id
from tephra.util import timeutil

__all__ = [
    "OPEN_METEO_URL",
    "fetch_winds",
    "parse_winds",
    "profile_at",
    "wind_at_fl",
    "wind_params",
]

logger = logging.getLogger(__name__)

OPEN_METEO_URL: Final = "https://api.open-meteo.com/v1/forecast"
PRESSURE_LEVELS_HPA: Final[tuple[int, ...]] = tuple(sorted(PRESSURE_LEVEL_FL))


def wind_params(lat: float, lon: float, *, past_hours: int = 1) -> dict[str, str]:
    """Query parameters in a fixed key order (the URL is the cache and replay key).

    ``forecast_hours=24`` rather than ``forecast_days=1``: the latter stops at 23:00 UTC of
    the current day, which late in the UTC day leaves almost no forecast. ``past_hours`` is
    longer for a crew report, whose observation may be hours old.
    """
    hourly = ",".join(f"wind_speed_{hpa}hPa,wind_direction_{hpa}hPa" for hpa in PRESSURE_LEVELS_HPA)
    return {
        "latitude": f"{lat:.2f}",
        "longitude": f"{lon:.2f}",
        "hourly": hourly,
        "wind_speed_unit": "kn",
        "timezone": "GMT",
        "past_hours": str(past_hours),
        "forecast_hours": "24",
    }


def parse_winds(result: FetchResult, *, lat: float, lon: float) -> list[WindProfile]:
    """One profile per hour, oldest first; levels missing from the response are left out."""
    try:
        payload = result.json()
    except ValueError as exc:
        raise ValueError(f"Open-Meteo response is not JSON: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("hourly"), dict):
        raise ValueError("Open-Meteo response has no 'hourly' block")
    hourly: Mapping[str, Any] = payload["hourly"]
    times = hourly.get("time")
    if not isinstance(times, list):
        raise ValueError("Open-Meteo 'hourly' has no 'time' array")
    offset = timedelta(seconds=int(payload.get("utc_offset_seconds") or 0))
    profiles: list[WindProfile] = []
    for index, stamp in enumerate(times):
        try:
            valid_at = timeutil.parse_iso(str(stamp)) - offset
        except ValueError:
            logger.warning("skipping Open-Meteo hour with unreadable time %r", stamp)
            continue
        levels = _levels_at(hourly, index)
        if not levels:
            continue
        source_id = make_source_id("WINDS", f"{lat:.2f}", f"{lon:.2f}", timeutil.compact(valid_at))
        provenance = result.provenance(
            source_id, valid_from=valid_at, valid_to=valid_at + timedelta(hours=1)
        )
        profiles.append(
            WindProfile(provenance=provenance, lat=lat, lon=lon, valid_at=valid_at, levels=levels)
        )
    profiles.sort(key=lambda profile: profile.valid_at)
    return profiles


async def fetch_winds(
    source: Source, lat: float, lon: float, *, past_hours: int = 1
) -> list[WindProfile]:
    result = await source.fetch(
        OPEN_METEO_URL, feed=FeedId.WINDS, params=wind_params(lat, lon, past_hours=past_hours)
    )
    return parse_winds(result, lat=lat, lon=lon)


def profile_at(profiles: Sequence[WindProfile], at: datetime) -> WindProfile | None:
    """The profile whose hour is nearest ``at`` (the earlier one on a tie)."""
    if not profiles:
        return None
    return min(
        profiles,
        key=lambda profile: (abs((profile.valid_at - at).total_seconds()), profile.valid_at),
    )


def wind_at_fl(profile: WindProfile, flight_level: int) -> WindLevel:
    """The level nearest ``flight_level`` (the lower one on a tie)."""
    if not profile.levels:
        raise ValueError(f"wind profile {profile.provenance.source_id} has no levels")
    return min(
        profile.levels,
        key=lambda level: (abs(level.flight_level - flight_level), level.flight_level),
    )


def _levels_at(hourly: Mapping[str, Any], index: int) -> list[WindLevel]:
    levels: list[WindLevel] = []
    for hpa in PRESSURE_LEVELS_HPA:
        speed = _value_at(hourly.get(f"wind_speed_{hpa}hPa"), index)
        direction = _value_at(hourly.get(f"wind_direction_{hpa}hPa"), index)
        if speed is None or direction is None:
            continue
        levels.append(
            WindLevel(
                pressure_hpa=hpa,
                flight_level=PRESSURE_LEVEL_FL[hpa],
                speed_kt=speed,
                from_deg=direction % 360.0,
            )
        )
    levels.sort(key=lambda level: level.flight_level)
    return levels


def _value_at(column: object, index: int) -> float | None:
    if not isinstance(column, list) or index >= len(column):
        return None
    value = column[index]
    if value is None or isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)
