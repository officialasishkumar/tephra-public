"""The daily model-call budgets: per model id, per Google quota day, kept in the store, and
split into urgent, interactive and routine shares (``tephra.agents.quota``)."""

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tephra.agents.quota import (
    LANES,
    ModelDay,
    QuotaLedger,
    Shares,
    current_admitted,
    current_lane,
    day_bounds,
    judge,
    next_routine_slot,
    quota_day,
    use_lane,
)
from tephra.config import Settings
from tephra.store.base import Collection
from tephra.store.sqlite_store import SqliteStore
from tephra.util.timeutil import FixedClock

LITE = "gemini-3.5-flash-lite"
MAIN = "gemini-3.8-flash"
TTS = "gemini-3.8-flash-lite-tts"
SETTINGS = Settings(_env_file=None)
# 0800Z on 13 Oct is 0100 PDT: 1/24 of Google's quota day has gone by.
EARLY = datetime(2026, 10, 13, 8, 0, tzinfo=UTC)


@pytest.fixture
async def store(tmp_path: Path) -> AsyncIterator[SqliteStore]:
    store = SqliteStore(tmp_path / "tephra.sqlite3", tmp_path / "blobs")
    yield store
    await store.aclose()


def ledger(store: Any, clock: FixedClock, settings: Settings = SETTINGS) -> QuotaLedger:
    return QuotaLedger(settings, store, now=clock.now)


def test_the_quota_day_is_googles_midnight_to_midnight_pacific() -> None:
    """research/10: free-tier requests per day reset at midnight Pacific time, 0700Z until the
    clock change on 1 Nov 2026 and 0800Z after it."""
    assert quota_day(datetime(2026, 10, 13, 6, 59, tzinfo=UTC)).isoformat() == "2026-10-12"
    assert quota_day(datetime(2026, 10, 13, 7, 0, tzinfo=UTC)).isoformat() == "2026-10-13"
    start, end = day_bounds(quota_day(EARLY))
    assert (start.hour, end.hour) == (7, 7)
    start, end = day_bounds(datetime(2026, 11, 1, 12, tzinfo=UTC).date())
    assert (start.hour, end.hour, (end - start).total_seconds() / 3600) == (7, 8, 25)


def test_budgets_are_the_free_limit_less_the_margin_per_model() -> None:
    assert SETTINGS.daily_budget(MAIN) == 18
    assert SETTINGS.daily_budget(LITE) == 450
    assert SETTINGS.daily_budget(TTS) == 9
    assert SETTINGS.daily_budget("gemma-4-31b-it") == 12_960
    assert SETTINGS.paced_rpm(LITE) == 13
    assert SETTINGS.paced_tpm("gemma-4-31b-it") == 14_400
    assert SETTINGS.paced_tpm(LITE) is None
    assert SETTINGS.daily_budget("no-such-model") == 0
    overridden = Settings(_env_file=None, model_lite_daily_budget=100)
    assert overridden.daily_budget(LITE) == 100
    added = Settings(_env_file=None, model_limits={"gemma-4-31b-it": {"rpm": 10, "rpd": 1000}})
    assert added.daily_budget("gemma-4-31b-it") == 900
    assert added.daily_budget(LITE) == 450, "a row given adds to the defaults"


def test_each_model_holds_back_only_the_lanes_its_jobs_use() -> None:
    lite, main, tts = (Shares.of(SETTINGS, model) for model in (LITE, MAIN, TTS))
    assert (lite.urgent, lite.interactive, lite.routine) == (135, 90, 225)
    assert (main.urgent, main.interactive, main.routine) == (5, 0, 13)
    assert (tts.urgent, tts.interactive, tts.routine) == (0, 9, 0), "speech is Desk work only"
    assert tts.burst == 0


def test_routine_work_is_paced_through_the_day_and_urgent_work_is_not() -> None:
    shares = Shares.of(SETTINGS, LITE)
    early = 1 / 24
    day = ModelDay(quota_day=quota_day(EARLY), model_id=LITE, used={"routine": 30})
    # 225 x 1/24 + a burst of 22 = 31.4 routine calls by 0100 PDT.
    assert judge(day, shares, "routine", early).ok
    day = day.model_copy(update={"used": {"routine": 31}})
    refused = judge(day, shares, "routine", early)
    assert not refused.ok
    assert "paced" in (refused.reason or "")
    assert judge(day, shares, "urgent", early).ok
    assert judge(day, shares, "interactive", early).ok
    assert judge(day, shares, "routine", 0.5).ok


def test_an_admitted_routine_run_finishes_within_the_daily_cap() -> None:
    """Review of 28e8b20, item 1: a run admitted the moment its estimated 12 calls fit was cut
    off at its 13th call by pacing, and its flight marked planned with AI UNAVAILABLE. Pacing
    decides when a run starts; once admitted, its calls are not paced again (the daily cap and
    the held reserves still apply, below)."""
    shares = Shares.of(SETTINGS, LITE)
    early = 1 / 24
    day = ModelDay(quota_day=quota_day(EARLY), model_id=LITE, used={"routine": 31})
    assert not judge(day, shares, "routine", early).ok, "a new routine run waits"
    assert judge(day, shares, "routine", early, admitted=True).ok, "an admitted one goes on"
    full = day.model_copy(update={"used": {"routine": 31, "urgent": 419}})
    refused = judge(full, shares, "routine", early, admitted=True)
    assert not refused.ok
    assert "450 of 450" in (refused.reason or "")


def test_an_admitted_routine_run_never_takes_the_desk_s_reserve() -> None:
    """18 Oct 2026: the Desk got none of its 90 calls. A routine run that needs more calls than
    its estimate goes on past pacing, but not into the urgent or interactive reserve held."""
    shares = Shares.of(SETTINGS, LITE)
    early = 1 / 24
    day = ModelDay(quota_day=quota_day(EARLY), model_id=LITE, used={"routine": 225, "urgent": 135})
    refused = judge(day, shares, "routine", early, admitted=True)
    assert not refused.ok
    assert "held for urgent and Desk work" in (refused.reason or "")
    assert judge(day, shares, "interactive", early).ok, "the Desk's 90 are still there"
    assert judge(day, shares, "routine", 0.99, admitted=True).ok, "released late in the day"


def test_the_reserves_are_held_until_late_in_the_day_then_flow_to_routine() -> None:
    shares = Shares.of(SETTINGS, LITE)
    day = ModelDay(quota_day=quota_day(EARLY), model_id=LITE, used={"routine": 225})
    assert not judge(day, shares, "routine", 0.7).ok, "routine has spent its own share"
    assert judge(day, shares, "routine", 0.9).ok, "unused reserves flow to routine late"
    spent = day.model_copy(update={"used": {"routine": 225, "interactive": 100}})
    refused = judge(spent, shares, "interactive", 0.5)
    assert not refused.ok
    assert "held for urgent work" in (refused.reason or "")
    assert judge(spent, shares, "urgent", 0.5).ok
    full = day.model_copy(update={"used": {"urgent": 450}})
    assert not judge(full, shares, "urgent", 0.99).ok, "the budget caps urgent work too"


def test_a_paced_call_knows_its_next_slot() -> None:
    shares = Shares.of(SETTINGS, LITE)
    day = ModelDay(quota_day=quota_day(EARLY), model_id=LITE, used={"routine": 60})
    slot = next_routine_slot(day, shares, EARLY)
    start, end = day_bounds(day.quota_day)
    assert EARLY < slot < end
    fraction = (slot - start) / (end - start)
    assert judge(day, shares, "routine", fraction + 1e-6).ok
    assert not judge(day, shares, "routine", fraction - 1e-3).ok
    spent = day.model_copy(update={"used": {"routine": 225, "urgent": 135, "interactive": 90}})
    assert next_routine_slot(spent, shares, EARLY) == end, "nothing left today: the next day"


def test_the_lane_comes_from_the_context_and_is_interactive_by_default() -> None:
    assert current_lane() == "interactive"
    assert not current_admitted()
    with use_lane("routine", admitted=True):
        assert current_lane() == "routine"
        assert current_admitted()
        with use_lane("urgent"):
            assert not current_admitted()
        assert current_admitted()
    assert not current_admitted()
    with use_lane("routine"):
        assert current_lane() == "routine"
        with use_lane("urgent"):
            assert current_lane() == "urgent"
        assert current_lane() == "routine"
    assert current_lane() == "interactive"
    assert set(LANES) == {"urgent", "interactive", "routine"}


async def test_counts_are_kept_in_the_store_per_model_and_survive_a_new_instance(
    store: SqliteStore,
) -> None:
    """A redeploy or a replaced instance used to start the day at zero (the count lived in
    /tmp); the store now carries it, so the new instance refuses what the old one spent."""
    clock = FixedClock(EARLY)
    before = ledger(store, clock, Settings(_env_file=None, model_daily_budget=2))
    assert await before.reserve(MAIN, "urgent") is None
    assert await before.reserve(MAIN, "urgent") is None
    assert await before.reserve(LITE, "interactive") is None

    after = ledger(store, clock, Settings(_env_file=None, model_daily_budget=2))
    refused = await after.reserve(MAIN, "urgent")
    assert refused is not None
    assert "2 of 2" in refused
    assert (await after.load(LITE)).used == {"interactive": 1}
    doc = await store.get(Collection.AI_BUDGET, f"2026-10-13/{MAIN}")
    assert doc is not None
    assert doc["used"] == {"urgent": 2}

    clock.set(datetime(2026, 10, 14, 7, 1, tzinfo=UTC))  # 0001 PDT on 14 Oct
    assert await after.reserve(MAIN, "urgent") is None, "a new quota day starts at zero"


async def test_a_daily_429_closes_only_that_model_and_outlives_the_instance(
    store: SqliteStore,
) -> None:
    clock = FixedClock(EARLY)
    first = ledger(store, clock)
    await first.close(TTS, "Google answered 429 for a per-day quota")
    assert await first.reserve(TTS, "interactive") is not None
    assert await first.reserve(LITE, "interactive") is None, "speech closing leaves lite open"
    second = ledger(store, clock)
    refused = await second.reserve(TTS, "interactive")
    assert refused is not None
    assert "spent" in refused


async def test_two_instances_never_hand_out_the_same_last_call(store: SqliteStore) -> None:
    clock = FixedClock(EARLY)
    settings = Settings(_env_file=None, model_daily_budget=1)
    one, two = ledger(store, clock, settings), ledger(store, clock, settings)
    await one.load(MAIN)
    await two.load(MAIN)
    assert await one.reserve(MAIN, "urgent") is None
    assert await two.reserve(MAIN, "urgent") is not None, "the stored count is checked again"


async def test_a_failing_store_refuses_every_call_until_it_answers_again(
    store: SqliteStore, caplog: pytest.LogCaptureFixture
) -> None:
    """Review of 28e8b20, item 3: a store fault used to let calls go counted in memory, and a
    new instance started at zero. The count is unknown then, so no call goes."""

    class Flaky:
        def __init__(self) -> None:
            self.down = True

        async def get(self, *args: Any) -> Any:
            if self.down:
                raise OSError("store down")
            return await store.get(*args)

        async def update(self, *args: Any) -> Any:
            if self.down:
                raise OSError("store down")
            return await store.update(*args)

    clock = FixedClock(EARLY)
    settings = Settings(_env_file=None, model_daily_budget=5)
    spent = ledger(store, clock, settings)
    for _ in range(5):
        assert await spent.reserve(MAIN, "urgent") is None

    flaky = Flaky()
    fresh = QuotaLedger(settings, flaky, now=clock.now)  # type: ignore[arg-type]
    with caplog.at_level(logging.WARNING, logger="tephra.agents.quota"):
        refused = await fresh.reserve(MAIN, "urgent")
    assert refused is not None, "a new instance never starts the day at zero"
    assert "could not be reached" in refused
    assert "could not be reached" in caplog.text
    assert fresh.unreadable(MAIN) == refused
    admission = fresh.admission(MAIN, "routine")
    assert not admission.ok
    assert admission.next_slot is None
    assert await store.get(Collection.AI_BUDGET, f"2026-10-13/{MAIN}") is not None

    flaky.down = False
    refused = await fresh.reserve(MAIN, "urgent")
    assert refused is not None
    assert "5 of 5" in refused, "the store answers again: its count, not a guess"
    assert fresh.unreadable(MAIN) is None
    assert await fresh.reserve(LITE, "interactive") is None


async def test_admission_gives_waiting_routine_work_its_next_slot(store: SqliteStore) -> None:
    clock = FixedClock(EARLY)
    counted = ledger(store, clock, Settings(_env_file=None, model_daily_budget=10))
    await counted.load(MAIN)
    # Budget 10: urgent 3, routine 7, burst 1; at 0100 PDT routine may use 1.29 calls.
    assert counted.admission(MAIN, "routine").ok
    waiting = counted.admission(MAIN, "routine", calls=3)
    assert not waiting.ok
    assert waiting.next_slot is not None
    assert waiting.next_slot > EARLY
    assert counted.admission(MAIN, "urgent", calls=3).ok
    await counted.close(MAIN, "Google answered 429 for a per-day quota")
    closed = counted.admission(MAIN, "routine")
    assert not closed.ok
    assert closed.next_slot == day_bounds(quota_day(EARLY))[1], "the next quota day"


def test_urgent_work_takes_routines_share_but_never_the_desks_reserve() -> None:
    """Live, 18 Oct 2026: the loop's urgent Duty Officer runs spent 430 lite calls of a 135
    share and left the Desk 0 of its 90, so Ask, paperwork, messages and a Desk-started airport
    plan answered AI UNAVAILABLE until 0700Z. Urgent work may take routine's unused share, never
    the interactive reserve."""
    shares = Shares.of(SETTINGS, LITE)
    day = ModelDay(quota_day=quota_day(EARLY), model_id=LITE, used={"urgent": 359})
    assert judge(day, shares, "urgent", 0.5).ok, "its own 135 and routine's unused 225"
    saturated = day.model_copy(update={"used": {"urgent": 360}})
    refused = judge(saturated, shares, "urgent", 0.5)
    assert not refused.ok
    assert "held for Desk work" in (refused.reason or "")
    assert judge(saturated, shares, "interactive", 0.5, calls=90).ok, "the Desk keeps its 90"
    paced_routine = day.model_copy(update={"used": {"urgent": 135, "routine": 225}})
    assert not judge(paced_routine, shares, "urgent", 0.5).ok, "routine spent its own share"


async def test_the_desk_still_gets_its_reserve_after_urgent_work_saturates(
    store: SqliteStore,
) -> None:
    clock = FixedClock(datetime(2026, 10, 13, 19, 0, tzinfo=UTC))  # 1200 PDT: half the day
    counted = ledger(store, clock)
    urgent = 0
    while await counted.reserve(LITE, "urgent") is None:
        urgent += 1
    assert urgent == 360, "135 urgent + 225 routine; the 90 Desk calls are not touched"
    desk = 0
    while await counted.reserve(LITE, "interactive") is None:
        desk += 1
    assert desk == 90
    assert (await counted.load(LITE, fresh=True)).used == {"urgent": 360, "interactive": 90}


async def test_capped_urgent_work_knows_its_next_slot(store: SqliteStore) -> None:
    """Refused urgent work waits for its slot, as routine work does: the Desk's unused reserve
    is released to it late in the day, and a spent budget opens at the next quota day."""
    clock = FixedClock(datetime(2026, 10, 13, 19, 0, tzinfo=UTC))
    counted = ledger(store, clock)
    for _ in range(360):
        assert await counted.reserve(LITE, "urgent") is None
    waiting = counted.admission(LITE, "urgent")
    assert not waiting.ok
    start, end = day_bounds(quota_day(clock.now()))
    assert waiting.next_slot is not None
    assert start + (end - start) * SETTINGS.ai_reserve_release < waiting.next_slot < end
    clock.set(waiting.next_slot + timedelta(seconds=1))
    assert counted.admission(LITE, "urgent").ok, "the released Desk reserve flows to urgent"
    assert counted.admission(LITE, "interactive").next_slot is None, "a person waits now"
    await counted.close(LITE, "Google answered 429 for a per-day quota")
    assert counted.admission(LITE, "urgent").next_slot == end, "the next quota day"
