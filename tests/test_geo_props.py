"""Property tests for the safety rules in geo: the cone never shrinks below the official
floor, every track that enters it is reported, and the fuel formula reproduces itself."""

import math
import re
from datetime import UTC, datetime, timedelta
from itertools import pairwise

import numpy as np
import shapely
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from tephra.geo.cone import build_cone, contains_point, covers_official, geometry_to_shape
from tephra.geo.exposure import MIN_MOVING_GS_KT, find_exposed
from tephra.geo.fuel import BURN_KG_PER_MIN, divert_line
from tephra.geo.units import (
    destination_point,
    fl_to_ft,
    ft_to_fl,
    initial_bearing_deg,
    kt_to_km_per_min,
)
from tephra.models import (
    Aircraft,
    AircraftCategory,
    GeoPolygon,
    HazardCone,
    OfficialLayer,
    PlumeAssessment,
    PlumeEstimate,
    PlumeMode,
    Position,
    RunMode,
    Situation,
    VaacCentre,
    Volcano,
)

AT = datetime(2026, 10, 9, 19, 0, tzinfo=UTC)
VENT = Volcano(
    id="263300",
    name="Semeru",
    country="Indonesia",
    lat=-8.108,
    lon=112.922,
    summit_elev_m=3676,
    observatory="PVMBG",
    vaac=VaacCentre.DARWIN,
)
EDGE_TOLERANCE_DEG = 1e-4
"""About 11 m. The straight lon/lat chord between one-minute points and the great circle differ
by a few metres, so a track this close to a cone edge is not evidence either way."""
DENSE_STEPS_PER_MIN = 20


# --- builders ---------------------------------------------------------------------------


@st.composite
def feed_rings(draw: st.DrawFn) -> list[Position]:
    """Closed rings as a forecaster might type them, on an arc-minute grid around the vent.

    Any vertex order is allowed, so rings cross, fold back over themselves, touch themselves,
    repeat points and make slivers; a vertex can sit on the vent. Spans run from a small VAA
    polygon (a few km, narrower than a minute of jet flight) to a few hundred km.
    """
    span = draw(st.sampled_from([4, 12, 90]))
    minutes = st.tuples(st.integers(-span, span), st.integers(-span, span))
    offsets = draw(st.lists(minutes, min_size=3, max_size=9))
    ring = [(VENT.lon + dx / 60.0, VENT.lat + dy / 60.0) for dx, dy in offsets]
    if draw(st.booleans()):
        ring[draw(st.integers(0, len(ring) - 1))] = (VENT.lon, VENT.lat)
    assume(len(set(ring)) >= 3)
    return [*ring, ring[0]]


def _layer(ring: list[Position], index: int, base_ft: int, top_ft: int) -> OfficialLayer:
    return OfficialLayer(
        source_id=f"SIGMET:WAAF:{index}:20261009T1820Z",
        kind="SIGMET",
        layer="SIGMET",
        label=f"SIGMET WAAF {index}",
        volcano_id=VENT.id,
        polygon=GeoPolygon(coordinates=[ring]),
        base_ft=base_ft,
        top_ft=top_ft,
        valid_from=AT - timedelta(hours=1),
        valid_to=AT + timedelta(hours=5),
    )


def _estimate(
    mode: PlumeMode,
    *,
    base_fl: int = 0,
    top_fl: int = 150,
    bearing_from_deg: float = 0.0,
    bearing_to_deg: float = 0.0,
    extent_km: float = 0.0,
) -> PlumeEstimate:
    return PlumeEstimate(
        mode=mode,
        base_fl=base_fl,
        top_fl=top_fl,
        bearing_from_deg=bearing_from_deg,
        bearing_to_deg=bearing_to_deg,
        extent_km=extent_km,
        horizon_h=6.0,
        confidence=0.5,
        sources_used=[],
        disagreements_explained=[],
        uncertainty_notes="",
        rationale="",
    )


def _cone(layers: list[OfficialLayer], estimate: PlumeEstimate) -> HazardCone:
    situation = Situation(
        volcano=VENT, as_of=AT, mode=RunMode.REPLAY, active_reasons=["test"], official_layers=layers
    )
    assessment = PlumeAssessment(
        id="PA-0123456789ab",
        volcano_id=VENT.id,
        created_at=AT,
        input_hash="1" * 64,
        estimate=estimate,
        llm_backend="stub",
        model_id="stub",
        prompt_hash="2" * 64,
        outcome="STUB",
        attempts=0,
    )
    return build_cone(situation, assessment)


def _aircraft(lat: float, lon: float, gs_kt: float | None, track_deg: float | None) -> Aircraft:
    return Aircraft(
        hex="8a01f2",
        callsign="GIA417",
        lat=lat,
        lon=lon,
        alt_baro_ft=12_000,
        gs_kt=gs_kt,
        track_deg=track_deg,
        observed_at=AT,
        source_id="ADSB:-8.200:113.600:20261009T190000Z",
    )


# --- oracles ----------------------------------------------------------------------------


def _winding_number(x: float, y: float, ring: list[Position]) -> int:
    """How many times the closed ring winds around the point (no shapely involved)."""
    winding = 0
    for (x1, y1), (x2, y2) in pairwise(ring):
        side = (x2 - x1) * (y - y1) - (x - x1) * (y2 - y1)
        if y1 <= y < y2 and side > 0:
            winding += 1
        elif y2 <= y < y1 and side < 0:
            winding -= 1
    return winding


def _near_an_edge(x: float, y: float, ring: list[Position]) -> bool:
    for (x1, y1), (x2, y2) in pairwise(ring):
        dx, dy = x2 - x1, y2 - y1
        length2 = dx * dx + dy * dy
        t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / length2))
        if math.hypot(x - (x1 + t * dx), y - (y1 + t * dy)) < EDGE_TOLERANCE_DEG:
            return True
    return False


def _enclosed_points(ring: list[Position], *, per_side: int = 13) -> list[tuple[float, float]]:
    """``(lat, lon)`` grid points the ring winds around: inside by any fill rule."""
    xs = [x for x, _ in ring]
    ys = [y for _, y in ring]
    points = []
    for i in range(per_side):
        for j in range(per_side):
            x = min(xs) + (max(xs) - min(xs)) * (i + 0.5) / per_side
            y = min(ys) + (max(ys) - min(ys)) * (j + 0.381966) / per_side
            if _winding_number(x, y, ring) != 0 and not _near_an_edge(x, y, ring):
                points.append((y, x))
    return points


def _entry_bounds(
    shape: shapely.Geometry, dense: list[tuple[float, float]]
) -> tuple[float | None, float | None]:
    """From a densely sampled track: by when it is surely inside the shape, and the earliest
    it comes within the edge tolerance of it (minutes), each None if never."""
    inner = shape.buffer(-EDGE_TOLERANCE_DEG)
    outer = shape.buffer(EDGE_TOLERANCE_DEG)
    start = shapely.Point(dense[0][1], dense[0][0])
    if len(dense) == 1:
        return (0.0 if inner.covers(start) else None), (0.0 if outer.covers(start) else None)
    coords = np.array([(lon, lat) for lat, lon in dense])
    segments = shapely.linestrings(np.stack([coords[:-1], coords[1:]], axis=1))
    sure = np.flatnonzero(shapely.intersects(inner, segments))
    near = np.flatnonzero(shapely.intersects(outer, segments))
    surely_in = 0.0 if inner.covers(start) else None
    if surely_in is None and sure.size:
        surely_in = (sure[0] + 1) / DENSE_STEPS_PER_MIN
    return surely_in, (near[0] / DENSE_STEPS_PER_MIN if near.size else None)


# --- the cone ---------------------------------------------------------------------------


@settings(max_examples=300, deadline=None)
@given(
    rings=st.lists(feed_rings(), min_size=1, max_size=3),
    bands=st.lists(st.tuples(st.sampled_from([0, 5_000, 20_000]), st.integers(1, 40)), min_size=3),
    mode=st.sampled_from(list(PlumeMode)),
    bearing_from=st.floats(0.0, 360.0),
    bearing_to=st.floats(0.0, 360.0),
    extent_km=st.one_of(st.just(0.0), st.floats(0.0, 500.0)),
    base_fl=st.integers(0, 300),
    top_fl=st.integers(0, 600),
)
def test_cone_contains_everything_the_official_rings_enclose(
    rings: list[list[Position]],
    bands: list[tuple[int, int]],
    mode: PlumeMode,
    bearing_from: float,
    bearing_to: float,
    extent_km: float,
    base_fl: int,
    top_fl: int,
) -> None:
    layers = [
        _layer(ring, i, base, base + depth * 1_000)
        for i, (ring, (base, depth)) in enumerate(zip(rings, bands, strict=False))
    ]
    estimate = _estimate(
        mode,
        base_fl=base_fl,
        top_fl=top_fl,
        bearing_from_deg=bearing_from,
        bearing_to_deg=bearing_to,
        extent_km=extent_km,
    )
    cone = _cone(layers, estimate)

    assert covers_official(cone, layers)
    assert cone.base_ft <= min(layer.base_ft for layer in layers)
    assert cone.top_ft >= max(layer.top_ft for layer in layers)
    for ring in rings:
        for lat, lon in _enclosed_points(ring):
            assert contains_point(cone, lat, lon), (lat, lon)
    if mode is PlumeMode.OFFICIAL:
        assert cone.sector is None
    if cone.geometry is not None:
        assert shapely.geometry.shape(cone.geometry.model_dump()).is_valid
    if cone.geometry is not None and cone.sector is not None:
        stored = geometry_to_shape(cone.geometry, ref_lon=VENT.lon)
        sector = geometry_to_shape(cone.sector, ref_lon=VENT.lon)
        assert stored.covers(sector) or sector.difference(stored).area <= 1e-12


# --- exposure ---------------------------------------------------------------------------


@settings(max_examples=300, deadline=None)
@given(
    ring=feed_rings(),
    aim=st.tuples(st.floats(0.05, 0.95), st.floats(0.05, 0.95)),
    approach_deg=st.floats(0.0, 360.0),
    distance_km=st.floats(0.0, 600.0),
    miss_deg=st.floats(-20.0, 20.0),
    gs_kt=st.one_of(st.none(), st.just(0.0), st.floats(0.0, 600.0)),
    has_track=st.booleans(),
)
def test_every_track_that_enters_the_cone_is_reported(
    ring: list[Position],
    aim: tuple[float, float],
    approach_deg: float,
    distance_km: float,
    miss_deg: float,
    gs_kt: float | None,
    has_track: bool,
) -> None:
    cone = _cone([_layer(ring, 0, 0, 15_000)], _estimate(PlumeMode.OFFICIAL))
    assume(cone.geometry is not None)
    assert cone.geometry is not None
    shape = geometry_to_shape(cone.geometry, ref_lon=VENT.lon)
    xs = [x for x, _ in ring]
    ys = [y for _, y in ring]
    aim_lon = min(xs) + (max(xs) - min(xs)) * aim[0]
    aim_lat = min(ys) + (max(ys) - min(ys)) * aim[1]
    lat, lon = destination_point(aim_lat, aim_lon, approach_deg, distance_km)
    track = (initial_bearing_deg(lat, lon, aim_lat, aim_lon) + miss_deg) % 360
    target = _aircraft(lat, lon, gs_kt, track if has_track else None)
    flights = find_exposed(cone, [target], AT, lookahead_min=60, vertical_margin_ft=2_000)

    if gs_kt is not None and has_track and gs_kt >= MIN_MOVING_GS_KT:
        km_per_step = kt_to_km_per_min(gs_kt) / DENSE_STEPS_PER_MIN
        steps = 60 * DENSE_STEPS_PER_MIN
        dense = [destination_point(lat, lon, track, km_per_step * i) for i in range(steps + 1)]
    else:
        dense = [(lat, lon)]
    surely_in, earliest = _entry_bounds(shape, dense)

    if surely_in is not None:
        (flight,) = flights
        assert flight.minutes_to_entry <= math.ceil(surely_in)
    for flight in flights:
        assert earliest is not None
        assert flight.minutes_to_entry >= math.floor(earliest)
        assert flight.inside_now is (flight.minutes_to_entry == 0)
        numbers = [flight.entry_lat, flight.entry_lon, *(v for p in flight.path for v in p)]
        assert all(math.isfinite(value) for value in numbers)


@settings(max_examples=100, deadline=None)
@given(
    lat=st.floats(-10.0, 10.0),
    lon=st.floats(105.0, 130.0),
    gs_kt=st.sampled_from([math.nan, math.inf, -math.inf]),
    track_deg=st.one_of(st.floats(0.0, 360.0), st.just(math.nan)),
)
def test_exposure_never_projects_a_non_finite_speed(
    lat: float, lon: float, gs_kt: float, track_deg: float
) -> None:
    box = [(lon - 0.5, lat - 0.5), (lon + 0.5, lat - 0.5), (lon + 0.5, lat + 0.5),
           (lon - 0.5, lat + 0.5), (lon - 0.5, lat - 0.5)]  # fmt: skip
    cone = _cone([_layer(box, 0, 0, 15_000)], _estimate(PlumeMode.OFFICIAL))
    target = _aircraft(lat, lon, gs_kt, track_deg)
    (flight,) = find_exposed(cone, [target], AT, lookahead_min=60, vertical_margin_ft=2_000)
    assert flight.inside_now
    assert (flight.entry_lat, flight.entry_lon) == (lat, lon)


# --- fuel and units ---------------------------------------------------------------------

_DIVERT = re.compile(
    r"DIVERT WARR (\d+) NM AT (\d+) KT(?: \(ASSUMED\))? = (\d+) MIN \+ 15 MIN = (\d+) MIN"
    r" x (\d+) KG/MIN \(.+\) = (\d+) KG"
)


@settings(max_examples=300, deadline=None)
@given(
    distance_nm=st.floats(0.0, 900.0),
    gs_kt=st.one_of(st.none(), st.just(math.nan), st.floats(0.0, 700.0)),
    category=st.sampled_from(list(AircraftCategory)),
)
def test_divert_formula_reproduces_its_own_numbers(
    distance_nm: float, gs_kt: float | None, category: AircraftCategory
) -> None:
    line = divert_line(category, alternate_icao="WARR", distance_nm=distance_nm, gs_kt=gs_kt)
    match = _DIVERT.fullmatch(line.formula)
    assert match is not None, line.formula
    distance, speed, cruise, total, burn, fuel = (int(group) for group in match.groups())
    assert cruise == -(-distance * 60 // speed)
    assert total == cruise + 15 == line.minutes
    assert burn == BURN_KG_PER_MIN[category]
    assert fuel == total * burn == line.fuel_kg


@given(ft=st.floats(-2_000.0, 70_000.0))
def test_flight_level_is_the_nearest_hundred_feet(ft: float) -> None:
    fl = ft_to_fl(ft)
    assert abs(fl * 100 - ft) <= 50
    assert fl_to_ft(fl) == fl * 100
    assert ft_to_fl(ft + 1.0) >= fl
