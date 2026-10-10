"""Rendered Himawari-9 frames cropped around a volcano: context for the Wall and Gemini.

Two public sources, both images rather than data:

* JMA Meteorological Satellite Center real-time JPEGs (Band 13 IR and Dust RGB). File
  names carry only the 10-minute slot (``se3_b13_1920.jpg``) and are overwritten daily, so
  the slot's date comes from the ``slt_time`` list on ``sat_img.php``. JMA's Public Data
  License 1.0 asks for the source and a note that the image was edited (cropped here).
* NICT true colour tiles (dated paths), fetched only in local daylight. NICT's terms say
  "not allowed for commercial uses"; TEPHRA is a non-commercial demo.

Neither publishes its georeference. The crops below use projections inferred from the
burned-in graticule and coastlines (JMA) or the standard 2 km full-disk grid (NICT), which
is close enough to centre a crop but not to overlay it on the map. Every frame therefore
has ``bbox=None`` and the Wall shows it in a side strip. Frames are context only and are
never used to draw the cone.

The registry asks for frames one volcano at a time, while every volcano in one JMA area
shares the slot list and the two JPEGs, and neighbours share NICT tiles. Each source's
answers (failures included) are therefore reused for :data:`REUSE_S` seconds on the
active clock, so one poll downloads each image once and crops it per volcano.
"""

import asyncio
import io
import logging
import math
import re
import weakref
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final, Protocol

from PIL import Image

from tephra.feeds.base import FetchError, FetchResult, Source, build_url
from tephra.geo.units import destination_point, solar_hour
from tephra.models import FeedId, FrameProduct, Provenance, SatelliteFrame, Volcano, make_source_id
from tephra.util import timeutil
from tephra.util.hashing import combine_hashes

__all__ = [
    "JMA_AREAS",
    "JMA_IMAGE_URL",
    "JMA_SLOTS_URL",
    "NICT_LATEST_URL",
    "NICT_TILE_URL",
    "REUSE_S",
    "JmaArea",
    "Mercator",
    "PlateCarree",
    "fetch_frames",
    "frame_key",
    "fulldisk_pixel",
    "parse_jma_slots",
    "parse_nict_latest",
]

logger = logging.getLogger(__name__)

JMA_IMAGE_URL: Final = (
    "https://www.data.jma.go.jp/mscweb/data/himawari/img/{area}/{area}_{band}_{hhmm}.jpg"
)
JMA_SLOTS_URL: Final = "https://www.data.jma.go.jp/mscweb/data/himawari/sat_img.php"
NICT_LATEST_URL: Final = "https://himawari8.nict.go.jp/img/D531106/latest.json"
NICT_TILE_URL: Final = (
    "https://himawari8.nict.go.jp/img/D531106/{level}d/550/{year}/{month}/{day}/"
    "{hhmmss}_{x}_{y}.png"
)

JMA_BANDS: Final[dict[FrameProduct, str]] = {
    FrameProduct.B13_IR: "b13",
    FrameProduct.DUST_RGB: "dst",
}
PRODUCT_LABELS: Final[dict[FrameProduct, str]] = {
    FrameProduct.B13_IR: "Band 13 infrared (10.4 um)",
    FrameProduct.DUST_RGB: "Dust RGB",
    FrameProduct.TRUE_COLOR: "true colour",
}
JMA_SETTLE_MIN: Final = 35
"""Minimum slot age before its image is trusted.

A slot's file lands about 14 min after scan start and CloudFront may keep the previous
day's copy of the same date-less name for up to 10 min more (research/05 C5).
"""
JMA_LABEL_OFFSET: Final = timedelta(minutes=10)
"""The ``slt_time`` labels (and burned-in captions) read slot start + 10 min."""

NICT_TILE_PX: Final = 550
NICT_DEFAULT_LEVEL: Final = 8
NICT_MAX_TILES: Final = 4
NICT_DARK_TILE_BYTES: Final = 1024
"""Night tiles are 444-byte all-black PNGs; a daylight tile is hundreds of kilobytes."""
DAYLIGHT_SOLAR_HOURS: Final = (7.0, 17.0)

FRAME_CAPTION_SUFFIX: Final = "context only; not used to draw the cone"
JMA_CREDIT: Final = "Source: JMA Meteorological Satellite Center ({area} image), cropped by TEPHRA"
NICT_CREDIT: Final = (
    "Source: NICT Himawari real-time web (non-commercial use only), cropped by TEPHRA"
)
REUSE_S: Final = 60.0
"""Seconds one source's answer serves the later volcanoes of a poll.

Well below the registry's 120 s retry gap and 600 s frame cadence, so the next poll
always fetches afresh.
"""

_MONTHS: Final[dict[str, int]] = {
    name: number
    for number, name in enumerate(
        (
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
        ),
        start=1,
    )
}  # fmt: skip
_SLOT_OPTION = re.compile(
    r"<option\s+value=[\"']?(\d{4})[\"']?\s*>\s*(\d{2}):(\d{2})\s+UTC\s+(\d{1,2})\s+([A-Za-z]+)"
    r"\s+(\d{4})\s*</option>",
    re.IGNORECASE,
)

type _Failure = tuple[str, str]
"""``(url, reason)`` of a product that could not be made."""


# --- projections ------------------------------------------------------------------------


class Projection(Protocol):
    def to_pixel(self, lat: float, lon: float) -> tuple[float, float] | None: ...


@dataclass(frozen=True, slots=True)
class PlateCarree:
    """Equal-angle grid: ``deg_per_px`` in both axes from the top-left corner."""

    west_deg: float
    north_deg: float
    deg_per_px: float

    def to_pixel(self, lat: float, lon: float) -> tuple[float, float]:
        return (lon - self.west_deg) / self.deg_per_px, (self.north_deg - lat) / self.deg_per_px


@dataclass(frozen=True, slots=True)
class Mercator:
    """Mercator with ``px_per_deg`` of longitude; ``ref_lat_deg`` sits on row ``ref_y_px``."""

    west_deg: float
    px_per_deg: float
    ref_lat_deg: float
    ref_y_px: float

    def to_pixel(self, lat: float, lon: float) -> tuple[float, float]:
        px_per_rad = self.px_per_deg * 180.0 / math.pi
        y = self.ref_y_px - (_mercator_y(lat) - _mercator_y(self.ref_lat_deg)) * px_per_rad
        return (lon - self.west_deg) * self.px_per_deg, y


@dataclass(frozen=True, slots=True)
class JmaArea:
    code: str
    name: str
    width_px: int
    height_px: int
    projection: PlateCarree | Mercator

    def covers(self, lat: float, lon: float) -> bool:
        x, y = self.projection.to_pixel(lat, lon)
        return 0 <= x < self.width_px and 0 <= y < self.height_px


JMA_AREAS: Final[tuple[JmaArea, ...]] = (
    # 0.05 deg/px from 90E 10N to 145E 15S; the 10-degree graticule sits at x=200,400,...
    # and y=200,400 and Semeru falls near pixel (458, 362) (tests/fixtures/FORMATS.md).
    JmaArea("se3", "Southeast Asia 3", 1101, 501, PlateCarree(90.0, 10.0, 0.05)),
    # Mercator, 20 px/deg from 115E; 40N on row 200 and 30N on row 445 (inferred likewise).
    JmaArea("jpn", "Japan", 801, 641, Mercator(115.0, 20.0, 40.0, 200.0)),
)

HIMAWARI_SUB_LON_DEG: Final = 140.7
_SAT_DISTANCE_KM: Final = 42164.0
_POLAR_RADIUS_KM: Final = 6356.7523
_FULL_DISK_PX: Final = 5500
_CFAC: Final = 20466275  # 2 km grid: columns per degree of scan angle x 2^16
_COFF: Final = 2750.5


def fulldisk_pixel(lat: float, lon: float, size_px: int) -> tuple[float, float] | None:
    """Pixel of a point in a full-disk Himawari image ``size_px`` wide, or None if unseen.

    CGMS normalized geostationary projection on the JMA 2 km grid, scaled linearly to the
    image. Assumes NICT's D531106 PNGs resample that grid edge to edge, which matches the
    coastlines in the fixture tiles (Darwin and Flores fall where predicted).
    """
    phi = math.radians(lat)
    dlon = math.radians(lon - HIMAWARI_SUB_LON_DEG)
    c_lat = math.atan(0.993305616 * math.tan(phi))
    r_l = _POLAR_RADIUS_KM / math.sqrt(1.0 - 0.00669438444 * math.cos(c_lat) ** 2)
    x_e = r_l * math.cos(c_lat) * math.cos(dlon)
    if x_e * _SAT_DISTANCE_KM <= r_l * r_l:
        return None  # beyond the limb
    r1 = _SAT_DISTANCE_KM - x_e
    r2 = -r_l * math.cos(c_lat) * math.sin(dlon)
    r3 = r_l * math.sin(c_lat)
    rn = math.sqrt(r1 * r1 + r2 * r2 + r3 * r3)
    x_deg = math.degrees(math.atan(-r2 / r1))
    y_deg = math.degrees(math.asin(-r3 / rn))
    column = _COFF + x_deg * _CFAC / 2**16
    line = _COFF + y_deg * _CFAC / 2**16
    scale = size_px / _FULL_DISK_PX
    return (column - 0.5) * scale, (line - 0.5) * scale


# --- public API -------------------------------------------------------------------------


def frame_key(volcano_id: str, product: FrameProduct, observed_at: datetime) -> str:
    return f"frames/{volcano_id}_{product.value}_{timeutil.compact(observed_at)}.png"


async def fetch_frames(
    source: Source,
    volcano: Volcano,
    *,
    half_width_km: float = 300.0,
    areas: Sequence[JmaArea] = JMA_AREAS,
    nict_level: int = NICT_DEFAULT_LEVEL,
    nict: bool = True,
) -> list[tuple[SatelliteFrame, bytes]]:
    """Crops around ``volcano`` as ``(frame, png)``; a product that fails is skipped.

    ``nict=False`` skips NICT's true colour entirely (``Settings.nict_frames``).

    Raises :class:`FetchError` when products were tried and none came back, so an outage
    reaches the feed health instead of reading as an empty success.
    """
    frames: list[tuple[SatelliteFrame, bytes]] = []
    failures: list[_Failure] = []
    area = next((area for area in areas if area.covers(volcano.lat, volcano.lon)), None)
    if area is not None:
        jma, failed = await _jma_frames(source, volcano, area, half_width_km)
        frames.extend(jma)
        failures.extend(failed)
    if nict:
        try:
            frame = await _nict_frame(source, volcano, half_width_km, nict_level)
        except (FetchError, ValueError, OSError) as exc:
            logger.warning("NICT true colour for %s skipped: %s", volcano.name, exc)
            url = exc.url if isinstance(exc, FetchError) else NICT_LATEST_URL
            failures.append((url, f"NICT true colour: {_reason(exc)}"))
        else:
            if frame is not None:
                frames.append(frame)
    if failures and not frames:
        raise FetchError(failures[0][0], FeedId.FRAMES, "; ".join(why for _, why in failures))
    return frames


def parse_jma_slots(result: FetchResult) -> list[datetime]:
    """Scan start of every slot in the page's ``slt_time`` list, newest first."""
    slots: list[datetime] = []
    for value, hour, minute, day, month_name, year in _SLOT_OPTION.findall(result.text()):
        month = _MONTHS.get(month_name.lower())
        if month is None:
            continue
        labelled = datetime(int(year), month, int(day), int(hour), int(minute), tzinfo=UTC)
        start = labelled - JMA_LABEL_OFFSET
        if start.strftime("%H%M") == value:
            slots.append(start)
    if not slots:
        raise ValueError("no image slots in the JMA slot list")
    return sorted(set(slots), reverse=True)


def parse_nict_latest(result: FetchResult) -> datetime:
    payload = result.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("date"), str):
        raise ValueError("NICT latest.json has no 'date'")
    return timeutil.parse_iso(payload["date"])


# --- JMA --------------------------------------------------------------------------------


async def _jma_frames(
    source: Source, volcano: Volcano, area: JmaArea, half_width_km: float
) -> tuple[list[tuple[SatelliteFrame, bytes]], list[_Failure]]:
    page_url = build_url(JMA_SLOTS_URL, {"area": area.code})
    try:
        page = await _fetch(source, JMA_SLOTS_URL, {"area": area.code})
        if page.stale:
            raise ValueError("slot list served from cache; image dates cannot be trusted")
        slot = _settled_slot(parse_jma_slots(page), page.fetched_at)
    except (FetchError, ValueError) as exc:
        logger.warning("JMA %s slot list unusable: %s", area.code, exc)
        return [], [(page_url, f"JMA {area.code} slot list: {_reason(exc)}")]
    frames: list[tuple[SatelliteFrame, bytes]] = []
    failures: list[_Failure] = []
    for product, band in JMA_BANDS.items():
        url = JMA_IMAGE_URL.format(area=area.code, band=band, hhmm=slot.strftime("%H%M"))
        try:
            result = await _fetch(source, url)
            if result.stale:
                # A cached copy of a date-less file name may hold another day's image.
                raise ValueError("image served from cache")
            box = _crop_box(area.projection, volcano, half_width_km, area.width_px, area.height_px)
            png, size = await asyncio.to_thread(
                _crop_image, result.content, box, (area.width_px, area.height_px)
            )
        except (FetchError, ValueError, OSError) as exc:
            logger.warning("JMA %s %s for %s skipped: %s", area.code, band, volcano.name, exc)
            failures.append((url, f"JMA {area.code} {band}: {_reason(exc)}"))
            continue
        caption = (
            f"Himawari-9 {PRODUCT_LABELS[product]}, scan {timeutil.hhmmz(slot)}. "
            f"{JMA_CREDIT.format(area=area.name)}; {FRAME_CAPTION_SUFFIX}"
        )
        provenance = result.provenance(_source_id(product, volcano, slot), issued_at=slot)
        frames.append((_frame(product, volcano, slot, provenance, size, caption), png))
    return frames, failures


def _settled_slot(slots: Sequence[datetime], fetched_at: datetime) -> datetime:
    cutoff = fetched_at - timedelta(minutes=JMA_SETTLE_MIN)
    for slot in slots:
        if slot <= cutoff:
            return slot
    raise ValueError("no slot old enough to be today's image")


# --- NICT -------------------------------------------------------------------------------


async def _nict_frame(
    source: Source, volcano: Volcano, half_width_km: float, level: int
) -> tuple[SatelliteFrame, bytes] | None:
    latest = await _fetch(source, NICT_LATEST_URL)
    scan = parse_nict_latest(latest)
    start_h, end_h = DAYLIGHT_SOLAR_HOURS
    if not start_h <= solar_hour(volcano.lon, scan) <= end_h:
        return None
    size = NICT_TILE_PX * level
    box = _crop_box(_FullDisk(size), volcano, half_width_km, size, size)
    tiles = _tiles_for(box)
    if len(tiles) > NICT_MAX_TILES:
        raise ValueError(f"crop needs {len(tiles)} tiles; lower the level or the width")
    results: list[tuple[tuple[int, int], FetchResult]] = []
    for x, y in tiles:
        url = NICT_TILE_URL.format(
            level=level,
            year=scan.strftime("%Y"),
            month=scan.strftime("%m"),
            day=scan.strftime("%d"),
            hhmmss=scan.strftime("%H%M%S"),
            x=x,
            y=y,
        )
        result = await _fetch(source, url)
        if len(result.content) < NICT_DARK_TILE_BYTES:
            return None
        results.append(((x, y), result))
    png, out_size = await asyncio.to_thread(
        _stitch_and_crop, [(xy, result.content) for xy, result in results], box
    )
    caption = (
        f"Himawari-9 {PRODUCT_LABELS[FrameProduct.TRUE_COLOR]}, scan {timeutil.hhmmz(scan)}. "
        f"{NICT_CREDIT}; {FRAME_CAPTION_SUFFIX}"
    )
    provenance = _tiles_provenance(
        _source_id(FrameProduct.TRUE_COLOR, volcano, scan),
        [result for _, result in results],
        scan,
    )
    frame = _frame(FrameProduct.TRUE_COLOR, volcano, scan, provenance, out_size, caption)
    return frame, png


@dataclass(frozen=True, slots=True)
class _FullDisk:
    size_px: int

    def to_pixel(self, lat: float, lon: float) -> tuple[float, float] | None:
        return fulldisk_pixel(lat, lon, self.size_px)


def _tiles_for(box: tuple[int, int, int, int]) -> list[tuple[int, int]]:
    left, top, right, bottom = box
    columns = range(left // NICT_TILE_PX, (right - 1) // NICT_TILE_PX + 1)
    rows = range(top // NICT_TILE_PX, (bottom - 1) // NICT_TILE_PX + 1)
    return [(x, y) for y in rows for x in columns]


def _tiles_provenance(source_id: str, results: Sequence[FetchResult], scan: datetime) -> Provenance:
    """One provenance for a stitched frame: first tile's URL, hash over every tile."""
    first = results[0]
    stale_ages = [result.stale_age_s for result in results if result.stale_age_s is not None]
    return Provenance(
        source_id=source_id,
        feed=FeedId.FRAMES,
        url=first.url,
        fetched_at=max(result.fetched_at for result in results),
        issued_at=scan,
        sha256=combine_hashes(result.sha256 for result in results),
        stale=any(result.stale for result in results),
        stale_age_s=max(stale_ages) if stale_ages else None,
        replay=any(result.replay for result in results),
    )


# --- shared -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Answer:
    at: datetime
    result: FetchResult | None = None
    failure: str = ""


_ANSWERS: Final[weakref.WeakKeyDictionary[Source, dict[str, _Answer]]] = weakref.WeakKeyDictionary()


async def _fetch(source: Source, url: str, params: Mapping[str, str] | None = None) -> FetchResult:
    """``source.fetch`` for frames, reusing this source's answer from the last ``REUSE_S``."""
    answers = _answers_of(source)
    key = build_url(url, params)
    at = timeutil.now()
    answer = answers.get(key)
    if answer is None or not _reusable(answer, at):
        try:
            answer = _Answer(at, result=await source.fetch(url, feed=FeedId.FRAMES, params=params))
        except FetchError as exc:
            answer = _Answer(at, failure=exc.reason)
        for old in [old for old, kept in answers.items() if not _reusable(kept, at)]:
            del answers[old]
        answers[key] = answer
    if answer.result is None:
        raise FetchError(key, FeedId.FRAMES, answer.failure)
    return answer.result


def _reusable(answer: _Answer, at: datetime) -> bool:
    """A clock that moved back (a replay starting its loop again) expires every answer."""
    return 0.0 <= (at - answer.at).total_seconds() < REUSE_S


def _answers_of(source: Source) -> dict[str, _Answer]:
    try:
        return _ANSWERS.setdefault(source, {})
    except TypeError:  # a source that cannot be weakly referenced shares nothing
        return {}


def _reason(exc: Exception) -> str:
    return exc.reason if isinstance(exc, FetchError) else str(exc)


def _crop_box(
    projection: Projection, volcano: Volcano, half_width_km: float, width: int, height: int
) -> tuple[int, int, int, int]:
    """``(left, top, right, bottom)`` pixels of a square of ``half_width_km`` around the vent."""
    points = [(volcano.lat, volcano.lon)] + [
        destination_point(volcano.lat, volcano.lon, bearing, half_width_km)
        for bearing in (0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0)
    ]
    projected = [projection.to_pixel(lat, lon) for lat, lon in points]
    pixels = [pixel for pixel in projected if pixel is not None]
    if len(pixels) != len(projected):
        raise ValueError(f"{volcano.name} is not fully visible in this image")
    xs = [x for x, _ in pixels]
    ys = [y for _, y in pixels]
    vent_x, vent_y = pixels[0]
    if not (0 <= vent_x < width and 0 <= vent_y < height):
        raise ValueError(f"{volcano.name} is outside this image")
    left, top = max(0, math.floor(min(xs))), max(0, math.floor(min(ys)))
    right, bottom = min(width, math.ceil(max(xs))), min(height, math.ceil(max(ys)))
    if right - left < 2 or bottom - top < 2:
        raise ValueError("crop is empty")
    return left, top, right, bottom


def _crop_image(
    content: bytes, box: tuple[int, int, int, int], expected_size: tuple[int, int]
) -> tuple[bytes, tuple[int, int]]:
    with Image.open(io.BytesIO(content)) as image:
        if image.size != expected_size:
            # A different layout means the inferred georeference no longer holds.
            raise ValueError(f"image is {image.size}, expected {expected_size}")
        crop = image.convert("RGB").crop(box)
    return _png(crop), crop.size


def _stitch_and_crop(
    tiles: Sequence[tuple[tuple[int, int], bytes]], box: tuple[int, int, int, int]
) -> tuple[bytes, tuple[int, int]]:
    x0 = min(x for (x, _), _ in tiles)
    y0 = min(y for (_, y), _ in tiles)
    columns = max(x for (x, _), _ in tiles) - x0 + 1
    rows = max(y for (_, y), _ in tiles) - y0 + 1
    canvas = Image.new("RGB", (columns * NICT_TILE_PX, rows * NICT_TILE_PX))
    for (x, y), content in tiles:
        with Image.open(io.BytesIO(content)) as tile:
            canvas.paste(tile.convert("RGB"), ((x - x0) * NICT_TILE_PX, (y - y0) * NICT_TILE_PX))
    left, top, right, bottom = box
    offset_x, offset_y = x0 * NICT_TILE_PX, y0 * NICT_TILE_PX
    crop = canvas.crop((left - offset_x, top - offset_y, right - offset_x, bottom - offset_y))
    return _png(crop), crop.size


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _source_id(product: FrameProduct, volcano: Volcano, observed_at: datetime) -> str:
    return make_source_id("FRAME", product.value, volcano.id, timeutil.compact(observed_at))


def _frame(
    product: FrameProduct,
    volcano: Volcano,
    observed_at: datetime,
    provenance: Provenance,
    size: tuple[int, int],
    caption: str,
) -> SatelliteFrame:
    return SatelliteFrame(
        provenance=provenance,
        product=product,
        observed_at=observed_at,
        volcano_id=volcano.id,
        image_key=frame_key(volcano.id, product, observed_at),
        width_px=size[0],
        height_px=size[1],
        bbox=None,
        caption=caption,
    )


def _mercator_y(lat: float) -> float:
    return math.log(math.tan(math.pi / 4.0 + math.radians(lat) / 2.0))
