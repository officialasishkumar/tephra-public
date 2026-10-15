"""The models' kept answers: a model is asked again only when something material changed.

A kept answer is the same model's answer to materially the same question, checked again by the
same validators against the input of the moment, and keeps the time it was given. When it no
longer passes, the model is asked as usual; when the model cannot be asked, the step reports
AI UNAVAILABLE and the kept answer is never shown. LIVE and REPLAY (and each replay case) keep
apart, and nothing in the UI announces any of it.
"""

import re
from collections import Counter
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel
from test_ai_worker import EARLY, LATER, NamedGemini
from test_ask import make_runtime as ask_runtime
from test_drafter import POLICY as DRAFTER_POLICY
from test_drafter import change_level_case, make_assessment, make_cone, make_situation
from test_duty_officer import ASSESS, PLAN_LATER, SRA, WORKLIST, FakeExecutor
from test_pipeline import GIA417, SEMERU, FixtureSource, make_draft, make_runtime, make_settings
from test_planner import make_ctx as planner_ctx

from tephra import ai_worker as ai_worker_module
from tephra.agents import answers as answers_module
from tephra.agents import ask as ask_module
from tephra.agents import duty_officer as duty_officer_module
from tephra.agents import exposure_planner as planner_module
from tephra.agents.answers import (
    KEY_VERSION,
    AiAnswer,
    AiAnswers,
    AnswerScope,
    NotOnHand,
    Question,
    Reuse,
    on_hand_only,
)
from tephra.agents.ask import AskAnswer, AskClaim, AskReply, answer_question
from tephra.agents.dispatch_drafter import draft_advisory, drafter_question
from tephra.agents.duty_officer import (
    OUTCOME_KEYS,
    DutyToolkit,
    coordinator_question,
    run_duty_officer,
)
from tephra.agents.exposure_planner import (
    plan_flight,
    plan_key,
    planner_question,
    rule_based_decision,
)
from tephra.agents.llm import BUDGET_EXHAUSTED, LlmCall, StubBackend, Tier, prompt_hash
from tephra.agents.notice_reader import notice_question
from tephra.agents.plume_reader import plume_question
from tephra.agents.quota import QuotaLedger, current_admitted, current_lane
from tephra.agents.satellite_reader import satellite_question
from tephra.comms.messages import crew_notice_spec, templates_question
from tephra.config import PROJECT_ROOT, Settings
from tephra.desk.approvals import list_advisories
from tephra.models import (
    ActionKind,
    Advisory,
    AiFailure,
    Discrepancy,
    DiscrepancyKind,
    DraftText,
    DutyBrief,
    DutyItem,
    DutyItemKind,
    DutyRun,
    FeedId,
    FrameProduct,
    LlmBackendName,
    PlannerDecision,
    Provenance,
    RerouteKind,
    RerouteOption,
    RerouteStatus,
    RunMode,
    SatelliteFrame,
    SupportingEvidence,
    TickReport,
    TraceEvent,
)
from tephra.pipeline import Runtime
from tephra.scheduler import run_tick
from tephra.store.base import Collection
from tephra.store.firestore_store import DOC_FIELD, FirestoreStore
from tephra.store.sqlite_store import SqliteStore
from tephra.util.timeutil import FixedClock, SystemClock, use_clock

AT = datetime(2026, 10, 9, 18, 30, tzinfo=UTC)
HOUR = timedelta(hours=1)
WEB = PROJECT_ROOT / "tephra" / "web"


# --- stand-ins ------------------------------------------------------------------------


class Counting(StubBackend):
    """The stub's answers under a model's name; counts every ask and every budget reservation.
    ``refuse`` plays the assistant paused: no ask gets an answer."""

    def __init__(self, *, refuse: bool = False) -> None:
        self.asks: Counter[str] = Counter()
        self.reserved = 0
        self.refuse = refuse

    @property
    def name(self) -> LlmBackendName:
        return "gemini"

    def model_id(self, tier: Tier) -> str:
        return f"counting-{tier}"

    async def reserve(self, tier: Tier) -> str | None:
        self.reserved += 1
        return BUDGET_EXHAUSTED if self.refuse else None

    async def structured[T: BaseModel](
        self,
        *,
        tier: Tier,
        system: str,
        parts: Sequence[Any],
        schema: type[T],
        stub: Callable[[], T],
        temperature: float | None = None,
    ) -> tuple[T | None, LlmCall]:
        self.asks[schema.__name__] += 1
        call = LlmCall(
            backend="gemini", model_id=self.model_id(tier), prompt_hash=prompt_hash(system, parts)
        )
        if self.refuse:
            return None, call.model_copy(update={"error": BUDGET_EXHAUSTED})
        value = schema.model_validate(stub().model_dump())
        return value, call.model_copy(update={"raw_text": value.model_dump_json()})


@dataclass
class Agents:
    """The planner and the Duty Officer agents, replaced by stand-ins that count their runs."""

    runs: Counter[str] = field(default_factory=Counter)
    refuse: bool = False

    async def planner(self, ctx: Any, llm: Any, run: Any, **_: Any) -> None:
        self.runs["planner"] += 1
        if self.refuse:
            run.problems = ["AI BUDGET EXHAUSTED"]
            return
        run.decision = rule_based_decision(ctx)

    async def coordinator(self, toolkit: Any, llm: Any, run: Any, task: str, _: Any) -> None:
        self.runs["coordinator"] += 1
        if self.refuse:
            run.problems = ["AI BUDGET EXHAUSTED"]
            return
        await toolkit.assess_volcanoes([i.subject for i in toolkit.pending(DutyItemKind.ASSESS)])
        await toolkit.plan_flights([i.subject for i in toolkit.pending(DutyItemKind.PLAN)])
        for item in toolkit.pending(DutyItemKind.SRA):
            toolkit.defer([item.id], "Flights first.")
        if toolkit.pending(DutyItemKind.RECOVER):
            await toolkit.run_recovery()
        order = [item.id for item in toolkit.worklist() if item.id not in toolkit.deferred]
        toolkit.submit_brief("Flights first, then the rest.", order, ["Urgent."] * len(order), [])
        run.turns = 3


@pytest.fixture
def agents(monkeypatch: pytest.MonkeyPatch) -> Agents:
    stand_ins = Agents()
    monkeypatch.setattr(planner_module, "_run_agent", stand_ins.planner)
    monkeypatch.setattr(duty_officer_module, "_run_agent", stand_ins.coordinator)
    return stand_ins


@dataclass
class Scope:
    now: AnswerScope = field(default_factory=lambda: AnswerScope(RunMode.LIVE, None))

    def __call__(self) -> AnswerScope:
        return self.now


@pytest.fixture
async def sqlite(tmp_path: Path) -> AsyncIterator[SqliteStore]:
    store = SqliteStore(tmp_path / "tephra.sqlite3", tmp_path / "blobs")
    yield store
    await store.aclose()


def book_on(store: Any, scope: Scope | None = None, **settings: Any) -> AiAnswers:
    return AiAnswers(store, Settings(_env_file=None, **settings), scope=scope or Scope())


@pytest.fixture
def clock() -> Iterator[FixedClock]:
    fixed = FixedClock(AT)
    with use_clock(fixed):
        yield fixed


QUESTION = Question("flight_planner", {"flight": "f1", "cone": "CONE-1"}, HOUR)


# --- the store: SQLite and Firestore ----------------------------------------------------


async def test_an_answer_is_found_only_in_its_mode_case_and_model(
    sqlite: SqliteStore, clock: FixedClock
) -> None:
    scope = Scope()
    book = book_on(sqlite, scope)
    await book.keep(QUESTION, "lite", {"n": 1}, prompt_hash="p" * 64, answered_at=AT)
    found = await book.recall(QUESTION, "lite")
    assert found is not None
    assert found.payload == {"n": 1}
    assert await book.recall(QUESTION, "other-model") is None
    assert await book.recall(QUESTION._replace(material={"flight": "f2"}), "lite") is None

    scope.now = AnswerScope(RunMode.REPLAY, "case-a")
    assert await book.recall(QUESTION, "lite") is None, "LIVE answers never serve a replay"
    await book.keep(QUESTION, "lite", {"n": 2}, prompt_hash="p" * 64, answered_at=AT)
    scope.now = AnswerScope(RunMode.REPLAY, "case-b")
    assert await book.recall(QUESTION, "lite") is None, "nor one case another"
    scope.now = AnswerScope(RunMode.LIVE, None)
    live = await book.recall(QUESTION, "lite")
    assert live is not None
    assert live.payload == {"n": 1}, "nor a replay LIVE"

    new_build = book_on(sqlite, Scope(), build_sha="def456")
    found_again = await new_build.recall(QUESTION, "lite")
    assert found_again is not None, "a new build finds what the last one kept"
    assert found_again.payload == {"n": 1}
    assert found_again.build == "local", "the build it was given under stays on record"


async def test_a_replay_answer_outlives_the_live_limit(
    sqlite: SqliteStore, clock: FixedClock
) -> None:
    scope = Scope(AnswerScope(RunMode.REPLAY, "case-a"))
    book = book_on(sqlite, scope)
    await book.keep(QUESTION, "lite", {"n": 1}, prompt_hash="p", answered_at=AT)
    replay = await book.recall(QUESTION, "lite")
    assert replay is not None
    assert replay.expires_at - replay.stored_at == timedelta(hours=2160)

    scope.now = AnswerScope(RunMode.LIVE, None)
    await book.keep(QUESTION, "lite", {"n": 2}, prompt_hash="p", answered_at=AT)
    live = await book.recall(QUESTION, "lite")
    assert live is not None
    assert live.expires_at - live.stored_at == min(timedelta(hours=72), HOUR)
    forever = Question("notice_reader", {"text": "abc"})
    await book.keep(forever, "lite", {"n": 3}, prompt_hash="p", answered_at=AT)
    notice = await book.recall(forever, "lite")
    assert notice is not None
    assert notice.expires_at - notice.stored_at == timedelta(hours=72)


async def test_a_new_key_version_never_reads_an_old_key(
    sqlite: SqliteStore, clock: FixedClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    await book_on(sqlite).keep(QUESTION, "lite", {"n": 1}, prompt_hash="p", answered_at=AT)
    assert await book_on(sqlite).recall(QUESTION, "lite") is not None
    monkeypatch.setattr(answers_module, "KEY_VERSION", KEY_VERSION + 1)
    assert await book_on(sqlite).recall(QUESTION, "lite") is None, "an older recipe: asked afresh"
    assert len(await sqlite.list_docs(Collection.AI_ANSWERS)) == 1, "the old answer is left alone"


# --- seeded answers (a case folder's answers/ai_answers.jsonl) ---------------------------

CASE = AnswerScope(RunMode.REPLAY, "case-a")
MODEL = "gemini-test"


async def _lines_kept_by(
    store: Any, *answers: tuple[Question, str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """The answers an earlier run kept, as the lines of its ``ai_answers.jsonl``."""
    book = book_on(store, Scope(CASE))
    for question, model_id, payload in answers:
        await book.keep(question, model_id, payload, prompt_hash="p" * 64, answered_at=AT)
    return await store.list_docs(Collection.AI_ANSWERS)


async def test_seeded_answers_are_found_under_the_current_key_recipe(
    tmp_path: Path, sqlite: SqliteStore, clock: FixedClock
) -> None:
    earlier = SqliteStore(tmp_path / "earlier.sqlite3", tmp_path / "earlier-blobs")
    other = Question("drafter", {"flight": "f1", "action": "HOLD"}, HOUR)
    lines = await _lines_kept_by(earlier, (QUESTION, MODEL, {"n": 1}), (other, MODEL, {"n": 2}))
    await earlier.aclose()
    assert len(lines) == 2
    (kept,) = [line for line in lines if line["payload"] == {"n": 1}]

    book = book_on(sqlite, Scope(CASE), build_sha="def456")  # a later deploy
    assert all(book.seeded_key(line) == line["key"] for line in lines)
    before = SystemClock().now()
    assert await book.seed(lines) == 2
    clock.set(AT + timedelta(minutes=30))  # the loop plays the same minutes again
    found = await book.recall(QUESTION, MODEL)
    assert found is not None
    assert found.payload == {"n": 1}
    assert found.answered_at == AT, "the time the model gave it stays"
    assert found.stored_at == datetime.fromisoformat(kept["stored_at"]), "and when it was kept"
    fresh = timedelta(hours=2160)
    assert before + fresh <= found.expires_at <= SystemClock().now() + fresh, "expiry from now"
    assert await book.recall(QUESTION, "other-model") is None
    assert await book_on(sqlite, Scope(CASE)).recall(other, MODEL) is not None, "in the store"
    assert await book.seed(lines) == 0, "seeded once"


async def test_a_seeded_answer_never_overwrites_a_newer_one(
    tmp_path: Path, sqlite: SqliteStore, clock: FixedClock
) -> None:
    earlier = SqliteStore(tmp_path / "earlier.sqlite3", tmp_path / "earlier-blobs")
    lines = await _lines_kept_by(earlier, (QUESTION, MODEL, {"n": 1}))
    await earlier.aclose()
    book = book_on(sqlite, Scope(CASE))
    await book.keep(QUESTION, MODEL, {"n": 2}, prompt_hash="p" * 64, answered_at=AT + HOUR)
    assert await book.seed(lines) == 0
    newer = await book_on(sqlite, Scope(CASE)).recall(QUESTION, MODEL)
    assert newer is not None
    assert newer.payload == {"n": 2}
    assert newer.answered_at == AT + HOUR


async def test_the_seed_says_once_why_its_lines_would_never_be_found(
    tmp_path: Path, sqlite: SqliteStore, clock: FixedClock
) -> None:
    earlier = SqliteStore(tmp_path / "earlier.sqlite3", tmp_path / "earlier-blobs")
    lines = await _lines_kept_by(earlier, (QUESTION, MODEL, {"n": 1}))
    await earlier.aclose()
    book = book_on(sqlite, Scope(CASE))
    models = {"main": "main-model", "lite": MODEL}
    planner_prompt = answers_module.prompt_version(
        (answers_module.PROMPTS_DIR / "planner.md").read_text(encoding="utf-8")
    )
    fine = {"prompt_versions": {"planner": planner_prompt, "drafter": "0" * 16}}
    assert book.seed_problems(lines, fine, models=models) == [], (
        "a drafter prompt that changed: no drafter answers in the file"
    )
    assert book.seed_problems(lines, None, models=models) == [], "no answers.json: no word"
    changed = {"prompt_versions": {"planner": "0" * 16}}
    (problem,) = book.seed_problems(lines, changed, models=models)
    assert problem.startswith("the planner prompt changed since the answers were given")
    (problem,) = book.seed_problems(lines, None, models={"main": "m", "lite": "other-lite"})
    assert problem.startswith(f"1 answers were given by {MODEL}, which no tier runs now")
    other_recipe = [{**line, "key": "f" * 32} for line in lines]
    (problem,) = book.seed_problems(other_recipe, None, models=models)
    assert problem == "1 of 1 answers were kept under another key recipe and are not used"


async def test_a_seed_line_already_in_the_store_is_read_once_and_remembered(
    tmp_path: Path, sqlite: SqliteStore, clock: FixedClock
) -> None:
    earlier = SqliteStore(tmp_path / "earlier.sqlite3", tmp_path / "earlier-blobs")
    lines = await _lines_kept_by(earlier, (QUESTION, MODEL, {"n": 1}))
    await earlier.aclose()
    await book_on(sqlite, Scope(CASE)).keep(
        QUESTION, MODEL, {"n": 2}, prompt_hash="p" * 64, answered_at=AT + HOUR
    )
    store = _Counting(sqlite)
    book = book_on(store, Scope(CASE))  # a new process: nothing in memory
    assert await book.seed(lines) == 0
    assert store.calls["get"] == 1
    found = await book.recall(QUESTION, MODEL)
    assert found is not None
    assert found.payload == {"n": 2}, "what the store holds, not the line"
    assert store.calls["get"] == 1, "remembered at the seed: the recall read nothing"


async def test_stub_answers_are_never_seeded(
    tmp_path: Path, sqlite: SqliteStore, clock: FixedClock
) -> None:
    earlier = SqliteStore(tmp_path / "earlier.sqlite3", tmp_path / "earlier-blobs")
    stub, none = QUESTION._replace(material={"flight": "f2"}), QUESTION._replace(material={"f": 3})
    lines = await _lines_kept_by(
        earlier, (QUESTION, MODEL, {"n": 1}), (stub, "stub", {"n": 2}), (none, "none", {"n": 3})
    )
    await earlier.aclose()
    lines.append(
        {**next(line for line in lines if line["model_id"] == MODEL), "llm_backend": "stub"}
    )
    book = book_on(sqlite, Scope(CASE))
    assert await book.seed(lines) == 1, "the model's answer; never the stub's, nor one from none"
    assert await book.recall(stub, "stub") is None
    assert await book.recall(none, "none") is None
    found = await book.recall(QUESTION, MODEL)
    assert found is not None
    assert found.payload == {"n": 1}


async def test_a_seed_line_from_another_case_or_recipe_is_skipped(
    tmp_path: Path, sqlite: SqliteStore, clock: FixedClock
) -> None:
    earlier = SqliteStore(tmp_path / "earlier.sqlite3", tmp_path / "earlier-blobs")
    lines = await _lines_kept_by(earlier, (QUESTION, MODEL, {"n": 1}))
    await earlier.aclose()
    (line,) = lines
    other_case = {**line, "case_id": "case-b"}
    live = {**line, "mode": "LIVE", "case_id": None}
    older_recipe = {**line, "key": "0" * 32}
    missing = {k: v for k, v in line.items() if k != "fingerprint"}
    book = book_on(sqlite, Scope(CASE))
    assert book.seeded_key(other_case) != line["key"]
    assert book.seeded_key(missing) is None
    assert await book.seed([other_case, live, older_recipe, missing]) == 0
    assert await sqlite.list_docs(Collection.AI_ANSWERS) == []
    assert await book.seed([line]) == 1
    assert isinstance(await book.recall(QUESTION, MODEL), AiAnswer)


async def test_an_answer_that_comes_back_after_a_reset_is_not_kept(
    sqlite: SqliteStore, clock: FixedClock
) -> None:
    scope = Scope(AnswerScope(RunMode.REPLAY, "case-a", epoch=3))
    book = book_on(sqlite, scope)
    asked = book.reuse(QUESTION)  # put while the replay played
    scope.now = AnswerScope(RunMode.LIVE, None, epoch=4)  # a switch to LIVE meanwhile
    await asked.keep("lite", {"n": 1}, prompt_hash="p", answered_at=AT)
    assert await book.recall(QUESTION, "lite") is None, "not filed under LIVE"
    scope.now = AnswerScope(RunMode.REPLAY, "case-a", epoch=5)  # nor under the next loop
    assert await book.recall(QUESTION, "lite") is None
    assert book.counts[("flight_planner", "dropped")] == 1
    assert await sqlite.list_docs(Collection.AI_ANSWERS) == []

    looked_up = book.reuse(QUESTION)
    await book.keep(QUESTION, "lite", {"n": 2}, prompt_hash="p", answered_at=AT)
    scope.now = AnswerScope(RunMode.LIVE, None, epoch=6)
    found = await looked_up.recall("lite")
    assert found is not None, "looked up in the scope the question was put in"
    assert await book.reuse(QUESTION).recall("lite") is None


async def test_inside_on_hand_work_a_missing_or_failing_answer_asks_no_model(
    sqlite: SqliteStore, clock: FixedClock
) -> None:
    book = book_on(sqlite)
    with on_hand_only():
        with pytest.raises(NotOnHand):
            await book.reuse(QUESTION).recall("lite")
        await book.keep(QUESTION, "lite", {"n": 1}, prompt_hash="p", answered_at=AT)
        kept = book.reuse(QUESTION)
        assert await kept.recall("lite") is not None
        with pytest.raises(NotOnHand):
            kept.rejected(["NO LONGER FITS"])
        with pytest.raises(NotOnHand):
            await kept.recall_as("lite", DraftText)  # unreadable as a draft: rejected
    assert book.counts[("flight_planner", "not_on_hand")] == 3
    assert await book.reuse(QUESTION).recall_as("lite", DraftText) is None, "outside: ask"


async def test_an_answer_lives_as_long_as_its_question_allows(
    sqlite: SqliteStore, clock: FixedClock
) -> None:
    book = book_on(sqlite)
    await book.keep(QUESTION, "lite", {"n": 1}, prompt_hash="p", answered_at=AT)
    clock.set(AT + timedelta(minutes=59))
    assert await book.recall(QUESTION, "lite") is not None
    clock.set(AT + timedelta(minutes=61))
    assert await book.recall(QUESTION, "lite") is None, "past the skill's age limit"
    assert book.counts[("flight_planner", "expired")] == 1

    forever = Question("notice_reader", {"text": "abc"})
    await book.keep(forever, "lite", {"n": 1}, prompt_hash="p", answered_at=AT)
    clock.set(AT + timedelta(days=2))
    assert await book.recall(forever, "lite") is not None, "a notice's text never ages"


async def test_a_replay_answer_serves_its_question_at_any_replay_age(
    sqlite: SqliteStore, clock: FixedClock
) -> None:
    """A replay loop plays the same minutes again; the material question is the situation,
    so the kept answer is good before and after the minute it was given in, however far."""
    book = book_on(sqlite, Scope(AnswerScope(RunMode.REPLAY, "case-a")))
    await book.keep(QUESTION, "lite", {"n": 1}, prompt_hash="p", answered_at=AT)
    clock.set(AT + timedelta(minutes=90))
    assert await book.recall(QUESTION, "lite") is not None, "later in the loop"
    clock.set(AT - timedelta(minutes=90))
    assert await book.recall(QUESTION, "lite") is not None, "the next loop, before its minute"
    assert book.counts[("flight_planner", "hit")] == 2
    assert ("flight_planner", "expired") not in book.counts


async def test_the_sweep_removes_expired_answers_a_few_pages_at_a_time(
    sqlite: SqliteStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(answers_module, "SWEEP_PAGE", 2)
    monkeypatch.setattr(answers_module, "SWEEP_PAGES", 2)
    book = book_on(sqlite, ai_answer_keep_h=1e-9)
    for n in range(5):
        question = QUESTION._replace(material={"flight": f"f{n}"})
        await book.keep(question, "lite", {"n": n}, prompt_hash="p", answered_at=AT)
    assert len(await sqlite.list_docs(Collection.AI_ANSWERS)) == 5
    assert await book.sweep() == 4, "at most two pages of two"
    assert len(await sqlite.list_docs(Collection.AI_ANSWERS)) == 1
    assert await book.sweep() == 0, "at most one sweep each ten minutes"


class _Counting:
    """A store that counts its reads, so a test can say what a step cost."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.calls: Counter[str] = Counter()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def get(self, *args: Any, **kwargs: Any) -> Any:
        self.calls["get"] += 1
        return await self._inner.get(*args, **kwargs)

    async def list_docs(self, *args: Any, **kwargs: Any) -> Any:
        self.calls["list_docs"] += 1
        return await self._inner.list_docs(*args, **kwargs)


async def test_the_sweep_reads_a_page_only_when_an_answer_can_have_expired(
    sqlite: SqliteStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The earliest expiry the last page showed, lowered by every keep since, is the floor:
    a store of long-lived replay answers costs no reads between expiries."""
    monkeypatch.setattr(answers_module, "SWEEP_EVERY", timedelta(0))
    store = _Counting(sqlite)
    book = book_on(store, ai_answer_keep_h=1)
    assert await book.sweep() == 0
    assert store.calls["list_docs"] == 1, "the first sweep of a process reads a page"
    assert await book.sweep() == 0
    assert store.calls["list_docs"] == 1, "an empty store: nothing to sweep until a keep"
    await book.keep(QUESTION, "lite", {"n": 1}, prompt_hash="p", answered_at=AT)
    assert await book.sweep() == 0
    assert store.calls["list_docs"] == 1, "kept for an hour: no page until then"
    gone = QUESTION._replace(material={"flight": "f2"}, max_age=timedelta(0))
    await book.keep(gone, "lite", {"n": 2}, prompt_hash="p", answered_at=AT)
    assert await book.sweep() == 1, "expired as it was kept: the keep lowered the floor"
    assert store.calls["list_docs"] == 2
    assert await book.sweep() == 0
    assert store.calls["list_docs"] == 2, "the hour-long answer is the floor again"


class _Snapshot:
    def __init__(self, data: dict[str, Any] | None) -> None:
        self._data = data
        self.exists = data is not None

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data or {})


class _Document:
    def __init__(self, docs: dict[str, dict[str, Any]], doc_id: str) -> None:
        self._docs, self._id = docs, doc_id

    async def set(self, data: dict[str, Any]) -> None:
        self._docs[self._id] = dict(data)

    async def get(self) -> _Snapshot:
        return _Snapshot(self._docs.get(self._id))

    async def delete(self) -> None:
        self._docs.pop(self._id, None)


@dataclass
class _Query:
    """Only what the store asks of Firestore for these answers: get, set, delete, and a
    single-field order with a limit (served from Firestore's automatic index)."""

    docs: dict[str, dict[str, Any]]
    order: tuple[str, str] | None = None
    count: int | None = None
    orders: list[str] = field(default_factory=list)

    def document(self, doc_id: str) -> _Document:
        return _Document(self.docs, doc_id)

    def where(self, **_: Any) -> "_Query":
        raise AssertionError("the answers never filter on the server")

    def order_by(self, name: str, direction: str) -> "_Query":
        self.orders.append(name)
        return _Query(self.docs, (name, direction), self.count, self.orders)

    def limit(self, count: int) -> "_Query":
        return _Query(self.docs, self.order, count, self.orders)

    async def stream(self) -> AsyncIterator[_Snapshot]:
        rows = list(self.docs.values())
        if self.order is not None:
            name, direction = self.order
            rows.sort(key=lambda row: row[name], reverse=direction == "DESC")
        for row in rows[: self.count]:
            yield _Snapshot(row)


def fake_firestore() -> tuple[FirestoreStore, _Query]:
    collection = _Query({})
    store = FirestoreStore.__new__(FirestoreStore)
    store._firestore = SimpleNamespace(
        FieldFilter=None, Query=SimpleNamespace(ASCENDING="ASC", DESCENDING="DESC")
    )
    store._db = SimpleNamespace(collection=lambda name: collection)
    return store, collection


async def test_the_firestore_store_keeps_finds_and_sweeps_answers(clock: FixedClock) -> None:
    store, collection = fake_firestore()
    book = book_on(store, ai_answer_keep_h=1e-9)
    await book.keep(QUESTION, "lite", {"n": 1}, prompt_hash="p", answered_at=AT)
    stored = next(iter(collection.docs.values()))
    assert isinstance(stored["expires_at"], str), "copied beside the JSON text: it is indexed"
    assert set(stored) == {"expires_at", DOC_FIELD}, "and nothing else is (no index per field)"
    fresh = book_on(store)  # nothing in memory: read through Firestore
    assert await fresh.peek(QUESTION, "lite") is None, "expired"
    long_lived = book_on(store)
    await long_lived.keep(QUESTION, "other", {"n": 2}, prompt_hash="p", answered_at=AT)
    found = await book_on(store).recall(QUESTION, "other")
    assert found is not None
    assert found.payload == {"n": 2}
    assert await book.sweep() == 1
    assert collection.orders == ["expires_at"], "one single-field order, no composite index"
    assert len(collection.docs) == 1


# --- what is material ---------------------------------------------------------------------


def _planner_q(ctx: Any, policy: str = "2026.10.1", cone: str = "v1") -> Question:
    return planner_question(ctx, cone_version=cone, policy_version=policy, max_age=HOUR)


def _drafter_q(ctx: Any, plan: Any, policy: str = "2026.10.1", cone: str = "v1") -> Question:
    return drafter_question(ctx, plan, cone_version=cone, policy_version=policy, max_age=HOUR)


def _moved(ctx: Any, **flight: Any) -> Any:
    return ctx.model_copy(update={"flight": ctx.flight.model_copy(update=flight)})


def test_a_flight_that_moves_on_asks_the_same_question_until_its_minutes_change() -> None:
    ctx = planner_ctx()
    same = _moved(
        ctx,
        lat=ctx.flight.lat + 0.07,  # about 5 NM
        lon=ctx.flight.lon + 0.03,
        alt_baro_ft=17_900,
        observed_at=AT + timedelta(minutes=2),
        source_id="ADSB:other",
    )
    assert _planner_q(same) == _planner_q(ctx)
    plan = change_level_case()[1]
    assert _drafter_q(same, plan) == _drafter_q(ctx, plan)
    nearer = _moved(same, minutes_to_entry=10)
    assert _planner_q(nearer) == _planner_q(ctx), "two minutes nearer, the same bucket"
    assert _drafter_q(nearer, plan) != _drafter_q(ctx, plan), "the body names the minutes"


def test_every_material_change_is_a_new_plan_question() -> None:
    ctx = planner_ctx()
    base = _planner_q(ctx)
    opened = [
        alt.model_copy(update={"check": alt.check.model_copy(update={"ok": True})})
        for alt in ctx.alternates
    ]
    usable = RerouteOption(
        id="RR-usable",
        flight_id=ctx.flight.id,
        cone_id=ctx.flight.cone_id,
        kind=RerouteKind.REJOIN_TRACK,
        status=RerouteStatus.OK,
        note="LATERAL ROUTE AROUND THE BUFFERED HAZARD",
    )
    changed = {
        "inside now": _moved(ctx, inside_now=True, minutes_to_entry=0),
        "a later bucket": _moved(ctx, minutes_to_entry=ctx.hold_within_min + 5),
        "another 2,000 ft step": _moved(ctx, alt_baro_ft=19_000),
        "a higher hazard band": ctx.model_copy(update={"hazard_top_ft": ctx.hazard_top_ft + 2000}),
        "an alternate opens": ctx.model_copy(update={"alternates": opened}),
        "a usable reroute": ctx.model_copy(update={"reroutes": [usable]}),
        "fewer actions allowed": ctx.model_copy(
            update={"allowed_actions": [ActionKind.MONITOR, ActionKind.HOLD]}
        ),
    }
    for why, other in changed.items():
        assert _planner_q(other) != base, why
    assert _planner_q(ctx, policy="2026.10.2") != base, "a new policy version"
    refused = usable.model_copy(update={"status": RerouteStatus.TOO_LONG})
    assert _planner_q(ctx.model_copy(update={"reroutes": [refused]})) == base, (
        "a reroute that is not usable is not offered: not material"
    )
    assert _planner_q(_moved(ctx, cone_id="CONE-other")) == base, "a cone reissued under a new id"
    assert _planner_q(ctx, cone="v2") == base, "the cone's version is not asked; its band is"


def test_a_cone_rebuilt_on_new_winds_with_the_same_band_is_the_same_question() -> None:
    ctx = planner_ctx()
    base = _planner_q(ctx)
    rebuilt = _moved(ctx, cone_id="CONE-rebuilt")
    assert _planner_q(rebuilt) == base, "a new cone id with the same band asks nothing again"
    assert plan_key(_planner_q(rebuilt)) == plan_key(base)
    ctx_d, plan = change_level_case()
    assert _drafter_q(_moved(ctx_d, cone_id="CONE-rebuilt"), plan) == _drafter_q(ctx_d, plan)
    lower = ctx.model_copy(update={"hazard_top_ft": ctx.hazard_top_ft - 2000})
    assert _planner_q(lower) != base, "a lower top is a new band: a new question"


def test_every_material_change_is_a_new_draft_question() -> None:
    ctx, plan = change_level_case()
    base = _drafter_q(ctx, plan)
    decision = plan.decision
    assert decision is not None
    others = {
        "another action": PlannerDecision(action=ActionKind.HOLD, hold_fl=170, reasoning="x"),
        "another band": decision.model_copy(update={"change_level_fl_max": 300}),
        "an alternate": PlannerDecision(
            action=ActionKind.DIVERT, alternate_icao="WARR", reasoning="x"
        ),
        "a reroute": PlannerDecision(action=ActionKind.REROUTE, reroute_id="RR-1", reasoning="x"),
    }
    for why, other in others.items():
        changed = plan.model_copy(update={"decision": other})
        assert _drafter_q(ctx, changed) != base, why
    assert _drafter_q(_moved(ctx, cone_id="CONE-x"), plan) == base, "a reissued cone, same band"
    assert _drafter_q(ctx, plan, cone="v2") == base, "the cone's version is not material"
    higher = ctx.model_copy(update={"hazard_top_ft": ctx.hazard_top_ft + 2000})
    assert _drafter_q(higher, plan) != base, "the hazard band changed"
    assert _drafter_q(ctx, plan, policy="2026.10.2") != base, "drafted under another policy"
    sooner = _moved(ctx, minutes_to_entry=ctx.flight.minutes_to_entry - 1)
    assert _drafter_q(sooner, plan) != base, "a minute nearer: the body's ENTRY N MIN figure"
    inside = _moved(ctx, inside_now=True, minutes_to_entry=0)
    assert _drafter_q(inside, plan).material["entry_min"] is None, "INSIDE NOW names none"


def test_the_plume_question_is_the_products_and_the_disagreements() -> None:
    situation = make_situation()
    base = plume_question(situation, max_age=3 * HOUR)
    later = situation.model_copy(update={"as_of": AT + HOUR})
    assert plume_question(later, max_age=3 * HOUR) == base, "the clock alone is not material"
    amended = [s.model_copy(update={"raw_text": f"{s.raw_text} AMD"}) for s in situation.sigmets]
    new_text = situation.model_copy(update={"sigmets": amended})
    assert plume_question(new_text, max_age=3 * HOUR) != base
    discrepancy = make_discrepancy()
    disagree = situation.model_copy(update={"discrepancies": [discrepancy]})
    assert plume_question(disagree, max_age=3 * HOUR) != base
    quieter = discrepancy.model_copy(update={"magnitude": 1.0, "summary": "less"})
    assert plume_question(
        situation.model_copy(update={"discrepancies": [quieter]}), max_age=3 * HOUR
    ) == plume_question(disagree, max_age=3 * HOUR), "magnitude and wording move with the clock"
    seen = SupportingEvidence(source_id="SAT-1", text="Dust RGB: ash visible to the west.")
    with_sat = situation.model_copy(update={"supporting": [seen]})
    assert plume_question(with_sat, max_age=3 * HOUR) != base, "new satellite evidence"
    newer = seen.model_copy(update={"source_id": "SAT-2", "text": "Dust RGB: no ash visible."})
    assert plume_question(
        situation.model_copy(update={"supporting": [newer]}), max_age=3 * HOUR
    ) != plume_question(with_sat, max_age=3 * HOUR), "a reading of newer frames"


def make_discrepancy() -> Discrepancy:
    return Discrepancy(
        id="D-12345678",
        volcano_id="263300",
        kind=DiscrepancyKind.SILENCE,
        aspect="presence",
        source_ids=["VONA:SMR:1"],
        values={"VONA:SMR:1": "ash reported"},
        magnitude=90.0,
        unit="min",
        summary="silent for 90 min",
    )


def _coordinator_q(worklist: Sequence[DutyItem], policy: str = "2026.10.1") -> Question:
    return coordinator_question(worklist, policy_version=policy, max_age=HOUR)


def test_the_coordinator_question_is_the_work_not_the_digest() -> None:
    base = _coordinator_q(WORKLIST)
    relabelled = [item.model_copy(update={"label": f"{item.label} (now)"}) for item in WORKLIST]
    assert _coordinator_q(relabelled) == base, "a label's minutes move with the clock"
    assert _coordinator_q(list(reversed(WORKLIST))) == base
    optional = [
        item.model_copy(update={"mandatory": False}) if item.id == ASSESS.id else item
        for item in WORKLIST
    ]
    assert _coordinator_q(optional) != base
    assert _coordinator_q(WORKLIST[:-1]) != base
    other = [
        item.model_copy(update={"subject": "f9"}) if item.id == PLAN_LATER.id else item
        for item in WORKLIST
    ]
    assert _coordinator_q(other) != base
    sooner = [
        item.model_copy(update={"urgency": item.urgency - 1}) if item.id == PLAN_LATER.id else item
        for item in WORKLIST
    ]
    assert _coordinator_q(sooner) != base, "a flight moved into a more urgent bucket"
    assert _coordinator_q(WORKLIST, policy="2026.10.2") != base, "another operator policy"


def test_the_other_skills_ask_by_their_inputs() -> None:
    assert notice_question("ERUPTION AT SEMERU") == notice_question("ERUPTION AT SEMERU")
    assert notice_question("ERUPTION AT SEMERU") != notice_question("ERUPTION AT IBU")
    assert templates_question(crew_notice_spec(("en",))) != templates_question(
        crew_notice_spec(("en", "id"))
    )
    volcano = make_situation().volcano
    frame = _frame(AT)
    chosen = {frame.product: (frame, b"")}
    newer = _frame(AT + timedelta(minutes=10))
    assert satellite_question(volcano, chosen) == satellite_question(
        volcano, {frame.product: (frame, b"png bytes do not matter")}
    )
    assert satellite_question(volcano, chosen) != satellite_question(
        volcano, {newer.product: (newer, b"")}
    )


def _frame(at: datetime) -> SatelliteFrame:
    stamp = f"{at:%Y%m%dT%H%MZ}"
    return SatelliteFrame(
        provenance=Provenance(
            source_id=f"FRAME:DUST:{stamp}",
            feed=FeedId.FRAMES,
            url="https://example.invalid/frame.png",
            fetched_at=at,
            sha256="0" * 64,
        ),
        volcano_id="263300",
        product=FrameProduct.DUST_RGB,
        observed_at=at,
        image_key=f"frames/{stamp}.png",
        width_px=100,
        height_px=100,
        caption="Dust RGB",
    )


# --- re-checked, timed, and never shown when it fails -------------------------------------


async def test_a_kept_plan_is_used_only_while_it_passes_the_checks_now(
    sqlite: SqliteStore, clock: FixedClock, agents: Agents
) -> None:
    ctx = planner_ctx()
    llm = Counting()
    reuse = Reuse(book_on(sqlite), _planner_q(ctx))
    trace: list[TraceEvent] = []
    settings = Settings(_env_file=None)
    first = await plan_flight(ctx, llm, settings=settings, trace=trace.append, reuse=reuse)
    assert agents.runs["planner"] == 1
    assert first.decision is not None

    clock.set(AT + timedelta(minutes=20))
    moved = _moved(ctx, lat=ctx.flight.lat + 0.05, minutes_to_entry=10)
    again = await plan_flight(moved, llm, settings=settings, trace=trace.append, reuse=reuse)
    assert agents.runs["planner"] == 1, "the same material question: no model asked"
    assert llm.reserved == 0, "and no budget spent"
    assert again.decision == first.decision
    assert trace[-1].message.startswith(f"PLAN {first.outcome} at 1830Z: ")
    assert not _REUSE_WORDS.search(trace[-1].message), "the step was done, at its time"

    divert = PlannerDecision(action=ActionKind.DIVERT, alternate_icao="WIII", reasoning="Near.")
    await reuse.keep(
        "counting-lite",
        first.model_copy(update={"decision": divert}).model_dump(mode="json"),
        prompt_hash="p",
        answered_at=AT,
    )
    fresh = await plan_flight(moved, llm, settings=settings, trace=trace.append, reuse=reuse)
    assert agents.runs["planner"] == 2, "WIII's screen failed now: the model is asked"
    assert fresh.decision is not None
    assert fresh.decision.alternate_icao != "WIII"
    assert reuse.book.counts[("flight_planner", "rejected")] == 1


async def test_paused_with_no_good_answer_is_ai_unavailable_never_the_kept_one(
    sqlite: SqliteStore, clock: FixedClock, agents: Agents
) -> None:
    ctx = planner_ctx()
    reuse = Reuse(book_on(sqlite), _planner_q(ctx))
    divert = PlannerDecision(action=ActionKind.DIVERT, alternate_icao="WIII", reasoning="Near.")
    held = await plan_flight(ctx, Counting(), settings=Settings(_env_file=None))
    await reuse.keep(
        "counting-lite",
        held.model_copy(update={"decision": divert}).model_dump(mode="json"),
        prompt_hash="p",
        answered_at=AT,
    )
    agents.refuse = True
    paused = await plan_flight(ctx, Counting(), settings=Settings(_env_file=None), reuse=reuse)
    assert paused.decision is None
    assert paused.outcome == "MODEL_FAILED", "AI UNAVAILABLE: the failed answer is not shown"

    ctx_d, plan = change_level_case()
    draft_reuse = Reuse(book_on(sqlite), _drafter_q(ctx_d, plan))
    stale = DraftText(body="CLIMB TO FL999 NOW.", cost_note="NONE.")
    await draft_reuse.keep("counting-lite", stale.model_dump(), prompt_hash="p", answered_at=AT)
    llm = Counting(refuse=True)
    failure = await _draft(llm, draft_reuse)
    assert isinstance(failure, AiFailure)
    assert BUDGET_EXHAUSTED in failure.reason
    assert llm.asks["DraftText"] == 1, "the model was asked, and refused"


async def _draft(llm: Counting, reuse: Reuse | None, **ctx_changes: Any) -> Advisory | AiFailure:
    situation = make_situation()
    ctx, plan = change_level_case()
    if ctx_changes:
        ctx = _moved(ctx, **ctx_changes)
    return await draft_advisory(
        situation=situation,
        assessment=make_assessment(situation),
        cone=make_cone(),
        ctx=ctx,
        plan=plan,
        llm=llm,
        settings=Settings(_env_file=None),
        policy=DRAFTER_POLICY,
        reuse=reuse,
    )


async def test_a_kept_draft_keeps_the_time_it_was_written(
    sqlite: SqliteStore, clock: FixedClock
) -> None:
    ctx, plan = change_level_case()
    reuse = Reuse(book_on(sqlite), _drafter_q(ctx, plan))
    llm = Counting()
    first = await _draft(llm, reuse)
    assert isinstance(first, Advisory)
    assert first.drafted_at == first.created_at == AT
    assert "DRAFTED 1830Z" in first.header

    clock.set(AT + timedelta(minutes=20))
    again = await _draft(llm, reuse, lat=ctx.flight.lat + 0.05)
    assert isinstance(again, Advisory)
    assert llm.asks["DraftText"] == 1, "the same material question: no second ask"
    assert again.body == first.body
    assert again.created_at == AT + timedelta(minutes=20), "the facts are the facts of now"
    assert again.drafted_at == AT, "the text keeps the time it was written"
    header = again.header.splitlines()
    assert "DRAFTED 1830Z" in header
    assert f"ENTRY {ctx.flight.minutes_to_entry} MIN AT 1850Z" in header

    sooner = await _draft(llm, reuse, minutes_to_entry=ctx.flight.minutes_to_entry - 2)
    assert llm.asks["DraftText"] == 2, "the kept text names the old entry time: asked again"
    assert isinstance(sooner, Advisory)
    assert sooner.drafted_at == sooner.created_at

    replay = Scope(AnswerScope(RunMode.REPLAY, "case-a"))
    loop_reuse = Reuse(book_on(sqlite, replay), _drafter_q(ctx, plan))
    clock.set(AT)
    await _draft(llm, loop_reuse)
    asked = llm.asks["DraftText"]
    clock.set(AT - timedelta(minutes=5))  # the next loop plays this minute before it again
    replayed = await _draft(llm, loop_reuse)
    assert isinstance(replayed, Advisory)
    assert llm.asks["DraftText"] == asked
    assert replayed.drafted_at == AT - timedelta(minutes=5), "never shown as newer than now"


async def test_a_kept_plume_read_is_checked_against_the_products_now(
    tmp_path: Path, clock: FixedClock
) -> None:
    runtime = make_runtime(make_settings(tmp_path), FixtureSource())
    try:
        await run_tick(runtime, reason="manual")
        situation = runtime.situations[SEMERU]
        report = TickReport(started_at=AT, finished_at=AT, mode=RunMode.LIVE, reason="t")
        runtime.llm = llm = Counting()
        first = await runtime._plume_read(situation, report)
        assert first.outcome in ("ACCEPTED", "REPAIRED")
        asked = llm.asks["PlumeEstimate"]

        clock.set(AT + HOUR)
        trace: list[TraceEvent] = []
        runtime.sink = trace.append  # type: ignore[method-assign]
        again = await runtime._plume_read(situation, report)
        assert llm.asks["PlumeEstimate"] == asked, "the same products: not asked again"
        assert trace[-1].message.startswith("Plume Reader accepted at 1830Z: ")
        assert not _REUSE_WORDS.search(trace[-1].message)
        assert again.id == first.id
        assert again.created_at == first.created_at == AT, "read when it was read"

        book = runtime.answers
        assert book is not None
        seen = await runtime._with_satellite(situation, report)  # as the read was given it
        question = plume_question(seen, max_age=3 * HOUR)
        bad = first.estimate.model_copy(update={"sources_used": ["SIGMET:NOWHERE:1"]})
        await book.keep(
            question,
            "counting-main",
            first.model_copy(update={"estimate": bad}).model_dump(mode="json"),
            prompt_hash="p",
            answered_at=AT,
        )
        runtime.llm = paused = Counting(refuse=True)
        failed = await runtime._plume_read(situation, report)
        assert paused.asks["PlumeEstimate"] == 1, "the kept read failed its checks: asked"
        assert failed.outcome == "MODEL_FAILED", "official products only, nothing kept shown"
        assert failed.estimate != bad
    finally:
        await runtime.aclose()


async def test_a_kept_plume_read_is_checked_with_the_satellite_reading_it_was_given(
    tmp_path: Path, clock: FixedClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = make_runtime(make_settings(tmp_path), FixtureSource())
    try:
        await run_tick(runtime, reason="manual")
        situation = runtime.situations[SEMERU]
        report = TickReport(started_at=AT, finished_at=AT, mode=RunMode.LIVE, reason="t")
        reading = SupportingEvidence(source_id="SAT-demo", text="Dust RGB: ash to the west.")

        async def with_satellite(s: Any, _: TickReport) -> Any:
            return s.model_copy(update={"supporting": [reading]})

        monkeypatch.setattr(runtime, "_with_satellite", with_satellite)
        runtime.llm = llm = Counting()
        first = await runtime._plume_read(situation, report)
        seen = await with_satellite(situation, report)
        cited = first.estimate.model_copy(
            update={"sources_used": [*first.estimate.sources_used, "SAT-demo"]}
        )
        book = runtime.answers
        assert book is not None
        await book.keep(
            plume_question(seen, max_age=3 * HOUR),
            "counting-main",
            first.model_copy(update={"estimate": cited}).model_dump(mode="json"),
            prompt_hash="p",
            answered_at=AT,
        )
        asked = llm.asks["PlumeEstimate"]
        again = await runtime._plume_read(situation, report)
        assert llm.asks["PlumeEstimate"] == asked, "it cites the reading it was given: it passes"
        assert "SAT-demo" in again.estimate.sources_used

        reading = reading.model_copy(update={"source_id": "SAT-newer", "text": "No ash seen."})
        await runtime._plume_read(situation, report)
        assert llm.asks["PlumeEstimate"] == asked + 1, "newer satellite evidence: asked"
    finally:
        await runtime.aclose()


async def test_on_hand_work_that_needs_a_model_stays_due_and_fails_nothing(
    tmp_path: Path, clock: FixedClock, agents: Agents
) -> None:
    runtime = make_runtime(make_settings(tmp_path), FixtureSource())
    try:
        runtime.llm = llm = Counting()
        await run_tick(runtime, reason="manual")
        report = TickReport(started_at=AT, finished_at=AT, mode=RunMode.LIVE, reason="t")
        due = dict(runtime.assess_due)
        assert SEMERU in due
        with on_hand_only(), pytest.raises(NotOnHand):
            await runtime.assess_volcano(SEMERU, AT, report)
        assert runtime.assess_due == due, "the plume read is due as before"

        flight = runtime.exposed[f"{GIA417}:{SEMERU}"]
        urgency = runtime.plan_due(flight, [], AT)
        assert urgency is not None
        with on_hand_only(), pytest.raises(NotOnHand):
            await runtime.plan_flight_now(flight.id, [], AT, report)
        assert runtime.plan_due(flight, [], AT) == urgency, "the flight is due as before"
        assert runtime.open_failures == {}, "no AI UNAVAILABLE for want of a slot"
        assert await list_advisories(runtime.store) == []
        assert sum(llm.asks.values()) == 0
        assert agents.runs["planner"] == 0
        assert llm.reserved == 0
    finally:
        await runtime.aclose()


DIGEST = "- Semeru (263300): 3 exposed flight(s), 1 inside now"


async def _coordinate(
    book: AiAnswers,
    executor: FakeExecutor,
    digest: str = DIGEST,
    worklist: list[DutyItem] = WORKLIST,
) -> DutyRun:
    return await run_duty_officer(
        worklist,
        executor,
        Counting(),
        digest=digest,
        settings=Settings(_env_file=None),
        trigger="tick",
        replay=False,
        reuse=book.reuse(_coordinator_q(worklist)),
        rerun=timedelta(minutes=5),
    )


def _decisions(**changes: Any) -> dict[str, Any]:
    return {
        "delegations": [],
        "deferrals": [],
        "summary": "Flights first.",
        "priorities": [],
        "watch": [],
        "outcome": "ACCEPTED",
        "turns": 2,
        **changes,
    }


async def test_the_coordinators_decisions_are_made_again_through_the_same_tools(
    sqlite: SqliteStore, clock: FixedClock, agents: Agents
) -> None:
    book = book_on(sqlite)
    first_exec = FakeExecutor()
    first = await _coordinate(book, first_exec, f"{DIGEST}\n- AI budget today, lite: 40 of 450")
    assert agents.runs["coordinator"] == 1
    assert first.outcome == "ACCEPTED"
    assert first.decided_at == first.finished_at == AT

    clock.set(AT + timedelta(minutes=4))
    executor = FakeExecutor()
    again = await _coordinate(book, executor, f"{DIGEST}\n- AI budget today, lite: 52 of 450")
    assert agents.runs["coordinator"] == 1, "the budget lines moved; the work did not"
    assert executor.calls == first_exec.calls, "every delegation made again, by the same tools"
    assert again.outcome == "ACCEPTED"
    assert again.turns == first.turns == 3, "the turns the model took then"
    assert again.decided_at == AT, "decided when the model decided"
    assert again.finished_at == AT + timedelta(minutes=4), "the delegations ran now"
    assert [d.item_id for d in again.deferred] == [d.item_id for d in first.deferred]
    assert again.brief == first.brief

    other_work = [item.model_copy(update={"mandatory": True}) for item in WORKLIST]
    await _coordinate(book, FakeExecutor(), worklist=other_work)
    assert agents.runs["coordinator"] == 2, "other work: another question"


class OpenDraftPlans(FakeExecutor):
    """The pipeline's plan results: a draft stored on the first ask, the same advice found
    open on the next (``Runtime._commit_draft``)."""

    async def plan(self, flight_id: str) -> dict[str, Any]:
        first = ("plan", flight_id) not in self.calls
        self.calls.append(("plan", flight_id))
        if first:
            return {
                "summary": f"{flight_id}: DRAFT MONITOR for a dispatcher",
                "advisory_id": "adv_000000000001",
                "action": "MONITOR",
            }
        return {"summary": f"{flight_id}: same advice as an open draft", "action": "MONITOR"}


async def test_a_decision_is_not_refused_because_its_draft_is_already_open(
    sqlite: SqliteStore, clock: FixedClock, agents: Agents
) -> None:
    """Next loop the plan delegation finds the draft it made still open: the same advice is
    the same outcome, and the kept decision serves (this cost eight Coordinator runs a
    loop on the Krakatau window)."""
    book = book_on(sqlite)
    executor = OpenDraftPlans()
    await _coordinate(book, executor)
    assert agents.runs["coordinator"] == 1

    clock.set(AT + timedelta(minutes=2))
    again = await _coordinate(book, executor)
    assert agents.runs["coordinator"] == 1, "the delegation came out the same"
    assert book.counts[("coordinator", "hit")] == 1
    assert again.outcome == "ACCEPTED"


async def test_the_pipeline_reports_the_action_when_the_same_advice_is_already_open(
    tmp_path: Path,
) -> None:
    """A draft stored and the same advice found open read the same to the Coordinator's
    re-check: the keys ``OUTCOME_KEYS`` names agree."""
    runtime = make_runtime(make_settings(tmp_path), FixtureSource())
    try:
        ctx, plan = change_level_case()
        draft = make_draft("adv_000000000001", replay=False, flight_id=ctx.flight.id)
        report = TickReport(started_at=AT, finished_at=AT, mode=RunMode.LIVE, reason="manual")
        stored = await runtime._commit_draft(ctx, ctx.flight, plan, draft, 1, report, [])
        same = draft.model_copy(update={"id": "adv_000000000002"})  # the dedupe key stays
        found = await runtime._commit_draft(ctx, ctx.flight, plan, same, 1, report, [])
    finally:
        await runtime.aclose()
    assert "advisory_id" in stored
    assert "advisory_id" not in found
    assert report.drafts_created == 1
    assert {k: v for k, v in stored.items() if k in OUTCOME_KEYS} == {
        k: v for k, v in found.items() if k in OUTCOME_KEYS
    }


class FailingPlans(FakeExecutor):
    async def plan(self, flight_id: str) -> dict[str, Any]:
        self.calls.append(("plan", flight_id))
        return {"flight_id": flight_id, "status": "ai_unavailable", "summary": "AI UNAVAILABLE"}


async def test_decisions_whose_delegations_come_out_otherwise_go_to_the_model(
    sqlite: SqliteStore, clock: FixedClock, agents: Agents
) -> None:
    book = book_on(sqlite)
    await _coordinate(book, FakeExecutor())
    assert agents.runs["coordinator"] == 1

    clock.set(AT + timedelta(minutes=2))
    run = await _coordinate(book, FailingPlans())
    assert agents.runs["coordinator"] == 2, "its brief was written on plans that were drafted"
    assert book.counts[("coordinator", "rejected")] == 1
    assert run.decided_at == run.finished_at, "the model decided now"
    assert run.outcome == "ACCEPTED"


async def test_a_kept_brief_or_reason_that_fails_its_checks_now_goes_to_the_model(
    sqlite: SqliteStore, clock: FixedClock, agents: Agents
) -> None:
    book = book_on(sqlite)
    question = _coordinator_q(WORKLIST)
    await book.keep(
        question,
        "counting-lite",
        _decisions(summary="Handled 99 flights."),
        prompt_hash="p",
        answered_at=AT,
    )
    run = await _coordinate(book, FakeExecutor())
    assert agents.runs["coordinator"] == 1, "a brief that fails the checks: the model finishes"
    assert run.outcome == "ACCEPTED"
    assert run.validation_errors == [], "the kept brief's problems are not this run's"
    assert run.brief is not None
    assert run.brief.summary == "Flights first, then the rest."

    reason = {"kind": "SRA", "subject": SRA.subject, "text": "Budget low, 12 calls left."}
    await book.keep(
        question,
        "counting-lite",
        _decisions(deferrals=[reason]),
        prompt_hash="p",
        answered_at=AT,
    )
    await _coordinate(book, FakeExecutor())
    assert agents.runs["coordinator"] == 2, "12 calls left is not in today's input"

    await book.keep(question, "counting-lite", {"summary": 1}, prompt_hash="p", answered_at=AT)
    await _coordinate(book, FakeExecutor())
    assert agents.runs["coordinator"] == 3, "an answer that no longer reads: asked, no error"


async def test_deferrals_are_made_again_only_until_the_policy_offers_the_work_again(
    sqlite: SqliteStore, clock: FixedClock, agents: Agents
) -> None:
    book = book_on(sqlite)
    first = await _coordinate(book, FakeExecutor())
    assert [d.item_id for d in first.deferred] == [SRA.id]
    clock.set(AT + timedelta(minutes=4))
    await _coordinate(book, FakeExecutor())
    assert agents.runs["coordinator"] == 1, "a restart within the re-offer time"
    clock.set(AT + timedelta(minutes=5))
    await _coordinate(book, FakeExecutor())
    assert agents.runs["coordinator"] == 2, "deferred work offered again gets a fresh look"


def test_a_deferral_reason_is_checked_as_the_brief_is() -> None:
    kit = DutyToolkit.of(WORKLIST, FakeExecutor(), trace=None)
    kit.evidence.append(DIGEST)
    refused = kit.defer([SRA.id], "Budget low, 12 calls left.")
    assert refused["deferred"] == []
    assert refused["refused"][0]["error"] == "NUMBER 12 IN REASON IS NOT IN THE INPUT"
    assert kit.defer([SRA.id], "Flights first; 3 are exposed.")["deferred"] == [SRA.id]


# --- the AI worker: answers on hand run even while the assistant is paused ---------------


@pytest.fixture
async def paused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Any]:
    """A gemini runtime at 0100 PDT with a lite budget so small that no routine run fits."""
    settings = make_settings(tmp_path, model_lite_daily_budget=10)
    clock = FixedClock(EARLY)
    runtime = make_runtime(settings, FixtureSource())
    runtime.llm = NamedGemini()
    runtime.ledger = QuotaLedger(settings, runtime.store, now=clock.now)
    runtime.last_tick = TickReport(
        started_at=EARLY, finished_at=EARLY, mode=RunMode.LIVE, reason="t"
    )
    runs: list[tuple[list[str], str, bool]] = []

    async def no_drafts(_: Runtime) -> dict[str, list[Any]]:
        return {}

    async def recorder(_: Runtime, items: list[DutyItem], *args: Any, **kwargs: Any) -> None:
        runs.append(([i.id for i in items], current_lane(), current_admitted()))

    monkeypatch.setattr(ai_worker_module, "drafts_by_flight", no_drafts)
    monkeypatch.setattr(ai_worker_module, "duty_worklist", lambda *_: [LATER])
    monkeypatch.setattr(ai_worker_module, "dispatch_duty", recorder)
    with use_clock(clock):
        yield runtime, runs, monkeypatch
    await runtime.aclose()


async def test_work_whose_answers_are_on_hand_runs_while_paused(paused: Any) -> None:
    runtime, runs, monkeypatch = paused

    async def on_hand(item: DutyItem) -> bool:
        return item.id == LATER.id

    async def coordinator_on_hand(items: Sequence[DutyItem]) -> bool:
        return True

    monkeypatch.setattr(runtime, "answered", on_hand)
    monkeypatch.setattr(runtime, "coordinator_answered", coordinator_on_hand)
    await runtime.worker.drain()
    assert runs == [([LATER.id], "routine", False)], "run now, at no model call"
    assert LATER.id in runtime.duty_offered


async def test_on_hand_work_that_needs_a_model_after_all_waits_for_budget(paused: Any) -> None:
    runtime, runs, monkeypatch = paused
    book = book_on(runtime.store)

    async def on_hand(*_: Any) -> bool:
        return True

    async def needs_a_model(_: Runtime, items: list[DutyItem], *args: Any, **kwargs: Any) -> None:
        runs.append(([i.id for i in items], current_lane(), current_admitted()))
        await book.reuse(QUESTION).recall("lite")  # no answer: inside on-hand work, it raises

    monkeypatch.setattr(runtime, "answered", on_hand)
    monkeypatch.setattr(runtime, "coordinator_answered", on_hand)
    monkeypatch.setattr(ai_worker_module, "dispatch_duty", needs_a_model)
    await runtime.worker.drain()
    assert runs == [([LATER.id], "routine", False)], "tried once, not again in the same minutes"
    assert LATER.id not in runtime.duty_offered, "not offered: it is still due"
    assert [work.status for work in runtime.worker.queue()] == ["WAITING"]
    assert (
        await runtime.worker.work_once(
            TickReport(started_at=EARLY, finished_at=EARLY, mode=RunMode.LIVE, reason="t")
        )
        is False
    )


async def test_work_the_coordinator_would_be_asked_about_waits_while_paused(paused: Any) -> None:
    runtime, runs, monkeypatch = paused

    async def on_hand(item: DutyItem) -> bool:
        return True

    async def coordinator_missing(items: Sequence[DutyItem]) -> bool:
        return False

    monkeypatch.setattr(runtime, "answered", on_hand)
    monkeypatch.setattr(runtime, "coordinator_answered", coordinator_missing)
    await runtime.worker.drain()
    assert runs == []
    assert [work.status for work in runtime.worker.queue()] == ["WAITING"]


# --- end to end: a restart asks nothing it was asked before -------------------------------


async def test_after_a_restart_the_same_picture_asks_no_model(
    tmp_path: Path, clock: FixedClock, agents: Agents
) -> None:
    settings = make_settings(tmp_path)

    async def picture() -> tuple[Runtime, Counting]:
        runtime = make_runtime(settings, FixtureSource())
        runtime.llm = llm = Counting()
        runtime.worker.paced = False
        await run_tick(runtime, reason="manual")
        await runtime.worker.drain()
        return runtime, llm

    first, llm = await picture()
    try:
        asked = sum(llm.asks.values()) + sum(agents.runs.values())
        assert asked > 0
        drafts = await list_advisories(first.store)
        assert [a.flight_id for a in drafts] == [f"{GIA417}:{SEMERU}"]
        for draft in drafts:  # gone with the picture: the flight is planned and drafted again
            await first.store.delete(Collection.ADVISORIES, draft.id)
    finally:
        await first.aclose()

    clock.set(AT + timedelta(minutes=2))
    runs_before = sum(agents.runs.values())
    second, llm2 = await picture()
    try:
        assert sum(llm2.asks.values()) == 0, "every structured answer was on hand"
        assert sum(agents.runs.values()) == runs_before, "and the planner's and coordinator's"
        assert llm2.reserved == 0
        [again] = await list_advisories(second.store)
        assert again.body == drafts[0].body
        assert again.created_at == AT + timedelta(minutes=2)
        assert again.drafted_at == drafts[0].drafted_at == AT, "written when it was written"
    finally:
        await second.aclose()


async def test_an_ask_answer_is_given_again_only_on_the_same_tool_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FixedClock(AT)
    with use_clock(clock):
        runtime = ask_runtime(tmp_path, Counting())
        runtime.answers = book_on(runtime.store)
        runtime.duty = _duty_run("Flights first.")
        runs: list[str] = []

        async def agent(rt: Any, llm: Any, toolkit: Any, run: Any, question: str, _: Any) -> None:
            runs.append(question)
            await toolkit.duty_brief()
            claim = AskClaim(
                text="The brief puts flights first.", evidence_ids=["T01"], kind="fact"
            )
            run.reply = AskReply(
                answer="The brief puts flights first.",
                claims=[claim],
                status="answered",
                language="en",
            )

        monkeypatch.setattr(ask_module, "_run_agent", agent)
        try:
            first = await answer_question(runtime, runtime.llm, "What does the brief say?")
            assert isinstance(first, AskAnswer)
            assert first.answered_at == first.asked_at == AT
            clock.set(AT + timedelta(minutes=3))
            again = await answer_question(runtime, runtime.llm, "what does the brief say")
            assert isinstance(again, AskAnswer)
            assert len(runs) == 1, "the same question on the same tool results"
            assert again.answer == first.answer
            assert again.asked_at == AT + timedelta(minutes=3)
            assert again.answered_at == AT, "answered when the model answered"

            runtime.duty = _duty_run("Plume reads first.")
            await answer_question(runtime, runtime.llm, "What does the brief say?")
            assert len(runs) == 2, "the brief it read changed: asked again"
        finally:
            await runtime.store.aclose()


def _duty_run(summary: str) -> DutyRun:
    return DutyRun(
        id="DUTY-000000000001",
        started_at=AT,
        finished_at=AT,
        replay=False,
        trigger="tick",
        worklist=[],
        brief=DutyBrief(summary=summary, priorities=[]),
        outcome="ACCEPTED",
        llm_backend="gemini",
        model_id="counting-lite",
        prompt_hash="p",
    )


# --- the UI never announces any of it ------------------------------------------------------

_REUSE_WORDS = re.compile(
    r"(?<![\w-])cach(?:e|ed|es|ing)\b|\breus(?:e|ed|es|ing)\b|first pass|answer recorded"
    r"|recorded answer|recorded_answer|earlier answer|previous answer|kept answer|from memory",
    re.IGNORECASE,
)
_LITERAL = re.compile(r"\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`")


def _shown_text(path: Path) -> str:
    """What a page can show: string literals in scripts, text and attributes in pages."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".js":
        return "\n".join(_LITERAL.findall(text))
    return text


def test_no_page_says_an_answer_was_reused() -> None:
    pages = [p for p in WEB.rglob("*") if p.suffix in (".js", ".html") and p.is_file()]
    assert len(pages) > 20
    found = {
        str(page.relative_to(WEB)): sorted(set(_REUSE_WORDS.findall(_shown_text(page))))
        for page in pages
    }
    assert {page: words for page, words in found.items() if words} == {}
