"""What every TEPHRA ADK agent shares: the budget guard in front of each model turn and the
record of each tool call.

The Exposure Planner, Ask TEPHRA, the recovery agent and the Duty Officer all run a Google ADK
``LlmAgent`` on the lite tier. Each model turn is one HTTP attempt (ADK's Gemini model and the
google-genai client make no retries of their own unless given ``retry_options``, and TEPHRA gives
none), and it is taken from its model's daily budget, in the current lane, before it is sent; a
per-day 429 closes that model until Google's quota day ends; a turn cap stops a model that
loops. A stopped run ends with no answer, and the caller reports AI UNAVAILABLE.
"""

import json
from typing import Any, Final

from tephra.agents.llm import LlmBackend, Tier, daily_quota_spent, estimate_tokens
from tephra.models import ToolCallRecord

__all__ = [
    "BUDGET_EXHAUSTED",
    "DAILY_QUOTA_SPENT",
    "ModelGuard",
    "request_tokens",
    "stop_response",
    "summarise",
    "tool_record",
]

DAILY_QUOTA_SPENT: Final = "GEMINI DAILY QUOTA SPENT (429): MODEL CLOSED FOR THE QUOTA DAY"
BUDGET_EXHAUSTED: Final = "budget_exhausted"
SUMMARY_CHARS: Final = 240
"""Tool results are kept on record (and in the trace) cut to this length."""


class ModelGuard:
    """The daily budget in front of every ADK model turn.

    As ``before_model_callback`` it caps the turns, waits for the turn's slot in the per-minute
    limits (``LlmBackend.pace``) and then takes the turn from the tier's model budget; as
    ``on_model_error`` (the ``on_model_error_callback``) it closes the model for the quota day
    when Gemini answers 429 for a per-day quota, which no retry clears. Either one answers in
    the model's place to stop; with no function call in that answer the run ends.
    """

    def __init__(self, llm: LlmBackend, *, max_turns: int, tier: Tier = "lite") -> None:
        self._llm = llm
        self._max_turns = max_turns
        self._tier: Tier = tier
        self.turns = 0
        self.stop_reason: str | None = None

    async def __call__(self, callback_context: Any, llm_request: Any) -> Any:
        self.turns += 1
        if self.turns > self._max_turns:
            self.stop_reason = f"MODEL TURN LIMIT {self._max_turns} REACHED"
            return stop_response(self.stop_reason)
        # The slot first, the count after it: a turn cancelled while it waits is not counted.
        await self._llm.pace(self._tier, request_tokens(llm_request))
        if await self._llm.reserve(self._tier) is not None:
            self.stop_reason = BUDGET_EXHAUSTED
            return stop_response(self.stop_reason)
        return None

    async def on_model_error(
        self, callback_context: Any, llm_request: Any, error: Exception
    ) -> Any:
        if not daily_quota_spent(error):
            return None
        await self._llm.exhaust(self._tier)
        self.stop_reason = DAILY_QUOTA_SPENT
        return stop_response(self.stop_reason)


def request_tokens(llm_request: Any) -> int:
    """The estimated input tokens of an ADK request: its instruction and every text part of the
    conversation so far (each turn resends the whole history)."""
    texts: list[str] = []
    config = getattr(llm_request, "config", None)
    instruction = getattr(config, "system_instruction", None)
    if isinstance(instruction, str):
        texts.append(instruction)
    for content in getattr(llm_request, "contents", None) or []:
        for part in getattr(content, "parts", None) or []:
            text = getattr(part, "text", None)
            if isinstance(text, str):
                texts.append(text)
            for data in (
                getattr(part, "function_call", None),
                getattr(part, "function_response", None),
            ):
                if data is not None:
                    texts.append(
                        json.dumps(
                            getattr(data, "args", None) or getattr(data, "response", None),
                            default=str,
                        )
                    )
    return estimate_tokens(texts)


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
