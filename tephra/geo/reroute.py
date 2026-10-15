"""Lateral reroute around the hazard cone: a visibility graph priced in minutes of wind.

The hazard cone, simplified and buffered outward, is the obstacle. A shortest path around a
polygon bends only at its convex vertices, so those vertices plus the flight's present
position and the candidate end points form the graph; an edge exists where the straight leg
stays out of the obstacle. Dijkstra then runs on minutes, each leg costed with the ground
speed the wind at the flight level gives. There is no airway data for the region, so the
route is free-route direct legs between latitude/longitude turn points (``research/18a``).

Geometry runs in a local azimuthal equidistant plane (NM) centred on the cone, hand-written
because pyproj is an optional dependency. The obstacle and its vertex visibility graph do
not depend on the flight, so they are cached per cone and level band; a flight adds only its
own start and end edges, all tested and costed with vectorised shapely 2 and numpy.

Official layers lie inside the cone (``tephra.geo.cone.covers_official``), so the cone at its
band is the whole obstacle: a flight whose level misses the cone's band widened by the
vertical margin meets no official layer either. The obstacle is the convex hull of each
connected piece of the buffered cone: always a superset, so never a narrower hazard, and with
far fewer vertices, so far fewer turns.
"""

import math
import time
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Final, Literal

import numpy as np
import shapely
from numpy.typing import NDArray
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient

from tephra.geo.cone import geometry_to_shape
from tephra.geo.fuel import MIN_TRUSTED_GS_KT, reroute_line
from tephra.geo.units import (
    EARTH_RADIUS_KM,
    KM_PER_NM,
    bearing_diff_deg,
    destination_point,
    ft_to_fl,
    initial_bearing_deg,
    nm_to_km,
)
from tephra.models import (
    ExposedFlight,
    FlightRoute,
    GeoPolygon,
    HazardCone,
    OperatorPolicy,
    Position,
    RerouteKind,
    RerouteOption,
    RerouteStatus,
    Situation,
    WindProfile,
)
from tephra.util.hashing import sha256_text, stable_id

__all__ = ["clear_cache", "coordinate_text", "plan_reroutes"]

FloatArray = NDArray[np.float64]

EARTH_RADIUS_NM: Final = EARTH_RADIUS_KM / KM_PER_NM
QUAD_SEGS: Final = 2
"""Segments per quarter circle of the buffer. Few segments keep the vertex count, and so the
graph, small; the buffer radius is widened so every edge still lies at the full distance."""
INSET_NM: Final = 0.01
"""A leg may touch the obstacle outline; it may not enter this far inside it."""
RAY_STEP_NM: Final = 5.0
"""Spacing of the samples along the present track, where it meets the obstacle."""
ARC_MINUTE_NM: Final = 1.0
"""Rounding a turn point to one arc-minute moves it by less than this."""
GREAT_CIRCLE_STEP_NM: Final = 25.0
RETRY_SIMPLIFY_FACTOR: Final = 2
"""Simplification is raised by this factor once when a route needs too many turn points."""
COLLINEAR_NM: Final = 0.05
CACHE_SIZE: Final = 16
MIN_GS_KT: Final = 1.0

_GRAPHS: OrderedDict[tuple[str, int, int, float, float], "_Graph"] = OrderedDict()


def clear_cache() -> None:
    _GRAPHS.clear()


class _TooManyTurnPoints(Exception):
    """The shortest path needs more turn points than the policy allows at this simplification."""


# --- projection ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Aeqd:
    """Spherical azimuthal equidistant projection onto a plane in NM."""

    lat0: float
    lon0: float

    def forward(self, lat: FloatArray, lon: FloatArray) -> tuple[FloatArray, FloatArray]:
        phi, phi0 = np.radians(lat), math.radians(self.lat0)
        dlon = np.radians(lon - self.lon0)
        cos_c = np.clip(
            math.sin(phi0) * np.sin(phi) + math.cos(phi0) * np.cos(phi) * np.cos(dlon), -1.0, 1.0
        )
        c = np.arccos(cos_c)
        sin_c = np.sin(c)
        scale = np.where(sin_c < 1e-12, 1.0, c / np.where(sin_c < 1e-12, 1.0, sin_c))
        x = EARTH_RADIUS_NM * scale * np.cos(phi) * np.sin(dlon)
        y = (
            EARTH_RADIUS_NM
            * scale
            * (math.cos(phi0) * np.sin(phi) - math.sin(phi0) * np.cos(phi) * np.cos(dlon))
        )
        return x, y

    def inverse(self, x: FloatArray, y: FloatArray) -> tuple[FloatArray, FloatArray]:
        phi0 = math.radians(self.lat0)
        rho = np.hypot(x, y)
        c = rho / EARTH_RADIUS_NM
        safe = np.where(rho == 0, 1.0, rho)
        sin_c, cos_c = np.sin(c), np.cos(c)
        sin_phi = np.clip(cos_c * math.sin(phi0) + y * sin_c * math.cos(phi0) / safe, -1.0, 1.0)
        dlon = np.arctan2(x * sin_c, rho * math.cos(phi0) * cos_c - y * math.sin(phi0) * sin_c)
        lon = (self.lon0 + np.degrees(dlon) + 180.0) % 360.0 - 180.0
        return np.degrees(np.arcsin(sin_phi)), lon

    def point(self, lat: float, lon: float) -> tuple[float, float]:
        x, y = self.forward(np.array([lat]), np.array([lon]))
        return float(x[0]), float(y[0])

    def project(self, shape: BaseGeometry) -> BaseGeometry:
        def convert(coords: FloatArray) -> FloatArray:
            x, y = self.forward(coords[:, 1], coords[:, 0])
            return np.column_stack([x, y])

        return shapely.transform(shape, convert)


def _leg(
    lat1: FloatArray, lon1: FloatArray, lat2: FloatArray, lon2: FloatArray
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """Great-circle distance (NM) and the east and north parts of the initial bearing."""
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dlon = np.radians(lon2 - lon1)
    a = np.sin((phi2 - phi1) / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlon / 2) ** 2
    nm = 2.0 * EARTH_RADIUS_NM * np.arcsin(np.minimum(1.0, np.sqrt(a)))
    east = np.sin(dlon) * np.cos(phi2)
    north = np.cos(phi1) * np.sin(phi2) - np.sin(phi1) * np.cos(phi2) * np.cos(dlon)
    norm = np.hypot(east, north)
    safe = np.where(norm == 0, 1.0, norm)
    return nm, east / safe, north / safe


# --- wind and speed -----------------------------------------------------------------------


@dataclass(frozen=True)
class _Wind:
    """The wind at the flight level: the vector it blows toward (kt) and how it was read."""

    east_kt: float
    north_kt: float
    from_deg: float
    speed_kt: float


def _isa_hpa(fl: int) -> float:
    ft = fl * 100.0
    if ft <= 36_089.0:
        return 1013.25 * (1.0 - 6.8756e-6 * ft) ** 5.2559
    return 226.32 * math.exp(-(ft - 36_089.0) / 20_806.0)


def _wind_at(situation: Situation | None, fl: int) -> _Wind | None:
    """Wind at ``fl`` from the hourly profile nearest ``as_of``, interpolated in ln(pressure)."""
    if situation is None or not situation.winds:
        return None
    profile: WindProfile = min(
        situation.winds, key=lambda p: abs((p.valid_at - situation.as_of).total_seconds())
    )
    levels = sorted(profile.levels, key=lambda level: level.pressure_hpa)
    if not levels:
        return None
    ln_p = np.log([level.pressure_hpa for level in levels])
    toward = np.radians([level.from_deg + 180.0 for level in levels])
    speed = np.array([level.speed_kt for level in levels])
    here = math.log(_isa_hpa(fl))
    east = float(np.interp(here, ln_p, speed * np.sin(toward)))
    north = float(np.interp(here, ln_p, speed * np.cos(toward)))
    return _Wind(
        east_kt=east,
        north_kt=north,
        from_deg=(math.degrees(math.atan2(east, north)) + 180.0) % 360.0,
        speed_kt=math.hypot(east, north),
    )


def _ground_speed(
    tas_kt: float, wind: _Wind | None, east: FloatArray, north: FloatArray
) -> FloatArray:
    """Ground speed on a track given by its unit vector: crab into the wind, add the tail."""
    if wind is None:
        return np.full_like(east, tas_kt)
    tail = wind.east_kt * east + wind.north_kt * north
    cross = wind.east_kt * north - wind.north_kt * east
    return np.maximum(tail + np.sqrt(np.maximum(tas_kt**2 - cross**2, 1.0)), MIN_GS_KT)


def _tas_kt(flight: ExposedFlight, wind: _Wind | None, policy: OperatorPolicy) -> float:
    """True airspeed: ADS-B ground velocity less the wind, else the policy's cruise value."""
    gs, track = flight.gs_kt, flight.track_deg
    if gs is not None and track is not None and gs >= MIN_TRUSTED_GS_KT:
        ground_e, ground_n = gs * math.sin(math.radians(track)), gs * math.cos(math.radians(track))
        if wind is not None:
            ground_e, ground_n = ground_e - wind.east_kt, ground_n - wind.north_kt
        tas = math.hypot(ground_e, ground_n)
        if tas >= MIN_TRUSTED_GS_KT:
            return tas
    return float(policy.reroute.cruise_tas_kt.value)


# --- obstacle graph (cached per cone) -----------------------------------------------------


@dataclass(frozen=True)
class _Graph:
    proj: _Aeqd
    guard: BaseGeometry
    """The true cone plus the buffer less the rounding slack: no finished route may enter it."""
    obstacle: BaseGeometry
    inset: BaseGeometry
    xy: FloatArray
    lat: FloatArray
    lon: FloatArray
    nm: FloatArray
    """Leg length between convex vertices; infinity where the leg enters the obstacle."""
    east: FloatArray
    north: FloatArray
    build_ms: float


def _graph(cone: HazardCone, policy: OperatorPolicy, simplify_nm: float) -> _Graph:
    buffer_nm = float(policy.reroute.buffer_nm.value)
    key = (cone.id, cone.base_ft, cone.top_ft, buffer_nm, simplify_nm)
    cached = _GRAPHS.get(key)
    if cached is not None:
        _GRAPHS.move_to_end(key)
        return cached
    graph = _build_graph(cone, buffer_nm, simplify_nm)
    _GRAPHS[key] = graph
    while len(_GRAPHS) > CACHE_SIZE:
        _GRAPHS.popitem(last=False)
    return graph


def _cone_shape(cone: HazardCone) -> BaseGeometry:
    """The cone as a lon/lat shape with holes filled: a hole is not a way through."""
    geometry = cone.geometry
    if geometry is None:
        return Polygon()
    ref_lon = (
        geometry.coordinates[0][0][0]
        if isinstance(geometry, GeoPolygon)
        else geometry.coordinates[0][0][0][0]
    )
    shape = geometry_to_shape(geometry, ref_lon=ref_lon)
    return shapely.union_all([Polygon(part.exterior) for part in shapely.get_parts(shape)])


def _build_graph(cone: HazardCone, buffer_nm: float, simplify_nm: float) -> _Graph:
    started = time.perf_counter()
    shape = _cone_shape(cone)
    centre = shape.centroid
    proj = _Aeqd(lat0=centre.y, lon0=centre.x)
    core = proj.project(shape)
    reach = (buffer_nm + simplify_nm) / math.cos(math.pi / (4 * QUAD_SEGS))
    simplified = core.simplify(simplify_nm, preserve_topology=True)
    obstacle = _hulls(simplified.buffer(reach, quad_segs=QUAD_SEGS))
    inset = obstacle.buffer(-INSET_NM)
    shapely.prepare(inset)
    guard = core.buffer(max(buffer_nm - ARC_MINUTE_NM, 0.0))
    shapely.prepare(guard)
    xy = _convex_vertices(obstacle)
    lat, lon = proj.inverse(xy[:, 0], xy[:, 1])
    nm, east, north = _leg(lat[:, None], lon[:, None], lat[None, :], lon[None, :])
    visible = _visible_pairs(inset, xy)
    return _Graph(
        proj=proj,
        guard=guard,
        obstacle=obstacle,
        inset=inset,
        xy=xy,
        lat=lat,
        lon=lon,
        nm=np.where(visible, nm, np.inf),
        east=east,
        north=north,
        build_ms=(time.perf_counter() - started) * 1000.0,
    )


def _hulls(buffered: BaseGeometry) -> BaseGeometry:
    """The convex hull of each connected piece of the buffered cone. A hull always contains
    its piece, so it never narrows the hazard; it has far fewer vertices, so far fewer turns.
    Hulls that touch merge into one piece, which is hulled again until none touch."""
    shape = buffered
    while True:
        parts = shapely.get_parts(shape)
        merged = shapely.union_all([part.convex_hull for part in parts])
        if len(shapely.get_parts(merged)) == len(parts):
            return merged
        shape = merged


def _convex_vertices(obstacle: BaseGeometry) -> FloatArray:
    """Exterior vertices where the outline turns left (counter-clockwise rings): the only
    places a shortest path around the obstacle can bend."""
    found: list[FloatArray] = []
    for part in shapely.get_parts(obstacle):
        ring = np.asarray(orient(part, sign=1.0).exterior.coords)[:-1]
        before, after = np.roll(ring, 1, axis=0), np.roll(ring, -1, axis=0)
        into, out = ring - before, after - ring
        turn = into[:, 0] * out[:, 1] - into[:, 1] * out[:, 0]
        found.append(ring[turn > 1e-9])
    return np.vstack(found) if found else np.empty((0, 2))


def _visible_pairs(inset: BaseGeometry, xy: FloatArray) -> NDArray[np.bool_]:
    count = len(xy)
    visible = np.zeros((count, count), dtype=bool)
    if count < 2:
        return visible
    first, second = np.triu_indices(count, 1)
    legs = shapely.linestrings(np.stack([xy[first], xy[second]], axis=1))
    clear = ~shapely.intersects(inset, legs)
    visible[first, second] = clear
    visible[second, first] = clear
    return visible


# --- one flight ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Trip:
    flight: ExposedFlight
    cone: HazardCone
    policy: OperatorPolicy
    fl: int
    tas_kt: float
    wind: _Wind | None


@dataclass(frozen=True)
class _End:
    """A place the route may finish. ``tail_min`` is the time on from there to the common
    reference end, so ends strung along the present track are comparable."""

    lat: float
    lon: float
    x: float
    y: float
    tail_min: float
    baseline_nm: float
    baseline_min: float


@dataclass(frozen=True)
class _Found:
    end: _End
    vertices: list[int]


def plan_reroutes(
    flight: ExposedFlight,
    cone: HazardCone,
    situation: Situation | None,
    route: FlightRoute | None,
    policy: OperatorPolicy,
    *,
    dest_position: tuple[float, float] | None = None,
) -> list[RerouteOption]:
    """Both reroute kinds for one exposed flight, whatever their status.

    ``dest_position`` is the ``(lat, lon)`` of ``route.dest_icao``. The options are code
    results the planner and drafter use as they are; there is no substitute route.
    """
    started = time.perf_counter()
    trip = _trip(flight, cone, situation, policy)
    if not _meets_cone(flight, cone, policy):
        options = [
            _refusal(trip, kind, RerouteStatus.NOT_EXPOSED, "LEVEL IS OUTSIDE THE HAZARD BAND")
            for kind in RerouteKind
        ]
    else:
        rejoin = _solve_with_retry(trip, RerouteKind.REJOIN_TRACK, None, None)
        if rejoin.status is RerouteStatus.NOT_EXPOSED:
            direct = _refusal(trip, RerouteKind.DIRECT_DEST, rejoin.status, rejoin.note)
        else:
            direct = _solve_with_retry(trip, RerouteKind.DIRECT_DEST, route, dest_position)
        options = [rejoin, direct]
    elapsed = round((time.perf_counter() - started) * 1000.0, 1)
    return [option.model_copy(update={"compute_ms": elapsed}) for option in options]


def _trip(
    flight: ExposedFlight, cone: HazardCone, situation: Situation | None, policy: OperatorPolicy
) -> _Trip:
    low, high = flight.aircraft_band_ft
    altitude = flight.alt_baro_ft if flight.alt_baro_ft is not None else (low + high) // 2
    fl = ft_to_fl(altitude)
    wind = _wind_at(situation, fl)
    return _Trip(
        flight=flight,
        cone=cone,
        policy=policy,
        fl=fl,
        tas_kt=_tas_kt(flight, wind, policy),
        wind=wind,
    )


def _meets_cone(flight: ExposedFlight, cone: HazardCone, policy: OperatorPolicy) -> bool:
    margin = policy.exposure.vertical_margin_ft.value
    low, high = flight.aircraft_band_ft
    return high >= cone.base_ft - margin and low <= cone.top_ft + margin


def _solve_with_retry(
    trip: _Trip, kind: RerouteKind, route: FlightRoute | None, dest: tuple[float, float] | None
) -> RerouteOption:
    simplify = float(trip.policy.reroute.simplify_nm.value)
    try:
        return _solve(trip, kind, route, dest, simplify)
    except _TooManyTurnPoints:
        pass
    try:
        return _solve(trip, kind, route, dest, simplify * RETRY_SIMPLIFY_FACTOR)
    except _TooManyTurnPoints:
        limit = trip.policy.reroute.max_waypoints_count.value
        return _refusal(
            trip, kind, RerouteStatus.NO_ROUTE, f"MORE THAN {limit} TURN POINTS ARE NEEDED"
        )


def _solve(
    trip: _Trip,
    kind: RerouteKind,
    route: FlightRoute | None,
    dest: tuple[float, float] | None,
    simplify_nm: float,
) -> RerouteOption:
    if kind is RerouteKind.DIRECT_DEST and (route is None or dest is None):
        return _refusal(
            trip, kind, RerouteStatus.NO_DEST, "NO PUBLISHED ROUTE: DESTINATION UNKNOWN"
        )
    graph = _graph(trip.cone, trip.policy, simplify_nm)
    start = graph.proj.point(trip.flight.lat, trip.flight.lon)
    if _inside(graph, [start])[0]:
        return _refusal(trip, kind, RerouteStatus.START_INSIDE, "AIRCRAFT IS INSIDE THE BUFFER")
    if kind is RerouteKind.DIRECT_DEST:
        assert route is not None
        assert dest is not None
        ends = _destination_end(trip, graph, dest)
        if ends is None:
            return _refusal(
                trip, kind, RerouteStatus.DEST_INSIDE, f"{route.dest_icao} IS INSIDE THE BUFFER"
            )
    else:
        ends = _rejoin_ends(trip, graph, start)
        if isinstance(ends, RerouteOption):
            return ends
    found = _shortest(trip, graph, start, ends)
    if found is None:
        return _refusal(trip, kind, RerouteStatus.NO_ROUTE, "NO CLEAR PATH AROUND THE BUFFER")
    return _finish(trip, kind, route, graph, start, found)


def _inside(graph: _Graph, points: Sequence[tuple[float, float]]) -> NDArray[np.bool_]:
    marks = shapely.points(np.asarray(points, dtype=float))
    return np.atleast_1d(shapely.intersects(graph.inset, marks))


def _destination_end(trip: _Trip, graph: _Graph, dest: tuple[float, float]) -> list[_End] | None:
    x, y = graph.proj.point(*dest)
    if _inside(graph, [(x, y)])[0]:
        return None
    nm, east, north = _leg(*_arrays(trip.flight.lat, trip.flight.lon, *dest))
    speed = _ground_speed(trip.tas_kt, trip.wind, east, north)
    minutes = float(nm[0] / speed[0] * 60.0)
    return [_End(dest[0], dest[1], x, y, 0.0, float(nm[0]), minutes)]


def _arrays(*values: float) -> tuple[FloatArray, ...]:
    return tuple(np.array([value], dtype=float) for value in values)


def _rejoin_ends(
    trip: _Trip, graph: _Graph, start: tuple[float, float]
) -> list[_End] | RerouteOption:
    """Points on the present track beyond the obstacle, or the refusal that says why none."""
    kind = RerouteKind.REJOIN_TRACK
    track = trip.flight.track_deg
    if track is None:
        return _refusal(trip, kind, RerouteStatus.NO_ROUTE, "NO TRACK TO REJOIN")
    reroute = trip.policy.reroute
    window_nm = reroute.max_extra_min.value * trip.tas_kt / 60.0
    corners = np.array(graph.obstacle.bounds).reshape(2, 2)
    far = max(
        math.hypot(cx - start[0], cy - start[1]) for cx in corners[:, 0] for cy in corners[:, 1]
    )
    samples = np.arange(0.0, far + window_nm + 2 * RAY_STEP_NM, RAY_STEP_NM)
    lat, lon = _along(trip, track, samples)
    x, y = graph.proj.forward(lat, lon)
    legs = shapely.linestrings(
        np.stack([np.column_stack([x[:-1], y[:-1]]), np.column_stack([x[1:], y[1:]])], axis=1)
    )
    hits = np.flatnonzero(shapely.intersects(graph.inset, legs))
    if len(hits) == 0:
        note = "PRESENT TRACK DOES NOT MEET THE BUFFERED HAZARD AREA"
        return _refusal(trip, kind, RerouteStatus.NOT_EXPOSED, note)
    first = (int(hits[-1]) + 1) * RAY_STEP_NM
    step = float(reroute.rejoin_step_nm.value)
    distances = first + step * np.arange(int(window_nm // step) + 1)
    lat, lon = _along(trip, track, distances)
    px, py = graph.proj.forward(lat, lon)
    keep = ~_inside(graph, list(zip(px, py, strict=True)))
    if not keep.any():
        return _refusal(trip, kind, RerouteStatus.NO_ROUTE, "NO REJOIN POINT OUTSIDE THE BUFFER")
    east, north = math.sin(math.radians(track)), math.cos(math.radians(track))
    track_gs = float(_ground_speed(trip.tas_kt, trip.wind, np.array([east]), np.array([north]))[0])
    reference = float(distances[-1])
    return [
        _End(
            float(lat[i]),
            float(lon[i]),
            float(px[i]),
            float(py[i]),
            (reference - distances[i]) / track_gs * 60.0,
            float(distances[i]),
            float(distances[i]) / track_gs * 60.0,
        )
        for i in np.flatnonzero(keep)
    ]


def _along(trip: _Trip, bearing: float, distances: FloatArray) -> tuple[FloatArray, FloatArray]:
    points = [
        destination_point(trip.flight.lat, trip.flight.lon, bearing, nm_to_km(float(d)))
        for d in distances
    ]
    return np.array([p[0] for p in points]), np.array([p[1] for p in points])


def _shortest(
    trip: _Trip, graph: _Graph, start: tuple[float, float], ends: list[_End]
) -> _Found | None:
    count = len(graph.xy)
    vertex_cost = _minutes(trip, graph.nm, graph.east, graph.north)
    lat, lon = np.array([trip.flight.lat]), np.array([trip.flight.lon])
    to_start = _edge_costs(trip, graph, start, (lat, lon), outward=True)
    dist, prev = _dijkstra(vertex_cost, to_start)
    best: tuple[float, _End, int] | None = None
    for end in ends:
        arrival = _edge_costs(
            trip, graph, (end.x, end.y), (np.array([end.lat]), np.array([end.lon])), outward=False
        )
        direct = _direct_cost(trip, graph, start, end)
        via = dist + arrival
        index = int(via.argmin()) if count else -1
        reach = float(via[index]) if count else math.inf
        cost, last = (direct, -1) if direct <= reach else (reach, index)
        total = cost + end.tail_min
        if math.isfinite(total) and (best is None or total < best[0]):
            best = (total, end, last)
    if best is None:
        return None
    _, end, last = best
    vertices: list[int] = []
    while last >= 0:
        vertices.append(last)
        last = int(prev[last])
    return _Found(end=end, vertices=vertices[::-1])


def _minutes(trip: _Trip, nm: FloatArray, east: FloatArray, north: FloatArray) -> FloatArray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return nm / _ground_speed(trip.tas_kt, trip.wind, east, north) * 60.0


def _edge_costs(
    trip: _Trip,
    graph: _Graph,
    point: tuple[float, float],
    latlon: tuple[FloatArray, FloatArray],
    *,
    outward: bool,
) -> FloatArray:
    """Minutes between ``point`` and each vertex it sees: from it if ``outward``, else to it."""
    count = len(graph.xy)
    if count == 0:
        return np.empty(0)
    legs = shapely.linestrings(np.stack([np.tile(point, (count, 1)), graph.xy], axis=1))
    seen = ~shapely.intersects(graph.inset, legs)
    if outward:
        nm, east, north = _leg(latlon[0], latlon[1], graph.lat, graph.lon)
    else:
        nm, east, north = _leg(graph.lat, graph.lon, latlon[0], latlon[1])
    return np.where(seen, _minutes(trip, nm, east, north), np.inf)


def _direct_cost(trip: _Trip, graph: _Graph, start: tuple[float, float], end: _End) -> float:
    leg = shapely.linestrings([start, (end.x, end.y)])
    if shapely.intersects(graph.inset, leg):
        return math.inf
    nm, east, north = _leg(*_arrays(trip.flight.lat, trip.flight.lon, end.lat, end.lon))
    return float(_minutes(trip, nm, east, north)[0])


def _dijkstra(cost: FloatArray, first: FloatArray) -> tuple[FloatArray, NDArray[np.int64]]:
    """Dense Dijkstra from a virtual start whose edge costs to each vertex are ``first``.
    ``prev`` is -1 for a vertex reached from the start."""
    count = len(first)
    dist = first.copy()
    prev = np.full(count, -1, dtype=np.int64)
    done = np.zeros(count, dtype=bool)
    for _ in range(count):
        frontier = np.where(done, np.inf, dist)
        node = int(frontier.argmin())
        if not math.isfinite(frontier[node]):
            break
        done[node] = True
        via = dist[node] + cost[node]
        better = via < dist
        dist[better] = via[better]
        prev[better] = node
    return dist, prev


# --- result -------------------------------------------------------------------------------


def _finish(
    trip: _Trip,
    kind: RerouteKind,
    route: FlightRoute | None,
    graph: _Graph,
    start: tuple[float, float],
    found: _Found,
) -> RerouteOption:
    reroute = trip.policy.reroute
    end = found.end
    xy = [start, *map(tuple, graph.xy[found.vertices]), (end.x, end.y)]
    keep = _without_collinear(xy)
    turn_points = [
        (float(graph.lat[found.vertices[i - 1]]), float(graph.lon[found.vertices[i - 1]]))
        for i in keep
        if 0 < i < len(xy) - 1
    ]
    if len(turn_points) > reroute.max_waypoints_count.value:
        raise _TooManyTurnPoints
    rounded = [(_arc_minute(lat), _arc_minute(lon)) for lat, lon in turn_points]
    finish = (end.lat, end.lon) if kind is RerouteKind.DIRECT_DEST else _round_point(end)
    path = [(trip.flight.lat, trip.flight.lon), *rounded, finish]
    largest = _largest_turn(trip, kind, path)
    if largest > reroute.max_turn_deg.value:
        return _refusal(
            trip, kind, RerouteStatus.NO_ROUTE, f"A TURN OF {round(largest)} DEG IS NEEDED"
        )
    if _enters_guard(graph, path):
        return _refusal(
            trip, kind, RerouteStatus.NO_ROUTE, "ROUTE ENTERS THE BUFFER AFTER ROUNDING"
        )
    return _option(trip, kind, route, graph, path, end, largest)


def _without_collinear(points: Sequence[tuple[float, float]]) -> list[int]:
    """Indexes of ``points`` kept: the ends, and every point that is not on the line between
    its neighbours (a tie in the shortest path can run through a collinear vertex)."""
    kept = [0]
    for i in range(1, len(points) - 1):
        (ax, ay), (bx, by), (cx, cy) = points[kept[-1]], points[i], points[i + 1]
        chord = math.hypot(cx - ax, cy - ay)
        offset = abs((cx - ax) * (ay - by) - (ax - bx) * (cy - ay)) / chord if chord else 0.0
        if offset > COLLINEAR_NM:
            kept.append(i)
    kept.append(len(points) - 1)
    return kept


def _arc_minute(degrees: float) -> float:
    return round(degrees * 60.0) / 60.0


def _round_point(end: _End) -> tuple[float, float]:
    return _arc_minute(end.lat), _arc_minute(end.lon)


def _bearings(path: Sequence[tuple[float, float]]) -> list[float]:
    return [initial_bearing_deg(a[0], a[1], b[0], b[1]) for a, b in pairwise(path)]


def _largest_turn(trip: _Trip, kind: RerouteKind, path: Sequence[tuple[float, float]]) -> float:
    """The biggest track change: onto the first leg, at each turn point and, for a rejoin,
    back onto the present track."""
    bearings = _bearings(path)
    track = trip.flight.track_deg
    sequence = bearings if track is None else [track, *bearings]
    if kind is RerouteKind.REJOIN_TRACK and track is not None:
        sequence = [*sequence, track]
    return max((bearing_diff_deg(a, b) for a, b in pairwise(sequence)), default=0.0)


def _enters_guard(graph: _Graph, path: Sequence[tuple[float, float]]) -> bool:
    """Whether the great-circle route, sampled every 25 NM, comes closer to the cone than the
    buffer less the rounding slack."""
    points: list[tuple[float, float]] = []
    for a, b in pairwise(path):
        nm, _, _ = _leg(*_arrays(a[0], a[1], b[0], b[1]))
        bearing = initial_bearing_deg(a[0], a[1], b[0], b[1])
        count = max(1, math.ceil(float(nm[0]) / GREAT_CIRCLE_STEP_NM))
        points.extend(
            destination_point(a[0], a[1], bearing, nm_to_km(float(nm[0]) * i / count))
            for i in range(count)
        )
    points.append(path[-1])
    lat, lon = np.array([p[0] for p in points]), np.array([p[1] for p in points])
    x, y = graph.proj.forward(lat, lon)
    return bool(shapely.intersects(graph.guard, shapely.linestrings(np.column_stack([x, y]))))


def _path_minutes(trip: _Trip, path: Sequence[tuple[float, float]]) -> tuple[float, float, float]:
    """Length (NM), time (min) and the tail-wind part of the legs, summed over the route."""
    lat1, lon1 = np.array([p[0] for p in path[:-1]]), np.array([p[1] for p in path[:-1]])
    lat2, lon2 = np.array([p[0] for p in path[1:]]), np.array([p[1] for p in path[1:]])
    nm, east, north = _leg(lat1, lon1, lat2, lon2)
    minutes = _minutes(trip, nm, east, north)
    tail = 0.0
    if trip.wind is not None:
        tail = float(
            np.sum((trip.wind.east_kt * east + trip.wind.north_kt * north) * nm) / nm.sum()
        )
    return float(nm.sum()), float(minutes.sum()), tail


def _option(
    trip: _Trip,
    kind: RerouteKind,
    route: FlightRoute | None,
    graph: _Graph,
    path: list[tuple[float, float]],
    end: _End,
    largest_turn: float,
) -> RerouteOption:
    reroute = trip.policy.reroute
    dist_nm, time_min, tail_kt = _path_minutes(trip, path)
    extra_nm, extra_min = dist_nm - end.baseline_nm, time_min - end.baseline_min
    turn_count = len(path) - 2
    if turn_count == 0:
        status, note = RerouteStatus.OK, "DIRECT TO THE DESTINATION CLEARS THE BUFFER"
    elif extra_min > reroute.max_extra_min.value:
        status, note = RerouteStatus.TOO_LONG, f"{_whole(extra_min)} MIN EXTRA IS OVER THE LIMIT"
    elif extra_min < reroute.min_extra_min.value:
        status, note = RerouteStatus.NO_BENEFIT, "LESS THAN THE MINIMUM EXTRA TIME"
    else:
        status, note = RerouteStatus.OK, "LATERAL ROUTE AROUND THE BUFFERED HAZARD"
    waypoints: list[Position] = [(lon, lat) for lat, lon in path[1:-1]]
    route_string = _route_string(kind, route, path)
    return RerouteOption(
        id=_option_id(trip, kind, path, route),
        flight_id=trip.flight.id,
        cone_id=trip.cone.id,
        kind=kind,
        status=status,
        note=note,
        side=_side(kind, graph, trip.flight.track_deg, path),
        fl=trip.fl,
        waypoints=waypoints,
        end=(path[-1][1], path[-1][0]),
        end_icao=route.dest_icao if kind is RerouteKind.DIRECT_DEST and route else None,
        path=[(lon, lat) for lat, lon in path],
        dist_nm=round(dist_nm, 1),
        extra_nm=round(extra_nm, 1),
        time_min=round(time_min, 1),
        extra_min=round(extra_min, 1),
        buffer_nm=reroute.buffer_nm.value,
        max_turn_deg=round(largest_turn, 1),
        fuel=reroute_line(trip.flight.category, extra_min, extra_nm),
        route_string=route_string,
        wind_note=_wind_note(trip, tail_kt),
    )


def _side(
    kind: RerouteKind,
    graph: _Graph,
    track_deg: float | None,
    path: Sequence[tuple[float, float]],
) -> Literal["LEFT", "RIGHT"] | None:
    """Which side of the reference line the route swings furthest to: the present track for
    a rejoin, else the direct line to the destination."""
    if len(path) < 3:
        return None
    points = [graph.proj.point(lat, lon) for lat, lon in path]
    (sx, sy), (ex, ey) = points[0], points[-1]
    if kind is RerouteKind.REJOIN_TRACK and track_deg is not None:
        dx, dy = math.sin(math.radians(track_deg)), math.cos(math.radians(track_deg))
    else:
        dx, dy = ex - sx, ey - sy
    widest = max((dx * (py - sy) - dy * (px - sx) for px, py in points[1:-1]), key=abs)
    return "LEFT" if widest > 0 else "RIGHT"


def _whole(value: float) -> int:
    return math.ceil(round(value, 6))


def _wind_note(trip: _Trip, tail_kt: float) -> str:
    wind = trip.wind
    if wind is None:
        return f"NO WIND DATA: TIMED AT {round(trip.tas_kt)} KT TRUE AIRSPEED"
    kind = "TAILWIND" if tail_kt >= 0 else "HEADWIND"
    return (
        f"WIND FL{trip.fl:03d} {round(wind.from_deg) % 360:03d}/{round(wind.speed_kt)} KT,"
        f" {round(abs(tail_kt))} KT {kind} ON THE ROUTE"
    )


def _route_string(
    kind: RerouteKind, route: FlightRoute | None, path: Sequence[tuple[float, float]]
) -> str:
    """``DCT 0540S10930E DCT 0701S11215E DCT WADD``; a rejoin ends on its coordinate then DCT."""
    tokens = [f"DCT {coordinate_text(lat, lon)}" for lat, lon in path[1:-1]]
    if kind is RerouteKind.DIRECT_DEST and route is not None:
        tokens.append(f"DCT {route.dest_icao}")
    else:
        tokens += [f"DCT {coordinate_text(*path[-1])}", "DCT"]
    return " ".join(tokens)


def coordinate_text(lat: float, lon: float) -> str:
    """ICAO ``DDMM[NS]DDDMM[EW]`` to the nearest arc-minute (``0812S11245E``)."""
    lat_min, lon_min = round(abs(lat) * 60.0), round(abs(lon) * 60.0)
    return (
        f"{lat_min // 60:02d}{lat_min % 60:02d}{'S' if lat < 0 else 'N'}"
        f"{lon_min // 60:03d}{lon_min % 60:02d}{'W' if lon < 0 else 'E'}"
    )


def _option_id(
    trip: _Trip,
    kind: RerouteKind,
    path: Sequence[tuple[float, float]] = (),
    route: FlightRoute | None = None,
) -> str:
    """By content, not by cone or position: the kind, the level, the turn points around the
    hazard and, direct, the destination. The start is the aircraft and the rejoin point moves
    with it every tick, so both stay out: the same way round at the same level keeps its id
    while the flight flies on and under a reissued cone, and a kept plan that names it still
    passes the checks."""
    turns = " ".join(coordinate_text(lat, lon) for lat, lon in path[1:-1])
    dest = route.dest_icao if kind is RerouteKind.DIRECT_DEST and route is not None else ""
    return stable_id("RR", trip.flight.id, kind.value, sha256_text(f"{turns}|{dest}|{trip.fl}"))


def _refusal(trip: _Trip, kind: RerouteKind, status: RerouteStatus, note: str) -> RerouteOption:
    return RerouteOption(
        id=_option_id(trip, kind),
        flight_id=trip.flight.id,
        cone_id=trip.cone.id,
        kind=kind,
        status=status,
        note=note,
        fl=trip.fl,
        buffer_nm=trip.policy.reroute.buffer_nm.value,
    )
