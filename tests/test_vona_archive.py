"""VONAs from archived MAGMA list pages: the census saved list pages on 9 Oct, so a replay of
late September sees pages that also list later notices, and no detail pages at all."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tephra.feeds.base import FetchError, FetchResult, build_url
from tephra.feeds.vona import VONA_LIST_URL, fetch_vonas
from tephra.models import AviationColor, FeedId
from tephra.replay.cases import ReplaySource, case_path, load_case
from tephra.util.hashing import sha256_bytes
from tephra.util.timeutil import FixedClock, use_clock

FIXTURES = Path(__file__).parent / "fixtures" / "magma"
PAGES = {
    1: FIXTURES / "vona_list_p010_20261009.html",  # 28 Sep 13:06Z back to 26 Sep 17:21Z
    2: FIXTURES / "vona_list_p011_20261009.html",  # 26 Sep 17:15Z back to 25 Sep 02:48Z
    3: FIXTURES / "vona_list_p012_20261009.html",  # 24 Sep 23:56Z back to 21 Sep 16:01Z
}
SAVED_AT = datetime(2026, 10, 9, 19, 34, tzinfo=UTC)
CLOCK = datetime(2026, 9, 25, 16, 0, tzinfo=UTC)
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class ArchivedListing:
    """Serves saved list pages for ``?page=n`` and fails every detail page, like a replay."""

    def __init__(self) -> None:
        self.requested: list[str] = []

    async def fetch(
        self, url: str, *, feed: FeedId, params: Mapping[str, str] | None = None
    ) -> FetchResult:
        full_url = build_url(url, params)
        self.requested.append(full_url)
        page = int((params or {}).get("page", "1"))
        if url != VONA_LIST_URL or page not in PAGES:
            raise FetchError(full_url, feed, "not recorded")
        content = PAGES[page].read_bytes()
        return FetchResult(
            feed=feed,
            url=full_url,
            status_code=200,
            content=content,
            content_type="text/html",
            fetched_at=SAVED_AT,
            sha256=sha256_bytes(content),
            replay=True,
        )

    async def aclose(self) -> None:
        return None


async def read(**kwargs: object) -> tuple[list, ArchivedListing]:
    source = ArchivedListing()
    with use_clock(FixedClock(CLOCK)):
        vonas = await fetch_vonas(source, since=CLOCK - timedelta(hours=24), **kwargs)
    return vonas, source


async def test_notices_issued_after_the_clock_are_never_read() -> None:
    vonas, _ = await read(max_pages=2)
    assert vonas
    assert all(CLOCK - timedelta(hours=24) <= vona.issued_at <= CLOCK for vona in vonas)


async def test_a_page_of_later_notices_does_not_use_up_the_page_budget() -> None:
    vonas, source = await read(max_pages=1)
    assert source.requested[:2] == [VONA_LIST_URL, build_url(VONA_LIST_URL, {"page": "2"})]
    assert any(vona.magma_id == 22713 for vona in vonas)


async def test_a_card_gives_the_notice_text_when_the_detail_page_is_missing() -> None:
    vonas, _ = await read(max_pages=3)
    by_id = {vona.magma_id: vona for vona in vonas}
    ash = by_id[22713]  # Semeru 20260925/1515Z: "Ash cloud moving to north", 4376 M
    assert ash.volcano_name == "Semeru"
    assert ash.issued_at == datetime(2026, 9, 25, 15, 15, tzinfo=UTC)
    assert ash.color_code is AviationColor.ORANGE
    assert ash.ash_observed
    assert ash.cloud_top_m == 4376
    assert ash.movement_toward_deg == 0
    assert ash.source_text == "ground observer"
    assert ash.provenance.url == build_url(VONA_LIST_URL, {"page": "2"})
    assert ash.provenance.fetched_at == SAVED_AT
    assert "Ash cloud moving to north" in ash.raw_text
    unseen = by_id[22712]  # 20260925/1137Z: "Ash-cloud is not observed."
    assert not unseen.ash_observed
    assert unseen.cloud_top_ft is None
    assert unseen.movement_toward_deg is None


async def test_known_notices_are_not_fetched_again() -> None:
    vonas, source = await read(max_pages=3, known_ids=frozenset({22713}))
    assert 22713 not in {vona.magma_id for vona in vonas}
    assert not any("/vona/22713" in url for url in source.requested)


@pytest.mark.skipif(
    not (case_path(DATA_DIR, "semeru-20260923") / "manifest.json").is_file(),
    reason="the semeru-20260923 replay case is not in this checkout",
)
async def test_the_semeru_replay_case_shows_the_northward_vonas() -> None:
    case = load_case(DATA_DIR, "semeru-20260923")
    source = ReplaySource(case_path(DATA_DIR, case.case_id), case)
    with use_clock(FixedClock(CLOCK)):
        vonas = await fetch_vonas(source, since=CLOCK - timedelta(hours=24), max_pages=2)
    semeru = [vona for vona in vonas if vona.volcano_name == "Semeru" and vona.ash_observed]
    assert semeru
    assert all(vona.issued_at <= CLOCK for vona in vonas)
    assert {vona.movement_toward_deg for vona in semeru} <= {0.0, 45.0}
    assert all(vona.provenance.replay for vona in semeru)
