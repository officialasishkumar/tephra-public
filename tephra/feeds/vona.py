"""MAGMA Indonesia VONAs, read from the public HTML (the JSON API needs a token).

The list page links each notice with a signed URL; the unsigned detail URL answers 403, so
detail pages are always fetched with the link exactly as listed. MAGMA prints feet as metres
x 3.2, so heights are read from the metre figures and converted here.
"""

import logging
import re
from datetime import UTC, datetime
from typing import Final
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from tephra.feeds.base import FetchError, FetchResult, Source
from tephra.geo.units import compass_to_deg, m_to_ft
from tephra.models import (
    AviationColor,
    FeedId,
    TephraModel,
    UtcDatetime,
    Vona,
    make_source_id,
    source_slug,
)
from tephra.util import timeutil

__all__ = [
    "VONA_LIST_URL",
    "VonaListItem",
    "fetch_vonas",
    "parse_vona_list",
    "parse_vona_page",
]

VONA_LIST_URL: Final = "https://magma.esdm.go.id/v1/vona"

log = logging.getLogger(__name__)

_MAGMA_ID = re.compile(r"/vona/(\d+)")
_SLASH_DTG = re.compile(r"\d{8}\s*/\s*\d{4}\s*Z", re.IGNORECASE)
_LIST_TIME = re.compile(r"(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})(?::(\d{2}))?\s*UTC")
_NOT_OBSERVED = re.compile(r"\bnot\s+(?:be\s+)?observed\b", re.IGNORECASE)
_ASH_MENTION = re.compile(r"\bash\b|\bash[- ]cloud\b", re.IGNORECASE)
_TOP_ASL_M = re.compile(r"(\d[\d,.]*)\s*M\s*\)?\s*above\s+sea\s+level", re.IGNORECASE)
_ABOVE_SUMMIT_M = re.compile(r"(\d[\d,.]*)\s*M\s*\)?\s*above\s+(?:the\s+)?summit", re.IGNORECASE)
_METRES = re.compile(r"(\d[\d,.]*)\s*M\b", re.IGNORECASE)
_MOVING = re.compile(r"\b(?:ash\s+cloud|ash|it)\s+(?:is\s+)?moving\s+(?P<dir>[^.]+)", re.IGNORECASE)
_HEIGHT_SOURCE = re.compile(r"source\s+of\s+height\s+data\s*:\s*([^.]+)", re.IGNORECASE)
_ERUPTION_TIME = re.compile(r"\bat\s+(\d{4})\s*UTC\b", re.IGNORECASE)
_NOTICE_CODE = re.compile(r"^\d{4}([A-Z]+)\d+$")
_NAME_NUMBER = re.compile(r"^(.*?)\s*\((\d+)\)\s*$")

# Rows 15-16 (contacts, next-notice boilerplate) carry office contact details and no
# hazard information, so the stored raw text stops at the remarks.
_LAST_HAZARD_ROW = 14


class VonaListItem(TephraModel):
    """One entry of the MAGMA VONA list page."""

    url: str
    magma_id: int
    volcano_name: str
    issued_at: UtcDatetime
    color_code: AviationColor
    summary: str | None = None


def parse_vona_list(result: FetchResult) -> list[VonaListItem]:
    soup = BeautifulSoup(result.text(), "lxml")
    items: list[VonaListItem] = []
    for node in soup.select("div.timeline-item"):
        if "timeline-day" in (node.get("class") or []):
            continue
        try:
            item = _list_item(node, result.url)
        except ValueError as exc:
            log.warning("skipping unreadable MAGMA list entry: %s", exc)
            continue
        if item is not None:
            items.append(item)
    return items


def parse_vona_page(result: FetchResult, item: VonaListItem | None = None) -> Vona:
    soup = BeautifulSoup(result.text(), "lxml")
    rows = _detail_rows(soup)
    title = _title_parts(soup)
    if not rows and title is None:
        raise ValueError("page has no VONA table")

    issued_text = rows.get("issued") or (title[2] if title else None)
    if issued_text:
        issued_at = timeutil.parse_slash_dtg(issued_text)
    elif item is not None:
        issued_at = item.issued_at
    else:
        raise ValueError("VONA has no issue time")

    volcano_text = rows.get("volcano") or (title[1] if title else None)
    name_match = _NAME_NUMBER.match(volcano_text or "")
    volcano_name = (name_match.group(1) if name_match else volcano_text) or (
        item.volcano_name if item else None
    )
    if not volcano_name:
        raise ValueError("VONA names no volcano")

    summary = rows.get("volcanic activity summary")
    height = rows.get("volcanic cloud height")
    cloud_info = rows.get("other volcanic cloud information")
    notice_number = rows.get("notice number")
    cloud_top_m = _cloud_top_m(height, rows.get("summit elevation"))
    ash_observed = _ash_observed(summary, height, cloud_info, cloud_top_m)
    movement_text = _movement_text(cloud_info, height)
    source_id = make_source_id("VONA", source_slug(volcano_name), timeutil.compact(issued_at))
    return Vona(
        provenance=result.provenance(source_id, issued_at=issued_at),
        magma_id=_magma_id(result.url) or (item.magma_id if item else None),
        notice_number=notice_number,
        volcano_name=volcano_name,
        volcano_code=_volcano_code(notice_number),
        issued_at=issued_at,
        color_code=_color(rows.get("current aviation colour code"), title, item),
        ash_observed=ash_observed,
        cloud_top_ft=round(m_to_ft(cloud_top_m)) if ash_observed and cloud_top_m else None,
        cloud_top_m=cloud_top_m if ash_observed else None,
        movement_toward_deg=_movement_deg(movement_text) if ash_observed else None,
        movement_text=movement_text,
        eruption_at=_eruption_at(summary, issued_at),
        source_text=_height_source(height) or rows.get("source"),
        remarks=rows.get("remarks"),
        raw_text=_raw_text(soup) or (item.summary if item and item.summary else volcano_name),
    )


async def fetch_vonas(
    source: Source,
    *,
    since: datetime,
    known_urls: frozenset[str] = frozenset(),
    max_pages: int = 1,
) -> list[Vona]:
    """New VONAs issued at or after ``since``; detail pages already known are not fetched."""
    vonas: list[Vona] = []
    for page in range(1, max_pages + 1):
        params = None if page == 1 else {"page": str(page)}
        listing = await source.fetch(VONA_LIST_URL, feed=FeedId.VONA, params=params)
        items = parse_vona_list(listing)
        for item in items:
            if item.issued_at < since or item.url in known_urls:
                continue
            vona = await _fetch_detail(source, item)
            if vona is not None:
                vonas.append(vona)
        if not items or min(item.issued_at for item in items) < since:
            break
    return vonas


async def _fetch_detail(source: Source, item: VonaListItem) -> Vona | None:
    try:
        result = await source.fetch(item.url, feed=FeedId.VONA)
        return parse_vona_page(result, item)
    except (FetchError, ValueError) as exc:
        log.warning("skipping VONA %s (%s): %s", item.magma_id, item.volcano_name, exc)
        return None


# --- list page --------------------------------------------------------------------------


def _list_item(node: Tag, base_url: str) -> VonaListItem | None:
    link = node.select_one("a.card-link[href]") or _find_vona_link(node)
    if link is None:
        return None
    url = urljoin(base_url, str(link["href"]))
    magma_id = _magma_id(url)
    if magma_id is None:
        raise ValueError(f"no VONA id in {url}")
    title_node = node.select_one(".timeline-title")
    title = _clean(title_node.get_text(" ")) if title_node else ""
    name, _, title_dtg = title.rpartition(" - ")
    issued_at = _list_time(node, title_dtg)
    button = node.select_one(".timeline-time a.btn") or node.select_one("a.btn")
    text_node = node.select_one(".timeline-text")
    return VonaListItem(
        url=url,
        magma_id=magma_id,
        volcano_name=name.strip() or title,
        issued_at=issued_at,
        color_code=_color_word(button.get_text() if button else ""),
        summary=(_clean(text_node.get_text(" ")) or None) if text_node else None,
    )


def _find_vona_link(node: Tag) -> Tag | None:
    for anchor in node.find_all("a", href=True):
        if _MAGMA_ID.search(str(anchor["href"])):
            return anchor
    return None


def _list_time(node: Tag, title_dtg: str) -> datetime:
    if _SLASH_DTG.fullmatch(title_dtg.strip()):
        return timeutil.parse_slash_dtg(title_dtg)
    small = node.select_one(".timeline-time small")
    match = _LIST_TIME.search(small.get_text() if small else "")
    if match is None:
        raise ValueError("entry has no issue time")
    year, month, day, hour, minute = (int(part) for part in match.groups()[:5])
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


# --- detail page ------------------------------------------------------------------------


def _detail_rows(soup: BeautifulSoup) -> dict[str, str]:
    """Label (lower case) -> value text for each ``(n) | Label | : | value`` table row."""
    rows: dict[str, str] = {}
    for row in soup.select("table tr"):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 4:
            continue
        label = _clean(cells[1].get_text(" ")).lower()
        if label and label not in rows:
            rows[label] = _clean(cells[3].get_text(" "))
    return rows


def _title_parts(soup: BeautifulSoup) -> tuple[str, str, str] | None:
    """``ORANGE | SEMERU | 20261008/2103Z`` from the page title."""
    if soup.title is None:
        return None
    parts = [part.strip() for part in soup.title.get_text().split("|")]
    if len(parts) != 3 or not _SLASH_DTG.fullmatch(parts[2]):
        return None
    return parts[0], parts[1], parts[2]


def _raw_text(soup: BeautifulSoup) -> str:
    lines: list[str] = []
    for row in soup.select("table tr"):
        cells = row.find_all("td", recursive=False)
        if not cells:
            continue
        number = _clean(cells[0].get_text()).strip("()")
        if number.isdigit() and int(number) > _LAST_HAZARD_ROW:
            continue
        if len(cells) >= 4:
            lines.append(f"{_clean(cells[1].get_text(' '))}: {_clean(cells[3].get_text(' '))}")
        elif len(cells) >= 2:
            lines.append(_clean(cells[1].get_text(" ")))
    return "\n".join(line for line in lines if line.strip(": "))


def _cloud_top_m(height: str | None, summit: str | None) -> int | None:
    if not height:
        return None
    match = _TOP_ASL_M.search(height)
    if match is not None:
        return _int(match.group(1))
    above = _ABOVE_SUMMIT_M.search(height)
    summit_match = _METRES.search(summit or "")
    if above is not None and summit_match is not None:
        above_m, summit_m = _int(above.group(1)), _int(summit_match.group(1))
        if above_m is not None and summit_m is not None:
            return above_m + summit_m
    return None


def _ash_observed(
    summary: str | None, height: str | None, cloud_info: str | None, cloud_top_m: int | None
) -> bool:
    texts = [text for text in (height, cloud_info) if text]
    if any(_NOT_OBSERVED.search(text) for text in texts):
        return False
    if cloud_top_m is not None:
        return True
    return any(_ASH_MENTION.search(text) for text in (summary or "", *texts))


def _movement_text(cloud_info: str | None, height: str | None) -> str | None:
    for text in (cloud_info, height):
        match = _MOVING.search(text or "")
        if match is not None:
            return _clean(match.group(0))
    return None


def _movement_deg(movement_text: str | None) -> float | None:
    if not movement_text:
        return None
    match = _MOVING.search(movement_text)
    return compass_to_deg(match.group("dir") if match else movement_text)


def _eruption_at(summary: str | None, issued_at: datetime) -> datetime | None:
    match = _ERUPTION_TIME.search(summary or "")
    if match is None:
        return None
    return timeutil.parse_hhmmz(match.group(1), issued_at)


def _height_source(height: str | None) -> str | None:
    match = _HEIGHT_SOURCE.search(height or "")
    return _clean(match.group(1)) if match else None


def _volcano_code(notice_number: str | None) -> str | None:
    match = _NOTICE_CODE.match((notice_number or "").strip())
    return match.group(1) if match else None


def _color(
    value: str | None, title: tuple[str, str, str] | None, item: VonaListItem | None
) -> AviationColor:
    for candidate in (value, title[0] if title else None):
        color = _color_word(candidate or "")
        if color is not AviationColor.UNKNOWN:
            return color
    return item.color_code if item else AviationColor.UNKNOWN


def _color_word(text: str) -> AviationColor:
    try:
        return AviationColor(text.strip().upper())
    except ValueError:
        return AviationColor.UNKNOWN


def _magma_id(url: str) -> int | None:
    match = _MAGMA_ID.search(url)
    return int(match.group(1)) if match else None


def _int(text: str) -> int | None:
    digits = text.replace(",", "")
    try:
        return round(float(digits))
    except ValueError:
        return None


def _clean(text: str) -> str:
    return " ".join(text.split())
