"""Live shapes of the feeds-geo sources: one real request each, read by TEPHRA's parsers.

Deselected by default; run with ``uv run pytest -m network tests/test_live_feeds_geo.py``.
The assertions check structure, never values: traffic, winds and daylight change by the
minute. Every request goes through :class:`HttpSource`, so the adsb.lol call keeps the
configured spacing and 429 back-off, and nothing is cached outside ``tmp_path``.
"""

import io
from collections.abc import AsyncIterator
from datetime import timedelta
from itertools import pairwise
from pathlib import Path

import pytest
from PIL import Image

from tephra.config import Settings
from tephra.feeds.adsb import fetch_aircraft
from tephra.feeds.base import HttpSource
from tephra.feeds.satellite import FRAME_CAPTION_SUFFIX, fetch_frames
from tephra.feeds.volcanoes import load_volcanoes
from tephra.feeds.winds import fetch_winds
from tephra.models import PRESSURE_LEVEL_FL, AdsbQueryPoint, FeedId, FrameProduct
from tephra.util import timeutil

pytestmark = pytest.mark.network

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SEMERU_ID = "263300"
SEMERU_LAT, SEMERU_LON = -8.108, 112.922


@pytest.fixture
async def source(tmp_path: Path) -> AsyncIterator[HttpSource]:
    live = HttpSource.from_settings(Settings(_env_file=None, cache_dir=tmp_path))
    yield live
    await live.aclose()


async def test_adsb_lol_point(source: HttpSource) -> None:
    point = AdsbQueryPoint(lat=SEMERU_LAT, lon=SEMERU_LON, radius_nm=250)
    (snapshot,) = await fetch_aircraft(source, [point])

    provenance = snapshot.provenance
    assert snapshot.query == point
    assert provenance.feed is FeedId.ADSB
    assert not provenance.stale
    assert provenance.source_id.startswith("ADSB:-8.108:112.922:")
    assert provenance.issued_at is not None
    assert abs((provenance.fetched_at - provenance.issued_at).total_seconds()) < 120
    for aircraft in snapshot.aircraft:
        assert aircraft.hex == aircraft.hex.strip().lower()
        assert -90 <= aircraft.lat <= 90
        assert -180 <= aircraft.lon <= 180
        assert aircraft.source_id == provenance.source_id
        assert timedelta(0) <= provenance.issued_at - aircraft.observed_at < timedelta(minutes=5)
        assert aircraft.track_deg is None or 0 <= aircraft.track_deg < 360
        assert aircraft.gs_kt is None or aircraft.gs_kt >= 0


async def test_open_meteo_pressure_level_winds(source: HttpSource) -> None:
    profiles = await fetch_winds(source, SEMERU_LAT, SEMERU_LON)

    times = [profile.valid_at for profile in profiles]
    assert len(times) >= 24
    assert all(later - earlier == timedelta(hours=1) for earlier, later in pairwise(times))
    now = timeutil.now()
    assert times[0] <= now < times[-1]
    assert times[-1] - now > timedelta(hours=20)
    for profile in profiles:
        assert profile.valid_at.utcoffset() == timedelta(0)
        assert profile.provenance.source_id.startswith("WINDS:-8.11:112.92:")
        assert [level.pressure_hpa for level in profile.levels] == sorted(
            PRESSURE_LEVEL_FL, reverse=True
        )
        for level in profile.levels:
            assert level.flight_level == PRESSURE_LEVEL_FL[level.pressure_hpa]
            assert 0 <= level.speed_kt < 400
            assert 0 <= level.from_deg < 360


async def test_satellite_frames_around_semeru(source: HttpSource) -> None:
    semeru = load_volcanoes(DATA_DIR).get(SEMERU_ID)
    assert semeru is not None
    frames = await fetch_frames(source, semeru)

    products = [frame.product for frame, _ in frames]
    assert products[:2] == [FrameProduct.B13_IR, FrameProduct.DUST_RGB]  # se3, day and night
    assert products[2:] in ([], [FrameProduct.TRUE_COLOR])  # NICT only in local daylight
    now = timeutil.now()
    for frame, png in frames:
        assert frame.volcano_id == SEMERU_ID
        assert frame.bbox is None
        assert frame.caption.endswith(FRAME_CAPTION_SUFFIX)
        assert not frame.provenance.stale
        assert timedelta(minutes=5) < now - frame.observed_at < timedelta(hours=3)
        with Image.open(io.BytesIO(png)) as image:
            assert image.format == "PNG"
            assert image.size == (frame.width_px, frame.height_px)
            assert min(image.size) > 50
