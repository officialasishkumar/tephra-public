"""The sample airline feed: real flights, pushed the way an airline would push them.

The flights are real: each is an airline aircraft (its ICAO address, callsign and type) at a
position, level, speed and track it was recorded at in a replay case's ADS-B (``data/replay``).
Only the time is made up: every few seconds each flight is moved along its own track at its own
ground speed from that recorded fix, and pushed through the same path an airline's push takes
(``Runtime.take_push``), timed on TEPHRA's active clock. A flight that has flown its leg starts
it again. Flights whose leg crosses an ash area are picked first, so the demo has work in it.
"""

import asyncio
import contextlib
import json
import logging
import random
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Final

import shapely
from shapely.geometry import LineString

from tephra.geo.units import destination_point, distance_nm
from tephra.models import AIRLINE_FORMAT, BBox, FlightRoute
from tephra.util import timeutil
from tephra.util.hashing import proxy_flight_number

__all__ = [
    "PUSH_EVERY_S",
    "SampleFlight",
    "load_pool",
    "pick_flights",
    "pilot_report",
    "plans_for",
    "positions_at",
    "sample_batch",
]

logger = logging.getLogger(__name__)

PUSH_EVERY_S: Final = 5.0
LEG_KM: Final = 900.0
"""Each flight flies this far along its track from its recorded fix, then starts again"""
MAX_FLIGHTS: Final = 40
RUN_FOR_S: Final = 3600.0
"""The sample feed stops itself after an hour"""
_AIRLINE = re.compile(r"^[A-Z]{3}\d{1,4}[A-Z]?$")


@dataclass(frozen=True)
class SampleFlight:
    hex: str
    callsign: str
    type_icao: str | None
    lat: float
    lon: float
    alt_baro_ft: int
    gs_kt: float
    track_deg: float
    phase: float
    """0..1: how far along its leg the flight is when the feed starts, so they spread out"""

    def leg(self, samples: int = 12) -> LineString:
        points = [
            destination_point(self.lat, self.lon, self.track_deg, LEG_KM * i / samples)
            for i in range(samples + 1)
        ]
        return LineString([(lon, lat) for lat, lon in points])


def _fix(ac: dict[str, Any]) -> SampleFlight | None:
    callsign = str(ac.get("flight") or "").strip()
    alt, gs, track = ac.get("alt_baro"), ac.get("gs"), ac.get("track")
    if not _AIRLINE.fullmatch(callsign) or not isinstance(alt, int) or alt < 8000:
        return None
    if not isinstance(gs, int | float) or gs < 200 or not isinstance(track, int | float):
        return None
    if not isinstance(ac.get("lat"), int | float) or not isinstance(ac.get("lon"), int | float):
        return None
    hex_id = str(ac.get("hex", "")).lower()
    if not re.fullmatch(r"[0-9a-f]{6}", hex_id):
        return None
    kind = ac.get("t")
    return SampleFlight(
        hex=hex_id,
        callsign=callsign,
        type_icao=kind if isinstance(kind, str) and re.fullmatch(r"[A-Z0-9]{2,4}", kind) else None,
        lat=float(ac["lat"]),
        lon=float(ac["lon"]),
        alt_baro_ft=alt,
        gs_kt=float(gs),
        track_deg=float(track) % 360,
        phase=0.0,
    )


def load_pool(data_dir: Path, bbox: BBox) -> list[SampleFlight]:
    """One cruising airline fix per aircraft from every recorded case, inside ``bbox``."""
    rng = random.Random(7)  # the same spread every time
    found: dict[str, SampleFlight] = {}
    for path in sorted((data_dir / "replay").glob("*/raw/adsb/*.json")):
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for ac in body.get("ac") or []:
            flight = _fix(ac) if isinstance(ac, dict) else None
            if flight is None or flight.hex in found or not bbox.contains(flight.lat, flight.lon):
                continue
            found[flight.hex] = flight
    return [
        SampleFlight(**{**flight.__dict__, "phase": rng.random()})
        for flight in sorted(found.values(), key=lambda f: f.hex)
    ]


def pick_flights(
    pool: Sequence[SampleFlight],
    areas: Sequence[Any],
    *,
    skip: set[str],
    limit: int = MAX_FLIGHTS,
    prefer: Callable[[SampleFlight], bool] | None = None,
) -> list[SampleFlight]:
    """Flights whose leg crosses an ash area first (up to two thirds), then the rest; within
    each, the ``prefer``red ones (those with a known route, so they get a flight plan) first."""
    usable = [flight for flight in pool if flight.hex not in skip]
    if prefer is not None:
        usable.sort(key=lambda flight: not prefer(flight))
    shape = shapely.union_all(list(areas)) if areas else None
    crossing = [f for f in usable if shape is not None and f.leg().intersects(shape)]
    others = [f for f in usable if f not in crossing]
    first = crossing[: (limit * 2) // 3]
    return first + others[: limit - len(first)]


def positions_at(flights: Sequence[SampleFlight], elapsed_s: float, at: datetime) -> list[dict]:
    """Each flight moved ``elapsed_s`` along its leg (looping), as ``tephra.positions/1``."""
    out = []
    for flight in flights:
        leg_s = LEG_KM / (flight.gs_kt * 1.852) * 3600
        flown_km = ((flight.phase * leg_s + elapsed_s) % leg_s) / 3600 * flight.gs_kt * 1.852
        lat, lon = destination_point(flight.lat, flight.lon, flight.track_deg, flown_km)
        out.append(
            {
                "hex": flight.hex,
                "callsign": flight.callsign,
                "type_icao": flight.type_icao,
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "alt_baro_ft": flight.alt_baro_ft,
                "gs_kt": round(flight.gs_kt, 1),
                "track_deg": round(flight.track_deg, 1),
                "observed_at": timeutil.to_iso(at),
            }
        )
    return out


def plans_for(
    flights: Sequence[SampleFlight],
    route_of: Callable[[SampleFlight], FlightRoute | None],
    position_of: Callable[[str], tuple[float, float] | None],
    at: datetime,
) -> list[dict[str, Any]]:
    """A flight plan for each flight whose callsign has a usual route it is flying (VRS
    standing data): its real origin and destination, the RFA flight number it stands for, the
    level it flies, and departure and arrival times worked out from its speed and where it is
    now (the sample's only estimate)."""
    out = []
    for flight in flights:
        route = route_of(flight)
        if route is None:
            continue
        origin, dest = position_of(route.origin_icao), position_of(route.dest_icao)
        if origin is None or dest is None:
            continue
        speed = max(flight.gs_kt, 1.0)
        sta = at + timedelta(hours=distance_nm(flight.lat, flight.lon, *dest) / speed)
        std = sta - timedelta(hours=distance_nm(*origin, *dest) / speed)
        out.append(
            {
                "flight": proxy_flight_number(flight.hex),
                "hex": flight.hex,
                "callsign": flight.callsign,
                "origin_icao": route.origin_icao,
                "dest_icao": route.dest_icao,
                "std": timeutil.to_iso(std.replace(second=0, microsecond=0)),
                "sta": timeutil.to_iso(sta.replace(second=0, microsecond=0)),
                "cruise_fl": round(flight.alt_baro_ft / 1000) * 10,
            }
        )
    return out


def pilot_report(position: dict[str, Any], at: datetime) -> dict[str, Any]:
    """A crew report of ash from a flight now (a ``CrewEntry``). No position: TEPHRA holds the
    flight's fix (its pushed position), and a report on a tracked flight is placed there."""
    fl = position["alt_baro_ft"] // 100
    return {
        "hex": position["hex"],
        "cues": ["ASH_SEEN", "SULPHUR_SMELL"],
        "level_from_fl": max(0, fl - 20),
        "level_to_fl": min(600, fl + 10),
        "observed_at": timeutil.to_iso(at),
        "remarks": "Sample feed: crew report ash in sight",
    }


def sample_batch(
    flights: Sequence[SampleFlight],
    plans: list[dict[str, Any]],
    in_ash: Callable[[dict[str, Any]], bool],
    at: datetime,
) -> dict[str, Any]:
    """A downloadable example of every section, on TEPHRA's clock: the flights at their recorded
    fixes, their flight plans, and pilot reports from up to two of them in the ash."""
    positions = positions_at(flights, 0.0, at)
    reports = [pilot_report(p, at) for p in positions if in_ash(p)][:2]
    return {
        "format": AIRLINE_FORMAT,
        "positions": positions,
        "flight_plans": plans,
        "pilot_reports": reports,
    }


async def run_sample_feed(
    flights: Sequence[SampleFlight],
    push: Callable[[list[dict]], Any],
    stop: asyncio.Event,
) -> None:
    """Push every :data:`PUSH_EVERY_S` until stopped or :data:`RUN_FOR_S` has passed."""
    started = time.monotonic()
    while not stop.is_set():
        elapsed = time.monotonic() - started
        if elapsed > RUN_FOR_S:
            return
        try:
            await push(positions_at(flights, elapsed, timeutil.now()))
        except Exception:  # one failed push must not end the feed
            logger.exception("sample feed push failed")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=PUSH_EVERY_S)
