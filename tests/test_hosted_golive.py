"""Go live on TEPHRA (SPEC §5.1): the 10-minute feeds rule with pilot reports optional, the
assistant, policy and people items, the derived region and what blocks Start."""

from datetime import timedelta
from pathlib import Path

import pytest

from tephra.airline.models import Stamp
from tephra.hosted import golive, keys
from tephra.hosted.feeds import FeedStats
from tephra.hosted.models import HostedRefused, Member, PolicyConfirmed, TenantRecord
from tephra.models import PushProblem
from tests.test_hosted_tenants import airports, answers, site, wall

KEY = "AIzaTestKeyRFB0123456789abcdefghijKLMN"
BY = "Ana Ops#MB-1a2b3c4d5e"


def ready_record(tmp_path: Path, **update: object) -> TenantRecord:
    from tephra.hosted.models import TenantAssistant

    base = site(tmp_path)
    return TenantRecord(
        icao="RFB",
        airline_id="AL-0123456789ab",
        name="Ring of Fire Charter",
        version=3,
        state="setup",
        state_since=wall(),
        created=Stamp(by=BY, at=wall()),
        ops_managers=["MB-1a2b3c4d5e"],
        assistant=TenantAssistant(model="gemini-3.8-flash", model_lite="gemini-3.5-flash-lite"),
        model_key=keys.seal("RFB", KEY, base, by=BY, at=wall()),
        policy_version=2,
        policy_confirmed=PolicyConfirmed(by=BY, at=wall(), version=2),
    ).model_copy(update=update)


def dispatcher() -> Member:
    return Member(
        id="MB-2b3c4d5e6f",
        icao="RFB",
        login_key="d" * 64,
        email="dee@rfb.example",
        display_name="Dee Disp",
        role="dispatcher",
        joined_at=wall(),
    )


def pushed(
    stats: FeedStats, *, minutes_ago: float, plans: int = 1, key: str = "CN-0a1b2c3d4e"
) -> None:
    stats.record(
        accepted={"positions": 10, "flight_plans": plans},
        refused=[],
        wall_at=wall() - timedelta(minutes=minutes_ago),
        connection_id=key,
    )


def card(tmp_path: Path, record: TenantRecord, stats: FeedStats, **kw: object) -> golive.GoLive:
    values: dict[str, object] = {
        "settings": site(tmp_path),
        "airports": airports(),
        "stats": stats,
        "live_keys": ["CN-0a1b2c3d4e"],
        "members": [dispatcher()],
        "open_invites": 1,
        "slots_used": 1,
        "memory_ok": True,
        "now": wall(),
    }
    return golive.checklist(
        record,
        answers(feeds={"positions": True, "flight_plans": True}),
        **(values | kw),  # type: ignore[arg-type]
    )


def test_all_four_done_lets_shadow_runs_start(tmp_path: Path) -> None:
    stats = FeedStats(since=wall() - timedelta(hours=1))
    pushed(stats, minutes_ago=2)
    got = card(tmp_path, ready_record(tmp_path), stats)
    assert [item.done for item in got.items] == [True, True, True, True]
    assert got.items[0].detail == (
        "Positions and flight plans received in the last 10 minutes. "
        "Pilot reports: none yet (optional)."
    )
    assert got.items[1].detail == "Google AI Studio with your own key, ending KLMN"
    assert got.items[2].detail == "Version 2 confirmed by Ana Ops"
    assert got.items[3].detail == "1 dispatcher joined; 1 invite open"
    assert got.region is not None
    assert (got.region.key, got.region.derived) == ("java_bali", True)
    assert (got.can_start, got.blocked) == (True, None)
    assert got.items[0].href == "/a/RFB/feeds"


def test_feeds_older_than_ten_minutes_or_on_a_revoked_key_do_not_count(tmp_path: Path) -> None:
    stats = FeedStats(since=wall() - timedelta(hours=1))
    pushed(stats, minutes_ago=11)
    got = card(tmp_path, ready_record(tmp_path), stats)
    assert got.items[0].done is False
    assert got.items[0].detail.startswith("Positions and flight plans: none received")
    assert (got.can_start, got.blocked) == (False, "checklist")
    fresh = FeedStats(since=wall() - timedelta(hours=1))
    pushed(fresh, minutes_ago=1, key="CN-ffffffffff")
    assert card(tmp_path, ready_record(tmp_path), fresh).items[0].done is False


def test_a_dry_run_is_not_a_feed_connected(tmp_path: Path) -> None:
    stats = FeedStats(since=wall() - timedelta(hours=1))
    stats.record(
        accepted={"positions": 5, "flight_plans": 2}, refused=[], wall_at=wall(), connection_id=None
    )
    assert card(tmp_path, ready_record(tmp_path), stats).items[0].done is False


def test_only_positions_missing_says_so_and_the_count_start(tmp_path: Path) -> None:
    stats = FeedStats(since=wall() - timedelta(minutes=3))
    pushed(stats, minutes_ago=1, plans=0)
    stats.record(
        accepted={},
        refused=[PushProblem(section="positions", index=0, reason="bad")],
        wall_at=wall(),
        connection_id="CN-0a1b2c3d4e",
    )
    detail = card(tmp_path, ready_record(tmp_path), stats).items[0].detail
    assert detail.startswith("Flight plans: none received in the last 10 minutes.")
    assert "Counted since" in detail


def test_nothing_declared_is_public_adsb_only(tmp_path: Path) -> None:
    got = golive.checklist(
        ready_record(tmp_path),
        answers(feeds={"positions": False, "flight_plans": False, "pilot_reports": False}),
        settings=site(tmp_path),
        airports=airports(),
        stats=FeedStats(since=wall()),
        live_keys=[],
        members=[dispatcher()],
        open_invites=0,
        slots_used=0,
        memory_ok=True,
        now=wall(),
    )
    assert got.items[0].done is True
    assert got.items[0].detail == "Public ADS-B only: your flights are found by callsign RFB"


@pytest.mark.parametrize(
    ("update", "detail"),
    [
        ({"assistant": None}, "No model chosen"),
        ({"model_key": None}, "No key set"),
    ],
)
def test_the_assistant_item_needs_a_model_and_a_key(
    tmp_path: Path, update: dict[str, object], detail: str
) -> None:
    stats = FeedStats(since=wall())
    item = card(tmp_path, ready_record(tmp_path, **update), stats).items[1]
    assert (item.done, item.detail) == (False, detail)


def test_policy_and_people_items(tmp_path: Path) -> None:
    stats = FeedStats(since=wall())
    got = card(
        tmp_path, ready_record(tmp_path, policy_version=3), stats, members=[], open_invites=0
    )
    assert (got.items[2].done, got.items[2].detail) == (False, "Version 3 not confirmed")
    assert (got.items[3].done, got.items[3].detail) == (
        False,
        "No dispatcher has joined yet; 0 invites open",
    )


def test_blocked_by_places_then_by_memory(tmp_path: Path) -> None:
    stats = FeedStats(since=wall())
    pushed(stats, minutes_ago=1)
    full = card(tmp_path, ready_record(tmp_path), stats, slots_used=3)
    assert (full.can_start, full.blocked) == (False, "airline_limit_reached")
    assert (full.slots.used, full.slots.max) == (3, 3)
    memory = card(tmp_path, ready_record(tmp_path), stats, memory_ok=False)
    assert memory.blocked == "site_memory"


def test_regions_follow_the_network(tmp_path: Path) -> None:
    java = answers(airports_list=("WIII", "WADD"))
    assert golive.derive_region(java, airports()) == "java_bali"
    spread = answers(airports_list=("WIII", "RJFK"))
    assert golive.regions_for(spread, airports()) == ["java_bali", "kyushu"]
    assert golive.derive_region(spread, airports()) is None
    outside = answers(airports_list=("RJTT",))
    assert golive.regions_for(outside, airports()) == []
    stats = FeedStats(since=wall())
    pushed(stats, minutes_ago=1)
    got = golive.checklist(
        ready_record(tmp_path),
        outside,
        settings=site(tmp_path),
        airports=airports(),
        stats=stats,
        live_keys=["CN-0a1b2c3d4e"],
        members=[dispatcher()],
        open_invites=0,
        slots_used=0,
        memory_ok=True,
        now=wall(),
    )
    assert (got.region, got.region_note, got.blocked) == (None, golive.OUTSIDE_NOTE, "region")
    assert golive.start_region(java, airports(), None) == "java_bali"
    with pytest.raises(HostedRefused, match="region"):
        golive.start_region(java, airports(), "kyushu")
    with pytest.raises(HostedRefused, match="region"):
        golive.start_region(spread, airports(), None)
    assert golive.start_region(spread, airports(), "kyushu") == "kyushu"
