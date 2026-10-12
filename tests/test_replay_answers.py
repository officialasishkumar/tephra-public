"""Replay answer reuse: a loop of a recording gets the same model's first-pass answer to the
same question, labelled, checked again, and never for a different input; LIVE never reuses."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from test_ai_worker import NamedGemini
from test_drafter import POLICY as DRAFTER_POLICY
from test_drafter import (
    FakeLlm,
    change_level_case,
    make_assessment,
    make_cone,
    make_situation,
)
from test_duty_officer import PLAN_INSIDE, PLAN_LATER, WORKLIST, FakeExecutor
from test_pipeline import SEMERU, FixtureSource, make_runtime, make_settings
from test_planner import GeminiStandIn
from test_planner import make_ctx as planner_ctx

from tephra import pipeline as pipeline_module
from tephra.agents import duty_officer as duty_officer_module
from tephra.agents.dispatch_drafter import (
    RecordedDraft,
    draft_advisory,
    drafter_prompt_hash,
    stub_draft,
)
from tephra.agents.duty_officer import RecordedDuty, run_duty_officer
from tephra.agents.exposure_planner import (
    plan_from_record,
    planner_prompt_hash,
    rule_based_decision,
)
from tephra.config import Settings
from tephra.models import (
    ActionKind,
    DraftText,
    DutyBrief,
    DutyDispatch,
    DutyPriority,
    DutyRun,
    PlannedAction,
    PlannerDecision,
    RunMode,
    TickReport,
)
from tephra.replay.answers import ReplayAnswers, recorded_label
from tephra.scheduler import run_tick
from tephra.store.sqlite_store import SqliteStore
from tephra.util.timeutil import FixedClock, use_clock

AT = datetime(2026, 10, 9, 18, 30, tzinfo=UTC)
LABEL = "AI answer recorded on this replay's first pass at 0912Z real time"


@pytest.fixture
async def store(tmp_path: Path) -> AsyncIterator[SqliteStore]:
    store = SqliteStore(tmp_path / "tephra.sqlite3", tmp_path / "blobs")
    yield store
    await store.aclose()


def test_the_label_names_the_first_pass_time_and_the_day_when_not_today() -> None:
    first = datetime(2026, 10, 13, 9, 12, tzinfo=UTC)
    assert recorded_label(first, datetime(2026, 10, 13, 20, 0, tzinfo=UTC)) == LABEL
    assert recorded_label(first, datetime(2026, 10, 14, 1, 0, tzinfo=UTC)) == (
        "AI answer recorded on this replay's first pass on 13 Oct at 0912Z real time"
    ), "the wall-clock time is said to be one, beside the replay clock"


async def test_an_answer_is_found_only_for_the_same_case_build_job_input_and_model(
    store: SqliteStore,
) -> None:
    answers = ReplayAnswers(store, case_id="case-a", build="abc123")
    await answers.keep("plan", "f1/1", "CONE-1", "lite-model", {"n": 1})
    await answers.keep("plan", "f1/1", "CONE-1", "lite-model", {"n": 2})
    found = await answers.find("plan", "f1/1", "CONE-1", "lite-model")
    assert found is not None
    assert found.payload == {"n": 1}, "the first answer recorded stays"
    assert await answers.find("plan", "f1/1", "CONE-2", "lite-model") is None, "other input"
    assert await answers.find("plan", "f1/1", "CONE-1", "other-model") is None, "other model"
    assert await answers.find("plan", "f2/1", "CONE-1", "lite-model") is None, "other flight"
    other_case = ReplayAnswers(store, case_id="case-b", build="abc123")
    assert await other_case.find("plan", "f1/1", "CONE-1", "lite-model") is None
    new_build = ReplayAnswers(store, case_id="case-a", build="def456")
    assert await new_build.find("plan", "f1/1", "CONE-1", "lite-model") is None


def _recorded_plan(decision: PlannerDecision, question: str | None = None) -> PlannedAction:
    ctx = planner_ctx()
    return PlannedAction(
        id="PLAN-first",
        flight_id=ctx.flight.id,
        cone_id=ctx.flight.cone_id,
        decision=decision,
        llm_backend="gemini",
        model_id="gemini-3.5-flash-lite",
        prompt_hash=question or planner_prompt_hash(ctx),
        outcome="ACCEPTED",
    )


def test_a_recorded_plan_is_reused_only_while_it_passes_the_checks_now() -> None:
    ctx = planner_ctx()
    good = rule_based_decision(ctx)
    with use_clock(FixedClock(AT)):
        reused = plan_from_record(ctx, _recorded_plan(good), label=LABEL)
    assert reused is not None
    assert reused.decision == good
    assert reused.recorded_answer == LABEL
    assert (reused.llm_backend, reused.model_id) == ("gemini", "gemini-3.5-flash-lite")

    failed_screen = PlannerDecision(
        action=ActionKind.DIVERT, alternate_icao="WIII", reasoning="Nearest airport."
    )
    assert plan_from_record(ctx, _recorded_plan(failed_screen), label=LABEL) is None

    moved = ctx.model_copy(
        update={"flight": ctx.flight.model_copy(update={"lon": ctx.flight.lon + 0.5})}
    )
    assert planner_prompt_hash(moved) != planner_prompt_hash(ctx)
    assert plan_from_record(moved, _recorded_plan(good), label=LABEL) is None, (
        "an answer to another question (the flight has moved on) is never reused"
    )


def _gemini_case() -> Any:
    ctx, plan = change_level_case()
    return ctx, plan.model_copy(update={"llm_backend": "gemini", "model_id": "gemini-test-lite"})


async def _draft(llm: FakeLlm, recorded: RecordedDraft | None, plan: Any = None) -> Any:
    situation = make_situation()
    ctx, gemini_plan = _gemini_case()
    plan = plan or gemini_plan
    with use_clock(FixedClock(AT)):
        return await draft_advisory(
            situation=situation,
            assessment=make_assessment(situation),
            cone=make_cone(),
            ctx=ctx,
            plan=plan,
            llm=llm,
            settings=Settings(_env_file=None),
            policy=DRAFTER_POLICY,
            recorded=recorded,
        )


async def test_a_recorded_draft_is_used_only_for_the_same_question_and_says_what_was_reused() -> (
    None
):
    ctx, plan = _gemini_case()
    question = drafter_prompt_hash(ctx, plan)
    draft = stub_draft(ctx, plan)
    llm = FakeLlm("gemini")
    advisory = await _draft(
        llm, RecordedDraft(draft, "gemini-test-lite", "3" * 64, question, LABEL)
    )
    assert llm.calls == 0
    assert advisory.body == draft.body.strip()
    assert advisory.recorded_answer == f"Draft: {LABEL}; the plan was made by the model now"
    assert advisory.llm_backend == "gemini"
    assert advisory.prompt_hashes["drafter"] == "3" * 64

    reused_plan = plan.model_copy(update={"recorded_answer": LABEL})
    llm = FakeLlm("gemini")
    advisory = await _draft(
        llm, RecordedDraft(draft, "gemini-test-lite", "3" * 64, question, LABEL), reused_plan
    )
    assert llm.calls == 0
    assert advisory.recorded_answer == f"Plan and draft: {LABEL}"

    llm = FakeLlm("gemini")
    advisory = await _draft(llm, None, reused_plan)
    assert llm.calls == 1
    assert advisory.recorded_answer == f"Plan: {LABEL}; the draft was written by the model now"

    llm = FakeLlm("gemini")
    other = RecordedDraft(draft, "gemini-test-lite", "3" * 64, "9" * 64, LABEL)
    advisory = await _draft(llm, other)
    assert llm.calls == 1, "a draft that answered another question: the model is asked"
    assert advisory.recorded_answer is None

    stale = DraftText(body="CONTINUE AT FL999.", cost_note="NONE.")
    llm = FakeLlm("gemini")
    advisory = await _draft(
        llm, RecordedDraft(stale, "gemini-test-lite", "3" * 64, question, LABEL)
    )
    assert llm.calls == 1, "a recorded draft that fails the checks now: the model is asked"
    assert advisory.recorded_answer is None


def _first_pass(summary: str) -> DutyRun:
    return DutyRun(
        id="DUTY-first0000001",
        started_at=AT,
        finished_at=AT,
        replay=True,
        trigger="tick",
        worklist=WORKLIST,
        dispatches=[
            DutyDispatch(
                tool="assess_volcanoes", item_ids=["DI-ASSESS-v1-1"], ok=True, result="", ms=1
            ),
            DutyDispatch(
                tool="plan_flights",
                item_ids=[PLAN_INSIDE.id, PLAN_LATER.id],
                ok=True,
                result="",
                ms=1,
            ),
            DutyDispatch(
                tool="run_recovery", item_ids=["DI-RECOVER-network-1"], ok=True, result="", ms=1
            ),
            DutyDispatch(
                tool="draft_sra", item_ids=["DI-SRA-java_bali-1"], ok=True, result="", ms=1
            ),
        ],
        brief=DutyBrief(
            summary=summary,
            priorities=[DutyPriority(item_id=PLAN_INSIDE.id, why="Inside the area now.")],
        ),
        outcome="ACCEPTED",
        llm_backend="gemini",
        model_id="gemini-3.5-flash-lite",
        prompt_hash="4" * 64,
        turns=6,
    )


async def test_a_recorded_duty_run_is_made_again_only_for_the_same_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review of 28e8b20, item 2: a Duty Officer answer was keyed by the work item ids only,
    and reused although the picture digest it answered (budget lines, situation lines) had
    changed. It is keyed by the prompt hash now: instructions, digest and work list."""
    asked: list[str] = []

    async def no_agent(*args: Any, **kwargs: Any) -> None:
        asked.append("agent")

    monkeypatch.setattr(duty_officer_module, "_run_agent", no_agent)
    book: dict[str, RecordedDuty] = {}

    async def recall(question: str) -> RecordedDuty | None:
        return book.get(question)

    digest = "- Semeru (263300): 3 exposed flight(s), 1 inside now"

    async def run(executor: FakeExecutor, digest: str) -> DutyRun:
        with use_clock(FixedClock(AT)):
            return await run_duty_officer(
                WORKLIST,
                executor,
                GeminiStandIn(),
                digest=digest,
                settings=Settings(_env_file=None),
                trigger="tick",
                replay=True,
                recall=recall,
            )

    first = await run(FakeExecutor(), digest)
    assert asked == ["agent"], "nothing recorded yet: the model is asked"
    book[first.prompt_hash] = RecordedDuty(
        _first_pass("Semeru ash; 3 exposed flights handled."), LABEL
    )

    executor = FakeExecutor()
    duty = await run(executor, digest)
    assert asked == ["agent"]
    assert executor.calls == [
        ("assess", "v1"),
        ("plan", "f1"),
        ("plan", "f2"),
        ("recover", "network"),
        ("sra", "java_bali"),
    ]
    assert duty.outcome == "ACCEPTED"
    assert duty.recorded_answer == LABEL
    assert duty.turns == 0
    assert duty.model_id == "gemini-3.5-flash-lite"

    moved = f"{digest}\n- AI budget today, lite (every other AI step): 40 of 450 used"
    duty = await run(FakeExecutor(), moved)
    assert asked == ["agent", "agent"], "the same work in a changed picture: the model is asked"
    assert duty.recorded_answer is None

    book[first.prompt_hash] = RecordedDuty(_first_pass("Semeru ash; 99 flights handled."), LABEL)
    duty = await run(FakeExecutor(), digest)
    assert asked == ["agent"] * 3, "a recorded brief that fails the checks: the model finishes"
    assert duty.recorded_answer is None


async def test_a_replay_loop_reuses_the_plume_read_and_live_never_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = make_runtime(make_settings(tmp_path), FixtureSource())
    try:
        with use_clock(FixedClock(datetime(2026, 10, 9, 19, 40, tzinfo=UTC))):
            await run_tick(runtime, reason="manual")
        situation = runtime.situations[SEMERU]
        runtime.llm = NamedGemini()
        assert await runtime.recorded_answer("assess", SEMERU, situation.input_hash) is None

        first = runtime.assessments[SEMERU].model_copy(
            update={"outcome": "ACCEPTED", "llm_backend": "gemini", "model_id": "m"}
        )
        runtime.mode = RunMode.REPLAY
        answers = ReplayAnswers(runtime.store, case_id="case-a", build=None)
        monkeypatch.setattr(runtime, "_answers", lambda: answers)
        payload = {"assessment": first.model_dump(mode="json"), "satellite": None}
        main = runtime.llm.model_id("main")
        await runtime.keep_answer("assess", SEMERU, "an-earlier-input", main, payload)

        async def not_asked(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("the model was asked")

        monkeypatch.setattr(pipeline_module, "read_plume", not_asked)
        report = TickReport(started_at=AT, finished_at=AT, mode=RunMode.REPLAY, reason="t")
        with pytest.raises(AssertionError, match="the model was asked"):
            await runtime._read_or_reuse(situation, report)  # recorded for another input only

        await runtime.keep_answer("assess", SEMERU, situation.input_hash, main, payload)
        reused = await runtime._read_or_reuse(situation, report)
        assert reused.id == first.id
        assert reused.estimate == first.estimate
        assert reused.recorded_answer is not None
        assert reused.recorded_answer.startswith("AI answer recorded on this replay's first pass")
    finally:
        await runtime.aclose()
