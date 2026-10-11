"""The one place TEPHRA talks to Gemini, plus a deterministic stand-in.

Gemini is reached only with a Google AI Studio key through ``genai.Client(api_key=...)``;
never Vertex AI, never Application Default Credentials. Every call:

* is checked against a per-tier daily budget first (the free tier allows about 20 calls a
  day to the main model; research/06), counted on Google's quota day, which ends at
  midnight Pacific time, and kept in ``cache_dir/llm`` so a restart does not reset it,
* is answered from a disk cache when the same model already saw the same prompt and images,
* runs a Gemini 3 model at its default temperature of 1.0 unless the caller names one,
* retries 5xx and per-minute 429s with back-off; a 429 for a per-day quota closes the tier
  until the quota day ends, and
* never raises for model trouble: callers get ``(None, call)`` with ``call.error`` set and
  fall back to code.

``StubBackend`` (``TEPHRA_LLM=stub``) returns the caller's deterministic ``stub()`` result
and never touches the network; everything it produces is labelled NO MODEL downstream.
"""

import asyncio
import json
import logging
import os
import re
import time
from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta, timezone, tzinfo
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal, Protocol, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt

from tephra.agents.schemas import gemini_schema, parse_json_model
from tephra.config import Settings
from tephra.models import LlmBackendName, TephraModel
from tephra.util import timeutil
from tephra.util.hashing import sha256_bytes, sha256_json

if TYPE_CHECKING:
    from google.genai import types as genai_types

__all__ = [
    "BudgetExhausted",
    "DailyBudget",
    "GeminiBackend",
    "LlmBackend",
    "LlmCall",
    "LlmPart",
    "StubBackend",
    "Tier",
    "daily_quota_spent",
    "get_llm",
    "prompt_hash",
    "temperature_for",
]

logger = logging.getLogger(__name__)

Tier = Literal["main", "lite"]

RETRY_DELAYS_S: Final[tuple[float, ...]] = (2.0, 8.0)
"""Back-off before the second and third attempt of one call (429 and 5xx only)."""
RETRYABLE_STATUS: Final = frozenset({429, 500, 502, 503, 504})
BUDGET_EXHAUSTED: Final = "budget_exhausted"
BUDGET_FILE: Final = "daily_budget.json"
GEMINI_3_TEMPERATURE: Final = 1.0
"""research/10 C9: Google strongly recommends keeping every Gemini 3 model at its default
temperature of 1.0; lower values may make it loop."""
DEFAULT_TEMPERATURE: Final = 0.2
_GEMINI_3: Final = re.compile(r"(?:models/)?gemini-3(?:[.-]|$)")


def temperature_for(model_id: str) -> float:
    return GEMINI_3_TEMPERATURE if _GEMINI_3.match(model_id) else DEFAULT_TEMPERATURE


class LlmPart(TephraModel):
    """One piece of the user turn: text, an image with the label it is announced by, or audio
    (an unlabelled-to-the-model recording; the label is for logs and the prompt hash)."""

    model_config = ConfigDict(
        extra="ignore", protected_namespaces=(), populate_by_name=True, ser_json_bytes="base64"
    )

    kind: Literal["text", "image", "audio"]
    text: str | None = None
    data: bytes | None = None
    mime_type: str | None = None
    label: str | None = None

    @classmethod
    def of_text(cls, text: str) -> Self:
        return cls(kind="text", text=text)

    @classmethod
    def of_image(cls, data: bytes, *, label: str, mime_type: str = "image/png") -> Self:
        return cls(kind="image", data=data, mime_type=mime_type, label=label)

    @classmethod
    def of_audio(cls, data: bytes, *, label: str, mime_type: str) -> Self:
        return cls(kind="audio", data=data, mime_type=mime_type, label=label)


class LlmCall(TephraModel):
    """What one ``structured`` call did, for traces, assessments and the audit trail."""

    backend: LlmBackendName
    model_id: str
    prompt_hash: str
    latency_ms: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    raw_text: str | None = None
    error: str | None = None
    cached: bool = False


class LlmBackend(Protocol):
    @property
    def name(self) -> LlmBackendName: ...

    def model_id(self, tier: Tier) -> str: ...

    def reserve(self, tier: Tier) -> bool: ...

    def exhaust(self, tier: Tier) -> None:
        """Google reported the tier's daily quota spent: refuse it until the quota day ends."""
        ...

    async def structured[T: BaseModel](
        self,
        *,
        tier: Tier,
        system: str,
        parts: Sequence[LlmPart],
        schema: type[T],
        stub: Callable[[], T],
        temperature: float | None = None,
    ) -> tuple[T | None, LlmCall]:
        """``temperature=None`` runs the tier's model at ``temperature_for(model)``."""
        ...


class BudgetExhausted(RuntimeError):
    """Today's call budget for a tier is used up; the caller falls back to code."""


def _quota_zone() -> tzinfo:
    try:
        return ZoneInfo("America/Los_Angeles")
    except ZoneInfoNotFoundError:
        # No tz database: Pacific standard time all year (the day starts an hour late in summer).
        return timezone(timedelta(hours=-8))


_QUOTA_ZONE: Final = _quota_zone()
"""Free-tier requests per day reset at midnight Pacific time (research/10, rate-limits page)."""


class _SavedBudget(TephraModel):
    """One quota day of ``DailyBudget`` counts, as kept on disk."""

    quota_day: date
    used: dict[Tier, NonNegativeInt] = Field(default_factory=dict)
    spent: list[Tier] = Field(default_factory=list)


class DailyBudget:
    """Calls per tier per quota day.

    The day is Google's (midnight to midnight Pacific time) on the wall clock, even in
    REPLAY: the quota being protected resets on real days, not recorded ones. A 429 that
    names a per-day quota closes the tier until the next quota day. With a ``path`` the
    day's counts are written there on every change and read back at start, so a restart does
    not hand the day's quota out again; if the file cannot be written, counting goes on in
    memory.
    """

    def __init__(
        self, now: Callable[[], datetime] | None = None, *, path: Path | None = None
    ) -> None:
        self._now = now or timeutil.SystemClock().now
        self._path = path
        self._day = self._today()
        self._used: dict[Tier, int] = {}
        self._spent: set[Tier] = set()
        self._save_failed = False
        self._load()

    def take(self, tier: Tier, limit: int) -> None:
        self._roll()
        used = self._used.get(tier, 0)
        if tier in self._spent:
            raise BudgetExhausted(f"{tier} tier: Google reported today's quota spent")
        if used >= limit:
            raise BudgetExhausted(f"{tier} tier used {used} of {limit} calls today")
        self._used[tier] = used + 1
        self._save()

    def exhaust(self, tier: Tier) -> None:
        self._roll()
        self._spent.add(tier)
        self._save()

    def used(self, tier: Tier) -> int:
        self._roll()
        return self._used.get(tier, 0)

    def _today(self) -> date:
        return self._now().astimezone(_QUOTA_ZONE).date()

    def _roll(self) -> None:
        today = self._today()
        if today != self._day:
            self._day, self._used, self._spent = today, {}, set()

    def _load(self) -> None:
        if self._path is None:
            return
        try:
            saved = _SavedBudget.model_validate_json(self._path.read_bytes())
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            logger.warning("ignoring unreadable llm daily budget %s: %s", self._path, exc)
            return
        if saved.quota_day == self._day:
            self._used, self._spent = dict(saved.used), set(saved.spent)

    def _save(self) -> None:
        if self._path is None:
            return
        saved = _SavedBudget(quota_day=self._day, used=self._used, spent=sorted(self._spent))
        tmp = self._path.with_suffix(f".{os.getpid()}.tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(saved.model_dump_json(), encoding="utf-8")
            tmp.replace(self._path)
        except OSError as exc:
            if not self._save_failed:
                logger.warning(
                    "could not save the llm daily budget to %s (%s); counting in memory",
                    self._path,
                    exc,
                )
            self._save_failed = True


@cache
def _process_budget(path: Path) -> DailyBudget:
    """One budget per file, shared by every backend in the process."""
    return DailyBudget(path=path)


def prompt_hash(system: str, parts: Sequence[LlmPart]) -> str:
    """Content hash of a prompt; an image or a recording contributes the sha256 of its bytes."""
    pieces: list[dict[str, Any]] = []
    for part in parts:
        if part.kind in ("image", "audio"):
            pieces.append(
                {
                    "kind": part.kind,
                    "label": part.label,
                    "mime_type": part.mime_type,
                    "sha256": sha256_bytes(part.data or b""),
                }
            )
        else:
            pieces.append({"kind": "text", "text": part.text or ""})
    return sha256_json({"system": system, "parts": pieces})


def get_llm(settings: Settings) -> LlmBackend:
    if settings.llm == "gemini":
        return GeminiBackend(settings)
    return StubBackend()


class StubBackend:
    """Deterministic and offline (``TEPHRA_LLM=stub``): returns the caller's ``stub()``."""

    @property
    def name(self) -> LlmBackendName:
        return "stub"

    def model_id(self, tier: Tier) -> str:
        return "stub"

    def reserve(self, tier: Tier) -> bool:
        return True

    def exhaust(self, tier: Tier) -> None:
        """The stub spends no quota, so there is nothing to close."""

    async def structured[T: BaseModel](
        self,
        *,
        tier: Tier,
        system: str,
        parts: Sequence[LlmPart],
        schema: type[T],
        stub: Callable[[], T],
        temperature: float | None = None,
    ) -> tuple[T | None, LlmCall]:
        value = schema.model_validate(stub().model_dump())
        call = LlmCall(
            backend="stub",
            model_id="stub",
            prompt_hash=prompt_hash(system, parts),
            raw_text=value.model_dump_json(),
        )
        return value, call


class GeminiBackend:
    """Gemini through the google-genai SDK with an AI Studio API key only."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: Any | None = None,
        cache_dir: Path | None = None,
        budget: DailyBudget | None = None,
        retry_delays_s: Sequence[float] = RETRY_DELAYS_S,
    ) -> None:
        api_key = settings.gemini_api_key
        if api_key is None:
            raise ValueError("GeminiBackend needs GEMINI_API_KEY (a Google AI Studio key)")
        self._settings = settings
        self._api_key = api_key
        self._client_obj = client
        llm_dir = cache_dir if cache_dir is not None else settings.cache_dir / "llm"
        self._cache = _DiskCache(llm_dir)
        self._budget = budget if budget is not None else _process_budget(llm_dir / BUDGET_FILE)
        self._retry_delays_s = tuple(retry_delays_s)

    @property
    def name(self) -> LlmBackendName:
        return "gemini"

    def model_id(self, tier: Tier) -> str:
        return self._settings.model if tier == "main" else self._settings.model_lite

    def reserve(self, tier: Tier) -> bool:
        try:
            self._budget.take(tier, self._limit(tier))
        except BudgetExhausted as exc:
            logger.warning("gemini budget: %s", exc)
            return False
        return True

    def exhaust(self, tier: Tier) -> None:
        self._budget.exhaust(tier)

    async def structured[T: BaseModel](
        self,
        *,
        tier: Tier,
        system: str,
        parts: Sequence[LlmPart],
        schema: type[T],
        stub: Callable[[], T],
        temperature: float | None = None,
    ) -> tuple[T | None, LlmCall]:
        model = self.model_id(tier)
        if temperature is None:
            temperature = temperature_for(model)
        p_hash = prompt_hash(system, parts)
        key = sha256_json(
            {
                "model": model,
                "prompt": p_hash,
                "schema": gemini_schema(schema),
                "temperature": temperature,
            }
        )
        call = LlmCall(backend="gemini", model_id=model, prompt_hash=p_hash)

        cached_text = await asyncio.to_thread(self._cache.read, key)
        if cached_text is not None:
            try:
                value = parse_json_model(cached_text, schema)
            except ValueError:
                logger.warning("ignoring unreadable llm cache entry %s", key[:12])
            else:
                call = call.model_copy(update={"raw_text": cached_text, "cached": True})
                self._log(tier, call, "cache_hit")
                return value, call

        if not self.reserve(tier):
            call = call.model_copy(update={"error": BUDGET_EXHAUSTED})
            self._log(tier, call, "budget_exhausted")
            return None, call

        started = time.monotonic()
        try:
            response = await self._generate(model, system, parts, schema, temperature)
        except Exception as exc:  # any SDK, transport or timeout failure falls back to code
            if daily_quota_spent(exc):
                self.exhaust(tier)
            call = call.model_copy(
                update={"latency_ms": _elapsed_ms(started), "error": _describe(exc)}
            )
            self._log(tier, call, "error")
            return None, call

        usage = getattr(response, "usage_metadata", None)
        text = response.text
        call = call.model_copy(
            update={
                "latency_ms": _elapsed_ms(started),
                "input_tokens": _tokens(usage, "prompt_token_count"),
                "output_tokens": _output_tokens(usage),
                "raw_text": text,
            }
        )
        if not text:
            call = call.model_copy(update={"error": f"empty_response {_finish_reason(response)}"})
            self._log(tier, call, "empty")
            return None, call
        try:
            value = parse_json_model(text, schema)
        except ValueError as exc:
            call = call.model_copy(update={"error": f"invalid_output: {exc}"})
            self._log(tier, call, "invalid")
            return None, call
        await asyncio.to_thread(self._cache.write, key, model, p_hash, text)
        self._log(tier, call, "ok")
        return value, call

    # --- internals ----------------------------------------------------------------------

    def _limit(self, tier: Tier) -> int:
        if tier == "main":
            return self._settings.model_daily_budget
        return self._settings.model_lite_daily_budget

    def _client(self) -> Any:
        if self._client_obj is None:
            from google import genai
            from google.genai import types

            # vertexai=False pins the Gemini Developer API (AI Studio key); never Vertex/ADC.
            self._client_obj = genai.Client(
                api_key=self._api_key.get_secret_value(),
                vertexai=False,
                http_options=types.HttpOptions(timeout=int(self._settings.llm_timeout_s * 1000)),
            )
        return self._client_obj

    async def _generate(
        self,
        model: str,
        system: str,
        parts: Sequence[LlmPart],
        schema: type[BaseModel],
        temperature: float,
    ) -> Any:
        from google.genai import errors

        contents = _contents(parts)
        config = _config(system, parts, schema, temperature)
        for attempt, delay in enumerate(self._retry_delays_s, start=1):
            try:
                return await self._request(model, contents, config)
            except (errors.APIError, httpx.TransportError) as exc:
                if not _retryable(exc):
                    raise
                logger.warning(
                    "gemini attempt %d failed (%s); retrying in %.1f s",
                    attempt,
                    _describe(exc),
                    delay,
                )
                await asyncio.sleep(delay)
        return await self._request(model, contents, config)

    async def _request(
        self,
        model: str,
        contents: list["genai_types.Part"],
        config: "genai_types.GenerateContentConfig",
    ) -> Any:
        return await asyncio.wait_for(
            self._client().aio.models.generate_content(
                model=model, contents=contents, config=config
            ),
            timeout=self._settings.llm_timeout_s,
        )

    def _log(self, tier: Tier, call: LlmCall, outcome: str) -> None:
        logger.info(
            "llm backend=gemini tier=%s model=%s prompt=%s outcome=%s latency_ms=%d "
            "input_tokens=%s output_tokens=%s",
            tier,
            call.model_id,
            call.prompt_hash[:12],
            outcome,
            call.latency_ms,
            call.input_tokens,
            call.output_tokens,
        )


class _DiskCache:
    """Validated responses keyed by model, prompt hash (images included) and schema."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def read(self, key: str) -> str | None:
        try:
            entry = json.loads((self._root / f"{key}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        raw = entry.get("raw_text")
        return raw if isinstance(raw, str) else None

    def write(self, key: str, model: str, p_hash: str, raw_text: str) -> None:
        entry = {
            "model_id": model,
            "prompt_hash": p_hash,
            "stored_at": timeutil.to_iso(timeutil.SystemClock().now()),
            "raw_text": raw_text,
        }
        path = self._root / f"{key}.json"
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(entry), encoding="utf-8")
            tmp.replace(path)
        except OSError as exc:
            logger.warning("could not write llm cache entry %s: %s", key[:12], exc)


def _contents(parts: Sequence[LlmPart]) -> list["genai_types.Part"]:
    from google.genai import types

    contents: list[types.Part] = []
    for part in parts:
        if part.kind == "image":
            contents.append(types.Part.from_text(text=f"IMAGE {part.label or 'UNLABELLED'}"))
            mime_type = part.mime_type or "image/png"
            contents.append(types.Part.from_bytes(data=part.data or b"", mime_type=mime_type))
        elif part.kind == "audio":
            mime_type = part.mime_type or "audio/wav"
            contents.append(types.Part.from_bytes(data=part.data or b"", mime_type=mime_type))
        else:
            contents.append(types.Part.from_text(text=part.text or ""))
    return contents


def _config(
    system: str, parts: Sequence[LlmPart], schema: type[BaseModel], temperature: float
) -> "genai_types.GenerateContentConfig":
    from google.genai import types

    has_images = any(part.kind == "image" for part in parts)
    return types.GenerateContentConfig(
        system_instruction=system,
        temperature=temperature,
        response_mime_type="application/json",
        response_json_schema=gemini_schema(schema),
        # research/10: "high" is Google's recommendation for image analysis on Gemini 3.
        media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH if has_images else None,
    )


def _retryable(exc: Exception) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    return getattr(exc, "code", None) in RETRYABLE_STATUS and not daily_quota_spent(exc)


def daily_quota_spent(exc: BaseException) -> bool:
    """A 429 whose QuotaFailure names a per-day quota (``...PerDay...``): nothing clears it
    before Google's quota day ends, so retrying only spends time."""
    return getattr(exc, "code", None) == 429 and "PerDay" in str(getattr(exc, "details", ""))


def _describe(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError):
        return "timeout"
    code = getattr(exc, "code", None)
    status = getattr(exc, "status", None)
    if code is not None:
        return f"api_error {code} {status or ''}".strip()
    return f"{type(exc).__name__}: {exc}"[:300]


def _tokens(usage: Any, field: str) -> int | None:
    value = getattr(usage, field, None) if usage is not None else None
    return int(value) if isinstance(value, int) else None


def _output_tokens(usage: Any) -> int | None:
    candidates = _tokens(usage, "candidates_token_count")
    thoughts = _tokens(usage, "thoughts_token_count")
    if candidates is None and thoughts is None:
        return None
    return (candidates or 0) + (thoughts or 0)


def _finish_reason(response: Any) -> str:
    candidates = getattr(response, "candidates", None) or []
    reason = getattr(candidates[0], "finish_reason", None) if candidates else None
    return str(reason) if reason is not None else "no_candidates"


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
