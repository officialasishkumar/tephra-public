"""Volcanic-ash SIGMETs from aviationweather.gov international SIGMET JSON.

Geometry comes from the JSON ``coords`` (decimal degrees, already closed). The raw text is
kept for display and audit and is the fallback for anything the JSON leaves out; raw-text
coordinates are degrees and minutes (``S0806`` is 8 deg 06 min south), never decimals.

The degree-minute, level-band and movement helpers here are shared with ``tephra.feeds.vaac``
because SIGMETs and VAAs write those groups the same way.
"""

import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any, Final, NamedTuple

from tephra.feeds.base import FetchResult, Source
from tephra.geo.units import KM_PER_NM, compass_to_deg
from tephra.models import FeedId, GeoPolygon, Sigmet, make_source_id, polygon_from_latlon
from tephra.util import timeutil

__all__ = [
    "SIGMET_PARAMS",
    "SIGMET_URL",
    "LevelBand",
    "Movement",
    "fetch_sigmets",
    "find_dm_points",
    "parse_dm_point",
    "parse_level_band",
    "parse_movement",
    "parse_sigmets",
    "polygon_or_none",
]

SIGMET_URL: Final = "https://aviationweather.gov/api/data/isigmet"
SIGMET_PARAMS: Final = {"format": "json", "hazard": "va"}

log = logging.getLogger(__name__)

# A degree-minute position: N0129 E12738, S0806E11255, or degrees only (N01 E127).
_DM_POINT = re.compile(r"\b([NS])(\d{2})(\d{2})?\s*([EW])(\d{3})(\d{2})?\b")
_LEVEL_BAND = re.compile(r"\b(SFC|FL\d{3})\s*/\s*(?:FL)?(\d{3})\b")
_TOP_LEVEL = re.compile(r"\bTOPS?\s+(ABV\s+)?FL(\d{3})\b")
_ABOVE_LEVEL = re.compile(r"\bABV\s+FL(\d{3})\b")
_PSN_GROUP = re.compile(r"\bPSN\s+(?P<lat>[NS]\d{2}(?:\d{2})?)\s*(?P<lon>[EW]\d{3}(?:\d{2})?)\b")
# The volcano's name runs from the last of these words to PSN: "FIR VA ERUPTION MT SEMERU
# PSN", but also "FIR MT SAKURAJIMA (AIRA CALDERA) PSN" (RJJJ, WIIF) and "FIR VA CLD MT ...".
_NAME_LEAD = re.compile(r"\b(?:FIR|VA|CLD|ERUPTION|MT)\b")
_NAME = re.compile(r"[A-Z][A-Z0-9 ()\[\]'.-]*")
_MOVEMENT = re.compile(r"\bMOV\s+([NESW]{1,3})\s+(\d{1,3})\s*(KT|KMH)\b")
_MOVEMENT_NO_SPEED = re.compile(r"\bMOV\s+([NESW]{1,3})\b")
_STATIONARY = re.compile(r"\bSTNR\b")
_HEADER_DTG = re.compile(r"^\s*[A-Z]{4}\d{2}\s+[A-Z]{4}\s+(\d{6})\b")
_VALID = re.compile(r"\bVALID\s+(\d{6})/(\d{6})\b")
_OBS_AT = re.compile(r"\bOBS\s+AT\s+(\d{4})Z")
_QUALIFIER_PREFIX = re.compile(r"^(?:ERUPTION\s+)?(?:MT\s+)?")
_FCST = re.compile(r"\bFCST\b")
_OBS_WORD = re.compile(r"\bOBS\b")
_NOT_IDENTIFIABLE = re.compile(r"\bNOT\s+IDENTIFIABLE\b")
_AND = re.compile(r"\bAND\b")
_VA_CLD = re.compile(r"\bVA\s+CLD\b")
_CANCEL = re.compile(r"\bCNL\s+SIGMET\b")
_INTENSITY = re.compile(r"\b(NC|WKN|INTSF)\b")


# --- shared text helpers (SIGMET and VAA) -----------------------------------------------


class LevelBand(NamedTuple):
    """A vertical band in feet: ``SFC/FL150`` -> (0, 15000); ``FL200/350`` -> (20000, 35000)."""

    base_ft: int
    top_ft: int


class Movement(NamedTuple):
    """``MOV NE 10KT`` -> toward 45 deg at 10 kt; ``STNR`` -> stationary at 0 kt."""

    toward_deg: float | None
    speed_kt: float | None
    stationary: bool = False


def parse_dm_point(lat_token: str, lon_token: str) -> tuple[float, float] | None:
    """``("S0806", "E11255")`` -> ``(-8.1, 112.9167)``; None for a malformed token."""
    match = _DM_POINT.fullmatch(f"{lat_token.strip()} {lon_token.strip()}")
    return _point_from_match(match) if match else None


def find_dm_points(text: str) -> list[tuple[float, float]]:
    """Every degree-minute ``(lat, lon)`` in ``text``, in order; malformed groups are skipped."""
    points: list[tuple[float, float]] = []
    for match in _DM_POINT.finditer(text):
        found = _point_from_match(match)
        if found is not None:
            points.append(found)
    return points


def parse_level_band(text: str) -> LevelBand | None:
    match = _LEVEL_BAND.search(text)
    if match is None:
        return None
    base = 0 if match.group(1) == "SFC" else int(match.group(1)[2:]) * 100
    return LevelBand(base, int(match.group(2)) * 100)


def parse_movement(text: str) -> Movement | None:
    match = _MOVEMENT.search(text)
    if match is not None:
        speed = float(match.group(2))
        if match.group(3) == "KMH":
            speed = round(speed / KM_PER_NM, 1)
        return Movement(compass_to_deg(match.group(1)), speed)
    if _STATIONARY.search(text):
        return Movement(None, 0.0, True)
    match = _MOVEMENT_NO_SPEED.search(text)
    if match is not None:
        return Movement(compass_to_deg(match.group(1)), None)
    return None


def polygon_or_none(points: Iterable[tuple[float, float]]) -> GeoPolygon | None:
    """A closed polygon from ``(lat, lon)`` points, or None when they do not make one."""
    try:
        return polygon_from_latlon(points)
    except ValueError:
        return None


def _point_from_match(match: re.Match[str]) -> tuple[float, float] | None:
    lat_hem, lat_deg, lat_min, lon_hem, lon_deg, lon_min = match.groups()
    lat_minutes = int(lat_min or 0)
    lon_minutes = int(lon_min or 0)
    if lat_minutes >= 60 or lon_minutes >= 60:
        return None
    lat = int(lat_deg) + lat_minutes / 60.0
    lon = int(lon_deg) + lon_minutes / 60.0
    if lat > 90 or lon > 180:
        return None
    return (-lat if lat_hem == "S" else lat, -lon if lon_hem == "W" else lon)


# --- SIGMET parsing ---------------------------------------------------------------------


def parse_sigmets(result: FetchResult) -> list[Sigmet]:
    """Every VA record in the response, expired ones included (replay needs them)."""
    if not result.content.strip():
        return []
    try:
        payload = result.json()
    except ValueError as exc:
        raise ValueError(f"isigmet response is not JSON: {exc}") from exc
    if not isinstance(payload, list):
        raise ValueError("isigmet response is not a JSON array")
    sigmets: list[Sigmet] = []
    seen: set[tuple[str, str]] = set()
    for record in payload:
        if not isinstance(record, Mapping) or str(record.get("hazard", "")).upper() != "VA":
            continue
        key = (str(record.get("rawSigmet", "")), str(record.get("seriesId", "")))
        if key in seen:
            continue
        seen.add(key)
        try:
            sigmets.extend(_parse_record(record, result))
        except (ValueError, TypeError) as exc:
            log.warning("skipping unreadable VA SIGMET %s: %s", key[1] or "?", exc)
    return sigmets


async def fetch_sigmets(source: Source) -> list[Sigmet]:
    result = await source.fetch(SIGMET_URL, feed=FeedId.SIGMET, params=SIGMET_PARAMS)
    at = timeutil.now()
    return [sigmet for sigmet in parse_sigmets(result) if sigmet.valid_to >= at]


def _parse_record(record: Mapping[str, Any], result: FetchResult) -> list[Sigmet]:
    """The record's own cloud, plus one record per later cloud joined to it by ``AND``."""
    raw = str(record.get("rawSigmet") or "").replace("\r", "")
    flat = " ".join(raw.split())
    series_id = str(record.get("seriesId") or "").strip()
    fir_id = str(record.get("firId") or "").strip().upper()
    if not series_id or not fir_id:
        raise ValueError("record has no seriesId or firId")
    forecast_record = series_id.upper().endswith("F")
    areas = _areas(flat)
    observed_part, forecast_part = areas[0]
    # A SIGMET with only a forecast cloud ("VA CLD FCST AT 1600Z WI ...") has no F record.
    own_forecast = forecast_record or (bool(forecast_part) and not _OBS_WORD.search(observed_part))
    kind = 1 if own_forecast else 0
    parts = [(area[kind], f"{area[0]} {area[1]}") for area in areas if area[kind]]
    own_part = parts[0][0] if parts else ""

    receipt = _optional_time(record.get("receiptTime"))
    valid_from, valid_to = _validity(record, flat, receipt or result.fetched_at)
    issued_at = _header_dtg(raw, valid_from) or receipt

    name, psn = _volcano(flat, record.get("qualifier"))
    band = parse_level_band(own_part) or parse_level_band(flat)
    text_base, text_top = (band.base_ft, band.top_ft) if band else _open_levels(flat)
    base_ft = _optional_int(record.get("base"))
    top_ft = _optional_int(record.get("top"))
    if base_ft is None:
        base_ft = text_base or 0
    if top_ft is None:
        top_ft = text_top

    movement = parse_movement(own_part) or parse_movement(flat) or _json_movement(record)
    source_id = make_source_id("SIGMET", fir_id, series_id, timeutil.compact(valid_from))
    sigmet = Sigmet(
        provenance=result.provenance(
            source_id, issued_at=issued_at, valid_from=valid_from, valid_to=valid_to
        ),
        fir_id=fir_id,
        fir_name=_optional_str(record.get("firName")),
        issuing_office=_optional_str(record.get("icaoId")),
        series_id=series_id,
        volcano_name=name,
        volcano_lat=psn[0] if psn else None,
        volcano_lon=psn[1] if psn else None,
        observed=_observed(forecast_record, observed_part, forecast_part),
        observed_at=None if forecast_record else _observed_at(observed_part, valid_from),
        base_ft=base_ft,
        top_ft=top_ft,
        polygon=_json_polygon(record.get("coords"), series_id) or _text_polygon(own_part),
        movement_toward_deg=movement.toward_deg if movement else None,
        movement_speed_kt=movement.speed_kt if movement else None,
        stationary=movement.stationary if movement else False,
        intensity_change=_intensity(record.get("chng"), own_part),
        valid_from=valid_from,
        valid_to=valid_to,
        cancelled=bool(_CANCEL.search(flat)),
        raw_text=raw.strip(),
    )
    if sigmet.cancelled:
        return [sigmet]
    return [sigmet, *_later_areas(sigmet, parts[1:])]


def _split_forecast(flat: str) -> tuple[str, str]:
    match = _FCST.search(flat)
    if match is None:
        return flat, ""
    return flat[: match.start()], flat[match.start() :]


def _areas(flat: str) -> list[tuple[str, str]]:
    """``(observed part, forecast part)`` of each cloud the SIGMET describes, in text order.

    Clouds are joined by ``AND``. A cloud that names neither OBS nor FCST (``FCST AT 0000Z WI
    ... AND WI ...``) is of the same kind as the part before it.
    """
    areas: list[tuple[str, str]] = []
    for chunk in _AND.split(flat):
        observed, forecast = _split_forecast(chunk)
        if areas and areas[-1][1] and not forecast and not _OBS_WORD.search(chunk):
            observed, forecast = "", chunk
        areas.append((observed, forecast))
    return areas


def _later_areas(main: Sigmet, parts: Sequence[tuple[str, str]]) -> list[Sigmet]:
    """One record per later cloud, ``(its part, its whole text)``, named ``05 AREA 2``.

    AWC's ``coords``, ``base`` and ``top`` describe the first cloud only (WAAF 05 on 26 Sep
    2026 lost a second cloud at SFC/FL150). Splitting the rest off the way AWC splits forecast
    polygons into ``F`` records keeps every official polygon.
    """
    extras: list[Sigmet] = []
    for number, (part, area) in enumerate(parts, start=2):
        polygon = _text_polygon(part)
        if polygon is None:
            continue
        base_ft, top_ft = _area_levels(part, area, main)
        movement = parse_movement(part) or parse_movement(area)
        intensity = _INTENSITY.search(area)
        series_id = f"{main.series_id} AREA {number}"
        source_id = make_source_id(
            "SIGMET", main.fir_id, series_id, timeutil.compact(main.valid_from)
        )
        update = {
            "provenance": main.provenance.model_copy(update={"source_id": source_id}),
            "series_id": series_id,
            "observed_at": _observed_at(part, main.valid_from) or main.observed_at,
            "base_ft": base_ft,
            "top_ft": top_ft,
            "polygon": polygon,
            "movement_toward_deg": movement.toward_deg if movement else None,
            "movement_speed_kt": movement.speed_kt if movement else None,
            "stationary": movement.stationary if movement else False,
            "intensity_change": intensity.group(1) if intensity else None,
        }
        extras.append(main.model_copy(update=update))
    return extras


def _area_levels(part: str, area: str, main: Sigmet) -> tuple[int, int | None]:
    """A later cloud's band from its own text; a cloud that states none shares the first's."""
    for text in (part, area):
        band = parse_level_band(text)
        if band is not None:
            return band.base_ft, band.top_ft
        base_ft, top_ft = _open_levels(text)
        if base_ft is not None or top_ft is not None:
            return base_ft or 0, top_ft
    return main.base_ft, main.top_ft


def _validity(
    record: Mapping[str, Any], flat: str, reference: datetime
) -> tuple[datetime, datetime]:
    start = _optional_time(record.get("validTimeFrom"))
    end = _optional_time(record.get("validTimeTo"))
    if start is None or end is None:
        match = _VALID.search(flat)
        if match is None:
            raise ValueError("no validity in JSON or raw text")
        start = start or timeutil.parse_ddhhmm(match.group(1), reference)
        end = end or timeutil.parse_ddhhmm(match.group(2), start)
    return start, end


def _header_dtg(raw: str, reference: datetime) -> datetime | None:
    match = _HEADER_DTG.match(raw)
    if match is None:
        return None
    try:
        return timeutil.parse_ddhhmm(match.group(1), reference)
    except ValueError:
        return None


def _volcano(flat: str, qualifier: Any) -> tuple[str | None, tuple[float, float] | None]:
    psn = _PSN_GROUP.search(flat)
    position = parse_dm_point(psn.group("lat"), psn.group("lon")) if psn else None
    name = _name_before(flat[: psn.start()]) if psn else None
    if name is None and isinstance(qualifier, str) and qualifier.strip():
        name = _QUALIFIER_PREFIX.sub("", " ".join(qualifier.upper().split())) or None
    return name, position


def _name_before(text: str) -> str | None:
    leads = list(_NAME_LEAD.finditer(text))
    if not leads:
        return None
    name = text[leads[-1].end() :].strip()
    return name if _NAME.fullmatch(name) else None


def _observed(forecast_record: bool, observed_part: str, forecast_part: str) -> bool | None:
    if forecast_record:
        return False
    if _NOT_IDENTIFIABLE.search(observed_part):
        return None  # "VA CLD OBS AT 2310Z VA NOT IDENTIFIABLE": a non-observation
    if _OBS_WORD.search(observed_part):
        return True
    return False if forecast_part else None


def _observed_at(observed_part: str, valid_from: datetime) -> datetime | None:
    match = _OBS_AT.search(observed_part)
    if match is None:
        return None
    return timeutil.parse_hhmmz(match.group(1), valid_from)


def _json_polygon(coords: Any, series_id: str) -> GeoPolygon | None:
    if not isinstance(coords, list) or not coords:
        return None
    rings = coords if isinstance(coords[0], list) else [coords]
    if len(rings) > 1:
        # Seen only on non-VA records ("AREAS"); a GeoPolygon holds one area, so the extra
        # rings are dropped loudly rather than silently.
        log.warning("SIGMET %s has %d areas; keeping the first", series_id, len(rings))
    points: list[tuple[float, float]] = []
    for vertex in rings[0]:
        if isinstance(vertex, Mapping) and "lat" in vertex and "lon" in vertex:
            points.append((float(vertex["lat"]), float(vertex["lon"])))
    return polygon_or_none(points)


def _text_polygon(part: str) -> GeoPolygon | None:
    cloud = _VA_CLD.search(part)
    text = part[cloud.end() :] if cloud else part
    # The PSN group is not a vertex, but a vertex often sits on the vent: drop the group only.
    return polygon_or_none(find_dm_points(_PSN_GROUP.sub(" ", text)))


def _open_levels(flat: str) -> tuple[int | None, int | None]:
    """``(base_ft, top_ft)`` from a level that is not a band; None where it is not stated.

    ``TOP FL150`` is a top. ``ABV FL080`` puts the ash above FL080: a base with no stated top.
    ``TOP ABV FL300`` is a top somewhere above FL300, so not stated either.
    """
    top = _TOP_LEVEL.search(flat)
    if top is not None:
        return None, None if top.group(1) else int(top.group(2)) * 100
    above = _ABOVE_LEVEL.search(flat)
    if above is not None:
        return int(above.group(1)) * 100, None
    return None, None


def _json_movement(record: Mapping[str, Any]) -> Movement | None:
    direction = _optional_str(record.get("dir"))
    speed = _optional_float(record.get("spd"))
    if direction == "-":
        return Movement(None, 0.0, True) if speed == 0 else None
    if direction is None:
        return None
    return Movement(compass_to_deg(direction.upper()), speed)


def _intensity(chng: Any, part: str) -> str | None:
    text = _optional_str(chng)
    if text:
        return text.upper()
    match = _INTENSITY.search(part)
    return match.group(1) if match else None


def _optional_time(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        return timeutil.parse_iso(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    number = _optional_float(value)
    return None if number is None else round(number)


def _optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
