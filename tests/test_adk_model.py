"""Explicit model keys for every ADK agent (SPEC-FINAL §2.4, B1): a Gemini model carries the
key of the settings it was built from, ADK never reads one from the environment, a keyless
Gemini model is refused rather than handed over as a bare name, and an airline without a usable
key gets AI UNAVAILABLE with its reason. No model is called here."""

from pathlib import Path

import pytest
from google.adk.models import Gemini
from test_hosted_runtime import KEY_RFB, hosted_settings

from tephra.agents import adk_app
from tephra.agents.adk_runtime import AgentModelUnavailable, adk_model, agent_model
from tephra.agents.llm import (
    GeminiBackend,
    LlmPart,
    StubBackend,
    UnavailableBackend,
    backend_for,
    model_name,
)
from tephra.config import Settings
from tephra.models import TephraModel


class Answer(TephraModel):
    text: str


def test_a_gemini_name_carries_its_key_and_reads_nothing_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "the-process-key-is-not-used-here")
    settings = Settings(_env_file=None, llm="gemini", gemini_api_key=KEY_RFB)
    model = adk_model(settings)
    assert isinstance(model, Gemini)
    assert model.model == settings.model_lite
    assert model.client_kwargs == {"api_key": KEY_RFB, "vertexai": False}
    assert KEY_RFB not in repr(model)
    assert "client_kwargs" not in model.model_dump()
    assert model.api_client._api_client.api_key == KEY_RFB
    assert model.api_client.vertexai is False
    assert model_name(model) == settings.model_lite


def test_other_names_stay_names() -> None:
    assert adk_model(Settings(_env_file=None, llm="stub")) == "gemini-3.5-flash-lite"
    ollama = Settings(_env_file=None, llm="ollama", model="gemma4:e4b", model_lite="gemma4:e4b")
    assert adk_model(ollama) == "gemma4:e4b"
    unknown = Settings(
        _env_file=None, llm="gemini", gemini_api_key=KEY_RFB, model_lite="tephra-not-a-model"
    )
    assert adk_model(unknown) == "tephra-not-a-model", "ADK refuses it when the agent runs"


def test_a_keyless_gemini_model_is_refused_never_a_bare_name() -> None:
    keyless = hosted_settings(Path("/nonexistent"), llm="gemini")
    with pytest.raises(AgentModelUnavailable, match="no model key is set"):
        adk_model(keyless)


async def test_an_unavailable_backend_refuses_every_step_with_its_reason() -> None:
    settings = hosted_settings(Path("/nonexistent"), llm="gemini")
    reason = "the model key cannot be read: enter it again"
    backend = backend_for(settings, unavailable=reason)
    assert isinstance(backend, UnavailableBackend)
    assert (backend.name, backend.metered) == ("gemini", True)
    assert backend.model_id("lite") == settings.model_lite
    assert await backend.reserve("main") == reason
    value, call = await backend.structured(
        tier="lite",
        system="s",
        parts=[LlmPart.of_text("q")],
        schema=Answer,
        stub=lambda: Answer(text="never used"),
    )
    assert value is None
    assert (call.backend, call.error) == ("gemini", reason)
    with pytest.raises(AgentModelUnavailable, match="cannot be read"):
        agent_model(settings, backend)


def test_backend_for_builds_the_airlines_own_backend() -> None:
    keyed = hosted_settings(Path("/nonexistent"), llm="gemini", gemini_api_key=KEY_RFB)
    assert isinstance(backend_for(keyed, unavailable=None), GeminiBackend)
    stub = hosted_settings(Path("/nonexistent"))
    assert isinstance(backend_for(stub, unavailable=None), StubBackend)


def test_the_import_time_root_agent_is_built_through_adk_model() -> None:
    assert adk_app.root_agent.model == adk_model(adk_app.get_settings())
