"""The planner's and the drafter's questions are material: the flight's decision inputs, not
the cone's id or times. A reissued cone with the same band asks nothing again; a band change,
a new usable reroute, a closed alternate or another urgency bucket does. Reroute ids are by
content, so the same route under a new cone keeps its id and a kept plan that names it still
passes the checks."""

import json
import re
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from test_drafter import (
    POLICY,
    FakeLlm,
    make_assessment,
    make_cone,
    make_ctx,
    make_plan,
    make_situation,
)
from test_drafter import make_flight as make_drafter_flight
from test_reroute import make_cone as make_hazard
from test_reroute import make_flight
from test_reroute import make_situation as make_winds

from tephra.agents.answers import AiAnswers, AnswerScope, Question, Reuse
from tephra.agents.dispatch_drafter import _facts, draft_advisory, drafter_question
from tephra.agents.exposure_planner import (
    _context_part,
    build_planner_context,
    plan_key,
    planner_question,
    rule_based_decision,
    urgency_band,
)
from tephra.agents.llm import LlmCall
from tephra.agents.validators import validate_draft
from tephra.config import PROJECT_ROOT, Settings
from tephra.feeds.airports import load_airports
from tephra.feeds.routes import RouteTable
from tephra.geo import reroute
from tephra.models import (
    ActionKind,
    Advisory,
    DraftText,
    HazardCone,
    PlannerContext,
    RerouteStatus,
    RunMode,
)
from tephra.store.sqlite_store import SqliteStore
from tephra.util.hashing import sha256_json
from tephra.util.timeutil import FixedClock, use_clock

AT = datetime(2026, 10, 9, 18, 30, tzinfo=UTC)
HOUR = timedelta(hours=1)
AIRPORTS = load_airports(PROJECT_ROOT / "data", min_runway_m=POLICY.alternates.min_runway_m.value)
TABLE = RouteTable({"GIA417": "WIII-WADD"})
POLICY_VERSION = "2026.10.1"


@pytest.fixture(autouse=True)
def fresh_cache() -> None:
    reroute.clear_cache()


@pytest.fixture
def clock() -> Iterator[FixedClock]:
    fixed = FixedClock(AT)
    with use_clock(fixed):
        yield fixed


@pytest.fixture
async def sqlite(tmp_path: Path) -> AsyncIterator[SqliteStore]:
    store = SqliteStore(tmp_path / "tephra.sqlite3", tmp_path / "blobs")
    yield store
    await store.aclose()


def context(cone: HazardCone | None = None, *, alt_ft: int = 35_000) -> PlannerContext:
    """GIA417 WIII-WADD, 40 minutes from the Semeru cone, both reroute kinds OK."""
    flight = make_flight(alt_ft=alt_ft).model_copy(update={"minutes_to_entry": 40})
    cone = cone or make_hazard()
    return build_planner_context(
        flight.model_copy(update={"cone_id": cone.id}),
        cone,
        volcano_name="Semeru",
        airports=AIRPORTS,
        tafs={},
        at=AT,
        policy=POLICY,
        routes=TABLE,
        situation=make_winds(250.0, 30.0),
    )


def reissued(cone: HazardCone) -> HazardCone:
    """The same hazard under a new cone id, built an hour later."""
    return cone.model_copy(
        update={
            "id": "CONE-reissued0001",
            "created_at": cone.created_at + HOUR,
            "valid_to": cone.valid_to + HOUR,
        }
    )


def planner_q(ctx: PlannerContext, **kw: Any) -> Question:
    return planner_question(ctx, policy_version=POLICY_VERSION, max_age=HOUR, **kw)


def drafter_q(ctx: PlannerContext, **kw: Any) -> Question:
    plan = make_plan(ctx, rule_based_decision(ctx))
    return drafter_question(ctx, plan, policy_version=POLICY_VERSION, max_age=HOUR, **kw)


def ok_ids(ctx: PlannerContext) -> list[str]:
    return sorted(o.id for o in ctx.reroutes if o.status is RerouteStatus.OK)


_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z")
_COMPUTE_MS = re.compile(r'"compute_ms":\s*[\d.]+')


def rendered_planner_prompt(ctx: PlannerContext) -> str:
    """The planner's state part with its cone id and every time masked."""
    text = _context_part(ctx).text.replace(ctx.flight.cone_id, "CONE")
    return _COMPUTE_MS.sub('"compute_ms":T', _TIME.sub("T", text))


def rendered_drafter_prompt(ctx: PlannerContext) -> str:
    plan = make_plan(ctx, rule_based_decision(ctx))
    return json.dumps(_facts(ctx, plan), indent=1)


# --- the questions ------------------------------------------------------------------------


def test_planner_and_drafter_prompts_render_identically_for_equal_material() -> None:
    first = context()
    cone = reissued(make_hazard())
    second = context(cone)
    assert first.flight.cone_id != second.flight.cone_id
    assert ok_ids(first), "the fixture has usable reroutes"
    assert ok_ids(first) == ok_ids(second), "the same routes, by content"
    assert planner_q(first) == planner_q(second)
    assert plan_key(planner_q(first)) == plan_key(planner_q(second))
    assert drafter_q(first) == drafter_q(second)
    assert rendered_planner_prompt(first) == rendered_planner_prompt(second)
    assert rendered_drafter_prompt(first) == rendered_drafter_prompt(second)
    assert "CONE" not in rendered_drafter_prompt(first), "the drafter's facts carry no id"


def test_a_cone_with_a_new_id_and_the_same_band_is_the_same_question() -> None:
    ctx = context()
    later = context(reissued(make_hazard()))
    base = planner_q(ctx)
    assert "cone" not in base.material
    assert planner_q(later) == base
    assert planner_q(later, cone_version="v2") == planner_q(ctx, cone_version="v1"), (
        "the cone's version is accepted and ignored until T18 removes it"
    )
    assert drafter_q(later, cone_version="v2") == drafter_q(ctx, cone_version="v1")
    assert plan_key(base) == sha256_json(base.material)[:16]
    assert re.fullmatch(r"[0-9a-f]{16}", plan_key(base))


def test_a_band_change_a_new_ok_reroute_or_a_closed_alternate_is_a_new_question() -> None:
    ctx = context()
    base = planner_q(ctx)
    draft_base = drafter_q(ctx)
    assert base.material["band"] == [0, 400]
    higher = ctx.model_copy(update={"hazard_top_ft": ctx.hazard_top_ft + 2000})
    assert planner_q(higher) != base, "a band change"
    assert drafter_q(higher) != draft_base, "a band change is a new draft question too"

    extra = ctx.reroutes[0].model_copy(update={"id": "RR-another-route"})
    more = ctx.model_copy(update={"reroutes": [*ctx.reroutes, extra]})
    assert planner_q(more) != base, "a new OK reroute"
    refused = extra.model_copy(update={"status": RerouteStatus.TOO_LONG})
    same = ctx.model_copy(update={"reroutes": [*ctx.reroutes, refused]})
    assert planner_q(same) == base, "a reroute that is not OK is not offered: not material"

    assert ctx.alternates, "the fixture lists alternates, none open under an empty TAF set"
    opened = [
        alt.model_copy(update={"check": alt.check.model_copy(update={"ok": True})})
        for alt in ctx.alternates
    ]
    with_open = ctx.model_copy(update={"alternates": opened})
    assert planner_q(with_open) != base, "an alternate opens"
    closed = with_open.model_copy(update={"alternates": ctx.alternates})
    assert planner_q(closed) == base, "and closes again: the alternate set is what counts"
    assert planner_q(closed) != planner_q(with_open), "a closed alternate"


# --- reroute ids ----------------------------------------------------------------------------


def test_the_same_route_under_a_new_cone_keeps_its_id() -> None:
    first = context()
    second = context(reissued(make_hazard()))
    by_kind = {o.kind: o for o in first.reroutes}
    for option in second.reroutes:
        same = by_kind[option.kind]
        assert option.cone_id != same.cone_id
        assert option.route_string == same.route_string
        assert option.id == same.id
    lower = context(alt_ft=31_000)
    assert ok_ids(lower), "the lower level has usable reroutes too"
    assert set(ok_ids(lower)).isdisjoint(ok_ids(first)), "another level is another id"
    assert all(o.id.startswith("RR-") for o in first.reroutes)
    plan = make_plan(first, rule_based_decision(first))
    assert plan.decision is not None
    assert plan.decision.action is ActionKind.REROUTE
    assert plan.decision.reroute_id in ok_ids(second), "a kept plan still names a listed option"


# --- the advisory's plan key and token counts ---------------------------------------------


class MeteredLlm(FakeLlm):
    """A fake 'gemini' whose every call reports its usage."""

    async def structured(self, **kwargs: Any) -> tuple[Any, LlmCall]:
        value, call = await super().structured(**kwargs)
        return value, call.model_copy(update={"input_tokens": 120, "output_tokens": 40})


async def draft(llm: FakeLlm, ctx: PlannerContext, reuse: Reuse | None, key: str | None) -> Any:
    situation = make_situation()
    plan = make_plan(ctx, rule_based_decision(ctx))
    return await draft_advisory(
        situation=situation,
        assessment=make_assessment(situation),
        cone=make_cone(),
        ctx=ctx,
        plan=plan,
        llm=llm,
        settings=Settings(_env_file=None),
        policy=POLICY,
        reuse=reuse,
        plan_key=key,
    )


async def test_a_fresh_draft_carries_its_plan_key_and_token_counts(clock: FixedClock) -> None:
    ctx = context()
    key = plan_key(planner_q(ctx))
    advisory = await draft(MeteredLlm("gemini"), ctx, None, key)
    assert isinstance(advisory, Advisory)
    assert advisory.plan_key == key
    assert (advisory.input_tokens, advisory.output_tokens) == (120, 40)
    unkeyed = await draft(FakeLlm(), ctx, None, None)
    assert isinstance(unkeyed, Advisory)
    assert unkeyed.plan_key is None


async def test_a_reused_body_has_no_token_counts(sqlite: SqliteStore, clock: FixedClock) -> None:
    ctx = context()
    plan = make_plan(ctx, rule_based_decision(ctx))
    question = drafter_question(ctx, plan, policy_version=POLICY_VERSION, max_age=HOUR)
    book = AiAnswers(
        sqlite, Settings(_env_file=None), scope=lambda: AnswerScope(RunMode.LIVE, None)
    )
    llm = MeteredLlm("gemini")
    first = await draft(llm, ctx, Reuse(book, question), plan_key(planner_q(ctx)))
    assert isinstance(first, Advisory)
    assert (first.input_tokens, first.output_tokens) == (120, 40)
    assert llm.calls == 1

    clock.set(AT + timedelta(minutes=20))
    again = await draft(llm, ctx, Reuse(book, question), plan_key(planner_q(ctx)))
    assert isinstance(again, Advisory)
    assert llm.calls == 1, "the same material question: no model asked"
    assert again.body == first.body
    assert again.drafted_at == first.drafted_at, "the body keeps the time it was written"
    assert (again.input_tokens, again.output_tokens) == (None, None)


# --- urgency ------------------------------------------------------------------------------


def urgency_context(**flight: Any) -> PlannerContext:
    """The drafter fixture: a B738 at 17,000 ft under a SFC/FL150 hazard, inside it now or
    some minutes out; the rules climb it to FL180-FL200 either way."""
    return make_ctx(make_drafter_flight(**flight))


def book(sqlite: SqliteStore) -> AiAnswers:
    return AiAnswers(
        sqlite, Settings(_env_file=None), scope=lambda: AnswerScope(RunMode.LIVE, None)
    )


def drafted(advisory: Any) -> DraftText:
    assert isinstance(advisory, Advisory)
    return DraftText(body=advisory.body, cost_note=advisory.cost_note)


async def test_a_drafted_body_is_not_reused_across_urgency_buckets(
    sqlite: SqliteStore, clock: FixedClock
) -> None:
    inside, soon = urgency_context(inside=True), urgency_context(minutes=3)
    assert (urgency_band(inside), urgency_band(soon)) == (0, 1)
    inside_q, soon_q = drafter_q(inside), drafter_q(soon)
    differing = {k for k in inside_q.material if inside_q.material[k] != soon_q.material[k]}
    assert differing == {"urgency"}, "the same flight, band and action: only the urgency"
    assert inside_q.material["action"] == ActionKind.CHANGE_LEVEL.value
    assert plan_key(inside_q) != plan_key(soon_q)
    assert planner_q(inside) != planner_q(soon), "the planner's question differs the same way"

    answers = book(sqlite)
    llm = FakeLlm("gemini")
    first = await draft(llm, inside, Reuse(answers, inside_q), None)
    assert "INSIDE HAZARD AREA NOW" in drafted(first).body
    soon_plan = make_plan(soon, rule_based_decision(soon))
    assert validate_draft(drafted(first), ctx=soon, plan=soon_plan) == [], (
        "the checks alone would let the inside body through for a flight 3 min out"
    )
    clock.set(AT + timedelta(minutes=2))
    second = await draft(llm, soon, Reuse(answers, soon_q), None)
    assert llm.calls == 2, "another urgency bucket is another question: asked again"
    assert "ENTRY 3 MIN" in drafted(second).body


def test_the_same_urgency_bucket_keeps_the_drafter_question() -> None:
    ctx, later = context(), context(reissued(make_hazard()))
    assert ctx.flight.cone_id != later.flight.cone_id
    assert urgency_band(ctx) == urgency_band(later) == 3, "40 min out: beyond the hold limit"
    assert drafter_q(ctx).material["urgency"] == 3
    assert drafter_q(later) == drafter_q(ctx)
    twelve, five = urgency_context(minutes=12), urgency_context(minutes=5)
    assert urgency_band(twelve) == urgency_band(five) == 1
    assert drafter_q(twelve) == drafter_q(five), "the minutes within a bucket are not material"


async def test_a_kept_body_with_a_stale_minute_figure_is_asked_again(
    sqlite: SqliteStore, clock: FixedClock
) -> None:
    twelve, five = urgency_context(minutes=12), urgency_context(minutes=5)
    question = drafter_q(twelve)
    assert question == drafter_q(five)
    answers = book(sqlite)
    llm = FakeLlm("gemini")
    first = await draft(llm, twelve, Reuse(answers, question), None)
    assert "ENTRY 12 MIN" in drafted(first).body
    five_plan = make_plan(five, rule_based_decision(five))
    assert validate_draft(drafted(first), ctx=five, plan=five_plan) == [
        "BODY HAS NUMBERS NOT IN THE INPUT: 12"
    ]
    clock.set(AT + timedelta(minutes=7))
    second = await draft(llm, five, Reuse(answers, question), None)
    assert llm.calls == 2, "the kept body no longer passes the checks: asked again"
    assert "ENTRY 5 MIN" in drafted(second).body
    assert isinstance(second, Advisory)
    assert second.drafted_at == AT + timedelta(minutes=7), "a fresh body, written now"
