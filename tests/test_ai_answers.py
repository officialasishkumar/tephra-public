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
from test_drafter import POLICY as DRAFTER_POLICY
from test_drafter import change_level_case, make_assessment, make_cone, make_situation
from test_duty_officer import ASSESS, PLAN_LATER, WORKLIST, FakeExecutor
from test_pipeline import GIA417, SEMERU, FixtureSource, make_runtime, make_settings
from test_planner import make_ctx as planner_ctx

from tephra import ai_worker as ai_worker_module
from tephra.agents import duty_officer as duty_officer_module
from tephra.agents import exposure_planner as planner_module
from tephra.agents.answers import AiAnswers, AnswerScope, Question, Reuse
from tephra.agents.dispatch_drafter import draft_advisory, drafter_question
from tephra.agents.duty_officer import coordinator_question, run_duty_officer
from tephra.agents.exposure_planner import plan_flight, planner_question, rule_based_decision
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
    DutyItem,
    DutyItemKind,
    FeedId,
    FrameProduct,
    LlmBackendName,
    PlannerDecision,
    Provenance,
    RunMode,
    SatelliteFrame,
    TickReport,
    TraceEvent,
)
from tephra.pipeline import Runtime
from tephra.scheduler import run_tick
from tephra.store.base import Collection
from tephra.store.firestore_store import FirestoreStore
from tephra.store.sqlite_store import SqliteStore
from tephra.util.timeutil import FixedClock, use_clock

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


async def test_an_answer_is_found_only_in_its_mode_case_build_and_model(
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
    assert await new_build.recall(QUESTION, "lite") is None, "a new build asks afresh"


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


async def test_the_sweep_removes_expired_answers_once_an_hour(sqlite: SqliteStore) -> None:
    book = book_on(sqlite, ai_answer_keep_h=1e-9)
    await book.keep(QUESTION, "lite", {"n": 1}, prompt_hash="p", answered_at=AT)
    assert len(await sqlite.list_docs(Collection.AI_ANSWERS)) == 1
    assert await book.sweep() == 1
    assert await sqlite.list_docs(Collection.AI_ANSWERS) == []
    await book.keep(QUESTION, "lite", {"n": 1}, prompt_hash="p", answered_at=AT)
    assert await book.sweep() == 0, "at most one sweep an hour"


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


def _planner_q(ctx: Any, policy: str = "2026.10.1") -> Question:
    return planner_question(ctx, policy_version=policy, max_age=HOUR)


def _moved(ctx: Any, **flight: Any) -> Any:
    return ctx.model_copy(update={"flight": ctx.flight.model_copy(update=flight)})


def test_a_flight_that_moves_on_asks_the_same_question() -> None:
    ctx = planner_ctx()
    same = _moved(
        ctx,
        lat=ctx.flight.lat + 0.07,  # about 5 NM
        lon=ctx.flight.lon + 0.03,
        minutes_to_entry=10,
        alt_baro_ft=17_900,
        observed_at=AT + timedelta(minutes=2),
        source_id="ADSB:other",
    )
    assert _planner_q(same) == _planner_q(ctx)
    plan = change_level_case()[1]
    assert drafter_question(same, plan, max_age=HOUR) == drafter_question(ctx, plan, max_age=HOUR)


def test_every_material_change_is_a_new_plan_question() -> None:
    ctx = planner_ctx()
    base = _planner_q(ctx)
    closed = [
        alt.model_copy(update={"check": alt.check.model_copy(update={"ok": True})})
        for alt in ctx.alternates
    ]
    changed = {
        "a new cone": _moved(ctx, cone_id="CONE-other"),
        "inside now": _moved(ctx, inside_now=True, minutes_to_entry=0),
        "a later bucket": _moved(ctx, minutes_to_entry=ctx.hold_within_min + 5),
        "another 2,000 ft step": _moved(ctx, alt_baro_ft=19_000),
        "an alternate opens": ctx.model_copy(update={"alternates": closed}),
        "fewer actions allowed": ctx.model_copy(
            update={"allowed_actions": [ActionKind.MONITOR, ActionKind.HOLD]}
        ),
    }
    for why, other in changed.items():
        assert _planner_q(other) != base, why
    assert _planner_q(ctx, policy="2026.10.2") != base, "a new policy version"


def test_every_material_change_is_a_new_draft_question() -> None:
    ctx, plan = change_level_case()
    base = drafter_question(ctx, plan, max_age=HOUR)
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
        assert drafter_question(ctx, changed, max_age=HOUR) != base, why
    assert drafter_question(_moved(ctx, cone_id="CONE-x"), plan, max_age=HOUR) != base


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


def test_the_coordinator_question_is_the_work_not_the_digest() -> None:
    base = coordinator_question(WORKLIST, max_age=HOUR)
    relabelled = [
        item.model_copy(update={"label": f"{item.label} (now)", "urgency": 2}) for item in WORKLIST
    ]
    assert coordinator_question(relabelled, max_age=HOUR) == base
    assert coordinator_question(list(reversed(WORKLIST)), max_age=HOUR) == base
    optional = [
        item.model_copy(update={"mandatory": False}) if item.id == ASSESS.id else item
        for item in WORKLIST
    ]
    assert coordinator_question(optional, max_age=HOUR) != base
    assert coordinator_question(WORKLIST[:-1], max_age=HOUR) != base
    other = [
        item.model_copy(update={"subject": "f9"}) if item.id == PLAN_LATER.id else item
        for item in WORKLIST
    ]
    assert coordinator_question(other, max_age=HOUR) != base


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
    draft_reuse = Reuse(book_on(sqlite), drafter_question(ctx_d, plan, max_age=HOUR))
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
    reuse = Reuse(book_on(sqlite), drafter_question(ctx, plan, max_age=HOUR))
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
    loop_reuse = Reuse(book_on(sqlite, replay), drafter_question(ctx, plan, max_age=HOUR))
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
        question = plume_question(situation, max_age=3 * HOUR)
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


async def test_the_coordinators_decisions_are_made_again_through_the_same_tools(
    sqlite: SqliteStore, clock: FixedClock, agents: Agents
) -> None:
    book = book_on(sqlite)
    question = coordinator_question(WORKLIST, max_age=HOUR)

    async def run(executor: FakeExecutor, digest: str, worklist: list[DutyItem] = WORKLIST) -> Any:
        return await run_duty_officer(
            worklist,
            executor,
            Counting(),
            digest=digest,
            settings=Settings(_env_file=None),
            trigger="tick",
            replay=False,
            reuse=Reuse(book, coordinator_question(worklist, max_age=HOUR)),
        )

    digest = "- Semeru (263300): 3 exposed flight(s), 1 inside now"
    first_exec = FakeExecutor()
    first = await run(first_exec, f"{digest}\n- AI budget today, lite: 40 of 450 used")
    assert agents.runs["coordinator"] == 1
    assert first.outcome == "ACCEPTED"

    clock.set(AT + timedelta(minutes=10))
    executor = FakeExecutor()
    again = await run(executor, f"{digest}\n- AI budget today, lite: 52 of 450 used")
    assert agents.runs["coordinator"] == 1, "the budget lines moved; the work did not"
    assert executor.calls == first_exec.calls, "every delegation made again, by the same tools"
    assert again.outcome == "ACCEPTED"
    assert again.turns == 0
    assert [d.item_id for d in again.deferred] == [d.item_id for d in first.deferred]
    assert again.brief == first.brief

    await book.keep(
        question,
        "counting-lite",
        {
            "delegations": [],
            "deferrals": [],
            "summary": "Handled 99 flights.",
            "priorities": [],
            "watch": [],
            "outcome": "ACCEPTED",
        },
        prompt_hash="p",
        answered_at=AT,
    )
    finished = await run(FakeExecutor(), digest)
    assert agents.runs["coordinator"] == 2, "a brief that fails the checks: the model finishes"
    assert finished.outcome == "ACCEPTED"

    mandatory = [item.model_copy(update={"mandatory": True}) for item in WORKLIST]
    await run(FakeExecutor(), digest, mandatory)
    assert agents.runs["coordinator"] == 3, "other work: another question"


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
    assert runs == [([LATER.id], "routine", False)], (
        "run now, at no model call; a step whose answer fails its checks meets the pacing"
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
