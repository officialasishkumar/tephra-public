"""Science module: segment planning, the numpy HSD reader and the split-window indicator.

Nothing here needs satpy or the network. HSD segments are synthesised byte for byte from
the HSD v1.3 block layout with a planted negative-BTD patch, so the reader, the resampling
and the indicator are exercised end to end.
"""

import bz2
import struct
from collections.abc import Mapping
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest
from PIL import Image
from shapely.geometry import Point, shape

from tephra.config import Settings
from tephra.feeds.base import FetchResult, build_url
from tephra.geo.units import destination_point
from tephra.models import BBox, BtdIndicator, FeedId, VaacCentre, Volcano
from tephra.science.btd import (
    HIMAWARI_CREDIT,
    INDICATOR_AREA_LABEL,
    STANDARD_CAVEATS,
    BtdSummary,
    CropGrid,
    HsdFormatError,
    analyse_btd,
    btd_caption,
    btd_key,
    cold_top_corrected_btd,
    compute_btd,
    crop_grid,
    decode_segment,
    render_png,
    run_btd,
    summarise,
)
from tephra.science.hsd_segments import (
    HIMAWARI_AHI_2KM,
    HSD_BUCKET_URL,
    HsdObject,
    find_latest_scan,
    listing_params,
    parse_listing,
    segment_for_line,
    segments_for_bbox,
)
from tephra.util.hashing import combine_hashes, sha256_bytes

FIXTURES = Path(__file__).parent / "fixtures"
LISTING_1800 = FIXTURES / "aws_himawari" / "list_AHI-L1b-FLDK_2026-10-09_1800.xml"
SLOT = datetime(2026, 10, 9, 18, 0, tzinfo=UTC)
SCANNED = datetime(2026, 10, 9, 18, 5, 4, tzinfo=UTC)
FETCHED = datetime(2026, 10, 9, 18, 14, 30, tzinfo=UTC)
SEMERU = Volcano(
    id="263300",
    name="Semeru",
    country="Indonesia",
    lat=-8.108,
    lon=112.92,
    summit_elev_m=3676,
    observatory="PVMBG",
    vaac=VaacCentre.DARWIN,
)


def _fetch_result(
    url: str, content: bytes, *, content_type: str = "application/xml"
) -> FetchResult:
    return FetchResult(
        feed=FeedId.HSD,
        url=url,
        status_code=200,
        content=content,
        content_type=content_type,
        fetched_at=FETCHED,
        sha256=sha256_bytes(content),
    )


# --- geostationary projection and segment choice ----------------------------------------


def test_sub_satellite_point_is_the_disk_centre():
    line, column = HIMAWARI_AHI_2KM.line_col(0.0, 140.7)
    assert float(line) == pytest.approx(2750.5, abs=1e-6)
    assert float(column) == pytest.approx(2750.5, abs=1e-6)


def test_far_side_of_the_earth_is_not_visible():
    line, column = HIMAWARI_AHI_2KM.line_col(0.0, -40.0)
    assert np.isnan(line)
    assert np.isnan(column)


def test_java_maps_to_segment_6_south_of_the_equator():
    line, column = HIMAWARI_AHI_2KM.line_col(-7.9, 112.9)
    # research/12 measured Semeru (8.11 S) at line 3186, column 1314 from real headers.
    assert 3150 < float(line) < 3210
    assert 1250 < float(column) < 1400
    assert segment_for_line(round(float(line))) == 6
    assert segments_for_bbox(BBox(west=112.8, south=-8.0, east=113.0, north=-7.8)) == [6]


def test_sakurajima_maps_to_segment_3():
    line, _ = HIMAWARI_AHI_2KM.line_col(31.6, 130.7)
    assert 1100 < float(line) < 1180
    assert segments_for_bbox(BBox(west=130.6, south=31.5, east=130.8, north=31.7)) == [3]


def test_whole_java_bali_region_needs_one_segment():
    assert segments_for_bbox(BBox(west=104.5, south=-9.8, east=117.5, north=-5.0)) == [6]


def test_box_across_the_equator_needs_two_segments():
    assert segments_for_bbox(BBox(west=126.0, south=-1.0, east=129.0, north=1.0)) == [5, 6]


@pytest.mark.parametrize(
    ("line", "segment"),
    [(1, 1), (550, 1), (551, 2), (2750, 5), (2751, 6), (5500, 10)],
)
def test_segment_boundaries_are_550_lines(line: int, segment: int):
    assert segment_for_line(line) == segment


# --- S3 listing -------------------------------------------------------------------------


def test_listing_params_floor_to_the_ten_minute_slot():
    params = listing_params(datetime(2026, 10, 9, 18, 7, 31, tzinfo=UTC))
    assert params == {"list-type": "2", "prefix": "AHI-L1b-FLDK/2026/10/09/1800/"}


def test_parse_listing_reads_every_full_disk_segment():
    objects = parse_listing(_fetch_result("listing", LISTING_1800.read_bytes()))
    assert len(objects) == 160
    assert {obj.band for obj in objects} == set(range(1, 17))
    assert {obj.segment for obj in objects} == set(range(1, 11))
    assert all(obj.scan_start == SLOT for obj in objects)
    b13_s06 = next(obj for obj in objects if obj.band == 13 and obj.segment == 6)
    assert b13_s06.url == HSD_BUCKET_URL + b13_s06.key
    assert b13_s06.key.endswith("HS_H09_20261009_1800_B13_FLDK_R20_S0610.DAT.bz2")
    assert b13_s06.size_bytes > 1_000_000


def test_parse_listing_rejects_non_xml():
    with pytest.raises(ValueError, match="not XML"):
        parse_listing(_fetch_result("listing", b"<html"))


def _empty_listing(prefix: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        f"<Name>noaa-himawari9</Name><Prefix>{prefix}</Prefix><KeyCount>0</KeyCount>"
        "<MaxKeys>1000</MaxKeys><IsTruncated>false</IsTruncated></ListBucketResult>"
    ).encode()


def _listing(objects: Mapping[str, bytes]) -> bytes:
    contents = "".join(
        f"<Contents><Key>{key}</Key><Size>{len(blob)}</Size></Contents>"
        for key, blob in objects.items()
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        f"<KeyCount>{len(objects)}</KeyCount><IsTruncated>false</IsTruncated>{contents}"
        "</ListBucketResult>"
    ).encode()


class _BucketSource:
    """Answers listing GETs by prefix and object GETs by URL, like the anonymous bucket."""

    def __init__(self, listings: Mapping[str, bytes], objects: Mapping[str, bytes]) -> None:
        self.listings = dict(listings)
        self.objects = dict(objects)
        self.requested: list[str] = []

    async def fetch(
        self, url: str, *, feed: FeedId, params: Mapping[str, str] | None = None
    ) -> FetchResult:
        full = build_url(url, params)
        self.requested.append(full)
        if params is not None:
            prefix = params["prefix"]
            return _fetch_result(full, self.listings.get(prefix, _empty_listing(prefix)))
        return _fetch_result(full, self.objects[url], content_type="binary/octet-stream")

    async def aclose(self) -> None:
        return None


async def test_find_latest_scan_walks_back_to_the_newest_complete_slot():
    source = _BucketSource({"AHI-L1b-FLDK/2026/10/09/1800/": LISTING_1800.read_bytes()}, {})
    found = await find_latest_scan(source, FETCHED, bands=(13, 15), segments=[6])
    assert found is not None
    slot, objects = found
    assert slot == SLOT
    assert [(obj.band, obj.segment) for obj in objects] == [(13, 6), (15, 6)]
    assert len(source.requested) == 2
    assert "1810" in source.requested[0]
    assert "1800" in source.requested[1]


async def test_find_latest_scan_gives_up_after_the_lookback():
    source = _BucketSource({}, {})
    found = await find_latest_scan(source, FETCHED, (13, 15), [6], lookback_slots=3)
    assert found is None
    assert len(source.requested) == 3


# --- synthetic HSD segments -------------------------------------------------------------

_LIGHT, _PLANCK, _BOLTZMANN = 2.99792458e8, 6.62606957e-34, 1.3806488e-23
_WAVELENGTH_UM = {13: 10.4074, 14: 11.2080, 15: 12.3648}
_SLOPE = 0.001
# HSD v1.3 header block lengths; blocks 8 to 10 vary in real files and the reader walks them.
_BLOCK_LENGTHS = dict(enumerate((282, 50, 127, 139, 147, 259, 47, 40, 20, 40, 259), start=1))
_MJD_EPOCH = datetime(1858, 11, 17, tzinfo=UTC)


def _radiance(bt_k: npt.NDArray[np.float64], wavelength_um: float) -> npt.NDArray[np.float64]:
    """Planck radiance in W m-2 sr-1 um-1, the inverse of the reader's calibration."""
    lam = wavelength_um * 1e-6
    exponent = _PLANCK * _LIGHT / (_BOLTZMANN * lam * bt_k)
    return 2.0 * _PLANCK * _LIGHT**2 / (lam**5 * np.expm1(exponent)) * 1e-6


def _hsd_segment(
    band: int, bt_k: npt.NDArray[np.float64], *, first_line: int, coff: float, loff: float
) -> bytes:
    """One little-endian HSD v1.3 segment with identity block-5 correction (Tb = Te)."""
    lines, columns = bt_k.shape
    header = bytearray(sum(_BLOCK_LENGTHS.values()))
    starts: dict[int, int] = {}
    offset = 0
    for number, length in _BLOCK_LENGTHS.items():
        header[offset] = number
        struct.pack_into("<I" if number == 10 else "<H", header, offset + 1, length)
        starts[number] = offset
        offset += length
    b1, b2, b3, b5, b7 = (starts[n] for n in (1, 2, 3, 5, 7))
    struct.pack_into("<H", header, b1 + 3, 11)
    header[b1 + 5] = 0
    header[b1 + 6 : b1 + 16] = b"Himawari-9"
    mjd = (SCANNED - _MJD_EPOCH).total_seconds() / 86400.0
    struct.pack_into("<ddd", header, b1 + 46, mjd, mjd + 60 / 86400.0, mjd + 180 / 86400.0)
    struct.pack_into("<II", header, b1 + 70, len(header), 2 * lines * columns)
    struct.pack_into("<HHHB", header, b2 + 3, 16, columns, lines, 0)
    navigation = (140.7, 20466275, 20466275, coff, loff, 42164.0, 6378.137, 6356.7523)
    struct.pack_into("<dIIffddd", header, b3 + 3, *navigation)
    counts_to_radiance = (band, _WAVELENGTH_UM[band], 11, 65535, 65534, _SLOPE, 0.0)
    struct.pack_into("<HdHHHdd", header, b5 + 3, *counts_to_radiance)
    identity_correction = (0.0, 1.0, 0.0, 0.0, 1.0, 0.0, _LIGHT, _PLANCK, _BOLTZMANN)
    struct.pack_into("<9d", header, b5 + 35, *identity_correction)
    struct.pack_into("<BBH", header, b7 + 3, 10, 6, first_line)
    counts = np.rint(_radiance(bt_k, _WAVELENGTH_UM[band]) / _SLOPE).astype("<u2")
    return bytes(header) + counts.tobytes()


class _Scene:
    """A 300-line x 400-column patch of segment 6 with Semeru near its middle.

    COFF is shifted so the vent falls on column 200: the reader navigates with whatever
    block 3 says, so a small image exercises the same code as a 5500-column segment.
    """

    lines, columns = 300, 400

    def __init__(self) -> None:
        line0, col0 = HIMAWARI_AHI_2KM.line_col(SEMERU.lat, SEMERU.lon)
        self.coff = 2750.5 - float(col0) + 200.0
        self.loff = 2750.5
        self.first_line = round(float(line0)) - 150
        self.vent_row, self.vent_col = 150, 199
        self.b13 = np.full((self.lines, self.columns), 290.0)
        self.b15 = np.full((self.lines, self.columns), 287.0)

    def plant_ash(self, rows: slice, cols: slice, btd_k: float = -2.0) -> None:
        self.b15[rows, cols] = self.b13[rows, cols] - btd_k

    def blobs(self) -> list[tuple[HsdObject, bytes]]:
        out = []
        for band, field in ((13, self.b13), (15, self.b15)):
            raw = _hsd_segment(
                band, field, first_line=self.first_line, coff=self.coff, loff=self.loff
            )
            blob = bz2.compress(raw)
            key = (
                f"AHI-L1b-FLDK/2026/10/09/1800/"
                f"HS_H09_20261009_1800_B{band:02d}_FLDK_R20_S0610.DAT.bz2"
            )
            obj = HsdObject(
                key=key,
                url=HSD_BUCKET_URL + key,
                band=band,
                segment=6,
                size_bytes=len(blob),
                scan_start=SLOT,
            )
            out.append((obj, blob))
        return out


def test_reader_recovers_brightness_temperature_and_header():
    scene = _Scene()
    scene.b13[0, :5] = 250.0
    raw = _hsd_segment(13, scene.b13, first_line=scene.first_line, coff=scene.coff, loff=2750.5)
    segment = decode_segment(raw)
    assert segment.band == 13
    assert segment.segment == 6
    assert segment.first_line == scene.first_line
    assert segment.bt_k.shape == (scene.lines, scene.columns)
    assert float(segment.bt_k[0, 0]) == pytest.approx(250.0, abs=0.05)
    assert float(segment.bt_k[100, 100]) == pytest.approx(290.0, abs=0.05)
    assert abs((segment.observation_start - SCANNED).total_seconds()) < 1.0
    assert segment.projection.sub_lon_deg == pytest.approx(140.7)


def test_reader_masks_error_and_outside_scan_counts():
    scene = _Scene()
    raw = bytearray(
        _hsd_segment(13, scene.b13, first_line=scene.first_line, coff=scene.coff, loff=2750.5)
    )
    data_start = sum(_BLOCK_LENGTHS.values())
    struct.pack_into("<HH", raw, data_start, 65535, 65534)
    bt = decode_segment(bytes(raw)).bt_k
    assert np.isnan(bt[0, 0])
    assert np.isnan(bt[0, 1])
    assert np.isfinite(bt[0, 2])


def test_reader_rejects_layouts_it_does_not_handle():
    scene = _Scene()
    raw = bytearray(
        _hsd_segment(13, scene.b13, first_line=scene.first_line, coff=scene.coff, loff=2750.5)
    )
    compressed_flag = _BLOCK_LENGTHS[1] + 9
    raw[compressed_flag] = 1
    with pytest.raises(HsdFormatError, match="compression"):
        decode_segment(bytes(raw))
    with pytest.raises(HsdFormatError):
        decode_segment(b"\x01\x00")


def test_compute_btd_finds_a_planted_ash_patch_south_east_of_the_vent():
    scene = _Scene()
    rows = slice(scene.vent_row + 10, scene.vent_row + 17)
    cols = slice(scene.vent_col + 15, scene.vent_col + 22)
    scene.plant_ash(rows, cols)
    segments = scene.blobs()
    listing_url = build_url(HSD_BUCKET_URL, listing_params(SLOT))

    analysis = analyse_btd(
        segments,
        SEMERU,
        band_pair="B13-B15",
        half_width_km=100.0,
        threshold_k=-0.5,
        listing_url=listing_url,
        fetched_at=FETCHED,
    )
    result = analysis.result

    assert result.indicator is BtdIndicator.NEGATIVE_BTD_PRESENT
    assert result.negative_pixel_count >= 20
    assert result.min_btd_k == pytest.approx(-2.0, abs=0.05)
    assert result.median_btd_k == pytest.approx(3.0, abs=0.05)
    assert result.min_bt_k == pytest.approx(290.0, abs=0.05)
    assert result.negative_centroid_bearing_deg is not None
    assert 95.0 < result.negative_centroid_bearing_deg < 160.0
    assert result.negative_centroid_distance_km is not None
    assert 25.0 < result.negative_centroid_distance_km < 70.0
    assert result.nearest_negative_km is not None
    assert result.nearest_negative_km < result.negative_centroid_distance_km

    digests = [sha256_bytes(blob) for _, blob in segments]
    assert result.provenance.source_id == "BTD:263300:20261009T1800Z"
    assert result.provenance.feed is FeedId.HSD
    assert result.provenance.url == listing_url
    assert result.provenance.sha256 == combine_hashes(digests)
    assert result.provenance.issued_at is not None
    assert abs((result.provenance.issued_at - SCANNED).total_seconds()) < 1.0
    assert result.segment_sha256 == digests
    assert result.image_key == "btd/263300_20261009T1800Z.png"
    assert result.caveats[0].endswith("An indicator, not detection.")
    assert result.caveats[-1] == HIMAWARI_CREDIT

    assert analysis.indicator_label == INDICATOR_AREA_LABEL
    assert analysis.indicator_area is not None
    area = shape(analysis.indicator_area.model_dump())
    centroid_lat, centroid_lon = destination_point(
        SEMERU.lat,
        SEMERU.lon,
        result.negative_centroid_bearing_deg,
        result.negative_centroid_distance_km,
    )
    assert area.contains(Point(centroid_lon, centroid_lat))
    assert not area.contains(Point(SEMERU.lon, SEMERU.lat))

    image = Image.open(BytesIO(analysis.png))
    assert image.mode == "RGBA"
    assert image.size == _grid_for(100.0).shape[::-1]
    pixels = np.asarray(image)
    bluish = (pixels[..., 2].astype(int) - pixels[..., 0] > 80) & (pixels[..., 3] > 0)
    assert bluish.any()


def test_compute_btd_is_silent_on_a_moist_background_and_says_so():
    scene = _Scene()
    result, png = compute_btd(
        scene.blobs(),
        SEMERU,
        band_pair="B13-B15",
        half_width_km=100.0,
        threshold_k=-0.5,
        listing_url="listing",
        fetched_at=FETCHED,
    )
    assert result.indicator is BtdIndicator.SILENT
    assert result.negative_pixel_count == 0
    assert result.negative_centroid_bearing_deg is None
    assert "does not mean no ash" in result.caveats[0]
    assert any("moist air" in line for line in result.caveats)
    assert png.startswith(b"\x89PNG")


def test_compute_btd_needs_both_bands():
    scene = _Scene()
    only_b13 = scene.blobs()[:1]
    with pytest.raises(ValueError, match="needs segments of bands"):
        compute_btd(
            only_b13,
            SEMERU,
            band_pair="B13-B15",
            half_width_km=100.0,
            threshold_k=-0.5,
            listing_url="listing",
            fetched_at=FETCHED,
        )


async def test_run_btd_finds_downloads_and_computes_the_newest_scan():
    scene = _Scene()
    scene.plant_ash(slice(140, 147), slice(180, 187))
    segments = scene.blobs()
    source = _BucketSource(
        {"AHI-L1b-FLDK/2026/10/09/1800/": _listing({obj.key: blob for obj, blob in segments})},
        {obj.url: blob for obj, blob in segments},
    )
    settings = Settings(_env_file=None, btd_half_width_km=100.0)

    outcome = await run_btd(source, SEMERU, FETCHED, settings)

    assert outcome is not None
    result, png = outcome
    assert result.scan_start == SLOT
    assert result.indicator is BtdIndicator.NEGATIVE_BTD_PRESENT
    assert result.provenance.fetched_at == FETCHED
    assert result.provenance.url == build_url(HSD_BUCKET_URL, listing_params(SLOT))
    assert png.startswith(b"\x89PNG")


async def test_run_btd_returns_none_without_a_complete_scan():
    settings = Settings(_env_file=None)
    assert await run_btd(_BucketSource({}, {}), SEMERU, FETCHED, settings) is None


# --- indicator logic on synthetic grids (no HSD at all) ---------------------------------


def _grid_for(half_width_km: float) -> CropGrid:
    return crop_grid(SEMERU.lat, SEMERU.lon, half_width_km)


def _cell(grid: CropGrid, lat: float, lon: float) -> tuple[int, int]:
    return int(np.argmin(np.abs(grid.lats - lat))), int(np.argmin(np.abs(grid.lons - lon)))


def _fields(
    grid: CropGrid, t1: float = 290.0, btd: float = 3.0
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    first = np.full(grid.shape, t1)
    return first, first - btd


def _summarise(
    grid: CropGrid,
    first: npt.NDArray[np.float64],
    second: npt.NDArray[np.float64],
    half_width_km: float = 100.0,
) -> BtdSummary:
    return summarise(
        grid,
        first,
        second,
        vent_lat=SEMERU.lat,
        vent_lon=SEMERU.lon,
        half_width_km=half_width_km,
        threshold_k=-0.5,
    )


def test_crop_grid_is_centred_and_mercator_regular():
    grid = _grid_for(100.0)
    assert grid.shape == (100, 100)
    assert grid.bbox.contains(SEMERU.lat, SEMERU.lon)
    assert (grid.bbox.west + grid.bbox.east) / 2 == pytest.approx(SEMERU.lon)
    assert (grid.bbox.south + grid.bbox.north) / 2 == pytest.approx(SEMERU.lat)
    assert np.all(np.diff(grid.lats) < 0)
    assert np.all(np.diff(grid.lons) > 0)
    merc = np.log(np.tan(np.pi / 4 + np.radians(grid.lats) / 2))
    assert np.allclose(np.diff(merc), np.diff(merc)[0])
    assert grid.bbox.corners_lonlat()[0] == (grid.bbox.west, grid.bbox.north)


def test_background_without_negative_pixels_is_silent():
    grid = _grid_for(100.0)
    first, second = _fields(grid)
    summary = _summarise(grid, first, second)
    assert summary.indicator is BtdIndicator.SILENT
    assert summary.negative_pixel_count == 0
    assert summary.median_btd_k == pytest.approx(3.0)
    assert summary.indicator_area is None


def test_a_single_negative_pixel_is_noise():
    grid = _grid_for(100.0)
    first, second = _fields(grid)
    row, col = _cell(grid, SEMERU.lat - 0.1, SEMERU.lon + 0.1)
    second[row, col] = first[row, col] + 2.0
    summary = _summarise(grid, first, second)
    assert summary.negative_pixel_count == 1
    assert summary.indicator is BtdIndicator.SILENT
    assert summary.indicator_area is None


def test_cluster_near_the_vent_gives_bearing_distance_and_polygon():
    grid = _grid_for(100.0)
    first, second = _fields(grid)
    lat, lon = destination_point(SEMERU.lat, SEMERU.lon, 45.0, 40.0)
    row, col = _cell(grid, lat, lon)
    second[row - 1 : row + 2, col - 1 : col + 2] = first[row - 1 : row + 2, col - 1 : col + 2] + 1.5
    summary = _summarise(grid, first, second)
    assert summary.indicator is BtdIndicator.NEGATIVE_BTD_PRESENT
    assert summary.cluster_count == 1
    assert summary.indicator_pixel_count == 9
    assert summary.centroid_bearing_deg == pytest.approx(45.0, abs=5.0)
    assert summary.centroid_distance_km == pytest.approx(40.0, abs=3.0)
    assert summary.min_btd_k == pytest.approx(-1.5)

    assert summary.indicator_area is not None
    area = shape(summary.indicator_area.model_dump())
    lat2d, lon2d = grid.mesh()
    for r in range(row - 1, row + 2):
        for c in range(col - 1, col + 2):
            assert area.contains(Point(lon2d[r, c], lat2d[r, c]))
    assert not area.contains(Point(SEMERU.lon, SEMERU.lat))
    assert area.area < 25 * grid.pixel_deg**2


def test_cluster_far_from_the_vent_does_not_count():
    grid = _grid_for(250.0)
    first, second = _fields(grid)
    lat, lon = destination_point(SEMERU.lat, SEMERU.lon, 90.0, 200.0)
    row, col = _cell(grid, lat, lon)
    second[row - 1 : row + 2, col - 1 : col + 2] += 5.0
    summary = _summarise(grid, first, second, half_width_km=250.0)
    assert summary.negative_pixel_count == 9
    assert summary.indicator is BtdIndicator.SILENT
    assert summary.centroid_bearing_deg is None


def test_cold_top_correction_suppresses_negatives_on_deep_cloud():
    corrected = cold_top_corrected_btd(np.array([205.0, 280.0]), np.array([206.5, 281.5]))
    assert corrected[0] == pytest.approx(0.5)
    assert corrected[1] == pytest.approx(-1.5)


def test_deep_cloud_over_the_crop_is_inconclusive_not_silent():
    grid = _grid_for(100.0)
    first, second = _fields(grid, t1=220.0)
    summary = _summarise(grid, first, second)
    assert summary.indicator is BtdIndicator.INCONCLUSIVE
    assert summary.deep_cloud_fraction == pytest.approx(1.0)


def test_missing_data_is_inconclusive():
    grid = _grid_for(100.0)
    first, second = _fields(grid)
    first[: int(grid.shape[0] * 0.7), :] = np.nan
    summary = _summarise(grid, first, second)
    assert summary.indicator is BtdIndicator.INCONCLUSIVE
    assert summary.valid_fraction < 0.5


def test_no_valid_pixels_is_an_error():
    grid = _grid_for(100.0)
    first = np.full(grid.shape, np.nan)
    with pytest.raises(ValueError, match="no usable"):
        _summarise(grid, first, first)


def test_png_is_transparent_where_there_is_no_data_and_marks_the_vent():
    grid = _grid_for(100.0)
    btd = np.full(grid.shape, 3.0)
    btd[0, 0] = np.nan
    btd[10, 10] = -3.0
    image = Image.open(BytesIO(render_png(grid, btd, vent_lat=SEMERU.lat, vent_lon=SEMERU.lon)))
    pixels = np.asarray(image)
    assert image.size == (grid.shape[1], grid.shape[0])
    assert pixels[0, 0, 3] == 0
    assert tuple(pixels[10, 10, :3]) == (33, 102, 172)
    row, col = _cell(grid, SEMERU.lat, SEMERU.lon)
    assert tuple(pixels[row, col]) == (0, 0, 0, 255)


# --- labels -----------------------------------------------------------------------------


def test_btd_key_matches_the_blob_pattern():
    assert btd_key("263300", SLOT) == "btd/263300_20261009T1800Z.png"


def test_caption_never_reads_silence_as_no_ash():
    scene = _Scene()
    result, _ = compute_btd(
        scene.blobs(),
        SEMERU,
        band_pair="B13-B15",
        half_width_km=100.0,
        threshold_k=-0.5,
        listing_url="listing",
        fetched_at=FETCHED,
    )
    caption = btd_caption(result)
    assert "scanned 18:05:04Z" in caption
    assert "does not mean no ash" in caption
    assert caption.endswith(HIMAWARI_CREDIT)
    assert set(STANDARD_CAVEATS) <= set(result.caveats)
