"""Bound settings follow their provider; the process's settings never carry an airline's, and
the model key leaves the process environment alone once hosted is on."""

import asyncio
import os
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from tephra import config
from tephra.config import Settings, apply_process_env, bind_settings, get_settings

KEY = "AIzaTEST" + "x" * 31


@pytest.fixture
def process(monkeypatch: pytest.MonkeyPatch) -> Settings:
    settings = Settings(_env_file=None, region="java_bali")
    monkeypatch.setattr(config, "_process_settings", lambda: settings)
    return settings


def airline(stage: str = "shadow", **overrides: object) -> Settings:
    fields: dict[str, object] = {
        "fleet_prefixes": "RFB",
        "airline_name": "Ring of Fire Charter",
        "airline_icao": "RFB",
        "hosted_tenant": "RFB",
        "hosted_stage": stage,
        "region": "halmahera",
    }
    return Settings(_env_file=None, **(fields | overrides))


def test_unbound_is_the_process_settings(process: Settings) -> None:
    assert get_settings() is process


def test_bound_settings_follow_a_later_change_of_the_provider(process: Settings) -> None:
    held = [airline("shadow")]
    with bind_settings(lambda: held[0]):
        assert get_settings().airline.shadow
        held[0] = airline("live")
        assert not get_settings().airline.shadow
        assert get_settings().region == "halmahera"
    assert get_settings() is process


async def test_tasks_and_threads_see_the_bound_provider(process: Settings) -> None:
    held = [airline("shadow")]

    async def stage_later() -> str | None:
        await asyncio.sleep(0)
        return get_settings().hosted_stage

    with bind_settings(lambda: held[0]):
        task = asyncio.ensure_future(stage_later())
        held[0] = airline("live")
        assert await asyncio.to_thread(lambda: get_settings().hosted_stage) == "live"
    assert await task == "live"
    assert get_settings() is process


def test_process_settings_refuse_hosted_only_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)  # no .env
    unwrapped = config._process_settings.__wrapped__
    monkeypatch.setenv("TEPHRA_HOSTED_TENANT", "RFB")
    with pytest.raises(ValueError, match="TEPHRA_HOSTED_TENANT"):
        unwrapped()
    monkeypatch.delenv("TEPHRA_HOSTED_TENANT")
    (tmp_path / ".env").write_text("TEPHRA_HOSTED_TENANT=RFB\nTEPHRA_HOSTED_STAGE=live\n")
    with pytest.raises(ValueError, match="hosted airline's runtime"):
        unwrapped()


def test_only_a_hosted_airline_may_run_gemini_without_a_key() -> None:
    with pytest.raises(ValidationError, match="GEMINI_API_KEY"):
        Settings(_env_file=None, llm="gemini")
    keyless = airline(llm="gemini")
    assert keyless.gemini_api_key is None


def test_the_key_is_exported_only_without_hosted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "before")
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
    monkeypatch.setenv("GOOGLE_GENAI_USE_ENTERPRISE", "TRUE")
    keyed = Settings(_env_file=None, llm="gemini", gemini_api_key=SecretStr(KEY))
    apply_process_env(keyed, export_key=False)
    assert os.environ["GOOGLE_API_KEY"] == "before"
    assert os.environ["GOOGLE_GENAI_USE_VERTEXAI"] == "FALSE"
    assert os.environ["GOOGLE_GENAI_USE_ENTERPRISE"] == "FALSE"
    hosted = Settings(
        _env_file=None,
        llm="gemini",
        gemini_api_key=SecretStr(KEY),
        features="onboard,hosted",
        session_secret="s" * 40,
    )
    apply_process_env(hosted)
    assert os.environ["GOOGLE_API_KEY"] == "before"
    apply_process_env(keyed)
    assert os.environ["GOOGLE_API_KEY"] == KEY


def test_an_airlines_settings_never_reach_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "before")
    with pytest.raises(ValueError, match="never reach the process environment"):
        apply_process_env(airline(llm="gemini", gemini_api_key=SecretStr(KEY)))
    assert os.environ["GOOGLE_API_KEY"] == "before"
