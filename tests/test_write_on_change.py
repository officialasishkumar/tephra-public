"""Reroutes and plans are written when they change (SPEC-FINAL §3.7, B2): a flight planned again
to the same answer costs no write, after a restart too (the stored reroutes are known). The
demo works the same way; its answers do not change."""

from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from test_pipeline import AT, FixtureSource, make_runtime, make_settings, tick_and_work

from tephra.desk.approvals import list_advisories
from tephra.pipeline import Runtime
from tephra.store.base import Collection
from tephra.util.timeutil import FixedClock, use_clock

COUNTED = (Collection.REROUTES, Collection.PLANS)


def count_puts(runtime: Runtime) -> Counter[str]:
    puts: Counter[str] = Counter()
    put = runtime.store.put

    async def counting(collection: str, doc_id: str, doc: Mapping[str, Any]) -> None:
        if collection in COUNTED:
            puts[str(collection)] += 1
        await put(collection, doc_id, doc)

    runtime.store.put = counting  # type: ignore[method-assign]
    return puts


async def replan(runtime: Runtime) -> None:
    """Plan every exposed flight again, as a new urgency bucket or cone would."""
    runtime._planned.clear()
    await tick_and_work(runtime, reason="manual")


async def test_a_flight_planned_again_to_the_same_answer_writes_nothing(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    with use_clock(FixedClock(AT)):
        runtime = make_runtime(settings, FixtureSource())
        try:
            puts = count_puts(runtime)
            await tick_and_work(runtime, reason="manual")
            first = dict(puts)
            drafts = await list_advisories(runtime.store, limit=50)
            puts.clear()
            await replan(runtime)
            again = dict(puts)
            assert await list_advisories(runtime.store, limit=50) == drafts
        finally:
            await runtime.aclose()

        assert first.get(Collection.REROUTES.value, 0) > 0
        assert first.get(Collection.PLANS.value, 0) > 0
        assert again == {}

        restarted = make_runtime(settings, FixtureSource())
        try:
            await restarted.restore()
            puts = count_puts(restarted)
            await tick_and_work(restarted, reason="manual")
            after_restart = dict(puts)
        finally:
            await restarted.aclose()

    assert Collection.REROUTES.value not in after_restart, "the stored reroutes are known"


async def test_a_changed_document_is_written(tmp_path: Path) -> None:
    with use_clock(FixedClock(AT)):
        runtime = make_runtime(make_settings(tmp_path), FixtureSource())
        try:
            puts = count_puts(runtime)
            doc = {"id": "RR-1", "flight_id": "F", "kind": "x"}
            await runtime._put_on_change(Collection.REROUTES, "RR-1", doc)
            await runtime._put_on_change(Collection.REROUTES, "RR-1", dict(doc))
            await runtime._put_on_change(Collection.REROUTES, "RR-1", {**doc, "kind": "y"})
            stored = await runtime.store.get(Collection.REROUTES, "RR-1")
        finally:
            await runtime.aclose()
    assert puts[Collection.REROUTES.value] == 2
    assert stored is not None
    assert stored["kind"] == "y"
