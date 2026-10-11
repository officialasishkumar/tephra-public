"""The Plume Reader's code-side guarantees: every validator rule, one repair, the official
fallback, and the stub and official-only paths. Uses the real 23 Sep Semeru SIGMET 11 and
VONA 2026SMR1806 built in test_discrepancies (research/13)."""

import json
import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import BaseModel
from test_discrepancies import (
    SEMERU,
    SETTINGS,
    SIGMET_11,
    VONA_1806,
    make_vona,
    provenance,
    utc,
)

from tephra.agents.llm import (
    BudgetExhausted,
    DailyBudget,
    GeminiBackend,
    LlmCall,
    LlmPart,
    StubBackend,
    prompt_hash,
)
from tephra.agents.plume_reader import (
    MIN_HORIZON_H,
    PROMPT_PATH,
    build_parts,
    read_plume,
    stub_estimate,
    validate_estimate,
)
from tephra.agents.schemas import gemini_schema
from tephra.agents.validators import clock_problems
from tephra.config import MAX_HORIZON_H, MAX_PLUME_EXTENT_KM, MAX_SECTOR_WIDTH_DEG, Settings
from tephra.geo.cone import build_cone
from tephra.models import (
    BBox,
    BtdIndicator,
    BtdResult,
    DisagreementReading,
    FeedId,
    LlmBackendName,
    PlumeEstimate,
    PlumeMode,
    RunMode,
    Situation,
    TraceEvent,
)
from tephra.reconcile import build_situation
from tephra.util.timeutil import FixedClock, compact, use_clock

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
        (
            {"rationale": "The split-window result is inconclusive, so we narrow the sector."},
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


def make_btd(indicator: BtdIndicator) -> BtdResult:
    scan = utc(2026, 9, 23, 22, 50)
    return BtdResult(
        provenance=provenance(f"BTD:{SEMERU.id}:{compact(scan)}", FeedId.HSD, scan),
        volcano_id=SEMERU.id,
        scan_start=scan,
        band_pair="B13-B15",
        bbox=BBox(west=112.4, south=-8.6, east=113.4, north=-7.6),
        threshold_k=0.0,
        pixel_count=10_000,
        negative_pixel_count=4,
        negative_fraction=0.0004,
        min_btd_k=-0.3,
        p05_btd_k=0.8,
        median_btd_k=2.1,
        min_bt_k=212.4,
        indicator=indicator,
        caveats=["Tropical water vapour can mask ash."],
        segment_sha256=["ab" * 32],
    )


@pytest.mark.parametrize("indicator", list(BtdIndicator))
def test_a_blind_split_window_cannot_settle_a_disagreement(
    situation: Situation, indicator: BtdIndicator
) -> None:
    """SILENT and INCONCLUSIVE both say the split window could not tell, not that there is no
    ash (the science captions), so neither may be the source leaned on; a BTD that shows
    negative pixels may."""
    btd = make_btd(indicator)
    with_btd = situation.model_copy(update={"btd": btd})
    estimate = good_estimate(with_btd)
    leaning = [
        reading.model_copy(update={"which_source_we_lean_on": btd.provenance.source_id})
        for reading in estimate.disagreements_explained
    ]
    estimate = estimate.model_copy(update={"disagreements_explained": leaning})
    problems = validate_estimate(estimate, with_btd)
    texts = [part.text or "" for part in build_parts(with_btd, [])]
    btd_block = next(text for text in texts if text.startswith("SPLIT-WINDOW"))
    if indicator is BtdIndicator.NEGATIVE_BTD_PRESENT:
        assert problems == []
        assert "never means no ash" not in btd_block
    else:
        assert any("non-observation" in problem for problem in problems), problems
        assert f"{indicator.value} never means no ash." in btd_block


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

    def exhaust(self, tier: str) -> None:
        raise AssertionError("the Plume Reader never closes a tier itself")

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


async def test_two_rejections_leave_official_products_only(situation: Situation) -> None:
    shrunk = good_estimate(situation, top_fl=90)
    llm = ScriptedLlm([shrunk, shrunk, shrunk])
    with use_clock(FixedClock(AT)):
        assessment = await read_plume(situation, llm, settings=SETTINGS)
    assert llm.calls == 2, "exactly one repair call"
    assert assessment.outcome == "MODEL_FAILED"
    assert assessment.validation_errors
    estimate = assessment.estimate
    assert estimate.uncertainty_notes.startswith("AI UNAVAILABLE:")
    assert estimate.mode is PlumeMode.OFFICIAL
    assert estimate.top_fl * 100 >= situation.official_top_ft()
    assert estimate.confidence == 1.0
    assert set(estimate.sources_used) <= situation.source_ids()


async def test_unparseable_output_is_a_model_failure(situation: Situation) -> None:
    llm = ScriptedLlm([None, None])
    with use_clock(FixedClock(AT)):
        assessment = await read_plume(situation, llm, settings=SETTINGS)
    assert assessment.outcome == "MODEL_FAILED"


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


@pytest.fixture
def no_official_floor() -> Situation:
    """Only the 23 Sep VONA: no SIGMET or VAA polygon, so HYPOTHESIS territory."""
    return build_situation(
        SEMERU,
        active_reasons=["test"],
        sigmets=[],
        vonas=[VONA_1806],
        vaas=[],
        winds=[],
        frames=[],
        btd=None,
        at=AT,
        mode=RunMode.REPLAY,
        settings=SETTINGS,
    )


def test_widened_needs_an_official_polygon(no_official_floor: Situation) -> None:
    """A WIDENED cone with no official polygon is the model's sector alone, yet WIDENED allows
    CHANGE_LEVEL and DIVERT; with no official polygon only HYPOTHESIS (MONITOR or HOLD) may
    stand."""
    vona_id = VONA_1806.provenance.source_id
    widened = good_estimate(no_official_floor, sources_used=[vona_id], disagreements_explained=[])
    problems = validate_estimate(widened, no_official_floor)
    assert any("HYPOTHESIS" in problem for problem in problems), problems
    hypothesis = widened.model_copy(update={"mode": PlumeMode.HYPOTHESIS})
    assert validate_estimate(hypothesis, no_official_floor) == []


def vona_hypothesis(situation: Situation, **changes: object) -> PlumeEstimate:
    vona_id = VONA_1806.provenance.source_id
    defaults: dict[str, object] = {
        "mode": PlumeMode.HYPOTHESIS,
        "sources_used": [vona_id],
        "disagreements_explained": [],
    }
    return good_estimate(situation, **(defaults | changes))


@pytest.mark.parametrize(
    ("changes", "fragment"),
    [
        ({"extent_km": 0.0}, "draws no sector"),
        ({"bearing_from_deg": 90.0, "bearing_to_deg": 90.0}, "draws no sector"),
        ({"top_fl": 130}, "13,701 ft"),
    ],
)
def test_a_hypothesis_must_cover_a_recent_ash_report(
    no_official_floor: Situation, changes: dict[str, object], fragment: str
) -> None:
    """With no official polygon the model's sector is all the cone draws: while a recent VONA
    reports ash it must draw something and reach the reported top (13,701 ft here)."""
    assert validate_estimate(vona_hypothesis(no_official_floor), no_official_floor) == []
    problems = validate_estimate(vona_hypothesis(no_official_floor, **changes), no_official_floor)
    assert any(fragment in problem for problem in problems), problems


def test_a_column_above_fl600_asks_for_the_highest_top_an_estimate_can_give() -> None:
    """A Plinian column can top 20 km; a PlumeEstimate stops at FL600. Asking for more would
    reject every answer and the stub alike, and leave the cone empty for the largest ash
    cloud of all."""
    column = make_vona(
        issued_at=utc(2026, 9, 23, 22, 31),
        notice="2026SMR1807",
        ash=True,
        top_m=20_000,
        toward_deg=45,
        direction_text="Ash cloud moving to northeast",
    )
    plinian = build_situation(
        SEMERU,
        active_reasons=["test"],
        sigmets=[],
        vonas=[column],
        vaas=[],
        winds=[],
        frames=[],
        btd=None,
        at=AT,
        mode=RunMode.REPLAY,
        settings=SETTINGS,
    )
    highest = vona_hypothesis(plinian, top_fl=600, sources_used=[column.provenance.source_id])
    assert validate_estimate(highest, plinian) == []
    assert "top_fl >= 600" in (build_parts(plinian, [])[-1].text or "")
    stub = stub_estimate(plinian, SETTINGS)
    assert stub.mode is PlumeMode.HYPOTHESIS
    assert validate_estimate(stub, plinian) == []


def test_only_a_recent_ash_report_sets_the_hypothesis_floor() -> None:
    later = build_situation(
        SEMERU,
        active_reasons=["test"],
        sigmets=[],
        vonas=[VONA_1806],
        vaas=[],
        winds=[],
        frames=[],
        btd=None,
        at=AT + timedelta(hours=7),
        mode=RunMode.REPLAY,
        settings=SETTINGS,
    )
    empty = vona_hypothesis(later, extent_km=0.0, top_fl=20)
    assert validate_estimate(empty, later) == []


def test_the_task_states_the_hypothesis_floor(no_official_floor: Situation) -> None:
    task = build_parts(no_official_floor, [])[-1].text or ""
    assert "top_fl >= 138" in task
    assert "extent_km > 0" in task
    assert "When a recent VONA reports ash" in PROMPT_PATH.read_text(encoding="utf-8")


async def test_a_rejected_answer_with_no_official_polygon_draws_nothing(
    no_official_floor: Situation,
) -> None:
    """No code hypothesis stands in for the model: with no official polygon the cone is
    empty and the trace says the AI was unavailable."""
    widened = vona_hypothesis(no_official_floor).model_copy(update={"mode": PlumeMode.WIDENED})
    llm = ScriptedLlm([widened, widened])
    events: list[TraceEvent] = []
    with use_clock(FixedClock(AT)):
        assessment = await read_plume(
            no_official_floor, llm, settings=SETTINGS, trace=events.append
        )
    assert llm.calls == 2
    assert assessment.outcome == "MODEL_FAILED"
    assert assessment.validation_errors
    assert assessment.llm_backend == "gemini"
    estimate = assessment.estimate
    assert estimate.mode is PlumeMode.OFFICIAL
    assert estimate.extent_km == 0
    assert estimate.uncertainty_notes.startswith("AI UNAVAILABLE:")
    assert "AI UNAVAILABLE" in events[-1].message
    assert "nothing is drawn" in events[-1].message
    assert events[-1].level == "error"
    assert build_cone(no_official_floor, assessment).geometry is None


async def test_no_answer_with_no_official_polygon_makes_no_request_and_draws_nothing(
    no_official_floor: Situation, tmp_path: Path
) -> None:
    client = ScriptedClient([])
    settings = Settings(
        _env_file=None, llm="gemini", GEMINI_API_KEY="test-key", model_daily_budget=0
    )
    llm = GeminiBackend(settings, client=client, cache_dir=tmp_path, budget=DailyBudget())
    with use_clock(FixedClock(AT)):
        assessment = await read_plume(no_official_floor, llm, settings=SETTINGS)
    assert client.models.calls == 0
    assert assessment.outcome == "MODEL_FAILED"
    assert assessment.attempts == 0
    assert build_cone(no_official_floor, assessment).geometry is None


ZONE_TIMES = [
    "The observatory saw ash at 2221 UTC.",
    "Eruption at 0521 local, before sunrise.",
    "Reported 2221 GMT by the observer.",
    "Ash seen at 1830 UTC moving north-east.",
    "Eruption reported 0930UTC by the observatory.",
    "Observers saw the column at 0521 WIB.",
    "The plume was seen at 1830 JST.",
    "Ash reported at 1830 HRS by the observer.",
    "Ash reported at 1830 hrs.",
    "Plume seen at 1830 LCL.",
    "Satellite saw it at 1830 Z.",
    "Eruption at 1030 PHT.",
]
"""How VONAs, observers and pilots write a clock time with a zone word."""


@pytest.mark.parametrize("text", ZONE_TIMES)
def test_clock_times_with_a_zone_word_are_rejected(situation: Situation, text: str) -> None:
    problems = validate_estimate(good_estimate(situation, rationale=text), situation)
    assert any("time or date" in problem for problem in problems), problems


@pytest.mark.parametrize("text", ZONE_TIMES)
def test_the_planner_and_drafter_checks_reject_the_same_times(text: str) -> None:
    """MODULES.md 5.6: decisions and drafts are held to the plume validator's time rules."""
    assert clock_problems(text, "REASONING")
    assert clock_problems(text.upper(), "BODY")


def test_numbers_that_are_not_times_pass(situation: Situation) -> None:
    text = "Ash near 4176 m, below FL150, 15 km north; advisory 2026/1157 from 263300."
    assert validate_estimate(good_estimate(situation, rationale=text), situation) == []


def test_a_horizon_under_an_hour_is_rejected(situation: Situation) -> None:
    """The pipeline keeps an assessment only until created_at + horizon_h, so a horizon of
    minutes would ask the model again on every tick and spend the day's budget."""
    problems = validate_estimate(good_estimate(situation, horizon_h=0.05), situation)
    assert any("horizon_h" in problem for problem in problems), problems


def test_the_prompt_names_every_schema_field() -> None:
    """prompts/plume_reader.md must describe the response schema field for field."""
    schema = gemini_schema(PlumeEstimate)
    reading = schema["properties"]["disagreements_explained"]["items"]
    fields = {*schema["properties"], *reading["properties"]}
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    missing = sorted(name for name in fields if f"`{name}`" not in prompt)
    assert missing == []
    assert set(schema["properties"]["mode"]["enum"]) == {mode.value for mode in PlumeMode}
    assert all(f"`{mode.value}`" in prompt for mode in PlumeMode)


def test_the_prompt_states_the_validator_limits() -> None:
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    assert f"at most {MAX_SECTOR_WIDTH_DEG:.0f} degrees" in prompt
    assert f"`extent_km` at most {MAX_PLUME_EXTENT_KM:.0f}" in prompt
    assert f"`horizon_h` from {MIN_HORIZON_H:.0f} to {MAX_HORIZON_H:.0f}" in prompt
    assert "first" not in _task_block_line(), "the schema, not the prompt, orders the keys"


def _task_block_line() -> str:
    situation = build_situation(
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
    return build_parts(situation, [])[-1].text or ""


# --- the Gemini client, offline (a scripted stand-in for genai.Client) ------------------

GEMINI_SETTINGS = Settings(_env_file=None, llm="gemini", GEMINI_API_KEY="test-key")


class _ScriptedModels:
    def __init__(self, outcomes: Sequence[object]) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0
        self.configs: list[genai_types.GenerateContentConfig] = []

    async def generate_content(
        self, *, model: str, contents: object, config: genai_types.GenerateContentConfig
    ) -> object:
        self.calls += 1
        self.configs.append(config)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(text=outcome, usage_metadata=None, candidates=[])


class ScriptedClient:
    """Answers ``client.aio.models.generate_content`` from a script; never touches a network."""

    def __init__(self, outcomes: Sequence[object]) -> None:
        self.models = _ScriptedModels(outcomes)
        self.aio = SimpleNamespace(models=self.models)


def gemini(client: ScriptedClient, tmp_path: Path) -> GeminiBackend:
    return GeminiBackend(
        GEMINI_SETTINGS,
        client=client,
        cache_dir=tmp_path,
        budget=DailyBudget(),
        retry_delays_s=(0.0, 0.0),
    )


def test_the_daily_budget_follows_googles_quota_day() -> None:
    """research/10: free-tier requests per day reset at midnight Pacific time. Counting UTC
    days opened a second budget at 0000Z, five hours before Google's day ended (1700 PDT)."""
    clock = FixedClock(datetime(2026, 10, 10, 23, 50, tzinfo=UTC))  # 1650 PDT on 10 Oct
    budget = DailyBudget(now=clock.now)
    budget.take("main", 2)
    budget.take("main", 2)
    clock.set(datetime(2026, 10, 11, 0, 10, tzinfo=UTC))  # 1710 PDT, still Google's 10 Oct
    with pytest.raises(BudgetExhausted):
        budget.take("main", 2)
    clock.set(datetime(2026, 10, 11, 7, 1, tzinfo=UTC))  # 0001 PDT on 11 Oct
    budget.take("main", 2)
    assert budget.used("main") == 1


def test_the_daily_budget_survives_a_restart(tmp_path: Path) -> None:
    """A restart used to hand the day's quota out again; the counts now outlive the process
    until Google's quota day ends."""
    clock = FixedClock(datetime(2026, 10, 10, 23, 50, tzinfo=UTC))  # 1650 PDT on 10 Oct
    path = tmp_path / "llm" / "daily_budget.json"
    before = DailyBudget(now=clock.now, path=path)
    before.take("main", 2)
    before.take("main", 2)
    before.exhaust("lite")

    after = DailyBudget(now=clock.now, path=path)
    assert after.used("main") == 2
    with pytest.raises(BudgetExhausted):
        after.take("main", 2)
    with pytest.raises(BudgetExhausted):
        after.take("lite", 100)

    clock.set(datetime(2026, 10, 11, 7, 1, tzinfo=UTC))  # 0001 PDT on 11 Oct
    next_day = DailyBudget(now=clock.now, path=path)
    assert next_day.used("main") == 0
    next_day.take("lite", 100)


def test_the_daily_budget_counts_in_memory_when_its_file_cannot_be_written(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    blocked = tmp_path / "llm"
    blocked.write_text("a file where the directory should be", encoding="utf-8")
    budget = DailyBudget(path=blocked / "daily_budget.json")
    with caplog.at_level(logging.WARNING, logger="tephra.agents.llm"):
        budget.take("main", 1)
    with pytest.raises(BudgetExhausted):
        budget.take("main", 1)
    assert "could not save the llm daily budget" in caplog.text


async def test_gemini_keeps_its_daily_budget_under_the_cache_dir(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, llm="gemini", GEMINI_API_KEY="test-key", cache_dir=tmp_path)
    llm = GeminiBackend(settings, client=ScriptedClient(['{"value": 7}']))
    await llm.structured(
        tier="main",
        system="s",
        parts=[LlmPart.of_text("question")],
        schema=_Answer,
        stub=lambda: _Answer(value=0),
    )
    saved = json.loads((tmp_path / "llm" / "daily_budget.json").read_text(encoding="utf-8"))
    assert saved["used"] == {"main": 1}


@pytest.mark.parametrize(
    ("model", "temperature"),
    [("gemini-3.8-flash", 1.0), ("gemini-3.5-flash-lite", 1.0), ("gemini-2.5-flash", 0.2)],
)
async def test_gemini_3_models_run_at_their_default_temperature(
    tmp_path: Path, model: str, temperature: float
) -> None:
    """research/10 C9: Google strongly recommends temperature 1.0 for every Gemini 3 model,
    since lower values may loop. A caller that names no temperature gets the model's own."""
    client = ScriptedClient(['{"value": 7}'])
    settings = Settings(_env_file=None, llm="gemini", GEMINI_API_KEY="test-key", model=model)
    llm = GeminiBackend(settings, client=client, cache_dir=tmp_path, budget=DailyBudget())
    await llm.structured(
        tier="main",
        system="s",
        parts=[LlmPart.of_text("question")],
        schema=_Answer,
        stub=lambda: _Answer(value=0),
    )
    assert [config.temperature for config in client.models.configs] == [temperature]


DAILY_QUOTA_429 = {
    "error": {
        "code": 429,
        "status": "RESOURCE_EXHAUSTED",
        "message": "You exceeded your current quota.",
        "details": [
            {
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}],
            },
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "41s"},
        ],
    }
}


class _Answer(BaseModel):
    value: int


async def test_a_spent_daily_quota_falls_back_without_more_requests(tmp_path: Path) -> None:
    """A 429 naming a per-day quota cannot clear before Google's day ends: no retries, and
    the tier is closed so later calls fall back to code without a request."""
    client = ScriptedClient([genai_errors.ClientError(429, DAILY_QUOTA_429) for _ in range(6)])
    llm = gemini(client, tmp_path)
    parts = [LlmPart.of_text("question")]

    value, call = await llm.structured(
        tier="main", system="s", parts=parts, schema=_Answer, stub=lambda: _Answer(value=0)
    )
    assert value is None
    assert call.error is not None
    assert "429" in call.error
    assert client.models.calls == 1

    value, call = await llm.structured(
        tier="main", system="s", parts=parts, schema=_Answer, stub=lambda: _Answer(value=0)
    )
    assert value is None
    assert call.error == "budget_exhausted"
    assert client.models.calls == 1
    assert llm.reserve("lite"), "the lite tier has its own quota"


async def test_a_per_minute_429_is_still_retried(tmp_path: Path) -> None:
    per_minute = {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": []}}
    client = ScriptedClient([genai_errors.ClientError(429, per_minute), '{"value": 7}'])
    value, call = await gemini(client, tmp_path).structured(
        tier="main",
        system="s",
        parts=[LlmPart.of_text("question")],
        schema=_Answer,
        stub=lambda: _Answer(value=0),
    )
    assert value == _Answer(value=7)
    assert call.error is None
    assert client.models.calls == 2


@pytest.mark.parametrize(
    "malformed",
    [
        '{"mode": "WIDE"}',
        '{"extent_km": NaN}',
        '```json\n{"mode": "OFFICIAL"}\n```',
        "I cannot see the plume.",
        "",
    ],
)
async def test_malformed_output_gets_one_repair_then_official_products_only(
    situation: Situation, tmp_path: Path, malformed: str
) -> None:
    client = ScriptedClient([malformed, malformed])
    with use_clock(FixedClock(AT)):
        assessment = await read_plume(situation, gemini(client, tmp_path), settings=SETTINGS)
    assert client.models.calls == (1 if malformed == "" else 2)
    assert assessment.outcome == "MODEL_FAILED"
    assert assessment.validation_errors
    assert assessment.estimate.top_fl * 100 >= situation.official_top_ft()


async def test_a_malformed_answer_repaired_by_the_model_is_accepted(
    situation: Situation, tmp_path: Path
) -> None:
    client = ScriptedClient(['{"extent_km": NaN}', good_estimate(situation).model_dump_json()])
    with use_clock(FixedClock(AT)):
        assessment = await read_plume(situation, gemini(client, tmp_path), settings=SETTINGS)
    assert assessment.outcome == "REPAIRED"
    assert assessment.attempts == 2
    assert [config.temperature for config in client.models.configs] == [1.0, 1.0]
