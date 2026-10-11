"""Planner rules, plan and draft validators, the code-rendered header and the drafter."""

import json
import re
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel
from test_plume_reader import ScriptedClient

from tephra.agents.dispatch_drafter import (
    HEADER_TITLE,
    _facts,
    draft_advisory,
    render_header,
    stub_draft,
)
from tephra.agents.dispatch_drafter import PROMPT_PATH as DRAFTER_PROMPT
from tephra.agents.exposure_planner import (
    build_planner_context,
    fuel_for,
    nearest_clear_band,
    plan_flight,
    planner_limits,
    rule_based_decision,
)
from tephra.agents.llm import DailyBudget, GeminiBackend, LlmCall, LlmPart, prompt_hash
from tephra.agents.validators import (
    VOCABULARY,
    allowed_actions,
    validate_decision,
    validate_draft,
)
from tephra.config import PROJECT_ROOT, Settings
from tephra.feeds.airports import AirportCatalogue
from tephra.geo.fuel import category_for_type, divert_line, hold_line
from tephra.geo.units import destination_point
from tephra.models import (
    ActionKind,
    AdvisoryStatus,
    AiFailure,
    Airport,
    AlternateCandidate,
    AlternateCheck,
    DraftText,
    ExposedFlight,
    FeedId,
    HazardCone,
    LlmBackendName,
    PlannedAction,
    PlannerContext,
    PlannerDecision,
    PlumeAssessment,
    PlumeEstimate,
    PlumeMode,
    Provenance,
    RunMode,
    Sigmet,
    Situation,
    SourceRef,
    VaacCentre,
    Volcano,
    polygon_from_latlon,
)
from tephra.policy import load_policy
from tephra.util.hashing import proxy_flight_number, stable_id
from tephra.util.timeutil import FixedClock, use_clock

AT = datetime(2026, 10, 9, 18, 30, tzinfo=UTC)
POLICY = load_policy(PROJECT_ROOT / "data")
HOLD_MIN = POLICY.fuel.hold_min.value
DIVERT_EXTRA_MIN = POLICY.fuel.divert_extra_min.value
SHA = "ab" * 32
VOLCANO_ID = "263300"
CONE_ID = "CONE-0123456789ab"
SIGMET_ID = "SIGMET:WAAF:3:20261009T1800Z"


def provenance(source_id: str, feed: FeedId, url: str, **times: datetime) -> Provenance:
    return Provenance(source_id=source_id, feed=feed, url=url, fetched_at=AT, sha256=SHA, **times)


def make_flight(
    *, alt_ft: int = 17_000, minutes: int = 12, inside: bool = False, hex_id: str = "8a0123"
) -> ExposedFlight:
    category = category_for_type("B738")
    return ExposedFlight(
        id=f"{hex_id}:{VOLCANO_ID}",
        hex=hex_id,
        callsign="GIA417",
        proxy_flight=proxy_flight_number(hex_id),
        type_icao="B738",
        category=category,
        lat=-7.5,
        lon=112.0,
        alt_baro_ft=alt_ft,
        gs_kt=440.0,
        track_deg=110.0,
        observed_at=AT,
        source_id="ADSB:-8.200:113.600:20261009T183000Z",
        volcano_id=VOLCANO_ID,
        cone_id=CONE_ID,
        inside_now=inside,
        minutes_to_entry=0 if inside else minutes,
        entry_lat=-7.9,
        entry_lon=112.9,
        aircraft_band_ft=(alt_ft, alt_ft),
        hazard_band_ft=(0, 15_000),
        path=[(112.0, -7.5), (112.9, -7.9)],
        hold=hold_line(category, minutes=HOLD_MIN),
    )


def make_alternate(icao: str, name: str, distance_nm: float, *, ok: bool) -> AlternateCandidate:
    check = AlternateCheck(
        icao=icao,
        ok=ok,
        reasons=[] if ok else ["VA IN TEMPO GROUP"],
        taf_source_id=f"TAF:{icao}:20261009T1700Z",
        checked_for=AT,
    )
    divert = divert_line(
        category_for_type("B738"),
        alternate_icao=icao,
        distance_nm=distance_nm,
        gs_kt=440.0,
        extra_minutes=DIVERT_EXTRA_MIN,
    )
    return AlternateCandidate(
        icao=icao, name=name, distance_nm=distance_nm, bearing_deg=270.0, check=check, divert=divert
    )


DEFAULT_ALTERNATES = (
    make_alternate("WIII", "Soekarno-Hatta International", 50.0, ok=False),
    make_alternate("WARR", "Juanda International", 120.0, ok=True),
    make_alternate("WADD", "I Gusti Ngurah Rai International", 200.0, ok=True),
)


def make_ctx(
    flight: ExposedFlight | None = None,
    *,
    mode: PlumeMode = PlumeMode.OFFICIAL,
    top_ft: int = 15_000,
    alternates: Sequence[AlternateCandidate] = DEFAULT_ALTERNATES,
) -> PlannerContext:
    flight = flight or make_flight()
    return PlannerContext(
        flight=flight,
        volcano_name="Semeru",
        plume_mode=mode,
        confidence=0.8,
        hazard_base_ft=0,
        hazard_top_ft=top_ft,
        vertical_margin_ft=2_000,
        allowed_actions=allowed_actions(mode),
        alternates=list(alternates),
        hold=flight.hold,
        **planner_limits(POLICY),
    )


def make_plan(ctx: PlannerContext, decision: PlannerDecision) -> PlannedAction:
    return PlannedAction(
        id=stable_id("PLAN", ctx.flight.id, ctx.flight.cone_id),
        flight_id=ctx.flight.id,
        cone_id=ctx.flight.cone_id,
        decision=decision,
        fuel=fuel_for(decision, ctx),
        llm_backend="stub",
        model_id="stub",
        prompt_hash="0" * 64,
        outcome="STUB",
    )


def change_level_case() -> tuple[PlannerContext, PlannedAction]:
    ctx = make_ctx()
    return ctx, make_plan(ctx, rule_based_decision(ctx))


class FakeLlm:
    """A minimal LlmBackend: returns the stub, or a fixed draft for a fake 'gemini'."""

    def __init__(self, name: LlmBackendName = "stub", draft: DraftText | None = None) -> None:
        self.name: LlmBackendName = name
        self._draft = draft
        self.calls = 0

    def model_id(self, tier: str) -> str:
        return "stub" if self.name == "stub" else "gemini-test-lite"

    def reserve(self, tier: str) -> bool:
        return True

    def exhaust(self, tier: str) -> None:
        raise AssertionError("the drafter never closes a tier itself")

    async def structured[T: BaseModel](
        self,
        *,
        tier: str,
        system: str,
        parts: Sequence[LlmPart],
        schema: type[T],
        stub: Callable[[], T],
        temperature: float | None = None,
    ) -> tuple[T | None, LlmCall]:
        self.calls += 1
        result = stub() if self._draft is None else schema.model_validate(self._draft.model_dump())
        call = LlmCall(
            backend=self.name,
            model_id=self.model_id(tier),
            prompt_hash=prompt_hash(system, parts),
            latency_ms=0,
            input_tokens=0,
            output_tokens=0,
            raw_text="",
            error=None,
        )
        return result, call


# --- allowed actions and rules ----------------------------------------------------------


def test_hypothesis_allows_only_monitor_and_hold() -> None:
    assert allowed_actions(PlumeMode.HYPOTHESIS) == [ActionKind.MONITOR, ActionKind.HOLD]
    assert allowed_actions(PlumeMode.OFFICIAL) == list(ActionKind)
    assert allowed_actions(PlumeMode.WIDENED) == list(ActionKind)


def test_hypothesis_holds_at_present_level_when_entry_is_close() -> None:
    ctx = make_ctx(make_flight(alt_ft=35_000, minutes=10), mode=PlumeMode.HYPOTHESIS)
    decision = rule_based_decision(ctx)
    assert decision.action is ActionKind.HOLD
    assert decision.hold_fl == 350
    assert decision.reasoning.startswith("NO MODEL:")


def test_hypothesis_monitors_when_entry_is_far() -> None:
    ctx = make_ctx(make_flight(alt_ft=35_000, minutes=40), mode=PlumeMode.HYPOTHESIS)
    assert rule_based_decision(ctx).action is ActionKind.MONITOR


def test_change_level_to_nearest_clear_band() -> None:
    ctx = make_ctx(make_flight(alt_ft=17_000))
    assert nearest_clear_band(ctx) == (180, 200)
    decision = rule_based_decision(ctx)
    assert decision.action is ActionKind.CHANGE_LEVEL
    assert (decision.change_level_fl_min, decision.change_level_fl_max) == (180, 200)


def test_level_search_comes_from_the_policy() -> None:
    ctx = make_ctx(make_flight(alt_ft=17_000))
    assert nearest_clear_band(ctx) == (180, 200)  # 1,000 ft away
    narrow = ctx.model_copy(update={"level_search_ft": 500})
    assert nearest_clear_band(narrow) is None
    assert rule_based_decision(narrow).action is not ActionKind.CHANGE_LEVEL


def test_divert_to_nearest_acceptable_alternate_when_inside_and_no_clear_band() -> None:
    ctx = make_ctx(make_flight(alt_ft=35_000, inside=True), top_ft=45_000)
    decision = rule_based_decision(ctx)
    assert decision.action is ActionKind.DIVERT
    assert decision.alternate_icao == "WARR"  # WIII is nearer but failed its screen


def test_hold_when_entry_is_close_and_no_alternate_is_acceptable() -> None:
    alternates = [make_alternate("WIII", "Soekarno-Hatta International", 50.0, ok=False)]
    ctx = make_ctx(make_flight(alt_ft=35_000, minutes=12), top_ft=45_000, alternates=alternates)
    decision = rule_based_decision(ctx)
    assert decision.action is ActionKind.HOLD
    assert decision.hold_fl == 350


def test_monitor_when_entry_is_far_and_no_clear_band() -> None:
    ctx = make_ctx(make_flight(alt_ft=35_000, minutes=40), top_ft=45_000)
    assert rule_based_decision(ctx).action is ActionKind.MONITOR


FAILED_ONLY = (make_alternate("WIII", "Soekarno-Hatta International", 50.0, ok=False),)


def with_hazard(ctx: PlannerContext, base_ft: int, top_ft: int) -> PlannerContext:
    flight = ctx.flight.model_copy(update={"hazard_band_ft": (base_ft, top_ft)})
    return ctx.model_copy(
        update={"flight": flight, "hazard_base_ft": base_ft, "hazard_top_ft": top_ft}
    )


def with_selected(ctx: PlannerContext, selected_ft: int) -> PlannerContext:
    """The aircraft climbs or descends to ``selected_ft`` (ADS-B nav_altitude_mcp)."""
    altitude = ctx.flight.alt_baro_ft or 0
    band = (min(altitude, selected_ft), max(altitude, selected_ft))
    flight = ctx.flight.model_copy(
        update={"nav_altitude_mcp_ft": selected_ft, "aircraft_band_ft": band}
    )
    return ctx.model_copy(update={"flight": flight})


def climbing_into_layer_above() -> PlannerContext:
    """FL100 climbing to FL300 under a FL200/FL350 layer: the base is above the aircraft."""
    ctx = with_hazard(make_ctx(make_flight(alt_ft=10_000, minutes=12)), 20_000, 35_000)
    return with_selected(ctx, 30_000)


def descending_onto_layer_below() -> PlannerContext:
    """FL370 descending to FL240 over a SFC/FL330 layer."""
    return with_selected(make_ctx(make_flight(alt_ft=37_000, minutes=12), top_ft=33_000), 24_000)


def unknown_type_far_divert() -> PlannerContext:
    """Type unknown and slow (assumed 250 KT): the divert formula runs past 120 characters."""
    category = category_for_type(None)
    flight = make_flight(alt_ft=35_000, inside=True).model_copy(
        update={
            "type_icao": None,
            "category": category,
            "gs_kt": 120.0,
            "hold": hold_line(category, minutes=HOLD_MIN),
        }
    )
    far = AlternateCandidate(
        icao="WADD",
        name="Denpasar I Gusti Ngurah Rai International Airport",
        distance_nm=399.0,
        bearing_deg=95.0,
        check=make_alternate("WADD", "Denpasar", 399.0, ok=True).check,
        divert=divert_line(
            category,
            alternate_icao="WADD",
            distance_nm=399.0,
            gs_kt=120.0,
            extra_minutes=DIVERT_EXTRA_MIN,
        ),
    )
    ctx = make_ctx(flight, top_ft=45_000, alternates=[far])
    return ctx.model_copy(update={"volcano_name": "Lewotobi Laki-laki"})


RULE_CASES = [
    make_ctx(make_flight(alt_ft=17_000)),
    make_ctx(make_flight(alt_ft=17_000), mode=PlumeMode.WIDENED),
    unknown_type_far_divert(),
    make_ctx(make_flight(alt_ft=35_000, inside=True), top_ft=45_000),
    make_ctx(make_flight(alt_ft=35_000, minutes=12), top_ft=45_000, alternates=FAILED_ONLY),
    make_ctx(make_flight(alt_ft=35_000, minutes=40), top_ft=45_000),
    make_ctx(make_flight(alt_ft=35_000, minutes=10), mode=PlumeMode.HYPOTHESIS),
    make_ctx(make_flight(alt_ft=35_000, minutes=40), mode=PlumeMode.HYPOTHESIS),
    make_ctx(make_flight(alt_ft=35_000, inside=True), top_ft=45_000, alternates=FAILED_ONLY),
    make_ctx(make_flight(alt_ft=35_000, inside=True), top_ft=45_000, alternates=()),
    make_ctx(make_flight(alt_ft=41_000, minutes=5), top_ft=44_000, alternates=()),
    with_hazard(
        make_ctx(make_flight(alt_ft=30_000, inside=True), alternates=FAILED_ONLY), 20_000, 35_000
    ),
    make_ctx(make_flight(alt_ft=12_000, inside=True), mode=PlumeMode.HYPOTHESIS),
    with_selected(
        make_ctx(make_flight(alt_ft=19_000, inside=True), mode=PlumeMode.HYPOTHESIS), 12_000
    ),
    climbing_into_layer_above(),
    descending_onto_layer_below(),
]


@pytest.mark.parametrize("ctx", RULE_CASES)
def test_rule_decisions_and_template_drafts_pass_the_validators(ctx: PlannerContext) -> None:
    decision = rule_based_decision(ctx)
    assert validate_decision(decision, ctx) == []
    plan = make_plan(ctx, decision)
    assert validate_draft(stub_draft(ctx, plan), ctx=ctx, plan=plan) == []


@pytest.mark.parametrize(
    "ctx",
    [
        make_ctx(make_flight(alt_ft=35_000, inside=True), top_ft=45_000, alternates=FAILED_ONLY),
        make_ctx(make_flight(alt_ft=35_000, inside=True), top_ft=45_000, alternates=()),
        with_hazard(
            make_ctx(make_flight(alt_ft=30_000, inside=True), alternates=FAILED_ONLY),
            20_000,
            35_000,
        ),
        make_ctx(make_flight(alt_ft=12_000, inside=True), mode=PlumeMode.HYPOTHESIS),
    ],
)
def test_rules_never_hold_inside_the_hazard(ctx: PlannerContext) -> None:
    decision = rule_based_decision(ctx)
    assert decision.action is not ActionKind.HOLD
    body = stub_draft(ctx, make_plan(ctx, decision)).body
    assert "OUTSIDE HAZARD" not in body


def test_hypothesis_holds_inside_the_cone_only_at_a_clear_present_level() -> None:
    # FL190 descending to FL120 into a SFC/FL150 hypothesis: holding at FL190 stays above it.
    ctx = with_selected(
        make_ctx(make_flight(alt_ft=19_000, inside=True), mode=PlumeMode.HYPOTHESIS), 12_000
    )
    decision = rule_based_decision(ctx)
    assert (decision.action, decision.hold_fl) == (ActionKind.HOLD, 190)


@pytest.mark.parametrize(
    ("ctx", "says", "never"),
    [
        (climbing_into_layer_above(), "DO NOT CLIMB ABOVE FL120", "DESCEND TO"),
        (descending_onto_layer_below(), "DO NOT DESCEND BELOW FL370", "DESCEND TO"),
    ],
)
def test_template_tells_a_level_aircraft_to_stay_in_its_band(
    ctx: PlannerContext, says: str, never: str
) -> None:
    decision = rule_based_decision(ctx)
    assert decision.action is ActionKind.CHANGE_LEVEL
    body = stub_draft(ctx, make_plan(ctx, decision)).body
    assert says in body
    assert never not in body


# --- decision validator -----------------------------------------------------------------


def _problems(ctx: PlannerContext, **fields: object) -> list[str]:
    decision = PlannerDecision.model_validate({"reasoning": "HAZARD AHEAD.", **fields})
    return validate_decision(decision, ctx)


def test_decision_rejects_level_band_inside_hazard() -> None:
    problems = _problems(
        make_ctx(), action="CHANGE_LEVEL", change_level_fl_min=140, change_level_fl_max=160
    )
    assert any("DOES NOT CLEAR" in problem for problem in problems)


def test_decision_rejects_unlisted_or_failed_alternates() -> None:
    ctx = make_ctx()
    assert any("FAILED" in p for p in _problems(ctx, action="DIVERT", alternate_icao="WIII"))
    assert any("NOT ONE OF" in p for p in _problems(ctx, action="DIVERT", alternate_icao="WXYZ"))
    assert _problems(ctx, action="DIVERT", alternate_icao="WARR") == []


def test_decision_rejects_divert_in_hypothesis_mode() -> None:
    ctx = make_ctx(mode=PlumeMode.HYPOTHESIS)
    problems = _problems(ctx, action="DIVERT", alternate_icao="WARR")
    assert any("NOT ALLOWED IN HYPOTHESIS" in problem for problem in problems)


def test_decision_rejects_hold_without_level_and_clock_times() -> None:
    ctx = make_ctx()
    assert any("hold_fl" in p for p in _problems(ctx, action="HOLD"))
    problems = _problems(ctx, action="MONITOR", reasoning="ASH SEEN AT 1830Z.")
    assert any("CLOCK TIME" in problem for problem in problems)


@pytest.mark.parametrize(
    "reasoning",
    ["ASH SEEN AT 1830 UTC.", "ERUPTION 0930UTC.", "ASH SINCE 09/1830.", "PLUME AT 18:30."],
)
def test_decision_rejects_every_written_clock_time(reasoning: str) -> None:
    problems = _problems(make_ctx(), action="MONITOR", reasoning=reasoning)
    assert any("CLOCK TIME" in problem for problem in problems), problems


def test_decision_checks_the_mode_not_only_the_context_list() -> None:
    # A context whose allowed_actions list was built wrongly (or edited in ADK state) must
    # still never let a HYPOTHESIS cone divert.
    ctx = make_ctx(mode=PlumeMode.HYPOTHESIS).model_copy(
        update={"allowed_actions": list(ActionKind)}
    )
    problems = _problems(ctx, action="DIVERT", alternate_icao="WARR")
    assert any("NOT ALLOWED IN HYPOTHESIS" in problem for problem in problems)


def test_decision_rejects_continue_into_the_hazard_band() -> None:
    assert any("CONTINUE" in p for p in _problems(make_ctx(), action="CONTINUE"))
    # Descending from FL370 to FL240 into SFC/FL330: present level is clear, selected is not.
    descending = descending_onto_layer_below()
    assert any("CONTINUE" in p for p in _problems(descending, action="CONTINUE"))
    above = make_ctx(make_flight(alt_ft=37_000), top_ft=33_000)
    assert _problems(above, action="CONTINUE") == []


def test_decision_rejects_hold_inside_the_hazard_now() -> None:
    inside = make_ctx(make_flight(alt_ft=35_000, inside=True), top_ft=45_000)
    assert any("INSIDE" in p for p in _problems(inside, action="HOLD", hold_fl=350))
    layer = with_hazard(make_ctx(make_flight(alt_ft=30_000, inside=True)), 20_000, 35_000)
    assert any("INSIDE" in p for p in _problems(layer, action="HOLD", hold_fl=300))
    assert _problems(layer, action="HOLD", hold_fl=380) == []
    approaching = make_ctx(make_flight(alt_ft=35_000, minutes=12), top_ft=45_000)
    assert _problems(approaching, action="HOLD", hold_fl=350) == []


def test_decision_treats_a_hold_at_another_level_as_a_level_change() -> None:
    hypothesis = make_ctx(make_flight(alt_ft=35_000, minutes=10), mode=PlumeMode.HYPOTHESIS)
    assert any("LEVEL" in p for p in _problems(hypothesis, action="HOLD", hold_fl=390))
    assert _problems(hypothesis, action="HOLD", hold_fl=350) == []
    official = make_ctx(make_flight(alt_ft=35_000, minutes=10), top_ft=45_000)
    assert any("FL410" in p for p in _problems(official, action="HOLD", hold_fl=490))


def without_taf(alternate: AlternateCandidate) -> AlternateCandidate:
    check = alternate.check.model_copy(update={"taf_source_id": None})
    return alternate.model_copy(update={"check": check})


def test_decision_rejects_divert_to_an_alternate_without_a_taf() -> None:
    ctx = make_ctx(alternates=[without_taf(make_alternate("WARR", "Juanda", 120.0, ok=True))])
    problems = _problems(ctx, action="DIVERT", alternate_icao="WARR")
    assert any("NO TAF" in problem for problem in problems), problems


def test_rules_divert_only_to_an_alternate_with_a_taf() -> None:
    alternates = [
        without_taf(make_alternate("WARR", "Juanda", 120.0, ok=True)),
        make_alternate("WADD", "I Gusti Ngurah Rai International", 200.0, ok=True),
    ]
    ctx = make_ctx(make_flight(alt_ft=35_000, inside=True), top_ft=45_000, alternates=alternates)
    decision = rule_based_decision(ctx)
    assert decision.alternate_icao == "WADD"
    assert validate_decision(decision, ctx) == []


# --- draft validator --------------------------------------------------------------------


def _draft_problems(body: str | None = None, cost_note: str | None = None) -> list[str]:
    ctx, plan = change_level_case()
    good = stub_draft(ctx, plan)
    draft = DraftText(body=body or good.body, cost_note=cost_note or good.cost_note)
    return validate_draft(draft, ctx=ctx, plan=plan)


def _good_body() -> str:
    ctx, plan = change_level_case()
    return stub_draft(ctx, plan).body


def test_template_body_is_valid_and_states_the_level_band() -> None:
    assert _draft_problems() == []
    assert "CLIMB TO FL180-FL200" in _good_body()
    assert "VAR" in _good_body()


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (lambda b: b.replace("CLIMB", "climb"), "UPPER CASE"),
        (lambda b: b + " MONITOR" * 60, "LONGER THAN 400"),
        (lambda b: b + " DIVERT WAAA IF REQUIRED.", "NO INVENTED PLACES"),
        (lambda b: b + " CHECK POINT ABCDE.", "NO INVENTED PLACES"),
        (lambda b: b + " ENTRY 12345 MIN.", "NUMBERS NOT IN THE INPUT"),
        (lambda b: b + " ASH REPORTED AT 1830Z.", "CLOCK TIME"),
        (lambda b: b + " AIRSPACE CLOSED.", "CLOSED"),
        (lambda b: b.replace("(VAR)", ""), "VAR"),
        (lambda b: b.replace("CLIMB", "PROCEED"), "MUST STATE THE ACTION"),
        (lambda b: b + " TEMP 5°.", "ASCII"),
    ],
)
def test_draft_body_violations(body: Callable[[str], str], expected: str) -> None:
    problems = _draft_problems(body=body(_good_body()))
    assert any(expected in problem for problem in problems), problems


def test_cost_note_must_be_one_short_line_with_known_numbers() -> None:
    assert any("ONE LINE" in p for p in _draft_problems(cost_note="NO EXTRA FUEL.\nNONE."))
    assert any("120" in p for p in _draft_problems(cost_note="NO EXTRA FUEL " * 20))
    assert any("NUMBERS" in p for p in _draft_problems(cost_note="ABOUT 999 KG EXTRA"))


def test_cost_note_place_check_ignores_letter_case() -> None:
    problems = _draft_problems(cost_note="No extra fuel unless diverting to Wxyz.")
    assert any("WXYZ" in problem for problem in problems), problems


def test_body_may_name_the_airline_the_facts_give() -> None:
    assert _draft_problems(body=f"RING OF FIRE AIR DISPATCH. {_good_body()}") == []


REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures"
KNOWN_STATION_IDS = frozenset({"HEAT", "SAME"})
"""aviationweather.gov stationinfo (2026-10-10) knows these 4-letter words as ICAO ids:
HEAT is Assiut (Egypt) and SAME is Mendoza (Argentina)."""


def _catalogue_icaos() -> set[str]:
    airports = json.loads((REPO / "data" / "airports.json").read_text())["airports"]
    return {airport["icao"] for airport in airports}


def _recorded_location_ids() -> set[str]:
    ids = _catalogue_icaos()
    for sigmet in json.loads((FIXTURES / "isigmet" / "isigmet_all.json").read_text()):
        ids.update(str(sigmet[key]) for key in ("firId", "icaoId") if sigmet.get(key))
    for name in ("taf.json", "metar.json"):
        ids.update(str(item["icaoId"]) for item in json.loads((FIXTURES / "wx" / name).read_text()))
    return ids


def test_vocabulary_holds_no_icao_location_id() -> None:
    assert not VOCABULARY & (_recorded_location_ids() | KNOWN_STATION_IDS)


@pytest.mark.parametrize("word", ["SAME", "HEAT", "TOKYO"])
def test_body_naming_a_real_place_not_in_the_input_is_rejected(word: str) -> None:
    problems = _draft_problems(body=f"{_good_body()} ALTN {word}.")
    assert any(word in problem and "NO INVENTED PLACES" in problem for problem in problems)


def test_templates_and_prompt_example_use_no_unlisted_icao_code() -> None:
    prompt = DRAFTER_PROMPT.read_text(encoding="utf-8")
    texts = [prompt[prompt.index("Example shape") :]]
    listed: set[str] = set()
    for ctx in RULE_CASES:
        plan = make_plan(ctx, rule_based_decision(ctx))
        draft = stub_draft(ctx, plan)
        texts += [draft.body, draft.cost_note, plan.decision.reasoning]
        listed |= {alternate.icao for alternate in ctx.alternates}
    words = {word for text in texts for word in re.findall(r"\b[A-Z]{4}\b", text)}
    assert words & _catalogue_icaos() <= listed, sorted(words & _catalogue_icaos())


def test_drafter_prompt_names_only_fields_the_facts_carry() -> None:
    ctx = make_ctx(make_flight(alt_ft=35_000, inside=True), top_ft=45_000)
    plan = make_plan(ctx, rule_based_decision(ctx))
    assert plan.decision.action is ActionKind.DIVERT  # every optional fact is filled
    facts = _facts(ctx, plan)
    prompt = DRAFTER_PROMPT.read_text(encoding="utf-8")
    paths = set(re.findall(r"`([a-z_]+(?:\.[a-z_]+)*)`", prompt)) - set(DraftText.model_fields)
    assert {"cost", "cost.formula", "action.alternate.icao", "flight.present_fl"} <= paths
    for path in sorted(paths):
        node: object = facts
        for key in path.split("."):
            assert isinstance(node, dict), path
            assert key in node, path
            node = node[key]


def test_every_number_in_the_structured_facts_passes_the_number_rule() -> None:
    for ctx in RULE_CASES:
        plan = make_plan(ctx, rule_based_decision(ctx))
        facts = _facts(ctx, plan)
        facts["action"].pop("planner_reasoning")
        text = json.dumps(facts)
        draft = DraftText(body=text.upper(), cost_note="NO EXTRA FUEL.")
        problems = validate_draft(draft, ctx=ctx, plan=plan)
        assert not [p for p in problems if "NUMBERS NOT IN THE INPUT" in p], problems


@pytest.mark.parametrize(
    "extra",
    [
        "CONSIDER DIVERT WARR.",
        "CONSIDER DIVERTING TO WARR.",
        "PLAN A DIVERSION TO WARR.",
        "START DESCENT IF ASH SEEN.",
        "CLIMBING MAY HELP.",
        "LEVEL CHANGES MAY FOLLOW.",
    ],
)
def test_hypothesis_body_may_not_advise_divert_or_level_change(extra: str) -> None:
    ctx = make_ctx(make_flight(alt_ft=35_000, minutes=40), mode=PlumeMode.HYPOTHESIS)
    plan = make_plan(ctx, rule_based_decision(ctx))
    good = stub_draft(ctx, plan)
    bad = good.model_copy(update={"body": f"{good.body} {extra}"})
    problems = validate_draft(bad, ctx=ctx, plan=plan)
    assert any("HYPOTHESIS MODE" in problem for problem in problems), problems


# --- header -----------------------------------------------------------------------------


def make_cone(*, geometry_ring: Sequence[tuple[float, float]] | None = None) -> HazardCone:
    ring = geometry_ring or [(-8.5, 112.3), (-8.5, 113.5), (-7.0, 113.5), (-7.0, 112.3)]
    return HazardCone(
        id=CONE_ID,
        volcano_id=VOLCANO_ID,
        assessment_id="PA-0123456789ab",
        mode=PlumeMode.OFFICIAL,
        confidence=0.8,
        llm_backend="stub",
        created_at=AT,
        horizon_h=6.0,
        valid_to=AT + timedelta(hours=6),
        geometry=polygon_from_latlon(ring),
        base_ft=0,
        top_ft=15_000,
        official_source_ids=[SIGMET_ID],
    )


def test_header_is_code_rendered_with_binding_source_first() -> None:
    ctx, plan = change_level_case()
    vaa = SourceRef.from_provenance(
        provenance(
            "VAA:DARWIN:263300:2026/1157",
            FeedId.VAAC_DARWIN,
            "https://tgftp.nws.noaa.gov/data/raw/fv/fvau03.adrm..txt",
            issued_at=AT - timedelta(minutes=40),
        )
    )
    sigmet = SourceRef.from_provenance(
        provenance(
            SIGMET_ID,
            FeedId.SIGMET,
            "https://aviationweather.gov/api/data/isigmet",
            issued_at=AT - timedelta(minutes=30),
        )
    )
    header = render_header(ctx=ctx, plan=plan, cone=make_cone(), sources=[vaa, sigmet], at=AT)
    lines = header.splitlines()
    assert lines[0] == HEADER_TITLE
    assert lines[1] == f"{ctx.flight.proxy_flight} (ADS-B GIA417 8A0123)"
    assert "ACTION CHANGE LEVEL FL180-FL200" in lines
    assert "ENTRY 12 MIN" in lines
    assert "CONE OFFICIAL 80% NO MODEL" in lines
    assert "DRAFTED 1830Z" in lines
    src = [line for line in lines if line.startswith("SRC ")]
    assert src[0].startswith(f"SRC SIGMET {SIGMET_ID} ISSUED 091800Z FETCHED 091830Z #")
    assert src[1].startswith("SRC VAAC_DARWIN VAA:DARWIN:263300:2026/1157 ISSUED 091750Z")
    assert all(line.endswith(f"#{SHA[:12]}") for line in src)


# --- planner and drafter entry points (stub backend, no network) -------------------------


async def test_plan_flight_with_stub_backend_uses_rules() -> None:
    ctx = make_ctx()
    with use_clock(FixedClock(AT)):
        plan = await plan_flight(ctx, FakeLlm(), settings=Settings(_env_file=None))
    assert plan.outcome == "STUB"
    assert plan.llm_backend == "stub"
    assert plan.decision.action is ActionKind.CHANGE_LEVEL
    assert plan.decision.reasoning.startswith("NO MODEL:")
    assert plan.id == stable_id("PLAN", ctx.flight.id, CONE_ID)


def make_situation() -> Situation:
    volcano = Volcano(
        id=VOLCANO_ID,
        name="Semeru",
        aliases=["SEMERU"],
        magma_code="SMR",
        country="Indonesia",
        lat=-8.108,
        lon=112.922,
        summit_elev_m=3676,
        observatory="PVMBG",
        vaac=VaacCentre.DARWIN,
    )
    sigmet = Sigmet(
        provenance=provenance(
            SIGMET_ID,
            FeedId.SIGMET,
            "https://aviationweather.gov/api/data/isigmet",
            issued_at=AT - timedelta(minutes=30),
        ),
        fir_id="WAAF",
        series_id="3",
        volcano_name="SEMERU",
        observed=True,
        top_ft=15_000,
        valid_from=AT - timedelta(minutes=30),
        valid_to=AT + timedelta(hours=5),
        raw_text="WAAF SIGMET 3 VALID 091800/092330 WAAA- VA ERUPTION MT SEMERU",
    )
    return Situation(
        volcano=volcano, as_of=AT, mode=RunMode.LIVE, active_reasons=["SIGMET"], sigmets=[sigmet]
    )


def make_assessment(situation: Situation) -> PlumeAssessment:
    estimate = PlumeEstimate(
        mode=PlumeMode.OFFICIAL,
        base_fl=0,
        top_fl=150,
        bearing_from_deg=0,
        bearing_to_deg=0,
        extent_km=0,
        horizon_h=6,
        confidence=1.0,
        sources_used=[SIGMET_ID],
        disagreements_explained=[],
        uncertainty_notes="",
        rationale="NO MODEL: official products only.",
    )
    return PlumeAssessment(
        id="PA-0123456789ab",
        volcano_id=VOLCANO_ID,
        created_at=AT,
        input_hash=situation.input_hash,
        estimate=estimate,
        llm_backend="stub",
        model_id="stub",
        prompt_hash="1" * 64,
        outcome="STUB",
        attempts=0,
    )


async def _draft(llm: FakeLlm) -> tuple[PlannerContext, PlannedAction, Any]:
    situation = make_situation()
    ctx, plan = change_level_case()
    with use_clock(FixedClock(AT)):
        advisory = await draft_advisory(
            situation=situation,
            assessment=make_assessment(situation),
            cone=make_cone(),
            ctx=ctx,
            plan=plan,
            llm=llm,
            settings=Settings(_env_file=None),
            policy=POLICY,
        )
    return ctx, plan, advisory


async def test_draft_advisory_with_stub_backend() -> None:
    ctx, plan, advisory = await _draft(FakeLlm())
    assert advisory.status is AdvisoryStatus.DRAFT
    assert advisory.version == 1
    assert advisory.created_at == advisory.updated_at == AT
    assert advisory.id.startswith("adv_")
    assert len(advisory.id) == 16
    assert advisory.body == stub_draft(ctx, plan).body
    assert advisory.header.startswith(HEADER_TITLE)
    assert advisory.validation_notes == []
    assert advisory.llm_backend == "stub"
    assert set(advisory.prompt_hashes) == {"plume_reader", "planner", "drafter"}
    assert [source.source_id for source in advisory.sources] == [SIGMET_ID]
    assert advisory.dedupe_key == stable_id(
        "DD", ctx.flight.hex, VOLCANO_ID, ActionKind.CHANGE_LEVEL, 180, None, None
    )


class UnparseableFirstLlm(FakeLlm):
    """A 'gemini' whose first answer does not parse; the repair answer is a valid draft."""

    async def structured[T: BaseModel](
        self,
        *,
        tier: str,
        system: str,
        parts: Sequence[LlmPart],
        schema: type[T],
        stub: Callable[[], T],
        temperature: float | None = None,
    ) -> tuple[T | None, LlmCall]:
        if self.calls > 0:
            return await super().structured(
                tier=tier, system=system, parts=parts, schema=schema, stub=stub
            )
        self.calls += 1
        call = LlmCall(
            backend="gemini",
            model_id=self.model_id(tier),
            prompt_hash=prompt_hash(system, parts),
            raw_text='{"body": "RFA CLIMB',
            error="invalid_output: no JSON object in model output",
        )
        return None, call


async def test_unparseable_draft_gets_its_one_repair() -> None:
    ctx, plan = change_level_case()
    good = stub_draft(ctx, plan)
    repaired = good.model_copy(update={"body": good.body.replace("CLIMB TO", "REQUEST CLIMB TO")})
    llm = UnparseableFirstLlm(name="gemini", draft=repaired)
    _, _, advisory = await _draft(llm)
    assert llm.calls == 2
    assert advisory.llm_backend == "gemini"
    assert advisory.body == repaired.body


async def test_a_draft_failing_after_one_repair_gives_no_advisory() -> None:
    """No template stands in: the flight goes to the Desk as an AI failure."""
    bad = DraftText(body="please divert to wxyz at 1830z", cost_note="unknown")
    llm = FakeLlm(name="gemini", draft=bad)
    ctx, plan, failure = await _draft(llm)
    assert llm.calls == 2
    assert isinstance(failure, AiFailure)
    assert failure.stage == "drafter"
    assert failure.plan_id == plan.id
    assert failure.flight_id == ctx.flight.id
    assert failure.reason.startswith("DRAFT FAILED CHECKS AFTER REPAIR")


class NoAnswerLlm(FakeLlm):
    """A 'gemini' whose call fails outright (budget, API error): nothing to repair."""

    async def structured[T: BaseModel](
        self,
        *,
        tier: str,
        system: str,
        parts: Sequence[LlmPart],
        schema: type[T],
        stub: Callable[[], T],
        temperature: float | None = None,
    ) -> tuple[T | None, LlmCall]:
        self.calls += 1
        call = LlmCall(
            backend="gemini",
            model_id=self.model_id(tier),
            prompt_hash=prompt_hash(system, parts),
            error="budget_exhausted",
        )
        return None, call


async def test_no_answer_at_all_gives_no_advisory_and_no_repair() -> None:
    llm = NoAnswerLlm(name="gemini")
    _, _, failure = await _draft(llm)
    assert llm.calls == 1
    assert isinstance(failure, AiFailure)
    assert failure.reason.startswith("NO DRAFT RETURNED")


async def test_the_drafter_runs_gemini_3_at_temperature_one(tmp_path: Path) -> None:
    """research/10 C9: Google strongly recommends temperature 1.0 for Gemini 3 models."""
    ctx, plan = change_level_case()
    client = ScriptedClient([stub_draft(ctx, plan).model_dump_json()])
    settings = Settings(_env_file=None, llm="gemini", GEMINI_API_KEY="test-key")
    llm = GeminiBackend(settings, client=client, cache_dir=tmp_path, budget=DailyBudget())
    situation = make_situation()
    with use_clock(FixedClock(AT)):
        advisory = await draft_advisory(
            situation=situation,
            assessment=make_assessment(situation),
            cone=make_cone(),
            ctx=ctx,
            plan=plan,
            llm=llm,
            settings=settings,
            policy=POLICY,
        )
    assert advisory.llm_backend == "gemini"
    assert advisory.model_id == settings.model_lite
    assert [config.temperature for config in client.models.configs] == [1.0]


# --- context ----------------------------------------------------------------------------


def test_alternate_inside_or_near_the_cone_is_not_acceptable() -> None:
    airports = AirportCatalogue(
        [
            Airport(
                icao="WARR",
                name="Juanda International",
                country="Indonesia",
                lat=-7.3798,
                lon=112.7869,
                elev_ft=9,
                longest_runway_m=3000,
            ),
            Airport(
                icao="WADD",
                name="I Gusti Ngurah Rai International",
                country="Indonesia",
                lat=-8.7482,
                lon=115.1672,
                elev_ft=14,
                longest_runway_m=3000,
            ),
        ],
        min_runway_m=POLICY.alternates.min_runway_m.value,
    )
    ctx = build_planner_context(
        make_flight(),
        make_cone(),
        volcano_name="Semeru",
        airports=airports,
        tafs={},
        at=AT,
        policy=POLICY,
    )
    by_icao = {alternate.icao: alternate for alternate in ctx.alternates}
    assert "INSIDE HAZARD CONE" in by_icao["WARR"].check.reasons
    assert not by_icao["WARR"].check.ok
    assert "INSIDE HAZARD CONE" not in by_icao["WADD"].check.reasons
    assert ctx.allowed_actions == list(ActionKind)


@pytest.mark.parametrize("bearing", [60, 90, 150, 180])
def test_alternate_near_a_narrow_plume_is_not_acceptable(bearing: float) -> None:
    # A Sakurajima-sized plume, 3 km wide and 30 km long: its nearest edge is 11 to 13 NM
    # from Kagoshima, inside the 20 NM buffer, yet clear of the airport itself.
    vent = (31.593, 130.657)
    left = destination_point(*vent, bearing - 90, 1.5)
    right = destination_point(*vent, bearing + 90, 1.5)
    ring = [
        left,
        destination_point(*left, bearing, 30.0),
        destination_point(*right, bearing, 30.0),
        right,
    ]
    kagoshima = Airport(
        icao="RJFK",
        name="Kagoshima Airport",
        country="Japan",
        lat=31.8034,
        lon=130.7194,
        elev_ft=906,
        longest_runway_m=3000,
    )
    flight = make_flight().model_copy(update={"lat": 32.5, "lon": 130.0})
    ctx = build_planner_context(
        flight,
        make_cone(geometry_ring=ring),
        volcano_name="Sakurajima",
        airports=AirportCatalogue([kagoshima], min_runway_m=POLICY.alternates.min_runway_m.value),
        tafs={},
        at=AT,
        policy=POLICY,
    )
    assert "INSIDE HAZARD CONE" in ctx.alternates[0].check.reasons
