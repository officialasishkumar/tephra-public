"""JMA eruption observation reports (JMAXML), read with a parser and no model.

JMA publishes its volcano XML in an Atom feed (PDL 1.0; credit "Source: Japan Meteorological
Agency website", and a note that TEPHRA edited it). Two report types say that an eruption
happened, and only those become a ``Vona``:

* ``VFVO52`` 噴火に関する火山観測報 (eruption observation report): event time, plume height
  above sea level in feet, plume flow direction;
* ``VFVO56`` 噴火速報 (eruption flash report): the volcano and the time. No real example was
  available when this was written, so it is read with the same element names as VFVO52 and
  a report that lacks them is skipped, never guessed at.

Warnings and commentary (``VFVO50``, ``VFVO51``), ash fall forecasts (``VFVO53``) and plume
flow reports (``VFVO60``) hold no observation of ash and are not requested.

An eruption report with a plume or with the kind 噴火 sets ``ash_observed``: the eruption is
the observation, and a Vona that says ash was seen can only widen what TEPHRA considers
hazardous. JMA publishes alert levels, not aviation colour codes, so ``color_code`` is
UNKNOWN. The catalogue has no Japanese names, so volcanoes are matched by the names JMA
prints (``VOLCANO_NAMES``); an unlisted volcano is skipped.
"""

import logging
import re
import unicodedata
from datetime import datetime
from typing import Final

from lxml import etree

from tephra.config import FEED_CLOCK_SLACK
from tephra.feeds.base import FetchError, FetchResult, Source
from tephra.feeds.volcanoes import VolcanoCatalogue
from tephra.geo.units import COMPASS_POINTS, FT_PER_M
from tephra.models import AviationColor, FeedId, TephraModel, UtcDatetime, Volcano, Vona
from tephra.util import timeutil

__all__ = [
    "CREDIT",
    "ERUPTION_CODES",
    "JMA_EQVOL_URL",
    "JmaEntry",
    "fetch_jma_volcano",
    "parse_jma_entries",
    "parse_jma_report",
]

JMA_EQVOL_URL: Final = "https://www.data.jma.go.jp/developer/xml/feed/eqvol.xml"
ERUPTION_CODES: Final = frozenset({"VFVO52", "VFVO56"})
CREDIT: Final = "Source: Japan Meteorological Agency website (parsed by TEPHRA)"
MAX_ENTRIES: Final = 30
"""Newest entries read per poll; the high-frequency feed holds about a day of reports."""

VOLCANO_NAMES: Final[dict[str, str]] = {
    "桜島": "SAKURAJIMA",
    "阿蘇山": "ASO",
    "霧島山(新燃岳)": "SHINMOEDAKE",
    "雲仙岳": "UNZENDAKE",
    "諏訪之瀬島": "SUWANOSEJIMA",
    "口永良部島": "KUCHINOERABUJIMA",
    "薩摩硫黄島": "SATSUMA-IOJIMA",
    "九重山": "KUJUSAN",
}
"""JMA's printed volcano name (NFKC) -> catalogue alias. The first four were seen in JMA's
feed; the others are JMA's standard names and have not been seen in a fetched report."""
_PLUME_DIRECTIONS: Final[dict[str, str]] = {
    "北": "N", "北北東": "NNE", "北東": "NE", "東北東": "ENE",
    "東": "E", "東南東": "ESE", "南東": "SE", "南南東": "SSE",
    "南": "S", "南南西": "SSW", "南西": "SW", "西南西": "WSW",
    "西": "W", "西北西": "WNW", "北西": "NW", "北北西": "NNW",
}  # fmt: skip
"""JMA writes 噴煙の流向 as a kanji compass point: the direction the plume flows toward.
"直上" (straight up) and "不明" (unknown) name none."""
_SOURCE_TEXT: Final = {
    "VFVO52": "JMA eruption observation report",
    "VFVO56": "JMA eruption flash report",
}
_CODE_IN_URL: Final = re.compile(r"_(VFVO\d{2})_")
_ATOM: Final = "{http://www.w3.org/2005/Atom}"
_ERUPTION_KIND: Final = "噴火"

log = logging.getLogger(__name__)


class JmaEntry(TephraModel):
    """One Atom entry: a JMAXML document and when it was published."""

    url: str
    code: str
    updated: UtcDatetime


def parse_jma_entries(result: FetchResult) -> list[JmaEntry]:
    """Every entry of the Atom feed whose document is a JMAXML report with a ``VFVOnn`` code."""
    root = _parse_xml(result.content)
    entries: list[JmaEntry] = []
    for node in root.iter(f"{_ATOM}entry"):
        link = node.find(f"{_ATOM}link")
        updated = node.findtext(f"{_ATOM}updated")
        url = link.get("href") if link is not None else None
        code = _CODE_IN_URL.search(url or "")
        if not url or not updated or code is None:
            continue
        try:
            entries.append(
                JmaEntry(url=url, code=code.group(1), updated=timeutil.parse_iso(updated))
            )
        except ValueError:
            log.warning("skipping JMA feed entry with an unreadable time: %s", url)
    return entries


def parse_jma_report(result: FetchResult, catalogue: VolcanoCatalogue) -> Vona | None:
    """A Vona from a VFVO52 or VFVO56 document; None when it is not an eruption of a
    catalogue volcano. Raises ValueError for a document that is not JMAXML."""
    code = _CODE_IN_URL.search(result.url)
    if code is None or code.group(1) not in ERUPTION_CODES:
        return None
    root = _parse_xml(result.content)
    info = _first(root, "VolcanoInfo")
    event_id = _text(_first(root, "EventID"))
    if info is None or not event_id:
        raise ValueError("report has no VolcanoInfo or EventID")

    volcano = _volcano(info, catalogue)
    erupted_at = _event_time(info)
    issued_text = _text(_first(root, "ReportDateTime")) or _text(_first(root, "DateTime"))
    if volcano is None or erupted_at is None or not issued_text:
        return None
    plume = _first(root, "ColorPlume")
    top_ft = _plume_top_ft(plume)
    if top_ft is None and _text(_first(info, "Name", under="Kind")) != _ERUPTION_KIND:
        return None

    issued_at = timeutil.parse_iso(issued_text)
    direction = _text(_first(plume, "PlumeDirection")) if plume is not None else None
    deg = _plume_deg(direction)
    source_id = f"JMA-{code.group(1)}-{event_id}"
    return Vona(
        provenance=result.provenance(source_id, issued_at=issued_at),
        notice_number=None,
        volcano_name=volcano.name,
        volcano_code=None,
        issued_at=issued_at,
        color_code=AviationColor.UNKNOWN,
        ash_observed=True,
        cloud_top_ft=top_ft,
        cloud_top_m=round(top_ft / FT_PER_M) if top_ft is not None else None,
        movement_toward_deg=deg,
        movement_text=direction if direction else None,
        eruption_at=erupted_at,
        source_text=_SOURCE_TEXT[code.group(1)],
        remarks=_text(_first(root, "OtherObservation")) or None,
        raw_text=_raw_text(root, plume),
    )


async def fetch_jma_volcano(
    source: Source,
    catalogue: VolcanoCatalogue,
    *,
    since: datetime,
    known_urls: frozenset[str] = frozenset(),
) -> list[Vona]:
    """Eruption reports published from ``since`` up to now for catalogue volcanoes.

    A report stamped after now cannot be known now (a replay serves a feed saved later), and
    reports already read (``known_urls``) are not fetched again. A report that cannot be
    fetched or read is logged and skipped; a feed that cannot be read at all raises.
    """
    now = timeutil.now()
    listing = await source.fetch(JMA_EQVOL_URL, feed=FeedId.JMA_VOLCANO)
    entries = sorted(parse_jma_entries(listing), key=lambda entry: entry.updated, reverse=True)
    wanted = [
        entry
        for entry in entries
        if entry.code in ERUPTION_CODES
        and since <= entry.updated <= now + FEED_CLOCK_SLACK
        and entry.url not in known_urls
    ]
    vonas: list[Vona] = []
    for entry in wanted[:MAX_ENTRIES]:
        try:
            result = await source.fetch(entry.url, feed=FeedId.JMA_VOLCANO)
            vona = parse_jma_report(result, catalogue)
        except (FetchError, ValueError) as exc:
            log.warning("skipping JMA report %s: %s", entry.url, exc)
            continue
        if vona is not None:
            vonas.append(vona)
    return vonas


# --- reading the document ---------------------------------------------------------------


def _parse_xml(content: bytes) -> etree._Element:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    try:
        return etree.fromstring(content, parser)
    except etree.XMLSyntaxError as exc:
        raise ValueError(f"not XML: {exc}") from exc


def _first(
    root: etree._Element | None, name: str, *, under: str | None = None
) -> etree._Element | None:
    """First element called ``name`` in document order, ignoring namespaces; with ``under``
    it must sit directly below an element of that name."""
    if root is None:
        return None
    for element in root.iter():
        if not isinstance(element.tag, str) or etree.QName(element).localname != name:
            continue
        parent = element.getparent()
        if under is None or (parent is not None and etree.QName(parent).localname == under):
            return element
    return None


def _text(element: etree._Element | None) -> str:
    return "" if element is None or element.text is None else element.text.strip()


def _volcano(info: etree._Element, catalogue: VolcanoCatalogue) -> Volcano | None:
    name = unicodedata.normalize("NFKC", _text(_first(_first(info, "Area"), "Name")))
    alias = VOLCANO_NAMES.get(name)
    return catalogue.resolve(alias) if alias else None


def _event_time(info: etree._Element) -> datetime | None:
    text = _text(_first(info, "EventDateTimeUTC")) or _text(_first(info, "EventDateTime"))
    return timeutil.parse_iso(text) if text else None


def _plume_top_ft(plume: etree._Element | None) -> int | None:
    element = _first(plume, "PlumeHeightAboveSeaLevel")
    if element is None:
        return None
    try:
        value = float(_text(element))
    except ValueError:
        return None
    unit = (element.get("unit") or "").upper()
    if unit == "FT":
        return round(value)
    if unit == "M":
        return round(value * FT_PER_M)
    return None


def _plume_deg(direction: str | None) -> float | None:
    point = _PLUME_DIRECTIONS.get(direction or "")
    return COMPASS_POINTS.index(point) * 22.5 if point else None


def _raw_text(root: etree._Element, plume: etree._Element | None) -> str:
    lines = [_text(_first(_first(root, "Headline"), "Text"))]
    for name in ("PlumeHeightAboveCrater", "PlumeHeightAboveSeaLevel", "PlumeDirection"):
        element = _first(plume, name)
        if element is not None and element.get("description"):
            lines.append(str(element.get("description")))
    lines.append(_text(_first(root, "OtherObservation")))
    lines.append(CREDIT)
    return "\n".join(line for line in lines if line)
