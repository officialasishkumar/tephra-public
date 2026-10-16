"""data/demo/local-demo.json: the local Gemma demo starts the app with real settings on a case
that exists, and its run sheet names only pages the app serves."""

import hashlib
import importlib.util
import json
from datetime import datetime
from pathlib import Path

from tephra.config import Settings
from tephra.util.hashing import proxy_flight_number

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


def test_the_run_sheet_is_a_three_minute_demo_on_a_short_loop() -> None:
    """Six beats of about 30 s each; the replay loops a window short enough that its kept
    answers come round again within the warm-up, at real-time speed."""

    def seconds(stamp: str) -> int:
        minutes, secs = stamp.split(":")
        return int(minutes) * 60 + int(secs)

    starts = [seconds(beat["at"]) for beat in PLAN["beats"]]
    assert starts == sorted(starts)
    assert starts[0] == 0
    assert starts[-1] + 30 <= 180
    assert all(beat["say"].count(".") <= 1 for beat in PLAN["beats"])  # one sentence each
    assert {"/", "/assistant", "/desk"} <= {beat["page"] for beat in PLAN["beats"]}
    env = PLAN["env"]
    start = datetime.fromisoformat(env["TEPHRA_REPLAY_START"])
    end = datetime.fromisoformat(env["TEPHRA_REPLAY_END"])
    assert env["TEPHRA_REPLAY_SPEED"] == "1"
    loop_min = (end - start).total_seconds() / 60
    assert loop_min < PLAN["warm_up_min"] <= 2 * loop_min
    assert PLAN["warm_up_why"]


def test_the_flight_the_sheet_names_is_the_one_it_says() -> None:
    """RFA numbers come from a hash of the aircraft hex, which the generator takes from the
    callsign: the sheet's RFA7601 is CPA140."""
    hex_id = hashlib.sha256(b"tephra-demo:CPA140").hexdigest()[:6]
    assert proxy_flight_number(hex_id) == "RFA7601"
    assert any("RFA7601" in beat["do"] and "CPA140" in beat["do"] for beat in PLAN["beats"])
