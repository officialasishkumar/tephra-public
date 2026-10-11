"""Lateral reroute geometry (``tephra.geo.reroute``): cases T1 to T13 of research/18a, the
property that no route enters the unbuffered cone, wind pricing and a speed benchmark.

Distances to the cone are measured in the same local plane the planner uses, on the route
sampled along its great circles, so a leg that cuts a corner would show.
"""

import math
import random
import re
import time
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
import shapely
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from shapely.geometry import Polygon

from tephra.config import PROJECT_ROOT
from tephra.geo import reroute
from tephra.geo.fuel import category_for_type, hold_line, reroute_line
from tephra.geo.reroute import coordinate_text, plan_reroutes
from tephra.geo.units import destination_point, distance_nm, initial_bearing_deg, nm_to_km
from tephra.models import (
    ExposedFlight,
    FeedId,
    FlightRoute,
    GeoMultiPolygon,
    HazardCone,
    OperatorPolicy,
    PlumeMode,
    PolicyValue,
    Provenance,
    RerouteKind,
    RerouteOption,
    RerouteStatus,
    RunMode,
    Situation,
    VaacCentre,
    Volcano,
    WindLevel,
    WindProfile,
    polygon_from_latlon,
)
from tephra.policy import load_policy

AT = datetime(2026, 10, 9, 18, 30, tzinfo=UTC)
POLICY = load_policy(PROJECT_ROOT / "data")
BUFFER_NM = POLICY.reroute.buffer_nm.value
CATEGORY = category_for_type("B738")
CENTRE = (-7.45, 110.9)  # midway between WIII and WADD
WIII = (-6.1256, 106.656)
WADD = (-8.7482, 115.1672)
ROUTE = FlightRoute(callsign="GIA417", origin_icao="WIII", dest_icao="WADD", cross_track_nm=3.0)
ROUNDING_NM = 1.0  # a turn point rounded to one arc-minute moves by under this


@pytest.fixture(autouse=True)
def fresh_cache() -> None:
    reroute.clear_cache()


def circle(lat: float, lon: float, radius_nm: float, points: int = 64) -> list[tuple[float, float]]:
    return [
        destination_point(lat, lon, i * 360.0 / points, nm_to_km(radius_nm)) for i in range(points)
    ]


def make_cone(
    ring: list[tuple[float, float]] | None = None,
    *,
    base_ft: int = 0,
    top_ft: int = 40_000,
    cone_id: str = "CONE-0123456789ab",
) -> HazardCone:
    return HazardCone(
        id=cone_id,
        volcano_id="263300",
        assessment_id="PA-0123456789ab",
        mode=PlumeMode.OFFICIAL,
        confidence=0.8,
        llm_backend="stub",
        created_at=AT,
        horizon_h=6.0,
        valid_to=AT + timedelta(hours=6),
        geometry=polygon_from_latlon(ring or circle(*CENTRE, 40.0)),
        base_ft=base_ft,
        top_ft=top_ft,
        official_source_ids=[],
    )


def make_flight(
    lat: float = WIII[0],
    lon: float = WIII[1],
    track: float | None = 107.0,
    *,
    alt_ft: int = 35_000,
    gs: float | None = 450.0,
    hex_id: str = "8a0123",
) -> ExposedFlight:
    return ExposedFlight(
        id=f"{hex_id}:263300",
        hex=hex_id,
        callsign="GIA417",
        proxy_flight="RFA417",
        type_icao="B738",
        category=CATEGORY,
        lat=lat,
        lon=lon,
        alt_baro_ft=alt_ft,
        gs_kt=gs,
        track_deg=track,
        observed_at=AT,
        source_id="ADSB:test",
        volcano_id="263300",
        cone_id="CONE-0123456789ab",
        inside_now=False,
        minutes_to_entry=20,
        entry_lat=CENTRE[0],
        entry_lon=CENTRE[1],
        aircraft_band_ft=(alt_ft, alt_ft),
        hazard_band_ft=(0, 40_000),
        path=[(lon, lat), (lon, lat)],
        hold=hold_line(CATEGORY, minutes=20),
    )


def make_situation(from_deg: float | None = None, speed_kt: float = 0.0) -> Situation:
    volcano = Volcano(
        id="263300",
        name="Semeru",
        country="Indonesia",
        lat=-8.108,
        lon=112.922,
        summit_elev_m=3676,
        observatory="PVMBG",
        vaac=VaacCentre.DARWIN,
    )
    winds: list[WindProfile] = []
    if from_deg is not None:
        levels = [
            WindLevel(pressure_hpa=hpa, flight_level=fl, speed_kt=speed_kt, from_deg=from_deg)
            for hpa, fl in ((500, 180), (300, 300), (200, 390))
        ]
        provenance = Provenance(
            source_id="WINDS:test",
            feed=FeedId.WINDS,
            url="https://example.invalid/winds",
            fetched_at=AT,
            sha256="ab" * 32,
        )
        winds = [
            WindProfile(provenance=provenance, lat=-8.1, lon=112.9, valid_at=AT, levels=levels)
        ]
    return Situation(
        volcano=volcano, as_of=AT, mode=RunMode.LIVE, active_reasons=["SIGMET"], winds=winds
    )


def with_policy(**values: int) -> OperatorPolicy:
    """The test policy with some ``reroute`` values replaced."""
    changed = {
        name: PolicyValue(value=value, unit=getattr(POLICY.reroute, name).unit, source="test")
        for name, value in values.items()
    }
    return POLICY.model_copy(update={"reroute": POLICY.reroute.model_copy(update=changed)})


def plan(
    flight: ExposedFlight | None = None,
    cone: HazardCone | None = None,
    *,
    situation: Situation | None = None,
    route: FlightRoute | None = ROUTE,
    policy: OperatorPolicy = POLICY,
) -> dict[RerouteKind, RerouteOption]:
    options = plan_reroutes(
        flight or make_flight(),
        cone or make_cone(),
        situation,
        route,
        policy,
        dest_position=WADD if route is not None else None,
    )
    return {option.kind: option for option in options}


def route_points(option: RerouteOption, spacing_nm: float = 5.0) -> list[tuple[float, float]]:
    """``(lat, lon)`` along the route's great circles, from the present position to its end."""
    points: list[tuple[float, float]] = []
    legs = list(zip(option.path, option.path[1:], strict=False))
    for (lon1, lat1), (lon2, lat2) in legs:
        distance = distance_nm(lat1, lon1, lat2, lon2)
        bearing = initial_bearing_deg(lat1, lon1, lat2, lon2)
        steps = max(1, math.ceil(distance / spacing_nm))
        points += [
            destination_point(lat1, lon1, bearing, nm_to_km(distance * i / steps))
            for i in range(steps)
        ]
    points.append((option.path[-1][1], option.path[-1][0]))
    return points


def distance_to_cone_nm(cone: HazardCone, points: list[tuple[float, float]]) -> float:
    """Least distance (NM) from the points to the cone, 0 when any is inside it."""
    assert cone.geometry is not None
    graph = reroute._graph(cone, POLICY, float(POLICY.reroute.simplify_nm.value))
    core = graph.proj.project(reroute._cone_shape(cone))
    lat = np.array([p[0] for p in points])
    lon = np.array([p[1] for p in points])
    x, y = graph.proj.forward(lat, lon)
    return float(shapely.distance(core, shapely.points(np.column_stack([x, y]))).min())


# --- T1 to T13 --------------------------------------------------------------------------


def test_t1_circular_cone_on_the_track_gives_a_short_lateral_route() -> None:
    cone = make_cone()
    options = plan(cone=cone)
    for option in options.values():
        assert option.status is RerouteStatus.OK, option.note
        assert 1 <= len(option.waypoints) <= POLICY.reroute.max_waypoints_count.value
        assert option.side in ("LEFT", "RIGHT")
        assert option.fl == 350
        # analytic detour about 13 to 16 NM (research/18a T1); the polygon adds a little
        assert option.extra_nm is not None
        assert 8 <= option.extra_nm <= 25
        assert distance_to_cone_nm(cone, route_points(option)) >= BUFFER_NM - ROUNDING_NM
    direct = options[RerouteKind.DIRECT_DEST]
    assert direct.end_icao == "WADD"
    assert direct.route_string.endswith("DCT WADD")
    assert direct.end == pytest.approx((WADD[1], WADD[0]))
    rejoin = options[RerouteKind.REJOIN_TRACK]
    assert rejoin.end_icao is None
    assert rejoin.route_string.endswith("DCT")
    assert direct.fuel is not None
    assert direct.fuel.formula.startswith("REROUTE +")


def test_t2_cone_offset_from_the_track_is_not_exposed() -> None:
    far = destination_point(*CENTRE, 0.0, nm_to_km(100.0))
    options = plan(cone=make_cone(circle(*far, 40.0)))
    assert {o.status for o in options.values()} == {RerouteStatus.NOT_EXPOSED}
    assert all(not o.waypoints and o.route_string == "" for o in options.values())


def test_t3_destination_inside_the_buffer_has_no_direct_route() -> None:
    cone = make_cone(circle(*WADD, 40.0))
    options = plan(cone=cone)
    direct = options[RerouteKind.DIRECT_DEST]
    assert direct.status is RerouteStatus.DEST_INSIDE
    assert direct.route_string == ""
    assert not direct.waypoints


def test_t4_aircraft_inside_the_buffer_has_no_route() -> None:
    inside = destination_point(*CENTRE, 90.0, nm_to_km(55.0))  # outside the cone, inside buffer
    options = plan(make_flight(*inside, track=270.0))
    assert {o.status for o in options.values()} == {RerouteStatus.START_INSIDE}


def test_t5_vertical_band_decides_exposure() -> None:
    cone = make_cone(base_ft=40_000, top_ft=60_000)
    margin = POLICY.exposure.vertical_margin_ft.value
    clear = plan(make_flight(alt_ft=40_000 - margin - 1_000), cone)
    assert {o.status for o in clear.values()} == {RerouteStatus.NOT_EXPOSED}
    meets = plan(make_flight(alt_ft=40_000 - margin + 500), cone)
    assert meets[RerouteKind.DIRECT_DEST].status is RerouteStatus.OK


def multi(polygons: list[Polygon]) -> GeoMultiPolygon:
    return GeoMultiPolygon(coordinates=[[list(p.exterior.coords)] for p in polygons])


def test_t6_two_cones_closer_than_twice_the_buffer_are_one_obstacle() -> None:
    north = destination_point(*CENTRE, 0.0, nm_to_km(40.0))  # 25 NM discs, 30 NM apart
    south = destination_point(*CENTRE, 180.0, nm_to_km(40.0))
    polygons = [
        Polygon([(lon, lat) for lat, lon in circle(*centre, 25.0)]) for centre in (north, south)
    ]
    cone = make_cone().model_copy(update={"geometry": multi(polygons)})
    direct = plan(cone=cone)[RerouteKind.DIRECT_DEST]
    assert direct.status is RerouteStatus.OK, direct.note
    assert distance_to_cone_nm(cone, route_points(direct)) >= BUFFER_NM - ROUNDING_NM
    # the route passes beyond both discs rather than threading the 30 NM gap between them
    near = [lat for lat, lon in route_points(direct) if abs(lon - CENTRE[1]) < 0.3]
    assert max(near) > north[0] or min(near) < south[0]


def test_t8_wind_decides_the_side_when_the_legs_differ() -> None:
    start = destination_point(*CENTRE, 270.0, nm_to_km(160.0))
    flight = make_flight(*start, track=90.0)
    dest = destination_point(*CENTRE, 90.0, nm_to_km(400.0))
    route = FlightRoute(callsign="GIA417", origin_icao="WIII", dest_icao="WADD", cross_track_nm=1.0)

    def side(from_deg: float) -> str | None:
        options = plan_reroutes(
            flight,
            make_cone(),
            make_situation(from_deg, 80.0),
            route,
            POLICY,
            dest_position=dest,
        )
        direct = next(o for o in options if o.kind is RerouteKind.DIRECT_DEST)
        assert direct.status is RerouteStatus.OK
        return direct.side

    assert side(0.0) == "RIGHT"  # wind from the north: the long leg runs south of east
    assert side(180.0) == "LEFT"
    note = plan(flight, situation=make_situation(0.0, 80.0))[RerouteKind.DIRECT_DEST].wind_note
    assert note is not None
    assert re.fullmatch(r"WIND FL350 000/80 KT, \d+ KT (TAIL|HEAD)WIND ON THE ROUTE", note)


def test_t9_property_no_route_enters_the_cone_and_the_obstacle_covers_it() -> None:
    @given(
        radii=st.lists(st.floats(18.0, 70.0), min_size=5, max_size=14),
        offset=st.floats(-60.0, 60.0),
        seed=st.integers(0, 10_000),
    )
    @settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def check(radii: list[float], offset: float, seed: int) -> None:
        count = len(radii)
        centre = destination_point(*CENTRE, 0.0, nm_to_km(offset))
        ring = [
            destination_point(*centre, i * 360.0 / count, nm_to_km(r)) for i, r in enumerate(radii)
        ]
        cone = make_cone(ring, cone_id=f"CONE-{seed:012d}")
        reroute.clear_cache()
        for option in plan(cone=cone).values():
            if option.status is RerouteStatus.OK:
                assert distance_to_cone_nm(cone, route_points(option)) >= BUFFER_NM - ROUNDING_NM
        graph = reroute._graph(cone, POLICY, float(POLICY.reroute.simplify_nm.value))
        assert graph.obstacle.contains(graph.proj.project(reroute._cone_shape(cone)))

    check()


def test_t10_rounded_turn_points_stay_clear_by_the_buffer_less_one_mile() -> None:
    cone = make_cone()
    direct = plan(cone=cone)[RerouteKind.DIRECT_DEST]
    for lon, lat in direct.waypoints:
        assert round(lat * 60) == pytest.approx(lat * 60, abs=1e-6)
        assert round(lon * 60) == pytest.approx(lon * 60, abs=1e-6)
        assert distance_to_cone_nm(cone, [(lat, lon)]) >= BUFFER_NM - ROUNDING_NM


def test_t11_a_turn_over_the_limit_is_refused_never_accepted() -> None:
    option = plan(policy=with_policy(max_turn_deg=5))[RerouteKind.DIRECT_DEST]
    assert option.status is RerouteStatus.NO_ROUTE
    assert "TURN" in option.note
    assert not option.waypoints
    for ok in plan().values():
        assert ok.max_turn_deg is not None
        assert ok.max_turn_deg <= POLICY.reroute.max_turn_deg.value


def test_t12_route_strings_use_icao_coordinates() -> None:
    for option in plan().values():
        tokens = option.route_string.split()
        coordinates = [t for t in tokens if t not in ("DCT", "WADD")]
        assert len(coordinates) >= len(option.waypoints)
        assert all(re.fullmatch(r"\d{4}[NS]\d{5}[EW]", t) for t in coordinates)
    assert coordinate_text(-8.2, 112.75) == "0812S11245E"
    assert coordinate_text(5.0 + 59.7 / 60, -0.5) == "0600N00030W"


def test_t13_no_destination_means_no_direct_route_and_no_substitute() -> None:
    options = plan(route=None)
    direct = options[RerouteKind.DIRECT_DEST]
    assert direct.status is RerouteStatus.NO_DEST
    assert direct.route_string == ""
    assert not direct.path
    assert direct.fuel is None
    assert options[RerouteKind.REJOIN_TRACK].status is RerouteStatus.OK


# --- limits from the policy -------------------------------------------------------------


def test_extra_time_limits_come_from_the_policy() -> None:
    assert plan(policy=with_policy(max_extra_min=1))[RerouteKind.DIRECT_DEST].status is (
        RerouteStatus.TOO_LONG
    )
    assert plan(policy=with_policy(min_extra_min=10))[RerouteKind.DIRECT_DEST].status is (
        RerouteStatus.NO_BENEFIT
    )


def test_too_many_turn_points_are_refused_after_one_simplified_retry() -> None:
    option = plan(policy=with_policy(max_waypoints_count=0))[RerouteKind.DIRECT_DEST]
    assert option.status is RerouteStatus.NO_ROUTE
    assert "0 TURN POINTS" in option.note
    sizes = {key[4] for key in reroute._GRAPHS}
    assert sizes == {2.0, 4.0}  # the simplification was raised once, from the policy's 2 NM


def test_a_flight_without_a_track_has_no_rejoin() -> None:
    options = plan(make_flight(track=None))
    assert options[RerouteKind.REJOIN_TRACK].status is RerouteStatus.NO_ROUTE
    assert options[RerouteKind.DIRECT_DEST].status is RerouteStatus.OK


def test_the_buffer_widens_the_detour() -> None:
    narrow = plan(policy=with_policy(buffer_nm=10))[RerouteKind.DIRECT_DEST]
    wide = plan(policy=with_policy(buffer_nm=30))[RerouteKind.DIRECT_DEST]
    assert narrow.extra_nm is not None
    assert wide.extra_nm is not None
    assert narrow.extra_nm < wide.extra_nm


def test_a_strong_headwind_costs_more_minutes_than_still_air() -> None:
    # no ADS-B ground speed: the policy's cruise TAS is flown, so the wind changes the time
    flight = make_flight(gs=None)
    still = plan(flight)[RerouteKind.DIRECT_DEST]
    headwind = plan(flight, situation=make_situation(107.0, 80.0))[RerouteKind.DIRECT_DEST]
    assert still.wind_note is not None
    assert still.wind_note.startswith("NO WIND DATA")
    assert headwind.time_min is not None
    assert still.time_min is not None
    assert headwind.time_min > still.time_min
    assert headwind.wind_note is not None
    assert "HEADWIND" in headwind.wind_note


def test_wind_is_interpolated_between_levels_in_the_vector_components() -> None:
    wind = reroute._wind_at(make_situation(270.0, 40.0), 250)
    assert wind is not None
    assert wind.from_deg == pytest.approx(270.0, abs=0.5)
    assert wind.speed_kt == pytest.approx(40.0, abs=0.5)
    assert reroute._wind_at(make_situation(), 250) is None


def test_ids_and_options_are_stable_for_the_same_inputs() -> None:
    first, second = plan(), plan()
    assert {k: o.id for k, o in first.items()} == {k: o.id for k, o in second.items()}
    assert all(o.id.startswith("RR-") for o in first.values())
    assert first[RerouteKind.DIRECT_DEST].path == second[RerouteKind.DIRECT_DEST].path


def test_reroute_line_formula_reproduces_its_numbers() -> None:
    line = reroute_line(CATEGORY, extra_min=2.1, extra_nm=14.4)
    assert (line.minutes, line.fuel_kg, line.distance_nm) == (3, 126, 14.0)
    assert line.formula == "REROUTE +14 NM = +3 MIN x 42 KG/MIN (NARROWBODY) = 126 KG"
    assert reroute_line(CATEGORY, extra_min=-1.0, extra_nm=-2.0).fuel_kg == 0


# --- speed ------------------------------------------------------------------------------


def test_the_obstacle_is_the_convex_hull_of_each_piece_and_never_narrower_than_the_cone() -> None:
    notched = [
        destination_point(*CENTRE, i * 15.0, nm_to_km(40.0 if i % 2 else 18.0)) for i in range(24)
    ]
    cone = make_cone(notched)
    graph = reroute._graph(cone, POLICY, float(POLICY.reroute.simplify_nm.value))
    core = graph.proj.project(reroute._cone_shape(cone))
    pieces = shapely.get_parts(graph.obstacle)
    assert len(pieces) == 1
    assert pieces[0].equals(pieces[0].convex_hull)
    assert graph.obstacle.contains(core.buffer(BUFFER_NM - 1.0))


def test_the_obstacle_graph_is_cached_per_cone_and_flights_reuse_it() -> None:
    cone = make_cone()
    plan(cone=cone)
    assert len(reroute._GRAPHS) == 1
    graph = next(iter(reroute._GRAPHS.values()))
    plan(make_flight(hex_id="8a0124"), cone)
    assert next(iter(reroute._GRAPHS.values())) is graph
    plan(cone=make_cone(cone_id="CONE-other0000000"))
    assert len(reroute._GRAPHS) == 2


def test_benchmark_200_flights_against_a_multi_polygon_cone() -> None:
    rng = random.Random(7)
    centres = [(-7.2, 110.2), (-7.9, 111.3), (-7.0, 112.1), (-8.2, 109.6)]
    polygons = []
    for lat, lon in centres:
        radii = [rng.uniform(22.0, 45.0) for _ in range(40)]
        ring = [destination_point(lat, lon, i * 9.0, nm_to_km(r)) for i, r in enumerate(radii)]
        polygons.append(Polygon([(p[1], p[0]) for p in ring]))
    cone = make_cone().model_copy(update={"geometry": multi(polygons)})
    flights = []
    for i in range(200):
        start = destination_point(*CENTRE, rng.uniform(0, 360), nm_to_km(rng.uniform(150, 260)))
        track = initial_bearing_deg(*start, *CENTRE) + rng.uniform(-15, 15)
        flights.append(make_flight(*start, track=track, hex_id=f"{i:06x}"))
    situation = make_situation(250.0, 40.0)

    started = time.perf_counter()
    first = plan_reroutes(flights[0], cone, situation, None, POLICY)
    cold_ms = (time.perf_counter() - started) * 1000.0
    started = time.perf_counter()
    results = [plan_reroutes(f, cone, situation, None, POLICY) for f in flights]
    warm_ms = (time.perf_counter() - started) * 1000.0
    graph = next(iter(reroute._GRAPHS.values()))
    statuses = [r[0].status for r in results]
    print(
        f"\nreroute benchmark: {len(graph.xy)} convex vertices,"
        f" graph build {graph.build_ms:.1f} ms,"
        f" first flight (cache miss) {cold_ms:.1f} ms, 200 flights {warm_ms:.0f} ms"
        f" ({warm_ms / 200:.2f} ms each); statuses "
        + ", ".join(f"{s.value}={statuses.count(s)}" for s in sorted(set(statuses)))
    )
    assert first[0].compute_ms is not None
    assert RerouteStatus.OK in statuses
    assert cold_ms < 2_000
    assert warm_ms / 200 < 100  # target is 10 ms per flight; generous so CI noise never fails
    for option in (o for r in results for o in r if o.status is RerouteStatus.OK):
        assert option.compute_ms is not None
