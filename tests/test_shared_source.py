"""The one live source every hosted airline fetches through (SPEC-FINAL §3.8): a response
fetched seconds ago is handed out again under its own time, every request goes through one
client with one per-host spacing, and closing it closes nothing."""

import asyncio
import itertools
import time
from pathlib import Path

import httpx
import pytest

from tephra.config import Settings
from tephra.feeds.base import FetchError, HttpSource, SharedHttpSource
from tephra.models import FeedId

SIGMETS = "https://aviationweather.gov/api/data/isigmet?format=json&hazard=va"
ADSB_A = "https://api.adsb.lol/v2/point/-8.1/112.9/250"
ADSB_B = "https://api.adsb.lol/v2/point/-1.7/127.9/250"


class Upstream:
    """A mock transport that counts requests and notes when each one arrived."""

    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.requests: list[tuple[str, float]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append((str(request.url), time.monotonic()))
        return httpx.Response(self.status, json={"n": len(self.requests)})


def inner(tmp_path: Path, upstream: Upstream, *, adsb_gap_s: float = 0.0) -> HttpSource:
    return HttpSource(
        cache_dir=tmp_path,
        retries=0,
        host_intervals_s={"api.adsb.lol": adsb_gap_s},
        transport=httpx.MockTransport(upstream.handler),
    )


async def test_a_fetch_within_the_window_is_the_same_response_under_its_own_time(
    tmp_path: Path,
) -> None:
    upstream = Upstream()
    shared = SharedHttpSource(inner(tmp_path, upstream), memo_s=0.2)
    try:
        first = await shared.fetch(SIGMETS, feed=FeedId.SIGMET)
        again = await shared.fetch(SIGMETS, feed=FeedId.SIGMET)
        assert again is first
        assert (again.fetched_at, again.stale, again.content) == (
            first.fetched_at,
            first.stale,
            first.content,
        )
        assert len(upstream.requests) == 1
        await asyncio.sleep(0.25)
        later = await shared.fetch(SIGMETS, feed=FeedId.SIGMET)
        assert later.fetched_at > first.fetched_at
        assert len(upstream.requests) == 2
    finally:
        await shared.inner.aclose()


async def test_concurrent_callers_share_one_request_and_one_host_spacing(tmp_path: Path) -> None:
    upstream = Upstream()
    shared = SharedHttpSource(inner(tmp_path, upstream, adsb_gap_s=0.2))
    try:
        same = await asyncio.gather(*(shared.fetch(ADSB_A, feed=FeedId.ADSB) for _ in range(3)))
        assert len({id(result) for result in same}) == 1
        assert len(upstream.requests) == 1
        await asyncio.gather(
            shared.fetch(ADSB_B, feed=FeedId.ADSB),
            shared.fetch(f"{ADSB_B}?x=1", feed=FeedId.ADSB),
        )
        times = [at for _, at in upstream.requests]
        assert len(times) == 3
        assert all(b - a >= 0.18 for a, b in itertools.pairwise(times))
    finally:
        await shared.inner.aclose()


async def test_the_window_is_never_longer_than_half_the_feeds_cadence(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, cadence_sigmet_s=30)
    shared = SharedHttpSource(inner(tmp_path, Upstream()), memo_s=25.0, settings=settings)
    try:
        assert shared._window(FeedId.SIGMET) == 15.0
        assert SharedHttpSource(shared.inner, memo_s=5.0, settings=settings)._window(
            FeedId.SIGMET
        ) == pytest.approx(5.0)
    finally:
        await shared.inner.aclose()


async def test_a_failed_fetch_is_not_kept(tmp_path: Path) -> None:
    upstream = Upstream(status=503)
    shared = SharedHttpSource(inner(tmp_path, upstream))
    try:
        for _ in range(2):
            with pytest.raises(FetchError):
                await shared.fetch(SIGMETS, feed=FeedId.SIGMET)
        assert len(upstream.requests) == 2
    finally:
        await shared.inner.aclose()


async def test_closing_the_shared_source_closes_nothing(tmp_path: Path) -> None:
    upstream = Upstream()
    shared = SharedHttpSource(inner(tmp_path, upstream), memo_s=0.0)
    await shared.aclose()
    result = await shared.fetch(SIGMETS, feed=FeedId.SIGMET)
    assert result.status_code == 200
    await shared.inner.aclose()  # the registry's close, at shutdown
    with pytest.raises(RuntimeError, match="client has been closed"):
        await shared.fetch(f"{SIGMETS}&again=1", feed=FeedId.SIGMET)
