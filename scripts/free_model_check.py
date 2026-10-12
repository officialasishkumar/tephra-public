"""Check the free Google models live before any TEPHRA job moves to them.

pytest-free: this is a script a person runs by hand, not a test. pytest never collects it.

It runs the live tests of the free-model brief of 13 Oct 2026 (section 4, tests 0 to 8 and
12) on ``gemma-4-31b-it``, ``gemma-4-26b-a4b-it`` and ``gemini-3.1-flash-lite``. It never
calls ``gemini-3.5-flash-lite`` (the live site's pool), Vertex AI or Application Default
Credentials: every request goes through ``genai.Client(api_key=GEMINI_API_KEY,
vertexai=False)``, and the ADK agents get the same key through ``apply_process_env``.

* Every request (generate, models.get, batch create and poll, each ADK model turn) counts
  against a hard cap of 80 per run, checked before it is sent.
* Requests are paced to the free tier: Gemma 30 a minute and 16,000 input tokens a minute,
  Flash-Lite 15 a minute. The script prints whenever it waits.
* A failed request (429 for a minute limit, 5xx, timeout) is retried once, and the retry is
  its own row. An ADK turn is never retried. A per-day 429 closes that model for the rest of
  the run. Nothing is ever sent to another model in its place.
* The key is read from the environment only. It is never printed or written; error text is
  scrubbed of it before it is kept.

Tests 2 to 4 run TEPHRA's own code on a labelled stub replay of the judged window
(``anak-krakatau-20260905`` at 11:00Z: 27 exposed flights, the 31-item Duty work list). Test 2
runs the Dispatch Drafter, the Notice Reader and the shift handover with a probe backend in
Gemini's place; a repair request is recorded and not sent, because the test scores the first
answer. Tests 3 and 4 run the real ADK Exposure Planner and Duty Officer agents, tools and
prompts with the model swapped by ``--model``. The Duty Officer's delegations answer with what
the stub (NO MODEL) specialists returned on that tick, so test 4 spends calls on the Duty
Officer alone.

Test 7 needs 60 calls in each of two windows (Asia daytime, US daytime), so it is not in the
default set: run ``--only 7`` once in each window. Results go to ``evals/free_models/results/``
as JSON (every call) and a short Markdown summary.

    uv run python scripts/free_model_check.py --dry-run
    GEMINI_API_KEY=... uv run python scripts/free_model_check.py
    GEMINI_API_KEY=... uv run python scripts/free_model_check.py --only 7
    GEMINI_API_KEY=... uv run python scripts/free_model_check.py --only 12 --batch-job batches/...
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import importlib.metadata
import importlib.util
import json
import math
import os
import re
import sys
import tempfile
import time
from collections import deque
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, Final

import httpx
from pydantic import BaseModel

from tephra.agents.llm import LlmCall, LlmPart, daily_quota_spent, prompt_hash, retry_after_s
from tephra.agents.schemas import gemini_schema, parse_json_model
from tephra.config import PROJECT_ROOT, Settings
from tephra.models import DutyItem, PlannedAction, PlannerContext, RunMode
from tephra.util import timeutil

if TYPE_CHECKING:
    from google.genai import types as genai_types

GEMMA_31B: Final = "gemma-4-31b-it"
GEMMA_26B: Final = "gemma-4-26b-a4b-it"
FLASH_LITE: Final = "gemini-3.1-flash-lite"
MODELS: Final = (GEMMA_31B, GEMMA_26B, FLASH_LITE)

HARD_CAP: Final = 80
TEST_IDS: Final = (0, 1, 2, 3, 4, 5, 6, 7, 8, 12)
DEFAULT_TESTS: Final = tuple(test for test in TEST_IDS if test != 7)

CASE_ID: Final = "anak-krakatau-20260905"
CASE_AT: Final = datetime(2026, 9, 5, 11, 0, tzinfo=UTC)
"""The judged replay window (deploy.yml) at its busiest probed minute: 27 exposed flights."""
NOTICE_FIXTURE: Final = (
    PROJECT_ROOT / "tests" / "fixtures" / "notices" / "synthetic_id_ash_seen.txt"
)
PLUME_SCRIPT: Final = PROJECT_ROOT / "scripts" / "plume_eval.py"
OUT_DIR: Final = PROJECT_ROOT / "evals" / "free_models" / "results"

CARD_SAMPLING: Final[dict[str, float | int]] = {"temperature": 1.0, "top_p": 0.95, "top_k": 64}
"""Gemma 4 model card sampling."""
LOW_TEMPERATURE: Final = 0.6
GEMINI_3_SAMPLING: Final[dict[str, float | int]] = {"temperature": 1.0}
T2_RUNS: Final = 5
T7_CALLS: Final = 30
T7_GAP_S: Final = 4.0
OVERSIZE_TOKENS: Final = 20_000
BATCH_POLLS: Final = 3
BATCH_POLL_GAP_S: Final = 60.0
PLANNER_RUN_TIMEOUT_S: Final = 900.0
DUTY_RUN_TIMEOUT_S: Final = 1800.0
"""Longer than the app's 60 s and 900 s: the Gemma token pacing is what test 3 and 4 measure."""

CALL_TIMEOUT_S: Final = 180.0
WINDOW_S: Final = 60.0
CHARS_PER_TOKEN: Final = 3.5
IMAGE_TOKENS_EST: Final = 1120
"""The largest Gemma image soft-token budget; the real count comes back in usage."""
RETRYABLE: Final = frozenset({429, 500, 502, 503, 504})
RETRY_WAIT_S: Final = 10.0
LONG_WAIT_S: Final = 5.0
TEXT_KEEP: Final = 600
GEMMA_TPM: Final = 16_000
THOUGHT_MARK: Final = re.compile(r"<\|?/?(?:channel|think|thought)", re.IGNORECASE)
TERMINAL_JOB_STATES: Final = frozenset(
    {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"}
)

BASIC_SYSTEM: Final = "You answer for an airline dispatch desk. Reply in one plain sentence."
BASIC_PROMPT: Final = "Name the three things a volcanic ash advisory gives for an ash cloud."
SMALL_PROMPT: Final = "Reply with the single word READY."
THINK_PROMPT: Final = (
    "An ash cloud drifts east at 30 knots from a vent. How far east of the vent is its front"
    " after 2 hours? Answer in one line."
)


@dataclass(frozen=True)
class Limit:
    rpm: int
    tpm: int | None


LIMITS: Final = {
    GEMMA_31B: Limit(rpm=30, tpm=GEMMA_TPM),
    GEMMA_26B: Limit(rpm=30, tpm=GEMMA_TPM),
    FLASH_LITE: Limit(rpm=15, tpm=None),
}


def is_gemma(model: str) -> bool:
    return model.startswith("gemma-")


def sampling_for(model: str) -> dict[str, float | int]:
    return dict(CARD_SAMPLING if is_gemma(model) else GEMINI_3_SAMPLING)


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def estimate_tokens(chars: int) -> int:
    return math.ceil(chars / CHARS_PER_TOKEN)


# --- what is recorded ---------------------------------------------------------------------


@dataclass
class Row:
    """One request (or one request not sent, with the reason)."""

    test: int
    label: str
    model: str
    attempt: int = 1
    sent: bool = True
    started_utc: str | None = None
    latency_ms: int | None = None
    http_status: int | None = None
    error: str | None = None
    model_version: str | None = None
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    thoughts_tokens: int | None = None
    total_tokens: int | None = None
    finish_reason: str | None = None
    passed: bool | None = None
    why: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class Verdict:
    """A test's result by the brief's pass rule. ``result`` is PASS, FAIL, INFO or NOT RUN."""

    test: int
    name: str
    model: str
    result: str
    why: str
    notes: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)


class CapReached(RuntimeError):
    """The run's hard cap of requests is used up; nothing more is sent."""


# --- pacing and the counted client ----------------------------------------------------------


class Pacer:
    """One model's sends: at most ``rpm`` in any 60 s and, with ``tpm``, at most that many
    estimated input tokens. A request larger than ``tpm`` waits for an empty window."""

    def __init__(self, limit: Limit) -> None:
        self._limit = limit
        self._sent: deque[list[float]] = deque()
        self._last = -math.inf

    async def wait(self, est_tokens: int, min_gap_s: float) -> list[float]:
        while True:
            now = time.monotonic()
            while self._sent and now - self._sent[0][0] >= WINDOW_S:
                self._sent.popleft()
            used = sum(tokens for _, tokens in self._sent)
            fits = len(self._sent) < self._limit.rpm and (
                self._limit.tpm is None or not self._sent or used + est_tokens <= self._limit.tpm
            )
            gap = self._last + min_gap_s - now
            if fits and gap <= 0:
                entry = [now, float(est_tokens)]
                self._sent.append(entry)
                self._last = now
                return entry
            waits = [gap] if gap > 0 else []
            if not fits:
                waits.append(WINDOW_S - (now - self._sent[0][0]))
            await asyncio.sleep(max(0.05, min(waits)))


class Probe:
    """The Gemini Developer API client of this run: counts, paces and records every request."""

    def __init__(self, key: str, cap: int) -> None:
        self._key = key
        self.cap = cap
        self.sent = 0
        self.rows: list[Row] = []
        self.closed: dict[str, str] = {}
        self._pacers = {model: Pacer(limit) for model, limit in LIMITS.items()}
        self._client: Any = None

    def client(self) -> Any:
        if self._client is None:
            from google import genai
            from google.genai import types

            # vertexai=False pins the Gemini Developer API (AI Studio key); never Vertex/ADC.
            self._client = genai.Client(
                api_key=self._key,
                vertexai=False,
                http_options=types.HttpOptions(timeout=int(CALL_TIMEOUT_S * 1000)),
            )
        return self._client

    def scrub(self, text: str) -> str:
        return text.replace(self._key, "[KEY]") if self._key else text

    def take(self) -> None:
        if self.sent >= self.cap:
            raise CapReached(f"hard cap of {self.cap} requests reached")
        self.sent += 1

    async def pace(self, model: str, est_tokens: int, min_gap_s: float = 0.0) -> list[float]:
        started = time.monotonic()
        entry = await self._pacers[model].wait(est_tokens, min_gap_s)
        waited = time.monotonic() - started
        if waited >= LONG_WAIT_S:
            print(f"    waited {waited:.0f} s for {model}'s per-minute limits")
        return entry

    def fail(self, row: Row, exc: BaseException) -> None:
        """Fill ``row`` from a failed request; a per-day 429 closes the model for the run."""
        code = getattr(exc, "code", None)
        row.http_status = code if isinstance(code, int) else None
        status = getattr(exc, "status", None) or ""
        message = getattr(exc, "message", None) or str(exc)
        if isinstance(exc, TimeoutError):
            message = f"no answer within {CALL_TIMEOUT_S:.0f} s"
        row.error = self.scrub(f"{type(exc).__name__} {status}: {message}".strip())[:800]
        row.passed = False
        row.why = row.error
        if daily_quota_spent(exc):
            self.closed[row.model] = f"per-day 429 on {row.model} earlier in this run"

    async def send(
        self,
        test: int,
        label: str,
        model: str,
        request: Callable[[], Awaitable[Any]],
        *,
        est_tokens: int = 0,
        min_gap_s: float = 0.0,
        paced: bool = True,
    ) -> tuple[Any | None, Row, list[float] | None]:
        """One request with at most one recorded retry. Returns the result (None on failure),
        the last attempt's row and its pacing entry."""
        entry: list[float] | None = None
        for attempt in (1, 2):
            row = Row(test=test, label=label, model=model, attempt=attempt)
            self.rows.append(row)
            if model in self.closed:
                row.sent, row.passed = False, False
                row.why = row.error = f"not sent: {self.closed[model]}"
                return None, row, None
            self.take()
            entry = await self.pace(model, est_tokens, min_gap_s) if paced else None
            row.started_utc = utc_now()
            started = time.monotonic()
            try:
                result = await asyncio.wait_for(request(), timeout=CALL_TIMEOUT_S + 10)
            except Exception as exc:  # recorded as the result of this attempt
                row.latency_ms = round((time.monotonic() - started) * 1000)
                self.fail(row, exc)
                if attempt == 2 or not _retryable(exc):
                    return None, row, entry
                delay = retry_after_s(exc) or RETRY_WAIT_S
                row.detail["retried"] = f"one retry after {delay:.0f} s"
                print(f"    {model} {label}: {row.error[:120]}; one retry in {delay:.0f} s")
                await asyncio.sleep(delay)
                continue
            row.latency_ms = round((time.monotonic() - started) * 1000)
            row.http_status = 200
            return result, row, entry
        raise AssertionError("unreachable: the loop returns on its second attempt")

    async def generate(
        self,
        test: int,
        label: str,
        model: str,
        contents: Any,
        config: genai_types.GenerateContentConfig,
        *,
        est_tokens: int,
        min_gap_s: float = 0.0,
    ) -> tuple[Any | None, Row]:
        async def request() -> Any:
            return await self.client().aio.models.generate_content(
                model=model, contents=contents, config=config
            )

        response, row, entry = await self.send(
            test, label, model, request, est_tokens=est_tokens, min_gap_s=min_gap_s
        )
        if response is not None:
            record_response(row, response)
            if entry is not None and row.prompt_tokens is not None:
                entry[1] = float(row.prompt_tokens)
        return response, row


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TransportError, TimeoutError)):
        return True
    return getattr(exc, "code", None) in RETRYABLE and not daily_quota_spent(exc)


def _int(obj: Any, name: str) -> int | None:
    value = getattr(obj, name, None) if obj is not None else None
    return value if isinstance(value, int) else None


def response_parts(response: Any) -> list[Any]:
    """Parts of a GenerateContentResponse's first candidate, or of an ADK LlmResponse."""
    content = getattr(response, "content", None)
    if content is None:
        candidates = getattr(response, "candidates", None) or []
        content = getattr(candidates[0], "content", None) if candidates else None
    return list(getattr(content, "parts", None) or [])


def thought_counts(parts: Sequence[Any]) -> dict[str, int]:
    return {
        "thought_parts": sum(1 for part in parts if getattr(part, "thought", None)),
        "thought_signatures": sum(1 for part in parts if getattr(part, "thought_signature", None)),
    }


def record_response(row: Row, response: Any) -> None:
    usage = getattr(response, "usage_metadata", None)
    row.prompt_tokens = _int(usage, "prompt_token_count")
    row.output_tokens = _int(usage, "candidates_token_count")
    row.thoughts_tokens = _int(usage, "thoughts_token_count")
    row.total_tokens = _int(usage, "total_token_count")
    row.model_version = getattr(response, "model_version", None)
    reason = getattr(response, "finish_reason", None)
    if reason is None:
        candidates = getattr(response, "candidates", None) or []
        reason = getattr(candidates[0], "finish_reason", None) if candidates else None
    row.finish_reason = getattr(reason, "value", None) or (str(reason) if reason else None)
    row.detail.update(thought_counts(response_parts(response)))


def visible_text(parts: Sequence[Any]) -> str:
    return "".join(part.text for part in parts if getattr(part, "text", None) and not part.thought)


def config(
    model: str,
    *,
    system: str | None = None,
    thinking: str | None = "MINIMAL",
    sampling: dict[str, float | int] | None = None,
    schema: dict[str, Any] | None = None,
) -> genai_types.GenerateContentConfig:
    """``thinking`` is a ThinkingLevel name; None leaves it to the model, as TEPHRA's lite
    calls do today."""
    from google.genai import types

    return types.GenerateContentConfig(
        system_instruction=system,
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel[thinking])
        if thinking
        else None,
        response_mime_type="application/json" if schema is not None else None,
        response_json_schema=schema,
        **(sampling if sampling is not None else sampling_for(model)),
    )


def all_required(node: Any) -> Any:
    """The schema with every property required at every level (the brief's test 2 setting)."""
    if isinstance(node, list):
        return [all_required(item) for item in node]
    if not isinstance(node, dict):
        return node
    out = {key: all_required(value) for key, value in node.items()}
    if isinstance(out.get("properties"), dict):
        out["required"] = list(out["properties"])
    return out


# --- the labelled stub replay that tests 2 to 4 read ----------------------------------------


@dataclass
class World:
    settings: Settings
    runtime: Any
    at: datetime
    worklist: list[DutyItem]
    digest: str
    delegations: dict[tuple[str, str], Any]
    planner_ctx: PlannerContext
    stub_plan: PlannedAction

    @property
    def volcano_id(self) -> str:
        return self.planner_ctx.flight.volcano_id


class RecordingExecutor:
    """Wraps the stub tick's real executor and keeps what each delegation returned."""

    def __init__(self, inner: Any, recorded: dict[tuple[str, str], Any]) -> None:
        self._inner = inner
        self._recorded = recorded

    async def assess(self, volcano_id: str) -> tuple[dict[str, Any], list[DutyItem]]:
        result = await self._inner.assess(volcano_id)
        self._recorded[("assess", volcano_id)] = copy.deepcopy(result)
        return result

    async def plan(self, flight_id: str) -> dict[str, Any]:
        result = await self._inner.plan(flight_id)
        self._recorded[("plan", flight_id)] = copy.deepcopy(result)
        return result

    async def recover(self) -> dict[str, Any]:
        result = await self._inner.recover()
        self._recorded[("recover", "network")] = copy.deepcopy(result)
        return result

    async def draft_sra(self, region: str) -> dict[str, Any]:
        result = await self._inner.draft_sra(region)
        self._recorded[("sra", region)] = copy.deepcopy(result)
        return result


class RecordedExecutor:
    """The Duty Officer's specialists for test 4: each answers with what the stub (NO MODEL)
    specialist returned on the captured tick, with no model call."""

    def __init__(self, recorded: dict[tuple[str, str], Any]) -> None:
        self._recorded = recorded

    def _get(self, kind: str, subject: str) -> Any:
        found = self._recorded.get((kind, subject))
        missing = {"error": f"NO RECORDED {kind.upper()} RESULT FOR {subject}"}
        return copy.deepcopy(found) if found is not None else missing

    async def assess(self, volcano_id: str) -> tuple[dict[str, Any], list[DutyItem]]:
        found = self._get("assess", volcano_id)
        return found if isinstance(found, tuple) else (found, [])

    async def plan(self, flight_id: str) -> dict[str, Any]:
        return self._get("plan", flight_id)

    async def recover(self) -> dict[str, Any]:
        return self._get("recover", "network")

    async def draft_sra(self, region: str) -> dict[str, Any]:
        return self._get("sra", region)


async def build_world(tmp: Path) -> World:
    """One stub tick (``TEPHRA_LLM=stub``, no network, throwaway store) of the judged window,
    with the Duty Officer's real work list, digest and delegation results captured."""
    import tephra.duty as duty_module
    from tephra.agents.exposure_planner import build_planner_context, plan_flight
    from tephra.agents.llm import StubBackend
    from tephra.pipeline import create_runtime

    manifest = PROJECT_ROOT / "data" / "replay" / CASE_ID / "manifest.json"
    settings = Settings(
        _env_file=None,
        llm="stub",
        mode=RunMode.REPLAY,
        replay_case=CASE_ID,
        data_dir=PROJECT_ROOT / "data",
        store="sqlite",
        sqlite_path=tmp / "world.sqlite3",
        cache_dir=tmp / "cache",
        region=json.loads(manifest.read_text(encoding="utf-8"))["region"],
    )
    captured: list[tuple[list[DutyItem], str]] = []
    delegations: dict[tuple[str, str], Any] = {}
    original = duty_module.run_duty_officer

    async def capture(worklist: Sequence[DutyItem], executor: Any, llm: Any, **kwargs: Any) -> Any:
        captured.append((list(worklist), kwargs["digest"]))
        return await original(worklist, RecordingExecutor(executor, delegations), llm, **kwargs)

    # The AI worker calls the Duty Officer through tephra.duty; capture what it is handed.
    duty_module.run_duty_officer = capture
    try:
        runtime = await create_runtime(settings)
        with timeutil.use_clock(timeutil.FixedClock(CASE_AT)):
            await runtime.tick(reason="free-model-check")
            # the tick only queues AI work; the AI worker runs it, the Duty Officer included
            await runtime.worker.drain()
    finally:
        duty_module.run_duty_officer = original
    if not captured:
        await runtime.aclose()
        raise SystemExit(f"the stub tick of {CASE_ID} at {CASE_AT:%H:%MZ} offered no Duty work")
    worklist, digest = max(captured, key=lambda found: len(found[0]))
    first = next((item for item in worklist if item.kind.value == "PLAN"), None)
    flight = runtime.exposed.get(first.subject) if first is not None else None
    if flight is None:
        await runtime.aclose()
        raise SystemExit(f"the stub tick of {CASE_ID} at {CASE_AT:%H:%MZ} has no flight to plan")
    situation = runtime.situations[flight.volcano_id]
    ctx = build_planner_context(
        flight,
        runtime.cones[flight.volcano_id],
        volcano_name=situation.volcano.name,
        airports=runtime.airports,
        tafs=runtime.live.tafs,
        at=CASE_AT,
        policy=runtime.policy,
        routes=runtime.routes,
        situation=situation,
    )
    with timeutil.use_clock(timeutil.FixedClock(CASE_AT)):
        stub_plan = await plan_flight(ctx, StubBackend(), settings=settings)
    return World(settings, runtime, CASE_AT, worklist, digest, delegations, ctx, stub_plan)


# --- the run --------------------------------------------------------------------------------


class Run:
    def __init__(self, args: argparse.Namespace, probe: Probe | None) -> None:
        self.args = args
        self._probe = probe
        self._tmp = tempfile.TemporaryDirectory(prefix="tephra-model-check-")
        self._world: World | None = None

    @property
    def probe(self) -> Probe:
        if self._probe is None:
            raise RuntimeError("a dry run sends nothing")
        return self._probe

    @property
    def model(self) -> str:
        return str(self.args.model)

    async def world(self) -> World:
        if self._world is None:
            print(f"    building the stub replay world ({CASE_ID} at {CASE_AT:%H:%MZ}, no model)")
            self._world = await build_world(Path(self._tmp.name))
        return self._world

    async def close(self) -> None:
        if self._world is not None:
            await self._world.runtime.aclose()
        self._tmp.cleanup()


# --- test 0: limits -------------------------------------------------------------------------


async def check_limits(run: Run) -> list[Verdict]:
    verdicts: list[Verdict] = []
    for model in MODELS:

        async def request(model: str = model) -> Any:
            return await run.probe.client().aio.models.get(model=model)

        info, row, _ = await run.probe.send(0, "models.get", model, request, paced=False)
        if info is None:
            verdicts.append(Verdict(0, "Limits", model, "FAIL", row.error or "no answer"))
            continue
        fields = (
            "version",
            "input_token_limit",
            "output_token_limit",
            "supported_actions",
            "thinking",
            "temperature",
            "max_temperature",
            "top_p",
            "top_k",
        )
        row.detail.update({name: getattr(info, name, None) for name in fields})
        row.passed, row.why = True, "limits recorded"
        verdicts.append(
            Verdict(
                0,
                "Limits",
                model,
                "INFO",
                f"input {info.input_token_limit}, output {info.output_token_limit} tokens",
                detail=dict(row.detail),
            )
        )
    return verdicts


# --- test 1: basics -------------------------------------------------------------------------


async def check_basics(run: Run) -> list[Verdict]:
    verdicts: list[Verdict] = []
    est = estimate_tokens(len(BASIC_SYSTEM) + len(BASIC_PROMPT))
    for model in MODELS:
        cfg = config(model, system=BASIC_SYSTEM)
        response, row = await run.probe.generate(
            1, "basics", model, BASIC_PROMPT, cfg, est_tokens=est
        )
        if response is None:
            verdicts.append(Verdict(1, "Basics", model, "FAIL", row.error or "no answer"))
            continue
        text = response.text or ""
        problems: list[str] = []
        if not text.strip():
            problems.append("no text returned")
        if row.thoughts_tokens:
            problems.append(f"thoughts_token_count {row.thoughts_tokens} at minimal")
        if text != visible_text(response_parts(response)):
            problems.append("response.text differs from the non-thought parts")
        if THOUGHT_MARK.search(text):
            problems.append("thinking markup inside the text")
        row.passed = not problems
        row.why = "; ".join(problems) or "200, no thoughts, text returned"
        row.detail["text"] = text[:TEXT_KEEP]
        verdicts.append(Verdict(1, "Basics", model, "PASS" if row.passed else "FAIL", row.why))
    return verdicts


# --- test 2: structured output through TEPHRA's own jobs ------------------------------------


class ProbeBackend:
    """``LlmBackend`` for one run of one job: its first request goes out through the probe
    with the test's sampling and an all-required schema; a repair request is recorded with the
    problems code found, and not sent."""

    name: Final = "gemini"

    def __init__(self, probe: Probe, model: str, sampling: dict[str, float | int], label: str):
        self._probe = probe
        self._model = model
        self._sampling = sampling
        self._label = label
        self.requests = 0
        self.row: Row | None = None
        self.repair_problems: str | None = None

    def model_id(self, tier: str) -> str:
        return self._model

    async def reserve(self, tier: str) -> str | None:
        """The probe counts each request against the run's hard cap itself."""
        return None

    async def exhaust(self, tier: str) -> None:
        """The probe closes a model on a per-day 429 itself."""

    async def pace(self, tier: str, tokens: int = 0) -> None:
        """The probe paces each request itself."""

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
        from tephra.agents.llm import _contents

        call = LlmCall(
            backend="gemini", model_id=self._model, prompt_hash=prompt_hash(system, parts)
        )
        self.requests += 1
        if self.requests > 1:
            self.repair_problems = (parts[-1].text or "")[:TEXT_KEEP]
            return None, call.model_copy(
                update={"error": "REPAIR NOT SENT: test 2 scores the first answer"}
            )
        cfg = config(
            self._model,
            system=system,
            thinking="MINIMAL" if is_gemma(self._model) else None,
            sampling=self._sampling,
            schema=all_required(gemini_schema(schema)),
        )
        chars = len(system) + sum(len(part.text or "") for part in parts)
        response, row = await self._probe.generate(
            2, self._label, self._model, _contents(parts), cfg, est_tokens=estimate_tokens(chars)
        )
        self.row = row
        if response is None:
            return None, call.model_copy(update={"error": row.error})
        text = response.text or ""
        row.detail["text"] = text[:TEXT_KEEP]
        call = call.model_copy(
            update={
                "raw_text": text,
                "input_tokens": row.prompt_tokens,
                "latency_ms": row.latency_ms,
            }
        )
        try:
            value = parse_json_model(text, schema)
        except ValueError as exc:
            row.detail["parse_error"] = str(exc)[:300]
            return None, call.model_copy(update={"error": f"invalid_output: {exc}"})
        return value, call


async def job_draft(world: World, backend: ProbeBackend) -> tuple[bool, str]:
    from tephra.agents.dispatch_drafter import draft_advisory
    from tephra.models import AiFailure

    runtime, volcano_id = world.runtime, world.volcano_id
    with timeutil.use_clock(timeutil.FixedClock(world.at)):
        result = await draft_advisory(
            situation=runtime.situations[volcano_id],
            assessment=runtime.assessments[volcano_id],
            cone=runtime.cones[volcano_id],
            ctx=world.planner_ctx,
            plan=world.stub_plan,
            llm=backend,
            settings=world.settings,
            policy=runtime.policy,
        )
    if isinstance(result, AiFailure):
        return False, result.reason
    return True, "advisory drafted"


async def job_notice(world: World, backend: ProbeBackend) -> tuple[bool, str]:
    from tephra.agents.notice_reader import read_notice

    text = NOTICE_FIXTURE.read_text(encoding="utf-8")
    with timeutil.use_clock(timeutil.SystemClock()):
        reading = await read_notice(text, backend, world.runtime.catalogue)
    reason = f"reading {reading.status}" + (f" ({reading.reason})" if reading.reason else "")
    return reading.status != "ai_unavailable", reason


async def job_handover(world: World, backend: ProbeBackend) -> tuple[bool, str]:
    from tephra.comms.handover import AiUnavailable, draft_handover

    runtime = world.runtime
    previous, runtime.llm = runtime.llm, backend
    try:
        with timeutil.use_clock(timeutil.FixedClock(world.at)):
            await draft_handover(runtime, world.at - timedelta(hours=8), "outgoing", "incoming")
    except AiUnavailable as exc:
        return False, str(exc)
    finally:
        runtime.llm = previous
    return True, "handover brief drafted"


JOBS: Final[dict[str, Callable[[World, ProbeBackend], Awaitable[tuple[bool, str]]]]] = {
    "DraftText (Dispatch Drafter)": job_draft,
    "NoticeExtraction (Notice Reader)": job_notice,
    "Narrative (shift handover)": job_handover,
}


async def check_schema(run: Run) -> list[Verdict]:
    from google.genai import types

    world = await run.world()
    verdicts: list[Verdict] = []
    settings = [
        ("1.0/0.95/64", CARD_SAMPLING, T2_RUNS),
        ("0.6", {"temperature": LOW_TEMPERATURE}, 1),
    ]
    if not is_gemma(run.model):
        settings = [("1.0", GEMINI_3_SAMPLING, T2_RUNS)]
    for job_name, job in JOBS.items():
        for sampling_name, sampling, runs in settings:
            clean = 0
            reasons: list[str] = []
            for n in range(1, runs + 1):
                label = f"{job_name} at {sampling_name}, run {n}"
                backend = ProbeBackend(run.probe, run.model, dict(sampling), label)
                ok, reason = await job(world, backend)
                row = backend.row
                passed = (
                    row is not None
                    and row.http_status == 200
                    and ok
                    and not backend.repair_problems
                )
                why = reason
                if backend.repair_problems is not None:
                    why = f"repair asked: {backend.repair_problems}"
                if row is not None and row.http_status == 200:
                    row.passed, row.why = passed, why
                clean += passed
                if not passed:
                    reasons.append(row.why if row is not None else why)
            rule = clean == runs if runs == T2_RUNS else None
            result = "INFO" if rule is None else "PASS" if rule else "FAIL"
            verdicts.append(
                Verdict(
                    2,
                    f"Schema: {job_name}, sampling {sampling_name}",
                    run.model,
                    result,
                    f"{clean}/{runs} parsed and passed the code checks with no repair",
                    notes=[" ".join(reason.split())[:200] for reason in reasons[:3]],
                )
            )
    schema_rows = [row for row in run.probe.rows if row.test == 2 and row.sent]
    if schema_rows and all(row.http_status == 500 for row in schema_rows):
        verdicts.append(
            Verdict(2, "Schema: free tier", run.model, "FAIL", "every schema call returned 500")
        )
    if "response_format" not in types.GenerateContentConfig.model_fields:
        version = importlib.metadata.version("google-genai")
        verdicts.append(
            Verdict(
                2,
                "Schema: response_format shape",
                run.model,
                "NOT RUN",
                f"the pinned google-genai {version} has no response_format field",
            )
        )
    return verdicts


# --- tests 3 and 4: the real ADK agents -----------------------------------------------------


class AgentMeter:
    """ADK model callbacks for one agent run: each turn is counted against the hard cap and
    the turn cap, paced, and recorded with its usage and the thought parts it carried."""

    def __init__(self, probe: Probe, test: int, model: str, max_turns: int) -> None:
        self._probe = probe
        self._test = test
        self._model = model
        self._max_turns = max_turns
        self.turns = 0
        self.stop_reason: str | None = None
        self.rows: list[Row] = []
        self._pending: tuple[Row, float, list[float]] | None = None
        self._returned = {"thought_parts": 0, "thought_signatures": 0}
        self._last_prompt_tokens = 0

    async def before(self, callback_context: Any, llm_request: Any) -> Any:
        from tephra.agents.adk_runtime import stop_response

        self.turns += 1
        if self.turns > self._max_turns:
            self.stop_reason = f"MODEL TURN LIMIT {self._max_turns} REACHED"
        elif self._model in self._probe.closed:
            self.stop_reason = f"NOT SENT: {self._probe.closed[self._model]}"
        else:
            try:
                self._probe.take()
            except CapReached as exc:
                self.stop_reason = str(exc).upper()
        if self.stop_reason is not None:
            return stop_response(self.stop_reason)
        est = max(_request_tokens(llm_request), self._last_prompt_tokens)
        entry = await self._probe.pace(self._model, est)
        history = [
            part
            for content in llm_request.contents or []
            if content.role == "model"
            for part in content.parts or []
        ]
        row = Row(test=self._test, label=f"turn {self.turns}", model=self._model)
        row.started_utc = utc_now()
        row.detail = {
            "estimated_input_tokens": est,
            "history": thought_counts(history),
            "returned_before": dict(self._returned),
        }
        self._pending = (row, time.monotonic(), entry)
        return None

    def after(self, callback_context: Any, llm_response: Any) -> Any:
        if getattr(llm_response, "partial", False) or self._pending is None:
            return None
        row, started, entry = self._pending
        self._pending = None
        row.latency_ms = round((time.monotonic() - started) * 1000)
        record_response(row, llm_response)
        if llm_response.error_code is not None:
            row.error = self._probe.scrub(
                f"{llm_response.error_code}: {llm_response.error_message}"
            )
            row.passed, row.why = False, row.error
        else:
            row.http_status, row.passed = 200, True
        parts = response_parts(llm_response)
        row.detail["function_calls"] = [p.function_call.name for p in parts if p.function_call]
        row.detail["text"] = visible_text(parts)[:TEXT_KEEP]
        for key in self._returned:
            self._returned[key] += row.detail.get(key, 0)
        if row.prompt_tokens is not None:
            entry[1] = float(row.prompt_tokens)
            self._last_prompt_tokens = row.prompt_tokens
        self._keep(row)
        return None

    def on_error(self, callback_context: Any, llm_request: Any, error: Exception) -> Any:
        """Recorded; the error ends the run (an agent turn is never retried here)."""
        if self._pending is not None:
            row, started, _ = self._pending
            self._pending = None
            row.latency_ms = round((time.monotonic() - started) * 1000)
            self._probe.fail(row, error)
            self._keep(row)
        return None

    def unanswered(self) -> None:
        """A turn still in flight when the run's time ran out."""
        if self._pending is not None:
            row, started, _ = self._pending
            self._pending = None
            row.latency_ms = round((time.monotonic() - started) * 1000)
            row.passed, row.why = False, "no answer before the run's time limit"
            row.error = row.why
            self._keep(row)

    def _keep(self, row: Row) -> None:
        self.rows.append(row)
        self._probe.rows.append(row)

    def thought_note(self) -> str:
        """Whether thought parts and signatures the model returned were sent back to it."""
        returned = self._returned
        later = [row for row in self.rows if row.label != "turn 1" and row.detail.get("history")]
        if not later:
            return f"one model turn only: nothing to carry ({returned})"
        kept = all(
            row.detail["history"][key] >= row.detail["returned_before"][key]
            for row in later
            for key in returned
        )
        return (
            f"model returned {returned['thought_parts']} thought part(s) and "
            f"{returned['thought_signatures']} signature(s); "
            + ("all present in later turns' history" if kept else "SOME DROPPED from later turns")
        )

    def token_notes(self) -> list[str]:
        prompts = [row.prompt_tokens for row in self.rows if row.prompt_tokens is not None]
        over = [row.label for row in self.rows if (row.prompt_tokens or 0) > GEMMA_TPM]
        failed_over = [
            row.label
            for row in self.rows
            if row.error and row.detail.get("estimated_input_tokens", 0) > GEMMA_TPM
        ]
        notes = [
            f"prompt tokens per turn: {prompts}",
            f"input tokens in total: {sum(prompts)}; largest turn: {max(prompts, default=0)}",
        ]
        if is_gemma(self._model):
            notes.append(
                f"turns over {GEMMA_TPM} input tokens: {over or 'none'};"
                f" failed turns estimated over it: {failed_over or 'none'}"
            )
        return notes


def _request_tokens(llm_request: Any) -> int:
    """Estimated input tokens of an ADK request: system text, tool declarations, history."""
    chars = 0
    cfg = llm_request.config
    if cfg is not None and cfg.system_instruction:
        chars += len(str(cfg.system_instruction))
    for tool in (cfg.tools or []) if cfg is not None else []:
        dump = (
            tool.model_dump(mode="json", exclude_none=True) if isinstance(tool, BaseModel) else {}
        )
        chars += len(json.dumps(dump, default=str))
    for content in llm_request.contents or []:
        for part in content.parts or []:
            chars += len(part.text or "")
            if part.function_call:
                chars += len(json.dumps(part.function_call.args or {}, default=str))
            if part.function_response:
                chars += len(json.dumps(part.function_response.response or {}, default=str))
    return estimate_tokens(chars)


def _check_developer_api(agent: Any) -> str:
    """The ADK model class, after checking its client is the Developer API, not Vertex AI."""
    llm = agent.canonical_model
    if getattr(getattr(llm, "api_client", None), "vertexai", True):
        raise SystemExit("ADK's client is not the Gemini Developer API; stopping before any call")
    return type(llm).__name__


async def _agent_turn(
    runner: Any, user_id: str, session_id: str, message: str, deadline: float, log: list[str]
) -> str:
    from google.genai import types

    from tephra.agents.adk_runtime import summarise

    content = types.Content(role="user", parts=[types.Part(text=message)])
    last_text = ""
    async with asyncio.timeout_at(deadline):
        async for event in runner.run_async(
            user_id=user_id, session_id=session_id, new_message=content
        ):
            for call in event.get_function_calls():
                log.append(f"call {call.name} {summarise(dict(call.args or {}), 160)}")
            for response in event.get_function_responses():
                log.append(f"result {response.name} {summarise(response.response, 160)}")
            parts = event.content.parts if event.content is not None else None
            text = visible_text(parts or []).strip()
            if text:
                last_text = text
    return last_text


async def check_planner(run: Run) -> list[Verdict]:
    from google.adk.runners import InMemoryRunner

    from tephra.agents import exposure_planner as planner
    from tephra.agents.adk_app import build_planner_agent

    world = await run.world()
    ctx = world.planner_ctx
    meter = AgentMeter(run.probe, 3, run.model, planner.MAX_MODEL_TURNS)
    agent = build_planner_agent(
        run.model,
        before_model_callback=meter.before,
        after_model_callback=meter.after,
        on_model_error_callback=meter.on_error,
    )
    adk_class = _check_developer_api(agent)
    runner = InMemoryRunner(agent=agent, app_name=planner.ADK_APP_NAME)
    log: list[str] = []
    decision, problems, error, repaired = None, [], None, False
    started = time.monotonic()
    deadline = asyncio.get_running_loop().time() + PLANNER_RUN_TIMEOUT_S
    try:
        session = await runner.session_service.create_session(
            app_name=planner.ADK_APP_NAME,
            user_id=planner.ADK_USER_ID,
            state={planner.CONTEXT_STATE_KEY: ctx.model_dump(mode="json")},
        )
        user, sid = planner.ADK_USER_ID, session.id
        text = await _agent_turn(runner, user, sid, planner._task_text(ctx), deadline, log)
        decision, problems = await planner._read_decision(runner, sid, text, ctx)
        if problems and meter.stop_reason is None:
            repaired = True
            repair = planner._repair_text(problems)
            text = await _agent_turn(runner, user, sid, repair, deadline, log)
            decision, problems = await planner._read_decision(runner, sid, text, ctx)
    except Exception as exc:  # recorded: the run ends with no plan
        error = run.probe.scrub(f"{type(exc).__name__}: {exc}")[:300]
    finally:
        meter.unanswered()
        await runner.close()
    minutes = (time.monotonic() - started) / 60
    passed = decision is not None and not problems and error is None and meter.stop_reason is None
    why = (
        f"{decision.action.value} accepted{' after one repair' if repaired else ''}"
        f" in {meter.turns} turn(s)"
        if passed and decision is not None
        else "; ".join([*(problems[:3]), *filter(None, [error, meter.stop_reason])]) or "no plan"
    )
    notes = [
        f"flight {ctx.flight.proxy_flight} ({ctx.volcano_name}), allowed:"
        f" {', '.join(a.value for a in ctx.allowed_actions)}; ADK model class {adk_class}",
        f"{minutes:.1f} min for the run (the app's planner turn timeout is"
        f" {world.settings.llm_timeout_s:.0f} s); temperature as the app sets it:"
        f" {agent.generate_content_config.temperature}",
        *meter.token_notes(),
        meter.thought_note(),
        f"tool calls: {[line for line in log if line.startswith('call')]}"[:600],
    ]
    return [
        Verdict(
            3,
            "Planner tools (ADK, 7 tools)",
            run.model,
            "PASS" if passed else "FAIL",
            why,
            notes=notes,
            detail={
                "tool_log": log,
                "decision": decision.model_dump(mode="json") if decision else None,
            },
        )
    ]


async def check_duty(run: Run) -> list[Verdict]:
    from google.adk.runners import InMemoryRunner

    from tephra.agents import duty_officer as duty

    world = await run.world()
    toolkit = duty.DutyToolkit.of(world.worklist, RecordedExecutor(world.delegations), trace=None)
    toolkit.evidence.append(world.digest)
    meter = AgentMeter(run.probe, 4, run.model, duty.MAX_MODEL_TURNS)
    agent = duty.build_duty_agent(
        run.model,
        toolkit,
        before_model_callback=meter.before,
        on_model_error_callback=meter.on_error,
    )
    agent.after_model_callback = meter.after  # build_duty_agent takes no after-model callback
    adk_class = _check_developer_api(agent)
    runner = InMemoryRunner(agent=agent, app_name=duty.ADK_APP_NAME)
    log: list[str] = []
    error, repaired = None, False
    started = time.monotonic()
    deadline = asyncio.get_running_loop().time() + DUTY_RUN_TIMEOUT_S
    try:
        session = await runner.session_service.create_session(
            app_name=duty.ADK_APP_NAME, user_id=duty.ADK_USER_ID
        )
        user, sid = duty.ADK_USER_ID, session.id
        await _agent_turn(runner, user, sid, duty._task_text(world.digest, toolkit), deadline, log)
        if (
            toolkit.brief is None or toolkit.undispatched_mandatory()
        ) and meter.stop_reason is None:
            repaired = True
            await _agent_turn(runner, user, sid, duty._repair_text(toolkit), deadline, log)
    except Exception as exc:  # recorded: the run ends where it stopped
        error = run.probe.scrub(f"{type(exc).__name__}: {exc}")[:300]
    finally:
        meter.unanswered()
        await runner.close()
    minutes = (time.monotonic() - started) / 60
    rejected = [
        line for line in log if line.startswith("result submit_brief") and "rejected" in line
    ]
    undone = toolkit.undispatched_mandatory()
    passed = toolkit.brief is not None and not undone and not rejected and error is None
    problems = [
        *(["no brief accepted"] if toolkit.brief is None else []),
        *([f"{len(undone)} mandatory item(s) not dispatched"] if undone else []),
        *([f"{len(rejected)} brief(s) rejected by the code checks"] if rejected else []),
        *filter(None, [error, meter.stop_reason]),
    ]
    why = (
        f"brief accepted{' after one repair' if repaired else ''}, {len(toolkit.dispatches)}"
        f" delegation(s), {len(toolkit.deferred)} deferred, in {meter.turns} turn(s)"
        if passed
        else "; ".join(problems)
    )
    kinds = sorted({item.kind.value for item in world.worklist})
    notes = [
        f"work list {len(world.worklist)} item(s) ({', '.join(kinds)}),"
        f" {sum(item.mandatory for item in world.worklist)} mandatory; ADK model class {adk_class}",
        f"{minutes:.1f} min for the run (the app allows {world.settings.duty_run_timeout_s:.0f} s);"
        " delegations answered from the recorded stub tick, no model behind them",
        *meter.token_notes(),
        meter.thought_note(),
        *([f"brief: {toolkit.brief.summary[:300]}"] if toolkit.brief is not None else []),
        *([f"last brief problems: {toolkit.brief_problems[:3]}"] if toolkit.brief_problems else []),
    ]
    return [
        Verdict(
            4,
            "Duty Officer (ADK, 6 tools)",
            run.model,
            "PASS" if passed else "FAIL",
            why,
            notes=notes,
            detail={"tool_log": log},
        )
    ]


# --- test 5: oversized prompt ---------------------------------------------------------------


def filler_text(tokens: int) -> str:
    line = "LINE {:05d}: archived ash advisory entry for token counting; no instruction here.\n"
    count = math.ceil(tokens * CHARS_PER_TOKEN / len(line.format(0)))
    return "".join(line.format(n) for n in range(1, count + 1))


async def check_oversize(run: Run) -> list[Verdict]:
    model = run.model
    prompt = filler_text(OVERSIZE_TOKENS) + "\nReply with only the number of the last line above."
    big, row = await run.probe.generate(
        5, "oversize prompt", model, prompt, config(model), est_tokens=estimate_tokens(len(prompt))
    )
    if big is None:
        oversize = Verdict(5, "Oversize prompt", model, "INFO", f"rejected: {row.error}")
    else:
        row.passed, row.why = True, f"accepted with {row.prompt_tokens} prompt tokens"
        row.detail["text"] = (big.text or "")[:TEXT_KEEP]
        oversize = Verdict(5, "Oversize prompt", model, "INFO", row.why)
    oversize.notes.append(
        f"limit for the model: {LIMITS[model].tpm or 'none'} input tokens a minute"
    )
    est = estimate_tokens(len(THINK_PROMPT))
    thought, think_row = await run.probe.generate(
        5, "thinking high", model, THINK_PROMPT, config(model, thinking="HIGH"), est_tokens=est
    )
    thinking = Verdict(
        5,
        "Thinking tokens",
        model,
        "INFO",
        f"thoughts_token_count {think_row.thoughts_tokens}, prompt {think_row.prompt_tokens}"
        if thought is not None
        else f"failed: {think_row.error}",
        notes=[
            f"sent at {think_row.started_utc}: compare the model's input-token chart on the"
            " AI Studio usage page to see whether thinking counts toward the minute limit"
        ],
    )
    return [oversize, thinking]


# --- test 6: plume images -------------------------------------------------------------------


def load_plume_eval() -> ModuleType:
    spec = importlib.util.spec_from_file_location("tephra_script_plume_eval", PLUME_SCRIPT)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {PLUME_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _PartMaker:
    """What ``plume_eval.arm_i_parts`` needs from its caller: text and image parts."""

    @staticmethod
    def text(value: str) -> Any:
        from google.genai import types

        return types.Part.from_text(text=value)

    @staticmethod
    def image(data: bytes) -> Any:
        from google.genai import types

        return types.Part.from_bytes(data=data, mime_type="image/png")


def plume_cases(plume: ModuleType) -> list[Path]:
    return sorted(path for path in plume.CASES_DIR.iterdir() if (path / "case.json").exists())


def semeru_ready(plume: ModuleType) -> bool:
    return (plume.ARM_T_DIR / "sigmets.json").exists() and (plume.ARM_T_DIR / "vona.txt").exists()


async def check_plume(run: Run) -> list[Verdict]:
    plume = load_plume_eval()
    model = run.model
    # No media_resolution: per-item resolution is documented for Gemini 3 only (brief, test 6).
    image_cfg = config(model, system=plume.SYSTEM_ARM_I, thinking="HIGH", schema=plume.SCHEMA)
    results: dict[str, list[dict[str, Any] | None]] = {}
    ids = {*plume.IMAGE_IDS, "VENT", "WIND"}
    for case_dir in plume_cases(plume):
        case = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
        parts = plume.arm_i_parts(_PartMaker, case_dir, case)
        text_chars = sum(len(part.text or "") for part in parts) + len(plume.SYSTEM_ARM_I)
        est = estimate_tokens(text_chars) + IMAGE_TOKENS_EST * len(plume.IMAGE_IDS)
        label = f"plume {case['id']} ({case['class']})"
        response, row = await run.probe.generate(6, label, model, parts, image_cfg, est_tokens=est)
        if response is None:
            results[case["id"]] = []
            continue
        answer = plume._parse(response.text)
        results[case["id"]] = [answer]
        problems = plume.schema_problems(answer, ids, "I")
        finding = answer.get("image_finding") if answer else None
        row.passed = not problems
        row.why = "; ".join(problems) or f"{finding} (label {case['class']})"
        row.detail["text"] = (response.text or "")[:TEXT_KEEP]
    table, scores = plume.score_arm_i(results, 1)
    verdicts = [
        Verdict(
            6,
            "Plume images (Arm I, 1 run per case)",
            model,
            "INFO",
            scores["existence"],
            notes=[
                *(f"{name}: {value}" for name, value in scores.items() if name != "stability"),
                "stability is not scored: it needs 3 runs per case (plume_eval.py)",
            ],
            detail={"table": table},
        )
    ]
    if not semeru_ready(plume):
        missing = (plume.ARM_T_DIR / "vona.txt").relative_to(PROJECT_ROOT)
        why = f"{missing} is missing (MAGMA text is not in the repo)"
        verdicts.append(Verdict(6, "Semeru texts (Arm T)", model, "NOT RUN", why))
        return verdicts
    lines, text_ids = plume.arm_t_inputs()
    text_cfg = config(model, system=plume.SYSTEM_ARM_T, thinking="HIGH", schema=plume.SCHEMA)
    prompt = "\n".join(lines)
    est = estimate_tokens(len(prompt) + len(plume.SYSTEM_ARM_T))
    response, row = await run.probe.generate(
        6, "Semeru texts", model, prompt, text_cfg, est_tokens=est
    )
    answers = [plume._parse(response.text)] if response is not None else []
    scores_t = plume.score_arm_t(answers, text_ids, 1)
    row.passed = scores_t["verdict"] == "PASS"
    row.why = str(scores_t)
    verdicts.append(
        Verdict(
            6,
            "Semeru texts (Arm T)",
            model,
            "INFO",
            scores_t["verdict"],
            notes=[f"{name}: {value}" for name, value in scores_t.items()],
        )
    )
    return verdicts


# --- test 7: reliability and latency --------------------------------------------------------


def p95(values: Sequence[int]) -> int | None:
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1] if ordered else None


async def check_reliability(run: Run) -> list[Verdict]:
    models = (GEMMA_31B, GEMMA_26B)
    calls = int(run.args.t7_calls)
    est = estimate_tokens(len(BASIC_SYSTEM) + len(SMALL_PROMPT))
    outcome: dict[str, list[tuple[bool, Row]]] = {model: [] for model in models}
    window = utc_now()
    for n in range(1, calls + 1):
        for model in models:
            cfg = config(model, system=BASIC_SYSTEM)
            response, row = await run.probe.generate(
                7, f"reliability {n}", model, SMALL_PROMPT, cfg, est_tokens=est, min_gap_s=T7_GAP_S
            )
            ok = response is not None and bool((response.text or "").strip())
            row.passed, row.why = ok, "text returned" if ok else row.why or "empty text"
            outcome[model].append((ok, row))
    verdicts: list[Verdict] = []
    for model, results in outcome.items():
        first = [r for r in run.probe.rows if r.test == 7 and r.model == model and r.attempt == 1]
        first_ok = sum(1 for r in first if r.http_status == 200)
        ok_count = sum(ok for ok, _ in results)
        latencies = [row.latency_ms for ok, row in results if ok and row.latency_ms is not None]
        top = p95(latencies)
        rate = ok_count / len(results) if results else 0.0
        passed = rate >= 0.95 and top is not None and top < 20_000
        errors = sorted({r.error[:80] for r in first if r.error})
        verdicts.append(
            Verdict(
                7,
                "Reliability and latency",
                model,
                "PASS" if passed else "FAIL",
                f"{ok_count}/{len(results)} ok with one retry ({first_ok}/{len(first)} first try);"
                f" p95 {top} ms",
                notes=[
                    f"window started {window} (the app retries twice; this script once)",
                    f"p50 {sorted(latencies)[len(latencies) // 2] if latencies else None} ms",
                    *(f"error seen: {error}" for error in errors[:4]),
                ],
            )
        )
    return verdicts


# --- test 8: pool independence --------------------------------------------------------------


async def check_pool(run: Run) -> list[Verdict]:
    est = estimate_tokens(len(SMALL_PROMPT))
    sent: list[str] = []
    for n in range(1, 6):
        response, row = await run.probe.generate(
            8, f"pool {n}", FLASH_LITE, SMALL_PROMPT, config(FLASH_LITE), est_tokens=est
        )
        row.passed = response is not None
        row.why = "sent" if response is not None else row.why
        if row.started_utc:
            sent.append(row.started_utc)
    ok = sum(1 for row in run.probe.rows if row.test == 8 and row.http_status == 200)
    return [
        Verdict(
            8,
            "Pool independence",
            FLASH_LITE,
            "INFO",
            f"{ok} answered of {len(sent)} sent; the pass needs the AI Studio usage page",
            notes=[
                f"sent at {', '.join(sent)}",
                f"pass: {FLASH_LITE} rises by the requests sent while gemini-3.5-flash-lite"
                " moves only by the live site's own logged gemini_call events",
            ],
        )
    ]


# --- test 12: free-key Batch ----------------------------------------------------------------


def batch_requests() -> list[Any]:
    from google.genai import types

    return [
        types.InlinedRequest(contents=prompt, config=config(FLASH_LITE))
        for prompt in (SMALL_PROMPT, BASIC_PROMPT)
    ]


def _state(job: Any) -> str:
    state = getattr(job, "state", None)
    return str(getattr(state, "value", state))


async def check_batch(run: Run) -> list[Verdict]:
    probe = run.probe
    name = run.args.batch_job
    if name is None:
        inline = batch_requests()

        async def create() -> Any:
            return await probe.client().aio.batches.create(
                model=FLASH_LITE, src=inline, config={"display_name": "tephra-free-model-check"}
            )

        job, row, _ = await probe.send(
            12, "batch create (2 requests)", FLASH_LITE, create, est_tokens=50
        )
        if job is None:
            return [Verdict(12, "Free-key Batch", FLASH_LITE, "FAIL", f"not accepted: {row.error}")]
        name = job.name
        row.passed, row.why = True, f"accepted as {name}, state {_state(job)}"
        polls = BATCH_POLLS
    else:
        polls = 1
    job = None
    for n in range(1, polls + 1):
        if run.args.batch_job is None:
            await asyncio.sleep(BATCH_POLL_GAP_S)

        async def get(name: str = str(name)) -> Any:
            return await probe.client().aio.batches.get(name=name)

        job, row, _ = await probe.send(12, f"batch poll {n}", FLASH_LITE, get, paced=False)
        if job is None:
            break
        row.passed, row.why = True, _state(job)
        if _state(job) in TERMINAL_JOB_STATES:
            break
    state = _state(job) if job is not None else "unknown"
    notes = [f"poll it later: --only 12 --batch-job {name}"]
    responses = getattr(getattr(job, "dest", None), "inlined_responses", None) or []
    for item in responses:
        reply = getattr(item, "response", None)
        usage = getattr(reply, "usage_metadata", None)
        text = (reply.text or "")[:120] if reply is not None else ""
        notes.append(f"answer: {text!r}; prompt tokens {_int(usage, 'prompt_token_count')}")
        if getattr(item, "error", None):
            notes.append(f"error: {probe.scrub(str(item.error))[:200]}")
    notes.append(f"pass also needs the AI Studio usage page: did {FLASH_LITE}'s day count move?")
    result = "PASS" if state == "JOB_STATE_SUCCEEDED" else "INFO"
    return [Verdict(12, "Free-key Batch", FLASH_LITE, result, f"{name}: {state}", notes=notes)]


# --- plan, dry run and output ---------------------------------------------------------------


@dataclass(frozen=True)
class Check:
    name: str
    runner: Callable[[Run], Awaitable[list[Verdict]]]
    models: Callable[[argparse.Namespace], tuple[str, ...]]
    calls: Callable[[argparse.Namespace], int]
    note: str


def _plume_calls(_: argparse.Namespace) -> int:
    plume = load_plume_eval()
    return len(plume_cases(plume)) + semeru_ready(plume)


def _agent_turns(module: str) -> int:
    return int(importlib.import_module(f"tephra.agents.{module}").MAX_MODEL_TURNS)


TESTS: Final[dict[int, Check]] = {
    0: Check("Limits (models.get)", check_limits, lambda a: MODELS, lambda a: 3, "information"),
    1: Check(
        "Basics", check_basics, lambda a: MODELS, lambda a: 3, "system text, minimal thinking"
    ),
    2: Check(
        "Schema (drafter, notice, handover)",
        check_schema,
        lambda a: (a.model,),
        lambda a: len(JOBS) * (T2_RUNS + (1 if is_gemma(a.model) else 0)),
        f"{T2_RUNS} runs at 1.0/0.95/64 and 1 at 0.6 per job; repairs recorded, not sent",
    ),
    3: Check(
        "Planner tools (ADK)",
        check_planner,
        lambda a: (a.model,),
        lambda a: _agent_turns("exposure_planner"),
        "worst case: the app's turn cap, repair included",
    ),
    4: Check(
        "Duty Officer (ADK)",
        check_duty,
        lambda a: (a.model,),
        lambda a: _agent_turns("duty_officer"),
        "worst case: the app's turn cap; delegations answered from the stub tick",
    ),
    5: Check(
        "Oversize prompt",
        check_oversize,
        lambda a: (a.model,),
        lambda a: 2,
        "~20K tokens, then thinking high",
    ),
    6: Check(
        "Plume images",
        check_plume,
        lambda a: (a.model,),
        _plume_calls,
        "1 run per case, no media_resolution",
    ),
    7: Check(
        "Reliability and latency",
        check_reliability,
        lambda a: (GEMMA_31B, GEMMA_26B),
        lambda a: 2 * a.t7_calls,
        f"each model's sends at least {T7_GAP_S:.0f} s apart; run once per window",
    ),
    8: Check(
        "Pool independence",
        check_pool,
        lambda a: (FLASH_LITE,),
        lambda a: 5,
        "check AI Studio after",
    ),
    12: Check(
        "Free-key Batch",
        check_batch,
        lambda a: (FLASH_LITE,),
        lambda a: 1 if a.batch_job else 1 + BATCH_POLLS,
        "2 inline requests; polls count as requests",
    ),
}


def print_plan(args: argparse.Namespace, tests: Sequence[int]) -> int:
    total = 0
    print(f"Plan (hard cap {HARD_CAP} requests a run; a failed request may be retried once):")
    for test_id in tests:
        test = TESTS[test_id]
        calls = test.calls(args)
        total += calls
        models = ", ".join(test.models(args))
        print(f"  test {test_id:>2} {test.name:<36} {calls:>3} request(s)  {models}  ({test.note})")
    print(f"  worst case before retries: {total} request(s)")
    print(
        f"  pacing: Gemma {LIMITS[GEMMA_31B].rpm}/min and {GEMMA_TPM} input tokens/min,"
        f" {FLASH_LITE} {LIMITS[FLASH_LITE].rpm}/min; never gemini-3.5-flash-lite"
    )
    return total


async def dry_run(args: argparse.Namespace, tests: Sequence[int]) -> int:
    """Everything a live run prepares, offline: configs, inputs and the stub replay world."""
    from google.genai import types

    for model in MODELS:
        types.GenerateContentConfig.model_validate(config(model, system=BASIC_SYSTEM))
    if 12 in tests:
        print(f"  batch: {len(batch_requests())} inline request(s) to {FLASH_LITE}")
    if any(test in tests for test in (2, 3, 4)):
        run = Run(args, probe=None)
        try:
            world = await run.world()
            ctx = world.planner_ctx
            decision = world.stub_plan.decision
            print(
                f"  world: {len(world.worklist)} Duty item(s), {len(world.delegations)} recorded"
                f" delegation(s); planner flight {ctx.flight.proxy_flight} ({ctx.volcano_name}),"
                f" stub plan {decision.action.value if decision else None}"
            )
            print("  digest:\n    " + world.digest.replace("\n", "\n    "))
        finally:
            await run.close()
    if 2 in tests:
        print(f"  notice fixture: {NOTICE_FIXTURE.relative_to(PROJECT_ROOT)}")
        if "response_format" not in types.GenerateContentConfig.model_fields:
            print("  response_format variant: not run (the pinned google-genai has no such field)")
    if 6 in tests:
        plume = load_plume_eval()
        print(
            f"  plume cases: {len(plume_cases(plume))}; Semeru texts ready: {semeru_ready(plume)}"
        )
    print("Dry run: no request was sent.")
    return 0


def write_outputs(
    args: argparse.Namespace,
    tests: Sequence[int],
    probe: Probe,
    verdicts: list[Verdict],
    started: str,
) -> tuple[Path, Path]:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%MZ")
    tag = "-".join(str(test) for test in tests)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"free-model-check-{stamp}-t{tag}.json"
    md_path = json_path.with_suffix(".md")
    run_info = {
        "started_utc": started,
        "finished_utc": utc_now(),
        "tests": list(tests),
        "model_under_test": args.model,
        "requests_sent": probe.sent,
        "hard_cap": HARD_CAP,
        "replay_world": f"{CASE_ID} at {CASE_AT:%Y-%m-%dT%H:%MZ} (stub tick, NO MODEL)",
        "google_genai": importlib.metadata.version("google-genai"),
        "google_adk": importlib.metadata.version("google-adk"),
        "closed_models": probe.closed,
    }
    payload = {
        "run": run_info,
        "verdicts": [asdict(v) for v in verdicts],
        "calls": [asdict(row) for row in probe.rows],
    }
    text = probe.scrub(json.dumps(payload, indent=1, default=str, ensure_ascii=False))
    json_path.write_text(text + "\n", encoding="utf-8")
    lines = [
        f"# Free-model check, {started}",
        "",
        f"Tests {', '.join(map(str, tests))}; {probe.sent} of {HARD_CAP} requests sent;"
        f" tests 2 to 6 on `{args.model}`. Pass rules are the free-model brief's (13 Oct 2026,"
        " section 4). Every call is in"
        f" `{json_path.name}`.",
        "",
        "| Test | Model | Result | Why |",
        "|---|---|---|---|",
        *(
            f"| {v.test} {v.name} | `{v.model}` | {v.result} | {v.why.replace('|', '/')} |"
            for v in verdicts
        ),
        "",
    ]
    for verdict in verdicts:
        if verdict.notes:
            lines += [f"**{verdict.test} {verdict.name} ({verdict.model})**", ""]
            lines += [f"- {note}" for note in verdict.notes] + [""]
    if probe.closed:
        lines += [f"- Closed for the run: {model}: {why}" for model, why in probe.closed.items()]
    md_path.write_text(probe.scrub("\n".join(lines)) + "\n", encoding="utf-8")
    return json_path, md_path


async def live_run(args: argparse.Namespace, tests: Sequence[int], key: str) -> int:
    probe = Probe(key, HARD_CAP)
    run = Run(args, probe)
    verdicts: list[Verdict] = []
    started = utc_now()
    try:
        for test_id in tests:
            test = TESTS[test_id]
            print(f"test {test_id}: {test.name}")
            capped = False
            try:
                found = await test.runner(run)
            except CapReached as exc:
                found, capped = (
                    [Verdict(test_id, test.name, args.model, "NOT RUN", f"stopped: {exc}")],
                    True,
                )
            except Exception as exc:  # a script fault in one test is kept; the rest still run
                why = probe.scrub(f"script error: {type(exc).__name__}: {exc}")[:300]
                found = [Verdict(test_id, test.name, args.model, "NOT RUN", why)]
            verdicts += found
            for verdict in found:
                print(f"  {verdict.result:<7} {verdict.model}: {verdict.why[:140]}")
            if capped:
                break
    finally:
        await run.close()
        json_path, md_path = write_outputs(args, tests, probe, verdicts, started)
        print(f"\n{probe.sent} request(s) sent.\nResults: {json_path}\nSummary: {md_path}")
    return 0


def parse_tests(values: Sequence[str] | None) -> tuple[int, ...]:
    if not values:
        return DEFAULT_TESTS
    found: list[int] = []
    for value in values:
        for piece in value.split(","):
            if not piece.strip():
                continue
            test = int(piece)
            if test not in TEST_IDS:
                raise SystemExit(
                    f"unknown test {test}; choose from {', '.join(map(str, TEST_IDS))}"
                )
            found.append(test)
    return tuple(dict.fromkeys(sorted(found)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Live checks of the free Google models (free-model brief, section 4)."
    )
    parser.add_argument("--dry-run", action="store_true", help="print the plan; send nothing")
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="TEST",
        help=f"test ids, e.g. 0 1 or 0,1 (default: {','.join(map(str, DEFAULT_TESTS))})",
    )
    parser.add_argument(
        "--model",
        choices=MODELS,
        default=GEMMA_31B,
        help="model for tests 2 to 6 (default %(default)s)",
    )
    parser.add_argument("--t7-calls", type=int, default=T7_CALLS, help="test 7 calls per model")
    parser.add_argument(
        "--batch-job", help="test 12: poll this batch job once instead of creating one"
    )
    parser.add_argument("--out-dir", default=str(OUT_DIR), help="where results are written")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    tests = parse_tests(args.only)

    total = print_plan(args, tests)
    if total > HARD_CAP:
        print(
            f"The plan needs {total} requests, over the cap of {HARD_CAP}: run fewer with --only."
        )
        return 2
    if args.dry_run:
        return asyncio.run(dry_run(args, tests))
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        print("GEMINI_API_KEY is not set (a personal Google AI Studio key).")
        return 2
    # As tephra.config.apply_process_env: ADK reads GOOGLE_API_KEY; Vertex AI stays off.
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"
    os.environ["GOOGLE_GENAI_USE_ENTERPRISE"] = "FALSE"
    os.environ["GOOGLE_API_KEY"] = key
    return asyncio.run(live_run(args, tests, key))


if __name__ == "__main__":
    raise SystemExit(main())
