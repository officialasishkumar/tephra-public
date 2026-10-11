"""REROUTE in the planner and the drafter: context, rules, validators, the ADK tools run
against a scripted model, and the advisory text. The model never writes a coordinate."""

from typing import Any

import pytest
from test_drafter import (
    AT,
    POLICY,
    FakeLlm,
    make_assessment,
    make_cone,
    make_reroute_case,
    make_situation,
)
from test_planner import SCRIPTED_MODEL, GeminiStandIn, Turn, call, script, text  # noqa: F401
from test_reroute import WIII, make_flight
from test_reroute import make_cone as make_hazard
from test_reroute import make_situation as make_winds

from tephra.agents.dispatch_drafter import (
    HEADER_TITLE,
    _facts,
    draft_advisory,
    stub_draft,
)
from tephra.agents.exposure_planner import (
    build_planner_context,
    cost_summary,
    fuel_for,
    normalise_decision,
    plan_flight,
    reroutes_summary,
    rule_based_decision,
    submit_decision,
)
from tephra.agents.validators import validate_decision, validate_draft
from tephra.config import PROJECT_ROOT, Settings
from tephra.feeds.airports import load_airports
from tephra.feeds.routes import RouteTable
from tephra.geo import reroute
from tephra.models import (
    ActionKind,
    AdvisoryStatus,
    AiFailure,
    DraftText,
    PlannerContext,
    PlannerDecision,
    PlumeMode,
    RerouteKind,
    RerouteStatus,
)
from tephra.util.hashing import stable_id
from tephra.util.timeutil import FixedClock, use_clock

AIRPORTS = load_airports(PROJECT_ROOT / "data", min_runway_m=POLICY.alternates.min_runway_m.value)
TABLE = RouteTable({"GIA417": "WIII-WADD"})


@pytest.fixture(autouse=True)
def fresh_cache() -> None:
    reroute.clear_cache()


def planner_ctx(
    *,
    minutes: int = 40,
    routes: RouteTable | None = TABLE,
    mode: PlumeMode = PlumeMode.OFFICIAL,
) -> PlannerContext:
    flight = make_flight().model_copy(update={"minutes_to_entry": minutes})
    cone = make_hazard().model_copy(update={"mode": mode})
    return build_planner_context(
        flight,
        cone,
        volcano_name="Semeru",
        airports=AIRPORTS,
        tafs={},
        at=AT,
        policy=POLICY,
        routes=routes,
        situation=make_winds(250.0, 30.0),
    )


def usable_id(ctx: PlannerContext) -> str:
    return next(o.id for o in ctx.reroutes if o.status is RerouteStatus.OK)


# --- context ----------------------------------------------------------------------------


def test_context_carries_the_route_and_both_reroute_options() -> None:
    ctx = planner_ctx()
    assert ctx.route is not None
    assert (ctx.route.origin_icao, ctx.route.dest_icao) == ("WIII", "WADD")
    assert {o.kind for o in ctx.reroutes} == set(RerouteKind)
    assert all(o.status is RerouteStatus.OK for o in ctx.reroutes)
    assert ActionKind.REROUTE in ctx.allowed_actions


def test_without_routes_the_direct_option_has_no_destination() -> None:
    ctx = planner_ctx(routes=None)
    assert ctx.route is None
    by_kind = {o.kind: o for o in ctx.reroutes}
    assert by_kind[RerouteKind.DIRECT_DEST].status is RerouteStatus.NO_DEST
    assert by_kind[RerouteKind.REJOIN_TRACK].status is RerouteStatus.OK


def test_hypothesis_mode_gets_no_reroutes_and_may_not_reroute() -> None:
    ctx = planner_ctx(mode=PlumeMode.HYPOTHESIS)
    assert ctx.reroutes == []
    assert ActionKind.REROUTE not in ctx.allowed_actions
    decision = PlannerDecision(action=ActionKind.REROUTE, reroute_id="RR-x", reasoning="WHY")
    assert any("NOT ALLOWED IN HYPOTHESIS" in p for p in validate_decision(decision, ctx))


def test_reroute_is_not_offered_without_a_usable_option() -> None:
    flight = make_flight(lat=WIII[0] + 3.0, track=0.0)  # flying away from the cone
    ctx = build_planner_context(
        flight,
        make_hazard(),
        volcano_name="Semeru",
        airports=AIRPORTS,
        tafs={},
        at=AT,
        policy=POLICY,
        routes=TABLE,
    )
    assert ActionKind.REROUTE not in ctx.allowed_actions


# --- rules and validators ---------------------------------------------------------------


def test_stub_rule_reroutes_when_no_level_is_clear_and_entry_is_not_urgent() -> None:
    ctx = planner_ctx(minutes=40)
    decision = rule_based_decision(ctx)
    assert decision.action is ActionKind.REROUTE
    assert decision.reroute_id == usable_id(ctx)
    assert decision.reasoning.startswith("NO MODEL:")
    assert validate_decision(decision, ctx) == []
    option = next(o for o in ctx.reroutes if o.id == decision.reroute_id)
    assert fuel_for(decision, ctx) == option.fuel


def test_stub_rule_does_not_reroute_when_entry_is_within_the_decisive_time() -> None:
    ctx = planner_ctx(minutes=POLICY.planner.divert_within_min.value)
    assert rule_based_decision(ctx).action is not ActionKind.REROUTE


def test_stub_rule_picks_the_cheapest_usable_route() -> None:
    ctx = planner_ctx()
    fast = ctx.reroutes[0].model_copy(update={"extra_min": 1.0, "id": "RR-fast"})
    slow = ctx.reroutes[1].model_copy(update={"extra_min": 9.0, "id": "RR-slow"})
    assert rule_based_decision(ctx.model_copy(update={"reroutes": [slow, fast]})).reroute_id == (
        "RR-fast"
    )


def test_validator_accepts_only_a_listed_usable_route_without_other_targets() -> None:
    ctx = planner_ctx(routes=None)
    ok_id = usable_id(ctx)
    unavailable = next(o.id for o in ctx.reroutes if o.status is RerouteStatus.NO_DEST)

    def problems(**fields: Any) -> list[str]:
        base: dict[str, Any] = {"action": ActionKind.REROUTE, "reasoning": "LATERAL ROUTE."}
        return validate_decision(PlannerDecision(**{**base, **fields}), ctx)

    assert problems(reroute_id=ok_id) == []
    assert any("NEEDS reroute_id" in p for p in problems())
    assert any("NOT ONE OF THE LISTED" in p for p in problems(reroute_id="RR-invented"))
    assert any("NOT AVAILABLE (NO_DEST)" in p for p in problems(reroute_id=unavailable))
    assert any("TAKES NO LEVEL" in p for p in problems(reroute_id=ok_id, hold_fl=350))
    assert any("TAKES NO LEVEL" in p for p in problems(reroute_id=ok_id, alternate_icao="WARR"))
    other = PlannerDecision(action=ActionKind.MONITOR, reroute_id=ok_id, reasoning="WATCH.")
    assert any("BELONGS ONLY TO A REROUTE" in p for p in validate_decision(other, ctx))


def test_normalise_drops_a_reroute_id_from_any_other_action() -> None:
    decision = PlannerDecision(
        action=ActionKind.HOLD, reroute_id="RR-x", hold_fl=350, reasoning="W"
    )
    assert normalise_decision(decision).reroute_id is None
    keep = PlannerDecision(action=ActionKind.REROUTE, reroute_id="RR-x", reasoning="W")
    assert normalise_decision(keep).reroute_id == "RR-x"


def test_summaries_list_usable_routes_in_full_and_the_rest_with_a_reason() -> None:
    ctx = planner_ctx(routes=None)
    summary = reroutes_summary(ctx)
    assert [r["kind"] for r in summary["reroutes"]] == ["REJOIN_TRACK"]
    first = summary["reroutes"][0]
    assert first["reroute_id"] == usable_id(ctx)
    assert first["route"].startswith("DCT ")
    assert summary["not_available"][0]["status"] == "NO_DEST"
    assert summary["published_route"] is None
    cost = cost_summary(ctx, "REROUTE", None, usable_id(ctx))
    assert cost["formula"].startswith("REROUTE +")
    assert "error" in cost_summary(ctx, "REROUTE", None, "RR-x")


def test_submit_decision_rechecks_the_route_id() -> None:
    ctx = planner_ctx()
    kwargs: dict[str, Any] = {
        "action": "reroute",
        "reasoning": "LATERAL ROUTE.",
        "change_level_fl_min": 180,
        "change_level_fl_max": 200,
        "hold_fl": 350,
        "alternate_icao": "WARR",
        "alternatives_considered": ["HOLD"],
    }
    decision, problems = submit_decision(ctx, reroute_id=usable_id(ctx), **kwargs)
    assert problems == []  # the fields of other actions are dropped
    assert decision is not None
    assert decision.reroute_id == usable_id(ctx)
    assert decision.hold_fl is None
    _, problems = submit_decision(ctx, reroute_id="RR-nope", **kwargs)
    assert any("NOT ONE OF THE LISTED" in p for p in problems)


# --- ADK path ---------------------------------------------------------------------------


async def run_plan(ctx: PlannerContext) -> Any:
    settings = Settings(_env_file=None, model_lite=SCRIPTED_MODEL)
    with use_clock(FixedClock(AT)):
        return await plan_flight(ctx, GeminiStandIn(), settings=settings)  # type: ignore[arg-type]


async def test_the_model_reads_the_routes_and_submits_one(script: list[Turn]) -> None:  # noqa: F811
    ctx = planner_ctx()
    rid = usable_id(ctx)
    script += [
        call("get_flight"),
        call("list_reroutes"),
        call("estimate_cost", action="REROUTE", reroute_id=rid),
        call(
            "submit_plan",
            action="REROUTE",
            reroute_id=rid,
            reasoning="HAZARD SFC/FL400, NO CLEAR LEVEL. THE LATERAL ROUTE ADDS FEW MINUTES.",
            alternatives_considered=["HOLD"],
        ),
        text("REROUTE submitted."),
    ]
    planned = await run_plan(ctx)
    assert planned.outcome == "ACCEPTED"
    assert planned.decision.action is ActionKind.REROUTE
    assert planned.decision.reroute_id == rid
    assert planned.fuel == next(o.fuel for o in ctx.reroutes if o.id == rid)
    assert [r.name for r in planned.tool_calls] == [
        "get_flight",
        "list_reroutes",
        "estimate_cost",
        "submit_plan",
    ]
    listed = planned.tool_calls[1].result_summary
    assert rid in listed or "reroute_id" in listed


async def test_an_invented_route_id_gets_one_repair_then_no_plan(script: list[Turn]) -> None:  # noqa: F811
    ctx = planner_ctx()
    bad = call("submit_plan", action="REROUTE", reroute_id="RR-invented", reasoning="LATERAL.")
    script += [bad, text("done"), bad, text("done")]
    planned = await run_plan(ctx)
    assert planned.outcome == "MODEL_FAILED"
    assert planned.decision is None
    assert any("NOT ONE OF THE LISTED" in e for e in planned.validation_errors)


async def test_a_repair_with_a_real_id_is_accepted(script: list[Turn]) -> None:  # noqa: F811
    ctx = planner_ctx()
    script += [
        call("submit_plan", action="REROUTE", reroute_id="RR-invented", reasoning="LATERAL."),
        text("done"),
        call("submit_plan", action="REROUTE", reroute_id=usable_id(ctx), reasoning="LATERAL."),
        text("done"),
    ]
    planned = await run_plan(ctx)
    assert planned.outcome == "REPAIRED"
    assert planned.decision is not None
    assert planned.decision.reroute_id == usable_id(ctx)


# --- drafter ----------------------------------------------------------------------------


def test_the_template_draft_carries_the_route_string_verbatim_and_passes_the_checks() -> None:
    ctx, plan = make_reroute_case()
    draft = stub_draft(ctx, plan)
    option = ctx.reroutes[0]
    assert option.route_string in draft.body
    assert draft.body.startswith("RFA")
    assert "REROUTE" in draft.body
    assert validate_draft(draft, ctx=ctx, plan=plan) == []
    assert draft.cost_note == option.fuel.formula  # type: ignore[union-attr]


def draft_with(body: str) -> list[str]:
    ctx, plan = make_reroute_case()
    return validate_draft(DraftText(body=body, cost_note="NO NOTE."), ctx=ctx, plan=plan)


def test_the_body_must_hold_the_route_string_and_no_other_coordinate_or_place() -> None:
    ctx, plan = make_reroute_case()
    good = stub_draft(ctx, plan).body
    route = ctx.reroutes[0].route_string
    assert any("VERBATIM" in p for p in draft_with(good.replace(route, "DCT 0654S11231E DCT WADD")))
    assert any("COORDINATES NOT IN" in p for p in draft_with(good + " VIA 0701S11300E."))
    assert any("NO INVENTED PLACES" in p for p in draft_with(good + " DIVERTING TO TOKYO."))
    assert any("NUMBERS NOT IN THE INPUT" in p for p in draft_with(good + " EXTRA 99 NM."))
    assert any("MUST STATE THE ACTION" in p for p in draft_with(good.replace("REROUTE", "TURN")))


def test_the_facts_for_a_reroute_carry_only_code_written_values() -> None:
    ctx, plan = make_reroute_case()
    facts = _facts(ctx, plan)
    assert facts["action"]["reroute"] == {
        "route_string": ctx.reroutes[0].route_string,
        "side": "LEFT",
        "buffer_nm": 20,
        "end": "WADD",
        "wind": ctx.reroutes[0].wind_note,
    }
    assert facts["action"]["say_one_of"] == ["REROUTE"]
    assert facts["cost"]["formula"].startswith("REROUTE +")


async def test_the_advisory_carries_the_reroute_and_a_header_that_names_the_action() -> None:
    ctx, plan = make_reroute_case()
    situation = make_situation()
    with use_clock(FixedClock(AT)):
        advisory = await draft_advisory(
            situation=situation,
            assessment=make_assessment(situation),
            cone=make_cone(),
            ctx=ctx,
            plan=plan,
            llm=FakeLlm(),  # type: ignore[arg-type]
            settings=Settings(_env_file=None),
            policy=POLICY,
        )
    assert not isinstance(advisory, AiFailure)
    assert advisory.status is AdvisoryStatus.DRAFT
    assert advisory.action is ActionKind.REROUTE
    assert advisory.reroute == ctx.reroutes[0]
    assert advisory.fuel_line == ctx.reroutes[0].fuel.formula  # type: ignore[union-attr]
    assert advisory.header.startswith(HEADER_TITLE)
    assert "ACTION REROUTE AROUND HAZARD" in advisory.header
    assert ctx.reroutes[0].route_string in advisory.body
    expected = stable_id(
        "DD", advisory.hex, advisory.volcano_id, "REROUTE", None, None, None, ctx.reroutes[0].id
    )
    assert advisory.dedupe_key == expected


async def test_a_draft_that_changes_the_route_is_ai_unavailable_not_patched() -> None:
    ctx, plan = make_reroute_case()
    bad = DraftText(
        body="RFA REROUTE VIA DCT 0654S11231E DCT WADD, ATC PERMITTING. REPORT VAR.",
        cost_note="NO NOTE.",
    )
    situation = make_situation()
    with use_clock(FixedClock(AT)):
        result = await draft_advisory(
            situation=situation,
            assessment=make_assessment(situation),
            cone=make_cone(),
            ctx=ctx,
            plan=plan,
            llm=FakeLlm("gemini", bad),  # type: ignore[arg-type]
            settings=Settings(_env_file=None),
            policy=POLICY,
        )
    assert isinstance(result, AiFailure)
    assert "VERBATIM" in result.reason
