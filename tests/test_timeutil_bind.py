"""Bound clocks and tenants: nesting, tasks and threads keep them, and the process clock
cannot be moved from inside a binding."""

import asyncio
from datetime import UTC, datetime

import pytest
from starlette.concurrency import run_in_threadpool

from tephra.util import timeutil
from tephra.util.scope import bind_tenant, current_tenant

REPLAY_AT = datetime(2026, 9, 5, 10, 30, tzinfo=UTC)
AIRLINE_AT = datetime(2026, 10, 17, 14, 2, tzinfo=UTC)
INNER_AT = datetime(2026, 10, 17, 15, 0, tzinfo=UTC)


def test_a_bound_clock_wins_and_nesting_resets() -> None:
    with timeutil.use_clock(timeutil.FixedClock(REPLAY_AT)):
        assert not timeutil.clock_bound()
        with timeutil.bind_clock(timeutil.FixedClock(AIRLINE_AT)) as bound:
            assert timeutil.clock_bound()
            assert timeutil.get_clock() is bound
            assert timeutil.now() == AIRLINE_AT
            with timeutil.bind_clock(timeutil.FixedClock(INNER_AT)):
                assert timeutil.now() == INNER_AT
            assert timeutil.now() == AIRLINE_AT
        assert not timeutil.clock_bound()
        assert timeutil.now() == REPLAY_AT


def test_now_exact_follows_the_bound_clock() -> None:
    replay = timeutil.ReplayClock(REPLAY_AT, INNER_AT, quantum_s=60)
    with timeutil.use_clock(replay):
        assert timeutil.now_exact().year == 2026
        with timeutil.bind_clock(timeutil.FixedClock(AIRLINE_AT)):
            assert timeutil.now_exact() == AIRLINE_AT
            assert timeutil.age_s(AIRLINE_AT) == 0


def test_set_clock_inside_a_binding_raises_and_moves_nothing() -> None:
    with timeutil.use_clock(timeutil.FixedClock(REPLAY_AT)):
        with timeutil.bind_clock(timeutil.SystemClock()):
            with pytest.raises(RuntimeError, match="inside a bound clock"):
                timeutil.set_clock(timeutil.FixedClock(INNER_AT))
            with (
                pytest.raises(RuntimeError, match="inside a bound clock"),
                timeutil.use_clock(timeutil.FixedClock(INNER_AT)),
            ):
                pass
        assert timeutil.now() == REPLAY_AT


async def test_a_task_created_inside_a_binding_keeps_it() -> None:
    seen: list[tuple[datetime, str | None]] = []

    async def work() -> None:
        await asyncio.sleep(0)
        seen.append((timeutil.now(), current_tenant()))

    with timeutil.use_clock(timeutil.FixedClock(REPLAY_AT)):
        with bind_tenant("RFB"), timeutil.bind_clock(timeutil.FixedClock(AIRLINE_AT)):
            task = asyncio.ensure_future(work())
        outside = asyncio.ensure_future(work())
        await asyncio.gather(task, outside)
    assert seen == [(AIRLINE_AT, "RFB"), (REPLAY_AT, None)]


async def test_threads_see_the_binding() -> None:
    def read() -> tuple[datetime, str | None]:
        return timeutil.now(), current_tenant()

    with bind_tenant("RFC"), timeutil.bind_clock(timeutil.FixedClock(AIRLINE_AT)):
        assert await run_in_threadpool(read) == (AIRLINE_AT, "RFC")
        assert await asyncio.to_thread(read) == (AIRLINE_AT, "RFC")
    assert (await asyncio.to_thread(read))[1] is None


def test_bind_tenant_nests_and_refuses_what_is_not_an_icao() -> None:
    assert current_tenant() is None
    with bind_tenant("RFB"):
        with bind_tenant("RFC"):
            assert current_tenant() == "RFC"
        assert current_tenant() == "RFB"
    assert current_tenant() is None
    for bad in ("rfb", "RF", "RFBX", "R1B", ""):
        with pytest.raises(ValueError, match="ICAO"), bind_tenant(bad):
            pass
