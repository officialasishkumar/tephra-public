"""Text feed parsers and fetchers, tested against the real responses in tests/fixtures/.

Fixture fetch times and URLs are the ones recorded in tests/fixtures/README.md. HTTP is faked
by a small in-test Source; nothing here touches the network.
"""

import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tephra.feeds.base import FetchError, FetchResult, build_url
from tephra.feeds.sigmet import (
    SIGMET_PARAMS,
    SIGMET_URL,
    fetch_sigmets,
    find_dm_points,
    parse_dm_point,
    parse_sigmets,
)
from tephra.feeds.taf import (
    METAR_URL,
    TAF_URL,
    assess_alternate,
    fetch_tafs,
    parse_metars,
    parse_tafs,
    station_params,
)
from tephra.feeds.vaac import (
    DARWIN_BACKUP_LIST_URL,
    DARWIN_BULLETIN_URLS,
    TOKYO_LIST_URL,
    fetch_vaas,
    parse_vaa,
    parse_vaa_text,
    parse_vaac_list,
)
from tephra.feeds.vona import VONA_LIST_URL, fetch_vonas, parse_vona_list, parse_vona_page
from tephra.models import (
    AviationColor,
    FeedId,
    Sigmet,
    Taf,
    TafPeriod,
    VaacAdvisory,
    VaacCentre,
)
from tephra.util.hashing import sha256_bytes
from tephra.util.timeutil import FixedClock, use_clock

FIXTURES = Path(__file__).parent / "fixtures"
JMA_VAAC = "https://ds.data.jma.go.jp/svd/vaac/data/"
MAGMA_DETAIL = {
    22880: "https://magma.esdm.go.id/v1/vona/22880?signature=9678e5287b728bc1210c62090abbbab47c3fa7e66f72a155954ab56c74cc2d03",
    22881: "https://magma.esdm.go.id/v1/vona/22881?signature=9b1dd1019782c6c6dc83817dc6f9538e08b294a61f3ec41481dbcb4a462b58df",
    22889: "https://magma.esdm.go.id/v1/vona/22889?signature=5412ce61fc8ab19051a3a1682ceb3ec3cfcf9aca8457455414c1cadda2305bad",
}
MAGMA_FIXTURE = {
    22880: "magma/vona_22880_semeru_ash.html",
    22881: "magma/vona_22881_ibu_ash.html",
    22889: "magma/vona_22889_semeru_no_ash.html",
}

# Darwin's tgftp bulletin as quoted in research/05 section 3.7 (fvau02.adrm, 2026-10-10).
FVAU02_SEMERU = """FVAU02 ADRM 091820
VA ADVISORY
DTG: 20261009/1820Z
VAAC: DARWIN
VOLCANO: SEMERU 263300
ADVISORY NR: 2026/1157
INFO SOURCE: HIMAWARI-9, CVGHM
ERUPTION DETAILS: VA TO FL150 OBS AT 09/1800Z, MOV E
OBS VA CLD: SFC/FL150 S0803 E11253 - S0754 E11316 - S0807
        E11324 - S0820 E11318 - S0811 E11253 MOV E 10KT
FCST VA CLD +6 HR: 10/0000Z SFC/FL150 S0803 E11253 - S0753
        E11317 - S0807 E11324 - S0821 E11318 - S0811 E11253
RMK: VA IDENTIFIABLE ON CURRENT SATELLITE IMAGERY MOVING
        EAST. DISCRETE EMISSIONS ARE ONGOING. AREA IS PARTIALLY
        OBSCURED BY MET CLOUD. HEIGHT AND MOVEMENT BASED ON
        SATELLITE IMAGERY, GROUND REPORTS AND MODEL GUIDANCE.
NXT ADVISORY: NO LATER THAN 20261010/0020Z=
"""

# Abridged from the Tokyo backup handover notice described in research/01 and research/07.
NOTICE_TEXT = """FVAU01 ADRM 231216
VA ADVISORY
DTG: 20260923/1216Z
VAAC: TOKYO
VOLCANO: NOTICE 999999
PSN: N1000 E11300
SOURCE ELEV: 9999M AMSL
ADVISORY NR: 2026/3
RMK: VAAC TOKYO HAS ASSUMED RESPONSIBILITY FOR ISSUING VAA TO THE VAAC DARWIN AREA OF
RESPONSIBILITY NORTH OF LATITUDE 20S
"""


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=UTC)


def make_result(
    content: bytes,
    *,
    feed: FeedId,
    url: str,
    fetched_at: datetime,
    content_type: str = "text/html; charset=UTF-8",
) -> FetchResult:
    return FetchResult(
        feed=feed,
        url=url,
        status_code=200,
        content=content,
        content_type=content_type,
        fetched_at=fetched_at,
        sha256=sha256_bytes(content),
    )


def fixture_result(
    name: str, *, feed: FeedId, url: str, fetched_at: datetime, content_type: str
) -> FetchResult:
    content = (FIXTURES / name).read_bytes()
    return make_result(
        content, feed=feed, url=url, fetched_at=fetched_at, content_type=content_type
    )


class FakeSource:
    """Answers GETs from a URL -> bytes map; unknown URLs fail like a dead link."""

    def __init__(self, responses: Mapping[str, bytes], *, default: bytes | None = None) -> None:
        self.responses = dict(responses)
        self.default = default
        self.requests: list[tuple[str, FeedId]] = []

    async def fetch(
        self, url: str, *, feed: FeedId, params: Mapping[str, str] | None = None
    ) -> FetchResult:
        full_url = build_url(url, params)
        self.requests.append((full_url, feed))
        content = self.responses.get(full_url, self.default)
        if content is None:
            raise FetchError(full_url, feed, "HTTP 404")
        return make_result(content, feed=feed, url=full_url, fetched_at=utc(2026, 10, 9, 19, 40))

    async def aclose(self) -> None:
        return None

    @property
    def urls(self) -> list[str]:
        return [url for url, _ in self.requests]


# --- SIGMET -----------------------------------------------------------------------------

SIGMET_FETCHED = utc(2026, 10, 9, 19, 36, 48)


def sigmet_result(name: str = "isigmet/isigmet_va.json") -> FetchResult:
    return fixture_result(
        name,
        feed=FeedId.SIGMET,
        url=build_url(SIGMET_URL, SIGMET_PARAMS),
        fetched_at=SIGMET_FETCHED,
        content_type="application/json; charset=utf-8",
    )


def sigmet_records() -> list[dict[str, Any]]:
    return json.loads((FIXTURES / "isigmet/isigmet_va.json").read_bytes())


def json_result(records: list[dict[str, Any]]) -> FetchResult:
    return make_result(
        json.dumps(records).encode(),
        feed=FeedId.SIGMET,
        url=build_url(SIGMET_URL, SIGMET_PARAMS),
        fetched_at=SIGMET_FETCHED,
        content_type="application/json",
    )


def by_series(sigmets: list[Sigmet], fir: str, series: str) -> Sigmet:
    return next(s for s in sigmets if s.fir_id == fir and s.series_id == series)


def test_degree_minute_coordinates_are_not_decimals() -> None:
    assert parse_dm_point("S0806", "E11255") == pytest.approx((-(8 + 6 / 60), 112 + 55 / 60))
    assert parse_dm_point("N0129", "E12738") == pytest.approx((1 + 29 / 60, 127 + 38 / 60))
    assert parse_dm_point("N5147", "W178047") is None  # malformed Anchorage PSN on BoM
    points = find_dm_points("N0222\nE12839 - N0202 E12902 - N0059E03209")
    expected = [(2 + 22 / 60, 128 + 39 / 60), (2 + 2 / 60, 129 + 2 / 60), (59 / 60, 32 + 9 / 60)]
    assert len(points) == len(expected)
    for found, wanted in zip(points, expected, strict=True):
        assert found == pytest.approx(wanted)


def test_parse_sigmets_reads_every_va_record() -> None:
    sigmets = parse_sigmets(sigmet_result())
    assert len(sigmets) == 11
    assert {s.fir_id for s in sigmets} >= {"WAAF", "WIIF", "MHTG", "SEFG", "SKED"}


def test_semeru_sigmet_fields() -> None:
    semeru = by_series(parse_sigmets(sigmet_result()), "WAAF", "12")
    assert semeru.volcano_name == "SEMERU"
    assert semeru.volcano_lat == pytest.approx(-(8 + 6 / 60))
    assert semeru.volcano_lon == pytest.approx(112 + 55 / 60)
    assert semeru.issuing_office == "WAAA"
    assert semeru.fir_name == "WAAF UJUNG PANDANG"
    assert semeru.observed is True
    assert semeru.observed_at == utc(2026, 10, 9, 18, 0)
    assert semeru.valid_from == utc(2026, 10, 9, 18, 20)
    assert semeru.valid_to == utc(2026, 10, 10, 0, 20)
    assert (semeru.base_ft, semeru.top_ft) == (0, 15000)
    assert semeru.movement_toward_deg == 90.0
    assert semeru.movement_speed_kt == 10.0
    assert semeru.stationary is False
    assert semeru.intensity_change == "NC"
    assert semeru.cancelled is False
    assert semeru.polygon is not None
    ring = semeru.polygon.coordinates[0]
    assert ring[0] == (112.883, -8.05)
    assert ring[0] == ring[-1]
    assert semeru.raw_text.startswith("WVID21 WAAA 091820")
    provenance = semeru.provenance
    assert provenance.source_id == "SIGMET:WAAF:12:20261009T1820Z"
    assert provenance.issued_at == utc(2026, 10, 9, 18, 20)
    assert provenance.valid_from == semeru.valid_from
    assert provenance.valid_to == semeru.valid_to
    assert provenance.feed is FeedId.SIGMET
    assert provenance.fetched_at == SIGMET_FETCHED


def test_volcano_names_with_and_without_prefix() -> None:
    sigmets = parse_sigmets(sigmet_result())
    assert by_series(sigmets, "SKED", "A3").volcano_name == "VOLCAN PURACE"
    assert by_series(sigmets, "MHTG", "1").volcano_name == "MASAYA"
    assert by_series(sigmets, "WAAF", "13").volcano_name == "IBU"
    assert by_series(sigmets, "WAAF", "13").intensity_change == "INTSF"
    assert by_series(sigmets, "WIIF", "07").observed_at == utc(2026, 10, 9, 15, 50)


def test_forecast_series_is_its_own_record() -> None:
    sigmets = parse_sigmets(sigmet_result())
    observed = by_series(sigmets, "SEFG", "3")
    forecast = by_series(sigmets, "SEFG", "3F")
    assert observed.observed is True
    assert forecast.observed is False
    assert forecast.observed_at is None
    assert observed.polygon != forecast.polygon
    assert forecast.provenance.source_id == "SIGMET:SEFG:3F:20261009T1654Z"
    assert observed.raw_text == forecast.raw_text


def test_duplicate_records_are_dropped() -> None:
    records = sigmet_records()
    assert len(parse_sigmets(json_result([*records, records[5]]))) == len(records)


def test_non_va_records_are_ignored() -> None:
    sigmets = parse_sigmets(sigmet_result("isigmet/isigmet_all.json"))
    assert len(sigmets) == 11


def test_raw_text_fallback_reads_degrees_and_minutes() -> None:
    semeru = next(r for r in sigmet_records() if r["seriesId"] == "12")
    stripped = {**semeru, "coords": None, "top": None, "base": None, "dir": None, "spd": None}
    sigmet = parse_sigmets(json_result([stripped]))[0]
    assert sigmet.polygon is not None
    ring = sigmet.polygon.coordinates[0]
    assert ring[0] == pytest.approx((112 + 53 / 60, -(8 + 3 / 60)))
    assert len(ring) == 6
    assert (sigmet.base_ft, sigmet.top_ft) == (0, 15000)
    assert sigmet.movement_toward_deg == 90.0


def test_raw_text_fallback_uses_the_forecast_part_for_f_series() -> None:
    masaya = next(r for r in sigmet_records() if r["seriesId"] == "1F")
    sigmet = parse_sigmets(json_result([{**masaya, "coords": []}]))[0]
    assert sigmet.polygon is not None
    assert sigmet.polygon.coordinates[0][0] == pytest.approx((-(86 + 10 / 60), 12 + 1 / 60))


def test_cancelled_sigmet() -> None:
    semeru = next(r for r in sigmet_records() if r["seriesId"] == "12")
    cancel = {
        **semeru,
        "seriesId": "14",
        "qualifier": None,
        "coords": [],
        "rawSigmet": "WVID21 WAAA 091900\nWAAF SIGMET 14 VALID 091900/100020 WAAA-\n"
        "WAAF UJUNG PANDANG FIR CNL SIGMET 12 091820/100020=",
    }
    sigmet = parse_sigmets(json_result([cancel]))[0]
    assert sigmet.cancelled is True
    assert sigmet.polygon is None
    assert sigmet.is_valid(utc(2026, 10, 9, 20, 0)) is False


def test_stationary_from_json_when_text_says_nothing() -> None:
    semeru = next(r for r in sigmet_records() if r["seriesId"] == "12")
    raw = semeru["rawSigmet"].replace(" MOV E 10KT", "")
    sigmet = parse_sigmets(json_result([{**semeru, "rawSigmet": raw, "dir": "-", "spd": "0"}]))[0]
    assert sigmet.stationary is True
    assert sigmet.movement_toward_deg is None


async def test_fetch_sigmets_drops_expired_records() -> None:
    content = (FIXTURES / "isigmet/isigmet_va.json").read_bytes()
    source = FakeSource({build_url(SIGMET_URL, SIGMET_PARAMS): content})
    with use_clock(FixedClock(utc(2026, 10, 10, 0, 50))):
        sigmets = await fetch_sigmets(source)
    assert source.requests == [(build_url(SIGMET_URL, SIGMET_PARAMS), FeedId.SIGMET)]
    assert {s.series_id for s in sigmets} == {"A5", "A5F", "13"}


# --- VONA -------------------------------------------------------------------------------


def vona_list_result() -> FetchResult:
    return fixture_result(
        "magma/vona_list.html",
        feed=FeedId.VONA,
        url=VONA_LIST_URL,
        fetched_at=utc(2026, 10, 9, 19, 37, 17),
        content_type="text/html; charset=UTF-8",
    )


def vona_page_result(magma_id: int) -> FetchResult:
    return fixture_result(
        MAGMA_FIXTURE[magma_id],
        feed=FeedId.VONA,
        url=MAGMA_DETAIL[magma_id],
        fetched_at=utc(2026, 10, 9, 19, 37, 35),
        content_type="text/html; charset=UTF-8",
    )


def test_parse_vona_list() -> None:
    items = parse_vona_list(vona_list_result())
    assert len(items) == 15
    first = items[0]
    assert first.magma_id == 22889
    assert first.url == MAGMA_DETAIL[22889]
    assert first.volcano_name == "Semeru"
    assert first.issued_at == utc(2026, 10, 9, 18, 0)
    assert first.color_code is AviationColor.ORANGE
    assert first.summary is not None
    assert "Ash-cloud is not observed" in first.summary
    krakatau = next(item for item in items if item.magma_id == 22885)
    assert krakatau.volcano_name == "Anak Krakatau"
    assert krakatau.issued_at == utc(2026, 10, 9, 11, 44)
    assert [item.magma_id for item in items] == list(range(22889, 22874, -1))


def test_vona_with_ash() -> None:
    items = {item.magma_id: item for item in parse_vona_list(vona_list_result())}
    vona = parse_vona_page(vona_page_result(22880), items[22880])
    assert vona.volcano_name == "Semeru"
    assert vona.volcano_code == "SMR"
    assert vona.notice_number == "2026SMR1913"
    assert vona.magma_id == 22880
    assert vona.issued_at == utc(2026, 10, 8, 21, 3)
    assert vona.color_code is AviationColor.ORANGE
    assert vona.ash_observed is True
    assert vona.cloud_top_m == 4376
    assert vona.cloud_top_ft == 14357  # not MAGMA's 14003 (metres x 3.2)
    assert vona.movement_toward_deg == 0.0
    assert vona.movement_text == "Ash cloud moving to north"
    assert vona.eruption_at == utc(2026, 10, 8, 21, 3)
    assert vona.source_text == "ground observer"
    assert vona.remarks is not None
    assert vona.remarks.startswith("Eruption recorded on seismogram")
    assert vona.provenance.source_id == "VONA:SEMERU:20261008T2103Z"
    assert vona.provenance.issued_at == vona.issued_at
    assert "Issued: 20261008/2103Z" in vona.raw_text
    assert "pvmbg" not in vona.raw_text.lower()


def test_vona_without_ash() -> None:
    vona = parse_vona_page(vona_page_result(22889))
    assert vona.magma_id == 22889
    assert vona.issued_at == utc(2026, 10, 9, 18, 0)
    assert vona.ash_observed is False
    assert vona.cloud_top_ft is None
    assert vona.cloud_top_m is None
    assert vona.movement_toward_deg is None
    assert vona.eruption_at == utc(2026, 10, 9, 18, 0)
    assert vona.source_text == "Semeru Volcano Observatory"


def test_vona_ibu() -> None:
    vona = parse_vona_page(vona_page_result(22881))
    assert vona.volcano_name == "Ibu"
    assert vona.volcano_code == "IBU"
    assert vona.cloud_top_m == 1725
    assert vona.cloud_top_ft == 5659
    assert vona.movement_toward_deg == 90.0
    assert vona.eruption_at == utc(2026, 10, 9, 1, 37)


def test_vona_page_without_table_is_rejected() -> None:
    result = make_result(
        b"<html><body>Maintenance</body></html>",
        feed=FeedId.VONA,
        url=MAGMA_DETAIL[22880],
        fetched_at=utc(2026, 10, 9, 19, 40),
    )
    with pytest.raises(ValueError, match="VONA"):
        parse_vona_page(result)


async def test_fetch_vonas_fetches_only_new_signed_pages() -> None:
    responses = {VONA_LIST_URL: (FIXTURES / "magma/vona_list.html").read_bytes()}
    for magma_id in (22880, 22889):
        responses[MAGMA_DETAIL[magma_id]] = (FIXTURES / MAGMA_FIXTURE[magma_id]).read_bytes()
    source = FakeSource(responses)
    vonas = await fetch_vonas(
        source, since=utc(2026, 10, 8, 21, 0), known_urls=frozenset({MAGMA_DETAIL[22881]})
    )
    assert [vona.magma_id for vona in vonas] == [22889, 22880]
    requested = {int(m.group(1)) for url in source.urls if (m := re.search(r"/(\d+)\?", url))}
    assert requested == {22880, *range(22882, 22890)}
    assert source.urls[0] == VONA_LIST_URL
    assert all(feed is FeedId.VONA for _, feed in source.requests)


async def test_fetch_vonas_pages_with_page_param() -> None:
    listing = (FIXTURES / "magma/vona_list.html").read_bytes()
    page_two = build_url(VONA_LIST_URL, {"page": "2"})
    source = FakeSource({VONA_LIST_URL: listing, page_two: listing})
    known = frozenset(item.url for item in parse_vona_list(vona_list_result()))
    vonas = await fetch_vonas(source, since=utc(2026, 10, 1), known_urls=known, max_pages=2)
    assert vonas == []
    assert source.urls == [VONA_LIST_URL, page_two]


# --- VAA --------------------------------------------------------------------------------


def jma_text_result(name: str, feed: FeedId = FeedId.VAAC_TOKYO) -> FetchResult:
    return fixture_result(
        name,
        feed=feed,
        url=f"{JMA_VAAC}TextData/2026/{Path(name).name}",
        fetched_at=utc(2026, 10, 9, 19, 38),
        content_type="text/html",
    )


def text_result(text: str, url: str = DARWIN_BULLETIN_URLS[1]) -> FetchResult:
    return make_result(
        text.encode(),
        feed=FeedId.VAAC_DARWIN,
        url=url,
        fetched_at=utc(2026, 10, 9, 19, 40),
        content_type="text/plain; charset=utf-8",
    )


def bom_recent_block(vaac_heading: str) -> list[str]:
    page = (FIXTURES / "darwin_vaac/bom_volc_ash_recent.html").read_text(encoding="utf-8")
    match = re.search(rf"<h3>{vaac_heading}</h3><pre>(.*?)</pre>", page, re.S)
    assert match is not None
    chunks = re.split(r"(?m)^Received .*$", match.group(1))
    return [chunk for chunk in chunks[1:] if chunk.strip()]


def advisory_by_nr(advisories: list[VaacAdvisory], nr: str) -> VaacAdvisory:
    return next(advisory for advisory in advisories if advisory.advisory_nr == nr)


def test_parse_tokyo_list() -> None:
    result = fixture_result(
        "tokyo_vaac/vaac_list.html",
        feed=FeedId.VAAC_TOKYO,
        url=TOKYO_LIST_URL,
        fetched_at=utc(2026, 10, 9, 19, 38),
        content_type="text/html",
    )
    items = parse_vaac_list(result, VaacCentre.TOKYO)
    assert len(items) == 158
    first = items[0]
    assert first.vaac is VaacCentre.TOKYO
    assert first.volcano_name == "TAAL"
    assert first.area == "PHILIPPINES"
    assert first.advisory_nr == "2026/24"
    assert first.issued_at == utc(2026, 10, 8, 17, 50)
    assert first.url == f"{JMA_VAAC}TextData/2026/20261008_27307000_0024_Text.html"
    assert items[2].volcano_name == "SAKURAJIMA (AIRA CALDERA)"


def test_parse_darwin_backup_list() -> None:
    result = fixture_result(
        "darwin_vaac/vaac_darwin_list.html",
        feed=FeedId.VAAC_DARWIN,
        url=DARWIN_BACKUP_LIST_URL,
        fetched_at=utc(2026, 10, 9, 19, 38),
        content_type="text/html",
    )
    items = parse_vaac_list(result, VaacCentre.DARWIN)
    assert len(items) == 34
    assert sum(item.volcano_name == "NOTICE" for item in items) == 19
    assert items[1].advisory_nr == "2026/1081"
    assert items[1].issued_at == utc(2026, 9, 23, 14, 19)


def test_tokyo_advisory_with_polygons() -> None:
    vaa = parse_vaa(jma_text_result("tokyo_vaac/20261008_27307000_0023_Text.html"))
    assert vaa is not None
    assert vaa.vaac is VaacCentre.TOKYO
    assert vaa.advisory_nr == "2026/23"
    assert vaa.issued_at == utc(2026, 10, 8, 15, 0)
    assert (vaa.volcano_name, vaa.volcano_number) == ("TAAL", "273070")
    assert (vaa.volcano_lat, vaa.volcano_lon) == pytest.approx((14.0, 121.0))
    assert vaa.area == "PHILIPPINES"
    assert vaa.summit_elev_ft == 1020
    assert vaa.info_source == "HIMAWARI-9"
    assert vaa.aviation_color is None
    assert vaa.observation is not None
    assert vaa.observation.valid_at == utc(2026, 10, 8, 14, 20)
    assert vaa.observation.estimated is False
    [layer] = vaa.observation.layers
    assert (layer.base_ft, layer.top_ft) == (0, 15000)
    assert layer.movement_toward_deg == 225.0
    assert layer.movement_speed_kt == 15.0
    assert layer.polygon is not None
    ring = layer.polygon.coordinates[0]
    assert len(ring) == 5  # four vertices, closed by the parser
    assert ring[0] == pytest.approx((120 + 14 / 60, 13 + 40 / 60))
    assert ring[3] == pytest.approx((120 + 23 / 60, 13 + 30 / 60))  # wrapped onto a new line
    assert [step.offset_h for step in vaa.forecasts] == [6, 12, 18]
    six, twelve, eighteen = vaa.forecasts
    assert six.valid_at == utc(2026, 10, 8, 20, 20)
    assert six.layers[0].top_ft == 16000
    assert twelve.valid_at == utc(2026, 10, 9, 2, 20)
    assert twelve.layers[0].top_ft == 18000
    assert eighteen.no_ash_expected is True
    assert eighteen.layers == []
    assert eighteen.valid_at == utc(2026, 10, 9, 8, 20)
    assert vaa.remarks == "SOME PART OF VA OBSCURED BY MET CLOUD."
    assert vaa.next_advisory_at == utc(2026, 10, 8, 18, 0)
    assert vaa.final is False
    assert vaa.raw_text.startswith("FVFE01 RJTD 081500\nVA ADVISORY")
    assert vaa.raw_text.endswith("NXT ADVISORY: 20261008/1800Z=")
    provenance = vaa.provenance
    assert provenance.source_id == "VAA:TOKYO:273070:2026/23"
    assert provenance.issued_at == vaa.issued_at
    assert provenance.valid_to == utc(2026, 10, 8, 19, 0)


def test_tokyo_advisory_not_identifiable_and_final() -> None:
    vaa = parse_vaa(jma_text_result("tokyo_vaac/20261008_28208001_0279_Text.html"))
    assert vaa is not None
    assert vaa.volcano_name == "SAKURAJIMA (AIRA CALDERA)"
    assert vaa.observation is not None
    assert vaa.observation.not_identifiable is True
    assert vaa.observation.layers == []  # "WIND FL180 040/1KT" is wind, not ash
    assert all(step.no_ash_expected for step in vaa.forecasts)
    assert vaa.final is True
    assert vaa.next_advisory_at is None
    assert vaa.next_advisory_text == "NO FURTHER ADVISORIES"
    assert vaa.provenance.valid_to == utc(2026, 10, 8, 12, 50)


def test_darwin_backup_text_joins_wrapped_remarks() -> None:
    vaa = parse_vaa(
        jma_text_result("darwin_vaac/20260923_26803000_1081_Text.html", FeedId.VAAC_DARWIN)
    )
    assert vaa is not None
    assert vaa.vaac is VaacCentre.DARWIN
    assert vaa.provenance.source_id == "VAA:DARWIN:268030:2026/1081"
    assert vaa.observation is not None
    assert vaa.observation.valid_at == utc(2026, 9, 23, 9, 50)
    assert vaa.observation.layers[0].polygon is not None
    assert len(vaa.observation.layers[0].polygon.coordinates[0]) == 6
    assert vaa.forecasts[-1].valid_at == utc(2026, 9, 24, 3, 50)
    assert vaa.remarks is not None
    assert "REGULAR GROUND REPORTS INDICATE INTERMITTENT" in vaa.remarks
    assert vaa.remarks.endswith("VA AREA IS AN ESTIMATED AREA.")


def test_darwin_plain_text_with_indented_continuations() -> None:
    chunks = bom_recent_block("Darwin VAAC")
    advisories = [parse_vaa_text(chunk, text_result(chunk)) for chunk in chunks]
    assert len(advisories) == 32
    parsed = [advisory for advisory in advisories if advisory is not None]
    assert all(advisory.vaac is VaacCentre.DARWIN for advisory in parsed)

    semeru = advisory_by_nr(parsed, "2026/1157")
    assert semeru.observation is not None
    [layer] = semeru.observation.layers
    assert layer.top_ft == 15000
    assert layer.movement_toward_deg == 90.0
    assert layer.polygon is not None
    ring = layer.polygon.coordinates[0]
    assert len(ring) == 6
    assert ring[0] == pytest.approx((112 + 53 / 60, -(8 + 3 / 60)))
    assert ring[2] == pytest.approx((113 + 24 / 60, -(8 + 7 / 60)))  # lon on the next line
    assert [step.offset_h for step in semeru.forecasts] == [6, 12, 18]
    assert semeru.next_advisory_at == utc(2026, 10, 10, 0, 20)
    assert semeru.remarks is not None
    assert "AREA IS PARTIALLY OBSCURED BY MET CLOUD" in semeru.remarks

    krakatau = advisory_by_nr(parsed, "2026/225")
    twelve = krakatau.forecasts[1]
    assert twelve.no_ash_expected is True
    assert twelve.valid_at == utc(2026, 10, 10, 3, 50)
    assert twelve.layers == []

    manam = advisory_by_nr(parsed, "2026/51")
    assert manam.observation is not None
    assert manam.observation.estimated is True
    assert manam.observation.not_identifiable is True
    assert manam.observation.layers == []  # "WIND SFC/FL070 160/05KT" is not an ash layer
    assert manam.final is True

    taal = advisory_by_nr(parsed, "2026/29")
    assert all(step.not_available for step in taal.forecasts)
    assert taal.observation is not None
    assert taal.observation.layers == []


def test_bom_html_fragment_with_split_coordinates() -> None:
    path = FIXTURES / "darwin_vaac/bom_process_volcanic-ash-darwin.json"
    payload = json.loads(path.read_bytes())
    texts = {entry["name"]: entry["text"] for entry in payload["advisories"].values()}
    vaa = parse_vaa(text_result(texts["DUKONO 268010"]))
    assert vaa is not None
    assert vaa.advisory_nr == "2026/855"
    assert vaa.observation is not None
    polygon = vaa.observation.layers[0].polygon
    assert polygon is not None
    ring = polygon.coordinates[0]
    assert ring[2] == pytest.approx((128 + 39 / 60, 2 + 22 / 60))  # "N0222<br />E12839"
    assert vaa.next_advisory_at == utc(2026, 10, 9, 21, 50)


def test_format_variants() -> None:
    page = (FIXTURES / "tokyo_vaac/20261008_28208001_0278_Text.html").read_text(encoding="utf-8")
    old_cloud = (
        "OBS VA CLD: SFC/FL080 N3135 E13039 - N3140 E13037 - N3144 E13043 - <BR>"
        "N3141 E13044 MOV N 10KT"
    )
    two_layers = (
        "OBS VA CLD: SFC/FL100 N3135 E13039 - N3140 E13037 - N3144 E13043 MOV N 10KT "
        "FL100/FL200 N3130 E13030 - N3140 E13020 - N3150 E13030 MOV E 20KT"
    )
    edits = {
        "+6 HR": "+6HR",
        "+12 HR": "+12HR",
        "NXT ADVISORY: 20261008/1200Z": "NXT ADVISORY: WILL BE ISSUED BY 20261008/1200Z",
        "<BR>ERUPTION DETAILS": "<BR>AVIATION COLOUR CODE: RED<BR>ERUPTION DETAILS",
        old_cloud: two_layers,
    }
    for old, new in edits.items():
        assert old in page
        page = page.replace(old, new)
    result = make_result(
        page.encode(),
        feed=FeedId.VAAC_TOKYO,
        url=f"{JMA_VAAC}TextData/2026/20261008_28208001_0278_Text.html",
        fetched_at=utc(2026, 10, 9, 19, 38),
    )
    vaa = parse_vaa(result)
    assert vaa is not None
    assert [step.offset_h for step in vaa.forecasts] == [6, 12, 18]
    assert vaa.next_advisory_at == utc(2026, 10, 8, 12, 0)
    assert vaa.aviation_color is AviationColor.RED
    assert vaa.observation is not None
    lower, upper = vaa.observation.layers
    assert (lower.base_ft, lower.top_ft, lower.movement_toward_deg) == (0, 10000, 0.0)
    assert (upper.base_ft, upper.top_ft) == (10000, 20000)
    assert (upper.movement_toward_deg, upper.movement_speed_kt) == (90.0, 20.0)


def test_notice_pseudo_advisory_is_not_an_advisory() -> None:
    assert parse_vaa_text(NOTICE_TEXT, text_result(NOTICE_TEXT)) is None


def test_other_vaacs_and_non_vaa_text_are_rejected() -> None:
    buenos_aires = bom_recent_block("Buenos Aires VAAC")[0]
    with pytest.raises(ValueError, match="outside"):
        parse_vaa_text(buenos_aires, text_result(buenos_aires))
    with pytest.raises(ValueError, match="DTG"):
        parse_vaa(text_result("Not Found"))


async def test_fetch_tokyo_vaas() -> None:
    responses = {TOKYO_LIST_URL: (FIXTURES / "tokyo_vaac/vaac_list.html").read_bytes()}
    for name in ("27307000_0023", "28208001_0279", "28208001_0278"):
        file_name = f"20261008_{name}_Text.html"
        url = f"{JMA_VAAC}TextData/2026/{file_name}"
        responses[url] = (FIXTURES / "tokyo_vaac" / file_name).read_bytes()
    source = FakeSource(responses)
    since = utc(2026, 10, 8, 5, 0)
    known = frozenset({f"{JMA_VAAC}TextData/2026/20261008_27307000_0024_Text.html"})
    advisories = await fetch_vaas(source, FeedId.VAAC_TOKYO, since=since, known_urls=known)
    assert [a.provenance.source_id for a in advisories] == [
        "VAA:TOKYO:273070:2026/23",
        "VAA:TOKYO:282080:2026/279",
        "VAA:TOKYO:282080:2026/278",
    ]
    listing = make_result(
        responses[TOKYO_LIST_URL], feed=FeedId.VAAC_TOKYO, url=TOKYO_LIST_URL, fetched_at=since
    )
    wanted = [
        item.url
        for item in parse_vaac_list(listing, VaacCentre.TOKYO)
        if item.issued_at >= since and item.url not in known
    ]
    assert source.urls == [TOKYO_LIST_URL, *wanted]
    assert all(feed is FeedId.VAAC_TOKYO for _, feed in source.requests)


async def test_fetch_darwin_vaas_from_bulletins_and_backup_list() -> None:
    responses = {
        DARWIN_BULLETIN_URLS[1]: FVAU02_SEMERU.encode(),
        DARWIN_BACKUP_LIST_URL: (FIXTURES / "darwin_vaac/vaac_darwin_list.html").read_bytes(),
    }
    for file_name in ("20260923_26801000_0788_Text.html", "20260923_26803000_1081_Text.html"):
        url = f"{JMA_VAAC}TextData/2026/{file_name}"
        responses[url] = (FIXTURES / "darwin_vaac" / file_name).read_bytes()
    source = FakeSource(responses)
    advisories = await fetch_vaas(source, FeedId.VAAC_DARWIN, since=utc(2026, 9, 23))
    assert [a.provenance.source_id for a in advisories] == [
        "VAA:DARWIN:263300:2026/1157",
        "VAA:DARWIN:268010:2026/788",
        "VAA:DARWIN:268030:2026/1081",
    ]
    assert source.urls[:4] == list(DARWIN_BULLETIN_URLS)
    assert f"{JMA_VAAC}TextData/2026/20260923_99999902_0003_Text.html" not in source.urls
    semeru = advisories[0]
    assert semeru.observation is not None
    assert semeru.observation.valid_at == semeru.issued_at  # tgftp copy has no OBS VA DTG
    assert semeru.provenance.url == DARWIN_BULLETIN_URLS[1]


async def test_fetch_darwin_vaas_raises_when_every_source_fails() -> None:
    with pytest.raises(FetchError):
        await fetch_vaas(FakeSource({}), FeedId.VAAC_DARWIN, since=utc(2026, 9, 23))


async def test_fetch_vaas_rejects_other_feeds() -> None:
    with pytest.raises(ValueError, match="not a VAAC feed"):
        await fetch_vaas(FakeSource({}), FeedId.SIGMET, since=utc(2026, 9, 23))


# --- TAF and METAR ----------------------------------------------------------------------

WX_FETCHED = utc(2026, 10, 9, 19, 40)


def taf_result() -> FetchResult:
    return fixture_result(
        "wx/taf.json",
        feed=FeedId.TAF,
        url=build_url(TAF_URL, station_params(["WARR"])),
        fetched_at=WX_FETCHED,
        content_type="application/json",
    )


def metar_result() -> FetchResult:
    return fixture_result(
        "wx/metar.json",
        feed=FeedId.METAR,
        url=build_url(METAR_URL, station_params(["WARR"])),
        fetched_at=WX_FETCHED,
        content_type="application/json",
    )


def tafs_by_icao() -> dict[str, Taf]:
    return {taf.icao: taf for taf in parse_tafs(taf_result())}


def test_station_params_are_sorted_and_unique() -> None:
    assert station_params(["WARR", "WADD", "WARR"]) == {"ids": "WADD,WARR", "format": "json"}
    assert list(station_params(["WARR"])) == ["ids", "format"]


def test_parse_tafs() -> None:
    tafs = tafs_by_icao()
    assert sorted(tafs) == ["RJFF", "RJFK", "RPLL", "WAAA", "WADD", "WARR", "WIII", "WSSS"]
    warr = tafs["WARR"]
    assert warr.issued_at == utc(2026, 10, 9, 17, 0)
    assert (warr.valid_from, warr.valid_to) == (utc(2026, 10, 9, 18), utc(2026, 10, 10, 18))
    assert warr.provenance.source_id == "TAF:WARR:20261009T1700Z"
    assert warr.raw_text.startswith("TAF WARR 091700Z")
    base, becmg = warr.periods
    assert base.change is None
    assert base.visibility_m == 4000  # AWC's 2.49 SM
    assert base.weather == ["HZ"]
    assert (base.wind_from_deg, base.wind_speed_kt) == (260.0, 5.0)
    assert base.ceiling_ft is None
    assert becmg.change == "BECMG"
    assert becmg.visibility_m == 9999
    assert becmg.weather == []  # NSW is not weather


def test_taf_period_type_traps() -> None:
    rjfk = tafs_by_icao()["RJFK"]
    base, tempo_wind, tempo_rain = rjfk.periods
    assert base.ceiling_ft == 3000
    assert tempo_wind.change == "TEMPO"
    assert tempo_wind.visibility_m is None  # "" means the group does not change it
    assert tempo_rain.visibility_m == 3000  # 1.86 SM
    assert tempo_rain.weather == ["SHRA", "BR"]
    assert tempo_rain.wind_from_deg is None
    rpll = tafs_by_icao()["RPLL"]
    assert rpll.periods[0].wind_from_deg is None  # VRB
    assert rpll.periods[0].wind_speed_kt == 3.0


def test_parse_metars() -> None:
    metars = {metar.icao: metar for metar in parse_metars(metar_result())}
    assert len(metars) == 8
    warr = metars["WARR"]
    assert warr.observed_at == utc(2026, 10, 9, 19, 30)
    assert warr.visibility_m == 5000
    assert warr.weather == ["HZ"]
    assert warr.flight_category == "MVFR"
    assert warr.provenance.source_id == "METAR:WARR:20261009T1930Z"
    assert metars["RJFF"].weather == []
    assert metars["RJFF"].visibility_m == 9999
    assert metars["RJFK"].observed_at == utc(2026, 10, 9, 12, 0)
    assert metars["WSSS"].ceiling_ft == 30000


def test_empty_awc_answer_is_no_reports() -> None:
    empty = make_result(b"", feed=FeedId.TAF, url=TAF_URL, fetched_at=WX_FETCHED)
    assert parse_tafs(empty) == []
    assert parse_metars(empty) == []


async def test_fetch_tafs_in_chunks_of_twenty() -> None:
    icaos = [f"WA{chr(65 + i // 26)}{chr(65 + i % 26)}" for i in range(45)]
    source = FakeSource({}, default=b"[]")
    assert await fetch_tafs(source, [*reversed(icaos), icaos[0]]) == []
    expected = [sorted(icaos)[i : i + 20] for i in (0, 20, 40)]
    assert source.urls == [build_url(TAF_URL, station_params(chunk)) for chunk in expected]
    assert all(feed is FeedId.TAF for _, feed in source.requests)
    assert await fetch_tafs(source, []) == []


def test_assess_alternate_with_real_tafs() -> None:
    tafs = tafs_by_icao()
    ok = assess_alternate(tafs["WARR"], utc(2026, 10, 9, 21, 0))
    assert ok.ok is True
    assert ok.reasons == []
    assert ok.icao == "WARR"
    assert ok.taf_source_id == "TAF:WARR:20261009T1700Z"
    assert ok.checked_for == utc(2026, 10, 9, 21, 0)
    late = assess_alternate(tafs["WARR"], utc(2026, 10, 10, 19, 0))
    assert late.ok is False
    assert late.reasons == ["TAF NOT VALID AT ETA"]
    assert assess_alternate(tafs["RJFK"], utc(2026, 10, 10, 1, 0)).ok is True  # 3000 m is minima


def test_assess_alternate_without_taf() -> None:
    check = assess_alternate(None, utc(2026, 10, 9, 21, 0), icao="WADD")
    assert (check.icao, check.ok, check.reasons) == ("WADD", False, ["NO TAF"])
    assert check.taf_source_id is None


def synthetic_taf(periods: list[TafPeriod]) -> Taf:
    result = make_result(b"[]", feed=FeedId.TAF, url=TAF_URL, fetched_at=WX_FETCHED)
    issued = utc(2026, 10, 10, 0, 0)
    return Taf(
        provenance=result.provenance("TAF:WXYZ:20261010T0000Z", issued_at=issued),
        icao="WXYZ",
        issued_at=issued,
        valid_from=issued,
        valid_to=utc(2026, 10, 11, 0, 0),
        periods=periods,
        raw_text="TAF WXYZ 100000Z 1000/1024 ...",
    )


def test_assess_alternate_screens_every_group_near_eta() -> None:
    taf = synthetic_taf(
        [
            TafPeriod(valid_from=utc(2026, 10, 10), valid_to=utc(2026, 10, 11), visibility_m=9999),
            TafPeriod(valid_from=utc(2026, 10, 10, 6), valid_to=utc(2026, 10, 10, 10),
                      change="TEMPO", weather=["TSRA"]),
            TafPeriod(valid_from=utc(2026, 10, 10, 8), valid_to=utc(2026, 10, 10, 12),
                      change="PROB30 TEMPO", weather=["VA"], visibility_m=1500, ceiling_ft=800),
            TafPeriod(valid_from=utc(2026, 10, 10, 20), valid_to=utc(2026, 10, 10, 22),
                      change="TEMPO", weather=["VA"]),
        ]
    )  # fmt: skip
    storm_only = assess_alternate(taf, utc(2026, 10, 10, 6, 30))
    assert storm_only.ok is True
    assert storm_only.reasons == ["TS IN TEMPO GROUP"]
    ash = assess_alternate(taf, utc(2026, 10, 10, 7, 30))
    assert ash.ok is False
    assert ash.reasons == [
        "VA IN PROB30 TEMPO GROUP",
        "VIS 1500 M BELOW 3000 M IN PROB30 TEMPO GROUP",
        "CEILING 800 FT BELOW 1000 FT IN PROB30 TEMPO GROUP",
        "TS IN TEMPO GROUP",
    ]
    clear = assess_alternate(taf, utc(2026, 10, 10, 16, 0))
    assert (clear.ok, clear.reasons) == (True, [])
