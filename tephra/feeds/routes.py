"""Origin and destination of an ADS-B callsign from VRS standing data (CC0).

``data/routes_apac.json`` is built once by ``scripts/build_routes.py`` and read from disk;
there is no network at runtime. The routes are crowd-sourced per callsign, so a leg is used
only when the aircraft lies near its great circle and flies along it. The file also holds the
position of every airport its chains use that ``data/airports.json`` lacks (VRS airports,
CC0); the catalogue wins where both know an airport.
"""

import math
import re
from collections.abc import Iterable, Mapping
from itertools import pairwise
from pathlib import Path
from typing import Any, Final, Protocol

from pydantic import BaseModel, ConfigDict

from tephra.feeds.airports import AirportCatalogue
from tephra.geo.units import (
    EARTH_RADIUS_KM,
    bearing_diff_deg,
    distance_nm,
    initial_bearing_deg,
    km_to_nm,
    normalize_lon,
    unwrap_lon,
)
from tephra.models import (
    FlightRoute,
    GeoLineString,
    OperatorPolicy,
    Position,
    RouteFeatureProps,
    feature,
    feature_collection,
    point,
)

__all__ = [
    "ROUTES_FILE",
    "RouteTable",
    "cross_track_nm",
    "great_circle",
    "load_routes",
    "route_features",
]

ROUTES_FILE: Final = "routes_apac.json"
_LINE_STEP_NM: Final = 40.0
"""Spacing of the points of a drawn route: the line bends with the great circle at any zoom"""
_LINE_MAX_POINTS: Final = 256
_EARTH_RADIUS_NM: Final = km_to_nm(EARTH_RADIUS_KM)
_LEADING_ZEROS: Final = re.compile(r"^([A-Z]{3})0+(?=\d)")
"""VRS keeps callsigns without leading zeros in the flight number (GIA0101 is GIA101)."""


class _Located(Protocol):
    """An aircraft or an exposed flight: what the lookup reads."""

    @property
    def callsign(self) -> str | None: ...
    @property
    def lat(self) -> float: ...
    @property
    def lon(self) -> float: ...
    @property
    def track_deg(self) -> float | None: ...


class RoutesSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    url: str
    fetched: str
    sha256: str
    license: str
    note: str


class RoutesFile(BaseModel):
    """Shape of ``data/routes_apac.json``: callsign -> hyphen-joined airport chain, and the
    ``[lat, lon]`` of the chain airports that the airport catalogue does not hold."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: RoutesSource
    airports_source: RoutesSource
    airports: dict[str, tuple[float, float]]
    routes: dict[str, str]


class RouteTable:
    def __init__(
        self, routes: Mapping[str, str], positions: Mapping[str, tuple[float, float]] | None = None
    ) -> None:
        self._chains = {callsign: tuple(chain.split("-")) for callsign, chain in routes.items()}
        self._positions = dict(positions or {})

    def __len__(self) -> int:
        return len(self._chains)

    def chain(self, callsign: str | None) -> tuple[str, ...] | None:
        if not callsign:
            return None
        code = callsign.strip().upper()
        return self._chains.get(code) or self._chains.get(_LEADING_ZEROS.sub(r"\1", code))

    def position(self, icao: str, airports: AirportCatalogue) -> tuple[float, float] | None:
        """``(lat, lon)`` of an airport: the catalogue's, else the one in the routes file."""
        known = airports.get(icao)
        if known is not None:
            return known.lat, known.lon
        return self._positions.get(icao.strip().upper())

    def lookup(
        self, aircraft: _Located, airports: AirportCatalogue, policy: OperatorPolicy
    ) -> FlightRoute | None:
        """The leg of the callsign's chain the aircraft is flying, or None.

        A leg qualifies when the aircraft lies between its ends, within the policy's
        cross-track distance of its great circle, with its track within 90 degrees of the
        bearing to the leg's destination. The nearest qualifying leg wins.
        """
        chain = self.chain(aircraft.callsign)
        if chain is None or aircraft.track_deg is None or aircraft.callsign is None:
            return None
        limit = policy.reroute.route_max_cross_track_nm.value
        best: tuple[float, str, str] | None = None
        for origin_icao, dest_icao in pairwise(chain):
            origin, dest = self.position(origin_icao, airports), self.position(dest_icao, airports)
            if origin is None or dest is None:
                continue
            cross = _cross_track_nm(aircraft, *origin, *dest)
            if cross is None or cross > limit:
                continue
            bearing = initial_bearing_deg(aircraft.lat, aircraft.lon, *dest)
            if bearing_diff_deg(aircraft.track_deg, bearing) > 90.0:
                continue
            if best is None or cross < best[0]:
                best = (cross, origin_icao, dest_icao)
        if best is None:
            return None
        return FlightRoute(
            callsign=aircraft.callsign.strip().upper(),
            origin_icao=best[1],
            dest_icao=best[2],
            cross_track_nm=round(best[0], 1),
        )


def _cross_track_nm(
    aircraft: _Located, lat1: float, lon1: float, lat2: float, lon2: float
) -> float | None:
    """Distance from the leg's great circle, or None when the aircraft is beyond either end."""
    leg_nm = distance_nm(lat1, lon1, lat2, lon2)
    from_origin = distance_nm(lat1, lon1, aircraft.lat, aircraft.lon)
    to_dest = distance_nm(aircraft.lat, aircraft.lon, lat2, lon2)
    if leg_nm == 0 or from_origin > leg_nm + 1 or to_dest > leg_nm + 1:
        return None
    angle = math.radians(
        initial_bearing_deg(lat1, lon1, aircraft.lat, aircraft.lon)
        - initial_bearing_deg(lat1, lon1, lat2, lon2)
    )
    sine = math.sin(from_origin / _EARTH_RADIUS_NM) * math.sin(angle)
    return abs(math.asin(max(-1.0, min(1.0, sine)))) * _EARTH_RADIUS_NM


def cross_track_nm(
    aircraft: _Located, lat1: float, lon1: float, lat2: float, lon2: float
) -> float | None:
    """The aircraft's distance from the leg's great circle, or None beyond either end (also
    used for a route an airline's own flight plan gives)."""
    return _cross_track_nm(aircraft, lat1, lon1, lat2, lon2)


def great_circle(lat1: float, lon1: float, lat2: float, lon2: float) -> list[Position]:
    """``(lon, lat)`` points along the great circle, one every ``_LINE_STEP_NM`` or so.

    The first longitude is in [-180, 180) and each next one is unwrapped against the one
    before, so a line across the antimeridian runs on (179, 181, ...) instead of jumping back
    across the map; MapLibre draws such a line continuously into the next world copy.
    """
    a, b = _unit(lat1, lon1), _unit(lat2, lon2)
    angle = math.acos(max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b, strict=True)))))
    steps = min(
        _LINE_MAX_POINTS - 1, max(1, math.ceil(distance_nm(lat1, lon1, lat2, lon2) / _LINE_STEP_NM))
    )
    points: list[Position] = []
    previous = normalize_lon(lon1)
    for index in range(steps + 1):
        fraction = index / steps
        if angle < 1e-9:
            lat, lon = lat1, lon1
        else:
            wa = math.sin((1 - fraction) * angle) / math.sin(angle)
            wb = math.sin(fraction * angle) / math.sin(angle)
            x, y, z = (wa * p + wb * q for p, q in zip(a, b, strict=True))
            lat = math.degrees(math.atan2(z, math.hypot(x, y)))
            lon = math.degrees(math.atan2(y, x))
        previous = unwrap_lon(normalize_lon(lon), previous) if index else previous
        points.append((round(previous, 4), round(lat, 4)))
    return points


def _unit(lat: float, lon: float) -> tuple[float, float, float]:
    phi, lmb = math.radians(lat), math.radians(lon)
    return math.cos(phi) * math.cos(lmb), math.cos(phi) * math.sin(lmb), math.sin(phi)


def route_features(
    legs: Mapping[tuple[str, str], Iterable[str]], table: RouteTable, airports: AirportCatalogue
) -> dict[str, Any]:
    """One ``line`` per pair of airports, drawn for the given flight hexes, and one ``airport``
    Point per end. Both directions of a pair share one line (it has no arrows), so a WIII-WAAA
    flight and a WAAA-WIII flight never stack two faint lines into one that looks picked. A pair
    whose airport has no known position is left out: a line is never drawn to a guessed place."""
    pairs: dict[tuple[str, str], set[str]] = {}
    for (origin_icao, dest_icao), hexes in legs.items():
        if origin_icao == dest_icao:
            continue
        pair = (min(origin_icao, dest_icao), max(origin_icao, dest_icao))
        pairs.setdefault(pair, set()).update(hexes)
    features: list[dict[str, Any]] = []
    ends: dict[tuple[str, float], Position] = {}
    for (first, second), hexes in sorted(pairs.items()):
        start = table.position(first, airports)
        end = table.position(second, airports)
        if start is None or end is None:
            continue
        line = great_circle(*start, *end)
        props = RouteFeatureProps(feature="line", ends=[first, second], hexes=sorted(hexes))
        features.append(
            feature(GeoLineString(coordinates=line), props, feature_id=f"{first}-{second}")
        )
        for icao, (lon, lat) in ((first, line[0]), (second, line[-1])):
            ends.setdefault((icao, lon), (lon, lat))
    for (icao, _), (lon, lat) in sorted(ends.items()):
        props = RouteFeatureProps(feature="airport", icao=icao)
        features.append(feature(point(lat, lon), props, feature_id=f"{icao}@{lon:g}"))
    return feature_collection(features)


def load_routes(data_dir: Path) -> RouteTable:
    table = RoutesFile.model_validate_json((data_dir / ROUTES_FILE).read_bytes())
    return RouteTable(table.routes, table.airports)
