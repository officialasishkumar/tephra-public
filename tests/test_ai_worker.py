"""The AI worker: model work off the tick, one job at a time, urgent first, routine work paced
and kept WAITING with its next slot, the queue kept in the store across a restart."""

import asyncio
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from test_pipeline import AT, GIA417, SEMERU, FixtureSource, make_runtime, make_settings

from tephra import ai_worker as ai_worker_module
from tephra import pipeline as pipeline_module
from tephra.agents.llm import StubBackend, Tier
from tephra.agents.quota import Lane, QuotaLedger, current_admitted, current_lane
from tephra.desk.approvals import list_advisories
from tephra.models import (
    DutyItem,
    DutyItemKind,
    LlmBackendName,
    RunMode,
    SseEvent,
    TickReport,
)
from tephra.pipeline import Runtime
from tephra.scheduler import run_tick
from tephra.store.base import Collection
from tephra.util.timeutil import FixedClock, use_clock

LITE = "gemini-3.5-flash-lite"
MAIN = "gemini-3.8-flash"
TTS = "gemini-3.8-flash-lite-tts"
EARLY = datetime(2026, 10, 13, 8, 0, tzinfo=UTC)  # 0100 PDT: 1/24 of the quota day gone


class NamedGemini(StubBackend):
    """The stub's answers under a Gemini name and model ids, so the budget and pacing apply;
    the tests replace the Duty Officer, so nothing here is ever asked."""

    @property
    def name(self) -> LlmBackendName:
        return "gemini"

    def model_id(self, tier: Tier) -> str:
        return {"main": MAIN, "lite": LITE, "tts": TTS}[tier]


def item(kind: DutyItemKind, subject: str, *, mandatory: bool, urgency: int) -> DutyItem:
    return DutyItem(
        id=f"DI-{kind.value}-{subject}",
        kind=kind,
        subject=subject,
        label=f"{kind.value.title()} {subject}",
        mandatory=mandatory,
        urgency=urgency,
        volcano_id="v2" if kind is DutyItemKind.PLAN else None,
    )


INSIDE = item(DutyItemKind.PLAN, "f1", mandatory=True, urgency=0)
LATER = item(DutyItemKind.PLAN, "f2", mandatory=False, urgency=2)
SRA = item(DutyItemKind.SRA, "java_bali", mandatory=False, urgency=4)


@pytest.fixture
def clock() -> Iterator[FixedClock]:
    fixed = FixedClock(AT)
    with use_clock(fixed):
        yield fixed


@pytest.fixture
async def paced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Any]:
    """A runtime on a 'gemini' backend with a 100-call lite budget, at 0100 PDT; the work list
    is fixed and the Duty Officer is a recorder."""
    settings = make_settings(tmp_path, model_lite_daily_budget=100)
    clock = FixedClock(EARLY)
    runtime = make_runtime(settings, FixtureSource())
    runtime.llm = NamedGemini()
    runtime.ledger = QuotaLedger(settings, runtime.store, now=clock.now)
    runtime.last_tick = TickReport(
        started_at=EARLY, finished_at=EARLY, mode=RunMode.LIVE, reason="t"
    )
    runs: list[tuple[list[str], Lane]] = []

    async def no_drafts(_: Runtime) -> dict[str, list[Any]]:
        return {}

    async def recorder(_: Runtime, items: list[DutyItem], *args: Any, **kwargs: Any) -> None:
        runs.append(([i.id for i in items], current_lane()))

    monkeypatch.setattr(ai_worker_module, "drafts_by_flight", no_drafts)
    monkeypatch.setattr(ai_worker_module, "duty_worklist", lambda *_: [INSIDE, LATER, SRA])
    monkeypatch.setattr(ai_worker_module, "dispatch_duty", recorder)
    yield runtime, clock, runs
    await runtime.aclose()


async def test_urgent_work_runs_and_routine_work_waits_for_its_slot(paced: Any) -> None:
    runtime, clock, runs = paced
    await runtime.worker.drain()

    assert runs == [([INSIDE.id], "urgent")], "urgent work runs first, alone, and is not paced"
    queue = {work.id: work for work in runtime.worker.queue()}
    assert set(queue) == {LATER.id, SRA.id}
    for work in queue.values():
        assert work.status == "WAITING"
        assert work.next_slot_at is not None
        assert work.next_slot_at > EARLY
        assert work.reason == f"waiting for AI budget, next slot {work.next_slot_at:%H%M}Z"
    stored = {doc["id"]: doc["status"] for doc in await runtime.store.list_docs(Collection.AI_WORK)}
    assert stored == {LATER.id: "WAITING", SRA.id: "WAITING"}

    view = await runtime.budget_view()
    assert [work.id for work in view.waiting] == [LATER.id, SRA.id]
    lite = next(model for model in view.models if model.model_id == LITE)
    assert lite.next_routine_slot is None, "one routine call still fits; a whole job does not"

    clock.set(EARLY + timedelta(hours=12))  # past midday Pacific: the routine share has grown
    await runtime.worker.drain()
    assert runs[1] == ([LATER.id, SRA.id], "routine"), "the same work, on the same model"
    assert runtime.worker.queue() == []


async def test_waiting_work_is_offered_to_no_model_until_its_slot(paced: Any) -> None:
    runtime, _, runs = paced
    await runtime.worker.drain()
    await runtime.worker.drain()
    assert len(runs) == 1, "waiting costs no Duty Officer run"


async def test_the_queue_outlives_a_restart(paced: Any, tmp_path: Path) -> None:
    runtime, _, _ = paced
    await runtime.worker.drain()
    runtime.worker.enqueue_recovery(["WIII", "WARR"])
    await runtime.worker._persist()

    restarted = make_runtime(runtime.settings, FixtureSource())
    try:
        await restarted.worker.restore()
        queue = {work.id: work for work in restarted.worker.queue()}
        assert queue[LATER.id].status == "WAITING"
        assert queue[SRA.id].status == "WAITING"
        assert restarted.worker.recovery_queued()
        assert queue[ai_worker_module.RECOVERY_WORK_ID].airports == ["WARR", "WIII"]
    finally:
        await restarted.aclose()


async def test_the_tick_stays_responsive_while_the_ai_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clock: FixedClock
) -> None:
    """The tick used to hold the runtime's lock through the Duty Officer's whole run (11-minute
    tick gaps on the live site). Now a tick runs while a model job is still in flight."""
    runtime = make_runtime(make_settings(tmp_path), FixtureSource())
    started, release = asyncio.Event(), asyncio.Event()
    real_dispatch = ai_worker_module.dispatch_duty

    async def slow_dispatch(*args: Any, **kwargs: Any) -> Any:
        started.set()
        await release.wait()
        return await real_dispatch(*args, **kwargs)

    try:
        first = await run_tick(runtime, reason="manual")
        assert first.drafts_created == 0, "the tick itself makes no model call"
        assert first.duty_runs == 0
        monkeypatch.setattr(ai_worker_module, "dispatch_duty", slow_dispatch)
        work = asyncio.create_task(runtime.worker.drain())
        await asyncio.wait_for(started.wait(), 5)
        second = await asyncio.wait_for(run_tick(runtime, reason="manual"), 10)
        assert not second.skipped
        release.set()
        done = await asyncio.wait_for(work, 30)
        assert done.drafts_created == 1
        assert [a.flight_id for a in await list_advisories(runtime.store)] == [f"{GIA417}:{SEMERU}"]
    finally:
        release.set()
        await runtime.aclose()


async def test_a_plan_made_while_the_area_changed_is_not_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clock: FixedClock
) -> None:
    runtime = make_runtime(make_settings(tmp_path), FixtureSource())
    real_plan = pipeline_module.plan_flight
    changed: list[str] = []

    async def plan_while_the_area_moves(ctx: Any, *args: Any, **kwargs: Any) -> Any:
        if not changed:
            cone = runtime.cones[SEMERU]
            runtime.cones[SEMERU] = cone.model_copy(update={"id": "CONE-moved"})
            changed.append(cone.id)
        return await real_plan(ctx, *args, **kwargs)

    monkeypatch.setattr(pipeline_module, "plan_flight", plan_while_the_area_moves)
    try:
        await run_tick(runtime, reason="manual")
        await runtime.worker.drain()
        assert changed
        assert await list_advisories(runtime.store) == []
        flight_id = f"{GIA417}:{SEMERU}"
        assert flight_id not in runtime._planned, "not marked planned: due again"
        messages = [e.data["message"] for e in runtime.bus.recent(SseEvent.TRACE, limit=200)]
        assert any("the area changed while the flight was planned" in m for m in messages)
    finally:
        await runtime.aclose()


async def test_a_reset_picture_drops_the_queue_and_commits_nothing(paced: Any) -> None:
    runtime, _, _ = paced
    await runtime.worker.drain()
    assert runtime.worker.queue()
    epoch = runtime.epoch
    runtime._reset_picture()
    assert runtime.epoch == epoch + 1
    assert runtime.worker.queue() == []


async def test_urgent_work_runs_while_a_recovery_run_goes_on(
    paced: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review of 28e8b20, item 5: urgent plans waited behind a recovery run for its whole
    length. The recovery run now goes on beside the worker; routine work waits for it."""
    runtime, clock, _ = paced
    clock.set(EARLY + timedelta(hours=12))
    started, release = asyncio.Event(), asyncio.Event()
    runs: list[tuple[list[str], Lane, bool]] = []
    recovered: list[tuple[list[str], Lane, bool]] = []

    async def recorder(_: Runtime, items: list[DutyItem], *args: Any, **kwargs: Any) -> None:
        runs.append(([i.id for i in items], current_lane(), current_admitted()))

    async def slow_recovery(airports: list[str]) -> None:
        recovered.append((list(airports), current_lane(), current_admitted()))
        started.set()
        await release.wait()

    worklist: list[DutyItem] = []
    monkeypatch.setattr(ai_worker_module, "dispatch_duty", recorder)
    monkeypatch.setattr(ai_worker_module, "duty_worklist", lambda *_: list(worklist))
    monkeypatch.setattr(runtime, "recover_queued", slow_recovery)
    report = runtime.worker._report()
    try:
        runtime.worker.enqueue_recovery(["WIII"])
        assert await runtime.worker.work_once(report), "the recovery run starts"
        await asyncio.wait_for(started.wait(), 5)
        assert recovered == [(["WIII"], "routine", True)]

        worklist[:] = [INSIDE, SRA]
        assert await runtime.worker.work_once(report), "urgent work does not wait for it"
        assert runs == [([INSIDE.id], "urgent", False)]
        assert not await runtime.worker.work_once(report), "routine work waits for it"
        queue = {work.id: work.status for work in runtime.worker.queue()}
        assert queue == {SRA.id: "QUEUED", ai_worker_module.RECOVERY_WORK_ID: "RUNNING"}

        release.set()
        await asyncio.wait_for(runtime.worker.drain(), 5)
        assert runs[1] == ([SRA.id], "routine", True), "admitted: pacing no longer cuts it off"
        assert runtime.worker.queue() == []
    finally:
        release.set()


async def test_routine_work_waits_with_the_reason_when_the_budget_cannot_be_read(
    paced: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review of 28e8b20, item 3: with the store down the day's count is unknown, so routine
    work is not admitted on a guess; it waits and says why."""
    runtime, clock, runs = paced
    clock.set(EARLY + timedelta(hours=12))

    async def down(*_: Any) -> Any:
        raise OSError("store down")

    monkeypatch.setattr(runtime.store, "get", down)
    await runtime.worker.drain()
    assert [lane for _, lane in runs] == ["urgent"]
    for work in runtime.worker.queue():
        assert work.status == "WAITING"
        assert work.next_slot_at is None
        assert work.reason is not None
        assert "AI budget store could not be reached" in work.reason
    view = await runtime.budget_view()
    lite = next(model for model in view.models if model.model_id == LITE)
    assert lite.pacing.startswith("Count unknown:")


async def test_the_budget_shows_only_the_lanes_each_model_uses(paced: Any) -> None:
    """Review of 28e8b20, item 7: speech showed urgent and routine lanes and a pacing line,
    though no scheduled work runs on it; the Plume Reader's routine pacing went unexplained."""
    runtime, _, _ = paced
    view = await runtime.budget_view()
    rows = {model.model_id: model for model in view.models}
    assert [lane.lane for lane in rows[TTS].lanes] == ["interactive"]
    assert rows[TTS].next_routine_slot is None
    assert (
        rows[TTS].pacing == "No scheduled work runs on this model: every call is kept for the Desk."
    )
    assert rows[TTS].jobs == "Spoken answers"
    assert [lane.lane for lane in rows[MAIN].lanes] == ["urgent", "routine"]
    assert "13 calls a day, about one every 2 hours" in rows[MAIN].pacing
    assert rows[LITE].jobs == "Every other AI step"
