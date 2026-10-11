"""The Exposure Planner's ADK path (google-adk 2.x), run offline against a scripted model.

A ``BaseLlm`` registered for ``tephra-scripted-*`` model names stands in for Gemini, so the
real ``LlmAgent``, ``FunctionTool`` wrapping, ``InMemoryRunner`` and session state all run
without a key or a network call.
"""

import inspect
import re
from collections.abc import AsyncGenerator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

import pytest
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.adk.models.google_llm import _ResourceExhaustedError
from google.adk.models.registry import LLMRegistry
from google.genai import errors as genai_errors
from google.genai import types
from test_plume_reader import DAILY_QUOTA_429

# Importing adk_app runs get_settings() now, before any test patches the environment.
from tephra.agents.adk_app import build_planner_agent
from tephra.agents.exposure_planner import PROMPT_PATH, plan_flight, planner_limits
from tephra.agents.llm import DailyBudget, GeminiBackend, LlmBackend
from tephra.agents.validators import allowed_actions
from tephra.config import PROJECT_ROOT, Settings
from tephra.geo.fuel import category_for_type, divert_line, hold_line
from tephra.models import (
    ActionKind,
    AlternateCandidate,
    AlternateCheck,
    ExposedFlight,
    LlmBackendName,
    PlannerContext,
    PlumeMode,
    TraceEvent,
)
from tephra.policy import load_policy
from tephra.util.hashing import proxy_flight_number
from tephra.util.timeutil import FixedClock, use_clock

AT = datetime(2026, 10, 9, 18, 30, tzinfo=UTC)
SCRIPTED_MODEL = "tephra-scripted-planner"
POLICY = load_policy(PROJECT_ROOT / "data")
HOLD_MIN = POLICY.fuel.hold_min.value
DIVERT_EXTRA_MIN = POLICY.fuel.divert_extra_min.value

Turn = list[types.Part] | Exception
_SCRIPT: list[Turn] = []
_CALLS: list[LlmRequest] = []


class ScriptedLlm(BaseLlm):
    """Answers each model turn with the next scripted parts, or raises a scripted error."""

    patterns: ClassVar[list[str]] = [r"tephra-scripted-.*"]

    @classmethod
    def supported_models(cls) -> list[str]:
        return cls.patterns

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        _CALLS.append(llm_request)
        turn = _SCRIPT.pop(0) if _SCRIPT else [types.Part(text="DONE")]
        if isinstance(turn, Exception):
            raise turn
        yield LlmResponse(content=types.Content(role="model", parts=turn))


LLMRegistry.register(ScriptedLlm)


@pytest.fixture(autouse=True)
def script() -> Iterator[list[Turn]]:
    _SCRIPT.clear()
    _CALLS.clear()
    yield _SCRIPT
    _SCRIPT.clear()


class GeminiStandIn:
    """Only what ``plan_flight`` reads from a non-stub backend: its name, ids and budget."""

    def __init__(self, *, budget_left: bool = True) -> None:
        self.name: LlmBackendName = "gemini"
        self._budget_left = budget_left

    def model_id(self, tier: str) -> str:
        return "gemini-test-lite"

    async def pace(self, tier: str) -> None:
        return None

    def reserve(self, tier: str) -> bool:
        return self._budget_left

    def exhaust(self, tier: str) -> None:
        self._budget_left = False

    async def structured(self, **_: Any) -> Any:
        raise AssertionError("the planner never makes a structured call")


def call(name: str, **args: Any) -> list[types.Part]:
    return [types.Part(function_call=types.FunctionCall(name=name, args=args))]


def text(message: str) -> list[types.Part]:
    return [types.Part(text=message)]


def make_ctx() -> PlannerContext:
    """FL170, 12 minutes from a SFC/FL150 cone; WIII failed its screen, WARR passed."""
    category = category_for_type("B738")
    hex_id = "8a0123"
    flight = ExposedFlight(
        id=f"{hex_id}:263300",
        hex=hex_id,
        callsign="GIA417",
        proxy_flight=proxy_flight_number(hex_id),
        type_icao="B738",
        category=category,
        lat=-7.5,
        lon=112.0,
        alt_baro_ft=17_000,
        gs_kt=440.0,
        track_deg=110.0,
        observed_at=AT,
        source_id="ADSB:-8.200:113.600:20261009T183000Z",
        volcano_id="263300",
        cone_id="CONE-0123456789ab",
        inside_now=False,
        minutes_to_entry=12,
        entry_lat=-7.9,
        entry_lon=112.9,
        aircraft_band_ft=(17_000, 17_000),
        hazard_band_ft=(0, 15_000),
        path=[(112.0, -7.5), (112.9, -7.9)],
        hold=hold_line(category, minutes=HOLD_MIN),
    )
    alternates = [
        AlternateCandidate(
            icao=icao,
            name=name,
            distance_nm=distance,
            bearing_deg=270.0,
            check=AlternateCheck(
                icao=icao,
                ok=ok,
                reasons=[] if ok else ["VA IN TEMPO GROUP"],
                taf_source_id=f"TAF:{icao}:20261009T1700Z",
                checked_for=AT,
            ),
            divert=divert_line(
                category,
                alternate_icao=icao,
                distance_nm=distance,
                gs_kt=440.0,
                extra_minutes=DIVERT_EXTRA_MIN,
            ),
        )
        for icao, name, distance, ok in (
            ("WIII", "Soekarno-Hatta International", 50.0, False),
            ("WARR", "Juanda International", 120.0, True),
        )
    ]
    return PlannerContext(
        flight=flight,
        volcano_name="Semeru",
        plume_mode=PlumeMode.OFFICIAL,
        confidence=0.8,
        hazard_base_ft=0,
        hazard_top_ft=15_000,
        vertical_margin_ft=2_000,
        allowed_actions=allowed_actions(PlumeMode.OFFICIAL),
        alternates=alternates,
        hold=flight.hold,
        **planner_limits(POLICY),
    )


async def plan(llm: LlmBackend, *, model: str = SCRIPTED_MODEL) -> tuple[Any, list[TraceEvent]]:
    trace: list[TraceEvent] = []
    settings = Settings(_env_file=None, model_lite=model)
    with use_clock(FixedClock(AT)):
        planned = await plan_flight(make_ctx(), llm, settings=settings, trace=trace.append)
    return planned, trace


async def test_adk_agent_reads_tools_and_submits_a_plan(script: list[Turn]) -> None:
    script += [
        call("get_flight"),
        call("list_alternates"),
        call("check_level_band", fl_min=180, fl_max=200),
        call(
            "submit_plan",
            action="CHANGE_LEVEL",
            reasoning="HAZARD SFC/FL150, ENTRY IN 12 MIN. FL180-FL200 IS CLEAR OF IT.",
            change_level_fl_min=180,
            change_level_fl_max=200,
            alternatives_considered=["HOLD", "DIVERT"],
        ),
        text("CHANGE_LEVEL FL180-FL200 submitted."),
    ]
    planned, trace = await plan(GeminiStandIn())
    assert planned.outcome == "ACCEPTED"
    assert planned.llm_backend == "gemini"
    assert planned.decision.action is ActionKind.CHANGE_LEVEL
    assert (planned.decision.change_level_fl_min, planned.decision.change_level_fl_max) == (
        180,
        200,
    )
    assert [record.name for record in planned.tool_calls] == [
        "get_flight",
        "list_alternates",
        "check_level_band",
        "submit_plan",
    ]
    assert {event.actor for event in trace} == {"adk"}
    first = _CALLS[0]
    assert str(first.config.system_instruction).startswith("# TEPHRA Exposure Planner")


async def test_rejected_plan_gets_one_repair_turn(script: list[Turn]) -> None:
    script += [
        call("submit_plan", action="DIVERT", reasoning="DIVERT WIII.", alternate_icao="WIII"),
        text("Submitted."),
        call("submit_plan", action="DIVERT", reasoning="WARR PASSED.", alternate_icao="warr"),
        text("DIVERT WARR."),
    ]
    planned, trace = await plan(GeminiStandIn())
    assert planned.outcome == "REPAIRED"
    assert planned.decision.alternate_icao == "WARR"
    assert any("REPAIR" in event.message for event in trace)


async def test_bad_tool_arguments_go_back_to_the_model(script: list[Turn]) -> None:
    script += [
        call("check_level_band", fl_min=180, fl_max=200.5),
        call(
            "submit_plan",
            action="CHANGE_LEVEL",
            reasoning="FL180-FL200 CLEARS THE HAZARD.",
            change_level_fl_min=180,
            change_level_fl_max=200,
        ),
        text("ok"),
    ]
    planned, _ = await plan(GeminiStandIn())
    assert planned.outcome == "ACCEPTED", planned.validation_errors
    band_check = planned.tool_calls[0]
    assert band_check.name == "check_level_band"
    assert "error" in band_check.result_summary


async def test_agent_error_gives_no_plan_and_keeps_the_trace(script: list[Turn]) -> None:
    script += [call("get_flight"), RuntimeError("model unavailable")]
    planned, trace = await plan(GeminiStandIn())
    assert planned.outcome == "MODEL_FAILED"
    assert planned.decision is None
    assert planned.fuel is None
    assert planned.validation_errors == ["PLANNER AGENT ERROR: RuntimeError"]
    assert [record.name for record in planned.tool_calls] == ["get_flight"]
    failed = trace[-1]
    assert failed.level == "error"
    assert "AI UNAVAILABLE" in failed.message
    assert "A DISPATCHER MUST PLAN THIS FLIGHT" in failed.message


async def test_without_an_api_key_there_is_no_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The real ADK Gemini model, Gemini API (never Vertex AI) and no key: the client refuses
    # to build before any request is made.
    for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")
    monkeypatch.setenv("GOOGLE_GENAI_USE_ENTERPRISE", "FALSE")
    planned, trace = await plan(GeminiStandIn(), model="gemini-3.5-flash-lite")
    assert planned.outcome == "MODEL_FAILED"
    assert planned.decision is None
    assert planned.validation_errors == ["PLANNER AGENT ERROR: ValueError"]
    assert any("AI UNAVAILABLE" in event.message for event in trace)


async def test_exhausted_budget_stops_before_any_model_call(script: list[Turn]) -> None:
    script += [call("get_flight")]
    planned, trace = await plan(GeminiStandIn(budget_left=False))
    assert _CALLS == []
    assert planned.outcome == "MODEL_FAILED"
    assert "budget_exhausted" in planned.validation_errors
    assert "AI UNAVAILABLE" in trace[-1].message


async def test_a_spent_daily_quota_closes_the_lite_tier(script: list[Turn], tmp_path: Path) -> None:
    """A 429 naming a per-day quota reaches the planner as ADK's wrapped ClientError. Nothing
    clears it before Google's quota day ends, so the run stops without a repair turn, no plan
    is made, and the lite tier stays closed for the Drafter and later flights."""
    script += [_ResourceExhaustedError(genai_errors.ClientError(429, DAILY_QUOTA_429))]
    settings = Settings(
        _env_file=None, llm="gemini", GEMINI_API_KEY="test-key", model_lite=SCRIPTED_MODEL
    )
    llm = GeminiBackend(settings, cache_dir=tmp_path, budget=DailyBudget())
    planned, trace = await plan(llm)
    assert len(_CALLS) == 1
    assert planned.outcome == "MODEL_FAILED"
    assert any("DAILY QUOTA" in problem for problem in planned.validation_errors)
    assert "AI UNAVAILABLE" in trace[-1].message
    assert not llm.reserve("lite")
    assert llm.reserve("main")


@pytest.mark.parametrize(
    ("model", "temperature"), [("gemini-3.5-flash-lite", 1.0), (SCRIPTED_MODEL, 0.2)]
)
def test_the_planner_runs_gemini_3_at_temperature_one(model: str, temperature: float) -> None:
    """research/10 C9: Google strongly recommends temperature 1.0 for Gemini 3 models."""
    config = build_planner_agent(model).generate_content_config
    assert config is not None
    assert config.temperature == temperature


def test_planner_prompt_matches_the_tools_the_agent_has() -> None:
    tools = {
        tool.__name__: [
            name for name in inspect.signature(tool).parameters if name != "tool_context"
        ]
        for tool in build_planner_agent(SCRIPTED_MODEL).tools
        if callable(tool)
    }
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    named: dict[str, set[str]] = {}
    for name, args in re.findall(r"`([a-z_]+)\(([a-z_, .]*)\)`", prompt):
        named.setdefault(name, set()).add(args)
    assert set(named) == set(tools)
    for name, spellings in named.items():
        for args in spellings - {"", "..."}:  # `name()` and `name(...)` are references
            assert [arg.strip() for arg in args.split(",")] == tools[name], name
    known = set(tools) | set(tools["submit_plan"])
    fields = set(re.findall(r"`([a-z_]+)`", prompt))
    assert fields <= known, sorted(fields - known)


async def test_a_looping_model_is_stopped_by_the_turn_limit(script: list[Turn]) -> None:
    script += [call("get_flight") for _ in range(30)]
    planned, _ = await plan(GeminiStandIn())
    assert len(_CALLS) == 10
    assert planned.outcome == "MODEL_FAILED"
    assert any("TURN LIMIT" in problem for problem in planned.validation_errors)
