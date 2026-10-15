"""TEPHRA_LLM=ollama: every model step on a local Gemma model, offline here (Ollama's replies are
stand-ins; nothing is sent)."""

import asyncio
from typing import Any

import pytest
from google.adk.models import LLMRegistry, LlmRequest
from google.genai import types
from pydantic import BaseModel

from tephra.agents import ollama
from tephra.agents.llm import LlmPart, get_llm
from tephra.agents.ollama import LocalSlot, OllamaBackend, OllamaLlm
from tephra.agents.quota import use_lane
from tephra.config import Settings


class Answer(BaseModel):
    action: str


def _settings(**extra: Any) -> Settings:
    return Settings(
        _env_file=None, llm="ollama", model="gemma4:e4b", model_lite="gemma4:e4b", **extra
    )


def test_ollama_needs_ollama_tags() -> None:
    with pytest.raises(ValueError, match="Ollama tags"):
        Settings(_env_file=None, llm="ollama")


def test_get_llm_gives_the_local_backend_unmetered() -> None:
    llm = get_llm(_settings())
    assert isinstance(llm, OllamaBackend)
    assert (llm.name, llm.metered, llm.model_id("lite")) == ("ollama", False, "gemma4:e4b")


def test_adk_resolves_an_ollama_tag_to_the_local_model() -> None:
    assert LLMRegistry.resolve("gemma4:e4b") is OllamaLlm
    assert LLMRegistry.resolve("gemini-3.5-flash-lite") is not OllamaLlm


def test_structured_sends_the_schema_and_validates_the_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[dict[str, Any], str]] = []

    async def chat(body: dict[str, Any], tier: str) -> dict[str, Any]:
        sent.append((body, tier))
        return {"message": {"content": '{"action": "HOLD"}'}, "prompt_eval_count": 9}

    monkeypatch.setattr(ollama, "_chat", chat)
    llm = OllamaBackend(_settings())
    parts = [LlmPart.of_text("brief"), LlmPart.of_image(b"png", label="HIMAWARI")]
    value, call = asyncio.run(
        llm.structured(
            tier="main", system="sys", parts=parts, schema=Answer, stub=lambda: Answer(action="")
        )
    )
    assert value == Answer(action="HOLD")
    assert (call.backend, call.model_id, call.input_tokens, call.error) == (
        "ollama",
        "gemma4:e4b",
        9,
        None,
    )
    body, tier = sent[0]
    assert tier == "main"
    assert body["format"]["properties"]["action"]["type"] == "string"
    assert body["messages"][1]["content"] == "brief\nIMAGE HIMAWARI (attached)"
    assert body["messages"][1]["images"] == ["cG5n"]


def test_an_invalid_or_failed_reply_is_ai_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    replies: list[Any] = [{"message": {"content": '{"other": 1}'}}, OSError("refused")]

    async def chat(body: dict[str, Any], tier: str) -> dict[str, Any]:
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(ollama, "_chat", chat)
    llm = OllamaBackend(_settings())

    def ask() -> Any:
        return asyncio.run(
            llm.structured(
                tier="lite",
                system="s",
                parts=[LlmPart.of_text("q")],
                schema=Answer,
                stub=lambda: Answer(action=""),
            )
        )

    value, call = ask()
    assert value is None
    assert call.error.startswith("invalid_output")
    value, call = ask()
    assert value is None
    assert call.error == "OSError: refused"


def test_audio_is_refused_without_a_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ollama, "_chat", None)
    value, call = asyncio.run(
        OllamaBackend(_settings()).structured(
            tier="lite",
            system="s",
            parts=[LlmPart.of_audio(b"x", label="voice", mime_type="audio/wav")],
            schema=Answer,
            stub=lambda: Answer(action=""),
        )
    )
    assert value is None
    assert call.error == "the local model takes no audio"


def test_an_agent_turn_keeps_the_whole_conversation_and_returns_tool_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict[str, Any]] = []

    async def chat(body: dict[str, Any], tier: str) -> dict[str, Any]:
        sent.append(body)
        call = {"function": {"name": "plan_flights", "arguments": {"flight_ids": ["RFA1"]}}}
        return {"message": {"content": "", "tool_calls": [call]}}

    monkeypatch.setattr(ollama, "_chat", chat)
    declaration = types.FunctionDeclaration(
        name="plan_flights",
        description="Plan these flights.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "flight_ids": types.Schema(
                    type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)
                )
            },
            required=["flight_ids"],
        ),
    )
    request = LlmRequest(
        contents=[
            types.Content(role="user", parts=[types.Part(text="the task")]),
            types.Content(
                role="model",
                parts=[types.Part(function_call=types.FunctionCall(name="assess", args={"v": 1}))],
            ),
            types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(name="assess", response={"ok": 1})
                    )
                ],
            ),
        ],
        config=types.GenerateContentConfig(
            system_instruction="be the duty officer",
            tools=[types.Tool(function_declarations=[declaration])],
        ),
    )

    async def run() -> list[Any]:
        return [r async for r in OllamaLlm(model="gemma4:e4b").generate_content_async(request)]

    (response,) = asyncio.run(run())
    roles = [m["role"] for m in sent[0]["messages"]]
    assert roles == ["system", "user", "assistant", "tool"]
    assert sent[0]["messages"][1]["content"] == "the task"
    assert sent[0]["messages"][3] == {"role": "tool", "tool_name": "assess", "content": '{"ok": 1}'}
    tool = sent[0]["tools"][0]["function"]
    assert tool["parameters"]["properties"]["flight_ids"] == {
        "type": "array",
        "items": {"type": "string"},
    }
    (part,) = response.content.parts
    assert (part.function_call.name, part.function_call.args) == (
        "plan_flights",
        {"flight_ids": ["RFA1"]},
    )


def test_the_slot_serves_a_person_before_routine_work() -> None:
    slot = LocalSlot()
    order: list[str] = []

    async def job(name: str, lane: str) -> None:
        with use_lane(lane):
            async with slot:
                order.append(name)
                await asyncio.sleep(0)

    async def run() -> None:
        async with slot:  # busy: everything below queues
            tasks = [
                asyncio.create_task(job("routine-1", "routine")),
                asyncio.create_task(job("routine-2", "routine")),
                asyncio.create_task(job("ask", "interactive")),
            ]
            await asyncio.sleep(0)
        await asyncio.gather(*tasks)

    asyncio.run(run())
    assert order == ["ask", "routine-1", "routine-2"]


def test_thinking_is_for_the_plume_reader_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    ollama.configure(_settings())
    seen: list[bool] = []

    class Client:
        def __init__(self, **_: Any) -> None: ...

        async def __aenter__(self) -> "Client":
            return self

        async def __aexit__(self, *_: Any) -> None: ...

        async def post(self, url: str, json: dict[str, Any]) -> Any:
            seen.append(json["think"])
            assert json["options"]["num_ctx"] == 32768
            return type("R", (), {"status_code": 200, "json": lambda self: {"message": {}}})()

    monkeypatch.setattr(ollama.httpx, "AsyncClient", Client)
    asyncio.run(ollama._chat({"options": {}}, "main"))
    asyncio.run(ollama._chat({"options": {}}, "lite"))
    assert seen == [True, False]


def test_the_slot_takes_its_size_at_once() -> None:
    slot = LocalSlot(size=2)
    running = 0
    peak = 0

    async def job() -> None:
        nonlocal running, peak
        async with slot:
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.01)
            running -= 1

    async def run() -> None:
        await asyncio.gather(*(job() for _ in range(5)))

    asyncio.run(run())
    assert peak == 2
