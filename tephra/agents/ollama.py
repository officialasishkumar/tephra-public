"""Every model step on a Gemma model served by Ollama on this computer (``TEPHRA_LLM=ollama``).

Two doors to one local model:

* ``OllamaBackend`` is the ``LlmBackend`` for the single-call skills (Plume reader, Drafter,
  Notice and Satellite readers, messages, handover, SRA narrative): one ``/api/chat`` request
  with the caller's JSON schema as Ollama's ``format``, parsed and validated like Gemini's.
* ``OllamaLlm`` is the ADK model class for the agents (Coordinator, Flight planner, Ask,
  Recovery planner). ``TEPHRA_MODEL_LITE=gemma4:e4b`` reaches it through ADK's registry: an
  Ollama tag (``name:tag``) matches no Gemini pattern, and :data:`OLLAMA_TAG` claims it.

A local model has no daily quota, so nothing is reserved or paced. It answers one request at a
time: :class:`LocalSlot` queues the rest, a person's question (the interactive lane) and urgent
work ahead of routine work, so the Desk's Ask is not stuck behind a backlog of flight plans.
A failure is AI UNAVAILABLE with its reason, exactly as with Gemini; nothing stands in for it.
"""

import asyncio
import base64
import heapq
import itertools
import json
import logging
import time
from collections.abc import AsyncGenerator, Callable, Sequence
from typing import Any, ClassVar, Final, Literal

import httpx
from google.adk.models import BaseLlm, LLMRegistry, LlmRequest, LlmResponse
from google.genai import types
from pydantic import BaseModel

from tephra.agents.llm import LlmCall, LlmPart, Tier, prompt_hash, temperature_for
from tephra.agents.quota import Lane, current_lane
from tephra.agents.schemas import gemini_schema, parse_json_model
from tephra.config import Settings
from tephra.models import LlmBackendName

__all__ = ["OLLAMA_TAG", "LocalSlot", "OllamaBackend", "OllamaLlm", "ollama_ready"]

logger = logging.getLogger(__name__)

OLLAMA_TAG: Final = r"[A-Za-z0-9._-]+:[A-Za-z0-9._-]+"
"""An Ollama model tag such as ``gemma4:e4b``; no Gemini model id has a colon."""
KEEP_ALIVE: Final = "30m"
"""How long Ollama keeps the model in memory after a request, so a demo never reloads it."""
LANE_ORDER: Final[dict[Lane, int]] = {"urgent": 0, "interactive": 1, "routine": 2}
_SCHEMA_DROP: Final = frozenset({"nullable", "property_ordering", "title", "example"})


class LocalSlot:
    """One request at a time to the local model; waiting requests go in lane order, then in
    the order they asked."""

    def __init__(self) -> None:
        self._busy = False
        self._queue: list[tuple[int, int, asyncio.Future[None]]] = []
        self._order = itertools.count()

    async def __aenter__(self) -> None:
        if not self._busy and not self._queue:
            self._busy = True
            return
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        heapq.heappush(self._queue, (LANE_ORDER[current_lane()], next(self._order), future))
        try:
            await future
        except asyncio.CancelledError:
            if future.done() and not future.cancelled():
                self._release()  # handed the slot just as it was cancelled: pass it on
            raise

    async def __aexit__(self, *_: object) -> None:
        self._release()

    def _release(self) -> None:
        while self._queue:
            _, _, future = heapq.heappop(self._queue)
            if not future.done():
                future.set_result(None)
                return
        self._busy = False


_SLOT = LocalSlot()


class _Config:
    """What ``OllamaLlm`` instances read: ADK builds them from a model name alone."""

    url = "http://127.0.0.1:11434"
    think: Literal["none", "main", "all"] = "main"
    timeout_s = 60.0
    num_ctx = 32768


def configure(settings: Settings) -> None:
    _Config.url = settings.ollama_url.rstrip("/")
    _Config.think = settings.ollama_think
    _Config.num_ctx = settings.ollama_num_ctx
    _Config.timeout_s = settings.llm_timeout_s


async def _chat(body: dict[str, Any], tier: Tier) -> dict[str, Any]:
    """One ``/api/chat`` request once the local slot is free; raises on any HTTP trouble."""
    # Ollama's default context is a few thousand tokens and it drops the start of a longer
    # conversation without a word: an agent's task and system prompt went first.
    options = {**body.get("options", {}), "num_ctx": _Config.num_ctx}
    payload = {
        **body,
        "options": options,
        "stream": False,
        "think": _Config.think == "all" or (_Config.think == "main" and tier == "main"),
        "keep_alive": KEEP_ALIVE,
    }
    async with _SLOT, httpx.AsyncClient(timeout=_Config.timeout_s) as client:
        response = await client.post(f"{_Config.url}/api/chat", json=payload)
    if response.status_code != 200:
        raise OllamaError(f"ollama {response.status_code}: {response.text[:200]}")
    return response.json()


class OllamaError(Exception):
    """Ollama answered with an error status."""


async def ollama_ready(settings: Settings) -> str | None:
    """None when Ollama answers at ``ollama_url`` and has both configured models pulled;
    otherwise what is missing, in plain words."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.ollama_url.rstrip('/')}/api/tags")
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return f"Ollama is not answering at {settings.ollama_url} ({type(exc).__name__})"
    pulled = {m.get("name") for m in response.json().get("models", [])}
    missing = sorted({settings.model, settings.model_lite} - pulled)
    return f"not pulled in Ollama: {', '.join(missing)} (ollama pull ...)" if missing else None


class OllamaBackend:
    """``LlmBackend`` on the local model: no quota, no pacing, one attempt a call."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        configure(settings)

    @property
    def name(self) -> LlmBackendName:
        return "ollama"

    @property
    def metered(self) -> bool:
        return False

    def model_id(self, tier: Tier) -> str:
        return self._settings.model if tier == "main" else self._settings.model_lite

    async def reserve(self, tier: Tier) -> str | None:
        return None

    async def exhaust(self, tier: Tier) -> None:
        """A local model has no daily quota to close."""

    async def pace(self, tier: Tier, tokens: int = 0) -> None:
        """Nothing to pace: requests queue for the local slot instead."""

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
        call = LlmCall(backend="ollama", model_id=model, prompt_hash=prompt_hash(system, parts))
        if tier == "tts" or any(part.kind == "audio" for part in parts):
            call = call.model_copy(update={"error": "the local model takes no audio"})
            _log(tier, call, "refused")
            return None, call
        user: dict[str, Any] = {"role": "user", "content": _user_text(parts)}
        images = [_b64(part.data) for part in parts if part.kind == "image"]
        if images:
            user["images"] = images
        body = {
            "model": model,
            "messages": [{"role": "system", "content": system}, user],
            "format": gemini_schema(schema),
            "options": {
                "temperature": temperature_for(model) if temperature is None else temperature
            },
        }
        started = time.monotonic()
        try:
            reply = await _chat(body, tier)
        except Exception as exc:  # transport, timeout or Ollama error: AI UNAVAILABLE
            call = call.model_copy(update={"latency_ms": _ms(started), "error": _describe(exc)})
            _log(tier, call, "error")
            return None, call
        text = (reply.get("message") or {}).get("content") or ""
        call = call.model_copy(
            update={
                "latency_ms": _ms(started),
                "input_tokens": reply.get("prompt_eval_count"),
                "output_tokens": reply.get("eval_count"),
                "raw_text": text,
            }
        )
        if not text:
            call = call.model_copy(update={"error": f"empty_response {reply.get('done_reason')}"})
            _log(tier, call, "empty")
            return None, call
        try:
            value = parse_json_model(text, schema)
        except ValueError as exc:
            call = call.model_copy(update={"error": f"invalid_output: {exc}"})
            _log(tier, call, "invalid")
            return None, call
        _log(tier, call, "ok")
        return value, call


class OllamaLlm(BaseLlm):
    """ADK's model for an agent turn on the local model: the conversation, the agent's tools as
    Ollama tools, and the reply's text and tool calls back as one ``LlmResponse``."""

    supported: ClassVar[list[str]] = [OLLAMA_TAG]

    @classmethod
    def supported_models(cls) -> list[str]:
        return cls.supported

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        config = llm_request.config
        messages: list[dict[str, Any]] = []
        system = _system_text(config.system_instruction if config else None)
        if system:
            messages.append({"role": "system", "content": system})
        for content in llm_request.contents:
            messages.extend(_messages(content))
        body: dict[str, Any] = {"model": self.model, "messages": messages}
        tools = _tools(config.tools if config else None)
        if tools:
            body["tools"] = tools
        temperature = config.temperature if config and config.temperature is not None else None
        body["options"] = {
            "temperature": temperature_for(self.model) if temperature is None else temperature
        }
        started = time.monotonic()
        reply = await _chat(body, "lite")
        message = reply.get("message") or {}
        logger.info(
            "llm backend=ollama-adk model=%s latency_ms=%d input_tokens=%s output_tokens=%s "
            "tool_calls=%s text=%r",
            self.model,
            _ms(started),
            reply.get("prompt_eval_count"),
            reply.get("eval_count"),
            [_call_words(call) for call in message.get("tool_calls") or []],
            (message.get("content") or "")[:300],
        )
        parts: list[types.Part] = []
        if message.get("content"):
            parts.append(types.Part(text=message["content"]))
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            args = function.get("arguments") or {}
            if isinstance(args, str):
                args = json.loads(args or "{}")
            parts.append(
                types.Part(function_call=types.FunctionCall(name=function.get("name"), args=args))
            )
        if not parts:
            parts.append(types.Part(text=""))
        yield LlmResponse(
            content=types.Content(role="model", parts=parts),
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=reply.get("prompt_eval_count"),
                candidates_token_count=reply.get("eval_count"),
            ),
        )


LLMRegistry.register(OllamaLlm)


def _messages(content: types.Content) -> list[dict[str, Any]]:
    """One ADK turn as Ollama messages: a tool's results become ``tool`` messages of their own."""
    role = "assistant" if content.role == "model" else "user"
    text: list[str] = []
    images: list[str] = []
    calls: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    for part in content.parts or []:
        if part.text and not part.thought:
            text.append(part.text)
        elif part.inline_data is not None and part.inline_data.data:
            images.append(_b64(part.inline_data.data))
        elif part.function_call is not None:
            calls.append(
                {
                    "function": {
                        "name": part.function_call.name,
                        "arguments": part.function_call.args or {},
                    }
                }
            )
        elif part.function_response is not None:
            results.append(
                {
                    "role": "tool",
                    "tool_name": part.function_response.name,
                    "content": json.dumps(part.function_response.response, default=str),
                }
            )
    out: list[dict[str, Any]] = []
    if text or images or calls:
        message: dict[str, Any] = {"role": role, "content": "\n".join(text)}
        if images:
            message["images"] = images
        if calls:
            message["tool_calls"] = calls
        out.append(message)
    return out + results


def _tools(tools: Sequence[Any] | None) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for tool in tools or []:
        for declaration in getattr(tool, "function_declarations", None) or []:
            if declaration.parameters_json_schema is not None:
                parameters = declaration.parameters_json_schema
            elif declaration.parameters is not None:
                parameters = _json_schema(
                    declaration.parameters.model_dump(mode="json", exclude_none=True)
                )
            else:
                parameters = {"type": "object", "properties": {}}
            found.append(
                {
                    "type": "function",
                    "function": {
                        "name": declaration.name,
                        "description": declaration.description or "",
                        "parameters": parameters,
                    },
                }
            )
    return found


def _json_schema(node: Any) -> Any:
    """A google-genai ``Schema`` dump (``type: "OBJECT"``, ``any_of``) as plain JSON schema."""
    if isinstance(node, list):
        return [_json_schema(item) for item in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in _SCHEMA_DROP:
            continue
        if key == "type" and isinstance(value, str):
            out["type"] = value.lower()
        elif key == "any_of":
            out["anyOf"] = _json_schema(value)
        elif key == "properties":
            out["properties"] = {name: _json_schema(prop) for name, prop in value.items()}
        else:
            out[key] = _json_schema(value)
    return out


def _call_words(call: dict[str, Any]) -> str:
    function = call.get("function") or {}
    return f"{function.get('name')}{json.dumps(function.get('arguments'), default=str)[:160]}"


def _system_text(instruction: Any) -> str:
    if instruction is None or isinstance(instruction, str):
        return instruction or ""
    parts = getattr(instruction, "parts", None) or []
    return "\n".join(part.text for part in parts if getattr(part, "text", None))


def _user_text(parts: Sequence[LlmPart]) -> str:
    """The text parts in order; each image is announced by its label where it stands."""
    lines = [
        f"IMAGE {part.label or 'UNLABELLED'} (attached)"
        if part.kind == "image"
        else part.text or ""
        for part in parts
    ]
    return "\n".join(line for line in lines if line)


def _b64(data: bytes | None) -> str:
    return base64.b64encode(data or b"").decode("ascii")


def _describe(exc: BaseException) -> str:
    if isinstance(exc, httpx.TimeoutException | TimeoutError):
        return "timeout"
    if isinstance(exc, httpx.ConnectError):
        return f"Ollama is not answering at {_Config.url}"
    return f"{type(exc).__name__}: {exc}"[:300]


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _log(tier: Tier, call: LlmCall, outcome: str) -> None:
    logger.info(
        "llm backend=ollama tier=%s model=%s prompt=%s outcome=%s latency_ms=%d "
        "input_tokens=%s output_tokens=%s error=%s",
        tier,
        call.model_id,
        call.prompt_hash[:12],
        outcome,
        call.latency_ms,
        call.input_tokens,
        call.output_tokens,
        call.error,
    )
