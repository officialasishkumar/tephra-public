"""The Plume Reader's code-side guarantees: every validator rule, one repair, the official
fallback, and the stub and official-only paths. Uses the real 23 Sep Semeru SIGMET 11 and
VONA 2026SMR1806 built in test_discrepancies (research/13)."""

from collections.abc import Callable, Sequence

import pytest
from pydantic import BaseModel
from test_discrepancies import SEMERU, SETTINGS, SIGMET_11, VONA_1806, utc

from tephra.agents.llm import LlmCall, LlmPart, StubBackend, prompt_hash
from tephra.agents.plume_reader import read_plume, validate_estimate
from tephra.models import (
    DisagreementReading,
    LlmBackendName,
    PlumeEstimate,
    PlumeMode,
    RunMode,
    Situation,
)
from tephra.reconcile import build_situation
from tephra.util.timeutil import FixedClock, use_clock

AT = utc(2026, 9, 23, 23, 0)


@pytest.fixture
def situation() -> Situation:
    return build_situation(
        SEMERU,
        active_reasons=["test"],
        sigmets=[SIGMET_11],
        vonas=[VONA_1806],
        vaas=[],
        winds=[],
        frames=[],
        btd=None,
        at=AT,
        mode=RunMode.REPLAY,
        settings=SETTINGS,
    )


def good_estimate(situation: Situation, **changes: object) -> PlumeEstimate:
    sigmet_id = SIGMET_11.provenance.source_id
    estimate = PlumeEstimate(
        mode=PlumeMode.WIDENED,
        base_fl=0,
        top_fl=150,
        bearing_from_deg=20.0,
        bearing_to_deg=150.0,
        extent_km=60.0,
        horizon_h=3.0,
        confidence=0.6,
        sources_used=[sigmet_id, VONA_1806.provenance.source_id],
        disagreements_explained=[
            DisagreementReading(
                discrepancy_id=d.id,
                reading="Observatory drift is north-east; the official area runs south-east.",
                which_source_we_lean_on=sigmet_id,
                why="Official area is binding; the observatory direction widens it.",
            )
            for d in situation.discrepancies
        ],
        uncertainty_notes="Ground observer and satellite disagree on direction.",
        rationale="Union of the official polygon and the observatory's reported drift.",
    )
    return estimate.model_copy(update=changes)


def test_situation_has_an_official_floor(situation: Situation) -> None:
    assert situation.official_valid_now()
    assert situation.official_top_ft() == 15000
    assert situation.discrepancies


def test_good_estimate_passes(situation: Situation) -> None:
    assert validate_estimate(good_estimate(situation), situation) == []


@pytest.mark.parametrize(
    ("changes", "fragment"),
    [
        ({"sources_used": ["SIGMET:MADE:UP"]}, "SIGMET:MADE:UP"),
        ({"rationale": "Ash seen at 2221Z moving north-east."}, "2221Z"),
        ({"uncertainty_notes": "Observed 23/2221Z by the observatory."}, "2221Z"),
        ({"rationale": "Report from 2026-09-23 says so."}, "2026-09-23"),
        ({"rationale": "Observer saw it at 22:21."}, "22:21"),
        ({"mode": PlumeMode.HYPOTHESIS}, "HYPOTHESIS"),
        ({"top_fl": 120}, "120"),
        ({"bearing_from_deg": 0.0, "bearing_to_deg": 270.0}, "sector"),
        ({"extent_km": 900.0}, "900"),
        ({"base_fl": 150, "top_fl": 150}, "base"),
        (
            {"rationale": "Ash-cloud is not observed by the observatory, so we narrow the sector."},
            "narrows",
        ),
    ],
)
def test_each_validator_rule_rejects(
    situation: Situation, changes: dict[str, object], fragment: str
) -> None:
    problems = validate_estimate(good_estimate(situation, **changes), situation)
    assert problems, f"expected a rejection for {changes}"
    assert any(fragment.lower() in problem.lower() for problem in problems), problems


def test_unknown_discrepancy_id_is_rejected(situation: Situation) -> None:
    estimate = good_estimate(situation)
    bad = estimate.disagreements_explained[0].model_copy(update={"discrepancy_id": "DX:NOPE"})
    estimate = estimate.model_copy(update={"disagreements_explained": [bad]})
    assert validate_estimate(estimate, situation)


class ScriptedLlm:
    """Returns the scripted estimates in order, as a non-stub backend would."""

    def __init__(self, answers: Sequence[PlumeEstimate | None]) -> None:
        self.name: LlmBackendName = "gemini"
        self._answers = list(answers)
        self.calls = 0

    def model_id(self, tier: str) -> str:
        return "gemini-test"

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
        answer = self._answers[self.calls]
        self.calls += 1
        call = LlmCall(
            backend=self.name,
            model_id="gemini-test",
            prompt_hash=prompt_hash(system, parts),
            latency_ms=0,
            input_tokens=0,
            output_tokens=0,
            raw_text="{}" if answer is None else answer.model_dump_json(),
            error=None if answer is not None else "invalid_json",
        )
        return (None if answer is None else schema.model_validate(answer.model_dump())), call


async def test_accepted_on_first_call(situation: Situation) -> None:
    llm = ScriptedLlm([good_estimate(situation)])
    with use_clock(FixedClock(AT)):
        assessment = await read_plume(situation, llm, settings=SETTINGS)
    assert assessment.outcome == "ACCEPTED"
    assert assessment.attempts == 1
    assert llm.calls == 1


async def test_one_repair_then_accepted(situation: Situation) -> None:
    llm = ScriptedLlm([good_estimate(situation, top_fl=90), good_estimate(situation)])
    with use_clock(FixedClock(AT)):
        assessment = await read_plume(situation, llm, settings=SETTINGS)
    assert assessment.outcome == "REPAIRED"
    assert assessment.attempts == 2


async def test_two_rejections_fall_back_to_official_never_smaller(situation: Situation) -> None:
    shrunk = good_estimate(situation, top_fl=90)
    llm = ScriptedLlm([shrunk, shrunk, shrunk])
    with use_clock(FixedClock(AT)):
        assessment = await read_plume(situation, llm, settings=SETTINGS)
    assert llm.calls == 2, "exactly one repair call"
    assert assessment.outcome == "FALLBACK_OFFICIAL"
    assert assessment.validation_errors
    estimate = assessment.estimate
    assert estimate.mode is PlumeMode.OFFICIAL
    assert estimate.top_fl * 100 >= situation.official_top_ft()
    assert estimate.confidence == 1.0
    assert set(estimate.sources_used) <= situation.source_ids()


async def test_unparseable_output_falls_back(situation: Situation) -> None:
    llm = ScriptedLlm([None, None])
    with use_clock(FixedClock(AT)):
        assessment = await read_plume(situation, llm, settings=SETTINGS)
    assert assessment.outcome == "FALLBACK_OFFICIAL"


async def test_stub_backend_is_labelled_and_never_shrinks(situation: Situation) -> None:
    with use_clock(FixedClock(AT)):
        assessment = await read_plume(situation, StubBackend(), settings=SETTINGS)
    assert assessment.outcome == "STUB"
    assert assessment.attempts == 0
    assert assessment.estimate.rationale.startswith("NO MODEL:")
    assert assessment.estimate.top_fl * 100 >= situation.official_top_ft()


async def test_call_model_false_uses_official_only_without_a_call(situation: Situation) -> None:
    llm = ScriptedLlm([])
    with use_clock(FixedClock(AT)):
        assessment = await read_plume(situation, llm, settings=SETTINGS, call_model=False)
    assert assessment.outcome == "OFFICIAL_ONLY"
    assert assessment.model_id == "none"
    assert llm.calls == 0
