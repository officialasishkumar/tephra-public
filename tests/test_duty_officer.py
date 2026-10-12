"""The Duty Officer: the coordinator that hands each tick's AI work to the specialist agents.

Its ADK path runs offline against the scripted model of ``test_planner`` (the real
``LlmAgent``, ``FunctionTool`` wrapping and ``InMemoryRunner``, no key and no network).
Code holds the safety line around it: plume reads before plans, no deferring mandatory
work, a checked brief, and mandatory work left undone sent to the Desk.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from test_drafter import make_assessment, make_situation
from test_pipeline import GIA417, SEMERU, FixtureSource, make_runtime, make_settings, tick_and_work
from test_planner import _CALLS, _SCRIPT, GeminiStandIn, Turn, call, text

from tephra import ai_worker as ai_worker_module
from tephra import duty as duty_module
from tephra.agents.duty_officer import DutyToolkit, run_duty_officer, validate_brief
from tephra.agents.llm import StubBackend
from tephra.config import Settings
from tephra.desk.approvals import list_advisories
from tephra.desk.failures import list_failures
from tephra.models import (
    DutyBrief,
    DutyItem,
    DutyItemKind,
    DutyPriority,
    DutyRun,
    OfficialLayer,
    PlumeMode,
    TraceEvent,
    polygon_from_latlon,
)
from tephra.pipeline import Runtime, _holds_while_pending
from tephra.util.timeutil import FixedClock, use_clock

AT = datetime(2026, 10, 9, 19, 40, tzinfo=UTC)
SCRIPTED_MODEL = "tephra-scripted-duty"


@pytest.fixture(autouse=True)
def script() -> Iterator[list[Turn]]:
    _SCRIPT.clear()
    _CALLS.clear()
    yield _SCRIPT
    _SCRIPT.clear()


@pytest.fixture(autouse=True)
def clock() -> Iterator[FixedClock]:
    fixed = FixedClock(AT)
    with use_clock(fixed):
        yield fixed


def item(
    kind: DutyItemKind,
    subject: str,
    *,
    mandatory: bool = False,
    urgency: int = 2,
    volcano_id: str | None = None,
    version: str = "1",
) -> DutyItem:

    return DutyItem(
        id=f"DI-{kind.value}-{subject}-{version}",
        kind=kind,
        subject=subject,
        label=f"{kind.value.title()} {subject}",
        mandatory=mandatory,
        urgency=urgency,
        volcano_id=volcano_id,
    )


ASSESS = item(DutyItemKind.ASSESS, "v1", mandatory=True, urgency=0, volcano_id="v1")
PLAN_INSIDE = item(DutyItemKind.PLAN, "f1", mandatory=True, urgency=0, volcano_id="v1")
PLAN_LATER = item(DutyItemKind.PLAN, "f2", urgency=3, volcano_id="v2")
RECOVER = item(DutyItemKind.RECOVER, "network", urgency=3)
SRA = item(DutyItemKind.SRA, "java_bali", urgency=4)
WORKLIST = [ASSESS, PLAN_INSIDE, PLAN_LATER, RECOVER, SRA]


class FakeExecutor:
    """The specialists, as code-written results; ``new_items`` come back from an assess."""

    def __init__(self, new_items: list[DutyItem] | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.new_items = new_items or []

    async def assess(self, volcano_id: str) -> tuple[dict[str, Any], list[DutyItem]]:
        self.calls.append(("assess", volcano_id))
        summary = f"{volcano_id}: WIDENED 62% SFC/FL300; 2 flight(s) exposed"
        return {"volcano_id": volcano_id, "summary": summary, "status": "ok"}, self.new_items

    async def plan(self, flight_id: str) -> dict[str, Any]:
        self.calls.append(("plan", flight_id))
        return {"flight_id": flight_id, "summary": f"{flight_id}: DRAFT HOLD for a dispatcher"}

    async def recover(self) -> dict[str, Any]:
        self.calls.append(("recover", "network"))
        return {"summary": "Recovery agent started for WIII"}

    async def draft_sra(self, region: str) -> dict[str, Any]:
        self.calls.append(("sra", region))
        return {"summary": f"SRA draft DOC-1 for {region}"}


def toolkit(executor: FakeExecutor | None = None) -> DutyToolkit:
    kit = DutyToolkit.of(WORKLIST, executor or FakeExecutor(), trace=None)
    kit.evidence.append("- Semeru (263300): 3 exposed flight(s), 1 inside now; RFA4238")
    return kit


def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        llm="gemini",
        GEMINI_API_KEY="test-key",
        model_lite=SCRIPTED_MODEL,
        cache_dir=tmp_path / "cache",
    )


def brief_call(ids: list[str], summary: str = "Semeru ash; 3 exposed flights handled.") -> Turn:
    return call(
        "submit_brief",
        summary=summary,
        priority_item_ids=ids,
        priority_reasons=["protects a flight" for _ in ids],
        watch=["Semeru drift against the official area"],
    )


# --- the toolkit's rules --------------------------------------------------------------------


async def test_a_flight_waits_for_its_volcanos_plume_read() -> None:
    """Plans made on an old area are wasted: code refuses them until the read is done."""
    executor = FakeExecutor()
    kit = toolkit(executor)
    refused = await kit.plan_flights(["f1"])
    assert refused["results"][0]["error"].startswith("ASSESS VOLCANO v1 FIRST")
    assert executor.calls == []
    await kit.assess_volcanoes(["v1"])
    planned = await kit.plan_flights(["f1", "f2", "f1"])
    assert [r["flight_id"] for r in planned["results"]] == ["f1", "f2"]
    assert executor.calls == [("assess", "v1"), ("plan", "f1"), ("plan", "f2")]
    assert kit.undispatched_mandatory() == []


async def test_a_new_cone_replaces_the_older_plan_item_for_the_same_flight() -> None:
    """The read rebuilt the cone: f1's new item supersedes the old one, which no longer counts
    as mandatory work left undone."""
    newer = item(DutyItemKind.PLAN, "f1", mandatory=True, urgency=0, volcano_id="v1", version="2")
    kit = toolkit(FakeExecutor(new_items=[newer]))
    result = await kit.assess_volcanoes(["v1"])
    assert [view["item_id"] for view in result["results"][0]["new_plan_items"]] == [newer.id]
    assert PLAN_INSIDE.id in kit.replaced
    assert [i.id for i in kit.undispatched_mandatory()] == [newer.id]
    assert PLAN_INSIDE.id not in {i.id for i in kit.worklist()}


def test_mandatory_work_cannot_be_deferred_and_a_deferral_needs_a_reason() -> None:
    kit = toolkit()
    result = kit.defer([PLAN_INSIDE.id, RECOVER.id, "DI-unknown"], "budget low, flights first")
    assert result["deferred"] == [RECOVER.id]
    errors = {entry["item_id"]: entry["error"] for entry in result["refused"]}
    assert errors == {
        PLAN_INSIDE.id: "MANDATORY: DISPATCH IT THIS RUN",
        "DI-unknown": "NOT AN OPEN ITEM",
    }
    assert kit.defer([SRA.id], "   ")["refused"] == [{"item_id": SRA.id, "error": "GIVE A REASON"}]


def test_digits_inside_ids_and_hashes_are_not_evidence() -> None:
    """A number the model made up must not pass because it sits inside an id or a hash."""
    kit = toolkit()
    kit.evidence.append('{"cone_id": "CONE-9876543210ab", "flight_id": "8a0123:263300"}')
    brief = DutyBrief(
        summary="Semeru ash: 9 flights exposed.",
        priorities=[DutyPriority(item_id=PLAN_INSIDE.id, why="inside the area now")],
    )
    assert validate_brief(brief, kit) == ["NUMBER 9 IN SUMMARY IS NOT IN THE INPUT"]


def test_a_brief_uses_only_what_the_officer_was_shown() -> None:
    kit = toolkit()
    good = DutyBrief(
        summary="Semeru ash: 3 exposed flights, 1 inside now; RFA4238 first.",
        priorities=[DutyPriority(item_id=PLAN_INSIDE.id, why="inside the area now")],
        watch=["Semeru drift"],
    )
    assert validate_brief(good, kit) == []
    bad = DutyBrief(
        summary="Semeru ash at 1830 UTC: 7 flights exposed, RFA9999 first.",
        priorities=[
            DutyPriority(item_id="DI-nope", why="x"),
            DutyPriority(item_id=SRA.id, why=""),
        ],
        watch=["a", "b", "c", "d", "e"],
    )
    problems = validate_brief(bad, kit)
    assert "UNKNOWN ITEM DI-nope IN PRIORITIES" in problems
    assert "NUMBER 7 IN SUMMARY IS NOT IN THE INPUT" in problems
    assert "FLIGHT RFA9999 IN SUMMARY IS NOT IN THE INPUT" in problems
    assert any("CLOCK" in problem or "TIME" in problem for problem in problems)
    assert f"REASON FOR {SRA.id} EMPTY OR LONGER THAN 160" in problems
    assert "MORE THAN 4 WATCH ITEMS" in problems


# --- runs -------------------------------------------------------------------------------------


async def test_offline_stub_dispatches_everything_most_urgent_first(tmp_path: Path) -> None:
    executor = FakeExecutor()
    duty = await run_duty_officer(
        WORKLIST,
        executor,
        StubBackend(),
        digest="- picture",
        settings=Settings(_env_file=None),
        trigger="tick",
        replay=False,
    )
    assert duty.outcome == "STUB"
    assert executor.calls == [
        ("assess", "v1"),
        ("plan", "f1"),
        ("plan", "f2"),
        ("recover", "network"),
        ("sra", "java_bali"),
    ]
    assert duty.undispatched == []
    assert duty.brief is not None
    assert duty.brief.summary.startswith("NO MODEL:")


async def test_the_duty_officer_delegates_defers_and_briefs(
    script: list[Turn], tmp_path: Path
) -> None:
    script += [
        call("assess_volcanoes", volcano_ids=["v1"]),
        call("plan_flights", flight_ids=["f1", "f2"]),
        call("defer", item_ids=[RECOVER.id, SRA.id], reason="flights first, budget kept"),
        brief_call([PLAN_INSIDE.id, PLAN_LATER.id]),
    ]
    executor = FakeExecutor()
    events: list[TraceEvent] = []
    duty = await run_duty_officer(
        WORKLIST,
        executor,
        GeminiStandIn(),
        digest="- Semeru: 3 exposed flight(s)",
        settings=settings(tmp_path),
        trigger="tick",
        replay=False,
        trace=events.append,
    )
    assert duty.outcome == "ACCEPTED", duty.validation_errors
    assert executor.calls == [("assess", "v1"), ("plan", "f1"), ("plan", "f2")]
    assert [d.tool for d in duty.dispatches] == ["assess_volcanoes", "plan_flights", "plan_flights"]
    assert {d.item_id for d in duty.deferred} == {RECOVER.id, SRA.id}
    assert duty.undispatched == []
    assert duty.brief is not None
    assert [p.item_id for p in duty.brief.priorities] == [PLAN_INSIDE.id, PLAN_LATER.id]
    assert duty.turns == 5
    assert any(e.message.startswith("Duty Officer -> plan_flights") for e in events)
    assert events[-1].message.startswith("Duty Officer brief")


async def test_mandatory_work_left_undone_gets_one_repair_turn(
    script: list[Turn], tmp_path: Path
) -> None:
    script += [
        brief_call([PLAN_LATER.id]),  # briefs at once, leaving the mandatory items
        text("Done."),
        call("assess_volcanoes", volcano_ids=["v1"]),
        call("plan_flights", flight_ids=["f1"]),
        brief_call([PLAN_INSIDE.id]),
        text("Done."),
    ]
    duty = await run_duty_officer(
        WORKLIST,
        FakeExecutor(),
        GeminiStandIn(),
        digest="- Semeru: 3 exposed flight(s)",
        settings=settings(tmp_path),
        trigger="tick",
        replay=False,
    )
    assert duty.outcome == "REPAIRED"
    assert duty.undispatched == []
    repair = _CALLS[2].contents[-1].parts[0].text or ""
    assert "Mandatory items are still undone" in repair
    assert PLAN_INSIDE.id in repair


async def test_a_model_error_leaves_mandatory_work_for_the_desk(
    script: list[Turn], tmp_path: Path
) -> None:
    script += [call("plan_flights", flight_ids=["f2"]), RuntimeError("model unavailable")]
    executor = FakeExecutor()
    duty = await run_duty_officer(
        WORKLIST,
        executor,
        GeminiStandIn(),
        digest="- Semeru",
        settings=settings(tmp_path),
        trigger="tick",
        replay=False,
    )
    assert duty.outcome == "MODEL_FAILED"
    assert duty.brief is None
    assert executor.calls == [("plan", "f2")]  # what was dispatched stands
    assert set(duty.undispatched) == {ASSESS.id, PLAN_INSIDE.id}
    assert duty.validation_errors == ["DUTY OFFICER ERROR: RuntimeError"]


async def test_no_budget_makes_no_model_call(script: list[Turn], tmp_path: Path) -> None:
    script += [call("assess_volcanoes", volcano_ids=["v1"])]
    duty = await run_duty_officer(
        WORKLIST,
        FakeExecutor(),
        GeminiStandIn(budget_left=False),
        digest="- Semeru",
        settings=settings(tmp_path),
        trigger="tick",
        replay=False,
    )
    assert _CALLS == []
    assert duty.outcome == "MODEL_FAILED"
    assert "budget_exhausted" in duty.validation_errors
    assert set(duty.undispatched) == {ASSESS.id, PLAN_INSIDE.id}


# --- in the pipeline --------------------------------------------------------------------------


@pytest.fixture
async def runtime(tmp_path: Path) -> Any:
    made = make_runtime(make_settings(tmp_path), FixtureSource())
    yield made
    await made.aclose()


async def test_a_flight_the_duty_officer_leaves_undone_goes_to_the_desk(
    runtime: Runtime, clock: FixedClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No substitute dispatcher: the inside flight gets no draft, one AI failure, and the work
    is offered again only after duty.rerun_min."""
    offered: list[list[DutyItem]] = []

    async def idle_officer(worklist: list[DutyItem], *args: Any, **kwargs: Any) -> DutyRun:
        offered.append(list(worklist))
        return DutyRun(
            id="DUTY-000000000001",
            started_at=clock.now(),
            finished_at=clock.now(),
            replay=False,
            trigger=kwargs["trigger"],
            worklist=list(worklist),
            outcome="MODEL_FAILED",
            llm_backend="gemini",
            model_id="gemini-test-lite",
            prompt_hash="0" * 64,
            validation_errors=["budget_exhausted"],
            undispatched=[i.id for i in worklist if i.mandatory],
        )

    monkeypatch.setattr(duty_module, "run_duty_officer", idle_officer)
    report = await tick_and_work(runtime, reason="manual")
    assert report.duty_runs >= 1
    assert report.drafts_created == 0
    assert await list_advisories(runtime.store) == []
    plan_items = [i for i in offered[0] if i.kind is DutyItemKind.PLAN]
    assert [i.subject for i in plan_items] == [f"{GIA417}:{SEMERU}"]
    assert all(i.mandatory for i in offered[0]), "the urgent run comes first, on its own"
    failures = await list_failures(runtime.store)
    assert [(f.stage, f.flight_id) for f in failures] == [("duty_officer", f"{GIA417}:{SEMERU}")]
    assert failures[0].reason == "DUTY OFFICER AI UNAVAILABLE: budget_exhausted"

    runs = len(offered)
    assert (await runtime.worker.drain()).duty_runs == 0, "nothing new: no model call"
    clock.advance(timedelta(minutes=runtime.policy.duty.rerun_min.value))
    assert (await runtime.worker.drain()).duty_runs >= 1
    assert len(offered) > runs


def reading(mode: PlumeMode, *, outcome: str = "ACCEPTED") -> Any:
    """A Semeru reading, and the situation it was made in with a valid official area."""
    plain = make_situation()
    layer = OfficialLayer(
        source_id="SIGMET-WAAF-3",
        kind="SIGMET",
        layer="SIGMET",
        label="SIGMET WAAF 3",
        volcano_id=plain.volcano.id,
        polygon=polygon_from_latlon([(-8.0, 112.8), (-8.0, 113.2), (-8.4, 113.2), (-8.4, 112.8)]),
        base_ft=0,
        top_ft=15_000,
        valid_from=AT - timedelta(minutes=30),
        valid_to=AT + timedelta(hours=5),
    )
    situation = plain.model_copy(update={"as_of": AT, "official_layers": [layer]})
    base = make_assessment(situation)
    estimate = base.estimate.model_copy(update={"mode": mode, "horizon_h": 6})
    return situation, base.model_copy(
        update={"estimate": estimate, "created_at": AT, "outcome": outcome}
    )


async def test_a_volcano_with_a_mandatory_flight_has_a_mandatory_plume_read(
    runtime: Runtime, clock: FixedClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plans wait for the read, so the read cannot be deferred while a flight is urgent."""

    async def no_dispatch(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(ai_worker_module, "dispatch_duty", no_dispatch)
    report = await tick_and_work(runtime, reason="manual")
    assert report.exposed_flights == 1
    semeru = runtime.situations[SEMERU]
    runtime.assess_due[SEMERU] = semeru.input_hash
    items = duty_module.duty_worklist(runtime, clock.now(), {})
    assess = next(i for i in items if i.kind is DutyItemKind.ASSESS and i.subject == SEMERU)
    plans = [i for i in items if i.kind is DutyItemKind.PLAN and i.volcano_id == SEMERU]
    assert any(plan.mandatory for plan in plans)
    assert assess.mandatory
    assert assess.urgency == 0


def test_a_last_reading_holds_the_area_only_while_it_fits_the_official_products() -> None:
    situation, widened = reading(PlumeMode.WIDENED)  # an official area is valid
    assert _holds_while_pending(widened, situation, AT + timedelta(hours=1))
    assert not _holds_while_pending(widened, situation, AT + timedelta(hours=6))
    _, hypothesis = reading(PlumeMode.HYPOTHESIS)
    assert not _holds_while_pending(hypothesis, situation, AT + timedelta(hours=1))
    _, pending = reading(PlumeMode.OFFICIAL, outcome="PENDING")
    assert not _holds_while_pending(pending, situation, AT + timedelta(hours=1))
