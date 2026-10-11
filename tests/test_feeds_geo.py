"""feeds-geo: ADS-B, winds, satellite frames and the volcano/airport catalogues.

Every test reads saved feed responses from ``tests/fixtures`` (fetched 2026-10-09
19:36-19:44Z) or the shipped ``data/*.json``; nothing touches the network.
"""

import io
import json
import math
import re
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image

from tephra.config import REGIONS
from tephra.feeds.adsb import (
    AdsbPointsFailed,
    fetch_aircraft,
    merge_aircraft,
    parse_adsb,
    point_url,
    query_points,
)
from tephra.feeds.airports import AirportCatalogue, load_airports
from tephra.feeds.base import FetchError, FetchResult, build_url
from tephra.feeds.satellite import (
    FRAME_CAPTION_SUFFIX,
    JMA_AREAS,
    JMA_SLOTS_URL,
    NICT_LATEST_URL,
    fetch_frames,
    frame_key,
    fulldisk_pixel,
    parse_jma_slots,
)
from tephra.feeds.volcanoes import VolcanoCatalogue, load_volcanoes
from tephra.feeds.winds import (
    OPEN_METEO_URL,
    fetch_winds,
    parse_winds,
    profile_at,
    wind_at_fl,
    wind_params,
)
from tephra.geo.units import haversine_km
from tephra.models import (
    PRESSURE_LEVEL_FL,
    AdsbQueryPoint,
    BBox,
    FeedId,
    FrameProduct,
    Region,
    VaacCentre,
    Volcano,
)
from tephra.policy import load_policy
from tephra.store.base import BLOB_KEY_PATTERN
from tephra.util import timeutil
from tephra.util.hashing import combine_hashes, sha256_bytes

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "fixtures"
DATA_DIR = REPO / "data"
MIN_RUNWAY_M = load_policy(DATA_DIR).alternates.min_runway_m.value

ADSB_JAVA = FIXTURES / "adsb" / "point_java_-7.9_112.9_250.json"
ADSB_JAKARTA = FIXTURES / "adsb" / "point_jakarta_-6.1_106.7_150.json"
ADSB_KYUSHU = FIXTURES / "adsb" / "point_kyushu_31.6_130.6_200.json"
WINDS_SEMERU = FIXTURES / "openmeteo" / "semeru_pressure_level_winds.json"
HIMAWARI = FIXTURES / "himawari"

SAMPLED_AT = datetime(2026, 10, 9, 19, 43, tzinfo=UTC)


def _result(
    content: bytes,
    *,
    url: str,
    feed: FeedId,
    fetched_at: datetime = SAMPLED_AT,
    stale: bool = False,
    stale_age_s: int | None = None,
) -> FetchResult:
    return FetchResult(
        feed=feed,
        url=url,
        status_code=200,
        content=content,
        content_type=None,
        fetched_at=fetched_at,
        sha256=sha256_bytes(content),
        stale=stale,
        stale_age_s=stale_age_s if stale else None,
    )


class FakeSource:
    """Answers GETs from a URL -> bytes table; unknown URLs fail like a 404.

    ``stale_urls`` answer like HttpSource's last-good copy, ``stale_age_s`` old.
    """

    def __init__(
        self,
        responses: Mapping[str, bytes],
        *,
        fetched_at: datetime = SAMPLED_AT,
        stale_urls: frozenset[str] = frozenset(),
        stale_age_s: int = 60,
    ) -> None:
        self._responses = dict(responses)
        self._fetched_at = fetched_at
        self._stale_urls = stale_urls
        self._stale_age_s = stale_age_s
        self.calls: list[str] = []

    async def fetch(
        self, url: str, *, feed: FeedId, params: Mapping[str, str] | None = None
    ) -> FetchResult:
        full_url = build_url(url, params)
        self.calls.append(full_url)
        if full_url not in self._responses:
            raise FetchError(full_url, feed, "HTTP 404")
        return _result(
            self._responses[full_url],
            url=full_url,
            feed=feed,
            fetched_at=self._fetched_at,
            stale=full_url in self._stale_urls,
            stale_age_s=self._stale_age_s,
        )

    async def aclose(self) -> None:
        return None


@pytest.fixture(scope="module")
def volcanoes() -> VolcanoCatalogue:
    return load_volcanoes(DATA_DIR)


@pytest.fixture(scope="module")
def airports() -> AirportCatalogue:
    return load_airports(DATA_DIR, min_runway_m=MIN_RUNWAY_M)


def _snapshot(path: Path, lat: float, lon: float, radius_nm: int, fetched_at: datetime):
    query = AdsbQueryPoint(lat=lat, lon=lon, radius_nm=radius_nm)
    result = _result(
        path.read_bytes(), url=point_url(query), feed=FeedId.ADSB, fetched_at=fetched_at
    )
    return parse_adsb(result, query)


# --- ADS-B ------------------------------------------------------------------------------


def test_point_url_uses_three_decimals() -> None:
    query = AdsbQueryPoint(lat=-7.9, lon=112.9, radius_nm=250)
    assert point_url(query) == "https://api.adsb.lol/v2/point/-7.900/112.900/250"


def test_query_points_skips_volcanoes_near_a_chosen_point(volcanoes: VolcanoCatalogue) -> None:
    region = Region(
        key="test",
        name="Test",
        center_lat=-7.6,
        center_lon=111.0,
        zoom=6,
        bbox=BBox(west=104.5, south=-9.8, east=117.5, north=-5.0),
        adsb_points=[],
    )
    kelud, bromo, merapi = (volcanoes.get(i) for i in ("263280", "263310", "263250"))
    assert kelud is not None
    assert bromo is not None
    assert merapi is not None
    points = query_points(region, [kelud, bromo, merapi], radius_nm=300)
    assert [(p.lat, p.lon) for p in points] == [(-7.935, 112.314), (-7.54, 110.446)]
    assert all(p.radius_nm == 250 for p in points)


def test_query_points_keeps_region_points_first(volcanoes: VolcanoCatalogue) -> None:
    region = REGIONS["java_bali"]
    semeru, merapi = volcanoes.get("263300"), volcanoes.get("263250")
    assert semeru is not None
    assert merapi is not None
    points = query_points(region, [semeru, merapi], radius_nm=250)
    # Semeru lies within 50 nm of the region's East Java point, Merapi does not.
    assert points[: len(region.adsb_points)] == region.adsb_points
    assert [(p.lat, p.lon) for p in points[len(region.adsb_points) :]] == [(-7.54, 110.446)]


def test_parse_adsb_java_fixture() -> None:
    fetched_at = datetime(2026, 10, 9, 19, 40, 46, tzinfo=UTC)
    snapshot = _snapshot(ADSB_JAVA, -7.9, 112.9, 250, fetched_at)
    assert len(snapshot.aircraft) == 7
    assert snapshot.provenance.source_id == "ADSB:-7.900:112.900:20261009T194046Z"
    assert snapshot.provenance.feed is FeedId.ADSB
    response_at = timeutil.parse_iso(1791574846501)
    assert snapshot.provenance.issued_at == response_at

    by_hex = {aircraft.hex: aircraft for aircraft in snapshot.aircraft}
    batik = by_hex["8a091f"]
    assert batik.callsign == "BTK6264"
    assert batik.type_icao == "A320"
    assert batik.alt_baro_ft == 31025
    assert batik.nav_altitude_mcp_ft == 31000
    assert batik.gs_kt == pytest.approx(458.7)
    assert batik.track_deg == pytest.approx(93.25)
    assert batik.baro_rate_fpm == -64
    assert batik.observed_at == response_at - timedelta(seconds=0.383)
    assert batik.source_id == snapshot.provenance.source_id
    assert batik.airline

    assert by_hex["885118"].callsign is None  # no 'flight' key in the response
    dumped = snapshot.model_dump_json()
    assert "PK-BKJ" not in dumped
    assert "9V-SKY" not in dumped


def test_parse_adsb_kyushu_keeps_targets_without_track() -> None:
    snapshot = _snapshot(ADSB_KYUSHU, 31.6, 130.6, 200, SAMPLED_AT)
    assert len(snapshot.aircraft) == 19
    by_hex = {aircraft.hex: aircraft for aircraft in snapshot.aircraft}
    stale = by_hex["84b807"]
    assert (stale.gs_kt, stale.track_deg, stale.nav_altitude_mcp_ft) == (None, None, None)
    assert by_hex["861bd2"].nav_altitude_mcp_ft == 37000  # 36992 is FL370
    assert by_hex["899097"].seen_pos_s == pytest.approx(48.863)


def test_parse_adsb_drops_ground_unpositioned_and_registration_callsigns() -> None:
    payload = {
        "now": 1791574846501,
        "ac": [
            {"hex": "aaaaa1", "flight": "GIA417  ", "lat": -7.0, "lon": 112.0, "alt_baro": 30000},
            {"hex": "aaaaa2", "lat": -7.0, "lon": 112.0, "alt_baro": "ground"},
            {"hex": "aaaaa3", "flight": "GIA419  ", "alt_baro": 12000},
            {"hex": "AAAAA4", "flight": "PKABC   ", "r": "PK-ABC", "lat": -7.1, "lon": 112.1},
            {"flight": "NOHEX1", "lat": -7.0, "lon": 112.0},
            "not an object",
        ],
    }
    query = AdsbQueryPoint(lat=-7.0, lon=112.0, radius_nm=100)
    result = _result(json.dumps(payload).encode(), url=point_url(query), feed=FeedId.ADSB)
    snapshot = parse_adsb(result, query)
    assert [aircraft.hex for aircraft in snapshot.aircraft] == ["aaaaa1", "aaaaa4"]
    general_aviation = snapshot.aircraft[1]
    assert general_aviation.callsign is None
    assert general_aviation.alt_baro_ft is None


@pytest.mark.parametrize(
    "body",
    [
        b"<html>busy</html>",
        b"[]",
        b'{"ac": []}',
        b'{"now": null, "ac": []}',
        b'{"now": [1791574846501], "ac": []}',
        b'{"now": Infinity, "ac": []}',
        b'{"now": 1e20, "ac": []}',
    ],
)
def test_parse_adsb_rejects_unreadable_responses(body: bytes) -> None:
    """A ValueError fails only this point; anything else would abort the whole ADS-B pass."""
    query = AdsbQueryPoint(lat=-7.0, lon=112.0, radius_nm=100)
    with pytest.raises(ValueError, match=r"adsb\.lol"):
        parse_adsb(_result(body, url=point_url(query), feed=FeedId.ADSB), query)


def test_parse_adsb_never_passes_on_a_non_finite_number() -> None:
    """json.loads reads NaN and Infinity tokens and float() reads 'nan' and 'inf'; a NaN
    position must never reach the Wall, and round(inf) must not abort the snapshot."""
    body = (
        b'{"now": 1791574846501, "ac": ['
        b'{"hex": "ccccc1", "flight": "GIA417", "lat": NaN, "lon": 112.0, "alt_baro": 30000},'
        b'{"hex": "ccccc2", "flight": "GIA418", "lat": -7.0, "lon": "inf", "alt_baro": 30000},'
        b'{"hex": "ccccc3", "flight": "GIA419", "lat": -7.0, "lon": 112.0,'
        b' "alt_baro": "Infinity", "alt_geom": -Infinity, "nav_altitude_mcp": NaN,'
        b' "gs": "nan", "track": Infinity, "baro_rate": 1e999, "seen_pos": "inf"}'
        b"]}"
    )
    query = AdsbQueryPoint(lat=-7.0, lon=112.0, radius_nm=100)
    snapshot = parse_adsb(_result(body, url=point_url(query), feed=FeedId.ADSB), query)
    (aircraft,) = snapshot.aircraft
    assert aircraft.hex == "ccccc3"
    numbers = (
        aircraft.alt_baro_ft,
        aircraft.alt_geom_ft,
        aircraft.nav_altitude_mcp_ft,
        aircraft.gs_kt,
        aircraft.track_deg,
        aircraft.baro_rate_fpm,
        aircraft.seen_pos_s,
    )
    assert numbers == (None,) * len(numbers)
    assert aircraft.observed_at == snapshot.provenance.issued_at


def test_parse_adsb_skips_targets_with_numbers_out_of_range() -> None:
    payload = {
        "now": 1791574846501,
        "ac": [
            {"hex": "ddddd1", "flight": "GIA417", "lat": -7.0, "lon": 112.0, "seen_pos": 1e300},
            {"hex": "ddddd2", "flight": "GIA418", "lat": -7.1, "lon": 112.1},
            {"hex": "ddddd3", "flight": "GIA419", "lat": 10**400, "lon": 112.2},
        ],
    }
    query = AdsbQueryPoint(lat=-7.0, lon=112.0, radius_nm=100)
    result = _result(json.dumps(payload).encode(), url=point_url(query), feed=FeedId.ADSB)
    assert [aircraft.hex for aircraft in parse_adsb(result, query).aircraft] == ["ddddd2"]


def test_merge_aircraft_keeps_the_newest_copy() -> None:
    java = _snapshot(ADSB_JAVA, -7.9, 112.9, 250, SAMPLED_AT)
    jakarta = _snapshot(ADSB_JAKARTA, -6.1, 106.7, 150, SAMPLED_AT)
    merged = merge_aircraft([java, jakarta])
    hexes = [aircraft.hex for aircraft in merged]
    assert hexes == sorted(hexes)
    assert len(merged) == 7 + 6 - 1  # BTK6264 (8a091f) is in both circles
    batik = next(aircraft for aircraft in merged if aircraft.hex == "8a091f")
    assert batik.lon == pytest.approx(109.175026)  # the Jakarta copy is 3 s newer
    assert batik.source_id == jakarta.provenance.source_id


def test_parse_adsb_never_takes_the_level_from_alt_geom() -> None:
    payload = {
        "now": 1791574846501,
        "ac": [{"hex": "bbbbb1", "flight": "GIA417", "lat": -7.0, "lon": 112.0, "alt_geom": 31000}],
    }
    query = AdsbQueryPoint(lat=-7.0, lon=112.0, radius_nm=100)
    result = _result(json.dumps(payload).encode(), url=point_url(query), feed=FeedId.ADSB)
    (aircraft,) = parse_adsb(result, query).aircraft
    assert (aircraft.alt_baro_ft, aircraft.alt_geom_ft) == (None, 31000)


async def test_fetch_aircraft_reports_failed_points_after_trying_every_point() -> None:
    """A point lost to a 429 must not look like an empty sky (first live run, 2026-10-10)."""
    good = AdsbQueryPoint(lat=-7.9, lon=112.9, radius_nm=250)
    failing = AdsbQueryPoint(lat=1.2, lon=127.8, radius_nm=220)
    garbled = AdsbQueryPoint(lat=31.8, lon=130.6, radius_nm=200)
    source = FakeSource(
        {point_url(good): ADSB_JAVA.read_bytes(), point_url(garbled): b"<html>oops</html>"}
    )
    with pytest.raises(AdsbPointsFailed) as caught:
        await fetch_aircraft(source, [failing, good, garbled])
    assert source.calls == [point_url(failing), point_url(good), point_url(garbled)]
    error = caught.value
    assert isinstance(error, FetchError)
    assert error.feed is FeedId.ADSB
    assert "2 of 3" in error.reason
    assert error.failed_points == [failing, garbled]
    assert [snapshot.query for snapshot in error.snapshots] == [good]
    assert len(error.snapshots[0].aircraft) == 7


async def test_fetch_aircraft_does_not_pass_an_old_cached_copy_off_as_traffic() -> None:
    point = AdsbQueryPoint(lat=-7.9, lon=112.9, radius_nm=250)
    url = point_url(point)
    source = FakeSource(
        {url: ADSB_JAVA.read_bytes()}, stale_urls=frozenset({url}), stale_age_s=3600
    )
    with pytest.raises(AdsbPointsFailed, match="cached copy") as caught:
        await fetch_aircraft(source, [point])
    assert caught.value.snapshots == []


async def test_fetch_aircraft_keeps_a_recent_cached_copy_marked_stale() -> None:
    point = AdsbQueryPoint(lat=-7.9, lon=112.9, radius_nm=250)
    url = point_url(point)
    source = FakeSource({url: ADSB_JAVA.read_bytes()}, stale_urls=frozenset({url}), stale_age_s=35)
    (snapshot,) = await fetch_aircraft(source, [point])
    assert snapshot.provenance.stale
    assert snapshot.provenance.stale_age_s == 35
    assert len(snapshot.aircraft) == 7


# --- winds ------------------------------------------------------------------------------


def _isa_pressure_altitude_ft(hpa: float) -> float:
    """ICAO standard atmosphere: troposphere to 226.32 hPa, isothermal layer above."""
    if hpa >= 226.32:
        return 145366.45 * (1.0 - (hpa / 1013.25) ** 0.190284)
    return 36089.24 + 20805.8 * math.log(226.32 / hpa)


def test_pressure_level_table_matches_the_standard_atmosphere() -> None:
    for hpa, flight_level in PRESSURE_LEVEL_FL.items():
        assert abs(_isa_pressure_altitude_ft(hpa) - flight_level * 100) < 500, hpa
    assert sorted(PRESSURE_LEVEL_FL.values()) == [50, 100, 140, 180, 240, 300, 340, 390, 450]


def test_wind_params_fixed_order() -> None:
    params = wind_params(-8.108, 112.922)
    assert list(params) == [
        "latitude",
        "longitude",
        "hourly",
        "wind_speed_unit",
        "timezone",
        "past_hours",
        "forecast_hours",
    ]
    assert params["latitude"] == "-8.11"
    assert params["longitude"] == "112.92"
    assert params["hourly"].startswith("wind_speed_150hPa,wind_direction_150hPa,wind_speed_200hPa")
    assert params["hourly"].endswith("wind_speed_850hPa,wind_direction_850hPa")
    assert (params["wind_speed_unit"], params["timezone"]) == ("kn", "GMT")


def _semeru_profiles():
    result = _result(WINDS_SEMERU.read_bytes(), url=OPEN_METEO_URL, feed=FeedId.WINDS)
    return parse_winds(result, lat=-8.108, lon=112.922)


def test_parse_winds_fixture() -> None:
    profiles = _semeru_profiles()
    assert len(profiles) == 24
    assert profiles[0].valid_at == datetime(2026, 10, 9, 0, 0, tzinfo=UTC)
    assert profiles[-1].valid_at == datetime(2026, 10, 9, 23, 0, tzinfo=UTC)
    # The fixture was requested without 150 hPa, so FL450 is simply absent.
    assert [level.flight_level for level in profiles[0].levels] == [
        50, 100, 140, 180, 240, 300, 340, 390,
    ]  # fmt: skip
    at_1900 = profiles[19]
    assert at_1900.provenance.source_id == "WINDS:-8.11:112.92:20261009T1900Z"
    assert at_1900.provenance.valid_to == at_1900.valid_at + timedelta(hours=1)
    fl140 = next(level for level in at_1900.levels if level.pressure_hpa == 600)
    assert (fl140.flight_level, fl140.speed_kt, fl140.from_deg) == (140, 6.6, 290.0)
    assert fl140.toward_deg == pytest.approx(110.0)


def test_profile_at_and_wind_at_fl() -> None:
    profiles = _semeru_profiles()
    profile = profile_at(profiles, datetime(2026, 10, 9, 19, 20, tzinfo=UTC))
    assert profile is not None
    assert profile.valid_at == datetime(2026, 10, 9, 19, 0, tzinfo=UTC)
    assert wind_at_fl(profile, 150).pressure_hpa == 600
    assert wind_at_fl(profile, 160).pressure_hpa == 600  # tie between FL140 and FL180
    assert wind_at_fl(profile, 450).pressure_hpa == 200
    assert profile_at([], datetime(2026, 10, 9, tzinfo=UTC)) is None


def test_parse_winds_rejects_a_response_without_hourly_data() -> None:
    result = _result(b'{"error": true, "reason": "bad"}', url=OPEN_METEO_URL, feed=FeedId.WINDS)
    with pytest.raises(ValueError, match="hourly"):
        parse_winds(result, lat=0.0, lon=0.0)


async def test_fetch_winds_requests_the_documented_url() -> None:
    url = build_url(OPEN_METEO_URL, wind_params(-8.108, 112.922))
    source = FakeSource({url: WINDS_SEMERU.read_bytes()})
    profiles = await fetch_winds(source, -8.108, 112.922)
    assert source.calls == [url]
    assert len(profiles) == 24


# --- volcano catalogue ------------------------------------------------------------------

REQUIRED_VOLCANOES = {
    "263300": "Semeru",
    "264180": "Lewotobi",
    "268030": "Ibu",
    "268010": "Dukono",
    "261140": "Marapi",
    "262000": "Krakatau",
    "263250": "Merapi",
    "263340": "Raung",
    "264020": "Agung",
    "267010": "Ruang",
    "267020": "Karangetang",
    "261080": "Sinabung",
    "282080": "Sakurajima",
    "282030": "Suwanosejima",
    "282090": "Shinmoedake",
    "282110": "Aso",
    "272020": "Kanlaon",
    "273070": "Taal",
    "273030": "Mayon",
    "273010": "Bulusan",
    "251020": "Manam",
    "255020": "Bagana",
}


def test_catalogue_has_the_required_volcanoes(volcanoes: VolcanoCatalogue) -> None:
    for volcano_id, name in REQUIRED_VOLCANOES.items():
        volcano = volcanoes.get(volcano_id)
        assert volcano is not None, volcano_id
        assert volcanoes.resolve(name) == volcano, name
    for volcano in volcanoes.all():
        expected = VaacCentre.TOKYO if volcano.country in {"Japan", "Philippines"} else None
        assert volcano.vaac == (expected or VaacCentre.DARWIN), volcano.name


@pytest.mark.parametrize(
    ("name", "volcano_id"),
    [
        ("SAKURAJIMA (AIRA CALDERA)", "282080"),
        ("SAKURAJIMA [AIRA CALDERA]", "282080"),
        ("Aira", "282080"),
        ("Semeru (263300)", "263300"),
        ("DUKONO 268010", "268010"),
        ("263300", "263300"),
        ("MT SEMERU", "263300"),
        ("Lewotobi Laki-laki", "264180"),
        ("ili lewotolok", "264230"),
        ("Anak Krakatau", "262000"),
        ("KIRISHIMAYAMA", "282090"),
    ],
)
def test_resolve_names_as_feeds_print_them(
    volcanoes: VolcanoCatalogue, name: str, volcano_id: str
) -> None:
    volcano = volcanoes.resolve(name)
    assert volcano is not None
    assert volcano.id == volcano_id


@pytest.mark.parametrize("name", ["FUEGO", "SHEVELUCH 300270", "", "NOTICE 999999"])
def test_resolve_unknown_names(volcanoes: VolcanoCatalogue, name: str) -> None:
    assert volcanoes.resolve(name) is None


def test_find_in_text_reads_every_indonesian_sigmet(volcanoes: VolcanoCatalogue) -> None:
    records = json.loads((FIXTURES / "isigmet" / "isigmet_va.json").read_bytes())
    expected = {"SEMERU": "263300", "IBU": "268030", "DUKONO": "268010", "KRAKATAU": "262000"}
    seen: set[str] = set()
    for record in records:
        found = volcanoes.find_in_text(record["rawSigmet"])
        name = (record["qualifier"] or "").removeprefix("ERUPTION MT ").strip()
        if record["firId"] in {"WAAF", "WIIF"}:
            assert found is not None, record["rawSigmet"]
            assert found.id == expected[name]
            seen.add(name)
        else:
            assert found is None, record["rawSigmet"]  # Central and South America
    assert seen == set(expected)


def test_find_in_text_matches_whole_words_only(volcanoes: VolcanoCatalogue) -> None:
    anak = volcanoes.find_in_text("VOLCANO: ANAK KRAKATAU 262000")
    assert anak is not None
    assert anak.id == "262000"
    assert volcanoes.find_in_text("IBUKOTA NUSANTARA S0806 E11255") is None
    first = volcanoes.find_in_text("VA FM MT IBU, NOT DUKONO")
    assert first is not None
    assert first.id == "268030"


def test_vaa_fixture_volcanoes_resolve_to_their_printed_numbers(
    volcanoes: VolcanoCatalogue,
) -> None:
    pages = [
        *(FIXTURES / "tokyo_vaac").glob("*_Text.html"),
        *(FIXTURES / "darwin_vaac").glob("*_Text.html"),
    ]
    assert pages
    for page in pages:
        match = re.search(r"VOLCANO:\s*([^<\n]+?)\s+(\d{6})", page.read_text(encoding="utf-8"))
        assert match is not None, page.name
        volcano = volcanoes.resolve(match.group(1))
        assert volcano is not None, match.group(1)
        assert volcano.id == match.group(2)


@pytest.mark.parametrize("fixture", ["vona_22880_semeru_ash.html", "vona_22881_ibu_ash.html"])
def test_magma_locations_agree_with_gvp(volcanoes: VolcanoCatalogue, fixture: str) -> None:
    page = (FIXTURES / "magma" / fixture).read_text(encoding="utf-8")
    number = re.search(r"\((\d{6})\)", page)
    location = re.search(
        r"([NS]) (\d+) deg (\d+) min (\d+) sec ([EW]) (\d+) deg (\d+) min (\d+) sec", page
    )
    assert number is not None
    assert location is not None
    hemi_lat, lat_d, lat_m, lat_s, hemi_lon, lon_d, lon_m, lon_s = location.groups()
    lat = (int(lat_d) + int(lat_m) / 60 + int(lat_s) / 3600) * (-1 if hemi_lat == "S" else 1)
    lon = (int(lon_d) + int(lon_m) / 60 + int(lon_s) / 3600) * (-1 if hemi_lon == "W" else 1)
    volcano = volcanoes.get(number.group(1))
    assert volcano is not None
    assert haversine_km(lat, lon, volcano.lat, volcano.lon) < 2.0


def test_catalogue_lookups(volcanoes: VolcanoCatalogue) -> None:
    semeru = volcanoes.by_magma_code("smr")
    assert semeru is not None
    assert semeru.id == "263300"
    assert volcanoes.nearest(-8.1, 112.9, max_km=50) == semeru
    assert volcanoes.nearest(0.0, 0.0, max_km=500) is None
    kyushu = {volcano.id for volcano in volcanoes.in_bbox(REGIONS["kyushu"].bbox)}
    assert {"282080", "282090", "282110"} <= kyushu
    assert "282030" not in kyushu  # Suwanosejima lies south of the preset


def test_catalogue_rejects_an_alias_shared_by_two_volcanoes() -> None:
    def volcano(volcano_id: str, name: str, aliases: list[str]) -> Volcano:
        return Volcano(
            id=volcano_id,
            name=name,
            aliases=aliases,
            country="Indonesia",
            lat=0.0,
            lon=0.0,
            summit_elev_m=100,
            observatory="test",
            vaac=VaacCentre.DARWIN,
        )

    with pytest.raises(ValueError, match="names both"):
        VolcanoCatalogue([volcano("1", "One", ["SHARED"]), volcano("2", "Two", ["Shared"])])


# --- airport catalogue ------------------------------------------------------------------


def test_airport_file_is_consistent(airports: AirportCatalogue) -> None:
    # Alternates are chosen by runway length, so every airport needs one.
    assert all(airport.longest_runway_m for airport in airports.all())
    expected = {
        "WIII", "WIHH", "WICA", "WARR", "WAHI", "WADD", "WAMM", "WAEE",
        "RJFK", "RJFT", "RJFM", "RJFO", "RJFU", "RJFF", "RPLL", "WSSS", "YPDN",
    }  # fmt: skip
    assert expected <= airports.icaos()


def test_every_taf_fixture_station_is_catalogued(airports: AirportCatalogue) -> None:
    stations = {item["icaoId"] for item in json.loads((FIXTURES / "wx" / "taf.json").read_bytes())}
    assert stations
    assert stations <= airports.icaos()


def test_nearest_alternates(airports: AirportCatalogue) -> None:
    found = airports.nearest(-8.108, 112.922, limit=4, max_nm=200)
    distances = [distance for _, distance in found]
    assert len(found) == 4
    assert distances == sorted(distances)
    assert all(airports.alternate_ok(airport) for airport, _ in found)
    assert found[0][0].icao == "WARA"  # Malang, about 15 nm from Semeru
    everything = airports.nearest(-8.108, 112.922, limit=50, max_nm=200, alternates_only=False)
    assert "WADY" in {airport.icao for airport, _ in everything}  # short runway, not alternate
    assert airports.get("warr") == airports.get("WARR")
    assert airports.nearest(0.0, 0.0, max_nm=100) == []


def test_alternates_follow_the_policy_runway_length(airports: AirportCatalogue) -> None:
    short = airports.get("WADY")
    assert short is not None
    assert short.longest_runway_m is not None
    assert short.longest_runway_m < MIN_RUNWAY_M
    assert not airports.alternate_ok(short)
    relaxed = load_airports(DATA_DIR, min_runway_m=short.longest_runway_m)
    assert relaxed.alternate_ok(short)


# --- satellite frames -------------------------------------------------------------------


def test_frame_key_is_a_valid_blob_key() -> None:
    key = frame_key("263300", FrameProduct.B13_IR, datetime(2026, 10, 9, 19, 0, tzinfo=UTC))
    assert key == "frames/263300_B13_IR_20261009T1900Z.png"
    assert re.fullmatch(BLOB_KEY_PATTERN, key)


def test_parse_jma_slots_fixture() -> None:
    page = (HIMAWARI / "jma_mscweb_sat_img_se3.html").read_bytes()
    slots = parse_jma_slots(_result(page, url=JMA_SLOTS_URL, feed=FeedId.FRAMES))
    assert len(slots) == 137
    assert slots[0] == datetime(2026, 10, 9, 19, 20, tzinfo=UTC)  # labelled 19:30 UTC
    assert slots[-1] == datetime(2026, 10, 8, 20, 0, tzinfo=UTC)


def test_inferred_projections_place_known_points() -> None:
    se3, jpn = JMA_AREAS
    x, y = se3.projection.to_pixel(-8.108, 112.922)
    assert (round(x), round(y)) == (458, 362)
    x, y = jpn.projection.to_pixel(31.5772, 130.6589)
    assert (round(x), round(y)) == (313, 408)
    assert not se3.covers(31.58, 130.66)
    assert jpn.covers(31.58, 130.66)
    darwin = fulldisk_pixel(-12.42, 130.88, 2200)
    assert darwin is not None
    assert (int(darwin[0] // 550), int(darwin[1] // 550)) == (1, 2)
    assert fulldisk_pixel(0.0, -40.0, 2200) is None  # far side of the earth


def _jma_responses(slot: str = "1900") -> dict[str, bytes]:
    base = "https://www.data.jma.go.jp/mscweb/data/himawari/img/se3/se3_{}_" + slot + ".jpg"
    return {
        build_url(JMA_SLOTS_URL, {"area": "se3"}): (
            HIMAWARI / "jma_mscweb_sat_img_se3.html"
        ).read_bytes(),
        # The fixture JPEGs are slot 1920; the crop does not care which slot they are.
        base.format("b13"): (HIMAWARI / "jma_se3_b13_1920.jpg").read_bytes(),
        base.format("dst"): (HIMAWARI / "jma_se3_dst_1920.jpg").read_bytes(),
    }


async def test_fetch_frames_at_night_returns_jma_crops_only(volcanoes: VolcanoCatalogue) -> None:
    semeru = volcanoes.get("263300")
    assert semeru is not None
    responses = _jma_responses()
    responses[NICT_LATEST_URL] = (HIMAWARI / "nict_latest.json").read_bytes()
    source = FakeSource(responses)

    frames = await fetch_frames(source, semeru)

    assert [frame.product for frame, _ in frames] == [FrameProduct.B13_IR, FrameProduct.DUST_RGB]
    # Fetched at 19:43Z, so the newest slot old enough to be today's is 19:00Z.
    slot = datetime(2026, 10, 9, 19, 0, tzinfo=UTC)
    for frame, png in frames:
        assert frame.observed_at == slot
        assert frame.bbox is None
        assert frame.volcano_id == "263300"
        assert frame.image_key == frame_key("263300", frame.product, slot)
        assert frame.provenance.source_id == f"FRAME:{frame.product.value}:263300:20261009T1900Z"
        assert frame.provenance.issued_at == slot
        assert FRAME_CAPTION_SUFFIX in frame.caption
        with Image.open(io.BytesIO(png)) as image:
            assert image.format == "PNG"
            assert image.size == (frame.width_px, frame.height_px)
        assert 100 <= frame.width_px <= 130  # 600 km at 0.05 deg/px
    assert not any("/D531106/" in call and call.endswith(".png") for call in source.calls)


async def test_fetch_frames_skips_jma_when_the_slot_list_is_stale(
    volcanoes: VolcanoCatalogue,
) -> None:
    semeru = volcanoes.get("263300")
    assert semeru is not None
    page_url = build_url(JMA_SLOTS_URL, {"area": "se3"})
    source = FakeSource(_jma_responses(), stale_urls=frozenset({page_url}))
    # NICT is not in the table either, so nothing at all came back: that is an outage.
    with pytest.raises(FetchError, match="slot list served from cache"):
        await fetch_frames(source, semeru)
    assert not any(call.endswith(".jpg") for call in source.calls)


def _nict_day_source(tile: Path) -> FakeSource:
    latest = b'{"date":"2026-10-09 05:00:00","file":"PI_H09_20261009_0500_TRC_FLDK_R10_PGPFD.png"}'
    tile_url = "https://himawari8.nict.go.jp/img/D531106/4d/550/2026/10/09/050000_1_2.png"
    return FakeSource({NICT_LATEST_URL: latest, tile_url: tile.read_bytes()})


async def test_fetch_frames_crops_nict_true_colour_in_daylight(
    volcanoes: VolcanoCatalogue,
) -> None:
    lewotobi = volcanoes.get("264180")
    assert lewotobi is not None
    tile = HIMAWARI / "nict_D531106_4d_550_20261009_050000_1_2_daytime.png"
    frames = await fetch_frames(_nict_day_source(tile), lewotobi, areas=(), nict_level=4)

    assert len(frames) == 1
    frame, png = frames[0]
    assert frame.product is FrameProduct.TRUE_COLOR
    assert frame.observed_at == datetime(2026, 10, 9, 5, 0, tzinfo=UTC)
    assert frame.bbox is None
    assert frame.provenance.sha256 == combine_hashes([sha256_bytes(tile.read_bytes())])
    with Image.open(io.BytesIO(png)) as image:
        assert image.size == (frame.width_px, frame.height_px)
        assert image.size[0] > 50


async def test_nict_is_never_asked_when_switched_off(volcanoes: VolcanoCatalogue) -> None:
    """NICT's terms are non-commercial: with Settings.nict_frames off, no NICT URL is fetched."""
    semeru = volcanoes.get("263300")
    assert semeru is not None
    source = FakeSource(_jma_responses())
    frames = await fetch_frames(source, semeru, nict=False)
    assert [frame.product for frame, _ in frames] == [FrameProduct.B13_IR, FrameProduct.DUST_RGB]
    assert not any("nict.go.jp" in call for call in source.calls)


async def test_fetch_frames_skips_black_night_tiles(volcanoes: VolcanoCatalogue) -> None:
    lewotobi = volcanoes.get("264180")
    assert lewotobi is not None
    tile = HIMAWARI / "nict_D531106_4d_550_20261009_192000_1_2.png"
    assert await fetch_frames(_nict_day_source(tile), lewotobi, areas=(), nict_level=4) == []


LIVE_RUN_ACTIVE = ("262000", "263300", "264230", "268010", "268030")
"""Anak Krakatau, Semeru, Ili Lewotolok, Dukono, Ibu: active in the first live run."""


def _night_jma_responses() -> dict[str, bytes]:
    responses = _jma_responses()
    responses[NICT_LATEST_URL] = (HIMAWARI / "nict_latest.json").read_bytes()
    return responses


async def test_one_frames_poll_fetches_each_url_once(volcanoes: VolcanoCatalogue) -> None:
    """The registry asks volcano by volcano; one area's slot list and images are shared.

    The first live run fetched the se3 slot list and each JPEG once per volcano (48 s tick).
    """
    responses = _night_jma_responses()
    source = FakeSource(responses)
    with timeutil.use_clock(timeutil.FixedClock(SAMPLED_AT)):
        for volcano_id in LIVE_RUN_ACTIVE:
            volcano = volcanoes.get(volcano_id)
            assert volcano is not None
            frames = await fetch_frames(source, volcano)
            assert [frame.product for frame, _ in frames] == [
                FrameProduct.B13_IR,
                FrameProduct.DUST_RGB,
            ]
            assert all(frame.volcano_id == volcano_id for frame, _ in frames)
    assert Counter(source.calls) == dict.fromkeys(responses, 1)


async def test_neighbouring_volcanoes_share_nict_tiles(volcanoes: VolcanoCatalogue) -> None:
    tile = HIMAWARI / "nict_D531106_4d_550_20261009_050000_1_2_daytime.png"
    source = _nict_day_source(tile)
    with timeutil.use_clock(timeutil.FixedClock(SAMPLED_AT)):
        for volcano_id in ("264180", "264230"):  # Lewotobi and Ili Lewotolok: both in tile 1_2
            volcano = volcanoes.get(volcano_id)
            assert volcano is not None
            frames = await fetch_frames(source, volcano, areas=(), nict_level=4)
            assert [frame.product for frame, _ in frames] == [FrameProduct.TRUE_COLOR]
    assert sorted(Counter(source.calls).values()) == [1, 1]


async def test_the_next_frames_poll_fetches_again(volcanoes: VolcanoCatalogue) -> None:
    semeru = volcanoes.get("263300")
    assert semeru is not None
    responses = _night_jma_responses()
    source = FakeSource(responses)
    clock = timeutil.FixedClock(SAMPLED_AT)
    with timeutil.use_clock(clock):
        await fetch_frames(source, semeru)
        clock.advance(timedelta(minutes=10))
        await fetch_frames(source, semeru)
    assert Counter(source.calls) == dict.fromkeys(responses, 2)


async def test_a_failed_download_is_tried_once_per_poll(volcanoes: VolcanoCatalogue) -> None:
    responses = _night_jma_responses()
    dust_url = next(url for url in responses if "_dst_" in url)
    del responses[dust_url]
    source = FakeSource(responses)
    with timeutil.use_clock(timeutil.FixedClock(SAMPLED_AT)):
        for volcano_id in ("263300", "264230"):
            volcano = volcanoes.get(volcano_id)
            assert volcano is not None
            frames = await fetch_frames(source, volcano)
            assert [frame.product for frame, _ in frames] == [FrameProduct.B13_IR]
    assert source.calls.count(dust_url) == 1


async def test_fetch_frames_raises_when_every_product_fails(volcanoes: VolcanoCatalogue) -> None:
    """An outage must reach the feed health, not read as a quiet empty success."""
    semeru = volcanoes.get("263300")
    assert semeru is not None
    with pytest.raises(FetchError, match="HTTP 404") as caught:
        await fetch_frames(FakeSource({}), semeru)
    assert caught.value.feed is FeedId.FRAMES


async def test_no_frame_at_night_outside_the_jma_areas_is_not_a_failure(
    volcanoes: VolcanoCatalogue,
) -> None:
    bagana = volcanoes.get("255020")  # east of se3 and south of jpn; 05:41 local solar time
    assert bagana is not None
    source = FakeSource({NICT_LATEST_URL: (HIMAWARI / "nict_latest.json").read_bytes()})
    assert await fetch_frames(source, bagana) == []


async def test_frame_captions_cite_the_source_and_say_it_was_cropped(
    volcanoes: VolcanoCatalogue,
) -> None:
    """JMA's Public Data License 1.0 asks for the source and a note that it was edited."""
    semeru, lewotobi = volcanoes.get("263300"), volcanoes.get("264180")
    assert semeru is not None
    assert lewotobi is not None
    jma = await fetch_frames(FakeSource(_night_jma_responses()), semeru)
    tile = HIMAWARI / "nict_D531106_4d_550_20261009_050000_1_2_daytime.png"
    nict = await fetch_frames(_nict_day_source(tile), lewotobi, areas=(), nict_level=4)
    captions = {frame.product: frame.caption for frame, _ in [*jma, *nict]}
    assert set(captions) == set(FrameProduct)
    for product, caption in captions.items():
        assert "cropped by TEPHRA" in caption, product
        assert caption.endswith(FRAME_CAPTION_SUFFIX), product
    assert "Source: JMA Meteorological Satellite Center" in captions[FrameProduct.B13_IR]
    assert "Source: JMA Meteorological Satellite Center" in captions[FrameProduct.DUST_RGB]
    assert "Source: NICT" in captions[FrameProduct.TRUE_COLOR]
    assert "non-commercial" in captions[FrameProduct.TRUE_COLOR]
