"""``TEPHRA_POLICY_FILE``: an airline's own TEPHRA reads its own policy file;
the default is Policy A, unchanged."""

import json
import shutil
from pathlib import Path

import pytest

from tephra.config import PROJECT_ROOT, Settings
from tephra.policy import POLICY_FILE, load_policy

DATA = PROJECT_ROOT / "data"


def test_the_default_is_policy_a_unchanged() -> None:
    settings = Settings(_env_file=None)
    assert settings.policy_file == POLICY_FILE.as_posix()
    loaded = load_policy(settings.data_dir, settings.policy_file)
    assert loaded.content_hash() == load_policy(DATA).content_hash()


def test_an_airline_policy_file_is_loaded(tmp_path: Path) -> None:
    (tmp_path / "policy").mkdir()
    policy = json.loads((DATA / POLICY_FILE).read_text())
    policy |= {"policy_id": "RFA-POLICY-A", "title": "Ring of Fire Air policy A (ILLUSTRATIVE)"}
    policy["exposure"]["vertical_margin_ft"]["value"] = 3000
    (tmp_path / "policy" / "airline.json").write_text(json.dumps(policy))
    shutil.copy(DATA / POLICY_FILE, tmp_path / "policy" / "policy_a.json")
    settings = Settings(_env_file=None, data_dir=tmp_path, policy_file="policy/airline.json")

    loaded = load_policy(settings.data_dir, settings.policy_file)

    assert loaded.exposure.vertical_margin_ft.value == 3000
    assert loaded.label == "ILLUSTRATIVE, not an airline SRA"


@pytest.mark.parametrize(
    "path", ["../x.json", "policy/A.json", "/etc/policy.json", "policy/../x.json", "policy/a.txt"]
)
def test_a_path_outside_the_policy_folder_is_refused(path: str) -> None:
    with pytest.raises(ValueError, match="policy_file"):
        Settings(_env_file=None, policy_file=path)
