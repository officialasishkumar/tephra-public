"""docs/LOCAL-TEST-ACCOUNTS.md against the local test server and seed scripts: the logins the
doc lists are the values the scripts use, the launcher's values make valid settings that can
run no model, and nothing in the three files looks like a live secret."""

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

from tephra.airline.models import AirlineAnswers
from tephra.config import PROJECT_ROOT, Settings
from tephra.hosted.keys import API_KEY
from tephra.hosted.settings_for import hosted_models

DOC = PROJECT_ROOT / "docs" / "LOCAL-TEST-ACCOUNTS.md"
SERVER = PROJECT_ROOT / "scripts" / "local_test_server.py"
SEED = PROJECT_ROOT / "scripts" / "local_test_seed.py"
LIVE_LOOKING = {
    "Google API key": re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    "TEPHRA push key": re.compile(r"\btph_[A-Za-z0-9_-]{16,}"),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9]{20,}"),
    "Slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
}


def _load(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module  # the seed imports the server's values by this name
    spec.loader.exec_module(module)
    return module


server = _load(SERVER)
seed = _load(SEED)


def _rows() -> dict[str, list[str]]:
    """The doc's login table: role -> [where, email or name, password or PIN], unquoted."""
    rows: dict[str, list[str]] = {}
    for line in DOC.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip().replace("`", "") for cell in line.strip().strip("|").split("|")]
        if len(cells) == 4 and cells[0] not in ("Role", "---"):
            rows[cells[0]] = cells[1:]
    return rows


def test_the_doc_lists_every_login_the_seed_makes() -> None:
    rows = _rows()
    assert rows == {
        "TEPHRA staff": ["/admin", seed.STAFF.email, seed.PASSWORD],
        f"{seed.AIRLINE} ({seed.ICAO}) ops manager, {seed.OPS_MANAGER.name}": [
            "/signin",
            seed.OPS_MANAGER.email,
            seed.PASSWORD,
        ],
        f"{seed.ICAO} dispatcher, {seed.DISPATCHER.name}": [
            "/signin",
            seed.DISPATCHER.email,
            seed.PASSWORD,
        ],
        f"{seed.ICAO} viewer, {seed.VIEWER.name}": ["/signin", seed.VIEWER.email, seed.PASSWORD],
        "Demo Desk (RFA dispatcher)": ["/desk", "any name", f"PIN {server.ENV['TEPHRA_DESK_PIN']}"],
    }


def test_the_doc_names_the_fake_model_key_and_the_commands() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert seed.FAKE_MODEL_KEY in text
    assert "uv run python scripts/local_test_server.py" in text
    assert "uv run python scripts/local_test_seed.py --wait" in text
    assert "never on the live site" in text
    assert f"http://127.0.0.1:{server.PORTS['on']}" in text
    assert f"http://127.0.0.1:{server.PORTS['off']}" in text


def test_the_seed_uses_the_servers_task_token() -> None:
    assert server.ENV["TEPHRA_TASK_TOKEN"] == seed.TASK_TOKEN


@pytest.mark.parametrize("hosting", ["on", "off"])
def test_the_launcher_values_are_valid_settings_that_run_no_model(
    hosting: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in server.REMOVED:
        monkeypatch.delenv(name, raising=False)
    for name, value in server.environment(hosting, 8080, tmp_path).items():
        monkeypatch.setenv(name, value)
    settings = Settings(_env_file=None)
    assert settings.llm == "stub"
    assert settings.gemini_api_key is None
    assert settings.sqlite_path == tmp_path / "tephra.sqlite3"
    assert ("hosted" in settings.features) is (hosting == "on")
    assert {"connect", "onboard"} <= settings.features


def test_the_answers_are_valid_onboarding_answers() -> None:
    answers = AirlineAnswers.model_validate(seed.ANSWERS)
    assert answers.airline.icao == seed.ICAO
    assert answers.airline.name == seed.AIRLINE
    assert answers.airline.ops_email == seed.OPS_MANAGER.email


def test_the_models_are_offered_and_the_fake_key_is_accepted_but_not_google_shaped() -> None:
    assert {seed.MODEL, seed.MODEL_LITE} <= hosted_models(Settings(_env_file=None)).keys()
    assert API_KEY.fullmatch(seed.FAKE_MODEL_KEY)
    assert not seed.FAKE_MODEL_KEY.startswith("AIza")
    assert "fake" in seed.FAKE_MODEL_KEY


def test_every_local_secret_says_it_is_local() -> None:
    for name in ("TEPHRA_SESSION_SECRET", "TEPHRA_TASK_TOKEN"):
        assert server.ENV[name].startswith("local-test-")
        assert "not-for-live" in server.ENV[name]


@pytest.mark.parametrize("path", [DOC, SERVER, SEED], ids=lambda p: p.name)
def test_nothing_looks_like_a_live_secret(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    found = [what for what, pattern in LIVE_LOOKING.items() if pattern.search(text)]
    assert found == []
