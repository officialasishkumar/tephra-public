"""The operator policy file: every margin, buffer and minimum the code applies comes from
``data/policy/policy_a.json``, carries a unit and a reason, and changes only with a new
version."""

import json
import re
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

import tephra.agents.exposure_planner as planner
import tephra.agents.validators as validators
import tephra.config as config
import tephra.pipeline as pipeline
from tephra.config import PROJECT_ROOT, Settings
from tephra.models import OperatorPolicy
from tephra.policy import POLICY_FILE, load_policy

DATA_DIR = PROJECT_ROOT / "data"
CODE_DIR = PROJECT_ROOT / "tephra"
POLICY = load_policy(DATA_DIR)

PINNED_HASHES = {
    "2026.10.1": "8ce2e026c5f7de766c74c07a8ccb0998d23e9710675ab4946422ce01a0472a42",
    "2026.10.2": "4df955f1bda2326697374ba053d62004677759615d2cdfda947cff5cb712263a",
    "2026.10.3": "4e1d84a73f8693b0338ea45459718cafb4e62d1b5bd268b72a21dcaabaf4b75f",
    "2026.10.4": "6a00d8ac37b6943d4f876077933b5f8b6cff530f8e16013253b52d6b42ed7492",
    "2026.10.5": "9f8fcf4237451485adee8a12bc004aa10f930550a06c12f781185b92d6795fcb",
    "2026.10.6": "7538c6b1e01228000e396ebe5e96a16d41981b6594eeebf102f251674573b8d5",
    "2026.10.7": "bbb2a30efdd85680773fa8d3ad8d6d16f84de97dfced4be49efff89fccd2c73c",
    "2026.10.8": "5495a940c5ec4ab4c6e0ebf2126f2c190705b6c00bcb0835f48e8472c339d7b6",
    "2026.10.9": "51826941aff39903e27dbb642e543a60a37c583e8054a3f6440ddfc44d1011f9",
}
"""Each version's content hash. An edit without a new version fails here: every audit entry
names the version its draft was made under, so one version must mean one content."""

UNIT_BY_SUFFIX = {
    "ft": "ft",
    "fl": "FL",
    "nm": "NM",
    "m": "m",
    "min": "min",
    "kt": "kt",
    "deg": "deg",
    "s": "s",
    "usd": "USD",
    "count": "count",
    "pct": "pct",
}


def raw_policy() -> dict[str, Any]:
    return json.loads((DATA_DIR / POLICY_FILE).read_text(encoding="utf-8"))


def test_the_policy_file_loads_and_is_labelled_illustrative() -> None:
    assert POLICY.policy_id == "RFA-POLICY-A"
    assert POLICY.preset == "A"
    assert POLICY.label == "ILLUSTRATIVE, not an airline SRA"
    assert POLICY.sra_ref is None
    assert POLICY.risk_owner == "Flight Operations"
    assert "Doc 9974 App 5 5.4(d)(2)" in POLICY.summary_text


def test_every_value_has_a_reason_and_a_unit_that_matches_its_name() -> None:
    values = POLICY.named_values()
    assert len(values) == 48
    for name, value in values.items():
        assert value.source.strip(), name
        suffix = name.rsplit("_", 1)[1]
        assert value.unit == UNIT_BY_SUFFIX[suffix], name


def test_every_citation_is_used_and_quoted() -> None:
    cited = set(POLICY.summary_citation_ids)
    for item in [*POLICY.source_order, *POLICY.named_values().values()]:
        cited.update(item.citation_ids)
    assert cited == {citation.id for citation in POLICY.citations}
    for citation in POLICY.citations:
        assert citation.text.strip(), citation.id
        assert citation.ref.strip(), citation.id


def test_source_order_puts_official_areas_first_and_cites_doc_9974() -> None:
    assert [rule.rule_id for rule in POLICY.source_order] == [
        "S1_OFFICIAL_AREAS",
        "S2_VONA_ADDS",
        "S3_NON_OBSERVATION",
    ]
    assert all(rule.citation_ids == ["9974-2.4d"] for rule in POLICY.source_order)


def test_the_version_changes_with_the_content() -> None:
    actual = POLICY.content_hash()
    assert PINNED_HASHES.get(POLICY.version) == actual, (
        f"policy content changed: bump the version and pin {POLICY.version!r}: {actual!r}"
    )
    changed = POLICY.model_copy(
        update={
            "planner": POLICY.planner.model_copy(
                update={
                    "level_search_ft": POLICY.planner.level_search_ft.model_copy(
                        update={"value": 1000}
                    )
                }
            )
        }
    )
    assert changed.content_hash() != actual


def test_a_misspelt_key_is_refused() -> None:
    data = raw_policy()
    data["planner"]["level_serch_ft"] = data["planner"].pop("level_search_ft")
    with pytest.raises(ValidationError):
        OperatorPolicy.model_validate(data)


def test_a_missing_value_or_reason_is_refused() -> None:
    missing = raw_policy()
    del missing["fuel"]["hold_min"]
    with pytest.raises(ValidationError):
        OperatorPolicy.model_validate(missing)
    blank = raw_policy()
    blank["exposure"]["vertical_margin_ft"]["source"] = ""
    with pytest.raises(ValidationError):
        OperatorPolicy.model_validate(blank)


def test_an_unknown_citation_is_refused() -> None:
    data = raw_policy()
    data["source_order"][0]["citation_ids"] = ["no-such-paragraph"]
    with pytest.raises(ValidationError, match="unknown citation ids"):
        OperatorPolicy.model_validate(data)


def test_only_policy_a_exists_until_code_can_plan_over_under_or_through() -> None:
    data = raw_policy()
    data["preset"] = "B"
    with pytest.raises(ValidationError):
        OperatorPolicy.model_validate(data)
    assert [path.name for path in (DATA_DIR / "policy").glob("*.json")] == ["policy_a.json"]


def test_every_value_is_read_by_the_code() -> None:
    code = "\n".join(
        path.read_text(encoding="utf-8")
        for path in CODE_DIR.rglob("*.py")
        if path.name != "models.py"
    )
    for name in POLICY.named_values():
        field = name.split(".", 1)[1]
        assert re.search(rf"\.{field}\.value\b", code), f"{name} is in the policy but unread"


@pytest.mark.parametrize(
    ("module", "name"),
    [
        (config, "HOLD_MINUTES"),
        (config, "DIVERT_EXTRA_MINUTES"),
        (config, "ALTERNATE_MIN_VISIBILITY_M"),
        (config, "ALTERNATE_MIN_CEILING_FT"),
        (config, "ALTERNATE_ETA_WINDOW_MIN"),
        (planner, "ALTERNATE_CONE_BUFFER_NM"),
        (planner, "LEVEL_SEARCH_FT"),
        (planner, "LEVEL_BAND_FL"),
        (planner, "DIVERT_WITHIN_MIN"),
        (planner, "HOLD_WITHIN_MIN"),
        (planner, "HYPOTHESIS_HOLD_WITHIN_MIN"),
        (validators, "MAX_CHANGE_LEVEL_FL"),
        (pipeline, "URGENCY_LIMITS_MIN"),
    ],
)
def test_no_module_keeps_its_own_copy_of_a_policy_value(module: object, name: str) -> None:
    assert not hasattr(module, name)


def test_settings_no_longer_carry_policy_values() -> None:
    assert not {"vertical_margin_ft", "alternate_search_nm"} & set(Settings.model_fields)


def test_the_policy_loads_from_any_data_directory(tmp_path: Path) -> None:
    target = tmp_path / POLICY_FILE
    target.parent.mkdir(parents=True)
    target.write_text((DATA_DIR / POLICY_FILE).read_text(encoding="utf-8"), encoding="utf-8")
    assert load_policy(tmp_path) == POLICY
