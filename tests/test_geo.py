"""Units, great circles, the official floor, the hazard cone, exposure and fuel lines."""

import math
from datetime import UTC, datetime, timedelta

import pytest
import shapely
from hypothesis import given, settings
from hypothesis import strategies as st

from tephra.geo.cone import (
    UNKNOWN_TOP_FT,
    VAA_CLOCK_SLACK,
    build_cone,
    contains_point,
    covers_official,
    geometry_to_shape,
    official_layers,
    polygon_iou,
    sector_polygon,
)
from tephra.geo.exposure import extrapolate, find_exposed
from tephra.geo.fuel import BURN_KG_PER_MIN, category_for_type, divert_line, hold_line
from tephra.geo.units import (
    KM_PER_NM,
    bearing_diff_deg,
    compass_to_deg,
    deg_to_compass,
    destination_point,
    distance_nm,
    fl_to_ft,
    ft_to_fl,
    haversine_km,
    initial_bearing_deg,
    sector_width_deg,
    solar_hour,
)
from tephra.models import (
    ActionKind,
    Aircraft,
    AircraftCategory,
    FeedId,
    GeoMultiPolygon,
    GeoPolygon,
    HazardCone,
    OfficialLayer,
    PlumeAssessment,
    PlumeEstimate,
    PlumeMode,
    Position,
    Provenance,
    RunMode,
    Sigmet,
    Situation,
    VaacAdvisory,
    VaacCentre,
    VaacStep,
    VaLayer,
    Volcano,
)
from tephra.util.hashing import stable_id

AT = datetime(2026, 10, 9, 19, 0, tzinfo=UTC)
ONE_DEG_KM = 111.19508  # pi * 6371.0088 / 180

SEMERU = Volcano(
    id="263300",
    name="Semeru",
    aliases=["SEMERU"],
    magma_code="SMR",
    country="Indonesia",
    lat=-8.108,
    lon=112.922,
    summit_elev_m=3676,
    observatory="PVMBG",
    vaac=VaacCentre.DARWIN,
)

# SIGMET WAAF 12, 9 Oct 2026 1820Z (tests/fixtures/isigmet/isigmet_va.json), JSON `coords`.
SEMERU_SIGMET_RING: list[Position] = [
    (112.883, -8.05),
    (113.267, -7.9),
    (113.4, -8.117),
    (113.3, -8.333),
    (112.883, -8.183),
    (112.883, -8.05),
]


# --- builders ---------------------------------------------------------------------------


def _prov(source_id: str, feed: FeedId) -> Provenance:
    return Provenance(
        source_id=source_id,
        feed=feed,
        url="https://example.invalid/feed",
        fetched_at=AT,
        sha256="0" * 64,
    )


def _square(west: float, south: float, east: float, north: float) -> GeoPolygon:
    ring = [(west, south), (east, south), (east, north), (west, north), (west, south)]
    return GeoPolygon(coordinates=[ring])


def _sigmet(
    series_id: str = "12",
    *,
    polygon: GeoPolygon | None = None,
    valid_from: datetime = AT - timedelta(minutes=40),
    valid_to: datetime = AT + timedelta(hours=5, minutes=20),
    top_ft: int | None = 15_000,
    cancelled: bool = False,
) -> Sigmet:
    return Sigmet(
        provenance=_prov(f"SIGMET:WAAF:{series_id}:20261009T1820Z", FeedId.SIGMET),
        fir_id="WAAF",
        series_id=series_id,
        volcano_name="SEMERU",
        observed=True,
        base_ft=0,
        top_ft=top_ft,
        polygon=polygon if polygon is not None else GeoPolygon(coordinates=[SEMERU_SIGMET_RING]),
        valid_from=valid_from,
        valid_to=valid_to,
        cancelled=cancelled,
        raw_text="WAAF SIGMET 12 VALID 091820/100020 WAAA- ... SFC/FL150 MOV E 10KT NC=",
    )


def _step(offset_h: int, valid_at: datetime, *layers: VaLayer, **flags: bool) -> VaacStep:
    return VaacStep(offset_h=offset_h, valid_at=valid_at, layers=list(layers), text="", **flags)


def _vaa(
    advisory_nr: str,
    issued_at: datetime,
    *,
    vaac: VaacCentre = VaacCentre.DARWIN,
    next_advisory_at: datetime | None = None,
    final: bool = False,
    observation: VaacStep | None = None,
    forecasts: list[VaacStep] | None = None,
) -> VaacAdvisory:
    return VaacAdvisory(
        provenance=_prov(f"VAA:{vaac.value}:263300:{advisory_nr}", FeedId.VAAC_DARWIN),
        vaac=vaac,
        advisory_nr=advisory_nr,
        issued_at=issued_at,
        volcano_name="SEMERU",
        volcano_number="263300",
        next_advisory_at=next_advisory_at,
        final=final,
        observation=observation,
        forecasts=forecasts or [],
        raw_text="FVAU03 ADRM",
    )


def _layer(
    polygon: GeoPolygon,
    *,
    source_id: str = "SIGMET:WAAF:12:20261009T1820Z",
    base_ft: int = 0,
    top_ft: int = 15_000,
) -> OfficialLayer:
    return OfficialLayer(
        source_id=source_id,
        kind="SIGMET",
        layer="SIGMET",
        label="SIGMET WAAF 12",
        volcano_id=SEMERU.id,
        polygon=polygon,
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
    horizon_h: float = 6.0,
) -> PlumeEstimate:
    return PlumeEstimate(
        mode=mode,
        base_fl=base_fl,
        top_fl=top_fl,
        bearing_from_deg=bearing_from_deg,
        bearing_to_deg=bearing_to_deg,
        extent_km=extent_km,
        horizon_h=horizon_h,
        confidence=0.6,
        sources_used=[],
        disagreements_explained=[],
        uncertainty_notes="",
        rationale="",
    )


def _assessment(estimate: PlumeEstimate) -> PlumeAssessment:
    return PlumeAssessment(
        id="PA-0123456789ab",
        volcano_id=SEMERU.id,
        created_at=AT,
        input_hash="1" * 64,
        estimate=estimate,
        llm_backend="stub",
        model_id="stub",
        prompt_hash="2" * 64,
        outcome="STUB",
        attempts=0,
    )


def _situation(layers: list[OfficialLayer], volcano: Volcano = SEMERU) -> Situation:
    return Situation(
        volcano=volcano,
        as_of=AT,
        mode=RunMode.REPLAY,
        active_reasons=["test"],
        official_layers=layers,
    )


def _cone(
    geometry: GeoPolygon | None,
    *,
    base_ft: int = 0,
    top_ft: int = 15_000,
    horizon_h: float = 6.0,
) -> HazardCone:
    return HazardCone(
        id="CONE-test",
        volcano_id=SEMERU.id,
        assessment_id="PA-test",
        mode=PlumeMode.OFFICIAL,
        confidence=1.0,
        llm_backend="stub",
        created_at=AT,
        horizon_h=horizon_h,
        valid_to=AT + timedelta(hours=horizon_h),
        geometry=geometry,
        base_ft=base_ft,
        top_ft=top_ft,
        official_source_ids=[],
    )


def _aircraft(
    *,
    lat: float = -8.5,
    lon: float = 112.0,
    track_deg: float | None = 90.0,
    gs_kt: float | None = 480.0,
    alt_baro_ft: int | None = 12_000,
    nav_altitude_mcp_ft: int | None = None,
    callsign: str | None = "GIA417",
    hex_id: str = "8a01f2",
    type_icao: str | None = "B738",
    observed_at: datetime = AT,
) -> Aircraft:
    return Aircraft(
        hex=hex_id,
        callsign=callsign,
        type_icao=type_icao,
        lat=lat,
        lon=lon,
        alt_baro_ft=alt_baro_ft,
        nav_altitude_mcp_ft=nav_altitude_mcp_ft,
        gs_kt=gs_kt,
        track_deg=track_deg,
        observed_at=observed_at,
        source_id="ADSB:-8.200:113.600:20261009T190000Z",
    )


def _covered(outer: GeoPolygon | GeoMultiPolygon, inner: GeoPolygon, ref_lon: float) -> bool:
    big = geometry_to_shape(outer, ref_lon=ref_lon)
    small = geometry_to_shape(inner, ref_lon=ref_lon)
    return bool(big.covers(small)) or small.difference(big).area <= 1e-12


# --- units ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ft", "fl"), [(0, 0), (15_000, 150), (15_049, 150), (15_050, 151), (13_701, 137)]
)
def test_ft_to_fl_rounds_to_nearest(ft: float, fl: int) -> None:
    assert ft_to_fl(ft) == fl


def test_fl_to_ft() -> None:
    assert fl_to_ft(150) == 15_000
    assert fl_to_ft(0) == 0
    assert fl_to_ft(ft_to_fl(35_000)) == 35_000


def test_haversine_one_degree_of_latitude() -> None:
    assert haversine_km(0.0, 0.0, 1.0, 0.0) == pytest.approx(ONE_DEG_KM, rel=1e-6)
    assert haversine_km(-8.1, 112.9, -8.1, 112.9) == 0.0
    assert distance_nm(0.0, 0.0, 1.0, 0.0) == pytest.approx(ONE_DEG_KM / KM_PER_NM, rel=1e-6)


def test_haversine_is_symmetric() -> None:
    there = haversine_km(-8.108, 112.922, -7.38, 112.787)
    back = haversine_km(-7.38, 112.787, -8.108, 112.922)
    assert there == pytest.approx(back, rel=1e-12)


@pytest.mark.parametrize(
    ("lat2", "lon2", "bearing"),
    [(1.0, 0.0, 0.0), (0.0, 1.0, 90.0), (-1.0, 0.0, 180.0), (0.0, -1.0, 270.0)],
)
def test_initial_bearing_cardinal(lat2: float, lon2: float, bearing: float) -> None:
    assert initial_bearing_deg(0.0, 0.0, lat2, lon2) == pytest.approx(bearing, abs=1e-9)


@pytest.mark.parametrize("bearing", [0.0, 37.0, 90.0, 181.0, 271.5, 359.0])
@pytest.mark.parametrize("distance_km", [1.0, 150.0, 480.0])
def test_destination_point_round_trip(bearing: float, distance_km: float) -> None:
    lat, lon = destination_point(SEMERU.lat, SEMERU.lon, bearing, distance_km)
    assert haversine_km(SEMERU.lat, SEMERU.lon, lat, lon) == pytest.approx(distance_km, rel=1e-9)
    back = initial_bearing_deg(SEMERU.lat, SEMERU.lon, lat, lon)
    assert bearing_diff_deg(back, bearing) == pytest.approx(0.0, abs=1e-6)


def test_destination_point_zero_distance_is_start() -> None:
    assert destination_point(-8.108, 112.922, 45.0, 0.0) == (-8.108, 112.922)


def test_destination_point_wraps_the_antimeridian() -> None:
    lat, lon = destination_point(0.0, 179.5, 90.0, ONE_DEG_KM)
    assert lat == pytest.approx(0.0, abs=1e-9)
    assert lon == pytest.approx(-179.5, abs=1e-6)


@pytest.mark.parametrize(
    ("a", "b", "diff"),
    [
        (350.0, 10.0, 20.0),
        (10.0, 350.0, 20.0),
        (0.0, 180.0, 180.0),
        (90.0, 90.0, 0.0),
        (45.0, 300.0, 105.0),
        (720.0, 0.0, 0.0),
    ],
)
def test_bearing_diff(a: float, b: float, diff: float) -> None:
    assert bearing_diff_deg(a, b) == pytest.approx(diff)


@pytest.mark.parametrize(
    ("bearing_from", "bearing_to", "width"),
    [
        (330.0, 30.0, 60.0),
        (30.0, 330.0, 300.0),
        (0.0, 360.0, 360.0),
        (10.0, 10.0, 0.0),
        (45.0, 135.0, 90.0),
    ],
)
def test_sector_width_is_clockwise(bearing_from: float, bearing_to: float, width: float) -> None:
    assert sector_width_deg(bearing_from, bearing_to) == pytest.approx(width)


@pytest.mark.parametrize(
    ("text", "deg"),
    [
        ("NE", 45.0),
        ("MOV NE 05KT", 45.0),
        ("WSW", 247.5),
        ("Ash cloud moving to north", 0.0),
        ("Ash cloud moving to the east", 90.0),
        ("north east", 45.0),
        ("North-East", 45.0),
        ("north-northeast", 22.5),
        ("southwest", 225.0),
        ("drifting eastward", 90.0),
        ("Ash cloud moving from northeast to east", 67.5),
        ("ASH CLOUD MOVING TO SOUTH", 180.0),
    ],
)
def test_compass_to_deg(text: str, deg: float) -> None:
    assert compass_to_deg(text) == pytest.approx(deg)


@pytest.mark.parametrize(
    "text",
    ["", "Ash-cloud is not observed.", "S0806 E11255", "moving towards the sea", "north to south"],
)
def test_compass_to_deg_none(text: str) -> None:
    assert compass_to_deg(text) is None


@pytest.mark.parametrize(
    ("deg", "name"),
    [
        (0.0, "N"),
        (11.24, "N"),
        (11.25, "NNE"),
        (45.0, "NE"),
        (247.5, "WSW"),
        (359.0, "N"),
        (-45.0, "NW"),
        (405.0, "NE"),
    ],
)
def test_deg_to_compass(deg: float, name: str) -> None:
    assert deg_to_compass(deg) == name


def test_compass_round_trip_16_points() -> None:
    for i in range(16):
        assert compass_to_deg(deg_to_compass(i * 22.5)) == pytest.approx(i * 22.5)


def test_solar_hour() -> None:
    assert solar_hour(105.0, datetime(2026, 10, 10, 0, 0, tzinfo=UTC)) == pytest.approx(7.0)
    assert solar_hour(-90.0, datetime(2026, 10, 10, 3, 0, tzinfo=UTC)) == pytest.approx(21.0)
    assert solar_hour(112.922, AT) == pytest.approx((19.0 + 112.922 / 15.0) % 24.0)


# --- official floor ---------------------------------------------------------------------


def _vaa_with_steps(
    advisory_nr: str = "2026/1157", *, vaac: VaacCentre = VaacCentre.DARWIN
) -> VaacAdvisory:
    """Issued 30 min before AT: OBS, +6 h and +12 h polygons, and +18 h NO VA EXP."""
    obs = VaLayer(base_ft=0, top_ft=15_000, polygon=GeoPolygon(coordinates=[SEMERU_SIGMET_RING]))
    fcst_polygon = _square(112.9, -8.4, 113.8, -7.9)
    fcst6 = VaLayer(base_ft=0, top_ft=15_000, polygon=fcst_polygon)
    fcst12 = VaLayer(base_ft=0, top_ft=12_000, polygon=fcst_polygon)
    return _vaa(
        advisory_nr,
        AT - timedelta(minutes=30),
        vaac=vaac,
        next_advisory_at=AT + timedelta(hours=5, minutes=30),
        observation=_step(0, AT - timedelta(hours=1), obs),
        forecasts=[
            _step(6, AT + timedelta(hours=5), fcst6),
            _step(12, AT + timedelta(hours=11), fcst12),
            _step(18, AT + timedelta(hours=17), no_ash_expected=True),
        ],
    )


def test_official_layers_sigmet_and_vaa_steps() -> None:
    vaa = _vaa_with_steps()
    layers = official_layers(SEMERU, [_sigmet()], [vaa], AT)

    assert [layer.layer for layer in layers] == ["SIGMET", "OBS", "FCST+6H", "FCST+12H"]
    sigmet_layer, obs, fcst6, fcst12 = layers
    assert sigmet_layer.label == "SIGMET WAAF 12"
    assert sigmet_layer.kind == "SIGMET"
    assert sigmet_layer.volcano_id == SEMERU.id
    assert (sigmet_layer.base_ft, sigmet_layer.top_ft) == (0, 15_000)

    assert obs.label == "VAA DARWIN 2026/1157 OBS"
    assert obs.valid_from == AT - timedelta(hours=1)
    assert obs.valid_to == vaa.valid_until()
    assert fcst6.label == "VAA DARWIN 2026/1157 FCST+6H"
    assert (fcst6.valid_from, fcst6.valid_to) == (AT + timedelta(hours=2), AT + timedelta(hours=8))
    assert fcst12.top_ft == 12_000
    assert all(layer.source_id == vaa.provenance.source_id for layer in layers[1:])


def test_official_layers_estimated_observation_is_labelled_est() -> None:
    polygon = GeoPolygon(coordinates=[SEMERU_SIGMET_RING])
    vaa = _vaa(
        "2026/1158",
        AT - timedelta(minutes=10),
        observation=_step(
            0,
            AT - timedelta(minutes=20),
            VaLayer(base_ft=0, top_ft=15_000, polygon=polygon),
            estimated=True,
        ),
    )
    (layer,) = official_layers(SEMERU, [], [vaa], AT)
    assert layer.layer == "OBS"
    assert layer.label == "VAA DARWIN 2026/1158 EST"


def test_official_layers_multi_layer_step_labels_band() -> None:
    low = VaLayer(base_ft=0, top_ft=15_000, polygon=_square(112.9, -8.3, 113.3, -8.0))
    high = VaLayer(base_ft=15_000, top_ft=25_000, polygon=_square(113.0, -8.4, 113.6, -8.0))
    vaa = _vaa("2026/1159", AT - timedelta(minutes=10), observation=_step(0, AT, low, high))
    layers = official_layers(SEMERU, [], [vaa], AT)
    assert {layer.label: (layer.base_ft, layer.top_ft) for layer in layers} == {
        "VAA DARWIN 2026/1159 OBS SFC/FL150": (0, 15_000),
        "VAA DARWIN 2026/1159 OBS FL150/FL250": (15_000, 25_000),
    }


def test_official_layers_drop_expired_cancelled_far_future_and_unpolygoned() -> None:
    sigmets = [
        _sigmet("1", valid_from=AT - timedelta(hours=6), valid_to=AT - timedelta(minutes=1)),
        _sigmet("2", cancelled=True),
        _sigmet("3", valid_from=AT + timedelta(hours=19), valid_to=AT + timedelta(hours=23)),
        _sigmet("4", valid_from=AT + timedelta(hours=17), valid_to=AT + timedelta(hours=21)),
        _sigmet("5").model_copy(update={"polygon": None}),
    ]
    layers = official_layers(SEMERU, sigmets, [], AT)
    assert [layer.label for layer in layers] == ["SIGMET WAAF 4"]


def test_official_layers_sigmet_without_top_is_binding_to_fl600() -> None:
    (layer,) = official_layers(SEMERU, [_sigmet(top_ft=None)], [], AT)
    assert layer.top_ft == UNKNOWN_TOP_FT
    assert layer.label.endswith("TOP NOT STATED")


def test_official_layers_use_only_latest_vaa_per_centre() -> None:
    older = _vaa_with_steps("2026/1156").model_copy(
        update={"issued_at": AT - timedelta(hours=6, minutes=30)}
    )
    newer = _vaa_with_steps("2026/1157")
    tokyo = _vaa_with_steps("2026/0042", vaac=VaacCentre.TOKYO)
    labels = {layer.label for layer in official_layers(SEMERU, [], [older, newer, tokyo], AT)}
    assert "VAA DARWIN 2026/1157 OBS" in labels
    assert "VAA TOKYO 2026/0042 OBS" in labels
    assert not any("2026/1156" in label for label in labels)


def test_official_layers_never_revive_a_superseded_vaa() -> None:
    polygon = GeoPolygon(coordinates=[SEMERU_SIGMET_RING])
    older = _vaa(
        "2026/1150",
        AT - timedelta(hours=7),
        next_advisory_at=AT + timedelta(hours=1),
        observation=_step(
            0, AT - timedelta(hours=7), VaLayer(base_ft=0, top_ft=10_000, polygon=polygon)
        ),
    )
    final = _vaa("2026/1151", AT - timedelta(hours=2), final=True)
    assert not final.is_current(AT)
    assert older.is_current(AT)
    assert official_layers(SEMERU, [], [older, final], AT) == []


def test_official_layers_ignore_vaa_issued_after_at() -> None:
    issued_at = AT + VAA_CLOCK_SLACK + timedelta(seconds=1)
    future = _vaa_with_steps().model_copy(update={"issued_at": issued_at})
    assert official_layers(SEMERU, [], [future], AT) == []


def test_official_layers_use_a_vaa_stamped_minutes_after_at() -> None:
    # A tick takes about a minute; a VAA whose DTG is just after the tick time is already in
    # hand, and record selection passes it on instead of the advisory it replaces.
    newer = _vaa_with_steps("2026/1158").model_copy(update={"issued_at": AT + timedelta(minutes=2)})
    labels = [layer.label for layer in official_layers(SEMERU, [], [newer], AT)]
    assert labels == [
        "VAA DARWIN 2026/1158 OBS",
        "VAA DARWIN 2026/1158 FCST+6H",
        "VAA DARWIN 2026/1158 FCST+12H",
    ]


# --- sector -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("bearing_from", "bearing_to", "extent_km"),
    [(45.0, 135.0, 0.0), (90.0, 90.0, 200.0), (45.0, 135.0, 1e-300)],
)
def test_sector_polygon_none_for_empty_sector(
    bearing_from: float, bearing_to: float, extent_km: float
) -> None:
    assert sector_polygon(SEMERU.lat, SEMERU.lon, bearing_from, bearing_to, extent_km) is None


def test_sector_polygon_wedge_geometry() -> None:
    sector = sector_polygon(SEMERU.lat, SEMERU.lon, 330.0, 30.0, 200.0, steps=12)
    assert sector is not None
    ring = sector.coordinates[0]
    assert ring[0] == ring[-1] == (SEMERU.lon, SEMERU.lat)
    arc = ring[1:-1]
    assert len(arc) == 13
    for lon, lat in arc:
        assert haversine_km(SEMERU.lat, SEMERU.lon, lat, lon) == pytest.approx(200.0, rel=1e-9)
    bearings = [initial_bearing_deg(SEMERU.lat, SEMERU.lon, lat, lon) for lon, lat in arc]
    assert bearing_diff_deg(bearings[0], 330.0) == pytest.approx(0.0, abs=1e-6)
    assert bearing_diff_deg(bearings[6], 0.0) == pytest.approx(0.0, abs=1e-6)
    assert bearing_diff_deg(bearings[-1], 30.0) == pytest.approx(0.0, abs=1e-6)

    shape = geometry_to_shape(sector, ref_lon=SEMERU.lon)
    assert shape.is_valid
    north_lat, north_lon = destination_point(SEMERU.lat, SEMERU.lon, 0.0, 100.0)
    south_lat, south_lon = destination_point(SEMERU.lat, SEMERU.lon, 180.0, 100.0)
    assert shape.covers(shapely.Point(north_lon, north_lat))
    assert not shape.covers(shapely.Point(south_lon, south_lat))


def test_sector_polygon_full_circle_is_a_disc() -> None:
    disc = sector_polygon(SEMERU.lat, SEMERU.lon, 0.0, 360.0, 100.0, steps=24)
    assert disc is not None
    ring = disc.coordinates[0]
    assert len(ring) == 25
    assert (SEMERU.lon, SEMERU.lat) not in ring
    for lon, lat in ring:
        assert haversine_km(SEMERU.lat, SEMERU.lon, lat, lon) == pytest.approx(100.0, rel=1e-9)
    shape = geometry_to_shape(disc, ref_lon=SEMERU.lon)
    assert shape.is_valid
    assert shape.covers(shapely.Point(SEMERU.lon, SEMERU.lat))


# --- cone -------------------------------------------------------------------------------


def test_build_cone_official_is_the_official_union() -> None:
    layers = official_layers(SEMERU, [_sigmet()], [], AT)
    assessment = _assessment(_estimate(PlumeMode.OFFICIAL, bearing_to_deg=90.0, extent_km=300))
    cone = build_cone(_situation(layers), assessment)

    assert cone.sector is None
    assert cone.geometry is not None
    assert polygon_iou(cone.geometry, layers[0].polygon) == pytest.approx(1.0, abs=1e-9)
    assert covers_official(cone, layers)
    assert (cone.base_ft, cone.top_ft) == (0, 15_000)
    assert cone.id == stable_id("CONE", SEMERU.id, assessment.id)
    assert cone.assessment_id == assessment.id
    assert cone.valid_to == AT + timedelta(hours=6)
    assert cone.horizon_h == 6.0
    assert cone.official_source_ids == ["SIGMET:WAAF:12:20261009T1820Z"]
    assert cone.label == "OFFICIAL 60% (NO MODEL)"


def test_build_cone_widened_adds_the_sector_and_never_shrinks() -> None:
    layers = official_layers(SEMERU, [_sigmet()], [_vaa_with_steps()], AT)
    estimate = _estimate(
        PlumeMode.WIDENED,
        base_fl=50,
        top_fl=100,
        bearing_from_deg=45.0,
        bearing_to_deg=135.0,
        extent_km=300.0,
    )
    cone = build_cone(_situation(layers), _assessment(estimate))

    assert cone.geometry is not None
    assert cone.sector is not None
    assert covers_official(cone, layers)
    assert _covered(cone.geometry, cone.sector, SEMERU.lon)
    # The model's lower band never lowers the official top or raises the official base.
    assert (cone.base_ft, cone.top_ft) == (0, 15_000)
    east_lat, east_lon = destination_point(SEMERU.lat, SEMERU.lon, 90.0, 250.0)
    assert contains_point(cone, east_lat, east_lon)
    west_lat, west_lon = destination_point(SEMERU.lat, SEMERU.lon, 270.0, 250.0)
    assert not contains_point(cone, west_lat, west_lon)


def test_build_cone_band_widens_to_the_estimate() -> None:
    layers = [_layer(GeoPolygon(coordinates=[SEMERU_SIGMET_RING]), base_ft=5_000)]
    estimate = _estimate(
        PlumeMode.WIDENED, base_fl=0, top_fl=250, bearing_to_deg=90.0, extent_km=100.0
    )
    cone = build_cone(_situation(layers), _assessment(estimate))
    assert (cone.base_ft, cone.top_ft) == (0, 25_000)


def test_build_cone_hypothesis_is_the_sector() -> None:
    estimate = _estimate(
        PlumeMode.HYPOTHESIS,
        top_fl=170,
        bearing_from_deg=60.0,
        bearing_to_deg=120.0,
        extent_km=200.0,
    )
    cone = build_cone(_situation([]), _assessment(estimate))
    assert cone.geometry is not None
    assert cone.sector is not None
    assert polygon_iou(cone.geometry, cone.sector) == pytest.approx(1.0, abs=1e-9)
    assert cone.official_source_ids == []
    assert (cone.base_ft, cone.top_ft) == (0, 17_000)


def test_build_cone_without_layers_or_sector_has_no_geometry() -> None:
    estimate = _estimate(PlumeMode.OFFICIAL, top_fl=0)
    cone = build_cone(_situation([]), _assessment(estimate))
    assert cone.geometry is None
    assert cone.sector is None
    assert (cone.base_ft, cone.top_ft) == (0, 0)
    assert covers_official(cone, [])
    assert not contains_point(cone, SEMERU.lat, SEMERU.lon)
    assert cone.to_features() == []


def test_build_cone_covers_disjoint_official_polygons() -> None:
    layers = [
        _layer(GeoPolygon(coordinates=[SEMERU_SIGMET_RING])),
        _layer(
            _square(114.5, -8.6, 115.0, -8.2),
            source_id="VAA:DARWIN:263300:2026/1157",
            top_ft=20_000,
        ),
    ]
    cone = build_cone(_situation(layers), _assessment(_estimate(PlumeMode.OFFICIAL)))
    assert isinstance(cone.geometry, GeoMultiPolygon)
    assert covers_official(cone, layers)
    assert cone.top_ft == 20_000


def test_build_cone_covers_a_self_crossing_feed_polygon() -> None:
    bowtie = GeoPolygon(
        coordinates=[[(113.0, -8.5), (113.5, -8.0), (113.5, -8.5), (113.0, -8.0), (113.0, -8.5)]]
    )
    layers = [_layer(bowtie)]
    cone = build_cone(_situation(layers), _assessment(_estimate(PlumeMode.OFFICIAL)))
    assert cone.geometry is not None
    assert covers_official(cone, layers)
    # The ring crosses itself at 113.25 E; its two lobes are west and east of that point.
    assert contains_point(cone, -8.25, 113.1)
    assert contains_point(cone, -8.25, 113.4)
    assert not contains_point(cone, -8.1, 113.25)


def test_build_cone_keeps_what_a_folded_feed_ring_encloses_twice() -> None:
    # The ring's arm folds back over its body, so 113.1-113.3 E, 8.3-8.2 S lies inside the
    # outline twice. That is still ash area: an even-odd repair would cut a hole there.
    fold = GeoPolygon(
        coordinates=[
            [
                (113.0, -8.4),
                (113.4, -8.4),
                (113.4, -8.2),
                (113.1, -8.2),
                (113.1, -8.3),
                (113.3, -8.3),
                (113.3, -8.1),
                (113.0, -8.1),
                (113.0, -8.4),
            ]
        ]
    )
    layers = [_layer(fold)]
    cone = build_cone(_situation(layers), _assessment(_estimate(PlumeMode.OFFICIAL)))
    assert covers_official(cone, layers)
    assert contains_point(cone, -8.25, 113.2)
    assert contains_point(cone, -8.35, 113.2)
    assert contains_point(cone, -8.15, 113.2)
    assert not contains_point(cone, -8.05, 113.2)


def test_cone_handles_the_antimeridian() -> None:
    vent = SEMERU.model_copy(update={"id": "999999", "lat": -15.0, "lon": 179.9})
    straddling = GeoPolygon(
        coordinates=[
            [(179.5, -15.5), (-179.5, -15.5), (-179.5, -14.5), (179.5, -14.5), (179.5, -15.5)]
        ]
    )
    layers = [_layer(straddling)]
    estimate = _estimate(
        PlumeMode.WIDENED, bearing_from_deg=60.0, bearing_to_deg=120.0, extent_km=200.0
    )
    cone = build_cone(_situation(layers, vent), _assessment(estimate))

    assert covers_official(cone, layers)
    assert contains_point(cone, -15.0, -179.8)
    assert contains_point(cone, -15.0, 179.6)
    east_lat, east_lon = destination_point(vent.lat, vent.lon, 90.0, 150.0)
    assert east_lon < 0
    assert contains_point(cone, east_lat, east_lon)
    assert not contains_point(cone, -15.0, 0.0)
    assert not contains_point(cone, -15.0, 178.0)


def test_covers_official_fails_when_band_or_area_is_short() -> None:
    layers = [_layer(GeoPolygon(coordinates=[SEMERU_SIGMET_RING]))]
    cone = build_cone(_situation(layers), _assessment(_estimate(PlumeMode.OFFICIAL)))
    assert covers_official(cone, layers)
    assert not covers_official(cone.model_copy(update={"top_ft": 10_000}), layers)
    assert not covers_official(cone.model_copy(update={"base_ft": 1_000}), layers)
    assert not covers_official(cone.model_copy(update={"geometry": None}), layers)
    elsewhere = [_layer(_square(120.0, -9.0, 121.0, -8.0))]
    assert not covers_official(cone, elsewhere)


def test_polygon_iou() -> None:
    a = _square(0.0, 0.0, 2.0, 1.0)
    assert polygon_iou(a, a) == pytest.approx(1.0)
    assert polygon_iou(a, _square(1.0, 0.0, 3.0, 1.0)) == pytest.approx(1.0 / 3.0)
    assert polygon_iou(a, _square(5.0, 5.0, 6.0, 6.0)) == 0.0


@st.composite
def _star_polygons(draw: st.DrawFn) -> GeoPolygon:
    """Random simple (star-shaped) polygons within a few hundred km of the vent."""
    centre_lon = SEMERU.lon + draw(st.floats(-3.0, 3.0))
    centre_lat = SEMERU.lat + draw(st.floats(-3.0, 3.0))
    angles = sorted(draw(st.lists(st.integers(0, 359), min_size=3, max_size=9, unique=True)))
    radii = draw(st.lists(st.floats(0.05, 2.0), min_size=len(angles), max_size=len(angles)))
    ring: list[Position] = []
    for angle, radius in zip(angles, radii, strict=True):
        lat, lon = destination_point(centre_lat, centre_lon, float(angle), radius * ONE_DEG_KM)
        ring.append((lon, lat))
    ring.append(ring[0])
    return GeoPolygon(coordinates=[ring])


@st.composite
def _layers(draw: st.DrawFn) -> list[OfficialLayer]:
    polygons = draw(st.lists(_star_polygons(), min_size=0, max_size=4))
    layers: list[OfficialLayer] = []
    for i, polygon in enumerate(polygons):
        base = draw(st.sampled_from([0, 5_000, 10_000, 20_000]))
        top = base + draw(st.integers(1, 40)) * 1_000
        layers.append(_layer(polygon, source_id=f"SIGMET:WAAF:{i}:X", base_ft=base, top_ft=top))
    return layers


@settings(max_examples=150, deadline=None)
@given(
    layers=_layers(),
    mode=st.sampled_from(list(PlumeMode)),
    bearing_from=st.floats(0.0, 360.0),
    bearing_to=st.floats(0.0, 360.0),
    extent_km=st.floats(0.0, 500.0),
    base_fl=st.integers(0, 600),
    top_fl=st.integers(0, 600),
)
def test_cone_always_covers_every_official_layer(
    layers: list[OfficialLayer],
    mode: PlumeMode,
    bearing_from: float,
    bearing_to: float,
    extent_km: float,
    base_fl: int,
    top_fl: int,
) -> None:
    estimate = _estimate(
        mode,
        base_fl=base_fl,
        top_fl=top_fl,
        bearing_from_deg=bearing_from,
        bearing_to_deg=bearing_to,
        extent_km=extent_km,
    )
    cone = build_cone(_situation(layers), _assessment(estimate))

    assert covers_official(cone, layers)
    if layers:
        assert cone.geometry is not None
        assert cone.base_ft <= min(layer.base_ft for layer in layers)
        assert cone.top_ft >= max(layer.top_ft for layer in layers)
    if mode is PlumeMode.OFFICIAL:
        assert cone.sector is None
    if cone.sector is not None:
        assert cone.geometry is not None
        assert _covered(cone.geometry, cone.sector, SEMERU.lon)


# --- exposure ---------------------------------------------------------------------------

# A box east of the aircraft's start; at -8.5 the box edge (113.0 E) is 109.97 km away, so at
# 480 kt (14.816 km/min) the first minute inside is minute 8.
BOX = _square(113.0, -9.0, 114.0, -8.0)


def test_extrapolate_steps_along_the_track() -> None:
    target = _aircraft()
    points = extrapolate(target, 60)
    assert len(points) == 61
    assert points[0] == (target.lat, target.lon)
    lat, lon = points[10]
    assert haversine_km(target.lat, target.lon, lat, lon) == pytest.approx(
        480.0 * KM_PER_NM / 6.0, rel=1e-9
    )
    assert initial_bearing_deg(target.lat, target.lon, lat, lon) == pytest.approx(90.0, abs=1e-6)
    assert len(extrapolate(target, 60, step_min=5)) == 13


@pytest.mark.parametrize(("gs_kt", "track_deg"), [(None, 90.0), (480.0, None), (30.0, 90.0)])
def test_extrapolate_holds_slow_or_unknown_targets(
    gs_kt: float | None, track_deg: float | None
) -> None:
    target = _aircraft(gs_kt=gs_kt, track_deg=track_deg)
    assert extrapolate(target, 60) == [(target.lat, target.lon)]


def test_extrapolate_rejects_a_non_positive_step() -> None:
    with pytest.raises(ValueError, match="step_min"):
        extrapolate(_aircraft(), 10, step_min=0)


def test_find_exposed_minutes_to_entry_and_path() -> None:
    cone = _cone(BOX)
    (flight,) = find_exposed(cone, [_aircraft()], AT, lookahead_min=60, vertical_margin_ft=2000)

    assert flight.minutes_to_entry == 8
    assert not flight.inside_now
    assert flight.id == f"8a01f2:{SEMERU.id}"
    assert flight.cone_id == cone.id
    assert flight.volcano_id == SEMERU.id
    assert flight.proxy_flight.startswith("RFA")
    assert 113.0 <= flight.entry_lon <= 113.2
    assert flight.entry_lat == pytest.approx(-8.5, abs=0.01)
    assert contains_point(cone, flight.entry_lat, flight.entry_lon)
    assert flight.path[0] == (112.0, -8.5)
    assert flight.path[-1] == (flight.entry_lon, flight.entry_lat)
    assert len(flight.path) == 9
    assert flight.aircraft_band_ft == (12_000, 12_000)
    assert flight.hazard_band_ft == (0, 15_000)
    assert flight.category is AircraftCategory.NARROWBODY
    assert flight.hold.action is ActionKind.HOLD
    assert flight.hold.fuel_kg == 840


def test_find_exposed_catches_a_narrow_cone_crossed_between_two_minutes() -> None:
    # 112.95-113.05 E is 11 km wide. At 480 kt the minute-7 and minute-8 positions
    # (112.943 E and 113.078 E) fall either side of it, yet the track crosses it at 7.05 min.
    strip = _square(112.95, -9.0, 113.05, -8.0)
    cone = _cone(strip)
    (flight,) = find_exposed(cone, [_aircraft()], AT, lookahead_min=60, vertical_margin_ft=2000)
    assert flight.minutes_to_entry == 8
    assert not flight.inside_now
    assert flight.entry_lon == pytest.approx(112.95, abs=1e-6)
    assert flight.entry_lat == pytest.approx(-8.5, abs=0.01)
    assert flight.path[-1] == (flight.entry_lon, flight.entry_lat)
    assert len(flight.path) == 9


def test_find_exposed_counts_minutes_from_now_for_an_old_position() -> None:
    stale = _aircraft(observed_at=AT - timedelta(minutes=3))
    (flight,) = find_exposed(_cone(BOX), [stale], AT, lookahead_min=60, vertical_margin_ft=2000)
    assert flight.minutes_to_entry == 5
    assert flight.path[0] == (stale.lon, stale.lat)


def test_find_exposed_skips_a_position_older_than_the_lookahead() -> None:
    # Both report a position inside the box and no speed, so each is checked where it was.
    # Where a target seen 61 minutes ago is now, a 60-minute projection cannot say.
    seen = {"lon": 113.5, "gs_kt": None, "track_deg": None}
    lost = _aircraft(hex_id="8a01f2", observed_at=AT - timedelta(minutes=61), **seen)
    held = _aircraft(hex_id="8a01f3", observed_at=AT - timedelta(minutes=60), **seen)
    flights = find_exposed(_cone(BOX), [lost, held], AT, lookahead_min=60, vertical_margin_ft=0)
    assert [flight.hex for flight in flights] == ["8a01f3"]


def test_find_exposed_inside_now() -> None:
    inside = _aircraft(lon=113.5)
    (flight,) = find_exposed(_cone(BOX), [inside], AT, lookahead_min=60, vertical_margin_ft=2000)
    assert flight.inside_now
    assert flight.minutes_to_entry == 0
    assert (flight.entry_lat, flight.entry_lon) == (inside.lat, inside.lon)
    assert flight.path == [(113.5, -8.5), (113.5, -8.5)]


@pytest.mark.parametrize(
    ("alt_baro_ft", "mcp_ft", "exposed"),
    [
        (12_000, None, True),
        (17_000, None, True),  # top 15,000 + 2,000 margin, inclusive
        (17_100, None, False),
        (36_000, None, False),
        (36_000, 16_000, True),  # descending into the band
        (36_000, 38_000, False),
    ],
)
def test_find_exposed_vertical_band_with_margin(
    alt_baro_ft: int, mcp_ft: int | None, exposed: bool
) -> None:
    target = _aircraft(alt_baro_ft=alt_baro_ft, nav_altitude_mcp_ft=mcp_ft)
    flights = find_exposed(_cone(BOX), [target], AT, lookahead_min=60, vertical_margin_ft=2000)
    assert bool(flights) is exposed
    if flights:
        expected_band = (min(alt_baro_ft, mcp_ft or alt_baro_ft), max(alt_baro_ft, mcp_ft or 0))
        assert flights[0].aircraft_band_ft == expected_band


def test_find_exposed_below_the_base() -> None:
    cone = _cone(BOX, base_ft=20_000, top_ft=35_000)
    low = _aircraft(alt_baro_ft=17_000)
    lower = _aircraft(alt_baro_ft=16_000)
    assert find_exposed(cone, [low], AT, lookahead_min=60, vertical_margin_ft=3000)
    assert not find_exposed(cone, [lower], AT, lookahead_min=60, vertical_margin_ft=3000)


def test_find_exposed_skips_non_airline_and_unknown_altitude() -> None:
    targets = [
        _aircraft(callsign="PKABC"),
        _aircraft(callsign=None),
        _aircraft(alt_baro_ft=None),
    ]
    assert find_exposed(_cone(BOX), targets, AT, lookahead_min=60, vertical_margin_ft=2000) == []


def test_find_exposed_lookahead_is_capped_by_horizon_and_setting() -> None:
    target = [_aircraft()]
    assert not find_exposed(
        _cone(BOX, horizon_h=0.1), target, AT, lookahead_min=60, vertical_margin_ft=2000
    )
    assert not find_exposed(_cone(BOX), target, AT, lookahead_min=7, vertical_margin_ft=2000)
    assert find_exposed(_cone(BOX), target, AT, lookahead_min=8, vertical_margin_ft=2000)


def test_find_exposed_ignores_slow_targets_outside_and_tracks_away() -> None:
    targets = [
        _aircraft(hex_id="000001", gs_kt=30.0),
        _aircraft(hex_id="000002", track_deg=270.0),
        _aircraft(hex_id="000003", gs_kt=None, track_deg=None),
    ]
    assert find_exposed(_cone(BOX), targets, AT, lookahead_min=60, vertical_margin_ft=2000) == []


@pytest.mark.parametrize(
    ("gs_kt", "track_deg"), [(math.nan, 90.0), (480.0, math.nan), (math.inf, 90.0)]
)
def test_find_exposed_treats_a_non_finite_speed_or_track_as_unknown(
    gs_kt: float, track_deg: float
) -> None:
    target = _aircraft(lon=113.5, gs_kt=gs_kt, track_deg=track_deg)
    assert extrapolate(target, 60) == [(target.lat, target.lon)]
    (flight,) = find_exposed(_cone(BOX), [target], AT, lookahead_min=60, vertical_margin_ft=2000)
    assert flight.inside_now
    assert (flight.entry_lat, flight.entry_lon) == (target.lat, target.lon)


def test_find_exposed_slow_target_inside_is_exposed_now() -> None:
    target = _aircraft(lon=113.5, gs_kt=None, track_deg=None)
    (flight,) = find_exposed(_cone(BOX), [target], AT, lookahead_min=60, vertical_margin_ft=2000)
    assert flight.inside_now
    assert flight.gs_kt is None


def test_find_exposed_sorted_by_minutes_to_entry() -> None:
    targets = [
        _aircraft(hex_id="aaaaaa", type_icao="B77W"),
        _aircraft(hex_id="bbbbbb", lon=113.5),
        _aircraft(hex_id="cccccc", lon=112.5),
    ]
    flights = find_exposed(_cone(BOX), targets, AT, lookahead_min=60, vertical_margin_ft=2000)
    assert [f.hex for f in flights] == ["bbbbbb", "cccccc", "aaaaaa"]
    assert flights[-1].category is AircraftCategory.WIDEBODY
    assert flights[-1].hold.fuel_kg == 2200


def test_find_exposed_without_geometry() -> None:
    cone = _cone(None)
    assert find_exposed(cone, [_aircraft()], AT, lookahead_min=60, vertical_margin_ft=0) == []


# --- fuel -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("type_icao", "category"),
    [
        ("A20N", AircraftCategory.NARROWBODY),
        ("A21N", AircraftCategory.NARROWBODY),
        ("A320", AircraftCategory.NARROWBODY),
        ("A321", AircraftCategory.NARROWBODY),
        ("B738", AircraftCategory.NARROWBODY),
        ("B38M", AircraftCategory.NARROWBODY),
        ("B739", AircraftCategory.NARROWBODY),
        ("A332", AircraftCategory.WIDEBODY),
        ("A333", AircraftCategory.WIDEBODY),
        ("A359", AircraftCategory.WIDEBODY),
        ("B772", AircraftCategory.WIDEBODY),
        ("B77W", AircraftCategory.WIDEBODY),
        ("B788", AircraftCategory.WIDEBODY),
        ("B789", AircraftCategory.WIDEBODY),
        ("AT76", AircraftCategory.TURBOPROP),
        ("E190", AircraftCategory.REGIONAL_JET),
        ("C172", AircraftCategory.LIGHT),
        (" b738 ", AircraftCategory.NARROWBODY),
        ("ZZZZ", AircraftCategory.UNKNOWN),
        ("", AircraftCategory.UNKNOWN),
        (None, AircraftCategory.UNKNOWN),
    ],
)
def test_category_for_type(type_icao: str | None, category: AircraftCategory) -> None:
    assert category_for_type(type_icao) is category


def test_burn_rates_cover_every_category() -> None:
    assert set(BURN_KG_PER_MIN) == set(AircraftCategory)
    assert BURN_KG_PER_MIN[AircraftCategory.UNKNOWN] == BURN_KG_PER_MIN[AircraftCategory.NARROWBODY]


def test_hold_line_formula() -> None:
    line = hold_line(AircraftCategory.NARROWBODY)
    assert line.action is ActionKind.HOLD
    assert (line.minutes, line.fuel_kg, line.burn_kg_per_min) == (20, 840, 42)
    assert line.formula == "HOLD 20 MIN x 42 KG/MIN (NARROWBODY) = 840 KG"
    assert hold_line(AircraftCategory.WIDEBODY).fuel_kg == 2200
    assert hold_line(AircraftCategory.TURBOPROP).formula == (
        "HOLD 20 MIN x 12 KG/MIN (TURBOPROP) = 240 KG"
    )


def test_hold_line_unknown_type_says_so() -> None:
    line = hold_line(AircraftCategory.UNKNOWN)
    assert line.fuel_kg == 840
    assert line.category is AircraftCategory.UNKNOWN
    assert "(TYPE UNKNOWN, NARROWBODY RATE)" in line.formula


def test_divert_line_rounds_minutes_and_fuel_up() -> None:
    line = divert_line(
        AircraftCategory.NARROWBODY, alternate_icao="WARR", distance_nm=182.0, gs_kt=430.0
    )
    # 182 / 430 * 60 = 25.4 -> 26 min; + 15 = 41 min; x 42 = 1722 kg.
    assert line.action is ActionKind.DIVERT
    assert (line.minutes, line.fuel_kg) == (41, 1722)
    assert line.alternate_icao == "WARR"
    assert line.distance_nm == 182.0
    assert line.formula == (
        "DIVERT WARR 182 NM AT 430 KT = 26 MIN + 15 MIN = 41 MIN x 42 KG/MIN (NARROWBODY) = 1722 KG"
    )


@pytest.mark.parametrize("gs_kt", [None, 0.0, 120.0, 149.9])
def test_divert_line_assumes_250_kt_for_missing_or_slow_speed(gs_kt: float | None) -> None:
    line = divert_line(
        AircraftCategory.WIDEBODY, alternate_icao="WADD", distance_nm=125.0, gs_kt=gs_kt
    )
    # Exactly 30 min (no float noise pushing it to 31); + 15 = 45 min x 110 = 4950 kg.
    assert (line.minutes, line.fuel_kg) == (45, 4950)
    assert "250 KT (ASSUMED)" in line.formula


@pytest.mark.parametrize(
    ("distance_nm", "gs_kt", "prefix"),
    [
        (100.0, 399.6, "DIVERT WARR 100 NM AT 400 KT = 15 MIN + 15 MIN = 30 MIN"),
        (125.4, None, "DIVERT WARR 125 NM AT 250 KT (ASSUMED) = 30 MIN + 15 MIN = 45 MIN"),
    ],
)
def test_divert_line_minutes_follow_from_the_printed_formula(
    distance_nm: float, gs_kt: float | None, prefix: str
) -> None:
    line = divert_line(
        AircraftCategory.NARROWBODY, alternate_icao="WARR", distance_nm=distance_nm, gs_kt=gs_kt
    )
    assert line.formula.startswith(prefix)
    assert line.fuel_kg == line.minutes * 42


def test_divert_line_trusts_cruise_speed() -> None:
    line = divert_line(
        AircraftCategory.UNKNOWN, alternate_icao="WIII", distance_nm=300.0, gs_kt=450.0
    )
    assert line.minutes == 40 + 15
    assert "AT 450 KT =" in line.formula
    assert "(ASSUMED)" not in line.formula
    assert "(TYPE UNKNOWN, NARROWBODY RATE)" in line.formula
