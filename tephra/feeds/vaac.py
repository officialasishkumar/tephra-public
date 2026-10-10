"""Volcanic Ash Advisories (ICAO Annex 3 VAA text) from the Tokyo and Darwin VAACs.

Tokyo advisories come from JMA's list page and its ``TextData`` pages. Darwin advisories
come from NOAA's public tgftp bulletins, one file per WMO header holding only the latest
issue; JMA's "Darwin backup" list only carries what Tokyo issued while standing in for
Darwin, and is polled too. BoM is not polled: its list loads by POST and its terms forbid
scraping (research/05, research/13).

The text parser works on any of the layouts those sources use: JMA's ``<BR>``-separated
HTML, BoM-style ``<br />`` HTML, and plain text whose wrapped lines are indented or not.
"""

import html
import logging
import re
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Final
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from tephra.feeds.base import FetchError, FetchResult, Source
from tephra.feeds.sigmet import (
    find_dm_points,
    parse_dm_point,
    parse_level_band,
    parse_movement,
    polygon_or_none,
)
from tephra.geo.units import m_to_ft
from tephra.models import (
    AviationColor,
    FeedId,
    TephraModel,
    UtcDatetime,
    VaacAdvisory,
    VaacCentre,
    VaacStep,
    VaLayer,
    make_source_id,
    source_slug,
)
from tephra.util import timeutil

__all__ = [
    "DARWIN_BACKUP_LIST_URL",
    "DARWIN_BULLETIN_URLS",
    "TOKYO_LIST_URL",
    "VaacListItem",
    "fetch_vaas",
    "parse_vaa",
    "parse_vaa_text",
    "parse_vaac_list",
]

TOKYO_LIST_URL: Final = "https://ds.data.jma.go.jp/svd/vaac/data/vaac_list.html"
DARWIN_BACKUP_LIST_URL: Final = "https://ds.data.jma.go.jp/svd/vaac/data/vaac_darwin_list.html"
# Darwin rotates its advisories over ten WMO headers, FVAU01-FVAU10, and a slot's file keeps
# its last bulletin until the slot is reused (research/05, row 7 and K6).
DARWIN_BULLETIN_URLS: Final = tuple(
    f"https://tgftp.nws.noaa.gov/data/raw/fv/fvau{n:02d}.adrm..txt" for n in range(1, 11)
)

log = logging.getLogger(__name__)

_FIELD = re.compile(
    r"^(?P<key>STATUS|DTG|VAAC|VOLCANO|PSN|AREA|SOURCE ELEV|SUMMIT ELEV|ADVISORY NR|INFO SOURCE"
    r"|AVIATION COLOU?R CODE|ERUPTION DETAILS|(?:OBS|EST) VA DTG|(?:OBS|EST) VA CLD"
    r"|FCST VA CLD\s*\+\s*\d{1,2}\s*HR|RMK|NXT ADVISORY)\s*:\s*(?P<value>.*)$"
)
_WMO_HEADER = re.compile(r"^FV[A-Z]{2}\d{2}\s+[A-Z]{4}\s+\d{6}\b")
_ADVISORY_LINE = re.compile(r"^VA\s+ADVISORY\b")
_FCST_OFFSET = re.compile(r"\+\s*(\d{1,2})\s*HR")
_STEP_TIME = re.compile(r"^\s*(\d{2}/\d{4}Z)\s*")
_SLASH_DTG = re.compile(r"\d{8}/\d{4}Z?")
_LEVEL_START = re.compile(r"\b(?:SFC|FL\d{3})\s*/\s*(?:FL)?\d{3}\b")
_WIND_TAIL = re.compile(r"\bWIND\b.*$")
_VOLCANO = re.compile(r"^(?P<name>.*?)\s+(?P<number>\d{6})$")
_ELEV_FT = re.compile(r"(\d[\d,]*)\s*FT\b")
_ELEV_M = re.compile(r"(\d[\d,]*)\s*M\b")
_ROW_TIME = re.compile(r"(\d{4})/(\d{2})/(\d{2})\s+(\d{2}):(\d{2})(?::(\d{2}))?")
_ROW_LABEL_TIME = re.compile(r"(\d{2}):(\d{2})\s*UTC,\s*(\d{1,2})\s+([A-Za-z]{3})\.?\s+(\d{4})")
_TEXT_START = "<!-- VAA Text Start -->"
_TEXT_END = "<!-- VAA Text End -->"
_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_MONTHS: Final = {
    name: index
    for index, name in enumerate(
        ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"),
        start=1,
    )
}
_NOTICE_NAME = "NOTICE"
_NOTICE_NUMBER = "999999"
_NOT_REAL_STATUS = frozenset({"TEST", "EXER"})
"""ICAO's ``STATUS:`` line marks test and exercise bulletins, which may name real volcanoes."""


class VaacListItem(TephraModel):
    """One row of a JMA VAAC list page (Tokyo, or the Darwin backup list)."""

    vaac: VaacCentre
    url: str
    volcano_name: str
    area: str | None = None
    issued_at: UtcDatetime
    advisory_nr: str | None = None


# --- list pages -------------------------------------------------------------------------


def parse_vaac_list(result: FetchResult, vaac: VaacCentre) -> list[VaacListItem]:
    soup = BeautifulSoup(result.text(), "lxml")
    items: list[VaacListItem] = []
    for row in soup.find_all("tr", class_="mtx"):
        cells = row.find_all("td")
        if len(cells) < 6:
            continue
        link = cells[5].find("a", href=True)
        href = str(link["href"]) if link is not None else ""
        if not href or href.lower().startswith("javascript"):
            continue
        issued_at = _row_time(cells[0].get_text(" ")) or _row_label_time(cells[1].get_text(" "))
        volcano = _clean(cells[2].get_text(" "))
        if issued_at is None or not volcano:
            log.warning("skipping unreadable VAAC list row for %r", volcano or href)
            continue
        items.append(
            VaacListItem(
                vaac=vaac,
                url=urljoin(result.url, href),
                volcano_name=volcano,
                area=_clean(cells[3].get_text(" ")) or None,
                issued_at=issued_at,
                advisory_nr=_clean(cells[4].get_text(" ")) or None,
            )
        )
    return items


def _row_time(text: str) -> datetime | None:
    match = _ROW_TIME.search(text)
    if match is None:
        return None
    year, month, day, hour, minute = (int(part) for part in match.groups()[:5])
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def _row_label_time(text: str) -> datetime | None:
    match = _ROW_LABEL_TIME.search(text)
    if match is None or match.group(4).upper() not in _MONTHS:
        return None
    hour, minute, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
    month, year = _MONTHS[match.group(4).upper()], int(match.group(5))
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


# --- advisory text ----------------------------------------------------------------------


def parse_vaa(result: FetchResult) -> VaacAdvisory | None:
    """Parse one advisory from a JMA text page, a ``<br />`` HTML fragment or plain text."""
    return parse_vaa_text(_extract_text(result.text()), result)


def parse_vaa_text(text: str, result: FetchResult) -> VaacAdvisory | None:
    """One VAA from its text; None for ``VOLCANO: NOTICE`` pseudo-advisories and for
    ``STATUS: TEST`` or ``EXER`` bulletins.

    Raises ValueError when the text is not a VAA or comes from a VAAC TEPHRA does not model.
    """
    fields, raw_lines = _fields(text)
    if _not_real(fields.get("STATUS")):
        return None
    issued_at = _required_time(fields, "DTG")
    volcano_name, volcano_number = _volcano(fields.get("VOLCANO"))
    if volcano_name.upper() == _NOTICE_NAME or volcano_number == _NOTICE_NUMBER:
        return None
    advisory_nr = fields.get("ADVISORY NR", "").strip()
    if not advisory_nr:
        raise ValueError("VAA has no ADVISORY NR")
    vaac = _vaac(fields.get("VAAC"), raw_lines)

    observation = _observation(fields, issued_at)
    forecasts = _forecasts(fields, issued_at, observation)
    next_text = _next_advisory_text(fields.get("NXT ADVISORY"))
    psn = _psn(fields.get("PSN"))
    source_id = make_source_id(
        "VAA", vaac.value, volcano_number or source_slug(volcano_name), advisory_nr
    )
    advisory = VaacAdvisory(
        provenance=result.provenance(source_id, issued_at=issued_at, valid_from=issued_at),
        vaac=vaac,
        advisory_nr=advisory_nr,
        issued_at=issued_at,
        volcano_name=volcano_name,
        volcano_number=volcano_number,
        volcano_lat=psn[0] if psn else None,
        volcano_lon=psn[1] if psn else None,
        area=fields.get("AREA") or None,
        summit_elev_ft=_elevation_ft(fields.get("SOURCE ELEV") or fields.get("SUMMIT ELEV")),
        info_source=fields.get("INFO SOURCE") or None,
        aviation_color=_aviation_color(fields.get("AVIATION COLOUR CODE")),
        eruption_details=fields.get("ERUPTION DETAILS") or None,
        observation=observation,
        forecasts=forecasts,
        remarks=fields.get("RMK") or None,
        next_advisory_text=next_text,
        next_advisory_at=_next_advisory_at(next_text),
        final=bool(next_text and "NO FURTHER ADVISORIES" in next_text),
        raw_text="\n".join(raw_lines),
    )
    # The validity rule lives on the model, so the provenance learns valid_to afterwards.
    provenance = result.provenance(
        source_id, issued_at=issued_at, valid_from=issued_at, valid_to=advisory.valid_until()
    )
    return advisory.model_copy(update={"provenance": provenance})


def _extract_text(document: str) -> str:
    start = document.find(_TEXT_START)
    if start >= 0:
        end = document.find(_TEXT_END, start)
        document = document[start + len(_TEXT_START) : end if end >= 0 else None]
    elif not _BR.search(document) and "<html" not in document.lower():
        return document
    return html.unescape(_TAG.sub("", _BR.sub("\n", document)))


def _fields(text: str) -> tuple[dict[str, str], list[str]]:
    """Field values (continuation lines joined) and the advisory's own raw lines.

    A line that does not start with a known ``KEY:`` continues the previous field, whatever
    its indent: line wrapping differs by source and can split a latitude from its longitude.
    """
    fields: dict[str, str] = {}
    raw_lines: list[str] = []
    current: str | None = None
    started = False
    for line in text.replace("\r", "").split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        match = _FIELD.match(stripped)
        if not started:
            # Preamble such as BoM's "Received FVAU03 at ..." or tgftp's sequence number.
            if not (match or _WMO_HEADER.match(stripped) or _ADVISORY_LINE.match(stripped)):
                continue
            started = True
        raw_lines.append(line.rstrip())
        if match is not None:
            current = _normalise_key(match.group("key"))
            fields[current] = match.group("value").strip()
        elif current is not None:
            fields[current] = f"{fields[current]} {stripped}".strip()
        if current == "NXT ADVISORY" and stripped.endswith("="):
            break
    for key, value in fields.items():
        fields[key] = " ".join(value.rstrip("=").split())
    if "DTG" not in fields:
        raise ValueError("text has no VAA DTG line")
    return fields, raw_lines


def _not_real(status: str | None) -> bool:
    words = (status or "").upper().split()
    return bool(words) and words[0] in _NOT_REAL_STATUS


def _normalise_key(key: str) -> str:
    key = " ".join(key.split()).replace("COLOR", "COLOUR")
    offset = _FCST_OFFSET.search(key)
    if key.startswith("FCST") and offset is not None:
        return f"FCST {int(offset.group(1))}"
    return key


def _required_time(fields: dict[str, str], key: str) -> datetime:
    match = _SLASH_DTG.search(fields.get(key, ""))
    if match is None:
        raise ValueError(f"VAA has no readable {key}")
    return timeutil.parse_slash_dtg(match.group(0))


def _volcano(value: str | None) -> tuple[str, str | None]:
    text = " ".join((value or "").split())
    if not text:
        raise ValueError("VAA names no volcano")
    match = _VOLCANO.match(text)
    if match is None:
        return text, None
    return match.group("name"), match.group("number")


def _vaac(value: str | None, raw_lines: Iterable[str]) -> VaacCentre:
    name = " ".join((value or "").upper().split())
    if not name:
        header = next((line for line in raw_lines if _WMO_HEADER.match(line.strip())), "")
        name = {"RJTD": "TOKYO", "ADRM": "DARWIN"}.get(header.split()[1] if header else "", "")
    try:
        return VaacCentre(name)
    except ValueError as exc:
        raise ValueError(f"VAAC {name or '?'} is outside TEPHRA's scope") from exc


def _psn(value: str | None) -> tuple[float, float] | None:
    tokens = (value or "").split()
    if len(tokens) < 2:
        return None
    return parse_dm_point(tokens[0], tokens[1])


def _elevation_ft(value: str | None) -> int | None:
    if not value:
        return None
    feet = _ELEV_FT.search(value)
    if feet is not None:
        return int(feet.group(1).replace(",", ""))
    metres = _ELEV_M.search(value)
    if metres is not None:
        return round(m_to_ft(int(metres.group(1).replace(",", ""))))
    return None


def _aviation_color(value: str | None) -> AviationColor | None:
    word = (value or "").strip().upper()
    if not word or word == AviationColor.UNKNOWN.value:
        return None
    try:
        return AviationColor(word)
    except ValueError:
        return None


def _observation(fields: dict[str, str], issued_at: datetime) -> VaacStep | None:
    cloud_key = "EST VA CLD" if "EST VA CLD" in fields else "OBS VA CLD"
    if cloud_key not in fields:
        return None
    dtg_key = "EST VA DTG" if "EST VA DTG" in fields else "OBS VA DTG"
    dtg = fields.get(dtg_key, "")
    try:
        # A missing or unreadable observation DTG falls back to the advisory DTG.
        valid_at = timeutil.parse_day_time(dtg, issued_at) if dtg else issued_at
    except ValueError:
        valid_at = issued_at
    estimated = cloud_key.startswith("EST") or dtg_key.startswith("EST")
    return _step(0, valid_at, fields[cloud_key], estimated=estimated)


def _forecasts(
    fields: dict[str, str], issued_at: datetime, observation: VaacStep | None
) -> list[VaacStep]:
    steps: list[VaacStep] = []
    for key, value in fields.items():
        if not key.startswith("FCST "):
            continue
        offset = int(key.split()[1])
        match = _STEP_TIME.match(value)
        if match is not None:
            valid_at = timeutil.parse_day_time(match.group(1), issued_at)
            body = value[match.end() :]
        else:
            # Tokyo omits the time on "NO VA EXP" steps; ICAO steps are observation + N h.
            anchor = observation.valid_at if observation is not None else issued_at
            valid_at = anchor + timedelta(hours=offset)
            body = value
        steps.append(_step(offset, valid_at, body, estimated=False, text=value))
    return sorted(steps, key=lambda step: step.offset_h)


def _step(
    offset_h: int, valid_at: datetime, body: str, *, estimated: bool, text: str | None = None
) -> VaacStep:
    upper = body.upper()
    not_identifiable = "NOT IDENTIFIABLE" in upper
    return VaacStep(
        offset_h=offset_h,
        valid_at=valid_at,
        layers=_layers(upper),
        estimated=estimated,
        not_identifiable=not_identifiable,
        no_ash_expected="NO VA EXP" in upper,
        not_available=any(word in upper for word in ("NOT AVBL", "NOT AVAILABLE", "NOT PROVIDED")),
        text=text if text is not None else body,
    )


def _layers(body: str) -> list[VaLayer]:
    """Every ``LEVEL/LEVEL vertices [MOV ...]`` group; ``WIND SFC/FL070 160/05KT`` is not one."""
    body = _WIND_TAIL.sub("", body)
    starts = [match.start() for match in _LEVEL_START.finditer(body)]
    layers: list[VaLayer] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(body)
        segment = body[start:end]
        band = parse_level_band(segment)
        if band is None:
            continue
        movement = parse_movement(segment)
        layers.append(
            VaLayer(
                base_ft=band.base_ft,
                top_ft=band.top_ft,
                polygon=polygon_or_none(find_dm_points(segment)),
                movement_toward_deg=movement.toward_deg if movement else None,
                movement_speed_kt=movement.speed_kt if movement else None,
            )
        )
    return layers


def _next_advisory_text(value: str | None) -> str | None:
    text = " ".join((value or "").rstrip("=").split())
    return text or None


def _next_advisory_at(text: str | None) -> datetime | None:
    if not text or "NO FURTHER ADVISORIES" in text:
        return None
    match = _SLASH_DTG.search(text)
    return timeutil.parse_slash_dtg(match.group(0)) if match else None


# --- fetching ---------------------------------------------------------------------------


async def fetch_vaas(
    source: Source,
    feed: FeedId,
    *,
    since: datetime,
    known_urls: frozenset[str] = frozenset(),
) -> list[VaacAdvisory]:
    """Advisories issued at or after ``since`` for one VAAC feed."""
    if feed is FeedId.VAAC_TOKYO:
        advisories = await _from_list(
            source, feed, TOKYO_LIST_URL, VaacCentre.TOKYO, since, known_urls
        )
    elif feed is FeedId.VAAC_DARWIN:
        advisories = await _darwin(source, since, known_urls)
    else:
        raise ValueError(f"{feed.value} is not a VAAC feed")
    return _dedupe(advisories)


async def _darwin(
    source: Source, since: datetime, known_urls: frozenset[str]
) -> list[VaacAdvisory]:
    advisories: list[VaacAdvisory] = []
    failures: list[FetchError] = []
    for url in DARWIN_BULLETIN_URLS:
        try:
            result = await source.fetch(url, feed=FeedId.VAAC_DARWIN)
        except FetchError as exc:
            log.warning("Darwin bulletin unavailable: %s", exc)
            failures.append(exc)
            continue
        advisory = _parse_logged(result)
        if advisory is not None and advisory.issued_at >= since:
            advisories.append(advisory)
    if len(failures) == len(DARWIN_BULLETIN_URLS):
        # tgftp is Darwin's only live source. The backup list holds only what Tokyo issued
        # while standing in, so an answer from it alone would pass for "no advisories".
        raise failures[-1]
    try:
        advisories += await _from_list(
            source, FeedId.VAAC_DARWIN, DARWIN_BACKUP_LIST_URL, VaacCentre.DARWIN, since, known_urls
        )
    except FetchError as exc:
        log.warning("Darwin backup list unavailable: %s", exc)
    return advisories


async def _from_list(
    source: Source,
    feed: FeedId,
    list_url: str,
    vaac: VaacCentre,
    since: datetime,
    known_urls: frozenset[str],
) -> list[VaacAdvisory]:
    listing = await source.fetch(list_url, feed=feed)
    advisories: list[VaacAdvisory] = []
    for item in parse_vaac_list(listing, vaac):
        if item.issued_at < since or item.url in known_urls:
            continue
        if item.volcano_name.upper() == _NOTICE_NAME:
            continue
        try:
            result = await source.fetch(item.url, feed=feed)
        except FetchError as exc:
            log.warning("skipping VAA %s %s: %s", item.volcano_name, item.advisory_nr, exc)
            continue
        advisory = _parse_logged(result)
        if advisory is not None:
            advisories.append(advisory)
    return advisories


def _parse_logged(result: FetchResult) -> VaacAdvisory | None:
    try:
        return parse_vaa(result)
    except ValueError as exc:
        log.warning("skipping unreadable VAA at %s: %s", result.url, exc)
        return None


def _dedupe(advisories: Iterable[VaacAdvisory]) -> list[VaacAdvisory]:
    seen: set[str] = set()
    unique: list[VaacAdvisory] = []
    for advisory in advisories:
        if advisory.provenance.source_id not in seen:
            seen.add(advisory.provenance.source_id)
            unique.append(advisory)
    return unique


def _clean(text: str) -> str:
    return " ".join(text.split())
