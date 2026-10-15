"""data/demo/local-demo.json: the local Gemma demo starts the app with real settings on a case
that exists, and its run sheet names only pages the app serves."""

import importlib.util
import json
from pathlib import Path

from tephra.config import Settings

ROOT = Path(__file__).resolve().parents[1]
PLAN = json.loads((ROOT / "data" / "demo" / "local-demo.json").read_text(encoding="utf-8"))


def test_the_plan_settings_load_and_name_a_local_model() -> None:
    env = {key.removeprefix("TEPHRA_").lower(): value for key, value in PLAN["env"].items()}
    settings = Settings(_env_file=None, **env)
    assert settings.llm == "ollama"
    assert settings.model == settings.model_lite == PLAN["ollama"]["model"]


def test_the_case_exists_and_says_it_is_synthetic() -> None:
    manifest = ROOT / "data" / "replay" / PLAN["env"]["TEPHRA_REPLAY_CASE"] / "manifest.json"
    assert json.loads(manifest.read_text(encoding="utf-8"))["synthetic"] is True


def test_every_beat_is_on_a_page_and_the_sheet_prints_it() -> None:
    pages = {"/", "/assistant", "/desk", "/connect", "/guide"}
    assert {beat["page"] for beat in PLAN["beats"]} <= pages
    spec = importlib.util.spec_from_file_location("demo_local", ROOT / "scripts" / "demo_local.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sheet = module.run_sheet(PLAN, "http://localhost:8080")
    assert sheet.count("http://localhost:8080/") == len(PLAN["beats"])
