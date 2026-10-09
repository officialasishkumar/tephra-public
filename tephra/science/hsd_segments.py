"""Find and fetch raw Himawari-9 full-disk segments (HSD) on the NOAA Open Data bucket.

The bucket ``noaa-himawari9`` is listed and read anonymously over plain HTTPS GET, so it
goes through the same :class:`~tephra.feeds.base.Source` as every other feed (and replays
the same way). A full-disk scan starts every 10 minutes and is published as 16 bands x 10
segments, numbered north to south; the 2 km infrared bands are 5500 x 5500 pixels, so each
segment holds 550 lines. Which segments cover a volcano follows from the geostationary
projection (CGMS LRIT/HRIT Global Specification 4.4, as the JMA HSD User's Guide v1.3
uses it), implemented here in numpy so no satellite library is needed to plan a download.

Objects usually appear 10 to 14 minutes after the nominal scan start (research/12), so the
newest complete scan is found by walking back over a few 10-minute slots.
"""

import bz2
import logging
import re
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

import numpy as np
import numpy.typing as npt

from tephra.feeds.base import FetchError, FetchResult, Source
from tephra.models import BBox, FeedId, TephraModel, UtcDatetime
from tephra.util import timeutil

__all__ = [
    "FLDK_PREFIX",
    "FULL_DISK_LINES",
    "HIMAWARI_AHI_2KM",
    "HSD_BUCKET_URL",
    "LINES_PER_SEGMENT",
    "SEGMENT_COUNT",
    "SLOT_MINUTES",
    "GeosProjection",
    "HsdObject",
    "decompress",
    "download",
    "fetch_segments",
    "find_latest_scan",
    "listing_params",
    "parse_listing",
    "segment_for_line",
    "segments_for_bbox",
    "write_decompressed",
]

log = logging.getLogger(__name__)

HSD_BUCKET_URL: Final = "https://noaa-himawari9.s3.amazonaws.com/"
FLDK_PREFIX: Final = "AHI-L1b-FLDK"
SLOT_MINUTES: Final = 10
FULL_DISK_LINES: Final = 5500
SEGMENT_COUNT: Final = 10
LINES_PER_SEGMENT: Final = FULL_DISK_LINES // SEGMENT_COUNT
BBOX_SAMPLES: Final = 17
"""Sample points per bbox side when working out which segments it touches."""

_KEY_NAME = re.compile(
    r"HS_H\d{2}_(?P<date>\d{8})_(?P<time>\d{4})_B(?P<band>\d{2})_FLDK_R\d{2}"
    r"_S(?P<segment>\d{2})(?P<total>\d{2})\.DAT\.bz2$"
)


@dataclass(frozen=True, slots=True)
class GeosProjection:
    """Normalised geostationary projection of an HSD image (header block #3).

    Defaults are the Himawari-9 2 km full-disk values read from real 2026 headers
    (research/12): sub-satellite longitude 140.7 E, CFAC = LFAC = 20466275,
    COFF = LOFF = 2750.5. Line and column numbers are 1-based, lines run north to south
    and columns west to east, as in the HSD guide.
    """

    sub_lon_deg: float = 140.7
    cfac: float = 20466275.0
    lfac: float = 20466275.0
    coff: float = 2750.5
    loff: float = 2750.5
    satellite_distance_km: float = 42164.0
    equatorial_radius_km: float = 6378.137
    polar_radius_km: float = 6356.7523

    def line_col(
        self, lat_deg: npt.ArrayLike, lon_deg: npt.ArrayLike
    ) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
        """Fractional (line, column) of each point; NaN where the satellite cannot see it."""
        lat = np.radians(np.asarray(lat_deg, dtype=np.float64))
        dlon = np.radians(np.asarray(lon_deg, dtype=np.float64) - self.sub_lon_deg)
        ratio = (self.polar_radius_km / self.equatorial_radius_km) ** 2
        c_lat = np.arctan(ratio * np.tan(lat))
        r_l = self.polar_radius_km / np.sqrt(1.0 - (1.0 - ratio) * np.cos(c_lat) ** 2)
        r1 = self.satellite_distance_km - r_l * np.cos(c_lat) * np.cos(dlon)
        r2 = -r_l * np.cos(c_lat) * np.sin(dlon)
        r3 = r_l * np.sin(c_lat)
        rn = np.sqrt(r1**2 + r2**2 + r3**2)
        x_deg = np.degrees(np.arctan(-r2 / r1))
        y_deg = np.degrees(np.arcsin(-r3 / rn))
        column = self.coff + x_deg * self.cfac / 2.0**16
        line = self.loff + y_deg * self.lfac / 2.0**16
        # Spherical horizon test: the point faces the satellite when |P|^2 < h * P_x.
        visible = r_l**2 < self.satellite_distance_km * (self.satellite_distance_km - r1)
        return np.where(visible, line, np.nan), np.where(visible, column, np.nan)


HIMAWARI_AHI_2KM: Final = GeosProjection()


class HsdObject(TephraModel):
    """One ``.DAT.bz2`` segment file in the bucket."""

    key: str
    url: str
    band: int
    segment: int
    size_bytes: int
    scan_start: UtcDatetime


def listing_params(scan_start: datetime) -> dict[str, str]:
    """ListObjectsV2 query for one full-disk slot (the slot holds 160 keys, under 1000)."""
    slot = timeutil.floor_minutes(scan_start, SLOT_MINUTES)
    return {"list-type": "2", "prefix": f"{FLDK_PREFIX}/{slot:%Y/%m/%d/%H%M}/"}


def parse_listing(result: FetchResult) -> list[HsdObject]:
    """Full-disk segment objects in an S3 ``ListBucketResult``; other keys are ignored."""
    try:
        root = ET.fromstring(result.content)
    except ET.ParseError as exc:
        raise ValueError(f"S3 listing is not XML: {exc}") from exc
    if _local(root.tag) != "ListBucketResult":
        raise ValueError(f"unexpected S3 listing root element {_local(root.tag)!r}")
    if _child_text(root, "IsTruncated") == "true":
        log.warning(
            "S3 listing truncated at %s; segments past the first page are ignored", result.url
        )
    objects: list[HsdObject] = []
    for contents in root:
        if _local(contents.tag) != "Contents":
            continue
        obj = _object_from_contents(contents)
        if obj is not None:
            objects.append(obj)
    return objects


def segment_for_line(line: int) -> int:
    """Full-disk segment (1..10) holding a 1-based 2 km line."""
    return min(max((line - 1) // LINES_PER_SEGMENT + 1, 1), SEGMENT_COUNT)


def segments_for_bbox(bbox: BBox, projection: GeosProjection = HIMAWARI_AHI_2KM) -> list[int]:
    """Full-disk segments (1..10, north to south) that cover any part of ``bbox``.

    The box is sampled on a grid that includes the sub-satellite meridian when the box
    spans it, because that is where a latitude reaches its extreme line number.
    """
    lons = np.linspace(bbox.west, bbox.east, BBOX_SAMPLES)
    if bbox.west < projection.sub_lon_deg < bbox.east:
        lons = np.append(lons, projection.sub_lon_deg)
    lats = np.linspace(bbox.south, bbox.north, BBOX_SAMPLES)
    lat_grid, lon_grid = np.meshgrid(lats, lons, indexing="ij")
    lines, _ = projection.line_col(lat_grid, lon_grid)
    seen = lines[np.isfinite(lines)]
    if seen.size == 0:
        raise ValueError(f"bbox {bbox} is not visible from Himawari-9")
    pixels = np.floor(seen + 0.5).astype(int)
    pixels = pixels[(pixels >= 1) & (pixels <= FULL_DISK_LINES)]
    if pixels.size == 0:
        raise ValueError(f"bbox {bbox} falls outside the full-disk image")
    return sorted({segment_for_line(int(line)) for line in np.unique(pixels)})


async def find_latest_scan(
    source: Source,
    at: datetime,
    bands: Sequence[int],
    segments: Sequence[int],
    *,
    lookback_slots: int = 6,
) -> tuple[datetime, list[HsdObject]] | None:
    """Newest slot at or before ``at`` holding every requested band x segment.

    Returns the slot's nominal start time and its objects ordered by (band, segment), or
    None when none of the last ``lookback_slots`` slots is complete yet.
    """
    wanted = {(band, segment) for band in bands for segment in segments}
    if not wanted:
        raise ValueError("find_latest_scan needs at least one band and one segment")
    newest = timeutil.floor_minutes(at, SLOT_MINUTES)
    for step in range(lookback_slots):
        slot = newest - timedelta(minutes=SLOT_MINUTES * step)
        result = await source.fetch(HSD_BUCKET_URL, feed=FeedId.HSD, params=listing_params(slot))
        found = {
            (obj.band, obj.segment): obj
            for obj in parse_listing(result)
            if (obj.band, obj.segment) in wanted and obj.scan_start == slot
        }
        if found.keys() == wanted:
            return slot, [found[pair] for pair in sorted(wanted)]
        log.debug("HSD slot %s has %d of %d wanted segments", slot, len(found), len(wanted))
    return None


async def fetch_segments(
    source: Source, objects: Sequence[HsdObject]
) -> list[tuple[HsdObject, FetchResult]]:
    """GET each segment in turn; a body whose size differs from the listing is an error."""
    fetched: list[tuple[HsdObject, FetchResult]] = []
    for obj in objects:
        result = await source.fetch(obj.url, feed=FeedId.HSD)
        if len(result.content) != obj.size_bytes:
            raise FetchError(
                obj.url,
                FeedId.HSD,
                f"got {len(result.content)} bytes, listing says {obj.size_bytes}",
            )
        fetched.append((obj, result))
    return fetched


async def download(source: Source, objects: Sequence[HsdObject]) -> list[tuple[HsdObject, bytes]]:
    """The bzip2-compressed bytes of each object, in the given order."""
    return [(obj, result.content) for obj, result in await fetch_segments(source, objects)]


def decompress(blob: bytes) -> bytes:
    """Decompress a whole-file bzip2 segment (multi-stream files included)."""
    try:
        return bz2.decompress(blob)
    except (OSError, ValueError, EOFError) as exc:
        raise ValueError(f"segment is not a valid bzip2 stream: {exc}") from exc


def write_decompressed(segments: Sequence[tuple[HsdObject, bytes]], directory: Path) -> list[Path]:
    """Write each segment as a plain ``.DAT`` file named as in the bucket (for satpy).

    Decompressing once here spares satpy's own temporary bzip2 extraction per read.
    """
    directory.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for obj, blob in segments:
        name = Path(obj.key).name.removesuffix(".bz2")
        path = directory / name
        path.write_bytes(decompress(blob))
        paths.append(path)
    return paths


def _object_from_contents(contents: ET.Element) -> HsdObject | None:
    key = _child_text(contents, "Key")
    if key is None or not key.startswith(f"{FLDK_PREFIX}/"):
        return None
    match = _KEY_NAME.search(key)
    if match is None or int(match["total"]) != SEGMENT_COUNT:
        return None
    size = _child_text(contents, "Size")
    if size is None or not size.isdigit():
        log.warning("S3 object %s has no usable Size; skipped", key)
        return None
    scan_start = datetime.strptime(match["date"] + match["time"], "%Y%m%d%H%M").replace(tzinfo=UTC)
    return HsdObject(
        key=key,
        url=HSD_BUCKET_URL + key,
        band=int(match["band"]),
        segment=int(match["segment"]),
        size_bytes=int(size),
        scan_start=scan_start,
    )


def _child_text(element: ET.Element, name: str) -> str | None:
    for child in element:
        if _local(child.tag) == name:
            return (child.text or "").strip()
    return None


def _local(tag: str) -> str:
    """Element name without its ``{namespace}`` prefix."""
    return tag.rpartition("}")[2]
