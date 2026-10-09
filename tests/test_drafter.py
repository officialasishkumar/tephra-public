"""Planner rules, plan and draft validators, the code-rendered header and the drafter."""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import BaseModel

from tephra.agents.dispatch_drafter import (
    HEADER_TITLE,
    NEEDS_HUMAN,
    draft_advisory,
    render_header,
    stub_draft,
)
from tephra.agents.exposure_planner import (
    build_planner_context,
    fuel_for,
    nearest_clear_band,
    plan_flight,
    rule_based_decision,
)
from tephra.agents.llm import LlmCall, LlmPart, prompt_hash
from tephra.agents.validators import allowed_actions, validate_decision, validate_draft
from tephra.config import Settings
from tephra.feeds.airports import AirportCatalogue
from tephra.geo.fuel import category_for_type, divert_line, hold_line
from tephra.models import (
    ActionKind,
    Advisory,
    AdvisoryStatus,
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
from tephra.util.hashing import proxy_flight_number, stable_id
from tephra.util.timeutil import FixedClock, use_clock

AT = datetime(2026, 10, 9, 18, 30, tzinfo=UTC)
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
        hold=hold_line(category),
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
        category_for_type("B738"), alternate_icao=icao, distance_nm=distance_nm, gs_kt=440.0
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

    async def structured[T: BaseModel](
        self,
        *,
        tier: str,
        system: str,
        parts: Sequence[LlmPart],
        schema: type[T],
        stub: Callable[[], T],
        temperature: float = 0.2,
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


RULE_CASES = [
    make_ctx(make_flight(alt_ft=17_000)),
    make_ctx(make_flight(alt_ft=35_000, inside=True), top_ft=45_000),
    make_ctx(
        make_flight(alt_ft=35_000, minutes=12),
        top_ft=45_000,
        alternates=[make_alternate("WIII", "Soekarno-Hatta International", 50.0, ok=False)],
    ),
    make_ctx(make_flight(alt_ft=35_000, minutes=40), top_ft=45_000),
    make_ctx(make_flight(alt_ft=35_000, minutes=10), mode=PlumeMode.HYPOTHESIS),
    make_ctx(make_flight(alt_ft=35_000, minutes=40), mode=PlumeMode.HYPOTHESIS),
]


@pytest.mark.parametrize("ctx", RULE_CASES)
def test_rule_decisions_and_template_drafts_pass_the_validators(ctx: PlannerContext) -> None:
    decision = rule_based_decision(ctx)
    assert validate_decision(decision, ctx) == []
    plan = make_plan(ctx, decision)
    assert validate_draft(stub_draft(ctx, plan), ctx=ctx, plan=plan) == []


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


def test_hypothesis_body_may_not_advise_divert() -> None:
    ctx = make_ctx(make_flight(alt_ft=35_000, minutes=40), mode=PlumeMode.HYPOTHESIS)
    plan = make_plan(ctx, rule_based_decision(ctx))
    good = stub_draft(ctx, plan)
    bad = good.model_copy(update={"body": good.body + " CONSIDER DIVERT WARR."})
    problems = validate_draft(bad, ctx=ctx, plan=plan)
    assert any("HYPOTHESIS MODE" in problem for problem in problems)


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


async def _draft(llm: FakeLlm) -> tuple[PlannerContext, PlannedAction, Advisory]:
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


async def test_draft_advisory_fails_closed_after_one_repair() -> None:
    bad = DraftText(body="please divert to wxyz at 1830z", cost_note="unknown")
    llm = FakeLlm(name="gemini", draft=bad)
    ctx, plan, advisory = await _draft(llm)
    assert llm.calls == 2
    assert advisory.body == stub_draft(ctx, plan).body
    assert advisory.llm_backend == "stub"
    assert any(note.startswith(NEEDS_HUMAN) for note in advisory.validation_notes)


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
                alternate_ok=True,
            ),
            Airport(
                icao="WADD",
                name="I Gusti Ngurah Rai International",
                country="Indonesia",
                lat=-8.7482,
                lon=115.1672,
                elev_ft=14,
                longest_runway_m=3000,
                alternate_ok=True,
            ),
        ]
    )
    ctx = build_planner_context(
        make_flight(),
        make_cone(),
        volcano_name="Semeru",
        airports=airports,
        tafs={},
        at=AT,
        settings=Settings(_env_file=None),
    )
    by_icao = {alternate.icao: alternate for alternate in ctx.alternates}
    assert "INSIDE HAZARD CONE" in by_icao["WARR"].check.reasons
    assert not by_icao["WARR"].check.ok
    assert "INSIDE HAZARD CONE" not in by_icao["WADD"].check.reasons
    assert ctx.allowed_actions == list(ActionKind)
