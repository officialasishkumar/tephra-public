"""A replay case folder may carry the answers its model gave on an earlier run
(``answers/ai_answers.jsonl``). A REPLAY runtime seeds them into its store on restore, so a
fresh store, a redeploy or a clone starts where the model has already worked; every recall
still goes through the skill's checks, LIVE never seeds, and the stub's NO MODEL results are
never seeded. Nothing on screen or in the trace says an answer was seeded."""

import json
import shutil
from collections import Counter
from collections.abc import AsyncIterator, Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from test_ai_answers import Agents, Counting
from test_pipeline import (
    AT,
    DATA_DIR,
    POLICY,
    FixtureSource,
    make_runtime,
    make_settings,
    tick_and_work,
)
from test_replay import CASE_ID, record_case, replay_runtime, replay_settings

from tephra.agents import duty_officer as duty_officer_module
from tephra.agents import exposure_planner as planner_module
from tephra.agents.answers import AiAnswers, AnswerScope, Question
from tephra.agents.llm import Tier
from tephra.config import Settings
from tephra.desk.approvals import list_advisories
from tephra.models import RunMode, SseEvent
from tephra.replay.cases import answers_path, case_path
from tephra.store.base import Collection
from tephra.store.sqlite_store import SqliteStore
from tephra.util import timeutil
from tephra.util.timeutil import FixedClock, use_clock

MODEL = "gemini-test"
QUESTION = Question("flight_planner", {"flight": "f1", "cone": "CONE-1"}, timedelta(hours=1))


class Seeding(Counting):
    """The counting stand-in under a model name of its own, so a seeded answer is found only
    by the model that gave it."""

    def model_id(self, tier: Tier) -> str:
        return f"{MODEL}-{tier}"


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    for name in ("volcanoes.json", "airports.json", "routes_apac.json"):
        shutil.copy(DATA_DIR / name, data / name)
    shutil.copytree(DATA_DIR / "policy", data / "policy")
    return data


@pytest.fixture(autouse=True)
def restore_clock() -> Iterator[None]:
    """REPLAY installs a process-wide clock; put back whatever was there before."""
    with use_clock(timeutil.get_clock()):
        yield


@pytest.fixture
def agents(monkeypatch: pytest.MonkeyPatch) -> Agents:
    """The planner and coordinator agents replaced by stand-ins that count their runs (the
    real ones would start ADK against a model)."""
    stand_ins = Agents()
    monkeypatch.setattr(planner_module, "_run_agent", stand_ins.planner)
    monkeypatch.setattr(duty_officer_module, "_run_agent", stand_ins.coordinator)
    return stand_ins


@pytest.fixture
async def scratch(tmp_path: Path) -> AsyncIterator[SqliteStore]:
    store = SqliteStore(tmp_path / "scratch.sqlite3", tmp_path / "scratch-blobs")
    yield store
    await store.aclose()


def write_answers(data_dir: Path, docs: list[dict[str, Any]]) -> Path:
    path = answers_path(case_path(data_dir, CASE_ID))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(doc) + "\n" for doc in docs), encoding="utf-8")
    return path


async def kept_docs(store: SqliteStore) -> list[dict[str, Any]]:
    return await store.list_docs(Collection.AI_ANSWERS, limit=1000)


def asked(llm: Counting, agents: Agents) -> int:
    return sum(llm.asks.values()) + sum(agents.runs.values())


async def test_restore_seeds_the_case_answers_in_replay_only(
    data_dir: Path, tmp_path: Path, scratch: SqliteStore
) -> None:
    case = await record_case(data_dir, tmp_path / "record")
    clock = FixedClock(AT)
    with use_clock(clock):
        # Answers made on an earlier run: a model's, and the stub's NO MODEL result.
        book = AiAnswers(
            scratch,
            Settings(_env_file=None),
            scope=lambda: AnswerScope(RunMode.REPLAY, CASE_ID),
        )
        await book.keep(QUESTION, f"{MODEL}-lite", {"n": 1}, prompt_hash="p" * 64, answered_at=AT)
        await book.keep(QUESTION, "stub", {"n": 0}, prompt_hash="p" * 64, answered_at=AT)
        docs = await kept_docs(scratch)
        assert len(docs) == 2
        path = write_answers(data_dir, docs)
        path.write_text(path.read_text(encoding="utf-8") + "not json\n\n", encoding="utf-8")

        replay = replay_runtime(case, replay_settings(data_dir, tmp_path / "replay"))
        try:
            await replay.restore()
            seeded = await kept_docs(replay.store)
            assert [doc["model_id"] for doc in seeded] == [f"{MODEL}-lite"], "never the stub's"
            [given] = [doc for doc in docs if doc["model_id"] == f"{MODEL}-lite"]
            assert seeded[0]["answered_at"] == given["answered_at"]
            assert seeded[0]["stored_at"] == given["stored_at"], "its own time, kept"
            found = await replay._answer_book.recall(QUESTION, f"{MODEL}-lite")
            assert found is not None
            assert found.payload == {"n": 1}
            assert await replay._answer_book.recall(QUESTION, "stub") is None
            trace = [event.data for event in replay.bus.recent(SseEvent.TRACE, limit=50)]
            assert trace == [], "nothing in the trace announces the seed"
        finally:
            await replay.aclose()

    with use_clock(clock):
        live = make_runtime(make_settings(tmp_path / "live", data_dir=data_dir), FixtureSource())
        try:
            await live.restore()
            assert await kept_docs(live.store) == [], "LIVE restores from its store alone"
        finally:
            await live.aclose()

    path.unlink()
    with use_clock(clock):
        bare = replay_runtime(case, replay_settings(data_dir, tmp_path / "bare"))
        try:
            await bare.restore()
            assert await kept_docs(bare.store) == [], "a case without the file seeds nothing"
        finally:
            await bare.aclose()


MINUTES = (0, 2, 4)
"""The replay minutes each loop plays (the recording holds two ticks a minute apart), inside
the policy's ``duty.rerun_min``: deferred work is offered to the Coordinator again after it,
so a longer loop asks the Coordinator again by policy, not for want of a kept answer."""


def shown(drafts: list[Any]) -> list[tuple[str, str, Any]]:
    """What the Desk shows of a draft: the flight, the text and when it was written."""
    return [(d.flight_id, d.body, d.drafted_at) for d in drafts if d.status == "DRAFT"]


async def play(runtime: Any, clock: FixedClock) -> dict[int, list[tuple[str, str, Any]]]:
    """One loop over :data:`MINUTES`; the open drafts after each minute."""
    drafts: dict[int, list[tuple[str, str, Any]]] = {}
    for minutes in MINUTES:
        clock.set(AT + timedelta(minutes=minutes))
        await tick_and_work(runtime, reason="manual")
        drafts[minutes] = shown(await list_advisories(runtime.store))
    return drafts


def same_drafts(
    played: dict[int, list[tuple[str, str, Any]]], cold: dict[int, list[tuple[str, str, Any]]]
) -> bool:
    """Every minute drafts the same flights, written when they were written; the text is
    compared where the loop has converged (its last minute): a kept body is the model's latest
    for the question, so the minute a draft is first made may already show the later wording."""
    minutes = all(
        [(flight, at) for flight, _, at in played[m]] == [(flight, at) for flight, _, at in cold[m]]
        for m in MINUTES
    )
    return minutes and played[MINUTES[-1]] == cold[MINUTES[-1]]


async def test_a_replay_with_seeded_answers_re_issues_its_drafts_after_a_loop(
    data_dir: Path, tmp_path: Path, agents: Agents
) -> None:
    case = await record_case(data_dir, tmp_path / "record")
    clock = FixedClock(AT)
    with use_clock(clock):  # a REPLAY runtime's aclose() puts the system clock back
        # Loop 1, cold: the model (the counting stand-in) is asked, and its answers kept.
        first = replay_runtime(case, replay_settings(data_dir, tmp_path / "first"))
        first.llm = llm = Seeding()
        first.worker.paced = False
        try:
            cold = await play(first, clock)
            docs = await kept_docs(first.store)
        finally:
            await first.aclose()
    assert cold[0], "the fixture flight is drafted"
    assert {drafted_at for _, _, drafted_at in cold[0]} == {AT}
    assert cold[MINUTES[-1]] != cold[0], "the flight moves on, and its draft with it"
    assert max(MINUTES) < POLICY.duty.rerun_min.value
    assert asked(llm, agents) > 0
    assert {doc["skill"] for doc in docs} >= {"plume_reader", "flight_planner", "drafter"}
    assert all(doc["model_id"].startswith(MODEL) for doc in docs)
    write_answers(data_dir, docs)
    runs_before = sum(agents.runs.values())

    with use_clock(clock):
        # A fresh store (a redeploy, a clone): seeded on restore, the loop asks nothing.
        second = replay_runtime(case, replay_settings(data_dir, tmp_path / "second"))
        second.llm = llm2 = Seeding()
        second.worker.paced = False
        try:
            await second.restore()
            assert len(await kept_docs(second.store)) == len(docs)
            warm = await play(second, clock)
            assert same_drafts(warm, cold), "the same drafts, written when they were written"

            clock.set(AT)  # the recording ran out and the clock wrapped to its start
            report = await tick_and_work(second, reason="manual")
            assert any("from the start" in note for note in report.notes)
            wrapped = await play(second, clock)
            assert same_drafts(wrapped, cold), "and again after the loop"

            assert sum(llm2.asks.values()) == 0, "every structured answer was on hand"
            assert llm2.reserved == 0, "and no budget spent"
            assert sum(agents.runs.values()) == runs_before, "nor the planner's or coordinator's"
            trace = " ".join(
                str(event.data.get("message", ""))
                for event in second.bus.recent(SseEvent.TRACE, limit=500)
            )
            assert "seed" not in trace.lower()
            assert Counter(doc["skill"] for doc in await kept_docs(second.store)) == Counter(
                doc["skill"] for doc in docs
            ), "the seeded answers stand; nothing was asked and kept anew"
        finally:
            await second.aclose()
