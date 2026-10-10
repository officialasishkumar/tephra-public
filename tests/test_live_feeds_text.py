"""Live format checks for the text feeds: each test polls one public source once.

Deselected by default; run them with
``uv run pytest -m network tests/test_live_feeds_text.py``. The data change all the time, so
the checks assert structure and units, never values. MAGMA is never fetched here: its
robots.txt disallows crawling (research/05).
"""

import json
import re
from collections.abc import AsyncIterator, Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tephra.feeds.base import FetchResult, HttpSource
from tephra.feeds.sigmet import SIGMET_PARAMS, SIGMET_URL, find_dm_points, parse_sigmets
from tephra.feeds.taf import assess_alternate, fetch_metars, fetch_tafs
from tephra.feeds.vaac import (
    DARWIN_BULLETIN_URLS,
    TOKYO_LIST_URL,
    fetch_vaas,
    parse_vaa,
    parse_vaac_list,
)
from tephra.models import FeedId, GeoPolygon, Sigmet, VaacAdvisory, VaacCentre
from tephra.util import timeutil

pytestmark = pytest.mark.network

STATIONS = ("RJFF", "RJFK", "RPLL", "WAAA", "WADD", "WARR", "WIII", "WILL", "WSSS")
SIGMET_ID = re.compile(r"^SIGMET:[A-Z]{4}:[A-Z0-9_]+:\d{8}T\d{4}Z$")
VAA_ID = re.compile(r"^VAA:(TOKYO|DARWIN):[A-Z0-9_]+:\d{4}/\d+$")
VAAC_LINE = re.compile(r"^VAAC:\s*([A-Z]+)", re.MULTILINE)


class Recorder:
    """Passes fetches through and keeps every result, so one poll can be inspected."""

    def __init__(self, inner: HttpSource) -> None:
        self.inner = inner
        self.results: list[FetchResult] = []

    async def fetch(
        self, url: str, *, feed: FeedId, params: Mapping[str, str] | None = None
    ) -> FetchResult:
        result = await self.inner.fetch(url, feed=feed, params=params)
        self.results.append(result)
        return result

    async def aclose(self) -> None:
        await self.inner.aclose()


@pytest.fixture
async def source(tmp_path: Path) -> AsyncIterator[HttpSource]:
    http = HttpSource(cache_dir=tmp_path)
    try:
        yield http
    finally:
        await http.aclose()


def assert_recent(at: datetime, now: datetime, *, days: float) -> None:
    assert now - timedelta(days=days) <= at <= now + timedelta(hours=2), at


def assert_ring(polygon: GeoPolygon) -> None:
    ring = polygon.coordinates[0]
    assert len(ring) >= 4
    assert ring[0] == ring[-1]
    for lon, lat in ring:
        assert -360 <= lon <= 360  # AWC runs past 180 to keep an antimeridian ring continuous
        assert -90 <= lat <= 90


def assert_same_ring(text_polygon: GeoPolygon, json_coords: list[dict[str, Any]]) -> None:
    """The degree-minute reading of the raw text matches AWC's decimal ``coords``."""
    ring = text_polygon.coordinates[0]
    for (lon, lat), vertex in zip(ring, json_coords, strict=True):
        # The same meridian modulo 360: AWC writes W17953 as 180.117 across the antimeridian.
        assert (lon - vertex["lon"] + 180) % 360 - 180 == pytest.approx(0, abs=1e-3)
        assert lat == pytest.approx(vertex["lat"], abs=1e-3)


async def test_live_va_sigmets(source: HttpSource) -> None:
    result = await source.fetch(SIGMET_URL, feed=FeedId.SIGMET, params=SIGMET_PARAMS)
    now = timeutil.now()
    records = [r for r in result.json() if isinstance(r, dict) and r.get("hazard") == "VA"]
    sigmets = parse_sigmets(result)
    unique = {(r.get("rawSigmet"), r.get("seriesId")) for r in records}
    assert len([s for s in sigmets if "AREA" not in s.series_id]) == len(unique)

    for sigmet in sigmets:
        assert SIGMET_ID.match(sigmet.provenance.source_id), sigmet.provenance.source_id
        assert re.fullmatch(r"[A-Z]{4}", sigmet.fir_id)
        assert sigmet.valid_from < sigmet.valid_to <= sigmet.valid_from + timedelta(hours=12)
        assert_recent(sigmet.valid_from, now, days=1)
        assert sigmet.provenance.issued_at is not None
        assert sigmet.base_ft >= 0
        assert sigmet.top_ft is None or sigmet.top_ft > sigmet.base_ft
        if sigmet.polygon is not None:
            assert_ring(sigmet.polygon)
        assert sigmet.raw_text

    for record in records:
        main = _main_record(sigmets, record)
        top = record.get("top")
        if isinstance(top, int | float):
            assert main.top_ft == round(top)  # AWC's levels are feet; so are TEPHRA's
        coords = record.get("coords") or []
        if not coords or not isinstance(coords[0], dict):
            continue
        if len({(vertex["lat"], vertex["lon"]) for vertex in coords}) < 3:
            continue  # a SIGMET placed at a single point ("N3140E13032 FL080 STNR")
        assert main.polygon is not None
        from_text = _main_record(parse_sigmets(_without_coords(result, record)), record)
        if from_text.polygon is None:
            continue  # the text gives no area: AWC drew its own circle around the PSN
        if len(from_text.polygon.coordinates[0]) == len(coords):
            assert_same_ring(from_text.polygon, coords)


def _main_record(sigmets: list[Sigmet], record: Mapping[str, Any]) -> Sigmet:
    """The record AWC sent (not an extra ``AREA n`` split off its text)."""
    raw = str(record["rawSigmet"]).replace("\r", "").strip()
    series = str(record["seriesId"]).strip()
    return next(s for s in sigmets if s.series_id == series and s.raw_text == raw)


def _without_coords(result: FetchResult, record: Mapping[str, Any]) -> FetchResult:
    content = json.dumps([{**record, "coords": None}]).encode()
    return FetchResult(
        feed=result.feed,
        url=result.url,
        status_code=result.status_code,
        content=content,
        content_type=result.content_type,
        fetched_at=result.fetched_at,
        sha256=result.sha256,
    )


async def test_live_tokyo_list_and_latest_text(source: HttpSource) -> None:
    listing = await source.fetch(TOKYO_LIST_URL, feed=FeedId.VAAC_TOKYO)
    now = timeutil.now()
    items = parse_vaac_list(listing, VaacCentre.TOKYO)
    assert items, "the Tokyo list keeps about five weeks of advisories"
    for item in items:
        assert item.url.startswith("https://ds.data.jma.go.jp/svd/vaac/data/TextData/")
        assert item.volcano_name
        assert_recent(item.issued_at, now, days=120)
    assert [item.issued_at for item in items] == sorted(
        (item.issued_at for item in items), reverse=True
    )

    newest = items[0]
    vaa = parse_vaa(await source.fetch(newest.url, feed=FeedId.VAAC_TOKYO))
    if vaa is None:
        assert newest.volcano_name.upper() in {"NOTICE", "TEST"}
        return
    assert vaa.vaac is VaacCentre.TOKYO
    assert vaa.issued_at == newest.issued_at
    assert vaa.advisory_nr == newest.advisory_nr
    assert_advisory(vaa, now)


async def test_live_darwin_tgftp_slots(source: HttpSource) -> None:
    recorder = Recorder(source)
    now = timeutil.now()
    since = now - timedelta(hours=24)
    advisories = await fetch_vaas(recorder, FeedId.VAAC_DARWIN, since=since)
    slots = [result for result in recorder.results if result.url in DARWIN_BULLETIN_URLS]
    assert [result.url for result in slots] == list(DARWIN_BULLETIN_URLS)

    for result in slots:
        text = result.text()
        assert text.lstrip().startswith("FV"), result.url  # a WMO bulletin, not an error page
        vaac = VAAC_LINE.search(text)
        assert vaac is not None, result.url
        if vaac.group(1) not in {centre.value for centre in VaacCentre}:
            continue  # another VAAC's bulletin in a Darwin slot, which parse_vaa refuses
        vaa = parse_vaa(result)
        if vaa is not None:  # None: a test, exercise or notice bulletin
            assert_advisory(vaa, now)
    for advisory in advisories:
        assert advisory.issued_at >= since  # a slot's stale bulletin never comes back


def assert_advisory(vaa: VaacAdvisory, now: datetime) -> None:
    assert VAA_ID.match(vaa.provenance.source_id), vaa.provenance.source_id
    assert_recent(vaa.issued_at, now, days=120)
    assert vaa.provenance.valid_to == vaa.valid_until()
    assert vaa.valid_until() > vaa.issued_at
    if vaa.next_advisory_at is not None:
        assert vaa.issued_at < vaa.next_advisory_at <= vaa.issued_at + timedelta(hours=12)
    else:
        assert vaa.final or vaa.next_advisory_text is None
    steps = [vaa.observation] if vaa.observation is not None else []
    steps += vaa.forecasts
    assert {step.offset_h for step in vaa.forecasts} <= {6, 12, 18}
    for step in steps:
        assert abs(step.valid_at - vaa.issued_at) <= timedelta(hours=20)
        for layer in step.layers:
            assert 0 <= layer.base_ft < layer.top_ft <= 70_000
            assert layer.top_ft % 100 == 0  # flight levels, never feet read as levels
            if layer.polygon is not None:
                assert_ring(layer.polygon)
                assert len(find_dm_points(step.text)) >= len(layer.polygon.coordinates[0]) - 1


async def test_live_tafs_and_metars(source: HttpSource) -> None:
    tafs = await fetch_tafs(source, STATIONS)
    metars = await fetch_metars(source, STATIONS)
    now = timeutil.now()
    assert tafs
    assert metars
    for taf in tafs:
        assert taf.icao in STATIONS
        assert taf.icao in taf.raw_text
        assert_recent(taf.issued_at, now, days=2)
        assert taf.valid_from < taf.valid_to <= taf.valid_from + timedelta(hours=30)
        assert taf.periods
        for period in taf.periods:
            assert taf.valid_from <= period.valid_from < period.valid_to <= taf.valid_to
            assert period.visibility_m is None or 0 <= period.visibility_m <= 9999
            assert period.ceiling_ft is None or 0 <= period.ceiling_ft <= 50_000
            assert all(token == token.upper() for token in period.weather)
        check = assess_alternate(taf, taf.valid_from + (taf.valid_to - taf.valid_from) / 2)
        assert check.icao == taf.icao
        assert check.taf_source_id == taf.provenance.source_id
        assert all(reason == reason.upper() for reason in check.reasons)
    for metar in metars:
        assert metar.icao in STATIONS
        assert metar.raw_text.split()[0] in {"METAR", "SPECI"}
        assert_recent(metar.observed_at, now, days=1)
        assert metar.visibility_m is None or metar.visibility_m >= 0
