"""The synthetic demo case ``data/replay/demo-agung-20261014`` (``scripts/make_demo_case.py``).

It must load through the ordinary replay path with every feed readable by its own parser, say
everywhere that it is invented, show the situations the demo needs at its window start, and never
be scored by the backtest. No network: the case plays through ``ReplaySource`` on a fixed clock.
"""

import importlib.util
import random
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Final
from urllib.parse import urlsplit

import pytest

from tephra.backtest.runner import SyntheticCase, run_case
from tephra.config import PROJECT_ROOT, Settings
from tephra.desk.approvals import list_advisories
from tephra.feeds.adsb import parse_adsb
from tephra.feeds.base import FetchResult
from tephra.feeds.jma_volcano import JMA_EQVOL_URL, parse_jma_entries, parse_jma_report
from tephra.feeds.sigmet import parse_sigmets
from tephra.feeds.taf import parse_metars, parse_tafs
from tephra.feeds.vaac import DARWIN_BACKUP_LIST_URL, TOKYO_LIST_URL, parse_vaa, parse_vaac_list
from tephra.feeds.volcanoes import load_volcanoes
from tephra.feeds.vona import parse_vona_card, parse_vona_list
from tephra.feeds.winds import parse_winds
from tephra.models import (
    ActionKind,
    AdsbQueryPoint,
    AdvisoryStatus,
    DiscrepancyKind,
    FeedId,
    FeedStatus,
    ReplayCase,
    ReplayRecord,
    RerouteStatus,
    RunMode,
    VaacCentre,
)
from tephra.pipeline import create_runtime
from tephra.replay.cases import MANIFEST_NAME, case_path, load_case, replay_banner, replay_info
from tephra.util.hashing import sha256_bytes
from tephra.util.timeutil import FixedClock, use_clock

DATA_DIR = PROJECT_ROOT / "data"
CASE = "demo-agung-20261014"
DEMO_FROM = datetime(2026, 10, 14, 7, 5, tzinfo=UTC)
DEMO_TO = datetime(2026, 10, 14, 7, 15, tzinfo=UTC)
AGUNG, SAKURAJIMA = "264020", "282080"
CASE_FEEDS = {
    FeedId.SIGMET,
    FeedId.VONA,
    FeedId.JMA_VOLCANO,
    FeedId.VAAC_TOKYO,
    FeedId.VAAC_DARWIN,
    FeedId.TAF,
    FeedId.METAR,
    FeedId.WINDS,
    FeedId.ADSB,
}

pytestmark = pytest.mark.skipif(
    not (case_path(DATA_DIR, CASE) / MANIFEST_NAME).is_file(),
    reason=f"the {CASE} replay case is not in this checkout",
)


def _case() -> ReplayCase:
    return load_case(DATA_DIR, CASE)


def _result(record: ReplayRecord) -> FetchResult:
    content = (case_path(DATA_DIR, CASE) / record.path).read_bytes()
    return FetchResult(
        feed=record.feed,
        url=record.url,
        status_code=record.status_code,
        content=content,
        content_type=record.content_type,
        fetched_at=record.fetched_at,
        sha256=record.sha256,
        replay=True,
    )


def _load_script(name: str) -> ModuleType:
    module_name = f"tephra_script_{name}"
    spec = importlib.util.spec_from_file_location(module_name, PROJECT_ROOT / "scripts" / name)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# --- what the case is -------------------------------------------------------------------


def test_the_case_says_it_is_synthetic_everywhere_it_names_itself() -> None:
    case = _case()
    assert case.synthetic
    assert not case.reconstructed
    assert case.label.startswith("SYNTHETIC DEMO:")
    assert (case.notes or "").startswith("Synthetic demo data")
    assert "recorded" not in replay_banner(case)
    assert replay_banner(case) == "REPLAY: synthetic demo data, scenario dated 14 Oct 2026"
    info = replay_info(case, auto=False)
    assert info.synthetic
    assert info.volcano_ids == [AGUNG, SAKURAJIMA]


def test_every_record_is_on_disk_with_its_hash_and_the_case_stays_small() -> None:
    case = _case()
    root = case_path(DATA_DIR, CASE)
    size = 0
    for record in case.records:
        content = (root / record.path).read_bytes()
        assert sha256_bytes(content) == record.sha256, record.path
        size += len(content)
    assert size < 20_000_000
    listed = {record.path for record in case.records}
    on_disk = {p.relative_to(root).as_posix() for p in (root / "raw").rglob("*") if p.is_file()}
    assert on_disk == listed


def test_the_case_holds_every_feed_but_the_satellite_pictures() -> None:
    feeds = {record.feed for record in _case().records}
    assert feeds == CASE_FEEDS
    # every URL has an answer at the window start, so the replay never shows a later one early
    case = _case()
    first: dict[str, datetime] = {}
    for record in case.records:
        first[record.url] = min(first.get(record.url, record.fetched_at), record.fetched_at)
    pages = [url for url in first if "TextData" in url or "VFVO52" in url]
    assert all(at == case.recorded_from for url, at in first.items() if url not in pages)


def test_every_page_says_it_was_invented() -> None:
    case = _case()
    for record in case.records:
        if record.feed in (FeedId.SIGMET, FeedId.TAF, FeedId.METAR, FeedId.WINDS, FeedId.ADSB):
            continue  # JSON has no comments; the manifest says it for them
        text = _result(record).text()
        assert "SYNTHETIC DEMO DATA" in text, record.url


def test_every_response_reads_with_its_own_parser() -> None:
    case = _case()
    catalogue = load_volcanoes(DATA_DIR)
    seen: dict[FeedId, int] = defaultdict(int)
    for record in case.records:
        result = _result(record)
        match record.feed:
            case FeedId.SIGMET:
                seen[record.feed] += len(parse_sigmets(result))
            case FeedId.VONA:
                items = parse_vona_list(result)
                assert items
                seen[record.feed] += len([parse_vona_card(result, item) for item in items])
            case FeedId.JMA_VOLCANO if record.url == JMA_EQVOL_URL:
                assert parse_jma_entries(result)
            case FeedId.JMA_VOLCANO:
                report = parse_jma_report(result, catalogue)
                assert report is not None
                assert report.volcano_name == "Sakurajima"
                seen[record.feed] += 1
            case FeedId.VAAC_TOKYO if record.url == TOKYO_LIST_URL:
                assert parse_vaac_list(result, VaacCentre.TOKYO)
            case FeedId.VAAC_DARWIN if record.url == DARWIN_BACKUP_LIST_URL:
                assert parse_vaac_list(result, VaacCentre.DARWIN) == []
            case FeedId.VAAC_TOKYO | FeedId.VAAC_DARWIN:
                assert parse_vaa(result) is not None, record.url
                seen[record.feed] += 1
            case FeedId.TAF:
                tafs = parse_tafs(result)
                assert len(tafs) == len(_ids(record.url))
                seen[record.feed] += len(tafs)
            case FeedId.METAR:
                metars = parse_metars(result)
                assert len(metars) == len(_ids(record.url))
                seen[record.feed] += len(metars)
            case FeedId.WINDS:
                query = dict(part.split("=", 1) for part in urlsplit(record.url).query.split("&"))
                profiles = parse_winds(
                    result, lat=float(query["latitude"]), lon=float(query["longitude"])
                )
                assert len(profiles) == 25
                seen[record.feed] += 1
            case FeedId.ADSB:
                lat, lon, radius = urlsplit(record.url).path.split("/")[-3:]
                query = AdsbQueryPoint(lat=float(lat), lon=float(lon), radius_nm=int(radius))
                snapshot = parse_adsb(result, query)
                assert all(aircraft.airline for aircraft in snapshot.aircraft)
                seen[record.feed] += len(snapshot.aircraft)
    assert set(seen) == CASE_FEEDS
    assert all(count > 0 for count in seen.values())


def _ids(url: str) -> list[str]:
    query = urlsplit(url).query
    return [part for part in query.split("ids=")[1].split("&")[0].split("%2C") if part]


# --- what the demo window shows -----------------------------------------------------------

NAMED: Final = {
    "CPA140": "REROUTE",
    "CPA133": "CHANGE_LEVEL",
    "GIA456": "HOLD",
    "VOZ4134": "DIVERT",
}
"""The flights data/demo/local-demo.json and data/replay/README.md name, and what the code drafts
for each at the window start."""


def test_the_picture_holds_through_the_window() -> None:
    """Only aircraft move in the window: no product, report or forecast changes inside it, so
    every minute of the loop shows the same sources."""
    changed = [
        record
        for record in _case().records
        if record.feed is not FeedId.ADSB and DEMO_FROM < record.fetched_at <= DEMO_TO
    ]
    assert changed == []


@pytest.mark.parametrize("minute", [0, 3])
async def test_the_first_minutes_show_every_demo_situation(tmp_path: Path, minute: int) -> None:
    settings = Settings(
        _env_file=None,
        llm="stub",
        mode=RunMode.REPLAY,
        replay_case=CASE,
        data_dir=DATA_DIR,
        store="sqlite",
        sqlite_path=tmp_path / "demo.sqlite3",
        cache_dir=tmp_path / "cache",
    )
    at = DEMO_FROM + timedelta(minutes=minute)
    runtime = await create_runtime(settings)
    try:
        with use_clock(FixedClock(at)):
            await runtime.tick(reason="manual")
            due = runtime.recovery_due
            runtime.recovery_due = None  # its solve takes most of a minute; it is due, enough
            await runtime.worker.drain()  # the drafts, which the AI worker makes off the tick
            state = await runtime.system_state()
            drafts = await list_advisories(runtime.store, status=AdvisoryStatus.DRAFT, limit=200)
    finally:
        await runtime.aclose()

    assert state.replay is not None
    assert state.replay.synthetic
    assert state.replay.banner.startswith("REPLAY: synthetic demo data")
    health = {feed.feed: feed for feed in state.feeds}
    assert {feed for feed, h in health.items() if h.status is FeedStatus.OK} == CASE_FEEDS
    assert health[FeedId.FRAMES].status is FeedStatus.DISABLED

    assert set(runtime.live.active) == {AGUNG, SAKURAJIMA, "263300", "268010"}
    sakurajima = {d.kind for d in runtime.situations[SAKURAJIMA].discrepancies}
    assert DiscrepancyKind.CONFLICT in sakurajima
    agung = {d.kind for d in runtime.situations[AGUNG].discrepancies}
    assert {DiscrepancyKind.HEIGHT_MISMATCH, DiscrepancyKind.DIRECTION_MISMATCH} <= agung
    assert "VA" in (runtime.live.metars["WADD"].raw_text or "")

    exposed = list(runtime.exposed.values())
    agung_flights = [flight for flight in exposed if flight.volcano_id == AGUNG]
    assert len(agung_flights) >= 20
    assert sum(flight.inside_now for flight in agung_flights) >= 2
    assert sum(0 < flight.minutes_to_entry <= 15 for flight in agung_flights) >= 4
    assert any(flight.volcano_id == SAKURAJIMA for flight in exposed)
    assert due is not None
    assert "WADD" in due.airports

    actions = {draft.action for draft in drafts}
    assert {
        ActionKind.DIVERT,
        ActionKind.HOLD,
        ActionKind.CHANGE_LEVEL,
        ActionKind.REROUTE,
    } <= actions
    label = f"REPLAY - SYNTHETIC DEMO DATA {CASE.upper()} (14 OCT 2026) - NOT LIVE"
    assert all(label in draft.header for draft in drafts)
    if minute == 0:
        by_callsign = {draft.callsign: draft.action.value for draft in drafts}
        assert {cs: by_callsign.get(cs) for cs in NAMED} == NAMED
        reroute = runtime.reroutes[next(f.id for f in exposed if f.callsign == "CPA140")]
        assert all(option.status is RerouteStatus.OK for option in reroute)


# --- never scored -------------------------------------------------------------------------


async def test_the_backtest_refuses_the_synthetic_case(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, llm="stub", cache_dir=tmp_path / "cache")
    with pytest.raises(SyntheticCase, match="synthetic demo data"):
        await run_case(CASE, settings=settings)


def test_the_backtest_script_leaves_the_synthetic_case_out(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TEPHRA_LLM", "stub")
    script = _load_script("backtest.py")
    settings = Settings(_env_file=None, llm="stub", data_dir=DATA_DIR)
    ids = script._case_ids(settings, [])
    assert CASE not in ids
    assert ids
    with pytest.raises(SystemExit, match="synthetic demo data, never scored"):
        script.main(["--case", CASE, "--out", str(tmp_path)])


# --- the generator --------------------------------------------------------------------------


def test_the_generator_writes_the_same_products_twice(tmp_path: Path) -> None:
    generator = _load_script("make_demo_case.py")
    first = generator.product_records(generator.Store(tmp_path / "a"))
    second = generator.product_records(generator.Store(tmp_path / "b"))
    assert [(r.url, r.fetched_at, r.sha256) for r in first] == [
        (r.url, r.fetched_at, r.sha256) for r in second
    ]
    committed = {(r.url, r.fetched_at, r.sha256) for r in _case().records}
    assert {(r.url, r.fetched_at, r.sha256) for r in first} <= committed


def test_the_flights_fly_real_routes_at_rule_levels_and_plain_speeds() -> None:
    generator = _load_script("make_demo_case.py")
    routes, _ = generator.route_table()
    flights = generator.traffic()
    assert len(flights) > 300
    for flight in flights:
        assert routes[flight.callsign] == f"{flight.origin}-{flight.dest}"
        track = generator.initial_bearing_deg(*flight.o, *flight.d)
        assert generator.level_ok(flight.cruise_ft // 100, track), flight.callsign
        cruise = max(flight.legs, key=lambda leg: leg.minutes)
        assert 180 <= cruise.gs_kt <= 580, flight.callsign
        assert flight.legs[-1].alt_to == 0
    assert {flight.type_icao for flight in flights if flight.callsign.startswith("JAL3")} <= {
        "AT76",
        "AT46",
    }


def test_each_hero_is_where_the_demo_needs_it() -> None:
    """The exposure check the app runs finds each hero flight its lead from the official area."""
    generator = _load_script("make_demo_case.py")
    flights = generator.hero_flights(random.Random(generator.SEED))
    for flight, hero in zip(flights, generator.HEROES, strict=True):
        when = DEMO_FROM + timedelta(minutes=hero.at_min)
        assert generator.lead_at(flight, hero.volcano.id, when) == hero.lead_min, flight.callsign


def test_the_wall_words_a_synthetic_replay_as_demo_data() -> None:
    """The replay words, About and every "real aircraft" line read the case's flag."""
    web = PROJECT_ROOT / "tephra" / "web" / "wall"
    xparts = (web / "x-parts.js").read_text(encoding="utf-8")
    assert 'replay?.synthetic ? "Replay · synthetic demo data"' in xparts
    assert 'state.replay?.synthetic ? "demo aircraft" : "real aircraft"' in xparts
    for name in ("panels.js", "details.js"):
        text = (web / name).read_text(encoding="utf-8")
        assert "real aircraft ${" not in text.lower(), name
        assert "aircraftNoun(D.state)" in text, name
    assert 'M.demo ? "Demo" : "Real"' in (web / "board-view.js").read_text(encoding="utf-8")
    assert "demo: replay && !!s.replay?.synthetic" in (web / "board.js").read_text(encoding="utf-8")
    about = (web / "controls.js").read_text(encoding="utf-8")
    assert "This REPLAY is synthetic demo data" in about
