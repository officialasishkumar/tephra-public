"""The Exposure Planner as a Google ADK app: ``root_agent`` for ``adk web`` and ``adk eval``.

The tools are thin wrappers: each reads the flight's ``PlannerContext`` from session state
(``state["tephra_ctx"]``, a ``PlannerContext`` JSON dump) and returns what code computed.
Geometry, alternates, TAF screening and costs are never the model's work.

Gemini is reached only with a Google AI Studio key, never Vertex AI or ADC.
``tephra.config.get_settings()`` (called below) pins ``GOOGLE_GENAI_USE_VERTEXAI`` and
``GOOGLE_GENAI_USE_ENTERPRISE`` to FALSE and copies ``GEMINI_API_KEY`` into
``GOOGLE_API_KEY``. Outside the app, set the same in the shell first::

    export GOOGLE_GENAI_USE_VERTEXAI=FALSE GOOGLE_GENAI_USE_ENTERPRISE=FALSE
    export GEMINI_API_KEY=...            # AI Studio key
    uv run adk web tephra/agents         # choose "adk_app"; seed state["tephra_ctx"]

For evaluation, ``AgentEvaluator.evaluate(agent_module="tephra.agents.adk_app", ...)``
with eval cases that put a ``PlannerContext`` dump in ``session_input.state["tephra_ctx"]``.
"""

import sys
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools import BaseTool, ToolContext
from google.genai import types

from tephra.agents.exposure_planner import (
    CONTEXT_STATE_KEY,
    DECISION_STATE_KEY,
    PROMPT_PATH,
    alternate_summary,
    alternates_summary,
    context_from_state,
    cost_summary,
    flight_summary,
    level_band_summary,
    submit_decision,
)
from tephra.agents.llm import temperature_for
from tephra.config import get_settings
from tephra.models import PlannerContext

AGENT_NAME = "tephra_exposure_planner"
_NO_CONTEXT = {"error": f"NO PLANNER CONTEXT IN SESSION STATE KEY {CONTEXT_STATE_KEY}"}


def _context(tool_context: ToolContext) -> PlannerContext | None:
    return context_from_state(tool_context.state.get(CONTEXT_STATE_KEY))


def get_flight(tool_context: ToolContext) -> dict[str, Any]:
    """Return the exposed flight: present and selected flight level, ground speed, track,
    minutes to hazard entry (or inside now), the hazard band, the vertical margin, the
    plume mode with its confidence, the actions allowed in that mode and the hold cost."""
    ctx = _context(tool_context)
    return flight_summary(ctx) if ctx is not None else _NO_CONTEXT


def list_alternates(tool_context: ToolContext) -> dict[str, Any]:
    """List the nearby alternate aerodromes, nearest first, each with distance, bearing,
    whether it passed the TAF and hazard-cone screen (with reasons), and its divert cost."""
    ctx = _context(tool_context)
    return alternates_summary(ctx) if ctx is not None else _NO_CONTEXT


def check_alternate(icao: str, tool_context: ToolContext) -> dict[str, Any]:
    """Return the screen result and divert cost of one listed alternate (4-letter ICAO)."""
    ctx = _context(tool_context)
    return alternate_summary(ctx, icao) if ctx is not None else _NO_CONTEXT


def check_level_band(fl_min: int, fl_max: int, tool_context: ToolContext) -> dict[str, Any]:
    """Check whether a flight-level band (e.g. 180 to 200) is clear of the hazard band plus
    the vertical margin and at or below FL410, and how far it is from the present level."""
    ctx = _context(tool_context)
    return level_band_summary(ctx, fl_min, fl_max) if ctx is not None else _NO_CONTEXT


def estimate_cost(
    action: str, tool_context: ToolContext, alternate_icao: str | None = None
) -> dict[str, Any]:
    """Return TEPHRA's labelled time and fuel formula for HOLD, or for DIVERT to a listed
    alternate (pass alternate_icao). Other actions carry no extra hold or diversion fuel."""
    ctx = _context(tool_context)
    return cost_summary(ctx, action, alternate_icao) if ctx is not None else _NO_CONTEXT


def submit_plan(
    action: str,
    reasoning: str,
    tool_context: ToolContext,
    change_level_fl_min: int | None = None,
    change_level_fl_max: int | None = None,
    hold_fl: int | None = None,
    alternate_icao: str | None = None,
    alternatives_considered: list[str] | None = None,
) -> dict[str, Any]:
    """Submit the plan for this flight. action is one of CONTINUE, MONITOR, CHANGE_LEVEL,
    HOLD, DIVERT. CHANGE_LEVEL needs change_level_fl_min and change_level_fl_max; HOLD
    needs hold_fl; DIVERT needs alternate_icao. reasoning is two or three sentences of
    operational language with no clock times. The result lists any problems to fix."""
    ctx = _context(tool_context)
    if ctx is None:
        return _NO_CONTEXT
    decision, problems = submit_decision(
        ctx,
        action=action,
        reasoning=reasoning,
        change_level_fl_min=change_level_fl_min,
        change_level_fl_max=change_level_fl_max,
        hold_fl=hold_fl,
        alternate_icao=alternate_icao,
        alternatives_considered=alternatives_considered,
    )
    if decision is not None:
        tool_context.state[DECISION_STATE_KEY] = decision.model_dump(mode="json")
    return {"accepted": not problems, "problems": problems}


def _instruction(_: ReadonlyContext) -> str:
    # A provider (not a plain string) so ADK does not template "{...}" in the prompt file.
    return PROMPT_PATH.read_text(encoding="utf-8")


def _tool_error(
    tool: BaseTool, args: dict[str, Any], tool_context: ToolContext, error: Exception
) -> dict[str, Any]:
    """Answers a tool that raised on the model's arguments, so the model can correct them.

    ADK 2.x does not coerce tool arguments by default and aborts the whole run when a tool
    raises; a level of 200.5 or "FL200" would otherwise end planning for the flight.
    """
    return {
        "error": f"{tool.name} COULD NOT USE THESE ARGUMENTS ({type(error).__name__}). PASS"
        " FLIGHT LEVELS AS WHOLE NUMBERS (E.G. 180), ACTIONS AND ICAO CODES AS TEXT."
    }


def build_planner_agent(
    model: str, *, before_model_callback: Any = None, on_model_error_callback: Any = None
) -> LlmAgent:
    """The planner agent; the model callbacks are how the app enforces its daily budget."""
    return LlmAgent(
        name=AGENT_NAME,
        model=model,
        description="Picks one safe action per flight exposed to a volcanic-ash hazard cone.",
        instruction=_instruction,
        tools=[
            get_flight,
            list_alternates,
            check_alternate,
            check_level_band,
            estimate_cost,
            submit_plan,
        ],
        generate_content_config=types.GenerateContentConfig(temperature=temperature_for(model)),
        before_model_callback=before_model_callback,
        on_model_error_callback=on_model_error_callback,
        on_tool_error_callback=_tool_error,
    )


root_agent: LlmAgent = build_planner_agent(get_settings().model_lite)

# ADK's AgentEvaluator imports `agent_module` and then reads `<module>.agent.root_agent`
# unless the module name ends in ".agent" (google-adk 2.11 agent_evaluator). Pointing `agent`
# at this module itself lets agent_module="tephra.agents.adk_app" resolve to root_agent.
agent = sys.modules[__name__]
