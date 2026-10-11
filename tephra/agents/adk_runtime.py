"""What every TEPHRA ADK agent shares: the budget guard in front of each model turn and the
record of each tool call.

The Exposure Planner, Ask TEPHRA, the recovery agent and the Duty Officer all run a Google ADK
``LlmAgent`` on the lite tier. Each model turn is taken from the daily budget before it is
sent; a per-day 429 closes the tier until Google's quota day ends; a turn cap stops a model
that loops. A stopped run ends with no answer, and the caller reports AI UNAVAILABLE.
"""

import json
from typing import Any, Final

from tephra.agents.llm import LlmBackend, daily_quota_spent
from tephra.models import ToolCallRecord

__all__ = [
    "BUDGET_EXHAUSTED",
    "DAILY_QUOTA_SPENT",
    "ModelGuard",
    "stop_response",
    "summarise",
    "tool_record",
]

DAILY_QUOTA_SPENT: Final = "GEMINI DAILY QUOTA SPENT (429): LITE TIER CLOSED FOR THE QUOTA DAY"
BUDGET_EXHAUSTED: Final = "budget_exhausted"
SUMMARY_CHARS: Final = 240
"""Tool results are kept on record (and in the trace) cut to this length."""


class ModelGuard:
    """The daily budget in front of every ADK model turn.

    As ``before_model_callback`` it takes each turn from the lite budget, caps the turns and
    waits for the turn's slot in the per-minute limit (``LlmBackend.pace``);
    as ``on_model_error`` (the ``on_model_error_callback``) it closes the lite tier for the
    quota day when Gemini answers 429 for a per-day quota, which no retry clears. Either one
    answers in the model's place to stop; with no function call in that answer the run ends.
    """

    def __init__(self, llm: LlmBackend, *, max_turns: int) -> None:
        self._llm = llm
        self._max_turns = max_turns
        self.turns = 0
        self.stop_reason: str | None = None

    async def __call__(self, callback_context: Any, llm_request: Any) -> Any:
        self.turns += 1
        if self.turns > self._max_turns:
            self.stop_reason = f"MODEL TURN LIMIT {self._max_turns} REACHED"
        elif not self._llm.reserve("lite"):
            self.stop_reason = BUDGET_EXHAUSTED
        if self.stop_reason is not None:
            return stop_response(self.stop_reason)
        await self._llm.pace("lite")
        return None

    def on_model_error(self, callback_context: Any, llm_request: Any, error: Exception) -> Any:
        if not daily_quota_spent(error):
            return None
        self._llm.exhaust("lite")
        self.stop_reason = DAILY_QUOTA_SPENT
        return stop_response(self.stop_reason)


def stop_response(reason: str) -> Any:
    """A model answer with no function call, so ADK ends the run."""
    from google.adk.models import LlmResponse
    from google.genai import types

    stop = types.Part(text=f"STOPPED: {reason}")
    return LlmResponse(content=types.Content(role="model", parts=[stop]))


def tool_record(name: str, args: dict[str, Any], result: Any) -> ToolCallRecord:
    return ToolCallRecord(name=name, args=args, result_summary=summarise(result))


def summarise(result: Any, limit: int = SUMMARY_CHARS) -> str:
    text = json.dumps(result, default=str, separators=(",", ":"), ensure_ascii=True)
    return text if len(text) <= limit else text[: limit - 3] + "..."
