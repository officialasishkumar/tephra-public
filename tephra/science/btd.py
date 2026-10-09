"""Split-window brightness-temperature difference (BTD) around one volcano.

Method
------
Silicate ash absorbs more strongly at 12 um than at 10 to 11 um, so over a semi-transparent
ash cloud BT(10.4 or 11.2 um) minus BT(12.4 um) turns negative, while ice, liquid water and
water vapour push it positive (the "reverse absorption" or split-window test, Prata 1989).
VAACs have long used it alongside pattern analysis (Tupper et al. 2004). Here:

1. Decode the two Himawari-9 bands (B13 or B14, and B15) from their HSD v1.3 segments
   with a small numpy reader: header blocks 1, 2, 3, 5 and 7, counts to radiance, inverse
   Planck at the band's central wavelength, then the block-5 correction to brightness
   temperature. If a file is in a layout this reader does not handle, satpy's ``ahi_hsd``
   reader is tried instead (optional extra ``[science]``); if that is missing too,
   :class:`ScienceUnavailable` is raised.
2. Resample (nearest neighbour) onto a crop centred on the summit. Columns are evenly
   spaced in longitude and rows evenly spaced in Web Mercator y, because MapLibre stretches
   an image source linearly in Mercator between its corners: with this grid the PNG lands
   on the map exactly where the pixels were observed.
3. Add the Darwin VAAC cold-top correction, (230 K - T) / 12.5 where the first band is
   colder than 230 K, which suppresses false negatives on deep convective tops.
4. Within ``half_width_km`` of the summit, report the minimum, 5th percentile and median
   (the background) of the difference and the fraction of pixels below the threshold.
5. Indicator pixels are below-threshold pixels in 8-connected clusters of at least three
   pixels, where the cluster reaches within 150 km of the vent. Their centroid gives a
   bearing and distance from the summit, and the convex hull of each cluster, buffered by
   one pixel, gives an indicator polygon.
6. NEGATIVE_BTD_PRESENT when indicator pixels exist; INCONCLUSIVE when under half of the
   crop has data or over half of it is colder than 233 K (deep cloud hides what is under
   it); SILENT otherwise.

Limits
------
Repeated to the dispatcher and to Gemini in ``BtdResult.caveats``.

* No water-vapour correction is applied (Yu, Rose and Prata 2002). In moist tropical air
  the background is +3 to +6 K and ash can stay positive: Indonesia is the worst case, and
  the method stayed silent on real Semeru and Ruang cases (research/12).
* Ice-coated ash, and opaque fresh eruption columns, show little or no negative signal.
* Very thin ash falls into the noise; small or low eruptions fall below 2 km pixels.
* Cold cloud tops, surface temperature inversions and mineral dust give false alarms.

This is an indicator, never detection. A SILENT or INCONCLUSIVE result never means "no
ash" and may never narrow the hazard; a negative cluster may only widen it or raise the
urgency. Output images are derived from Himawari-9 data (JMA, distributed by NOAA) and are
labelled as processed by TEPHRA; raw HSD files are never re-served.
"""

import asyncio
import logging
import math
import struct
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Final, Literal

import numpy as np
import numpy.typing as npt
from PIL import Image
from shapely import MultiPoint, MultiPolygon, Polygon, unary_union
from shapely.geometry.base import BaseGeometry

from tephra.config import Settings
from tephra.feeds.base import Source, build_url
from tephra.geo.units import EARTH_RADIUS_KM, haversine_km, initial_bearing_deg
from tephra.models import (
    BBox,
    BtdIndicator,
    BtdResult,
    FeedId,
    GeoMultiPolygon,
    GeoPolygon,
    Position,
    Provenance,
    Volcano,
    make_source_id,
)
from tephra.science.hsd_segments import (
    HSD_BUCKET_URL,
    GeosProjection,
    HsdObject,
    decompress,
    fetch_segments,
    find_latest_scan,
    listing_params,
    segments_for_bbox,
    write_decompressed,
)
from tephra.util import timeutil
from tephra.util.hashing import combine_hashes, sha256_bytes

__all__ = [
    "BAND_PAIRS",
    "HIMAWARI_CREDIT",
    "INDICATOR_AREA_LABEL",
    "STANDARD_CAVEATS",
    "BandPair",
    "BtdAnalysis",
    "BtdSummary",
    "CropGrid",
    "DecodedSegment",
    "HsdFormatError",
    "ScienceUnavailable",
    "analyse_btd",
    "band_numbers",
    "btd_caption",
    "btd_key",
    "cold_top_corrected_btd",
    "compute_btd",
    "crop_grid",
    "decode_segment",
    "render_png",
    "run_btd",
    "sample_segments",
    "summarise",
]

log = logging.getLogger(__name__)

BandPair = Literal["B13-B15", "B14-B15"]
BAND_PAIRS: Final[dict[str, tuple[int, int]]] = {"B13-B15": (13, 15), "B14-B15": (14, 15)}

GRID_STEP_KM: Final = 2.0
"""Crop grid spacing, matching the 2 km sub-satellite resolution of the IR bands."""
NEAR_VENT_KM: Final = 150.0
MIN_CLUSTER_PX: Final = 3
COLD_TOP_REFERENCE_K: Final = 230.0
COLD_TOP_SCALE_K: Final = 12.5
DEEP_CLOUD_K: Final = 233.0
MIN_VALID_FRACTION: Final = 0.5
MAX_DEEP_CLOUD_FRACTION: Final = 0.5
MOIST_BACKGROUND_K: Final = 2.0
PNG_SCALE_K: Final = (-3.0, 5.0)
"""Fixed colour scale so frames are comparable: blue at -3 K, neutral at 0, orange at +5."""

HIMAWARI_CREDIT: Final = (
    "Himawari-9 data: JMA, distributed by NOAA (NODD / AWS Open Data); "
    "processed by TEPHRA, not original JMA data"
)
INDICATOR_AREA_LABEL: Final = (
    "Split-window BTD indicator (negative-BTD pixels near the vent): "
    "not detection and not a hazard boundary"
)
STANDARD_CAVEATS: Final[tuple[str, ...]] = (
    "Indicator only, not detection: a negative split-window difference suggests silicate "
    "ash; it may widen the hazard but never narrow it.",
    "No water-vapour correction is applied: in moist tropical air the difference stays "
    "positive and can mask ash completely.",
    "Ice-coated ash and opaque fresh eruption columns show little or no negative "
    "difference, and very thin ash is lost in the noise.",
    "Cold cloud tops, surface inversions and mineral dust can produce spurious negative "
    "differences; a cold-top correction is added below 230 K.",
    "2 km pixels: small or low eruptions often fall below the resolution.",
)

_HSD_BLOCK_COUNT: Final = 11
_FIRST_IR_BAND: Final = 7
_MJD_EPOCH: Final = datetime(1858, 11, 17, tzinfo=UTC)
_KM_PER_DEG_LAT: Final = 111.32
_MAX_MERCATOR_LAT: Final = 85.0
_WEB_MERCATOR_RADIUS_M: Final = 6378137.0
_SATPY_RADIUS_OF_INFLUENCE_M: Final = 5000.0
_ASH_BLUE: Final = np.array([33.0, 102.0, 172.0])
_NEUTRAL: Final = np.array([247.0, 247.0, 247.0])
_MOIST_ORANGE: Final = np.array([179.0, 88.0, 6.0])
_OVERLAY_ALPHA: Final = 210
_VENT_ARM_PX: Final = 4

FloatArray = npt.NDArray[np.floating[Any]]
IndexArray = npt.NDArray[np.intp]
Cluster = tuple[IndexArray, IndexArray]


class ScienceUnavailable(RuntimeError):
    """Neither the numpy HSD reader nor satpy could turn the segments into temperatures."""


class HsdFormatError(ValueError):
    """The bytes are a valid file but not in the HSD layout the numpy reader handles."""


@dataclass(frozen=True, slots=True, eq=False)
class CropGrid:
    """Pixel centres of the output crop; rows run north to south, columns west to east."""

    bbox: BBox
    lats: npt.NDArray[np.float64]
    lons: npt.NDArray[np.float64]

    @property
    def shape(self) -> tuple[int, int]:
        return self.lats.size, self.lons.size

    @property
    def pixel_deg(self) -> float:
        """Largest cell side in degrees (rows are unevenly spaced in latitude)."""
        lon_step = (self.bbox.east - self.bbox.west) / self.lons.size
        lat_step = float(np.max(np.abs(np.diff(self.lats)))) if self.lats.size > 1 else 0.0
        return max(lon_step, lat_step)

    def mesh(self) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
        lat2d, lon2d = np.meshgrid(self.lats, self.lons, indexing="ij")
        return lat2d, lon2d


@dataclass(frozen=True, slots=True, eq=False)
class DecodedSegment:
    """One calibrated HSD segment: brightness temperature per (line, column), NaN if bad."""

    band: int
    segment: int
    first_line: int
    projection: GeosProjection
    observation_start: datetime
    observation_end: datetime
    bt_k: npt.NDArray[np.float32]


@dataclass(frozen=True, slots=True, eq=False)
class BtdSummary:
    """Statistics over the disc of radius ``half_width_km`` around the summit."""

    pixel_count: int
    negative_pixel_count: int
    negative_fraction: float
    min_btd_k: float
    p05_btd_k: float
    median_btd_k: float
    min_bt_k: float
    valid_fraction: float
    deep_cloud_fraction: float
    cluster_count: int
    indicator_pixel_count: int
    nearest_negative_km: float | None
    centroid_bearing_deg: float | None
    centroid_distance_km: float | None
    indicator: BtdIndicator
    indicator_area: GeoPolygon | GeoMultiPolygon | None
    btd_k: FloatArray


@dataclass(frozen=True, slots=True, eq=False)
class BtdAnalysis:
    """Everything one run produces; ``compute_btd`` returns only the stored parts."""

    result: BtdResult
    png: bytes
    indicator_area: GeoPolygon | GeoMultiPolygon | None
    indicator_label: str = INDICATOR_AREA_LABEL


@dataclass(frozen=True, slots=True, eq=False)
class _BandFields:
    first_bt_k: FloatArray
    second_bt_k: FloatArray
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class _IrCalibration:
    wavelength_um: float
    slope: float
    intercept: float
    error_count: int
    outside_count: int
    c0: float
    c1: float
    c2: float
    light_speed: float
    planck: float
    boltzmann: float

    def brightness_temperature(self, counts: npt.NDArray[np.uint16]) -> npt.NDArray[np.float32]:
        radiance = counts.astype(np.float64) * self.slope + self.intercept  # W m-2 sr-1 um-1
        wavelength_m = self.wavelength_um * 1e-6
        spectral = radiance * 1e6  # per metre of wavelength, as the Planck function wants
        valid = (counts != self.error_count) & (counts != self.outside_count) & (radiance > 0)
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            effective = (self.planck * self.light_speed / (self.boltzmann * wavelength_m)) / np.log(
                2.0 * self.planck * self.light_speed**2 / (wavelength_m**5 * spectral) + 1.0
            )
            bt = self.c0 + self.c1 * effective + self.c2 * effective**2
        return np.where(valid, bt, np.nan).astype(np.float32)


# --- public helpers ---------------------------------------------------------------------


def band_numbers(band_pair: BandPair) -> tuple[int, int]:
    """``"B13-B15"`` -> ``(13, 15)``: the first band minus the second."""
    return BAND_PAIRS[band_pair]


def btd_key(volcano_id: str, scan_start: datetime) -> str:
    return f"btd/{volcano_id}_{timeutil.compact(scan_start)}.png"


def crop_grid(
    lat: float, lon: float, half_width_km: float, *, step_km: float = GRID_STEP_KM
) -> CropGrid:
    """Square crop of side ``2 * half_width_km`` centred on (lat, lon)."""
    if half_width_km <= 0 or step_km <= 0:
        raise ValueError("crop half width and step must be positive")
    dlat = half_width_km / _KM_PER_DEG_LAT
    dlon = half_width_km / (_KM_PER_DEG_LAT * math.cos(math.radians(lat)))
    bbox = BBox(
        west=lon - dlon,
        south=max(lat - dlat, -_MAX_MERCATOR_LAT),
        east=lon + dlon,
        north=min(lat + dlat, _MAX_MERCATOR_LAT),
    )
    size = max(2, math.ceil(2.0 * half_width_km / step_km))
    centres = np.arange(size, dtype=np.float64) + 0.5
    lons = bbox.west + centres * ((bbox.east - bbox.west) / size)
    y_north, y_south = _mercator_y(bbox.north), _mercator_y(bbox.south)
    lats = _mercator_lat(y_north - centres * ((y_north - y_south) / size))
    return CropGrid(bbox=bbox, lats=lats, lons=lons)


def decode_segment(raw: bytes) -> DecodedSegment:
    """Calibrate one decompressed HSD v1.3 IR segment to brightness temperature.

    Raises :class:`HsdFormatError` for a layout this reader does not handle (compressed
    data block, non-16-bit counts, a visible band, an unexpected block sequence).
    """
    try:
        return _decode_segment(raw)
    except struct.error as exc:
        raise HsdFormatError(f"HSD header shorter than its block layout: {exc}") from exc


def sample_segments(segments: Sequence[DecodedSegment], grid: CropGrid) -> npt.NDArray[np.float32]:
    """Nearest HSD pixel for every grid cell of one band; NaN where no segment covers it."""
    if not segments:
        raise ValueError("no segments to sample")
    projection = segments[0].projection
    if any(segment.projection != projection for segment in segments):
        raise HsdFormatError("segments of one band disagree on their projection")
    lat2d, lon2d = grid.mesh()
    line, column = projection.line_col(lat2d, lon2d)
    seen = np.isfinite(line) & np.isfinite(column)
    line_no = np.floor(np.where(seen, line, 0.0) + 0.5).astype(np.int64)
    column_no = np.floor(np.where(seen, column, 0.0) + 0.5).astype(np.int64)
    out = np.full(grid.shape, np.nan, dtype=np.float32)
    for segment in segments:
        rows = line_no - segment.first_line
        cols = column_no - 1
        n_lines, n_cols = segment.bt_k.shape
        inside = seen & (rows >= 0) & (rows < n_lines) & (cols >= 0) & (cols < n_cols)
        out[inside] = segment.bt_k[rows[inside], cols[inside]]
    return out


def cold_top_corrected_btd(first_bt_k: FloatArray, second_bt_k: FloatArray) -> FloatArray:
    """First minus second band, plus (230 K - T1) / 12.5 where T1 < 230 K (Tupper 2004)."""
    first = np.asarray(first_bt_k, dtype=np.float64)
    btd = first - np.asarray(second_bt_k, dtype=np.float64)
    with np.errstate(invalid="ignore"):
        shift = np.where(
            first < COLD_TOP_REFERENCE_K, (COLD_TOP_REFERENCE_K - first) / COLD_TOP_SCALE_K, 0.0
        )
    return btd + shift


def summarise(
    grid: CropGrid,
    first_bt_k: FloatArray,
    second_bt_k: FloatArray,
    *,
    vent_lat: float,
    vent_lon: float,
    half_width_km: float,
    threshold_k: float,
) -> BtdSummary:
    """Statistics, indicator pixels, indicator state and polygon for one crop."""
    if np.shape(first_bt_k) != grid.shape or np.shape(second_bt_k) != grid.shape:
        raise ValueError(f"band fields must match the grid shape {grid.shape}")
    btd = cold_top_corrected_btd(first_bt_k, second_bt_k)
    lat2d, lon2d = grid.mesh()
    distance_km = _haversine_grid_km(vent_lat, vent_lon, lat2d, lon2d)
    disc = distance_km <= half_width_km
    valid = disc & np.isfinite(btd)
    pixel_count = int(valid.sum())
    if pixel_count == 0:
        raise ValueError("no usable split-window pixels around the volcano")
    with np.errstate(invalid="ignore"):
        negative = valid & (btd < threshold_k)
        deep_cloud = valid & (np.asarray(first_bt_k) < DEEP_CLOUD_K)
    clusters = _indicator_clusters(negative, distance_km, min(NEAR_VENT_KM, half_width_km))
    values = btd[valid]
    valid_fraction = pixel_count / int(disc.sum())
    deep_cloud_fraction = int(deep_cloud.sum()) / pixel_count

    rows = np.concatenate([r for r, _ in clusters]) if clusters else np.empty(0, np.intp)
    cols = np.concatenate([c for _, c in clusters]) if clusters else np.empty(0, np.intp)
    nearest_km, bearing_deg, centroid_km = _centroid(
        lat2d[rows, cols], lon2d[rows, cols], distance_km[rows, cols], vent_lat, vent_lon
    )

    if clusters:
        indicator = BtdIndicator.NEGATIVE_BTD_PRESENT
    elif valid_fraction < MIN_VALID_FRACTION or deep_cloud_fraction > MAX_DEEP_CLOUD_FRACTION:
        indicator = BtdIndicator.INCONCLUSIVE
    else:
        indicator = BtdIndicator.SILENT

    negative_count = int(negative.sum())
    return BtdSummary(
        pixel_count=pixel_count,
        negative_pixel_count=negative_count,
        negative_fraction=round(negative_count / pixel_count, 5),
        min_btd_k=round(float(values.min()), 2),
        p05_btd_k=round(float(np.percentile(values, 5)), 2),
        median_btd_k=round(float(np.median(values)), 2),
        min_bt_k=round(float(np.asarray(first_bt_k)[valid].min()), 2),
        valid_fraction=round(valid_fraction, 4),
        deep_cloud_fraction=round(deep_cloud_fraction, 4),
        cluster_count=len(clusters),
        indicator_pixel_count=int(rows.size),
        nearest_negative_km=nearest_km,
        centroid_bearing_deg=bearing_deg,
        centroid_distance_km=centroid_km,
        indicator=indicator,
        indicator_area=_indicator_area(clusters, lat2d, lon2d, grid.pixel_deg),
        btd_k=btd,
    )


def render_png(grid: CropGrid, btd_k: FloatArray, *, vent_lat: float, vent_lon: float) -> bytes:
    """Diverging heat map of the difference (fixed -3..+5 K scale) with a vent cross.

    Pixels without data are transparent, so the basemap shows through on the Wall.
    """
    if np.shape(btd_k) != grid.shape:
        raise ValueError(f"BTD field must match the grid shape {grid.shape}")
    low, high = PNG_SCALE_K
    finite = np.isfinite(btd_k)
    clipped = np.clip(np.where(finite, btd_k, 0.0), low, high)
    is_negative = clipped < 0
    weight = np.where(is_negative, clipped / low, clipped / high)[..., np.newaxis]
    end_colour = np.where(is_negative[..., np.newaxis], _ASH_BLUE, _MOIST_ORANGE)
    rgb = np.rint(_NEUTRAL + weight * (end_colour - _NEUTRAL)).astype(np.uint8)
    alpha = np.where(finite, _OVERLAY_ALPHA, 0).astype(np.uint8)
    rgba = np.ascontiguousarray(np.dstack([rgb, alpha]))
    _draw_vent_cross(rgba, grid, vent_lat, vent_lon)
    buffer = BytesIO()
    Image.fromarray(rgba).save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def analyse_btd(
    segments: Sequence[tuple[HsdObject, bytes]],
    volcano: Volcano,
    *,
    band_pair: BandPair,
    half_width_km: float,
    threshold_k: float,
    listing_url: str,
    fetched_at: datetime,
) -> BtdAnalysis:
    """Decode, crop, summarise and render one scan for one volcano (sync, CPU-bound)."""
    bands = band_numbers(band_pair)
    used = [(obj, blob) for obj, blob in segments if obj.band in bands]
    if {obj.band for obj, _ in used} != set(bands):
        raise ValueError(f"{band_pair} needs segments of bands {bands}")
    scan_starts = {obj.scan_start for obj, _ in used}
    if len(scan_starts) != 1:
        raise ValueError("segments come from more than one scan")
    scan_start = scan_starts.pop()

    grid = crop_grid(volcano.lat, volcano.lon, half_width_km)
    fields = _band_fields(used, bands, grid)
    summary = summarise(
        grid,
        fields.first_bt_k,
        fields.second_bt_k,
        vent_lat=volcano.lat,
        vent_lon=volcano.lon,
        half_width_km=half_width_km,
        threshold_k=threshold_k,
    )
    png = render_png(grid, summary.btd_k, vent_lat=volcano.lat, vent_lon=volcano.lon)
    digests = [sha256_bytes(blob) for _, blob in used]
    provenance = Provenance(
        source_id=make_source_id("BTD", volcano.id, timeutil.compact(scan_start)),
        feed=FeedId.HSD,
        url=listing_url,
        fetched_at=fetched_at,
        issued_at=fields.observed_at,
        sha256=combine_hashes(digests),
    )
    result = BtdResult(
        provenance=provenance,
        volcano_id=volcano.id,
        scan_start=scan_start,
        band_pair=band_pair,
        bbox=grid.bbox,
        threshold_k=threshold_k,
        pixel_count=summary.pixel_count,
        negative_pixel_count=summary.negative_pixel_count,
        negative_fraction=summary.negative_fraction,
        min_btd_k=summary.min_btd_k,
        p05_btd_k=summary.p05_btd_k,
        median_btd_k=summary.median_btd_k,
        min_bt_k=summary.min_bt_k,
        nearest_negative_km=summary.nearest_negative_km,
        negative_centroid_bearing_deg=summary.centroid_bearing_deg,
        negative_centroid_distance_km=summary.centroid_distance_km,
        indicator=summary.indicator,
        caveats=_caveats(summary, band_pair, threshold_k),
        segment_sha256=digests,
        image_key=btd_key(volcano.id, scan_start),
    )
    return BtdAnalysis(result=result, png=png, indicator_area=summary.indicator_area)


def compute_btd(
    segments: Sequence[tuple[HsdObject, bytes]],
    volcano: Volcano,
    *,
    band_pair: BandPair,
    half_width_km: float,
    threshold_k: float,
    listing_url: str,
    fetched_at: datetime,
) -> tuple[BtdResult, bytes]:
    """The stored result and its PNG (sync and CPU-bound; core runs it in a thread)."""
    analysis = analyse_btd(
        segments,
        volcano,
        band_pair=band_pair,
        half_width_km=half_width_km,
        threshold_k=threshold_k,
        listing_url=listing_url,
        fetched_at=fetched_at,
    )
    return analysis.result, analysis.png


async def run_btd(
    source: Source, volcano: Volcano, at: datetime, settings: Settings
) -> tuple[BtdResult, bytes] | None:
    """Newest complete scan at or before ``at``; None when no recent scan is complete."""
    bands = band_numbers(settings.btd_band_pair)
    bbox = crop_grid(volcano.lat, volcano.lon, settings.btd_half_width_km).bbox
    found = await find_latest_scan(source, at, bands, segments_for_bbox(bbox))
    if found is None:
        log.info("no complete Himawari-9 scan for %s near %s", volcano.id, timeutil.to_iso(at))
        return None
    slot, objects = found
    fetched = await fetch_segments(source, objects)
    result, png = await asyncio.to_thread(
        compute_btd,
        [(obj, response.content) for obj, response in fetched],
        volcano,
        band_pair=settings.btd_band_pair,
        half_width_km=settings.btd_half_width_km,
        threshold_k=settings.btd_threshold_k,
        listing_url=build_url(HSD_BUCKET_URL, listing_params(slot)),
        fetched_at=max(response.fetched_at for _, response in fetched),
    )
    if any(response.replay for _, response in fetched):
        replayed = result.provenance.model_copy(update={"replay": True})
        result = result.model_copy(update={"provenance": replayed})
    return result, png


def btd_caption(result: BtdResult) -> str:
    """One line for the map overlay and the source card, with the actual scan time."""
    scanned = result.provenance.issued_at or result.scan_start
    state = {
        BtdIndicator.NEGATIVE_BTD_PRESENT: "negative BTD near the vent (indicator, not detection)",
        BtdIndicator.SILENT: "no signal - this does not mean no ash",
        BtdIndicator.INCONCLUSIVE: "inconclusive - this does not mean no ash",
    }[result.indicator]
    return (
        f"Himawari-9 {result.band_pair} split window, scanned {scanned:%H:%M:%S}Z | "
        f"background {result.median_btd_k:+.1f} K | "
        f"{result.negative_pixel_count} px below {result.threshold_k:+.1f} K | {state} | "
        f"{HIMAWARI_CREDIT}"
    )


# --- HSD decoding -----------------------------------------------------------------------


def _decode_segment(raw: bytes) -> DecodedSegment:
    if len(raw) < 6:
        raise HsdFormatError("HSD file too short")
    order = {0: "<", 1: ">"}.get(raw[5])
    if order is None:
        raise HsdFormatError(f"unknown HSD byte-order flag {raw[5]}")
    blocks, walked = _header_blocks(raw, order)
    basic, data_info, nav, calib, seg_info = (blocks[n] for n in (1, 2, 3, 5, 7))

    (header_length,) = struct.unpack_from(order + "I", basic, 70)
    if header_length != walked:
        raise HsdFormatError(f"header length {header_length} != sum of blocks {walked}")
    bits, columns, lines, compression = struct.unpack_from(order + "HHHB", data_info, 3)
    if bits != 16 or compression != 0:
        raise HsdFormatError(f"unsupported data block ({bits} bit, compression {compression})")

    (band,) = struct.unpack_from(order + "H", calib, 3)
    if band < _FIRST_IR_BAND:
        raise HsdFormatError(f"band {band} is not an infrared band")
    sub_lon, cfac, lfac, coff, loff, distance, eq_radius, polar_radius = struct.unpack_from(
        order + "dIIffddd", nav, 3
    )
    projection = GeosProjection(
        sub_lon_deg=sub_lon,
        cfac=float(cfac),
        lfac=float(lfac),
        coff=float(coff),
        loff=float(loff),
        satellite_distance_km=distance,
        equatorial_radius_km=eq_radius,
        polar_radius_km=polar_radius,
    )
    _, segment_no, first_line = struct.unpack_from(order + "BBH", seg_info, 3)
    obs_start, obs_end = struct.unpack_from(order + "dd", basic, 46)

    data_end = header_length + 2 * columns * lines
    if len(raw) < data_end:
        raise HsdFormatError(f"data block truncated: {len(raw)} bytes, need {data_end}")
    counts = np.frombuffer(
        raw, dtype=np.dtype(f"{order}u2"), count=columns * lines, offset=header_length
    ).reshape(lines, columns)
    return DecodedSegment(
        band=band,
        segment=segment_no,
        first_line=first_line,
        projection=projection,
        observation_start=_from_mjd(obs_start),
        observation_end=_from_mjd(obs_end),
        bt_k=_ir_calibration(calib, order).brightness_temperature(counts),
    )


def _header_blocks(raw: bytes, order: str) -> tuple[dict[int, bytes], int]:
    """Blocks 1..11 by their stated lengths (block 10 alone has a 4-byte length field)."""
    blocks: dict[int, bytes] = {}
    offset = 0
    for number in range(1, _HSD_BLOCK_COUNT + 1):
        if offset >= len(raw) or raw[offset] != number:
            raise HsdFormatError(f"HSD header block {number} not found at byte {offset}")
        (length,) = struct.unpack_from(order + ("I" if number == 10 else "H"), raw, offset + 1)
        if length < 3 or offset + length > len(raw):
            raise HsdFormatError(f"HSD header block {number} has bad length {length}")
        blocks[number] = raw[offset : offset + length]
        offset += length
    return blocks, offset


def _ir_calibration(block: bytes, order: str) -> _IrCalibration:
    (wavelength_um,) = struct.unpack_from(order + "d", block, 5)
    error_count, outside_count = struct.unpack_from(order + "HH", block, 15)
    slope, intercept = struct.unpack_from(order + "dd", block, 19)
    c0, c1, c2 = struct.unpack_from(order + "ddd", block, 35)
    light_speed, planck, boltzmann = struct.unpack_from(order + "ddd", block, 83)
    return _IrCalibration(
        wavelength_um=wavelength_um,
        slope=slope,
        intercept=intercept,
        error_count=error_count,
        outside_count=outside_count,
        c0=c0,
        c1=c1,
        c2=c2,
        light_speed=light_speed,
        planck=planck,
        boltzmann=boltzmann,
    )


def _from_mjd(mjd: float) -> datetime:
    """Header times are MJD doubles (about 1 us of float noise): keep whole milliseconds."""
    return _MJD_EPOCH + timedelta(seconds=round(mjd * 86400.0, 3))


def _band_fields(
    segments: Sequence[tuple[HsdObject, bytes]], bands: tuple[int, int], grid: CropGrid
) -> _BandFields:
    try:
        return _regrid_numpy(segments, bands, grid)
    except HsdFormatError as exc:
        log.warning("numpy HSD reader cannot read these segments (%s); trying satpy", exc)
        return _regrid_satpy(segments, bands, grid)


def _regrid_numpy(
    segments: Sequence[tuple[HsdObject, bytes]], bands: tuple[int, int], grid: CropGrid
) -> _BandFields:
    decoded: dict[int, list[DecodedSegment]] = {band: [] for band in bands}
    for obj, blob in segments:
        segment = decode_segment(decompress(blob))
        if segment.band != obj.band:
            raise ValueError(f"{obj.key} holds band {segment.band}, not {obj.band}")
        decoded[obj.band].append(segment)
    first, second = (sample_segments(decoded[band], grid) for band in bands)
    observed = min(segment.observation_start for group in decoded.values() for segment in group)
    return _BandFields(first_bt_k=first, second_bt_k=second, observed_at=observed)


def _regrid_satpy(
    segments: Sequence[tuple[HsdObject, bytes]], bands: tuple[int, int], grid: CropGrid
) -> _BandFields:
    try:
        from pyresample.geometry import AreaDefinition
        from satpy import Scene
    except ImportError as exc:
        raise ScienceUnavailable(
            "the numpy HSD reader cannot read these segments and satpy is not installed "
            "(install the [science] extra)"
        ) from exc
    names = [f"B{band:02d}" for band in bands]
    height, width = grid.shape
    bbox = grid.bbox
    radius = _WEB_MERCATOR_RADIUS_M
    extent = (
        radius * math.radians(bbox.west),
        radius * float(_mercator_y(bbox.south)),
        radius * math.radians(bbox.east),
        radius * float(_mercator_y(bbox.north)),
    )
    # Assumes pyresample's positional AreaDefinition(id, description, proj_id, projection,
    # width, height, area_extent) and EPSG:3857 as the spherical Web Mercator of crop_grid.
    area = AreaDefinition(
        "tephra_btd", "TEPHRA BTD crop", "tephra_btd", "EPSG:3857", width, height, extent
    )
    try:
        with tempfile.TemporaryDirectory(prefix="tephra-hsd-") as tmp:
            paths = write_decompressed(segments, Path(tmp))
            scene = Scene(filenames=[str(path) for path in paths], reader="ahi_hsd")
            scene.load(names, calibration="brightness_temperature")
            local = scene.resample(
                area, resampler="nearest", radius_of_influence=_SATPY_RADIUS_OF_INFLUENCE_M
            )
            first, second = (np.asarray(local[name].values, dtype=np.float32) for name in names)
            start: datetime = scene.start_time
    except Exception as exc:
        raise ScienceUnavailable(f"satpy could not read the HSD segments: {exc}") from exc
    observed = start.replace(tzinfo=UTC) if start.tzinfo is None else start.astimezone(UTC)
    return _BandFields(first_bt_k=first, second_bt_k=second, observed_at=observed)


# --- geometry and clusters --------------------------------------------------------------


def _mercator_y(lat_deg: npt.ArrayLike) -> npt.NDArray[np.float64]:
    """Web Mercator y on the unit sphere."""
    return np.log(np.tan(np.pi / 4.0 + np.radians(lat_deg) / 2.0))


def _mercator_lat(y: npt.ArrayLike) -> npt.NDArray[np.float64]:
    return np.degrees(2.0 * np.arctan(np.exp(y)) - np.pi / 2.0)


def _haversine_grid_km(
    lat: float, lon: float, lats: FloatArray, lons: FloatArray
) -> npt.NDArray[np.float64]:
    phi1, phi2 = math.radians(lat), np.radians(lats)
    a = (
        np.sin((phi2 - phi1) / 2.0) ** 2
        + math.cos(phi1) * np.cos(phi2) * np.sin(np.radians(lons - lon) / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.minimum(1.0, np.sqrt(a)))


def _connected_components(mask: npt.NDArray[np.bool_]) -> list[Cluster]:
    """8-connected groups of True cells; the masks are sparse, so a plain flood fill does."""
    remaining = {(int(r), int(c)) for r, c in zip(*np.nonzero(mask), strict=True)}
    components: list[Cluster] = []
    while remaining:
        start = remaining.pop()
        stack = [start]
        members = [start]
        while stack:
            row, col = stack.pop()
            for d_row in (-1, 0, 1):
                for d_col in (-1, 0, 1):
                    neighbour = (row + d_row, col + d_col)
                    if neighbour in remaining:
                        remaining.remove(neighbour)
                        stack.append(neighbour)
                        members.append(neighbour)
        rows, cols = zip(*members, strict=True)
        components.append((np.array(rows, dtype=np.intp), np.array(cols, dtype=np.intp)))
    return components


def _indicator_clusters(
    negative: npt.NDArray[np.bool_], distance_km: FloatArray, near_vent_km: float
) -> list[Cluster]:
    """Clusters big enough to be more than noise that reach to within ``near_vent_km``."""
    return [
        (rows, cols)
        for rows, cols in _connected_components(negative)
        if rows.size >= MIN_CLUSTER_PX and float(distance_km[rows, cols].min()) <= near_vent_km
    ]


def _centroid(
    lats: FloatArray, lons: FloatArray, distance_km: FloatArray, vent_lat: float, vent_lon: float
) -> tuple[float | None, float | None, float | None]:
    """Nearest distance, and bearing and distance of the centroid, of indicator pixels."""
    if lats.size == 0:
        return None, None, None
    centroid_lat, centroid_lon = float(lats.mean()), float(lons.mean())
    return (
        round(float(distance_km.min()), 1),
        round(initial_bearing_deg(vent_lat, vent_lon, centroid_lat, centroid_lon), 1),
        round(haversine_km(vent_lat, vent_lon, centroid_lat, centroid_lon), 1),
    )


def _indicator_area(
    clusters: Sequence[Cluster],
    lat2d: FloatArray,
    lon2d: FloatArray,
    pixel_deg: float,
) -> GeoPolygon | GeoMultiPolygon | None:
    if not clusters:
        return None
    hulls = [
        MultiPoint(np.column_stack((lon2d[rows, cols], lat2d[rows, cols]))).convex_hull.buffer(
            pixel_deg, quad_segs=2
        )
        for rows, cols in clusters
    ]
    return _to_geometry(unary_union(hulls))


def _to_geometry(geometry: BaseGeometry) -> GeoPolygon | GeoMultiPolygon:
    if isinstance(geometry, Polygon):
        return GeoPolygon(coordinates=_rings(geometry))
    if isinstance(geometry, MultiPolygon):
        return GeoMultiPolygon(coordinates=[_rings(part) for part in geometry.geoms])
    raise ValueError(f"indicator area is a {geometry.geom_type}, not a polygon")


def _rings(polygon: Polygon) -> list[list[Position]]:
    return [
        [(float(x), float(y)) for x, y in ring.coords]
        for ring in (polygon.exterior, *polygon.interiors)
    ]


def _draw_vent_cross(
    rgba: npt.NDArray[np.uint8], grid: CropGrid, vent_lat: float, vent_lon: float
) -> None:
    row = int(np.argmin(np.abs(grid.lats - vent_lat)))
    col = int(np.argmin(np.abs(grid.lons - vent_lon)))
    black = np.array([0, 0, 0, 255], dtype=np.uint8)
    rgba[row, max(col - _VENT_ARM_PX, 0) : col + _VENT_ARM_PX + 1] = black
    rgba[max(row - _VENT_ARM_PX, 0) : row + _VENT_ARM_PX + 1, col] = black


# --- caveats ----------------------------------------------------------------------------


def _caveats(summary: BtdSummary, band_pair: BandPair, threshold_k: float) -> list[str]:
    lines = [_indicator_line(summary, threshold_k)]
    if summary.median_btd_k > MOIST_BACKGROUND_K:
        lines.append(
            f"Background {band_pair} is {summary.median_btd_k:+.1f} K (moist air): ash here "
            "can stay positive and unseen."
        )
    lines.extend(STANDARD_CAVEATS)
    lines.append(HIMAWARI_CREDIT)
    return lines


def _indicator_line(summary: BtdSummary, threshold_k: float) -> str:
    if summary.indicator is BtdIndicator.NEGATIVE_BTD_PRESENT:
        return (
            f"{summary.indicator_pixel_count} pixels in {summary.cluster_count} cluster(s) "
            f"below {threshold_k:+.1f} K reach within {NEAR_VENT_KM:.0f} km of the vent: "
            "consistent with silicate ash. An indicator, not detection."
        )
    if summary.indicator is BtdIndicator.INCONCLUSIVE:
        if summary.valid_fraction < MIN_VALID_FRACTION:
            reason = f"only {summary.valid_fraction:.0%} of the crop has usable pixels"
        else:
            reason = (
                f"{summary.deep_cloud_fraction:.0%} of the crop is colder than "
                f"{DEEP_CLOUD_K:.0f} K (deep cloud hides what lies beneath)"
            )
        return f"Inconclusive: {reason}. This does not mean no ash."
    return (
        "No split-window signal near the vent. This does not mean no ash: the method often "
        "misses low, moist, ice-coated or opaque tropical plumes (Tupper et al. 2004)."
    )
