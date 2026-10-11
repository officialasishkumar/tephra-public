"""The recovery planner: an ADK agent on the lite model that runs scenarios through the solver
and recommends one, as a DRAFT for a dispatcher.

The tools are ``tephra.recovery.tools.Toolbox`` methods; everything numeric comes from the
solver. The rationale is checked against the tool results (``validate_recommendation``) with
one repair turn. With no model answer that passes, there is no plan: the result says
``AI UNAVAILABLE`` and nothing is substituted. The stub backend (``TEPHRA_LLM=stub``) runs the
same tools and recommends the published-closure scenario in fixed words, labelled NO MODEL.
"""

import asyncio
import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal

from tephra.agents.llm import LlmBackend, LlmPart, daily_quota_spent, prompt_hash, temperature_for
from tephra.config import Settings
from tephra.models import (
    Airport,
    OperatorPolicy,
    ToolCallRecord,
    TraceActor,
    TraceEvent,
    TraceSink,
    TraceStage,
)
from tephra.recovery.models import (
    AI_UNAVAILABLE,
    Closure,
    Disruption,
    RecoveryPlan,
    RecoveryScenario,
    Schedule,
    SolveStatus,
)
from tephra.recovery.solver import describe_disruption
from tephra.recovery.tools import Toolbox
from tephra.util import timeutil
from tephra.util.hashing import sha256_json, stable_id

if TYPE_CHECKING:
    from google.adk.agents import LlmAgent
    from google.adk.runners import InMemoryRunner

__all__ = ["PROMPT_PATH", "build_recovery_agent", "recommend_recovery"]

logger = logging.getLogger(__name__)

PROMPT_PATH: Final = Path(__file__).resolve().parent.parent / "agents" / "prompts" / "recovery.md"
ADK_APP_NAME: Final = "tephra_recovery"
ADK_USER_ID: Final = "tephra-dispatch"
"""ADK sessions need a user id; no person is behind it and no name is sent to Gemini."""
AGENT_NAME: Final = "tephra_recovery_planner"
MAX_MODEL_TURNS: Final = 16
"""Model calls per run, tool round trips and the repair turn included: about 8 are normal."""
DAILY_QUOTA_SPENT: Final = "GEMINI DAILY QUOTA SPENT (429): LITE TIER CLOSED FOR THE QUOTA DAY"
_SUMMARY_CHARS: Final = 240
_TASK: Final = (
    "Closures are in force. Read the disruption, run the closure as published and the two"
    " extensions it lists, compare the scenarios, then call submit_recommendation exactly once."
)

Outcome = Literal["ACCEPTED", "REPAIRED", "MODEL_FAILED", "STUB"]


# --- the entry point ------------------------------------------------------------------------


async def recommend_recovery(
    schedule: Schedule,
    closures: Sequence[Closure],
    llm: LlmBackend,
    *,
    settings: Settings,
    policy: OperatorPolicy,
    airports: Mapping[str, Airport],
    replay: bool,
    trace: TraceSink | None = None,
) -> RecoveryPlan:
    """A DRAFT plan, or a stored ``AI_UNAVAILABLE`` record when no valid recommendation came."""
    now = timeutil.now()
    box = Toolbox(schedule, closures, now=now, policy=policy, airports=airports)
    found = describe_disruption(schedule, closures, now=now, policy=policy)
    system = PROMPT_PATH.read_text(encoding="utf-8")
    phash = prompt_hash(system, [LlmPart.of_text(found.model_dump_json())])
    run = _Run(model_id=llm.model_id("lite"))
    if llm.name == "stub":
        await _stub(box, run)
    else:
        try:
            await _adk(box, llm, run, settings=settings, trace=trace)
        except Exception as exc:  # ADK or API failure: no plan, agents never raise
            logger.warning("recovery agent failed: %s", type(exc).__name__)
            run.problems = [f"RECOVERY AGENT ERROR: {type(exc).__name__}"]
    plan = _plan(box, run, llm, found, now=now, replay=replay, phash=phash)
    _emit(trace, plan)
    return plan


@dataclass
class _Run:
    model_id: str
    outcome: Outcome = "ACCEPTED"
    records: list[ToolCallRecord] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def _plan(
    box: Toolbox,
    run: _Run,
    llm: LlmBackend,
    found: Disruption,
    *,
    now: datetime,
    replay: bool,
    phash: str,
) -> RecoveryPlan:
    accepted = box.accepted
    base: dict[str, Any] = {
        "id": stable_id("REC", now, sha256_json(found.model_dump(mode="json"))),
        "created_at": now,
        "replay": replay,
        "closures": found.closures,
        "disruption": found,
        "llm_backend": llm.name,
        "model_id": run.model_id,
        "prompt_hash": phash,
        "tool_calls": run.records,
    }
    if accepted is not None and not run.problems:
        return RecoveryPlan(
            **base,
            status="DRAFT",
            scenarios=sorted(box.scenarios.values(), key=lambda s: s.extend_min),
            chosen_scenario_id=accepted.scenario_id,
            rationale=accepted.rationale,
            risks=accepted.risks,
            outcome=run.outcome,
        )
    problems = run.problems or box.problems or ["NO RECOMMENDATION SUBMITTED"]
    reason = "; ".join(problems[:3])
    return RecoveryPlan(
        **base,
        status="AI_UNAVAILABLE",
        unavailable_reason=f"{AI_UNAVAILABLE}: {reason}",
        outcome="MODEL_FAILED",
        validation_errors=problems,
    )


# --- stub ------------------------------------------------------------------------------------


async def _stub(box: Toolbox, run: _Run) -> None:
    """NO MODEL: the published closure, in fixed words that quote the comparison."""
    run.outcome = "STUB"
    rules = box.policy.recovery
    for extend in (0, rules.scenario_extend_1_min.value, rules.scenario_extend_2_min.value):
        summary = await box.run_scenario(extend)
        run.records.append(_record("run_scenario", {"extend_min": extend}, summary))
    ids = list(box.scenarios)
    table = box.compare(ids)
    run.records.append(_record("compare", {"scenario_ids": ids}, table))
    first = next(iter(box.scenarios.values()))
    rows = {row["scenario_id"]: row for row in table.get("scenarios", [])}
    row = rows.get(first.id, {})
    if first.status is SolveStatus.NO_PLAN or "total_usd" not in row:
        run.problems = [f"NO FEASIBLE PLAN FOR THE PUBLISHED CLOSURE ({first.solver_status})"]
        return
    words = (
        f"NO MODEL: the plan for the published closure cancels {row['cancelled_flights']}"
        f" flights and delays {row['delayed_flights']}, affects {row['passengers_affected']}"
        f" passengers and costs {row['total_usd']} USD."
    )
    result = box.submit(first.id, words, [])
    run.records.append(_record("submit_recommendation", {"scenario_id": first.id}, result))


# --- ADK -------------------------------------------------------------------------------------


def build_recovery_agent(
    model: str,
    box: Toolbox,
    *,
    before_model_callback: Any = None,
    on_model_error_callback: Any = None,
) -> "LlmAgent":
    from google.adk.agents import LlmAgent
    from google.adk.agents.readonly_context import ReadonlyContext
    from google.genai import types

    async def disruption() -> dict[str, Any]:
        """Return the closures with their sources and times, the flights and passengers they
        block, the flights the plan may change and the closure extensions to run as scenarios."""
        return box.disruption()

    async def run_scenario(
        extend_min: int,
        protect_flights: list[str] | None = None,
        max_delay_min: int | None = None,
    ) -> dict[str, Any]:
        """Solve the day with every closure lasting extend_min minutes longer than published
        (0 for as published). protect_flights lists flight keys (number/date, like
        RFA239/06SEP) that must not be cancelled; max_delay_min shortens the longest delay
        allowed. Returns the scenario id, solver status and the totals of kept, delayed,
        cancelled and moved flights, passengers and USD cost."""
        return await box.run_scenario(extend_min, protect_flights, max_delay_min)

    async def compare(scenario_ids: list[str]) -> dict[str, Any]:
        """Return the given scenarios side by side with each one's extra cost against the first."""
        return box.compare(scenario_ids)

    async def submit_recommendation(
        scenario_id: str, rationale: str, risks: list[str] | None = None
    ) -> dict[str, Any]:
        """Recommend one scenario. rationale is two to four plain sentences quoting only figures,
        times, flights, aircraft and airports the tools returned; risks is up to three short
        statements of what could still go wrong. The result lists any problems to fix."""
        return box.submit(scenario_id, rationale, risks)

    def instruction(_: ReadonlyContext) -> str:
        # A provider (not a plain string) so ADK does not template "{...}" in the prompt file.
        return PROMPT_PATH.read_text(encoding="utf-8")

    return LlmAgent(
        name=AGENT_NAME,
        model=model,
        description="Compares closure scenarios for an airline network and recommends one.",
        instruction=instruction,
        tools=[disruption, run_scenario, compare, submit_recommendation],
        generate_content_config=types.GenerateContentConfig(temperature=temperature_for(model)),
        before_model_callback=before_model_callback,
        on_model_error_callback=on_model_error_callback,
        on_tool_error_callback=_tool_error,
    )


def _tool_error(
    tool: Any, args: dict[str, Any], tool_context: Any, error: Exception
) -> dict[str, Any]:
    """Answers a tool that raised on the model's arguments, so the model can correct them."""
    return {
        "error": f"{tool.name} COULD NOT USE THESE ARGUMENTS ({type(error).__name__}). PASS"
        " MINUTES AS WHOLE NUMBERS AND FLIGHT NUMBERS AND SCENARIO IDS AS TEXT."
    }


async def _adk(
    box: Toolbox, llm: LlmBackend, run: _Run, *, settings: Settings, trace: TraceSink | None
) -> None:
    """Fills ``run`` as it goes, so the tool calls made before a failure stay on record."""
    from google.adk.runners import InMemoryRunner

    guard = _Guard(llm)
    agent = build_recovery_agent(
        settings.model_lite,
        box,
        before_model_callback=guard,
        on_model_error_callback=guard.on_model_error,
    )
    runner = InMemoryRunner(agent=agent, app_name=ADK_APP_NAME)
    try:
        session = await runner.session_service.create_session(
            app_name=ADK_APP_NAME, user_id=ADK_USER_ID
        )
        await _turn(runner, session.id, _TASK, run.records, trace, settings)
        if box.accepted is None and guard.stop_reason is None:
            problems = box.problems or ["NO RECOMMENDATION SUBMITTED: CALL submit_recommendation"]
            _emit_line(trace, "code", "RECOMMENDATION REJECTED; ONE REPAIR TURN", level="warn")
            repair = _repair_text(problems)
            await _turn(runner, session.id, repair, run.records, trace, settings)
            run.outcome = "REPAIRED"
        if box.accepted is None:
            run.problems = [
                *(box.problems or ["NO RECOMMENDATION SUBMITTED"]),
                *([guard.stop_reason] if guard.stop_reason else []),
            ]
    finally:
        await runner.close()


def _repair_text(problems: Sequence[str]) -> str:
    listed = "\n".join(f"- {problem}" for problem in problems[:8])
    return (
        f"Code rejected the recommendation:\n{listed}\n"
        "Fix these problems and call submit_recommendation again. Use only scenario ids,"
        " figures, times, flights, aircraft and airports that the tools returned."
    )


class _Guard:
    """The daily budget in front of every ADK model turn.

    As ``before_model_callback`` it takes each turn from the budget and caps turns; as
    ``on_model_error_callback`` it closes the lite tier for the quota day when Gemini answers
    429 for a per-day quota. Either one answers in the model's place to stop the run.
    """

    def __init__(self, llm: LlmBackend) -> None:
        self._llm = llm
        self.turns = 0
        self.stop_reason: str | None = None

    def __call__(self, callback_context: Any, llm_request: Any) -> Any:
        self.turns += 1
        if self.turns > MAX_MODEL_TURNS:
            self.stop_reason = f"MODEL TURN LIMIT {MAX_MODEL_TURNS} REACHED"
        elif not self._llm.reserve("lite"):
            self.stop_reason = "budget_exhausted"
        return None if self.stop_reason is None else _stop(self.stop_reason)

    def on_model_error(self, callback_context: Any, llm_request: Any, error: Exception) -> Any:
        if not daily_quota_spent(error):
            return None
        self._llm.exhaust("lite")
        self.stop_reason = DAILY_QUOTA_SPENT
        return _stop(self.stop_reason)


def _stop(reason: str) -> Any:
    from google.adk.models import LlmResponse
    from google.genai import types

    return LlmResponse(
        content=types.Content(role="model", parts=[types.Part(text=f"STOPPED: {reason}")])
    )


async def _turn(
    runner: "InMemoryRunner",
    session_id: str,
    message: str,
    records: list[ToolCallRecord],
    trace: TraceSink | None,
    settings: Settings,
) -> None:
    from google.genai import types

    content = types.Content(role="user", parts=[types.Part(text=message)])
    pending: dict[str, tuple[str, dict[str, Any]]] = {}
    async with asyncio.timeout(settings.llm_timeout_s):
        async for event in runner.run_async(
            user_id=ADK_USER_ID, session_id=session_id, new_message=content
        ):
            for call in event.get_function_calls():
                pending[call.id or call.name] = (call.name, dict(call.args or {}))
            for response in event.get_function_responses():
                name, args = pending.pop(response.id or response.name, (response.name, {}))
                record = _record(name, args, response.response)
                records.append(record)
                _emit_line(trace, "adk", f"{name}: {record.result_summary}", detail={"args": args})


# --- helpers ---------------------------------------------------------------------------------


def _record(name: str, args: dict[str, Any], result: Any) -> ToolCallRecord:
    text = json.dumps(result, default=str, separators=(",", ":"), ensure_ascii=True)
    summary = text if len(text) <= _SUMMARY_CHARS else text[: _SUMMARY_CHARS - 3] + "..."
    return ToolCallRecord(name=name, args=args, result_summary=summary)


def _emit(trace: TraceSink | None, plan: RecoveryPlan) -> None:
    if plan.status == "AI_UNAVAILABLE":
        _emit_line(
            trace,
            "code",
            f"{plan.unavailable_reason}: NO RECOVERY PLAN, A DISPATCHER MUST PLAN THE NETWORK",
            level="error",
            detail={"problems": plan.validation_errors},
        )
        return
    chosen: RecoveryScenario | None = plan.chosen
    label = chosen.label if chosen is not None else "?"
    actor: TraceActor = "stub" if plan.llm_backend == "stub" else "adk"
    _emit_line(trace, actor, f"RECOVERY DRAFT {plan.outcome}: {label}")


def _emit_line(
    trace: TraceSink | None,
    actor: TraceActor,
    message: str,
    *,
    level: Literal["info", "warn", "error"] = "info",
    detail: Mapping[str, Any] | None = None,
) -> None:
    if trace is None:
        return
    trace(TraceEvent.new(TraceStage.RECOVERY, actor, message, level=level, detail=detail))
